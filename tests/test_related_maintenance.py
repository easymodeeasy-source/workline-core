"""Related-relation maintenance for existing unstarted Roadmap Works.

Roadmap owns ``WorkDesign.related`` at Phase entry, so it also owns later
corrections to that plan. Before this operation existed, ``roadmap.yaml``
future-plan relations could be maintained but ``related.yaml`` could not, so a
missing ``must_read`` on an unstarted Work could only be fixed by editing the
file by hand or by discarding and recreating the Work.
"""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git, scripted_executor
from workline import gitcmd, roadmap as rm, start as st
from workline.create import RelatedSpec, WorkSpec, create_standalone_work
from workline.errors import SpecViolation, StopError, ValidationError
from workline.mutation import MutationController
from workline.ops import Replan
from workline.state import ProjectView
from workline.store import ProjectStore
from workline.validate import validate_project

CONTRACT = "CONTRACT.md"


class RelatedMaintenanceCase(WorklineTestCase):
    """A Phase entered with two Works, one of which already reads CONTRACT.md."""

    def entered_project(self, name: str = "proj", *, remote: bool = False) -> tuple[ProjectStore, rm.PhaseEntryResult]:
        store = self.new_project(name, remote=remote)
        # W2 reads CONTRACT.md, so the Project really holds it: a Work whose current
        # read target is missing cannot start at all (BL-009).
        (store.root / CONTRACT).write_text("the contract\n", encoding="utf-8")
        git(store.root, "add", "--", CONTRACT)
        git(store.root, "commit", "-m", "seed the contract")
        if remote:
            git(store.root, "push", "-u", "origin", "main")
        roadmap = self.simple_roadmap(store)
        phase_id = roadmap.phase_ids["a"]
        design = rm.PhaseEntryDesign(
            {
                "w2": rm.WorkDesign("W2", "W2 が成立する", related=(RelatedSpec("must_read", CONTRACT),)),
                "w3": rm.WorkDesign("W3", "W3 が成立する"),
            },
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
            requires_completion=(("w2", "w3"),),
        )
        entry = rm.enter_phase(store, phase_id, design)
        return store, entry

    def related_of(self, store: ProjectStore, work_id: str) -> list[tuple[str, str]]:
        view = ProjectView.load(store)
        return sorted((r.type, r.to) for r in view.related if r.from_id == work_id)

    def snapshot(self, store: ProjectStore, work_id: str) -> dict:
        view = ProjectView.load(store)
        work = view.works[work_id]
        return {
            "id": work.id,
            "display": work.display,
            "body": work.body,
            "meta": dict(work.meta),
            "state": view.work_state(work_id).state,
            "events": [e.to_record() for e in view.events],
            "roadmap_relations": sorted((r.id, r.type, r.from_id, r.to) for r in view.roadmap_relations),
        }


