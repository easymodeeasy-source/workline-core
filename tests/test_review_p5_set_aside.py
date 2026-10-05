"""RB4 / P5 §28.5 / §28.27 item 5 (R-5): a stale P5 predecessor set aside by its replacement's canonical G1.

Each owner has its own path, so each is covered. A P5 Run that was left behind (its owner mutation
lost) and whose Candidate became stale is set aside by the next invocation's new first Run, whose request names
it positively (``set_aside_runs``) and binds its summary (``set_aside_summaries``); the ``set_aside`` Run summary
is written in exactly that replacement's generation 1 (P-6). An older Run whose own final disposition already
exists (``not_authorized``, written by its own G2) is named too, but never gets a ``set_aside`` summary.

The replacement's G1 dies after its generation mutation recorded the summary and before its commit; the retry
writes the same path with the same bytes, once. The predecessor's own records are never rewritten, the
replacement keeps its own state, and the history projection changes no lifecycle state.

Planning: real end to end. Work (residual R-5W): canonical Work recovery discovery (``recovery._work_named``,
landed P4 code) reads only a v1 / v2 Work request, so a P4-family Work Run another (lost) START left behind makes
every later START of that Work ``review_recovery_incomplete`` before any effect (RB3-C1 Option B, fail closed): the
Work owner's set-aside write is not reachable end to end today. ``WorkSetAsideFailClosedTests`` proves that
behaviour on the real production path. ``WorkSetAsideSeamTests`` is TEST-SEAM coverage, not reachable e2e: it
exercises the Work owner's own G1 transition (the write, the retry, exactly one summary, no overwrite) through the
test-only patch ``p4_work_requests_named``, which lets discovery read a P4-family Work request's ``set_aside_runs``.
No runtime code, flag or selector carries that seam.
"""

from __future__ import annotations

from typing import Any
from unittest import mock

from p5_helpers import committed_paths, first_envelope
from planning_helpers import Crash, crash_at, git
from test_review_p4_planning import Discovery, P4PlanningCase, p4_review
from test_review_p4_work import P4WorkCase, work_p4
from test_review_p5_boundaries import history_bytes, recorded_history
from test_work_review_recovery import Upgrade
from test_work_terminal import Crash as WorkCrash
from workline import roadmap_review as rr
from workline import start as st
from workline import start_review as sr
from workline.errors import ReconcileRequired
from workline.mutation import MutationController
from workline.review import history, p4, paths, planning, recovery
from workline.review.store import ReviewStore
from workline.state import ProjectView

LOW = p4.P4Claim("LOW", "low", "a minor wording note")
STALE = planning.STALE_CONTEXT
CHANGED = bytes([10]) + b"changed" + bytes([10])


def changed_authority() -> Any:
    """The planning authority text changed (``registry.md``): every Review Context computed now is another one."""
    real = planning._read_authority
    return mock.patch.object(
        planning, "_read_authority", lambda path: real(path) + (CHANGED if str(path).endswith("registry.md") else b"")
    )


def source_bytes(store: Any, run_id: str) -> dict[str, bytes]:
    """Every record of the Run its own chain names (gates, snapshot, TaskInputs, reports, adjudication, history)."""
    review = ReviewStore(store)
    found = recovery.p4_record_paths(review, run_id, review.gate_chain(run_id))
    return {relative: review.read_bytes(relative) for relative in sorted(set(found))}


def adding_commits(repo: Any, relative: str) -> list[str]:
    """Every commit of HEAD's history that touches ``relative`` (one = written once, never rewritten)."""
    return git(repo, "log", "--format=%H", "--", relative).split()


