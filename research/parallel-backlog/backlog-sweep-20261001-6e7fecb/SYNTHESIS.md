NON-CANONICAL RESEARCH ARTIFACT
DO NOT MERGE INTO MAIN
Research baseline: 6e7fecb784a6ba1f49586761ab1038aa47d1738b

# Parallel Backlog Research Synthesis

Run `backlog-sweep-20261001-6e7fecb`. Parent: Opus 5.5 (orchestration, cross-check, synthesis). Workers: four Sonnet 5.5 researchers (R1-R4). This document freezes nothing, amends nothing and authorizes nothing. `BACKLOG.md` is not authority. The only normative authority is `registry.md` and the canonical Skills it routes. Every semantic choice that the evidence does not decide is listed in section 9 as GPT_REVIEW_REQUIRED.

Worker reports (detailed evidence, citations, tags) sit next to this file:

| Worker | Topic | Report | Status |
|---|---|---|---|
| R1 | BL-004 Review finding classification / convergence | `workers/R1_BL004.md` | complete |
| R2 | BL-005 Review / achievement evidence durability | `workers/R2_BL005.md` | complete |
| R3 | BL-006 Read-only status/context command + BL-007 Cold-start recovery performance | `workers/R3_BL006_BL007.md` | complete |
| R4 | BL-003 Phase completion automatic review (dependency research) | `workers/R4_BL003.md` | complete |

Tags used below follow the worker reports: [CURRENT FACT], [FROZEN CONTRACT FACT], [CANONICAL AUTHORITY FACT], [BACKLOG CLAIM], [INFERENCE], [RECOMMENDATION], [GPT_REVIEW_REQUIRED]. "PARENT-VERIFIED" marks a worker claim the parent re-checked in source at the baseline.

## 1. Baseline

| Item | Value |
|---|---|
| Research baseline commit | `6e7fecb784a6ba1f49586761ab1038aa47d1738b` |
| Baseline tree | `124ee98884bf707218292995a02d07dd659d5268` |
| `BACKLOG.md` blob at baseline | `2034fc818bcda8c0734d5f963894a6887db3b195` |
| Preflight (research start, 2026-10-01 ~06:24Z) | `git ls-remote origin refs/heads/main` = GitHub API `commits/main` = baseline; canonical checkout at baseline, ahead/behind 0, no tracked change |
| Research source | fresh clone of the GitHub repository, detached at the baseline, clean, no interrupted Git operation; checked clean (`status --porcelain --ignored` empty) after every worker finished |
| Program state at baseline | P1 and P2 landed; P3 F1/F2/F3 contracts landed; F3 pre-activation implementation landed through Batch D; Gate 3 (Work-terminal Review gating) NOT activated; Batch E being implemented in another session, content unknown to this run; P4+ not started |
| Worker model control | each worker was launched with an explicit Sonnet model selection and self-checked its model before starting research; all four done markers report `Sonnet 5.5` |
| Baseline status at publication | current: live main was still `6e7fecb784a6ba1f49586761ab1038aa47d1738b` when this artifact was published |

Batch E content is unknown to this run. No statement here says what Batch E does or does not address. Section 9 marks the questions that matter before Gate 3 activation.

## 2. Executive result

### 2.1 Per item

