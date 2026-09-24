# Review System P3 — F2 Work Candidate / Review Validity / Evidence Contract Freeze

Status: CONTRACT FROZEN / IMPLEMENTATION NOT STARTED / LIVE BASELINE `098600b1c7555dd7f0be303c52d4360e80e17661`

P3 implementation remains NOT STARTED. Nothing in this document is activated by writing it, and it authorizes no
Gate of the P3 F1 ordered prerequisites.

---

## 1. Status, baseline, authority and precedence

### 1.1 Baseline

Frozen against live `main` at `098600b1c7555dd7f0be303c52d4360e80e17661` — the landed P3 F1 contract plus its
post-landing repair. Measured at that baseline, `src/`, `tests/`, `registry.md` and `.claude/` are byte-identical
to `68085d6`, the baseline P3 F1 was frozen against, so every F1 live fact carries over unchanged and was
re-verified here rather than assumed.

Decisions in this document are not rebased onto another baseline silently. A later implementation re-verifies the
live facts of §3 first.

### 1.2 Authority

Runtime authority is, and remains:

```text
1. registry.md
2. registry-routed canonical Skills
3. live implementation / tests
```

This document is a **frozen implementation contract**, not runtime authority. It changes no behaviour until the
corresponding implementation lands and the authority statements of §17 are activated.

### 1.3 Precedence

P1 and P2 freeze documents and the P3 F1 contract remain as they are and are **not edited**. F2 is bound by them.
Where F2 must control a P3 question differently, it says so as a **forward amendment**, naming the document, the
section, the change, the reason and its exact limit. Broad supersession is prohibited, and no decision of this
contract is described as inheritance where it in fact narrows or changes a prior text.

Forward amendments made here, and only these:

```text
P1 R1 §6 / P1 R3 §4   narrowed for review-v1-work-v1 (§6.4): the Candidate material binds path,
                      mode, deletion and content identity exactly, and binds symlink semantics
                      exactly; it does NOT support a gitlink at a result path. A Project whose
                      HEAD tree holds any gitlink cannot use review-v1-work-v1, refused at START
                      entry. This narrows the supported object-kind set of a Work Candidate at
                      this contract version; it relaxes nothing and adds no guess.
```

F1's own forward amendments (P1 R4 §2, P1 R4 §4.2, P1 R5 §8) are inherited unchanged. F2 re-amends none of them.

### 1.4 F1 decisions F2 preserves without change

F1-D1 through F1-D11 are binding. In particular F2 changes nothing about: explicit per-invocation opt-in; the
durable `review_contract` / `publication_contract` markers; pending-mutation contract mismatch; activation as
Project capability × per-invocation selection; the dedicated activation producer; activation immutability and
uniqueness; `work-terminal-activation-digest-v1`; the repaired post-activation classification (marker → review-v1,
no marker → legacy, unknown → reconcile, contradictory → reconcile); no migration; result-less Option B; and the
ownership boundary.

---

## 2. F2 scope and non-scope

### 2.1 In scope — frozen here

```text
D1   Work Formal Review identities                                    §4
D2   Work Candidate canonical schema and candidate_hash               §5
D3   result-bearing Candidate content                                 §6
D4   empty-artifact Candidate content                                 §7
D5   the three Work-kind projections                                  §8
D6   Candidate reconstruction and provenance                          §9
D7   Work Review Context                                              §10
D8   activation binding                                               §11
D9   reviewer identity/version binding                                §12
D10  reviewer task / request envelope                                 §12
D11  Evidence execution model                                         §13
D12  dependency completeness and coverage                             §13
D13  ReviewValidityClosure for Work                                   §14
D14  HEAD advancement validity                                        §14
D15  sealing / Receipt semantic boundary                              §15
D16  invalidation boundary                                            §16
D17  canonical authority activation plan                              §17
```

### 2.2 Out of scope — deferred, named in §19

F2 freezes **what is valid, what is bound, and what change invalidates validity**. It does not freeze K1/K2 proof
checkpoints or commit topology, the split publication validator, the terminal Consumption stage, Class A/B/C, stale
generation mechanics, adoption, or the recovery matrix. Those are F3 and F4.

### 2.3 The no-trap rule

F1-D10 rejected an option because it refused an ordinary, correct Work *after* the executor had already produced
it, leaving a pending review-v1 mutation that could neither continue nor be retried as legacy. F2 adopts that
reasoning as a rule:

```text
An outcome that is ordinary and correct MUST be expressible as a Work Candidate.

An outcome outside the expressible domain refuses. That refusal is an ordinary reconcile - a
human decides, exactly as for any other STOP that strands a pending mutation - and never a
contract trap, PROVIDED the inexpressible set is kept as small as the architecture allows.

Where the condition is knowable before the executor runs, the refusal MUST happen at START
entry instead, so the caller learns it before any work is done.
```

This rule is why §6.4 supports symlinks and the executable mode rather than refusing them, and why the gitlink
limitation is an entry-time refusal rather than a post-executor one.

---

## 3. Measured live architecture

Re-verified at this baseline. These are the facts the decisions rest on.

