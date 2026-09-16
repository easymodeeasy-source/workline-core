# Review System P1 — Integration Contract Reconnaissance Checkpoint

Status: R1-R12 CONTRACTS FROZEN / IMPLEMENTATION NOT STARTED

This checkpoint closes the Candidate 7 P1 Integration Contract Reconnaissance requested after `READY_FOR_P1`.

It is non-normative design/implementation-contract history until the corresponding implementation and canonical authority updates are activated. Runtime authority remains `registry.md`, registry-routed canonical Skills, and live code.

## 1. Baseline

Candidate 7 readiness checkpoint established:

```text
Architecture blockers: 0
HUMAN decisions: 0
Verdict: READY_FOR_P1
```

P1 reconnaissance then inspected the live store/layout, Project Start/bootstrap, Mutation Controller, Project execution lock, Git helpers/finalization, IDs, validation, Roadmap/Phase planning identities, `ProjectView/state.py`, START completion/finalization, and current tests.

The purpose was not to create Candidate 8, but to freeze exact implementation contracts where live code determines the safe shape.

## 2. Frozen contract documents

### R1 — Durable layout / loader / bootstrap

`REVIEW_SYSTEM_P1_R1_DURABLE_LAYOUT_CONTRACT.md`

Frozen:

```text
.workline/review/
  gates/<review_run_id>/<generation:06d>.yaml
  receipts/<receipt_id>.yaml
  consumptions/<consumption_id>.yaml
  supersessions/<superseded_receipt_id>.yaml
```

- canonical Review layout is lazy; Project Start does not create empty directories/manifests;
- `.workline/runtime/review/` may hold scratch only and is never gate truth/evidence/authorization by itself;
- Gate generations are immutable chain files;
- stored generation state is `open | sealed_authorized`; superseded status is derived from a later valid generation rather than rewriting immutable old files;
- dedicated `ReviewStore`, separate from `ProjectView/state.py`;
- `validate_project()` gains separate Review structural validation;
- existing Projects without Review namespace remain valid and become Review-capable lazily.

### R2 — IDs / reservation

`REVIEW_SYSTEM_P1_R2_ID_RESERVATION_CONTRACT.md`

Frozen stable kinds:

```text
review_run         -> rr
review_receipt     -> rcp
review_consumption -> rcs
review_task        -> rtk
```

- use central `ids.py` and existing `Mutation.reserve_id()`;
- generation is integer chain state, not ULID;
- Candidate/Context/Policy/etc identities are digests, not allocated IDs;
- Receipt/task/Consumption reservation keys are deterministic and retry-stable;
- no callback-side/random stable ID later adopted by canonical state.

### R3 — Gate Generation mutation contract

`REVIEW_SYSTEM_P1_R3_GATE_GENERATION_MUTATION_CONTRACT.md`

Frozen:

- Review gate writes are owned by the top-level operation using Review (Roadmap, START, future Policy owner), not a second progression controller;
- async callbacks do not directly mutate Project state;
- accepted task is canonical before launch when cutoff semantics depend on it;
- result is ingested under the Project lock and becomes settled only through a new immutable Gate generation;
- seal + newly issued Receipt are one mutation decision/stage;
- a new invalidating fact creates a later open generation and supersedes old Receipt before consumption;
- only `sealed_authorized` generation may issue/retain consumable authorization;
- canonical gate fact relied on after clone must reach canonical/tracked local Git state before the dependent boundary.

### R4 — Consumption uniqueness

`REVIEW_SYSTEM_P1_R4_CONSUMPTION_UNIQUENESS_CONTRACT.md`

Frozen:

```text
one Receipt -> at most one valid Consumption
Work terminal event ID -> at most one valid Consumption
```

- stable physical Consumption ID + ReviewStore logical indexes/cardinality;
- exact tuple replay idempotent; conflicts reconcile;
- superseded Receipt cannot be newly consumed;
- Work terminal stage orders AuthorizedTransition effects before Consumption metadata effect;
- physical partial application is recovered through existing Mutation intent;
- Planning/Policy use kind-specific binding, no fake Work terminal event.

### R5 — START result commit / proof / push split

`REVIEW_SYSTEM_P1_R5_START_COMMIT_PROOF_PUSH_CONTRACT.md`

Live finding: current `gitops.finalize()` couples local commit and optional push in one stage; START therefore cannot currently insert Review proof between them.