| Item | Current actual status at baseline | Remaining problem | Research readiness | Dependencies |
|---|---|---|---|---|
| **BL-003** Phase completion automatic review (BACKLOG: OPEN) | Phase `complete` is a purely mechanical projection (`state.ProjectView.phase_state` -> `phase_completion`). No operation owns the transition: `work_completed`, `work_cancelled`, Work `plan_excluded` (measured) and `phase_resumed` can all produce it. `complete` is not terminal, and it refuses new Works. No canonical text defines what a `phase_integration_check` verifies. No Phase-level Review exists in code or authority. [CURRENT FACT] / [CANONICAL AUTHORITY FACT] (R4 s1) | BACKLOG premise confirmed by measurement: a Work derived with `before_integration=False` can complete after the only integration and the Phase still reads `complete` (R4 s1.5; mechanism PARENT-VERIFIED in `start.py` `_derivation_registration`). Attachment point, Candidate, Consumption anchor and selector are all undefined. | Dependency research complete. Can implement before BL-004: **PARTIAL** (read-only diagnostics and characterization tests only). | A usable gate depends on BL-004 (exit route, REQUIREMENT CHANGE routing, re-review identity). Evidence value depends on BL-005 (no Phase event to anchor to). Sequencing against Gate 3 is open (R4-Q8). |
| **BL-004** Review finding classification / convergence (OPEN) | Severity HIGH/MID/LOW is the only classification. The reviewer declares it and it is final; HIGH and MID block. Findings have no identity and no disposition, and obligations are never resolved ("P2 resolves none" / "P3 resolves none"). Finding text is runtime-only; the canonical gate keeps digests. A not-authorized planning attempt forgets the refusal on retry. A not-authorized Work Run leaves the START mutation pending in `ReconcileRequired` (R2 measured; R1 infers no re-run path). [CURRENT FACT] (R1 s1-s2) | The BACKLOG four-class taxonomy appears nowhere else (no contract, Skill, code or test). The non-normative design memos use a different model (Problem/Improvement x severity; dismissal and HUMAN as adjudication outcomes) and disagree with the BACKLOG on whether an IMPROVEMENT blocks. Gate-shape pins (1 slot, 1 task, 3 or 4 generations, 1 Policy per kind, one Candidate per START mutation) constrain every design. | **READY_FOR_GPT_DESIGN_REVIEW** (13 questions). Not implementation-ready: taxonomy, adjudicator, durability and loop shape are semantic choices. | Durability decision shared with BL-005 (R1-Q4 = R2-Q1). P4/P5 governing text is ambiguous (R1-Q12). The Work-path slice touches files Batch E is changing. |
| **BL-005** Review / achievement evidence durability (VERIFIED) | Partly stale. The Event model has a metadata carrier, and review-v1 records (CandidateSnapshot, TaskInput, gate chain, Receipt, Consumption) exist. The Work path is unreachable in production: no activation writer exists, and a test pins that. Planning review is live as an opt-in. Every production event is still four-field. P3 built an authorization-integrity chain (digests), not a justification record. `roadmap_achieved` drops `detail`. Phase completion is generated and never recorded. [CURRENT FACT] (R2 s1-s3) | Reviewer reasoning and finding text; functional verification used; Roadmap achievement judgement; Phase-level judgement; wall-clock verification time; a Project-wide totality check (every review-v1 `work_completed` has one Consumption); a public-repository content policy for committed Review material. | Evidence-based disposition candidate: **SPLIT** (not RESOLVE). 9 questions. | Work slice follows BL-002 / P3 activation. Findings and history slice follows BL-004 / P5. Achievement and Phase evidence have no design owner. |
| **BL-006** Read-only status/context command (OPEN) | Accurate. The CLI has six subcommands and none reports state. `validate-project` said PASS on a fixture holding 2,020 recovery records, 20 of them pending. The router has no owner for a bare "where am I" request. Every read primitive exists and most are write-free. Two are not pure: `gitcmd.dirty_paths` rewrote `.git/index` on a stale stat cache, and `committed_view` / `publication.barrier_problem` create `.workline/runtime/review/proofs`. [CURRENT FACT] (R3 Part A) | A canonical interface and contract. A scratch prototype (2 Git calls, one load, byte-identical output, tree unchanged) shows it can be built from existing functions. | **READY_FOR_GPT_DESIGN_REVIEW** (R3-Q1..Q8, Q11). | BL-019 hands pending-record visibility to BL-006. BL-055 sets the shadow-authority boundary. At about 1,000 Works or more, a status command needs BL-007 derivation indexing. |
| **BL-007** Cold-start recovery performance (INVESTIGATE) | First non-canonical decomposition exists (R3 Part C). Up to about 300 Works the machine-side data path costs a few hundred ms, mostly process start, activation/import (about 150 ms per process) and Git subprocesses. Above that, `validate_structure` and the state derivations grow roughly quadratically (O(events) scan in `ProjectView.events_for`). Write operations run 35-63 Git subprocesses each (93-99 % of wall time), independent of Project size; most are HEAD/branch safety guards. [CURRENT FACT] | The AI-side reading load: a fresh AI is told to read 85-145 KB of canonical text, and only 1.6 % of `registry.md` is routing. The bootstrap is byte-compared and has no upgrade path (PARENT-VERIFIED: `bootstrap.bootstrap_state` -> `conflict`, `backfill_bootstrap` STOPs `bootstrap_conflict`). | Machine side **READY_FOR_GPT_DESIGN_REVIEW**. AI side and real Project sizes **INSUFFICIENT_EVIDENCE** (not measurable here). | About a third is solved by BL-006 (process collapse, single load, fixed Git count). The rest is authority structure (R3-Q9) or internal optimization (R3-Q10). |

### 2.2 Cross-cutting findings

1. **Code and frozen contract disagree on the Work Candidate's desired state.** [CURRENT FACT] `src/workline/start_review.py` `declared_base` reads `work.meta.get("desired_state")`. Work frontmatter has no such key: `create._registration_effects` writes `id`, `display`, `type`, `phase_id`, `origin`, optional `work_kind` and `confirmation_target`, and the desired state lives in the body section `WORK_DESIRED_HEADING`. Planning code reads it as `entity.section(WORK_DESIRED_HEADING)` (`roadmap_review.py`). [FROZEN CONTRACT FACT] F2 specifies `desired_state: <the Work's desired state at the base>` (two places). R2 measured `null` in the snapshot, TaskInput and request envelope. R4 measured the parsed meta independently. PARENT-VERIFIED in source. Whether this is a defect to fix or an omission to ratify is G-01 (section 9). It is time-sensitive only in that no production Candidate exists before Gate 3 activation.
2. **Committed Candidate snapshots carry full result bytes before review, including results that are then rejected.** [CURRENT FACT] / [FROZEN CONTRACT FACT] F2 imposes no size cap. With a remote, such a commit reaches the push destination with the next push of that branch (R2 s5, inference from `registry.md` push semantics). Records are immutable, so there is no removal path. Workline offers no content policy. See G-02.
3. **The Work path has no channel for reviewer findings.** [CURRENT FACT] The Work Policy says LOW findings are "returned to the caller", but `StartResult` has no findings field, and after runtime loss the report copy is gone (R1-Q13, R2 s1.3). Planning returns findings through `ReviewedPlanningResult`.
4. **The Work Review Policy (`review-v1-work`) is defined only in code.** [CURRENT FACT] No canonical Skill or `registry.md` declares it. The planning Policy is declared in `skills/review` and pinned equal by a test (R1 s1.1). [CANONICAL AUTHORITY FACT] `skills/review` states "Work terminal Review gating: NOT ACTIVATED", and `skills/start` contains no Review text (R2, R4).
5. **Document-status lag.** [CURRENT FACT] The headers of the P2 contract ("P2 IMPLEMENTATION NOT LANDED") and the P3 F1/F2 contracts ("IMPLEMENTATION NOT STARTED") contradict the landed code. `REVIEW_SYSTEM_IMPLEMENTATION_ROADMAP_CHECKPOINT.md` is the Candidate-2 roadmap, superseded by `..._CANDIDATE3..7.md`, and the two versions differ on P4 scope (R1 s0, R4 staleness table). This is not authority (`BACKLOG.md` `## Authority`). It is a misreading risk for fresh sessions (see cross-check E).
6. **Incidental public-repository hygiene observation.** R2 s5.4 notes that a frozen contract document at baseline names a local-filesystem evidence location, contrary to the BACKLOG convention for this public repository. This run does not reproduce it and makes no change.

