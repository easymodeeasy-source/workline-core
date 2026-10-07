"""``global-policy-change``: the one owner of Global Review policy mutation in the Workline root (P7, §16.15, §31).

A dedicated Workline-root maintenance operation. It is not ProjectSTART, not a
Workline Project mutation, not self-hosting and not a Roadmap / Phase / Work
operation: the Workline root never becomes a Project, and nothing here creates
``<workline-root>/.workline/``. The Global Policy Change Review
(``global-policy-change-v1``, :mod:`workline.review.global_policy`) produces
authorization only; this owner alone writes the Workline root and finalizes
its Git:

```text
entry          require_root_invocation -> the request (C) -> the root lock (B) -> the class B entry
               (an unconfigured Git identity STOPs here, before any effect)
freeze         full branch ref, exact base HEAD, the committed Global policy (version / digest, the
               canonical loader in materialized mode), owned-path dirt (dirty_overlap), the publication
               binding (B); committability of the whole closed effect set
mutation       the same request resumes its own pending root mutation; with none pending, canonical
               recovery discovery (the shared core) rebinds an earlier Run's IDs, or a Candidate is frozen
Candidate      read-only source snapshots -> clusters -> eligibility (or the exact rollback exception)
               -> after policy -> total compatibility proof -> Promotion Packet -> Candidate
               -> reviewer floor -> mechanical meta-verifier, all before any effect
root Review    G1 Packet + snapshot + discovery TaskInputs -> Kg1 -> discovery -> G2 -> Kg2
               -> G3 adjudication TaskInput -> Kg3 -> adjudication + meta-verifier -> G4 -> Kg4
               -> G5 seal + Receipt -> Kg5      (blocking: not_authorized at G4; HUMAN: the same canonical
                                                 HUMAN_WAIT Run at G4, R8; there is no Repair Batch)
persistence    currentness -> change record + Patch Note + exact global-policy.yaml CAS -> Kp -> C-2(Kp)
               -> exact Kp publication -> Global Policy Consumption v4 -> Km -> C-2(Km)
               -> exact Km publication -> complete      (a remote-less root: the same proofs, no push)
```

**Commits** are class B only (RB7C-5): each one is a commit tree plan built
object by object (:func:`workline.review.workcommit.build`) in an isolated
index under ``.workline-root-runtime/tmp/`` from the RECORDED effect bytes,
against its exact expected parent; the prepared commit is recorded before the
branch moves by an ``update-ref`` compare-and-swap from that parent, the ref is
read back, and only then is the real index refreshed for the commit's own
paths. Unexpected HEAD movement is never rebased, reset, amended, cherry-picked
or forced over: it is reconcile.

**Publication** happens at exactly one place, :func:`_publish`, and only after
the authorization is re-validated, the locator re-resolved and read as itself,
the destination branch read, the exact fast-forward proven, the push previewed,
the root C-2 proof of that exact commit passed and the publication barrier
cleared. The refspec is ``<exact sha>:<full ref>``; a branch tip is never
published in place of the recorded commit, and nothing is ever forced.

**Recovery** after runtime loss is only the shared discovery core
(``recovery.discover_kind_in`` over the root Review namespace); the IDs of the
one recoverable Run are rebound, never reallocated (§31.11). A change record
committed without the Consumption of its own Receipt is never adopted: its Kp /
Km identity was not durably saved, so it is reconcile (CP_EARLY L35).

There is no P5 history at the root: no Run summary, Finding history, relation
or Human-decision evidence is written, and no history function is called
(RB7C-1 (e)).
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from . import destination, gitcmd, ids, root_maintenance
from .errors import GitError, ReconcileRequired, StopError, ValidationError
from .implementation import package_directory
from .review import fsafe, gate, p4, planning, policy, publication, records, serialize, workcommit
from .review import global_policy as review_global_policy
from .review import recovery as review_recovery
from .review.committed import CommittedReviewStore, added_in_history, parse_record
from .review.hermetic import HermeticGit
from .review.namespace import ROOT_POLICY_LAYOUT, ROOT_POLICY_REVIEW_NAMESPACE
from .review.store import ReviewStore

OWNER = OPERATION = root_maintenance.OPERATION_CHANGE
OPERATION_EVALUATION = root_maintenance.OPERATION_EVALUATION

#: The ``CommitTreePlan.contract`` of every root commit (Kg1-Kg5, Kp, Km, the evaluation commit).
ROOT_COMMIT_CONTRACT = "review-v1-p7-root-commit-v1"

STATUS_APPLIED = "applied"
STATUS_NOT_AUTHORIZED = "not_authorized"
STATUS_HUMAN_WAIT = "human_wait"

# --------------------------------------------------------------------------- the P7 owner catalogue

#: The exact before-state (the committed Global policy) is not the one the Candidate was decided against.
CODE_BEFORE_STATE_CONFLICT = "review_p7_before_state_conflict"
#: After G5 and before Kp the frozen basis (Global policy, Packet evidence) went stale (§31.40).
CODE_STALE_CANDIDATE = "review_p7_stale_candidate"
#: HEAD commits no ``review-policy/global-policy.yaml``: the root is not materialized there (§31.2 / §31.3).
CODE_GLOBAL_POLICY_UNAVAILABLE = "review_p7_global_policy_unavailable"
STOP_CODES = (CODE_BEFORE_STATE_CONFLICT, CODE_STALE_CANDIDATE, CODE_GLOBAL_POLICY_UNAVAILABLE)

REASON_PERSISTED_MISMATCH = "review_p7_persisted_mismatch"
REASON_PUBLICATION_INVALID = "review_p7_publication_invalid"
REASON_RUN_UNRECOVERED = "review_p7_run_unrecovered"
REASON_RECORD_CONFLICT = "review_p7_record_conflict"
RECONCILE_REASONS = (REASON_PERSISTED_MISMATCH, REASON_PUBLICATION_INVALID, REASON_RUN_UNRECOVERED,
                     REASON_RECORD_CONFLICT)

#: Already-catalogued shared codes this owner raises unchanged (never a new spelling of them).
REUSED_CODES = ("dirty_overlap", "detached_head", "review_reviewer_failed", "review_reviewer_mismatch",
                "review_contract_invalid", "review_not_persisted", "review_persistence_unknown",
                "review_callback_unknown", "review_callback_conflict")
REUSED_REASONS = ("review_recovery_incomplete", "review_recovery_ambiguous")


def stop(code: str, message: str) -> StopError:
    """A STOP of this owner (built here so every one carries a catalogued code)."""
    if code not in STOP_CODES + REUSED_CODES:
        raise ValueError(f"not a global-policy-change STOP code: {code!r}")
    return StopError(message, code=code)


def reconcile(message: str, reason: str) -> ReconcileRequired:
    if reason not in RECONCILE_REASONS + REUSED_REASONS:
        raise ValueError(f"not a global-policy-change reconcile reason: {reason!r}")
    return ReconcileRequired(f"{message}: reconcile required", reason=reason)


def _catalogued(catalogue: Sequence[str], name: str) -> str:
    """The one entry of another P7 module's catalogue named ``name`` - raised by that module's own helper.

    The P7 one-catalogue rule: a P7 code is spelled once, in the catalogue of
    the module that owns it. This owner raises the Review semantics' codes
    (``review_global_policy``) through that module's ``stop`` / ``reconcile``
    with the value read from its catalogue, never re-spelled here.
    """
    found = [code for code in catalogue if code.endswith("_" + name)]
    if len(found) != 1:
        raise ValueError(f"the P7 Review catalogue declares {len(found)} codes named {name!r}")
    return found[0]


def _c_stop(name: str, message: str) -> StopError:
    return review_global_policy.stop(_catalogued(review_global_policy.STOP_CODES, name), message)


def _c_reconcile(message: str, name: str) -> ReconcileRequired:
    return review_global_policy.reconcile(message, _catalogued(review_global_policy.RECONCILE_REASONS, name))


def _chain_invalid(message: str) -> ReconcileRequired:
    return _c_reconcile(message, "chain_invalid")


# --------------------------------------------------------------------------- stages, notes, reservation keys

STAGE_KP = "kp"
STAGE_KM = "km"
STAGE_EVALUATION = "evaluation"
#: The root Review generation commits Kg1-Kg5, one per gate generation.
STAGE_GENERATIONS = tuple(f"kg{generation}" for generation in range(1, p4.SEAL_GENERATION + 1))

#: The frozen Candidate material (``{"material": ...}``).
NOTE_CANDIDATE = "global_policy_candidate"
#: The earlier Run a mutation rebound from canonical records after runtime loss (§31.11).
NOTE_RECOVERED = "global_policy_recovered_run"
#: Every recorded stage plan, in order (``{"order": [...], "plans": {stage: plan}}``), saved in one write so a
#: stage is decided whole before its first effect is recorded.
NOTE_STAGES = "root_stages"

#: The commit facts and the push fact this owner marks (B's frozen fact names).
FACT_PREPARED_COMMIT = "prepared_commit"
FACT_PREPARED_TREE = "prepared_tree"
FACT_REF_MOVED = "ref_moved"
FACT_PUSHED = "pushed"
_FACT_KEYS = (FACT_PREPARED_COMMIT, FACT_PREPARED_TREE, FACT_REF_MOVED, FACT_PUSHED)

#: The canonical file kinds a stage creates or replaces (B's closed effect set, less commit and push).
_FILE_EFFECTS = (
    root_maintenance.EFFECT_REVIEW_CREATE, root_maintenance.EFFECT_PACKET_CREATE,
    root_maintenance.EFFECT_CHANGE_CREATE, root_maintenance.EFFECT_PATCH_NOTE_CREATE,
    root_maintenance.EFFECT_GLOBAL_POLICY_REPLACE, root_maintenance.EFFECT_CONSUMPTION_CREATE,
    root_maintenance.EFFECT_EVALUATION_CREATE,
)

_NS = ROOT_POLICY_REVIEW_NAMESPACE
_LAYOUT = ROOT_POLICY_LAYOUT
_REGULAR = "100644"


#: The stable reservation keys of the IDs an exact write-scope path names (Amendment 4: one each per mutation; a
#: mutation is one operation). Their first allocation is made at the first open and stored with the record itself.
PACKET_KEY = "review-promotion-packet"
CHANGE_KEY = "review-global-policy-change"
EVALUATION_KEY = "review-global-policy-evaluation"


def _run_key() -> str:
    return gate.review_run_key(review_global_policy.REVIEW_KIND, review_global_policy.TARGET_IDENTITY)


# =========================================================================== public shapes

@dataclass(frozen=True)
class GlobalPolicyReview:
    """The root Review actor binding: the discovery actors and one adjudicator, each identity / version.

    The discovery actors must meet the floor the Candidate binds -
    ``max(2 | 3, pre-change Global required_slots)`` over distinct reviewer
    identity / version bindings (§31.26); the proposed after-state never selects
    the reviewers of the review authorizing it. There is no repair actor.
    """

    discovery: tuple[p4.DiscoveryBinding, ...]
    adjudicator: p4.ActorBinding


@dataclass(frozen=True)
class GlobalPolicyChangeResult:
    """How a ``global-policy-change`` invocation ended."""

    status: str
    global_policy_change_id: str
    promotion_packet_id: str
    review_run_id: str
    receipt_id: str | None
    consumption_id: str | None
    global_policy_version: int | None
    global_policy_digest: str | None
    policy_commit: str | None
    metadata_commit: str | None
    mutation_id: str
    findings: tuple[dict[str, Any], ...]
    detail: str


@dataclass(frozen=True)
class GlobalPolicyEvaluationResult:
    evaluation_id: str
    global_policy_change_id: str
    result: str
    next_action: str
    commit: str | None
    mutation_id: str


def validate_global_policy_review(review: object) -> GlobalPolicyReview:
    """The ``review`` argument, validated before the lock and before anything of the root is read."""
    if type(review) is not GlobalPolicyReview:
        raise ValidationError(f"review must be a GlobalPolicyReview, not {type(review).__name__}",
                              code="review_contract_invalid")
    problems = p4.binding_problems(review.discovery, review.adjudicator, review.adjudicator, None)
    if problems:
        raise ValidationError("invalid GlobalPolicyReview: " + "; ".join(problems), code="review_contract_invalid")
    return review


# =========================================================================== the entry and its freeze

@dataclass(frozen=True)
class _Entry:
    """What the operation froze at entry (§31.30): branch, base, the committed Global policy, the destination."""

    branch: str
    head: str
    global_policy: dict[str, Any]
    publication: Any  # root_maintenance.PublicationBinding | None (remote-less)
    #: the exact working-tree bytes of global-policy.yaml, captured at the freeze as the checkout of the committed
    #: policy (CRLF on a ``core.autocrlf`` clone); ``None`` while the path holds this mutation's own write
    global_policy_checkout: bytes | None = None

    @property
    def global_policy_digest(self) -> str:
        return policy.global_policy_digest(self.global_policy)

    @property
    def publication_record(self) -> dict[str, str] | None:
        if self.publication is None:
            return None
        return {"remote": self.publication.remote, "branch": self.publication.branch}


@dataclass
class _Op:
    root: Path
    git: HermeticGit
    lock: Any
    operation: str
    request: Any
    record: dict[str, Any]
    request_digest: str
    entry: _Entry
    review: GlobalPolicyReview | None = None

    @property
    def operation_identity(self) -> str:
        if self.operation == OPERATION:
            return review_global_policy.operation_identity(self.request_digest)
        return review_global_policy.evaluation_operation_identity(self.request_digest)


@dataclass
class _Run:
    global_policy_change_id: str
    promotion_packet_id: str
    review_run_id: str
    material: dict[str, Any]
    receipt_id: str | None
    consumption_id: str | None


def _invocation(operation: str, request_digest: str) -> dict[str, Any]:
    found = {"operation": operation, "request_digest": request_digest, "commit_contract": ROOT_COMMIT_CONTRACT}
    if operation == OPERATION:
        found["review_contract"] = review_global_policy.CONTRACT
    return found


def _owned(relative: str) -> bool:
    """Whether ``relative`` lies in the closed root write scope (§31.30 "exact owned paths")."""
    for prefix in _LAYOUT.owned_prefixes():
        if relative == prefix if not prefix.endswith("/") else relative.startswith(prefix):
            return True
    return False


def _payload(effect: Mapping[str, Any]) -> Mapping[str, Any]:
    found = effect.get("payload")
    return found if isinstance(found, Mapping) else {}


def _facts(effect: Mapping[str, Any]) -> Mapping[str, Any]:
    """The facts B recorded on an effect through ``mark_effect``."""
    found = effect.get("facts")
    if isinstance(found, Mapping):
        return found
    return {key: effect[key] for key in _FACT_KEYS if key in effect}


def _own_pending(root: Path, invocation: Mapping[str, Any]) -> dict[str, Any] | None:
    """The pending root mutation of exactly this invocation, read without the mutation API (it resumes)."""
    for record in root_maintenance.pending_mutations(root):
        if record.get("invocation") == dict(invocation):
            return dict(record)
    return None


def _written_paths(record: Mapping[str, Any] | None) -> set[str]:
    """The paths the file effects of a pending root mutation record name (its own uncommitted writes)."""
    if record is None:
        return set()
    found: set[str] = set()
    for effect in record.get("effects") or []:
        if isinstance(effect, Mapping) and effect.get("kind") in _FILE_EFFECTS:
            path = _payload(effect).get("path")
            if isinstance(path, str):
                found.add(path)
    return found


def _freeze_entry(root: Path, pending: Mapping[str, Any] | None) -> _Entry:
    """§31.30 at entry: before any canonical effect, and before a pending mutation is resumed."""
    branch = gitcmd.current_branch_ref(root)
    head = gitcmd.head_commit(root)
    if not branch or not head:
        raise stop("detached_head", "the Workline root's HEAD is on no branch or has no commit, so the root policy "
                                    "change cannot bind its branch and base: STOP")
    own = _written_paths(pending)
    dirt = sorted(path for path in gitcmd.dirty_paths(root) if _owned(path) and path not in own)
    if dirt:
        raise stop("dirty_overlap", "pre-existing changes overlap the root policy write scope and cannot be separated "
                                    f"safely: {', '.join(dirt)}; nothing is written")
    clean = policy.GLOBAL_POLICY_REL not in own
    global_policy = _committed_global_policy(root, head, loader=clean)
    checkout = None
    if clean:
        checkout = _working_bytes_of(root, policy.GLOBAL_POLICY_REL)
        if checkout is None or checkout.replace(b"\r\n", b"\n") != policy.global_policy_bytes(global_policy):
            raise stop(CODE_BEFORE_STATE_CONFLICT, f"the working tree's {policy.GLOBAL_POLICY_REL} is not the checkout "
                                                   "of the committed Global policy; nothing is written")
    return _Entry(branch, head, global_policy, root_maintenance.publication_binding(root), checkout)


def _working_bytes_of(root: Path, relative: str) -> bytes | None:
    """The exact bytes the working tree holds at ``relative``, read without following anything; ``None`` if absent."""
    parts = relative.split("/")
    try:
        chain = fsafe.walk(root, parts[:-1])
        if chain is None:
            return None
        with chain:
            return chain.last.read_file(parts[-1])
    except ValidationError as exc:
        raise stop(CODE_BEFORE_STATE_CONFLICT, f"{relative} cannot be read without following an indirection ({exc}); "
                                               "nothing is written") from exc


def _committed_global_policy(root: Path, commit: str, *, loader: bool) -> dict[str, Any]:
    """The Global policy ``commit`` holds, strictly; with ``loader``, also what the canonical loader reads now.

    Only a materialized Global policy can be changed (§31.2): the initial
    version is the implementation's tracked artifact, never written here.
    """
    raw = gitcmd.blob_at(root, commit, policy.GLOBAL_POLICY_REL)
    if raw is None:
        raise stop(CODE_GLOBAL_POLICY_UNAVAILABLE,
                   f"{commit} holds no {policy.GLOBAL_POLICY_REL}: the Global policy is not materialized, so no Global "
                   "Policy Change or evaluation can begin; nothing is written")
    found = policy.parse_global_policy_bytes(raw, f"{policy.GLOBAL_POLICY_REL} at {commit}")
    if loader:
        baseline = policy.load_global_baseline(root)
        if baseline.source_mode != policy.SOURCE_MODE_MATERIALIZED \
                or baseline.global_policy_identity != policy.global_policy_digest(found):
            raise stop(CODE_BEFORE_STATE_CONFLICT,
                       f"the canonical loader reads {baseline.source_mode} Global policy {baseline.global_policy_identity}, "
                       f"not the materialized policy {commit} commits; nothing is written")
    return found


def _probe(kind: str) -> str:
    """A well-formed ID of ``kind`` naming nothing: the committability preflight asks about shapes, not records."""
    return f"{ids.PREFIXES[kind]}_{'0' * 26}"


def _closed_effect_set(operation: str) -> list[str]:
    """Every path family the operation may write, as the directories and one exact record path of each (RB7C-9)."""
    if operation == OPERATION_EVALUATION:
        return sorted({_LAYOUT.evaluations_dir + "/", _LAYOUT.global_evaluation_rel(_probe("review_global_policy_evaluation"))})
    run = _probe("review_run")
    digest = "0" * 64
    return sorted({
        _LAYOUT.review_dir + "/", _LAYOUT.promotion_packets_dir + "/", _LAYOUT.changes_dir + "/",
        _LAYOUT.patch_notes_dir + "/", _LAYOUT.global_policy_rel,
        _LAYOUT.promotion_packet_rel(_probe("review_promotion_packet")),
        _LAYOUT.global_change_rel(_probe("review_global_policy_change")),
        _LAYOUT.patch_note_rel(_probe("review_global_policy_change")),
        _NS.gate_rel(run, 1), _NS.candidate_snapshot_rel(digest), _NS.task_input_rel(_probe("review_task")),
        _NS.report_rel(digest), _NS.adjudication_rel(run), _NS.receipt_rel(_probe("review_receipt")),
        _NS.consumption_rel(_probe("review_consumption")),
    })


def _enter(workline_root: Path, operation: str, request: Any, record: dict[str, Any], request_digest: str,
           review: GlobalPolicyReview | None, lock: Any) -> tuple[_Op, dict[str, Any] | None]:
    git = root_maintenance.enter_git(lock)  # class B entry: an unconfigured identity STOPs here (N-3)
    root = Path(lock.root)
    pending = _own_pending(root, _invocation(operation, request_digest))
    entry = _freeze_entry(root, pending)
    root_maintenance.require_committable(root, _closed_effect_set(operation))
    return _Op(root, git, lock, operation, request, record, request_digest, entry, review), pending


# =========================================================================== global-policy-change

def change_global_policy(workline_root: Path, request: "review_global_policy.GlobalPolicyChangeRequest", *,
                         review: GlobalPolicyReview) -> GlobalPolicyChangeResult:
    """Propose, review and - when authorized - persist one Global Policy Change (§16.15-§16.21, §31).

    The same request resumes its own unfinished root mutation with the same
    Packet, change, Run and task IDs; after runtime loss it rediscovers the
    same canonical Run; another request meets the pending one and is refused
    (single-writer root maintenance).
    """
    root_maintenance.require_root_invocation()
    record = review_global_policy.request_record(request)
    validate_global_policy_review(review)
    digest = review_global_policy.request_digest(record)
    with root_maintenance.root_operation(Path(workline_root), OPERATION, {"request_digest": digest}) as lock:
        op, pending = _enter(Path(workline_root), OPERATION, request, record, digest, review, lock)
        mutation = _open_change(op, pending)
        return _run(op, mutation)


def _change_scope(promotion_packet_id: str, global_policy_change_id: str) -> list[str]:
    return sorted([
        _LAYOUT.global_policy_rel, _LAYOUT.promotion_packet_rel(promotion_packet_id),
        _LAYOUT.global_change_rel(global_policy_change_id), _LAYOUT.patch_note_rel(global_policy_change_id),
        _LAYOUT.review_dir + "/",
    ])


def _open(op: _Op, *, write_scope: Sequence[str], reserved: Mapping[str, str] | None = None,
          rebind: Mapping[str, str] | None = None) -> Any:
    """A NEW root mutation (Amendments 4-5): the first allocation of its scope IDs (``reserved``), or - a recovery
    open only - the canonical IDs reconstructed from committed records (``rebind``); never both. The committability
    preflight runs over the exact scope first, so nothing is opened for a scope the root would not commit."""
    root_maintenance.require_committable(op.root, list(write_scope))
    return root_maintenance.open_mutation(
        op.lock, _invocation(op.operation, op.request_digest), branch=op.entry.branch, base=op.entry.head,
        global_policy_version=int(op.entry.global_policy["global_policy_version"]),
        global_policy_digest=op.entry.global_policy_digest, write_scope=list(write_scope),
        publication=op.entry.publication_record, rebind=None if rebind is None else dict(rebind),
        reserved=None if reserved is None else dict(reserved),
    )


def _reopen(op: _Op, pending: Mapping[str, Any]) -> Any:
    """Resume the pending root mutation of this invocation, with exactly the values it was opened with."""
    frozen = pending.get("global_policy") or {}
    mutation = root_maintenance.open_mutation(
        op.lock, _invocation(op.operation, op.request_digest), branch=str(pending.get("branch")),
        base=str(pending.get("base")), global_policy_version=frozen.get("version"),
        global_policy_digest=frozen.get("digest"), write_scope=list(pending.get("write_scope") or []),
        publication=pending.get("publication"),
    )
    if mutation.mutation_id != pending.get("mutation_id"):
        raise reconcile(f"the pending root mutation {pending.get('mutation_id')} of this request was not the one "
                        f"resumed ({mutation.mutation_id})", REASON_RECORD_CONFLICT)
    _require_resume_basis(op, mutation)
    return mutation


def _require_resume_basis(op: _Op, mutation: Any) -> None:
    """Amendment 8: a resumed mutation, checked before any further effect (§31.30 / §31.39).

    * HEAD is on the record's own full branch ref;
    * HEAD is the exact expected parent of the next step - the last own commit
      whose ref move is recorded, else the frozen base - or that step's own
      commit when the step's prepared commit (recorded durably BEFORE its ref
      moved, on exactly that parent) is already what the branch names: the
      move landed and only its record did not (RB7BL-1). Anything else is
      reconcile; nothing is rebased, cherry-picked, amended or reset;
    * the working-tree ``global-policy.yaml``, LF-normalized, is the frozen
      before policy until the Kp stage is decided, the reviewed after policy
      once Kp's ref moved, and one of the two in between (the one exact CAS of
      the recorded stage decides which);
    * the root resolves the frozen publication (and re-checks it before every push).
    """
    record = mutation.record
    if op.entry.branch != record.get("branch"):
        raise reconcile(f"root mutation {mutation.mutation_id} is bound to {record.get('branch')}, and HEAD is on "
                        f"{op.entry.branch}; nothing is rebased onto another branch", REASON_RECORD_CONFLICT)
    expected = _expected_parent(mutation)
    allowed = {expected}
    for effect in mutation.effects():
        facts = _facts(effect)
        if effect.get("kind") == root_maintenance.EFFECT_COMMIT and facts.get(FACT_REF_MOVED) is not True \
                and facts.get(FACT_PREPARED_COMMIT) and _payload(effect).get("parent") == expected \
                and _prepared_object_problem(op, facts, _payload(effect)) is None:
            allowed.add(str(facts[FACT_PREPARED_COMMIT]))
    if op.entry.head not in allowed:
        raise reconcile(f"HEAD is {op.entry.head}, not the commit root mutation {mutation.mutation_id} expects "
                        f"({', '.join(sorted(allowed))}); unexpected HEAD movement is never rebased, reset or amended",
                        REASON_RECORD_CONFLICT)
    _require_resumed_global_policy(op, mutation)
    if op.entry.publication_record != record.get("publication"):
        raise reconcile(f"root mutation {mutation.mutation_id} was frozen with publication {record.get('publication')}, "
                        f"and the root now resolves {op.entry.publication_record}; nothing is published",
                        REASON_PUBLICATION_INVALID)


def _require_resumed_global_policy(op: _Op, mutation: Any) -> None:
    """The working-tree Global policy of a resumed mutation is the one its recorded stage implies (Amendment 8)."""
    frozen = str((mutation.record.get("global_policy") or {}).get("digest"))
    admitted = {frozen}
    if _stage_planned(mutation, STAGE_KP):
        material = (mutation.note(NOTE_CANDIDATE) or {}).get("material") or {}
        after = str(material.get("after_global_policy_digest"))
        found = _commit_effect(mutation, STAGE_KP)
        admitted = {after} if found is not None and _facts(found[1]).get(FACT_REF_MOVED) is True else {frozen, after}
    raw = _working_bytes_of(op.root, policy.GLOBAL_POLICY_REL)
    try:
        held = None if raw is None else policy.global_policy_digest(
            policy.parse_global_policy_bytes(raw.replace(b"\r\n", b"\n"), policy.GLOBAL_POLICY_REL))
    except ValidationError:
        held = None
    if held not in admitted:
        raise reconcile(f"the working tree's {policy.GLOBAL_POLICY_REL} is not the Global policy root mutation "
                        f"{mutation.mutation_id} left it at; nothing is written over it", REASON_RECORD_CONFLICT)


def _resumed_candidate(op: _Op, mutation: Any) -> None:
    """A resumed mutation that has not saved its Candidate yet gets it now - the same one, never another.

    A crash between the open and the Candidate note leaves the reservations
    only. When the reserved Run already has a gate chain (a recovered Run), the
    Candidate is that Run's committed snapshot, held to this request and these
    reservations; otherwise nothing canonical exists yet and the Candidate is
    frozen on the same reservations.
    """
    if mutation.note(NOTE_CANDIDATE) is not None:
        return
    with _abandoned_on_stop(mutation):
        run_id = mutation.reserved(_run_key())
        reader = _reader(op)
        chain = None if run_id is None else reader.gate_chain(run_id)
        if chain is None:
            _freeze(op, mutation)
            return
        first = chain.generations[0]
        material = serialize.canonical_data(dict(reader.read_candidate_snapshot(first.candidate_hash).material or {}))
        if first.operation_identity != op.operation_identity \
                or material.get("promotion_packet_id") != mutation.reserved(PACKET_KEY) \
                or material.get("global_policy_change_id") != mutation.reserved(CHANGE_KEY):
            raise reconcile(f"root mutation {mutation.mutation_id} reserved Run {run_id}, whose Candidate is not this "
                            "request's", REASON_RECORD_CONFLICT)
        mutation.set_note(NOTE_CANDIDATE, {"material": material})


def _open_change(op: _Op, pending: Mapping[str, Any] | None) -> Any:
    if pending is not None:
        mutation = _reopen(op, pending)
        _resumed_candidate(op, mutation)
        return mutation
    _require_no_stranded_change(op)
    found = _discover(op)
    if found is None:
        # The exact Packet / change / Patch Note paths name the IDs: their first allocation is made right before the
        # open and stored by it (Amendments 4-5); a crash before the open leaves nothing, and a retry allocates anew.
        packet_id = ids.new_id("review_promotion_packet")
        change_id = ids.new_id("review_global_policy_change")
        mutation = _open(op, write_scope=_change_scope(packet_id, change_id),
                         reserved={PACKET_KEY: packet_id, CHANGE_KEY: change_id})
        with _abandoned_on_stop(mutation):
            _freeze(op, mutation)
        return mutation
    recovered = _recover(op, found)
    material = recovered.material
    mutation = _open(op, write_scope=_change_scope(str(material["promotion_packet_id"]),
                                                   str(material["global_policy_change_id"])),
                     rebind=recovered.bindings)  # §31.11: the reconstructed canonical IDs, rebound, never reallocated
    with _abandoned_on_stop(mutation):
        mutation.set_note(NOTE_RECOVERED, {"review_run_id": recovered.review_run_id})
        mutation.set_note(NOTE_CANDIDATE, {"material": material})
        if not recovered.waiting and not recovered.sealed:
            receipt_id = mutation.reserve_id(gate.review_receipt_key(recovered.review_run_id, p4.SEAL_GENERATION),
                                             "review_receipt")
            mutation.reserve_id(gate.review_consumption_key(receipt_id), "review_consumption")
        elif recovered.sealed:
            receipt_id = recovered.bindings[gate.review_receipt_key(recovered.review_run_id, p4.SEAL_GENERATION)]
            mutation.reserve_id(gate.review_consumption_key(receipt_id), "review_consumption")
    return mutation


@contextmanager
def _abandoned_on_stop(mutation: Any) -> Iterator[None]:
    """A STOP before the mutation's first effect abandons it: nothing canonical names what it reserved."""
    try:
        yield
    except StopError:
        if not mutation.effects():
            mutation.abandon()
        raise