Frozen Review-v1 topology:

```text
local K1
-> post-commit artifact/metadata/scope/Review-validity proof
-> authorized push K1
-> terminal event + Consumption stage
-> local K2 terminal commit
-> exact transition/metadata/scope proof
-> authorized push K2
-> postcheck / mutation complete
```

- normal K1 contains ReviewedArtifact + sealed Gate/Receipt metadata;
- no-result Work still gets metadata-only authorization K1;
- Receipt does not contain containing commit SHA; Consumption later binds K1;
- K2 deterministic terminal transition/metadata commit needs proof but no new Receipt;
- add commit-only and push-only recoverable Git helper boundaries;
- explicit legacy vs review-v1 activation remains required.

### R6 — HEAD advancement closure

`REVIEW_SYSTEM_P1_R6_HEAD_ADVANCEMENT_CLOSURE_CONTRACT.md`

Frozen `ReviewValidityClosure` covers:

- ReviewedArtifact semantic dependencies;
- Review Context provenance;
- Evidence dependencies;
- Effective Policy/verifier inputs;
- Git persistence semantics (`.gitattributes`, filters/config, hooks, line-ending/mode/symlink/gitlink semantics as applicable);
- tool/runtime/dependency identities.

Positive reuse requires:

```text
Git-write compatibility PASS
AND complete Review-validity closure
AND intervening changed material surfaces proven disjoint
AND non-repo material identities unchanged
```

Any unprovable completeness/identity -> new Candidate, never negative-search inference.

### R7 — Class A `adopt_existing_local_commit`

`REVIEW_SYSTEM_P1_R7_CLASS_A_ADOPTION_CONTRACT.md`

Frozen:

- K1 exact operation-made one-parent object;
- complete parent->K1 delta operation-owned;
- branch/lineage exact;
- while HEAD exactly K1, configured destination `push_dry_run` is used conservatively:
  - `=` => already published; not normal Class A;
  - new/fast-forward => may continue;
  - rejection/unknown => reconcile;
- exact K1 becomes Candidate C2 and is independently authorized by R2;
- R2/supersession stored in deterministic metadata-only child K2;
- K2 no domain/transition delta, no recursive Receipt; mismatch -> reconcile;
- only after exact K2 proof is branch pushed.

### R8 — Roadmap `PersistedProjectionAdapter`

`REVIEW_SYSTEM_P1_R8_ROADMAP_PROJECTION_ADAPTER_CONTRACT.md`

Frozen semantic round-trip reuses live `RoadmapPlan`, `roadmap_request_identity()`, stable reservations, registration helpers, `ProjectView.with_effects()` and fresh `ProjectView.load()`.

PASS requires reviewed normalized Roadmap/Phase/relation semantics to equal reconstructed canonical semantics using exact created IDs, plus exact physical commit-delta proof and structure validation.

Request identity alone is not semantic proof.

### R9 — Phase Entry `PersistedProjectionAdapter`

`REVIEW_SYSTEM_P1_R9_PHASE_ENTRY_PROJECTION_ADAPTER_CONTRACT.md`

Frozen round-trip covers normal Works, integration, optional confirmation, Related, planned/requires edges and affiliation using exact reservations and canonical reload.

Important live seam discovered:

```text
PhaseEntryDesign.entry
```

currently affects immediate selection/return but is not persisted as canonical plan state. Review metadata is forbidden from becoming progression truth.

Therefore review-v1 Phase design is frozen to be **canonically self-selecting**:

- the persisted graph itself must leave zero/one unique first Work as appropriate;
- explicit `entry` cannot be the sole mechanism resolving a canonical ambiguity;
- when supplied, `entry` must equal the unique Work the canonical graph selects;
- legacy behavior remains until P2 activation.

This closes the seam without adding a second state source or Candidate 8 architecture change.

### R10 — Project / Global Policy adapter hook

`REVIEW_SYSTEM_P1_R10_POLICY_ADAPTER_HOOK_CONTRACT.md`

Frozen common protocol responsibilities only:

```text
scope identity
loader/schema/default identity
normalize reviewed before/after
expected persisted projection
canonical reload
normalized semantic equality
```

P1 deliberately does not invent Project Policy path/schema, Global root Policy path/schema, physical owners or root maintenance primitives. Those are P6/P7 live-contract decisions. Unimplemented Policy Review kind fails explicitly; no fallback to `project.yaml` or generic dictionary persistence.

