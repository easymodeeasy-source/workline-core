"""P6 §30.40, Policy Review windows 1-9: interruption / recovery of ``project-policy-change`` before persistence.

Each row kills the process (``Crash`` / ``Interrupted``, never a StopError, so nothing is abandoned on its way out)
at one instant of a Policy Change - a strengthen of ``review.discovery.required_slots`` 1 -> 2 on an evidence
Project with a local bare remote - and runs the same request again. Every retry must end ``applied`` with the §30.40
retry invariants (``project_policy_helpers.InterruptionCase.assert_invariants``):

* the same policy_change_id / Candidate / Review IDs the interrupted attempt reserved;
* no duplicate change record, no Profile version skip, no overwrite on a before mismatch;
* no duplicate Consumption / publication, no force / history rewrite;
* no authorization under after-state strength.
"""

from __future__ import annotations

from project_policy_helpers import (
    Crash, InterruptionCase, Interrupted, after_effect, at_call, crash_at, reserving,
)
from workline import project_policy
from workline.mutation import Mutation
from workline.review import p4, paths

CANDIDATES = paths.candidate_snapshot_rel("0" * 64).rsplit("/", 1)[0] + "/"


def generation(n: int, *, after: bool):
    """Around the n-th generation mutation's finish: before it applies anything, or right after its commit."""
    return lambda: crash_at(project_policy, "_finish_generation", after=after, when=at_call(n))


class PolicyReviewWindows(InterruptionCase):
    # 1. policy_change_id reservation
    def test_w01_policy_change_id_reserved(self) -> None:
        self.interrupted(lambda: crash_at(Mutation, "reserve_id", after=True, when=reserving("review_policy_change")))

    # 2. Candidate snapshot
    def test_w02a_candidate_frozen_before_any_review_record(self) -> None:
        self.interrupted(lambda: crash_at(project_policy, "_accept"))

    def test_w02b_candidate_snapshot_created_before_g1_completes(self) -> None:
        self.interrupted(lambda: after_effect("create_file", project_policy.STAGE_GENERATION,
                                              path=lambda found: found.startswith(CANDIDATES)), Interrupted)

    # 3. G1
    def test_w03_g1_committed(self) -> None:
        self.interrupted(generation(1, after=True))

    # 4. discovery return before G2
    def test_w04_discovery_returned_before_g2(self) -> None:
        self.interrupted(lambda: crash_at(p4, "report_record", after=True, when=at_call(1)))

    # 5. G2
    def test_w05a_g2_recorded_not_applied(self) -> None:
        self.interrupted(generation(2, after=False))

    def test_w05b_g2_committed(self) -> None:
        self.interrupted(generation(2, after=True))
        self.assertEqual(0, self.discovery_calls, "a settled discovery task is never launched again")

    # 6. G3
    def test_w06_g3_committed(self) -> None:
        self.interrupted(generation(3, after=True))
        self.assertEqual(0, self.discovery_calls)

    # 7. adjudicator return before G4
    def test_w07_adjudicator_returned_before_g4(self) -> None:
        self.interrupted(lambda: crash_at(p4, "normalize_adjudication", after=True, when=at_call(1)))

    # 8. G4
    def test_w08a_g4_recorded_not_applied(self) -> None:
        self.interrupted(generation(4, after=False))

    def test_w08b_g4_committed(self) -> None:
        self.interrupted(generation(4, after=True))
        self.assertEqual((0, 0), (self.discovery_calls, self.adjudicator_calls),
                         "a settled adjudication is never launched again")

    # 9. G5 Receipt
    def test_w09a_g5_recorded_not_applied(self) -> None:
        self.interrupted(generation(5, after=False))

    def test_w09b_g5_receipt_committed(self) -> None:
        self.interrupted(generation(5, after=True))
        self.assertEqual((0, 0), (self.discovery_calls, self.adjudicator_calls))


class PolicyReviewWindowsRemoteLess(InterruptionCase):
    template = "local"

    def test_w03_g1_committed_remote_less(self) -> None:
        self.interrupted(generation(1, after=True))

    def test_w09b_g5_receipt_committed_remote_less(self) -> None:
        self.interrupted(generation(5, after=True))


if __name__ == "__main__":
    import unittest

    unittest.main()