| # | fact | where |
| --- | --- | --- |
| M-1 | `CandidateSnapshot` carries `candidate_hash`, `reconstruction_mode`, `projection_semantics_version`, `material`, `builder`. `material` is an unconstrained mapping in snapshot mode and must be non-empty; builder mode requires identity, version and a non-empty ordered input list. A digest is never reconstruction material. | `review/records.py` |
| M-2 | `TaskInput` carries `task_id`, `task_slot`, `task_kind`, `reviewer_identity`, `reviewer_version`, `request_envelope`, `request_digest`, `candidate_hash`, `reconstruction_mode`, `candidate_material_digest`, `review_context_hash`, `effective_policy_hash`, `accepted_generation`. No provider handle. | `review/records.py` |
| M-3 | `GateGeneration` carries the chain (`previous_generation`, `previous_digest`), `review_kind`, `target_identity`, `operation_identity`, `candidate_hash`, `review_context_hash`, `effective_policy_hash`, `evidence_digest`, `coverage_digest`, `raw_report_set_digest`, `adjudication_digest`, `obligation_digest`, full-snapshot `accepted_tasks` / `settled_tasks`, `status`, `receipt_id`, `authorized_operation_stage`. | `review/records.py` |
| M-4 | `Receipt` carries `target_identity`, `operation_identity`, `authorized_candidate_hash`, `review_context_hash`, `effective_policy_hash`, `coverage_hash`, `adjudication_hash`, `obligation_digest`, `unresolved_obligations` (must be 0) and `authorized_operation_stage`. `target_identity` and `authorized_operation_stage` are free text. It carries no commit SHA of its own storage. | `review/records.py` |
| M-5 | P2 builds a kind's Candidate as `{schema, version, review_kind, projection{projection_kind, semantics_version, content}, declared_base}` and `candidate_hash = digest(that record)`; the snapshot's `material` **is** that record. | `review/planning.py` |
| M-6 | P2's Context binds `review_kind`, `contract`, `projection_semantics_version`, `adapter_identity`, `loader_identity`, `authority` digests, `git_persistence`, `checkout_capability`. | `review/planning.py` |
| M-7 | `rules/git`, `rules/ai-decision`, `rules/human-confirmation` and `rules/information-tracing` carry a `workline-id` but **no** `workline-target`: their text lives inside `registry.md`. Binding the `registry` digest therefore binds all four rules. Only `skills/*` resolve to separate files. | `registry.md`, `registry.py` |
| M-8 | `gitcmd.hash_blob(repo, data)` returns the Git blob object id of arbitrary bytes and **writes nothing**. Exact Git object identity is therefore computable for working-tree bytes before any commit exists. | `gitcmd.py` |
| M-9 | `gitcmd.tree_entries(repo, commit, …)` returns `mode`, `type`, `oid`, `path`; a gitlink entry has type `commit`. Whether a Project holds any gitlink is decidable from HEAD before the executor runs. | `gitcmd.py` |
| M-10 | `review/closure.py` implements `ReviewValidityClosure`, `ReviewProvenance`, `SurfaceClosure`, `EvidenceDeclaration`, `MechanismProof`, `may_reuse`, the seven required surfaces and R11's fifteen dependency classes. Nothing constructs one; no record persists one. Its `to_record` emits `surfaces` / `evidence_dependencies` / `git_semantics` / `review_provenance_dependencies`, which is the live resolution of R6 §2's field sketch. | `review/closure.py` |
| M-11 | `review/projections.py` implements the three projection kinds and `normative()`, which answers no for `operation_metadata`. Kind-specific contents are absent. | `review/projections.py` |
| M-12 | START's `Completed` carries `result_paths`, `message`, `deleted_paths`. `completion_precheck` requires each result path to exist and each deleted path to be a tracked file that is now absent. `declare_own_content` records a sha256 per owned path at the moment the executor returns. | `start.py`, `mutation.py` |
| M-13 | A Work with no owned result paths produces no result commit: `_Session._commit` returns before recording a Git stage when nothing differs from HEAD. | `start.py` |
| M-14 | `state.py` derives lifecycle from events alone and imports nothing from `review/`; the pin that it contains no Review dependency is live. | `state.py`, `tests/test_review_authority.py` |

---

## 4. Work Review identities (F2-D1)

### 4.1 Frozen identities

```text
review_kind                    "work-result-v1"
task_kind                      "work-result-review-v1"
task_slot                      "work-result-reviewer"
projection_semantics_version   "work-result-projection-v1"
adapter_identity               "work-result-adapter-v1"
authorized_operation_stage     "start:work-terminal"
```

None collides with P2's registered strings (`roadmap-plan-v1`, `phase-entry-design-v1`, `planning-review-v1`,
`roadmap-plan-reviewer`, `phase-entry-design-reviewer`, and their projection/adapter identities).

### 4.2 Target and operation identity

```text
target_identity      the stable Work ID, verbatim

request identity     {schema: "review-work-request-identity", version: 1,
                      work_id: <Work ID>,
                      review_contract: "review-v1-work-v1"}

operation_identity   "start:" + SHA-256 of the canonical bytes of that request identity record
```

This keeps P2's `"<operation>:<digest>"` shape. The START **mode** (`single-work` / `outer`) is deliberately
**not** in the request identity: it decides how far the driving operation continues, not what is reviewed, and a
Work completed under one mode is the same completion as under the other. The review contract **is** in it, so a
future Work review contract is a different operation rather than a silent continuation of this one.

### 4.3 Relationship to F1's contract string

Two versioned strings exist and they are deliberately in different namespaces:

```text
"review-v1-work-v1"   F1-D1 / F1-D2: the START caller selector and the durable mutation
                      review_contract marker. It says which START contract is running.

"work-result-v1"      F2-D1: the Review Run kind. It says what kind of Review this is and which
                      records, projections and adapter apply.
```

The Work Review Context (§10) binds **both**, so a Run whose kind and whose contract do not agree is detectable
from canonical records alone. Neither string is derived from the other, and neither is inferred from state.

### 4.4 Prohibited in identity

No display number, timestamp, PID, clock reading, mutation id, host, path, branch name or ordinal takes part in any
identity frozen here. Identities are content digests or stable IDs.

---

## 5. Work Candidate schema (F2-D2)

### 5.1 Frozen record

```text
{
  schema:   "review-work-candidate"
  version:  1
  review_kind: "work-result-v1"
  projection: {
      projection_kind:  "reviewed_artifact"
      semantics_version: "work-result-projection-v1"
      content: <the ReviewedArtifactProjection content of §6 or §7>
  }
  declared_base: <the base lineage of §5.3>
  activation:    <the activation binding of §11>
}
```

Exactly these six keys. Canonical form is the P1 Review serializer: mapping keys in ascending code point order at
every depth, sequences in given order, UTF-8, LF.

This mirrors P2's Candidate shape (M-5) and adds exactly one field, `activation`, because a Work Candidate is only
meaningful inside an activated Project and F1 deferred that binding to F2. It is **not** a copy of the planning
Candidate's content: §6 and §7 derive the content from live START completion semantics.

### 5.2 `candidate_hash`

```text
candidate_hash = SHA-256 of the canonical bytes of the Work Candidate record above
```

Nothing else. Not the artifact alone, not the projection alone, not the Receipt, not the Consumption, not any
commit. Two Candidates with the same artifact but a different declared base, a different activation binding or a
different review kind are different Candidates.

### 5.3 `declared_base` — base lineage

```text
{
  base_commit:  <full commit id of HEAD when the completion was decided>
  branch:       <full ref name, "refs/heads/<name>">
  work: {
      work_id:        <stable Work ID>
      display:        <the Work's display at the base>
      name:           <the Work's name at the base>
      desired_state:  <the Work's desired state at the base>
      phase_id:       <the Work's phase id at the base, or null for a standalone Work>
      state:          <the derived Work state at the base>
  }
  dependencies: [ {relation_id, from, from_state} ... ]   the Work's requires_completion
                                                          edges at the base, sorted by relation_id
  read_obligations: [ {relation_id, type, to} ... ]        the Work's current read obligations at
                                                           the base, sorted by relation_id
}
```

Every field is read from the **committed state of `base_commit`**, through the canonical loader, never from the
working tree. `state` and `from_state` are the derived state strings `state.py` produces, not event records — so
the Work Candidate is unaffected by the F1 Gate 1 Event metadata carrier, and cannot become a second reader of
lifecycle events.

`base_commit` is HEAD at the moment the completion is decided, which is the same commit F3 will later require as
K1's parent for a result-bearing Work. F2 binds it as **lineage**, not as a commit proof: the Candidate says what
the result is measured against, and F3 says what must be proven about the commit that carries it.

### 5.4 Not in the Candidate

