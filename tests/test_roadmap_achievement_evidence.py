"""RB5 §32.61: Roadmap achievement - the structured decision, H-2 preconditions, basis, evidence and event agreement.

Pure, apart from ``DeferredRoadmapTests``, which the post-RB6 integration (I-8) enabled on real Projects: the
specialized roadmap-achievement mutation (reservations, one recoverable stage of evidence + event, commit /
publication, read-back) and the startable-Phase gating.
"""

from __future__ import annotations

import dataclasses
import unittest

from rb5_doubles import ViewBuilder, ident, reviewed_phase
from rb5_run_helpers import IntegrationRunCase, phase_review
from test_phase_achievement import evidence_for, legacy_phase
from workline import achievement as ach
from workline import roadmap as rm
from workline.errors import ValidationError
from workline.review import serialize
from workline.store import ROADMAP_EVENTS, Event

EVENT = ident("evt", 42)
#: No open obligation, no unresolved HUMAN decision, and the owner's validation of the referenced Review / Human
#: Decision Evidence records found nothing wrong (RB5FB-1: that last input is required too).
NO_OPEN = dict(blocking_obligations=(), unresolved_human_decisions=(), reference_problems=())
DANGLING_RUN = ident("rr", 999)


def decision(judgement: str = ach.JUDGEMENT_ACHIEVED, refs: tuple[str, ...] = (), **extra) -> ach.RoadmapAchievementDecision:
    return ach.RoadmapAchievementDecision(judgement, "claude-opus", "5.5",
                                          "Every Phase objective holds and the Roadmap goal is met.", refs, **extra)


class Project:
    """One Roadmap: a reviewed Phase (with or without current evidence) and a legacy-complete Phase."""

    def __init__(self, *, with_evidence: bool = True, legacy: bool = True) -> None:
        self.b = ViewBuilder()
        self.reviewed, _, _, _ = reviewed_phase(self.b)
        self.evidence = [evidence_for(ach.phase_basis(self.b.view(), self.reviewed))] if with_evidence else []
        self.legacy = legacy_phase(self.b) if legacy else None

    def basis(self, **extra) -> ach.RoadmapBasis:
        return ach.roadmap_basis(self.b.view(), self.b.roadmap_id, self.evidence, **extra)

    def refs(self) -> tuple[str, ...]:
        return tuple(sorted(e.achievement_evidence_id for e in self.evidence))

    def achieve(self) -> Event:
        """Append the reserved roadmap_achieved event, as the applied stage leaves the committed state."""
        self.b.events.append(Event(EVENT, "roadmap_achieved", self.b.roadmap_id, "2026-10-06T00:00:00Z"))
        return self.b.events[-1]


class DecisionTests(unittest.TestCase):
    def test_judgement_vocabulary_maps_onto_the_existing_semantics(self) -> None:
        self.assertEqual(set(rm.JUDGEMENTS), set(ach.LEGACY_JUDGEMENTS))
        self.assertEqual(set(ach.JUDGEMENTS), set(ach.LEGACY_JUDGEMENTS.values()))
        self.assertEqual("human_confirmation_required", ach.structured_judgement("human_confirmation"))
        with self.assertRaises(ValidationError):
            ach.structured_judgement("done")

    def test_strict_decision(self) -> None:
        self.assertEqual([], decision().problems())
        self.assertTrue(decision("maybe").problems())
        self.assertTrue(ach.RoadmapAchievementDecision("achieved", "", "1", "r.").problems())
        self.assertTrue(decision(refs=("b", "a")).problems())
        self.assertTrue(decision(human_decision_ref="rr_00000000000000000000000001").problems())
        self.assertEqual([], decision(human_decision_ref=ident("rhd", 1)).problems())
        self.assertEqual(64, len(decision().digest))
        with self.assertRaises(ValidationError):
            decision("maybe").digest

    def test_only_achieved_records_an_event(self) -> None:
        self.assertTrue(decision().records_event)
        for judgement in ach.JUDGEMENTS[1:]:
            with self.subTest(judgement=judgement):
                self.assertFalse(decision(judgement).records_event)

    def test_the_legacy_string_is_for_legacy_only_roadmaps(self) -> None:
        """RB5C-L7 / §32.43."""
        reviewed = Project().basis()
        self.assertTrue(ach.decision_input_problems(reviewed, "achieved"))
        self.assertEqual([], ach.decision_input_problems(reviewed, "not_achieved"), "non-achieved stays read-only")
        self.assertEqual([], ach.decision_input_problems(reviewed, decision(refs=Project().refs())))
        legacy_only = ViewBuilder()
        legacy_phase(legacy_only)
        legacy_basis = ach.roadmap_basis(legacy_only.view(), legacy_only.roadmap_id, [])
        self.assertEqual([], ach.decision_input_problems(legacy_basis, "achieved"))
        self.assertTrue(ach.decision_input_problems(legacy_basis, "done"))
        self.assertTrue(ach.decision_input_problems(legacy_basis, object()))


