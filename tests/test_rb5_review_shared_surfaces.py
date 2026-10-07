"""RB5 deltas on the CROSS_SHARED Review surfaces (post-RB6 integration, written by the shared-surface writer).

I-1 (playbook R01 / R02 / the R14 constant): the ``review_achievement`` ID kind, the ``history/achievements``
family and the version 5 Consumption number (allocation A-1). The ID and path pins themselves live with the P5
pins in ``test_review_history_records.py``; this file holds the RB5-only checks that have no older home.

I-3 (R09 - R12): the strict versioned achievement record (``history.AchievementRecord``), its readers in
``ReviewStore`` / ``CommittedReviewStore``, its record-level validity (``validate.review_problems``, the §32.49
source Run / Receipt / Consumption refs of a phase_completion record included), and the progression reader
(``review.achievement_reader``) that feeds the pure RB5 core.

I-4 (R13 - R18, rulings OQ-B / OQ-C): the Phase Integration contract and its family policy, the version 5
Integration Consumption, the Phase outcome carried by the version 2 Integration adjudication, the kind-specific
G4-terminal path, the integration fix provenance of a ``future_work_link`` and the CPQ-05 source references.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from helpers import WorklineTestCase, git, rmtree
from rb5_doubles import ViewBuilder, ident, reviewed_phase
import test_work_terminal_activation as activation_tests
from test_review_p4_adjudication import DESCRIPTOR, TASK_A, bound, disposition, finding_ids, gate, report, returned
from workline import achievement as ach, state
from workline.errors import ValidationError
from workline.review import achievement_reader, history, p4, paths, records, serialize, validate
from workline.review import integration as ri
from workline.review.committed import CommittedReviewStore
from workline.review.store import GateChain, ReviewStore
from workline.store import ProjectStore

EVALUATORS = [("adjudicator", "claude-opus", "5.5"), ("discovery", "reviewer-a", "1")]
OPERATION = "start:" + "e" * 64
CONTEXT, POLICY_HASH, FILLER = "b" * 64, "c" * 64, "f" * 64
INTEGRATION_ENVELOPE = {
    serialize.SCHEMA_KEY: p4.SCHEMA_DISCOVERY_REQUEST, serialize.VERSION_KEY: p4.RECORD_VERSION,
    "policy_id": p4.P6_POLICY_ID, history.HISTORY_CONTRACT_KEY: history.HISTORY_CONTRACT,
    "review_contract": records.P4_PHASE_INTEGRATION_CONTRACT,
}


def satisfied(basis: ach.PhaseBasis, kind: str = ri.OBJECTIVELY_SATISFIED) -> ri.PhaseOutcome:
    return ri.PhaseOutcome(kind, str(basis.phase_desired_state_digest), "The Phase objective holds.")


def integration_reports(*claims: tuple[str, str, str]) -> list:
    item = dict(report(TASK_A, "correctness", list(claims or [("HIGH", "x", "claim one")])))
    item.update(review_kind=records.INTEGRATION_REVIEW_KIND, review_contract=records.P4_PHASE_INTEGRATION_CONTRACT)
    return bound(serialize.canonical_data(item))


def integration_adjudication(outcome: object, branch: str, *, claim: str = p4.OUTCOME_UNSUPPORTED,
                             run: str | None = None, integration: str | None = None,
                             candidate: str = "a" * 64) -> records.P4Adjudication:
    """A real normalized Phase Integration adjudication (version 2), built by ``p4.adjudication``."""
    reports = integration_reports()
    normalized = p4.normalize_adjudication(returned(disposition(TASK_A, 0, claim)), DESCRIPTOR, reports, None)
    gate_record = gate(review_run_id=run or ident("rr", 1), review_kind=records.INTEGRATION_REVIEW_KIND,
                       target_identity=integration or ident("w", 1), candidate_hash=candidate)
    return p4.adjudication(
        normalized, finding_ids(len(normalized.drafts)), review_run_id=run or ident("rr", 1), gate_record=gate_record,
        candidate_generation=1, review_contract=records.P4_PHASE_INTEGRATION_CONTRACT, descriptor=DESCRIPTOR,
        reports=reports, prior=None, policy_id=p4.P6_POLICY_ID, phase_outcome=outcome, integration_disposition=branch,
    )


def generations(run: str, integration: str, candidate: str, adjudication_digest: str, count: int, *,
                receipt_id: str | None = None) -> list[records.GateGeneration]:
    """Generations 1..count of a task-free Integration chain; from G4 on they bind the adjudication, G5 seals."""
    found: list[records.GateGeneration] = []
    previous = None
    for number in range(1, count + 1):
        sealed = number == 5
        item = records.GateGeneration(
            review_run_id=run, generation=number, previous_generation=None if number == 1 else number - 1,
            previous_digest=previous, review_kind=records.INTEGRATION_REVIEW_KIND, target_identity=integration,
            operation_identity=OPERATION, candidate_hash=candidate, review_context_hash=CONTEXT,
            effective_policy_hash=POLICY_HASH, evidence_digest=FILLER, coverage_digest=FILLER,
            raw_report_set_digest=FILLER, adjudication_digest=adjudication_digest if number >= 4 else FILLER,
            obligation_digest=FILLER, accepted_tasks=(), settled_tasks=(),
            status=records.GATE_STATUS_SEALED if sealed else records.GATE_STATUS_OPEN,
            receipt_id=receipt_id if sealed else None,
            authorized_operation_stage=ri.AUTHORIZED_OPERATION_STAGE if sealed else None,
        )
        found.append(item)
        previous = serialize.digest(item.to_record())
    return found


def phase_evidence(basis: ach.PhaseBasis, ref: ach.IntegrationRunRef, outcome: ri.PhaseOutcome, number: int = 1, *,
                   evidence_id: str | None = None) -> ach.PhaseCompletionEvidence:
    """A strict phase_completion body over ``basis`` under a reserved ``review_achievement`` identity."""
    return ach.build_phase_completion_evidence(
        evidence_id or ident("rha", number), basis, covering_integration_id=ref.integration_id,
        integration_review=ref, phase_outcome=outcome, evaluators=EVALUATORS,
        rationale="Every effective Work is integrated and the Phase objective holds.",
        causing_mutation_id=ident("mut", number), causing_operation="start", causing_event_ids=[ident("evt", 900 + number)],
    )


def unlaid_ref(basis: ach.PhaseBasis, number: int = 1) -> ach.IntegrationRunRef:
    """References no stored record names (structural tests that never read the sources; validation reports a
    stored record citing them, §32.49)."""
    return ach.IntegrationRunRef(basis.covering_integration_ids[0], ident("rr", number), "1" * 64, "2" * 64,
                                 ident("rcp", number), "3" * 64, ident("rcs", number), "4" * 64, "5" * 64)


def roadmap_evidence(b: ViewBuilder, evidence: list[ach.PhaseCompletionEvidence], number: int = 50
                     ) -> ach.RoadmapAchievementEvidence:
    basis = ach.roadmap_basis(b.view(), b.roadmap_id, evidence)
    decision = ach.RoadmapAchievementDecision(
        ach.JUDGEMENT_ACHIEVED, "claude-opus", "5.5", "Every Phase objective holds and the Roadmap goal is met.",
        tuple(sorted(item.achievement_evidence_id for item in evidence)))
    return ach.build_roadmap_achievement_evidence(ident("rha", number), basis, decision,
                                                  reserved_event_id=ident("evt", number),
                                                  causing_mutation_id=ident("mut", number))


class FoundationTests(unittest.TestCase):
    def test_the_integration_consumption_version_is_the_a1_allocation(self) -> None:
        self.assertEqual(5, records.INTEGRATION_CONSUMPTION_VERSION)
        taken = (records.VERSION, records.PLANNING_CONSUMPTION_VERSION, records.POLICY_CONSUMPTION_VERSION)
        self.assertEqual((1, 2, 3), taken)
        self.assertNotIn(records.INTEGRATION_CONSUMPTION_VERSION, taken)
        self.assertNotEqual(4, records.INTEGRATION_CONSUMPTION_VERSION, "4 is the Global Policy Consumption (P7)")

    def test_the_achievement_family_is_a_history_record_location_and_nothing_else(self) -> None:
        achievement = "rha_01ARZ3NDEKTSV4RRFFQ69G5FAV"
        relative = paths.history_achievement_rel(achievement)
        self.assertEqual(f"{paths.HISTORY_DIR}/achievements/{achievement}.yaml", relative)
        paths.require_review_record_path(relative)
        paths.require_review_readable_path(relative)
        self.assertNotIn("achievements", paths.REVIEW_SUBDIRS, "achievements lives under history, not beside it")
        self.assertNotIn("achievements", paths.POLICY_FAMILIES)


class Directory(unittest.TestCase):
    """A bare directory read through ``ReviewStore``: records laid down as their exact canonical bytes."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="workline-rb5-shared-"))
        self.addCleanup(rmtree, self.root)
        self.store = ProjectStore(self.root)
        self.review = ReviewStore(self.store)

    def put(self, relative: str, record: dict | None = None, raw: bytes | None = None) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw if raw is not None else serialize.canonical_bytes(record))

    def put_achievement(self, evidence: object) -> history.AchievementRecord:
        found = history.achievement_record(evidence)
        self.put(paths.history_achievement_rel(found.achievement_evidence_id), found.to_record())
        return found

    def codes(self) -> list[str]:
        return [problem.code for problem in validate.review_problems(self.review)]

    def codes_beyond(self, baseline: list[str]) -> list[str]:
        """What validation reports beyond ``baseline`` (sorted multiset difference): ``baseline`` is taken once the
        task-free fixture Integration Run is laid down, whose own Run-level gaps are not what a test is about
        (see :class:`SourceReferenceTests`). A baseline code that disappears fails the test."""
        remaining = self.codes()
        for code in baseline:
            remaining.remove(code)
        return sorted(remaining)

    def integration_run(self, basis: ach.PhaseBasis, number: int = 1) -> tuple[ach.IntegrationRunRef, ri.PhaseOutcome]:
        """A consumed Phase Integration Run of ``basis``'s covering integration, every record laid down:
        G1-G5 (the seal issues the Receipt), the version 2 adjudication, the Receipt, the version 5 Consumption of
        the integration's own ``work_completed`` and the consumed P5 Run summary - and the references to them."""
        integration = basis.covering_integration_ids[0]
        run, receipt_id, consumption_id = ident("rr", number), ident("rcp", number), ident("rcs", number)
        candidate = serialize.digest({"integration-candidate": number})
        outcome = satisfied(basis)
        found = integration_adjudication(outcome, records.AUTHORIZATION_READY, run=run, integration=integration,
                                         candidate=candidate)
        adjudication_digest = serialize.digest(found.to_record())
        chain = generations(run, integration, candidate, adjudication_digest, 5, receipt_id=receipt_id)
        receipt = records.Receipt(
            receipt_id=receipt_id, review_run_id=run, review_generation=5, review_kind=records.INTEGRATION_REVIEW_KIND,
            target_identity=integration, operation_identity=OPERATION, authorized_candidate_hash=candidate,
            review_context_hash=CONTEXT, effective_policy_hash=POLICY_HASH, coverage_hash=FILLER,
            adjudication_hash=adjudication_digest, obligation_digest=FILLER, unresolved_obligations=0,
            authorized_operation_stage=ri.AUTHORIZED_OPERATION_STAGE,
        )
        consumption = records.IntegrationConsumption(
            consumption_id, receipt_id, run, 5, records.INTEGRATION_REVIEW_KIND, candidate, OPERATION,
            ident("mut", number), str(basis.work_fact(integration)["terminal_event_id"]), "work_completed", integration,
        )
        summary = history.consumed_run_summary(chain[-1], receipt, consumption_id, candidate_generation=1,
                                               adjudication=found)
        for item in chain:
            self.put(paths.gate_rel(run, item.generation), item.to_record())
        self.put(paths.adjudication_rel(run), found.to_record())
        self.put(paths.receipt_rel(receipt_id), receipt.to_record())
        self.put(paths.consumption_rel(consumption_id), consumption.to_record())
        self.put(paths.history_run_rel(run), summary.to_record())
        ref = ach.IntegrationRunRef(
            integration, run, candidate, serialize.digest(chain[-1].to_record()), receipt_id,
            serialize.digest(receipt.to_record()), consumption_id, serialize.digest(consumption.to_record()),
            serialize.digest(summary.to_record()),
        )
        return ref, outcome

    def evidence(self, basis: ach.PhaseBasis, number: int = 1) -> ach.PhaseCompletionEvidence:
        """Valid current evidence of ``basis``: its Integration Run laid down, and the record stored."""
        ref, outcome = self.integration_run(basis, number)
        return self.put_achievement(phase_evidence(basis, ref, outcome, number)).evidence