class AddRemoveTests(RelatedMaintenanceCase):
    def test_add_must_read_to_unstarted_work(self) -> None:
        store, entry = self.entered_project()
        w3 = entry.work_ids["w3"]
        self.assertEqual(self.related_of(store, w3), [])

        result = rm.maintain_work_related(store, w3, add=(RelatedSpec("must_read", CONTRACT),))

        self.assertTrue(result.changed)
        self.assertEqual(len(result.added), 1)
        self.assertEqual(result.removed, ())
        self.assertEqual(self.related_of(store, w3), [("must_read", CONTRACT)])
        self.assertEqual(validate_project(store), [])

    def test_add_leaves_work_events_and_roadmap_relations_untouched(self) -> None:
        store, entry = self.entered_project()
        w3 = entry.work_ids["w3"]
        before = self.snapshot(store, w3)
        w2_related_before = self.related_of(store, entry.work_ids["w2"])

        rm.maintain_work_related(store, w3, add=(RelatedSpec("must_read", CONTRACT),))

        after = self.snapshot(store, w3)
        self.assertEqual(after["id"], before["id"])
        self.assertEqual(after["display"], before["display"])
        self.assertEqual(after["body"], before["body"])
        self.assertEqual(after["meta"], before["meta"])
        self.assertEqual(after["state"], before["state"])
        self.assertEqual(after["events"], before["events"])
        self.assertEqual(after["roadmap_relations"], before["roadmap_relations"])
        # another Work's related relations are untouched
        self.assertEqual(self.related_of(store, entry.work_ids["w2"]), w2_related_before)
        # the commit touches related.yaml only
        self.assertEqual(
            set(git(store.root, "show", "--name-only", "--format=", "HEAD").split()),
            {".workline/relations/related.yaml"},
        )

    def test_remove_existing_related_by_relation_id(self) -> None:
        store, entry = self.entered_project()
        w2 = entry.work_ids["w2"]
        relation = next(r for r in ProjectView.load(store).related if r.from_id == w2)

        result = rm.maintain_work_related(store, w2, remove_relation_ids=(relation.id,))

        self.assertTrue(result.changed)
        self.assertEqual(result.removed, (relation.id,))
        self.assertEqual(self.related_of(store, w2), [])
        self.assertEqual(validate_project(store), [])

    def test_add_and_remove_in_one_mutation(self) -> None:
        store, entry = self.entered_project()
        w2 = entry.work_ids["w2"]
        relation = next(r for r in ProjectView.load(store).related if r.from_id == w2)
        head_before = gitcmd.head_commit(store.root)

        result = rm.maintain_work_related(
            store,
            w2,
            add=(RelatedSpec("obey", "docs/SAFETY.md"),),
            remove_relation_ids=(relation.id,),
        )

        self.assertEqual(len(result.added), 1)
        self.assertEqual(result.removed, (relation.id,))
        self.assertEqual(self.related_of(store, w2), [("obey", "docs/SAFETY.md")])
        # one mutation, one commit
        self.assertEqual(
            git(store.root, "log", "--format=%s", f"{head_before}..HEAD").splitlines(),
            [f"chore(workline): update related refs {ProjectView.load(store).works[w2].display}"],
        )
        self.assertEqual(MutationController(store).list_pending(), [])

    def test_conditional_relations_use_the_existing_condition_validation(self) -> None:
        store, entry = self.entered_project()
        w3 = entry.work_ids["w3"]
        condition = {"kind": "path_glob", "pattern": "app/**"}

        rm.maintain_work_related(
            store, w3, add=(RelatedSpec("conditional_must_read", "docs/OCR.md", condition),)
        )

        relation = next(r for r in ProjectView.load(store).related if r.from_id == w3)
        self.assertEqual(relation.type, "conditional_must_read")
        self.assertEqual(relation.extra.get("condition"), condition)
        self.assertEqual(validate_project(store), [])

        for spec in (
            RelatedSpec("conditional_must_update", "docs/X.md", None),
            RelatedSpec("conditional_must_read", "docs/Y.md", {"kind": "nonsense", "pattern": "x"}),
            RelatedSpec("must_read", "docs/Z.md", condition),  # condition on a non-conditional type
        ):
            with self.subTest(spec=spec):
                with self.assertRaises(ValidationError):
                    rm.maintain_work_related(store, w3, add=(spec,))


