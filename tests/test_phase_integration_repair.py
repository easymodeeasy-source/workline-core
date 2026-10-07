"""RB5 §32.58: integration domain repair - the IntegrationRepairPlan model and STRATEGY_CHANGE reuse refusal.

The plan over START's ``Derive`` lives with START (``start_integration_review``); the Review-side facts
(blocking context, strategy identity, provenance) live in ``review.integration``. The START repair planning
hook, the P5 future_work_link provenance write and the A/B/C linkage across integration Runs need shared
surfaces; see ``DeferredRepairTests``.
"""

from __future__ import annotations

import dataclasses
import unittest

from helpers import completing_executor, git
from rb5_doubles import DEFERRED, ident
from rb5_run_helpers import Adjudicator, Discovery, IntegrationRunCase, claim, phase_review, repairing_executor
from workline import start as st
from workline import start_integration_review as sir
from workline import start_review as sr
from workline.create import RelationSpec
from workline.errors import StopError, ValidationError
from workline.review import history, p4
from workline.review import integration as ri
from workline.review import paths as review_paths
from workline.review.store import ReviewStore
from workline.state import ProjectView
from workline.store import ProjectStore

RUN = ident("rr", 1)
FINDING = ident("rfd", 2)
PRIOR_FINDING = ident("rfd", 3)
INTEGRATION = ident("w", 4)
SURFACE = "phase.reporting"


def prior(surface: str = SURFACE, strategy: str = "split-report-writer") -> ri.PriorRepairLink:
    return ri.PriorRepairLink(surface, strategy, PRIOR_FINDING, ident("rr", 5), ident("w", 6))


def context(*, strategy_change: bool = False, findings: tuple[tuple[str, str], ...] = ((FINDING, SURFACE),),
            obligations: tuple[str, ...] = (), links: tuple[ri.PriorRepairLink, ...] | None = None
            ) -> ri.IntegrationRepairContext:
    return ri.IntegrationRepairContext(INTEGRATION, RUN, findings, obligations,
                                       (prior(),) if links is None else links, strategy_change)


def plan(strategy: str = "split-report-writer", **derive) -> sir.IntegrationRepairPlan:
    values = dict(works={"fix": st.DerivedWork("Fix the report", "the report covers every Work")}, move=True)
    values.update(derive)
    return sir.IntegrationRepairPlan(strategy, st.Derive(**values))


