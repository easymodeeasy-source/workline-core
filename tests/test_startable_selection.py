"""Which startable candidate is chosen, and when none is (BL-014).

Every path that used to take the head of a candidate list now reads the plan:
``planned_next`` says what comes next, and when it does not separate the
candidates the operation STOPs instead of guessing. The four paths - startable
Phase selection, Phase entry, Roadmap handoff and START's same-Phase
continuation - answer the same way, so they are checked against the same cases.

The orders that must never decide are exercised directly: identifiers are made
to sort against the declaration order, and relation records are rewritten into a
different order for the same graph. Neither may change the answer.
"""

from __future__ import annotations

import re
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from workline import ids
from workline import roadmap as rm
from workline import start as st
from workline.errors import StopError
from workline.mutation import MutationController
from workline.state import ProjectView

AMBIGUOUS = "ambiguous_startable_candidates"


def descending_ulids():
    """ULIDs that sort against the order they are minted in.

    Identifiers carry a timestamp, so they normally happen to sort the way Works
    were created. Walking the clock backwards puts the candidate list in reverse
    declaration order without changing anything the specification recognises.
    """
    real = ids.new_ulid
    clock = {"ms": 1_900_000_000_000}

    def mint(now_ms=None):
        clock["ms"] -= 1000
        return real(clock["ms"])

    return mock.patch.object(ids, "new_ulid", mint)


def same_millisecond_ulids():
    """ULIDs minted inside one millisecond, where only the random bits differ."""
    real = ids.new_ulid
    return mock.patch.object(ids, "new_ulid", lambda now_ms=None: real(1_700_000_000_000))


