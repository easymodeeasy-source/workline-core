"""An interrupted Phase expansion carries on where it stopped (BL-023).

Expanding a Phase writes several entities and relations. If the process stops
part-way, the mutation stays pending and the operation must be able to continue
it: the same mutation, the same reserved IDs, the recorded effects classified
rather than repeated, and only the stages that were never recorded decided now.

Continuing is only safe when it is provable that the continuation is expanding
the same plan. Nothing in the Project's own files says which design a
half-finished expansion belonged to, so Phase entry writes the design into the
mutation's invocation before it reserves a single ID. A retry carrying a
different design does not match that record, and is refused rather than grafted
onto it - half of one plan and half of another is what must never happen. A
record written before Phase entry bound its design cannot be shown to be either,
so it is left for a human to reconcile.
"""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor
from workline import gitcmd, gitops, yamlish
from workline import roadmap as rm
from workline import start as st
from workline.errors import ReconcileRequired, StopError
from workline.mutation import Mutation, MutationController
from workline.state import ProjectView
from workline.validate import validate_project

D1 = rm.PhaseEntryDesign(
    {"a": rm.WorkDesign("Work A", "A が成立する"), "b": rm.WorkDesign("Work B", "B が成立する")},
    rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
)
D1_CONFIRMED = rm.PhaseEntryDesign(
    dict(D1.works), D1.integration, rm.WorkDesign("Confirm", "人間が確認した"))
D2 = rm.PhaseEntryDesign(
    {"x": rm.WorkDesign("Work X", "X が成立する")},
    rm.WorkDesign("Other integration", "別の統合確認"),
)


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


class ResumeCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.phase = self.simple_roadmap(self.store).phase_ids["a"]

    # interruption points ---------------------------------------------------
    def nth_call(self, target, attr: str, n: int, *, after: bool = False):
        real = getattr(target, attr)
        seen = {"n": 0}

        def fire(*args, **kwargs):
            seen["n"] += 1
            if seen["n"] == n and not after:
                raise Interrupted(f"{attr} #{n}")
            result = real(*args, **kwargs)
            if seen["n"] == n and after:
                raise Interrupted(f"{attr} #{n} (after)")
            return result

        return mock.patch.object(target, attr, fire)

    def at_stage(self, stage: str, *, after: bool = False):
        real = rm.register_works

        def fire(mutation, name, specs, relations=()):
            if name == stage and not after:
                raise Interrupted(f"before {stage}")
            result = real(mutation, name, specs, relations)
            if name == stage and after:
                raise Interrupted(f"after {stage}")
            return result

        return mock.patch.object(rm, "register_works", fire)

    POINTS = {
        "P0 intent opened": lambda case: case.nth_call(gitops, "ensure_git_ready", 1),
        "P1 IDs reserved": lambda case: case.nth_call(Mutation, "extend_scope", 1),
        "P2 works recorded": lambda case: case.nth_call(Mutation, "apply", 2),
        "P4 works applied": lambda case: case.at_stage("integration"),
        "P5 integration recorded": lambda case: case.nth_call(Mutation, "apply", 3),
        "P7 integration applied": lambda case: case.at_stage("integration", after=True),
        "P9 before finalize": lambda case: case.nth_call(rm, "_finalize", 1),
        "P10 committed": lambda case: case.nth_call(Mutation, "complete", 1),
    }

    CONFIRMED_POINTS = {
        "P8a confirmation recorded": lambda case: case.nth_call(Mutation, "apply", 4),
        "P8b confirmation applied": lambda case: case.at_stage("confirmation", after=True),
    }

    def interrupt(self, point: str, design: rm.PhaseEntryDesign = D1) -> dict:
        points = {**self.POINTS, **self.CONFIRMED_POINTS}
        with points[point](self):
            with self.assertRaises(Interrupted):
                rm.enter_phase(self.store, self.phase, design)
        (pending,) = MutationController(self.store).list_pending()
        return pending

    # observation -----------------------------------------------------------
    def record_bytes(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))}

    def phase_shape(self) -> dict:
        view = ProjectView.load(self.store)
        works = view.effective_works(self.phase)
        return {
            "normal": sorted(w.name for w in works if w.work_kind is None),
            "integrations": sorted(w.name for w in works if w.work_kind == "phase_integration_check"),
            "confirmations": sorted(w.name for w in works if w.work_kind == "human_confirmation"),
            "relations": sorted((r.type, r.from_id, r.to) for r in view.roadmap_relations),
        }


