"""``project-policy-change``: the one owner of Project-local Review policy mutation (P6, §15.20 / §30.15).

A distinct canonical internal operation - no Project-facing domain Skill, no
second lifecycle controller. ``skills/review`` coordinates it: the Policy Review
(``project-policy-change-v1``) produces authorization only, and this owner
alone writes the Project Profile and its policy evidence and finalizes Git:

```text
Project context + execution lock      oplock.project_operation
pending mutation open / resume         MutationController.open (exact request identity)
Candidate freeze                       policy_change_id reserved first: the proposed Profile binds it
fixed meta-verifier                    policy.candidate_problems, before any effect and again before the seal
Policy Review                          G1 discovery accept -> G2 settle + raw reports -> G3 adjudication accept
                                       -> G4 settle + adjudication + P5 Finding summaries
                                       -> G5 seal + Receipt   (blocking: terminal at G4; HUMAN: HUMAN_WAIT at G4;
                                                               no Repair Batch branch)
persistence                            change record + exact Profile CAS -> Kp -> C-2(Kp) -> publish exact Kp
                                       -> Policy Consumption v3 + consumed Run summary -> Km -> C-2(Km)
                                       -> publish exact Km -> complete
```

No push before proof, no force, no history rewrite; a remote-less Project keeps
the same local proof and commit boundaries without a push. Evaluations are
evidence only: one immutable create and an ordinary exact Git finalization by
the same owner (:func:`record_policy_evaluation`).

A Policy Review at G4 HUMAN_WAIT stays the same canonical HUMAN_WAIT Run (CP
ruling R8): the owner completes its mutation there, and every later call of the
same request - after that completion or after its runtime record was lost -
rediscovers that Run by canonical recovery discovery and returns ``human_wait``
with its canonical ``policy_change_id`` and Review IDs. Nothing sets it aside,
replaces it, reserves a Receipt for it or guesses a Human answer; the policy
kind has no Human-decision continuation input.

It owns physical Profile mutation and policy evidence only, never Project
lifecycle: nothing here reads or writes a Roadmap, Phase or Work.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
from typing import Any, Iterator

from . import gitcmd, gitops
from .committed_view import CommittedReadError
from .errors import ReconcileRequired, StopError, ValidationError
from .mutation import Effect, Mutation, MutationController, WriteScope, abandon_on_stop, bind_policy_recovery
from .oplock import project_operation
from .review import checkout, gate, history, p4, policy, records, serialize
from .review import recovery as review_recovery
from .review import committed as review_committed
from .review import paths as review_paths
from .review.store import ReviewStore
from .store import ProjectStore

OWNER = policy.OWNER
OPERATION = policy.OPERATION
OPERATION_EVALUATION = policy.OPERATION_EVALUATION
GENERATION_OPERATION = "review-generation"

NOTE_BINDING = "policy_binding"
NOTE_CANDIDATE = "policy_candidate"
NOTE_PUBLICATION_PROOF = "policy_publication_proof"
#: ORCH-RB6-1: the earlier Policy Review Run a mutation recovered from canonical records (its owner record was lost).
NOTE_RECOVERED = "policy_recovered_run"
PROOF_CONTRACT = "review-v1-p6-policy-proof-v1"

STAGE_GENERATION = "review-generation"
STAGE_GENERATION_COMMIT = "review-generation-commit"
STAGE_POLICY = "policy-state"
STAGE_KP = "policy-commit"
STAGE_KP_PUBLICATION = "policy-publication"
STAGE_CONSUMPTION = "policy-consumption"
STAGE_KM = "policy-consumption-commit"
STAGE_KM_PUBLICATION = "policy-consumption-publication"
STAGE_EVALUATION = "policy-evaluation"
STAGE_EVALUATION_FINALIZE = "finalize"

STATUS_APPLIED = "applied"
STATUS_NOT_AUTHORIZED = "not_authorized"
STATUS_HUMAN_WAIT = "human_wait"

POLICY_CHANGE_KEY = "review-policy-change"
POLICY_EVALUATION_KEY = "review-policy-evaluation"


@dataclass(frozen=True)
class PolicyReview:
    """The Policy Review actor binding (§30.13): discovery actors and one adjudicator, each identity / version.

    The discovery actors must satisfy the PRE-CHANGE Effective Policy's
    ``required_slots`` (and its holdout plan, when an active lightening
    experiment requires one); the proposed after-state never selects the
    reviewers of the review authorizing it. There is no repair actor: a Policy
    Review has no Repair Batch branch.
    """

    discovery: tuple[p4.DiscoveryBinding, ...]
    adjudicator: p4.ActorBinding
    holdout_discovery: tuple[p4.DiscoveryBinding, ...] = ()


@dataclass(frozen=True)
class PolicyChangeResult:
    """How a ``project-policy-change`` invocation ended."""

    status: str
    policy_change_id: str
    review_run_id: str
    receipt_id: str | None
    consumption_id: str | None
    profile_version: int | None
    profile_digest: str | None
    policy_commit: str | None
    metadata_commit: str | None
    mutation_id: str
    findings: tuple[dict[str, Any], ...]
    detail: str


@dataclass(frozen=True)
class PolicyEvaluationResult:
    evaluation_id: str
    policy_change_id: str
    result: str
    next_action: str
    commit: str | None
    mutation_id: str


def _reconcile(message: str, reason: str) -> ReconcileRequired:
    return policy.reconcile(message, reason)


def validate_policy_review(review: object) -> PolicyReview:
    """The ``review`` argument, validated before the lock and before any Project state is read."""
    if type(review) is not PolicyReview:
        raise ValidationError(f"review must be a PolicyReview, not {type(review).__name__}",
                              code="review_contract_invalid")
    problems = p4.binding_problems(review.discovery, review.adjudicator, review.adjudicator, None)
    if not isinstance(review.holdout_discovery, tuple):
        problems.append("holdout_discovery must be a tuple of DiscoveryBinding")
    else:
        for item in review.holdout_discovery:
            if type(item) is not p4.DiscoveryBinding:
                problems.append(f"a holdout discovery actor is {type(item).__name__}, not a DiscoveryBinding")
            else:
                problems.extend(p4._actor_problems(item, f"holdout discovery actor {item.viewpoint!r}"))
                try:
                    p4.discovery_slot(item.viewpoint)
                except ValidationError as exc:
                    problems.append(str(exc))
    if problems:
        raise ValidationError("invalid PolicyReview: " + "; ".join(problems), code="review_contract_invalid")
    return review


# =========================================================================== the owner entry

def change_project_policy(store: ProjectStore, request: policy.PolicyChangeRequest, *,
                          review: PolicyReview) -> PolicyChangeResult:
    """Propose, review and - when authorized - persist one Project Policy Change (§15.20, §30.15).

    The same request resumes its own unfinished mutation with the same
    ``policy_change_id``, Candidate and Review IDs; another request meets the
    pending one's write scope and is refused (reconcile required).
    """
    record = policy.request_record(request)
    validate_policy_review(review)
    digest = policy.request_digest(record)
    invocation = {
        "operation": OPERATION, "request_digest": digest,
        "review_contract": policy.POLICY_CHANGE_CONTRACT, "publication_contract": policy.POLICY_PUBLICATION_CONTRACT,
    }
    with project_operation(store, OPERATION, {"request_digest": digest}):
        checkout.require_namespace_readable(store)
        destination = gitops.ensure_push_destination(store)
        mutation = MutationController(store).open(OWNER, invocation, WriteScope(files=(review_paths.POLICY_PROFILE_REL,)))
        gitops.ensure_git_ready(store.root)
        gitops.record_preexisting_dirty(mutation, store.root)
        if mutation.effects:
            mutation.apply()
        op = _Op(store, record, digest, review)
        return _run(op, mutation, destination)


@dataclass
class _Op:
    store: ProjectStore
    request: dict[str, Any]
    request_digest: str
    review: PolicyReview

    @property
    def operation_identity(self) -> str:
        return policy.operation_identity(self.request_digest)

    @property
    def root(self):
        return self.store.root


@dataclass
class _Run:
    policy_change_id: str
    review_run_id: str
    candidate: dict[str, Any]
    effective: dict[str, Any]
    receipt_id: str | None = None
    consumption_id: str | None = None


def _run(op: _Op, mutation: Mutation, destination: Any) -> PolicyChangeResult:
    if mutation.note(NOTE_CANDIDATE) is None:
        with abandon_on_stop(mutation):
            facts = _policy_history(op.store)
            _require_no_stranded_change(facts)
            recovered = _discover(op, facts)
            if recovered is None:
                _freeze(op, mutation)
            else:
                _recover(op, mutation, recovered)
    run = _recorded_run(op, mutation)
    _resolve_pending_generation(op, mutation, run)
    with _released_when_stale(mutation):
        return _review_and_persist(op, mutation, destination, run)


@contextmanager
def _released_when_stale(mutation: Mutation) -> Iterator[None]:
    """ORCH-RB6-1-R1: a before-state that moved never strands the owner mutation holding the Profile scope.

    Every step re-proves the exact before-state before it writes
    (:func:`_require_state_current`). When it has moved, the effect-free owner
    mutation is abandoned - its committed generations stay canonical evidence
    and nothing is written - so no pending mutation keeps refusing every later
    Policy Change and evaluation of the Project. Once the Run is canonical
    (generation 1 committed), a retry of the same request finds it by
    canonical discovery and is refused the same way before any binding
    (:func:`_recover`). Before generation 1 nothing canonical names the IDs the
    released mutation reserved, so a later call of the same request is a new
    Candidate frozen on the moved state (canonical discovery finds no Run).
    Another request is a new Candidate either way. Once the policy stage is
    recorded (effects exist) nothing is released: the exact Profile CAS and
    its reconcile own that window (§30.40 "no overwrite on before mismatch").
    """
    try:
        yield
    except StopError as exc:
        if exc.code == policy.CODE_BEFORE_STATE_CONFLICT and mutation.status == "pending" and not mutation.effects:
            mutation.abandon()
        raise


def _review_and_persist(op: _Op, mutation: Mutation, destination: Any, run: "_Run") -> PolicyChangeResult:
    while True:
        review = ReviewStore(op.store)
        chain = review.gate_chain(run.review_run_id)
        latest = 0 if chain is None else chain.latest.generation
        if chain is not None:
            problems = p4.chain_problems(chain)
            if problems or p4.shape_of(chain) == p4.SHAPE_REPAIR:
                raise _reconcile(f"Policy Review Run {run.review_run_id}: " + "; ".join(problems or ["a repair shape"]),
                                 policy.REASON_CHAIN_INVALID)
        if latest == 0:
            _accept(op, mutation, run)
        elif latest == 1:
            _launch_discovery(op, mutation, run, chain)
        elif latest == 2:
            if any(task["status"] != records.TASK_SETTLED_OK for task in chain.latest.settled_tasks):
                return _finish(op, mutation, run, STATUS_NOT_AUTHORIZED, chain,
                               "a discovery task declined; the Policy Review is not authorizing and no Receipt issues")
            _accept_adjudication(op, mutation, run, chain)
        elif latest == 3:
            _adjudicate(op, mutation, run, chain)
        elif latest == 4:
            found = review.read_adjudication(run.review_run_id)
            if found.outcome == records.HUMAN_WAIT:
                return _finish(op, mutation, run, STATUS_HUMAN_WAIT, chain,
                               "the adjudication needs a Human requirement decision; no Receipt issues")
            if found.outcome != records.AUTHORIZATION_READY:
                return _finish(op, mutation, run, STATUS_NOT_AUTHORIZED, chain,
                               "a supported blocking Problem was adjudicated; a Policy Review has no Repair Batch "
                               "branch, so no Receipt issues and a changed proposal is a new Candidate")
            _seal(op, mutation, run, chain)
        elif latest == p4.SEAL_GENERATION and chain.latest.sealed:
            return _persist(op, mutation, destination, run, chain)
        else:
            raise _reconcile(f"Policy Review Run {run.review_run_id} is at generation {latest}, which this owner never "
                             "writes", policy.REASON_CHAIN_INVALID)


# --------------------------------------------------------------------------- recovery after runtime loss (ORCH-RB6-1)

class _PolicyHistory:
    """What HEAD's history, HEAD's tree and the working tree hold of the policy changes (ORCH-RB6-1-R2).

    ``added``: change ids whose record a commit of HEAD's history added;
    ``present``: change id -> the Receipts its record names, for every record
    HEAD's tree or the working tree holds (a record that does not read names
    none, so it is never consumed); :meth:`consumptions`: every COMMITTED
    Consumption - HEAD's tree or one a commit of HEAD's history added, never
    the working tree (RB6FR1-2) - read only once a policy change was ever
    added or is present, or once a Run with a Receipt is classified
    (ORCH-RB6-1-N3: a Project with no policy history never reads them, so an
    unreadable unrelated Consumption cannot refuse its Policy Changes).
    Facts only, read the way planning's recovery row b reads
    registrations: no commit identity is inferred from them and nothing is
    adopted.
    """

    def __init__(self, store: ProjectStore, head: str | None, added: frozenset[str],
                 present: dict[str, frozenset[str]]) -> None:
        self._store = store
        self._head = head
        self.added = added
        self.present = present
        self._consumptions: list[Any] | None = None
        if added or present:
            self.consumptions()

    def consumptions(self) -> list[Any]:
        if self._consumptions is None:
            self._consumptions = _consumptions_of_history(self._store, self._head)
        return self._consumptions

    def consumed(self, change_id: str, receipt_ids: "set[str] | frozenset[str]") -> bool:
        """Whether a v3 Policy Consumption names ``change_id`` under one of ``receipt_ids`` (ORCH-RB6-1-N4: the change
        is consumed by the Consumption of its own Receipt, never by one that merely names its id)."""
        return any(isinstance(found, records.PolicyConsumption)
                   and str(found.persisted_policy["policy_change_id"]) == change_id
                   and str(found.receipt_id) in receipt_ids for found in self.consumptions())

    def consumed_receipts(self) -> frozenset[str]:
        """The Receipts any Consumption names."""
        return frozenset(str(found.receipt_id) for found in self.consumptions())


def _unread(exc: Exception) -> ReconcileRequired:
    return ReconcileRequired(f"the policy changes and Consumptions of HEAD's history do not read ({exc}); no Policy "
                             "Change is begun or recovered on them: reconcile required",
                             reason="review_recovery_incomplete")


def _policy_history(store: ProjectStore) -> _PolicyHistory:
    review = ReviewStore(store)
    repo = store.root
    changes_dir = f"{review_paths.POLICY_DIR}/{review_paths.POLICY_CHANGES}"
    try:
        head = gitcmd.head_commit(repo)
        present: dict[str, set[str]] = {}
        readers: list[ReviewStore] = [review]
        added: set[str] = set()
        if head is not None:
            for _adding, names in review_committed.added_in_history(repo, head, [changes_dir]):
                added |= {name[len(changes_dir) + 1:-len(".yaml")] for name in names
                          if name.startswith(changes_dir + "/") and name.endswith(".yaml")}
            readers.append(review_committed.CommittedReviewStore(repo, head))
        for reader in readers:
            for change_id in reader.policy_change_ids():
                receipts = present.setdefault(change_id, set())
                try:
                    receipts.add(str(reader.read_policy_change(change_id)["receipt_id"]))
                except ValidationError:
                    pass  # a record that does not read binds no Receipt: it is never consumed (stranded)
        return _PolicyHistory(store, head, frozenset(added),
                              {change_id: frozenset(receipts) for change_id, receipts in present.items()})
    except (ValidationError, CommittedReadError) as exc:
        raise _unread(exc) from exc


def _consumptions_of_history(store: ProjectStore, head: str | None) -> list[Any]:
    """Every COMMITTED Consumption: HEAD's tree, and every one a commit of HEAD's history added.

    Never the working tree (RB6FR1-2): a Consumption that is only written - the
    §30.40 windows 16-17 between the Consumption stage and Km, or a hand-written
    file - proves nothing about a committed change record, so such a change
    stays stranded (``review_p6_run_unrecovered``, the manual reconciliation
    boundary), symmetric with the Kp window. Change records may still be read
    from the working tree (``_policy_history``): that direction only refuses.
    """
    repo = store.root
    consumptions: list[Any] = []
    try:
        if head is not None:
            consumptions += list(review_committed.CommittedReviewStore(repo, head).consumptions())
            for adding, names in review_committed.added_in_history(repo, head, [review_paths.CONSUMPTIONS_DIR]):
                for name in names:
                    raw = gitcmd.blob_at(repo, adding, name)
                    if raw is None:
                        raise ValidationError(f"the Consumption {name} added by {adding} cannot be read",
                                              code="review_record_invalid")
                    found, _ = review_committed.parse_record(raw, f"{name} at {adding}", records.consumption_from_record)
                    consumptions.append(found)
    except (ValidationError, CommittedReadError) as exc:
        raise _unread(exc) from exc
    return consumptions


def _require_no_stranded_change(facts: _PolicyHistory) -> None:
    """ORCH-RB6-1: no Policy Change starts while an applied change has no Consumption (any request).

    A change record HEAD's tree or the working tree holds without the
    committed v3 Consumption of its own Receipt is a policy-state stage whose Kp / Km
    identity was not durably saved: it is never inferred from Git history (no
    commit is adopted), never published by this owner, and no new Candidate is
    built on top of it - ``review_p6_run_unrecovered``, reconcile required (the
    manual reconciliation boundary). One a commit of HEAD's history added and a
    later commit removed (a revert) is no longer built upon: it stops only its
    own request's Run (``_classifier``, row b), never the other requests.
    """
    stranded = sorted(change_id for change_id, receipts in facts.present.items()
                      if not receipts or not all(facts.consumed(change_id, {receipt}) for receipt in receipts))
    if stranded:
        raise _reconcile(f"policy change {', '.join(stranded)} is stored and has no Policy Consumption: its policy "
                         "commit identity was never durably saved, so it is neither inferred from Git history nor "
                         "built upon", policy.REASON_RUN_UNRECOVERED)


def _settled(review: ReviewStore, chain: Any) -> str | None:
    """How an earlier Policy Review Run ended for good, or ``None`` when it is not settled.

    ``not_authorized``: a declining G2, or a G4 neither AUTHORIZATION_READY nor
    HUMAN_WAIT (a supported blocking Problem: terminal, no Receipt, no Repair
    Batch branch), so the same request is a new Run. ``consumed`` is row b's
    (:func:`_classifier`). A G4 HUMAN_WAIT is never settled (CP ruling R8): it
    stays the same canonical HUMAN_WAIT Run, which the same request rediscovers
    and the owner returns as ``human_wait`` again (:func:`_human_wait`). Nothing
    else is settled either: an open G1-G3, an authorizing G4 not sealed, a
    sealed Receipt not consumed.
    """
    latest = chain.latest
    if latest.generation == 2 and any(task["status"] != records.TASK_SETTLED_OK for task in latest.settled_tasks):
        return "not_authorized"
    if latest.generation == p4.ADJUDICATION_SETTLE_GENERATION:
        found = review.read_adjudication(chain.review_run_id)
        return None if found.outcome in (records.AUTHORIZATION_READY, records.HUMAN_WAIT) else "not_authorized"
    return None


def _human_wait(review: ReviewStore, chain: Any) -> bool:
    """Whether the Run stands at canonical G4 HUMAN_WAIT: its adjudication needs a Human requirement decision."""
    return chain.latest.generation == p4.ADJUDICATION_SETTLE_GENERATION \
        and review.read_adjudication(chain.review_run_id).outcome == records.HUMAN_WAIT


def _incomplete(review_run_id: str, problem: str) -> ReconcileRequired:
    return ReconcileRequired(
        f"Policy Review Run {review_run_id} does not reconstruct: {problem}; a matching Review Run that cannot be shown "
        "whole is never replaced by a new Run: reconcile required",
        reason="review_recovery_incomplete",
    )


def _reconstruction_problem(review: ReviewStore, found: Any) -> str | None:
    """ORCH-RB6-1-R3 (row e): what an owner-lost Run must re-prove before it may authorize anything.

    The policy shape (the Policy Review kind and target, discovery ->
    adjudication -> seal, never a repair branch or a generation past the seal),
    every accepted task's provenance at its accepting generation (the shared
    P4 reconstruction), and a sealed generation 5 bound field by field to its
    Receipt and to the Policy Change stage.
    """
    from .review.validate import GATE_RECEIPT_BINDING

    chain = found.chain
    first, latest = chain.generations[0], chain.latest
    if first.review_kind != policy.REVIEW_KIND or first.target_identity != policy.TARGET_IDENTITY:
        return "it is not a Policy Review of the project-policy target"
    if p4.chain_problems(chain) or p4.shape_of(chain) == p4.SHAPE_REPAIR or latest.generation > p4.SEAL_GENERATION:
        return "it is not discovery -> adjudication -> seal (a Policy Review has no repair branch and no generation 6)"
    problem = review_recovery.p4_reconstruction_problem(review, found)
    if problem:
        return problem
    if latest.sealed:
        receipt = review.read_receipt(str(latest.receipt_id))
        for gate_field, receipt_field in GATE_RECEIPT_BINDING:
            if getattr(latest, gate_field) != getattr(receipt, receipt_field):
                return f"its Receipt's {receipt_field} is not generation 5's {gate_field}"
        if latest.authorized_operation_stage != policy.AUTHORIZED_OPERATION_STAGE:
            return "its seal authorizes another stage than the Policy Change"
    return None


def _classifier(facts: _PolicyHistory):
    def classify(store: ProjectStore, review: ReviewStore, head: str | None, found: Any, named_aside: set[str],
                 currency: Any) -> str | None:
        """The policy kind's rows of canonical recovery discovery (§30.40; SKILL Recovery classification).

        ```text
        not the Policy Review contract                           incomplete (reconcile)
        its change record added in HEAD's history or present     b: the Policy Consumption of it under the Run's own
                                                                    Receipt -> consumed; else
                                                                    review_p6_run_unrecovered (never re-applied)
        a Consumption of its Receipt without its change record   incomplete
        G2 declined / G4 neither ready nor HUMAN_WAIT            not_authorized (terminal: the request is a new Run)
        named by another matching Run                            set_aside (an explicit Human recovery disposition)
        does not reconstruct                                     e: incomplete
        G4 HUMAN_WAIT                                            recoverable as the same canonical HUMAN_WAIT Run
                                                                    (CP R8): returned human_wait, nothing re-judged
                                                                    against the current state, as P4 planning / Work
                                                                    exempt HUMAN_WAIT from currency
        otherwise                                                recoverable (its before-state is
                                                                    re-proven before binding: f, in _recover)
        ```
        """
        run_id = found.review_run_id
        if found.contract != policy.POLICY_CHANGE_CONTRACT:
            raise _reconcile(f"Review Run {run_id} of the Policy Review kind binds contract {found.contract}",
                             policy.REASON_CHAIN_INVALID)
        change_id = str((found.material or {}).get("policy_change_id"))
        receipts = {str(generation.receipt_id) for generation in found.chain.generations if generation.receipt_id}
        if change_id in facts.added or change_id in facts.present:
            if facts.consumed(change_id, receipts):
                return "consumed"
            raise _reconcile(
                f"the change record of Policy Review Run {run_id} ({change_id}) was committed and has no Policy "
                "Consumption: its policy commit identity was never durably saved, so the change is neither re-applied "
                "nor inferred from Git history (a revert does not reconcile it)", policy.REASON_RUN_UNRECOVERED)
        if receipts and receipts & facts.consumed_receipts():
            raise _incomplete(run_id, "a Consumption names its Receipt and no commit added its change record")
        try:
            settled = _settled(review, found.chain)
        except ValidationError as exc:
            raise _incomplete(run_id, str(exc)) from exc
        if settled is not None:
            return settled
        if run_id in named_aside:
            return "set_aside"
        try:
            problem = _reconstruction_problem(review, found)
        except ValidationError as exc:
            problem = str(exc)
        if problem:
            raise _incomplete(run_id, problem)
        return None

    return classify


def _adapter(facts: _PolicyHistory) -> review_recovery.RecoveryAdapter:
    # ORCH-RB6-1-R9: a Policy Review kind Run whose TaskInputs bind no P4-family contract is never classified
    return review_recovery.RecoveryAdapter(
        shape=lambda chain: "binds no Policy Review contract in its generation-1 TaskInputs",
        named=lambda review, found: [], classify=_classifier(facts))


def _discover(op: _Op, facts: _PolicyHistory) -> Any:
    """ORCH-RB6-1: canonical recovery discovery of this request's earlier Policy Review Run - the shared mechanics.

    Runs only when no pending mutation of this invocation holds a frozen
    Candidate (its owner record was lost, or its owner completed, or it never
    froze). The Runs of the Policy Review kind and this exact operation
    identity (``project-policy-change:<request digest>``) in HEAD's history and
    the working tree are proven whole; settled ones (``not_authorized``,
    ``consumed``) are set aside; exactly one recoverable Run is resumed with its
    canonical IDs - a Run at G4 HUMAN_WAIT included, which the owner returns as
    ``human_wait`` again and never sets aside or replaces (CP R8) - several are
    ``review_recovery_ambiguous``, a malformed one ``review_recovery_incomplete``.
    None: a new Run.
    """
    return review_recovery.discover_kind(op.store, policy.REVIEW_KIND, op.operation_identity, _adapter(facts)).recoverable


def _recover(op: _Op, mutation: Mutation, found: Any) -> None:
    """Resume the one recoverable earlier Run with its canonical IDs, before any effect (ORCH-RB6-1).

    Its Candidate is its committed snapshot; its frozen Effective Policy is the
    one its generation-1 requests bind; its policy change id, Run, discovery
    tasks, adjudication task and (sealed) Receipt are bound from its records,
    never generated. What it never made canonical (a Receipt not yet sealed,
    the Consumption) is reserved as a fresh owner does. The discovery actors are
    held to the frozen policy (RB6C-D2); every later step re-proves the exact
    before-state, as any resume does.

    ORCH-RB6-1-R1 / R3: before anything is bound, the recovered Run is
    re-proven as an owner-lost Run must be (the trust anchor of the lost owner
    record is gone): its Candidate is this request's and is the G1 Candidate;
    its frozen Effective Policy is the one G1 binds and the Candidate was
    decided under; the exact before-state still holds (a moved Profile,
    Effective Policy or Global baseline is ``review_p6_before_state_conflict``
    with nothing reserved or pending - the same request is a stale proposal,
    another request a new Candidate); and the fixed meta-verifier still accepts
    the Candidate. Discovery already proved it whole, its task provenance and
    its sealed Receipt binding (:func:`_classifier`).

    CP R8: a Run at canonical G4 HUMAN_WAIT is recovered as that same Run. It
    is re-proven as this request's Candidate under its frozen Effective
    Policy, and nothing about it is re-judged against the current state or the
    invocation's actors - no before-state, no meta-verifier, no discovery-slot
    check (RB6FR1-4), exactly as P4 planning and Work recovery exempt a G4
    HUMAN_WAIT Run from currency - because it authorizes, launches and writes
    nothing: the owner reads its G4 and returns ``human_wait``. Only
    its canonical IDs are bound, in this runtime mutation that then completes;
    no Receipt or Consumption is reserved and the scope is never extended.
    """
    store = op.store
    review = ReviewStore(store)
    chain = found.chain
    run_id = found.review_run_id
    candidate = dict(found.material or {})
    first = chain.generations[0]
    if candidate.get("request_digest") != op.request_digest or first.operation_identity != op.operation_identity \
            or policy.candidate_hash(candidate) != first.candidate_hash:
        raise _reconcile(f"the recoverable Policy Review Run {run_id} is not this request's Candidate",
                         policy.REASON_CHAIN_INVALID)
    try:
        effective = p4.run_effective_policy(review, chain)
    except ValidationError as exc:
        raise _reconcile(f"Policy Review Run {run_id}'s frozen Effective Policy does not read: {exc}",
                         policy.REASON_CHAIN_INVALID) from exc
    try:
        waiting = _human_wait(review, chain)
    except ValidationError as exc:
        raise _incomplete(run_id, f"its adjudication does not read: {exc}") from exc
    if effective is None:
        raise _reconcile(f"Policy Review Run {run_id} binds no frozen Effective Policy", policy.REASON_CHAIN_INVALID)
    frozen_hash = policy.effective_policy_hash(effective)
    if frozen_hash != first.effective_policy_hash or frozen_hash != candidate.get("before_effective_policy_digest"):
        raise _reconcile(f"Policy Review Run {run_id}'s frozen Effective Policy is not the one its generation 1 and its "
                         "Candidate bind", policy.REASON_CHAIN_INVALID)
    if not waiting:
        # RB6FR1-4: a waiting Run launches nothing, so the invocation's actors are not judged for it
        problem = policy.discovery_slots_problem(effective, op.review.discovery, op.review.holdout_discovery)
        if problem is not None:
            raise policy.stop(*problem)
        state = _require_before_state(op, candidate)
        policy.require_candidate(candidate, state, review)
    bindings = [
        (f"{POLICY_CHANGE_KEY}:{op.request_digest}", str(candidate["policy_change_id"]), "review_policy_change"),
        (gate.review_run_key(policy.REVIEW_KIND, policy.TARGET_IDENTITY), run_id, "review_run"),
    ]
    for task in chain.generations[0].accepted_tasks:
        bindings.append((gate.review_task_key(run_id, str(task["task_slot"])), str(task["task_id"]), "review_task"))
    for generation in chain.generations[1:]:
        for task in generation.accepted_tasks:
            if task["task_slot"] == p4.SLOT_ADJUDICATOR:
                bindings.append((gate.review_task_key(run_id, p4.SLOT_ADJUDICATOR), str(task["task_id"]), "review_task"))
    if chain.latest.sealed and chain.latest.receipt_id:
        bindings.append((gate.review_receipt_key(run_id, p4.SEAL_GENERATION), str(chain.latest.receipt_id),
                         "review_receipt"))
    bind_policy_recovery(mutation, sorted(set(bindings)), (NOTE_RECOVERED, {"review_run_id": run_id}))
    if not waiting:
        receipt_id = mutation.reserve_id(gate.review_receipt_key(run_id, p4.SEAL_GENERATION), "review_receipt")
        mutation.reserve_id(gate.review_consumption_key(receipt_id), "review_consumption")
        change_path = review_paths.policy_change_rel(str(candidate["policy_change_id"]))
        if change_path not in mutation.scope.files:
            mutation.extend_scope(files=[change_path])
    branch = gitcmd.current_branch_ref(store.root)
    head = gitcmd.head_commit(store.root)
    if branch is None or head is None:
        raise StopError("HEAD is on no branch or has no commit, so the policy change binding cannot be recorded: STOP",
                        code="detached_head")
    mutation.set_note(NOTE_BINDING, {"branch": branch, "head": head})
    mutation.set_note(NOTE_CANDIDATE, {"candidate": candidate, "effective": effective})


# --------------------------------------------------------------------------- the freeze (before any effect)

def _freeze(op: _Op, mutation: Mutation) -> None:
    """Reserve the policy change ID, build and verify the Candidate, reserve the Review IDs - before any effect."""
    store = op.store
    reader = ReviewStore(store)
    state = policy.resolve_policy_state(reader, store.workline_root())
    problem = policy.discovery_slots_problem(state.effective, op.review.discovery, op.review.holdout_discovery)
    if problem is not None:
        raise policy.stop(*problem)
    policy_change_id = mutation.reserve_id(f"{POLICY_CHANGE_KEY}:{op.request_digest}", "review_policy_change")
    candidate = policy.build_candidate(op.request, policy_change_id, state, reader)
    policy.require_candidate(candidate, state, reader)
    run_id = mutation.reserve_id(gate.review_run_key(policy.REVIEW_KIND, policy.TARGET_IDENTITY), "review_run")
    for binding in _discovery_bindings(op):
        mutation.reserve_id(gate.review_task_key(run_id, binding.task_slot), "review_task")
    receipt_id = mutation.reserve_id(gate.review_receipt_key(run_id, p4.SEAL_GENERATION), "review_receipt")
    mutation.reserve_id(gate.review_consumption_key(receipt_id), "review_consumption")
    mutation.extend_scope(files=[review_paths.policy_change_rel(policy_change_id)])
    branch = gitcmd.current_branch_ref(store.root)
    head = gitcmd.head_commit(store.root)
    if branch is None or head is None:
        raise StopError("HEAD is on no branch or has no commit, so the policy change binding cannot be recorded: STOP",
                        code="detached_head")
    checkout.require_namespace_readable(store)
    mutation.set_note(NOTE_BINDING, {"branch": branch, "head": head})
    mutation.set_note(NOTE_CANDIDATE, {"candidate": candidate, "effective": state.effective})


def _discovery_bindings(op: _Op) -> list[p4.DiscoveryBinding]:
    return sorted(op.review.discovery, key=lambda b: b.viewpoint) + sorted(op.review.holdout_discovery,
                                                                         key=lambda b: b.viewpoint)


def _recorded_run(op: _Op, mutation: Mutation) -> _Run:
    frozen = mutation.note(NOTE_CANDIDATE) or {}
    candidate = frozen.get("candidate")
    effective = frozen.get("effective")
    if not isinstance(candidate, dict) or not isinstance(effective, dict):
        raise _reconcile(f"the policy change mutation {mutation.id} holds no frozen Candidate", policy.REASON_CHAIN_INVALID)
    policy_change_id = mutation.reserved(f"{POLICY_CHANGE_KEY}:{op.request_digest}")
    run_id = mutation.reserved(gate.review_run_key(policy.REVIEW_KIND, policy.TARGET_IDENTITY))
    if policy_change_id is None or run_id is None or candidate.get("policy_change_id") != policy_change_id:
        raise _reconcile(f"the policy change mutation {mutation.id} does not hold its reserved identities",
                         policy.REASON_CHAIN_INVALID)
    receipt_id = mutation.reserved(gate.review_receipt_key(run_id, p4.SEAL_GENERATION))
    consumption_id = None if receipt_id is None else mutation.reserved(gate.review_consumption_key(receipt_id))
    return _Run(policy_change_id, run_id, candidate, effective, receipt_id, consumption_id)


def _require_binding(op: _Op, mutation: Mutation) -> dict[str, str]:
    binding = mutation.note(NOTE_BINDING)
    repo = op.root
    if not isinstance(binding, dict) or gitcmd.current_branch_ref(repo) != binding.get("branch"):
        raise _reconcile(f"the policy change mutation {mutation.id} is bound to {binding}, and HEAD is not on that branch",
                         policy.REASON_CHAIN_INVALID)
    head = gitcmd.head_commit(repo)
    if head is None or gitcmd.descends_from(repo, head, str(binding.get("head"))) is not True:
        raise _reconcile(f"HEAD no longer holds the commit the policy change was bound at ({binding.get('head')})",
                         policy.REASON_CHAIN_INVALID)
    return dict(binding)


def _require_discovery_actors(op: _Op, run: _Run) -> None:
    """RB6C-D2: the invocation's discovery (and holdout) actors satisfy the FROZEN pre-change Effective Policy.

    §30.13: the pre-change policy picks the reviewer count, and the after-state
    never selects fewer for the review authorizing it. The freeze checks it
    once; a retry of the same request may bind another PolicyReview, so every
    step that accepts or launches discovery - G1 included, on every resume -
    checks it again against the Effective Policy frozen in the Candidate note,
    before anything is written or launched. Never trust the freeze alone.
    """
    problem = policy.discovery_slots_problem(run.effective, op.review.discovery, op.review.holdout_discovery)
    if problem is not None:
        code, message = problem
        raise policy.stop(code, f"{message}; the Policy Review resumes only with discovery actors sufficient for the "
                                "pre-change Effective Policy it froze, and nothing is written or launched")


def _require_state_current(op: _Op, run: _Run) -> policy.PolicyState:
    """The exact before-state the Candidate was decided against still holds - or fail closed (§30.37)."""
    return _require_before_state(op, run.candidate)


def _require_before_state(op: _Op, candidate: dict[str, Any]) -> policy.PolicyState:
    """The exact before-state ``candidate`` was decided against, re-proven now; ``review_p6_before_state_conflict``."""
    reader = ReviewStore(op.store)
    # The Profile moved since the freeze (any bytes, valid or not): a before-state conflict, named as one before
    # the new Profile is judged at all - a changed proposal is a later new Candidate.
    try:
        moved = reader.profile_digest() != candidate["before_profile"]["digest"]
    except ValidationError:
        moved = True
    if moved:
        raise policy.stop(policy.CODE_BEFORE_STATE_CONFLICT,
                          "the Project Profile is no longer the exact before-state the PolicyChangeCandidate was "
                          "decided against; nothing is written, and a changed proposal is a later new Candidate")
    state = policy.resolve_policy_state(reader, op.store.workline_root())
    if candidate["before_profile"] != {"profile_version": state.profile_version, "digest": state.profile_digest} \
            or candidate["before_effective_policy_digest"] != state.effective_hash \
            or candidate["global_baseline_digest"] != state.baseline.digest:
        raise policy.stop(policy.CODE_BEFORE_STATE_CONFLICT,
                          "the Project Profile, Effective Policy or Global baseline is no longer the exact before-state "
                          "the PolicyChangeCandidate was decided against; nothing is written, and a changed proposal is "
                          "a later new Candidate")
    return state


# --------------------------------------------------------------------------- generation mutations

def _generation_invocation(mutation: Mutation, run: _Run, generation: int, transition: str,
                           gate_record: records.GateGeneration, receipt_id: str | None) -> dict[str, Any]:
    return {
        "operation": GENERATION_OPERATION,
        "review_contract": policy.POLICY_CHANGE_CONTRACT,
        "policy_mutation_id": mutation.id,
        "review_kind": policy.REVIEW_KIND,
        "review_run_id": run.review_run_id,
        "generation": generation,
        "transition": transition,
        "candidate_hash": gate_record.candidate_hash,
        "review_context_hash": gate_record.review_context_hash,
        "effective_policy_hash": gate_record.effective_policy_hash,
        "obligation_digest": gate_record.obligation_digest,
        "receipt_id": receipt_id,
    }


def _generation_message(generation: int, review_run_id: str) -> str:
    return f"chore(workline): record policy review generation {generation} of {review_run_id}"


def _require_committed(store: ProjectStore, expected: dict[str, bytes]) -> None:
    """``gate.require_persisted`` plus the blob check: HEAD holds each path as a 100644 blob of exactly these bytes."""
    relatives = sorted(expected)
    gate.require_persisted(store, relatives)
    head = gitcmd.head_commit(store.root)
    entries = None if head is None else gitcmd.tree_entries(store.root, head, relatives)
    if entries is None:
        raise StopError("git cannot list the committed Review records: STOP", code="review_persistence_unknown")
    by_path = {entry.path: entry for entry in entries}
    for relative in relatives:
        entry = by_path.get(relative)
        data = None if entry is None else gitcmd.read_blob(store.root, entry.oid)
        if entry is None or entry.type != "blob" or entry.mode != "100644" or data != expected[relative]:
            raise StopError(f"{relative} is not committed at HEAD as a 100644 blob of its canonical bytes: STOP",
                            code="review_not_persisted")


def _finish_generation(store: ProjectStore, gen: Mutation) -> None:
    stage = gen.stage_effects(STAGE_GENERATION)
    paths = [effect["payload"]["path"] for effect in stage]
    expected = {effect["payload"]["path"]: effect["payload"]["content"].encode("utf-8") for effect in stage}
    gen.apply()
    if not gen.has_stage(STAGE_GENERATION_COMMIT):
        gitops.require_no_planning_transform(store.root, paths)
        checkout.require_checkout_capability(store, paths)
        message = _generation_message(int(gen.invocation["generation"]), str(gen.invocation["review_run_id"]))
        gen.add_effects(STAGE_GENERATION_COMMIT, [gitops.review_commit_effect(store, message, paths)])
        gen.apply()
    _require_committed(store, expected)
    gen.complete()


def _start_generation(op: _Op, mutation: Mutation, run: _Run, generation: int, transition: str,
                      gate_record: records.GateGeneration, extra: list[tuple[str, dict[str, Any]]],
                      receipt_id: str | None = None) -> None:
    """Start, apply, commit and complete the generation mutation writing ``gate_record`` (and ``extra``)."""
    store = op.store
    _require_binding(op, mutation)
    scope = gate.next_generation_scope(store, run.review_run_id)
    if scope.generation != generation:
        raise _reconcile(f"Policy Review Run {run.review_run_id}'s next generation is {scope.generation}, not "
                         f"{generation}", policy.REASON_CHAIN_INVALID)
    if transition == p4.TRANSITION_ACCEPT:
        writes = list(extra) + [(scope.gate_path, gate_record.to_record())]
    else:
        writes = [(scope.gate_path, gate_record.to_record())] + list(extra)
    invocation = _generation_invocation(mutation, run, generation, transition, gate_record, receipt_id)
    files = tuple(scope.files) + tuple(path for path, _ in extra)
    gen = MutationController(store).open(OWNER, invocation, WriteScope(files=files))
    record_paths = [path for path, _ in writes]
    with abandon_on_stop(gen):
        gitops.record_preexisting_dirty(gen, store.root)
        gitops.ensure_separable_before_effects(gen, record_paths)
        if not gen.has_stage(STAGE_GENERATION):
            gate.require_committable(store, record_paths)
            gitops.require_no_planning_transform(store.root, record_paths)
            checkout.require_checkout_capability(store, record_paths)
            gen.add_effects(STAGE_GENERATION, [Effect.create_file(path, serialize.canonical_text(record))
                                               for path, record in writes])
    _finish_generation(store, gen)


def _resolve_pending_generation(op: _Op, mutation: Mutation, run: _Run) -> None:
    """A pending generation mutation of this Run is resumed first, and nothing else is (§11.8 step 3)."""
    store = op.store
    pending = gate.pending_generation_mutations(store, run.review_run_id)
    if not pending:
        return
    if len(pending) > 1:
        raise _reconcile(f"Policy Review Run {run.review_run_id} has {len(pending)} pending generation mutations",
                         policy.REASON_CHAIN_INVALID)
    record = pending[0]
    invocation = record.get("invocation") or {}
    if record.get("owner") != OWNER or invocation.get("operation") != GENERATION_OPERATION \
            or invocation.get("policy_mutation_id") != mutation.id or invocation.get("review_run_id") != run.review_run_id:
        raise _reconcile(f"the pending generation mutation {record.get('mutation_id')} of Policy Review Run "
                         f"{run.review_run_id} is not bound to this policy change mutation {mutation.id}",
                         policy.REASON_CHAIN_INVALID)
    gen = MutationController(store).open(OWNER, invocation, WriteScope.from_record(record.get("write_scope") or {}))
    if not gen.effects:
        gen.abandon()
        return
    generation = invocation.get("generation")
    chain = ReviewStore(store).gate_chain(run.review_run_id)
    next_number = records.FIRST_GENERATION if chain is None else chain.next_generation
    recorded = {effect["payload"]["path"]: effect["payload"]["content"] for effect in gen.stage_effects(STAGE_GENERATION)}
    fits = generation == next_number
    if not fits and chain is not None and generation == chain.latest.generation:
        gate_path = review_paths.gate_rel(run.review_run_id, int(generation))
        stored = ReviewStore(store).read_bytes(gate_path)
        fits = stored is not None and gate_path in recorded and stored == recorded[gate_path].encode("utf-8")
    allowed = p4.TRANSITIONS.get(int(generation), ()) if type(generation) is int else ()
    if not fits or invocation.get("transition") not in allowed or generation == p4.LAST_GENERATION:
        raise _reconcile(f"the pending generation mutation {gen.id} writes generation {generation} of Policy Review Run "
                         f"{run.review_run_id}, which is not its next transition", policy.REASON_CHAIN_INVALID)
    _finish_generation(store, gen)


# --------------------------------------------------------------------------- G1 .. G5

def _context(op: _Op) -> dict[str, Any]:
    baseline = policy.load_global_baseline(op.store.workline_root())
    return policy.context_record(op.store.workline_root(), baseline)


def _accept(op: _Op, mutation: Mutation, run: _Run) -> None:
    """G1: the Candidate snapshot, every discovery TaskInput (required + holdout) and the open gate, together."""
    store = op.store
    _require_discovery_actors(op, run)
    _require_state_current(op, run)
    candidate = run.candidate
    snapshot = policy.snapshot_for(candidate)
    context = _context(op)
    evidence = policy.evidence_record(candidate)
    requirement = policy.requirement(candidate)
    holdout_slots = {binding.task_slot for binding in op.review.holdout_discovery}
    task_inputs: list[records.TaskInput] = []
    for binding in _discovery_bindings(op):
        task_id = mutation.reserved(gate.review_task_key(run.review_run_id, binding.task_slot))
        if task_id is None:
            raise _reconcile(f"discovery slot {binding.task_slot} has no reserved task", policy.REASON_CHAIN_INVALID)
        envelope = p4.discovery_request(
            review_contract=policy.POLICY_CHANGE_CONTRACT, review_kind=policy.REVIEW_KIND, viewpoint=binding.viewpoint,
            candidate=candidate, context=context, requirement=requirement, candidate_generation=1, succession=None,
            set_aside_runs=(), human_decision=None, evidence_ids=[f"policy-evidence:{serialize.digest(evidence)}"],
            policy_id=p4.P6_POLICY_ID, effective_policy=run.effective,
            discovery_role=policy.ROLE_HOLDOUT if binding.task_slot in holdout_slots else policy.ROLE_REQUIRED,
        )
        task_inputs.append(p4.task_input(
            task_id=task_id, task_slot=binding.task_slot, task_kind=p4.TASK_KIND_DISCOVERY,
            actor_identity=binding.identity, actor_version=binding.version, envelope=envelope,
            candidate_hash=snapshot.candidate_hash, candidate_material_digest=serialize.digest(snapshot.to_record()),
            review_context_hash=serialize.digest(context), accepted_generation=p4.DISCOVERY_ACCEPT_GENERATION,
            policy_id=p4.P6_POLICY_ID,
        ))
    required = [(found.task_slot, found.task_id) for found in task_inputs]
    gate_one = records.GateGeneration(
        review_run_id=run.review_run_id, generation=1, previous_generation=None, previous_digest=None,
        review_kind=policy.REVIEW_KIND, target_identity=policy.TARGET_IDENTITY,
        operation_identity=op.operation_identity, candidate_hash=snapshot.candidate_hash,
        review_context_hash=serialize.digest(context), effective_policy_hash=policy.effective_policy_hash(run.effective),
        evidence_digest=serialize.digest(evidence), coverage_digest=serialize.digest(p4.coverage_record(required, [])),
        raw_report_set_digest=serialize.digest(p4.report_set_record([])),
        adjudication_digest=serialize.digest(p4.pending_adjudication_record()),
        obligation_digest=serialize.digest(p4.obligations_record(None)),
        accepted_tasks=tuple(p4.accepted_descriptor(found) for found in task_inputs), settled_tasks=(),
        status=records.GATE_STATUS_OPEN, receipt_id=None, authorized_operation_stage=None,
    )
    extra: list[tuple[str, dict[str, Any]]] = []
    if not ReviewStore(store).candidate_snapshot_exists(snapshot.candidate_hash):
        extra.append((review_paths.candidate_snapshot_rel(snapshot.candidate_hash), snapshot.to_record()))
    extra += [(review_paths.task_input_rel(found.task_id), found.to_record()) for found in task_inputs]
    _start_generation(op, mutation, run, 1, p4.TRANSITION_ACCEPT, gate_one, extra)


def _launch_discovery(op: _Op, mutation: Mutation, run: _Run, chain: Any) -> None:
    """G1 -> G2: every accepted discovery task (required and holdout) launched to its bound actor, then G2."""
    store = op.store
    _require_discovery_actors(op, run)
    review = ReviewStore(store)
    first = chain.latest
    tasks = list(first.accepted_tasks)
    wanted = [review_paths.candidate_snapshot_rel(first.candidate_hash), review_paths.gate_rel(run.review_run_id, 1)]
    wanted += [review_paths.task_input_rel(str(task["task_id"])) for task in tasks]
    _require_committed(store, {relative: (review.read_bytes(relative) or b"") for relative in wanted})
    for task in tasks:
        problems = [message for _, message in review.provenance_problems(task, 1)]
        if problems:
            raise _reconcile("the accepted discovery task's provenance: " + "; ".join(problems),
                             policy.REASON_CHAIN_INVALID)
    _require_state_current(op, run)
    bindings = {binding.task_slot: binding for binding in _discovery_bindings(op)}
    settled: list[dict[str, Any]] = []
    reports: dict[str, dict[str, Any]] = {}
    for task in tasks:
        task_id = str(task["task_id"])
        binding = bindings.get(str(task["task_slot"]))
        if binding is None or (binding.identity, binding.version) != (task["reviewer_identity"], task["reviewer_version"]):
            raise StopError(f"discovery task {task_id} ({task['task_slot']}) was accepted for {task['reviewer_identity']} "
                            f"{task['reviewer_version']}, and this invocation binds no such actor; nothing is launched",
                            code="review_reviewer_mismatch")
        task_input = review.read_task_input(task_id)
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
            raise StopError(f"the discovery actor raised for task {task_id}: {exc}; nothing is settled",
                            code="review_reviewer_failed") from exc
        report = p4.report_record(returned, task, review_kind=first.review_kind,
                                  review_contract=policy.POLICY_CHANGE_CONTRACT)
        result_digest = serialize.digest(report)
        gate.validate_settlement(store, run.review_run_id, task_id, result_digest, str(returned.reviewer_identity))
        settled.append({"task_id": task_id, "status": p4.settled_status(report), "result_digest": result_digest,
                        "settled_generation": 2})
        reports[task_id] = report
    _require_state_current(op, run)
    required = [(str(task["task_slot"]), str(task["task_id"])) for task in tasks]
    gate_two = replace(
        first, generation=2, previous_generation=1, previous_digest=chain.latest_digest,
        coverage_digest=serialize.digest(p4.coverage_record(required, settled, reports)),
        raw_report_set_digest=serialize.digest(p4.report_set_record(settled)), settled_tasks=tuple(settled),
    )
    extra = [(review_paths.report_rel(task["result_digest"]), reports[task["task_id"]]) for task in settled]
    # GAP-E: a declined discovery task makes the Policy Review non-authorizing and final in this same G2
    extra += p4.not_authorized_history(gate_two, 1)
    _start_generation(op, mutation, run, 2, p4.TRANSITION_SETTLE, gate_two, extra)


def _reports(review: ReviewStore, chain: Any) -> list[tuple[str, str, dict[str, Any]]]:
    discovery_ids = {str(task["task_id"]) for task in p4.discovery_tasks(chain)}
    found = []
    for task in chain.generation(2).settled_tasks:
        if str(task["task_id"]) in discovery_ids:
            digest = str(task["result_digest"])
            found.append((str(task["task_id"]), digest, serialize.canonical_data(review.read_report(digest).to_record())))
    return found


def _first_envelope(review: ReviewStore, chain: Any) -> dict[str, Any]:
    return review.read_task_input(str(chain.generations[0].accepted_tasks[0]["task_id"])).request_envelope


def _accept_adjudication(op: _Op, mutation: Mutation, run: _Run, chain: Any) -> None:
    """G3: one adjudication TaskInput built from canonical material only, accepted before any launch."""
    store = op.store
    review = ReviewStore(store)
    second = chain.latest
    envelope = _first_envelope(review, chain)
    reports = _reports(review, chain)
    evidence_ids = [eid for _, _, report in reports for eid in report["coverage"]["evidence_ids"]]
    request = p4.adjudication_request(
        review_contract=policy.POLICY_CHANGE_CONTRACT, review_kind=second.review_kind, review_run_id=run.review_run_id,
        candidate_hash=second.candidate_hash, candidate_generation=1, review_context_hash=second.review_context_hash,
        requirement=envelope["requirement"], reports=[{"task_id": t, "result_digest": d} for t, d, _ in reports],
        prior=p4.NO_PRIOR, evidence_ids=evidence_ids, policy_id=p4.P6_POLICY_ID,
        prior_history=p4.prior_history_references(review, second.review_kind, second.target_identity,
                                                  run.review_run_id),
        effective_policy=run.effective,
    )
    task_id = mutation.reserve_id(gate.review_task_key(run.review_run_id, p4.SLOT_ADJUDICATOR), "review_task")
    adjudicator = op.review.adjudicator
    task_input = p4.task_input(
        task_id=task_id, task_slot=p4.SLOT_ADJUDICATOR, task_kind=p4.TASK_KIND_ADJUDICATION,
        actor_identity=adjudicator.identity, actor_version=adjudicator.version, envelope=request,
        candidate_hash=second.candidate_hash, candidate_material_digest=review.candidate_material_digest(second.candidate_hash),
        review_context_hash=second.review_context_hash, accepted_generation=p4.ADJUDICATION_ACCEPT_GENERATION,
        policy_id=p4.P6_POLICY_ID,
    )
    gate_three = replace(
        second, generation=3, previous_generation=2, previous_digest=chain.latest_digest,
        accepted_tasks=second.accepted_tasks + (p4.accepted_descriptor(task_input),),
    )
    _start_generation(op, mutation, run, 3, p4.TRANSITION_ACCEPT, gate_three,
                      [(review_paths.task_input_rel(task_id), task_input.to_record())])


def _adjudicate(op: _Op, mutation: Mutation, run: _Run, chain: Any) -> None:
    """G3 -> G4: the adjudicator, launched only to its bound identity; normalized; the fixed meta-verifier; G4."""
    store = op.store
    review = ReviewStore(store)
    third = chain.latest
    descriptor = p4.adjudication_task(chain)
    if descriptor is None:
        raise _reconcile(f"Policy Review Run {run.review_run_id} accepted no adjudication", policy.REASON_CHAIN_INVALID)
    task_id = str(descriptor["task_id"])
    reports = _reports(review, chain)
    wanted = [review_paths.task_input_rel(task_id), review_paths.gate_rel(run.review_run_id, 3)]
    wanted += [review_paths.report_rel(digest) for _, digest, _ in reports]
    _require_committed(store, {relative: (review.read_bytes(relative) or b"") for relative in wanted})
    problems = review.provenance_problems(descriptor, 3)
    if problems:
        raise _reconcile("the accepted adjudication task's provenance: " + "; ".join(m for _, m in problems),
                         policy.REASON_CHAIN_INVALID)
    state = _require_state_current(op, run)
    binding = op.review.adjudicator
    if (binding.identity, binding.version) != (descriptor["reviewer_identity"], descriptor["reviewer_version"]):
        raise StopError(f"adjudication task {task_id} was accepted for {descriptor['reviewer_identity']} "
                        f"{descriptor['reviewer_version']}, and this invocation binds {binding.identity} "
                        f"{binding.version}; the adjudicator is not launched", code="review_reviewer_mismatch")
    task_input = review.read_task_input(task_id)
    references = list(task_input.request_envelope.get("prior_history") or [])
    launched = p4.P4AdjudicationTask(
        task_id=task_id, task_slot=task_input.task_slot, task_kind=task_input.task_kind, review_kind=third.review_kind,
        request_envelope=serialize.canonical_data(task_input.request_envelope), request_digest=task_input.request_digest,
        candidate_hash=third.candidate_hash, review_context_hash=third.review_context_hash,
        effective_policy_hash=third.effective_policy_hash, candidate=dict(run.candidate),
        reports=tuple(report for _, _, report in reports), prior_findings=(), prior_repair_batch=None,
        prior_repair_result=None, prior_history=p4.prior_history_records(review, references),
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
        review_contract=policy.POLICY_CHANGE_CONTRACT, descriptor=descriptor, reports=reports, prior=None,
        policy_id=p4.P6_POLICY_ID,
    )
    drafts = p4.relation_drafts(returned, adjudication, references, policy_id=p4.P6_POLICY_ID)
    relation_ids = [mutation.reserve_id(history.review_relation_key(run.review_run_id, ordinal), "review_relation")
                    for ordinal in range(1, len(drafts) + 1)]
    record = adjudication.to_record()
    digest = serialize.digest(record)
    gate.validate_settlement(store, run.review_run_id, task_id, digest, str(returned.adjudicator_identity))
    # §30.14: the fixed mechanical meta-policy verification, whatever any reviewer said
    policy.require_candidate(run.candidate, state, review)
    settled = {"task_id": task_id, "status": records.TASK_SETTLED_OK, "result_digest": digest, "settled_generation": 4}
    gate_four = replace(
        third, generation=4, previous_generation=3, previous_digest=chain.latest_digest, adjudication_digest=digest,
        obligation_digest=serialize.digest(p4.obligations_record(adjudication)),
        settled_tasks=third.settled_tasks + (settled,),
    )
    extra = [(review_paths.adjudication_rel(run.review_run_id), record)]
    extra += p4.g4_history(adjudication, gate_four, drafts, relation_ids, references).extra()
    _start_generation(op, mutation, run, 4, p4.TRANSITION_SETTLE, gate_four, extra)
    history.require_history_ready(ReviewStore(store), run.review_run_id, history.BOUNDARY_FINDINGS,
                                  history_contract=history.HISTORY_CONTRACT)


def _seal(op: _Op, mutation: Mutation, run: _Run, chain: Any) -> None:
    """G5 seal: the Receipt at generation 5, only on the full convergence predicate and the meta-verifier."""
    review = ReviewStore(op.store)
    unmet = p4.convergence_from_records(review, run.review_run_id, chain, _first_envelope(review, chain),
                                        evidence_current=True)
    if unmet:
        raise _reconcile(f"Policy Review Run {run.review_run_id} is not converged: " + "; ".join(unmet),
                         policy.REASON_CHAIN_INVALID)
    state = _require_state_current(op, run)
    policy.require_candidate(run.candidate, state, review)
    fourth = chain.latest
    receipt_id = mutation.reserve_id(gate.review_receipt_key(run.review_run_id, p4.SEAL_GENERATION), "review_receipt")
    run.receipt_id = receipt_id
    gate_five = replace(
        fourth, generation=5, previous_generation=4, previous_digest=chain.latest_digest,
        status=records.GATE_STATUS_SEALED, receipt_id=receipt_id,
        authorized_operation_stage=policy.AUTHORIZED_OPERATION_STAGE,
    )
    receipt = records.Receipt(
        receipt_id=receipt_id, review_run_id=run.review_run_id, review_generation=p4.SEAL_GENERATION,
        review_kind=fourth.review_kind, target_identity=fourth.target_identity,
        operation_identity=fourth.operation_identity, authorized_candidate_hash=fourth.candidate_hash,
        review_context_hash=fourth.review_context_hash, effective_policy_hash=fourth.effective_policy_hash,
        coverage_hash=fourth.coverage_digest, adjudication_hash=fourth.adjudication_digest,
        obligation_digest=fourth.obligation_digest, unresolved_obligations=0,
        authorized_operation_stage=policy.AUTHORIZED_OPERATION_STAGE,
    )
    _start_generation(op, mutation, run, 5, p4.TRANSITION_SEAL, gate_five,
                      [(review_paths.receipt_rel(receipt_id), receipt.to_record())], receipt_id=receipt_id)


# --------------------------------------------------------------------------- persistence (§30.18-§30.22)

def _change_paths(run: _Run) -> list[str]:
    return sorted([review_paths.policy_change_rel(run.policy_change_id), review_paths.POLICY_PROFILE_REL])


def _metadata_paths(run: _Run) -> list[str]:
    return sorted([review_paths.history_run_rel(run.review_run_id), review_paths.consumption_rel(str(run.consumption_id))])


def _receipt_problems(store: ProjectStore, run: _Run, chain: Any) -> list[str]:
    """The Receipt is this Run's G5 authorization of exactly this Candidate, current: not superseded, not consumed."""
    review = ReviewStore(store)
    found: list[str] = []
    fifth = chain.generation(p4.SEAL_GENERATION)
    if not fifth.sealed or fifth.receipt_id != run.receipt_id:
        found.append("generation 5 does not issue the reserved Receipt")
    try:
        receipt = review.read_receipt(str(run.receipt_id))
    except ValidationError as exc:
        return found + [f"the Receipt does not read ({exc})"]
    if (receipt.authorized_candidate_hash, receipt.authorized_operation_stage, receipt.review_kind) != (
            policy.candidate_hash(run.candidate), policy.AUTHORIZED_OPERATION_STAGE, policy.REVIEW_KIND):
        found.append("the Receipt does not authorize exactly this Candidate's persist-profile stage")
    if review.supersession_exists(str(run.receipt_id)) or len(chain.generations) > p4.SEAL_GENERATION:
        found.append("the Receipt is superseded")
    return found