class RoadmapBasisTests(unittest.TestCase):
    def test_reviewed_refs_are_current_and_legacy_facts_explicit(self) -> None:
        project = Project()
        basis = project.basis()
        self.assertTrue(basis.all_active_phases_complete)
        self.assertEqual((project.reviewed,), basis.reviewed_phase_ids)
        self.assertEqual(((project.reviewed, project.evidence[0].achievement_evidence_id, project.evidence[0].digest),),
                         basis.phase_evidence_refs, "the matched record's own body digest, never a supplied one")
        self.assertEqual(((project.legacy, True),), tuple((p, complete) for p, _, complete in basis.legacy_phase_facts))
        self.assertTrue(basis.requires_structured_decision)
        self.assertEqual((), basis.unready_phases)

    def test_the_basis_does_not_bind_the_lifecycle_its_own_event_changes(self) -> None:
        """RB5C-H1."""
        project = Project()
        before = project.basis()
        self.assertNotIn("roadmap_lifecycle", before.material)
        project.achieve()
        after = project.basis()
        self.assertEqual("achieved", after.roadmap_lifecycle)
        self.assertEqual(before.digest, after.digest)

    def test_legacy_only_roadmap_keeps_the_string_judgement(self) -> None:
        b = ViewBuilder()
        legacy_phase(b)
        basis = ach.roadmap_basis(b.view(), b.roadmap_id, [])
        self.assertFalse(basis.requires_structured_decision)
        self.assertEqual((), basis.phase_evidence_refs, "no Review history is invented for a legacy Phase")

    def test_missing_evidence_is_reported_as_an_evidence_obligation_not_lifecycle(self) -> None:
        project = Project(with_evidence=False)
        basis = project.basis()
        self.assertTrue(basis.all_active_phases_complete, "generated-complete")
        self.assertEqual(((project.reviewed, ach.EVIDENCE_MISSING),), basis.unready_phases)