### 2.3 Cross-checks requested by the run protocol

| Check | Result |
|---|---|
| **A. R1 BL-004 against R4 BL-003 dependencies** | Consistent. R1 lists BL-003 as a consumer of classification and of the existing fix-Work route. R4 shows that building a Phase gate needs no BL-004, while a usable gate does: under the landed severity-final policy a blocking finding dead-ends at `reconcile required` (`start_review.py` `_continue`). Both cite the same Work-path dead end. R4-Q5 ("classification-free first gate?") is the BL-003 face of R1-Q6 / R1-Q8. Merged as G-12, G-14 and G-23. |
| **B. R1 durability needs against R2 BL-005** | Consistent. Both establish that finding content is runtime-only, the canonical gate holds digests, the Receipt says "authorized" but not why, and P5 is the named home for durable history (P1 R1 s14, F3 s25.2). R1 adds the constraint that P1 R3 s10 requires gate or provenance facts relied on after process loss to be committed before the dependent boundary, so a disposition that decides sealing cannot stay runtime-only. R2 adds the measured public-repository exposure. R1-Q4, R2-Q1 and R4-Q7 are one question (G-04). R2-Q8 depends on it (G-05). |
| **C. R3 BL-006 contract against R3 BL-007 measurements** | Consistent, with one coupling. The status prototype is cheap up to about 300 Works, but at 3,000 Works it took 12.7 s because the quadratic derivations dominate. A status contract that promises bounded cost (R3 M11) therefore needs either BL-007 derivation indexing (R3-Q10 option 1) or a stated size envelope. The status contract also makes the read path Git-bound at 2-3 calls, removing most of the avoidable machine-side cold-start cost. It cannot touch the AI-side reading load or the write-path Git guards. |
| **D. Proposed authority changes against current canonical authority** | Proposals that would change canonical authority, and the authority they meet: (1) any BL-004 class, disposition or adjudicator meets `skills/review` "Adjudication (P2)" and the frozen P1 R3 / P2 / F3 shape pins, so it needs forward amendments (R1 D-A..D-C); (2) a REQUIREMENT CHANGE route meets `registry.md` `rules/human-confirmation` / `rules/ai-decision` and START "Work completion precheck" (the desired state is never rewritten to make a Work pass); (3) defining integration scope or changing Phase completion meets `rules/human-confirmation` for common-rule changes (R4-Q6); (4) a new status Skill is allowed by `registry.md` (a Skill is added by the registry plus its `SKILL.md`, with no Project update), whereas a bootstrap text change strands every existing Project (PARENT-VERIFIED no upgrade path); (5) authority digests in a status report (R3-Q8) meet the explicit `registry.md` statement that only the configured root's working tree is guaranteed; (6) durable achievement records meet `registry.md` (Project execution lock paragraph) and `skills/roadmap` "Roadmap achievement", which make achievement the caller's evaluation. None of these is decided here. |
| **E. Shadow-authority risk (BL-055 concern, not researched further)** | Observations only: (1) the Work Policy exists in code with no canonical declaration (2.2 item 4), the reverse of shadow authority but the same "two places disagree" risk; (2) stale contract headers and the superseded roadmap checkpoint at repo root can be misread as current program state (2.2 item 5); (3) the BACKLOG taxonomy and the design-memo taxonomy compete with each other while neither is authority (R1 s3.1); (4) a status command's output becomes shadow state if it is ever persisted, cached or treated as an operation input, which R3 D4 / M8 address by design and which `registry.md` already forbids for operation inputs (re-read under the lock); (5) this research artifact is itself non-canonical, lives on a research ref and carries the do-not-merge header. |

## 3. Evidence-derived dependency graph

Edges read "X -> Y" as "X needs Y (or a decision in Y) first". The graph is derived from the worker evidence, not from BL number order.

