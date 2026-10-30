"""§37.21 Phase Integration Review Context currency: the bound Context is re-derived, never only frozen.

A Phase Integration Review Run binds its Review Context (the running loader's
identity and the Global policy baseline, whose digest carries the runtime
authority digests of registry.md and the review / roadmap / start Skills) once,
when the Run is frozen. Before every reviewer launch, at the G5 seal and at the
terminal gate the Context is recomputed exactly as at freeze and compared with
the digest the Candidate binds; the frozen Effective Policy of the open Run is
kept as frozen and never re-resolved (R6-1).
"""

from __future__ import annotations

import contextlib
from typing import Any, Iterator
from unittest import mock

from planning_helpers import Crash, crash_at
from rb5_run_helpers import Adjudicator, Discovery, IntegrationRunCase, phase_review
from workline import start_review as sr
from workline.errors import ReconcileRequired, StopError
from workline.mutation import MutationController
from workline.review import integration as ri
from workline.review import p4
from workline.review import planning
from workline.review import policy as review_policy
from workline.review.store import ReviewStore
from workline.state import ProjectView
from workline.validate import validate_project

OTHER = "f" * 64


@contextlib.contextmanager
def loader_changed() -> Iterator[None]:
    """The running implementation package is another one than the Run was frozen under."""
    with mock.patch.object(planning, "loader_identity", lambda directory: OTHER):
        yield


@contextlib.contextmanager
def authority_changed() -> Iterator[None]:
    """registry.md reads other bytes than at freeze, so the Global baseline digest re-derives differently."""
    real = review_policy.baseline_authority_digests

    def digests(root: Any) -> list[dict[str, str]]:
        return [{**entry, "digest": OTHER} if entry["id"] == "registry" else entry for entry in real(root)]

    with mock.patch.object(review_policy, "baseline_authority_digests", digests):
        yield


CHANGES = (("loader identity", loader_changed), ("authority / Global baseline", authority_changed))


def after_generation(number: int):
    return lambda n, *args, **kwargs: args[2] == number


