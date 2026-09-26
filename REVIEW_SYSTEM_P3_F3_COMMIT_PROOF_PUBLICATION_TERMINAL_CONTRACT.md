# Review System P3 — F3 Commit Proof / Publication / Terminal Topology Contract Freeze

Status: **CONTRACT FROZEN / REPAIRED AFTER INDEPENDENT REVIEW** / ARCHITECTURE BLOCKER: NONE /
HUMAN DECISION: NONE / **FORWARD AMENDMENTS TO LANDED F2: THREE (§1.5)** /
**IMPLEMENTATION NOT AUTHORIZED** / **P3 IMPLEMENTATION NOT STARTED**

F3 freezes the physical Git topology of a review-v1 Work completion: how the local commits are made, what
each commit's exact proof establishes, where that proof durably lives, which mutation stages may publish,
how publication composes with the P2 publication barrier, what the terminal stage is, and when START may
return `completed`.

It inherits F1 (START boundary and activation) and F2 (Work Candidate, Review validity, Evidence) without
reopening either, and it defers Class A/B/C mismatch behaviour, adoption, stale-generation mechanics and the
recovery matrix to F4.

---

## 1. Status, baseline, authority and precedence

### 1.1 Baseline

```text
Repository            easymodeeasy-source/workline-core
Authoritative branch  main
Live main at freeze   fa6b28b5f9c923d2c87a8a048ae7e10a76e451a0
That SHA is           the landed P3 F2 exact candidate
P3 F2                 LANDED
```

The landed chain read back from the remote and verified intact:

```text
fa6b28b  docs(review): remove stale blob-only F2 references
4db967c  docs(review): make P3 F2 Candidate reconstruction clone-safe
6a5c4ea  docs(review): repair P3 F2 contract after independent review
0055b03  docs(review): freeze P3 F2 Work Candidate contract
098600b  docs(review): clarify P3 F1 post-activation legacy classification
57490ba  docs(review): freeze P3 F1 START activation contract
```

Every live fact in §3 was measured at `fa6b28b`.

### 1.2 Authority

This document is a **frozen implementation contract**. It is not runtime authority. Runtime authority
remains, in order:

```text
1. registry.md
2. registry-routed canonical Skills
3. live implementation and tests
```

Nothing here changes any of them. The statements that must reach canonical authority when F3's
implementation lands are listed in §23 and are not written by this document.

### 1.3 Precedence

```text
P1 R1-R12          inherited; specialized, never weakened
P2 integration     inherited; the publication barrier is preserved exactly (§12)
P3 F1              inherited without change (F1-D1 ... F1-D11)
P3 F2              inherited EXCEPT the three explicit forward amendments of §1.5
                   (F2-D1 ... F2-D17 otherwise unchanged)
F3                 this document: physical topology, proof, publication, terminal stage
F4                 deferred (§25)
```

Where F3 appears to say something an earlier freeze also says, F3 is a **specialization**: it narrows,
never widens. Every apparent collision was audited item by item in §22.

```text
F3 semantic forward amendments: YES - three, all to landed F2, all stated in §1.5.
```

They are declared there in full, with the exact superseded sentences and the narrow replacement.
**No historical file is edited**: F2 keeps its bytes, and the amendment lives here, which is the
same discipline F1 used for its amendments to P1 R4 and R5.

### 1.4 F1 and F2 decisions F3 preserves without change

Everything in this list is inherited exactly. What F3 does **not** inherit unchanged is the three
statements named in §1.5, and nothing else.

```text
review-v1 START is explicit per-invocation opt-in; the default is legacy        F1-D1
the durable invocation carries both markers together, before any Git stage      F1-D2
  review_contract      = "review-v1-work-v1"
  publication_contract = "review-v1-split-v1"
markers are compatibility metadata, never slot identity                         F1-D2
the contract is never inferred from stage shape, files, content or branch       F1-D2, R5 §12.3.2
activation is Project capability, gated Gate 1 -> Gate 2 -> Gate 3              F1-D4 ... F1-D6
a result-less Work is valid; an empty artifact never invents a K1               F1-D10
Consumption artifact_kind in ("result_commit", "empty"), present-as-null        F1 §11.3
the Work Review identities and operation identity                               F2-D1
the Candidate is frozen BEFORE K1 and never contains K1 or K2                   F2-D2, F2 §20.3
every Git object kind is supported, including gitlink 160000                    F2-D3
the empty-artifact Candidate, with positive emptiness proof                     F2-D4
the three projections and their semantic roles                                  F2-D5
clone-safe reconstruction from declared_base + snapshot material                F2-D6
git_persistence identity "review-v1-work-local-v1" bound in the Context         F2-D7
isolated verification is a P3 responsibility                                    F2-D11
Evidence completeness is "unknown": fresh use allowed, all reuse refused        F2-D12
the ReviewValidityClosure and the HEAD-advance predicate                        F2-D13, F2-D14
the Receipt authorizes and never completes                                      F2-D15
the invalidation boundary                                                       F2-D16
```

---

### 1.5 Forward amendments to landed F2

F3 supersedes three statements of the landed F2 contract. Each is named exactly, with the sentence
superseded, the replacement, and why the two cannot both stand. **The F2 file is not edited.** This is the
mechanism F1 §11.3 already used for P1 R4 §2 and R5 §8: the amendment is declared in the new contract, and
the historical freeze keeps its bytes.

An amendment is declared here — rather than called a specialization — whenever F3's rule would make a
sentence of F2 **false as written**. A specialization narrows what an under-determined sentence permits; an
amendment replaces a sentence that says something definite and different. The first draft of this contract
classified A-1 and A-2 as specializations. That was wrong, and the correction is recorded rather than
quietly applied: F2 §5.3 does not merely under-determine K1's parent, it *names* it, and F2 §16.1's row
states a consequence *without qualification*. Calling either a specialization would have been exactly the
"inherits" understatement the F1 repair was made to eliminate.

---

#### A-1 — F2 §5.3: what `declared_base.base_commit` is, and that it is K1's parent

```text
F2 §5.3 says

    "base_commit is HEAD at the moment the completion is decided, which is the same commit F3
     will later require as K1's parent for a result-bearing Work."

F3 supersedes BOTH clauses:

  the timing clause    base_commit is the exact committed base HEAD holds after S-c0 (§4.3) and
                       immediately before the Candidate is frozen — not HEAD at the instant the
                       executor returned. S-c0 commits this Work's entry lifecycle events, so the
                       committed state the Candidate declares is one in which the Work is already
                       started and holds its target.

  the parentage clause parent(K1) is NOT required to be base_commit. It is required to be reached
                       from base_commit by this Run's own canonical Review-generation commits
                       alone, under the exact range proof of §8.2 L-1 ... L-5.
```

**Why both cannot stand.** P1 R3 §10, enforced live by `gate.require_persisted`, requires an accepted
task's canonical records to be committed before the external launch boundary. The Review gate therefore
commits generation 1 (accept), generation 2 (settle) and generation 3 (seal) in its own mutations, each of
which advances HEAD on the same branch, before K1 can exist. `parent(K1) == base_commit` is therefore
satisfiable only by committing K1 on an older base, which forks the branch and is prohibited throughout P1
and `rules/git`. F2's sentence describes a topology that cannot be built.

**Why this is an amendment and not a reinterpretation.** F2 §5.3 does not leave K1's parent open for F3 to
fill in; it states what F3 will require. F3 requires something else. The honest form of that is a named
supersession, not a reading.

---

#### A-2 — F2 §14.4 and §16.1: that every HEAD advance requires a new Candidate

```text
F2 §16.1 lists, among the material facts that invalidate a Work Review:

    "HEAD advances    §14.4, which at this contract version always requires a new Candidate"

and F2 §14.4 states the consequence unqualified:

    "An intervening HEAD advance therefore resolves as: closure completeness unknown -> prior
     Review is not reused -> freeze a NEW Candidate against the new HEAD -> perform fresh
     verification and review as required."

F3 supersedes the UNQUALIFIED scope of that consequence, and nothing else about it.
```

The narrow replacement, frozen:

```text
1. declared_base.base_commit is the exact post-S-c0, pre-Candidate committed base, for as long as
   S-c0 remains the selected topology (§4.3, A-1).

2. This Run's own canonical Review-generation commits — the commits that write this exact Review's
   own records as part of producing it — MAY occur after the Candidate is frozen and before K1
   and K2.

3. They are NOT generic reusable-Review HEAD advancement. They are internal to the production of
   the Review being authorized, not a later state a finished Review is being reused against.

4. They are accepted ONLY under the exact own-Review range proof of §8.2 L-2, every condition
   required together:
       the exact Run           the commits write this Run's records and no other's
       exact derived paths     the path set is derived from this Run's validated chain,
                               never hardcoded and never widened
       status A                every delta entry is an addition
       mode 100644             every delta entry is a regular file
       one parent              no merge anywhere in the range
       complete delta          the whole delta is enumerated, never a path allowlist
       no foreign commit       every commit in the range satisfies all of the above

5. EVERY other intervening advance — a person's commit, another tool's, another operation's,
   another Run's, or any commit failing any condition of item 4 — remains governed by F2 §14.4 in
   full: the prior Review is not reused, a NEW Candidate is frozen against the new HEAD, and fresh
   verification and review are performed.

6. The positive general HEAD-reuse branch remains UNREACHABLE while Work Evidence completeness is
   unknown (F2 §13.6, §14.4). Nothing here makes may_reuse answer "reusable", nothing here
   establishes completeness, and nothing here deletes the fast-path predicate.
```

**Why both cannot stand.** Read literally and applied to the Review's own generation commits, F2 §16.1
invalidates the Candidate that generation 1 has just accepted — so generation 2 could never be reached and
no review-v1 Work Review could ever seal. The unqualified consequence is not implementable.

**Why this is an amendment and not a reinterpretation.** §14.4's own wording is about reuse of a *prior*
Review, which suggests the narrower reading, and the first draft of this contract relied on that
suggestion. But §16.1's row carries no such qualification: it lists "HEAD advances" flatly as invalidating.
A rule that admits a class of advances which a landed invalidation row lists flatly is a change to that
row, whatever §14.4's prose suggests. Declaring it is the only way a reader of F2 alone can discover it.

---

#### A-3 — F2 §7.1, §7.2 and §7.3: the result-bearing / no-K1 boundary

```text
F2 §7.1 says

    "Exactly when the owned change set is empty - result_paths and deleted_paths are both empty,
     so START makes no result commit at all (M-13)."

F2 §7.2 freezes that Candidate's content with

    entries: []
    emptiness_proof.declared_result_paths:  []
    emptiness_proof.declared_deleted_paths: []

and its reconstruction material with

    material.payloads: []

F2 §7.3 says

    "An empty-artifact Candidate is refused if any declared path exists, which makes the two
     artifact kinds mutually exclusive by construction rather than by convention."

F3 supersedes the DISCRIMINATOR in all three: the boundary moves from
"is the declared path set empty?" to "is the complete owned tree delta empty?".

F3 ALSO supersedes the `payloads: []` consequence of F2 §7.2, and ONLY for the all-inert case.
The no-declared-path case keeps `entries: []` and `payloads: []` exactly as F2 froze them.
```

**Why the payload consequence has to move with the discriminator.** F2 §9.4.1 freezes a *uniform* coverage
rule that is deliberately indifferent to whether an entry changed anything:

```text
F2 §9.4.1, Uniform coverage rule

    "An entry whose old and new Git identity are equal still carries its payload when its
     new_kind is file or symlink. Reconstruction never depends on noticing that the bytes happen
     to match the base and fetching them from there instead."
```

F2 §7.2's `payloads: []` is not a competing rule — it is simply what the uniform rule *yields* when there
are no entries at all. Once A-3 admits an "empty" Candidate that **has** entries, the two texts would give
opposite answers for those entries, and taking `payloads: []` literally would be exactly the
match-the-base shortcut §9.4.1 exists to forbid. So the uniform rule governs, and §7.2's empty payload list
is superseded for that case alone.

The narrow replacement is frozen in §6.7, and the reason it is forced is in §6.6. Everything else about
F2 §7 stands unchanged: the positive emptiness proof, the prohibition on a fake or synthesized K1, the rule
that a reader never infers the kind from the emptiness of `entries`, and the independence of the
Candidate's and the Consumption's `artifact_kind`.

**Why both cannot stand.** F2 §6.3 keeps an inert entry — one whose `old_kind`/`old_mode`/`old_oid` equal
its `new_*` — in the Candidate, "because what the executor declared is part of what is reviewed". So a Work
whose executor declares a result path it did not actually change has a non-empty `result_paths` and a
Candidate every one of whose entries is inert. Under F2 §7.1 that is not the empty kind, so it is
`result_commit`, so F3 would require a K1 — but the complete owned tree delta is empty, and the frozen
primitive `git commit --only ... -- <paths>` creates no commit from an empty delta. Live START does not
even record the stage (`_commit` filters by `changed_against_head` and returns when nothing is left).
The Candidate would demand a commit that cannot exist.

**Why the alternatives were rejected.**

```text
keep artifact_kind = result_commit and allow a result-bearing Candidate with no K1
    rejected: F1 §11.3 freezes authorized_result_commit_sha as a full commit id IFF
    artifact_kind == "result_commit". This would break a landed F1 rule instead of an F2 one, and
    it would create the third, ambiguous category — "result_commit, but no commit" — that must
    not exist.

synthesize the commit with --allow-empty
    rejected: F1 §11.2 rejected exactly this as Option A. Nothing in the system creates an empty
    commit, and manufacturing Git history to satisfy a schema field is what that decision
    forbade.

refuse the outcome
    rejected: it is an ordinary correct outcome discovered only after the executor returned, which
    is the trap F1-D10 and F2 §2.3 both reject.
```

**Why this is an amendment and not a reinterpretation.** F2 §7.1 says "Exactly when", and §7.3 says an
empty-artifact Candidate "is refused if any declared path exists". Those are definite, and they are the
opposite of what §6.7 freezes. There is no reading of them that admits an all-inert Candidate.

---

#### What these amendments do NOT change

```text
no P1, P2 or P3 F1 statement is amended by F3
no historical file is edited
the Candidate is still frozen before any K1 (F2 §20.3)
no fake, placeholder, synthesized or all-zero commit identity exists anywhere (F2 §20.5)
the Candidate still preserves exactly what the executor declared (F2 §6.3)
the Candidate's and the Consumption's artifact_kind remain independent statements, both read and
  compared, neither derived from the other (F2 §7.6, §14 here)
Evidence completeness remains unknown, and reuse remains refused (F2 §13.6)
the positive HEAD-reuse branch remains unreachable (F2 §14.4)
```

---

## 2. F3 scope and non-scope

### 2.1 In scope — frozen here

```text
F3-D1   the review-v1 Work commit-only primitive and its persistence-semantics identity
F3-D2   K1 lineage: the exact parent rule and what may lie between the base and that parent
F3-D3   the complete result-bearing physical topology and its durable-intent boundaries
F3-D4   the complete no-K1 physical topology: no declared path, and all-inert
F3-D5   what C-2(K1) proves, item by item
F3-D6   the C-2 durability model and why it is Option A
F3-D7   the review-v1-split-v1 validator for the Work path
F3-D8   composition with the existing P2 cross-operation publication barrier
F3-D9   terminal identifier reservation and the terminal stage's physical shape
F3-D10  the Candidate / Consumption artifact_kind consistency proof
F3-D11  normal terminal K2 lineage and what C-2(K2) proves
F3-D12  the physical allocation of the three projections
F3-D13  the recursion cutoff that keeps an ordinary terminal K2 out of Review
F3-D14  the recorded-completion proof: when START may return "completed"
F3-D15  the no-remote topology
```

### 2.2 Out of scope — deferred, named in §25

```text
Class A / B / C mismatch behaviour, adopt_existing_local_commit, stale-generation
mechanics, the repair action matrix, the full interruption matrix, the Repair Loop,
dependency-class completeness expansion, isolated Integration, enabling the positive
HEAD-reuse branch
```

### 2.3 What F3 does not redesign

F3 does not move K1 earlier, does not make Review the operation owner, does not give Review records
lifecycle authority, and does not change the legacy path. Legacy START behaves at every point exactly as it
does at this baseline.

F3 does not redesign the Candidate **except for the narrow A-3 forward amendment** (§1.5), which moves the
result-bearing / no-K1 discriminator and, for the all-inert case only, the content and payload consequences
that followed from it. The Candidate's schema, its entry shape, its object-kind support, its base lineage,
its identity rule and its reconstruction criterion are all inherited unchanged.

---

## 3. Measured live architecture

Measured at `fa6b28b`. Each item is a fact this contract is built on, not an inference.

