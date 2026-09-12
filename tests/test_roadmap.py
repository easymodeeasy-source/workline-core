from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git, scripted_executor
from workline import roadmap as rm
from workline import start as st
from workline.errors import SpecViolation, StopError, ValidationError
from workline.mutation import Mutation, MutationController, WriteScope
from workline.oplock import project_operation
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
        # Phase CREATE joins the Project execution lock its Roadmap caller holds
        with project_operation(store, "phase-create-test"):
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
        with project_operation(store, "phase-create-test"):
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
        # A Phase that already holds its Works does not accept another design: it
        # is refused rather than quietly ignored (BL-015).
        with self.assertRaises(StopError) as refused:
            self.simple_entry(store, b)
        self.assertEqual(refused.exception.code, "phase_already_expanded")
        self.assertTrue(first.expanded)
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



class PhaseStateTests(WorklineTestCase):
    """A Phase is started only by Works that entered their execution lifecycle."""

    def test_plan_excluded_work_leaves_the_phase_unstarted(self) -> None:
        store = self.new_project()
        result = self.simple_roadmap(store)
        phase_id = result.phase_ids["a"]
        entry = self.simple_entry(store, phase_id, {"w1": "one", "w2": "two"})
        w1, w2 = entry.work_ids["w1"], entry.work_ids["w2"]
        self.assertEqual(ProjectView.load(store).phase_state(phase_id), "unstarted")

        # excluding an unstarted Work from the current plan is a planning decision
        view = ProjectView.load(store)
        rel = next(r for r in view.roadmap_relations if r.type == "requires_completion" and r.from_id == w1)
        rm.plan_exclude_work(store, w1, Replan(remove_relation_ids=(rel.id,)))
        view = ProjectView.load(store)
        self.assertEqual(view.work_state(w1).state, "plan_excluded")
        self.assertEqual([w.id for w in view.effective_works(phase_id)], sorted([w2, entry.integration_id]))
        self.assertEqual(view.phase_state(phase_id), "unstarted")

        # so the future-plan Phase itself can still be plan-excluded
        excluded = rm.plan_exclude_phase(store, phase_id)
        self.assertEqual(excluded.status, "plan_excluded")
        self.assertEqual(ProjectView.load(store).phase_state(phase_id), "plan_excluded")
        self.assertEqual(validate_project(store), [])

    def test_started_work_makes_the_phase_in_progress(self) -> None:
        store = self.new_project()
        result = self.simple_roadmap(store)
        phase_id = result.phase_ids["a"]
        entry = self.simple_entry(store, phase_id, {"w1": "one", "w2": "two"})
        st.start(store, entry.work_ids["w1"], "single-work", completing_executor(store))
        self.assertEqual(ProjectView.load(store).phase_state(phase_id), "in_progress")
        with self.assertRaises(SpecViolation):
            rm.plan_exclude_phase(store, phase_id)
        self.assertEqual(validate_project(store), [])

    def test_cancelled_after_start_still_counts_as_execution(self) -> None:
        store = self.new_project()
        result = self.simple_roadmap(store)
        phase_id = result.phase_ids["a"]
        entry = self.simple_entry(store, phase_id, {"w1": "one", "w2": "two"})
        w1 = entry.work_ids["w1"]
        view = ProjectView.load(store)
        rel = next(r for r in view.roadmap_relations if r.type == "requires_completion" and r.from_id == w1)
        st.start(store, w1, "single-work", scripted_executor({w1: [st.Cancel(Replan(remove_relation_ids=(rel.id,)))]}))
        view = ProjectView.load(store)
        self.assertEqual(view.work_state(w1).state, "cancelled")
        self.assertNotIn(w1, [w.id for w in view.effective_works(phase_id)])
        # the Work left the current plan but execution did happen: the Phase is started
        self.assertEqual(view.phase_state(phase_id), "in_progress")
        with self.assertRaises(SpecViolation):
            rm.plan_exclude_phase(store, phase_id)