def _persist(op: _Op, mutation: Mutation, destination: Any, run: _Run, chain: Any) -> PolicyChangeResult:
    store = op.store
    repo = op.root
    review = ReviewStore(store)
    if run.receipt_id is None or run.consumption_id is None:
        raise _reconcile(f"the policy change mutation {mutation.id} holds no Receipt / Consumption reservation",
                         policy.REASON_CHAIN_INVALID)
    binding = _require_binding(op, mutation)
    change_path = review_paths.policy_change_rel(run.policy_change_id)
    after = policy.ProjectProfile.from_record(dict(run.candidate["after_profile"]), "the reviewed after Profile")
    # step 1 - the immutable change record and the exact Profile CAS, recorded together
    if not mutation.has_stage(STAGE_POLICY):
        problems = _receipt_problems(store, run, chain)
        consumed = [found for found in review.consumptions() if found.receipt_id == run.receipt_id]
        if problems or consumed:
            raise _reconcile("the Policy Change Receipt is not current: " + "; ".join(problems or ["it is consumed"]),
                             policy.REASON_CHAIN_INVALID)
        state = _require_state_current(op, run)
        policy.require_candidate(run.candidate, state, review)
        # R6-2: the change record binds the complete baseline record the Candidate was reviewed under
        change = policy.change_record(run.candidate, review_run_id=run.review_run_id, receipt_id=str(run.receipt_id),
                                      baseline_record=state.baseline.record)
        paths = _change_paths(run)
        gate.require_committable(store, paths)
        gitops.require_no_planning_transform(repo, paths)
        checkout.require_checkout_capability(store, paths)
        gitops.ensure_separable(gitops.record_preexisting_dirty(mutation, repo), paths)
        mutation.add_effects(STAGE_POLICY, [
            Effect.create_file(change_path, serialize.canonical_text(change)),
            Effect.replace_review_profile(review_paths.POLICY_PROFILE_REL, after.text(), state.profile_digest),
        ])
    expected = _expected_policy_state(mutation, run, change_path, after)
    mutation.apply()
    # step 2 - Kp: the base-exact local policy commit of exactly those two paths
    if not mutation.has_stage(STAGE_KP):
        binding = _require_binding(op, mutation)
        problem = _record_problem(mutation, expected)
        if problem is not None:
            raise _reconcile(problem, policy.REASON_PERSISTED_MISMATCH)
        parent = gitcmd.head_commit(repo) or ""
        paths = _change_paths(run)
        gitops.ensure_separable(gitops.record_preexisting_dirty(mutation, repo), paths)
        mutation.add_effects(STAGE_KP, [gitops.review_commit_effect(
            store, f"chore(workline): apply project policy change {run.policy_change_id}", paths,
            base_head=parent, branch=binding["branch"], base_exact=True,
        )])
        mutation.apply()
    # step 3 - C-2(Kp), on every pass: no publication before it holds
    kp, parent = _c2_kp(op, mutation, run, expected)
    proof = {"contract": PROOF_CONTRACT, "policy_commit": kp, "metadata_commit": None}
    if not mutation.has_stage(STAGE_CONSUMPTION) and mutation.note(NOTE_PUBLICATION_PROOF) is None:
        mutation.set_note(NOTE_PUBLICATION_PROOF, proof)
    # step 4 - publish exact Kp when a remote exists
    if destination is not None and not mutation.has_stage(STAGE_KP_PUBLICATION):
        from .review import publication

        publication.require_barrier_clear(repo, kp)
        mutation.add_effects(STAGE_KP_PUBLICATION, [
            gitops.review_publication_effect(destination, binding["branch"].removeprefix("refs/heads/"), kp)
        ])
    mutation.apply()
    # step 5 - the Policy Consumption v3 and the consumed Run summary, in one recorded stage
    metadata = _metadata_paths(run)
    summary_path = review_paths.history_run_rel(run.review_run_id)
    consumption_path = review_paths.consumption_rel(str(run.consumption_id))
    if not mutation.has_stage(STAGE_CONSUMPTION):
        missing = [path for path in metadata if path not in mutation.scope.files]
        if missing:
            mutation.extend_scope(files=missing)
        _require_binding(op, mutation)
        gate.require_committable(store, metadata)
        gitops.require_no_planning_transform(repo, metadata)
        checkout.require_checkout_capability(store, metadata)
        receipt = review.read_receipt(str(run.receipt_id))
        sealed = chain.generation(p4.SEAL_GENERATION)
        summary = history.consumed_run_summary(sealed, receipt, str(run.consumption_id), candidate_generation=1,
                                               adjudication=p4.bound_adjudication(review, chain))
        consumption = _consumption_record(op, mutation, run, chain, kp, parent)
        mutation.add_effects(STAGE_CONSUMPTION, [
            Effect.create_file(summary_path, serialize.canonical_text(summary.to_record())),
            Effect.create_file(consumption_path, serialize.canonical_text(consumption.to_record())),
        ])
    mutation.apply()
    history.require_history_ready(ReviewStore(store), run.review_run_id, history.BOUNDARY_CONSUMPTION,
                                  history_contract=history.HISTORY_CONTRACT, consumption_id=str(run.consumption_id))
    # step 6 - Km: the metadata commit
    if not mutation.has_stage(STAGE_KM):
        _require_binding(op, mutation)
        gitops.ensure_separable(gitops.record_preexisting_dirty(mutation, repo), metadata)
        mutation.add_effects(STAGE_KM, [gitops.review_commit_effect(
            store, f"chore(workline): record policy consumption {run.consumption_id}", metadata,
        )])
        mutation.apply()
    # step 7 - C-2(Km), then publish exact Km when a remote exists
    km = _c2_km(op, mutation, run, chain, kp)
    proof = {"contract": PROOF_CONTRACT, "policy_commit": kp, "metadata_commit": km}
    if mutation.note(NOTE_PUBLICATION_PROOF) != proof and not mutation.has_stage(STAGE_KM_PUBLICATION):
        mutation.set_note(NOTE_PUBLICATION_PROOF, proof)
    if destination is not None and not mutation.has_stage(STAGE_KM_PUBLICATION):
        from .review import publication

        binding = _require_binding(op, mutation)
        publication.require_barrier_clear(repo, km)
        mutation.add_effects(STAGE_KM_PUBLICATION, [
            gitops.review_publication_effect(destination, binding["branch"].removeprefix("refs/heads/"), km)
        ])
    mutation.apply()
    mutation.complete()
    return PolicyChangeResult(
        status=STATUS_APPLIED, policy_change_id=run.policy_change_id, review_run_id=run.review_run_id,
        receipt_id=run.receipt_id, consumption_id=run.consumption_id, profile_version=after.profile_version,
        profile_digest=after.digest, policy_commit=kp, metadata_commit=km, mutation_id=mutation.id,
        findings=_findings(review, run.review_run_id), detail="the Project Profile was changed and proven",
    )