@contextmanager
def _released_when_stale(mutation: Any) -> Iterator[None]:
    """A before-state that moved never strands the single-writer root mutation (the ORCH-RB6-1-R1 analogue).

    Every step re-proves the exact before-state before it records anything.
    When it moved, an effect-free mutation is abandoned; one whose recorded
    stages are all committed is completed - its committed generations stay
    canonical evidence, a retry of the same request finds that Run by canonical
    discovery and is refused the same way before anything is opened, and
    another request is a new Candidate. A mutation with an unfinished stage is
    left pending: its own resume owns that window.
    """
    try:
        yield
    except StopError as exc:
        if exc.code in (CODE_BEFORE_STATE_CONFLICT, CODE_STALE_CANDIDATE):
            if not mutation.effects():
                mutation.abandon()
            elif not _unfinished_stages(mutation):
                mutation.complete()
        raise


def _run(op: _Op, mutation: Any) -> GlobalPolicyChangeResult:
    run = _recorded_run(op, mutation)
    with _released_when_stale(mutation):
        return _review_and_persist(op, mutation, run)


def _recorded_run(op: _Op, mutation: Any) -> _Run:
    frozen = mutation.note(NOTE_CANDIDATE) or {}
    material = frozen.get("material") if isinstance(frozen, Mapping) else None
    packet_id = mutation.reserved(PACKET_KEY)
    change_id = mutation.reserved(CHANGE_KEY)
    run_id = mutation.reserved(_run_key())
    if not isinstance(material, Mapping) or packet_id is None or change_id is None or run_id is None \
            or material.get("promotion_packet_id") != packet_id or material.get("global_policy_change_id") != change_id:
        raise reconcile(f"root mutation {mutation.mutation_id} does not hold its frozen Candidate and its reserved "
                        "Packet, change and Run identities", REASON_RECORD_CONFLICT)
    receipt_id = mutation.reserved(gate.review_receipt_key(run_id, p4.SEAL_GENERATION))
    consumption_id = None if receipt_id is None else mutation.reserved(gate.review_consumption_key(receipt_id))
    return _Run(change_id, packet_id, run_id, dict(material), receipt_id, consumption_id)


