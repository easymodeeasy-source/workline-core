"""field-feedback item 4: a Phase Integration surface is excluded as ``not_applicable`` only on the discovery's own Evidence.

The adjudicator's bare word used to be enough to turn an uninspected integration path into ``not_applicable`` and
then into AUTHORIZATION_READY. With ``ground_not_applicable`` (the Phase Integration caller) the exclusion cites at
least one Evidence ID, every one of them declared by the reporting discovery task itself. Every other caller, and
every other resolution, is unchanged.
"""

from __future__ import annotations

import unittest

from test_review_p4_adjudication import DESCRIPTOR, TASK_A, bound, report, returned
from workline.errors import StopError
from workline.review import p4

SURFACE = "the solver fork source"


def reports_with_evidence(*evidence_ids: str) -> list:
    item = report(TASK_A, "integration", [], not_inspected=(SURFACE,))
    item["coverage"]["evidence_ids"] = list(evidence_ids)
    return bound(item)


def gap(resolution: str, evidence_ids: tuple[str, ...] = (), task_id: str = TASK_A) -> p4.P4AdjudicationReturn:
    return returned(gaps=[p4.P4CoverageGap(task_id, SURFACE, resolution, evidence_ids)])


class NotApplicableGroundsTests(unittest.TestCase):
    def normalize(self, reports: list, ret: p4.P4AdjudicationReturn, grounded: bool = True) -> p4.Normalized:
        return p4.normalize_adjudication(ret, DESCRIPTOR, reports, None, ground_not_applicable=grounded)

    def test_a_bare_not_applicable_is_refused_for_integration(self) -> None:
        reports = reports_with_evidence("ev-1")
        with self.assertRaises(StopError) as raised:
            self.normalize(reports, gap(p4.GAP_NOT_APPLICABLE))
        self.assertEqual(p4.CODE_ADJUDICATION_INVALID, raised.exception.code)
        self.assertIn("without grounds", str(raised.exception))
        self.assertIn("cites no Evidence", str(raised.exception))

    def test_evidence_the_discovery_never_declared_is_not_grounds(self) -> None:
        reports = reports_with_evidence("ev-1")
        with self.assertRaises(StopError) as raised:
            self.normalize(reports, gap(p4.GAP_NOT_APPLICABLE, ("ev-invented",)))
        self.assertIn("never declared", str(raised.exception))

    def test_evidence_declared_by_the_discovery_grounds_the_exclusion(self) -> None:
        found = self.normalize(reports_with_evidence("ev-1", "ev-2"), gap(p4.GAP_NOT_APPLICABLE, ("ev-1",)))
        self.assertEqual(p4.AUTHORIZATION_READY, p4.derive_outcome(found))
        self.assertEqual(["ev-1"], found.gaps[0]["evidence_ids"], "the grounds are recorded with the exclusion")

    def test_the_other_resolutions_and_the_other_callers_are_unchanged(self) -> None:
        reports = reports_with_evidence()
        # not integration: the bare exclusion stays what it always was
        self.assertEqual(p4.AUTHORIZATION_READY,
                         p4.derive_outcome(self.normalize(reports, gap(p4.GAP_NOT_APPLICABLE), grounded=False)))
        # integration: an unresolved surface is still HUMAN, an unverified one still is not silently excluded
        self.assertEqual(p4.HUMAN_WAIT, p4.derive_outcome(self.normalize(reports, gap(p4.GAP_HUMAN))))
        self.assertEqual(p4.HUMAN_WAIT,
                         p4.derive_outcome(self.normalize(reports, gap(p4.GAP_TARGETED_CHECK))))
        with self.assertRaises(StopError):
            self.normalize(reports, gap(p4.GAP_COVERED))


if __name__ == "__main__":
    unittest.main()


class WaitBreakdownTests(unittest.TestCase):
    """field-feedback item 1: a wait names what is a requirement question and what is only a check or an ordinary fix."""

    def adjudication(self, *dispositions: p4.P4ClaimDisposition, gaps=()) -> object:
        from test_review_p4_adjudication import adjudicate

        item = report(TASK_A, "integration", [("HIGH", "x", "one"), ("HIGH", "y", "two")], not_inspected=(SURFACE,))
        return adjudicate(bound(item), returned(*dispositions, gaps=gaps))

    def test_the_three_kinds_are_told_apart_and_the_outcome_is_unchanged(self) -> None:
        from test_review_p4_adjudication import disposition

        found = self.adjudication(
            disposition(TASK_A, 0, p4.OUTCOME_HUMAN), disposition(TASK_A, 1, p4.OUTCOME_PROBLEM),
            gaps=[p4.P4CoverageGap(TASK_A, SURFACE, p4.GAP_TARGETED_CHECK)],
        )
        self.assertEqual(p4.HUMAN_WAIT, found.outcome, "HUMAN stays first: nothing about the wait changes")
        self.assertEqual({"requirement_decisions": 1, "targeted_checks": 1, "blocking_findings": 1},
                         p4.wait_breakdown(found))
        self.assertIn("targeted checks (access or evidence to close, not a requirement question): 1",
                      p4.wait_breakdown_text(found))

    def test_a_human_resolved_gap_is_a_requirement_decision(self) -> None:
        found = self.adjudication(gaps=[p4.P4CoverageGap(TASK_A, SURFACE, p4.GAP_HUMAN)]) \
            if False else None
        from test_review_p4_adjudication import disposition

        found = self.adjudication(disposition(TASK_A, 0, p4.OUTCOME_DISMISSED), disposition(TASK_A, 1, p4.OUTCOME_DISMISSED),
                                  gaps=[p4.P4CoverageGap(TASK_A, SURFACE, p4.GAP_HUMAN)])
        self.assertEqual({"requirement_decisions": 1, "targeted_checks": 0, "blocking_findings": 0},
                         p4.wait_breakdown(found))
