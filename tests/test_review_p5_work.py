"""RB4 / P5 §28.27 (Work): history written by the START owner at each exact transition boundary.

Every flow runs ``start(..., review=WorkReviewP4(...))`` with the scripted, terminating actors of
:mod:`test_review_p4_work` and the real terminal path (K1, the terminal stage, K2, both pushes). A fresh Run
binds the P5-capable policy (GAP-A option 3), and its START owner writes:

* G4: one Finding summary per normalized Finding (§28.8);
* G6 repair: the Repair summary and the repaired Run summary (§28.9);
* the terminal stage: the consumed Run summary FIRST, then the two events and the Consumption - one durable unit
  (§28.6, P-2) - and K2 carries the event log, the Consumption and the summary, proven by C-2(K2) T4 / T8;

A P4-only cycle (the test-only seam ``p4_only_cycle``) keeps the frozen three-effect stage and K2 delta.
"""

from __future__ import annotations

from p5_helpers import first_envelope, p4_only_cycle, p5_only_cycle
from test_review_p4_planning import Discovery, problem
from test_review_p4_work import P4WorkCase, WorkRepairer, work_p4
from workline import start_review as sr
from workline.review import history, p4, paths
from workline.review.store import ReviewStore



#: R6-1 (TEST-ONLY seam, tests/p5_helpers.p5_only_cycle): production binds the P6-capable default to every NEW first
#: Run; this module keeps testing P5 Runs exactly as pre-P6 code wrote them.
_P5_SEAM = p5_only_cycle()


def setUpModule() -> None:
    _P5_SEAM.__enter__()


def tearDownModule() -> None:
    _P5_SEAM.__exit__(None, None, None)

class P5WorkTests(P4WorkCase):
    def terminal_stage(self, record: dict) -> list[dict]:
        """The effects of the one lifecycle stage that creates a file: the review-v1 terminal stage."""
        lifecycle = [effect for effect in record["effects"] if str(effect["stage"]).startswith(f"{self.work_id}:lifecycle:")]
        (stage,) = {effect["stage"] for effect in lifecycle if effect["kind"] == "create_file"}
        return [effect for effect in lifecycle if effect["stage"] == stage]

    def test_a_fresh_work_run_is_p5_and_its_terminal_stage_writes_the_consumed_summary_first(self) -> None:
        discovery = Discovery((p4.P4Claim("LOW", "low", "a minor note"),))
        result, record = self.complete(self.completing(write={"out.txt": b"out\n"}, message="feat: out"),
                                       review=work_p4(discovery))
        review = ReviewStore(self.store)
        (run_id,) = self.runs()
        envelope = first_envelope(review, run_id)
        self.assertEqual((p4.P5_POLICY_ID, history.HISTORY_CONTRACT),
                         (envelope["policy_id"], envelope["history_contract"]))
        self.assertEqual(p4.P5_POLICY_ID, envelope["context"]["policy_id"])
        (finding,) = review.read_adjudication(run_id).findings
        self.assertEqual("LOW", review.read_history(paths.HISTORY_FINDINGS, str(finding["finding_id"])).severity)
        # P-2: one terminal stage, the summary create first, then exactly the frozen three effects
        stage = self.terminal_stage(record)
        self.assertEqual(["create_file", "append_event", "append_event", "create_file"], [e["kind"] for e in stage])
        self.assertEqual(paths.history_run_rel(run_id), stage[0]["payload"]["path"])
        k2 = self.head()
        consumption = self.consumption(k2, record)
        self.assertEqual(sorted([("M", ".workline/events/events.jsonl"),
                                 ("A", paths.consumption_rel(consumption.consumption_id)),
                                 ("A", paths.history_run_rel(run_id))]), self.delta(k2))
        summary = review.read_history(paths.HISTORY_RUNS, run_id)
        self.assertEqual((history.DISPOSITION_CONSUMED, consumption.consumption_id),
                         (summary.durable_disposition, summary.consumption_id))
        self.assertTrue(sr.is_terminal_stage(_Loaded(self.store, record), stage[0]["stage"], self.work_id))
        self.assertEqual([], history.history_problems(review, work_ids=None))
        self.assertEqual([], self.problems())
        self.assertEqual(k2, self.remote_main())

    def test_a_work_repair_writes_the_repair_and_repaired_summaries_and_the_successor_stays_p5(self) -> None:
        discovery = Discovery((problem(),), ())
        result, record = self.complete(self.completing(write={"out.txt": b"broken\n"}, message="feat: out"),
                                       review=work_p4(discovery, repairer=WorkRepairer({"out.txt": b"repaired\n"})))
        review = ReviewStore(self.store)
        consumption = self.consumption(self.head(), record)
        predecessor = [run for run in self.runs() if run != consumption.review_run_id][0]
        batch_id = review.repair_batch_ids()[0]
        self.assertEqual(history.DISPOSITION_REPAIRED,
                         review.read_history(paths.HISTORY_RUNS, predecessor).durable_disposition)
        self.assertEqual(predecessor, review.read_history(paths.HISTORY_REPAIRS, batch_id).source_review_run_id)
        self.assertEqual(p4.P5_POLICY_ID, first_envelope(review, consumption.review_run_id)["policy_id"])
        self.assertEqual(history.DISPOSITION_CONSUMED,
                         review.read_history(paths.HISTORY_RUNS, consumption.review_run_id).durable_disposition)
        self.assertEqual([], history.history_problems(review, work_ids=None))
        self.assertEqual([], self.problems())

    def test_a_p4_only_work_cycle_keeps_the_frozen_terminal_stage_and_k2_delta(self) -> None:
        with p4_only_cycle():
            result, record = self.complete(self.completing(write={"out.txt": b"out\n"}, message="feat: out"),
                                           review=work_p4(Discovery()))
        review = ReviewStore(self.store)
        (run_id,) = self.runs()
        envelope = first_envelope(review, run_id)
        self.assertEqual(p4.POLICY_ID, envelope["policy_id"])
        self.assertNotIn("history_contract", envelope)
        self.assertEqual(["append_event", "append_event", "create_file"], [e["kind"] for e in self.terminal_stage(record)])
        k2 = self.head()
        consumption = self.consumption(k2, record)
        self.assertEqual(sorted([("M", ".workline/events/events.jsonl"),
                                 ("A", paths.consumption_rel(consumption.consumption_id))]), self.delta(k2))
        self.assertFalse((self.root / paths.HISTORY_DIR).exists())
        self.assertEqual([], self.problems())


class _Loaded:
    """A loaded mutation record as ``is_terminal_stage`` reads one (its record and its store)."""

    def __init__(self, store, record: dict) -> None:
        self.store = store
        self.record = record