def _expected_policy_state(mutation: Mutation, run: _Run, change_path: str,
                           after: policy.ProjectProfile) -> dict[str, bytes]:
    """The exact bytes the recorded policy-state stage puts at its two paths, proven to be this change's own.

    The change record is read from the recorded stage itself (a resume never
    rebuilds it against a later baseline) and must parse as this Candidate's
    change record of this Run and Receipt; the Profile must be the reviewed
    after Profile exactly.
    """
    recorded = {str(effect["payload"]["path"]): str(effect["payload"]["content"])
                for effect in mutation.stage_effects(STAGE_POLICY)}
    text = recorded.get(change_path)
    try:
        change = policy.parse_change(serialize.parse(text or "", "the recorded change record"),
                                     "the recorded change record")
    except ValidationError as exc:
        raise _reconcile(f"the recorded policy change record does not read: {exc}", policy.REASON_PERSISTED_MISMATCH)
    if (change["policy_change_id"], change["candidate_hash"], change["review_run_id"], change["receipt_id"],
            change["after_profile_digest"]) != (run.policy_change_id, policy.candidate_hash(run.candidate),
                                                run.review_run_id, run.receipt_id, after.digest) \
            or serialize.canonical_text(change) != text:
        raise _reconcile("the recorded policy change record is not this Candidate's change record",
                         policy.REASON_PERSISTED_MISMATCH)
    return {change_path: text.encode("utf-8"), review_paths.POLICY_PROFILE_REL: after.text().encode("utf-8")}