```text
M-1   gitops.finalize_effects builds ONE stage holding [git_commit] or [git_commit, git_push]
      (gitops.py:159), and Mutation.apply applies a stage's effects in one uninterrupted
      ordered pass. There is no interposition point between a commit and its push.

M-2   The live START completion topology is:
        <W>:results:<n>    [git_commit, git_push]   the result commit, owned paths only
        <W>:lifecycle:<n>  [append_event x2]        work_target_removed, work_completed
        <W>:finalize:<n>   [git_commit, git_push]   the events commit
        postcheck -> ProjectView.load(store).work_state(...).state == COMPLETED
      (start.py:875 _complete, :909 _finalize_completion, :446 _commit, :455 _lifecycle)

M-3   A review-v1 SPLIT publication already exists and works, for the P2 planning path:
        gitops.review_commit_effect     a git_commit carrying payload["mode"], optionally base_exact
        gitops.review_publication_effect a git_push carrying payload["commit"]
        mutation._planning_publication  the push-only-stage validator (mutation.py:1506)
      The split is therefore an implemented architecture, not a new one.

M-4   mutation._publication_contract (mutation.py:1482) selects the rule from the durable
      invocation alone. With review_contract "review-v1-work-v1" and publication_contract
      "review-v1-split-v1" on operation "start", it returns "invalid" today, because its
      "planning" branch additionally requires operation in ("roadmap-create", "phase-entry").
      A review-v1 Work mutation therefore FAILS CLOSED at publication, exactly as F1-D2 said
      it would until F3 lands. That is the designed state, not a defect.

M-5   Effect.git_commit payload "mode" is hard-restricted to exactly one value:
      _validate_planning_commit raises unless payload["mode"] == PLANNING_COMMIT_MODE
      ("review-v1-planning-local-v1") (mutation.py:1094-1100), and apply_effect dispatches on
      the same single value (mutation.py:2484). A second local-persistence identity cannot be
      recorded at this baseline. IMPLEMENTATION PREREQUISITE, §21.

M-6   The contained commit primitive is gitcmd.contained_add / contained_commit (gitcmd.py:810,
      :817): core.hooksPath pointed at a Workline-owned empty directory, core.fsmonitor=false,
      commit.gpgSign=false, gc.auto=0, maintenance.auto=false, and
      `git commit --only --no-verify --no-gpg-sign -m <message> -- <paths>`.
      mutation._no_hooks_directory proves that directory is an empty plain directory or STOPs
      with review_hooks_path_invalid.

M-7   base_exact is live: _make_planning_commit re-reads HEAD immediately before `git add` and
      again immediately before `git commit`, and refuses with
      ReconcileRequired(reason="review_registration_base_moved") if HEAD is no longer the
      recorded parent (mutation.py:1800). mutation.py:2326 excludes a base_exact payload from
      the generic _head_advanced_independently allowance.

M-8   Exact-commit publication is live and total: gitcmd._exact_refspec rejects anything that is
      not `<full commit ID>:refs/heads/<name>`, rejects "*" and never forces (gitcmd.py:267);
      gitcmd.push and push_dry_run both route through it.

M-9   Complete tree-entry delta plumbing EXISTS at this baseline:
        gitcmd.commit_delta   `git diff-tree -r -z --no-renames --no-abbrev --raw`
                              -> old_mode, new_mode, old_blob, new_blob, status, path
        gitcmd.tree_entries   `git ls-tree -z --full-tree -r` -> mode, type, oid, path
        gitcmd.hash_blob      `git hash-object --no-filters -t blob --stdin`, writes nothing
        gitcmd.zero_object_id, full_commit_id  width-agnostic, SHA-1 and SHA-256
      R7 §10.1's implementation binding ("no live helper supplies mode or object identity") is
      a stale statement of fact at baseline e32a741; it no longer describes live code. §22 row 6.

M-10  C-1 is live: the Mutation Controller records the made commit's full object ID beside the
      effect payload as "commit_id" (_MADE_COMMIT, mutation.py:131) when it can prove the new
      HEAD is a one-parent child of the pre-commit HEAD. Message identity, content identity and
      branch-tip fallback are all refused (registry.md, Commit / push).

M-11  C-2 durability is live, and it is Option A: _c2_kp and _c2_km (roadmap_review.py:2797,
      :2905) RE-EXECUTE the whole proof from the exact committed objects, the CommittedReviewStore
      at the exact commit and the recorded effect's commit_id. The runtime note
      "publication_proof" carries only the contract and which commits the proof was for; the
      validator requires the pushed commit to be the one the note names and then re-derives every
      Git fact itself. No canonical commit-proof record exists anywhere.

M-12  Review records reach committed state through their OWN generation mutations, before the
      operation's own Git stages: _start_generation opens a mutation with operation
      "review-generation", records the create_file effects, and _finish_generation commits them
      with the review-v1 commit primitive and then proves them persisted
      (roadmap_review.py:1444, :1503; gate.require_persisted enforces R3 §10 before any external
      launch). A generation mutation publishes NOTHING (_publication_contract -> "generation").
      Consequence, and it is decisive for §8: by the time K1 is committed, HEAD has necessarily
      advanced past declared_base.base_commit by this Run's own generation commits.

M-13  The canonical Review namespace is CLOSED: REVIEW_SUBDIRS is exactly (gates, receipts,
      consumptions, supersessions, candidate-snapshots, task-inputs, activation), and
      paths.require_review_record_path refuses any other location. There is no commit-proof
      record directory and no room for one without a namespace expansion.

M-14  The P2 publication barrier applies to EVERY Workline push, legacy ones included
      (publication.require_barrier_clear, called from gitops.finalize before a push stage is
      recorded and from MutationController.apply_effect immediately before the network write).
      Its fast path is PATH-based, not schema-based:
        git rev-list --full-history -n 1 <C> -- .workline/review/candidate-snapshots/
      A Work Candidate snapshot lives in that very directory. §12 states the consequence.

M-15  publication.registered_runs SKIPS a snapshot whose material is not a planning Candidate
      (`planning.is_planning_candidate` tests schema == "review-planning-candidate"; F2's Work
      Candidate schema is "review-work-candidate"). A Work Candidate snapshot therefore never
      begins the barrier — but it does take every later push off the fast path.

M-16  Consumption version 1 (records.py:521-648) has no artifact_kind field and binds
      terminal_event_id / terminal_event_type / authorized_result_commit_sha as an all-or-none
      triple. F1 Gate 2 owns that repair; F3 writes against the repaired field set.

M-17  start._recorded_completion (start.py:1394) requires the completion's lifecycle stage to hold
      exactly `["append_event"] * 2` and nothing else. A review-v1 terminal stage holds three
      effects. IMPLEMENTATION PREREQUISITE, §21.

M-18  state.py contains no reference to Review of any kind. The pin F2 §20.12 requires still
      holds exactly.

M-19  records.WorkTerminalActivation is a schema and a reader with no producer anywhere in src/.
      Its activation_base_head is validated as `[0-9a-f]{40}` — SHA-1 width only — while
      Consumption.authorized_result_commit_sha accepts 40 or 64. That asymmetry belongs to F1
      Gate 3 (the activation producer), not to F3; it is recorded here as an observation so it is
      not lost, and F3's own identities are width-agnostic throughout.
```

---

## 4. Definitions and frozen identities

### 4.1 The commits

```text
K1   the result commit. Exists only when artifact_kind is "result_commit" — that is, only when
     at least one Candidate entry is CHANGING (§6.7). Carries the ReviewedArtifactProjection and
     nothing else.

K2   the terminal commit. Exists for EVERY completed review-v1 Work, result-bearing or empty.
     Carries the AuthorizedTransitionProjection and the terminal OperationMetadataProjection,
     and nothing else.
```

`K2` in this document always means the **ordinary Work terminal commit**. The special metadata-only commit
of P1 R7 §6 is never called K2 here; it is written `K2-A` and it is F4's (§25).

### 4.2 The checkpoints

Inherited verbatim from P1 R5 §1.1 and specialized to the Work path:

```text
C-1(K)   the commit is recorded applied and the exact identity of K is durable
C-2(K)   the exact proof for K is complete and durable
C-3(K)   the push of exactly K is authorized and recorded
```

```text
C-2 MUST be durably complete before C-3 is recorded or applied.
A push effect MAY exist only for a K whose C-2 is already satisfied.
C-2 is NEVER reconstructed from the presence of C-3, from a remote, from a successful push
  or from a branch tip.
A crash at any point resumes at the earliest unsatisfied checkpoint.
```

### 4.3 The stages

```text
S-c0   <W>:entry:<n>                    commit-only, the entry events   only when they are
                                                                        not already committed
S-c1   <W>:results:<n>                  commit-only, makes K1        result_commit only
S-p1   <W>:results-publication:<n>      push-only, publishes K1      result_commit, with a remote
S-t    <W>:lifecycle:<n>                the terminal stage           always
S-c2   <W>:finalize:<n>                 commit-only, makes K2        always
S-p2   <W>:finalize-publication:<n>     push-only, publishes K2      with a remote
```

The commit stages keep the live stage-name prefixes (`<W>:results`, `<W>:finalize`) so that START's existing
resume reader continues to recognize a recorded completion by shape (`_completion_to_finish` looks for a
later stage beginning `<W>:finalize:`). Only the pushes move out into stages of their own.

```text
Every stage frozen here holds exactly the effects named for it, and no others.
A commit stage holds exactly one git_commit. A push stage holds exactly one git_push.
A review-v1 Work mutation MUST NOT record a stage holding a git_commit and a git_push together.
```

#### S-c0 — why an entry-events commit exists, and why it is F3's

Measured: START appends this Work's entry lifecycle events (`work_started` / `work_resumed`,
`work_target_added`) before the executor runs, and the live flow leaves them uncommitted until the
**finalization** commit sweeps them in with `include_canonical=True` (start.py:446, :455, :911).

Left that way, K2's delta would carry those entry events as well as the two authorized terminal events —
and K2 would then hold lifecycle events that are **not** the AuthorizedTransitionProjection, which is exactly
the projection ambiguity F3 exists to remove (§17). F3 therefore commits them first:

```text
S-c0 is recorded immediately after the executor returns Completed and BEFORE the Candidate is
frozen, and it commits the event log alone.

It is recorded only when there is something to commit. When the event log already matches HEAD —
a resumed START, a Work already in_progress with its target, or a cycle whose earlier derivation
commit already swept it — no stage is recorded and nothing is committed, exactly as the live
commit helper already behaves.

Its commit is never published on its own. It reaches the destination only as the history of K1 or
K2, which is what `rules/git` (Push destination) already says a later stage's push publishes.

Consequence, deliberate: declared_base.base_commit is HEAD after S-c0, so the committed state the
Candidate declares is one in which this Work is already started and holds its target. That is the
state the reviewer is shown, and it is the state the terminal transition is measured against.
```

F2 §5.3 describes `base_commit` as "HEAD when the completion was decided". F3 owns when each
physical thing happens, and fixes that moment exactly:

```text
declared_base.base_commit is read immediately after S-c0 and immediately before the Candidate is
frozen. It is therefore the first commit at which the completion's artifact is fixed, and no
commit of this operation lies between it and the Review.
```

This is a specialization of an under-determined timing description, not a change to a normative
rule: every normative clause of F2 §5.3 still holds exactly — `base_commit` is a full commit id of
HEAD, every `declared_base` field is read from its committed state through the canonical loader,
and it is the lineage the result is measured against. The entries' `old_*` are unaffected, because
the event log is never a result path. §22 row 19.

#### Every other Git stage of a review-v1 Work mutation is commit-only

A Work cycle can record further Git stages before the completion — a derived registration, a move, a
human-NG move — each of which is a combined `git_commit + git_push` stage in the live flow
(start.py:572-579).

```text
In a review-v1 Work mutation, EVERY Git stage is commit-only, except the two push-only
publication stages S-p1 and S-p2. There are no other pushes.

This is forced, not chosen: a combined stage pushes in the same uninterrupted apply pass as its
commit, which is a push before proof (R5 §12.2), and there is no C-2 for a derivation commit to
have passed. Refusing the outcome instead would be a post-executor refusal of an ordinary correct
outcome, which F2 §2.3 rejects.

Nothing is lost by it. Those commits reach the destination as the history of the next authorized
push of this same mutation, which is the live, frozen meaning of an exact-commit push.
```

### 4.4 Frozen identity strings

```text
git persistence        "review-v1-work-local-v1"      F2-D7, used at commit time by F3 (§7)
proof contract         "review-v1-work-proof-v1"      F3 (§9, §17)
lineage contract       "review-v1-work-lineage-v1"    F3 (§8)
terminal stage         "review-v1-work-terminal-v1"   F3 (§13)
publication validator  "review-v1-work-publication-v1" F3 (§11)
publication marker     "review-v1-split-v1"           F1-D2, UNCHANGED
review contract marker "review-v1-work-v1"            F1-D1 / F1-D2, UNCHANGED
authorized stage       "start:work-terminal"          F2-D1, UNCHANGED
```

