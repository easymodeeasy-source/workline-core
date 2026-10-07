"""RB5 §32.59 / §32.60: Phase basis, phase_completion evidence, current-basis matching, progression decision.

All pure, apart from the ``DeferredAchievementTests`` the post-RB6 integration enabled: two with the
shared-surface writer's I-1 / I-3 (the ``review_achievement`` ID kind and the ``history/achievements``
record), and the integration terminal completion's evidence with START's Phase Integration Review (I-5) on a
real Project. The other owner hooks and ``phase_progression_ready`` in the owners are still deferred there. Fixtures name evidence by reserved ``rha_`` IDs (MC-16): the history record requires
the kind, the body checks a public-safe label.
"""

from __future__ import annotations

import dataclasses
import unittest

import tempfile
from pathlib import Path

from helpers import git, rmtree
from rb5_doubles import DEFERRED, ViewBuilder, ident, reviewed_phase
from rb5_run_helpers import IntegrationRunCase
from workline import achievement as ach
from workline import ids
from workline import phase_integration as pi
from workline.errors import ValidationError
from workline.review import achievement_reader, history, paths
from workline.review import integration as ri, serialize
from workline.review.store import ReviewStore
from workline.review.validate import review_problems
from workline.state import ProjectView
from workline.store import ProjectStore, Relation
from workline.validate import validate_project

DIGEST = "d" * 64
CANDIDATE, RUN, RECEIPT, CONSUMPTION, SUMMARY = ("1" * 64, "2" * 64, "3" * 64, "4" * 64, "5" * 64)


def run_ref(basis: ach.PhaseBasis, number: int = 1, integration: str | None = None) -> ach.IntegrationRunRef:
    return ach.IntegrationRunRef(integration or basis.covering_integration_ids[0], ident("rr", number), CANDIDATE, RUN,
                                 ident("rcp", number), RECEIPT, ident("rcs", number), CONSUMPTION, SUMMARY)


def judged(basis: ach.PhaseBasis, kind: str = ri.OBJECTIVELY_SATISFIED, digest: str | None = None) -> ri.PhaseOutcome:
    return ri.PhaseOutcome(kind, digest or str(basis.phase_desired_state_digest), "The Phase objective holds.")


def evidence_for(basis: ach.PhaseBasis, number: int = 1, *, outcome: str = ri.OBJECTIVELY_SATISFIED,
                 integration: str | None = None, work_review_refs=()) -> ach.PhaseCompletionEvidence:
    integration = integration or basis.covering_integration_ids[0]
    return ach.build_phase_completion_evidence(
        ident("rha", number), basis,
        covering_integration_id=integration, integration_review=run_ref(basis, number, integration),
        phase_outcome=judged(basis, outcome), work_review_refs=work_review_refs,
        evaluators=[("adjudicator", "claude-opus", "5.5"), ("discovery", "reviewer-a", "1")],
        rationale="Every effective Work is integrated and the Phase objective holds.",
        causing_mutation_id=ident("mut", number), causing_operation="start",
        causing_event_ids=[ident("evt", 900 + number)],
    )


def legacy_phase(b: ViewBuilder, *, complete: bool = True) -> str:
    phase = b.phase("Legacy")
    work, integration = b.work(phase), b.integration(phase, marker=None)
    b.requires(work, integration)
    if complete:
        b.complete(work, integration)
    return phase


