from __future__ import annotations

import unittest

from helpers import WorklineTestCase, completing_executor, git, scripted_executor
from workline import roadmap as rm
from workline import start as st
from workline.create import RelationSpec, WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, SpecViolation, StopError
from workline.mutation import MutationController
from workline.ops import Replan
from workline.state import ProjectView
from workline.validate import validate_project


def events_of(store, work_id):
    return [e.type for e in ProjectView.load(store).events if e.entity == work_id]


class StartLifecycleTests(WorklineTestCase):
    def _phase(self, store, works=None, **kwargs):
        roadmap = self.simple_roadmap(store)
        entry = self.simple_entry(store, roadmap.phase_ids["a"], works, **kwargs)
        return roadmap, entry

    def test_normal_completion_single_work(self) -> None:
        store = self.new_project(remote=True)
        roadmap, entry = self._phase(store)
        w1 = entry.work_ids["w1"]
        log: list[str] = []
        result = st.start(store, w1, "single-work", completing_executor(store, log))
        self.assertEqual(result.status, "completed")
        self.assertEqual(log, [w1])
        self.assertEqual(events_of(store, w1), ["work_started", "work_target_added", "work_target_removed", "work_completed"])
        messages = git(store.root, "log", "--format=%s").splitlines()
        self.assertEqual(messages[:2], ["chore(workline): complete W-01", "feat(workline): W-01 W1"])
        result_commit = set(git(store.root, "show", "--name-only", "--format=", "HEAD~1").split())
        self.assertEqual(result_commit, {"result_W-01.txt"})
        final_commit = set(git(store.root, "show", "--name-only", "--format=", "HEAD").split())
        self.assertIn(".workline/events/events.jsonl", final_commit)
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), git(self.remote_path(), "rev-parse", "main").strip())
        # single-work mode does not continue with the integration
        view = ProjectView.load(store)
        self.assertEqual(view.work_state(entry.integration_id).state, "unstarted")
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(validate_project(store), [])

    def test_dependency_and_terminal_guards(self) -> None:
        store = self.new_project()
        roadmap, entry = self._phase(store)
        with self.assertRaises(StopError) as ctx:
            st.start(store, entry.integration_id, "single-work", completing_executor(store))
        self.assertEqual(ctx.exception.code, "dependency_unsatisfied")
        st.start(store, entry.work_ids["w1"], "single-work", completing_executor(store))
        with self.assertRaises(SpecViolation):
            st.start(store, entry.work_ids["w1"], "single-work", completing_executor(store))

    def test_question_wait_keeps_target_and_resumes_same_mutation(self) -> None:
        store = self.new_project()
        roadmap, entry = self._phase(store)
        w1 = entry.work_ids["w1"]
        result = st.start(store, w1, "single-work", scripted_executor({w1: [st.QuestionWait("which colour?")]}))
        self.assertEqual(result.status, "question_wait")
        state = ProjectView.load(store).work_state(w1)
        self.assertEqual((state.state, state.has_target), ("in_progress", True))
        self.assertEqual(events_of(store, w1), ["work_started", "work_target_added"])
        self.assertEqual(len(ProjectView.load(store).works), 2)  # no human_confirmation for a question
        pending = MutationController(store).list_pending()
        self.assertEqual([p["mutation_id"] for p in pending], [result.mutation_id])
        resumed = st.start(store, w1, "single-work", completing_executor(store))
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(resumed.mutation_id, result.mutation_id)
        self.assertEqual(events_of(store, w1), ["work_started", "work_target_added", "work_target_removed", "work_completed"])

    def test_hold_and_resume(self) -> None:
        store = self.new_project()
        roadmap, entry = self._phase(store)
        w1 = entry.work_ids["w1"]
        held = st.start(store, w1, "single-work", scripted_executor({w1: [st.Hold("blocked externally")]}))
        self.assertEqual(held.status, "held")
        self.assertEqual(events_of(store, w1), ["work_started", "work_target_added", "work_target_removed", "work_held"])
        self.assertEqual(ProjectView.load(store).work_state(w1).state, "held")
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertIn(".workline/events/events.jsonl", git(store.root, "show", "--name-only", "--format=", "HEAD"))
        resumed = st.start(store, w1, "single-work", completing_executor(store))
        self.assertEqual(resumed.status, "completed")
        self.assertNotEqual(resumed.mutation_id, held.mutation_id)
        self.assertEqual(events_of(store, w1)[4:], ["work_resumed", "work_target_added", "work_target_removed", "work_completed"])

    def test_cancel_requires_replan_and_is_not_completion(self) -> None:
        store = self.new_project()
        roadmap, entry = self._phase(store, {"w1": "one", "w2": "two"})
        w1, w2, integration = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id
        # cancel without replan leaves integration depending on a cancelled predecessor → STOP before writes
        with self.assertRaises(SpecViolation):
            st.start(store, w1, "single-work", scripted_executor({w1: [st.Cancel()]}))
        self.assertEqual(events_of(store, w1), ["work_started", "work_target_added"])
        self.assertEqual([p["owner"] for p in MutationController(store).list_pending()], ["start"])
        view = ProjectView.load(store)
        rel = next(r for r in view.roadmap_relations if r.type == "requires_completion" and r.from_id == w1)
        replan = Replan(remove_relation_ids=(rel.id,))
        result = st.start(store, w1, "single-work", scripted_executor({w1: [st.Cancel(replan, "not needed")]}))
        self.assertEqual(result.status, "cancelled")
        view = ProjectView.load(store)
        self.assertEqual(view.work_state(w1).state, "cancelled")
        self.assertEqual([w.id for w in view.effective_works(roadmap.phase_ids["a"])], sorted([w2, integration]))
        self.assertTrue(view.dependencies_satisfied(integration) is False)  # w2 still pending
        self.assertEqual(validate_project(store), [])
        # cancelled is not completed: the Phase is not complete after finishing the others
        outer = st.start(store, w2, "outer", completing_executor(store))
        self.assertEqual(outer.status, "phase_complete")
        self.assertEqual(ProjectView.load(store).work_state(w1).state, "cancelled")

    def test_plan_exclusion_ownership(self) -> None:
        store = self.new_project()
        roadmap, entry = self._phase(store, {"w1": "one", "w2": "two"})
        w2, integration = entry.work_ids["w2"], entry.integration_id
        view = ProjectView.load(store)
        rel = next(r for r in view.roadmap_relations if r.type == "requires_completion" and r.from_id == w2)
        with self.assertRaises(SpecViolation):
            st.plan_exclude_standalone_work(store, w2)  # Phase Work exclusion is Roadmap-owned
        result = rm.plan_exclude_work(store, w2, Replan(remove_relation_ids=(rel.id,)))
        self.assertEqual(result.status, "plan_excluded")
        view = ProjectView.load(store)
        self.assertEqual(view.work_state(w2).state, "plan_excluded")
        self.assertNotIn(w2, [w.id for w in view.effective_works(roadmap.phase_ids["a"])])
        with self.assertRaises(SpecViolation):
            rm.plan_exclude_work(store, entry.work_ids["w1"])  # would leave the dependency unreplanned
        standalone = create_standalone_work(store, WorkSpec("S", "standalone"))
        with self.assertRaises(SpecViolation):
            rm.plan_exclude_work(store, standalone.work_id)
        excluded = st.plan_exclude_standalone_work(store, standalone.work_id)
        self.assertEqual(excluded.status, "plan_excluded")
        self.assertEqual(ProjectView.load(store).work_state(standalone.work_id).state, "plan_excluded")
        st.start(store, entry.work_ids["w1"], "single-work", completing_executor(store))
        with self.assertRaises(SpecViolation):
            rm.plan_exclude_work(store, entry.work_ids["w1"])  # started Works are cancelled, not plan_excluded
        self.assertEqual(validate_project(store), [])

    def test_derived_fix_work_joins_existing_integration(self) -> None:
        store = self.new_project()
        roadmap, entry = self._phase(store)
        w1, integration = entry.work_ids["w1"], entry.integration_id
        phase_id = roadmap.phase_ids["a"]
        log: list[str] = []
        derived = {"done": False}

        def executor(ctx: st.ExecutionContext):
            log.append(ctx.work.name)
            if ctx.work.id == w1 and not derived["done"]:
                derived["done"] = True
                return st.Derive({"fix": st.DerivedWork("Fix", "gap closed", return_to=True)}, move=True)
            return st.Completed()

        moved = st.start(store, w1, "outer", executor)
        self.assertEqual(moved.status, "phase_complete")
        view = ProjectView.load(store)
        fix = next(w for w in view.works.values() if w.name == "Fix")
        self.assertEqual(view.unfinished_integrations(phase_id), [])
        self.assertEqual(len([w for w in view.phase_works(phase_id) if w.work_kind == "phase_integration_check"]), 1)
        rels = {(r.type, r.from_id, r.to) for r in view.roadmap_relations}
        self.assertIn(("derived", w1, fix.id), rels)
        self.assertIn(("return_to", fix.id, w1), rels)
        self.assertIn(("requires_completion", fix.id, integration), rels)
        self.assertEqual(log, ["W1", "Fix", "W1", "Integration"])
        self.assertEqual(events_of(store, w1), ["work_started", "work_target_added", "work_target_removed", "work_target_added", "work_target_removed", "work_completed"])
        self.assertEqual(validate_project(store), [])

    def test_human_confirmation_ng_flow(self) -> None:
        store = self.new_project()
        roadmap, entry = self._phase(store, confirmation=True)
        phase_id = roadmap.phase_ids["a"]
        w1, i1, h1 = entry.work_ids["w1"], entry.integration_id, entry.confirmation_id
        log: list[str] = []
        ng_done = {"done": False}

        def executor(ctx: st.ExecutionContext):
            log.append(ctx.work.name)
            if ctx.work.id == h1 and not ng_done["done"]:
                ng_done["done"] = True
                return st.HumanNG({"f1": st.DerivedWork("F1", "defect fixed")}, st.DerivedWork("I2", "re-integrated"))
            return st.Completed()

        result = st.start(store, w1, "outer", executor)
        self.assertEqual(result.status, "phase_complete")
        self.assertEqual(log, ["W1", "Integration", "Confirmation", "F1", "I2", "Confirmation"])
        view = ProjectView.load(store)
        confirmations = [w for w in view.phase_works(phase_id) if w.work_kind == "human_confirmation"]
        self.assertEqual([w.id for w in confirmations], [h1])  # H1 was not multiplied
        integrations = [w for w in view.phase_works(phase_id) if w.work_kind == "phase_integration_check"]
        self.assertEqual(len(integrations), 2)
        i2 = next(w.id for w in integrations if w.id != i1)
        self.assertEqual([e for e in events_of(store, i1)], ["work_started", "work_target_added", "work_target_removed", "work_completed"])  # I1 not reopened
        self.assertEqual(events_of(store, h1), ["work_started", "work_target_added", "work_target_removed", "work_target_added", "work_target_removed", "work_completed"])
        rels = {(r.type, r.from_id, r.to) for r in view.roadmap_relations}
        f1 = next(w.id for w in view.works.values() if w.name == "F1")
        self.assertIn(("derived", h1, f1), rels)
        self.assertIn(("requires_completion", f1, i2), rels)
        self.assertIn(("requires_completion", i2, h1), rels)
        self.assertEqual(validate_project(store), [])

    def test_final_push_failure_resumes_finalization_only(self) -> None:
        store = self.new_project(remote=True)
        roadmap, entry = self._phase(store)
        w1 = entry.work_ids["w1"]
        calls: list[str] = []
        away = self.tmp / "proj-remote-away.git"

        def executor(ctx: st.ExecutionContext):
            calls.append(ctx.work.id)
            # The approved destination stays the same; it is merely unreachable.
            self.remote_path().rename(away)
            return st.Completed()

        with self.assertRaises(StopError) as ctx:
            st.start(store, w1, "single-work", executor)
        self.assertEqual(ctx.exception.code, "git_error")
        self.assertEqual(events_of(store, w1), ["work_started", "work_target_added", "work_target_removed", "work_completed"])
        self.assertEqual(git(store.root, "log", "-1", "--format=%s").strip(), "chore(workline): complete W-01")
        pending = MutationController(store).list_pending()
        self.assertEqual(len(pending), 1)
        away.rename(self.remote_path())
        resumed = st.start(store, w1, "single-work", executor)
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(resumed.mutation_id, pending[0]["mutation_id"])
        self.assertEqual(calls, [w1])  # the executor did not run again
        self.assertEqual(events_of(store, w1), ["work_started", "work_target_added", "work_target_removed", "work_completed"])
        self.assertEqual(git(store.root, "log", "--format=%s").count("complete W-01"), 1)
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), git(self.remote_path(), "rev-parse", "main").strip())
        self.assertEqual(MutationController(store).list_pending(), [])

    def test_outer_stays_inside_phase(self) -> None:
        store = self.new_project()
        roadmap = self.simple_roadmap(store, {"a": ("A", "a"), "b": ("B", "b")}, [("planned_next", "a", "b")])
        entry = self.simple_entry(store, roadmap.phase_ids["a"], {"w1": "one", "w2": "two"}, planned_next=(("w2", "w1"),))
        log: list[str] = []
        result = st.start(store, entry.work_ids["w2"], "outer", completing_executor(store, log))
        self.assertEqual(result.status, "phase_complete")
        self.assertEqual(log, [entry.work_ids["w2"], entry.work_ids["w1"], entry.integration_id])
        view = ProjectView.load(store)
        self.assertEqual(view.phase_state(roadmap.phase_ids["a"]), "complete")
        self.assertEqual(view.phase_works(roadmap.phase_ids["b"]), [])
        self.assertEqual(view.phase_state(roadmap.phase_ids["b"]), "unstarted")


