"""RB4 / P5 §28.27 / §28.28 / §28.29: history writes are replay-safe, clone-safe and never lifecycle truth.

Interruption and retry at the history boundaries - the process dies right after a generation / stage recorded its
history and before its commit or proof, and the next normal invocation finishes it - proves the same path, the same
bytes and the same IDs, no duplicate and no overwrite. A fresh clone validates every P5 reference without the
runtime area; P5 history alone never stands in for a missing P1-P4 source; LOW / Improvement create no Work.
"""

from __future__ import annotations

from typing import Any

from p5_helpers import committed_paths
from planning_helpers import Crash, crash_at
from test_review_p4_planning import Discovery, P4PlanningCase, Repairer, p4_review, problem
from test_review_p4_work import P4WorkCase, work_p4
from test_work_terminal import Crash as WorkCrash
from workline import roadmap_review as rr
from workline import start as st
from workline.review import history, paths, workcommit
from workline.review.store import ReviewStore

LOW = ("LOW", "low", "a minor wording note")
IMPROVE = ("MID", "improve", "a clearer phase name")


def claims(*items: tuple[str, str, str]) -> tuple:
    from workline.review import p4

    return tuple(p4.P4Claim(*item) for item in items)


def recorded_history(store: Any) -> dict[str, bytes]:
    """The history creates the pending generation mutation recorded (its durable record, before any apply)."""
    from workline.mutation import MutationController

    found: dict[str, bytes] = {}
    for record in MutationController(store).list_pending():
        if (record.get("invocation") or {}).get("operation") != "review-generation":
            continue
        for effect in record.get("effects") or []:
            path = str((effect.get("payload") or {}).get("path"))
            if effect.get("kind") == "create_file" and path.startswith(paths.HISTORY_DIR + "/"):
                found[path] = str(effect["payload"]["content"]).encode("utf-8")
    return found


def history_bytes(store: Any) -> dict[str, bytes]:
    base = store.root / paths.HISTORY_DIR
    return {path.relative_to(store.root).as_posix(): path.read_bytes() for path in sorted(base.rglob("*.yaml"))}


class PlanningBoundaryTests(P4PlanningCase):
    def test_g4_history_interrupted_before_its_commit_is_finished_with_the_same_bytes(self) -> None:
        store = self.planning_project()
        review = p4_review(Discovery(claims(LOW, IMPROVE)))
        with crash_at(rr, "_finish_generation", when=lambda n, s, gen: gen.invocation.get("generation") == 4), \
                self.assertRaises(Crash):
            self.reviewed_p4(store, review)
        before = recorded_history(store)
        self.assertEqual(2, len([path for path in before if "/findings/" in path]), "recorded in the G4 stage")
        self.assertEqual({}, history_bytes(store), "nothing applied before the crash")
        result = self.reviewed_p4(store, p4_review(Discovery(claims(LOW, IMPROVE))))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        after = history_bytes(store)
        self.assertEqual(before, {path: data for path, data in after.items() if path in before}, "no overwrite")
        self.assertEqual(1, len(ReviewStore(store).run_ids()), "no duplicate Run")
        self.assertEqual([], history.history_problems(ReviewStore(store), work_ids=None))

    def test_the_consumption_stage_interrupted_before_km_is_finished_with_the_same_summary(self) -> None:
        store = self.planning_project()
        with crash_at(rr, "_c2_km"), self.assertRaises(Crash):
            self.reviewed_p4(store, p4_review(Discovery(claims(LOW))))
        run = ReviewStore(store).run_ids()[0]
        summary = (store.root / paths.history_run_rel(run)).read_bytes()
        result = self.reviewed_p4(store, p4_review(Discovery(claims(LOW))))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        self.assertEqual(summary, (store.root / paths.history_run_rel(run)).read_bytes())
        self.assertEqual(sorted([paths.history_run_rel(run), paths.consumption_rel(str(result.consumption_id))]),
                         committed_paths(store.root))

    def test_a_repaired_g6_interrupted_before_its_commit_keeps_one_repair_summary(self) -> None:
        store = self.planning_project()
        with crash_at(rr, "_finish_generation", when=lambda n, s, gen: gen.invocation.get("generation") == 6), \
                self.assertRaises(Crash):
            self.reviewed_p4(store, p4_review(Discovery((problem(),), ()), repairer=Repairer()))
        before = recorded_history(store)
        self.assertEqual(1, len([path for path in before if "/repairs/" in path]), "recorded in the G6 stage")
        # the retry's discovery actor sees only the successor's (clean) discovery: the first one already settled
        result = self.reviewed_p4(store, p4_review(Discovery(), repairer=Repairer()))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        after = history_bytes(store)
        self.assertEqual(before, {path: data for path, data in after.items() if path in before})
        self.assertEqual(1, len([path for path in after if "/repairs/" in path]))


