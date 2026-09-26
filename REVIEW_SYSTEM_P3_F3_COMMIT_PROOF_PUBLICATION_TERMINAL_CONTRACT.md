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
P3 F2              inherited EXCEPT the seven explicit forward amendments of §1.5 (A-1 ... A-7)
                   (F2-D1 ... F2-D17 otherwise unchanged)
F3                 this document: physical topology, proof, publication, terminal stage
F4                 deferred (§25)
```

Where F3 appears to say something an earlier freeze also says, F3 is a **specialization**: it narrows,
never widens. Every apparent collision was audited item by item in §22.

```text
F2 forward amendments:  YES - SEVEN (A-1 ... A-7), all stated in §1.5.
F3-only corrections:    ONE (C3-1), stated in §1.5, superseding nothing in F2.
```

They are declared there in full, with the exact superseded sentences and the narrow replacement.
**No historical file is edited**: F2 keeps its bytes, and the amendment lives here, which is the
same discipline F1 used for its amendments to P1 R4 and R5.

### 1.4 F1 and F2 decisions F3 preserves without change

Everything in this list is inherited exactly. What F3 does **not** inherit unchanged is the seven
statements named in §1.5 (A-1 ... A-7), and nothing else.

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
git_persistence identity "review-v1-work-local-v2" bound in the Context         F2-D7
    -> F3 amends the VALUE to "review-v1-work-local-v2" (A-7); the field, its
       position and its meaning are unchanged
isolated verification is a P3 responsibility                                    F2-D11
Evidence completeness is "unknown": fresh use allowed, all reuse refused        F2-D12
the ReviewValidityClosure and the HEAD-advance predicate                        F2-D13, F2-D14
the Receipt authorizes and never completes                                      F2-D15
the invalidation boundary                                                       F2-D16
```

---

### 1.5 Forward amendments to landed F2

TWO CATEGORIES, and they are not mixed. An earlier draft counted "eight amendments" while C3-1's
own text said it "supersedes nothing in F2" — which cannot both be true. The categories are now
distinct in name as well as in count:

```text
F2 FORWARD AMENDMENTS          A-1 ... A-7                            COUNT = SEVEN
                               each supersedes a NAMED SENTENCE of the landed F2 contract

F3-ONLY CORRECTIONS            C3-1  the generation mode dispatch     COUNT = ONE
                               supersedes NOTHING in F2. It corrects an assumption F3 itself
                               made about live code (`gitops.review_commit_effect` sets the
                               planning mode unconditionally), and it is recorded here only
                               because a reader comparing recorded modes must be able to find it.
                               The label A-8 is RETIRED; this is C3-1.
```

F3 supersedes seven statements of the landed F2 contract. The F2 file is not edited by either
category. Each is named exactly, with the sentence
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
suggestion. But F2 §16.1's row carries no such qualification: it lists "HEAD advances" flatly as invalidating.
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
match-the-base shortcut F2 §9.4.1 exists to forbid. So the uniform rule governs, and §7.2's empty payload list
is superseded for that case alone.

The narrow replacement is frozen in §6.7, and the reason it is forced is in §6.6. Everything else about
F2 §7 stands unchanged: the positive emptiness proof, the prohibition on a fake or synthesized K1, the rule
that a reader never infers the kind from the emptiness of `entries`, and the independence of the
Candidate's and the Consumption's `artifact_kind`.

**Why both cannot stand.** F2 §6.3 keeps an inert entry — one whose `old_kind`/`old_mode`/`old_oid` equal
its `new_*` — in the Candidate, "because what the executor declared is part of what is reviewed". So a Work
whose executor declares a result path it did not actually change has a non-empty `result_paths` and a
Candidate every one of whose entries is inert. Under F2 §7.1 that is not the empty kind, so it is
`result_commit`, so F3 would require a K1 — but the complete owned tree delta is empty, and a commit
over an empty delta is a SYNTHETIC EMPTY COMMIT, which F1 §11.2, F1 invariant 8 and F2 §20.5 prohibit
outright. Live START does not even record the stage (`_commit` filters by `changed_against_head` and
returns when nothing is left). The Candidate would demand a commit that is not permitted to exist.

```text
STATED PLAINLY, BECAUSE THE PRIMITIVE CHANGED. The earlier draft rested this on a MECHANICAL fact:
`git commit --only` refuses an empty delta. The object-driven primitive of §7.1.2 has no such
refusal — `write-tree` would return the parent's tree and `commit-tree` would happily commit it.
So the guard is now the RULE alone, and the rule is made explicit rather than left implied:

    O-5/O-6 MUST NOT run when the tree they would write equals the parent's tree.
    That condition STOPS, never commits. It is an INTERNAL ASSERTION, not a new refusal
    reason: §6.7's discriminator already routes an all-inert Candidate to artifact_kind
    "empty" with no K1 at all, so O-5/O-6 can only see an empty delta if the discriminator and
    the primitive disagree — a defect, reported as one. F3 adds no reason value for it.

Nothing else in this contract may lean on Git refusing an empty commit.
```

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

"Unchanged in name, order and meaning" is said of the FIELDS, and is exact: A-7 changes the VALUE
of `git_persistence` to "review-v1-work-local-v2" without touching the field, its position or what
the field means, which is still the Git persistence semantics identity. A-4 and A-7 are therefore
consistent as written, and this sentence says so rather than leaving a reader to reconcile them.
```

The narrow replacement, frozen in §7.9:

```text
1. THE CONTEXT IS VERSION 2 and gains a bound checkout-capability claim over the CANONICAL
   REVIEW NAMESPACE — not over the Work result. F2's reason for excluding it stands untouched
   for the result: a result's bytes are the executor's and are bound by Git object identity.

2. THE CLAIM BINDS THE PROOF TARGET ONLY, exactly five keys (§7.9.6):

       capability_contract    "review-v1-work-checkout-capability-v1"
       form                   "form-L"
       namespace              ".workline/review/**"
       base_tree              <full object id>
       resulting_tree         <full object id>

   NO VERDICT FIELD of any kind. `review_context_hash` covers the claim, and a Run whose Context
   does not carry it is not a Run of this contract version.

3. AN UNSAFE OR UNKNOWN RESULTING TREE STILL PRODUCES A VALID CONTEXT. Such a Run is built,
   reaches generation 1 and is reviewed normally. This is the whole reason the field carries a
   target and not a verdict.

