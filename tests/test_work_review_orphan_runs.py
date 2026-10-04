"""RB3-C1 repair (R-2): §11.12 on EVERY review-v1 Work Review invocation (``WORKLINE_COMPLETION_SPRINT.md`` §11.6, §11.12).

The Work operation identity has no mutation id, time or mode in it, so a Run another START of the same Work
began - a START whose runtime record was lost - is a matching Run of every later START of that Work. These
tests hold that every invocation classifies them, and that only the invocation's own reserved Runs are its
selector's:

* T1  a fresh START beside a recoverable Run of a lost START stops (``review_recovery_unbound_run``) before
      its mutation opens: no record, no reservation, no write, and the executor never runs;
* T2  a fresh START beside only non-resumable older Runs (a not-authorized one and a stale one) proceeds, and
      its first Run's request names each with the reason it is set aside;
* T3  a first-Run-only resume beside another recoverable Run stops (``review_recovery_ambiguous``) and writes
      nothing;
* T4  a first-Run-only resume beside only non-resumable older Runs continues to completion;
* T5  an ordinary START with no older Run names nothing: its request is exactly the f8f1af7 request
      (``set_aside_runs: []``), byte for byte;
* T6  a Class-A successor names its predecessor as its replacement and the older non-resumable Run with its
      own reason, and the adopted-result proof accepts it.
"""

from __future__ import annotations

from unittest import mock

from test_work_review_recovery import AdoptionCase, Upgrade
from test_work_review_runtime import Reviewer
from test_work_terminal import Crash

from workline import start as st
from workline import start_review
from workline.errors import ReconcileRequired
from workline.mutation import MutationController
from workline.review import serialize, validate, work_review
from workline.review.store import ReviewStore


class OrphanCase(AdoptionCase):
    remote = False

    # --- fixtures: Runs a lost START left behind ------------------------------------------------
    def start_records(self) -> list[dict]:
        return [r for r in self.pending() if (r.get("invocation") or {}).get("operation") == "start"]

    def first_run_of(self, record: dict) -> str:
        (run,) = [v for k, v in record["reserved_ids"].items() if k.startswith("review-run:work-result-v1:")]
        return run

    def lose_start(self) -> str:
        """The pending START's runtime record is lost; the Run its generation commits made stays in history."""
        (record,) = self.start_records()
        MutationController(self.store).intent_path(record["mutation_id"]).unlink()
        self.assertEqual(self.start_records(), [])
        return self.first_run_of(record)

    def to_generation_1(self, reviewer=None) -> None:
        """A review-v1 START of the (empty-artifact) Work that dies right after its generation 1."""
        with mock.patch.object(start_review, "_launch_and_settle", side_effect=Crash()), self.assertRaises(Crash):
            st.start(self.store, self.work_id, "single-work", self.completing(), review=self.review(reviewer))

    def orphan_at_generation_1(self) -> str:
        self.to_generation_1()
        return self.lose_start()

    def not_authorized_orphan(self) -> str:
        finding = work_review.WorkReviewFinding("HIGH", "blocking", "not acceptable")
        with self.assertRaises(ReconcileRequired):
            st.start(self.store, self.work_id, "single-work", self.completing(),
                     review=self.review(Reviewer(findings=(finding,))))
        return self.lose_start()

    def request_of(self, run_id: str) -> dict:
        review = ReviewStore(self.store)
        first = review.gate_chain(run_id).generations[0]
        return review.read_task_input(str(first.accepted_tasks[0]["task_id"])).request_envelope

    def nothing_written_since(self, head: str, records: list, runs: tuple) -> None:
        self.assertEqual(self.head(), head)
        self.assertEqual([r["mutation_id"] for r in MutationController(self.store).list_records()], records)
        self.assertEqual(ReviewStore(self.store).run_ids(), runs)

    def snapshot(self) -> tuple:
        return (self.head(), [r["mutation_id"] for r in MutationController(self.store).list_records()],
                ReviewStore(self.store).run_ids())

    def recording_executor(self, ran: list):
        def execute(ctx):
            ran.append(ctx.work.id)
            return st.Completed()

        return execute


