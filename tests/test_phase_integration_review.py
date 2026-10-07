"""RB5 §32.56 / §32.57: the Phase Integration Review semantic model and START's pure orchestration parts.

``DeferredReviewTests`` now runs START's Phase Integration Review Run on real Projects (post-RB6 integration
I-5); the G4-terminal follow-ups START owns next (I-6) and the Human-decision successor are still deferred there.
"""

from __future__ import annotations

import dataclasses
import subprocess
from typing import Any
import unittest
from unittest import mock

from helpers import completing_executor, git
from p5_helpers import decision_evidence
from planning_helpers import Crash, crash_at, design, plan, registered
from rb5_doubles import V1, ViewBuilder, ident, reviewed_phase
from rb5_run_helpers import (Adjudicator, Discovery, IntegrationRunCase, answering_executor, claim, phase_review,
                             repairing_executor)
from workline import gitcmd
from workline import phase_integration as pi
from workline import roadmap as rm
from workline import start as st
from workline import start_integration_review as sir
from workline import start_review as sr
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.mutation import MutationController
from workline.review import achievement_reader, closure, gate, history, integration as ri, p4, planning, records, serialize
from workline.review import paths as review_paths
from workline.review.store import ReviewStore
from workline.state import ProjectView
from workline.store import WORK_DESIRED_HEADING, Event, Relation
from workline.validate import validate_project

DIGEST = "a" * 64
OTHER_DIGEST = "b" * 64
COMMIT = "c" * 40
TREE = "d" * 40
READY, REPAIR, HUMAN = records.AUTHORIZATION_READY, records.REPAIR_REQUIRED, records.HUMAN_WAIT


def build_candidate(view, phase, integration, **overrides):
    arguments = dict(
        base_commit=COMMIT, branch="refs/heads/main", owning_mutation_id=ident("mut", 1),
        terminal_stage=f"{integration}:lifecycle:1", lifecycle_projection=[(ident("evt", 999), "work_started")],
        work_review_refs=[], achievement_evidence_refs=[], review_context_digest=DIGEST,
        effective_policy_hash=OTHER_DIGEST, candidate_generation=1,
    )
    arguments.update(overrides)
    return sir.build_candidate(view, phase, integration, **arguments)


def outcome(kind: str, *, digest: str = DIGEST, obligations: tuple[str, ...] = ()) -> ri.PhaseOutcome:
    return ri.PhaseOutcome(kind, digest, "Bounded public-safe rationale.", obligations)


def outcome_problems(kind: str, p4_outcome: str, *, blocking: int = 0, human: int = 0,
                     obligations: tuple[str, ...] = (), digest: str = DIGEST) -> list[str]:
    return ri.phase_outcome_problems(outcome(kind, digest=digest, obligations=obligations),
                                     candidate_desired_state_digest=DIGEST, p4_outcome=p4_outcome,
                                     blocking_problems=blocking, human_obligations=human)


class IdentityTests(unittest.TestCase):
    def test_only_authorization_ready_issues_a_receipt(self) -> None:
        self.assertTrue(ri.branch_issues_receipt(ri.BRANCH_AUTHORIZATION_READY))
        for branch in (ri.BRANCH_HUMAN_WAIT, ri.BRANCH_DOMAIN_REPAIR_REQUIRED, ri.BRANCH_CONFIRMATION_STRUCTURE_REQUIRED):
            with self.subTest(branch=branch):
                self.assertFalse(ri.branch_issues_receipt(branch))
        with self.assertRaises(ValidationError):
            ri.branch_issues_receipt("REPAIR_REQUIRED")

    def test_the_entry_gate_has_no_activation_input(self) -> None:
        self.assertEqual(["route", "work_review_applies", "phase_review_applies"],
                         [field.name for field in dataclasses.fields(sir.EntryGate)])


class OutcomeTests(unittest.TestCase):
    def test_exactly_one_of_the_four_outcomes(self) -> None:
        self.assertEqual(("objectively_satisfied", "human_confirmation_required", "not_satisfied",
                          "desired_state_change_required"), ri.PHASE_OUTCOMES)
        self.assertTrue(any("not one of" in p for p in outcome_problems("satisfied", READY)))

    def test_not_satisfied_needs_a_blocking_problem_or_an_unmet_obligation(self) -> None:
        self.assertTrue(outcome_problems(ri.NOT_SATISFIED, READY))
        self.assertEqual([], outcome_problems(ri.NOT_SATISFIED, REPAIR, blocking=1))
        self.assertEqual([], outcome_problems(ri.NOT_SATISFIED, READY, obligations=("phase-goal.reporting",)))

    def test_the_phase_outcome_is_bound_to_the_candidate_objective(self) -> None:
        problems = outcome_problems(ri.OBJECTIVELY_SATISFIED, READY, digest=OTHER_DIGEST)
        self.assertTrue(any("canonical Phase desired state" in p for p in problems))
        self.assertEqual(("outcome", "phase_desired_state_digest", "rationale", "unmet_objective_obligations"),
                         tuple(field.name for field in dataclasses.fields(ri.PhaseOutcome)))

    def test_only_not_satisfied_carries_unmet_obligations(self) -> None:
        self.assertTrue(outcome_problems(ri.HUMAN_CONFIRMATION_REQUIRED, READY, obligations=("x",)))
        self.assertEqual([], outcome_problems(ri.HUMAN_CONFIRMATION_REQUIRED, READY))

    def test_the_phase_outcome_is_cross_checked_against_the_p4_outcome(self) -> None:
        """RB5B-M1 / M2: one story per settled adjudication."""
        refused = {
            "desired-state change over AUTHORIZATION_READY": (ri.DESIRED_STATE_CHANGE_REQUIRED, READY, 0, 0),
            "objectively satisfied with blocking Problems": (ri.OBJECTIVELY_SATISFIED, REPAIR, 3, 0),
            "human confirmation with blocking Problems": (ri.HUMAN_CONFIRMATION_REQUIRED, REPAIR, 1, 0),
            "REPAIR_REQUIRED without blocking support (in-Review repair)": (ri.OBJECTIVELY_SATISFIED, REPAIR, 0, 0),
            "AUTHORIZATION_READY with a blocking obligation": (ri.NOT_SATISFIED, READY, 1, 0),
            "HUMAN_WAIT without a HUMAN obligation": (ri.OBJECTIVELY_SATISFIED, HUMAN, 0, 0),
        }
        for described, (kind, p4_outcome, blocking, human) in refused.items():
            with self.subTest(case=described):
                self.assertTrue(outcome_problems(kind, p4_outcome, blocking=blocking, human=human))
        self.assertEqual([], outcome_problems(ri.DESIRED_STATE_CHANGE_REQUIRED, HUMAN, human=1))

    def test_round_trip_and_no_objective_text(self) -> None:
        found = outcome(ri.NOT_SATISFIED, obligations=("a", "b"))
        self.assertEqual(found, ri.PhaseOutcome.from_record(found.to_record()))
        self.assertEqual(serialize.digest(found.to_record()), found.digest)
        with self.assertRaises(ValidationError):
            ri.PhaseOutcome.from_record({**found.to_record(), "desired_state": "rewritten objective"})


class BranchTests(unittest.TestCase):
    def branch(self, p4_outcome: str, kind: str, *, blocking: int = 0, human: int = 0, confirmation: bool = False,
               uncovered: tuple[str, ...] = (), evidence: bool = True, obligations: tuple[str, ...] = ()) -> str:
        return ri.integration_branch(
            p4_outcome=p4_outcome, phase_outcome=outcome(kind, obligations=obligations),
            candidate_desired_state_digest=DIGEST, blocking_problems=blocking, human_obligations=human,
            valid_downstream_confirmation=confirmation, invalid_uncovered=uncovered, evidence_current=evidence,
        )

    def test_precedence(self) -> None:
        self.assertEqual(ri.BRANCH_HUMAN_WAIT, self.branch(HUMAN, ri.DESIRED_STATE_CHANGE_REQUIRED, blocking=2, human=1))
        self.assertEqual(ri.BRANCH_HUMAN_WAIT, self.branch(HUMAN, ri.NOT_SATISFIED, blocking=1, human=1))
        self.assertEqual(ri.BRANCH_DOMAIN_REPAIR_REQUIRED, self.branch(REPAIR, ri.NOT_SATISFIED, blocking=1))
        self.assertEqual(ri.BRANCH_CONFIRMATION_STRUCTURE_REQUIRED, self.branch(READY, ri.HUMAN_CONFIRMATION_REQUIRED))
        self.assertEqual(ri.BRANCH_AUTHORIZATION_READY,
                         self.branch(READY, ri.HUMAN_CONFIRMATION_REQUIRED, confirmation=True))
        self.assertEqual(ri.BRANCH_AUTHORIZATION_READY, self.branch(READY, ri.OBJECTIVELY_SATISFIED))

    def test_domain_repair_always_has_support(self) -> None:
        """RB5B-M1: reached through a blocking Problem or an explicit unmet obligation - never a raw REPAIR_REQUIRED."""
        self.assertEqual(ri.BRANCH_DOMAIN_REPAIR_REQUIRED,
                         self.branch(READY, ri.NOT_SATISFIED, obligations=("phase-goal.reporting",)))
        with self.assertRaises(ValidationError) as raised:
            self.branch(REPAIR, ri.OBJECTIVELY_SATISFIED)
        self.assertEqual("review_record_invalid", raised.exception.code)

    def test_an_inconsistent_adjudication_derives_no_branch(self) -> None:
        with self.assertRaises(ValidationError):
            self.branch(READY, ri.DESIRED_STATE_CHANGE_REQUIRED)
        with self.assertRaises(ValidationError):
            self.branch(REPAIR, ri.OBJECTIVELY_SATISFIED, blocking=3)
        with self.assertRaises(ValidationError):
            self.branch("PASS", ri.OBJECTIVELY_SATISFIED)

    def test_rb5fb2_a_human_obligation_is_never_routed_to_domain_repair(self) -> None:
        """RB5FB-2 / §32.22 step 1: a HUMAN obligation under any P4 outcome but HUMAN_WAIT is inconsistent, so it
        derives no branch - it can never be carried into domain repair instead of a Human decision."""
        problems = outcome_problems(ri.NOT_SATISFIED, REPAIR, blocking=1, human=1)
        self.assertTrue(any("HUMAN obligation is P4 HUMAN_WAIT" in p for p in problems), problems)
        self.assertTrue(any("HUMAN obligation is P4 HUMAN_WAIT" in p
                            for p in outcome_problems(ri.OBJECTIVELY_SATISFIED, READY, human=2)))
        cases = (
            (REPAIR, ri.NOT_SATISFIED, 1, ()),  # before RB5FB-2 this derived DOMAIN_REPAIR_REQUIRED
            (READY, ri.NOT_SATISFIED, 0, ("phase-goal.reporting",)),
            (READY, ri.OBJECTIVELY_SATISFIED, 0, ()),
        )
        for p4_outcome, kind, blocking, obligations in cases:
            with self.subTest(p4_outcome=p4_outcome, kind=kind), self.assertRaises(ValidationError) as raised:
                self.branch(p4_outcome, kind, blocking=blocking, human=1, obligations=obligations)
            self.assertEqual("review_record_invalid", raised.exception.code)
        self.assertEqual(ri.BRANCH_HUMAN_WAIT, self.branch(HUMAN, ri.NOT_SATISFIED, blocking=1, human=1),
                         "the same counts under P4 HUMAN_WAIT keep step 1")

    def test_invalid_uncovered_or_stale_evidence_never_authorizes_and_is_not_a_record_defect(self) -> None:
        with self.assertRaises(ValidationError) as uncovered:
            self.branch(READY, ri.OBJECTIVELY_SATISFIED, uncovered=(ident("w", 9),))
        self.assertEqual(ri.CODE_UNCOVERED, uncovered.exception.code)
        with self.assertRaises(ValidationError) as stale:
            self.branch(READY, ri.OBJECTIVELY_SATISFIED, evidence=False)
        self.assertEqual(ri.CODE_NOT_AUTHORIZABLE, stale.exception.code)


