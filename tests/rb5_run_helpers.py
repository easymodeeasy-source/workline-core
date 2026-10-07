"""RB5 I-5 fixtures: START's Phase Integration Review Run on real Projects (not a test module).

Every Run here goes through ``start.start(..., phase_review=...)`` and every Project
is a real Workline Project whose root ``.gitattributes`` carries the canonical
Review-attribute rule (``planning_helpers.PlanningTestCase``); nothing shortcuts
production code. The actors are scripted and deterministic, so a retry asks and
hears the same.
"""

from __future__ import annotations

import subprocess
from typing import Any

from helpers import completing_executor, git
from planning_helpers import PlanningTestCase
from workline import phase_integration as pi
from workline import start as st
from workline import start_integration_review as sir
from workline import start_review as sr
from workline.create import RelationSpec, WorkSpec, register_works
from workline.mutation import MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import integration as ri
from workline.review import p4
from workline.review import paths as review_paths
from workline.review.store import ReviewStore
from workline.store import ProjectStore

V1 = pi.PHASE_INTEGRATION_REVIEW_V1


def claim(code: str = "problem", severity: str = "HIGH") -> p4.P4Claim:
    return p4.P4Claim(severity, code, f"the integrated Phase has a {code}")


class Discovery:
    """A scripted discovery actor: every call returns the same claims."""

    def __init__(self, *claims: p4.P4Claim, viewpoint: str = "correctness", identity: str = "integration-discovery",
                 version: str = "1", status: str = "completed", mutate: Any = None) -> None:
        self.claims = tuple(claims)
        self.viewpoint, self.identity, self.version, self.status = viewpoint, identity, version, status
        #: a callable run inside the launch (a verification that is NOT read-only), or None
        self.mutate = mutate
        self.tasks: list[Any] = []

    def __call__(self, task: Any) -> p4.P4DiscoveryReport:
        self.tasks.append(task)
        if self.mutate is not None:
            self.mutate()
        coverage = p4.P4Coverage(("the Phase Integration Candidate",), ("the canonical Phase objective",), (), ())
        return p4.P4DiscoveryReport(task.task_id, self.identity, self.version, self.status,
                                    self.claims if self.status == "completed" else (), coverage)

    def binding(self) -> p4.DiscoveryBinding:
        return p4.DiscoveryBinding(self.viewpoint, self, self.identity, self.version)


class Adjudicator:
    """A deterministic Integration adjudicator: a claim's code decides its §12.4 outcome.

    ``problem*`` -> Problem HIGH (blocking, repair_required); ``human`` -> HUMAN; anything else -> dismissed.
    The Phase outcome is ``outcome`` when given; else ``desired_state_change_required`` with a HUMAN claim,
    ``not_satisfied`` with a blocking one and ``objectively_satisfied`` otherwise - always about the Candidate's
    own canonical Phase objective (its desired-state digest). ``bare=True`` returns the P4 part alone.
    """

    def __init__(self, outcome: str | None = None, *, identity: str = "integration-adjudicator", version: str = "1",
                 bare: bool = False) -> None:
        self.outcome, self.identity, self.version, self.bare = outcome, identity, version, bare
        self.tasks: list[Any] = []

    def __call__(self, task: Any) -> Any:
        self.tasks.append(task)
        dispositions = []
        blocking = human = False
        for report in task.reports:
            for index, found in enumerate(report["claims"]):
                code = found["code"]
                base = dict(task_id=report["task_id"], claim_index=index, reason="adjudicated by script")
                if code.startswith("problem"):
                    blocking = True
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=False, fails_requirement=True,
                        better_alternative=False, outcome=p4.OUTCOME_PROBLEM, severity="HIGH",
                        statement=found["message"], semantic_surface="phase-objective", repair_identity=code,
                        disposition=p4.DISPOSITION_REPAIR_REQUIRED, **base))
                elif code == "human":
                    human = True
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=True, fails_requirement=False,
                        better_alternative=False, outcome=p4.OUTCOME_HUMAN, **base))
                else:
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=False, fails_requirement=False,
                        better_alternative=False, outcome=p4.OUTCOME_DISMISSED, **base))
        adjudication = p4.P4AdjudicationReturn(
            task.task_id, self.identity, self.version, True, tuple(dispositions),
            repair_purpose="repair the blocking integration problems" if blocking else None,
        )
        if self.bare:
            return adjudication
        kind = self.outcome or (ri.DESIRED_STATE_CHANGE_REQUIRED if human
                                else ri.NOT_SATISFIED if blocking else ri.OBJECTIVELY_SATISFIED)
        outcome = ri.PhaseOutcome(kind, task.candidate["phase_desired_state_digest"],
                                  "Bounded public-safe rationale of the scripted adjudicator.")
        return sr.IntegrationAdjudicationReturn(adjudication, outcome)

    def binding(self) -> p4.ActorBinding:
        return p4.ActorBinding(self, self.identity, self.version)


