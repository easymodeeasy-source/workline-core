"""Sprint 41.31 (the RB11 contract amendment), checks of the units that the integration made precise.

AM-E (the cycle over Phase relations and Work dependencies together), AM-D / AM-E (the reviewed route), AM-F (entry
without a design), AM-H1 (who may carry a registration_key), AM-H2 (the Phase prerequisite gate lives in one predicate
and only holds an unstarted Work), AM-K (independent_candidates is read-only) and the literal-path rule that replaces
the deliverable-pattern unit (every deliverable is an exact path; ``glob:`` and ``*`` carry no meaning).
"""

from __future__ import annotations

import dataclasses
import inspect
from unittest import mock

from helpers import WorklineTestCase, completing_executor, scripted_executor
from test_roadmap_registered_works import design, plan
from workline import roadmap as rm
from workline import start as st
from workline.create import RelatedSpec, WorkSpec, create_standalone_work
from workline.errors import StopError, ValidationError
from workline.ops import Replan
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.state import ProjectView


class CycleTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def test_a_cycle_through_a_phase_relation_and_a_work_dependency_is_refused_before_writing(self) -> None:
        # Phase b requires a (relation a -> b) while a's Work a1 waits for b's Work b1: neither Phase could ever start.
        cyclic = dataclasses.replace(
            plan((("requires_completion", "a", "b"),)), work_dependencies=(rm.WorkDependency("b", "b1", "a", "a1"),)
        )
        with self.assertRaises(ValidationError) as raised:
            rm.create_roadmap(self.store, cyclic)
        self.assertIn("cycle", str(raised.exception))
        self.assertEqual(ProjectView.load(self.store).roadmaps, {})
        self.assertEqual([], list(self.store.mutations.glob("*.yaml")) if self.store.mutations.is_dir() else [])

    def test_a_phase_relation_cycle_of_a_plan_that_registers_works_is_refused_before_writing(self) -> None:
        cyclic = plan((("requires_completion", "a", "b"), ("requires_completion", "b", "a")))
        with self.assertRaises(ValidationError) as raised:
            rm.create_roadmap(self.store, cyclic)
        self.assertIn("cycle", str(raised.exception))
        self.assertEqual(ProjectView.load(self.store).roadmaps, {})

    def test_a_legacy_plan_with_a_phase_relation_cycle_keeps_the_refusal_it_always_had(self) -> None:
        legacy = plan((("requires_completion", "a", "b"), ("requires_completion", "b", "a")), entries={})
        with self.assertRaises(Exception) as raised:
            rm.create_roadmap(self.store, legacy)
        self.assertEqual("postcheck_failed", getattr(raised.exception, "code", None), raised.exception)
        self.assertEqual(ProjectView.load(self.store).roadmaps, {})

    def test_the_acyclic_control_is_accepted_and_registers_in_dependency_order(self) -> None:
        acyclic = dataclasses.replace(
            plan((("requires_completion", "a", "b"),)), work_dependencies=(rm.WorkDependency("a", "a1", "b", "b1"),)
        )
        result = rm.create_roadmap(self.store, acyclic)
        self.assertEqual({"a", "b", "c"}, set(result.work_ids))

    def test_work_dependencies_without_phase_entries_are_refused(self) -> None:
        bare = dataclasses.replace(plan(entries={}), work_dependencies=(rm.WorkDependency("a", "a1", "b", "b1"),))
        with self.assertRaises(ValidationError):
            rm.create_roadmap(self.store, bare)
        self.assertEqual(ProjectView.load(self.store).roadmaps, {})

    def test_the_reviewed_route_refuses_work_dependencies_as_it_refuses_phase_entries(self) -> None:
        bare = dataclasses.replace(plan(entries={}), work_dependencies=(rm.WorkDependency("a", "a1", "b", "b1"),))
        with mock.patch("workline.roadmap_review.require_entry_gate"):
            with self.assertRaises(ValidationError) as raised:
                rm.create_roadmap(self.store, bare, review=object())
        self.assertIn("work_dependencies", str(raised.exception))
        self.assertEqual(ProjectView.load(self.store).roadmaps, {})


class EntryWithoutDesignTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def test_it_is_refused_with_a_planning_review(self) -> None:
        result = rm.create_roadmap(self.store, plan())
        with self.assertRaises(ValidationError):
            rm.enter_phase(self.store, result.phase_ids["a"], review=object())

    def test_it_is_refused_for_a_phase_whose_works_roadmap_time_registration_did_not_write(self) -> None:
        legacy = self.simple_roadmap(self.store, {"a": ("Phase A", "A が成立する")})
        phase_id = legacy.phase_ids["a"]
        self.simple_entry(self.store, phase_id)
        with self.assertRaises(ValidationError) as raised:
            rm.enter_phase(self.store, phase_id)
        self.assertIn("Roadmap-time registration", str(raised.exception))


class RegistrationKeyTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def test_registration_key_is_keyword_only_and_the_positional_shape_is_unchanged(self) -> None:
        parameters = inspect.signature(WorkSpec).parameters
        self.assertEqual(inspect.Parameter.KEYWORD_ONLY, parameters["registration_key"].kind)
        positional = [name for name, p in parameters.items() if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD]
        self.assertEqual("phase_review_contract", positional[-1])
        self.assertEqual(9, len(positional))

    def test_direct_create_refuses_a_registration_key(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            create_standalone_work(self.store, WorkSpec("A", "a", registration_key="k"))
        self.assertIn("Roadmap-time registration", str(raised.exception))
        self.assertEqual({}, ProjectView.load(self.store).works)

    def test_a_specification_from_any_other_path_cannot_carry_the_marker(self) -> None:
        """A replan (or any caller) hands plain Work specifications to the registration core; the core refuses a
        registration_key that Roadmap-time registration did not stamp, before anything is written."""
        from workline.create import validate_work_specs

        result = rm.create_roadmap(self.store, plan())
        view = ProjectView.load(self.store)
        forged = WorkSpec(
            "Forged", "forged", phase_id=result.phase_ids["a"], roadmap_id=result.roadmap_id, registration_key="a1"
        )
        with self.assertRaises(ValidationError) as raised:
            validate_work_specs({"forged": forged}, view)
        self.assertIn("Roadmap-time registration", str(raised.exception))
        plain = dataclasses.replace(forged, registration_key=None)
        validate_work_specs({"plain": plain}, view)  # the same spec without the key is an ordinary valid spec
        self.assertEqual(
            {w.id: w.roadmap_registration for w in view.works.values() if w.roadmap_registration is None}.keys(),
            {w.id for w in view.works.values() if w.roadmap_registration is None},
        )


class PhaseGateTests(WorklineTestCase):
    """AM-H2: one predicate, and only for a Work that has not started."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def test_a_started_work_is_not_held_by_a_prerequisite_added_later_but_an_unstarted_one_is(self) -> None:
        from status_helpers import append_events

        result = rm.create_roadmap(
            self.store,
            dataclasses.replace(plan(entries={}), phase_entries={"a": design("a1", "a2"), "b": design("b1"), "c": design("c1")}),
        )
        a1, a2 = result.work_ids["a"]["a1"], result.work_ids["a"]["a2"]
        rm.add_phases(
            self.store, result.roadmap_id, {"z": PhaseSpec("Phase Z", "Z が成立する")},
            (PhaseRelationSpec("requires_completion", "z", result.phase_ids["a"]),),
        )
        view = ProjectView.load(self.store)
        self.assertTrue(view.unsatisfied_dependencies(result.phase_ids["a"]), "the added prerequisite is real")
        self.assertTrue(view.unsatisfied_dependencies(a1), "before it starts a marked Work is held")
        append_events(self.store, ("work_started", a1))  # a1 has started (a fixture, not an operation)
        view = ProjectView.load(self.store)
        self.assertEqual("in_progress", view.work_state(a1).state)
        self.assertEqual([], view.unsatisfied_dependencies(a1), "a started Work is not held, so its completion is not refused")
        self.assertTrue(view.unsatisfied_dependencies(a2), "an unstarted marked Work still is")
        self.assertNotIn(a2, [w.id for w in view.startable_works(result.phase_ids["a"])])
        self.assertEqual([], view.unsatisfied_dependencies(a1, include_phase=False))


class IndependentCandidatesTests(WorklineTestCase):
    def test_it_changes_nothing(self) -> None:
        store = self.new_project()
        result = rm.create_roadmap(store, plan((("requires_completion", "a", "b"),)))
        rm.hold_phase(store, result.phase_ids["c"])
        before = {path.relative_to(store.root).as_posix(): path.read_bytes() for path in (store.root / ".workline").rglob("*") if path.is_file()}
        candidates = rm.independent_candidates(store, result.roadmap_id)
        after = {path.relative_to(store.root).as_posix(): path.read_bytes() for path in (store.root / ".workline").rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual([], list(store.mutations.glob("*.yaml")) if store.mutations.is_dir() else [])
        self.assertNotIn(result.phase_ids["c"], candidates.works, "a held Phase is not listed")
        self.assertIn(result.phase_ids["b"], candidates.blocked)


class LiteralDeliverablePathTests(WorklineTestCase):
    """Human decision 2026-10-21 (AM-G not adopted): every deliverable is an exact path on every route."""

    def literal_target_is_not_satisfied(self, target: str) -> None:
        store = self.new_project()
        work_id = create_standalone_work(
            store, WorkSpec("Doc", "doc", related=(RelatedSpec("must_update", target),))
        ).work_id
        with self.assertRaises(StopError) as raised:
            st.start(store, work_id, "single-work", completing_executor(store))
        self.assertIn(f"must_update not satisfied: {target}", str(raised.exception))

    def test_a_glob_prefix_is_a_literal_path(self) -> None:
        self.literal_target_is_not_satisfied("glob:docs/*.md")

    def test_a_star_is_a_literal_path(self) -> None:
        self.literal_target_is_not_satisfied("docs/*.md")

    def test_a_question_mark_is_a_literal_path(self) -> None:
        self.literal_target_is_not_satisfied("docs/?.md")