class SetAsideAssertions:
    """The R-5 facts every owner proves, read from canonical records only."""

    def assert_set_aside(self, store: Any, *, stale: str, final: str, successor: str, recorded: dict[str, bytes],
                         final_bytes: bytes, sources: dict[str, bytes], stale_generations: int,
                         successor_consumed: bool = True) -> None:
        """``successor_consumed``: the replacement went on to its Consumption (else it stands at its own G1)."""
        review = ReviewStore(store)
        summary_rel = paths.history_run_rel(stale)
        # the replacement positively names the predecessor and binds its summary's exact digest
        envelope = first_envelope(review, successor)
        self.assertEqual(sorted([{"review_run_id": final, "reason": planning.SET_ASIDE_NOT_AUTHORIZED},
                                 {"review_run_id": stale, "reason": STALE}], key=lambda item: item["review_run_id"]),
                         envelope["set_aside_runs"])
        self.assertEqual([{"review_run_id": stale, "digest": review.history_digest(paths.HISTORY_RUNS, stale)}],
                         envelope["set_aside_summaries"], "only the predecessor with no final disposition")
        summary = review.read_history(paths.HISTORY_RUNS, stale)
        self.assertEqual((stale, history.DISPOSITION_SET_ASIDE, stale_generations),
                         (summary.review_run_id, summary.durable_disposition, summary.gate_generation))
        # written in exactly the replacement's G1 commit, once, with the bytes its recorded G1 held
        (commit,) = adding_commits(store.root, summary_rel)
        self.assertIn(paths.gate_rel(successor, 1), committed_paths(store.root, commit))
        self.assertIn(summary_rel, committed_paths(store.root, commit))
        self.assertEqual({summary_rel: (store.root / summary_rel).read_bytes()}, recorded,
                         "the retry wrote the same path with the same bytes")
        # the stronger, already-final disposition is never overwritten
        self.assertEqual(final_bytes, (store.root / paths.history_run_rel(final)).read_bytes())
        self.assertEqual(history.DISPOSITION_NOT_AUTHORIZED,
                         review.read_history(paths.HISTORY_RUNS, final).durable_disposition)
        self.assertEqual(1, len(adding_commits(store.root, paths.history_run_rel(final))))
        # exactly one summary per Run, and the predecessor's own records are untouched
        self.assertEqual(tuple(sorted([final, stale] + ([successor] if successor_consumed else []))),
                         review.history_ids(paths.HISTORY_RUNS))
        self.assertEqual(sources, {relative: review.read_bytes(relative) for relative in sources})
        # the replacement keeps its own state: its own chain and policy, and - once consumed - its own summary
        chain = review.gate_chain(successor)
        self.assertEqual(p4.P5_POLICY_ID, envelope["policy_id"])
        if successor_consumed:
            self.assertTrue(chain.generation(p4.SEAL_GENERATION).sealed)
            own = review.read_history(paths.HISTORY_RUNS, successor)
            self.assertEqual((history.DISPOSITION_CONSUMED, successor), (own.durable_disposition, own.review_run_id))
        else:
            self.assertEqual(1, len(chain.generations), "the replacement stands at its own generation 1")
            self.assertFalse(review.history_exists(paths.HISTORY_RUNS, successor), "it has no final disposition yet")
        # the history projection changes no lifecycle state: the predecessor's canonical P4 chain is as it was
        # left, holds no Receipt and no final source fact; set_aside lives only in the replacement's request
        # and in history
        stale_chain = review.gate_chain(stale)
        self.assertEqual(stale_generations, len(stale_chain.generations))
        self.assertEqual(set(), {g.receipt_id for g in stale_chain.generations if g.receipt_id})
        self.assertIsNone(p4.final_disposition(review, stale_chain))
        self.assertEqual(history.HISTORY_COMPLETE, history.rb5_reference(
            review, stale, history_contract=history.HISTORY_CONTRACT).history_status)
        self.assertEqual([], history.history_problems(review, work_ids=None))