```
Gate 3 / Batch E (in progress, content unknown)
   ^            ^                 ^                    ^
   |            |                 |                    |
BL-002 close   BL-005 Work slice  BL-003 gate form?    BL-004 Work-path slice (D-A Work part, D-C)
(activation,   (totality check,   (R4-Q8 open)         (files Batch E is changing:
 canonical      canonical text)                         start_review.py, work_review.py)
 Skill text)

G-04 durability decision (R1-Q4 = R2-Q1 = R4-Q7)
   ^                ^                    ^
   |                |                    |
BL-004 dispositions BL-005 content slice BL-003 evidence value
   |                |
   |                +--> G-05 content rules (privacy) --> human policy H-2
   v
P4/P5 governing text (G-18)

BL-003 usable gate --> BL-004 (exit route G-12, REQUIREMENT CHANGE G-14, re-review identity G-11)
BL-003 any gate    --> its own design decisions G-19..G-22 (trigger, Candidate, Consumption anchor, selector)
BL-003 diagnostics --> nothing (read-only; overlaps BL-006)

BL-006 v1          --> R3-Q1..Q8 decisions only
BL-006 at >=1k Works --> BL-007 internal optimization (derivation indexing)
BL-006 constraints <-- BL-019 (pending visibility hand-off), BL-055 (non-authority boundary)

BL-007 = (a) BL-006-dependent part  --> BL-006
         (b) authority structure    --> G-37 (bootstrap/registry; human policy H-6)
         (c) internal optimization  --> nothing but an equivalence proof (indexing);
                                        mutation.py guards are safety semantics (BL-035/036/038)
```

Independent of each other at the evidence level: the BL-006/BL-007(c) lane and the whole BL-004 design. Their file surfaces barely overlap (section 4).

## 4. Recommended implementation lanes

These are recommendations, not authorization. All lanes start only after Batch E lands, and only after a delta refresh of this research against the new main.

### 4.1 Lane 1: BL-006 v1 read-only status, plus BL-007 internal optimization (c)

- **Ready for:** GPT design review of R3-Q1..Q8 (G-29..G-36). A minimal v1 needs decisions on location (G-29), basis (G-30), consistency (G-31), format and exit codes (G-32), Git read policy (G-33) and Review scope (G-34).
- **Independent of:** BL-003/004/005 semantics, if the v1 Review section stays at validity, counts and activation presence (R3-Q6 option A/B) and excludes the publication-barrier verdict, which writes runtime files.
- **BL-007 part that can join this lane:** event/phase indexing inside `ProjectView`, removing the O(events) scan. R3 rates it the only plausibly semantics-free optimization, provable by output equivalence over fixtures. `Path.resolve()` cost and `mutation.py` guard counts are excluded until reviewed: the first may be a containment check, the second is safety semantics.

### 4.2 Lane 2: BL-004 design, then a first slice

- **Ready for:** GPT design review only (G-04, G-08..G-18). Implementation is not ready, because every decomposition (R1 D-A classification and adjudication v2 without a loop; D-B planning-first; D-C loop-first) fixes a semantic choice and amends frozen pins (P1 R3 shapes, P2 s19.1, F3 s4.5 / s11.3.1).
- **Coupling with Batch E:** D-A's Work part and D-C touch `start_review.py`, `work_review.py`, `records.py` and `start.py`, which are the areas Batch E is presumably changing (unknown). D-B (planning-first) touches `planning.py`, `roadmap_review.py`, `recovery.py` and `skills/review`, so it is the least Batch-E-coupled option, but it leaves the Work path, BL-002's target, unaddressed.

### 4.3 Can BL-004 and BL-006/BL-007 run in parallel after Batch E lands?

[RECOMMENDATION] **Yes, conditionally.** The evidence shows no dependency edge between them and little file overlap:

| Concern | Lane 1 (BL-006 / BL-007 c) | Lane 2 (BL-004) | Overlap |
|---|---|---|---|
| Production files | `cli.py`, a new read-only status module, a read-only helper in `gitcmd.py`, `run-workline.py` CLI module list, `state.py` (indexing only) | `review/records.py`, `review/planning.py`, `review/work_review.py`, `review/store.py`, `review/validate.py`, `review/recovery.py`, `roadmap_review.py`, `start_review.py`, possibly `ids.py`, `start.py` | Possibly `src/workline/validate.py` (D-A may extend it; status reads it). `state.py` must not mention Review (test pin), so BL-004 does not touch it. |
| Canonical text | `project-router` and/or a new read-only Skill, `registry.md` routing (if G-29 chooses a Skill) | `skills/review`, possibly `skills/start`, `skills/roadmap` | none expected |
| Tests | new status tests, `tests/test_project_context.py` write-free list, equivalence tests for indexing | `tests/test_review_*.py`, `tests/test_work_review_runtime.py`, ID-kind pin | none expected |

Conditions: (1) v1 status keeps Review to validity, counts and activation; (2) BL-007 code work is limited to derivation indexing with an equivalence proof; (3) BL-004 implementation waits for its GPT design decisions; (4) both lanes rebase onto the post-Batch-E main through a delta refresh; (5) BL-007 re-measurement runs on a quiet machine, because R3 saw bimodal process-creation latency under concurrent load. A change to any package `*.py` changes the Review Context digest and stales in-flight Runs by design (R1 s1.4). That is runtime behaviour in Projects, not a merge conflict.

### 4.4 Other lanes

- **BL-003:** only non-gating work before BL-004: characterization tests of the measured completion routes, and a read-only "Works completed after the last integration" diagnostic. The diagnostic overlaps BL-006 O5 (R3 D2), which R3-Q7 cautions about.
- **BL-005:** the split is a BACKLOG lifecycle decision (H-5). The Work-slice closure item (a Project-wide totality check in `review/validate.py`) is meaningful only after Gate 3. The content-policy slice is a human-policy decision first (H-2).
- **Pre-activation items (G-01, G-02, G-03)** belong to the Gate 3 owner's decision path, not to any lane here.

## 5. BL-004 / P4 mapping

