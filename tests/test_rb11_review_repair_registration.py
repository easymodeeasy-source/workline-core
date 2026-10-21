"""Sprint 41.31 (the RB11 contract amendment): real-flow tests and negative controls the formal review found missing.

RB11INT-EVID-1: "a real-flow test and a negative control for each unit, per refusing path for AM-H1".  Every test
here drives a production entry point (``rm.create_roadmap``, ``rm.enter_phase``, ``st.start``, ``create_standalone_work``,
``st.plan_exclude_standalone_work``, ``validate_project``); none of them stops at a helper.

Layout
    RegistrationKeyRefusalTests   AM-H1  one test per refusing path (direct CREATE, replan, START derivation, HumanNG
                                          fix / re-integration Work, reviewed route) + "only Roadmap-time registration
                                          writes the marker".
    DirtyOverlapTests             AM-D   dirty overlap over the PLANNED Work paths stops the creation before its first effect.
    DependencyResumeTests         AM-D / AM-E   an interrupted creation with phase_entries AND work_dependencies resumes.
    TableTSweep                   Table T / T-B15 sweep, units AM-D, AM-E, AM-F, AM-H1, AM-H2, AM-K.
    TableTReviewerAccessRows      Table T / T-B15 sweep, unit AM-I (needs the submodule fixture of the Lane B tests).

Table T rows covered (column: A = newly ACCEPTED input, R = newly REFUSED input / changed code, U = a similar input that
is NOT in the table and must stay as at the base):

    AM-D  A  a plan carrying phase_entries ............................ TableTSweep.test_am_d_*
    AM-D  R  phase_entries / work_dependencies on a reviewed route; an explicit ``entry``; a wrong shape
    AM-D  U  a plan without phase_entries (five-field result, no Works); a design without ``entry``
    AM-E  A  a plan carrying work_dependencies ........................ TableTSweep.test_am_e_*
    AM-E  R  work_dependencies without phase_entries; a dependency cycle
    AM-E  U  a legacy Phase relation cycle keeps its code; a Phase relation alone is accepted
    AM-F  A  enter_phase(store, phase_id) of a Roadmap-time registered Phase  TableTSweep.test_am_f_*
    AM-F  R  the same call for a Phase that does not qualify
    AM-F  U  a design for a legacy Phase still expands; a design for a registered Phase is still phase_already_expanded
    AM-H1 A  registration_key supplied by Roadmap-time registration only ...  TableTSweep.test_am_h1_* (+ RegistrationKeyRefusalTests)
    AM-H1 R  registration_key on any other path
    AM-H1 U  the same specification without the key is accepted on every path
    AM-H2 R  START of a marked, unstarted Work while a Phase prerequisite is unsatisfied (dependency_unsatisfied)
             ................................................................. TableTSweep.test_am_h2_*
    AM-H2 U  an unmarked Work of an ordinarily entered Phase; a marked Work that is in_progress
    AM-I  R  a START whose Review actor declares read_access and has a shortage ... TableTReviewerAccessRows
    AM-I  U  an actor without read_access; an actor whose allowance is sufficient
    AM-K  A  the new read-only operation independent_candidates ......... TableTSweep.test_am_k_*
    AM-K  U  it changes nothing on disk and refuses an inactive Roadmap as the existing checks do

Things that cannot be driven end to end here are marked ``NOT_VERIFIED`` (skipped with the reason, listed in the report).
"""

from __future__ import annotations

import dataclasses
from unittest import mock
import unittest

from helpers import WorklineTestCase, completing_executor
import test_laneb_reviewer_access as laneb
from test_roadmap_registered_works import Interrupted, design, plan
from test_review_p4_work import Adjudicator
from workline import gitcmd
from workline import reviewer_access as ra
from workline import roadmap as rm
from workline import start as st
from workline.create import RelationSpec, WorkSpec, create_standalone_work, validate_work_specs
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.mutation import MutationController
from workline.ops import Replan
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.state import ProjectView
from workline.store import ProjectStore
from workline.validate import validate_project

MARKER = "roadmap_registration"


