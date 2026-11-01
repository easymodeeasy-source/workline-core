"""RB4 / P5 §28.14 / §28.18 / §28.30, GAP-G: Human Decision Evidence of a P5 cycle resumed under a Human decision.

A fresh cycle is P5 (GAP-A option 3), and a P5 cycle resumed under a Human decision needs the separate explicit
evidence input (§28.14 lines 9101-9106; §28.18 line 9210). Planning and Work alike:

* WITHOUT evidence: ``review_p5_history_missing`` before ANY effect - no Run, TaskInput, generation, snapshot or
  reservation is created, and the waiting Run is untouched;
* WITH valid evidence: one Human Decision Evidence record per affected Run, in the successor's G1, committed before
  the successor's discovery actor is launched; the waiting Run is set aside as ``human_decision``;
* a mismatched or detached affected Run: ``review_p5_decision_evidence_invalid`` before any effect;
* planning ``requirement_changed`` across the operation-identity boundary (GAP-G): the evidence names the old Run
  explicitly, the new G1 sets it aside, and the authority must reflect the change (else
  ``review_p5_authority_mismatch``); ``requirement_confirmed`` may leave the authority unchanged;
* Work: ``affected_review_run_id`` must be exactly the P4-R7 waiting Run.
"""

from __future__ import annotations

from typing import Any
from unittest import mock

from p5_helpers import at_head, decision_evidence, first_envelope, p5_only_cycle
from planning_helpers import plan
from test_review_p4_planning import Discovery, P4PlanningCase, p4_review
from test_review_p4_work import P4WorkCase
from test_work_review_runtime import git
from workline import roadmap as rm
from workline import roadmap_review as rr
from workline import start as st
from workline import start_review as sr
from workline.errors import ReconcileRequired, StopError
from workline.review import history, p4, paths, planning, serialize, work_context, work_review
from workline.review.store import ReviewStore

HUMAN = p4.P4Claim("HIGH", "human", "which scope?")
CONFIRMED = p4.HumanDecision("hd-1", p4.DECISION_CONFIRMED)
CHANGED = p4.HumanDecision("hd-2", p4.DECISION_CHANGED)



#: R6-1 (TEST-ONLY seam, tests/p5_helpers.p5_only_cycle): production binds the P6-capable default to every NEW first
#: Run; this module keeps testing P5 Runs exactly as pre-P6 code wrote them.
_P5_SEAM = p5_only_cycle()


def setUpModule() -> None:
    _P5_SEAM.__enter__()


def tearDownModule() -> None:
    _P5_SEAM.__exit__(None, None, None)

class LaunchWitness(Discovery):
    """A discovery actor that records, at its launch, whether the given history paths are already committed."""

    def __init__(self, store: Any, *script: Any) -> None:
        super().__init__(*script)
        self.store = store
        self.committed_at_launch: list[dict[str, bool]] = []

    def __call__(self, task: Any) -> p4.P4DiscoveryReport:
        wanted = p4.first_generation_history_paths(task.request_envelope)
        self.committed_at_launch.append({path: at_head(self.store.root, path) for path in wanted})
        return super().__call__(task)


def roadmap_requirement(the_plan: rm.RoadmapPlan) -> dict[str, Any]:
    digest = planning.request_digest(planning.OPERATION_ROADMAP, rm.roadmap_request_identity(the_plan))
    return planning.requirement_authority(planning.OPERATION_ROADMAP, digest, None, None)


def review_with(decision: p4.HumanDecision, evidence: tuple, discovery: Any = None) -> planning.PlanningReviewP4:
    base = p4_review(discovery, decision=decision)
    return planning.PlanningReviewP4(base.discovery, base.adjudicator, base.repair, decision,
                                     decision_evidence=evidence)