Source: R1 s6. Two non-normative roadmap texts exist: the Candidate-2 roadmap in `REVIEW_SYSTEM_IMPLEMENTATION_ROADMAP_CHECKPOINT.md` s19, and Candidate 7 s15. Which one governs P4 is G-18.

| P4-deferred responsibility | Baseline state | How BL-004 interacts |
|---|---|---|
| Repair loop (`ReviewRepairRequest`, executor repair purpose) | absent; `ExecutionContext` has no purpose; not-authorized Work Run is a dead end | Classification decides which findings drive the loop. Without a dismissal route, false positives drive it, which is the BL-004 problem itself. |
| Loop placement vs F3 | F3 s4.5 / s11.3.1: one Candidate, proof notes written once per START mutation | Several Candidates per mutation amends F3; one Run per Candidate needs a lineage link and a way to end the pending mutation (G-12) |
| Mismatch classes (post-commit Class A/B/C) | frozen as F4 (inside P3), not P4 | Unrelated to finding classes, but a name collision with recurrence A/B/C and Git invocation class A/B (G-17) |
| Stale generation / supersession | planning writes generation 4 + Supersession; Work path only checks | A dismissal or repair after a seal would be a supersession case |
| Interruption recovery | planning: discovery + set-aside; Work: resume own Run | Each new transition (adjudicate, repair) adds an interruption window; a runtime-only disposition is lost on runtime loss |
| Evidence reuse across Candidates | refused for Work (completeness `unknown`) | Independent of classification; P4 dependency-class work |
| Same-run recurrence (A new / B recurrence / C repair-induced) | absent | Needs finding identity (G-11) and a Candidate lineage. "Same run" is ambiguous: one Run spanning Candidates (not what the chain format builds) vs linked Runs. |
| Cross-run recurrence, durable history | absent; P5 in both roadmap texts | BL-004's "record the classification" and false-positive memory need durable data earlier than P5 (G-04, G-18) |
| LOW workization / `planned_next` deferral | `planned_next` is a recommended order only | LOW (and non-blocking IMPROVEMENT) disposition lands here |
| Phase Integration Check | absent | BL-003 consumer (section 7) |

## 6. BL-005 disposition candidates

Source: R2 s2 and s4. Classification of the original BL-005 concerns:

| Concern | Classification |
|---|---|
| Events carry only id/type/entity/at | PARTIALLY_SOLVED (carrier mechanism; production events unchanged) |
| No PASS / achieved reason | Work: PARTIALLY_SOLVED after Gate 3, STILL_OPEN at baseline. Roadmap: STILL_OPEN |
| Verification / evidence used not stored | Work: integrity checks PARTIALLY_SOLVED after Gate 3; functional verification STILL_OPEN. Roadmap/Phase: STILL_OPEN |
| Roadmap achievement judgement not persisted | STILL_OPEN (no design owner) |
| Recovery record is runtime-only | MOVED_TO_ANOTHER_RESPONSIBILITY for review-v1 (deliberate design: P1 R1 s3, F3 s10, BL-019); STILL_OPEN outside review-v1 |
| Event time is not verification time | logical ordering PARTIALLY_SOLVED after Gate 3; wall clock STILL_OPEN |
| Third-party review results not kept | PARTIALLY_SOLVED (who, what, outcome class, by digest); content STILL_OPEN; history MOVED to P5 / BL-004 |

| Option | Evidence for | Evidence against |
|---|---|---|
| RESOLVE | authorization chain, carrier and Consumption shape exist and are tested | nothing reachable in production; no canonical text; several concerns open |
| RETAIN | VERIFIED is accurate for production behaviour | problem text stale in two places; double-counts BL-002 / BL-004 / P5 |
| SHRINK | the Work authorization slice has an owner (P3) | leaves unrelated residues under one heading |
| **SPLIT (candidate)** | concerns fall on four owners and gates: Work authorization (BL-002 / P3 activation), findings, classification and history (BL-004 / P5), achievement and Phase judgement plus time semantics (no owner), content/privacy policy (no owner) | creates new BACKLOG items; which slice keeps the ID is a lifecycle decision (H-5) |

Cross-check against R1 and R4: R1 independently places finding and disposition durability on the BL-004 / P4-P5 boundary. R4 independently finds no Phase event to anchor Phase evidence to. Both support SPLIT over RETAIN. The split shape and the resolution criteria (canonical Skill text, an activation producer, a Project-wide totality check) are G-28.

## 7. BL-003 dependency boundary

Source: R4.

