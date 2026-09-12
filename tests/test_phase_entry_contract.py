"""The Phase-entry contract: what a design means, and when it is checked (BL-015).

Works are expanded into a Phase once. A Phase that already holds its Works has
nothing for a design to register, so passing one is refused rather than quietly
ignored - a caller that overlooked the result would otherwise believe its plan
had been recorded. What such a Phase holds is read through the Project's
read-only state, and a formal change to it belongs to the Roadmap's own
maintenance.

An explicit entry is decided from the design and the Works that already exist, so
it is checked before the expansion writes anything, rather than discovered once
the expansion has been committed.

An interrupted expansion is not a caller re-entry: its pending mutation is
recovery state and is left exactly as found. Resuming it is BL-023's subject.

The structure an expansion produced is checked before it is committed, not
after: the commit and the push happen inside the finalization, so a check that
ran only afterwards would refuse a Phase that had already landed.
"""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from workline import gitcmd
from workline import roadmap as rm
from workline import start as st
from workline import yamlish
from workline.create import RelatedSpec, WorkSpec, create_standalone_work
from workline.errors import SpecViolation, StopError, ValidationError
from workline.mutation import Mutation, MutationController
from workline.state import ProjectView
from workline.validate import Problem

D1 = rm.PhaseEntryDesign(
    {"a": rm.WorkDesign("Work A", "A が成立する"), "b": rm.WorkDesign("Work B", "B が成立する")},
    rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
)


class PhaseEntryCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.phase = self.simple_roadmap(self.store).phase_ids["a"]

    # observation -----------------------------------------------------------
    def snapshot(self) -> dict:
        """Everything a refused entry must leave exactly as it was."""
        view = ProjectView.load(self.store)
        return {
            "works": sorted(view.works),
            "relations": sorted((r.id, r.type, r.from_id, r.to) for r in view.roadmap_relations),
            "related": sorted((r.id, r.type, r.from_id, r.to) for r in view.related),
            "events": [(e.id, e.type, e.entity) for e in view.events],
            "head": gitcmd.head_commit(self.store.root),
            "records": {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))},
            "tracked": sorted(git(self.store.root, "ls-files", "--", ".workline").split()),
            "status": sorted(git(self.store.root, "status", "--porcelain", "--untracked-files=all").splitlines()),
        }

    def no_mutation_opened(self):
        """Watch the two calls a refusal must never make."""
        calls: list[str] = []
        real_open = MutationController.open
        real_reserve = Mutation.reserve_id

        def watch_open(controller, owner, invocation, scope):
            calls.append(f"open:{owner}")
            return real_open(controller, owner, invocation, scope)

        def watch_reserve(mutation, key, kind):
            calls.append(f"reserve:{key}")
            return real_reserve(mutation, key, kind)

        patches = (
            mock.patch.object(MutationController, "open", watch_open),
            mock.patch.object(Mutation, "reserve_id", watch_reserve),
        )
        return patches, calls

    def assertRefusedAndUntouched(self, design: rm.PhaseEntryDesign, code: str) -> StopError:
        """The entry is refused, and the Project is exactly as it was."""
        before = self.snapshot()
        (patch_open, patch_reserve), calls = self.no_mutation_opened()
        with patch_open, patch_reserve:
            with self.assertRaises(StopError) as raised:
                rm.enter_phase(self.store, self.phase, design)
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(calls, [])  # no intent, no reserved ID
        return raised.exception


