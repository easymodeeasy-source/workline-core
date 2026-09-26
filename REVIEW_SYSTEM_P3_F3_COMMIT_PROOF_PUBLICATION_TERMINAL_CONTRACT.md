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
P3 F2              inherited EXCEPT the five explicit forward amendments of §1.5
                   (F2-D1 ... F2-D17 otherwise unchanged)
F3                 this document: physical topology, proof, publication, terminal stage
F4                 deferred (§25)
```

Where F3 appears to say something an earlier freeze also says, F3 is a **specialization**: it narrows,
never widens. Every apparent collision was audited item by item in §22.

```text
F3 semantic forward amendments: YES - five, all to landed F2, all stated in §1.5.
```

They are declared there in full, with the exact superseded sentences and the narrow replacement.
**No historical file is edited**: F2 keeps its bytes, and the amendment lives here, which is the
same discipline F1 used for its amendments to P1 R4 and R5.

### 1.4 F1 and F2 decisions F3 preserves without change

Everything in this list is inherited exactly. What F3 does **not** inherit unchanged is the five
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

F3 supersedes five statements of the landed F2 contract. Each is named exactly, with the sentence
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

#### A-4 — F2 §10.3: checkout capability is not bound in the Work Context

```text
F2 §10.3 says

    "Checkout capability is not bound in the Work Context. P2 binds it because planning writes
     canonical Review records whose committed bytes must reproduce exactly; a Work result's
     bytes are the executor's, and the Candidate binds them by Git object identity (§6.3), which
     is the identity Git itself will store. A later contract version that needs a
     checkout-capability claim adds it as a Context version change."

F3 supersedes the first sentence, by the exact mechanism the last sentence names.
```

It supersedes F2 §10.1's exact record as well, because a Context field cannot be added to a frozen exact
schema without doing so:

```text
F2 §10.1 freezes the Work Review Context as an EXACT record at version 1, with nine named fields,
and the P1 reader is strict about unknown fields.

F3 supersedes it with the complete version 2 record of §7.9.6: the same nine fields, unchanged in
name, order and meaning, plus exactly one new field `review_checkout_capability`. A version 1
Context is not a Context of this contract version.
```

The narrow replacement, frozen in §7.9:

```text
1. The Work Review Context gains a bound checkout-capability claim over the CANONICAL REVIEW
   NAMESPACE — not over the Work result. F2's reason for excluding it stands untouched for the
   result: a result's bytes are the executor's and are bound by Git object identity.

2. The claim is a Context field, so `review_context_hash` covers it and the Context's version is
   raised. A Run whose Context does not carry it is not a Run of this contract version.

3. It is proven at SEAL, over the RESULTING TREE, by the committed attribute evaluation of M-21:
   no material attribute applies to this Run's canonical Review record paths or to the
   Consumption path.

4. It is a SEAL precondition, never a Candidate refusal. The Candidate stays expressible and
   reviewable; what it cannot do is receive authorization (§7.9.2).
```

**Why both cannot stand.** F2 §10.3's reason for excluding checkout capability is that a Work result's
bytes are the executor's and are bound by object identity — which is true of the *result* and false of the
*Review records*. Those records are Workline's own canonical bytes, P1 requires them to remain exactly
readable from a fresh clone, and a Work result can now be shown to make them unreadable there. Leaving the
claim unbound would mean a review-v1 Work could authorize its own terminalization while destroying the
readability of the very records that authorize it. The two sentences cannot both hold once the result is
allowed to change persistence semantics, which is what §7.4.1 established.

**Why this is an amendment and not a reinterpretation.** §10.3 states the exclusion as a decision, gives
its reason, and names "a Context version change" as what a later version must do to add it. F3 does
exactly that, and says so, rather than reading the exclusion as if it had been conditional all along.

---

#### A-5 — F2 §6.2: the reviewed surface excludes the canonical Review namespace

```text
F2 §6.2 says

    "The reviewed surface is exactly `result_paths ∪ deleted_paths` as the executor declared
     them — the same owned set START protects with declare_own_content and commits by exact
     path."

F3 supersedes it by ONE exclusion, and nothing else:

    a review-v1 Work may not declare a result path or a deletion path inside the canonical
    Review namespace (`.workline/review/**`). A declared owned set containing one cannot be
    projected to a Candidate, and is refused with the existing `review_candidate_unavailable`
    (F2 §6.5).
