"""RB5 §32.55: reintegration closure, late Work and the operation-contract note.

The pure START parts first; then the START hooks that apply them on real Projects (post-RB6 integration R23:
the semantics note in the first durable save, marker injection and the closure on a reviewed derivation, the
reviewed checks), in ``StartHookDeferredTests`` and ``SemanticsNoteWindowTests``.
"""

from __future__ import annotations

from dataclasses import dataclass
import unittest

from helpers import WorklineTestCase, completing_executor, git, scripted_executor
from planning_helpers import Crash, crash_at
from rb5_doubles import DEFERRED, V1, ViewBuilder, reviewed_phase
from workline import phase_integration as pi
from workline import start as st
from workline import start_integration_review as sir
from workline import start_review as sr
from workline import yamlish
from workline.create import RelationSpec, WorkSpec, register_works
from workline.errors import SpecViolation, StopError, ValidationError
from workline.mutation import Effect, MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import p4
from workline.state import ProjectView
from workline.store import Event
from workline.validate import validate_project


def phase_review() -> "sr.PhaseIntegrationReview":
    """A valid Phase Integration Review selector whose actors are never launched in these tests."""
    def never(task):
        raise AssertionError("no Phase Integration Review Run is launched here")

    return sr.PhaseIntegrationReview(discovery=(p4.DiscoveryBinding("correctness", never, "reviewer-a", "1"),),
                                     adjudicator=p4.ActorBinding(never, "adjudicator-a", "1"))


class StartCase(WorklineTestCase):
    def project(self, *, marked: bool = True, completed: bool = True, late: bool = True):
        """Phase a: W1 -> integration (marked or not; completed or not) and, unless ``late`` is False, an unstarted
        Work Y with no edge - the Work whose START derives."""
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        phase_id, rid = roadmap.phase_ids["a"], roadmap.roadmap_id
        specs = {"w1": WorkSpec("W1", "done", phase_id=phase_id, roadmap_id=rid),
                 "integration": WorkSpec("Integration", "integrated", phase_id=phase_id, roadmap_id=rid,
                                         work_kind=pi.INTEGRATION_KIND, phase_review_contract=V1 if marked else None)}
        if late:
            specs["y"] = WorkSpec("Y", "done", phase_id=phase_id, roadmap_id=rid)
        with project_operation(store, "rb5-r23-fixture"):
            mutation = MutationController(store).open(
                "roadmap", {"operation": "phase-entry", "phase_id": phase_id}, WriteScope(entities=(phase_id,))
            )
            ids = register_works(mutation, "entry", specs, [RelationSpec("requires_completion", "w1", "integration")]
                                 ).work_ids
            if completed:
                mutation.add_effects("lifecycle", [
                    Effect.append_event(Event(mutation.reserve_id(f"evt:{key}:{kind}", "event"), kind, ids[key],
                                              "2026-10-07T00:00:00Z"))
                    for key in ("w1", "integration") for kind in ("work_started", "work_completed")
                ])
                mutation.apply()
            mutation.complete()
        git(store.root, "add", "-A")
        git(store.root, "commit", "-q", "-m", "fixture")
        return store, phase_id, ids

    @staticmethod
    def reintegration():
        return st.Derive({"fix": st.DerivedWork("Fix", "fixed")}, st.DerivedWork("Reintegration", "re-integrated"))

    @staticmethod
    def new_integration(store, old: str):
        (found,) = [w for w in ProjectView.load(store).works.values()
                    if w.work_kind == pi.INTEGRATION_KIND and w.id != old]
        return found

    @staticmethod
    def predecessors(store, integration_id: str) -> list[str]:
        return sorted(r.from_id for r in ProjectView.load(store).relations_to(integration_id, "requires_completion"))

    @staticmethod
    def work_named(store, name: str) -> str:
        (found,) = [w.id for w in ProjectView.load(store).works.values() if w.name == name]
        return found

    @staticmethod
    def pending(store) -> list[dict]:
        return MutationController(store).list_pending()


@dataclass(frozen=True)
class Derived:
    """The two fields of START's ``DerivedWork`` the reviewed derivation rule reads."""

    work_kind: str | None = None
    before_integration: bool = True


