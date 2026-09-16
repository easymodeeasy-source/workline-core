# Review System P1 — R10 Project / Global Policy Adapter Hook Contract Freeze

Status: CONTRACT FROZEN / IMPLEMENTATION NOT STARTED

This checkpoint freezes only the P1 common hook needed so later Project/Global Policy Changes can use Candidate 7's semantic round-trip proof. It deliberately does not invent P6/P7 policy schemas, paths, or physical owners before their live reconnaissance.

## 1. Live facts inspected

The current live implementation has no Review Policy persistence subsystem and no Project/Global self-evolving Review Policy canonical loader. `project.yaml` contains Workline root/rule routing/push configuration and is not a generic Review Policy store. `state.py` derives domain lifecycle from canonical entities/relations/events and must not absorb Review Policy state.

Therefore P1 should establish a reusable adapter contract and identity boundary only. Creating speculative policy files or making `project.yaml` carry future policy semantics now would be premature and could accidentally create a second authority.

## 2. Frozen common Policy persisted-projection hook

Any future Policy Review kind that is allowed to persist a Policy Change must supply an adapter implementing these semantic responsibilities:

```text
policy_scope_identity()
canonical_loader_identity()
normalize_reviewed_before()
normalize_reviewed_after()
expected_persisted_projection()
load_persisted_policy()
normalize_loaded_policy()
compare_semantics()
```

Exact Python protocol names are implementation detail, but an adapter must expose equivalent behavior before the Review kind can be activated.

## 3. Semantic round-trip invariant

For Project or Global Policy Change:

```text
reviewed normalized after-state
+
exact base/before version
+
loader/schema/default-semantics identity
↓
deterministic expected persisted projection
↓
local commit
↓
exact artifact/metadata/scope proof
↓
canonical policy loader reread
↓
normalized loaded after-state
=
reviewed normalized after-state
```

A byte/hash match alone is insufficient because defaults, omitted fields, schema interpretation, or loader changes can alter effective meaning.

## 4. Before-version binding

Every Policy Change Candidate binds an exact before-state identity/version. The adapter must fail closed if the canonical Policy has changed since Review:

```text
current before identity != reviewed before identity
-> stale Candidate
-> new Candidate / Review
```

It must never apply a patch designed for one Policy version to another by best-effort merge.

## 5. Loader/schema/default identity

The Review Context for a Policy Change includes a durable identity for the code/schema/default semantics that interpret the persisted Policy.

At minimum the identity must distinguish changes to:

- adapter contract version;
- schema version;
- canonical loader implementation identity;
- default values/normalization semantics;
- materially relevant Global base version when evaluating a Project-local effective Policy.

If that identity changes between Review and persistence/reload, the old semantic proof is invalid unless irrelevance is positively proven.

## 6. Exact persisted projection

The adapter returns a closed expected set of canonical paths and deterministic expected contents/tree entries for the Policy operation.

Rules:

- expected path set is fixed before local commit;
- no opportunistic extra metadata path after freeze;
- exact commit-delta proof rejects extra/missing path or content;
- Review runtime files are never part of the canonical Policy projection;
- if Policy storage later uses multiple files, the adapter treats them as one semantic projection and rereads them through the canonical loader as a unit.

## 7. Project vs Global boundary

P1 freezes only the interface distinction:

```text
Project Policy adapter
  scope = one established Project
  future physical owner/path/version = P6 reconnaissance

Global Policy adapter
  scope = Workline-root/global authority
  future physical owner/path/version = P7 reconnaissance
```

P1 does **not** choose:

- exact Project Profile path;
- exact Global root Policy path;
- final YAML schema;
- version-number format;
- root-maintenance Git primitive;
- promotion thresholds.

Those decisions require the actual P6/P7 live implementation surface and are explicitly deferred, not missing architecture.

## 8. Effective Policy construction boundary

The adapter hook supports the Candidate 7 model in which a Review Run binds an `effective_policy_hash`. The exact Effective Policy may later combine:

```text
Global mandatory/default policy
+ Project profile
+ Review-kind requirements
+ Candidate risk adjustments
+ temporary experiment/guard state
```

P1 does not make this combination mutable from `state.py` and does not allow Policy metadata to alter domain lifecycle directly.

## 9. Rollback/versioning

Future rollback is always a new reviewed Policy version/commit, not mutation of historical bytes or Git history rewrite.

The adapter must be able to load both before and after semantic versions sufficiently to prove rollback candidate meaning. The exact observation/retain/adjust/rollback workflow belongs to P6/P7.

## 10. Activation rule

A Policy Review kind is unavailable until its concrete adapter, canonical loader, physical operation owner, persistence path and recovery contract are implemented and registered.

No generic fallback serializes arbitrary dictionaries and calls that a Policy.

Attempting an unimplemented Project/Global Policy Review kind must fail explicitly rather than using `project.yaml` or a Review metadata file as an accidental substitute.

## 11. Architecture blocker / HUMAN

Architecture blocker: `None`.

HUMAN decision: `None`.

The lack of a current Policy subsystem is expected at P1. The safe contract is to freeze the semantic adapter hook now and defer physical schemas/owners/paths to P6/P7 rather than inventing them.