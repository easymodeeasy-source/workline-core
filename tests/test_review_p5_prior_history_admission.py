"""RB4 / P5 Formal-review repair: a history record is P5 prior history only if its Run stores the P5 identity.

``p4.prior_history_references`` (GAP-C) admits a same-target Run / Finding / Repair summary only when the
summary's Run is P5 by the policy and history contract that Run itself stores (GAP-A) - never because the history
file exists, has a P5 shape, or validates against its immutable P1-P4 source. A P4-only Run's summary written by
hand validates against that source (as ``test_create_future_work_link`` shows for a Finding) and is still no P5
history: a same-target one makes the P5 prior-history set invalid (``review_p5_history_invalid``, GAP-B) and the
P5 adjudicator is never launched. A record of another review kind or target is no gate; a P4-only current Run binds
no prior history at all, byte for byte as before.

* unit level, over an in-memory reader: every family, P4-only refused, P5 admitted, other targets isolated, and a
  source Run whose stored policy does not read;
* real canonical records of a P4-only planning cycle: a hand-written Finding / Repair / Run summary each validates
  against its source and is refused, and is no gate for another target or kind;
* both owners end to end: a P5 Run of the same target refuses at its adjudication acceptance (G3) and its
  adjudicator is never called. Planning is the real path: phase entry, whose target is the Phase (a Roadmap
  registration reserves a new Roadmap ID each time, so it never shares a target with an earlier one). Work is
  TEST-SEAM coverage (R-5W): today landed Work recovery refuses every later START of a Work a P4-family Run was
  left on (``review_recovery_incomplete``), so the Work owner's G3 is reached only through the test-only
  ``p4_work_requests_named`` seam;
* a P4-only current cycle beside such a record is unchanged.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any
import unittest
from unittest import mock

from p5_helpers import first_envelope, p4_only_cycle
from planning_helpers import design, git
from test_review_p4_planning import Adjudicator, Discovery, P4PlanningCase, Repairer, p4_review, problem
from test_review_p4_work import work_p4
from test_review_p5_owner_material import Chain, Reader, run_with
from test_review_p5_set_aside import _WorkCase, p4_work_requests_named
from workline import roadmap as rm
from workline import roadmap_review as rr
from workline import start as st
from workline.errors import StopError, ValidationError
from workline.review import history, p4, paths, serialize
from workline.review.store import ReviewStore

LOW = p4.P4Claim("LOW", "low", "a minor wording note")
IMPROVE = p4.P4Claim("MID", "improve", "a clearer phase name")
SOURCE = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"
CURRENT = "rr_01ARZ3NDEKTSV4RRFFQ69G5FB0"
OTHER_TARGET = "w_01ARZ3NDEKTSV4RRFFQ69G5FB1"
KIND = "work-result-v1"
TARGET = "w_01ARZ3NDEKTSV4RRFFQ69G5FAV"
FAMILY_IDS = {paths.HISTORY_RUNS: SOURCE, paths.HISTORY_FINDINGS: "rfd_01ARZ3NDEKTSV4RRFFQ69G5FAV",
              paths.HISTORY_REPAIRS: "rrb_01ARZ3NDEKTSV4RRFFQ69G5FAV"}


class HistoryReader(Reader):
    """The owner-material fake reader, plus the history listing and digests the prior-history collection reads."""

    def __init__(self) -> None:
        super().__init__()
        self.digests: dict[tuple[str, str], str] = {}

    def history_ids(self, family: str) -> tuple[str, ...]:
        return tuple(sorted(identifier for found, identifier in self.history if found == family))

    def history_digest(self, family: str, identifier: str) -> str:
        return self.digests[(family, identifier)]

    def record(self, family: str, run_id: str = SOURCE) -> str:
        """One ``family`` summary of ``run_id`` (only the field naming its Run matters here)."""
        identifier = FAMILY_IDS[family] if run_id == SOURCE else run_id
        named = {"source_review_run_id": run_id} if family == paths.HISTORY_REPAIRS else {"review_run_id": run_id}
        self.history[(family, identifier)] = SimpleNamespace(**named)
        self.digests[(family, identifier)] = str(len(self.digests)) * 64
        return identifier


def retarget(reader: HistoryReader, chain: Chain, *, review_kind: str = KIND, target_identity: str = TARGET) -> None:
    first = replace(chain.generations[0], review_kind=review_kind, target_identity=target_identity)
    reader.chains[chain.review_run_id] = Chain(chain.review_run_id, (first,) + chain.generations[1:])


def validating() -> Any:
    """Every summary validates against its immutable source: only the Run's stored identity can still refuse it."""
    return mock.patch.multiple(history, run_summary_problems=lambda reader, summary: [],
                               finding_summary_problems=lambda reader, summary: [],
                               repair_summary_problems=lambda reader, summary: [])