class PhaseSelectionTests(WorklineTestCase):
    """An explicit Phase is validated independently of the candidate count."""

    def test_invalid_explicit_stops_with_and_without_other_candidates(self) -> None:
        store = self.new_project()
        result = self.simple_roadmap(store, {"a": ("A", "a"), "b": ("B", "b")}, [("requires_completion", "a", "b")])
        a, b = result.phase_ids["a"], result.phase_ids["b"]

        # A: candidates >= 1 + invalid explicit -> SpecViolation
        self.assertEqual([p.id for p in rm.startable_phases(store, result.roadmap_id)], [a])
        with self.assertRaises(SpecViolation):
            rm.select_phase(store, result.roadmap_id, explicit=b)
        # D: valid explicit -> that Phase
        self.assertEqual(rm.select_phase(store, result.roadmap_id, explicit=a).id, a)

        # B: candidates == 0 + invalid explicit (held Phase) -> SpecViolation
        rm.hold_phase(store, a)
        self.assertEqual(rm.startable_phases(store, result.roadmap_id), [])
        with self.assertRaises(SpecViolation):
            rm.select_phase(store, result.roadmap_id, explicit=a)
        with self.assertRaises(SpecViolation):
            rm.select_phase(store, result.roadmap_id, explicit=b)
        # C: candidates == 0 + no explicit -> None
        self.assertIsNone(rm.select_phase(store, result.roadmap_id))

    def test_explicit_completed_phase_stops_after_all_phases_complete(self) -> None:
        store = self.new_project()
        result = self.simple_roadmap(store)
        a = result.phase_ids["a"]
        entry = self.simple_entry(store, a)
        st.start(store, entry.entry_work_id, "outer", completing_executor(store))
        self.assertEqual(ProjectView.load(store).phase_state(a), "complete")
        self.assertEqual(rm.startable_phases(store, result.roadmap_id), [])
        self.assertIsNone(rm.select_phase(store, result.roadmap_id))
        with self.assertRaises(SpecViolation):
            rm.select_phase(store, result.roadmap_id, explicit=a)
        with self.assertRaises(SpecViolation):
            rm.select_phase(store, result.roadmap_id, explicit="p_01ARZ3NDEKTSV4RRFFQ69G5FAV")


