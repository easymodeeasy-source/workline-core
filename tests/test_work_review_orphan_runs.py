"""RB3-C1 repair: §11.12 on EVERY review-v1 Work Review invocation (``WORKLINE_COMPLETION_SPRINT.md`` §11.6, §11.12).

The Work operation identity has no mutation id, time or mode in it, so a Run another START of the same Work
began is a matching Run of every later START of that Work. A Work Run is resumed only from the record of the
START mutation that reserved it (``skills/start``: resume), and what its remaining stages need - its reserved
IDs, its generation mutations' owner, the ownership witnesses and pre-existing-dirty snapshot its Candidate was
frozen under, its S-c0 / S-c1 commits, its terminal stage - is in that record alone. So a Run of a recoverable
shape that no pending START mutation of the Work holds is incomplete, and these tests hold that:

* T1  a fresh START beside such a Run of a lost START (generation 1, current) stops
      (``review_recovery_incomplete``) before its mutation opens: no record, no reservation, no write, and the
      executor never runs; T1b the same for a sealed, result-bearing one, whose bytes are left as they are;
* T2  a fresh START beside only non-resumable older Runs (a not-authorized one and a stale one) proceeds, and
      its first Run's request names each with the reason it is set aside;
* T3  a first-Run-only resume beside another START's Run of a recoverable shape stops
      (``review_recovery_incomplete``) and writes nothing;
* T4  a first-Run-only resume beside only non-resumable older Runs continues to completion without running
      the executor again, and makes one Run, one Receipt and one Consumption of its own and no Supersession;
* T5  an ordinary START with no older Run names nothing: its request is exactly the f8f1af7 request
      (``set_aside_runs: []``), byte for byte;
* T6  a Class-A successor names its predecessor as its replacement and the older non-resumable Run with its
      own reason, and the adopted-result proof accepts it;
* T7  a Run another mode's pending START holds is left to that START: opening refuses on the existing
      write-scope conflict, nothing begins beside it, and its own START then resumes it;
* T8  at the discovery core: two recoverable Runs are ``review_recovery_ambiguous`` (the closest reachable form:
      the live model never holds two), and a Run the held set does not own is incomplete;
* T9  a START that began its Run is never abandoned on a STOP, even with no recorded effect (a Work already in
      progress with its target records no lifecycle effect): (a) a reviewer error keeps it pending and the next
      START relaunches the same task and completes, (b) a settlement that does not authorize stops the same way
      again on every retry, as for an unstarted Work, (c) a STOP before any Run began still abandons.
"""

from __future__ import annotations

from unittest import mock

from test_work_review_recovery import AdoptionCase, Upgrade
from test_work_review_runtime import Reviewer, git
from test_work_terminal import Crash

from workline import start as st
from workline import start_review
from workline.errors import ReconcileRequired, StopError
from workline.ids import new_id
from workline.mutation import MutationController, utc_now
from workline.review import paths as review_paths
from workline.review import recovery, serialize, validate, work_review
from workline.review.store import ReviewStore
from workline.state import IN_PROGRESS, ProjectView
from workline.store import Event, render_event_line

#: The phrase the Work recovery policy states for a Run of a recoverable shape no pending START holds.
UNOWNED = "no pending START mutation of this Work holds it"


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

    def own_run_beside_a_lost_starts_current_run(self) -> tuple[dict, bytes, str]:
        self.to_generation_1()  # this START's own first Run, at generation 1
        (own,) = self.start_records()
        path = MutationController(self.store).intent_path(own["mutation_id"])
        saved = path.read_bytes()
        path.unlink()  # another clone / session no longer sees it ...
        Upgrade().install(self, after_k1=False).on = True  # ... its Run is stale there, so a fresh START proceeds
        self.to_generation_1()
        other = self.lose_start()  # ... and that START's runtime is lost: its Run has a recoverable (current) shape
        path.write_bytes(saved)  # the own record is back
        return own, saved, other

    def assert_incomplete_refusal(self, refused: ReconcileRequired, run_id: str) -> None:
        self.assertEqual(refused.reason, "review_recovery_incomplete")
        self.assertIn(run_id, str(refused))
        self.assertIn(UNOWNED, str(refused))