class IntegrationOwnershipTests(WorklineTestCase):
    def test_first_integration_is_designed_by_roadmap(self) -> None:
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        entry = self.simple_entry(store, roadmap.phase_ids["a"], {"w1": "one", "w2": "two"})
        view = ProjectView.load(store)
        integration = view.works[entry.integration_id]
        self.assertEqual(integration.work_kind, "phase_integration_check")
        preds = sorted(r.from_id for r in view.relations_to(integration.id, "requires_completion"))
        self.assertEqual(preds, sorted(entry.work_ids.values()))
        self.assertEqual(len(view.unfinished_integrations(roadmap.phase_ids["a"])), 1)

    def test_existing_unfinished_integration_receives_dependency(self) -> None:
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        entry = self.simple_entry(store, roadmap.phase_ids["a"])
        w1 = entry.work_ids["w1"]
        st.start(store, w1, "single-work", scripted_executor({w1: [st.Derive({"extra": st.DerivedWork("Extra", "more")}), st.Completed()]}))
        view = ProjectView.load(store)
        extra = next(w for w in view.works.values() if w.name == "Extra")
        self.assertEqual([r.to for r in view.relations_from(extra.id, "requires_completion")], [entry.integration_id])
        self.assertEqual(len(view.unfinished_integrations(roadmap.phase_ids["a"])), 1)
        with self.assertRaises(SpecViolation):  # START must not create a second unfinished integration
            st.start(store, extra.id, "single-work", scripted_executor({extra.id: [st.Derive({}, integration=st.DerivedWork("I2", "x"))]}))

    def test_cancelled_old_integration_is_not_counted(self) -> None:
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        entry = self.simple_entry(store, roadmap.phase_ids["a"])
        phase_id = roadmap.phase_ids["a"]
        w1, i1 = entry.work_ids["w1"], entry.integration_id
        st.start(store, w1, "single-work", completing_executor(store))
        view = ProjectView.load(store)
        old_rel = next(r for r in view.roadmap_relations if r.type == "requires_completion" and r.to == i1)
        replan = Replan(
            remove_relation_ids=(old_rel.id,),
            add_relations=(RelationSpec("requires_completion", w1, "i2"),),
            new_works={"i2": WorkSpec("I2", "new integration", phase_id=phase_id, roadmap_id=roadmap.roadmap_id, work_kind="phase_integration_check")},
        )
        result = st.start(store, i1, "single-work", scripted_executor({i1: [st.Cancel(replan, "wrong scope")]}))
        self.assertEqual(result.status, "cancelled")
        view = ProjectView.load(store)
        unfinished = view.unfinished_integrations(phase_id)
        self.assertEqual([w.name for w in unfinished], ["I2"])
        self.assertEqual(view.work_state(i1).state, "cancelled")
        self.assertFalse(view.phase_completion(phase_id).complete)
        outer = st.start(store, unfinished[0].id, "outer", completing_executor(store))
        self.assertEqual(outer.status, "phase_complete")

    def test_reintegration_after_completed_integration(self) -> None:
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        entry = self.simple_entry(store, roadmap.phase_ids["a"])
        phase_id = roadmap.phase_ids["a"]
        w1, i1 = entry.work_ids["w1"], entry.integration_id
        st.start(store, w1, "outer", completing_executor(store))
        self.assertEqual(ProjectView.load(store).phase_state(phase_id), "complete")
        # a completed Phase does not accept new Works; re-integration applies before completion:
        # rebuild the scenario with a two-work Phase where I1 completes while w2 still runs
        store2 = self.new_project("proj2")
        roadmap2 = self.simple_roadmap(store2)
        entry2 = self.simple_entry(store2, roadmap2.phase_ids["a"], {"w1": "one", "w2": "two"})
        phase2 = roadmap2.phase_ids["a"]
        a, b, i = entry2.work_ids["w1"], entry2.work_ids["w2"], entry2.integration_id
        st.start(store2, a, "single-work", completing_executor(store2))
        # w2 derives a fix without the integration having run: joins the unfinished I1
        st.start(store2, b, "single-work", scripted_executor({b: [st.Derive({"fx": st.DerivedWork("FX", "fixed")}), st.Completed()]}))
        view = ProjectView.load(store2)
        fx = next(w for w in view.works.values() if w.name == "FX")
        st.start(store2, fx.id, "single-work", completing_executor(store2))
        st.start(store2, i, "single-work", completing_executor(store2))
        self.assertEqual(ProjectView.load(store2).unfinished_integrations(phase2), [])
        self.assertEqual(ProjectView.load(store2).phase_state(phase2), "complete")
        # once complete, START refuses to add Works (no re-integration path into a completed Phase)
        with self.assertRaises(SpecViolation):
            st.start(store2, a, "single-work", completing_executor(store2))
        # re-integration while the Phase is still open: integration completed, a later derived Work needs I2
        store3 = self.new_project("proj3")
        roadmap3 = self.simple_roadmap(store3)
        entry3 = self.simple_entry(store3, roadmap3.phase_ids["a"], {"w1": "one", "w2": "two"})
        phase3 = roadmap3.phase_ids["a"]
        a3, b3, i3 = entry3.work_ids["w1"], entry3.work_ids["w2"], entry3.integration_id
        st.start(store3, a3, "single-work", completing_executor(store3))
        b_started = st.start(store3, b3, "single-work", scripted_executor({b3: [st.QuestionWait()]}))
        self.assertEqual(b_started.status, "question_wait")
        # the integration cannot complete before w2, so remove that dependency through a formal replan
        view = ProjectView.load(store3)
        self.assertEqual(len(MutationController(store3).list_pending()), 1)
        resumed = st.start(store3, b3, "single-work", scripted_executor({b3: [st.Derive({"late": st.DerivedWork("Late", "late fix", before_integration=False)}), st.Completed()]}))
        self.assertEqual(resumed.status, "completed")
        st.start(store3, i3, "single-work", completing_executor(store3))
        view = ProjectView.load(store3)
        late = next(w for w in view.works.values() if w.name == "Late")
        self.assertEqual(view.unfinished_integrations(phase3), [])
        self.assertFalse(view.phase_completion(phase3).complete)  # Late is unstarted, no unfinished integration
        with self.assertRaises(StopError) as ctx:  # a normal derived Work now needs a START-designed re-integration
            st.start(store3, late.id, "single-work", scripted_executor({late.id: [st.Derive({"more": st.DerivedWork("More", "more")})]}))
        self.assertEqual(ctx.exception.code, "reintegration_required")
        # the STOP left a pending single-work mutation: another mode on the same Work is a conflict, not a resume
        with self.assertRaises(ReconcileRequired):
            st.start(store3, late.id, "outer", completing_executor(store3))
        resumed_late = st.start(store3, late.id, "single-work", scripted_executor({
            late.id: [st.Derive({"more": st.DerivedWork("More", "more")}, integration=st.DerivedWork("I2", "re-integrated")), st.Completed()],
        }))
        self.assertEqual(resumed_late.status, "completed")
        more = next(w for w in ProjectView.load(store3).works.values() if w.name == "More")
        result = st.start(store3, more.id, "outer", completing_executor(store3))
        self.assertEqual(result.status, "phase_complete")
        view = ProjectView.load(store3)
        self.assertEqual(events_of(store3, i3).count("work_completed"), 1)  # completed integration was not reopened
        self.assertEqual(len([w for w in view.phase_works(phase3) if w.work_kind == "phase_integration_check"]), 2)
        self.assertEqual(validate_project(store3), [])


if __name__ == "__main__":
    unittest.main()