class PreconditionTests(unittest.TestCase):
    def test_h2_achieved_needs_no_extra_human_step(self) -> None:
        project = Project()
        frozen = project.basis()
        self.assertEqual([], ach.achieved_precondition_problems(frozen, project.basis(), decision(refs=project.refs()),
                                                                **NO_OPEN))

    def test_a_migration_roadmap_closes_on_current_phase_evidence_alone(self) -> None:
        """RB8-FC-09 item 2: review_refs=() plus a decision citing exactly the current phase evidence suffices."""
        project = Project()
        basis = project.basis(review_refs=())
        self.assertEqual((), basis.review_refs)
        self.assertEqual([], ach.achieved_precondition_problems(basis, project.basis(review_refs=()),
                                                                decision(refs=project.refs()), **NO_OPEN))

    def test_blocking_and_human_inputs_are_required(self) -> None:
        """RB5C-L2: no default reads as "none"."""
        project = Project()
        basis = project.basis()
        with self.assertRaises(TypeError):
            ach.achieved_precondition_problems(basis, basis, decision(refs=project.refs()))  # type: ignore[call-arg]
        problems = ach.achieved_precondition_problems(basis, basis, decision(refs=project.refs()),
                                                      blocking_obligations=None,  # type: ignore[arg-type]
                                                      unresolved_human_decisions=(), reference_problems=())
        self.assertTrue(any("blocking_obligations is not established" in p for p in problems))

    def test_rb5fb1_referenced_review_and_human_decision_evidence_must_be_validated_by_the_owner(self) -> None:
        """RB5FB-1 / §32.44 "all referenced P5 evidence valid/current": review_refs and human_decision_ref are bound
        as given, so the owner's validation result over them is a required input - no default reads as "none"."""
        project = Project()
        human = ident("rhd", 7)
        basis = project.basis(review_refs=(DANGLING_RUN,), human_decision_ref=human)
        cites = decision(refs=tuple(sorted(project.refs() + (DANGLING_RUN,))), human_decision_ref=human)
        open_items = dict(blocking_obligations=(), unresolved_human_decisions=())
        with self.assertRaises(TypeError):
            ach.achieved_precondition_problems(basis, basis, cites, **open_items)  # type: ignore[call-arg]
        dangling = ach.achieved_precondition_problems(
            basis, basis, cites, **open_items,
            reference_problems=(f"review_refs entry {DANGLING_RUN}: no such Review Run",
                                f"human_decision_ref {human}: no such Human Decision Evidence"))
        self.assertEqual(2, sum("does not validate" in p for p in dangling), dangling)
        for unestablished in (None, "", "no such Review Run", b"x", {"problem"}):
            with self.subTest(reference_problems=unestablished):
                problems = ach.achieved_precondition_problems(
                    basis, basis, cites, **open_items, reference_problems=unestablished)  # type: ignore[arg-type]
                self.assertTrue(any("reference_problems is not established" in p for p in problems), problems)
        for valid_empty in ((), []):
            with self.subTest(reference_problems=valid_empty):
                self.assertEqual([], ach.achieved_precondition_problems(
                    basis, basis, cites, **open_items, reference_problems=valid_empty),
                    "a valid empty result: the owner proved every referenced record valid and current")

    def test_rb5fa1_an_unhashable_decision_ref_is_reported_never_raised(self) -> None:
        """RB5FA-1 sibling: the citable-set check runs over values a caller supplied; a malformed one is a problem."""
        project = Project()
        basis = project.basis()
        for refs in (([ident("rha", 1)],), ({"ref": "x"},), None, [ident("rha", 1)]):
            with self.subTest(refs=refs):
                given = ach.RoadmapAchievementDecision(ach.JUDGEMENT_ACHIEVED, "claude-opus", "5.5", "Rationale.",
                                                       refs)  # type: ignore[arg-type]
                self.assertTrue(ach.achieved_precondition_problems(basis, basis, given, **NO_OPEN))

    def test_each_mechanical_precondition(self) -> None:
        project = Project()
        frozen = project.basis()
        good = decision(refs=project.refs())
        cases = {
            "judgement": (decision(ach.JUDGEMENT_NOT_ACHIEVED, refs=project.refs()), {}, "records no achievement"),
            "uncited evidence": (decision(), {}, "does not cite current Phase evidence"),
            "unknown ref": (decision(refs=tuple(sorted(project.refs() + ("other-ref",)))), {}, "does not hold as valid"),
            "blocking": (good, {"blocking_obligations": ["review-run-x"]}, "blocking Review / achievement obligation"),
            "human": (good, {"unresolved_human_decisions": [ident("rhd", 4)]}, "unresolved HUMAN decision"),
            "human ref mismatch": (decision(refs=project.refs(), human_decision_ref=ident("rhd", 5)), {},
                                   "Human Decision Evidence reference"),
        }
        for described, (given, extra, expected) in cases.items():
            with self.subTest(case=described):
                problems = ach.achieved_precondition_problems(frozen, project.basis(), given, **{**NO_OPEN, **extra})
                self.assertTrue(any(expected in p for p in problems), problems)

    def test_a_basis_change_under_the_lock_refuses_achieved(self) -> None:
        project = Project()
        frozen = project.basis()
        project.b.work(project.reviewed, "Late")
        problems = ach.achieved_precondition_problems(frozen, project.basis(), decision(refs=project.refs()), **NO_OPEN)
        self.assertTrue(any("re-evaluate" in problem for problem in problems))
        self.assertTrue(any("not every active Phase" in problem for problem in problems))

    def test_a_non_active_roadmap_or_another_roadmap_refuses_achieved(self) -> None:
        project = Project()
        frozen = project.basis()
        project.b.event(project.b.roadmap_id, "roadmap_held")
        problems = ach.achieved_precondition_problems(frozen, project.basis(), decision(refs=project.refs()), **NO_OPEN)
        self.assertTrue(any("not active" in p for p in problems))
        other = dataclasses.replace(frozen, roadmap_id=ident("r", 999))
        self.assertTrue(any("another Roadmap" in p for p in ach.achieved_precondition_problems(
            other, frozen, decision(refs=project.refs()), **NO_OPEN)))

    def test_unready_reviewed_phase_blocks_achieved(self) -> None:
        project = Project(with_evidence=False)
        problems = ach.achieved_precondition_problems(project.basis(), project.basis(), decision(), **NO_OPEN)
        self.assertTrue(any("progression-ready" in problem for problem in problems))

    def test_an_isolated_structural_failure_blocks_achieved(self) -> None:
        """RB5C-L8: the only defect is an unrelated structural Problem in another Roadmap."""
        project = Project()
        other_roadmap = project.b.roadmap("Other")
        other_phase = project.b.phase("Other", roadmap_id=other_roadmap)
        project.b.integration(other_phase, marker=None)
        project.b.integration(other_phase, marker=None)
        current = project.basis()
        self.assertFalse(current.structural_validation_passed)
        problems = ach.achieved_precondition_problems(current, current, decision(refs=project.refs()), **NO_OPEN)
        self.assertTrue(any("structural validation does not pass" in p for p in problems))
        self.assertEqual(((project.reviewed, ach.EVIDENCE_STRUCTURE_INVALID),), current.unready_phases,
                         "reported as a structure failure, not as stale evidence")