### R11 — Evidence dependency-class adapter contract

`REVIEW_SYSTEM_P1_R11_EVIDENCE_DEPENDENCY_CLASS_CONTRACT.md`

Frozen vocabulary v1 minimum classes:

```text
repository_files
filesystem_external
environment
subprocess
network
clock
randomness
locale
dynamic_libraries
runtime_toolchain
hardware
external_service
cache_state
git_state
```

Coverage mode per required class:

```text
observed | pinned | denied | unknown
```

Complete only where the required-class declaration itself is closed and every required class is mechanically accounted for. Unknown -> no cross-Candidate reuse. Same manifest feeds R6 Review-validity proof.

### R12 — Recovery / invariant tests

`REVIEW_SYSTEM_P1_R12_RECOVERY_INVARIANT_TEST_CONTRACT.md`

Frozen activation test matrix covers:

- lazy canonical layout / malformed chains / ID reservation;
- accepted/settled/sealed Gate interruption windows;
- seal + Receipt partial stage;
- terminal event + Consumption partial stage/cardinality;
- K1 local commit / proof / push windows;
- R6 closure reuse/invalidation;
- Class A K1 already-remote / K2 mismatch / no recursion;
- Roadmap semantic round-trip fault injection;
- Phase semantic round-trip including ephemeral-entry ambiguity rejection;
- generic Policy adapter harness;
- Evidence dependency coverage;
- clone/runtime cleanup;
- authority boundary: Review metadata never changes `state.py` lifecycle.

P1/P2/P3 activation gates require the corresponding interruption/fault-injection tests, not happy path alone.

## 3. Cross-contract implementation shape now frozen

The P1 implementation can now be decomposed without another architecture-review cycle:

```text
A. ReviewStore + canonical record render/load/validation
B. central Review ID extensions/reservation helpers
C. Gate Generation + Receipt orchestration under parent operation owner
D. common Consumption model/cardinality loader
E. Git commit-only / proof / push-only primitives
F. complete commit-delta/tree-entry and Review-validity closure plumbing
G. Class A adoption flow
H. PersistedProjectionAdapter protocol
I. Roadmap adapter
J. Phase-entry adapter with review-v1 canonical self-selection guard
K. Policy adapter hook (no concrete policy store yet)
L. Evidence dependency manifest/completeness engine
M. synthetic/recovery/invariant test suite
```

P1 itself still does **not** activate Work terminal Review gating; that remains P3 after common infrastructure and tests exist.

## 4. Live code changes required later (not performed in reconnaissance)

Likely implementation surfaces now identified:

```text
src/workline/store.py          ReviewStore/path integration or adjacent review_store module
src/workline/validate.py       separate Review structural validation
src/workline/ids.py            rr/rcp/rcs/rtk kinds
src/workline/mutation.py       sanctioned stage commit ID/proof checkpoint access as needed
src/workline/gitops.py         commit-only / push-only Review-v1 primitives
src/workline/gitcmd.py         complete tree/delta/attributes/config/hook inspection primitives
src/workline/roadmap.py        adapter hooks + review-v1 self-selecting Phase guard at P2
src/workline/start.py          Review-v1 commit/proof/push + terminal Consumption at P3
registry/canonical Skills      activation/authority text only when implementation is ready
new Review modules/tests       common Review domain/store/orchestration/adapters
```

This list is implementation targeting, not permission to update canonical authority before behavior exists.

## 5. Architecture/HUMAN result

After R1-R12 live reconnaissance:

```text
Architecture blockers: None
HUMAN decisions required: None
Candidate 8 required: No
```

The only notable newly exposed live seam was PhaseEntryDesign `entry` not being canonical persisted state. It is resolved as an implementation-contract restriction for `review-v1`: canonical relations/state must independently determine the same first Work, so Review metadata never becomes progression authority.

No finding requires changing Candidate 7's core authority/lifecycle architecture.

## 6. Next stage

```text
Candidate 7 architecture: frozen for implementation
P1 Integration Contract Reconnaissance: COMPLETE
R1-R12 contracts: FROZEN
P1 implementation: NOT STARTED
```

Next work is P1 implementation against these frozen contracts, beginning with common storage/ID/Gate/ReviewStore foundations and their invariant tests before any Review-v1 planning or START gate activation.