def _bound_settings(mutation: Mutation, run: _Run) -> dict[str, int]:
    """The Global settings the after Profile is bound to: those of the baseline record the recorded change record
    binds (FC-RB7-8 positive evidence), never a code table."""
    change_path = review_paths.policy_change_rel(run.policy_change_id)
    for effect in mutation.stage_effects(STAGE_POLICY):
        if effect["payload"]["path"] == change_path:
            change = serialize.parse(str(effect["payload"]["content"]), "the recorded change record")
            return policy.bound_global_settings(change["global_baseline"])
    raise _reconcile("the policy change mutation recorded no change record", policy.REASON_PERSISTED_MISMATCH)


def _record_problem(mutation: Mutation, expected: dict[str, bytes]) -> str | None:
    """The recorded policy-state stage writes exactly the expected two paths with exactly the expected bytes."""
    effects = mutation.stage_effects(STAGE_POLICY)
    written = {str(effect["payload"]["path"]): str(effect["payload"]["content"]).encode("utf-8") for effect in effects}
    if written != expected or [effect["kind"] for effect in effects] != ["create_file", "replace_review_profile"]:
        return "the recorded policy-state stage is not exactly the change record and the reviewed Profile"
    return None


def _proof_failed(item: str, detail: str) -> ReconcileRequired:
    return _reconcile(f"C-2(Kp) {item} fails: {detail}; nothing is published", policy.REASON_PERSISTED_MISMATCH)