class RoadmapEvidenceTests(unittest.TestCase):
    def built(self, project: Project, basis: ach.RoadmapBasis | None = None) -> ach.RoadmapAchievementEvidence:
        return ach.build_roadmap_achievement_evidence("test-roadmap-achievement-1", basis or project.basis(),
                                                      decision(refs=project.refs()), reserved_event_id=EVENT,
                                                      causing_mutation_id=ident("mut", 9))

    def test_event_and_evidence_read_back_against_the_committed_state(self) -> None:
        """RB5C-H1: the committed state holds the real roadmap_achieved event, and read-back still agrees."""
        project = Project()
        frozen = project.basis()
        evidence = self.built(project, frozen)
        self.assertEqual([], evidence.problems())
        self.assertEqual(evidence, ach.RoadmapAchievementEvidence.from_record(evidence.to_record()))
        event = project.achieve()
        committed = project.basis()
        self.assertEqual("achieved", project.b.view().roadmap_lifecycle(project.b.roadmap_id))
        self.assertEqual({"id", "type", "entity", "at"}, set(event.to_record()))
        self.assertEqual([], ach.event_evidence_problems(evidence, event))
        self.assertEqual([], ach.readback_problems(evidence, committed, event))
        self.assertIn("roadmap_achieved", ROADMAP_EVENTS)
        for wrong in (Event(ident("evt", 43), "roadmap_achieved", project.b.roadmap_id, "t"),
                      Event(EVENT, "roadmap_held", project.b.roadmap_id, "t"),
                      Event(EVENT, "roadmap_achieved", project.b.roadmap_id, "t", {"evidence": "x"})):
            with self.subTest(event=wrong.to_record()):
                self.assertTrue(ach.event_evidence_problems(evidence, wrong))

    def test_resume_after_the_stage_applied_reads_back_and_is_not_re_preconditioned(self) -> None:
        """RB5C-H1 resume shape: once the stage is applied the owner proves read-back, which passes."""
        project = Project()
        evidence = self.built(project)
        event = project.achieve()
        resumed = project.basis()
        self.assertEqual(evidence.roadmap_basis_digest, resumed.digest)
        self.assertEqual([], ach.readback_problems(evidence, resumed, event))

    def test_every_active_phase_bound_exactly_once(self) -> None:
        project = Project()
        record = self.built(project).to_record()
        record["legacy_phase_facts"] = []
        with self.assertRaises(ValidationError):
            ach.RoadmapAchievementEvidence.from_record(record)

    def test_legacy_facts_are_explicit_legacy_completion_facts(self) -> None:
        """RB5C-L1."""
        project = Project()
        record = self.built(project).to_record()
        self.assertEqual({"completion_mode": "legacy", "generated_complete": True},
                         {k: record["legacy_phase_facts"][0][k] for k in ("completion_mode", "generated_complete")})
        record["legacy_phase_facts"][0]["generated_complete"] = False
        with self.assertRaises(ValidationError):
            ach.RoadmapAchievementEvidence.from_record(record)

    def test_the_builder_refuses_a_basis_not_ready_for_achievement(self) -> None:
        """RB5C-L1: even without the precondition call, an incomplete legacy Phase is never certified."""
        incomplete = Project()
        legacy_incomplete = legacy_phase(incomplete.b, complete=False)
        self.assertIn(legacy_incomplete, incomplete.basis().active_phase_ids)
        with self.assertRaises(ValidationError):
            self.built(incomplete)
        with self.assertRaises(ValidationError):
            self.built(Project(with_evidence=False))

    def test_the_decision_digest_is_recomputed_from_the_persisted_decision(self) -> None:
        """RB5C-L3."""
        project = Project()
        record = self.built(project).to_record()
        self.assertEqual(list(project.refs()), record["decision_evidence_refs"])
        for mutate in (lambda r: r.update(decision_digest="f" * 64),
                       lambda r: r.update(decision_evidence_refs=[]),
                       lambda r: r.update(decision_evidence_refs=sorted(r["decision_evidence_refs"] + ["zz-unbound"]))):
            broken = dict(record)
            mutate(broken)
            with self.subTest(mutate=mutate), self.assertRaises(ValidationError):
                ach.RoadmapAchievementEvidence.from_record(broken)

    def test_rb5fa1_an_unhashable_or_unorderable_value_reads_as_review_record_invalid(self) -> None:
        """RB5FA-1 sibling reader: the citable set and the exactly-once binding run over stored values; a YAML
        sequence or mapping where an identity belongs is review_record_invalid, never a raw TypeError."""
        project = Project()
        record = self.built(project).to_record()
        self.assertTrue(record["legacy_phase_facts"], "the unorderable case needs a legacy fact beside a reviewed ref")

        def phase_ref(**fields):
            return lambda r: r.update(phase_evidence_refs=[{**r["phase_evidence_refs"][0], **fields}])

        mutations = {
            "list review_refs entry": lambda r: r.update(review_refs=[["rr-x"]]),
            "mapping review_refs entry": lambda r: r.update(review_refs=[{"ref": "rr-x"}]),
            "list decision_evidence_refs entry": lambda r: r.update(
                decision_evidence_refs=r["decision_evidence_refs"] + [["zz-unbound"]]),
            "list phase evidence ref ID": phase_ref(achievement_evidence_id=[record["phase_evidence_refs"][0][
                "achievement_evidence_id"]]),
            "list phase ID beside a legacy fact": phase_ref(phase_id=[project.reviewed]),
        }
        for described, mutate in mutations.items():
            with self.subTest(case=described):
                broken = serialize.canonical_data(record)
                mutate(broken)
                with self.assertRaises(ValidationError) as raised:
                    ach.RoadmapAchievementEvidence.from_record(broken)
                self.assertEqual("review_record_invalid", raised.exception.code)

    def test_non_achieved_judgements_create_no_evidence(self) -> None:
        project = Project()
        for judgement in ach.JUDGEMENTS[1:]:
            with self.subTest(judgement=judgement), self.assertRaises(ValidationError):
                ach.build_roadmap_achievement_evidence("test-x", project.basis(), decision(judgement),
                                                       reserved_event_id=ident("evt", 1),
                                                       causing_mutation_id=ident("mut", 1))

    def test_readback_detects_a_moved_basis(self) -> None:
        project = Project()
        evidence = self.built(project)
        event = project.achieve()
        project.b.work(project.reviewed, "Late")
        self.assertTrue(ach.readback_problems(evidence, project.basis(), event))


