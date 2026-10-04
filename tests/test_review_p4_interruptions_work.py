"""P4 §27.36 (Work): the interruption / recovery matrix, rows 1-21 (+ the G-5 adoption instant), over a Work START.

Each row kills the process (``Crash``, a BaseException so neither START's nor a generation mutation's STOP
guard sees it) at one instant of the cycle - Run N finds a blocking Problem, the repair proposal becomes
Candidate N+1, START adopts it, the successor authorizes and the terminal path completes - and then runs the
same START again. Every retry must complete with the same Runs, Finding, Repair Batch and successor IDs the
interrupted attempt reserved; no duplicate raw report, adjudication, Repair Batch / Result, Receipt or
Consumption; the adopted bytes in K1; no v1 fallback or Class A; no newest/timestamp choice.
"""

from __future__ import annotations

from typing import Any

from test_review_p4_interruptions_planning import ByGeneration
from test_review_p4_planning import Adjudicator
from test_review_p4_work import P4WorkCase, WorkRepairer
from test_work_terminal import Crash
from workline import start as st
from workline import start_review as sr
from workline.review import p4, work_review
from workline.review.store import ReviewStore
from unittest import mock

from test_work_review_runtime import git


def review() -> work_review.WorkReviewP4:
    return work_review.WorkReviewP4((ByGeneration().binding(),), Adjudicator().binding(),
                                    WorkRepairer({"out.txt": b"repaired\n"}).binding())


ROWS = (
    (1, sr, "_p4_reserve", True, 1),                      # P4 Run reservation
    (2, sr, "_p4_accept", False, 1),                      # G1 before effect
    (3, sr, "_finish_generation", True, 1),               # G1 commit
    (4, p4, "report_record", True, 1),                    # one discovery return before G2
    (5, sr, "_finish_generation", False, 2),              # raw report creation before G2 completes
    (6, sr, "_finish_generation", True, 2),               # G2 commit
    (7, sr, "_p4_accept_adjudication", True, 1),          # G3 adjudication TaskInput accepted
    (8, p4, "normalize_adjudication", True, 1),           # adjudicator return before G4
    (9, sr, "_finish_generation", False, 4),              # G4 adjudication record creation
    (10, sr, "_finish_generation", True, 4),              # G4 commit
    (11, p4, "repair_batch", True, 1),                    # Repair Batch ID reservation
    (12, sr, "_finish_generation", False, 5),             # G5 Repair Batch / TaskInput partial apply
    (13, sr, "_finish_generation", True, 5),              # G5 commit
    (14, p4, "repair_return_problems", True, 1),          # repair external return before G6
    (15, sr, "_finish_generation", False, 6),             # Candidate N+1 / Repair Result partial apply
    (16, sr, "_finish_generation", True, 6),              # G6 commit
    (17, sr, "_p4_reserve", True, 2),                     # successor reservation
    (18, sr, "_p4_begin_successor", False, 1),            # successor before G1
    (19, p4, "report_record", True, 2),                   # successor discovery cycle
    (20, sr, "_p4_seal", True, 1),                        # P4 G5 seal
    (21, sr, "_terminal", False, 1),                      # existing owner persistence / Consumption
    (22, sr, "_p4_adopt", True, 1),                       # G-5: adopted, before the successor's G1
)


class InterruptionCase(P4WorkCase):
    def interrupted(self, target: Any, name: str, after: bool, call: int) -> None:
        executor = self.completing(write={"out.txt": b"broken\n"}, message="feat: out")
        original = getattr(target, name)
        calls = {"n": 0}

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            calls["n"] += 1
            if calls["n"] != call:
                return original(*args, **kwargs)
            if after:
                original(*args, **kwargs)
            raise Crash(f"crash at {name}")

        with mock.patch.object(target, name, side_effect=wrapper):
            with self.assertRaises(Crash):
                st.start(self.store, self.work_id, "single-work", executor, review=review())
        (pending,) = [record for record in self.pending() if (record.get("invocation") or {}).get("operation") == "start"]
        reserved = dict(pending.get("reserved_ids") or {})
        self.assertEqual(work_review.P4_CONTRACT, pending["invocation"]["review_contract"])
        result, record = self.complete(executor, review=review())
        self.assert_cycle(reserved, record)

    def assert_cycle(self, reserved: dict[str, str], record: dict) -> None:
        review_store = ReviewStore(self.store)
        runs = list(review_store.run_ids())
        self.assertEqual(2, len(runs), "Run N and its one successor, never a third")
        self.assertEqual(2, len(review_store.report_digests()))
        self.assertEqual(sorted(runs), sorted(review_store.adjudication_run_ids()))
        self.assertEqual(1, len(review_store.repair_batch_ids()))
        self.assertEqual(1, len(review_store.repair_result_ids()))
        self.assertEqual(1, len(review_store.receipt_ids()))
        self.assertEqual(1, len(review_store.consumption_ids()))
        for key, identifier in reserved.items():
            if key.startswith(("review-run:", "review-successor-run:")):
                self.assertIn(identifier, runs, f"the retry kept {key}")
            elif key.startswith("review-repair-batch:"):
                self.assertEqual([identifier], list(review_store.repair_batch_ids()))
            elif key.startswith("review-finding:"):
                run_id = key.split(":")[1]
                self.assertIn(identifier, [f["finding_id"] for f in review_store.read_adjudication(run_id).findings])
        k1 = git(self.root, "rev-parse", "HEAD~1")
        self.assertEqual("repaired", git(self.root, "show", f"{k1}:out.txt"))
        self.assertIsNone(record["notes"].get(sr.NOTE_CLASS_A), "never F4 Class A")
        consumption = self.consumption(self.head(), record)
        self.assertEqual(p4.SEAL_GENERATION, consumption.review_generation)


def _make(row: int, target: Any, name: str, after: bool, call: int):
    def test(self: InterruptionCase) -> None:
        self.interrupted(target, name, after, call)

    test.__name__ = f"test_row_{row:02d}_{name.strip('_')}{'_after' if after else ''}_{call}"
    return test


class WorkInterruptionRows01To08(InterruptionCase):
    pass


class WorkInterruptionRows09To15(InterruptionCase):
    pass


class WorkInterruptionRows16To22(InterruptionCase):
    pass


for _row, _target, _name, _after, _call in ROWS:
    _holder = (WorkInterruptionRows01To08 if _row <= 8 else WorkInterruptionRows09To15 if _row <= 15
               else WorkInterruptionRows16To22)
    _test = _make(_row, _target, _name, _after, _call)
    setattr(_holder, _test.__name__, _test)
# A module-level name left bound to a TestCase class is collected again under that name: unbind every loop name.
del _holder, _test, _row, _target, _name, _after, _call
