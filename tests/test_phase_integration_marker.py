"""RB5 §32.2 / §32.53: the Work marker - CREATE validates and persists the caller-decided value, nothing more.

Proven here against the live registration core (a real Project): the marker is written only
on a phase_integration_check Work, only with the exact supported value, read back unchanged by
the store's own entity rules, and a registration without it is byte-for-byte what it was.
The read-only ``Entity.phase_review_contract`` property (store.py) and structural validation of a
stored marker (validate.py) landed with the post-RB6 integration I-2 (rows R03 / R04) and are
proven in ``DeferredMarkerTests``; Roadmap / START marker injection and the replan decision
records that must bind the marker are still listed there as deferred.
"""

from __future__ import annotations

import ast
import dataclasses
from dataclasses import fields
from pathlib import Path
import unittest

from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from planning_helpers import Crash, PlanningTestCase, crash_at, design, plan, registered, run_ids
from rb5_doubles import DEFERRED, V1, ViewBuilder
from workline import phase_integration as pi
from workline import roadmap as rm
from workline import roadmap_review as rr
from workline import start as st
from workline.create import RelationSpec, WorkSpec, create_standalone_work, register_works
from workline.errors import ReconcileRequired, SpecViolation, StopError, ValidationError
from workline.mutation import MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import paths as review_paths, planning, serialize
from workline.review.store import ReviewStore
from workline.state import ProjectView
from workline.store import WORK_DESIRED_HEADING, Entity, ProjectStore, render_body, render_entity
from workline.validate import validate_project

SRC = Path(pi.__file__).resolve().parent


class MarkerRegistrationTests(WorklineTestCase):
    def registration(self):
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        phase_id = roadmap.phase_ids["a"]
        lock = project_operation(store, "rb5-marker-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        mutation = MutationController(store).open(
            "roadmap", {"operation": "phase-entry", "phase_id": phase_id}, WriteScope(entities=(phase_id,))
        )
        return store, roadmap.roadmap_id, phase_id, mutation

    def test_an_integration_carries_the_caller_decided_marker_and_reads_it_back(self) -> None:
        store, roadmap_id, phase_id, mutation = self.registration()
        spec = WorkSpec("Integration", "integrated", phase_id=phase_id, roadmap_id=roadmap_id,
                        work_kind="phase_integration_check", phase_review_contract=V1)
        result = register_works(mutation, "integration", {"integration": spec})
        work_id = result.work_ids["integration"]
        text = (store.root / ProjectStore.entity_rel_path("work", work_id)).read_text(encoding="utf-8")
        self.assertIn("work_kind: phase_integration_check\nphase_review_contract: phase-integration-review-v1\n", text)
        entity = ProjectView.load(store).works[work_id]
        self.assertEqual(V1, entity.meta[pi.PHASE_REVIEW_CONTRACT_KEY], "read back by the store's own entity rules")
        self.assertEqual("phase_integration_check", entity.work_kind)
        self.assertEqual([], validate_project(store))
        # the recorded stage, projected without being applied, reads the same marker
        projected = ProjectView.load(store).with_effects(mutation.stage_effects("integration"))
        self.assertEqual(V1, projected.works[work_id].meta[pi.PHASE_REVIEW_CONTRACT_KEY])

    def test_unsupported_or_misplaced_markers_are_refused_before_anything_is_written(self) -> None:
        store, roadmap_id, phase_id, mutation = self.registration()
        unsupported, misplaced = "unsupported phase_review_contract", "only for phase_integration_check Works"
        cases = {
            "unknown value": (dict(work_kind="phase_integration_check", phase_review_contract="phase-integration-review-v2"),
                              unsupported),
            "empty value": (dict(work_kind="phase_integration_check", phase_review_contract=""), unsupported),
            "not text": (dict(work_kind="phase_integration_check", phase_review_contract=["phase-integration-review-v1"]),
                         unsupported),
            "case variant": (dict(work_kind="phase_integration_check", phase_review_contract=V1.upper()), unsupported),
            "normal Work": (dict(phase_review_contract=V1), misplaced),
            "human_confirmation": (dict(work_kind="human_confirmation", phase_review_contract=V1), misplaced),
        }
        for index, (described, (extra, message)) in enumerate(cases.items()):
            with self.subTest(case=described), self.assertRaisesRegex(ValidationError, message):
                register_works(mutation, f"s{index}", {"w": WorkSpec("W", "d", phase_id=phase_id, roadmap_id=roadmap_id,
                                                                      **extra)})
        self.assertEqual({}, ProjectView.load(store).works)

    def test_an_unmarked_registration_is_byte_for_byte_the_legacy_one(self) -> None:
        store, roadmap_id, phase_id, mutation = self.registration()
        spec = WorkSpec("Integration", "integrated", phase_id=phase_id, roadmap_id=roadmap_id,
                        work_kind="phase_integration_check")
        work_id = register_works(mutation, "integration", {"integration": spec}).work_ids["integration"]
        meta = {"id": work_id, "display": "W-01", "type": "work", "phase_id": phase_id,
                "origin": {"type": "roadmap", "roadmap_id": roadmap_id, "phase_id": phase_id},
                "work_kind": "phase_integration_check"}
        expected = render_entity(meta, render_body("Integration", [(WORK_DESIRED_HEADING, "integrated")]))
        stored = (store.root / ProjectStore.entity_rel_path("work", work_id)).read_bytes()
        self.assertEqual(expected.encode("utf-8"), stored)
        self.assertNotIn(b"phase_review_contract", stored)

    def test_the_roadmap_phase_entry_still_registers_an_unmarked_legacy_integration(self) -> None:
        """OQ-A reading A (I-7): the legacy ``review=None`` Phase entry stays exactly what it was - unmarked, with its
        version 1 design identity (the P2 baseline pins the rest byte for byte)."""
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        entry = self.simple_entry(store, roadmap.phase_ids["a"], confirmation=True)
        view = ProjectView.load(store)
        for work in view.works.values():
            with self.subTest(work=work.name):
                self.assertNotIn(pi.PHASE_REVIEW_CONTRACT_KEY, work.meta)
        self.assertEqual(pi.MODE_LEGACY, pi.completion_mode(view, entry.phase_id))

    def test_legacy_start_completes_an_ordinary_work_without_any_review_selector(self) -> None:
        """§32.53 / §32.63 regression pin at this checkpoint: nothing in START reads the marker yet, so this pins only
        that ordinary Work completion is unchanged; the integrated assertion is DeferredMarkerTests'."""
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        entry = self.simple_entry(store, roadmap.phase_ids["a"])
        result = st.start(store, entry.work_ids["w1"], "single-work", completing_executor(store))
        self.assertEqual("completed", result.status)