class ContextCurrencyTests(IntegrationRunCase):
    def interrupted(self, name: str, generation: int, discovery: Discovery, adjudicator: Adjudicator):
        """A marked integration whose START stopped right after committing ``generation`` of its one Run."""
        store, phase_id, ids = self.marked_project(name)
        with crash_at(sr, "_integration_generation", after=True, when=after_generation(generation)):
            with self.assertRaises(Crash):
                self.integrate(store, ids["integration"], phase_review(discovery, adjudicator=adjudicator))
        chain = self.one_run(store, ids["integration"])
        self.assertEqual(generation, chain.latest.generation)
        return store, phase_id, ids

    def assert_untouched(self, store, ids: dict[str, str], generation: int) -> None:
        chain = self.one_run(store, ids["integration"])
        self.assertEqual(generation, chain.latest.generation, "no generation is written over a stale Context")
        self.assertEqual([], list(ReviewStore(store).consumptions()))
        self.assertEqual("in_progress", ProjectView.load(store).work_state(ids["integration"]).state)
        self.assertEqual(1, len(MutationController(store).list_pending()), "the START stays pending, unchanged")

    def test_a_context_change_after_freeze_refuses_every_reviewer_launch_seal_and_terminal_stage(self) -> None:
        """Changed between freeze and the discovery launch (G1), the adjudicator launch (G3), the G5 seal (G4) and
        the terminal gate (G5): START refuses with reason ``review_context_changed`` before the launch / Receipt /
        terminal stage, and nothing of the Run moves on."""
        stops = {1: "launched", 3: "launched", 4: "sealed", 5: "recorded"}
        for generation, verb in stops.items():
            for label, change in CHANGES:
                with self.subTest(generation=generation, change=label):
                    discovery, adjudicator = Discovery(), Adjudicator()
                    store, _, ids = self.interrupted(f"g{generation}{label[:6].strip().replace(' ', '')}", generation,
                                                     discovery, adjudicator)
                    asked = (len(discovery.tasks), len(adjudicator.tasks))
                    with change():
                        with self.assertRaises(ReconcileRequired) as raised:
                            self.integrate(store, ids["integration"], phase_review(discovery, adjudicator=adjudicator))
                    self.assertEqual(sr.REASON_INTEGRATION_CONTEXT_CHANGED, raised.exception.reason)
                    self.assertIn(f"nothing is {verb}", str(raised.exception))
                    self.assertEqual(asked, (len(discovery.tasks), len(adjudicator.tasks)), "no actor is launched")
                    self.assert_untouched(store, ids, generation)
                    if generation >= 4:
                        self.assertEqual(generation == 5, self.one_run(store, ids["integration"]).latest.sealed)

    def test_the_same_run_finishes_once_the_context_re_derives_again_and_its_policy_is_never_re_resolved(self) -> None:
        """Valid path: the Context that re-derives to the frozen digest is current, and the same Run finishes under
        its frozen Effective Policy - ``new_run_effective_policy`` is never called again for the open Run (R6-1)."""
        discovery, adjudicator = Discovery(), Adjudicator()
        store, phase_id, ids = self.interrupted("restored", 1, discovery, adjudicator)
        (run_id,) = self.integration_runs(store, ids["integration"])
        with loader_changed(), self.assertRaises(ReconcileRequired):
            self.integrate(store, ids["integration"], phase_review(discovery, adjudicator=adjudicator))
        with mock.patch.object(review_policy, "new_run_effective_policy",
                               side_effect=AssertionError("re-resolved")) as resolved:
            result = self.integrate(store, ids["integration"], phase_review(discovery, adjudicator=adjudicator))
        self.assertEqual("completed", result.status)
        self.assertEqual(0, resolved.call_count)
        self.assertEqual([run_id], self.integration_runs(store, ids["integration"]), "the same Run, no successor")
        self.assertTrue(self.one_run(store, ids["integration"]).latest.sealed)
        self.assertTrue(ProjectView.load(store).phase_completion(phase_id).complete)
        self.assertEqual([], MutationController(store).list_pending())
        self.assertEqual([], validate_project(store))

    def test_a_change_inside_one_invocation_between_freeze_and_launch_is_refused(self) -> None:
        """Not only across a resume: changed after G1 is recorded and before the discovery launch of the same START."""
        store, _, ids = self.marked_project()
        discovery = Discovery()
        changed = loader_changed()
        real = sr._integration_accept

        def accept(*args: Any, **kwargs: Any) -> None:
            real(*args, **kwargs)
            changed.__enter__()

        try:
            with mock.patch.object(sr, "_integration_accept", accept), self.assertRaises(ReconcileRequired) as raised:
                self.integrate(store, ids["integration"], phase_review(discovery))
        finally:
            changed.__exit__(None, None, None)
        self.assertEqual(sr.REASON_INTEGRATION_CONTEXT_CHANGED, raised.exception.reason)
        self.assertEqual([], discovery.tasks)
        self.assert_untouched(store, ids, 1)

    def test_a_change_while_the_adjudicator_runs_is_a_g4_terminal_not_authorizable_disposition(self) -> None:
        """Changed during the adjudicator's own launch: its answer is settled at G4 as the step-4 refusal
        ``phase_integration_not_authorizable`` (final not_authorized), so no Receipt issues for the old Context."""
        changed = loader_changed()

        class Changing(Adjudicator):
            def __call__(self, task: Any) -> Any:
                changed.__enter__()
                return super().__call__(task)

        store, _, ids = self.marked_project()
        try:
            with self.assertRaises(StopError) as raised:
                self.integrate(store, ids["integration"], phase_review(Discovery(), adjudicator=Changing()))
        finally:
            changed.__exit__(None, None, None)
        self.assertEqual(ri.CODE_NOT_AUTHORIZABLE, raised.exception.code)
        chain = self.one_run(store, ids["integration"])
        self.assertEqual((4, None), (chain.latest.generation, chain.latest.receipt_id))
        self.assertEqual(ri.CODE_NOT_AUTHORIZABLE,
                         ReviewStore(store).read_adjudication(chain.review_run_id).integration_disposition)

    def test_a_context_that_cannot_be_recomputed_is_its_own_stop_never_a_stale_difference(self) -> None:
        store, _, ids = self.interrupted("unavailable", 1, Discovery(), Adjudicator())
        unavailable = planning._context_unavailable("the implementation package cannot be read")
        with mock.patch.object(planning, "loader_identity", side_effect=unavailable):
            with self.assertRaises(StopError) as raised:
                self.integrate(store, ids["integration"])
        self.assertNotIsInstance(raised.exception, ReconcileRequired)
        self.assertEqual("review_context_unavailable", raised.exception.code)
        self.assert_untouched(store, ids, 1)

    def test_a_frozen_context_that_is_not_the_candidates_is_never_compared_as_current(self) -> None:
        """The START record's frozen Context must be the very one the Candidate binds by digest."""
        run = sr.IntegrationRun("wrk_x", "rr_x", {"review_context_digest": OTHER}, {"schema": "x"}, None, "p")
        with self.assertRaises(ReconcileRequired) as raised:
            sr._integration_context_problems(mock.Mock(), run)
        self.assertEqual(p4.REASON_CHAIN_INVALID, raised.exception.reason)
