"""A replan the registration would refuse is refused before the terminal event is applied (BL-077).

Every owner of a replan - Roadmap's plan exclusion of a Phase or a Phase Work,
START's plan exclusion of a standalone Work and START's cancel - records and
applies its terminal event (``plan_excluded``, ``work_cancelled``) and only then
registers the replan's new Works. The owner judged the replan beforehand on a
projection of the whole change, but the registration core also applies payload
rules that projection does not hold - the Related types and conditions of a new
Work, the type and endpoints of a relation it carries, the state of the Phase it
joins as the terminal event leaves it - and it read the Project after the event
was in the working tree. A payload refused there left the mutation pending with
its event log uncommitted: the same request was refused again, any other request
was ``reconcile required``, and every later write of the Project was refused.

The registration's own checks now run after the owner's projection and before
it records its terminal event (``ops.refuse_replan_registration``), on the
Project with the owner's terminal events projected and with the IDs it reserved,
so such a payload is refused while the owner can still abandon its mutation:
nothing is recorded, applied, committed or pushed, the next write goes through,
and a valid replan goes exactly as it always did.
"""

from __future__ import annotations

import unittest

from helpers import WorklineTestCase, completing_executor, git, scripted_executor
from workline import roadmap as rm
from workline import start as st
from workline.create import RelatedSpec, RelationSpec, WorkSpec, create_standalone_work
from workline.errors import SpecViolation, ValidationError
from workline.mutation import MutationController
from workline.ops import Replan
from workline.state import ProjectView
from workline.validate import validate_project


class ReplanRefusalCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)

    # observation -------------------------------------------------------------
    def head(self) -> str:
        return git(self.store.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote_path(), "rev-parse", "main").strip()

    def dirty(self) -> list[str]:
        return [line for line in git(self.store.root, "status", "--porcelain", "--untracked-files=all").splitlines()
                if ".workline/runtime/" not in line]

    def snapshot(self) -> dict:
        canonical = {
            path.relative_to(self.store.root).as_posix(): path.read_bytes()
            for path in sorted(self.store.workline.rglob("*"))
            if path.is_file() and "runtime" not in path.relative_to(self.store.workline).parts
        }
        return {"files": canonical, "head": self.head(), "remote": self.remote_head(), "dirty": self.dirty()}

    def events(self, entity: str) -> list[str]:
        return [e.type for e in ProjectView.load(self.store).events if e.entity == entity]

    def assertRefusedUntouched(self, call, error, fragment: str) -> None:
        """Refused with ``error``, and the Project, Git and the recovery area are exactly as before."""
        before = self.snapshot()
        with self.assertRaises(error) as refused:
            call()
        self.assertIn(fragment, str(refused.exception))
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(self.snapshot(), before)

    def assertWritable(self) -> None:
        """The next, unrelated write of the Project goes through."""
        create_standalone_work(self.store, WorkSpec("Unrelated", "unrelated"))
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(self.dirty(), [])

    # fixtures ---------------------------------------------------------------
    def phase_works(self):
        roadmap = self.simple_roadmap(self.store)
        self.rid, self.pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, self.pa, works={"w1": "W1", "w2": "W2"})
        self.w2, self.i1 = entry.work_ids["w2"], entry.integration_id
        (self.w2_edge,) = [
            r.id for r in ProjectView.load(self.store).roadmap_relations
            if (r.type, r.from_id, r.to) == ("requires_completion", self.w2, self.i1)
        ]

    def replacement(self, *, related=(), relation_type: str = "requires_completion") -> Replan:
        """W2 excluded and replaced by W3 in front of the integration."""
        return Replan(
            remove_relation_ids=(self.w2_edge,),
            add_relations=(RelationSpec(relation_type, "w3", self.i1),),
            new_works={"w3": WorkSpec("W3", "w3", phase_id=self.pa, roadmap_id=self.rid, related=tuple(related))},
        )