class RepairPlanTests(unittest.TestCase):
    def test_a_valid_plan_moves_the_target_and_keeps_the_same_unfinished_integration(self) -> None:
        self.assertEqual([], context().problems())
        self.assertEqual([], sir.repair_plan_problems(plan(), context()))

    def test_the_plan_must_move_the_target(self) -> None:
        self.assertTrue(sir.repair_plan_problems(plan(move=False), context()))

    def test_no_second_integration_merely_because_the_review_failed(self) -> None:
        problems = sir.repair_plan_problems(plan(integration=st.DerivedWork("I2", "again")), context())
        self.assertTrue(any("creates no integration" in problem for problem in problems))

    def test_fix_works_are_normal_works_that_directly_precede_the_integration(self) -> None:
        late = plan(works={"fix": st.DerivedWork("Fix", "f", before_integration=False)})
        special = plan(works={"fix": st.DerivedWork("Fix", "f", work_kind="human_confirmation")})
        self.assertTrue(sir.repair_plan_problems(late, context()))
        self.assertTrue(sir.repair_plan_problems(special, context()))
        self.assertTrue(sir.repair_plan_problems(plan(works={}), context()))

    def test_executor_relations_touching_the_integration_are_refused(self) -> None:
        """RB5B-L4: no fix Work is made post-integration; the edges into the integration are START's own."""
        after = plan(relations=(RelationSpec("requires_completion", INTEGRATION, "fix"),))
        self.assertTrue(any("touches the integration" in p for p in sir.repair_plan_problems(after, context())))
        among_fixes = plan(works={"a": st.DerivedWork("A", "a"), "b": st.DerivedWork("B", "b")},
                           relations=(RelationSpec("planned_next", "a", "b"),))
        self.assertEqual([], sir.repair_plan_problems(among_fixes, context()))

    def test_only_starts_own_derive_is_a_plan(self) -> None:
        for broken in (sir.IntegrationRepairPlan("s", None), sir.IntegrationRepairPlan("s", object()), object()):
            with self.subTest(plan=broken):
                self.assertTrue(sir.repair_plan_problems(broken, context()))

    def test_strategy_change_rejects_the_same_linked_strategy_on_the_same_surface(self) -> None:
        self.assertEqual([], sir.repair_plan_problems(plan(), context(strategy_change=False)))
        refused = sir.repair_plan_problems(plan(), context(strategy_change=True))
        self.assertTrue(any("STRATEGY_CHANGE" in problem for problem in refused))
        self.assertEqual([], sir.repair_plan_problems(plan("restructure-reporting"), context(strategy_change=True)))
        other_surface = context(strategy_change=False, findings=((FINDING, "phase.other"),))
        self.assertEqual([], sir.repair_plan_problems(plan(), other_surface),
                         "a strategy linked on another surface is not reuse")

    def test_the_strategy_change_refusal_is_never_vacuous(self) -> None:
        """RB5B-M3: a context that cannot name the prior strategy fails closed; nothing is accepted."""
        no_link = context(strategy_change=True, links=())
        self.assertTrue(no_link.problems())
        self.assertTrue(sir.repair_plan_problems(plan("restructure-reporting"), no_link))
        no_surface = context(strategy_change=True, findings=(), obligations=("phase-goal.reporting",))
        self.assertTrue(no_surface.problems())
        unlinked_surface = context(strategy_change=True, findings=((FINDING, "phase.other"),))
        self.assertTrue(unlinked_surface.problems(), "STRATEGY_CHANGE with no prior link on the context's surfaces")

    def test_the_strategy_id_is_structured_identity_not_prose(self) -> None:
        for strategy in ("Rewrite the whole report", "", "UPPER", "a" * 200, "ok\n"):
            with self.subTest(strategy=strategy):
                self.assertTrue(sir.repair_plan_problems(plan(strategy), context()))

    def test_no_completed_outcome_bypasses_blocking_obligations(self) -> None:
        self.assertTrue(sir.repair_outcome_problems(st.Completed(("out.txt",)), context()))
        self.assertTrue(sir.repair_outcome_problems(st.Derive({"fix": st.DerivedWork("F", "f")}, move=True), context()))
        self.assertEqual([], sir.repair_outcome_problems(st.QuestionWait("which report?"), context()))
        self.assertEqual([], sir.repair_outcome_problems(st.Hold("waiting"), context()))
        self.assertEqual([], sir.repair_outcome_problems(plan(), context()))

    def test_an_objective_only_not_satisfied_has_a_repairable_context(self) -> None:
        """RB5B-M1: a not_satisfied resting only on an unmet objective obligation is still repairable."""
        objective_only = context(findings=(), obligations=("phase-goal.reporting",), links=())
        self.assertEqual([], objective_only.problems())
        self.assertEqual([], sir.repair_plan_problems(plan("add-report-step"), objective_only))

    def test_context_strictness(self) -> None:
        empty = context(findings=(), obligations=(), links=())
        self.assertTrue(empty.problems(), "a domain repair context needs blocking support")
        unsorted = context(findings=((PRIOR_FINDING, SURFACE), (FINDING, SURFACE)))
        self.assertTrue(unsorted.problems())
        self.assertTrue(context(findings=((FINDING, "two words"),)).problems())


class ProvenanceTests(unittest.TestCase):
    def test_the_strategy_id_and_source_reach_the_fix_provenance(self) -> None:
        work = ident("w", 7)
        provenance = sir.fix_provenance(context(), plan("restructure-reporting"), FINDING, work)
        self.assertEqual({"source_review_run_id": RUN, "source_finding_id": FINDING,
                          "strategy_id": "restructure-reporting", "target_work_id": work}, provenance.to_record())
        with self.assertRaises(ValidationError):
            sir.fix_provenance(context(), plan(), PRIOR_FINDING, work)

    def test_no_provenance_for_a_refused_plan(self) -> None:
        """RB5B-M3 probe P13."""
        with self.assertRaises(ValidationError):
            sir.fix_provenance(context(strategy_change=True), plan(), FINDING, ident("w", 7))
        with self.assertRaises(ValidationError):
            sir.fix_provenance(context(), plan(move=False), FINDING, ident("w", 7))