class ClosureTests(unittest.TestCase):
    def test_cpq03_a_pre_existing_gap_is_reported_and_fails_closed_never_repaired(self) -> None:
        """Ruling CPQ-03: START adds / replays only the edges it owns; a gap it did not create STOPs before any effect."""
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        b.complete(normal[0])
        sir.require_no_pre_existing_closure_gap(b.view(), phase, integration)  # complete closure: proceeds
        straggler = b.work(phase, "Straggler")  # existing structure with no edge, not created by this operation
        view = b.view()
        self.assertEqual((straggler,), sir.pre_existing_closure_gaps(view, phase, integration))
        with self.assertRaises(StopError) as raised:
            sir.require_no_pre_existing_closure_gap(view, phase, integration)
        self.assertEqual(sir.CODE_COVERAGE_GAP, raised.exception.code)
        self.assertEqual(view.roadmap_relations, b.view().roadmap_relations, "nothing was wired")
        self.assertFalse(hasattr(sir, "unfinished_closure_relations"), "no auto-repair seam remains")

    def test_a_fresh_reintegration_closure_includes_completed_works_and_skips_historical_integrations(self) -> None:
        b = ViewBuilder()
        phase, normal, old, confirmation = reviewed_phase(b, confirmation=True)
        view = b.view()
        relations = sir.reintegration_closure_relations(view, phase)
        self.assertEqual(sorted(normal + [confirmation]), [relation.from_ref for relation in relations])
        self.assertTrue(all(relation.to_ref == "integration" for relation in relations))
        self.assertNotIn(old, [relation.from_ref for relation in relations])
        self.assertEqual(sorted(normal), [r.from_ref for r in sir.reintegration_closure_relations(
            view, phase, planned_downstream=[confirmation])], "a confirmation the stage makes downstream is excluded")

    def test_a_registered_reintegration_with_the_closure_covers_the_expanded_plan(self) -> None:
        b = ViewBuilder()
        phase, normal, old, _ = reviewed_phase(b)
        late = b.work(phase, "Late")
        closure = sir.reintegration_closure_relations(b.view(), phase)
        new = b.integration(phase)
        for relation in closure:
            b.requires(relation.from_ref, new)
        b.complete(late, new)
        view = b.view()
        self.assertEqual((new,), pi.covering_integration_ids(view, phase))
        self.assertTrue(pi.phase_generated_complete(view, phase))

    def test_before_integration_false_is_invalid_under_reviewed_semantics_only(self) -> None:
        works = {"fix": Derived(before_integration=False), "ok": Derived(), "conf": Derived("human_confirmation", False)}
        problems = sir.reviewed_derivation_problems(works, reviewed=True)
        self.assertEqual(1, len(problems))
        self.assertIn("fix", problems[0])
        self.assertEqual([], sir.reviewed_derivation_problems(works, reviewed=False), "legacy unchanged")