class DirectCreateTests(WorklineTestCase):
    def test_direct_create_refuses_a_marker_before_the_lock(self) -> None:
        store = self.new_project()
        with self.assertRaises(SpecViolation):
            create_standalone_work(store, WorkSpec("Standalone", "d", phase_review_contract=V1))
        self.assertEqual([], sorted(store.mutations.glob("*.yaml")) if store.mutations.is_dir() else [])
        self.assertEqual({}, ProjectView.load(store).works)


class WorkSpecShapeTests(unittest.TestCase):
    def test_the_marker_is_an_optional_last_field_defaulting_to_none(self) -> None:
        names = [field.name for field in fields(WorkSpec)]
        self.assertEqual("phase_review_contract", names[-1])
        self.assertIsNone(WorkSpec("n", "d").phase_review_contract)
        self.assertEqual(WorkSpec("n", "d", None, None, None, None, (), None), WorkSpec("n", "d"),
                         "the existing positional form is unchanged")

    #: The production modules that may reach the marker, and how (RB5 integration; each entry names its row).
    MARKER_OWNERS = {
        ("start.py", "imports start_integration_review"),  # I-5 R21: the Phase integration entry gate
        ("roadmap.py", "phase_review_contract= keyword"),  # I-7 R29: the integration spec of a v2 design
        ("roadmap_review.py", "phase_review_contract= keyword"),  # I-7 R29: W / the freeze's stage inputs
        ("start.py", "phase_review_contract= keyword"),  # R28 (R-1): a cancel decision's recorded marker, rebuilt
        ("start.py", "marked_integration_spec"),  # I-6 R23: a reviewed derivation's reintegration
        ("start_review.py", "imports start_integration_review"),  # I-5 R20 / R21: the Run's Candidate and its gate
    }

    def test_only_the_named_owners_reach_the_marker(self) -> None:
        """CREATE never decides it; the Roadmap / START owners that do are named here (§32.3 / §32.4).

        Rewritten at the post-RB6 integration (row R21, playbook MC-4; was
        ``test_no_production_caller_passes_the_marker_yet``). Pinned on the call graph (RB5A-10), not on text:
        outside the module that defines the injection, exactly the owners in :attr:`MARKER_OWNERS` pass
        ``phase_review_contract=`` to a call, name ``marked_integration_spec``, or import
        ``start_integration_review`` - each in the way named there, and nothing else does.
        """
        found = []
        for path in sorted(SRC.rglob("*.py")):
            name = path.relative_to(SRC).as_posix()
            if name == "start_integration_review.py":
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and "phase_review_contract" in [k.arg for k in node.keywords]:
                    found.append((name, node.lineno, "phase_review_contract= keyword"))
                if isinstance(node, (ast.Name, ast.Attribute)) and                         getattr(node, "id", getattr(node, "attr", None)) == "marked_integration_spec":
                    found.append((name, node.lineno, "marked_integration_spec"))
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    imported = [alias.name for alias in node.names] + [getattr(node, "module", None) or ""]
                    if any(item.endswith("start_integration_review") for item in imported):
                        found.append((name, node.lineno, "imports start_integration_review"))
        self.assertEqual(self.MARKER_OWNERS, {(name, how) for name, _, how in found}, found)

    def test_the_marker_vocabulary_has_one_definition(self) -> None:
        """The exact contract value is a string constant in phase_integration.py alone (any quote style)."""
        for path in sorted(SRC.rglob("*.py")):
            if path.name == "phase_integration.py":
                continue
            constants = [node.value for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                         if isinstance(node, ast.Constant) and isinstance(node.value, str)]
            with self.subTest(module=path.name):
                self.assertNotIn(V1, constants)


