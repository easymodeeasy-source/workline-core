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
from p5_helpers import decision_evidence
from rb5_run_helpers import Adjudicator, Discovery, IntegrationRunCase, claim, phase_review, repairing_executor
from workline import start as st
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


@contextlib.contextmanager
def global_policy_changed() -> Iterator[None]:
    """The loaded Global policy baseline record differs from the one at freeze (as after a promotion), so its digest
    differs while the authority digests stay the same."""
    import dataclasses

    real = review_policy.load_global_baseline

    def load(root: Any) -> Any:
        found = real(root)
        return dataclasses.replace(found, record={**found.record, "global_policy_version": 2})

    with mock.patch.object(review_policy, "load_global_baseline", load):
        yield


CHANGES = (("loader identity", loader_changed), ("authority / Global baseline", authority_changed),
           ("Global policy content", global_policy_changed))


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
        stops = {1: "launched", 2: "accepted", 3: "launched", 4: "sealed", 5: "recorded"}
        for generation, verb in stops.items():
            for label, change in CHANGES:
                with self.subTest(generation=generation, change=label):
                    discovery, adjudicator = Discovery(), Adjudicator()
                    store, _, ids = self.interrupted(f"g{generation}{label[:9].replace(' ', '').replace('/', '')}", generation,
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

    def test_a_change_while_the_adjudicator_runs_settles_no_branch(self) -> None:
        """F1: changed during the adjudicator's own launch, whichever branch its answer derives (AUTHORIZATION_READY,
        HUMAN_WAIT, DOMAIN_REPAIR_REQUIRED, CONFIRMATION_STRUCTURE_REQUIRED): ``review_context_changed`` before G4 -
        no adjudication, Finding, relation, successor Run, CREATE or repair plan; the Run stays at G3."""
        branches = (("ready", (), None), ("human", (claim("human"),), None), ("repair", (claim("problem"),), None),
                    ("structure", (), ri.HUMAN_CONFIRMATION_REQUIRED))
        for name, claims, kind in branches:
            with self.subTest(branch=name):
                changed = loader_changed()

                class Changing(Adjudicator):
                    def __call__(self, task: Any) -> Any:
                        changed.__enter__()
                        return super().__call__(task)

                store, phase_id, ids = self.marked_project(f"adj-{name}")
                works = set(ProjectView.load(store).works)
                log: list = []
                try:
                    with self.assertRaises(ReconcileRequired) as raised:
                        self.integrate(store, ids["integration"], phase_review(Discovery(*claims),
                                                                               adjudicator=Changing(kind)),
                                       executor=repairing_executor(store, log))
                finally:
                    changed.__exit__(None, None, None)
                self.assertEqual(sr.REASON_INTEGRATION_CONTEXT_CHANGED, raised.exception.reason)
                self.assertIn("nothing is settled", str(raised.exception))
                chain = self.one_run(store, ids["integration"])
                self.assertEqual(3, chain.latest.generation)
                self.assertFalse(ReviewStore(store).adjudication_exists(chain.review_run_id))
                self.assertEqual(works, set(ProjectView.load(store).works), "no Work is registered")
                self.assertEqual([], [entry for entry in log if entry[1] is not None], "no repair plan is asked")

    def test_a_g4_settled_run_begins_no_follow_up_after_its_context_changed(self) -> None:
        """F2 (CP F2 i): a Run settled at G4 under the old Context is not followed up after the change - no successor
        Run is reserved for a HUMAN_WAIT (even with a Human decision and its evidence), no confirmation is
        registered, no repair plan is asked - each ``review_context_changed``, the Run kept as it is."""
        for name, claims, kind in (("human", (claim("human"),), None), ("repair", (claim("problem"),), None),
                                   ("structure", (), ri.HUMAN_CONFIRMATION_REQUIRED)):
            for label, change in CHANGES[:2]:
                with self.subTest(branch=name, change=label):
                    store, phase_id, ids = self.marked_project(f"g4-{name}-{label[:6].strip()}")
                    integration = ids["integration"]
                    log: list = []
                    selector = phase_review(Discovery(*claims), adjudicator=Adjudicator(kind))
                    with crash_at(sr, "_integration_generation", after=True, when=after_generation(4)):
                        with self.assertRaises(Crash):
                            self.integrate(store, integration, selector, executor=repairing_executor(store, log))
                    (run_id,) = self.integration_runs(store, integration)
                    works = set(ProjectView.load(store).works)
                    if name == "human":
                        decision = p4.HumanDecision("hd-1", p4.DECISION_CONFIRMED)
                        evidence = decision_evidence(ReviewStore(store), run_id, decision,
                                                     sr.current_integration_requirement(store, integration))
                        selector = sr.PhaseIntegrationReview(
                            discovery=(Discovery().binding(),), adjudicator=Adjudicator().binding(),
                            human_decision=decision, decision_evidence=(evidence,))
                    with change(), self.assertRaises(ReconcileRequired) as raised:
                        self.integrate(store, integration, selector, executor=repairing_executor(store, log))
                    self.assertEqual(sr.REASON_INTEGRATION_CONTEXT_CHANGED, raised.exception.reason)
                    self.assertEqual([run_id], self.integration_runs(store, integration), "no successor Run")
                    self.assertEqual(works, set(ProjectView.load(store).works), "no Work is registered")
                    self.assertEqual([], [entry for entry in log if entry[1] is not None], "no repair plan is asked")
                    pending = MutationController(store).list_pending()
                    self.assertEqual(1, len(pending))
                    self.assertFalse((pending[0].get("notes") or {}).get(sr.NOTE_INTEGRATION_DECISIONS))
                    self.assertEqual(4, self.one_run(store, integration).latest.generation)

    def test_a_follow_up_or_terminal_stage_already_recorded_is_finished_from_its_record(self) -> None:
        """What was recorded before the change is finished from the record, as an interrupted stage always is: the
        integration's terminal stage, and a repair follow-up whose plan is kept."""
        store, _, ids = self.marked_project("terminal-recorded")
        with crash_at(st._Session, "_finalize_completion"), self.assertRaises(Crash):
            self.integrate(store, ids["integration"])
        with loader_changed():
            self.assertEqual("completed", self.integrate(store, ids["integration"]).status)
        store, _, ids = self.marked_project("plan-kept")
        log: list = []
        kept = lambda n, mutation, run_id, entry: entry is not None  # noqa: E731
        selector = phase_review(Discovery(claim("problem")))
        with crash_at(sr, "_set_followup", after=True, when=kept), self.assertRaises(Crash):
            self.integrate(store, ids["integration"], selector, executor=repairing_executor(store, log))
        asked = len(log)
        with loader_changed():
            moved = self.integrate(store, ids["integration"], selector, executor=repairing_executor(store, log))
        self.assertEqual("moved", moved.status)
        self.assertEqual(asked, len(log), "the kept plan is never asked again")

    def test_a_context_that_cannot_be_recomputed_is_its_own_stop_never_a_stale_difference(self) -> None:
        store, _, ids = self.interrupted("unavailable", 1, Discovery(), Adjudicator())
        unavailable = planning._context_unavailable("the implementation package cannot be read")
        with mock.patch.object(planning, "loader_identity", side_effect=unavailable):
            with self.assertRaises(StopError) as raised:
                self.integrate(store, ids["integration"])
        self.assertNotIsInstance(raised.exception, ReconcileRequired)
        self.assertEqual("review_context_unavailable", raised.exception.code)
        self.assert_untouched(store, ids, 1)

    def test_an_unavailable_global_baseline_or_an_invalid_global_policy_is_its_own_stop(self) -> None:
        store, _, ids = self.interrupted("baseline", 1, Discovery(), Adjudicator())
        for code, side in (("review_p6_baseline_unavailable", review_policy.stop(
                review_policy.CODE_BASELINE_UNAVAILABLE, "the Global policy cannot be read")),
                           ("review_record_invalid", None)):
            with self.subTest(code=code):
                patch = mock.patch.object(review_policy, "_read_global_policy", side_effect=side) if side else \
                    mock.patch.object(review_policy, "_read_global_policy", lambda root: b"not: a policy\n")
                with patch, self.assertRaises(StopError) as raised:
                    self.integrate(store, ids["integration"])
                self.assertNotIsInstance(raised.exception, ReconcileRequired)
                self.assertEqual(code, raised.exception.code)
                self.assert_untouched(store, ids, 1)

    def test_a_pending_generation_is_finished_and_the_next_launch_is_refused(self) -> None:
        """F3: a generation mutation recorded before the change is finished from its record (it is the already
        accepted material), and the next launch over the changed Context is refused."""
        from workline import roadmap_review as rr_module

        store, _, ids = self.marked_project("pending-g1")
        finishing = lambda n, store_, gen, *a, **k: (gen.invocation or {}).get("generation") == 1  # noqa: E731
        discovery = Discovery()
        with crash_at(rr_module, "_finish_generation", when=finishing), self.assertRaises(Crash):
            self.integrate(store, ids["integration"], phase_review(discovery))
        with loader_changed(), self.assertRaises(ReconcileRequired) as raised:
            self.integrate(store, ids["integration"], phase_review(discovery))
        self.assertEqual(sr.REASON_INTEGRATION_CONTEXT_CHANGED, raised.exception.reason)
        self.assertEqual([], discovery.tasks)
        self.assertEqual(1, self.one_run(store, ids["integration"]).latest.generation)

    def test_a_frozen_context_that_is_not_the_candidates_is_never_compared_as_current(self) -> None:
        """The START record's frozen Context must be the very one the Candidate binds by digest."""
        run = sr.IntegrationRun("wrk_x", "rr_x", {"review_context_digest": OTHER}, {"schema": "x"}, None, "p")
        with self.assertRaises(ReconcileRequired) as raised:
            sr._integration_context_problems(mock.Mock(), run)
        self.assertEqual(p4.REASON_CHAIN_INVALID, raised.exception.reason)