def _kp_effect(mutation: Mutation) -> dict[str, Any] | None:
    found = mutation.stage_effects(STAGE_KP)
    return found[0] if len(found) == 1 else None


def _c2_kp(op: _Op, mutation: Mutation, run: _Run, expected: dict[str, bytes]) -> tuple[str, str]:
    """C-2(Kp): Kp is this mutation's own, exactly the reviewed policy state, semantically round-tripped, current."""
    store = op.store
    repo = op.root
    kp_record = _kp_effect(mutation)
    if kp_record is None or kp_record.get("applied") is not True:
        raise _proof_failed("K1", "the policy commit is not recorded applied")
    kp = kp_record.get("commit_id")
    if not gitcmd.full_commit_id(kp):
        raise _proof_failed("K1", "the policy commit is recorded without the ID of a commit this mutation made")
    binding = mutation.note(NOTE_BINDING) or {}
    parents = gitcmd.commit_parents(repo, kp)
    parent = parents[0] if parents and len(parents) == 1 else None
    tip = gitcmd.branch_commit(repo, str(binding.get("branch")))
    if gitcmd.current_branch_ref(repo) != binding.get("branch") or tip is None \
            or gitcmd.descends_from(repo, tip, kp) is not True or parent is None \
            or parent != kp_record["payload"].get("base_head"):
        raise _proof_failed("K2", "the branch, parent or lineage of the policy commit is not the recorded one")
    delta = gitcmd.commit_delta(repo, parent, kp)
    if delta is None:
        raise _proof_failed("K3", "Git cannot show the policy commit's delta")
    found = {item.path: item for item in delta}
    before_absent = run.candidate["before_profile"]["digest"] is None
    statuses = {review_paths.policy_change_rel(run.policy_change_id): "A",
                review_paths.POLICY_PROFILE_REL: "A" if before_absent else "M"}
    if set(found) != set(expected) or any(
        item.status != statuses[item.path] or item.new_mode != "100644"
        or gitcmd.read_blob(repo, item.new_blob) != expected[item.path] for item in delta
    ):
        raise _proof_failed("K3", "the policy commit is not exactly the change record and the reviewed Profile bytes")
    problem = _record_problem(mutation, expected)
    if problem is not None:
        raise _proof_failed("K4", problem)
    committed_profile = gitcmd.blob_at(repo, kp, review_paths.POLICY_PROFILE_REL)
    problem = policy.persisted_projection_problem(run.candidate["after_profile"], committed_profile,
                                                  _bound_settings(mutation, run))
    if problem is not None:
        raise _proof_failed("K5", problem)
    before_profile = gitcmd.blob_at(repo, parent, review_paths.POLICY_PROFILE_REL)
    before_digest = None if before_profile is None else hashlib.sha256(before_profile).hexdigest()
    if before_digest != run.candidate["before_profile"]["digest"]:
        raise _proof_failed("K6", "the policy commit's parent does not hold the exact reviewed before Profile")
    try:
        baseline = policy.load_global_baseline(store.workline_root())
        loaded, _ = policy.parse_profile_bytes(committed_profile or b"", "the committed Profile")
    except (ValidationError, StopError) as exc:
        raise _proof_failed("K7", str(exc)) from exc
    incompatible = policy.compatibility_problem(loaded, baseline, ReviewStore(store))
    if incompatible is not None:
        raise _proof_failed("K7", incompatible)
    try:
        at_kp = review_committed.CommittedReviewStore(repo, kp)
        if at_kp.supersession_exists(str(run.receipt_id)) \
                or at_kp.entry(review_paths.gate_rel(run.review_run_id, p4.INVALIDATION_GENERATION)) is not None:
            raise _proof_failed("K8", f"{kp} holds an invalidation of the Receipt")
        if any(found_consumption.receipt_id == run.receipt_id for found_consumption in at_kp.consumptions()):
            raise _proof_failed("K8", f"{kp} holds a Consumption of the Receipt")
        chain = at_kp.gate_chain(run.review_run_id)
        if chain is None or len(chain.generations) != p4.SEAL_GENERATION or chain.latest.receipt_id != run.receipt_id:
            raise _proof_failed("K8", f"{kp} does not hold the sealed Policy Review Run")
        at_kp.read_receipt(str(run.receipt_id))
    except ValidationError as exc:
        raise _proof_failed("K8", str(exc)) from exc
    pushes_before = [effect for effect in mutation.effects
                     if effect.get("kind") == "git_push" and effect.get("stage") != STAGE_KP_PUBLICATION
                     and effect.get("stage") != STAGE_KM_PUBLICATION]
    if pushes_before:
        raise _proof_failed("K9", "the policy change mutation holds a push that is not its exact Kp / Km publication")
    return str(kp), str(parent)