```text
K1 commit id             does not exist yet (F1 invariant; §19 defers it to F3)
K2 commit id             likewise
Receipt / Consumption    OperationMetadataProjection, never Candidate content (§8.3)
the working tree at large only the declared owned change set is reviewed (§6.2)
runtime material         never (§20 invariant 7)
the START mode           §4.2
```

---

## 6. Result-bearing Candidate (F2-D3)

### 6.1 Frozen content

```text
content = {
  artifact_kind: "result_commit"
  entries: [ <one entry per owned path, sorted by the path's UTF-8 bytes> ]
  message: <the result commit message the completion decided, exactly as it will be committed>
}
```

`artifact_kind` inside the Candidate names the **shape of the reviewed artifact**. It is deliberately spelled the
same as the Consumption field F1 §11.3 introduced, because it answers the same question, but the two are separate
records with separate responsibilities: the Candidate states what was reviewed, the Consumption states what was
consumed. Neither reads the other's field (§8.3, §15.3).

### 6.2 The owned change set, and nothing else

The reviewed surface is exactly `result_paths ∪ deleted_paths` as the executor declared them — the same owned set
START protects with `declare_own_content` and commits by exact path. The working tree at large is **not** the
artifact, and a path outside the declared set never enters the Candidate, however dirty it is.

### 6.3 Entry shape

Each entry binds exact Git object identity against `declared_base.base_commit`:

```text
{
  path:       <repository-relative POSIX path, exactly as declared>
  status:     "A" | "M" | "D"
  old_mode:   <"100644" | "100755" | "120000", or "000000" when the base holds nothing>
  old_blob:   <full blob id at the base, or the all-zero id when the base holds nothing>
  new_mode:   <"100644" | "100755" | "120000", or "000000" for a deletion>
  new_blob:   <full blob id of the bytes the executor produced, or the all-zero id for a deletion>
  content_sha256: <SHA-256 of those same bytes, or null for a deletion>
}
```

* `old_mode` / `old_blob` come from the base commit's tree.
* `new_blob` is `gitcmd.hash_blob` of the bytes at the path **as the executor left them** (M-8). Nothing is
  written and no commit is needed, which is what lets the Candidate exist before K1.
* `content_sha256` is the same digest `declare_own_content` already records, so the Candidate and START's
  own-bytes proof speak about the same bytes.
* `status` is derived: absent at base → `A`; present at base → `M`; declared deleted → `D`.
* Ordering is by the path's UTF-8 bytes, so the record is canonical and diffable.

An entry whose `old_*` equals its `new_*` is a declared result that changed nothing. It stays in the Candidate,
because what the executor declared is part of what is reviewed.

### 6.4 Object kinds — supported, and the one narrowing

```text
supported   100644   regular file
            100755   regular file, executable
            120000   symlink; new_blob is the blob id of the link target bytes, exactly as Git
                     stores a symlink, and content_sha256 is the SHA-256 of those same bytes
            deletion of any of the above

refused     a gitlink (mode 160000, tree entry type "commit")
```

**Symlinks and the executable mode are supported deliberately**, under the no-trap rule (§2.3): they are ordinary,
correct results, they are fully expressible with live primitives, and refusing them after the executor returned
would recreate exactly the trap F1-D10 rejected.

**Gitlinks are not supported at this contract version**, and this is the forward amendment of §1.3 against
R1 §6 / R3 §4. A gitlink's identity is a commit in another repository; the Candidate cannot bind its content, and
`hash_blob` does not apply. To keep this out of the trap, the refusal is **entry-time, not post-executor**: a
review-v1 START refuses at entry, before the lock takes effect on any write and before the executor runs, when
HEAD's tree holds any entry of type `commit` (M-9). The caller learns immediately, nothing is stranded, and legacy
START is unaffected.

### 6.5 Post-executor refusals

A declared path that is a directory, or that cannot be read, makes the Candidate unavailable:

```text
review_candidate_unavailable    the declared owned set cannot be projected exactly
```

This is a post-executor refusal and therefore a reconcile, permitted by §2.3 because the input is malformed rather
than ordinary: a directory declared as a file result is not a correct result declaration. Legacy START keeps its
current behaviour for the same input; nothing about legacy changes.

---

## 7. Empty-artifact Candidate (F2-D4)

### 7.1 When it applies

Exactly when the owned change set is empty — `result_paths` and `deleted_paths` are both empty, so START makes no
result commit at all (M-13). This is F1-D10 Option B, closed here to an exact schema.

### 7.2 Frozen content

```text
content = {
  artifact_kind: "empty"
  entries: []
  emptiness_proof: {
      base_commit:  <the same commit as declared_base.base_commit>
      declared_result_paths: []
      declared_deleted_paths: []
      owned_paths_differing_from_base: []
  }
}
```

`message` is absent: there is no result commit to carry one.

### 7.3 What is reviewed, and what proves the emptiness

What is reviewed is **that this Work is correctly complete having produced no file result** — a semantic
completion. The reviewer judges the declared base (§5.3): the Work, its desired state, its dependency states and
its read obligations as of `base_commit`, together with the positive statement that the owned change set is empty.

The emptiness is proven positively, not by absence of evidence: the operation declares the empty owned set, and
`owned_paths_differing_from_base` is the enumeration — necessarily empty — of paths in that set that differ from
the base. An empty-artifact Candidate is refused if any declared path exists, which makes the two artifact kinds
mutually exclusive by construction rather than by convention.

### 7.4 Base lineage and `candidate_hash`

Identical rules to §5.3 and §5.2: `declared_base` is bound exactly as for a result-bearing Candidate, and
`candidate_hash` is the digest of the whole Candidate record. An empty-artifact Candidate therefore still has exact
base lineage and exact identity.

### 7.5 Distinguished from a result-bearing Candidate

By `content.artifact_kind` alone, which is part of the canonical bytes and therefore part of `candidate_hash`. A
reader never infers the kind from the emptiness of `entries`.

### 7.6 Prohibited

```text
a fake, placeholder, empty-string or all-zero commit id standing in for K1
a synthesized empty commit created so that a K1 exists
treating "no commit" as "no Candidate"
reusing Consumption.artifact_kind as the Candidate's statement, or vice versa
```

`Consumption.artifact_kind` (F1 §11.3, Gate 2) is **operation metadata** recording what was consumed. The
Candidate's `content.artifact_kind` is **reviewed artifact content**. They will agree in a correct operation, and
F3 owns the rule that checks that they do; neither is computed from the other here.

---

## 8. The three Work projections (F2-D5)

### 8.1 `ReviewedArtifactProjection`

```text
kind              reviewed_artifact
semantics version work-result-projection-v1
content           §6.1 (result-bearing) or §7.2 (empty-artifact)
```

This is the exact artifact whose correctness the reviewer judges, and the only projection inside the Candidate.

### 8.2 `AuthorizedTransitionProjection`

The canonical domain transition the START owner may apply **under this authorization**, and nothing more:

