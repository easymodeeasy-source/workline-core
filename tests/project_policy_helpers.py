"""RB6-C shared fixtures for the ``project-policy-change`` tests (P6 §30.36, §30.37, §30.40).

Not a test module. Every Project here is a real Workline Project, and every
Policy Change runs through :func:`workline.project_policy.change_project_policy`
and every evaluation through :func:`workline.project_policy.record_policy_evaluation`;
nothing shortcuts production code.

Evidence. A permanent Policy Change needs two distinct relevant P5 opportunity
references (§30.9), so an evidence Project carries two consumed P5 planning Runs
(``create_roadmap`` under ``PlanningReviewP4``), whose Run summaries are the
Relevant Opportunities. Building one costs about twenty seconds, so each kind of
evidence Project is built once per process at a FIXED absolute location and then
restored there by copy before each test: every absolute path the Project holds -
its remote, its pinned push locator - is therefore exactly the one it was built
with. The kinds:

* ``local``     - no remote (remote-less operation);
* ``remote``    - a local bare remote (never a production remote) pinned as the push destination, with
                  ``receive.denyNonFastForwards`` / ``receive.denyDeletes`` and two real hooks: a post-receive
                  hook that logs every ref update it receives, and a pre-receive hook that refuses every push
                  while a flag file exists;
* ``profiled``  - ``local`` plus one applied strengthen of ``review.discovery.required_slots`` 1 -> 2 (Profile v1).
"""

from __future__ import annotations

import atexit
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Iterator
from unittest import mock

from helpers import git, rmtree
from planning_helpers import Crash, PlanningTestCase, crash_at, plan
from workline import gitcmd, project_policy
from workline import roadmap as rm
from workline.mutation import Mutation, MutationController
from workline.review import p4, paths, planning, policy, records, serialize
from workline.review.store import ReviewStore
from workline.store import ProjectStore

COVERAGE = p4.P4Coverage(("the policy change candidate",), ("normalized policy semantics",), (), ())

#: The remote's ref-update log (one ``old new ref`` line per update it received) and the refusal flag.
PUSH_LOG = "workline-test-push-log"
REFUSE_FLAG = "workline-test-refuse-push"
POST_RECEIVE = """#!/bin/sh
# post-receive hook of the test's local bare remote: log every ref update it received
log="$(git rev-parse --git-dir)/workline-test-push-log"
while read old new ref; do
  echo "$old $new $ref" >> "$log"
done
exit 0
"""
PRE_RECEIVE = """#!/bin/sh
# pre-receive hook of the test's local bare remote: refuse every push while the flag exists
flag="$(git rev-parse --git-dir)/workline-test-refuse-push"
if [ -f "$flag" ]; then
  echo "refused by the test remote" >&2
  exit 1
fi
exit 0
"""

KP_SUBJECT = "chore(workline): apply project policy change "
KM_SUBJECT = "chore(workline): record policy consumption "
GENERATION_SUBJECT = "chore(workline): record policy review generation "
EVALUATION_SUBJECT = "chore(workline): record project policy evaluation "


# --------------------------------------------------------------------------- scripted, deterministic actors

def claim(code: str = "problem", severity: str = "HIGH", message: str | None = None) -> p4.P4Claim:
    return p4.P4Claim(severity, code, message or f"the policy change has a {code}")


class Discovery:
    """A scripted discovery actor: every call returns the same claims, so a retry asks and hears the same."""

    def __init__(self, *claims: p4.P4Claim, viewpoint: str = "correctness", identity: str = "discovery",
                 version: str = "1", status: str = "completed") -> None:
        self.claims = tuple(claims)
        self.viewpoint = viewpoint
        self.identity = identity
        self.version = version
        self.status = status
        self.tasks: list[Any] = []

    def __call__(self, task: Any) -> p4.P4DiscoveryReport:
        self.tasks.append(task)
        return p4.P4DiscoveryReport(task.task_id, self.identity, self.version, self.status,
                                    self.claims if self.status == "completed" else (), COVERAGE)

    def binding(self) -> p4.DiscoveryBinding:
        return p4.DiscoveryBinding(self.viewpoint, self, self.identity, self.version)