class StartEntryGateTests(WorklineTestCase):
    """start.py (I-5, row R21, the gate half): a marked integration never runs START's ordinary executor path.

    §32.14 - §32.15, §14.27. The ``phase_review`` selector and the Phase Integration Review Run arrive with the rest
    of I-5; until then every START of a marked integration STOPs ``phase_review_required`` before any effect of its
    own, and every other Work - an unmarked integration included - runs exactly as before.
    """

    def marked_phase(self):
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        phase_id, roadmap_id = roadmap.phase_ids["a"], roadmap.roadmap_id
        with project_operation(store, "rb5-gate-fixture"):
            mutation = MutationController(store).open(
                "roadmap", {"operation": "phase-entry", "phase_id": phase_id}, WriteScope(entities=(phase_id,))
            )
            work_ids = register_works(mutation, "entry", {
                "w1": WorkSpec("W1", "done", phase_id=phase_id, roadmap_id=roadmap_id),
                "integration": WorkSpec("Integration", "integrated", phase_id=phase_id, roadmap_id=roadmap_id,
                                        work_kind="phase_integration_check", phase_review_contract=V1),
            }, [RelationSpec("requires_completion", "w1", "integration")]).work_ids
            mutation.complete()
        git(store.root, "add", "-A")
        git(store.root, "commit", "-q", "-m", "fixture: a phase-integration-review-v1 integration")
        return store, work_ids

    def state(self, store: ProjectStore) -> tuple:
        view = ProjectView.load(store)
        return (git(store.root, "rev-parse", "HEAD").strip(), [e.id for e in view.events],
                MutationController(store).list_pending())

    def test_a_marked_integration_stops_before_anything_is_written(self) -> None:
        store, work_ids = self.marked_phase()
        log: list[str] = []
        self.assertEqual("completed", st.start(store, work_ids["w1"], "single-work", completing_executor(store, log)).status)
        before = self.state(store)
        with self.assertRaises(StopError) as raised:
            st.start(store, work_ids["integration"], "single-work", completing_executor(store, log))
        self.assertEqual("phase_review_required", raised.exception.code)
        self.assertEqual([work_ids["w1"]], log, "the executor is never called for the marked integration")
        self.assertEqual(before, self.state(store), "no commit, no event, no intent record")
        self.assertEqual([], before[2])

    def test_outer_continuation_stops_at_the_marked_integration_after_the_ordinary_work(self) -> None:
        """Changed with R23 (the phase_review selector exists now): the outer continuation of a START without it ends
        before the marked integration - completing what it did, nothing of the integration - instead of STOPping
        with its own effects pending."""
        store, work_ids = self.marked_phase()
        log: list[str] = []
        result = st.start(store, work_ids["w1"], "outer", completing_executor(store, log))
        self.assertEqual("stopped", result.status)
        self.assertIn("needs the phase_review selector", result.detail)
        view = ProjectView.load(store)
        self.assertEqual([work_ids["w1"]], log)
        self.assertEqual("completed", view.work_state(work_ids["w1"]).state)
        self.assertEqual([], view.events_for(work_ids["integration"]), "no lifecycle effect of the integration")
        self.assertEqual([], MutationController(store).list_pending())


