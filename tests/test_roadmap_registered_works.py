"""Roadmap-time Work registration and the execution gate it needs (WL-YGO-08, WL-YGO-07).

A Roadmap may register the Works of its Phases at creation. Registered is not startable: a Work of a Phase whose
``requires_completion`` predecessors are unfinished must not start, Phase entry registers nothing again, and a
Roadmap made without ``phase_entries`` behaves as it always did.
"""

from __future__ import annotations

import dataclasses
from unittest import mock

from helpers import WorklineTestCase, completing_executor
from workline import roadmap as rm
from workline import start as st
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.state import ProjectView
from workline.validate import validate_project


def design(*keys: str) -> rm.PhaseEntryDesign:
    return rm.PhaseEntryDesign(
        {key: rm.WorkDesign(key.upper(), f"{key} が成立する") for key in keys},
        rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
    )


def plan(relations=(), entries=None) -> rm.RoadmapPlan:
    phases = {key: PhaseSpec(f"Phase {key}", f"{key} が成立する") for key in ("a", "b", "c")}
    return rm.RoadmapPlan(
        "Test Roadmap", "背景", "達成したい状態", phases,
        tuple(PhaseRelationSpec(t, x, y) for t, x, y in relations),
        phase_entries={"a": design("a1"), "b": design("b1"), "c": design("c1")} if entries is None else entries,
    )


class Interrupted(RuntimeError):
    pass


class RegisteredWorksTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def create(self, relations=(("requires_completion", "a", "b"),)):
        return rm.create_roadmap(self.store, plan(relations))

    def test_creation_registers_every_work_unstarted_and_nothing_completes(self) -> None:
        result = self.create()
        view = ProjectView.load(self.store)
        self.assertEqual(set(result.work_ids), {"a", "b", "c"})
        self.assertEqual(len(view.works), 6)  # one normal Work + one integration per Phase
        for phase_id in result.phase_ids.values():
            self.assertEqual(view.phase_state(phase_id), "unstarted")
        self.assertFalse(view.all_active_phases_complete(result.roadmap_id))
        self.assertEqual(validate_project(self.store), [])

    def test_work_of_a_blocked_phase_is_not_startable_and_does_not_start(self) -> None:
        result = self.create()
        phase_b = result.phase_ids["b"]
        work_b = result.work_ids["b"]["b1"]
        view = ProjectView.load(self.store)
        self.assertEqual(view.startable_works(phase_b), [])
        with self.assertRaises(StopError) as raised:
            st.start(self.store, work_b, "single-work", completing_executor(self.store))
        self.assertEqual(raised.exception.code, "dependency_unsatisfied")
        self.assertEqual(ProjectView.load(self.store).work_state(work_b).state, "unstarted")

    def test_phase_entry_hands_over_without_registering_again(self) -> None:
        result = self.create()
        phase_b = result.phase_ids["b"]
        with self.assertRaises(StopError) as raised:
            rm.enter_phase(self.store, phase_b)
        self.assertEqual(raised.exception.code, "phase_blocked")
        # complete A through its registered Works
        entry_a = rm.enter_phase(self.store, result.phase_ids["a"])
        self.assertFalse(entry_a.expanded)
        self.assertEqual(entry_a.entry_work_id, result.work_ids["a"]["a1"])
        self.assertEqual(st.start(self.store, entry_a.entry_work_id, "outer", completing_executor(self.store)).status,
                         "phase_complete")
        before = len(ProjectView.load(self.store).works)
        entry_b = rm.enter_phase(self.store, phase_b)
        self.assertFalse(entry_b.expanded)
        self.assertEqual(entry_b.entry_work_id, result.work_ids["b"]["b1"])
        self.assertEqual(len(ProjectView.load(self.store).works), before)
        # a design for a Phase that already holds Works is still refused
        with self.assertRaises(StopError) as raised:
            rm.enter_phase(self.store, phase_b, design("x"))
        self.assertEqual(raised.exception.code, "phase_already_expanded")
        self.assertEqual(
            st.start(self.store, entry_b.entry_work_id, "outer", completing_executor(self.store)).status,
            "phase_complete",
        )

    def test_entry_without_design_needs_registered_works(self) -> None:
        legacy = self.simple_roadmap(self.store, {"a": ("Phase A", "A が成立する")})
        with self.assertRaises(ValidationError):
            rm.enter_phase(self.store, legacy.phase_ids["a"])

    def test_independent_phase_proceeds_while_another_is_stopped(self) -> None:
        result = self.create((("requires_completion", "a", "b"), ("planned_next", "b", "c")))
        found = rm.independent_candidates(self.store, result.roadmap_id)
        # C is only planned after B, never required: it is startable now; B waits for A
        self.assertIn(result.phase_ids["c"], found.phases)
        self.assertIn(result.phase_ids["a"], found.phases)
        self.assertNotIn(result.phase_ids["b"], found.phases)
        self.assertIn(result.phase_ids["b"], found.blocked)
        self.assertNotIn(result.phase_ids["c"], found.works, "a startable Phase is listed once, in phases (AM-K: other Phases)")
        # and its registered Work really starts
        st.start(self.store, result.work_ids["c"]["c1"], "single-work", completing_executor(self.store))
        self.assertEqual(
            ProjectView.load(self.store).work_state(result.work_ids["c"]["c1"]).state, "completed"
        )

    def test_the_registration_result_is_the_derived_class_and_carries_work_ids(self) -> None:
        result = self.create()
        self.assertIs(type(result), rm.RegisteredRoadmapResult)
        self.assertIsInstance(result, rm.RoadmapResult)
        self.assertEqual(
            ["roadmap_id", "phase_ids", "mutation_id", "head", "resumed", "work_ids"], list(dataclasses.asdict(result))
        )
        self.assertEqual(set(result.work_ids), {"a", "b", "c"})

    def test_legacy_roadmap_is_unchanged(self) -> None:
        legacy = self.simple_roadmap(self.store, {"a": ("A", "a"), "b": ("B", "b")}, [("requires_completion", "a", "b")])
        # the legacy result keeps its baseline shape and serialization: no ``work_ids`` at all
        self.assertIs(type(legacy), rm.RoadmapResult)
        self.assertFalse(hasattr(legacy, "work_ids"))
        self.assertEqual(
            ["roadmap_id", "phase_ids", "mutation_id", "head", "resumed"], list(dataclasses.asdict(legacy))
        )
        self.assertEqual(ProjectView.load(self.store).works, {})
        entry = self.simple_entry(self.store, legacy.phase_ids["a"])
        self.assertTrue(entry.expanded)
        st.start(self.store, entry.entry_work_id, "outer", completing_executor(self.store))
        self.assertTrue(self.simple_entry(self.store, legacy.phase_ids["b"]).expanded)

    def test_interrupted_creation_resumes_as_the_same_plan(self) -> None:
        real = rm.register_works
        calls = {"n": 0}

        def fire(mutation, name, specs, relations=(), **kw):
            if name == "works@1":
                calls["n"] += 1
                if calls["n"] == 1:
                    raise Interrupted(name)
            return real(mutation, name, specs, relations, **kw)

        with mock.patch.object(rm, "register_works", fire):
            with self.assertRaises(Interrupted):
                self.create()
        # a different plan is not grafted onto the unfinished one
        other = plan((("requires_completion", "a", "b"),), {"a": design("zz"), "b": design("b1"), "c": design("c1")})
        with self.assertRaises(ReconcileRequired):
            rm.create_roadmap(self.store, other)
        result = self.create()
        self.assertTrue(result.resumed)
        view = ProjectView.load(self.store)
        self.assertEqual(len(view.works), 6)
        self.assertEqual(len(view.roadmaps), 1)
        self.assertEqual(validate_project(self.store), [])

    def test_unknown_phase_key_is_refused_before_writing(self) -> None:
        bad = plan(entries={"zzz": design("a1")})
        with self.assertRaises(ValidationError):
            rm.create_roadmap(self.store, bad)
        self.assertEqual(ProjectView.load(self.store).roadmaps, {})

    def test_planning_review_with_registered_works_is_not_silently_skipped(self) -> None:
        # RB11INT-EVID-3: the entry gate is stepped over so that the refusal under test is the one that is reached
        with mock.patch("workline.roadmap_review.require_entry_gate"):
            with self.assertRaises(ValidationError) as raised:
                rm.create_roadmap(self.store, plan(), review=object())
        self.assertIn("not yet available with a Planning Review", str(raised.exception))
        self.assertEqual(ProjectView.load(self.store).roadmaps, {})