class PlanningSetAsideTests(SetAsideAssertions, P4PlanningCase):
    def test_a_stale_p5_planning_run_is_set_aside_in_its_replacement_g1_once_and_a_retry_keeps_the_bytes(self) -> None:
        store = self.planning_project()
        declined = self.reviewed_p4(store, p4_review(Discovery(status="declined")))
        self.assertEqual(rr.STATUS_NOT_AUTHORIZED, declined.status, declined.detail)
        final = str(declined.review_run_id)
        final_bytes = (store.root / paths.history_run_rel(final)).read_bytes()
        with crash_at(rr, "_p4_seal"), self.assertRaises(Crash):
            self.reviewed_p4(store, p4_review(Discovery((LOW,))))
        (stale,) = [run for run in self.runs(store) if run != final]
        review = ReviewStore(store)
        envelope = first_envelope(review, stale)
        self.assertEqual((p4.P5_POLICY_ID, history.HISTORY_CONTRACT), (envelope["policy_id"], envelope["history_contract"]),
                         "the predecessor is P5-capable by its stored policy and history contract")
        self.assertEqual(4, review.gate_chain(stale).latest.generation)
        self.assertFalse((store.root / paths.history_run_rel(stale)).exists(), "no final disposition yet")
        sources = source_bytes(store, stale)
        roadmaps = ProjectView.load(store).roadmaps
        self.runtime_gone(store)  # the owner mutation is lost; the Run stays in history, recoverable in shape
        with changed_authority():  # ... and its Context is stale now
            with crash_at(rr, "_finish_generation", when=lambda n, s, gen: gen.invocation.get("generation") == 1), \
                    self.assertRaises(Crash):
                self.reviewed_p4(store, p4_review(Discovery((LOW,))))
            recorded = recorded_history(store)
            self.assertEqual([paths.history_run_rel(stale)], sorted(recorded), "recorded in the replacement's G1")
            self.assertFalse((store.root / paths.history_run_rel(stale)).exists(), "nothing applied before the crash")
            result = self.reviewed_p4(store, p4_review(Discovery((LOW,))))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        successor = str(result.review_run_id)
        self.assertNotIn(successor, (stale, final))
        self.assert_set_aside(store, stale=stale, final=final, successor=successor, recorded=recorded,
                              final_bytes=final_bytes, sources=sources, stale_generations=4)
        self.assertEqual(result.consumption_id, ReviewStore(store).read_history(paths.HISTORY_RUNS, successor).consumption_id)
        self.assertEqual(len(roadmaps) + 1, len(ProjectView.load(store).roadmaps), "one registration, the replacement's")
        self.assertEqual([], self.problems(store))


def p4_work_requests_named() -> Any:
    """TEST-ONLY seam (R-5W): Work recovery discovery also reads the ``set_aside_runs`` of a P4-family Work request.

    Everything else is the production reader: a v1 / v2 Work request is read exactly as ``recovery._work_named``
    reads it, and the P4-family Run is then classified by the production ``recovery._classify_work_p4``.
    """
    original = recovery._work_named

    def named(review: ReviewStore, found: Any) -> list[str]:
        task_input = review.read_task_input(found.task_id)
        if p4.contract_of_task_input(task_input) == p4.WORK_CONTRACT:
            return [str(item["review_run_id"]) for item in task_input.request_envelope.get("set_aside_runs") or []]
        return original(review, found)

    return mock.patch.object(recovery, "_work_named", named)


class _WorkCase(SetAsideAssertions, P4WorkCase):
    def setUp(self) -> None:
        super().setUp()
        self.executor = self.completing(write={"out.txt": b"out" + bytes([10])}, message="feat: out")

    def lose_start(self) -> str:
        """The pending START's runtime record is lost and its uncommitted result discarded; its Run stays."""
        (record,) = [found for found in self.pending() if (found.get("invocation") or {}).get("operation") == "start"]
        MutationController(self.store).intent_path(record["mutation_id"]).unlink()
        (self.root / "out.txt").unlink(missing_ok=True)
        (run,) = [value for key, value in record["reserved_ids"].items() if key.startswith("review-run:")]
        return run

    def stale_p5_run(self) -> tuple[str, dict[str, bytes]]:
        """A P5 Work Run whose START dies before its discovery launch and is lost."""
        with mock.patch.object(sr, "_p4_launch_discovery", side_effect=WorkCrash()), self.assertRaises(WorkCrash):
            st.start(self.store, self.work_id, "single-work", self.executor, review=work_p4(Discovery()))
        stale = self.lose_start()
        review = ReviewStore(self.store)
        envelope = first_envelope(review, stale)
        self.assertEqual((p4.P5_POLICY_ID, history.HISTORY_CONTRACT), (envelope["policy_id"], envelope["history_contract"]),
                         "the predecessor is P5-capable by its stored policy and history contract")
        self.assertEqual(1, review.gate_chain(stale).latest.generation)
        self.assertFalse((self.root / paths.history_run_rel(stale)).exists(), "no final disposition yet")
        return stale, source_bytes(self.store, stale)