class Adjudicator:
    """A deterministic adjudicator: a claim's code decides its §12.4 outcome.

    ``problem*`` -> Problem HIGH (blocking); ``low`` -> Problem LOW retained; ``improve`` -> Improvement;
    ``human`` -> HUMAN; ``false`` -> unsupported; anything else -> dismissed.
    """

    def __init__(self, identity: str = "adjudicator", version: str = "1") -> None:
        self.identity = identity
        self.version = version
        self.tasks: list[Any] = []

    def __call__(self, task: Any) -> p4.P4AdjudicationReturn:
        self.tasks.append(task)
        dispositions = []
        repairing = False
        for report in task.reports:
            for index, found in enumerate(report["claims"]):
                code = found["code"]
                base = dict(task_id=report["task_id"], claim_index=index, reason="adjudicated by script")
                if code.startswith("problem"):
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=False, fails_requirement=True,
                        better_alternative=False, outcome=p4.OUTCOME_PROBLEM, severity="HIGH",
                        statement=found["message"], semantic_surface="policy-semantics", repair_identity=code,
                        disposition=p4.DISPOSITION_REPAIR_REQUIRED, **base))
                    repairing = True
                elif code == "low":
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=False, fails_requirement=True,
                        better_alternative=False, outcome=p4.OUTCOME_PROBLEM, severity="LOW",
                        statement=found["message"], semantic_surface="policy-semantics", repair_identity="low",
                        disposition=p4.DISPOSITION_RETAINED_HISTORY_ONLY, **base))
                elif code == "improve":
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=False, fails_requirement=False,
                        better_alternative=True, outcome=p4.OUTCOME_IMPROVEMENT, severity="MID",
                        statement=found["message"], semantic_surface="policy-semantics", repair_identity="improve",
                        disposition=p4.DISPOSITION_FUTURE_WORK_CANDIDATE, **base))
                elif code == "human":
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=True, fails_requirement=False,
                        better_alternative=False, outcome=p4.OUTCOME_HUMAN, **base))
                elif code == "false":
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=False, requirement_decision_required=False, fails_requirement=False,
                        better_alternative=False, outcome=p4.OUTCOME_UNSUPPORTED, **base))
                else:
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=False, fails_requirement=False,
                        better_alternative=False, outcome=p4.OUTCOME_DISMISSED, **base))
        return p4.P4AdjudicationReturn(
            task.task_id, self.identity, self.version, True, tuple(dispositions),
            repair_purpose="repair the blocking policy problems" if repairing else None,
        )

    def binding(self) -> p4.ActorBinding:
        return p4.ActorBinding(self, self.identity, self.version)


def policy_review(*discovery: Discovery, adjudicator: Adjudicator | None = None,
                  holdout: tuple[Discovery, ...] = ()) -> project_policy.PolicyReview:
    """A Policy Review actor binding: the given discovery actors (one default actor when none), one adjudicator."""
    found = discovery or (Discovery(),)
    return project_policy.PolicyReview(tuple(item.binding() for item in found), (adjudicator or Adjudicator()).binding(),
                                       tuple(item.binding() for item in holdout))


def two_reviewers() -> project_policy.PolicyReview:
    """Two discovery actors over two distinct reviewer identity/version pairs (required_slots 2)."""
    return policy_review(Discovery(), Discovery(viewpoint="safety", identity="discovery-two"))


def planning_review() -> planning.PlanningReviewP4:
    """The P4 planning selector whose consumed Runs are the evidence (its repair actor is never asked)."""
    return planning.PlanningReviewP4((Discovery().binding(),), Adjudicator().binding(),
                                     p4.ActorBinding(lambda task: None, "repairer", "1"))


# --------------------------------------------------------------------------- requests

def history_refs(store: ProjectStore, family: str = paths.HISTORY_RUNS) -> tuple[policy.EvidenceRef, ...]:
    """Every stored P5 history record of ``family`` as an exact reference (family, id, digest), sorted."""
    review = ReviewStore(store)
    return tuple(sorted((policy.EvidenceRef(family, identifier, review.history_digest(family, identifier))
                         for identifier in review.history_ids(family)), key=lambda ref: (ref.family, ref.id)))