class RegistrationProvenanceTests(WorklineTestCase):
    """RB11R-1 / RB11R-10: ownership of a Roadmap-time registered Work is persisted, never inferred."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def _work_file(self, work_id: str):
        return self.store.root / ".workline" / "works" / f"{work_id}.md"

    def _strip_marker(self, work_id: str) -> None:
        path = self._work_file(work_id)
        lines = path.read_bytes().decode("utf-8").split("\n")
        kept: list[str] = []
        skipping = False
        for line in lines:
            if line.startswith("roadmap_registration:"):
                skipping = True
                continue
            if skipping and line.startswith("  "):
                continue
            skipping = False
            kept.append(line)
        path.write_bytes("\n".join(kept).encode("utf-8"))

    def test_every_roadmap_time_work_carries_its_plan_key_and_survives_a_reload(self) -> None:
        result = rm.create_roadmap(self.store, plan((("requires_completion", "a", "b"),)))
        view = ProjectView.load(self.store)  # a fresh load: the marker comes from the files, not from memory
        for phase_key, keys in result.work_ids.items():
            for work_key, work_id in keys.items():
                marker = view.works[work_id].roadmap_registration
                self.assertEqual(
                    marker,
                    {"roadmap_id": result.roadmap_id, "phase_id": result.phase_ids[phase_key], "key": work_key},
                )
        integrations = [w for w in view.works.values() if w.work_kind == "phase_integration_check"]
        self.assertEqual(sorted(w.roadmap_registration["key"] for w in integrations), ["integration"] * 3)
        self.assertEqual(validate_project(self.store), [])

    def test_a_phase_entered_the_ordinary_way_keeps_its_frozen_behavior_after_a_prerequisite_is_added(self) -> None:
        legacy = self.simple_roadmap(self.store, {"a": ("Phase A", "A が成立する")})
        entry = rm.enter_phase(self.store, legacy.phase_ids["a"], design("a1"))
        work_id = entry.work_ids["a1"]
        self.assertIsNone(ProjectView.load(self.store).works[work_id].roadmap_registration)
        added = rm.add_phases(
            self.store, legacy.roadmap_id, {"z": PhaseSpec("Phase Z", "Z が成立する")},
            (PhaseRelationSpec("requires_completion", "z", legacy.phase_ids["a"]),),
        )
        view = ProjectView.load(self.store)
        self.assertTrue(view.unsatisfied_dependencies(legacy.phase_ids["a"]))  # the added prerequisite is real
        self.assertEqual(view.unsatisfied_dependencies(work_id), [])
        self.assertIn(work_id, [w.id for w in view.startable_works(legacy.phase_ids["a"])])
        self.assertEqual(
            st.start(self.store, work_id, "single-work", completing_executor(self.store)).status, "completed"
        )
        self.assertTrue(added.phase_ids)

    def test_a_roadmap_time_work_is_held_back_by_its_phase_prerequisites_until_they_complete(self) -> None:
        result = rm.create_roadmap(self.store, plan((("requires_completion", "a", "b"),)))
        work_b = result.work_ids["b"]["b1"]
        with self.assertRaises(StopError) as raised:
            st.start(self.store, work_b, "single-work", completing_executor(self.store))
        self.assertEqual(raised.exception.code, "dependency_unsatisfied")
        entry_a = rm.enter_phase(self.store, result.phase_ids["a"])
        self.assertEqual(
            st.start(self.store, entry_a.entry_work_id, "outer", completing_executor(self.store)).status,
            "phase_complete",
        )
        view = ProjectView.load(self.store)
        self.assertEqual(view.unsatisfied_dependencies(work_b), [])
        self.assertEqual(
            st.start(self.store, work_b, "single-work", completing_executor(self.store)).status, "completed"
        )

    def test_a_work_of_unknown_provenance_is_never_taken_for_a_roadmap_time_registration(self) -> None:
        result = rm.create_roadmap(self.store, plan((("requires_completion", "a", "b"),)))
        work_b = result.work_ids["b"]["b1"]
        self._strip_marker(work_b)
        view = ProjectView.load(self.store)
        self.assertIsNone(view.works[work_b].roadmap_registration)
        # no marker, no inherited Phase gate: the Work is read exactly as a legacy Work is
        self.assertEqual(view.unsatisfied_dependencies(work_b), [])

    def test_an_inconsistent_marker_reads_as_no_marker(self) -> None:
        result = rm.create_roadmap(self.store, plan((("requires_completion", "a", "b"),)))
        work_b = result.work_ids["b"]["b1"]
        path = self._work_file(work_b)
        text = path.read_bytes().decode("utf-8")
        wrong = text.replace(f"roadmap_registration:\n  roadmap_id: {result.roadmap_id}", "roadmap_registration:\n  roadmap_id: r_OTHER", 1)
        self.assertNotEqual(text, wrong)
        path.write_bytes(wrong.encode("utf-8"))
        self.assertIsNone(ProjectView.load(self.store).works[work_b].roadmap_registration)

    def test_phase_entry_reads_back_registered_works_without_counting_or_ordering_them(self) -> None:
        result = rm.create_roadmap(self.store, plan((("requires_completion", "a", "b"),)))
        # Works are keyed by their own markers; adding or removing a Work elsewhere changes nothing about ownership
        view = ProjectView.load(self.store)
        keys = {w.roadmap_registration["key"]: w.id for w in view.works.values() if w.roadmap_registration}
        self.assertEqual(keys["a1"], result.work_ids["a"]["a1"])
        self.assertEqual(keys["b1"], result.work_ids["b"]["b1"])
        self.assertEqual(keys["c1"], result.work_ids["c"]["c1"])

    def test_the_reviewed_registration_route_is_not_part_of_the_candidate(self) -> None:
        for name in ("create_roadmap_with_works", "register_roadmap_works", "ReviewedRoadmapWorks"):
            self.assertFalse(hasattr(rm, name), name)
        import inspect

        self.assertNotIn("register_only", inspect.signature(rm.enter_phase).parameters)
        with mock.patch("workline.roadmap_review.require_entry_gate"):
            with self.assertRaises(ValidationError) as raised:
                rm.create_roadmap(self.store, plan(), review=object())
        self.assertIn("not yet available with a Planning Review", str(raised.exception))

    def test_a_roadmap_without_phase_entries_writes_no_provenance_marker(self) -> None:
        legacy = self.simple_roadmap(self.store, {"a": ("Phase A", "A が成立する")})
        entry = rm.enter_phase(self.store, legacy.phase_ids["a"], design("a1"))
        for work in ProjectView.load(self.store).works.values():
            self.assertNotIn("roadmap_registration", work.meta)
        self.assertTrue(entry.expanded)