class DeferredRepairTests(IntegrationRunCase):
    def test_executor_receives_the_canonical_blocking_obligation_context_only_after_g4(self) -> None:
        """start.py / start_review.py (I-6, R26; §32.25): START's executor is asked for the integration exactly once,
        after G4 settled DOMAIN_REPAIR_REQUIRED, in the dedicated repair planning context - the canonical blocking
        Findings with their semantic surfaces, read from the Run's own G4 records - never for a completion."""
        store, _, ids = self.marked_project()
        integration = ids["integration"]
        seen: list = []
        executor = repairing_executor(store)

        def asking(ctx):
            chain = ReviewStore(store).gate_chain(self.integration_runs(store, integration)[0])
            seen.append((ctx.work.id, ctx.integration_repair, chain.latest.generation))
            return executor(ctx)

        self.integrate(store, integration, phase_review(Discovery(claim("problem"), claim("problem-two"))),
                       executor=asking)
        ((work_id, context, generation),) = seen
        (run_id,) = self.integration_runs(store, integration)
        adjudication = ReviewStore(store).read_adjudication(run_id)
        self.assertEqual((integration, 4), (work_id, generation), "asked only once G4 is settled")
        self.assertIsInstance(context, ri.IntegrationRepairContext)
        # recomputed now, the context also holds the links this very repair wrote (R16); asked before them, none
        self.assertEqual(dataclasses.replace(sr.integration_repair_context(store, integration, run_id), prior_links=()),
                         context)
        self.assertEqual((), context.prior_links)
        self.assertEqual((integration, run_id), (context.integration_id, context.review_run_id))
        self.assertEqual(sorted((f["finding_id"], f["semantic_surface"]) for f in adjudication.findings if f["blocking"]),
                         list(context.blocking_findings))
        self.assertEqual(2, len(context.blocking_findings))
        self.assertEqual([], context.problems())

    def test_strategy_id_is_persisted_in_p5_provenance(self) -> None:
        """start_review.py (I-6, R16; §32.26 / §32.50): each fix Work START's repair plan registers gets the version 2
        future_work_link from its blocking Finding - source Integration Run and strategy identity as provenance -
        committed by the move commit with the Work it links, valid against its endpoints; the next repair of the
        same integration receives it as a prior supported link of that semantic surface."""
        store, phase_id, ids = self.marked_project()
        integration = ids["integration"]
        self.integrate(store, integration, phase_review(Discovery(claim("problem"))),
                       executor=repairing_executor(store, strategy="split-the-report"))
        (run_id,) = self.integration_runs(store, integration)
        review = ReviewStore(store)
        view = ProjectView.load(store)
        (fix,) = [w for w in view.effective_works(phase_id) if w.name == "Fix the integrated report"]
        (finding,) = [f for f in review.read_adjudication(run_id).findings if f["blocking"]]
        links = [review.read_history(review_paths.HISTORY_RELATIONS, relation_id)
                 for relation_id in review.history_ids(review_paths.HISTORY_RELATIONS)]
        (link,) = [found for found in links if found.relation_type == history.RELATION_FUTURE_WORK_LINK]
        self.assertEqual((finding["finding_id"], fix.id, {"source_review_run_id": run_id, "strategy_id": "split-the-report"}),
                         (link.source.id, link.target.id, dict(link.integration_provenance)))
        self.assertEqual(history.RELATION_PROVENANCE_VERSION, link.to_record()["version"])
        self.assertEqual([], history.relation_problems(review, link, work_ids=set(view.works)))
        changed = set(git(store.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").split())
        self.assertLessEqual({review_paths.history_relation_rel(link.relation_id),
                              ProjectStore.entity_rel_path("work", fix.id)}, changed, "the move commit carries both")
        self.assertEqual("completed", st.start(store, fix.id, "single-work", completing_executor(store)).status)
        seen: list = []
        self.integrate(store, integration, phase_review(Discovery(claim("problem"))),
                       executor=repairing_executor(store, seen, strategy="restructure-the-report"))
        ((_, context),) = [item for item in seen if item[1] is not None]
        self.assertEqual((ri.PriorRepairLink(str(finding["semantic_surface"]), "split-the-report", finding["finding_id"],
                                             run_id, fix.id),), context.prior_links)

    def test_after_fixes_the_same_integration_gets_a_new_candidate_and_run(self) -> None:
        """start.py + start_review.py (I-6, R26; §32.27): the fix Works run under normal semantics; the same
        integration Work is entered again only once they are complete - a new Candidate over the committed fixes and
        a new Run. Also in ONE outer START: the continuation runs the fix, re-enters the integration and completes
        the Phase, the re-entry being a successor Run of the repaired one."""
        store, phase_id, ids = self.marked_project()
        integration = ids["integration"]
        claims = [claim("problem")]

        class Once(Discovery):
            def __call__(self, task):
                found = super().__call__(task)
                self.claims = ()
                return found

        result = self.integrate(store, integration, phase_review(Once(*claims)), mode="outer",
                                executor=repairing_executor(store))
        self.assertEqual("phase_complete", result.status)
        view = ProjectView.load(store)
        (fix,) = [w for w in view.effective_works(phase_id) if w.name == "Fix the integrated report"]
        self.assertEqual([fix.id, integration], [w for w in result.completed_work_ids])
        first, second = self.integration_runs_in_order(store, integration)
        review = ReviewStore(store)
        candidate = review.read_candidate_snapshot(review.gate_chain(second).generations[0].candidate_hash).material
        old = review.read_candidate_snapshot(review.gate_chain(first).generations[0].candidate_hash).material
        self.assertNotIn(fix.id, old["effective_work_ids"])
        self.assertIn(fix.id, candidate["effective_work_ids"])
        self.assertNotEqual(old["base"]["commit"], candidate["base"]["commit"])
        self.assertEqual([integration], [w.id for w in view.effective_works(phase_id) if w.work_kind == "phase_integration_check"])
        self.assertEqual("completed", view.work_state(integration).state)

    # ---------------------------------------------------------------- CP RB5 set C, end to end (L152)

    EVIDENCE = ("e" * 64,)

    def blocking_finding(self, store, run_id: str) -> str:
        (finding,) = [f["finding_id"] for f in ReviewStore(store).read_adjudication(run_id).findings if f["blocking"]]
        return str(finding)

    def fix_of(self, store, finding_id: str) -> str:
        review = ReviewStore(store)
        (work,) = [found.target.id for found in (review.read_history(review_paths.HISTORY_RELATIONS, relation_id)
                                                 for relation_id in review.history_ids(review_paths.HISTORY_RELATIONS))
                   if found.relation_type == history.RELATION_FUTURE_WORK_LINK and found.source.id == finding_id]
        return str(work)

    def claims(self, relation_type: str, family: str, target: str, status: str = history.CAUSAL_SUPPORTED):
        """The adjudicator's one relation claim, from the Run's one blocking problem claim (the first report's)."""
        def relations(task):
            return (p4.P5RelationClaim(relation_type, str(task.reports[0]["task_id"]), 0, family, target, status,
                                       "The same defect again.", "phase-objective",
                                       self.EVIDENCE if status == history.CAUSAL_SUPPORTED else ()),)
        return relations

    def repair_cycle(self, store, integration: str, strategy: str, relations=None, *, refused: tuple[str, ...] = ()
                     ) -> tuple[str, str, ri.IntegrationRepairContext]:
        """One Integration Run settled DOMAIN_REPAIR_REQUIRED (one blocking problem, ``relations`` claimed): each
        ``refused`` strategy is answered first and refused before anything is registered, then ``strategy`` is
        accepted; its fix Work is completed. Returns the Run, its blocking Finding and the context START was given."""
        before = set(self.integration_runs(store, integration))
        selector = phase_review(Discovery(claim("problem")), adjudicator=Adjudicator(relations=relations))
        for answer in refused:
            works = set(ProjectView.load(store).works)
            with self.assertRaises(StopError) as raised:
                self.integrate(store, integration, selector, executor=repairing_executor(store, strategy=answer))
            self.assertEqual(sr.CODE_INTEGRATION_REPAIR_PLAN_INVALID, raised.exception.code, answer)
            self.assertIn("STRATEGY_CHANGE", str(raised.exception))
            self.assertEqual(works, set(ProjectView.load(store).works), "a refused plan registers nothing")
        seen: list = []
        self.integrate(store, integration, selector, executor=repairing_executor(store, seen, strategy=strategy))
        (run_id,) = set(self.integration_runs(store, integration)) - before
        ((_, context),) = [item for item in seen if item[1] is not None]
        finding = self.blocking_finding(store, run_id)
        self.assertEqual("completed", st.start(store, self.fix_of(store, finding), "single-work",
                                                completing_executor(store)).status)
        return run_id, finding, context

    def recorded_requirement(self, store, run_id: str) -> bool:
        return bool((ReviewStore(store).read_adjudication(run_id).obligations or {}).get("strategy_change_required"))

    def test_abc_linkage_across_integration_runs_uses_evidence_not_chronology(self) -> None:
        """L152 (§32.28 with CP RB5 Q-C2 / Q-C3, §32.26): across Integration Runs STRATEGY_CHANGE is the supported B/C
        relation chain on one semantic surface, end to end through START. One supported B is not two; a later Run
        whose relation is unresolved does not count, however many Runs came before on that surface; a C through the
        fix Work's version 2 link to a non-adjacent earlier Run's Finding that itself has a supported B is the chain
        - and the plan reusing the strategy already linked there is refused before anything is registered."""
        store, _, ids = self.marked_project()
        integration = ids["integration"]
        run_1, f1, context_1 = self.repair_cycle(store, integration, "split-the-report")
        self.assertFalse(context_1.strategy_change_required)
        # B: F2 recurs F1, and F1 has no B/C predecessor - not two consecutive; reusing the strategy is allowed
        run_2, f2, context_2 = self.repair_cycle(store, integration, "split-the-report",
                                                 self.claims(history.RELATION_CROSS_RUN_RECURRENCE, "findings", f1))
        self.assertEqual((False, False), (context_2.strategy_change_required, self.recorded_requirement(store, run_2)))
        # chronology alone (an unresolved B to the immediately previous Run) is A_NEW: nothing is required
        run_3, f3, context_3 = self.repair_cycle(
            store, integration, "split-the-report",
            self.claims(history.RELATION_CROSS_RUN_RECURRENCE, "findings", f2, status=history.CAUSAL_UNRESOLVED))
        self.assertEqual((False, False), (context_3.strategy_change_required, self.recorded_requirement(store, run_3)))
        # C to the fix Work of F2 (Run 2, not the adjacent Run 3): F2 has its supported B to F1 on the same surface
        fix_2 = self.fix_of(store, f2)
        run_4, f4, context_4 = self.repair_cycle(store, integration, "restructure-the-report",
                                                 self.claims(history.RELATION_REPAIR_INDUCED, p4.FIX_WORK_FAMILY, fix_2),
                                                 refused=("split-the-report",))
        self.assertEqual((True, True), (context_4.strategy_change_required, self.recorded_requirement(store, run_4)))
        self.assertEqual(frozenset({"split-the-report"}), context_4.prior_strategies())
        review = ReviewStore(store)
        (induced,) = [found for found in (review.read_history(review_paths.HISTORY_RELATIONS, relation_id)
                                          for relation_id in review.history_ids(review_paths.HISTORY_RELATIONS))
                      if found.relation_type == history.RELATION_REPAIR_INDUCED]
        link = history.integration_fix_link(review, fix_2)
        self.assertEqual((f4, history.ENDPOINT_WORK, fix_2), (induced.source.id, induced.target.kind, induced.target.id))
        self.assertEqual(dict(link.integration_provenance), dict(induced.integration_provenance))
        self.assertEqual([], history.relation_problems(review, induced, work_ids=set(ProjectView.load(store).works)))
        self.assertEqual(4, len({run_1, run_2, run_3, run_4}))

    def test_a_b_b_chain_requires_a_strategy_change_end_to_end(self) -> None:
        """CP RB5 Q-C3 / §32.26, end to end: F3 recurs F2 which recurs F1, all supported on one surface - STRATEGY_CHANGE
        is recorded at Run 3's G4, START's repair context says so, and a plan reusing a strategy already linked on
        that surface (from any earlier Run) is refused before anything is registered; another strategy is accepted.
        (Other surfaces, unresolved / insufficient evidence and A_NEW are PSW's unit rows in test_rb5_relation_chain.)"""
        store, _, ids = self.marked_project()
        integration = ids["integration"]
        _, f1, _ = self.repair_cycle(store, integration, "split-the-report")
        _, f2, _ = self.repair_cycle(store, integration, "rewrite-the-writer",
                                     self.claims(history.RELATION_CROSS_RUN_RECURRENCE, "findings", f1))
        run_3, _, context = self.repair_cycle(store, integration, "restructure-the-report",
                                              self.claims(history.RELATION_CROSS_RUN_RECURRENCE, "findings", f2),
                                              refused=("split-the-report", "rewrite-the-writer"))
        self.assertTrue(context.strategy_change_required)
        self.assertTrue(self.recorded_requirement(store, run_3))
        self.assertEqual(frozenset({"split-the-report", "rewrite-the-writer"}), context.prior_strategies())
        self.assertEqual([], context.problems())


if __name__ == "__main__":
    unittest.main()