# --------------------------------------------------------------------------- A, H, I
class FirstEntryTests(PhaseEntryCase):
    def test_a_first_entry_expands_the_phase(self) -> None:
        result = rm.enter_phase(self.store, self.phase, D1)

        view = ProjectView.load(self.store)
        self.assertTrue(result.expanded)
        self.assertEqual(sorted(result.work_ids), ["a", "b"])
        self.assertIsNotNone(result.integration_id)
        self.assertEqual(result.entry_work_id, result.work_ids["a"])
        self.assertEqual(len(view.phase_works(self.phase)), 3)

    def test_h_a_valid_explicit_entry_is_returned_as_the_entry(self) -> None:
        design = rm.PhaseEntryDesign(
            {"a": rm.WorkDesign("Work A", "A が成立する"), "b": rm.WorkDesign("Work B", "B が成立する")},
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
            entry="b",
        )

        result = rm.enter_phase(self.store, self.phase, design)

        self.assertEqual(result.entry_work_id, result.work_ids["b"])

    def test_i_without_an_explicit_entry_the_current_selection_is_unchanged(self) -> None:
        """BL-014 owns the tie-break among several startable Works; it is untouched.

        The expectation is pinned to the first declared Work rather than read back
        from ``startable_works``, so a change to that ordering - which is exactly
        what BL-014 is about - would fail here instead of moving both sides of the
        comparison together.
        """
        result = rm.enter_phase(self.store, self.phase, D1)

        self.assertEqual(result.entry_work_id, result.work_ids["a"])
        self.assertEqual(len(ProjectView.load(self.store).startable_works(self.phase)), 2)

    def test_an_entry_whose_predecessor_is_already_completed_is_accepted(self) -> None:
        """The dependency is satisfied, so this entry really can start."""
        external = create_standalone_work(self.store, WorkSpec("External", "ext done")).work_id
        st.start(self.store, external, "single-work", completing_executor(self.store))
        design = rm.PhaseEntryDesign(
            {"a": rm.WorkDesign("Work A", "A が成立する")},
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
            requires_completion=((external, "a"),),
            entry="a",
        )

        result = rm.enter_phase(self.store, self.phase, design)

        self.assertEqual(result.entry_work_id, result.work_ids["a"])


# --------------------------------------------------------------------------- G
class EntryValidationOrderingTests(PhaseEntryCase):
    """An unstartable explicit entry is refused before the expansion writes."""

    def test_g_an_entry_blocked_by_the_designs_own_dependency_is_refused_first(self) -> None:
        design = rm.PhaseEntryDesign(
            {"a": rm.WorkDesign("Work A", "A が成立する"), "b": rm.WorkDesign("Work B", "B が成立する")},
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
            requires_completion=(("a", "b"),),
            entry="b",
        )

        refused = self.assertRefusedAndUntouched(design, "spec_violation")

        self.assertIn("entry Work b", str(refused))
        self.assertIn("a (created by this expansion)", str(refused))
        self.assertEqual(ProjectView.load(self.store).phase_works(self.phase), [])

    def test_g_an_entry_naming_an_unknown_key_is_refused_first(self) -> None:
        design = rm.PhaseEntryDesign(
            {"a": rm.WorkDesign("Work A", "A が成立する")},
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
            entry="ghost",
        )

        refused = self.assertRefusedAndUntouched(design, "spec_violation")

        self.assertIn("ghost", str(refused))

    def test_g_an_entry_naming_the_integration_is_refused_first(self) -> None:
        design = rm.PhaseEntryDesign(
            {"a": rm.WorkDesign("Work A", "A が成立する")},
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
            entry="integration",
        )

        self.assertRefusedAndUntouched(design, "spec_violation")

    def test_g_an_entry_blocked_by_an_unfinished_existing_work_is_refused_first(self) -> None:
        external = create_standalone_work(self.store, WorkSpec("External", "ext done")).work_id
        design = rm.PhaseEntryDesign(
            {"a": rm.WorkDesign("Work A", "A が成立する")},
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
            requires_completion=((external, "a"),),
            entry="a",
        )

        refused = self.assertRefusedAndUntouched(design, "spec_violation")

        self.assertIn("unstarted", str(refused))

    def test_g_a_cancelled_predecessor_never_satisfies_the_entry(self) -> None:
        """``rules/ai-decision``: cancelled / plan_excluded is not completed."""
        external = create_standalone_work(self.store, WorkSpec("External", "ext done")).work_id
        from helpers import scripted_executor

        st.start(self.store, external, "single-work", scripted_executor({"*": [st.Cancel(reason="not needed")]}))
        self.assertEqual(ProjectView.load(self.store).work_state(external).state, "cancelled")
        design = rm.PhaseEntryDesign(
            {"a": rm.WorkDesign("Work A", "A が成立する")},
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
            requires_completion=((external, "a"),),
            entry="a",
        )

        self.assertRefusedAndUntouched(design, "spec_violation")

    def test_g_several_dependency_pairs_on_the_entry_are_all_reported(self) -> None:
        design = rm.PhaseEntryDesign(
            {
                "a": rm.WorkDesign("Work A", "A が成立する"),
                "b": rm.WorkDesign("Work B", "B が成立する"),
                "c": rm.WorkDesign("Work C", "C が成立する"),
            },
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
            requires_completion=(("a", "c"), ("b", "c")),
            entry="c",
        )

        refused = self.assertRefusedAndUntouched(design, "spec_violation")

        self.assertIn("a (created by this expansion)", str(refused))
        self.assertIn("b (created by this expansion)", str(refused))

    def test_g_an_unresolvable_predecessor_is_left_to_the_registration_core(self) -> None:
        """Not this check's concern - the core refuses it, and still before any commit."""
        head_before = gitcmd.head_commit(self.store.root)
        reached: list[str] = []
        register = rm.register_works

        def note(mutation, stage, specs, relations=()):
            reached.append(stage)
            return register(mutation, stage, specs, relations)

        design = rm.PhaseEntryDesign(
            {"a": rm.WorkDesign("Work A", "A が成立する")},
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
            requires_completion=(("w_01ARZ3NDEKTSV4RRFFQ69G5FAV", "a"),),
            entry="a",
        )

        with mock.patch.object(rm, "register_works", note):
            with self.assertRaises(ValidationError) as raised:
                rm.enter_phase(self.store, self.phase, design)

        # The pre-flight let it through; the registration core is what refused it.
        self.assertEqual(reached, ["works"])
        self.assertIn("unresolvable", str(raised.exception))
        self.assertEqual(ProjectView.load(self.store).phase_works(self.phase), [])
        self.assertEqual(gitcmd.head_commit(self.store.root), head_before)

    def test_the_design_shape_is_still_checked_on_a_first_entry(self) -> None:
        with self.assertRaises(ValidationError):
            rm.enter_phase(self.store, self.phase, rm.PhaseEntryDesign({}, D1.integration))
        with self.assertRaises(ValidationError):
            rm.enter_phase(
                self.store,
                self.phase,
                rm.PhaseEntryDesign({"integration": rm.WorkDesign("X", "x")}, D1.integration),
            )
        self.assertEqual(ProjectView.load(self.store).phase_works(self.phase), [])