The publication **marker** `review-v1-split-v1` is F1-frozen and is not renamed. The publication
**validator** is a separate identity because the planning split and the Work split are two different
shapes under one marker family, and each must be validated by its own rule (R5 §12: "Neither one's rule is
evidence about the other").

### 4.5 The durable proof notes

Two mutation notes, each written once, each naming exactly one commit:

```text
"review_work_result_proof" = {
    contract:        "review-v1-work-proof-v1"
    candidate_hash:  <the authorized Candidate's hash>
    receipt_id:      <the Receipt being consumed>
    result_commit:   <K1, a full object id>
    base_commit:     <parent(K1)>
    branch:          <the full ref name>
}

"review_work_terminal_proof" = {
    contract:        "review-v1-work-proof-v1"
    candidate_hash:  <the authorized Candidate's hash>
    receipt_id:      <the Receipt being consumed>
    artifact_kind:   "result_commit" | "empty"
    result_commit:   <K1, or null for an empty-artifact Candidate>
    terminal_commit: <K2, a full object id>
    terminal_event_ids: [<work_target_removed id>, <work_completed id>]
    consumption_id:  <the Consumption's id>
    base_commit:     <parent(K2)>
    branch:          <the full ref name>
}
```

```text
A note is a RECOVERY POINTER, never the proof and never authority (§10.4).
It says which commit a completed proof was for. It never says that the proof passed, and no
reader ever treats its presence as a proof result.
```

---

## 5. Result-bearing physical topology (F3-D3)

### 5.1 The frozen sequence

Read top to bottom. `durable` marks a point at which intent must be durable **before** the physical effect
below it is attempted.

```text
 1  START entry, review-v1 selected                       F1-D1
 2  destination pin verified, before the lock             registry.md, Push destination
 2a publication capability check, with a remote           §12.4
 2b transform-configuration entry refusal                 §7.4
 3  Project execution lock; activation verified           F1-D4, F1 §6.4
 4  durable  mutation opened with both markers            F1-D2
 5  the Work cycle runs; the executor returns Completed
 6  declare_own_content over result_paths U deleted_paths start.py:884, unchanged
 7  completion_precheck passes                            skills/start, unchanged
 8  dirty separability over the owned set                 gitops.ensure_separable, unchanged
 9  Git persistence preflight over the owned set (early)  §7.3
 9a durable  S-c0 recorded and applied, if anything is uncommitted in the event log   §4.3
10  the Work Candidate is frozen                          F2 §5, §6
11  the CandidateSnapshot material envelope is built      F2 §9.3
12  isolated verification runs against the exact Candidate F2 §13.4 V-1 ... V-5
13  durable  gate generation 1: accept, with the snapshot and the TaskInput  R3, M-12
             -> its own generation mutation commits them and proves them persisted
14  the reviewer is launched and returns                  F2 §12
15  durable  gate generation 2: settle                    -> committed by its own mutation
16  durable  gate generation 3: seal, issuing the Receipt -> committed by its own mutation
17  the lineage precondition is proven                    §8.2
17a the Consumption identifier is reserved, so S-c2's paths are known    §7.4.2, §13.2
17b Git persistence preflight, AGAIN after the Review, over the UNION of every path this
    operation will ever commit: the Candidate's entry paths, the event log and the
    Consumption path. This is the run W2 binds, not step 9's      §7.3, §7.4.2
18  durable  S-c1 recorded: the commit-only stage for K1  §7
19           S-c1 applied -> K1 made -> C-1(K1)           M-7, M-10
20  C-2(K1): items W1 ... W12                             §9
21  durable  the "review_work_result_proof" note          §4.5
22  the publication barrier is checked for K1             §12
23  durable  S-p1 recorded: the push-only stage for K1    §11
24           S-p1 applied: destination re-resolved, barrier re-checked, exact K1 pushed
25  durable  terminal identifiers reserved                §13.2
26  durable  S-t recorded: two events, then the Consumption  §13.3
27           S-t applied, in recorded order
28  Git persistence preflight over the terminal paths     §7.3
    (and the same preflight ran before S-c0 and before every pre-completion Work commit)
29  durable  S-c2 recorded: the commit-only stage for K2  §15.1
30           S-c2 applied -> K2 made -> C-1(K2)
31  C-2(K2): items T1 ... T12                             §16
32  durable  the "review_work_terminal_proof" note        §4.5
33  the publication barrier is checked for K2             §12
34  durable  S-p2 recorded: the push-only stage for K2    §11
35           S-p2 applied: exact K2 pushed
36  the recorded-completion proof                         §19
37  mutation.complete(); START returns "completed"
```

### 5.2 Frozen ordering rules

```text
R-1  No Git stage of this mutation is recorded before both durable markers exist (F1-D2).
R-2  The Candidate is frozen before any commit that carries the reviewed artifact. Step 10
     precedes step 18, always. The only commit of this operation before it is S-c0, which
     carries this Work's entry lifecycle events and no artifact at all, and which is what makes
     declared_base.base_commit the exact point the artifact is measured against (§4.3). Moving
     K1 earlier is prohibited (F2 §9.6, §20.3).
R-3  No push effect is recorded before the C-2 of the commit it publishes is complete, and
     C-2 is re-evaluated again before that push effect is applied (R5 §12.4).
R-4  No terminal event is recorded before C-2(K1) is complete. A review-v1 Work mutation that
     holds a Work terminal append_event effect recorded before its S-c1 stage is refused
     (§9, item W12; §11.4).
R-5  Terminal events are NEVER carried by K1. K1's physical delta is the Candidate's CHANGING
     entries exactly (§9, item W4), which cannot contain the event log. The Candidate's INERT
     entries are part of the reviewed artifact but are absent from that delta by construction,
     and are proven at K1 by exact tree containment instead (§9, item W5; §17.2).
R-6  Identifiers are reserved and content is durable before the stage that applies them
     (R4 §6, §13.2).
R-7  Each step marked `durable` completes its save before the step below it runs. An interruption
     between them resumes at the earliest unsatisfied checkpoint and re-derives, never re-decides.
```

### 5.3 Where an interruption resumes

F3 freezes the resume **point**; F4 owns what to do when the state found there does not match.

```text
before 9a                     nothing of the completion is committed; the flow continues
9a recorded, not applied      S-c0 replays; when the event log already matches HEAD it is a
                              no-op and the Candidate is frozen against the same base
after 9a, before 18           nothing physical happened since; the flow continues from the
                              Candidate, and a Review already sealed is used as it stands
18 recorded, 19 not applied   S-c1 is classified first; base_exact refuses a moved HEAD (M-7)
19 applied, 20 not reached    C-2(K1) runs; it is a re-execution, so a retry repeats it in full
21 noted, 23 not recorded     the barrier and S-p1 are attempted again
23 recorded, 24 not applied   C-2(K1) is re-evaluated before apply; a stale proof refuses
24 applied                    the exact-commit push classification decides (registry.md)
26 recorded, 27 not applied   the stage replays in recorded order, nothing is re-decided
29 recorded, 30 not applied   base_exact refuses a moved HEAD
31 onward                     as 20 onward, for K2
```

---

## 6. No-K1 physical topology (F3-D4)

This section covers **both** Candidates that carry no result commit. They are one topology and one
`artifact_kind`, not two, because the thing that decides them is the same fact — the complete owned tree
delta is empty — and because a third category would be exactly the ambiguity F2 §7.5 forbids.

```text
no declared path      the executor declared no result path and no deleted path (F2 §7.1's
                      original case)
all-inert             the executor declared paths, and every Candidate entry is inert: its
                      old_kind/old_mode/old_oid equal its new_* (§6.6)
```

### 6.1 The mandatory invariant

```text
NO K1.

No physical result commit. No synthetic empty commit. No placeholder commit. No all-zero,
empty-string or otherwise fabricated commit identity, anywhere, at any point, for any purpose.
```

This is F1 §11.2, F1 invariant 8 and F2 §7.6 and §20.4/§20.5, restated because F3 is where a commit would
have been created if anywhere. It holds for both cases above, and it is what forces the amendment A-3:
an all-inert Candidate cannot have a K1, because `git commit --only` makes no commit from an empty delta.

### 6.2 The frozen sequence

For the **no declared path** case, identical to §5.1 with steps 6, 8, 9, 18-24 **absent**, and nothing
substituted for them:

```text
 1 ...  5   as §5.1; the executor returns Completed with an empty owned set
 6          no declare_own_content: there is no owned path         (start.py:880, unchanged)
 7          completion_precheck passes
 8, 9       not applicable: there is no owned path to separate or to preflight
 9a         S-c0 exactly as in §5.1: the entry events are committed before the Candidate
10          the empty-artifact Candidate is frozen                  F2 §7.2
11          the material envelope is built: payloads = [] for the no-declared-path case
            (F2 §7.2), and one payload per inert file / symlink entry for the all-inert
            case under F2 §9.4's uniform coverage rule (§6.7, amendment A-3)
12 ... 16   isolated verification, accept, launch, settle, seal     as §5.1
17          the lineage precondition is proven, measured to K2      §8.5, §6.3
18 ... 24   ABSENT. No K1 stage, no K1 proof, no K1 publication.
25 ... 37   as §5.1, with artifact_kind "empty" throughout
```

For the **all-inert** case the sequence is §5.1's exactly — steps 6, 8 and 9 all run, because there are
declared paths to protect, to separate and to preflight — up to and including step 10, and then steps
**18-24 are absent** for the same reason and with the same consequences. The difference between the two
cases is entirely before the Candidate is frozen; from the Candidate onward they are one topology.

### 6.3 Terminal parentage when there is no K1

```text
parent(K2) is the commit HEAD holds when S-c2 is recorded, and it MUST satisfy the lineage
contract of §8 measured from declared_base.base_commit:

    parent(K2) == declared_base.base_commit
    OR
    parent(K2) is reached from declared_base.base_commit by own-Review commits only (§8.2)

and S-c2 is base-exact: HEAD is re-read immediately before the commit and must still be exactly
parent(K2), or the commit is not made (M-7).
```

The empty case is therefore not a special parentage rule. It is the **same** lineage rule the result-bearing
case applies to K1, applied one step later because there is no K1 in between. §8.5 explains why this is not
`parent(K2) == declared_base.base_commit` verbatim.

### 6.4 What the terminal commit carries

Exactly as in the result-bearing case (§17):

```text
K2 delta = the event log, with exactly the two authorized terminal events appended
         + the Consumption record, added
and nothing else.
```

The Consumption carries `artifact_kind = "empty"` and `authorized_result_commit_sha = null`, which is
F1 §11.3's exact frozen repair, and §14 proves that against the Candidate's `content.artifact_kind`.

### 6.5 Prohibited in the no-K1 topology

```text
creating an empty commit so that a K1 exists
recording a git_commit effect with an empty path list
treating the terminal commit K2 as the K1 of an empty Candidate
writing any commit id into authorized_result_commit_sha
omitting the artifact_kind key rather than writing it as "empty"
reporting "no commit" as "no Candidate", or as a refusal of review-v1
treating an all-inert Candidate as result-bearing, and so demanding a K1 that cannot exist
using --allow-empty, or any other flag or mechanism, to bring a commit into being for one
```

### 6.6 The all-inert Candidate — the fact that forces amendment A-3

Measured, and reachable without anything unusual happening:

```text
F2 §6.3 keeps an entry whose old_* equals its new_* in the Candidate, "because what the executor
declared is part of what is reviewed". Such an entry is INERT: it declares a result path whose
Git object identity the executor did not change.

F2 §7.1 makes the empty kind apply "Exactly when" result_paths and deleted_paths are both empty.

So a Work whose executor declares result paths and changes none of their object identities has:
    result_paths           non-empty
    every Candidate entry  inert
    the complete owned tree delta against base_commit   EMPTY
```

Under the unamended boundary that Candidate is `result_commit`, and §5.1 would require a K1. No K1 can
exist:

```text
the frozen primitive is `git commit --only --no-verify --no-gpg-sign -m <msg> -- <paths>`,
  which makes no commit when the complete delta is empty;
live START does not even record the stage: _commit computes
  `dirty = changed_against_head(root, owned)` and returns when nothing is left (start.py:446);
F1 §11.2 rejected manufacturing an empty commit as Option A, so --allow-empty is not available;
and a placeholder or all-zero identity is prohibited everywhere (F2 §20.5).
```

This is an **ordinary correct outcome** — a Work that touched a declared path and left its content as it
was, or that re-wrote a file with identical bytes — discovered only when the executor returns. Refusing it
is the trap F1-D10 and F2 §2.3 both reject. So the boundary moves.

### 6.7 The frozen representation of an all-inert Candidate

```text
DISCRIMINATOR, replacing F2 §7.1 (amendment A-3)

    artifact_kind = "result_commit"   IFF at least one Candidate entry is CHANGING
    artifact_kind = "empty"           IFF no Candidate entry is changing

    An entry is CHANGING when any of old_kind/old_mode/old_oid differs from the corresponding
    new_*. It is INERT when none does. "No declared entry at all" is the degenerate case of
    "no changing entry", which is why the two cases of §6 are one kind.

    The discriminator is the complete owned tree delta, which is exactly what decides whether a
    physical commit can exist. It is never the emptiness of `entries`, never the length of
    result_paths, and never inferred from the Consumption.
```

```text
CONTENT, replacing F2 §7.2 for the all-inert case

content = {
  artifact_kind: "empty"
  entries: [ <every declared entry, inert, in the exact shape of F2 §6.3, sorted by the path's
              UTF-8 bytes — nothing is dropped> ]
  emptiness_proof: {
      base_commit:                     <the same commit as declared_base.base_commit>
      declared_result_paths:           [ <exactly what the executor declared> ]
      declared_deleted_paths:          [ <exactly what the executor declared> ]
      owned_paths_differing_from_base: []
  }
}

`message` is absent: there is no result commit to carry one, and a message that no commit will
carry is not part of what was reviewed.
```

Frozen answers to each question the boundary raises:

```text
how an all-inert declared result is represented
    as an "empty" Candidate whose entries are the declared entries, every one inert.

whether inert declared entries remain represented
    YES, all of them, unchanged in shape. F2 §6.3's rule is preserved rather than weakened: this
    amendment is the only way an all-inert declaration can be both kept and terminalized.

artifact_kind
    "empty". There is no third value and no third category.

emptiness proof
    owned_paths_differing_from_base is [] — and it is now doing real work rather than being
    trivially empty. It is the positive statement that no declared path differs from the base,
    which is precisely the condition under which no commit can be made. It is proven by
    enumerating the declared set against base_commit's tree, never by absence of evidence, and it
    is cross-checked against the entries: an "empty" Candidate holding a CHANGING entry is
    malformed and fails closed.

Consumption artifact_kind
    "empty", independently determined and then compared (§14). Never derived from the Candidate.

authorized_result_commit_sha
    null, present as null, never omitted (F1 §11.3).

physical topology
    §6.2's all-inert variant: no S-c1, no C-2(K1), no S-p1. K2 is the only commit of the
    completion, and its parent follows §6.3.

C-2(K2) proof
    T1 ... T12 unchanged, with T12 taking its "empty" branch: no commit of this mutation carries
    a ReviewedArtifact delta, and authorized_result_commit_sha is null.

the no-K1 invariant
    unchanged and absolute (§6.1).
```

```text
MATERIAL, replacing F2 §7.2's `payloads: []` for the all-inert case (amendment A-3)

CandidateSnapshot.material follows F2 §9.4 in full, with no exception for inertness:

    inert file entry       EXACTLY ONE payload, same path, kind "file"
                           the exact result bytes, base64-rfc4648-v1        REQUIRED
    inert symlink entry    EXACTLY ONE payload, same path, kind "symlink"
                           the exact link-target bytes Git stores            REQUIRED
    inert gitlink entry    NO payload — the entry itself is the material
    deletion               cannot occur in an all-inert Candidate: a deletion is a CHANGING
                           entry by construction (old present, new absent)

    ordering               by the payload's path UTF-8 bytes (F2 §9.4.3)
    cross-checks           F2 §9.5 in full and unweakened, for every payload:
                             strict canonical Base64 decode
                             SHA-256(decoded) == the entry's content_sha256
                             Git blob identity(decoded) == the entry's new_oid
    digest                 candidate_material_digest covers the whole snapshot record, payload
                           strings included, exactly as for any other Candidate

The closed correspondence of F2 §9.4.1 applies unchanged: a missing payload for an inert file or
symlink entry, a duplicate, an extra payload with no entry, a path or kind mismatch, or a payload
present for a gitlink is `reconcile_required`.
```

```text
An all-inert file or symlink is NEVER reconstructed by noticing that its identity equals the
base's and reading the bytes from base_commit instead. F2 §9.4.1 rejected that shortcut
explicitly, and A-3 does not reintroduce it: the payload is carried, and it is cross-checked.
```

```text
Isolated verification of an all-inert Candidate (F2 §13.4, V-2)

The workspace is materialized from declared_base.base_commit plus CandidateSnapshot.material, in
the ordinary way. For an all-inert Candidate the resulting tree EQUALS the base on those paths —
that is what inert means — but the frozen payload material is still decoded, still cross-checked
against content_sha256 and new_oid, and still used to install the path.

It is NOT discarded as redundant, and the equality is NOT used as a reason to skip the
materialization. A payload that fails its cross-check fails the verification even though the
base holds identical bytes, because what is being verified is the frozen Candidate, not the base
(V-1, V-3).
```

```text
Why the declared entries are kept rather than emptied to match F2 §7.2 exactly:
dropping them would discard what the executor declared, which F2 §6.3 requires the Candidate to
preserve, and would make two materially different Works — one that declared nothing and one that
declared three paths it did not change — produce the identical Candidate and the identical
candidate_hash. The reviewer would be shown less than was actually claimed.
```

---

## 7. Work local persistence (F3-D1)

### 7.1 Frozen primitive

```text
git_persistence identity = "review-v1-work-local-v1"
```

Its behaviour is frozen as the contained commit primitive, identical in mechanism to the live planning
primitive (M-6) and carrying a **distinct identity**:

```text
staging     `git add` with core.hooksPath = a Workline-owned empty plain directory,
            core.fsmonitor=false, and nothing else
commit      `git commit --only --no-verify --no-gpg-sign -m <message> -- <paths>`
            with core.hooksPath = that same directory
                commit.gpgSign=false
                core.fsmonitor=false
                gc.auto=0
                maintenance.auto=false
hooks dir   proven to be an empty plain directory immediately before use, or STOP
            (review_hooks_path_invalid)
```

```text
The identity is distinct from "review-v1-planning-local-v1" even though the behaviour is the
same today. The Context binds this string (F2 §10.3) and R6/R11 bind it into Review validity, so
two contracts sharing one identity would let a change made for one silently redefine what the
other was validated under. Sharing the identity is prohibited; sharing the implementation is not.
```

### 7.2 What this satisfies, and what it does not

R5 §4 requires that **every** external executable or process Git can invoke on the exact staging and local
commit path be classified before the commit. The primitive splits that surface in two:

```text
mechanically denied by the primitive
    every hook on the commit path (pre-commit, prepare-commit-msg, commit-msg, post-commit),
      because core.hooksPath names a directory proven empty immediately before use
    GPG / SSH signing programs and default-key commands, because signing is disabled twice:
      by configuration (commit.gpgSign=false) and by the flag (--no-gpg-sign)
    the filesystem monitor
    background gc and maintenance

proven absent, never disabled
    clean filters, process filters, LFS clean/process filters, ident expansion and
      working-tree re-encoding
```

R5 §6 is explicit that a filter which materially defines committed bytes **cannot simply be disabled to
obtain safety**, because disabling it changes the semantic bytes. So the primitive does not disable filters.
It **proves none applies** (§7.3), and fails closed when one does.

```text
Review-v1 Work commit signing = disabled by the commit primitive.
That fact is part of the frozen Git persistence semantics identity and is bound into
Review-validity / Evidence identity (R5 §5, F2 §14.2 git_semantics). A future signed review-v1
commit is a later explicit contract version that must positively bind signing format, program,
agent, key and helper identity first. F3 does not infer such safety.
```

### 7.3 The Git persistence preflight — before EVERY commit of the primitive

P1 R5 §4 requires **every** external executable or process Git can invoke on the exact staging and local
commit path to be classified before the commit. §11.3 puts every Git stage of a review-v1 Work mutation
under this primitive, so the preflight binds every one of them — not only the two that carry K1 and K2.

```text
IMMEDIATELY BEFORE EVERY git_commit stage recorded with mode "review-v1-work-local-v1":

  1. determine the EXACT path set that stage will commit — the paths the stage's payload will
     name, after the same changed-against-HEAD narrowing the stage itself applies, and never a
     wider or a nominal set;

  2. run the complete persistence / external-process preflight for exactly those paths:
       hooks, signing, filesystem monitor and background maintenance are MECHANICALLY DENIED by
         the primitive itself (§7.1, §7.2) — the denial is re-established by the invocation, not
         assumed from a previous stage;
       `git check-attr filter ident working-tree-encoding` MUST print "unspecified" or "unset"
         for every one of those paths and every one of those attributes;
       the effective configuration MUST define no filter driver named "unset" or "unspecified";

  3. a question Git cannot answer is a REFUSAL, not a pass;

  4. an applicable or unsupported transform FAILS CLOSED before that commit is recorded and
     therefore before it is made.

Refusal code: review_git_transform (the existing live code; F3 introduces no new code here).
```

This binds, explicitly and without exception:

```text
S-c0                              the entry-events commit
S-c1                              the result commit K1
S-c2                              the terminal commit K2
every pre-completion Work Git commit
                                  a derived registration, a move, a human-NG move — every
                                  commit-only stage the Work cycle records under §11.3
```

```text
AND, before S-c1 only, the UNION check of §7.4.2: the same preflight over the complete set of
paths this operation will ever commit — the Candidate's entry paths, the event log, and the
Consumption path — so that a transform the executor itself introduced is discovered before any
result commit exists rather than at S-c2, when K1 might already be published.
```

```text
A preflight passed for one stage NEVER carries to another stage. Each stage's path set is its
own, the Project's attributes and configuration can change between stages, and a pass proven for
paths A says nothing about paths B.
```

**S-c1 specifically is preflighted twice, and the second time is the one W2 binds.** Topology step 9 runs
it as an early refusal, before the Candidate is frozen, so the operation does not pay for a whole Review
before discovering a transform. But the Review runs between step 9 and step 18, and it can take arbitrarily
long, during which the Project's attributes or configuration can change. So the preflight is run **again**
immediately before S-c1 is recorded, after the Review has completed (step 17a), and it is that later run
that C-2(K1) item W2 requires. The early run is an optimization and never satisfies W2.

The preflight is required at all because F2 §6.3 froze the Candidate's `new_oid` as `gitcmd.hash_blob` of
the executor's bytes, which is `git hash-object --no-filters`: if a clean filter applied, Git would store a
different object and C-2(K1)'s tree proof (§9, W4/W5) would fail after the commit already existed.

```text
Checkout capability is NOT bound for the Work path. F2 §10.3 froze that boundary: a Work result's
bytes are the executor's and are bound by Git object identity, not by a reproduction claim.
F3 does not add it.
```

### 7.4 Where a transform refusal happens, and what it is not

F2 §20.17 governs this exactly: *an ordinary, correct Work outcome is always expressible as a Candidate;
where an outcome is outside the expressible domain and the condition is knowable before the executor runs,
the refusal happens at START entry.* A Project's effective transform configuration **is** knowable before
the executor runs, even though which result paths it will touch is not. So the refusal is split, and the
knowable part is moved to the only non-trapping point:

```text
ENTRY REFUSAL — the knowable condition, before anything exists

  At START entry, before the Project execution lock and before any mutation is opened, a review-v1
  Work START is refused when the Project's effective Git configuration or attributes define ANY
  filter, ident or working-tree-encoding that could apply to a working-tree path.

    code      review_git_transform
    effect    nothing is written, no mutation exists, no event, no commit, no Review record.
              The Project is exactly as it was, and legacy START is fully available for it as a
              separate invocation.

  Consequence, stated rather than hidden: a Project that genuinely uses a content filter — Git LFS,
  a clean/smudge pair, ident expansion, working-tree re-encoding — cannot use review-v1 Work at
  this contract version. That is a stated v1 boundary, refused before the person has spent
  anything, and it is the same kind of honest limit F2 §13.6 set for Evidence completeness.

POST-EXECUTOR — a transform that did not exist at entry now applies

  This is NOT one condition. It is two, with different causes and different lawful dispositions,
  and §7.4.1 separates them.
```

#### 7.4.1 Operation-owned persistence configuration is a legitimate Work result

The previous draft of this contract called any post-executor transform a "malformed run". **That
classification was unsupported and is withdrawn.** The check against landed authority:

```text
registry.md          names no path a Work result may not touch
skills/start         Work result = declared result paths and declared deleted paths; no exclusion
skills/review        says only that WORKLINE never writes .gitattributes or info/attributes —
                     a statement about Workline's own writes, not about an executor's result
F2 §6.2              the reviewed surface is exactly result_paths U deleted_paths as declared
F2 §6.4              directly on point: "If .gitmodules is itself a declared result path, it is
                     an ordinary file entry like any other and is represented separately."

There is no landed rule making .gitattributes, .gitmodules or any configuration file an invalid
Work result. Calling such a result malformed would be a post-executor prohibition invented here,
which is precisely what F2 §2.3 forbids.
```

Frozen classification:

```text
OPERATION-OWNED persistence-config result
    the changed .gitattributes (or equivalent) is a DECLARED result path of this Work, and the
    change is this operation's own product.

    -> NOT malformed. It is an ordinary Work result, represented in the Candidate as an ordinary
       file entry like any other (F2 §6.4), reviewed like any other, and committed like any other.

EXTERNAL persistence-config drift
    the effective attributes or configuration changed, and the change is NOT a declared result
    path of this Work.

    -> external interference. It is the same class as any other foreign change to the ground the
       operation decided on, and it reconciles. F4 owns what recovery is attempted (§25).
```

#### 7.4.2 The lawful topology for an operation-owned change

The danger the classification was reaching for is real, but it is a SCOPE problem, not a validity
problem: a new transform introduced by the executor can apply to paths this same operation has yet to
commit — including the terminal paths — and by the time S-c2 discovered it, K1 could already exist and
even be published.

That is closed by widening *when* and *over what* the preflight runs, not by prohibiting the result:

```text
BEFORE S-c1 IS RECORDED, the preflight runs over the COMPLETE set of paths this operation will
ever commit, evaluated against the post-executor working tree — which already holds whatever
.gitattributes the executor produced:

    the Candidate's entry paths                     (S-c1's set)
  U .workline/events/events.jsonl                   (S-c2's event log)
  U .workline/review/consumptions/<consumption_id>.yaml   (S-c2's Consumption)

The Consumption path is knowable at this point: its identifier is reserved under the
deterministic, replay-stable key `review-consumption:<receipt_id>` (R2 §2), and the Receipt exists
from the seal, which precedes S-c1. F3 therefore requires that reservation to happen at or after
the seal and BEFORE S-c1 (§13.2), which is earlier than R4 §6 demands and strictly safe.
```

```text
Consequence, and this is the point of the widening: a transform the executor introduced that
would affect the terminal commit is discovered BEFORE K1 exists. Nothing is committed, nothing is
published, and the operation refuses at a point where refusing costs a Review and no history.

A transform the executor introduced that affects NOTHING this operation commits does not refuse
at all. The .gitattributes change is committed as an ordinary result, the Work completes
normally, and later operations see the new semantics — which is exactly the lawful outcome the
re-review asked for.
```

The per-stage preflight of §7.3 remains, unchanged, as the backstop before every later commit: it catches
external drift arriving after the union check passed.

#### 7.4.3 The one bounded case that still refuses, named precisely

```text
The executor's new transform applies to a path THIS SAME OPERATION commits.

Then the Candidate cannot faithfully describe the artifact: F2 §6.3 freezes new_oid as
gitcmd.hash_blob of the executor's bytes, which is `git hash-object --no-filters`, and Git would
store a different object. The Candidate would assert an identity Git does not hold.

Disposition: refuse BEFORE S-c1 is recorded, code review_git_transform. No commit exists, nothing
is published, and the Review that was performed is the only cost.
```

```text
This is an EXPRESSIBILITY boundary of the Candidate at this contract version, and it is stated
rather than hidden. It is NOT called malformed, and it is not a claim that the outcome is wrong:
the Work may be perfectly correct. What is true is only that F2 §6.3's object identity cannot
describe it.

Lifting it would require amending F2 §6.3 so that new_oid is the FILTERED object identity — which
changes what the reviewer is shown, changes content_sha256's meaning, and interacts with
declare_own_content's own-bytes digest. That is a larger architecture change than this contract's
findings call for, and F3 deliberately does not make it. It is named here so a later contract
version does not have to rediscover it.

It is not an architecture blocker: the topology is lawful and complete for every other case, the
refusal happens before any physical effect, and the general operation-owned case — the one the
re-review raised — proceeds normally.
```

#### A pending review-v1 mutation never downgrades to legacy

This must not be read as a recovery mechanism, and the earlier draft's phrase "the recourse is legacy
START" invited exactly that misreading. The frozen statement:

```text
A pending review-v1 mutation NEVER becomes a legacy mutation. F1 §5.2 case 4 refuses a legacy
retry of a pending review-v1 record with ReconcileRequired / review_marker_mismatch, and F1
invariant 2 freezes that a pending mutation's semantic contract never changes on retry.

Legacy availability in an activated Project (F1 §10.3, F1 invariant 1) is a property of a
SEPARATE, LATER INVOCATION. It is not a fallback for, and says nothing about, a mutation that is
already pending under review-v1.

If the Project's configuration is changed so that the preflight passes, the SAME review-v1
mutation resumes from its saved result: START already records the executor's result and continues
from it without re-running the executor, exactly as it does after a dirty_overlap refusal.

If the condition cannot be changed, what recovery or abandonment would permit a later invocation
is NOT invented here. That belongs to the F4 recovery authority (§25), and F3 defers it rather
than implying a path that does not exist.
```

#### 7.4.4 No-trap re-check, case by case

```text
a transform configured at START entry
    refused at entry, before any mutation exists. Nothing is stranded because nothing was opened,
    and legacy START is available as a separate invocation.        F2 §20.17, knowable condition

an operation-owned .gitattributes result affecting nothing this operation commits
    PROCEEDS NORMALLY. Ordinary file entry, ordinary Candidate, ordinary K1, ordinary completion.
    This is the case the re-review raised, and it is lawful.                            §7.4.2

an operation-owned .gitattributes result affecting the TERMINAL paths
    caught by the union preflight BEFORE S-c1. No K1, nothing published, no stranded published
    result. The Work can be restructured and re-run.                                    §7.4.2

an operation-owned transform covering this operation's OWN result paths
    refused before S-c1, at an expressibility boundary that is named, bounded and pre-physical.
    Not called malformed, not called invalid.                                           §7.4.3

external drift after the union check passed
    the per-stage preflight refuses before the affected commit; this is foreign interference and
    it reconciles. What recovery is attempted is F4's.                                  §7.4.1
```

```text
No ordinary correct outcome is left with a pending mutation and no lawful continuation that F3
itself creates, and no post-executor prohibition is invented by naming an outcome malformed.

Architecture blocker: NONE.
```

F3 does not weaken the byte-identity requirement to accommodate any of this, because doing so would make
the Candidate's `new_oid` a claim about bytes Git does not store.

### 7.5 C-1: how exact local commit identity becomes durable

```text
The Mutation Controller records the full object ID of the commit it made beside the effect
payload, at the moment it makes it, and only when it can prove the new HEAD is a one-parent child
of the pre-commit HEAD (M-10).

A commit this operation cannot positively show it created is NEVER K, however exactly its
content, tree, parent, branch or message match (R5 §3.1). In particular:
    the branch tip is never K
    a commit with a matching message is never K
    a byte-identical commit made by another subject is never K
    a commit made by a hook continuing after the primitive's commit is never K
```

Where a review-v1 result stage's content reaches committed state without this operation having created the
commit, there is no K1 for that attempt and there never will be one: R5 §3.5 applies unchanged — no exact
proof, no authorized push, reconcile or a new Candidate against the actual committed state. F3 adds nothing
to that and takes nothing from it.

---

## 8. K1 lineage (F3-D2)

### 8.1 The question, and the primary-source constraint that answers it

The natural rule to freeze would be:

```text
parent(K1) == Candidate.declared_base.base_commit
```

**It is not implementable, and freezing it would make every review-v1 Work fail.** The reason is measured,
not theoretical (M-12):

```text
P1 R3 §10, enforced live by gate.require_persisted, requires an accepted task's canonical
records to have reached committed state before the external launch boundary is crossed — because
a record that exists only in the working tree is gone from a fresh clone, and an accepted task
whose provenance is gone cannot be rerun or retrieved.

The Review gate therefore commits its own records, in its own generation mutations, BEFORE the
reviewer is launched: generation 1 (accept, with the Candidate snapshot and the TaskInput),
generation 2 (settle) and generation 3 (seal, issuing the Receipt) each commit.

Each of those commits advances HEAD on the same branch.

So between freezing the Candidate at declared_base.base_commit and committing K1, HEAD has
necessarily advanced by at least three commits, none of which this contract may forbid.
```

A rule requiring `parent(K1) == base_commit` could only be satisfied by committing K1 on an older base,
which forks the branch — prohibited everywhere in P1 and in `rules/git`.

### 8.2 The frozen rule

```text
lineage contract "review-v1-work-lineage-v1"

parent(K1) is the commit HEAD holds when S-c1 is recorded, and ALL of the following MUST be
positively proven before S-c1 is recorded:

  L-1  declared_base.base_commit is an ancestor of parent(K1), or equal to it.

  L-2  EVERY commit in the range (declared_base.base_commit, parent(K1)] is an own-Review commit:
         it has exactly one parent, and
         its complete delta against that parent is non-empty and confined to this Run's own
           canonical Review record paths, and
         every entry of that delta has status "A" and mode 100644
           (a canonical Review record is immutable and is only ever added).

       This Run's own canonical Review record paths are DERIVED from the Run's validated chain,
       never hardcoded: the Candidate snapshot of candidate_hash, the task input of every task
       the chain accepted, the gate generation file of every generation the chain holds, and the
       Receipt the sealed generation issued. At this contract version the Policy requires exactly
       one task slot (F2 §10.4) and the chain is accept -> settle -> seal, so the set is:
         .workline/review/candidate-snapshots/<candidate_hash>.yaml
         .workline/review/task-inputs/<review_task_id>.yaml
         .workline/review/gates/<review_run_id>/000001.yaml
         .workline/review/gates/<review_run_id>/000002.yaml
         .workline/review/gates/<review_run_id>/000003.yaml
         .workline/review/receipts/<receipt_id>.yaml
       A path outside the derived set — any other Run's record, an invalidation generation, a
       Supersession, or anything at all outside the Review namespace — makes the commit foreign.

  L-3  HEAD is on declared_base.branch, by its full ref name, and that branch holds parent(K1).

  L-4  S-c1 is base-exact: HEAD is read again immediately before `git add` and again immediately
       before `git commit`, and the commit is not made unless HEAD is still exactly parent(K1)
       (M-7). A moved HEAD refuses with ReconcileRequired, reason review_registration_base_moved.

  L-5  The generic "HEAD advanced independently" allowance is NOT available. A recorded K1 is
       never made on a HEAD that grew after it was recorded, whatever paths the growth touched.
       The live controller already excludes a base_exact payload from that allowance.

Any commit in the range that is not an own-Review commit means the Candidate is not usable:
freeze a NEW Candidate against the new HEAD and perform fresh verification and review
(F2 §14.4). Nothing is adopted, nothing is rebased, nothing is reinterpreted.
```

### 8.3 Why this is stricter than the live planning rule, deliberately

The live planning currency proof tolerates any intervening commit that does not touch a planning-owned path
(`_pre_kp_proof`, `_c2_kp` P2). F3 does **not** adopt that tolerance for the Work path:

```text
F2 §14.4 froze that at this contract version a HEAD advance resolves as "prior Review is not
reused; freeze a NEW Candidate", because Evidence completeness is unknown and may_reuse cannot
answer "reusable". L1 alone — untouched owned paths — is explicitly NOT sufficient.

skills/review states the same thing directly:
    Git-write compatibility != Review-validity compatibility
    記録したpathsが触られていないことは、Context / Evidence / Policy / toolchain /
    provenanceが変わっていないことを何も示さない

Tolerating a foreign commit because it touched no owned path would therefore be exactly the
"unknown treated as proven" move F2 §20.10 and §20.16 forbid.
```

So the only tolerated commits are this Run's own record commits, which are **provably** incapable of
changing anything a bound identity covers: they add immutable Review records at named paths and change no
domain state, no authority file, no Policy and no toolchain.

### 8.4 Why an own-Review commit is not a "HEAD advance" under F2 §14.4

F2 §14.4 governs **prior** Review validity — whether a Review that already exists may be reused against a
later state. Its layer 2 is `closure.may_reuse(before, after)`, which compares two closures, and a closure
exists only once Evidence exists. A generation commit happens **while the Review is being produced**, before
any closure exists to compare: there is no prior Review to reuse. §22 row 3 classifies this formally.

F3 states the boundary so it can never be blurred:

```text
own-Review advance   commits of this Run's own canonical Review records, made by this Run's own
                     generation mutations, inside the Review. Enumerable exactly, provable from
                     committed objects alone, and covered by L-2.

foreign advance      every other commit: a person's, another tool's, another operation's, another
                     Run's. Invalidating. F2 §14.4 applies in full.
```

### 8.5 The same rule governs the empty case

For an empty-artifact Candidate there is no K1, and the lineage rule applies to `parent(K2)` measured from
`declared_base.base_commit` with the identical L-1 … L-5 (§6.3). The user-proposed
`parent(K2) == declared_base.base_commit` fails for exactly the reason §8.1 gives, and is replaced by the
same own-Review-only range rule.

### 8.6 What is never a lineage answer

```text
the branch tip
a commit found by message
a commit found by content identity
a commit whose parentage Git could not answer about
"the paths look unchanged"
a merge commit anywhere in the range (L-2 requires exactly one parent)
```

---

## 9. K1 exact proof — C-2(K1) (F3-D5)

Contract `review-v1-work-proof-v1`. Every item is evaluated against the **exact K1** named by C-1 and
against nothing else. Every item is required. A failure is `reconcile_required`; no item degrades to a
weaker check and no item is skipped because another passed.

```text
C-2(K1) exists only where K1 exists — that is, only when artifact_kind is "result_commit" (§6.7).
For an "empty" Candidate there is no K1, no C-2(K1) and no result publication, and the absence of
this proof is not a gap: there is nothing for it to be about. What is NOT permitted is to reach
this section with an "empty" Candidate and skip it; the topology never records S-c1 at all.
```

```text
W1   OWNERSHIP
     The S-c1 effect is recorded applied and carries commit_id = K1, the full object id of a
     commit this mutation made (M-10). Absent or unprovable -> review_commit_unowned. The branch
     tip, a matching message and byte-identical content are never accepted in its place
     (R5 §3.1). This item is a precondition of every item below it: W2 ... W12 are checked
     against an already-owned commit and never confer ownership.

W2   PERSISTENCE SEMANTICS
     The S-c1 payload names mode "review-v1-work-local-v1", and the Git persistence preflight of
     §7.3 passed IMMEDIATELY BEFORE the stage was recorded — topology step 17b, after the Review
     completed — over the UNION of every path this operation will ever commit: the Candidate's
     entry paths, the event log and the Consumption path (§7.4.2). Step 9's early run is an
     optimization and never satisfies this item, and a preflight over S-c1's paths alone does not
     satisfy it either.

W3   LINEAGE
     parent(K1) is exactly the recorded base_head; K1 has exactly one parent; L-1 ... L-5 of §8.2
     all hold; HEAD is on declared_base.branch and that branch still holds K1.

W4   ARTIFACT DELTA — exact, complete, and not a path allowlist
     Split the Candidate's entries by whether they changed anything:

         changing entries   old_kind/old_mode/old_oid differ from new_kind/new_mode/new_oid
         inert entries      they do not — a declared result that changed nothing, which F2 §6.3
                            keeps in the Candidate because what the executor declared is part of
                            what is reviewed

     Then, against commit_delta(parent(K1), K1):

         the delta's path set equals the CHANGING entries' path set exactly — no extra path,
           no missing path;
         for every such path the delta's old_mode, new_mode, old_oid and new_oid equal the
           entry's, and its status, normalized as below, equals the entry's status;
         no inert entry appears in the delta at all, because it changed nothing. Its identity is
           proven by W5 against K1's tree, never by its absence here.

     Status normalization, because the two vocabularies differ and the difference is not a defect:
         Git raw A -> "A"      Git raw D -> "D"      Git raw M -> "M"
         Git raw T -> "M"      a type change (file <-> symlink <-> gitlink) has both sides
                               present, which is exactly F2 §6.3's "M"
         any other letter (C, R, U, X, or anything unrecognized) -> the proof FAILS
     The delta is read with rename detection off, so C and R cannot arise; they are listed so
     that their appearance is a failure rather than an unhandled case.

     A path allowlist, a "touches only these paths" check or a rename-detecting diff is NEVER a
     substitute for this (R7 §10). If the complete enumeration cannot be obtained, the proof
     fails; it does not fall back to partial evidence.

W5   TREE CONTAINMENT
     tree_entries(K1, <the Candidate's entry paths>) resolves every non-deleted entry to exactly
     the Candidate's new_kind, new_mode and new_oid — including 120000 symlinks by their link
     object and 160000 gitlinks by their referenced commit OID — and every entry declared deleted
     is absent from K1's tree. A submodule checkout, a branch tip and .gitmodules are never
     consulted (F2 §6.4).

W6   MESSAGE
     K1's commit message is exactly content.message, byte for byte, with no prefix, no suffix, no
     normalization and no whitespace change (skills/start, 成果commit message).

W7   REVIEW RECORDS PRESENT AND UNCHANGED
     At parent(K1) AND at K1, every one of this Run's canonical Review record paths (§8.2, L-2)
     is held with its exact canonical bytes; the whole Review namespace reads canonically at
     both; and neither holds an invalidation generation of the Run or a Supersession of the
     Receipt.

W8   AUTHORIZATION CURRENT
     The Receipt is this Run's latest valid authorization; the gate-to-Receipt binding holds
     field by field; authorized_candidate_hash == candidate_hash;
     authorized_operation_stage == "start:work-terminal"; target_identity is this Work;
     operation_identity equals the recomputed "start:" + digest of the request identity (F2 §4.2);
     review_kind == "work-result-v1".

W9   CANDIDATE CURRENT
     W9a  declared_base re-derives exactly at declared_base.base_commit, through the canonical
          loader, from committed state only.
     W9b  every field of declared_base except base_commit re-derives identically at parent(K1).
     The two are separate checks by separate mechanisms — W9 reads through the loader, W3/L-2
     reads tree deltas — and both are required. A domain change smuggled into a commit that
     looked like a Review-record commit fails both.

W10  CONTEXT, POLICY AND EVIDENCE IDENTITY
     The Work Review Context recomputes to review_context_hash, including each bound authority
     digest (registry.md, skills/start, skills/review, skills/create), the loader identity, the
     git_persistence identity and the activation binding; effective_policy_hash matches the
     Effective Policy; evidence_digest and the closure digest inside it are the ones the gate
     bound.

W11  ACTIVATION
     The activation record at parent(K1) is present, well-formed and of a supported version; its
     prefix digest reproduces under work-terminal-activation-digest-v1; and its record digest
     equals the one bound in BOTH the Candidate and the Context (F2 §11). The two digests are
     never substituted for one another.

W12  NOT YET APPLIED — the transition and the consumption have not happened
     No work_target_removed and no work_completed event for this Work exists in the event log at
     K1 or among this mutation's applied effects;
     this mutation holds no recorded append_event of a Work terminal type at a position before
     the S-c1 stage;
     no Consumption of this Receipt exists at K1 or anywhere in the Review namespace;
     this mutation holds no git_push effect recorded before S-c1.
```

```text
The AuthorizedTransitionProjection is NOT applied at C-2(K1). The Consumption is NOT applied at
C-2(K1). K1 is the reviewed artifact and nothing else (§17).
```

---

## 10. The C-2 durability model (F3-D6)

### 10.1 The decision

```text
OPTION A is frozen.

C-2 is a DETERMINISTIC RE-EXECUTABLE PROOF whose authoritative, immutable inputs are:
    the exact committed Git objects of K and of its parent
    the canonical Review records, read at the exact commit through the committed reader
    the canonical mutation and publication identities of this operation

Runtime mutation state records C-1 (the exact commit identity) and the recovery pointer note
(§4.5) for same-operation recovery. It is NOT the semantic proof authority.

Before a publication effect is recorded, and again before it is applied, the exact proof is
re-evaluated in full from the authoritative immutable inputs.

Option B — a new clone-safe canonical commit-proof record — is NOT taken.
```

### 10.2 Why Option A satisfies P1's requirement that C-2 be complete, durable and exact-K-bound

```text
COMPLETE
  Every item of §9 (and §16 for K2) runs to a result before the publication effect is recorded.
  There is no partial pass and no deferred item. An item whose question Git or the canonical
  reader cannot answer FAILS; unanswerable is never a pass.

DURABLE
  Durability is a property of the INPUTS, not of a stored verdict — but the inputs are of TWO
  different layers with two different durability guarantees, and they must not be collapsed
  (§10.2.1). The semantic proof material is clone-readable; the operation's ownership binding is
  durable only for the owning mutation. The proof is re-executable wherever BOTH layers are
  present, which is not the same as "from any clone".

EXACT-K-BOUND
  Every item names the exact K of C-1 and evaluates against it alone. W1 refuses to proceed
  without that identity. No item reads a branch, a tip, a ref or a message.
```

#### 10.2.1 The two layers, and what each one's durability actually means

```text
LAYER 1 — SEMANTIC PROOF MATERIAL

    the exact Git objects of K and of its parent
    the canonical Review records, read at an exact commit
    the committed canonical Project state

    durability   immutable once written; readable from any clone of the repository
    role         every question the proof asks about WHAT was committed and WHAT was authorized

LAYER 2 — OPERATION OWNERSHIP BINDING

    C-1: the exact identity of K, recorded as commit_id on this mutation's own commit effect
    the recorded mutation effect and its stage identity
    the proof pointer note (§4.5)

    durability   durable for the OWNING mutation, in this workspace's
                 .workline/runtime/mutations/**
    role         the single question of WHOSE commit K is

    NOT reconstructed from a branch tip, from content identity, from a commit message, or from
    any resemblance whatever (R5 §3.1).
    NOT claimed to survive deletion or loss of .workline/runtime/**.
```

```text
Item W1 reads layer 2. Items W2 ... W12 read layer 1 and are evaluated against the K that layer 2
names. So the proof as a whole is re-executable exactly where both layers are present.
```

Frozen consequences, which are the two cases that actually occur:

```text
ordinary process crash, mutation record durable
    both layers present -> resume, and RE-EXECUTE the proof in full. Nothing is read from a
    stored verdict, and a prior pass does not carry (§10.2.2).

fresh clone, or the runtime mutation record lost
    layer 1 present, layer 2 GONE. Ownership cannot be reconstructed, no K is inferred, and the
    operation fails closed under R5 §3.5: no owned K1 -> no exact proof -> no authorized push ->
    reconcile, or a new Candidate against the actual committed state.
```

```text
It is NOT claimed that a C-2 proof is independently resumable "from any clone". Layer 1 is
clone-readable; layer 2 is not, by design, because operation ownership is precisely the thing
that must not be inferable by anyone who can read the repository.
```

#### 10.2.2 Durable checkpoint completion is NOT timeless current validity

This distinction is frozen, and the earlier draft got it wrong by claiming a proof over immutable inputs
"yields the same result at every later evaluation". That is false, and believing it would defeat the very
recheck R5 §12.4 requires:

```text
The committed objects are immutable. The SET of canonical facts is not.

Between a completed C-2 and a later boundary, new canonical facts can appear in the Review
namespace and change the answer:

    a Supersession of the Receipt
    an invalidation generation of the Run
    a Consumption of that Receipt
    a change in bound authority, Context, Policy or Evidence identity where applicable

Each of these is an addition, not a mutation of anything already written — and each of them makes
a previously passing C-2 FAIL on re-evaluation, correctly.
```

The frozen model:

```text
1. The exact-K proof is deterministically RE-EXECUTABLE from durable identities and canonical
   committed facts. It is never read from a stored verdict.

2. A durable note or pointer binds WHICH exact K and which checkpoint was reached, for recovery.
   It is never proof authority and never a proof result (§10.4).

3. CURRENT VALIDITY is re-derived at every required boundary: before a publication effect is
   recorded, and again before it is applied (R5 §12.4 — "Passing the check once at record time
   does not carry to apply time").

4. A later canonical fact can make a previously completed proof STALE. That is expected behaviour
   of a current-validity predicate, not a defect and not a contradiction.

5. Staleness causes FAIL-CLOSED / reconcile. It is never read as the proof having disappeared,
   never as a reason to fall back to a weaker contract, and never as evidence that a push
   authorizes itself.

6. "The checkpoint was reached" and "the authorization is valid now" are two different questions.
   The note answers only the first. Only re-execution answers the second.
```

This is also the decisive reason Option B is refused (§10.5 item 3): a stored verdict answers the first
question and silently presents it as an answer to the second.

### 10.3 Recovery of the exact K identity after runtime loss — the honest answer

The question is: after `.workline/runtime/**` is lost, how does the operation recover the exact K identity
without branch-tip inference?

```text
It does not, and it MUST NOT try.

The mutation record lives under .workline/runtime/mutations/**. Losing it loses C-1, and C-1 is
the operation's ownership of K. R5 §3.1 is absolute: a commit this operation cannot positively
show it created is never backfilled or adopted as K, however exactly its content, tree, parent,
branch or message match.

So runtime loss does not degrade into inference. It resolves, already and without any new rule,
as R5 §3.5:

    no owned K1  ->  no exact K1 proof  ->  no authorized push
                 ->  reconcile, or a new Candidate against the actual committed state

The absence of an owned K is not completed work, and it is never converted into a metadata-only
authorization of somebody else's commit.
```

What Option A **does** guarantee is the thing R5 actually asks for and the thing a stored verdict cannot
give: while the record survives, every resume re-derives the whole proof from immutable inputs, so
`C-2 is never reconstructed from the existence of a push` (R5 §12.4) is satisfied mechanically rather than
by discipline. The note is checked for agreement, never read as a result.

### 10.4 The durable checkpoint artifacts, and what they are not

```text
C-1(K)        the recorded commit effect's commit_id. Operation-owned identity. Durable.
C-2 note      §4.5. Names the contract and the exact commit a completed proof was for.
C-2 progress  the next recorded stage. With a remote, S-p; without one, the stage after it.
```

```text
A note is never evidence that a proof passed.
A recorded push is never evidence that a proof passed.
A published commit is never evidence that a proof passed.
A note that names a commit the record does not hold as this mutation's own publishes nothing.
A note whose contract identity is absent, unknown or of another version fails closed.
```

### 10.5 Why Option B is refused

```text
1. RECURSION. A canonical commit-proof record would have to be committed to be clone-safe. That
   commit would itself need a proof, whose record would need a commit. The live P2 architecture
   avoids this by making the NEXT durable artifact the checkpoint — the Consumption for C-2(Kp),
   the note for C-2(Km) — and introduces no proof record anywhere (M-11).

2. THE NAMESPACE IS CLOSED. REVIEW_SUBDIRS is exactly seven directories and
   require_review_record_path refuses any other location (M-13). Adding one is a namespace
   expansion P1 R1 deliberately closed, and F2 §9.3 was designed specifically to avoid one.

3. A STORED VERDICT CANNOT SATISFY R5 §12.4. That section requires C-2 to be re-checked as
   durably complete AND STILL CURRENT before S-p is recorded and again before it is applied, and
   states: "Passing the check once at record time does not carry to apply time." Only
   re-evaluation can meet that. A stored verdict would be exactly the thing that carries.

4. A SECOND AUTHORITY THAT CAN DISAGREE. A record asserting "K was proven" can survive a state
   in which it is no longer true — a Supersession written since, an invalidation generation, a
   Consumption of the same Receipt. Re-evaluation cannot.
```

### 10.6 What would change the decision

Stated so a later contract version does not have to re-derive it: Option B becomes necessary only if a
required C-2 item ever depends on material that is **neither** an immutable committed object **nor** a
canonical Review record — for example a reviewer-side observation that cannot be re-derived. No item in §9
or §16 has that property. If one is ever proposed, Option A must be revisited before that item is frozen.

---

## 11. `review-v1-split-v1` validation for the Work path (F3-D7)

### 11.1 Contract selection — durable metadata only

```text
The publication contract is read from the mutation's durable invocation and from NOTHING else.

  "work"              invocation["operation"] == "start"
                      AND invocation["review_contract"]      == "review-v1-work-v1"
                      AND invocation["publication_contract"] == "review-v1-split-v1"
                      AND no other marker key is present

  "planning"          unchanged, live (mutation._publication_contract)
  "generation"        unchanged, live: publishes nothing
  "current-combined"  unchanged, live: no marker key at all, positively shown
  "invalid"           every other presence, value or combination -> FAIL CLOSED
```

```text
Both markers are required together. One without the other is invalid.
A marker with an unknown or unsupported value is invalid.
A marker contradicted by the mutation's other durable operation metadata is invalid.
An invalid selection NEVER falls back to current-combined (R5 §12.3.1 case B / case E).
The contract is NEVER inferred from stage shape, from the presence or absence of a
git_commit + git_push pair, from Review file presence, from Candidate presence, from branch
state, from HEAD position, from history shape or from any content pattern (R5 §12.3.2).
```

Legacy is untouched: a mutation with no marker key, positively shown, is `current-combined` and is validated
by the live rule exactly as it is today (R5 §12.1).

### 11.2 The Work publication validator

```text
validator identity "review-v1-work-publication-v1"
```

A `git_push` effect in a "work" mutation publishes a commit only when **all** of the following are shown.
Anything short of it names no commit, publishes nothing, and stops with `reconcile_required`.

```text
V-1  PUSH-ONLY STAGE
     The push is the ONLY effect of its stage. A stage holding a git_commit beside it is a
     combined stage, which is a push in the same uninterrupted apply pass as its commit — that
     is a push before proof, and it is refused with review_publication_contract_invalid
     (R5 §12.2, §12.5).

V-2  THE PUSH NAMES A COMMIT
     payload["commit"] is a full object id K. The branch as it is when the push runs never
     stands in for it.

V-3  EXACTLY ONE PROOF NOTE NAMES K
     Exactly one of the two notes of §4.5 names K under contract "review-v1-work-proof-v1":
         "review_work_result_proof".result_commit     == K   -> this is the result publication
         "review_work_terminal_proof".terminal_commit == K   -> this is the terminal publication
     Neither naming K, or both naming K, publishes nothing. This is what identifies which
     publication point a push is; the stage's shape never identifies it.

V-4  THE COMMIT EFFECT THAT MADE K
     There is exactly one git_commit effect in this mutation recorded applied with
     commit_id == K. It is the only effect of its own stage, recorded earlier than the push by
     seq, its payload names mode "review-v1-work-local-v1", and its payload branch is the full
     ref name the push names.

V-5  GIT AGREES
     K has exactly one parent, that parent is the commit effect's recorded base_head, and the
     recorded branch still holds K.

V-6  THE ROLE-SPECIFIC DELTA
     result publication    permitted ONLY when artifact_kind is "result_commit" (§11.3.1).
                           commit_delta(parent(K), K) equals the Candidate's CHANGING entries
                           exactly (§9 W4), and this mutation holds no Work terminal
                           append_event effect recorded before the commit effect that made K.
                           A result publication in an "empty" operation is refused: there is no
                           K1, so a push claiming to be one names a commit that is not one.
     terminal publication  commit_delta(parent(K), K) is exactly the terminal delta of §17.2,
                           the terminal stage is recorded and applied, and the Consumption
                           effect is recorded and applied.

V-6a THE CARDINALITY FOR THIS CASE
     The number of git_push effects recorded in this mutation is consistent with what §11.3.1
     requires for this operation's case — computed from the destination pin and the CANDIDATE's
     content.artifact_kind, before any stage is examined — and at the terminal publication it
     equals that number exactly. Any excess push, and any push of a kind the case does not
     allow, is a refusal whichever individual pushes would otherwise validate.
     At a result publication the required count is not yet reached, which is expected and is not
     a defect: the check at that point is that no push beyond the case's allowance exists and
     that this one is the result publication the case permits.

V-7  C-2 IS STILL CURRENT
     The full C-2 of §9 or §16, for exactly K, is re-evaluated immediately before the push
     effect is applied. Passing at record time does not carry to apply time (R5 §12.4).

V-8  THE REFSPEC
     The push publishes `<K>:refs/heads/<full branch name>`, never forced, never a branch-tip or
     pattern refspec (R5 §7, M-8).
```

### 11.3 Which physical stages are legal under `review-v1-split-v1` for a Work mutation

```text
LEGAL
  a commit-only stage holding exactly one git_commit with mode "review-v1-work-local-v1" —
    S-c0, S-c1, S-c2, and every Git stage the Work cycle records before the completion
    (a derived registration, a move, a human-NG move)
  push-only stages, each holding exactly one git_push naming a commit one of the two proof notes
    names, in the exact cardinality of §11.3.1
  the terminal stage of §13.3
  the non-Git stages the Work cycle already records (lifecycle events, registrations, relation
    writes) — unchanged from legacy

ILLEGAL — each fails closed, publishes nothing, and reconciles
  a stage holding a git_commit and a git_push together
  a push whose stage holds any other effect
  a push naming a commit no proof note names, or that both notes name
  any push beyond the exact cardinality of §11.3.1 for this operation's case
  a push recorded before the C-2 of its commit is complete
  a git_commit with no mode, or with the planning mode, in a Work mutation
  a git_push in a generation mutation (live, unchanged)
  any push at all while the markers are partial, unknown or contradictory
```

#### 11.3.1 Push cardinality — exact, per case

The earlier draft said "exactly two push-only stages" as the general legal shape. That was wrong: it
contradicts both the no-K1 topology (§6), which has no K1 to publish, and the no-remote topology (§20),
which publishes nothing at all. The exact frozen cardinality:

```text
remote present, artifact_kind = "result_commit"    EXACTLY 2 pushes:  S-p1(K1), S-p2(K2)
remote present, artifact_kind = "empty"            EXACTLY 1 push:    S-p2(K2)
no remote, either artifact_kind                    EXACTLY 0 pushes

every case                                         AT MOST 2, and no git_push effect anywhere
                                                   in the mutation other than the ones this table
                                                   allows for that case
```

```text
The case is selected from TWO durable facts, and from nothing else:

  whether a remote exists     the Project's approved push destination pin, verified at entry
                              before the lock (registry.md, Push destination)

  which artifact_kind         the Candidate's content.artifact_kind — a durable field of a record
                              that exists from the moment the Candidate is frozen, which is before
                              any publication stage of either kind
```

```text
The Consumption's artifact_kind is NOT an input to this selection, and deliberately so: the
Consumption does not exist when S-p1 is recorded. It is created by the terminal stage, which runs
after the result publication. A validator that tried to read it at S-p1 would be reading a record
that has not been written.

Its role is a SEPARATE and later one, and it is not weakened by being later:

  as soon as the Consumption exists, §14's comparison runs — both fields read on their own, then
  compared — and agreement is a PRECONDITION of recording S-p2;
  a disagreement fails closed at that point, so an operation whose two records disagree never
  reaches its terminal publication;
  and the agreement is proven again from committed state at C-2(K2) item T8 and at the
  recorded-completion proof P-5.

So the cardinality is fixed from the Candidate at the first publication and independently
confirmed against the Consumption before the second. Neither field is ever derived from the
other (§14.1).
```

```text
The cardinality is NEVER inferred from what the mutation's stages look like.

Stage shape does not select the publication contract (R5 §12.3.2, §11.1) and it does not select
the case within it either. The validator computes the expected cardinality from the two durable
facts above and then checks the recorded stages against it — never the reverse. A mutation whose
stages happen to hold one push is not thereby an empty-artifact operation, and one that happens
to hold two is not thereby result-bearing: either mismatch is a refusal.
```

```text
A review-v1 Work mutation therefore holds at most two pushes, and never one that is not the
publication of K1 or of K2. Every other commit it makes is local, and reaches the destination
only as the proven history of one of those.
```

### 11.4 The fail-closed matrix

```text
S-c exists, C-2 missing                                   -> no push
C-2 note binds a different K than the push                -> fail closed
C-2 note contract absent / unknown / other version        -> fail closed
C-2 re-evaluation fails at record time                    -> the push stage is not recorded
C-2 re-evaluation fails at apply time                     -> nothing is pushed; reconcile
the authorization is stale or superseded                  -> fail closed
S-p binds a different destination than the pin            -> fail closed
a Work mutation holds a combined commit+push pair         -> refused; it does not bypass C-2
a terminal event is recorded before C-2(K1)               -> refused (§9 W12, V-6)
a push already occurred but C-2 is absent or unprovable   -> NEVER infer proof from the push;
                                                             historical escape, reconcile
Review-v1 durable metadata present, publication_contract
  absent (R5 §12.3.1 case B)                              -> contradictory; fail closed before
                                                             any contract is selected
```

```text
`unknown` is never `proven`, anywhere in this matrix.
```

---

## 12. Publication barrier composition (F3-D8)

### 12.1 The barrier is preserved exactly

```text
No Workline push — of ANY operation, legacy ones included — publishes a commit whose history
holds a review-v1 planning registration commit unless the committed planning proof proves that
registration's Run for exactly the commit being published.

F3 preserves this without narrowing, without exception and without a review-v1 Work carve-out.
```

### 12.2 Frozen composition and order

The barrier and C-2 are **two independent authorities with two different subjects**, and F3 creates no
third:

```text
C-2      "is THIS commit exactly what THIS operation's Review authorized?"
barrier  "does the history this push would publish contain somebody else's unproven planning
          registration?"
```

```text
Frozen order, for every review-v1 Work publication:

  1  C-2(K) completes in full                                        §9 or §16
  2  the C-2 note for K is durable                                   §4.5
  3  the barrier is evaluated for K                                  publication.barrier_problem
  4  S-p is recorded                                                 only if 1-3 all passed
  5  at apply: the destination pin is re-resolved and compared as text
  6  at apply: C-2(K) is re-evaluated in full                        V-7
  7  at apply: the barrier is evaluated for K again
  8  the exact-commit push runs

Frozen non-substitution:
  a clear barrier is NEVER evidence of C-2
  a passed C-2 is NEVER evidence of a clear barrier
  neither is skipped because the other passed
  an operation refused at step 3 waits as a pending mutation with its domain effects applied,
    and continues when the barrier clears — it does not push, and it does not give up
```

### 12.3 The measured consequence a Work Review has on the barrier

This is a real, measured effect of F2's design on P2's barrier, and it is stated rather than discovered
later:

```text
The barrier's fast path is PATH-based (M-14):
    git rev-list --full-history -n 1 <C> -- .workline/review/candidate-snapshots/

A review-v1 Work Candidate snapshot is written to exactly that directory.

Therefore, from the first review-v1 Work Review onward, that Project's history permanently
touches the fast-path directory, and EVERY later push in it — including every legacy push —
leaves the fast path and takes the proof path, which requires the running Git to meet
P2_PUBLICATION_GIT_MIN (2.31.0).

registered_runs then SKIPS the Work Candidate, because is_planning_candidate tests the schema
and F2's Work Candidate schema is "review-work-candidate" (M-15). So a Work Run never begins the
barrier and never has to be proven by the committed planning proof. Only the CAPABILITY
requirement is real.
```

### 12.4 The frozen consequence for review-v1 Work entry

```text
A review-v1 Work START in a Project that has a remote MUST refuse at entry, before any Review
record is written and therefore before the Candidate snapshot can be committed, unless the
running Git version is known and meets P2_PUBLICATION_GIT_MIN.

  refusal code   review_git_unsupported   (the existing live code)
  position       at entry, BEFORE the Project execution lock, in the position the push
                 destination check already occupies. It reads no Project state, so it does not
                 wait for the lock; F1 §6.4's activation check keeps its own position, under
                 the lock and before the mutation is opened, and is unchanged.
  scope          only when the Project has a remote; a remote-less Project pushes nothing,
                 so no barrier is ever evaluated and no capability is needed
```

```text
F3 introduces NO new Git version threshold. It reuses P2_PUBLICATION_GIT_MIN, which rules/git
already owns, and refuses before the irreversible step rather than after it.
```

The reason the refusal must be at entry and not later: once the Candidate snapshot is committed, the
Project's history touches the fast-path directory forever. Refusing afterwards would leave a Project in
which the person's ordinary legacy pushes begin failing with `review_publication_barrier` for a capability
reason they did not choose and cannot undo.

### 12.5 What F3 does not do to the barrier

```text
it does not add a second publication authority
it does not let a Work publication bypass the barrier
it does not make a Work Candidate snapshot begin the barrier
it does not weaken the fast path, the Git threshold or the committed planning proof
it does not change what the barrier says about any planning Run
```

---

## 13. Terminal identifier reservation and the terminal stage (F3-D9)

### 13.1 One stage

```text
terminal stage contract "review-v1-work-terminal-v1"

The AuthorizedTransitionProjection and the terminal OperationMetadataProjection are applied in
EXACTLY ONE mutation stage, in this semantic effect order (R4 §6):

    1. AuthorizedTransitionProjection events
    2. OperationMetadataProjection Consumption immutable create
```

One stage is required, not merely convenient: R4 §3 permits a temporary one-sided terminal-event /
Consumption state **only** where a matching pending terminal mutation proves both were one durable stage and
the missing effect remains recoverable. Two stages would make a one-sided state that no pending intent
covers, which R4 §3 declares invalid.

### 13.2 Identifier reservation — everything durable before apply

```text
Reserved, durably, BEFORE the terminal stage is applied:

  <W>:lifecycle:<n>:event:0   ->  the work_target_removed event id
  <W>:lifecycle:<n>:event:1   ->  the work_completed event id

Reserved EARLIER — at or after the seal, and before S-c1 is recorded (§7.4.2):

  review-consumption:<receipt_id>  ->  the Consumption id

  This is earlier than R4 §6 requires and is strictly safe: the key is deterministic and
  replay-stable (R2 §2), so reserving it sooner cannot change what it yields. It is required
  sooner because the union preflight of §7.4.2 must know the Consumption's path before any
  result commit is made.

The first two keys are the live reservation keys START already uses (ops.event_effects), and
start._recorded_completion already proves a recorded completion by them. The third is R2 §2's
deterministic, replay-stable Consumption key, unchanged.
```

```text
All intended identifiers AND all intended content are durable before apply:
  both event records, complete, with their reserved ids, in order
  the Consumption's complete canonical text, at its exact canonical path
Nothing in the stage is computed at apply time. A callback-side or apply-time identity is never
adopted (R2 §2).
```

### 13.3 The frozen stage shape

```text
stage  <W>:lifecycle:<n>

  effect 0   append_event   work_target_removed   entity = <W>   id = reserved key :event:0
  effect 1   append_event   work_completed        entity = <W>   id = reserved key :event:1
  effect 2   create_file    .workline/review/consumptions/<consumption_id>.yaml

exactly three effects, exactly in that order, and no others.
```

The `work_completed` event carries the R4 §5 operation-contract metadata (`operation_contract: review-v1`,
`review_receipt_id`, `review_run_id`, `review_generation`). That carrier is **F1 Gate 1** and is not
implemented at this baseline; §21 records it as the prerequisite it is.

### 13.4 Before the stage is recorded

```text
gate.require_committable over the Consumption path        (an ignored Review path is a STOP)
the Consumption path is inside the mutation's WriteScope
C-2(K1) is complete for a result-bearing Candidate, and its note is durable
the seal prerequisites of F2 §15.3 still hold
no Consumption of this Receipt exists, and no Supersession or invalidation generation exists
```

### 13.5 Replay and idempotence

```text
Exact replay is idempotent: create_file writes the identical record or recognizes it as already
written, and an append_event whose id is already in the log classifies MATCHING when the record
is identical and MISMATCH when it is not (live, unchanged).

A conflicting tuple is never overwritten and never reconciled silently: it is
reconcile_required (R4 §1).

A replay never re-decides. The stage's effects are read from the record, in recorded order.
```

### 13.6 Review does not become lifecycle truth

```text
state.py derives lifecycle from canonical entities, relations and lifecycle events, and reads no
Review record (M-18). The Consumption in this stage is OperationMetadataProjection: it records
that an authorization was consumed. It does not make the Work complete — the work_completed event
does — and nothing that derives lifecycle reads it.
```

---

## 14. Candidate / Consumption `artifact_kind` consistency (F3-D10)

### 14.1 Two independent statements

```text
Candidate.projection.content.artifact_kind   what was REVIEWED   (F2 §6.1, §7.2)
Consumption.artifact_kind                    what was CONSUMED   (F1 §11.3, Gate 2)
```

```text
Neither is computed from the other. Neither is defaulted from the other. Neither is filled in by
reading the other. Both are READ and COMPARED.
```

### 14.2 The frozen agreement

```text
result-bearing
    Candidate.content.artifact_kind               == "result_commit"
    Consumption.artifact_kind                     == "result_commit"
    Consumption.authorized_result_commit_sha      == K1, a full object id
    and K1 is exactly the commit C-1 names and C-2(K1) proved

empty  (both cases of §6: no declared path, and all-inert)
    Candidate.content.artifact_kind               == "empty"
    Consumption.artifact_kind                     == "empty"
    Consumption.authorized_result_commit_sha      == null, present as null, never omitted
    and no result commit exists anywhere in this operation
```

```text
The Candidate's side of this agreement is determined by §6.7's discriminator — at least one
CHANGING entry, or none — and never by the length of `entries` or of result_paths. An all-inert
Candidate therefore agrees with an "empty" Consumption while still carrying every declared entry,
and a Candidate holding a changing entry can never agree with one.

A Candidate that says "empty" while holding a CHANGING entry, or says "result_commit" while every
entry is inert, is malformed: it fails closed here and at C-2(K2) item T8, and it is never
repaired by recomputing the field from the entries.
```

### 14.3 Where it is proven

```text
before the terminal stage is recorded   the Consumption's content is built and checked against
                                        the Candidate's artifact_kind; a disagreement means the
                                        stage is never recorded
at C-2(K2), item T8                     both records are read back from committed state at K2
                                        and compared
at the recorded-completion proof, §19   read back once more from the committed Review namespace
```

### 14.4 Fail-closed

```text
the two disagree                                        reconcile_required
artifact_kind is absent, null on a Work-kind
  Consumption, or not one of the two values             reconcile_required
artifact_kind is "result_commit" with a null
  authorized_result_commit_sha, or vice versa           reconcile_required
authorized_result_commit_sha names a commit this
  operation cannot show it created                      reconcile_required, review_commit_unowned
a reader derives one field from the other               a contract violation, not a repair
```

---

## 15. Normal terminal K2 lineage (F3-D11, part 1)

### 15.1 The frozen parent rule

```text
result-bearing
    parent(K2) == K1, exactly. One parent. Nothing between them.

empty
    parent(K2) is reached from declared_base.base_commit by own-Review commits only, under the
    identical lineage contract of §8.2 (L-1 ... L-5), because there is no K1 (§6.3).

both
    S-c2 is base-exact: HEAD is re-read immediately before `git add` and again immediately before
    `git commit`, and the commit is not made unless HEAD is still exactly parent(K2).
    HEAD is on the bound branch by its full ref name, and that branch holds K2.
    The generic "HEAD advanced independently" allowance is NOT available (L-5).
```

### 15.2 Why `parent(K2) == K1` is exact and not "K1 or a clean descendant"

The live planning metadata commit tolerates a clean descendant of Kp as Km's parent. F3 does not, for the
result-bearing case:

```text
Between K1 and K2 this operation records nothing that commits. Every Review record commit happens
before K1 (M-12), the terminal stage writes the event log and the Consumption which K2 itself
carries, and no other stage of this mutation commits in that window.

So any commit appearing between K1 and K2 is by definition foreign, and a foreign commit is an
invalidating HEAD advance (F2 §14.4, §8.3). Tolerating it would be exactly the "untouched paths
prove validity" inference F2 forbids.

parent(K2) == K1 is therefore not a simplification: it is the only value the topology can
produce, and requiring it exactly makes any other value detectable rather than tolerated.
```

### 15.3 Prohibited

```text
a K2 with more than one parent
a K2 made on a branch other than the bound one
a K2 made after HEAD moved, on the moved HEAD
a merge, a rebase, an amend, a reset or a force at any point
treating K2 as republishable under a different Receipt
```

---

## 16. Normal terminal K2 exact proof — C-2(K2) (F3-D11, part 2)

Contract `review-v1-work-proof-v1`. Every item is required, evaluated against the exact K2 of C-1.

```text
T1   OWNERSHIP
     The S-c2 effect is recorded applied with commit_id = K2, a commit this mutation made.
     Absent or unprovable -> review_commit_unowned. W1's rule applies identically.

T2   PERSISTENCE SEMANTICS
     The S-c2 payload names mode "review-v1-work-local-v1", and the Git persistence preflight of
     §7.3 passed for the terminal paths.

T3   LINEAGE
     §15.1 holds in full: the exact parent rule, one parent, base-exact, bound branch, branch
     holds K2.

T4   DELTA — exactly the terminal projection and nothing else
     commit_delta(parent(K2), K2) is EXACTLY:
         .workline/events/events.jsonl                          status M   mode 100644
         .workline/review/consumptions/<consumption_id>.yaml    status A   mode 100644
     and no other entry of any kind. In particular: no Candidate entry path, no other Review
     record, no Work file, no relation file, no Project file. A path allowlist is not a
     substitute for this enumeration.

T5   NO NEW REVIEWED-ARTIFACT DELTA
     Follows from T4 and is checked as its own item so it can fail by name: K2 introduces no
     result delta beyond K1 (result-bearing) or beyond the base (empty). For a result-bearing
     Candidate, tree_entries(K2, <the Candidate's entry paths>) equals tree_entries(K1, <same>)
     exactly, and K1 is unchanged in K2's history.

T6   THE AUTHORIZED TRANSITION, EXACTLY
     The event log at K2 is the event log at parent(K2) with exactly TWO records appended, in
     this order, and nothing else changed anywhere in the file:
         work_target_removed, entity = <W>, id = the reserved :event:0 id
         work_completed,      entity = <W>, id = the reserved :event:1 id
     The types and their order are exactly the AuthorizedTransitionProjection's
     (F2 §8.2), whose base_commit is declared_base.base_commit.
     Exactly two is reachable because S-c0 committed this Work's entry lifecycle events before
     the Candidate was frozen (§4.3). Any third appended record means an event this operation
     did not commit when it should have, or one it did not record at all: either way T6 fails
     and nothing is published.

T7   NO UNAUTHORIZED LIFECYCLE EVENT
     No other lifecycle event of any type, for this Work or any other entity, is added in that
     range. No event is modified or removed. No event of another entity appears. No terminal
     event other than the two authorized ones appears anywhere in the range.

T8   CONSUMPTION CONTENT
     The blob K2 adds at the Consumption path is byte-identical to the recorded create_file
     content; it reads back as a valid Consumption; and the artifact_kind agreement of §14.2
     holds, both fields read from committed state and compared.

T9   CONSUMPTION BINDING
     It repeats the Receipt's binding fields exactly (receipt_id, review_run_id,
     review_generation, review_kind, target_identity, operation_identity,
     authorized_candidate_hash); operation_mutation_id is this mutation;
     terminal_event_id is the reserved work_completed id; terminal_event_type is "work_completed";
     target_identity is this Work's id.

T10  UNIQUENESS AND TOTALITY
     Read at K2, from committed state:
         exactly one valid Consumption of this Receipt
         exactly one valid Consumption of this terminal_event_id
         the Consumption-by-Receipt and Consumption-by-terminal-event indexes build without
           conflict over the whole namespace
         the whole Review namespace reads canonically
     This is R4 §1 and R4 §3's totality for this operation, proven at the commit that creates it.

T11  AUTHORIZATION STILL CURRENT
     At K2: no Supersession of the Receipt, no invalidation generation of the Run, this Run's
     record paths hold exactly the bytes parent(K2) holds, the Context / Policy / Evidence
     identities are still the ones the gate bound, and the activation record digest still
     matches the one bound in the Candidate and the Context.

T12  RESULT BINDING
     result-bearing   K1 is in K2's history, exactly and unchanged, and
                      Consumption.authorized_result_commit_sha == K1.
     empty            no commit of this mutation carries a ReviewedArtifact delta, and
                      Consumption.authorized_result_commit_sha is null. For an ALL-INERT
                      Candidate this is proven positively rather than by absence: every declared
                      entry resolves in K2's tree to exactly the identity the Candidate records
                      for it (tree_entries over the declared paths), and the complete delta from
                      declared_base.base_commit to K2 holds no declared path at all.
```

---

## 17. Physical allocation of the three projections (F3-D12)

### 17.1 The frozen allocation

```text
Candidate            the ReviewedArtifactProjection, as record content, frozen BEFORE K1.
                     It is inside candidate_hash. It never contains K1 or K2.

Gate / Receipt       the AuthorizedTransitionProjection, bound into the gate generation and into
                     the Receipt's authorization scope. It is not a commit and not in the
                     Candidate.

K1                   the ReviewedArtifactProjection, and NOTHING ELSE.
                     Its PHYSICAL DELTA is exactly the Candidate's CHANGING entries (§9 W4);
                     its TREE holds every Candidate entry, inert ones included, at exactly the
                     identity the Candidate records (§9 W5). See §17.2.

K2                   the AuthorizedTransitionProjection, as the two appended lifecycle events,
                     PLUS the terminal OperationMetadataProjection, as the Consumption record.
                     Nothing else (§16 T4).
```

Two commits of the same operation are deliberately **outside** this allocation, and neither is a
projection of any kind:

```text
S-c0                 this Work's entry lifecycle events, committed BEFORE the Candidate is
                     frozen so that they are part of the base the artifact is measured against
                     rather than part of K2's delta (§4.3). They are not authorized by anything
                     — they precede the Review entirely — and they carry no Review record.

the generation        this Run's own canonical Review records, committed by the Review gate's own
commits              mutations before K1 (M-12). They are the gate's bookkeeping, they publish
                     nothing, and they are the only commits the K1 lineage rule tolerates (§8.2).
```

### 17.2 The exact deltas

A projection is what is reviewed. A delta is what a commit physically changes. For K1 the two are
deliberately **not** the same set, and conflating them freezes a rule no Git commit can satisfy:

```text
ReviewedArtifactProjection (K1)
    = EVERY declared Candidate entry, CHANGING and INERT alike.
      This is the Candidate's content, it is inside candidate_hash, and no entry is ever
      dropped from it (F2 §6.3).

K1 PHYSICAL DELTA
    = the Candidate's CHANGING entries EXACTLY — one delta entry per changing entry, with that
      entry's status, old_mode, new_mode, old_oid and new_oid, and nothing else.

INERT Candidate entries
    = ABSENT from commit_delta(parent(K1), K1), necessarily: an entry whose old identity equals
      its new identity changed nothing, so Git reports nothing for it.
      Their identity is proven at K1 by EXACT TREE CONTAINMENT instead (§9 item W5):
      tree_entries(K1, <path>) resolves to exactly the kind, mode and object id the Candidate
      records. Absence from the delta is never taken as absence from the artifact.

K2 PHYSICAL DELTA
    = { .workline/events/events.jsonl                       M
        .workline/review/consumptions/<consumption_id>.yaml A }
      and nothing else.
```

```text
A Candidate may legally hold BOTH changing and inert entries at once (case B of §21.4). Any rule
that said "K1's delta is one entry per Candidate entry" would be unsatisfiable for such a
Candidate, because Git cannot report a delta entry for a path that did not change. Every
statement of this contract now reads "CHANGING entries" where it means the physical delta, and
"every declared entry" where it means the projection.

Nothing is synthesized for an inert path to make it appear in a delta, and no inert entry is
dropped from the Candidate to make the two sets coincide.
```

### 17.3 K1 carries no Review bookkeeping — and R5 §8 is satisfied

R5 §8 says K1 contains "ReviewedArtifact plus required pre-consumption Review metadata". F3 evaluated
whether that requires K1's **delta** to add Review records, and the answer is no:

```text
At this baseline the Review gate commits its own records in its own generation mutations, before
K1 (M-12). The Candidate snapshot, the TaskInput, gates 1-3 and the Receipt are therefore already
in parent(K1)'s tree and are inherited by K1's tree unchanged.

"K1 contains X" is a statement about CONTAINMENT, and K1 contains all of it. C-2(K1) item W7
proves exactly that: every one of this Run's record paths is held at K1 with its canonical bytes.

Re-adding them in K1's delta is impossible anyway — a canonical Review record is immutable and is
only ever created once (R1 §8; create_file never updates one) — and would be a delta of zero.

This is a SPECIALIZATION of R5 §8, not an amendment. §22 row 2.
```

### 17.4 The boundaries that must stay unconfusable

```text
Receipt existence          !=  operation completion
Authorization              !=  Consumption
OperationMetadataProjection !=  lifecycle truth
ReviewedArtifactProjection  !=  AuthorizedTransitionProjection

Consumption occurs ONLY with the terminal transition, in the same stage (§13.1).
Lifecycle events remain the only lifecycle authority (M-18).
Nothing in state.py, ProjectView, validate_structure, startability or progression reads a Review
record, and the live pin proving it must keep holding (F2 §20.12).
```

---

## 18. Recursion cutoff boundary (F3-D13)

### 18.1 The two metadata-bearing commits, told apart

```text
                       ordinary Work terminal K2        Class-A metadata-only K2-A (R7 §6, F4)
parent                 K1, or the post-Review HEAD      exactly K1, always
                         for an empty Candidate
delta                  event log + Consumption          deterministic OperationMetadata only
lifecycle events       YES — the two authorized ones    NONE
AuthorizedTransition   YES                              NONE, explicitly (R7 §6)
authorized by          the Receipt this Run issued      R2, a REPLACEMENT Receipt issued after
                                                          a mismatch
consumes               that Receipt, in the same stage  nothing; R2 is not consumed by K2-A
why it exists          to complete the Work             to record R2 and the supersession around
                                                          an already-made K1
```

```text
The distinguishing fact is PRESENT-OR-ABSENT and needs no judgement: an ordinary terminal K2
carries lifecycle events; a Class-A metadata-only K2-A carries none. A reader tells them apart by
reading the delta, never by intent, naming or context.
```

### 18.2 The frozen cutoff rule

```text
A commit whose complete delta is confined to

    the AuthorizedTransitionProjection of an ALREADY-ISSUED Receipt
    plus that same Receipt's terminal OperationMetadataProjection

requires NO further Review, NO further Candidate, NO further Receipt and NO further Gate
generation. It is the authorized consumption of an authorization that already exists, not a new
reviewable artifact.
```

### 18.3 Why this is not a hole

```text
nothing in K2 is a product judgement. The event types and their order are exactly what the
  AuthorizedTransitionProjection names; the ids are reserved before apply; the Consumption is the
  exact record bound to the Receipt.

C-2(K2) proves the delta is EXACTLY that and nothing more (T4, T5, T6, T7). A K2 that smuggled in
  a ReviewedArtifact change would fail T4 and T5 and would never be published.

the cutoff cannot chain. K2 is the last commit of the operation; nothing is committed after it,
  so there is no third commit to require a cutoff of its own.
```

R7 §6 already states the same cutoff for K2-A ("K2 does not require another Review Receipt … This is the
recursion cutoff"). F3 states the ordinary-K2 form of it and the rule that tells the two apart — nothing
more.

### 18.4 The F4 boundary here

```text
F3 freezes   that an ordinary terminal K2 triggers no Review, and how a reader distinguishes it
             from a Class-A metadata-only K2-A.

F4 owns      Class A eligibility, adopt_existing_local_commit, freezing K1 as a replacement
             Candidate C2, the replacement Receipt R2, the supersession, K2-A's own proof, the
             remote-publication precondition for an adopted K1, and Class B / Class C entirely.

F3 does NOT define any of them, and nothing in F3 may be read as permitting adoption.
```

---

## 19. Recorded completion proof (F3-D14)

### 19.1 When START may return `completed`

```text
START returns "completed" for a review-v1 Work only when ALL of the following are shown, in
committed state, after the terminal publication (or, with no remote, after K2):

  P-1  the terminal stage is recorded AND applied: both events are in the event log under their
       reserved ids, and the Consumption record exists at its canonical path

  P-2  C-2(K2) passed for exactly the K2 this mutation made, re-evaluated at this point

  P-3  with a remote: S-p2 is applied — the exact K2 reached the pinned destination, or was
       positively classified as already published by the exact-commit classification
       (`=`, or `!` with a destination read that holds K2). Unreadable, changed while being read
       or unanswerable is a STOP and is never taken for published.

  P-4  the live lifecycle postcheck passes:
           ProjectView.load(store).work_state(<W>).state == COMPLETED
       derived from canonical entities, relations and events, reading no Review record

  P-5  the Review consistency postcheck passes, read back from committed state at K2:
           exactly one valid Consumption of this Receipt
           exactly one valid Consumption of this terminal_event_id
           the Candidate / Consumption artifact_kind agreement of §14.2
           no Supersession of the Receipt and no invalidation generation of the Run
           the Review namespace reads canonically

  P-6  the working tree holds no uncommitted change at any path this operation owns

then, and only then: mutation.complete(), and START returns "completed".
```

### 19.2 What is explicitly insufficient

```text
a Receipt exists                          insufficient — a Receipt authorizes, it does not complete
K2 exists                                 insufficient — existence is not proof
K2 was pushed                             insufficient — publication is not proof (R5 §12.4)
the remote holds K2                       insufficient — the same
the Consumption exists                    insufficient — OperationMetadata is never lifecycle truth
the event log holds work_completed        necessary but not sufficient on its own: P-2, P-3 and
                                          P-5 are also required
```

### 19.3 Review records never replace lifecycle state

```text
P-4 is derived exclusively from canonical entities, relations and lifecycle events. It is the
live postcheck, unchanged. P-5 is an ADDITIONAL operation-consistency check that can only refuse;
it can never make a Work complete that P-4 does not, and it is never consulted to decide
lifecycle.
```

### 19.4 Never left open

```text
A review-v1 Work whose terminal events are applied but whose K2 is not committed, or whose K2 is
committed but not proven, or not published where a remote exists, is NEVER reported completed and
the mutation is NEVER closed. The pending mutation resumes from the earliest unsatisfied
checkpoint (§5.3), exactly as the live Terminal finalization rule already requires.
```

---

## 20. No-remote topology (F3-D15)

### 20.1 What is omitted

```text
S-p1 is not recorded.
S-p2 is not recorded.
The mutation holds EXACTLY ZERO git_push effects (§11.3.1), and a push recorded anyway is a
  refusal rather than an anomaly.
The publication barrier is not evaluated, because nothing is published.
The publication capability check of §12.4 does not apply.
The transform-configuration entry refusal of §7.4 still applies: it is about what Git stores
  locally, not about publication.
```

### 20.2 What is NOT omitted

```text
the commit-only stages and the commit primitive          §7
K1 lineage and base-exactness                            §8
C-2(K1), items W1 ... W12, in full                       §9
the durable proof notes                                  §4.5
terminal identifier reservation and the terminal stage   §13
the artifact_kind consistency proof                      §14
K2 lineage and C-2(K2), items T1 ... T12, in full        §16
the three-projection allocation and its exact deltas     §17
the recorded-completion proof, minus P-3 only            §19
every fail-closed rule                                   §21.3
```

### 20.3 No collapse into legacy

```text
"No remote" is the absence of a PUBLICATION, never the absence of a PROOF.

A remote-less review-v1 Work MUST NOT use the combined commit+push primitive, MUST NOT record a
stage holding a git_commit and a git_push together, and MUST NOT skip any C-2 item. The split is
the shape of the contract, not an artefact of pushing.

The proof notes are recorded in the no-remote case exactly as with a remote, so that recovery is
uniform and so that a Project that later gains a remote has the same durable record shape.
```

`rules/git` already states that a remote-less Project's local commit suffices, and P1 R5 §7 is a push-only
primitive that simply does not run. Neither says the proof is optional, and F3 says explicitly that it is not.

---

## 21. Implementation prerequisites and fail-closed rules

### 21.1 Measured, bounded implementation prerequisites

F3 authorizes none of these. They are named so the work is a known quantity rather than a discovery.

```text
IP-1  Effect.git_commit must accept a CLOSED SET of two persistence modes rather than one
      (_validate_planning_commit, mutation.py:1094-1110), and apply_effect must dispatch
      "review-v1-work-local-v1" to the contained commit primitive (mutation.py:2484). An unknown
      mode must stay a ValidationError. (M-5)

IP-2  _publication_contract must gain the "work" branch of §11.1, and _recorded_publication must
      route it to the Work validator of §11.2. current-combined, planning and generation must be
      untouched. (M-4)

IP-3  start._recorded_completion must recognize the review-v1 terminal stage's exact three-effect
      shape — two append_event effects in order under the reserved ids, followed by exactly one
      create_file at this Run's Consumption path — AND must keep accepting the legacy two-effect
      shape unchanged. (M-17)

IP-4  F1 Gate 1, the Event metadata carrier, must land before any post-activation review-v1
      terminal event exists: the Event model and reader, Effect.append_event, and the classify
      comparison. The terminal stage of §13.3 cannot be applied without it.

IP-5  F1 Gate 2, the Consumption version 1 artifact_kind repair, must land: §14 and §16 T8/T9
      are written against the repaired field set. (M-16)

IP-6  The isolated verification materialization primitive of F2 §13.4 V-2 does not exist; no live
      primitive exports a Work result tree. This is F2's named gap and F3 does not close it.

IP-7  F1 Gate 3, the activation producer, still fails closed until IP-4 and IP-5 both land.
```

```text
Freezing F3 authorizes NO gate. Nothing in this document permits Gate 1, Gate 2 or Gate 3 to
begin.
```

### 21.2 What F3 requires that live code already provides

```text
the contained commit primitive, hooks and signing contained          gitcmd.contained_add/commit
base-exact commits, with HEAD re-read immediately before the commit  _make_planning_commit
exact-commit publication, never forced, never a branch tip           gitcmd._exact_refspec
complete tree-entry delta with mode and object identity              gitcmd.commit_delta
tree entry resolution with mode, type and oid                        gitcmd.tree_entries
object identity of bytes, writing nothing                            gitcmd.hash_blob
width-agnostic object ids, SHA-1 and SHA-256                         _FULL_ID, zero_object_id
the commit-identity record and its ownership rule                    _make_commit / commit_id
the split-publication stage machinery                                review_commit_effect,
                                                                     review_publication_effect
the committed Review reader at an exact commit                       CommittedReviewStore
the publication barrier, at record time and at apply time            publication.require_barrier_clear
the transform preflight                                              require_no_planning_transform
deterministic id reservation                                         Mutation.reserve_id
```

### 21.3 Fail-closed rules

```text
FC-1   No push is ever recorded or applied before the C-2 of the exact commit it publishes is
       complete, and C-2 is re-evaluated before both.

FC-2   Publication is exact-SHA only: `<commit id>:refs/heads/<full branch>`, never forced, never
       force-with-lease, never a branch tip, never a pattern.

FC-3   A commit this operation cannot positively show it created is never K, never backfilled,
       never adopted and never published.

FC-4   Unknown, partial or contradictory contract metadata fails closed and never selects the
       weaker contract.

FC-5   A question Git or the canonical reader cannot answer is a refusal. `unknown` is never
       `proven`, and absence of discovered change is never proof of invariance.

FC-6   No amend, reset, rebase, force push, squash, merge or clean recovery is introduced
       anywhere by this contract.

FC-7   No path allowlist substitutes for an exact committed-tree proof.

FC-8   No synthetic, placeholder, empty-string or all-zero commit identity is written anywhere,
       for any reason.

FC-9   A Review record is never rewritten; an immutable create that finds different bytes at its
       path is reconcile_required.

FC-10  A transform that would make committed bytes differ from the Candidate's object identity
       fails closed before any commit is made, and is never disabled to obtain a pass.

FC-11  The publication barrier is never bypassed, weakened or substituted by C-2, and C-2 is
       never substituted by the barrier.

FC-12  A one-sided terminal-event / Consumption state exists only where the matching pending
       terminal mutation proves both were one durable stage and the missing effect is still
       recoverable. Otherwise it is invalid and reconciles.

FC-13  START never returns completed, and never closes its mutation, with an uncommitted,
       unproven or (where a remote exists) unpublished terminal commit.
```

---

### 21.4 Case matrix — every reachable shape, proven end to end

Each case is traced through the whole topology. `n/a` means the step does not exist for that case, not that
it was skipped. Every case has a lawful continuation; none traps.

```text
A. RESULT-BEARING, every entry changing
   Candidate        artifact_kind "result_commit"; entries = the changing entries
   material         one payload per file/symlink entry (F2 §9.4)
   K1               EXISTS
   K1 delta         the changing entries exactly (= all entries here)          §9 W4
   C-2(K1)          W1 ... W12 in full
   pushes           2 with a remote, 0 without                                 §11.3.1
   terminal stage   two events + Consumption, one stage                        §13.3
   K2 parent        K1, exactly                                                §15.1
   C-2(K2)          T1 ... T12; T12 result-bearing branch
   Consumption      artifact_kind "result_commit", authorized_result_commit_sha = K1
   completion       P-1 ... P-6                                                §19
   trap             none

B. RESULT-BEARING, changing and inert MIXED                      <- the R8 case
   Candidate        artifact_kind "result_commit"; entries = changing U inert, all kept
   material         one payload per file/symlink entry, INERT ONES INCLUDED (F2 §9.4.1)
   K1               EXISTS
   K1 delta         the CHANGING entries exactly. The inert entries are ABSENT from the delta
                    by construction and are proven at K1 by exact tree containment (W5).
                    This is the contradiction the second review found; §17.2 now states it once.
   C-2(K1)          W1 ... W12, with W4 splitting changing from inert
   pushes           2 / 0 as case A
   K2 parent        K1
   Consumption      "result_commit", sha = K1
   trap             none

C. ALL-INERT, files
   Candidate        artifact_kind "empty"; entries = every declared inert entry, kept   §6.7
   material         one payload per inert file entry, REQUIRED and cross-checked       §6.7, A-3
   K1               DOES NOT EXIST — no commit can be made from an empty delta          §6.6
   K1 delta         n/a
   C-2(K1)          n/a
   pushes           1 with a remote (K2 only), 0 without                                §11.3.1
   terminal stage   as case A
   K2 parent        reached from declared_base.base_commit by own-Review commits only    §6.3
   C-2(K2)          T1 ... T12; T12 empty branch, proven positively over the declared paths
   Consumption      artifact_kind "empty", authorized_result_commit_sha = null
   completion       P-1 ... P-6 with P-3 applying to K2 only
   trap             none

D. ALL-INERT, symlinks
   as case C, with the payload carrying the exact link-target bytes Git stores as the blob;
   never the dereferenced target's contents (F2 §9.4.1, §6.7)

E. ALL-INERT, gitlinks
   as case C, except: NO payload for a gitlink entry. The entry itself is the material —
   path + new_kind gitlink + new_mode 160000 + new_oid (F2 §9.4.1). A payload present for a
   gitlink is reconcile_required.

F. NO DECLARED PATHS
   Candidate        artifact_kind "empty"; entries = []; F2 §7.2 unchanged for this case
   material         payloads = []                                              F2 §7.2, unchanged
   K1               DOES NOT EXIST
   everything else  as case C
   trap             none

G. REMOTE + RESULT-BEARING      2 pushes: S-p1(K1), S-p2(K2)                    §11.3.1
H. REMOTE + NO-K1               1 push: S-p2(K2). A result publication is refused: there is no
                                K1 for one to name.                             §11.2 V-6
I. NO REMOTE + RESULT-BEARING   0 pushes. Every proof, both C-2s and the recorded-completion
                                proof minus P-3 all still run.                  §20
J. NO REMOTE + NO-K1            0 pushes. Same.                                 §20

K. OPERATION-OWNED .gitattributes CHANGE                         <- the R9 case
   classification   a legitimate Work result, NOT malformed                     §7.4.1
   Candidate        .gitattributes is an ordinary file entry, exactly as F2 §6.4 says
                    .gitmodules is
   K.1  the new transform affects NOTHING this operation commits
        -> proceeds normally, as case A or B. The change is committed as an ordinary result and
           later operations see the new semantics.                     LAWFUL, no refusal
   K.2  the new transform affects the TERMINAL paths
        -> caught by the union preflight BEFORE S-c1 (§7.4.2). No K1 exists, nothing is
           published, nothing is stranded.                            refuse, pre-physical
   K.3  the new transform covers this operation's OWN result paths
        -> refused before S-c1 at the named expressibility boundary of F2 §6.3 (§7.4.3).
           Bounded, stated, pre-physical. Not malformed, not invalid.  refuse, pre-physical
   trap             none: K.1 completes, K.2 and K.3 refuse before any commit exists

L. EXTERNAL .gitattributes / config DRIFT
   classification   foreign interference, not this operation's product          §7.4.1
   disposition      the per-stage preflight refuses before the affected commit; reconcile.
                    What recovery is attempted is F4's (§25).
   trap             none created by F3

M. RUNTIME MUTATION RECORD SURVIVES A CRASH
   layers           both present (§10.2.1)
   disposition      resume at the earliest unsatisfied checkpoint (§5.3) and RE-EXECUTE the
                    proof in full. A prior pass never carries (§10.2.2).
   trap             none

N. RUNTIME MUTATION RECORD IS LOST
   layers           layer 1 present, layer 2 (C-1 / ownership) GONE              §10.2.1
   disposition      ownership cannot be reconstructed; no K is inferred from a branch tip,
                    content or message; fail closed under R5 §3.5 — reconcile, or a new
                    Candidate against the actual committed state.
   trap             none created by F3: this is P1's frozen answer, not a new one
```

```text
Architecture blocker: NONE. Every case above has a lawful continuation, and the two that refuse
(K.2, K.3) refuse before any commit, any event and any publication.
```

## 22. Consistency audit against P1 / P2 / F1 / F2

Every point at which F3 touches an earlier freeze, classified.

```text
A  no conflict; specialization only
B  stale wording, already superseded
C  true conflict requiring a new forward amendment
```

```text
 1  R5 §1 / §1.1 / §1.2  the K1 -> proof -> push -> terminal -> K2 -> proof -> push topology,
    the C-1/C-2/C-3 checkpoints and the S-c / C-2 / S-p split.
    F3 implements it exactly and adds the lineage rule R5 left open.                          A

 2  R5 §8  "K1 contains ReviewedArtifact plus required pre-consumption Review metadata".
    F3 reads "contains" as tree containment, which K1 satisfies because the gate committed
    those records before K1 (M-12), and proves it as C-2(K1) item W7. Re-adding them in K1's
    delta is impossible: a canonical Review record is immutable and created once. §17.3.       A

 3  F2 §14.4 / §16.1  "HEAD advances -> a new Candidate".
    §16.1's invalidation row states that consequence flatly and without qualification, and F3
    admits a class of advances it does not cover — this Run's own generation commits, which must
    be able to happen or no Review could ever seal. §14.4's own prose is about reuse of a PRIOR
    Review, which is why the first draft called this a specialization; but a rule that carves an
    exception out of a flat invalidation row changes that row. FORWARD AMENDMENT A-2 (§1.5).
    F3 remains STRICTER than the live planning rule in every other respect: it tolerates no
    foreign commit at all, where planning tolerates one that touches no owned path. §8.2 ... §8.4.
                                                                                               C

 4  R4 §6  terminal stage ordering: events, then the Consumption immutable create, all durable
    before apply. F3 freezes the physical form of exactly that. §13.                           A

 5  R4 §1 / §3  one Receipt -> at most one valid Consumption; one terminal_event_id -> at most
    one; exact replay idempotent; conflict reconciles; totality after activation.
    F3 proves all of it at C-2(K2) T10 and again at the recorded-completion proof P-5. §16, §19. A

 6  R7 §10.1  "no live helper supplies mode or object identity — both commit_changes and the
    ls-tree helper use --name-only", recorded at baseline e32a741.
    Live code at fa6b28b provides gitcmd.commit_delta (mode, blob, status) and
    gitcmd.tree_entries (mode, type, oid) (M-9). The statement is a stale implementation
    binding, superseded by landed implementation rather than by an amendment; it is not a
    normative rule, and R7's safety condition is unchanged and satisfied.                      B

 7  R7 §6  the Class-A metadata-only K2's invariants.
    F3 neither changes nor applies them; it freezes the distinguishing rule that keeps an
    ordinary terminal K2 out of that path, and defers Class A entirely. §18.                   A

 8  R5 §12.3 / §12.3.1 / §12.3.2  the discriminator and its precedence.
    F3 adds one branch to a selection that already fails closed on everything else, and repeats
    the never-inferred-from-shape rule verbatim. §11.1.                                        A

 9  R5 §12.2  review-v1-split does not use a same-stage pair and may not push through one.
    F3's V-1 refuses exactly that for the Work path. §11.2.                                    A

10  R5 §4 / §5 / §6  the external-process surface, signing disabled, filters not simply
    disabled. F3 splits the surface into mechanically-denied and proven-absent and fails closed
    on a filter rather than disabling it. §7.2, §7.3.                                          A

11  F1-D2  both markers written together at mutation open, before any Git stage.
    F3 consumes them and changes neither. §11.1.                                               A

12  F1 §11.3 / F1-D10  artifact_kind, and no K1 for an empty artifact.
    F3 freezes the physical topology of exactly that case and creates no commit. §6, §14.      A

13  F2 §6.3 / §6.4  the Candidate entry shape and every object kind.
    C-2(K1) W4 and W5 prove against exactly those fields, including 160000 by referenced commit
    OID. §9.                                                                                   A

14  F2 §10.3  git_persistence identity bound in the Context; "its use at commit time is F3".
    F3 uses it at commit time and adds no Context field. §7.1.                                 A

15  F2 §13.4 V-2  the verification workspace is materialized from base + snapshot material and
    NEVER from a future K1. F3 keeps K1 strictly after the Review and never makes verification
    depend on it. §5.1, §5.2 R-2.                                                              A

16  P2 publication barrier.  Preserved exactly, composed but never merged with C-2, and its
    measured capability consequence is stated with an entry-time refusal that fires before the
    irreversible step. §12.                                                                    A

17  skills/start Terminal finalization.  F3's sequence is the live sequence with the pushes
    split out and the Consumption added to the terminal stage; the resume reader's stage-name
    shape is preserved deliberately (§4.3). The Skill is not edited; the statement is listed
    for activation in §23.                                                                     A

18  registry.md Commit / push, Push destination, Git versions.  F3 introduces no new threshold,
    no new refspec form, no new adoption rule and no new destination behaviour. It adds one
    entry-time capability refusal using the existing threshold and the existing code. §12.4.   A

19  F2 §5.3  "base_commit is HEAD at the moment the completion is decided, which is the same
    commit F3 will later require as K1's parent for a result-bearing Work."
    BOTH clauses are superseded. The timing clause is refixed to the post-S-c0, pre-Candidate
    base; the parentage clause names something F3 cannot require, because the gate's own
    generation commits necessarily lie between. §5.3 does not leave K1's parent open for F3 to
    fill in — it states what F3 will require — so this is not a timing specialization, which is
    what the first draft wrongly called it. FORWARD AMENDMENT A-1 (§1.5). §4.3, §8.1.          C

21  F2 §7.1 / §7.2 / §7.3  the result-bearing / empty Candidate boundary, "Exactly when
    result_paths and deleted_paths are both empty", and "refused if any declared path exists".
    An all-inert Candidate — declared paths, no changing entry — is an ordinary correct outcome
    that those sentences classify as result-bearing and that therefore demands a K1 which
    `git commit --only` cannot make. The discriminator moves to the complete owned tree delta.
    FORWARD AMENDMENT A-3 (§1.5). §6.6, §6.7.                                                  C

20  Live START's combined Git stages for a derivation, a move or a human-NG move
    (start.py:572-579).  In a review-v1 Work mutation every Git stage is commit-only except the
    two publication stages, because a combined stage is a push in the same apply pass as its
    commit and no C-2 exists for those commits. They reach the destination as the history of the
    next authorized push, which is the live frozen meaning of an exact-commit push. Legacy START
    keeps its combined stages exactly. §4.3.                                                   A
```

```text
Forward amendment required: YES

Three, all to landed F2, all declared in full in §1.5:
    A-1  F2 §5.3          base_commit's timing, and that it is K1's parent        row 19
    A-2  F2 §14.4, §16.1  the unqualified "every HEAD advance" consequence        row 3
    A-3  F2 §7.1/7.2/7.3  the result-bearing / no-K1 discriminator                row 21

No P1, P2 or P3 F1 statement is amended.
No historical P1, P2, F1 or F2 document is edited by this contract.
```

---

## 23. Canonical authority activation plan (F3's own statements)

No canonical authority is edited by this document. When F3's implementation lands, these statements need
activation. Labels `PB-*`, `PR-*` and `TM-*` are statements of **this** contract, not P1 freeze documents.

### 23.1 `rules/git` (inside `registry.md`)

```text
PB-1  the review-v1 WORK publication rule: a mutation whose durable invocation names
      operation "start", review_contract "review-v1-work-v1" and publication_contract
      "review-v1-split-v1" publishes only by push-only stages, each naming the exact commit one
      of its two proof notes names, recorded only after that commit's C-2 passed
PB-2  current-combined, planning and generation rules are unchanged by PB-1
PB-3  the commit primitive identity "review-v1-work-local-v1": no hook, no signing, no
      filesystem monitor, no background maintenance; a transform on a committed path is
      review_git_transform, never disabled to obtain a pass
PB-4  base-exact commits: K1 and K2 are made only while HEAD is still exactly their recorded
      parent, and the independent-HEAD-advance allowance does not apply to them
PB-5  a review-v1 Work START in a Project with a remote requires the running Git to meet
      P2_PUBLICATION_GIT_MIN, refused at entry with review_git_unsupported, because its
      Candidate snapshot permanently takes that Project's pushes off the barrier's fast path
PB-6  the Git persistence preflight runs immediately before EVERY commit stage of a review-v1
      Work mutation, for exactly that stage's path set, and a pass never carries between
      stages (§7.3)
PB-7  a review-v1 Work START is refused at entry, before the lock, when the Project's
      effective configuration or attributes define any filter, ident or working-tree-encoding
      that could apply to a working-tree path (review_git_transform, §7.4)
PB-8  the push cardinality of a review-v1 Work mutation is 2, 1 or 0 by case, computed from
      the destination pin and the independently agreed artifact_kind, never from stage shape
      (§11.3.1)
```

### 23.2 `skills/start`

```text
PR-1  the review-v1 Work completion topology of §5.1 and §6.2, and its durable-intent boundaries
PR-2  the split stages: <W>:entry / <W>:results / <W>:results-publication / <W>:lifecycle /
      <W>:finalize / <W>:finalize-publication; that a commit and a push never share a stage;
      that a review-v1 Work mutation holds at most two pushes, both publications; and that every
      other Git stage of the Work cycle is commit-only and reaches the destination only as the
      proven history of one of those two
PR-3  the terminal stage of §13.3 and its reservation keys
PR-4  the recorded-completion proof of §19, and that Receipt existence, K2 existence and remote
      publication are each insufficient
PR-5  the no-remote topology of §20, and that it never collapses into the combined legacy shape
PR-6  the resume points of §5.3, and that a resume re-derives and never re-decides
PR-7  that a pending review-v1 mutation never downgrades to legacy, and that legacy
      availability is a property of a separate later invocation (§7.4)
```

### 23.3 `skills/review`

```text
TM-1  the proof contract identity "review-v1-work-proof-v1" and that C-2 is a re-executable
      proof over immutable inputs, never a stored verdict
TM-2  C-2(K1) items W1 ... W12 and C-2(K2) items T1 ... T12
TM-3  the three-projection physical allocation of §17 and its exact deltas
TM-4  the artifact_kind consistency rule of §14: both read, compared, neither derived
TM-5  the recursion cutoff of §18 and the ordinary-K2 / Class-A-K2 distinction
TM-6  that a proof note is a recovery pointer and never a proof result, and that a completed
      C-2 is a durable checkpoint rather than timeless validity: current validity is
      re-derived at every boundary and a later canonical fact makes a passed proof stale
      (§10.2)
TM-7  the no-K1 discriminator of §6.7: artifact_kind is decided by whether any Candidate entry
      is changing, never by the emptiness of entries or of result_paths
TM-8  the three forward amendments to landed F2 (§1.5), which a reader of F2 alone cannot
      discover from F2
```

### 23.4 `registry.md` routing

```text
TM-9  Work publication and Work commit-proof statements route to skills/review for record
      meaning and to skills/start for operation flow; the Mutation Controller enforces the
      publication contract mechanically from the durable invocation alone
```

### 23.5 Statements that must NOT move into `skills/review`

```text
Review opens no mutation, holds no lock, makes no commit, records no push and finalizes no Git.
The operation owner is START, before F3 and after it. Review authorizes; it never progresses.
```

---

## 24. F3 decision table

```text
F3-D1   Work local persistence      FROZEN   "review-v1-work-local-v1": the contained commit
                                             primitive, hooks and signing mechanically denied,
                                             filters proven absent and never disabled, distinct
                                             identity from the planning primitive. The preflight
                                             binds EVERY commit stage of the mutation, and S-c1's
                                             binding run is the one after the Review.  §7.1-§7.4

F3-D2   K1 lineage                  FROZEN   parent(K1) is reached from
                                             declared_base.base_commit by OWN-REVIEW COMMITS
                                             ONLY; base-exact; no independent-advance
                                             allowance. The naive parent == base_commit is
                                             impossible because the gate commits its own
                                             records before the reviewer launches.        §8

F3-D3   result-bearing topology     FROZEN   the full ordered sequence with explicit
                                             durable-intent boundaries; the entry events
                                             committed before the Candidate is frozen;
                                             Candidate before K1; no terminal event before
                                             C-2(K1).                              §5, §4.3

F3-D4   no-K1 topology              FROZEN   ONE kind and one topology for both cases — no
                                             declared path, and all-inert. The discriminator is
                                             the complete owned tree delta, not the declared path
                                             set (forward amendment A-3). No K1 of any kind; K2
                                             takes the identical lineage rule.    §6, §6.6, §6.7

F3-D5   K1 exact proof              FROZEN   W1 ... W12, exact-K-bound, complete tree-entry
                                             delta, no path allowlist.                     §9

F3-D6   C-2 durability              FROZEN   Option A: deterministic re-executable proof over
                                             durable inputs; runtime state caches C-1 and a
                                             recovery pointer only; durable checkpoint completion
                                             is NOT timeless validity — a later canonical fact
                                             makes a passed proof stale and that fails closed;
                                             runtime loss resolves as no-owned-K, never as
                                             branch-tip inference.                        §10

F3-D7   split publication validator FROZEN   "review-v1-work-publication-v1": V-1 ... V-8 plus
                                             V-6a, push-only stages, exactly one proof note
                                             naming the pushed commit, contract AND case from
                                             durable metadata alone; cardinality 2 / 1 / 0 by
                                             case (§11.3.1); every other Git stage commit-only.
                                                                                 §11, §4.3

F3-D8   P2 barrier composition      FROZEN   two independent authorities, ordered, neither
                                             substituting for the other; the fast-path
                                             consequence measured and answered by an
                                             entry-time capability refusal.               §12

F3-D9   terminal stage              FROZEN   one stage: two events then the Consumption
                                             create; every id and every byte durable before
                                             apply; exact replay idempotent.              §13

F3-D10  artifact_kind consistency   FROZEN   two independent statements, both read, compared at
                                             three points, neither ever derived.          §14

F3-D11  normal K2 proof             FROZEN   parent(K2) == K1 exactly (result-bearing) or the
                                             own-Review lineage (empty); T1 ... T12 including
                                             the exact two-entry delta.                §15, §16

F3-D12  three-projection allocation FROZEN   K1 = ReviewedArtifact alone; K2 = AuthorizedTransition
                                             + terminal OperationMetadata; Candidate and gate
                                             hold the other two. A projection is NOT a delta:
                                             K1's delta is the CHANGING entries, its tree holds
                                             every declared entry.               §17, §17.2

F3-D13  recursion cutoff            FROZEN   an ordinary terminal K2 carries lifecycle events
                                             and a Class-A K2-A carries none; a delta confined
                                             to an already-issued Receipt's transition and its
                                             own Consumption triggers no Review.          §18

F3-D14  recorded completion         FROZEN   P-1 ... P-6; Receipt, K2 and publication each
                                             insufficient; lifecycle stays state.py's.    §19

F3-D15  no-remote topology          FROZEN   push stages omitted, every proof retained, no
                                             collapse into the combined legacy shape.     §20
```

```text
BLOCKED: none.
```

---

## 25. Deferred F4 / P4 and later boundaries

### 25.1 F4 (still inside P3)

```text
Class A / B / C mismatch behaviour in full
adopt_existing_local_commit, and freezing an adopted K1 as a replacement Candidate
the replacement Receipt R2, the supersession, and the Class-A metadata-only K2-A's own proof
the remote-publication precondition for an adopted K1
stale-generation mutation mechanics and stale-generation blocking
the repair action matrix
the full interruption matrix, and what happens after an invalidation, mismatch or interruption
```

F3 defines invariants F4 must respect — the exact-K proof, the no-push-before-proof rule, the exact-SHA
publication, the barrier composition, the cutoff distinction and the recorded-completion proof — and absorbs
none of F4's decisions.

### 25.2 P4 and later

```text
the Repair Loop and ReviewRepairRequest
dependency-class completeness expansion, coverage contracts and completeness proof claims
isolated Integration and the Integration side-effect contract
enabling the positive HEAD-reuse branch once completeness can actually be proven
full durable Review history, causality and recurrence (P5)
project-local or global adaptive Policy (P6)
```

```text
F3 does not pull any of these forward. In particular it does not make Work Evidence completeness
provable, does not enable the positive reuse branch, and does not delete the fast-path
architecture that is unreachable in v1.
```

---

## 26. Critical invariants

Stop conditions. An implementation that violates any of them is not implementing this contract.

```text
 1. No push is recorded or applied before the C-2 of the exact commit it publishes is complete,
    and C-2 is re-evaluated again before the push is applied.

 2. C-2 is never inferred from a push, a remote, a branch tip, a successful transport or the
    existence of a proof note.

 3. Publication is exact-SHA only, never forced, never a branch tip, never a pattern.

 4. A Work whose complete owned tree delta is empty has no K1 — whether it declared no path at
    all or declared paths it did not change: no physical commit, no synthetic commit, no
    --allow-empty commit, no placeholder identity, anywhere. There is no third artifact_kind and
    no "result_commit without a commit".

 5. The Candidate is frozen before K1 and K1 is never moved earlier to satisfy any requirement.

 6. K1 carries the ReviewedArtifactProjection and nothing else; K2 carries the
    AuthorizedTransitionProjection and the terminal OperationMetadataProjection and nothing else.
    A projection is not a delta: K1's physical delta is the Candidate's CHANGING entries exactly,
    while its tree holds every declared entry — inert ones included — at exactly the identity the
    Candidate records. Both are proven by complete tree-entry enumeration and exact tree
    containment, never by a path allowlist, and nothing is synthesized to make an inert entry
    appear in a delta.

 7. Terminal events are never carried by K1, and the terminal transition and its Consumption are
    applied in one stage with every identifier and every byte durable before apply.

 8. OperationMetadataProjection is never lifecycle truth, state.py never reads a Review record,
    and the live pin proving it keeps holding.

 9. No HEAD advance is tolerated except this Run's own canonical Review record commits, each
    proven by its complete delta; every foreign commit requires a new Candidate.

10. A commit this operation cannot positively show it created is never K, never adopted, never
    backfilled and never published — however exactly its content, tree, parent, branch or message
    match.

11. The P2 cross-operation publication barrier remains active for every push, is never bypassed
    by a review-v1 Work publication, and is never substituted for C-2 nor C-2 for it.

12. The ordinary terminal K2 is never confused with the Class-A metadata-only K2-A, and neither
    creates a new Review requirement.

13. The Candidate's and the Consumption's artifact_kind are independent statements, both read and
    compared, never derived one from the other.

14. START never reports completed, and never closes its mutation, without the recorded-completion
    proof of §19 — Receipt existence, K2 existence and remote publication are each insufficient.

15. "No remote" removes the publication, never the proof, and never permits the combined legacy
    stage.

16. Unknown, partial or contradictory contract metadata fails closed and never degrades to legacy
    or to a weaker contract; `unknown` is never `proven`.

17. Legacy START behaves exactly as it does at this baseline unless review-v1 is explicitly
    selected by the caller.

18. F3 defines no Class A/B/C behaviour, no adoption, no stale-generation mechanics and no
    recovery matrix.

19. A review-v1 Work mutation holds exactly the number of pushes its case requires — 2 with a
    remote and a result commit, 1 with a remote and none, 0 without a remote — computed from the
    destination pin and the independently agreed artifact_kind, never from stage shape. Every
    other Git stage it records is commit-only, and no commit of that mutation reaches the
    destination except as the proven history of a published K.

20. The Git persistence preflight runs immediately before EVERY commit stage of the mutation, for
    exactly that stage's path set, and a pass never carries from one stage to another.

21. A pending review-v1 mutation never downgrades to legacy. Legacy availability is a property of
    a separate later invocation, never a recovery mechanism for a mutation already pending.

22. A completed C-2 is a durable checkpoint, not timeless validity. Current validity is re-derived
    at every required boundary, a later canonical fact can make a passed proof stale, and
    staleness fails closed rather than being read as the proof having disappeared.
```

---

## 27. Implementation readiness

```text
Contract status              FROZEN (repaired after independent review, twice)
Architecture blocker         NONE
HUMAN decision               NONE
Forward amendment required   YES - three, to landed F2 only, declared in §1.5
Implementation authorized    NO
P3 implementation            NOT STARTED
F4 started                   NO

F1 ordered prerequisites, unchanged and still binding:
  Gate 1  Event metadata carrier                                    NOT AUTHORIZED
  Gate 2  Consumption v1 artifact_kind repair, test-pinned          NOT AUTHORIZED
  Gate 3  activation producer and actual activation                 NOT AUTHORIZED

Freezing F3 authorizes no Gate. The activation producer still fails closed until Gates 1 and 2
are both satisfied.

Implementation prerequisites this contract measured and named, authorizing none:
  IP-1  a closed set of two git_commit persistence modes
  IP-2  the "work" branch of the publication discriminator and its validator
  IP-3  _recorded_completion recognizing the three-effect terminal stage, legacy unchanged
  IP-4  F1 Gate 1
  IP-5  F1 Gate 2
  IP-6  the isolated verification materialization primitive (F2's named gap)
  IP-7  F1 Gate 3

Not implemented by this contract:
  any commit primitive, proof, validator, terminal stage, publication or postcheck code
  any change to src/, tests/, registry.md, canonical Skills, BACKLOG.md, or any P1, P2, P3 F1 or
    P3 F2 document
```