class RejectionTests(RelatedMaintenanceCase):
    def test_removing_another_works_relation_stops(self) -> None:
        store, entry = self.entered_project()
        w2, w3 = entry.work_ids["w2"], entry.work_ids["w3"]
        relation = next(r for r in ProjectView.load(store).related if r.from_id == w2)

        with self.assertRaises(SpecViolation) as ctx:
            rm.maintain_work_related(store, w3, remove_relation_ids=(relation.id,))

        self.assertIn(w2, str(ctx.exception))
        self.assertEqual(self.related_of(store, w2), [("must_read", CONTRACT)])

    def test_unresolvable_relation_id_is_not_guessed(self) -> None:
        store, entry = self.entered_project()
        w2 = entry.work_ids["w2"]
        existing = next(r for r in ProjectView.load(store).related if r.from_id == w2)

        with self.assertRaises(ValidationError):
            rm.maintain_work_related(store, w2, remove_relation_ids=("rel_0000000000000000000000000",))

        # the near-miss target was not removed by similarity
        self.assertEqual(self.related_of(store, w2), [("must_read", CONTRACT)])
        self.assertIn(existing.id, {r.id for r in ProjectView.load(store).related})
        self.assertEqual(MutationController(store).list_pending(), [])

    def test_started_work_is_rejected(self) -> None:
        store, entry = self.entered_project()
        w2 = entry.work_ids["w2"]
        st.start(store, w2, "single-work", scripted_executor({w2: [st.QuestionWait("waiting")]}))
        self.assertNotEqual(ProjectView.load(store).work_state(w2).state, "unstarted")

        with self.assertRaises(SpecViolation) as ctx:
            rm.maintain_work_related(store, w2, add=(RelatedSpec("must_read", "docs/A.md"),))
        self.assertIn("unstarted", str(ctx.exception))

    def test_completed_cancelled_and_plan_excluded_works_are_rejected(self) -> None:
        # completed
        store, entry = self.entered_project()
        w2 = entry.work_ids["w2"]
        st.start(store, w2, "single-work", completing_executor(store))
        with self.assertRaises(SpecViolation):
            rm.maintain_work_related(store, w2, add=(RelatedSpec("must_read", "docs/A.md"),))

        # cancelled
        store2, entry2 = self.entered_project("cancelled")
        c2 = entry2.work_ids["w2"]
        orphaned = tuple(
            r.id for r in ProjectView.load(store2).roadmap_relations
            if r.type == "requires_completion" and r.from_id == c2
        )
        st.start(
            store2,
            c2,
            "single-work",
            scripted_executor({c2: [st.Cancel(Replan(remove_relation_ids=orphaned), "not needed")]}),
        )
        self.assertEqual(ProjectView.load(store2).work_state(c2).state, "cancelled")
        with self.assertRaises(SpecViolation):
            rm.maintain_work_related(store2, c2, add=(RelatedSpec("must_read", "docs/A.md"),))

        # plan_excluded
        store3, entry3 = self.entered_project("excluded")
        w3 = entry3.work_ids["w3"]
        integration = entry3.integration_id
        deps = [
            r.id for r in ProjectView.load(store3).roadmap_relations
            if r.type == "requires_completion" and (r.from_id == w3 or r.to == w3)
        ]
        rm.plan_exclude_work(store3, w3, Replan(remove_relation_ids=tuple(deps)))
        self.assertEqual(ProjectView.load(store3).work_state(w3).state, "plan_excluded")
        with self.assertRaises(SpecViolation):
            rm.maintain_work_related(store3, w3, add=(RelatedSpec("must_read", "docs/A.md"),))
        self.assertIsNotNone(integration)

    def test_standalone_work_is_outside_roadmap_scope(self) -> None:
        store = self.new_project()
        standalone = create_standalone_work(store, WorkSpec("Standalone", "単独作業が成立する"))

        with self.assertRaises(SpecViolation) as ctx:
            rm.maintain_work_related(store, standalone.work_id, add=(RelatedSpec("must_read", CONTRACT),))

        self.assertIn("standalone", str(ctx.exception).lower())

    def test_invalid_type_and_empty_target_are_rejected(self) -> None:
        store, entry = self.entered_project()
        w3 = entry.work_ids["w3"]
        for spec in (RelatedSpec("must_think", "docs/A.md"), RelatedSpec("must_read", "   ")):
            with self.subTest(spec=spec):
                with self.assertRaises(ValidationError):
                    rm.maintain_work_related(store, w3, add=(spec,))
        self.assertEqual(self.related_of(store, w3), [])

    def test_unresolvable_work_is_rejected(self) -> None:
        store, _ = self.entered_project()
        with self.assertRaises(ValidationError):
            rm.maintain_work_related(store, "w_0000000000000000000000000", add=(RelatedSpec("must_read", CONTRACT),))

    def test_empty_request_is_rejected(self) -> None:
        store, entry = self.entered_project()
        with self.assertRaises(ValidationError):
            rm.maintain_work_related(store, entry.work_ids["w3"])