# --------------------------------------------------------------------------- B, C, D, E, F
class ReEntryTests(PhaseEntryCase):
    """A Phase that already holds its Works does not accept a design."""

    def setUp(self) -> None:
        super().setUp()
        self.first = rm.enter_phase(self.store, self.phase, D1)

    def test_b_the_very_same_design_is_refused(self) -> None:
        refused = self.assertRefusedAndUntouched(D1, "phase_already_expanded")

        self.assertIn(self.phase, str(refused))
        self.assertIn("already expanded", str(refused))

    def test_c_a_completely_different_design_is_refused(self) -> None:
        other = rm.PhaseEntryDesign(
            {"x": rm.WorkDesign("Work X", "X が成立する"), "y": rm.WorkDesign("Work Y", "Y が成立する")},
            rm.WorkDesign("Integration Z", "Z の統合確認"),
            rm.WorkDesign("Confirm", "人間が確認した"),
            planned_next=(("x", "y"),),
            requires_completion=(("x", "y"),),
            entry="y",
        )

        self.assertRefusedAndUntouched(other, "phase_already_expanded")

    def test_d_an_unknown_entry_is_refused_rather_than_silently_substituted(self) -> None:
        design = rm.PhaseEntryDesign(D1.works, D1.integration, entry="nope")

        self.assertRefusedAndUntouched(design, "phase_already_expanded")

        # The caller is never handed some other Work as though it had asked for it.
        view = ProjectView.load(self.store)
        self.assertEqual(len(view.phase_works(self.phase)), 3)

    def test_e_an_empty_design_is_not_a_silent_success(self) -> None:
        design = rm.PhaseEntryDesign({}, D1.integration)

        self.assertRefusedAndUntouched(design, "phase_already_expanded")

    def test_f_every_kind_of_difference_is_refused_the_same_way(self) -> None:
        """The refusal is about passing a design at all, not about comparing designs.

        One representative fixture per category: no design comparison exists, so
        none of these is distinguished from another.
        """
        integration = D1.integration
        cases = {
            "work name": rm.PhaseEntryDesign(
                {"a": rm.WorkDesign("RENAMED", "A が成立する"), "b": D1.works["b"]}, integration),
            "desired state": rm.PhaseEntryDesign(
                {"a": rm.WorkDesign("Work A", "別の成立状態"), "b": D1.works["b"]}, integration),
            "related": rm.PhaseEntryDesign(
                {"a": rm.WorkDesign("Work A", "A が成立する", (RelatedSpec("must_read", "docs/x.md"),)),
                 "b": D1.works["b"]}, integration),
            "work removed": rm.PhaseEntryDesign({"a": D1.works["a"]}, integration),
            "work added": rm.PhaseEntryDesign(
                {**D1.works, "c": rm.WorkDesign("Work C", "C が成立する")}, integration),
            "integration": rm.PhaseEntryDesign(D1.works, rm.WorkDesign("OTHER", "別の統合確認")),
            "human_confirmation": rm.PhaseEntryDesign(
                D1.works, integration, rm.WorkDesign("Confirm", "人間が確認した")),
            "planned_next": rm.PhaseEntryDesign(D1.works, integration, planned_next=(("a", "b"),)),
            "requires_completion": rm.PhaseEntryDesign(D1.works, integration, requires_completion=(("a", "b"),)),
            "explicit entry": rm.PhaseEntryDesign(D1.works, integration, entry="b"),
        }
        for label, design in cases.items():
            with self.subTest(difference=label):
                self.assertRefusedAndUntouched(design, "phase_already_expanded")

    def test_a_started_work_does_not_make_re_entry_acceptable(self) -> None:
        st.start(self.store, self.first.work_ids["a"], "single-work", completing_executor(self.store))

        self.assertRefusedAndUntouched(D1, "phase_already_expanded")