class EntryGateTests(unittest.TestCase):
    def setUp(self) -> None:
        b = ViewBuilder()
        phase = b.phase()
        self.normal = b.work(phase)
        self.marked_normal = b.work(phase, "Marked normal", marker=V1)
        self.legacy = b.integration(phase, marker=None)
        self.marked = b.integration(phase)
        self.unsupported = b.integration(phase, marker="phase-integration-review-v0")
        self.empty = b.integration(phase, marker="")
        self.view = b.view()

    def gate(self, work_id: str, *, phase_review: bool, review: bool) -> sir.EntryGate:
        return sir.entry_gate(self.view.works[work_id], phase_review_supplied=phase_review, work_review_supplied=review)

    def test_marked_integration_requires_phase_review_and_review_never_substitutes(self) -> None:
        for review in (False, True):
            with self.subTest(review=review), self.assertRaises(StopError) as raised:
                self.gate(self.marked, phase_review=False, review=review)
            self.assertEqual(sir.CODE_PHASE_REVIEW_REQUIRED, raised.exception.code)
        gate = self.gate(self.marked, phase_review=True, review=True)
        self.assertEqual((sir.ROUTE_PHASE_INTEGRATION_REVIEW, False, True),
                         (gate.route, gate.work_review_applies, gate.phase_review_applies))

    def test_legacy_integration_runs_without_phase_review_and_selectors_apply_to_their_own_kind(self) -> None:
        gate = self.gate(self.legacy, phase_review=False, review=False)
        self.assertEqual((sir.ROUTE_LEGACY_INTEGRATION, False, False),
                         (gate.route, gate.work_review_applies, gate.phase_review_applies))
        self.assertTrue(self.gate(self.legacy, phase_review=True, review=True).work_review_applies)
        self.assertFalse(self.gate(self.normal, phase_review=True, review=False).phase_review_applies)

    def test_unsupported_empty_or_misplaced_markers_are_refused(self) -> None:
        for work_id in (self.unsupported, self.empty, self.marked_normal):
            with self.subTest(work=work_id), self.assertRaises(StopError) as raised:
                self.gate(work_id, phase_review=True, review=False)
            self.assertEqual(sir.CODE_PHASE_REVIEW_CONTRACT_UNSUPPORTED, raised.exception.code)