class OpenItemsOwnerTests(IntegrationRunCase):
    """§32.44 / §32.51: ``roadmap_review.unresolved_human_waits`` is the one owner of the Roadmap's unresolved Human
    decisions - structured, read-only - and ``achievement_open_items`` reads its HUMAN half from it, its prose and its
    blocking half unchanged."""

    def test_the_structured_owner_agrees_with_achievement_open_items(self) -> None:
        from planning_helpers import Crash, crash_at
        from rb5_run_helpers import Discovery, claim
        from workline import roadmap_review as rr
        from workline import start_review as sr
        from workline.errors import StopError
        from workline.review import p4
        from workline.review.store import ReviewStore
        from workline.state import ProjectView

        with self.subTest("an integration Run waiting on a Human decision"):
            store, phase_id, ids = self.marked_project("waiting")
            with self.assertRaises(StopError) as raised:
                self.integrate(store, ids["integration"], phase_review(Discovery(claim("human"))))
            self.assertEqual(p4.CODE_HUMAN_WAIT, raised.exception.code)
            (run_id,) = self.integration_runs(store, ids["integration"])
            view, roadmap_id = ProjectView.load(store), self.roadmap_of(store, phase_id)
            before = self.snapshot_state(store)
            self.assertEqual([(run_id, ids["integration"])], rr.unresolved_human_waits(ReviewStore(store), view, roadmap_id))
            self.assertEqual(([], [f"Review Run {run_id} waits on a Human requirement decision"]),
                             rr.achievement_open_items(store, view, roadmap_id, None))
            self.assertEqual(before, self.snapshot_state(store), "read-only")
        with self.subTest("an open Run is blocking, never a Human decision"):
            store, phase_id, ids = self.marked_project("open-run")
            with crash_at(sr, "_integration_launch"):
                with self.assertRaises(Crash):
                    self.integrate(store, ids["integration"], phase_review())
            (run_id,) = self.integration_runs(store, ids["integration"])
            view, roadmap_id = ProjectView.load(store), self.roadmap_of(store, phase_id)
            self.assertEqual([], rr.unresolved_human_waits(ReviewStore(store), view, roadmap_id))
            self.assertEqual(([f"Review Run {run_id} of {ids['integration']} is not final"], []),
                             rr.achievement_open_items(store, view, roadmap_id, None))
        with self.subTest("a completed integration leaves neither"):
            store, phase_id, ids = self.marked_project("settled")
            self.assertEqual("completed", self.integrate(store, ids["integration"], phase_review()).status)
            view, roadmap_id = ProjectView.load(store), self.roadmap_of(store, phase_id)
            self.assertEqual([], rr.unresolved_human_waits(ReviewStore(store), view, roadmap_id))
            self.assertEqual(([], []), rr.achievement_open_items(store, view, roadmap_id, None))


