"""RB4 / P5 §28.4 / §28.27 (R-4): a recovered P5 Run re-binds its relation and decision IDs from canonical history.

Two canonical P5 histories, each interrupted after the Run's G4 and before its seal, with the runtime lost:

* a repair successor S whose G4 accepted one cross-run relation - a ``review_relation`` ID reserved under
  ``review-relation:<S>:1``;
* a Human-decision successor B whose generation 1 bound one Human Decision Evidence record - a ``review_decision``
  ID reserved under ``review-decision:<the HUMAN_WAIT Run>``.

The next invocation's recovery planning mutation binds the Run's canonical reservations from its committed
records (``roadmap_review._p4_recovered_bindings`` <- ``p4.recovered_history_bindings``); it dies right after
binding them, and the next invocation resumes that binding and finishes the Run. For each:

* the same key binds the same ID, each ID under exactly one key, and nothing else is reserved for history;
* no second relation or Human Decision Evidence record, and every history record keeps its exact bytes;
* a missing or malformed source fails closed before any recovery reservation is recorded.

A P4-only Run binds no P5 history: ``recovered_history_bindings`` returns nothing and its recovery reserves none.
"""

from __future__ import annotations

from typing import Any, Callable

from p5_helpers import decision_evidence, p4_only_cycle
from planning_helpers import Crash, crash_at, plan
from test_review_p4_planning import Discovery, P4PlanningCase, Repairer, p4_review, problem
from test_review_p5_human_decisions import roadmap_requirement
from test_review_p5_planning import RelatingAdjudicator
from workline import roadmap_review as rr
from workline.errors import ReconcileRequired, StopError
from workline.ids import kind_of
from workline.review import history, p4, paths, planning
from workline.review.store import ReviewStore

HUMAN = p4.P4Claim("HIGH", "human", "which scope?")
LOW = p4.P4Claim("LOW", "low", "a minor wording note")
CONFIRMED = p4.HumanDecision("hd-1", p4.DECISION_CONFIRMED)
HISTORY_KEYS = (history.RELATION_KEY_PREFIX, history.DECISION_KEY_PREFIX)


def resumed_review(evidence: tuple) -> Any:
    """The Human-decision continuation: CONFIRMED, its evidence and a LOW discovery."""
    base = p4_review(Discovery((LOW,)), decision=CONFIRMED)
    return planning.PlanningReviewP4(base.discovery, base.adjudicator, base.repair, CONFIRMED,
                                     decision_evidence=evidence)


def repairing_review(adjudicator: Any = None) -> Any:
    """A repair cycle: the first discovery finds a blocking problem, the successor's a LOW note."""
    return p4_review(Discovery((problem(),), (LOW,)), adjudicator=adjudicator or RelatingAdjudicator(),
                     repairer=Repairer())


def history_bytes(store: Any) -> dict[str, bytes]:
    base = store.root / paths.HISTORY_DIR
    return {path.relative_to(store.root).as_posix(): path.read_bytes() for path in sorted(base.rglob("*.yaml"))}


def history_reservations(record: dict[str, Any]) -> dict[str, str]:
    return {key: value for key, value in (record.get("reserved_ids") or {}).items() if key.startswith(HISTORY_KEYS)}


