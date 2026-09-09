from __future__ import annotations

import unittest

from helpers import WorklineTestCase, completing_executor, git
from workline import roadmap as rm
from workline import start as st
from workline.errors import SpecViolation, StopError, ValidationError
from workline.mutation import MutationController, WriteScope
from workline.ops import Replan
from workline.phase_create import PhaseRelationSpec, PhaseSpec, register_phases
from workline.state import ProjectView
from workline.store import ROADMAP_DESIRED_HEADING
from workline.validate import validate_project


class RoadmapTests(WorklineTestCase):
    def test_new_roadmap_registers_all_phases(self) -> None:
        store = self.new_project(remote=True)
        result = self.simple_roadmap(store, {"a": ("A", "a state"), "b": ("B", "b state")}, [("requires_completion", "a", "b"), ("planned_next", "a", "b")])
        view = ProjectView.load(store)
        roadmap = view.roadmaps[result.roadmap_id]
        self.assertEqual(roadmap.display, "R-01")
        self.assertEqual(roadmap.section(ROADMAP_DESIRED_HEADING), "テスト用の達成したい状態")
        for forbidden in ("state", "phases", "progress"):
            self.assertNotIn(forbidden, roadmap.meta)
        self.assertEqual({p.display for p in view.phases.values()}, {"P-01", "P-02"})
        self.assertTrue(all(p.roadmap_id == result.roadmap_id for p in view.phases.values()))
        self.assertEqual(view.works, {})
        self.assertEqual(view.events, [])
        self.assertEqual({(r.type, r.from_id, r.to) for r in view.roadmap_relations}, {
            ("requires_completion", result.phase_ids["a"], result.phase_ids["b"]),
            ("planned_next", result.phase_ids["a"], result.phase_ids["b"]),
        })
        self.assertEqual(git(store.root, "log", "-1", "--format=%s").strip(), "chore(workline): create roadmap R-01")
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), git(self.remote_path(), "rev-parse", "main").strip())
        self.assertEqual(validate_project(store), [])

    def test_phase_create_validates_and_refuses_meaning(self) -> None:
        store = self.new_project()
        result = self.simple_roadmap(store)
        controller = MutationController(store)
        mutation = controller.open("roadmap", {"operation": "test"}, WriteScope())
        with self.assertRaises(ValidationError):
            register_phases(mutation, "p1", "r_01ARZ3NDEKTSV4RRFFQ69G5FAV", {"x": PhaseSpec("X", "x")})
        with self.assertRaises(ValidationError):
            register_phases(mutation, "p2", result.roadmap_id, {"x": PhaseSpec("X", "")})
        with self.assertRaises(ValidationError):  # mixed Phase↔Work relation
            register_phases(mutation, "p3", result.roadmap_id, {"x": PhaseSpec("X", "x")}, [PhaseRelationSpec("planned_next", "x", "w_01ARZ3NDEKTSV4RRFFQ69G5FAV")])
        registered = register_phases(mutation, "p4", result.roadmap_id, {"x": PhaseSpec("X", "x")}, [PhaseRelationSpec("requires_completion", result.phase_ids["a"], "x")])
        again = register_phases(mutation, "p4", result.roadmap_id, {"x": PhaseSpec("X", "x")}, [PhaseRelationSpec("requires_completion", result.phase_ids["a"], "x")])
        self.assertEqual(registered.phase_ids, again.phase_ids)
        self.assertEqual(len(ProjectView.load(store).phases), 2)
        mutation.complete()
        rm.hold_roadmap(store, result.roadmap_id)
        mutation = controller.open("roadmap", {"operation": "test2"}, WriteScope())
        with self.assertRaises(SpecViolation):
            register_phases(mutation, "p5", result.roadmap_id, {"y": PhaseSpec("Y", "y")})
        register_phases(mutation, "p5", result.roadmap_id, {"y": PhaseSpec("Y", "y")}, future_plan_change=True)
        mutation.complete()

    def test_phase_dependency_and_selection(self) -> None:
        store = self.new_project()
        result = self.simple_roadmap(store, {"a": ("A", "a"), "b": ("B", "b"), "c": ("C", "c")},
                                     [("requires_completion", "a", "b"), ("planned_next", "a", "b"), ("planned_next", "b", "c")])
        a, b, c = result.phase_ids["a"], result.phase_ids["b"], result.phase_ids["c"]
        self.assertEqual([p.id for p in rm.startable_phases(store, result.roadmap_id)], sorted([a, c]))
        self.assertEqual(rm.select_phase(store, result.roadmap_id).id, a)
        with self.assertRaises(SpecViolation):
            rm.select_phase(store, result.roadmap_id, explicit=b)
        with self.assertRaises(StopError):
            self.simple_entry(store, b)
        entry = self.simple_entry(store, a)
        self.assertEqual(st.start(store, entry.entry_work_id, "outer", completing_executor(store)).status, "phase_complete")
        self.assertEqual([p.id for p in rm.startable_phases(store, result.roadmap_id)], sorted([b, c]))
        self.assertEqual(rm.select_phase(store, result.roadmap_id).id, b)  # planned_next from the completed Phase
        # selection does not enter the Phase; entry expands Works only once
        self.assertEqual(ProjectView.load(store).phase_works(b), [])
        first = self.simple_entry(store, b)
        second = self.simple_entry(store, b)
        self.assertTrue(first.expanded)
        self.assertFalse(second.expanded)
        self.assertEqual(second.entry_work_id, first.entry_work_id)
        self.assertEqual(len(ProjectView.load(store).phase_works(b)), 2)

    def test_phase_entry_structure(self) -> None:
        store = self.new_project()
        result = self.simple_roadmap(store)
        phase_id = result.phase_ids["a"]
        entry = self.simple_entry(store, phase_id, {"w1": "one", "w2": "two"}, confirmation=True, planned_next=(("w1", "w2"),), entry="w1")
        view = ProjectView.load(store)
        works = view.phase_works(phase_id)
        self.assertEqual(len(works), 4)
        integration = view.works[entry.integration_id]
        confirmation = view.works[entry.confirmation_id]
        self.assertEqual(confirmation.meta["confirmation_target"], integration.id)
        self.assertEqual(sorted(r.from_id for r in view.relations_to(integration.id, "requires_completion")), sorted(entry.work_ids.values()))
        self.assertEqual([r.from_id for r in view.relations_to(confirmation.id, "requires_completion")], [integration.id])
        self.assertEqual(entry.entry_work_id, entry.work_ids["w1"])
        self.assertEqual(view.events, [])
        self.assertTrue(all(view.work_state(w.id).state == "unstarted" for w in works))
        self.assertEqual(git(store.root, "log", "-1", "--format=%s").strip(), "chore(workline): expand phase P-01")
        self.assertEqual(validate_project(store), [])
        fresh = self.simple_roadmap(store, {"z": ("Z", "z")})
        with self.assertRaises(SpecViolation):
            self.simple_entry(store, fresh.phase_ids["z"], entry="does-not-exist")
        self.assertEqual(MutationController(store).list_pending(), [])

    def test_phase_completion_requires_integration(self) -> None:
        store = self.new_project()
        result = self.simple_roadmap(store)
        phase_id = result.phase_ids["a"]
        entry = self.simple_entry(store, phase_id, {"w1": "one"})
        st.start(store, entry.work_ids["w1"], "single-work", completing_executor(store))
        view = ProjectView.load(store)
        completion = view.phase_completion(phase_id)
        self.assertFalse(completion.complete)
        self.assertTrue(any("unfinished integration" in r for r in completion.reasons))
        st.start(store, entry.integration_id, "single-work", completing_executor(store))
        self.assertTrue(ProjectView.load(store).phase_completion(phase_id).complete)
        self.assertEqual(ProjectView.load(store).phase_state(phase_id), "complete")
        # no completion event is stored
        self.assertFalse(any(e.entity == phase_id for e in ProjectView.load(store).events))

    def test_lifecycle_events_do_not_propagate(self) -> None:
        store = self.new_project()
        result = self.simple_roadmap(store, {"a": ("A", "a"), "b": ("B", "b")})
        a, b = result.phase_ids["a"], result.phase_ids["b"]
        entry = self.simple_entry(store, a)
        rm.hold_phase(store, a)
        view = ProjectView.load(store)
        self.assertEqual(view.phase_state(a), "held")
        self.assertEqual(view.work_state(entry.work_ids["w1"]).state, "unstarted")
        self.assertEqual([p.id for p in rm.startable_phases(store, result.roadmap_id)], [b])
        with self.assertRaises(StopError):
            st.start(store, entry.work_ids["w1"], "single-work", completing_executor(store))
        rm.resume_phase(store, a)
        self.assertEqual(ProjectView.load(store).phase_state(a), "unstarted")
        rm.plan_exclude_phase(store, b)
        self.assertEqual(ProjectView.load(store).phase_state(b), "plan_excluded")
        rm.hold_roadmap(store, result.roadmap_id)
        with self.assertRaises(StopError):
            rm.select_phase(store, result.roadmap_id)
        rm.resume_roadmap(store, result.roadmap_id)
        st.start(store, entry.work_ids["w1"], "outer", completing_executor(store))
        rm.cancel_phase(store, a)
        view = ProjectView.load(store)
        self.assertEqual(view.phase_state(a), "cancelled")
        self.assertEqual(view.work_state(entry.work_ids["w1"]).state, "completed")
        self.assertEqual(validate_project(store), [])

    def test_achievement_is_explicit(self) -> None:
        store = self.new_project(remote=True)
        result = self.simple_roadmap(store, {"a": ("A", "a"), "b": ("B", "b")})
        a, b = result.phase_ids["a"], result.phase_ids["b"]
        self.assertEqual(rm.evaluate_achievement(store, result.roadmap_id, "achieved").status, "not_ready")
        entry = self.simple_entry(store, a)
        st.start(store, entry.entry_work_id, "outer", completing_executor(store))
        self.assertEqual(rm.evaluate_achievement(store, result.roadmap_id, "achieved").status, "not_ready")
        rm.plan_exclude_phase(store, b)
        human = rm.evaluate_achievement(store, result.roadmap_id, "human_confirmation", "見た目の確認が要る")
        self.assertEqual(human.status, "human_confirmation_required")
        self.assertEqual(ProjectView.load(store).roadmap_lifecycle(result.roadmap_id), "active")
        not_yet = rm.evaluate_achievement(store, result.roadmap_id, "not_achieved")
        self.assertEqual(not_yet.status, "not_achieved")
        self.assertIsNone(rm.select_phase(store, result.roadmap_id))
        self.assertIn("achievement", rm.diagnose_no_candidate(store, result.roadmap_id))
        achieved = rm.evaluate_achievement(store, result.roadmap_id, "achieved")
        self.assertEqual(achieved.status, "achieved")
        self.assertEqual(ProjectView.load(store).roadmap_lifecycle(result.roadmap_id), "achieved")
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), git(self.remote_path(), "rev-parse", "main").strip())
        with self.assertRaises(SpecViolation):
            rm.evaluate_achievement(store, result.roadmap_id, "achieved")
        self.assertEqual(validate_project(store), [])


if __name__ == "__main__":
    unittest.main()