class FamilyAdmissionUnitTests(unittest.TestCase):
    def refused(self, reader: HistoryReader) -> StopError:
        with validating(), self.assertRaises(StopError) as raised:
            p4.prior_history_references(reader, KIND, TARGET, CURRENT)
        self.assertEqual(history.CODE_HISTORY_INVALID, raised.exception.code, raised.exception.message)
        return raised.exception

    def test_no_family_of_a_p4_only_same_target_run_is_p5_prior_history_even_when_it_validates(self) -> None:
        for family in p4.REFERENCE_KINDS:
            with self.subTest(family):
                reader = HistoryReader()
                run_with(reader, SOURCE, p4.POLICY_ID)
                identifier = reader.record(family)
                error = self.refused(reader)
                self.assertIn(identifier, error.message)
                self.assertIn("not a P5 Run", error.message)

    def test_every_family_of_a_p5_same_target_run_is_admitted_at_its_exact_digest(self) -> None:
        reader = HistoryReader()
        run_with(reader, SOURCE, p4.P5_POLICY_ID)
        expected = sorted(({"family": family, "id": reader.record(family),
                            "digest": reader.digests[(family, FAMILY_IDS[family])]} for family in p4.REFERENCE_KINDS),
                          key=lambda item: (item["family"], item["id"]))
        with validating():
            self.assertEqual(expected, p4.prior_history_references(reader, KIND, TARGET, CURRENT))
            self.assertEqual(expected, p4.prior_history_references(reader, KIND, TARGET, CURRENT), "deterministic")

    def test_a_p4_only_run_of_another_target_or_kind_is_no_gate(self) -> None:
        for name, kind, target in (("another target", KIND, OTHER_TARGET), ("another kind", "roadmap-plan-v1", TARGET)):
            for family in p4.REFERENCE_KINDS:
                with self.subTest(name=name, family=family):
                    reader = HistoryReader()
                    retarget(reader, run_with(reader, SOURCE, p4.POLICY_ID), review_kind=kind, target_identity=target)
                    reader.record(family)
                    with validating():
                        self.assertEqual([], p4.prior_history_references(reader, KIND, TARGET, CURRENT))

    def test_a_same_target_run_whose_stored_policy_does_not_read_is_history_invalid(self) -> None:
        def no_tasks(reader: HistoryReader) -> None:
            chain = run_with(reader, SOURCE, p4.P5_POLICY_ID)
            first = replace(chain.generations[0], accepted_tasks=())
            reader.chains[SOURCE] = Chain(SOURCE, (first,) + chain.generations[1:])

        def two_policies(reader: HistoryReader) -> None:
            chain = run_with(reader, SOURCE, p4.P5_POLICY_ID)
            p4_only = HistoryReader()
            other = run_with(p4_only, SOURCE, p4.POLICY_ID, task="rtk_01ARZ3NDEKTSV4RRFFQ69G5FA2")
            reader.inputs.update(p4_only.inputs)
            first = replace(chain.generations[0], accepted_tasks=chain.generations[0].accepted_tasks
                            + other.generations[0].accepted_tasks)
            reader.chains[SOURCE] = Chain(SOURCE, (first,) + chain.generations[1:])

        def unreadable(reader: HistoryReader) -> None:
            run_with(reader, SOURCE, p4.P5_POLICY_ID)

            def read_task_input(task_id: str) -> Any:
                raise ValidationError(f"TaskInput {task_id} does not read", code="review_record_invalid")

            reader.read_task_input = read_task_input  # type: ignore[method-assign]

        for name, build in (("no generation-1 TaskInput", no_tasks), ("two policies in generation 1", two_policies),
                            ("a TaskInput that does not read", unreadable)):
            with self.subTest(name):
                reader = HistoryReader()
                build(reader)
                reader.record(paths.HISTORY_FINDINGS)
                error = self.refused(reader)
                self.assertIn("stored policy does not read", error.message)