- **What makes a Phase complete now** [CURRENT FACT]: lifecycle not cancelled, plan-excluded or held; non-empty effective set; every effective Work completed; at least one `phase_integration_check`; no effective Work depends on a cancelled or excluded predecessor. "Structural validation PASS" and "replan complete", which the Skill lists, are enforced by operation postchecks and are not predicates of `phase_completion`.
- **Constraints any attachment inherits:** Review never enters state derivation (`skills/review` authority boundary plus a test pin that `state.py` does not mention Review) [CANONICAL AUTHORITY FACT]; no cross-operation Review precondition (P2 s22 item 3) [FROZEN CONTRACT FACT]; one Consumption per terminal event (P1 R4) [FROZEN CONTRACT FACT]; contract mode is never inferred from Work kind or Project state (F1 s3.1 item 7) [FROZEN CONTRACT FACT]; new Works cannot join a complete Phase [CURRENT FACT]; 44 references in 19 test files pin `phase_complete` [CURRENT FACT]; review-v1 outer START returns after one completion (PARENT-VERIFIED `start.py` outer loop) [CURRENT FACT].
- **Attachment points (AP-1..AP-7) and forms (F-1..F-6):** none is mechanically mandatory. A Review record inside `phase_completion`, a "next Phase requires a Phase Receipt" precondition, and two Consumptions on one terminal event without amending P1 R4 are excluded by current authority and pins.
- **Reusable vs kind-specific:** the P1 records, gate, store, serialization, paths/fsafe, committed reader, closure, projections and hermetic Git are kind-generic. Candidate, Context, Policy, Evidence and adjudication have been written per kind by convention. All Work Candidate machinery (owned paths, K1/K2, resulting tree, isolated verification) is Work-specific. No kind binds a Phase's desired-state text.
- **Before BL-004:** PARTIAL. Only read-only diagnostics and characterization tests. Any gate, Candidate, Consumption, selector, canonical wording or completion-semantics change needs G-19..G-25.

## 8. Genuine human decisions

These are human-policy decisions only: changes that `registry.md` `rules/human-confirmation` reserves for a human, publication policy, and BACKLOG lifecycle. Design questions stay in section 9.

| ID | Decision | Why it is human policy | Related |
|---|---|---|---|
| H-1 | Whether a review finding may ever lead to a requirement or desired-state change, and who may classify a finding as REQUIREMENT CHANGE (reviewer, adjudicator, or only a human) | `rules/human-confirmation` (desired-state change of a Roadmap, or of a started Phase or Work); START never rewrites a desired state to make a Work pass | G-14 |
| H-2 | Public-repository content policy for committed Review material: result bytes in Candidate snapshots (including rejected results), and finding or evidence text if it becomes durable | publication of Project content to a remote; records are immutable, so there is no later removal path | G-02, G-05 |
| H-3 | Whether Roadmap achievement judgement and Phase-level judgement become durable canonical records | canonical schema / common-rule change; `registry.md` currently makes achievement the caller's evaluation | G-26, G-27 |
| H-4 | Whether Phase completion semantics change (for example, "an integration must complete after the last other effective Work") or integration scope is defined in canonical text | common completion rule for every Project | G-24 |
| H-5 | BACKLOG lifecycle: approve or reject the BL-005 split and decide which slice keeps the ID; where BL-004 sits relative to P4/P5 | the owner manages BACKLOG; BACKLOG is not authority | G-28, G-18 |
| H-6 | Whether the cold-start reading load is reduced by changing the bootstrap text (affects every existing Project, no upgrade path today) or the registry layout | change to the common bootstrap / authority structure | G-37 |
| H-7 | Value of any repair-iteration emergency cap, if one is adopted | policy value carried in the Review Policy hash | G-15 |

## 9. GPT_REVIEW_REQUIRED

Deduplicated from R1-Q1..Q13, R2-Q1..Q9, R3-Q1..Q11 and R4-Q1..Q8. Each worker report holds the options, evidence, affected files and consequences under its own IDs.

### 9.1 Time-sensitive relative to Gate 3 activation

| ID | Question | Source IDs |
|---|---|---|
| G-01 | The Work Candidate's `declared_base.work.desired_state` (and the request envelope's `work.desired_state`) is always `null` because `start_review.declared_base` reads a frontmatter key Work entities never have, while F2 specifies the Work's desired state at the base. Is this a defect to fix before activation (read the body section), a contract amendment (desired state bound only through `base_commit`), or acceptable as is? No production Candidate exists before Gate 3, so a fix changes no stored hash. | R2-Q3, R4 incidental (fact PARENT-VERIFIED) |
| G-02 | How are committed Candidate snapshot payloads bounded for public repositories (full result bytes committed before review, including rejected results, no size cap, immutable)? Options in R2-Q7: accept and document; cap with refusal; payload by reference; Project sensitivity policy; extend the publication barrier. Most options amend F2. | R2-Q7, R4-Q2 (public-content consequence) |
| G-03 | Is a result channel for Work findings (the Work Policy says LOW is "returned to the caller"; `StartResult` has none) in scope for Gate 3, for BL-004, or dropped from the Policy text? | R1-Q13, R2-Q1 (part) |

### 9.2 Durability (BL-004 x BL-005 x BL-003)

