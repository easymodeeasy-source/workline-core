"""§28 T: Phase-entry continuation mode (P2-IMPL-BLOCKER-006).

Once the slot's pending review-v1 Phase-entry planning mutation holds a Run with a canonical generation 1,
the facts that decide whether a *new* entry may begin no longer refuse that request (§5.8). Every static and
structural check still runs, a call that is not that request is still refused at the same-request check, and
a changed fact is classified by currency, the use check and the proofs — on committed state, so an
uncommitted effect of an operation the publication barrier holds back is never currency.
"""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import git
from planning_helpers import (
    Crash,
    PlanningTestCase,
    Reviewer,
    crash_at,
    design,
    plan,
    rr,
    run_ids,
)
from test_review_planning_writer_input import conditional

from workline import gitops, ids
from workline import mutation as mutation_module
from workline import roadmap as rm
from workline.errors import ReconcileRequired, SpecViolation, StopError, ValidationError
from workline.review import gate, planning
from workline.review.store import ReviewStore
from workline.state import ProjectView
from workline.store import Event, Relation, render_event_line, render_relations
from workline.mutation import utc_now

EVENT_LOG = ".workline/events/events.jsonl"
ROADMAP_LEDGER = ".workline/relations/roadmap.yaml"

#: every refusal that decides whether a *new* Phase entry may begin (§5.8).
ADMISSION_CODES = ("roadmap_held", "spec_violation", "phase_blocked", "phase_already_expanded",
                   "ambiguous_startable_candidates", "postcheck_failed")


class _ContinuationCase(PlanningTestCase):
    """A Project whose review-v1 Phase entry is pending, its Run stopped at a chosen generation."""

    remote = False

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project(remote=self.remote)
        created = rm.create_roadmap(self.store, plan())
        self.roadmap_id, self.phase_id = created.roadmap_id, created.phase_ids["a"]
        self.the_design = design(entry="w1")
        #: a person's own ``phase_held`` line: while this Phase's entry is pending no Workline
        #: ``phase-hold`` can apply one, because its scope overlaps the planning mutation's (§13.5).
        self.hold_lines = self.event_line("phase_held", self.phase_id)

    def entry(self, the_design=None):
        return self.reviewed_entry(self.store, self.phase_id, Reviewer(), the_design or self.the_design)

    def crash(self, target, name, **kwargs) -> None:
        with crash_at(target, name, **kwargs):
            with self.assertRaises(Crash):
                self.entry()

    def pending_entry(self) -> dict:
        (found,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "phase-entry"]
        return found

    def admitted(self, the_design=None):
        """The same request again: its result, or the exception the frozen machinery classified it with.

        Whatever the outcome, it is never one of the new-entry admission refusals.
        """
        try:
            return self.entry(the_design)
        except (StopError, ValidationError, ReconcileRequired) as exc:
            self.assertNotIn(getattr(exc, "code", None), ADMISSION_CODES, f"an admission refusal: {exc}")
            return exc

    def event_line(self, event_type: str, entity_id: str) -> bytes:
        """One event line as the production renderer writes it, for a person to commit."""
        return (render_event_line(Event(ids.new_id("event"), event_type, entity_id, utc_now())) + "\n").encode(
            "utf-8"
        )

    def persons_commit(self, lines: bytes) -> str:
        path = self.store.root / EVENT_LOG
        path.write_bytes(path.read_bytes() + lines)
        return self.commit_all(self.store, "a person commits a lifecycle change", EVENT_LOG)