```

**Why both cannot stand.** Measured (M-26): with the canonical Review checkout rule in the base tree, a
file staged inside `.workline/review/**` comes out with its bytes normalized, because `eol=lf` applies at
check-in. So for a Candidate entry in that namespace, `Candidate.new_oid` and the committed object would
differ, and the storage-identity invariant — the thing the whole pin architecture exists to guarantee —
would break. F2 §6.2's unrestricted surface and that invariant cannot both hold once the Review namespace
carries the rule that makes Review records durable.

**What exactly is added, and to which landed sections.** Stated precisely, because the previous draft
claimed this was merely F2 §6.5's existing case and that §6.5 was unchanged. **That was not exact and is
withdrawn.**

```text
F2 §6.2   SUPERSEDED, by one exclusion: the reviewed surface is result_paths U deleted_paths as
          declared, MINUS any path inside the canonical Review namespace.

F2 §6.5   EXTENDED, not merely cited. §6.5 names exactly two post-executor declaration failures —
          a declared path that is a directory, and one that cannot be read — and both are about
          PROJECTABILITY. F3 adds a THIRD, different declaration-invalidity case, about
          OWNERSHIP, with its own refusal identity `review_reserved_namespace` (§7.8.4).
          It is not correct to say §6.5 is unchanged.

F2 §2.3   NOT superseded, and not weakened. §2.3 forbids refusing an ordinary correct outcome for
          an unsupported RESULT SHAPE. A reserved-namespace declaration is not a shape refusal: it
          is unowned state, which §2.3 expressly permits refusing, under a rule in force before
          the executor ran.
```

**Why this is an ownership rule and not a post-executor prohibition.** The rule binds at invocation, as
part of what selecting review-v1 means, and the executor is subject to it before it produces anything. The
refusal fires when a declaration violates a contract that already existed — not when a produced shape
turns out to be unsupported. The concrete result paths need not be known in advance for the rule to be in
force, which is exactly why it does not depend on the thing F2 says is unknowable.

**Why the gap has to be closed here.** Checked: `completion_precheck` applies no namespace restriction and
`declare_own_content` takes any path, so no landed rule excludes the namespace today. And it cannot be left
open: measured (M-26), a Candidate entry inside that namespace under the canonical form-L rule is stored
with normalized bytes, so `Candidate.new_oid` and the committed object would differ and the
storage-identity invariant would break.

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

M-20  ATTRIBUTE-SOURCE PINNING WORKS, AND IT IS MEASURED, NOT ASSUMED.
      Git reads a path's attributes from the WORKING TREE's .gitattributes at `git add` time, so
      an executor that writes .gitattributes changes how this operation's own commits store
      objects. `attr.tree` / `GIT_ATTR_SOURCE` replaces the tree source with a named tree-ish.

      CORRECTION, and it matters: an earlier draft of this contract argued that because
      `git check-attr --source` exists at `P2_REVIEW_GIT_MIN` (2.40.0), the pin needs no new
      minimum. That inference is withdrawn. `--source` on `check-attr` does not establish that
      `attr.tree` governs attribute resolution for `git add` and `git commit`, and the version at
      which the attribute subsystem honours `attr.tree` is LATER than 2.40. §7.7 freezes the
      minimum and the capability probe that makes the contract safe regardless.

      Measured on git 2.54.0, in the live primitive's own shape (`git add` then
      `git commit --only --no-verify --no-gpg-sign -- <paths>`), with a clean filter configured,
      a working-tree .gitattributes assigning it, and the filter instrumented to record every
      execution:

          UNPINNED                committed object ebdd5f79  (filtered - NOT the Candidate's id)
                                  filter program executed 3 times
          PINNED attr.tree=<base> committed object f92b6422  (EXACTLY `git hash-object
                                  --no-filters`, which is F2 §6.3's new_oid)
                                  filter program executed ZERO times
          both cases              .gitattributes itself committed, with its new content

      So pinning simultaneously (a) makes the committed object identity equal the Candidate's by
      construction, and (b) mechanically prevents the filter program from running at all, which is
      containment rather than the prohibited disabling of a filter that materially defines
      committed bytes (P1 R5 §6). This is the measurement §7.6 is built on.

M-21  The live committed-attribute evaluation already demonstrates full source containment
      (review/checkout.py:171-215): a fresh bare repository borrowing this one's object store,
      `GIT_ATTR_NOSYSTEM=1`, `GIT_CONFIG_NOSYSTEM=1`, an empty `GIT_CONFIG_GLOBAL`, an empty
      `core.attributesFile`, and every `GIT_*` variable stripped from the environment. The same
      technique neutralizes the system and global attribute sources for a commit.

M-25  THE COMPATIBILITY ALIAS `crlf` IS MATERIAL, AND SO IS `eol` ALONE. MEASURED, git 2.54.
      Each rule below was placed in the BASE tree, and a CRLF file was staged under the full pin
      with core.autocrlf=false and core.eol=lf. "RAW" means the staged object equalled
      `git hash-object --no-filters`, i.e. Candidate.new_oid.

          *.txt text            CHANGED   material
          *.txt crlf            CHANGED   material   <- the alias the five-name set missed
          *.txt crlf=input      CHANGED   material
          *.txt eol=crlf        CHANGED   material   <- `eol` alone bites, without `text`
          *.txt -crlf           RAW       safe (an unset)
          *.txt -text           RAW       safe (an unset)
          *.txt binary          RAW       safe (built-in macro -> -diff -merge -text)

      Two frozen conclusions. `crlf` must be in the parsed surface, or `generated/** crlf` escapes
      it. And `binary` is safe despite being a macro, because its built-in expansion only UNSETS
      text — so the macro rule of §7.8.2 must distinguish the built-in `binary` from a
      user-defined `[attr]` macro rather than refusing the word.

M-26  THE CANONICAL REVIEW CHECKOUT RULE NORMALIZES CHECK-IN BYTES. MEASURED, git 2.54.
      With `skills/review`'s form-L line in the base tree:

          .workline/review/** !text eol=lf -filter -ident -working-tree-encoding

      a CRLF file staged at `.workline/review/gates/x.yaml` under the full pin came out CHANGED,
      not RAW. So `eol=lf` normalizes on check-in even with `text` unspecified.

      This is decisive for §7.8.4: the canonical Review safety rule and the storage-identity
      invariant can only coexist if no Candidate entry ever lies inside the Review namespace.
      That is why §7.8.4 excludes the namespace from the reviewed surface (amendment A-5) rather
      than merely exempting the rule from the parser.

M-27  `GATE_STATUSES` is exactly `("open", "sealed_authorized")` (review/records.py:48-50), and
      `GateGeneration` has no reason, detail or failure field: an open generation carrying a
      receipt_id is refused, and only a seal names an authorized_operation_stage. So a
      "Run ends unsealed with the reason recorded" state does not exist in the landed schema, and
      §7.9.5 freezes what actually happens instead of inventing one.

M-23  THE PIN DOES NOT COVER core.autocrlf / core.eol. MEASURED, git 2.54.
      `core.autocrlf` is CONFIGURATION, not an attribute, so pinning the attribute source does
      not touch it. Measured with a CRLF working-tree file whose raw identity is c30dea8a:

          pinned, core.autocrlf=true   staged 422c2b7a   NORMALIZED  != Candidate new_oid
          pinned, core.autocrlf=input  staged 422c2b7a   NORMALIZED  != Candidate new_oid
          pinned, core.autocrlf=false  staged c30dea8a   RAW         == hash-object --no-filters

      So the primitive must set `core.autocrlf=false` (and `core.eol`) explicitly, exactly as it
      already sets `commit.gpgSign=false`. Git for Windows ships `core.autocrlf=true` globally,
      so this is the DEFAULT condition on that platform, not an exotic one.

M-24  THE PIN COVERS WORKING-TREE text/eol/encoding, BUT NOT THE BASE'S OWN. MEASURED, git 2.54.

          working tree says `*.txt text`, base tree clean, pinned   staged RAW      c30dea8a
          the same, UNPINNED                                        staged NORMALIZED 422c2b7a
          BASE TREE itself says `*.txt text`, pinned                staged NORMALIZED 422c2b7a
          BASE TREE says `working-tree-encoding=UTF-16`, pinned     staged re-encoded, not raw
          base tree clean, pinned                                   staged RAW      c30dea8a

      Two frozen conclusions. The pin is load-bearing: unpinned, an executor-authored `text` rule
      changes the committed object. And the pin cannot rescue a base tree that carries such a
      rule itself, because the pin faithfully honours the base — which is precisely why the entry
      predicate of §7.8 must be proven over the attribute SOURCE, and why `filter`/`ident`/
      `working-tree-encoding` alone was an incomplete surface (§7.7.2).

M-22  `require_effective_evaluation` (review/checkout.py:222) evaluates attributes with NO
      `--source`, i.e. against the WORKING TREE. That is why an executor-authored .gitattributes
      can make a Review-generation commit refuse after the executor returned: the refusal is real
      and it is not on the K1 path at all. §7.6 closes it by pinning that evaluation too.

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
 9  Git persistence preflight over the owned set, under the pin  §7.3
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
17a the Consumption identifier is reserved                              §13.2
17b Git persistence preflight, AGAIN after the Review, under the pin, over exactly the
    paths S-c1 will write. This is the run W2 binds, not step 9's       §7.3
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
attribute   attr.tree = <the PERSISTENCE BASIS of this commit, per §7.1.1>, on BOTH invocations
source      GIT_ATTR_NOSYSTEM=1, core.attributesFile = a Workline-owned empty file,
            GIT_CONFIG_NOSYSTEM=1, GIT_CONFIG_GLOBAL = that same empty file,
            every GIT_* variable stripped from the inherited environment
line        core.autocrlf=false and core.eol=lf, on BOTH invocations.
endings     These are CONFIGURATION, not attributes: the attribute pin does not touch them, and
            measured, `core.autocrlf=true` normalizes CRLF check-in content even with the pin in
            place (M-23). Git for Windows sets it globally by default, so this is the ordinary
            condition on that platform.
staging     `git add` with core.hooksPath = a Workline-owned empty plain directory,
            core.fsmonitor=false, and the attribute-source and line-ending pins above
commit      `git commit --only --no-verify --no-gpg-sign -m <message> -- <paths>`
            with core.hooksPath = that same directory
                commit.gpgSign=false
                core.fsmonitor=false
                gc.auto=0
                maintenance.auto=false
                the attribute-source and line-ending pins above
hooks dir   proven to be an empty plain directory immediately before use, or STOP
            (review_hooks_path_invalid)
capability  the running Git is proven to honour the pin, by the probe of §7.7, before the first
            pinned commit
source      the pinned attribute source is proven to carry no material attribute at all, by the
predicate   finite proof over the source itself of §7.8 — not by probing paths
```

```text
THE STAGING-BYTE CONTRACT, frozen, and this is what the whole primitive exists to make true:

    Candidate.new_oid  ==  the index object after the actual contained_add
                       ==  the committed object after contained_commit

for every supported Work result, with no exception and no "usually".
```

#### 7.1.1 The two bases, and why they are one persistence basis

An earlier draft said "every commit this operation makes, including S-c0, pins to
`declared_base.base_commit`". That is **circular** and is withdrawn: `declared_base.base_commit` is HEAD
*after* S-c0 (amendment A-1), so S-c0 cannot pin to a commit that does not exist until S-c0 has finished.

```text
PRE_S_C0_BASE   the exact committed HEAD immediately before S-c0 is recorded.
                It is a commit that already exists, so there is nothing circular about it.

S-c0                            pins to PRE_S_C0_BASE
declared_base.base_commit       = the exact post-S-c0 HEAD
generation commits 1 / 2 / 3    pin to declared_base.base_commit
every pre-completion Work commit
S-c1, S-c2                      pin to declared_base.base_commit

When S-c0 is not recorded at all — the event log already matches HEAD — PRE_S_C0_BASE and
declared_base.base_commit are the same commit and the distinction collapses.
```

**Why this is semantically ONE persistence basis, and not two.** The premise has to be guaranteed, not
assumed, so F3 freezes the restriction that makes it true:

```text
S-c0 COMMITS THE EVENT LOG AND NOTHING ELSE.

    its path set is exactly { .workline/events/events.jsonl }, and a stage recorded under the
    name <W>:entry:<n> whose payload names any other path is refused before it is applied.

Therefore S-c0 cannot add, remove or modify ANY attribute source: not the root .gitattributes,
not a nested one, not .git/info/attributes (which is outside the tree entirely and is not a
committed path at all).

Therefore the attribute-source tree of PRE_S_C0_BASE and that of declared_base.base_commit are
IDENTICAL with respect to every attribute source: the two trees differ only at the event log,
which is not an attribute source and matches no attribute pattern that the entry predicate of
§7.8 permits to exist.

So the entry predicate, proven once over PRE_S_C0_BASE, holds unchanged over
declared_base.base_commit, and the two pins denote the same attribute state. One basis,
named twice because the commit ids differ.
```

```text
The entry predicate of §7.8 is evaluated over PRE_S_C0_BASE, because that is the tree that
exists when the entry decision is made. Its conclusion carries to declared_base.base_commit by
the argument above, and §7.3's per-commit preflight re-proves it under each commit's own pin
regardless.
```

The attribute-source pin is the part that is new in this contract version, and §7.6 is why it exists. It
is part of the frozen `review-v1-work-local-v1` identity, so it is bound into the Context (F2 §10.3) and
into Review validity through R6/R11: a Review is valid under the persistence semantics it was taken with,
and those semantics are now named exactly rather than inherited from whatever the working tree happens to
hold when the commit runs.

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
    every clean, process, LFS or ident program the WORKING TREE's attributes would select,
      because the attribute source is pinned to the base tree and the system and global sources
      are neutralized. Measured: under the pin the filter program is invoked zero times where
      the unpinned commit invokes it three times (M-20)

proven absent, never disabled
    a clean filter, process filter, ident expansion or working-tree re-encoding assigned by the
      PINNED source itself — the base tree, or a non-tree source
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

### 7.3 The Git persistence preflight — before EVERY commit, under the pin

P1 R5 §4 requires **every** external executable or process Git can invoke on the exact staging and local
commit path to be classified before the commit. §11.3 puts every Git stage of a review-v1 Work mutation
under this primitive, and §7.6 puts the Review's own generation commits under it too, so the preflight
binds all of them.

```text
IMMEDIATELY BEFORE EVERY commit this operation makes with "review-v1-work-local-v1":

  1. determine the EXACT path set that commit will write — after the same changed-against-HEAD
     narrowing the stage itself applies, and never a wider or a nominal set;

  2. evaluate the attributes of exactly those paths UNDER THE PINNED SOURCE — the same
     attr.tree = <tree of declared_base.base_commit>, the same neutralized system and global
     sources, that the commit itself will run with (§7.1).

     Evaluating against the working tree instead would let the evaluation and the storage
     disagree, which is precisely the defect M-22 records in the live effective evaluation;

  3. require "unspecified" or "unset" for EVERY material attribute — filter, ident,
     working-tree-encoding, text and eol (M-23, M-24) — on every one of those paths, and require
     that the effective configuration define no filter driver named "unset" or "unspecified";

  3a. require that the invocation carry core.autocrlf=false and core.eol=lf. These are
     configuration rather than attributes, so the attribute pin does not reach them, and measured
     they change check-in bytes on their own (M-23);

  4. hooks, signing, the filesystem monitor and background maintenance are MECHANICALLY DENIED by
     the primitive itself, re-established by each invocation rather than assumed from a previous
     one; and under the pin no filter, ident or encoding program is reachable at all (M-20);

  4a. the running Git is proven to honour the pin, by the capability probe of §7.7, before the
     first pinned commit of the operation;

  5. a question Git cannot answer is a REFUSAL, not a pass;

  6. anything that does apply FAILS CLOSED before that commit is recorded.

Refusal code: review_git_transform (the existing live code; F3 introduces no new code here).
```

This binds, explicitly and without exception:

```text
S-c0                              the entry-events commit
generation 1 / 2 / 3              the Review's own record commits                     §7.6
every pre-completion Work Git commit
                                  a derived registration, a move, a human-NG move
S-c1                              the result commit K1
S-c2                              the terminal commit K2
```

```text
A preflight passed for one commit NEVER carries to another. Each commit's path set is its own,
and a pass proven for paths A says nothing about paths B.

Under the pin the tree source cannot change beneath the operation, so what this per-commit check
actually catches is drift in a NON-TREE source — .git/info/attributes, or a global or system
source — arriving mid-run. That is external interference (§7.4.1), and it reconciles.
```

The preflight exists at all because F2 §6.3 froze the Candidate's `new_oid` as `gitcmd.hash_blob` of the
executor's bytes, which is `git hash-object --no-filters`. Under the pin that equality is what Git
actually produces (M-20); the preflight is what proves the base tree itself carries no rule that would
break it.

```text
Checkout capability is NOT bound for the Work path. F2 §10.3 froze that boundary: a Work result's
bytes are the executor's and are bound by Git object identity, not by a reproduction claim.
F3 does not add it. §7.6 states what that leaves open and why the Review is the control.
```

### 7.4 Where a transform refusal happens, and what it is not

F2 §20.17 governs this exactly: *an ordinary, correct Work outcome is always expressible as a Candidate;
where an outcome is outside the expressible domain and the condition is knowable before the executor runs,
the refusal happens at START entry.* Under the attribute-source pin of §7.1 there is exactly ONE condition
left that can break the Candidate's object identity, and it is **entirely knowable before execution**:
whether the pinned source itself — the base tree, plus the non-tree sources the primitive cannot
neutralize — carries a transform. So there is one refusal, and it is at entry.

```text
ENTRY REFUSAL — the only transform refusal this contract has

  At START entry, before the Project execution lock and before any mutation is opened, a review-v1
  Work START is refused unless BOTH hold:

    the UNIVERSAL SOURCE PREDICATE of §7.8 passes: every attribute source of the pinned
      configuration — every .gitattributes in the base tree at every depth, plus
      .git/info/attributes — is parsed, and none of them ASSIGNS any material attribute
      (filter, ident, working-tree-encoding, text, eol) and none defines an [attr] macro.
      The predicate is over the SOURCE, not over paths, so it covers result paths that do not
      exist yet;

    the primitive's neutralization of the system and global sources is shown to hold (M-21);

    the running Git honours the pin, proven by the capability probe of §7.7.

    code      review_git_transform
    effect    nothing is written, no mutation exists, no event, no commit, no Review record.
              The Project is exactly as it was, and legacy START is fully available for it as a
              separate invocation.

  The source predicate covers every path at once, including result paths the executor has not
  produced yet and Review record paths whose identifiers are not yet allocated, which is why it is
  stated over the attribute SOURCE rather than over a path list (§7.8).

  Consequence, stated rather than hidden: a Project that genuinely uses a content filter — Git LFS,
  a clean/smudge pair, ident expansion, working-tree re-encoding — cannot use review-v1 Work at
  this contract version. That is a stated v1 boundary, refused before the person has spent
  anything, and it is the same kind of honest limit F2 §13.6 set for Evidence completeness.

AFTER THE EXECUTOR — no RESULT SHAPE is refused

  The pin makes an executor-authored transform irrelevant to how this operation STORES objects
  (§7.4.2), so there is no post-executor transform refusal at all: such a result is stored
  exactly, expressed in the Candidate and reviewed.

  Two things are nevertheless decided after the executor returns, and neither is a shape refusal:

    AUTHORIZATION   a result whose RESULTING TREE breaks canonical Review checkout capability is
                    fully expressible and fully reviewable, and cannot be sealed (§7.9). That is
                    authorization being withheld, not a result being refused.

    OWNERSHIP       a result that declares a path inside the reserved Review namespace violates
                    the review-v1 invocation contract, which bound before the executor ran
                    (§7.8.4). That is unowned state, which F2 §2.3 expressly permits refusing.

  What remains beyond those is only external drift in a non-tree source, which §7.4.1 classifies
  as interference.
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

#### 7.4.2 The pin, and why no post-executor refusal is needed

The earlier draft answered this by widening *when* the preflight runs, and then refusing when an
executor-introduced transform covered a path this operation commits. **That refusal is withdrawn.** It was
a post-executor refusal of a supported result shape, which F2 §2.3 prohibits outright, and calling it an
"expressibility boundary" did not change what it was. The draft's claim that such a refusal happens
"before any commit" was also simply false: by the time S-c1 is reached, S-c0 and three Review-generation
commits have already been made (§7.5).

The architecture that actually removes the refusal is the attribute-source pin of §7.1, and the reason it
works is measured, not argued (M-20):

```text
Every commit this operation makes runs with a pinned attribute source — S-c0 to PRE_S_C0_BASE,
every later commit to declared_base.base_commit, which §7.1.1 proves is the same attribute state —
with the system and global attribute sources neutralized.

Therefore the persistence semantics this operation commits under are FIXED, at the base, before
the executor runs — the same base the Candidate's object identities were computed against.

An executor-authored .gitattributes is therefore an ORDINARY RESULT and nothing more. It is
committed, with its new content, as an ordinary file entry (F2 §6.4's rule for .gitmodules,
applied to the same question). It does not change how this operation stores any object, so it
cannot make any commit of this operation deviate from the Candidate, and there is nothing to
refuse.
```

Measured, in the live primitive's shape, with a clean filter that the new `.gitattributes` assigns to the
result path (M-20):

```text
unpinned    committed object != Candidate.new_oid, and the filter program ran 3 times
pinned      committed object == `git hash-object --no-filters` == Candidate.new_oid EXACTLY,
            and the filter program ran ZERO times
```

So the pin closes three things at once, and this is the whole of the architecture:

```text
1. IDENTITY.  reviewed object identity == committed object identity, by construction rather than
   by preflight. F2 §6.3's new_oid = hash_blob(bytes) becomes a statement Git makes true, not a
   hope the preflight guards.

2. EXTERNAL-PROCESS SAFETY.  The filter program is never invoked. P1 R5 §4 requires every
   external process reachable on the staging/commit path to be classified before commit_local;
   here it is mechanically DENIED, measurably, alongside hooks, signing, fsmonitor and
   maintenance. This is containment, not the prohibited disabling of a filter that materially
   defines committed bytes (R5 §6): under the pinned semantics no filter is applicable to this
   operation at all, so none materially defines its committed bytes.

3. NO POST-EXECUTOR REFUSAL.  There is no outcome shape the executor can produce that the pin
   turns into a refusal, so F2 §2.3 and §20.17 are satisfied without any appeal to malformedness,
   to legacy, or to F4.
```

#### 7.4.3 What the pin deliberately does NOT do, stated plainly

```text
The repository ends up holding the result object stored under the BASE semantics, while the
newly committed .gitattributes describes different semantics for it going forward.
```

This is deliberate, and it is the correct behaviour for a Review system:

```text
the committed object is EXACTLY what the reviewer judged. The alternative — running the new
  filter — would commit an object the reviewer never saw and never authorized, which is the
  failure a Review system exists to prevent;

it is ordinary Git behaviour, not an invention: attributes apply when content is staged, and
  changing them later does not retroactively re-clean objects already stored. That is what
  `git add --renormalize` exists for;

and the decision itself is REVIEWED. Because .gitattributes is a declared result path, its new
  content is an entry in the Candidate and the reviewer sees exactly which rule is being
  introduced. Nothing is hidden behind a contract refusal: the control is the Review.
```

```text
Renormalizing other paths under the new semantics is a separate Work, with its own Candidate and
its own Review. F3 neither performs it nor forbids it.

A LATER review-v1 Work in that Project then starts from a base whose committed attributes hold
the new rule, so §7.4's entry refusal applies to it in the ordinary way, before anything is
written. That boundary is unchanged by this repair and remains a stated v1 limit rather than a
trap: it is decided at entry, where F2 §20.17 says a knowable condition belongs.
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
a transform already in the base tree, or in a non-tree source, at START entry
    refused AT ENTRY, before the lock and before any mutation exists. Knowable before execution,
    so F2 §20.17 puts the refusal exactly here. Nothing is opened, nothing is stranded, and
    legacy START is available as a separate invocation.

an operation-owned .gitattributes result — ANY of them, whatever it covers
    storage        proceeds normally under the pin. The pin fixes this operation's persistence
                   semantics at the base, so the result cannot affect how this operation stores
                   any object, and it is committed as an ordinary file entry.          §7.4.2
    Candidate      expressible, and reviewed like any other file entry.
    authorization  decided by the ordinary Review, PLUS the §7.9 checkout-capability seal
                   condition over the resulting tree. A result that breaks that capability is
                   reviewed and then not sealed.
    completion     only after authorization, and then only through the ordinary K1 / K2 /
                   recorded-completion topology.

    So the storage question has one answer for every such result, and the authorization question
    does not: it is NOT the case that every Work with a .gitattributes result completes. What the
    pin removed is the dependence of STORAGE on what the new attributes cover — not the
    dependence of AUTHORIZATION on it.

external drift in a non-tree attribute source during the run
    (.git/info/attributes, or a global or system source that the primitive cannot neutralize
    retroactively). Not producible as a Work result: a result is a tracked repository path, and
    these are not. Foreign interference, detected by the per-commit preflight (§7.3) before the
    affected commit, and it reconciles. What recovery is attempted is F4's.             §7.4.1
```

```text
NO POST-EXECUTOR REFUSAL OF A SUPPORTED RESULT SHAPE REMAINS.

Every refusal this contract now states is one of:
    knowable before execution      -> refused at START entry (F2 §20.17)
    external interference          -> reconcile (F2 §2.3's permitted category)
    malformed declaration          -> F2 §6.5's two frozen cases, plus the ownership case
                                      F3 adds with its own identity (§7.8.4, A-5)
    unowned state                  -> refused (F2 §2.3's permitted category)
    authorization withheld         -> not a refusal of a result at all (§7.9)
and none of them is a refusal of what the executor produced.

Architecture blocker: NONE.
```

F3 does not weaken the byte-identity requirement to accommodate any of this, because doing so would make
the Candidate's `new_oid` a claim about bytes Git does not store.

### 7.5 "Before S-c1" is NOT "before any physical effect"

This correction is recorded because the previous draft's reasoning depended on the opposite being true,
and it was wrong. By the time S-c1 is reached, this operation has already made commits:

```text
S-c0                          the entry lifecycle events commit                     §4.3
Candidate freeze              (no commit)
generation 1 commit           the CandidateSnapshot, the TaskInput and gate 1       M-12
   external reviewer launch
generation 2 commit           gate 2, the settlement
generation 3 commit           gate 3 and the Receipt

S-c1                          <- four commits already exist on the branch by here
```

```text
Therefore a refusal "before S-c1" strands a pending mutation that has already applied lifecycle
events and made four commits. It is not pre-physical, nothing about it is free, and no statement
of this contract may claim otherwise.

Every statement equivalent to "K.2 / K.3 refuse before any commit, so nothing is stranded" has
been removed. The architecture no longer needs them, because §7.4.2 removes the refusals
themselves rather than arguing they are cheap.
```

### 7.6 The whole physical path surface, not only K1 and K2

The second half of this finding is that the Review's OWN commits are exposed. Measured (M-22):
`require_effective_evaluation` evaluates attributes with **no** `--source`, i.e. against the working tree,
and the live generation flow runs the persistence preflight over the Review record paths before each
generation commit. So an executor-authored `.gitattributes` covering `.workline/review/**` would make the
**Review-generation commit** refuse — after the executor returned, and on a path that has nothing to do
with K1.

The pin closes this by the same mechanism, applied to the same complete surface:

```text
EVERY commit this operation makes is pinned — S-c0 to PRE_S_C0_BASE and every later commit to
declared_base.base_commit (§7.1.1) — and every persistence evaluation this operation makes is
evaluated UNDER THAT SAME PIN, over exactly the paths that commit writes:

    S-c0                        the event log
    generation 1 / 2 / 3        .workline/review/candidate-snapshots/**
                                .workline/review/task-inputs/**
                                .workline/review/gates/**
                                .workline/review/receipts/**
    every pre-completion Work Git commit
    S-c1                        the Candidate's entry paths
    S-c2                        the event log and .workline/review/consumptions/**

The evaluation and the storage therefore agree by construction: both are governed by the base
tree. An evaluation that read the working tree while the commit stored under the pin would be
the two disagreeing, which is the defect M-22 names.
```

```text
The base-tree condition, proven once at entry and re-proven before each commit under the pin:

    no material attribute — filter, ident, working-tree-encoding, text, eol (and the alias crlf) —
    applies, under the pinned source, to any path this operation will write — result paths, Review record paths, the event log and the
    Consumption path alike.

A base tree that assigns no material attribute at all — the complete alias-expanded surface of
§7.8.2 — to anything satisfies this for every path
at once, including paths whose identifiers are not yet allocated, which is why it is the
condition the entry refusal (§7.4) actually tests. It is the same shape as the single supported
configuration P2 already freezes for its own checkout capability (`skills/review`).
```

```text
Future checkouts are a SEPARATE question from storage, and the previous draft answered it badly.
After the Work lands, a fresh clone checks out with the NEW attributes, so a result that makes
.workline/review/** subject to a checkout transform would make this Run's own canonical records
unreadable in a fresh clone — the CandidateSnapshot, the TaskInput, the gates, the Receipt and
the Consumption that authorize the very transition being performed.

That draft left it to the reviewer's discretion. A reviewer is not a mechanical safety property,
and P1 requires those records to remain exactly readable from a fresh clone. §7.9 replaces the
discretion with a proof: the Candidate stays fully expressible and reviewable, and the SEAL
cannot issue a Receipt unless the RESULTING TREE preserves canonical Review checkout capability.
That is forward amendment A-4 (§1.5), by the Context-version mechanism F2 §10.3 itself names.
```

### 7.7 The pin mechanism, its Git minimum, and the capability probe (R13)

#### 7.7.1 The inference that was withdrawn

```text
An earlier draft argued: `git check-attr --source` exists at P2_REVIEW_GIT_MIN (2.40.0),
therefore the attr.tree pin needs no new minimum.

That is a non-sequitur and it is withdrawn. `--source` is an option of check-attr. It does not
establish that `attr.tree` governs attribute resolution for `git add` and `git commit`, which is
a different subsystem path and landed later. The independent re-review reports the attribute
subsystem learned to honour `attr.tree` at Git 2.43.
```

```text
The measurements of M-20, M-23 and M-24 were taken on git 2.54.0. They prove the MECHANISM —
that a pinned source plus neutralized line-ending configuration yields exactly
`git hash-object --no-filters`, and that the filter program never runs. They prove NOTHING about
2.40, 2.41 or 2.42, and this contract does not claim they do. Only git 2.54 was available in the
environment where they were taken, so Option 1 of the re-review — measure the exact primitive on
2.40.x — could not be discharged and was not selected.
```

#### 7.7.2 Frozen decision — Option 2, with a probe that makes the floor non-load-bearing

```text
A. A NEW THRESHOLD is introduced, owned by `rules/git` alongside the two P2 ones:

       P3_WORK_ATTR_PIN_GIT_MIN = 2.43.0

   the first version at which the attribute subsystem honours attr.tree. This contract adopts
   2.43.0 on the independent re-review's report of upstream release notes; it is NOT a fact this
   contract measured.

B. THE FLOOR IS NOT THE AUTHORITY. Before the first pinned commit of a review-v1 Work
   operation, the running Git is PROVEN to honour the pin, positively, by a capability probe:

       in a throwaway scratch directory under .workline/runtime/** — the same containment the
       live committed-attribute evaluation already uses (M-21) — create a repository, commit a
       tree that carries NO attributes, then write a working-tree .gitattributes that assigns a
       transform to a probe path, stage that probe path with the exact pin the primitive uses,
       and require the staged object id to equal `git hash-object --no-filters` of the probe
       bytes.

       pass  -> the running Git honours the pin, measured on this machine, this run
       fail  -> review_git_unsupported; nothing is opened and nothing is written
       unanswerable -> the same refusal; not knowing is not a yes

   The probe uses no filter program that does anything: the transform it assigns need only be
   one whose application is detectable, so the probe itself has no external side effect.

C. BOTH ERROR DIRECTIONS ARE SAFE, which is why a version number this contract did not measure
   is acceptable as a floor:

       floor too HIGH  -> a Git that would have worked is refused at entry. Conservative, and it
                          costs availability, never correctness.
       floor too LOW   -> the probe fails on that Git and the operation refuses. The floor never
                          authorizes an unpinned commit by itself.

   No combination of a wrong floor and a passing probe can produce a commit whose object
   identity differs from the Candidate's, because the probe tests exactly that equality.

D. INTERACTION WITH THE EXISTING THRESHOLDS. They are unchanged and independent:

       P2_PUBLICATION_GIT_MIN   2.31.0   the publication barrier proof (§12.4)
       P2_REVIEW_GIT_MIN        2.40.0   review-v1 planning Git semantics
       P3_WORK_ATTR_PIN_GIT_MIN 2.43.0   the review-v1 WORK attribute pin

   A review-v1 Work START's effective minimum is the greatest of those that apply to it. With a
   remote that is 2.43.0, since 2.43.0 > 2.31.0; without a remote it is also 2.43.0, because the
   pin is required whether or not anything is published.

E. REFUSAL CODE. `review_git_unsupported`, the existing live code that `rules/git` already owns
   for a Git below a review-v1 threshold. F3 introduces no new code.
```

---

### 7.8 The universal predicate over the attribute source (R16)

#### 7.8.1 Why a path-wise check cannot work

```text
The result path set is unknown before the executor runs (F2 §6.2). So a predicate of the shape
"no material attribute applies to any path this operation will write" cannot be evaluated at
entry, where the refusal has to happen, because the paths do not exist yet.

Rules that must not escape, and that a path-wise probe at entry would miss entirely:

    generated/**  filter=x
    **/*.txt      text
    new/**        working-tree-encoding=UTF-16
    [attr]macro   text filter=y        and then `foo/** macro`
```

The predicate is therefore frozen over the **attribute source itself**, which is finite, and not over
paths, which are not.

#### 7.8.2 The complete byte-transform surface, and the supported source shape

The previous draft's five-name set was incomplete. The exact frozen surface, with every name classified
and every compatibility alias expanded before it is judged (M-23, M-25):

```text
CANONICAL MATERIAL ATTRIBUTES — an assignment of any of these changes stored bytes

    text                        check-in normalization
    eol                         MEASURED material on its own, without `text` (M-25)
    working-tree-encoding       re-encoding
    filter                      clean / process / LFS driver
    ident                       $Id$ expansion

COMPATIBILITY ALIASES — the backwards-compatible spellings, expanded to canonical form BEFORE
the decision, never matched as opaque words

    crlf                        ==  text
    -crlf                       ==  -text          (an unset: SAFE)
    crlf=input                  ==  eol=lf
    binary                      ==  -diff -merge -text   built-in macro; only UNSETS text: SAFE

CONFIG VARIABLES — not attributes at all, so the attribute pin does not reach them; the primitive
neutralizes them on every invocation (§7.1)

    core.autocrlf               MEASURED material (M-23)
    core.eol                    neutralized with it; material for checkout semantics
```

```text
`crlf` is the name the previous draft missed, and it is exactly the escape the re-review named:
`generated/** crlf` assigns text normalization to a path that does not exist yet, and a parser
that knows only the five canonical names would pass it. Measured CHANGED (M-25).
```

**The supported source shape**, over every source enumerated in §7.8.3:

```text
RULE 1 — ordinary paths
    no rule may ASSIGN or SET any canonical material attribute, after alias expansion, to any
    pattern that can match a path outside the canonical Review namespace.
        refused:  `*.txt text`, `text=auto`, `eol=lf`, `eol=crlf`, `*.bin filter=lfs`, `ident`,
                  `working-tree-encoding=UTF-16`, `generated/** crlf`, `**/*.txt crlf=input`

RULE 2 — explicit unsets are permitted
        allowed:  `-text`, `-crlf`, `-filter`, `-ident`, `!text`, and `binary`
    An unset provably means "no transform", and refusing it would refuse the safest configuration
    a repository can have. `binary` is permitted by its built-in expansion, measured RAW (M-25),
    and is the one macro word the parser resolves rather than refuses.

RULE 3 — user-defined macros are refused
        refused:  any `[attr]name ...` definition, anywhere in any source, and any use of a name
                  so defined.
    A user-defined macro can expand to a material attribute; this contract version does not do
    expansion analysis and refuses the construct. The built-in `binary` is not a definition and
    is handled by RULE 2.

RULE 4 — the canonical Review namespace is the one place an assignment is REQUIRED
    See §7.8.4. The form-L rule is not merely tolerated there; the capability claim of §7.9
    requires it.

Anything the parser cannot classify — an unreadable blob, a line it does not understand, a source
it cannot enumerate, an alias it does not recognize — is a REFUSAL. Not knowing is not a yes.
```

