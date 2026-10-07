"""RB5 §32.54: structural coverage / reviewed completion mode - pure, over canonical metadata, events and relations.

Runs against :mod:`rb5_doubles` (in-memory views of plain store Entities). The state.py reviewed predicate, the
validate.py marker / coverage-order wiring and CREATE's edge refusal landed with the post-RB6 integration I-2
(rows R03 - R06), and the replan owners' refusal (``ops.plan_replan``) with its ops / START half;
``StateIntegrationDeferredTests`` and ``StructuralWiringTests`` prove them.
"""

from __future__ import annotations

import unittest

from dataclasses import replace

from helpers import WorklineTestCase, git
from workline import roadmap as rm
from workline import start as st
from workline.ops import Replan
from rb5_doubles import CONFIRMATION, INTEGRATION, V1, ViewBuilder, ident, reviewed_phase
from workline import phase_integration as pi
from workline.create import INTEGRATION_COVERAGE_ORDER, RelationSpec, WorkSpec, register_works
from workline.errors import ValidationError
from workline.mutation import Effect, MutationController, WriteScope
from workline.oplock import project_operation
from workline.state import COMPLETE, COMPLETED, IN_PROGRESS, ProjectView
from workline.store import Entity, Event, Relation
from workline.validate import validate_project, validate_structure


class MarkerDetectionTests(unittest.TestCase):
    def test_only_an_integration_with_the_exact_contract_is_reviewed(self) -> None:
        b = ViewBuilder()
        phase = b.phase()
        marked = b.integration(phase)
        legacy = b.integration(phase, marker=None)
        other = b.integration(phase, marker="phase-integration-review-v2")
        normal = b.work(phase, marker=V1)  # a stray marker on a normal Work is never a reviewed integration
        view = b.view()
        self.assertTrue(pi.is_reviewed_integration(view.works[marked]))
        for work_id in (legacy, other, normal):
            with self.subTest(work=work_id):
                self.assertFalse(pi.is_reviewed_integration(view.works[work_id]))

    def test_completion_mode_follows_the_effective_plan(self) -> None:
        b = ViewBuilder()
        legacy_phase = b.phase()
        b.integration(legacy_phase, marker=None)
        reviewed = b.phase()
        b.integration(reviewed)
        excluded = b.phase()
        marked = b.integration(excluded)
        b.exclude(marked)
        b.integration(excluded, marker=None)
        view = b.view()
        self.assertEqual(pi.MODE_LEGACY, pi.completion_mode(view, legacy_phase))
        self.assertEqual(pi.MODE_REVIEWED, pi.completion_mode(view, reviewed))
        self.assertEqual(pi.MODE_LEGACY, pi.completion_mode(view, excluded), "an excluded marked integration")
        self.assertEqual(V1, pi.MODE_REVIEWED)
        self.assertEqual((V1,), pi.SUPPORTED_PHASE_REVIEW_CONTRACTS)


