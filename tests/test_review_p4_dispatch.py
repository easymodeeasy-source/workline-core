"""P4 §27.3 / §27.31 / G-3 / G-6 / G-7: explicit contract dispatch and the P4 chain shapes, at unit level.

* a Run's contract is the one its TaskInput's request explicitly binds - never its shape or generation count;
* the P4 shapes: G5 is a seal exactly when sealed with no new task, a repair acceptance exactly when it accepts
  one repair task; G6 settles that repair or invalidates the seal; no G7; a P4 G4 is never a v1 invalidation;
* v1 markers, request envelopes and the Work operation identity keep their exact v1 meaning (G-6 item 4, G-7);
* the selectors are new types, refused before anything when malformed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import unittest

from workline.errors import ValidationError
from workline.review import p4, planning, records, serialize, work_invocation, work_review
from workline.review.store import _chain_invariants

RUN = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"
RECEIPT = "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def descriptor(task_id: str, kind: str, slot: str) -> dict:
    return {
        "task_id": task_id, "task_slot": slot, "task_kind": kind, "reviewer_identity": "a", "reviewer_version": "1",
        "candidate_hash": "a" * 64, "candidate_material_digest": "b" * 64, "reconstruction_mode": "snapshot",
        "request_digest": "c" * 64, "task_input_digest": "d" * 64, "review_context_hash": "e" * 64,
        "effective_policy_hash": p4.policy_hash(),
    }


DISCOVERY = descriptor("rtk_01ARZ3NDEKTSV4RRFFQ69G5FA1", p4.TASK_KIND_DISCOVERY, p4.discovery_slot("correctness"))
ADJUDICATION = descriptor("rtk_01ARZ3NDEKTSV4RRFFQ69G5FA2", p4.TASK_KIND_ADJUDICATION, p4.SLOT_ADJUDICATOR)
REPAIR = descriptor("rtk_01ARZ3NDEKTSV4RRFFQ69G5FA3", p4.TASK_KIND_REPAIR, p4.SLOT_REPAIR)


def settled(task: dict, generation: int) -> dict:
    return {"task_id": task["task_id"], "status": "completed", "result_digest": "f" * 64, "settled_generation": generation}


def gate(generation: int, accepted: tuple, done: tuple, *, sealed: bool = False) -> records.GateGeneration:
    return records.GateGeneration(
        review_run_id=RUN, generation=generation, previous_generation=None if generation == 1 else generation - 1,
        previous_digest=None if generation == 1 else "0" * 64, review_kind="work-result-v1", target_identity="w_x",
        operation_identity="start:" + "1" * 64, candidate_hash="a" * 64, review_context_hash="e" * 64,
        effective_policy_hash=p4.policy_hash(), evidence_digest="2" * 64, coverage_digest="3" * 64,
        raw_report_set_digest="4" * 64, adjudication_digest="5" * 64, obligation_digest="6" * 64,
        accepted_tasks=accepted, settled_tasks=done,
        status=records.GATE_STATUS_SEALED if sealed else records.GATE_STATUS_OPEN,
        receipt_id=RECEIPT if sealed else None, authorized_operation_stage="start:work-terminal" if sealed else None,
    )


@dataclass(frozen=True)
class Chain:
    generations: tuple

    @property
    def latest(self):
        return self.generations[-1]


def chain(*gens: records.GateGeneration) -> Chain:
    return Chain(tuple(gens))


G1 = gate(1, (DISCOVERY,), ())
G2 = gate(2, (DISCOVERY,), (settled(DISCOVERY, 2),))
G3 = gate(3, (DISCOVERY, ADJUDICATION), (settled(DISCOVERY, 2),))
G4 = gate(4, (DISCOVERY, ADJUDICATION), (settled(DISCOVERY, 2), settled(ADJUDICATION, 4)))
G5_SEAL = replace(G4, generation=5, previous_generation=4, status=records.GATE_STATUS_SEALED, receipt_id=RECEIPT,
                  authorized_operation_stage="start:work-terminal")
G5_REPAIR = gate(5, (DISCOVERY, ADJUDICATION, REPAIR), (settled(DISCOVERY, 2), settled(ADJUDICATION, 4)))
G6_SETTLE = gate(6, (DISCOVERY, ADJUDICATION, REPAIR),
                 (settled(DISCOVERY, 2), settled(ADJUDICATION, 4), settled(REPAIR, 6)))
G6_INVALIDATE = replace(G5_SEAL, generation=6, previous_generation=5, status=records.GATE_STATUS_OPEN, receipt_id=None,
                        authorized_operation_stage=None)


class ShapeTests(unittest.TestCase):
    def test_every_p4_shape_is_valid_and_classified_by_its_records(self) -> None:
        for gens, state in (
            ((G1,), p4.STATE_G1), ((G1, G2), p4.STATE_G2), ((G1, G2, G3), p4.STATE_G3),
            ((G1, G2, G3, G4, G5_SEAL), p4.STATE_G5_SEALED), ((G1, G2, G3, G4, G5_REPAIR), p4.STATE_G5_REPAIR),
            ((G1, G2, G3, G4, G5_REPAIR, G6_SETTLE), p4.STATE_G6_SETTLED),
            ((G1, G2, G3, G4, G5_SEAL, G6_INVALIDATE), p4.STATE_G6_INVALIDATED),
        ):
            with self.subTest(state=state):
                found = chain(*gens)
                self.assertEqual([], p4.chain_problems(found))
                self.assertEqual(state, p4.run_state(found, None))
                _chain_invariants(RUN, list(gens))  # the P1 full-snapshot invariants hold for every P4 shape

    def test_g4_reads_its_outcome_from_the_adjudication_never_as_an_invalidation(self) -> None:
        found = chain(G1, G2, G3, G4)
        self.assertEqual([], p4.chain_problems(found))
        self.assertEqual(p4.STATE_G4_HUMAN, p4.run_state(found, p4.HUMAN_WAIT))
        self.assertEqual(p4.STATE_G4_REPAIR, p4.run_state(found, p4.REPAIR_REQUIRED))
        self.assertEqual(p4.STATE_G4_READY, p4.run_state(found, p4.AUTHORIZATION_READY))
        self.assertIsNone(p4.shape_of(found))

    def test_g5_seal_and_g5_repair_are_told_apart_by_records_not_number(self) -> None:
        self.assertEqual(p4.SHAPE_SEAL, p4.shape_of(chain(G1, G2, G3, G4, G5_SEAL)))
        self.assertEqual(p4.SHAPE_REPAIR, p4.shape_of(chain(G1, G2, G3, G4, G5_REPAIR)))
        hybrid = replace(G5_REPAIR, status=records.GATE_STATUS_SEALED, receipt_id=RECEIPT,
                         authorized_operation_stage="start:work-terminal")
        self.assertTrue(p4.chain_problems(chain(G1, G2, G3, G4, hybrid)), "a seal that accepts a repair is no P4 shape")

    def test_no_g7_and_no_invalidation_after_a_repair_or_settle_after_a_seal(self) -> None:
        g7 = replace(G6_SETTLE, generation=7, previous_generation=6)
        self.assertTrue(p4.chain_problems(chain(G1, G2, G3, G4, G5_REPAIR, G6_SETTLE, g7)))
        self.assertTrue(p4.chain_problems(chain(G1, G2, G3, G4, G5_SEAL, G6_SETTLE)))
        repair_invalidated = replace(G5_REPAIR, generation=6, previous_generation=5)
        self.assertTrue(p4.chain_problems(chain(G1, G2, G3, G4, G5_REPAIR, repair_invalidated)))

    def test_a_candidate_change_inside_a_run_is_refused(self) -> None:
        moved = replace(G2, candidate_hash="9" * 64)
        self.assertTrue(p4.chain_problems(chain(G1, moved)))

    def test_a_v1_shaped_chain_is_no_p4_shape(self) -> None:
        v1_task = descriptor("rtk_01ARZ3NDEKTSV4RRFFQ69G5FA9", "work-result-review-v1", "work-result-reviewer")
        v1 = gate(1, (v1_task,), ())
        self.assertTrue(p4.chain_problems(chain(v1)))

    def test_transition_map_is_p4s_own_and_v1_maps_are_untouched(self) -> None:
        from workline import roadmap_review, start_review

        self.assertEqual(("seal", "accept"), p4.TRANSITIONS[5])
        self.assertEqual(("settle", "invalidate"), p4.TRANSITIONS[6])
        self.assertNotIn(7, p4.TRANSITIONS)
        self.assertEqual({1: "accept", 2: "settle", 3: "seal", 4: "invalidate"}, start_review.TRANSITIONS)
        self.assertEqual({1: "accept", 2: "settle", 3: "seal", 4: "invalidate"}, roadmap_review._TRANSITION_OF)


class DispatchTests(unittest.TestCase):
    def envelope(self, **overrides: object) -> dict:
        found = p4.discovery_request(
            review_contract=p4.WORK_CONTRACT, review_kind="work-result-v1", viewpoint="correctness", candidate={"c": 1},
            context={"x": 1}, requirement={"r": 1}, candidate_generation=1, succession=None, set_aside_runs=[],
            human_decision=None,
        )
        found.update(overrides)
        return found

    def test_dispatch_reads_the_explicit_contract_only(self) -> None:
        self.assertEqual(p4.WORK_CONTRACT, p4.contract_of_envelope(self.envelope()))
        self.assertIsNone(p4.contract_of_envelope(self.envelope(review_contract="review-v1-work-v1")))
        self.assertIsNone(p4.contract_of_envelope(self.envelope(policy_id="review-v1-work-policy-v1")))
        self.assertIsNone(p4.contract_of_envelope({"schema": "review-work-request", "version": 2}))
        self.assertIsNone(p4.contract_of_envelope({"schema": "review-planning-request", "version": 1}))

    def test_a_task_input_whose_kind_and_request_disagree_is_not_p4(self) -> None:
        found = p4.task_input(task_id="rtk_01ARZ3NDEKTSV4RRFFQ69G5FA1", task_slot="p4-discovery.correctness",
                              task_kind=p4.TASK_KIND_REPAIR, actor_identity="a", actor_version="1",
                              envelope=self.envelope(), candidate_hash="a" * 64, candidate_material_digest="b" * 64,
                              review_context_hash="e" * 64, accepted_generation=1)
        self.assertIsNone(p4.contract_of_task_input(found))
        self.assertEqual(p4.WORK_CONTRACT, p4.contract_of_task_input(replace(found, task_kind=p4.TASK_KIND_DISCOVERY)))

    def test_v1_markers_keep_their_bytes_and_p4_markers_are_distinct(self) -> None:
        self.assertEqual({"review_contract": "review-v1-work-v1", "publication_contract": "review-v1-split-v1"},
                         work_invocation.markers())
        p4_markers = work_invocation.markers(p4.WORK_CONTRACT)
        self.assertEqual("review-v1-work-p4-v1", p4_markers["review_contract"])
        live = {"operation": "start", "work_id": "w_x", "mode": "single-work"}
        self.assertEqual("review-v1-work-v1", work_invocation.contract_of({**live, **work_invocation.markers()}))
        self.assertEqual(p4.WORK_CONTRACT, work_invocation.contract_of({**live, **p4_markers}))
        self.assertIsNone(work_invocation.contract_of({**live, "review_contract": "review-v1-work-v9",
                                                       "publication_contract": "review-v1-split-v1"}))
        self.assertIsNone(work_invocation.contract_of(live))
        self.assertEqual({"review_contract": "review-v1-planning-v1", "publication_contract": planning.PUBLICATION_CONTRACT},
                         planning.invocation_markers())
        self.assertEqual("review-v1-planning-p4-v1", planning.invocation_markers_p4()["review_contract"])
        with self.assertRaises(ValueError):
            work_invocation.markers("review-v1-work-v9")

    def test_p4_identities_are_distinct_from_every_v1_identity(self) -> None:
        v1 = {"review-v1-planning-v1", "review-v1-work-v1", "review-v1-planning-policy-v1", "review-v1-work-policy-v1",
              "review-v1-planning-publication-v1", "review-v1-split-v1"}
        mine = {p4.PLANNING_CONTRACT, p4.WORK_CONTRACT, p4.POLICY_ID, p4.DISCOVERY_INSTRUCTION,
                p4.ADJUDICATION_INSTRUCTION, p4.REPAIR_INSTRUCTION, p4.ADJUDICATION_CONTRACT}
        self.assertEqual(set(), v1 & mine)
        self.assertEqual(7, len(mine))

    def test_work_operation_identity_is_unchanged_by_p4(self) -> None:
        identity = work_review.request_identity_record("w_01ARZ3NDEKTSV4RRFFQ69G5FAV")
        self.assertEqual("review-v1-work-v1", identity["review_contract"])
        self.assertEqual("start:" + serialize.digest(identity), work_review.operation_identity("w_01ARZ3NDEKTSV4RRFFQ69G5FAV"))


class SelectorTests(unittest.TestCase):
    def test_p4_selectors_are_new_types_validated_before_anything(self) -> None:
        def actor(task):  # pragma: no cover - never called
            return None

        good = dict(discovery=(p4.DiscoveryBinding("correctness", actor, "d", "1"),),
                    adjudicator=p4.ActorBinding(actor, "a", "1"), repair=p4.ActorBinding(actor, "r", "1"))
        planning.validate_planning_review_p4(planning.PlanningReviewP4(**good))
        work_review.validate_work_review_p4(work_review.WorkReviewP4(**good))
        for bad in (
            dict(good, discovery=()),
            dict(good, discovery=(p4.DiscoveryBinding("Bad View", actor, "d", "1"),)),
            dict(good, discovery=(p4.DiscoveryBinding("v", actor, "d", "1"), p4.DiscoveryBinding("v", actor, "e", "1"))),
            dict(good, adjudicator=p4.ActorBinding("not callable", "a", "1")),
            dict(good, repair=p4.ActorBinding(actor, " r", "1")),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                work_review.validate_work_review_p4(work_review.WorkReviewP4(**bad))
        with self.assertRaises(ValidationError):
            work_review.validate_work_review_p4(work_review.WorkReviewP4(**good, contract="review-v1-work-v1"))
        with self.assertRaises(ValidationError):
            planning.validate_planning_review_p4(work_review.WorkReviewP4(**good))
        with self.assertRaises(ValidationError):
            work_review.validate_work_review(work_review.WorkReviewP4(**good))
        decided = dict(good, human_decision=p4.HumanDecision("hd 1", "maybe"))
        with self.assertRaises(ValidationError):
            planning.validate_planning_review_p4(planning.PlanningReviewP4(**decided))


if __name__ == "__main__":
    unittest.main()