def repairing_executor(store: ProjectStore, log: list | None = None, *, strategy: str = "split-the-report",
                       fixes: dict[str, st.DerivedWork] | None = None):
    """START's executor: in an integration-repair context it answers with an IntegrationRepairPlan (one fix Work by
    default); every other Work completes with one result file. ``log`` gets ``(work_id, context or None)``."""
    planned = fixes or {"fix": st.DerivedWork("Fix the integrated report", "the report covers every Work")}

    def execute(ctx: st.ExecutionContext):
        if log is not None:
            log.append((ctx.work.id, ctx.integration_repair))
        if ctx.integration_repair is not None:
            return sir.IntegrationRepairPlan(strategy, st.Derive(dict(planned), move=True))
        name = f"result_{ctx.work.display}.txt"
        (store.root / name).write_text(f"{ctx.work.name}\n", encoding="utf-8")
        return st.Completed((name,))

    return execute


def answering_executor(answer, log: list | None = None):
    """START's executor answering every call with ``answer`` (and writing nothing); ``log`` as above."""
    def execute(ctx: st.ExecutionContext):
        if log is not None:
            log.append((ctx.work.id, ctx.integration_repair))
        return answer

    return execute


def phase_review(*discovery: Discovery, adjudicator: Adjudicator | None = None) -> sr.PhaseIntegrationReview:
    """The ``phase_review=`` selector: the given discovery actors (one default actor when none), one adjudicator."""
    found = discovery or (Discovery(),)
    return sr.PhaseIntegrationReview(discovery=tuple(item.binding() for item in found),
                                     adjudicator=(adjudicator or Adjudicator()).binding())


