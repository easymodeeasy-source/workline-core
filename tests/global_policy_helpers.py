"""RB7-D shared fixtures for the ``global-policy-change`` owner tests (P7 §31.55-§31.58) and RB8's I-RB7-2.

Not a test module. RB7-B and RB7-C keep their own fixtures and never import it.
Every Global Policy Change here runs through
:func:`workline.global_policy.change_global_policy` and every evaluation through
:func:`workline.global_policy.record_global_policy_evaluation`; nothing shortcuts
production code.

* **The root.** :func:`materialized_root_copy` is a committed copy of this
  Workline root - its sources, registry, Skills, launcher, ``.gitignore`` and the
  materialized ``review-policy/global-policy.yaml`` - in its own repository. It is
  never a Project: no ``.workline`` exists in it, ever.
* **The binding.** Root maintenance runs only against the Workline root whose
  implementation the process runs (``require_root_target``). In-process owner
  tests make the copy that root with :func:`bound_to`, the one place a binding is
  stood in for; :func:`run_remote_less_change` runs a change through the copy's
  OWN implementation in a fresh isolated interpreter, with nothing stood in for.
* **The sources.** Read-only evidence Projects, each its own repository lineage
  (its own ``git init``), carrying two consumed P5 planning Runs whose Run
  summaries are the evidence. Built once per process and restored by copy.
* **The actors.** Deterministic discovery / adjudication: a claim's code decides
  its outcome, so a retry asks and hears the same.

No row is skipped: every shared piece the owner needs (RB7-A / B / C, PSW
IR-RB7-1..6, RB7-F's materialized loader and Global-origin experiments) is in the
tree the rows run in.
"""

from __future__ import annotations

import atexit
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Iterator, Mapping, Sequence
from unittest import mock

from helpers import WORKLINE_ROOT, copy_workline_root, cwd, git, rmtree
from planning_helpers import PlanningTestCase, plan
from workline import global_policy as _owner
from workline import gitcmd, implementation
from workline import roadmap as rm
from workline import root_maintenance as _maintenance
from workline.review import global_policy as _semantics
from workline.review import p4, policy, serialize
from workline.review.committed import CommittedReviewStore

GLOBAL_POLICY_REL = policy.GLOBAL_POLICY_REL
RUNTIME_DIR = ".workline-root-runtime"
MUTATIONS_DIR = f"{RUNTIME_DIR}/mutations"
SLOTS = policy.SURFACE_REQUIRED_SLOTS
STEPS = policy.SURFACE_EXTRA_SCOPE_STEPS
BRANCH = "refs/heads/main"

KG_SUBJECT = "chore(workline): record global policy review generation "
KP_SUBJECT = "chore(workline): apply global policy change "
KM_SUBJECT = "chore(workline): record global policy consumption "
EVALUATION_SUBJECT = "chore(workline): record global policy evaluation "

#: The remote's ref-update log (one ``old new ref`` line per update it received) and the refusal flag.
PUSH_LOG = "workline-test-push-log"
REFUSE_FLAG = "workline-test-refuse-push"
POST_RECEIVE = """#!/bin/sh
log="$(git rev-parse --git-dir)/workline-test-push-log"
while read old new ref; do
  echo "$old $new $ref" >> "$log"
done
exit 0
"""
PRE_RECEIVE = """#!/bin/sh
flag="$(git rev-parse --git-dir)/workline-test-refuse-push"
if [ -f "$flag" ]; then
  echo "refused by the test remote" >&2
  exit 1
fi
exit 0
"""


# --------------------------------------------------------------------------- the modules under test

def owner() -> Any:
    """:mod:`workline.global_policy` (RB7-D), the owner under test."""
    return _owner


def semantics() -> Any:
    """:mod:`workline.review.global_policy` (RB7-C), the Review semantics the owner drives."""
    return _semantics


def maintenance() -> Any:
    """:mod:`workline.root_maintenance` (RB7-B), the root runtime the owner runs under."""
    return _maintenance


class Crash(BaseException):
    """A simulated process death: no ``except Exception`` / ``except StopError`` on its way out sees it."""