class RoadmapPlanExclusionTest(ReplanRefusalCase):
    def test_a_new_work_in_the_phase_being_excluded_is_refused_before_the_event(self) -> None:
        roadmap = self.simple_roadmap(self.store, {"a": ("A", "a"), "b": ("B", "b")})
        rid, pb = roadmap.roadmap_id, roadmap.phase_ids["b"]
        replan = Replan(new_works={"x": WorkSpec("X", "x", phase_id=pb, roadmap_id=rid)})
        self.assertRefusedUntouched(lambda: rm.plan_exclude_phase(self.store, pb, replan), SpecViolation, "is plan_excluded")
        self.assertEqual(self.events(pb), [])
        self.assertWritable()
        self.assertEqual(rm.plan_exclude_phase(self.store, pb).status, "plan_excluded")

    def test_a_new_work_with_an_unknown_related_type_is_refused_before_the_event(self) -> None:
        self.phase_works()
        replan = self.replacement(related=[RelatedSpec("bogus", "elsewhere")])
        self.assertRefusedUntouched(
            lambda: rm.plan_exclude_work(self.store, self.w2, replan), ValidationError, "unknown related type bogus"
        )
        self.assertEqual(self.events(self.w2), [])
        self.assertWritable()
        self.assertEqual(rm.plan_exclude_work(self.store, self.w2, self.replacement()).status, "plan_excluded")

    def test_a_relation_of_an_unknown_type_is_still_refused_by_the_projection(self) -> None:
        """Not a BL-077 case: the owner's projection already refused it before the event, and still does."""
        self.phase_works()
        self.assertRefusedUntouched(
            lambda: rm.plan_exclude_work(self.store, self.w2, self.replacement(relation_type="bogus")),
            SpecViolation, "unknown type bogus",
        )
        self.assertEqual(self.events(self.w2), [])
        self.assertWritable()

    def test_a_valid_replacement_is_registered_as_before(self) -> None:
        self.phase_works()
        result = rm.plan_exclude_work(self.store, self.w2, self.replacement())
        self.assertEqual(result.status, "plan_excluded")
        view = ProjectView.load(self.store)
        (w3,) = [w.id for w in view.works.values() if w.name == "W3"]
        self.assertEqual(self.events(self.w2), ["plan_excluded"])
        self.assertIn(("requires_completion", w3, self.i1), {(r.type, r.from_id, r.to) for r in view.roadmap_relations})
        self.assertNotIn(self.w2_edge, {r.id for r in view.roadmap_relations})
        self.assertEqual(self.head(), self.remote_head())
        self.assertWritable()


class StartPlanExclusionTest(ReplanRefusalCase):
    def test_a_new_work_with_an_unknown_related_type_is_refused_before_the_event(self) -> None:
        s1 = create_standalone_work(self.store, WorkSpec("S1", "s1")).work_id
        replan = Replan(new_works={"x": WorkSpec("X", "x", related=(RelatedSpec("bogus", "elsewhere"),))})
        self.assertRefusedUntouched(
            lambda: st.plan_exclude_standalone_work(self.store, s1, replan), ValidationError, "unknown related type bogus"
        )
        self.assertEqual(self.events(s1), [])
        self.assertWritable()
        # Another request is not held against an unfinished record any more: there is none.
        self.assertEqual(st.plan_exclude_standalone_work(self.store, s1, Replan()).status, "plan_excluded")

    def test_a_valid_replacement_is_registered_as_before(self) -> None:
        s1 = create_standalone_work(self.store, WorkSpec("S1", "s1")).work_id
        replan = Replan(new_works={"x": WorkSpec("X", "x")})
        self.assertEqual(st.plan_exclude_standalone_work(self.store, s1, replan).status, "plan_excluded")
        self.assertEqual([w.name for w in ProjectView.load(self.store).works.values() if w.name == "X"], ["X"])
        self.assertWritable()