4. AT SEAL, THE CAPABILITY IS DERIVED for exactly `Context.resulting_tree`. Success means the
   CANONICAL FORM-L PROOF of §7.9.3 holds — the exact rule

       .workline/review/** !text eol=lf -filter -ident -working-tree-encoding

   printing form L, under all four proof layers `skills/review` freezes. It is NOT the weaker
   "no material attribute applies" test, which the previous draft of this amendment still
   carried and which is withdrawn: that test says nothing about a fresh clone's own
   line-ending configuration, which is exactly what `eol=lf` is there to override.

5. THE PROOF PROTECTS THE COMPLETE REQUIRED DURABLE SURFACE — the whole canonical Review
   namespace as it stands in the resulting tree, every Run's records and not only this Run's,
   plus the records this seal is about to create and the Consumption path this authorization
   may later create (§7.9.4).

6. ONLY `capable` MAY ISSUE A RECEIPT. `unsafe` and `unknown` withhold authorization.

7. THIS IS NEVER A CANDIDATE REFUSAL. It is a SEAL precondition: the Candidate stays expressible
   and reviewable, and what it cannot do is receive authorization (§7.9.2).
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

#### A-5 — F2 §6.2 superseded, §6.5 extended, §2.3 retained: the reserved Review namespace

```text
F2 §6.2 says

    "The reviewed surface is exactly `result_paths ∪ deleted_paths` as the executor declared
     them — the same owned set START protects with declare_own_content and commits by exact
     path."

F3 supersedes it by ONE exclusion, and nothing else:

    A review-v1 Work may not declare a result path or a deletion path inside
    `.workline/review/**`.

    A Completed outcome that does so violates the pre-bound ownership contract (PR-8) and is
    refused as:

        ReconcileRequired(
            reason = "review_reserved_namespace"
        )

    recovery class   reconcile_required
    code             reconcile_required
    reason           review_reserved_namespace

    "Inside" is decided by the exact three-layer path-identity rule of §7.8.4 — canonical
    spelling, component-wise and case-insensitive namespace test including the Review root
    itself, and ancestor-only Project containment — and NEVER by a string prefix test.

    The refusal happens BEFORE declare_own_content (§5.1 steps 5b, 5c and 5d), so no ownership of
    the reserved path is ever asserted. No Candidate is built from that declaration.

    It is NOT `review_candidate_unavailable`, NOT a new StopError code, NOT a new exception
    class, and NOT a refusal of an unsupported Git result shape.

    A declaration whose path identity cannot be established at all is a DIFFERENT refusal:
    `review_candidate_unavailable`, F2 §6.5's own predicate, reused as a third instance of it
    rather than extended (§7.8.4). The two are never collapsed.
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

#### A-6 — F2 §6.2 superseded, §6.5 extended, §2.3 retained: the lifecycle event log

```text
F2 §6.2's reviewed surface has no exclusion for START's own lifecycle state either. F3 adds a
SECOND exclusion, on exactly the same footing as A-5 and for a reason A-5 did not have:

    A review-v1 Work may not declare a result path or a deletion path at

        .workline/events/events.jsonl

    A Completed outcome that does so is UNOWNED STATE, refused as

        ReconcileRequired(reason = "review_reserved_namespace")

F2 §6.5   EXTENDED, by the same ownership-based declaration-invalidity case A-5 added; this is a
          second instance of THAT predicate, not a third predicate.
F2 §2.3   RETAINED. An ownership violation of a rule bound before execution is unowned state,
          which §2.3 expressly permits refusing — not a refusal of a result SHAPE.
```

**Why this is needed, and why it could not be assumed.** §7.8.5 has the full argument; in short: the
deletion witness must bind a base identity at step 5d, which runs BEFORE S-c0, so the only base that
exists then is PRE_S_C0_BASE — while the Candidate measures `old_*` against `declared_base.base_commit`.
Those two commits differ at exactly one path, the event log. If an executor could declare that path, the
two bases would differ AT A DECLARED PATH and the witness's base identity would be the wrong one. Checked
against primary sources: nothing excludes it today, exactly as nothing excluded the Review namespace.

The earlier draft simply asserted "the event log is never a result path". That was an unsupported premise
rather than a rule, and it is replaced by this amendment rather than retained.

**Why the same reason value as A-5.** Both are the same condition — a declaration over state the
invocation contract reserved before the executor ran — and both reconcile identically. Splitting them
would distinguish two things that behave the same way, which is the ambiguity this contract removes
elsewhere.

---

#### A-7 — F2 §10.3: the value of `git_persistence`, and why it cannot stay `...-v1`

```text
F2 §10.3 binds the Work Review Context field

    git_persistence = "review-v1-work-local-v1"

and says three things about it: the field is the Git persistence SEMANTICS identity; the
behaviour that identity denotes is the CONTAINED COMMIT PRIMITIVE; and F3 owns its use at commit
time.

F3 changes the behaviour. §7.1.1 and §7.1.2 replace `contained_add` / `contained_commit` with a
CommitTreePlan built against the parent object, an isolated index, hash-object,
update-index --cacheinfo, write-tree, commit-tree, a durable prepared_commit_id and a
compare-and-swap update-ref. That is not the contained commit primitive, and calling it
"review-v1-work-local-v1" would make a landed F2 sentence false while leaving every reader's
comparison silently pointing at the wrong semantics.

FROZEN:

    git_persistence = "review-v1-work-local-v2"

for every commit a review-v1 Work operation makes.
```

**What changes and what does not:**

```text
THE FIELD'S MEANING    UNCHANGED. It is still the Git persistence SEMANTICS identity, in the same
                       record, at the same key, in the same position. A-4's statement that Context
                       v2 keeps F2 §10.1's nine fields unchanged in NAME, ORDER and MEANING stands
                       exactly as written.
THE FIELD'S VALUE      CHANGED, from "review-v1-work-local-v1" to "review-v1-work-local-v2",
                       because the semantics it names are different semantics.
F2 §10.3               SUPERSEDED as to the VALUE and as to the sentence that the identity denotes
                       the contained commit primitive. Everything else in §10.3 is retained.
THE PLANNING IDENTITY  UNTOUCHED. "review-v1-planning-local-v1" keeps its exact meaning and its
                       exact behaviour for every P2 planning Run (§7.1.7, C3-1).
```

```text
WHY NOT SILENTLY REDEFINE v1. A version identity exists so that a reader who has only the older
contract can tell that it does not understand this record. Redefining the string in place destroys
exactly that, and it would also have made three statements of this contract mutually
contradictory: F2 §10.3's "the contained commit primitive", §7.9.6's "F2 §10.3, unchanged", and
§7.1.2's replacement of that primitive. A new value resolves all three at once.
```

```text
A v1 CONTEXT IS NOT A CONTEXT OF THIS CONTRACT VERSION, and this compounds §7.9.6's existing
version rule: a record carrying git_persistence "review-v1-work-local-v1" describes a Run whose
commits were made by the contained primitive, which no review-v1 Work Run of this contract
version makes. The strict reader refuses it as it refuses a v1 field set.
```

---

#### C3-1 — F3-ONLY CORRECTION (not an F2 amendment): the Work Review's own generation commits

```text
Live `_finish_generation` (roadmap_review.py:1447) records its generation commit through
`gitops.review_commit_effect`, which sets

    effect.payload["mode"] = PLANNING_COMMIT_MODE = "review-v1-planning-local-v1"

UNCONDITIONALLY. F3 §7.6 puts the Review's own generation commits under the Work persistence
primitive, so for a Work Review Run those two cannot both hold.

FROZEN, and the discriminator is durable rather than inferred:

    a generation mutation whose invocation carries review_kind == "work-result-v1"
        -> mode "review-v1-work-local-v2", CommitTreePlan and O-1...O-8
    every other review_kind (roadmap, phase, and every other planning kind)
        -> mode "review-v1-planning-local-v1", behaviour EXACTLY as it is today

`_generation_invocation` (roadmap_review.py:1422) already writes `review_kind` into the generation
mutation's durable invocation, so the discriminator is read from recorded data and never guessed.
```

```text
THIS IS NOT A GLOBAL REDEFINITION. No planning Run's behaviour changes, no planning Run's recorded
mode changes, and the planning identity keeps its meaning. What changes is which of the two
identities a WORK generation commit names.

THIS IS NOT AN AMENDMENT TO F2, and it is no longer counted as one. F2 does not legislate
`_finish_generation`, so there is no F2 sentence to supersede: what this corrects is an assumption
F3 §7.6 itself made about live code. An earlier draft labelled it A-8 and counted it among the
forward amendments while simultaneously saying it superseded nothing — a contradiction, now
resolved by giving it its own class. It is still recorded in full, because a reader comparing
recorded persistence modes must be able to find it.
```

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

M-64  THE CONFIG-NEUTRALIZATION VARIABLES MAKE THE IDENTITY CAPTURE IMPOSSIBLE, AND THE STRIP
      ALONE ALREADY PROTECTS IT. MEASURED, in a Project whose identity lives ONLY in global
      config — `user.name = Global Person`, `user.email = global@example.com`, with NO
      repository-local `user.name` or `user.email` — and with hostile inherited GIT_AUTHOR_NAME,
      GIT_AUTHOR_EMAIL, GIT_COMMITTER_NAME, GIT_COMMITTER_EMAIL, GIT_INDEX_FILE,
      GIT_OBJECT_DIRECTORY, GIT_ALTERNATE_OBJECT_DIRECTORIES and
      GIT_CONFIG_COUNT / GIT_CONFIG_KEY_0=user.name / GIT_CONFIG_VALUE_0=ConfigEnvAttacker:

          STRIP EVERY INHERITED GIT_* ONLY, no injection
              git -C <root> config --get user.name   -> EXIT 0, "Global Person"
              git -C <root> config --get user.email  -> EXIT 0, "global@example.com"

          THE SAME, PLUS GIT_CONFIG_NOSYSTEM=1 AND GIT_CONFIG_GLOBAL=<empty file>
              git -C <root> config --get user.name   -> EXIT 1, EMPTY
              git -C <root> config --get user.email  -> EXIT 1, EMPTY

      So a universal allowlist that marks those two variables "always" makes §7.1.9 phase A
      IMPOSSIBLE for an ordinary Project. The two classes of §7.1.9 exist for exactly this.

      NOTE WHAT THE STRIP ALONE ALREADY DOES: the hostile `GIT_CONFIG_COUNT` /
      `GIT_CONFIG_KEY_0` / `GIT_CONFIG_VALUE_0` triple is itself `GIT_*`, so it is stripped and
      never reaches the capture — an environment-injected `user.name` cannot poison it either.

      PRECEDENCE IS PRESERVED BY THE CAPTURE. With a repository-local identity added, the same
      stripped capture returned `Real Person` / `real@proj`; with it removed again, `Global
      Person` / `global@example.com`. Ordinary system -> global -> local precedence, untouched.

      END TO END, global-only identity with all of the hostile variables above inherited: class A
      captured `Global Person` / `global@example.com`; class B then neutralized configuration,
      injected those values and ran commit-tree; and the raw commit object, read back under a
      stripped environment, held

          author    Global Person <global@example.com>
          committer Global Person <global@example.com>

      with no hostile value anywhere in it.

M-63  `git var ...IDENT` CONSUMES THE INHERITED ENVIRONMENT; `config --get` UNDER THE STRIP DOES
      NOT. MEASURED, in a Project configured `user.name = Real Person`,
      `user.email = real@proj`, whose global config says `Global Person`, with hostile inherited
      GIT_AUTHOR_NAME=Attacker, GIT_AUTHOR_EMAIL=evil@x, GIT_COMMITTER_NAME=AttackerC,
      GIT_COMMITTER_EMAIL=evilc@x:

          git var GIT_AUTHOR_IDENT                       -> Attacker <evil@x>
          git var GIT_COMMITTER_IDENT                    -> AttackerC <evilc@x>
          <GIT_* stripped> git -C <root> config --get user.name   -> Real Person
          <GIT_* stripped> git -C <root> config --get user.email  -> real@proj

      Repository-local values won over the global ones, so ordinary configuration precedence is
      preserved by the capture.

      END TO END, with GIT_AUTHOR_*, GIT_COMMITTER_*, GIT_OBJECT_DIRECTORY and GIT_INDEX_FILE all
      hostile, running phase A then phase B of §7.1.9, the raw commit object read back under a
      stripped environment held:

          author    Real Person <real@proj>
          committer Real Person <real@proj>

      and no hostile value appeared anywhere in it.

      AND WITH NO IDENTITY CONFIGURED AT ALL:
          <stripped> config --get user.name  -> EXIT 1, empty output, nothing invented
          <stripped> var GIT_AUTHOR_IDENT    -> EXIT 128, "Author identity unknown"
      Both refuse, so withdrawing `git var` costs nothing; `config --get` refuses more quietly and
      never guesses an identity from a fallback.

      NOTE ON WHAT ACTUALLY CLOSES IT: `git var` run UNDER the same strip also returned
      `Real Person <real@proj>`. The ORDERING — strip before capture — is what removes the
      poisoning; withdrawing `git var` removes the remaining ambiguity and its
      invent-an-identity fallback. §7.1.9 freezes both.

M-57  GIT'S REVISION VIEW IS NOT THE COMMIT OBJECT, AND GRAFTS PROVE IT. MEASURED on a linear
      chain C1 <- C2 <- C3 <- C4, with `.git/info/grafts` holding "C4 C1":

          rev-list --parents -n 1 C4        -> C1        <- the walker is LIED TO
          merge-base --is-ancestor C2 C4    -> FALSE     <- C2 genuinely IS an ancestor
          cat-file commit C4  | parent      -> C3        <- the stored object is UNAFFECTED

      The live helpers are exactly these two: `gitcmd.commit_parents` runs `rev-list --parents`
      (gitcmd.py:399) and `gitcmd.descends_from` runs `merge-base --is-ancestor` (gitcmd.py:412).
      So a graft file silently changes what every lineage answer built on them would say, and a
      one-time entry check cannot help — the file can be written at any moment during the Run.

M-58  A REPLACEMENT REF CHANGES `cat-file commit` TOO, SO THE RAW READER MUST CARRY THE SETTING.
      MEASURED, with `git replace -f C4 C1` active:

          cat-file commit C4  | parent                      -> (none: it read C1, a root)
          GIT_NO_REPLACE_OBJECTS=1 cat-file commit C4        -> C3, the true parent

      Reading the object is only raw when the replace mechanism is off for that invocation.

M-59  A SHALLOW BOUNDARY MAKES THE WALKER REPORT A ROOT WHILE THE OBJECT HOLDS PARENTS. MEASURED
      in a `--depth 1` clone whose HEAD is a merge commit:

          .git/shallow                      holds HEAD
          rev-parse --is-shallow-repository -> true
          rev-list --parents -n 1 HEAD      -> HEAD alone, NO parents   <- looks like a ROOT
          rev-list --count HEAD             -> 1
          GIT_NO_REPLACE_OBJECTS=1 cat-file commit HEAD
                                            -> TWO `parent` headers, b1296f37 and a9af4324
          cat-file -e <that parent>         -> ABSENT locally

      So the honest raw answer is "this commit has two parents and I cannot see them" — UNKNOWN,
      fail closed — and never "this commit is a root". A walker-based predicate would have
      concluded the latter.

M-60  RAW PARENT HEADERS SURVIVE A MERGE INTACT. MEASURED: a merge commit's
      `GIT_NO_REPLACE_OBJECTS=1 cat-file commit` printed exactly two `parent` headers, in order,
      equal to the two commits merged. Parsing the literal headers preserves count and order.

M-61  HOSTILE INHERITED GIT_* VARIABLES CHANGE THE OUTCOME, SO STRIPPING IS LOAD-BEARING.
      MEASURED, each one alone:

          GIT_AUTHOR_NAME="Attacker" GIT_AUTHOR_EMAIL="evil@x" commit-tree
              -> the commit carried `author Attacker <evil@x>`, although the Project's configured
                 identity was "Real Person <real@t>". Injecting the captured identity explicitly
                 overrode it back to "Real Person <real@t>".
          GIT_INDEX_FILE inherited
              -> silently redirects every index command to that file
          GIT_OBJECT_DIRECTORY pointed elsewhere
              -> `cat-file -e HEAD` EXIT 1: the repository's own commit became invisible

      GIT_AUTHOR_* beat configuration, which is why "inherited GIT_AUTHOR_* survive" and
      "user.name/user.email are captured and injected" cannot both be said: §7.1.9 says only the
      second.

M-62  A LOCKFILE CARRIES NO OWNER. MEASURED: an `O_CREAT|O_EXCL` `.git/index.lock` created by this
      session is ZERO BYTES — no pid, no host, no identity of any kind. Git's own protocol writes
      the NEW INDEX into that file and renames it over `index`, so a lock that is merely held is
      indistinguishable from any other. Nothing in the file, its name, its age, or the absence of
      a process proves whose it is, which is why §7.1.4 treats an existing lock as UNKNOWN and
      never deletes one.

M-48  THE EMPTY HOOKS DIRECTORY CONTAINS THE HOOKS THE NEW COMMANDS ACTUALLY REACH, AND THOSE
      HOOKS ARE REAL. MEASURED BOTH WAYS, with executable marker hooks installed in the default
      `.git/hooks` for pre-commit, commit-msg, reference-transaction, post-index-change and
      post-commit:

          with core.hooksPath = <empty dir>, running hash-object -w, read-tree, update-index
            --cacheinfo, write-tree, commit-tree, update-ref AND a real-index update-index:
            NO marker was written at all
          CONTROL, the SAME `git update-ref` WITHOUT the empty hooksPath:
            `reference-transaction` ran THREE TIMES
          CONTROL, a real-index `git update-index --cacheinfo` WITHOUT it:
            `post-index-change` RAN

      So the two hooks the object-driven primitive newly reaches — `reference-transaction` from
      O-7's `update-ref`, and `post-index-change` from the real-index refresh — are genuinely
      invocable, and `core.hooksPath` pointed at an empty plain directory is measured to contain
      both. This is what P1 R5 §4's external-process classification requires, and it is the
      containment, not `commit-tree`'s hooklessness alone (M-37), that covers them.

M-49  A REPLACEMENT REF SILENTLY SUBSTITUTES AN OBJECT FOR AN EXACT OID. MEASURED. With
      `git replace -f <P> <OTHER>` in place, for the exact commit id <P>:

          default              cat-file -p <P>      -> tree 0b996586...   (the REPLACEMENT's)
          default              rev-parse <P>^{tree} -> 0b996586...
          GIT_NO_REPLACE_OBJECTS=1  cat-file -p <P> -> tree 8b00ff5b...   (the TRUE object)
          GIT_NO_REPLACE_OBJECTS=1  rev-parse <P>^{tree} -> 8b00ff5b...

      So without the setting, "the object named by this OID" is not what the plan means by it:
      a parent, tree, blob or commit id can be read as another object entirely, and every
      identity this contract compares would be comparing the replaced view. §7.1.9 binds the
      setting for every command.

M-50  DEFAULT PATHSPEC SEMANTICS EXPAND A LEGAL FILENAME INTO ANOTHER PATH. MEASURED. With two
      tracked files `d/a1.txt` and `d/a[1].txt`:

          default                    git ls-files -- 'd/a[1].txt'  -> BOTH d/a1.txt AND d/a[1].txt
          GIT_LITERAL_PATHSPECS=1    git ls-files -- 'd/a[1].txt'  -> d/a[1].txt only

      `ls-tree` happened to match only one here, which is exactly why the setting is bound for
      EVERY command that consumes a declared path rather than chosen per command: which command
      globs is not a property this contract may rely on. F2 declares exact paths, never patterns.

M-51  NEUTRALIZING CONFIG REMOVES THE COMMIT IDENTITY, AND commit-tree THEN REFUSES. MEASURED, in
      a Project whose `user.name` / `user.email` live ONLY in global config:

          before neutralization   git config user.name  -> "Global Person"
                                  git config user.email -> "global@example.com"
          GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git commit-tree ...
                                  -> EXIT 128, "Author identity unknown"
          same, with the identity CAPTURED FIRST and passed as GIT_AUTHOR_* / GIT_COMMITTER_*
                                  -> commit made, and `cat-file -p` shows
                                     author/committer "Global Person <global@example.com>"

      So an ordinary Project would have become uncommittable purely because F3 neutralizes config
      for persistence safety. §7.1.9 freezes capturing the configured identity AFTER the GIT_*
      strip and BEFORE neutralization — by `config --get`, never by `git var ...IDENT` (M-63) —
      and supplying it explicitly.

M-52  GIT'S INDEX TRANSACTION IS AN O_EXCL LOCKFILE, AND HOLDING IT EXCLUDES EVERY ORDINARY GIT
      INDEX WRITE. MEASURED. After creating `.git/index.lock` with O_CREAT|O_EXCL:

          git add a/f.txt          -> EXIT 128, "Unable to create '.../.git/index.lock': File exists"
          git update-index ...     -> EXIT 128, same
          a second O_CREAT|O_EXCL  -> FileExistsError

      So a compare-then-write with NO gap is constructible: the lock is held across both.

M-53  THE ATOMIC CONDITIONAL INDEX TRANSACTION WORKS, AND PRESERVES FOREIGN STAGED STATE ON OWN
      PATHS AS WELL AS UNRELATED ONES. MEASURED end to end, with a person's unrelated `b/g.txt`
      staged AND a person's foreign `c/h.txt` staged ON AN OWN PLAN PATH:

          1  O_EXCL create .git/index.lock
          2  a concurrent `git add` -> EXIT 128 for the WHOLE transaction
          3  copy .git/index -> .git/wl-index.tmp
          4  read exact entries from the snapshot (GIT_INDEX_FILE=<tmp> ls-files --stage)
          5  a/f.txt entry == the expected old entry -> refreshed to f49b8164
             c/h.txt entry is FOREIGN               -> PRESERVED, nothing written for it
          6  os.replace(wl-index.tmp, .git/index)   -> atomic publish
          7  release .git/index.lock

      RESULT: a/f.txt refreshed; c/h.txt still `43751a14` (the person's staged bytes, untouched);
      b/g.txt still `17b11086` (byte-identical); and NO hook fired, the empty hooksPath holding
      for `post-index-change` too. A failure before step 6 leaves `.git/index` exactly as it was.

M-54  A LOCALLY ABSENT OBJECT FAILS CLOSED, AND PROMISOR CONFIGURATION IS DETECTABLE. MEASURED:

          GIT_NO_LAZY_FETCH=1 git cat-file -e <absent oid>  -> EXIT 128, "Not a valid object name"
          git config --get-regexp '^remote\..*\.promisor$'  -> names any promisor remote
          GIT_NO_LAZY_FETCH=1 accepted with exit 0 by hash-object, write-tree, rev-parse,
            ls-files and cat-file

      NOT MEASURED HERE, and said so rather than implied: a genuine demand-fetch could not be
      provoked in this environment, because a local `file://` server answers
      "filtering not recognized by server, ignoring" and the clone comes back complete. The
      setting is bound and §21.13 A requires the regression test; this contract does not claim to
      have observed a lazy fetch being suppressed.

M-55  THE LIVE PATH GRAMMAR ACCEPTS MORE THAN THE PREVIOUS DRAFT'S LAYER 1 DID. MEASURED against
      `mutation._safe_relative` itself:

          "caf\u00e9/x.txt"      NFC   -> True
          "cafe\u0301/x.txt"     NFD   -> True        <- BOTH forms are accepted today
          ".git/config"                -> True        <- no "Git-reserved name" rule exists
          "CON/x.txt"                  -> True
          "d/a[1].txt"                 -> True
          "d/a\0b.txt"                 -> True        <- no NUL rule exists
          "d/"                         -> False       \
          "/abs.txt"                   -> False       | already refused, so these are NOT new
          "a/../b.txt"                 -> False       |
          "C:/x.txt"                   -> False       /

      So requiring NFC would turn a declaration that is valid TODAY into a refusal — a
      post-executor refusal of a supported result shape, which F2 §2.3 forbids. §7.8.4 layer 1 is
      reduced to exactly this grammar.

M-56  `planned_write` IS THE LIVE WRITER'S OWN RENDERING, AND IT READS THE WORKING TREE. READ,
      mutation.py:1740. For `write_file` / `create_file` it returns the payload's content; for
      `add_relation` / `remove_relation` it re-renders the WHOLE ledger from
      `store.read_relation_file(...)`; for `append_event` it appends to `store.events_text()`.
      Two consequences the plan must respect:

          it is NOT a pure function of (parent object, recorded payload) — two of its four
            branches read the working-tree copy, so re-evaluating it at plan time would both
            trust that copy and, for an append, double-apply an event already written;
          the mutation DOES durably record a digest of what it planned to write before writing it
            (`record[_WROTE] = _text_digest(planned[1]); self._save()`, mutation.py:501) — a
            digest, not the bytes.

      §7.1.1 therefore computes plan material from the PARENT OBJECT plus the recorded payloads,
      by each kind's own rendering rule, and REQUIRES the result to match that recorded digest.

M-41  THE LIVE CONTROLLER RECORDS OWNERSHIP ONLY AFTER THE COMMIT PRIMITIVE RETURNS, AND THE GAP
      IS REACHABLE. READ, not inferred. `Mutation.apply` (mutation.py:501) classifies, then for an
      UNAPPLIED git_commit calls `_require_own_bytes_committed` and `_make_commit`
      (mutation.py:1394). `_make_commit` calls `controller.apply_effect(record)` — which makes the
      commit AND advances the ref — and only then reads `_commit_just_made`; the caller sets
      `record["applied"] = True` and calls `self._save()` AFTERWARDS. Its own docstring says so:
      "An interruption after the commit succeeded and before that save leaves neither."

      What makes that unsafe under the object-driven primitive is `_classify_commit`
      (mutation.py:2259). For a record that is NOT applied and has no recorded id it reaches

          changed = gitcmd.changed_against_head(repo, list(payload["paths"]))
          if head is not None and not changed:
              return MATCHING          # "nothing left to commit for these paths"

      so a crash between the ref advance and the save is classified MATCHING on retry, with NO
      owned commit id. P1 R5 §3.1 / §3.5 forbid exactly that: the branch state is not ownership.
      §7.1.2's prepared-commit checkpoint is what removes the gap.

M-42  THE PREPARED COMMIT IS FULLY VERIFIABLE BEFORE ANY REF MOVES, AND THE CAS RETRY IS EXACT.
      MEASURED. With PREPARED built by commit-tree and the ref still at the parent:

          git cat-file -e <PREPARED>      -> exists
          git cat-file -t <PREPARED>      -> commit
          git rev-parse <PREPARED>^{tree} -> EQUAL to the planned tree
          git rev-parse <PREPARED>^       -> EQUAL to the expected parent
          git log -1 --format=%B          -> the exact recorded message
          git update-ref <ref> <PREPARED> <expected-old>   -> succeeded

      So a resume that holds a durable prepared id never has to rebuild: it re-verifies THAT
      object and retries the CAS of THAT id.

M-43  THE FOUR RESUME STATES ARE DISTINGUISHABLE FROM THE PREPARED ID ALONE. MEASURED.
          ref == expected parent      -> CAS not yet applied              (case B)
          ref == PREPARED             -> the CAS landed                   (case C)
          ref != PREPARED and
            raw_descends_from(<ref>, <PREPARED>) -> YES                    (case F, descendant)
          CAS with a stale expected-old -> refused, "is at <actual> but expected <given>", and
            the ref was left unchanged                                     (case D)
      A missing or unreadable object answers `cat-file -e` negatively, which is case E.
      None of these readings is a branch-tip inference: each is a question asked ABOUT an id this
      operation durably recorded as its own.

M-44  NOT REFRESHING THE REAL INDEX IS NOT HARMLESS. MEASURED. After commit-tree + update-ref with
      no index write, with the executor's result in the working tree and the base entry still in
      the index:

          git status --short        ->  MM a/f.txt
          git diff --cached         ->  M  a/f.txt

      The path shows as modified in BOTH the index and the working tree, and the person's next
      ordinary `git commit` would record the OLD bytes back over the result just committed. So
      "leave the index alone" is a hazard, not a neutral choice; the live `git add` primitive
      updated the real index as a side effect and the object-driven one does not.

M-45  A CONDITIONAL, ENTRY-COMPARED REFRESH IS SAFE AND PRESERVES FOREIGN STAGED STATE. MEASURED,
      with a person's unrelated `b/g.txt` staged and our `a/f.txt` at its base entry:

          git ls-files --stage -- a/f.txt   -> the exact current entry, comparable
          entry == the expected base entry  -> refresh permitted
          git update-index --add --cacheinfo 100644,<new>,a/f.txt
          git status --short                -> our path CLEAN; only `M  b/g.txt` remains
          git ls-files --stage -- b/g.txt   -> BYTE-IDENTICAL, untouched

      And with a foreign entry staged on OUR path (the person staged different bytes there), the
      comparison sees `b2f3ae2a` rather than the expected entry and the refresh is REFUSED for
      that path — a person's staging intent is never overwritten.

      WHAT THIS IS NOT: Git exposes no compare-and-swap for the real index, so the read and the
      write are two invocations and a person staging in between is a real if narrow window. §7.1.4
      handles it by verifying afterwards and by making the whole step non-authoritative, and says
      plainly why that answer is acceptable for the index when it was NOT acceptable for the
      committed tree.

M-36  THE OBJECT-DRIVEN PRIMITIVE CLOSES THE STAGING RACE. MEASURED, git 2.54, UNDER ACTIVE
      SABOTAGE. A tracked `dir/file.txt` was committed, `dir` was then REPLACED BY A JUNCTION to
      a directory whose `file.txt` held different bytes — so `cat dir/file.txt` returned the
      foreign content — and the commit was then built WITHOUT resolving any working-tree path:

          GIT_INDEX_FILE=<isolated>  git read-tree <parent>
          git hash-object -w --stdin          <- the WITNESSED bytes, not the path
          git update-index --add --cacheinfo 100644,<oid>,dir/file.txt
          git update-index --add --cacheinfo 100755,<oid>,keep/exec.sh
          git update-index --add --cacheinfo 120000,<oid>,keep/link
          git update-index --add --cacheinfo 160000,<commit oid>,keep/mod
          git update-index --force-remove keep/doomed.txt
          git write-tree ; git commit-tree <tree> -p <parent> -m <message>

      RESULT, read back from the commit:

          dir/file.txt   924c75cd  == the WITNESSED blob
          the junction's foreign blob was b2f3ae2a and DOES NOT APPEAR
          100755, 120000 and 160000 entries all present with their exact ids
          keep/doomed.txt absent from the tree
          HEAD unchanged; the primitive moved no ref and wrote no working-tree file

      So with the redirection ACTIVE THROUGHOUT, the committed tree still holds exactly the
      witnessed artifact. The race is not detected-after-the-fact; it is IMPOSSIBLE, because no
      working-tree pathname is resolved between the identity proof and the committed tree.

M-37  `commit-tree` RUNS NO HOOKS AND APPLIES NO SIGNATURE. MEASURED. With executable
      `pre-commit` and `commit-msg` hooks installed, a commit built as above ran NEITHER (the
      hooks' marker file was never created). With `commit.gpgsign=true` AND a deliberately broken
      `gpg.program`, `commit-tree` still succeeded and produced the IDENTICAL commit id, so it
      does not honour `commit.gpgsign`; `--no-gpg-sign` is accepted and yields the same id.
      Hook and signing containment are therefore properties of the plumbing itself, not of
      configuration this operation must fight.

M-38  REF UPDATE IS A REAL COMPARE-AND-SWAP. MEASURED.
          git update-ref <ref> <new> <expected-old>
      with a WRONG expected-old refused — "cannot lock ref ...: is at <actual> but expected
      <given>" — and left the ref unchanged; with the correct expected-old it succeeded. So the
      branch advance can be made conditional on the exact parent rather than on a re-read tip.

M-46  THE GITLINK OID IS OBTAINABLE ENTIRELY THROUGH HANDLE-BOUND READS, WITH NO `git -C` AND NO
      PATHNAME RE-RESOLUTION. MEASURED, against a real submodule, using `workline.review.fsafe`'s
      own cross-platform primitives and no Git process at all:

          fsafe.walk(root, ["sub"])                 -> proven handle to the submodule directory
          .read_file(".git")                        -> b'gitdir: ../.git/modules/sub\n'
          the components are ['..', '.git', 'modules', 'sub'], and '..' steps back to a handle
            ALREADY HELD by the same chain
          fsafe.walk(root, [".git","modules","sub"]).read_file("HEAD")  -> 'ref: refs/heads/master'
          fsafe.walk(root, [".git","modules","sub","refs","heads"]).read_file("master")
                                                    -> f600f63fd1c8ea463c51608453299e0a1a9a200c

      and `git -C sub rev-parse HEAD` returns EXACTLY `f600f63fd1c8ea463c51608453299e0a1a9a200c`,
      while `git ls-files --stage sub` shows `160000 f600f63f...`. So the handle-bound read
      reproduces Git's own answer without ever handing a pathname to a second process.
      MEASURED ALSO: a submodule's `.git` is a FILE holding a RELATIVE gitdir, not a directory, so
      the indirection §7.8.4 must resolve is real and is the one place the chain could leave the
      held handles. §7.8.4 resolves it against the held chain and fails closed otherwise.

M-47  A FINAL COMPONENT'S IDENTITY IS OBTAINABLE WITHOUT DEREFERENCING IT, AND AN `O_NOFOLLOW`
      OPEN IS THE WRONG PRIMITIVE FOR IT. MEASURED on NTFS with a junction `jn` -> `real`:

          os.lstat("jn")   reparse=True   st_ino=11258999074582616   <- the JUNCTION ITSELF
          os.lstat("real") reparse=False  st_ino= 4785074610237389
          os.stat("jn")    (following)    st_ino= 4785074610237389   <- the TARGET

      The no-follow identity of the indirection is its OWN identity and differs from its target's.
      On Windows `S_ISLNK` is False for a junction while
      `st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT` is True, so the reparse attribute is the
      discriminator there, not `S_ISLNK`.
      MEASURED ALSO: `os.supports_dir_fd` is EMPTY on Windows, so `dir_fd` is unavailable there and
      the handle-bound form must be the `NtCreateFile(RootDirectory=..., FILE_OPEN_REPARSE_POINT)`
      backend `fsafe` already carries; on POSIX it is
      `os.stat(name, dir_fd=parent_fd, follow_symlinks=False)` — `fstatat(..., AT_SYMLINK_NOFOLLOW)`.
      An `O_NOFOLLOW` OPEN cannot serve: on POSIX it REFUSES a symlink with ELOOP instead of
      identifying it, which is precisely how the previous draft wrongly turned a valid F2 symlink
      result into `review_candidate_unavailable`.

M-39  THE GITLINK'S NEW OID HAS AN EXACT SOURCE. MEASURED. After moving a submodule's HEAD,
      `git add <submodule-path>` staged `160000 a4937a0df268...`, and
      `git -C <submodule-path> rev-parse HEAD` returned exactly `a4937a0df268...`. So the value
      Git records for a gitlink is the SUBMODULE REPOSITORY'S HEAD COMMIT, read from that
      repository — not a branch name, not the superproject's old index entry, and not anything
      derived from directory contents. This measurement establishes WHAT VALUE is correct; it is
      NOT the mechanism F3 freezes, because `-C` re-resolves a pathname. §7.8.4 obtains the same
      value by handle-bound reads (M-46).

M-40  `hash-object -w --stdin` WRITES ONLY AN OBJECT. MEASURED: it returned the blob id, and
      afterwards HEAD was unchanged and `git status` reported nothing — no ref moved and no
      working-tree file was written. Without `--path` no attribute or filter machinery is
      consulted at all, so the id it returns is the raw-bytes id, which is exactly F2 §6.3's
      `new_oid`.

M-32  A GITLINK CANNOT SATISFY THE CURRENT OWN-CONTENT GUARD. MEASURED, on a real submodule.
      A gitlink path is a DIRECTORY, so in `_content_digest`: `is_symlink()` is False, `exists()`
      is True, and `read_bytes()` raises IsADirectoryError, which the except clause turns into
      `None`. `declare_own_content` therefore stores the `_UNREADABLE` string. The later guard
      `_require_own_bytes_committed` compares `_content_digest(abs(path)) != expected`, i.e.

          None  !=  "unreadable"      ->  True  ->  the path is classified FOREIGN

      so a CHANGED gitlink result is refused by the own-content guard and its commit never
      happens. Measured exactly that way: tree entry `160000 commit 40755bbb...`, digest `None`,
      stored `'unreadable'`, comparison unequal.

      Consequence for this contract: the previous claim that the witness needs "no recorded form
      changes and no downstream reader changes" was FALSE, and is withdrawn. §7.8.4 freezes a
      per-kind witness and IP-16 names the runtime extension it needs.

M-33  MODE IS NOT IN THE OWN-CONTENT FORM AT ALL. `_content_digest` produces `_BYTES`, `_LINK`,
      `_ABSENT` or `None`; none of them carries the Git mode. So `100644` vs `100755` is invisible
      to the own-content guard, while F2 §6.3 makes `new_mode` part of Candidate identity. A
      chmod between the witness and staging is therefore not detected by that guard today.

M-34  WINDOWS: GIT DOES NOT REFUSE AN ANCESTOR JUNCTION AT STAGING. MEASURED.
      With a tracked `dir/file.txt`, `dir` removed and replaced by a junction to `elsewhere`
      (`fsutil reparsepoint query` reports tag 0xa0000003, IO_REPARSE_TAG_MOUNT_POINT):

          git add -- dir/file.txt        ->  EXIT 0, and it staged b2f3ae2a, the blob from
                                             `elsewhere/file.txt`, NOT HEAD's 4b48deed

      So Git does NOT mechanically fail closed on Windows ancestor indirection. The independent
      re-review's POSIX measurement — `fatal: pathspec 'dir/file' is beyond a symbolic link` —
      is reported here as THEIR measurement; this environment is Windows only and could not
      reproduce it.

M-35  BUT THE OWN-BYTES GUARD DOES CATCH THE HARMFUL CASE. MEASURED, same fixture.
      `_content_digest` resolves by pathname too, so it follows the junction and reads the
      foreign bytes:

          digest through the junction   bytes:c11b5b87...
          digest recorded at witness    bytes:25718360...
          equal?                        NO  ->  FOREIGN  ->  STOP, nothing staged

      And when the redirected file holds the SAME bytes, the staged blob is byte-identical to
      the witnessed one (`4b48deed` both sides), so there is no identity breach to detect.
      An ancestor redirection therefore either changes the artifact's bytes — and is caught — or
      does not change them, and is harmless. §7.8.4 turns this into the frozen argument, and
      extends it to mode and gitlink identity, which M-33 and M-32 show the current form misses.

M-30  ABSENCE IS ALREADY A REPRESENTABLE OWNERSHIP STATE. `mutation._content_digest`
      (mutation.py:190-208) returns the `_ABSENT` sentinel for a path that does not exist, the
      `_LINK` form for a symlink — read by `os.readlink` and NEVER followed — and `_BYTES`
      otherwise; only an OSError/ValueError yields `None`, which `declare_own_content` records as
      `_UNREADABLE`. So a deleted path's own-content state is `_ABSENT`, a normal recorded value,
      and NOT an error. And `completion_precheck` requires a deleted path to be absent and to be
      a tracked file (start.py:353-358) — it requires nothing of the path's PARENT directory.

M-31  fsafe's POSIX LIMITATION IS ABOUT CREATES, NOT READS. Its module docstring lists
      `openat(parent_fd, name, O_NOFOLLOW ...)` as "relative to the proven fd (reads only)"
      (fsafe.py:18), and separately warns that "an fd pins nothing: the directory it holds can be
      renamed anywhere" (fsafe.py:42), which is why an immutable CREATE is refused on POSIX
      before anything is opened. The ownership snapshot of §7.8.4 creates nothing — it captures
      what the executor already produced — so the handle-bound read is exactly the supported
      case, and the placement limitation does not apply to it. §7.8.4 states this explicitly.

M-28  THE CANONICAL-SPELLING PREDICATE ALREADY EXISTS AND IS ALREADY ENFORCED.
      `mutation._safe_relative` (mutation.py:333) returns false for a path that is empty, not a
      string, absolute (`startswith("/")`), drive-qualified (`":" in path.split("/")[0]`, which
      also catches a UNC path once backslashes are separators), or that holds any empty, `.` or
      `..` component. `validate_effect` applies it to every `git_commit` path, so a declaration
      failing it could never reach a commit anyway — the Git stage would raise. What F3 needs is
      the same predicate applied EARLIER, before ownership is asserted.

      Also measured: `review.paths.is_review_path` is only
      `relative.startswith(".workline/review/")`, and `ProjectStore.abs` is `root / relative`.
      So a naive `is_review_path` over the slash-replaced declaration does NOT close
      `./.workline/review/gates/x.yaml` or `.workline/runtime/../review/gates/x.yaml`: the
      prefix test says "not Review", while `root / relative` reaches the Review namespace.
      That is exactly why §7.8.4 freezes a three-layer rule instead of a prefix test.

M-29  THE ANCESTOR-CONTAINMENT MECHANISM ALSO EXISTS. `review.fsafe.walk(root, parts)`
      (fsafe.py:601) walks from the Project root one component at a time, following nothing,
      refusing anything present that is not a plain in-Project directory, and holding a handle to
      each. Its module docstring states the reason F3 relies on: checking a path and then using
      it are two operations, and a component can be replaced in between — which is why the proof
      binds to the directory object rather than to the name. F3 reuses that discipline for the
      ANCESTORS of a declared path and never for its final component.

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
S-c0 is recorded BEFORE the Candidate is frozen, at §5.1 step 9a — after the declaration checks
of 5b-5d, the ownership assertion of 6, the completion precheck and the separability and
persistence preflights — and it commits the event log alone. The earlier wording "immediately
after the executor returns" is withdrawn: steps 5a through 9 precede it.

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

This timing and lineage rule is the physical consequence of **forward amendment A-1** (§1.5), which
supersedes both relevant clauses of F2 §5.3 — the timing of `base_commit` and the statement that it is
what F3 will require as K1's parent. It is not a specialization, and the earlier draft's claim that "every
normative clause of F2 §5.3 still holds exactly" is withdrawn as inconsistent with A-1 and with §22 row 19.

F2 §5.3's remaining, unaffected requirements continue unchanged: `base_commit` is a full commit id of
HEAD, every `declared_base` field is read from that commit's committed state through the canonical loader,
and it is the lineage the result is measured against. The entries' `old_*` are unaffected, because the
event log is never a result path — which is not an assumption but the ownership rule of
§7.8.5, declared as forward amendment A-6 (§1.5). §22 row 19, row 24.

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
git persistence        "review-v1-work-local-v2"      F2-D7, used at commit time by F3 (§7)
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
 5a normalize the declared result_paths and deleted_paths ONLY as the pre-existing START API
    already normatively normalizes them: `p.replace("\\", "/")`, and nothing else
                                                           start.py:876, unchanged
 5b CANONICAL SPELLING                                     §7.8.4 layer 1, §7.8.6 step 1
    Establish the path's exact canonical spelling by EXACTLY the landed predicate
    `mutation._safe_relative` and nothing further: non-empty string, no leading `/`, no drive
    letter in the first component, and no empty, `.` or `..` component (a trailing `/` is already
    refused, as an empty last component). This is a LEXICAL step; it opens nothing.
    NO ADDITIONAL GRAMMAR. An earlier draft also demanded NFC, a NUL rule and "no component that
    is a Git-reserved name". All three are withdrawn: MEASURED (M-55), the landed predicate
    accepts BOTH NFC and NFD, accepts `.git/config`, and accepts a NUL — so each of those rules
    would have turned a declaration that is valid TODAY into a post-executor refusal of a
    supported result shape, which F2 §2.3 forbids, and "Git-reserved name" was never defined.
    A path Git genuinely cannot store fails at §7.1.2 O-3/O-4 as an unsupported Git object, where
    it actually fails, rather than at a new invented grammar boundary.
    Failure -> review_candidate_unavailable, and NOTHING FURTHER about this path is evaluated.
 5c RESERVED OWNERSHIP CLASSIFICATION                      §7.8.4 layer 2, §7.8.5,
                                                           A-5 and A-6, PR-8
    With the spelling fixed, classify the path against the two namespaces the invocation
    contract reserved BEFORE the executor ran:

        .workline/review  and  .workline/review/**      A-5   the canonical Review namespace
        .workline/events/events.jsonl                   A-6   the lifecycle event log

    by the ASCII case fold AND, where the canonical directory exists, by filesystem object
    identity (§7.8.4 layer 2; object identity is the authority, the fold is a pre-filter).
    If a declared result path OR a declared deletion path is classified reserved:

        ReconcileRequired(reason = "review_reserved_namespace")  and STOP

    and NOTHING FURTHER is evaluated for it — in particular 5d never runs on it, so a reserved
    path can never be downgraded into the generic malformed refusal merely because its final
    object happens to be a directory (§7.8.6).
 5d CONTAINMENT and the BOUND OWNERSHIP WITNESS            §7.8.4 layer 3, §7.8.6 step 3
    For NON-RESERVED paths only. Walk the ancestor chain with no-follow semantics and produce a
    BOUND OWNERSHIP WITNESS, captured relative to the proven parent handle, carrying path, kind,
    git_mode, identity and — where the kind has material — the material bytes. A result whose
    containment or identity cannot be established is MALFORMED and fails closed; for a deletion
    a MISSING ancestor positively proves absence and is accepted, while an existing-but-
    unprovable ancestor fails closed.

    On ANY failure at 5b, 5c or 5d:
            no declare_own_content        no _OWN_CONTENT note
            no completion_precheck        no dirty-separability check
            no Candidate projection       no Review of any kind

    The precedence is the point: declare_own_content writes the _OWN_CONTENT note through
    set_note, which calls _save() (measured), so it is a DURABLE assertion that these paths are
    START's own. A path whose spelling is not canonical, that the invocation contract says START
    may never own, or whose containment cannot be proven, must not first be durably recorded as
    START-owned and only then refused.
 6  OWNERSHIP ASSERTION: persist the already-bound witness from 5d, for paths that passed 5b,
    5c and 5d. The declared path is NOT re-read by ordinary pathname here, so the recorded
    identity is the identity that was proven. This is declare_own_content's existing guarantee,
    reached without a second root-relative resolution, over the per-kind witness form of IP-16
    rather than over a single content digest         start.py:884, see IP-15 and IP-16
 7  completion_precheck passes                            skills/start, unchanged
 8  dirty separability over the owned set                 gitops.ensure_separable, unchanged
 9  Git persistence preflight over the owned set, under the pin  §7.3
 9a durable  S-c0 recorded and applied, if anything is uncommitted in the event log   §4.3
10  the Work Candidate is frozen                          F2 §5, §6
11  the CandidateSnapshot material envelope is built      F2 §9.3
11a the RESULTING TREE identity becomes computable: base tree + the Candidate's entries,
    fully determined by what step 10 froze                §7.9.2
11b          the Work Review Context v2 is built. It is NOT a durable checkpoint yet: its
             first canonical durable binding is generation 1 (§5.3)            §7.9.6
             it binds capability_contract, form, namespace, base_tree, resulting_tree —
             the proof TARGET, never a verdict, so a Context is built and valid whatever
             the resulting tree's capability turns out to be
12  isolated verification runs against the exact Candidate F2 §13.4 V-1 ... V-5
             under that Context: F2 §13.4 V-4 binds review_context_hash into the Evidence
             identity, which is why the Context precedes this step and not the reverse
13  durable  gate generation 1: accept, with the snapshot and the TaskInput  R3, M-12
             -> its own generation mutation commits them and proves them persisted
             the TaskInput binds review_context_hash (M-2), so the Context is already frozen
14  the reviewer is launched and returns                  F2 §12
15  durable  gate generation 2: settle                    -> committed by its own mutation
15a THE CHECKOUT-CAPABILITY DECISION, before ANY generation-3 canonical effect is recorded:
    derive the capability for exactly Context.resulting_tree, by the four layers of §7.9.3

        capable          -> step 16 may proceed
        unsafe|unknown   -> STOP exactly as §7.9.5: no generation-3 record, no Receipt, no
                            authorization, no Consumption, no K1, nothing published;
                            generation 2 remains the latest generation and stays `open`;
                            the Candidate stays expressible and reviewed, and this operation
                            ends without authorization
16  durable  gate generation 3: seal, issuing the Receipt -> committed by its own mutation
             reached only on `capable` at 15a
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
R-6a SPELLING, THEN RESERVED OWNERSHIP, THEN CONTAINMENT, THEN ASSERTION — in that order, and
     the order matters more than the step numbers:

         5b  CANONICAL SPELLING    lexical; opens nothing
         5c  RESERVED OWNERSHIP    both reserved sets proven absent — A-5's Review namespace and
                                   A-6's event log — by the ASCII fold as a pre-filter and
                                   FILESYSTEM OBJECT IDENTITY as the authority
         5d  CONTAINMENT + WITNESS the ancestor chain proven, the bound witness captured
         6   OWNERSHIP ASSERTION   declare_own_content

     WHY 5c PRECEDES 5d, which the earlier draft had the other way round: a reserved path may be
     a DIRECTORY — `.workline/review` itself is one — and a directory is not a valid result
     object. If containment ran first it would classify that declaration as malformed and the
     reserved refusal would never be reached, giving two answers for one declaration. Refusing
     first on ownership makes the answer unique (§7.8.6).

     All three checks run before declare_own_content, before completion_precheck and before any
     dirty-separability check, because declare_own_content durably records the declared paths as
     this mutation's own. No refusal of a declaration may follow a durable assertion of the very
     ownership it refuses, and no ownership decision may be made about a path whose spelling has
     not been fixed — a decision about an ambiguous path is not a decision.
R-6b THE OBJECT PROVEN IS THE OBJECT ASSERTED, AND IT IS THE OBJECT COMMITTED. The containment
     proof of 5d produces a bound witness and step 6 persists it; the declared path is never
     resolved a second time from the Project root for the ownership snapshot. Checking a name and
     then using the name are two operations, and a component can be swapped between them (fsafe,
     M-29) — so the capture is bound to the proven directory object, not repeated by pathname.
     The chain does not stop at the assertion: §7.1.2's primitive carries the witnessed bytes and
     identities into the commit itself, so no step between the proof and K1's tree resolves a
     working-tree pathname (M-36).
R-7  Each step marked `durable` completes its save before the step below it runs. An interruption
     between them resumes at the earliest unsatisfied checkpoint and re-derives, never re-decides.
```

### 5.3 The Context's durability before generation 1

The Context must exist before isolated verification, because F2 §13.4 V-4 binds
`review_context_hash` into the Evidence identity. That is an ORDERING requirement and not a durability
claim, and the previous draft conflated the two by marking step 11b `durable` and its resume table
"11b recorded"
while defining no carrier for it. Withdrawn. The frozen model:

```text
BEFORE GENERATION 1
    the Context is computed and used, and NOTHING durably carries it. There is no mutation note,
    no runtime record and no canonical record that holds it, and this contract does not invent
    one.

    A crash before generation 1 has durably committed the TaskInput and gate 1 therefore loses
    the Context. The resume:
        1. re-establishes the still-valid Candidate and base ownership facts;
        2. recomputes the CURRENT exact Context;
        3. reruns the isolated verification under THAT recomputed Context;
        4. generation 1 then makes that Context the first durable binding.

    THE RECOMPUTED review_context_hash MAY DIFFER from the lost in-memory one. The previous
    draft claimed sameness was guaranteed "because every input is fixed"; that is too strong and
    is withdrawn. Two Context fields are content identities of the configured Workline root's
    CURRENT working tree, not of committed or pinned state:

        loader_identity    the content identity of the running implementation package
        authority          the digests of registry.md and the bound Skills (F2 §10.2)

    The live implementation-identity check proves the running package comes from the configured
    root. It does NOT prove that root is committed, clean, unchanged or a fixed release. So an
    authority or loader update between the crash and the retry changes the recomputed hash.

    That is NOT reuse of a prior Review and NOT a retarget: no Review Context had been durably
    bound yet, so there is nothing to reuse or retarget. It is the first binding, taken from
    current authority.
```

```text
GENERATION 1 IS THE FIRST CANONICAL DURABLE BINDING
    the TaskInput carries `review_context_hash` (M-2) and the gate generation carries it too
    (M-3), and the generation mutation commits both and proves them persisted (M-12).

AFTER GENERATION 1 — recovery has an exact, concrete source
    F2 §12.3 freezes that the request envelope contains `context: <the whole Work Review Context
    record>`, and the TaskInput binds that envelope (M-2). Therefore:

        the exact Context BYTES are durably recoverable from
            TaskInput.request_envelope.context
        `review_context_hash` verifies and binds those bytes;
        a resume READS that exact Context;
        it NEVER reconstructs the Context from the hash, and never recomputes it.

    The Context is IMMUTABLE from here: never rebuilt, never recomputed, never retargeted.

    If current authority differs from what those bytes record, that is ordinary Context /
    current-validity drift under F2 §16.1 — an invalidation question — and NOT permission to
    rebuild the bound Context.
```

```text
Nothing here weakens §7.9.6's statement that the Context is immutable before generation 1 accepts
the task: it is immutable in the sense that it is not edited once built, and the Review is
launched under exactly it. What it is not, before generation 1, is DURABLE.
```

---

### 5.4 Where an interruption resumes

F3 freezes the resume **point**; F4 owns what to do when the state found there does not match.

```text
before 5b                     the executor has returned; the mutation opened at step 4 is pending
                              with its markers, and no ownership or completion effect of this
                              completion is recorded yet. A retry asks the executor again or
                              reuses a saved result, exactly as today
5b, 5c or 5d refused          what is TRUE is that START has asserted no ownership and recorded
                              nothing of this completion — not that nothing exists:

                                the mutation opened at step 4 REMAINS PENDING, and its durable
                                  review markers are unchanged;
                                the executor may already have modified the working tree, and
                                  that state is LEFT UNTOUCHED for human reconciliation;
                                NO _OWN_CONTENT note for the refused declaration;
                                NO completion effect, NO Candidate, NO Review record, and NO
                                  Git stage caused by this completion.

                              A retry re-runs the same checks and reaches the same answer while
                              the declaration is the same; a person reconciles
                              (reconcile_required). There is no automatic legacy downgrade.
before 9a                     nothing of the completion is committed; the flow continues
9a recorded, not applied      S-c0 replays; when the event log already matches HEAD it is a
                              no-op and the Candidate is frozen against the same base
after 9a, before 11b          nothing physical happened since; the Candidate is re-frozen or
                              reused and the Context is built
after 11b, before 13          the Context exists in memory only and NO durable carrier holds
                              it. A crash here loses it, and §5.3 says exactly what a resume
                              does: recompute the CURRENT Context, rerun the isolated
                              verification under it, and claim no prior Context survived. The
                              recomputed review_context_hash may differ, legitimately, if the
                              loader or authority files changed in between
13 recorded, before 16        generation 1 has durably bound the Context through the TaskInput
                              and the gate record. From here the Context is IMMUTABLE and is
                              never rebuilt or retargeted; the flow resumes at the earliest
                              unfinished gate generation
after 15, before 16           the pre-seal boundary: the capability of Context.resulting_tree is
                              derived again, from committed objects, and decides whether the
                              seal proceeds. A previous pass does not carry, and a previous
                              failure is not final — §7.9.5 says exactly which retries can
                              change it
after 16, before 18           nothing physical happened since the seal; the flow continues from
                              the sealed Review as it stands
18 recorded, 19 not applied   S-c1 is classified first, then §7.1.2 runs. EVERY interruption
                              inside it — before O-6a, between O-6a and O-7, between O-7 and
                              O-7a, at a CAS refusal, and after C-1 — is decided by §7.1.3's
                              matrix rows A ... G, from this operation's own durable
                              prepared_commit_id and never from the branch tip. The isolated
                              index of O-1 is discarded and rebuilt on a retry, so a partially
                              built index is never reused.
                              NOTE what is NOT here. The earlier draft carried a row "19 applied,
                              ref not advanced" saying the retry "rebuilds from the same parent
                              and either produces the identical commit — same tree, same parent,
                              same message, same identity — or refuses". Both halves are
                              withdrawn: the state it described is now §7.1.3 row B, where the
                              prepared id is durable and the answer is to RE-VERIFY AND RETRY THE
                              CAS OF THAT EXACT OBJECT (M-42), never to rebuild; and
                              reconstruction-produces-the-same-id was an unstated assumption that
                              every identity input — including the author and committer
                              timestamps — is durably frozen, which this contract does not claim.
                              Under the prepared-commit model reconstruction is not needed at all.
19 applied, 20 not reached    C-2(K1) runs against the O-7a-owned commit; it is a re-execution,
                              so a retry repeats it in full
C-1 done, index not refreshed §7.1.4's refresh is non-authoritative (row G): C-1 stands, the
                              operation continues, and the outcome is recorded rather than
                              retried into a failure
21 noted, 23 not recorded     the barrier and S-p1 are attempted again
23 recorded, 24 not applied   C-2(K1) is re-evaluated before apply; a stale proof refuses
24 applied                    the exact-commit push classification decides (registry.md)
26 recorded, 27 not applied   the stage replays in recorded order, nothing is re-decided
29 recorded, 30 not applied   as 18/19 for K2, by the same §7.1.3 matrix: the prepared id
                              decides, a moved branch refuses at the CAS, and an unreachable
                              object this operation never durably prepared is never adopted
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
an all-inert Candidate cannot have a K1, because a commit over an empty delta is the synthetic empty
commit those rules prohibit — and, since §7.1.2's primitive would not mechanically refuse one, because
§7.1.2 forbids O-5/O-6 from running on an empty delta at all.

### 6.2 The frozen sequence

For the **no declared path** case, identical to §5.1 with steps 6, 8, 9, 18-24 **absent**, and nothing
substituted for them:

```text
 1 ...  5   as §5.1; the executor returns Completed with an empty owned set
 5b-5d     canonical spelling, the reserved-ownership classification and the containment walk
            with its bound witness are all VACUOUS for the no-declared-path case: there is no
            declared path to inspect. For the ALL-INERT case ALL THREE still run in full, before
            step 6, because declared paths exist. An
            all-inert declaration holds NO deletion path: a deletion has old_kind present and
            new_kind absent, so it is necessarily CHANGING (F2 §6.3)           §5.1, §7.8.4
 6          no declare_own_content: there is no owned path         (start.py:880, unchanged)
 7          completion_precheck passes
 8, 9       not applicable: there is no owned path to separate or to preflight
 9a         S-c0 exactly as in §5.1: the entry events are committed before the Candidate
10          the empty-artifact Candidate is frozen                  F2 §7.2
11          the material envelope is built: payloads = [] for the no-declared-path case
            (F2 §7.2), and one payload per inert file / symlink entry for the all-inert
            case under F2 §9.4's uniform coverage rule (§6.7, amendment A-3)
11a ... 16  the resulting tree identity, the immutable Context v2, isolated verification,
            accept, launch, settle, the 15a checkout-capability decision and the seal —
            all exactly as §5.1, including that an unsafe or unknown capability at 15a stops
            the operation before any generation-3 effect and before any K2
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

and S-c2 is base-exact BY CONSTRUCTION: §7.1.2 O-2 seeds from the exact parent(K2) object id, O-6
records it as the parent, and O-7 advances the branch only under compare-and-swap against it, so a
branch that moved refuses at the ref update rather than being committed onto (M-38).
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
the frozen primitive of §7.1.2 forbids O-5/O-6 on an empty delta — the rule that replaced
  `git commit --only`'s mechanical refusal — as an internal assertion, not a new reason;
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
git_persistence identity = "review-v1-work-local-v2"
```

**A NEW VALUE, because the semantics are new — forward amendment A-7.** An earlier draft kept F2's
string `review-v1-work-local-v1` and changed only what it denoted, reasoning that renaming it would
supersede a landed statement for no reason. That was backwards and is withdrawn: F2 §10.3 says the
identity denotes the CONTAINED COMMIT PRIMITIVE, and §7.1.2 replaces that primitive, so keeping the
string is what would have made a landed sentence false — and would have left every reader comparing
recorded modes against semantics that no longer exist. The FIELD is untouched: same record, same key,
same position, same meaning, so A-4's "nine fields unchanged in name, order and meaning" still holds.
Only the VALUE moves to `review-v1-work-local-v2`. The planning identity
`review-v1-planning-local-v1` is not redefined and no planning Run changes (C3-1, §7.1.7).

#### 7.1.0 Why the contained primitive could not be retained

The earlier draft froze the contained commit primitive — `git add -- <paths>` then
`git commit --only --no-verify --no-gpg-sign -m <message> -- <paths>` — identical in mechanism to the
live planning primitive (M-6). Both of those calls take ORDINARY ROOT-RELATIVE WORKING-TREE PATHNAMES
and resolve them, component by component, AT THE MOMENT THEY RUN. The identity proof runs earlier. So:

```text
THE RACE, stated exactly

    t0   the artifact's identity is proven: witness captured, Candidate frozen, Review sealed,
         pre-stage containment re-proven, currentness confirmed
    t1   an ancestor directory component of a declared path is replaced by an indirection to
         somewhere else
    t2   `git add -- <path>` resolves <path> AGAIN, through the replaced component, and stages
         WHATEVER IS THERE NOW

MEASURED, M-34: on this Windows volume Git does NOT refuse t2. `git add` through a junction staged
the redirected blob. On POSIX Git refuses it, so the safety was platform-dependent — which is to say
it was not a property of the contract at all.
```

The earlier draft answered this with "C-2(K1) catches it after the commit". That answer is **rejected
and withdrawn**. C-2(K1) proves that nothing wrong is ever *published*; it does not preserve the
invariant this contract freezes, which is

```text
    WITNESS == CANDIDATE == PRE-STAGE == STAGED == K1
```

If the wrong object can reach the committed tree at all, that chain is broken at its fourth link, and a
downstream refusal does not repair it — it reports it. The primitive is therefore replaced with one
under which the race **cannot change the committed tree**, rather than one under which it is detected
afterwards.

#### 7.1.1 The COMMIT TREE PLAN — what every commit class commits, and where its bytes come from

The primitive below is generic. It commits a **plan**, never a reread of the working tree, and every
commit this operation makes has one:

```text
CommitTreePlan
    parent            the EXACT full commit id this commit is built on
    ref               the EXACT full branch ref this commit advances (§7.1.5)
    message           the EXACT message bytes
    contract          the persistence contract identity
    entries[]         one per path this commit changes, and no other path:
                        path          canonical, from §7.8.4
                        old_mode      \ as the PARENT TREE holds them, so the plan is
                        old_oid       / self-checking against the parent it names
                        new_mode      "100644" | "100755" | "120000" | "160000" | absent
                        new_oid       the exact object id the entry will carry
                        material      the exact bytes, for a file or a symlink ONLY
                        deleted       true when the path is removed, and then no new_* at all
```

An earlier draft wrote O-3 as "hash the witnessed bytes and require the id to equal
`Candidate.new_oid`". That is **K1-specific and is withdrawn**: S-c0, the Review generation
commits, the Work cycle's own pre-completion commit stages and S-c2 all lack a Candidate and an
artifact witness, so the primitive as written described ONE of the five commit classes it claimed
to govern. The plan is what generalizes it, and `Candidate.new_oid` is now named only in the one
class that has a Candidate.

**THE ONE GENERIC RULE, and then the classes it produces.** There is exactly one way a plan entry's
material is computed, and it is total over every commit this operation makes:

```text
MATERIAL(path) for a commit whose parent is P and whose stage recorded effects E1 ... En:

    start from the PARENT OBJECT: the blob P's tree holds at `path`, verbatim, or b"" when P's
      tree has no such path;
    apply, IN RECORDED ORDER, every recorded effect of THIS STAGE that writes `path`, by that
      effect kind's own rendering rule (below);
    the result is the material.

    THEN REQUIRE, and this is what makes the working tree not the authority:
        _text_digest(material) == the digest the mutation DURABLY RECORDED for the last effect
        writing that path, before it wrote it
    A disagreement STOPS. It means the bytes this operation recorded putting there and the bytes
    the plan computes are not the same, which is a defect or interference, and either way not
    something to commit.

PER EFFECT KIND, exactly, and every one of these is a function of (parent object, recorded
payload) alone:

    write_file / create_file   the payload's `content`, replacing whatever the accumulator held
    add_relation               parse the ACCUMULATOR as a relation ledger, append the payload's
                               relation record, re-render the whole ledger by the canonical
                               renderer
    remove_relation            parse the ACCUMULATOR, drop the relation whose id matches the
                               payload's, re-render the whole ledger
    append_event               the ACCUMULATOR, given a trailing LF if it lacks one, then the
                               canonical serialization of the payload's event record and one LF.
                               BL-039's line-separator escaping applies and the log stays LF-only.
    git_commit / git_push      write no file and contribute no material
```

```text
WHY "THE ACCUMULATOR" AND NOT THE FILE, stated because the live helper does the opposite.
`mutation.planned_write` (mutation.py:1740) is the writer's own rendering and F3 reuses its RULES,
but not its SOURCE: for `add_relation` / `remove_relation` it re-renders from
`store.read_relation_file(...)` and for `append_event` it appends to `store.events_text()` — the
WORKING-TREE copies (M-56). Re-evaluating it at plan time would both trust that copy and, for an
append, apply an event that has already been written, producing a double entry.

Sourcing from the parent object and chaining in recorded order is deterministic, reproducible from
committed state plus the durable record, and free of both faults. The recorded digest then pins the
result to what the mutation actually wrote, so the two independent derivations must agree.

An implementation therefore needs a parent-object-sourced variant of that rendering (IP-22); the
rules it applies are the live ones, unchanged.
```

**The classes this produces. Every commit this operation makes is one of them, and the list is total:**

```text
S-c0                SOURCE: the parent tree's event-log blob + this mutation's recorded
                    append_event effects for the entry stage.
                    entries = exactly one, `.workline/events/events.jsonl` — which is why A-6
                    reserves it. Because the rule is append-only, the plan also REQUIRES
                    material.startswith(parent_blob); an append that is not an append is a defect.

PRE-COMPLETION      the Work cycle's own commit-only stages, which F3 §7.3, §7.6 and §11.3 already
WORK STAGES         put under this primitive and which an earlier draft left with NO plan source
                    at all: derived registration, move, human-NG move, and every other currently
                    supported pre-completion Work Git stage.
                    SOURCE: the generic rule above, over exactly that stage's recorded effects.
                    entries = every path those effects write — a registration or relation ledger
                    via add_relation / remove_relation, an entity or registration file via
                    write_file, the event log via append_event — each computed from the parent
                    object and the recorded payloads, none reread from the working tree.
                    These stages are ordinary commits of this operation and get no exception.

REVIEW GENERATION   SOURCE: the `create_file` effects the generation mutation already recorded, so
COMMITS             the material is THE EXACT BYTES THAT EFFECT CARRIES — the same bytes P1's
(gen 1 / 2 / 3)     serializer produced — never a reread of the file the effect wrote. Live
                    `_finish_generation` already builds its expectation this way
                    (`expected = {path: content.encode("utf-8")}`, roadmap_review.py:1450).
                    entries = exactly this generation's Review record paths.
                    WHICH IDENTITY these commits carry is §7.1.7 (C3-1): the Work identity for a
                    Work Review Run, the planning identity for every planning Run.

S-c1 / K1           SOURCE: the bound artifact witness (§7.8.4) and the frozen Candidate.
                    entries = the Candidate's CHANGING entries EXACTLY, which already includes
                    every deletion — a deletion has old_* present and new_kind absent, so it is
                    necessarily changing (F2 §6.3). An earlier draft wrote "changing entries plus
                    its deletions", which would have named a deletion twice; a plan never holds
                    two entries for one path.
                    material = the witnessed bytes; new_oid = Candidate.new_oid; new_mode =
                    Candidate.new_mode. The invariant is unchanged and one link longer:

                        WITNESS == CANDIDATE == PLAN == STAGED == K1

S-c2 / K2           SOURCE: the parent tree, plus this mutation's recorded terminal append_event
                    effects and its recorded Consumption record effect — the event entry as S-c0
                    computes it, the Consumption entry as a generation commit computes it.
                    §16's exact two-entry delta is therefore a property of the PLAN, checkable
                    BEFORE the commit rather than only after it.
```

```text
"EVERY COMMIT THIS OPERATION MAKES" IS NOW TOTAL. The five classes above are exhaustive over the
Git stages §11.3 puts under this primitive, and each has a named source that is a function of the
parent object and durably recorded effects. No class reads the working-tree copy of a path its
plan describes as the authority for what to commit.
```

#### 7.1.2 The frozen object-driven sequence

```text
FROZEN. Every commit this operation makes — S-c0, each Review generation commit, S-c1/K1 and
S-c2/K2 — is built by the following sequence and by no other. MEASURED end to end,
M-36..M-38, M-40, M-42..M-45.

O-1  ISOLATED INDEX
       GIT_INDEX_FILE = a Workline-owned path under .workline/runtime/**, created fresh for this
       commit and removed afterwards. The repository's real index is NOT read and NOT written by
       O-1..O-8.

O-2  SEED FROM THE EXACT PARENT
       git read-tree <plan.parent>
       never `HEAD`, never a branch name, never a re-read tip. Every path the parent holds is
       carried forward unchanged, so the committed delta is COMPUTED, not filtered: paths the plan
       does not name cannot enter the commit, and the executor's unrelated working-tree
       modifications are structurally absent rather than excluded by a `--only` pathspec.

O-2a PARENT AGREEMENT
       for every plan entry, the parent tree's entry at that path EQUALS the plan's old_mode /
       old_oid (absent where the plan says absent). A disagreement STOPS: the plan was computed
       against a different parent than the one being committed on.

O-3  MATERIALIZE EACH ENTRY FROM THE PLAN, NEVER FROM THE WORKING TREE
       file / executable file / symlink:
           git hash-object -w --stdin      <- fed plan.entry.material
       and the returned id is REQUIRED to equal plan.entry.new_oid, or STOP. No `--path` is
       passed, so no attribute or filter machinery is consulted and the id is the raw-bytes id
       (M-40) — which for K1 is exactly F2 §6.3's `new_oid`.
       gitlink: nothing is written; its identity is already a commit id (§7.8.4, M-46).
       deletion: nothing is written.

O-4  PLACE EACH ENTRY BY IDENTITY, NOT BY PATH RESOLUTION
       present:   git update-index --add --cacheinfo <new_mode>,<new_oid>,<path>
       deleted:   git update-index --force-remove <path>
       `--cacheinfo` and `--force-remove` write an INDEX ENTRY whose key is the path STRING. They
       do not open, stat, traverse or resolve anything on the filesystem. This is the step that
       closes the staging race, measured rather than reasoned: with an ancestor junction ACTIVE
       and redirecting throughout, the committed entry was the witnessed blob `924c75cd` and the
       redirected blob `b2f3ae2a` appeared nowhere in the commit (M-36).

O-5  WRITE THE TREE
       git write-tree
       The result is REQUIRED to equal the tree the plan determines. Nothing later recomputes it.

O-6  WRITE THE COMMIT OBJECT
       git commit-tree <tree> -p <plan.parent> --no-gpg-sign -m <plan.message>
       Hooks do not run and no signature is applied — MEASURED, M-37. Because `commit-msg` cannot
       run, the committed message is exactly `plan.message`, which is what §13 and the
       same-message identity rules downstream depend on.
       NO REF HAS MOVED YET. The commit object exists and is unreachable.

O-6a PREPARED-COMMIT OWNERSHIP CHECKPOINT — DURABLE, AND BEFORE ANY REF MUTATION
       PREPARED_COMMIT_ID = the exact full object id O-6 returned.

       Durably record, on this mutation's git_commit effect, in ONE save that completes before
       O-7 begins:

           prepared_commit_id   PREPARED_COMMIT_ID
           prepared_parent      plan.parent
           prepared_tree        the tree O-5 wrote
           prepared_ref         plan.ref, by full ref name
           prepared_contract    the persistence contract identity

       THIS IS NOT C-1 AND IS NOT K. It proves exactly one thing: THIS OPERATION CREATED THIS
       EXACT COMMIT OBJECT. It confers no reachability, authorizes no push, and satisfies no
       proof item.

       Why it must exist: without it there is a window in which the ref has advanced and no
       durable record says this operation made the commit, and live `_classify_commit` resolves
       that window by observing that the paths no longer differ from HEAD and returning MATCHING
       with no owned id (M-41) — which P1 R5 §3.1 / §3.5 forbid. The precedent is live: the write
       path already records the bytes it is about to write BEFORE writing them
       (`record[_WROTE] = wrote; self._save()`, mutation.py:501), "so that what it wrote is known
       however the write ends". O-6a is that same discipline for a commit.

O-7  ADVANCE THE BRANCH BY COMPARE-AND-SWAP
       git update-ref <plan.ref> <PREPARED_COMMIT_ID> <plan.parent>
       MEASURED, M-38: a wrong expected-old is refused ("is at <actual> but expected <given>") and
       the ref is left untouched, so a concurrent advance can neither be overwritten nor silently
       accepted. A refusal STOPS with the EXISTING reason `review_registration_base_moved` (M-7),
       never a retry against the new tip.

O-7a C-1: DURABLE PROMOTION, ONCE REACHABILITY IS PROVEN
       `plan.ref` is read back and shown to be PREPARED_COMMIT_ID. Then, durably:

           commit_id = PREPARED_COMMIT_ID
           applied   = true

       THIS is C-1. Every downstream item — W1, the proof notes, the publication barrier, every
       push — reads this, never the prepared checkpoint and never the branch tip.

O-8  DISCARD THE ISOLATED INDEX
       the O-1 index file is removed. It is never reused across commits or across resumes: a
       partially built index has no standing, and rebuilding it from `plan.parent` is free.
```

```text
NOT PART OF THE PRIMITIVE, and forbidden inside it:

    git add                     resolves working-tree pathnames        (the race, M-34)
    git commit                  resolves working-tree pathnames, runs hooks, honours commit.gpgsign
    git commit --only -- <p>    both of the above
    git stash / reset / checkout / restore   touch state this operation does not own
    any `--path` on hash-object              would consult attributes
    any read of the working-tree copy of a path the plan already describes
```

#### 7.1.3 Crash recovery — the exact resume matrix

Every row is decided from the operation's OWN durable record. **The branch tip never confers
ownership**, and no row recovers ownership from the observation that the paths no longer differ
from HEAD. Measured: M-42, M-43.

```text
A. NO prepared_commit_id, ref == plan.parent
   nothing of this commit is owned. Rebuild the plan and run O-1..O-7a from the start.
   Any objects a previous attempt wrote are unreachable and unowned (§7.1.4); they are not
   searched for, not adopted, and not evidence.

B. prepared_commit_id DURABLE, ref == plan.parent
   the CAS had not landed. Re-verify THAT object exactly — it exists, it is a commit, its tree
   equals prepared_tree, its parent equals prepared_parent, its message equals plan.message —
   and retry the CAS OF THAT ID. MEASURED to succeed (M-42).
   DO NOT rebuild a new commit and DO NOT adopt any other commit.

C. prepared_commit_id DURABLE, ref == prepared_commit_id
   the CAS landed and the crash fell between O-7 and O-7a. C-1 is recovered POSITIVELY, from this
   operation's own durable prepared id compared to the ref it recorded. This is NOT branch-tip
   inference: the id was written down before the ref moved, and the ref is only being asked
   whether it holds THAT id.

D. prepared_commit_id DURABLE, ref moved ELSEWHERE (not the prepared id, not an ancestor case)
   reconcile / fail closed. The prepared commit is NEVER retargeted onto the new tip, never
   rebuilt against it, and never published. ReconcileRequired, reason
   review_registration_base_moved.

E. prepared_commit_id DURABLE, the object is MISSING, corrupt or unanswerable
   fail closed. `git cat-file -e` answering negatively is not permission to rebuild: this
   operation recorded that it made a specific object, and a repository that no longer has it is a
   state a person reconciles.

F. prepared_commit_id DURABLE, ref is a DESCENDANT of the prepared id
   `raw_descends_from(<ref>, <prepared>)` answers YES — the §7.1.8 RAW walk, never
   `merge-base --is-ancestor`, which a graft or a shallow boundary would answer differently
   (M-57, M-59). Ownership of the prepared
   OBJECT is still known — this operation made it — but the stage's own conditions do not hold:
   the branch is no longer at the commit this stage produced, so base-exactness, L-3 and W3 fail.
   Reconcile. The later branch state is NEVER silently treated as this stage's result.

G. prepared_commit_id DURABLE and PROMOTED (C-1 complete), real-index refresh not done or failed
   C-1 STANDS. §7.1.4's refresh is non-authoritative and its outcome never un-owns K.
```

#### 7.1.4 The real index — after C-1, conditional, verified, and never authoritative

An earlier draft reconciled the real index as O-8, INSIDE the commit step and BEFORE the effect was
durably owned. That is withdrawn for two measured reasons.

```text
1. IT REPRODUCED THE C-1 GAP. O-7 succeeds, the index step fails or crashes, apply_effect never
   returns, and commit_id/applied are never saved (M-41). A cosmetic step must not be able to
   cost the operation its ownership of a commit that is already on the branch.

2. IT COULD OVERWRITE A PERSON'S STAGING INTENT. A person may change the real index during the
   Review wait without touching the working tree. The working tree still holds the witnessed
   bytes, so full-witness currentness — an ARTIFACT witness — still passes; K1 correctly commits
   the witnessed bytes; and a blind `update-index` would then replace the person's staged entry.
   Owning a PATH is not owning a person's later staging intent, and F3 does not confuse them.
```

Leaving the index alone is not neutral either, and that is measured rather than assumed:

```text
M-44: after commit-tree + update-ref with no index write, `git status --short` shows `MM` on the
path and `git diff --cached` shows it staged-modified — so the person's next ordinary
`git commit` would record the OLD bytes back over the result just committed. The live `git add`
primitive updated the real index as a side effect; the object-driven one does not, and that
difference has to be handled rather than inherited silently.
```

**FROZEN — the ATOMIC conditional index transaction.** An earlier draft accepted a compare/write gap,
reasoning that the index is "local and ephemeral". **That is withdrawn.** A person's staged entry is
unsaved Git state, and canonical `registry.md` requires that existing unsaved work, uncommitted changes,
untracked files and other people's or other AIs' changes are not lost for Workline's convenience. "The
race is narrow" is not an exemption. Git's own index transaction is an `O_CREAT|O_EXCL` lockfile, and
holding it closes the gap entirely (M-52, M-53).

```text
R-IDX-1  IT RUNS ONLY AFTER O-7a. C-1 is durable before any index work begins.

R-IDX-2  IT IS NON-AUTHORITATIVE FOR OWNERSHIP. Its outcome never un-owns K, never invalidates
         C-1, C-2 or the proof note. (What it does gate is completion: see R-IDX-8.)

R-IDX-3  EXCLUSIVE OWNERSHIP OF THE TRANSACTION, BY GIT'S OWN PROTOCOL.
             create `<git-dir>/index.lock` with O_CREAT|O_EXCL
         MEASURED (M-52): while it is held, `git add` and `git update-index` both fail with
         "Unable to create ... index.lock: File exists".

         IF THE CREATE FAILS, OWNERSHIP OF THAT LOCK IS **UNKNOWN**, and it is never guessed.
         MEASURED (M-62): a lockfile is ZERO BYTES — no pid, no host, no identity of any kind —
         and Git's own protocol writes the new index into it and renames, so a held lock is
         indistinguishable from any other. The lock may belong to a live Git process, to a
         crashed one, or to an earlier crashed attempt of THIS operation, and nothing available
         distinguishes them.

         THEREFORE, and this is exhaustive:
             the lock is NEVER deleted automatically, and never "stolen";
             ownership is NEVER inferred from the filename, the file's age, the absence of a
               process, the current index contents, or the existence of a pending mutation —
               none of those is a proof, and an earlier draft's "another Git process owns the
               index right now" asserted one of them without evidence;
             a bounded number of retries is attempted, because ordinary contention is common and
               brief;
             if it still exists, the operation STOPS at INDEX LOCK RECONCILIATION (R-IDX-8).

R-IDX-4  UNDER THAT SAME LOCK, AND WITH NO GAP ANYWHERE INSIDE IT:
             a  snapshot the exact current index to a Workline-owned temporary file inside the
                Git directory, so the publish in R-IDX-6 is a same-directory rename
             b  read the exact entries from the SNAPSHOT (GIT_INDEX_FILE=<snapshot>
                `ls-files --stage`), under the hermetic environment of §7.1.9
             c  for each of THIS COMMIT'S OWN plan paths, compare the snapshot entry against the
                entry the plan expected to find there — plan.old_mode / plan.old_oid
             d  write, into the SNAPSHOT only, the new entry for a path whose current entry still
                equals that expected one
         Every unrelated entry is carried through untouched, because the snapshot IS the real
         index and nothing but (d) modifies it.

R-IDX-5  A FOREIGN ENTRY IS NEVER OVERWRITTEN — on an unrelated path or on an OWN path. If an own
         path's current entry is anything other than the expected old one, a person staged
         something there: PRESERVE it and continue. Path ownership is not ownership of a person's
         later staging intent. MEASURED (M-53): with the person's `c/h.txt` staged on an own plan
         path and `b/g.txt` staged on an unrelated one, both survived byte-identical while
         `a/f.txt` refreshed.

R-IDX-6  PUBLISH ATOMICALLY OR NOT AT ALL. Rename the snapshot over the real index — a
         same-directory rename, which is what Git's own protocol does — then release the lock. A
         failure at any earlier point leaves `<git-dir>/index` EXACTLY as it was.

R-IDX-7  NEVER `git reset`, NEVER a whole-index `read-tree` against HEAD, NEVER a blind
         `update-index` against the LIVE index. The first two discard state this operation does
         not own; the third is the gap this rule exists to remove.

R-IDX-8  A CLEANUP FAILURE DOES NOT UN-OWN K, AND DOES NOT SILENTLY COMPLETE EITHER.
         The outcomes are exhaustive, and the first is the ordinary one:

             the own path's entry is FOREIGN
                 -> the person staged there deliberately. Nothing is owed. Record it and
                    CONTINUE; this is an ordinary, correct completion.

             the own path's entry is still the operation's expected STALE OLD entry, and the
             transaction could not complete
                 -> the measured trap is live: `git status` shows the path staged-backwards and
                    the person's next ordinary `git commit` would revert K (M-44). The operation
                    does NOT return completed as though nothing were owed. It STOPS at a LOCAL
                    CLEANUP CHECKPOINT, with C-1 and everything proven about K fully intact.

             the lock could not be acquired, or this operation crashed while holding it
                 -> INDEX LOCK RECONCILIATION, a STOP with its own exact identity. Stated
                    plainly, because an earlier draft said a resume simply "retries" and that is
                    NOT TRUE of this case: a resume re-attempting O_EXCL finds the file and gets
                    UNKNOWN again (M-62), so retrying alone can never clear a lock this
                    operation itself left behind. The loop only ends when a person or F4 removes
                    or reconciles the stale Git lock — which is an ordinary Git housekeeping act,
                    the same one anyone performs after any Git process dies mid-write.

         WHAT IS TRUE WHILE IT IS STOPPED, and it is the whole point of the ordering:

             C-1 REMAINS VALID. K is owned, on the branch, and provable.
             NO proof and NO publication ownership is lost. W1, the proof note, the barrier and
               every push right stand exactly where they stood.
             the mutation remains pending, so nothing is abandoned and nothing is re-decided.
             after reconciliation, the SAME pending operation resumes at the SAME cleanup
               checkpoint and finishes the transaction.

         So "non-authoritative" means it cannot un-own K — not that its failure is invisible, and
         not that every failure resolves itself.

R-IDX-9  NO CRASH-RESUMABLE LOCK-OWNERSHIP PROTOCOL IS INVENTED. One could be built — write an
         owner record durably before creating the lock — but it would have its own gap between
         that write and the O_EXCL create, and a gap is exactly what this section exists to
         remove. Since R-IDX-8's stop is safe, bounded and leaves nothing lost, the simpler
         honest answer is taken instead. If a future version wants automatic recovery, it must
         MEASURE that no acquisition-to-ownership-record gap exists, not assume it.

R-IDX-10 NO NEW DURABLE CARRIER, AND NO LATER-OPERATION DEPENDENCE ON THE MUTATION RECORD. An
         earlier draft said "a later Workline operation reads that record rather than inferring
         from the index". That is withdrawn: `Mutation.complete()` calls `_drop_own_record()`, so
         the completed runtime record is taken away and no later operation can read it. Nothing
         is needed in its place, because R-IDX-3...R-IDX-6 leave the real index in a state that
         is already correct on its own terms — own paths refreshed, foreign entries preserved —
         and R-IDX-8 refuses to complete in the one state that would have needed explaining. A
         later operation sees ordinary Git state and handles it with the ordinary dirty-state
         rules (BL-041), which is what those rules are for.
```

```text
MEASURED END TO END (M-53), in this exact order, with both kinds of foreign staged state present:

    O_EXCL .git/index.lock  ->  concurrent `git add` EXIT 128 for the whole transaction
    copy .git/index -> wl-index.tmp
    read exact entries from the snapshot
    a/f.txt  == expected old  -> refreshed to f49b8164
    c/h.txt  FOREIGN          -> preserved (43751a14, the person's bytes)
    b/g.txt  unrelated        -> preserved (17b11086, byte-identical)
    os.replace(wl-index.tmp, .git/index)   ->  atomic publish
    release the lock

and NO hook fired, the empty `core.hooksPath` holding for `post-index-change` as well (M-48).
```

#### 7.1.5 The ref O-7 advances, and detached HEAD

```text
O-7 advances the EXACT FULL BRANCH REF the operation recorded — `plan.ref`, which is
declared_base.branch bound before the Git stage (BL-036) and re-checked by BL-038's
`_require_finalized_branch`.

DETACHED HEAD NEVER REACHES REVIEW-V1 WORK PERSISTENCE. Live START already calls
`gitops.ensure_git_ready` (gitops.py:151), which returns the current branch and raises
StopError(code="detached_head") when there is none. F3 introduces NO detached-head semantics.

An earlier draft wrote "the branch bound by BL-036 when on a branch, HEAD itself when detached".
That second branch is withdrawn: it invented a case the operation cannot be in, and a
compare-and-swap on a detached HEAD would have been a new and unreviewed behaviour.
```

#### 7.1.6 Unreachable object residue

```text
STATED PLAINLY, because "nothing was written" would be FALSE after O-3, O-5 or O-6.

A crash, a STOP at O-2a / O-3 / O-5, or a CAS refusal at O-7 can leave behind:

    blobs    written by `hash-object -w`
    trees    written by `write-tree`
    commits  written by `commit-tree`

About them, all of the following hold and none is softened:

    they are CONTROLLED local Git object-database side effects, inside the Project's own .git;
    they MOVE NO REF and change no branch, no tag and no note;
    they are NEVER C-1, C-2 or checkpoint evidence;
    they are NEVER adopted — no step searches the object database for a commit that looks right,
      and only a DURABLE prepared_commit_id makes an object this operation's own (§7.1.3);
    ordinary `git gc` may remove them whenever it likes, and nothing depends on their surviving;
    their existence NEVER authorizes a retry, a push, or any inference about what happened.

Measured support: `hash-object -w --stdin` left HEAD unchanged and `git status` empty (M-40), and
O-6 moves no ref by construction — the ref moves only at O-7.
```

#### 7.1.7 Which persistence identity a generation commit carries (C3-1)

```text
MEASURED IN LIVE CODE, not assumed. `_finish_generation` (roadmap_review.py:1447) records its
generation commit through `gitops.review_commit_effect` (gitops.py:201), which does

    effect.payload["mode"] = PLANNING_COMMIT_MODE          # "review-v1-planning-local-v1"

UNCONDITIONALLY, for every Review kind. F3 §7.6 puts the Review's own generation commits under the
Work persistence primitive. Both cannot hold for a Work Review Run, and the earlier draft simply
did not notice the conflict.
```

**FROZEN — F3-only correction C3-1:**

```text
THE DISCRIMINATOR IS DURABLE INVOCATION DATA, never a guess and never the calling code path.
`_generation_invocation` (roadmap_review.py:1422) already writes `review_kind` into the generation
mutation's own durable invocation record. So:

    generation mutation invocation review_kind == "work-result-v1"
        -> git_commit mode "review-v1-work-local-v2"
        -> CommitTreePlan (§7.1.1, the REVIEW GENERATION class) and O-1 ... O-8

    every other review_kind — roadmap, phase, and every other planning kind
        -> git_commit mode "review-v1-planning-local-v1"
        -> behaviour EXACTLY as today, unchanged in every respect

THE PLANNING IDENTITY IS NOT REDEFINED. No planning Run changes behaviour, no planning Run's
recorded mode changes, and nothing about P2 is touched. What changes is only which of the two
identities a WORK Review Run's generation commit names.
```

```text
WHY IT MUST BE THE WORK IDENTITY FOR A WORK RUN. A Work Review Run's generation commits are commits
this operation makes, on the same branch, between declared_base.base_commit and K1, and §8.2's
lineage rule counts them as own-Review commits. If they were made by the contained primitive while
K1 was made by the object-driven one, the operation would be making commits under two different
persistence semantics within one proven range, and §7.3's per-commit preflight — which is stated
over "every commit this operation makes" — would be describing a primitive that half of them do
not use.
```

```text
WHAT THIS DOES NOT CHANGE: the Review record BYTES are the same either way — the recorded
`create_file` content (§7.1.1) — so no canonical Review record, no Candidate, and no Context field
changes. This is a change of persistence mechanism and recorded mode, nothing else.
```

#### 7.1.8 RAW ANCESTRY — the only authority for parentage, range and descent

```text
MEASURED, not argued. Git has TWO different answers to "what are this commit's parents":

    THE REVISION VIEW      what `rev-list`, `log`, `merge-base` and every revision walker say,
                           after applying refs/replace, `.git/info/grafts` and `.git/shallow`
    THE COMMIT OBJECT      the literal `parent <oid>` headers stored in the object itself

They differ, and the difference is attacker-controllable. M-57: with `.git/info/grafts` holding
"C4 C1", `rev-list --parents -n 1 C4` returned C1 and `merge-base --is-ancestor C2 C4` returned
FALSE for a commit that genuinely IS an ancestor, while `cat-file commit C4` still named C3.
M-59: in a shallow clone the walker reported HEAD as a ROOT with no parents, while the object
held two `parent` headers.

The live helpers are on the wrong side of that line: `gitcmd.commit_parents` runs
`rev-list --parents` (gitcmd.py:399) and `gitcmd.descends_from` runs `merge-base --is-ancestor`
(gitcmd.py:412).
```

**FROZEN — every security-critical ancestry answer in this contract is a RAW-OBJECT answer:**

```text
RAW_PARENTS(commit_oid)

    read THE ACTUAL COMMIT OBJECT named by commit_oid:

        GIT_NO_REPLACE_OBJECTS=1
        GIT_NO_LAZY_FETCH=1
        git cat-file commit <commit_oid>

    parse its literal `parent <oid>` headers, in order, from the header block that ends at the
    first empty line. Those headers, and ONLY those headers, are the commit's parents for every
    P3 proof.

    the object is not present, is not a commit, or cannot be parsed -> UNKNOWN, FAIL CLOSED

    GIT_NO_REPLACE_OBJECTS IS REQUIRED HERE, not inherited from the general environment by
    assumption: MEASURED (M-58), with a replacement active, plain `cat-file commit C4` showed NO
    parent because it read the replacement, and only the setting restored the true C3.
```

```text
Every ancestry predicate this contract relies on is built from RAW_PARENTS and nothing else:

    raw_parent(commit)                  RAW_PARENTS(commit), exactly
    raw_descends_from(commit, ancestor) commit == ancestor, or a walk of RAW_PARENTS from commit
                                        reaches ancestor
    raw_range(base, head)               the commits on the RAW_PARENTS walk from head down to,
                                        and excluding, base

    ANY unreachable step — a named parent whose object is locally unavailable — makes the whole
    answer UNKNOWN and FAILS CLOSED. It is NEVER read as "the walk ended, so this is a root".
    M-59 is exactly that case: the shallow boundary's commit names two parents that are not here.

    A walk is bounded: it stops at `base`, at a genuine root (a commit with NO parent header at
    all), or at UNKNOWN. A cycle is impossible in a content-addressed store, and a walk that
    exceeds a frozen step budget is UNKNOWN rather than an infinite loop.
```

```text
FORBIDDEN as an authority, in §8.2's lineage rule, in C-2's items, in §7.1.3's resume matrix and
anywhere else a proof depends on the answer:

    git rev-list --parents          the graft/shallow view (M-57, M-59)
    git merge-base --is-ancestor    the same view (M-57 returned FALSE for a real ancestor)
    gitcmd.commit_parents           built on the first
    gitcmd.descends_from            built on the second
    any other revision walker, unless it is MECHANICALLY PROVEN for that exact invocation to
      ignore replace, grafts and shallow — and this contract proves that for none of them

They may still be used for non-proof convenience, such as a hint in a message, provided nothing
a proof reads is derived from them.
```

```text
WHY THE ENTRY CHECK IS NOT ENOUGH, and why §7.1.9's grafts refusal is now DEFENCE IN DEPTH rather
than the mechanism. An earlier draft refused a non-empty `.git/info/grafts` at entry and said
nothing about shallow at all. Both gaps are real:

    the graft file can be created or changed at ANY moment during the Run, by anyone with write
      access to the Git directory, and nothing re-reads it;
    a shallow repository was never considered, and its boundary makes the walker report a root.

Under RAW_PARENTS neither matters to correctness: the stored headers do not change when a graft
file appears, and a shallow boundary becomes a locally-unavailable parent, which is UNKNOWN. The
entry refusal for a non-empty grafts file is RETAINED anyway — it is cheap, and a Project using
grafts is one a person should know about — and an entry check for
`rev-parse --is-shallow-repository` is added on the same footing. Neither is load-bearing.
```

#### 7.1.9 The environment the sequence runs in

```text
environment TWO RULES, NOT ONE, AND THE DIFFERENCE IS EXACT. An earlier draft stated a single
            mechanical rule — strip, then inject the allowlist — "for EVERY Git invocation of
            this operation", with `GIT_CONFIG_NOSYSTEM=1` and `GIT_CONFIG_GLOBAL=<empty file>`
            marked "always". That made the identity capture of §7.1.9 phase A IMPOSSIBLE, because
            phase A exists precisely to read the configuration those two variables hide.

            MEASURED (M-64), in a Project whose identity lives ONLY in global config:
                strip inherited GIT_* only
                    config --get user.name  -> EXIT 0, "Global Person"
                    config --get user.email -> EXIT 0, "global@example.com"
                strip PLUS GIT_CONFIG_NOSYSTEM=1 and GIT_CONFIG_GLOBAL=<empty file>
                    config --get user.name  -> EXIT 1, empty
                    config --get user.email -> EXIT 1, empty

            So the two halves of the old "one rule" are separated. THE STRIP IS UNIVERSAL; THE
            CONFIG-NEUTRALIZATION ALLOWLIST IS NOT. There are exactly TWO classes and no others:

            CLASS A — THE IDENTITY CAPTURE INVOCATION (§7.1.9 phase A). Exactly the two
                      `config --get` commands, and nothing else, ever.
                        1. start from the parent process environment;
                        2. REMOVE EVERY INHERITED `GIT_*` VARIABLE — the same strip as class B,
                           with no exception;
                        3. DO NOT inject the configuration-neutralization variables yet;
                        4. ordinary Git configuration resolution stays intact, with its ordinary
                           precedence: system -> global -> repository-local;
                        5. the Project root is given as a COMMAND ARGUMENT (`git -C <root>`),
                           never through an ambient Git environment variable.

            CLASS B — EVERY OTHER GIT INVOCATION OF THIS OPERATION: plan construction, O-1...O-8,
                      prepared-commit verification, RAW_PARENTS (§7.1.8), C-2, lineage and delta
                      proof, the Git persistence preflight, and the §7.1.4 index transaction.
                        1. REMOVE EVERY INHERITED `GIT_*` VARIABLE;
                        2. INJECT EXACTLY the class B allowlist below, and nothing else.

            BOTH CLASSES STRIP EVERYTHING INHERITED. The strip is what protects against a hostile
            environment, and no invocation of this operation is exempt from it. What class A
            omits is only the configuration NEUTRALIZATION — and it omits it for the one purpose
            that requires the configuration to be readable.

            MEASURED (M-61) that the strip is load-bearing: an inherited GIT_AUTHOR_NAME /
            GIT_AUTHOR_EMAIL put `author Attacker <evil@x>` on a commit in a Project configured
            to "Real Person"; an inherited GIT_INDEX_FILE silently redirects every index command;
            and an inherited GIT_OBJECT_DIRECTORY made `cat-file -e HEAD` EXIT 1 — the
            repository's own commit invisible. MEASURED (M-64) that the strip alone already
            protects class A: with hostile GIT_AUTHOR_*, GIT_COMMITTER_*, GIT_INDEX_FILE,
            GIT_OBJECT_DIRECTORY, GIT_ALTERNATE_OBJECT_DIRECTORIES and
            GIT_CONFIG_COUNT/KEY_0/VALUE_0 all set, the stripped capture still returned the
            configured identity and none of the hostile values.

allowlist   THE CLASS B ALLOWLIST. Class A injects NONE of these; it strips and injects nothing.

            GIT_ATTR_NOSYSTEM=1              every class B invocation
            GIT_CONFIG_NOSYSTEM=1            every class B invocation — NOT class A
            GIT_CONFIG_GLOBAL=<empty file>   every class B invocation — NOT class A;
                                             a Workline-owned empty file
            GIT_NO_LAZY_FETCH=1              every class B invocation
            GIT_NO_REPLACE_OBJECTS=1         every class B invocation
            GIT_LITERAL_PATHSPECS=1          every class B invocation
            GIT_AUTHOR_NAME                  \
            GIT_AUTHOR_EMAIL                  | on commit-tree only, from the class A capture
            GIT_AUTHOR_DATE                   |
            GIT_COMMITTER_NAME                |
            GIT_COMMITTER_EMAIL               |
            GIT_COMMITTER_DATE               /
            GIT_INDEX_FILE                   ONLY on the commands that need the isolated index
                                             of O-1 or the §7.1.4 snapshot; absent everywhere
                                             else, so no command touches an index by accident
            Any further variable a final design needs must be added to this list explicitly. A
            variable that is not on it is not set, and a variable that is inherited is not kept.
            Nothing is added to class A: its environment is the stripped parent environment and
            nothing more.

identity    ONE MECHANISM, in TWO ORDERED PHASES. An earlier draft offered
precedence  `git var GIT_AUTHOR_IDENT` / `GIT_COMMITTER_IDENT` and the resolved
            `user.name` / `user.email` as EQUIVALENT ways to capture the identity. THEY ARE NOT
            EQUIVALENT, and the difference is the whole of this rule: MEASURED (M-63), with
            hostile inherited GIT_AUTHOR_NAME / GIT_AUTHOR_EMAIL / GIT_COMMITTER_NAME /
            GIT_COMMITTER_EMAIL, `git var GIT_AUTHOR_IDENT` returned `Attacker <evil@x>` and
            `git var GIT_COMMITTER_IDENT` returned `AttackerC <evilc@x>`. Because the capture
            necessarily runs BEFORE the configuration is neutralized, a poisoned capture would
            then be re-injected into class B as an ALLOWLISTED value — so the hostile identity would
            survive through the very rule that claims to remove it. `git var ...IDENT` is
            WITHDRAWN as an authorized capture mechanism.

            PHASE A — CONFIGURATION CAPTURE. This invocation is CLASS A of the environment rule
            above: every inherited `GIT_*` variable is already removed, and the
            configuration-neutralization variables are NOT yet set. The Project root is given on
            the command line rather than through the environment:

                git -C <project root> config --get user.name
                git -C <project root> config --get user.email

            and nothing else is ever run in class A.

            `--get` reads the MERGED configuration with ordinary precedence, so system, global
            and repository-local settings decide exactly as they always did; `-C` survives the
            strip because it is an argument, not a variable.
            MEASURED (M-63): with repository-local identity present this returns `Real Person` /
            `real@proj`, the global `Global Person` correctly overridden.
            MEASURED (M-64): with identity ONLY in global config — no repository-local
            `user.name` or `user.email` — and hostile GIT_AUTHOR_*, GIT_COMMITTER_*,
            GIT_INDEX_FILE, GIT_OBJECT_DIRECTORY, GIT_ALTERNATE_OBJECT_DIRECTORIES and
            GIT_CONFIG_COUNT/KEY_0/VALUE_0 all inherited, the stripped capture returned
            `Global Person` / `global@example.com` and none of the hostile values. The same
            capture run with the class B neutralization variables set returned EXIT 1 and empty
            output for both fields — which is why class A must not set them.
            Either lookup failing is STOP AT ENTRY (the same condition ordinary Git reports),
            raised before anything is written. There is no fallback: no `git var ...IDENT`, no
            OS or hostname identity synthesis, and an empty value is never accepted. MEASURED
            (M-63): with no identity configured anywhere, `config --get` exits 1 with EMPTY
            output and invents nothing, where `git var` exits 128 — so removing `git var` loses
            no capability here.

            PHASE B — HERMETIC EXECUTION. Every invocation from here is CLASS B: the same strip
            stays in force, the configuration above IS NOW neutralized, and the class B allowlist
            injects the PHASE A values — and only those — as
            GIT_AUTHOR_NAME / GIT_AUTHOR_EMAIL / GIT_COMMITTER_NAME / GIT_COMMITTER_EMAIL, with
            the dates. Nothing else contributes to author or committer.

            THE ORDER IS THE MECHANISM, and it is stated once so it cannot be read either way:

                STRIP  ->  CAPTURE  ->  NEUTRALIZE  ->  HERMETIC EXECUTION

                1. strip every inherited `GIT_*` for the class A capture invocation
                2. capture the configured identity under ordinary Git configuration resolution
                3. STOP AT ENTRY if either identity field is unavailable
                4. activate the configuration neutralization
                5. construct the class B hermetic environment
                6. explicitly inject the captured identity
                7. execute every commit and proof Git operation

            NOT capture-then-strip, and NOT strip-then-neutralize-then-capture: the first leaves
            the capture poisonable (M-63), the second makes it impossible (M-64). There is no
            point at which an inherited identity variable is visible to any Git invocation of
            this operation, in either class.
            MEASURED END TO END (M-63): with GIT_AUTHOR_*, GIT_COMMITTER_*, GIT_OBJECT_DIRECTORY
            and GIT_INDEX_FILE all hostile, the raw commit carried
            `author Real Person <real@proj>` and `committer Real Person <real@proj>`, with no
            hostile value anywhere in the object.
attribute   attr.tree = <the PERSISTENCE BASIS of this commit, per §7.1.11>, on every CLASS B
pin         invocation of the sequence that resolves attributes
line        core.autocrlf=false and core.eol=lf, on every CLASS B invocation. These are CONFIGURATION,
endings     not attributes: the attribute pin does not touch them, and measured, `core.autocrlf=true`
            normalizes CRLF check-in content even with the pin in place (M-23). Git for Windows
            sets it globally by default, so this is the ordinary condition on that platform.
            Under O-3 no check-in conversion path is entered at all, so these settings are
            belt-and-braces here; they are retained because the sequence must stay safe even if a
            future step ever reads a file through Git.
object      GIT_NO_LAZY_FETCH=1        a missing object is LOCAL UNAVAILABLE and FAILS CLOSED.
semantics                              It is never an implicit fetch, never a transport helper,
                                       never a credential helper, never network. P1 R5 §4's
                                       external-process rule requires this, and a partial clone
                                       would otherwise demand-fetch from a promisor remote in the
                                       middle of a proof. The Project's promisor configuration is
                                       also read at entry (`git config --get-regexp
                                       '^remote\..*\.promisor$'`) and recorded, so the condition
                                       is visible rather than silent (M-54).
            GIT_NO_REPLACE_OBJECTS=1   an OID means the object it names, never a refs/replace
                                       view. MEASURED (M-49): without it, `cat-file -p <P>` and
                                       `rev-parse <P>^{tree}` returned the REPLACEMENT's tree
                                       `0b996586` instead of the true `8b00ff5b`. Legacy
                                       Legacy `.git/info/grafts` and a SHALLOW repository
                                       (`rev-parse --is-shallow-repository`) are checked at entry
                                       and STOP, as DEFENCE IN DEPTH ONLY: correctness does not
                                       depend on either check, because §7.1.8's RAW_PARENTS reads
                                       the stored commit object, which neither mechanism alters
                                       (M-57, M-59). The checks are retained because a graft file
                                       or a shallow clone is something a person should be told
                                       about, and because a graft file can appear at any later
                                       moment — which is precisely why it cannot be the
                                       mechanism.
            GIT_LITERAL_PATHSPECS=1    a declared path addresses exactly itself. MEASURED (M-50):
                                       without it, `ls-files -- 'd/a[1].txt'` ALSO matched
                                       `d/a1.txt`. Bound for EVERY command that consumes a
                                       declared path, not chosen per command, because which
                                       command globs is not something to rely on.
            All three are set for EVERY CLASS B invocation — plan construction, O-1...O-8,
            prepared-commit verification, RAW_PARENTS (§7.1.8), C-2, lineage/tree/delta proof,
            the Git persistence preflight, and the §7.1.4 index transaction. Class A sets none of
            them; it runs only the two `config --get` commands, which fetch no object, follow no
            promisor remote and consume no pathspec.
identity    THE ONE RULE IS `identity precedence` ABOVE, and this row adds nothing to it. It is
            kept only to say WHY the identity has to be injected at all: MEASURED (M-51), with
            the identity only in global config, neutralized configuration makes `commit-tree`
            fail with EXIT 128 "Author identity unknown", so an ordinary Project would have
            become uncommittable purely because F3 neutralizes config for persistence safety.
            The capture that prevents that is class A's, in the order `identity precedence`
            freezes — strip, then capture, then neutralize — and an earlier version of THIS row
            said only "captured before the configuration above is neutralized", which left the
            position of the strip unstated. It is not a second rule and never was.
dates       GIT_AUTHOR_DATE and GIT_COMMITTER_DATE are supplied explicitly, both equal to the one
            timestamp this commit is recorded with, so the commit identity does not depend on
            when within the operation `commit-tree` happens to run. They are part of the commit's
            identity inputs and are frozen with the rest of the plan.
other       core.hooksPath = a Workline-owned empty plain directory, core.fsmonitor=false,
            commit.gpgSign=false, gc.auto=0, maintenance.auto=false
hooks dir   proven to be an empty plain directory immediately before use, or STOP
            (review_hooks_path_invalid). This is NOT merely defence in depth any more: the
            object-driven primitive reaches hooks `commit-tree`'s own hooklessness does not
            cover, and P1 R5 §4 requires every external process the commands can invoke to be
            classified. The complete list for this primitive, with what invokes each:

                pre-commit, prepare-commit-msg, commit-msg, post-commit
                                        would come from `git commit`, WHICH IS NOT USED; and
                                        MEASURED not to run under `commit-tree` (M-37)
                reference-transaction   INVOKED BY `git update-ref` — O-7. MEASURED (M-48): with
                                        the default hooks directory it ran THREE TIMES for one
                                        `update-ref`; with the empty `core.hooksPath` it did not
                                        run at all
                post-index-change       INVOKED WHEN GIT WRITES AN INDEX — the §7.1.4 real-index
                                        transaction, and any isolated-index write. MEASURED
                                        (M-48): it RAN for a real-index `update-index` with the
                                        default hooks directory, and did NOT run with the empty
                                        one
                post-checkout, post-merge, pre-push, fsmonitor
                                        come from commands this primitive does not run; the
                                        empty directory covers them regardless

            MEASURED (M-48) over the whole sequence with marker hooks installed for pre-commit,
            commit-msg, reference-transaction, post-index-change and post-commit: running
            hash-object, read-tree, update-index, write-tree, commit-tree, update-ref AND a
            real-index update-index under the empty `core.hooksPath` wrote NO marker at all.
            The same `core.hooksPath` is passed to every invocation of §7.1.4's transaction.
capability  the running Git is proven to honour the pin, by the probe of §7.7, before the first
            commit of the sequence
```

#### 7.1.10 The staging-byte contract, now true by construction

```text
FROZEN:

    plan.entry.new_oid ==  the object id O-3 wrote        (CHECKED in O-3, or STOP)
                       ==  the index entry O-4 placed     (BY CONSTRUCTION: --cacheinfo takes
                                                           that id literally)
                       ==  the tree entry O-5 wrote       (BY CONSTRUCTION)
                       ==  the entry in the commit's tree (BY CONSTRUCTION: O-6 commits it)
                       ==  the entry in the tree C-1 owns (BY CONSTRUCTION: O-7a promotes that
                                                           exact commit id)

for EVERY commit class, and for K1 `plan.entry.new_oid` IS `Candidate.new_oid` (§7.1.1) — so for
every supported Work result, with no exception and no "usually".
```

The difference from the earlier draft is the BASIS of that claim. Before, it rested on Git behaving
correctly while re-resolving paths under a pinned attribute source — which the Windows measurement
falsified. Now the only step taking input from outside Git's object store is O-3, its output is CHECKED
against the frozen Candidate identity before anything else happens, and every later step carries object
ids only.

**What this does to the attribute pin.** The pin is **retained unchanged**, and its status is now stated
accurately rather than overstated:

```text
FOR STORAGE IDENTITY   no longer load-bearing. O-3 passes no `--path`, so no attribute is consulted
                       when the object is written, and O-4..O-6 consult none either. A material
                       transform assignment in the pinned source cannot alter what is committed.
                       The pin is DEFENCE IN DEPTH here.
STILL LOAD-BEARING     for the checkout-capability claim of §7.9: form-L over `.workline/review/**`
                       is what makes the canonical records readable back in a fresh clone, and the
                       ordinary-surface predicate is what lets §7.9's claim be made about the whole
                       tree rather than about the Review namespace alone.
STILL LOAD-BEARING     for the two-surface entry predicate of §7.8, which is evaluated BEFORE the
                       executor runs and is therefore not a post-executor refusal of a result shape.
```

The pin is not removed on the strength of one platform's measurement of one Git version. It is
re-classified, and the re-classification is what is frozen.

#### 7.1.11 The two bases, and why they are one persistence basis

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
is part of the frozen `review-v1-work-local-v2` identity, so it is bound into the Context (F2 §10.3) and
into Review validity through R6/R11: a Review is valid under the persistence semantics it was taken with,
and those semantics are now named exactly rather than inherited from whatever the working tree happens to
hold when the commit runs.

```text
The identity is distinct from "review-v1-planning-local-v1", and the BEHAVIOURS ARE NOW DIFFERENT
TOO: planning keeps the contained commit primitive, Work uses the object-driven sequence of §7.1.2.
An earlier draft said the two behaved "the same today" and justified the separate identity by what
COULD diverge later; that divergence has now happened, which is why A-7 moved the Work value to
"review-v1-work-local-v2" rather than redefining a shared string.

The reasoning is unchanged and is what A-7 acted on: the Context binds this string (F2 §10.3) and
R6/R11 bind it into Review validity, so two contracts sharing one identity would let a change made
for one silently redefine what the other was validated under — and redefining an identity IN PLACE
does the same damage to readers of the older contract. Sharing an identity is prohibited; sharing
an implementation is not, and the planning implementation is untouched.
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
IMMEDIATELY BEFORE EVERY commit this operation makes with "review-v1-work-local-v2" — S-c0, every
pre-completion Work stage, every Work Review generation commit (§7.1.7), S-c1/K1 and S-c2/K2:

  1. determine the EXACT path set that commit will write. Under §7.1.2 that set is COMPUTED,
     not narrowed by a pathspec: it is exactly the paths O-4 places or removes — the Candidate's
     changing entries and its deletions for S-c1, this Run's own Review record paths for a
     generation commit, the event log for S-c0, the terminal paths for S-c2. Never a wider set
     and never a nominal one;

  2. evaluate the attributes of exactly those paths UNDER THE PINNED SOURCE — the same
     attr.tree = <tree of declared_base.base_commit>, the same neutralized system and global
     sources, that the commit itself will run with (§7.1).

     Evaluating against the working tree instead would let the evaluation and the storage
     disagree, which is precisely the defect M-22 records in the live effective evaluation;

  3. apply the TWO-SURFACE requirement of §7.8.2 to those paths — not a blanket "every
     material attribute unset", which would refuse this operation's OWN generation commits:

         ORDINARY / RESULT PATHS      "unspecified" or "unset" for EVERY material attribute —
                                      filter, ident, working-tree-encoding, text and eol
                                      (M-23, M-24)
         RESERVED REVIEW PATHS        exactly the canonical form-L state and nothing else:
         `.workline/review/**`        text UNSPECIFIED (`!text`), filter UNSET, ident UNSET,
                                      working-tree-encoding UNSET, eol = lf. Any other value,
                                      or any additional material assignment, FAILS.

     and in both surfaces require that the effective configuration define no filter driver named
     "unset" or "unspecified";

     `eol = lf` IS A MATERIAL TRANSFORM AND IS NOT PRETENDED OTHERWISE. Measured, M-26: a CRLF
     file staged under `.workline/review/**` with the full pin in place came out CHANGED, not
     RAW — `eol=lf` normalizes on check-in EVEN WITH `text` unspecified. It is required all the
     same, because it is what makes canonical Review records readable back in a fresh clone
     (§7.9.3, PB-3). Two things keep that from contradicting the storage-identity invariant:
     A-5 puts the whole namespace out of reach of any Candidate entry, so no reviewed artifact is
     ever stored through it; and §7.1.2's O-3 writes this operation's own Review records from
     their exact bytes with no `--path`, so no check-in conversion runs on them either (M-40) —
     Workline's canonical serializer emits LF-only content in any case, making the rule a no-op
     on the bytes it actually governs.

     A DRAFT THAT SAID OTHERWISE IS CORRECTED HERE: demanding every material attribute unset on
     every path would have made the Review's own generation commits unsatisfiable, since they
     write exactly the paths form-L governs.

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

    the UNIVERSAL SOURCE PREDICATE of §7.8 passes, IN ITS TWO-SURFACE FORM: every attribute
      source of the pinned configuration — every .gitattributes in the base tree at every depth,
      plus .git/info/attributes — is parsed, and
          ORDINARY SURFACE   no rule assigns any material attribute (filter, ident,
                             working-tree-encoding, text, eol, after alias expansion)
          RESERVED SURFACE   a rule confined to `.workline/review/**` must be exactly the
                             canonical form-L rule, which is REQUIRED rather than refused
                             (§7.8.2, §7.9.3, PB-3)
      and none defines an [attr] macro. The predicate is over the SOURCE, not over paths, so it
      covers result paths that do not exist yet. Saying "no material attribute at all" here would
      contradict §7.8.2 and would make every P2-capable Project unusable for P3 Work Review;

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

  WHY IT IS RETAINED NOW THAT STORAGE NO LONGER NEEDS IT. The object-driven primitive (§7.1.2)
  makes the committed object independent of every attribute, so this refusal is no longer what
  protects storage identity. It is retained for two reasons that remain: §7.9's checkout-capability
  claim is a claim about reading the tree back, which filters DO affect; and relaxing it here would
  turn an input this contract version refuses into one it accepts, which is a boundary change this
  round is not making. Widening it is a candidate for a later version, evaluated on its own.

AFTER THE EXECUTOR — no RESULT SHAPE is refused

  The pin makes an executor-authored transform irrelevant to how this operation STORES objects
  (§7.4.2), so there is no post-executor transform refusal at all: such a result is stored
  exactly, expressed in the Candidate and reviewed.

  Two things are nevertheless decided after the executor returns, and neither is a shape refusal:

    AUTHORIZATION   a result whose RESULTING TREE breaks canonical Review checkout capability is
                    fully expressible and fully reviewable, and cannot be sealed (§7.9). That is
                    authorization being withheld, not a result being refused.

    OWNERSHIP       a result that declares a path inside EITHER reserved namespace — the
                    canonical Review namespace (A-5) or the lifecycle event log (A-6) — violates
                    the review-v1 invocation contract, which bound before the executor ran
                    (§7.8.4, §7.8.5). That is unowned state, which F2 §2.3 expressly permits
                    refusing.

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
every later commit to declared_base.base_commit, which §7.1.11 proves is the same attribute state —
with the system and global attribute sources neutralized.

Therefore the persistence semantics this operation commits under are FIXED, at the base, before
the executor runs — the same base the Candidate's object identities were computed against.

An executor-authored .gitattributes is therefore an ORDINARY RESULT and nothing more. It is
committed, with its new content, as an ordinary file entry (F2 §6.4's rule for .gitmodules,
applied to the same question). It does not change how this operation stores any object, so it
cannot make any commit of this operation deviate from the Candidate, and there is nothing to
refuse.
```

Measured, in the LIVE planning primitive's shape — `git add` then `git commit --only`, which is what
F3's own primitive no longer uses (§7.1.0) — with a clean filter that the new `.gitattributes` assigns to
the result path (M-20). The measurement is retained because it is what establishes the pin's effect on
Git's check-in conversion path, which is a fact about Git rather than about F3's call sequence:

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

```text
AND THE PRIMITIVE CLOSES ITEM 1 INDEPENDENTLY, which is why §7.1.10 re-classifies the pin rather
than leaning on it. §7.1.2's O-3 writes the object from the WITNESSED BYTES with no `--path`, so
Git's check-in conversion path is not entered at all and no attribute is consulted (M-40); the
returned id is then CHECKED against Candidate.new_oid before anything else happens. Identity
therefore holds even if the pin were ineffective on some Git build the probe failed to catch.

Item 2 likewise holds twice over: under the pin no filter is applicable (M-20), and under the
primitive no command that could invoke one is ever run on the artifact.

Item 3 is unchanged and is the one that still rests on the pin's PLACEMENT — the predicate is
evaluated at ENTRY, before the executor runs (§7.4), which is what keeps it from being a
post-executor refusal.
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
declared_base.base_commit (§7.1.11) — and every persistence evaluation this operation makes is
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

    THE TWO-SURFACE RULE holds under the pinned source (§7.1, §7.8.2):

        ORDINARY SURFACE   no material attribute — filter, ident, working-tree-encoding, text,
                           eol, or the alias crlf — applies to any ORDINARY path this operation
                           will write, which is every result path and the event log.
        RESERVED SURFACE   the canonical form-L rule is REQUIRED over `.workline/review/**`, so
                           the Review record paths and the Consumption path are governed by it
                           rather than by the ordinary rule (§7.9.3).

A base tree that assigns no material attribute to any ORDINARY path satisfies the first half for
every path at once, including paths whose identifiers are not yet allocated, which is why it is
the condition the entry refusal (§7.4) actually tests. The second half is the single supported
configuration P2 already freezes for its own checkout capability (`skills/review`), and refusing
it would make every P2-capable Project unusable for P3 Work Review — which is precisely the
mistake an earlier draft made by demanding "no material attribute at all" everywhere.
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
neutralizes them on every CLASS B invocation (§7.1, §7.1.9)

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

By §7.1.11 the conclusion carries unchanged to `declared_base.base_commit`.

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

  THE CHECK RUNS BEFORE declare_own_content (§5.1 steps 5b, 5c and 5d). declare_own_content writes
  the _OWN_CONTENT note through set_note, which calls _save(), so it durably asserts that the
  declared paths are this mutation's own. Refusing after that would mean durably claiming
  ownership of a path the contract says may never be owned, and only then rejecting it.

  refusal identity:  ReconcileRequired, carrying the frozen reason

                         ReconcileRequired(reason = "review_reserved_namespace")

                     The recovery CLASS is `reconcile_required`, which is what F2 §2.3 says an
                     unowned-state refusal is, and the dedicated semantic identity is the
                     reason. The previous draft froze a plain StopError and simultaneously
                     claimed §2.3 was retained unchanged; those could not both hold, and the
                     StopError form is withdrawn.
```

#### The exact path identity the check requires

A prefix test over the declared string is **not** sufficient and must not be implemented. Measured
(M-28): `is_review_path` is only `relative.startswith(".workline/review/")`, while `ProjectStore.abs` is
`root / relative` — so `./.workline/review/gates/x.yaml` and `.workline/runtime/../review/gates/x.yaml`
both pass the prefix test as "not Review" while reaching the Review namespace on the filesystem.

The frozen rule has three layers, all required, evaluated on the declaration as START's existing
normalization leaves it (`p.replace("\\", "/")` and nothing more):

```text
LAYER 1 — CANONICAL SPELLING (lexical).  §5.1 step 5b

  The declared path MUST satisfy the landed predicate `mutation._safe_relative` (M-28):

      non-empty, and a string
      not absolute                  (no leading "/")
      not drive-qualified           (no ":" in the first component — also catches UNC once
                                     backslashes have become separators)
      no empty component, no "." component, no ".." component
      no backslash survives, because step 5a has already turned every one into a separator

  F3 REFUSES every non-canonical spelling; it does NOT rewrite one into a canonical form.
  Silently turning `./x` into `x` would replace one declared result identity with another after
  the executor returned, which is exactly what this contract refuses to do anywhere else.

  failure -> MALFORMED DECLARATION (see "How a malformed declaration is classified", below)

LAYER 2 — RESERVED OWNERSHIP CLASSIFICATION.  §5.1 step 5c

  TWO reserved namespaces, both bound by the invocation contract before the executor ran:

      A-5   [".workline", "review"]                  the Review root ITSELF, and
            [".workline", "review", ...]             every descendant
      A-6   [".workline", "events", "events.jsonl"]  the lifecycle event log, exactly that path
                                                     and nothing else in that directory

  compared COMPONENT BY COMPONENT — never by string prefix, which is what lets `.workline/reviewX`
  be correctly accepted and `.workline/review` itself be correctly refused. A-6's set is exactly
  one path: `.workline/events/other.txt` is NOT reserved, and widening it would refuse an input
  that is lawful today.

  THE LEXICAL COMPARISON ALGORITHM IS FROZEN EXACTLY, and it is not "case-insensitive" left to the
  implementation:

      ASCII-ONLY CASE FOLD. In the declared component, every code point in U+0041..U+005A
      (ASCII A-Z) is mapped to the corresponding code point in U+0061..U+007A (ASCII a-z).
      EVERY OTHER CODE POINT COMPARES LITERALLY, unchanged. The folded component is then compared
      to the reserved literal by exact code-point equality.

      NOT locale-aware comparison.
      NOT the filesystem's own comparison.
      NOT str.lower(), str.casefold(), Unicode simple or full case folding, or any mapping that
        can change length or fold non-ASCII code points.

  THE LEXICAL FOLD IS A PRE-FILTER, NOT THE PROOF, AND IT IS NEVER THE SECURITY AUTHORITY. It is
  deterministic and platform-independent, which is what a lexical rule must be, and it refuses the
  common aliases early. But it is an EMULATION of a filesystem comparator, and emulating one is
  not a positive proof that some other spelling cannot reach the same object. Windows compares
  filenames through Unicode upcase tables — NTFS stores a per-volume `$UpCase` — so the mapping is
  a property of the volume, not of this contract.

  MEASURED on the NTFS volume available here:

      ".workline"         reaches the canonical object
      ".WORKLINE"         SAME OBJECT   (mkdir -> FileExistsError, read succeeds)
      ".Workline"         SAME OBJECT
      ".workl\u0131ne"    (U+0131)  DISTINCT object (mkdir succeeded, read FileNotFound)
      ".WORKL\u0130NE"    (U+0130)  DISTINCT object

  So the ASCII aliases are real and must be caught, while the dotless-i hypothesis does NOT hold
  on this volume. That is exactly why the fold cannot be the proof: it happened to match here, on
  one volume, and a differently formatted volume is not this contract's to predict.

  THE PROOF IS FILESYSTEM OBJECT IDENTITY. It dominates any comparator, lexical or native, because
  it asks the filesystem WHICH OBJECT was reached instead of guessing which names are equal. Layer
  2 performs its OWN no-follow walk to obtain it — it does not borrow layer 3's, because layer 2
  runs FIRST (§7.8.6) and a reserved declaration must never reach layer 3 at all:

      2a  ANCESTORS ONLY. Walk from the Project root toward the declared path, opening each
          ancestor component with no-follow semantics — `openat(parent_fd, name, O_NOFOLLOW|
          O_DIRECTORY)` on POSIX, the equivalent handle open without reparse traversal on Windows
          — and take each opened directory's OBJECT IDENTITY: POSIX (st_dev, st_ino); Windows the
          volume serial plus the file index, from the open handle. The declared path's FINAL
          component is not opened at this sub-step and is never traversed through.

      2b  CANONICAL IDENTITIES. Take the identity of whichever of these exist, by the SAME
          no-follow metadata query 2d uses — never by an O_NOFOLLOW open, so that an indirection
          standing where a canonical object belongs is IDENTIFIED rather than merely refused:
              .workline/review          normally a directory
              .workline/events          normally a directory
              .workline/events/events.jsonl   normally a plain file, never read here
          A canonical path that is NOT the plain object kind it should be is a Project state this
          operation does not repair: its identity is still taken, so 2c/2d stay answerable, and
          the Review-generation side refuses separately under its own rules (fsafe).

      2c  ANCESTOR MATCH. If any opened ancestor of the declared path IS the `.workline/review`
          object, the declaration is RESERVED under A-5, whatever it was spelled.

      2d  FINAL-COMPONENT MATCH, WITHOUT DEREFERENCING IT AND WITHOUT REFUSING AN INDIRECTION.
          If the declared path's final component EXISTS, take ITS OWN identity — the identity of
          whatever object the name denotes, be it a regular file, a directory, a symlink or any
          other reparse point — and compare it to the canonical identities from 2b. If it is the
          `.workline/review` object the declaration is RESERVED under A-5; if it is the
          `.workline/events/events.jsonl` object it is RESERVED under A-6.

          THE PRIMITIVE IS A NO-FOLLOW METADATA QUERY, NOT AN OPEN. This is stated exactly because
          an earlier draft got it wrong:

              POSIX    os.stat(name, dir_fd=<proven parent fd>, follow_symlinks=False)
                       — fstatat(..., AT_SYMLINK_NOFOLLOW); identity = (st_dev, st_ino), and
                       S_ISLNK says whether it is a symlink
              Windows  the `fsafe` NtCreateFile(RootDirectory=<proven parent handle>,
                       FILE_OPEN_REPARSE_POINT) form followed by GetFileInformationByHandle;
                       identity = volume serial + file index, and
                       dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT says whether it is an
                       indirection. `os.supports_dir_fd` is EMPTY on Windows (M-47), so `dir_fd`
                       is not available there and this backend is the handle-bound form.

          AN `O_NOFOLLOW` OPEN MUST NOT BE USED HERE. On POSIX it REFUSES a symlink with ELOOP
          instead of identifying it, so a draft built on it turned every valid F2 mode-120000
          symlink result into `review_candidate_unavailable` BEFORE layer 3 ever ran — refusing
          exactly the result shape F2 §6.4 supports and §21.12 records as ACCEPTED. That draft is
          withdrawn. MEASURED, M-47: the no-follow identity of a reparse point is its OWN identity
          (`st_ino=11258999074582616`) and differs from its target's (`4785074610237389`), so an
          indirection can be identified without being followed.

          THE REQUIRED DISTINCTION, frozen:

              FINAL component is a symlink / reparse object
                  its identity IS established; it is not a canonical reserved object; the
                  declaration PROCEEDS to layer 3, where F2's symlink result semantics apply and
                  the link is still never dereferenced
              ANCESTOR component is a symlink / junction / reparse object
                  containment failure, fail closed — unchanged

          A valid final symlink is NEVER refused merely for being a symlink.

          IF THE FINAL COMPONENT DOES NOT EXIST, no physical comparison is possible for it, and
          this contract does not pretend otherwise. An earlier draft said the lexical fold was
          sound there "because the canonical event log exists from the moment the mutation is
          opened". THAT IS WRONG and is withdrawn: 5c runs AFTER the executor, and the executor
          may have DELETED the event log — which is exactly the declaration being judged. A proof
          the runtime can no longer perform is not a proof.

          THE HONEST BEHAVIOUR, frozen, and still fail-closed:

              the exact spellings and the ASCII-fold aliases are caught at 2c/2d regardless, by
                the lexical half, which needs no object;
              a filesystem-specific alias spelling that passes the lexical pre-filter while the
                object is gone reaches LAYER 3, which for a DELETION requires an exact tracked
                identity for THAT DECLARED GIT PATH in PRE_S_C0_BASE (§7.8.4's deletion rule);
              a spelling that is not a tracked path in PRE_S_C0_BASE is unprojectable and is
                refused as `review_candidate_unavailable` BEFORE ownership is asserted — a
                projectability refusal, NOT `review_reserved_namespace`, because this operation
                cannot show the path is reserved, only that it cannot place it.

          So the reserved surface is not breached, and the refusal is named for what was actually
          established. The residual is stated rather than hidden: a volume-specific alias of a
          DELETED reserved path is refused as unprojectable rather than as reserved, which is a
          difference in reason value and not in safety.

      2e  UNKNOWN IS NOT A PASS, AND IT IS NOT THE SAME REFUSAL. The two outcomes of this layer
          are different recovery classes and are never merged:

              RESERVED MATCH — 2c or 2d identifies a canonical reserved object, or the lexical
              fold matches a reserved component sequence
                  -> ReconcileRequired(reason = "review_reserved_namespace")
                     unowned state: the declaration is over something the invocation contract
                     reserved before the executor ran

              IDENTITY UNANSWERABLE at 2a, 2b or 2d, or projectability otherwise unknown
                  -> review_candidate_unavailable
                     not a claim that the path IS reserved; a claim that this operation cannot
                     say what it is, which fails closed before ownership is asserted

          No blanket "failure -> review_reserved_namespace" sentence may stand beside this. A
          refusal that cannot name which of the two it is, is the second one.

  This is what makes A-6 ALIAS-SAFE PHYSICALLY and not merely lexically: a declared path that
  reaches the canonical event log by any spelling, through any directory alias the volume honours,
  is classified reserved by 2d because the object it reaches is the object compared — the same
  authority A-5 uses, applied to A-6's single path.

  When a canonical directory does not exist yet — `.workline/review` is created lazily — there is
  no object to compare against for it, and the lexical fold is then the whole test for that
  namespace. That is sound in that state precisely because there is no Review object for an alias
  to reach.

  Layer 2 opens directories, so it is physical evidence inside a classification step. That is
  deliberate and it reorders nothing: it asks only WHICH OBJECT an ancestor or the final component
  IS, and it never judges whether the final object is a valid result — a directory, a file, a
  symlink or absent. That question belongs to layer 3, and only for paths layer 2 has cleared.

  outcome -> per 2e: a RESERVED MATCH is
             ReconcileRequired(reason = "review_reserved_namespace"); an UNANSWERABLE IDENTITY is
             `review_candidate_unavailable`. The two are never collapsed.

LAYER 3 — PROJECT CONTAINMENT AND THE BOUND OWNERSHIP WITNESS.  §5.1 step 5d

  Layers 1 and 2 are lexical, and a lexical test cannot see a symlinked or junctioned ANCESTOR
  directory that makes an innocent-looking path reach a canonical Review object.

  Walk from the Project root toward the declared path one component at a time, following
  nothing, proving every component that EXISTS is a plain in-Project directory — the discipline
  `review.fsafe` already implements, and the reason its module gives for binding to handles
  rather than to names (M-29).

  A MISSING COMPONENT MEANS DIFFERENT THINGS FOR A RESULT AND FOR A DELETION, and the previous
  draft collapsed them. That was wrong and is withdrawn: it would have refused an ordinary
  correct deletion after the executor returned, which F2 §2.3 forbids.

      RESULT PATH — the object must EXIST when Completed is returned (F2 §6.2, live
      completion_precheck). So every ancestor required to reach the final name must exist and be
      proven plain:

          every ancestor exists and is a plain in-Project directory   -> containment proven
          any ancestor is a symlink, junction or other reparse point  -> FAIL CLOSED
          any ancestor is missing                                     -> FAIL CLOSED
          any ancestor's identity cannot be established               -> FAIL CLOSED

      DELETION PATH — the object is expected to be ABSENT now, and its identity comes from the
      base tree rather than from the filesystem (M-30: completion_precheck requires a deleted
      path to be absent and tracked, and requires nothing of its parent).

      WHICH base tree, exactly: step 5d runs BEFORE S-c0, so `declared_base.base_commit` — the
      post-S-c0 HEAD — DOES NOT EXIST YET. The witness therefore binds the tracked identity in
      PRE_S_C0_BASE, and §7.8.5 proves that this is the same entry `declared_base` will hold for
      every path a review-v1 Work is allowed to declare. The previous draft said "declared_base /
      the base tree" here, which was impossible at that point in the sequence, and is withdrawn:

          the walk reaches the parent, and the final name is absent relative to it
                                                         -> POSITIVE ABSENCE, accepted
          the walk finds an ancestor component MISSING    -> POSITIVE ABSENCE, accepted:
              a path cannot exist beneath a component that does not exist, so the first missing
              ancestor PROVES the declared path is absent. It is not "containment unknown".
          any EXISTING ancestor is a symlink, junction or other reparse point  -> FAIL CLOSED
          any EXISTING ancestor's identity cannot be established               -> FAIL CLOSED

  THE FINAL COMPONENT IS NEVER DEREFERENCED. F2 supports a symlink as a result object, and this
  layer must not break that: what is proven is the chain that leads to the name, not what the
  name itself resolves to.

  failure -> for a RESULT, containment unknown -> MALFORMED DECLARATION (below).
             For a DELETION, only an existing-but-unprovable ancestor fails; a missing one does
             not. Not knowing is not a yes, but a proven absence is not a not-knowing.
```

```text
THE BOUND OWNERSHIP WITNESS — closing the check/use race.  §5.1 step 5d, persisted at step 6

`review.fsafe`'s own module states the problem this solves: "Checking a path and then using the
path is two operations, and anything can happen between them: a component can be replaced with a
symlink or a junction, and the second operation - the one that actually reads or writes - follows
it. Adding a second check narrows that window without closing it."

The previous draft proved containment at 5d and then let step 6 call the live
`declare_own_content`, which resolves `ProjectStore.abs(path)` — `root / relative` — and digests
whatever that pathname reaches. That is a SECOND root-relative resolution, so the object digested
need not be the object proven. Withdrawn.

FROZEN: layer 3 does not merely check. It produces a BOUND OWNERSHIP WITNESS per declaration, and
step 6 persists that witness WITHOUT re-reading the declared path by ordinary pathname.

    CHECKED OBJECT  ==  DIGESTED OBJECT  ==  OWNERSHIP-ASSERTED OBJECT

    no second root-relative pathname resolution may substitute another filesystem object between
    those steps.

THE WITNESS IS PER-KIND, AND IT IS NOT THE CURRENT `_content_digest` FORM. The previous draft
claimed the witness needed "no recorded form changes and no downstream reader changes". That was
FALSE and is withdrawn, on measurement: a gitlink digests to `None`, is stored as `"unreadable"`,
and the later guard compares `None != "unreadable"` and refuses the commit (M-32); and the mode
is not in the form at all, so `100644` vs `100755` is invisible to it (M-33).

```text
EVERY witness binds, for every F2-supported kind:

    path        the declared canonical path
    kind        "file" | "symlink" | "gitlink" | "absent"
    git_mode    "100644" | "100755" | "120000" | "160000" | "000000"
    identity    the exact Git object identity for that kind, and the exact material where the
                kind has material
    captured    RELATIVE TO THE PROVEN PARENT — the handle chain is held across the capture and
                the final entry is stat'd / read / readlink'd relative to that parent, never
                reopened as `root / declared_path`

PER KIND, exactly:

    100644 / 100755 file
        git_mode  from the entry's executable bit as Git records it, NOT from the filesystem
                  permission alone where the platform does not carry one
        identity  the exact bytes, and their RAW Git blob id — `hash_blob` of those bytes, with
                  no attribute or filter machinery consulted, which is what F2 §6.3's new_oid is
                  and what §7.1.2 O-3 reproduces and checks (M-40)
        material  the exact bytes, which become the CandidateSnapshot payload (F2 §9.4)

    120000 symlink
        identity  the exact link-target bytes, read with no-follow semantics and NEVER followed,
                  and their Git blob id
        material  those same target bytes, as F2 §9.4.1 requires

    160000 gitlink
        identity  THE EXACT REFERENCED COMMIT OID, read by HANDLE-BOUND READS ONLY.

                  AN EARLIER DRAFT FROZE `git -C <the submodule path> rev-parse HEAD`. THAT IS
                  WITHDRAWN. `-C` hands a PATHNAME to a second process, which re-resolves it from
                  the root; a path "assembled from the proven chain" is NOT equivalent to using
                  that chain's handles. The gap is real cross-platform: `fsafe`'s own analysis
                  says a POSIX fd "pins nothing - the directory it holds can be renamed anywhere
                  while it is held", so containment proven at 5d does not keep the PATH pointing
                  at the proven directory, and `git -C` could be made to read another repository
                  entirely.

                  FROZEN — every step is a read relative to a handle already held, and no
                  pathname is re-resolved at any of them:

                    G-1  the submodule directory handle comes from the SAME proven chain as every
                         other kind (§7.8.4 layer 3), never from a fresh walk
                    G-2  read `.git` from that handle. MEASURED, M-46: in a real submodule it is a
                         FILE holding `gitdir: ../.git/modules/sub` — a RELATIVE path — not a
                         directory, so this indirection must be resolved and is the only place the
                         chain could leave the held handles
                    G-3  resolve that gitdir COMPONENT BY COMPONENT AGAINST THE HELD CHAIN: each
                         `..` steps back to a handle the chain ALREADY HOLDS, and each name opens
                         the next component no-follow from the handle before it. An ABSOLUTE
                         gitdir, a `..` that would step above the Project root, and any component
                         that is an indirection each FAIL CLOSED. When `.git` is a directory
                         rather than a gitfile, G-2/G-3 collapse to opening it from G-1's handle
                    G-4  read `HEAD` from the resulting handle. A raw 40/64-hex line IS the
                         identity; `ref: <name>` is resolved by reading `<name>` from that same
                         handle, and failing that the handle's `packed-refs`
                    G-5  the result must be a full object id. Anything else fails closed

                  MEASURED END TO END, M-46, using `workline.review.fsafe`'s existing
                  cross-platform handle-bound primitives and NO Git process: the chain yielded
                  `f600f63fd1c8ea463c51608453299e0a1a9a200c`, which is EXACTLY what
                  `git -C sub rev-parse HEAD` returns and exactly what `git ls-files --stage sub`
                  shows as `160000 f600f63f...`. The handle-bound read reproduces Git's own answer
                  without ever handing a pathname to a second process.

                  NOT the superproject's index entry, which still holds the OLD commit until
                  something stages it — reading it would witness the pre-executor value.
                  NOT a branch name or any symbolic ref, which is not an identity; G-4 resolves a
                  symbolic HEAD to an id and never records the name.
                  NOT derived from the submodule's working-tree contents, which do not determine
                  the referenced commit at all.
                  NOT a fallback to refusing gitlinks: F2 requires them supported, and this is why
                  a portable mechanism had to be frozen rather than the kind dropped.

                  This is what F2 §6.3 calls new_oid for this kind, and §7.1.2 O-4 places it
                  directly with `--cacheinfo 160000,<oid>,<path>` — O-3 writes no object for a
                  gitlink, because the identity already IS a commit id.
        material  NONE. F2 §9.4.1 gives a gitlink no payload; the entry IS the material

    absent (deletion)
        identity  the exact TRACKED identity in the base tree (§7.8.4's deletion rule), plus the
                  positive current-absence witness from the walk
        material  NONE
```

```text
THIS NEEDS A RUNTIME EXTENSION, AND IT IS NAMED RATHER THAN ASSUMED: `_OWN_CONTENT` must be able
to hold a per-kind witness rather than only the four `_content_digest` strings, and the
currentness comparison must compare the whole witness — kind, mode and identity — rather than a
single digest string. See IP-16. This is RUNTIME / RECOVERY material only: no canonical Review
record and no Candidate schema changes.
```

```text
THE CANDIDATE DERIVES FROM THE WITNESS, NOT FROM A REREAD.  (F2 ST-1)

F2 ST-1 freezes that START freezes the Work Candidate from the declared owned set AT THE MOMENT
THE EXECUTOR RETURNS. The witness IS that moment's exact capture, so §5.1 step 10 CONSUMES it:

    for every Candidate entry, new_kind, new_mode, new_oid and content_sha256 are taken from the
      bound witness for that path — never by an ordinary path-string reread of the working tree;
    the CandidateSnapshot payload bytes for a file or a symlink are the exact bytes the witness
      binds;
    for a gitlink, new_oid is the exact referenced commit OID the witness binds;
    for a deletion, new_kind is "absent" and the absence material derives from the positive
      absence witness.

    old_kind / old_mode / old_oid continue to come from the base tree, as F2 §6.3 says.

FROZEN INVARIANT:

    EXECUTOR-RETURN ARTIFACT == OWNERSHIP WITNESS == CANDIDATE IDENTITY == SNAPSHOT MATERIAL

A foreign change between step 6 and step 10 therefore CANNOT become the thing Review judges: the
Candidate is built from what was captured, not from what the path holds when step 10 runs.
```

WHY THE HANDLE-BOUND READ IS SOUND HERE, including on POSIX. fsafe warns that on POSIX "an fd
pins nothing: the directory it holds can be renamed anywhere", and for that reason refuses an
immutable CREATE on POSIX. That limitation is about WHERE A CREATE LANDS. This operation creates
nothing: it captures what the executor already produced, and fsafe's own docstring lists
`openat(parent_fd, name, O_NOFOLLOW ...)` as "relative to the proven fd (reads only)" — exactly
this case (M-31). A renamed ancestor carries the proven directory OBJECT with it, and the read
still reads that object, which is the object whose containment was proven. On Windows the
no-follow / reparse handling is preserved unchanged: every directory is opened without following,
and the final entry is opened with reparse-point semantics rather than being resolved.

Unknown identity at any point -> FAIL CLOSED, before any ownership assertion.
```

```text
THE WITNESS ALONE DOES NOT CLOSE THE STAGING RACE. THE PRIMITIVE DOES. BOTH HALVES MEASURED.

The witness is taken at executor return. Review can take arbitrarily long. An ancestor component
of a declared path can be replaced in between.

MEASURED (M-34), Windows/NTFS: with `dir` replaced by a JUNCTION (reparse tag 0xa0000003),
`git add -- dir/file.txt` SUCCEEDED and staged the blob from the junction's target, not HEAD's.
So Git does NOT mechanically refuse ancestor indirection at staging on Windows. The re-review's
POSIX result — `fatal: pathspec ... is beyond a symbolic link` — is recorded as THEIR
measurement; this environment is Windows only and did not reproduce it.

THAT IS WHY THE STAGING PRIMITIVE NO LONGER RESOLVES PATHNAMES AT ALL. §7.1.2 replaces
`git add`/`git commit --only` with the object-driven sequence: the PLAN's material — for K1, the
witnessed bytes — is hashed into an object, that object id is checked against the plan's new_oid,
and the index entry is written by `update-index --cacheinfo <mode>,<oid>,<path>`, which touches no
filesystem.

MEASURED (M-36), same junction, ACTIVE THROUGHOUT: the committed tree held the WITNESSED blob
`924c75cd`, and the junction target's blob `b2f3ae2a` appeared nowhere in the commit. The witness
is what reaches K1 even while the redirection is in force.

Therefore F3 does NOT claim the initial witness closes this race, and does NOT claim Git closes it.
**Nor does it claim any longer that a check closes it.** An earlier draft answered with
"pre-stage containment re-proof + full-witness currentness + C-2(K1)", argued that a redirection
"either changes the identity — refused before staging — or does not — no breach", and concluded the
invariant held. **That argument is withdrawn.** Its first branch is false for a swap AFTER the
check: a check and a later use are two operations, and nothing in that list stood between them. Its
second branch conceded that a commit could be built through a redirection at all, which is the
concession the invariant cannot afford. And it ended at "nothing wrong is ever PUBLISHED", which is
a weaker claim than the one being made.

Three mechanisms remain, doing three DIFFERENT jobs, and exactly one of them closes the race:

  1. PRE-STAGE CONTAINMENT RE-PROOF AND FULL-WITNESS CURRENTNESS — AN EARLY REFUSAL, NOT A
     CLOSURE. Immediately before S-c1 stages, the ancestor chain of every path is re-proven by
     the layer-3 walk including the object-identity check, and the WHOLE witness — kind, git_mode
     and identity — is compared against what the path holds now. This is what makes a chmod
     (M-33) and a changed gitlink (M-32) detectable, which a single `_content_digest` string
     cannot express (IP-16). What it catches is interference that has ALREADY happened, and it
     STOPS with review_candidate_unavailable. It is retained because turning a tampered working
     tree into an early refusal is worth doing — not because it closes anything.

  2. THE OBJECT-DRIVEN COMMIT TREE PLAN — THE REASON A LATER PATHNAME RACE CANNOT ALTER THE
     COMMITTED TREE. The plan carries the witnessed bytes and identities (§7.1.1); O-3 hashes
     THOSE bytes and checks the id against the plan's; O-4 places that id under the path STRING
     with `--cacheinfo`, which opens, stats, traverses and resolves nothing. There is no later
     pathname resolution left to lose. MEASURED with the redirection ACTIVE THROUGHOUT (M-36):
     the committed entry was the witnessed blob `924c75cd` and the junction target's `b2f3ae2a`
     appeared nowhere in the commit.

  3. C-2(K1) — AN INDEPENDENT PROOF AFTER C-1, NOT A REPAIR. W4 and W5 compare the COMMITTED tree
     entries against the Candidate's by kind, mode and object id. It would catch a primitive that
     failed to hold the chain. It does NOT make the chain hold, and it cannot repair a wrong local
     K: by the time it runs, a wrong K would already exist and already be owned.

So the frozen end-to-end invariant holds for the COMMITTED artifact, not merely for the published
one, and that strengthening is the whole point of the change:

    ARTIFACT AT EXECUTOR RETURN == WITNESS == CANDIDATE == PLAN == STAGED == K1

THE PROPERTY IS NO LONGER PLATFORM-DEPENDENT, AND IT IS PINNED BY TEST.
`review-v1-work-local-v2` carries a required regression test over the measured matrix of §21.12,
asserting that the committed tree entry equals the PLANNED identity with an ancestor indirection
ACTIVE — on every platform, because the primitive never asks the filesystem. The earlier draft
pinned Git's `git add` containment behaviour instead; that behaviour is now merely recorded as a
measurement (M-34) and nothing relies on it.
```

```text
THE INVARIANT, stated once: START must POSITIVELY prove that a declared path is in NEITHER
reserved namespace — not the canonical Review namespace (A-5) and not the lifecycle event log
(A-6) — before it durably asserts ownership of that path. Unknown containment fails
closed, before declare_own_content.
```

#### How a malformed declaration is classified

```text
A declaration that fails LAYER 1 or LAYER 3 has no establishable path identity, so the declared
owned set cannot be projected exactly. That is F2 §6.5's OWN PREDICATE, and the existing
refusal is reused verbatim:

    review_candidate_unavailable

F2 §6.5 names two instances of that predicate — a declared path that is a directory, and one
that cannot be read. A path whose spelling or containment cannot be established is a THIRD
INSTANCE OF THE SAME PREDICATE, not a new one, so this is a SPECIALIZATION and needs no
amendment.

Contrast A-5, which DID extend §6.5: it added an OWNERSHIP-based invalidity, a different
predicate, with its own reason. The two are deliberately kept apart:

    malformed path identity   -> review_candidate_unavailable   (projectability)
    reserved namespace        -> review_reserved_namespace      (ownership)

They are never collapsed into one condition, because they answer different questions and a
reader needs to know which one refused.
```

```text
No extension is needed to carry it. `ReconcileRequired(message, *, reason=...)` exists in live
code as a subclass of StopError whose code is always `reconcile_required` and whose `reason`
names which review-v1 reason stopped the operation — exactly the shape this needs. F1 already
used it for `review_marker_mismatch`, so `review_reserved_namespace` joins the same catalogue as
a new REASON value, not a new code.

What is preserved by using it: the `reconcile_required` recovery class, a dedicated semantic
identity, human reconciliation semantics, and no automatic legacy downgrade.
```

```text
Why a DEDICATED IDENTITY rather than `review_candidate_unavailable`. That code means exactly one thing in
F2 §6.5 — "the declared owned set cannot be projected exactly" — which is about PROJECTABILITY, a
property of the bytes at a path. This condition is about OWNERSHIP, which is a property of the
namespace and is decided without looking at the bytes at all. Overloading one code with two
unrelated meanings is the ambiguity this contract is supposed to remove, and no existing code
states it: the contract-argument refusal is about the caller's argument, `review_containment` is
about where Review's own writes land, and `review_candidate_unavailable` is about projection.

This is the same reasoning F1 used when it introduced `review_not_activated`, and
`review_reserved_namespace` is the only new ReconcileRequired REASON VALUE F3 introduces. It is not
a new code and not a new exception class: the code stays `reconcile_required`.
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

#### 7.8.5 The reserved lifecycle event log, and why the two bases are interchangeable (A-6)

The deletion witness binds its tracked identity in PRE_S_C0_BASE, while the Candidate's entries are
measured against `declared_base.base_commit`. Those are two different commits, so F3 owes a proof that
they hold the SAME entry at every path a review-v1 Work may declare. S-c0 changes exactly one path, so
the proof reduces to one question: may an executor declare THAT path?

```text
S-c0 commits `.workline/events/events.jsonl` and nothing else (§4.3).

If an executor could declare that path as a result or a deletion, then PRE_S_C0_BASE and
declared_base.base_commit would differ AT A DECLARED PATH, and the two bases would not be
interchangeable. Checked: no landed rule excludes it. `completion_precheck` applies no namespace
restriction and `declare_own_content` takes any path — the same gap A-5 found for the Review
namespace.

So the earlier sentence "the event log is never a result path" was an UNSUPPORTED PREMISE, not a
rule. It is replaced by one.
```

**FROZEN, as an ownership boundary declared before execution — forward amendment A-6:**

```text
The review-v1 Work INVOCATION CONTRACT declares

    .workline/events/events.jsonl

to be START LIFECYCLE-OWNED state that the executor may not own — not as a result path and not as
a deletion path. The rule is static, part of what selecting review-v1 means (F1-D1), and in force
BEFORE the executor runs; the concrete future path list need not be known for it to bind.

A Completed outcome declaring it has violated a pre-existing ownership contract. It is UNOWNED
STATE, refused exactly as A-5's case is:

    ReconcileRequired(reason = "review_reserved_namespace")

carrying the same reason: the condition is the same one — a declaration over state this operation
was never permitted to own — and splitting it into a second reason would distinguish two things
that reconcile identically.

It is NOT an unsupported Git result shape, NOT `review_candidate_unavailable`, and never a legacy
downgrade. The check runs at §5.1 step 5c with the reserved-namespace check, on the same canonical
path identity established at 5b.
```

**The interchangeability proof, which is what this boundary buys:**

```text
Given A-6 and A-5, every path a review-v1 Work may declare lies outside
    .workline/review/**        (A-5)
    .workline/events/events.jsonl   (A-6)

S-c0's complete delta is exactly { .workline/events/events.jsonl }, and that path is not
declarable. Therefore, for EVERY allowed result path and deletion path:

    the tree entry at that path in PRE_S_C0_BASE
      ==
    the tree entry at that path in declared_base.base_commit

so the deletion witness's tracked identity, taken at PRE_S_C0_BASE, IS the `old_*` identity the
Candidate records against declared_base. The two bases are interchangeable exactly where it
matters, and nowhere else is claimed.
```

```text
This is the same argument §7.1.11 makes for the attribute source, and it is now the same argument:
S-c0 touches one path, that path is reserved, so nothing a Work can declare or read differs
between the two bases.
```

#### 7.8.6 Classification precedence — exactly one answer per declaration

A reserved path may be a DIRECTORY — `.workline/review` itself is one — and a directory is not a valid
result object. If the filesystem layer ran first it would classify that declaration as malformed, and A-5
would never be reached. That is two answers for one declaration, and it is fixed by precedence:

```text
1. CANONICAL SPELLING                         §7.8.4 layer 1        step 5b
     fails -> review_candidate_unavailable, and nothing further is evaluated

2. RESERVED OWNERSHIP CLASSIFICATION          §7.8.4 layer 2,       step 5c
                                              §7.8.5
     lexical component-wise test, plus the object-identity test where the canonical directories
     exist. A path classified reserved here is refused as
     ReconcileRequired(reason = "review_reserved_namespace") and NOTHING FURTHER IS EVALUATED —
     in particular the filesystem/witness layer never runs on it, so it can never be downgraded
     into the generic malformed refusal merely because its final object is a directory.

3. FILESYSTEM CONTAINMENT AND THE BOUND WITNESS, FOR NON-RESERVED PATHS ONLY
                                              §7.8.4 layer 3        step 5d
     fails -> review_candidate_unavailable (result) or, for a deletion, only where an EXISTING
     ancestor is indirect or unprovable

4. OWNERSHIP ASSERTION                        step 6
```

```text
The object-identity half of step 2 needs an opened directory, so it is physical evidence inside a
classification step. That is deliberate and it does not reorder anything: it opens ANCESTORS to
ask which object they are, and it never judges the declared path's final object. Whether the
final object is a directory, a file, a symlink or absent is a question only step 3 asks, and only
for paths step 2 has already cleared.
```

```text
A-5's reserved set is, explicitly and in both halves:

    .workline/review            the Review root ITSELF
    .workline/review/**         every descendant

and A-6 adds .workline/events/events.jsonl. All three are classified at step 2.
```

#### 7.8.7 Defence in depth, not a substitute

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

  3. the Consumption path this authorization may later create — covered WITHOUT knowing its
     identifier, because the required rule is a single pattern over the whole namespace and
     therefore guarantees the checkout capability of a future, not-yet-named path inside it.

Because the required rule is a single pattern over `.workline/review/**`, proving it covers the
whole namespace at once — including record paths that do not exist yet, which is the same reason
the entry predicate is over the source rather than over paths (§7.8.1).
```

```text
TWO DIFFERENT SCOPES, and they must not be conflated:

  FORM-L COVERAGE        applies to the namespace as a pattern, so it covers paths that EXIST in
                         the resulting tree AND paths that will be created later — the sealing
                         generation, the Receipt, and the Consumption. No identifier is needed
                         for any of them.

  STRICT-READER CHECK    applies only to records that ALREADY EXIST in the resulting tree. A
                         record that has not been written cannot be read, and its future
                         readability is exactly what the form-L guarantee provides.

So the capability decision at §5.1 step 15a requires NO reserved Consumption identifier. The
identifier is reserved after the seal (§13.2), which is where it belongs, and nothing in the
pre-seal proof depends on it.
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
  git_persistence:              "review-v1-work-local-v2"                F2 §10.3 as amended
                                                                        by A-7: same field, same
                                                                        meaning, new value
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

C-1 is reached in **two durable steps**, not one, and the split is what makes it crash-safe.

```text
O-6a  PREPARED, durable BEFORE any ref moves
        prepared_commit_id + parent + tree + ref + contract
        proves ONLY: this operation created this exact commit object
        it is NOT C-1, confers no reachability, authorizes no push, satisfies no proof item

O-7a  C-1, durable AFTER the ref is read back holding that id
        commit_id = prepared_commit_id, applied = true
        every downstream item reads THIS
```

Why the split exists, measured rather than argued:

```text
The live controller records the id only after the commit primitive RETURNS: `_make_commit`
(mutation.py:1394) calls `controller.apply_effect`, and the caller sets `applied` and saves
afterwards (mutation.py:501). Under the object-driven primitive `apply_effect` contains BOTH the
commit and the ref advance, so a crash between them leaves a moved ref and no durable ownership.

And that gap is not benign: live `_classify_commit` (mutation.py:2259) reaches

    changed = gitcmd.changed_against_head(repo, list(payload["paths"]))
    if head is not None and not changed:
        return MATCHING          # "nothing left to commit for these paths"

so on retry the effect is classified MATCHING with NO owned commit id (M-41) — the paths are
already committed, so nothing differs from HEAD. P1 R5 §3.1 / §3.5 forbid precisely that.
The prepared checkpoint removes the window: after O-6a there is always a durable id, and
§7.1.3's matrix decides every resume from it.
```

```text
A commit this operation cannot positively show it created is NEVER K, however exactly its
content, tree, parent, branch or message match (R5 §3.1). In particular:
    the branch tip is never K
    "the paths no longer differ from HEAD" is never K, and is never ownership of anything
    a commit with a matching message is never K
    a byte-identical commit made by another subject is never K
    a commit made by a hook continuing after the primitive's commit is never K
    an unreachable object this operation wrote but never durably prepared is never K (§7.1.6)

What IS positive proof is the operation's own durable prepared_commit_id, compared against the
ref it recorded. Reading a ref to ask whether it holds an id written down beforehand is not
branch-tip inference; inferring an id FROM the tip is, and that is what stays forbidden.
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
       "Holds" is `raw_descends_from` over RAW_PARENTS (§7.1.8), never `merge-base
       --is-ancestor`: a graft file or a shallow boundary changes the latter's answer (M-57,
       M-59) and changes nothing about the stored objects.

  L-4  S-c1 is base-exact BY CONSTRUCTION, not by a re-read. §7.1.2 O-2 seeds the isolated index
       from the EXACT parent(K1) object id, O-6 records that same id as the parent, and O-7
       advances the branch only under compare-and-swap against it. MEASURED, M-38: a wrong
       expected-old is refused and the ref is left untouched. So a branch that moved cannot be
       committed onto and cannot be overwritten; the CAS refusal surfaces as ReconcileRequired,
       reason review_registration_base_moved. This is strictly stronger than the live
       re-read-HEAD-twice technique (M-7), which leaves a window between the second read and the
       ref update.

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
     The S-c1 effect is recorded applied and carries commit_id = K1 — that is, O-7a completed
     (§7.10). Absent or unprovable -> review_commit_unowned. The branch tip, a matching message,
     byte-identical content, and "the declared paths no longer differ from HEAD" are never
     accepted in its place (R5 §3.1, M-41). This item is a precondition of every item below it:
     W2 ... W12 are checked against an already-owned commit and never confer ownership.

     A PREPARED COMMIT IS NOT ENOUGH. A durable prepared_commit_id without the O-7a promotion
     proves the object was created by this operation and nothing more; W1 is not satisfied, no
     proof note is written and no push may be recorded. §7.1.3 says what a resume does in that
     state, and in no row does it promote itself.

W2   PERSISTENCE SEMANTICS
     The S-c1 payload names mode "review-v1-work-local-v2", whose frozen behaviour is the
     OBJECT-DRIVEN sequence of §7.1.2; the commit was made with the attribute source pinned to
     the tree of declared_base.base_commit (§7.1.9, §7.1.11); and the Git persistence preflight of
     §7.3, evaluated UNDER THAT SAME PIN, passed IMMEDIATELY BEFORE the stage was recorded —
     topology step 17b, after the Review completed. Step 9's early run is an optimization and
     never satisfies this item, and an evaluation made against the working tree rather than the
     pinned source never satisfies it at all.

     WHAT THIS ITEM DOES AND DOES NOT PROVE, stated because the primitive changed. C-2(K1) reads
     COMMITTED OBJECTS; it cannot observe how they were produced, so it cannot verify that O-1
     ... O-8 were the steps taken. It proves the RESULT — W4 and W5 prove the committed tree is
     exactly the Candidate — while §7.1.2 is what makes that result unreachable by any other
     artifact in the first place. The two are independent, and neither is offered as the other:
     the frozen chain WITNESS == CANDIDATE == PRE-STAGE == STAGED == K1 is held by the primitive,
     and C-2(K1) is the check that would catch a primitive that failed to hold it.

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
     seq, its payload names mode "review-v1-work-local-v2", and its payload branch is the full
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
  a commit-only stage holding exactly one git_commit with mode "review-v1-work-local-v2" —
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
    S-c2 is base-exact BY CONSTRUCTION, exactly as L-4 states for S-c1: §7.1.2 O-2 seeds from the
    exact parent(K2) id, O-6 records it, and O-7 advances the branch only under compare-and-swap
    against it (M-38). No HEAD re-read window exists.
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
     The S-c2 payload names mode "review-v1-work-local-v2" — the identity A-7 freezes, never
     "review-v1-work-local-v1" and never the planning identity — and the Git persistence
     preflight of §7.3 passed for the terminal paths, under the hermetic environment of §7.1.9.
     As with W2, this item reads COMMITTED OBJECTS and so proves the RESULT rather than the steps
     taken; §7.1.2 is what makes any other result unreachable.

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
checkpoint (§5.4), exactly as the live Terminal finalization rule already requires.
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
      (_validate_planning_commit, mutation.py:1094-1110):
          "review-v1-planning-local-v1"  -> `contained_add`/`contained_commit`, unchanged
          "review-v1-work-local-v2"      -> the OBJECT-DRIVEN primitive of §7.1.2 (IP-17)
      The second is a NEW value (A-7), so the validator's closed set gains it rather than having
      an existing member redefined, and nothing that recorded the planning mode changes meaning.
      `contained_add`/`contained_commit` (mutation.py:2484) stay exactly where they are and keep
      serving the planning mode; they are never used for the Work mode, because they resolve
      working-tree pathnames. An unknown mode must stay a ValidationError. (M-5)

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

IP-8  THE ENVIRONMENT IS PER-INVOCATION, NOT "BOTH INVOCATIONS". An earlier draft said the pin
      applies "on BOTH invocations" and that what was new was "applying it to `git add` and
      `git commit`" — that describes the v1 contained primitive, which v2 PROHIBITS (§7.1.0).
      There is no pair of invocations any more: the sequence is O-1 ... O-8 and the §7.1.4
      transaction, and the requirement is stated over each of them by class.

      TWO ENVIRONMENT CLASSES, and every Git invocation of this operation is in exactly one of
      them. An earlier draft put EVERY invocation into one hermetic class that always injected
      GIT_CONFIG_NOSYSTEM and GIT_CONFIG_GLOBAL=<empty file>; that made §7.1.9 phase A impossible
      for a Project whose identity lives in global config (M-64), and it is corrected here.

        (a1) THE IDENTITY CAPTURE INVOCATION — class A of §7.1.9. Exactly
             `git -C <root> config --get user.name` and `user.email`, and nothing else, ever.
             Strip every inherited `GIT_*`; inject NOTHING; leave ordinary Git configuration
             resolution intact so the configured identity can be read; take the Project root
             from the command line. MEASURED (M-64): the strip alone already defeats hostile
             GIT_AUTHOR_*, GIT_COMMITTER_*, GIT_INDEX_FILE, GIT_OBJECT_DIRECTORY,
             GIT_ALTERNATE_OBJECT_DIRECTORIES and GIT_CONFIG_COUNT/KEY_0/VALUE_0, while the same
             command WITH the neutralization variables returns EXIT 1 and empty.

        (a2) EVERY OTHER INVOCATION — class B of §7.1.9, which is the hermetic environment:
             strip every inherited `GIT_*`, then inject exactly the class B allowlist
             (GIT_ATTR_NOSYSTEM, GIT_CONFIG_NOSYSTEM, GIT_CONFIG_GLOBAL, GIT_NO_LAZY_FETCH,
             GIT_NO_REPLACE_OBJECTS, GIT_LITERAL_PATHSPECS, and nothing else by default), with
             core.hooksPath at the empty directory, core.fsmonitor=false, commit.gpgSign=false,
             gc.auto=0, maintenance.auto=false. MEASURED that the strip is load-bearing (M-61).

        BOTH strip everything inherited; only (a2) neutralizes configuration. The strip is what
        protects against a hostile environment and has no exception; the neutralization is what
        (a1) must not have, for the one purpose that requires the configuration to be readable.

      Classes (b) and (c) below qualify (a2) invocations only: class A resolves no attributes and
      consumes no declared path, because the only two commands it ever runs do neither.

        (b) EVERY INVOCATION THAT RESOLVES ATTRIBUTES — the attribute-source pin: `attr.tree`
            (or GIT_ATTR_SOURCE) set to this commit's persistence basis (§7.1.11), plus the empty
            core.attributesFile that (a) already provides. The mechanism is proven live in
            review/checkout.py:171-215 (M-21). Under v2 the pin is DEFENCE IN DEPTH for storage
            identity (§7.1.10) and load-bearing for §7.9's checkout claim, so this class is the
            Git persistence preflight and the capability machinery — NOT a staging command,
            because v2 runs none.

        (c) EVERY INVOCATION CONSUMING AN EXACT DECLARED PATH — GIT_LITERAL_PATHSPECS, which (a)
            already sets for all of them, called out because it is the one that silently
            mis-addresses a legal filename otherwise (M-50).

      NO IMPLEMENTATION PREREQUISITE ASKS FOR `git add`, `git commit` OR `git commit --only`.
      They are prohibited for this identity (§7.1.2) and remain the PLANNING mode's primitive,
      untouched. Git >= P3_WORK_ATTR_PIN_GIT_MIN (2.43.0) is still required for class (b), and
      the capability probe of §7.7 is the binding authority regardless of the declared floor.
      No further environment class exists: (a1) and (a2) are exhaustive over the invocations
      this operation makes.

IP-10 The line-ending configuration core.autocrlf=false and core.eol=lf is set on EVERY CLASS B
      invocation — class (a2) above — not on "both invocations". Measured, without them a CRLF result is
      normalized on check-in even with the attribute pin in place (M-23), and Git for Windows
      enables autocrlf globally by default. Under v2 no check-in conversion path is entered at
      all (O-3 passes no `--path`), so this is belt-and-braces — retained so the sequence stays
      safe if a future step ever reads a file through Git.

IP-11 The capability probe of §7.7 must exist and must run before the first pinned commit of every
      review-v1 Work operation. `rules/git` gains P3_WORK_ATTR_PIN_GIT_MIN = 2.43.0 as its
      declared floor.

IP-12 The universal source predicate of §7.8 requires a parser over every .gitattributes blob in a
      tree, at every depth, plus .git/info/attributes — not a path probe. Its supported shape is
      narrow by design and refuses any [attr] macro.

IP-17 THE OBJECT-DRIVEN PERSISTENCE PRIMITIVE of §7.1.2, which is the largest single piece of
      implementation this contract requires and the one that must not be approximated. It
      REPLACES `gitcmd.contained_add` / `contained_commit` for every commit this operation makes:
      an isolated `GIT_INDEX_FILE`, `read-tree <exact parent>`, parent agreement, `hash-object -w
      --stdin` from the PLAN's material with the returned id CHECKED against the plan's new_oid,
      `update-index --cacheinfo <mode>,<oid>,<path>` and `--force-remove` for deletions,
      `write-tree`, `commit-tree --no-gpg-sign -p <exact parent> -m <exact message>`, and a
      compare-and-swap `update-ref <ref> <new> <expected-old>`. All of it is present in Git today
      and all of it is MEASURED (M-36..M-38, M-40, M-42, M-43); none of it resolves a working-tree
      pathname.

IP-18 THE PREPARED-COMMIT OWNERSHIP CHECKPOINT (§7.1.2 O-6a / O-7a, §7.1.3, §7.10). The
      git_commit effect must carry `prepared_commit_id` with its parent, tree, ref and contract,
      saved in its own durable save BEFORE the ref advance, and `commit_id`/`applied` must be
      promoted in a SECOND save after the ref is read back. `Mutation.apply` and `_make_commit`
      (mutation.py:501, :1394) currently do one save after `apply_effect` returns, and
      `_classify_commit` (mutation.py:2259) currently returns MATCHING when the recorded paths no
      longer differ from HEAD — which, for a not-yet-owned record, is ownership by branch state
      and must become unreachable for review-v1 Work (M-41). The resume matrix §7.1.3 rows A ... G
      replaces it. RUNTIME / RECOVERY material only: no canonical Review record and no Candidate
      schema changes.

IP-19 THE GENERIC COMMIT TREE PLAN (§7.1.1): a plan builder per commit class — Candidate/witness
      for S-c1, parent blob plus recorded append_event effects for S-c0, the recorded
      immutable-create bytes for each Review generation commit, and both together for S-c2 — none
      of which may read the working-tree copy of a path the plan already describes. Includes the
      append assertion `material.startswith(parent_blob)` for the event log.

IP-20 THE CONDITIONAL REAL-INDEX REFRESH (§7.1.4): entry-compared, own-paths-only, run after
      durable C-1, non-authoritative, with the outcome recorded on the mutation. MEASURED
      feasible (M-45); the hazard of omitting it is MEASURED too (M-44).

IP-26 THE RAW COMMIT ANCESTRY READER of §7.1.8, which must NOT be built from, or quietly
      delegated to, the existing revision-view helpers. `gitcmd.commit_parents` (gitcmd.py:399)
      runs `rev-list --parents` and `gitcmd.descends_from` (gitcmd.py:412) runs
      `merge-base --is-ancestor`; both are changed by grafts and by a shallow boundary (M-57,
      M-59) and neither may back any P3 proof. The reader must provide:

          RAW_PARENTS(oid)      `GIT_NO_REPLACE_OBJECTS=1 GIT_NO_LAZY_FETCH=1 git cat-file commit
                                <oid>`, parsing the literal `parent <oid>` headers from the header
                                block that ends at the first blank line, in order. The replace
                                setting is REQUIRED here specifically: without it a replacement
                                changes the answer (M-58).
          raw_descends_from     a walk over RAW_PARENTS only
          raw_range(base, head) the RAW_PARENTS walk from head down to and excluding base
          NO interpretation of refs/replace, `.git/info/grafts` or `.git/shallow` anywhere
          LOCALLY UNAVAILABLE PARENT -> UNKNOWN, FAIL CLOSED, and never "this is a root" (M-59)
          FULL OID WIDTHS for both hashes: 40 hex for SHA-1 and 64 hex for SHA-256, matched
            exactly, with no abbreviation accepted or produced anywhere
          a frozen step budget, beyond which the answer is UNKNOWN rather than an unbounded walk

      Every lineage, range, descent and parentage question in §8.2, §9, §15, §16 and §7.1.3 is
      answered by this reader and by nothing else.

IP-25 THE HERMETIC GIT ENVIRONMENT of §7.1.9, applied to EVERY CLASS B invocation rather than
      to the commit path alone — and the GIT_* STRIP applied to class A as well, which is the
      one thing both classes share (§7.1.9, IP-8 (a1)/(a2)):
      GIT_NO_LAZY_FETCH=1, GIT_NO_REPLACE_OBJECTS=1, GIT_LITERAL_PATHSPECS=1,
      the promisor-configuration read and the grafts refusal at entry, and the author/committer
      identity captured BEFORE config neutralization but AFTER the GIT_* strip, by
      `git -C <root> config --get user.name` / `user.email` and by no other mechanism (§7.1.9
      phase A), then supplied explicitly with its dates. Without the capture an ordinary Project
      becomes uncommittable (M-51); with the capture in the wrong order a hostile inherited
      GIT_AUTHOR_* would be captured and re-injected (M-63); and with the class B neutralization
      applied to the capture itself, a global-only identity cannot be read at all (M-64).

IP-24 THE ATOMIC INDEX TRANSACTION of §7.1.4: an O_CREAT|O_EXCL `<git-dir>/index.lock`, a snapshot
      of the real index, entry-wise comparison against the plan's expected old entries, writes
      confined to permitted own paths, an atomic same-directory rename to publish, bounded
      contention retry, and R-IDX-8's cleanup checkpoint. No new durable carrier is added and no
      later operation reads the mutation record, which `Mutation.complete` / `_drop_own_record`
      takes away.

IP-23 THE GENERATION MODE DISPATCH of §7.1.7: `gitops.review_commit_effect` (gitops.py:201) sets
      PLANNING_COMMIT_MODE unconditionally, and `_finish_generation` (roadmap_review.py:1447) is
      its only caller for generations. A Work Review Run's generation commit must instead name
      "review-v1-work-local-v2" and use the object-driven primitive, discriminated by the
      `review_kind` already present in the generation mutation's durable invocation
      (roadmap_review.py:1422). Planning Runs are untouched.

IP-22 THE PARENT-OBJECT-SOURCED RENDERING of §7.1.1 — the generic plan builder. It applies the
      SAME rules as `mutation.planned_write` (mutation.py:1740) but sources them from the parent
      blob and the recorded payloads instead of `store.read_relation_file` /
      `store.events_text` (M-56), chains them in recorded order, and checks the result against
      the digest the mutation durably recorded. It must cover every effect kind a Work cycle's
      pre-completion stages can record, not only the Review's own.

IP-21 TWO HANDLE-BOUND READERS `fsafe` does not expose yet, both built from primitives it already
      uses:
        a NO-FOLLOW FINAL-OBJECT IDENTITY query — `fstatat(..., AT_SYMLINK_NOFOLLOW)` on POSIX,
          the existing `NtCreateFile(RootDirectory=..., FILE_OPEN_REPARSE_POINT)` +
          `GetFileInformationByHandle` on Windows — which IDENTIFIES a symlink or reparse point
          instead of refusing it, so a valid F2 mode-120000 result is not lost (M-47);
        a HANDLE-BOUND SUBMODULE HEAD READER implementing §7.8.4's G-1 ... G-5 from
          `SafeDirectory.child` / `.read_file`, which M-46 measured end to end.

      ALSO REQUIRED WITH IT:
        the pre-stage containment re-proof of §7.8.4 — immediately before S-c1 stages, the
          ancestor chain of every path to be staged is re-proven by the layer-3 walk including
          the object-identity check. It is retained even though the primitive no longer depends
          on it, because it turns a tampered working tree into an early refusal rather than a
          late one;
        the empty-delta assertion of §7.1.2, which is now a RULE rather than a consequence of
          `git commit --only` declining an empty delta, and which carries no new reason value
          because §6.7's discriminator is what prevents the case;
        a required regression test over §21.12's matrix asserting that the committed tree entry
          equals the witnessed identity WITH AN ANCESTOR INDIRECTION ACTIVE. The earlier draft
          pinned Git's `git add` containment behaviour instead, which was platform-dependent
          (POSIX refuses per the re-review's measurement, Windows does not per M-34); nothing
          relies on that behaviour any more, and the test now pins the property the contract
          actually claims.

IP-16 THE PER-KIND WITNESS NEEDS A RUNTIME FORM `_content_digest` CANNOT EXPRESS, and this is
      measured rather than assumed. A gitlink digests to `None` and is stored as `"unreadable"`,
      so the currentness guard compares `None != "unreadable"` and refuses a changed gitlink
      outright (M-32); and the mode is absent from every form, so a chmod is invisible (M-33).
      `_OWN_CONTENT` must therefore hold a per-kind witness — path, kind, git_mode, identity and
      material where the kind has material — and the currentness comparison must compare the
      whole witness rather than one digest string. RUNTIME / RECOVERY material only: no canonical
      Review record and no Candidate schema changes.

IP-15 THE BOUND OWNERSHIP WITNESS of §7.8.4 cannot be built from the live helpers as they
      stand, and this is named rather than papered over. `declare_own_content` takes path
      STRINGS and calls `_content_digest(mutation.store.abs(path))`, which re-resolves
      `root / relative` (M-28, M-30) — a second root-relative resolution, which is exactly what
      the witness exists to avoid. The implementation needs a capture that walks the ancestors
      no-follow, HOLDS the handle chain, reads or stats or readlinks the final entry RELATIVE to
      the proven parent, and hands the ownership assertion the already-captured state instead of
      a path to resolve again.

      IP-15 IS THE CAPTURE. IP-16 IS THE FORM IT IS CAPTURED INTO, and the two must land
      together. An earlier draft of this prerequisite claimed "no recorded form changes and no
      downstream reader changes; only where the value comes from does". THAT CLAIM WAS FALSE and
      is withdrawn: `_content_digest`'s four forms carry no mode and cannot express a gitlink's
      referenced commit (M-32, M-33), so capturing the same four strings from a bound handle
      would faithfully record a witness that still cannot detect a chmod or a changed gitlink.
      The recorded form DOES change, to the per-kind witness of IP-16, and the currentness
      comparison that reads it changes with it.

      SPLIT OF RESPONSIBILITY, so neither is mistaken for the other:
          IP-15  WHERE the value comes from — a handle-bound capture, no second root-relative
                 resolution, the final component never reopened by pathname
          IP-16  WHAT is recorded and compared — path, kind, git_mode, identity, and material
                 where the kind has material
      Neither alone is sufficient: IP-15 without IP-16 records an expressively inadequate
      witness; IP-16 without IP-15 records an adequate witness of a possibly re-resolved object.

IP-14 The reserved-ownership boundary of A-5 AND A-6 — ONE predicate over TWO reserved sets,
      `.workline/review` with its descendants and `.workline/events/events.jsonl` — needs three
      things: the pre-execution binding in the review-v1 invocation contract (PR-8), a
      post-Completed validation of every declared result and deletion path WHICH MUST RUN BEFORE
      declare_own_content (§5.1 steps 5b, 5c and 5d, because that call durably records
      ownership), implemented as §7.8.4's three layers — `_safe_relative` for spelling; then the
      reserved classification, which is the ASCII-only fold as a PRE-FILTER plus its own
      no-follow walk taking FILESYSTEM OBJECT IDENTITY as the authority, over the ancestors and
      over the declared path's final component opened no-follow (sub-steps 2a-2e), never
      dereferencing that component; then the `fsafe`-style containment walk and witness capture —
      with a malformed identity routed to `review_candidate_unavailable` and either reserved set
      to the new reason value `review_reserved_namespace` registered in the reason catalogue
      alongside the review-v1 planning reasons, carried through ReconcileRequired. It is the only
      new reason F3 introduces, it covers both namespaces because they reconcile identically, and
      it needs no new exception class.

      NOT WIDENED: A-6 reserves exactly one path. `.workline/events/` is not reserved as a
      directory and `.workline/events/other.txt` remains a lawful declaration, because reserving
      the directory would refuse an input that is valid today.

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
object-writing, tree-writing and commit-writing plumbing             git hash-object / write-tree
                                                                     / commit-tree, all present
compare-and-swap ref update                                          git update-ref <new> <old>
base-exact commits, with HEAD re-read immediately before the commit  _make_planning_commit
    (the TECHNIQUE F3 replaces with O-2/O-7's compare-and-swap; listed because the live code
     shows base-exactness is already an accepted requirement, not because F3 reuses the mechanism)
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

FC-10  The attribute source of every commit this operation makes is pinned (§7.1.11), so
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
   disposition      resume at the earliest unsatisfied checkpoint (§5.4) and RE-EXECUTE the
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
    handling     the primitive sets core.autocrlf=false and core.eol=lf on every class B invocation
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
    consequence  generation 2 remains the latest generation and stays `open`; NO generation-3
                 record is written; no Receipt, no authorization, no Consumption, no K1 and
                 nothing published. The failure is an operation STOP only — there is NO
                 canonical reason record, because GateGeneration has no field that could hold
                 one (M-27).
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
              exist. The circularity the re-review found is resolved in §7.1.11.

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
   order      the Candidate is frozen first, so the resulting tree and its object id are known;
              then the Context's TARGET-ONLY record is built from them
   verdicts   NONE. No resulting-tree verdict is required, computed or stored at Context build
              time — the Context carries a target, never a verdict (§7.9.6). The earlier
              "both verdicts are proven then" is obsolete and withdrawn.
   base       the base capability is ALREADY an entry precondition (§7.4, §7.8), decided before
              any mutation exists, so nothing about it is decided here either
   resulting  the resulting-tree verdict is derived at SEAL ONLY, at §5.1 step 15a
   durability the Context is NOT durable before generation 1; generation 1 is its first canonical
              durable binding, and a crash before it recomputes rather than resumes (§5.3)
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
   when         §5.1 step 5c, after path identity at 5b and before declare_own_content
   refusal      ReconcileRequired(reason = "review_reserved_namespace")
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

### 21.8 End-to-end propagation trace

Each row is traced through the **frozen sequence of §5.1 as repaired**, so that the sequence, the
authority plan and the matrices cannot drift apart again.

```text
A. SAFE CANDIDATE, CAPABILITY CAPABLE
   §5.1  10 Candidate frozen -> 11 material -> 11a resulting tree id -> 11b Context v2 built
         -> 12 isolated verification under that Context -> 13 gen 1 accept + TaskInput
         -> 14 reviewer -> 15 gen 2 settle
         -> 15a capability derived for Context.resulting_tree = CAPABLE
         -> 16 gen 3 seal + Receipt
         -> 17 lineage -> 17a Consumption id -> 17b preflight -> 18 S-c1 -> K1
         -> terminal stage -> S-c2 -> K2 -> recorded completion (§19)
   result  ordinary authorization and the ordinary K1/K2 topology

B. UNSAFE RESULTING TREE
   §5.1  identical through step 15. The Context at 11b IS BUILT AND VALID — it binds the proof
         target and carries no verdict (§7.9.6, TM-11) — so generation 1 exists, the TaskInput
         binds review_context_hash, and the external Review occurs normally.
   note  no verdict is computed at 11b in this case either; `unsafe` is first known at 15a.
   15a   capability derived for Context.resulting_tree = UNSAFE
   then  NO step 16: no generation-3 record, no Receipt, no authorization, no Consumption,
         no K1, nothing published. Generation 2 remains latest and `open`. Operation STOP
         (review_checkout_unsafe) with NO canonical reason record (§7.9.5, M-27).
   result  EXPRESSIBLE + REVIEWED + NOT AUTHORIZED, which is invariant 26

C. UNKNOWN CAPABILITY
   identical to B in every step, with review_checkout_unknown. Unknown is never read as capable
   and never as an invalid Candidate.

D. S-c0
   §5.1  step 9a, pinned to PRE_S_C0_BASE — the committed HEAD immediately before it, which
         exists (§7.1.11). It commits the event log ALONE, which is what makes the two bases one
         attribute state. Activated as PB-9.

E. EVERY LATER COMMIT
   the generation commits of 13 / 15 / 16, every pre-completion Work commit, S-c1 at 18 and
   S-c2: all pinned to declared_base.base_commit, with core.autocrlf / core.eol neutralized and
   the per-commit preflight under that same pin (§7.3, PB-3, PB-9).

F. RESULT PATH INSIDE .workline/review/**   (A-5)
   bound   before the executor ran, by the review-v1 invocation contract (PR-8)
   at 5c   the reserved-ownership classification refuses BEFORE declare_own_content and BEFORE
           the containment walk of 5d: no _OWN_CONTENT note, no completion_precheck, no
           dirty-separability check, no Candidate projection, no Review. "Inside" is decided by
           §7.8.4's layer 2 — the ASCII fold as a pre-filter, filesystem OBJECT IDENTITY as the
           authority — never by a string prefix
   refusal ReconcileRequired(reason="review_reserved_namespace") — unowned state, which F2 §2.3
           permits refusing, and refusing as a reconcile is what §2.3 says it is
   not     an unsupported Git result shape; not review_candidate_unavailable; never legacy.
           In particular the Review ROOT, which is a directory, is refused HERE and is never
           downgraded to malformed by 5d, because 5d never runs on it
   same    for a DELETION path inside the namespace

F2. DECLARED PATH IS .workline/events/events.jsonl   (A-6)
   bound   the same way and at the same moment, by PR-8
   at 5c   classified reserved by the same predicate and the same two tests; where the canonical
           file exists — and it does, from the moment the mutation is opened — an alias reaching
           it is caught by the final-component object-identity comparison, so A-6 is alias-safe
           physically and not merely lexically (§7.8.4 sub-step 2d)
   refusal the SAME reason value: the condition is the same one, a declaration over state this
           operation was never permitted to own, and both reconcile identically
   same    for a DELETION of that path
   why     this is what makes PRE_S_C0_BASE and declared_base.base_commit interchangeable at
           every declarable path, which every deletion witness depends on (§7.8.5)
   not     widened: `.workline/events/other.txt` is NOT reserved and remains lawful

G. ORDINARY .gitattributes RESULT
   storage       proceeds under the pin; the committed object equals Candidate.new_oid (M-20)
   Candidate     expressible; reviewed as an ordinary file entry
   11a/11b       the resulting tree it produces is what the Context binds
   15a           capability decides: capable -> A; unsafe/unknown -> B
   completion    only via A, and then only through the ordinary K1/K2/recorded-completion
                 topology. It is NOT the case that every such Work completes (§7.4.4).
```

### 21.9 Ownership-ordering and Context-recovery trace

```text
A. ORDINARY RESULT OUTSIDE BOTH RESERVED NAMESPACES
   5 Completed -> 5a normalize -> 5b spelling PASSES -> 5c reserved classification PASSES
   (neither A-5's namespace nor A-6's path) -> 5d containment PASSES and the witness is captured
   -> 6 declare_own_content persists that witness -> 7 completion_precheck -> ... -> 10 Candidate
   result  ordinary supported result; the Candidate is built FROM THE WITNESS

B. RESULT PATH INSIDE .workline/review/**, OR THE EVENT LOG
   5 Completed -> 5a normalize -> 5b spelling PASSES -> 5c reserved classification FAILS
   refusal ReconcileRequired(reason = "review_reserved_namespace")
   NOT run  5d's containment walk, declare_own_content, the _OWN_CONTENT note,
            completion_precheck, dirty-separability, Candidate projection, any Review
   why      declare_own_content writes the note through set_note -> _save(), a DURABLE ownership
            assertion. Refusing after it would durably claim ownership of a path that may never
            be owned, and only then reject it.
   legacy   never. The pending review-v1 mutation does not downgrade (§7.4).

C. DELETION PATH INSIDE EITHER RESERVED NAMESPACE
   identical to B. The ownership rule names result paths and deletion paths alike, and it names
   both reserved sets alike.

D. ALL-INERT ORDINARY RESULT
   5b, 5c and 5d run IN FULL — declared paths exist, they are simply inert — and all pass.
   -> 6 declare_own_content -> ... -> all-inert Candidate, artifact_kind "empty", NO K1 (§6.7)

E. NO DECLARED PATH
   5b, 5c and 5d are VACUOUS: there is no declared path to inspect. No declare_own_content either
   (start.py:880). -> empty Candidate, NO K1.

F. CRASH AFTER CONTEXT BUILD, BEFORE GENERATION 1, AUTHORITY FILES UNCHANGED
   the Context had NO durable carrier, so it is lost. The resume re-establishes the Candidate and
   base facts, recomputes the CURRENT Context, reruns isolated verification, and generation 1
   binds that Context. The recomputed review_context_hash may happen to equal the lost one —
   but SAMENESS IS NOT AN INVARIANT and nothing depends on it (§5.3).

G. SAME CRASH, BUT loader_identity OR AUTHORITY FILES CHANGED
   the recomputed hash DIFFERS, legitimately: those two fields are content identities of the
   configured root's CURRENT working tree, and the implementation-identity check proves only that
   the running package comes from that root — not that the root is committed, clean or pinned.
   No prior durable Context is claimed, because none existed. This is the FIRST binding, taken
   from current authority — not reuse, not retarget.

H. CRASH AFTER GENERATION 1
   the exact Context BYTES are recovered from `TaskInput.request_envelope.context` (F2 §12.3,
   M-2), and `review_context_hash` verifies them. The resume READS that Context; it never
   recomputes it and never reconstructs it from the hash, and it NEVER retargets to a newly
   recomputed Context. Authority that differs now is ordinary current-validity drift under
   F2 §16.1 — an invalidation question, not a licence to rebuild.
```

### 21.10 Declared-path identity matrix

Every row is a declared result or deletion path, judged by §7.8.4's three layers at §5.1 steps 5b,
5c and 5d — all of them before `declare_own_content`. Outcomes are exactly four: **accepted**,
`review_reserved_namespace`,
**malformed** (`review_candidate_unavailable`), or **containment unknown** (fail closed, which is reported
as malformed because no identity was established).

```text
DECLARATION                                     LAYER   OUTCOME

"./.workline/review/gates/x.yaml"               1       MALFORMED -> review_candidate_unavailable
   the "." component fails _safe_relative. Note that the naive prefix test would have said
   "not Review" while `root / relative` reaches the Review namespace (M-28) — which is exactly
   why layer 1 runs first and why the path is refused rather than rewritten to a canonical form.

".workline/runtime/../review/gates/x.yaml"      1       MALFORMED -> review_candidate_unavailable
   the ".." component fails _safe_relative, for the same reason and with the same consequence.
   F3 does not normalize it into ".workline/review/gates/x.yaml" and then refuse that; silently
   replacing one declared result identity with another after the executor returned is prohibited.

".workline/review"  (the Review ROOT itself)    2       review_reserved_namespace
   reserved. The component sequence is exactly [".workline", "review"], which the component-wise
   test covers — a "starts with .workline/review/" prefix test would have MISSED it.

".workline/reviewX/notes.md"                    2       ACCEPTED
   not reserved: the second component is "reviewX", not "review". Component-wise comparison is
   what makes this correct, where a string-prefix test on ".workline/review" would wrongly
   refuse it.

".WORKLINE/Review/gates/x.yaml"                 2       review_reserved_namespace
   an ASCII case alias, caught by the fold on EVERY PLATFORM deliberately: a rule that depended
   on the running filesystem would make one declaration lawful on one machine and not another.
   MEASURED here: ".WORKLINE" and ".Workline" DO reach the canonical object on this NTFS volume,
   so the alias is real. The fold is the PRE-FILTER; the authority is object identity (2c/2d),
   which answers the same way without having to predict the volume's upcase table.

".workline/events/events.jsonl"                 2       review_reserved_namespace
   reserved by A-6. Result path and deletion path alike, and the SAME reason value as A-5's
   case, because both are declarations over state reserved before the executor ran.

any spelling that REACHES the canonical
.workline/events/events.jsonl object            2       review_reserved_namespace
   caught at sub-step 2d: the declared path's final component is opened with no-follow semantics
   and its identity compared to the canonical event log's. This is what makes A-6 alias-safe
   PHYSICALLY — the object reached is the object compared — rather than only lexically. The
   canonical file exists from the moment the mutation is opened, so there is always an object to
   compare against.

".workline/events/other.txt"                    2       ACCEPTED
   NOT reserved. A-6's set is exactly one path, and reserving the directory would refuse a
   declaration that is lawful today.

"src/app/main.py"   (ordinary canonical path)   1,2,3   ACCEPTED
   canonical spelling, not reserved, ancestors proven plain in-Project directories. Ordinary
   supported result; proceeds to declare_own_content.

"build/out.so" where "build" IS A SYMLINK       3       CONTAINMENT FAIL -> fail closed,
   (ancestor indirection, whatever it targets)          review_candidate_unavailable
   an EXISTING ancestor that is a symlink, junction or other reparse point is refused, for a
   result and for a deletion alike. This is the case a lexical test cannot see, and the reason
   layer 3 exists: an innocent-looking path must not be able to make the ownership snapshot read
   a canonical Review object through a redirected ancestor.

"tmp/old.txt" DELETED, and "tmp/" is now gone   3       ACCEPTED (positive absence)
   an ordinary correct F2 deletion. The missing ancestor PROVES the path is absent, and
   completion_precheck requires only that a deleted path be absent and tracked (M-30). Refusing
   it would be a post-executor refusal of an ordinary correct outcome, which F2 §2.3 forbids.

"assets/link" where "link" ITSELF is a symlink  3       ACCEPTED
   the FINAL component is NEVER dereferenced. F2 supports a symlink as a result object and this
   layer must not break that: what layer 3 proves is the chain that leads to the name, not what
   the name resolves to.

any path whose ancestor identity cannot be
established at all                              3       CONTAINMENT UNKNOWN -> fail closed
   not knowing is not a yes. It is refused before any ownership is asserted.
```

```text
In every refusing row, the refusal happens BEFORE declare_own_content, so no _OWN_CONTENT note is
written for the declaration, and §5.4's refusal state applies: the mutation stays pending with its
markers unchanged, and the executor's working-tree state is left untouched for reconciliation.
```

### 21.11 Bound ownership witness matrix

Every row runs at §5.1 step 5d, before ownership is asserted at step 6. "Witness" is the bound ownership
witness of §7.8.4: captured relative to the proven parent handle, never by re-resolving
`root / declared_path`.

```text
A. RESULT FILE, ALL PARENTS PLAIN
   walk      every ancestor exists and is proven a plain in-Project directory
   witness   the final entry stat'd and read RELATIVE to the proven parent, into the PER-KIND
             witness of IP-16 — path, kind "file", git_mode 100644 or 100755, the raw blob id
             and the exact bytes. NOT the existing `_BYTES` digest string, which carries no
             mode (M-33); the earlier draft's "same recorded forms" claim is withdrawn.
   outcome   ACCEPTED -> step 6 persists the witness, no pathname re-resolution, and §7.1.2 O-3
             later hashes THESE bytes rather than rereading the path

B. RESULT FINAL COMPONENT IS A SYMLINK, PARENTS PLAIN
   witness   the link target's bytes, read with no-follow semantics relative to the proven
             parent; kind "symlink", git_mode 120000, the blob id of those bytes and the bytes
             themselves. THE LINK IS NEVER FOLLOWED.
   outcome   ACCEPTED. F2 §6.4's symlink result object keeps its semantics exactly. The
             executable bit is carried in the witness's git_mode, and a gitlink's referenced
             commit OID comes from its own frozen handle-bound source — G-1..G-5 of §7.8.4,
             measured end to end with no Git process at all (M-46) — so neither is dropped.

C. RESULT PATH WITH A SYMLINK ANCESTOR
   walk      an existing ancestor is a symlink / junction / reparse point
   outcome   FAIL CLOSED before ownership assertion -> review_candidate_unavailable.
             No witness, no _OWN_CONTENT note, no Candidate.

D. DELETION, PARENT EXISTS, FINAL PATH ABSENT
   walk      ancestors proven plain; the final name is absent relative to the proven parent
   witness   declared canonical path + kind "absent" + git_mode 000000 + the tracked identity
             in PRE_S_C0_BASE (§7.8.5, which A-6 makes interchangeable with declared_base at
             every declarable path) + the positive absence
   outcome   ACCEPTED -> step 6 persists that witness; §7.1.2 O-4 later issues
             `update-index --force-remove <path>`, which resolves nothing on the filesystem

E. DELETION, IMMEDIATE PARENT ABSENT
   walk      the parent component does not exist
   witness   the missing parent POSITIVELY proves the declared path is absent — a path cannot
             exist beneath a component that does not exist
   outcome   ACCEPTED, exactly as D. NOT "containment unknown", NOT malformed.
   no-trap   this is the ordinary shape of a deletion that removed the last file in a directory
             and let the directory go. F2 supports `new_kind = "absent"` for every object kind
             and requires nothing of the parent; live completion_precheck requires only absence
             and tracked-ness (M-30). Refusing it would be a post-executor refusal of an
             ordinary correct outcome, which F2 §2.3 forbids — so the previous draft's blanket
             "missing ancestor -> fail closed" is withdrawn.

F. DELETION, A HIGHER ANCESTOR ABSENT
   identical to E at whatever depth the walk first finds a missing component. The proof does not
   care which level it is: the first missing component ends the walk and proves the absence.

G. DELETION, AN EXISTING ANCESTOR IS A SYMLINK / JUNCTION
   outcome   FAIL CLOSED. Absence "below" an indirection proves nothing about the declared path,
             because the name could denote an object elsewhere. Missing is a proof; redirected
             is not.

H. AN ANCESTOR IS SWAPPED AFTER VALIDATION BUT BEFORE THE OWNERSHIP SNAPSHOT
   outcome   THE SNAPSHOT CANNOT BE REDIRECTED, because there is no pathname reopen to redirect.
             The capture is performed relative to the handle chain already proven, so a component
             replaced by name afterwards is not consulted again (fsafe, M-29). This is the race
             the previous draft left open by handing step 6 a path string.
   POSIX     sound for this operation: fsafe's pinning caveat is about where a CREATE lands, and
             this creates nothing; `openat(parent_fd, ..., O_NOFOLLOW)` relative to the proven fd
             is listed as the supported read form (M-31).

I. EXTERNAL CHANGE AFTER THE OWNERSHIP SNAPSHOT
   outcome   the snapshot is NOT redefined retroactively, and the change cannot reach the commit
             at all. The full-witness currentness comparison detects the drift and refuses; and
             independently of that refusal, §7.1.2 commits the WITNESSED bytes and identities, so
             even an undetected change to the working tree is not what gets committed (M-36).
             The earlier draft's formulation — "the Git stage commits the owned paths only while
             they still hold exactly what was recorded" — described a pathname-resolving stage
             that no longer exists.

J. A GITLINK RESULT, SUBMODULE HEAD MOVED BY THE EXECUTOR
   witness   kind "gitlink", git_mode 160000, identity read by §7.8.4's handle-bound chain
             G-1..G-5 — the submodule handle from the proven chain, its `.git` gitfile, the
             gitdir resolved component-wise against handles already held, then HEAD and its ref
             (M-46). No `git -C`, no pathname re-resolution, no material
   outcome   ACCEPTED. Measured today this is REFUSED by the live own-content guard, because a
             gitlink digests to `None` against a stored `"unreadable"` (M-32) — that defect is
             IP-16's, and this row holds only once IP-16 lands, which is stated rather than
             assumed.
```

### 21.12 End-to-end artifact identity matrix

For every SUPPORTED ordinary result the chain proven is

    witness == Candidate == CandidateSnapshot material == pre-stage current identity
            == staged identity == K1 identity

and for every RESERVED case the refusal precedes any ownership assertion.

```text
A. REGULAR 100644 RESULT
   witness   kind file, git_mode 100644, exact bytes + blob id, captured on the proven parent
   Candidate new_kind/new_mode/new_oid/content_sha256 taken FROM THE WITNESS (§7.8.4), not a
             reread; snapshot payload is the witnessed bytes
   pre-stage full-witness currentness: kind, mode and identity all compared
   staged    the same blob; C-2(K1) W4/W5 confirm it against the Candidate
   chain     HOLDS

B. EXECUTABLE 100755 RESULT
   as A, and git_mode 100755 is IN the witness. Measured gap it closes: the current
   `_content_digest` form carries no mode at all (M-33), so without IP-16 a chmod between
   witness and staging is invisible. With it, the pre-stage comparison catches it.
   chain     HOLDS

C. FINAL SYMLINK 120000 RESULT
   witness   link-target bytes read with no-follow semantics, NEVER followed; blob id of those
             bytes; git_mode 120000
   snapshot  the same target bytes (F2 §9.4.1)
   chain     HOLDS. The final component is never dereferenced at any step.

D. GITLINK 160000 CHANGED TO ANOTHER COMMIT
   measured  today this is REFUSED by the own-content guard: digest None vs stored "unreadable"
             (M-32). That is the defect IP-16 fixes.
   witness   kind gitlink, git_mode 160000, identity = the exact referenced commit OID obtained
             by §7.8.4's HANDLE-BOUND chain G-1...G-5 — the submodule handle from the proven
             chain, its `.git` gitfile, the gitdir resolved component-wise against handles
             already held, then HEAD and its ref (M-46). NO material.
             NOT "the tree entry": neither the superproject's OLD index entry nor its parent
             tree entry is the executor-return new_oid — both still hold the pre-executor commit
             until something stages the change. That earlier wording was ambiguous between the
             two and is replaced.
   Candidate new_oid IS that commit OID (F2 §6.3/§6.4); no snapshot payload (F2 §9.4.1)
   pre-stage compares the referenced OID, which the digest string could not express
   chain     HOLDS once IP-16 lands; NOT before, and that is stated rather than assumed.

E. DELETION, PARENT PRESENT        witness: base identity in PRE_S_C0_BASE + positive absence
F. DELETION, PARENT ABSENT         the missing ancestor PROVES absence; accepted (§7.8.4)
   both      Candidate new_kind "absent", no payload; chain HOLDS

G. REVIEW ROOT `.workline/review` DECLARED AS A RESULT
   step 2    classified RESERVED and refused there:
             ReconcileRequired(reason = "review_reserved_namespace")
   NOT       downgraded to review_candidate_unavailable because its final object is a directory —
             the filesystem layer never runs on it (§7.8.6 precedence)

H. REVIEW DESCENDANT DECLARED AS A RESULT          as G
I. `.workline/events/events.jsonl` AS A RESULT     as G, by A-6 (§7.8.5)
J. `.workline/events/events.jsonl` AS A DELETION   as G, by A-6; result and deletion alike

K. `.WORKLINE/Review/...`
   lexical   caught by the ASCII fold
   physical  and independently by object identity, where the canonical directory exists
   MEASURED  `.WORKLINE` and `.Workline` DO resolve to the canonical object on this NTFS volume
   outcome   review_reserved_namespace

L. `.workl\u0131ne/review/...`   (U+0131 DOTLESS I)
   MEASURED  a DISTINCT object on this volume — mkdir succeeded, read raised FileNotFound
   outcome   NOT reserved here, and accepted if it is otherwise valid. The point of the
             object-identity test is that this answer comes from the FILESYSTEM rather than from
             a guessed case table: on a volume whose upcase table maps it, the same test would
             classify it reserved without any contract change.

M. ANCESTOR SWAPPED AFTER THE WITNESS BUT BEFORE THE CANDIDATE
   the Candidate is built FROM THE WITNESS (§7.8.4), so the swap cannot become what Review
   judges. F2 ST-1's "at the moment the executor returns" is what the witness captures.

N. ANCESTOR SWAPPED AFTER REVIEW BUT BEFORE THE STAGE IS RECORDED
   the pre-stage containment re-proof and the full-witness currentness check run there and
   refuse; and C-2(K1) would refuse afterwards regardless.

O. ANCESTOR SWAPPED BETWEEN THE CURRENTNESS CHECK AND THE COMMIT   (the central case)
   was      answered by the earlier draft with "C-2(K1) catches it after the wrong commit".
            THAT ANSWER IS WITHDRAWN. It proves publication safety and not the frozen chain: if
            a redirected object can reach the committed tree at all, WITNESS == ... == K1 is
            broken at its fourth link, and a later refusal reports that rather than preventing
            it.
   now      the commit is built by §7.1.2's object-driven sequence, which resolves NO
            working-tree pathname between the identity proof and the committed tree. The bytes
            come from the witness; `hash-object -w --stdin` turns them into an object; the id is
            CHECKED against Candidate.new_oid; `update-index --cacheinfo` places that id under
            the path STRING without touching the filesystem.
   MEASURED  M-36, with the junction ACTIVE THROUGHOUT: the committed entry was the witnessed
            blob `924c75cd`; the junction target's blob `b2f3ae2a` appeared NOWHERE in the
            commit. Git's own `git add` containment behaviour — refusing on POSIX (the
            re-review's measurement), not refusing on Windows (M-34) — is now IRRELEVANT to the
            outcome, and the result is therefore the same on every platform.
   outcome   THE RACE CANNOT CHANGE THE COMMITTED TREE. The pre-stage currentness read may still
            see the redirected content and refuse there (review_candidate_unavailable) — a
            refusal, never a wrong commit. C-2(K1) remains as an independent backstop, and is no
            longer what the property rests on.

P. THE SAME SWAP, CONTENT IDENTICAL
   the earlier draft conceded this as a residual: "the same artifact, so the invariant is not
   violated". No concession is needed now. The bytes committed are the witnessed bytes whether or
   not the redirected ones happen to match, so identity of content is not part of the argument.

Q. EXTERNAL chmod AFTER CANDIDATE FREEZE
   caught by the full-witness currentness comparison (mode is in the witness, IP-16), and it
   cannot reach the commit regardless: O-4 places `--cacheinfo <new_mode>,...` from the frozen
   Candidate, so the filesystem's mode at commit time is never consulted. C-2(K1) W4/W5 compare
   new_mode against the committed tree entry as a third, independent check.

R. GITLINK CHANGES AFTER CANDIDATE FREEZE
   caught the same way, by comparing the referenced commit OID (source frozen at §7.8.4: the
   submodule repository's HEAD, M-39) rather than a byte digest — which M-32 shows the current
   digest form cannot do at all. It likewise cannot reach the commit: O-4 places the frozen OID.

S. THE BRANCH MOVES BETWEEN THE STAGE RECORD AND THE COMMIT
   MEASURED  M-38: `git update-ref <ref> <new> <expected-old>` with a wrong expected-old is
            refused — "is at <actual> but expected <given>" — and the ref is left unchanged.
   outcome   O-2 seeds from the exact recorded parent and O-7 advances the branch only under
            compare-and-swap against that same id, so a concurrent advance can neither be
            overwritten nor silently accepted. STOP, surfaced as ReconcileRequired with the
            EXISTING reason review_registration_base_moved. This replaces the live
            re-read-HEAD-twice technique (M-7), which leaves a window between the second read and
            the ref update.

T. CANONICAL FORM-L BASE SOURCE
   permitted and REQUIRED in the reserved surface (§7.1.9 two-surface rule, §7.9.3), while the
   ordinary surface admits no material assignment. A base carrying form-L is not refused at
   entry; one carrying a material rule over ordinary paths is. Under the object-driven primitive
   neither assignment can alter a committed object — the pin is defence in depth for storage
   (§7.1.10) — but the entry predicate still binds, because it is also what §7.9's
   checkout-capability claim rests on.
```

```text
WHAT THE MATRIX DOES NOT CLAIM. Every "impossible" above is impossible for the COMMITTED TREE,
which is what the frozen chain is about. It is not a claim that the working tree cannot be
tampered with, that a currentness read cannot see foreign content, or that an executor cannot
leave the Project in a state this operation then refuses. Those are refusals, and they are
supposed to happen.
```

### 21.13 Persistence integration matrix — ownership, recovery, index and commit classes

Every row is decided from the operation's OWN durable record. No row recovers ownership from the
branch tip or from "the paths no longer differ from HEAD". Measured: M-41 ... M-47.

```text
A. CRASH BEFORE prepared_commit_id IS SAVED
   state     objects may exist in the ODB; no ref moved; nothing durable claims them
   answer    §7.1.3 row A. Rebuild the plan and run O-1...O-7a from the start. The earlier
             objects are unreachable and unowned (§7.1.6): not searched for, not adopted, not
             evidence, and `git gc` may remove them whenever it likes.

B. CRASH AFTER prepared_commit_id IS SAVED, BEFORE THE CAS
   state     ref == plan.parent; a durable id names an object this operation made
   answer    §7.1.3 row B. Re-verify THAT object exactly — exists, is a commit, tree ==
             prepared_tree, parent == prepared_parent, message == plan.message — then retry the
             CAS OF THAT ID. MEASURED to succeed (M-42). Never rebuild, never adopt another
             commit, and never reconstruct-and-compare.

C. CRASH IMMEDIATELY AFTER THE CAS, BEFORE THE C-1 SAVE
   state     ref == prepared_commit_id; commit_id/applied not yet written
   answer    §7.1.3 row C. C-1 is recovered POSITIVELY: the id was written down BEFORE the ref
             moved, and the ref is only asked whether it holds THAT id. Not branch-tip inference.
   WITHOUT   the prepared checkpoint this is exactly the P1 R5 §3.1/§3.5 violation: live
             `_classify_commit` would find the paths no longer differ from HEAD and return
             MATCHING with no owned id (M-41).

D. CAS REFUSED BECAUSE THE BRANCH MOVED
   MEASURED  "cannot lock ref ...: is at <actual> but expected <given>", ref unchanged (M-38)
   answer    §7.1.3 row D. STOP, reason review_registration_base_moved. The prepared commit is
             never retargeted onto the new tip, never rebuilt against it, never published.

E. PREPARED ID DURABLE, THE OBJECT IS MISSING OR UNREADABLE
   answer    §7.1.3 row E. FAIL CLOSED. `cat-file -e` answering negatively is not permission to
             rebuild: this operation recorded that it made a specific object, and a repository
             that no longer has it is a state a person reconciles.

F. ON RESUME THE REF ALREADY EQUALS THE PREPARED ID
   answer    row C. This is the ordinary crash-after-CAS recovery and is decided in one
             comparison against the operation's own record.

F2. THE REF IS A DESCENDANT OF THE PREPARED ID
   MEASURED  the descendant relation is detectable and distinct from ref == prepared (M-43,
             measured with `merge-base --is-ancestor`). The FROZEN predicate is
             `raw_descends_from` (§7.1.8), because the walker's answer is changed by grafts and
             by a shallow boundary (M-57, M-59) while the raw walk's is not.
   answer    §7.1.3 row F. The OBJECT's ownership is still known, but the stage's conditions do
             not hold — base-exactness, L-3 and W3 all fail — so reconcile. The later branch
             state is NEVER silently treated as this stage's result.

G. A PERSON CHANGES ONLY THE REAL INDEX DURING THE REVIEW WAIT
   state     working tree = the witnessed bytes; real index = the person's staged bytes
   witness   full-witness currentness is an ARTIFACT/worktree witness, so it still PASSES —
             stated plainly rather than hidden
   K1        commits the WITNESSED bytes, correctly, because the plan carries them
   index     §7.1.4 R-IDX-4 reads the current entry, sees it is NOT the entry the plan expected,
             and LEAVES IT EXACTLY AS IT IS. MEASURED (M-45): a foreign `b2f3ae2a` staged on our
             own path was detected and not overwritten. Owning a path is not owning a person's
             staging intent.

H. UNRELATED STAGED ENTRIES EXIST
   MEASURED  the person's `b/g.txt` entry survived the refresh BYTE-IDENTICAL (M-45), because
             R-IDX-3 touches only this commit's own plan paths and O-1...O-8 never read or write
             the real index at all.

I. THE REAL-INDEX REFRESH FAILS AFTER C-1
   answer    §7.1.3 row G. C-1 STANDS. R-IDX-2 makes the refresh non-authoritative: its success
             is not a precondition of C-1, C-2, the proof note, publication or completion, and
             its failure is recorded on the mutation.

J. A CRASH DURING THE REFRESH
   answer    as I. The refresh runs AFTER O-7a, so there is no window in which it can cost the
             operation a commit that is already on the branch — which is exactly the defect the
             earlier draft's O-8 had (§7.1.4).

K. S-c0, OBJECT-DRIVEN
   plan      parent tree's event-log blob ++ the canonical serialization of THIS MUTATION'S
             already-recorded append_event effects, in recorded order (§7.1.1)
   proof     no working-tree reread: the mutable event log is a file anything may have appended
             to, and reading it would make S-c0 commit whatever is there rather than what this
             mutation recorded. The plan also asserts material.startswith(parent_blob).
   entries   exactly one, `.workline/events/events.jsonl` — which is why A-6 reserves it

L. A REVIEW GENERATION COMMIT
   plan      the EXACT BYTES the recorded immutable-create effect carries — the same bytes P1's
             serializer produced — not a reread of the file that effect wrote
   proof     no working-tree reread: a record is immutable, so the two are equal when nothing
             interfered, and committing the recorded bytes means an interference changes nothing
             about what is committed
   entries   exactly this generation's Review record paths

M. S-c1 / K1, THE CANDIDATE COMMIT
   plan      the bound artifact witness and the frozen Candidate; material = witnessed bytes;
             new_oid = Candidate.new_oid
   chain     WITNESS == CANDIDATE == PLAN == STAGED == K1

N. S-c2 / K2, TERMINAL
   plan      parent tree + recorded terminal append_event effects (as K) + the recorded
             Consumption record effect (as L)
   proof     no working-tree reread for either entry; §16's exact two-entry delta becomes a
             property of the PLAN, checkable BEFORE the commit rather than only after it

O. FINAL SYMLINK RESULT
   layer 2   the final component's OWN identity is taken by a no-follow METADATA QUERY —
             fstatat(..., AT_SYMLINK_NOFOLLOW) / FILE_OPEN_REPARSE_POINT + handle info — which
             IDENTIFIES the symlink instead of refusing it. It is not a canonical reserved
             object, so it PROCEEDS to layer 3.
   layer 3   witness = the link-target bytes read no-follow, git_mode 120000; the link is never
             dereferenced
   outcome   ACCEPTED. MEASURED (M-47): a reparse point's no-follow identity is its own
             (`11258999074582616`) and differs from its target's (`4785074610237389`).
   WITHDRAWN the earlier draft opened the final component with O_NOFOLLOW, which on POSIX
             REFUSES a symlink with ELOOP — turning every valid F2 mode-120000 result into
             `review_candidate_unavailable` before layer 3 ever ran. A valid final symlink is
             never refused merely for being a symlink.

P. SYMLINK / JUNCTION ANCESTOR
   outcome   containment failure, FAIL CLOSED, unchanged. The distinction from O is the point:
             the final object may be an indirection; an ancestor may not.

Q. THE GITLINK PATH'S ANCESTOR IS SWAPPED BEFORE THE OID IS CAPTURED
   was       `git -C <path> rev-parse HEAD`, which hands a PATHNAME to a second process. On POSIX
             a held fd pins nothing (fsafe), so the path could denote another repository by then
             and `-C` would read IT. WITHDRAWN.
   now       G-1...G-5 (§7.8.4): the submodule handle comes from the proven chain, its `.git`
             gitfile is read from that handle, the relative gitdir is resolved COMPONENT BY
             COMPONENT against handles already held, and HEAD and its ref are read from the
             resulting handle. An absolute gitdir, a `..` above the Project root, or an
             indirection in the chain each FAIL CLOSED.
   MEASURED  M-46: the handle-bound chain yielded `f600f63f...`, EXACTLY what
             `git -C sub rev-parse HEAD` returns and what `git ls-files --stage sub` records —
             with no Git process involved at all.

R. THE GITLINK'S OID CHANGES AFTER THE CANDIDATE IS FROZEN
   caught    by the full-witness currentness comparison, which compares the referenced commit OID
             rather than a byte digest — something M-32 shows the current `_content_digest` form
             cannot do at all (IP-16)
   cannot    reach the commit regardless: O-4 places the plan's frozen OID with
             `--cacheinfo 160000,<oid>,<path>`, which reads nothing from the filesystem

S. DETACHED HEAD AT START
   outcome   REFUSED BEFORE ANY PERSISTENCE. Live START calls `gitops.ensure_git_ready`
             (gitops.py:151), which raises StopError(code="detached_head") when there is no
             current branch. O-7 therefore always has a full branch ref to advance, and F3
             introduces NO detached-head semantics (§7.1.5). The earlier draft's "HEAD itself
             when detached" branch is withdrawn: it invented a case the operation cannot be in.
```

```text
FOR EVERY COMMIT CLASS the same four identities are one identity, and each step is checked rather
than assumed:

    the tree the PLAN determines
      == the tree `write-tree` returns          O-5 requires it
      == the tree `commit-tree` commits         O-6 is given that exact tree
      == the tree of the commit C-1 owns        O-7a promotes that exact id, and W4/W5 read it

and the parent is the plan's parent at O-2, at O-2a's agreement check, at O-6's `-p`, and at
O-7's compare-and-swap expected-old.
```

### 21.14 Hermetic-Git, identity and commit-class matrix

Every row is a required regression test. Where this environment could not construct the condition,
the row says so instead of claiming a measurement.

```text
A. PARTIAL CLONE, A BLOB MISSING LOCALLY
   bound     GIT_NO_LAZY_FETCH=1 on every class B invocation (§7.1.9), plus a promisor-configuration read
             at entry
   required  a locally absent object is LOCAL UNAVAILABLE and fails closed: no implicit fetch, no
             transport helper, no credential helper, no network
   MEASURED  an absent oid fails closed with EXIT 128 under the setting, the setting is accepted
             by every command the primitive uses, and promisor remotes are detectable (M-54)
   NOT       a real demand-fetch could NOT be provoked here: a local `file://` server answers
   MEASURED  "filtering not recognized by server, ignoring" and the clone comes back complete.
             The regression test must run against a filtering server. This contract does not
             claim to have observed a lazy fetch being suppressed.

B. refs/replace OVER plan.parent
   MEASURED  without the setting, `cat-file -p <P>` and `rev-parse <P>^{tree}` returned the
             REPLACEMENT's tree `0b996586`; with GIT_NO_REPLACE_OBJECTS=1 they returned the true
             `8b00ff5b` (M-49)
   required  the exact original object is used everywhere. Legacy `.git/info/grafts`, if present
             and non-empty, STOPS at entry.

C. A LITERAL FILENAME CONTAINING PATHSPEC WILDCARD CHARACTERS
   MEASURED  default `ls-files -- 'd/a[1].txt'` matched BOTH `d/a1.txt` and `d/a[1].txt`;
             GIT_LITERAL_PATHSPECS=1 matched exactly one (M-50)
   required  exactly one path is addressed, by every command that consumes a declared path

D. user.name / user.email ONLY IN GLOBAL CONFIG
   MEASURED  with config neutralized and no explicit identity, `commit-tree` EXIT 128 "Author
             identity unknown"; with the identity captured first and passed as GIT_AUTHOR_* /
             GIT_COMMITTER_*, the commit was made with the correct author and committer (M-51)
   required  an ordinary Project does not become uncommittable because F3 neutralized config

D2. HOSTILE INHERITED GIT_AUTHOR_* / GIT_COMMITTER_* AT CAPTURE TIME
   MEASURED  `git var GIT_AUTHOR_IDENT` -> `Attacker <evil@x>` and `git var GIT_COMMITTER_IDENT`
             -> `AttackerC <evilc@x>`, while `git -C <root> config --get user.name` / `user.email`
             UNDER THE GIT_* STRIP returned `Real Person` / `real@proj` (M-63)
   required  the capture runs AFTER the strip and uses `config --get` only; `git var ...IDENT` is
             withdrawn. End to end the raw commit carried the configured identity and no hostile
             value (M-63). Configuration precedence is preserved: repository-local beat global.

D3. GLOBAL-ONLY IDENTITY + HOSTILE INHERITED GIT_* + EXACT PHASE A ENVIRONMENT
   setup     global config `user.name = Global Person`, `user.email = global@example.com`; NO
             repository-local user.name or user.email; hostile inherited GIT_AUTHOR_*,
             GIT_COMMITTER_*, GIT_INDEX_FILE, GIT_OBJECT_DIRECTORY,
             GIT_ALTERNATE_OBJECT_DIRECTORIES and GIT_CONFIG_COUNT/KEY_0/VALUE_0
   class A   strip every inherited `GIT_*`; do NOT activate configuration neutralization; run
             `git -C <root> config --get user.name` / `user.email`
   MEASURED  -> EXIT 0, `Global Person` / `global@example.com` (M-64)
   CONTROL   the SAME capture with GIT_CONFIG_NOSYSTEM=1 and GIT_CONFIG_GLOBAL=<empty file> set
             -> EXIT 1 and EMPTY for both fields (M-64). THIS REGRESSION FAILS under a universal
             allowlist that applies the class B neutralization to class A, which is exactly what
             it exists to catch.
   class B   neutralize configuration, inject the captured `Global Person` /
             `global@example.com`, then commit-tree
   MEASURED  the raw commit read back cleanly held
                 author    Global Person <global@example.com>
                 committer Global Person <global@example.com>
             and NO hostile value anywhere in the object (M-64)
   required  a Project whose identity lives only in global configuration completes normally, and
             no hostile inherited value reaches the commit.

E. MALICIOUS reference-transaction HOOK
   MEASURED  with the default hooks directory it ran THREE TIMES for one `update-ref`; under the
             empty `core.hooksPath` it did not run at all (M-48)

F. MALICIOUS post-index-change HOOK
   MEASURED  it RAN for a real-index `update-index` with the default hooks directory, and did NOT
             run under the empty `core.hooksPath` — including inside the §7.1.4 transaction (M-48)

G. CONCURRENT STAGING DURING THE INDEX REFRESH
   MEASURED  while `.git/index.lock` is held O_EXCL, `git add` and `git update-index` both fail
             EXIT 128 (M-52), so there is NO compare/write gap; and with a person's foreign entry
             staged on an OWN plan path it was preserved byte-identical while the permitted path
             refreshed (M-53)
   required  foreign staging survives, always

H. EXPECTED-OLD ENTRY PRESENT, CLEANUP CANNOT COMPLETE
   required  C-1 REMAINS OWNED, and the operation does NOT silently return completed: R-IDX-8
             stops at a local cleanup checkpoint, because the measured trap is live — the
             person's next ordinary `git commit` would revert K (M-44)
   contrast  if the entry is FOREIGN instead, nothing is owed and completion is ordinary

I. WORK-RESULT GENERATION 1
   required  the generation mutation's invocation carries review_kind "work-result-v1", so its
             commit effect names "review-v1-work-local-v2" and is built by CommitTreePlan /
             O-1...O-8 (§7.1.7, C3-1)
   source    the recorded `create_file` bytes, never a reread of the file that effect wrote

J. AN ORDINARY P2 PLANNING GENERATION
   required  review_kind is a planning kind, so the effect still names
             "review-v1-planning-local-v1" and its behaviour is EXACTLY as today. The planning
             identity is never redefined and no planning Run changes.

K. A DERIVED REGISTRATION / MOVE PRE-COMPLETION COMMIT
   required  it HAS a CommitTreePlan, built by §7.1.1's generic rule from the parent object plus
             that stage's recorded effects in recorded order — add_relation / remove_relation
             re-rendering the ledger parsed from the ACCUMULATOR, write_file taking its payload,
             append_event appending to the accumulator — with the result required to match the
             digest the mutation durably recorded before writing
   not       `mutation.planned_write` as it stands, which sources two of its four branches from
             the working tree (M-56)

L. A PATH F2 LEGITIMATELY ACCEPTS THAT IS NOT NFC
   MEASURED  `mutation._safe_relative` accepts NFD as readily as NFC (M-55)
   required  ACCEPTED. §5.1 step 5b is exactly the landed predicate, so no NFC rule, no NUL rule
             and no "Git-reserved name" rule refuses it. Adding any of them would have been a
             post-executor refusal of a supported result shape (F2 §2.3), and no amendment beyond
             A-7 and C3-1 is taken for path grammar.
```

### 21.15 Raw-ancestry and recovery matrix

Every ancestry row compares Git's REVISION VIEW against the RAW COMMIT OBJECT. The frozen authority
is always the raw one (§7.1.8).

```text
A. `.git/info/grafts` SUPPLIES A FAKE PARENT
   MEASURED  on C1 <- C2 <- C3 <- C4 with grafts holding "C4 C1" (M-57):
                 rev-list --parents -n 1 C4       -> C1      the walker is LIED TO
                 merge-base --is-ancestor C2 C4   -> FALSE   for a genuine ancestor
                 cat-file commit C4 | parent      -> C3      the object is UNAFFECTED
   frozen    RAW_PARENTS(C4) == {C3}. The graft file changes no P3 answer.
   live gap  `gitcmd.commit_parents` and `gitcmd.descends_from` ARE the two lied-to calls, which
             is why IP-26 forbids delegating to them.

B. A GRAFT FILE APPEARS AFTER THE OPERATION HAS ENTERED
   frozen    nothing changes. RAW_PARENTS re-reads the stored object every time it is asked, so
             there is no window in which an earlier check is relied upon. The entry refusal is
             retained as DEFENCE IN DEPTH only (§7.1.9) — correctness never depended on it, which
             is what makes a mid-Run graft harmless rather than a blocker.

C. A SHALLOW CLONE / SHALLOW BOUNDARY
   MEASURED  in a `--depth 1` clone whose HEAD is a merge commit (M-59):
                 rev-parse --is-shallow-repository -> true
                 rev-list --parents -n 1 HEAD      -> HEAD alone: LOOKS LIKE A ROOT
                 rev-list --count HEAD             -> 1
                 RAW cat-file commit HEAD          -> TWO parent headers
                 cat-file -e <that parent>         -> ABSENT locally
   frozen    the raw object is the authority, so HEAD has two parents; they are locally
             unavailable, so the answer is UNKNOWN and FAILS CLOSED.
             NEVER "this commit is a root". That is the exact misreading the walker produces, and
             a lineage proof built on it would conclude a commit had no history at all.

D. A MERGE COMMIT
   MEASURED  `GIT_NO_REPLACE_OBJECTS=1 cat-file commit <merge>` printed exactly TWO `parent`
             headers, in order, equal to the two merged commits (M-60)
   frozen    RAW_PARENTS preserves count and order. Nothing in this contract assumes one parent
             where the object has two; where a proof REQUIRES one parent (W3, T3), it requires it
             of the raw headers and refuses a second.

E. refs/replace OVER A COMMIT WHOSE PARENTAGE IS BEING READ
   MEASURED  plain `cat-file commit C4` showed NO parent, because it read the replacement (a
             root); `GIT_NO_REPLACE_OBJECTS=1` showed the true C3 (M-58)
   frozen    the setting is part of RAW_PARENTS itself, not merely of the ambient environment, so
             reading the object is raw even if some future caller forgets the global rule.

F. A CRASH IMMEDIATELY AFTER `index.lock` O_EXCL ACQUISITION
   MEASURED  a lockfile is ZERO BYTES — no pid, no host, no owner of any kind (M-62)
   frozen    ONE recovery class: ownership is UNKNOWN, the lock is NEVER deleted automatically,
             and the operation STOPS at INDEX LOCK RECONCILIATION (R-IDX-8). Ownership is not
             inferred from the filename, the file's age, the absence of a process, the index
             contents, or the existence of a pending mutation.
   NOT       that "a resume retries and it resolves". A resume re-attempting O_EXCL finds the
   CLAIMED   same file and gets UNKNOWN again, so retrying alone can never clear a lock this
             operation itself left. A person or F4 removes the stale Git lock — ordinary Git
             housekeeping after any process dies mid-write — and the same pending operation then
             resumes at the same cleanup checkpoint.

G. A STALE OWN `index.lock` FOUND ON RESUME
   frozen    C-1 REMAINS OWNED. K is on the branch and provable; W1, the proof note, the barrier
             and every publication right stand exactly where they stood; the mutation stays
             pending so nothing is abandoned or re-decided. Only the cosmetic index refresh is
             outstanding, and R-IDX-8 refuses to call the operation complete while the measured
             revert trap (M-44) is live.

H. A HOSTILE INHERITED GIT ENVIRONMENT
   MEASURED  each alone (M-61):
                 GIT_AUTHOR_NAME/EMAIL inherited -> the commit carried `Attacker <evil@x>`
                                                    although the Project was configured otherwise
                 GIT_INDEX_FILE inherited        -> silently redirects every index command
                 GIT_OBJECT_DIRECTORY inherited  -> `cat-file -e HEAD` EXIT 1: the repository's
                                                    own commit invisible
   frozen    §7.1.9's ONE rule: strip EVERY inherited `GIT_*` — including GIT_DIR, GIT_WORK_TREE,
             GIT_INDEX_FILE, GIT_OBJECT_DIRECTORY, GIT_ALTERNATE_OBJECT_DIRECTORIES,
             GIT_REPLACE_REF_BASE, GIT_CEILING_DIRECTORIES, GIT_NAMESPACE, GIT_AUTHOR_*,
             GIT_COMMITTER_* and every unknown `GIT_` name — then inject EXACTLY the allowlist.
             The author/committer identity is the one CAPTURED before neutralization; inherited
             GIT_AUTHOR_* do not survive, and the contract says only that.
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
    F2 §16.1's invalidation row states that consequence flatly and without qualification, and F3
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

26  Live `_finish_generation` / `gitops.review_commit_effect` (roadmap_review.py:1447,
    gitops.py:201). They set mode "review-v1-planning-local-v1" UNCONDITIONALLY, while F3 §7.6
    puts the Review's own generation commits under the Work primitive. Resolved by the durable
    `review_kind` discriminator: "work-result-v1" -> the Work identity, every other kind ->
    planning, unchanged. The planning identity is never redefined.
    F3-ONLY CORRECTION C3-1 (§1.5) — NOT an F2 amendment. §7.1.7.                            C

25  F2 §10.3 — `git_persistence = "review-v1-work-local-v1"`, described there as denoting the
    contained commit primitive. F3 §7.1.2 replaces that primitive, so the value must change or a
    landed sentence becomes false while readers compare against the wrong semantics. The FIELD
    keeps its name, position and meaning (A-4 stands); only its VALUE becomes
    "review-v1-work-local-v2". FORWARD AMENDMENT A-7 (§1.5). §7.1, §7.9.6.                    C

24  F2 §6.2, §6.5 and §2.3 — the reserved lifecycle event log.
    The deletion witness binds a base identity at step 5d, before S-c0 exists, so it must use
    PRE_S_C0_BASE; the Candidate measures old_* against declared_base. The two differ at exactly
    one path, `.workline/events/events.jsonl`, and nothing landed excludes that path from a
    declaration — so the two bases were not interchangeable and the earlier sentence "the event
    log is never a result path" was an unsupported premise. §6.2 is superseded by a second
    exclusion, §6.5 extended by a second instance of A-5's ownership predicate, §2.3 retained.
    FORWARD AMENDMENT A-6 (§1.5). §7.8.5.                                                      C

23  F2 §6.2, §6.5 and §2.3 — the reserved Review namespace. A-5 touches three sections and
    each one differently, so each is stated:

    §6.2  "The reviewed surface is exactly result_paths U deleted_paths as the executor declared
          them."  SUPERSEDED by one exclusion: minus any path inside the canonical Review
          namespace. Required because the canonical Review checkout rule normalizes check-in
          bytes there (M-26), so a Candidate entry in that namespace would break the
          storage-identity invariant.                                                          C

    §6.5  EXTENDED, and it is NOT correct to call it unchanged. §6.5 names exactly two
          post-executor declaration failures — a declared path that is a directory, and one that
          cannot be read — both about PROJECTABILITY. F3 adds a third, about OWNERSHIP, with its
          own refusal identity `review_reserved_namespace`.                                    C

    §2.3  RETAINED in full, and not weakened. §2.3 forbids refusing an ordinary correct outcome
          for an unsupported RESULT SHAPE; a reserved-namespace declaration is unowned state,
          which §2.3 expressly permits refusing, under a rule bound before the executor ran
          (PR-8).                                                                              A

    No landed rule excludes the namespace today — checked — so the exclusion is declared rather
    than assumed. FORWARD AMENDMENT A-5 (§1.5). §7.8.4.

22  F2 §10.3 and §10.1  "Checkout capability is not bound in the Work Context.\"
    F3 binds a checkout-capability claim over the CANONICAL REVIEW NAMESPACE - not over the Work
    result, where §10.3's reason stands - because a Work result can now change persistence
    semantics and make the Run's own records unreadable in a fresh clone. §10.3 names "a Context
    version change" as the mechanism, and F3 uses exactly that.
    FORWARD AMENDMENT A-4 (§1.5), which also supersedes §10.1's exact Context record
    because a field cannot be added to a frozen exact schema otherwise. §7.9, §7.9.6.        C

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

18  registry.md Commit / push, Push destination, Git versions.
    F3 introduces no new refspec form, no new adoption rule and no new destination behaviour,
    and the publication-capability refusal of §12.4 uses the existing P2_PUBLICATION_GIT_MIN
    and the existing code. It DOES introduce one new threshold, and the earlier claim that it
    introduced none is corrected here:

        P3_WORK_ATTR_PIN_GIT_MIN = 2.43.0    the review-v1 Work attribute pin (§7.7)

    It is owned by rules/git alongside the two P2 thresholds, it does not alter either of them,
    and it is not the authority for anything on its own — the capability probe of §7.7 is
    (PB-11). Adding a threshold is an extension of what rules/git owns, not a change to a rule
    it already states, so this stays a specialization.                                         A

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
    that those sentences classify as result-bearing and that therefore demands a K1 that may not
    be made — a synthetic empty commit, prohibited by F1 §11.2 and F2 §20.5 and forbidden at
    §7.1.2 O-5/O-6. The discriminator moves to the complete owned tree delta.
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

Seven F2 amendments (A-1 ... A-7) and one F3-only correction (C3-1), declared in full in §1.5:
    A-1  F2 §5.3           base_commit's timing, and that it is K1's parent       row 19
    A-2  F2 §14.4, §16.1   the unqualified "every HEAD advance" consequence       row 3
    A-3  F2 §7.1/7.2/7.3   the result-bearing / no-K1 discriminator               row 21
    A-4  F2 §10.3, §10.1   checkout capability unbound, and the exact Context     row 22
                           record it has to be added to
    A-5  F2 §6.2 SUPERSEDED, §6.5 EXTENDED, §2.3 RETAINED                         row 23
                           the reserved Review namespace: the reviewed surface excludes it,
                           and a declaration there is unowned state refused as
                           `review_reserved_namespace` — a third declaration-invalidity case
                           beside §6.5's two, not one of them
    A-6  F2 §6.2 SUPERSEDED, §6.5 EXTENDED, §2.3 RETAINED                         row 24
                           the reserved lifecycle event log, refused identically and by the
                           same reason value — a SECOND INSTANCE of A-5's case, not a fourth
                           case. It is what makes PRE_S_C0_BASE and declared_base
                           interchangeable at every declarable path
    A-7  F2 §10.3         git_persistence's VALUE becomes                         row 25
                           "review-v1-work-local-v2". The field's MEANING is unchanged
                           and A-4 stands; the behaviour it names is no longer the
                           contained commit primitive, so the identity cannot be
                           reused without making a landed F2 sentence false

AND, IN ITS OWN CLASS, superseding no F2 sentence:

    C3-1 F3-ONLY CORRECTION  a Work Review Run's own generation commits use the Work  row 26
                           persistence identity, discriminated by the durable
                           review_kind; every planning Run is untouched. NOT an F2
                           amendment and NOT counted among the seven.

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
PB-3  the commit primitive identity "review-v1-work-local-v2" — a NEW semantics identity (A-7),
      because the behaviour is no longer F2 §10.3's contained commit primitive, and the planning
      identity "review-v1-planning-local-v1" is NOT redefined (C3-1). Its frozen behaviour is the
      OBJECT-DRIVEN sequence of §7.1.2: the commit is built from object identities, and no
      working-tree pathname is resolved between the artifact's identity proof and the committed
      tree. `git add` and `git commit`/`git commit --only` are not used for it. Hooks do not run
      and no signature is applied — a property of `commit-tree` itself (M-37), with
      core.hooksPath / commit.gpgSign retained as defence in depth — and there is no filesystem
      monitor, no background maintenance, and core.autocrlf / core.eol are neutralized.
      Every commit class commits a COMMIT TREE PLAN (§7.1.1), never a reread of the working tree,
      and the branch advances only under a compare-and-swap `update-ref` against the exact
      recorded parent (M-38). Ownership is durable BEFORE the ref moves (O-6a) and is promoted to
      C-1 only after the ref is read back holding that exact id (O-7a). The real index is
      refreshed only after C-1, under an O_EXCL `index.lock` held across the whole compare and
      write, only for this commit's own plan paths, only where the entry is still the one the
      plan expected, published by an atomic rename, and never able to un-own K (§7.1.4). Every
      invocation runs under the hermetic environment of §7.1.9 — GIT_NO_LAZY_FETCH,
      GIT_NO_REPLACE_OBJECTS, GIT_LITERAL_PATHSPECS, an empty core.hooksPath that is measured to
      contain `reference-transaction` and `post-index-change` (M-48), and an author/committer
      identity captured before config neutralization.
      A material transform assigned by the PINNED source to an ORDINARY path is
      review_git_transform, never disabled to obtain a pass. This does NOT reach the reserved
      canonical Review namespace: a rule whose pattern is confined to `.workline/review/**` is
      the form-L rule the capability claim REQUIRES (§7.8.4, §7.9.3), and refusing it would make
      every P2-capable Project unusable for P3 Work Review. The two surfaces are distinguished
      by pattern confinement, never by which attribute name appears
PB-4  base-exact commits: K1 and K2 are built on their EXACT recorded parent object id and the
      branch advances only under a compare-and-swap against that same id (§7.1.2 O-2/O-7, M-38),
      so a moved branch is refused rather than committed onto; the independent-HEAD-advance
      allowance does not apply to them. Ownership is the operation's own DURABLE
      prepared_commit_id, recorded before the ref moves and promoted to commit_id only after the
      ref is read back holding it (§7.1.2 O-6a/O-7a, §7.10). An object this operation wrote but
      never durably prepared is never adopted, and "the recorded paths no longer differ from
      HEAD" is never ownership (M-41)
PB-5  a review-v1 Work START in a Project with a remote requires the running Git to meet
      P2_PUBLICATION_GIT_MIN, refused at entry with review_git_unsupported, because its
      Candidate snapshot permanently takes that Project's pushes off the barrier's fast path
PB-6  the Git persistence preflight runs immediately before EVERY commit a review-v1 Work
      mutation makes, for exactly that commit's path set, evaluated under the pinned
      attribute source, and a pass never carries between commits (§7.3)
PB-9  the attribute-source pin, with its TWO bases (§7.1.11): S-c0 is made with attr.tree set
      to the tree of PRE_S_C0_BASE — the committed HEAD immediately before it — and EVERY later
      commit of the mutation with attr.tree set to the tree of declared_base.base_commit. The
      two are proven to represent the SAME attribute state, because S-c0 commits the event log
      alone and so can change no attribute source. In both cases the system and global attribute
      sources are neutralized, so committed object identity equals the Candidate's by
      construction and no filter program is reachable (§7.1, §7.1.11, §7.4.2)
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
PR-6  the resume points of §5.4, the Context durability model of §5.3, and that a resume
      re-derives and never re-decides
PR-7  that a pending review-v1 mutation never downgrades to legacy, and that legacy
      availability is a property of a separate later invocation (§7.4)
PR-8  THE TWO RESERVED NAMESPACES, BOUND BEFORE EXECUTION. Selecting review-v1 binds, as part
      of the invocation contract and BEFORE the executor runs, that

          .workline/review  and  .workline/review/**      A-5   the canonical Review namespace
          .workline/events/events.jsonl                   A-6   the lifecycle event log

      are reserved namespaces which START's executor may not own — not as result paths and not as
      deletion paths. The rule is static and in force from selection; the concrete future path
      list need not be known for it to bind. Both refuse identically, with the same reason, and
      A-6 is what makes PRE_S_C0_BASE and declared_base.base_commit interchangeable at every
      declarable path (§7.8.5).

      The checks run at §5.1 steps 5b, 5c and 5d, BEFORE declare_own_content, so this operation
      never durably asserts ownership of a path it may not own — and "inside a reserved
      namespace" is decided by the three-layer rule of §7.8.4, never by a string prefix test.
      FILESYSTEM OBJECT IDENTITY IS THE AUTHORITY there, for both namespaces: the ASCII-only case
      fold is a deterministic pre-filter, and the positive proof is that an opened ancestor, or
      the declared path's own final component opened with no-follow semantics, IS or IS NOT the
      canonical object (§7.8.4 layer 2, sub-steps 2a-2e). An identity that cannot be established
      fails closed.
      Step 5d produces a BOUND OWNERSHIP WITNESS and step 6 persists it without re-resolving the
      declared path, so the object proven is the object asserted. A declared DELETION whose
      ancestor directory no longer exists is an ordinary correct outcome, not a refusal: the
      missing ancestor positively proves the absence.

      A `Completed` outcome declaring a path in either namespace has violated a pre-existing ownership
      contract. It is UNOWNED STATE, refused as
      ReconcileRequired(reason = "review_reserved_namespace") — the reconcile recovery class F2
      §2.3 assigns to unowned state, carrying a dedicated reason.
      It is NOT an unsupported Git result shape, NOT `review_candidate_unavailable` (which means
      projectability), and NEVER a fallback to legacy.

      This statement is load-bearing: it is what makes the refusal lawful under F2 §2.3, which
      permits refusing unowned state while forbidding a post-executor refusal of a supported
      result shape. Without it in the executor contract, the same refusal would be a discovery
      made during Candidate projection, which §2.3 does not permit (§7.8.4, A-5)
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
TM-8  the seven F2 forward amendments of §1.5, and the one F3-only correction C3-1 beside
      them, which a reader of F2 alone cannot
      discover from F2
TM-10 the seal precondition of §7.9: a Review may not seal unless the resulting tree preserves
      canonical Review checkout capability over the Review namespace, proven mechanically
      over that tree and never left to reviewer discretion
TM-11 THE WORK REVIEW CONTEXT, VERSION 2, and its target-only capability record:

          schema:  "review-work-context"
          version: 2

          review_checkout_capability: {
              capability_contract: "review-v1-work-checkout-capability-v1"
              form:                "form-L"
              namespace:           ".workline/review/**"
              base_tree:           <full object id>
              resulting_tree:      <full object id>
          }

      Exactly five keys, and NO VERDICT FIELD of any kind. Also activating:

        the Context is IMMUTABLE before generation 1 accepts the task, and is what the TaskInput
          and every gate generation bind through review_context_hash;
        a Context whose resulting tree is UNSAFE or UNKNOWN is a VALID Context — it is built,
          generation 1 may exist and the external Review occurs normally;
        the verdict is DERIVED, only at seal, for exactly Context.resulting_tree;
        only `capable` may issue a Receipt; unsafe and unknown withhold authorization (§7.9.5);
        the seal changes no Context byte and computes no new review_context_hash.

      A schema in which only the passing outcome is representable is the defect this replaces:
      it would make an unsafe resulting tree unable to reach Review at all
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
F3-D1   Work local persistence      FROZEN   "review-v1-work-local-v2" — a NEW semantics
                                             identity (A-7), because the behaviour is no longer
                                             F2 §10.3's contained commit primitive. Every
                                             commit class commits a COMMIT TREE
                                             PLAN (§7.1.1) built from the witness/Candidate
                                             (K1), the parent blob plus recorded append_event
                                             effects (S-c0), the recorded immutable-create bytes
                                             (generation commits) or both (K2) — never a reread
                                             of the working tree. The OBJECT-DRIVEN sequence
                                             O-1..O-8 (§7.1.2) resolves NO working-tree pathname
                                             between the identity proof and the committed tree,
                                             so the ancestor-swap race cannot change what is
                                             committed, measured under active sabotage (M-36).
                                             Isolated index, exact-parent read-tree, parent
                                             agreement, hash-object from the PLAN's material with
                                             the id checked against the plan's new_oid,
                                             update-index --cacheinfo / --force-remove,
                                             write-tree, commit-tree (no hooks, no signature —
                                             M-37). OWNERSHIP IS DURABLE BEFORE THE REF MOVES:
                                             O-6a records prepared_commit_id, O-7 is a
                                             compare-and-swap update-ref (M-38), and O-7a
                                             promotes it to C-1 only after the ref is read back
                                             holding that id — closing the crash window in which
                                             live code would have inferred ownership from "the
                                             paths no longer differ from HEAD" (M-41). §7.1.3
                                             decides every resume from that durable id. The real
                                             index is refreshed only after C-1, only for own plan
                                             paths, only where the entry is still the expected
                                             one, and never as a condition of anything (§7.1.4,
                                             M-44, M-45). An empty delta is a STOP, not a
                                             commit. Parentage, range and descent come from the
                                             stored commit object's literal `parent` headers
                                             (§7.1.8), never Git's revision view, which grafts
                                             and shallow change (M-57, M-59); and every
                                             invocation strips all inherited GIT_* and injects
                                             only an exact allowlist (§7.1.9, M-61).
                                             The ATTRIBUTE SOURCE PIN is RETAINED
                                             and RE-CLASSIFIED: defence in depth for storage
                                             identity, still load-bearing for §7.9's
                                             checkout-capability claim and §7.8's entry
                                             predicate. Line-ending configuration neutralized
                                             (M-23), a capability probe before the first pinned
                                             commit, and a universal predicate over the attribute
                                             source. The preflight binds every commit the
                                             operation makes — the Review's own generation
                                             commits included.
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
    the same attribute state because S-c0 commits the event log alone (§7.1.11). The Git
    persistence preflight runs
    immediately before each of them, over exactly that commit's path set, evaluated under that
    same pin. A pass never carries from one commit to another, and an evaluation made against the
    working tree never satisfies it.

23. The staging-byte contract holds exactly: the plan's new_oid equals the object written, the
    index entry placed, the tree entry written and the entry in the tree C-1 owns — for every
    commit class, and for K1 that id IS Candidate.new_oid. It is made true BY CONSTRUCTION: the
    object is written from the plan's own material and its id is checked before anything else
    happens, and every later step carries object ids only. The attribute-source pin, the
    neutralized line-ending configuration and the universal source predicate are retained as
    defence in depth (§7.1.10); none of it is ever assumed from the absence of a clean filter.

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

27d. The artifact identity is carried unbroken from executor return to K1: witness, Candidate,
    CommitTreePlan, snapshot material, pre-stage currentness, staged object and K1 tree entry are
    the same artifact, for every supported kind — file, executable file, symlink, gitlink and
    deletion. The Candidate is derived from the witness, never from a reread of the working tree.

27j. The persistence semantics identity names the semantics actually used. When the behaviour an
    identity denotes changes, the identity changes with it; an identity is never silently
    redefined, and one operation's change never redefines another's identity.

27k. A person's staged Git state is unsaved work. It is never overwritten for this operation's
    convenience, on an own path or an unrelated one, and the comparison that decides is made
    under the same exclusive lock as the write, so no gap exists between them.

27l. EVERY Git invocation of this operation strips EVERY inherited `GIT_*` variable. That rule
    has no exception, and it is what protects the operation from a hostile ambient environment.

    What the class B invocations ADD to it — an exact allowlist, configuration neutralization,
    and with them the guarantees that an OID means the object it names, a path addresses exactly
    itself, no network is reached and no hook runs — is NOT part of the strip and does not apply
    to the one class A invocation, whose declared purpose is to read the configuration those
    additions hide (§7.1.9, M-64). Stripping inherited `GIT_*` on every invocation and injecting
    the post-capture hermetic allowlist on every invocation are two different rules; only the
    first is universal.

27m. Parentage, range and descent are read from the literal `parent` headers of the stored commit
    object. Git's revision view is not the authority, because refs/replace, `.git/info/grafts`
    and `.git/shallow` change it and change no object; a named parent that is not locally
    available is UNKNOWN and fails closed, and is never read as a root.

27n. Ownership of a lock is never inferred. A lock this operation did not provably create is
    UNKNOWN, is never deleted automatically, and stops the operation at a reconciliation
    checkpoint that costs it nothing it had already proven.

27g. EVERY commit this operation makes commits a PLAN, and no plan's material is a reread of the
    working-tree copy of a path the plan describes. S-c0 and K2's event entry come from the parent
    blob plus this mutation's recorded events; a generation commit and K2's Consumption entry come
    from the bytes the recorded immutable-create effect carries; K1 comes from the artifact
    witness. A mutable file anything may have touched is never the authority for what is
    committed.

27h. A commit is owned because this operation DURABLY RECORDED making it, before any ref moved,
    and never because the branch reached a state consistent with it. "The recorded paths no longer
    differ from HEAD" is not ownership; neither is the branch tip, a matching message, or a
    byte-identical commit. An object written but never durably prepared is never adopted.

27i. No cosmetic or local-convenience step can cost the operation a commit it already owns, and no
    such step may overwrite state the operation does not own. The real-index refresh runs after
    durable C-1, touches only this commit's own paths, leaves any foreign entry exactly as it is,
    and its failure changes nothing that is proven.

27e. The witness is per-kind and carries kind, mode and object identity. A single content digest
    cannot express a gitlink's referenced commit or an executable bit, and a contract that relied
    on one would not detect either.

27f. Two ownership boundaries bind before execution and are refused identically: the canonical
    Review namespace (A-5) and the lifecycle event log (A-6). The second is what makes
    PRE_S_C0_BASE and declared_base interchangeable at every declarable path.

27b. The object whose containment was proven is the object whose ownership is asserted. The
    identity proof produces a bound witness captured relative to the proven parent, and the
    ownership snapshot persists that witness rather than resolving the declared path from the
    Project root a second time.

27c. A declared deletion whose ancestor directory no longer exists is an ordinary correct
    outcome. A missing ancestor positively proves the declared path's absence and is accepted;
    only an EXISTING ancestor that is an indirection, or whose identity cannot be established,
    fails closed. An ordinary correct deletion is never refused after the executor returns.

27a. Canonical spelling is fixed, then reserved ownership is classified, then containment is
    proven and the witness captured, then ownership is asserted — in that order, and a step
    never runs on a path an earlier step refused. Both reserved namespaces are proven absent
    BEFORE declare_own_content durably records the path as START's own. A prefix test over the
    declared string is never sufficient; the ASCII fold is a pre-filter and FILESYSTEM OBJECT
    IDENTITY is the authority; unknown identity or unknown containment fails closed; and the
    final component is never dereferenced — where its identity is taken, it is taken by a
    no-follow open that refuses a symlink rather than following one.

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
Contract status              FROZEN (repaired through successive independent reviews)
Architecture blocker         NONE
HUMAN decision               NONE
F2 forward amendments        SEVEN (A-1 ... A-7), declared in §1.5
F3-only corrections          ONE (C3-1), superseding nothing in F2
Implementation authorized    NO
P3 implementation            NOT STARTED
F4 started                   NO

F1 ordered prerequisites, unchanged and still binding:
  Gate 1  Event metadata carrier                                    NOT AUTHORIZED
  Gate 2  Consumption v1 artifact_kind repair, test-pinned          NOT AUTHORIZED
  Gate 3  activation producer and actual activation                 NOT AUTHORIZED

Freezing F3 authorizes no Gate. The activation producer still fails closed until Gates 1 and 2
are both satisfied.

Implementation prerequisites this contract measured and named, authorizing none. This list is
the complete set of §21.1 and is never a weaker summary of it:
  IP-1  a closed set of two git_commit persistence modes, the review-v1 one dispatching to the
        object-driven primitive rather than to contained_add/contained_commit
  IP-2  the "work" branch of the publication discriminator and its validator
  IP-3  _recorded_completion recognizing the three-effect terminal stage, legacy unchanged
  IP-4  F1 Gate 1
  IP-5  F1 Gate 2
  IP-6  the isolated verification materialization primitive (F2's named gap)
  IP-7  F1 Gate 3
  IP-8  the per-invocation environment classes of §7.1.9 — the GIT_* STRIP on EVERY invocation
        including the class A capture, the hermetic allowlist and configuration neutralization on
        every CLASS B invocation only, the attribute pin with its two bases (§7.1.11) on every
        class B invocation that resolves attributes, literal pathspecs on every class B
        invocation consuming a declared path. NOT "both invocations", and never
        `git add` / `git commit`
  IP-9  the persistence evaluation made UNDER the pin, not against the working tree
  IP-10 core.autocrlf / core.eol neutralization on every class B invocation
  IP-11 P3_WORK_ATTR_PIN_GIT_MIN = 2.43.0 and the capability probe that is its actual authority
  IP-12 the universal attribute-source parser: every .gitattributes in the tree at every depth
        plus info/attributes, alias-expanded, narrow supported shape, no user-defined macros
  IP-13 the resulting-tree checkout-capability machinery and the Work Review Context v2 record
  IP-26 the RAW commit ancestry reader of §7.1.8 — raw parent headers only, no replace/graft/
        shallow interpretation, locally-unavailable parent -> fail closed, both OID widths. It
        must not be delegated to gitcmd.commit_parents / descends_from (M-57, M-59)
  IP-25 the hermetic Git environment of §7.1.9 on every CLASS B invocation — strip ALL
        inherited GIT_* (which class A does too), inject exactly the class B allowlist, and
        capture the author/committer identity AFTER the strip and BEFORE config neutralization,
        by `config --get` alone (M-51, M-61, M-63, M-64)
  IP-24 the atomic index transaction of §7.1.4 (O_EXCL index.lock, snapshot, entry-wise compare,
        atomic rename, R-IDX-8 cleanup checkpoint)
  IP-23 the generation mode dispatch of §7.1.7: review_kind "work-result-v1" -> the Work
        identity; every planning kind unchanged
  IP-22 the parent-object-sourced generic plan builder of §7.1.1, covering every effect kind a
        pre-completion Work stage can record
  IP-21 two handle-bound readers fsafe does not expose yet: a no-follow final-object identity
        query that IDENTIFIES a symlink rather than refusing it (M-47), and the handle-bound
        submodule HEAD reader of §7.8.4 G-1...G-5 (M-46)
  IP-20 the conditional, entry-compared, non-authoritative real-index refresh of §7.1.4 (M-44,
        M-45)
  IP-19 the generic CommitTreePlan of §7.1.1, one builder per commit class, none of which reads
        the working-tree copy of a path the plan describes
  IP-18 the prepared-commit ownership checkpoint of §7.1.2 O-6a / O-7a and the §7.1.3 resume
        matrix — without it a crash between the ref advance and the save is classified MATCHING
        with no owned commit id (M-41), which P1 R5 §3.1/§3.5 forbid
  IP-17 the object-driven persistence primitive of §7.1.2 — the replacement for
        contained_add/contained_commit — together with the pre-stage containment re-proof of
        §7.8.4, the empty-delta assertion, and the regression test over §21.12 that pins the
        committed tree entry to the planned identity under an active ancestor indirection
  IP-16 the per-kind witness runtime form: `_OWN_CONTENT` extended to carry path, kind, git_mode
        and identity, and a currentness comparison over the whole witness — without it a changed
        gitlink (M-32) and a chmod (M-33) are undetectable
  IP-15 the bound ownership witness of §7.8.4 — the CAPTURE half, which must land TOGETHER with
        IP-16: a handle-bound capture that replaces declare_own_content's second
        `root / relative` resolution. It does NOT produce the same recorded forms; an earlier
        draft claimed "_BYTES, _LINK, _ABSENT, _UNREADABLE unchanged" and that claim is
        withdrawn (M-32, M-33). IP-15 fixes WHERE the value comes from, IP-16 fixes WHAT is
        recorded, and neither alone is sufficient
  IP-14 the reserved-namespace ownership boundary of A-5 AND A-6 — the Review namespace and the
        lifecycle event log, one predicate with two reserved sets: the pre-execution binding in
        the review-v1 invocation contract, the post-Completed validation of every declared
        result and deletion path — running BEFORE declare_own_content, by §7.8.4's three-layer
        rule rather than a prefix test, with filesystem object identity as the authority and the
        ASCII fold as a pre-filter — and the new ReconcileRequired reason value
        `review_reserved_namespace` registered in the reason catalogue (no new code and no new
        exception class is needed)

Not implemented by this contract:
  any commit primitive, proof, validator, terminal stage, publication or postcheck code
  any change to src/, tests/, registry.md, canonical Skills, BACKLOG.md, or any P1, P2, P3 F1 or
    P3 F2 document
```