def _consumption_record(op: _Op, mutation: Mutation, run: _Run, chain: Any, kp: str,
                        parent: str) -> records.PolicyConsumption:
    from .review import planning
    from .implementation import package_directory

    first = chain.generations[0]
    after = policy.ProjectProfile.from_record(dict(run.candidate["after_profile"]), "the reviewed after Profile")
    delta = gitcmd.commit_delta(op.root, parent, kp) or []
    delta_record = {
        "parent": parent, "commit": kp,
        "entries": [{"path": item.path, "status": item.status, "mode": item.new_mode, "blob": item.new_blob}
                    for item in sorted(delta, key=lambda entry: entry.path)],
    }
    persisted = {
        "contract": records.PERSISTED_POLICY_CONTRACT,
        "policy_change_id": run.policy_change_id,
        "before_profile_version": run.candidate["before_profile"]["profile_version"],
        "before_profile_digest": run.candidate["before_profile"]["digest"],
        "after_profile_version": after.profile_version,
        "after_profile_digest": after.digest,
        "global_baseline_digest": run.candidate["global_baseline_digest"],
        "normalized_projection_hash": policy.projection_hash(after, _bound_settings(mutation, run)),
        "policy_commit": kp,
        "policy_parent": parent,
        "branch": (mutation.note(NOTE_BINDING) or {}).get("branch"),
        "policy_delta_digest": serialize.digest(delta_record),
        "adapter_identity": records.POLICY_ADAPTER_IDENTITY,
        "loader_identity": planning.loader_identity(package_directory(op.store.workline_root())),
    }
    return records.PolicyConsumption(
        consumption_id=str(run.consumption_id), receipt_id=str(run.receipt_id), review_run_id=run.review_run_id,
        review_generation=p4.SEAL_GENERATION, review_kind=first.review_kind,
        authorized_candidate_hash=first.candidate_hash, operation_identity=first.operation_identity,
        operation_mutation_id=mutation.id, target_identity=first.target_identity,
        persisted_policy=serialize.canonical_data(persisted),
    )