@contextmanager
def crash_at(target: Any, name: str, *, after: bool = False, when: Callable[..., bool] | None = None,
             ) -> Iterator[dict[str, int]]:
    """Raise :class:`Crash` when ``target.name`` is called (before it runs, or right after it returns).

    ``when(n, *args, **kwargs)`` picks the call (``n`` counts from 1); other
    calls run normally. Yields the call counter.
    """
    original = getattr(target, name)
    calls = {"n": 0, "crashed": 0}

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["crashed"] or (when is not None and not when(calls["n"], *args, **kwargs)):
            return original(*args, **kwargs)
        calls["crashed"] = 1
        if not after:
            raise Crash(f"crash before {name}")
        original(*args, **kwargs)
        raise Crash(f"crash after {name}")

    with mock.patch.object(target, name, wrapper):
        yield calls


# --------------------------------------------------------------------------- scratch bases

_BASE: list[Path] = []


def _base() -> Path:
    if not _BASE:
        base = Path(tempfile.mkdtemp(prefix="wl-p7d-"))
        atexit.register(rmtree, base)
        _BASE.append(base)
    return _BASE[0]


# --------------------------------------------------------------------------- the root

_ROOT_TEMPLATE: list[Path] = []


def configure_identity(root: Path) -> None:
    git(root, "config", "user.name", "workline-root-test")
    git(root, "config", "user.email", "root@example.invalid")


def _root_template() -> Path:
    if not _ROOT_TEMPLATE:
        target = _base() / "root-template"
        root = copy_workline_root(target)  # IR-RB7-6: it carries the root .gitignore and the tracked Global policy
        for relative in (".gitignore", GLOBAL_POLICY_REL):
            copied = root / relative
            if not copied.is_file() or copied.read_bytes() != (WORKLINE_ROOT / relative).read_bytes():
                raise AssertionError(f"the copied root does not carry this root's {relative} exactly")
        ignore = (root / ".gitignore").read_text(encoding="utf-8")
        if f"{RUNTIME_DIR}/" not in ignore.splitlines():
            raise AssertionError("the copied root .gitignore does not ignore the root maintenance runtime")
        git(root, "init", "-q", "-b", "main")
        configure_identity(root)
        # as a checkout of the real root is: the copied files carry this checkout's line ends, the blobs are LF
        # (the committed Global policy is canonical bytes, which the owner reads exactly)
        git(root, "config", "core.autocrlf", "true")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "the Workline root")
        _ROOT_TEMPLATE.append(root)
    return _ROOT_TEMPLATE[0]


def materialized_root_copy(tmp: Path, *, name: str = "root") -> Path:
    """A committed, remote-less copy of this Workline root with the materialized Global policy (I-RB7-2, I-RB7-3).

    Its own repository on ``main`` with a configured identity; the root
    ``.gitignore`` ignores ``.workline-root-runtime/``; no ``.workline`` exists.
    """
    destination = Path(tmp) / name
    shutil.copytree(_root_template(), destination, symlinks=True)
    gitcmd.forget_object_answers()
    if (destination / ".workline").exists():
        raise AssertionError("a root copy is never a Project")
    return destination.resolve()


@contextmanager
def bound_to(root: Path) -> Iterator[Path]:
    """Work from ``root`` as the Workline root this process runs (in-process owner tests only).

    The one stand-in: the running-root answer the root binding reads is
    ``root``, whose sources are byte copies of the running ones. Everything else
    - the cwd context check, the lock, the runtime, Git - is real.
    """
    with ExitStack() as stack:
        answer = lambda modules=None: Path(root)  # noqa: E731
        stack.enter_context(mock.patch.object(implementation, "running_workline_root", answer))
        stack.enter_context(cwd(Path(root)))
        yield Path(root)