class FreshStartTests(OrphanCase):
    def test_t1_a_recoverable_shaped_run_no_pending_start_holds_is_incomplete_and_nothing_is_begun(self) -> None:
        orphan = self.orphan_at_generation_1()
        before = self.snapshot()
        ran: list[str] = []
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work", self.recording_executor(ran), review=self.review())
        self.assert_incomplete_refusal(raised.exception, orphan)
        self.assertEqual(ran, [], "the executor never ran")
        self.assertEqual(self.reviewer.tasks, [], "no reviewer was called")
        self.nothing_written_since(*before)  # no mutation record (not even an abandoned one), no Run, no commit

    def test_t1b_a_sealed_result_bearing_run_of_a_lost_start_is_incomplete_and_its_bytes_are_left(self) -> None:
        with mock.patch.object(start_review, "_result_commit", side_effect=Crash()), self.assertRaises(Crash):
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                     review=self.review())
        orphan = self.lose_start()
        chain = ReviewStore(self.store).gate_chain(orphan)
        self.assertEqual((chain.latest.generation, chain.latest.sealed), (3, True), "sealed, unconsumed, no K1")
        produced = (self.root / "out.txt").read_bytes()
        before = self.snapshot()
        ran: list[str] = []
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work", self.recording_executor(ran), review=self.review())
        self.assert_incomplete_refusal(raised.exception, orphan)
        self.assertEqual(ran, [])
        self.assertEqual((self.root / "out.txt").read_bytes(), produced, "the lost START's bytes are left as they are")
        self.nothing_written_since(*before)

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
    def test_t3_a_first_run_resume_beside_another_starts_recoverable_shaped_run_stops_and_writes_nothing(self) -> None:
        own, saved, other = self.own_run_beside_a_lost_starts_current_run()
        path = MutationController(self.store).intent_path(own["mutation_id"])
        before = self.snapshot()
        ran: list[str] = []
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work", self.recording_executor(ran), review=self.review())
        self.assert_incomplete_refusal(raised.exception, other)
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
        result = self.resume()  # its executor raises if it runs: the resumed Run is not produced again
        self.assertEqual(result.status, "completed")
        self.assertEqual(self.first_run_of(self.captured[-1]), run, "the own first Run is the one completed")
        self.assertEqual(self.pending(), [])
        # nothing duplicated: one Run of its own beside the older one, one Receipt, one Consumption, no Supersession,
        # one completion
        review = ReviewStore(self.store)
        self.assertEqual(sorted(review.run_ids()), sorted([not_authorized, run]))
        self.assertEqual(review.receipt_ids(), (review.gate_chain(run).generation(3).receipt_id,))
        self.assertEqual(len(review.consumption_ids()), 1)
        self.assertEqual(list((self.root / review_paths.SUPERSESSIONS_DIR).glob("*")), [])
        self.assertEqual([event["type"] for event in self.events_for("HEAD")].count("work_completed"), 1)


class OtherStartTests(OrphanCase):
    def test_t7_a_run_another_modes_pending_start_holds_is_left_to_it_and_nothing_begins(self) -> None:
        self.to_generation_1()  # a single-work START holds its Run at generation 1
        (held,) = self.start_records()
        path = MutationController(self.store).intent_path(held["mutation_id"])
        saved = path.read_bytes()
        before = self.snapshot()
        ran: list[str] = []
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "outer", self.recording_executor(ran), review=self.review())
        self.assertIn("overlaps the planned write scope", str(raised.exception))  # the existing slot conflict
        self.assertEqual(ran, [])
        self.assertEqual(path.read_bytes(), saved)
        self.nothing_written_since(*before)
        # the START that holds it resumes it: the one recoverable Run, continued by its owner
        result = self.resume()
        self.assertEqual(result.status, "completed")
        self.assertEqual(ReviewStore(self.store).run_ids(), (self.first_run_of(held),))


