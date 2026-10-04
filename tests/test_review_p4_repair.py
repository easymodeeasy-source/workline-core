"""P4 §27.32 / G-2 at unit level: the Repair Result <-> Candidate N+1 <-> successor linkage, and positive
set-aside-by-successor proof (five conditions; anything short of them is no proof, never a heuristic).

The end-to-end repair flows (one batch per generation, persisted before launch, N+1 complete, successor key
reused, set-aside recorded) are in ``test_review_p4_planning`` / ``test_review_p4_work``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any
import unittest

from workline.errors import ValidationError
from workline.review import p4, records, serialize

from test_review_p4_adjudication import adjudicate, bound, disposition, report, returned, TASK_A
from test_review_p4_dispatch import (
    ADJUDICATION, DISCOVERY, G1, G2, G3, G4, G5_REPAIR, G6_SETTLE, REPAIR, RUN, Chain,
)
from test_review_p4_evidence import coverage

SUCCESSOR = "rr_01ARZ3NDEKTSV4RRFFQ69G5FB2"
OTHER = "rr_01ARZ3NDEKTSV4RRFFQ69G5FB3"
BATCH = "rrb_01ARZ3NDEKTSV4RRFFQ69G5FAB"
N1 = "b" * 64


def task_input(descriptor: dict, envelope: dict) -> records.TaskInput:
    return p4.task_input(task_id=descriptor["task_id"], task_slot=descriptor["task_slot"],
                         task_kind=descriptor["task_kind"], actor_identity="a", actor_version="1", envelope=envelope,
                         candidate_hash=descriptor["candidate_hash"], candidate_material_digest="b" * 64,
                         review_context_hash="e" * 64, accepted_generation=1)


def discovery_envelope(generation: int, succession: dict | None, set_aside: list[dict]) -> dict:
    return p4.discovery_request(
        review_contract=p4.WORK_CONTRACT, review_kind="work-result-v1", viewpoint="correctness", candidate={"c": 1},
        context={"x": 1}, requirement={"r": 1}, candidate_generation=generation, succession=succession,
        set_aside_runs=set_aside, human_decision=None,
    )


@dataclass
class Reader:
    """A read-only Review reader double: what the proof is allowed to read, and nothing it may write."""

    chains: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, records.TaskInput] = field(default_factory=dict)
    batches: dict[str, records.P4RepairBatch] = field(default_factory=dict)
    results: dict[str, records.P4RepairResult] = field(default_factory=dict)
    snapshots: set[str] = field(default_factory=set)
    consumed_runs: list[str] = field(default_factory=list)

    def run_ids(self):
        return tuple(sorted(self.chains))

    def gate_chain(self, run_id):
        return self.chains.get(run_id)

    def read_task_input(self, task_id):
        if task_id not in self.inputs:
            raise ValidationError(f"no task input {task_id}", code="review_record_missing")
        return self.inputs[task_id]

    def read_repair_batch(self, batch_id):
        return self.batches[batch_id]

    def read_repair_result(self, batch_id):
        return self.results[batch_id]

    def repair_result_digest(self, batch_id):
        return serialize.digest(self.results[batch_id].to_record())

    def candidate_snapshot_exists(self, candidate_hash):
        return candidate_hash in self.snapshots

    def consumptions(self):
        return [type("C", (), {"review_run_id": run})() for run in self.consumed_runs]


def world(*, successors: tuple[str, ...] = (SUCCESSOR,), set_aside_reason: str = p4.SET_ASIDE_REPAIRED,
          digest_override: str | None = None) -> Reader:
    found = adjudicate(bound(report(TASK_A, "correctness", [("HIGH", "x", "broken")])),
                       returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="HIGH")))
    batch = p4.repair_batch(found, "9" * 64, repair_batch_id=BATCH, allowed_result_surface=["out.txt"])
    batch = replace(batch, source_review_run_id=RUN, source_candidate_hash="a" * 64, target_identity="w_x",
                    review_kind="work-result-v1", operation_identity="start:" + "1" * 64)
    result = records.P4RepairResult(
        repair_batch_id=BATCH, review_kind="work-result-v1", target_identity="w_x",
        operation_identity="start:" + "1" * 64, review_contract=p4.WORK_CONTRACT, source_review_run_id=RUN,
        source_candidate_hash="a" * 64, source_candidate_generation=1, result_candidate_hash=N1,
        result_candidate_generation=2, result_candidate_material_digest="c" * 64,
        repair_task_id=REPAIR["task_id"], repair_identity="r", repair_version="1", repaired_surface=("out.txt",),
        impact_class=p4.IMPACT_LOCAL, coverage_check=coverage().to_record(), coverage_check_digest="0" * 64,
        evidence_decisions=(), reverification={"required": [], "completed": [], "residual": 0},
        reverification_digest="0" * 64, causal_summary="fixed", successor_eligible=True,
    )
    digest = digest_override or serialize.digest(result.to_record())
    six = replace(G6_SETTLE, settled_tasks=G6_SETTLE.settled_tasks[:2] + ({**G6_SETTLE.settled_tasks[2], "result_digest": digest},))
    reader = Reader()
    reader.chains[RUN] = Chain((G1, G2, G3, G4, G5_REPAIR, six))
    first = discovery_envelope(1, None, [])
    reader.inputs[DISCOVERY["task_id"]] = task_input(DISCOVERY, first)
    reader.inputs[ADJUDICATION["task_id"]] = replace(task_input(ADJUDICATION, p4.adjudication_request(
        review_contract=p4.WORK_CONTRACT, review_kind="work-result-v1", review_run_id=RUN, candidate_hash="a" * 64,
        candidate_generation=1, review_context_hash="e" * 64, requirement={"r": 1}, reports=[], prior=p4.NO_PRIOR,
        evidence_ids=[])), accepted_generation=3)
    reader.inputs[REPAIR["task_id"]] = replace(task_input(REPAIR, p4.repair_request(
        review_contract=p4.WORK_CONTRACT, review_kind="work-result-v1", review_run_id=RUN, candidate_hash="a" * 64,
        candidate_generation=1, requirement={"r": 1}, repair_batch_id=BATCH, repair_batch_digest="9" * 64,
        allowed_result_surface=["out.txt"], strategy="ordinary", evidence_constraints=[])), accepted_generation=5)
    reader.batches[BATCH] = batch
    reader.results[BATCH] = result
    reader.snapshots.add(N1)
    succession = p4.succession_record(RUN, "a" * 64, BATCH, serialize.digest(result.to_record()))
    for index, run_id in enumerate(successors):
        task = dict(DISCOVERY, task_id=f"rtk_01ARZ3NDEKTSV4RRFFQ69G5FC{index}", candidate_hash=N1)
        reader.chains[run_id] = Chain((replace(G1, review_run_id=run_id, candidate_hash=N1, accepted_tasks=(task,)),))
        reader.inputs[task["task_id"]] = task_input(task, discovery_envelope(
            2, succession, [{"review_run_id": RUN, "reason": set_aside_reason}]))
    return reader


class ProvenSuccessorTests(unittest.TestCase):
    def test_all_five_conditions_prove_the_one_successor(self) -> None:
        reader = world()
        self.assertEqual(SUCCESSOR, p4.proven_successor(reader, RUN, reader.chains[RUN]))
        self.assertTrue(p4.named_by_successor(reader, RUN))

    def test_no_successor_is_no_proof(self) -> None:
        reader = world(successors=())
        self.assertIsNone(p4.proven_successor(reader, RUN, reader.chains[RUN]))
        self.assertFalse(p4.named_by_successor(reader, RUN))

    def test_two_successors_are_a_conflict_never_a_choice(self) -> None:
        reader = world(successors=(SUCCESSOR, OTHER))
        self.assertIsNone(p4.proven_successor(reader, RUN, reader.chains[RUN]))

    def test_a_successor_that_does_not_name_the_predecessor_set_aside_is_no_proof(self) -> None:
        reader = world(set_aside_reason=p4.SET_ASIDE_HUMAN_DECISION)
        self.assertIsNone(p4.proven_successor(reader, RUN, reader.chains[RUN]))

    def test_a_predecessor_with_a_consumption_of_its_own_is_no_proof(self) -> None:
        reader = world()
        reader.consumed_runs.append(RUN)
        self.assertIsNone(p4.proven_successor(reader, RUN, reader.chains[RUN]))

    def test_a_settlement_that_is_not_the_stored_result_is_no_proof(self) -> None:
        reader = world(digest_override="7" * 64)
        self.assertIsNone(p4.proven_successor(reader, RUN, reader.chains[RUN]))

    def test_a_missing_n_plus_1_snapshot_is_no_proof(self) -> None:
        reader = world()
        reader.snapshots.clear()
        self.assertIsNone(p4.proven_successor(reader, RUN, reader.chains[RUN]))

    def test_unreadable_records_are_no_proof(self) -> None:
        reader = world()
        del reader.inputs[REPAIR["task_id"]]
        self.assertIsNone(p4.proven_successor(reader, RUN, reader.chains[RUN]))
        self.assertIsNone(p4.proven_successor(reader, RUN, Chain(reader.chains[RUN].generations[:5])))


class LinkageTests(unittest.TestCase):
    def test_linkage_problems_name_each_disagreement(self) -> None:
        reader = world()
        batch, result = reader.batches[BATCH], reader.results[BATCH]
        digest = reader.repair_result_digest(BATCH)
        envelope = reader.inputs["rtk_01ARZ3NDEKTSV4RRFFQ69G5FC0"].request_envelope
        ok = dict(source_run_id=RUN, source_candidate_hash="a" * 64, source_candidate_generation=1, snapshot_hash=N1,
                  successor_envelope=envelope, repair_result_digest=digest)
        self.assertEqual([], p4.linkage_problems(batch, result, **ok))
        for change in (dict(source_run_id=SUCCESSOR), dict(source_candidate_hash="9" * 64),
                       dict(source_candidate_generation=2), dict(snapshot_hash=None),
                       dict(repair_result_digest="8" * 64),
                       dict(successor_envelope={**envelope, "candidate_generation": 3}),
                       dict(successor_envelope={**envelope, "review_contract": p4.PLANNING_CONTRACT}),
                       dict(successor_envelope={**envelope, "set_aside_runs": []})):
            with self.subTest(change=sorted(change)):
                self.assertTrue(p4.linkage_problems(batch, result, **{**ok, **change}))


if __name__ == "__main__":
    unittest.main()