```text
This is deliberately a NARROW SUPPORTED SHAPE. It over-refuses: a base tree with `docs/** text`
is refused even though no Work result may ever land under docs/. That is a stated availability
cost, never a correctness one, and it is decided at START ENTRY where a knowable condition
belongs (F2 §20.17).
```

#### 7.8.3 The sources, enumerated completely

```text
every .gitattributes blob in PRE_S_C0_BASE, at the root and at EVERY nested depth, found by
  enumerating the tree rather than by guessing at locations;
.git/info/attributes;
the system and global sources, which the primitive neutralizes (M-21) and which are proven
  neutralized rather than assumed.
```

By §7.1.1 the conclusion carries unchanged to `declared_base.base_commit`.

#### 7.8.4 The reserved canonical Review namespace (R21, amendment A-5)

The canonical Review safety rule that `skills/review` freezes is itself an **assignment**:

```text
.workline/review/** !text eol=lf -filter -ident -working-tree-encoding
```

So RULE 1, applied blindly, would refuse exactly the configuration that makes canonical Review records
durable — and would make every P2-capable Project incompatible with P3 Work Review. The two must coexist,
and the measurement says how they cannot:

```text
MEASURED (M-26): with that rule in the base tree, a CRLF file staged at
`.workline/review/gates/x.yaml` under the full pin came out CHANGED, not RAW.

So `eol=lf` normalizes on check-in. If a Candidate entry ever lay inside the Review namespace,
the committed object would differ from Candidate.new_oid and the storage-identity invariant
would break. Exempting the rule from the parser alone is therefore NOT sufficient.
```

The frozen distinction:

```text
A. ORDINARY / RESULT PATH PERSISTENCE SEMANTICS
   governed by RULE 1: no material assignment, so Candidate.new_oid == index oid == committed oid
   holds absolutely.

B. THE RESERVED CANONICAL REVIEW NAMESPACE  (.workline/review/**)
   the form-L assignment is PERMITTED and REQUIRED there (§7.9). Nothing this operation stores
   under the pin lies in that namespace except the canonical Review records themselves, which
   Workline writes as canonical LF bytes through the P1 serializer — so `eol=lf` is a no-op on
   them by construction, not by luck.

   A rule in this namespace is permitted only when its pattern is CONFINED to it: a pattern that
   can also match a path outside the namespace is judged by RULE 1, as an ordinary rule.
```

**What makes B sound is an ownership rule that does not yet exist in primary sources.** Checked, and
stated rather than assumed:

```text
There is NO landed rule excluding .workline/review/** from Work result paths. completion_precheck
checks existence, tracked-ness, must_update, realizes and dependency satisfaction, and no
namespace at all; declare_own_content takes any path; F2 §6.2 says the reviewed surface is
"exactly result_paths U deleted_paths as the executor declared them", with no exclusion.

So F3 does not get to assume the namespace is reserved. It freezes the exclusion explicitly, as
forward amendment A-5 (§1.5).
```

```text
FROZEN, AS AN OWNERSHIP BOUNDARY DECLARED BEFORE EXECUTION:

  The review-v1 Work INVOCATION CONTRACT declares `.workline/review/**` to be a reserved,
  Review-owned namespace that START's executor may not own as a result path or as a deletion
  path. This is part of what selecting review-v1 means (F1-D1), it is static, and it is known
  before the executor runs — the concrete future result path list need not be known for the rule
  to be in force.

  A Completed outcome that declares a path in that namespace has violated a contract that already
  bound it. START cannot show ownership of that path for this operation, because the namespace is
  owned by Review.

  refusal identity:  ReconcileRequired is NOT used. The refusal is a StopError with the frozen
                     code `review_reserved_namespace`.
```

```text
Why a NEW code rather than `review_candidate_unavailable`. That code means exactly one thing in
F2 §6.5 — "the declared owned set cannot be projected exactly" — which is about PROJECTABILITY, a
property of the bytes at a path. This condition is about OWNERSHIP, which is a property of the
namespace and is decided without looking at the bytes at all. Overloading one code with two
unrelated meanings is the ambiguity this contract is supposed to remove, and no existing code
states it: the contract-argument refusal is about the caller's argument, `review_containment` is
about where Review's own writes land, and `review_candidate_unavailable` is about projection.

This is the same reasoning F1 used when it introduced `review_not_activated`, and it is the only
new code F3 introduces.
```

**Why this refusal does not break the no-trap principle.** It is not a refusal of a RESULT SHAPE, and
the distinction is exact rather than rhetorical:

```text
F2 §2.3 protects every ordinary correct Work outcome from a post-executor refusal of an
UNSUPPORTED SHAPE — an object kind, a mode, a byte pattern, something about WHAT the executor
produced. A reserved-namespace declaration is none of those. The Git object at that path may be a
perfectly ordinary blob.

What is refused is a DECLARATION OF OWNERSHIP over a path this operation was never permitted to
own, under a rule that was in force before the executor started. F2 §2.3 expressly permits
refusing unowned state; this is exactly that class, and the rule is knowable before execution,
which is where F2 §20.17 says such a condition belongs.

The executor learns the rule the same way it learns every other part of the review-v1 contract:
from the invocation contract, before it runs. A Work that needs to change Review records has no
correct form under review-v1 at all — canonical Review records are immutable and are written only
through create_file (R1 §8), and live code refuses a generic write_file to a Review path — so
there is no ordinary correct outcome being taken away.
```

```text
The primary-source basis for the namespace being Review's own, cited rather than asserted:

  REVIEW_SUBDIRS closes the canonical Review namespace to seven directories
  require_review_record_path owns the canonical record path shape
  canonical Review records are immutable (R1 §8)
  create_file is the Review create-only primitive
  live Mutation validation refuses a generic write_file to a Review path outright

What was MISSING from primary sources, and is therefore added here rather than assumed, is only
the statement that a Work RESULT may not land there: completion_precheck applies no namespace
restriction and declare_own_content takes any path.
```

#### 7.8.5 Defence in depth, not a substitute

```text
After the source parse passes, the entry check ALSO evaluates `check-attr` under the pinned
source over the paths that ARE known — the event log, the Review namespace prefixes, and the
Project's tracked paths — inside the contained evaluation of M-21.

The parse is what makes the predicate universal and covers unborn paths. The evaluation is a
second, independent mechanism over the paths that exist. Neither replaces the other, and a
disagreement between them is a refusal.
```

---

### 7.9 Fresh-clone durability of the canonical Review records (R15)

#### 7.9.1 The problem the previous draft left open

```text
The previous §7.6 permitted a Work result to introduce attributes covering .workline/review/**
and said a fresh clone might then read those records transformed, with "the reviewer sees the
rule" as the control.

That is not sufficient. The Work has ALREADY created canonical Review records by then — the
CandidateSnapshot, the TaskInput, the gate generations and the Receipt — and it is about to
create the Consumption. P1 requires those records to remain exactly readable from a fresh clone;
that is the whole reason they are canonical rather than runtime. Leaving it to reviewer
discretion is not a mechanical safety property, and a reviewer cannot be the proof.
```

#### 7.9.2 The frozen rule — expressible, reviewable, but not authorizable

The rule is placed so that it does **not** recreate the F2 no-trap failure:

```text
A Candidate that introduces such attributes REMAINS FULLY EXPRESSIBLE. It is frozen, its
material is built, it is verified and it is reviewed, exactly like any other Candidate. Nothing
about the executor's result is refused, so F2 §2.3 and §20.17 are untouched.

What it cannot do is receive AUTHORIZATION: the seal cannot issue a Receipt unless the capability
claim of §7.9.3 holds over the RESULTING TREE.

    resulting tree = the base tree with this Candidate's entries applied — every changing entry
                     at its new kind, mode and object id, every deletion absent. It is fully
                     determined by the Candidate and declared_base, so it is computable BEFORE
                     K1 exists and before the Review is even launched.
```

```text
Why this is not a post-executor refusal of a supported result shape: the result IS supported,
IS expressed, and IS reviewed. What the contract declines to do is AUTHORIZE a transition whose
own bookkeeping would become unreadable in a fresh clone. F2 §2.3 governs expressibility as a
Candidate; it does not require that every expressible Candidate be authorizable — a reviewer
rejecting a Candidate is the ordinary case of exactly that.
```

#### 7.9.3 The capability claim — the canonical form-L rule, reused verbatim (R19)

The previous draft defined success as "no material attribute applies under a neutralized test config".
**That is withdrawn**: it proves nothing about an actual fresh clone, which runs with the person's own
configuration, and this contract has itself measured that `core.autocrlf` changes bytes (M-23).

F3 therefore does **not** invent a proof. It reuses the canonical one, **the same exact form-L rule**
that `skills/review` already freezes for P2:

```text
THE REQUIRED RULE, verbatim from skills/review (Checkout capability):

    .workline/review/** !text eol=lf -filter -ident -working-tree-encoding

THE REQUIRED PRINTED FORM, verbatim:

    form L   text: unspecified   eol: lf   filter: unset   ident: unset   working-tree-encoding: unset

THE FOUR PROOF LAYERS, all required, verbatim in structure from skills/review, with the tree
under test being the RESULTING TREE rather than HEAD:

  1. the raw bytes of the resulting tree's root .gitattributes, read from the committed object,
     contain no NUL and their LAST attribute rule is exactly that line;
  2. the resulting tree holds no entry under .workline/ whose name folds to .gitattributes;
  3. the evaluation of the resulting tree's committed .gitattributes ALONE prints form L;
  4. this repository's effective evaluation — info/attributes, attribute-source substitution,
     global and system included — prints form L, and no filter driver named `unset` is
     configured.

    failure at any layer -> review_checkout_unsafe
    undeterminable       -> review_checkout_unknown
```

**Why this proves actual fresh-clone bytes and the previous formulation did not.** `eol=lf` is an explicit
assignment, so checkout produces LF **regardless of the reader's `core.autocrlf` or `core.eol`**; it does
not depend on the absence of configuration, which is the thing a fresh clone cannot promise. `!text` keeps
check-in from normalizing, and the three unsets keep filters, ident expansion and re-encoding away. That
is why the canonical rule assigns rather than merely leaving things unspecified, and it is why F3 adopts it
unchanged instead of substituting a weaker "nothing applies" test.

```text
The word "unspecified" printing in form L proves nothing on its own — a literal `filter=unset`
prints the same word — which is exactly why layers 1 and 3 read the committed bytes and evaluate
the committed source, and not only the printed result. F3 inherits that reasoning with the rule.
```

#### 7.9.4 The complete path surface the claim must cover (R20)

The previous draft covered only this Run's record paths plus the Consumption path. **Too narrow**: a
Candidate can leave this Run untouched and still corrupt an OLDER canonical Review record on fresh
checkout.

```text
THE COVERED SURFACE, frozen:

  1. EVERY canonical Review record path present in the RESULTING TREE, enumerated from that tree
     over the closed Review namespace (REVIEW_SUBDIRS: gates, receipts, consumptions,
     supersessions, candidate-snapshots, task-inputs, activation) — every Run's records, not
     this one's;

  2. the paths this seal is about to create: the sealing generation record and the Receipt;

  3. the Consumption path this authorization may later create, whose identifier is already
     reserved (§13.2).

Because the required rule is a single pattern over `.workline/review/**`, proving it covers the
whole namespace at once — including record paths that do not exist yet, which is the same reason
the entry predicate is over the source rather than over paths (§7.8.1).
```

```text
SECOND CONDITION, and it is separate from attributes: every canonical Review record present in
the RESULTING TREE must still read under P1's strict reader.

    `skills/review` already makes this a precondition of writing any Review record
    (`review_namespace_unreadable`), evaluated over the Project. F3 evaluates the same condition
    over the RESULTING TREE, because that is the state this authorization would bring about.

    This is what catches a Candidate that writes bytes at a Review path — which §7.8.4 refuses at
    Candidate projection anyway, so the two are belt and braces rather than one control.
```

#### 7.9.5 What happens when the capability proof fails (R23)

The previous draft said the Run "ends unsealed with the reason recorded". **No such state exists**:
`GATE_STATUSES` is exactly `("open", "sealed_authorized")`, `GateGeneration` has no reason field, an open
generation carrying a `receipt_id` is refused, and only a seal names an `authorized_operation_stage`
(M-27). F3 does not invent a state. What is frozen:

```text
NO new generation is written. Generation 2 — the settlement — remains the latest generation of
  the Run, and it is `open`. The gate chain is left exactly as it was.

NO Receipt is issued. NO authorization exists. NO Consumption is created. NO K1 is made, and
  nothing is published.

THE FAILURE IS AN OPERATION RESULT, NOT A REVIEW RECORD. It is the STOP of the owning operation
  — review_checkout_unsafe, or review_checkout_unknown when undeterminable — carried in the
  operation's own result and in the mutation's runtime metadata. No canonical Review record
  states it, because none of them can.

RECOVERY IS NARROW, AND THE PREVIOUS DRAFT STATED IT TOO BROADLY. The Candidate,
  declared_base, the resulting tree and the Context are IMMUTABLE for this Run, so a same-Run
  retry cannot change what the resulting tree is:

      A SAME-RUN RETRY MAY CHANGE THE ANSWER only when the failed proof depended on TRANSIENT,
      NON-TREE state that can be corrected without touching Candidate or base identity:
          .git/info/attributes interference removed
          a local capability query that was unanswerable becomes answerable
          the effective evaluation of layer 4 restored to form L
      The Context is not rebuilt and no Context byte changes; the same bound
      Context.resulting_tree is re-derived and now passes.

      A SAME-RUN RETRY CAN NEVER CHANGE the INTRINSIC capability of the resulting tree. Layers 1,
      2 and 3 read that tree's committed objects, which are fixed by the Candidate.

      CHANGING the tracked .gitattributes, the Work result, or declared_base produces a DIFFERENT
      resulting tree, hence a different Candidate and a NEW RUN. The old Run does not retarget
      itself onto it: its Context binds the old resulting_tree by object id, and F2 §16.1 makes
      the change invalidating. What becomes of the old Run is F4's.
```

```text
SEAL TIMING, frozen: the capability is re-derived BEFORE any generation-3 canonical effect is
recorded.

On failure, in the same order:
    no generation-3 record is written
    no Receipt
    no authorization
    no Consumption
    no K1, and nothing published
    generation 2 remains the latest generation, and it is `open`

NO PENDING SAME-RUN SEAL MUTATION MAY BLOCK THE RETRY. If an implementation opens a mutation
before the recheck, it MUST be abandoned atomically on the STOP, so that
`pending_generation_mutations()` does not report it and R2 §4's "exactly one pending generation
mutation -> resume it first" rule is not triggered by a seal that never wrote anything. A retry
must find the Run exactly as it was.

No third GateGeneration status is invented, and no invalidation generation is written (M-27).
```

```text
PERMANENT SET-ASIDE IS DEFERRED. Whether an unsealable Run is invalidated, superseded or left
  pending is F4's recovery matrix (§25). F3 does not decide it.
```

```text
No schema change is required by this disposition, which is why it is freezable inside F3. Had it
required a durable canonical representation of non-authorization, that would have been a schema
change outside F3's scope and would have been reported as a blocker instead.
```

#### 7.9.6 The Work Review Context, version 2 — the complete record (R22)

A-4 previously said only that the Context "gains a claim" and "the version is raised". That is not
implementation-complete: F2 §10.1 freezes an exact canonical record and the P1 reader is strict about
unknown fields, so the whole replacement record has to be stated. It is:

```text
{
  schema:  "review-work-context"
  version: 2
  review_kind:                  "work-result-v1"
  review_contract:              "review-v1-work-v1"
  projection_semantics_version: "work-result-projection-v1"
  adapter_identity:             "work-result-adapter-v1"
  loader_identity:              <content identity of the running implementation package>
  authority:                    [ {id, digest} ... ]                     F2 §10.2, unchanged
  git_persistence:              "review-v1-work-local-v1"                F2 §10.3, unchanged
  activation:                   <the activation binding of F2 §11>       unchanged
  review_checkout_capability: {
      capability_contract: "review-v1-work-checkout-capability-v1"
      form:                "form-L"
      namespace:           ".workline/review/**"
      base_tree:           <the full object id of PRE_S_C0_BASE's tree>
      resulting_tree:      <the full object id of the resulting tree, §7.9.2>
  }
}
```

```text
schema          unchanged: "review-work-context". The record kind is the same kind.
version         2. Exactly one field is added to F2 §10.1's nine; the other nine keep their
                names, their order and their meanings.
field name      review_checkout_capability
field type      a mapping of exactly FIVE keys, all present, none nullable
field contents  the capability contract identity, the form identity, the namespace the claim is
                about, and the two exact tree identities the claim is about
serialization   the existing P1 Review serializer, unchanged: mapping keys in ascending code
                point order at every depth, sequences in given order, UTF-8, LF. The nested
                mapping is serialized by the same rule at its own depth.
review_context_hash
                SHA-256 of the canonical bytes of the whole version 2 record, computed exactly as
                F2 §10.1 computes it for version 1. The capability field is inside those bytes,
                so it is bound by the hash and by everything the hash reaches: the gate
                generations, the TaskInput, the Receipt and the closure.
version 1       a Context at version 1 is NOT a Context of this contract version. The strict
rejection      reader refuses a record whose field set does not match its version exactly, so a
                v1 record cannot silently pass as v2 and a v2 record cannot be read as v1. A Run
                whose Context is v1 is not a Run of the review-v1 Work contract F3 freezes.
```

**The Context binds the PROOF TARGET, never a passing verdict.** The previous draft carried
`base_tree_verdict` and `resulting_tree_verdict`, both fixed at `"capable"`, and that was a defect: it made
an unsafe resulting tree **unrepresentable**, so such a Candidate could never build a Context, never reach
generation 1 and never be reviewed — flatly contradicting §7.9.2's frozen boundary that it stays
expressible and reviewable, and contradicting case F, case L and invariant 26. Withdrawn.

```text
The Context says WHICH exact trees, under WHICH capability contract, in WHICH form, over WHICH
namespace, must be proven.

It does NOT claim that either tree already passed. No verdict is a Context field, so every
capability outcome — capable, unsafe, unknown — yields the SAME valid, immutable Context, and
the Review can be launched in all three.
```

**Timing, and what the seal actually does:**

```text
1. The Candidate is frozen first (F2 §5), so `declared_base` and every entry are fixed.
2. The resulting tree is therefore fully determined BEFORE the Context is built. Its object id is
   computable at that point, which is all the Context needs.
3. The Context is built by naming the two tree ids, and becomes IMMUTABLE before generation 1
   accepts the task — which is what the TaskInput binds and what the reviewer is shown.
   It is built and is valid WHATEVER the resulting tree's capability turns out to be.
4. THE BASE capability remains an ENTRY requirement, unchanged (§7.4, §7.8): a base tree that
   fails it means no review-v1 Work starts at all, so no Context is reached. That refusal keeps
   its existing position and is not moved into the Context.
5. AT SEAL, the capability is DERIVED for exactly `Context.resulting_tree` — the bound object id,
   not a tree recomputed from anything:

       capable            the seal may proceed
       unsafe | unknown   NO Receipt, NO authorization (§7.9.5)

   The seal adds no field, changes no Context byte and computes no new review_context_hash.
```

```text
So the immutable identity bound into the Context, and used at seal, is exactly: the capability
contract identity, the form, the namespace, and the two exact tree object ids. The VERDICT is
derived, never stored — which is what lets an unsafe Candidate be expressible, reviewable and
unauthorizable at the same time.
```

#### 7.9.7 This requires a forward amendment — A-4

F2 §10.3 does not merely omit checkout capability; it states its absence and names the mechanism for
adding it. So this is a declared amendment and not a reinterpretation. See §1.5 A-4, and §1.5 A-5 for the
namespace ownership rule §7.8.4 needs.

---

### 7.10 C-1: how exact local commit identity becomes durable

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
     The S-c1 payload names mode "review-v1-work-local-v1"; the commit was made with the
     attribute source pinned to the tree of declared_base.base_commit (§7.1); and the Git
     persistence preflight of §7.3, evaluated UNDER THAT SAME PIN, passed IMMEDIATELY BEFORE the
     stage was recorded — topology step 17b, after the Review completed. Step 9's early run is an
     optimization and never satisfies this item, and an evaluation made against the working tree
     rather than the pinned source never satisfies it at all.

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
  replay-stable (R2 §2), so reserving it sooner cannot change what it yields. It is reserved
  sooner so that S-c2's exact path set is known — which the per-commit preflight of §7.3 needs
  for that commit, and which lets the reservation be replayed rather than re-decided.

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

IP-8  The commit primitive must pass the attribute-source pin on BOTH invocations — `attr.tree`
      (or GIT_ATTR_SOURCE) set to the base commit's tree, GIT_ATTR_NOSYSTEM=1, an empty
      core.attributesFile, GIT_CONFIG_NOSYSTEM=1, an empty GIT_CONFIG_GLOBAL, and a GIT_*-stripped
      environment. The mechanism is already proven live in review/checkout.py:171-215 (M-21); what
      is new is applying it to `git add` and `git commit` rather than only to `git check-attr`.
      This requires Git >= P3_WORK_ATTR_PIN_GIT_MIN (2.43.0), NOT 2.40: `check-attr --source`
      at 2.40 does not establish that attr.tree governs `git add` (§7.7.1). The capability
      probe of §7.7 is the binding authority regardless of the declared floor.

IP-10 The primitive must set core.autocrlf=false and core.eol=lf on both invocations. Measured,
      without them a CRLF result is normalized on check-in even with the attribute pin in place
      (M-23), and Git for Windows enables autocrlf globally by default.

IP-11 The capability probe of §7.7 must exist and must run before the first pinned commit of every
      review-v1 Work operation. `rules/git` gains P3_WORK_ATTR_PIN_GIT_MIN = 2.43.0 as its
      declared floor.

IP-12 The universal source predicate of §7.8 requires a parser over every .gitattributes blob in a
      tree, at every depth, plus .git/info/attributes — not a path probe. Its supported shape is
      narrow by design and refuses any [attr] macro.

IP-13 The seal precondition of §7.9 requires composing the resulting tree from the base tree and
      the Candidate's entries, and evaluating attributes with --source against it inside the
      contained scratch repository of M-21. The Work Review Context gains the bound
      checkout-capability claim of amendment A-4, which raises its version.

IP-9  The persistence evaluation must be made under the pin. The live
      require_effective_evaluation evaluates with no --source, i.e. against the working tree
      (M-22); the Work path needs the pinned-source form so that evaluation and storage cannot
      disagree.
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

FC-10  The attribute source of every commit this operation makes is pinned (§7.1.1), so
       committed object identity equals the Candidate's by construction. A transform assigned by
       the PINNED source itself is refused at START entry, before any mutation exists. No
       transform is ever disabled to obtain a pass, and no result the executor produces is ever
       refused for what it does to persistence semantics.

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
   classification   a legitimate ordinary Work result. NOT malformed, NOT refused.   §7.4.1
   Candidate        .gitattributes is an ordinary file entry, exactly as F2 §6.4 says
                    .gitmodules is; its new content is IN the Candidate and is reviewed
   material         an ordinary payload for it, like any other file entry
   why no case split
                    the pin (§7.1) fixes this operation's persistence semantics at the base
                    tree, so WHAT the new attributes cover does not matter to this operation.
                    The previous draft's K.1 / K.2 / K.3 split is gone with the refusals it
                    described.
   K.1  covers nothing this operation writes   -> proceeds as case A or B
   K.2  covers the TERMINAL paths              -> proceeds as case A or B
   K.3  covers this operation's RESULT paths   -> proceeds as case A or B
   Review-gen       generation commits are pinned too, so they are unaffected       §7.6
   K1               exists exactly as the artifact_kind says; its object ids equal the
                    Candidate's, measured, because the filter never runs               M-20
   C-2(K1)/C-2(K2)  W1...W12 and T1...T12 in full, unchanged
   publication      by the ordinary cardinality of §11.3.1
   Consumption      by the ordinary artifact_kind rules
   completion       P-1 ... P-6
   trap             NONE. There is no refusal in this case at all.

K'. OPERATION-OWNED .gitattributes COVERING THE REVIEW-GENERATION PATHS
   the second half of R9, called out separately because it is not on the K1 path
   classification   same as K: an ordinary result
   Review-gen       the generation commits are made under the pin, and their persistence
                    evaluation is made under the SAME pin, so evaluation and storage agree.
                    The live defect this closes is M-22: require_effective_evaluation reads the
                    WORKING TREE, which is what would otherwise refuse here.            §7.6
   disposition      PROCEEDS. No refusal after the executor returned.
   future checkout  a later clone checks out under the new attributes; F2 §10.3 scoped checkout
                    capability out of the Work Context, and the control is that the reviewer sees
                    the exact rule in the Candidate and may refuse it.                  §7.6
   trap             NONE

L. EXTERNAL DRIFT IN A NON-TREE ATTRIBUTE SOURCE
   classification   foreign interference, not this operation's product. Not producible as a Work
                    result: a result is a tracked repository path, and .git/info/attributes,
                    global and system sources are not.                                §7.4.1
   scope            the tree source cannot drift under the operation at all, because it is
                    pinned. Only non-tree sources remain.
   disposition      the per-commit preflight (§7.3) refuses before the affected commit;
                    reconcile. What recovery is attempted is F4's (§25).
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
Architecture blocker: NONE.

Every case above has a lawful continuation, and NO case is a refusal of what the executor
produced. The only transform refusal this contract has is at START entry, on a condition that is
knowable before execution (§7.4) — which is exactly where F2 §20.17 puts it.
```

### 21.5 Persistence-semantics case matrix

Every case the second re-review named, traced to an exact outcome. "committed id" means the object id Git
actually stores; it must equal `Candidate.new_oid` in every supported case, which is the staging-byte
contract of §7.1.

```text
 1. GIT AT EXACTLY P3_WORK_ATTR_PIN_GIT_MIN (2.43.0)
    entry        the floor passes; the capability probe of §7.7 then runs and must PASS on this
                 machine. The floor alone never authorizes anything.
    committed id == Candidate.new_oid, because the probe proved the pin holds here.
    outcome      SUPPORTED. Ordinary topology throughout.

 2. GIT ONE VERSION BELOW THE MINIMUM (2.42.x)
    entry        REFUSED, review_git_unsupported, before the Project execution lock and before
                 any mutation is opened. No event, no commit, no Review record.
    note         even if the floor were mis-stated, the probe would refuse this Git independently
                 (§7.7 item C). Both error directions are safe.

 3. WORKING-TREE .gitattributes ADDS A CLEAN FILTER (executor-authored)
    Candidate    .gitattributes is an ordinary file entry; its new content is reviewed
    committed id == hash-object --no-filters == Candidate.new_oid.   MEASURED, M-20/M-24
    filter       never invoked.                                      MEASURED, M-20
    outcome      SUPPORTED. No refusal of any kind.

 4. THE NEW FILTER TARGETS A RESULT PATH          same as 3. SUPPORTED, no refusal.
 5. THE NEW FILTER TARGETS A REVIEW-GENERATION PATH
                 the generation commits are pinned too, so storage is unaffected (§7.6).
                 SUPPORTED for storage; case 10 governs whether it can be AUTHORIZED.
 6. THE NEW FILTER TARGETS A TERMINAL PATH        same as 5. SUPPORTED, no refusal.

 7. BASE TREE CARRIES text / eol NORMALIZATION
    why it bites the pin honours the BASE, so a base rule DOES apply.  MEASURED, M-24
    entry        REFUSED by the universal source predicate (§7.8.2), before the lock.
    outcome      UNSUPPORTED BASE CONDITION, refused at entry, never post-executor.

 8. core.autocrlf = true  (or input)
    why it bites configuration, not an attribute: the pin does not reach it. MEASURED, M-23
    handling     the primitive sets core.autocrlf=false and core.eol=lf on both invocations
                 (§7.1), which restores raw identity.                  MEASURED, M-23
    committed id == Candidate.new_oid.
    outcome      SUPPORTED. This is the DEFAULT condition on Git for Windows, so it had to be.

 9. CRLF EXECUTOR BYTES
    Candidate    new_oid = hash_blob(the CRLF bytes as the executor left them), F2 §6.3
    committed id identical, because no text/eol attribute applies (case 7 refused those at
                 entry) and autocrlf is neutralized (case 8).          MEASURED, M-23
    outcome      SUPPORTED. The CRLF bytes are stored exactly, not normalized.

10. THE NEW .gitattributes WOULD MAKE .workline/review/** NON-CANONICAL ON A FRESH CLONE
    Candidate    FULLY EXPRESSIBLE. Frozen, material built, verified, reviewed. Nothing about the
                 executor's result is refused, so F2 §2.3 is untouched.
    seal         REFUSED. The seal precondition of §7.9.2 evaluates the RESULTING TREE and finds
                 a material attribute over this Run's canonical Review record paths.
    consequence  no Receipt, no authorization, no terminalization. The Run ends unsealed with the
                 reason recorded.
    outcome      EXPRESSIBLE AND REVIEWABLE, NOT AUTHORIZABLE. That distinction is the whole
                 point of placing the rule at seal rather than at Candidate freeze.

11. NESTED .gitattributes INTRODUCED BY THE EXECUTOR
    storage      unaffected: the pin resolves attributes from the base tree, at every depth.
    authorization the §7.9.2 proof enumerates the RESULTING TREE, so a nested source the executor
                 added is covered at whatever depth it sits (§7.9.3). A DELETED source is covered
                 too, because the proof is over the resulting tree rather than over the diff, so
                 a parent rule it had been overriding is seen once it is uncovered.
    outcome      SUPPORTED for storage; case 10's rule decides authorization.

12. A FUTURE / NOT-YET-EXISTING RESULT PATH MATCHED BY A BASE WILDCARD RULE
    e.g.         the base tree holds `generated/** filter=x` and the executor creates
                 generated/out.bin, a path that did not exist at entry.
    why a path-wise check fails  at entry the path does not exist, so probing paths finds nothing.
    entry        REFUSED by the universal source predicate (§7.8): the predicate parses the
                 SOURCE and refuses the `filter=x` assignment itself, regardless of which paths
                 will ever match it. `**/*.txt text`, `new/** working-tree-encoding=UTF-16` and
                 any `[attr]` macro are refused by the same rule.
    outcome      UNSUPPORTED BASE CONDITION, refused at entry, before the lock.
```

```text
Every SUPPORTED case has exact committed object identity equal to the Candidate's.
Every UNSUPPORTED BASE condition is refused at START ENTRY, before the mutation is opened.
The one case that is neither — case 10 — stays expressible and reviewable and is stopped at
authorization, which is not a refusal of a result shape.

No case is refused after the executor returns for what the executor produced.
```

### 21.6 Pinning-boundary case matrix

Columns, for every case: entry decision / Context identity / Candidate expressibility / Review launch
safety / Review-generation persistence / authorization / K1 existence / K1 identity / terminal safety /
fresh-clone Review readability / recovery state.

```text
A. S-c0 EXISTS (entry events not yet committed)
   entry      predicate proven over PRE_S_C0_BASE; probe passes
   Context    v2, both tree verdicts capable
   Candidate  expressible; declared_base.base_commit = post-S-c0 HEAD
   launch     safe; generation commits pinned to declared_base.base_commit
   review-gen persisted under the pin
   auth       granted if the seal recheck passes
   K1         exists iff artifact_kind = result_commit
   K1 id      == Candidate.new_oid, by the pin
   terminal   K2 ordinary; C-2(K2) T1...T12
   clone      form L holds over the resulting tree
   recovery   ordinary resume at the earliest unsatisfied checkpoint
   NOTE       S-c0 pins to PRE_S_C0_BASE, NOT to declared_base.base_commit, which does not yet
              exist. The circularity the re-review found is resolved in §7.1.1.

B. S-c0 ABSENT (event log already matches HEAD)
   as A, except PRE_S_C0_BASE == declared_base.base_commit and the distinction collapses. No
   stage is recorded, nothing is committed, and every later pin names the same tree.

C. BASE CONTAINS A LEGACY `crlf` WILDCARD MATCHING A FUTURE RESULT
   e.g.       `generated/** crlf`, and the executor later creates generated/out.bin
   entry      REFUSED, review_git_transform, before the lock. The parser expands crlf == text and
              refuses the assignment over the SOURCE, so the not-yet-existing path never matters.
              MEASURED material (M-25).
   everything else  does not arise: no mutation is opened.

D. BASE CONTAINS THE EXACT CANONICAL REVIEW CHECKOUT RULE
   e.g.       `.workline/review/** !text eol=lf -filter -ident -working-tree-encoding`
   entry      PERMITTED, and required by the capability claim. The pattern is confined to the
              reserved namespace, so RULE 1 does not judge it (§7.8.4).
   Candidate  expressible; no entry lies in the Review namespace (A-5), so the rule cannot touch
              any Candidate entry's stored bytes
   K1 id      == Candidate.new_oid: the rule applies only where no entry is
   clone      form L holds: this IS the configuration that makes it hold
   NOTE       this is the case the previous predicate would have refused, making every P2-capable
              Project incompatible with P3 Work Review.

E. OLD REVIEW RECORDS FROM EARLIER RUNS ARE PRESENT
   auth       the §7.9.4 surface covers EVERY canonical Review record path in the resulting tree,
              not just this Run's, so the old records are inside the proof
   clone      guaranteed for them too, by the same single `.workline/review/**` pattern

F. CANDIDATE ADDS A RULE AFFECTING ONLY AN OLD REVIEW RECORD
   Candidate  EXPRESSIBLE, frozen, verified, reviewed. Nothing is refused.
   auth       REFUSED at seal: the resulting-tree evaluation covers that old path (case E) and
              form L no longer holds there
   K1         none: seal failed, so no Receipt, no authorization, no K1
   recovery   §7.9.5 — generation 2 stays latest and open, the failure is an operation STOP, a
              retry re-evaluates, permanent set-aside is F4's
   NOTE       this is precisely the case the previous "this Run's paths only" surface missed.

G. CANDIDATE ADDS A NESTED .gitattributes AFFECTING THE REVIEW NAMESPACE
   Candidate  EXPRESSIBLE
   auth       REFUSED at seal: layer 2 of §7.9.3 requires the resulting tree to hold NO entry
              under .workline/ whose name folds to .gitattributes, and layers 1 and 3 read the
              root source's raw bytes and evaluate the committed source alone
   recovery   as F

H. CANDIDATE DELETES A NESTED .gitattributes AND UNCOVERS A PARENT RULE
   Candidate  EXPRESSIBLE
   auth       decided on the NET effect: the proof is over the resulting tree as a whole, not over
              the diff, so an uncovered parent rule is seen (§7.9.4). If form L still holds, the
              seal proceeds; if the uncovered rule breaks it, the seal refuses as in F.

I. WINDOWS-LIKE FRESH CLONE WITH core.autocrlf=true
   clone      Review records still check out as canonical LF, because `eol=lf` is an explicit
              ASSIGNMENT and overrides the reader's autocrlf. This is exactly why F3 adopts the
              canonical form-L rule rather than a "no attribute applies" test, which would have
              left this case to the reader's configuration (§7.9.3).
   storage    unaffected: the operation's own commits set core.autocrlf=false (M-23)

J. CONTEXT v2 BYTES BEFORE GENERATION 1
   timing     the Candidate is frozen first, so the resulting tree and its object id are known
              before the Context is built; both verdicts are proven then; the Context is immutable
              before generation 1 accepts the task and is what the TaskInput binds
   identity   review_context_hash covers review_checkout_capability, so the claim reaches the gate
              generations, the Receipt and the closure
   v1         a version 1 Context is not a Context of this contract version; the strict reader
              cannot confuse them (§7.9.6)

K. SEAL CAPABILITY PASS
   auth       the capability derived for Context.resulting_tree is `capable`; the seal issues
              the Receipt in the ordinary way; no Context byte changes

L. SEAL CAPABILITY FAILURE
   auth       NO Receipt, NO authorization, NO Consumption, NO K1
   gate       NO new generation written; generation 2 remains latest and `open`
   record     none: GATE_STATUSES has no third state and GateGeneration no reason field (M-27),
              so the failure is an operation STOP (review_checkout_unsafe / _unknown) carried in
              the operation result and runtime metadata
   clone      unchanged, because nothing was authorized or committed

M. RECOVERY AFTER SEAL CAPABILITY FAILURE
   retry      deterministic: the proof is over the resulting tree, so a retry reaches the same
              answer until something changes
   changes    the person adds the canonical rule to the Project, or the Work's result changes —
              which is a different Candidate and therefore a different Run
   deferred   invalidation, supersession or permanent set-aside of an unsealable Run is F4's
              recovery matrix; F3 writes no invalidation generation to imply one
```

```text
Every case has a determinate outcome. Every refusal is either at START ENTRY on a condition
knowable before execution (C), or at SEAL on authorization (F, G, H, L) — never a refusal of what
the executor produced. The one declaration refusal (a declared path inside the reserved Review
namespace, §7.8.4) is an OWNERSHIP violation of a rule that bound before the executor ran, with
its own identity `review_reserved_namespace`, declared as amendment A-5.
```

### 21.7 Capability-representation and namespace-ownership matrices

#### 21.7.1 Resulting-tree capability — every outcome must be representable

The point of these seven rows is that `unsafe` and `unknown` are **first-class**: they build a valid
Context, reach generation 1, and are reviewed. Only sealing is withheld.

```text
A. CAPABILITY = CAPABLE
   Candidate    expressible            Context v2   built, binds both tree oids
   generation 1 may exist              Review       occurs normally
   seal         capability re-derived for Context.resulting_tree -> capable -> Receipt issued
   outcome      ordinary authorization and the ordinary K1/K2 topology

B. CAPABILITY = UNSAFE, from a Candidate-authored root .gitattributes
   Candidate    EXPRESSIBLE — nothing about the result is refused
   Context v2   BUILT AND VALID. No verdict is a Context field, so an unsafe resulting tree is
                representable; this is exactly what the previous verdict-carrying schema made
                impossible (§7.9.6)
   generation 1 MAY EXIST; the TaskInput binds this Context
   Review       OCCURS — an external reviewer judges the Candidate normally
   seal         re-derives capability for Context.resulting_tree -> UNSAFE
                -> NO Receipt, NO authorization, NO Consumption, NO K1   (§7.9.5)
   outcome      EXPRESSIBLE + REVIEWABLE + NOT AUTHORIZABLE, which is the frozen boundary of
                §7.9.2 and invariant 26

C. CAPABILITY = UNKNOWN
   identical to B in every row, with `review_checkout_unknown` rather than
   `review_checkout_unsafe`. Unknown is never read as capable, and never as "invalid Candidate":
   the Candidate is fine, the authorization is not available.

D. CAPABLE AT CONTEXT-BUILD TIME, TRANSIENT info/attributes MAKES THE SEAL RECHECK UNSAFE
   Context      unchanged and still valid — it never claimed a verdict
   seal         layer 4's effective evaluation fails -> no Receipt, no generation-3 record,
                generation 2 stays latest/open
   note         this is a TRANSIENT, NON-TREE condition, so it is recoverable within the Run

E. THE TRANSIENT CONDITION IS RESTORED, SAME CANDIDATE RETRIED
   Context      NOT rebuilt; no Context byte changes; the SAME bound resulting_tree is re-derived
   seal         now capable -> Receipt issued
   proof        this is the same-Run recovery §7.9.5 permits, and it is permitted precisely
                because nothing about the Candidate, the base or the resulting tree moved

F. TRACKED .gitattributes CHANGED AFTER CONTEXT FREEZE
   retarget     NO. The Context binds `resulting_tree` by object id; a changed tracked source
                yields a DIFFERENT resulting tree, which that id does not name
   currency     FAILS: the Candidate's declared base / entries no longer reproduce, and F2 §16.1
                makes the change invalidating
   outcome      a NEW Candidate and a new Run are required; the old Run's disposition is F4's

G. CANDIDATE CHANGED AFTER CONTEXT FREEZE
   identical to F. A different Candidate is a different candidate_hash, a different resulting
   tree and a different Run. The same Run never silently retargets onto it.
```

#### 21.7.2 Reserved Review namespace — ownership, not shape

```text
A. ORDINARY RESULT PATH OUTSIDE .workline/review/**
   ordinary supported result. Expressible, stored under the pin at exactly Candidate.new_oid,
   reviewed, and authorizable on the ordinary conditions.

B. .gitattributes RESULT
   ordinary supported result. Same as A for storage and expressibility (§7.4.2). Its effect on
   the resulting tree's capability is an AUTHORIZATION question (§21.7.1 B), never a refusal of
   the result.

C. RESULT PATH EXACTLY INSIDE .workline/review/gates/**
   violation of the PRE-EXISTING review-v1 executor ownership contract (§7.8.4, A-5).
   refusal      StopError, code `review_reserved_namespace`
   framing      this is NOT an unsupported Git result shape. The blob there may be perfectly
                ordinary. What is refused is a DECLARATION OF OWNERSHIP over a namespace the
                invocation contract reserved before the executor ran — unowned state, which
                F2 §2.3 expressly permits refusing.
   no legacy    the pending review-v1 mutation does not downgrade to legacy (§7.4).

D. DELETION PATH INSIDE .workline/review/**
   identical to C. The ownership rule names result paths and deletion paths alike, because
   deleting a canonical Review record is exactly as much an assertion of ownership over it as
   writing one.

E. THE EXECUTOR DIRTIES THE REVIEW NAMESPACE BUT DOES NOT DECLARE IT
   not a Candidate entry — the reviewed surface is the DECLARED owned set, and this is not in it.
   It is therefore UNOWNED / CONTRADICTORY state, and it is never silently absorbed into the
   Candidate:
       the dirty-separability check refuses an operation whose pre-existing dirty state overlaps
         what it commits;
       `skills/review`'s precondition that every existing Review record reads canonically
         (`review_namespace_unreadable`) refuses the next Review-record write;
       and the seal's resulting-tree readability condition (§7.9.4) refuses authorization.
   It is never taken for a result, and never committed as one.
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
    F3 uses it at commit time, and extends what that identity denotes: the attribute-source
    pin and the line-ending configuration are part of the frozen primitive. That is the part
    §10.3 left to F3. §7.1.                                 A

23  F2 §6.2  "The reviewed surface is exactly result_paths U deleted_paths as the executor
    declared them."
    F3 excludes the canonical Review namespace from it, because the canonical Review checkout
    rule normalizes check-in bytes there (M-26) and a Candidate entry in that namespace would
    break the storage-identity invariant. No landed rule excludes it today - checked - so this
    is declared rather than assumed. FORWARD AMENDMENT A-5 (§1.5). §7.8.4.                     C

22  F2 §10.3 and §10.1  "Checkout capability is not bound in the Work Context.\"
    F3 binds a checkout-capability claim over the CANONICAL REVIEW NAMESPACE - not over the Work
    result, where §10.3's reason stands - because a Work result can now change persistence
    semantics and make the Run's own records unreadable in a fresh clone. §10.3 names "a Context
    version change" as the mechanism, and F3 uses exactly that.
    FORWARD AMENDMENT A-4 (§1.5), which also supersedes §10.1's exact Context record
    because a field cannot be added to a frozen exact schema otherwise. §7.9, §7.9.6.                                                        C

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

Five, all to landed F2, all declared in full in §1.5:
    A-1  F2 §5.3           base_commit's timing, and that it is K1's parent       row 19
    A-2  F2 §14.4, §16.1   the unqualified "every HEAD advance" consequence       row 3
    A-3  F2 §7.1/7.2/7.3   the result-bearing / no-K1 discriminator               row 21
    A-4  F2 §10.3, §10.1   checkout capability unbound, and the exact Context     row 22
                           record it has to be added to
    A-5  F2 §6.2           the reviewed surface excludes the Review namespace     row 23

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
PB-6  the Git persistence preflight runs immediately before EVERY commit a review-v1 Work
      mutation makes, for exactly that commit's path set, evaluated under the pinned
      attribute source, and a pass never carries between commits (§7.3)
PB-9  the attribute-source pin: every commit of a review-v1 Work mutation is made with
      attr.tree set to the tree of declared_base.base_commit and the system and global
      attribute sources neutralized, so committed object identity equals the Candidate's by
      construction and no filter program is reachable (§7.1, §7.4.2)
PB-10 an executor-authored change to Git persistence configuration is an ordinary Work
      result, committed and reviewed as an ordinary file entry, and is never refused
      (§7.4.1, §7.4.2)
PB-11 P3_WORK_ATTR_PIN_GIT_MIN = 2.43.0, and the capability probe that is the actual
      authority for whether the running Git honours the pin (§7.7)
PB-12 the primitive neutralizes core.autocrlf and core.eol, because they change check-in
      bytes and the attribute pin does not reach them (§7.1, M-23)
PB-13 the universal predicate over the attribute source, parsed rather than probed, which is
      what covers result paths that do not exist yet (§7.8)
PB-7  a review-v1 Work START is refused at entry, before the lock, when the PINNED source —
      the base tree, or a non-tree source — assigns any material attribute after alias
      expansion (filter, ident, working-tree-encoding, text, eol (and the alias crlf)), outside the reserved
      Review namespace (review_git_transform, §7.4, §7.8). This is the only transform refusal
      the contract has.
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
TM-8  the five forward amendments to landed F2 (§1.5), which a reader of F2 alone cannot
      discover from F2
TM-10 the seal precondition of §7.9: a Review may not seal unless the resulting tree preserves
      canonical Review checkout capability over the Review namespace, proven mechanically
      over that tree and never left to reviewer discretion
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
                                             primitive with the ATTRIBUTE SOURCE PINNED to the
                                             base tree, hooks, signing and every filter program
                                             mechanically denied (measured, M-20), line-ending
                                             configuration neutralized (M-23), a capability probe
                                             before the first pinned commit, and a universal
                                             predicate over the attribute source. The preflight
                                             binds every commit the operation makes — the
                                             Review's own generation commits included.
                                                                                    §7.1-§7.10

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

20. Every commit this operation makes — the entry-events commit, the Review's own generation
    commits, every pre-completion Work commit, K1 and K2 alike — is made with a pinned attribute
    source: S-c0 to PRE_S_C0_BASE and every later commit to declared_base.base_commit, which are
    the same attribute state because S-c0 commits the event log alone (§7.1.1). The Git
    persistence preflight runs
    immediately before each of them, over exactly that commit's path set, evaluated under that
    same pin. A pass never carries from one commit to another, and an evaluation made against the
    working tree never satisfies it.

23. The staging-byte contract holds exactly: Candidate.new_oid equals the index object after
    the actual staging and the committed object after the commit, for every supported Work
    result. It is made true mechanically — the attribute-source pin, the neutralized line-ending
    configuration, and the universal source predicate together — and never assumed from the
    absence of a clean filter.

24. The running Git is proven to honour the attribute pin by a positive capability probe before
    the first pinned commit. A declared version floor is a fast pre-check, never the authority,
    and no combination of a wrong floor and a passing probe can produce a commit whose identity
    differs from the Candidate's.

25. The condition that decides whether a Project may run a review-v1 Work is proven over the
    ATTRIBUTE SOURCE itself, finitely and completely, never by probing paths — because the result
    paths do not exist when the decision has to be made.

26. A Candidate whose resulting tree would destroy canonical Review checkout capability over the
    Review namespace remains fully expressible and reviewable, and cannot be sealed. Authorization
    is withheld by mechanical proof over the resulting tree; it is never left to reviewer
    discretion, and it is never a refusal of the Candidate.

27. The material byte-transform surface is complete and alias-expanded: text, eol,
    working-tree-encoding, filter, ident, the compatibility spellings crlf / -crlf / crlf=input,
    the built-in macro binary, and the configuration variables core.autocrlf and core.eol. A name
    is never judged as an opaque word.

28. The canonical Review namespace is reserved: no Candidate entry lies inside it, and the
    canonical form-L checkout rule is required there rather than refused. Those two together are
    what let the storage-identity invariant and canonical Review durability both hold.

29. Canonical Review durability is proven by the same exact form-L rule and the same four proof
    layers `skills/review` already freezes, evaluated over the RESULTING TREE and over every
    canonical Review record path in it — not only this Run's. It is never defined as "nothing
    applies under a neutralized test configuration".

30. The Work Review Context is version 2 and binds the capability claim, so review_context_hash
    covers it. The seal RECHECKS that bound identity and never adds or changes a Context byte.

31. A failed capability proof writes no Review record and invents no gate state: no new
    generation, no Receipt, no authorization, no Consumption, no K1. It is an operation STOP, and
    permanent set-aside is F4's.

32. No supported result shape is ever refused after the executor returns. An executor-authored
    change to Git persistence configuration is an ordinary Work result, committed and reviewed as
    an ordinary file entry; the pin makes what it covers irrelevant to this operation. The only
    transform refusal is at START entry, on the pinned source, which is knowable before
    execution.

21. A pending review-v1 mutation never downgrades to legacy. Legacy availability is a property of
    a separate later invocation, never a recovery mechanism for a mutation already pending.

22. A completed C-2 is a durable checkpoint, not timeless validity. Current validity is re-derived
    at every required boundary, a later canonical fact can make a passed proof stale, and
    staleness fails closed rather than being read as the proof having disappeared.
```

---

## 27. Implementation readiness

```text
Contract status              FROZEN (repaired after independent review, five times)
Architecture blocker         NONE
HUMAN decision               NONE
Forward amendment required   YES - five, to landed F2 only, declared in §1.5
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