# --------------------------------------------------------------------------- the design identity
class DesignIdentityTests(ResumeCase):
    def test_the_record_holds_the_whole_design_it_is_expanding(self) -> None:
        pending = self.interrupt("P0 intent opened")

        identity = pending["invocation"]["design"]
        self.assertEqual(identity["version"], rm.DESIGN_IDENTITY_VERSION)
        self.assertEqual([w["key"] for w in identity["works"]], ["a", "b"])
        self.assertEqual(identity["works"][0]["name"], "Work A")
        self.assertEqual(identity["works"][0]["desired_state"], "A が成立する")
        self.assertEqual(identity["integration"]["name"], "Integration")
        self.assertIsNone(identity["confirmation"])
        self.assertEqual(identity["entry"], None)

    def test_the_declared_order_of_the_works_is_kept(self) -> None:
        """It decides their display numbers, so a reordering is a different plan."""
        reordered = rm.PhaseEntryDesign({"b": D1.works["b"], "a": D1.works["a"]}, D1.integration)

        self.assertNotEqual(rm.design_identity(D1), rm.design_identity(reordered))
        self.assertEqual([w["key"] for w in rm.design_identity(reordered)["works"]], ["b", "a"])

    def test_every_part_of_the_design_changes_the_identity(self) -> None:
        from workline.create import RelatedSpec

        base = rm.design_identity(D1)
        for label, design in {
            "work name": rm.PhaseEntryDesign(
                {"a": rm.WorkDesign("RENAMED", "A が成立する"), "b": D1.works["b"]}, D1.integration),
            "desired state": rm.PhaseEntryDesign(
                {"a": rm.WorkDesign("Work A", "別の状態"), "b": D1.works["b"]}, D1.integration),
            "related": rm.PhaseEntryDesign(
                {"a": rm.WorkDesign("Work A", "A が成立する", (RelatedSpec("must_read", "d.md"),)),
                 "b": D1.works["b"]}, D1.integration),
            "related condition": rm.PhaseEntryDesign(
                {"a": rm.WorkDesign("Work A", "A が成立する",
                                    (RelatedSpec("conditional_must_read", "d.md", {"kind": "path_glob", "pattern": "x"}),)),
                 "b": D1.works["b"]}, D1.integration),
            "integration": rm.PhaseEntryDesign(dict(D1.works), rm.WorkDesign("Other", "別の統合")),
            "confirmation added": D1_CONFIRMED,
            "planned_next": rm.PhaseEntryDesign(dict(D1.works), D1.integration, planned_next=(("a", "b"),)),
            "requires_completion": rm.PhaseEntryDesign(dict(D1.works), D1.integration, requires_completion=(("a", "b"),)),
            "entry": rm.PhaseEntryDesign(dict(D1.works), D1.integration, entry="a"),
        }.items():
            with self.subTest(part=label):
                self.assertNotEqual(rm.design_identity(design), base)

    def test_a_desired_state_that_renders_the_same_is_the_same_plan(self) -> None:
        """Rendering strips it, so the whitespace never reaches the Project."""
        spaced = rm.PhaseEntryDesign(
            {"a": rm.WorkDesign("Work A", "  A が成立する\n"), "b": D1.works["b"]},
            D1.integration,
        )

        self.assertEqual(rm.design_identity(spaced), rm.design_identity(D1))

    def test_a_desired_state_whose_whitespace_only_differs_still_resumes(self) -> None:
        pending = self.interrupt("P4 works applied")
        spaced = rm.PhaseEntryDesign(
            {"a": rm.WorkDesign("Work A", "A が成立する  "), "b": D1.works["b"]},
            D1.integration,
        )

        result = rm.enter_phase(self.store, self.phase, spaced)

        self.assertTrue(result.expanded)
        self.assertEqual(result.mutation_id, pending["mutation_id"])

    def test_the_same_design_gives_the_same_identity(self) -> None:
        same = rm.PhaseEntryDesign(
            {"a": rm.WorkDesign("Work A", "A が成立する"), "b": rm.WorkDesign("Work B", "B が成立する")},
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
        )

        self.assertEqual(rm.design_identity(same), rm.design_identity(D1))

    def test_the_design_is_on_disk_before_the_first_ID_is_reserved(self) -> None:
        """The window in which a record exists but is bound to nothing is closed."""
        seen: list[object] = []
        reserve = Mutation.reserve_id

        def watch(mutation: Mutation, key: str, kind: str) -> str:
            if not seen:
                record = yamlish.load(mutation.path.read_text(encoding="utf-8"))
                seen.append(record["invocation"].get("design"))
            return reserve(mutation, key, kind)

        with mock.patch.object(Mutation, "reserve_id", watch):
            rm.enter_phase(self.store, self.phase, D1)

        self.assertEqual(seen, [rm.design_identity(D1)])