def add_remote(tmp: Path, root: Path, *, name: str = "root") -> Path:
    """A local bare remote (never a production remote) with a ref-update log and a refusal flag; ``main`` pushed."""
    bare = Path(tmp) / f"{name}-remote.git"
    git(Path(tmp), "init", "-q", "--bare", "-b", "main", str(bare))
    hooks = bare / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "post-receive").write_text(POST_RECEIVE, encoding="utf-8", newline="\n")
    (hooks / "pre-receive").write_text(PRE_RECEIVE, encoding="utf-8", newline="\n")
    git(bare, "config", "receive.denyNonFastForwards", "true")
    git(bare, "config", "receive.denyDeletes", "true")
    git(root, "remote", "add", "origin", str(bare))
    git(root, "push", "-q", "origin", "main")
    log = bare / PUSH_LOG
    if log.exists():
        log.unlink()
    return bare


def push_locator(root: Path) -> str:
    return git(root, "remote", "get-url", "--push", "origin").strip()


def authorize(root: Path) -> Any:
    """The explicit Human-approved root maintenance authorization of ``origin`` / ``main`` / its exact locator."""
    with bound_to(root):
        return maintenance().authorize(root, remote="origin", branch=BRANCH, locator=push_locator(root))


# --------------------------------------------------------------------------- the source Projects

_SOURCE_TEMPLATES: dict[int, Path] = {}


@dataclass(frozen=True)
class Source:
    """One read-only evidence source: its label, its root, and the explicit evidence references a request names."""

    source_id: str
    root: Path
    evidence: tuple[dict[str, Any], ...]


#: The generalized mechanism every fixture request and every source's provenance names.
MECHANISM = "independent-discovery-slot-recall"
#: The declared environment of a fixture source (RB7-C's ENVIRONMENT_FIELDS) and of an evaluation window.
ENVIRONMENT = {"reviewers": ["discovery-1", "discovery-2"], "check_adapters": ["planning-validator"],
               "toolchain": "py3", "dependencies": []}
MEASUREMENT = {
    "version": "m1", "metric": "supported plan Problems per relevant Run",
    "success_criteria": "more supported Problems per relevant Run", "minimum_opportunities": 2,
    "minimum_clusters": 2, "continued_observation_permitted": True,
}
ROLLBACK = {"threshold": "no extra supported Problem after ten relevant Runs"}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def provenance(root: Path, *, mechanism: str = MECHANISM) -> dict[str, Any]:
    """A source's explicit structured provenance (RB7-C's ``provenance`` reference), positively declared.

    Opaque SHA-256 identities only: the lineage of the source repository (its
    root commit), and an incident and an implementation of that lineage; no copy
    source and no shared dependency (both declared - an empty list, never
    "unknown"). Two copies of one repository therefore share their lineage,
    incident and implementation: known correlated, one cluster.
    """
    first = git(Path(root), "rev-list", "--max-parents=0", "HEAD").split()[0]
    lineage = _sha256(f"lineage:{first}")
    return {"kind": "provenance", "lineage": lineage, "copy_sources": [],
            "incidents": [_sha256(f"incident:{lineage}")], "implementations": [_sha256(f"implementation:{lineage}")],
            "dependencies": [], "mechanism": mechanism, "environment": dict(ENVIRONMENT)}


def source_evidence(root: Path, *, mechanism: str = MECHANISM) -> tuple[dict[str, Any], ...]:
    """The explicit evidence a source contributes: its provenance, and every committed P5 Run summary by reference.

    The one place the evidence reference shape is written (RB7-C's: one
    ``provenance`` and ``record`` references ``{kind, family, id, digest}``);
    every request here takes it from here.
    """
    head = gitcmd.head_commit(Path(root))
    reader = CommittedReviewStore(Path(root), str(head))
    family = "runs"
    records_ = tuple({"kind": "record", "family": family, "id": identifier,
                      "digest": reader.history_digest(family, identifier)}
                     for identifier in sorted(reader.history_ids(family)))
    return (provenance(Path(root), mechanism=mechanism),) + records_