class StartCancelTest(ReplanRefusalCase):
    def cancel(self, work_id: str, replan: Replan):
        return st.start(self.store, work_id, "single-work", scripted_executor({"*": [st.Cancel(replan, "not needed")]}))

    def test_a_new_work_with_an_unknown_related_type_is_refused_before_the_cancel_event(self) -> None:
        s1 = create_standalone_work(self.store, WorkSpec("S1", "s1")).work_id
        bad = Replan(new_works={"x": WorkSpec("X", "x", related=(RelatedSpec("bogus", "elsewhere"),))})
        head = self.head()
        with self.assertRaises(ValidationError) as refused:
            self.cancel(s1, bad)
        self.assertIn("unknown related type bogus", str(refused.exception))
        # START's own run stays open, as for any outcome its cancel refuses, but the Work is not terminal:
        # the cancel recorded nothing, so the same START carries on with an outcome it accepts.
        self.assertNotIn("work_cancelled", self.events(s1))
        self.assertEqual(self.head(), head)
        (pending,) = MutationController(self.store).list_pending()
        self.assertFalse(any(
            effect["payload"].get("record", {}).get("type") == "work_cancelled" for effect in pending["effects"]
        ))
        self.assertEqual(self.cancel(s1, Replan()).status, "cancelled")
        self.assertEqual(self.events(s1)[-1], "work_cancelled")
        self.assertWritable()

    def test_a_valid_replacement_is_registered_as_before(self) -> None:
        s1 = create_standalone_work(self.store, WorkSpec("S1", "s1")).work_id
        result = self.cancel(s1, Replan(new_works={"x": WorkSpec("X", "x")}))
        self.assertEqual(result.status, "cancelled")
        self.assertEqual([w.name for w in ProjectView.load(self.store).works.values() if w.name == "X"], ["X"])
        self.assertWritable()


class StartOuterCancelTest(ReplanRefusalCase):
    """An outer START cancels W2 after completing W1 in the same run: the cancel meets that run's own effects."""

    def outer(self, related) -> tuple[str, str, object]:
        self.phase_works_in_order()
        replan = Replan(
            remove_relation_ids=(self.w2_edge,),
            add_relations=(RelationSpec("requires_completion", "n", self.i1),),
            new_works={"n": WorkSpec("N", "n", phase_id=self.pa, roadmap_id=self.rid, related=tuple(related))},
        )
        complete = completing_executor(self.store)

        def execute(ctx):
            return st.Cancel(replan, "superseded") if ctx.work.id == self.w2 else complete(ctx)

        return lambda: st.start(self.store, self.w1, "outer", execute)

    def phase_works_in_order(self) -> None:
        roadmap = self.simple_roadmap(self.store)
        self.rid, self.pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, self.pa, works={"w1": "W1", "w2": "W2"}, planned_next=(("w1", "w2"),))
        self.w1, self.w2, self.i1 = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id
        (self.w2_edge,) = [
            r.id for r in ProjectView.load(self.store).roadmap_relations
            if (r.type, r.from_id, r.to) == ("requires_completion", self.w2, self.i1)
        ]

    def test_a_new_work_with_an_unknown_related_type_is_refused_before_the_cancel_event(self) -> None:
        call = self.outer([RelatedSpec("bogus", "elsewhere")])
        with self.assertRaises(ValidationError) as refused:
            call()
        self.assertIn("unknown related type bogus", str(refused.exception))
        self.assertNotIn("work_cancelled", self.events(self.w2))
        (pending,) = MutationController(self.store).list_pending()
        self.assertFalse(any(
            effect["payload"].get("record", {}).get("type") in ("work_cancelled", "work_target_removed")
            and effect["payload"]["record"].get("entity") == self.w2
            for effect in pending["effects"]
        ))

    def test_a_valid_replacement_is_registered_as_before(self) -> None:
        result = self.outer([])()
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(self.events(self.w2)[-1], "work_cancelled")
        self.assertEqual([w.name for w in ProjectView.load(self.store).works.values() if w.name == "N"], ["N"])
        self.assertWritable()


class StartStandaloneKindTest(ReplanRefusalCase):
    def test_a_special_work_kind_without_a_phase_is_refused_before_the_event(self) -> None:
        s1 = create_standalone_work(self.store, WorkSpec("S1", "s1")).work_id
        replan = Replan(new_works={"x": WorkSpec("X", "x", work_kind="human_confirmation")})
        self.assertRefusedUntouched(
            lambda: st.plan_exclude_standalone_work(self.store, s1, replan), ValidationError, "special Work kinds require a Phase"
        )
        self.assertEqual(self.events(s1), [])
        self.assertWritable()

if __name__ == "__main__":
    unittest.main()