class DeferredMarkerTests(PlanningTestCase):
    def test_entity_exposes_phase_review_contract(self) -> None:
        """store.py (I-2, R03): read-only ``Entity.phase_review_contract`` - the RAW stored value (RB5A-03 / Q-1).

        ``None`` only when the key is absent; a present-but-empty, ``null`` or non-text marker comes back as stored,
        so it never reads as legacy. The property reads exactly the key ``phase_integration`` names.
        """
        def entity(**meta) -> Entity:
            return Entity("w_1", "work", {"id": "w_1", "type": "work", **meta}, "# W\n", ".workline/works/w_1.md")

        self.assertIsNone(entity().phase_review_contract)
        for value in (V1, "", None, [V1], V1.upper(), "phase-integration-review-v2", 1, False):
            with self.subTest(value=value):
                found = entity(**{pi.PHASE_REVIEW_CONTRACT_KEY: value}).phase_review_contract
                self.assertIs(type(value), type(found))
                self.assertEqual(value, found)
        self.assertIsNotNone(entity(**{pi.PHASE_REVIEW_CONTRACT_KEY: ""}).phase_review_contract,
                             "decided by presence, never by truthiness")
        with self.assertRaises(AttributeError):
            entity().phase_review_contract = V1  # type: ignore[misc]
        # read back from a real Project by the store's own entity rules
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        phase_id = roadmap.phase_ids["a"]
        with project_operation(store, "rb5-marker-property-test"):
            mutation = MutationController(store).open(
                "roadmap", {"operation": "phase-entry", "phase_id": phase_id}, WriteScope(entities=(phase_id,))
            )
            specs = {"w1": WorkSpec("W1", "done", phase_id=phase_id, roadmap_id=roadmap.roadmap_id),
                     "integration": WorkSpec("Integration", "integrated", phase_id=phase_id, roadmap_id=roadmap.roadmap_id,
                                             work_kind="phase_integration_check", phase_review_contract=V1)}
            work_ids = register_works(mutation, "entry", specs).work_ids
        view = ProjectView.load(store)
        self.assertEqual(V1, view.works[work_ids["integration"]].phase_review_contract)
        self.assertIsNone(view.works[work_ids["w1"]].phase_review_contract)

    def test_structural_validation_refuses_an_unsupported_or_misplaced_stored_marker(self) -> None:
        """validate.py (I-2, R04): marker only on phase_integration_check, exact supported value, present-but-empty fails.

        The files are written past CREATE (which refuses all of these before writing), as a manual edit would;
        structural validation reports each by key presence and repairs nothing.
        """
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        self.simple_entry(store, roadmap.phase_ids["a"], confirmation=True)
        self.assertEqual([], validate_project(store))
        by_kind = {work.work_kind: work for work in ProjectView.load(store).works.values()}
        integration, confirmation, normal = by_kind["phase_integration_check"], by_kind["human_confirmation"], by_kind[None]

        def unsupported(work, value) -> str:
            return f"{work.id}: unsupported phase_review_contract {value!r}"

        def misplaced(work) -> str:
            return f"{work.id}: phase_review_contract on non phase_integration_check Work"

        cases = {
            "unknown value": (integration, "phase-integration-review-v2", [unsupported(integration, "phase-integration-review-v2")]),
            "empty value": (integration, "", [unsupported(integration, "")]),
            "null value": (integration, None, [unsupported(integration, None)]),
            "not text": (integration, [V1], [unsupported(integration, [V1])]),
            "case variant": (integration, V1.upper(), [unsupported(integration, V1.upper())]),
            "normal Work": (normal, V1, [misplaced(normal)]),
            "human_confirmation": (confirmation, V1, [misplaced(confirmation)]),
            "misplaced and unsupported": (normal, "", [misplaced(normal), unsupported(normal, "")]),
            "the supported value on the integration": (integration, V1, []),
        }
        for described, (work, value, expected) in cases.items():
            path = store.root / ProjectStore.entity_rel_path("work", work.id)
            original = path.read_bytes()
            path.write_bytes(render_entity({**work.meta, pi.PHASE_REVIEW_CONTRACT_KEY: value}, work.body).encode("utf-8"))
            try:
                with self.subTest(case=described):
                    self.assertIn(pi.PHASE_REVIEW_CONTRACT_KEY, ProjectView.load(store).works[work.id].meta)
                    problems = validate_project(store)
                    self.assertEqual(expected, [p.message for p in problems if p.code == "work_invalid"])
                    self.assertEqual(len(expected), len(problems), problems)
            finally:
                path.write_bytes(original)
        self.assertEqual([], validate_project(store))

    def entries(self, store) -> list[dict]:
        return [r for r in self.pending(store) if r["invocation"].get("operation") == planning.OPERATION_PHASE_ENTRY]

    def crash_between_stages(self, store, phase_id, *, review: bool) -> dict:
        with crash_at(rm, "register_works", when=lambda n, mutation, stage, specs, relations: stage == "integration"):
            with self.assertRaises(Crash):
                if review:
                    self.reviewed_entry(store, phase_id)
                else:
                    rm.enter_phase(store, phase_id, design())
        (record,) = self.entries(store)
        return record

    def test_fresh_phase_entry_gets_the_marker(self) -> None:
        """roadmap.py / roadmap_review.py (I-7, R29; rulings OQ-A reading A, OQ-D option B).

        A review-v1 Phase entry is RB5-capable: it records the version 2 design identity, whose integration entry
        binds the Phase Review contract; the Candidate Review authorizes carries it; the integration Work it
        registers holds it; and the persisted-side normalization observes it (the working-tree round trip and the
        C-2 proofs of the registration would refuse otherwise). A ``review=None`` entry of the same Project stays
        legacy. Interrupted between stages, a fresh entry resumes as the version 2 plan it recorded.
        """
        store = self.planning_project()
        roadmap = rm.create_roadmap(store, plan())
        reviewed_phase, legacy_phase = roadmap.phase_ids["a"], roadmap.phase_ids["b"]
        identity = rm.design_identity(design(), version=rm.DESIGN_IDENTITY_VERSION)
        self.assertEqual((2, V1), (identity["version"], identity["integration"][pi.PHASE_REVIEW_CONTRACT_KEY]))
        self.assertEqual(rm.design_identity(design()), rm.design_identity(design(), version=1))
        self.assertNotIn(pi.PHASE_REVIEW_CONTRACT_KEY, rm.design_identity(design())["integration"])
        record = self.crash_between_stages(store, reviewed_phase, review=True)
        self.assertEqual(identity["version"], record["invocation"]["design"]["version"])
        self.assertEqual(V1, record["invocation"]["design"]["integration"][pi.PHASE_REVIEW_CONTRACT_KEY])
        result = self.reviewed_entry(store, reviewed_phase)
        self.assertEqual(("registered", record["mutation_id"]), (result.status, result.mutation_id))
        found = registered(store, result)
        integration = planning.candidate_content(found.material)["integration"]
        self.assertEqual(V1, integration[pi.PHASE_REVIEW_CONTRACT_KEY], "bound in the Candidate Review authorized")
        view = ProjectView.load(store)
        self.assertEqual(V1, view.works[integration["id"]].phase_review_contract)
        self.assertEqual([integration["id"]], sorted(w.id for w in view.works.values() if pi.PHASE_REVIEW_CONTRACT_KEY in w.meta))
        self.assertEqual(pi.MODE_REVIEWED, pi.completion_mode(view, reviewed_phase))
        self.assertEqual(pi.COVERAGE_MISSING, pi.coverage_status(view, reviewed_phase).status)
        self.simple_entry(store, legacy_phase, confirmation=True)
        view = ProjectView.load(store)
        self.assertEqual(pi.MODE_LEGACY, pi.completion_mode(view, legacy_phase))
        self.assertEqual([integration["id"]], sorted(w.id for w in view.works.values() if pi.PHASE_REVIEW_CONTRACT_KEY in w.meta))
        self.assertEqual([], validate_project(store))

    def test_pending_legacy_phase_entry_resumes_without_marker_injection(self) -> None:
        """roadmap.py (I-7, R29 (5)(b); rulings OQ-A / OQ-D; ruling OQ-D-R1 row A, surviving-runtime legacy): a
        pending pre-RB5 design is compared and resumed in the version it recorded, so it registers the unmarked
        integration it decided - never upgraded, never refused as another plan. Both pre-RB5 kinds: a review-v1 entry
        recorded by a build whose design identity was version 1, and a legacy ``review=None`` entry."""
        store = self.planning_project()
        roadmap = rm.create_roadmap(store, plan())
        reviewed_phase, legacy_phase = roadmap.phase_ids["a"], roadmap.phase_ids["b"]
        with mock.patch.object(rm, "DESIGN_IDENTITY_VERSION", rm.LEGACY_DESIGN_IDENTITY_VERSION):  # a pre-RB5 build
            record = self.crash_between_stages(store, reviewed_phase, review=True)
        self.assertEqual(1, record["invocation"]["design"]["version"])
        self.assertNotIn(pi.PHASE_REVIEW_CONTRACT_KEY, record["invocation"]["design"]["integration"])
        result = self.reviewed_entry(store, reviewed_phase)  # this build continues it
        self.assertEqual(("registered", record["mutation_id"]), (result.status, result.mutation_id))
        integration = planning.candidate_content(registered(store, result).material)["integration"]
        self.assertNotIn(pi.PHASE_REVIEW_CONTRACT_KEY, integration, "the old Candidate is not reinterpreted")
        record = self.crash_between_stages(store, legacy_phase, review=False)
        self.assertEqual(rm.design_identity(design()), record["invocation"]["design"])
        resumed = rm.enter_phase(store, legacy_phase, design())
        self.assertEqual(record["mutation_id"], resumed.mutation_id)
        view = ProjectView.load(store)
        self.assertEqual([], [w.id for w in view.works.values() if pi.PHASE_REVIEW_CONTRACT_KEY in w.meta])
        for phase_id in (reviewed_phase, legacy_phase):
            with self.subTest(phase=phase_id):
                self.assertEqual(pi.MODE_LEGACY, pi.completion_mode(view, phase_id))
        self.assertEqual([], self.entries(store))
        self.assertEqual([], validate_project(store))

    def test_replan_decisions_bind_or_refuse_a_marked_new_work(self) -> None:
        """ops.py / start.py (R28; Control Plane ruling R-1).

        A fresh replan request (Roadmap / START plan exclusion) and a START cancel decision positively bind a new
        Work's ``phase_review_contract`` - on every new Work entry, under a new record version - so the marker is
        part of what was decided; one without a marked Work keeps its version 1 shape exactly. A version 1 record is
        rebuilt without a marker (no injection): a recorded registration of a marked Work does not prove against it,
        so its resume fails closed. A record of the wrong shape for its version is never read as a decision. The
        projection of a replan reads the marked new integration as one.
        """
        from dataclasses import replace

        from rb5_doubles import ident
        from workline import ops
        from workline.create import _registration_effects

        b = ViewBuilder()
        phase = b.phase()
        plain = WorkSpec("Fix", "fixed", phase_id=phase, roadmap_id=b.roadmap_id)
        marked = WorkSpec("Reintegration", "integrated", phase_id=phase, roadmap_id=b.roadmap_id,
                          work_kind="phase_integration_check", phase_review_contract=V1)
        edge = (RelationSpec("requires_completion", "fix", "integration"),)
        legacy_replan = ops.Replan(new_works={"fix": plain})
        marked_replan = ops.Replan(new_works={"fix": plain, "integration": marked}, add_relations=edge)
        key = pi.PHASE_REVIEW_CONTRACT_KEY
        # the plan exclusion request
        legacy_request = ops._plan_exclusion_request(ident("w", 1), legacy_replan)
        self.assertEqual(1, legacy_request["version"])
        self.assertEqual([], [entry for entry in legacy_request["new_works"] if key in entry])
        request = ops._plan_exclusion_request(ident("w", 1), marked_replan)
        self.assertEqual(2, request["version"])
        self.assertEqual([None, V1], [entry[key] for entry in request["new_works"]])
        unmarked_alike = ops.Replan(new_works={"fix": plain, "integration": replace(marked, phase_review_contract=None)},
                                    add_relations=edge)
        self.assertNotEqual(request, ops._plan_exclusion_request(ident("w", 1), unmarked_alike),
                            "deciding the marker otherwise is another request")
        # the projection of a replan
        projected = ops.projected_view(b.view(), add_works={ident("w", 900): marked})
        self.assertEqual(V1, projected.works[ident("w", 900)].phase_review_contract)
        self.assertEqual(pi.MODE_REVIEWED, pi.completion_mode(projected, phase))
        # the START cancel decision
        decision = st._cancel_decision(ident("w", 1), "cancel", st.Cancel(marked_replan, "superseded"), [], "W-01")
        self.assertEqual(2, decision["version"])
        self.assertEqual([None, V1], [entry[key] for entry in decision["new_works"]])
        self.assertIsNone(st._decision_problem(decision))
        self.assertEqual(marked_replan.new_works, st._decided_replan(decision).new_works)
        legacy = st._cancel_decision(ident("w", 1), "cancel", st.Cancel(legacy_replan, "superseded"), [], "W-01")
        self.assertEqual(1, legacy["version"])
        self.assertEqual([], [entry for entry in legacy["new_works"] if key in entry])
        self.assertIsNone(st._decision_problem(legacy))
        self.assertIsNone(st._decided_replan(legacy).new_works["fix"].phase_review_contract)
        for described, broken in {
            "a version 1 entry holding the field": {**legacy, "new_works": [{**legacy["new_works"][0], key: V1}]},
            "a version 2 entry without it": {**decision, "new_works": [
                {name: value for name, value in entry.items() if name != key} for entry in decision["new_works"]]},
            "a marker that is not text": {**decision, "new_works": [decision["new_works"][0],
                                                                    {**decision["new_works"][1], key: [V1]}]},
            "an unknown version": {**decision, "version": 3},
        }.items():
            with self.subTest(case=described):
                self.assertIsNotNone(st._decision_problem(broken))
        # a version 1 record holds no marker: what it rebuilds never matches a recorded marked registration
        old = {**legacy, "new_works": [{name: value for name, value in entry.items() if name != key}
                                       for entry in decision["new_works"]]}
        self.assertIsNone(st._decision_problem(old))
        work_ids = {"fix": ident("w", 901), "integration": ident("w", 902)}
        displays = {"fix": "W-01", "integration": "W-02"}
        recorded = [{"kind": effect.kind, "payload": effect.payload}
                    for effect in _registration_effects(marked_replan.new_works, work_ids, [], {}, {}, displays)]
        self.assertTrue(ops._registration_matches(recorded, st._decided_replan(decision).new_works, work_ids, [], {}, {}))
        self.assertFalse(ops._registration_matches(recorded, st._decided_replan(old).new_works, work_ids, [], {}, {}),
                         "a version 1 record is not upgraded: its resume fails closed")

    def test_no_backfill_of_existing_integrations(self) -> None:
        """I-11 (R37; §14.2, §14.27, §32.5, §32.63): an existing unmarked integration stays legacy - entering, running
        and completing its Phase with the Phase Integration Review selector supplied runs it by the ordinary executor
        and never rewrites its Work file to opt it in; nothing gains a marker."""
        from helpers import completing_executor
        from rb5_run_helpers import phase_review

        store = self.planning_project()
        roadmap = rm.create_roadmap(store, plan())
        entry = self.simple_entry(store, roadmap.phase_ids["a"])
        integration = entry.integration_id
        before = (store.root / ProjectStore.entity_rel_path("work", integration)).read_bytes()
        log: list[str] = []
        result = st.start(store, entry.work_ids["w1"], "outer", completing_executor(store, log),
                          phase_review=phase_review())
        self.assertEqual("phase_complete", result.status)
        self.assertIn(integration, log, "the legacy integration ran by the ordinary executor")
        self.assertEqual(before, (store.root / ProjectStore.entity_rel_path("work", integration)).read_bytes())
        view = ProjectView.load(store)
        self.assertEqual([], [w.id for w in view.works.values() if pi.PHASE_REVIEW_CONTRACT_KEY in w.meta])
        self.assertEqual(pi.MODE_LEGACY, pi.completion_mode(view, roadmap.phase_ids["a"]))