class NoOpTests(RelatedMaintenanceCase):
    def test_existing_edge_is_not_duplicated(self) -> None:
        store, entry = self.entered_project()
        w2 = entry.work_ids["w2"]
        before = [r.id for r in ProjectView.load(store).related]
        head_before = gitcmd.head_commit(store.root)

        result = rm.maintain_work_related(store, w2, add=(RelatedSpec("must_read", CONTRACT),))

        self.assertFalse(result.changed)
        self.assertEqual(result.added, ())
        self.assertEqual(result.removed, ())
        self.assertEqual([r.id for r in ProjectView.load(store).related], before)
        self.assertEqual(gitcmd.head_commit(store.root), head_before)
        self.assertEqual(MutationController(store).list_pending(), [])

    def test_duplicate_inside_one_request_collapses(self) -> None:
        store, entry = self.entered_project()
        w3 = entry.work_ids["w3"]

        result = rm.maintain_work_related(
            store,
            w3,
            add=(RelatedSpec("must_read", CONTRACT), RelatedSpec("must_read", CONTRACT)),
        )

        self.assertEqual(len(result.added), 1)
        self.assertEqual(self.related_of(store, w3), [("must_read", CONTRACT)])

    def test_no_op_makes_no_commit_and_no_push(self) -> None:
        store, entry = self.entered_project(remote=True)
        w2 = entry.work_ids["w2"]
        head_before = gitcmd.head_commit(store.root)
        remote_before = git(self.remote_path(), "rev-parse", "main").strip()

        result = rm.maintain_work_related(store, w2, add=(RelatedSpec("must_read", CONTRACT),))

        self.assertFalse(result.changed)
        self.assertIsNone(result.mutation_id)
        self.assertEqual(gitcmd.head_commit(store.root), head_before)
        self.assertEqual(git(self.remote_path(), "rev-parse", "main").strip(), remote_before)


class FinalizationTests(RelatedMaintenanceCase):
    def test_remote_project_pushes(self) -> None:
        store, entry = self.entered_project(remote=True)
        w3 = entry.work_ids["w3"]

        rm.maintain_work_related(store, w3, add=(RelatedSpec("must_read", CONTRACT),))

        self.assertEqual(
            gitcmd.head_commit(store.root),
            git(self.remote_path(), "rev-parse", "main").strip(),
        )
        self.assertEqual(validate_project(store), [])

    def test_pre_existing_dirty_state_is_not_committed(self) -> None:
        store, entry = self.entered_project()
        (store.root / "user.txt").write_text("mine\n", encoding="utf-8")

        rm.maintain_work_related(store, entry.work_ids["w3"], add=(RelatedSpec("must_read", CONTRACT),))

        committed = set(git(store.root, "show", "--name-only", "--format=", "HEAD").split())
        self.assertEqual(committed, {".workline/relations/related.yaml"})
        self.assertIn("?? user.txt", git(store.root, "status", "--porcelain", "--untracked-files=all"))

    def test_resume_keeps_the_same_mutation_and_relation_ids(self) -> None:
        store, entry = self.entered_project()
        w3 = entry.work_ids["w3"]

        with mock.patch("workline.roadmap.gitops.finalize", side_effect=RuntimeError("crash before commit")):
            with self.assertRaises(RuntimeError):
                rm.maintain_work_related(store, w3, add=(RelatedSpec("must_read", CONTRACT),))

        pending = MutationController(store).list_pending()
        self.assertEqual(len(pending), 1)
        applied = [r.id for r in ProjectView.load(store).related if r.from_id == w3]
        self.assertEqual(len(applied), 1)

        result = rm.maintain_work_related(store, w3, add=(RelatedSpec("must_read", CONTRACT),))

        self.assertTrue(result.resumed)
        self.assertEqual(result.mutation_id, pending[0]["mutation_id"])
        self.assertEqual(result.added, tuple(applied))  # same relation ID, not a second one
        self.assertEqual([r.id for r in ProjectView.load(store).related if r.from_id == w3], applied)
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(validate_project(store), [])