class P4OnlySourceRecordTests(P4PlanningCase):
    """Real canonical records of a P4-only planning cycle, and the collection path over them."""

    def test_a_hand_written_summary_of_a_p4_only_run_validates_and_is_still_never_p5_prior_history(self) -> None:
        store = self.planning_project()
        with p4_only_cycle():
            result = self.reviewed_p4(store, p4_review(Discovery((problem(),), (IMPROVE,)), repairer=Repairer()))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        review = ReviewStore(store)
        (source,) = [run for run in review.run_ids() if run != result.review_run_id]
        chain = review.gate_chain(source)
        kind, target = chain.generations[0].review_kind, chain.generations[0].target_identity
        self.assertEqual(p4.POLICY_ID, first_envelope(review, source)["policy_id"])
        self.assertFalse((store.root / paths.HISTORY_DIR).exists(), "a P4-only cycle writes no history")
        self.assertEqual([], p4.prior_history_references(review, kind, target, CURRENT))
        adjudication = review.read_adjudication(source)
        (finding,) = adjudication.findings
        finding_id = str(finding["finding_id"])
        (batch_id,) = review.repair_batch_ids()
        repaired = dict(p4.g6_history(
            adjudication, review.read_repair_batch(batch_id), review.read_repair_result(batch_id), chain.latest,
            source_candidate_material_digest=review.candidate_material_digest(chain.latest.candidate_hash),
        ))
        forged = {
            paths.HISTORY_FINDINGS: (finding_id, history.finding_summary(adjudication, finding_id).to_record(),
                                     history.finding_summary_problems),
            paths.HISTORY_REPAIRS: (batch_id, repaired[paths.history_repair_rel(batch_id)],
                                    history.repair_summary_problems),
            paths.HISTORY_RUNS: (source, repaired[paths.history_run_rel(source)], history.run_summary_problems),
        }
        self.assertEqual(set(p4.REFERENCE_KINDS), set(forged))
        for family, (identifier, record, checker) in forged.items():
            with self.subTest(family):
                rel = paths.history_rel(family, identifier)
                (store.root / rel).parent.mkdir(parents=True, exist_ok=True)
                (store.root / rel).write_bytes(serialize.canonical_text(record).encode("utf-8"))
                review = ReviewStore(store)
                self.assertEqual([], checker(review, review.read_history(family, identifier)),
                                 "it agrees with its immutable source; only the Run's stored identity says not P5")
                with self.assertRaises(StopError) as refused:
                    p4.prior_history_references(review, kind, target, CURRENT)
                self.assertEqual(history.CODE_HISTORY_INVALID, refused.exception.code, refused.exception.message)
                self.assertIn("not a P5 Run", refused.exception.message)
                self.assertIn(identifier, refused.exception.message)
                # no gate for another target or review kind
                self.assertEqual([], p4.prior_history_references(review, kind, OTHER_TARGET, CURRENT))
                self.assertEqual([], p4.prior_history_references(review, "other-kind-v1", target, CURRENT))
                (store.root / rel).unlink()