def _build_source(case: PlanningTestCase, index: int) -> Path:
    from project_policy_helpers import planning_review

    build = _base() / f"source-{index}-build"
    rmtree(build)
    build.mkdir(parents=True)
    saved = case.tmp
    case.tmp = build
    try:
        store = case.planning_project(f"evidence{index}")
        for name in (f"Evidence {index} One", f"Evidence {index} Two"):
            rm.create_roadmap(store, plan(name), review=planning_review())
    finally:
        case.tmp = saved
        os.chdir(saved)
    template = _base() / f"source-{index}"
    rmtree(template)
    shutil.copytree(store.root, template, symlinks=True)
    return template


def sources(case: PlanningTestCase, count: int, *, correlated: bool = False) -> tuple[Source, ...]:
    """``count`` restored evidence Projects; each its own lineage, or - ``correlated`` - copies of ONE lineage."""
    found = []
    for index in range(count):
        lineage = 0 if correlated else index
        if lineage not in _SOURCE_TEMPLATES:
            _SOURCE_TEMPLATES[lineage] = _build_source(case, lineage)
        target = Path(case.tmp) / f"source-{index}"
        rmtree(target)
        shutil.copytree(_SOURCE_TEMPLATES[lineage], target, symlinks=True)
        found.append(Source(f"source-{index}", target.resolve(), source_evidence(target.resolve())))
    gitcmd.forget_object_answers()
    return tuple(found)


_OBSERVED_DRIVER = r'''
import json, os, subprocess, sys
from pathlib import Path

payload = json.loads(sys.stdin.read())
root = Path(payload["root"])
sys.path.insert(0, str(root / "src"))
from workline import roadmap as rm
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.project_start import project_start
from workline.review import p4, planning
from workline.store import ProjectStore

coverage = p4.P4Coverage(("the planning candidate",), ("plan semantics",), (), ())


class Discovery:
    def __init__(self, identity):
        self.identity = identity

    def __call__(self, task):
        return p4.P4DiscoveryReport(task.task_id, self.identity, "1", "completed", (), coverage)


def adjudicate(task):
    return p4.P4AdjudicationReturn(task.task_id, "adjudicator", "1", True, ())


viewpoints = ("correctness", "safety", "evidence", "compatibility")
review = planning.PlanningReviewP4(
    tuple(p4.DiscoveryBinding(viewpoints[i], Discovery(f"discovery-{i + 1}"), f"discovery-{i + 1}", "1")
          for i in range(payload["reviewers"])),
    p4.ActorBinding(adjudicate, "adjudicator", "1"), p4.ActorBinding(lambda task: None, "repairer", "1"))
rule = ".workline/review/** !text eol=lf -filter -ident -working-tree-encoding"
for item in payload["projects"]:
    project = Path(item["path"])
    project.mkdir(parents=True)
    os.chdir(root)
    project_start(project, root)
    os.chdir(project)
    (project / ".gitattributes").write_text("* text=auto\n" + rule + "\n", encoding="utf-8", newline="\n")
    subprocess.run(["git", "add", ".gitattributes"], check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "attributes"], check=True, capture_output=True)
    store = ProjectStore(project)
    for name in item["roadmaps"]:
        rm.create_roadmap(store, rm.RoadmapPlan(
            name, "the plan's background", "the state to reach",
            {"a": PhaseSpec("Phase A", "A holds"), "b": PhaseSpec("Phase B", "B holds")},
            (PhaseRelationSpec("planned_next", "a", "b"),)), review=review)
print("observed")
'''