# --------------------------------------------------------------------------- forward resume
class ForwardResumeTests(ResumeCase):
    def assertResumedAndFinished(self, pending: dict, design: rm.PhaseEntryDesign = D1) -> None:
        reserved = dict(pending["reserved_ids"])

        result = rm.enter_phase(self.store, self.phase, design)

        self.assertTrue(result.expanded)
        self.assertEqual(result.mutation_id, pending["mutation_id"])  # the same mutation
        shape = self.phase_shape()
        self.assertEqual(shape["normal"], ["Work A", "Work B"])
        self.assertEqual(shape["integrations"], ["Integration"])
        self.assertEqual(shape["confirmations"], ["Confirm"] if design.human_confirmation else [])
        self.assertEqual(len(shape["relations"]), len(set(shape["relations"])))  # no duplicate relation
        self.assertEqual(validate_project(self.store), [])
        # every ID this mutation had reserved is still the ID it used
        final = MutationController(self.store).list_records()
        if final:  # a resumed record is retained (BL-019)
            (record,) = [r for r in final if r["mutation_id"] == pending["mutation_id"]]
            for key, value in reserved.items():
                self.assertEqual(record["reserved_ids"][key], value)

    def test_each_interruption_point_carries_on(self) -> None:
        for point in self.POINTS:
            with self.subTest(point=point):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    pending = case.interrupt(point)
                    case.assertResumedAndFinished(pending)
                finally:
                    case.doCleanups()

    def test_a_resume_does_not_write_the_works_twice(self) -> None:
        pending = self.interrupt("P4 works applied")
        before = {w.id for w in ProjectView.load(self.store).phase_works(self.phase)}
        already = {effect["seq"] for effect in pending["effects"] if effect.get("applied")}
        self.assertTrue(already)
        executed: list[int] = []
        apply_effect = MutationController.apply_effect

        def watch(controller: MutationController, record: dict) -> None:
            executed.append(record["seq"])
            apply_effect(controller, record)

        with mock.patch.object(MutationController, "apply_effect", watch):
            rm.enter_phase(self.store, self.phase, D1)

        # The effects that had already run are classified, never executed again.
        self.assertEqual(already & set(executed), set())
        after = {w.id for w in ProjectView.load(self.store).phase_works(self.phase)}
        self.assertTrue(before < after)  # the Works already there kept their identity
        self.assertEqual(len(after), 3)
        self.assertEqual(
            [r["mutation_id"] for r in MutationController(self.store).list_records()],
            [pending["mutation_id"]],
        )

    def test_an_optional_confirmation_survives_the_interruption(self) -> None:
        with self.at_stage("confirmation"):
            with self.assertRaises(Interrupted):
                rm.enter_phase(self.store, self.phase, D1_CONFIRMED)
        (pending,) = MutationController(self.store).list_pending()

        self.assertResumedAndFinished(pending, D1_CONFIRMED)

    def test_a_confirmation_stage_already_recorded_is_not_decided_again(self) -> None:
        """The recorded confirmation is read back, not built from the design again."""
        for point in self.CONFIRMED_POINTS:
            with self.subTest(point=point):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    pending = case.interrupt(point, D1_CONFIRMED)
                    case.assertIn("confirmation", {e["stage"] for e in pending["effects"]})
                    case.assertResumedAndFinished(pending, D1_CONFIRMED)
                    case.assertEqual(case.phase_shape()["confirmations"], ["Confirm"])
                finally:
                    case.doCleanups()

    def test_a_design_without_a_confirmation_does_not_grow_one(self) -> None:
        pending = self.interrupt("P7 integration applied")

        self.assertResumedAndFinished(pending, D1)

        self.assertEqual(self.phase_shape()["confirmations"], [])

    def test_the_explicit_entry_is_the_one_the_expansion_was_bound_to(self) -> None:
        design = rm.PhaseEntryDesign(dict(D1.works), D1.integration, entry="b")
        with self.at_stage("integration"):
            with self.assertRaises(Interrupted):
                rm.enter_phase(self.store, self.phase, design)

        result = rm.enter_phase(self.store, self.phase, design)

        self.assertEqual(result.entry_work_id, result.work_ids["b"])

    def test_a_later_start_can_proceed(self) -> None:
        pending = self.interrupt("P5 integration recorded")
        self.assertResumedAndFinished(pending)

        view = ProjectView.load(self.store)
        startable = view.startable_works(self.phase)

        result = st.start(self.store, startable[0].id, "single-work", completing_executor(self.store))
        self.assertEqual(result.status, "completed")


