"""RB11 review repair: real-flow tests and negative controls for Sprint §41.31 AM-B, AM-C1 and AM-C3 (RB11INT-EVID-1).

§41.31 ("Pins and verification obligations") asks each unit for a real-flow test and a negative control. The unit-level
tests (``test_laneb_gap_grounds``, the ``wait_breakdown`` unit tests, the message pins) call helpers; the tests here
drive the production entry points instead:

* AM-B   ``start.start(..., phase_review=...)`` on a real marked Phase Integration (``rb5_run_helpers``), with scripted
         discovery / adjudication actors, through G1 - G4 (``start_review._integration_adjudicate``).
* AM-C1  ``start.start`` on a Work under the P4 contract (``start_review._p4_human_wait``) and on a Phase Integration
         (``start_review._integration_exit_wait``): the STOP the Human sees.
* AM-C3  ``roadmap.enter_phase`` on a Phase that is already expanded.

Nothing under test is mocked. Where a test patches something, the patch only makes an input of the production path
fail or return a shape the real adjudication cannot produce; each such case is named in its docstring.
"""

from __future__ import annotations

import dataclasses
import sys
import unittest
from unittest import mock

from p5_helpers import p4_only_cycle
from rb5_run_helpers import Adjudicator, Discovery, IntegrationRunCase, claim, phase_review
from helpers import WorklineTestCase
from test_phase_entry_contract import D1, PhaseEntryCase
from test_roadmap_registered_works import design as registered_design, plan as registered_plan
from test_review_p4_planning import Discovery as WorkDiscovery
from test_review_p4_work import P4WorkCase, work_p4
from workline import roadmap as rm
from workline import start as st
from workline.errors import StopError
from workline.mutation import MutationController
from workline.review import p4
from workline.review.store import ReviewStore
from workline.state import ProjectView
from workline.validate import validate_project

SURFACE = "the solver fork source"
SURFACE_B = "the second discovery's own surface"
HOLDS = ". It holds "


# --------------------------------------------------------------------------- AM-B actors
class CoverageDiscovery(Discovery):
    """A scripted integration discovery that declares what it did not inspect and which Evidence IDs it declares."""

    def __init__(self, *claims, not_inspected: tuple[str, ...] = (), evidence_ids: tuple[str, ...] = (), **kwargs) -> None:
        super().__init__(*claims, **kwargs)
        self.not_inspected, self.evidence_ids = not_inspected, evidence_ids

    def __call__(self, task):
        self.tasks.append(task)
        coverage = p4.P4Coverage(("the Phase Integration Candidate",), ("the canonical Phase objective",),
                                 self.evidence_ids, self.not_inspected)
        return p4.P4DiscoveryReport(task.task_id, self.identity, self.version, self.status,
                                    self.claims if self.status == "completed" else (), coverage)


