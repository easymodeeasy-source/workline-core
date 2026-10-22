"""Repairs of the formal review findings of the integrated RB11 candidate f1e8cf83 (Sprint 41.31).

RB11INT-D-1   a Roadmap-time design carries no explicit entry: it is refused, never accepted and dropped
RB11INT-D-2   a ``phase_entries`` / ``work_dependencies`` of the wrong shape is a controlled ValidationError
RB11INT-F-1   the design-less entry returns the plan keys of the effective current-plan Works
RB11INT-K-1   ``independent_candidates`` lists a startable Phase once, in ``phases``, and its Works nowhere else
RB11INT-EVID-2  a REAL persistence failure of the abandon write keeps the record pending and the original STOP

The other findings have their own tests in ``test_laneb_reviewer_access`` (H1-1, H1-2), ``test_laneb_overlap_diagnosis``
(C-1), ``test_laneb_gap_grounds`` (C-2) and ``test_rb11_review_repair_flows`` / ``test_rb11_review_repair_registration``
(EVID-1, C-3).
"""

from __future__ import annotations

import dataclasses
import unittest
from typing import Any
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from workline import gitops
from workline import roadmap as rm
from workline import start as st
from workline.create import WorkSpec, create_standalone_work
from workline.durable import DurableWriteError
from workline.errors import SpecViolation, StopError, ValidationError
from workline.mutation import MutationController
from workline.ops import Replan
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.state import ProjectView
from workline.validate import validate_project


def design(works: tuple[str, ...] = ("a1",), *, planned_next=(), requires=(), entry=None) -> rm.PhaseEntryDesign:
    return rm.PhaseEntryDesign(
        {key: rm.WorkDesign(key.upper(), f"{key} が成立する") for key in works},
        rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
        planned_next=tuple(planned_next),
        requires_completion=tuple(requires),
        entry=entry,
    )


def plan(entries: Any, relations=(), dependencies: Any = ()) -> rm.RoadmapPlan:
    phases = {key: PhaseSpec(f"Phase {key}", f"{key} が成立する") for key in ("a", "b", "c")}
    return rm.RoadmapPlan(
        "Test Roadmap", "背景", "達成したい状態", phases,
        tuple(PhaseRelationSpec(t, x, y) for t, x, y in relations),
        phase_entries=entries, work_dependencies=dependencies,
    )


class RepairCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def nothing_was_written(self) -> None:
        self.assertEqual({}, ProjectView.load(self.store).roadmaps)
        self.assertEqual([], MutationController(self.store).list_pending())
        self.assertEqual([], validate_project(self.store))


class ExplicitEntryTests(RepairCase):
    """RB11INT-D-1: the Work to start is read from ``planned_next``; an explicit entry is refused at registration."""

    def refused(self, entries: dict[str, rm.PhaseEntryDesign]) -> str:
        with self.assertRaises(ValidationError) as raised:
            rm.create_roadmap(self.store, plan(entries))
        self.nothing_was_written()
        return str(raised.exception)

    def test_a_valid_explicit_entry_is_refused_not_accepted_and_dropped(self) -> None:
        message = self.refused({"a": design(("a1", "a2"), entry="a1")})
        self.assertIn("explicit entry", message)
        self.assertIn("planned_next", message)

    def test_an_entry_that_is_not_a_work_key_is_refused_too(self) -> None:
        self.assertIn("explicit entry", self.refused({"a": design(("a1", "a2"), entry="zz")}))

    def test_one_explicit_entry_refuses_the_whole_creation_and_writes_nothing_for_the_other_phases(self) -> None:
        self.refused({"a": design(("a1",)), "b": design(("b1", "b2"), entry="b2")})

    def test_the_entry_is_the_work_planned_next_singles_out(self) -> None:
        result = rm.create_roadmap(self.store, plan({"a": design(("a1", "a2"), planned_next=(("a1", "a2"),))}))
        entered = rm.enter_phase(self.store, result.phase_ids["a"])
        self.assertFalse(entered.expanded)
        self.assertEqual(result.work_ids["a"]["a1"], entered.entry_work_id)

    def test_a_work_that_cannot_start_yet_is_not_the_entry(self) -> None:
        result = rm.create_roadmap(self.store, plan({"a": design(("a1", "a2"), requires=(("a1", "a2"),))}))
        entered = rm.enter_phase(self.store, result.phase_ids["a"])
        self.assertEqual(result.work_ids["a"]["a1"], entered.entry_work_id)

    def test_an_ambiguous_plan_names_no_entry_and_is_not_an_error(self) -> None:
        result = rm.create_roadmap(self.store, plan({"a": design(("a1", "a2"))}))
        entered = rm.enter_phase(self.store, result.phase_ids["a"])
        self.assertIsNone(entered.entry_work_id, "equally planned Works: the entry is named when START is handed over")

    def test_the_legacy_design_carrying_entry_still_honours_and_checks_its_explicit_entry(self) -> None:
        legacy = self.simple_roadmap(self.store, {"a": ("Phase A", "A が成立する"), "b": ("Phase B", "B が成立する")})
        with self.assertRaises(SpecViolation):
            rm.enter_phase(self.store, legacy.phase_ids["b"], design(("b1", "b2"), entry="zz"))
        entered = rm.enter_phase(self.store, legacy.phase_ids["a"], design(("a1", "a2"), entry="a2"))
        self.assertTrue(entered.expanded)
        self.assertEqual(entered.work_ids["a2"], entered.entry_work_id)