class PlanningHumanDecisionTests(P4PlanningCase):
    def wait(self, store: Any, the_plan: rm.RoadmapPlan | None = None) -> str:
        result = self.reviewed_p4(store, p4_review(Discovery((HUMAN,))), the_plan)
        self.assertEqual(rr.STATUS_HUMAN_WAIT, result.status, result.detail)
        waiting = str(result.review_run_id)
        summary = ReviewStore(store).read_history(paths.HISTORY_RUNS, waiting)
        self.assertEqual(history.DISPOSITION_HUMAN_WAIT, summary.durable_disposition, "HUMAN_WAIT summary at G4")
        return waiting

    def test_a_p5_wait_resumed_without_evidence_stops_before_any_effect(self) -> None:
        store = self.planning_project()
        waiting = self.wait(store)
        before = self.snapshot_state(store)
        head = self.head(store)
        with self.assertRaises(StopError) as raised:
            self.reviewed_p4(store, p4_review(decision=CONFIRMED))
        self.assertEqual(history.CODE_HISTORY_MISSING, raised.exception.code, raised.exception)
        self.assertEqual([waiting], self.runs(store), "no Run is created")
        self.assertEqual([], self.pending(store), "no owner mutation, so no reservation, is left")
        self.assertEqual(head, self.head(store))
        after = {path: data for path, data in self.snapshot_state(store).items() if "/runtime/" not in path}
        self.assertEqual({path: data for path, data in before.items() if "/runtime/" not in path}, after,
                         "no TaskInput, generation, snapshot or history record is written")

    def test_a_confirmed_decision_with_evidence_persists_it_in_the_successor_g1_before_launch(self) -> None:
        store = self.planning_project()
        the_plan = plan()
        waiting = self.wait(store, the_plan)
        review = ReviewStore(store)
        evidence = decision_evidence(review, waiting, CONFIRMED, roadmap_requirement(the_plan))
        witness = LaunchWitness(store)
        result = self.reviewed_p4(store, review_with(CONFIRMED, (evidence,), witness), the_plan)
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        envelope = first_envelope(review, str(result.review_run_id))
        self.assertIn({"review_run_id": waiting, "reason": p4.SET_ASIDE_HUMAN_DECISION}, envelope["set_aside_runs"])
        (bound,) = envelope["decision_evidence"]
        self.assertEqual(waiting, bound["affected_review_run_id"])
        record = review.read_history(paths.HISTORY_HUMAN_DECISIONS, bound["review_decision_id"])
        self.assertEqual((waiting, CONFIRMED.decision_id, history.ACTION_RESUME_CONFIRMED),
                         (record.affected_review_run_id, record.decision_id, record.action_class))
        self.assertEqual(bound["digest"], serialize.digest(record.to_record()))
        self.assertEqual([{paths.history_decision_rel(bound["review_decision_id"]): True}],
                         witness.committed_at_launch, "committed before the successor's external launch")
        self.assertEqual(4, len(review.gate_chain(waiting).generations), "the waiting Run is never rewritten")
        self.assertEqual([], history.history_problems(review, work_ids=None))

    def test_requirement_changed_crosses_the_operation_identity_boundary_explicitly(self) -> None:
        store = self.planning_project()
        old_plan = plan()
        waiting = self.wait(store, old_plan)
        new_plan = plan(scope="the changed scope")
        review = ReviewStore(store)
        evidence = decision_evidence(review, waiting, CHANGED, roadmap_requirement(new_plan))
        result = self.reviewed_p4(store, review_with(CHANGED, (evidence,)), new_plan)
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        new_first = review.gate_chain(str(result.review_run_id)).generations[0]
        old_first = review.gate_chain(waiting).generations[0]
        self.assertNotEqual(old_first.operation_identity, new_first.operation_identity, "identities are not merged")
        envelope = first_envelope(review, str(result.review_run_id))
        self.assertIn({"review_run_id": waiting, "reason": p4.SET_ASIDE_HUMAN_DECISION}, envelope["set_aside_runs"])
        (bound,) = envelope["decision_evidence"]
        record = review.read_history(paths.HISTORY_HUMAN_DECISIONS, bound["review_decision_id"])
        self.assertEqual((serialize.digest(roadmap_requirement(new_plan)),), record.effect_digests)
        self.assertEqual(p4.P5_POLICY_ID, envelope["policy_id"], "the cycle keeps its first Run's family")
        self.assertEqual([], history.history_problems(review, work_ids=None))

    def test_requirement_changed_with_the_authority_unchanged_is_an_authority_mismatch(self) -> None:
        store = self.planning_project()
        the_plan = plan()
        waiting = self.wait(store, the_plan)
        evidence = decision_evidence(ReviewStore(store), waiting, CHANGED, roadmap_requirement(the_plan))
        with self.assertRaises(StopError) as raised:
            self.reviewed_p4(store, review_with(CHANGED, (evidence,)), the_plan)
        self.assertEqual(history.CODE_AUTHORITY_MISMATCH, raised.exception.code, raised.exception)
        self.assertEqual([waiting], self.runs(store))
        self.assertEqual([], self.pending(store))

    def test_evidence_for_a_run_that_is_no_human_wait_is_refused_before_any_effect(self) -> None:
        store = self.planning_project()
        the_plan = plan()
        waiting = self.wait(store, the_plan)
        review = ReviewStore(store)
        good = decision_evidence(review, waiting, CONFIRMED, roadmap_requirement(the_plan))
        for name, bad in (
            ("detached", p4.DecisionEvidence(**{**good.__dict__, "affected_review_run_id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"})),
            ("candidate", p4.DecisionEvidence(**{**good.__dict__, "affected_candidate_hash": "f" * 64})),
        ):
            with self.subTest(name), self.assertRaises(StopError) as raised:
                self.reviewed_p4(store, review_with(CONFIRMED, (bad,)), the_plan)
            self.assertEqual(history.CODE_DECISION_EVIDENCE_INVALID, raised.exception.code, raised.exception)
            self.assertEqual([waiting], self.runs(store))
            self.assertEqual([], self.pending(store))