class CandidateTests(unittest.TestCase):
    def test_candidate_reconstructs_the_exact_phase_basis(self) -> None:
        def project() -> tuple[ViewBuilder, str, list[str], str]:
            b = ViewBuilder()
            phase, normal, integration, _ = reviewed_phase(b, complete=False)
            b.complete(*normal)
            b.must_read(normal[0], "docs/spec.md")
            return b, phase, normal, integration

        first, phase, normal, integration = project()
        candidate = build_candidate(first.view(), phase, integration)
        self.assertEqual([], ri.candidate_problems(candidate))
        self.assertEqual(sorted(normal + [integration]), candidate["effective_work_ids"])
        self.assertEqual(V1, candidate["integration"]["phase_review_contract"])
        self.assertEqual({"commit": COMMIT, "branch": "refs/heads/main"}, candidate["base"])
        self.assertEqual([pi.CURRENT_INTEGRATION], [c["class"] for c in candidate["coverage"]["classes"]
                                                    if c["work_id"] == integration])
        second, _, _, _ = project()  # an independently built Project holding the same canonical facts
        self.assertEqual(candidate, build_candidate(second.view(), phase, integration))
        self.assertEqual(serialize.digest(candidate), ri.candidate_hash(candidate))
        self.assertEqual((), ri.invalid_uncovered_of(candidate))

    def test_a_sha256_object_format_base_is_accepted_as_the_owner_accepts_it(self) -> None:
        """RB5B-M4."""
        b = ViewBuilder()
        phase, _, integration, _ = reviewed_phase(b, complete=False)
        self.assertEqual("e" * 64, build_candidate(b.view(), phase, integration, base_commit="e" * 64)["base"]["commit"])
        for bad in ("e" * 63, "E" * 40, "e" * 50):
            with self.subTest(base=bad), self.assertRaises(ValidationError):
                build_candidate(b.view(), phase, integration, base_commit=bad)

    def test_own_transient_lifecycle_is_bound_separately_from_the_committed_basis(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        b.complete(*normal)
        committed = b.view()
        own = Event(ident("evt", 999), "work_started", integration, "2026-10-06T00:00:00Z")
        working_with_own = dataclasses.replace(committed, events=committed.events + [own])
        candidate = build_candidate(committed, phase, integration)
        self.assertEqual("unstarted", next(w for w in candidate["works"] if w["work_id"] == integration)["state"])
        self.assertEqual([{"event_id": own.id, "type": "work_started", "entity": integration}],
                         candidate["owning_operation"]["lifecycle_projection"])
        self.assertEqual([], sir.unowned_structural_difference(committed, committed, phase, integration))
        self.assertTrue(sir.unowned_structural_difference(committed, working_with_own, phase, integration),
                        "START's own opening, if not removed from the working view, would differ from the basis")
        self.assertNotEqual(candidate, build_candidate(working_with_own, phase, integration))

    def test_every_unowned_structural_difference_invalidates_the_freeze(self) -> None:
        """RB5B-M5: one case per field of the Candidate's structural projection."""
        def base() -> tuple[ViewBuilder, str, list[str], str, str]:
            b = ViewBuilder()
            phase, normal, integration, confirmation = reviewed_phase(b, complete=False, confirmation=True)
            return b, phase, normal, integration, confirmation

        def retarget(b, phase, normal, integration, confirmation):
            work = b.works[confirmation]
            b.works[confirmation] = type(work)(work.id, work.type, {**work.meta, "confirmation_target": normal[0]},
                                               work.body, work.path)

        def move_roadmap(b, phase, normal, integration, confirmation):
            other = b.roadmap("Other")
            work = b.phases[phase]
            b.phases[phase] = type(work)(work.id, work.type, {**work.meta, "roadmap_id": other}, work.body, work.path)

        def drop_edge(b, phase, normal, integration, confirmation):
            b.relations[:] = [r for r in b.relations if not (r.from_id == normal[0] and r.to == integration)]

        def drop_downstream(b, phase, normal, integration, confirmation):
            b.relations[:] = [r for r in b.relations if not (r.from_id == integration and r.to == confirmation)]

        def add_work(b, phase, normal, integration, confirmation):
            b.work(phase, "Foreign")

        def add_related(b, phase, normal, integration, confirmation):
            b.must_read(normal[0], "docs/other.md")

        for change in (retarget, move_roadmap, drop_edge, drop_downstream, add_work, add_related):
            b, phase, normal, integration, confirmation = base()
            committed = b.view()
            change(b, phase, normal, integration, confirmation)
            with self.subTest(change=change.__name__):
                self.assertTrue(sir.unowned_structural_difference(committed, b.view(), phase, integration))

    def test_nested_entries_are_strict(self) -> None:
        """RB5B-M6."""
        b = ViewBuilder()
        phase, normal, integration, confirmation = reviewed_phase(b, complete=False, confirmation=True)
        b.must_read(normal[0])
        candidate = build_candidate(b.view(), phase, integration)
        work_index = candidate["works"].index(next(w for w in candidate["works"] if w["work_id"] == normal[0]))

        def with_work(**fields):
            works = [dict(w) for w in candidate["works"]]
            works[work_index].update(fields)
            return {**candidate, "works": works}

        broken = {
            "desired digest": with_work(desired_state_digest="not-a-digest"),
            "state": with_work(state="bogus"),
            "kind": with_work(work_kind="nonsense"),
            "terminal": with_work(terminal_event_id=12),
            "marker on a normal Work": with_work(phase_review_contract="v9"),
            "target on a normal Work": with_work(confirmation_target=[integration]),
            "dependency endpoint": {**candidate, "dependencies": [{**candidate["dependencies"][0], "from": "nobody"}]
                                    + candidate["dependencies"][1:]},
            "downstream ids": {**candidate, "downstream_confirmation_ids": ["not-an-id"]},
            "related type": {**candidate, "related_authority_refs": [{**candidate["related_authority_refs"][0],
                                                                      "type": "bogus"}]},
            "work review ref outside the plan": {**candidate, "work_review_refs": [
                {"work_id": ident("w", 999), "review_run_id": ident("rr", 1), "run_summary_digest": DIGEST}]},
            "work review ref without a digest": {**candidate, "work_review_refs": [
                {"work_id": normal[0], "review_run_id": ident("rr", 1), "run_summary_digest": None}]},
        }
        for described, tampered in broken.items():
            with self.subTest(case=described):
                self.assertTrue(ri.candidate_problems(tampered))
                with self.assertRaises(ValidationError):
                    ri.candidate_hash(tampered)

    def test_coverage_must_follow_from_the_candidates_own_dependencies(self) -> None:
        """RB5B-M6 probe P6b: a stray edge-less Work relabelled pre_integration is refused, never hashed."""
        b = ViewBuilder()
        phase, _, integration, _ = reviewed_phase(b, complete=False)
        stray = b.work(phase, "Stray")
        candidate = build_candidate(b.view(), phase, integration)
        self.assertEqual((stray,), ri.invalid_uncovered_of(candidate))
        classes = [dict(c) for c in candidate["coverage"]["classes"]]
        next(c for c in classes if c["work_id"] == stray)["class"] = pi.PRE_INTEGRATION
        tampered = {**candidate, "coverage": {**candidate["coverage"], "classes": classes}}
        self.assertTrue(any("does not follow" in p for p in ri.candidate_problems(tampered)))
        with self.assertRaises(ValidationError):
            ri.invalid_uncovered_of(tampered)

    def test_owning_operation_names_the_integrations_own_opening(self) -> None:
        """RB5B-L3."""
        b = ViewBuilder()
        phase, _, integration, _ = reviewed_phase(b, complete=False)
        view = b.view()
        for override in ({"lifecycle_projection": []},
                         {"lifecycle_projection": [(ident("evt", 9), "work_completed")]},
                         {"terminal_stage": "anything"},
                         {"terminal_stage": f"{ident('w', 777)}:lifecycle:1"}):
            with self.subTest(override=override), self.assertRaises(ValidationError):
                build_candidate(view, phase, integration, **override)

    def test_strictness_of_the_frame(self) -> None:
        b = ViewBuilder()
        phase, _, integration, _ = reviewed_phase(b, complete=False)
        view = b.view()
        for override in ({"base_commit": "abc"}, {"branch": "main"}, {"effective_policy_hash": "policy"},
                         {"candidate_generation": 0}, {"owning_mutation_id": "m"}):
            with self.subTest(override=override), self.assertRaises(ValidationError):
                build_candidate(view, phase, integration, **override)
        candidate = build_candidate(view, phase, integration)
        tampered = {**candidate, "effective_work_ids": list(reversed(candidate["effective_work_ids"]))}
        self.assertTrue(ri.candidate_problems(tampered))
        self.assertTrue(ri.candidate_problems({**candidate, "phase_outcome": "x"}))

    def test_rb5fb3_the_candidate_binds_the_available_achievement_evidence_refs(self) -> None:
        """RB5FB-3 / §14.5 "available Work Review/achievement evidence references": a strict slot, shape-checked
        exactly like work_review_refs. Which records are available is the achievement history reader's (deferred)."""
        self.assertIn("achievement_evidence_refs", ri.CANDIDATE_FIELDS)
        b = ViewBuilder()
        phase, normal, _, _ = reviewed_phase(b)  # completed on its first basis: evidence for it may exist
        new = b.integration(phase)  # the reintegration whose Candidate is frozen
        for work_id in normal:
            b.requires(work_id, new)
        view = b.view()
        unbound = build_candidate(view, phase, new)
        self.assertEqual([], unbound["achievement_evidence_refs"], "none given, none bound: nothing is backfilled")
        self.assertEqual([], sir.build_candidate(
            view, phase, new, base_commit=COMMIT, branch="refs/heads/main", owning_mutation_id=ident("mut", 1),
            terminal_stage=f"{new}:lifecycle:1", lifecycle_projection=[(ident("evt", 999), "work_started")],
            work_review_refs=[], review_context_digest=DIGEST, effective_policy_hash=OTHER_DIGEST,
            candidate_generation=1)["achievement_evidence_refs"], "the parameter defaults to no refs")
        candidate = build_candidate(view, phase, new, achievement_evidence_refs=[
            (phase, ident("rha", 2), OTHER_DIGEST), (phase, ident("rha", 1), DIGEST)])
        self.assertEqual(
            [{"phase_id": phase, "achievement_evidence_id": ident("rha", 1), "evidence_digest": DIGEST},
             {"phase_id": phase, "achievement_evidence_id": ident("rha", 2), "evidence_digest": OTHER_DIGEST}],
            candidate["achievement_evidence_refs"], "bound in (phase_id, achievement_evidence_id) order")
        self.assertEqual([], ri.candidate_problems(candidate))
        self.assertNotEqual(ri.candidate_hash(unbound), ri.candidate_hash(candidate), "the refs are frozen material")
        entry = candidate["achievement_evidence_refs"][0]

        def refs(*entries):
            return {**candidate, "achievement_evidence_refs": list(entries)}

        broken = {
            "slot missing": {k: v for k, v in candidate.items() if k != "achievement_evidence_refs"},
            "not a list": {**candidate, "achievement_evidence_refs": {}},
            "extra field": refs({**entry, "extra": 1}),
            "missing field": refs({k: v for k, v in entry.items() if k != "evidence_digest"}),
            "not a Phase ID": refs({**entry, "phase_id": ident("w", 1)}),
            "prose evidence ID": refs({**entry, "achievement_evidence_id": "two words"}),
            "list evidence ID": refs({**entry, "achievement_evidence_id": [ident("rha", 1)]}),
            "not a digest": refs({**entry, "evidence_digest": "not-a-digest"}),
            "unsorted": refs(*reversed(candidate["achievement_evidence_refs"])),
            "duplicate": refs(entry, entry),
        }
        for described, tampered in broken.items():
            with self.subTest(case=described):
                self.assertTrue(ri.candidate_problems(tampered))
                with self.assertRaises(ValidationError):
                    ri.candidate_hash(tampered)

    def test_rb5fa1_an_unhashable_stored_value_is_reported_never_raised(self) -> None:
        """RB5FA-1 sibling reader: the Candidate's set-membership and classification checks run over stored values; a
        YAML sequence or mapping where an ID belongs is review_record_invalid in every reader, never a raw TypeError."""
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        b.must_read(normal[0])
        candidate = build_candidate(b.view(), phase, integration)
        dependency, related = candidate["dependencies"][0], candidate["related_authority_refs"][0]
        broken = {
            "list dependency from": {**candidate, "dependencies": [{**dependency, "from": [dependency["from"]]}]
                                     + candidate["dependencies"][1:]},
            "mapping dependency to": {**candidate, "dependencies": [{**dependency, "to": {"id": dependency["to"]}}]
                                      + candidate["dependencies"][1:]},
            "list Related from": {**candidate, "related_authority_refs": [{**related, "from": [related["from"]]}]},
            "list Work Review ref work_id": {**candidate, "work_review_refs": [
                {"work_id": [normal[0]], "review_run_id": ident("rr", 1), "run_summary_digest": DIGEST}]},
        }
        for described, tampered in broken.items():
            with self.subTest(case=described):
                self.assertTrue(ri.candidate_problems(tampered))
                for reader in (ri.candidate_hash, ri.invalid_uncovered_of, ri.downstream_confirmation_ids_of):
                    with self.assertRaises(ValidationError) as raised:
                        reader(tampered)
                    self.assertEqual("review_record_invalid", raised.exception.code)

    def test_cpq04_a_candidate_freezes_with_invalid_uncovered_and_never_authorizes(self) -> None:
        """Ruling CPQ-04: freeze is allowed; the §32.22 order is kept and AUTHORIZATION_READY (a Receipt) is impossible."""
        b = ViewBuilder()
        phase, _, integration, _ = reviewed_phase(b, complete=False)
        stray = b.work(phase, "Stray")
        candidate = build_candidate(b.view(), phase, integration)
        uncovered = ri.invalid_uncovered_of(candidate)
        self.assertEqual((stray,), uncovered)

        def branch(kind: str, p4_outcome: str = READY, *, blocking: int = 0, human: int = 0,
                   obligations: tuple[str, ...] = ()) -> str:
            return ri.integration_branch(
                p4_outcome=p4_outcome, phase_outcome=outcome(kind, obligations=obligations),
                candidate_desired_state_digest=DIGEST, blocking_problems=blocking, human_obligations=human,
                valid_downstream_confirmation=bool(ri.downstream_confirmation_ids_of(candidate)),
                invalid_uncovered=uncovered, evidence_current=True)

        self.assertEqual(ri.BRANCH_HUMAN_WAIT, branch(ri.DESIRED_STATE_CHANGE_REQUIRED, HUMAN, human=1))
        self.assertEqual(ri.BRANCH_DOMAIN_REPAIR_REQUIRED, branch(ri.NOT_SATISFIED, REPAIR, blocking=1))
        self.assertEqual(ri.BRANCH_CONFIRMATION_STRUCTURE_REQUIRED, branch(ri.HUMAN_CONFIRMATION_REQUIRED),
                         "step 3 comes first; the successor Candidate is re-evaluated")
        with self.assertRaises(ValidationError) as raised:
            branch(ri.OBJECTIVELY_SATISFIED)
        self.assertEqual(ri.CODE_UNCOVERED, raised.exception.code)

    def test_cpq02_a_candidate_never_calls_an_unfinished_integration_historical(self) -> None:
        b = ViewBuilder()
        phase, normal, old, _ = reviewed_phase(b)
        new = b.integration(phase)
        for work_id in normal:
            b.requires(work_id, new)
        candidate = build_candidate(b.view(), phase, new)
        self.assertEqual(pi.HISTORICAL_INTEGRATION, next(c["class"] for c in candidate["coverage"]["classes"]
                                                         if c["work_id"] == old))
        works = [dict(w) for w in candidate["works"]]
        entry = next(w for w in works if w["work_id"] == old)
        entry.update(state="in_progress", terminal_event_id=None)
        self.assertTrue(any("does not follow" in p for p in ri.candidate_problems({**candidate, "works": works})),
                        "an unfinished other integration classified historical is refused")

    def test_a_candidate_is_only_for_an_unfinished_integration(self) -> None:
        b = ViewBuilder()
        phase, _, integration, _ = reviewed_phase(b, complete=False)
        candidate = build_candidate(b.view(), phase, integration)
        works = [dict(w) for w in candidate["works"]]
        entry = next(w for w in works if w["work_id"] == integration)
        entry.update(state="completed", terminal_event_id=ident("evt", 5))
        self.assertTrue(any("unfinished integration" in p for p in ri.candidate_problems({**candidate, "works": works})))

    def test_a_failing_structure_is_never_frozen(self) -> None:
        """RB5B-L2 / CPQ-04: the only freeze refusal is a failing structural validation (here a cycle), never
        invalid_uncovered."""
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        b.requires(integration, normal[0])  # with normal[0] -> integration: a requires_completion cycle
        with self.assertRaises(ValidationError) as raised:
            build_candidate(b.view(), phase, integration)
        self.assertEqual(sir.CODE_STRUCTURE_INVALID, raised.exception.code)

    def test_a_legacy_integration_is_not_a_phase_integration_candidate(self) -> None:
        b = ViewBuilder()
        phase = b.phase()
        work = b.work(phase)
        legacy = b.integration(phase, marker=None)
        b.requires(work, legacy)
        with self.assertRaises(ValidationError):
            build_candidate(b.view(), phase, legacy)

    def test_related_authority_refs_bind_every_effective_works_related(self) -> None:
        """RB8-FC-09 item 5: obey / must_read / conditional_must_read of every effective Work are bound."""
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        expected = []
        for index, (kind, extra) in enumerate((("must_read", {}), ("obey", {}),
                                               ("conditional_must_read", {"condition": {"kind": "path_glob",
                                                                                         "pattern": "src/*.py"}}))):
            relation = Relation(ident("rel", 800 + index), kind, normal[index % len(normal)], f"docs/{kind}.md", extra)
            b.related.append(relation)
            expected.append(relation.id)
        excluded = b.work(phase, "Excluded")
        b.exclude(excluded)
        b.related.append(Relation(ident("rel", 900), "must_read", excluded, "docs/excluded.md"))
        candidate = build_candidate(b.view(), phase, integration)
        self.assertEqual(expected, [r["relation_id"] for r in candidate["related_authority_refs"]])
        self.assertEqual({"kind": "path_glob", "pattern": "src/*.py"}, candidate["related_authority_refs"][2]["condition"])


class ConfirmationTests(unittest.TestCase):
    def test_human_confirmation_required_without_confirmation_creates_exactly_one_deterministic_work(self) -> None:
        b = ViewBuilder()
        phase, _, integration, _ = reviewed_phase(b, complete=False)
        view = b.view()
        self.assertEqual((sir.CONFIRMATION_CREATE, ()), sir.confirmation_decision(view, phase, integration))
        specs, relations = sir.confirmation_registration(view, phase, integration)
        (spec,) = specs.values()
        self.assertEqual(("human_confirmation", integration), (spec.work_kind, spec.confirmation_target))
        self.assertEqual([("requires_completion", integration, "confirmation")],
                         [(r.type, r.from_ref, r.to_ref) for r in relations])
        self.assertEqual(sir.CONFIRMATION_DESIRED_STATE, spec.desired_state, "the §32.23 sentence, verbatim")
        self.assertEqual("Human has confirmed that this Phase's current canonical desired state is satisfied after the "
                         "reviewed integration.", spec.desired_state)
        self.assertEqual((specs, relations), sir.confirmation_registration(b.view(), phase, integration), "deterministic")
        self.assertIsNone(spec.phase_review_contract)

    def test_no_reviewer_text_reaches_the_confirmation(self) -> None:
        built = sir.confirmation_structure(ident("p", 1), "P-01", ident("w", 2))
        self.assertEqual("Phase confirmation: P-01", built.name)
        with self.assertRaises(ValidationError):
            sir.confirmation_structure("not-a-phase", "P-01", ident("w", 2))

    def test_valid_downstream_confirmations_create_none_and_only_generated_duplicates_conflict(self) -> None:
        """RB5B-L5."""
        b = ViewBuilder()
        phase, _, integration, designed = reviewed_phase(b, complete=False, confirmation=True)
        self.assertEqual((sir.CONFIRMATION_EXISTS, (designed,)), sir.confirmation_decision(b.view(), phase, integration))
        second = b.confirmation(phase, integration)  # a second designed Human judgement: compatible
        self.assertEqual((sir.CONFIRMATION_EXISTS, tuple(sorted([designed, second]))),
                         sir.confirmation_decision(b.view(), phase, integration))
        structure = sir.confirmation_structure(phase, b.phases[phase].display, integration)
        for _ in range(2):  # the deterministic builder's own Work twice: a duplicated registration
            generated = b.work(phase, structure.name, kind="human_confirmation", target=integration,
                               desired=structure.desired_state)
            b.requires(integration, generated)
        with self.assertRaises(ReconcileRequired) as raised:
            sir.confirmation_decision(b.view(), phase, integration)
        self.assertEqual(sir.REASON_CONFIRMATION_CONFLICT, raised.exception.reason)

    def test_the_successor_candidate_includes_the_structure_and_the_phase_waits_for_it(self) -> None:
        b = ViewBuilder()
        phase, normal, integration, _ = reviewed_phase(b, complete=False)
        b.complete(*normal)
        confirmation = b.confirmation(phase, integration)
        candidate = build_candidate(b.view(), phase, integration)
        self.assertEqual([confirmation], candidate["downstream_confirmation_ids"])
        self.assertEqual((confirmation,), ri.downstream_confirmation_ids_of(candidate))
        b.complete(integration)
        self.assertFalse(pi.phase_generated_complete(b.view(), phase))
        b.complete(confirmation)
        self.assertTrue(pi.phase_generated_complete(b.view(), phase))


class VerificationOnlyTests(unittest.TestCase):
    def declaration(self, **overrides) -> p4.IntegrationDeclaration:
        values = dict(adapter_identity="verifier", allowed_project_state=(), allowed_external_state=(),
                      allowed_nested_state=(), isolation_mechanism=None, disposal_proven=False)
        values.update(overrides)
        return p4.IntegrationDeclaration(**values)

    def check(self, proof, observation=None, declaration=None) -> list[str]:
        return ri.verification_only_problems(declaration or self.declaration(),
                                             observation if observation is not None else p4.IntegrationObservation(),
                                             proof, candidate_base_tree=TREE)

    def materialized(self, **overrides) -> ri.MaterializationProof:
        values = dict(mechanism_identity="frozen-checkout", mechanism_version="1", materialized_tree=TREE, disposed=True)
        values.update(overrides)
        return ri.MaterializationProof(**values)

    def measured(self, **overrides) -> ri.OwnerMeasuredProof:
        values = dict(measured_by="start", before_state_digest=DIGEST, after_state_digest=DIGEST,
                      declared_external_scopes=(), declared_nested_scopes=())
        values.update(overrides)
        return ri.OwnerMeasuredProof(**values)

    def test_a_self_reported_empty_observation_is_never_proof(self) -> None:
        """RB5B-H1: IntegrationObservation() with no positive proof is refused."""
        self.assertEqual([ri.NO_PROOF], self.check(None))
        self.assertEqual([ri.NO_PROOF], self.check(object()))

    def test_a_disposed_materialization_of_the_candidate_base_proves_read_only(self) -> None:
        self.assertEqual([], self.check(self.materialized()))
        for override in ({"materialized_tree": "f" * 40}, {"disposed": False}, {"mechanism_identity": "two words"}):
            with self.subTest(override=override):
                self.assertTrue(self.check(self.materialized(**override)))

    def test_an_owner_measured_unchanged_state_proves_read_only(self) -> None:
        self.assertEqual([], self.check(self.measured()))
        for override in ({"measured_by": "verifier"}, {"after_state_digest": OTHER_DIGEST},
                         {"declared_external_scopes": ("db",)}):
            with self.subTest(override=override):
                self.assertTrue(self.check(self.measured(**override)))

    def test_undeclared_mutation_cannot_pass_even_with_a_proof(self) -> None:
        self.assertTrue(self.check(self.materialized(), p4.IntegrationObservation(project_mutations=("src/app.py",))))
        self.assertTrue(self.check(self.materialized(), p4.IntegrationObservation(external_mutations=("db",))))
        self.assertTrue(self.check(self.materialized(), declaration=self.declaration(allowed_project_state=("out/",))))
        self.assertTrue(ri.verification_only_problems(object(), p4.IntegrationObservation(), self.materialized(),
                                                      candidate_base_tree=TREE))

    def test_a_declared_isolated_external_scope_passes_only_with_the_proof_binding_it(self) -> None:
        declared = self.declaration(allowed_external_state=("db",), disposal_proven=True,
                                    isolation_mechanism=closure.MechanismProof(closure.PROOF_OBSERVATION, "container", "1"))
        observed = p4.IntegrationObservation(external_mutations=("db",))
        self.assertEqual([], self.check(self.measured(declared_external_scopes=("db",)), observed, declared))
        self.assertTrue(self.check(self.measured(), observed, declared), "the proof must bind the declared scopes")


class TerminalGateTests(unittest.TestCase):
    def facts(self, **overrides) -> sir.TerminalGateFacts:
        values = dict(
            ordinary_precheck_passed=True, marker_matches=True, candidate_current=True,
            structural_validation_passed=True, structural_coverage_current=True, phase_basis_invalidated=False,
            review_complete=True, review_evidence_current=True, branch=ri.BRANCH_AUTHORIZATION_READY,
            phase_outcome=ri.OBJECTIVELY_SATISFIED, downstream_confirmation_modeled=False, blocking_problems=0,
            dispositions_valid=True, receipt_authorizes_candidate=True, history_obligations_valid=True,
            incompatible_pending_successor=False, side_effect_problems=(), conflicts=(), unclosed_obligations=(),
        )
        values.update(overrides)
        return sir.TerminalGateFacts(**values)

    def test_every_condition(self) -> None:
        self.assertEqual([], sir.terminal_gate_problems(self.facts()))
        for override in (
            {"ordinary_precheck_passed": False}, {"marker_matches": False}, {"candidate_current": False},
            {"structural_validation_passed": False}, {"structural_coverage_current": False},
            {"phase_basis_invalidated": True}, {"review_complete": False}, {"review_evidence_current": False},
            {"branch": ri.BRANCH_CONFIRMATION_STRUCTURE_REQUIRED}, {"phase_outcome": ri.NOT_SATISFIED},
            {"phase_outcome": ri.HUMAN_CONFIRMATION_REQUIRED}, {"blocking_problems": 1}, {"dispositions_valid": False},
            {"receipt_authorizes_candidate": False}, {"history_obligations_valid": False},
            {"side_effect_problems": ("x",)}, {"conflicts": ("superseded",)}, {"incompatible_pending_successor": True},
            {"unclosed_obligations": ("HUMAN",)},
            {"side_effect_problems": None}, {"conflicts": None}, {"unclosed_obligations": None},
            {"phase_basis_invalidated": None}, {"review_evidence_current": None},
        ):
            with self.subTest(override=override):
                self.assertTrue(sir.terminal_gate_problems(self.facts(**override)))
        self.assertEqual([], sir.terminal_gate_problems(self.facts(phase_outcome=ri.HUMAN_CONFIRMATION_REQUIRED,
                                                                   downstream_confirmation_modeled=True)))

    def test_no_fact_has_a_passing_default(self) -> None:
        """RB5B-M7: omitting any fact is a construction error, never a pass."""
        for field in dataclasses.fields(sir.TerminalGateFacts):
            self.assertIs(dataclasses.MISSING, field.default, field.name)
            self.assertIs(dataclasses.MISSING, field.default_factory, field.name)


class DeferredReviewTests(IntegrationRunCase):
    """START's Phase Integration Review Run (I-5: rows R19 - R22, the terminal half of R27), on real Projects.

    Every Run goes through ``start.start(..., phase_review=...)`` with scripted actors
    (``rb5_run_helpers``). The two G4-terminal follow-ups START owns next (domain
    repair planning, the confirmation structure) and the Human-decision successor stay
    deferred to I-6 / the successor row.
    """

    def test_g1_to_g5_authorization_path(self) -> None:
        """G1 discovery accepted -> G2 settled -> G3 adjudication accepted -> G4 AUTHORIZATION_READY -> G5 sealed,
        under the registered contract, the Phase Integration kind and the integration's own operation identity."""
        store, phase_id, ids = self.marked_project()
        discovery, adjudicator = Discovery(), Adjudicator()
        result = self.integrate(store, ids["integration"], phase_review(discovery, adjudicator=adjudicator))
        self.assertEqual("completed", result.status)
        chain = self.one_run(store, ids["integration"])
        first, sealed = chain.generations[0], chain.latest
        self.assertEqual([1, 2, 3, 4, 5], [found.generation for found in chain.generations])
        self.assertEqual((ri.REVIEW_KIND, ids["integration"], sr.integration_operation_identity(ids["integration"])),
                         (first.review_kind, first.target_identity, first.operation_identity))
        self.assertTrue(sealed.sealed)
        self.assertEqual(ri.AUTHORIZED_OPERATION_STAGE, sealed.authorized_operation_stage)
        review = ReviewStore(store)
        self.assertEqual({records.P4_PHASE_INTEGRATION_CONTRACT}, p4.run_contracts(review, chain))
        self.assertEqual(p4.P6_POLICY_ID, p4.run_policy(review, chain))
        adjudication = review.read_adjudication(chain.review_run_id)
        self.assertEqual((records.AUTHORIZATION_READY, ri.BRANCH_AUTHORIZATION_READY, ri.OBJECTIVELY_SATISFIED),
                         (adjudication.outcome, adjudication.integration_disposition,
                          adjudication.phase_outcome["outcome"]))
        receipt = review.read_receipt(str(sealed.receipt_id))
        self.assertEqual((chain.review_run_id, first.candidate_hash, ri.AUTHORIZED_OPERATION_STAGE),
                         (receipt.review_run_id, receipt.authorized_candidate_hash, receipt.authorized_operation_stage))
        self.assertEqual((1, 1), (len(discovery.tasks), len(adjudicator.tasks)), "each actor asked exactly once")
        candidate = review.read_candidate_snapshot(first.candidate_hash).material
        self.assertEqual(candidate, adjudicator.tasks[0].candidate, "the adjudicator reads the frozen Candidate")
        self.assertEqual(V1, candidate["integration"]["phase_review_contract"])
        view = ProjectView.load(store)
        self.assertEqual("completed", view.work_state(ids["integration"]).state)
        self.assertTrue(view.phase_completion(phase_id).complete)
        self.assertEqual([], MutationController(store).list_pending())
        self.assertEqual([], validate_project(store))

    def test_a_step_4_refusal_is_a_live_g4_terminal_disposition(self) -> None:
        """RB5J-3, ruling OQ-C's named trigger, live: a Candidate frozen with an ``invalid_uncovered`` Work (CPQ-04)
        reaches step 4 of §32.22 and its refusal ``phase_integration_uncovered`` is the Run's stored G4 disposition -
        final ``not_authorized``, no Receipt - and the owner STOPs with exactly that code; a retry never seals,
        re-adjudicates or recovers it as authorizable."""
        store, phase_id, ids = self.marked_project(uncovered=True)
        adjudicator = Adjudicator()
        selector = phase_review(Discovery(), adjudicator=adjudicator)
        for attempt in (1, 2):
            with self.assertRaises(StopError) as raised:
                self.integrate(store, ids["integration"], selector)
            self.assertEqual(ri.CODE_UNCOVERED, raised.exception.code, attempt)
        chain = self.one_run(store, ids["integration"])
        review = ReviewStore(store)
        candidate = review.read_candidate_snapshot(chain.generations[0].candidate_hash).material
        self.assertEqual((ids["w2"],), ri.invalid_uncovered_of(candidate))
        adjudication = review.read_adjudication(chain.review_run_id)
        self.assertEqual(ri.CODE_UNCOVERED, adjudication.integration_disposition)
        self.assertEqual(records.AUTHORIZATION_READY, adjudication.outcome, "a step-4 refusal is a P4 AUTHORIZATION_READY")
        self.assertEqual((4, None), (chain.latest.generation, chain.latest.receipt_id))
        self.assertEqual(history.DISPOSITION_NOT_AUTHORIZED, p4.final_disposition(review, chain))
        self.assertEqual(history.DISPOSITION_NOT_AUTHORIZED,
                         review.read_history(review_paths.HISTORY_RUNS, chain.review_run_id).durable_disposition)
        self.assertEqual(1, len(adjudicator.tasks), "never adjudicated again")
        self.assertEqual([], [found for found in review.consumptions()])
        self.assertEqual("in_progress", ProjectView.load(store).work_state(ids["integration"]).state)

    def test_g4_state_seal_and_p5_disposition_come_from_the_integration_branch(self) -> None:
        """§32.20 - §32.22, rulings CPQ-04 / OQ-C / R8: only AUTHORIZATION_READY seals G5. A G4-terminal disposition
        is final not_authorized with its P5 summary in that G4 and no Receipt; HUMAN_WAIT keeps the Run and the START
        pending. Re-running START never seals or re-asks either one. (Changed at I-6: a DOMAIN_REPAIR_REQUIRED Run now
        asks START's executor for its repair plan - here an answer that is no plan, refused each time; the
        CONFIRMATION_STRUCTURE_REQUIRED row is ``test_first_run_gets_a_p5_final_disposition_and_no_receipt``.)"""
        cases = (
            ("domain repair", (claim("problem"),), ri.BRANCH_DOMAIN_REPAIR_REQUIRED,
             sr.CODE_INTEGRATION_REPAIR_PLAN_INVALID, history.DISPOSITION_NOT_AUTHORIZED),
            ("human wait", (claim("human"),), records.HUMAN_WAIT, p4.CODE_HUMAN_WAIT, history.DISPOSITION_HUMAN_WAIT),
        )
        for name, claims, disposition, code, durable in cases:
            with self.subTest(name):
                store, _, ids = self.marked_project(name.replace(" ", "-"))
                adjudicator = Adjudicator()
                selector = phase_review(Discovery(*claims), adjudicator=adjudicator)
                log: list = []
                for attempt in (1, 2):
                    with self.assertRaises(StopError) as raised:
                        self.integrate(store, ids["integration"], selector,
                                       executor=answering_executor(st.Completed(), log))
                    self.assertEqual(code, raised.exception.code, attempt)
                chain = self.one_run(store, ids["integration"])
                review = ReviewStore(store)
                self.assertEqual(4, chain.latest.generation, "never sealed, never past G4")
                self.assertIsNone(chain.latest.receipt_id)
                self.assertEqual(disposition, review.read_adjudication(chain.review_run_id).integration_disposition)
                self.assertEqual(durable, p4.final_disposition(review, chain))
                summary = review.read_history(review_paths.HISTORY_RUNS, chain.review_run_id)
                self.assertEqual((durable, None), (summary.durable_disposition, summary.receipt_id))
                self.assertEqual(1, len(adjudicator.tasks), "a settled G4 is never adjudicated again")
                if disposition == ri.BRANCH_DOMAIN_REPAIR_REQUIRED:
                    self.assertEqual([ids["integration"]] * 2, [work_id for work_id, _ in log])
                    self.assertTrue(all(context is not None for _, context in log),
                                    "asked only in the repair planning context, never for a completion")
                else:
                    self.assertEqual([], log, "the executor is never asked")
                (pending,) = MutationController(store).list_pending()
                self.assertEqual({"operation": "start", "work_id": ids["integration"], "mode": "single-work"},
                                 pending["invocation"])
                self.assertEqual("in_progress", ProjectView.load(store).work_state(ids["integration"]).state)
                self.assertEqual([], [found for found in review.consumptions()])

    def test_no_ordinary_executor_success_path_for_a_marked_integration(self) -> None:
        """§32.16: the marked integration is verification-only - no executor call, no result path, and its completion
        is START's ordinary unmarked ``work_completed``; ``outer`` reaches it and ends phase_complete."""
        store, phase_id, ids = self.marked_project(complete_w1=False)
        log: list[str] = []
        result = self.integrate(store, ids["w1"], mode="outer", log=log)
        self.assertEqual(("phase_complete", (ids["w1"], ids["integration"])),
                         (result.status, result.completed_work_ids))
        self.assertEqual([ids["w1"]], log, "only the ordinary Work reached the executor")
        events = ProjectView.load(store).events_for(ids["integration"])
        self.assertEqual(["work_started", "work_target_added", "work_target_removed", "work_completed"],
                         [event.type for event in events])
        self.assertEqual({}, dict(events[-1].metadata or {}), "an ordinary, unmarked work_completed")
        tracked = git(store.root, "ls-files").split()
        display = ProjectView.load(store).works[ids["w1"]].display
        self.assertEqual([f"result_{display}.txt"], [path for path in tracked if path.startswith("result_")],
                         "the integration produced no result path")

    def test_receipt_consumption_and_work_completed_are_bound(self) -> None:
        """§32.31: one terminal stage - the consumed P5 summary, the two ordinary events, the version 5 Consumption
        bound to exactly that work_completed - finalized by START's ordinary commit, which HEAD holds byte for byte."""
        store, phase_id, ids = self.marked_project()
        result = self.integrate(store, ids["integration"])
        chain = self.one_run(store, ids["integration"])
        review = ReviewStore(store)
        receipt_id = str(chain.latest.receipt_id)
        consumption = review.consumption_by_receipt()[receipt_id]
        self.assertIsInstance(consumption, records.IntegrationConsumption)
        completed = ProjectView.load(store).events_for(ids["integration"])[-1]
        self.assertEqual((completed.id, "work_completed", ids["integration"], result.mutation_id),
                         (consumption.terminal_event_id, consumption.terminal_event_type, consumption.target_identity,
                          consumption.operation_mutation_id))
        summary = review.read_history(review_paths.HISTORY_RUNS, chain.review_run_id)
        self.assertEqual((history.DISPOSITION_CONSUMED, consumption.consumption_id, receipt_id),
                         (summary.durable_disposition, summary.consumption_id, summary.receipt_id))
        head = gitcmd.head_commit(store.root)
        subject = git(store.root, "log", "-1", "--format=%s").strip()
        self.assertEqual(f"chore(workline): complete {ProjectView.load(store).works[ids['integration']].display}",
                         subject)
        changed = set(git(store.root, "diff-tree", "--no-commit-id", "--name-only", "-r", head).split())
        self.assertLessEqual({".workline/events/events.jsonl", review_paths.consumption_rel(consumption.consumption_id),
                              review_paths.history_run_rel(chain.review_run_id)}, changed)
        for relative in changed:
            if relative.startswith(".workline/review/"):
                self.assertEqual((store.root / relative).read_bytes(),
                                 subprocess.run(["git", "-C", str(store.root), "show", f"HEAD:{relative}"],
                                        capture_output=True, check=True).stdout, relative)
        self.assertEqual("", git(store.root, "status", "--porcelain", "--", ".workline/events", ".workline/review"))
        self.assertEqual([], validate_project(store))

    def test_in_flight_integration_run_binding_and_selector_kind_mismatch_are_refused(self) -> None:
        """§32.15, R22: a START that holds a Run continues it only with a selector at all, and only with one binding
        the Run's own actors; a Run no START holds is never resumed or replaced (review_recovery_incomplete) - all
        before any new effect. (``review=`` never standing in for ``phase_review`` is EntryGateTests' and
        StartEntryGateTests'.)"""
        store, _, ids = self.marked_project()
        with crash_at(sr, "_integration_launch"):
            with self.assertRaises(Crash):
                self.integrate(store, ids["integration"])
        (pending,) = MutationController(store).list_pending()
        before = (self.integration_runs(store, ids["integration"]), pending)
        with self.assertRaises(StopError) as raised:
            st.start(store, ids["integration"], "single-work", completing_executor(store))
        self.assertEqual("phase_review_required", raised.exception.code)
        other = Discovery(identity="another-discovery")
        with self.assertRaises(StopError) as raised:
            self.integrate(store, ids["integration"], phase_review(other))
        self.assertEqual("review_reviewer_mismatch", raised.exception.code)
        self.assertEqual([], other.tasks, "nothing launched to an actor the Run did not accept")
        self.assertEqual(before[0], self.integration_runs(store, ids["integration"]))
        self.assertEqual(1, self.one_run(store, ids["integration"]).latest.generation)
        # runtime loss: the START record is gone, its own opening put back - the open Run is resumed by no one
        self.runtime_gone(store)
        git(store.root, "checkout", "--", ".workline/events/events.jsonl")
        with self.assertRaises(ReconcileRequired) as lost:
            self.integrate(store, ids["integration"])
        self.assertEqual("review_recovery_incomplete", lost.exception.reason)
        self.assertEqual(before[0], self.integration_runs(store, ids["integration"]))
        self.assertEqual([], MutationController(store).list_pending())

    def test_g4_terminal_run_is_never_recovered_as_authorizable(self) -> None:
        """Ruling OQ-C, interruption / recovery: a G4-terminal Run resumed by its own START, or met by a fresh START
        after runtime loss, is never sealed, never named as set aside, never given a Receipt."""
        store, _, ids = self.marked_project()
        selector = phase_review(Discovery(claim("problem")))
        refusing = answering_executor(st.Completed())
        with crash_at(sr, "_integration_generation", after=True, when=lambda n, *a, **k: a[2] == 4):
            with self.assertRaises(Crash):
                self.integrate(store, ids["integration"], selector, executor=refusing)
        with self.assertRaises(StopError) as raised:
            self.integrate(store, ids["integration"], selector, executor=refusing)
        self.assertEqual(sr.CODE_INTEGRATION_REPAIR_PLAN_INVALID, raised.exception.code)
        (old,) = self.integration_runs(store, ids["integration"])
        # runtime loss with the lost START's opening still uncommitted: refused before any effect, nothing begins
        self.runtime_gone(store)
        with self.assertRaises(StopError) as raised:
            self.integrate(store, ids["integration"], selector, executor=refusing)
        self.assertEqual("dirty_overlap", raised.exception.code)
        self.assertEqual([], MutationController(store).list_pending())
        self.assertEqual([old], self.integration_runs(store, ids["integration"]))
        # the opening put back: a fresh Run begins over committed state and never names the settled one
        git(store.root, "checkout", "--", ".workline/events/events.jsonl")
        with self.assertRaises(StopError) as raised:
            self.integrate(store, ids["integration"], selector, executor=refusing)
        self.assertEqual(sr.CODE_INTEGRATION_REPAIR_PLAN_INVALID, raised.exception.code)
        runs = self.integration_runs(store, ids["integration"])
        self.assertEqual(2, len(runs))
        review = ReviewStore(store)
        (new,) = set(runs) - {old}
        envelope = review.read_task_input(str(review.gate_chain(new).generations[0].accepted_tasks[0]["task_id"]))
        self.assertEqual([], envelope.request_envelope["set_aside_runs"], "MC-7: the G4-terminal Run is never named")
        for run_id in runs:
            chain = review.gate_chain(run_id)
            self.assertEqual((4, None), (chain.latest.generation, chain.latest.receipt_id))
            self.assertEqual(history.DISPOSITION_NOT_AUTHORIZED, p4.final_disposition(review, chain))

    def test_an_interrupted_terminal_stage_is_finished_from_its_record(self) -> None:
        """§32.31 recoverably: interrupted after G5, or after the terminal stage is applied and before its commit,
        the next START finishes it - the same work_completed ID bound by the same Consumption, one of each."""
        for name, target, attribute in (("before the terminal stage", sr, "_integration_terminal"),
                                        ("before the finalization", st._Session, "_finalize_completion")):
            with self.subTest(name):
                store, _, ids = self.marked_project(name.replace(" ", "-"))
                with crash_at(target, attribute):
                    with self.assertRaises(Crash):
                        self.integrate(store, ids["integration"])
                recorded = MutationController(store).list_pending()[0]["reserved_ids"]
                self.assertEqual("completed", self.integrate(store, ids["integration"]).status)
                chain = self.one_run(store, ids["integration"])
                review = ReviewStore(store)
                consumption = review.consumption_by_receipt()[str(chain.latest.receipt_id)]
                events = [e for e in ProjectView.load(store).events_for(ids["integration"]) if e.type == "work_completed"]
                self.assertEqual([consumption.terminal_event_id], [event.id for event in events])
                if attribute == "_finalize_completion":
                    self.assertEqual(recorded.get(gate.review_consumption_key(str(chain.latest.receipt_id))),
                                     consumption.consumption_id)
                self.assertEqual([consumption.consumption_id], [found.consumption_id for found in review.consumptions()])
                self.assertEqual([], MutationController(store).list_pending())
                self.assertEqual([], validate_project(store))

    def test_the_interruption_matrix_of_one_reviewed_integration(self) -> None:
        """R39 (§32.62 items 1-7 and 13-21; items 8-12 are the G4-terminal / follow-up / successor rows above, 22-28
        test_roadmap_achievement_evidence's matrix): one reviewed integration completing its Phase, interrupted at each
        point and finished by re-running the same START with the same selector. Every retry keeps the reserved IDs
        (Run, Receipt, Consumption, evidence), makes no second Run / Receipt / Consumption / work_completed / evidence /
        completion commit / publication, never falls back to the ordinary executor, and leaves HEAD published."""
        from workline import roadmap_review as rr_module
        from workline.mutation import Mutation, MutationController as Controller

        def generation(number: int):
            return lambda n, *args, **kwargs: args[2] == number

        def finishing(number: int):
            return lambda n, store, gen, *a, **k: (gen.invocation or {}).get("generation") == number

        def completion_push(n, repo, *args, **kwargs) -> bool:
            return git(repo, "log", "-1", "--format=%s").startswith("chore(workline): complete")

        def terminal_effect(kind: str):
            def when(n, controller, record) -> bool:
                if record["kind"] == "create_file":
                    return kind in record["payload"]["path"]
                return record["kind"] == "append_event" and record["payload"]["record"]["type"] == kind
            return when

        points = (
            ("1 opening lifecycle recorded", sr, "_integration_open", True, None),
            ("2 Candidate frozen", sr, "_integration_freeze", True, None),
            ("3 G1 recorded, not committed", rr_module, "_finish_generation", False, finishing(1)),
            ("3 G1 committed", sr, "_integration_generation", True, generation(1)),
            ("4 discovery returned before G2", sr, "_integration_generation", False, generation(2)),
            ("5 G2 committed", sr, "_integration_generation", True, generation(2)),
            ("6 G3 recorded, not committed", rr_module, "_finish_generation", False, finishing(3)),
            ("6 G3 committed", sr, "_integration_generation", True, generation(3)),
            ("7 adjudicator returned before G4", sr, "_integration_generation", False, generation(4)),
            ("G4 committed", sr, "_integration_generation", True, generation(4)),
            ("G5 committed", sr, "_integration_generation", True, generation(5)),
            ("17 achievement ID reserved", Mutation, "reserve_id", True,
             lambda n, mutation, key, kind, *a, **k: kind == "review_achievement"),
            ("13 terminal stage recorded, not applied", Mutation, "apply", False,
             lambda n, mutation, *a, **k: any(e["kind"] == "create_file" and "/consumptions/" in e["payload"]["path"]
                                              and not e.get("applied") for e in mutation.effects)),
            ("14 / 19 partial terminal apply (work_completed applied)", Controller, "apply_effect", True,
             terminal_effect("work_completed")),
            ("18 achievement record applied", Controller, "apply_effect", True, terminal_effect("/history/achievements/")),
            ("15 / 20 terminal commit, not published", gitcmd, "push", False, completion_push),
            ("16 terminal publication", gitcmd, "push", True, completion_push),
            ("21 postcommit basis proof", sr, "completion_postcommit", False, None),
        )
        for name, target, attribute, after, when in points:
            with self.subTest(name):
                store, phase_id, ids = self.marked_project("p" + "".join(c for c in name if c.isalnum())[:24].lower(),
                                                           remote=True)
                integration = ids["integration"]
                log: list[str] = []
                with crash_at(target, attribute, after=after, when=when):
                    with self.assertRaises(Crash):
                        self.integrate(store, integration, phase_review(), log=log)
                reserved = {key: value for record in MutationController(store).list_pending()
                            for key, value in (record.get("reserved_ids") or {}).items()}
                self.assertEqual("completed", self.integrate(store, integration, phase_review(), log=log).status)
                self.assertNotIn(integration, log, "never run by the ordinary executor")
                review = ReviewStore(store)
                (run_id,) = self.integration_runs(store, integration)
                chain = review.gate_chain(run_id)
                self.assertTrue(chain.latest.sealed)
                if any(value.startswith("rr_") for value in reserved.values()):
                    self.assertIn(run_id, reserved.values(), "the reserved Run is the one finished")
                (consumption,) = review.consumptions()
                self.assertEqual(str(chain.latest.receipt_id), consumption.receipt_id)
                completed = [e.id for e in ProjectView.load(store).events_for(integration) if e.type == "work_completed"]
                self.assertEqual([consumption.terminal_event_id], completed)
                (evidence,) = review.phase_completion_evidence()
                self.assertEqual(phase_id, evidence.phase_id)
                for value, kind in ((consumption.consumption_id, "rcs_"), (evidence.achievement_evidence_id, "rha_")):
                    if any(item.startswith(kind) for item in reserved.values()):
                        self.assertIn(value, reserved.values(), f"the reserved {kind} ID is the one kept")
                subjects = self.subjects(store, 60)
                display = ProjectView.load(store).works[integration].display
                self.assertEqual(1, subjects.count(f"chore(workline): complete {display}"), subjects)
                self.assertEqual(self.head(store), self.remote_head(store.root.name), "published once, HEAD == remote")
                self.assertEqual([], MutationController(store).list_pending())
                self.assertEqual([], validate_project(store))

    def test_a_verification_that_mutates_project_state_never_settles(self) -> None:
        """§32.29: START measures the Project state around every launch; a discovery that writes persistent state
        settles nothing (``result_paths=()`` is never proof), and the Run stays at G1."""
        store, _, ids = self.marked_project()

        def write() -> None:
            (store.root / "side_effect.txt").write_text("written by the verifier\n", encoding="utf-8")

        with self.assertRaises(StopError) as raised:
            self.integrate(store, ids["integration"], phase_review(Discovery(mutate=write)))
        self.assertEqual(sr.CODE_INTEGRATION_SIDE_EFFECT, raised.exception.code)
        self.assertEqual(1, self.one_run(store, ids["integration"]).latest.generation)

    def test_first_run_gets_a_p5_final_disposition_and_no_receipt(self) -> None:
        """§32.23 (I-6, R26 / R16): a CONFIRMATION_STRUCTURE_REQUIRED Run is final ``not_authorized`` at G4 - its P5
        summary binds the disposition that explains the structure was required - with no Receipt. START then creates
        exactly one deterministic confirmation through CREATE (no reviewer text), commits it alone, and a successor
        Run of the same integration - naming nothing set aside - authorizes the integration over a Candidate that
        binds the confirmation; the Phase now waits for that confirmation."""
        store, phase_id, ids = self.marked_project()
        integration = ids["integration"]
        adjudicator = Adjudicator(ri.HUMAN_CONFIRMATION_REQUIRED)
        result = self.integrate(store, integration, phase_review(Discovery(), adjudicator=adjudicator))
        self.assertEqual("completed", result.status)
        first, successor = (ReviewStore(store).gate_chain(run_id) for run_id in self.integration_runs_in_order(
            store, integration))
        review = ReviewStore(store)
        self.assertEqual((4, None), (first.latest.generation, first.latest.receipt_id))
        self.assertEqual(ri.BRANCH_CONFIRMATION_STRUCTURE_REQUIRED,
                         review.read_adjudication(first.review_run_id).integration_disposition)
        summary = review.read_history(review_paths.HISTORY_RUNS, first.review_run_id)
        self.assertEqual((history.DISPOSITION_NOT_AUTHORIZED, None), (summary.durable_disposition, summary.receipt_id))
        self.assertEqual(history.DISPOSITION_NOT_AUTHORIZED, p4.final_disposition(review, first))
        view = ProjectView.load(store)
        (confirmation,) = [work for work in view.effective_works(phase_id) if work.work_kind == pi.CONFIRMATION_KIND]
        built = sir.confirmation_structure(phase_id, view.phases[phase_id].display, integration)
        self.assertEqual((built.name, built.desired_state, [integration]),
                         (confirmation.name, confirmation.section(WORK_DESIRED_HEADING),
                          list(pi.confirmation_targets(confirmation))))
        self.assertIn(integration, [r.from_id for r in view.relations_to(confirmation.id, "requires_completion")])
        envelope = review.read_task_input(str(successor.generations[0].accepted_tasks[0]["task_id"])).request_envelope
        self.assertEqual([], envelope["set_aside_runs"], "MC-7: the final Run is never named")
        candidate = review.read_candidate_snapshot(successor.generations[0].candidate_hash).material
        self.assertEqual([confirmation.id], candidate["downstream_confirmation_ids"])
        self.assertTrue(successor.latest.sealed)
        self.assertEqual(history.DISPOSITION_CONSUMED, p4.final_disposition(review, successor))
        self.assertEqual("completed", view.work_state(integration).state)
        self.assertEqual("unstarted", view.work_state(confirmation.id).state)
        self.assertFalse(view.phase_completion(phase_id).complete, "the Phase waits for its confirmation")
        self.assertEqual((), review.phase_completion_evidence())
        log = git(store.root, "log", "--format=%s", "-3").splitlines()
        self.assertTrue(log[0].startswith("chore(workline): complete "), log)
        structure = [subject for subject in git(store.root, "log", "--format=%s").splitlines()
                     if subject.startswith("chore(workline): add the Phase confirmation of ")]
        self.assertEqual(1, len(structure))
        self.assertEqual([], MutationController(store).list_pending())
        self.assertEqual([], validate_project(store))

    def test_domain_repair_run_gets_a_p5_terminal_g4_disposition(self) -> None:
        """§32.25 - §32.27 (I-6, R26 / R16, RB5B-L9 b): a DOMAIN_REPAIR_REQUIRED Run is final ``not_authorized`` at G4
        with no Receipt; START's repair plan registers a normal fix Work before the SAME integration and moves the
        target off (``moved``); after the fix completes, the integration is entered again - a new Run over a new
        Candidate, never naming the final one - and it completes the Phase. No second integration exists."""
        store, phase_id, ids = self.marked_project()
        integration = ids["integration"]
        log: list = []
        moved = self.integrate(store, integration, phase_review(Discovery(claim("problem"))),
                               executor=repairing_executor(store, log))
        self.assertEqual("moved", moved.status)
        review = ReviewStore(store)
        (first_id,) = self.integration_runs(store, integration)
        first = review.gate_chain(first_id)
        self.assertEqual((4, None), (first.latest.generation, first.latest.receipt_id))
        self.assertEqual(history.DISPOSITION_NOT_AUTHORIZED,
                         review.read_history(review_paths.HISTORY_RUNS, first_id).durable_disposition)
        view = ProjectView.load(store)
        (fix,) = [work for work in view.effective_works(phase_id) if work.name == "Fix the integrated report"]
        self.assertEqual(("in_progress", False), (view.work_state(integration).state,
                                                  view.work_state(integration).has_target))
        self.assertIn(fix.id, [r.from_id for r in view.relations_to(integration, "requires_completion")])
        self.assertEqual([integration], [w.id for w in view.effective_works(phase_id) if w.work_kind == pi.INTEGRATION_KIND])
        self.assertEqual([], MutationController(store).list_pending())
        self.assertEqual("completed", st.start(store, fix.id, "single-work", completing_executor(store)).status)
        done = self.integrate(store, integration, phase_review(Discovery()))
        self.assertEqual("completed", done.status)
        runs = self.integration_runs(store, integration)
        (second_id,) = set(runs) - {first_id}
        second = review.gate_chain(second_id)
        envelope = review.read_task_input(str(second.generations[0].accepted_tasks[0]["task_id"])).request_envelope
        self.assertEqual([], envelope["set_aside_runs"])
        candidate = review.read_candidate_snapshot(second.generations[0].candidate_hash).material
        self.assertIn(fix.id, candidate["effective_work_ids"])
        self.assertEqual(history.DISPOSITION_NOT_AUTHORIZED, p4.final_disposition(review, first))
        self.assertTrue(ProjectView.load(store).phase_completion(phase_id).complete)
        self.assertEqual(1, len(review.phase_completion_evidence()))
        self.assertEqual([], validate_project(store))

    def test_g4_terminal_follow_ups_are_finished_from_the_record(self) -> None:
        """R26 interruption / recovery (§32.62 items 9-12): interrupted inside the repair follow-up - after the plan
        is kept, after the fix Work's registration, after the target removal, after the move commit - or inside the
        confirmation structure - after its registration, after its commit - the next START finishes the SAME
        decision from its record: the executor is never asked again, one fix Work / one confirmation exists, the
        Run is never repeated."""
        kept = lambda n, mutation, run_id, entry: entry is not None  # noqa: E731 - the save that keeps the plan
        repair_points = (("plan kept", sr, "_set_followup", True, kept),
                         ("registered", st._Session, "_lifecycle", False, None),
                         ("removed", st._Session, "_commit", False, None),
                         ("committed", st._Session, "_commit", True, None))
        for name, target, attribute, after, when in repair_points:
            with self.subTest(follow_up="repair", point=name):
                store, phase_id, ids = self.marked_project("repair-" + name.replace(" ", "-"))
                log: list = []
                executor = repairing_executor(store, log)
                selector = phase_review(Discovery(claim("problem")))
                with crash_at(target, attribute, after=after, when=when):
                    with self.assertRaises(Crash):
                        self.integrate(store, ids["integration"], selector, executor=executor)
                self.assertEqual("moved", self.integrate(store, ids["integration"], selector, executor=executor).status)
                view = ProjectView.load(store)
                fixes = [w for w in view.effective_works(phase_id) if w.name == "Fix the integrated report"]
                self.assertEqual(1, len(fixes))
                self.assertEqual(1, len([context for _, context in log if context is not None]), "asked once")
                self.assertEqual(1, len(self.integration_runs(store, ids["integration"])))
                self.assertFalse(view.work_state(ids["integration"]).has_target)
                self.assertEqual([], MutationController(store).list_pending())
                self.assertEqual([], validate_project(store))
        structure_points = (("registered", st._Session, "_commit", False),
                            ("committed", sr, "_integration_successor", False))
        for name, target, attribute, after in structure_points:
            with self.subTest(follow_up="structure", point=name):
                store, phase_id, ids = self.marked_project("structure-" + name.replace(" ", "-"))
                selector = phase_review(Discovery(), adjudicator=Adjudicator(ri.HUMAN_CONFIRMATION_REQUIRED))
                when = (lambda n, session, prefix, *a, **k: prefix.endswith(":structure-commit")) \
                    if attribute == "_commit" else None
                with crash_at(target, attribute, after=after, when=when):
                    with self.assertRaises(Crash):
                        self.integrate(store, ids["integration"], selector)
                self.assertEqual("completed", self.integrate(store, ids["integration"], selector).status)
                view = ProjectView.load(store)
                self.assertEqual(1, len([w for w in view.effective_works(phase_id) if w.work_kind == pi.CONFIRMATION_KIND]))
                self.assertEqual(2, len(self.integration_runs(store, ids["integration"])))
                self.assertEqual([], MutationController(store).list_pending())
                self.assertEqual([], validate_project(store))

    def test_successor_run_of_the_same_integration_sets_the_old_run_aside(self) -> None:
        """R8 / P4-R7 / GAP-G (RB5B-L9 c, MC-7): a G4 HUMAN_WAIT Run stays the same canonical Run - its START stays
        pending, and after runtime loss a fresh START without a decision begins nothing beside it - until an explicit
        Human decision with its evidence exits it. Only then does a successor Run of the same integration name exactly
        that Run as set aside (``human_decision``), persist the evidence in its G1 before any launch, and authorize
        the terminal stage. The waiting Run itself is never sealed; a G4-terminal Run is never named
        (``test_g4_terminal_run_is_never_recovered_as_authorizable``)."""
        for lost in (False, True):
            with self.subTest(runtime_lost=lost):
                store, _, ids = self.marked_project("lost" if lost else "held")
                integration = ids["integration"]
                with self.assertRaises(StopError) as raised:
                    self.integrate(store, integration, phase_review(Discovery(claim("human"))))
                self.assertEqual(p4.CODE_HUMAN_WAIT, raised.exception.code)
                (waiting,) = self.integration_runs(store, integration)
                if lost:
                    self.runtime_gone(store)
                    git(store.root, "checkout", "--", ".workline/events/events.jsonl")
                    with self.assertRaises(StopError) as raised:
                        self.integrate(store, integration, phase_review(Discovery()))
                    self.assertEqual(p4.CODE_HUMAN_WAIT, raised.exception.code, "no decision: the same waiting Run")
                    self.assertEqual([waiting], self.integration_runs(store, integration))
                    self.assertEqual([], MutationController(store).list_pending())
                review = ReviewStore(store)
                decision = p4.HumanDecision("hd-1", p4.DECISION_CONFIRMED)
                evidence = decision_evidence(review, waiting, decision,
                                             sr.current_integration_requirement(store, integration))
                discovery, adjudicator = Discovery(), Adjudicator()
                selector = sr.PhaseIntegrationReview(discovery=(discovery.binding(),), adjudicator=adjudicator.binding(),
                                                     human_decision=decision, decision_evidence=(evidence,))

                def unfrozen(n, session, view, work, run_id, set_aside) -> bool:
                    return run_id not in (session.mutation.note(sr.NOTE_INTEGRATION_FREEZE) or {})

                # interrupted after the decision is bound and the next Run reserved, before it is frozen
                with crash_at(sr, "_integration_freeze", when=unfrozen):
                    with self.assertRaises(Crash):
                        self.integrate(store, integration, selector)
                self.assertEqual("completed", self.integrate(store, integration, selector).status)
                (successor,) = set(self.integration_runs(store, integration)) - {waiting}
                chain = review.gate_chain(successor)
                envelope = review.read_task_input(str(chain.generations[0].accepted_tasks[0]["task_id"])).request_envelope
                self.assertEqual([{"review_run_id": waiting, "reason": p4.SET_ASIDE_HUMAN_DECISION}],
                                 envelope["set_aside_runs"])
                self.assertEqual(decision.to_record(), envelope["human_decision"])
                (bound,) = envelope["decision_evidence"]
                self.assertEqual(waiting, review.read_history(review_paths.HISTORY_HUMAN_DECISIONS,
                                                              bound["review_decision_id"]).affected_review_run_id)
                old = review.gate_chain(waiting)
                self.assertEqual((4, None), (old.latest.generation, old.latest.receipt_id))
                self.assertEqual(history.DISPOSITION_HUMAN_WAIT, p4.final_disposition(review, old))
                self.assertTrue(chain.latest.sealed)
                self.assertEqual(history.DISPOSITION_CONSUMED, p4.final_disposition(review, chain))
                self.assertEqual(1, len(discovery.tasks), "the successor asked its own discovery once")
                self.assertEqual("completed", ProjectView.load(store).work_state(integration).state)
                self.assertEqual([], MutationController(store).list_pending())
                self.assertEqual([], validate_project(store))

    def test_candidate_binds_the_current_effective_policy_hash(self) -> None:
        """R19 / R6-1: the Effective Policy is resolved once, before any reservation, and the SAME value is bound by
        the Candidate, generation 1 and every TaskInput."""
        store, _, ids = self.marked_project()
        self.integrate(store, ids["integration"])
        chain = self.one_run(store, ids["integration"])
        review = ReviewStore(store)
        candidate = review.read_candidate_snapshot(chain.generations[0].candidate_hash).material
        effective = p4.run_effective_policy(review, chain)
        self.assertIsNotNone(effective)
        expected = p4.run_effective_policy_hash(p4.P6_POLICY_ID, effective)
        self.assertEqual(expected, candidate["effective_policy_hash"])
        self.assertEqual({expected}, {found.effective_policy_hash for found in chain.generations})

    def test_candidate_binds_the_achievement_history_readers_validated_refs(self) -> None:
        """RB5FB-3 / R10: at freeze the achievement history reader supplies the refs the Candidate binds, exactly."""
        store, phase_id, ids = self.marked_project()
        ref = (phase_id, ident("rha", 7), "e" * 64)
        with mock.patch.object(achievement_reader, "candidate_achievement_refs", return_value=(ref,)) as reader:
            with crash_at(sr, "_integration_launch"):
                with self.assertRaises(Crash):
                    self.integrate(store, ids["integration"])
        self.assertEqual(phase_id, reader.call_args.args[2])
        candidate = ReviewStore(store).read_candidate_snapshot(
            self.one_run(store, ids["integration"]).generations[0].candidate_hash).material
        self.assertEqual([{"phase_id": phase_id, "achievement_evidence_id": ident("rha", 7), "evidence_digest": "e" * 64}],
                         candidate["achievement_evidence_refs"])


class BothSelectorsTests(IntegrationRunCase):
    """RB5J-1 (§32.14): with both selectors supplied, each applies only to its own Review kind."""

    def work_review(self) -> Any:
        from workline.review import work_review

        def never(task):
            raise AssertionError("the Work Formal Review reviewer is never asked for a marked integration")

        return work_review.WorkReview(never, "reviewer-x", "1")

    def test_a_marked_integration_named_with_both_selectors_runs_phase_integration_review_alone(self) -> None:
        """Single-work naming a marked integration: ``review=`` applies to nothing - in a Project with NO P3
        Work-terminal activation there is no ``review_not_activated``, the record carries no review-v1 Work marker,
        and the integration finishes by START's ordinary ``<Work>:finalize`` commit AND push (§32.31)."""
        store, phase_id, ids = self.marked_project(remote=True)
        self.assertFalse((store.root / ".workline" / "review" / "activation" / "work-terminal-v1.yaml").exists())
        result = st.start(store, ids["integration"], "single-work", completing_executor(store),
                          review=self.work_review(), phase_review=phase_review())
        self.assertEqual("completed", result.status)
        head = gitcmd.head_commit(store.root)
        self.assertEqual(head, git(self.remote_path("proj"), "rev-parse", "main").strip(), "pushed")
        subject = git(store.root, "log", "-1", "--format=%s").strip()
        self.assertEqual(f"chore(workline): complete {ProjectView.load(store).works[ids['integration']].display}",
                         subject)
        self.assertEqual("completed", ProjectView.load(store).work_state(ids["integration"]).state)
        self.assertTrue(self.one_run(store, ids["integration"]).latest.sealed)
        self.assertEqual([], validate_project(store))

    def test_a_phase_review_only_resume_of_the_same_slot_continues(self) -> None:
        """The interrupted both-selectors START left a legacy record (no review-v1 Work marker), so a
        ``phase_review``-only START of the same slot resumes it - never ``review_marker_mismatch`` - and finishes."""
        store, _, ids = self.marked_project()
        with crash_at(sr, "_integration_launch"):
            with self.assertRaises(Crash):
                st.start(store, ids["integration"], "single-work", completing_executor(store),
                         review=self.work_review(), phase_review=phase_review())
        (pending,) = MutationController(store).list_pending()
        self.assertEqual({"operation": "start", "work_id": ids["integration"], "mode": "single-work"},
                         pending["invocation"])
        result = self.integrate(store, ids["integration"])
        self.assertEqual(("completed", pending["mutation_id"]), (result.status, result.mutation_id))
        self.assertEqual([], MutationController(store).list_pending())

    def test_outer_mode_with_both_selectors_fails_closed(self) -> None:
        """The outer combination is not settled by the frozen text (a review-v1 Work mutation commits only review-v1
        Work commits and publishes only by push-only stages, while the integration finishes by an ordinary commit and
        push): an outer START naming a marked integration with both selectors STOPs before anything is written, and
        an outer review-v1 continuation that reaches one ends before it, nothing of it recorded."""
        store, _, ids = self.marked_project()
        before = (gitcmd.head_commit(store.root), [e.id for e in ProjectView.load(store).events])
        with self.assertRaises(StopError) as raised:
            st.start(store, ids["integration"], "outer", completing_executor(store),
                     review=self.work_review(), phase_review=phase_review())
        self.assertEqual(st.CODE_SELECTORS_OUTER, raised.exception.code)
        self.assertEqual(before, (gitcmd.head_commit(store.root), [e.id for e in ProjectView.load(store).events]))
        self.assertEqual([], MutationController(store).list_pending())
        self.assertEqual([], self.integration_runs(store, ids["integration"]))
        from workline.start_integration_review import SEMANTICS_REVIEWED

        session = st._Session(store, None, None, "outer", completing_executor(store), review=self.work_review(),
                              phase_review=phase_review(), semantics=SEMANTICS_REVIEWED)
        reason = session.unreviewable_integration(ProjectView.load(store).works[ids["integration"]])
        self.assertIn("runs review-v1 Work Review", reason)
        session.review = None
        self.assertIsNone(session.unreviewable_integration(ProjectView.load(store).works[ids["integration"]]))

    def test_an_ordinary_work_keeps_review_v1_with_both_selectors(self) -> None:
        """The other side of §32.14: an ordinary Work named with both selectors keeps ``review=`` exactly - here its
        P3 activation is asked and refuses (``review_not_activated``) before anything is written."""
        from planning_helpers import CANONICAL_RULE

        store, _, ids = self.marked_project(complete_w1=False, attributes=CANONICAL_RULE + "\n")
        with self.assertRaises(StopError) as raised:
            st.start(store, ids["w1"], "single-work", completing_executor(store), review=self.work_review(),
                     phase_review=phase_review())
        self.assertEqual("review_not_activated", raised.exception.code)
        self.assertEqual([], MutationController(store).list_pending())


class WorkReviewRefsTests(IntegrationRunCase):
    """RB5J-2 (§32.18 / §14.5): the Candidate binds the validated P5 Work Review refs of its Phase - and only those."""

    def test_the_candidate_binds_exactly_the_validated_p5_work_review_ref_of_its_phase(self) -> None:
        from test_review_p4_work import work_p4

        from planning_helpers import CANONICAL_RULE
        from workline.review import work_review

        store, phase_id, ids = self.marked_project(complete_w1=False, remote=True, attributes=CANONICAL_RULE + "\n",
                                                   second_phase=True)
        self.activate(store)

        def producing(name: str):
            def execute(ctx):
                (store.root / name).write_bytes(b"result\n")
                return st.Completed((name,), message=f"feat: {name}")
            return execute

        for key, name in (("w1", "out-w1.txt"), ("other", "out-x.txt")):
            self.assertEqual("completed", st.start(store, ids[key], "single-work", producing(name),
                                                   review=work_p4()).status)
        review = ReviewStore(store)
        runs = {consumption.target_identity: consumption.review_run_id for consumption in review.consumptions()
                if getattr(consumption, "review_kind", None) == work_review.REVIEW_KIND}
        self.assertEqual({ids["w1"], ids["other"]}, set(runs))
        self.assertEqual("completed", self.integrate(store, ids["integration"]).status)
        candidate = review.read_candidate_snapshot(
            self.one_run(store, ids["integration"]).generations[0].candidate_hash).material
        expected = [{"work_id": ids["w1"], "review_run_id": runs[ids["w1"]],
                     "run_summary_digest": review.history_digest(review_paths.HISTORY_RUNS, runs[ids["w1"]])}]
        self.assertEqual(expected, candidate["work_review_refs"], "the other Phase's Run contributes none")
        committed = sr.committed_view_at(store, sr.hermetic_module.enter(store), gitcmd.head_commit(store.root))
        self.assertEqual([(ids["w1"], runs[ids["w1"]], expected[0]["run_summary_digest"])],
                         sr._integration_work_review_refs(review, committed, phase_id))
        with mock.patch.object(history, "run_summary_problems", return_value=[("review_record_invalid", "differs")]):
            self.assertEqual([], sr._integration_work_review_refs(review, committed, phase_id),
                             "a Run whose summary does not validate contributes none")


class ReviewedPhaseEndToEndTests(IntegrationRunCase):
    """RB5I-1 (the landing constraint): review-v1 Phase entry -> ordinary Works -> the integration START with
    ``phase_review=`` -> Phase COMPLETE, through the public owners only."""

    def test_review_v1_phase_entry_to_phase_complete(self) -> None:
        store = self.planning_project()
        phase_id = rm.create_roadmap(store, plan()).phase_ids["a"]
        result = self.reviewed_entry(store, phase_id, the_design=design(confirmation=False))
        view = ProjectView.load(store)
        integration = planning.candidate_content(registered(store, result).material)["integration"]["id"]
        self.assertEqual(V1, view.works[integration].phase_review_contract)
        entry = next(work.id for work in view.effective_works(phase_id) if work.id != integration
                     and view.work_state(work.id).state == "unstarted" and view.dependencies_satisfied(work.id))
        log: list[str] = []
        done = self.integrate(store, entry, mode="outer", log=log)
        self.assertEqual("phase_complete", done.status)
        self.assertNotIn(integration, log)
        view = ProjectView.load(store)
        self.assertTrue(view.phase_completion(phase_id).complete)
        self.assertTrue(pi.phase_generated_complete(view, phase_id))
        self.assertEqual(pi.MODE_REVIEWED, pi.completion_mode(view, phase_id))
        (evidence,) = ReviewStore(store).phase_completion_evidence()
        self.assertEqual((integration, done.mutation_id), (evidence.covering_integration_id, evidence.causing_mutation_id))
        self.assertTrue(achievement_reader.phase_progression_ready(store, phase_id).ready)
        self.assertEqual([], MutationController(store).list_pending())
        self.assertEqual([], validate_project(store))

if __name__ == "__main__":
    unittest.main()