# --------------------------------------------------------------------------- I-3: the achievement record


class AchievementRecordTests(Directory):
    def test_both_kinds_are_one_strict_record_under_the_p5_header(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        ref, outcome = self.integration_run(basis)  # §32.49: validation reads the phase record's source refs
        run_gaps = self.codes()
        body = phase_evidence(basis, ref, outcome)
        roadmap = roadmap_evidence(b, [body])
        for evidence in (body, roadmap):
            with self.subTest(kind=evidence.kind):
                found = history.achievement_record(evidence)
                record = found.to_record()
                self.assertEqual((history.SCHEMA_ACHIEVEMENT, history.RECORD_VERSION, history.HISTORY_CONTRACT),
                                 (record["schema"], record["version"], record["history_contract"]))
                self.assertEqual(evidence.to_record(), {k: v for k, v in record.items()
                                                        if k not in history.ACHIEVEMENT_HEADER_FIELDS})
                self.assertEqual(evidence, found.evidence)
                self.assertEqual(evidence.digest, found.body_digest)
                self.assertEqual(evidence.achievement_evidence_id, history.record_identity(paths.HISTORY_ACHIEVEMENTS,
                                                                                           found))
                self.put_achievement(evidence)
                self.assertEqual(found, self.review.read_achievement(found.achievement_evidence_id))
                self.assertTrue(self.review.achievement_exists(found.achievement_evidence_id))
                self.assertEqual(serialize.digest(record), self.review.achievement_digest(found.achievement_evidence_id))
        self.assertEqual((body.achievement_evidence_id, roadmap.achievement_evidence_id), self.review.achievement_ids())
        self.assertEqual([body, roadmap], [item.evidence for item in self.review.achievement_records()])
        self.assertEqual([], self.codes_beyond(run_gaps),
                         "both records valid: the phase record's Integration Run is laid down")

    def test_the_history_reader_checks_the_review_achievement_id_kind(self) -> None:
        """MC-16 / D-13: the body checks a public-safe label; the history record requires the ``rha`` kind."""
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        labelled = phase_evidence(basis, unlaid_ref(basis), satisfied(basis), evidence_id="test-achievement-1")
        with self.assertRaises(ValidationError) as raised:
            history.achievement_record(labelled)
        self.assertEqual("review_record_invalid", raised.exception.code)
        roadmap = roadmap_evidence(b, [phase_evidence(basis, unlaid_ref(basis), satisfied(basis))])
        fields = {name: getattr(roadmap, name) for name in roadmap.__dataclass_fields__}
        fields.update(phase_evidence_refs=tuple((p, "test-achievement-1", d) for p, _, d in roadmap.phase_evidence_refs),
                      decision_evidence_refs=("test-achievement-1",))
        foreign = ach.RoadmapAchievementEvidence(**fields)
        foreign = ach.RoadmapAchievementEvidence(**dict(fields, decision_digest=foreign.decision().digest))
        self.assertEqual([], foreign.problems(), "the body alone is valid")
        with self.assertRaises(ValidationError):
            history.achievement_record(foreign)

    def test_the_record_is_strict(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        base = history.achievement_record(phase_evidence(basis, unlaid_ref(basis), satisfied(basis))).to_record()
        for name, change in {
            "unknown kind": {"kind": "phase_achieved"},
            "unhashable kind": {"kind": ["phase_completion"]},
            "roadmap kind over a phase body": {"kind": ach.KIND_ROADMAP_ACHIEVEMENT},
            "other contract": {"history_contract": "review-v1-history-v2"},
            "unknown field": {"transcript": "the whole chat"},
            "legacy mode": {"completion_mode": "legacy"},
        }.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                history.parse_history(paths.HISTORY_ACHIEVEMENTS, {**base, **change}, name)
        with self.assertRaises(ValidationError) as raised:
            history.parse_history(paths.HISTORY_ACHIEVEMENTS, {**base, "version": 2}, "later")
        self.assertEqual("review_record_version", raised.exception.code)

    def test_every_nested_mapping_of_both_bodies_is_a_closed_field_set(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b, confirmation=True)
        basis = ach.phase_basis(b.view(), phase)
        body = phase_evidence(basis, unlaid_ref(basis), satisfied(basis))
        legacy = b.phase("Legacy")
        work, integration = b.work(legacy), b.integration(legacy, marker=None)
        b.requires(work, integration)
        b.complete(work, integration)
        roadmap = roadmap_evidence(b, [body])
        self.assertTrue(roadmap.legacy_phase_facts and body.downstream_confirmations)
        nested = 0
        for evidence in (body, roadmap):
            base = history.achievement_record(evidence).to_record()
            for key, value in base.items():
                items = [value] if isinstance(value, dict) else value if isinstance(value, list) else []
                for index, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    nested += 1
                    changed = [dict(entry) for entry in value] if isinstance(value, list) else dict(value)
                    target = changed[index] if isinstance(changed, list) else changed
                    target["notes"] = "free text"
                    with self.subTest(kind=evidence.kind, field=key), self.assertRaises(ValidationError):
                        history.parse_history(paths.HISTORY_ACHIEVEMENTS, {**base, key: changed}, key)
        self.assertGreaterEqual(nested, 6)

    def test_an_unreadable_record_fails_the_reader_closed(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        body = self.evidence(ach.phase_basis(b.view(), phase))
        self.put(paths.history_achievement_rel(ident("rha", 77)), raw=b"schema: x\n")
        with self.assertRaises(ValidationError):
            self.review.phase_completion_evidence()
        with self.assertRaises(ValidationError):
            achievement_reader.phase_progression(b.view(), self.review, phase)
        self.assertIn("review_record_invalid", self.codes())
        self.assertEqual(body, self.review.read_achievement(body.achievement_evidence_id).evidence)


class AchievementValidityTests(Directory):
    def test_two_records_for_one_phase_basis_are_a_conflict(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        ref, outcome = self.integration_run(basis)  # §32.49: validation reads the source refs too
        run_gaps = self.codes()
        self.put_achievement(phase_evidence(basis, ref, outcome, 1))
        self.assertEqual([], self.codes_beyond(run_gaps))
        self.put_achievement(phase_evidence(basis, ref, outcome, 2))
        self.assertEqual(["review_record_conflict"], self.codes_beyond(run_gaps), "only the duplicate: both sources hold")
        self.assertIn(history.PROBLEM_CONFLICT,
                      [code for code, _ in history.history_problems(self.review, work_ids=None)])

    def test_two_valid_records_for_one_basis_are_never_ready(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        self.evidence(basis, 1)
        self.evidence(basis, 2)
        decision = achievement_reader.phase_progression(b.view(), self.review, phase)
        self.assertFalse(decision.ready)
        self.assertEqual(ach.EVIDENCE_CONFLICT, decision.match.status)

    def test_a_roadmap_record_cites_stored_phase_evidence_by_its_body_digest(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        ref, outcome = self.integration_run(basis)  # §32.49: validation reads the phase record's source refs
        run_gaps = self.codes()
        body = phase_evidence(basis, ref, outcome)
        roadmap = roadmap_evidence(b, [body])
        self.put_achievement(roadmap)
        self.assertIn("review_record_missing", self.codes_beyond(run_gaps), "the cited phase evidence is not stored")
        self.put_achievement(body)
        self.assertEqual([], self.codes_beyond(run_gaps))
        other = phase_evidence(basis, ref, outcome, 3)
        (self.root / paths.history_achievement_rel(body.achievement_evidence_id)).unlink()
        self.put(paths.history_achievement_rel(body.achievement_evidence_id),
                 history.achievement_record(ach.PhaseCompletionEvidence(**{
                     **{name: getattr(other, name) for name in other.__dataclass_fields__},
                     "achievement_evidence_id": body.achievement_evidence_id,
                     "rationale": "Another rationale for the same basis."})).to_record())
        self.assertIn("review_record_conflict", self.codes(), "the stored record is not the cited body")

    def test_a_named_human_decision_must_be_stored(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        ref, outcome = self.integration_run(basis)  # RB5PSWR-1: the sources hold, so only the decision is missing
        run_gaps = self.codes()
        body = phase_evidence(basis, ref, outcome)
        self.put_achievement(body)
        self.assertEqual([], self.codes_beyond(run_gaps))
        roadmap_basis = ach.roadmap_basis(b.view(), b.roadmap_id, [body], human_decision_ref=ident("rhd", 5))
        decision = ach.RoadmapAchievementDecision(ach.JUDGEMENT_ACHIEVED, "claude-opus", "5.5", "The goal is met.",
                                                  (body.achievement_evidence_id,), ident("rhd", 5))
        self.put_achievement(ach.build_roadmap_achievement_evidence(
            ident("rha", 60), roadmap_basis, decision, reserved_event_id=ident("evt", 60),
            causing_mutation_id=ident("mut", 60)))
        self.assertEqual(["review_record_missing"], self.codes_beyond(run_gaps))
        self.assertTrue(any(ident("rhd", 5) in problem.message and "Human Decision Evidence" in problem.message
                            for problem in validate.review_problems(self.review)), "the decision, not a source")

    def test_two_roadmap_records_for_one_reserved_event_are_a_conflict(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        body = phase_evidence(basis, unlaid_ref(basis), satisfied(basis))
        self.put_achievement(body)
        first = roadmap_evidence(b, [body], 50)
        self.put_achievement(first)
        self.put_achievement(ach.RoadmapAchievementEvidence(**{
            **{name: getattr(first, name) for name in first.__dataclass_fields__},
            "achievement_evidence_id": ident("rha", 51)}))
        self.assertIn("review_record_conflict", self.codes())


class ProgressionReaderTests(Directory):
    def test_a_reviewed_complete_phase_is_ready_only_with_its_one_current_record(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        view = b.view()
        missing = achievement_reader.phase_progression(view, self.review, phase)
        self.assertEqual((False, True, ach.EVIDENCE_MISSING), (missing.ready, missing.generated_complete,
                                                               missing.match.status))
        body = self.evidence(ach.phase_basis(view, phase))
        ready = achievement_reader.phase_progression(view, self.review, phase)
        self.assertTrue(ready.ready)
        self.assertEqual(body.achievement_evidence_id, ready.match.evidence_id)
        late = b.work(phase, "Late")
        b.complete(late)
        stale = achievement_reader.phase_progression(b.view(), self.review, phase)
        self.assertEqual((False, False), (stale.ready, stale.generated_complete), "late Work reopens the Phase")

    def test_a_legacy_phase_needs_no_evidence(self) -> None:
        b = ViewBuilder()
        phase = b.phase("Legacy")
        work, integration = b.work(phase), b.integration(phase, marker=None)
        b.requires(work, integration)
        b.complete(work, integration)
        found = achievement_reader.phase_progression(b.view(), self.review, phase)
        self.assertTrue(found.ready)
        self.assertEqual("legacy Phase complete", found.reason)

    def test_phase_progression_ready_reads_the_working_project_and_its_review_history(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        view = b.view()
        self.evidence(ach.phase_basis(view, phase))
        with mock.patch.object(state.ProjectView, "load", return_value=view) as load:
            found = achievement_reader.phase_progression_ready(self.store, phase)
        load.assert_called_once_with(self.store)
        self.assertTrue(found.ready)

    def test_the_narrowing_holds_back_a_successor_until_the_evidence_exists(self) -> None:
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        successor = b.phase("Next")
        b.requires(phase, successor)
        view = b.view()
        held = achievement_reader.progression_narrowing(view, self.review, [view.phases[successor]])
        self.assertEqual((), held.ready)
        self.assertEqual([(successor, phase)], [(c, p) for c, p, _ in held.blocked])
        self.evidence(ach.phase_basis(view, phase))
        free = achievement_reader.progression_narrowing(view, self.review, [view.phases[successor]])
        self.assertEqual([successor], [entity.id for entity in free.ready])

    def test_the_candidate_refs_are_the_current_evidence_of_the_reviewed_predecessors(self) -> None:
        b = ViewBuilder()
        reviewed, _, _, _ = reviewed_phase(b)
        legacy = b.phase("Legacy")
        work, integration = b.work(legacy), b.integration(legacy, marker=None)
        b.requires(work, integration)
        b.complete(work, integration)
        target, _, _, _ = reviewed_phase(b, complete=False)
        b.requires(reviewed, target)
        b.requires(legacy, target)
        view = b.view()
        self.assertEqual((), achievement_reader.candidate_achievement_refs(view, self.review, target),
                         "a reviewed predecessor without ready evidence contributes nothing")
        body = self.evidence(ach.phase_basis(view, reviewed))
        refs = achievement_reader.candidate_achievement_refs(view, self.review, target)
        self.assertEqual(((reviewed, body.achievement_evidence_id, body.digest),), refs)
        self.assertEqual((), achievement_reader.candidate_achievement_refs(view, self.review, reviewed))
        with self.assertRaises(ValidationError):
            achievement_reader.candidate_achievement_refs(view, self.review, ident("p", 999))

    def test_the_reader_is_read_only_and_reaches_no_history_module(self) -> None:
        text = Path(achievement_reader.__file__).read_text(encoding="utf-8")
        for forbidden in ("mutation", "oplock", "gitcmd", "gitops", "durable", "write_", "reserve_id", "history"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(f"import {forbidden}", text)
                self.assertNotIn(f"{forbidden}(", text)


class CommittedAchievementTests(WorklineTestCase):
    def test_the_committed_reader_reads_the_family_and_its_sources_from_git_objects(self) -> None:
        repo = self.new_dir("repo")
        git(repo, "init", "-b", "main")
        b = ViewBuilder()
        phase, _, _, _ = reviewed_phase(b)
        basis = ach.phase_basis(b.view(), phase)
        laid = Directory("run")
        laid.root, laid.store = repo, ProjectStore(repo)
        laid.review = ReviewStore(laid.store)
        body = laid.evidence(basis)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "achievement and its Integration Run")
        head = git(repo, "rev-parse", "HEAD").strip()
        (repo / paths.history_achievement_rel(body.achievement_evidence_id)).unlink()
        committed = CommittedReviewStore(repo, head)
        self.assertEqual((body.achievement_evidence_id,), committed.achievement_ids())
        self.assertEqual(body, committed.read_achievement(body.achievement_evidence_id).evidence)
        self.assertEqual((body,), committed.phase_completion_evidence())
        self.assertTrue(achievement_reader.phase_progression(b.view(), committed, phase).ready)
        self.assertEqual((), ReviewStore(ProjectStore(repo)).phase_completion_evidence(), "the working tree lost it")


# --------------------------------------------------------------------------- I-4: registration (OQ-B)


class RegistrationTests(unittest.TestCase):
    def test_the_contract_is_a_p4_family_contract_with_no_repair_batch_branch(self) -> None:
        contract = records.P4_PHASE_INTEGRATION_CONTRACT
        self.assertEqual("review-v1-phase-integration-p4-v1", contract)
        self.assertIn(contract, records.P4_CONTRACTS)
        self.assertNotIn(contract, records.P4_REPAIR_CONTRACTS)
        self.assertFalse(p4.repairs(contract))
        self.assertIs(p4.CONTRACTS, records.P4_CONTRACTS)

    def test_the_contract_binds_the_p6_capable_family_policy_only(self) -> None:
        contract = records.P4_PHASE_INTEGRATION_CONTRACT
        self.assertEqual((p4.P6_POLICY_ID,), p4.CONTRACT_POLICIES[contract])
        self.assertIsNone(p4.contract_policy_problem(contract, p4.P6_POLICY_ID))
        for other in (p4.POLICY_ID, p4.P5_POLICY_ID, "review-v1-unknown"):
            with self.subTest(policy=other):
                self.assertIn("always a new P6-capable Run", str(p4.contract_policy_problem(contract, other)))
        self.assertEqual(contract, p4.contract_of_envelope(dict(INTEGRATION_ENVELOPE)))
        self.assertIsNone(p4.contract_of_envelope({**INTEGRATION_ENVELOPE, "policy_id": p4.P5_POLICY_ID}))

    def test_every_restricted_contract_states_its_own_refusal_reason(self) -> None:
        """RB5PSW-3: the refusal text is mandatory per contract - a CONTRACT_POLICIES key without its
        _CONTRACT_POLICY_REASONS entry fails here, never as a KeyError at a Run open. A later contract (RB7's root
        meta-review one among them) adds its reason with its policy."""
        self.assertEqual(set(p4.CONTRACT_POLICIES), set(p4._CONTRACT_POLICY_REASONS))
        for contract, allowed in p4.CONTRACT_POLICIES.items():
            with self.subTest(contract=contract):
                refused = p4.contract_policy_problem(contract, "review-v1-unknown")
                self.assertTrue(str(refused).endswith(p4._CONTRACT_POLICY_REASONS[contract]))
                self.assertIsNone(p4.contract_policy_problem(contract, allowed[0]))

    def test_h1_the_p6_family_record_is_untouched(self) -> None:
        self.assertNotIn(records.P4_PHASE_INTEGRATION_CONTRACT, p4.P6_POLICY_RECORD["review_contracts"])
        self.assertEqual([p4.PLANNING_CONTRACT, p4.WORK_CONTRACT, records.P6_POLICY_CHANGE_CONTRACT],
                         p4.P6_POLICY_RECORD["review_contracts"])

    def test_the_policy_review_refusal_text_is_rb6s_byte_for_byte(self) -> None:
        self.assertEqual(
            f"{records.P6_POLICY_CHANGE_CONTRACT} Runs bind the {p4.P6_POLICY_ID} family policy, never "
            f"{p4.P5_POLICY_ID!r}: a Policy Review is reviewed under the pre-change Effective Policy only a P6-capable "
            "Run freezes", p4.contract_policy_problem(records.P6_POLICY_CHANGE_CONTRACT, p4.P5_POLICY_ID))

    def test_the_shared_vocabularies_are_the_rb5_cores(self) -> None:
        self.assertEqual(ri.REVIEW_KIND, records.INTEGRATION_REVIEW_KIND)
        self.assertEqual(ri.PHASE_OUTCOMES, records.INTEGRATION_PHASE_OUTCOMES)
        self.assertEqual(ri.AUTHORIZING_PHASE_OUTCOMES,
                         (records.INTEGRATION_OBJECTIVELY_SATISFIED, records.INTEGRATION_HUMAN_CONFIRMATION_REQUIRED))
        self.assertEqual(set(ri.BRANCHES) | {ri.CODE_UNCOVERED, ri.CODE_NOT_AUTHORIZABLE},
                         set(records.INTEGRATION_DISPOSITIONS))
        self.assertEqual({ri.BRANCH_DOMAIN_REPAIR_REQUIRED, ri.BRANCH_CONFIRMATION_STRUCTURE_REQUIRED, ri.CODE_UNCOVERED,
                          ri.CODE_NOT_AUTHORIZABLE}, set(records.INTEGRATION_G4_TERMINAL_DISPOSITIONS))
        self.assertEqual(ri.STRATEGY_ID_PATTERN.pattern, history.STRATEGY_ID_PATTERN.pattern)
        self.assertEqual(("outcome", "phase_desired_state_digest", "rationale", "unmet_objective_obligations"),
                         tuple(ri.PhaseOutcome("x", "d", "r").to_record()))
        self.assertEqual(tuple(ri.PhaseOutcome("x", "d", "r").to_record()), records.INTEGRATION_PHASE_OUTCOME_FIELDS)
        self.assertIn(records.INTEGRATION_REVIEW_KIND, history.G4_TERMINAL_REVIEW_KINDS)
        self.assertEqual(records.POLICY_REVIEW_KIND, history.G4_TERMINAL_REVIEW_KINDS[0], "RB6's kind stays first")


# --------------------------------------------------------------------------- I-4: the version 5 Consumption (R14)


class IntegrationConsumptionTests(Directory):
    def consumption(self, **changes: object) -> dict:
        base = records.IntegrationConsumption(
            ident("rcs", 1), ident("rcp", 1), ident("rr", 1), 5, records.INTEGRATION_REVIEW_KIND, "a" * 64, OPERATION,
            ident("mut", 1), ident("evt", 1), "work_completed", ident("w", 1),
        ).to_record()
        return {**base, **changes}

    def test_version_5_reads_only_its_own_strict_shape(self) -> None:
        record = self.consumption()
        found = records.consumption_from_record(record, "v5")
        self.assertIsInstance(found, records.IntegrationConsumption)
        self.assertEqual(record, found.to_record())
        self.assertEqual((True, ident("w", 1), None, None), (found.work_kind, found.work_id,
                                                              found.authorized_result_commit_sha, found.artifact_kind))
        for name, change in {
            "another kind": {"review_kind": "work-result-v1"},
            "another event": {"terminal_event_type": "work_cancelled"},
            "a result commit": {"authorized_result_commit_sha": "0" * 40},
            "no terminal event": {"terminal_event_id": None},
            "a Phase target": {"target_identity": ident("p", 1)},
            "an event target": {"terminal_event_id": ident("w", 2)},
        }.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                records.consumption_from_record(self.consumption(**change), name)
        v1 = records.Consumption(
            ident("rcs", 1), ident("rcp", 1), ident("rr", 1), 5, records.INTEGRATION_REVIEW_KIND, "a" * 64, OPERATION,
            ident("mut", 1), ident("evt", 1), "work_completed", ident("w", 1), None, "empty").to_record()
        with self.assertRaises(ValidationError):
            records.consumption_from_record({**v1, "version": 5}, "a v1 shape at version 5")
        with self.assertRaises(ValidationError):
            records.consumption_from_record({**record, "version": 1}, "a v5 shape at version 1")
        with self.assertRaises(ValidationError) as raised:
            records.consumption_from_record({**record, "version": 4}, "version 4")
        # composition with landed RB7: version 4 is P7's Global Policy Consumption, whose strict reader refuses this shape
        self.assertEqual("review_record_invalid", raised.exception.code,
                         "version 4 is read by P7's GlobalPolicyConsumption reader, which refuses a version 5 shape")

    def test_one_terminal_event_has_one_consumption_whatever_its_version(self) -> None:
        self.put(paths.consumption_rel(ident("rcs", 1)), self.consumption())
        work = records.Consumption(
            ident("rcs", 2), ident("rcp", 2), ident("rr", 2), 3, "work-result-v1", "a" * 64, OPERATION, ident("mut", 2),
            ident("evt", 1), "work_completed", ident("w", 1), None, "empty")
        self.put(paths.consumption_rel(ident("rcs", 2)), work.to_record())
        with self.assertRaises(ValidationError) as raised:
            self.review.consumption_by_terminal_event()
        self.assertEqual("review_consumption_conflict", raised.exception.code)


class IntegrationConsumptionActivationTests(activation_tests.ActivationCase):
    """RB5PSW-4 / §32.31 over an activated disposable Project: the completion totality binds no version 5
    Integration Consumption to an event, because the reviewed integration's own ``work_completed`` is ordinary and
    unmarked. Its event binding is the terminal START stage's (RB5 I-5 / I-6), never ``activation_problems``'."""

    def integration_consumption(self) -> dict:
        return records.IntegrationConsumption(
            ident("rcs", 1), ident("rcp", 1), ident("rr", 1), 5, records.INTEGRATION_REVIEW_KIND, "a" * 64, OPERATION,
            ident("mut", 1), activation_tests.EVENT_ID, "work_completed", ident("w", 1)).to_record()

    def test_an_integration_consumption_naming_an_absent_event_is_never_unbound(self) -> None:
        self.activate()
        work = paths.consumption_rel(activation_tests.CONSUMPTION_ID)
        self.put_record(work, activation_tests.consumption_record())
        self.assertEqual([validate.CONSUMPTION_UNBOUND], self.totality(), "a version 1 Work Consumption is bound")
        (self.root / work).unlink()
        self.put_record(paths.consumption_rel(ident("rcs", 1)), self.integration_consumption())
        self.assertEqual([], self.totality(), "its event is absent: no CONSUMPTION_UNBOUND (§32.31)")
        self.append_events(activation_tests.legacy_completion(activation_tests.EVENT_ID, ident("w", 1)))
        self.assertEqual([], self.totality(), "its event is the integration's ordinary, unmarked completion")


# --------------------------------------------------------------------------- I-4: the Integration adjudication (R14 / R17)


class IntegrationAdjudicationTests(unittest.TestCase):
    OUTCOME = ri.PhaseOutcome(ri.OBJECTIVELY_SATISFIED, "d" * 64, "The Phase objective holds.")

    def test_the_integration_contract_carries_one_phase_outcome_and_its_g4_disposition_at_version_2(self) -> None:
        found = integration_adjudication(self.OUTCOME, records.AUTHORIZATION_READY)
        record = found.to_record()
        self.assertEqual(records.P4_INTEGRATION_ADJUDICATION_VERSION, record["version"])
        self.assertEqual(self.OUTCOME.to_record(), record["phase_outcome"])
        self.assertEqual(self.OUTCOME.digest, serialize.digest(found.phase_outcome))
        self.assertEqual(records.AUTHORIZATION_READY, found.integration_disposition)
        self.assertEqual(found, records.P4Adjudication.from_record(record, "round trip"))
        self.assertEqual([], p4.adjudication_problems(found))
        with self.assertRaises(ValidationError):
            records.P4Adjudication.from_record({**record, "version": 1}, "the integration contract at version 1")
        with self.assertRaises(ValidationError):
            records.P4Adjudication.from_record({k: v for k, v in record.items() if k != "integration_disposition"}, "x")

    def test_every_other_contract_is_version_1_byte_for_byte(self) -> None:
        reports = bound(report(TASK_A, "correctness", [("HIGH", "x", "claim one")]))
        normalized = p4.normalize_adjudication(returned(disposition(TASK_A, 0, p4.OUTCOME_UNSUPPORTED)), DESCRIPTOR,
                                               reports, None)
        work = p4.adjudication(normalized, [], review_run_id=ident("rr", 1), gate_record=gate(), candidate_generation=1,
                               review_contract=p4.WORK_CONTRACT, descriptor=DESCRIPTOR, reports=reports, prior=None)
        record = work.to_record()
        self.assertEqual(records.VERSION, record["version"])
        self.assertEqual(set(records.P4_ADJUDICATION_FIELDS), set(record))
        self.assertEqual((None, None), (work.phase_outcome, work.integration_disposition))
        with self.assertRaises(ValidationError):
            p4.adjudication(normalized, [], review_run_id=ident("rr", 1), gate_record=gate(), candidate_generation=1,
                            review_contract=p4.WORK_CONTRACT, descriptor=DESCRIPTOR, reports=reports, prior=None,
                            phase_outcome=self.OUTCOME, integration_disposition=records.AUTHORIZATION_READY)
        with self.assertRaises(ValidationError):
            records.P4Adjudication.from_record({**record, "version": 2, "phase_outcome": self.OUTCOME.to_record(),
                                                "integration_disposition": records.AUTHORIZATION_READY}, "x")

    def test_the_disposition_is_the_one_the_frozen_order_allows(self) -> None:
        """§32.22 / CPQ-04 as far as the record alone can prove it; the Candidate half is the owner's derivation."""
        hcr = ri.PhaseOutcome(ri.HUMAN_CONFIRMATION_REQUIRED, "d" * 64, "A Human confirms the Phase.")
        unmet = ri.PhaseOutcome(ri.NOT_SATISFIED, "d" * 64, "The objective is not met.", ("objective-a",))
        change = ri.PhaseOutcome(ri.DESIRED_STATE_CHANGE_REQUIRED, "d" * 64, "The objective must change.")
        allowed = [
            (self.OUTCOME, records.AUTHORIZATION_READY, p4.OUTCOME_UNSUPPORTED),
            (self.OUTCOME, ri.CODE_UNCOVERED, p4.OUTCOME_UNSUPPORTED),
            (self.OUTCOME, ri.CODE_NOT_AUTHORIZABLE, p4.OUTCOME_UNSUPPORTED),
            (hcr, ri.BRANCH_CONFIRMATION_STRUCTURE_REQUIRED, p4.OUTCOME_UNSUPPORTED),
            (hcr, records.AUTHORIZATION_READY, p4.OUTCOME_UNSUPPORTED),
            (unmet, ri.BRANCH_DOMAIN_REPAIR_REQUIRED, p4.OUTCOME_UNSUPPORTED),
            (unmet, ri.BRANCH_DOMAIN_REPAIR_REQUIRED, p4.OUTCOME_PROBLEM),
            (change, records.HUMAN_WAIT, p4.OUTCOME_HUMAN),
            (self.OUTCOME, records.HUMAN_WAIT, p4.OUTCOME_HUMAN),
        ]
        for outcome, branch, claim in allowed:
            with self.subTest(allowed=(outcome.outcome, branch, claim)):
                integration_adjudication(outcome, branch, claim=claim)
        refused = [
            (self.OUTCOME, ri.BRANCH_CONFIRMATION_STRUCTURE_REQUIRED, p4.OUTCOME_UNSUPPORTED),
            (self.OUTCOME, ri.BRANCH_DOMAIN_REPAIR_REQUIRED, p4.OUTCOME_UNSUPPORTED),
            (self.OUTCOME, records.HUMAN_WAIT, p4.OUTCOME_UNSUPPORTED),
            (self.OUTCOME, records.AUTHORIZATION_READY, p4.OUTCOME_PROBLEM),
            (self.OUTCOME, records.AUTHORIZATION_READY, p4.OUTCOME_HUMAN),
            (unmet, records.AUTHORIZATION_READY, p4.OUTCOME_UNSUPPORTED),
            (unmet, ri.CODE_UNCOVERED, p4.OUTCOME_UNSUPPORTED),
            (change, records.AUTHORIZATION_READY, p4.OUTCOME_UNSUPPORTED),
            (ri.PhaseOutcome(ri.NOT_SATISFIED, "d" * 64, "Unsupported."), ri.BRANCH_DOMAIN_REPAIR_REQUIRED,
             p4.OUTCOME_UNSUPPORTED),
            (ri.PhaseOutcome(ri.OBJECTIVELY_SATISFIED, "d" * 64, "x", ("objective-a",)), records.AUTHORIZATION_READY,
             p4.OUTCOME_UNSUPPORTED),
            (self.OUTCOME, "REPAIR_REQUIRED", p4.OUTCOME_UNSUPPORTED),
            (None, records.AUTHORIZATION_READY, p4.OUTCOME_UNSUPPORTED),
            (self.OUTCOME, None, p4.OUTCOME_UNSUPPORTED),
            ({"outcome": ri.OBJECTIVELY_SATISFIED}, records.AUTHORIZATION_READY, p4.OUTCOME_UNSUPPORTED),
        ]
        for outcome, branch, claim in refused:
            with self.subTest(refused=(getattr(outcome, "outcome", outcome), branch, claim)), \
                    self.assertRaises(ValidationError):
                integration_adjudication(outcome, branch, claim=claim)


# --------------------------------------------------------------------------- I-4: the G4-terminal path (OQ-C, R15 / R16)


class StubReader:
    """A read-only Review reader over in-memory records (the shared functions take any reader)."""

    def __init__(self, adjudication: records.P4Adjudication | None, envelope: dict | None = None,
                 consumptions: tuple = (), receipts: dict | None = None) -> None:
        self.adjudication, self.envelope = adjudication, envelope or dict(INTEGRATION_ENVELOPE)
        self._consumptions, self.receipts = consumptions, receipts or {}

    def read_task_input(self, task_id: str) -> SimpleNamespace:
        return SimpleNamespace(request_envelope=dict(self.envelope), task_kind=p4.TASK_KIND_DISCOVERY)

    def adjudication_exists(self, run: str) -> bool:
        return self.adjudication is not None

    def read_adjudication(self, run: str) -> records.P4Adjudication:
        assert self.adjudication is not None
        return self.adjudication

    def history_exists(self, family: str, identifier: str) -> bool:
        return False

    def consumption_by_receipt(self) -> dict:
        return {}

    def consumptions(self) -> tuple:
        return self._consumptions

    def read_receipt(self, receipt_id: str) -> records.Receipt:
        return self.receipts[receipt_id]


def stub_chain(adjudication: records.P4Adjudication, count: int) -> GateChain:
    run, integration = adjudication.review_run_id, adjudication.target_identity
    found = generations(run, integration, adjudication.candidate_hash, serialize.digest(adjudication.to_record()),
                        count, receipt_id=ident("rcp", 1))
    task = {"task_id": ident("rtk", 1)}
    found = [records.GateGeneration(**{**{name: getattr(item, name) for name in item.__dataclass_fields__},
                                       "accepted_tasks": (task,)}) for item in found]
    return GateChain(run, tuple(found), tuple(serialize.digest(item.to_record()) for item in found))


class G4TerminalTests(Directory):
    HCR = ri.PhaseOutcome(ri.HUMAN_CONFIRMATION_REQUIRED, "d" * 64, "A Human confirms the Phase.")

    def terminal(self, branch: str = ri.BRANCH_CONFIRMATION_STRUCTURE_REQUIRED) -> records.P4Adjudication:
        outcome = self.HCR if branch == ri.BRANCH_CONFIRMATION_STRUCTURE_REQUIRED else \
            ri.PhaseOutcome(ri.OBJECTIVELY_SATISFIED, "d" * 64, "The Phase objective holds.")
        return integration_adjudication(outcome, branch)

    def test_the_one_narrow_predicate(self) -> None:
        for branch in records.INTEGRATION_G4_TERMINAL_DISPOSITIONS:
            if branch == ri.BRANCH_DOMAIN_REPAIR_REQUIRED:
                found = integration_adjudication(
                    ri.PhaseOutcome(ri.NOT_SATISFIED, "d" * 64, "Not met.", ("objective-a",)), branch)
            else:
                found = self.terminal(branch)
            with self.subTest(branch=branch):
                self.assertTrue(history.g4_terminal_adjudication(found))
        self.assertFalse(history.g4_terminal_adjudication(integration_adjudication(self.HCR, records.AUTHORIZATION_READY)))
        self.assertFalse(history.g4_terminal_adjudication(None))
        reports = bound(report(TASK_A, "correctness", [("HIGH", "x", "claim one")]))
        normalized = p4.normalize_adjudication(returned(disposition(TASK_A, 0, p4.OUTCOME_UNSUPPORTED)), DESCRIPTOR,
                                               reports, None)
        work = p4.adjudication(normalized, [], review_run_id=ident("rr", 1), gate_record=gate(), candidate_generation=1,
                               review_contract=p4.WORK_CONTRACT, descriptor=DESCRIPTOR, reports=reports, prior=None)
        self.assertFalse(history.g4_terminal_adjudication(work), "a Work Run is never G4-terminal")

    def test_g4_history_writes_the_not_authorized_summary_in_that_g4(self) -> None:
        for branch in (ri.BRANCH_CONFIRMATION_STRUCTURE_REQUIRED, ri.CODE_UNCOVERED, ri.CODE_NOT_AUTHORIZABLE):
            found = self.terminal(branch)
            gate_four = stub_chain(found, 4).latest
            with self.subTest(branch=branch):
                written = p4.g4_history(found, gate_four, (), (), ())
                summary = written.run_summary
                self.assertEqual(history.DISPOSITION_NOT_AUTHORIZED, summary.durable_disposition)
                self.assertEqual(serialize.digest(found.to_record()), summary.adjudication_digest)
                self.assertEqual((None, None, None), (summary.receipt_id, summary.consumption_id, summary.repair_batch_id))
                self.assertEqual(summary, history.RunSummary.from_record(summary.to_record(), "the G4 summary"))
                self.assertIn(paths.history_run_rel(found.review_run_id), [path for path, _ in written.extra()])
        ready = integration_adjudication(self.HCR, records.AUTHORIZATION_READY)
        self.assertIsNone(p4.g4_history(ready, stub_chain(ready, 4).latest, (), (), ()).run_summary)

    def test_the_run_is_final_not_authorized_and_its_summary_is_its_own_history(self) -> None:
        found = self.terminal()
        chain = stub_chain(found, 4)
        reader = StubReader(found)
        self.assertEqual(history.DISPOSITION_NOT_AUTHORIZED, p4.own_summary_disposition(reader, chain))
        self.assertEqual(history.DISPOSITION_NOT_AUTHORIZED, p4.final_disposition(reader, chain),
                         "never recoverable as authorizable; no successor writes a set_aside summary for it")
        self.assertIn(paths.history_run_rel(found.review_run_id), p4.run_history_paths(reader, found.review_run_id, chain))
        ready = integration_adjudication(self.HCR, records.AUTHORIZATION_READY)
        self.assertIsNone(p4.own_summary_disposition(StubReader(ready), stub_chain(ready, 4)))

    def test_rb6s_policy_kind_keeps_its_reading(self) -> None:
        """The P6 Policy Review's G4-terminal Run: its own summary disposition stays None (unchanged)."""
        item = dict(report(TASK_A, "correctness", [("HIGH", "x", "claim one")]))
        item.update(review_kind=records.POLICY_REVIEW_KIND, review_contract=records.P6_POLICY_CHANGE_CONTRACT)
        reports = bound(serialize.canonical_data(item))
        normalized = p4.normalize_adjudication(returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM)), DESCRIPTOR,
                                               reports, None)
        policy = p4.adjudication(
            normalized, finding_ids(len(normalized.drafts)), review_run_id=ident("rr", 1),
            gate_record=gate(review_run_id=ident("rr", 1), review_kind=records.POLICY_REVIEW_KIND),
            candidate_generation=1, review_contract=records.P6_POLICY_CHANGE_CONTRACT, descriptor=DESCRIPTOR,
            reports=reports, prior=None, policy_id=p4.P6_POLICY_ID)
        self.assertEqual(records.REPAIR_REQUIRED, policy.outcome)
        self.assertTrue(history.g4_terminal_adjudication(policy))
        chain = GateChain(ident("rr", 1), tuple(
            records.GateGeneration(**{**{name: getattr(item, name) for name in item.__dataclass_fields__},
                                      "review_kind": records.POLICY_REVIEW_KIND})
            for item in stub_chain(policy, 4).generations), ("0" * 64,) * 4)
        self.assertIsNone(p4.own_summary_disposition(StubReader(policy), chain))

    def test_the_source_validation_and_the_g4_findings_readiness_require_the_summary(self) -> None:
        found = self.terminal()
        chain = generations(found.review_run_id, found.target_identity, found.candidate_hash,
                            serialize.digest(found.to_record()), 4)
        for item in chain:
            self.put(paths.gate_rel(found.review_run_id, item.generation), item.to_record())
        self.put(paths.adjudication_rel(found.review_run_id), found.to_record())
        ready = history.readiness_problems(self.review, found.review_run_id, history.BOUNDARY_FINDINGS,
                                           history_contract=history.HISTORY_CONTRACT)
        self.assertIn(history.PROBLEM_MISSING, [code for code, _ in ready], "the P5 Run summary is REQUIRED")
        summary = p4.g4_history(found, chain[-1], (), (), ()).run_summary
        self.put(paths.history_run_rel(found.review_run_id), summary.to_record())
        self.assertEqual([], history.readiness_problems(self.review, found.review_run_id, history.BOUNDARY_FINDINGS,
                                                        history_contract=history.HISTORY_CONTRACT))
        self.assertEqual([], history.run_summary_problems(self.review, summary))

    def test_validation_refuses_a_seal_after_a_terminal_g4_and_a_kind_contract_mismatch(self) -> None:
        found = self.terminal()
        self.assertEqual([], validate._integration_records(StubReader(found), {found.review_run_id: stub_chain(found, 4)}))
        sealed = validate._integration_records(StubReader(found), {found.review_run_id: stub_chain(found, 5)})
        self.assertEqual(["review_gate_chain"], [problem.code for problem in sealed])
        ready = integration_adjudication(self.HCR, records.AUTHORIZATION_READY)
        self.assertEqual([], validate._integration_records(StubReader(ready), {ready.review_run_id: stub_chain(ready, 5)}))
        for name, envelope in {
            "P5 policy": {**INTEGRATION_ENVELOPE, "policy_id": p4.P5_POLICY_ID},
            "Work contract": {**INTEGRATION_ENVELOPE, "review_contract": p4.WORK_CONTRACT},
        }.items():
            with self.subTest(name):
                problems = validate._integration_records(StubReader(ready, envelope),
                                                         {ready.review_run_id: stub_chain(ready, 4)})
                self.assertEqual(["review_record_conflict"], [problem.code for problem in problems])

    def test_validation_keys_the_consumption_version_on_the_receipt(self) -> None:
        receipt = records.Receipt(
            receipt_id=ident("rcp", 1), review_run_id=ident("rr", 1), review_generation=5,
            review_kind=records.INTEGRATION_REVIEW_KIND, target_identity=ident("w", 1), operation_identity=OPERATION,
            authorized_candidate_hash="a" * 64, review_context_hash=CONTEXT, effective_policy_hash=POLICY_HASH,
            coverage_hash=FILLER, adjudication_hash=FILLER, obligation_digest=FILLER, unresolved_obligations=0,
            authorized_operation_stage=ri.AUTHORIZED_OPERATION_STAGE)
        v5 = records.IntegrationConsumption(
            ident("rcs", 1), ident("rcp", 1), ident("rr", 1), 5, records.INTEGRATION_REVIEW_KIND, "a" * 64, OPERATION,
            ident("mut", 1), ident("evt", 1), "work_completed", ident("w", 1))
        v1 = records.Consumption(
            ident("rcs", 1), ident("rcp", 1), ident("rr", 1), 5, records.INTEGRATION_REVIEW_KIND, "a" * 64, OPERATION,
            ident("mut", 1), ident("evt", 1), "work_completed", ident("w", 1), None, "empty")
        self.assertEqual([], validate._integration_records(StubReader(None, consumptions=(v5,),
                                                                      receipts={receipt.receipt_id: receipt}), {}))
        for name, consumption, stored in (
            ("v1 of an Integration Receipt", v1, receipt),
            ("v5 of a Work Receipt", v5, records.Receipt(**{**{n: getattr(receipt, n) for n in receipt.__dataclass_fields__},
                                                            "review_kind": "work-result-v1"})),
            ("v5 of another stage", v5, records.Receipt(**{**{n: getattr(receipt, n) for n in receipt.__dataclass_fields__},
                                                           "authorized_operation_stage": "work-terminal"})),
        ):
            with self.subTest(name):
                problems = validate._integration_records(
                    StubReader(None, consumptions=(consumption,), receipts={receipt.receipt_id: stored}), {})
                self.assertEqual(["review_record_conflict"], [problem.code for problem in problems])


# --------------------------------------------------------------------------- I-4: CPQ-05 source references (R18)


class SourceReferenceTests(Directory):
    def setUp(self) -> None:
        super().setUp()
        self.b = ViewBuilder()
        self.phase, _, _, _ = reviewed_phase(self.b)
        self.basis = ach.phase_basis(self.b.view(), self.phase)
        self.ref, self.outcome = self.integration_run(self.basis)
        self.body = phase_evidence(self.basis, self.ref, self.outcome)

    def problems(self, body: ach.PhaseCompletionEvidence | None = None, **kwargs: object) -> list[str]:
        return [code for code, _ in history.integration_ref_problems(self.review, body or self.body, **kwargs)]

    def test_the_four_distinct_digests_and_the_summary_ref_are_the_canonical_records(self) -> None:
        self.assertEqual([], self.problems())
        self.assertEqual([], self.ref.problems())
        self.put_achievement(self.body)
        self.assertEqual((self.body,), self.review.phase_completion_evidence())
        self.assertEqual([], [code for code, _ in history.history_problems(self.review, work_ids=None)
                              if code != history.PROBLEM_MISSING], "only the task-free fixture chain's own gaps")

    def test_every_wrong_reference_is_refused(self) -> None:
        def body_with(**changes: object) -> ach.PhaseCompletionEvidence:
            ref = ach.IntegrationRunRef(**{**{n: getattr(self.ref, n) for n in self.ref.__dataclass_fields__},
                                           **changes})
            return ach.PhaseCompletionEvidence(**{**{n: getattr(self.body, n) for n in self.body.__dataclass_fields__},
                                                  "integration_review": ref})
        for name, changes in {
            "the Run summary digest as the Run digest": {"run_digest": self.ref.run_summary_digest,
                                                         "run_summary_digest": self.ref.run_digest},
            "another Receipt digest": {"receipt_digest": "6" * 64},
            "another Consumption digest": {"consumption_digest": "7" * 64},
            "another Candidate": {"candidate_hash": "8" * 64},
            "an unknown Run": {"review_run_id": ident("rr", 77)},
            "an unknown Consumption": {"consumption_id": ident("rcs", 77)},
        }.items():
            with self.subTest(name):
                self.assertTrue(self.problems(body_with(**changes)))
        other = ach.PhaseCompletionEvidence(**{**{n: getattr(self.body, n) for n in self.body.__dataclass_fields__},
                                               "phase_outcome_digest": "9" * 64})
        self.assertIn(history.PROBLEM_CONFLICT, self.problems(other), "another Phase outcome than the Run judged")

    def test_validation_reports_a_stored_record_whose_source_refs_do_not_hold(self) -> None:
        """§32.49 "source Run / Receipt / Consumption refs", reached from ``validate.review_problems`` (RB5PSW-2):
        Review records only, so a reader-level pass reports what the progression reader would refuse."""
        def named(code: str) -> bool:
            return any(problem.code == code and self.body.achievement_evidence_id in problem.message
                       for problem in validate.review_problems(self.review))
        run_gaps = self.codes()
        self.put_achievement(self.body)
        self.assertEqual([], self.codes_beyond(run_gaps))
        wrong = ach.PhaseCompletionEvidence(**{
            **{n: getattr(self.body, n) for n in self.body.__dataclass_fields__},
            "integration_review": ach.IntegrationRunRef(**{
                **{n: getattr(self.ref, n) for n in self.ref.__dataclass_fields__}, "receipt_digest": "6" * 64})})
        self.put_achievement(wrong)
        self.assertTrue(named("review_record_conflict"), "a Receipt digest the stored Receipt does not have")
        self.put_achievement(phase_evidence(self.basis, unlaid_ref(self.basis, 9), self.outcome))
        self.assertTrue(named("review_record_missing"), "an Integration Run with no gate chain")
        self.put_achievement(self.body)
        self.assertEqual([], self.codes_beyond(run_gaps))
        (self.root / paths.consumption_rel(self.ref.consumption_id)).unlink()
        self.assertTrue(any(self.body.achievement_evidence_id in problem.message
                            for problem in validate.review_problems(self.review)), "its Consumption is gone")

    def test_a_record_with_broken_sources_fails_the_progression_reader_closed(self) -> None:
        self.put_achievement(self.body)
        (self.root / paths.consumption_rel(self.ref.consumption_id)).unlink()
        with self.assertRaises(ValidationError) as raised:
            self.review.phase_completion_evidence()
        self.assertEqual("review_record_invalid", raised.exception.code)
        with self.assertRaises(ValidationError):
            achievement_reader.phase_progression(self.b.view(), self.review, self.phase)

    def test_the_owner_validates_its_own_terminal_stage_before_the_consumption_and_summary_are_stored(self) -> None:
        consumption = self.review.read_consumption(self.ref.consumption_id)
        summary = self.review.read_history(paths.HISTORY_RUNS, self.ref.review_run_id)
        (self.root / paths.consumption_rel(self.ref.consumption_id)).unlink()
        (self.root / paths.history_run_rel(self.ref.review_run_id)).unlink()
        self.assertTrue(self.problems())
        self.assertEqual([], self.problems(consumption=consumption, run_summary=summary))
        owner = history.integration_run_ref_problems(self.review, self.ref, self.outcome, consumption=consumption,
                                                     run_summary=summary)
        self.assertEqual([], owner, "the owner checks the refs and the outcome before it builds the body")
        other = ri.PhaseOutcome(ri.OBJECTIVELY_SATISFIED, str(self.basis.phase_desired_state_digest), "Other text.")
        self.assertIn(history.PROBLEM_CONFLICT, [code for code, _ in history.integration_run_ref_problems(
            self.review, self.ref, other, consumption=consumption, run_summary=summary)])
        self.assertEqual([history.PROBLEM_INVALID], [code for code, _ in history.integration_run_ref_problems(
            self.review, self.ref, "objectively_satisfied")])
        found = ach.phase_completion_evidence_for(
            self.b.view(), self.phase, (), achievement_evidence_id=ident("rha", 1),
            covering_integration_id=self.ref.integration_id, integration_review=self.ref, phase_outcome=self.outcome,
            source_ref_problems=[m for _, m in owner],
            evaluators=EVALUATORS, rationale="Every effective Work is integrated and the Phase objective holds.",
            causing_mutation_id=ident("mut", 1), causing_operation="start", causing_event_ids=[ident("evt", 901)])
        self.assertEqual(self.body, found)

    def test_the_owner_may_not_cite_a_run_that_did_not_authorize(self) -> None:
        terminal = integration_adjudication(
            ri.PhaseOutcome(ri.HUMAN_CONFIRMATION_REQUIRED, str(self.basis.phase_desired_state_digest), "Confirm."),
            ri.BRANCH_CONFIRMATION_STRUCTURE_REQUIRED, run=self.ref.review_run_id, integration=self.ref.integration_id,
            candidate=self.ref.candidate_hash)
        self.put(paths.adjudication_rel(self.ref.review_run_id), terminal.to_record())
        self.assertIn(history.PROBLEM_MISSING, self.problems(), "the G4 the chain settled is not this adjudication")


# --------------------------------------------------------------------------- I-4: fix-Work provenance (R16)


class FixProvenanceTests(Directory):
    def source(self) -> history.FindingSummary:
        found = integration_adjudication(ri.PhaseOutcome(ri.NOT_SATISFIED, "d" * 64, "Not met.", ("objective-a",)),
                                         ri.BRANCH_DOMAIN_REPAIR_REQUIRED, claim=p4.OUTCOME_PROBLEM)
        return history.finding_summary(found, str(found.findings[0]["finding_id"]))

    def test_a_future_work_link_carries_the_integration_provenance_at_version_2(self) -> None:
        source = self.source()
        provenance = ri.IntegrationFixProvenance(source.review_run_id, source.finding_id, "split-parser.v2", ident("w", 9))
        link = history.future_work_link(
            ident("rhr", 1), source, provenance.target_work_id, status=history.CAUSAL_SUPPORTED,
            rationale="The fix Work repairs the Integration Finding.", supporting_evidence_digests=["e" * 64],
            integration_provenance={"source_review_run_id": provenance.source_review_run_id,
                                    "strategy_id": provenance.strategy_id})
        record = link.to_record()
        self.assertEqual(history.RELATION_PROVENANCE_VERSION, record["version"])
        self.assertEqual({"source_review_run_id": source.review_run_id, "strategy_id": "split-parser.v2"},
                         record[history.INTEGRATION_PROVENANCE_KEY])
        self.assertEqual(link, history.Relation.from_record(record, "v2"))
        plain = history.future_work_link(ident("rhr", 2), source, ident("w", 9), status=history.CAUSAL_SUPPORTED,
                                         rationale="Provenance only.", supporting_evidence_digests=["e" * 64])
        self.assertEqual(history.RECORD_VERSION, plain.to_record()["version"])
        self.assertEqual(set(history.RELATION_FIELDS), set(plain.to_record()), "version 1 unchanged")
        for name, change in {
            "bad strategy": {"strategy_id": "Split Parser"},
            "not a Run": {"source_review_run_id": ident("w", 1)},
            "extra key": {"notes": "x"},
        }.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                history.Relation.from_record(
                    {**record, history.INTEGRATION_PROVENANCE_KEY: {**record[history.INTEGRATION_PROVENANCE_KEY],
                                                                     **change}}, name)
        with self.assertRaises(ValidationError):
            history.Relation.from_record({**record, "version": 1}, "provenance at version 1")
        with self.assertRaises(ValidationError):
            history.Relation.from_record({**record, "relation_type": history.RELATION_DOWNSTREAM_ESCAPE}, "other type")

    def test_the_provenance_names_the_integration_run_of_its_source_finding(self) -> None:
        source = self.source()
        self.put(paths.history_finding_rel(source.finding_id), source.to_record())
        found = integration_adjudication(ri.PhaseOutcome(ri.NOT_SATISFIED, "d" * 64, "Not met.", ("objective-a",)),
                                         ri.BRANCH_DOMAIN_REPAIR_REQUIRED, claim=p4.OUTCOME_PROBLEM)
        for item in generations(found.review_run_id, found.target_identity, found.candidate_hash,
                                serialize.digest(found.to_record()), 4):
            self.put(paths.gate_rel(found.review_run_id, item.generation), item.to_record())
        link = history.future_work_link(
            ident("rhr", 1), source, ident("w", 9), status=history.CAUSAL_SUPPORTED, rationale="Fix Work.",
            supporting_evidence_digests=["e" * 64],
            integration_provenance={"source_review_run_id": source.review_run_id, "strategy_id": "s1"})
        codes = [code for code, _ in history.relation_problems(self.review, link, work_ids=None)]
        self.assertNotIn(history.PROBLEM_CONFLICT, codes)
        other = history.future_work_link(
            ident("rhr", 2), source, ident("w", 9), status=history.CAUSAL_SUPPORTED, rationale="Fix Work.",
            supporting_evidence_digests=["e" * 64],
            integration_provenance={"source_review_run_id": ident("rr", 55), "strategy_id": "s1"})
        self.assertIn(history.PROBLEM_CONFLICT, [code for code, _ in history.relation_problems(self.review, other,
                                                                                               work_ids=None)])


if __name__ == "__main__":
    unittest.main()