def _metadata_failed(item: str, detail: str) -> ReconcileRequired:
    return _reconcile(f"C-2(Km) {item} fails: {detail}; nothing is published", policy.REASON_PERSISTED_MISMATCH)


def _c2_km(op: _Op, mutation: Mutation, run: _Run, chain: Any, kp: str) -> str:
    """C-2(Km): Km is this mutation's own, exactly the consumed Run summary and the Policy Consumption, on Kp."""
    repo = op.root
    found = mutation.stage_effects(STAGE_KM)
    km_record = found[0] if len(found) == 1 else {}
    km = km_record.get("commit_id")
    if km_record.get("applied") is not True or not gitcmd.full_commit_id(km):
        raise _metadata_failed("M1", "the metadata commit is not recorded applied with the ID of its own commit")
    parents = gitcmd.commit_parents(repo, km)
    q = parents[0] if parents and len(parents) == 1 else None
    if q is None or not (q == kp or (gitcmd.descends_from(repo, q, kp) is True
                                     and gitcmd.commits_touching(repo, kp, q, _change_paths(run)) == [])):
        raise _metadata_failed("M1", "the metadata commit's parent is not the policy commit or its clean descendant")
    binding = mutation.note(NOTE_BINDING) or {}
    tip = gitcmd.branch_commit(repo, str(binding.get("branch")))
    if gitcmd.current_branch_ref(repo) != binding.get("branch") or tip is None \
            or gitcmd.descends_from(repo, tip, km) is not True:
        raise _metadata_failed("M2", "HEAD is not on the bound branch, or the branch does not hold the metadata commit")
    recorded = {str(effect["payload"]["path"]): str(effect["payload"]["content"]).encode("utf-8")
                for effect in mutation.stage_effects(STAGE_CONSUMPTION) if effect.get("kind") == "create_file"}
    delta = gitcmd.commit_delta(repo, q, km) or []
    if set(recorded) != set(_metadata_paths(run)) or {item.path for item in delta} != set(recorded) or any(
        item.status != "A" or item.new_mode != "100644" or gitcmd.read_blob(repo, item.new_blob) != recorded[item.path]
        for item in delta
    ):
        raise _metadata_failed("M3", "the metadata commit is not exactly the added Run summary and Policy Consumption")
    try:
        at_km = review_committed.CommittedReviewStore(repo, km)
        summary = at_km.read_history(review_paths.HISTORY_RUNS, run.review_run_id)
        problems = history.run_summary_problems(at_km, summary)
        if problems or summary.durable_disposition != history.DISPOSITION_CONSUMED \
                or summary.consumption_id != run.consumption_id:
            raise _metadata_failed("M4", "the Run summary does not validate against the exact Consumption")
        consumption = at_km.read_consumption(str(run.consumption_id))
    except ValidationError as exc:
        raise _metadata_failed("M4", str(exc)) from exc
    if not isinstance(consumption, records.PolicyConsumption) or consumption.receipt_id != run.receipt_id \
            or consumption.policy_commit != kp:
        raise _metadata_failed("M5", "the Consumption does not bind the Receipt and the policy commit")
    for path in _change_paths(run):
        if gitcmd.blob_at(repo, km, path) != gitcmd.blob_at(repo, kp, path):
            raise _metadata_failed("M6", f"{km} does not hold the policy commit's {path}")
    return str(km)