# --------------------------------------------------------------------------- T-A, T-B: the deadlock
class DeadlockTests(_ContinuationCase):
    """T-A: a Roadmap hold held by the publication barrier no longer stops the planning operation it waits for."""

    remote = True

    def test_a_both_operations_finish_through_workline(self) -> None:
        self.crash(rr, "_c2_kp")  # Kp made, its ID saved, C-2(Kp) not run (§21.1 row 23)
        kp = self.head(self.store)
        record = self.pending_entry()

        with self.assertRaises(StopError) as barrier:
            rm.hold_roadmap(self.store, self.roadmap_id)
        self.assertEqual("review_publication_barrier", barrier.exception.code)
        self.assertEqual(kp, self.head(self.store), "the hold made no commit")
        self.assertNotEqual(kp, self.remote_head(), "the destination never received Kp")
        (hold,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-hold"]
        self.assertTrue(hold["effects"], "the hold stays pending with its domain effects applied")
        self.assertIn("roadmap_held", (self.store.root / EVENT_LOG).read_text(encoding="utf-8"))

        result = self.entry()  # the same request, not stopped by roadmap_held, the Phase state or startability
        self.assertEqual("registered", result.status)
        self.assertEqual(record["mutation_id"], result.mutation_id, "the same planning mutation continued")
        km = result.registration.head
        self.assertEqual(km, self.remote_head(), "the planning operation published exactly Km")
        consumption = ReviewStore(self.store).read_consumption(result.consumption_id)
        self.assertEqual(kp, consumption.persisted_result["registration_commit"])

        held = rm.hold_roadmap(self.store, self.roadmap_id)  # the pending hold, retried
        self.assertEqual(held.head, self.remote_head(), "the hold commits and publishes on top of Km")
        self.assertEqual([], self.pending(self.store), "both operations completed through Workline")
        self.assertEqual("held", ProjectView.load(self.store).roadmap_lifecycle(self.roadmap_id))

    def test_a_nothing_but_workline_touched_the_records_or_the_branch(self) -> None:
        self.crash(rr, "_c2_kp")
        with self.assertRaises(StopError):
            rm.hold_roadmap(self.store, self.roadmap_id)
        before = self.head(self.store)
        pending = {r["mutation_id"] for r in self.pending(self.store)}
        self.assertEqual(2, len(pending), "one planning mutation and one hold, both pending")

        self.assertEqual("registered", self.entry().status)
        rm.hold_roadmap(self.store, self.roadmap_id)

        self.assertEqual([], self.pending(self.store))
        self.assertEqual("0", git(self.store.root, "rev-list", "--count", f"{self.head(self.store)}..{before}").strip(),
                         "the branch only moved forward: Kp is still in the history it ends with")
        self.assertEqual([], [line for line in git(self.store.root, "reflog", "--format=%gs").splitlines()
                              if "reset" in line or "rebase" in line or "amend" in line])


class RemotelessHoldTests(_ContinuationCase):
    """T-B: remote-less, the hold commits at once and the committed change is classified by §13, never roadmap_held."""

    def test_b_the_committed_hold_is_classified_by_the_proof_that_owns_that_window(self) -> None:
        self.crash(rr, "_c2_kp")
        kp = self.head(self.store)
        rm.hold_roadmap(self.store, self.roadmap_id)  # no destination, so no barrier: it commits on top of Kp
        result = self.admitted()
        self.assertEqual("registered", getattr(result, "status", None), "never roadmap_held; C-2(Kp) decides")
        consumption = ReviewStore(self.store).read_consumption(result.consumption_id)
        self.assertEqual(kp, consumption.persisted_result["registration_commit"])
        self.assertEqual("held", ProjectView.load(self.store).roadmap_lifecycle(self.roadmap_id),
                         "the hold stands; P12 read Kp's parent P, where the Roadmap was active (§15.3)")


# --------------------------------------------------------------------------- T-C: the boundary
class BoundaryTests(_ContinuationCase):
    """T-C: the boundary is a canonical generation 1 — committed at HEAD and reading back."""

    def test_c_before_generation_1_the_live_refusal_stands(self) -> None:
        self.crash(rr, "_accept")
        before = self.pending_entry()
        self.assertEqual((), run_ids(self.store), "no Run was accepted canonically")
        rm.hold_roadmap(self.store, self.roadmap_id)
        with self.assertRaises(StopError) as raised:
            self.entry()
        self.assertEqual("roadmap_held", raised.exception.code)
        self.assertEqual(before, self.pending_entry(), "the pending mutation is untouched")

    def test_c_a_generation_1_applied_but_not_committed_is_no_boundary(self) -> None:
        self.crash(gitops, "review_commit_effect")  # generation 1 applied, its commit not made
        self.assertTrue(run_ids(self.store), "generation 1 is in the working tree")
        self.assertFalse(any("record review generation" in subject for subject in self.subjects(self.store)),
                         "and it is not committed")
        rm.hold_roadmap(self.store, self.roadmap_id)
        with self.assertRaises(StopError) as raised:
            self.entry()
        self.assertEqual("roadmap_held", raised.exception.code, "an uncommitted generation 1 accepted nothing")

    def test_c_after_a_committed_generation_1_the_call_is_a_continuation(self) -> None:
        self.crash(rr, "_launch_and_settle")
        (run_id,) = run_ids(self.store)
        self.assertEqual(1, self.chain(self.store, run_id).latest.generation)
        rm.hold_roadmap(self.store, self.roadmap_id)
        result = self.admitted()
        self.assertEqual("stale", getattr(result, "status", None), "the currency of §13 owns the committed hold")
        self.assertEqual(planning.STALE_DECLARED_BASE, result.detail)

    def test_c_a_recovery_planning_mutation_is_covered_by_its_binding(self) -> None:
        self.crash(rr, "_seal")
        self.runtime_gone(self.store)
        self.crash(rr, "_use_check")  # a recovery planning mutation, bound to the canonical Run
        record = self.pending_entry()
        self.assertIn(planning.MARKER_RECOVERY, record["invocation"])
        key = gate.review_run_key(planning.KIND_PHASE_ENTRY, self.phase_id)
        bound = (record.get("reserved_ids") or {}).get(key)
        self.assertEqual(record["invocation"][planning.MARKER_RECOVERY], bound, "the canonical Run, bound")
        self.assertEqual(bound, ((record.get("notes") or {}).get("recovery_binding") or {}).get("review_run_id"))
        rm.hold_roadmap(self.store, self.roadmap_id)
        result = self.admitted()
        self.assertEqual("stale", getattr(result, "status", None))


# --------------------------------------------------------------------------- T-D / T-E: the suppressed set
class SuppressedChecksTests(_ContinuationCase):
    """T-D: with the Run at canonical generation 1, no mutable new-entry admission fact refuses the request."""

    def setUp(self) -> None:
        super().setUp()
        # A second Roadmap, made before this entry is pending: a Roadmap creation writes the same ledger,
        # so it could not run afterwards (the live scope overlap, §13.5).
        self.other_phase_id = rm.create_roadmap(self.store, plan("Other Roadmap")).phase_ids["a"]
        self.crash(rr, "_launch_and_settle")
        self.record = self.pending_entry()

    def assert_admitted(self) -> None:
        found = self.admitted()
        self.assertNotIsInstance(found, SpecViolation)
        self.assertNotIsInstance(found, ValidationError)

    def test_d_the_roadmap_is_held(self) -> None:
        rm.hold_roadmap(self.store, self.roadmap_id)
        self.assert_admitted()

    def test_d_the_roadmap_is_cancelled(self) -> None:
        rm.cancel_roadmap(self.store, self.roadmap_id)
        self.assert_admitted()

    def test_d_the_phase_is_held(self) -> None:
        self.persons_commit(self.hold_lines)
        self.assert_admitted()

    def test_d_a_lifecycle_decision_is_decided_and_not_applied(self) -> None:
        with crash_at(mutation_module.Mutation, "add_effects", after=True):
            with self.assertRaises(Crash):
                rm.hold_roadmap(self.store, self.roadmap_id)
        (decided,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-hold"]
        self.assertTrue(decided["effects"], "the hold decided its event")
        self.assert_admitted()

    def test_d_a_dependency_of_the_phase_is_unsatisfied(self) -> None:
        relations = self.store.read_relation_file("roadmap")
        relations.append(Relation(ids.new_id("relation"), "requires_completion", self.other_phase_id, self.phase_id))
        (self.store.root / ROADMAP_LEDGER).write_text(
            render_relations(relations), encoding="utf-8", newline="\n"
        )
        self.commit_all(self.store, "a person adds a dependency", ROADMAP_LEDGER)
        self.assertTrue(ProjectView.load(self.store).unsatisfied_dependencies(self.phase_id))
        self.assert_admitted()

    def test_d_the_explicit_entry_is_no_longer_startable(self) -> None:
        self.persons_commit(self.hold_lines)
        self.assertEqual([], ProjectView.load(self.store).startable_works(self.phase_id),
                         "the explicit entry w1 is not startable now")
        self.assert_admitted()


class BeforeTheBoundaryTests(_ContinuationCase):
    """T-E: before a canonical generation 1 each of those checks refuses, unchanged."""

    def setUp(self) -> None:
        super().setUp()
        self.crash(rr, "_accept")

    def test_e_a_held_roadmap_refuses(self) -> None:
        rm.hold_roadmap(self.store, self.roadmap_id)
        with self.assertRaises(StopError) as raised:
            self.entry()
        self.assertEqual("roadmap_held", raised.exception.code)

    def test_e_a_cancelled_roadmap_refuses(self) -> None:
        rm.cancel_roadmap(self.store, self.roadmap_id)
        with self.assertRaises(SpecViolation):
            self.entry()

    def test_e_a_held_phase_refuses(self) -> None:
        self.persons_commit(self.hold_lines)
        with self.assertRaises(SpecViolation):
            self.entry()

    def test_e_the_refusal_writes_nothing(self) -> None:
        rm.hold_roadmap(self.store, self.roadmap_id)
        before = {k: v for k, v in self.snapshot_state(self.store).items() if "/runtime/" not in k}
        with self.assertRaises(StopError):
            self.entry()
        after = {k: v for k, v in self.snapshot_state(self.store).items() if "/runtime/" not in k}
        self.assertEqual(before, after)


# --------------------------------------------------------------------------- T-F: static checks
class StaticChecksTests(_ContinuationCase):
    """T-F: continuation mode is no validation bypass."""

    def setUp(self) -> None:
        super().setUp()
        self.crash(rr, "_launch_and_settle")
        rm.hold_roadmap(self.store, self.roadmap_id)  # the very state that used to refuse the retry
        self.record = self.pending_entry()

    def assert_refused(self, exception, call) -> None:
        with self.assertRaises(exception):
            call()
        self.assertEqual(self.record, self.pending_entry(), "the pending record is untouched")

    def test_f_a_design_with_no_normal_work(self) -> None:
        # A malformed design for this slot is also not the pending mutation's request, so the same-request
        # check of §5.6 step 5 may refuse it before the static check of step 6 does. Either way the call
        # stops with nothing written: continuation mode admits no malformed design.
        self.assert_refused(
            (ValidationError, ReconcileRequired), lambda: self.entry(design(works={}, planned_next=(), entry=None))
        )

    def test_f_a_reserved_work_key(self) -> None:
        self.assert_refused(
            (ValidationError, ReconcileRequired),
            lambda: self.entry(design(works={"integration": "X"}, planned_next=(), entry=None)),
        )

    def test_f_a_caller_value_the_canonical_form_cannot_carry(self) -> None:
        bad = design(entry="w1", related=conditional({"kind": "path_glob", "pattern": "p", "weight": 1.5}))
        with self.assertRaises(ValidationError) as raised:
            self.entry(bad)
        self.assertEqual("review_candidate_unrepresentable", raised.exception.code)
        self.assertEqual(self.record, self.pending_entry())

    def test_f_a_different_request_is_still_refused(self) -> None:
        other = design(works={"w1": "W1 が成立する", "z": "Z が成立する"}, planned_next=(("w1", "z"),), entry="w1")
        self.assert_refused(ReconcileRequired, lambda: self.entry(other))

    def test_f_a_legacy_invocation_is_never_a_continuation(self) -> None:
        with self.assertRaises(StopError) as raised:
            rm.enter_phase(self.store, self.phase_id, self.the_design)
        self.assertEqual("roadmap_held", raised.exception.code, "legacy keeps the live admission refusal")
        self.assertEqual(self.record, self.pending_entry())

    def test_f_an_unreadable_project_structure_fails_closed(self) -> None:
        target = self.store.root / ".workline/phases" / f"{self.phase_id}.md"
        target.write_text("not a canonical entity\n", encoding="utf-8", newline="\n")
        with self.assertRaises((ValidationError, StopError)):
            self.entry()


# --------------------------------------------------------------------------- T-G / T-H: committed vs not
class CommittedChangeTests(_ContinuationCase):
    """T-G: a committed change is classified at the boundary the flow has reached, never swallowed."""

    def test_g_before_a_receipt_the_use_check_owns_it(self) -> None:
        self.crash(rr, "_use_check")
        rm.hold_roadmap(self.store, self.roadmap_id)
        result = self.entry()
        self.assertEqual(("stale", planning.STALE_DECLARED_BASE), (result.status, result.detail))
        self.assertEqual(4, self.chain(self.store, result.review_run_id).latest.generation)

    def test_g_after_the_registration_began_the_pre_kp_proof_owns_it(self) -> None:
        self.crash(rm, "register_works", when=lambda n, mutation, stage, specs, relations: stage == "integration")
        rm.hold_roadmap(self.store, self.roadmap_id)
        with self.assertRaises(ReconcileRequired) as raised:
            self.entry()
        self.assertEqual("review_registration_currency_changed", raised.exception.reason)
        self.assertFalse(any("expand phase" in subject for subject in self.subjects(self.store)), "no Kp")

    def test_g_after_kp_p12_reads_p_alone(self) -> None:
        self.crash(rr, "_c2_kp")
        rm.hold_roadmap(self.store, self.roadmap_id)  # committed on top of Kp: a descendant, never P
        result = self.entry()
        self.assertEqual("registered", result.status, "a fact committed after Kp is not what P12 reads (§15.3)")
        self.assertTrue(ReviewStore(self.store).consumption_ids())

    def test_g_a_declared_base_change_on_p_itself_is_p12(self) -> None:
        """The same fact where P12 does read it: on P, with the pre-Kp proof bypassed (§28 D, §15.3)."""
        self.crash(rm, "register_works", when=lambda n, mutation, stage, specs, relations: stage == "integration")
        rm.hold_roadmap(self.store, self.roadmap_id)
        with mock.patch.object(rr, "_pre_kp_proof", lambda *args, **kwargs: None):
            with self.assertRaises(ReconcileRequired) as raised:
                self.entry()
        self.assertEqual("review_persisted_proof_failed", raised.exception.reason)
        self.assertIn("C-2(Kp) P12", str(raised.exception))


class UncommittedChangeTests(_ContinuationCase):
    """T-H: an applied but uncommitted effect of an operation the barrier holds back is never currency."""

    remote = True

    def test_h_the_run_ends_exactly_as_one_with_no_such_operation(self) -> None:
        self.crash(rr, "_c2_kp")
        with self.assertRaises(StopError):
            rm.hold_roadmap(self.store, self.roadmap_id)  # applied, uncommitted, pending at the barrier
        result = self.entry()
        self.assertEqual("registered", result.status)
        chain = self.chain(self.store, result.review_run_id)
        self.assertEqual([1, 2, 3], [generation.generation for generation in chain.generations],
                         "no generation 4: the uncommitted hold was no declared-base change")
        material = ReviewStore(self.store).read_candidate_snapshot(chain.generations[0].candidate_hash).material
        self.assertEqual("active", material["declared_base"]["roadmap"]["lifecycle"],
                         "the reviewed base says active, and every proof passed on the committed views")
        self.assertEqual("held", ProjectView.load(self.store).roadmap_lifecycle(self.roadmap_id),
                         "while the working tree has said held since the barrier stopped that hold")


# --------------------------------------------------------------------------- T-I / T-J / T-K / T-L
class LegacyUnchangedTests(_ContinuationCase):
    """T-I: a legacy Phase entry never enters continuation mode."""

    def test_i_a_legacy_entry_into_a_held_roadmap_is_refused_fresh_and_interrupted(self) -> None:
        rm.hold_roadmap(self.store, self.roadmap_id)
        with self.assertRaises(StopError) as fresh:
            rm.enter_phase(self.store, self.phase_id, self.the_design)
        self.assertEqual("roadmap_held", fresh.exception.code)

        rm.resume_roadmap(self.store, self.roadmap_id)
        with crash_at(rm, "register_works"):
            with self.assertRaises(Crash):
                rm.enter_phase(self.store, self.phase_id, self.the_design)
        rm.hold_roadmap(self.store, self.roadmap_id)
        with self.assertRaises(StopError) as interrupted:
            rm.enter_phase(self.store, self.phase_id, self.the_design)
        self.assertEqual("roadmap_held", interrupted.exception.code, "a legacy interrupted entry keeps the live rule")

    def test_i_a_legacy_entry_reads_no_review_record(self) -> None:
        with mock.patch.object(ReviewStore, "gate_chain", side_effect=AssertionError("Review was read")):
            result = rm.enter_phase(self.store, self.phase_id, self.the_design)
        self.assertTrue(result.work_ids)


class RoadmapCreationTests(_ContinuationCase):
    """T-J: a review-v1 Roadmap creation has no such check and is unaffected."""

    def test_j_a_held_roadmap_elsewhere_refuses_nothing(self) -> None:
        rm.hold_roadmap(self.store, self.roadmap_id)
        result = self.reviewed_roadmap(self.store, Reviewer(), plan("Another Roadmap"))
        self.assertEqual("registered", result.status)


class LifecycleAndEntryWorkTests(_ContinuationCase):
    """T-K and T-L: no lifecycle authority, and the entry Work of the result is the reviewed one."""

    remote = True

    def test_k_the_end_state_holds_the_projects_own_facts_only(self) -> None:
        self.crash(rr, "_c2_kp")
        with self.assertRaises(StopError):
            rm.hold_roadmap(self.store, self.roadmap_id)
        self.assertEqual("registered", self.entry().status)
        rm.hold_roadmap(self.store, self.roadmap_id)
        view = ProjectView.load(self.store)
        self.assertEqual("held", view.roadmap_lifecycle(self.roadmap_id))
        self.assertEqual(4, len(view.phase_works(self.phase_id)), "w1, w2, the integration and the confirmation")
        events = (self.store.root / EVENT_LOG).read_text(encoding="utf-8")
        self.assertEqual(1, events.count('"roadmap_held"'), "one hold event; the continuation wrote none")

    def test_l_the_entry_work_is_the_reviewed_canonical_first_work(self) -> None:
        self.crash(rr, "_c2_kp")
        self.persons_commit(self.hold_lines)  # the Phase is held now, so nothing in it is startable
        self.assertEqual([], ProjectView.load(self.store).startable_works(self.phase_id))
        result = self.entry()
        chain = self.chain(self.store, result.review_run_id)
        material = ReviewStore(self.store).read_candidate_snapshot(chain.generations[0].candidate_hash).material
        first = planning.candidate_content(material)["canonical_first_work"]
        self.assertEqual(first["id"], result.registration.entry_work_id,
                         "the reviewed selection, not a working-tree recomputation")
        self.assertEqual(result.registration.work_ids[first["key"]], result.registration.entry_work_id)


if __name__ == "__main__":
    unittest.main()