#: A pre-RB5 build, as a test can stand one up: its Phase-entry design identity was version 1, and its implementation
#: (the planning Context's loader identity) was another - so after the RB5 landing its Runs are stale.
PRE_RB5_LOADER = serialize.digest({"implementation": "pre-RB5 build"})


class PhaseEntryV1PredecessorTests(PlanningTestCase):
    """CONTROL_PLANE_RULING_RB5_OQ_D_R1 = SET_ASIDE_V1_THEN_START_FRESH_V2 (CP rulings wave B §1 - §7), rows B - F.

    Row A (a surviving pre-RB5 runtime resumes its version 1 design, unmarked) is
    ``DeferredMarkerTests.test_pending_legacy_phase_entry_resumes_without_marker_injection``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()
        self.phase_id = rm.create_roadmap(self.store, plan()).phase_ids["a"]

    def lost_pre_rb5_run(self, *, stale: bool = True) -> str:
        """A pre-RB5 review-v1 Phase entry: G1 committed, then its process and its runtime owner record are lost."""
        before = set(run_ids(self.store))
        patches = [mock.patch.object(rm, "DESIGN_IDENTITY_VERSION", rm.LEGACY_DESIGN_IDENTITY_VERSION)]
        if stale:
            patches.append(mock.patch.object(planning, "loader_identity", return_value=PRE_RB5_LOADER))
        for patch in patches:
            patch.start()
        try:
            with crash_at(rr, "_launch_and_settle"):
                with self.assertRaises(Crash):
                    self.reviewed_entry(self.store, self.phase_id)
        finally:
            for patch in reversed(patches):
                patch.stop()
        self.runtime_gone(self.store)
        (run_id,) = set(run_ids(self.store)) - before
        return run_id

    def review_records(self) -> dict[str, bytes]:
        root = self.store.root / ".workline" / "review"
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def first_request(self, run_id: str) -> dict:
        review = ReviewStore(self.store)
        task_id = str(review.gate_chain(run_id).generations[0].accepted_tasks[0]["task_id"])
        return review.read_task_input(task_id).request_envelope

    def integration_of(self, result) -> str:
        return planning.candidate_content(registered(self.store, result).material)["integration"]["id"]

    def test_b_a_lost_v1_run_is_set_aside_as_stale_and_a_fresh_marked_v2_run_begins(self) -> None:
        """Row B, with row F: the old Run is positively rediscovered under its own version 1 identity, classified
        stale by the existing Planning currency, set aside canonically by the fresh version 2 Run's G1 request, and
        never reinterpreted; the integration that fresh Run registers is reviewed / marked."""
        old = self.lost_pre_rb5_run()
        old_material = planning.candidate_content(
            ReviewStore(self.store).read_candidate_snapshot(
                ReviewStore(self.store).gate_chain(old).generations[0].candidate_hash).material)
        self.assertNotIn(pi.PHASE_REVIEW_CONTRACT_KEY, old_material["integration"], "a version 1 Candidate")
        before = self.review_records()
        result = self.reviewed_entry(self.store, self.phase_id)
        self.assertEqual("registered", result.status)
        self.assertNotEqual(old, result.review_run_id)
        self.assertEqual({old, result.review_run_id}, set(run_ids(self.store)), "one fresh Run, nothing else")
        set_aside = self.first_request(result.review_run_id)["set_aside_runs"]
        self.assertEqual([old], [item["review_run_id"] for item in set_aside])
        self.assertEqual(planning.STALE_CONTEXT, set_aside[0]["reason"], "classified by the existing currency")
        view = ProjectView.load(self.store)
        self.assertEqual(V1, view.works[self.integration_of(result)].phase_review_contract)
        self.assertEqual(pi.MODE_REVIEWED, pi.completion_mode(view, self.phase_id))
        # row F: every record the old Run holds is byte for byte what it was; nothing is backfilled or converted
        after = self.review_records()
        self.assertEqual(before, {path: after.get(path) for path in before})
        self.assertNotIn(pi.PHASE_REVIEW_CONTRACT_KEY, planning.candidate_content(
            ReviewStore(self.store).read_candidate_snapshot(
                ReviewStore(self.store).gate_chain(old).generations[0].candidate_hash).material)["integration"])
        self.assertEqual([], validate_project(self.store))

    def test_c_no_old_run_is_an_ordinary_fresh_v2_run(self) -> None:
        result = self.reviewed_entry(self.store, self.phase_id)
        self.assertEqual("registered", result.status)
        self.assertEqual((result.review_run_id,), run_ids(self.store))
        self.assertEqual([], self.first_request(result.review_run_id)["set_aside_runs"])
        self.assertEqual(V1, ProjectView.load(self.store).works[self.integration_of(result)].phase_review_contract)

    def test_d_a_lost_v2_runtime_recovers_the_same_run(self) -> None:
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.reviewed_entry(self.store, self.phase_id)
        self.runtime_gone(self.store)
        (run_id,) = run_ids(self.store)
        with mock.patch.object(rr, "_v1_predecessor", side_effect=AssertionError("a version 2 Run exists")):
            result = self.reviewed_entry(self.store, self.phase_id)
        self.assertEqual(("registered", run_id), (result.status, result.review_run_id))
        self.assertEqual((run_id,), run_ids(self.store), "no duplicate version 2 Run")
        self.assertEqual(V1, ProjectView.load(self.store).works[self.integration_of(result)].phase_review_contract)

    def assert_fails_closed(self, reason: str) -> None:
        before_runs, before_records = run_ids(self.store), self.review_records()
        with self.assertRaises(ReconcileRequired) as raised:
            self.reviewed_entry(self.store, self.phase_id)
        self.assertEqual(reason, raised.exception.reason)
        self.assertEqual(before_runs, run_ids(self.store), "no version 2 Run is allocated")
        self.assertEqual(before_records, self.review_records())
        self.assertEqual([], self.pending(self.store), "no planning mutation is left")
        self.assertEqual({}, {w.id: w for w in ProjectView.load(self.store).works.values() if w.phase_id == self.phase_id})

    def test_e_several_v1_predecessors_fail_closed(self) -> None:
        base = self.head(self.store)
        git(self.store.root, "checkout", "-q", "-b", "first")
        self.lost_pre_rb5_run()
        git(self.store.root, "checkout", "-q", "-b", "second", base)
        self.lost_pre_rb5_run()
        git(self.store.root, "merge", "-q", "--no-edit", "first")
        self.assertEqual(2, len(run_ids(self.store)))
        self.assert_fails_closed("review_recovery_ambiguous")

    def test_e_a_v1_predecessor_still_recoverable_fails_closed(self) -> None:
        """Not safely classifiable: still current under this build, it is neither continued as version 1 nor set
        aside."""
        self.lost_pre_rb5_run(stale=False)
        self.assert_fails_closed("review_recovery_ambiguous")

    def test_e_a_malformed_v1_predecessor_fails_closed(self) -> None:
        """An unreadable record of the predecessor: the existing Review namespace check refuses before discovery."""
        old = self.lost_pre_rb5_run()
        task_id = str(ReviewStore(self.store).gate_chain(old).generations[0].accepted_tasks[0]["task_id"])
        (self.store.root / review_paths.task_input_rel(task_id)).write_bytes(b"not a task input\n")
        with self.assertRaises(StopError) as raised:
            self.reviewed_entry(self.store, self.phase_id)
        self.assertEqual("review_namespace_unreadable", raised.exception.code)
        self.assertEqual((old,), run_ids(self.store), "no version 2 Run is allocated")
        self.assertEqual([], self.pending(self.store))

    def test_e_a_v1_predecessor_this_build_cannot_reconstruct_fails_closed(self) -> None:
        """A canonical predecessor the existing machinery cannot classify (its Context names an adapter this build
        does not provide): the existing discovery's own incomplete classification fails closed."""
        kind = planning.KINDS[planning.KIND_PHASE_ENTRY]
        with mock.patch.dict(planning.KINDS, {planning.KIND_PHASE_ENTRY: dataclasses.replace(
                kind, adapter_identity="phase-entry-design-adapter-v0")}):
            self.lost_pre_rb5_run()
        self.assert_fails_closed("review_recovery_incomplete")