```text
kind              authorized_transition
semantics version work-result-projection-v1
content = {
  work_id:      <the Work>
  events:       ["work_target_removed", "work_completed"]
  base_commit:  <declared_base.base_commit>
}
```

Frozen properties:

* it names **event types and their order**, not event IDs — the IDs are reserved by the owning mutation at
  transition time and are not knowable when the Candidate is frozen;
* it authorizes exactly the completion transition of exactly this Work. It authorizes no other Work, no other
  event type, no relation change and no registration;
* it is produced and **bound into the gate**, not into the Candidate: it states what may follow from the
  authorization, while the Candidate states what was judged. Its exact placement in a mutation stage is F3;
* it is a normative projection (`projections.normative` answers yes), so a mismatch between it and what the
  operation later applies is a refusal, not a note.

### 8.3 `OperationMetadataProjection`

```text
kind              operation_metadata
semantics version work-result-projection-v1
content           the Review bookkeeping of this operation: the Receipt reference, the Consumption
                  reference, any Supersession reference, and the Run/generation identities
```

Frozen boundary, absolute:

```text
OperationMetadataProjection is NEVER lifecycle truth and NEVER a correctness authority.

Nothing in state.py, ProjectView, validate_structure, startability or progression reads it.
No Candidate content is computed from it.
No projection of this kind informs whether the artifact is correct.
```

`projections.normative()` already answers no for this kind; F2 adds no exception and requires that the live pin on
`state.py` (M-14) keeps holding.

### 8.4 Where each lives

```text
ReviewedArtifactProjection       inside the Candidate record (§5.1), and therefore inside candidate_hash
AuthorizedTransitionProjection   bound into the gate generation and the Receipt's authorization scope
OperationMetadataProjection      the Review records themselves; never inside the Candidate
```

---

## 9. Candidate reconstruction and provenance (F2-D6)

### 9.1 Frozen reconstruction mode

```text
review-v1-work-v1 uses snapshot mode only.
builder_v1 is not used for the Work kind at this contract version.
```

Reason: the reviewed artifact is bytes an executor produced. There is no deterministic builder that can regenerate
them from clone-safe inputs, which is precisely what builder mode requires (M-1). Declaring builder mode would
make the record claim a reconstruction that does not exist.

### 9.2 Snapshot material

```text
CandidateSnapshot.material            = the whole Work Candidate record of §5.1
CandidateSnapshot.candidate_hash      = §5.2
CandidateSnapshot.reconstruction_mode = "snapshot"
CandidateSnapshot.projection_semantics_version = "work-result-projection-v1"
CandidateSnapshot.builder             = null
candidate_material_digest             = SHA-256 of the canonical bytes of the snapshot record
```

This is exactly P2's arrangement (M-5) with the Work Candidate as material, so no second reconstruction mechanism
is introduced and `ReviewStore.provenance_problems` applies unchanged.

### 9.3 What "reconstructible" means here

The Candidate is **self-describing**: it binds path, status, modes, blob ids and content digests, plus the base
commit and branch. After a clone or a loss of `.workline/runtime/**`, a reader rebuilds the exact reviewed artifact
identity from the snapshot record alone, and can re-derive every `old_*` value from `base_commit` and every
`new_*` value from the committed result once K1 exists.

The reviewed **bytes** themselves are not copied into the record. What is stored is their exact Git object identity
and content digest, which is what the artifact's identity *is*. This satisfies R1 §6's rule — a digest is never
reconstruction material — because the record carries the full structured projection, not a bare hash of it.

### 9.4 Mismatch behaviour

```text
snapshot missing, unreadable, or not a Work Candidate record      fail closed
material does not digest to the Run's candidate_hash              fail closed
reconstruction_mode is not "snapshot"                             fail closed
projection_semantics_version is not this contract's               fail closed
a later well-formed replacement of the snapshot that happens to
  reproduce the same candidate_hash                               a Review-validity material
                                                                  change (R3 §5); never silently
                                                                  reused
```

Every one of these is `reconcile_required`; none degrades to a weaker Review contract, and none allocates a
substitute identity.

---

## 10. Work Review Context (F2-D7)

### 10.1 Frozen record

```text
{
  schema:  "review-work-context"
  version: 1
  review_kind:        "work-result-v1"
  review_contract:    "review-v1-work-v1"
  projection_semantics_version: "work-result-projection-v1"
  adapter_identity:   "work-result-adapter-v1"
  loader_identity:    <content identity of the running implementation package>
  authority:          [ {id, digest} ... ]         §10.2
  git_persistence:    <the Git persistence semantics identity>      §10.3
  activation:         <the activation binding of §11>
}
```

`review_context_hash` is the SHA-256 of this record's canonical bytes.

Both versioned strings of §4.3 are present, so a Run whose kind and contract disagree is detectable from canonical
records alone.

### 10.2 Authority digests — what is bound and why

```text
bound       registry          registry.md
            skills/start      the operation owner of a Work completion
            skills/review     the Review gate's own authority
            skills/create     START registers derived Works through CREATE during a Work cycle

not bound   skills/roadmap, skills/phase-create, skills/project-start, skills/project-router
```

Each is the SHA-256 of the file's bytes with CRLF read as LF, the same rule P2 uses.

The four `rules/*` are **not listed separately and do not need to be**: measured at this baseline they carry a
`workline-id` but no `workline-target`, so their text lives inside `registry.md` (M-7). The `registry` digest
therefore already binds `rules/git`, `rules/ai-decision`, `rules/human-confirmation` and
`rules/information-tracing` exactly. An implementation that later moves a rule into its own file must add it here;
that is a Context version change, not a silent extension.

The excluded Skills are excluded because they cannot affect what a Work result means: Roadmap and Phase CREATE own
planning, and Project開始 and the router own bootstrap and dispatch. Binding them would make an unrelated planning
edit invalidate every Work Review — which is the "bind everything by inertia" failure R6 warns against. `create` is
bound because a Work cycle can register derived Works through it, so its rules materially affect what a completion
may contain.

### 10.3 Git persistence semantics

The Context binds the identity of the Git persistence semantics the review-v1 Work path uses. F2 binds the
**identity**; the primitive's behaviour is F1-D11 (already frozen: the contained commit primitive, hooks
suppressed, signing disabled) and its use at commit time is F3.

```text
git_persistence = "review-v1-work-local-v1"
```

Checkout capability is **not** bound in the Work Context. P2 binds it because planning writes canonical Review
records whose committed bytes must reproduce exactly; a Work result's bytes are the executor's, and the Candidate
binds them by Git object identity (§6.3), which is the identity Git itself will store. A later contract version
that needs a checkout-capability claim adds it as a Context version change.

### 10.4 Effective Policy

```text
policy_id = "review-v1-work-policy-v1"
```

A single static Policy for the Work kind, of the same shape and with the same canonical-digest rule as P2's:
one required task slot (`work-result-reviewer`), the report statuses, severities, blocking severities, the
adjudication rule, the obligation rule and the seal rule. `effective_policy_hash` is the digest of its canonical
bytes. F2 introduces no adaptive or project-local policy machinery; that remains a later phase.