class CloneAndCleanupTests(P4PlanningCase):
    def test_runtime_cleanup_and_a_fresh_clone_keep_every_p5_reference_valid(self) -> None:
        store = self.planning_project()
        result = self.reviewed_p4(store, p4_review(Discovery(claims(LOW, IMPROVE))))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        written = history_bytes(store)
        self.runtime_gone(store)
        self.assertEqual(written, history_bytes(store), "deleting .workline/runtime/** removes no history")
        clone = self.fresh_clone(store.root, "clone")
        self.assertEqual(written, history_bytes(clone))
        self.assertEqual([], history.history_problems(ReviewStore(clone), work_ids=None))
        self.assertEqual(history.HISTORY_COMPLETE, history.rb5_reference(
            ReviewStore(clone), str(result.review_run_id), history_contract=history.HISTORY_CONTRACT).history_status)
        # P5 history alone never stands in for a missing P1-P4 source: the summary no longer validates
        (clone.root / paths.adjudication_rel(str(result.review_run_id))).unlink()
        codes = {code for code, _ in history.history_problems(ReviewStore(clone), work_ids=None)}
        self.assertIn(history.PROBLEM_MISSING, codes)

    def test_low_and_improvement_findings_create_no_work(self) -> None:
        store = self.planning_project()
        result = self.reviewed_p4(store, p4_review(Discovery(claims(LOW, IMPROVE))))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        review = ReviewStore(store)
        dispositions = sorted(review.read_history(paths.HISTORY_FINDINGS, f).disposition
                              for f in review.history_ids(paths.HISTORY_FINDINGS))
        self.assertEqual(["future_work_candidate", "retained_history_only"], dispositions)
        self.assertEqual([], store.list_entities("work"), "no Work is created from a LOW or an Improvement")
        self.assertEqual((), review.history_ids(paths.HISTORY_RELATIONS), "and no future_work_link either")


class WorkBoundaryTests(P4WorkCase):
    def test_the_terminal_stage_interrupted_before_k2_is_finished_with_the_same_summary(self) -> None:
        executor = self.completing(write={"out.txt": b"out\n"}, message="feat: out")
        real = workcommit.terminal_commit_effect
        calls: list[int] = []

        def crash_once(*args: Any, **kwargs: Any) -> Any:
            calls.append(1)
            if len(calls) == 1:
                raise WorkCrash()
            return real(*args, **kwargs)

        from unittest import mock

        with mock.patch.object(workcommit, "terminal_commit_effect", side_effect=crash_once), \
                self.assertRaises(WorkCrash):
            st.start(self.store, self.work_id, "single-work", executor, review=work_p4(Discovery()))
        (run_id,) = self.runs()
        summary = (self.root / paths.history_run_rel(run_id)).read_bytes()
        result, record = self.complete(executor, review=work_p4(Discovery()))
        self.assertEqual(summary, (self.root / paths.history_run_rel(run_id)).read_bytes(), "no overwrite")
        consumption = self.consumption(self.head(), record)
        self.assertEqual(sorted([("M", ".workline/events/events.jsonl"),
                                 ("A", paths.consumption_rel(consumption.consumption_id)),
                                 ("A", paths.history_run_rel(run_id))]), self.delta(self.head()))
        self.assertEqual(run_id, consumption.review_run_id)
        self.assertEqual([], history.history_problems(ReviewStore(self.store), work_ids=None))