# --------------------------------------------------------------------------- the Candidate freeze (before any effect)

def _freeze(op: _Op, mutation: Any) -> None:
    """Sources, eligibility, after policy, proof, Packet and Candidate; reviewer floor and meta-verifier first."""
    before = op.entry.global_policy
    record = op.record
    packet_id = mutation.reserve_id(PACKET_KEY, "review_promotion_packet")  # the first-open reservations
    change_id = mutation.reserve_id(CHANGE_KEY, "review_global_policy_change")
    _require_exact_rollback(op, before)
    snapshots = _source_snapshots(op)
    clusters = review_global_policy.clustering(snapshots)
    eligibility = review_global_policy.eligibility(record, snapshots, clusters)
    if not eligibility.get("eligible"):
        problems = ", ".join(str(item) for item in eligibility.get("problems") or ()) or "no eligibility basis"
        raise _c_stop("not_eligible", f"the promotion is not mechanically eligible ({problems}); nothing is reviewed "
                                      "or written")
    # an unchanged setting never reaches here: C refuses it (review_p7_request_invalid, Amendment 10 item 2)
    after = review_global_policy.after_global_policy(before, record)
    problem = policy.global_policy_successor_problem(before, after)
    if problem is not None:
        raise reconcile(f"the proposed Global policy is not the exact successor of the current one: {problem}",
                        REASON_RECORD_CONFLICT)
    proof = review_global_policy.compatibility_proof(before, after)
    packet = review_global_policy.promotion_packet(
        record, promotion_packet_id=packet_id, global_policy_change_id=change_id, before_global=before,
        after_global=after, snapshots=snapshots, clusters=clusters, eligibility=eligibility, proof=proof,
    )
    material = review_global_policy.candidate_material(packet, before, after, proof)
    _require_reviewers(op, material)
    _require_meta_verified(op, material, source_problems=(), base=str(mutation.record["base"]),
                           publication=mutation.record.get("publication"))
    run_id = mutation.reserve_id(_run_key(), "review_run")
    for binding in _discovery_bindings(op):
        mutation.reserve_id(gate.review_task_key(run_id, binding.task_slot), "review_task")
    receipt_id = mutation.reserve_id(gate.review_receipt_key(run_id, p4.SEAL_GENERATION), "review_receipt")
    mutation.reserve_id(gate.review_consumption_key(receipt_id), "review_consumption")
    mutation.set_note(NOTE_CANDIDATE, {"material": serialize.canonical_data(dict(material))})


def _discovery_bindings(op: _Op) -> list[p4.DiscoveryBinding]:
    assert op.review is not None
    return sorted(op.review.discovery, key=lambda binding: binding.viewpoint)