class GapAdjudicator(Adjudicator):
    """The scripted Integration adjudicator, resolving every declared not-inspected surface ``not_applicable``.

    ``cite(report_index, report)`` returns the Evidence IDs the resolution of that report's gaps cites, so a test chooses
    exactly which IDs the adjudicator offers as grounds (none, an invented one, another task's, or the task's own).
    """

    def __init__(self, cite, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cite = cite

    def __call__(self, task):
        answer = super().__call__(task)
        gaps = []
        for index, report in enumerate(task.reports):
            for surface in report["coverage"]["not_inspected"]:
                gaps.append(p4.P4CoverageGap(report["task_id"], surface, p4.GAP_NOT_APPLICABLE,
                                             tuple(self.cite(index, report))))
        return dataclasses.replace(answer, adjudication=dataclasses.replace(answer.adjudication, coverage_gaps=tuple(gaps)))


class GroundedNotApplicableFlowTests(IntegrationRunCase):
    """AM-B (Sprint §41.31) real flow + negative control; closes RB11INT-EVID-1 for AM-B.

    The adjudication reaches the adjudication-invalid STOP at G3 -> G4 and nothing is settled; the negative control grounds
    the same gap on the reporting task's own declared Evidence ID and the same START completes.
    """

    def run_start(self, name: str, discoveries, cite):
        store, _, ids = self.marked_project(name)
        adjudicator = GapAdjudicator(cite)
        selector = phase_review(*discoveries, adjudicator=adjudicator)
        return store, ids["integration"], adjudicator, selector

    def assert_nothing_settled(self, store, integration: str, adjudicator: GapAdjudicator) -> None:
        review = ReviewStore(store)
        chain = self.one_run(store, integration)
        self.assertEqual(1, len(adjudicator.tasks), "the adjudicator was asked and its answer was refused")
        self.assertEqual(3, chain.latest.generation, "G4 is never written: nothing is settled")
        self.assertIsNone(chain.latest.receipt_id)
        self.assertFalse(chain.latest.sealed)
        with self.assertRaises(Exception):
            review.read_adjudication(chain.review_run_id)
        self.assertEqual("in_progress", ProjectView.load(store).work_state(integration).state)
        self.assertEqual(1, len(MutationController(store).list_pending()), "the START stays pending, nothing completed")

    def assert_refused(self, name: str, discoveries, cite, expected: str) -> None:
        store, integration, adjudicator, selector = self.run_start(name, discoveries, cite)
        with self.assertRaises(StopError) as raised:
            self.integrate(store, integration, selector)
        self.assertEqual(p4.CODE_ADJUDICATION_INVALID, raised.exception.code)
        self.assertIn("without grounds", str(raised.exception))
        self.assertIn(expected, str(raised.exception))
        self.assert_nothing_settled(store, integration, adjudicator)

    def test_a_not_applicable_gap_without_any_evidence_id_is_refused_and_settles_nothing(self) -> None:
        """AM-B / RB11INT-EVID-1: no Evidence ID at all -> adjudication-invalid STOP through ``start.start``."""
        discovery = CoverageDiscovery(not_inspected=(SURFACE,), evidence_ids=("ev-1",))
        self.assert_refused("no-evidence", (discovery,), lambda index, report: (), "cites no Evidence")

    def test_a_not_applicable_gap_citing_an_id_the_reporting_task_never_declared_is_refused(self) -> None:
        """AM-B / RB11INT-EVID-1: an invented Evidence ID is not grounds -> adjudication-invalid STOP, nothing settled."""
        discovery = CoverageDiscovery(not_inspected=(SURFACE,), evidence_ids=("ev-1",))
        self.assert_refused("invented", (discovery,), lambda index, report: ("ev-invented",), "never declared")

    def test_a_not_applicable_gap_citing_another_tasks_declared_id_is_refused(self) -> None:
        """AM-B / RB11INT-EVID-1: an ID declared by ANOTHER discovery task does not ground the reporting task's gap.

        Two real discovery tasks: A (not_inspected, declares ev-a) and B (declares ev-b). The adjudication cites ev-b for
        A's gap. The association is by task, so it is refused.
        """
        first = CoverageDiscovery(not_inspected=(SURFACE,), evidence_ids=("ev-a",), viewpoint="correctness",
                                  identity="integration-discovery-a")
        second = CoverageDiscovery(evidence_ids=("ev-b",), viewpoint="coverage", identity="integration-discovery-b")

        def cite(index, report):
            return ("ev-b",)  # B's declaration, offered for A's gap

        self.assert_refused("other-task", (first, second), cite, "never declared")
        self.assertEqual((1, 1), (len(first.tasks), len(second.tasks)), "both discovery tasks really ran and reported")
        self.assertEqual(("ev-b",), second.evidence_ids, "the other task really declared ev-b in its own report")

    def test_negative_control_the_same_gap_grounded_on_the_reporting_tasks_own_evidence_proceeds(self) -> None:
        """AM-B / RB11INT-EVID-1 negative control: the identical START, with the gap grounded on an ID the reporting task
        declared in its own report (``coverage.evidence_ids``), is accepted and reaches the sealed completion."""
        discovery = CoverageDiscovery(not_inspected=(SURFACE,), evidence_ids=("ev-1", "ev-2"))
        store, integration, adjudicator, selector = self.run_start("grounded", (discovery,),
                                                                   lambda index, report: ("ev-1",))
        self.assertEqual("completed", self.integrate(store, integration, selector).status)
        review = ReviewStore(store)
        chain = self.one_run(store, integration)
        self.assertTrue(chain.latest.sealed)
        adjudication = review.read_adjudication(chain.review_run_id)
        self.assertEqual(p4.AUTHORIZATION_READY, adjudication.outcome)
        self.assertEqual([{"task_id": discovery.tasks[0].task_id, "surface": SURFACE, "resolution": p4.GAP_NOT_APPLICABLE,
                           "evidence_ids": ["ev-1"]}], [dict(gap) for gap in adjudication.coverage_gaps],
                         "the grounds are recorded with the exclusion")
        self.assertEqual("completed", ProjectView.load(store).work_state(integration).state)
        self.assertEqual([], MutationController(store).list_pending())
        self.assertEqual([], validate_project(store))

    def test_negative_control_two_tasks_each_grounded_on_its_own_declaration_proceeds(self) -> None:
        """AM-B / RB11INT-EVID-1 negative control for the by-task association: with two reporting tasks that each
        declare their own ID, citing each task's own ID is accepted."""
        first = CoverageDiscovery(not_inspected=(SURFACE,), evidence_ids=("ev-a",), viewpoint="correctness",
                                  identity="integration-discovery-a")
        second = CoverageDiscovery(not_inspected=(SURFACE_B,), evidence_ids=("ev-b",), viewpoint="coverage",
                                   identity="integration-discovery-b")
        store, integration, adjudicator, selector = self.run_start(
            "two-grounded", (first, second), lambda index, report: tuple(report["coverage"]["evidence_ids"]))
        self.assertEqual("completed", self.integrate(store, integration, selector).status)
        adjudication = ReviewStore(store).read_adjudication(self.one_run(store, integration).review_run_id)
        self.assertEqual({"ev-a", "ev-b"}, {item for gap in adjudication.coverage_gaps for item in gap["evidence_ids"]})


# --------------------------------------------------------------------------- AM-C1 helpers
def called_from(*names: str) -> bool:
    """True when the caller of the caller (the function that invoked a patched method) is one of ``names``."""
    frame = sys._getframe(2)
    return frame.f_code.co_name in names


class WaitTextChecks:
    """Shared AM-C1 assertions; ``breakdown_for`` and ``leading`` are supplied by the concrete case."""

    def assert_tail(self, message: str, leading: str, expected_tail_text: str) -> None:
        self.assertTrue(message.startswith(leading), f"the original leading text is preserved: {message!r}")
        self.assertEqual(HOLDS + expected_tail_text, message[len(leading):])


class WorkHumanWaitTextFlowTests(WaitTextChecks, P4WorkCase):
    """AM-C1 (Sprint §41.31), Work Review P4 wait, through ``start.start``; closes RB11INT-EVID-1 for AM-C1 (Work path)."""

    def setUp(self) -> None:
        super().setUp()
        seam = p4_only_cycle()  # a P4-only first Run, exactly as ``test_review_p4_work.WorkHumanWaitTests``
        seam.__enter__()
        self.addCleanup(seam.__exit__, None, None, None)
        self.human = WorkDiscovery((p4.P4Claim("HIGH", "human", "which format?"),), ())
        self.executor = self.completing(write={"out.txt": b"out\n"}, message="feat: out")

    def wait(self) -> StopError:
        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", self.executor, review=work_p4(self.human))
        self.assertEqual(p4.CODE_HUMAN_WAIT, raised.exception.code, "the original code is preserved")
        return raised.exception

    def leading(self) -> str:
        (run_id,) = self.runs()
        return (f"Work Review Run {run_id} waits on a Human requirement decision at generation 4; no repair guesses it, "
                "and this START stays pending until an invocation carries the decision")

    def test_the_wait_keeps_code_and_leading_text_and_appends_the_breakdown(self) -> None:
        """AM-C1 / RB11INT-EVID-1: code p4.CODE_HUMAN_WAIT, the original leading message, then the wait_breakdown_text."""
        stop = self.wait()
        (run_id,) = self.runs()
        counted = p4.wait_breakdown_text(ReviewStore(self.store).read_adjudication(run_id))
        self.assertIn("requirement decisions for a Human: 1", counted)
        self.assert_tail(str(stop), self.leading(), counted)
        self.assertEqual(1, len(self.pending()), "the START stays pending at HUMAN_WAIT")

    def test_negative_control_a_failing_breakdown_leaves_the_stop_exactly_as_before(self) -> None:
        """AM-C1 / RB11INT-EVID-1 negative control: ``p4.wait_breakdown_text`` raising -> the same code and the same
        leading text, no tail; the next START (breakdown computable again) carries the tail for the same Run."""
        with mock.patch.object(p4, "wait_breakdown_text", side_effect=RuntimeError("breakdown failed")):
            stop = self.wait()
        self.assertEqual(self.leading(), str(stop), "exactly the pre-AM-C1 text")
        self.assertNotIn("It holds", str(stop))
        self.assertTrue(str(self.wait()).startswith(self.leading() + HOLDS), "the same waiting Run, now with the tail")
        self.assertEqual(1, len(self.runs()))

    def test_negative_control_an_unreadable_adjudication_leaves_the_stop_exactly_as_before(self) -> None:
        """AM-C1 / RB11INT-EVID-1 negative control: ``ReviewStore.read_adjudication`` raising ONLY for the breakdown read
        (the patch fires when ``_p4_human_wait`` is the caller; every other read in the flow is the real one)."""
        real = ReviewStore.read_adjudication

        def read(store, run_id):
            if called_from("_p4_human_wait"):
                raise RuntimeError("adjudication unreadable")
            return real(store, run_id)

        with mock.patch.object(ReviewStore, "read_adjudication", read):
            stop = self.wait()
        self.assertEqual(self.leading(), str(stop))

    def test_a_wait_whose_adjudication_counts_nothing_says_a_human_is_still_needed(self) -> None:
        """AM-C1 / RB11INT-EVID-1: the stored adjudication counts no requirement decision, targeted check or blocking
        finding -> the text must not print "requirement decisions for a Human: 0" as if no Human were needed.

        SIMULATED INPUT: a consistent P4 adjudication cannot be HUMAN_WAIT with all three counts zero, so the breakdown read
        of the real waiting Run is replaced by its own record with the counted fields emptied (patch fires only when
        ``_p4_human_wait`` is the caller). Everything else is the real START.
        """
        real = ReviewStore.read_adjudication

        def read(store, run_id):
            found = real(store, run_id)
            if called_from("_p4_human_wait"):
                return dataclasses.replace(found, entries=(), coverage_gaps=(),
                                           obligations={**found.obligations, "problem_high": 0, "problem_mid": 0})
            return found

        with mock.patch.object(ReviewStore, "read_adjudication", read):
            stop = self.wait()
        message = str(stop)
        self.assertTrue(message.startswith(self.leading() + HOLDS), message)
        self.assertNotIn("requirement decisions for a Human: 0", message)
        self.assertIn("the wait still needs a Human", message)
        self.assertIn("no requirement decision, targeted check or blocking finding is counted", message)


class IntegrationHumanWaitTextFlowTests(WaitTextChecks, IntegrationRunCase):
    """AM-C1 (Sprint §41.31), Phase Integration G4 wait, through ``start.start``; closes RB11INT-EVID-1 for AM-C1
    (Integration path, ``_integration_exit_wait``)."""

    def setUp(self) -> None:
        super().setUp()
        self.store, _, ids = self.marked_project("wait-text")
        self.integration = ids["integration"]
        self.selector = phase_review(Discovery(claim("human")), adjudicator=Adjudicator())

    def wait(self) -> StopError:
        with self.assertRaises(StopError) as raised:
            self.integrate(self.store, self.integration, self.selector)
        self.assertEqual(p4.CODE_HUMAN_WAIT, raised.exception.code, "the original code is preserved")
        return raised.exception

    def leading(self) -> str:
        (run_id,) = self.integration_runs(self.store, self.integration)
        return (f"Integration Review Run {run_id} of {self.integration} waits on a Human requirement decision at "
                "generation 4; it stays the same canonical Run, nothing guesses the decision, and no other Run of the "
                "integration begins beside it (R8)")

    def settle_the_wait(self) -> str:
        """The first START reaches G4 HUMAN_WAIT; the returned text is the message of the resumed START, which is the
        one that goes through ``_integration_exit_wait`` (the Run exists, no Human decision is bound)."""
        self.wait()
        return str(self.wait())

    def test_the_wait_keeps_code_and_leading_text_and_appends_the_breakdown(self) -> None:
        """AM-C1 / RB11INT-EVID-1: code p4.CODE_HUMAN_WAIT, the original leading message, then the wait_breakdown_text."""
        message = self.settle_the_wait()
        (run_id,) = self.integration_runs(self.store, self.integration)
        counted = p4.wait_breakdown_text(ReviewStore(self.store).read_adjudication(run_id))
        self.assertIn("requirement decisions for a Human: 1", counted)
        self.assert_tail(message, self.leading(), counted)

    def test_negative_control_a_failing_breakdown_leaves_the_stop_exactly_as_before(self) -> None:
        """AM-C1 / RB11INT-EVID-1 negative control: ``p4.wait_breakdown_text`` raising -> same code, same leading text,
        no tail."""
        self.wait()
        with mock.patch.object(p4, "wait_breakdown_text", side_effect=RuntimeError("breakdown failed")):
            stop = self.wait()
        self.assertEqual(self.leading(), str(stop), "exactly the pre-AM-C1 text")
        self.assertNotIn("It holds", str(stop))
        self.assertTrue(str(self.wait()).startswith(self.leading() + HOLDS), "breakdown computable again: the tail is back")

    def test_negative_control_an_unreadable_adjudication_leaves_the_stop_exactly_as_before(self) -> None:
        """AM-C1 / RB11INT-EVID-1 negative control: ``ReviewStore.read_adjudication`` raising ONLY for the breakdown read
        (caller ``_integration_exit_wait``); every other read in the flow is the real one."""
        self.wait()
        real = ReviewStore.read_adjudication

        def read(store, run_id):
            if called_from("_integration_exit_wait"):
                raise RuntimeError("adjudication unreadable")
            return real(store, run_id)

        with mock.patch.object(ReviewStore, "read_adjudication", read):
            stop = self.wait()
        self.assertEqual(self.leading(), str(stop))

    def test_a_wait_whose_adjudication_counts_nothing_says_a_human_is_still_needed(self) -> None:
        """AM-C1 / RB11INT-EVID-1: an Integration wait whose adjudication counts nothing (the shape of a wait resting on
        another ground, e.g. desired_state_change_required) must not print "requirement decisions for a Human: 0".

        SIMULATED INPUT: a consistent Integration adjudication cannot be HUMAN_WAIT with all three counts zero (the
        desired_state_change_required outcome itself requires a counted HUMAN obligation), so the breakdown read of the
        real waiting Run is replaced by its own record with the counted fields emptied (patch fires only when
        ``_integration_exit_wait`` is the caller). The START, the Run and the STOP are the real ones.
        """
        self.wait()
        real = ReviewStore.read_adjudication

        def read(store, run_id):
            found = real(store, run_id)
            if called_from("_integration_exit_wait"):
                return dataclasses.replace(found, entries=(), coverage_gaps=(),
                                           obligations={**found.obligations, "problem_high": 0, "problem_mid": 0})
            return found

        with mock.patch.object(ReviewStore, "read_adjudication", read):
            stop = self.wait()
        message = str(stop)
        self.assertTrue(message.startswith(self.leading() + HOLDS), message)
        self.assertNotIn("requirement decisions for a Human: 0", message)
        self.assertIn("the wait still needs a Human", message)


# --------------------------------------------------------------------------- AM-C3
class PhaseAlreadyExpandedMessageFlowTests(PhaseEntryCase):
    """AM-C3 (Sprint §41.31) through ``roadmap.enter_phase``; closes RB11INT-EVID-1 for AM-C3."""

    LEADING = ("is already expanded, so a new entry design is not accepted; read the current structure instead, and change "
               "it through Roadmap maintenance")
    GUIDANCE = "(a Phase whose Works the Roadmap registered is entered without a design)"

    def setUp(self) -> None:
        super().setUp()
        rm.enter_phase(self.store, self.phase, D1)

    def test_the_refusal_keeps_code_and_leading_text_appends_the_guidance_and_writes_nothing(self) -> None:
        """AM-C3 / RB11INT-EVID-1: code ``phase_already_expanded``; the unchanged leading text; the guidance appended after
        it; nothing written (no mutation opened, no ID reserved, Project snapshot unchanged)."""
        refused = self.assertRefusedAndUntouched(D1, "phase_already_expanded")
        self.assertEqual(f"Phase {self.phase} {self.LEADING} {self.GUIDANCE}", str(refused))


class PhaseEnteredWithoutDesignControlTests(WorklineTestCase):
    """AM-C3 negative control (Sprint §41.31); RB11INT-EVID-1."""

    def test_negative_control_a_phase_entered_without_a_design_is_not_refused(self) -> None:
        """AM-C3 / RB11INT-EVID-1 negative control: the route the guidance names (a Phase whose Works the Roadmap
        registered, entered with no design) is accepted by the same entry point and never raises
        ``phase_already_expanded``; the design-carrying entry of the same Phase is the refused one."""
        store = self.new_project()
        created = rm.create_roadmap(store, registered_plan())
        entered = rm.enter_phase(store, created.phase_ids["a"])
        self.assertFalse(entered.expanded)
        self.assertEqual(created.work_ids["a"]["a1"], entered.entry_work_id)
        with self.assertRaises(StopError) as refused:
            rm.enter_phase(store, created.phase_ids["a"], registered_design("x"))
        self.assertEqual("phase_already_expanded", refused.exception.code)


if __name__ == "__main__":
    unittest.main()