def observed_sources(case: PlanningTestCase, root: Path, count: int, *, reviewers: int = 2) -> tuple[Source, ...]:
    """Sources whose Relevant Opportunities were REVIEWED UNDER the copied root's applied Global change (§31.43).

    Each is a new Project bound to ``root`` - its own lineage - with two
    consumed P4 planning Runs reviewed after the change, so each Run froze the
    change as an active Global experiment (``origin = global``): what a retain /
    adjust / rollback evaluation rests on. The Projects are made through the
    copy's OWN implementation in a fresh isolated interpreter (a Project binds
    the implementation of its configured root), with ``reviewers`` discovery
    actors for the current Global ``required_slots``; nothing is stood in for.
    """
    projects = [{"path": str(Path(case.tmp) / f"observed-{index}"),
                 "roadmaps": [f"Observed {index} One", f"Observed {index} Two"]} for index in range(count)]
    for item in projects:
        rmtree(Path(item["path"]))
    payload = {"root": str(root), "reviewers": reviewers, "projects": projects}
    completed = subprocess.run([sys.executable, "-I", "-B", "-c", _OBSERVED_DRIVER], cwd=str(root),
                               capture_output=True, input=json.dumps(payload).encode("utf-8"), timeout=1800)
    if completed.returncode != 0:
        raise AssertionError("the observed sources were not made: " + completed.stderr.decode("utf-8", "replace"))
    gitcmd.forget_object_answers()
    return tuple(Source(f"observed-{index}", Path(item["path"]).resolve(), source_evidence(Path(item["path"]).resolve()))
                 for index, item in enumerate(projects))


# --------------------------------------------------------------------------- deterministic actors

COVERAGE = p4.P4Coverage(("the Global Policy Change Candidate",), ("normalized Global policy semantics",), (), ())


def claim(code: str = "problem", severity: str = "HIGH", message: str | None = None) -> p4.P4Claim:
    return p4.P4Claim(severity, code, message or f"the Global policy change has a {code}")


class Discovery:
    """A scripted discovery actor: every call returns the same claims."""

    def __init__(self, *claims: p4.P4Claim, viewpoint: str = "correctness", identity: str = "discovery",
                 version: str = "1", status: str = "completed", raises: BaseException | None = None) -> None:
        self.claims = tuple(claims)
        self.viewpoint = viewpoint
        self.identity = identity
        self.version = version
        self.status = status
        self.raises = raises
        self.tasks: list[Any] = []

    def __call__(self, task: Any) -> p4.P4DiscoveryReport:
        self.tasks.append(task)
        if self.raises is not None:
            raise self.raises
        return p4.P4DiscoveryReport(task.task_id, self.identity, self.version, self.status,
                                    self.claims if self.status == "completed" else (), COVERAGE)

    def binding(self) -> p4.DiscoveryBinding:
        return p4.DiscoveryBinding(self.viewpoint, self, self.identity, self.version)


class Adjudicator:
    """A deterministic adjudicator: ``problem*`` -> blocking Problem; ``human`` -> HUMAN; else dismissed."""

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
                base = dict(task_id=report["task_id"], claim_index=index, reason="adjudicated by script")
                if found["code"].startswith("problem"):
                    repairing = True
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=False, fails_requirement=True,
                        better_alternative=False, outcome=p4.OUTCOME_PROBLEM, severity="HIGH",
                        statement=found["message"], semantic_surface="global-policy-semantics",
                        repair_identity=found["code"], disposition=p4.DISPOSITION_REPAIR_REQUIRED, **base))
                elif found["code"] == "human":
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=True, fails_requirement=False,
                        better_alternative=False, outcome=p4.OUTCOME_HUMAN, **base))
                else:
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=False, fails_requirement=False,
                        better_alternative=False, outcome=p4.OUTCOME_DISMISSED, **base))
        return p4.P4AdjudicationReturn(task.task_id, self.identity, self.version, True, tuple(dispositions),
                                       repair_purpose="repair the blocking policy problems" if repairing else None)

    def binding(self) -> p4.ActorBinding:
        return p4.ActorBinding(self, self.identity, self.version)


def discovery_actors(count: int, *claims: p4.P4Claim) -> tuple[Discovery, ...]:
    """``count`` discovery actors over distinct viewpoints and distinct reviewer identities (§31.26)."""
    viewpoints = ("correctness", "safety", "evidence", "compatibility")
    return tuple(Discovery(*claims, viewpoint=viewpoints[index], identity=f"discovery-{index + 1}")
                 for index in range(count))


def root_review(*discovery: Discovery, adjudicator: Adjudicator | None = None, reviewers: int = 2) -> Any:
    """A root Review actor binding: the given discovery actors (``reviewers`` distinct ones when none), one adjudicator."""
    found = discovery or discovery_actors(reviewers)
    return owner().GlobalPolicyReview(tuple(item.binding() for item in found), (adjudicator or Adjudicator()).binding())