---

## 11. Activation binding (F2-D8)

### 11.1 The two digests, kept apart

This is the distinction F1 warned must not be blurred:

```text
work-terminal-activation-digest-v1     F1-D7. A digest over the canonical parsed Event records of
                                       the pre-activation event-log prefix. It is a FIELD INSIDE
                                       the activation record (legacy_event_prefix_sha256).

activation record digest               F2. The SHA-256 of the canonical bytes of the whole
                                       activation record, taken with the P1 Review record
                                       serializer, exactly as every other Review record digest.
```

They are computed over different material by different rules and are never substituted for one another.

### 11.2 Frozen binding

```text
activation = {
  record_digest:        <the activation record digest of §11.1>
  operation_contract:   "review-v1"
  activation_base_head: <the activation record's activation_base_head>
}
```

This block appears in **both** the Candidate (§5.1) and the Context (§10.1), with identical content.

* `record_digest` is the single source of truth for the activation's identity. `legacy_event_count` and
  `legacy_event_prefix_sha256` are **not** copied out: they are inside the record the digest covers, so copying
  them would create the second source of truth F1 prohibits.
* `operation_contract` and `activation_base_head` are carried in the clear **as well**, and this is not a second
  source of truth: both are also inside the digested record, and a reader that finds a disagreement between the
  clear value and the record it re-reads fails closed. They are carried because a Candidate must state the
  contract it was frozen under and the history point it rests on without first resolving another record.

### 11.3 Frozen rules

```text
A Work Candidate is frozen only in a Project whose activation record is present, well-formed,
of a supported version, and whose prefix digest reproduces (F1 §10.1). Otherwise the review-v1
START has already refused at entry and no Candidate exists.

An activation record digest that does not match the one bound in the Candidate or the Context
invalidates the Review (§16). It is never repaired by re-deriving the digest.

Nothing here makes activation lifecycle truth, and nothing reads the activation record to derive
Work, Phase or Roadmap state.
```

---

## 12. Reviewer and task binding (F2-D9, F2-D10)

### 12.1 Where the reviewer is bound (F2-D9)

```text
NOT bound in   the START durable mutation invocation (F1-D2 / F1-D3 forbid it: a reviewer version
               change must never become a pending-mutation contract mismatch)

bound in       the Review gate, at acceptance:
                 the TaskInput record        (reviewer_identity, reviewer_version)
                 the accepted task descriptor in gate generation 1
```

It becomes canonical when generation 1 is written and its record is committed. This is exactly P2's split, and it
means a reviewer identity or version that changes between invocations is a **gate** question, never a mutation
contract question.

### 12.2 What a retry compares

```text
the invocation's reviewer identity/version   vs   the accepted task descriptor's
  differ  -> StopError, code review_reviewer_mismatch; nothing is settled, the task is not
             launched, the gate is unchanged and the Run stays exactly as it is

a settlement whose report names another reviewer identity/version than the accepted descriptor
  -> the same refusal, at settlement
```

`review_reviewer_mismatch` already exists in the live taxonomy and is reused verbatim. **F2 introduces no new
refusal code.** Every refusal it names is one of: `review_contract_invalid`, `review_reviewer_mismatch`,
`review_context_unavailable`, `review_report_invalid`, `review_record_invalid`, `reconcile_required`, and the one
code F1 introduced, `review_not_activated`. The single new *value* F2 needs is `review_candidate_unavailable`
(§6.5) for a declared owned set that cannot be projected exactly; no existing code states that, and it is scoped to
exactly that condition.

### 12.3 Request envelope (F2-D10)

```text
{
  schema:  "review-work-request"
  version: 1
  review_kind: "work-result-v1"
  policy_id:   "review-v1-work-policy-v1"
  instruction: "review-v1-work-instruction-v1"
  candidate:   <the whole Work Candidate record of §5.1>
  context:     <the whole Work Review Context record of §10.1>
  work: {
      work_id:  <the Work ID>
      display:  <the Work's display at the base>
      name:     <the Work's name at the base>
      desired_state: <the Work's desired state at the base>
  }
}
```

`request_digest` is the SHA-256 of its canonical bytes.

* The Candidate and the Context are carried **whole**, not by digest, so the reviewer sees exactly what is being
  judged and a clone can rebuild the identical request.
* The activation identity reaches the envelope through both the Candidate and the Context (§11.2); it is not
  carried a third time.
* The `work` block repeats the human-facing identity of the target so a reviewer has it without re-deriving it;
  every field is a copy of `candidate.declared_base.work`, and a disagreement is a malformed envelope.
* The reviewer identity and version are **not** in the envelope. They are in the TaskInput and the accepted
  descriptor (§12.1), which is where they are compared.
* No provider job handle, no runtime path, no session identity and no clock reading appear anywhere.

### 12.4 TaskInput and accepted descriptor

Both are the live P1 records, used unchanged (M-2, M-3): `TaskInput` binds the envelope, `request_digest`,
`candidate_hash`, `reconstruction_mode`, `candidate_material_digest`, `review_context_hash`,
`effective_policy_hash`, `accepted_generation`, and the reviewer identity and version; the accepted descriptor
carries every one of those into generation 1. F2 adds no field to either.

---

## 13. Evidence execution and dependency completeness (F2-D11, F2-D12)

### 13.1 What Evidence is, and is not

```text
Evidence is    the canonical record of the checks Workline itself performed before authorization,
               each named, each with a result, each reproducible from committed material.

Evidence is NOT the reviewer's report. A reviewer saying "OK" is an adjudication input, recorded
               through raw_report_set_digest and adjudication_digest, and it is never Evidence.
```

The gate keeps these apart already (M-3), and F2 keeps them apart: `evidence_digest` covers §13.2,
`raw_report_set_digest` and `adjudication_digest` cover the reviewer's return, `coverage_digest` covers which
required task slots were settled.

### 13.2 Frozen Evidence checks for the Work kind

```text
activation-valid        the activation record is present, well-formed, supported, and its prefix
                        digest reproduces
candidate-projection    the declared owned set projects exactly to the Candidate's entries, with
                        every mode and blob identity resolved
object-kinds            every entry is a supported object kind (§6.4), and HEAD's tree holds no
                        gitlink
base-lineage            declared_base reproduces from base_commit's committed state through the
                        canonical loader
own-bytes               every owned path still holds exactly what the operation recorded putting
                        there (START's existing own-bytes rule)
dirty-separability      no pre-existing change overlaps the owned set
review-namespace        every existing Review record reads canonically
completion-precheck     START's own completion precheck passed
```

Each is `pass` or `not-applicable`; there is no `unknown` result for a check. The Evidence record has the same
shape as P2's (a schema, a version and a list of `{check, result}`), and `evidence_digest` is its canonical digest.

### 13.3 Execution basis