class RecoveredHistoryIdTests(P4PlanningCase):
    def recovery_records(self, store: Any) -> list[dict[str, Any]]:
        return [record for record in self.pending(store)
                if planning.MARKER_RECOVERY in (record.get("invocation") or {})]

    def at_g4(self, store: Any) -> str:
        """The one Run of the interrupted cycle that stands at G4 (the one recovery continues)."""
        review = ReviewStore(store)
        (run,) = [run for run in self.runs(store) if review.gate_chain(run).latest.generation == 4]
        return run

    def refused_before_any_reservation(self, store: Any, review_of: Callable[[], Any], the_plan: Any) -> StopError:
        with self.assertRaises(StopError) as raised:
            self.reviewed_p4(store, review_of(), the_plan)
        self.assertEqual([], self.pending(store), "nothing is opened, so nothing is reserved")
        return raised.exception

    def recover(self, store: Any, run: str, expected: dict[str, str], review_of: Callable[[], Any], the_plan: Any,
                sources: list[str]) -> None:
        """Lose the runtime of the cycle interrupted at ``run``'s G4, then prove the recovery binds ``expected``."""
        review = ReviewStore(store)
        chain = review.gate_chain(run)
        (original,) = [record for record in self.pending(store)
                       if (record.get("invocation") or {}).get("operation") == "roadmap-create"]
        self.assertEqual(expected, history_reservations(original), "what the interrupted Run reserved")
        self.assertEqual(sorted((key, value, kind_of(value)) for key, value in expected.items()),
                         sorted(p4.recovered_history_bindings(review, run, chain)),
                         "derived from the Run's canonical records alone")
        before = history_bytes(store)
        families = {family: review.history_ids(family) for family in paths.HISTORY_FAMILIES}
        self.runtime_gone(store)

        # a missing or malformed source fails closed: recovery discovery reconciles before any mutation opens
        for relative in sources:
            path = store.root / relative
            saved = path.read_bytes()
            with self.subTest(missing=relative):
                path.unlink()
                refused = self.refused_before_any_reservation(store, review_of, the_plan)
                self.assertIsInstance(refused, ReconcileRequired)
                self.assertEqual("review_recovery_incomplete", refused.reason, refused)
            with self.subTest(malformed=relative):
                path.write_bytes(b"schema: review-history\nversion: 1\nnot: canonical\n")
                self.refused_before_any_reservation(store, review_of, the_plan)
            path.write_bytes(saved)
        self.assertEqual(before, history_bytes(store))

        # the recovery planning mutation binds the canonical reservations - and dies right after binding them
        with crash_at(rr, "_note_binding"), self.assertRaises(Crash):
            self.reviewed_p4(store, review_of(), the_plan)
        (recovery,) = self.recovery_records(store)
        self.assertEqual(run, recovery["invocation"][planning.MARKER_RECOVERY])
        bound = recovery["reserved_ids"]
        self.assertEqual(expected, history_reservations(recovery),
                         "the same key binds the same ID, and nothing else is reserved for history")
        self.assertEqual(len(bound), len(set(bound.values())), "no ID is reserved twice")
        for key, identifier in expected.items():
            self.assertEqual([key], [found for found, value in bound.items() if value == identifier])

        # the next invocation resumes that binding (re-derived from canonical history) and finishes the Run
        result = self.reviewed_p4(store, review_of(), the_plan)
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        self.assertEqual(run, result.review_run_id)
        self.assertIn("recovered Run", result.detail)
        review = ReviewStore(store)
        self.assertEqual(families[paths.HISTORY_RELATIONS], review.history_ids(paths.HISTORY_RELATIONS),
                         "no second relation record")
        self.assertEqual(families[paths.HISTORY_HUMAN_DECISIONS], review.history_ids(paths.HISTORY_HUMAN_DECISIONS),
                         "no second Human Decision Evidence record")
        after = history_bytes(store)
        self.assertEqual(before, {path: data for path, data in after.items() if path in before},
                         "the relation / evidence and every earlier history record keep their bytes")
        self.assertEqual(sorted([*before, paths.history_run_rel(run)]), sorted(after),
                         "the only new history record is the Run's consumed summary")
        self.assertEqual([], history.history_problems(review, work_ids=None))
        self.assertEqual([], self.problems(store))

    def test_a_recovered_p5_run_binds_its_relation_id_once_from_canonical_history(self) -> None:
        store = self.planning_project()
        adjudicator = RelatingAdjudicator()
        with crash_at(rr, "_p4_seal"), self.assertRaises(Crash):
            self.reviewed_p4(store, repairing_review(adjudicator))
        self.assertEqual(1, len(adjudicator.claims))
        successor = self.at_g4(store)
        review = ReviewStore(store)
        (relation_id,) = review.history_ids(paths.HISTORY_RELATIONS)
        relation = review.read_history(paths.HISTORY_RELATIONS, relation_id)
        relation_rel = paths.history_relation_rel(relation_id)
        # the reader alone fails closed on a missing or unreadable source (TaskInput, relation record)
        chain = review.gate_chain(successor)
        task_input = store.root / paths.task_input_rel(str(chain.generations[0].accepted_tasks[0]["task_id"]))
        for path in (task_input, store.root / relation_rel):
            saved = path.read_bytes()
            path.unlink()
            with self.subTest(unread=path.name), self.assertRaises(StopError):
                p4.recovered_history_bindings(ReviewStore(store), successor, chain)
            path.write_bytes(b"schema: review-history\nversion: 1\nnot: canonical\n")
            with self.subTest(malformed=path.name), self.assertRaises(StopError):
                p4.recovered_history_bindings(ReviewStore(store), successor, chain)
            path.write_bytes(saved)
        self.recover(store, successor, {history.review_relation_key(successor, 1): relation_id},
                     lambda: repairing_review(), None,
                     [relation_rel, paths.history_finding_rel(relation.source.id)])

    def test_a_recovered_p5_run_binds_its_decision_id_once_from_canonical_history(self) -> None:
        store = self.planning_project()
        the_plan = plan()
        waiting_result = self.reviewed_p4(store, p4_review(Discovery((HUMAN,))), the_plan)
        self.assertEqual(rr.STATUS_HUMAN_WAIT, waiting_result.status, waiting_result.detail)
        waiting = str(waiting_result.review_run_id)
        evidence = (decision_evidence(ReviewStore(store), waiting, CONFIRMED, roadmap_requirement(the_plan)),)
        with crash_at(rr, "_p4_seal"), self.assertRaises(Crash):
            self.reviewed_p4(store, resumed_review(evidence), the_plan)
        (successor,) = [run for run in self.runs(store) if run != waiting]
        self.assertEqual(4, ReviewStore(store).gate_chain(successor).latest.generation)
        (decision_id,) = ReviewStore(store).history_ids(paths.HISTORY_HUMAN_DECISIONS)
        self.recover(store, successor, {history.review_decision_key(waiting): decision_id},
                     lambda: resumed_review(evidence), the_plan, [paths.history_decision_rel(decision_id)])

    def test_a_p4_only_run_has_no_p5_history_binding_and_its_recovery_reserves_none(self) -> None:
        store = self.planning_project()
        with p4_only_cycle(), crash_at(rr, "_p4_seal"), self.assertRaises(Crash):
            self.reviewed_p4(store, p4_review(Discovery((LOW,))))
        (run,) = self.runs(store)
        review = ReviewStore(store)
        self.assertEqual([], p4.recovered_history_bindings(review, run, review.gate_chain(run)))
        self.runtime_gone(store)
        with crash_at(rr, "_note_binding"), self.assertRaises(Crash):
            self.reviewed_p4(store, p4_review(Discovery()))
        (recovery,) = self.recovery_records(store)
        self.assertEqual({}, history_reservations(recovery))
        self.assertIn(run, recovery["reserved_ids"].values(), "the Run itself is bound")
        result = self.reviewed_p4(store, p4_review(Discovery()))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        self.assertEqual(run, result.review_run_id)
        self.assertFalse((store.root / paths.HISTORY_DIR).exists(), "a P4-only cycle writes no history")
        self.assertEqual([], self.problems(store))
