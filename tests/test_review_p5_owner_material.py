"""RB4 / P5 owner material at unit level, over a read-only fake Review reader (no Project, no Git).

* the Run summary disposition a Run's OWN chain makes final (G2 failed, G4 HUMAN_WAIT, G6) and ``consumed``;
* the ``set_aside`` summaries a P5 setter writes: only for P5 predecessors with no final summary that no other
  Run already set aside (P-6) - never for a P4-only Run, never twice;
* the history paths a P5 Run's generations wrote, derived from canonical records only (P-5), none for P4-only;
* the G1 history bindings carry each record's exact digest.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import unittest
from typing import Any

from workline.review import history, p4, paths, records, serialize

RUN = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"
SETTER = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAW"
TASK = "rtk_01ARZ3NDEKTSV4RRFFQ69G5FA1"
CANDIDATE = "a" * 64


@dataclass(frozen=True)
class Chain:
    review_run_id: str
    generations: tuple

    @property
    def latest(self) -> records.GateGeneration:
        return self.generations[-1]


class Reader:
    """Just the reads the owner material makes, over in-memory canonical records."""

    def __init__(self) -> None:
        self.chains: dict[str, Chain] = {}
        self.inputs: dict[str, records.TaskInput] = {}
        self.history: dict[tuple[str, str], Any] = {}

    def gate_chain(self, run_id: str) -> Chain | None:
        return self.chains.get(run_id)

    def read_task_input(self, task_id: str) -> records.TaskInput:
        return self.inputs[task_id]

    def adjudication_exists(self, run_id: str) -> bool:
        return False

    def consumption_by_receipt(self) -> dict:
        return {}

    def history_exists(self, family: str, identifier: str) -> bool:
        return (family, identifier) in self.history

    def read_history(self, family: str, identifier: str) -> Any:
        return self.history[(family, identifier)]


def run_with(reader: Reader, run_id: str, policy: str, *, failed: bool = False, generations: int = 2,
             task: str = TASK) -> Chain:
    envelope = p4.discovery_request(
        review_contract=p4.WORK_CONTRACT, review_kind="work-result-v1", viewpoint="correctness", candidate={"c": 1},
        context={"x": 1}, requirement={"r": 1}, candidate_generation=1, succession=None, set_aside_runs=[],
        human_decision=None, policy_id=policy,
    )
    task_input = p4.task_input(task_id=task, task_slot=p4.discovery_slot("correctness"),
                               task_kind=p4.TASK_KIND_DISCOVERY, actor_identity="d", actor_version="1",
                               envelope=envelope, candidate_hash=CANDIDATE, candidate_material_digest="b" * 64,
                               review_context_hash="c" * 64, accepted_generation=1, policy_id=policy)
    reader.inputs[task] = task_input
    first = records.GateGeneration(
        review_run_id=run_id, generation=1, previous_generation=None, previous_digest=None,
        review_kind="work-result-v1", target_identity="w_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        operation_identity="start:" + "e" * 64, candidate_hash=CANDIDATE, review_context_hash="c" * 64,
        effective_policy_hash=p4.policy_hash(policy), evidence_digest="f" * 64, coverage_digest="f" * 64,
        raw_report_set_digest="f" * 64, adjudication_digest="f" * 64, obligation_digest="f" * 64,
        accepted_tasks=(p4.accepted_descriptor(task_input),), settled_tasks=(), status=records.GATE_STATUS_OPEN,
        receipt_id=None, authorized_operation_stage=None,
    )
    found = [first]
    if generations >= 2:
        settled = {"task_id": task, "status": records.TASK_SETTLED_FAILED if failed else records.TASK_SETTLED_OK,
                   "result_digest": "d" * 64, "settled_generation": 2}
        found.append(replace(first, generation=2, previous_generation=1,
                             previous_digest=serialize.digest(first.to_record()), settled_tasks=(settled,)))
    chain = Chain(run_id, tuple(found))
    reader.chains[run_id] = chain
    return chain


class DispositionTests(unittest.TestCase):
    def test_only_a_failed_g2_is_a_final_disposition_before_g4(self) -> None:
        reader = Reader()
        self.assertEqual(history.DISPOSITION_NOT_AUTHORIZED,
                         p4.own_summary_disposition(reader, run_with(reader, RUN, p4.P5_POLICY_ID, failed=True)))
        self.assertIsNone(p4.own_summary_disposition(reader, run_with(Reader(), RUN, p4.P5_POLICY_ID)))
        self.assertIsNone(p4.final_disposition(reader, run_with(Reader(), RUN, p4.P5_POLICY_ID, generations=1)))


class SetAsideTests(unittest.TestCase):
    def test_a_p5_predecessor_without_a_final_summary_gets_one_set_aside_summary(self) -> None:
        reader = Reader()
        run_with(reader, RUN, p4.P5_POLICY_ID)
        (summary,) = p4.set_aside_summaries(reader, [{"review_run_id": RUN, "reason": "review_context_changed"}])
        self.assertEqual((RUN, history.DISPOSITION_SET_ASIDE, 2),
                         (summary.review_run_id, summary.durable_disposition, summary.gate_generation))
        writes = p4.HistoryWrites((summary,))
        self.assertEqual([{"review_run_id": RUN, "digest": serialize.digest(summary.to_record())}],
                         writes.summary_bindings())
        self.assertEqual([paths.history_run_rel(RUN)], writes.paths())

    def test_no_summary_for_a_p4_only_run_a_final_one_or_a_run_another_request_set_aside(self) -> None:
        for name, policy, failed, reason in (
            ("P4-only", p4.POLICY_ID, False, "review_context_changed"),
            ("final", p4.P5_POLICY_ID, True, "not_authorized"),
            ("named", p4.P5_POLICY_ID, False, "set_aside"),
        ):
            with self.subTest(name):
                reader = Reader()
                run_with(reader, RUN, policy, failed=failed)
                self.assertEqual((), p4.set_aside_summaries(reader, [{"review_run_id": RUN, "reason": reason}]))


class OwnPathTests(unittest.TestCase):
    def test_the_history_a_p5_run_wrote_is_derived_from_its_records_and_a_p4_only_run_wrote_none(self) -> None:
        reader = Reader()
        chain = run_with(reader, RUN, p4.P5_POLICY_ID, failed=True)
        self.assertEqual([paths.history_run_rel(RUN)], p4.run_history_paths(reader, RUN, chain))
        p4_only = Reader()
        self.assertEqual([], p4.run_history_paths(p4_only, RUN, run_with(p4_only, RUN, p4.POLICY_ID, failed=True)))

    def test_generation_one_bindings_name_the_paths_a_setter_wrote(self) -> None:
        envelope = p4.discovery_request(
            review_contract=p4.WORK_CONTRACT, review_kind="work-result-v1", viewpoint="correctness",
            candidate={"c": 1}, context={"x": 1}, requirement={"r": 1}, candidate_generation=1, succession=None,
            set_aside_runs=[], human_decision=None, policy_id=p4.P5_POLICY_ID,
            set_aside_summaries=[{"review_run_id": RUN, "digest": "a" * 64}],
            decision_evidence=[{"review_decision_id": "rhd_01ARZ3NDEKTSV4RRFFQ69G5FAV", "affected_review_run_id": RUN,
                                "digest": "b" * 64}],
        )
        self.assertEqual([paths.history_run_rel(RUN), paths.history_decision_rel("rhd_01ARZ3NDEKTSV4RRFFQ69G5FAV")],
                         p4.first_generation_history_paths(envelope))


if __name__ == "__main__":
    unittest.main()