# --------------------------------------------------------------------------- requests

def change_request(found: Sequence[Source], *, surface: str = SLOTS, direction: str = "strengthen", after: int = 2,
                   mechanism: str = MECHANISM, rollback_of: str | None = None,
                   rollback_evaluation_id: str | None = None, evidence: Mapping[str, Any] | None = None) -> Any:
    """A Global Policy Change request over ``found`` (strengthen ``required_slots`` 1 -> 2 by default)."""
    review_global_policy = semantics()
    return review_global_policy.GlobalPolicyChangeRequest(
        policy_surface_id=surface, direction=direction, after_setting=after, generalized_mechanism_id=mechanism,
        summary="independent discovery reviewers find more supported plan problems across projects",
        expected_effect="more supported Problems per relevant review run",
        measurement_contract=dict(MEASUREMENT), rollback_contract=dict(ROLLBACK),
        sources=tuple(review_global_policy.SourceProject(item.source_id, item.root) for item in found),
        evidence=dict(evidence) if evidence is not None else {item.source_id: item.evidence for item in found},
        rollback_of=rollback_of, rollback_evaluation_id=rollback_evaluation_id,
    )


def evaluation_environment(start: Mapping[str, Any] | None = None, end: Mapping[str, Any] | None = None) -> dict:
    """An evaluation's environment (RB7-C's): the window's start and end environments, no split / proof basis."""
    return {"window_start": dict(start or ENVIRONMENT), "window_end": dict(end or start or ENVIRONMENT),
            "basis": None, "basis_digest": None}


def evaluation_request(global_policy_change_id: str, found: Sequence[Source], *, result: str = "inconclusive",
                       rationale: str = "the observation window holds too few relevant runs to decide",
                       environment: Mapping[str, Any] | None = None) -> Any:
    review_global_policy = semantics()
    return review_global_policy.GlobalPolicyEvaluationRequest(
        global_policy_change_id=global_policy_change_id, result=result, rationale=rationale,
        environment=dict(environment) if environment is not None else evaluation_environment(),
        sources=tuple(review_global_policy.SourceProject(item.source_id, item.root) for item in found),
        evidence={item.source_id: item.evidence for item in found},
    )


# --------------------------------------------------------------------------- the test case

@dataclass(frozen=True)
class Delta:
    status: str
    mode: str
    data: bytes