def change_request(refs: tuple[policy.EvidenceRef, ...], *, surface: str = policy.SURFACE_REQUIRED_SLOTS,
                   direction: str = policy.DIRECTION_STRENGTHEN, after: int = 2,
                   opportunities: tuple[policy.EvidenceRef, ...] | None = None, supersedes: tuple[str, ...] = (),
                   rolls_back: str | None = None, reevaluation: str | None = None,
                   overlap: str = policy.OVERLAP_PROVEN_DISJOINT, continued: bool = True,
                   expected_effect: str = "two independent discovery reviewers find more plan problems",
                   ) -> policy.PolicyChangeRequest:
    return policy.PolicyChangeRequest(
        policy_surface_id=surface, direction=direction, after_setting=after, evidence=refs,
        opportunity_definition="every consumed planning Review Run whose discovery was settled",
        opportunities=refs if opportunities is None else opportunities, expected_effect=expected_effect,
        validation_plan="compare supported findings per relevant run before and after",
        measurement_contract=policy.MeasurementContract("m1", "supported plan Problems found per relevant Run",
                                                        continued),
        observation_window=policy.ObservationWindow(2, 10), success_criteria="more supported Problems per Run",
        rollback_threshold="no extra supported Problem after ten Runs",
        environment=policy.EnvironmentInput(("discovery 1",), ("planning-validator",), "py3"),
        overlap_classification=overlap, supersedes=supersedes, rolls_back=rolls_back, reevaluation=reevaluation,
    )


def evaluation_request(policy_change_id: str, refs: tuple[policy.EvidenceRef, ...], *,
                       result: str = policy.RESULT_RETAIN, next_action: str = policy.NEXT_END_OBSERVATION,
                       ) -> policy.PolicyEvaluationRequest:
    return policy.PolicyEvaluationRequest(
        policy_change_id=policy_change_id, result=result, evidence=refs,
        environment=policy.EnvironmentInput(("discovery 1",), ("planning-validator",), "py3"),
        rationale="the observation window shows the expected effect", next_action=next_action,
    )


# --------------------------------------------------------------------------- the evidence Projects

_BASE: list[Path] = []
_BUILT: set[str] = set()
TEMPLATE_KINDS = ("local", "remote", "profiled")


def _base() -> Path:
    if not _BASE:
        base = Path(tempfile.mkdtemp(prefix="wl-p6c-"))
        atexit.register(rmtree, base)
        _BASE.append(base)
    return _BASE[0]


def _live(kind: str) -> Path:
    return _base() / ("live-remote" if kind == "remote" else "live-local")


def _template(kind: str) -> Path:
    return _base() / f"tpl-{kind}"


def _install_remote_hooks(remote: Path) -> None:
    hooks = remote / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "post-receive").write_text(POST_RECEIVE, encoding="utf-8", newline="\n")
    (hooks / "pre-receive").write_text(PRE_RECEIVE, encoding="utf-8", newline="\n")
    git(remote, "config", "receive.denyNonFastForwards", "true")
    git(remote, "config", "receive.denyDeletes", "true")
    log = remote / PUSH_LOG
    if log.exists():
        log.unlink()


def _build(case: "PolicyCase", kind: str) -> None:
    live = _live(kind)
    if kind == "profiled":
        store = _restore(case, "local")
        result = project_policy.change_project_policy(store, change_request(history_refs(store)),
                                                      review=policy_review())
        if result.status != project_policy.STATUS_APPLIED:
            raise AssertionError(f"the profiled template did not apply: {result}")
    else:
        os.chdir(case.tmp)
        rmtree(live)
        live.mkdir(parents=True)
        saved = case.tmp
        case.tmp = live
        try:
            store = case.planning_project(remote=kind == "remote")
            for name in ("Evidence One", "Evidence Two"):
                rm.create_roadmap(store, plan(name), review=planning_review())
            if kind == "remote":
                _install_remote_hooks(live / "proj-remote.git")
        finally:
            case.tmp = saved
    os.chdir(case.tmp)
    rmtree(_template(kind))
    shutil.copytree(live, _template(kind), symlinks=True)
    _BUILT.add(kind)