# --------------------------------------------------------------------------- precedence
class RefusalPrecedenceTests(PhaseEntryCase):
    """The lifecycle and dependency refusals keep their own, more specific reasons.

    They predate this change and say something more useful than "already
    expanded" - that the Phase is finished, held, or still blocked. None of them
    writes anything either, so the properties BL-015 requires hold on every path.
    """

    def setUp(self) -> None:
        super().setUp()
        self.first = rm.enter_phase(self.store, self.phase, D1)

    def test_a_held_expanded_phase_reports_that_it_is_held(self) -> None:
        rm.hold_phase(self.store, self.phase)
        before = self.snapshot()

        with self.assertRaises(StopError) as raised:
            rm.enter_phase(self.store, self.phase, D1)

        self.assertIn("held", str(raised.exception))
        self.assertEqual(self.snapshot(), before)

    def test_a_completed_expanded_phase_reports_that_it_is_complete(self) -> None:
        st.start(self.store, self.first.entry_work_id, "outer", completing_executor(self.store))
        self.assertEqual(ProjectView.load(self.store).phase_state(self.phase), "complete")
        before = self.snapshot()

        with self.assertRaises(StopError) as raised:
            rm.enter_phase(self.store, self.phase, D1)

        self.assertIn("already complete", str(raised.exception))
        self.assertEqual(self.snapshot(), before)


