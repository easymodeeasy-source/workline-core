"""RB4/P5 reader carry: the canonical P4 set-aside reader reads a P5 ``p4_repaired`` successor's linkage.

``p4.set_aside_named`` (carried byte for byte from RB1-carry ``28c69e55``) is the one reader of a stored P4
discovery request's set-aside linkage. A P5 discovery request is the P4 request plus ``history_contract``,
``set_aside_summaries`` and ``decision_evidence`` (``p4.discovery_request``): the reader does not pin the
envelope's field set, it identifies the request through ``p4.contract_of_envelope`` (which reads both family
policies, GAP-A) and reads only the four linkage fields; the ``p4_repaired`` name is proven by
``p4.proven_successor``, which keeps a successor in its predecessor's policy family.
"""

from __future__ import annotations

from dataclasses import replace
import unittest

from workline.errors import ValidationError
from workline.review import history, p4, records, serialize

from test_review_p4_adjudication import adjudicate, bound, disposition, report, returned, TASK_A
from test_review_p4_dispatch import ADJUDICATION, DISCOVERY, G1, G2, G3, G4, G5_REPAIR, G6_SETTLE, REPAIR, RUN, Chain
from test_review_p4_evidence import coverage
from test_review_p4_repair import BATCH, N1, SUCCESSOR, Reader

P5 = p4.P5_POLICY_ID
SUCCESSOR_TASK = "rtk_01ARZ3NDEKTSV4RRFFQ69G5FC0"


class DigestReader(Reader):
    """The repair test's read-only reader double, plus the stored TaskInput digest ``set_aside_named`` checks."""

    def task_input_digest(self, task_id):
        return serialize.digest(self.read_task_input(task_id).to_record())


def _input(descriptor: dict, envelope: dict, policy: str, generation: int = 1) -> records.TaskInput:
    return p4.task_input(task_id=descriptor["task_id"], task_slot=descriptor["task_slot"],
                         task_kind=descriptor["task_kind"], actor_identity="a", actor_version="1", envelope=envelope,
                         candidate_hash=descriptor["candidate_hash"], candidate_material_digest="b" * 64,
                         review_context_hash="e" * 64, accepted_generation=generation, policy_id=policy)


def _discovery(generation: int, succession: dict | None, set_aside: list[dict], policy: str) -> dict:
    return p4.discovery_request(
        review_contract=p4.WORK_CONTRACT, review_kind="work-result-v1", viewpoint="correctness", candidate={"c": 1},
        context={"x": 1}, requirement={"r": 1}, candidate_generation=generation, succession=succession,
        set_aside_runs=set_aside, human_decision=None, policy_id=policy,
    )


def p5_world(*, successor_policy: str = P5) -> DigestReader:
    """A P5 predecessor repair-settled at G6 and its one Candidate N+1 successor (the P4 repair world, P5 policy)."""
    hashed = p4.policy_hash(P5)
    gens = [replace(gen, effective_policy_hash=hashed) for gen in (G1, G2, G3, G4, G5_REPAIR, G6_SETTLE)]
    found = adjudicate(bound(report(TASK_A, "correctness", [("HIGH", "x", "broken")])),
                       returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="HIGH")))
    batch = replace(p4.repair_batch(found, "9" * 64, repair_batch_id=BATCH, allowed_result_surface=["out.txt"]),
                    source_review_run_id=RUN, source_candidate_hash="a" * 64, target_identity="w_x",
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
    digest = serialize.digest(result.to_record())
    six = gens[5]
    gens[5] = replace(six, settled_tasks=six.settled_tasks[:2] + ({**six.settled_tasks[2], "result_digest": digest},))
    reader = DigestReader()
    reader.chains[RUN] = Chain(tuple(gens))
    reader.inputs[DISCOVERY["task_id"]] = _input(DISCOVERY, _discovery(1, None, [], P5), P5)
    reader.inputs[ADJUDICATION["task_id"]] = _input(ADJUDICATION, p4.adjudication_request(
        review_contract=p4.WORK_CONTRACT, review_kind="work-result-v1", review_run_id=RUN, candidate_hash="a" * 64,
        candidate_generation=1, review_context_hash="e" * 64, requirement={"r": 1}, reports=[], prior=p4.NO_PRIOR,
        evidence_ids=[], policy_id=P5), P5, 3)
    reader.inputs[REPAIR["task_id"]] = _input(REPAIR, p4.repair_request(
        review_contract=p4.WORK_CONTRACT, review_kind="work-result-v1", review_run_id=RUN, candidate_hash="a" * 64,
        candidate_generation=1, requirement={"r": 1}, repair_batch_id=BATCH, repair_batch_digest="9" * 64,
        allowed_result_surface=["out.txt"], strategy="ordinary", evidence_constraints=[], policy_id=P5), P5, 5)
    reader.batches[BATCH] = batch
    reader.results[BATCH] = result
    reader.snapshots.add(N1)
    succession = p4.succession_record(RUN, "a" * 64, BATCH, digest)
    successor_input = _input(dict(DISCOVERY, task_id=SUCCESSOR_TASK, candidate_hash=N1), _discovery(
        2, succession, [{"review_run_id": RUN, "reason": p4.SET_ASIDE_REPAIRED}], successor_policy), successor_policy)
    task = dict(DISCOVERY, task_id=SUCCESSOR_TASK, candidate_hash=N1,
                effective_policy_hash=p4.policy_hash(successor_policy),
                task_input_digest=serialize.digest(successor_input.to_record()))
    reader.inputs[SUCCESSOR_TASK] = successor_input
    reader.chains[SUCCESSOR] = Chain((replace(G1, review_run_id=SUCCESSOR, candidate_hash=N1, accepted_tasks=(task,),
                                              effective_policy_hash=p4.policy_hash(successor_policy)),))
    return reader


class P5SetAsideReaderTests(unittest.TestCase):
    def test_set_aside_named_positively_recognizes_a_p5_repaired_successor_linkage(self) -> None:
        reader = p5_world()
        envelope = reader.inputs[SUCCESSOR_TASK].request_envelope
        # the stored request is a P5 one: the P5 policy and the history contract, explicitly
        self.assertEqual(P5, p4.policy_of_envelope(envelope))
        self.assertEqual(history.HISTORY_CONTRACT, envelope[history.HISTORY_CONTRACT_KEY])
        self.assertIn("set_aside_summaries", envelope)
        self.assertEqual({P5}, p4.run_policies(reader, reader.chains[RUN]))
        self.assertEqual(SUCCESSOR, p4.proven_successor(reader, RUN, reader.chains[RUN]))
        self.assertEqual([{"review_run_id": RUN, "reason": p4.SET_ASIDE_REPAIRED}],
                         p4.set_aside_named(reader, SUCCESSOR, reader.chains[SUCCESSOR]))
        # the same linkage from a successor of another policy family is never a proof (GAP-A item 5)
        mixed = p5_world(successor_policy=p4.POLICY_ID)
        with self.assertRaises(ValidationError) as caught:
            p4.set_aside_named(mixed, SUCCESSOR, mixed.chains[SUCCESSOR])
        self.assertEqual(p4.REASON_LINKAGE_INVALID, caught.exception.code)


if __name__ == "__main__":
    unittest.main()