def _restore(case: "PolicyCase", kind: str) -> ProjectStore:
    if kind not in _BUILT:
        _build(case, kind)
    os.chdir(case.tmp)
    live = _live(kind)
    rmtree(live)
    shutil.copytree(_template(kind), live, symlinks=True)
    gitcmd.forget_object_answers()
    store = ProjectStore(live / "proj")
    case.enter(store.root)
    return store


# --------------------------------------------------------------------------- the test case

@dataclass(frozen=True)
class Delta:
    status: str
    mode: str
    data: bytes


class PolicyCase(PlanningTestCase):
    """A test on a restored evidence Project (``template``), entered as the working context."""

    template = "local"

    def setUp(self) -> None:
        super().setUp()
        self.store = _restore(self, self.template)
        self.root = self.store.root

    # running -----------------------------------------------------------------
    def change(self, request: policy.PolicyChangeRequest | None = None,
               review: project_policy.PolicyReview | None = None) -> project_policy.PolicyChangeResult:
        return project_policy.change_project_policy(self.store, request or change_request(history_refs(self.store)),
                                                    review=review or policy_review())

    def applied(self, request: policy.PolicyChangeRequest | None = None,
                review: project_policy.PolicyReview | None = None) -> project_policy.PolicyChangeResult:
        result = self.change(request, review)
        self.assertEqual(project_policy.STATUS_APPLIED, result.status, result.detail)
        return result

    def refs(self, family: str = paths.HISTORY_RUNS) -> tuple[policy.EvidenceRef, ...]:
        return history_refs(self.store, family)

    def request(self, **kwargs: Any) -> policy.PolicyChangeRequest:
        return change_request(self.refs(), **kwargs)

    # reading -----------------------------------------------------------------
    @property
    def review_store(self) -> ReviewStore:
        return ReviewStore(self.store)

    def profile_bytes(self) -> bytes | None:
        target = self.root / paths.POLICY_PROFILE_REL
        return target.read_bytes() if target.is_file() else None

    def state(self) -> policy.PolicyState:
        return policy.resolve_policy_state(ReviewStore(self.store), self.store.workline_root())

    def git(self, *args: str, check: bool = True) -> str:
        return git(self.root, *args, check=check)

    def commit_of(self, ref: str = "HEAD") -> str:
        return self.git("rev-parse", "--verify", ref).strip()

    def parents(self, commit: str) -> list[str]:
        return self.git("rev-list", "--parents", "-n", "1", commit).split()[1:]

    def subject(self, commit: str) -> str:
        return self.git("log", "-1", "--format=%s", commit).strip()

    def commits_with(self, prefix: str, ref: str = "HEAD") -> list[str]:
        """Every commit reachable from ``ref`` whose subject starts with ``prefix``, newest first."""
        found = []
        for line in self.git("log", "--format=%H %s", ref).splitlines():
            commit, _, subject = line.partition(" ")
            if subject.startswith(prefix):
                found.append(commit)
        return found

    def delta(self, commit: str) -> dict[str, Delta]:
        """What ``commit`` changes against its one parent: path -> (status, new mode, new bytes)."""
        (parent,) = self.parents(commit)
        found: dict[str, Delta] = {}
        raw = subprocess.run(["git", "-C", str(self.root), "diff-tree", "-r", "-z", "--no-renames", "--no-abbrev",
                              "--raw", parent, commit], capture_output=True, check=True).stdout
        items = raw.split(b"\0")
        index = 0
        while index + 1 < len(items) and items[index]:
            header = items[index].decode("ascii").lstrip(":").split()
            path = items[index + 1].decode("utf-8")
            data = b"" if header[4] == "D" else self.blob(commit, path)
            found[path] = Delta(header[4], header[1], data)
            index += 2
        return found

    def blob(self, commit: str, path: str) -> bytes:
        completed = subprocess.run(["git", "-C", str(self.root), "cat-file", "blob", f"{commit}:{path}"],
                                   capture_output=True)
        if completed.returncode != 0:
            raise AssertionError(f"{commit}:{path} is not a blob")
        return completed.stdout

    def has_path(self, commit: str, path: str) -> bool:
        return bool(self.git("ls-tree", "--name-only", commit, "--", path).strip())

    def dirty(self) -> list[str]:
        return [line for line in self.git("status", "--porcelain", "--untracked-files=all").splitlines()
                if "/runtime/" not in line]

    def owner_pending(self) -> list[dict[str, Any]]:
        return [record for record in MutationController(self.store).list_pending()
                if record["owner"] == project_policy.OWNER]

    def policy_pending(self) -> list[dict[str, Any]]:
        """The pending owner-level policy change mutation(s) (not their generation mutations)."""
        return [record for record in self.owner_pending()
                if (record.get("invocation") or {}).get("operation") == project_policy.OPERATION]

    def policy_receipts(self) -> list[str]:
        """The Receipts of Policy Reviews (the evidence Runs' planning Receipts left out)."""
        review = ReviewStore(self.store)
        return [found for found in review.receipt_ids() if review.read_receipt(found).review_kind == policy.REVIEW_KIND]

    def policy_consumptions(self) -> list[records.PolicyConsumption]:
        return [found for found in ReviewStore(self.store).consumptions() if isinstance(found, records.PolicyConsumption)]

    def policy_runs(self) -> list[str]:
        """The Policy Review Runs (the evidence planning Runs left out)."""
        review = ReviewStore(self.store)
        return [run for run in review.run_ids() if review.gate_chain(run).generations[0].review_kind == policy.REVIEW_KIND]

    def problems(self) -> list[str]:
        from workline.validate import validate_project

        return [f"{problem.code}: {problem.message}" for problem in validate_project(self.store)]

    # the remote --------------------------------------------------------------
    @property
    def remote(self) -> Path:
        return self.root.parent / "proj-remote.git"

    def remote_main(self) -> str | None:
        found = git(self.remote, "rev-parse", "--verify", "--quiet", "refs/heads/main", check=False)
        return found.strip() or None

    def remote_has(self, commit: str) -> bool:
        return subprocess.run(["git", "-C", str(self.remote), "cat-file", "-e", f"{commit}^{{commit}}"],
                              capture_output=True).returncode == 0

    def pushes(self) -> list[tuple[str, str, str]]:
        """Every ref update the remote received since the template was built: (old, new, ref)."""
        log = self.remote / PUSH_LOG
        if not log.exists():
            return []
        return [tuple(line.split()) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def refuse_pushes(self, on: bool) -> None:
        flag = self.remote / REFUSE_FLAG
        if on:
            flag.write_text("refuse\n", encoding="utf-8")
        elif flag.exists():
            flag.unlink()

    def is_ancestor(self, older: str, newer: str, repo: Path | None = None) -> bool:
        return subprocess.run(["git", "-C", str(repo or self.root), "merge-base", "--is-ancestor", older, newer],
                              capture_output=True).returncode == 0

    def assert_fast_forward_pushes(self) -> None:
        """No ref update the remote received rewrote history: each one is a fast-forward of the one before."""
        for old, new, ref in self.pushes():
            if set(old) == {"0"}:
                continue
            self.assertTrue(self.is_ancestor(old, new, self.remote), f"{ref} {old}..{new} is not a fast-forward")


# --------------------------------------------------------------------------- windows

class Interrupted(RuntimeError):
    """A deterministic interruption injected by the test alone (never a StopError: nothing is abandoned)."""


@contextmanager
def after_recording(stage: str) -> Iterator[None]:
    """Stop right after the stage ``stage`` is durably recorded in a mutation, none of it applied."""
    real = Mutation.add_effects

    def fire(mutation: Mutation, recorded: str, effects: list[Any]) -> None:
        real(mutation, recorded, effects)
        if recorded == stage:
            raise Interrupted(f"recorded {recorded}")

    with mock.patch.object(Mutation, "add_effects", fire):
        yield


def _matches(record: dict[str, Any], kind: str, stage: str, path: "str | Callable[[str], bool] | None") -> bool:
    if record["kind"] != kind or record["stage"] != stage:
        return False
    found = str(record["payload"].get("path"))
    return path is None or (path(found) if callable(path) else found == path)


@contextmanager
def after_effect(kind: str, stage: str, *, path: "str | Callable[[str], bool] | None" = None) -> Iterator[None]:
    """Stop right after the first effect of ``kind`` in ``stage`` (at ``path``) is applied, its flag not saved."""
    real = MutationController.apply_effect

    def fire(controller: MutationController, record: dict[str, Any]) -> None:
        real(controller, record)
        if _matches(record, kind, stage, path):
            raise Interrupted(f"applied {kind} of {stage}, flag not saved")

    with mock.patch.object(MutationController, "apply_effect", fire):
        yield


@contextmanager
def before_effect(kind: str, stage: str, *, path: "str | Callable[[str], bool] | None" = None) -> Iterator[None]:
    """Stop right before the first effect of ``kind`` in ``stage`` (at ``path``) is applied (its bytes recorded)."""
    real = MutationController.apply_effect

    def fire(controller: MutationController, record: dict[str, Any]) -> None:
        if _matches(record, kind, stage, path):
            raise Interrupted(f"before {kind} of {stage}")
        real(controller, record)

    with mock.patch.object(MutationController, "apply_effect", fire):
        yield


@contextmanager
def before_owner_completion() -> Iterator[None]:
    """Stop right before the owner-level policy change mutation is completed (its generation mutations complete)."""
    real = Mutation.complete

    def fire(mutation: Mutation) -> None:
        if mutation.owner == project_policy.OWNER and mutation.invocation.get("operation") == project_policy.OPERATION:
            raise Interrupted("before completion")
        real(mutation)

    with mock.patch.object(Mutation, "complete", fire):
        yield


def at_call(n: int) -> Callable[..., bool]:
    return lambda calls, *args, **kwargs: calls == n


def reserving(kind: str) -> Callable[..., bool]:
    """A ``crash_at(Mutation, "reserve_id", when=...)`` filter: the reservation of an ID of ``kind``."""
    return lambda calls, mutation, key, found_kind: found_kind == kind


# --------------------------------------------------------------------------- the §30.40 retry invariants

class InterruptionCase(PolicyCase):
    """One §30.40 window: run the change into the window, then the same request again, and prove the invariants.

    The request is a strengthen of ``required_slots`` 1 -> 2 reviewed by ONE discovery actor (the pre-change
    policy). A retry that resolved its policy from the after state would need two reviewers and refuse; one that
    authorized under it would bind the after Effective Policy - both are caught below.
    """

    template = "remote"

    def interrupted(self, window: Callable[[], Any], expected: Any = (Crash, Interrupted),
                    *, between: Callable[[], None] | None = None) -> None:
        before = self.state()
        remote_before = self.remote_main() if self.template == "remote" else None
        head_before = self.commit_of()
        request = self.request()
        with window(), self.assertRaises(expected):
            self.change(request, policy_review())
        pending = self.policy_pending()
        self.assertEqual(1, len(pending), "the policy change mutation is kept for the retry")
        reserved = dict(pending[0].get("reserved_ids") or {})
        frozen = ((pending[0].get("notes") or {}).get("policy_candidate") or {}).get("candidate")
        if between is not None:
            between()
        discovery, adjudicator = Discovery(), Adjudicator()
        result = self.change(request, policy_review(discovery, adjudicator=adjudicator))
        self.assertEqual("applied", result.status, result.detail)
        self.assert_invariants(result, reserved, frozen, before, remote_before, head_before)
        self.discovery_calls, self.adjudicator_calls = len(discovery.tasks), len(adjudicator.tasks)

    def assert_invariants(self, result: Any, reserved: dict[str, str], frozen: dict[str, Any] | None,
                          before: policy.PolicyState, remote_before: str | None, head_before: str) -> None:
        review = ReviewStore(self.store)
        # the same policy_change_id / Candidate / Review IDs the interrupted attempt reserved
        for key, identifier in reserved.items():
            if key.startswith("review-policy-change:"):
                self.assertEqual(identifier, result.policy_change_id, "the retry keeps the policy_change_id")
            elif key.startswith("review-run:"):
                self.assertEqual(identifier, result.review_run_id, "the retry keeps the Review Run")
            elif key.startswith("review-receipt:"):
                self.assertEqual(identifier, result.receipt_id, "the retry keeps the Receipt ID")
            elif key.startswith("review-consumption:"):
                self.assertEqual(identifier, result.consumption_id, "the retry keeps the Consumption ID")
            elif key.startswith("review-task:"):
                chain = review.gate_chain(result.review_run_id)
                self.assertIn(identifier, [t["task_id"] for g in chain.generations for t in g.accepted_tasks])
        chain = review.gate_chain(result.review_run_id)
        candidate_hash = chain.generations[0].candidate_hash
        if frozen is not None:
            self.assertEqual(policy.candidate_hash(frozen), candidate_hash, "the retry keeps the Candidate")
        self.assertEqual([result.review_run_id], self.policy_runs(), "one Policy Review Run, never a second")
        self.assertEqual(5, len(chain.generations))
        self.assertEqual([], p4.chain_problems(chain))
        settled = [t for t in chain.generations[1].settled_tasks]
        self.assertEqual(1, len(settled), "one raw discovery report, no duplicate")
        # no duplicate change record, no Profile version skip
        self.assertEqual((result.policy_change_id,), review.policy_change_ids(), "no duplicate change record")
        change = review.read_policy_change(result.policy_change_id)
        self.assertEqual(candidate_hash, change["candidate_hash"])
        profile = review.read_profile()
        self.assertEqual((1, None), (profile.profile_version, profile.parent_profile_digest), "no version skip")
        self.assertEqual(profile.digest, change["after_profile_digest"])
        # one Receipt, one Consumption, one Kp, one Km - and nothing authorized under the after state
        self.assertEqual([result.receipt_id], self.policy_receipts())
        self.assertEqual([result.consumption_id], [c.consumption_id for c in self.policy_consumptions()])
        receipt = review.read_receipt(str(result.receipt_id))
        self.assertEqual(candidate_hash, receipt.authorized_candidate_hash)
        self.assertEqual(before.effective_hash, receipt.effective_policy_hash, "no authorization under the after state")
        for gate in chain.generations:
            self.assertEqual(before.effective_hash, gate.effective_policy_hash)
        kps, kms = self.commits_with(KP_SUBJECT), self.commits_with(KM_SUBJECT)
        self.assertEqual([result.policy_commit], kps, "one Kp")
        self.assertEqual([result.metadata_commit], kms, "one Km")
        self.assertEqual(5, len([c for c in self.commits_with(GENERATION_SUBJECT)
                                 if self.subject(c).endswith(result.review_run_id)]))
        summary = review.read_history(paths.HISTORY_RUNS, result.review_run_id)
        self.assertEqual(result.consumption_id, summary.consumption_id)
        # no force / history rewrite, no duplicate publication
        self.assertTrue(self.is_ancestor(head_before, str(result.metadata_commit)), "no history rewrite")
        if self.template == "remote":
            self.assertEqual(result.metadata_commit, self.remote_main())
            news = [new for _, new, _ in self.pushes()]
            self.assertLessEqual(news.count(str(result.policy_commit)), 1, "Kp is published at most once")
            self.assertEqual(1, news.count(str(result.metadata_commit)), "Km is published exactly once")
            self.assertTrue(set(news) <= {str(result.policy_commit), str(result.metadata_commit)})
            if remote_before is not None:
                self.assertTrue(self.is_ancestor(remote_before, str(result.metadata_commit), self.remote))
            self.assert_fast_forward_pushes()
        self.assertEqual([], self.owner_pending())
        self.assertEqual([], self.dirty())
        self.assertEqual([], self.problems())


__all__ = [
    "Adjudicator", "COVERAGE", "Crash", "Delta", "Discovery", "EVALUATION_SUBJECT", "GENERATION_SUBJECT",
    "InterruptionCase", "Interrupted", "KM_SUBJECT", "KP_SUBJECT", "PolicyCase", "after_effect", "after_recording", "at_call",
    "before_effect", "before_owner_completion", "change_request", "claim", "crash_at", "evaluation_request",
    "history_refs", "planning_review", "policy_review", "records", "reserving", "serialize", "two_reviewers",
]