class DiscoveryCoreTests(OrphanCase):
    def test_t8_two_recoverable_runs_are_ambiguous_and_a_run_no_held_set_owns_is_incomplete(self) -> None:
        own, _, other = self.own_run_beside_a_lost_starts_current_run()
        mine = self.first_run_of(own)
        identity = work_review.operation_identity(self.work_id)
        current = lambda found: start_review._Currency(True, False, "current")  # noqa: E731 - both Contexts current
        # the closest reachable form of "several recoverable": the shared core over these two real Runs with a
        # policy that sets neither aside (the live Work policy cannot: the other's request names this one, and a
        # Run is recoverable only through the one pending START that holds it)
        permissive = recovery.RecoveryAdapter(shape=recovery._work_shape_problem, named=lambda review, found: [],
                                              classify=lambda *args: None)
        with self.assertRaises(ReconcileRequired) as raised:
            recovery._discover(self.store, work_review.REVIEW_KIND, identity, current, permissive)
        self.assertEqual(raised.exception.reason, "review_recovery_ambiguous")
        self.assertIn(mine, str(raised.exception))
        self.assertIn(other, str(raised.exception))
        # the live Work policy over the same two Runs with neither held: the one the other names is set aside
        found = recovery.discover_work(self.store, identity, currency=current, owned={mine, other})
        self.assertEqual(found.recoverable.review_run_id, other)
        self.assertEqual(found.set_aside, ({"review_run_id": mine, "reason": "set_aside"},))
        # START's form: the pending START's own Run held, the other Run owned by no pending START
        with self.assertRaises(ReconcileRequired) as raised:
            recovery.discover_work(self.store, identity, currency=current, owned={mine}, held={mine})
        self.assert_incomplete_refusal(raised.exception, other)
        # owned by a pending START: recoverable, the one to continue
        found = recovery.discover_work(self.store, identity, currency=current, owned={mine, other}, held={mine})
        self.assertEqual((found.recoverable.review_run_id, found.set_aside), (other, ()))
        with self.assertRaises(ValueError):
            recovery.discover_work(self.store, identity, currency=current, owned=(), held={mine})


class SuccessorNamingTests(OrphanCase):
    def test_t6_the_successor_names_its_predecessor_and_every_older_non_resumable_run(self) -> None:
        not_authorized = self.not_authorized_orphan()
        Upgrade().install(self)  # A2 after K1
        result, record = self.complete(self.completing(write={"out.txt": b"out\n"}))
        self.assertEqual(result.status, "completed")
        older = ({"review_run_id": not_authorized, "reason": "not_authorized"},)
        ids = self.assert_adopted(record, remote=False, older=older)
        self.assertEqual(self.request_of(ids["initial"])["set_aside_runs"], list(older))


class StopKeepsBegunRunMixin:
    """(b): a settlement that does not authorize stops every retry the same way, and no new Run begins."""

    def assert_not_authorized_stops_the_same_way_on_every_retry(self) -> None:
        finding = work_review.WorkReviewFinding("HIGH", "blocking", "not acceptable")
        reviewer = Reviewer(findings=(finding,))
        with self.assertRaises(ReconcileRequired) as first:
            st.start(self.store, self.work_id, "single-work", self.completing(), review=self.review(reviewer))
        (record,) = self.start_records()
        run = self.first_run_of(record)
        with self.assertRaises(ReconcileRequired) as again:
            st.start(self.store, self.work_id, "single-work", self.never, review=self.review(reviewer))
        self.assertEqual((again.exception.reason, str(again.exception)), (first.exception.reason, str(first.exception)))
        (still,) = self.start_records()
        self.assertEqual(still["mutation_id"], record["mutation_id"], "the same record, still pending")
        self.assertEqual(ReviewStore(self.store).run_ids(), (run,), "no new Run")
        self.assertEqual(len(reviewer.tasks), 1, "a settled task is not launched again")
        self.assertEqual(ReviewStore(self.store).receipt_ids(), ())