def work_review_with(decision: p4.HumanDecision | None, evidence: tuple = (), discovery: Any = None) -> Any:
    from test_review_p4_work import work_p4

    base = work_p4(discovery or Discovery((HUMAN,)), decision=decision)
    return work_review.WorkReviewP4(base.discovery, base.adjudicator, base.repair, decision, decision_evidence=evidence)


class WorkHumanDecisionTests(P4WorkCase):
    def setUp(self) -> None:
        super().setUp()
        self.executor = self.completing(write={"out.txt": b"out\n"}, message="feat: out")

    def wait(self) -> str:
        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", self.executor, review=work_review_with(None))
        self.assertEqual(p4.CODE_HUMAN_WAIT, raised.exception.code)
        (waiting,) = self.runs()
        self.assertEqual(history.DISPOSITION_HUMAN_WAIT,
                         ReviewStore(self.store).read_history(paths.HISTORY_RUNS, waiting).durable_disposition)
        return waiting

    def requirement(self) -> dict[str, Any]:
        from workline.state import ProjectView

        return work_review.requirement_authority(self.work_id, ProjectView.load(self.store).works[self.work_id].body)

    def test_a_p5_work_wait_resumed_without_evidence_stops_before_any_reservation(self) -> None:
        waiting = self.wait()
        reserved = dict(self.start_record().get("reserved_ids") or {})
        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", self.executor, review=work_review_with(CONFIRMED))
        self.assertEqual(history.CODE_HISTORY_MISSING, raised.exception.code, raised.exception)
        record = self.start_record()
        self.assertEqual(reserved, dict(record.get("reserved_ids") or {}), "no successor or decision reservation")
        self.assertNotIn("p4_human_decisions", record.get("notes") or {}, "the decision is not even bound")
        self.assertEqual([waiting], self.runs())

    def test_the_evidence_of_the_p4_r7_waiting_run_is_persisted_in_the_successor_g1(self) -> None:
        waiting = self.wait()
        evidence = decision_evidence(ReviewStore(self.store), waiting, CONFIRMED, self.requirement())
        witness = LaunchWitness(self.store)
        result, record = self.complete(self.executor, review=work_review_with(CONFIRMED, (evidence,), witness))
        review = ReviewStore(self.store)
        consumption = self.consumption(self.head(), record)
        envelope = first_envelope(review, consumption.review_run_id)
        self.assertEqual([{"review_run_id": waiting, "reason": p4.SET_ASIDE_HUMAN_DECISION}], envelope["set_aside_runs"])
        (bound,) = envelope["decision_evidence"]
        self.assertEqual(waiting, bound["affected_review_run_id"], "exactly the P4-R7 waiting Run")
        self.assertTrue(all(all(found.values()) for found in witness.committed_at_launch))
        self.assertEqual([], history.history_problems(review, work_ids=None))

    def amend(self, *rels: str, message: str = "correct the requirement") -> None:
        """One commit appending a section to each of ``rels`` (the Work's body by default), as a Human decision needs."""
        for rel in rels or (self.work_rel(),):
            (self.root / rel).write_bytes((self.root / rel).read_bytes() + b"\n## Corrected\nThe evidence is a comparison.\n")
        git(self.root, "add", "--", *(rels or (self.work_rel(),)))
        git(self.root, "commit", "-q", "-m", message)

    def work_rel(self) -> str:
        return f".workline/works/{self.work_id}.md"

    def phase_rel(self) -> str:
        from workline.state import ProjectView

        return f".workline/phases/{ProjectView.load(self.store).works[self.work_id].phase_id}.md"

    def changed_review(self, waiting: str) -> Any:
        evidence = decision_evidence(ReviewStore(self.store), waiting, CHANGED, self.requirement())
        return work_review_with(CHANGED, (evidence,), Discovery())

    def assert_refused_by_the_lineage(self, review: Any) -> None:
        before = self.head()
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work", self.executor, review=review)
        self.assertIn("L-2", str(raised.exception))
        self.assertEqual("", git(self.root, "log", "--format=%H", "--", "out.txt"), "no K1")
        self.assertTrue(before)

    def test_a_requirement_changed_by_a_human_on_an_appended_work_body_completes(self) -> None:
        waiting = self.wait()
        self.amend()
        result, record = self.complete(self.executor, review=self.changed_review(waiting))
        self.assertEqual("completed", result.status)
        review = ReviewStore(self.store)
        (bound,) = first_envelope(review, self.consumption(self.head(), record).review_run_id)["decision_evidence"]
        self.assertEqual(waiting, bound["affected_review_run_id"])
        self.assertEqual([], history.history_problems(review, work_ids=None))
        self.assertEqual([], self.problems())

    def test_the_phase_body_may_be_appended_in_the_same_commit(self) -> None:
        waiting = self.wait()
        self.amend(self.work_rel(), self.phase_rel())
        result, _ = self.complete(self.executor, review=self.changed_review(waiting))
        self.assertEqual("completed", result.status)

    def test_an_amendment_that_also_touches_another_file_is_foreign(self) -> None:
        waiting = self.wait()
        (self.root / "person.txt").write_bytes(b"theirs\n")
        git(self.root, "add", "--", "person.txt")
        self.amend()
        git(self.root, "reset", "-q", "--soft", "HEAD~1")
        git(self.root, "commit", "-q", "-m", "the requirement and something else")
        self.assert_refused_by_the_lineage(self.changed_review(waiting))

    def test_an_amendment_of_the_phase_alone_is_foreign(self) -> None:
        waiting = self.wait()
        self.amend()
        self.amend(self.phase_rel(), message="the phase alone")
        self.assert_refused_by_the_lineage(self.changed_review(waiting))

    def test_a_rewritten_work_body_is_foreign_even_with_its_digest_as_the_effect(self) -> None:
        waiting = self.wait()
        path = self.root / self.work_rel()
        path.write_bytes(path.read_bytes().replace(b"\n#", b"\n\n#", 1))
        git(self.root, "add", "--", self.work_rel())
        git(self.root, "commit", "-q", "-m", "a rewrite")
        self.assert_refused_by_the_lineage(self.changed_review(waiting))

    def test_an_appended_body_no_evidence_names_is_foreign(self) -> None:
        waiting = self.wait()
        self.amend()
        review = self.changed_review(waiting)
        self.amend(message="a second, undecided correction")
        with self.assertRaises(StopError):
            st.start(self.store, self.work_id, "single-work", self.executor, review=review)
        self.assertEqual("", git(self.root, "log", "--format=%H", "--", "out.txt"), "no K1")

    def test_a_correction_after_the_seal_is_foreign(self) -> None:
        waiting = self.wait()
        self.amend()
        real = sr._p4_seal

        def seal(*args: Any, **kwargs: Any) -> None:
            real(*args, **kwargs)
            self.amend(message="after the seal")

        with mock.patch.object(sr, "_p4_seal", side_effect=seal):
            self.assert_refused_by_the_lineage(self.changed_review(waiting))

    def test_a_confirmed_requirement_is_no_amendment(self) -> None:
        waiting = self.wait()
        self.amend()
        evidence = decision_evidence(ReviewStore(self.store), waiting, CONFIRMED, self.requirement(), effect=True)
        self.assert_refused_by_the_lineage(work_review_with(CONFIRMED, (evidence,), Discovery()))

    def sealed_then_another_workline(self) -> tuple[str, Any]:
        """A START stopped right after its seal, and a patcher making the implementation identity another one."""
        real = sr._p4_seal

        class Interrupted(BaseException):
            pass

        def seal(*args: Any, **kwargs: Any) -> None:
            real(*args, **kwargs)
            raise Interrupted()

        with mock.patch.object(sr, "_p4_seal", side_effect=seal), self.assertRaises(Interrupted):
            st.start(self.store, self.work_id, "single-work", self.executor, review=work_review_with(None, (), Discovery()))
        (first,) = self.runs()
        return first, mock.patch.object(work_context, "loader_identity", return_value="f" * 64)

    def test_a_seal_gone_stale_before_k1_is_invalidated_and_reviewed_again_under_the_running_workline(self) -> None:
        first, another = self.sealed_then_another_workline()
        receipt = ReviewStore(self.store).gate_chain(first).latest.receipt_id
        head = self.head()
        self.assertEqual("", git(self.root, "log", "--format=%H", "--", "out.txt"))
        with another:
            result, record = self.complete(self.executor, review=work_review_with(None, (), Discovery()))
        self.assertEqual("completed", result.status)
        review = ReviewStore(self.store)
        self.assertEqual(p4.INVALIDATION_GENERATION, review.gate_chain(first).latest.generation)
        self.assertTrue(review.supersession_exists(str(receipt)))
        consumption = self.consumption(self.head(), record)
        self.assertNotEqual(first, consumption.review_run_id)
        envelope = first_envelope(review, consumption.review_run_id)
        self.assertEqual([{"review_run_id": first, "reason": p4.SET_ASIDE_INVALIDATED}], envelope["set_aside_runs"])
        self.assertEqual(history.DISPOSITION_INVALIDATED, review.read_history(paths.HISTORY_RUNS, first).durable_disposition)
        # the invalidation precedes K1: nothing of the result exists under the stale authorization
        k1 = git(self.root, "log", "--format=%H", "--", "out.txt")
        self.assertIn(paths.gate_rel(first, p4.INVALIDATION_GENERATION),
                      git(self.root, "log", "--name-only", "--format=", f"{head}..{k1}"))
        self.assertEqual([], history.history_problems(review, work_ids=None))
        with another:
            self.assertEqual([], self.problems())

    def test_a_seal_still_current_is_not_invalidated(self) -> None:
        first, _ = self.sealed_then_another_workline()
        result, record = self.complete(self.executor, review=work_review_with(None, (), Discovery()))
        self.assertEqual("completed", result.status)
        self.assertEqual(first, self.consumption(self.head(), record).review_run_id)
        self.assertEqual([first], self.runs())

    def test_the_requirement_amendment_survives_a_workline_update_in_the_same_cycle(self) -> None:
        waiting = self.wait()
        self.amend()
        real = sr._p4_seal

        class Interrupted(BaseException):
            pass

        def seal(*args: Any, **kwargs: Any) -> None:
            real(*args, **kwargs)
            raise Interrupted()

        changed = self.changed_review(waiting)
        with mock.patch.object(sr, "_p4_seal", side_effect=seal), self.assertRaises(Interrupted):
            st.start(self.store, self.work_id, "single-work", self.executor, review=changed)
        with mock.patch.object(work_context, "loader_identity", return_value="f" * 64):
            result, _ = self.complete(self.executor, review=work_review_with(None, (), Discovery()))
        self.assertEqual("completed", result.status)
        self.assertEqual(3, len(self.runs()))

    def test_evidence_naming_another_run_than_the_waiting_one_is_refused_before_any_effect(self) -> None:
        waiting = self.wait()
        good = decision_evidence(ReviewStore(self.store), waiting, CONFIRMED, self.requirement())
        bad = p4.DecisionEvidence(**{**good.__dict__, "affected_review_run_id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"})
        reserved = dict(self.start_record().get("reserved_ids") or {})
        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", self.executor, review=work_review_with(CONFIRMED, (bad,)))
        self.assertEqual(history.CODE_DECISION_EVIDENCE_INVALID, raised.exception.code, raised.exception)
        self.assertEqual(reserved, dict(self.start_record().get("reserved_ids") or {}))
        self.assertEqual([waiting], self.runs())
