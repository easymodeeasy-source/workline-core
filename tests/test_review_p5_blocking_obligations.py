"""RB4/P5 carry of RB1's ``p4.blocking_obligations``: a valid P5 Run's adjudication is read under the family dispatch.

The helper (carried byte for byte from RB1-carry ``854dde64``) checks the Run's identity through ``run_contracts``
(the owner contract its generation-1 TaskInputs bind) against the adjudication's ``review_contract``. Under GAP-A both
policies of the P4-capable family bind the same owner contract, so a P5 Run - P5 policy, history contract, P5
Effective Policy - is read exactly as a P4-only one, and its blocking count is the adjudication's.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import unittest

from workline.review import p4, serialize

from test_review_p4_adjudication import adjudicate, bound, disposition, report, returned, TASK_A
from test_review_p4_dispatch import DISCOVERY, G1, G2, G3, G4, RUN, Chain
from test_review_p4_repair import Reader
from test_review_p5_set_aside_reader import _discovery, _input


@dataclass(frozen=True)
class GateChain(Chain):
    """The dispatch tests' chain double, plus the by-number lookup a validated gate chain offers."""

    def generation(self, number: int):
        return self.generations[number - 1]


class AdjudicationReader(Reader):
    """The repair test's read-only reader double, plus the stored adjudication the helper reads."""

    adjudication = None

    def read_adjudication(self, run_id):
        return self.adjudication

    def adjudication_digest(self, run_id):
        return serialize.digest(self.adjudication.to_record())


def run_at_g4(policy: str) -> AdjudicationReader:
    """A Run of ``policy`` at generation 4, bound to an adjudication with one HIGH Problem (REPAIR_REQUIRED)."""
    found = adjudicate(bound(report(TASK_A, "correctness", [("HIGH", "x", "broken")])),
                       returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="HIGH")))
    found = replace(found, effective_policy_hash=p4.policy_hash(policy))
    digests = {"adjudication_digest": serialize.digest(found.to_record()),
               "obligation_digest": serialize.digest(p4.obligations_record(found))}
    identity = {"review_run_id": RUN, "review_kind": found.review_kind, "target_identity": found.target_identity,
                "operation_identity": found.operation_identity, "candidate_hash": found.candidate_hash,
                "effective_policy_hash": p4.policy_hash(policy)}
    reader = AdjudicationReader()
    reader.adjudication = found
    reader.chains[RUN] = GateChain(tuple(replace(gen, **identity, **digests) for gen in (G1, G2, G3, G4)))
    reader.inputs[DISCOVERY["task_id"]] = _input(DISCOVERY, _discovery(1, None, [], policy), policy)
    return reader


class P5BlockingObligationsTests(unittest.TestCase):
    def test_a_valid_p5_runs_adjudication_is_counted_under_the_family_dispatch(self) -> None:
        for policy in (p4.P5_POLICY_ID, p4.POLICY_ID):
            with self.subTest(policy=policy):
                reader = run_at_g4(policy)
                self.assertEqual({policy}, p4.run_policies(reader, reader.chains[RUN]))
                self.assertEqual(p4.REPAIR_REQUIRED, reader.adjudication.outcome)
                self.assertEqual(1, p4.blocking_obligations(reader, RUN, reader.chains[RUN]))
                # generations 1-3 hold no adjudication yet: never 0
                self.assertIsNone(p4.blocking_obligations(reader, RUN, GateChain(reader.chains[RUN].generations[:3])))


if __name__ == "__main__":
    unittest.main()