```text
executes    inside the START operation, under the Project execution lock, in the operation's own
            process, against the working tree for the owned bytes and against base_commit's
            committed state for everything derived from the base

never       mutates the Project. Any scratch material lives under .workline/runtime/**, is never
            committed and is never authorization.
```

### 13.4 Isolated verification is not in P3

```text
Running the Project's own tests or any other verifier against an exported tree is NOT part of
review-v1-work-v1 Evidence. No such primitive exists at this baseline, and building one is the
repair-loop phase's work, not F2's.
```

The consequence is stated honestly rather than hidden: the dependency classes such a verifier would cover are
declared `unknown`, and therefore **no Work Evidence is reusable across Candidates** (§13.5). Fresh use is
permitted; reuse is not.

### 13.5 Dependency completeness (F2-D12)

The Work Evidence declares, in the live `EvidenceDeclaration` form and R11's fifteen-class vocabulary:

```text
repository_files      observed   the Candidate's entries and the base tree entries, by exact
                                 path + mode + object identity
git_state             observed   base commit, branch, the object identities read, and the
                                 git_persistence identity of §10.3
review_provenance     observed   candidate_hash, candidate_material_digest, task_input_digest,
                                 request_digest, reviewer identity/version, review_context_hash,
                                 effective_policy_hash
runtime_toolchain     pinned     the loader identity of §10.1 and the running Git version
filesystem_external   not_required   the checks read only the Project
clock, randomness,
locale, hardware,
cache_state           not_required   no check depends on them
environment,
subprocess,
dynamic_libraries,
network,
external_service      unknown    a reviewer and any future verifier may reach them, and nothing
                                 here contains them
```

Completeness is therefore `unknown` for `review-v1-work-v1`, by construction and by declaration. Under R11 and the
live `closure.may_reuse`, that means: usable for this authorization, never reusable for another Candidate. F2 does
not claim a completeness it cannot prove.

---

## 14. ReviewValidityClosure and HEAD advancement (F2-D13, F2-D14)

### 14.1 No second closure system

F2 **specializes the live P1 closure** (M-10) and defines no parallel structure. The seven required surfaces, the
fifteen dependency classes, the typed mechanism proofs, `completeness()` and `may_reuse()` are used exactly as
implemented.

### 14.2 Work-specific closure contents

```text
version                          1
base_commit_sha                  declared_base.base_commit

provenance (ReviewProvenance)    candidate_hash, candidate_material_digest, task_input_digest,
                                 request_digest, reviewer_identity, reviewer_version,
                                 review_context_hash, effective_policy_hash;
                                 builder_* are null (snapshot mode, §9.1)

surfaces
  reviewed_artifact              covered    identities: the Candidate's entry identities
  review_provenance              covered    identities: the provenance digests above
  review_context                 covered    identities: review_context_hash and the activation
                                            record digest of §11.2
  evidence                       covered    identities: evidence_digest
  policy                         covered    identities: effective_policy_hash
  git_semantics                  covered    identities: git_persistence, the running Git version,
                                            base_commit, branch
  tool_runtime                   covered    identities: loader_identity

evidence_dependencies            the declaration of §13.5
git_semantics                    {git_persistence, git_version, base_commit, branch}
completeness                     unknown, because §13.5 leaves classes unaccounted
```

### 14.3 Durable home

The closure is bound **by digest**, not stored as a new record kind:

```text
closure_digest = the canonical digest of the closure record

It is carried in the Evidence record as one named entry, so it reaches evidence_digest, and
through evidence_digest it reaches the gate generation and the Receipt.
```

No new canonical record type, no new directory, no change to any P1 record's field set.

### 14.4 HEAD advancement — the validity predicate (F2-D14)

Two layers, and both are required. Layer 1 already exists in the Mutation Controller as Git-write compatibility;
Layer 2 is this contract's.

```text
prior Review validity survives an intervening HEAD advance only when ALL hold:

L1  base_commit is an ancestor of the new HEAD;
    HEAD is on the branch the Candidate bound;
    no commit since base_commit changes any path in the Candidate's owned set.

L2  closure.may_reuse(before, after) == reusable, which requires BOTH closures complete and
    every bound identity unchanged: provenance, every surface's state/identities/proof
    mechanism, the git_semantics identity and every Evidence declaration identity.
```

And the frozen consequence at this contract version:

```text
Because §13.5 makes Work Evidence completeness "unknown", may_reuse can never answer "reusable"
for review-v1-work-v1. Therefore an intervening HEAD advance always requires a NEW Candidate.

This is a fail-closed outcome, stated plainly rather than engineered around. The fast path is
defined so that a later contract version which can prove completeness inherits a predicate that
is already exact; it is not reachable now.
```

`unknown` is never `proven`, and absence of discovered change is never proof of invariance.

### 14.5 Not decided here

Class A/B/C, `adopt_existing_local_commit`, stale-generation mechanics and the recovery matrix are F4 (§19). F2
says what validity *is* and what breaks it; F4 says what to do afterwards.

---

## 15. Sealing and the Receipt semantic boundary (F2-D15)

### 15.1 What a Work Receipt authorizes

```text
A Work Receipt says exactly:

  this exact Candidate (authorized_candidate_hash), under this exact Context
  (review_context_hash) and this exact Policy (effective_policy_hash), for this exact Work
  (target_identity), is authorized for this exact operation stage
  (authorized_operation_stage = "start:work-terminal").

It does NOT say:
  that the Work is completed
  that anything may be pushed
  that the authorization has been or may be consumed
  anything about the commit that stores it
```

`Receipt existence != operation completion`, and `Authorization != Consumption`, exactly as the canonical Review
Skill already states.

### 15.2 No Receipt schema change

Verified against live code (M-4): `target_identity` and `authorized_operation_stage` are free text, so a Work ID
and `"start:work-terminal"` fit without modification; `authorized_candidate_hash`, the Context and Policy hashes,
the coverage, adjudication and obligation digests and the zero-unresolved rule all carry Work semantics as they
stand.

```text
Receipt schema repair required: NO
```

### 15.3 Seal prerequisites

```text
every required task slot of the Policy settled "completed"
zero unsettled accepted tasks
obligation_digest equals the empty-obligations digest
the Run's records read back canonically
```

A seal that first issues the Receipt records both immutable creates in one mutation stage (R3 §7), unchanged.

The Receipt is not the Consumption and does not name one. What consumes it, in which stage, and with which
`artifact_kind`, is F1 Gate 2 plus F3.

---

## 16. Invalidation boundary (F2-D16)

### 16.1 Material facts that invalidate a Work Review

```text
the Candidate changes                    any field of §5.1, hence candidate_hash
the base lineage changes                 base_commit, branch, or any declared_base field
the owned bytes change                   any entry's new_blob or content_sha256
the Review Context changes               review_context_hash, including any bound authority
                                         digest, the loader identity or the activation binding
the Effective Policy changes             effective_policy_hash
the Evidence closure changes             evidence_digest or the closure digest inside it
the reviewer identity or version changes relative to the accepted descriptor
the activation record changes            its record digest no longer matches the bound one
a later generation supersedes            a Supersession of the Receipt exists, or an invalidation
                                         generation exists for the Run
the authorization is already consumed    a Consumption of the Receipt exists
HEAD advances                            §14.4, which at this contract version always requires a
                                         new Candidate
```