class ClassificationTests(unittest.TestCase):
    def test_the_exact_five_classes(self) -> None:
        b = ViewBuilder()
        phase = b.phase()
        old = b.integration(phase, marker=None)
        w1, w2, late = b.work(phase, "W1"), b.work(phase, "W2"), b.work(phase, "Late")
        b.requires(w1, old)
        b.requires(w2, old)
        b.complete(w1, w2, old)
        current = b.integration(phase)
        b.requires(w1, current)
        b.requires(w2, current)
        confirmation = b.confirmation(phase, current)
        view = b.view()
        self.assertEqual(
            {old: pi.HISTORICAL_INTEGRATION, w1: pi.PRE_INTEGRATION, w2: pi.PRE_INTEGRATION,
             late: pi.INVALID_UNCOVERED, current: pi.CURRENT_INTEGRATION,
             confirmation: pi.POST_INTEGRATION_CONFIRMATION},
            pi.classify_coverage(view, phase, current),
        )
        self.assertEqual(set(pi.COVERAGE_CLASSES), set(pi.classify_coverage(view, phase, current).values()))
        self.assertEqual((late,), pi.invalid_uncovered_ids(view, phase, current))

    def test_coverage_needs_a_direct_edge_not_a_transitive_one(self) -> None:
        b = ViewBuilder()
        phase = b.phase()
        first, second = b.work(phase, "First"), b.work(phase, "Second")
        integration = b.integration(phase)
        b.requires(first, second)
        b.requires(second, integration)
        view = b.view()
        self.assertEqual(pi.INVALID_UNCOVERED, pi.classify_coverage(view, phase, integration)[first])
        self.assertEqual((first,), pi.missing_predecessor_ids(view, phase, integration))

    def test_a_confirmation_is_downstream_by_the_direct_edge_alone(self) -> None:
        """Ruling R5-1 (§14.6 over the §32.8 wording): confirmation_target is not a classification input."""
        b = ViewBuilder()
        phase = b.phase()
        integration = b.integration(phase)
        both = b.confirmation(phase, integration)
        target_only = b.confirmation(phase, integration, edge=False)
        other = b.work(phase, "Other")
        edge_only = b.work(phase, "EdgeOnly", kind=CONFIRMATION, target=other)
        b.requires(integration, edge_only)
        middle = b.work(phase, "Middle")
        transitive = b.work(phase, "Transitive", kind=CONFIRMATION, target=integration)
        b.requires(integration, middle)
        b.requires(middle, transitive)
        view = b.view()
        classes = pi.classify_coverage(view, phase, integration)
        self.assertEqual(pi.POST_INTEGRATION_CONFIRMATION, classes[both])
        self.assertEqual(pi.POST_INTEGRATION_CONFIRMATION, classes[edge_only], "the edge decides, not the target")
        self.assertEqual(pi.INVALID_UNCOVERED, classes[target_only], "target without the requires_completion edge")
        self.assertEqual(pi.INVALID_UNCOVERED, classes[transitive], "a transitive edge is not a direct one")
        self.assertEqual(sorted([both, edge_only]), [w.id for w in pi.downstream_confirmations(view, phase, integration)])

    def test_a_list_confirmation_target_including_the_integration_counts(self) -> None:
        b = ViewBuilder()
        phase = b.phase()
        normal = b.work(phase)
        integration = b.integration(phase)
        listed = b.work(phase, "Listed", kind=CONFIRMATION, target=[normal, integration])
        b.requires(integration, listed)
        self.assertTrue(pi.is_downstream_confirmation(b.view(), b.view().works[listed], integration))

    def test_a_normal_work_never_becomes_post_integration_by_order(self) -> None:
        b = ViewBuilder()
        phase = b.phase()
        integration = b.integration(phase, number=1)
        b.complete(integration)
        after = b.work(phase, "After", number=99)  # later ID, later events, downstream edge
        b.requires(integration, after)
        b.complete(after)
        self.assertEqual(pi.INVALID_UNCOVERED, pi.classify_coverage(b.view(), phase, integration)[after])

    def test_human_ng_reintegration_returns_to_the_same_confirmation_and_the_phase_completes(self) -> None:
        """RB5A-01 / RB5B-M8 / R-2: the start._human_ng structure under ruling R5-1.

        W1, W2 -> I1 (reviewed) -> c (target I1). c judges NG: fix F and reviewed reintegration I2 with
        ``I2 -> c`` (c keeps target I1) and the closure W1, W2, F -> I2 (c planned downstream, so no cycle).
        """
        b = ViewBuilder()
        phase, normal, first, confirmation = reviewed_phase(b, complete=False, confirmation=True)
        b.complete(*normal, first)
        b.start(confirmation)
        fix = b.work(phase, "Fix")
        closure = pi.required_pre_integration_ids(b.view(), phase, None, planned_downstream=[confirmation])
        self.assertEqual(sorted(normal + [fix]), list(closure), "c is never a pre-integration predecessor")
        second = b.integration(phase)
        b.requires(second, confirmation)  # start._human_ng: RelationSpec("requires_completion", "integration", c)
        for work_id in closure:
            b.requires(work_id, second)
        view = b.view()
        self.assertEqual([], validate_structure(view), "no cycle, structurally valid")
        self.assertEqual(pi.POST_INTEGRATION_CONFIRMATION, pi.classify_coverage(view, phase, second)[confirmation])
        self.assertEqual((), pi.missing_predecessor_ids(view, phase, second))
        b.complete(fix, second)
        b.event(confirmation, "work_completed")
        view = b.view()
        self.assertEqual((second,), pi.covering_integration_ids(view, phase))
        self.assertEqual(pi.COVERAGE_COVERED, pi.coverage_status(view, phase).status)
        self.assertTrue(pi.phase_generated_complete(view, phase))
        self.assertNotIn(first, pi.covering_integration_ids(view, phase), "the old integration never saw the fix")

    def test_cpq01_a_relation_added_later_never_launders_late_work(self) -> None:
        """Ruling CPQ-01: coverage of a completed integration needs the Work to complete BEFORE it (canonical order)."""
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b)
        late = b.work(phase, "Late")
        b.complete(late)
        self.assertEqual([], pi.completed_integration_edge_problems(b.view(), [("requires_completion", normal[0],
                                                                               integration)]),
                         "a Work that completed before the integration passes the same predicate")
        self.assertEqual(1, len(pi.completed_integration_edge_problems(b.view(), [("requires_completion", late,
                                                                                  integration)])))
        b.requires(late, integration)  # the manual relation the owners refuse
        view = b.view()
        self.assertEqual(pi.INVALID_UNCOVERED, pi.classify_coverage(view, phase, integration)[late])
        self.assertEqual((), pi.covering_integration_ids(view, phase))
        self.assertEqual(((integration, (late,)),), pi.coverage_status(view, phase).stale)
        self.assertFalse(pi.phase_generated_complete(view, phase))
        problems = pi.coverage_order_problems(view)
        self.assertEqual(1, len(problems))
        self.assertEqual("integration_coverage_order", problems[0][0])
        self.assertIn(late, problems[0][1])

    def test_cpq01_canonical_order_is_the_event_log_never_the_timestamp(self) -> None:
        b = ViewBuilder()
        phase = b.phase()
        work = b.work(phase)
        integration = b.integration(phase)
        b.requires(work, integration)
        b.start(work)
        b.start(integration)
        b.events.append(Event(ident("evt", 501), "work_completed", integration, "2026-10-06T00:00:00Z"))
        b.events.append(Event(ident("evt", 500), "work_completed", work, "2000-01-01T00:00:00Z"))  # earlier `at`, lower ID
        view = b.view()
        ranks = pi.completion_ranks(view, [work, integration])
        self.assertLess(ranks[integration], ranks[work])
        self.assertFalse(pi.completed_before(ranks, work, integration))
        self.assertEqual(pi.INVALID_UNCOVERED, pi.classify_coverage(view, phase, integration)[work])
        self.assertEqual((), pi.covering_integration_ids(view, phase))

    def test_cpq01_never_applies_to_an_unfinished_integration(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        self.assertEqual(pi.PRE_INTEGRATION, pi.classify_coverage(b.view(), phase, integration)[normal[0]])
        self.assertEqual([], pi.coverage_order_problems(b.view()))

    def test_cpq02_an_unfinished_other_integration_is_not_historical(self) -> None:
        """Ruling CPQ-02: historical_integration is an older COMPLETED integration."""
        b = ViewBuilder()
        phase, normal, first, _ = reviewed_phase(b)
        late = b.work(phase, "Late")
        second = b.integration(phase)
        for work_id in normal + [late]:
            b.requires(work_id, second)
        view = b.view()
        self.assertEqual(pi.INVALID_UNCOVERED, pi.classify_coverage(view, phase, first)[second])
        self.assertEqual(pi.HISTORICAL_INTEGRATION, pi.classify_coverage(view, phase, second)[first])
        self.assertNotIn(first, pi.covering_integration_ids(view, phase))
        status = pi.coverage_status(view, phase)
        self.assertEqual(pi.COVERAGE_STALE, status.status)
        self.assertIn(second, dict(status.stale)[first], "the unfinished integration is exposed as invalid")
        b.complete(late, second)
        view = b.view()
        self.assertEqual(pi.HISTORICAL_INTEGRATION, pi.classify_coverage(view, phase, first)[second],
                         "once completed it is historical, whatever its order relative to the other")
        self.assertEqual((second,), pi.covering_integration_ids(view, phase))

    def test_cpq02_two_unfinished_integrations_stay_a_structural_stop(self) -> None:
        b = ViewBuilder()
        phase, _, first, _ = reviewed_phase(b, complete=False)
        second = b.integration(phase)
        view = b.view()
        self.assertEqual(pi.INVALID_UNCOVERED, pi.classify_coverage(view, phase, first)[second])
        self.assertEqual(pi.INVALID_UNCOVERED, pi.classify_coverage(view, phase, second)[first])
        self.assertEqual((pi.ROUTE_STRUCTURAL_STOP, None), pi.late_work_route(view, phase))
        self.assertIn("integration_invariant", [p.code for p in validate_structure(view)])

    def test_superset_predecessors_still_cover(self) -> None:
        b = ViewBuilder()
        phase, normal, old, _ = reviewed_phase(b)
        other_phase = b.phase()
        foreign = b.work(other_phase, "Foreign")
        b.complete(foreign)
        late = b.work(phase, "Late")
        new = b.integration(phase)
        for work_id in normal + [late, old, foreign]:  # an extra historical integration and a cross-Phase Work
            b.requires(work_id, new)
        b.complete(late, new)
        self.assertEqual((new,), pi.covering_integration_ids(b.view(), phase))

    def test_a_held_work_is_still_a_required_predecessor(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        held = b.work(phase, "Held")
        b.start(held)
        b.event(held, "work_held")
        view = b.view()
        self.assertIn(held, pi.required_pre_integration_ids(view, phase, integration))
        self.assertEqual((held,), pi.missing_predecessor_ids(view, phase, integration))

    def test_only_a_confirmation_can_be_planned_downstream(self) -> None:
        b = ViewBuilder()
        phase, normal, _, _ = reviewed_phase(b)
        with self.assertRaises(ValidationError):
            pi.required_pre_integration_ids(b.view(), phase, None, planned_downstream=[normal[0]])

    def test_historical_integrations_are_never_required_predecessors(self) -> None:
        b = ViewBuilder()
        phase = b.phase()
        old = b.integration(phase, marker=None)
        work = b.work(phase)
        b.requires(work, old)
        b.complete(work, old)
        new = b.integration(phase)
        b.requires(work, new)
        view = b.view()
        self.assertEqual((work,), pi.required_pre_integration_ids(view, phase, new))
        self.assertEqual((), pi.missing_predecessor_ids(view, phase, new))
        self.assertEqual(pi.HISTORICAL_INTEGRATION, pi.classify_coverage(view, phase, new)[old])

    def test_excluded_works_are_not_classified(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        dropped = b.work(phase, "Dropped")
        b.exclude(dropped)
        classes = pi.classify_coverage(b.view(), phase, integration)
        self.assertNotIn(dropped, classes)
        self.assertEqual(set(normal) | {integration}, set(classes))

    def test_classification_refuses_what_is_not_an_effective_integration_of_the_phase(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        other = b.phase()
        for work_id, phase_id in ((normal[0], phase), (integration, other)):
            with self.subTest(work=work_id), self.assertRaises(ValidationError):
                pi.classify_coverage(b.view(), phase_id, work_id)
        b.cancel(integration)
        with self.assertRaises(ValidationError):
            pi.classify_coverage(b.view(), phase, integration)


class CoveringIntegrationTests(unittest.TestCase):
    def test_one_completed_covering_integration_satisfies_the_structural_predicate(self) -> None:
        b = ViewBuilder()
        phase, _, integration, _ = reviewed_phase(b)
        view = b.view()
        self.assertEqual((integration,), pi.covering_integration_ids(view, phase))
        status = pi.coverage_status(view, phase)
        self.assertEqual((pi.MODE_REVIEWED, pi.COVERAGE_COVERED), (status.mode, status.status))
        self.assertEqual((), pi.completion_reasons(view, phase))
        self.assertEqual(COMPLETE, view.phase_state(phase))
        self.assertTrue(pi.phase_generated_complete(view, phase))

    def test_late_work_makes_the_old_integration_stale(self) -> None:
        b = ViewBuilder()
        phase, _, integration, _ = reviewed_phase(b)
        late = b.work(phase, "Late")
        b.complete(late)  # even completed, an uncovered late Work leaves the reviewed basis stale
        view = b.view()
        self.assertEqual((), pi.covering_integration_ids(view, phase))
        status = pi.coverage_status(view, phase)
        self.assertEqual(pi.COVERAGE_STALE, status.status)
        self.assertEqual(((integration, (late,)),), status.stale)
        # Flipped at the post-RB6 integration I-2 (R05, playbook MC-4): the legacy predicate alone would call it
        # complete; generated state now applies the reviewed predicate (state.py, §32.9).
        self.assertNotEqual(COMPLETE, view.phase_state(phase), "the legacy predicate alone would call it complete")
        self.assertEqual(pi.completion_reasons(view, phase), view.phase_completion(phase).reasons)
        self.assertFalse(pi.phase_generated_complete(view, phase))
        self.assertIn("stale", pi.completion_reasons(view, phase)[0])
        self.assertIn("reintegration required", pi.completion_reasons(view, phase)[0])

    def test_stale_with_a_pending_reintegration_names_it(self) -> None:
        """RB5A-06: the stale reason says which reintegration it awaits."""
        b = ViewBuilder()
        phase, normal, old, _ = reviewed_phase(b)
        late = b.work(phase, "Late")
        new = b.integration(phase)
        for work_id in normal + [late]:
            b.requires(work_id, new)
        status = pi.coverage_status(b.view(), phase)
        self.assertEqual((pi.COVERAGE_STALE, (new,)), (status.status, status.unfinished_reviewed_integration_ids))
        self.assertIn(f"awaiting reintegration {new}", status.reasons[0])
        self.assertNotIn("reintegration required", status.reasons[0])

    def test_an_edge_onto_a_completed_reviewed_integration_is_refused_by_the_owner_seam(self) -> None:
        """RB5A-02: the pure seam owners call before adding relations; the owner wiring is deferred."""
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b)
        legacy_phase = b.phase()
        legacy = b.integration(legacy_phase, marker=None)
        b.complete(legacy)
        late = b.work(phase, "Late")
        view = b.view()
        problems = pi.completed_integration_edge_problems(view, [("requires_completion", late, integration)])
        self.assertEqual(1, len(problems))
        self.assertIn(integration, problems[0])
        self.assertEqual([], pi.completed_integration_edge_problems(view, [("planned_next", late, integration),
                                                                           ("requires_completion", late, legacy)]))
        unfinished = ViewBuilder()
        u_phase, _, u_integration, _ = reviewed_phase(unfinished, complete=False)
        u_late = unfinished.work(u_phase, "Late")
        self.assertEqual([], pi.completed_integration_edge_problems(unfinished.view(),
                                                                    [("requires_completion", u_late, u_integration)]))

    def test_any_exact_cover_satisfies_and_none_is_chosen_by_newest_id(self) -> None:
        b = ViewBuilder()
        phase = b.phase()
        work = b.work(phase, number=50)
        first = b.integration(phase, number=90)  # completed first, highest ID ...
        b.requires(work, first)
        b.complete(work, first)
        second = b.integration(phase, number=10)  # ... completed later, lowest ID: both cover exactly
        b.requires(work, second)
        b.complete(second)
        view = b.view()
        self.assertEqual([], validate_structure(view))
        self.assertEqual((second, first), pi.covering_integration_ids(view, phase), "a listing in ID order")
        self.assertEqual(pi.COVERAGE_COVERED, pi.coverage_status(view, phase).status)
        late = b.work(phase, "Late")
        b.requires(late, second)  # an edge added after `second` completed: CPQ-01 denies it as coverage
        b.complete(late)
        self.assertEqual((), pi.covering_integration_ids(b.view(), phase), "late Work is never laundered")
        self.assertEqual(pi.COVERAGE_STALE, pi.coverage_status(b.view(), phase).status)

    def test_an_old_integration_cannot_cover_an_expanded_plan_whatever_its_id_or_time(self) -> None:
        b = ViewBuilder()
        phase, normal, old, _ = reviewed_phase(b)
        late = b.work(phase, "Late", number=1)  # the oldest ID of all
        b.complete(late)
        self.assertNotIn(old, pi.covering_integration_ids(b.view(), phase))

    def test_missing_coverage_until_the_reviewed_integration_completes(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        b.complete(*normal)
        view = b.view()
        status = pi.coverage_status(view, phase)
        self.assertEqual(pi.COVERAGE_MISSING, status.status)
        self.assertEqual((integration,), status.unfinished_reviewed_integration_ids)
        self.assertIn(integration, status.reasons[0])

    def test_a_legacy_phase_keeps_the_legacy_predicate(self) -> None:
        b = ViewBuilder()
        phase = b.phase()
        work = b.work(phase)
        integration = b.integration(phase, marker=None)
        b.requires(work, integration)
        uncovered = b.work(phase, "NoEdge")  # legacy allows a before_integration=False Work
        b.complete(work, integration, uncovered)
        view = b.view()
        status = pi.coverage_status(view, phase)
        self.assertEqual((pi.MODE_LEGACY, pi.COVERAGE_NOT_APPLICABLE), (status.mode, status.status))
        self.assertEqual((), pi.completion_reasons(view, phase))
        self.assertTrue(pi.phase_generated_complete(view, phase))

    def test_downstream_confirmation_is_required_complete_through_the_legacy_check(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, confirmation = reviewed_phase(b, complete=False, confirmation=True)
        b.complete(*normal, integration)
        view = b.view()
        self.assertEqual((integration,), pi.covering_integration_ids(view, phase))
        self.assertNotEqual(COMPLETE, view.phase_state(phase), "Phase incomplete until the confirmation completes")
        self.assertFalse(pi.phase_generated_complete(view, phase))
        b.complete(confirmation)
        self.assertTrue(pi.phase_generated_complete(b.view(), phase))

    def test_reviewed_reasons_need_no_store(self) -> None:
        """The predicate reads only the view's entities / events / relations (a view with no store at all).

        That no Review code is even loaded is pinned separately by
        test_phase_integration_boundaries.py::InertTests::test_the_structural_module_and_generated_state_load_no_review_code.
        """
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        view = b.view()
        self.assertIsNone(view.store)
        self.assertEqual((), pi.completion_reasons(view, phase))

    def test_the_doubles_build_valid_structure(self) -> None:
        b = ViewBuilder()
        reviewed_phase(b, confirmation=True)
        self.assertEqual([], validate_structure(b.view()))


class LateWorkRouteTests(unittest.TestCase):
    def test_routes(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        self.assertEqual((pi.ROUTE_ADD_TO_UNFINISHED, integration), pi.late_work_route(b.view(), phase))
        b.complete(*normal, integration)
        self.assertEqual((pi.ROUTE_REINTEGRATION_REQUIRED, None), pi.late_work_route(b.view(), phase))
        b.integration(phase)
        b.integration(phase)
        self.assertEqual((pi.ROUTE_STRUCTURAL_STOP, None), pi.late_work_route(b.view(), phase))

    def test_a_reviewed_phase_never_routes_late_work_to_an_unmarked_integration(self) -> None:
        """RB5A-05."""
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        unmarked = b.integration(phase, marker=None)
        self.assertEqual((pi.ROUTE_UNMARKED_UNFINISHED, unmarked), pi.late_work_route(b.view(), phase))
        legacy = ViewBuilder()
        legacy_phase = legacy.phase()
        legacy_integration = legacy.integration(legacy_phase, marker=None)
        self.assertEqual((pi.ROUTE_ADD_TO_UNFINISHED, legacy_integration), pi.late_work_route(legacy.view(), legacy_phase),
                         "a legacy Phase keeps its route")


class FactsTests(unittest.TestCase):
    def test_facts_bind_kinds_markers_states_terminal_events_and_edges(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, confirmation = reviewed_phase(b, confirmation=True)
        view = b.view()
        facts = pi.effective_work_facts(view, phase)
        self.assertEqual(sorted(normal + [integration, confirmation]), [fact["work_id"] for fact in facts])
        by_id = {fact["work_id"]: fact for fact in facts}
        self.assertEqual(V1, by_id[integration][pi.PHASE_REVIEW_CONTRACT_KEY])
        self.assertIsNone(by_id[normal[0]][pi.PHASE_REVIEW_CONTRACT_KEY])
        completed = [e.id for e in view.events_for(integration) if e.type == "work_completed"]
        self.assertEqual(completed[0], by_id[integration]["terminal_event_id"])
        self.assertEqual(
            {"integration_id": integration, "predecessor_ids": sorted(normal),
             "downstream_confirmation_ids": [confirmation]},
            pi.coverage_facts(view, phase, integration),
        )
        self.assertEqual(len(normal) + 1, len(pi.dependency_edges(view, phase)))


class StateIntegrationDeferredTests(WorklineTestCase):
    def test_reviewed_phase_state_is_generated_without_review_store_read(self) -> None:
        """state.py (I-2, R05; §32.9): generated Phase state applies the reviewed predicate from entity / event /
        relation truth alone.

        The view has no store at all, so no Review record - or any file - can be read; that no Review code is even
        loaded is pinned by test_phase_integration_boundaries.py InertTests. The reviewed reasons are asked only once
        every legacy check holds (the recorded cost variant), and a legacy Phase keeps exactly its legacy predicate.
        """
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        view = b.view()
        self.assertIsNone(view.store)
        self.assertEqual((True, ()), (view.phase_completion(phase).complete, view.phase_completion(phase).reasons))
        self.assertEqual(COMPLETE, view.phase_state(phase), "a completed covering reviewed integration")
        late = b.work(phase, "Late")
        b.complete(late)  # every legacy check holds; the old integration no longer covers the plan
        legacy_phase = b.phase()
        legacy_work, stray = b.work(legacy_phase, "W"), b.work(legacy_phase, "NoEdge")
        legacy_integration = b.integration(legacy_phase, marker=None)
        b.requires(legacy_work, legacy_integration)
        b.complete(legacy_work, legacy_integration, stray)  # legacy allows a Work without the integration edge
        open_phase, normal, _, _ = reviewed_phase(b, complete=False)
        b.complete(normal[0])
        view = b.view()
        completion = view.phase_completion(phase)
        self.assertFalse(completion.complete)
        self.assertEqual(pi.completion_reasons(view, phase), completion.reasons)
        self.assertEqual(1, len(completion.reasons))
        self.assertIn("coverage stale; reintegration required", completion.reasons[0])
        self.assertEqual(IN_PROGRESS, view.phase_state(phase))
        self.assertIn(phase, [found.id for found in view.startable_phases(b.roadmap_id)])
        self.assertFalse(view.all_active_phases_complete(b.roadmap_id))
        self.assertEqual((True, ()), (view.phase_completion(legacy_phase).complete,
                                      view.phase_completion(legacy_phase).reasons))
        self.assertEqual(COMPLETE, view.phase_state(legacy_phase))
        open_reasons = view.phase_completion(open_phase).reasons
        self.assertTrue(open_reasons)
        self.assertFalse([reason for reason in open_reasons if "coverage" in reason],
                         "an incomplete Phase reports its legacy reasons only")
        for phase_id in view.phases:
            with self.subTest(phase=phase_id):
                self.assertEqual(pi.phase_generated_complete(view, phase_id), view.phase_state(phase_id) == COMPLETE)

    def test_marker_validity_is_reported_by_structural_validation(self) -> None:
        """validate.py (I-2, R04; §32.2): the marker only on a phase_integration_check, exactly the supported value -
        decided by key presence, never truthiness; reported as ``work_invalid``, never repaired."""
        def problems(kind, *values) -> tuple[str, list[tuple[str, str]]]:
            b = ViewBuilder()
            work = b.work(b.phase(), kind=kind)
            if values:
                b.works[work].meta[pi.PHASE_REVIEW_CONTRACT_KEY] = values[0]
            return work, [(p.code, p.message) for p in validate_structure(b.view())]

        for kind in (None, INTEGRATION, CONFIRMATION):
            with self.subTest(kind=kind, marker="absent"):
                self.assertEqual([], problems(kind)[1])
        self.assertEqual([], problems(INTEGRATION, V1)[1])
        for value in ("phase-integration-review-v2", "", None, [V1], V1.upper(), 1):
            with self.subTest(value=value):
                work, found = problems(INTEGRATION, value)
                self.assertEqual([("work_invalid", f"{work}: unsupported phase_review_contract {value!r}")], found)
        for kind in (None, CONFIRMATION):
            with self.subTest(kind=kind):
                work, found = problems(kind, V1)
                self.assertEqual([("work_invalid", f"{work}: phase_review_contract on non phase_integration_check Work")],
                                 found)
        work, found = problems(None, "")
        self.assertEqual([("work_invalid", f"{work}: phase_review_contract on non phase_integration_check Work"),
                          ("work_invalid", f"{work}: unsupported phase_review_contract ''")], found)

    def test_the_module_runs_on_a_loaded_project_without_doubles(self) -> None:
        """RB5A-03 (I-2, R03): the pure module on ``ProjectView.load`` of a real Project with a marked and an unmarked
        integration - plain store Entities, the raw stored marker, no test double."""
        store = self.new_project()
        roadmap = self.simple_roadmap(store, {"a": ("Phase A", "A holds"), "b": ("Phase B", "B holds")})
        legacy_phase, marked_phase = roadmap.phase_ids["a"], roadmap.phase_ids["b"]
        self.simple_entry(store, legacy_phase)  # the legacy Phase entry registers an unmarked integration
        with project_operation(store, "rb5-loaded-project-test"):
            mutation = MutationController(store).open(
                "roadmap", {"operation": "phase-entry", "phase_id": marked_phase}, WriteScope(entities=(marked_phase,))
            )
            specs = {"w1": WorkSpec("W1", "done", phase_id=marked_phase, roadmap_id=roadmap.roadmap_id),
                     "integration": WorkSpec("Integration", "integrated", phase_id=marked_phase,
                                             roadmap_id=roadmap.roadmap_id, work_kind=INTEGRATION,
                                             phase_review_contract=V1)}
            work_ids = register_works(mutation, "entry", specs,
                                      [RelationSpec("requires_completion", "w1", "integration")]).work_ids
        view = ProjectView.load(store)
        self.assertEqual({Entity}, {type(work) for work in view.works.values()})
        self.assertEqual(pi.MODE_LEGACY, pi.completion_mode(view, legacy_phase))
        self.assertEqual(pi.MODE_REVIEWED, pi.completion_mode(view, marked_phase))
        self.assertEqual(pi.COVERAGE_NOT_APPLICABLE, pi.coverage_status(view, legacy_phase).status)
        status = pi.coverage_status(view, marked_phase)
        self.assertEqual((pi.COVERAGE_MISSING, (work_ids["integration"],)),
                         (status.status, status.unfinished_reviewed_integration_ids))
        self.assertEqual(pi.PRE_INTEGRATION,
                         pi.classify_coverage(view, marked_phase, work_ids["integration"])[work_ids["w1"]])
        facts = {fact["work_id"]: fact for fact in pi.effective_work_facts(view, marked_phase)}
        self.assertEqual((V1, None), (facts[work_ids["integration"]][pi.PHASE_REVIEW_CONTRACT_KEY],
                                      facts[work_ids["w1"]][pi.PHASE_REVIEW_CONTRACT_KEY]))
        self.assertEqual({None},
                         {fact[pi.PHASE_REVIEW_CONTRACT_KEY] for fact in pi.effective_work_facts(view, legacy_phase)})
        self.assertEqual([], validate_project(store))

    def test_owners_refuse_an_edge_onto_a_completed_reviewed_integration(self) -> None:
        """RB5A-02 / R06 (ruling CPQ-01, deny-only), every owner seam on one real Project.

        Structural validation reports such an edge and repairs nothing; CREATE refuses it before its stage is
        recorded; the replan owners - Roadmap's plan exclusion and START's cancel, both deciding through
        ``ops.plan_replan`` - refuse it before any ID is reserved or any decision recorded, with the same code. A
        START derivation registers through CREATE (its Derive outcome wires only the unfinished integration, never a
        completed one). The same edges onto a completed legacy integration keep exactly their old result.
        """
        store = self.new_project()
        roadmap = self.simple_roadmap(store, {"a": ("Phase A", "A holds"), "b": ("Phase B", "B holds")})
        a, b, rid = roadmap.phase_ids["a"], roadmap.phase_ids["b"], roadmap.roadmap_id
        dep = "requires_completion"
        with project_operation(store, "rb5-owner-seams-fixture"):
            mutation = MutationController(store).open(
                "roadmap", {"operation": "phase-entry", "phase_id": a}, WriteScope(entities=(a, b))
            )
            ids = register_works(mutation, "entry", {
                "w1": WorkSpec("W1", "done", phase_id=a, roadmap_id=rid),
                "x": WorkSpec("X", "done", phase_id=a, roadmap_id=rid),
                "y": WorkSpec("Y", "done", phase_id=a, roadmap_id=rid),
                "integration": WorkSpec("Integration", "integrated", phase_id=a, roadmap_id=rid, work_kind=INTEGRATION,
                                        phase_review_contract=V1),
                "confirmation": WorkSpec("Confirmation", "confirmed", phase_id=a, roadmap_id=rid,
                                         work_kind=CONFIRMATION, confirmation_target="integration"),
                "w2": WorkSpec("W2", "done", phase_id=b, roadmap_id=rid),
                "z": WorkSpec("Z", "done", phase_id=b, roadmap_id=rid),
                "legacy": WorkSpec("Legacy integration", "integrated", phase_id=b, roadmap_id=rid,
                                   work_kind=INTEGRATION),
                "legacy_confirmation": WorkSpec("Legacy confirmation", "confirmed", phase_id=b, roadmap_id=rid,
                                                work_kind=CONFIRMATION, confirmation_target="legacy"),
            }, [RelationSpec(dep, "w1", "integration"), RelationSpec(dep, "integration", "confirmation"),
                RelationSpec(dep, "w2", "legacy"), RelationSpec(dep, "legacy", "legacy_confirmation")]).work_ids
            mutation.add_effects("lifecycle", [
                Effect.append_event(Event(mutation.reserve_id(f"evt:{key}:{kind}", "event"), kind, ids[key],
                                          "2026-10-07T00:00:00Z"))
                for key in ("w1", "integration", "w2", "legacy") for kind in ("work_started", "work_completed")
            ])
            mutation.apply()
            mutation.complete()
        git(store.root, "add", "-A")
        git(store.root, "commit", "-q", "-m", "fixture: a completed reviewed and a completed legacy integration")
        integration, legacy = ids["integration"], ids["legacy"]
        late_edge = RelationSpec(dep, ids["w2"], integration)  # w2 completed after the integration

        def relations() -> list[tuple[str, str]]:
            return sorted((r.from_id, r.to) for r in ProjectView.load(store).roadmap_relations if r.type == dep)

        before = relations()
        self.assertEqual([], validate_project(store))
        # validate: such an edge, written past the owners, is reported and left as it is
        view = ProjectView.load(store)
        manual = replace(view, roadmap_relations=view.roadmap_relations + [Relation(ident("rel", 990), dep, ids["y"],
                                                                                    integration)])
        self.assertEqual(["integration_coverage_order"], [p.code for p in validate_structure(manual)])
        # Roadmap's plan exclusion: refused before anything is reserved or recorded
        for described, replan in {
            "an existing Work completed after it": Replan(add_relations=(late_edge,)),
            "a new Work of the replan": Replan(new_works={"late": WorkSpec("Late", "done", phase_id=a, roadmap_id=rid)},
                                               add_relations=(RelationSpec(dep, "late", integration),)),
        }.items():
            with self.subTest(owner="roadmap plan exclusion", case=described):
                with self.assertRaises(ValidationError) as raised:
                    rm.plan_exclude_work(store, ids["x"], replan)
                self.assertEqual(INTEGRATION_COVERAGE_ORDER, raised.exception.code)
                self.assertEqual([], MutationController(store).list_pending(), "nothing recorded")
                self.assertEqual("unstarted", ProjectView.load(store).work_state(ids["x"]).state)
                self.assertEqual(before, relations())
        # legacy unchanged: the same late edge onto the completed unmarked integration is a plan exclusion as before
        legacy_edge = RelationSpec(dep, ids["y"], legacy)
        excluded = rm.plan_exclude_work(store, ids["z"], Replan(add_relations=(legacy_edge,)))
        self.assertEqual(("plan_excluded", ids["z"]), (excluded.status, excluded.entity_id))
        self.assertEqual("plan_excluded", ProjectView.load(store).work_state(ids["z"]).state)
        self.assertIn((ids["y"], legacy), relations())
        # START's cancel: the executor's replan is refused before the cancel is recorded
        log: list[str] = []

        def cancelling(ctx) -> object:
            log.append(ctx.work.id)
            return st.Cancel(Replan(add_relations=(late_edge,)), "superseded")

        with self.assertRaises(ValidationError) as raised:
            st.start(store, ids["y"], "single-work", cancelling)
        self.assertEqual(INTEGRATION_COVERAGE_ORDER, raised.exception.code)
        self.assertEqual([ids["y"]], log)
        self.assertNotEqual("cancelled", ProjectView.load(store).work_state(ids["y"]).state)
        self.assertNotIn((ids["w2"], integration), relations())
        # CREATE: refused before its stage is recorded (the START derivation registers through it)
        with project_operation(store, "rb5-owner-seams-create"):
            create = MutationController(store).open(
                "roadmap", {"operation": "phase-entry", "phase_id": a, "seam": "create"}, WriteScope(entities=(a,))
            )
            with self.assertRaises(ValidationError) as raised:
                register_works(create, "late", {"late": WorkSpec("Late", "done", phase_id=a, roadmap_id=rid)},
                               [RelationSpec(dep, "late", integration)])
            self.assertEqual(INTEGRATION_COVERAGE_ORDER, raised.exception.code)
            self.assertFalse(create.has_stage("late"))
        self.assertEqual([ids["w1"]], [source for source, to in relations() if to == integration])


class StructuralWiringTests(WorklineTestCase):
    """The I-2 halves of row R06 (ruling CPQ-01, deny-only): structural validation reports, CREATE refuses.

    The Roadmap / START replan relation paths are I-6; the deferred four-seam test above is enabled there.
    """

    def test_structural_validation_reports_a_laundering_edge_and_repairs_nothing(self) -> None:
        b = ViewBuilder()
        phase, _, integration, _ = reviewed_phase(b)
        self.assertEqual([], validate_structure(b.view()))
        late = b.work(phase, "Late")
        b.complete(late)
        b.requires(late, integration)  # the manual relation: the late Work completed after the integration
        view = b.view()
        self.assertEqual(
            [("integration_coverage_order", f"requires_completion {late} -> {integration}: {late} did not complete "
                                            f"before the completed {V1} integration {integration}")],
            [(p.code, p.message) for p in validate_structure(view)],
        )
        self.assertEqual([(late, integration)],
                         [(r.from_id, r.to) for r in view.roadmap_relations if r.from_id == late], "nothing repaired")
        legacy = ViewBuilder()
        legacy_phase = legacy.phase()
        legacy_work, legacy_integration = legacy.work(legacy_phase), legacy.integration(legacy_phase, marker=None)
        legacy.requires(legacy_work, legacy_integration)
        legacy.complete(legacy_work, legacy_integration)
        legacy_late = legacy.work(legacy_phase, "Late")
        legacy.complete(legacy_late)
        legacy.requires(legacy_late, legacy_integration)
        self.assertEqual([], validate_structure(legacy.view()), "an edge onto a legacy integration is not reported")
        # RB5I-2: one code, defined once, at both seams
        self.assertIs(pi.CODE_COVERAGE_ORDER, INTEGRATION_COVERAGE_ORDER)
        self.assertEqual(pi.CODE_COVERAGE_ORDER, validate_structure(view)[0].code)

    def test_the_report_has_the_owners_scope_and_changes_no_coverage(self) -> None:
        """RB5I-3 (CPQ-01: the same predicate at the owner-side refusal and in structural validation; §14.9
        "validation reports it"): an edge written by hand onto a completed reviewed integration from a Work of another
        Phase, from an excluded Work or from another integration, none of which completed before it, is reported -
        exactly the edges the owners refuse - and no coverage changes with it. Onto a legacy integration nothing is."""
        def build(marker):
            b = ViewBuilder()
            phase = b.phase()
            normal = b.work(phase, "W")
            integration = b.integration(phase, marker=marker)
            b.requires(normal, integration)
            b.complete(normal, integration)
            other = b.phase()
            foreign = b.work(other, "Foreign")
            b.complete(foreign)  # completed after the integration
            dropped = b.work(phase, "Dropped")
            b.exclude(dropped)  # never completes
            historical = b.integration(phase, marker=None, name="Later integration")
            b.requires(normal, historical)
            b.complete(historical)  # completed after the integration
            return b, phase, integration, {"another Phase's Work": foreign, "an excluded Work": dropped,
                                           "another integration": historical}

        for described in ("another Phase's Work", "an excluded Work", "another integration"):
            with self.subTest(source=described):
                b, phase, integration, sources = build(V1)
                before = b.view()
                coverage = (pi.classify_coverage(before, phase, integration), pi.covering_integration_ids(before, phase),
                            pi.coverage_status(before, phase))
                self.assertEqual([], [p for p in validate_structure(before) if p.code == pi.CODE_COVERAGE_ORDER])
                b.requires(sources[described], integration)
                after = b.view()
                self.assertEqual(
                    [f"requires_completion {sources[described]} -> {integration}: {sources[described]} did not complete "
                     f"before the completed {V1} integration {integration}"],
                    [p.message for p in validate_structure(after) if p.code == pi.CODE_COVERAGE_ORDER])
                self.assertEqual(1, len(pi.completed_integration_edge_problems(
                    before, [("requires_completion", sources[described], integration)])), "the owners refuse it too")
                self.assertEqual(coverage, (pi.classify_coverage(after, phase, integration),
                                            pi.covering_integration_ids(after, phase), pi.coverage_status(after, phase)))
                b, phase, legacy, sources = build(None)
                b.requires(sources[described], legacy)
                self.assertEqual([], [p for p in validate_structure(b.view()) if p.code == pi.CODE_COVERAGE_ORDER],
                                 "legacy: nothing reported")

    def test_create_refuses_an_edge_onto_a_completed_reviewed_integration_before_recording(self) -> None:
        store = self.new_project()
        roadmap = self.simple_roadmap(store, {"a": ("Phase A", "A holds"), "b": ("Phase B", "B holds")})
        a, b, rid = roadmap.phase_ids["a"], roadmap.phase_ids["b"], roadmap.roadmap_id
        dep = "requires_completion"
        with project_operation(store, "rb5-create-edge-test"):
            mutation = MutationController(store).open(
                "roadmap", {"operation": "phase-entry", "phase_id": a}, WriteScope(entities=(a, b))
            )
            ids = register_works(mutation, "entry", {
                "w1": WorkSpec("W1", "done", phase_id=a, roadmap_id=rid),
                "integration": WorkSpec("Integration", "integrated", phase_id=a, roadmap_id=rid, work_kind=INTEGRATION,
                                        phase_review_contract=V1),
                "confirmation": WorkSpec("Confirmation", "confirmed", phase_id=a, roadmap_id=rid,
                                         work_kind=CONFIRMATION, confirmation_target="integration"),
                "w2": WorkSpec("W2", "done", phase_id=b, roadmap_id=rid),
                "legacy": WorkSpec("Legacy integration", "integrated", phase_id=b, roadmap_id=rid,
                                   work_kind=INTEGRATION),
                "legacy_confirmation": WorkSpec("Legacy confirmation", "confirmed", phase_id=b, roadmap_id=rid,
                                                work_kind=CONFIRMATION, confirmation_target="legacy"),
            }, [RelationSpec(dep, "w1", "integration"), RelationSpec(dep, "integration", "confirmation"),
                RelationSpec(dep, "w2", "legacy"), RelationSpec(dep, "legacy", "legacy_confirmation")]).work_ids
            lifecycle = [
                Event(mutation.reserve_id(f"evt:{key}:{kind}", "event"), kind, ids[key], "2026-10-07T00:00:00Z")
                for key in ("w2", "w1", "integration", "legacy") for kind in ("work_started", "work_completed")
            ]
            mutation.add_effects("lifecycle", [Effect.append_event(event) for event in lifecycle])
            mutation.apply()
            view = ProjectView.load(store)
            self.assertEqual(COMPLETED, view.work_state(ids["integration"]).state)
            self.assertNotEqual(COMPLETE, view.phase_state(a), "its confirmation is still open, so late Work may join")
            works_before = sorted(view.works)
            refused = {
                "a new Work of the Phase": ("late_a", WorkSpec("Late", "done", phase_id=a, roadmap_id=rid)),
                "a new Work of another Phase": ("late_b", WorkSpec("Late B", "done", phase_id=b, roadmap_id=rid)),
            }
            for described, (key, spec) in refused.items():
                with self.subTest(case=described):
                    with self.assertRaises(ValidationError) as raised:
                        register_works(mutation, f"stage-{key}", {key: spec}, [RelationSpec(dep, key, ids["integration"])])
                    self.assertEqual(INTEGRATION_COVERAGE_ORDER, raised.exception.code)
                    self.assertIn(f"-> {ids['integration']}: {ids['integration']} is a completed {V1} integration",
                                  str(raised.exception))
                    self.assertFalse(mutation.has_stage(f"stage-{key}"), "refused before the stage is recorded")
                    self.assertEqual(works_before, sorted(ProjectView.load(store).works), "nothing written")
            # deny-only: a Work that completed before the integration may still point at it
            allowed = register_works(mutation, "stage-earlier",
                                     {"extra": WorkSpec("Extra", "done", phase_id=b, roadmap_id=rid)},
                                     [RelationSpec(dep, ids["w2"], ids["integration"])])
            self.assertIn(allowed.work_ids["extra"], ProjectView.load(store).works)
            # legacy unchanged: the same late edge onto a completed unmarked integration registers as it always did
            legacy_late = register_works(mutation, "stage-legacy",
                                         {"late": WorkSpec("Late legacy", "done", phase_id=b, roadmap_id=rid)},
                                         [RelationSpec(dep, "late", ids["legacy"])])
            self.assertIn(legacy_late.work_ids["late"], ProjectView.load(store).works)
        self.assertEqual([], validate_project(store))


if __name__ == "__main__":
    unittest.main()