class PlanningOwnerTests(P4PlanningCase):
    """Phase entry, whose target is the Phase: a later entry of a Phase after a P4-only entry of it declined is a
    fresh first Run - P5 by default (GAP-A item 7) - of the same review kind and target."""

    def p4_only_entry_with_a_hand_written_summary(self, store: Any) -> tuple[str, str]:
        """A P4-only entry Run whose discovery declined (``not_authorized``), and its summary written by hand."""
        _, phase = self.roadmap_and_phase(store)
        with p4_only_cycle():
            declined = rm.enter_phase(store, phase, design(), review=p4_review(Discovery(status="declined")))
        self.assertEqual(rr.STATUS_NOT_AUTHORIZED, declined.status, declined.detail)
        final = str(declined.review_run_id)
        review = ReviewStore(store)
        envelope = first_envelope(review, final)
        self.assertEqual(p4.POLICY_ID, envelope["policy_id"])
        self.assertFalse((store.root / paths.HISTORY_DIR).exists(), "a P4-only Run writes no history")
        ((rel, record),) = p4.not_authorized_history(review.gate_chain(final).latest,
                                                     int(envelope["candidate_generation"]))
        (store.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (store.root / rel).write_bytes(serialize.canonical_text(record).encode("utf-8"))
        self.commit_all(store, "a hand-written summary", rel)
        review = ReviewStore(store)
        self.assertEqual([], history.run_summary_problems(review, review.read_history(paths.HISTORY_RUNS, final)),
                         "it agrees with its immutable source")
        return phase, final

    def test_a_p5_entry_of_the_same_phase_refuses_before_its_adjudicator_is_launched(self) -> None:
        store = self.planning_project()
        phase, final = self.p4_only_entry_with_a_hand_written_summary(store)
        adjudicator = Adjudicator()
        with self.assertRaises(StopError) as refused:
            rm.enter_phase(store, phase, design(), review=p4_review(Discovery((LOW,)), adjudicator=adjudicator))
        self.assertEqual(history.CODE_HISTORY_INVALID, refused.exception.code, refused.exception.message)
        self.assertIn(final, refused.exception.message)
        self.assertIn("not a P5 Run", refused.exception.message)
        self.assertEqual([], adjudicator.tasks, "the adjudicator is never launched")
        (run,) = [found for found in self.runs(store) if found != final]
        review = ReviewStore(store)
        chain = review.gate_chain(run)
        self.assertEqual((p4.P5_POLICY_ID, phase), (first_envelope(review, run)["policy_id"],
                                                     chain.generations[0].target_identity), "a P5 Run of the same Phase")
        self.assertEqual(phase, review.gate_chain(final).generations[0].target_identity)
        self.assertEqual(2, len(chain.generations), "no adjudication task is accepted: no G3")
        self.assertIsNone(p4.adjudication_task(chain))

    def test_a_p4_only_entry_of_the_same_phase_is_unchanged_beside_that_record(self) -> None:
        store = self.planning_project()
        phase, final = self.p4_only_entry_with_a_hand_written_summary(store)
        adjudicator = Adjudicator()
        with p4_only_cycle():
            result = rm.enter_phase(store, phase, design(), review=p4_review(Discovery((LOW,)), adjudicator=adjudicator))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        (task,) = adjudicator.tasks
        self.assertEqual((), task.prior_history)
        self.assertEqual(p4.POLICY_ID, task.request_envelope["policy_id"])
        self.assertNotIn("prior_history", task.request_envelope, "a P4-only request is byte for byte the pre-P5 one")
        self.assertNotIn(history.HISTORY_CONTRACT_KEY, task.request_envelope)
        self.assertEqual((final,), ReviewStore(store).history_ids(paths.HISTORY_RUNS),
                         "it writes no history; only the hand-written record is there")


class WorkOwnerSeamTests(_WorkCase):
    """TEST-SEAM coverage (R-5W): the Work owner's G3 for a later START of a Work a P4-only Run was left on."""

    def test_seam_a_p5_work_run_of_the_same_work_refuses_before_its_adjudicator_is_launched(self) -> None:
        with p4_work_requests_named():
            with p4_only_cycle(), self.assertRaises(StopError):
                st.start(self.store, self.work_id, "single-work", self.executor,
                         review=work_p4(Discovery(status="declined")))
            final = self.lose_start()
            review = ReviewStore(self.store)
            envelope = first_envelope(review, final)
            self.assertEqual(p4.POLICY_ID, envelope["policy_id"])
            self.assertFalse((self.root / paths.HISTORY_DIR).exists(), "a P4-only Run writes no history")
            ((rel, record),) = p4.not_authorized_history(review.gate_chain(final).latest,
                                                         int(envelope["candidate_generation"]))
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_bytes(serialize.canonical_text(record).encode("utf-8"))
            git(self.root, "add", rel)
            git(self.root, "commit", "-q", "-m", "a hand-written summary")
            git(self.root, "push", "-q", "origin", "main")
            review = ReviewStore(self.store)
            self.assertEqual([], history.run_summary_problems(review, review.read_history(paths.HISTORY_RUNS, final)),
                             "it agrees with its immutable source")
            adjudicator = Adjudicator()
            with self.assertRaises(StopError) as refused:
                st.start(self.store, self.work_id, "single-work", self.executor,
                         review=work_p4(Discovery((LOW,)), adjudicator=adjudicator))
        self.assertEqual(history.CODE_HISTORY_INVALID, refused.exception.code, refused.exception.message)
        self.assertIn(final, refused.exception.message)
        self.assertIn("not a P5 Run", refused.exception.message)
        self.assertEqual([], adjudicator.tasks, "the adjudicator is never launched")
        (run,) = [found for found in self.runs() if found != final]
        review = ReviewStore(self.store)
        chain = review.gate_chain(run)
        self.assertEqual(p4.P5_POLICY_ID, first_envelope(review, run)["policy_id"])
        self.assertEqual(self.work_id, chain.generations[0].target_identity)
        self.assertEqual(2, len(chain.generations), "no adjudication task is accepted: no G3")
        self.assertIsNone(p4.adjudication_task(chain))


if __name__ == "__main__":
    unittest.main()