class PlanShapeTests(RepairCase):
    """RB11INT-D-2: ``phase_entries`` and ``work_dependencies`` are shape-checked before they are read."""

    def refused(self, entries: Any, dependencies: Any = ()) -> ValidationError:
        with self.assertRaises(ValidationError) as raised:  # a controlled refusal, not an AttributeError / TypeError
            rm.create_roadmap(self.store, plan(entries, dependencies=dependencies))
        self.nothing_was_written()
        return raised.exception

    def test_phase_entries_that_is_not_a_mapping(self) -> None:
        self.assertIn("mapping", str(self.refused([("a", design())])))

    def test_a_phase_entries_value_that_is_not_a_design(self) -> None:
        self.assertIn("PhaseEntryDesign", str(self.refused({"a": "not a design"})))

    def test_a_phase_entries_key_that_is_not_text(self) -> None:
        self.assertIn("Phase key", str(self.refused({1: design()})))

    def test_work_dependencies_that_is_not_a_sequence(self) -> None:
        self.assertIn("sequence", str(self.refused({"a": design(), "b": design(("b1",))}, {"x": 1})))

    def test_a_work_dependency_that_is_not_a_work_dependency(self) -> None:
        entries = {"a": design(), "b": design(("b1",))}
        self.assertIn("WorkDependency", str(self.refused(entries, [("a", "a1", "b", "b1")])))

    def test_a_work_dependency_with_a_key_that_is_not_text(self) -> None:
        entries = {"a": design(), "b": design(("b1",))}
        self.assertIn("to_work", str(self.refused(entries, (rm.WorkDependency("a", "a1", "b", 1),))))

    def test_work_dependencies_without_phase_entries_of_the_wrong_shape_is_still_a_validation_error(self) -> None:
        self.refused({}, "abc")

    def test_a_well_formed_plan_is_accepted_as_the_control(self) -> None:
        entries = {"a": design(), "b": design(("b1",))}
        result = rm.create_roadmap(self.store, plan(entries, dependencies=(rm.WorkDependency("a", "a1", "b", "b1"),)))
        self.assertEqual({"a", "b"}, set(result.work_ids))


class RegisteredEntryResultTests(RepairCase):
    """RB11INT-F-1: the design-less entry reports the plan keys of the effective current-plan Works."""

    def test_the_work_ids_are_keyed_by_the_plan_key_not_the_display_name(self) -> None:
        result = rm.create_roadmap(self.store, plan({"a": design(("a1", "a2"), planned_next=(("a1", "a2"),))}))
        entered = rm.enter_phase(self.store, result.phase_ids["a"])
        self.assertEqual({"a1", "a2"}, set(entered.work_ids))
        self.assertEqual(result.work_ids["a"], entered.work_ids, "the same keys and IDs the creation returned")

    def test_a_cancelled_work_is_not_part_of_the_reported_set(self) -> None:
        result = rm.create_roadmap(self.store, plan({"a": design(("a1", "a2"), planned_next=(("a1", "a2"),))}))
        a2 = result.work_ids["a"]["a2"]
        integration = rm.enter_phase(self.store, result.phase_ids["a"]).integration_id
        edge = [r.id for r in ProjectView.load(self.store).roadmap_relations
                if (r.type, r.from_id, r.to) == ("requires_completion", a2, integration)]
        self.assertEqual(1, len(edge))
        done = completing_executor(self.store)

        def execute(ctx: st.ExecutionContext):
            if ctx.work.id == a2:
                return st.Cancel(Replan(remove_relation_ids=tuple(edge)), "no longer needed")
            return done(ctx)

        st.start(self.store, a2, "single-work", execute)
        self.assertEqual("cancelled", ProjectView.load(self.store).work_state(a2).state)
        entered = rm.enter_phase(self.store, result.phase_ids["a"])
        self.assertEqual({"a1"}, set(entered.work_ids), "a2 is cancelled, so it is not an eligible Work of the Phase")


class CandidatesListedOnceTests(RepairCase):
    """RB11INT-K-1: AM-K lists the startable Phases, and for every OTHER Phase its blockers or its startable Works."""

    def test_a_startable_phase_is_listed_in_phases_only(self) -> None:
        entries = {"a": design(("a1",)), "b": design(("b1",)), "c": design(("c1",))}
        result = rm.create_roadmap(self.store, plan(entries, relations=(("requires_completion", "a", "b"),)))
        found = rm.independent_candidates(self.store, result.roadmap_id)
        self.assertEqual({result.phase_ids["a"], result.phase_ids["c"]}, set(found.phases))
        self.assertTrue(set(found.works).isdisjoint(found.phases), "no startable Phase is listed a second time")
        self.assertEqual({result.phase_ids["b"]}, set(found.blocked))