class GlobalPolicyCase(PlanningTestCase):
    """A test on a fresh materialized root copy with restored read-only evidence sources."""

    source_count = 2
    correlated = False
    remote = False

    def setUp(self) -> None:
        super().setUp()
        self.sources = sources(self, self.source_count, correlated=self.correlated)
        self.root = materialized_root_copy(self.tmp)
        self.bare: Path | None = None
        if self.remote:
            self.bare = add_remote(self.tmp, self.root)
            authorize(self.root)
        self.enter(self.root)

    # running -----------------------------------------------------------------
    def change(self, request: Any = None, review: Any = None) -> Any:
        with bound_to(self.root):
            return owner().change_global_policy(self.root, request or self.request(), review=review or root_review())

    def applied(self, request: Any = None, review: Any = None) -> Any:
        result = self.change(request, review)
        self.assertEqual(owner().STATUS_APPLIED, result.status, result.detail)
        return result

    def evaluate(self, request: Any) -> Any:
        with bound_to(self.root):
            return owner().record_global_policy_evaluation(self.root, request)

    def request(self, **kwargs: Any) -> Any:
        return change_request(self.sources, **kwargs)

    def stops(self, code: str, call: Callable[[], Any], *, reason: str | None = None) -> Any:
        from workline.errors import ReconcileRequired, StopError

        with self.assertRaises(StopError) as raised:
            call()
        if reason is not None:
            self.assertIsInstance(raised.exception, ReconcileRequired)
            self.assertEqual(reason, raised.exception.reason, str(raised.exception))
        else:
            self.assertEqual(code, raised.exception.code, str(raised.exception))
        return raised.exception

    # reading the root ----------------------------------------------------------
    def git(self, *args: str, check: bool = True) -> str:
        return git(self.root, *args, check=check)

    def head(self) -> str:
        return self.git("rev-parse", "--verify", "HEAD").strip()

    def parents(self, commit: str) -> list[str]:
        return self.git("rev-list", "--parents", "-n", "1", commit).split()[1:]

    def subject(self, commit: str) -> str:
        return self.git("log", "-1", "--format=%s", commit).strip()

    def commits_with(self, prefix: str, ref: str = "HEAD") -> list[str]:
        found = []
        for line in self.git("log", "--format=%H %s", ref).splitlines():
            commit, _, subject = line.partition(" ")
            if subject.startswith(prefix):
                found.append(commit)
        return found

    def blob(self, commit: str, path: str) -> bytes:
        completed = subprocess.run(["git", "-C", str(self.root), "cat-file", "blob", f"{commit}:{path}"],
                                   capture_output=True)
        if completed.returncode != 0:
            raise AssertionError(f"{commit}:{path} is not a blob")
        return completed.stdout

    def delta(self, commit: str) -> dict[str, Delta]:
        (parent,) = self.parents(commit)
        raw = subprocess.run(["git", "-C", str(self.root), "diff-tree", "-r", "-z", "--no-renames", "--no-abbrev",
                              "--raw", parent, commit], capture_output=True, check=True).stdout
        items = raw.split(b"\0")
        found: dict[str, Delta] = {}
        index = 0
        while index + 1 < len(items) and items[index]:
            header = items[index].decode("ascii").lstrip(":").split()
            path = items[index + 1].decode("utf-8")
            found[path] = Delta(header[4], header[1], b"" if header[4] == "D" else self.blob(commit, path))
            index += 2
        return found

    def dirty(self) -> list[str]:
        return [line for line in self.git("status", "--porcelain", "--untracked-files=all").splitlines()]

    def policy_record(self, commit: str = "HEAD") -> dict[str, Any]:
        return policy.parse_global_policy_bytes(self.blob(commit, GLOBAL_POLICY_REL), "the committed Global policy")

    def tracked(self, directory: str, commit: str = "HEAD") -> list[str]:
        listed = self.git("ls-tree", "-r", "--name-only", commit, "--", directory)
        return [line for line in listed.splitlines() if line]

    def run_ids(self, commit: str = "HEAD") -> list[str]:
        prefix = "review-policy/review/gates/"
        return sorted({path[len(prefix):].split("/")[0] for path in self.tracked(prefix, commit)})

    def runtime_records(self) -> list[dict[str, Any]]:
        directory = self.root / MUTATIONS_DIR
        if not directory.is_dir():
            return []
        return [serialize.parse_canonical(path.read_bytes(), path.name)[0] for path in sorted(directory.glob("*.yaml"))]

    def pending_records(self) -> list[dict[str, Any]]:
        return [record for record in self.runtime_records() if record["status"] == "pending"]

    def drop_runtime(self) -> None:
        """Runtime loss: ``.workline-root-runtime/`` removed whole."""
        rmtree(self.root / RUNTIME_DIR)

    def assertNoProjectNamespace(self) -> None:
        self.assertFalse(os.path.lexists(self.root / ".workline"), "the Workline root never gains .workline")

    def remote_log(self) -> list[str]:
        assert self.bare is not None
        log = self.bare / PUSH_LOG
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def remote_tip(self) -> str | None:
        assert self.bare is not None
        found = git(self.tmp, "--git-dir", str(self.bare), "rev-parse", "--verify", "--quiet", BRANCH, check=False)
        return found.strip() or None


# --------------------------------------------------------------------------- RB8 I-RB7-2: a change in a copied root, unmocked

FAKE = "fake"