class InProgressStopTests(StopKeepsBegunRunMixin, OrphanCase):
    """T9 on a Work already in progress with its target (an earlier cycle committed its opening events)."""

    def prepare(self) -> None:
        log = self.root / ".workline" / "events" / "events.jsonl"
        held = log.read_bytes()
        lines = "".join(render_event_line(Event(new_id("event"), kind, self.work_id, utc_now())) + "\n"
                        for kind in ("work_started", "work_target_added"))
        separator = b"" if not held or held.endswith(b"\n") else b"\n"
        log.write_bytes(held + separator + lines.encode("utf-8"))
        git(self.root, "add", "--", ".workline/events/events.jsonl")
        git(self.root, "commit", "-m", "an earlier cycle opened the Work", "--no-verify")

    def setUp(self) -> None:
        super().setUp()
        state = ProjectView.load(self.store).work_state(self.work_id)
        self.assertEqual((state.state, state.has_target), (IN_PROGRESS, True))

    def test_t9a_a_reviewer_error_keeps_the_start_pending_and_the_next_start_relaunches_the_same_task(self) -> None:
        failed: list[str] = []

        def fail_once(task):
            if not failed:
                failed.append(task.task_id)
                raise RuntimeError("the reviewer service is down")

        reviewer = Reviewer(before=fail_once)
        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                     review=self.review(reviewer))
        self.assertEqual(raised.exception.code, "review_reviewer_failed")
        (record,) = self.start_records()
        self.assertEqual((record["status"], record["effects"]), ("pending", []), "no effect, and still pending")
        run = self.first_run_of(record)
        # the next START: the same record, the same Run, the same task to the same reviewer identity
        result = st.start(self.store, self.work_id, "single-work", self.never, review=self.review(reviewer))
        self.assertEqual((result.status, result.mutation_id), ("completed", record["mutation_id"]))
        self.assertEqual([task.task_id for task in reviewer.tasks], [failed[0], failed[0]])
        self.assertEqual(reviewer.tasks[0], reviewer.tasks[1], "the very task, relaunched")
        self.assertEqual(self.first_run_of(self.captured[-1]), run)
        review = ReviewStore(self.store)
        self.assertEqual(review.run_ids(), (run,))
        self.assertEqual(len(review.receipt_ids()), 1)
        self.assertEqual(len(review.consumption_ids()), 1)
        self.assertEqual(len(list((self.root / review_paths.CANDIDATE_SNAPSHOTS_DIR).glob("*"))), 1, "no new Candidate")
        self.assertEqual(self.pending(), [])

    def test_t9b_a_settlement_that_does_not_authorize_stops_the_same_way_on_every_retry(self) -> None:
        self.assert_not_authorized_stops_the_same_way_on_every_retry()

    def test_t9c_a_stop_before_any_run_began_still_abandons(self) -> None:
        def stop(ctx):
            raise StopError("the executor stopped", code="executor_stopped")

        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", stop, review=self.review())
        self.assertEqual(raised.exception.code, "executor_stopped")
        self.assertEqual(self.start_records(), [])
        (record,) = [r for r in MutationController(self.store).list_records()
                     if (r.get("invocation") or {}).get("operation") == "start"]
        self.assertEqual((record["status"], record["effects"]), ("abandoned", []))
        self.assertEqual(ReviewStore(self.store).run_ids(), ())


class UnstartedStopTests(StopKeepsBegunRunMixin, OrphanCase):
    """T9b's twin on an unstarted Work, whose START records ``work_started`` and so was always kept pending."""

    def test_t9b_unstarted_a_settlement_that_does_not_authorize_stops_the_same_way_on_every_retry(self) -> None:
        self.assert_not_authorized_stops_the_same_way_on_every_retry()