class LateWorkTests(unittest.TestCase):
    def test_late_work_is_allowed_and_requires_reintegration(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        self.assertIsNone(sir.require_reintegration_design(b.view(), phase, has_design=True))
        with self.assertRaises(StopError) as raised:
            sir.require_reintegration_design(b.view(), phase, has_design=False)
        self.assertEqual(sir.CODE_REINTEGRATION_REQUIRED, raised.exception.code)

    def test_work_before_the_unfinished_integration_attaches_to_it(self) -> None:
        b = ViewBuilder()
        phase, _, integration, _ = reviewed_phase(b, complete=False)
        self.assertEqual(integration, sir.require_reintegration_design(b.view(), phase, has_design=False))

    def test_an_unmarked_unfinished_integration_in_a_reviewed_phase_stops(self) -> None:
        """RB5A-05: late Work is never wired to a legacy integration of a reviewed Phase."""
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        b.integration(phase, marker=None)
        with self.assertRaises(StopError) as raised:
            sir.require_reintegration_design(b.view(), phase, has_design=True)
        self.assertEqual(sir.CODE_UNMARKED_UNFINISHED, raised.exception.code)

    def test_two_unfinished_integrations_stop(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b, complete=False)
        b.integration(phase)
        with self.assertRaises(SpecViolation):
            sir.require_reintegration_design(b.view(), phase, has_design=True)


class SemanticsTests(unittest.TestCase):
    def test_a_fresh_start_records_the_note_and_a_resumed_legacy_one_stays_legacy(self) -> None:
        self.assertEqual({"phase_integration_semantics": V1}, sir.fresh_operation_note())
        self.assertEqual(sir.SEMANTICS_REVIEWED, sir.mutation_semantics(V1))
        self.assertEqual(sir.SEMANTICS_LEGACY, sir.mutation_semantics(None))
        with self.assertRaises(StopError) as raised:
            sir.mutation_semantics("phase-integration-review-v9")
        self.assertEqual(sir.CODE_SEMANTICS_UNKNOWN, raised.exception.code)

    def test_marker_injection_is_fixed_and_structural(self) -> None:
        spec = WorkSpec("Re-integration", "executor-decided", phase_id="p", roadmap_id="r",
                        work_kind="phase_integration_check")
        marked = sir.marked_integration_spec(spec)
        self.assertEqual(V1, marked.phase_review_contract)
        self.assertEqual((spec.name, spec.desired_state), (marked.name, marked.desired_state))
        self.assertEqual(marked, sir.marked_integration_spec(marked))
        for bad in (WorkSpec("W", "d", phase_id="p", roadmap_id="r"),
                    WorkSpec("I", "d", phase_id="p", roadmap_id="r", work_kind="phase_integration_check",
                             phase_review_contract="other")):
            with self.subTest(spec=bad), self.assertRaises(ValidationError):
                sir.marked_integration_spec(bad)

    def test_registration_of_a_reviewed_integration_needs_phase_review_first(self) -> None:
        with self.assertRaises(StopError) as raised:
            sir.require_phase_review_for_registration(semantics=sir.SEMANTICS_REVIEWED, phase_review_supplied=False)
        self.assertEqual(sir.CODE_PHASE_REVIEW_REQUIRED, raised.exception.code)
        sir.require_phase_review_for_registration(semantics=sir.SEMANTICS_REVIEWED, phase_review_supplied=True)
        sir.require_phase_review_for_registration(semantics=sir.SEMANTICS_LEGACY, phase_review_supplied=False)


class StartHookDeferredTests(StartCase):
    def test_fresh_start_reintegration_gets_the_marker(self) -> None:
        """start.py (R23; §32.4, §32.11 - §32.13): a fresh ``phase_review`` START that creates a reintegration injects
        the marker - name and desired state stay the executor's - and wires the complete direct predecessor closure
        of the Phase (completed Works included, the old integration not)."""
        store, phase_id, ids = self.project()
        executor = scripted_executor({ids["y"]: [self.reintegration(), st.Completed()]})
        result = st.start(store, ids["y"], "single-work", executor, phase_review=phase_review())
        self.assertEqual("completed", result.status)
        new = self.new_integration(store, ids["integration"])
        self.assertEqual((V1, "Reintegration", "re-integrated"),
                         (new.phase_review_contract, new.name, new.section("このWorkで成立させる状態")))
        self.assertEqual(sorted([ids["w1"], ids["y"], self.work_named(store, "Fix")]), self.predecessors(store, new.id))
        self.assertEqual([], self.pending(store))
        self.assertEqual([], validate_project(store))

    def test_pending_legacy_start_resumes_without_marker_injection(self) -> None:
        """start.py (R23; §32.4; ruling OQ-A, CP §12; PSW-IRA OB1 (3)): a pending START record without the semantics
        note is legacy. A ``phase_review`` re-invocation resumes it (the selector is no part of the invocation) and runs
        it under legacy semantics: the reintegration it creates is unmarked, with the legacy edges only."""
        store, phase_id, ids = self.project(marked=False)  # a legacy Phase: reviewed semantics would mark it

        def interrupted(ctx):
            raise Crash("the process died while the executor ran")

        with self.assertRaises(Crash):
            st.start(store, ids["y"], "single-work", interrupted)
        (record,) = self.pending(store)
        self.assertNotIn(sir.OPERATION_NOTE_KEY, record["notes"])
        executor = scripted_executor({ids["y"]: [self.reintegration(), st.Completed()]})
        result = st.start(store, ids["y"], "single-work", executor, phase_review=phase_review())
        self.assertEqual(("completed", record["mutation_id"]), (result.status, result.mutation_id))
        new = self.new_integration(store, ids["integration"])
        self.assertIsNone(new.phase_review_contract, "a legacy operation is never upgraded")
        self.assertEqual([self.work_named(store, "Fix")], self.predecessors(store, new.id), "no reviewed closure")
        self.assertEqual(pi.MODE_LEGACY, pi.completion_mode(ProjectView.load(store), phase_id))

    def test_missing_reintegration_design_stops_before_the_incomplete_structure_is_written(self) -> None:
        """start.py (R23; §32.13 / §14.9): late Work in a reviewed Phase with no unfinished integration and no
        reintegration design STOPs ``reintegration_required`` before the derivation is recorded or anything of it
        registered. A reviewed Phase whose one unfinished integration is unmarked STOPs
        ``phase_integration_unmarked_unfinished`` (CPQ-06 kept) the same way."""
        store, phase_id, ids = self.project()
        works_before = sorted(ProjectView.load(store).works)
        executor = scripted_executor({ids["y"]: [st.Derive({"fix": st.DerivedWork("Fix", "fixed")})]})
        with self.assertRaises(StopError) as raised:
            st.start(store, ids["y"], "single-work", executor, phase_review=phase_review())
        self.assertEqual(sir.CODE_REINTEGRATION_REQUIRED, raised.exception.code)
        self.assertEqual(works_before, sorted(ProjectView.load(store).works))
        (record,) = self.pending(store)
        self.assertFalse([e for e in record["effects"] if ":derive" in e["stage"]], "no derivation stage recorded")

    def test_an_unmarked_unfinished_integration_in_a_reviewed_phase_stops_the_derivation(self) -> None:
        """CPQ-06 = keep the STOP: late Work is never wired onto the unmarked unfinished integration."""
        store, phase_id, ids = self.project()
        # a reviewed Phase whose one unfinished integration is unmarked: a legacy START's own reintegration
        st.start(store, ids["y"], "single-work", scripted_executor({ids["y"]: [self.reintegration(), st.Completed()]}))
        legacy_new = self.new_integration(store, ids["integration"])
        self.assertIsNone(legacy_new.phase_review_contract)
        late = st.Derive({"late": st.DerivedWork("Late", "late done")})
        fix = self.work_named(store, "Fix")
        works_before = sorted(ProjectView.load(store).works)
        with self.assertRaises(StopError) as raised:
            st.start(store, fix, "single-work", scripted_executor({fix: [late]}), phase_review=phase_review())
        self.assertEqual(sir.CODE_UNMARKED_UNFINISHED, raised.exception.code)
        self.assertEqual(works_before, sorted(ProjectView.load(store).works))

    def test_legacy_phase_reintegration_behaviour_unchanged(self) -> None:
        """start.py (R23) regression: a START without ``phase_review`` registers the reintegration it always did -
        unmarked, the derived Works' own edges only - and its record carries no semantics note."""
        store, phase_id, ids = self.project(marked=False)
        executor = scripted_executor({ids["y"]: [self.reintegration(), st.Completed()]})
        with crash_at(MutationController, "begin", after=True):
            with self.assertRaises(Crash):
                st.start(store, ids["y"], "single-work", executor)
        (record,) = self.pending(store)
        self.assertEqual(({"operation": "start", "work_id": ids["y"], "mode": "single-work"}, {}),
                         (record["invocation"], record["notes"]), "the legacy first save, exactly")
        result = st.start(store, ids["y"], "single-work", executor)
        self.assertEqual("completed", result.status)
        new = self.new_integration(store, ids["integration"])
        self.assertIsNone(new.phase_review_contract)
        self.assertEqual([self.work_named(store, "Fix")], self.predecessors(store, new.id))
        self.assertEqual([], validate_project(store))


class SemanticsNoteWindowTests(StartCase):
    """The CP note-window ruling (§32.4; CP rulings wave B §12; PSW-IRA OB1 (1), (2), (4)): a fresh ``phase_review``
    START binds ``phase_integration_semantics`` in its FIRST durable owner save, through ``controller.open(notes=)``,
    never by a later ``set_note``."""

    def test_a_crash_right_after_the_first_durable_save_resumes_reviewed(self) -> None:
        store, phase_id, ids = self.project(marked=False)  # a legacy Phase: only reviewed semantics mark
        executor = scripted_executor({ids["y"]: [self.reintegration(), st.Completed()]})
        with crash_at(MutationController, "begin", after=True):
            with self.assertRaises(Crash):
                st.start(store, ids["y"], "single-work", executor, phase_review=phase_review())
        (record,) = self.pending(store)
        self.assertEqual({sir.OPERATION_NOTE_KEY: V1}, record["notes"], "the note is in the first durable save")
        self.assertEqual({"operation": "start", "work_id": ids["y"], "mode": "single-work"}, record["invocation"],
                         "the selector is no part of the invocation")
        saved = yamlish.load(MutationController(store).intent_path(record["mutation_id"]).read_text(encoding="utf-8"))
        self.assertEqual(V1, saved["notes"][sir.OPERATION_NOTE_KEY])
        # resumed without the selector: reviewed semantics, so the reviewed integration is refused before it is
        # registered (§32.15) - nothing is upgraded or downgraded
        with self.assertRaises(StopError) as raised:
            st.start(store, ids["y"], "single-work", scripted_executor({ids["y"]: [self.reintegration()]}))
        self.assertEqual(sir.CODE_PHASE_REVIEW_REQUIRED, raised.exception.code)
        self.assertEqual([ids["integration"]], [w.id for w in ProjectView.load(store).works.values()
                                                if w.work_kind == pi.INTEGRATION_KIND])
        result = st.start(store, ids["y"], "single-work", scripted_executor({ids["y"]: [self.reintegration(),
                                                                                         st.Completed()]}),
                          phase_review=phase_review())
        self.assertEqual(("completed", record["mutation_id"]), (result.status, result.mutation_id))
        new = self.new_integration(store, ids["integration"])
        self.assertEqual(V1, new.phase_review_contract, "resumed as reviewed, never as legacy")
        self.assertEqual(sorted([ids["w1"], ids["y"], self.work_named(store, "Fix")]), self.predecessors(store, new.id))

    def test_the_note_is_bound_only_through_open(self) -> None:
        """No ``set_note`` of the semantics anywhere in START: the one binding is ``open(notes=...)``."""
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(st))
        found = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and getattr(node.func, "attr", None) == "set_note"
                 and any("OPERATION_NOTE_KEY" in ast.dump(arg) or "phase_integration_semantics" in ast.dump(arg)
                         for arg in node.args)]
        self.assertEqual([], found)
        opens = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and getattr(node.func, "attr", None) == "open" and getattr(node.func.value, "id", None) == "controller"]
        with_notes = [node for node in opens if any(keyword.arg == "notes" for keyword in node.keywords)]
        self.assertEqual(1, len(with_notes), "one START open binds notes; the standalone plan exclusion's binds none")
        self.assertEqual(["OWNER", "invocation"], [getattr(arg, "id", None) for arg in with_notes[0].args[:2]])

    def test_a_resumed_legacy_operation_never_reviews_a_marked_integration(self) -> None:
        """PSW-IRA OB1 (3): the pair (a resumed note-less record, a marked integration) never runs the Review under
        legacy semantics. A legacy outer START interrupted on the ordinary Work, re-invoked WITH ``phase_review``:
        it finishes the ordinary Work under legacy semantics and its continuation ends before the marked
        integration, completing - the integration is untouched."""
        store, phase_id, ids = self.project(completed=False, late=False)

        def interrupted(ctx):
            raise Crash("the process died while the executor ran")

        with self.assertRaises(Crash):
            st.start(store, ids["w1"], "outer", interrupted)
        (record,) = self.pending(store)
        self.assertNotIn(sir.OPERATION_NOTE_KEY, record["notes"])
        log: list[str] = []
        result = st.start(store, ids["w1"], "outer", completing_executor(store, log), phase_review=phase_review())
        self.assertEqual(("stopped", record["mutation_id"]), (result.status, result.mutation_id))
        self.assertIn("legacy Phase integration semantics", result.detail)
        self.assertEqual([ids["w1"]], log)
        view = ProjectView.load(store)
        self.assertEqual("completed", view.work_state(ids["w1"]).state)
        self.assertEqual([], view.events_for(ids["integration"]), "the marked integration is not touched")
        self.assertEqual([], self.pending(store), "the legacy operation completed")


if __name__ == "__main__":
    unittest.main()