# --------------------------------------------------------------------------- J
class InterruptedExpansionTests(PhaseEntryCase):
    """An interrupted expansion is recovery state, not a caller re-entry.

    It is never reported as an already-expanded Phase, and its pending record is
    never abandoned or removed. Since BL-023 it is also carried forward: the same
    design finishes the expansion on the same mutation, and a different design is
    refused with the record left exactly as it was. The full resume behaviour is
    covered in ``test_phase_expansion_resume``; what matters here is that Phase
    entry keeps telling these two situations apart.
    """

    def interrupt_after_the_normal_works(self) -> dict:
        register = rm.register_works

        def crash_before_the_integration(mutation, stage, specs, relations=()):
            if stage == "integration":
                raise RuntimeError("the process stops here")
            return register(mutation, stage, specs, relations)

        with mock.patch.object(rm, "register_works", crash_before_the_integration):
            with self.assertRaises(RuntimeError):
                rm.enter_phase(self.store, self.phase, D1)
        (pending,) = MutationController(self.store).list_pending()
        return pending

    def test_j_the_same_design_carries_the_expansion_forward(self) -> None:
        pending = self.interrupt_after_the_normal_works()
        self.assertTrue(ProjectView.load(self.store).phase_works(self.phase))

        result = rm.enter_phase(self.store, self.phase, D1)

        self.assertTrue(result.expanded)
        self.assertEqual(result.mutation_id, pending["mutation_id"])  # the same mutation
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(len(ProjectView.load(self.store).phase_works(self.phase)), 3)

    def test_j_a_changed_design_never_touches_the_pending_record(self) -> None:
        pending = self.interrupt_after_the_normal_works()
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        recorded = path.read_bytes()

        other = rm.PhaseEntryDesign(
            {"x": rm.WorkDesign("Work X", "X が成立する")},
            rm.WorkDesign("Integration Z", "Z の統合確認"),
        )
        with self.assertRaises(StopError) as raised:
            rm.enter_phase(self.store, self.phase, other)

        self.assertEqual(raised.exception.code, "reconcile_required")
        self.assertEqual(path.read_bytes(), recorded)  # byte for byte
        self.assertEqual(yamlish.load(path.read_text(encoding="utf-8"))["status"], "pending")

    def test_j_an_interrupted_expansion_is_not_reported_as_already_expanded(self) -> None:
        self.interrupt_after_the_normal_works()

        result = rm.enter_phase(self.store, self.phase, D1)

        # Recovery state is carried forward, never refused as a settled Phase.
        self.assertTrue(result.expanded)

    def test_a_pending_mutation_of_another_operation_does_not_excuse_re_entry(self) -> None:
        """The exception needs this Phase's own phase-entry, not just its Phase ID.

        A predicate that matched only ``phase_id`` would wrongly treat this as
        recovery state.
        """
        from workline.mutation import WriteScope
        from workline.oplock import project_operation

        rm.enter_phase(self.store, self.phase, D1)
        with project_operation(self.store, "probe", {"phase_id": self.phase}):
            MutationController(self.store).open(
                "roadmap",
                {"operation": "phase-entry-lookalike", "phase_id": self.phase},
                WriteScope(entities=(self.phase,), files=rm.LEDGER_FILES),
            )
        (pending,) = MutationController(self.store).list_pending()
        self.assertEqual(pending["invocation"]["phase_id"], self.phase)

        with self.assertRaises(StopError) as raised:
            rm.enter_phase(self.store, self.phase, D1)

        self.assertEqual(raised.exception.code, "phase_already_expanded")

    def test_an_unrelated_phases_pending_mutation_does_not_excuse_re_entry(self) -> None:
        """The exception covers this Phase's own interrupted expansion, nothing else."""
        from workline.phase_create import PhaseSpec

        rm.enter_phase(self.store, self.phase, D1)  # this Phase is properly expanded
        roadmap_id = ProjectView.load(self.store).phases[self.phase].roadmap_id
        other_phase = rm.add_phases(self.store, roadmap_id, {"b": PhaseSpec("B", "b が成立する")}).phase_ids["b"]
        register = rm.register_works

        def crash_before_the_integration(mutation, stage, specs, relations=()):
            if stage == "integration":
                raise RuntimeError("the process stops here")
            return register(mutation, stage, specs, relations)

        with mock.patch.object(rm, "register_works", crash_before_the_integration):
            with self.assertRaises(RuntimeError):
                rm.enter_phase(self.store, other_phase, D1)
        (pending,) = MutationController(self.store).list_pending()
        self.assertEqual(pending["invocation"]["phase_id"], other_phase)

        # The pending entry belongs to the other Phase, so this one is still
        # refused: its own expansion finished and nothing is recovering it.
        with self.assertRaises(StopError) as raised:
            rm.enter_phase(self.store, self.phase, D1)

        self.assertEqual(raised.exception.code, "phase_already_expanded")
        self.assertEqual([p["mutation_id"] for p in MutationController(self.store).list_pending()],
                         [pending["mutation_id"]])


# --------------------------------------------------------------------------- structure check
class ExpansionStructureCheckTests(PhaseEntryCase):
    def test_a_broken_expansion_is_refused_before_anything_is_committed(self) -> None:
        """The expansion's own structure check is what STOPs it before Git.

        The check is called for its refusal, not for its value, so nothing later
        reads what it returns and no other test would notice if the call itself
        were dropped along with that unused result. Losing it would not go
        unnoticed at runtime: the finalization commits and pushes before its own
        postcheck, so the refusal would arrive only once the broken expansion
        had already landed.
        """
        before = gitcmd.head_commit(self.store.root)
        real = rm.validate_structure
        calls = {"n": 0}

        def failing(view):
            calls["n"] += 1
            # 1 is the precheck; 2 is the expansion's own structure check
            return [Problem("work_invalid", "injected")] if calls["n"] == 2 else real(view)

        with mock.patch.object(rm, "validate_structure", failing):
            with self.assertRaises(ValidationError) as raised:
                rm.enter_phase(self.store, self.phase, D1)

        # Nothing reached Git: the refusal came before the commit and the push.
        self.assertEqual(gitcmd.head_commit(self.store.root), before)
        self.assertEqual(raised.exception.code, "structure_invalid")
        self.assertIn("phase structure check", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