class PhaseBasisTests(unittest.TestCase):
    def test_basis_binds_the_structural_truth(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, confirmation = reviewed_phase(b, confirmation=True)
        basis = ach.phase_basis(b.view(), phase)
        self.assertEqual((pi.MODE_REVIEWED, True, True), (basis.completion_mode, basis.generated_complete,
                                                          basis.structural_validation_passed))
        self.assertEqual((integration,), basis.covering_integration_ids)
        self.assertEqual(tuple(sorted(normal + [integration, confirmation])), basis.effective_work_ids)
        self.assertEqual(ach.PASS_VALIDATION_DIGEST, basis.structural_validation_digest)
        completed = [e.id for e in b.view().events_for(confirmation) if e.type == "work_completed"]
        self.assertEqual([{"work_id": confirmation, "completed_event_id": completed[0]}],
                         basis.downstream_confirmations(integration))

    def test_evidence_never_changes_the_basis(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        before = ach.phase_basis(b.view(), phase)
        evidence_for(before)  # building evidence reads the basis and writes nothing into it
        b.event(b.roadmap_id, "roadmap_achieved")
        self.assertEqual(before.digest, ach.phase_basis(b.view(), phase).digest, "not even the Roadmap's own event")

    def test_the_same_structure_gives_the_same_digest_and_a_projection_equals_the_applied_state(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        b.complete(*normal)
        b.start(integration)
        before = b.view()
        completed = ident("evt", 777)
        projected = before.with_effects([{"kind": "append_event",
                                          "payload": {"record": {"id": completed, "type": "work_completed",
                                                                 "entity": integration, "at": "2026-10-06T00:00:01Z"}}}])
        b.events.append(projected.events[-1])
        self.assertEqual(ach.phase_basis(projected, phase).digest, ach.phase_basis(b.view(), phase).digest)
        self.assertTrue(ach.phase_basis(projected, phase).generated_complete)

    def test_relation_ids_do_not_change_the_basis_but_edges_do(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b)
        before = ach.phase_basis(b.view(), phase).digest
        edge = next(r for r in b.relations if r.from_id == normal[0] and r.to == integration)
        b.relations[b.relations.index(edge)] = Relation(ident("rel", 555), edge.type, edge.from_id, edge.to)
        self.assertEqual(before, ach.phase_basis(b.view(), phase).digest)
        b.work(phase, "Late")
        self.assertNotEqual(before, ach.phase_basis(b.view(), phase).digest)

    def test_legacy_basis(self) -> None:
        b = ViewBuilder()
        phase = legacy_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        self.assertEqual((pi.MODE_LEGACY, True, ()), (basis.completion_mode, basis.generated_complete,
                                                      basis.covering_integration_ids))


class PhaseEvidenceTests(unittest.TestCase):
    def test_reviewed_generated_completion_builds_strict_evidence(self) -> None:
        b = ViewBuilder()
        phase, _, integration, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        evidence = evidence_for(basis)
        self.assertEqual([], evidence.problems())
        self.assertEqual([], ach.phase_evidence_basis_problems(evidence, basis))
        self.assertEqual(basis.digest, evidence.basis_digest)
        self.assertEqual(integration, evidence.covering_integration_id)
        self.assertEqual(judged(basis).digest, evidence.phase_outcome_digest)
        self.assertEqual(evidence, ach.PhaseCompletionEvidence.from_record(evidence.to_record()))

    def test_no_work_review_history_is_required(self) -> None:
        """RB8-FC-09 item 1: work_review_refs=() builds valid evidence - nothing is backfilled."""
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        evidence = evidence_for(ach.phase_basis(b.view(), phase), work_review_refs=())
        self.assertEqual((), evidence.work_review_refs)
        self.assertEqual([], evidence.problems())

    def test_the_downstream_confirmation_case(self) -> None:
        b = ViewBuilder()
        phase, _, _, confirmation = reviewed_phase(b, confirmation=True)
        basis = ach.phase_basis(b.view(), phase)
        evidence = evidence_for(basis, outcome=ri.HUMAN_CONFIRMATION_REQUIRED)
        self.assertEqual(confirmation, evidence.downstream_confirmations[0][0])

    def test_the_judged_objective_must_be_the_current_objective(self) -> None:
        """RB5C-M2: an outcome judged on another Phase desired state never becomes evidence."""
        b = ViewBuilder()
        phase, _, integration, _ = reviewed_phase(b, confirmation=True)
        basis = ach.phase_basis(b.view(), phase)
        with self.assertRaises(ValidationError):
            ach.build_phase_completion_evidence(
                ident("rha", 99), basis, covering_integration_id=integration,
                integration_review=run_ref(basis), phase_outcome=judged(basis, ri.HUMAN_CONFIRMATION_REQUIRED, "f" * 64),
                evaluators=[("a", "b", "c")], rationale="r.", causing_mutation_id=ident("mut", 1),
                causing_operation="start")
        with self.assertRaises(ValidationError):
            ach.build_phase_completion_evidence(
                ident("rha", 99), basis, covering_integration_id=integration, integration_review=run_ref(basis),
                phase_outcome=ri.HUMAN_CONFIRMATION_REQUIRED, evaluators=[("a", "b", "c")], rationale="r.",
                causing_mutation_id=ident("mut", 1), causing_operation="start")

    def test_legacy_incomplete_or_uncovered_bases_build_no_evidence(self) -> None:
        legacy = ViewBuilder()
        phase = legacy_phase(legacy)
        incomplete = ViewBuilder()
        incomplete_phase, _, _, _ = reviewed_phase(incomplete, complete=False)
        for builder, phase_id in ((legacy, phase), (incomplete, incomplete_phase)):
            basis = ach.phase_basis(builder.view(), phase_id)
            with self.subTest(phase=phase_id), self.assertRaises(ValidationError):
                ach.build_phase_completion_evidence(
                    ident("rha", 99), basis, covering_integration_id=ident("w", 1),
                    integration_review=ach.IntegrationRunRef(ident("w", 1), ident("rr", 1), CANDIDATE, RUN,
                                                             ident("rcp", 1), RECEIPT, ident("rcs", 1), CONSUMPTION,
                                                             SUMMARY),
                    phase_outcome=ri.PhaseOutcome(ri.OBJECTIVELY_SATISFIED, DIGEST, "r."),
                    evaluators=[("a", "b", "c")], rationale="r.", causing_mutation_id=ident("mut", 1),
                    causing_operation="start")

    def test_non_authorizing_outcomes_and_unmodeled_confirmation_are_refused(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        for outcome in (ri.NOT_SATISFIED, ri.DESIRED_STATE_CHANGE_REQUIRED, ri.HUMAN_CONFIRMATION_REQUIRED):
            with self.subTest(outcome=outcome), self.assertRaises(ValidationError):
                evidence_for(basis, outcome=outcome)

    def test_cpq05a_four_distinct_digests_and_a_separate_run_summary_reference(self) -> None:
        """Ruling CPQ-05A: Candidate / terminal-Gate Run / Receipt / Consumption digests, and the P5 Run summary apart."""
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        evidence = evidence_for(ach.phase_basis(b.view(), phase))
        review = evidence.to_record()["integration_review"]
        self.assertEqual((CANDIDATE, RUN, RECEIPT, CONSUMPTION, SUMMARY),
                         (review["candidate_hash"], review["run_digest"], review["receipt_digest"],
                          review["consumption_digest"], review["run_summary_digest"]))
        summary_as_run = dataclasses.replace(evidence.integration_review, run_digest=SUMMARY)
        self.assertTrue(any("never the Run-summary digest" in p for p in summary_as_run.problems()))
        self.assertTrue(dataclasses.replace(evidence, integration_review=summary_as_run).problems())
        for field in ("candidate_hash", "receipt_digest", "consumption_digest"):
            with self.subTest(field=field):
                self.assertTrue(dataclasses.replace(evidence.integration_review, **{field: RUN}).problems())
        record = evidence.to_record()
        del record["integration_review"]["run_digest"]
        with self.assertRaises(ValidationError):
            ach.PhaseCompletionEvidence.from_record(record)

    def test_cpq05b_no_evidence_over_a_failing_project_structure(self) -> None:
        """Ruling CPQ-05B: the Project-wide structural result is bound; evidence is PASS-only."""
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        other = b.phase("Unrelated")
        b.integration(other, marker=None)
        b.integration(other, marker=None)
        basis = ach.phase_basis(b.view(), phase)
        self.assertFalse(basis.structural_validation_passed)
        self.assertNotEqual(ach.PASS_VALIDATION_DIGEST, basis.structural_validation_digest)
        with self.assertRaises(ValidationError):
            evidence_for(basis)

    def test_the_run_refs_belong_to_the_covering_integration(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        evidence = evidence_for(basis)
        foreign = dataclasses.replace(evidence, integration_review=dataclasses.replace(evidence.integration_review,
                                                                                         integration_id=ident("w", 999)))
        self.assertTrue(foreign.problems())

    def test_strict_reading(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        record = evidence_for(ach.phase_basis(b.view(), phase)).to_record()
        mutations = {
            "missing field": lambda r: r.pop("rationale"),
            "extra field": lambda r: r.update(extra=1),
            "legacy mode": lambda r: r.update(completion_mode="legacy"),
            "multi-line rationale": lambda r: r.update(rationale="line one\nline two"),
            "unsorted Works": lambda r: r.update(effective_work_ids=list(reversed(r["effective_work_ids"]))),
            "bad receipt": lambda r: r["integration_review"].update(receipt_id="rcp_bad"),
            "no evaluators": lambda r: r.update(evaluators=[]),
            "digest with a trailing newline": lambda r: r.update(basis_digest=r["basis_digest"] + "\n"),
            "structural digest of a failing validation": lambda r: r.update(structural_validation_digest="e" * 64),
            "confirmation outside the plan": lambda r: r.update(downstream_confirmations=[
                {"work_id": ident("w", 998), "completed_event_id": ident("evt", 1)}]),
            # RB5FA-1: a YAML sequence where a digest belongs is review_record_invalid, never a raw TypeError.
            "list digest": lambda r: r["integration_review"].update(
                candidate_hash=[r["integration_review"]["candidate_hash"]]),
        }
        for described, mutate in mutations.items():
            broken = serialize.canonical_data(record)
            mutate(broken)
            with self.subTest(case=described), self.assertRaises(ValidationError):
                ach.PhaseCompletionEvidence.from_record(broken)

    def test_rb5fa1_a_non_string_digest_is_review_record_invalid_never_a_raw_type_error(self) -> None:
        """RB5FA-1: every Integration Run digest, as a sequence or a mapping, reads as review_record_invalid, and the
        problem-list readers behind it (basis binding, matching, progression, the Roadmap basis) report it."""
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        evidence = evidence_for(basis)
        record = evidence.to_record()
        for field in ("candidate_hash", "run_digest", "receipt_digest", "consumption_digest", "run_summary_digest"):
            good = record["integration_review"][field]
            for bad in ([good], {"digest": good}):
                with self.subTest(field=field, value=type(bad).__name__):
                    broken = serialize.canonical_data(record)
                    broken["integration_review"][field] = bad
                    with self.assertRaises(ValidationError) as raised:
                        ach.PhaseCompletionEvidence.from_record(broken)
                    self.assertEqual("review_record_invalid", raised.exception.code)
                    self.assertIn("is not a lowercase hex SHA-256", str(raised.exception))
                    ref = dataclasses.replace(evidence.integration_review, **{field: bad})
                    self.assertTrue(any(field in problem for problem in ref.problems()))
                    drifted = dataclasses.replace(evidence, integration_review=ref)
                    self.assertTrue(drifted.problems())
                    self.assertTrue(ach.phase_evidence_basis_problems(drifted, basis))
                    self.assertEqual(ach.EVIDENCE_INVALID, ach.match_current_phase_evidence(basis, [drifted]).status)
                    self.assertFalse(ach.phase_progression_decision(b.view(), phase, [drifted]).ready)
                    self.assertEqual(((phase, ach.EVIDENCE_INVALID),),
                                     ach.roadmap_basis(b.view(), b.roadmap_id, [drifted]).unready_phases)
        both = dataclasses.replace(evidence.integration_review, candidate_hash=[CANDIDATE], run_digest=[CANDIDATE])
        self.assertEqual(2, sum("is not a lowercase hex SHA-256" in problem for problem in both.problems()),
                         "each non-string digest is reported by its own field check")


class MatchingTests(unittest.TestCase):
    def test_exactly_one_none_or_conflicting(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        first, second = evidence_for(basis, 1), evidence_for(basis, 2)
        self.assertEqual(ach.EVIDENCE_MISSING, ach.match_current_phase_evidence(basis, []).status)
        ready = ach.match_current_phase_evidence(basis, [first])
        self.assertEqual((ach.EVIDENCE_READY, first.achievement_evidence_id), (ready.status, ready.evidence_id))
        conflict = ach.match_current_phase_evidence(basis, [second, first])
        self.assertEqual(ach.EVIDENCE_CONFLICT, conflict.status)
        self.assertIsNone(conflict.evidence_id)
        with self.assertRaises(ValidationError):
            ach.match_current_phase_evidence(basis, [first.to_record()])

    def test_a_record_claiming_the_current_digest_must_bind_every_basis_field(self) -> None:
        """RB5C-M1: never trusted on its self-declared basis digest."""
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        good = evidence_for(basis)
        drifted = {
            "dropped Work": dataclasses.replace(good, effective_work_ids=tuple(w for w in good.effective_work_ids
                                                                                if w != normal[0])),
            "covering a normal Work": dataclasses.replace(
                good, covering_integration_id=normal[0],
                integration_review=dataclasses.replace(good.integration_review, integration_id=normal[0])),
            "another objective": dataclasses.replace(good, phase_desired_state_digest="f" * 64),
            "failing structure": dataclasses.replace(good, structural_validation_digest="e" * 64),
            "invalid instance": dataclasses.replace(good, completion_mode="legacy", phase_outcome=ri.NOT_SATISFIED,
                                                    evaluators=(), rationale=""),
        }
        for described, record in drifted.items():
            with self.subTest(case=described):
                self.assertTrue(ach.phase_evidence_basis_problems(record, basis))
                match = ach.match_current_phase_evidence(basis, [record])
                self.assertEqual(ach.EVIDENCE_INVALID, match.status)
                self.assertFalse(ach.phase_progression_decision(b.view(), phase, [record]).ready)
                with self.assertRaises(ValidationError):
                    ach.phase_evidence_obligation(b.view(), phase, [record])
        self.assertEqual(ach.EVIDENCE_INVALID, ach.match_current_phase_evidence(basis, [good, drifted["dropped Work"]]).status)

    def test_old_evidence_becomes_stale_after_late_work_and_a_new_completion_is_new_evidence(self) -> None:
        b = ViewBuilder()
        phase, normal, old, _ = reviewed_phase(b)
        old_evidence = evidence_for(ach.phase_basis(b.view(), phase), 1)
        late = b.work(phase, "Late")
        stale = ach.phase_basis(b.view(), phase)
        self.assertFalse(stale.generated_complete)
        self.assertEqual(ach.EVIDENCE_STALE, ach.match_current_phase_evidence(stale, [old_evidence]).status)
        new = b.integration(phase)
        for work_id in normal + [late]:
            b.requires(work_id, new)
        b.complete(late, new)
        current = ach.phase_basis(b.view(), phase)
        new_evidence = evidence_for(current, 2, integration=new)
        match = ach.match_current_phase_evidence(current, [old_evidence, new_evidence])
        self.assertEqual((ach.EVIDENCE_READY, new_evidence.achievement_evidence_id, (old_evidence.achievement_evidence_id,)),
                         (match.status, match.evidence_id, match.historical_ids))

    def test_a_structural_failure_elsewhere_is_reported_as_such_not_as_stale(self) -> None:
        """RB5C-L5."""
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        evidence = evidence_for(ach.phase_basis(b.view(), phase))
        other = b.phase("Unrelated")
        b.integration(other, marker=None)
        b.integration(other, marker=None)  # two unfinished integrations in another Phase: structure fails
        decision = ach.phase_progression_decision(b.view(), phase, [evidence])
        self.assertFalse(decision.ready)
        self.assertEqual(ach.EVIDENCE_STRUCTURE_INVALID, decision.match.status)
        self.assertNotIn("older basis", decision.reason)


class ObligationAndProgressionTests(unittest.TestCase):
    def test_obligation_only_for_reviewed_generated_complete_without_current_evidence(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        b.complete(*normal)
        self.assertFalse(ach.phase_evidence_obligation(b.view(), phase, []).required)
        b.complete(integration)
        obligation = ach.phase_evidence_obligation(b.view(), phase, [])
        self.assertTrue(obligation.required)
        evidence = evidence_for(obligation.basis)
        self.assertFalse(ach.phase_evidence_obligation(b.view(), phase, [evidence]).required)
        with self.assertRaises(ValidationError):
            ach.phase_evidence_obligation(b.view(), phase, [evidence, evidence_for(obligation.basis, 2)])

    def test_the_one_owner_entry_point_checks_the_obligation_and_the_source_refs(self) -> None:
        """RB5C-L6."""
        b = ViewBuilder()
        phase, _, integration, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)

        def create(existing, source_ref_problems):
            return ach.phase_completion_evidence_for(
                b.view(), phase, existing, achievement_evidence_id=ident("rha", 9),
                covering_integration_id=integration, integration_review=run_ref(basis), phase_outcome=judged(basis),
                source_ref_problems=source_ref_problems, evaluators=[("adjudicator", "claude-opus", "5.5")],
                rationale="The Phase objective holds.", causing_mutation_id=ident("mut", 9), causing_operation="start")

        created = create([], [])
        self.assertIsNotNone(created)
        self.assertIsNone(create([created], []), "no duplicate when current evidence exists")
        with self.assertRaises(ValidationError):
            create([], ["the Receipt does not read"])
        legacy = ViewBuilder()
        legacy_id = legacy_phase(legacy)
        self.assertIsNone(ach.phase_completion_evidence_for(
            legacy.view(), legacy_id, [], achievement_evidence_id="x", covering_integration_id=ident("w", 1),
            integration_review=run_ref(basis), phase_outcome=judged(basis), source_ref_problems=[],
            evaluators=[("a", "b", "c")], rationale="r.", causing_mutation_id=ident("mut", 1), causing_operation="start"))

    def test_progression_distinguishes_generated_complete_from_evidence_ready(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        view = b.view()
        missing = ach.phase_progression_decision(view, phase, [])
        self.assertEqual((False, True), (missing.ready, missing.generated_complete))
        self.assertIn("obligation is not closed", missing.reason)
        evidence = evidence_for(ach.phase_basis(view, phase))
        self.assertTrue(ach.phase_progression_decision(view, phase, [evidence]).ready)
        b.work(phase, "Late")
        self.assertFalse(ach.phase_progression_decision(b.view(), phase, [evidence]).ready)

    def test_legacy_complete_is_ready_without_evidence_and_incomplete_is_not(self) -> None:
        """RB8-FC-09 item 3: a legacy Phase needs no evidence and nothing is backfilled."""
        b = ViewBuilder()
        phase = legacy_phase(b, complete=False)
        self.assertFalse(ach.phase_progression_decision(b.view(), phase, []).ready)
        work, integration = sorted(w.id for w in b.view().phase_works(phase))
        b.complete(work, integration)
        decision = ach.phase_progression_decision(b.view(), phase, [])
        self.assertEqual((True, pi.MODE_LEGACY), (decision.ready, decision.completion_mode))

    def test_postcommit_basis_round_trip(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        b.complete(*normal)
        b.start(integration)
        completed = {"kind": "append_event", "payload": {"record": {
            "id": ident("evt", 778), "type": "work_completed", "entity": integration, "at": "t"}}}
        projected = b.view().with_effects([completed])
        evidence = evidence_for(ach.phase_basis(projected, phase))  # built on the projection, before the write
        b.events.append(projected.events[-1])  # the committed state after the write
        committed = ach.phase_basis(b.view(), phase)
        self.assertEqual([], ach.postcommit_basis_problems(evidence, committed))
        b.work(phase, "Late")
        self.assertTrue(ach.postcommit_basis_problems(evidence, ach.phase_basis(b.view(), phase)))


class ProgressionNarrowingTests(unittest.TestCase):
    """RB8-FC-08: one pure narrowing over ProjectView.startable_phases for Roadmap and status."""

    def project(self) -> tuple[ViewBuilder, str, str, str]:
        b = ViewBuilder()
        reviewed, _, _, _ = reviewed_phase(b)
        legacy = legacy_phase(b)
        next_phase = b.phase("Next")
        b.requires(reviewed, next_phase)
        b.requires(legacy, next_phase)
        return b, reviewed, legacy, next_phase

    def test_a_reviewed_predecessor_without_evidence_holds_the_candidate_back(self) -> None:
        b, reviewed, _, next_phase = self.project()
        view = b.view()
        candidates = view.startable_phases(b.roadmap_id)
        self.assertEqual([next_phase], [p.id for p in candidates], "lifecycle alone makes it startable")
        narrowed = ach.progression_ready_candidates(view, candidates, [])
        self.assertEqual((), narrowed.ready)
        ((candidate, predecessor, reason),) = narrowed.blocked
        self.assertEqual((next_phase, reviewed), (candidate, predecessor))
        self.assertIn("evidence obligation", reason)

    def test_valid_evidence_unblocks_and_a_legacy_predecessor_needs_none(self) -> None:
        b, reviewed, _, next_phase = self.project()
        view = b.view()
        evidence = evidence_for(ach.phase_basis(view, reviewed))
        narrowed = ach.progression_ready_candidates(view, view.startable_phases(b.roadmap_id), [evidence])
        self.assertEqual([next_phase], [p.id for p in narrowed.ready])
        self.assertEqual((), narrowed.blocked)

    def test_stale_evidence_blocks_again(self) -> None:
        b, reviewed, _, next_phase = self.project()
        evidence = evidence_for(ach.phase_basis(b.view(), reviewed))
        late = b.work(reviewed, "Late")
        b.complete(late)
        view = b.view()
        narrowed = ach.progression_ready_candidates(view, [view.phases[next_phase]], [evidence])
        self.assertEqual((), narrowed.ready)


class DeferredAchievementTests(IntegrationRunCase):
    def test_achievement_records_live_in_history_achievements(self) -> None:
        """review/paths.py + store.py + validate.py + history.py (taken from the shared-surface writer at I-3):
        one strict record under the P5 header at ``history/achievements/<rha_...>.yaml``, read back by ``ReviewStore``
        exactly as the RB5 body built it, and refused by the history layer under any ID that is not a
        ``review_achievement`` one. Its §32.49 source references are validated (the shared-surface writer's repair
        72bfbd0): this record cites an Integration Run nothing stored here, so validation reports exactly that."""
        root = Path(tempfile.mkdtemp(prefix="workline-rb5-achievement-"))
        self.addCleanup(rmtree, root)
        review = ReviewStore(ProjectStore(root))
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        evidence = evidence_for(ach.phase_basis(b.view(), phase))
        found = history.achievement_record(evidence)
        relative = paths.history_achievement_rel(evidence.achievement_evidence_id)
        self.assertEqual(f".workline/review/history/achievements/{evidence.achievement_evidence_id}.yaml", relative)
        record = found.to_record()
        self.assertEqual((history.SCHEMA_ACHIEVEMENT, history.HISTORY_CONTRACT),
                         (record["schema"], record["history_contract"]))
        self.assertEqual(evidence.to_record(), {key: value for key, value in record.items()
                                                if key not in history.ACHIEVEMENT_HEADER_FIELDS})
        target = root / relative
        target.parent.mkdir(parents=True)
        target.write_bytes(serialize.canonical_bytes(record))
        self.assertEqual((evidence.achievement_evidence_id,), review.achievement_ids())
        self.assertEqual(evidence, review.read_achievement(evidence.achievement_evidence_id).evidence)
        self.assertEqual(["review_record_missing"], [problem.code for problem in review_problems(review)],
                         "the cited Integration Run records are not stored: the sources are validated, never assumed")
        labelled = dataclasses.replace(evidence, achievement_evidence_id="test-achievement-1")
        self.assertEqual([], labelled.problems(), "the body alone checks a public-safe label")
        with self.assertRaises(ValidationError):
            history.achievement_record(labelled)

    def test_review_achievement_id_kind(self) -> None:
        """ids.py (taken from the shared-surface writer at I-1; allocation A-1): ``review_achievement`` is ``rha``,
        parsed longest-first - never read as ``rr`` / ``r`` - and distinct from the P5 ``rhr`` / ``rhd`` kinds."""
        self.assertEqual("rha", ids.PREFIXES["review_achievement"])
        fresh = ids.new_id("review_achievement")
        self.assertTrue(fresh.startswith("rha_"))
        self.assertEqual("review_achievement", ids.kind_of(fresh))
        self.assertTrue(ids.is_valid_id(fresh, "review_achievement"))
        for kind in ("review_run", "review_relation", "review_decision", "roadmap"):
            with self.subTest(kind=kind):
                self.assertFalse(ids.is_valid_id(fresh, kind))
        self.assertEqual("review_achievement", paths.HISTORY_FAMILY_KINDS[paths.HISTORY_ACHIEVEMENTS])
        self.assertEqual(1, list(ids.PREFIXES.values()).count("rha"))

    def test_integration_terminal_completion_writes_evidence_in_the_same_mutation(self) -> None:
        """start.py / start_review.py (I-5, the terminal half of R27; §32.35 - §32.37, §32.39): the terminal stage
        that makes the reviewed Phase generated-complete reserves and builds its phase_completion record in the SAME
        START mutation and the SAME commit as the integration's work_completed - bound to that event, to the Run's
        terminal gate, Receipt, Consumption and consumed summary - and HEAD's committed basis proves it."""
        store, phase_id, ids = self.marked_project()
        result = self.integrate(store, ids["integration"])
        self.assertEqual("completed", result.status)
        review = ReviewStore(store)
        (evidence,) = review.phase_completion_evidence()
        view = ProjectView.load(store)
        (completed,) = [event for event in view.events_for(ids["integration"]) if event.type == "work_completed"]
        self.assertEqual((phase_id, ids["integration"], result.mutation_id, "start", (completed.id,)),
                         (evidence.phase_id, evidence.covering_integration_id, evidence.causing_mutation_id,
                          evidence.causing_operation, evidence.causing_event_ids))
        chain = self.one_run(store, ids["integration"])
        consumption = review.consumption_by_receipt()[str(chain.latest.receipt_id)]
        ref = evidence.integration_review
        self.assertEqual((chain.review_run_id, chain.latest_digest, chain.latest.receipt_id, consumption.consumption_id),
                         (ref.review_run_id, ref.run_digest, ref.receipt_id, ref.consumption_id))
        self.assertEqual(review.history_digest(paths.HISTORY_RUNS, chain.review_run_id), ref.run_summary_digest)
        changed = set(git(store.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").split())
        self.assertLessEqual({paths.history_achievement_rel(evidence.achievement_evidence_id),
                              ".workline/events/events.jsonl", paths.consumption_rel(consumption.consumption_id)},
                             changed, "one terminal commit")
        self.assertEqual([], ach.postcommit_basis_problems(evidence, ach.phase_basis(view, phase_id)))
        self.assertTrue(achievement_reader.phase_progression_ready(store, phase_id).ready)
        self.assertEqual([], validate_project(store))

    def test_downstream_confirmation_completion_writes_evidence(self) -> None:
        """start.py / start_review.py (I-6, R27; §32.36 - §32.37, §32.39): the integration authorized with its
        downstream confirmation leaves the reviewed Phase incomplete, so it writes no evidence; the ordinary START of
        the confirmation that makes it generated-complete reserves and builds the phase_completion record in the SAME
        lifecycle stage and commit as its work_completed - citing the covering integration's consumed Run from its
        committed terminal records - and HEAD's committed basis proves it."""
        from helpers import completing_executor
        from rb5_run_helpers import Adjudicator, Discovery, phase_review
        from workline import phase_integration as pi
        from workline import start as st

        store, phase_id, ids = self.marked_project()
        integration = ids["integration"]
        selector = phase_review(Discovery(), adjudicator=Adjudicator(ri.HUMAN_CONFIRMATION_REQUIRED))
        self.assertEqual("completed", self.integrate(store, integration, selector).status)
        review = ReviewStore(store)
        self.assertEqual((), review.phase_completion_evidence())
        view = ProjectView.load(store)
        (confirmation,) = [w for w in view.effective_works(phase_id) if w.work_kind == pi.CONFIRMATION_KIND]
        result = st.start(store, confirmation.id, "single-work", completing_executor(store))
        self.assertEqual("completed", result.status)
        (evidence,) = review.phase_completion_evidence()
        view = ProjectView.load(store)
        (completed,) = [e for e in view.events_for(confirmation.id) if e.type == "work_completed"]
        consumed = [run_id for run_id in self.integration_runs(store, integration)
                    if review.gate_chain(run_id).latest.sealed]
        self.assertEqual((integration, consumed[0], result.mutation_id, (completed.id,)),
                         (evidence.covering_integration_id, evidence.integration_review.review_run_id,
                          evidence.causing_mutation_id, evidence.causing_event_ids))
        changed = set(git(store.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").split())
        self.assertLessEqual({paths.history_achievement_rel(evidence.achievement_evidence_id),
                              ".workline/events/events.jsonl"}, changed, "one completion commit")
        self.assertEqual([], ach.postcommit_basis_problems(evidence, ach.phase_basis(view, phase_id)))
        self.assertTrue(achievement_reader.phase_progression_ready(store, phase_id).ready)
        self.assertEqual([], validate_project(store))

    def test_start_cancel_replan_completion_writes_evidence(self) -> None:
        """start.py / start_review.py (I-6, R27; §32.36 - §32.37): a START cancel whose applied effects close the
        reviewed basis - here the downstream confirmation of an integration authorized objectively_satisfied - records
        the phase_completion evidence over the Project the cancel leaves, after its replan and before the commit that
        carries it (the cancel's own work_cancelled is its causing event); interrupted in between, the resumed cancel
        proves the stage and finishes with exactly one record."""
        from rb5_run_helpers import phase_review
        from workline import phase_integration as pi
        from workline import start as st
        from workline.mutation import MutationController
        from planning_helpers import Crash, crash_at

        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted):
                store, phase_id, ids = self.marked_project("cancel-interrupted" if interrupted else "cancel",
                                                           confirmation=True)
                self.assertEqual("completed", self.integrate(store, ids["integration"], phase_review()).status)
                review = ReviewStore(store)
                self.assertEqual((), review.phase_completion_evidence(), "the confirmation is still pending")
                cancel = st.Cancel(reason="the Human confirmation is no longer needed")
                executor = lambda ctx: cancel  # noqa: E731
                if interrupted:
                    with crash_at(st._Session, "_commit", when=lambda n, session, prefix, *a, **k: prefix == "commit"):
                        with self.assertRaises(Crash):
                            st.start(store, ids["confirmation"], "single-work", executor)
                result = st.start(store, ids["confirmation"], "single-work", executor)
                self.assertEqual("cancelled", result.status)
                (evidence,) = review.phase_completion_evidence()
                view = ProjectView.load(store)
                (cancelled,) = [e for e in view.events_for(ids["confirmation"]) if e.type == "work_cancelled"]
                self.assertEqual((ids["integration"], (cancelled.id,), ()),
                                 (evidence.covering_integration_id, evidence.causing_event_ids,
                                  evidence.downstream_confirmations))
                self.assertEqual(ri.OBJECTIVELY_SATISFIED, evidence.phase_outcome)
                changed = set(git(store.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").split())
                self.assertIn(paths.history_achievement_rel(evidence.achievement_evidence_id), changed)
                self.assertEqual([], ach.postcommit_basis_problems(evidence, ach.phase_basis(view, phase_id)))
                self.assertTrue(achievement_reader.phase_progression_ready(store, phase_id).ready)
                self.assertEqual(pi.MODE_REVIEWED, pi.completion_mode(view, phase_id))
                self.assertEqual([], MutationController(store).list_pending())
                self.assertEqual([], validate_project(store))

    def test_roadmap_work_plan_exclude_completion_writes_evidence(self) -> None:
        """roadmap.py / ops.py (I-8, R30; §32.36 - §32.37, §32.39): excluding an unstarted Work that alone kept a
        reviewed Phase from completing restores its covering basis - the work-plan exclusion records the
        phase_completion evidence over the Project it leaves (its plan_excluded event the cause), in its own stage
        before the commit that carries it; interrupted in between, the resumed exclusion proves the stage and
        finishes with one record. A Phase exclusion creates none."""
        from helpers import completing_executor
        from planning_helpers import Crash, crash_at
        from rb5_run_helpers import phase_review
        from workline import roadmap as rm
        from workline import start as st
        from workline.mutation import MutationController

        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted):
                store, phase_id, ids = self.marked_project("exclude-interrupted" if interrupted else "exclude",
                                                           confirmation=True)
                self.assertEqual("completed", self.integrate(store, ids["integration"], phase_review()).status)
                late = self.add_late_work(store, phase_id)
                self.assertEqual("completed",
                                 st.start(store, ids["confirmation"], "single-work", completing_executor(store)).status)
                review = ReviewStore(store)
                self.assertEqual((), review.phase_completion_evidence(), "the late Work keeps the Phase incomplete")
                if interrupted:
                    with crash_at(rm, "_finalize"):
                        with self.assertRaises(Crash):
                            rm.plan_exclude_work(store, late)
                result = rm.plan_exclude_work(store, late)
                self.assertEqual("plan_excluded", result.status)
                (evidence,) = review.phase_completion_evidence()
                view = ProjectView.load(store)
                (excluded,) = [e for e in view.events_for(late) if e.type == "plan_excluded"]
                self.assertEqual((ids["integration"], (excluded.id,), "work-plan-exclude", result.mutation_id),
                                 (evidence.covering_integration_id, evidence.causing_event_ids,
                                  evidence.causing_operation, evidence.causing_mutation_id))
                changed = set(git(store.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").split())
                self.assertIn(paths.history_achievement_rel(evidence.achievement_evidence_id), changed)
                self.assertEqual([], ach.postcommit_basis_problems(evidence, ach.phase_basis(view, phase_id)))
                self.assertTrue(achievement_reader.phase_progression_ready(store, phase_id).ready)
                self.assertEqual([], MutationController(store).list_pending())
                self.assertEqual([], validate_project(store))

    def test_crash_resume_cannot_advance_roadmap_without_closing_the_obligation(self) -> None:
        """roadmap.py (I-8, R31; §32.40 - §32.42): the integration's terminal stage interrupted part-way - its
        work_completed applied, its phase_completion evidence not - leaves reviewed Phase a generated-complete but
        not progression-ready: Roadmap holds the Phase that requires it back (not startable, explicit choice refused,
        the diagnosis names a's evidence obligation). The START resumed from its record closes the obligation in the
        same stage, and only then does b become startable."""
        from planning_helpers import Crash, crash_at
        from rb5_run_helpers import phase_review
        from workline import roadmap as rm
        from workline.errors import SpecViolation
        from workline.mutation import MutationController as Controller

        store, phase_id, ids = self.marked_project(next_phase=True)
        roadmap_id = self.roadmap_of(store, phase_id)

        def evidence_create(n, controller, record) -> bool:
            return record["kind"] == "create_file" and "/history/achievements/" in record["payload"]["path"]

        with crash_at(Controller, "apply_effect", when=evidence_create):
            with self.assertRaises(Crash):
                self.integrate(store, ids["integration"], phase_review())
        view = ProjectView.load(store)
        self.assertTrue(view.phase_completion(phase_id).complete, "work_completed is applied")
        self.assertEqual((), ReviewStore(store).phase_completion_evidence())
        self.assertFalse(achievement_reader.phase_progression_ready(store, phase_id).ready)
        (phase_b,) = [p for p in view.roadmap_phases(roadmap_id) if p.id != phase_id]
        self.assertIn(phase_b.id, [p.id for p in view.startable_phases(roadmap_id)], "lifecycle alone would start b")
        self.assertEqual([], [p.id for p in rm.startable_phases(store, roadmap_id)])
        self.assertIsNone(rm.select_phase(store, roadmap_id))
        with self.assertRaises(SpecViolation) as refused:
            rm.select_phase(store, roadmap_id, explicit=phase_b.id)
        self.assertIn("not progression-ready", str(refused.exception))
        self.assertIn(phase_id, rm.diagnose_no_candidate(store, roadmap_id))
        self.assertEqual("completed", self.integrate(store, ids["integration"], phase_review()).status)
        self.assertEqual(1, len(ReviewStore(store).phase_completion_evidence()))
        self.assertEqual([phase_b.id], [p.id for p in rm.startable_phases(store, roadmap_id)])
        self.assertEqual(phase_b.id, rm.select_phase(store, roadmap_id).id)
        self.assertEqual([], Controller(store).list_pending())

    def test_status_projects_the_same_progression_narrowing(self) -> None:
        """L502 (I-9, R33; §32.41 / §32.42, RB8-FC-08): status projects exactly Roadmap's progression narrowing, on a
        real interrupted state - the integration's terminal stage applied up to its work_completed, its
        phase_completion evidence not. Status's next-Phase candidates are ``rm.startable_phases`` (never the
        lifecycle-only ``ProjectView.startable_phases``), b is held back with a's evidence obligation as its blocker,
        and no next Phase is selected, as ``rm.select_phase`` selects none; once the resumed START closes the
        obligation, status's next Phase is ``rm.select_phase``'s and nothing is held back."""
        from planning_helpers import Crash, crash_at
        from rb5_run_helpers import phase_review
        from workline import roadmap as rm
        from workline import status
        from workline.mutation import MutationController as Controller

        store, phase_id, ids = self.marked_project(next_phase=True)
        roadmap_id = self.roadmap_of(store, phase_id)

        def evidence_create(n, controller, record) -> bool:
            return record["kind"] == "create_file" and "/history/achievements/" in record["payload"]["path"]

        with crash_at(Controller, "apply_effect", when=evidence_create):
            with self.assertRaises(Crash):
                self.integrate(store, ids["integration"], phase_review())
        view = ProjectView.load(store)
        (phase_b,) = [p for p in view.roadmap_phases(roadmap_id) if p.id != phase_id]
        self.assertIn(phase_b.id, [p.id for p in view.startable_phases(roadmap_id)], "lifecycle alone would start b")
        lifecycle = status.build_status(store.root).data["lifecycle"]
        self.assertEqual([p.id for p in rm.startable_phases(store, roadmap_id)], lifecycle["next"]["phase"]["candidates"])
        self.assertEqual([], lifecycle["next"]["phase"]["candidates"])
        held = [item for item in lifecycle["blockers"] if item["code"] == "phase_evidence_not_ready"]
        self.assertEqual([(phase_b.id, [phase_id])], [(item["candidate"], item["ids"]) for item in held])
        self.assertIsNone(rm.select_phase(store, roadmap_id))
        self.assertIsNone(lifecycle["next"]["phase"]["id"])
        self.assertEqual("completed", self.integrate(store, ids["integration"], phase_review()).status)
        lifecycle = status.build_status(store.root).data["lifecycle"]
        self.assertEqual(phase_b.id, rm.select_phase(store, roadmap_id).id)
        self.assertEqual(phase_b.id, lifecycle["next"]["phase"]["id"])
        self.assertEqual([p.id for p in rm.startable_phases(store, roadmap_id)], lifecycle["next"]["phase"]["candidates"])
        self.assertNotIn("phase_evidence_not_ready", [item["code"] for item in lifecycle["blockers"]])

    def test_no_separate_lifecycle_phase_event(self) -> None:
        """I-11 (R38; §14.1, §32.63): Phase completion and its achievement evidence are never lifecycle events - the
        Phase event vocabulary is unchanged, and a reviewed Phase completed with its evidence leaves no
        phase_completed / phase_achieved (or any Phase) event in the log."""
        from rb5_run_helpers import phase_review
        from workline import store as store_module

        self.assertEqual(("phase_held", "phase_resumed", "phase_cancelled", "plan_excluded"), store_module.PHASE_EVENTS)
        store, phase_id, ids = self.marked_project()
        self.assertEqual("completed", self.integrate(store, ids["integration"], phase_review()).status)
        self.assertEqual(1, len(ReviewStore(store).phase_completion_evidence()))
        view = ProjectView.load(store)
        self.assertEqual([], view.events_for(phase_id))
        self.assertFalse({"phase_completed", "phase_achieved"} & {event.type for event in view.events})



class CoveringReferenceTests(IntegrationRunCase):
    """RB5K-1 / RB5K-2 (§32.38 - §32.39): the covering integration's Review references an ordinary completion's
    phase_completion evidence binds are read only from records that hold no change from before the operation, and an
    uncitable covering Review is a fail-closed refusal - in both cases nothing is recorded."""

    def confirmed_phase(self, name: str):
        from rb5_run_helpers import Adjudicator, Discovery, phase_review

        store, phase_id, work_ids = self.marked_project(name)
        selector = phase_review(Discovery(), adjudicator=Adjudicator(ri.HUMAN_CONFIRMATION_REQUIRED))
        self.assertEqual("completed", self.integrate(store, work_ids["integration"], selector).status)
        view = ProjectView.load(store)
        (confirmation,) = [w for w in view.effective_works(phase_id) if w.work_kind == pi.CONFIRMATION_KIND]
        review = ReviewStore(store)
        (run_id,) = [found for found in self.integration_runs(store, work_ids["integration"])
                     if review.gate_chain(found).latest.sealed]
        return store, phase_id, confirmation.id, run_id

    def test_a_changed_covering_record_is_refused_and_never_bound(self) -> None:
        """RB5K-1: the covering integration's committed Consumption hand-modified and left uncommitted - the
        completion that would close the Phase refuses ``dirty_overlap``, writes no evidence, and writes nothing
        over the changed record."""
        from helpers import completing_executor
        from workline import start as st
        from workline.errors import StopError

        store, phase_id, confirmation, run_id = self.confirmed_phase("dirty")
        review = ReviewStore(store)
        consumption = review.consumption_by_receipt()[str(review.gate_chain(run_id).latest.receipt_id)]
        target = store.root / paths.consumption_rel(consumption.consumption_id)
        original = target.read_bytes()
        changed = original.replace(consumption.operation_mutation_id.encode("utf-8"),
                                   ids.new_id("mutation").encode("utf-8"))
        self.assertNotEqual(original, changed)
        target.write_bytes(changed)
        with self.assertRaises(StopError) as raised:
            st.start(store, confirmation, "single-work", completing_executor(store))
        self.assertEqual("dirty_overlap", raised.exception.code)
        self.assertIn(paths.consumption_rel(consumption.consumption_id), str(raised.exception))
        self.assertEqual((), review.phase_completion_evidence(), "nothing is bound from the changed record")
        self.assertEqual(changed, target.read_bytes(), "and nothing is written over it")

    def test_a_covering_run_without_a_gate_chain_is_a_fail_closed_refusal(self) -> None:
        """RB5K-2: the covering integration's gate chain gone from the working tree - the completion refuses
        ``phase_evidence_unavailable`` (never a bare error) and records no evidence."""
        import shutil

        from helpers import completing_executor
        from workline import start as st
        from workline import start_review as sr
        from workline.errors import StopError

        store, phase_id, confirmation, run_id = self.confirmed_phase("chainless")
        for generation in range(1, 6):
            gate = store.root / paths.gate_rel(run_id, generation)
            if gate.exists():
                gate.unlink()
        self.assertIsNone(ReviewStore(store).gate_chain(run_id))
        with self.assertRaises(StopError) as raised:
            st.start(store, confirmation, "single-work", completing_executor(store))
        self.assertEqual(sr.CODE_PHASE_EVIDENCE_UNAVAILABLE, raised.exception.code)
        self.assertEqual((), ReviewStore(store).phase_completion_evidence())


if __name__ == "__main__":
    unittest.main()