| ID | Question | Source IDs |
|---|---|---|
| G-04 | Is "durable evidence" the P3 digest-bound authorization chain, or must finding text, classifications and dispositions (including a not-authorized Work's HIGH/MID reasons) become durable? If so, where (new committed record kind, gate or TaskInput fields, or runtime until P5) and in which phase? Must a disposition that decides sealing satisfy P1 R3 s10 (committed before the dependent boundary)? Where is Phase-level evidence anchored, given there is no Phase event? | R1-Q4, R2-Q1, R4-Q7 |
| G-05 | If findings or evidence text become durable, which content rules apply (representability only, size caps and refusal, digest plus external reference), and who owns them? | R2-Q8 |
| G-06 | Is the Work's own functional verification (tests, commands) meant to be Evidence, given that isolated verification only checks reconstruction and `Completed` has no verification field? | R2-Q2 |
| G-07 | Is logical ordering enough for "event time is not verification time", or should a canonical record carry a wall-clock verification time? | R2-Q6 |

### 9.3 BL-004 semantics

| ID | Question | Source IDs |
|---|---|---|
| G-08 | Which closed vocabulary defines BL-004: the BACKLOG four classes (T-1), T-1 plus UNDECIDABLE and OUT_OF_SCOPE, the memo axes (category x severity x outcome), a consequence-centric set, or validity x disposition? | R1-Q1 |
| G-09 | Does an IMPROVEMENT ever block authorization (BACKLOG: no; memos: yes at HIGH/MID; code: severity decides regardless of category)? | R1-Q2 |
| G-10 | Who adjudicates (reviewer severity final, a separate history-aware adjudicator task, or human only), given the one-slot / one-task / 3-4-generation pins? | R1-Q3 |
| G-11 | What is a finding's identity, who assigns it, and who decides sameness and recurrence (reviewer `code`, content digest, reserved ID kind, repair identity)? | R1-Q5 |
| G-12 | Does one mutation host several Candidates (amending F3 s4.5 / s11.3.1) or does each Candidate get its own Run with a lineage link? How does a not-authorized Work START mutation stop being pending forever? | R1-Q6, R4-Q5 (exit route) |
| G-13 | Can a dismissed or deferred finding let the same Candidate and Run continue to seal (redefined obligation and seal rule), or must a new Run re-review? | R1-Q7 |
| G-14 | What is the REQUIREMENT CHANGE route (question wait, `human_confirmation` Work, cancel and replan, or a Review-level HUMAN state), and who may classify a finding as one? (Policy part: H-1.) | R1-Q8, R4-Q5 |
| G-15 | Is there an iteration cap or instability trigger, what action follows it, and how is "same semantic surface" defined? (Value: H-7.) | R1-Q9 |
| G-16 | How are Policy versions and reviewer instructions defined (one Policy per kind; Work Policy absent from every Skill; `instruction` is an identity string only)? | R1-Q10 |
| G-17 | Which outcome vocabulary is canonical (`not_authorized` / `ReconcileRequired` vs REPAIR / HUMAN / READY / CONVERGED / PASS), and should the three A/B/C vocabularies be renamed? | R1-Q11 |
| G-18 | Which roadmap text governs P4 (Candidate-2 checkpoint s19 or Candidate 7 s15)? Is BL-004 one unit before the loop, a P4 item, a P5 item, or split? | R1-Q12 |

### 9.4 BL-003

| ID | Question | Source IDs |
|---|---|---|
| G-19 | Which transition does a Phase Review gate (START Phase-completing Work, START integration Work, plus the Roadmap-side routes, a non-blocking Roadmap evaluation, or validation only), given that no operation owns the transition into `complete`? | R4-Q1 |
| G-20 | What is the Phase Review Candidate, and does the Phase's desired-state text enter it? | R4-Q2 |
| G-21 | What does a Phase Consumption bind without a Phase terminal event, and what is the target identity? | R4-Q3 |
| G-22 | How is a Phase kind selected (explicit selector, Project activation, inferred trigger against F1 s3.1 item 7), and how do START outer / `phase_complete` and Roadmap `handoff` behave? | R4-Q4 |
| G-23 | Is a classification-free first Phase gate (dead end at `reconcile required`) acceptable before BL-004? | R4-Q5 (with G-12, G-14) |
| G-24 | Should canonical authority define what an integration verifies and require it to observe the final Work set, and by which mechanism? (Policy part: H-4.) | R4-Q6 |
| G-25 | Must the Phase kind wait for Gate 3, or is it independent? | R4-Q8 |

### 9.5 BL-005 residue

| ID | Question | Source IDs |
|---|---|---|
| G-26 | Should a Roadmap achievement judgement become durable, and how (event metadata, new record, Review kind, or not at all)? (Policy part: H-3.) | R2-Q4 |
| G-27 | Is Phase-completion evidence in scope, and is it a record, a rule on the integration Work, or nothing beyond the generated state? | R2-Q5 (overlaps G-04, G-24) |
| G-28 | Approve SPLIT and name the slice that keeps BL-005. Are a Project-wide totality check, an activation producer and canonical Skill text preconditions for closing the Work slice? (Lifecycle part: H-5.) | R2-Q9 |

### 9.6 BL-006 / BL-007

| ID | Question | Source IDs |
|---|---|---|
| G-29 | Should the status be a CLI subcommand only, a new routed read-only Skill plus CLI, or folded into existing Skills, and which canonical text carries its non-authority rules? | R3-Q1 |
| G-30 | Does it report working-tree state, HEAD's committed state, or both with a divergence field, and may a HEAD reader exist that writes nothing under the runtime area? | R3-Q2 |
| G-31 | What consistency does a lock-free status promise while a writer may be mid-mutation? | R3-Q3 |
| G-32 | Output form (JSON or the canonical YAML subset), escaping, versioning and exit-code semantics | R3-Q4 |
| G-33 | Must status Git reads strip ambient `GIT_*`, always disable optional locks, and may one `status --porcelain=v2 --branch` call replace the separate HEAD, branch and dirty-path reads? | R3-Q5 |
| G-34 | How much Review state belongs in v1, given that Batch E is changing Review code concurrently and the barrier verdict writes runtime files? | R3-Q6 |
| G-35 | May the report name a single selected next candidate and diagnosis reasons, or only candidate sets with a tie flag? | R3-Q7 |
| G-36 | Does authority identity report only observed facts, or also digests and the Git revision of the Workline root? | R3-Q8 |
| G-37 | Is reducing the 85-145 KB a fresh AI must read in scope, and through which route? (Policy part: H-6.) | R3-Q9 |
| G-38 | Which BL-007 code optimizations are in scope, and what behavioural-equivalence proof do they need? | R3-Q10 |
| G-39 | Is BL-006 designed first and BL-007 re-measured after it, or is G-37 decided first? | R3-Q11 |

### 9.7 Raised by the parent synthesis

| ID | Question | Basis |
|---|---|---|
| G-40 | Should the stale status headers of landed contracts (P2, P3 F1/F2) and the superseded roadmap checkpoint be corrected, annotated or left, given that they are not authority but can be misread by fresh sessions (cross-check E)? | 2.2 item 5; R1 s0; R4 staleness table |

## 10. Proposed implementation packages

Recommendations only. Nothing is authorized. Every package requires a delta refresh against the post-Batch-E main before it starts.

| Package | Scope | Dependency | Likely production surfaces | Likely tests | Review strength | Safe parallelism |
|---|---|---|---|---|---|---|
| **PK-0** Pre-activation conformance items (route to the Gate 3 owner) | decide G-01 and G-03, and G-02 if it must precede public use | GPT decision; Batch E state unknown | `start_review.py` `declared_base`; `work_review.py` envelope checks; `start.py` `StartResult` (G-03) | `tests/test_work_review_runtime.py` (pin the desired-state value), result-channel tests | high (frozen F2 text involved) | belongs to the Gate 3 path, not to the lanes below |
| **PK-1** BL-006 v1 read-only status | one canonical read-only command: authority facts, canonical state (working-tree basis), pending mutations, Git via a single no-optional-locks status call, validation, minimal Review section | G-29..G-36 | `cli.py`, a new status module, a read-only helper in `gitcmd.py`, `run-workline.py` module list, `project-router` SKILL or a new Skill, `registry.md` if routed | new status tests (determinism, byte-identical output, tree hash including `.git` before/after, stale-index fixture, pending visibility), `tests/test_project_context.py` write-free list | medium (read-only, but adds canonical text and an interface contract) | parallel with PK-3 and with BL-004 design and implementation |
| **PK-2** BL-007(c1) derivation indexing | remove the O(events) `events_for` scan and repeated Phase membership scans in `ProjectView` | G-38 (equivalence proof required) | `state.py` | output-equivalence tests over a size ladder; existing state and lifecycle suites | medium-high (`state.py` is lifecycle truth; must stay byte-for-byte equivalent) | parallel with PK-1 (PK-1 does not modify `state.py`); should land before PK-1 promises large-Project bounds |
| **PK-3** BL-007 re-measurement after PK-1 | repeat R3 Part C on a quiet machine, plus real Project sizes if the owner can share aggregate sizes | PK-1 | none (tooling outside the repo) | n/a | low | any time after PK-1 |
| **PK-4** BL-007(b) authority-structure change | reduce what a fresh AI must read | G-37 + H-6 | `bootstrap.py` (with a migration design), `registry.md`, `project-start` SKILL | bootstrap conflict and backfill tests | high (every Project) | only after decision; conflicts with any other bootstrap change |
| **PK-5** BL-004 slice 1 (shape depends on G-08..G-18; candidates R1 D-A / D-B / D-C) | for example durable findings, a closed classification and dispositions, adjudication v2, with or without a loop | G-04, G-08..G-18, H-1, H-7; post-Batch-E main | `review/records.py`, `review/planning.py`, `review/work_review.py`, `review/store.py`, `review/validate.py`, `review/recovery.py`, `review/paths.py`, `roadmap_review.py`, `start_review.py`, `ids.py`, `skills/review` (D-C adds `start.py`, `skills/start`) | `tests/test_review_planning_*.py`, `tests/test_review_gate_generation.py` (ID-kind pin), `tests/test_review_layout.py`, `tests/test_review_authority.py`, `tests/test_work_review_runtime.py`, new dismissal, idempotency and runtime-loss tests | high (frozen-contract forward amendments to P1 / P2 / F3) | parallel with PK-1/PK-2/PK-3; not parallel with PK-6 or with other Review-namespace work |
| **PK-6** BL-003 Phase gate | form chosen from F-1..F-6 | G-19..G-25 (+ G-12, G-14 for a usable gate); BL-004 slice 1 for a non-dead-end gate | `start.py`, `start_review.py` or `roadmap.py` / `roadmap_review.py`, `review/records.py` (Consumption), `skills/start`, `skills/roadmap`, `skills/review` | the 44 `phase_complete` references, `tests/test_review_authority.py`, new Phase-gate tests | high | after PK-5 |
| **PK-7** BL-003 pre-BL-004 slice | characterization tests of the measured completion routes, plus an optional read-only diagnostic | none (diagnostic: G-35 if it rides in PK-1) | none (tests), or the PK-1 module | new characterization tests | low-medium (adds pins later decisions must update) | parallel with everything |
| **PK-8** BL-005 Work-slice closure | Project-wide totality check (every review-v1 `work_completed` has exactly one Consumption) | Gate 3 activation; G-28 | `review/validate.py` | review validation tests | medium | after Gate 3; parallel with PK-1/PK-2 |
| **PK-9** BL-005 residue | achievement and Phase evidence, time semantics, content policy | G-26, G-27, G-07, G-05; H-2, H-3 | `roadmap.py`, `store.py` (if event metadata), `skills/roadmap`, `registry.md` | per decision | high (canonical schema) | after decisions |