_DRIVER = r'''
import json, sys
from dataclasses import asdict
from pathlib import Path

payload = json.loads(sys.stdin.read())
root = Path(payload["root"])
sys.path.insert(0, str(root / "src"))
from workline import global_policy as gp
from workline.review import global_policy as rgp, p4

coverage = p4.P4Coverage(("the Global Policy Change Candidate",), ("normalized Global policy semantics",), (), ())

class Discovery:
    def __init__(self, identity):
        self.identity = identity
    def __call__(self, task):
        return p4.P4DiscoveryReport(task.task_id, self.identity, "1", "completed", (), coverage)

class Adjudicator:
    def __call__(self, task):
        return p4.P4AdjudicationReturn(task.task_id, "adjudicator", "1", True, ())

viewpoints = ("correctness", "safety", "evidence", "compatibility")
review = gp.GlobalPolicyReview(
    tuple(p4.DiscoveryBinding(viewpoints[i], Discovery(f"discovery-{i + 1}"), f"discovery-{i + 1}", "1")
          for i in range(payload["reviewers"])),
    p4.ActorBinding(Adjudicator(), "adjudicator", "1"),
)
fields = dict(payload["request"])
fields["sources"] = tuple(rgp.SourceProject(item["source_id"], Path(item["root"])) for item in payload["sources"])
fields["evidence"] = {item["source_id"]: tuple(item["evidence"]) for item in payload["sources"]}
result = gp.change_global_policy(root, rgp.GlobalPolicyChangeRequest(**fields), review=review)
print(json.dumps(asdict(result), sort_keys=True))
'''


def run_remote_less_change(root: Path, found: Sequence[Source], *, actors: str = FAKE, reviewers: int = 2,
                           request: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One Global Policy Change in the copied ``root`` through the copy's own implementation (I-RB7-2).

    A fresh isolated interpreter (``-I -B``) runs from ``root`` - not a Project -
    with ``root/src`` as its implementation, so the root binding is the real one:
    nothing is stood in for. ``actors=FAKE`` binds deterministic approving
    actors (``reviewers`` distinct discovery identities and one adjudicator).
    Returns the ``GlobalPolicyChangeResult`` as a mapping.
    """
    if actors != FAKE:
        raise ValueError("only the deterministic fake actors run in a separate interpreter")
    fields = {
        "policy_surface_id": SLOTS, "direction": "strengthen", "after_setting": 2,
        "generalized_mechanism_id": "independent-discovery-slot-recall",
        "summary": "independent discovery reviewers find more supported plan problems across projects",
        "expected_effect": "more supported Problems per relevant review run",
        "measurement_contract": dict(MEASUREMENT), "rollback_contract": dict(ROLLBACK),
        "rollback_of": None, "rollback_evaluation_id": None,
    }
    fields.update(request or {})
    payload = {
        "root": str(root), "reviewers": reviewers, "request": fields,
        "sources": [{"source_id": item.source_id, "root": str(item.root), "evidence": list(item.evidence)}
                    for item in found],
    }
    completed = subprocess.run([sys.executable, "-I", "-B", "-c", _DRIVER], cwd=str(root), capture_output=True,
                               input=json.dumps(payload).encode("utf-8"), timeout=900)
    if completed.returncode != 0:
        raise AssertionError("the root change failed: " + completed.stderr.decode("utf-8", "replace"))
    return json.loads(completed.stdout.decode("utf-8").strip().splitlines()[-1])


__all__ = [
    "Adjudicator", "BRANCH", "Crash", "Delta", "Discovery", "ENVIRONMENT", "EVALUATION_SUBJECT", "FAKE",
    "GLOBAL_POLICY_REL", "GlobalPolicyCase", "KG_SUBJECT", "KM_SUBJECT", "KP_SUBJECT", "MEASUREMENT", "MECHANISM",
    "MUTATIONS_DIR", "PUSH_LOG", "REFUSE_FLAG", "RUNTIME_DIR", "SLOTS", "STEPS", "Source", "add_remote", "authorize",
    "bound_to", "change_request", "claim", "configure_identity", "crash_at", "discovery_actors",
    "evaluation_environment", "evaluation_request", "maintenance", "materialized_root_copy", "observed_sources",
    "owner", "provenance", "push_locator", "root_review", "run_remote_less_change", "semantics", "source_evidence",
    "sources",
]