class ResumeTests(RelatedMaintenanceCase):
    """A crash between the domain effects and Git must resume, never restart.

    The removal case is the sharp one: once the remove effect is applied the
    relation is gone from related.yaml, so re-resolving the request against
    current state would call it unresolvable and refuse to continue.
    """

    def _crash_before_commit(self):
        return mock.patch(
            "workline.roadmap.gitops.finalize", side_effect=RuntimeError("crash before commit")
        )

    def test_remove_only_resume_keeps_the_same_mutation(self) -> None:
        store, entry = self.entered_project()
        w2 = entry.work_ids["w2"]
        relation = next(r for r in ProjectView.load(store).related if r.from_id == w2)

        with self._crash_before_commit():
            with self.assertRaises(RuntimeError):
                rm.maintain_work_related(store, w2, remove_relation_ids=(relation.id,))

        pending = MutationController(store).list_pending()
        self.assertEqual(len(pending), 1)
        # the remove is already applied: current state no longer holds the relation
        self.assertNotIn(relation.id, {r.id for r in ProjectView.load(store).related})

        result = rm.maintain_work_related(store, w2, remove_relation_ids=(relation.id,))

        self.assertTrue(result.resumed)
        self.assertEqual(result.mutation_id, pending[0]["mutation_id"])
        self.assertEqual(result.removed, (relation.id,))
        self.assertEqual(result.added, ())
        self.assertEqual(self.related_of(store, w2), [])
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(validate_project(store), [])

    def test_add_and_remove_resume_does_not_multiply_relation_ids(self) -> None:
        store, entry = self.entered_project()
        w2 = entry.work_ids["w2"]
        relation = next(r for r in ProjectView.load(store).related if r.from_id == w2)
        request = dict(add=(RelatedSpec("obey", "docs/SAFETY.md"),), remove_relation_ids=(relation.id,))

        with self._crash_before_commit():
            with self.assertRaises(RuntimeError):
                rm.maintain_work_related(store, w2, **request)

        pending = MutationController(store).list_pending()
        self.assertEqual(len(pending), 1)
        applied = [r.id for r in ProjectView.load(store).related if r.from_id == w2]
        self.assertEqual(len(applied), 1)  # R removed, S added

        result = rm.maintain_work_related(store, w2, **request)

        self.assertTrue(result.resumed)
        self.assertEqual(result.mutation_id, pending[0]["mutation_id"])
        self.assertEqual(result.added, tuple(applied))  # the same S, not a second one
        self.assertEqual(result.removed, (relation.id,))
        self.assertEqual([r.id for r in ProjectView.load(store).related if r.from_id == w2], applied)
        self.assertEqual(self.related_of(store, w2), [("obey", "docs/SAFETY.md")])
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(validate_project(store), [])

    def test_push_failure_resumes_only_the_push(self) -> None:
        store, entry = self.entered_project("pushfail", remote=True)
        w3 = entry.work_ids["w3"]
        failing = gitcmd.GitResult(1, "", "network down")

        with mock.patch("workline.mutation.gitcmd.push", return_value=failing):
            with self.assertRaises(Exception):
                rm.maintain_work_related(store, w3, add=(RelatedSpec("must_read", CONTRACT),))

        pending = MutationController(store).list_pending()
        self.assertEqual(len(pending), 1)
        local_head = gitcmd.head_commit(store.root)
        applied = [r.id for r in ProjectView.load(store).related if r.from_id == w3]
        self.assertEqual(len(applied), 1)  # domain effect and local commit already landed
        self.assertNotEqual(
            git(self.remote_path("pushfail"), "rev-parse", "main").strip(), local_head
        )

        result = rm.maintain_work_related(store, w3, add=(RelatedSpec("must_read", CONTRACT),))

        self.assertTrue(result.resumed)
        self.assertEqual(result.mutation_id, pending[0]["mutation_id"])
        self.assertEqual(result.added, tuple(applied))
        # no second commit: the domain effect was not reinterpreted
        self.assertEqual(gitcmd.head_commit(store.root), local_head)
        self.assertEqual(git(self.remote_path("pushfail"), "rev-parse", "main").strip(), local_head)
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(validate_project(store), [])

    def test_new_operation_still_rejects_an_unresolvable_relation(self) -> None:
        """The resume path must not weaken validation for a fresh request."""
        store, entry = self.entered_project()
        w2 = entry.work_ids["w2"]
        self.assertEqual(MutationController(store).list_pending(), [])

        with self.assertRaises(ValidationError):
            rm.maintain_work_related(store, w2, remove_relation_ids=("rel_0000000000000000000000000",))

        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(self.related_of(store, w2), [("must_read", CONTRACT)])


