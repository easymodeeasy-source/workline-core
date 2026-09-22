# Review System P2 — Planning Review Gates: Integration Contract

Status: `CONTRACT FROZEN / FINAL READINESS REPAIR ROUND 2 (round 1: P2-CONTRACT-001..004; round 2: P2-CONTRACT-001, P2-CONTRACT-005; round 3: P2-CONTRACT-006; round 4: P2-CONTRACT-007; round 5: P2-CONTRACT-008; final readiness repair round 1: P2-READY-001..004 with P2-CONTRACT-004 closed again, and P2-READY-005, -006, -018, -024, -027; final readiness repair round 2: P2-READY-004 and P2-READY-029, with P2-CONTRACT-004 closed again) / IMPLEMENTATION NOT STARTED / PENDING INDEPENDENT FINAL IMPLEMENTATION READINESS RE-CHECK`

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
P2-CONTRACT-001 .. 008: CLOSED (round 1: 001-004; round 2: 001, 005; round 3: 006; round 4: 007; round 5: 008;
                        004 closed again by final readiness repair rounds 1 and 2; §33); cross-finding pass §34
P2-READY-001 .. 003:    CLOSED (final readiness repair round 1, §33.6)
P2-READY-004:           CLOSED (final readiness repair rounds 1 and 2, §33.6, §33.7)
P2-READY-029:           CLOSED (final readiness repair round 2, §33.7)
P2-READY-005, -006, -018, -024, -027:
                        RESOLVED (final readiness repair round 1, §33.6; the Git minimum of -027 split in
                        two by P2-READY-029, §33.7)
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
| round-2 repair baseline = contract under repair | `3a8b9cf0496b230ebcb773f5905d98f529b6b313` — local `main` of a fresh GitHub clone, `origin/main` and GitHub `refs/heads/main` verified equal, working tree clean; `src/`, `tests/`, Skills and `registry.md` still byte-identical to `b78be1c`; the repair changes this document only |
| round-3 repair baseline = contract under repair | `459f431c9715c5db0c50691d63f42d90b0c70513` — local `main` of a fresh GitHub clone, `origin/main` and GitHub `refs/heads/main` verified equal, working tree clean; `src/`, `tests/`, Skills and `registry.md` still byte-identical to `b78be1c`; the repair changes this document only |
| round-4 repair baseline = contract under repair | `bbdd93d38c48eddb86ce2200e27a4cc1f774a7bb` — local `main` of a fresh GitHub clone, `origin/main` and GitHub `refs/heads/main` verified equal, working tree clean; `src/`, `tests/`, Skills and `registry.md` still byte-identical to `b78be1c`; the repair changes this document only |
| round-5 repair baseline = contract under repair | `bd2e70da24bdb44b51ad7f9f9ee795e1625050c4` — local `main` of a fresh GitHub clone, `origin/main` and GitHub `refs/heads/main` verified equal, working tree clean; `src/`, `tests/`, Skills and `registry.md` still byte-identical to `b78be1c`; the repair changes this document only |
| final readiness repair round 1 baseline = contract under repair | `a6adf8106daf2a1d3f764798dc64a00d35fe12f7` — local `main` of a fresh GitHub clone, `origin/main` and GitHub `refs/heads/main` verified equal, working tree clean; `src/`, `tests/`, Skills and `registry.md` still byte-identical to `b78be1c`. The Final Implementation Readiness Check of this checkpoint raised P2-READY-001..004 (P2-READY-004 HIGH: P2-CONTRACT-004's form B is unsound) and the durable LOW items this repair folds in (§33.6); the repair changes this document only |
| final readiness repair round 2 baseline = contract under repair | `5e101a37fc86cd3b02c3bd0550b7e023070a5f54` — local `main` of a fresh GitHub clone, `origin/main` and GitHub `refs/heads/main` verified equal, working tree clean; `src/`, `tests/`, Skills and `registry.md` still byte-identical to `b78be1c`. The independent re-check of this checkpoint found two findings unresolved: P2-READY-004 (HIGH), because form L, read from `check-attr`, cannot tell a false state from the literal value `unset`, and P2-READY-029 (MID), because one Git minimum for review-v1 planning and for the publication barrier contradicted the barrier's own start rule (§33.7); the repair changes this document only |

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

Not implemented or activated by P2: START Review Gate; Work Formal Review runtime; Work completion Review; review-v1 `work_completed`; Work-terminal activation (`activation/work-terminal-v1.yaml` stays absent); Work-terminal Consumption totality; the P3 result-commit publication contract (`review-v1-split-v1`); P3 Class A / B / C; P3 Review-validity closure; P3 HEAD-advancement reuse; P3 stale-generation Work blocking; P3 Work commit / proof / push; P4+ learning, repair and policy systems. The planning publication contract of §18 is P2-native and activates none of them. Its publication barrier (§18.7) applies to every Workline push, legacy ones included, and, on a Git at or above `P2_PUBLICATION_GIT_MIN` (§5.7), refuses nothing in a history that holds no review-v1 planning registration commit: it asks nothing of the operation that pushes, only that what it publishes carries no unproven review-v1 registration. A history in which no commit ever touched the candidate-snapshot directory is cleared by one path-limited history read that every Git the live baseline runs on answers, so a legacy push of such a history is never refused because of the running Git's version (§5.7, §18.7).

Ungated planning writers stay ungated (reconnaissance §3.7 / Q18): `add_phases`, Related maintenance, plan exclusion with replan, START derivations, direct CREATE.

## 3. Terms

| term | meaning |
| --- | --- |
| planning operation | one call of `create_roadmap` (lock operation `roadmap-create`) or `enter_phase` (lock operation `phase-entry`) made with `review=` (§5) |
| planning mutation | the mutation that operation resumes or begins at its entry: owner `"roadmap"`, invocation = the live invocation plus the two markers of §5.2 |
| generation mutation | a mutation the planning operation starts, under its own lock and owner, to write exactly one gate generation transition of its Review Run (§11) |
| Run | the Review Run the planning mutation reserved (§6) — for a recovery planning mutation, the canonical Run it recovered (§12.4) |
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
| pre-Kp currency proof | the full currency re-proof on P, with the physical projection check of the recorded registration, right before Kp is recorded and right before a recorded Kp is replayed (§15.6) |
| registration commit | a commit that adds registration paths of a planning Run: Kp, or anyone's commit of those files (§18.7) |
| publication barrier | the rule that no Workline push publishes a history holding a registration commit unless the committed planning proof proves that registration (§18.7, §18.8) |
| checkout capability | the positive proof that Git reproduces canonical Review bytes in this repository and in a fresh clone, in four layers, all required (§14.5): HEAD's raw root `.gitattributes` ends with the canonical Review-attribute rule; HEAD holds no `.gitattributes` below `.workline/`; the committed evaluation prints form L; the effective evaluation prints form L with no filter driver named `unset` configured |
| canonical Review-attribute rule | the one line `.workline/review/** !text eol=lf -filter -ident -working-tree-encoding`, the last attribute rule of HEAD's root `.gitattributes`: the one Review checkout configuration P2 v1 supports, proven from its raw committed bytes (§14.5) |
| form L | the tuple `git check-attr` prints for a Review path under the canonical rule — `text` unspecified, `eol` lf, `filter`, `ident` and `working-tree-encoding` unset. A cross-check only: `check-attr` prints a literal value such as `filter=unset` with the same word as the false state, so the printed tuple never proves an attribute state by itself (§14.5) |
| fresh clone | a normal new clone of a commit: the repository's committed `.gitattributes` as its attribute source, no clone-specific `.git/info/attributes` added after cloning, any normal system or global configuration (§14.5) |
| committed planning proof (CP) | the proof, re-run from committed objects alone, that a registered Run's Kp (its exact bytes and its meaning), Consumption and Km are exactly what its Receipt authorized; the durable basis of C-2(Km) and the only thing that clears the publication barrier (§18.8) |
| canonical-input preflight | the pure check, before `_open`, that the request identity an explicit review-v1 invocation is about to make durable is exact P1 canonical data apart from mapping key order; a refusal begins nothing (§5.6) |
| canonical planning writer input (W) | `CanonicalPlanningWriterInput`: the exact inputs the live Roadmap, Phase CREATE and Work CREATE writer helpers receive on the review-v1 path, computed from the canonical Candidate record alone; computed, never stored (§7.8) |
| expected physical projection (E) | every path, add / modify transition, mode and exact byte Kp may carry — whole ledgers included — recomputed from W and Kp's parent P by the writer's own builders and planned-write computation; computed, never stored (§15.7) |
| display base check | the check, before each registration stage is recorded, that the working-tree entity files whose count allocates the stage's display numbers are exactly HEAD's plus the files the planning mutation's recorded stages wrote (§15.7) |
| matching Run | a canonical Review Run whose generation 1 carries this invocation's `review_kind` and `operation_identity` (§12.2) |
| recoverable Run | a matching Run that is cleanly persisted, reconstructs exactly, is not terminal and not set aside, has no registration commit, and — below generation 3 — has a current Candidate (§12.2–§12.3) |
| recovery planning mutation | a planning mutation begun after runtime loss to continue exactly one recoverable Run; its invocation carries `recovery_of_review_run_id` (§12.4) |
| set aside | a matching Run that a new Run does not continue (terminal or obsolete), named in the new Run's request envelope (`set_aside_runs`) and never recovered afterwards (§12.2, §12.8) |
| committed basis | a commit's committed view (§15.4) with W's expected registration effects applied by the writer's own planned-write computation: §15.7 steps 1–2 computed on that commit. The R9 selection (§7.7) and the freeze's projected checks (§7.6) are evaluated on the committed basis of HEAD, or of the base commit B of a rebuild (§13), and never on the working tree |
| working-tree compatibility check | the check at the freeze that the working tree and HEAD's committed view give the same declared base and, for a Phase entry, the same Work set of the Phase and the same R9 selection; a difference is `review_base_uncommitted` (§7.4) |
| pre-freeze resume setup | how a resumed review-v1 planning mutation that has recorded no effect and started no generation mutation completes its setup: its missing discovery outcome or recovered binding is established on that same mutation, its recorded reservations are reused (§12.9) |
| `P2_REVIEW_GIT_MIN` | Git 2.40.0: the oldest Git that may begin or resume an explicit review-v1 planning invocation, fixed by `git check-attr --source` of the checkout capability (§5.7) |
| `P2_PUBLICATION_GIT_MIN` | Git 2.31.0: the oldest Git that may run the publication barrier's registered-Run discovery and the committed planning proof, fixed by `git log --diff-merges=combined` of the add-history read (§5.7) |

## 4. Decision summary

| issue | frozen decision | section |
| --- | --- | --- |
| HUMAN-1 = A | keyword `review=PlanningReview(...)`; invocation markers `review_contract` / `publication_contract` | §5 |
| C-4 generation serialization | **Direction A**: every generation transition is its own `roadmap`-owned generation mutation, R2/R3 and the live helper unchanged | §11 |
| abandonment gap | the planning mutation is abandonable only before its first generation mutation starts (a recovery planning mutation: before its own first generation mutation); afterwards pending until a terminal outcome | §12, §12.4 |
| C-3 persisted proof | **Direction A**: Kp commit-only → exact proof → canonical reload from the committed result → equality → Consumption → Km commit-only → exact proof → push-only publication of exact Km | §15, §18 |
| C-2 planning Consumption binding | `review-consumption` **version 2** (Planning Consumption) with a `persisted_result` binding; v1 unchanged | §16 |
| ordering | Receipt → use check (`use_check_head`) → registration → pre-Kp currency proof → Kp → C-2(Kp) → Consumption → Km → C-2(Km) → publication barrier → publication | §17 |
| C-1 publication discriminator | durable invocation markers select `review-v1-planning-publication-v1`; legacy is the unchanged current-combined rule | §18.5 |
| C-5 invocation binding | markers augment, never replace, the request identity; Run / task / Receipt / Consumption IDs are planning reservations; generation invocations bind run, generation, transition and every hash | §5.2, §11.2 |
| C-6 runtime-loss rerun | never a substitute: after runtime loss the same logical invocation continues the same canonical Run and task (§12); a new Run only when none is recoverable | §12, §21, §23 |
| staleness | before a Receipt: terminal `stale`, nothing written; after the Receipt and before the registration: generation 4 (`open`) + Supersession in one stage, then terminal `stale`; after the registration began: `ReconcileRequired`, never `stale`; no re-review inside the operation | §13 |
| publication barrier (P2-CONTRACT-001) | no Workline push of any operation publishes a history holding a planning registration commit unless the committed planning proof (CP) proves that Run from committed objects at that push; the existence of a Consumption or of Km, and what the destination holds, are never proof | §18.7, §18.8 |
| C-2(Km) durable proof (P2-CONTRACT-001, round 2) | C-2(Km) = the operation's ownership checks + CP; its durable basis is the committed objects CP reads, reproducible in any clone; `publication_proof` is a runtime marker only; the barrier needs CP alone — safe history for another operation to publish ≠ a commit this planning mutation may adopt as its own | §18.2, §18.8 |
| runtime-loss recovery (P2-CONTRACT-005) | before any new Run is reserved, canonical recovery discovery finds the matching Runs; exactly one recoverable → a recovery planning mutation (`recovery_of_review_run_id`) binds the canonical Run, task, Receipt and domain IDs and continues the same Run and task; none → a new Run that records the set-aside Runs; several, or any matching Run that is incomplete → `ReconcileRequired` (`review_recovery_ambiguous`, `review_recovery_incomplete`) | §12.1–§12.9, §21.2 |
| exact physical projection (P2-CONTRACT-006, round 3) | Kp's delta must be exactly E: the path set, transitions, modes and every byte — whole ledgers included — that the writer's own builders and planned-write computation produce from the committed Candidate snapshot on Kp's exact parent P; one computation and one comparison for the pre-Kp proof, C-2(Kp) and the committed planning proof; semantic equality stays separately required, and each proof is required on its own; `registration_delta_digest` is derived from the proven E | §15.7, §15.3, §15.6, §18.8, §20 |
| canonical writer input (P2-CONTRACT-007, round 4) | on the review-v1 path the canonical Candidate is the only source of byte-affecting writer input: W is computed from the canonical Candidate record — mappings in the P1 canonical key order, sequences in Candidate order, every entry kept — and feeds the representability check, the actual registration, E, the pre-Kp proof, C-2(Kp), recovery and the committed planning proof; after the freeze the caller's plan or design never reaches a byte-producing helper; legacy is unchanged | §7.8, §7.6, §15.1, §15.7, §20 |
| canonical-input preflight (P2-CONTRACT-008, round 5) | before `_open`, and before the request identity is compared with any pending record, review-v1 checks the request identity with the live `validate_condition` and the P1 serializer — canonical data equal to the value apart from key order, canonical bytes, read back; a failure is `review_candidate_unrepresentable` (a condition the live validator refuses keeps its live refusal) with nothing begun; the full §7.6 check still runs after `_open`; legacy unchanged | §5.6, §7.6 |
| R9 basis (P2-READY-001) | the R9 selection and the freeze's projected checks are evaluated on the committed basis — HEAD's, or a rebuild's base commit B's, committed view with W's expected effects — never on the working tree; the freeze refuses with `review_base_uncommitted` when the working tree and HEAD give a different declared base, Work set of the Phase or R9 selection; every rebuild compares the declared base first (a difference follows the stale and base rules) and the rest of the Candidate only with the declared base equal (a difference is `ReconcileRequired`, `review_candidate_mismatch`) | §7.4, §7.6, §7.7, §13, §15.3, §18.8 |
| pre-freeze resume (P2-READY-002) | a resumed review-v1 planning mutation that has recorded no effect and started no generation mutation completes its setup on that same mutation: discovery runs again when its outcome is not recorded, recorded reservations are reused, a recovered binding is made or checked; a new Run for which discovery now finds a recoverable Run is `ReconcileRequired` (`review_discovery_changed`), never rewritten into a recovery; before its first generation mutation a review-v1 planning mutation is abandoned on every STOP, begun or resumed, a Phase entry included; legacy unchanged | §12, §12.4, §12.5, §12.9 |
| Phase-entry order (P2-READY-003) | argument, platform and Git version checks; the live checks up to the request identity; the preflight; the same-request and marker checks; the remaining live acceptance checks, `phase_already_expanded` included, under the live interrupted-entry rule for a pending mutation of this very request; canonical recovery discovery only with no pending planning mutation; `_open`; setup | §5.6, §11.8, §12.2, §12.7, §21, §28 |
| error reasons (P2-READY-005) | `ReconcileRequired` gains the attribute `reason` (default `None`; `code` unchanged); every `ReconcileRequired` P2 raises carries one reason of the catalogue | §25, §25.1 |
| `base_exact` (P2-READY-006) | removes only the independent-advancement step of the live classification; a recorded Kp classified unapplied is made only while HEAD is its `base_head`, after the pre-replay proof | §15.2, §15.6 |
| delta record types (P2-READY-018) | every scalar of `review-planning-delta` is text of an exact form: six-character octal modes, full lowercase hexadecimal object IDs of the repository's object format, status `A` / `M` | §15.7, §16.1 |
| authority routing (P2-READY-024) | `rules/git` owns the Git-operation rules, `skills/roadmap` the planning operation and its write scope, `skills/review` the meaning of Review records and proofs; each rule has one normative owner | §26 |
| Git minimums (P2-READY-027; split by P2-READY-029) | two independent thresholds. `P2_REVIEW_GIT_MIN` = 2.40.0: an explicit review-v1 invocation on an older Git, or on a Git whose version does not parse, stops before the lock (`review_git_unsupported`). `P2_PUBLICATION_GIT_MIN` = 2.31.0: the barrier's registered-Run discovery and the committed planning proof. Every push first runs the fast path, which needs no P2 minimum and clears a history that never touched the candidate-snapshot directory. On Git 2.31.0 or newer — 2.31 to 2.39 included, which cannot begin review-v1 planning — any other history is classified, and a Candidate snapshot without a registration commit begins no barrier. Below 2.31.0, or on an unknown version, its publication is refused as a capability failure (`review_publication_barrier`, the proof unavailable), which never asserts that a registration exists | §5.7, §18.7 |
| registration base (P2-CONTRACT-003) | `use_check_head` noted at the use check; Kp made on exactly its recorded parent P (`base_exact`); P = `use_check_head`, or a descendant through commits that touch no planning-owned path, with full currency on P; C-2(Kp) proves full currency on P's committed view | §13, §15.2, §15.3, §15.6, §17 |
| checkout capability (P2-CONTRACT-004; closed again by P2-READY-004, final readiness repair rounds 1 and 2) | one supported configuration: HEAD's root `.gitattributes`, read as raw committed bytes, ends with the canonical Review-attribute rule `.workline/review/** !text eol=lf -filter -ident -working-tree-encoding`; HEAD holds no `.gitattributes` below `.workline/`; the committed and the effective `check-attr` evaluations print form L, with no filter driver named `unset` configured. `check-attr`'s printed words never prove an attribute state: `-filter` and the literal `filter=unset` print the same `unset`, and a clone with a filter driver named `unset` runs it on the literal (**Measured**). Form B stays withdrawn; `-text`, `text=unset`, `text=unspecified` and the literal `unset` values are unsupported — not proven unsafe — and refused; every existing Review record must read canonically; fail closed before the first Review record; P1 reader unchanged; legacy unchanged | §14.5, §14.6 |
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
| no `review_contract` (legacy) | review-v1 | `ReconcileRequired` (`review_marker_mismatch`) — no silent upgrade; record untouched |
| the frozen marker pair | legacy | `ReconcileRequired` (`review_marker_mismatch`) — no silent downgrade; record untouched |
| the frozen marker pair | review-v1 | continue (resume by exact invocation) |
| the frozen marker pair plus `recovery_of_review_run_id` (a well-formed Review Run ID) | review-v1 | continue: the recovery planning mutation is resumed by its exact recorded invocation (§12.4) |
| the frozen marker pair plus `recovery_of_review_run_id` | legacy | `ReconcileRequired` (`review_marker_mismatch`) — no silent downgrade; record untouched |
| any other `review_contract` / `publication_contract` presence or value, a `recovery_of_review_run_id` without the marker pair, or any other added key | any | `ReconcileRequired` (`review_marker_mismatch`) — unknown contract, fail closed |

The check is added to the legacy entry too. It fires only for a pending record that carries a marker, which no baseline or legacy run writes, so every legacy outcome is unchanged; where it fires, the baseline would already stop the same call with `reconcile_required` through the scope overlap in `MutationController.open` (reconnaissance Q15, Measured), and now stops earlier with the same class and the reason `review_marker_mismatch`.

A review-v1 invocation that finds a pending review-v1 planning mutation for its slot resumes it by that record's exact invocation, with or without the recovery key: that is normal retry, and canonical recovery discovery does not run at the entry. While that mutation has recorded no effect and started no generation mutation, its resume completes its setup by the pre-freeze resume setup (§12.9), which runs discovery again only where the mutation has not recorded its outcome. Only when the slot has no pending review-v1 planning mutation does the entry run canonical recovery discovery (§12.2): after the remaining live acceptance checks (§5.6 step 6), before any planning mutation is begun or any ID reserved.

The canonical-input preflight (§5.6) runs before the live same-request check and before this comparison, on the current caller object, so no comparison ever serializes a caller value the canonical form cannot carry.

### 5.4 Platform and fail-closed

**Frozen.** `review` given and `workline.review.fsafe.immutable_create_supported()` false (POSIX at the baseline) → `StopError` code `review_create_unsupported` before `project_operation`: no lock, no mutation record, no write. Legacy invocations on POSIX are unchanged.

The checkout capability (§14.5) and the readability of the existing Review namespace (§14.6) are the second applicability condition of an opted-in invocation. They read the repository's attributes and records, so they are checked under the lock — readability first at recovery discovery (§12.2), both at the freeze or the recovery setup (§12.4) — before the first Review record: a failure is `review_checkout_unsafe`, `review_checkout_unknown` or `review_namespace_unreadable`, with nothing written. At recovery discovery no planning mutation exists yet, so nothing is begun; at the freeze or the recovery setup the planning mutation is abandoned (§12). Legacy invocations check none of this and are unchanged.

An opted-in invocation never falls back to the legacy path: every inability of the gate — platform, Git version (§5.7), checkout capability, Review namespace, Git persistence preflight, Context unavailable, reviewer failure, proof failure — is a STOP or a terminal review outcome, never an ungated registration.

### 5.5 What is never read to decide applicability

No Project-global activation state, no Review record, no `project.yaml` key and no prior Run decides whether a call is gated. Only the `review` argument does, and, for resume compatibility, the markers of the slot's own pending records. The publication barrier (§18.7) reads Review records in the published history, but it gates no call: it decides only whether a push may publish that history. Canonical recovery discovery (§12.2) reads the slot's matching Review Runs, but only to decide which Run a call that is already gated continues, never whether it is gated.

### 5.6 Canonical-input preflight

**Frozen.** An explicit review-v1 invocation proves, before anything is begun, that the caller values it is about to make durable can be carried by the frozen canonical form. The request identity I is the value `_open` makes durable in the planning invocation: `roadmap_request_identity(plan)` for a RoadmapPlan (`roadmap.py:459`), `design_identity(design)` for a PhaseEntryDesign (`roadmap.py:786`). Every caller value the Candidate takes is in it: names, desired states, sections, keys, relation references, Related `type` and `to`, and every Related `condition` of the normal Works, the integration and the confirmation.

Before `_open`, the live serialization of I is fragile. `MutationController.open` and `begin` normalize the invocation with `json.loads(json.dumps(invocation, sort_keys=True))` (`mutation.py:1668`, `mutation.py:1703`), and `Mutation._save` renders the record with `yamlish.dump` and writes it as UTF-8 (`mutation.py:379-385`, `durable.py:37-65`). A caller value outside what they carry fails there, with a serializer error, before §7.6 is reached (**Measured**, §31):

- a float, an empty mapping key or a sequence inside a sequence fails in `_save` (`YamlishError`);
- a lone surrogate fails in the UTF-8 write (`UnicodeEncodeError`) and leaves a runtime temporary file;
- a non-text key fails in `MutationController.open`'s `json.dumps(..., sort_keys=True)` (`TypeError`);
- a tuple is silently made a list.

The preflight is a pure function of the caller's object. It reads no Project state, reserves nothing, writes nothing, and uses no serializer but the P1 one. It runs two checks, in this order:

1. **Live condition validation.** Each `condition` of a conditional Related type goes through the live `validate_condition` (`validate.py:48-61`). That function is pure, and it is the rule `validate_related_specs` applies after `_open` (`create.py:116-133`). A refusal is that live refusal, unchanged: `ValidationError` code `validation_failed`, the same message. Only its time moves forward. It checks `kind` and `pattern` and keeps every further entry.
2. **Canonical representability** of I, with the P1 serializer (`review/serialize.py`) alone. All of these must hold:
   - `serialize.canonical_data(I)` succeeds: every mapping key is text, and every scalar is text, an integer, a boolean or null. A float (NaN included) and any other type are refused.
   - `serialize.canonical_data(I) == I` under Python equality. That equality ignores mapping key order at every depth and tells a tuple from a list, so canonicalization may change key order and nothing else.
   - `serialize.canonical_bytes` of a record holding I succeeds: every key rendered as a mapping key is non-empty, no sequence sits directly inside a sequence, and all text encodes as UTF-8.
   - `serialize.canonical_roundtrips` of that record holds: the canonical text reads back as the same data.

   A failure → `ValidationError` code `review_candidate_unrepresentable`, with a detail that names the caller value and says the caller input cannot be canonicalized. No serializer exception (`TypeError`, `YamlishError`, `UnicodeEncodeError`) is ever the outcome.

**What passes:**

- **Key order.** Mapping key order is never a refusal. `{"pattern": "src/*.py", "kind": "path_glob"}` and `{"kind": "path_glob", "pattern": "src/*.py"}` both pass, at any depth, and become the same Candidate and the same W (§7.8).
- **No schema narrowing.** Nested mappings and extra condition entries pass whenever the P1 form carries them exactly.
- **The P1 serializer decides.** A value the P1 form carries passes wherever it sits. An empty key inside a mapping that is an item of a sequence renders and reads back, so it passes (**Measured**). A value the P1 form does not carry is refused wherever it sits: the whole of I is checked, conditions and names alike.

Passing is exactly what the live invocation serialization needs. For a value that passes, `json.dumps(..., sort_keys=True)` returns the same value in the same (code point) key order the P1 form uses, `yamlish.dump` renders it, it reads back, and the UTF-8 write succeeds (**Measured**, §31). So after the preflight, `_open` cannot fail on the caller's values.

On a refusal nothing exists to undo: no planning mutation (so nothing is abandoned), no reservation, no Review record, no domain effect and no runtime file. A pending planning mutation of the slot stays exactly as it is.

**It is not §7.6.** The preflight proves only that the caller values can be carried. §7.6 still runs after `_open` and the reservations, over the Candidate and W as built: the projected effects, `validate_structure`, the semantic round trip, R9, and the representability of the whole Candidate record. A refusal there abandons the planning mutation (§12). Both checks use `review_candidate_unrepresentable`, and the detail says which one refused: a caller value that cannot be canonicalized (here), or a projected Candidate or persistence mismatch (§7.6).

**Where it runs.** The review-v1 entry order:

```text
1  §5.1 argument validation; §5.4 platform check; §5.7 Git version check        (before the lock)
2  the live checks that precede the request identity, unchanged:
     Roadmap creation: the payload checks, the structure precheck
     Phase entry:      the structure precheck; the Phase, Roadmap and lifecycle states; the dependencies
3  the request identity (the live roadmap_request_identity / design_identity)
4  this preflight
5  the live same-request check (require_same_request / _require_resumable) and the marker check (§5.3)
6  the remaining live acceptance checks, unchanged (Phase entry: already expanded, at least one normal
   Work, reserved Work keys, the explicit entry's startability, the unique entry; Roadmap creation has
   none), under the live interrupted-entry rule below
7  only when the slot has no pending review-v1 planning mutation: canonical recovery discovery (§12.2)
8  _open: the pending planning mutation resumed by its exact recorded invocation, or a planning
   mutation begun (MutationController.begin) for a new Run or a recovery (§12.4)
9  setup: a resumed planning mutation that has recorded no effect and started no generation mutation
   completes its setup by the pre-freeze resume setup (§12.9); a new Run: the recovery_discovery note,
   the reservations, the Candidate on the committed basis with the working-tree compatibility check
   (§7.4, §7.7), W, the full representability check (§7.6) and the rest of the freeze (§14.4); a
   recovery: the recovered reservations and its setup (§12.4, §12.5), with W from the committed
   snapshot (§7.8)
then the Review flow
```

This order is frozen for both kinds (P2-READY-003). Live Roadmap semantics decide whether the call is an admissible operation (steps 2, 5 and 6) before Review recovery decides which Run it continues (step 7).

**The live interrupted-entry rule.** The live Phase-entry code takes a pending Phase entry of this Phase that is this very request for an interrupted expansion (`_pending_phase_entry`, `_require_resumable`, `roadmap.py:786-792`). On the review-v1 path that is the pending review-v1 planning mutation step 5 accepted as this request. For it, as for a live interrupted expansion, two checks of step 6 are skipped:
- `phase_already_expanded` (`roadmap.py:793-805`), so the mutation's own applied registration stages are never taken for a finished expansion;
- the unique-entry check (`_require_unique_entry`, `roadmap.py:812-817`).

Every other check of steps 2 and 6 always runs: the structure precheck, the Phase, Roadmap and lifecycle states, the settled-lifecycle check, the dependencies, the at-least-one-normal-Work and reserved-key checks, and the explicit entry's startability (`_require_startable_entry`, `roadmap.py:811`).

**No pending mutation.** With no pending planning mutation for the slot, an already expanded Phase stops at step 6 with the live `phase_already_expanded`, before canonical recovery discovery. A historical Run of that Phase is not read to answer the caller — whether it was consumed, or holds a registration commit the committed planning proof does not prove. The publication barrier keeps any such unproven registration commit out of every published history on its own (§18.7). Discovery, with its `review_recovery_incomplete` and `review_recovery_ambiguous` refusals, runs only for an admissible operation: every Roadmap creation, and a Phase entry that passed step 6.

**Resume.** A resumed planning mutation passed the preflight when it was begun. The preflight still runs on the current caller object, because it comes before the comparison that decides whether the pending mutation is this request (step 5):

- an unrepresentable caller → the refusal, with the pending mutation untouched;
- a representable caller → the live comparison decides, as before.

**Recovery.** Canonical recovery discovery matches Runs by the operation identity digested from I (§6.2, §12.2), so the preflight comes first. An unrepresentable caller is refused before discovery and before any recovery planning mutation, and the canonical Run is left untouched. Once a Run is recovered, the caller's values only prove the identity: the writer takes W from the committed snapshot (§7.8).

**Legacy** invocations run no preflight. They keep their live outcomes, the serializer errors above included (§29 item 7).

### 5.7 Minimum Git versions

**Frozen** (P2-READY-027; split by P2-READY-029). P2 has two Git minimums. Each is fixed by the newest Git feature its own work needs, and the two are independent:

| threshold | value | what needs it | the newest Git feature it needs |
| --- | --- | --- | --- |
| `P2_REVIEW_GIT_MIN` | 2.40.0 | beginning or resuming an explicit review-v1 planning invocation | `git check-attr --source=<tree-ish>`, which the committed evaluation of the checkout capability runs (§14.5): the release notes of Git 2.40.0 record `check-attr` learning to read `.gitattributes` from a given tree-ish |
| `P2_PUBLICATION_GIT_MIN` | 2.31.0 | the publication barrier's registered-Run discovery and the committed planning proof (§18.7, §18.8) | `git log --diff-merges=combined` of the add-history read: Git 2.31.0 accepts `combined` (`diff-merges.c`), while Git 2.30.0 accepts only `--diff-merges=off` and stops on any other value (`revision.c`) |

**What review-v1 planning needs besides.** Everything else it runs is older than 2.40.0: `GIT_CONFIG_GLOBAL` of the isolated attribute evaluation (2.32.0), the publication command set below, and `check-attr --stdin -z`, `add` and `commit --only`, long present.

**The publication command set.** Every command the barrier and the committed planning proof run, audited against the release notes installed with Git for Windows 2.54.0 and against the Git sources of the versions named (**Measured**, §31):
- the fast path, `git rev-list --full-history -n 1 <C> -- .workline/review/candidate-snapshots/`: `--full-history` present in Git 2.0.0;
- the add-history read, `git log --full-history --no-renames --diff-merges=combined --diff-filter=A --name-only -z` (§12.2, §18.7): `--diff-merges=combined` since 2.31.0; `--no-renames`, `--diff-filter`, `--name-only` and `-z` present in 2.0.0;
- deltas: `git diff-tree -r -z --no-renames --no-abbrev --raw` (CP5, CP12) and `git diff-tree --no-commit-id --name-only -r -z --no-renames` (`gitcmd.commit_changes`): `--no-abbrev` and `--raw` present in 2.0.0;
- objects: `git cat-file blob`, long present; `git ls-tree -r -z --full-tree` (the blob check, modes, the committed-result loader), `--full-tree` since 1.6.1.2; `git hash-object --no-filters` (the blob IDs of E, §15.7), before 1.7.1;
- ancestry: `git merge-base --is-ancestor`, since 1.8.0; `git rev-list --full-history <A>..<B> -- <paths>` (`gitcmd.commits_touching`) and `git rev-list --parents -n 1` (`gitcmd.commit_parents`), present in 2.0.0; `git rev-parse --verify`, long present;
- the object format: no command. A repository's object format is the length of its full object IDs — 40 hexadecimal characters for SHA-1, 64 for SHA-256, the forms `gitcmd` accepts (`gitcmd.py:17-18`). SHA-256 repositories need Git 2.29.0, the final leg of SHA-256 support, which is below both minimums: no minimum drops SHA-256.

The newest is `--diff-merges=combined`, so `P2_PUBLICATION_GIT_MIN` is 2.31.0. One command set, one minimum: no substitute spelling (such as `-c`) is ever run on an older Git. None of these commands evaluates attributes or reads a checked-out file. The committed planning proof reads committed objects only (§15.4, §18.8), so it needs no `check-attr --source` and no checkout of the Review namespace.

**Reading the version.** The running Git's version is read once per process with `git --version`, as its first three numeric components (`git version 2.54.0.windows.1` gives 2.54.0). A version text that does not parse is an unknown version, which meets no minimum.

Frozen behaviour:

- **The review-v1 gate.** An explicit review-v1 invocation (`review=PlanningReview(...)`) on a Git older than `P2_REVIEW_GIT_MIN`, or of unknown version, stops at §5.6 step 1 with `StopError` code `review_git_unsupported`: before the project lock, `_open`, any planning mutation, reservation, Review record or domain effect. A pending review-v1 planning mutation of the slot is left exactly as it is, and continues once a Git at or above the minimum resumes it.
- **Legacy invocations** run no version gate and are refused by nothing here.
- **The publication barrier**, at every Workline push (§18.7):
  1. *The fast path runs first, on any Git.* When the read runs and lists nothing, no planning Candidate snapshot ever entered the history: the barrier is clear, and no P2 minimum and no P2 proof machinery takes part, so a legacy-only history publishes exactly as before. A read Git fails to answer holds the barrier.
  2. *A listed commit, on a Git at or above `P2_PUBLICATION_GIT_MIN`:* registered-Run discovery and the committed planning proof run (§18.7, §18.8). A Run whose registration paths were never added has no registration commit and begins no barrier, at every generation: a Candidate snapshot alone never begins one.
  3. *A listed commit, on a Git below `P2_PUBLICATION_GIT_MIN` or of unknown version:* the classification cannot run, so publication is refused — `StopError` code `review_publication_barrier`, with the detail "publication proof unavailable: the running Git is below P2_PUBLICATION_GIT_MIN (2.31.0)", or "... the running Git's version is unknown". This is a capability refusal before any Run is classified. It names no Run and no registration commit, and it never states that a registration exists — only that its presence or absence cannot be established on this Git.
- **Git 2.31.0 up to, not including, 2.40.0** cannot begin or resume review-v1 planning, and can prove and publish an existing P2 history whose committed planning proof passes.

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
| `review-v1-planning-committed-proof-v1` | the committed planning proof CP, re-run from committed objects (§18.8) |
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

Properties, each by construction: every key part is colon-free and stripped (`gate._require_key_part`); every value is stable across retry (the request identity is durable before any reservation; the target is a planning reservation for RoadmapPlan and the given, existing Phase ID for PhaseEntryDesign); none uses a display number, a timestamp or a process identity; `operation_identity` binds the exact request / design semantics, and not the insertion order of a caller's mapping (the digest is over canonical bytes; **Measured**, §31); the kind names carry the planned object and a version, and this contract reserves the `roadmap-` and `phase-entry-` prefixes for planning kinds, so a Work review kind cannot collide; `authorized_operation_stage` names exactly the registration stages of the planning mutation that holds the Consumption, committed as Kp (§15.1) — nothing else is authorized by the Receipt.

### 6.3 Where each Review ID is reserved

**Frozen.** All four in the planning mutation, at the freeze (§14.4), in this order: Run, task, Receipt (`review-receipt:<run_id>:3` — generation 3 is the only generation of a P2 Run that seals; generation 4, when written, is an invalidation generation with status `open` that issues nothing, §11.6), Consumption (`review-consumption:<receipt_id>`). The Supersession path of an invalidation is keyed by the reserved Receipt ID (`.workline/review/supersessions/<receipt_id>.yaml`), so it too is known at the freeze. Generation mutations reserve nothing; their invocations carry the IDs they use. Reservations are per mutation (live `Mutation.reserve_id`), so a Run reserved by one planning mutation is unreachable from any other — except through the recovery binding of §12.5, which only a recovery planning mutation performs, for exactly one recoverable Run. A recovery planning mutation never reserves anew an ID that is already canonical: it binds the Run and task IDs, the Receipt ID once generation 3 exists, and every domain ID from the committed records, and reserves only the IDs that never became canonical (§12.6).

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
- Reconstruction on resume: from the planning invocation (`request` / `design`), the planning mutation's reserved IDs (for a recovery planning mutation, the IDs bound from the snapshot, §12.5), the declared base recomputed under the lock on the committed view of the base commit B that currency is evaluated on (§7.4, §13), and the R9 selection recomputed on the committed basis of B (§7.7). The declared base is compared first: a different declared base is staleness or, once the registration began, reconciliation (§13 item 3). Only with the declared base equal is the rest compared: the rebuilt record must digest to the Run's `candidate_hash` and equal the stored snapshot's `material`, and any other difference is `ReconcileRequired` (reason `review_candidate_mismatch`, §13 item 4). The rebuilt record is compared, never written from — the writer takes W from the stored snapshot (§7.8).
- After runtime loss the planning mutation's reservations are gone, but the Candidate is not: the committed snapshot holds the reviewed content with every reserved domain ID, and the Run's records hold the Run and task IDs. The same logical invocation recovers them (§12): discovery, then a recovery planning mutation that binds exactly those IDs and continues the same Run and task. A fresh Candidate (new reserved IDs, new `candidate_hash`, new Run) is built only when no matching Run is recoverable (§12.8), and a matching Run that cannot be shown whole stops the call instead of being replaced (§12.3). A registration commit whose Run has no CP-proven Consumption is never recovered and never bypassed: the publication barrier keeps it unpublished (§18.7, §21.2).

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

The only normalization is the stripping the live writer itself performs (`store.render_body` strips section text; `roadmap_request_identity` records the same). Names stay verbatim. Frozen P1 R8 §3 fields are all present; the caller keys are reviewed semantics carried through the reservation map (Frozen P1 R8 §4, §6). A RoadmapPlan holds no caller-supplied mapping, and §7.8 applies to it all the same: after the freeze a review-v1 Roadmap creation writes from the Candidate, never from the caller's plan.

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
        condition: <null, or the caller's mapping as serialize.canonical_data gives it (§7.8)>
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

A condition is recorded as `serialize.canonical_data` gives it: keys in the P1 canonical order at every depth, every entry kept, sequences in their order. Two conditions equal as values are one Candidate value, whatever their key insertion order; a condition whose canonical form would differ from it in anything but key order is refused before `_open` by the canonical-input preflight (§5.6).

### 7.4 Declared base

**Frozen.** Computed under the lock on the committed view of HEAD (§3, §15.4) — at the freeze HEAD is `review_binding.head` — never on the working tree: the registration is committed on a commit, and the currency that authorizes it is that commit's (§13). Part of the Candidate and so of `candidate_hash` (Candidate 7 §4.1: "reviewed artifact identity plus declared base/context identity"). The live preconditions keep reading the working tree, unchanged. A working-tree-only change of a declared-base fact is never part of the base, and the freeze refuses to review while one exists (the working-tree compatibility check below). At every evaluation after the freeze, a declared-base difference is decided by §13.

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

**Working-tree compatibility check** (P2-READY-001). At the freeze, while the Candidate is built (§14.4 step 2) and before any Review record, review-v1 proves that no uncommitted change alters a fact the Candidate is derived from. The same production `ProjectView` code computes each of these twice — on the working tree (`ProjectView.load(store)`, the view the live preconditions read) and on HEAD's committed view (§15.4):

- the declared base above;
- PhaseEntryDesign: the Work set of the Phase (`phase_works`, the fact of the live "no Work" precondition);
- PhaseEntryDesign: the R9 selection (§7.7) — on the committed basis of HEAD, and on the working tree with the same expected effects applied (`ProjectView.load(store).with_effects(...)`, used for this comparison and nowhere else).

The two sides must be equal; otherwise `ValidationError` code `review_base_uncommitted`, before any Review record, and the planning mutation is abandoned (§12). An entity the declared base names that the committed view does not hold (a Phase or Work present only in the working tree) is one such difference.

- **What it covers.** Both sides are `ProjectView`'s reading of the same canonical files — the entity files, `relations/roadmap.yaml`, `relations/related.yaml` and `events/events.jsonl` — so the comparison covers every file these facts are derived from. An uncommitted change that alters a compared fact is refused: a change to the Phase or Roadmap entity, to a Work the design names, to a relation, or to a lifecycle event of any of them (a `phase_resumed` of a held Phase, a predecessor's `work_completed`).
- **What it does not cover.** An uncommitted change that alters no compared fact — another Roadmap's event, a file no compared fact reads — leaves the Candidate exactly as HEAD gives it, and is not refused. No whole-working-tree cleanliness is required.
- **What the working tree is for.** It is checked for safety only, and is never the semantic basis of the Candidate: the Candidate is derived from HEAD's committed view and, for R9, from the committed basis (§7.7).

`review_base_uncommitted` therefore has one meaning: a fact the review would rest on is not committed.

### 7.5 Excluded as presentation or runtime material

Display numbers (`R-xx`, `P-xx`, `W-xx`), commit messages, frontmatter layout and key order, ledger file order and whole-file rendering, timestamps, mutation IDs, lock holder, Git commits and branch, the `entry` field as such (the canonical first Work stands for its meaning, §7.7), filesystem enumeration order. The bytes that carry display and layout are never reviewed as meaning, and they are not free: Kp must hold exactly the expected physical projection (§15.7), which the pre-Kp proof (§15.6 item 6), C-2(Kp) (§15.3 P3) and the committed planning proof (§18.8 CP5) require. A layout the reader accepts with the same meaning is a physical mismatch. The key order of a caller-supplied mapping (a Related condition) is likewise no reviewed meaning: the reviewed condition is the mapping value. Once the Candidate is frozen, its canonical representation is what the writer receives (§7.8), so it decides the bytes without adding anything to what was reviewed.

### 7.6 Representability check (pre-Review)

**Frozen.** At the freeze, after every reservation and the live payload and structure refusals, before any Review record:

1. the expected effects, built from W (§7.8) — computed from the canonical Candidate record, never from the caller's plan or design — by the writer's own builders, exactly as §15.7 step 2 builds them on HEAD: RoadmapPlan: the Roadmap `write_file` effect exactly as `_create_roadmap` builds it (`roadmap.py:478-486`) plus the `decide_phases` effects; PhaseEntryDesign: the three stages' effects built by the registration core's own effect builder (`create._registration_effects` with `_allocated_displays`, counts accumulating across stages, the reserved relation and Related IDs) — reused, or extracted as pure functions with no behaviour change;
2. `projected` = the committed basis of HEAD (§3; P2-READY-001): HEAD's committed view (§15.4) with those effects applied by the writer's own planned-write computation, i.e. `ProjectView.load` over the scratch directory of §15.7 steps 1–2 computed on HEAD. The working tree is not the basis; the working-tree compatibility check (§7.4) proves it gives the same facts;
3. `validate_structure(projected) == []`;
4. `adapter.normalize_persisted(adapter.load_persisted(result identity, projected))` equals `adapter.normalize_candidate(...)` exactly (projection identity);
5. PhaseEntryDesign: R9 (§7.7) evaluated on `projected`.

Every caller value the Candidate takes has passed the canonical-input preflight before `_open` (§5.6), so no caller value the canonical form cannot carry reaches this point. The Candidate record itself — caller values, reserved IDs and declared base together — must still be canonical data that renders and reads back (`serialize.canonical_bytes`, `serialize.canonical_roundtrips`); otherwise `ValidationError` code `review_candidate_unrepresentable`, the detail naming a projected Candidate representability failure.

Failure of 3 → the live refusal (`ValidationError` code `postcheck_failed`); of 4 → `ValidationError` code `review_candidate_unrepresentable`; of 5 → the R9 codes of §7.7. Every one happens after `_open` and before any Review record or domain effect, and the planning mutation is abandoned (§12); a refusal of the canonical-input preflight comes before `_open` and begins nothing (§5.6). Nothing is normalized away to make it pass: a Roadmap name with a trailing space, a `## heading` line injected into a section, a CR or CRLF in any text, U+2028 in a name — every loss the reconnaissance measured (§10.2 there) — is refused here, and a lone CR can therefore never strand a review-v1 run (reconnaissance §17 item 1).

This check predicts the committed result on HEAD with the same W, the same effect builders and the same planned-write computation the expected physical projection uses (§7.8, §15.7 steps 1–2), and the working-tree compatibility check (§7.4) proves that the working tree agrees on every fact the Candidate is derived from. It is not the persisted proof, which is over the committed result, physically and semantically (§15.3, §15.7).

### 7.7 R9 canonical self-selection

**Frozen P1** R9 §4, §11 as repaired: the rule belongs to Roadmap authority, the adapter only verifies it, legacy is unchanged.

**Frozen.** Roadmap-owned code evaluates the selection on the committed basis only (§3; P2-READY-001), never on the working tree (all new Works are in the Phase, which held no Work before):
- at the freeze, on the projected view of §7.6: HEAD's committed view with W's expected effects;
- in every rebuild, on the committed view of the base commit B with W's expected effects (§13);
- in P8/P9 and CP6, on the committed view of Kp, which P3 and CP5 prove to be P with exactly E;
- in the working-tree round trip, on HEAD's committed basis (§15.1 step 2).

The selection is:

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

The rule applies to review-v1 invocations only; `tests/helpers.simple_entry`, which relies on the legacy acceptance of an explicit entry among equals, is unaffected. The adapter recomputes the selection on the committed view (§15.3 P9) and never decides it. The live `_require_startable_entry` and `_require_unique_entry` still run on the working tree before `_open`, as live admissibility checks (§5.6 step 6). At the freeze, the working-tree compatibility check (§7.4) makes the working tree and the committed basis give the same selection, so a frozen Candidate never rests on a selection the committed basis does not give.

### 7.8 The writer hand-off: `CanonicalPlanningWriterInput`

**Frozen.** On the review-v1 path the canonical reviewed Candidate is the only source of every byte-affecting registration writer input. The caller's `RoadmapPlan` / `PhaseEntryDesign` validates the invocation (the canonical-input preflight, §5.6; the live payload refusals, §7.6, §7.7), is what the Candidate is built from, and gives the request identity (§6.2). Once the Candidate is frozen, the caller's object never reaches a byte-producing helper again. Legacy invocations are unchanged: they hand the caller's objects to the live writer exactly as today.

`CanonicalPlanningWriterInput` — W — is the one concept that turns the Candidate back into the exact inputs the live Roadmap, Phase CREATE and Work CREATE writer helpers consume. It is deterministic and computed from the canonical Candidate record alone. It is never stored; it is no Project or Review record, no lifecycle truth and no semantic authority; and nothing a caller supplies after the freeze enters it.

**Source record.** W is computed from the Candidate record in its canonical form, never from an in-memory mapping that merely digests to the same `candidate_hash`:

- before the snapshot is written (the freeze, §7.6): `serialize.canonical_data` of the Candidate record — the record whose canonical text becomes the snapshot's `material`. W reads no part of `canonical_first_work`, which the writer does not take (below). At the freeze, W is therefore computed from the record before the R9 selection is added to it, since §7.7 evaluates the selection on the effects W gives; adding the selection changes no W;
- afterwards (the actual registration, the pre-Kp proof, C-2(Kp), recovery, the committed planning proof, a fresh clone): the snapshot's `material` as the P1 strict reader returns it — `ReviewStore.read_candidate_snapshot` in the working tree, `serialize.parse_canonical` over the committed blob (§18.8).

The two are the same data in the same key order: `parse_canonical` accepts only the canonical rendering of the record it returns (`review/serialize.py:135-173`; **Measured**, §31). So the hand-off before the write and after the read is the same W.

**Mappings.** Every mapping inside a Candidate field that reaches Project bytes — today the Related `condition` (§7.3), at every depth — enters W in the Candidate's representation: the P1 serializer's key order (ascending code point at every depth, `serialize.canonical_data`, `review/serialize.py:47-73`), with every entry the Candidate holds. No entry is dropped, added or renamed: the live `validate_condition` (`validate.py:48-61`) checks `kind` and `pattern` and accepts further keys, nested mappings included (**Measured**, §31), and W keeps them. No other key-order rule exists, and nothing is sorted inside the writer: `Relation.to_record`, `yamlish.dump` and `render_relations` are unchanged and render a mapping in the order they receive it (`store.py:151-154`, `yamlish.py:84-145`) — on the review-v1 path, the Candidate's.

**Sequences** keep the order the Candidate states: Phases, Works, Related entries, `planned_next` and `requires_completion`, relation records, reservation lists and the registration stages (§7.2, §7.3). Only mapping key order is normalized, as in the P1 serializer.

**Contents.** The values the writer helpers take, stage by stage:

```text
RoadmapPlan (§7.2)
  roadmap stage       the Roadmap file's id, name and sections in the writer's order: background, desired
                      state, then scope and out of scope where the Candidate's value is not null
  phases stage        the Roadmap ID; the Phase specs {key: PhaseSpec(name, desired_state)} in Candidate
                      order; PhaseRelationSpec(type, from, to) for the Candidate's relations in order
  reservations        roadmap, phases:phase:<key>, phases:rel:<i> -> the Candidate's IDs

PhaseEntryDesign (§7.3)
  works stage         {key: WorkSpec(name, desired_state, phase_id, roadmap_id, related=(RelatedSpec(type,
                      to, condition), ...))} for the normal Works in Candidate order; RelationSpec(type, from,
                      to) for the Candidate's works:rel relations in order (planned_next, then
                      requires_completion)
  integration stage   {"integration": WorkSpec(..., work_kind=phase_integration_check, related=...)};
                      requires_completion <normal Work ID> -> integration, normal Works in Candidate order
  confirmation stage  only with a Candidate confirmation: {"confirmation": WorkSpec(...,
                      work_kind=human_confirmation, confirmation_target=<the integration ID>, related=...)};
                      requires_completion <the integration ID> -> confirmation
  reservations        works:work:<key>, works:related:<key>:<i>, works:rel:<i>, integration:*,
                      confirmation:* -> the Candidate's IDs
```

In the relations the Candidate declares (RoadmapPlan `relations`, PhaseEntryDesign `works:rel`), an endpoint that is one of the Candidate's own reserved IDs is handed over as its key, as a caller writes it, and any other endpoint as the existing ID it is; the generated integration and confirmation relations take the form `_expand_phase` gives them (a Work ID, then the stage key). Each `condition` is the Candidate's mapping, or `None`. `entry` is not in W: the writer does not persist it, and the Candidate's `canonical_first_work` stands for its meaning (§7.7, Frozen P1 R9 §4).

**One derivation, no second semantics.** These stage inputs are what `_create_roadmap` (`roadmap.py:472-504`) and `_expand_phase` (`roadmap.py:949-1037`) derive from a plan or design: the specs, the generated integration and confirmation relations, the confirmation target, the stage order. That derivation is extracted from them as a pure function with no behaviour change: the legacy path calls it with the caller's plan or design, and W calls it with the plan or design value rebuilt from the Candidate, every field of which is the Candidate's, in Candidate order, with no `entry`. W renders nothing; every byte still comes from the unchanged builders it feeds (§15.7 step 2). A registration stage already recorded is carried forward from its record, as today (Frozen P1 R8 §9); W feeds every stage not yet recorded, and the record check proves the recorded ones equal E (§15.6 item 6).

**One hand-off, every user.** One function computes W from one record, and every consumer takes it: the representability check (§7.6), the actual review-v1 registration (§15.1 step 1), the expected physical projection (§15.7), the pre-Kp record check and C-2(Kp) (§15.6 item 6, §15.3 P3–P4), recovery after runtime loss (§12.4) and the committed planning proof in any clone (§18.8 CP5). For one Candidate, the W of an uninterrupted run, of a runtime-recovered run and of a fresh clone is the same; a mutation ID, a reviewer's or provider's state and a caller's mapping insertion order have no effect on it.

**Request identity is another question.** `operation_identity` (§6.2) answers whether an invocation is the same requested plan or design, and it compares canonically: `serialize.digest` sorts keys, and the Mutation Controller normalizes and compares invocations with `json.dumps(..., sort_keys=True)` (`mutation.py:702`, `mutation.py:1668`). W answers which exact values the writer receives. Two designs that differ only in the insertion order of a condition's keys are the same request, the same Candidate and `candidate_hash`, the same W, the same E and the same Kp bytes (**Measured**, §31).

The canonical key order is a representation, not reviewed meaning (§7.5): the reviewed condition is the mapping value. Once the Candidate is frozen, that representation decides which bytes the writer produces, as display numbers and layout do, and E proves them (§15.7).

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
| checkout semantics of Review paths (attributes, line endings) | `checkout_capability`: the capability contract of §14.5 (Frozen P1 R6 §6 / R11 §10 name attributes and line-ending conversion as bound Git semantics), whose one supported configuration is the canonical Review-attribute rule, proven from HEAD's raw committed `.gitattributes` (P2-READY-004) |
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
  set_aside_runs:                 # §12.8; [] when discovery set nothing aside
    - {review_run_id, reason}      # every matching Run discovery set aside, sorted by review_run_id
request_digest = serialize.digest(request_envelope)
```

`reason` is one of `invalidated`, `consumed`, `not_authorized`, `set_aside`, `review_context_changed`, `review_policy_changed`, `review_declared_base_changed` (§12.2). A recovered Run keeps its own envelope, byte for byte.

The TaskInput (P1 schema) at `.workline/review/task-inputs/<task_id>.yaml`: `task_id`, `task_slot`, `task_kind: planning-review-v1`, `reviewer_identity`, `reviewer_version`, `request_envelope`, `request_digest`, `candidate_hash`, `reconstruction_mode: snapshot`, `candidate_material_digest`, `review_context_hash`, `effective_policy_hash`, `accepted_generation: 1`. `task_input_digest` = SHA-256 of its canonical bytes. The accepted descriptor in generation 1 carries every P1 `ACCEPTED_TASK_FIELDS` value from the same sources.

### 10.3 Launch

**Frozen.** The reviewer is called only when all hold, checked right before the call:

- the Run's latest generation is generation 1 (`status: open`), and the task is accepted there and unsettled;
- `gate.require_persisted` passes for the snapshot, the task input and generation 1, and each of their HEAD blobs holds exactly the canonical bytes with mode `100644` (§15.2 blob check);
- `ReviewStore.provenance_problems(descriptor, 1) == []`;
- the task input's `request_digest` is `serialize.digest` of its `request_envelope`; the envelope's `candidate` equals the snapshot's `material`, whose digest is the Run's `candidate_hash`; the envelope's `context` digests to the Run's `review_context_hash`;
- the operation binding holds (§11.5); Candidate, Context and Policy are current (§13);
- the `review` argument's `reviewer_identity` and `reviewer_version` equal the accepted descriptor's, else `StopError` code `review_reviewer_mismatch` and no call.

A failed check stops with no call and the planning mutation pending (P2-READY-005):
- the first → `ReconcileRequired` (reason `review_chain_invalid`);
- the second → the P1 `review_not_persisted` STOP;
- the third or fourth → `ReconcileRequired` (reason `review_task_invalid`);
- the fifth → `ReconcileRequired` (reason `review_binding_moved`), or by currency: stale before a Receipt (§13.2), or a Candidate mismatch (`review_candidate_mismatch`, §13 item 4);
- the last → `review_reviewer_mismatch`.

The task object is rebuilt from the stored TaskInput, never from memory. So the external launch happens only after Candidate, TaskInput and the accepted generation are persisted in local Git (Frozen P1 R3 §3, §10). The same rules hold when a recovery planning mutation launches the task after runtime loss (§12.7): the callback then receives exactly the original `task_id`, `task_slot`, `task_kind`, `review_kind`, request envelope, `request_digest`, `candidate_hash`, `review_context_hash` and `effective_policy_hash`, and runs only for the accepted `reviewer_identity` and `reviewer_version`. No provider job handle is needed: the reviewer is synchronous.

### 10.4 Return validation, failures, retry

**Frozen.**

| event | outcome |
| --- | --- |
| the callback raises | `StopError` code `review_reviewer_failed` (original chained); nothing settled; the planning mutation stays pending |
| the return is not exactly a `PlanningReviewReport`, `task_id` differs, `status` outside `completed` / `declined`, or a finding is not exactly a `PlanningReviewFinding` with a valid severity and code | `StopError` code `review_report_invalid`; nothing settled |
| identity or version differ from the accepted descriptor | `StopError` code `review_reviewer_mismatch`; nothing settled |
| valid report | settled through generation 2 (§10.5) |
| next run while generation 1 is still the latest | the same `task_id` is launched again from the stored TaskInput — by the resumed planning mutation, or after runtime loss by a recovery planning mutation (§12.7); no new task ID is ever reserved for it (Frozen P1 R2 §5, R3 §4) |
| duplicate: generation 2 already settles the task with the same `result_digest` | `gate.validate_settlement` returns the descriptor; idempotent (P1 behaviour; the P2 launch rule of §10.3 never launches a settled task, so the flow itself cannot produce one) |
| conflict: a different `result_digest` for a settled task | `review_callback_conflict` (P1 `ValidationError`); nothing settled; the planning mutation pending |
| unknown: a task the Run never accepted, or another reviewer | `review_callback_unknown` (P1 `ValidationError`); nothing settled; the planning mutation pending |

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

It binds the parent (`planning_mutation_id`), the Run, the exact generation and transition, the Candidate / Context / Policy identities and, for an invalidation, the Receipt it supersedes and why (Frozen P1 R3 §9). A resumed generation mutation is re-entered through `MutationController.open` with its recorded owner, invocation and scope (reconnaissance probe 8), so its invocation never has to be recomputed. For a recovery planning mutation (§12.4), `planning_mutation_id` is that recovery planning mutation's own ID, and every other value is the canonical Run's: Frozen P1 R3 §9 lists what the owning mutation binds, not that every generation of a Run is written by one mutation, and gate records carry no mutation ID.

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

**Frozen.** At the end of the freeze the planning mutation records the note `review_binding = {branch: <full ref of HEAD's branch>, head: <HEAD commit>}`. "The binding holds" means: HEAD is on exactly that branch (full ref) and HEAD's history holds `head` (`gitcmd.descends_from`). It is checked before each generation mutation starts, before each reviewer launch, at the use check, and before the planning mutation records each of its post-Review stages (registration, Kp, Consumption, Km, publication). Not holding → `ReconcileRequired` (reason `review_binding_moved`), nothing replayed, recorded, committed or pushed; returning to the branch continues. Inside each mutation the live rules apply unchanged: a generation mutation's `create_file` stage carries `decided_on`, and its commit names that branch (`_bind_decision`).

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
G1 accept                                            unsealed: stale before a Receipt, or continued by recovery (§12)
G1 accept -> G2 settle                               unsealed: not authorized, stale before a Receipt, or continued by recovery
G1 accept -> G2 settle -> G3 seal                    sealed: the Receipt is used by the registration, or by recovery's use check
G1 accept -> G2 settle -> G3 seal -> G4 invalidate   unsealed again: the Receipt superseded; terminal
```

Generation 3 is the only seal, and generation 4 is the last generation a P2 Run ever has: no P2 path writes generation 5, seals again, or starts generation 4 once a registration stage is recorded (§11.10, §13.4). A transition started in any other state, a generation whose number the helper computes differently from this table, or a chain of any other shape is `ReconcileRequired` (reason `review_chain_invalid`).

Before recording the stage: `gate.require_committable` and the Git persistence preflight (§14.3, the checkout capability of §14.5 included) on its paths. Then `apply()`, then Git stage `review-generation-commit`: exactly one `git_commit` of the stage's paths with the planning commit primitive (§15.2), message `chore(workline): record review generation <N> of <run_id>`, commit-only, never a push. Then `gate.require_persisted(paths)` and the blob check (HEAD blob == canonical bytes, mode `100644`); a failure is the P1 `review_not_persisted` STOP, as at the use check (§17 item 6), with the generation mutation pending. Only then `complete()`. Generation commits stay local until a push from that branch carries them as history (they add no registration, so the publication barrier never concerns them, §18.7); the reviewer launch needs only the local Git boundary (Frozen P1 R3 §10: remote-less Projects remain valid).

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
1. §5.6 steps 1-6: the argument, platform and Git version checks; the live checks up to the request identity;
   the canonical-input preflight; the same-request and marker checks (§5.3); the remaining live acceptance
   checks, under the live interrupted-entry rule
2. a pending review-v1 planning mutation for the slot -> resumed by its exact recorded invocation (live `_open`),
   with or without recovery_of_review_run_id; while it has recorded no effect and started no generation
   mutation, it completes its setup by the pre-freeze resume setup (§12.9); none -> canonical recovery
   discovery (§12.2), before anything is begun:
     exactly one recoverable Run              -> a recovery planning mutation is begun; it binds its recovered
                                                 reservations before anything else (§12.4, §12.5)
     no recoverable Run, nothing incomplete   -> a planning mutation for a new Run is begun (§12.8)
     several recoverable, or any incomplete   -> ReconcileRequired (review_recovery_ambiguous,
                                                 review_recovery_incomplete), nothing begun
3. when the planning mutation has reserved or recovered a Run:
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
                                                                            ReconcileRequired, reason
                                                                            review_chain_invalid); then apply, Git
                                                                            stage, persistence proof, complete()
     exactly one bound to anything else            -> ReconcileRequired (review_generation_owner_conflict: a
                                                      conflicting owner)
     more than one                                 -> ReconcileRequired (review_generation_owner_conflict: the
                                                      condition the helper reports as review_generation_conflict)
4. the validated chain decides what the planning mutation does next:
     no chain                              -> the freeze (§14.4), then generation mutation 1 (a new Run only)
     latest 1                              -> the reviewer launch (§10.3; stale -> terminal, §13.2), then
                                              generation mutation 2 with a valid report
     latest 2                              -> not authorized -> terminal (§19.1); else currency: stale -> terminal
                                              (§13.2), current -> generation mutation 3
     latest 3, no registration stage       -> the use check (§17); stale -> generation mutation 4 (§13.3)
     latest 3, a registration stage        -> the registration flow from its record (§15.1)
     latest 4                              -> terminal stale (§13.3), nothing evaluated again; with a registration
                                              stage recorded -> ReconcileRequired (review_chain_invalid)
5. only for the generation mutation step 4 names does gate.next_generation_scope compute N+1
```

The planning mutation is resumed first, its pending generation mutation second, and no generation is computed before that one is resolved (Frozen P1 R3 §2).

### 11.9 Conflicts and crashed predecessors

- A second owner holding the Run's token is refused (step 3).
- A crashed predecessor is the pending generation mutation found through the token.
- A crash with no recorded effect leaves nothing physical: effects are durable before they are applied, so abandoning it and computing N again cannot fork the Run.
- A physical create before the `applied` flag was saved is resumed, classified `applied_matching` and completed before N+1 is computed; the token makes a hypothetical N+2 overlap it (Frozen P1 R12 §3).

### 11.10 Generation mutations and the registration never coexist

The planning mutation records no effect before the use check, and generation mutations — generation mutation 4 included — exist only before its first registration stage is recorded. Once a registration stage is recorded, a pending generation mutation of its Run is a conflict (`ReconcileRequired`, reason `review_generation_owner_conflict`), and generation mutation 4 is never started (§13.4).

### 11.11 The planning mutation disappears

**Frozen.** Runtime loss or a fresh clone after generations were committed:

- The committed Review records stay, and they — not the lost runtime — are the truth about the Run. A same-request invocation finds the Run by canonical recovery discovery (§12.2) and, when it is recoverable, continues it (§12.4): the same Run ID, the same task ID, the same Candidate and reserved IDs.
- A Run that is terminal (generation 4; consumed; a generation 2 that does not authorize) or set aside is never continued; it stays in history, and `validate_review` validates it.
- A Run whose runtime was lost with a generation stage partially applied, or applied and never committed, holds a stage no process can finish without guessing the lost intent; `validate_review` reports a half-written stage as Frozen P1 R3 requires. P2 never repairs it and never hides it behind a new Run: a matching invocation stops with `ReconcileRequired` (§12.3), and a non-matching one is not refused because of it (§14.6).
- A sealed Receipt whose planning mutation was lost is used only by the recovery of its own Run: the recovered use check (§17) registers under it or invalidates it with generation 4 (§13.3). No other Run ever uses it.
- A pending generation mutation whose planning mutation's record is gone (a partial runtime loss) is never adopted: discovery refuses its Run (§12.3), and a person reconciles.
- A registration commit the lost planning mutation left without a Consumption that the committed planning proof proves is never recovered and never bypassed: a matching invocation stops with `ReconcileRequired` (§12.7), and the publication barrier keeps every history holding it unpublished until a person reconciles (§18.7, §21.2).

### 11.12 The `rules/git` one-stable-mutation assumption

**Frozen.** `rules/git` Operation Owner says an operation resumes the one pending mutation that corresponds to the invocation and stops on several. The review-v1 planning operation owns one planning mutation and the generation mutations it starts. At the entry, the planning mutation is the one corresponding mutation. A pending generation mutation bound to it by `planning_mutation_id` and the Run's token is its subordinate and is resolved in the order of §11.8. A recovery planning mutation is likewise the one corresponding mutation of its own invocation (§12.4). Anything else remains "複数件 / 競合" and is `reconcile required`. The authority text is amended when the implementation lands (§26.1). Until then no review-v1 planning exists and the live rule is unchanged.

## 12. Planning mutation lifecycle

**Frozen.**

| state | condition | behaviour |
| --- | --- | --- |
| may be abandoned | no effect recorded and no generation mutation started, whether this run began it or resumed it, a Phase entry included (P2-READY-002). "Started" is decided per kind. A new Run: a gate chain exists for its Run, or a pending generation mutation is bound to it. A recovery planning mutation: a pending generation mutation is bound to it, or its Run's chain has a generation after the one recorded with its binding (§12.5) | a STOP of any class abandons it (live `abandon_on_stop`): every pre-Review refusal (§7.4, §7.6, §7.7, §14), every refusal of the pre-freeze resume setup (§12.9), a Context that cannot be computed, a reservation or note failure. The live rule that a resumed Phase entry is never abandoned (`skills/roadmap` Phase entry, `roadmap.py:823-828`) keeps an expansion whose reserved IDs and recorded effects abandoning would strand. A review-v1 planning mutation in this state has recorded no effect, and its reservations and notes were never canonical, so review-v1 abandons it; legacy Phase entry keeps the live rule |
| must remain pending | from the start of generation mutation 1 — for a recovery planning mutation, from the start of its first generation mutation — until a terminal outcome | any STOP (reviewer failure, invalid report, binding moved, proof failure, reconcile) leaves it pending; the next invocation with the same request resumes it |
| completed without registration | `not_authorized` (§19.1); `stale` before a Receipt exists (§13.2); `stale` after the Receipt, only once generation 4 and the Supersession are committed and proven persisted (§13.3) | `complete()` with no effect recorded; `ReviewedPlanningResult` returned |
| completed with registration | publication done (remote-less: C-2(Km) passed, §18.2) and the live structure postcheck passed | `complete()`; `ReviewedPlanningResult(status registered)` |
| never ends `stale` | from the moment its first registration stage is recorded | a currency difference is `ReconcileRequired` (§13.4); the registration is never undone |
| replaced by a new Run | never while pending, and never because the runtime is gone | a different request or design for the slot → `reconcile_required` (live); a new Run is begun only when canonical recovery discovery finds no recoverable and no incomplete matching Run (§12.8); a lost planning mutation's Run is otherwise continued (§12.1) |

The way out of an operational failure is to run the same request again with a working reviewer, or to have the reviewer return `declined`, which settles the task `failed` and ends the attempt as `not_authorized` (§19.1). A pending review-v1 planning mutation therefore never needs a human to stop blocking the Project, except where a reconcile rule of `rules/git` applies (history rewritten, foreign change, proof failure) or a registration commit that can no longer be proven holds the publication barrier (§18.7). After runtime loss the same request continues the same Run (§12.1–§12.7).

### 12.1 Runtime loss is continued, not replaced

**Frozen.** The runtime planning mutation is not clone-safe; the Review Run it started is. Runtime loss — a fresh clone, or `.workline/runtime/**` removed — takes the planning mutation's record, its reservations and notes, the runtime report copies and every pending generation mutation. It never takes the committed Run records. Frozen P1 R2 §5, R3 §4 and R12 §4 require that the same logical accepted task then continues under its own `task_id` after exact reconstruction, and that no replacement task ID is allocated for it. So a review-v1 invocation whose slot has no pending review-v1 planning mutation first runs canonical recovery discovery (§12.2) and continues the one recoverable Run (§12.4); only when there is none does it start a new Run (§12.8). Round 1's rule "runtime loss requires a fresh Candidate and a new Run" is withdrawn. Nothing the writer needs is lost with the runtime: W comes from the committed snapshot (§7.8).

Normal retry stays separate: while the planning mutation's record exists, the same request resumes it by its exact invocation (§5.3, §11.8), and discovery does not run at the entry. A resumed mutation that has not recorded its discovery outcome or its recovered binding runs discovery again only inside its pre-freeze resume setup, and only before its first generation mutation (§12.9).

"The same logical invocation" is exact: the same planning kind and the same `operation_identity` — `<operation>:<request_digest>` (§6.2), which binds the exact request or design semantics. Nothing else identifies it: not a name, a display number, a timestamp, a branch, an enumeration order or a Run ID's position among others.

### 12.2 Canonical recovery discovery

**Frozen.** Run under the lock at §5.6 step 7, only when the slot has no pending review-v1 planning mutation, and before any planning mutation is begun or any ID reserved. It runs after the live entry checks, the canonical-input preflight, §5.3 and the remaining live acceptance checks, so only for an admissible operation (P2-READY-003). The pre-freeze resume setup runs the same steps for a pending planning mutation that has not recorded their outcome (§12.9), and there too it begins nothing. It reads HEAD's committed objects and the working tree through the P1 reader; no runtime record takes part.

1. **Readability.** §14.6 over the working tree; a failure → `review_namespace_unreadable`, nothing begun.
2. **Matching Runs.** Every Run whose generation 1 — added anywhere in HEAD's history (read as in §18.7: `git log --full-history --no-renames --diff-merges=combined --diff-filter=A --name-only -z HEAD -- .workline/review/gates/`, each generation-1 blob parsed by the P1 reader) or present in the working tree (`ReviewStore.run_ids()`, `read_gate(run, 1)`) — carries this invocation's `review_kind` and `operation_identity`. No other Run is read further.
3. **Clean persistence** of each matching Run (§12.3). A matching Run that is not cleanly persisted → `ReconcileRequired` (reason `review_recovery_incomplete`), nothing begun.
4. **Classification** of each matching Run, in this order, the first applicable row deciding:

| row | canonical state at HEAD | class |
| --- | --- | --- |
| a | latest generation 4, with its Supersession | terminal `invalidated` |
| b | a registration commit or a Consumption exists: a registration path of the Run (from its snapshot, §18.7 step 2) is added in HEAD's history or present in HEAD's tree, or a Consumption naming its Receipt is present in HEAD's tree or was added in HEAD's history | the committed planning proof (§18.8) proves the Run for HEAD → terminal `consumed`; otherwise → `ReconcileRequired` (reason `review_recovery_incomplete`), nothing begun |
| c | latest generation 2, not authorizing (§10.6: some required task settled `failed`, or `obligation_digest` is not the digest of the empty obligations record) | terminal `not_authorized` |
| d | named in the `set_aside_runs` of another matching Run's committed request envelope | `set_aside` |
| e | reconstruction (§12.3) fails | `ReconcileRequired` (reason `review_recovery_incomplete`), nothing begun |
| f | latest generation 1, or latest generation 2 authorizing | currency (§13) on HEAD, in its order: the Context, the Policy, the declared base on HEAD's committed view compared with the snapshot's, then — only with the declared base equal — the Candidate rebuilt from this invocation, the snapshot's reserved IDs, that declared base and the R9 selection on HEAD's committed basis (§7.7): current → **recoverable**; stale → obsolete, reason = the §13 reason code; any other difference (§13 item 4) → `ReconcileRequired` (reason `review_recovery_incomplete`), nothing begun |
| g | latest generation 3 (sealed, not in row b) | **recoverable**; its currency is decided by the recovered use check (§17), which invalidates it when stale (§13.3) |

An unavailable Context in row f is the `review_context_unavailable` STOP (§8), never a stale reason.

5. **Outcome.**
   - exactly one recoverable Run → a recovery planning mutation for it (§12.4);
   - no recoverable Run → a new Run (§12.8), whose request envelope records every matching Run set aside by rows a, b (`consumed`), c, d and f (obsolete), with its class as reason;
   - more than one recoverable Run → `ReconcileRequired` (reason `review_recovery_ambiguous`), nothing begun; no Run is chosen by age, ID order or position.

Terminal and set-aside Runs are excluded by their own canonical state, so an operation that completed normally and one whose runtime was lost leave the same canonical answer. A matching Run that cannot be shown whole (§12.3), or that holds a registration commit the committed planning proof does not prove, is never excluded quietly and never replaced: the call stops.

### 12.3 Clean persistence and reconstruction

**Frozen.** *Clean persistence* of a matching Run — all of:

- every Review record of the Run that HEAD's history ever added (its gates, candidate snapshot, task input, Receipt, Supersession, and any Consumption naming its Receipt) is present in HEAD's tree with the same blob: nothing committed was deleted or rewritten;
- every such record `ReviewStore` reads in the working tree is committed at HEAD and unchanged (`gate.require_persisted` and the blob check, §15.2): no record of the Run exists only in the working tree;
- every stage is whole: generation 1 with its snapshot and task input; a sealed generation with its Receipt; generation 4 with its Supersession;
- the chain validates under the P1 reader and has one of the four shapes of §11.6;
- no pending mutation holds the Run's serialization token (`gate.pending_generation_mutations`): a generation mutation whose planning mutation's record is gone is never adopted.

A half-written stage (a gate without its task input, a seal without its Receipt, generation 4 without its Supersession), or a stage applied and never committed, fails clean persistence: no process can finish it without guessing the lost effect intent, and a new Run never hides it.

*Reconstruction* (Frozen P1 R2 §5, R3 §4–§5) of a matching Run that rows a–d do not classify:

- `ReviewStore.provenance_problems(descriptor, 1) == []` for the task generation 1 accepted;
- the task input's `request_digest` is the digest of its `request_envelope`; the envelope's `candidate` equals the snapshot's `material`, whose digest is `candidate_hash`; the envelope's `context` digests to the Run's `review_context_hash`, and its `policy_id` names the static policy (§9) whose digest is the Run's `effective_policy_hash`;
- the Run's `target_identity` is the Candidate's target (its reserved Roadmap ID, or its `phase_id`), and its `review_kind` the Candidate's;
- the running implementation provides the adapter the Context names (`adapter_identity`).

A failure is row e: missing or mismatching accepted material is never answered with a new Run or a new task ID (Frozen P1 R3 §4, R12 §4). The reviewer's identity and version are checked where the task is launched again (§10.3), because only a generation-1 recovery calls the reviewer.

### 12.4 The recovery planning mutation

**Frozen.**

- **Invocation.** The review-v1 invocation of §5.2 plus exactly one key: `"recovery_of_review_run_id": <the recovered Run ID>`. It is begun through the live `_open` with that invocation, after the canonical-input preflight passed on the recovering caller's request identity (§5.6), so it has its own new mutation ID; it never takes the lost mutation's ID and never claims that mutation's records. §5.3 accepts it; §18.5 treats it as a planning mutation.
- **Binding.** Right after `_open` returns — `_open` records only the live pre-existing-dirty snapshot note — and before any reservation, any other note and any effect, §12.2 steps 3–4 are evaluated again for its Run under the lock. The Run must still be the one recoverable Run; otherwise `ReconcileRequired` (reason `review_discovery_changed`), and the mutation is abandoned. The recovered reservations are then bound (§12.5), in one durable save with the note `recovery_binding`. On a resume:
  - a recovery planning mutation without a recorded binding binds now, by the pre-freeze resume setup (§12.9);
  - one with a recorded binding checks again that its bound reservations are exactly the canonical ones — otherwise `ReconcileRequired` (reason `review_recovery_reservation_conflict`).
- **Remaining setup.** The reservations the Run still needs (§12.6), with the entity scope extended by the bound domain IDs and the file scope by the Consumption path, as §14.4 steps 1 and 4 extend them; then §14.4 steps 5–6: `gate.require_committable`, the Git persistence preflight with the checkout capability, dirty overlap on the registration paths + Run record paths + Consumption path, the publication barrier on HEAD with a push destination, and the note `review_binding` = the current branch and HEAD, which holds every committed record of the Run (§12.3). The Candidate, Context and Policy are never rebuilt for storage: the Run's committed records are them.
- **Continuation.** By the Run's chain (§11.8 step 4): latest 1 → the reviewer launch of the same task (§10.3), then generation mutation 2; latest 2 → currency, then generation mutation 3; latest 3 → the use check (§17), then the registration, or the invalidation when stale (§13.3). The registration writes from W computed from the Run's committed Candidate snapshot (§7.8) — the W an uninterrupted run would have used; the recovering invocation's caller objects serve only its entry checks and its identity.
- **Generation mutations** it starts bind `planning_mutation_id` = the recovery planning mutation, with the Run's own `review_run_id`, `candidate_hash`, `review_context_hash`, `effective_policy_hash`, obligation digest and Receipt ID (§11.2). Frozen P1 R3 §9 lists what the owning mutation binds; it does not require every generation of a Run to be written by one mutation, and gate records carry no mutation ID. Generation numbering continues from the validated chain (`gate.next_generation_scope`, unchanged).
- **Lifecycle.** A recovery planning mutation is abandoned on a STOP while it has recorded no effect and started no generation mutation, whether this run began it or resumed it (§12 table; live `abandon_on_stop`); nothing canonical changes, and the next same-request invocation discovers again. From its first generation mutation on it remains pending until a terminal outcome (§12 table), and it is resumed like any planning mutation, by its exact recorded invocation.
- **Never.** It never adopts Kp, Km or any registration commit; it never continues a Run that §12.2 classifies terminal, set aside or incomplete; it never allocates a replacement Run, task, Candidate or domain ID.

### 12.5 Recovered reservations

**Frozen.** A private, recovery-only helper of the Mutation Controller — a module-level function of `mutation.py`, not a `Mutation` method (§25) — records reservations that already exist canonically. It never generates an ID. Its invariants:

- it is called only by the review-v1 recovery path, and only on a pending recovery planning mutation whose invocation names the Run, which:
  - has recorded no reservation, no effect and no `recovery_binding` note, and has started no generation mutation — whether this process began it or resumed it (§12.9);
  - and only after canonical recovery discovery (§12.2 steps 1–5), run in this process under the lock, found that Run to be the one recoverable Run for the invocation (P2-READY-002);
- the key → ID map is taken exactly from the Run's committed Candidate snapshot, under the keys the unchanged registration code reserves (§7.2 / §7.3): RoadmapPlan `roadmap`, `phases:phase:<key>`, `phases:rel:<index>`; PhaseEntryDesign `works:work:<key>`, `works:related:<key>:<i>`, `works:rel:<i>`, `integration:work:integration`, `integration:related:integration:<i>`, `integration:rel:<i>`, `confirmation:work:confirmation`, `confirmation:related:confirmation:<i>`, `confirmation:rel:0` (a Phase entry Work carries no `derivation_detail`, so no `:der:` key exists, `create.py:258-259`); plus the Run key → the Run ID, the task key → the accepted `task_id`, and, when generation 3 exists, the Receipt key → the Receipt's ID;
- it refuses — `ReconcileRequired`, reason `review_recovery_reservation_conflict`, nothing recorded — a key already reserved with another ID, an ID whose kind is not its key's kind, and a domain ID that already names an entity or a relation in HEAD's committed view or in the working tree;
- every binding is recorded in one durable save, before any effect, together with the note `recovery_binding = {review_run_id, latest_generation}`: the Run, and its latest generation at binding, from which the mutation tells whether it has started a generation mutation (§12 table). Afterwards the unchanged registration code's `reserve_id` calls return exactly these IDs (`mutation.py:391-395`: a key already reserved returns its recorded ID);
- the map is proven to be the reviewed one — at discovery for generations 1 and 2, at the use check for generation 3. With the declared base equal (§13 item 3), the Candidate rebuilt from the invocation, these IDs, that declared base and the R9 selection on the committed basis equals the snapshot's `material` (§13 item 4). A difference with the declared base equal is `ReconcileRequired`: `review_recovery_incomplete` at discovery, `review_candidate_mismatch` at the use check.

No public API accepts caller-supplied IDs: the helper takes its IDs only from the committed Candidate snapshot and the Run's committed records.

### 12.6 Review IDs after runtime loss

**Frozen.**

| ID | canonical before runtime loss? | in the recovery planning mutation |
| --- | --- | --- |
| Run ID | yes (gate records) | bound (§12.5); never replaced |
| task ID | yes (accepted descriptor, task input) | bound; the same task is launched again; never replaced |
| Candidate snapshot, task input | yes | read as committed; never rewritten |
| domain IDs | yes (the Candidate snapshot) | bound; never replaced |
| Receipt ID | only once generation 3 exists | generation 3 exists → bound; otherwise reserved anew under `review-receipt:<run_id>:3` |
| Consumption ID | never, for a recoverable Run (a Consumption puts the Run in row b of §12.2) | reserved anew under `review-consumption:<receipt_id>` |

Frozen P1 R2 §2 keeps the keys deterministic. A reservation value that never became canonical — the lost runtime's Receipt ID before generation 3, or its Consumption ID — authorized nothing and named nothing any reader can see, so reserving it anew under the same key substitutes nothing canonical. R2 §5 and R3 §4 forbid replacing accepted task identity, and no canonical ID is ever reserved anew.

### 12.7 Continuation per Run state

**Frozen.** After runtime loss, or in a fresh clone, a same-request review-v1 invocation does exactly this:

| committed state of the matching Run | outcome |
| --- | --- |
| no matching Run (the runtime was lost before generation 1 was committed) | a new Run (§12.8) |
| generation 1, current | recovered: the same Run and task; the task is launched again from the stored TaskInput for the accepted reviewer identity and version (§10.3, else `review_reviewer_mismatch`); a valid report is settled as generation 2 by a generation mutation of the recovery planning mutation |
| generation 1, stale | set aside (obsolete); a new Run |
| generation 2 authorizing, current | recovered: no reviewer call; currency, then generation 3 with a newly reserved Receipt ID |
| generation 2 authorizing, stale | set aside (obsolete); a new Run |
| generation 2 not authorizing | terminal: set aside; a new Run — P2 does not remember a refusal (§19.1), a completed and an interrupted not-authorized ending leave the same canonical state, and the settled task is never launched again |
| generation 3, sealed, no registration commit | recovered: the same Run and Receipt, into the use check (§17): current → the registration under that Receipt; stale → generation 4 and the Supersession, then `stale` (§13.3) |
| generation 4 | terminal: set aside; a new Run |
| a registration commit whose Consumption the committed planning proof proves | terminal `consumed`: set aside; what the new invocation means is the live Roadmap rule (Roadmap creation: a second Roadmap; Phase entry: `phase_already_expanded` before discovery) |
| a registration commit without such a Consumption (Kp only; Consumption only in the working tree; Km whose committed planning proof fails) | Roadmap creation: `ReconcileRequired` (`review_recovery_incomplete`, §12.2 row b); Phase entry: the live `phase_already_expanded` before discovery, because the registration's Works are in the Phase (§5.6 step 6); never recovered, never a new Run; the publication barrier holds (§18.7) |
| a half-written, uncommitted or rewritten stage, or a generation mutation left pending by a lost planning mutation | `ReconcileRequired` (`review_recovery_incomplete`) for an admissible operation (§5.6 step 6); never a new Run |
| registration files present only in the working tree (applied by the lost mutation; no registration commit) | generation 3 is recovered only once a person has discarded those files. Until then the call stops with nothing written: Roadmap creation when the recovered-reservation binding refuses the IDs those files already use (`review_recovery_reservation_conflict`, §12.5), Phase entry at the live `phase_already_expanded` precheck before discovery. Then the use check continues |

The table describes one matching Run; with several, §12.2 step 5 decides. "Current" and "stale" are the currency of §13 evaluated on HEAD. An obsolete Run's accepted task is not replaced by the new Run's task: its Candidate is no longer the one the current request means — the authorized base, Context or Policy changed — so the current request is a different logical review. Frozen P1 R3 §4 governs reconstructing the same logical task; §13 governs whether a reconstructed Candidate may still proceed, and a stale one never proceeds (Round 1, P2-CONTRACT-002 and -003).

### 12.8 New-Run eligibility

**Frozen.** A planning mutation for a new Run — the freeze of §14.4, new reserved IDs, a fresh Candidate — is begun only when discovery found no recoverable Run and nothing incomplete. Runtime loss alone never makes a Run eligible for replacement.

Right after it is begun, that planning mutation records the note `recovery_discovery = {set_aside: [{review_run_id, reason}, ...]}` (sorted by Run ID; kept on resume, never recomputed once recorded; a resumed new-Run planning mutation that has not recorded it establishes it by the pre-freeze resume setup, §12.9), and the freeze writes that list into the new Run's request envelope as `set_aside_runs` (§10.2). Once generation 1 is committed the decision is canonical and permanent: row d of §12.2 excludes every Run named there, whatever its currency becomes afterwards. A new Run lost before its generation 1 was committed leaves nothing canonical, and the next invocation discovers again.

A new Run is eligible when no Run was ever canonically created for the invocation, or when every matching Run ended `not_authorized`, stale before its Receipt (obsolete), invalidated by generation 4, or consumed. It is never eligible merely because the runtime is gone while an accepted and current generation 1, a current authorizing generation 2 or a sealed generation 3 exists.

### 12.9 Pre-freeze resume setup

**Frozen** (P2-READY-002). `_open` makes a planning mutation durable before any review-v1 step runs: `MutationController.begin` saves it (`mutation.py:1693-1711`), and the live pre-existing-dirty note is a second save (`roadmap.py:260`, `gitops.py:63-74`). Each setup step that follows saves on its own: the `recovery_discovery` note (§12.8) or the recovered binding (§12.5), the reservations, and the freeze (§14.4). A crash between two of those saves leaves a pending review-v1 planning mutation whose setup is incomplete. Its next same-request invocation resumes that mutation (§5.3) and completes the setup on it. It never begins a second mutation because the setup is incomplete.

**Scope.** This section governs a resumed review-v1 planning mutation that has recorded no effect and started no generation mutation, as the §12 table defines both. Once it has started a generation mutation or recorded an effect, this section never applies again:
- its recorded setup is final;
- canonical recovery discovery is never run again for it;
- `recovery_discovery` and its recovered binding are never rewritten;
- §11.8 and §12 govern its resume.

**A new-Run planning mutation** (invocation without `recovery_of_review_run_id`):

1. Without a recorded `recovery_discovery` note, canonical recovery discovery (§12.2 steps 1–5) runs for this invocation exactly as for a fresh invocation, and begins nothing:
   - no recoverable Run and nothing incomplete → the note is recorded on this mutation from that outcome, and the setup goes on;
   - exactly one recoverable Run → `ReconcileRequired` (reason `review_discovery_changed`); the durable invocation names a new Run and is never rewritten into a recovery invocation;
   - several recoverable Runs, or any incomplete matching Run → `ReconcileRequired` with the discovery reason (`review_recovery_ambiguous`, `review_recovery_incomplete`).

   A recorded note is kept and never recomputed (§12.8).
2. The freeze (§14.4) then runs from its step 1, deterministically.
   - **Reservations.** The live `reserve_id` returns every reservation already recorded under its key unchanged (`mutation.py:388-401`), and reserves a missing one in the frozen order. A recorded ID of the wrong kind is the live `reserve_id` refusal (`ReconcileRequired`, reason `None`). A recorded key the frozen order does not reserve is `ReconcileRequired` (reason `review_setup_invalid`). No recorded value is ever replaced.
   - **Every other step** runs in full, as for a mutation this run began: the working-tree compatibility check and the Candidate on the committed basis (§7.4, §7.7), W, the representability check, the Context, the Policy, `gate.require_committable`, the Git persistence preflight with the checkout capability, the Review namespace readability, dirty overlap and, with a push destination, the publication barrier on HEAD.
   - **`review_binding`** is kept and checked when recorded (§11.5), and recorded when missing.

**A recovery planning mutation** (invocation with `recovery_of_review_run_id`):

1. Without a recorded binding (no `recovery_binding` note), the mutation must hold no reservation; a reservation without a binding is `ReconcileRequired` (reason `review_recovery_reservation_conflict`). Canonical recovery discovery (§12.2 steps 1–5) then runs for this invocation, and begins nothing:
   - exactly one recoverable Run, and it is the Run the invocation names → the recovered reservations are bound now, into this mutation (§12.5), in one durable save with the note `recovery_binding`;
   - the named Run is no longer the one recoverable Run (it is terminal, set aside or obsolete now, or another Run is recoverable, or none is) → `ReconcileRequired` (reason `review_discovery_changed`);
   - several recoverable Runs, or any incomplete matching Run → the discovery reason.
2. With a recorded binding, every bound key must hold exactly the ID the Run's committed records give (§12.5); otherwise `ReconcileRequired` (reason `review_recovery_reservation_conflict`).
3. The remaining setup of §12.4 then runs in full: the reservations that never became canonical (§12.6), `gate.require_committable`, the Git persistence preflight with the checkout capability, the Review namespace readability, dirty overlap, the publication barrier on HEAD with a push destination, and `review_binding`.

**A STOP anywhere in this section abandons the mutation** (§12 table). It has recorded no effect and holds nothing canonical. The next same-request invocation finds no pending planning mutation for the slot and runs canonical recovery discovery at §5.6 step 7. So after a `review_discovery_changed` refusal, that next invocation takes the recovery the discovery now gives, or a new Run.

Tests: §28 Q.

## 13. Currency, staleness and invalidation

**Frozen.** *Currency* is evaluated against one exact base commit B and means, in this order, the first difference deciding:

1. the Context recomputed now (§8) digests to the Run's `review_context_hash` — a difference is reason `review_context_changed`;
2. the Policy recomputed now (§9) digests to the Run's `effective_policy_hash` — a difference is reason `review_policy_changed`;
3. the declared base computed on the committed view of B (§7.4) equals the snapshot Candidate's `declared_base` — a difference is reason `review_declared_base_changed`, classified by the stale and base rules of §13.1–§13.4, and never also as an R9 or Candidate mismatch;
4. only when 1–3 are equal: the Candidate rebuilt from the planning invocation (`request` / `design`), the planning mutation's reserved IDs, that declared base and the R9 selection recomputed on the committed basis of B (§7.7: B's committed view with W's expected effects) digests to the Run's `candidate_hash` and equals the stored snapshot's `material`. Any difference — reserved IDs, the planning invocation or the R9 selection not reproducing the Candidate — is `ReconcileRequired`, never staleness. Its reason is `review_candidate_mismatch`, except at canonical recovery discovery (`review_recovery_incomplete`, §12.2 row f) and in C-2(Kp) (`review_persisted_proof_failed`, P12).

This order holds at every point that rebuilds a Candidate (P2-READY-001): recovery discovery, the reviewer launch, the starts of generation mutations 2 and 3, the use check, the pre-Kp currency proof, C-2(Kp) (P12 before P8 and P9, §15.3) and the committed planning proof (CP7 before CP6, §18.8). So one committed lifecycle change is classified once, as a declared-base difference, and never also as an R9 mismatch.

The declared base is read from the committed view of B, never from the working tree, so the currency that authorizes a registration is the currency of the exact commit the registration is committed on. `review_kind`, `operation_identity`, `target_identity` and `authorized_operation_stage` are compared wherever a Receipt exists (§17 item 4, §15.6, §15.3 P12). No P3 Review-validity fast path exists; P2 never re-reviews inside the same planning operation.

### 13.1 Where currency is evaluated

| point | base B | a stale difference (items 1–3) means | a Candidate mismatch (item 4) means |
| --- | --- | --- | --- |
| right before the reviewer launch (§10.3) | HEAD | stale before a Receipt (§13.2) | `ReconcileRequired` (`review_candidate_mismatch`), pending |
| right before generation mutation 2 or 3 starts | HEAD | stale before a Receipt (§13.2) | `ReconcileRequired` (`review_candidate_mismatch`), pending |
| canonical recovery discovery, for a matching Run at generation 1 or 2 (§12.2 row f) | HEAD | the Run is obsolete and is not continued; when no matching Run is recoverable, a new Run is begun that records it in `set_aside_runs` (§12.2 step 5, §12.8); nothing is written for the old Run | `ReconcileRequired` (`review_recovery_incomplete`), nothing begun |
| the use check (latest generation 3, no registration stage recorded, §17) | HEAD, recorded as `use_check_head` when the use check passes | stale after the Receipt: invalidation (§13.3) | `ReconcileRequired` (`review_candidate_mismatch`), pending; nothing invalidated |
| the pre-Kp currency proof (registration stages recorded, Kp not made, §15.6) | P, which HEAD must be | `ReconcileRequired` (`review_registration_currency_changed`, §13.4) | `ReconcileRequired` (`review_candidate_mismatch`) |
| C-2(Kp) item P12 (§15.3) | Kp's parent P | `ReconcileRequired` (`review_persisted_proof_failed`, §13.4, §15.5) | the same |

Once C-2(Kp) has passed, the authorization is spent on the proven Kp: the Consumption records it, and Km and the publication are proven by exact metadata proofs and the committed planning proof (§18.2, §18.8) and by the publication barrier (§18.7), not by currency.

### 13.2 Stale before a Receipt exists

The Run's latest generation is 1 or 2: nothing is sealed and no Receipt exists. Then:

- no generation is written and no Supersession: a Supersession names a Receipt (Frozen P1 R1 §5, R3 §8), and there is none to invalidate;
- the planning mutation completes with no effect recorded, and the result is `ReviewedPlanningResult(status="stale", receipt_id=None, ...)` (§19.2);
- the Run keeps its latest generation (status `open`), its task accepted and unsettled (latest 1) or settled (latest 2). A subsequent same-request invocation's discovery (§12.2) recovers it when its Candidate is current again, or sets it aside as obsolete and begins a new Run that records it in `set_aside_runs`, after which it is never continued (§12.8).

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

- at the pre-Kp currency proof: `ReconcileRequired` (reason `review_registration_currency_changed`, `review_candidate_mismatch` for a Candidate mismatch with the declared base equal (§13 item 4), or `review_registration_base_moved` for the base rules of §15.6); no Kp is recorded or made, no Consumption is written, nothing is pushed; the planning mutation stays pending with its registration in the working tree, and the same request continues once the difference is gone (the authority text restored, for example);
- at C-2(Kp): `ReconcileRequired` (reason `review_persisted_proof_failed`) with the consequences of §15.5: no Consumption, and the publication barrier holds for every commit whose history holds Kp.

The registration is never undone, and Kp is never reset, rebased or amended.

### 13.5 Changes and outcomes

| change | detected by | before a Receipt | after the Receipt, before the registration | after the registration began |
| --- | --- | --- | --- | --- |
| a different request or design (the caller passes another plan) | live same-request / `_require_resumable` | `reconcile_required`, record untouched | same | same |
| declared base: lifecycle or state of a named existing Phase or Work, the Phase's or Roadmap's lifecycle or state, a Phase dependency's state — as committed | §13 item 3 on the committed view, before any R9 or Candidate comparison | terminal `stale` (§13.2) | generation 4 + Supersession, then terminal `stale` (§13.3) | `ReconcileRequired` (§13.4) |
| Workline implementation content | Context (`loader_identity`) | terminal `stale` | generation 4 + Supersession, then `stale` | `ReconcileRequired` |
| authority text (`registry.md`, a listed Skill) | Context (`authority`) | terminal `stale` | generation 4 + Supersession, then `stale` | `ReconcileRequired` |
| Effective Policy | policy hash | terminal `stale` | generation 4 + Supersession, then `stale` | `ReconcileRequired` |
| with the declared base equal: reserved IDs, the planning invocation or the R9 selection on the committed basis not reproducing the Run's Candidate | rebuild (§13 item 4) | `ReconcileRequired` (`review_candidate_mismatch`) | same | same before Kp; `review_persisted_proof_failed` in C-2(Kp) |
| a Run record changed | the P1 reader (`review_record_*`); the live `create_file` classification (`ReconcileRequired`, reason `None`); the blob check (`review_not_persisted`, §17 item 6; `review_receipt_invalid` in the pre-Kp proof, §15.6 item 3) | a STOP, the planning mutation pending | same | same |
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

1. *Transform attributes.* For every planning-owned path of the stage, `git check-attr -z filter ident working-tree-encoding -- <paths>` must report `unspecified` (or `unset`) for all three attributes, and the effective configuration must define no filter driver named `unset` or `unspecified` (no `filter.unset.*` or `filter.unspecified.*` key). Anything else → `StopError` code `review_git_transform`. These are the attributes that can make a committed blob differ from the written bytes or run an external process during `git add` (clean and process filters, Git LFS, `$Id$` expansion, re-encoding). The printed words alone prove no state: `check-attr` prints a literal value with the same word, and a committed `filter=unset` makes `git add` run a configured driver named `unset` (**Measured**, §31). With no driver named `unset` or `unspecified`, a printed `unset` or `unspecified` selects no filter; `ident` expands only when set; and a literal `unset` for `working-tree-encoding` names no encoding Git has, so `git add` fails instead of storing other bytes (**Measured**). Text and eol normalization is the identity on LF-only content, and every file P2 writes is LF-only (canonical renderers; CR refused by §7.6).
2. *Checkout capability.* For every Review record path of the stage — at the freeze every Review path the Run can write and every Review record committed at HEAD — the checkout capability of §14.5.

### 14.4 Freeze order

**Frozen.** For a new Run — begun only when canonical recovery discovery (§12.2) allows it, and after the planning mutation recorded the `recovery_discovery` note (§12.8) — after `_open` and the live reservations:

```text
1  RoadmapPlan: reserve `roadmap` (live) and the Phase and relation IDs through `decide_phases` (live; records
   nothing); PhaseEntryDesign: reserve every stage ID under the register_works keys (§7.3); extend the entity scope
2  build the Candidate on the committed basis of HEAD: the declared base on HEAD's committed view (§7.4); W
   from the canonical record (§7.8); the expected effects and the projected view (§7.6); the R9 selection
   (§7.7); the working-tree compatibility check (§7.4); the representability check (§7.6)
3  Context (§8), Policy (§9), evidence (§10.6); the request envelope's set_aside_runs from the recovery_discovery note
4  reserve Run, task, Receipt, Consumption IDs (§6.3); extend the file scope with the Consumption path
5  gate.require_committable (every Review path the Run can write: snapshot, task input, gates 1-4, Receipt,
   Supersession, Consumption); Git persistence preflight with the checkout capability (§14.3, §14.5);
   Review namespace readability (§14.6); dirty overlap (§14.2); with a push destination, the publication
   barrier on HEAD (§18.7)
6  record the note review_binding (§11.5)
7  start generation mutation 1
```

Everything in this order runs after `_open`; a refusal of the canonical-input preflight comes before `_open` and begins nothing, so there is nothing to abandon (§5.6). Before generation mutation 1 has started, steps 1–6 are refusals: a STOP anywhere in them abandons the planning mutation, whether this run began it or resumed it (§12). A resume runs them again deterministically, by the pre-freeze resume setup (§12.9): every recorded reservation is returned unchanged, a missing `recovery_discovery` note is established by discovery, and a recorded `review_binding` is kept and checked. Once generation mutation 1 has started, a resume never runs steps 5–6 again and never abandons: steps 1–3 are recomputed only as the currency evaluation of §13, and the recorded `review_binding` is checked, never re-recorded. The checkout capability and the transform attributes are evaluated again before every Review-writing and every Git stage (§14.3).

A recovery planning mutation (§12.4) never runs steps 2, 3 and 7 and never reserves a canonical ID anew. In place of steps 1 and 4 it binds the canonical reservations (§12.5; on a resume without a recorded binding, by §12.9), reserves only the IDs that never became canonical (§12.6), and extends the entity and file scope as steps 1 and 4 do; then it runs steps 5–6 for the recovered Run and continues the Run by its chain.

The publication barrier at step 5 keeps a new registration from being built on a history that no Workline push may publish: when HEAD's history already holds a registration commit that the committed planning proof does not prove (§18.7, §18.8), the call stops with `review_publication_barrier` before any Review record. A remote-less Project publishes nothing and skips it.

### 14.5 Checkout capability

**Frozen.** Physical Review bytes must equal the canonical render bytes before any use (Frozen P1 R1 §4; P1-REV-007: `serialize.parse_canonical` refuses CR bytes). P2 never weakens or normalizes that. It therefore writes Review records only where Git's checkout semantics for Review paths reproduce the committed LF bytes in this repository and in every fresh clone of the commits that carry them, and proves that positively before writing. A subsequent commit that removes the rule removes the guarantee for clones of that commit; a P2 call there stops before writing (§21.2 row L18).

**Measured** (§31; Git for Windows 2.54 with system `core.autocrlf=true`):

- with no attribute rule a fresh clone checks out an LF-only Review record as CRLF while `git status` stays clean, and the P1 reader refuses it (`review_record_noncanonical`);
- a committed `.gitattributes` rule `.workline/review/** eol=lf -filter -ident -working-tree-encoding` keeps the fresh clone's bytes LF, also under a global attributes file asking `*.yaml eol=crlf` and under `core.autocrlf=false` with `core.eol=crlf`, and so does `-text` in place of `eol=lf`. Only the canonical rule below is accepted now: that rule lacks `!text`, and `-text` is not the canonical rule;
- a rule only in the origin's `.git/info/attributes` is not carried by a clone; a clone-local `.git/info/attributes` rule `eol=crlf` overrides the committed rule; a subsequent commit dropping the rule loses the guarantee for clones of that commit;
- `git check-attr --source=<commit>` alone still reads `.git/info/attributes`; the committed evaluation below reads the committed rule alone; `check-attr` answers for a path that does not exist yet;
- (final readiness repair round 1) `git check-attr` prints `text: unset` both for a real `-text` and for the literal value `text=unset`, which Git's conversion treats as an unspecified `text`. Under the committed rule `.workline/review/** text=unset -filter -ident -working-tree-encoding`, both evaluations print exactly the tuple round 1 accepted as form B, and a fresh clone made with `core.autocrlf=true` checks the LF record out as CRLF;
- (final readiness repair round 2) the same holds for every word of form L. `check-attr` prints an attribute's value, and prints a false state as `unset`: the literal values `filter=unset`, `ident=unset` and `working-tree-encoding=unset` print what `-filter`, `-ident` and `-working-tree-encoding` print, and `text=unspecified` prints what `!text` prints. Under the committed literal `filter=unset`, both evaluations print form L, and a fresh clone whose global configuration defines a filter driver named `unset` runs its smudge command: the Review records' bytes change, and `git status` shows them modified. The literal `working-tree-encoding=unset` makes `git add` of a Review path fail (`failed to encode ... from unset to UTF-8`). Round 1's observation that the literal values cloned as LF held only because no driver named `unset` was configured; it is not proof;
- (final readiness repair round 2) the canonical Review-attribute rule below, committed as the last attribute rule of the root `.gitattributes`: `git add` under it stores the written bytes; both evaluations print form L; a fresh clone keeps every Review record byte for byte under `core.autocrlf=true`, under `core.autocrlf=false` with `core.eol=crlf`, under a global attributes file asking `*.yaml eol=crlf`, `*.yaml filter=unset` (with a driver `unset` whose smudge changes bytes), `*.yaml ident`, `*.yaml working-tree-encoding=UTF-16`, `*.yaml text eol=crlf`, or the legacy `*.yaml crlf`, `*.yaml -crlf` or `*.yaml crlf=input`, and under all of them at once with `core.autocrlf=false` and `core.eol=crlf`, given as global and, separately, as system configuration. Rules before it in the same file (`* text=auto`, `*.png binary`) change nothing;
- (final readiness repair round 2) under a correct root rule, `.workline/.gitattributes` asking `* eol=crlf` makes both evaluations print `eol: crlf` and a fresh clone CRLF; `.workline/review/gates/.gitattributes` asking `*.yaml filter=unset` leaves both evaluations printing form L, while a clone with a driver `unset` changes that directory's records; and `.workline/.GITATTRIBUTES`, a name the committed evaluation does not read, takes effect on this case-insensitive filesystem, where a record checked out again in a fresh clone is CRLF;
- (final readiness repair round 2) in a clone configured to read attributes from another tree (`attr.tree` since Git 2.43, `GIT_ATTR_SOURCE` since Git 2.41), the committed `.gitattributes` is not read and the records check out as CRLF; in the writing repository the same redirect makes the effective evaluation print every attribute `unspecified`. A literal `filter=unset` in this repository's `.git/info/attributes` makes the effective evaluation print form L, and with a driver `unset` configured a record checked out again here changes;
- (final readiness repair round 2) a NUL byte in the root `.gitattributes` before the canonical rule line leaves that line intact to a line-by-line reading, but Git stops reading the blob at the NUL: the committed evaluation prints every attribute `unspecified`, and a fresh clone under `core.autocrlf=true` is CRLF.

**The canonical Review-attribute rule** (P2-READY-004). P2 v1 supports exactly one Review checkout configuration: HEAD's root `.gitattributes` holds this line, byte for byte, as its last attribute rule, and HEAD holds no `.gitattributes` below `.workline/`:

```text
.workline/review/** !text eol=lf -filter -ident -working-tree-encoding
```

Its operators, as Git applies them (the Git 2.40.0 sources: `convert.c` `convert_attrs` with `git_path_check_crlf`, `git_path_check_eol`, `git_path_check_convert`, `git_path_check_ident` and `git_path_check_encoding`; `attr.c`):
- `!text` returns `text` to unspecified, so a broader rule before it in the same file (`* text=auto`) and every global or system `text` value stop applying to Review paths;
- `eol=lf` keeps LF line ends on checkout, with no CRLF under any `core.autocrlf` or `core.eol`, and normalizes to LF on checkin (the identity on LF-only records); a legacy `crlf` value from another source ends as LF input or as binary, never as CRLF;
- `-filter` is the false state: Git looks up no filter driver, whatever drivers are configured;
- `-ident` is the false state: no `$Id$` expansion;
- `-working-tree-encoding` is the false state, read as no encoding: `git_attr__false` begins with a NUL byte, so its length is zero and `git_path_check_encoding` returns no encoding before its refusal of true and false. Git's own test `t0028` adds a path under `-working-tree-encoding`, from 2.18.0, where the attribute appeared; an older Git does not know the attribute.

In-tree attribute files outrank the global and the system files (gitattributes(5)). So in every fresh clone the rule fixes these five attributes for Review paths, whatever the system and global configuration hold.

**Fresh clone.** A fresh clone is a normal new clone of the commit: it has the repository's committed `.gitattributes` as its attribute source, no clone-specific `.git/info/attributes` added after cloning, and any normal system or global configuration — `core.autocrlf`, `core.eol`, `core.attributesFile` with any rules, filter drivers of any name. The canonical rule dominates every system and global attribute value for Review paths (Measured, above). P2 claims no protection against a person adding a higher-precedence `.git/info/attributes` rule to a clone, or pointing a clone's attribute source at another tree (`attr.tree`, `GIT_ATTR_SOURCE`, `--attr-source`): each replaces the committed source, and no committed file guards against that. The effective evaluation below covers the current repository.

**The proof: four layers, all required** (P2-READY-004). For every Review path checked:

1. **Raw committed source.** From HEAD's committed objects alone (`git ls-tree -z --full-tree <HEAD>`, `git cat-file blob`), never from the working tree:
   - the root tree holds exactly one entry whose name folds to `.gitattributes` (below), and it is the regular blob `.gitattributes`, mode `100644`;
   - its bytes hold no NUL byte, because Git stops reading an attributes blob at its first NUL (Measured); and, split at LF, they hold the canonical rule as their last attribute rule: the last line that is not blank (empty, or spaces and tabs only) and not a comment (`#` as its first character after any spaces and tabs) is exactly the rule's bytes, with no byte before or after them and no CR. Blank lines and comments may follow it. Any other line after it fails this layer, whatever paths it names, so P2 needs no second attribute-pattern engine to decide whether a rule after it reaches a Review path.
2. **No deeper committed `.gitattributes`.** HEAD's tree holds no entry of any type below `.workline/` — `.workline/.gitattributes`, `.workline/review/.gitattributes`, `.workline/review/**/.gitattributes` or any other descendant — whose name folds to `.gitattributes` (`git ls-tree -r -t -z --full-tree <HEAD> -- .workline`), because a deeper `.gitattributes` outranks the root rule for the paths below it. This layer fails whatever the evaluations print. *Folding* drops every non-ASCII character and lowers ASCII letters: a case-insensitive filesystem reads `.workline/.GITATTRIBUTES` as `.workline/.gitattributes` (Measured), and Git itself takes `.gitattributes` with ignorable non-ASCII code points for that name on HFS+ (`utf8.c` `is_hfs_dotgitattributes`); dropping every non-ASCII character refuses a superset of those names.
3. **Committed evaluation**, a cross-check: the committed `.gitattributes` files of HEAD alone print exactly form L — `git check-attr --source=<HEAD commit>` with `GIT_ATTR_NOSYSTEM=1`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=<an empty file>`, `-c core.attributesFile=<an empty file>` and `--git-dir=<a fresh, empty bare directory under .workline/runtime/review/attr-eval/<nonce>/ whose objects/info/alternates names this repository's object directory>`, removed afterwards; no `info/attributes`, system or global source takes part. It confirms that Git itself applies the committed rule — it does not, for example, apply a root file over Git's attributes size limit — and it never proves an attribute state.
4. **Effective evaluation** of this repository, every source included — `.git/info/attributes`, the working tree's and the index's attribute files, an attribute-source redirect, the global and the system files: plain `git check-attr` prints exactly form L, and the effective configuration defines no filter driver named `unset` (no `filter.unset.*` key). Under these two conditions the printed tuple cannot hide a transformation of the bytes: a printed `unset` for `filter` is the false state or a value that selects no driver; `ident` expands only when set; a literal `text=unspecified` is converted as an unspecified `text`; and a literal `unset` for `working-tree-encoding` names no encoding Git has, so `git add` fails. This is what the next checkout here, and every P2 `git add`, applies.

```text
form L   text: unspecified   eol: lf   filter: unset   ident: unset   working-tree-encoding: unset
```

Form L is what layers 3 and 4 must print. It is never by itself proof of an attribute state: layers 1 and 2 prove the canonical rule's operators from HEAD's raw committed bytes, and the second condition of layer 4 keeps a literal lookalike in this repository from transforming the bytes.

A failure of any layer → `StopError` code `review_checkout_unsafe`. A committed object, a file or a Git question that cannot be read or answered well enough to decide a layer → `StopError` code `review_checkout_unknown`. An unspecified `eol`, `filter`, `ident` or `working-tree-encoding` is never safe: the measured failure had every attribute unspecified while the committed blob was LF.

**Unsupported is not unsafe.** P2 v1 supports one positive Review checkout configuration, not every Git configuration that might preserve the bytes. A refused configuration is one P2 v1 does not prove clone-safe, not one proven unsafe. Refused, among others: `-text`, which also keeps LF bytes; `text=unset`; `text=unspecified`; `filter=unset`; `ident=unset`; `working-tree-encoding=unset`; the canonical rule, or an equivalent rule, in another `.gitattributes` file or in `info/attributes`; any `.gitattributes` below `.workline/`; any attribute rule after the canonical one. Nothing is normalized in their place, and there is no fallback form.

**Form B is withdrawn** (P2-READY-004, final readiness repair round 1). Round 1 also accepted `text: unset` with `eol: unspecified` (form B), which is how `check-attr` reports a real `-text`. It reports the literal value `text=unset` the same way, and Git converts that value like an unspecified `text`. So form B cannot positively prove LF bytes in a fresh clone (**Measured**, above). A real `-text` also keeps LF bytes, but no reading of `check-attr` tells it from the literal value, and it is not the canonical rule: it is refused like every other configuration. Round 2 found the same ambiguity in every word of form L, and moved the proof to HEAD's raw committed source (above).

A commit P2 makes carries only its own paths (`git commit --only`), so it carries HEAD's committed `.gitattributes` unchanged: the raw source and the committed evaluation of HEAD are those of the commit that stores the record.

Where it is checked: at the freeze (§14.4 step 5) for every Review path the Run can write and every Review record path committed at HEAD (`git ls-tree -r --name-only <HEAD> -- .workline/review/`); and for each stage's own Review paths before that stage is recorded and before its Git stage is recorded (§11.6, §15.1). At the freeze a failure abandons the planning mutation with nothing written; after generation 1, the planning mutation stays pending and continues once the configuration is back.

Workline never writes `.gitattributes` or `info/attributes`: making the capability available is the Project's own configuration decision, as its ignore configuration is (`gate.require_committable`). A Project that uses review-v1 planning commits the canonical rule as the last attribute rule of its root `.gitattributes`, broader rules before it (**Measured**, §31).

The Context binds the capability contract (`checkout_capability: review-v1-planning-checkout-v1`, §8): Frozen P1 R6 §6 and R11 §10 make attributes and line-ending conversion bound Git semantics, and R1 §4 has the Git persistence proof show that the committed path reproduces the canonical bytes under them. The capability has one configuration, the canonical rule. Every P2 proof and the publication barrier read raw blobs (§15.2, §18.7), never checked-out bytes, and evaluate no attribute: the committed planning proof needs no checkout capability and no `P2_REVIEW_GIT_MIN` (§5.7).

Legacy invocations evaluate nothing here and write no Review record.

### 14.6 Existing Review namespace

**Frozen.** At recovery discovery (§12.2 step 1) and again at the freeze, before any Review record, every record already in the Review namespace must read through `ReviewStore` in the working tree: the namespace shape rule of `validate_review` (only the known subdirectories, each a plain directory); `run_ids()` and `gate_chain(id)` for each Run; `receipt_ids()` and `read_receipt`; `consumption_ids()` and `read_consumption`; `superseded_receipt_ids()` and `read_supersession`; `candidate_snapshot_hashes()` and `read_candidate_snapshot`; `task_input_ids()` and `read_task_input`; `read_activation()`. Any failure — a CRLF record checked out before the rule existed (`review_record_noncanonical`), an unknown entry, a malformed record — → `StopError` code `review_namespace_unreadable` with the P1 error chained, and nothing is written: at recovery discovery no planning mutation exists yet, so nothing is begun; at the freeze the planning mutation is abandoned (§12).

This is the unchanged P1 strict reader applied to every existing record before P2 adds one, so P2 adds Review state only to a namespace whose every physical record is canonical. Cross-record findings that `validate_review` also reports — a half-written stage left by a lost runtime (§11.11) — are not refused here. P2 reads other Runs' records in three places only: recovery discovery, which reads the Runs matching the invocation and stops on an incomplete one (§12.2, §12.3); the uniqueness indexes (§16.3), which fail closed on their own; and the publication barrier, which reads registered Runs from committed objects (§18.7). Refusing the findings of any other Run would let one lost runtime disable review-v1 planning for the Project for good.

## 15. Registration, persisted proof and committed reload (C-3)

**Chosen: Direction A**: a planning-specific local commit, then an exact proof, then a canonical reload from the committed result, then equality, and only then publication.

Why: it proves what Git stored rather than predicting it. Direction B would need a positive proof, before the commit, of the exact Git objects through hooks, filters and concurrent writers. Live code has no helper for that, and it is harder to prove correct. The user preference of the task (§8.1) rules it out.

### 15.1 Sequence

**Frozen.** The planning mutation, after the use check passed and noted `use_check_head` (§17):

```text
1  registration stages, live and unchanged — roadmap, phases | works, integration, confirmation —
   fed from W (§7.8), never from the caller's plan or design; each preceded by the display base check
   (§15.7), with their projected refusals, postchecks and (Phase entry) the live phase structure check
2  working-tree round trip: ProjectView.load(store) -> normalize_persisted == reviewed, the registered
   entities and relations read from the working tree and the R9 selection from HEAD's committed basis (§7.7);
   mismatch -> ValidationError review_roundtrip_mismatch (P1 adapter code), pending
3  pre-Kp currency proof on P = HEAD (§15.6), the physical projection check of the recorded
   registration included (item 6); Git persistence preflight; ensure_separable(preexisting,
   registration paths)
4  stage review-registration-commit: one git_commit (Kp) of exactly the registration paths,
   planning commit primitive, base_head = P, base_exact (§15.2), the live message
   (chore(workline): create roadmap <display> | chore(workline): expand phase <display>); apply
5  persisted proof over Kp (§15.3): physical (P3, §15.7) and semantic (P5-P9) -> C-2(Kp)
6  Git persistence preflight on the Consumption path; stage review-consumption: one create_file —
   the Planning Consumption binding Kp (§16); apply
   (the recorded Consumption effect is the durable C-2(Kp) checkpoint)
7  Git persistence preflight; stage review-consumption-commit: one git_commit (Km) of exactly the
   Consumption path, planning commit primitive, message
   chore(workline): record review consumption <consumption_id>; apply
8  C-2(Km): M1-M6 (§18.2), M6 being the committed planning proof (§18.8);
   note publication_proof (a runtime sequencing marker only)        -> C-2(Km)
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
- **Base-exact registration commit** (wording fixed by P2-READY-006). The Kp `git_commit` payload also carries `"base_exact": true`, with `base_head` = P (a full commit ID) and `branch` = `review_binding.branch`.
  - **What it changes.** `base_exact` removes one step of the live classification and nothing else: `_classify_commit` (`mutation.py:1949-2016`) never takes its independent-advancement step for such a commit (`_head_advanced_independently`, `mutation.py:2014-2015`).
  - **The other steps** still decide whether the recorded commit effect is applied, unapplied or a mismatch, as they do for any commit:
    - a Kp the record holds as applied with its `commit_id` is decided by that ID on the recorded branch: matching while HEAD's history holds it, a mismatch otherwise;
    - nothing left to commit at its paths is applied (`mutation.py:2009-2011`). A Kp made just before an interruption kept its ID from being saved, and anyone's commit of those files, land here, and are then refused as unowned (below);
    - HEAD exactly `base_head`, on the recorded branch, is unapplied;
    - anything else is a mismatch, never unapplied: `ReconcileRequired`, reason `review_registration_base_moved`.
  - **Making an unapplied Kp.** It is made, or replayed, only while HEAD is exactly `base_head`. The pre-replay currency proof runs first for a recorded Kp classified unapplied (§15.6). The primitive reads HEAD again immediately before `git commit` and STOPs (`ReconcileRequired`, reason `review_registration_base_moved`) when it is not `base_head`. `_commit_just_made` then shows the new commit's one parent. A moved HEAD never shifts Kp onto a new base.
  - **Other commits.** Generation commits and Km keep the live base rules, independent advancement included: they carry Review records only, their bytes are proven exactly (§11.6, §18.2), and M1 bounds Km's parent (§18.2). A legacy `git_commit` payload and its classification are unchanged.
- The primitive's identity is the Context's `git_persistence` (Frozen P1 R5 §5–§6, R11 §10, R12 §8: a mechanically suppressed hook mode is bound in the Git semantics identity).
- Blob check (used by §10.3, §11.6, §15.3, §18.2): the committed blob of a path is read with `git cat-file blob <oid>` as raw bytes (no text decoding, no filters) and compared byte for byte; its mode comes from `git ls-tree -r -z --full-tree`.
- Kp or Km recorded applied without a commit ID cannot be shown to be the mutation's own. This covers an interruption between `git commit` and the save, and anyone's commit of those files, which the live nothing-left-to-commit step classifies as applied. The result is `ReconcileRequired` (reason `review_commit_unowned`), with no backfill in P2, the live treatment of an unidentified commit (`rules/git` Commit / push).

### 15.3 Persisted proof over Kp — C-2(Kp)

**Frozen.** Contract `review-v1-planning-proof-v1`. PASS requires every item; any failure → `ReconcileRequired` (reason `review_persisted_proof_failed`):

| # | condition | how |
| --- | --- | --- |
| P1 | Kp is the planning mutation's own commit | the `review-registration-commit` `git_commit` is recorded `applied` with `commit_id`; Kp = that ID |
| P2 | exact branch, parent and lineage | HEAD on `review_binding.branch`; that branch holds Kp; Kp has exactly one parent P; P == the `base_head` recorded in the Kp effect; P == `use_check_head`, or P descends from `use_check_head` and `gitcmd.commits_touching(use_check_head, P, planning-owned paths) == []` (so P also descends from `review_binding.head`) |
| P3 | exact physical projection | the comparison of §15.7: `git diff-tree -r -z --no-renames --no-abbrev --raw P Kp` equals the expected physical projection E of the Run's Candidate on P entry for entry — the path set, each transition, old and new modes, and the raw bytes of every new blob, whole ledgers included |
| P4 | the record is the projection | the record check of §15.7: the recorded registration effects write exactly E's paths, each `write_file` content is E's bytes for its path, and each ledger's recorded `wrote` digest of the registration's last write to it is the digest of E's bytes; with P3, Kp == the record == E |
| P5 | fresh canonical reconstruction | committed-result loader (§15.4) over Kp and over P |
| P6 | exact relation and entity records (semantic) | Kp's roadmap relations == P's + exactly the expected new relations, appended in registration order, records identical; the same for Related; Kp's entities == P's + exactly the reserved new entities (the ledger and entity bytes are P3's) |
| P7 | structure | `validate_structure(Kp view) == []` |
| P8 | normalized persisted semantics == reviewed Candidate | `normalize_persisted(load_persisted(result identity, Kp view)) == normalize_candidate(reviewed)` (projection identity; kind and semantics version equal); created IDs == reserved IDs; each expected entity and relation exactly once; no extra operation-owned entity or relation (P3 + P6) |
| P9 | R9 canonical first Work (PhaseEntryDesign) | `startable_works` + `planned_next_preference` on the Kp view give exactly the reviewed `canonical_first_work` (unique ID, or none) |
| P10 | interpretation unchanged | `loader_identity` recomputed now == the Context's; `adapter_identity` equal (P12 covers the whole Context) |
| P11 | nothing published before this proof | the planning mutation holds no `git_push` effect; the planning commit primitive runs no hook; and no Workline push of any operation can carry Kp unless the committed planning proof proves Kp, its Consumption and Km for the commit being published (§18.7, §18.8) |
| P12 | authorized pre-state | full currency (§13) on P: the declared base computed on the committed view of P (P5's P view), the Candidate rebuilt from it (digest == the Run's `candidate_hash`, record == the snapshot's `material`), the Context and the Policy recomputed now (== `review_context_hash`, `effective_policy_hash`); `review_kind`, `operation_identity`, `target_identity` and `authorized_operation_stage` recomputed == the Receipt's; P's tree holds the Run's snapshot, task input, gates 1–3 and Receipt with the canonical bytes (blob check), and no gate 4, no Supersession of the Receipt and no Consumption for it |

**Order** (P2-READY-001). P12's declared-base comparison (§13 item 3) is evaluated before every R9 comparison — the projection identity of P8, which carries the selection, and P9. So a declared-base difference is reported as P12 and never as an R9 mismatch, and an R9 difference is reported only with the declared base equal. Every item fails with the same reason, `review_persisted_proof_failed`; the order decides only which item the STOP names.

This covers the task's eleven requirements: 1 = P3, 2 = P3 + P4, 3 = P3 modes, 4 = P6, 5 = P8 created IDs, 6 = P3 + P6, 7 = P5, 8 = P8, 9 = P9, 10 = P1 + P2, 11 = P11 + §18. Together, P2 + P12 prove the authorized pre-state, P3 the exact physical result and P5–P9 its exact meaning: authorized pre-state + authorized transition = exact Kp result, physically and semantically, each proven on its own (Frozen P1 R8 §6–§7, R9 §8). Nothing is substituted by a path list, working-tree bytes, the request identity, `ProjectView.with_effects`, a semantic match, or the fact that P descends from `review_binding.head`.

P1–P12 are this operation's proof of its own registration. The committed substance of C-2(Kp) — the Run's authorization at P, P3's exact physical projection, P5–P9 and P12's declared base — is proven again, from committed objects alone, by the committed planning proof (§18.8) before any Workline push publishes a history holding Kp. P3 and CP5 are one check: the same E, computed by the same function from the same committed inputs, compared by the same comparison (§15.7), so the operation's proof and the cross-operation proof cannot disagree about Kp's bytes. What only the operation can prove stays with it: that Kp is its own commit (P1), that its record is exactly E (P4), its runtime notes (P2's `use_check_head` and `base_head`), and the currency of the Context and Policy at the time of the registration (P10, P12).

### 15.4 The committed-result loader

**Frozen.** Its responsibility is limited to this: given a commit C, materialize exactly C's canonical Project files from raw blob bytes (`git ls-tree` + `git cat-file blob`; no checkout, no smudge, no eol conversion):

- `.workline/project.yaml`
- `.workline/roadmaps/*.md`, `.workline/phases/*.md`, `.workline/works/*.md`
- `.workline/relations/roadmap.yaml`, `.workline/relations/related.yaml`
- `.workline/events/events.jsonl`

It writes them into a fresh directory `.workline/runtime/review/proofs/<nonce>/`, then returns `ProjectView.load(ProjectStore(<that directory>))`, the production loader unchanged.

- Limits: every materialized entry is a blob of mode `100644`; a symlink (`120000`), gitlink (`160000`), executable (`100755`) or tree where a file belongs → proof failure. `.workline/review/**`, `.workline/derivations/**`, `.workline/runtime/**` and everything outside `.workline/` are not materialized (`ProjectView` does not read them). The directory is removed after the proof and read by nothing else; a leftover is runtime residue.
- No second parser: the loader parses nothing itself. Tests use this loader and the production readers, never a different parser.
- Why raw blobs: checkout conversion (`core.autocrlf`, eol attributes) changes only line ends, which the production reader normalizes. Content-changing checkout filters are refused on planning-owned paths (§14.3). So a raw-blob reading is what any conforming checkout reads. The reader's normalization is for meaning only: the physical comparison of §15.7 compares raw blob bytes exactly, so a line end the reader normalizes is still a physical mismatch there.
- **Measured** (§31): for a live Roadmap creation plus Phase entry, the materialized reading equals the working-tree reading, all 9 canonical files are mode `100644`, and structure validation is clean.
- The same loader gives the committed view of a base commit (§3) — `ProjectView` as of that exact commit, the only committed reader P2 has — to the freeze (the declared base, the working-tree compatibility check and the committed basis, §7.4, §7.6, §7.7), to recovery discovery (§12.2), to every currency evaluation (§13), the pre-Kp currency proof (§15.6) and P12, and it materializes P, into a directory of its own, as the base of the expected physical projection (§15.7); it is read by nothing that decides lifecycle (§22).

### 15.5 Proof failure after Kp exists

**Frozen.** STOP (`ReconcileRequired`, reason `review_persisted_proof_failed`). The planning mutation stays pending; no Consumption is written, and the planning mutation records no push. Kp remains a local, operation-owned commit that no Consumption proves, and the publication barrier (§18.7) refuses every Workline push — of this operation or of any other — whose history holds it. The barrier is computed from committed objects alone, so it survives a crash, the lock's release, another operation, runtime cleanup, runtime-record loss and a fresh clone. Workline never resets, rebases or amends Kp. Every retry runs the same proof over the same Kp. No invalidation follows (§13.4), and a Supersession would not clear the barrier: only the committed planning proof of Kp, its Consumption and Km does (§18.8) — never the mere presence of a Consumption.

A person can still push Kp with Git by hand; Workline cannot prevent that and never treats it as proof. The Consumption is written only after C-2(Kp) passes over the local objects; the barrier never reads the destination; and a push classification that finds the destination already holding a commit means only that nothing is pushed for it (§18.7). Which history the branch holds from then on is a person's reconciliation.

The preflight (§14.3), the representability check (§7.6), the contained commit primitive (§15.2), the working-tree round trip (§15.1 step 2) and the pre-Kp currency proof (§15.6) exist so that this path is reached only through a concurrent foreign change or a Git fault.

### 15.6 Pre-Kp currency proof

**Frozen.** Run immediately before the Kp stage is recorded (§15.1 step 3), with P = HEAD, and — when a resume finds the Kp stage recorded and its `git_commit` classified unapplied (§15.2) — immediately before `_open` replays it, with P = the recorded `base_head`, through the `refuse_recorded` hook of `_open` (composed after the live `refuse_invalid_phase_writes` / `refuse_invalid_work_writes`; the hook runs on a resumed mutation before `mutation.apply()`, `roadmap.py:233-264`). The hook classifies the recorded Kp first. A Kp classified a mismatch is refused before any replay (`ReconcileRequired`, reason `review_registration_base_moved`). A Kp classified applied is never replayed; C-2(Kp) decides it, and without a recorded `commit_id` it is `review_commit_unowned` (§15.2). PASS requires every item:

1. HEAD is P; the binding holds (§11.5);
2. P == `use_check_head`, or P descends from `use_check_head` and `gitcmd.commits_touching(use_check_head, P, planning-owned paths) == []`;
3. the Run's records are committed at P and unchanged (`gate.require_persisted` + blob check), and read back: latest generation 3, sealed, issuing the reserved Receipt; no Supersession of it; no Consumption for it;
4. `review_kind`, `operation_identity`, `target_identity` and `authorized_operation_stage` recomputed == the Receipt's;
5. currency (§13) on P, in its order: Context, Policy, the declared base on the committed view of P, then — with the declared base equal — the Candidate rebuilt with the R9 selection on the committed basis of P;
6. the physical projection on P: the record check of §15.7 — the recorded registration effects are exactly the expected physical projection E of the Run's Candidate on P.

It writes nothing. A failure of 1–2 → `ReconcileRequired` (reason `review_registration_base_moved`); of 3–4 → `ReconcileRequired` (reason `review_receipt_invalid`); of 5, a stale difference (§13 items 1–3) → `ReconcileRequired` (reason `review_registration_currency_changed`), a Candidate mismatch (§13 item 4) → `ReconcileRequired` (reason `review_candidate_mismatch`); of 6, or E unavailable (§15.7) → `ReconcileRequired` (reason `review_registration_projection_mismatch`). In every case no Kp is recorded or made, no Consumption is written and nothing is pushed; the planning mutation stays pending with its registration in the working tree (§13.4).

With W as the only writer input (§7.8), item 6 never meets two legitimate representations of one Candidate: a caller's mapping order does not reach the writer. It stays mandatory as the proof that the implementation fed the writer W and nothing else, and that no builder drifted.

Why not `P == use_check_head` alone: a Workline operation whose declared scope is disjoint from the pending planning mutation's (Roadmap / Phase hold, resume, cancel and achievement: event log only, §13.5) can commit in a crash window after the registration began. Strict equality would leave a registration that no Workline path can finish or undo. The invariant chosen is as strong for everything the Receipt authorized: the exact parent's committed semantic base, the Context and the Policy are the authorized ones (item 5, and again P12), no commit since the use check touched a planning-owned path, so every ledger the registration re-rendered holds on P exactly what it held when the registration was decided (item 2), the recorded registration is exactly E on P (item 6, and again P3/P4/P6), and Kp is made on exactly P (`base_exact`, §15.2). A commit that changed a declared-base fact, touched a planning-owned path, rewrote history, or added or removed an entity file whose count allocated the registration's display numbers stops the registration at this proof, before Kp exists.

### 15.7 The expected physical projection

**Frozen.** Frozen P1 R8 §5–§7 and R9 §6–§8 require two proofs of a planning registration, each required on its own: that its persisted meaning is the reviewed Candidate (P5–P9, CP6), and that its commit delta is exactly the canonical physical result the writer produces — entity bytes from the writer's own rendering functions, relation records with the exact reserved IDs, and the whole-file result of every shared ledger. This section freezes the second: one object, one computation, one comparison, used by the pre-Kp proof (§15.6 item 6), C-2(Kp) (§15.3 P3, P4) and the committed planning proof (§18.8 CP5).

**The object.** `ExpectedPlanningPhysicalProjection` — E. It is computed in memory whenever it is needed and never stored: no Review record, note or file carries it.

```text
E = project_expected(candidate, reserved, base=P)        # the kind's adapter (§20)
  parent:   P, a full lowercase hexadecimal commit ID
  entries:  one per path the registration writes, sorted by path (bytewise over its UTF-8 bytes):
    path       canonical relative path, text
    status     "A"  P's tree holds no entry at path
               "M"  P's tree holds a regular file at path
    old_mode   "000000" (A) | P's mode as Git writes it, which must be "100644" (M)
    old_blob   the all-zero object ID (A) | P's blob ID (M)
    new_mode   "100644"
    content    the exact bytes the writer's own computation produces for path
    new_blob   the object ID of content as a blob (git hash-object --no-filters -t blob --stdin, nothing written)
```

Every scalar of E except `content` is text of an exact form (P2-READY-018):
- **modes** are the six-character octal text `git diff-tree --raw` prints, never an integer (`000000` has no integer form);
- **object IDs** are full-length lowercase hexadecimal text in the repository's object format — 40 characters for SHA-1, 64 for SHA-256, the length of P's own ID, the forms `gitcmd` accepts (`gitcmd.py:17-18`). The all-zero object ID is that many `0` characters;
- **each status** is one uppercase letter.

These are the fields of the `review-planning-delta` record (§16.1).

**The computation.** Deterministic, from committed clone-safe inputs only: the Run's committed Candidate snapshot, through W (§7.8), Kp's exact parent P, and the running implementation's support for the adapter identity and projection semantics version the Run names (§6.2). No recorded effect, note or other runtime record takes part, so it is the same computation for the planning mutation, for another operation's push, after runtime loss and in a fresh clone.

1. Materialize P's canonical Project files with the committed-result loader (§15.4) into a scratch directory S of their own.
2. For each registration stage, in the writer's order — RoadmapPlan: `roadmap`, `phases`; PhaseEntryDesign: `works`, `integration`, then `confirmation` when the Candidate has one:
   1. allocate the stage's display numbers on S exactly as the writer allocates them on the working tree, from the number n of `*.md` entries S holds in the kind's entity directory (`ProjectStore.count_entities`), in the writer's two-digit form: the Roadmap `R-{n+1:02d}` (`roadmap.py:484`), the Phases `P-{n+offset+1:02d}` in declared order (`phase_create.py:144-152`), the Works `W-{n+offset+1:02d}` by `create._allocated_displays` (`create.py:100-107`, called at `create.py:276`), n growing across stages as the earlier stages' files land in S;
   2. build the stage's effects with the writer's own effect builders from W's inputs for that stage (§7.8): the Roadmap `write_file` exactly as `_create_roadmap` builds it (`roadmap.py:478-486`); the Phase `write_file` and `add_relation` effects exactly as `decide_phases` builds them (`phase_create.py:141-157`); for each Work stage `create._registration_effects` (`create.py:325`) with W's specs, relations and reserved IDs for that stage;
   3. apply the effects to S in their order with the writer's own planned-write computation (`MutationController._planned_write`, `mutation.py:2142-2169`): a `write_file` puts its content, and an `add_relation` re-renders the whole ledger as `render_relations(read_relation_file(file) + [record])`; each result is written into S as `durable_write_text` writes it (UTF-8, no line-end translation).
3. E's entries are the paths step 2 wrote, each with the bytes S holds at the end; the old side is read from P's tree.

The effect builders and the planned-write computation are the writer's own: reused, or extracted as pure functions with no behaviour change that the writer itself calls (§20, §27). The adapter renders nothing, formats nothing and parses nothing of its own, and it maps the Candidate to writer inputs only through W (§7.8), the same function the actual registration uses, so the registration and E cannot receive different inputs.

By construction:

- an entity's bytes are the writer's canonical frontmatter and body (`render_entity`, `render_body`), with the display numbers allocated on P;
- a shared ledger's expected bytes are the whole file the writer produces from P's ledger — every record P holds, re-rendered, followed by the Candidate's records in registration order — never only the added records, and never a comparison of record sets;
- the projection belongs to its base: the same Candidate on two different P gives each P's own whole-ledger bytes and display numbers, and Kp is compared only with the projection on its own parent. The base rules of §15.6 and P2 keep that parent the one the registration was decided on for every path the registration writes.

**The comparison** (C-2(Kp) P3, CP5). `git diff-tree -r -z --no-renames --no-abbrev --raw P K` lists exactly E's paths — none missing, none extra — and, for each, E's status (`A` / `M`; any other status, `T` included, fails), E's old mode and old blob, new mode `100644` (a symlink `120000`, gitlink `160000`, executable `100755`, or any other representation of the regular file fails), and E's `new_blob`, so the committed blob's raw bytes are E's `content`, byte for byte. A CRLF where E has LF, a reordered or re-quoted frontmatter key, a blank line more or less, a whole ledger re-rendered with the same records — every difference the production reader reads with the same meaning (**Measured**, §31) — is a mismatch.

**The record check** (pre-Kp proof item 6, C-2(Kp) P4). The planning mutation's recorded registration effects write exactly E's paths; each path's last `write_file` content is E's `content`, and each ledger's `wrote` digest of the registration's last write to it is the digest of E's `content` (`_text_digest`). It needs the record, so only the planning mutation runs it.

**The display base check.** The writer allocates display numbers from the working tree; E allocates them on P. So immediately before each registration stage is recorded — the first one at the use check (§17 item 9) — the `*.md` entries directly under each entity directory whose count allocates display numbers for the kind (RoadmapPlan: `.workline/roadmaps/` and `.workline/phases/`; PhaseEntryDesign: `.workline/works/`) must be exactly HEAD's entries there plus the entity files the planning mutation's recorded stages wrote there. Otherwise `StopError` code `dirty_overlap`: nothing is recorded, the planning mutation stays pending, and once the person commits or removes the entry the same request continues. So no registration is recorded with display numbers no base can reproduce. A change that still slips in — an actor outside Workline under the lock, or a person's commit adding or removing an entity file of that kind after the registration began — is refused by pre-Kp proof item 6 before Kp exists.

**Availability.** E is unavailable when the running implementation does not provide the adapter identity the Run's Context names, does not support the Candidate's projection semantics version, or cannot complete a step (a file of P unreadable or malformed, a ledger missing, an entry the loader refuses). Unknown is never proof: the pre-Kp proof and C-2(Kp) stop with `ReconcileRequired` (`review_registration_projection_mismatch`, `review_persisted_proof_failed`), and the committed planning proof fails CP5, so the publication barrier holds (§18.7) and no Workline push publishes the history.

**Implementation upgrades.** An implementation proves a registration only by reproducing E and the semantic projection exactly. A Workline version whose package digest (`loader_identity`) differs from the recorded one proves an old registration when it provides the Run's adapter identity and projection semantics version and those reproduce every byte of E and the same semantic projection, with every other CP item passing. If it produces one different expected byte anywhere, CP5 fails and the barrier holds for every history holding that registration. A change to W (§7.8), a renderer, a display allocation or the planned-write computation that a planning adapter uses therefore changes that adapter's output: it is a new adapter version, never the old one under its old name, and a version that still has to publish histories holding such registrations keeps providing the adapter version they name; no loader-identity or semantic argument substitutes for the byte comparison.

**`registration_delta_digest`.** Derived from E, never from whatever Kp holds: the `review-planning-delta` record of §16.1 with `parent` P, `commit` Kp and E's entries (`path`, `status`, `old_mode`, `new_mode`, `old_blob`, `new_blob`), in the exact text forms above. The planning mutation computes it only after P3 has proven Kp's delta to be E (§15.1 steps 5–6), and CP9 recomputes it from E. A delta that is not E has no digest a Consumption may carry, and a Consumption carrying the digest of a delta that is not E fails CP5 and CP9.

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
  registration_delta_digest     # serialize.digest of the review-planning-delta record below, whose entries are the
                                #   expected physical projection E, proven to be Kp's delta (§15.7)
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

**The `review-planning-delta` record** (P2-READY-018) is canonical data with exactly these fields and types:

```text
schema:    "review-planning-delta"                 text
version:   1                                       integer
parent:    P                                       text, full lowercase hexadecimal commit ID
commit:    Kp                                      text, full lowercase hexadecimal commit ID
entries:   E's entries, sorted by path (bytewise)  a sequence of mappings, each with exactly:
  path:      text, the canonical relative path
  status:    text, "A" or "M"
  old_mode:  text, six octal characters: "000000" for "A", otherwise P's mode, "100644"
  new_mode:  text, "100644"
  old_blob:  text, full lowercase hexadecimal object ID: the all-zero ID for "A", otherwise P's blob ID
  new_blob:  text, full lowercase hexadecimal object ID
```

Object IDs have the length of the repository's object format — the length of P's own ID: 40 for SHA-1, 64 for SHA-256. The all-zero ID is that many `0` characters; nothing assumes SHA-1.

`registration_delta_digest = serialize.digest(record)`. It digests E, never Kp's actual delta (§15.7), and CP9 recomputes it the same way. The types are part of the identity: **Measured** (§31), the digest of the record changes when a mode is an integer instead of its text.

### 16.2 Reading and validation

**Frozen.**

- Version 2 is valid only for the two P2 kinds, and a P2 kind is valid only in version 2. Version 1 with a P2 kind is `review_record_invalid`.
- Exact field sets; exact per-kind `persisted_result` fields. IDs, digests, full commit IDs and full branch refs are checked for form.
- `target_identity == roadmap_id` (RoadmapPlan) or `phase_id` (PhaseEntryDesign), and `adapter_identity` is the kind's.
- Lists are free of duplicates.
- The P1 Receipt binding (`RECEIPT_CONSUMPTION_BINDING`) applies unchanged.
- A Consumption of a superseded Receipt is a problem, as in P1.
- The v1 reader, its Work binding rule and every v1 record are unchanged.
- Reading proves form and bindings only. What a Planning Consumption claims — its registration commit and parent, delta and semantic projection digests, IDs, adapter and loader identities — is never trusted for publication: the committed planning proof recomputes or cross-checks every claim from committed objects (§18.8), so a schema-valid Consumption that a person or another tool wrote proves nothing by existing. Its `registration_delta_digest` is compared with the digest of the expected physical projection, never with a digest of whatever Kp holds, so the digest of a noncanonical delta legitimizes nothing (§15.7).

### 16.3 Uniqueness (Frozen P1 R4 §1, §7)

**Frozen.** `ReviewStore` indexes, each a refusal (`review_consumption_conflict`):

- Receipt → at most one Consumption: the P1 index, now over v1 and v2.
- `persisted_result.registration_commit` → at most one Planning Consumption.
- `(review_kind, target_identity)` → at most one Planning Consumption.

This is "Receipt-based plus kind-specific semantic persisted-result binding" (R4 §7). No planning Consumption carries or invents a Work terminal event.

### 16.4 No self-reference

The Consumption names Kp (and its parent), which are ancestors of the commit that stores it, never Km itself. Receipts carry no commit SHA (P1 unchanged).

### 16.5 No field added by the round-1 to round-3 repairs

**Frozen.** Every candidate binding named for the repairs was re-checked; none is added, and version 2 stays exactly §16.1:

| candidate binding | decision |
| --- | --- |
| `use_check_head` | not bound: an intermediate anchor of the pre-Kp proof. What the Receipt authorized is proven on Kp's exact parent (P2, P12), which the Consumption binds as `registration_parent` |
| exact Kp parent | already bound: `registration_parent` |
| authorization generation | already bound: `review_generation` (3) with `receipt_id` |
| invalidation / supersession status at use | redundant: the use check, §15.6 and P12 require no Supersession, generation 4 never follows a registration stage (§13.3), and P1 refuses any Consumption of a superseded Receipt (§16.2) |
| publication-barrier identity | none exists to bind: the barrier's committed planning proof is computed from the Candidate snapshot, the registration commit, this Consumption and Km (§18.7, §18.8); `persisted_result.registration_commit` is one of the claims it cross-checks (CP9) |
| C-2(Km) proof basis | none: the durable basis is the committed objects the committed planning proof reads (§18.2, §18.8); a Consumption cannot name the commit that stores it (§16.4) and does not need to |
| recovery owner | none: `operation_mutation_id` names the planning mutation that consumes — for a recovered Run, the recovery planning mutation (§12.4); the Run is bound by `review_run_id`, and the committed planning proof never reads mutation IDs |
| expected physical projection | none: E is recomputed from the Candidate snapshot and P by the Run's adapter whenever it is needed and never stored (§15.7); `registration_delta_digest` binds its proven result, in the existing `review-planning-delta` encoding |

## 17. Ordering and authorization states

**Frozen.**

```text
seal generation + Receipt committed      -> ISSUED
use check passes, use_check_head noted   -> VALID (evaluated on every run until the first registration stage is
                                            recorded, never after)
registration applied                     -> (registration in the working tree; Receipt unconsumed; no barrier)
pre-Kp currency proof passes, Kp made    -> (registration commit exists locally; the publication barrier holds for it)
C-2(Kp) passes, Consumption recorded     -> (the operation's persisted proof checkpoint)
Km committed                             -> CONSUMED (the barrier still holds until the committed planning proof
                                            proves the Run for the commit a push would publish, §18.7)
C-2(Km) passes (M1-M6, §18.2)            -> SUCCESSFULLY USED; publication_proof noted as a runtime marker only
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
4. `operation_identity`, `target_identity`, `review_kind` and `authorized_operation_stage` equal the recomputed ones, and the Run is the planning mutation's reservation — for a recovery planning mutation, the Run its recovery bound (§12.5);
5. the binding holds (§11.5);
6. the Run's records are committed at HEAD and unchanged (`gate.require_persisted` + blob check), so every history that holds the registration commit holds the Run's Candidate snapshot (§18.7);
7. currency (§13) on HEAD, in its order: Context, Policy, the declared base on HEAD's committed view, then — with the declared base equal — the Candidate rebuilt with the R9 selection on HEAD's committed basis;
8. no registration path differs from HEAD (`gitcmd.changed_against_head`): a change made after the freeze would otherwise be taken into the registration's own writes;
9. the display base check (§15.7): the `*.md` entries of every entity directory whose count allocates the registration's display numbers are exactly HEAD's, so the display numbers the writer allocates are the ones the expected physical projection allocates on HEAD, which is Kp's parent P unless a commit changes those entries first (then §15.6 item 6 refuses the registration before Kp).

Failures of 1–4 → `ReconcileRequired` (reason `review_receipt_invalid`). A failure of 5 → `ReconcileRequired` (reason `review_binding_moved`). A failure of 6 → the P1 `review_not_persisted` STOP, the planning mutation pending. A stale difference in 7 (§13 items 1–3) → invalidation (§13.3): generation 4 and the Supersession, then terminal `stale`. A Candidate mismatch in 7 (§13 item 4) → `ReconcileRequired` (reason `review_candidate_mismatch`), and an unavailable Context → the `review_context_unavailable` STOP (§8); these two invalidate nothing. A failure of 8 or 9 → `StopError` code `dirty_overlap`; nothing is written, the planning mutation stays pending, and once the person commits or discards the change the same request continues.

On PASS the planning mutation records the note `use_check_head = <HEAD, full commit ID>` and then its first registration stage. Until that stage is recorded, every run evaluates the use check again and records the note again; once it is recorded, the note is never changed and the use check never runs again (§15.6 takes over).

Answers (task §10):

- **Can registration be locally committed before Consumption?** Yes: Kp precedes it.
- **What prevents that commit from being treated as successfully authorized before persisted proof?**
  - "successfully used" exists only once C-2(Km) passes: the committed planning proof (§18.8) proves Kp — its exact bytes and its meaning —, its Consumption and Km from committed objects, and the operation proves they are its own commits;
  - the planning mutation records no push before C-2(Km);
  - the publication barrier (§18.7): no Workline push of any operation publishes a history holding Kp unless the committed planning proof proves Kp, its Consumption and Km for the commit being published;
  - the planning commit primitive runs no hook, so nothing Workline starts publishes Kp;
  - Review metadata is never lifecycle truth (§22), so no reader of lifecycle treats anything as authorized;
  - the operation returns `registered` only after `complete()`.
- **When is Consumption written?** After C-2(Kp) passes, as stage `review-consumption`.
- **Which commit stores it?** Km, a commit-only metadata commit made on top of Kp.
- **Does Consumption refer to an earlier registration commit?** Yes: `persisted_result.registration_commit` = Kp.
- **What authorizes the metadata-only commit?** The P2 metadata-commit rule (§18.3): Km carries exactly one OperationMetadataProjection path, admitted by the exact deterministic metadata proof C-2(Km), not by a Review. The Receipt authorized Kp; Km records that use.
- **How is recursion terminated?** OperationMetadataProjection is never normative (`projections.normative()`, Candidate 7 §4.3), so it is outside what Review authorizes. Km is proven, never reviewed, and a Km mismatch is `reconcile_required`, never a re-review.
- **When does push become permitted?** Once C-2(Km) passes right before recording the push stage (M1–M6, §18.2) and the publication barrier is clear for Km (§18.7). At classification and apply time the mutation-level validator re-checks the binding and the barrier runs the committed planning proof again (§18.4, §18.7). The `publication_proof` note only sequences these steps inside the mutation; it is never evidence.
- **What if persisted proof fails after the local registration commit?** §15.5: no Consumption, and the barrier keeps every history holding Kp unpublished by Workline.
- **What if Consumption write succeeds but its publication does not?** The planning mutation stays pending with Km local. The Receipt counts as consumed locally, and until a push carries Km the destination holds no part of Kp or Km: no Workline push publishes Kp unless the committed planning proof proves Kp, its Consumption and Km for the commit being published (§18.7). A retry re-runs C-2(Km) whenever the note is missing — the note is never assumed — then records or applies the push under the live push classification (`=`, `*`, ` `, `!`) and the barrier. A destination that holds another history is `reconcile_required`, never forced. No second Consumption can be written (reserved ID + §16.3). Another operation's push from Km or a descendant may publish Km as history only where the committed planning proof proves the Run for that commit; the retry then classifies Km as already published. If the runtime is lost here, §21.2 applies: nothing about the lost `publication_proof` note is assumed.
- **What if the registration commit is accidentally published before Consumption?** No Workline push can do that: the barrier refuses every push — this operation's and every other operation's — whose history holds Kp unless the committed planning proof proves Kp, its Consumption and Km for the commit being published (§18.7). Only a person can push it by hand (manual Git). The resume then continues unchanged — C-2(Kp) if not yet recorded, Consumption, Km, C-2(Km), push of Km — and nothing about Kp being at the destination is read or relied on; the push fast-forwards the destination from Kp or from any subsequent commit (classified as live). If C-2(Kp) fails, §15.5 applies and the barrier stays.
- **Retry / resume in each case:** §21.

No reset, rebase, amend or deletion of a commit occurs anywhere.

## 18. P2 planning publication contract (C-1)

### 18.1 Shape

**Frozen.** `review-v1-planning-publication-v1`:

```text
Kp commit-only  ->  C-2(Kp) = recorded Consumption  ->  Km commit-only  ->  C-2(Km) = M1-M6 (M6: the committed
                                                                            planning proof, §18.8)
                ->  push-only stage publishing exact Km
```

One push per planning operation. It publishes Km and its history: Kp, the Run's generation commits, and base history. Any other Workline push from Km or a descendant may publish it as history too, but only where the committed planning proof proves the Run for the commit it publishes (§18.7, §18.8); no Workline push ever publishes Kp otherwise. This is not the current-combined shape (Frozen P1 R5 §12.1), and it is not the Work-terminal `review-v1-split-v1` contract (R5 §12.2, with its ReviewValidity bindings). It is a separately named P2 contract.

### 18.2 Metadata proof over Km — C-2(Km)

**Frozen.** Contract `review-v1-planning-proof-v1`. The planning operation records its push stage only when M1–M6 all pass; any failure → `ReconcileRequired` (reason `review_metadata_commit_mismatch`), no push, Km stays local:

| # | condition |
| --- | --- |
| M1 | Km is the planning mutation's own commit (recorded `applied` with `commit_id`); Km has exactly one parent Q; Q is Kp or descends from Kp, and `gitcmd.commits_touching(Kp, Q, planning-owned paths) == []` |
| M2 | HEAD on `review_binding.branch`; that branch holds Km |
| M3 | `diff-tree` of Q → Km is exactly one entry: the Consumption path, status `A`, mode `100644`, blob bytes == the recorded `create_file` content |
| M4 | Km's tree holds every Run record (snapshot, task input, gates 1–3, Receipt) and the Consumption with mode `100644` and bytes == their canonical bytes as `ReviewStore` reads them, no gate 4 and no Supersession of the Receipt, and every registration path with the same blob ID as in Kp |
| M5 | the Consumption reads back (v2 reader), binds the Receipt, and its `registration_commit` == Kp |
| M6 | the committed planning proof (§18.8) proves the Run for Km: every property of Kp, its Consumption and Km, re-proven from committed objects alone |

M1's ownership, M2's `review_binding` and M3's recorded `create_file` content are properties of this planning mutation's record; M6 needs no record, and M3–M5 are also parts of it (CP8, CP9, CP11–CP13).

**The durable checkpoint.** Frozen P1 R5 §1.1 requires C-2 to be durable, keyed by exact commit identity, complete before the push is recorded or applied, and never reconstructed from a push. The durable proof basis of C-2(Km) is the committed object set M6 reads: the Run's Candidate snapshot, task input, gates 1–3 and Receipt; the registration commit Kp and its parent P, whose tree is the base of the expected physical projection (§15.7); Km and its parent Q; the Consumption blob; and the history between them. Those objects are immutable and content-addressed, and the basis is keyed by the exact commit IDs of Kp and Km. Once Km exists, the outcome of the committed planning proof over that basis is fixed, and any process in any clone whose implementation provides the Run's adapter and projection semantics reproduces it (§15.7); the proof never reads a push, a remote or a runtime record. On PASS the planning mutation records the note `publication_proof = {contract: review-v1-planning-proof-v1, registration_commit: Kp, metadata_commit: Km, consumption_id}` — a runtime sequencing marker inside that mutation only. It is never the proof basis; a missing note is recomputed, never assumed; no barrier and no other operation reads it.

**Ownership and publication are separate questions (rule B).**

- *May this planning mutation adopt Kp and Km as its own commits?* Only if its own record shows it made them: P1 and M1, the `commit_id` recorded with `applied` (`_make_commit`). A commit it did not record — a byte-identical foreign commit, one made just before an interruption kept its ID from being saved, or any commit once the runtime record is lost — is never adopted (`review_commit_unowned`, §15.2). No recovery planning mutation continues a Run past its registration commit (§12.7).
- *May a Workline push publish a history that holds Kp and Km?* Only if the committed planning proof proves the Run for the commit being published (§18.7). This needs no ownership: it reconstructs every safety property from committed objects, so a history that passes it holds exactly what the Receipt authorized, whoever made the commits, and a history that fails it is never published, whoever made them.

Safe history for another operation to publish is therefore not a commit this planning mutation may adopt: foreign commit ≠ operation-owned commit stays true, and publication safety does not depend on a runtime record surviving. Positive historical ownership (rule A) cannot serve the barrier: a completed planning mutation's record is removed under the live retention rule, so no subsequent push can show it, and every published P2 registration would block every subsequent push.

### 18.3 The metadata-commit rule (Km)

**Frozen** (P2-native; not the P3 Class-A K2 rule):

| item | rule |
| --- | --- |
| allowed contents | exactly one added path `.workline/review/consumptions/<consumption_id>.yaml`, mode `100644`, bytes = the canonical bytes of the recorded Planning Consumption |
| prohibited contents | any other path: a domain entity, relation, event, `project.yaml`, derivation, any other Review record, anything outside `.workline/`; any modification or deletion |
| authorization | the recorded Receipt → Consumption binding plus M1–M6; no Review |
| why no recursive Review | Km changes one OperationMetadataProjection path, which is never normative; Km is proven by exact projection, never reviewed |
| deterministic metadata projection | `{added: [(consumption path, 100644, canonical bytes)]}` computed from the recorded effect |
| extra domain change | refused by M3 before any push |
| Kp binding | `persisted_result.registration_commit` + M1 ancestry + M6 (CP9, CP11) |
| publication proves Kp and Km | the push stage exists only after C-2(Km) (M1–M6) passes; at classification and apply the validator re-checks the binding and the barrier runs the committed planning proof again (§18.4, §18.7) |

### 18.4 The push stage and its validator

**Frozen.** Stage `review-publication`, recorded only when the Project has a verified push destination, after C-2(Km) — M1–M6 — passes again right before the stage is recorded, and with the publication barrier clear for Km (§18.7). It holds exactly one effect: `git_push` with payload `{remote, branch, locator, commit: <Km full ID>}` (the live three keys plus `commit`).

The mutation-level validator (`_recorded_publication`, planning branch) names the commit only when all hold:

- the discriminator selects the planning contract (§18.5);
- the push is the only effect of its stage and the last effect of the record;
- `payload.commit` is a full commit ID, equal to `publication_proof.metadata_commit` (the note of the same record: a sequencing cross-check, never the proof);
- the effect right before the push (by position and `seq`) is a `git_commit` that is the only effect of its own stage, recorded `applied` with `commit_id == payload.commit`, naming `refs/heads/<payload.branch>`;
- `publication_proof.registration_commit` equals the `commit_id` of the recorded, applied `review-registration-commit` effect;
- Km has one parent, and that parent descends from Kp;
- `gitcmd.commit_changes(Km)` ⊆ `{Consumption path}`;
- the branch holds Km.

Otherwise it names nothing, and the push is refused (`ReconcileRequired`, reason `review_publication_invalid`). Classification and push are live and unchanged: a dry run of the exact refspec `<Km>:refs/heads/<branch>`, `=` published, `*` / ` ` unpublished, `!` a read-only destination read; never forced, never a branch tip. The publication barrier — the committed planning proof — is evaluated again for Km whenever the dry run shows the push would write, and right before the push (§18.7).

### 18.5 Discriminator

**Frozen.** Selection is read from the durable invocation only, never from stage shape, content or Review files (Frozen P1 R5 §12.3.2):

| durable invocation | publication rule |
| --- | --- |
| no `review_contract`, no `publication_contract`, operation not `review-generation` | current-combined: the live `_recorded_publication`, unchanged (R5 §12.3.1 case A) |
| `review_contract == review-v1-planning-v1` and `publication_contract == review-v1-planning-publication-v1` and operation in {`roadmap-create`, `phase-entry`}, with or without `recovery_of_review_run_id` | planning publication (§18.4); a combined commit + push pair in such a mutation is refused (`ReconcileRequired`, reason `review_publication_contract_invalid`) |
| operation `review-generation` | publishes nothing: a recorded `git_push` is refused (`review_publication_contract_invalid`), and P2 never records one there |
| any other presence, value or combination | fail closed (`ReconcileRequired`, reason `review_publication_contract_invalid`), never current-combined |

Legacy mutations carry no marker and get exactly the live rule. R5's `review-v1-split-v1` value is not recognized by P2; P3 adds it for START under R5.

The publication barrier (§18.7) is not a publication contract and is not selected here: it applies to every push, whichever contract names the commit that push publishes.

### 18.6 Authority for the shape

`rules/git` Push destination currently says a push is the last effect of its Git stage, right after that stage's only commit. The planning shape and the publication barrier need the amendments of §26.1. Until the implementation lands, no planning publication exists, and no planning registration commit exists for the barrier to concern.

### 18.7 Publication barrier

**Frozen.** No Workline push — of a review-v1 planning mutation, of a recovery planning mutation, of a legacy mutation, of any operation — publishes a commit whose history holds a review-v1 planning registration commit unless the committed planning proof (§18.8) proves that registration's Run for exactly the commit being published. The barrier and the proof read committed Git objects only: no commit message, branch position, runtime note (`publication_proof` included), mutation record, mutation completion, remote state or human convention takes part, so a process crash or restart, the lock's release, another operation, runtime cleanup, runtime-record loss or a fresh clone cannot remove the barrier and cannot clear it.

**Registered Runs.** For a commit C, read entirely from Git objects reachable from C:

1. *planning Runs in C's history*: every Candidate snapshot blob added in C's history under `.workline/review/candidate-snapshots/`, read as raw bytes and parsed by the P1 reader (`serialize.parse_canonical`, `records.CandidateSnapshot`), whose `material` is a `review-planning-candidate` of kind `roadmap-plan-v1` or `phase-entry-design-v1`;
2. *registration paths of each*: from the snapshot's Candidate content (§7.2 / §7.3) — `.workline/roadmaps/<roadmap.id>.md` and `.workline/phases/<id>.md` for every Phase (RoadmapPlan); `.workline/works/<id>.md` for every normal Work, the integration and, when present, the confirmation (PhaseEntryDesign). These are reserved IDs, which no other operation ever uses;
3. *registration commits*: the commits in C's history that add any of those paths. A commit adds a path when its tree holds the path and none of its parents' trees does; every parent of a merge is followed;
4. a Run whose registration paths are added in C's history is a *registered Run* of C.

"Added in C's history" is read with `git log --full-history --no-renames --diff-merges=combined --diff-filter=A --name-only -z <C> -- <directory>` (**Measured**, §31: it lists a side-branch commit that adds a path and a merge that itself adds one, and lists an ordinary merge as adding nothing; without `--diff-merges=combined` the adding merge is missed), and each blob with `git cat-file blob <commit>:<path>`. A path that a subsequent commit deleted or reverted is still found: the barrier reads the history, not only C's tree. The snapshot is always in the history of Workline's own Kp: the Run's records must be committed at the commit Kp is made on (§17 item 6, §15.6 item 3, P12). Only a person who first removes the Run's records from the branch history and then commits the registration files by hand leaves the barrier nothing to read — manual Git, which Workline does not control and never treats as a registration it made.

**Fast path and Git versions** (P2-READY-027, P2-READY-029).
- **The first read.** The barrier first reads `git rev-list --full-history -n 1 <C> -- .workline/review/candidate-snapshots/`. It is empty exactly when no commit in C's history changed anything under that directory. Then no snapshot was ever added there, C has no planning Run and no registered Run, and the barrier is clear.
- **Measured** (§31): the read lists a commit for a side-branch addition brought in by an ordinary merge, an evil merge that adds a path, an addition deleted afterwards, and a root commit holding a snapshot; it lists nothing for a history that never touched the directory.
- **It needs no P2 minimum.** Every Git the live baseline runs on answers this read, so a history that never held a planning snapshot is published as before, on any Git. It clears only when it ran and listed nothing: a read Git fails to answer holds the barrier.
- **When it lists a commit,** the running Git must meet `P2_PUBLICATION_GIT_MIN` (2.31.0, §5.7). On such a Git — 2.31 to 2.39 included, which cannot begin or resume review-v1 planning — the steps above and the committed planning proof run. A history whose planning Runs never added their registration paths has no registered Run, and the barrier is clear for it: a Candidate snapshot alone never begins the barrier.
- **Below `P2_PUBLICATION_GIT_MIN`, or on a Git whose version text does not parse,** the steps above cannot run, and the publication of such a history is refused: `StopError` code `review_publication_barrier`, detail "publication proof unavailable: the running Git is below P2_PUBLICATION_GIT_MIN (2.31.0)" or "... the running Git's version is unknown". It is a capability refusal before any Run is classified: it names no Run, no registration commit and no proof item, and it never states that a registration exists — only that its presence or absence cannot be established on this Git. Unknown is never a clear barrier.
- **Scope of "no barrier".** Where this contract says that a state begins no barrier, that a push proceeds or that a push is permitted, it speaks of a history the fast path clears or of a Git at or above `P2_PUBLICATION_GIT_MIN`. Below that minimum, every other history is held by the capability refusal above, which is not a registration barrier.

**Rule.** The barrier is clear for C exactly when the fast path lists nothing, or when, on a Git at or above `P2_PUBLICATION_GIT_MIN`, the committed planning proof (§18.8) proves every registered Run of C for C. Otherwise it holds: `StopError` code `review_publication_barrier`, naming the Run's `candidate_hash`, its registration commit and the first proof item that failed — or, below that minimum, with the capability detail above, which names none of them. The existence of a Consumption, of Km or of a `publication_proof` note proves nothing, and Kp or Km being at the destination proves nothing: every property they stand for is re-proven, never trusted. A second commit adding one of the registration paths — a cherry-pick of Kp, or a person deleting and re-adding the files — keeps the barrier holding until a person reconciles: which commit is the registration is never guessed from content. A blob that cannot be read or parsed, a planning snapshot whose content does not yield its registration paths, an expected physical projection the running implementation cannot compute (§15.7), or a Git question that cannot be answered is the barrier holding, never a clear barrier.

**Where it is checked** — every point at which Workline records or makes a push:

| point | commit evaluated | when it holds |
| --- | --- | --- |
| `gitops.finalize`, before recording a Git stage that holds a `git_push` (every current-combined stage with a destination) | HEAD, the parent of the commit the stage will make; that commit adds only its operation's own paths, never a planning Candidate snapshot, a Review record or a reserved registration path | the stage is not recorded; its mutation stays pending with its domain effects applied and continues once the barrier clears |
| before the planning `review-publication` stage is recorded (§18.4) | Km | the stage is not recorded; the planning mutation stays pending |
| the freeze of a review-v1 planning call, and the setup of a recovery planning mutation, with a push destination (§14.4 step 5, §12.4) | HEAD | the call stops before it writes any Review record; the planning mutation is abandoned |
| `MutationController._classify_push`, when the dry run shows the push would write (`*` or ` `) | the commit the record names (`_recorded_publication`, or the planning validator of §18.4) | the push is not classified unapplied: STOP, nothing pushed |
| `apply_effect` `git_push`, right before `gitcmd.push` (after the locator re-resolution) | the same commit | STOP, nothing pushed |

Apart from the freeze row, which stops a review-v1 call before it builds on a history no Workline push may publish, the barrier refuses publication only. A commit-only stage is never refused: generation commits, Kp, Km, a remote-less finalization and Project start commit as before. A push classified as already published — `=`, or `!` with the destination holding the commit (`_published_under`) — pushes nothing and is not refused: it publishes nothing and proves nothing, and it is never read as proof of Kp or Km.

The barrier is a pure function of the objects reachable from C and of the running implementation. Within one process a result computed for a commit ID may be reused for the same commit ID, because the objects behind a commit ID cannot change; nothing is cached across processes, and nothing stands in for the proof.

**Begins** when a commit adding a registered Run's paths enters the history of a commit Workline would publish: Kp, or a person's commit of the planning mutation's working-tree registration. Generation commits, a sealed Receipt, generation 4 and a registration held only in the working tree begin nothing: no registration commit exists, and every current-combined commit carries only its own paths (`git commit --only`). A Candidate snapshot alone never begins it. Below `P2_PUBLICATION_GIT_MIN`, a history holding a planning Candidate snapshot cannot be classified, and its publication is refused by the capability rule above — not because a registration was found.

**Ends** only when the committed planning proof proves the Run for the commit being published: Km, or a descendant that still holds its Consumption, whose Kp, Consumption and Km pass every item of §18.8. Never by a Supersession, the existence of a Consumption or of Km, a remote state, a commit message, a branch position, a runtime note, the planning mutation's completion or its loss. A commit between Kp and Km never becomes publishable by its own push; it reaches the destination as history of Km or of a descendant of Km, after which its own push is classified as already published.

**Kinds.** The two planning kinds. A snapshot of any other kind concerns no planning registration and is passed over; P3 adds its own rules.

**Remote-less Projects** record and make no push, so the barrier is never evaluated there; C-2(Km) (§18.2) completes the operation (§12).

**Legacy.** In a history that holds no planning Candidate snapshot — every Project that never ran a review-v1 planning invocation — the fast path finds nothing, whatever the running Git's version, and the barrier refuses nothing: every legacy outcome is unchanged. It is not a Review gate on the legacy operation: it asks nothing of the operation itself (no Review, no Receipt, no activation), only that what it publishes carries no review-v1 registration the committed planning proof cannot prove, so HUMAN-1 = A holds.

From the third row on, the running Git is at or above `P2_PUBLICATION_GIT_MIN`.

| state of a planning Run | barrier |
| --- | --- |
| no planning Candidate snapshot ever in the history (legacy-only), on any Git | none: the fast path clears it |
| a planning Candidate snapshot in the history, on a Git below `P2_PUBLICATION_GIT_MIN` or of unknown version | publication refused as a capability failure (`review_publication_barrier`, the proof unavailable): no Run is classified, and no registration is asserted |
| generation 1 or 2 only; generation 3 without a registration commit; generation 4 | none: no registration commit |
| not authorized; stale before or after the seal | none |
| registration applied to the working tree, Kp not made | none; a person's commit of those files is a registration commit and begins it |
| Kp made, no Consumption; C-2(Kp) not run or failed | holds; after a C-2(Kp) failure, until a person reconciles the branch history |
| Consumption recorded or applied in the working tree, Km not made | holds: the proof reads committed objects only |
| Km made, the committed planning proof not yet run by this push | holds until this push runs it and it passes |
| Km made, the committed planning proof fails (any item: Kp bytes that are not the expected physical projection, a forged or mismatching Consumption, a claim it cannot re-prove, an extra change in Km, a changed Run record, a Supersession anywhere in the history) | holds; the planning mutation is `ReconcileRequired`, and a person reconciles |
| Km made and its Consumption present, the semantic projection matching, but Kp's bytes not the expected physical projection (a reordered or re-quoted frontmatter key, CRLF, a blank line, a re-formatted ledger) | holds (CP5), whoever made Kp, for every Workline push, after runtime loss and in a fresh clone alike; a Consumption carrying the digest of Kp's actual delta legitimizes nothing (CP9) |
| the running implementation does not provide the Run's adapter identity or projection semantics version | holds: the expected physical projection is unavailable, and unknown is never proof (§15.7) |
| Km made, the runtime record lost before the planning mutation's own C-2(Km) ran or was noted | the push re-runs the proof from committed objects: it passes → clear; it fails → holds. The lost `publication_proof` note is never assumed |
| Km made and the committed planning proof passes for the commit being published | clear for that commit, whoever made Kp and Km (§18.2: publishable history is not an adopted commit) |
| commits between Kp and Km | holds: their tree holds no Consumption |
| Kp or Km already at the destination (a person's push, or any other means) | unchanged: the destination is never read as proof; a push that would write still needs the proof, and a push classified as already published writes nothing |
| fresh clone | the same answer from the same objects |

**No unrecoverable global block.** The barrier concerns only histories that hold a registration commit the committed planning proof does not prove — exactly the histories that must not be published — and every other history publishes as before, on a Git at or above `P2_PUBLICATION_GIT_MIN`; below it, a history that holds planning Review material waits for such a Git (§5.7). It ends when the proof passes (the planning operation's own retry, or any process after runtime loss when the committed objects prove it) or when a person takes the unproven commits out of the branch history. A Run that registered nothing (at any generation, not authorized, stale, invalidated) never begins it.

**Why not the Receipt alone** (the direction the independent review proposed to investigate): a sealed, unsuperseded, unconsumed planning Receipt is also the state of a Run whose planning mutation was lost after the seal and before any registration, waiting for a same-request invocation to recover it (§12.7) — which may never come. A Receipt barrier would stop every Workline push from that history over a Run that registered nothing. The registration commit is what must not be published unproven; the Candidate snapshot, committed before any registration, names exactly its paths; and only the committed planning proof of Kp, its Consumption and Km ends it. `ReviewStore` reads only the working tree, so the barrier reads the same records from committed objects with the same P1 parser (§27).

### 18.8 The committed planning proof

**Frozen.** Contract `review-v1-planning-committed-proof-v1`. For a registered Run R of a commit C (§18.7), the proof reads only Git objects reachable from C. It parses Review records from raw blobs with the P1 reader (`serialize.parse_canonical`, the P1 record classes, the version-2 Consumption reader) and reads Project files through the committed-result loader (§15.4); it computes the expected physical projection (§15.7) with the adapter the Run's Context names. It reads no runtime record, no note, no remote and no working-tree file. It evaluates no attribute and runs no `check-attr`, so it needs no checkout capability, and it runs on any Git at or above `P2_PUBLICATION_GIT_MIN` (§5.7). PASS requires every item; the barrier's STOP names the first item that failed.

The registration commit and its authorization:

| # | condition |
| --- | --- |
| CP1 | exactly one commit K in C's history adds any of R's reserved entity paths (§18.7 step 2), and K adds every one of them; K has exactly one parent P |
| CP2 | P's tree holds R's Candidate snapshot, task input, gates 1–3 and Receipt, each read back canonically from its blob; the chain read from P's tree validates under the P1 chain rules and is G1 accept → G2 settle → G3 seal; generation 3 issues the Receipt (`GATE_RECEIPT_BINDING`); P's tree holds no generation 4 and no Supersession of the Receipt |
| CP3 | provenance: generation 1's accepted descriptor, the task input and the snapshot agree exactly as `ReviewStore.provenance_problems` requires (the same comparisons, applied to the blobs); the snapshot's material digests to `candidate_hash`; the task input's `request_digest` is the digest of its request envelope, whose `candidate` is the snapshot's material and whose `context` digests to the Run's `review_context_hash`; the Run's `effective_policy_hash` is the digest of the static policy its envelope names (§9); the Run's `review_kind` and `target_identity` are the Candidate's |
| CP4 | C's tree holds R's Run records with the same blobs as P's tree, and no generation 4 and no Supersession of the Receipt was ever added in C's history |

The registration (Kp) — two independent requirements, physical (CP5) and semantic (CP6, CP7), each required on its own (Frozen P1 R8 §6–§7, R9 §8):

| # | condition |
| --- | --- |
| CP5 | physical: the expected physical projection E of R's Candidate on P (§15.7), computed from committed objects — the snapshot's `material` through W (§7.8) — with the adapter the Run's Context names, equals K's delta by the comparison of §15.7 — `git diff-tree -r -z --no-renames --no-abbrev --raw P K` lists exactly E's paths (R's registration paths, §14.1), each with E's status, old and new modes, old blob and `new_blob`, so every committed blob, whole ledgers included, holds exactly E's bytes; E unavailable → fails |
| CP6 | semantic, on the committed views of P and K (§15.4): `validate_structure(K view) == []`; K's entities are P's plus exactly the Candidate's reserved new entities; K's roadmap relations and Related are P's plus exactly the Candidate's new ones, appended in registration order, records identical; `normalize_persisted(load_persisted(result identity, K view))`, with the adapter the Context names, equals the Candidate's projection (projection identity; kind and semantics version equal); PhaseEntryDesign: the R9 selection on the K view is the Candidate's `canonical_first_work` |
| CP7 | authorized pre-state: the declared base computed on P's committed view equals the Candidate's declared base (§7.4) |

**Order** (P2-READY-001). CP7 is evaluated before CP6. A declared base that differs on P fails CP7; only with CP7 passing are CP6's R9 selection, and the projection identity that carries it, compared. So the barrier's STOP names CP7 for a declared-base difference, and never an R9 mismatch for it. The items are evaluated in the order CP1–CP5, CP7, CP6, CP8–CP13.

The Consumption:

| # | condition |
| --- | --- |
| CP8 | C's tree holds exactly one Consumption naming R's Receipt; it is a Planning Consumption (version 2) that reads back; `RECEIPT_CONSUMPTION_BINDING` holds with the Receipt; `review_run_id`, `review_generation` (3), `review_kind`, `authorized_candidate_hash`, `operation_identity` and `target_identity` are the Run's |
| CP9 | every `persisted_result` claim is re-proven: `contract` is the constant; `request_digest` is the digest part of the Run's `operation_identity`; `registration_commit` is K and `registration_parent` is P; `branch` is a full branch ref (form only: history may travel between branches); `registration_delta_digest` is the digest of E's `review-planning-delta` record with parent P and commit K, in the exact text forms of §16.1 (§15.7), never of K's actual delta; `semantic_projection_digest` is recomputed from CP6's projection; `adapter_identity` and `loader_identity` equal the Context's in the Run's request envelope; the per-kind IDs equal the Candidate's reserved IDs in the Candidate's order, and `canonical_first_work_id` equals CP6's selection |
| CP10 | uniqueness in C's tree (Frozen P1 R4 §1, §7; §16.3): no other Consumption names the Receipt, no other Planning Consumption names K, and no other Planning Consumption has R's (`review_kind`, `target_identity`) |

The metadata commit (Km):

| # | condition |
| --- | --- |
| CP11 | exactly one commit Km in C's history adds the Consumption's path; Km has exactly one parent Q; Q is K or descends from K; `gitcmd.commits_touching(K, Q, R's planning-owned paths) == []`; the blob Km added is the blob C's tree holds at that path |
| CP12 | `diff-tree` of Q → Km is exactly one entry: the Consumption path, status `A`, mode `100644` |
| CP13 | Km's tree holds R's Run records with the same blobs as P's tree, no generation 4 and no Supersession of the Receipt, and every registration path of R with the same blob as K's tree |

Against the list the independent review required: the exact planning Candidate and Run (CP2–CP4); exact Kp (CP1); Kp's exact physical projection, the canonical writer's bytes on its parent with whole ledgers (CP5); exact Kp parent (CP1, CP9); valid Receipt (CP2); Receipt not superseded (CP2, CP4, CP13); exact Planning Consumption v2 (CP8); Consumption → Receipt (CP8); Consumption → Kp (CP9); persisted-result IDs (CP9); registration delta digest of the proven projection (CP5, CP9); semantic projection digest (CP6, CP9); adapter and loader identity (CP9); exact Km delta, and Km carrying only the Consumption (CP11, CP12); registration paths in Km exactly the proven Kp result (CP13); uniqueness (CP10).

**What it does not prove, and why publication does not need it.** It proves Kp's exact physical projection (CP5) and its exact meaning (CP6, CP7) from committed objects. Three things remain the planning operation's own act, and the planning operation proves them itself before it writes the Consumption:

- that Kp and Km are the planning mutation's own commits (P1, M1): rule B of §18.2 keeps any mutation that did not record them from ever adopting them;
- that the planning mutation recorded exactly those bytes (P4): which subject wrote a commit is ownership, not publication safety. The bytes themselves are still bound: CP5 requires them to be exactly the canonical writer's projection on P, and a history whose Kp bytes differ is never published, whoever made it;
- that the Context and Policy were current when Kp was made (P10, P12): authority text and the implementation live outside the Project's history. The proof checks that the Consumption names the Context the Run was reviewed under (CP9) and recomputes the physical and semantic projections with the running implementation (CP5, CP6). It does not require the running `loader_identity` to equal the recorded one: a Workline upgrade proves an old registration exactly when it still provides the Run's adapter identity and projection semantics version and they reproduce every byte of E and the same semantic projection (§15.7). One different expected byte, or an adapter, projection semantics version or policy no longer provided, and the proof fails and the barrier holds.

A registration a person makes by hand passes the proof only if its bytes are exactly the expected physical projection on its exact parent, its meaning is exactly the authorized content on the authorized base, and it is bound to a valid, unsuperseded, uniquely consumed Receipt. Publishing such a history publishes exactly what the Review authorized, byte for byte; it is still never adopted as a planning mutation's own commit. A hand-made or foreign Kp that the reader interprets identically but whose bytes differ — a reordered or re-quoted frontmatter key, CRLF, a blank line, a re-formatted ledger — keeps the barrier holding.

**Cost.** The proof runs for each registered Run in the published history, at each push that would write and at the freeze or recovery setup of a review-v1 call with a push destination. It is deterministic and bounded by those Runs' records, two committed views and one materialized projection base each. A Project that never ran a review-v1 planning invocation has no registered Run and pays one path-limited history read: the fast path of §18.7, which every Git the live baseline runs on answers, with no P2 minimum.

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
| retry of the identical request | a new Run and a new review; P2 does not remember the refusal: canonical recovery discovery sets the not-authorized Run aside (§12.2 row c) and records it in the new Run's `set_aside_runs` |
| crash between the settlement and `complete()` | with the planning mutation's record: the next run recomputes "not authorized" from the chain and completes. After runtime loss the canonical state is the same as after a completed not-authorized ending, and the identical request is a new Run (§12.7); the settled task is never launched again |

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
| a fresh call | discovery recovers the Run if its Candidate is current again; otherwise it sets it aside (obsolete) and begins a new Run (§12.2, §12.7) | the Run is terminal (generation 4): set aside, and a new Run is begun (§12.8) |

A difference found once a registration stage is recorded is never `stale` (§13.4).

### 19.3 Result type

**Frozen.** In `workline.roadmap_review`; `workline.roadmap` imports it inside the review-v1 branch:

```python
@dataclass(frozen=True)
class ReviewedPlanningResult:
    status: str                    # "registered" | "not_authorized" | "stale"
    operation: str                 # "roadmap-create" | "phase-entry"
    mutation_id: str               # the planning mutation (for a recovered Run, the recovery planning mutation)
    review_run_id: str             # for a recovered Run, the recovered Run
    receipt_id: str | None         # set when a Receipt exists (for "stale" after the seal: the superseded Receipt)
    consumption_id: str | None     # set for "registered"
    registration: RoadmapResult | PhaseEntryResult | None   # set for "registered"
    findings: tuple[PlanningReviewFinding, ...]             # the settled report's findings when available
    detail: str
```

On `registered`, `registration.head` is Km. `PhaseEntryResult.entry_work_id` is the reviewed canonical first Work, which equals the explicit entry when one was given. After runtime loss the runtime report copy is gone, so a recovered Run returns `findings=()` unless the task is launched again and reports; `detail` names a recovered Run ("recovered Run <review_run_id>").

## 20. Semantic round-trip adapters

**Frozen.** Two implementations of the P1 `PersistedProjectionAdapter` protocol (`review/adapter.py`) live in `workline.roadmap_review` (Roadmap-owned). They reuse the canonical renderers and registration helpers:

- W (§7.8): the stage-input derivation of `_create_roadmap` / `_expand_phase`, extracted as a pure function with no behaviour change that the legacy path itself calls, applied to the plan or design value rebuilt from the canonical Candidate;
- the Roadmap-file rendering of `_create_roadmap`, extracted as a pure function with no behaviour change;
- the effect building of `phase_create.decide_phases` (the Phase `write_file` and `add_relation` effects from reserved IDs and a display base, `phase_create.py:141-157`), extracted as a pure function with no behaviour change that `decide_phases` itself calls;
- `create._registration_effects`, `_allocated_displays` and `_resolve_roadmap_relations`, reused, or extracted as pure functions with no behaviour change;
- the planned-write computation of `write_file` and `add_relation` (`MutationController._planned_write`, `mutation.py:2142-2169`), extracted as a module-level function of `mutation.py` taking a store, which `_planned_write` itself calls.

Their semantic side reads only through `ProjectView`, `Entity.name`, `Entity.section`, `Entity.meta` and the `Relation` records. Their physical side (§15.7) produces bytes only through the writer's own builders and planned-write computation listed above. They never reimplement Roadmap, Phase CREATE or Work CREATE semantics, entity rendering or relation rendering, in `review/` or anywhere else: a second renderer whose output merely parses the same is what the physical proof exists to exclude (Frozen P1 R8 §5, R9 §6). Roadmap and CREATE stay the semantic and rendering authorities; the adapters and `review/` only project and verify.

One hand-off: W is computed by one function from one Candidate record, and the representability check, `project_expected` (E), the actual review-v1 registration and recovery all take it. No adapter method rebuilds `WorkSpec`, `RelatedSpec`, `RelationSpec`, `PhaseSpec` or `PhaseRelationSpec` values on its own, and none takes them from the caller's plan or design after the freeze (§7.8).

| responsibility | Roadmap adapter (`roadmap-plan-adapter-v1`) | Phase-entry adapter (`phase-entry-design-adapter-v1`) |
| --- | --- | --- |
| `adapter_identity` / `loader_identity` | §6.2 / §8.1 | same |
| `normalize_candidate` | §7.2 content as `Projection(reviewed_artifact, roadmap-plan-projection-v1)` | §7.3 content as `Projection(reviewed_artifact, phase-entry-design-projection-v1)` |
| `project_expected` | the expected physical projection E on the base commit it is given (§15.7) — P for the pre-Kp proof, C-2(Kp) and CP5 — built from W (§7.8), never from recorded effects, which are compared with it (P4); returned as a `ProjectionSet` of the reviewed artifact and an authorized transition whose content is E's `{parent, entries: [{path, status, old_mode, new_mode, old_blob, new_blob}]}`. The display numbers are the ones the writer allocates under the lock (Frozen P1 R8 §11), reproduced on P and held equal to the writer's by the display base check and the record check. At the freeze the same W, builders and planned-write computation give the committed basis of HEAD (§7.6) | same, three stages |
| reserved IDs | `ReservedIds`: roadmap, `key → Phase ID`, `index → relation ID` | `key → Work ID`, integration, confirmation, relation and Related IDs |
| expected scope | E: the registration paths (§14.1) with their transitions, modes and exact bytes | same |
| persisted scope | Kp's whole delta (`git diff-tree -r -z --no-renames --no-abbrev --raw P Kp`), compared with E by §15.7 (P3, CP5) | same |
| `load_persisted` | the Roadmap by ID, Phases by reserved ID in declared order, relations by reserved ID in declared order; a missing one is a mismatch | Works by reserved ID; Related and roadmap relations by reserved ID; each Work's `phase_id`, `origin`, `work_kind` and `confirmation_target` |
| `normalize_persisted` | §7.2 shape from `Entity.name` / `Entity.section`; a relation with extra fields is a mismatch | §7.3 shape; `condition` from `Relation.extra`, any other extra field is a mismatch; `canonical_first_work` from `startable_works` + `planned_next_preference` on the committed basis its caller names (§7.7) — the loaded view itself at the freeze, in P8/P9 and in CP6, HEAD's committed basis in the working-tree round trip — mapped back to its key |
| committed result loading | §15.4 | §15.4 |
| equality | two independent requirements: physical — Kp's delta is E (P3, CP5); semantic — projection identity with P5–P8, P10 and P12 (CP6, CP7) | same + P9 |

The same `normalize_persisted` runs at three points with three names: the representability check (§7.6, on the committed basis), the working-tree round trip (§15.1 step 2), and the persisted proof (§15.3, over the committed result). The adapter's responsibilities are those of the P1 protocol, whose exact Python names are an implementation detail (`review/adapter.py:83-111`): the view its R9 selection is computed on is an input its caller gives, and only the working-tree round trip gives one other than the loaded view.

`project_expected` and `normalize_persisted` serve two proof dimensions and are never collapsed into one. E proves bytes, paths and modes; the persisted semantic projection proves meaning, identity and, for Phase entry, the R9 selection. A byte-perfect Kp whose meaning differs fails the semantic side, and a meaning-perfect Kp whose bytes differ fails the physical side (Frozen P1 R8 §7, R9 §8).

## 21. Crash and recovery matrix

Terms (reconnaissance §12):

- **resume**: the same pending mutation continues from its record;
- **replay**: recorded effects are classified again and only unapplied ones are applied;
- **retry**: an external action is repeated under the same identity (the same task, the same exact push);
- **reconcile**: STOP with the record untouched;
- **recover**: a recovery planning mutation continues the same canonical Run (§12.4);
- **new Run**: a new planning mutation, new reserved IDs, a fresh Candidate and a new Run — only where §12.8 allows it;
- **terminal**: not authorized or stale (§19).

Where a row below says that a push is allowed or permitted, or that no barrier applies, it speaks of a Git at or above `P2_PUBLICATION_GIT_MIN`, or of a history the barrier's fast path clears. Below that minimum, a push of any other history is refused as a capability failure, which asserts no registration (§5.7, §18.7, row R10).

### 21.1 Runtime record intact

Baseline conditions for rows 1–38: the runtime record is intact, HEAD is on the bound branch, and nobody changed a written path. §21.2 covers runtime loss and fresh clones, §21.3 other conditions at any window; the variants follow §21.3.

| # | window | behaviour of the next same-request run |
| --- | --- | --- |
| 1 | planning mutation begun, domain IDs reserved, freeze incomplete | resume; freeze recomputed deterministically by the pre-freeze resume setup (§12.9: the same reservations). A STOP here abandons the planning mutation, begun or resumed (§12) |
| 2 | Run / task / Receipt / Consumption IDs reserved, `review_binding` noted, no generation mutation yet | resume; the pre-freeze resume setup runs §14.4 steps 1–6 again with the recorded reservations and binding; generation 1 starts; a STOP here still abandons, begun or resumed (no generation mutation has started) |
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
| 17 | use check passed and noted, registration stage not recorded | the use check runs again and notes `use_check_head` again; a registration path changed since the freeze, or an entity file added or removed in a display-allocating directory (§17 item 9), stops it with `dirty_overlap`, nothing written |
| 18 | registration effects partially applied | resume; `_open` projects and replays (live `refuse_invalid_phase_writes` / `refuse_invalid_work_writes` first); the subsequent stages continue from their records, and a stage not yet recorded only after the display base check (§15.7); the use check never runs again and `stale` is no longer an outcome (§13.4) |
| 19 | registration fully applied, round trip / pre-Kp proof not run, Kp not recorded | resume; the round trip runs; the pre-Kp currency proof on P = HEAD (§15.6), its physical projection item included: pass → Kp recorded with `base_head` = P and `base_exact`, and made; failure → `ReconcileRequired` with its §15.6 reason, nothing committed, no Consumption, pending |
| 20 | HEAD advanced after the use check (a disjoint-scope operation's commit in a crash window, or a person's) | the pre-Kp currency proof decides on the new HEAD: P descends from `use_check_head`, no commit since touched a planning-owned path, and currency holds on P → Kp is made on P; otherwise `ReconcileRequired` (`review_registration_base_moved` / `review_registration_currency_changed`), nothing committed |
| 21 | Kp recorded, not made | `_open`'s `refuse_recorded` classifies the recorded Kp first (§15.2). Unapplied (HEAD == P on the recorded branch) → the pre-Kp currency proof with P = the recorded `base_head`: it passes → the replay makes Kp on exactly P; it fails → `ReconcileRequired` with its reason, Kp not made. A mismatch (HEAD moved, the registration files not committed) → `ReconcileRequired` (`review_registration_base_moved`), Kp not made. `base_exact`: never the independent-advancement rule |
| 22 | Kp made, `commit_id` not saved | the live nothing-left-to-commit step classifies it applied, without an ID → reconcile (`review_commit_unowned`, §15.2); Kp can never be proven, so the publication barrier holds for every history holding it (row 25) |
| 23 | Kp made, `commit_id` saved, C-2(Kp) not run | the proof runs over the recorded Kp (P1–P12); the barrier holds for every history holding Kp until the committed planning proof proves Kp, its Consumption and Km for the commit being published (§18.7) |
| 24 | C-2(Kp) failed | reconcile (§15.5); no Consumption; every retry repeats the same proof; no generation 4; the barrier holds for every history holding Kp; no reset, rebase or amend |
| 25 | another Workline operation attempts a push while Kp is unproven (rows 22–24, 26–28) | `review_publication_barrier` (§18.7): its current-combined stage is not recorded (the mutation stays pending with its domain effects applied), or its recorded push is not classified unapplied / not applied; nothing is pushed and the destination never receives Kp; it continues once Km exists, the committed planning proof passes and Km is published (its commit then fast-forwards over Km, or is classified already published) — or, when Kp can no longer be proven, after a person reconciles the branch history |
| 26 | C-2(Kp) passed, Consumption not recorded | the proof runs again (the recorded Consumption effect is the operation's checkpoint); Consumption recorded |
| 27 | Consumption recorded, not applied (a single immutable create: absent or exact) | `_open` replay creates it; exact bytes already present → matching; anything else → reconcile |
| 28 | Consumption applied, Km not recorded / not made | Km recorded / made (live base rules, M1 bounding its parent); a Km without a saved ID → `review_commit_unowned` |
| 29 | Km made, C-2(Km) not run or failed | C-2(Km) — M1–M6 — runs; failure → reconcile (`review_metadata_commit_mismatch`), no push, and the barrier holds for every history holding Kp |
| 30 | C-2(Km) passed, `publication_proof` not noted | C-2(Km) runs again (the note is never assumed); note recorded |
| 31 | Km local, publication pending (note recorded, push stage not recorded) | C-2(Km) re-run; the barrier (the committed planning proof of every registered Run in Km's history) is evaluated; push stage recorded. The barrier holds only while that proof fails for some registered Run of Km's history — another Run's unproven registration commit: then `review_publication_barrier`, pending. Another operation's push from Km or a descendant may publish Km meanwhile, where the proof passes |
| 32 | push stage recorded, not applied | `_open` replay: planning validator (§18.4), dry run, barrier, exact push |
| 33 | pushed, `applied` not saved | dry run `=` → matching (nothing pushed; not a barrier point) |
| 34 | published, before `complete()` | everything matches; structure postcheck; complete |
| 35 | after `complete()` | record removed per the live rule; the same request again → discovery sets the consumed Run aside, and a new Run is begun (Roadmap creation: a second Roadmap, as in legacy; Phase entry: `phase_already_expanded` before discovery) |
| 36 | a person pushes Kp (or a descendant) by hand before Km | Workline cannot prevent it and never treats it as proof: the planning resume still runs C-2(Kp) over the local objects and writes the Consumption only if it passes; every Workline push of a history holding Kp stays refused until Km is committed and the committed planning proof passes (§18.7); if C-2(Kp) fails, row 24 |
| 37 | not authorized decided | terminal; after a crash before `complete()`, recomputed from the chain (after runtime loss: §21.2 row L6) |
| 38 | stale before a Receipt decided (rows 6, 10) | terminal; after a crash before `complete()`, recomputed (currency evaluated again: current → the flow goes on; stale → terminal); nothing to finish |

### 21.2 Runtime loss and fresh clones

**Frozen.** The runtime record is lost (a fresh clone, or `.workline/runtime/**` removed); a same-request review-v1 invocation runs discovery (§12.2). "Push allowed" says whether a Workline push may publish a history that holds this Run's commits. A fresh clone is the row of its committed state, with nothing uncommitted.

| # | lost after | same Run | same task | recovery planning mutation | new Run | publication barrier | push allowed | result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L1 | nothing of generation 1 committed (at most a snapshot or task input without its gate, a P1 legal orphan) | — (no Run) | — (none accepted) | no | yes | none | yes | a new Run; the freeze starts again |
| L2 | generation 1 committed, reviewer not called | yes | yes | yes | no | none | yes | current: the same task is launched from the stored TaskInput for the accepted reviewer only (§10.3), then generation 2. Stale: set aside, and a new Run |
| L3 | reviewer running, result only in memory | yes | yes | yes | no | none | yes | as L2: the same task is launched again |
| L4 | reviewer returned, runtime report copy written, generation 2 not written | yes | yes | yes | no | none | yes | as L2: the runtime copy is gone and was never settlement material |
| L5 | generation 2 committed | authorizing and current: yes; otherwise no | settled; never launched again | authorizing and current: yes | not authorizing (terminal) or stale (obsolete): yes; otherwise no | none | yes | authorizing and current: currency, then generation 3 with a newly reserved Receipt ID. Otherwise set aside with its class, and a new Run |
| L6 | generation 2 not authorizing, the planning mutation not completed | no | never launched again | no | yes | none | yes | the same canonical state as a completed not-authorized ending: set aside (`not_authorized`), and a new Run (§19.1) |
| L7 | generation 3 committed, no registration commit | yes | settled | yes | no | none | yes | recovered with the same Receipt into the use check: current → registration; stale → generation 4 and the Supersession, then `stale` |
| L8 | generation 4 committed | no (terminal) | — | no | yes | none | yes | set aside (`invalidated`), and a new Run |
| L9 | a half-written, applied-but-uncommitted or rewritten generation stage, or a generation mutation left pending | no | no | no | no | none (nothing registered) | yes | `ReconcileRequired` (`review_recovery_incomplete`); never hidden by a new Run; once a person has reconciled the records, discovery reads the Run's committed state again |
| L10 | registration applied to the working tree only (generation 3 committed, no registration commit) | yes | settled | yes | no | none (no registration commit) | yes | the call stops with nothing written — Roadmap creation at the recovered-reservation binding (`review_recovery_reservation_conflict`, §12.5), Phase entry at the live `phase_already_expanded` precheck — until a person discards the uncommitted files; then as L7 |
| L11 | Kp made, C-2(Kp) not run | no | — | no | no | holds | no | Roadmap creation: `ReconcileRequired` (`review_recovery_incomplete`, §12.2 row b); Phase entry: the live `phase_already_expanded` before discovery (§5.6 step 6). The operation's C-2(Kp) can never run again (Kp's ID lived only in the lost record, §15.2), so no Consumption is written; no recovery adopts Kp, the committed planning proof fails for want of a Consumption (CP8), and a person reconciles the branch history |
| L12 | C-2(Kp) passed, Consumption not recorded | no | — | no | no | holds | no | as L11 |
| L13 | Consumption written (working tree), Km not made | no | — | no | no | holds (no committed Consumption) | no | Roadmap creation: `ReconcileRequired` (`review_recovery_incomplete`), the uncommitted Consumption also failing clean persistence (§12.3); Phase entry: `phase_already_expanded` before discovery |
| L14 | Km made, C-2(Km) not run or not noted | no | — | no | only if the proof passes (then per the live Roadmap rules) | decided by the committed planning proof at each push | where the proof passes | Roadmap creation: the proof passes → terminal `consumed` (the same request is then a new Run, a second Roadmap as in legacy), and the next Workline push from the branch publishes Km; it fails → `ReconcileRequired` (`review_recovery_incomplete`), and the barrier holds. Phase entry: `phase_already_expanded` before discovery; the barrier decides every push as for Roadmap creation |
| L15 | C-2(Km) passed, push not made | no | — | no | as L14 | as L14: the lost `publication_proof` note is never assumed; every push re-runs the proof over the same immutable objects | where the proof passes | as L14 |
| L16 | Km published | no | — | no | per the live Roadmap rules | re-run at each subsequent push; passes | yes | terminal `consumed` (Phase entry: `phase_already_expanded` before discovery) |
| L17 | fresh clone, safe checkout semantics (the checked-out commit carries the canonical rule as the last attribute rule of its root `.gitattributes` and no `.gitattributes` below `.workline/`; no clone-local `info/attributes` rule and no attribute-source redirect, §14.5) | per its committed state | per its committed state | per its committed state | per its committed state | the same answer from the same objects | as the barrier says | every Review record checks out as its canonical LF bytes (**Measured**, §14.5); discovery and recovery read them as in L1–L16 |
| L18 | fresh clone, unsafe checkout semantics (the checked-out commit lacks that configuration, or the clone adds an `info/attributes` override or an attribute-source redirect) | no | no | no | no | unaffected (it reads raw blobs) | as the barrier says | a review-v1 call stops at discovery's first step with `review_namespace_unreadable` (§12.2 step 1) or, at the freeze or the recovery setup, with `review_checkout_unsafe`; nothing is normalized (P1 unchanged); legacy operations are unaffected |

A new Run never makes an unproven registration commit publishable: the barrier reads the history, not the Run a call happens to continue (§18.7). The committed planning proof every push runs includes the exact physical projection (CP5), recomputed from the committed Candidate snapshot, P's tree and the Run's adapter (§15.7): after runtime loss after Kp or Km, and in a fresh clone, a Kp whose bytes are not E stays unpublishable; recovery never bypasses the check, and a new Run never makes such a Kp publishable. Every registration after recovery writes from W computed from the committed snapshot (§7.8), exactly as an uninterrupted run would.

### 21.3 Other conditions, at any window

| # | condition | behaviour |
| --- | --- | --- |
| O1 | branch changed | reconcile (binding §11.5: `review_binding_moved`; live `_require_decided_branch` / `_require_finalized_branch`, reason `None`); checking out the bound branch continues |
| O2 | remote moved | live push classification: destination holds Km → matching; another history → reconcile, never forced; a push that would write is also held to the barrier |
| O3 | canonical Review record tampered | reconcile: `create_file` applied_mismatch, `ReviewStore` refusal, a blob / M4 / P12 mismatch, or a committed planning proof failure; never re-reviewed or repaired |
| O4 | pre-existing dirty path | refused at the freeze or the recovery setup with `dirty_overlap`, the planning mutation abandoned, nothing written (§14.2); a change after the freeze on a written path → live own-bytes reconcile |
| O5 | POSIX with review-v1 | `review_create_unsupported` before the lock; nothing exists |
| O6 | checkout capability missing or lost | at the freeze or recovery setup: `review_checkout_unsafe`, planning abandoned, nothing written; after the first generation mutation (the rule removed while pending): the next Review-writing or Git stage stops, the planning mutation stays pending, and continues once the rule is back |
| O7 | several recoverable matching Runs | `ReconcileRequired` (`review_recovery_ambiguous`), nothing begun; no Run is chosen by age, ID order or position |
| O8 | a legacy invocation of the same request after runtime loss | the live path, unchanged: discovery never runs for a legacy invocation |
| O9 | a Kp — the planning mutation's own or anyone's — whose bytes are not the expected physical projection although its meaning is the reviewed one | the planning mutation's own: C-2(Kp) P3 fails, `ReconcileRequired` (`review_persisted_proof_failed`), no Consumption (§15.5); anyone's: never adopted; for every history holding it the barrier holds (CP5), before and after runtime loss and in a fresh clone |
| O10 | a review-v1 caller value the canonical form cannot carry (a float, a tuple, a non-text or empty mapping key, a sequence inside a sequence, a lone surrogate) | `review_candidate_unrepresentable` from the canonical-input preflight before `_open`: no planning mutation, reservation, Review record, domain effect or runtime file; a pending planning mutation of the slot untouched; before recovery discovery, so a recoverable Run stays as it is (§5.6) |

Variants at any row: a different request or design → `reconcile_required` (live); a legacy invocation against a review-v1 record, or the reverse → `reconcile_required` (`review_marker_mismatch`, §5.3); a pending generation mutation bound to another planning mutation → reconcile (`review_generation_owner_conflict`, §11.8); structure changed by an independent operation while pending → the live projected refusal (`postcheck_failed`) before replay; the parent Roadmap held while a Phase entry is pending → the live Phase-entry precheck STOP, continued after resume; that hold committed after the use check → the pre-Kp currency proof decides (a declared-base difference is `ReconcileRequired`, §13.4).

### 21.4 Windows and conditions of the final readiness repair

**Frozen** (P2-READY-001..004, P2-READY-027, P2-READY-029). The rows below are keyed R1–R10; "none of its own" means no canonical Run begun by that mutation.

| # | window | pending mutation | canonical Run | same mutation resumed | discovery run again | abandoned | ReconcileRequired | Review record written | domain effect | push permitted | outcome |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | crash after `_open` (`MutationController.begin` saved), before the `recovery_discovery` note; new Run | yes, without the note | none of its own; matching Runs untouched | yes (§5.3) | yes (§12.9) | only on a STOP of the setup | only when discovery answers differently: `review_discovery_changed` (a Run became recoverable), `review_recovery_ambiguous`, `review_recovery_incomplete` | none before generation 1 | none | yes: nothing of it is committed | the note recorded on the same mutation, then the freeze (§28 Q-A); after `review_discovery_changed`, the next invocation recovers the Run (§28 Q-C) |
| R2 | crash after the `recovery_discovery` note, before the first reservation | yes | none of its own | yes | no: the note is kept | only on a STOP | no | none | none | yes | the freeze from its step 1 |
| R3 | crash after some reservations, before the Candidate or generation 1 | yes | none of its own | yes | no | only on a STOP | only a recorded key the order does not reserve (`review_setup_invalid`) or a wrong-kind ID (live `reserve_id`, reason `None`) | none | none | yes | the recorded reservations reused, the missing ones reserved in order (§28 Q-B) |
| R4 | resumed recovery planning mutation before its recovered binding | yes, with `recovery_of_review_run_id`, without `recovery_binding` | yes: the named Run | yes | yes (§12.9) | only on a STOP | `review_discovery_changed` when the Run is no longer the one recoverable Run; `review_recovery_reservation_conflict` for a reservation without a binding | none written by it | none | yes | bound into the same mutation, then its setup (§28 Q-D) |
| R5 | a STOP in a resumed setup before generation 1 | yes, then abandoned | as R1–R4 | yes | as R1–R4 | yes: begun or resumed, a Phase entry included | as its cause | none | none | yes | the next same-request invocation starts again at §5.6 step 5 (§28 Q-E) |
| R6 | no pending mutation; the Phase already expanded (a consumed Run, or a registration commit, in history) | no | yes: historical | — | no | — | no: `StopError` `phase_already_expanded` | none | none | as the barrier says (§18.7) | the live refusal before discovery (§28 R-A) |
| R7 | the working tree and HEAD give a different declared base, Work set of the Phase or R9 selection at the freeze | yes, begun or resumed | none of its own | — | — | yes | no: `ValidationError` `review_base_uncommitted` | none | none | yes | commit or discard the change and run again (§28 P-B, P-C) |
| R8 | a layer of the checkout capability fails (§14.5): the root `.gitattributes` does not end with the canonical rule (no rule, `-text`, `text=unset`, `text=unspecified`, `filter=unset`, `ident=unset`, `working-tree-encoding=unset`, `eol=crlf`, an attribute rule after it), a `.gitattributes` below `.workline/`, an evaluation that does not print form L (an `info/attributes` override, an attribute-source redirect), or a filter driver named `unset` configured | at the freeze or the recovery setup: yes; after generation 1: yes, and it stays | — | — | — | at the freeze or the recovery setup: yes; after generation 1: no (§21.3 O6) | no: `StopError` `review_checkout_unsafe` (`review_checkout_unknown` when an object or Git cannot answer) | none | none | yes | commit the canonical rule as the root file's last attribute rule, remove the deeper file or the local override, and run again (§28 J) |
| R9 | an explicit review-v1 invocation on a Git older than `P2_REVIEW_GIT_MIN` (2.40.0), or whose version text does not parse | review-v1: none begun (stopped before the lock); a pending one untouched | untouched | — | no | no | no: `StopError` `review_git_unsupported` | none | none | as R10 says for the running Git | run with Git 2.40.0 or newer (§28 S) |
| R10 | a Workline push on a Git older than `P2_PUBLICATION_GIT_MIN` (2.31.0), or whose version text does not parse | the pushing operation's, pending where §18.7 says | untouched | — | no | no | no: a history the fast path clears publishes; for any other history `StopError` `review_publication_barrier`, the proof unavailable, naming no Run and no registration commit | none | the pushing operation's own, as §18.7 says | only for a history the fast path clears | run the push with Git 2.31.0 or newer, where a Run that registered nothing begins no barrier (§28 S) |

Nothing in the matrix is the P3 Work-terminal recovery contract.

## 22. Lifecycle separation

**Frozen** invariants:

1. `state.py`, `ProjectView`, `validate_structure`, Phase selection, Work selection, startability and Roadmap progression never read a Receipt, Consumption, gate generation, Supersession, snapshot or task input. `state.py` stays byte-identical, and the existing pin `test_review_authority` (no "review" in `state.py`) holds.
2. A review-v1 planning operation takes authorization only from its own Run's records. Recovery discovery reads the invocation's matching Runs only to classify them (§12.2); the uniqueness indexes (§16.3) and the publication barrier (§18.7) read other Runs' records only for their own refusals.
3. There is no cross-operation Review precondition. For example, "Phase entry requires the Roadmap to possess Receipt X" is prohibited: a PhaseEntryDesign Review reviews its own design, whatever the Roadmap's history. The publication barrier (§18.7) is not such a precondition: it asks no operation for a Review or a Receipt, and only keeps a review-v1 registration the committed planning proof cannot prove out of what a push publishes. Recovery discovery (§12.2) reads only the invocation's own matching Runs.
4. The R9 canonical first Work is computed from `ProjectView` on the committed basis (§7.7), never from a Review record and never from the working tree.
5. A broken Review record stops a review-v1 planning operation that relies on it. It cannot reinterpret lifecycle history, because nothing that derives lifecycle reads it.
6. The committed-result loader (§15.4) feeds only the freeze's committed basis and working-tree compatibility check (§7.4, §7.6), recovery discovery (§12.2), the proofs, the currency evaluations (§13) and the base of the expected physical projection (§15.7); its `ProjectView` and the projection's scratch directory are never used to decide lifecycle or progression.
7. A review-v1 Roadmap creation or Phase entry writes no event, so the lifecycle it leaves is identical to a legacy call's (Measured, reconnaissance probes 2, 5, 8).
8. The publication barrier (§18.7) reads Review records and history only to decide whether a push may publish. It derives no lifecycle and changes no lifecycle fact: a legacy operation it holds back has applied exactly the effects it would have applied, and only its commit and push wait.
9. Generation 4 and the Supersession (§13.3) are authorization records only: invalidating a Receipt changes no Work, Phase or Roadmap state, and nothing that derives lifecycle reads them.
10. Canonical recovery discovery (§12.2) and the committed planning proof (§18.8) read Review records only to decide which Run an already gated call continues and what a push may publish. They derive no lifecycle and change none; a recovered Run changes no lifecycle fact until its registration does, exactly as the original Run would have.
11. W (§7.8) is writer input only: computed from the Candidate, it is read by nothing that derives lifecycle and states nothing the Candidate does not already state.

P3 stays inactive: no activation record, no Work-terminal Consumption, no START change.

## 23. P1 seam disposition

| seam | frozen P1 text | disposition |
| --- | --- | --- |
| C-1 publication discriminator scope | R5 §12.3.1: Review-v1 durable metadata without `publication_contract` fails closed; R5 §12 enumerates two shapes for the operations it governs | **CLOSED BY P2 CONTRACT.** The planning mutation's durable invocation carries `publication_contract = review-v1-planning-publication-v1` from `begin` (R5-IMPL-2 satisfied). P2 implements the discriminator's first branches (§18.5): legacy → current-combined unchanged, planning → planning publication, generation mutations never publish, anything else fails closed. R5 §12.1 / §12.2 are unchanged; R5's `review-v1-split-v1` remains P3's |
| C-2 planning Consumption binding | R8 §8, R9 §9 | **CLOSED BY P2 CONTRACT.** Planning Consumption v2 with `persisted_result` (§16), written after C-2(Kp), stored in Km, binding Kp without self-reference; its `registration_delta_digest` is the digest of the proven expected physical projection (§15.7) |
| C-3 persisted proof / publication ordering | R8 §5–§9, R9 §7–§10, Candidate 7 §4.4 / §11 | **CLOSED BY P2 CONTRACT.** Direction A (§15, §17, §18), with the round-1 repair (the cross-operation publication barrier, the use-check head, the base-exact Kp and full currency on Kp's parent, §15.2, §15.3 P12, §15.6) and the round-2 repair: C-2(Km) is a reproducible proof over committed objects, and the barrier clears only when the committed planning proof passes (§18.2, §18.7, §18.8); and the round-3 repair: Kp must be exactly the expected physical projection on its parent, proven with one computation by the pre-Kp proof, C-2(Kp) P3 and CP5, beside the semantic proof (§15.7) |
| C-4 generation mutation / same-run serialization | R2 §4, R3 §2, §8 | **CLOSED BY P2 CONTRACT.** Direction A (§11), R2/R3 and the helper unchanged; abandonment gap closed (§12); the R3 §8 invalidation generation is generation mutation 4 under the same serialization (§11.6, §13.3) |
| C-5 owning mutation invocation binding | R3 §9 | **CLOSED BY P2 CONTRACT.** The planning invocation keeps the request identity and adds the two static markers (§5.2). Run / task / Receipt / Consumption IDs are planning reservations (§6.3). Each generation invocation binds run, generation, transition, Candidate / Context / Policy, obligation digest, Receipt ID and, for an invalidation, its reason (§11.2). The planning mutation binds the Receipt, Candidate, Context and obligation through its recorded Consumption effect and `persisted_result`. `proof_phase` (Candidate 6 §11) is the planning mutation's recorded stage position plus the `publication_proof` note, re-checked before recording the registration and the push; the note is a runtime sequencing marker, and the durable proof basis of C-2(Km) is the committed objects (§18.2). A recovery planning mutation adds one key, `recovery_of_review_run_id` (§12.4), and its generation invocations bind the canonical Run's identities with its own mutation ID (§11.2) |
| C-6 runtime-loss same-task / Run rerun | R2 §5, R3 §4, R12 §4 | **CLOSED BY P2 CONTRACT** (round 2). The accepted task material is canonical and survives runtime loss (snapshot, task input, generations). Recovery discovery runs before any new Run is reserved (§12.2). The exact Run, Candidate and TaskInput are reconstructed and every provenance digest is recomputed (§12.3). The same `task_id` is launched again, or its settlement continued (§12.7). The exact domain reservation map is bound from the snapshot, with no substitute ID (§12.5, §12.6). Malformed, incomplete or ambiguous recovery fails closed (`ReconcileRequired`), and a half-written generation is never hidden by a new Run (§12.3). A new Run is begun only when no Run is recoverable (§12.8). Runtime loss §21.2 |

Every seam is closed.

## 24. Consistency with frozen P1 contracts and Candidate 7

| frozen text | how P2 satisfies it |
| --- | --- |
| R1 §2–§8 layout, immutable create | no new directory. Planning Consumption v2 in `consumptions/`, the Supersession in `supersessions/`; runtime material in `.workline/runtime/review/` (proofs, reports, no-hooks, attr-eval), allowed by R1 §3 |
| R1 §3 runtime data is never authorization; what decides consumability or reconstructs an accepted task must come from canonical records plus canonical Git state | the publication barrier, the committed planning proof, recovery discovery and reconstruction, the currency evaluations and every proof read committed objects; nothing in `.workline/runtime/` decides (§12, §13, §18.7, §18.8) |
| R1 §4 "Git persistence proof separately proves the committed path reproduces those bytes under the Git semantics bound by R6" | blob checks at every generation commit, M4, P3 and P4 (§15.7), P12; and the checkout capability (§14.5), which proves positively — from HEAD's raw committed `.gitattributes`, with the committed and effective evaluations as cross-checks (P2-READY-004) — that the committed path reproduces the canonical bytes in this working tree and in a fresh clone; the strict reader (P1-REV-007) is unchanged |
| R1 §13 committability | `gate.require_committable` at the freeze and per writer |
| R2 §2–§4 | keys §6.2; reservations §6.3; a recovered Run keeps its keys and canonical IDs; a value that never became canonical is reserved anew under the same key (§12.6) |
| R2 §5: "A later clone resumes the same logical accepted task only when canonical task input reconstructs an exact request/Candidate whose digests and bound adapter identities match the accepted record. It never silently allocates a replacement task ID for missing accepted material." | recovery discovery and reconstruction (§12.2, §12.3); the same `task_id` is launched again (§12.7); missing or mismatching material → `ReconcileRequired`, never a new task |
| R3 §1 ownership | Roadmap mutation owner writes every record (§11.1) |
| R3 §2 serialization | §11.3, §11.8, helper unchanged; generation 4 included |
| R3 §3 launch after local persistence | §10.3, for the original launch and for the relaunch after recovery |
| R3 §4 fresh clone / runtime loss rerun the same task_id after exact reconstruction; fail closed otherwise | §12.2–§12.7 |
| R3 §5 provenance identities | reconstruction checks `candidate_material_digest`, `task_input_digest` and every shared identity (§12.3, CP3) |
| R3 §6 full snapshot | every generation, generation 4 included (§11.6.1) |
| R3 §7 seal + Receipt one stage | §11.6 |
| R3 §8 invalidation | a stale sealed Receipt is invalidated before the planning mutation ends: generation 4 (`open`) and the Supersession in one stage, committed and persisted; the old Receipt never proceeds and is never consumed (§13.3). No Supersession without a Receipt (§13.2) |
| R3 §9 invocation binding | C-5; a recovery planning mutation's generation invocations bind the canonical Run's identities with the recovery planning mutation's ID (§11.2, §12.4) — R3 §9 names what the owning mutation binds, not one mutation per Run |
| R3 §10 local Git persistence boundary | §11.6; remote-less valid |
| R3 §11, Candidate 7 §2 no second controller | §22 |
| R4 §1, §7 uniqueness | §16.3 |
| R5 §3.2 "complete base->K tree delta == expected projection"; tree proof including content / object identity, mode, symlink / gitlink | for Kp, the planning analogue: the comparison of §15.7 — path set, transitions, modes and raw blob bytes against E; a symlink, gitlink or executable fails (P3, CP5) |
| R5 §5–§6 signing disabled, hooks suppressed as bound semantics | §15.2, Context `git_persistence` |
| R5 §12 publication shapes | §18: current-combined unchanged; planning shape separately named and selected by durable metadata, never by shape. R5 §12's "exactly two" enumerates the contracts of the operations R5 governs; P2 adds one R5 did not govern and changes none of R5's |
| R5 §12.1 "not weakened, narrowed or made conditional" | every check of `_recorded_publication` stays as it is; the publication barrier (§18.7) is a separate refusal evaluated after the commit is named, never a substitute for any check; in a history without a planning Candidate snapshot it refuses nothing, and on a Git at or above `P2_PUBLICATION_GIT_MIN` nothing in a history without a planning registration commit |
| R5 §12.5 "push already occurred but C-2 is absent → NEVER infer proof from push" | the barrier never reads the destination; a destination already holding a commit only means nothing is pushed for it (§18.7); a person's push of Kp is never proof (§15.5) |
| R6 §6, R11 §10 attributes and line-ending semantics as bound Git semantics | the checkout capability contract is bound in the Context (`checkout_capability`, §8, §14.5) |
| R8 §5 expected canonical projection: entity bytes from the writer's rendering functions, exact relation records, whole-ledger physical results; Phase CREATE rendering never reimplemented | E (§15.7), from W and the writer's own builders and planned-write computation on Kp's parent — the Candidate is mapped to writer inputs once, by W (§7.8); §20 |
| R8 §6–§7 semantic reconstruction; PASS needs semantic equality and the exact commit-delta projection proof | semantic: P5–P9, CP6, CP7; physical: P3, CP5; each required on its own (§15.3, §18.8, §20) |
| R8 §11 display numbers decided by the writer under the lock, then proven after write | the writer allocates them; the display base check (§15.7, §17 item 9) keeps its count equal to P's; E reproduces them on P, and pre-Kp item 6, P3 and CP5 prove them |
| R8 §2–§4, §8–§10 | §7.2, §15.3, §16, §20 |
| R9 §6, §8 expected effects from the canonical WorkSpec / render / registration helpers, no second hand-coded renderer; the exact physical commit-delta proof | E for the three Work stages, fed by W (§7.8, §15.7), P3, CP5; the R9 self-selection stays an additional semantic check (P9, CP6) and never replaces the byte proof |
| R9 §2–§11 (as repaired) | §7.3, §7.7, §15.3 P9, §16, §20 |
| R9 §4, §11 `entry` is no persisted plan meaning | `entry` is not part of W; the Candidate's `canonical_first_work` stands for its meaning (§7.7, §7.8) |
| R8 §9, R9 §10 recovery reuses reservations and recorded registration effects | a recorded stage is carried forward from its record; a stage not yet recorded is written from W with the Candidate's reserved IDs, after runtime loss exactly as before it (§7.8, §12.4) |
| P1 canonical serialization (`review/serialize.py`: mapping keys in ascending code point order at every depth, sequences in their order; `parse_canonical` reads only that rendering) | the Candidate records a caller's mapping in that form, and W hands the writer the same form — from `canonical_data` before the snapshot is written, from the strict reader afterwards: the same data in the same order (§7.3, §7.8); the canonical-input preflight checks the request identity with the same functions before `_open` and adds no serializer of its own (§5.6) |
| R11 git_state, completeness | the primitive identity is bound; Evidence completeness `unknown`, never reused |
| R12 §2 "clone reproduces canonical bytes/digest" | §14.5; tests §28 J |
| R12 §4 fresh clone / runtime deletion reconstructs the exact Candidate and request and reruns the same `task_id`; negative cases fail closed | §12; tests §28 L |
| R12 §5 invalidation partial stage | §21.1 rows 13–16; tests §28 B |
| R5 §1.1 C-2 durable, keyed by exact commit identity, complete before the push, never reconstructed from a push | C-2(Km)'s durable basis is the committed objects the committed planning proof reads, keyed by Kp and Km (§18.2); the push stage is recorded only after it passes, and every push re-runs it (§18.4, §18.7) |
| R5 §12.4–§12.5 S-c / C-2 / S-p bindings; C-2 never inferred from a push; superseded authorization fails closed | the planning shape's own analogue (§18): Kp / Km commit stages, C-2 by committed proof, the push stage of exact Km; a destination holding Kp or Km is never proof; a Supersession fails CP2 / CP4 / CP13 |
| R12 §3, §8, §11, §13, §14 | test contract §28 (the R8 / R9 fault injection of §11: D, E and M) |
| Candidate 7 §4.4 exact union | Kp proof: ReviewedArtifact + AuthorizedTransition + scope; Km proof: OperationMetadata + scope |
| Candidate 7 §11 local commit → exact proof → re-read | §15 |

No frozen P1 document needs repair for this contract. P2-CONTRACT-004 in particular closes as a P2 capability precondition: the P1 reader keeps refusing non-canonical physical bytes, and R1 §4 with R6 §6 already make the checkout semantics of Review paths part of the Git semantics a persistence proof is under; P2 proves them positively before it writes.

## 25. Public API compatibility

**Frozen.**

| surface | P2 |
| --- | --- |
| `create_roadmap` | new keyword-only `review=None`; legacy unchanged; review-v1 returns `ReviewedPlanningResult` |
| `enter_phase` | same |
| a review-v1 caller value the canonical form cannot carry | `ValidationError(code="review_candidate_unrepresentable")` before `_open`: no planning mutation, reservation, Review record, domain effect or runtime file, and a pending planning mutation untouched (§5.6); a condition the live `validate_condition` refuses keeps its live `validation_failed` refusal, now before `_open`; legacy keeps its live outcome, serializer errors included (§29 item 7) |
| caller `RoadmapPlan` / `PhaseEntryDesign` | unchanged types; on the review-v1 path they validate the invocation, build the Candidate and give the request identity, and after the freeze the writer receives W (§7.8); the legacy path passes them to the writer as today |
| `RoadmapResult`, `PhaseEntryResult`, `OperationResult` | unchanged |
| new result type | `ReviewedPlanningResult` (`workline.roadmap_review`) |
| `Mutation` public methods | unchanged set (pin `test_project_start_recovery.py:978-991`) |
| `MutationController` public methods | unchanged set (same pin) |
| `ReconcileRequired` (`errors.py:38-42`) | gains one keyword-only attribute, `reason` (text or `None`, default `None`), stored as `.reason` (P2-READY-005). `.code` stays `reconcile_required`, and every existing construction keeps working with `reason` `None`. P2 sets `reason` on every `ReconcileRequired` it raises (§25.1), and tests assert `.reason`, never a substitute code |
| `EFFECT_KINDS`, `INTENT_VERSION` | unchanged (pins `test_decision_branch_binding.py:676`, `test_cancel_decision_resume.py:367`) |
| effect payloads | `git_commit` gains the durable `mode` field (§15.2) and, for Kp only, `base_exact: true`; a planning `git_push` gains `commit` (§18.4); `validate_effect` accepts `mode` only as `review-v1-planning-local-v1`, `base_exact` only as `true` together with that `mode`, a full-ID `base_head` and a `branch`, and `commit` only as a full commit ID; legacy payloads are unchanged |
| `gitops.finalize` | unchanged signature and stages; before recording a stage that holds a push it evaluates the publication barrier on HEAD (§18.7), which refuses nothing in a history without a planning Candidate snapshot, and on a Git at or above `P2_PUBLICATION_GIT_MIN` nothing in a history without a planning registration commit |
| codes and reasons | every STOP code and `ReconcileRequired` reason P2 uses, with its carrier, where it is raised and the state it leaves: the catalogue of §25.1. Only `review_publication_barrier` concerns legacy operations, and only when a published history holds a planning Candidate snapshot (§18.7) |
| Git versions | an explicit review-v1 invocation on a Git older than `P2_REVIEW_GIT_MIN` (2.40.0), or with a version text that does not parse, stops with `review_git_unsupported` before the lock; a Workline push on a Git older than `P2_PUBLICATION_GIT_MIN` (2.31.0), or of unknown version, of a history the barrier's fast path does not clear is refused with `review_publication_barrier`, the proof unavailable (§5.7, §18.7); legacy invocations run no version gate |
| planning invocation | one additional key, `recovery_of_review_run_id`, only on a recovery planning mutation (§12.4); the request identity and the two markers unchanged |
| request envelope | gains `set_aside_runs` (§10.2) |
| recovered reservations | a private module-level helper of `mutation.py` (§12.5), also callable on a resumed recovery planning mutation that has not bound yet (§12.9); no `Mutation` method, no public API accepting IDs |
| `register_phases`, `register_works` | unchanged signatures, stage names and keys; the review-v1 path pre-reserves under their keys |
| `phase_create.decide_phases`, `MutationController._planned_write` | unchanged behaviour and signatures; their effect building and planned-write computation become pure functions they call themselves, shared with the expected physical projection (§15.7, §20) |
| `rm.validate_structure` call order in Phase entry | unchanged: the review-v1 checks call `workline.validate` from `workline.roadmap_review`, never through `rm.validate_structure` (pin `test_phase_entry_contract.py:529-555`) |
| `OPERATION_LEDGERS` / `_ledgers` | unchanged: generation mutations build their scope from the helper, never through `_ledgers` (pin `test_declared_write_scope.py:162-191`) |
| `ROADMAP_REQUEST_VERSION`, `DESIGN_IDENTITY_VERSION` | unchanged |
| `project_operation` signature | unchanged (pin `test_self_hosting_guard.py:603`) |
| entry parameters | no parameter name contains `foreign` or `allow` (pin `test_project_context.py:478`) |
| Review P1 record classes | unchanged; Consumption gains version 2 alongside version 1 |

No `Mutation` or `MutationController` method is added. New behaviour lives in module-level helpers (`gitops`, `gitcmd`), the new modules, private functions of `mutation.py`, and the one `reason` attribute of `ReconcileRequired`.

### 25.1 Error and reason catalogue

**Frozen** (P2-READY-005). The carrier of each meaning is fixed:
- a `StopError`, or its subclass `ValidationError`, carries its meaning in `code`;
- a `ReconcileRequired` keeps `code == "reconcile_required"` and carries its P2 meaning in `reason`;
- a `ReconcileRequired` that live code raises on the review-v1 path keeps `reason` `None` and its live message, as in legacy — the same-request mismatch, a scope overlap in `MutationController.open`, a `reserve_id` kind mismatch, the live branch binding, a live replay or push-classification mismatch;
- the stale reasons are not exceptions: they are the `detail` of a `stale` result, the `reason` of a Supersession and of a generation-4 invocation, and a set-aside `reason` (§10.2, §11.6.1, §19.2).

Every code and reason the contract uses is in this table, and every `ReconcileRequired` P2 raises names one reason of it.

| code or reason | carrier | raised at | state it leaves |
| --- | --- | --- | --- |
| `review_contract_invalid` | `ValidationError` code | §5.1, before the lock | nothing read or written |
| `review_create_unsupported` | `StopError` code | §5.4, before the lock | nothing begun |
| `review_git_unsupported` | `StopError` code | §5.7, before the lock: an explicit review-v1 invocation on a Git below `P2_REVIEW_GIT_MIN` or of unknown version; never a push | nothing begun; a pending planning mutation untouched |
| `review_candidate_unrepresentable` | `ValidationError` code | the preflight before `_open` (§5.6); §7.6 after `_open` — the detail says which | before `_open`: nothing begun; after: the planning mutation abandoned |
| `review_base_uncommitted` | `ValidationError` code | the working-tree compatibility check at the freeze (§7.4) | the planning mutation abandoned |
| `review_entry_not_canonical`, `review_entry_ambiguous` | `StopError` code | §7.7, at the freeze | the planning mutation abandoned |
| `review_context_unavailable` | `StopError` code | §8: at discovery, at the freeze, at every recomputation | discovery: nothing begun; freeze: abandoned; afterwards: pending |
| `review_reviewer_failed`, `review_report_invalid`, `review_reviewer_mismatch` | `StopError` code | §10.3, §10.4 | pending; nothing settled |
| `review_git_transform` | `StopError` code | §14.3 | freeze: abandoned; afterwards: pending |
| `review_checkout_unsafe`, `review_checkout_unknown` | `StopError` code | §14.5 | freeze or recovery setup: abandoned; afterwards: pending |
| `review_namespace_unreadable` | `StopError` code | §14.6 | discovery: nothing begun; freeze or recovery setup: abandoned |
| `review_hooks_path_invalid` | `StopError` code | §15.2, before a Git stage | pending |
| `review_publication_barrier` | `StopError` code | §18.7: an unproven registration, the detail naming the Run's `candidate_hash`, its registration commit and the first failing item; or the proof unavailable on a Git below `P2_PUBLICATION_GIT_MIN` or of unknown version, the detail saying so and naming no Run | freeze or recovery setup: abandoned; `gitops.finalize`: the stage not recorded, the mutation pending with its domain effects applied; a push point: nothing pushed |
| `review_marker_mismatch` | `ReconcileRequired` reason | §5.3, before `_open` | the pending record untouched |
| `review_recovery_incomplete` | `ReconcileRequired` reason | §12.2 step 3, rows b, e and f; §12.9 | nothing begun; in §12.9 the mutation abandoned |
| `review_recovery_ambiguous` | `ReconcileRequired` reason | §12.2 step 5; §12.9 | the same |
| `review_discovery_changed` | `ReconcileRequired` reason | §12.4 binding; §12.9 | the planning mutation abandoned; the next invocation discovers again |
| `review_recovery_reservation_conflict` | `ReconcileRequired` reason | §12.4, §12.5, §12.9 | the recovery planning mutation abandoned (before its first generation mutation) |
| `review_setup_invalid` | `ReconcileRequired` reason | §12.9 | the planning mutation abandoned |
| `review_binding_moved` | `ReconcileRequired` reason | §11.5, §10.3, §17 item 5 | pending; nothing replayed, recorded, committed or pushed |
| `review_chain_invalid` | `ReconcileRequired` reason | §10.3, §11.6, §11.8 steps 3–4 | pending |
| `review_task_invalid` | `ReconcileRequired` reason | §10.3: provenance or envelope digests of the accepted task | pending; no reviewer call |
| `review_generation_owner_conflict` | `ReconcileRequired` reason | §11.8 step 3, §11.10 | pending |
| `review_candidate_mismatch` | `ReconcileRequired` reason | §13 item 4 at the reviewer launch, at the starts of generation mutations 2 and 3, at the use check and in the pre-Kp proof; §7.1 | pending |
| `review_receipt_invalid` | `ReconcileRequired` reason | §17 items 1–4; §15.6 items 3–4 | pending |
| `review_registration_base_moved` | `ReconcileRequired` reason | §15.2 (a Kp classified a mismatch; HEAD read again before `git commit`); §15.6 items 1–2 | pending; no Kp made |
| `review_registration_currency_changed` | `ReconcileRequired` reason | §15.6 item 5, a stale difference | pending; no Kp made |
| `review_registration_projection_mismatch` | `ReconcileRequired` reason | §15.6 item 6 | pending; no Kp made |
| `review_commit_unowned` | `ReconcileRequired` reason | §15.2 | pending; the barrier holds for Kp |
| `review_persisted_proof_failed` | `ReconcileRequired` reason | §15.3 | pending; no Consumption; the barrier holds |
| `review_metadata_commit_mismatch` | `ReconcileRequired` reason | §18.2 | pending; no push; Km local |
| `review_publication_invalid` | `ReconcileRequired` reason | §18.4 | pending; nothing pushed |
| `review_publication_contract_invalid` | `ReconcileRequired` reason | §18.5 | pending; nothing pushed |
| `review_context_changed`, `review_policy_changed`, `review_declared_base_changed` | no exception: a stale reason | §13 items 1–3 | terminal `stale` (§13.2, §13.3), or set aside at discovery (§12.2 row f) |
| `invalidated`, `consumed`, `not_authorized`, `set_aside` | no exception: a set-aside reason | §12.2 | recorded in the next Run's `set_aside_runs` |
| `validation_failed`, `postcheck_failed`, `structure_invalid` | `ValidationError` code (live, meaning unchanged) | the live refusals; the preflight's `validate_condition` (§5.6); §7.6 step 3 | before `_open`: nothing begun; at the freeze: abandoned; after generation 1: pending |
| `dirty_overlap` | `StopError` code (live, meaning unchanged) | §14.2, §11.4, §17 items 8–9, the display base check (§15.7), the Kp and Km finalize check | freeze: abandoned; in a generation mutation: that mutation abandoned; afterwards: pending |
| `phase_already_expanded`, `ambiguous_startable_candidates`, `phase_blocked`, `spec_violation` | live codes, meaning unchanged | §5.6 steps 2 and 6; §7.7 | before `_open`: nothing begun; at the freeze: abandoned |
| `review_not_persisted`, `review_persistence_unknown` | `StopError` code (P1) | `gate.require_persisted` and the blob check (§10.3, §11.6, §17 item 6) | pending |
| `review_roundtrip_mismatch` | `ValidationError` code (P1) | §15.1 step 2 | pending |
| `review_callback_unknown`, `review_callback_conflict` | `ValidationError` code (P1) | `gate.validate_settlement` (§10.4) | pending; nothing settled |
| `review_consumption_conflict` | `ValidationError` code (P1) | §16.3 | pending |
| `review_generation_conflict`, `review_generation_pending` | `ValidationError` code (P1) | `gate.next_generation_scope`, reached only after §11.8 step 3 resolved every pending generation mutation | pending |
| `review_path_ignored`, `review_committability_unknown` | `StopError` code (P1) | `gate.require_committable` (§14.4 step 5, §11.6) | freeze: abandoned; afterwards: pending |
| `review_containment` | `ValidationError` code (P1) | the P1 writers' containment (§11.6) | pending |
| `review_record_invalid`, `review_record_noncanonical`, `review_record_missing`, `review_record_version`, `review_gate_chain`, `review_namespace_invalid`, `review_projection_invalid`, `review_dependency_invalid`, `review_adapter_unresolved` | `ValidationError` code (P1) | the P1 reader and validators; at §14.6 chained under `review_namespace_unreadable` | as `review_namespace_unreadable` at §14.6; pending elsewhere after generation 1 |

## 26. Authority changes the implementation makes

When the implementation lands, it changes canonical authority as follows. Under `rules/human-confirmation` this is a Workline common-rule change, and the approval of this contract is what it rests on (reconnaissance Q17). This contract edits no authority file; the implementation edits exactly the three files below (P2-READY-024).

Each rule has one normative owner, the authority that already owns its subject:

- `registry.md` `rules/git` owns the Git-operation rules: Operation Owner, Commit / push, Push destination. It has no Scope section and no per-operation write-scope list. Its Operation Owner text speaks of an operation's planned write scope in general (`registry.md:64`), and the per-operation lists are the Roadmap Skill's;
- `skills/roadmap` owns the planning operation: the opt-in, the entry order, the orchestration of Review inside the operation, recovery orchestration, and the planning mutation's write scope;
- `skills/review` owns what Review records, the policy and the proofs mean. It owns no top-level planning mutation and no Git rule (`skills/review` Authority boundary).

Where a `rules/git` rule is part of the planning flow or of what a proof means, the Skill names that rule and does not restate it as its own. `rules/git` stays normative for the Git rules. `skills/roadmap` references them and owns the planning orchestration; `skills/review` references them and owns the meaning of the records and the proofs.

### 26.1 `registry.md` `rules/git`

1. Operation Owner: a review-v1 planning operation owns one planning mutation and the generation mutations it starts; resume order and conflicts as §11.8 and §11.12. After runtime loss it may begin a recovery planning mutation that continues exactly one canonical Run found by recovery discovery, never a foreign mutation's record (§12).
2. Commit / push: review-v1 planning commits use the contained planning commit primitive (§15.2). Review-v1 planning refuses `dirty_overlap` on its planning-owned paths before its first Review record (§14.2).
3. Commit / push: the review-v1 registration commit is made only on its recorded parent (`base_exact`). `base_exact` removes the independent-advancement step of the commit classification and nothing else (§15.2).
4. Commit / push: the review-v1 registration commit carries exactly the expected physical projection on its parent — the canonical writer's bytes, whole ledgers included (§15.7). Workline never publishes a registration commit with the same meaning in other bytes, whoever made it.
5. Push destination: for a mutation whose durable invocation names `review-v1-planning-publication-v1`, a push is its own stage publishing the exact commit named in its payload, recorded only after C-2(Km) — the committed planning proof included — has passed (§18.2, §18.4, §18.8). The current-combined rule is unchanged for every other mutation.
6. Push destination, for every operation: no push publishes a commit whose history holds a review-v1 planning registration commit unless the committed planning proof proves that registration's Run for that commit (§18.7, §18.8).
   - It is evaluated before a stage holding a push is recorded, when a recorded push would write, and right before the push.
   - A push the destination already holds is not refused, and nothing about the destination is read as proof.
   - A history in which no commit touched `.workline/review/candidate-snapshots/` is cleared by the fast-path read, which every Git answers, with no P2 minimum (§18.7).
   - Any other history is classified only on a Git at or above `P2_PUBLICATION_GIT_MIN` (item 8), where a Candidate snapshot without a registration commit begins no barrier. Below it, or on a Git of unknown version, its publication is refused because the proof cannot run, not because a registration was found.
7. Success on publication: a review-v1 planning operation succeeds only once its registration is published (remote-less: once C-2(Km) has passed). One that ends `not_authorized` or `stale` registers nothing and publishes nothing. It leaves its generation commits as local history that the next push from that branch carries — for `stale` after the seal, generation 4 and the Supersession too.
8. Git versions: `rules/git` owns both thresholds (§5.7).
   - `P2_REVIEW_GIT_MIN` = 2.40.0, the minimum to run the review-v1 planning Git semantics: an explicit review-v1 planning invocation on an older Git, or on one of unknown version, stops before the lock (`review_git_unsupported`).
   - `P2_PUBLICATION_GIT_MIN` = 2.31.0, the minimum to evaluate the publication proof: the barrier's registered-Run discovery and the committed planning proof. Below it, or on a Git of unknown version, a history the fast path does not clear is refused (`review_publication_barrier`, the proof unavailable).
   - Legacy operations need no newer Git than today for a history that never held a planning Candidate snapshot.

### 26.2 `skills/roadmap`

- the opt-in (§5), with the Git version gate, which names the `rules/git` review-v1 minimum, `P2_REVIEW_GIT_MIN` (§5.7);
- the review-v1 entry order and the canonical-input preflight before `_open` (§5.6): the live acceptance checks, `phase_already_expanded` included and under the live interrupted-entry rule, come before canonical recovery discovery;
- the review-v1 flows of Roadmap creation and Phase entry (§14.4, §15.1);
- the R9 canonical self-selection rule, owned here, on the committed basis, and the working-tree compatibility check (§7.4, §7.7);
- the terminal outcomes (§19), with stale before and after the seal (§13.2–§13.3);
- the currency rules (§13, §15.6, §17): the declared base on the committed view, compared before the rest of the Candidate; the use check with `use_check_head`; the pre-Kp currency proof; and the reconcile-only rule once the registration began;
- runtime-loss recovery orchestration (§12.1–§12.9): discovery, the recovery planning mutation, recovered reservations, new-Run eligibility and the pre-freeze resume setup;
- the pre-generation-1 abandonment rule (§12): before its first generation mutation, a review-v1 planning mutation is abandoned on every STOP, begun or resumed, a Phase entry included. The Skill's rule that a resumed Phase entry is never abandoned stays for legacy Phase entry;
- the write scope. The Skill's static write-scope paragraph ("各Roadmap operationが宣言する予定write scope", now `skills/roadmap/SKILL.md:466-476`) gains one stated exception: a review-v1 planning mutation also declares its Consumption path, `.workline/review/consumptions/<consumption_id>.yaml`, which depends on the reserved Consumption ID (§14.4 step 4, §12.4). The generation mutations it starts declare the scope `skills/review` gives each transition (§11.3);
- the review-v1 writer hand-off: after the freeze the registration writes from W, computed from the canonical Candidate, never from the caller's plan or design (§7.8);
- the display base check before each registration stage (§15.7, §17 item 9);
- the operation binding (§11.5);
- the planning operation's STOP codes and `ReconcileRequired` reasons (§25.1), with `ReconcileRequired` carrying its reason in `reason`.

### 26.3 `skills/review`

- the planning kinds and identities (§6);
- the Candidate's canonical representation of a caller-supplied mapping, and the refusal of a mapping it cannot hold exactly (§7.3, §7.6);
- the static policy record, verbatim (§9);
- the reviewer interface (§10);
- adjudication (§10.6);
- Planning Consumption v2 and uniqueness (§16), with the exact types of the `review-planning-delta` record (§16.1);
- the planning transition state machine, the records and initial write scope of each transition, and generation 4 with its Supersession (§11.3, §11.6);
- what the planning publication contract, the committed planning proof and the exact physical projection of Kp prove, and what they never take as proof (§15.7, §18, §18.8). The committed planning proof reads committed objects only and evaluates no attribute, so it needs no checkout capability; below `P2_PUBLICATION_GIT_MIN` a refused publication asserts no registration. Where the barrier applies, the shape of the push stage and both Git minimums are `rules/git`'s (§26.1 items 5, 6 and 8), which the Skill names;
- the recovery classification of a Run and `set_aside_runs` (§12.2, §12.3, §10.2);
- the checkout capability — the canonical Review-attribute rule proven from HEAD's raw committed `.gitattributes`, no `.gitattributes` below `.workline/`, and the committed and effective evaluations printing form L with no filter driver named `unset` — and the namespace readability, as the precondition for writing a Review record (§14.5, §14.6). Unsupported is not unsafe: the Skill states the one supported configuration. Workline never edits `.gitattributes` or `info/attributes`;
- the P2 scope of "適用範囲". Work terminal gating stays NOT ACTIVATED.

No other Skill changes. `skills/phase-create` and `skills/create` are unchanged: their registration cores are called exactly as today. `skills/start` and every other operation's Skill keep following `rules/git` for their pushes (for example `skills/create/SKILL.md:49`), where the barrier rule of §26.1 item 6 lives.

## 27. Implementation surface map

| file | purpose | contract sections | tests (§28) |
| --- | --- | --- | --- |
| `src/workline/review/planning.py` (new) | identifiers; `PlanningReview`, task, report and finding types; record builders (Candidate, Context, policy, request envelope, report, adjudication, obligations, coverage, report set, evidence, invalidation evidence); stale reason codes; report validation; loader identity; authority digests | §5.1, §6, §7.1, §8, §9, §10, §11.6.1 | A, B, C, D |
| `src/workline/review/committed.py` (new) | committed Review reading: paths added in a commit's history (`--full-history --diff-merges=combined --diff-filter=A`), raw blobs at a commit, parsed by the unchanged P1 serializer and record classes (and the v2 Consumption reader) | §15.3 P12, §18.7 | E, G |
| `src/workline/review/publication.py` (new) | the publication barrier and the committed planning proof: `barrier_problems(repo, commit)` over committed objects, CP1–CP13, with CP5 and CP6 through the adapter the Run's Context names and never a renderer of its own; CP7 before CP6; the fast path, run on any Git, and the barrier's Git capability rule — `P2_PUBLICATION_GIT_MIN` checked only when the fast path lists a commit, and a refusal below it that classifies no Run and names no registration (P2-READY-001, -027, -029); no attribute evaluation and no working-tree read | §5.7, §15.7, §18.7, §18.8 | G, K, M, P, S |
| `src/workline/review/recovery.py` (new, Review-owned reads only) | recovery discovery reads: matching Runs from history and working tree, clean persistence, reconstruction, classification rows a–g; it records nothing and starts no mutation | §12.2, §12.3 | L |
| `src/workline/review/checkout.py` (new) | the checkout capability in its four layers (P2-READY-004): the raw committed-source check of HEAD's root `.gitattributes` and the deeper-file check, from committed objects alone; the committed and the effective attribute evaluations, form L; no filter driver named `unset`; namespace readability | §14.5, §14.6 | J |
| `src/workline/review/records.py` | Planning Consumption v2 (reader and builder) beside v1 | §16.1–§16.2 | F |
| `src/workline/review/store.py` | v2 reading; registration-commit and target indexes | §16.3 | F |
| `src/workline/review/validate.py` | v2 validation, planning binding, uniqueness indexes | §16.2–§16.3 | F, H |
| `src/workline/review/paths.py` | runtime subpaths `proofs/`, `reports/`, `no-hooks/`, `attr-eval/` | §10.5, §14.5, §15.2, §15.4 | E, J |
| `src/workline/roadmap_review.py` (new, Roadmap-owned) | the review-v1 flow: the canonical-input preflight (§5.6), a pure function over the request identity that uses only `validate_condition` and the P1 serializer; the review-v1 entry order with the live interrupted-entry rule (§5.6) and the Git version gate of `P2_REVIEW_GIT_MIN` (§5.7); recovery orchestration (discovery call before `_open`, the recovery planning mutation, its binding and continuation, the pre-freeze resume setup, §12.9), the pre-generation-1 abandonment rule (§12), freeze with the committed basis and the working-tree compatibility check (§7.4, §7.6, §7.7), generation mutations 1–4, reviewer call, currency on committed views in the order of §13, use check and `use_check_head`, registration hand-off, pre-Kp currency proof (and its `refuse_recorded` hook), Kp / Km, proofs, Consumption, publication, terminal outcomes; W (`CanonicalPlanningWriterInput`, §7.8), the one Candidate-to-writer-input function every consumer takes; both adapters, with the expected physical projection (`project_expected`, §15.7), its comparison and record check, and the display base check; `ReviewedPlanningResult`; every `ReconcileRequired` it raises carries its §25.1 reason | §5.6, §5.7, §7, §11–§21, §25.1 | A–S |
| `src/workline/committed_view.py` (new) | committed-result loader: materialization from raw blobs and `ProjectView.load` — `ProjectView` as of an exact commit, for the freeze's committed basis and working-tree compatibility check as for every proof; delta reading; the materialized base of the expected physical projection | §7.4, §7.6, §15.3–§15.4, §15.7 | E, M, P |
| `src/workline/roadmap.py` | `review=` keyword; on the review-v1 path, the canonical-input preflight called right after the request identity is computed and before the same-request check and `_open` (§5.6); marker check at the entry (§5.3); the registration of `_create_roadmap` / `_expand_phase` separated from the legacy `_finalize` without changing legacy behaviour; the Roadmap-file rendering of `_create_roadmap` and the stage-input derivation of `_create_roadmap` / `_expand_phase` extracted as pure functions the legacy path itself calls, with no behaviour change (§7.8, §20); review-v1 branch, whose registration takes W | §5, §7.8, §15.1, §15.7 | A, B, I, M, N, O |
| `src/workline/phase_create.py` | the effect building of `decide_phases` extracted as a pure function that `decide_phases` calls, with identical output (§20) | §15.7, §20 | M |
| `src/workline/gitcmd.py` | a bytes runner; `tree_entries`, `read_blob`, `commit_delta`, `check_attributes` (effective, and committed through the isolated evaluation directory), `added_paths`, `blob_at`; contained `add` / `commit`; the running Git's version (`git --version`), compared with the two minimums; the fast-path read `rev-list --full-history -n 1`; the raw reads of HEAD's root `.gitattributes` and of the entries below `.workline/` (`ls-tree`, `cat-file`); the filter-driver keys of the effective configuration (`config --get-regexp`) | §5.7, §14.3, §14.5, §15.2–§15.4, §18.7 | E, G, J, S |
| `src/workline/gitops.py` | `review_commit_effect`, `review_publication_effect`, attribute preflight helper; the publication barrier in `finalize` before a stage holding a push is recorded | §14.3, §15.2, §18.4, §18.7 | E, G |
| `src/workline/mutation.py` (private functions only) | discriminator + planning publication branch in `_recorded_publication` (invocation threaded through `_classify_recorded` / `_publish`); `mode` in `apply_effect`; `base_exact` in `_classify_commit` (only its independent-advancement step removed) and the planning primitive; the publication barrier in `_classify_push` and in `apply_effect` for `git_push`; the recovery-only reservation binding helper, callable on a resumed recovery planning mutation that has not bound, saving `recovery_binding` with the binding (§12.5, §12.9); the planned-write computation of `write_file` / `add_relation` extracted as a module-level function that `_planned_write` and the expected physical projection share (§15.7, §20); payload validation | §12.5, §15.2, §15.7, §18.4–§18.5, §18.7 | E, G, L, M |
| `src/workline/errors.py` | `ReconcileRequired` gains the keyword-only attribute `reason` (default `None`); `code` and every existing construction unchanged (P2-READY-005) | §25, §25.1 | S |
| `registry.md`, `.claude/skills/roadmap/SKILL.md`, `.claude/skills/review/SKILL.md` | authority text, each rule under its one owner: `rules/git` sections Operation Owner, Commit / push and Push destination; the Roadmap Skill's New Roadmap, Phase entry and write-scope paragraphs; the Review Skill (P2-READY-024) | §26 | C (policy pin), S |
| `tests/test_review_planning_*.py` (new) | the test contract | §28 | — |

Expected not to change: `state.py` (no helper is needed), `store.py`, `validate.py` (`validate_structure`, `validate_project`), `start.py` and every START Work-terminal path, `create.py` and `phase_create.py` behaviour (at most a pure helper extracted with identical output), `ops.py`, `oplock.py`, `ids.py`, `implementation.py`, `cli.py` (Roadmap has no CLI), `review/gate.py`, `review/adapter.py`, `review/projections.py`, `review/closure.py`, `review/fsafe.py`, `review/serialize.py`, the P1 `GateGeneration`, `Receipt` and `Supersession` classes (generation 4 and the Supersession use them as they are), P3 activation code (none exists), and every unrelated operation — whose only new behaviour is the publication barrier on its push, inert in a history without a planning Candidate snapshot and, on a Git at or above `P2_PUBLICATION_GIT_MIN`, without a review-v1 planning registration commit.

## 28. Test contract

Frozen minimum. Every test runs on real Projects through `tests/helpers.py`, through production code paths. A happy path alone is insufficient (Frozen P1 R12 §14). Section J and the round-1 items of B, D, E and G are the tests of the round-1 repairs; sections K and L are the tests of the round-2 repairs; section M is the test of the round-3 repair; section N is the test of the round-4 repair; section O is the test of the round-5 repair; sections P, Q, R and S, and the P2-READY-004 items of J, are the tests of the final readiness repair (§33); items A–K of J and the Git-minimum items of S are the tests of its round 2 (§33.7).

**A. Applicability**

- A legacy Roadmap creation and a legacy Phase entry are byte-for-byte unchanged: invocation, stages, commits, pushes and result. The existing suite passes unchanged.
- An explicit review-v1 Roadmap creation is gated; an explicit review-v1 Phase entry is gated.
- The opt-in cannot fall back to legacy: platform, checkout capability, Review namespace, Git transform, Context unavailable and reviewer failure each STOP, with no ungated registration.
- Both marker mismatch directions → reconcile with the record untouched (§5.3).
- An invalid `review` argument → `review_contract_invalid` with nothing written.
- POSIX, or a patched `immutable_create_supported() == False`, with review-v1 → `review_create_unsupported` before any lock or record. POSIX legacy is unchanged.

**B. Generation serialization and the transition state machine**

- An uninterrupted run leaves three generation commits before Kp, and no generation 4.
- A crash at every generation window (§21.1 rows 3–5, 9, 11) resumes correctly.
- A pending predecessor is resumed before N+1.
- A conflicting second owner (a pending generation mutation bound to another planning mutation) → reconcile.
- Two pending generation mutations → reconcile.
- A generation file created with its `applied` flag not saved → classified matching, no N+2.
- No fork and no skipped generation.
- The initial scope is exactly as §11.3, with no `extend_scope` on generation mutations.
- The dirty snapshot is taken at the start.
- The binding is enforced across mutations (branch switch between generation commits → reconcile).
- *P2-CONTRACT-002.* Generation 3 sealed → stale at the use check (authority text, the Policy constant, and a committed declared-base fact, one test each) → generation 4 `open` + the Supersession in one stage, committed and persisted, every field as §11.6.1, before the planning mutation completes `stale` with the superseded Receipt; `validate_project` clean afterwards.
- Interruption at every generation-4 window (§21.1 rows 14–16): no recorded effect (abandoned; the use check runs again — current again → the registration proceeds with the unsuperseded Receipt; still stale → generation 4 again); gate 4 created with its `applied` flag unsaved; gate 4 created and the Supersession not; both created, not committed; committed, not completed; generation mutation completed, planning mutation not.
- The old Receipt cannot be consumed: the use check refuses it, and a fixture Consumption of it is a `validate_review` problem.
- No fake Supersession before a Receipt exists: stale before the reviewer launch, before generation mutation 2 and before generation mutation 3 → no generation and no Supersession written, `validate_review` clean, result `stale` with `receipt_id=None`.
- Chain shape: generation 5 is never started; generation mutation 4 is never started once a registration stage is recorded; a pending generation mutation of the Run while a registration stage is recorded → reconcile; a transition out of order → reconcile.

**C. Authorization**

- The accepted → settled → sealed chain validates (`validate_project` clean).
- A seal with an unsettled task is refused (P1 invariant).
- An invalid Receipt (tampered, unbound) → reconcile at the use check.
- A superseded Receipt is refused, both from the real invalidation flow (B) and from a fixture.
- Not-authorized paths register nothing: HIGH, MID, `declined`, and a failed task; no publication barrier results from them (a subsequent legacy push proceeds on a Git at or above `P2_PUBLICATION_GIT_MIN`).
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

- Interruption at every commit, proof and publish boundary (§21.1 rows 19–34).
- No push before proof: no `git_push` exists in the record before C-2(Km) — M1–M6, the committed planning proof included — has passed.
- A foreign commit is not an operation-owned commit: a byte-identical Kp or Km made by another subject is never adopted or pushed as the operation's own; it reaches the destination only as history, and only where the committed planning proof passes (§18.2).
- Branch switch → reconcile. Rewritten history → reconcile.
- Remote advancement: fast-forward, destination ahead holding Km, and diverged → reconcile.
- The retry publishes exactly Km.
- Discriminator: legacy is unchanged; a combined pair in a planning mutation is refused; a push in a generation mutation is refused; unknown or partial markers fail closed; shape and content are never selectors.
- A remote-less Project completes without a push, and no barrier is evaluated.
- *P2-CONTRACT-001.* A crash after Kp and before C-2(Kp); an unrelated Workline operation (a hold of another Roadmap: event log only) then runs and attempts its own push → `review_publication_barrier` before its stage is recorded; the destination's branch never receives Kp (read from the destination); after the planning retry proves Kp and publishes Km, the other operation completes and its commit is published on top of Km.
- The same with a current-combined stage recorded before Kp existed and its commit made on Kp by the independent-advancement rule → refused at classification (the dry run shows a write) and, with the classification patched, at application; nothing pushed; completed once Km is at the destination (classified already published).
- Retry after proof: once Km is committed and the committed planning proof passes, pushes from Km and its descendants pass; a commit between Kp and Km is never pushed by its own push.
- Kp proof failure keeps every subsequent Workline push of a history holding Kp refused — legacy and review-v1 — across a process crash, a deleted `.workline/runtime/`, runtime-record loss and a fresh clone.
- Runtime-record loss with Kp unproven → the barrier holds for good; nothing lifts or bypasses it:
  - the same review-v1 Roadmap creation stops at discovery with `review_recovery_incomplete` (§12.2 row b);
  - the same review-v1 Phase entry stops before discovery with the live `phase_already_expanded`, since its Works are in the Phase (§5.6 step 6);
  - another review-v1 call with a push destination stops at its freeze with `review_publication_barrier`;
  - a legacy Roadmap creation registers, and its own push is refused;
  - a legacy Phase entry of that Phase gets `phase_already_expanded`.
- A manual external push is detected but never accepted as proof: a person pushes Kp before C-2(Kp); the barrier still finds the unproven Kp in the history of every Workline push that would carry it, whatever the destination holds, so a legacy push of a descendant is still refused; the planning resume still runs C-2(Kp) over local objects; with C-2(Kp) made to fail, no Consumption is written although Kp is at the destination; and a push classified as already published writes nothing and is read as nothing more.
- A person's commit of the working-tree registration after a crash begins the barrier; the planning mutation classifies its Kp applied without an ID → `review_commit_unowned`.
- History does not hide Kp: a subsequent commit that deletes the Candidate snapshot or reverts the registration files → the barrier still holds; a merge bringing in a side branch with Kp → found; an evil merge adding a reserved path → found.
- Unparseable planning snapshot in the pushed history (fixture) → the barrier holds (fail closed).
- No barrier where nothing was registered: generation 1 only, generation 2, generation 3 without a registration commit, generation 4, not authorized, stale — on a Git at or above `P2_PUBLICATION_GIT_MIN`, a legacy push proceeds in each (below it: §28 S).
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

**J. Checkout capability (P2-CONTRACT-004; P2-READY-004, final readiness repair rounds 1 and 2)**

- `core.autocrlf=true` with no attribute rule → `review_checkout_unsafe` at the freeze, before any Review record; the planning mutation abandoned; nothing written.
- **A — Canonical source.** The root `.gitattributes` ends with `.workline/review/** !text eol=lf -filter -ident -working-tree-encoding`, and HEAD holds no `.gitattributes` below `.workline/`: layers 1 and 2 pass from committed objects, the committed and the effective evaluations print form L, and a review-v1 run completes under `core.autocrlf=true`. A fresh clone keeps every Review record byte for byte, compared with its committed blob. Broader rules before the canonical one (`* text=auto`, `*.png binary`) change nothing.
- **B — Literal filter.** `filter=unset` in place of `-filter`, both evaluations printing the tuple of A → layer 1 fails → `review_checkout_unsafe`, nothing written.
- **C — Literal ident.** `ident=unset` in place of `-ident` → the same.
- A NUL byte in the root `.gitattributes` before the canonical rule line → layer 1 fails; the committed evaluation prints every attribute `unspecified`.
- **D — Literal working-tree-encoding.** `working-tree-encoding=unset` in place of `-working-tree-encoding` → the same.
- **E — Text lookalikes.** `-text`, `text=unset` and `text=unspecified` in place of `!text` → each unsupported: layer 1 fails, `review_checkout_unsafe`. `text=unspecified` prints exactly what `!text` prints.
- **F — Deeper committed override.** The root rule correct, and `.workline/.gitattributes` committed → layer 2 fails, whatever the evaluations print: asking `* eol=crlf`, they print `eol: crlf`; holding a comment only, they print form L. The same for `.workline/review/gates/.gitattributes` asking `*.yaml filter=unset`, under which they print form L, and for the case variant `.workline/.GITATTRIBUTES`.
- **G — Rule after it.** The canonical rule followed by another attribute rule → layer 1 fails: `*.png binary`, which leaves the printed tuple form L, and `* text=auto`, which prints `text: auto`.
- **H — Comments and blanks after it.** Comments, indented comments and blank lines after the canonical rule → the capability holds.
- **I — Hostile global and system configuration.** With `core.autocrlf=true`, a global attributes file asking `*.yaml eol=crlf`; `*.yaml filter=unset` with a driver `unset` whose smudge changes bytes; `*.yaml ident`; `*.yaml working-tree-encoding=UTF-16`; `*.yaml text eol=crlf`; or the legacy `*.yaml crlf`, `-crlf` or `crlf=input`; then all of them at once with `core.autocrlf=false` and `core.eol=crlf`, given as global and, separately, as system configuration: the capability holds, both evaluations print form L, and a fresh clone keeps every Review record byte for byte.
- **J — Current `info/attributes` override.** Layers 1 to 3 pass. `.git/info/attributes` asking `.workline/review/** eol=crlf` → the effective evaluation prints `eol: crlf` → `review_checkout_unsafe`. The same file asking `.workline/review/** filter=unset`, with a filter driver `unset` configured → the effective evaluation prints form L and layer 4 fails on the driver → `review_checkout_unsafe`; with no driver `unset`, the literal selects nothing and the capability holds.
- **K — Literal filter exploit.** A driver named `unset` whose smudge changes bytes, configured globally. The committed literal `filter=unset` fixture, whose evaluations print form L, is refused by layer 1. A fresh clone of that fixture made under this configuration changes the Review records' bytes, which is why it is refused; the canonical rule under the same configuration keeps them.
- An attribute-source redirect in this repository (`attr.tree`, `GIT_ATTR_SOURCE`) → the effective evaluation prints every attribute `unspecified` → `review_checkout_unsafe`.
- A rule only in `.git/info/attributes` → layer 1 fails → `review_checkout_unsafe`.
- `check-attr` unanswerable, or the root `.gitattributes` blob unreadable (fixture) → `review_checkout_unknown`.
- The Context carries `checkout_capability: review-v1-planning-checkout-v1`.
- No statement, record or test accepts form B, or takes the printed form L alone as proof.
- A fresh clone of a commit that carries the canonical rule, made under `core.autocrlf=true` and again under a global attributes file asking `*.yaml eol=crlf`, keeps every Review record's physical bytes LF; `ReviewStore` reads each; `validate_project` is clean; a new review-v1 call there passes §14.5 and §14.6.
- Existing Review records of earlier Runs remain readable in that clone.
- Unsafe semantics are never silently normalized: a CRLF record (checked out before the rule, or under a clone-local `info/attributes` `eol=crlf`) → the P1 reader refuses it (`review_record_noncanonical`), the call stops with `review_namespace_unreadable` at discovery's readability step (§12.2 step 1, §14.6), and no byte is rewritten or normalized.
- The rule removed by a commit after generation 1 → the next Review-writing stage stops `review_checkout_unsafe`, the planning mutation stays pending, and continues once the rule is back.
- Transform preflight (§14.3): a committed literal `filter=unset` on a registration path, with a filter driver `unset` configured → `review_git_transform` before any write; with no such driver → it passes.
- Legacy planning is unaffected: no evaluation and no refusal in a Project without the rule.

**K. C-2(Km) and the committed planning proof (P2-CONTRACT-001, round 2)**

- Kp proven → Consumption → Km committed → a crash before C-2(Km) → `.workline/runtime/` deleted → an unrelated Workline push (a hold of another Roadmap) of a descendant: it publishes only after its own committed planning proof passes over the committed objects. With the objects intact the proof passes and the push publishes, and nothing reads the lost note; with any proof item broken by a fixture → `review_publication_barrier`, and nothing is pushed.
- A schema-valid forged or hand-made Planning Consumption naming Kp does not clear the barrier unless every item passes: one fixture per item CP1–CP13. Examples: wrong `semantic_projection_digest`, `registration_delta_digest`, IDs, `loader_identity` or `adapter_identity`; the right fields over a Kp whose delta carries an extra path or whose meaning differs from the Candidate; a second Consumption for the Receipt; a Supersession added anywhere in the history.
- Km exists but a proof item fails → the barrier holds: an extra path in Km (CP12); Km's parent not descending from Kp (CP11); a planning-owned path touched between Kp and Km's parent (CP11); the Consumption blob changed after Km (CP11); a Run record changed after Kp (CP4, CP13).
- Km exists and the committed planning proof passes → the barrier clears, for the planning mutation's own push, for an unrelated operation's push, and from a fresh clone.
- The destination already holds Km (pushed by hand) while the proof fails (fixture) → a push that would write is refused, the planning mutation does not complete as published, and a push classified as already published writes nothing and proves nothing.
- The runtime `publication_proof` note is deleted → the planning retry runs C-2(Km) again and never assumes the note; after full runtime loss the outcome is decided by the committed planning proof alone.
- A Workline upgrade that changes `loader_identity` but reproduces the expected physical projection byte for byte and the same semantic projection → the proof still passes; an upgrade that changes one expected byte → the barrier holds (§15.7, §28 M item N). A running implementation lacking the adapter, the projection semantics version or the policy the Run names → the barrier holds.
- Ownership stays separate: a byte-identical foreign Km, such as a person's commit of the working-tree Consumption after a crash lost the Km commit ID → the planning mutation never adopts it (`review_commit_unowned`), while the barrier clears for it when the committed planning proof passes.
- A legacy-only Project's push performs one path-limited history read and no proof.

**L. Runtime-loss recovery (P2-CONTRACT-005)**

- Generation 1 accepted → `.workline/runtime/**` deleted → the same request → the same Run is recovered. The same `task_id` is launched again, and the callback receives exactly the original task fields (§10.3). The report is settled as generation 2 by a generation mutation whose `planning_mutation_id` is the recovery planning mutation. The invocation carries `recovery_of_review_run_id`, and no ID of the lost mutation is reused.
- The same from a fresh clone, with the checkout capability satisfied.
- Generation 1 with its task input missing or with a digest mismatch (fixture) → `review_recovery_incomplete`; no new Run and no new task ID.
- Generation 1 with a Candidate snapshot mismatch (fixture) → fail closed; no new Run.
- Two recoverable matching Runs (fixture: two histories merged) → `review_recovery_ambiguous`; no Run is chosen.
- Generation 2 settled, then runtime lost. Authorizing and current → the same Run resumes with no reviewer call, and generation 3 gets a newly reserved Receipt ID. Not authorizing → set aside (`not_authorized`), and a new Run whose `set_aside_runs` names it. The settled task is never launched again.
- Generation 3 sealed, then runtime lost → the same Run and Receipt are recovered into the use check. Current → the registration and the Consumption under that same Receipt. Stale → generation 4 and the Supersession, then `stale`.
- Generation 4 → not recovered: set aside (`invalidated`), and a new Run.
- Domain reservation IDs are recovered exactly from the reviewed Candidate: the registration writes exactly the snapshot's Roadmap / Phase / Work / relation / Related IDs, and no domain ID is generated. The helper refuses a key already reserved with another ID, an ID of the wrong kind, and an ID already used in HEAD's committed view or the working tree.
- The runtime-only Receipt and Consumption reservations of the lost mutation are gone → the recovery reserves them anew under the same keys (the Receipt only before generation 3; the Consumption always), and binds the sealed Receipt's ID when generation 3 exists.
- A half-written canonical generation with no runtime record (gate 1 without its task input, gate 3 without its Receipt, generation 4 without its Supersession), or an applied-but-uncommitted gate 2 → `review_recovery_incomplete`; a new Run never hides it.
- A new Run is allocated only when no recoverable canonical Run exists: none ever created, or every matching Run terminal or obsolete. An obsolete (stale) generation 1 is set aside and recorded in `set_aside_runs`, and it is never recovered afterwards, even when its currency returns.
- A stale-before-Receipt completion with the runtime intact, then the same request → the old Run is recovered if current again, or set aside as obsolete and a new Run begun.
- Registration files only in the working tree (generation 3, runtime lost) → the call stops with nothing written: Roadmap creation at the recovered-reservation binding (`review_recovery_reservation_conflict`), Phase entry at `phase_already_expanded`; once the files are discarded, recovery continues from the use check.
- Runtime loss after Kp, before any Consumption was committed → the same Roadmap creation stops at discovery with `review_recovery_incomplete`, and the same Phase entry stops before discovery with `phase_already_expanded` (§5.6 step 6); no new Run; the barrier holds.
- A generation mutation left pending by a lost planning mutation (only the planning mutation's record removed) → `review_recovery_incomplete`.
- Normal retry is untouched: with the planning mutation's record present, the same request resumes it, and discovery does not run at the entry (only the pre-freeze resume setup of a mutation that has not recorded its discovery outcome runs it, §28 Q). A pending recovery planning mutation is resumed by its exact invocation. A legacy invocation of the same request never runs discovery.
- §5.3 with the recovery key: a pending recovery record against a legacy invocation → reconcile; the key without the marker pair, or any other extra key → reconcile.

**M. Exact physical projection (P2-CONTRACT-006, round 3)**

- **A — Roadmap, canonical.** A review-v1 Roadmap creation with Phases and Phase relations, on a P whose `roadmap.yaml` already holds records: E computed from the committed Candidate snapshot and P equals Kp's delta path for path, transition, mode and byte — the Roadmap file, every Phase file, the whole `roadmap.yaml`; pre-Kp item 6, P3, P4 and CP5 pass.
- **B — Phase entry, canonical.** The same for a design with normal Works, `planned_next` and `requires_completion`, Related with and without a condition, an integration and a confirmation: every Work file, the whole `roadmap.yaml` and `related.yaml`.
- **C — Parser-equivalent entity bytes.** A fixture Kp (with its Consumption and Km) whose Roadmap, Phase or Work file holds the same meaning in other bytes — reordered frontmatter keys, a quoted scalar, no blank line after the frontmatter, an extra trailing blank line (each **Measured** as read with the same meaning, §31): CP6 passes, CP5 fails, `review_publication_barrier`. The planning mutation's own C-2(Kp) fails at P3.
- **D — CRLF.** An entity file or a ledger committed with CRLF (kept by `-text`, or `core.autocrlf=false`) where E has LF: CP5 fails. The checkout capability for Review records (§14.5) is not used and not changed by this case.
- **E — Ledger layout.** The same relation records in a whole `roadmap.yaml` or `related.yaml` rendered differently (record keys reordered, an extra top-level key, **Measured** as the same records, §31): CP5 fails.
- **F — Blank line or reordering.** An extra blank line, or a reordered but parser-equivalent representation, anywhere in a registration path: CP5 fails.
- **G — Wrong blob.** Exact path set, transitions and modes, one blob different: CP5 fails.
- **H — Right meaning, wrong entity byte.** One entity byte differs while the meaning is the reviewed one, for example a display number other than the one allocated on P: CP6 passes, CP5 fails.
- **I — Right bytes, wrong meaning.** Kp equals E, and a fixture makes the semantic side read another meaning (a patched reader or `normalize_persisted`): CP5 passes, CP6 fails, the barrier holds. Each dimension is required on its own.
- **J — Forged Consumption.** A schema-valid Consumption whose `registration_delta_digest` is the digest of C's actual noncanonical delta: the barrier holds (CP5; CP9 compares with E's digest).
- **K — Foreign Kp, canonical bytes.** A foreign or hand-made Kp with exactly E's bytes, every other item passing: the barrier clears for histories holding it (rule B, §18.2), and no planning mutation adopts it (`review_commit_unowned`).
- **L — Foreign Kp, same meaning, other bytes.** The barrier holds.
- **M — Runtime loss after Km.** `.workline/runtime/**` deleted, and again in a fresh clone: an unrelated Workline push recomputes E from the committed Candidate snapshot, P's tree and the Run's adapter only; a canonical Kp passes and a physical-mismatch fixture still holds the barrier.
- **N — Implementation upgrade.** (1) A different package digest (`loader_identity`) whose adapter reproduces E and the semantic projection exactly: CP passes when every other item passes. (2) A patched renderer, display allocation or planned-write computation that changes one expected byte: CP5 fails, the barrier holds. (3) The Run's adapter identity or projection semantics version not provided: E unavailable, the barrier holds.
- **O — Base sensitivity.** The same Candidate projected on two legitimate P — different `roadmap.yaml` / `related.yaml` contents, one of them a valid but non-canonically formatted ledger the writer re-renders, and different entity counts — gives each P its own whole-ledger bytes and display numbers; a Kp made on one P passes against its own projection and fails against the other's.
- **Display base check.** An untracked or deleted `*.md` entry in a display-allocating directory at the use check, or before a subsequent registration stage after a crash between stages: `dirty_overlap`, nothing recorded; once the entry is removed or committed the run continues and Kp equals E. A person's commit adding an entity file of that kind after the registration began: pre-Kp item 6 refuses (`review_registration_projection_mismatch`), and no Kp is made.
- **One mechanism.** Pre-Kp item 6, P3, P4 and CP5 use the same `project_expected` and the same comparison: a test that patches the projection sees all of them change together. No module under `review/` renders an entity or a ledger.

**N. Canonical writer input (P2-CONTRACT-007, round 4)**

- **A — Condition key order.** Two review-v1 Phase entries whose designs differ only in one Related condition's insertion order — `{"pattern": "src/*.py", "kind": "path_glob"}` and `{"kind": "path_glob", "pattern": "src/*.py"}` — with the same reserved IDs (a deterministic ID source): equal Candidate records and `candidate_hash`, equal `request_digest` and `operation_identity` (§6.2), equal TaskInput `request_digest`, equal W, equal E, equal `related.yaml` bytes (`kind` before `pattern`, the canonical order), and P3 and CP5 pass for both.
- **B — Nested mappings.** The live `validate_condition` accepts a nested mapping under an extra key (**Measured**, §31). Two conditions equal as values, with different insertion orders at two depths, give the same W, E and bytes, every entry kept. A value the canonical Candidate cannot hold exactly is refused as in J; no support is invented for it.
- **C — Extra condition fields.** Extra scalar, list and nested-mapping entries in different insertion orders: no entry lost, one W, one set of bytes.
- **D — Uninterrupted and recovered.** One Candidate registered by an uninterrupted run and, separately, by a recovery after `.workline/runtime/**` was deleted after generation 3: the same W, the same E and the same domain bytes, display numbers included.
- **E — Fresh clone.** W and E computed in a fresh clone from the committed snapshot equal the originals.
- **F — The caller's object is not the source after the freeze.** The same request is resumed with a new design object whose condition is equal as a value but built in the other insertion order: the resumed registration writes the Candidate's bytes, and its W is the Candidate's. Nothing the public API does not allow is mutated.
- **G — Legacy unchanged.** A legacy Phase entry with the pattern-first condition writes `pattern` before `kind`, byte for byte as at the baseline; no Candidate canonicalization touches the legacy path.
- **H — Sequences stay ordered.** Reordering two Related entries, or two normal Works, gives a different Candidate (`candidate_hash`), a different W and different bytes: mappings are canonicalized, sequences are not.
- **I — Record check.** Registration effects produced from W equal E. A fixture that records an effect built from the caller's pattern-first mapping instead is refused by pre-Kp item 6 (`review_registration_projection_mismatch`), and no Kp is made.
- **J — Representability.** A condition holding a tuple, a float, a non-text key, an empty key or a sequence directly inside a sequence → `review_candidate_unrepresentable` from the canonical-input preflight before `_open`, nothing begun (section O); the same condition with a list, an integer or a nested mapping instead is accepted and kept.

**O. Canonical-input preflight (P2-CONTRACT-008, round 5)**

For every refusal below, the test captures the mutation namespace (`.workline/runtime/mutations/`), the runtime temporary directory, the reservations, the Review namespace and the domain files before and after, and asserts them unchanged, entry for entry and byte for byte.

- **A — Float.** A review-v1 Phase entry whose condition carries an extra float entry: `review_candidate_unrepresentable` before `_open`; no new mutation record, no reservation, no Review record, no domain file change.
- **B — Tuple.** The same with a tuple value, which the canonical form would make a list: the same refusal and the same unchanged state.
- **C — Non-text key.** An integer, boolean or tuple mapping key, at the top of the condition and inside a sequence item: the same refusal, never the `TypeError` of `json.dumps(..., sort_keys=True)`.
- **D — Empty key.** An empty key directly in a condition mapping: the same refusal, because the P1 text cannot render it. An empty key inside a mapping that is a sequence item passes, because the P1 form carries it and reads it back (**Measured**, §31).
- **E — Sequence inside a sequence.** The same refusal.
- **F — Key order only.** Pattern-first and kind-first conditions both pass the preflight, and give the same Candidate, the same W, the same E and the same result.
- **G — Valid nested mapping.** Two insertion orders at several depths both pass, with the same Candidate, W and E.
- **H — Valid extra fields.** Extra scalar, list and nested-mapping entries the P1 form carries pass, and no entry is lost.
- **I — Legacy unchanged.** The float, tuple, non-text-key, empty-key, nested-sequence and lone-surrogate conditions through the legacy API give exactly the baseline outcomes recorded in §29 item 7, including the pending mutation the tuple strands; the legacy path runs no preflight.
- **J — No mutation created.** For every refusal of A–E, and for a lone surrogate in a condition or in a Work name, the mutation namespace and the runtime temporary directory are unchanged, entry for entry and byte for byte.
- **K — Normal retry.** A pending valid review-v1 planning mutation and the same valid caller: the preflight passes, and the planning mutation resumes normally.
- **L — Invalid caller against a pending mutation.** A pending valid review-v1 planning mutation and a new caller whose condition holds a float: the preflight refusal, with the pending mutation record untouched, byte for byte.
- **M — Recovery.** A recoverable canonical Run after runtime loss (§12.7) and a valid equivalent caller, with a different key order: the preflight passes and the same Run is recovered. The same Run and an unrepresentable caller: the preflight refusal comes before discovery and before any recovery planning mutation, and the Run's records are untouched.
- **Semantic condition validation.** A condition with an unsupported `kind` gets the live `validation_failed` refusal before `_open`, with nothing begun.
- **No second serializer.** The preflight calls only `validate_condition` and the P1 `serialize` functions: a test that patches `serialize.canonical_data` sees the preflight change with it.

**P. Committed R9 basis (P2-READY-001)**

- **A — Equal bases.** The working tree equals HEAD on every declared-base and R9 input. The Candidate's `canonical_first_work`, frozen on HEAD's committed basis, equals the selection of the pre-Kp proof on P, of P9 on the committed Kp view, and of CP6 in a fresh clone.
- **B — Uncommitted lifecycle.** An uncommitted `events/events.jsonl` change alters the Phase's lifecycle (a `phase_resumed` of a held Phase, present only in the working tree) or a predecessor Work's completion. review-v1 refuses at the freeze with `review_base_uncommitted`: before any Review record, the planning mutation abandoned, nothing written.
- **C — Uncommitted relation.** An uncommitted `relations/roadmap.yaml` change alters a compared fact — a `requires_completion` into the Phase from an unfinished Phase, or a relation that changes the R9 selection. The same refusal. For Phase entry that ledger is also a registration path, so a change that alters no compared fact is refused by `dirty_overlap` at §14.4 step 5 (§14.2).
- **D — Irrelevant change.** An uncommitted change that alters no compared fact — an event of another Roadmap, an unrelated file — is not refused. The Candidate is exactly the one HEAD gives, and the run completes. No whole-working-tree cleanliness is required.
- **E — Declared base first.** A committed lifecycle change of a declared-base fact after generation 1, 2 or 3 — the Phase held, a predecessor completed — that also changes the R9 selection is classified by the declared base, never as an R9 or Candidate mismatch:
  - stale before a Receipt;
  - generation 4 at the use check;
  - `review_registration_currency_changed` at the pre-Kp proof;
  - P12 in C-2(Kp);
  - CP7 in the committed planning proof.
- **F — Mismatch with an equal base.** The declared base is equal, and a fixture makes the R9 reconstruction differ (a patched selection). The result is `ReconcileRequired` with its point's reason:
  - `review_candidate_mismatch` at the use check and at the pre-Kp proof;
  - `review_recovery_incomplete` at discovery;
  - P8/P9 in C-2(Kp) (`review_persisted_proof_failed`);
  - CP6 at the barrier.
- **Round-trip basis.** The working-tree round trip (§15.1 step 2) takes its R9 selection from HEAD's committed basis: an uncommitted lifecycle event added after the freeze does not change it.

**Q. Pre-freeze resume setup (P2-READY-002)**

- **A — Crash after `begin`.** A fixture ends the process right after `MutationController.begin`, before the `recovery_discovery` note. The same request resumes that mutation, runs discovery again, records the note and completes the setup. No second planning mutation exists.
- **B — Some reservations saved.** The same with some reservations recorded and no generation 1. Every recorded reservation is reused unchanged, and the missing ones are reserved in the frozen order. A recorded key the order does not reserve → `review_setup_invalid`.
- **C — A Run becomes recoverable.** A new-Run planning mutation is interrupted before its note while a matching Run becomes recoverable (fixture). `ReconcileRequired` with reason `review_discovery_changed`; the invocation is never rewritten; the mutation is abandoned. The next same-request invocation begins a recovery planning mutation for that Run.
- **D — Recovery before binding.** A recovery planning mutation is interrupted before its recovered binding. The same request resumes it, re-proves the Run by discovery, and binds into that same mutation with the note `recovery_binding`. A reservation present without a binding → `review_recovery_reservation_conflict`; the Run no longer the one recoverable Run → `review_discovery_changed`.
- **E — STOP before generation 1.** A STOP during a resumed setup before generation 1 — `dirty_overlap` at step 5, or `review_checkout_unsafe` — abandons the mutation, which has no effect; a resumed Phase entry included. Legacy Phase entry keeps the live rule: a resumed legacy Phase entry is not abandoned.
- **F — After generation 1.** Once generation 1 exists, discovery is not run again, `recovery_discovery` and the recovered binding are never rewritten, and a STOP leaves the planning mutation pending.
- **No bypass.** Every resumed setup still runs the checkout capability, dirty overlap, the Context, the Policy, the publication barrier and the Review namespace readability. A fixture that fails each one stops the resumed setup exactly as it stops a begun one.

**R. Phase-entry order (P2-READY-003)**

- **A — Already expanded.** No pending mutation, the Phase already expanded, a consumed Run of it in history → `phase_already_expanded`. Discovery does not read the Run, and no recovery planning mutation is begun.
- **B — Incomplete Run.** No pending mutation, the operation admissible, a matching incomplete Run → `review_recovery_incomplete`.
- **C — Ambiguous Runs.** No pending mutation, the operation admissible, two recoverable Runs → `review_recovery_ambiguous`.
- **D — Own applied stages.** A pending review-v1 Phase-entry mutation of this very request, with its own registration stages applied, is resumed under the live interrupted-entry rule. It is never refused as `phase_already_expanded`; the unique-entry check is skipped for it, and the explicit entry's startability is checked.
- **E — Roadmap creation.** It has no remaining live acceptance checks, and discovery runs as before.
- **Earlier refusals.** A different pending request for the slot, a pending legacy record and a marker mismatch are refused at step 5 as before, ahead of every step 6 check.

**S. Readiness LOW fold-ins (P2-READY-005, -006, -018, -024, -027) and the Git minimums (P2-READY-029)**

- **Reason attribute.** Every `ReconcileRequired` P2 raises has `code == "reconcile_required"` and a `reason` from the catalogue (§25.1). A live `ReconcileRequired` on the same path has `reason` `None`. One built by existing code without `reason` still has `code` `reconcile_required` and `reason` `None`. Tests assert `.reason`.
- **Catalogue.** Every code and reason the contract names appears in §25.1, and every `ReconcileRequired` P2 raises names one of its reasons.
- **`base_exact`.**
  - A recorded Kp classified unapplied, with HEAD == `base_head`, is made after the pre-replay proof.
  - HEAD advanced by an independent commit → a mismatch, `review_registration_base_moved`, never the independent-advancement path.
  - A Kp made with its ID not saved, and a person's commit of the registration files, both classify as applied without an ID → `review_commit_unowned`.
  - A Kp recorded applied with its ID is decided by that ID.
  - A legacy commit's classification is unchanged, independent advancement included.
- **Delta record.** Every scalar of the `review-planning-delta` record has its §16.1 type:
  - the modes are the texts `"000000"` and `"100644"`;
  - the object IDs are full-length lowercase hexadecimal text; in a SHA-256 fixture repository they are 64 characters, and the zero ID is 64 `0` characters.

  A record with integer modes digests differently and fails CP9.
- **Authority text.**
  - `rules/git` carries the Git-operation rules of §26.1 and no write-scope list.
  - `skills/roadmap` carries the planning operation of §26.2; its write-scope paragraph names the Consumption path as the one exception to its static set.
  - `skills/review` carries §26.3, and names `rules/git` for the barrier and the push stage instead of restating them.
- **Git minimums (P2-READY-027, P2-READY-029).** Deterministic: the version reader is patched to report each version (fixture), and the pushed histories are built for real and run through the production barrier and committed planning proof.
  - **A — Git 2.40.0 or newer.** A new review-v1 call passes the version gate; the publication proof runs.
  - **B — Git 2.39.** A new review-v1 call → `review_git_unsupported` before the lock, nothing written, a pending mutation untouched; a legacy invocation registers as today. A legacy push of a history with no Candidate snapshot → clear. A legacy push of a history holding a snapshot and generation 1 only → registered-Run discovery runs with the publication command set, finds no registration commit, and the push proceeds. A valid Kp / Km history → the committed planning proof runs and passes → the push proceeds. An invalid Kp → the proof fails → the barrier holds.
  - **C — Exactly `P2_PUBLICATION_GIT_MIN` (2.31.0).** The publication behaviour of B.
  - **D — One version below it (2.30.9).** A history with no Candidate snapshot → cleared by the fast path. A history holding one → `review_publication_barrier`, detail "publication proof unavailable", naming no Run and no registration commit.
  - **E — An unparseable version.** A new review-v1 call → `review_git_unsupported`. A push of a history with no Candidate snapshot → clear only when the fast-path read ran and listed nothing; with that read made to fail (fixture), the barrier holds. A history holding a snapshot → `review_publication_barrier`, the capability unknown.
  - **F — Generation states.** On Git 2.31.0 or newer: generation 1 only, generation 2 only, generation 3 without a registration commit, generation 4, stale and not authorized → no registration barrier, and a legacy push proceeds in each.
  - **No attribute evaluation in the proof.** With `check-attr` made to fail (fixture) and the working tree's Review namespace removed, the outcomes of the barrier and of the committed planning proof are unchanged: they read committed objects only.
  - **One spelling.** The add-history read always runs `--diff-merges=combined`; no other spelling is ever run, on any Git (pin).

## 29. Incidental live findings outside P2

1. **Review records under checkout line-ending conversion (P1 layer).** **Measured** (§31): with this machine's system `core.autocrlf=true` and no attribute rule, a fresh clone checks out an LF-only Review record as CRLF while `git status` stays clean, and `serialize.parse_canonical` refuses it (`review_record_noncanonical`). For every Review record P2 writes, the checkout capability (§14.5) closes this: P2 writes Review records only where the committed attributes make every fresh clone reproduce the canonical bytes, proves it before writing, and refuses otherwise. No other path writes Review records at the baseline (P3 is not active). The P1 reader and the P1 documents are unchanged; this is recorded so that P3 and any subsequent Review writer carry the same precondition.
2. `gate.py:139` / `:149` print `record.get("id")` for pending generation mutations, which yields `None` (reconnaissance §6); message only.
3. The lone-CR stranding of legacy Roadmap creation and Phase entry (reconnaissance §17 item 1) remains in the legacy path; the review-v1 path refuses such input before Review (§7.6).
4. The late `dirty_overlap` of legacy Roadmap creation and Phase entry (BL-041 residual (4)) remains in the legacy path; review-v1 refuses early (§14.2).
5. A runtime lost inside a generation stage leaves a half-written stage that `validate_review` reports (Frozen P1 fail closed). P2 never repairs it and never hides it: a matching invocation stops with `ReconcileRequired` (§12.3), and a non-matching one is not refused because of it (§14.6).
6. `ReviewStore.provenance_problems` compares the accepted descriptor, the task input and the snapshot, but not the task input's `request_digest` against its own envelope, nor the envelope's `candidate` against the snapshot's material. P2 checks both wherever it relies on a task (§10.3, §12.3, CP3). This is not a P1 repair and changes no P1 document.
7. Live legacy outcomes for caller values the canonical form cannot carry, **Measured** (§31) on legacy Phase entry:
   - a float, an empty mapping key or a sequence inside a sequence → `YamlishError` from `Mutation._save` inside `MutationController.begin`, nothing recorded;
   - a non-text key → `TypeError` from `MutationController.open`'s `json.dumps(..., sort_keys=True)`, nothing recorded;
   - a lone surrogate → `UnicodeEncodeError` from the UTF-8 write, no record, but a temporary file left in `.workline/runtime/tmp/` (`durable_write_text` removes it only after an `OSError`);
   - a tuple → `begin` records the invocation, whose JSON normalization holds a list, and the next `_save` fails with `YamlishError` (`unsupported scalar type: tuple`). That leaves the Phase-entry mutation pending with no effect recorded: a `YamlishError` is not a `StopError`, so `abandon_on_stop` keeps it.

   P2 changes none of this on the legacy path; the review-v1 path refuses all of them before `_open` (§5.6).

## 30. Quality gates applied to this document

Searched, case-insensitively, after the final readiness repair round 2, for `TBD`, `TODO`, `maybe`, `either`, `alternative`, `open`, `later`, `implementation decides`, `could`, `option`:

Outside this section:

- `TBD`, `TODO`, `maybe`, `either`, `alternative`, `implementation decides`, `could`, `option`: no occurrence (substrings included);
- `later`: only inside the verbatim quotations of Frozen P1 R3 §8 in §13.3 and of Frozen P1 R2 §5 in §24;
- `open`: only as the P1 gate status literal `` `open` `` (also inside `` `status: open` ``), the live function and method names `_open` / `MutationController.open`, and inside the task's own labels "Architecture reopen" / "not reopened". None marks an unresolved item.

Also verified: no unresolved A/B choice (C-3 and C-4 name Direction A with reasons; §15.6 states why the equally strong invariant is chosen over bare equality with `use_check_head`; §18.2 chooses rule B for publication and states why rule A cannot serve); no implementation-defined identity (§6, §12.6); every mutation owner specified (§11.1, §12.4); Receipt / Consumption ordering specified (§17); commit / proof / push ordering specified (§15.1, §18); every recovery window specified (§21.1–§21.3); one projection mechanism for the pre-Kp proof, C-2(Kp) and the committed planning proof, and no second renderer (§15.7, §20); one writer-input function for every review-v1 byte producer (§7.8); every caller-value representability refusal before `_open`, and none of them described as an abandonment (§5.6); no hidden HUMAN choice (§32); no P3 activation (§2, §22); no Review-as-lifecycle authority (§22, §34.1 item 10).

Round-1 search for the superseded statements: no statement that another operation may publish Kp (§15.5, §17, §18.7 say the opposite); no statement that staleness ends without invalidation once a Receipt exists (§13.3, §19.2); no fixed three-generation sequence (the state machine of §11.6); no statement that the declared base is not re-evaluated after the use check (§13.4, §15.6, P12); no statement that a fresh clone does not matter (§14.5, §21.2 L17–L18, §29); and the checkpoint line "No push before proof: PASS" is replaced by the cross-operation lines of §32 (`C-2(Km)`, `Publication barrier`).

Round-2 search, over `fresh Candidate`, `fresh Run`, `orphan`, `never rerun`, `vacuously`, `runtime loss`, `runtime record lost`, `Km made`, `barrier clear`, `Consumption`, `publication_proof` and `C-2(Km)`, for the superseded statements:

- Km alone clears the barrier: no such statement. The barrier clears only when the committed planning proof passes for the commit being published (§18.7 rule, state table, "Ends"), and every "Km made" row says what that proof decides (§18.7, §21.1 row 29, §21.2 L14).
- Consumption existence is proof: no such statement. §4, §16.2 and §18.7 say that the existence of a Consumption, of Km or of a `publication_proof` note proves nothing; every statement of when a push may carry Kp names the committed planning proof (§15.3 P11, §15.5, §17, §21.1 rows 23, 25, 36).
- Remote presence is proof: no such statement. §17, §18.7, §21.1 row 36 and §24 (R5 §12.5) say the destination is never read as proof.
- Runtime loss of generation 1 or 2 always means a new Run: no such statement. A current generation 1 and a current authorizing generation 2 are recovered (§12.7, §21.2 L2–L5). `fresh Candidate` occurs only where §12.8 allows a new Run (§7.1, §12.8, §19.1, §21) and in §12.1, which withdraws round 1's rule; `fresh Run` does not occur.
- The same accepted task silently receives a new `task_id`: no such statement. §10.4, §12.3, §12.6, §12.7 and §24 say the reverse; `never rerun` does not occur.
- R2, R3 or R12 hold vacuously: no such statement. `vacuously` occurs only in §33.2, naming the round-1 claim that round 2 withdrew; C-6 is rewritten (§23).
- `publication_proof` occurs only as a runtime sequencing marker that is never evidence (§4, §15.1, §17, §18.2, §18.4, §18.7, §21, §23, §28 K, §32, §34), and in §33.2 as the round-1 checkpoint that round 2 demoted.
- `orphan` occurs only for the P1 legal orphan, an unreferenced snapshot or task input (§21.2 L1, §31); the chain table of §11.6 names recovery instead.

Round-3 search, over `presentation`, `layout`, `bytes`, `P4`, `delta`, `digest`, `semantic`, `path set` and `mode`, for the superseded statements:

- Presentation bytes do not matter: no such statement. §7.5 keeps display and layout out of the reviewed meaning and requires them to be exactly E; §18.8 no longer says that the committed proof need not prove Kp's bytes.
- Exact Kp bytes are not proven: no such statement. The pre-Kp proof (item 6), C-2(Kp) P3 / P4 and CP5 prove them against E (§15.7), for the planning mutation and for every Workline push alike.
- The digest of the actual delta is enough: no such statement. `registration_delta_digest` is the digest of E, computed after P3 and recomputed by CP9 (§15.7, §16.1, §16.2, §18.8).
- Semantic equality is sufficient: no such statement. §15.3, §18.8 and §20 require the physical and the semantic proof separately, each for its own dimension.
- A path and mode proof is sufficient: no such statement. P3 and CP5 compare raw blob bytes as well (§15.7); the round-2 CP5, which checked paths, statuses and modes only, is replaced.

Round-4 search, over `plan`, `design`, `caller`, `WorkSpec`, `rebuilt`, `writer input` and `condition`, for the superseded statements:

- The original plan or design is used after the Candidate freeze: no such statement. After the freeze the caller's object serves only validation and identity; the registration, the representability check, E and recovery take W (§7.8, §7.6, §15.1, §15.7, §12.4, §20).
- Writer input is rebuilt from the caller: no such statement. §15.1 step 1 feeds the registration from W, and §15.7 step 2 builds E from W's inputs.
- `WorkSpec` values are rebuilt from the design after the freeze: no such statement. `WorkSpec`, `RelatedSpec`, `RelationSpec`, `PhaseSpec` and `PhaseRelationSpec` values reach the writer only through W and the one stage-input derivation both paths share (§7.8, §20).
- The Candidate feeds E while the live writer takes the caller's object: no such statement. The registration and E take the same W (§7.8, §15.7), and the record check stays the defence against drift (§15.6).
- A condition recorded in the caller's key order: no such statement. §7.3 records it as `serialize.canonical_data` gives it, and the canonical-input preflight refuses before `_open` one the canonical form would change in anything but key order (§5.6).

Round-5 search, over `before any Review record`, `before any domain effect`, `abandon`, `review_candidate_unrepresentable`, `tuple`, `float`, `non-text`, `empty key`, `nested sequence`, `_open`, `MutationController.begin` and `freeze`, for the ordering statements:

- A caller value the canonical form cannot carry is refused only at the freeze: no such statement. §5.6 refuses it before `_open`, and §7.3, §7.6, §28 N-J and §28 O point there.
- A refusal before `_open` is described as an abandonment: no such statement. §5.4 and §14.6 now say that a readability failure at recovery discovery begins nothing, and §5.6 and §14.4 say the same of the preflight; every remaining "abandoned" concerns a planning mutation that exists (the freeze, the recovery setup, §7.6, §12).
- A lower-level serializer exception is a review-v1 outcome: no such statement. §5.6 names `TypeError`, `YamlishError` and `UnicodeEncodeError` only as what the live serialization would raise, and §29 item 7 as legacy outcomes.
- The Mutation Controller catches serializer errors: no such statement. The boundary is before `_open` (§5.6, §27).
- §7.6 moved or weakened: no such statement. It still runs after `_open` and the reservations, over the Candidate and W as built (§7.6, §5.6).

Final readiness repair round 1 search. It covered `form B`, `-text`, `text: unset`, `ProjectView.load(store).with_effects`, `canonical_first_work`, `recovery_discovery`, `begun by this run`, `resumed Phase`, `never abandoned`, `phase_already_expanded`, `review_recovery_incomplete`, `base_exact`, `registration_delta_digest`, `old_mode`, `new_mode`, `reason`, `Git version`, `minimum Git`, `write scope` and `rules/git`, looking for the superseded statements:

- **Form B accepted: no such statement.** §14.5 accepted form L alone; round 2 replaces that with the four layers of the checkout capability (below).
  - `form B` occurs only where it is withdrawn or recorded as history (§1, §4, §14.5, §21.4, §28 J, §31, §33.1, §33.6).
  - `-text` and `text: unset` occur only as refused readings, and in round 1's evidence, marked as no longer accepted. The one other `-text` is a CRLF fixture of §28 M, which concerns domain files.
- **R9 on the working tree: no such statement.** `ProjectView.load(store).with_effects` occurs only in the working-tree compatibility check, for comparison (§7.4), and in §33.6's description of the defect. Every R9 selection is on the committed basis (§7.7, §13, §15.1, §15.3, §18.8, §20), where the Candidate's `canonical_first_work` is computed.
- **Discovery never run for an incomplete setup, or the binding helper only on a mutation this run began: no such statement.** `begun by this run` does not occur. §5.3, §12.1, §12.4, §12.5, §12.8 and §12.9 give the pre-freeze resume setup: `recovery_discovery` is kept once recorded, and established on resume when missing.
- **A resumed review-v1 planning mutation never abandoned before generation 1: no such statement.** `never abandoned` occurs only for the legacy Phase-entry rule, which review-v1 does not keep in that state (§12, §26.2), and in §33.6's description of the defect.
- **Discovery before `phase_already_expanded`: no such statement.** Every order statement puts the remaining live acceptance checks first (§5.6, §11.8, §12.2, §12.7, §21, §28). `review_recovery_incomplete` after runtime loss past Kp is scoped to Roadmap creation.
- **`base_exact` as "otherwise applied": no such statement.** §15.2 and §15.6 state the classification steps, and §21.1 rows 21–22 follow them.
- **Untyped delta scalars: no such statement.** `registration_delta_digest`, `old_mode` and `new_mode` occur with the text forms of §15.7 and §16.1.
- **A `ReconcileRequired` P2 raises without its reason: no such statement in a normative section.** Every such `ReconcileRequired` names a reason of §25.1. Elsewhere, `reason` occurs in its ordinary sense, for the stale and set-aside reasons, and for live refusals, whose `reason` is `None`.
- **A Scope section of `rules/git`: no such statement.** §26 says it has none. `write scope` occurs for the Roadmap Skill's write-scope paragraph, and for the scopes of the planning and generation mutations.
- **An unstated Git version: no such statement.** §5.7 fixed 2.40.0; round 2 splits it into two minimums (below).

Final readiness repair round 2 search. It covered `form L`, `form B`, `-text`, `text=unset`, `text=unspecified`, `filter=unset`, `ident=unset`, `working-tree-encoding=unset`, `check-attr`, `checkout capability`, `Git 2.40`, `2.40.0`, `minimum Git`, `publication Git`, `candidate-snapshots`, `barrier begins`, `generation 1` to `generation 4` and `no registration`, looking for the superseded statements:

- **A printed tuple taken as proof: no such statement in a normative section.** `form L` occurs as the tuple layers 3 and 4 must print, always beside the raw committed source that proves the rule (§3, §4, §14.5, §21.4, §26.3, §27, §28 J, §32, §34.7), and in the records and evidence of the finding, round 1's marked where round 2 corrects them (§1, §30, §31, §33.1, §33.6, §33.7, §34.6).
- **A literal lookalike accepted: no such statement.** `text=unset`, `text=unspecified`, `filter=unset`, `ident=unset` and `working-tree-encoding=unset` occur only as refused or measured configurations. `-text` occurs only as a refused configuration, in round 1's evidence, and as a domain-file fixture of §28 M; `form B` only where it is withdrawn or recorded as history.
- **`check-attr` as proof of a state: no such statement.** In normative text `check-attr` occurs only as layers 3 and 4 of §14.5, the transform preflight with its driver condition (§14.3), the `check-attr --source` behind `P2_REVIEW_GIT_MIN` (§5.7), and the statement that the committed planning proof runs none (§18.8); the terms, tests, evidence and dispositions say the same.
- **A checkout capability without the raw source: no such statement.** Every `checkout capability` statement names the capability of §14.5, whose four layers begin with HEAD's raw committed `.gitattributes`.
- **One Git minimum for both capabilities: no such statement.** `2.40.0` and `Git 2.40` occur only for `P2_REVIEW_GIT_MIN` and in round 1's records; `2.31.0` only for `P2_PUBLICATION_GIT_MIN`, its audit and round 1's records. `minimum Git` occurs in the heading of §5.7 and in round 1's records. `publication Git` does not occur: the threshold is named `P2_PUBLICATION_GIT_MIN` throughout.
- **A Candidate snapshot that begins a barrier, or a refusal below the publication minimum stated as a found registration: no such statement.** `candidate-snapshots` occurs for the snapshot path and the fast path (§5.7, §7.1, §18.7, §26.1, §31), and `barrier begins` only in §33.7's statement of the start rule. Every `no registration` statement concerns the registration barrier, which a Candidate snapshot alone never begins; the capability refusal names no Run and no registration commit (§5.7, §18.7, §25.1).
- **A generation state that begins a barrier: no such statement.** `generation 1` to `generation 4` occur with "no barrier" only for the registration barrier, on a Git at or above `P2_PUBLICATION_GIT_MIN` or for a history the fast path clears: the scope rule of §18.7, the sentence before its state table, the note of §21 and §34.1–§34.2 say so.

## 31. Evidence

Probes are plain scripts (no pytest), run outside the repository; those that use Workline code run against the clone's `src` (`PYTHONPATH`) and assert that `workline` was imported from that tree. The round-1 probes build throw-away repositories only. Environment: Windows 11, Git for Windows 2.54.0.windows.1 with system `core.autocrlf=true`.

| probe | question | result |
| --- | --- | --- |
| autocrlf clone | what does a fresh clone do to an LF-only Review record? | blob LF (`git cat-file blob`); clone working tree CRLF; `git status` clean |
| hook suppression | does `-c core.hooksPath=<empty or absent dir>` suppress repository hooks for `git commit --only`? | default: a failing `pre-commit` hook ran and refused the commit; with an empty directory and with an absent directory: no hook ran, the commit was made |
| `committed_reload_probe.py` | does the production `ProjectView` read a commit's canonical files materialized from raw blobs exactly as it reads the working tree? | live Roadmap creation + Phase entry: 9 canonical files, all `100644`, committed reading == working-tree reading, `validate_structure` clean |
| reconnaissance probes 1–8 | accepted evidence (reconnaissance §18) | Direction A mechanics (probe 8), pre-reservation (probes 2, 5), reader loss (probe 1), projection equality (probe 4), lifecycle neutrality (probes 2, 5, 8) |
| checkout probe, part 1 (round 1) | which attribute conditions keep a Review record's bytes through a fresh clone under `core.autocrlf=true`, and can they be read from committed attributes alone, before the file exists? | no rule: clone CRLF, the P1 reader refuses (`review_record_noncanonical`), `git status` clean; committed `eol=lf -filter -ident -working-tree-encoding`: LF, accepted in round 1 (since final readiness repair round 2, only the canonical rule, with `!text`, is accepted, §14.5); committed `-text -filter -ident -working-tree-encoding`: LF, accepted in round 1 as form B, no longer an accepted form since the final readiness repair (§14.5); a rule only in the origin's `info/attributes`: clone CRLF, refused; committed `eol=lf` against a global `*.yaml eol=crlf`: LF; the global rule alone: CRLF, refused; `check-attr --source=HEAD` still reads `info/attributes`; the empty bare evaluation directory with alternates, `GIT_ATTR_NOSYSTEM`, and empty global configuration and attributes reads the committed rule alone (form L, the former form B, or all unspecified without a rule); `check-attr` answers for a path that does not exist |
| checkout probe, part 2 (round 1) | do clone-local sources or core settings override a committed rule? | a clone-local `info/attributes` `eol=crlf` overrides committed `eol=lf` after a re-checkout: CRLF, refused, `git status` clean, the effective evaluation shows `eol: crlf`; committed `eol=lf` and committed `-text` (no longer an accepted form, §14.5) keep LF under `core.autocrlf=false` with `core.eol=crlf`; a subsequent commit dropping the rule: a fresh clone of it CRLF, refused |
| add-detection probe (round 1) | which `git log` form lists exactly the commits that add a path — present in the commit, absent from every parent — across merges? | the default form misses a merge that itself adds a path; `--full-history --no-renames --diff-merges=combined --diff-filter=A --name-only` lists the side-branch commit adding a path and the adding merge, and lists an ordinary merge as adding nothing |
| physical projection probe (round 3) | does the production reader give the same meaning to physically different registration bytes, and does the writer's whole-ledger re-render canonicalize a ledger? | the writer's own `durable_write_text` puts exactly the canonical UTF-8 / LF bytes on disk; a Work entity file with CRLF line ends, reordered frontmatter keys, no blank line after the frontmatter, an extra trailing blank line or a quoted `display` scalar is read by `ProjectStore.read_entity` with the same meta, name and section as the canonical bytes; a `roadmap.yaml` with CRLF line ends, reordered record keys or an extra top-level key is read by `read_relation_file` as the same records, and `render_relations` of those records plus one more gives the same bytes in every case |
| writer-input probe (round 4) | does a Related condition's key insertion order reach the ledger bytes, and what does the Candidate's canonical form do with it? | `validate_condition` accepts `{"pattern": ..., "kind": ...}` and `{"kind": ..., "pattern": ...}`, and further keys with a nested mapping; the live writer (`_registration_effects`, `render_relations`) writes each condition in its insertion order at every depth, so the two ledgers differ while `read_relation_file` reads them as the same records; `serialize.canonical_data` and `parse_canonical` give both the same key order, ascending at every depth, and the same digest, and the writer fed that form writes identical bytes for both; `design_identity` keeps the caller's order and compares equal under Python equality, `json.dumps(sort_keys=True)` and `serialize.digest`; a tuple value: the live writer refuses it (`unsupported scalar type: tuple`) and the canonical form makes it a list; a float: both refuse |
| canonical-input probe (round 5) | where does each unusual condition value fail — in the durable planning invocation or in the P1 canonical form — and what does legacy Phase entry leave behind? | Through `design_identity`, `json.dumps(..., sort_keys=True)`, `yamlish.dump` and the UTF-8 write: a float or NaN, an empty mapping key and a sequence inside a sequence fail `yamlish.dump` (`_save`); integer, boolean and tuple keys fail `json.dumps(..., sort_keys=True)`; a lone surrogate, in a condition or in a Work name, fails the UTF-8 write; a tuple value and an integer key inside a sequence item pass but are changed (a list, a text key). Through the P1 form the same values are refused — `canonical_data` refuses floats and non-text keys, `canonical_bytes` refuses empty keys, nested sequences and surrogates, and a tuple fails value equality — while nested mappings in any order, extra scalar / list / mapping entries, sequences of mappings and an empty key inside a sequence item pass both ways and read back. Legacy end to end: float, empty key, nested sequence → `YamlishError`, no record; integer key → `TypeError`, no record; lone surrogate → `UnicodeEncodeError`, no record, a temporary file left; tuple → `YamlishError`, a pending mutation with no effect left; a valid nested mapping with extra entries registers |
| checkout forms probe (final readiness repair round 1) | which committed rules print each attribute tuple, and what does a fresh clone made with `core.autocrlf=true` check out for each? | the form-L rule `eol=lf -filter -ident -working-tree-encoding`: both evaluations form L, clone LF; a real `-text`: the former form-B tuple, clone LF; the literal `text=unset`: the former form-B tuple, clone CRLF; no rule, and `eol=crlf`: clone CRLF; `* text=auto` above the form-L rule: `text: auto`; with `!text` added: form L, clone LF; the literal values `text=unspecified`, `filter=unset`, `ident=unset` and `working-tree-encoding=unset` under `eol=lf`: form L printed, clone LF (Git reports an encoding error for the last and writes the bytes unchanged) — not proof, since no driver named `unset` was configured (round 2, below); `filter=lfs`: `filter: lfs`; a global attributes file `*.yaml eol=crlf` beside the committed form-L rule: both evaluations form L, clone LF |
| barrier fast-path probe (final readiness repair round 1) | is `git rev-list --full-history -n 1 <C> -- .workline/review/candidate-snapshots/` empty exactly when nothing was ever added there? | empty for a history that never touched the directory (other Review paths present); a commit listed for a side-branch addition brought in by an ordinary merge, for an evil merge adding a path, for an addition deleted afterwards, and for a root commit holding a snapshot; the add-history read of §18.7 lists the adding commit in each |
| delta types probe (final readiness repair round 1) | does the scalar type of a mode change the `review-planning-delta` digest? | `canonical_data` keeps text modes exactly; the digest of the record with text modes differs from the digest with integer modes; `000000` has no integer form |
| Git version check (final readiness repair round 1) | which release introduced each Git feature P2 needs? | the release notes installed with Git for Windows 2.54.0: `check-attr` reads `.gitattributes` from a tree-ish since 2.40.0, `log --diff-merges=<how>` since 2.31.0, `GIT_CONFIG_GLOBAL` since 2.32.0, the final leg of SHA-256 support in 2.29.0; `git check-attr -h` of 2.54 lists `--source` and `--stdin -z`. Round 2 splits the one minimum this gave (below) |
| canonical checkout probe (final readiness repair round 2) | does the exact canonical rule print form L and keep a fresh clone's Review bytes under hostile configuration, and what do the literal lookalikes, deeper files, rules after it and local overrides do? | the canonical rule: `git add` stores the written bytes; the raw check of layers 1 and 2 passes; both evaluations print form L; fresh clones byte-exact under `core.autocrlf=true`, under `core.autocrlf=false` with `core.eol=crlf`, under global attributes `*.yaml eol=crlf`, `filter=unset` with a driver `unset` whose smudge changes bytes, `ident`, `working-tree-encoding=UTF-16`, `text eol=crlf` and the legacy `crlf`, and under all of them at once as global and, separately, as system configuration; comments and blank lines after it, and `* text=auto` and `*.png binary` before it, change nothing. `filter=unset`, `ident=unset`, `working-tree-encoding=unset` and `text=unspecified`: form L printed, the raw check fails; `-text` and `text=unset`: `text: unset`, the raw check fails; `working-tree-encoding=unset`: `git add` fails. The committed literal `filter=unset` under a global driver `unset`: clone bytes changed, `git status` modified. A deeper `.workline/.gitattributes` asking `* eol=crlf`: `eol: crlf` printed, clone CRLF, layer 2 fails; the same file holding a comment: form L printed, layer 2 fails; `.workline/review/gates/.gitattributes` asking `*.yaml filter=unset`: form L printed, that directory's records changed under the driver, layer 2 fails; `.workline/.GITATTRIBUTES` asking `* eol=crlf`: committed evaluation form L, effective `eol: crlf`, a record checked out again in a fresh clone CRLF, layer 2 fails. A rule after the canonical one: layer 1 fails (`*.png binary` prints form L; `* text=auto` prints `text: auto`). `.git/info/attributes` asking `eol=crlf`: committed form L, effective `eol: crlf`. A global `attr.tree` naming the empty tree: fresh clone CRLF |
| checkout supplement probe (final readiness repair round 2) | what do attribute-source redirects do to the writing repository and to a clone, and what do the legacy `crlf` forms, a literal `working-tree-encoding=unset` over existing records, and a NUL byte in the root file do? | `attr.tree` in the global configuration and `GIT_ATTR_SOURCE`: the effective evaluation prints every attribute `unspecified`; a fresh clone under each is CRLF; a global `*.yaml -crlf` or `crlf=input`: clone byte-exact; `working-tree-encoding=unset` over records committed before the rule: `failed to encode` at checkout and at `git status`, bytes written unchanged; a NUL byte before the canonical rule line: layer 1 fails on it, the committed evaluation prints every attribute `unspecified`, and a fresh clone under `core.autocrlf=true` is CRLF |
| local lookalike probe (final readiness repair round 2) | does the effective evaluation tell a literal `filter=unset` in this repository's `.git/info/attributes` from the false state, and does the transform preflight's printed `unset` prove anything? | the canonical committed rule with `.workline/review/** filter=unset` in `.git/info/attributes`: form L printed with and without a driver `unset`; with the driver, `filter.unset.smudge` and `filter.unset.clean` are in the effective configuration and a record checked out again changes; without it, byte-exact. A committed literal `filter=unset` on a domain path prints `filter: unset`; `git add` stores the written bytes without a driver `unset` and a transformed blob with one |
| Git sources and release notes (final readiness repair round 2) | which Git accepts each spelling the proofs run, and what does Git do with each operator of the canonical rule? | `diff-merges.c` of 2.31.0 accepts `--diff-merges=combined`; `revision.c` of 2.30.0 accepts only `--diff-merges=off` and stops on any other value; the sources of 2.0.0 already parse `--full-history`, `--parents`, `--no-abbrev` (`revision.c`) and `--no-renames` (`diff.c`), and document `--raw`, `-z`, `--name-only` and `--diff-filter`; the release notes date `ls-tree --full-tree` (1.6.1.2), `hash-object --no-filters` (before 1.7.1), `merge-base --is-ancestor` (1.8.0), the final leg of SHA-256 (2.29.0), `--attr-source` (2.41.0) and `attr.tree` (2.43.0). In the 2.40.0 sources, `git_path_check_convert` looks up a driver only for a value that is not a state, `git_path_check_ident` expands only when set, `git_attr__false` is `"\0(builtin)false"`, so `git_path_check_encoding` returns no encoding for `-working-tree-encoding`, `t0028` adds a path under `-working-tree-encoding` (also in 2.18.0), and `utf8.c` `is_hfs_dotgitattributes` ignores the HFS+ ignorable code points |

Final readiness repair round 2 ran the three probes marked round 2 and read the Git sources and release notes of the last row. The probes write nothing outside their work directories, so the system attributes file (`$(prefix)/etc/gitattributes`) was not replaced; gitattributes(5) ranks it below the global file, which the probes made hostile, and the system configuration slot was made hostile through `GIT_CONFIG_SYSTEM`. Everything else round 2 relies on is Live code, cited where used (`gitcmd.commits_touching`, `gitcmd.commit_parents`, `gitcmd.commit_changes`, `gitcmd.descends_from`, `gitcmd.py:17-18`).

Final readiness repair round 1 ran the four rows marked round 1. Everything else it relies on is Live code, cited where used: `roadmap._enter_phase_locked`, `_pending_phase_entry`, `_require_resumable`, `_require_unique_entry`, `_require_startable_entry`, `_open`, `MutationController.begin` / `open`, `Mutation.reserve_id`, `abandon_on_stop`, `gitops.ensure_separable_before_effects`, `_classify_commit`, `state.startable_works`, `ProjectView`, `errors.ReconcileRequired`, the P1 exception classes of `review/*.py`, `review/adapter.py`. Beside those, the Final Implementation Readiness Check of `a6adf81` supplies one measurement. It observed that an uncommitted `phase_resumed` of a held Phase lets the live preconditions pass while the R9 selection differs between the working tree and HEAD (P2-READY-001).

Round 2 ran no new probe: what it relies on is Live code, cited where used (`mutation.py:391-395`, `gate.next_generation_scope`, `ReviewStore.provenance_problems`, and P1 `validate._candidate_snapshots` / `_task_inputs`, which treat an unreferenced snapshot or task input as a legal orphan), together with the round-1 add-detection probe for history reads.

Round 5 ran one probe, the canonical-input probe; everything else it relies on is Live code, cited where used (`roadmap.create_roadmap`, `_enter_phase_locked`, `design_identity`, `_require_resumable`, `mutation.same_request`, `MutationController.open` / `begin`, `Mutation._save`, `abandon_on_stop`, `durable_write_text`, `validate.validate_condition`, `create.validate_related_specs`, `yamlish.dump`, `review/serialize.py`).

Round 4 ran one probe, the writer-input probe; everything else it relies on is Live code, cited where used (`validate.validate_condition`, `create.RelatedSpec`, `create._registration_effects`, `store.Relation.to_record`, `yamlish.dump`, `review/serialize.py`, `roadmap.design_identity`, `roadmap._create_roadmap`, `_expand_phase`, and the invocation normalization of `mutation.py`).

Round 3 ran one probe, the physical projection probe; everything else it relies on is Live code, cited where used (`store.render_entity`, `render_body`, `render_relations`, `ProjectStore.count_entities`, `durable_write_text`, `MutationController._planned_write`, `phase_create.decide_phases`, `create._registration_effects`, `_allocated_displays`, `roadmap._create_roadmap`, `_expand_phase`, and the P1 `project_expected` protocol of `review/adapter.py`).

Kept outside the repository with the reconnaissance evidence: `D:\AIproject\workline-evidence\cases\`.

## 32. HUMAN, architecture, checkpoint

HUMAN: **None.** HUMAN-1 is resolved (A). Every choice made here, the round-1 to round-5 repairs and both final readiness repair rounds included, is an engineering choice bounded by live code and frozen text, and each has its reason stated in its section.

Architecture: Candidate 7 **RETAIN**; architecture reopen **No**; architecture blocker **None**. C-2, C-3 and C-4 close, P2-CONTRACT-001..008 are repaired, and P2-READY-001..004 and P2-READY-029 are closed, inside Candidate 7's responsibility split: Review stays a subordinate gate, the Roadmap operation stays the only top-level owner (recovery orchestration included; Review only reads and validates), Roadmap and CREATE stay the rendering authorities whose own builders the physical projection reuses and whose stage-input derivation W reuses, lifecycle stays event-derived, and the publication barrier is a publication rule over committed objects, not a Review gate on any operation.

```text
Contract baseline:              cdb152312006f6ac25533962d942ed77e2d98bd4
Round-1 contract under repair:  2f8771ae91df580453a0ebc026febe5c5a562cc0
Round-2 contract under repair:  3a8b9cf0496b230ebcb773f5905d98f529b6b313
Round-3 contract under repair:  459f431c9715c5db0c50691d63f42d90b0c70513
Round-4 contract under repair:  bbdd93d38c48eddb86ce2200e27a4cc1f774a7bb
Round-5 contract under repair:  bd2e70da24bdb44b51ad7f9f9ee795e1625050c4
Final readiness repair round 1
  contract under repair:        a6adf8106daf2a1d3f764798dc64a00d35fe12f7
Final readiness repair round 2
  contract under repair:        5e101a37fc86cd3b02c3bd0550b7e023070a5f54
P1 accepted checkpoint:         b78be1ccd778ceb2ecd97b90e2f71744bd1b3bc5
HUMAN-1:                        RESOLVED — A, per-invocation opt-in (review=PlanningReview)
C-1 .. C-6:                     CLOSED BY P2 CONTRACT (C-6 rewritten in round 2)
P2-CONTRACT-001 .. 004:         CLOSED (round 1; 001 completed in round 2) (§33)
P2-CONTRACT-005:                CLOSED (round 2) (§33)
P2-CONTRACT-006:                CLOSED (round 3) (§33)
P2-CONTRACT-007:                CLOSED (round 4) (§33)
P2-CONTRACT-008:                CLOSED (round 5) (§33)
P2-CONTRACT-004:                CLOSED AGAIN BY FINAL READINESS REPAIR ROUND 2 (§33.7)
                                (round 1's form-L closure, §33.6, superseded)
P2-READY-001 .. 003:            CLOSED (final readiness repair round 1) (§33.6)
P2-READY-004:                   CLOSED (final readiness repair rounds 1 and 2) (§33.6, §33.7)
P2-READY-029:                   CLOSED (final readiness repair round 2) (§33.7)
P2-READY-005, -006, -018, -024, -027:
                                RESOLVED (final readiness repair round 1) (§33.6); the Git minimum of -027
                                split in two by P2-READY-029 (§33.7)
R9 basis:                       the committed basis at the freeze and in every rebuild; the working-tree
                                compatibility check at the freeze; the declared base compared first (§7, §13)
Pre-freeze resume:              setup completed on the same pending mutation; discovery run again only where its
                                outcome is unrecorded; abandoned on a STOP before generation 1, begun or resumed (§12.9)
Phase-entry order:              the live acceptance checks, phase_already_expanded included, before canonical
                                recovery discovery (§5.6)
Git minimums:                   P2_REVIEW_GIT_MIN 2.40.0 (review-v1 planning, check-attr --source);
                                P2_PUBLICATION_GIT_MIN 2.31.0 (barrier discovery and the committed planning
                                proof, log --diff-merges=combined); below it, a history the fast path does not
                                clear is refused as a capability failure that asserts no registration (§5.7)
Generation contract:            Direction A — roadmap-owned generation mutations, R2/R3 unchanged;
                                G1 accept -> G2 settle -> G3 seal [-> G4 invalidate + Supersession]
Persisted-proof contract:       Direction A — Kp -> C-2(Kp) -> Consumption v2 -> Km -> C-2(Km) -> push Km
Registration base:              use_check_head; base-exact Kp on P; full currency on P's committed view
Physical projection:            Kp == E, the canonical writer's bytes on its exact parent, whole ledgers
                                included; one mechanism for pre-Kp, C-2(Kp) and CP5; semantic proof
                                separately required (§15.7)
Writer input:                   W from the canonical Candidate only, for every review-v1 byte producer;
                                no caller object reaches the writer after the freeze; legacy unchanged (§7.8)
Canonical input:                review-v1 request identity checked before _open (live validate_condition,
                                P1 serializer); a refusal begins nothing; full §7.6 still after _open (§5.6)
C-2(Km):                        reproducible over committed objects (committed planning proof, §18.8);
                                publication_proof is a runtime marker only
Publication barrier:            clears when the fast path finds no planning snapshot, or, on P2_PUBLICATION_GIT_MIN
                                or newer, when the committed planning proof passes for every registered Run; for
                                every Workline push; a Candidate snapshot alone never begins it (§18.7)
Runtime-loss recovery:          the same Run and task via canonical discovery; a new Run only when none is
                                recoverable; incomplete or ambiguous -> ReconcileRequired (§12)
Checkout capability:            the canonical rule as the last attribute rule of HEAD's raw root .gitattributes;
                                no .gitattributes below .workline/; committed + effective check-attr print form L,
                                no filter driver named unset (§14.5)
Lifecycle separation:           PASS
P1 frozen contract repair:      not required
P2 Integration Contract:        FROZEN / FINAL READINESS REPAIR ROUND 2
P2 implementation:              NOT STARTED
P2 accepted for implementation: NO (pending independent Final Implementation Readiness Re-check)
Candidate 7:                    RETAIN
Architecture reopen:            No
Architecture blocker:           None
HUMAN:                          None
P3:                             NOT STARTED
Outstanding HIGH:               0
Outstanding MID:                0
Status:                         READY_FOR_P2_FINAL_READINESS_RECHECK
```

## 33. Repair dispositions

### 33.1 Round 1 (on `2f8771a`)

The independent contract review of `2f8771a` raised four HIGH findings. Each was checked against the live code at the baseline and the frozen P1 texts before it was repaired. Only these four are repaired; every other decision of this contract stands, apart from the dependent changes listed below.

| finding | original failure, confirmed against live code and frozen text | repair | sections |
| --- | --- | --- | --- |
| P2-CONTRACT-001 — unproven Kp published by another Workline operation | "No push before proof" held only for the planning mutation's own record. Every Workline push publishes its commit with the history it was made on (`mutation._recorded_publication`), and a disjoint-scope operation (a Roadmap hold: event log only) can run in a crash window after Kp and push a descendant of Kp; the frozen §15.5 named that path itself | the publication barrier: no Workline push of any operation publishes a history holding a planning registration commit that no committed Planning Consumption binds; computed from committed objects; checked before every push stage is recorded, when a recorded push would write, and right before every push; Kp proof failure keeps it; a Supersession never clears it | §18.7, §15.5, §17, §21.1 rows 22–25, 36, §21.2 L11–L13 |
| P2-CONTRACT-002 — stale sealed Receipt left valid | staleness after the seal ended the planning mutation with generation 3 and its Receipt canonically sealed, unsuperseded and unconsumed, against Frozen P1 R3 §8 | stale after the Receipt → generation 4 (`open`) + Supersession in one stage under the same serialization, persisted before the planning mutation ends; stale before a Receipt writes nothing (no Supersession without a Receipt); the state machine G1 → G2 → G3 [→ G4] replaces the fixed 1/2/3 sequence; invalidation only while no registration stage is recorded, so it never meets a Kp | §11.2, §11.3, §11.6, §11.6.1, §13.2–§13.3, §19.2, §21.1 rows 12–16 |
| P2-CONTRACT-003 — full currency not re-proven at the registration boundary | currency was evaluated at the use check on the working tree; afterwards only the loader identity was re-checked; C-2(Kp) required only that P descend from `review_binding.head`; the live independent-advancement rule (`mutation._head_advanced_independently`) let Kp be made on a moved HEAD | the declared base read from the committed view of the exact base commit; `use_check_head` noted at the use check; the pre-Kp currency proof right before Kp is recorded and right before a recorded Kp is replayed; a base-exact Kp on its recorded parent P; C-2(Kp) proves full currency on P (P2, P12); after the registration began a difference is `ReconcileRequired`, never `stale`, with no Consumption and no publication | §7.4, §13, §15.1–§15.3, §15.6, §17, §21.1 rows 19–24 |
| P2-CONTRACT-004 — checkout conversion makes Review records unreadable | measured: under `core.autocrlf=true` without an attribute rule, a fresh clone checks out Review records as CRLF (`git status` clean) and the P1 reader refuses them; the repository commits no rule; the contract relied on P2 never reading old records, yet P2 reads the namespace through `ReviewStore` indexes | the checkout capability: the committed and the effective attributes of every Review path must be exactly form L or form B (measured; form B withdrawn by the final readiness repair, §33.6; form L as a printed tuple replaced as the proof by HEAD's raw committed source in its round 2, §33.7), before the first Review record and before every Review-writing and Git stage; every existing record must read canonically; the capability contract bound in the Context; the P1 reader and P1 documents unchanged | §5.4, §8, §14.3, §14.5, §14.6, §21.2 L17–L18, §21.3 O6 |

Dependent changes, each required by one of the four: the Context gains `checkout_capability` (004, §8); the evidence record gains two checks (004, §10.6); the generation invocation gains the `invalidate` transition and `invalidation_reason` (002, §11.2); the declared base is read from the committed view, with `review_base_uncommitted` at the freeze (003, §7.4); the `use_check_head` note, the Kp `base_exact` field and the pre-replay proof (003, §15.2, §15.6, §17); the freeze evaluates the barrier on HEAD with a push destination (001, §14.4); the Run records gain gate 4 and the Supersession (002, §3, §14.2, §18.2 M4); new codes and reasons (§25); authority text, surface map and tests (§26–§28). Planning Consumption v2 is unchanged (§16.5).

Preserved: Candidate 7 RETAIN; architecture reopen No; HUMAN-1 = A, per-invocation opt-in; the legacy default unchanged — a legacy invocation evaluates nothing new, and in a Project that never ran a review-v1 planning invocation the barrier finds no planning snapshot and refuses nothing; Review a subordinate authorization gate, never a lifecycle controller; the Roadmap operation the top-level owner; P3 not started; `state.py` reads no Review record; C-2 Planning Consumption v2, C-3 and C-4 Direction A; R9 canonical self-selection; POSIX opt-in fail-closed; legacy POSIX unchanged. No frozen P1 document was edited or needs repair (§24).

### 33.2 Round 2 (on `3a8b9cf`)

The independent contract re-review of `3a8b9cf` found P2-CONTRACT-001 only partially repaired and raised one new HIGH, P2-CONTRACT-005. Both were checked against the live code (`mutation.py`, `gitops.py`, `gitcmd.py`, `roadmap.py`, `review/records.py`, `review/store.py`, `review/gate.py`, `review/validate.py`) and the frozen P1 texts (R2 §5, R3 §3–§5, §9, R4, R5 §1.1, §12.4–§12.5, R8, R9, R12 §4) before being repaired. Only these two are repaired. P2-CONTRACT-002, -003 and -004 stay closed and unchanged.

| finding | failure, confirmed against live code and frozen text | repair | sections |
| --- | --- | --- | --- |
| P2-CONTRACT-001 — the barrier cleared before C-2(Km) was proven (round 1 was partial) | The round-1 barrier cleared when the pushed tree held a schema-valid Planning Consumption binding Kp. So the existence of Km, or of a Consumption, stood for C-2(Km), whose checkpoint was the runtime note `publication_proof`. After runtime loss before C-2(Km), the next Workline push published Km, and a hand-made Consumption cleared the barrier | C-2(Km) = M1–M6, M6 being the committed planning proof. Its durable basis is the committed objects, keyed by Kp and Km (Frozen P1 R5 §1.1). The barrier clears only when that proof passes for the exact commit being published: CP1–CP13, every Consumption claim recomputed or cross-checked. Ownership and publication are separate (rule B): the barrier needs no ownership; a planning mutation never adopts a commit it did not record. `publication_proof` is a runtime marker only | §18.1–§18.4, §18.7, §18.8, §15.3, §17, §21.1, §21.2 L11–L16, §28 K |
| P2-CONTRACT-005 — runtime loss abandoned the accepted task (new) | P2 began a new Run and a new task after runtime loss, against Frozen P1 R2 §5, R3 §4 and R12 §4, and C-6 claimed that these held vacuously | Canonical recovery discovery runs before any new Run is reserved. A recovery planning mutation (`recovery_of_review_run_id`) binds the canonical Run, task, Receipt and domain IDs through a private recovery-only helper, and continues the same Run and task. Terminal and obsolete Runs are set aside and recorded in `set_aside_runs`. Incomplete or ambiguous matches → `ReconcileRequired`. Half-written stages are never hidden. C-6 is rewritten | §12.1–§12.8, §3, §4, §5.3, §6.3, §7.1, §10.2–§10.4, §11.2, §11.8, §11.11, §13.1, §13.2, §14.4, §19, §21.2, §23, §24, §28 L |

Dependent changes, each required by one of the two:
- the §5.3 compatibility rows for the recovery key (005);
- the request envelope's `set_aside_runs` (005, §10.2);
- the task-input envelope checks at every launch (005, §10.3);
- the recovery planning mutation's generation binding (005, §11.2);
- the discovery step of the resume order (005, §11.8);
- §13.1's discovery row and §13.2's continuation of a stale-before-Receipt Run (005);
- §14.4's freeze entry (005);
- the committed-proof paragraph of §15.3 (001);
- the §16.2 note that reading proves no claim, and the §16.5 rows (both findings);
- §19's recovered-Run fields (005);
- the restructured §21 (both findings);
- new codes and the private helper (§25);
- authority text, surface map and tests (§26–§28);
- incidental item 6 (§29).

Planning Consumption v2 is unchanged (§16.5).

Round-1 repairs stay as they were. For recovery:
- **002:** recovery writes generation 4 only through the unchanged §13.3 path, for a recovered sealed Run found stale by its use check.
- **003:** recovery re-evaluates currency on HEAD's committed view (§12.2 row f, §10.3, §17), and the `use_check_head`, pre-Kp and committed-view C-2(Kp) rules apply unchanged.
- **004:** recovery runs the checkout capability and namespace readability before writing anything (§12.2 step 1, §12.4).

Preserved:
- Candidate 7 RETAIN; architecture reopen No; HUMAN-1 = A, per-invocation opt-in.
- The legacy default is unchanged: a legacy invocation runs no discovery and no proof beyond the barrier, and a Project without review-v1 registrations pays one history read per push.
- Review is a subordinate authorization and quality gate, never a lifecycle controller; the Roadmap operation stays the top-level owner, owning recovery orchestration while Review only reads and validates.
- P3 is not started; `state.py` reads no Review metadata.
- Planning Consumption v2; the G4 + Supersession invalidation; `use_check_head` and full pre-Kp currency; the committed-view C-2(Kp); the checkout capability contract.
- POSIX review-v1 fails closed; legacy POSIX is unchanged.

No frozen P1 document was edited or needs repair (§24).

### 33.3 Round 3 (on `459f431`)

The independent contract re-review of `459f431` closed P2-CONTRACT-001 and -005 and raised one HIGH, P2-CONTRACT-006. It was checked against the live code (`roadmap.py`, `phase_create.py`, `create.py`, `store.py`, `state.py`, `mutation.py`, `durable.py`, `review/adapter.py`, `review/projections.py`) and the frozen P1 texts (R5 §3.2, R8 §2–§11, R9 §3, §6–§8, R12 §11), and confirmed by the physical projection probe (§31), before being repaired. Only it is repaired; P2-CONTRACT-001 to -005 stay closed and unchanged.

| finding | failure, confirmed against live code and frozen text | repair | sections |
| --- | --- | --- | --- |
| P2-CONTRACT-006 — the committed planning proof did not prove Kp's physical bytes | CP5 checked Kp's path set, statuses and modes, CP6 its meaning, and §18.8 excluded "that Kp's bytes are exactly the effects the mutation recorded" because presentation bytes carry no reviewed meaning. The production reader gives the same meaning to CRLF, reordered or quoted frontmatter, blank-line changes and re-formatted ledgers (**Measured**), so a hand-made or foreign Kp in such bytes, with a Consumption whose `registration_delta_digest` hashed that delta, passed every CP item and cleared the barrier. That proves a delta that happened, not the delta the reviewed operation was authorized to produce, against Frozen P1 R8 §5–§7 and R9 §6–§8, which require the exact physical commit-delta proof beside semantic equality | The expected physical projection E (§15.7): every path, transition, mode and byte Kp may carry, whole ledgers included, recomputed from the committed Candidate snapshot on Kp's exact parent P by the writer's own builders and planned-write computation, never stored. One computation and one comparison serve the pre-Kp proof (new item 6), C-2(Kp) P3 / P4 and CP5; semantic equality (P5–P9, CP6) stays separately required. `registration_delta_digest` is derived from the proven E. A display base check keeps the writer's display allocation equal to E's. An upgrade proves an old registration only by reproducing E byte for byte; E unavailable holds the barrier | §15.7, §3, §4, §7.5, §7.6, §15.1, §15.3, §15.4, §15.6, §16, §17, §18.2, §18.7, §18.8, §20–§28 |

Dependent changes, each required by it:
- §15.1's sequence: the display base check, pre-Kp item 6, and the two proof dimensions of step 5;
- the §15.3 P3, P4 and P6 rows and the two paragraphs after the table;
- §15.6 item 6, with the reason `review_registration_projection_mismatch` (§25);
- the §17 use check item 9;
- the digest wording of §16.1, §16.2 and §16.5;
- §18.2's durable checkpoint; §18.7's barrier states; §18.8's CP5, CP9, coverage list, "What it does not prove" and cost;
- §20's builders, responsibilities and two proof dimensions;
- §21.1 rows 17–19, §21.2's closing paragraph, §21.3 O9;
- §22 item 6; the C-2 and C-3 rows of §23; the R1, R5, R8, R9 and R12 rows of §24;
- authority text, surface map and tests (§26–§28);
- quality gates and evidence (§30, §31).

Planning Consumption v2 is unchanged: `registration_delta_digest` keeps its field and its `review-planning-delta` encoding; only what it digests is fixed (§16.5).

Preserved:
- **001:** C-2(Km) stays M1–M6 over committed objects, now with the physical projection inside M6; the barrier stays cross-operation and clears only when the committed planning proof passes.
- **002:** generation 4 and the Supersession are unchanged.
- **003:** `use_check_head`, the base-exact Kp, full currency on P and the committed-view C-2(Kp) are unchanged; E is computed on that same P.
- **004:** the checkout capability for Review records is unchanged; the physical projection concerns domain registration files, compared as raw blobs.
- **005:** same-Run and same-task recovery is unchanged; a recovered Run's registration passes the same pre-Kp proof, C-2(Kp) and CP5.
- Candidate 7 RETAIN; architecture reopen No; HUMAN-1 = A; the legacy default is unchanged (a legacy invocation computes no E); Review is subordinate and never a lifecycle controller; the Roadmap operation is the only top-level owner; Roadmap and CREATE are the rendering authorities; P3 is not started; `state.py` reads no Review metadata; POSIX review-v1 fails closed and legacy POSIX is unchanged.

No frozen P1 document was edited or needs repair: P2 now conforms to R8 §5–§7 and R9 §6–§8 as written (§24).

### 33.4 Round 4 (on `bbdd93d`)

The independent contract re-review of `bbdd93d` closed P2-CONTRACT-006 and raised one HIGH, P2-CONTRACT-007. It was checked against the live code (`roadmap.py`, `create.py`, `store.py`, `yamlish.py`, `validate.py`, `mutation.py`, `review/serialize.py`, `review/adapter.py`) and the frozen P1 texts (R8 §3–§5, §9, §11; R9 §3–§6, §10; the P1 canonical serialization), and measured by the writer-input probe (§31), before being repaired. Only it is repaired; P2-CONTRACT-001 to -006 stay closed and unchanged.

| finding | failure, confirmed against live code and frozen text | repair | sections |
| --- | --- | --- | --- |
| P2-CONTRACT-007 — a byte-affecting writer input had two sources | The review-v1 registration handed the writer the caller's design, while E, the pre-Kp proof and CP5 rebuilt the writer input from the canonical Candidate. `yamlish.dump` renders a mapping in insertion order and `serialize.canonical_data` sorts it, so a Related condition built pattern-first was written `pattern` before `kind` while E wrote `kind` first: one Candidate, one meaning, two ledger byte sequences (**Measured**). The semantic representability check passed, and the pre-Kp record check failed only after the Review and the registration had run. Extra and nested condition entries behaved the same | W (`CanonicalPlanningWriterInput`, §7.8): on the review-v1 path the canonical Candidate record is the only source of byte-affecting writer input — mappings in the P1 canonical key order, sequences in Candidate order, every condition entry kept — computed by one function, from `canonical_data` before the snapshot is written and from the P1 strict reader afterwards, and taken by the representability check, the actual registration, E, the pre-Kp proof, C-2(Kp), recovery and the committed planning proof. The live writer is unchanged, and legacy keeps the caller's objects. A condition the canonical form would change in anything but key order is refused before Review | §7.8, §3, §4, §6.2, §7.1–§7.3, §7.5, §7.6, §12.1, §12.4, §14.4, §15.1, §15.6, §15.7, §18.8, §20–§28 |

Dependent changes, each required by it:
- §7.3's condition (recorded as `serialize.canonical_data` gives it) and §7.6's representability refusal of a condition the canonical form would change;
- §7.6 step 1, §15.1 step 1 and §15.7 step 2 fed from W; §14.4 step 2 computing W at the freeze;
- §12.1 and §12.4 (recovery writes from W), §21.2's closing paragraph;
- §15.6's note on the role of item 6, and §15.7's paragraphs on the adapter and on implementation upgrades;
- CP5's source (§18.8);
- §20's builder list and one hand-off; §22 item 11; the R8, R9 and P1-serialization rows of §24; §25's caller-object row;
- authority text, surface map and tests (§26–§28);
- quality gates and evidence (§30, §31).

No new record, field or schema: W is recomputed from the existing Candidate snapshot whenever it is needed, and Planning Consumption v2 is unchanged.

Preserved:
- **001:** the barrier stays cross-operation and clone-safe, and C-2(Km) stays M1–M6 over committed objects; W only fixes what E is computed from.
- **002:** generation 4 and the Supersession are unchanged.
- **003:** `use_check_head`, the base-exact Kp and full currency on P are unchanged; the Candidate rebuilt for currency is compared, never written from.
- **004:** the checkout capability is unchanged.
- **005:** same-Run and same-task recovery is unchanged, and it now writes from exactly the W an uninterrupted run would.
- **006:** the physical proof keeps its strength: Kp must still equal E in paths, statuses, modes, blobs and every byte, whole ledgers included, and the semantic proof stays separately required.
- Candidate 7 RETAIN; architecture reopen No; HUMAN-1 = A; the legacy default is unchanged (a legacy invocation computes no W and writes its caller's objects as today); Review is subordinate and never a lifecycle controller; the Roadmap operation is the only top-level owner and owns W; Roadmap and CREATE are the semantic and rendering authorities; P3 is not started; `state.py` reads no Review metadata.

No frozen P1 document was edited or needs repair: P2 conforms to R8 §3–§5, §9 and R9 §3–§6, §10 and to the P1 serializer as written (§24).

### 33.5 Round 5 (on `bd2e70d`)

The independent contract re-review of `bd2e70d` closed P2-CONTRACT-007 and raised one MID, P2-CONTRACT-008. It was checked against the live code (`roadmap.py`, `mutation.py`, `durable.py`, `validate.py`, `yamlish.py`, `create.py`, `review/serialize.py`) and measured by the canonical-input probe (§31), before being repaired. Only it is repaired; P2-CONTRACT-001 to -007 stay closed and unchanged.

| finding | failure, confirmed against live code | repair | sections |
| --- | --- | --- | --- |
| P2-CONTRACT-008 — the representability refusal of caller values ran after `_open` | §7.6 promised `review_candidate_unrepresentable` before any Review record or domain effect for a condition the canonical form cannot hold, but §7.6 runs after `_open`, and `_open` makes the request identity durable first: `MutationController.open` / `begin` normalize it with `json.dumps(..., sort_keys=True)`, and `Mutation._save` renders it with `yamlish.dump` and writes it as UTF-8. So a float, an empty key, a nested sequence or a lone surrogate failed with a serializer error inside `begin` (a surrogate leaving a temporary file), and a non-text key with a `TypeError` in `MutationController.open`, before §7.6 was reached (**Measured**). The same-request comparison (`same_request`) read an unserializable caller as a different request | The canonical-input preflight (§5.6): a pure check of the request identity, before the same-request comparison, §5.3, recovery discovery and `_open`. It runs the live `validate_condition` (its refusal unchanged), then the P1 serializer alone: canonical data equal to the value apart from key order, canonical bytes, read back. A failure is `review_candidate_unrepresentable` with nothing begun. The review-v1 entry order is frozen; §7.6 keeps its full check after `_open`; a refusal before `_open` is no longer described as an abandonment | §5.6, §3, §4, §5.3, §5.4, §7.3, §7.6, §7.8, §11.8, §12.2, §12.4, §14.4, §14.6, §21.3, §24–§29 |

Dependent changes, each required by it:
- §5.3 (the preflight before the comparison), §7.3 and §7.6 (the caller-value refusal moved to §5.6; §7.6 keeps the whole Candidate record's representability), §7.8 (the caller object validates through the preflight);
- the entry order in §11.8 step 1, §12.2's start and §12.4's invocation; §14.4's note that the freeze follows `_open`;
- §5.4 and §14.6: a readability failure at recovery discovery begins nothing, and only a failure at the freeze or the recovery setup abandons;
- §21.3 O10; the P1-serialization row of §24; §25's refusal row; the authority text, surface map and tests (§26–§28, with §28 N-J moved to the preflight);
- §29 item 7 (the measured legacy outcomes, unchanged by P2); quality gates and evidence (§30, §31).

No new code, record, field or schema: the preflight is a pure function over the request identity, using `validate_condition` and the P1 serializer, and the Mutation Controller is not changed for it.

Preserved:
- **001:** the publication barrier and C-2(Km) are unchanged.
- **002:** generation 4 and the Supersession are unchanged.
- **003:** full currency and the base rules are unchanged.
- **004:** the checkout capability is unchanged; its readability check at recovery discovery now states that nothing is begun there.
- **005:** same-Run and same-task recovery is unchanged; the recovering caller is preflighted before discovery, and the writer still takes W from the committed snapshot.
- **006:** the exact physical projection is unchanged.
- **007:** the canonical Candidate is still the only writer source, and key order is never a refusal: the preflight checks the caller's values against the same P1 canonical form W is built from.
- Candidate 7 RETAIN; architecture reopen No; HUMAN-1 = A; legacy unchanged (it runs no preflight and keeps its live outcomes); Review is subordinate and never a lifecycle controller; the Roadmap operation owns the preflight and the entry order; P3 is not started; `state.py` reads no Review metadata; POSIX review-v1 still fails closed first (§5.4).

No frozen P1 document was edited or needs repair.

### 33.6 Final readiness repair round 1 (on `a6adf81`)

The Final Implementation Readiness Check of `a6adf81` found four blockers, P2-READY-001..004. The independent reclassification made P2-READY-004 HIGH: it makes the positive proof of P2-CONTRACT-004 unsound. Each blocker was checked against the live code and the frozen P1 texts before it was repaired, and four probes measured what the repairs rest on (§31). The repair also fixes the five durable or authority-facing LOW items listed below.

| finding | failure, confirmed against live code | repair | sections |
| --- | --- | --- | --- |
| P2-READY-001 (MID) — the R9 basis was the working tree at the freeze, and the committed views in the proofs | §7.6 and §7.7 evaluated the R9 selection on `ProjectView.load(store).with_effects(...)`, the working tree. The declared base, every rebuild, P9, P12 and CP6 used committed views. R9 reads the Phase's lifecycle and the predecessors' states from `events/events.jsonl` (`state.py:303-320`), which no dirty-overlap check covers. So an uncommitted `phase_resumed` or `work_completed` gave a Candidate whose selection the committed proofs did not reproduce. It ended as a pending mutation stuck after generation 1, or as a Kp failing P9 behind a permanent barrier | the committed basis — HEAD's, or a rebuild's B's, committed view with W's expected effects — is the only basis of the R9 selection and of the freeze's projected checks. The freeze runs the working-tree compatibility check (`review_base_uncommitted`, one meaning). Every rebuild compares the declared base first, and the rest only with it equal (`review_candidate_mismatch`). CP7 comes before CP6, and P12 before P8/P9 | §3, §7.1, §7.4, §7.6, §7.7, §7.8, §12.2, §12.5, §13, §13.1, §13.5, §15.1, §15.3, §15.4, §15.6, §17, §18.8, §20, §22, §28 P |
| P2-READY-002 (MID) — no rule for a planning mutation interrupted before its first review-v1 save | `_open` saves twice before any review-v1 step (`mutation.py:1693-1711`, `roadmap.py:260`); the discovery note and the recovered binding are saves of their own after those. On resume "nothing of §12 runs", the binding helper ran only on a mutation this run began, and a resumed Phase entry was never abandoned. So a Phase entry stayed pending for good, blocking START and every operation that declares its ledgers | the pre-freeze resume setup (§12.9). The same mutation completes its setup, and discovery runs again only where its outcome is unrecorded. A new Run to which discovery now answers "a recoverable Run exists" is `review_discovery_changed`, and is never rewritten. Recorded reservations are reused, and a recovery binds on resume. The helper's precondition no longer depends on the process that began the mutation, and the `recovery_binding` note is added. Before generation 1, a review-v1 planning mutation is abandoned on every STOP, begun or resumed. Legacy is unchanged | §3, §4, §5.3, §11.8, §12, §12.1, §12.4, §12.5, §12.8, §12.9, §14.4, §21.1, §21.4, §28 Q |
| P2-READY-003 (MID) — the entry order contradicted itself | §5.6 step 4 ran discovery before the remaining live checks. §11.8, §12.2, §12.7, §21 and §28 put `phase_already_expanded` first — the round-5 text; `bd2e70d` had discovery after the live entry checks | one order (§5.6): the argument, platform and Git version checks; the live checks up to the identity; the preflight; the same-request and marker checks; the remaining live acceptance checks, under the live interrupted-entry rule; discovery only with no pending planning mutation; `_open`; setup. Outcomes that assumed discovery for an already expanded Phase are scoped to Roadmap creation | §5.3, §5.6, §11.8, §12.2, §12.7, §21.2, §28 G, L, R |
| P2-READY-004 (HIGH) — form B cannot positively prove LF bytes | `git check-attr` prints `text: unset` both for a real `-text` and for the literal `text=unset`, which Git converts like an unspecified `text`. Under the literal rule both evaluations printed form B, and a fresh clone under `core.autocrlf=true` got CRLF (**Measured**). P2-CONTRACT-004's positive fresh-clone proof was unsound | form B is withdrawn, and form L is the one accepted form. `-text` and `text=unset` are refused, with every other reading that is not form L. The measured `-text` evidence is marked as no longer accepted. `!text` is given for repositories with a broader `text` rule (Measured). P2-CONTRACT-004 is closed again | §3, §4, §8, §14.5, §21.4, §24, §28 J, §31, §33.1 |
| P2-READY-005 (LOW, folded in) — no reason carrier | `ReconcileRequired` has a fixed `code` and only a message (`errors.py:38-42`) | the keyword-only attribute `reason`, with `code` unchanged. Every `ReconcileRequired` P2 raises names a reason, listed in the catalogue of §25.1 | §5.3, §10.3, §10.4, §11.5, §11.6, §11.8, §11.10, §13, §13.1, §13.5, §17, §18.4, §18.5, §21.3, §25, §25.1, §27, §28 S |
| P2-READY-006 (LOW, folded in) — `base_exact` wording | "otherwise applied with an unexpected result", read literally, classified every Kp that was made as a mismatch, and left the pre-replay trigger undefined | `base_exact` removes only the independent-advancement step (`mutation.py:2014-2015`); the other steps decide as they do for any commit. The pre-replay proof runs for a Kp classified unapplied; a mismatch is `review_registration_base_moved` | §15.2, §15.6, §21.1 rows 21–22, §28 S |
| P2-READY-018 (LOW, folded in) — delta scalar types | the `review-planning-delta` record left modes and object IDs untyped, and the digest differs between text and integer modes (**Measured**) | modes are text of six octal characters; object IDs are full lowercase hexadecimal text in the repository's object format; status is `A` or `M` | §15.7, §16.1, §18.8 CP9, §28 S |
| P2-READY-024 (LOW, folded in) — authority routing | §26.1 item 4 put the write-scope rule in `rules/git`, which has no Scope section; the static write-scope paragraph is the Roadmap Skill's (`skills/roadmap/SKILL.md:466-476`). Several rules had two owners | one owner per rule: `rules/git` for the Git-operation rules; `skills/roadmap` for the planning operation and its write scope, with one stated exception for the Consumption path; `skills/review` for the meaning of records and proofs, now including the checkout capability | §26, §27, §28 S |
| P2-READY-027 (LOW, folded in) — minimum Git | no minimum Git version was stated. The barrier's add-history read needs `--diff-merges` (2.31.0), and the checkout evaluation needs `check-attr --source` (2.40.0) | Git 2.40.0, with `review_git_unsupported` before the lock. The barrier's fast path is answered by every Git, so legacy histories are unaffected; for any other history the barrier holds on an older Git | §2, §5.4, §5.6, §5.7, §18.7, §21.4, §25, §26.1, §27, §28 S |

Dependent changes: the status line and the header; the §1 baseline row; the quality gates, evidence, checkpoint and cross-finding sections (§30, §31, §32, §34.6).

The other LOW findings of the readiness check are not repaired here. P2-READY-007..017, -019..023, -025, -026 and -028 stay implementation notes, unchanged by this repair, except that the catalogue of §25.1 now lists each code's states.

Preserved:
- P2-CONTRACT-001, -002, -003, -005, -006, -007 and -008 stay closed; §34.6 checks each against this repair.
- Candidate 7 RETAIN; architecture reopen No; HUMAN-1 = A.
- Legacy planning unchanged by default: a legacy invocation runs no preflight, no discovery, no R9 of its own and no Git version gate, and in a history without a planning snapshot the barrier's fast path clears it on any Git.
- Review is a subordinate gate and never a lifecycle controller; the Roadmap operation stays the top-level owner.
- Planning Consumption v2; G1 → G2 → G3 [→ G4 + Supersession]; Kp → C-2(Kp) → Consumption → Km → C-2(Km) → publication; W and E; semantic and physical proof, each required on its own.
- P3 not started; `state.py` reads no Review metadata.

No frozen P1 document was edited or needs repair.

Final readiness repair round 2 (§33.7) found that form L, read from `check-attr`, still did not tell a false state from a literal value, and moved the proof to HEAD's raw committed `.gitattributes`; it also split the one Git minimum of P2-READY-027 in two (P2-READY-029).

### 33.7 Final readiness repair round 2 (on `5e101a3`)

The independent re-check of `5e101a3` found two findings unresolved, P2-READY-004 (HIGH) and P2-READY-029 (MID). P2-READY-001..003 stay closed, and no other LOW item is folded in. Both findings were confirmed by probes and against the Git sources before they were repaired (§31).

| finding | failure, confirmed | repair | sections |
| --- | --- | --- | --- |
| P2-READY-004 (HIGH) — form L cannot tell a false state from a literal value | round 1 accepted form L, a tuple printed by `git check-attr`. `check-attr` prints a literal value with the word that stands for a state: `filter=unset`, `ident=unset` and `working-tree-encoding=unset` print what `-filter`, `-ident` and `-working-tree-encoding` print, and `text=unspecified` prints what `!text` prints. Under the committed literal `filter=unset`, both evaluations printed form L, and a fresh clone whose configuration defines a filter driver named `unset` ran it on the Review records (**Measured**: bytes changed). A deeper `.gitattributes`, and a literal in this repository's `info/attributes`, did the same. P2-CONTRACT-004's positive proof was unsound again | one supported configuration, proven from raw committed source: the canonical Review-attribute rule `.workline/review/** !text eol=lf -filter -ident -working-tree-encoding` as the last attribute rule of HEAD's root `.gitattributes`, read from committed objects (layer 1); no `.gitattributes` below `.workline/`, names compared folded (layer 2); the committed evaluation as a cross-check (layer 3); the effective evaluation of this repository, with no filter driver named `unset` configured (layer 4). The transform-attribute preflight gains the same driver condition (§14.3). The fresh clone is defined. Unsupported is not unsafe: `-text`, `text=unset`, `text=unspecified` and the literal `unset` values are refused as unsupported. Measured on Git 2.54 and read in the 2.40.0 sources (§31) | §3, §4, §8, §14.3, §14.5, §21.2, §21.4, §24, §26.3, §27, §28 J, §31 |
| P2-READY-029 (MID) — one Git minimum contradicted the barrier's start rule | round 1 froze Git 2.40.0 for review-v1 planning and for the committed planning proof, and held the barrier on an older Git for every history the fast path did not clear. The barrier begins only with a registration commit, and generation 1 to 4, not-authorized and stale Runs begin none; yet on a Git older than 2.40.0 a history holding only a Candidate snapshot was held as if it were registered. 2.40.0 is needed only by `check-attr --source` of the checkout capability, which the committed planning proof never runs | two minimums. `P2_REVIEW_GIT_MIN` = 2.40.0 for an explicit review-v1 invocation (`review_git_unsupported` before the lock, as in round 1). `P2_PUBLICATION_GIT_MIN` = 2.31.0, the newest feature of the audited publication command set (`git log --diff-merges=combined`; 2.30.0 accepts only `off`), which also covers SHA-256 (2.29.0). Every push runs the fast path first, with no P2 minimum. On Git 2.31.0 or newer, registered-Run discovery classifies the history, and a Candidate snapshot without a registration commit begins no barrier. Below it, or on an unknown version, publication of such a history is refused as a capability failure (`review_publication_barrier`, the proof unavailable) that names no Run and asserts no registration. Git 2.31 to 2.39 cannot begin review-v1 planning, and can prove and publish existing P2 history | §2, §3, §4, §5.7, §18.7, §18.8, §21, §24, §25, §25.1, §26.1, §26.2, §26.3, §27, §28 E, §28 G, §28 S, §32, §34.1, §34.2, §34.7 |

Dependent changes: the status line and the header; the §1 baseline row; the quality gates, evidence, checkpoint and cross-finding sections (§30, §31, §32, §34.7); round 1's measured statements, search results and cross-check marked where round 2 corrects them (§14.5, §30, §31, §33.1, §34.6).

P2-CONTRACT-004: **CLOSED AGAIN BY FINAL READINESS REPAIR ROUND 2.** The canonical rule's operators are proven from HEAD's raw committed bytes, whatever filter drivers a clone's configuration defines: the whole class of literal lookalikes is refused, not only the driver this repository happens to lack.

Preserved:
- P2-READY-001 (committed R9 basis), P2-READY-002 (pre-freeze resume setup) and P2-READY-003 (Phase-entry admissibility before discovery) stay closed, their rules unchanged; §34.7 checks each.
- P2-CONTRACT-001, -002, -003, -005, -006, -007 and -008 stay closed.
- P2-READY-005, -006, -018, -024 and -027 stay resolved; only the Git minimum of -027 is split in two.
- Candidate 7 RETAIN; architecture reopen No; HUMAN-1 = A; HUMAN None.
- Legacy planning unchanged by default: a legacy invocation runs no version gate and no checkout evaluation, and a history that never held a planning Candidate snapshot publishes on any Git.
- Review is a subordinate gate and never a lifecycle controller; the Roadmap operation stays the top-level owner; P3 not started; `state.py` reads no Review metadata.

No frozen P1 document was edited or needs repair.

## 34. Cross-finding consistency

### 34.1 Round-1 questions, answered for the final contract

1. **When does the cross-operation publication barrier begin?** When a registration commit of a planning Run — Kp, or anyone's commit of that Run's reserved registration paths — enters the history of a commit Workline would publish (§18.7). Nothing earlier begins it: generation commits, the Receipt, generation 4 and a registration held only in the working tree carry no registration commit. A Candidate snapshot alone never begins it; on a Git below `P2_PUBLICATION_GIT_MIN`, the publication of a history holding one is refused as a capability failure, which begins no barrier and asserts no registration (§5.7).
2. **What canonical state makes it observable after a crash?** Committed Git objects only: the Candidate snapshot added in the published history (committed by generation 1, and required at the use check to be committed at the commit the registration builds on, §17 item 6), and the commit adding the reserved registration paths. It clears only when the committed planning proof proves Kp, its Consumption and Km from those objects (§18.8). No runtime record, note, message, branch position or remote state takes part.
3. **How does G4 invalidation affect that barrier?** It does not. Generation 4 is written only while no registration stage is recorded (§13.3), so a Run with generation 4 has no registration commit. The committed planning proof refuses any Supersession anywhere in the history (CP2, CP4, CP13).
4. **Can G4 ever clear a barrier protecting an already-created unproven Kp?** No, on two independent grounds. Generation mutation 4 is never started once a registration stage is recorded (§11.10, §13.4). And only the committed planning proof clears a barrier, which a superseded Receipt always fails. A Supersession can only keep a barrier.
5. **What happens when C-2(Kp) fails?** `ReconcileRequired`; no Consumption; the planning mutation stays pending and every retry repeats the same proof; no generation 4. The barrier holds for every history holding Kp, for every Workline operation. There is no reset, rebase or amend; a person reconciles (§15.5, §21.1 row 24).
6. **What happens after runtime-record loss?** (§12.7, §21.2)
   - generation 1 only: if current, the same Run and task are recovered and the same `task_id` launched again; if stale, it is set aside and a new Run begun. No barrier.
   - generation 2: if authorizing and current, the same Run is recovered with no reviewer call and continues to generation 3; if not authorizing, or stale, it is set aside and a new Run begun. No barrier.
   - sealed generation 3, no Kp: the same Run and Receipt are recovered into the use check (registration, or generation 4 when stale). No barrier.
   - Kp, no Consumption: `ReconcileRequired`; never recovered, never a new Run. The barrier holds for good; a person reconciles.
   - Km, not published: the committed planning proof decides at every push. If it passes, the Run is terminal (`consumed`) and the next Workline push publishes Km. If it fails, `ReconcileRequired`, and the barrier holds. The lost `publication_proof` note is never assumed.
7. **Can another Workline operation push at each state?**
   - Generation 1 to 4, not authorized, stale, registration only in the working tree: yes on a Git at or above `P2_PUBLICATION_GIT_MIN` (below it, only for a history the fast path clears), and its commit carries only its own paths.
   - Kp without its proof: no.
   - Km: only where the committed planning proof passes for the commit being pushed.
   - Commits between Kp and Km: never by their own push.
   - Km published: yes, subject to the same proof at every subsequent push.
8. **Can a fresh clone correctly identify the state?** Yes. The barrier and the committed planning proof read the same objects in any clone. Discovery reads the committed Run records and recovers or sets aside by the same rules as after any runtime loss (§21.2 L17), as long as the checkout capability held at the commits P2 wrote. Where a clone's checkout semantics are unsafe, a review-v1 call stops at discovery's readability step or at the setup, before it writes anything (L18), and the barrier is unaffected.
9. **What if checkout semantics cannot preserve canonical Review bytes?** Review-v1 planning is unavailable in that repository: `review_checkout_unsafe`, `review_checkout_unknown` or `review_namespace_unreadable` at discovery's readability step, before the first Review record, or before the next Review-writing stage of a pending planning mutation. Nothing is normalized; the P1 reader is unchanged; legacy planning and the barrier are unaffected.
10. **Does any repair make Review lifecycle truth?** **No.** `state.py`, `ProjectView` and every lifecycle derivation read no Review record. Generation 4, the Supersession, a recovered Run and `set_aside_runs` change no lifecycle fact. The barrier, the committed planning proof and recovery discovery decide only what a push may publish and which Run a gated call continues (§22).

### 34.2 Round-2 joint review of P2-CONTRACT-001 and P2-CONTRACT-005

| runtime loss after | P2-CONTRACT-005 (which Run continues) | P2-CONTRACT-001 (what may be published) |
| --- | --- | --- |
| generation 1 | the same Run and task, when current (§12.7) | no barrier: nothing registered |
| generation 2 | the same Run, when authorizing and current; otherwise set aside | no barrier |
| generation 3, no registration | the same Run and Receipt, into the use check | no barrier until a registration commit exists |
| Kp | none: `ReconcileRequired` (§12.2 row b) | the barrier holds for every history holding Kp |
| Km, before a provable C-2(Km) | none: terminal only if the committed planning proof passes; otherwise `ReconcileRequired` | the committed planning proof decides at every push; a new Run is never used to get past it, because the barrier reads the history, not the Run a call continues |
| Km, C-2(Km) provable | none (terminal `consumed`); what the new invocation means is the live Roadmap rule | publishable by any Workline push whose committed planning proof passes |

The "no barrier" rows speak of a Git at or above `P2_PUBLICATION_GIT_MIN`; below it, a push of any history the fast path does not clear is refused as a capability failure (§5.7, §18.7).

The round-2 repairs weaken no round-1 guarantee:
- **Lifecycle:** recovery uses no Review metadata as lifecycle truth (§22 items 1 and 10).
- **Checkout capability (004):** recovery never weakens it; it runs it before writing (§12.4).
- **G4 (002):** recovery never bypasses G4; a recovered sealed Run found stale is invalidated exactly by §13.3.
- **Currency (003):** recovery never bypasses the currency proof (§12.2 row f, §10.3, §17, §15.6).
- **Candidate IDs:** recovery never allocates replacement Candidate IDs (§12.5).
- **Superseded Receipts:** recovery never consumes a superseded Receipt (row a of §12.2; CP2, CP4, CP13; §16.2).

A new Run never makes an unproven Kp or Km history publishable.

### 34.3 Round-3 check of P2-CONTRACT-006 against P2-CONTRACT-001 to -005

| closed finding | what the exact physical projection changes there |
| --- | --- |
| 001 C-2(Km) and the barrier | C-2(Km) is still reproducible over committed objects: E is recomputed from the Candidate snapshot and P's tree in any clone. The barrier still applies to every Workline push and clears only when the committed planning proof passes, which now includes CP5; the existence of Km or of a Consumption, or a digest it carries, still proves nothing |
| 002 generation 4 and the Supersession | nothing: E concerns registration commits, which never coexist with generation 4 (§13.3) |
| 003 base and currency | nothing weakened: E is computed on the same P the base rules fix and currency is proven on; pre-Kp item 6 adds the physical precondition beside currency, and a commit that shifts E's base is refused before Kp exists |
| 004 checkout capability | nothing: it governs Review records. E compares domain registration files as raw blobs, so a CRLF checkout of a domain file never reaches E, and a CRLF blob fails it |
| 005 runtime-loss recovery | nothing in the recovery rules: a recovered Run registers through the same pre-Kp proof, C-2(Kp) and CP5, and after runtime loss the barrier recomputes E from committed objects; no recovery and no new Run makes a noncanonical Kp publishable |

Lifecycle: E is computed in a scratch materialization and read by nothing that decides lifecycle (§22 item 6). Review gains no authority: the adapters render only through Roadmap's and CREATE's own builders, and `review/` renders nothing (§20).

### 34.4 Round-4 check of P2-CONTRACT-007 against P2-CONTRACT-001 to -006

| closed finding | what the canonical writer input changes there |
| --- | --- |
| 001 C-2(Km) and the barrier | nothing weakened: the barrier and C-2(Km) still read committed objects only, and E is still recomputed in any clone — now from W over the committed snapshot, which is what the writer used |
| 002 generation 4 and the Supersession | nothing: W concerns registration, which never coexists with generation 4 |
| 003 base and currency | nothing: currency still rebuilds the Candidate from the invocation and compares it with the snapshot; the rebuilt record is compared, never written from |
| 004 checkout capability | nothing: W is computed from the Candidate record the P1 strict reader returns, whose bytes the checkout capability already protects |
| 005 runtime-loss recovery | the same Run and task, now with the same writer input: a recovered registration takes W from the committed snapshot, the W an uninterrupted run would take; the caller object of the recovering invocation writes nothing |
| 006 exact physical projection | strengthened, never weakened: E and the actual registration now have one input, so Kp == E is the expected outcome of every correct run, and the record check, P3 and CP5 still compare every byte |

Lifecycle: W is writer input only and is read by nothing that decides lifecycle (§22 item 11). Review gains no authority: W belongs to the Roadmap-owned flow, and its derivation is the one `_create_roadmap` and `_expand_phase` already use (§7.8, §20).

### 34.5 Round-5 check of P2-CONTRACT-008 against P2-CONTRACT-001 to -007

| closed finding | what the canonical-input preflight changes there |
| --- | --- |
| 001 C-2(Km) and the barrier | nothing: the preflight runs before `_open` and touches no commit, proof or push |
| 002 generation 4 and the Supersession | nothing |
| 003 base and currency | nothing: currency, the use check and the pre-Kp proof run after `_open`, as before |
| 004 checkout capability | nothing weakened: the checkout capability still runs at the freeze and the recovery setup; the wording of a readability failure at discovery is corrected to "nothing begun" |
| 005 runtime-loss recovery | the recovering caller is preflighted before discovery, so an unrepresentable caller leaves a recoverable Run untouched; a representable one recovers the same Run and task, and the writer takes W from the committed snapshot |
| 006 exact physical projection | nothing: E, the record check, P3 and CP5 are unchanged |
| 007 canonical writer input | kept: the preflight judges the caller's values by the same P1 canonical form, key order is never a refusal, and W is still built from the canonical Candidate alone |

Lifecycle: the preflight reads no Project state and decides no lifecycle. Review gains no authority: the preflight belongs to the Roadmap-owned entry, and the P1 serializer only defines the canonical representation it is measured against.

### 34.6 Final readiness repair check against P2-CONTRACT-001 to -008

| closed finding | what the final readiness repair changes there |
| --- | --- |
| 001 C-2(Km) and the barrier | nothing weakened. The barrier gains a fast path that clears only a history that never touched the candidate-snapshot directory — where step 1 found nothing before. It holds on a Git too old to run the committed planning proof (round 2: below `P2_PUBLICATION_GIT_MIN`, as a capability refusal that asserts no registration, §33.7). CP7 is evaluated before CP6 |
| 002 generation 4 and the Supersession | nothing: a declared-base change after the seal is invalidated by §13.3 as before, now reached by §13 item 3 before any R9 comparison |
| 003 base and currency | refined, never weakened. Every rebuild compares the declared base first, and the rest of the Candidate — the R9 selection on the committed basis included — only with it equal. The base rules of §15.6 are unchanged, and the freeze now also proves that the working tree gives the declared base HEAD gives |
| 004 checkout capability | closed again: form L alone. Every committed rule that prints form L keeps LF bytes in a fresh clone (**Measured**), the P1 strict reader is unchanged, and nothing is normalized. Round 2 corrects this: a rule that prints form L does not keep them when it holds the literal `filter=unset` and a clone defines a driver named `unset`, so the proof moved to the raw committed source (§33.7, §34.7) |
| 005 runtime-loss recovery | completed. A recovery planning mutation interrupted before its binding binds on resume (§12.9), and a new-Run mutation interrupted before its discovery note records it on resume. Discovery never runs for a mutation that has started a generation mutation. The same Run and the same task are continued as before |
| 006 exact physical projection | nothing weakened: E, the record check, P3 and CP5 are unchanged, and the `review-planning-delta` record now fixes the scalar types its digest always depended on |
| 007 canonical writer input | kept: W is still the one writer input. At the freeze it is computed before the R9 selection is added to the Candidate, and it never reads that selection |
| 008 canonical-input preflight | kept: the preflight still runs right after the request identity is computed (§5.6 step 4), before the same-request check, and only the order after that check is made single |

**The four repairs together.** A review-v1 Phase entry now runs in this order:
1. the argument, platform and Git version checks;
2. the live checks up to the request identity;
3. the canonical-input preflight;
4. the same-request and marker checks;
5. the remaining live acceptance checks, under the live interrupted-entry rule;
6. with a pending planning mutation of this request, `_open` resumes it and the pre-freeze resume setup completes its setup; with none, canonical recovery discovery runs, then `_open`;
7. the freeze on the committed basis, with the working-tree compatibility check;
8. generation 1 and the Review flow.

The joint properties:
- The R9 selection is never taken from the working tree.
- The pre-freeze resume setup runs every freeze check in full: the checkout capability, dirty overlap, the Context, the Policy, the publication barrier and the Review namespace readability.
- Admissibility is decided before discovery, and the setup runs after `_open`. So discovery never runs for an inadmissible operation, and runs once per invocation at most.
- The form-L rule is checked at every freeze, including the one the setup runs again, and at every Review-writing and Git stage (round 2: the checkout capability in its four layers, §14.5).
- `review_git_unsupported` comes before all of them, before the lock.
- The checkout repair leaves the P1 strict reader, and its canonical bytes, unchanged.

Lifecycle: the committed basis and the working-tree compatibility check are read by nothing that decides lifecycle (§22 items 4 and 6). The pre-freeze resume setup changes no lifecycle fact, and the reason attribute is an exception field only. Review gains no authority: the entry order, the setup and the R9 basis belong to the Roadmap operation, and `skills/review` keeps only the meaning of records and proofs (§26).

### 34.7 Final readiness repair round 2 check against P2-CONTRACT-001 to -008 and P2-READY-001 to -003

| closed finding | what round 2 changes there |
| --- | --- |
| 001 C-2(Km) and the barrier | nothing weakened. The barrier still clears only when the fast path lists nothing or the committed planning proof passes. Below `P2_PUBLICATION_GIT_MIN`, publication of a history the fast path lists is refused as a capability failure that asserts no registration; round 1 held it below 2.40.0. On Git 2.31 to 2.39 the proof runs, and a Run that registered nothing begins no barrier, as the start rule of §18.7 always said |
| 002 generation 4 and the Supersession | nothing |
| 003 base and currency | nothing |
| 004 checkout capability | closed again: the canonical rule proven from HEAD's raw committed bytes, no `.gitattributes` below `.workline/`, form L as a cross-check, and no filter driver named `unset` in this repository; the P1 strict reader unchanged; nothing normalized |
| 005 runtime-loss recovery | nothing weakened: recovery still runs the checkout capability before writing (§12.4), now in its four layers; §21.2 L17–L18 follow the fresh-clone definition of §14.5 |
| 006 exact physical projection | nothing: E, the record check, P3 and CP5 read raw blobs and evaluate no attribute |
| 007 canonical writer input | nothing |
| 008 canonical-input preflight | nothing: it still runs before `_open`; the Git version check of §5.6 step 1 is the `P2_REVIEW_GIT_MIN` gate |
| READY-001 committed R9 basis | nothing: the committed basis and the working-tree compatibility check are unchanged |
| READY-002 pre-freeze resume setup | nothing weakened: every resumed setup still runs the checkout capability, now in its four layers, and a STOP before generation 1 still abandons |
| READY-003 Phase-entry order | nothing: the order of §5.6 is unchanged, and its step 1 is the review-v1 minimum |

**The two repairs together.** They do not couple the two capabilities:
- The checkout capability is needed to write and use canonical Review records through a review-v1 planning operation, and it requires `P2_REVIEW_GIT_MIN`.
- The committed planning proof reads raw committed blobs, evaluates no attribute, needs no safely checked-out Review bytes, and runs on `P2_PUBLICATION_GIT_MIN`. It never depends on `git check-attr --source` or on the checkout's Review namespace.
- So a Git from 2.31.0 up to, not including, 2.40.0 cannot begin or resume review-v1 planning, and can still run the publication barrier over committed P2 history.

**Quality gate for P2-READY-004.** Every answer is yes:
1. *Can the implementation tell `-filter` from `filter=unset`?* Yes. Layer 1 compares the bytes of HEAD's committed rule line with the canonical rule, and `filter=unset` is not those bytes (§14.5; §28 J B, K).
2. *`-ident` from `ident=unset`?* Yes, by the same comparison (§28 J C).
3. *`-working-tree-encoding` from the literal `working-tree-encoding=unset`?* Yes, by the same comparison (§28 J D).
4. *Is that distinction derived from raw committed attribute source, not from the word `check-attr` prints?* Yes. Layers 1 and 2 read HEAD's committed objects (`ls-tree`, `cat-file`); `check-attr` is a cross-check (layers 3 and 4).
5. *Can a deeper committed `.gitattributes` override the safe root rule?* No. Layer 2 refuses every entry below `.workline/` whose name folds to `.gitattributes`, whatever the evaluations print (§14.5 layer 2; §28 J F).
6. *Does the current `.git/info/attributes` stay covered by the effective evaluation?* Yes. Layer 4 evaluates every source of this repository, `info/attributes` included (§28 J J), and requires that no filter driver named `unset` is configured, so a literal lookalike there cannot hide a transformation of the bytes (**Measured**, §31).
7. *Is a normal fresh clone under hostile global and system configuration shown to keep the canonical LF bytes?* Yes, byte for byte: under `core.autocrlf=true`; under `core.autocrlf=false` with `core.eol=crlf`; under hostile global `eol`, `filter` with a driver `unset`, `ident`, `working-tree-encoding`, `text` and legacy `crlf` rules; and under all of them at once as global and as system configuration (**Measured**, §31). A clone configured to read its attributes from another tree does not read the committed `.gitattributes`, so like a clone-local `info/attributes` it is outside the fresh-clone definition: the contract claims no protection there (§14.5), and the effective evaluation refuses such a redirect in this repository.

**Quality gate for P2-READY-029.** Every answer is yes:
1. *Is there one explicit review-v1 planning minimum?* Yes: `P2_REVIEW_GIT_MIN` = 2.40.0 (§5.7).
2. *Is there a separately justified publication-proof minimum?* Yes: `P2_PUBLICATION_GIT_MIN` = 2.31.0, the newest feature of the audited command set, with SHA-256 covered (§5.7, §31).
3. *Can Git 2.31 to 2.39 classify an existing P2 history without `check-attr --source`?* Yes: the command set runs no `check-attr`, and the proof reads committed objects only (§5.7, §18.8).
4. *Does a Candidate snapshot alone stay insufficient to begin a registration barrier?* Yes (§18.7 "Begins" and the state table).
5. *On a Git that supports the publication proof, can a generation-1-only history publish?* Yes (§18.7 state table; §28 S B, F).
6. *Does a too-old Git fail closed without claiming that a registration exists?* Yes: `review_publication_barrier` with the proof-unavailable detail, naming no Run and no registration commit (§5.7, §18.7, §25.1; §28 S D, E).
7. *Does a legacy-only history keep publishing without a P2 minimum?* Yes: the fast path clears it on any Git (§5.7, §18.7; §28 S B, D).

Lifecycle: the checkout capability and the Git minimums decide only whether a review-v1 call may write Review records and whether a push may publish; nothing that decides lifecycle reads them (§22). Review gains no authority: `rules/git` owns both Git minimums, the Roadmap Skill names the review-v1 minimum, and the Review Skill owns what the checkout capability and the proofs mean (§26).