class FreshStartTests(OrphanCase):
    def test_t1_a_recoverable_run_of_a_lost_start_is_unbound_and_nothing_is_begun(self) -> None:
        orphan = self.orphan_at_generation_1()
        before = self.snapshot()
        ran: list[str] = []
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work", self.recording_executor(ran), review=self.review())
        self.assertEqual(raised.exception.reason, "review_recovery_unbound_run")
        self.assertIn(orphan, str(raised.exception))
        self.assertEqual(ran, [], "the executor never ran")
        self.assertEqual(self.reviewer.tasks, [], "no reviewer was called")
        self.nothing_written_since(*before)  # no mutation record (not even an abandoned one), no Run, no commit

    def test_t2_only_non_resumable_older_runs_are_named_by_the_new_first_run(self) -> None:
        not_authorized = self.not_authorized_orphan()
        stale = self.orphan_at_generation_1()
        # the second START's own first Run already named the older, not-authorized one
        self.assertEqual(self.request_of(stale)["set_aside_runs"],
                         [{"review_run_id": not_authorized, "reason": "not_authorized"}])
        Upgrade().install(self, after_k1=False).on = True  # the implementation changed: that Run's Context is stale
        result = st.start(self.store, self.work_id, "single-work", self.completing(), review=self.review())
        self.assertEqual(result.status, "completed")
        record = self.captured[-1]
        named = self.request_of(self.first_run_of(record))["set_aside_runs"]
        self.assertEqual(named, sorted([
            {"review_run_id": not_authorized, "reason": "not_authorized"},
            {"review_run_id": stale, "reason": "review_context_changed"},
        ], key=lambda item: item["review_run_id"]))
        self.assertEqual(validate.validate_review(self.store), [])

    def test_t5_an_ordinary_start_names_nothing_and_its_request_bytes_are_the_f8f1af7_ones(self) -> None:
        self.to_generation_1()
        run = self.first_run_of(self.start_records()[0])
        envelope = self.request_of(run)
        self.assertEqual((envelope["version"], envelope["set_aside_runs"]), (2, []))
        # exactly what f8f1af7 built for an ordinary first Run: request_envelope(candidate, context, [], ...)
        rebuilt = work_review.request_envelope(envelope["candidate"], envelope["context"], [], review_run_id=run)
        self.assertEqual(serialize.canonical_bytes(rebuilt), serialize.canonical_bytes(envelope))
        review = ReviewStore(self.store)
        task = review.read_task_input(str(review.gate_chain(run).generations[0].accepted_tasks[0]["task_id"]))
        self.assertEqual(task.request_digest, serialize.digest(rebuilt))


class FirstRunResumeTests(OrphanCase):
    def test_t3_a_first_run_resume_beside_another_recoverable_run_stops_and_writes_nothing(self) -> None:
        self.to_generation_1()  # this START's own first Run, at generation 1
        (own,) = self.start_records()
        path = MutationController(self.store).intent_path(own["mutation_id"])
        saved = path.read_bytes()
        path.unlink()  # another clone / session no longer sees it ...
        Upgrade().install(self, after_k1=False).on = True  # ... its Run is stale there, so a fresh START proceeds
        self.to_generation_1()
        other = self.lose_start()  # ... and that START's runtime is lost: its Run is recoverable (current)
        path.write_bytes(saved)  # the own record is back
        before = self.snapshot()
        ran: list[str] = []
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work", self.recording_executor(ran), review=self.review())
        self.assertEqual(raised.exception.reason, "review_recovery_ambiguous")
        self.assertIn(other, str(raised.exception))
        self.assertEqual(ran, [])
        self.assertEqual(path.read_bytes(), saved, "the own START record is left exactly as it was")
        self.nothing_written_since(*before)

    def test_t4_a_first_run_resume_beside_only_non_resumable_older_runs_continues(self) -> None:
        not_authorized = self.not_authorized_orphan()
        self.to_generation_1()
        (own,) = self.start_records()
        run = self.first_run_of(own)
        self.assertEqual(self.request_of(run)["set_aside_runs"],
                         [{"review_run_id": not_authorized, "reason": "not_authorized"}])
        result = self.resume()
        self.assertEqual(result.status, "completed")
        self.assertEqual(self.first_run_of(self.captured[-1]), run, "the own first Run is the one completed")
        self.assertEqual(self.pending(), [])


class SuccessorNamingTests(OrphanCase):
    def test_t6_the_successor_names_its_predecessor_and_every_older_non_resumable_run(self) -> None:
        not_authorized = self.not_authorized_orphan()
        Upgrade().install(self)  # A2 after K1
        result, record = self.complete(self.completing(write={"out.txt": b"out\n"}))
        self.assertEqual(result.status, "completed")
        older = ({"review_run_id": not_authorized, "reason": "not_authorized"},)
        ids = self.assert_adopted(record, remote=False, older=older)
        self.assertEqual(self.request_of(ids["initial"])["set_aside_runs"], list(older))