class RegressionFixtureTests(RelatedMaintenanceCase):
    """The PokeTool case that exposed the defect, reduced to a fixture."""

    def test_w3_gains_contract_must_read_without_any_other_change(self) -> None:
        store, entry = self.entered_project()
        w2, w3 = entry.work_ids["w2"], entry.work_ids["w3"]

        view = ProjectView.load(store)
        dependency = sorted(
            (r.type, r.from_id, r.to) for r in view.roadmap_relations if r.type == "requires_completion"
        )
        self.assertIn(("requires_completion", w2, w3), dependency)
        self.assertEqual(self.related_of(store, w2), [("must_read", CONTRACT)])
        self.assertEqual(self.related_of(store, w3), [])
        before = self.snapshot(store, w3)

        result = rm.maintain_work_related(store, w3, add=(RelatedSpec("must_read", CONTRACT),))

        after = self.snapshot(store, w3)
        self.assertTrue(result.changed)
        self.assertEqual(after["id"], before["id"], "W-03 identity preserved")
        self.assertEqual(after["display"], before["display"])
        self.assertEqual(after["body"], before["body"], "Work body preserved")
        self.assertEqual(after["meta"], before["meta"])
        self.assertEqual(after["events"], before["events"], "events preserved")
        self.assertEqual(len(ProjectView.load(store).events_for(w3)), 0, "no lifecycle event")
        self.assertEqual(after["state"], "unstarted", "no plan_excluded / re-creation")
        self.assertEqual(
            sorted(
                (r.type, r.from_id, r.to)
                for r in ProjectView.load(store).roadmap_relations
                if r.type == "requires_completion"
            ),
            dependency,
            "requires_completion preserved",
        )
        self.assertEqual(self.related_of(store, w3), [("must_read", CONTRACT)], "must_read added")
        self.assertEqual(self.related_of(store, w2), [("must_read", CONTRACT)])
        self.assertEqual(validate_project(store), [])
        self.assertEqual(MutationController(store).list_pending(), [])


class SkillSpecTests(unittest.TestCase):
    def test_roadmap_skill_documents_related_maintenance(self) -> None:
        from pathlib import Path

        text = (Path(__file__).resolve().parents[1] / ".claude/skills/roadmap/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("related.yaml", text)
        self.assertIn("must_read", text)
        # manual editing is explicitly forbidden
        self.assertIn("手編集", text)


if __name__ == "__main__":
    unittest.main()