class WorkSelectionCase(WorklineTestCase):
    """One Phase whose Works are expanded per test."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.roadmap = self.simple_roadmap(self.store)
        self.phase = self.roadmap.phase_ids["a"]

    def design(self, keys, **kwargs) -> rm.PhaseEntryDesign:
        return rm.PhaseEntryDesign(
            {key: rm.WorkDesign(key.upper(), f"{key} が成立する") for key in keys},
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
            **kwargs,
        )

    def key_of(self, work_ids: dict[str, str], work_id: str | None) -> str | None:
        return next((key for key, value in work_ids.items() if value == work_id), work_id)


# --------------------------------------------------------------------------- site 2: Phase entry

class PhaseEntryChoiceTests(WorkSelectionCase):
    def test_a_planned_next_head_is_the_entry(self) -> None:
        """The design's recommended order decides, not the order it declared."""
        result = rm.enter_phase(self.store, self.phase, self.design(("a", "b", "c"), planned_next=(("c", "a"), ("a", "b"))))

        self.assertEqual(result.entry_work_id, result.work_ids["c"])

    def test_b_equally_startable_works_are_refused_before_anything_is_written(self) -> None:
        head = git(self.store.root, "rev-parse", "HEAD").strip()

        with self.assertRaises(StopError) as refused:
            rm.enter_phase(self.store, self.phase, self.design(("a", "b")))

        self.assertEqual(refused.exception.code, AMBIGUOUS)
        view = ProjectView.load(self.store)
        self.assertEqual(view.phase_works(self.phase), [])
        self.assertEqual(view.events, [])
        self.assertEqual(view.roadmap_relations, self.relations_at_start())
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(git(self.store.root, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(git(self.store.root, "status", "--porcelain", "--untracked-files=no").strip(), "")

    def relations_at_start(self):
        return ProjectView.load(self.store).roadmap_relations

    def test_c_one_ordered_work_does_not_decide_between_two_unordered_ones(self) -> None:
        """c is placed after a, which leaves a and b tied rather than deciding."""
        with self.assertRaises(StopError) as refused:
            rm.enter_phase(self.store, self.phase, self.design(("a", "b", "c"), planned_next=(("a", "c"),)))

        self.assertEqual(refused.exception.code, AMBIGUOUS)
        self.assertIn("a", refused.exception.message)
        self.assertIn("b", refused.exception.message)

    def test_c_a_work_that_recommends_the_rest_is_the_head(self) -> None:
        """Recommending two successors still names one Work to start: the one doing it."""
        result = rm.enter_phase(
            self.store, self.phase, self.design(("a", "b", "c"), planned_next=(("a", "b"), ("a", "c")))
        )

        self.assertEqual(result.entry_work_id, result.work_ids["a"])

    def test_d_an_explicit_entry_still_decides(self) -> None:
        """An undecided design is fine as long as the caller names the entry."""
        result = rm.enter_phase(self.store, self.phase, self.design(("a", "b"), entry="b"))

        self.assertEqual(result.entry_work_id, result.work_ids["b"])

    def test_e_a_dependency_that_leaves_one_startable_needs_no_plan(self) -> None:
        result = rm.enter_phase(self.store, self.phase, self.design(("a", "b"), requires_completion=(("a", "b"),)))

        self.assertEqual(result.entry_work_id, result.work_ids["a"])

    def test_f_identifier_order_does_not_decide(self) -> None:
        """Reversing how identifiers sort changes neither answer."""
        with descending_ulids():
            result = rm.enter_phase(self.store, self.phase, self.design(("a", "b", "c"), planned_next=(("c", "a"), ("a", "b"))))
        self.assertEqual(result.entry_work_id, result.work_ids["c"])

        other = self.simple_roadmap(self.store, {"z": ("Z", "z")}).phase_ids["z"]
        with descending_ulids(), self.assertRaises(StopError) as refused:
            rm.enter_phase(self.store, other, self.design(("a", "b")))
        self.assertEqual(refused.exception.code, AMBIGUOUS)

    def test_g_identifiers_minted_in_one_millisecond_do_not_decide(self) -> None:
        with same_millisecond_ulids(), self.assertRaises(StopError) as refused:
            rm.enter_phase(self.store, self.phase, self.design(("a", "b")))

        self.assertEqual(refused.exception.code, AMBIGUOUS)


# --------------------------------------------------------------------------- site 3: handoff

class HandoffChoiceTests(WorkSelectionCase):
    def test_a_handoff_without_an_entry_follows_the_plan(self) -> None:
        entry = rm.enter_phase(self.store, self.phase, self.design(("a", "b", "c"), planned_next=(("c", "a"), ("a", "b"))))
        log: list[str] = []

        rm.handoff(self.store, self.phase, completing_executor(self.store, log))

        self.assertEqual(self.key_of(entry.work_ids, log[0]), "c")

    def test_b_a_single_remaining_candidate_needs_no_plan(self) -> None:
        """With a completed and only b left, the handoff runs b rather than stopping."""
        entry = rm.enter_phase(self.store, self.phase, self.design(("a", "b"), entry="a"))
        st.start(self.store, entry.work_ids["a"], "single-work", completing_executor(self.store))
        log: list[str] = []

        rm.handoff(self.store, self.phase, completing_executor(self.store, log))

        self.assertEqual(self.key_of(entry.work_ids, log[0]), "b")

    def test_c_handoff_refuses_two_equally_startable_works(self) -> None:
        rm.enter_phase(self.store, self.phase, self.design(("a", "b"), entry="a"))
        head = git(self.store.root, "rev-parse", "HEAD").strip()
        log: list[str] = []

        with self.assertRaises(StopError) as refused:
            rm.handoff(self.store, self.phase, completing_executor(self.store, log))

        self.assertEqual(refused.exception.code, AMBIGUOUS)
        self.assertEqual(log, [])  # the executor never ran
        self.assertEqual(git(self.store.root, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(MutationController(self.store).list_pending(), [])

    def test_d_an_explicit_entry_work_still_decides(self) -> None:
        entry = rm.enter_phase(self.store, self.phase, self.design(("a", "b"), entry="a"))
        log: list[str] = []

        rm.handoff(self.store, self.phase, completing_executor(self.store, log), entry.work_ids["b"])

        self.assertEqual(self.key_of(entry.work_ids, log[0]), "b")


# --------------------------------------------------------------------------- site 4: outer continuation

class ContinuationChoiceTests(WorkSelectionCase):
    def test_a_the_completed_works_recommendation_is_followed(self) -> None:
        entry = rm.enter_phase(
            self.store, self.phase, self.design(("a", "b", "c"), planned_next=(("a", "b"),), entry="a")
        )
        log: list[str] = []

        result = st.start(self.store, entry.work_ids["a"], "outer", completing_executor(self.store, log))

        self.assertEqual(result.status, "phase_complete")
        self.assertEqual([self.key_of(entry.work_ids, w) for w in log[:3]], ["a", "b", "c"])

    def test_b_two_equally_recommended_works_stop_the_continuation(self) -> None:
        entry = rm.enter_phase(
            self.store, self.phase, self.design(("a", "b", "c"), planned_next=(("a", "b"), ("a", "c")), entry="a")
        )
        log: list[str] = []

        result = st.start(self.store, entry.work_ids["a"], "outer", completing_executor(self.store, log))

        self.assertEqual(result.status, "stopped")
        self.assertIn(entry.work_ids["b"], result.detail)
        self.assertIn(entry.work_ids["c"], result.detail)
        self.assertEqual([self.key_of(entry.work_ids, w) for w in log], ["a"])  # b and c never ran

    def test_c_the_stop_leaves_the_finished_work_complete_and_nothing_pending(self) -> None:
        entry = rm.enter_phase(self.store, self.phase, self.design(("a", "b", "c"), entry="a"))
        view_before = ProjectView.load(self.store)

        result = st.start(self.store, entry.work_ids["a"], "outer", completing_executor(self.store))

        self.assertEqual(result.status, "stopped")
        view = ProjectView.load(self.store)
        self.assertEqual(view.work_state(entry.work_ids["a"]).state, "completed")
        self.assertEqual(view.work_state(entry.work_ids["b"]).state, "unstarted")
        self.assertEqual(view.work_state(entry.work_ids["c"]).state, "unstarted")
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(git(self.store.root, "status", "--porcelain", "--untracked-files=no").strip(), "")
        self.assertGreater(len(view.events), len(view_before.events))  # a's own lifecycle was recorded

    def test_d_naming_the_next_work_continues_after_such_a_stop(self) -> None:
        """The human picks, and the Phase runs on from there."""
        entry = rm.enter_phase(self.store, self.phase, self.design(("a", "b", "c"), entry="a"))
        stopped = st.start(self.store, entry.work_ids["a"], "outer", completing_executor(self.store))
        self.assertEqual(stopped.status, "stopped")

        result = st.start(self.store, entry.work_ids["b"], "outer", completing_executor(self.store))

        self.assertEqual(result.status, "phase_complete")

    def test_e_identifier_order_does_not_decide_the_continuation(self) -> None:
        with descending_ulids():
            entry = rm.enter_phase(
                self.store, self.phase, self.design(("a", "b", "c"), planned_next=(("a", "b"),), entry="a")
            )
        log: list[str] = []

        result = st.start(self.store, entry.work_ids["a"], "outer", completing_executor(self.store, log))

        self.assertEqual(result.status, "phase_complete")
        self.assertEqual([self.key_of(entry.work_ids, w) for w in log[:2]], ["a", "b"])

    def test_f_derived_fix_works_do_not_pick_one_of_themselves(self) -> None:
        """Two fix Works registered together are equally startable, so START stops."""
        entry = rm.enter_phase(self.store, self.phase, self.design(("a",), entry="a"))
        derived: list[str] = []

        def execute(ctx):
            derived.append(ctx.work.id)
            if ctx.work.id == entry.work_ids["a"] and len(derived) == 1:
                return st.Derive(
                    {
                        "fix1": st.DerivedWork("Fix one", "一つ目が直っている"),
                        "fix2": st.DerivedWork("Fix two", "二つ目が直っている"),
                    }
                )
            name = f"r_{ctx.work.display}.txt"
            (self.store.root / name).write_text("x\n", encoding="utf-8")
            return st.Completed((name,))

        result = st.start(self.store, entry.work_ids["a"], "outer", execute)

        self.assertEqual(result.status, "stopped")
        self.assertIn("equally planned", result.detail)
        self.assertEqual(MutationController(self.store).list_pending(), [])


# --------------------------------------------------------------------------- site 1: startable Phase

class PhaseSelectionTests(WorklineTestCase):
    """A Roadmap whose Phases a and b are completed, each recommending another."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def roadmap_with(self, relations):
        result = self.simple_roadmap(
            self.store, {key: (key.upper(), f"{key} が成立する") for key in ("a", "b", "c", "d")}, relations
        )
        self.by_id = {value: key for key, value in result.phase_ids.items()}
        return result

    def complete(self, phase_id: str) -> None:
        entry = self.simple_entry(self.store, phase_id)
        rm.handoff(self.store, phase_id, completing_executor(self.store), entry.entry_work_id)

    def swap_planned_next_records(self) -> None:
        """Rewrite the same graph with its two planned_next records the other way round."""
        path = self.store.root / ".workline" / "relations" / "roadmap.yaml"
        text = path.read_text(encoding="utf-8")
        blocks = re.findall(r"(  - id: .*?)(?=\n  - id: |\Z)", text, re.S)
        planned = [block for block in blocks if "planned_next" in block]
        self.assertEqual(len(planned), 2)
        swapped = text.replace(planned[0], "@@0@@").replace(planned[1], planned[0]).replace("@@0@@", planned[1])
        path.write_text(swapped, encoding="utf-8")

    def test_a_one_recommended_phase_is_selected(self) -> None:
        result = self.roadmap_with([("planned_next", "a", "c"), ("planned_next", "c", "d")])
        self.complete(result.phase_ids["a"])

        selected = rm.select_phase(self.store, result.roadmap_id)

        self.assertEqual(self.by_id[selected.id], "c")

    def test_b_two_recommended_phases_are_refused(self) -> None:
        result = self.roadmap_with([("planned_next", "a", "c"), ("planned_next", "b", "d")])
        self.complete(result.phase_ids["a"])
        self.complete(result.phase_ids["b"])

        with self.assertRaises(StopError) as refused:
            rm.select_phase(self.store, result.roadmap_id)

        self.assertEqual(refused.exception.code, AMBIGUOUS)
        self.assertIn(result.phase_ids["c"], refused.exception.message)
        self.assertIn(result.phase_ids["d"], refused.exception.message)

    def test_c_relation_record_order_does_not_decide(self) -> None:
        """The same graph written in another order gives the same answer."""
        result = self.roadmap_with([("planned_next", "a", "c"), ("planned_next", "b", "d")])
        self.complete(result.phase_ids["a"])
        self.complete(result.phase_ids["b"])
        self.swap_planned_next_records()

        with self.assertRaises(StopError) as refused:
            rm.select_phase(self.store, result.roadmap_id)

        self.assertEqual(refused.exception.code, AMBIGUOUS)

    def test_d_relation_record_order_does_not_decide_a_unique_answer_either(self) -> None:
        result = self.roadmap_with([("planned_next", "a", "c"), ("planned_next", "c", "d")])
        self.complete(result.phase_ids["a"])
        self.swap_planned_next_records()

        selected = rm.select_phase(self.store, result.roadmap_id)

        self.assertEqual(self.by_id[selected.id], "c")

    def test_e_an_explicit_phase_still_decides(self) -> None:
        result = self.roadmap_with([("planned_next", "a", "c"), ("planned_next", "b", "d")])
        self.complete(result.phase_ids["a"])
        self.complete(result.phase_ids["b"])

        selected = rm.select_phase(self.store, result.roadmap_id, explicit=result.phase_ids["d"])

        self.assertEqual(self.by_id[selected.id], "d")

    def test_f_a_phase_the_plan_puts_later_does_not_tie_with_its_predecessor(self) -> None:
        """c comes after b, and b has not happened, so a is the one to start."""
        result = self.simple_roadmap(
            self.store,
            {key: (key.upper(), f"{key} が成立する") for key in ("a", "b", "c")},
            [("requires_completion", "a", "b"), ("planned_next", "a", "b"), ("planned_next", "b", "c")],
        )
        by_id = {value: key for key, value in result.phase_ids.items()}

        selected = rm.select_phase(self.store, result.roadmap_id)

        self.assertEqual(by_id[selected.id], "a")

    def test_g_a_cancelled_predecessor_holds_nothing_back(self) -> None:
        """A Phase planned after a cancelled one is not waiting for anything."""
        result = self.roadmap_with([("planned_next", "a", "c")])
        rm.cancel_phase(self.store, result.phase_ids["a"])
        rm.cancel_phase(self.store, result.phase_ids["b"])
        rm.cancel_phase(self.store, result.phase_ids["d"])

        selected = rm.select_phase(self.store, result.roadmap_id)

        self.assertEqual(self.by_id[selected.id], "c")

    def test_h_identifier_order_does_not_decide(self) -> None:
        with descending_ulids():
            result = self.roadmap_with([("planned_next", "a", "c"), ("planned_next", "c", "d")])
        self.complete(result.phase_ids["a"])

        selected = rm.select_phase(self.store, result.roadmap_id)

        self.assertEqual(self.by_id[selected.id], "c")


if __name__ == "__main__":
    unittest.main()
