"""P4 §27.35: convergence by obligations/coverage/Evidence, and the verification-only Integration contract."""

from __future__ import annotations

from dataclasses import replace
import unittest

from workline.review import closure, p4

from test_review_p4_adjudication import TASK_A, adjudicate, bound, disposition, report, returned


def converged(**overrides: object) -> p4.ConvergenceInput:
    values: dict = dict(
        discovery_settled=True, coverage_resolved=True, reports_durable=True, adjudication_complete=True,
        unadjudicated=0, problem_high=0, problem_mid=0, low_traceable_objective_holds=True,
        improvements_traceable=True, human=0, reverification_complete=True, repair_coverage_complete=True,
        repair_induced_unresolved=0, strategy_change_pending=False, evidence_current=True,
    )
    values.update(overrides)
    return p4.ConvergenceInput(**values)


class ConvergenceTests(unittest.TestCase):
    def test_every_condition_held_converges(self) -> None:
        self.assertEqual([], p4.convergence_problems(converged()))

    def test_each_unmet_condition_blocks(self) -> None:
        for overrides in (
            dict(coverage_resolved=False), dict(problem_high=1), dict(problem_mid=1), dict(human=1),
            dict(repair_coverage_complete=False), dict(evidence_current=False), dict(strategy_change_pending=True),
            dict(reverification_complete=False), dict(repair_induced_unresolved=1), dict(unadjudicated=1),
            dict(low_traceable_objective_holds=False), dict(improvements_traceable=False),
            dict(reports_durable=False), dict(discovery_settled=False), dict(adjudication_complete=False),
        ):
            with self.subTest(overrides=overrides):
                self.assertTrue(p4.convergence_problems(converged(**overrides)))

    def test_zero_findings_with_unknown_coverage_does_not_converge(self) -> None:
        reports = bound(report(TASK_A, "correctness", [], not_inspected=("the cache",)))
        found = adjudicate(reports, returned(gaps=[p4.P4CoverageGap(TASK_A, "the cache", p4.GAP_TARGETED_CHECK)]))
        state = p4.convergence_of(found, None, reports_durable=True, evidence_current=True)
        self.assertEqual((), found.findings)
        self.assertTrue(p4.convergence_problems(state))
        self.assertNotEqual(p4.AUTHORIZATION_READY, found.outcome)

    def test_traceable_low_and_improvement_with_objective_holding_converge(self) -> None:
        reports = bound(report(TASK_A, "correctness", [("LOW", "x", "minor"), ("HIGH", "y", "nicer")]))
        found = adjudicate(reports, returned(
            disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="LOW", repair_identity="r1",
                        disposition=p4.DISPOSITION_RETAINED_HISTORY_ONLY),
            disposition(TASK_A, 1, p4.OUTCOME_IMPROVEMENT, severity="HIGH", repair_identity="r2"),
        ))
        self.assertEqual(p4.AUTHORIZATION_READY, found.outcome)
        self.assertEqual([], p4.convergence_problems(
            p4.convergence_of(found, None, reports_durable=True, evidence_current=True)
        ))

    def test_unresolved_high_mid_and_stale_evidence_do_not_converge(self) -> None:
        reports = bound(report(TASK_A, "correctness", [("MID", "x", "broken")]))
        found = adjudicate(reports, returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM)))
        self.assertTrue(p4.convergence_problems(p4.convergence_of(found, None, reports_durable=True, evidence_current=True)))
        clean = adjudicate(reports, returned(disposition(TASK_A, 0, p4.OUTCOME_DISMISSED)))
        self.assertTrue(p4.convergence_problems(p4.convergence_of(clean, None, reports_durable=True, evidence_current=False)))
        self.assertEqual([], p4.convergence_problems(p4.convergence_of(clean, None, reports_durable=True, evidence_current=True)))


def declared(**overrides: object) -> p4.IntegrationDeclaration:
    values: dict = dict(
        adapter_identity="integration-adapter", allowed_project_state=(), allowed_external_state=("disposable-db",),
        allowed_nested_state=(), isolation_mechanism=closure.MechanismProof(closure.PROOF_DENIAL, "container", "v1"),
        disposal_proven=True,
    )
    values.update(overrides)
    return p4.IntegrationDeclaration(**values)