class PhaseAdditionTests(WorklineTestCase):
    """``add_phases``: the Roadmap-owned operation that adds Phases to an existing Roadmap."""

    @contextmanager
    def _recorded_effects(self) -> Iterator[list[tuple[str, str, str, str]]]:
        """Every effect a mutation records, and which mutation recorded it.

        A mutation that completes takes its own recovery record away again
        (``rules/git``: Mutation Controller), so what an operation planned - and
        that one mutation planned all of it - is read while it runs rather than
        from a leftover file.
        """
        recorded: list[tuple[str, str, str, str]] = []
        record_effects = Mutation.add_effects

        def capture(mutation: Mutation, stage: str, effects: list) -> None:
            recorded.extend(
                (mutation.id, mutation.owner, str(mutation.invocation.get("operation")), effect.kind)
                for effect in effects
            )
            record_effects(mutation, stage, effects)

        with mock.patch.object(Mutation, "add_effects", capture):
            yield recorded

    def _assertOneAdditionMutation(self, recorded: list, added) -> list[str]:
        """Every recorded effect belongs to this add-phases mutation; return the kinds."""
        self.assertEqual(
            {(mutation_id, owner, operation) for mutation_id, owner, operation, _ in recorded},
            {(added.mutation_id, "roadmap", "roadmap-add-phases")},
        )
        return [kind for *_, kind in recorded]

    def _addition_intents(self, store) -> list[dict]:
        """Recovery records an add-phases mutation left behind: none, once it completed."""
        controller = MutationController(store)
        records = [controller._load_intent(path) for path in sorted(store.mutations.glob("*.yaml"))]
        return [r for r in records if r["owner"] == "roadmap" and r["invocation"].get("operation") == "roadmap-add-phases"]

    def test_add_one_phase_to_an_active_roadmap(self) -> None:
        store = self.new_project()  # no remote
        result = self.simple_roadmap(store, {"a": ("A", "a"), "b": ("B", "b")}, [("planned_next", "a", "b")])
        a, b = result.phase_ids["a"], result.phase_ids["b"]
        before = ProjectView.load(store)
        roadmap_path = store.abs(before.roadmaps[result.roadmap_id].path)
        roadmap_text = roadmap_path.read_text(encoding="utf-8")
        phase_texts = {p.id: store.abs(p.path).read_text(encoding="utf-8") for p in before.phases.values()}
        relations_before = {(r.id, r.type, r.from_id, r.to) for r in before.roadmap_relations}
        dirty = store.root / "user_notes.txt"
        dirty.write_text("人間の未commit変更\n", encoding="utf-8")

        with self._recorded_effects() as recorded:
            added = rm.add_phases(store, result.roadmap_id, {"c": PhaseSpec("C", "c state")})

        view = ProjectView.load(store)
        new_id = added.phase_ids["c"]
        self.assertEqual(added.roadmap_id, result.roadmap_id)
        self.assertFalse(added.resumed)
        self.assertEqual(set(view.phases), {a, b, new_id})
        self.assertEqual(view.phases[new_id].roadmap_id, result.roadmap_id)
        self.assertEqual(view.phases[new_id].display, "P-03")  # display numbering continues
        self.assertEqual(view.phase_state(new_id), "unstarted")

        # nothing existing was rewritten
        self.assertEqual(roadmap_path.read_text(encoding="utf-8"), roadmap_text)
        for phase_id, content in phase_texts.items():
            self.assertEqual(store.abs(view.phases[phase_id].path).read_text(encoding="utf-8"), content)
        self.assertEqual({(r.id, r.type, r.from_id, r.to) for r in view.roadmap_relations}, relations_before)
        self.assertEqual(view.events, [])
        self.assertEqual(view.works, {})
        self.assertEqual(validate_project(store), [])

        # one Roadmap-owned mutation, commit but no push without a remote
        kinds = self._assertOneAdditionMutation(recorded, added)
        self.assertIn("git_commit", kinds)
        self.assertNotIn("git_push", kinds)
        # It completed, so it cleaned up after itself: no record of it is left,
        # and nothing of it is still open.
        self.assertEqual(self._addition_intents(store), [])
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(git(store.root, "log", "-1", "--format=%s").strip(), "chore(workline): add phases to roadmap R-01")
        self.assertEqual(set(git(store.root, "show", "--name-only", "--format=", "HEAD").split()), {view.phases[new_id].path})

        # the human's uncommitted change is untouched
        self.assertEqual(dirty.read_text(encoding="utf-8"), "人間の未commit変更\n")
        self.assertIn("?? user_notes.txt", git(store.root, "status", "--porcelain", "--untracked-files=all"))

    def test_add_multiple_phases_with_relations_and_push(self) -> None:
        store = self.new_project(remote=True)
        result = self.simple_roadmap(store, {"a": ("A", "a")})
        a = result.phase_ids["a"]
        with self._recorded_effects() as recorded:
            added = rm.add_phases(
                store,
                result.roadmap_id,
                {"c": PhaseSpec("C", "c state"), "d": PhaseSpec("D", "d state")},
                (
                    PhaseRelationSpec("requires_completion", "c", "d"),
                    PhaseRelationSpec("planned_next", "c", "d"),
                    PhaseRelationSpec("planned_next", a, "c"),
                ),
            )
        c, d = added.phase_ids["c"], added.phase_ids["d"]
        view = ProjectView.load(store)
        self.assertEqual({p.display for p in view.phases.values()}, {"P-01", "P-02", "P-03"})
        self.assertEqual({(r.type, r.from_id, r.to) for r in view.roadmap_relations}, {
            ("requires_completion", c, d),
            ("planned_next", c, d),
            ("planned_next", a, c),
        })
        self.assertEqual(len(added.relation_ids), 3)
        self.assertEqual([p.id for p in rm.startable_phases(store, result.roadmap_id)], sorted([a, c]))
        self.assertEqual(validate_project(store), [])
        self.assertIn("git_push", self._assertOneAdditionMutation(recorded, added))
        self.assertEqual(self._addition_intents(store), [])
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), git(self.remote_path(), "rev-parse", "main").strip())
        self.assertEqual(MutationController(store).list_pending(), [])

    def test_not_achieved_recovery_adds_a_phase_without_touching_the_desired_state(self) -> None:
        store = self.new_project()
        result = self.simple_roadmap(store)
        a = result.phase_ids["a"]
        entry = self.simple_entry(store, a)
        st.start(store, entry.entry_work_id, "outer", completing_executor(store))
        roadmap_path = store.abs(ProjectView.load(store).roadmaps[result.roadmap_id].path)
        roadmap_text = roadmap_path.read_text(encoding="utf-8")
        self.assertEqual(rm.evaluate_achievement(store, result.roadmap_id, "not_achieved").status, "not_achieved")
        self.assertIsNone(rm.select_phase(store, result.roadmap_id))

        added = rm.add_phases(
            store,
            result.roadmap_id,
            {"c": PhaseSpec("残り作業", "残りが成立する")},
            (PhaseRelationSpec("planned_next", a, "c"),),
        )

        view = ProjectView.load(store)
        self.assertEqual(roadmap_path.read_text(encoding="utf-8"), roadmap_text)  # desired state untouched
        self.assertEqual(view.roadmap_lifecycle(result.roadmap_id), "active")
        self.assertFalse(view.all_active_phases_complete(result.roadmap_id))
        self.assertEqual(rm.select_phase(store, result.roadmap_id).id, added.phase_ids["c"])
        self.assertEqual(rm.evaluate_achievement(store, result.roadmap_id, "achieved").status, "not_ready")
        self.assertEqual(validate_project(store), [])

    def test_terminal_roadmaps_refuse_phase_addition(self) -> None:
        store = self.new_project()
        result = self.simple_roadmap(store)
        entry = self.simple_entry(store, result.phase_ids["a"])
        st.start(store, entry.entry_work_id, "outer", completing_executor(store))
        self.assertEqual(rm.evaluate_achievement(store, result.roadmap_id, "achieved").status, "achieved")
        with self.assertRaises(SpecViolation):
            rm.add_phases(store, result.roadmap_id, {"x": PhaseSpec("X", "x state")})

        cancelled = self.simple_roadmap(store, {"z": ("Z", "z")})
        rm.cancel_roadmap(store, cancelled.roadmap_id)
        with self.assertRaises(SpecViolation):
            rm.add_phases(store, cancelled.roadmap_id, {"x": PhaseSpec("X", "x state")})

        # a held Roadmap follows the existing lifecycle rule
        held = self.simple_roadmap(store, {"h": ("H", "h")})
        rm.hold_roadmap(store, held.roadmap_id)
        with self.assertRaises(SpecViolation):
            rm.add_phases(store, held.roadmap_id, {"x": PhaseSpec("X", "x state")})
        rm.add_phases(store, held.roadmap_id, {"x": PhaseSpec("X", "x state")}, future_plan_change=True)

        with self.assertRaises(ValidationError):
            rm.add_phases(store, result.roadmap_id, {})
        with self.assertRaises(ValidationError):
            rm.add_phases(store, "r_01ARZ3NDEKTSV4RRFFQ69G5FAV", {"x": PhaseSpec("X", "x state")})
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(validate_project(store), [])

    def test_failed_push_resumes_the_same_addition(self) -> None:
        store = self.new_project(remote=True)
        result = self.simple_roadmap(store)
        phases = {"c": PhaseSpec("C", "c state")}
        # The approved destination stays the same; it is merely unreachable.
        away = self.tmp / "proj-remote-away.git"
        self.remote_path().rename(away)
        with self.assertRaises(StopError) as ctx:
            rm.add_phases(store, result.roadmap_id, phases)
        self.assertEqual(ctx.exception.code, "git_error")
        pending = MutationController(store).list_pending()
        self.assertEqual([p["owner"] for p in pending], ["roadmap"])
        registered = [p for p in ProjectView.load(store).phases if p != result.phase_ids["a"]]
        self.assertEqual(len(registered), 1)

        away.rename(self.remote_path())
        resumed = rm.add_phases(store, result.roadmap_id, phases)
        self.assertTrue(resumed.resumed)
        self.assertEqual(resumed.mutation_id, pending[0]["mutation_id"])
        self.assertEqual(resumed.phase_ids["c"], registered[0])  # same stable ID, no re-registration
        self.assertEqual(len(ProjectView.load(store).phases), 2)
        self.assertEqual(git(store.root, "log", "--format=%s").count("add phases to roadmap"), 1)
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), git(self.remote_path(), "rev-parse", "main").strip())
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(validate_project(store), [])


if __name__ == "__main__":
    unittest.main()