### 16.2 Frozen consequence

```text
An invalidated authorization is not consumable, however well-formed the Receipt still is.
An unknown or contradictory identity is invalidating, never a reason to fall back to a weaker
contract and never a reason to treat the Review as still valid.
```

### 16.3 Not decided here

How a stale generation is *created*, how a superseded Run is recovered, what repair or adoption is attempted, and
the full interruption matrix are F4.

---

## 17. Canonical authority activation plan (F2-D17)

No canonical authority is edited by this contract. When F2's implementation lands, these statements need activation.

> Label note: `RV-*`, `ST-*` and `GT-*` are statements of **this** F2 contract. They are not the P1 freeze
> documents `R1`…`R7`, which this document cites by full name.

### 17.1 `skills/review` — Candidate, Context, Evidence, validity

```text
RV-1  the Work Review identities of §4 and their relationship to F1's contract string
RV-2  the Work Candidate schema and candidate_hash of §5
RV-3  the result-bearing Candidate content of §6, including the supported object kinds
RV-4  the empty-artifact Candidate of §7 and its positive emptiness proof
RV-5  the three Work projections of §8, and that OperationMetadataProjection is never lifecycle
      truth or a correctness authority
RV-6  Candidate reconstruction and provenance of §9, snapshot mode only
RV-7  the Work Review Context of §10, its authority set, and why rules/* are bound through
      registry.md
RV-8  the activation binding of §11, and that the activation record digest and
      work-terminal-activation-digest-v1 are different digests over different material
RV-9  reviewer binding at the gate, and the request envelope of §12
RV-10 the Evidence contract of §13, including that a reviewer's report is not Evidence and that
      completeness is unknown at this contract version
RV-11 the ReviewValidityClosure specialization and the HEAD-advance predicate of §14
RV-12 the Receipt semantic boundary of §15 and the invalidation boundary of §16
```

### 17.2 `skills/start` — operation flow and the owner's obligations

```text
ST-1  that START freezes the Work Candidate from the declared owned set at the moment the
      executor returns, before any result commit exists
ST-2  the entry-time gitlink refusal of §6.4, alongside the activation precondition F1 froze
ST-3  the post-executor refusal of §6.5 for a declared owned set that cannot be projected exactly
ST-4  that START runs the Evidence checks of §13.2 and supplies them to the gate
ST-5  that START, not Review, applies the authorized transition, and only the transition the
      AuthorizedTransitionProjection names
```

### 17.3 `rules/git`

```text
GT-1  the Git persistence semantics identity "review-v1-work-local-v1" as a named identity
      (its behaviour is already F1-D11's; its use at commit time is F3's)
```

### 17.4 `registry.md` routing

```text
no change required. F2 adds no Skill and no operation owner: the Candidate, Context, Evidence and
validity statements belong to the existing skills/review, and the operation statements to the
existing skills/start. No new routing entry, and no routing change merely because a new Review
kind exists.
```

### 17.5 Ownership boundary

Candidate, Context, Evidence and Review validity are Review's. Operation flow, the executor, the lock, the mutation
and Git finalization are START's. Git safety semantics are `rules/git`'s. Review never takes ownership of Work
lifecycle.

---

## 18. F2 decision table

| Decision | Frozen rule | Primary live evidence | Amends / inherits | Downstream dependency |
| --- | --- | --- | --- | --- |
| **F2-D1** Work Review identity | `review_kind` `work-result-v1`; task kind/slot, projection semantics, adapter identity and `authorized_operation_stage` of §4.1; `target_identity` = Work ID; `operation_identity` = `"start:" + digest(request identity)`, mode excluded; distinct from F1's `review-v1-work-v1` and both bound in the Context (§4) | P2's `PlanningKind` registration and `operation_identity` shape; no string collides | inherits P1 R2 identity discipline and the P2 kind-registration pattern | every later section; F3 checks the authorized stage |
| **F2-D2** Candidate schema | the six-key record of §5.1; `candidate_hash` is the digest of the whole record; `declared_base` read from `base_commit`'s committed state through the canonical loader | P2 Candidate shape (M-5); `CandidateSnapshot.material` is unconstrained (M-1) | inherits P1 R1 §6 and R3 §4 reconstruction rules; **adds** the `activation` field F1 deferred | F3 compares K1's delta against the artifact content |
| **F2-D3** result-bearing Candidate | the owned change set only; per-entry path, status, old/new mode, old/new blob id, content digest; ordered by path bytes; computable before any commit; supported object kinds `100644` / `100755` / `120000` and their deletion (§6.4) | `hash_blob` writes nothing (M-8); `declare_own_content` digests (M-12); a gitlink is decidable from HEAD before the executor runs (M-9) | inherits R3 §4's exact-identity requirement for path, mode, deletion, content and symlink semantics; **forward-amends P1 R1 §6 / P1 R3 §4** by excluding a gitlink at a result path at this contract version, refused at START entry (§1.3, §6.4) | F3's K1 delta proof; gitlink support is a later contract version |
| **F2-D4** empty-artifact Candidate | `artifact_kind: "empty"`, empty `entries`, positive `emptiness_proof`; same base lineage and hashing; mutually exclusive with result-bearing by construction; no fake or synthesized commit | a result-less Work makes no commit (M-13) | inherits F1-D10 Option B and F1's R5 §8 clarification | F3's proof topology when no K1 exists; F1 Gate 2's `Consumption.artifact_kind` |
| **F2-D5** three projections | artifact content in the Candidate; transition = the two terminal events for this Work, by type and order, no event IDs; metadata = Review bookkeeping and never lifecycle truth or correctness authority (§8) | `projections.normative()` answers no for metadata (M-11); `state.py` has no Review dependency (M-14) | inherits the canonical three-projection boundary | F3 places the transition in a mutation stage |
| **F2-D6** reconstruction | snapshot mode only; material is the whole Candidate record; `candidate_material_digest` over the snapshot record; builder mode not used (§9) | builder mode demands a deterministic regenerator that executor bytes do not have (M-1) | inherits P1 R1 §6 / R3 §4 / R3 §5 | F4 recovery reads it |
| **F2-D7** Review Context | the record of §10.1; authority = registry + `skills/start` + `skills/review` + `skills/create`; `rules/*` bound through `registry.md`; `git_persistence` bound, checkout capability not (§10) | rules have no `workline-target` (M-7); P2 Context shape (M-6) | inherits the P2 Context pattern and amends nothing: no frozen text binds a Work Context's authority set, so §10.2 defines this kind's own set rather than narrowing P2's, which belongs to different kinds | §14 closure; §16 invalidation |
| **F2-D8** activation binding | `{record_digest, operation_contract, activation_base_head}` in both Candidate and Context; prefix digest never copied out; the activation-record digest and `work-terminal-activation-digest-v1` are different digests (§11) | F1-D7 defines the prefix digest; the activation record is a normal Review record | inherits F1-D4 and F1-D7 unchanged | §16 invalidation |
| **F2-D9** reviewer binding | bound at the gate in the TaskInput and the accepted descriptor, never in the START invocation; mismatch is the existing `review_reviewer_mismatch`, at launch and at settlement (§12.1, §12.2) | P2 binds the reviewer at acceptance and refuses with this code | inherits F1-D2/F1-D3 (which forbid binding it in the invocation) and the P2 gate pattern | F4 recovery comparisons |
| **F2-D10** request envelope | the record of §12.3; Candidate and Context carried whole; reviewer identity absent; no runtime identity anywhere (§12.3, §12.4) | P1 `TaskInput` fields suffice unchanged (M-2) | inherits P1 R3 §4 minimum binding | F4 reconstruction |
| **F2-D11** Evidence execution | Evidence is Workline's own named checks (§13.2), never the reviewer's report; runs in-operation under the lock, mutates nothing; isolated verification is out of P3 (§13.3, §13.4) | the gate already separates `evidence_digest` from the report and adjudication digests (M-3) | inherits P1 R11 and the P2 evidence-record shape | the repair-loop phase may add isolated verification |
| **F2-D12** dependency completeness | the declaration of §13.5 in R11's fifteen classes; completeness is **unknown** by construction, so Work Evidence is fresh-use only and never reused across Candidates | live `EvidenceDeclaration` / `completeness()` (M-10) | inherits P1 R11 §3–§10 | §14.4's consequence |
| **F2-D13** ReviewValidityClosure | specialize the live P1 closure, no second system; the surface and provenance contents of §14.2; bound by digest inside the Evidence record, so it reaches the gate and the Receipt without a new record kind | `closure.py` complete and unused (M-10) | inherits P1 R6; notes that live field naming, not R6 §2's sketch, is the shape | F4 |
| **F2-D14** HEAD advancement | L1 Git-write compatibility **and** L2 `may_reuse == reusable`; at this contract version completeness is unknown, so an intervening advance always requires a new Candidate (§14.4) | `_head_advanced_independently` is L1 only; `may_reuse` refuses on unknown (M-10) | inherits P1 R6 §9/§10 | F4 decides what happens after |
| **F2-D15** Receipt semantics | a Receipt authorizes an exact Candidate for `start:work-terminal` and nothing else; **no schema repair required** (§15) | `target_identity` and `authorized_operation_stage` are free text; no storage SHA (M-4) | inherits P1 R3 §7 and the canonical Receipt boundary | F1 Gate 2 and F3 consume it |
| **F2-D16** invalidation boundary | the material facts of §16.1; an invalidated authorization is never consumable; unknown or contradictory is invalidating, never a weaker fallback | live Supersession and Consumption indexes | inherits P1 R3 §8 and R4 §1/§7 | F4 owns the mechanics |
| **F2-D17** authority plan | RV-1…RV-12 to `skills/review`, ST-1…ST-5 to `skills/start`, GT-1 to `rules/git`, **no registry routing change** (§17) | no new Skill and no new operation owner is introduced | inherits the Review/START ownership boundary | each activates with its implementation |