def _source_snapshot(source: Any, evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One read-only source snapshot under a bounded B0/B1 witness: one retry, else unavailable (§31.16).

    The source is read only through committed objects at one exact HEAD; no
    source lock, mutation or write is ever made (§31.14).
    """
    for _attempt in range(2):
        head = gitcmd.head_commit(Path(source.root))
        if head is None:
            break
        found = review_global_policy.source_snapshot(source.source_id, CommittedReviewStore(Path(source.root), head),
                                                     head, evidence)
        if gitcmd.head_commit(Path(source.root)) == head:
            return found
    raise _c_stop("source_unavailable", f"source {source.source_id} has no stable HEAD across a bounded extraction "
                                        "(one retry); it is unavailable for this attempt and nothing is written")


def _source_snapshots(op: _Op) -> list[dict[str, Any]]:
    evidence = op.request.evidence or {}
    return [_source_snapshot(source, tuple(evidence.get(source.source_id, ()))) for source in op.request.sources]


def _source_problems(op: _Op, material: Mapping[str, Any]) -> list[str]:
    """Whether the exact bound source evidence still holds (§31.16): the frozen witness against a fresh one."""
    frozen = {str(item["source_id"]): item["snapshot"]
              for item in material["promotion_packet"]["source_snapshots"]}
    evidence = op.request.evidence or {}
    supplied = {source.source_id for source in op.request.sources}
    problems = [f"source {source_id} is not supplied to this invocation" for source_id in sorted(set(frozen) - supplied)]
    for source in op.request.sources:
        if source.source_id not in frozen:
            problems.append(f"source {source.source_id} is not one the Packet froze")
            continue
        try:
            now = _source_snapshot(source, tuple(evidence.get(source.source_id, ())))
        except StopError as exc:
            problems.append(f"source {source.source_id}: {exc}")
            continue
        # unrelated HEAD movement does not invalidate; the bound record digests and the Profile witness must hold
        problem = review_global_policy.witness_problem(review_global_policy.source_witness(frozen[source.source_id]),
                                                       review_global_policy.source_witness(now))
        if problem is not None:
            problems.append(problem)
    return problems


def _committed_record(op: _Op, commit: str, relative: str, parse: Callable[[object, str], dict[str, Any]]
                      ) -> dict[str, Any] | None:
    raw = gitcmd.blob_at(op.root, commit, relative)
    if raw is None:
        return None
    data, _ = serialize.parse_canonical(raw, f"{relative} at {commit}")
    return parse(data, f"{relative} at {commit}")


def _require_exact_rollback(op: _Op, before: Mapping[str, Any]) -> None:
    """§31.20 at the freeze: a request naming the exact-rollback exception proves it over the committed records.

    The exception (no fresh cross-Project trend) stands only on the exact
    change it rolls back and the committed evaluation proving that change's
    frozen rollback threshold fired; anything else is
    ``review_p7_rollback_inexact`` before anything is reserved or written. A
    rollback that does not name the exception meets ordinary eligibility by
    its actual movement.
    """
    change_id = op.record.get("rollback_of")
    if change_id is None:
        return
    evaluation_id = op.record.get("rollback_evaluation_id")
    head = op.entry.head
    change = _canonical_blob(op, head, _LAYOUT.global_change_rel(str(change_id)))
    evaluation = None if evaluation_id is None else _canonical_blob(
        op, head, _LAYOUT.global_evaluation_rel(str(evaluation_id)))
    if change is None or evaluation is None:
        raise _c_stop("rollback_inexact", f"the exact-rollback exception names {change_id} / {evaluation_id}, and HEAD "
                                          "does not commit both records; nothing is reviewed or written")
    problem = review_global_policy.exact_rollback_problem(op.record, before, change, evaluation)
    if problem is not None:
        raise _c_stop("rollback_inexact", f"the exact-rollback exception does not apply: {problem}; a non-exact "
                                          "rollback follows ordinary eligibility by its actual direction")


def _require_reviewers(op: _Op, material: Mapping[str, Any]) -> None:
    """§31.26: the invocation's discovery actors meet the Candidate's floor, distinct; the adjudicator apart."""
    assert op.review is not None
    problem = review_global_policy.reviewer_floor_problem(op.review.discovery, op.review.adjudicator,
                                                          int(material["required_discovery_slots"]))
    if problem is not None:
        raise _c_stop("reviewer_floor_unmet", f"{problem}; the root Review launches nothing and nothing is written")


def _current_global_digest(op: _Op) -> str:
    head = gitcmd.head_commit(op.root)
    if head is None:
        raise stop("detached_head", "the Workline root's HEAD names no commit: STOP")
    return policy.global_policy_digest(_committed_global_policy(op.root, head, loader=False))


def _canonical_blob(op: _Op, commit: str, relative: str) -> dict[str, Any] | None:
    """The canonical mapping ``commit`` holds at ``relative`` (exact blob, then canonical parse), or ``None``."""
    raw = gitcmd.blob_at(op.root, commit, relative)
    return None if raw is None else serialize.parse_canonical(raw, f"{relative} at {commit}")[0]


def _rollback_facts(op: _Op, material: Mapping[str, Any], base: str) -> tuple[Any, Any]:
    """Amendment 7: the stored change and evaluation an exact-rollback exception names, from committed objects at
    the frozen ``base``; ``(None, None)`` when the exception is not used."""
    exception = (material.get("promotion_packet") or {}).get("rollback_exception")
    if not exception:
        return None, None
    return (_canonical_blob(op, base, _LAYOUT.global_change_rel(str(exception["global_policy_change_id"]))),
            _canonical_blob(op, base, _LAYOUT.global_evaluation_rel(str(exception["evaluation_id"]))))


def _publication_ready(op: _Op, frozen: Mapping[str, Any] | None) -> bool | None:
    """§31.28 "root publication readiness where required", read NOW against the frozen binding.

    ``None`` for a root with no remote that was frozen remote-less; ``True``
    when the root's current authorized binding is exactly the frozen one;
    ``False`` otherwise - a remote added after a remote-less freeze, a
    removed remote, another remote or branch. A remote whose authorization
    is absent or no longer holds STOPs right here (``publication_binding``),
    before anything the readiness gates is written.
    """
    binding = root_maintenance.publication_binding(op.root)
    if binding is None:
        return None if frozen is None else False
    return frozen is not None and {"remote": binding.remote, "branch": binding.branch} == dict(frozen)


def _require_meta_verified(op: _Op, material: Mapping[str, Any], *, source_problems: Sequence[str],
                           base: str, publication: Mapping[str, Any] | None) -> None:
    """§31.28: every mechanical item, whatever any reviewer said; external approval never overrides one.

    ``base`` is the mutation's frozen base and ``publication`` its frozen
    binding (the entry freeze's before it is open): the exact-rollback
    records are read from committed objects at ``base``, and the publication
    readiness is re-derived now against ``publication``.
    """
    rollback_change, rollback_evaluation = _rollback_facts(op, material, base)
    facts = {
        "current_before_global_digest": _current_global_digest(op),
        "sources_current": not source_problems,
        "source_problems": list(source_problems),
        "publication_ready": _publication_ready(op, publication),
        "rollback_change": rollback_change,
        "rollback_evaluation": rollback_evaluation,
    }
    # review_p7_meta_verifier_failed, naming the first failed item; nothing is written
    review_global_policy.require_meta_verifier(material, facts)


def _require_before_state(op: _Op, material: Mapping[str, Any], *, code: str = CODE_BEFORE_STATE_CONFLICT) -> None:
    """The exact committed Global policy the Candidate was decided against still holds - or fail closed."""
    if _current_global_digest(op) != material.get("before_global_policy_digest"):
        raise stop(code, "the committed Global policy is no longer the exact before-state the Global Policy Change "
                         "Candidate was decided against; nothing is written or published, and a changed proposal is "
                         "a new Candidate")


# --------------------------------------------------------------------------- runtime-loss recovery (§31.29, RB7C-2)

def _reader(op: _Op) -> ReviewStore:
    return ReviewStore.for_namespace(op.root, _NS)


def _committed_consumptions(op: _Op) -> list[Any]:
    """Every committed Consumption of the root: HEAD's tree and every one HEAD's history added (never the working tree)."""
    head = gitcmd.head_commit(op.root)
    if head is None:
        return []
    found = list(CommittedReviewStore(op.root, head, namespace=_NS).consumptions())
    for adding, names in added_in_history(op.root, head, [_NS.consumptions_dir]):
        for name in names:
            raw = gitcmd.blob_at(op.root, adding, name)
            if raw is None:
                raise reconcile(f"the Consumption {name} added by {adding} cannot be read", "review_recovery_incomplete")
            consumption, _ = parse_record(raw, f"{name} at {adding}", records.consumption_from_record)
            found.append(consumption)
    return found


def _consumed_by(consumptions: Sequence[Any], receipt_id: str, change_id: str | None = None) -> bool:
    for found in consumptions:
        if isinstance(found, records.GlobalPolicyConsumption) and str(found.receipt_id) == receipt_id:
            if change_id is None or found.persisted_global_policy.get("global_policy_change_id") == change_id:
                return True
    return False


def _require_no_stranded_change(op: _Op) -> None:
    """No root mutation opens - a change or an evaluation (Amendment 12) - while a committed change record has no
    Consumption of its own Receipt.

    Such a change is a Kp whose identity was never durably saved: it is never
    inferred from Git history, never published and never built upon -
    :data:`REASON_RUN_UNRECOVERED`, the manual reconciliation boundary.
    """
    head = op.entry.head
    directory = _LAYOUT.changes_dir
    changes: dict[str, str | None] = {}
    blobs: list[tuple[str, bytes | None]] = []
    listed = gitcmd.tree_entries(op.root, head, [directory])
    if listed is None:
        raise reconcile(f"Git cannot list {directory} at {head}", "review_recovery_incomplete")
    for entry in listed:
        blobs.append((entry.path, gitcmd.read_blob(op.root, entry.oid)))
    for adding, names in added_in_history(op.root, head, [directory]):
        for name in names:
            blobs.append((name, gitcmd.blob_at(op.root, adding, name)))
    for relative, raw in blobs:
        change_id = relative.rsplit("/", 1)[-1].removesuffix(".yaml")
        try:
            data, _ = serialize.parse_canonical(raw or b"", relative)
            changes[change_id] = str(review_global_policy.parse_change_record(data, relative)["receipt_id"])
        except (ValidationError, KeyError):
            changes.setdefault(change_id, None)
    # a change a pending root mutation reserved is that mutation's, with its Kp identity durably recorded: the
    # single-writer refusal (review_p7_root_mutation_conflict) reports that state, never the reconciliation boundary
    for record in root_maintenance.pending_mutations(op.root):
        owned = (record.get("reserved_ids") or {}).get(CHANGE_KEY)
        if isinstance(owned, str):  # an evaluation mutation reserves no change
            changes.pop(owned, None)
    if not changes:
        return
    consumptions = _committed_consumptions(op)
    stranded = sorted(change_id for change_id, receipt in changes.items()
                      if receipt is None or not _consumed_by(consumptions, receipt, change_id))
    if stranded:
        raise reconcile(f"Global policy change {', '.join(stranded)} is committed and has no Global Policy Consumption "
                        "of its own Receipt: its policy commit identity was never durably saved, so it is neither "
                        "inferred from Git history nor built upon", REASON_RUN_UNRECOVERED)


def _adapter(op: _Op) -> review_recovery.RecoveryAdapter:
    """The root kind policy around the shared discovery core: the Review semantics' adapter (RB7C-2).

    No Packet / Candidate is bound yet when discovery runs (that is why it
    runs: the runtime record that held them is gone), so the adapter binds
    none and proves each matching Run's own Packet / Candidate identity; the
    operation identity the core matched on is this request's, and
    :func:`_recover` re-proves the recovered Candidate against the request.
    ``consumed`` reads committed Global Policy Consumptions only.
    """
    consumptions = _committed_consumptions(op)
    return review_global_policy.recovery_adapter(
        promotion_packet_id=None, candidate_hash=None,
        consumed=lambda receipt_id: _consumed_by(consumptions, str(receipt_id)),
    )


def _discover(op: _Op) -> Any:
    """Canonical recovery discovery of this request's earlier root Run - the shared core, nothing else (§31.29)."""
    return review_recovery.discover_kind_in(
        op.root, _NS, review_global_policy.REVIEW_KIND, op.operation_identity, _adapter(op),
        pending=lambda review_run_id: root_maintenance.pending_for_run(op.root, review_run_id),
    ).recoverable


@dataclass(frozen=True)
class _Recovered:
    review_run_id: str
    material: dict[str, Any]
    bindings: dict[str, str]
    waiting: bool
    sealed: bool


def _human_wait(reader: ReviewStore, chain: Any) -> bool:
    if chain.latest.generation != p4.ADJUDICATION_SETTLE_GENERATION:
        return False
    outcome = reader.read_adjudication(chain.review_run_id).outcome
    return review_global_policy.g4_outcome(chain, outcome) == review_global_policy.OUTCOME_HUMAN_WAIT


def _require_request_material(op: _Op, material: Mapping[str, Any]) -> None:
    """The recovered Candidate's Packet proposes what this request proposes."""
    packet = material.get("promotion_packet") or {}
    for name in ("policy_surface_id", "direction", "after_setting", "generalized_mechanism_id"):
        if name in op.record and packet.get(name) != op.record[name]:
            raise reconcile(f"the recovered root Review Run's Packet {name} is not this request's", REASON_RECORD_CONFLICT)


def _recover(op: _Op, found: Any) -> _Recovered:
    """The one recoverable earlier Run, re-proven before anything is bound; its canonical IDs, never new ones.

    R8: a Run at canonical G4 HUMAN_WAIT is recovered as that same Run and is
    not re-judged against the current state or the invocation's actors - it
    authorizes, launches and writes nothing; the owner returns ``human_wait``.
    Any other Run re-proves the exact before-state, the reviewer floor and the
    mechanical meta-verifier first: a moved Global policy is
    :data:`CODE_BEFORE_STATE_CONFLICT` with nothing opened.
    """
    chain = found.chain
    first = chain.generations[0]
    run_id = str(found.review_run_id)
    material = serialize.canonical_data(dict(found.material or {}))
    if first.review_kind != review_global_policy.REVIEW_KIND \
            or first.target_identity != review_global_policy.TARGET_IDENTITY \
            or first.operation_identity != op.operation_identity \
            or review_global_policy.candidate_hash(material) != first.candidate_hash:
        raise reconcile(f"the recoverable root Review Run {run_id} is not this request's Candidate", REASON_RECORD_CONFLICT)
    _require_request_material(op, material)
    reader = _reader(op)
    try:
        waiting = _human_wait(reader, chain)
    except ValidationError as exc:
        raise reconcile(f"root Review Run {run_id}'s adjudication does not read: {exc}", "review_recovery_incomplete")
    if not waiting:
        _require_reviewers(op, material)
        _require_before_state(op, material)
        _require_meta_verified(op, material, source_problems=_source_problems(op, material), base=op.entry.head,
                               publication=op.entry.publication_record)
    bindings = {
        PACKET_KEY: str(material["promotion_packet_id"]),
        CHANGE_KEY: str(material["global_policy_change_id"]),
        _run_key(): run_id,
    }
    for task in first.accepted_tasks:
        bindings[gate.review_task_key(run_id, str(task["task_slot"]))] = str(task["task_id"])
    for generation in chain.generations[1:]:
        for task in generation.accepted_tasks:
            if task["task_slot"] == p4.SLOT_ADJUDICATOR:
                bindings[gate.review_task_key(run_id, p4.SLOT_ADJUDICATOR)] = str(task["task_id"])
    sealed = bool(chain.latest.sealed and chain.latest.receipt_id)
    if sealed:
        bindings[gate.review_receipt_key(run_id, p4.SEAL_GENERATION)] = str(chain.latest.receipt_id)
    return _Recovered(run_id, dict(material), bindings, waiting, sealed)


# --------------------------------------------------------------------------- the root Review driver (G1-G5)

def _review_and_persist(op: _Op, mutation: Any, run: _Run) -> GlobalPolicyChangeResult:
    while True:
        _settle(op, mutation)
        reader = _reader(op)
        chain = reader.gate_chain(run.review_run_id)
        latest = 0 if chain is None else chain.latest.generation
        if chain is not None:
            problems = p4.chain_problems(chain)
            if problems or p4.shape_of(chain) == p4.SHAPE_REPAIR:
                raise _chain_invalid(f"root Review Run {run.review_run_id}: " + "; ".join(problems or ["a repair shape"]))
        if latest == 0:
            _accept(op, mutation, run)
        elif latest == 1:
            _launch_discovery(op, mutation, run, chain)
        elif latest == 2:
            if any(task["status"] != records.TASK_SETTLED_OK for task in chain.latest.settled_tasks):
                return _finish(op, mutation, run, STATUS_NOT_AUTHORIZED,
                               "a discovery task declined; the Global Policy Change Review is not authorizing and no "
                               "Receipt issues")
            _accept_adjudication(op, mutation, run, chain)
        elif latest == 3:
            _adjudicate(op, mutation, run, chain)
        elif latest == p4.ADJUDICATION_SETTLE_GENERATION:
            outcome = review_global_policy.g4_outcome(chain, reader.read_adjudication(run.review_run_id).outcome)
            if outcome == review_global_policy.OUTCOME_HUMAN_WAIT:
                return _finish(op, mutation, run, STATUS_HUMAN_WAIT,
                               "the adjudication needs a Human requirement decision; the same Run waits at G4 and no "
                               "Receipt issues")
            if outcome != review_global_policy.OUTCOME_AUTHORIZATION_READY:
                return _finish(op, mutation, run, STATUS_NOT_AUTHORIZED,
                               "a supported blocking Problem was adjudicated; a Global Policy Change Review has no "
                               "Repair Batch, so no Receipt issues and a changed proposal is a new Packet")
            _seal(op, mutation, run, chain)
        elif latest == p4.SEAL_GENERATION and chain.latest.sealed:
            return _persist(op, mutation, run, chain)
        else:
            raise _chain_invalid(f"root Review Run {run.review_run_id} is at generation {latest}, which this owner "
                                 "never writes")


def _context(op: _Op, material: Mapping[str, Any]) -> dict[str, Any]:
    return review_global_policy.review_context(material["before_global_policy"], loader_identity=_loader_identity(op))


def _loader_identity(op: _Op) -> str:
    return planning.loader_identity(package_directory(op.root))


def _text(record: Mapping[str, Any]) -> bytes:
    return serialize.canonical_text(dict(record)).encode("utf-8")


def _generation_message(generation: int, review_run_id: str) -> str:
    return f"chore(workline): record global policy review generation {generation} of {review_run_id}"


def _accept(op: _Op, mutation: Any, run: _Run) -> None:
    """G1: the Promotion Packet, the Candidate snapshot, every discovery TaskInput and the open gate, together."""
    material = run.material
    _require_reviewers(op, material)
    _require_before_state(op, material)
    packet = material["promotion_packet"]
    if serialize.digest(dict(packet)) != material["promotion_packet_digest"]:
        raise reconcile("the frozen Candidate's Packet is not the Packet its digest names", REASON_RECORD_CONFLICT)
    snapshot = review_global_policy.candidate_snapshot(material)
    context = _context(op, material)
    context_hash = serialize.digest(context)
    requirement = review_global_policy.requirement(material)
    evidence = review_global_policy.evidence_record(material)  # the Packet and each source snapshot, by digest
    evidence_ids = [f"root-evidence:{serialize.digest(evidence)}"]
    effective_hash = p4.family_policy_hash(p4.ROOT_POLICY_ID)
    task_inputs: list[records.TaskInput] = []
    for binding in _discovery_bindings(op):
        task_id = mutation.reserved(gate.review_task_key(run.review_run_id, binding.task_slot))
        if task_id is None:
            raise _chain_invalid(f"discovery slot {binding.task_slot} has no reserved task")
        envelope = review_global_policy.discovery_request(material=material, context=context,
                                                          viewpoint=binding.viewpoint, evidence_ids=evidence_ids)
        task_inputs.append(p4.task_input(
            task_id=task_id, task_slot=binding.task_slot, task_kind=p4.TASK_KIND_DISCOVERY,
            actor_identity=binding.identity, actor_version=binding.version, envelope=envelope,
            candidate_hash=snapshot.candidate_hash, candidate_material_digest=serialize.digest(snapshot.to_record()),
            review_context_hash=context_hash, accepted_generation=p4.DISCOVERY_ACCEPT_GENERATION,
            policy_id=p4.ROOT_POLICY_ID,
        ))
    required = [(found.task_slot, found.task_id) for found in task_inputs]
    gate_one = records.GateGeneration(
        review_run_id=run.review_run_id, generation=1, previous_generation=None, previous_digest=None,
        review_kind=review_global_policy.REVIEW_KIND, target_identity=review_global_policy.TARGET_IDENTITY,
        operation_identity=op.operation_identity, candidate_hash=snapshot.candidate_hash,
        review_context_hash=context_hash, effective_policy_hash=effective_hash,
        evidence_digest=serialize.digest(evidence),
        coverage_digest=serialize.digest(p4.coverage_record(required, [])),
        raw_report_set_digest=serialize.digest(p4.report_set_record([])),
        adjudication_digest=serialize.digest(p4.pending_adjudication_record()),
        obligation_digest=serialize.digest(p4.obligations_record(None)),
        accepted_tasks=tuple(p4.accepted_descriptor(found) for found in task_inputs), settled_tasks=(),
        status=records.GATE_STATUS_OPEN, receipt_id=None, authorized_operation_stage=None,
    )
    writes = [(root_maintenance.EFFECT_PACKET_CREATE, _LAYOUT.promotion_packet_rel(run.promotion_packet_id), _text(packet)),
              (root_maintenance.EFFECT_REVIEW_CREATE, _NS.candidate_snapshot_rel(snapshot.candidate_hash),
               _text(snapshot.to_record()))]
    writes += [(root_maintenance.EFFECT_REVIEW_CREATE, _NS.task_input_rel(found.task_id), _text(found.to_record()))
               for found in task_inputs]
    writes.append((root_maintenance.EFFECT_REVIEW_CREATE, _NS.gate_rel(run.review_run_id, 1), _text(gate_one.to_record())))
    _plan_stage(op, mutation, "kg1", writes, _generation_message(1, run.review_run_id))


def _require_committed(op: _Op, expected: Mapping[str, bytes | None]) -> None:
    """HEAD holds each record as a 100644 blob of exactly these bytes, and the working tree does not differ there.

    §31.27 / §16.14: every accepted external task is committed in root Review
    storage before it is launched.
    """
    relatives = sorted(expected)
    head = gitcmd.head_commit(op.root)
    entries = None if head is None else gitcmd.tree_entries(op.root, head, relatives)
    if entries is None:
        raise stop("review_persistence_unknown", "Git cannot list the committed root Review records: STOP")
    by_path = {entry.path: entry for entry in entries}
    for relative in relatives:
        entry = by_path.get(relative)
        data = expected[relative]
        if entry is None or entry.type != "blob" or entry.mode != _REGULAR or data is None \
                or gitcmd.read_blob(op.root, entry.oid) != data:
            raise stop("review_not_persisted", f"{relative} is not committed at HEAD as its canonical bytes, so the "
                                               "external launch that depends on it does not proceed: STOP")
    if gitcmd.changed_against_head(op.root, relatives):
        raise stop("review_not_persisted", "a root Review record differs from what is committed, so the external "
                                           "launch that depends on it does not proceed: STOP")


def _working_bytes(reader: ReviewStore, relatives: Sequence[str]) -> dict[str, bytes | None]:
    return {relative: reader.read_bytes(relative) for relative in relatives}


def _validate_settlement(reader: ReviewStore, review_run_id: str, task_id: str, result_digest: str,
                         reviewer_identity: str) -> None:
    """An arriving result is matched to canonical provenance before it settles anything (R3 §3, over the root reader)."""
    chain = reader.gate_chain(review_run_id)
    accepted = None if chain is None else chain.accepted_descriptor(task_id)
    accepted_at = None if chain is None else chain.accepted_at(task_id)
    if accepted is None or accepted_at is None:
        raise stop("review_callback_unknown", f"a result arrived for task {task_id}, which root Review Run "
                                              f"{review_run_id} never accepted: unknown callback")
    problems = reader.provenance_problems(accepted, accepted_at)
    if problems:
        raise _chain_invalid(f"the result for task {task_id} cannot be matched to canonical provenance: "
                             + "; ".join(message for _, message in problems))
    if reviewer_identity != accepted["reviewer_identity"]:
        raise stop("review_callback_unknown", f"task {task_id} was accepted for reviewer {accepted['reviewer_identity']}, "
                                              f"and a result arrived from {reviewer_identity}")
    for settled in chain.latest.settled_tasks:
        if str(settled["task_id"]) == task_id and str(settled["result_digest"]) != result_digest:
            raise stop("review_callback_conflict", f"task {task_id} is already settled with another result: "
                                                   "reconcile required")


def _launch_discovery(op: _Op, mutation: Any, run: _Run, chain: Any) -> None:
    """G1 -> G2: every accepted discovery task, committed (Kg1) before it is launched to its bound actor, then G2."""
    _require_reviewers(op, run.material)
    reader = _reader(op)
    first = chain.latest
    tasks = list(first.accepted_tasks)
    wanted = [_NS.candidate_snapshot_rel(first.candidate_hash), _NS.gate_rel(run.review_run_id, 1)]
    wanted += [_NS.task_input_rel(str(task["task_id"])) for task in tasks]
    expected = _working_bytes(reader, wanted)
    expected[_LAYOUT.promotion_packet_rel(run.promotion_packet_id)] = _text(run.material["promotion_packet"])
    _require_committed(op, expected)
    for task in tasks:
        problems = [message for _, message in reader.provenance_problems(task, 1)]
        if problems:
            raise _chain_invalid("the accepted discovery task's provenance: " + "; ".join(problems))
    _require_before_state(op, run.material)
    bindings = {binding.task_slot: binding for binding in _discovery_bindings(op)}
    settled: list[dict[str, Any]] = []
    reports: dict[str, dict[str, Any]] = {}
    for task in tasks:
        task_id = str(task["task_id"])
        binding = bindings.get(str(task["task_slot"]))
        if binding is None or (binding.identity, binding.version) != (task["reviewer_identity"], task["reviewer_version"]):
            raise stop("review_reviewer_mismatch",
                       f"discovery task {task_id} ({task['task_slot']}) was accepted for {task['reviewer_identity']} "
                       f"{task['reviewer_version']}, and this invocation binds no such actor; nothing is launched")
        task_input = reader.read_task_input(task_id)
        launched = p4.P4DiscoveryTask(
            task_id=task_id, task_slot=task_input.task_slot, task_kind=task_input.task_kind,
            review_kind=first.review_kind, viewpoint=binding.viewpoint,
            request_envelope=serialize.canonical_data(task_input.request_envelope),
            request_digest=task_input.request_digest, candidate_hash=task_input.candidate_hash,
            review_context_hash=task_input.review_context_hash, effective_policy_hash=task_input.effective_policy_hash,
        )
        try:
            returned = binding.actor(launched)
        except Exception as exc:
            raise stop("review_reviewer_failed", f"the discovery actor raised for task {task_id}: {exc}; nothing is "
                                                 "settled") from exc
        report = p4.report_record(returned, task, review_kind=first.review_kind,
                                  review_contract=review_global_policy.CONTRACT)
        result_digest = serialize.digest(report)
        _validate_settlement(reader, run.review_run_id, task_id, result_digest, str(returned.reviewer_identity))
        settled.append({"task_id": task_id, "status": p4.settled_status(report), "result_digest": result_digest,
                        "settled_generation": 2})
        reports[task_id] = report
    _require_before_state(op, run.material)
    required = [(str(task["task_slot"]), str(task["task_id"])) for task in tasks]
    gate_two = replace(
        first, generation=2, previous_generation=1, previous_digest=chain.latest_digest,
        coverage_digest=serialize.digest(p4.coverage_record(required, settled, reports)),
        raw_report_set_digest=serialize.digest(p4.report_set_record(settled)), settled_tasks=tuple(settled),
    )
    writes = [(root_maintenance.EFFECT_REVIEW_CREATE, _NS.gate_rel(run.review_run_id, 2), _text(gate_two.to_record()))]
    for task in settled:
        path = _NS.report_rel(task["result_digest"])
        if all(path != written for _, written, _ in writes):
            writes.append((root_maintenance.EFFECT_REVIEW_CREATE, path, _text(reports[task["task_id"]])))
    _plan_stage(op, mutation, "kg2", writes, _generation_message(2, run.review_run_id))


def _reports(reader: ReviewStore, chain: Any) -> list[tuple[str, str, dict[str, Any]]]:
    discovery_ids = {str(task["task_id"]) for task in p4.discovery_tasks(chain)}
    found = []
    for task in chain.generation(2).settled_tasks:
        if str(task["task_id"]) in discovery_ids:
            digest = str(task["result_digest"])
            found.append((str(task["task_id"]), digest, serialize.canonical_data(reader.read_report(digest).to_record())))
    return found


def _first_envelope(reader: ReviewStore, chain: Any) -> dict[str, Any]:
    return reader.read_task_input(str(chain.generations[0].accepted_tasks[0]["task_id"])).request_envelope


def _accept_adjudication(op: _Op, mutation: Any, run: _Run, chain: Any) -> None:
    """G3: one adjudication TaskInput built from canonical material only, accepted (and committed) before launch."""
    reader = _reader(op)
    second = chain.latest
    envelope = _first_envelope(reader, chain)
    reports = _reports(reader, chain)
    evidence_ids = [eid for _, _, report in reports for eid in report["coverage"]["evidence_ids"]]
    request = review_global_policy.adjudication_request(
        review_run_id=run.review_run_id, candidate_hash=second.candidate_hash,
        review_context_hash=second.review_context_hash, requirement=envelope["requirement"],
        reports=[{"task_id": task_id, "result_digest": digest} for task_id, digest, _ in reports],
        evidence_ids=evidence_ids,
    )
    task_id = mutation.reserve_id(gate.review_task_key(run.review_run_id, p4.SLOT_ADJUDICATOR), "review_task")
    assert op.review is not None
    adjudicator = op.review.adjudicator
    task_input = p4.task_input(
        task_id=task_id, task_slot=p4.SLOT_ADJUDICATOR, task_kind=p4.TASK_KIND_ADJUDICATION,
        actor_identity=adjudicator.identity, actor_version=adjudicator.version, envelope=request,
        candidate_hash=second.candidate_hash,
        candidate_material_digest=reader.candidate_material_digest(second.candidate_hash),
        review_context_hash=second.review_context_hash, accepted_generation=p4.ADJUDICATION_ACCEPT_GENERATION,
        policy_id=p4.ROOT_POLICY_ID,
    )
    gate_three = replace(
        second, generation=3, previous_generation=2, previous_digest=chain.latest_digest,
        accepted_tasks=second.accepted_tasks + (p4.accepted_descriptor(task_input),),
    )
    _plan_stage(op, mutation, "kg3", [
        (root_maintenance.EFFECT_REVIEW_CREATE, _NS.task_input_rel(task_id), _text(task_input.to_record())),
        (root_maintenance.EFFECT_REVIEW_CREATE, _NS.gate_rel(run.review_run_id, 3), _text(gate_three.to_record())),
    ], _generation_message(3, run.review_run_id))


def _adjudicate(op: _Op, mutation: Any, run: _Run, chain: Any) -> None:
    """G3 -> G4: the adjudicator, launched only to its bound identity; normalized; the meta-verifier; G4."""
    reader = _reader(op)
    third = chain.latest
    descriptor = p4.adjudication_task(chain)
    if descriptor is None:
        raise _chain_invalid(f"root Review Run {run.review_run_id} accepted no adjudication")
    task_id = str(descriptor["task_id"])
    reports = _reports(reader, chain)
    wanted = [_NS.task_input_rel(task_id), _NS.gate_rel(run.review_run_id, 3)]
    wanted += [_NS.report_rel(digest) for _, digest, _ in reports]
    _require_committed(op, _working_bytes(reader, wanted))
    problems = reader.provenance_problems(descriptor, 3)
    if problems:
        raise _chain_invalid("the accepted adjudication task's provenance: " + "; ".join(m for _, m in problems))
    _require_before_state(op, run.material)
    assert op.review is not None
    binding = op.review.adjudicator
    if (binding.identity, binding.version) != (descriptor["reviewer_identity"], descriptor["reviewer_version"]):
        raise stop("review_reviewer_mismatch",
                   f"adjudication task {task_id} was accepted for {descriptor['reviewer_identity']} "
                   f"{descriptor['reviewer_version']}, and this invocation binds {binding.identity} {binding.version}; "
                   "the adjudicator is not launched")
    task_input = reader.read_task_input(task_id)
    launched = p4.P4AdjudicationTask(
        task_id=task_id, task_slot=task_input.task_slot, task_kind=task_input.task_kind, review_kind=third.review_kind,
        request_envelope=serialize.canonical_data(task_input.request_envelope), request_digest=task_input.request_digest,
        candidate_hash=third.candidate_hash, review_context_hash=third.review_context_hash,
        effective_policy_hash=third.effective_policy_hash, candidate=dict(run.material),
        reports=tuple(report for _, _, report in reports), prior_findings=(), prior_repair_batch=None,
        prior_repair_result=None, prior_history=(),
    )
    try:
        returned = binding.actor(launched)
    except Exception as exc:
        raise p4.stop(p4.CODE_ADJUDICATOR_FAILED,
                      f"the adjudicator raised for task {task_id}: {exc}; nothing is settled") from exc
    normalized = p4.normalize_adjudication(returned, descriptor, reports, None)
    finding_ids = [mutation.reserve_id(gate.review_finding_key(run.review_run_id, ordinal), "review_finding")
                   for ordinal in range(1, len(normalized.drafts) + 1)]
    adjudication = p4.adjudication(
        normalized, finding_ids, review_run_id=run.review_run_id, gate_record=third, candidate_generation=1,
        review_contract=review_global_policy.CONTRACT, descriptor=descriptor, reports=reports, prior=None,
        policy_id=p4.ROOT_POLICY_ID,
    )
    record = adjudication.to_record()
    digest = serialize.digest(record)
    _validate_settlement(reader, run.review_run_id, task_id, digest, str(returned.adjudicator_identity))
    # §31.28: the fixed mechanical root meta-policy verification, whatever any reviewer said
    _require_meta_verified(op, run.material, source_problems=_source_problems(op, run.material),
                           base=str(mutation.record["base"]), publication=mutation.record.get("publication"))
    settled = {"task_id": task_id, "status": records.TASK_SETTLED_OK, "result_digest": digest, "settled_generation": 4}
    gate_four = replace(
        third, generation=4, previous_generation=3, previous_digest=chain.latest_digest, adjudication_digest=digest,
        obligation_digest=serialize.digest(p4.obligations_record(adjudication)),
        settled_tasks=third.settled_tasks + (settled,),
    )
    _plan_stage(op, mutation, "kg4", [
        (root_maintenance.EFFECT_REVIEW_CREATE, _NS.gate_rel(run.review_run_id, 4), _text(gate_four.to_record())),
        (root_maintenance.EFFECT_REVIEW_CREATE, _NS.adjudication_rel(run.review_run_id), _text(record)),
    ], _generation_message(4, run.review_run_id))


def _seal(op: _Op, mutation: Any, run: _Run, chain: Any) -> None:
    """G5: the Receipt, only on the full convergence predicate, the current basis and the meta-verifier."""
    reader = _reader(op)
    unmet = p4.convergence_from_records(reader, run.review_run_id, chain, _first_envelope(reader, chain),
                                        evidence_current=True)
    if unmet:
        raise _chain_invalid(f"root Review Run {run.review_run_id} is not converged: " + "; ".join(unmet))
    _require_before_state(op, run.material)
    _require_meta_verified(op, run.material, source_problems=_source_problems(op, run.material),
                           base=str(mutation.record["base"]), publication=mutation.record.get("publication"))
    fourth = chain.latest
    receipt_id = mutation.reserve_id(gate.review_receipt_key(run.review_run_id, p4.SEAL_GENERATION), "review_receipt")
    run.receipt_id = receipt_id
    run.consumption_id = mutation.reserve_id(gate.review_consumption_key(receipt_id), "review_consumption")
    gate_five = replace(
        fourth, generation=5, previous_generation=4, previous_digest=chain.latest_digest,
        status=records.GATE_STATUS_SEALED, receipt_id=receipt_id,
        authorized_operation_stage=review_global_policy.AUTHORIZED_OPERATION_STAGE,
    )
    receipt = records.Receipt(
        receipt_id=receipt_id, review_run_id=run.review_run_id, review_generation=p4.SEAL_GENERATION,
        review_kind=fourth.review_kind, target_identity=fourth.target_identity,
        operation_identity=fourth.operation_identity, authorized_candidate_hash=fourth.candidate_hash,
        review_context_hash=fourth.review_context_hash, effective_policy_hash=fourth.effective_policy_hash,
        coverage_hash=fourth.coverage_digest, adjudication_hash=fourth.adjudication_digest,
        obligation_digest=fourth.obligation_digest, unresolved_obligations=0,
        authorized_operation_stage=review_global_policy.AUTHORIZED_OPERATION_STAGE,
    )
    _plan_stage(op, mutation, "kg5", [
        (root_maintenance.EFFECT_REVIEW_CREATE, _NS.gate_rel(run.review_run_id, 5), _text(gate_five.to_record())),
        (root_maintenance.EFFECT_REVIEW_CREATE, _NS.receipt_rel(receipt_id), _text(receipt.to_record())),
    ], _generation_message(5, run.review_run_id))


def _findings(reader: ReviewStore, review_run_id: str) -> tuple[dict[str, Any], ...]:
    try:
        if not reader.adjudication_exists(review_run_id):
            return ()
        found = reader.read_adjudication(review_run_id)
    except ValidationError:
        return ()
    return tuple({"finding_id": item["finding_id"], "category": item["category"], "severity": item["severity"],
                  "blocking": item["blocking"], "statement": item["statement"]} for item in found.findings)


def _finish(op: _Op, mutation: Any, run: _Run, status: str, detail: str) -> GlobalPolicyChangeResult:
    """A root Review that issues no Receipt ends its mutation; no policy, change, note or Consumption is written."""
    if _unfinished_stages(mutation) or _stage_planned(mutation, STAGE_KP):
        raise reconcile(f"root mutation {mutation.mutation_id} holds an unfinished or persistence stage and cannot "
                        f"end {status}", REASON_RECORD_CONFLICT)
    mutation.complete()
    return GlobalPolicyChangeResult(
        status=status, global_policy_change_id=run.global_policy_change_id,
        promotion_packet_id=run.promotion_packet_id, review_run_id=run.review_run_id, receipt_id=None,
        consumption_id=None, global_policy_version=None, global_policy_digest=None, policy_commit=None,
        metadata_commit=None, mutation_id=mutation.mutation_id,
        findings=_findings(_reader(op), run.review_run_id), detail=detail,
    )


# --------------------------------------------------------------------------- persistence (§31.32-§31.38)

def _kp_paths(run: _Run) -> list[str]:
    return sorted([_LAYOUT.global_policy_rel, _LAYOUT.global_change_rel(run.global_policy_change_id),
                   _LAYOUT.patch_note_rel(run.global_policy_change_id)])


def _receipt_problems(op: _Op, run: _Run, chain: Any) -> list[str]:
    """The Receipt is this Run's G5 authorization of exactly this Candidate, current: not superseded, not consumed."""
    reader = _reader(op)
    found: list[str] = []
    fifth = chain.generation(p4.SEAL_GENERATION)
    if not fifth.sealed or fifth.receipt_id != run.receipt_id:
        found.append("generation 5 does not issue the reserved Receipt")
    try:
        receipt = reader.read_receipt(str(run.receipt_id))
    except ValidationError as exc:
        return found + [f"the Receipt does not read ({exc})"]
    if (receipt.authorized_candidate_hash, receipt.authorized_operation_stage, receipt.review_kind) != (
            review_global_policy.candidate_hash(run.material), review_global_policy.AUTHORIZED_OPERATION_STAGE,
            review_global_policy.REVIEW_KIND):
        found.append("the Receipt does not authorize exactly this Candidate's persist-global-policy stage")
    if reader.supersession_exists(str(run.receipt_id)) or len(chain.generations) > p4.SEAL_GENERATION:
        found.append("the Receipt is superseded")
    if any(str(item.receipt_id) == run.receipt_id for item in reader.consumptions()) \
            or _consumed_by(_committed_consumptions(op), str(run.receipt_id)):
        found.append("the Receipt is consumed")
    return found


def _persist(op: _Op, mutation: Any, run: _Run, chain: Any) -> GlobalPolicyChangeResult:
    material = run.material
    if run.receipt_id is None or run.consumption_id is None:
        raise reconcile(f"root mutation {mutation.mutation_id} holds no Receipt / Consumption reservation",
                        REASON_RECORD_CONFLICT)
    # step 1 - after G5, the currentness recheck, then the change record, the Patch Note and the exact CAS together
    if not _stage_planned(mutation, STAGE_KP):
        problems = _receipt_problems(op, run, chain)
        if problems:
            raise _chain_invalid("the Global Policy Change Receipt is not current: " + "; ".join(problems))
        _require_before_state(op, material, code=CODE_STALE_CANDIDATE)
        stale = _source_problems(op, material)
        if stale:
            raise stop(CODE_STALE_CANDIDATE, "the Promotion Packet's bound source evidence went stale after G5 ("
                       + "; ".join(stale) + "); no policy is written or published and a new Candidate is required")
        _require_meta_verified(op, material, source_problems=(), base=str(mutation.record["base"]),
                               publication=mutation.record.get("publication"))
        change = review_global_policy.change_record(material, review_run_id=run.review_run_id,
                                                    receipt_id=str(run.receipt_id))
        before = policy.global_policy_bytes(material["before_global_policy"])
        if gitcmd.blob_at(op.root, _expected_parent(mutation), _LAYOUT.global_policy_rel) != before:
            raise stop(CODE_STALE_CANDIDATE, "the committed global-policy.yaml is not the exact reviewed before bytes; "
                                             "nothing is written")
        checkout = _checkout_bytes(op, _LAYOUT.global_policy_rel, before)
        _plan_stage(op, mutation, STAGE_KP, [
            (root_maintenance.EFFECT_CHANGE_CREATE, _LAYOUT.global_change_rel(run.global_policy_change_id), _text(change)),
            (root_maintenance.EFFECT_PATCH_NOTE_CREATE, _LAYOUT.patch_note_rel(run.global_policy_change_id),
             review_global_policy.patch_note_bytes(change)),
            (root_maintenance.EFFECT_GLOBAL_POLICY_REPLACE, _LAYOUT.global_policy_rel,
             policy.global_policy_bytes(material["after_global_policy"]), checkout),
        ], f"chore(workline): apply global policy change {run.global_policy_change_id}")
    # step 2 - Kp, the base-exact class B commit of exactly those three paths
    _settle(op, mutation)
    # step 3 - C-2(Kp) on every pass; nothing is published before it holds. The source evidence is re-proven
    # current until the policy is published (or, remote-less, until the Consumption is decided on it).
    current_required = not _pushed(mutation, STAGE_KP) and not _stage_planned(mutation, STAGE_KM)
    kp, parent = _c2_kp(op, mutation, run, before_publication=current_required)
    # step 4 - the exact Kp publication when the root has a remote
    if mutation.record.get("publication") is not None:
        _push_stage(op, mutation, STAGE_KP, kp)
    # step 5 - the Global Policy Consumption v4, then Km
    consumption_path = _NS.consumption_rel(str(run.consumption_id))
    if not _stage_planned(mutation, STAGE_KM):
        _plan_stage(op, mutation, STAGE_KM, [
            (root_maintenance.EFFECT_CONSUMPTION_CREATE, consumption_path,
             _consumption_bytes(op, mutation, run, chain, kp, parent)),
        ], f"chore(workline): record global policy consumption {run.consumption_id}")
    _settle(op, mutation)
    # step 6 - C-2(Km), then the exact Km publication
    km = _c2_km(op, mutation, run, kp)
    if mutation.record.get("publication") is not None:
        _push_stage(op, mutation, STAGE_KM, km)
    mutation.complete()
    after = material["after_global_policy"]
    return GlobalPolicyChangeResult(
        status=STATUS_APPLIED, global_policy_change_id=run.global_policy_change_id,
        promotion_packet_id=run.promotion_packet_id, review_run_id=run.review_run_id, receipt_id=run.receipt_id,
        consumption_id=run.consumption_id, global_policy_version=int(after["global_policy_version"]),
        global_policy_digest=policy.global_policy_digest(after), policy_commit=kp, metadata_commit=km,
        mutation_id=mutation.mutation_id, findings=_findings(_reader(op), run.review_run_id),
        detail="the Global policy was changed, proven and recorded",
    )


def _checkout_bytes(op: _Op, relative: str, committed: bytes) -> bytes:
    """The CAS's expected bytes (Amendment 1 item 2): the working tree's exact bytes captured at the entry freeze.

    A checkout may carry the committed blob with other line ends
    (``core.autocrlf`` on the root's own clone), and the exact
    compare-and-replace of the Global policy is made against the bytes actually
    there. They must be ``committed`` exactly once line ends are read as LF,
    still be there now, and Git must see the path unchanged from HEAD;
    anything else is a stale before-state and nothing is written. The
    committed result is the reviewed after bytes exactly, whatever the
    checkout held (class B, C-2(Kp)).
    """
    captured = op.entry.global_policy_checkout
    if captured is None or captured.replace(b"\r\n", b"\n") != committed \
            or _working_bytes_of(op.root, relative) != captured or gitcmd.changed_against_head(op.root, [relative]):
        raise stop(CODE_STALE_CANDIDATE, f"the working tree's {relative} is not the checkout of the exact reviewed "
                                         "before policy captured at entry; nothing is written")
    return captured


def _consumption_bytes(op: _Op, mutation: Any, run: _Run, chain: Any, kp: str, parent: str) -> bytes:
    """The Global Policy Consumption v4 record (§31.37), strictly read back before it is recorded."""
    first = chain.generations[0]
    delta = gitcmd.commit_delta(op.root, parent, kp)
    if delta is None:
        raise reconcile(f"Git cannot show what {kp} changes", REASON_PERSISTED_MISMATCH)
    delta_record = {
        "parent": parent, "commit": kp,
        "entries": [{"path": item.path, "status": item.status, "mode": item.new_mode, "blob": item.new_blob}
                    for item in sorted(delta, key=lambda entry: entry.path)],
    }
    persisted = review_global_policy.persisted_global_policy(
        run.material, global_policy_change_id=run.global_policy_change_id, policy_commit=kp, policy_parent=parent,
        branch=str(mutation.record["branch"]), policy_delta_digest=serialize.digest(delta_record),
        loader_identity=_loader_identity(op),
    )
    record = {
        serialize.SCHEMA_KEY: records.SCHEMA_CONSUMPTION,
        serialize.VERSION_KEY: records.GLOBAL_POLICY_CONSUMPTION_VERSION,
        "consumption_id": str(run.consumption_id),
        "receipt_id": str(run.receipt_id),
        "review_run_id": run.review_run_id,
        "review_generation": p4.SEAL_GENERATION,
        "review_kind": first.review_kind,
        "authorized_candidate_hash": first.candidate_hash,
        "operation_identity": first.operation_identity,
        "root_policy_mutation_id": mutation.mutation_id,
        "target_identity": first.target_identity,
        "persisted_global_policy": serialize.canonical_data(dict(persisted)),
    }
    found = records.consumption_from_record(serialize.canonical_data(record), "the Global Policy Consumption")
    if not isinstance(found, records.GlobalPolicyConsumption):
        raise reconcile("the Global Policy Consumption does not read as a version 4 Consumption",
                        REASON_PERSISTED_MISMATCH)
    return _text(found.to_record())


# --------------------------------------------------------------------------- C-2(Kp) / C-2(Km) (committed objects)

def _proof_failed(item: str, detail: str) -> ReconcileRequired:
    return reconcile(f"C-2(Kp) {item} fails: {detail}; nothing is published", REASON_PERSISTED_MISMATCH)


def _recorded_commit(mutation: Any, stage: str) -> tuple[str, str]:
    """The commit a stage made, recorded with its ref moved: (commit, its recorded parent)."""
    found = _commit_effect(mutation, stage)
    facts = {} if found is None else _facts(found[1])
    commit = facts.get(FACT_PREPARED_COMMIT)
    if found is None or facts.get(FACT_REF_MOVED) is not True or not gitcmd.full_commit_id(commit):
        raise reconcile(f"the {stage} commit is not recorded as a commit this root mutation made and moved its branch "
                        "to", REASON_PERSISTED_MISMATCH)
    return str(commit), str(_payload(found[1]).get("parent"))


def _stage_bytes(mutation: Any, stage: str) -> dict[str, bytes]:
    plan = _stages(mutation)["plans"].get(stage) or {}
    return {str(item["path"]): str(item["content"]).encode("utf-8") for item in plan.get("creates") or []}


def _branch_holds(op: _Op, mutation: Any, commit: str) -> bool:
    branch = str(mutation.record["branch"])
    tip = gitcmd.branch_commit(op.root, branch)
    return gitcmd.current_branch_ref(op.root) == branch and tip is not None \
        and gitcmd.descends_from(op.root, tip, commit) is True


def _root_meta_policy() -> dict[str, Any]:
    return {
        "root_policy_id": p4.ROOT_POLICY_ID, "root_policy_hash": p4.family_policy_hash(p4.ROOT_POLICY_ID),
        "meta_rules_id": policy.META_RULES_ID, "meta_rules_digest": policy.meta_rules_digest(),
        "loader_semantics_identity": policy.LOADER_SEMANTICS_IDENTITY,
    }


def _c2_kp(op: _Op, mutation: Any, run: _Run, *, before_publication: bool) -> tuple[str, str]:
    """C-2(Kp) (§31.35): Kp is this mutation's own, exactly the reviewed policy state, round-tripped, current."""
    material = run.material
    try:
        kp, parent = _recorded_commit(mutation, STAGE_KP)
    except ReconcileRequired as exc:
        raise _proof_failed("K1", str(exc)) from exc
    if gitcmd.commit_parents(op.root, kp) != [parent] or not _branch_holds(op, mutation, kp):
        raise _proof_failed("K2", "the parent, branch or lineage of the policy commit is not the recorded one")
    expected = _stage_bytes(mutation, STAGE_KP)
    statuses = {_LAYOUT.global_policy_rel: "M", _LAYOUT.global_change_rel(run.global_policy_change_id): "A",
                _LAYOUT.patch_note_rel(run.global_policy_change_id): "A"}
    delta = gitcmd.commit_delta(op.root, parent, kp)
    if delta is None or set(expected) != set(statuses) or {item.path for item in delta} != set(statuses) or any(
        item.status != statuses[item.path] or item.new_mode != _REGULAR
        or gitcmd.read_blob(op.root, item.new_blob) != expected[item.path] for item in delta
    ):
        raise _proof_failed("K3", "the policy commit is not exactly the Global policy, change record and Patch Note "
                                  "the stage recorded")
    committed = gitcmd.blob_at(op.root, kp, _LAYOUT.global_policy_rel) or b""
    after = material["after_global_policy"]
    if committed != policy.global_policy_bytes(after):
        raise _proof_failed("K4", "global-policy.yaml is not the exact reviewed after bytes")
    try:
        loaded = policy.parse_global_policy_bytes(committed, f"{_LAYOUT.global_policy_rel} at {kp}")
    except ValidationError as exc:
        raise _proof_failed("K5", str(exc)) from exc
    projection = serialize.digest(policy.global_policy_projection(loaded))
    expected_kp = material["expected_kp"]
    if policy.global_policy_digest(loaded) != material["after_global_policy_digest"] \
            or policy.global_policy_digest(loaded) != expected_kp["global_policy_digest"] \
            or projection != material["normalized_projection_hash"] \
            or projection != expected_kp["normalized_projection_hash"] \
            or sorted(statuses) != list(expected_kp["paths"]):
        raise _proof_failed("K5", "the committed Global policy does not round-trip to the reviewed after-state")
    if not gitcmd.changed_against_head(op.root, [_LAYOUT.global_policy_rel]):
        try:
            baseline = policy.load_global_baseline(op.root)
        except StopError as exc:
            raise _proof_failed("K5", f"the canonical loader does not read the committed policy ({exc})") from exc
        if baseline.source_mode != policy.SOURCE_MODE_MATERIALIZED \
                or baseline.global_policy_identity != policy.global_policy_digest(loaded) \
                or serialize.digest(baseline.semantic_projection) != projection:
            raise _proof_failed("K5", "the canonical loader's normalized projection is not the reviewed after-state")
    before_raw = gitcmd.blob_at(op.root, parent, _LAYOUT.global_policy_rel)
    try:
        before = policy.parse_global_policy_bytes(before_raw or b"", f"{_LAYOUT.global_policy_rel} at {parent}")
    except ValidationError as exc:
        raise _proof_failed("K6", str(exc)) from exc
    if policy.global_policy_digest(before) != material["before_global_policy_digest"] \
            or policy.global_policy_successor_problem(before, loaded) is not None:
        raise _proof_failed("K6", "the policy commit's parent does not hold the exact reviewed before policy, or the "
                                  "committed policy is not its exact successor")
    if material.get("root_meta_policy") != _root_meta_policy():
        raise _proof_failed("K7", "the fixed root meta-policy, meta-rules or loader identity changed")
    proof = review_global_policy.compatibility_proof(before, loaded)
    if review_global_policy.compatibility_proof_digest(proof) != material["compatibility_proof_digest"]:
        raise _proof_failed("K8", "the total compatibility proof is not the reviewed one")
    try:
        at_kp = CommittedReviewStore(op.root, kp, namespace=_NS)
        chain = at_kp.gate_chain(run.review_run_id)
        if chain is None or len(chain.generations) != p4.SEAL_GENERATION or chain.latest.receipt_id != run.receipt_id:
            raise _proof_failed("K9", f"{kp} does not hold the sealed root Review Run")
        receipt = at_kp.read_receipt(str(run.receipt_id))
        if at_kp.supersession_exists(str(run.receipt_id)) \
                or any(str(found.receipt_id) == run.receipt_id for found in at_kp.consumptions()):
            raise _proof_failed("K9", f"{kp} holds an invalidation or a Consumption of the Receipt")
        if receipt.authorized_candidate_hash != review_global_policy.candidate_hash(material):
            raise _proof_failed("K9", "the Receipt does not authorize the reviewed Candidate")
        change = review_global_policy.parse_change_record(
            serialize.parse_canonical(expected[_LAYOUT.global_change_rel(run.global_policy_change_id)], "the change")[0],
            "the committed change record")
        if (change.get("receipt_id"), change.get("review_run_id")) != (run.receipt_id, run.review_run_id):
            raise _proof_failed("K9", "the change record does not bind this Run and Receipt")
    except ValidationError as exc:
        raise _proof_failed("K9", str(exc)) from exc
    if before_publication:
        stale = _source_problems(op, material)
        if stale:
            raise _proof_failed("K10", "; ".join(stale))
    if any(effect.get("kind") == root_maintenance.EFFECT_PUSH
           and _payload(effect).get("stage") not in (STAGE_KP, STAGE_KM) for effect in mutation.effects()):
        raise _proof_failed("K11", "the root mutation holds a push that is not its exact Kp / Km publication")
    return kp, parent


def _metadata_failed(item: str, detail: str) -> ReconcileRequired:
    return reconcile(f"C-2(Km) {item} fails: {detail}; nothing is published", REASON_PERSISTED_MISMATCH)


def _c2_km(op: _Op, mutation: Any, run: _Run, kp: str) -> str:
    """C-2(Km) (§31.38): Km is this mutation's own, exactly the Global Policy Consumption, directly on Kp."""
    try:
        km, parent = _recorded_commit(mutation, STAGE_KM)
    except ReconcileRequired as exc:
        raise _metadata_failed("M1", str(exc)) from exc
    if parent != kp or gitcmd.commit_parents(op.root, km) != [kp]:
        raise _metadata_failed("M1", "the metadata commit's parent is not exactly the policy commit")
    if not _branch_holds(op, mutation, km):
        raise _metadata_failed("M2", "HEAD is not on the bound branch, or the branch does not hold the metadata commit")
    expected = _stage_bytes(mutation, STAGE_KM)
    consumption_path = _NS.consumption_rel(str(run.consumption_id))
    delta = gitcmd.commit_delta(op.root, kp, km)
    if delta is None or set(expected) != {consumption_path} or {item.path for item in delta} != {consumption_path} \
            or any(item.status != "A" or item.new_mode != _REGULAR
                   or gitcmd.read_blob(op.root, item.new_blob) != expected[item.path] for item in delta):
        raise _metadata_failed("M3", "the metadata commit is not exactly the added Global Policy Consumption")
    try:
        consumption = CommittedReviewStore(op.root, km, namespace=_NS).read_consumption(str(run.consumption_id))
    except ValidationError as exc:
        raise _metadata_failed("M4", str(exc)) from exc
    if not isinstance(consumption, records.GlobalPolicyConsumption) or consumption.receipt_id != run.receipt_id \
            or consumption.policy_commit != kp \
            or consumption.persisted_global_policy.get("global_policy_change_id") != run.global_policy_change_id:
        raise _metadata_failed("M4", "the Consumption does not bind the Receipt, the change and the policy commit")
    for path in _kp_paths(run):
        if gitcmd.blob_at(op.root, km, path) != gitcmd.blob_at(op.root, kp, path):
            raise _metadata_failed("M5", f"{km} does not hold the policy commit's {path}")
    return km


def _c2_evaluation(op: _Op, mutation: Any, evaluation_path: str) -> str:
    """The evaluation commit is this mutation's own and adds exactly its one immutable evaluation record (§31.42)."""
    try:
        commit, parent = _recorded_commit(mutation, STAGE_EVALUATION)
    except ReconcileRequired as exc:
        raise reconcile(f"the evaluation commit proof fails: {exc}", REASON_PERSISTED_MISMATCH) from exc
    expected = _stage_bytes(mutation, STAGE_EVALUATION)
    delta = gitcmd.commit_delta(op.root, parent, commit)
    if gitcmd.commit_parents(op.root, commit) != [parent] or not _branch_holds(op, mutation, commit) \
            or delta is None or set(expected) != {evaluation_path} or {item.path for item in delta} != {evaluation_path} \
            or any(item.status != "A" or item.new_mode != _REGULAR
                   or gitcmd.read_blob(op.root, item.new_blob) != expected[item.path] for item in delta):
        raise reconcile("the evaluation commit is not exactly the one added evaluation record on its recorded parent; "
                        "nothing is published", REASON_PERSISTED_MISMATCH)
    return commit


def _require_root_proof(op: _Op, mutation: Any, stage: str, commit: str) -> None:
    """The root C-2 of exactly the commit a push publishes, run right before that push (AO-2)."""
    if stage == STAGE_EVALUATION:
        proven = _c2_evaluation(op, mutation, str(next(iter(_stage_bytes(mutation, STAGE_EVALUATION)), "")))
    else:
        run = _recorded_run(op, mutation)
        kp, _ = _c2_kp(op, mutation, run, before_publication=stage == STAGE_KP)
        proven = kp if stage == STAGE_KP else _c2_km(op, mutation, run, kp)
    if proven != commit:
        raise reconcile(f"the {stage} push names {commit}, and the proven {stage} commit is {proven}; nothing is "
                        "published", REASON_PUBLICATION_INVALID)


# --------------------------------------------------------------------------- the one root push point (AO-2)

def _pushed(mutation: Any, stage: str) -> bool:
    found = _push_effect(mutation, stage)
    return found is not None and _facts(found[1]).get(FACT_PUSHED) is True


def _push_stage(op: _Op, mutation: Any, stage: str, commit: str) -> None:
    """The recorded push of one stage's exact commit: intent first, then :func:`_publish`."""
    found = _push_effect(mutation, stage)
    if found is None:
        frozen = mutation.record.get("publication") or {}
        index = mutation.add_effect(root_maintenance.EFFECT_PUSH, {
            "stage": stage, "remote": frozen.get("remote"), "ref": frozen.get("branch"), "commit": commit,
        })
    else:
        index, effect = found
        if _payload(effect).get("commit") != commit:
            raise reconcile(f"the recorded {stage} push names {_payload(effect).get('commit')}, not the proven {commit}",
                            REASON_RECORD_CONFLICT)
    _publish(op, mutation, index)


def _publication_invalid(message: str) -> ReconcileRequired:
    return reconcile(f"{message}; nothing is pushed or forced", REASON_PUBLICATION_INVALID)


def _publish(op: _Op, mutation: Any, index: int) -> None:
    """Publish exactly one recorded commit to its exact full branch, or nothing (§31.31, §31.39).

    In this order, immediately before the push: the root authorization is
    re-validated, the push locator re-resolved and read as itself, the
    destination branch read explicitly, the exact fast-forward proven (objects
    only may be fetched; no ref moves), the exact push previewed, the root C-2
    proof of this exact commit passed, and the publication barrier cleared. A
    destination that already holds the commit is published already: nothing
    is pushed twice. Unknown, unreadable or divergent is no push.
    """
    effect = mutation.effects()[index]
    if _facts(effect).get(FACT_PUSHED) is True:
        return
    payload = _payload(effect)
    stage, remote, ref, commit = (str(payload.get(name)) for name in ("stage", "remote", "ref", "commit"))
    frozen = mutation.record.get("publication") or {}
    # 1 - the Human-approved root authorization, re-validated now (never inferred from origin)
    binding = root_maintenance.publication_binding(op.root)
    if binding is None or (binding.remote, binding.branch) != (frozen.get("remote"), frozen.get("branch")) \
            or (binding.remote, binding.branch) != (remote, ref) or ref != mutation.record.get("branch"):
        raise _publication_invalid(f"the {stage} push to {remote} {ref} is not the authorized root publication")
    # 2 - the push locator, re-resolved, and read as itself
    locator = destination.resolve_active_push_locator(op.root, remote)
    if locator != binding.locator or gitcmd.reads_itself(op.root, locator) is not True:
        raise _publication_invalid(f"remote {remote} no longer resolves to the authorized locator, or Git does not read "
                                   "it as itself")
    # 3 - the destination branch, read explicitly
    try:
        tip = gitcmd.destination_branch(op.root, locator, ref)
    except GitError as exc:
        raise _publication_invalid(f"the destination {ref} cannot be read ({exc})") from exc
    if tip == commit:
        mutation.mark_effect(index, {FACT_PUSHED: True})
        return
    # 4 - the exact fast-forward relation (the destination's objects may be fetched; no local ref moves)
    if tip is not None:
        holds = gitcmd.descends_from(op.root, tip, commit)
        forward = gitcmd.descends_from(op.root, commit, tip)
        if holds is None or forward is None:
            gitcmd.fetch_destination_branch(op.root, locator, ref)
            holds = gitcmd.descends_from(op.root, tip, commit)
            forward = gitcmd.descends_from(op.root, commit, tip)
        if holds is True:
            mutation.mark_effect(index, {FACT_PUSHED: True})  # the destination moved on past it: published already
            return
        if forward is not True:
            raise _publication_invalid(f"the destination {ref} is at {tip}, which {commit} does not fast-forward; "
                                       "nothing is rebased or cherry-picked")
    # 5 - the exact push, previewed over the real push path
    refspec = f"{commit}:{ref}"
    preview = gitcmd.push_dry_run(op.root, remote, refspec)
    if preview.flag == "=":
        mutation.mark_effect(index, {FACT_PUSHED: True})
        return
    if preview.flag not in ("*", " "):
        raise _publication_invalid(f"git push --dry-run reports {preview.flag!r} ({preview.summary}) for {refspec}")
    # 6 - the root C-2 proof of exactly this commit
    _require_root_proof(op, mutation, stage, commit)
    # 7 - the publication barrier, for every Workline push
    publication.require_barrier_clear(op.root, commit)
    pushed = gitcmd.push(op.root, remote, refspec)
    if not pushed.ok:
        raise GitError(f"the {stage} push to {locator} failed: {pushed.stderr.strip() or pushed.stdout.strip()}")
    mutation.mark_effect(index, {FACT_PUSHED: True})


# --------------------------------------------------------------------------- stages and class B commits

def _stages(mutation: Any) -> dict[str, Any]:
    found = mutation.note(NOTE_STAGES)
    if not isinstance(found, Mapping):
        return {"order": [], "plans": {}}
    return {"order": list(found.get("order") or []), "plans": dict(found.get("plans") or {})}


def _stage_planned(mutation: Any, stage: str) -> bool:
    return stage in _stages(mutation)["plans"]


def _commit_effect(mutation: Any, stage: str) -> tuple[int, dict[str, Any]] | None:
    for index, effect in enumerate(mutation.effects()):
        if effect.get("kind") == root_maintenance.EFFECT_COMMIT and _payload(effect).get("stage") == stage:
            return index, effect
    return None


def _push_effect(mutation: Any, stage: str) -> tuple[int, dict[str, Any]] | None:
    for index, effect in enumerate(mutation.effects()):
        if effect.get("kind") == root_maintenance.EFFECT_PUSH and _payload(effect).get("stage") == stage:
            return index, effect
    return None


def _unfinished_stages(mutation: Any) -> list[str]:
    """The recorded stages whose commit has not moved its branch yet."""
    found = []
    for stage in _stages(mutation)["order"]:
        commit = _commit_effect(mutation, stage)
        if commit is None or _facts(commit[1]).get(FACT_REF_MOVED) is not True:
            found.append(stage)
    return found


def _expected_parent(mutation: Any) -> str:
    """The commit the next root commit is made on: the last one this mutation made, else its frozen base."""
    parent = str(mutation.record["base"])
    for effect in mutation.effects():
        facts = _facts(effect)
        if effect.get("kind") == root_maintenance.EFFECT_COMMIT and facts.get(FACT_REF_MOVED) is True:
            parent = str(facts[FACT_PREPARED_COMMIT])
    return parent


def _plan_stage(op: _Op, mutation: Any, stage: str,
                writes: Sequence[tuple[Any, ...]], message: str) -> None:
    """Decide one stage whole, durably, before its first effect: what it writes and the commit that records it.

    ``writes`` are ``(effect kind, path, bytes)`` - plus the exact expected
    before bytes for the Global policy CAS. One note save records the plan;
    :func:`_settle` then records each effect from it, applies it and makes the
    commit, so a crash anywhere resumes the same stage, never a recomputed one.
    """
    stages = _stages(mutation)
    if stage in stages["plans"]:
        raise reconcile(f"root mutation {mutation.mutation_id} already recorded stage {stage}, and the root Review did "
                        "not advance past it", REASON_RECORD_CONFLICT)
    paths = [str(item[1]) for item in writes]
    if len(set(paths)) != len(paths):
        raise reconcile(f"stage {stage} writes one path twice", REASON_RECORD_CONFLICT)
    root_maintenance.require_committable(op.root, paths)
    creates = []
    for item in writes:
        kind, path, data = item[0], str(item[1]), bytes(item[2])
        create: dict[str, Any] = {"kind": kind, "path": path, "content": data.decode("utf-8")}
        if kind == root_maintenance.EFFECT_GLOBAL_POLICY_REPLACE:
            expected = item[3]
            create["expected_content"] = None if expected is None else bytes(expected).decode("utf-8")
        creates.append(create)
    plans = dict(stages["plans"])
    plans[stage] = {"creates": creates, "message": message, "paths": sorted(paths, key=_path_order)}
    mutation.set_note(NOTE_STAGES, {"order": stages["order"] + [stage], "plans": plans})


def _path_order(relative: str) -> bytes:
    """Path byte order: the order a root commit names its changed paths in (B's commit payload rule)."""
    return relative.encode("utf-8", "surrogatepass")


def _sha256(text: str | None) -> str | None:
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ensure_file_effect(mutation: Any, create: Mapping[str, Any]) -> int:
    """The recorded effect of one planned write - recorded now if it is not yet - and never a different one."""
    for index, effect in enumerate(mutation.effects()):
        payload = _payload(effect)
        if effect.get("kind") in _FILE_EFFECTS and payload.get("path") == create["path"]:
            if effect.get("kind") != create["kind"] or payload.get("content") != create["content"]:
                raise reconcile(f"the recorded effect at {create['path']} is not the one its stage planned",
                                REASON_RECORD_CONFLICT)
            return index
    payload = {"path": create["path"], "content": create["content"], "sha256": _sha256(create["content"])}
    if create["kind"] == root_maintenance.EFFECT_GLOBAL_POLICY_REPLACE:
        payload["expected_content"] = create.get("expected_content")
        payload["expected_sha256"] = _sha256(create.get("expected_content"))
    return mutation.add_effect(create["kind"], payload)


def _settle(op: _Op, mutation: Any) -> None:
    """Finish every recorded stage in order: its effects recorded and applied, its commit made and its ref moved."""
    stages = _stages(mutation)
    for stage in stages["order"]:
        plan = stages["plans"][stage]
        found = _commit_effect(mutation, stage)
        if found is not None and _facts(found[1]).get(FACT_REF_MOVED) is True:
            continue
        for create in plan["creates"]:
            mutation.apply_effect(_ensure_file_effect(mutation, create))
        if found is None:
            index = mutation.add_effect(root_maintenance.EFFECT_COMMIT, {
                "stage": stage, "parent": _expected_parent(mutation), "ref": str(mutation.record["branch"]),
                "message": plan["message"], "paths": list(plan["paths"]), "date": workcommit.commit_date(),
            })
        else:
            index = found[0]
        _finish_commit(op, mutation, index)


def _parent_entries(op: _Op, parent: str, paths: Sequence[str]) -> dict[str, tuple[str, str]]:
    """``path -> (mode, oid)`` of the exact parent commit's tree, read class B."""
    found = op.git.run_bytes("ls-tree", "-z", "--full-tree", parent, "--", *paths)
    if not found.ok:
        raise reconcile(f"Git cannot list the parent {parent} of a root commit", REASON_RECORD_CONFLICT)
    entries: dict[str, tuple[str, str]] = {}
    for item in found.stdout.split(b"\0"):
        if not item:
            continue
        head, separator, raw_path = item.partition(b"\t")
        fields = head.split(b" ")
        if not separator or len(fields) != 3:
            raise reconcile(f"the tree of {parent} holds an entry this reader cannot classify", REASON_RECORD_CONFLICT)
        entries[raw_path.decode("utf-8", "surrogateescape")] = (fields[0].decode("ascii"), fields[2].decode("ascii"))
    return entries


def _blob_id(op: _Op, data: bytes) -> str:
    found = op.git.run_bytes("hash-object", "--no-filters", "-t", "blob", "--stdin", input=data)
    oid = found.stdout.decode("ascii", "replace").strip() if found.ok else ""
    if not gitcmd.full_commit_id(oid):
        raise reconcile("Git cannot name the object of a root record's exact bytes", REASON_RECORD_CONFLICT)
    return oid


def _commit_plan(op: _Op, mutation: Any, payload: Mapping[str, Any]) -> workcommit.CommitTreePlan:
    """The commit tree plan of one recorded commit: the recorded bytes of its paths against its exact parent."""
    stage = str(payload["stage"])
    parent = str(payload["parent"])
    contents = _stage_bytes(mutation, stage)
    paths = [str(path) for path in payload["paths"]]
    if set(paths) != set(contents):
        raise reconcile(f"the {stage} commit does not name exactly the paths its stage recorded", REASON_RECORD_CONFLICT)
    held = _parent_entries(op, parent, paths)
    entries: list[workcommit.PlanEntry] = []
    for path in sorted(paths):
        data = contents[path]
        oid = _blob_id(op, data)
        old = held.get(path)
        if old == (_REGULAR, oid):
            continue  # an exact immutable record its parent already holds changes nothing
        entries.append(workcommit.PlanEntry(path, old[0] if old else None, old[1] if old else None, _REGULAR, oid, data))
    plan_class = workcommit.CLASS_GENERATION if stage in STAGE_GENERATIONS else workcommit.CLASS_WORK_STAGE
    return workcommit.CommitTreePlan(parent, str(payload["ref"]), str(payload["message"]), ROOT_COMMIT_CONTRACT,
                                     plan_class, tuple(entries))


def _isolated_index(op: _Op, mutation: Any, stage: str) -> Path:
    """O-1: a fresh isolated index in the proven root runtime temporary directory, never the real index."""
    return root_maintenance.tmp_directory(op.lock) / f"{mutation.mutation_id}-{stage}.index"


def _discard(index: Path) -> None:
    for candidate in (index, Path(str(index) + ".lock")):
        if candidate.is_file() and not candidate.is_symlink():
            candidate.unlink()


def _prepared_object_problem(op: _Op, facts: Mapping[str, Any], payload: Mapping[str, Any]) -> str | None:
    """Amendment 10 item 1: the recorded prepared commit is exactly the object recorded - or why not.

    Read from the stored object itself (class B): a commit, whose tree is the
    recorded ``prepared_tree``, whose one and only parent is the recorded
    expected parent, and whose message is the recorded message, byte for byte.
    Nothing is rebuilt, rebased or adopted by message.
    """
    commit = str(facts.get(FACT_PREPARED_COMMIT))
    kind = op.git.run_bytes("cat-file", "-t", commit)
    found = op.git.run_bytes("cat-file", "commit", commit)
    if not kind.ok or kind.stdout.strip() != b"commit" or not found.ok:
        return f"{commit} is not a readable commit object"
    header, separator, message = found.stdout.partition(b"\n\n")
    lines = header.split(b"\n")
    parents = [line[len(b"parent "):] for line in lines if line.startswith(b"parent ")]
    if not separator or not lines or lines[0] != b"tree " + str(facts.get(FACT_PREPARED_TREE)).encode("ascii") \
            or parents != [str(payload.get("parent")).encode("ascii")] \
            or message != str(payload.get("message")).encode("utf-8"):
        return f"{commit} is not the recorded prepared commit (its tree, parent or message differ)"
    return None


def _finish_commit(op: _Op, mutation: Any, index: int) -> None:
    """One class B root commit, made to the end: prepared, recorded, ref moved by CAS from its exact parent, read back.

    The prepared commit is recorded before the ref moves (RB7BL-1). When the
    branch already names the recorded prepared commit - the move landed and
    only its fact did not (Amendment 10 item 1) - that object is proven to be
    exactly the recorded one and its move is recorded; nothing is rebuilt.
    Otherwise the plan is built (a rebuild of the same recorded bytes, parent,
    message, date and identity is the same object; anything else is never
    adopted) and the ref moved by compare-and-swap from the exact parent. A
    branch that is neither the parent nor the prepared commit moved under the
    operation: reconcile, never a rebase.
    """
    effect = mutation.effects()[index]
    facts = _facts(effect)
    if facts.get(FACT_REF_MOVED) is True:
        return
    payload = _payload(effect)
    ref, parent = str(payload["ref"]), str(payload["parent"])
    recorded = facts.get(FACT_PREPARED_COMMIT)
    if recorded is not None and workcommit.ref_value(op.git, ref) == recorded:
        problem = _prepared_object_problem(op, facts, payload)
        if problem is not None:
            raise reconcile(f"{ref} names {recorded}, and {problem}; another object is never adopted",
                            REASON_RECORD_CONFLICT)
        prepared_facts = {FACT_PREPARED_COMMIT: str(recorded), FACT_PREPARED_TREE: str(facts[FACT_PREPARED_TREE])}
    else:
        plan = _commit_plan(op, mutation, payload)
        isolated = _isolated_index(op, mutation, str(payload["stage"]))
        try:
            prepared = workcommit.build(op.git, plan, index=isolated, date=str(payload["date"]))
        finally:
            _discard(isolated)
        if recorded is not None and (recorded, facts.get(FACT_PREPARED_TREE)) != (prepared.commit, prepared.tree):
            raise reconcile(f"the {payload['stage']} commit rebuilt from its record is {prepared.commit}, not the "
                            f"recorded {recorded}; another object is never adopted", REASON_RECORD_CONFLICT)
        prepared_facts = {FACT_PREPARED_COMMIT: prepared.commit, FACT_PREPARED_TREE: prepared.tree}
        if recorded is None:
            mutation.mark_effect(index, {**prepared_facts, FACT_REF_MOVED: False})
        held = workcommit.ref_value(op.git, ref)
        if held == parent:
            moved = op.git.run("update-ref", ref, prepared.commit, parent, check=False)
            if not moved.ok:
                raise reconcile(f"{ref} is no longer {parent}, the exact parent the {payload['stage']} commit was built "
                                f"on ({moved.stderr.strip()}); it is never moved onto another tip", REASON_RECORD_CONFLICT)
        elif held != prepared.commit:
            raise reconcile(f"{ref} is at {held}, neither the exact parent {parent} nor the prepared {payload['stage']} "
                            "commit; nothing is rebased, reset or amended", REASON_RECORD_CONFLICT)
    commit = prepared_facts[FACT_PREPARED_COMMIT]
    if workcommit.ref_value(op.git, ref) != commit:
        raise reconcile(f"{ref} was not read back holding the prepared commit {commit}", REASON_RECORD_CONFLICT)
    workcommit.refresh_real_index(op.git, parent, commit)
    mutation.mark_effect(index, {**prepared_facts, FACT_REF_MOVED: True})
    contents = _stage_bytes(mutation, str(payload["stage"]))
    entries = gitcmd.tree_entries(op.root, commit, sorted(contents))
    by_path = {} if entries is None else {entry.path: entry for entry in entries}
    for path, data in contents.items():
        entry = by_path.get(path)
        if entry is None or entry.mode != _REGULAR or gitcmd.read_blob(op.root, entry.oid) != data:
            raise stop("review_not_persisted", f"{commit} does not hold {path} as its recorded bytes: STOP")


# =========================================================================== global-policy-evaluation (§31.41-§31.43)

def record_global_policy_evaluation(workline_root: Path,
                                    request: "review_global_policy.GlobalPolicyEvaluationRequest"
                                    ) -> GlobalPolicyEvaluationResult:
    """One immutable Global policy evaluation: evidence only, never a policy write (§31.42).

    The same root lock, runtime, authorization and exact-scope Git discipline;
    one immutable evaluation record, its exact commit and its exact
    publication. ``adjust`` / ``rollback`` only say that a new reviewed
    Candidate is required; ``global-policy.yaml`` is never written here (B's
    closed effect set for this sub-operation has no policy replace).
    """
    root_maintenance.require_root_invocation()
    record = review_global_policy.evaluation_request_record(request)
    digest = review_global_policy.request_digest(record)
    with root_maintenance.root_operation(Path(workline_root), OPERATION_EVALUATION, {"request_digest": digest}) as lock:
        op, pending = _enter(Path(workline_root), OPERATION_EVALUATION, request, record, digest, None, lock)
        if pending is not None:
            mutation = _reopen(op, pending)  # a resume of its own pending mutation is not re-gated (Amendment 12)
        else:
            # Amendment 12: the stranded-change gate is a root-maintenance entry condition - no evaluation is
            # recorded against a change whose Kp identity was never durably saved (nothing allocated before it)
            _require_no_stranded_change(op)
            # the one exact path names the evaluation ID: allocated right before the open, stored by it (Amendment 4)
            allocated = ids.new_id("review_global_policy_evaluation")
            mutation = _open(op, write_scope=[_LAYOUT.global_evaluation_rel(allocated)],
                             reserved={EVALUATION_KEY: allocated})
        if not _stage_planned(mutation, STAGE_EVALUATION):
            with _abandoned_on_stop(mutation):
                _plan_evaluation(op, mutation)
        evaluation_id = mutation.reserved(EVALUATION_KEY)
        if evaluation_id is None:
            raise reconcile(f"root mutation {mutation.mutation_id} holds no evaluation reservation", REASON_RECORD_CONFLICT)
        path = _LAYOUT.global_evaluation_rel(evaluation_id)
        _settle(op, mutation)
        commit = _c2_evaluation(op, mutation, path)
        if mutation.record.get("publication") is not None:
            _push_stage(op, mutation, STAGE_EVALUATION, commit)
        mutation.complete()
        stored = _committed_record(op, commit, path, review_global_policy.parse_evaluation_record) or {}
        return GlobalPolicyEvaluationResult(
            evaluation_id=evaluation_id, global_policy_change_id=str(stored.get("global_policy_change_id")),
            result=str(stored.get("result")), next_action=str(stored.get("next_action")), commit=commit,
            mutation_id=mutation.mutation_id,
        )


def _plan_evaluation(op: _Op, mutation: Any) -> None:
    evaluation_id = mutation.reserve_id(EVALUATION_KEY, "review_global_policy_evaluation")  # the first-open one
    change_id = str(op.record.get("global_policy_change_id"))
    change = _committed_record(op, op.entry.head, _LAYOUT.global_change_rel(change_id),
                               review_global_policy.parse_change_record)
    if change is None:
        raise _c_stop("evaluation_invalid", f"the Global policy change {change_id} is not committed at HEAD; an "
                                            "evaluation binds a committed change only, and nothing is written")
    snapshots = _source_snapshots(op)
    clusters = review_global_policy.clustering(snapshots)
    found = review_global_policy.evaluation_record(op.record, evaluation_id=evaluation_id, change=change,
                                                   evaluated_global=op.entry.global_policy, snapshots=snapshots,
                                                   clusters=clusters)
    _plan_stage(op, mutation, STAGE_EVALUATION, [
        (root_maintenance.EFFECT_EVALUATION_CREATE, _LAYOUT.global_evaluation_rel(evaluation_id), _text(found)),
    ], f"chore(workline): record global policy evaluation {evaluation_id}")


__all__ = [
    "CODE_BEFORE_STATE_CONFLICT",
    "CODE_GLOBAL_POLICY_UNAVAILABLE",
    "CODE_STALE_CANDIDATE",
    "CHANGE_KEY",
    "EVALUATION_KEY",
    "GlobalPolicyChangeResult",
    "GlobalPolicyEvaluationResult",
    "GlobalPolicyReview",
    "OPERATION",
    "OPERATION_EVALUATION",
    "OWNER",
    "PACKET_KEY",
    "REASON_PERSISTED_MISMATCH",
    "REASON_PUBLICATION_INVALID",
    "REASON_RECORD_CONFLICT",
    "REASON_RUN_UNRECOVERED",
    "RECONCILE_REASONS",
    "REUSED_CODES",
    "REUSED_REASONS",
    "ROOT_COMMIT_CONTRACT",
    "STATUS_APPLIED",
    "STATUS_HUMAN_WAIT",
    "STATUS_NOT_AUTHORIZED",
    "STOP_CODES",
    "change_global_policy",
    "reconcile",
    "record_global_policy_evaluation",
    "stop",
    "validate_global_policy_review",
]