class WorkSetAsideFailClosedTests(_WorkCase):
    """The real production path today: no seam."""

    def test_a_lost_starts_stale_p5_run_stops_a_later_start_before_any_effect_and_no_summary(self) -> None:
        stale, sources = self.stale_p5_run()
        Upgrade().install(self, after_k1=False).on = True  # the implementation changed: that Run's Context is stale
        head, runs = self.head(), self.runs()
        records = [found["mutation_id"] for found in MutationController(self.store).list_records()]
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work", self.executor, review=work_p4(Discovery()))
        self.assertEqual("review_recovery_incomplete", raised.exception.reason, raised.exception)
        self.assertIn(stale, str(raised.exception))
        self.assertEqual((head, runs), (self.head(), self.runs()), "no commit and no Run")
        self.assertEqual(records, [found["mutation_id"] for found in MutationController(self.store).list_records()],
                         "no START mutation is opened")
        self.assertFalse((self.root / paths.history_run_rel(stale)).exists(), "no set_aside summary is written")
        self.assertEqual(sources, {relative: ReviewStore(self.store).read_bytes(relative) for relative in sources},
                         "the predecessor's records are untouched")
        self.assertEqual([], history.history_problems(ReviewStore(self.store), work_ids=None))


class WorkSetAsideSeamTests(_WorkCase):
    """TEST-SEAM coverage of the Work owner's G1 set-aside transition (not reachable end to end today, R-5W)."""

    def test_seam_the_work_owner_sets_a_stale_p5_run_aside_in_its_replacement_g1_once_and_a_retry_keeps_the_bytes(
        self,
    ) -> None:
        with p4_work_requests_named():
            with self.assertRaises(ReconcileRequired):
                st.start(self.store, self.work_id, "single-work", self.executor,
                         review=work_p4(Discovery(status="declined")))
            final = self.lose_start()
            final_bytes = (self.root / paths.history_run_rel(final)).read_bytes()
            stale, sources = self.stale_p5_run()
            Upgrade().install(self, after_k1=False).on = True  # the implementation changed: that Run is stale
            real = sr._finish_generation

            def crash_before_g1_commit(store: Any, gen: Any) -> str:
                if (gen.invocation or {}).get("generation") == 1:
                    raise WorkCrash("before the replacement's G1 commit")
                return real(store, gen)

            with mock.patch.object(sr, "_finish_generation", side_effect=crash_before_g1_commit), \
                    self.assertRaises(WorkCrash):
                st.start(self.store, self.work_id, "single-work", self.executor, review=work_p4(Discovery()))
            recorded = recorded_history(self.store)
            self.assertEqual([paths.history_run_rel(stale)], sorted(recorded), "recorded in the replacement's G1")
            self.assertFalse((self.root / paths.history_run_rel(stale)).exists(), "nothing applied before the crash")
            (record,) = [found for found in self.pending() if (found.get("invocation") or {}).get("operation") == "start"]
            (successor,) = [value for key, value in record["reserved_ids"].items() if key.startswith("review-run:")]
            head = self.head()
            # the retry finishes exactly that G1 (and dies at the replacement's discovery launch, which bounds the
            # case: the terminal path of a P5 Work Run is covered by test_review_p5_work)
            with mock.patch.object(sr, "_p4_launch_discovery", side_effect=WorkCrash()), self.assertRaises(WorkCrash):
                st.start(self.store, self.work_id, "single-work", self.executor, review=work_p4(Discovery()))
        self.assertNotIn(successor, (stale, final))
        self.assertEqual([paths.history_run_rel(stale)],
                         [path for path in committed_paths(self.root) if path.startswith(paths.HISTORY_DIR + "/")],
                         "the retry's one new commit is the replacement's G1, carrying the summary")
        self.assertEqual(head, git(self.root, "rev-parse", "HEAD~1").strip())
        self.assert_set_aside(self.store, stale=stale, final=final, successor=successor, recorded=recorded,
                              final_bytes=final_bytes, sources=sources, stale_generations=1, successor_consumed=False)
        self.assertEqual([], self.problems())