class IntegrationTests(unittest.TestCase):
    def test_undeclared_project_mutation_cannot_pass(self) -> None:
        found = p4.integration_problems(declared(), p4.IntegrationObservation(project_mutations=(".workline/works/w.md",)))
        self.assertTrue(found)
        self.assertTrue(p4.integration_problems(declared(allowed_project_state=("x",)), p4.IntegrationObservation()))

    def test_undeclared_external_mutation_cannot_pass(self) -> None:
        self.assertTrue(p4.integration_problems(declared(), p4.IntegrationObservation(external_mutations=("prod-db",))))

    def test_nested_repository_mutation_cannot_pass_from_gitlink_identity_alone(self) -> None:
        self.assertTrue(p4.integration_problems(
            declared(), p4.IntegrationObservation(nested_mutations=("vendor/lib",), gitlink_only_nested=("vendor/lib",))
        ))
        self.assertTrue(p4.integration_problems(declared(), p4.IntegrationObservation(nested_mutations=("vendor/lib",))))

    def test_disposable_rollback_confirmed_adapter_may_pass(self) -> None:
        self.assertEqual([], p4.integration_problems(
            declared(), p4.IntegrationObservation(external_mutations=("disposable-db",))
        ))
        self.assertTrue(p4.integration_problems(
            declared(disposal_proven=False), p4.IntegrationObservation(external_mutations=("disposable-db",))
        ))
        self.assertTrue(p4.integration_problems(
            declared(isolation_mechanism=None), p4.IntegrationObservation(external_mutations=("disposable-db",))
        ))

    def test_integration_discovered_fix_routes_through_normal_work_ownership(self) -> None:
        self.assertEqual(p4.INTEGRATION_FIX_ROUTE, p4.integration_repair_route(["the API returns 500"]))
        self.assertEqual("normal_fix_work", p4.INTEGRATION_FIX_ROUTE)


if __name__ == "__main__":
    unittest.main()


class ConvergenceFromRecordsTests(unittest.TestCase):
    """§27.12: the owner's pre-seal predicate, read through a reader of canonical records only."""

    def reader(self, found, *, durable: bool = True):
        class Reader:
            def read_adjudication(self, run_id):
                return found

            def read_repair_result(self, batch_id):  # pragma: no cover - generation 1 has no prior
                raise AssertionError("no Repair Result for a first-generation Run")

            def report_exists(self, digest):
                return durable

        return Reader()

    def test_a_ready_first_generation_run_converges_only_with_durable_reports_and_current_evidence(self) -> None:
        from test_review_p4_dispatch import G1, G2, G3, G4, Chain

        reports = bound(report(TASK_A, "correctness", [("LOW", "x", "minor")]))
        found = adjudicate(reports, returned(disposition(
            TASK_A, 0, p4.OUTCOME_PROBLEM, severity="LOW", disposition=p4.DISPOSITION_RETAINED_HISTORY_ONLY,
        )))
        chain = Chain((G1, G2, G3, G4))
        chain = type("C", (), {"generations": chain.generations, "latest": G4,
                               "generation": lambda self, n: chain.generations[n - 1]})()
        self.assertEqual([], p4.convergence_from_records(self.reader(found), "rr_x", chain, {"succession": None},
                                                         evidence_current=True))
        self.assertTrue(p4.convergence_from_records(self.reader(found, durable=False), "rr_x", chain,
                                                    {"succession": None}, evidence_current=True))
        self.assertTrue(p4.convergence_from_records(self.reader(found), "rr_x", chain, {"succession": None},
                                                    evidence_current=False))
        blocking = adjudicate(bound(report(TASK_A, "correctness", [("HIGH", "x", "broken")])),
                              returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="HIGH")))
        self.assertTrue(p4.convergence_from_records(self.reader(blocking), "rr_x", chain, {"succession": None},
                                                    evidence_current=True))