class AbandonPersistenceFailureTests(RepairCase):
    """RB11INT-EVID-2: the abandon write itself fails (``recovery_write_failed``), not a mocked ``Mutation.abandon``.

    ``Mutation.abandon`` sets the status in memory and then saves; the real failure is the save. The record on disk must
    still read ``pending`` with no effect, the STOP that is reported is the original ``detached_head``, and the same
    request resumes that very record once the branch is back.
    """

    def test_a_save_that_fails_while_abandoning_keeps_the_record_pending_and_the_original_stop(self) -> None:
        a = create_standalone_work(self.store, WorkSpec("A", "a")).work_id
        root = self.store.root
        branch = git(root, "symbolic-ref", "--short", "HEAD").strip()
        git(root, "checkout", "-q", "--detach", "HEAD")
        from workline import mutation as mutation_module

        real = mutation_module.durable_write_text
        failed: list[str] = []

        def write(path, text, **kwargs):
            if "status: abandoned" in text:
                failed.append(str(path))
                raise DurableWriteError("the abandonment cannot be written")
            return real(path, text, **kwargs)

        with mock.patch.object(mutation_module, "durable_write_text", side_effect=write):
            with self.assertRaises(StopError) as raised:
                st.plan_exclude_standalone_work(self.store, a)
        self.assertEqual("detached_head", raised.exception.code, "the original STOP is the one reported")
        self.assertEqual(1, len(failed), "the abandon write was attempted once and failed")
        (pending,) = MutationController(self.store).list_pending()
        self.assertEqual(("pending", []), (pending["status"], pending["effects"]), "the on-disk record is still pending")
        git(root, "checkout", "-q", branch)
        result = st.plan_exclude_standalone_work(self.store, a)
        self.assertEqual((pending["mutation_id"], "plan_excluded"), (result.mutation_id, result.status))
        self.assertEqual([], MutationController(self.store).list_pending())
        self.assertEqual([], validate_project(self.store))


class ZeroCountWaitIsUnreachableTests(unittest.TestCase):
    """RB11-GPT-D1 / C-2: a P4 HUMAN_WAIT always has at least one counted requirement decision or targeted check.

    ``derive_outcome`` returns HUMAN_WAIT exactly when ``obligations()["human"]`` is positive, and that number is
    ``_human_count`` = HUMAN claims + HUMAN gaps + targeted-check gaps, which is precisely what ``wait_breakdown`` reports
    as ``requirement_decisions + targeted_checks``. So under valid inputs the all-zero branch of ``wait_breakdown_text`` is
    not reachable; it stays as defensive text, and this test states the identity over every small combination.
    """

    def combos(self):
        import itertools

        from workline.review import p4, records

        outcomes = records.P4_OUTCOMES
        resolutions = records.P4_GAP_RESOLUTIONS
        for n_entries in range(3):
            for n_gaps in range(3):
                for entry_set in itertools.product(outcomes, repeat=n_entries):
                    for gap_set in itertools.product(resolutions, repeat=n_gaps):
                        yield p4, [{"outcome": o} for o in entry_set], [{"resolution": r} for r in gap_set]

    def test_a_human_wait_always_counts_a_requirement_decision_or_a_targeted_check(self) -> None:
        import types

        checked = waits = 0
        for p4, entries, gaps in self.combos():
            normalized = types.SimpleNamespace(drafts=(), entries=tuple(entries), gaps=tuple(gaps), strategy_change_required=False)
            outcome = p4.derive_outcome(normalized)
            stored = types.SimpleNamespace(entries=entries, coverage_gaps=gaps, obligations={})
            found = p4.wait_breakdown(stored)
            human = p4.obligations(normalized)["human"]
            self.assertEqual(human, found["requirement_decisions"] + found["targeted_checks"], (entries, gaps))
            if outcome == p4.HUMAN_WAIT:
                waits += 1
                self.assertGreaterEqual(found["requirement_decisions"] + found["targeted_checks"], 1, (entries, gaps))
                self.assertTrue(p4.wait_breakdown_text(stored).startswith("requirement decisions for a Human:"))
            checked += 1
        self.assertGreater(waits, 0)
        self.assertGreater(checked, 100)

    def test_the_defensive_text_keeps_the_stop_and_says_a_human_is_still_needed(self) -> None:
        import types

        from workline.review import p4

        empty = types.SimpleNamespace(entries=[], coverage_gaps=[], obligations={})
        text = p4.wait_breakdown_text(empty)
        self.assertIn("still needs a Human", text)
        self.assertNotIn("requirement decisions for a Human: 0", text)