class PhaseEntryAdapterExtensionTests(unittest.TestCase):
    """Ruling OQ-D option B: ``PhaseEntryDesignAdapter``'s persisted-side normalization is extended conservatively and
    backwards-compatibly under its unchanged identity ``phase-entry-design-adapter-v1`` - the marker is projected
    exactly as ``confirmation_target`` is, only when the reviewed content or the entity holds it."""

    def normalized(self, *, reviewed_marker: bool, entity_marker: object = None, stored: bool = False):
        b = ViewBuilder()
        phase = b.phase()
        work = b.integration(phase, marker=entity_marker)
        if stored and entity_marker is None:
            b.works[work].meta[pi.PHASE_REVIEW_CONTRACT_KEY] = None  # stored ``null``: present, not absent
        entity = b.works[work]
        reviewed = {"id": work, "name": entity.name, "desired_state": "Integration done", "related": [],
                    "work_kind": pi.INTEGRATION_KIND}
        if reviewed_marker:
            reviewed[pi.PHASE_REVIEW_CONTRACT_KEY] = V1
        content = {"roadmap_id": b.roadmap_id, "phase_id": phase}
        return reviewed, rr.PhaseEntryDesignAdapter()._work(b.view(), reviewed, content)

    def test_a_v1_candidate_of_an_unmarked_entity_normalizes_as_it_always_did(self) -> None:
        reviewed, found = self.normalized(reviewed_marker=False)
        self.assertNotIn(pi.PHASE_REVIEW_CONTRACT_KEY, found)
        self.assertEqual(reviewed, found)
        self.assertEqual(planning.KINDS[planning.KIND_PHASE_ENTRY].adapter_identity,
                         rr.PhaseEntryDesignAdapter().adapter_identity(), "the adapter identity is unchanged")

    def test_a_v2_candidate_of_its_marked_entity_is_observed(self) -> None:
        reviewed, found = self.normalized(reviewed_marker=True, entity_marker=V1)
        self.assertEqual(V1, found[pi.PHASE_REVIEW_CONTRACT_KEY])
        self.assertEqual(reviewed, found)

    def test_the_marker_on_one_side_alone_is_a_mismatch(self) -> None:
        for described, arguments in {
            "v2 Candidate, unmarked entity": dict(reviewed_marker=True),
            "v2 Candidate, stored null": dict(reviewed_marker=True, stored=True),
            "v1 Candidate, marked entity": dict(reviewed_marker=False, entity_marker=V1),
            "v1 Candidate, stored null": dict(reviewed_marker=False, stored=True),
            "v2 Candidate, another value": dict(reviewed_marker=True, entity_marker="phase-integration-review-v2"),
        }.items():
            with self.subTest(case=described):
                reviewed, found = self.normalized(**arguments)
                self.assertIn(pi.PHASE_REVIEW_CONTRACT_KEY, found)
                self.assertNotEqual(reviewed, found)


if __name__ == "__main__":
    unittest.main()