# --------------------------------------------------------------------------- a different design
class DifferentDesignTests(ResumeCase):
    def assertRefusedAndUntouched(self, pending: dict, design: rm.PhaseEntryDesign) -> StopError:
        before_records = self.record_bytes()
        before_shape = self.phase_shape()
        before_head = gitcmd.head_commit(self.store.root)

        with self.assertRaises(ReconcileRequired) as raised:
            rm.enter_phase(self.store, self.phase, design)

        self.assertEqual(raised.exception.code, "reconcile_required")
        self.assertEqual(self.record_bytes(), before_records)  # byte for byte
        self.assertEqual(self.phase_shape(), before_shape)
        self.assertEqual(gitcmd.head_commit(self.store.root), before_head)
        (still,) = MutationController(self.store).list_pending()
        self.assertEqual(still["mutation_id"], pending["mutation_id"])
        self.assertEqual(still["reserved_ids"], pending["reserved_ids"])
        return raised.exception

    def test_a_different_design_is_never_grafted_onto_a_recorded_one(self) -> None:
        for point in ("P2 works recorded", "P4 works applied", "P7 integration applied"):
            with self.subTest(point=point):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    pending = case.interrupt(point)
                    refused = case.assertRefusedAndUntouched(pending, D2)
                    case.assertIn("different design", str(refused))
                finally:
                    case.doCleanups()

    def test_a_retry_cannot_change_the_optional_confirmation(self) -> None:
        pending = self.interrupt("P7 integration applied", D1_CONFIRMED)

        self.assertRefusedAndUntouched(pending, D1)  # the same Works, but no confirmation now

    def test_a_retry_cannot_change_the_explicit_entry(self) -> None:
        design = rm.PhaseEntryDesign(dict(D1.works), D1.integration, entry="a")
        with self.at_stage("integration"):
            with self.assertRaises(Interrupted):
                rm.enter_phase(self.store, self.phase, design)
        (pending,) = MutationController(self.store).list_pending()

        self.assertRefusedAndUntouched(pending, rm.PhaseEntryDesign(dict(D1.works), D1.integration, entry="b"))

    def test_a_condition_that_only_looks_equal_to_python_is_a_different_design(self) -> None:
        """``True`` and ``1`` are one value to Python and two to the record."""
        from workline.create import RelatedSpec

        def design(mode: object) -> rm.PhaseEntryDesign:
            return rm.PhaseEntryDesign(
                dict(D1.works),
                rm.WorkDesign(
                    "Integration", "全Workの統合確認が取れている",
                    (RelatedSpec("conditional_must_read", "docs/x.md",
                                 {"kind": "path_glob", "pattern": "src/**", "mode": mode}),),
                ),
            )

        with self.at_stage("integration"):
            with self.assertRaises(Interrupted):
                rm.enter_phase(self.store, self.phase, design(True))
        (pending,) = MutationController(self.store).list_pending()

        self.assertRefusedAndUntouched(pending, design(1))

    def test_a_reordered_design_is_a_different_design(self) -> None:
        pending = self.interrupt("P4 works applied")
        reordered = rm.PhaseEntryDesign({"b": D1.works["b"], "a": D1.works["a"]}, D1.integration)

        self.assertRefusedAndUntouched(pending, reordered)