# --------------------------------------------------------------------------- terminal outcomes

def _findings(review: ReviewStore, review_run_id: str) -> tuple[dict[str, Any], ...]:
    try:
        if not review.adjudication_exists(review_run_id):
            return ()
        found = review.read_adjudication(review_run_id)
    except ValidationError:
        return ()
    return tuple({"finding_id": item["finding_id"], "category": item["category"], "severity": item["severity"],
                  "blocking": item["blocking"], "statement": item["statement"]} for item in found.findings)


def _finish(op: _Op, mutation: Mutation, run: _Run, status: str, chain: Any, detail: str) -> PolicyChangeResult:
    """A Policy Review that issues no Receipt ends its owner mutation; nothing was or is written to the Profile."""
    if mutation.effects:
        raise _reconcile(f"the policy change mutation {mutation.id} holds effects and cannot end {status}",
                         policy.REASON_CHAIN_INVALID)
    mutation.complete()
    return PolicyChangeResult(
        status=status, policy_change_id=run.policy_change_id, review_run_id=run.review_run_id, receipt_id=None,
        consumption_id=None, profile_version=None, profile_digest=None, policy_commit=None, metadata_commit=None,
        mutation_id=mutation.id, findings=_findings(ReviewStore(op.store), run.review_run_id), detail=detail,
    )


# =========================================================================== evaluations (§30.23-§30.25)

def record_policy_evaluation(store: ProjectStore, request: policy.PolicyEvaluationRequest) -> PolicyEvaluationResult:
    """One immutable observation evaluation: evidence only, never a Profile rewrite (§30.23).

    The same owner, the immutable Review create and an ordinary exact Git
    finalization. A retry of the same request keeps the same evaluation ID;
    retain and inconclusive never change the Profile, and adjust / rollback
    only say a new reviewed Candidate is required.
    """
    record = policy.evaluation_request_record(request)
    digest = serialize.digest(record)
    invocation = {"operation": OPERATION_EVALUATION, "request_digest": digest}
    with project_operation(store, OPERATION_EVALUATION, {"request_digest": digest}):
        checkout.require_namespace_readable(store)
        destination = gitops.ensure_push_destination(store)
        mutation = MutationController(store).open(OWNER, invocation, WriteScope(files=(review_paths.POLICY_PROFILE_REL,)))
        gitops.ensure_git_ready(store.root)
        gitops.record_preexisting_dirty(mutation, store.root)
        if mutation.effects:
            mutation.apply()
        evaluation_key = f"{POLICY_EVALUATION_KEY}:{digest}"
        with abandon_on_stop(mutation):
            if not mutation.has_stage(STAGE_EVALUATION):
                review = ReviewStore(store)
                state = policy.resolve_policy_state(review, store.workline_root())
                evaluation_id = mutation.reserve_id(evaluation_key, "review_policy_evaluation")
                found = policy.evaluation_record(record, evaluation_id, state, review)
                path = review_paths.policy_evaluation_rel(evaluation_id)
                mutation.extend_scope(files=[path])
                gate.require_committable(store, [path])
                gitops.require_no_planning_transform(store.root, [path])
                checkout.require_checkout_capability(store, [path])
                gitops.ensure_separable_before_effects(mutation, [path])
                mutation.add_effects(STAGE_EVALUATION, [Effect.create_file(path, serialize.canonical_text(found))])
        evaluation_id = str(mutation.reserved(evaluation_key))
        path = review_paths.policy_evaluation_rel(evaluation_id)
        mutation.apply()
        gitops.finalize(mutation, STAGE_EVALUATION_FINALIZE,
                        f"chore(workline): record project policy evaluation {evaluation_id}", [path],
                        destination=destination)
        mutation.complete()
        stored = ReviewStore(store).read_policy_evaluation(evaluation_id)
        return PolicyEvaluationResult(
            evaluation_id=evaluation_id, policy_change_id=str(stored["policy_change_id"]), result=str(stored["result"]),
            next_action=str(stored["next_action"]), commit=gitcmd.head_commit(store.root), mutation_id=mutation.id,
        )