class IntegrationRunCase(PlanningTestCase):
    """A reviewed Phase: ``W1 -> integration`` (marked), W1 completed by an ordinary START, everything committed."""

    def marked_project(self, name: str = "proj", *, complete_w1: bool = True,
                       remote: bool = False, attributes: str | None = None, uncovered: bool = False,
                       second_phase: bool = False, confirmation: bool = False, next_phase: bool = False
                       ) -> tuple[ProjectStore, str, dict[str, str]]:
        """``uncovered``: one more Work of the Phase with no edge to the integration (an ``invalid_uncovered`` Work);
        ``second_phase``: a legacy Phase ``b`` entered too (its Work under ``other``); ``confirmation``: the
        deterministic downstream confirmation of the integration, under ``confirmation``."""
        store = self.planning_project(name, remote=remote, attributes=attributes)
        phases = {"a": ("Phase A", "A が成立する")}
        if second_phase or next_phase:
            phases["b"] = ("Phase B", "B が成立する")
        # next_phase: Phase b requires Phase a's completion (the Roadmap's progression gate, §32.41)
        roadmap = self.simple_roadmap(store, phases, (("requires_completion", "a", "b"),) if next_phase else ())
        phase_id, roadmap_id = roadmap.phase_ids["a"], roadmap.roadmap_id
        with project_operation(store, "rb5-run-fixture"):
            mutation = MutationController(store).open(
                "roadmap", {"operation": "phase-entry", "phase_id": phase_id}, WriteScope(entities=(phase_id,))
            )
            work_ids = register_works(mutation, "entry", {
                "w1": WorkSpec("W1", "done", phase_id=phase_id, roadmap_id=roadmap_id),
                "integration": WorkSpec("Integration", "integrated", phase_id=phase_id, roadmap_id=roadmap_id,
                                        work_kind=pi.INTEGRATION_KIND, phase_review_contract=V1),
            }, [RelationSpec("requires_completion", "w1", "integration")]).work_ids
            work_ids = dict(work_ids)
            if uncovered:
                work_ids.update(register_works(mutation, "uncovered", {
                    "w2": WorkSpec("W2", "also done", phase_id=phase_id, roadmap_id=roadmap_id)}, []).work_ids)
            if confirmation:
                # the deterministic downstream confirmation START would build (``confirmation_registration``)
                from workline.state import ProjectView

                specs, relations = sir.confirmation_registration(ProjectView.load(store), phase_id,
                                                                 work_ids["integration"])
                work_ids.update(register_works(mutation, "confirmation", specs, relations).work_ids)
            mutation.complete()
        git(store.root, "add", "-A")
        git(store.root, "commit", "-q", "-m", "fixture: a phase-integration-review-v1 integration")
        if second_phase:
            work_ids["other"] = self.simple_entry(store, roadmap.phase_ids["b"], {"x": "X done"}).work_ids["x"]
        if remote:
            git(store.root, "push", "-q", "origin", "main")
        if complete_w1:
            self.assertEqual("completed", st.start(store, work_ids["w1"], "single-work", completing_executor(store)).status)
        return store, phase_id, dict(work_ids)

    def add_late_work(self, store: ProjectStore, phase_id: str, name: str = "Late") -> str:
        """One more unstarted Work of the Phase, with no edge at all, registered and committed as a fixture."""
        from workline.state import ProjectView

        roadmap_id = ProjectView.load(store).phases[phase_id].roadmap_id
        with project_operation(store, "rb5-late-fixture"):
            mutation = MutationController(store).open(
                "roadmap", {"operation": "late-work-fixture", "phase_id": phase_id}, WriteScope(entities=(phase_id,))
            )
            work_id = register_works(mutation, "late", {
                "late": WorkSpec(name, f"{name} done", phase_id=phase_id, roadmap_id=roadmap_id)}, []).work_ids["late"]
            mutation.complete()
        git(store.root, "add", "-A")
        git(store.root, "commit", "-q", "-m", "fixture: a late Work")
        return work_id

    def roadmap_of(self, store: ProjectStore, phase_id: str) -> str:
        from workline.state import ProjectView

        return str(ProjectView.load(store).phases[phase_id].roadmap_id)

    def integrate(self, store: ProjectStore, work_id: str, selector: Any = None, *, mode: str = "single-work",
                  log: list[str] | None = None, executor: Any = None) -> st.StartResult:
        return st.start(store, work_id, mode, executor or completing_executor(store, log),
                        phase_review=selector or phase_review())

    def activate(self, store: ProjectStore) -> None:
        """Commit the P3 Work-terminal activation record (review-v1 Work terminalization), as the Work suites do."""
        from test_work_review_runtime import prefix_digest
        from workline.review import records, serialize

        raw = subprocess.run(["git", "-C", str(store.root), "show", "HEAD:.workline/events/events.jsonl"],
                             capture_output=True, check=True).stdout
        count, digest = prefix_digest(raw)
        record = records.WorkTerminalActivation("review-v1", count, digest, git(store.root, "rev-parse", "HEAD").strip())
        target = store.root / ".workline" / "review" / "activation" / "work-terminal-v1.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(serialize.canonical_bytes(record.to_record()))
        git(store.root, "add", "--", ".workline/review/activation/work-terminal-v1.yaml")
        git(store.root, "commit", "-q", "-m", "activation fixture", "--no-verify")

    def integration_runs(self, store: ProjectStore, work_id: str) -> list[str]:
        review = ReviewStore(store)
        found = []
        for run_id in review.run_ids():
            chain = review.gate_chain(run_id)
            if chain is not None and chain.generations[0].review_kind == ri.REVIEW_KIND \
                    and chain.generations[0].target_identity == work_id:
                found.append(run_id)
        return sorted(found)

    def integration_runs_in_order(self, store: ProjectStore, work_id: str) -> list[str]:
        """The integration's Runs in the order their generation 1 was committed (oldest first)."""
        found = self.integration_runs(store, work_id)
        order = git(store.root, "log", "--reverse", "--format=%H").split()
        first: dict[str, int] = {}
        for run_id in found:
            path = review_paths.gate_rel(run_id, 1)
            added = git(store.root, "log", "--diff-filter=A", "--format=%H", "--", path).split()
            first[run_id] = order.index(added[-1]) if added else len(order)
        return sorted(found, key=lambda run_id: first[run_id])

    def one_run(self, store: ProjectStore, work_id: str) -> Any:
        (run_id,) = self.integration_runs(store, work_id)
        return ReviewStore(store).gate_chain(run_id)