# --------------------------------------------------------------------------- records from before
class LegacyPendingTests(ResumeCase):
    """A record written before Phase entry bound its design proves neither plan."""

    def strip_the_design(self, pending: dict) -> bytes:
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        del record["invocation"]["design"]
        path.write_text(yamlish.dump(record), encoding="utf-8")
        return path.read_bytes()

    def test_a_legacy_record_is_left_for_reconciliation(self) -> None:
        for point in ("P2 works recorded", "P4 works applied", "P7 integration applied", "P10 committed"):
            with self.subTest(point=point):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    pending = case.interrupt(point)
                    recorded = case.strip_the_design(pending)
                    shape = case.phase_shape()

                    with case.assertRaises(ReconcileRequired) as raised:
                        rm.enter_phase(case.store, case.phase, D1)

                    message = str(raised.exception)
                    case.assertIn(pending["mutation_id"], message)
                    case.assertIn(case.phase, message)
                    case.assertIn("which design", message)
                    case.assertIn("reconcile required", message)
                    path = MutationController(case.store).intent_path(pending["mutation_id"])
                    case.assertEqual(path.read_bytes(), recorded)  # untouched
                    case.assertEqual(yamlish.load(path.read_text(encoding="utf-8"))["status"], "pending")
                    case.assertEqual(case.phase_shape(), shape)
                finally:
                    case.doCleanups()


# --------------------------------------------------------------------------- what must not change
class UnchangedBehaviourTests(ResumeCase):
    def test_a_resumed_mutation_with_no_effects_is_not_abandoned(self) -> None:
        pending = self.interrupt("P1 IDs reserved")

        def stop_before_any_effect(mutation, stage, specs, relations=()):
            raise StopError("injected", code="injected")

        with mock.patch.object(rm, "register_works", stop_before_any_effect):
            with self.assertRaises(StopError):
                rm.enter_phase(self.store, self.phase, D1)

        (still,) = MutationController(self.store).list_pending()
        self.assertEqual(still["mutation_id"], pending["mutation_id"])
        self.assertEqual(still["reserved_ids"], pending["reserved_ids"])

    def test_a_fresh_mutation_that_stops_before_its_first_effect_is_still_abandoned(self) -> None:
        """BL-022's semantics for a Phase entry this run started are unchanged."""
        def stop_before_any_effect(mutation, stage, specs, relations=()):
            raise StopError("injected", code="injected")

        with mock.patch.object(rm, "register_works", stop_before_any_effect):
            with self.assertRaises(StopError):
                rm.enter_phase(self.store, self.phase, D1)

        self.assertEqual(MutationController(self.store).list_pending(), [])
        (record,) = MutationController(self.store).list_records()
        self.assertEqual(record["status"], "abandoned")

    def test_an_expanded_phase_with_nothing_pending_still_refuses_a_design(self) -> None:
        """BL-015 is untouched."""
        rm.enter_phase(self.store, self.phase, D1)

        with self.assertRaises(StopError) as raised:
            rm.enter_phase(self.store, self.phase, D1)

        self.assertEqual(raised.exception.code, "phase_already_expanded")

    def test_a_resumed_record_is_retained_after_it_completes(self) -> None:
        """BL-019: a mutation that was resumed keeps its record."""
        pending = self.interrupt("P4 works applied")

        rm.enter_phase(self.store, self.phase, D1)

        records = {r["mutation_id"]: r["status"] for r in MutationController(self.store).list_records()}
        self.assertEqual(records.get(pending["mutation_id"]), "completed")

    def test_an_uninterrupted_expansion_is_unchanged(self) -> None:
        result = rm.enter_phase(self.store, self.phase, D1)

        self.assertTrue(result.expanded)
        self.assertEqual(sorted(result.work_ids), ["a", "b"])
        self.assertEqual(self.phase_shape()["normal"], ["Work A", "Work B"])
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(MutationController(self.store).list_records(), [])  # cleaned up (BL-019)


if __name__ == "__main__":
    unittest.main()