class DeferredRoadmapTests(IntegrationRunCase):
    """I-8 (R31 / R32) on real Projects: a reviewed Phase whose integration ran through START's Phase Integration
    Review (its evidence written by the terminal stage), and the Roadmap owner's progression gate and achieved path."""

    def reviewed_roadmap(self, name: str = "proj", **fixture):
        from workline.review.store import ReviewStore

        store, phase_id, ids = self.marked_project(name, **fixture)
        self.assertEqual("completed", self.integrate(store, ids["integration"], phase_review()).status)
        (evidence,) = ReviewStore(store).phase_completion_evidence()
        return store, self.roadmap_of(store, phase_id), phase_id, ids, evidence

    def achieved_events(self, store, roadmap_id: str) -> list:
        from workline.state import ProjectView

        return [e for e in ProjectView.load(store).events_for(roadmap_id) if e.type == "roadmap_achieved"]

    def roadmap_records(self, store) -> list:
        from workline.review.store import ReviewStore

        review = ReviewStore(store)
        return [review.read_achievement(found).evidence for found in review.achievement_ids()
                if review.read_achievement(found).kind == ach.KIND_ROADMAP_ACHIEVEMENT]

    def test_evaluate_achievement_accepts_the_structured_decision(self) -> None:
        """roadmap.py (I-8, R32; §32.43, §32.48): a legacy-only Roadmap keeps the legacy string judgement exactly; a
        Roadmap containing a reviewed Phase refuses ``"achieved"`` as a string, reports every other structured
        judgement read-only (nothing written), and records ``achieved`` from the structured decision citing the
        Phase's current evidence."""
        from helpers import completing_executor
        from workline import start as st
        from workline.mutation import MutationController

        legacy = self.planning_project("legacy")
        roadmap = self.simple_roadmap(legacy)
        entry = self.simple_entry(legacy, roadmap.phase_ids["a"])
        self.assertEqual("phase_complete",
                         st.start(legacy, entry.work_ids["w1"], "outer", completing_executor(legacy)).status)
        self.assertEqual("achieved", rm.evaluate_achievement(legacy, roadmap.roadmap_id, "achieved").status)
        self.assertEqual([], self.roadmap_records(legacy), "the legacy path writes no evidence")

        store, roadmap_id, phase_id, ids, evidence = self.reviewed_roadmap()
        with self.assertRaises(ValidationError):
            rm.evaluate_achievement(store, roadmap_id, "achieved")
        for judgement in (ach.JUDGEMENT_NOT_ACHIEVED, ach.JUDGEMENT_HUMAN_CONFIRMATION_REQUIRED,
                          ach.JUDGEMENT_DESIRED_STATE_CHANGE_REQUIRED):
            with self.subTest(judgement=judgement):
                self.assertEqual(judgement, rm.evaluate_achievement(store, roadmap_id, decision(judgement)).status)
        self.assertEqual(([], []), (self.achieved_events(store, roadmap_id), self.roadmap_records(store)))
        result = rm.evaluate_achievement(store, roadmap_id, decision(refs=(evidence.achievement_evidence_id,)))
        self.assertEqual("achieved", result.status)
        (event,) = self.achieved_events(store, roadmap_id)
        (record,) = self.roadmap_records(store)
        self.assertEqual((event.id, roadmap_id, result.mutation_id, ((phase_id, evidence.achievement_evidence_id,
                                                                       evidence.digest),)),
                         (record.reserved_event_id, record.roadmap_id, record.causing_mutation_id,
                          record.phase_evidence_refs))
        self.assertEqual([], MutationController(store).list_pending())

    def test_event_and_evidence_are_one_recoverable_stage(self) -> None:
        """roadmap.py (I-8, R32; §32.46): the reserved roadmap_achieved event and the roadmap_achievement record that
        references it are ONE recorded stage; interrupted after it is applied and before its commit, the same
        decision finishes it - one event, one record, the same IDs - and reads it back from the commit."""
        from planning_helpers import Crash, crash_at
        from workline.mutation import MutationController

        store, roadmap_id, _, _, evidence = self.reviewed_roadmap()
        chosen = decision(refs=(evidence.achievement_evidence_id,))
        with crash_at(rm, "_finalize"):
            with self.assertRaises(Crash):
                rm.evaluate_achievement(store, roadmap_id, chosen)
        (pending,) = MutationController(store).list_pending()
        stage = [effect for effect in pending["effects"] if effect["stage"] == "achievement"]
        self.assertEqual(["append_event", "create_file"], [effect["kind"] for effect in stage])
        reserved_event = stage[0]["payload"]["record"]["id"]
        self.assertEqual(reserved_event, pending["reserved_ids"]["achievement:event:0"])
        self.assertEqual("achieved", rm.evaluate_achievement(store, roadmap_id, chosen).status)
        (event,) = self.achieved_events(store, roadmap_id)
        (record,) = self.roadmap_records(store)
        self.assertEqual((reserved_event, pending["reserved_ids"]["achievement:achievement"]),
                         (event.id, record.achievement_evidence_id))
        self.assertEqual(reserved_event, record.reserved_event_id)
        self.assertEqual([], MutationController(store).list_pending())

    def test_roadmap_refuses_to_progress_past_a_reviewed_complete_phase_with_missing_evidence(self) -> None:
        """roadmap.py (I-8, R31; §32.41 - §32.42): with reviewed Phase a complete and its evidence never written, the
        Phase that requires it is held back (startable_phases, select_phase, an explicit choice) and the diagnosis
        names a's evidence obligation rather than lifecycle; with its evidence, b is selected. Achieved is refused
        (not ready) while an obligation is open."""
        from unittest import mock

        from workline.errors import SpecViolation

        store, phase_id, ids = self.marked_project(next_phase=True)
        roadmap_id = self.roadmap_of(store, phase_id)
        with mock.patch.object(ach, "phase_completion_evidence_for", return_value=None):
            self.assertEqual("completed", self.integrate(store, ids["integration"], phase_review()).status)
        self.assertEqual([], rm.startable_phases(store, roadmap_id))
        self.assertIsNone(rm.select_phase(store, roadmap_id))
        diagnosis = rm.diagnose_no_candidate(store, roadmap_id)
        self.assertIn(phase_id, diagnosis)
        self.assertIn("progression-ready", diagnosis)
        b = [p for p in ProjectViewLoad(store).roadmap_phases(roadmap_id) if p.id != phase_id][0]
        with self.assertRaises(SpecViolation):
            rm.select_phase(store, roadmap_id, explicit=b.id)

        other, roadmap_two, phase_two, _ids, _evidence = self.reviewed_roadmap("ready", next_phase=True)
        b_two = [p for p in ProjectViewLoad(other).roadmap_phases(roadmap_two) if p.id != phase_two][0]
        self.assertEqual(b_two.id, rm.select_phase(other, roadmap_two).id)

    def test_roadmap_achievement_interruption_matrix(self) -> None:
        """§32.62 items 22 - 28 (I-8, R32): interrupted at the decision freeze (nothing durable), after the event /
        evidence ID reservations, with one effect of the stage applied, after the commit, the same decision finishes
        with the SAME reserved IDs, one roadmap_achieved event and one roadmap_achievement record; a read-back that
        does not agree is reconcile required, and nothing replaces the record."""
        from planning_helpers import Crash, crash_at
        from unittest import mock
        from workline import gitops
        from workline.errors import ReconcileRequired
        from workline.mutation import MutationController as Controller

        def evidence_create(n, controller, record) -> bool:
            return record["kind"] == "create_file" and "/history/achievements/" in record["payload"]["path"]

        points = (("decision freeze", rm, "_open", False, None),
                  ("reservations", ach, "build_roadmap_achievement_evidence", False, None),
                  ("one effect applied", Controller, "apply_effect", False, evidence_create),
                  ("commit", gitops, "finalize", True, None))
        for name, target, attribute, after, when in points:
            with self.subTest(point=name):
                store, roadmap_id, _, _, evidence = self.reviewed_roadmap(name.replace(" ", "-"))
                chosen = decision(refs=(evidence.achievement_evidence_id,))
                with crash_at(target, attribute, after=after, when=when):
                    with self.assertRaises(Crash):
                        rm.evaluate_achievement(store, roadmap_id, chosen)
                before = Controller(store).list_pending()
                reserved = dict(before[0]["reserved_ids"]) if before else {}
                self.assertEqual("achieved", rm.evaluate_achievement(store, roadmap_id, chosen).status)
                (event,) = self.achieved_events(store, roadmap_id)
                (record,) = self.roadmap_records(store)
                if "achievement:event:0" in reserved:
                    self.assertEqual(reserved["achievement:event:0"], event.id)
                if "achievement:achievement" in reserved:
                    self.assertEqual(reserved["achievement:achievement"], record.achievement_evidence_id)
                self.assertEqual([], Controller(store).list_pending())
        with self.subTest(point="postcommit proof"):
            store, roadmap_id, _, _, evidence = self.reviewed_roadmap("readback")
            with mock.patch.object(ach, "readback_problems", return_value=["the committed basis differs"]):
                with self.assertRaises(ReconcileRequired) as raised:
                    rm.evaluate_achievement(store, roadmap_id, decision(refs=(evidence.achievement_evidence_id,)))
            self.assertEqual("review_achievement_basis_mismatch", raised.exception.reason)
            self.assertEqual(1, len(self.roadmap_records(store)), "nothing replaces the record")

    def test_the_achieved_path_validates_the_referenced_review_and_human_decision_evidence(self) -> None:
        """roadmap.py / roadmap_review.py (I-8, R32; RB5FB-1, §32.44): before anything is written, every Review
        reference the decision cites beyond the Phase evidence must name a valid canonical record - a Review Run with
        a validating P5 summary - and its Human Decision Evidence reference a stored, validating record; otherwise
        nothing is recorded. A valid reference is bound in the record."""
        from workline import ids as id_kinds
        from workline.errors import StopError
        from workline.mutation import MutationController

        store, roadmap_id, phase_id, ids, evidence = self.reviewed_roadmap()
        phase_ref = evidence.achievement_evidence_id
        for name, chosen in (
            ("an unknown Review Run", decision(refs=tuple(sorted((phase_ref, id_kinds.new_id("review_run")))))),
            ("a missing Human Decision Evidence", decision(refs=(phase_ref,),
                                                           human_decision_ref=id_kinds.new_id("review_decision"))),
        ):
            with self.subTest(name):
                with self.assertRaises(StopError) as raised:
                    rm.evaluate_achievement(store, roadmap_id, chosen)
                self.assertEqual("achievement_not_ready", raised.exception.code)
                self.assertEqual(([], []), (self.achieved_events(store, roadmap_id), self.roadmap_records(store)))
                self.assertEqual([], MutationController(store).list_pending())
        (run_id,) = self.integration_runs(store, ids["integration"])
        result = rm.evaluate_achievement(store, roadmap_id, decision(refs=tuple(sorted((phase_ref, run_id)))))
        self.assertEqual("achieved", result.status)
        (record,) = self.roadmap_records(store)
        self.assertEqual((run_id,), record.review_refs)


def ProjectViewLoad(store):  # noqa: N802 - a small reader for the rows above
    from workline.state import ProjectView

    return ProjectView.load(store)

if __name__ == "__main__":
    unittest.main()