def project_state(store: ProjectStore) -> dict:
    """Everything an operation could have written: the whole ``.workline`` tree except the runtime area, the Git HEAD
    and the pending mutations.  Two equal states mean nothing was written."""
    root = store.root / ".workline"
    tree = {
        path.relative_to(store.root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "runtime" not in path.relative_to(root).parts
    }
    return {
        "tree": tree,
        "head": gitcmd.head_commit(store.root),
        "pending": [record["mutation_id"] for record in MutationController(store).list_pending()],
    }


def markers(store: ProjectStore) -> dict[str, dict | None]:
    return {work.id: work.roadmap_registration for work in ProjectView.load(store).works.values()}


class RegistrationKeyRefusalTests(WorklineTestCase):
    """AM-H1 (RB11INT-EVID-1): a registration_key is refused before anything is written on every non-Roadmap path."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    # (a) direct CREATE ----------------------------------------------------------------------------------------
    def test_a_direct_create_refuses_the_key_and_the_same_spec_without_it_is_accepted(self) -> None:
        """AM-H1 (a) direct CREATE, RB11INT-EVID-1: refused with nothing written; the keyless control is accepted."""
        before = project_state(self.store)
        with self.assertRaises(ValidationError) as raised:
            create_standalone_work(self.store, WorkSpec("A", "a", registration_key="k"))
        self.assertIn("Roadmap-time registration", str(raised.exception))
        self.assertEqual(before, project_state(self.store))
        self.assertEqual({}, ProjectView.load(self.store).works)
        created = create_standalone_work(self.store, WorkSpec("A", "a"))
        self.assertIsNone(markers(self.store)[created.work_id])

    # (b) replan -----------------------------------------------------------------------------------------------
    def test_b_a_standalone_plan_exclusion_replan_refuses_the_key_and_registers_no_work(self) -> None:
        """AM-H1 (b) replan through START plan exclusion (standalone), RB11INT-EVID-1.

        The refusal is the registration core's.  As for every Work payload the core refuses (BL-027), the exclusion
        event itself is already applied when the replan is judged (observed: ``plan_excluded`` is in the log and the
        START record stays pending); what the refusal guarantees, and what is asserted, is that the replan registers
        nothing: no Work, no marker.  The strict reading "before anything is written" is reported, not asserted.
        """
        target = create_standalone_work(self.store, WorkSpec("Target", "target")).work_id
        before = ProjectView.load(self.store)
        carrying = Replan(new_works={"n": WorkSpec("N", "n", registration_key="k")})
        with self.assertRaises(ValidationError) as raised:
            st.plan_exclude_standalone_work(self.store, target, carrying)
        self.assertIn("Roadmap-time registration", str(raised.exception))
        after = ProjectView.load(self.store)
        self.assertEqual(set(before.works), set(after.works), "the replan registered no Work")
        self.assertEqual({None}, set(markers(self.store).values()))
        # positive control: the same replan without the key is accepted and registers the new Work, unmarked
        st.plan_exclude_standalone_work(self.store, target, Replan(new_works={"n": WorkSpec("N", "n")}))
        view = ProjectView.load(self.store)
        self.assertEqual({"Target", "N"}, {w.name for w in view.works.values()})
        self.assertEqual({None}, {w.roadmap_registration for w in view.works.values()})
        self.assertEqual([], MutationController(self.store).list_pending())
        self.assertEqual(validate_project(self.store), [])

    def _phase_cancel(self, registration_key: str | None):
        roadmap = self.simple_roadmap(self.store)
        rid, pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, pa, {"w1": "W1", "w2": "W2"})
        w1, i1 = entry.work_ids["w1"], entry.integration_id
        view = ProjectView.load(self.store)
        (rel,) = [r.id for r in view.roadmap_relations if (r.type, r.from_id, r.to) == ("requires_completion", w1, i1)]
        replan = Replan(
            remove_relation_ids=(rel,),
            add_relations=(RelationSpec("requires_completion", "007", i1),),
            new_works={"007": WorkSpec("置き換え R", "replaces W1", phase_id=pa, roadmap_id=rid,
                                       registration_key=registration_key)},
        )
        return w1, (lambda: st.start(self.store, w1, "single-work", lambda ctx: st.Cancel(replan, "superseded")))

    def test_b_a_start_cancel_replan_refuses_the_key_and_registers_no_work(self) -> None:
        """AM-H1 (b) replan through a START cancel, RB11INT-EVID-1.

        The refusal is the registration core's (``validation_failed``).  As for every Work payload the core refuses
        (BL-027, tests/test_cancel_decision_resume.py: "as before: refused once the cancel events were applied"), the
        cancel events of the target itself are already applied when the replan is judged; what the refusal guarantees,
        and what is asserted, is that the replan registers nothing: no new Work, no new relation, no marker.
        """
        w1, call = self._phase_cancel("k")
        before = ProjectView.load(self.store)
        with self.assertRaises(ValidationError) as raised:
            call()
        self.assertIn("Roadmap-time registration", str(raised.exception))
        after = ProjectView.load(self.store)
        self.assertEqual(set(before.works), set(after.works), "the replan registered no Work")
        self.assertEqual(sorted((r.type, r.from_id, r.to) for r in before.roadmap_relations),
                         sorted((r.type, r.from_id, r.to) for r in after.roadmap_relations), "and changed no relation")
        self.assertEqual({None}, set(markers(self.store).values()))

    def test_b_the_same_start_cancel_replan_without_the_key_is_accepted(self) -> None:
        """AM-H1 (b) positive control, RB11INT-EVID-1: only the key differs."""
        w1, call = self._phase_cancel(None)
        before = set(ProjectView.load(self.store).works)
        self.assertEqual("cancelled", call().status)
        view = ProjectView.load(self.store)
        (added,) = set(view.works) - before
        self.assertIsNone(view.works[added].roadmap_registration)
        self.assertEqual([], MutationController(self.store).list_pending())
        self.assertEqual(validate_project(self.store), [])

    # (c) START derivation -------------------------------------------------------------------------------------
    def test_c_a_start_derived_work_cannot_carry_the_key_even_from_a_marked_work(self) -> None:
        """AM-H1 (c): ``DerivedWork`` has no registration_key field; a derivation from a Roadmap-time registered Work
        writes an unmarked Work, RB11INT-EVID-1."""
        self.assertNotIn("registration_key", {f.name for f in dataclasses.fields(st.DerivedWork)})
        self.assertNotIn("registration_key", {f.name for f in dataclasses.fields(st.Derive)})
        with self.assertRaises(TypeError):
            st.DerivedWork("Fix", "fixed", registration_key="k")  # type: ignore[call-arg]
        result = rm.create_roadmap(self.store, plan())
        a1 = result.work_ids["a"]["a1"]
        marked_before = {w for w, m in markers(self.store).items() if m is not None}
        self.assertEqual(set(result.work_ids["a"].values()), marked_before & set(result.work_ids["a"].values()))
        outcomes = iter([st.Derive({"fix": st.DerivedWork("Fix", "fixed", derivation_detail="found a gap")}), None])

        def executor(ctx: st.ExecutionContext):
            outcome = next(outcomes, None)
            return outcome if outcome is not None else st.Completed()

        st.start(self.store, a1, "single-work", executor)
        view = ProjectView.load(self.store)
        (fix,) = [w for w in view.works.values() if w.name == "Fix"]
        self.assertIsNone(fix.roadmap_registration)
        self.assertEqual(marked_before, {w for w, m in markers(self.store).items() if m is not None})
        self.assertEqual(validate_project(self.store), [])

    # (d) HumanNG fix Work and re-integration (the integration fix Works START creates) ---------------------------
    def test_d_human_ng_fix_and_reintegration_works_never_carry_the_marker(self) -> None:
        """AM-H1 (d): the fix Work and the re-integration Work START creates for a Phase of Roadmap-time registered
        Works are built from ``DerivedWork`` (no caller-controlled key), so they are written without a marker,
        RB11INT-EVID-1.  Driven through the real HumanNG flow of a Roadmap-time registered Phase."""
        confirmed = dataclasses.replace(design("a1"), human_confirmation=rm.WorkDesign("Confirmation", "人間が確認した"))
        result = rm.create_roadmap(self.store, dataclasses.replace(plan(entries={}), phase_entries={"a": confirmed, "b": design("b1"), "c": design("c1")}))
        phase_a = result.phase_ids["a"]
        entry = rm.enter_phase(self.store, phase_a)
        self.assertFalse(entry.expanded)
        confirmation = entry.confirmation_id
        self.assertIsNotNone(confirmation)
        registered = set(markers(self.store))
        seen = {"ng": False}

        def executor(ctx: st.ExecutionContext):
            if ctx.work.id == confirmation and not seen["ng"]:
                seen["ng"] = True
                return st.HumanNG({"f1": st.DerivedWork("F1", "defect fixed")}, st.DerivedWork("I2", "re-integrated"))
            return st.Completed()

        self.assertEqual("phase_complete", st.start(self.store, entry.entry_work_id, "outer", executor).status)
        self.assertTrue(seen["ng"])
        view = ProjectView.load(self.store)
        created = {w.id: w for w in view.works.values() if w.id not in registered}
        self.assertEqual({"F1", "I2"}, {w.name for w in created.values()})
        self.assertEqual({None}, {w.roadmap_registration for w in created.values()})
        for work_id in registered:  # the registered Works keep their markers
            self.assertIsNotNone(view.works[work_id].roadmap_registration)
        self.assertEqual(validate_project(self.store), [])

    @unittest.skip(
        "NOT_VERIFIED: the Review-derived integration fix Works (start_review._integration_fix_works, a real P4 "
        "Phase Integration Review with a repair plan) are not driven end to end here; they are built from DerivedWork "
        "like the HumanNG ones tested above, which has no registration_key field"
    )
    def test_d_review_derived_integration_fix_works(self) -> None:
        """AM-H1 (d) via a real Phase Integration Review repair plan. NOT_VERIFIED, RB11INT-EVID-1."""

    # (e) the reviewed registration route ------------------------------------------------------------------------
    def test_e_the_reviewed_route_refuses_phase_entries_and_writes_nothing(self) -> None:
        """AM-H1 (e) / AM-D: a Roadmap that registers Works cannot take the reviewed route, so no reviewed route
        carries a registration_key; the same plan without ``review`` is accepted, RB11INT-EVID-1."""
        before = project_state(self.store)
        with mock.patch("workline.roadmap_review.require_entry_gate"):
            with self.assertRaises(ValidationError) as raised:
                rm.create_roadmap(self.store, plan(), review=object())
        self.assertIn("not yet available with a Planning Review", str(raised.exception))
        self.assertEqual(before, project_state(self.store))
        self.assertEqual([], MutationController(self.store).list_pending())
        result = rm.create_roadmap(self.store, plan())
        self.assertEqual({"a", "b", "c"}, set(result.work_ids))

    def test_e_the_reviewed_phase_entry_route_is_refused_for_a_registered_phase_and_has_no_key_to_carry(self) -> None:
        """AM-H1 (e): a reviewed (Planning Review) entry without a design is refused for a registered Phase before
        anything is written, and ``WorkDesign`` (what the reviewed route builds Works from) has no registration_key
        field, RB11INT-EVID-1."""
        self.assertNotIn("registration_key", {f.name for f in dataclasses.fields(rm.WorkDesign)})
        self.assertNotIn("registration_key", {f.name for f in dataclasses.fields(rm.PhaseEntryDesign)})
        result = rm.create_roadmap(self.store, plan())
        before = project_state(self.store)
        with self.assertRaises(ValidationError) as raised:
            rm.enter_phase(self.store, result.phase_ids["a"], review=object())
        self.assertIn("not available with a Planning Review", str(raised.exception))
        self.assertEqual(before, project_state(self.store))
        # the same call without review is the accepted AM-F entry
        self.assertFalse(rm.enter_phase(self.store, result.phase_ids["a"]).expanded)

    @unittest.skip(
        "NOT_VERIFIED: a full reviewed Planning Review run (roadmap_review / WorkDesign registration with a real "
        "PlanningReview and Reviewer) is not driven here; only its refusals and the absence of a key field are"
    )
    def test_e_a_complete_reviewed_registration(self) -> None:
        """AM-H1 (e) through a real Planning Review. NOT_VERIFIED, RB11INT-EVID-1."""

    # only Roadmap-time registration writes the marker -----------------------------------------------------------
    def test_only_roadmap_time_registration_writes_the_marker(self) -> None:
        """AM-H1: Works registered by ``rm.create_roadmap`` with phase_entries carry the marker; Works of every other
        path (standalone, ordinary Phase entry, START derivation, replan) never do, RB11INT-EVID-1."""
        result = rm.create_roadmap(self.store, plan())
        registered = {wid for keys in result.work_ids.values() for wid in keys.values()}
        view = ProjectView.load(self.store)
        integrations = {w.id for w in view.works.values() if w.work_kind == "phase_integration_check"}
        for work_id in registered | integrations:
            self.assertIsNotNone(view.works[work_id].roadmap_registration, work_id)
        ordinary = self.simple_roadmap(self.store, {"z": ("Phase Z", "Z が成立する")})
        entered = self.simple_entry(self.store, ordinary.phase_ids["z"], {"z1": "Z1"})
        standalone = create_standalone_work(self.store, WorkSpec("S", "s")).work_id
        target = create_standalone_work(self.store, WorkSpec("T", "t")).work_id
        st.plan_exclude_standalone_work(self.store, target, Replan(new_works={"r": WorkSpec("Repl", "r")}))
        st.start(self.store, standalone, "single-work",
                 lambda ctx: st.Derive({"fix": st.DerivedWork("Fix", "fixed")}) if ctx.work.name == "S" and not any(
                     w.name == "Fix" for w in ProjectView.load(self.store).works.values()) else st.Completed())
        view = ProjectView.load(self.store)
        written = [w for w in view.works.values() if w.id not in registered | integrations]
        self.assertGreaterEqual(len(written), 5)
        self.assertEqual({None}, {w.roadmap_registration for w in written})
        self.assertIn(entered.entry_work_id, {w.id for w in written})
        self.assertEqual(validate_project(self.store), [])

    def test_the_core_refuses_a_forged_key_on_a_spec_it_is_handed_and_accepts_it_without(self) -> None:
        """AM-H1: ``validate_work_specs`` (the check every registration meets) refuses a key not stamped by Roadmap-time
        registration; the keyless control passes.  A positive: a spec stamped by Roadmap-time registration is accepted,
        RB11INT-EVID-1."""
        result = rm.create_roadmap(self.store, plan())
        view = ProjectView.load(self.store)
        forged = WorkSpec("F", "f", phase_id=result.phase_ids["a"], roadmap_id=result.roadmap_id, registration_key="x")
        with self.assertRaises(ValidationError):
            validate_work_specs({"f": forged}, view)
        validate_work_specs({"f": dataclasses.replace(forged, registration_key=None)}, view)


class DirtyOverlapTests(WorklineTestCase):
    """AM-D (RB11INT-EVID-1): pre-existing uncommitted changes over a PLANNED Work path stop the creation first."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def _committed_relations_file(self) -> str:
        """A valid, committed ``relations/roadmap.yaml`` (a first Roadmap with a Phase relation wrote it)."""
        self.simple_roadmap(self.store, {"x": ("Phase X", "X が成立する"), "y": ("Phase Y", "Y が成立する")},
                            [("requires_completion", "x", "y")])
        rel = ".workline/relations/roadmap.yaml"
        self.assertTrue((self.store.root / rel).is_file())
        return rel

    def test_a_dirty_file_over_a_planned_work_path_stops_the_creation_before_its_first_effect(self) -> None:
        """AM-D: ``relations/roadmap.yaml`` has an uncommitted change from before the operation.  The second plan has
        no Phase relation, so only its PLANNED Work registration (the integration Work's requires_completion
        relations) writes that path; the creation stops with dirty_overlap before its first effect, RB11INT-EVID-1."""
        rel = self._committed_relations_file()
        path = self.store.root / rel
        with open(path, "a", encoding="utf-8", newline="") as handle:
            handle.write("\n")  # a person's own, still valid, uncommitted change
        persons = path.read_bytes()
        before = project_state(self.store)
        roadmaps_before = self.store.list_entities("roadmap")
        with self.assertRaises(StopError) as raised:
            rm.create_roadmap(self.store, plan())
        self.assertEqual("dirty_overlap", raised.exception.code, raised.exception)
        self.assertIn(rel, str(raised.exception))
        self.assertEqual([], MutationController(self.store).list_pending(), "no mutation left pending")
        self.assertEqual(roadmaps_before, self.store.list_entities("roadmap"), "no second Roadmap was created")
        self.assertEqual(before, project_state(self.store), "no Phase, no Work, no event, no commit")
        self.assertEqual(persons, path.read_bytes(), "the person's bytes are left alone")

    def test_negative_control_the_same_dirty_file_does_not_stop_a_plan_that_does_not_write_it(self) -> None:
        """AM-D negative control: the same uncommitted change does not stop a plan without phase_entries, which writes
        no relations file, so the refusal above is owed to the planned Work paths, RB11INT-EVID-1."""
        rel = self._committed_relations_file()
        with open(self.store.root / rel, "a", encoding="utf-8", newline="") as handle:
            handle.write("\n")
        legacy = self.simple_roadmap(self.store, {"p": ("Phase P", "P が成立する")})
        self.assertEqual(1, len(legacy.phase_ids))

    def test_negative_control_an_unrelated_dirty_file_does_not_stop_the_creation(self) -> None:
        """AM-D negative control: the same plan with an unrelated uncommitted file is registered, RB11INT-EVID-1."""
        (self.store.root / "notes.txt").write_text("unrelated\n", encoding="utf-8")
        result = rm.create_roadmap(self.store, plan())
        self.assertEqual({"a", "b", "c"}, set(result.work_ids))
        self.assertEqual("unrelated\n", (self.store.root / "notes.txt").read_text(encoding="utf-8"))
        self.assertEqual(validate_project(self.store), [])


class DependencyResumeTests(WorklineTestCase):
    """AM-D / AM-E (RB11INT-EVID-1): an interrupted creation with phase_entries AND work_dependencies resumes."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.plan = dataclasses.replace(
            plan(entries={"a": design("a1"), "b": design("b1"), "c": design("c1")}),
            work_dependencies=(rm.WorkDependency("a", "a1", "b", "b1"),),
        )

    def _interrupt_at(self, stage: str):
        real = rm.register_works
        calls = {"n": 0}

        def fire(mutation, name, specs, relations=(), **kw):
            if name == stage:
                calls["n"] += 1
                if calls["n"] == 1:
                    raise Interrupted(name)
            return real(mutation, name, specs, relations, **kw)

        return mock.patch.object(rm, "register_works", fire)

    def _resumes(self, stage: str) -> None:
        with self._interrupt_at(stage):
            with self.assertRaises(Interrupted):
                rm.create_roadmap(self.store, self.plan)
        (pending,) = MutationController(self.store).list_pending()
        recorded = [effect for effect in pending["effects"]]
        self.assertTrue(recorded, "some effects were recorded before the interruption")
        result = rm.create_roadmap(self.store, self.plan)
        self.assertTrue(result.resumed)
        view = ProjectView.load(self.store)
        self.assertEqual(1, len(view.roadmaps))
        self.assertEqual(6, len(view.works))
        a1, b1 = result.work_ids["a"]["a1"], result.work_ids["b"]["b1"]
        relations = [(r.type, r.from_id, r.to) for r in view.roadmap_relations]
        self.assertEqual(1, relations.count(("requires_completion", a1, b1)), "the Work dependency exists exactly once")
        self.assertEqual(len(relations), len(set(relations)), "no relation is duplicated")
        self.assertEqual([], MutationController(self.store).list_pending())
        self.assertEqual(validate_project(self.store), [])
        # and the dependency really holds b1 back until a1 is completed
        with self.assertRaises(StopError) as held:
            st.start(self.store, b1, "single-work", completing_executor(self.store))
        self.assertEqual("dependency_unsatisfied", held.exception.code)

    def test_interrupted_before_the_dependent_phase_is_registered_resumes_with_the_dependency_once(self) -> None:
        """AM-D / AM-E: interrupted right before the dependent Phase's Works stage, then the SAME call, RB11INT-EVID-1."""
        self._resumes("works@1")

    def test_interrupted_after_the_dependent_works_are_recorded_resumes_with_the_dependency_once(self) -> None:
        """AM-D / AM-E: interrupted after the dependent Phase's Works (and the dependency relation) are recorded,
        RB11INT-EVID-1."""
        self._resumes("integration@1")

    def test_a_different_plan_is_not_grafted_onto_the_unfinished_one(self) -> None:
        """AM-D / AM-E negative control: the same Roadmap name with another dependency is not the same request."""
        with self._interrupt_at("works@1"):
            with self.assertRaises(Interrupted):
                rm.create_roadmap(self.store, self.plan)
        other = dataclasses.replace(self.plan, work_dependencies=())
        with self.assertRaises(ReconcileRequired):
            rm.create_roadmap(self.store, other)
        self.assertTrue(rm.create_roadmap(self.store, self.plan).resumed)
        self.assertEqual(validate_project(self.store), [])


class TableTSweep(WorklineTestCase):
    """Table T / T-B15 sweep (RB11INT-EVID-1): every surviving row of AM-D, AM-E, AM-F, AM-H1, AM-H2 and AM-K, each with
    the input the table names and a similar input it does not name, which must behave as at the base."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def refused(self, call, error=ValidationError):
        before = project_state(self.store)
        with self.assertRaises(error) as raised:
            call()
        self.assertEqual(before, project_state(self.store), "refused before anything was written")
        return raised.exception

    # --- AM-D -----------------------------------------------------------------------------------------------
    def test_am_d_row_accepted_a_plan_carrying_phase_entries(self) -> None:
        """Table T AM-D (A): a plan with phase_entries is accepted; U: a plan without them keeps the five-field result
        and registers no Work, RB11INT-EVID-1."""
        result = rm.create_roadmap(self.store, plan())
        self.assertIs(type(result), rm.RegisteredRoadmapResult)
        self.assertEqual({"a", "b", "c"}, set(result.work_ids))
        self.assertEqual(validate_project(self.store), [])

    def test_am_d_unchanged_a_plan_without_phase_entries(self) -> None:
        """Table T AM-D (U), RB11INT-EVID-1."""
        legacy = self.simple_roadmap(self.store, {"a": ("A", "a")})
        self.assertIs(type(legacy), rm.RoadmapResult)
        self.assertEqual(["roadmap_id", "phase_ids", "mutation_id", "head", "resumed"], list(dataclasses.asdict(legacy)))
        self.assertEqual({}, ProjectView.load(self.store).works)

    def test_am_d_row_refused_reviewed_route_explicit_entry_and_wrong_shapes(self) -> None:
        """Table T AM-D (R): phase_entries / work_dependencies on a reviewed route, an explicit ``entry``, a value of
        the wrong shape are refused with a ValidationError and nothing is written; U: the same design without
        ``entry`` is accepted, RB11INT-EVID-1."""
        with mock.patch("workline.roadmap_review.require_entry_gate"):
            self.refused(lambda: rm.create_roadmap(self.store, plan(), review=object()))
            only_deps = dataclasses.replace(plan(entries={}), work_dependencies=(rm.WorkDependency("a", "a1", "b", "b1"),))
            self.assertIn("work_dependencies", str(self.refused(lambda: rm.create_roadmap(self.store, only_deps, review=object()))))
        explicit = plan(entries={"a": dataclasses.replace(design("a1"), entry="a1"), "b": design("b1"), "c": design("c1")})
        self.assertIn("explicit entry", str(self.refused(lambda: rm.create_roadmap(self.store, explicit))))
        for wrong in (
            dataclasses.replace(plan(), phase_entries=["a"]),
            dataclasses.replace(plan(), phase_entries={"a": "not a design"}),
            dataclasses.replace(plan(), phase_entries={1: design("a1")}),
            dataclasses.replace(plan(), work_dependencies="a1->b1"),
            dataclasses.replace(plan(), work_dependencies=(("a", "a1", "b", "b1"),)),
            dataclasses.replace(plan(), work_dependencies=(rm.WorkDependency("a", 1, "b", "b1"),)),
        ):
            self.refused(lambda wrong=wrong: rm.create_roadmap(self.store, wrong))
        self.refused(lambda: rm.create_roadmap(self.store, plan(entries={"zzz": design("a1")})))
        self.refused(lambda: rm.create_roadmap(self.store, plan(entries={"a": design("integration")})))
        self.assertEqual({"a", "b", "c"}, set(rm.create_roadmap(self.store, plan()).work_ids))

    # --- AM-E -----------------------------------------------------------------------------------------------
    def test_am_e_row_accepted_an_acyclic_plan_carrying_work_dependencies(self) -> None:
        """Table T AM-E (A): an acyclic work_dependencies plan is accepted and the dependency is a
        requires_completion from the predecessor Work; U: a Phase-level relation alone, RB11INT-EVID-1."""
        acyclic = dataclasses.replace(plan(), work_dependencies=(rm.WorkDependency("a", "a1", "b", "b1"),))
        result = rm.create_roadmap(self.store, acyclic)
        view = ProjectView.load(self.store)
        self.assertIn(("requires_completion", result.work_ids["a"]["a1"], result.work_ids["b"]["b1"]),
                      {(r.type, r.from_id, r.to) for r in view.roadmap_relations})
        self.assertEqual(validate_project(self.store), [])

    def test_am_e_row_refused_without_phase_entries_a_cycle_and_a_dependency_inside_one_phase(self) -> None:
        """Table T AM-E (R): work_dependencies without phase_entries; a cycle over Phase relations and dependencies;
        U: the cycle-free control plan is accepted afterwards, RB11INT-EVID-1."""
        bare = dataclasses.replace(plan(entries={}), work_dependencies=(rm.WorkDependency("a", "a1", "b", "b1"),))
        self.refused(lambda: rm.create_roadmap(self.store, bare))
        cyclic = dataclasses.replace(
            plan((("requires_completion", "a", "b"),)), work_dependencies=(rm.WorkDependency("b", "b1", "a", "a1"),)
        )
        self.assertIn("cycle", str(self.refused(lambda: rm.create_roadmap(self.store, cyclic))))
        two_way = dataclasses.replace(
            plan(), work_dependencies=(rm.WorkDependency("a", "a1", "b", "b1"), rm.WorkDependency("b", "b1", "a", "a1"))
        )
        self.assertIn("cycle", str(self.refused(lambda: rm.create_roadmap(self.store, two_way))))
        inside = dataclasses.replace(plan(), work_dependencies=(rm.WorkDependency("a", "a1", "a", "a1"),))
        self.refused(lambda: rm.create_roadmap(self.store, inside))
        unknown = dataclasses.replace(plan(), work_dependencies=(rm.WorkDependency("a", "nope", "b", "b1"),))
        self.refused(lambda: rm.create_roadmap(self.store, unknown))
        acyclic = dataclasses.replace(plan((("requires_completion", "a", "b"),)),
                                      work_dependencies=(rm.WorkDependency("a", "a1", "b", "b1"),))
        self.assertEqual({"a", "b", "c"}, set(rm.create_roadmap(self.store, acyclic).work_ids))

    def test_am_e_unchanged_legacy_phase_relation_cycle_keeps_its_base_refusal(self) -> None:
        """Table T AM-E (U): a legacy plan (no phase_entries, no work_dependencies) with a Phase relation cycle is
        refused exactly as at the base (postcheck_failed), not with the new cycle ValidationError, RB11INT-EVID-1."""
        legacy = plan((("requires_completion", "a", "b"), ("requires_completion", "b", "a")), entries={})
        with self.assertRaises(Exception) as raised:
            rm.create_roadmap(self.store, legacy)
        self.assertEqual("postcheck_failed", getattr(raised.exception, "code", None), raised.exception)
        self.assertEqual({}, ProjectView.load(self.store).roadmaps)

    # --- AM-F -----------------------------------------------------------------------------------------------
    def test_am_f_row_accepted_entry_without_a_design_of_a_registered_phase(self) -> None:
        """Table T AM-F (A): enter_phase(store, phase_id) for a Roadmap-time registered Phase succeeds, registers
        nothing (expanded False); U: a design for it is still phase_already_expanded, RB11INT-EVID-1."""
        result = rm.create_roadmap(self.store, plan())
        before = project_state(self.store)
        entry = rm.enter_phase(self.store, result.phase_ids["a"])
        self.assertFalse(entry.expanded)
        self.assertEqual(result.work_ids["a"], entry.work_ids)
        self.assertEqual(before, project_state(self.store), "persists nothing")
        with self.assertRaises(StopError) as raised:
            rm.enter_phase(self.store, result.phase_ids["a"], design("x"))
        self.assertEqual("phase_already_expanded", raised.exception.code)

    def test_am_f_row_refused_the_same_call_for_a_phase_that_does_not_qualify(self) -> None:
        """Table T AM-F (R): a legacy Phase (no marker), a held Phase and a blocked Phase are refused; U: a design for
        the legacy Phase still expands it (expanded True), RB11INT-EVID-1."""
        legacy = self.simple_roadmap(self.store, {"l": ("Phase L", "L が成立する")})
        self.refused(lambda: rm.enter_phase(self.store, legacy.phase_ids["l"]))
        registered = rm.create_roadmap(self.store, plan((("requires_completion", "a", "b"),)))
        rm.hold_phase(self.store, registered.phase_ids["c"])
        self.refused(lambda: rm.enter_phase(self.store, registered.phase_ids["c"]), Exception)
        blocked = self.refused(lambda: rm.enter_phase(self.store, registered.phase_ids["b"]), StopError)
        self.assertEqual("phase_blocked", blocked.code)
        self.refused(lambda: rm.enter_phase(self.store, "ph_unknown"))
        self.assertTrue(self.simple_entry(self.store, legacy.phase_ids["l"]).expanded)

    # --- AM-H1 ----------------------------------------------------------------------------------------------
    def test_am_h1_row_the_key_is_accepted_only_from_roadmap_time_registration(self) -> None:
        """Table T AM-H1 (A/R): the marker exists on Roadmap-time Works only; R: the key on a direct CREATE is refused;
        U: the same spec without the key is accepted, RB11INT-EVID-1."""
        result = rm.create_roadmap(self.store, plan())
        for work_id in (w for keys in result.work_ids.values() for w in keys.values()):
            self.assertIsNotNone(markers(self.store)[work_id])
        self.refused(lambda: create_standalone_work(self.store, WorkSpec("A", "a", registration_key="k")))
        plain = create_standalone_work(self.store, WorkSpec("A", "a")).work_id
        self.assertIsNone(markers(self.store)[plain])

    # --- AM-H2 ----------------------------------------------------------------------------------------------
    def test_am_h2_row_refused_start_of_a_marked_unstarted_work_with_an_unsatisfied_phase_prerequisite(self) -> None:
        """Table T AM-H2 (R): START of a marked, unstarted Work whose Phase prerequisite is unsatisfied stops with
        dependency_unsatisfied and starts nothing; U: after the prerequisite completes it starts, RB11INT-EVID-1."""
        result = rm.create_roadmap(self.store, plan((("requires_completion", "a", "b"),)))
        b1 = result.work_ids["b"]["b1"]
        before = project_state(self.store)
        with self.assertRaises(StopError) as raised:
            st.start(self.store, b1, "single-work", completing_executor(self.store))
        self.assertEqual("dependency_unsatisfied", raised.exception.code)
        self.assertEqual("unstarted", ProjectView.load(self.store).work_state(b1).state)
        self.assertEqual(before["tree"], project_state(self.store)["tree"])
        entry = rm.enter_phase(self.store, result.phase_ids["a"])
        st.start(self.store, entry.entry_work_id, "outer", completing_executor(self.store))
        self.assertEqual("completed", st.start(self.store, b1, "single-work", completing_executor(self.store)).status)

    def test_am_h2_unchanged_an_unmarked_work_of_an_ordinarily_entered_phase(self) -> None:
        """Table T AM-H2 (U): an unmarked Work of a Phase entered the ordinary way is not held by a prerequisite added
        later, RB11INT-EVID-1."""
        legacy = self.simple_roadmap(self.store, {"a": ("Phase A", "A が成立する")})
        work_id = rm.enter_phase(self.store, legacy.phase_ids["a"], design("a1")).work_ids["a1"]
        rm.add_phases(
            self.store, legacy.roadmap_id, {"z": PhaseSpec("Phase Z", "Z が成立する")},
            (PhaseRelationSpec("requires_completion", "z", legacy.phase_ids["a"]),),
        )
        view = ProjectView.load(self.store)
        self.assertTrue(view.unsatisfied_dependencies(legacy.phase_ids["a"]))
        self.assertIsNone(view.works[work_id].roadmap_registration)
        self.assertEqual("completed", st.start(self.store, work_id, "single-work", completing_executor(self.store)).status)

    def test_am_h2_unchanged_a_marked_work_that_is_in_progress_is_not_held(self) -> None:
        """Table T AM-H2 (U): a marked Work already in_progress is not held by a prerequisite added later (its
        started state is a fixture event, the predicate is the production one), RB11INT-EVID-1."""
        from status_helpers import append_events

        result = rm.create_roadmap(self.store, plan(entries={"a": design("a1", "a2"), "b": design("b1"), "c": design("c1")}))
        a1, a2 = result.work_ids["a"]["a1"], result.work_ids["a"]["a2"]
        rm.add_phases(
            self.store, result.roadmap_id, {"z": PhaseSpec("Phase Z", "Z が成立する")},
            (PhaseRelationSpec("requires_completion", "z", result.phase_ids["a"]),),
        )
        append_events(self.store, ("work_started", a1))
        view = ProjectView.load(self.store)
        self.assertEqual("in_progress", view.work_state(a1).state)
        self.assertEqual([], view.unsatisfied_dependencies(a1))
        self.assertTrue(view.unsatisfied_dependencies(a2))
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a2, "single-work", completing_executor(self.store))
        self.assertEqual("dependency_unsatisfied", raised.exception.code)

    # --- AM-K -----------------------------------------------------------------------------------------------
    def test_am_k_row_accepted_the_new_operation_changes_nothing_on_disk(self) -> None:
        """Table T AM-K (A): independent_candidates exists and is read-only: the whole ``.workline`` tree (runtime
        included) is byte-identical afterwards, no mutation, RB11INT-EVID-1."""
        result = rm.create_roadmap(self.store, plan((("requires_completion", "a", "b"),)))

        def whole_tree() -> dict[str, bytes]:
            root = self.store.root / ".workline"
            return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

        before, head = whole_tree(), gitcmd.head_commit(self.store.root)
        found = rm.independent_candidates(self.store, result.roadmap_id)
        self.assertEqual(before, whole_tree())
        self.assertEqual(head, gitcmd.head_commit(self.store.root))
        self.assertEqual([], MutationController(self.store).list_pending())
        self.assertIn(result.phase_ids["a"], found.phases)
        self.assertIn(result.phase_ids["b"], found.blocked)

    def test_am_k_unchanged_it_refuses_an_inactive_roadmap_as_the_existing_checks_do(self) -> None:
        """Table T AM-K (U): a held Roadmap, a cancelled Roadmap and an unknown Roadmap are refused with the same
        exception types and codes as the existing active-Roadmap check of Phase entry gives, RB11INT-EVID-1."""
        result = rm.create_roadmap(self.store, plan())
        phase = result.phase_ids["a"]
        rm.hold_roadmap(self.store, result.roadmap_id)
        held_candidates = self.refused(lambda: rm.independent_candidates(self.store, result.roadmap_id), StopError)
        held_entry = self.refused(lambda: rm.enter_phase(self.store, phase), StopError)
        self.assertEqual("roadmap_held", held_candidates.code)
        self.assertEqual(held_entry.code, held_candidates.code)
        rm.resume_roadmap(self.store, result.roadmap_id)
        self.assertTrue(rm.independent_candidates(self.store, result.roadmap_id).phases)
        rm.cancel_roadmap(self.store, result.roadmap_id)
        cancelled_candidates = self.refused(lambda: rm.independent_candidates(self.store, result.roadmap_id), Exception)
        cancelled_entry = self.refused(lambda: rm.enter_phase(self.store, phase), Exception)
        self.assertIs(type(cancelled_entry), type(cancelled_candidates))
        self.refused(lambda: rm.independent_candidates(self.store, "rm_unknown"))

    def test_am_k_unchanged_a_legacy_roadmap_is_listed_without_a_change(self) -> None:
        """Table T AM-K (U): a Roadmap that registered no Works is read as well, and nothing is written,
        RB11INT-EVID-1."""
        legacy = self.simple_roadmap(self.store, {"a": ("A", "a"), "b": ("B", "b")}, [("requires_completion", "a", "b")])
        before = project_state(self.store)
        found = rm.independent_candidates(self.store, legacy.roadmap_id)
        self.assertEqual(before, project_state(self.store))
        self.assertNotIn(legacy.phase_ids["b"], found.phases)


class AccessAdjudicator(Adjudicator):
    def __init__(self, allowance) -> None:
        super().__init__()
        self.read_access = allowance


class TableTReviewerAccessRows(laneb.SubmoduleProjectCase):
    """Table T / T-B15 sweep, unit AM-I (RB11INT-EVID-1): a START whose Review actor declares read_access and has a
    shortage stops with review_reviewer_access_insufficient before anything is begun; an actor that declares nothing,
    or whose allowance is sufficient, is unchanged.  Uses the real-submodule Project of tests/test_laneb_reviewer_access.py."""

    def assert_untouched_refusal(self, review, *needles: str) -> None:
        head = self.head()
        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", self.executor, review=review)
        self.assertEqual(ra.CODE_REVIEWER_ACCESS, raised.exception.code, raised.exception)
        for needle in needles:
            self.assertIn(needle, str(raised.exception))
        self.assertEqual(head, self.head(), "nothing was committed")
        self.assertEqual([], self.pending(), "no mutation was begun")
        self.assertEqual([], self.runs(), "no Review Run was begun")

    def test_am_i_row_refused_an_actor_that_lacks_a_read_form(self) -> None:
        """Table T AM-I (R): permission_denied; U: the sufficient allowance runs the Review, RB11INT-EVID-1."""
        weak = laneb.AccessActor(laneb.no_dash_c_allowance)
        self.assert_untouched_refusal(laneb.work_p4(weak), ra.PERMISSION_DENIED)
        self.assertEqual([], weak.tasks, "the actor was never launched")
        self.complete(self.executor, review=laneb.work_p4(laneb.AccessActor(laneb.read_only_allowance)))
        self.assertEqual([], self.problems())

    def test_am_i_row_refused_an_actor_that_allows_a_state_changing_form(self) -> None:
        """Table T AM-I (R): write_permitted is the same code, never a requirement question, RB11INT-EVID-1."""
        self.assert_untouched_refusal(laneb.work_p4(laneb.AccessActor(laneb.writing_allowance)), ra.WRITE_PERMITTED)

    def test_am_i_row_every_bound_actor_is_checked_not_only_the_discovery(self) -> None:
        """Table T AM-I (R): a weak adjudicator binding stops the START although the discovery actor is sufficient,
        RB11INT-EVID-1."""
        sufficient = laneb.AccessActor(laneb.read_only_allowance)
        self.assert_untouched_refusal(
            laneb.work_p4(sufficient, adjudicator=AccessAdjudicator(laneb.no_dash_c_allowance)), ra.PERMISSION_DENIED
        )
        self.assertEqual([], sufficient.tasks)

    def test_am_i_unchanged_an_actor_without_read_access_is_not_checked(self) -> None:
        """Table T AM-I (U): an actor exposing no read_access is not asked, RB11INT-EVID-1."""
        self.complete(self.executor, review=laneb.work_p4(laneb.Discovery()))
        self.assertEqual(1, len(self.runs()))

    def test_am_i_row_an_unreadable_gitlink_list_is_unknown_and_stops(self) -> None:
        """Table T AM-I (R): unknown is never available, RB11INT-EVID-1."""
        actor = laneb.AccessActor(laneb.read_only_allowance)
        real = ra.gitcmd.run_git

        def unreadable(root, *args, **kwargs):
            if args[:1] == ("ls-files",):
                return mock.Mock(ok=False, stdout="")
            return real(root, *args, **kwargs)

        with mock.patch.object(ra.gitcmd, "run_git", side_effect=unreadable):
            self.assert_untouched_refusal(laneb.work_p4(actor), ra.UNKNOWN)

    @unittest.skip(
        "NOT_VERIFIED: the review-v1 WorkReview reviewer (selector.reviewer with reviewer_identity) is covered by "
        "reviewer_access._bindings only; no review-v1 reviewer fixture is driven through st.start here"
    )
    def test_am_i_row_the_review_v1_reviewer_is_checked(self) -> None:
        """Table T AM-I (R) for the review-v1 reviewer. NOT_VERIFIED, RB11INT-EVID-1."""


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