---

## 19. Deferred F3 / F4 responsibilities

F2 names these and solves none.

### F3

```text
the exact K1 and K2 durable proof checkpoints and their contracts
K1 / K2 commit topology, including the topology when no K1 exists (empty-artifact Candidate)
the split publication implementation and the review-v1-split-v1 validator
no-push-before-proof validator internals
the review-v1 terminal stage shape and its recorded-completion proof
the terminal Consumption mutation-stage placement and ordering
the K2 metadata-only recursion cutoff's exact delta rule
the rule that checks the Candidate's content.artifact_kind against the Consumption's artifact_kind
where the AuthorizedTransitionProjection is placed in a mutation stage and proven against what is applied
```

### F4

```text
Class A / B / C mismatch behaviour in full
adopt_existing_local_commit
stale-generation mutation mechanics
the recovery action matrix
the full interruption matrix
what happens after an invalidation, a mismatch or an interruption
```

### Later phases

```text
isolated verification / a verifier execution model, and the dependency-class coverage that would
  let Work Evidence completeness become "complete" and the HEAD-advance fast path become reachable
gitlink support at a result path
project-local or global adaptive Policy
```

---

## 20. Critical invariants

Stop conditions. An implementation that violates any of them is not implementing this contract.

```text
 1. Review authorizes; it never progresses Work lifecycle.

 2. Candidate identity is exact and reconstructible; a digest alone is never reconstruction
    material.

 3. The Candidate is defined before K1 and therefore never requires K1 identity.

 4. A valid empty-artifact Candidate exists without any physical K1.

 5. No fake, placeholder, empty-string, all-zero or synthetic commit identity is permitted
    anywhere.

 6. Candidate, Context and Evidence remain clone-safe wherever authorization depends on them.

 7. Runtime-only Review material is never sole canonical truth, and never authorization.

 8. Reviewer identity and version are bound by the Review gate, never by START's durable
    invocation identity.

 9. Activation history identity is bound without ever confusing the Event-prefix digest
    (work-terminal-activation-digest-v1) with the activation record's own canonical digest.

10. A ReviewValidityClosure is complete or automatic reuse fails closed. Unknown is never proven,
    and absence of discovered change is never proof of invariance.

11. OperationMetadataProjection is never lifecycle truth and never a correctness authority.

12. state.py remains independent of Review records, and the live pin proving it must keep holding.

13. F2 does not define K1/K2 publication topology.

14. F2 does not define F4 recovery or adoption actions.

15. Legacy START behaviour remains exactly unchanged unless review-v1 is explicitly selected.

16. Unknown, partial or contradictory Review contract material never silently degrades to legacy
    or to a weaker Review contract.

17. An ordinary, correct Work outcome is always expressible as a Candidate. Where an outcome is
    outside the expressible domain and the condition is knowable before the executor runs, the
    refusal happens at START entry.
```

---

## 21. Implementation readiness

```text
Contract status              FROZEN
Architecture blocker         NONE
HUMAN decision               NONE
Implementation authorized    NO
P3 implementation            NOT STARTED

F1 ordered prerequisites, unchanged and still binding:
  Gate 1  Event metadata carrier                                    NOT AUTHORIZED
  Gate 2  Consumption v1 artifact_kind repair, test-pinned          NOT AUTHORIZED
  Gate 3  activation producer and actual activation                 NOT AUTHORIZED

Freezing F2 authorizes no Gate. The activation producer still fails closed until Gates 1 and 2
are both satisfied.

Not implemented by this contract:
  any Work Candidate, Context, Evidence, closure or adapter code
  any change to src/, tests/, registry.md, canonical Skills, or any P1, P2 or P3 F1 document
```
