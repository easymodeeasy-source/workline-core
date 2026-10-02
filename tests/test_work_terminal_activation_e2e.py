"""Gate 3 end to end: a disposable Project that starts unactivated, is activated by the real producer, and runs.

Every Project here is a scratch Project made for the test. No real Project is
activated, and the Workline implementation repository never is (self-hosting
stays refused, ``test_work_terminal_activation``).

```text
A  result-bearing  legacy START works; a review-v1 START is refused review_not_activated with
                   nothing begun; the human-confirmed activation commits (and pushes) its record;
                   a review-v1 START then runs Candidate ... K1 ... Consumption ... K2 to completed
B  empty artifact  no K1 anywhere, an "empty" Consumption, K2 the only push
C  legacy after    a legacy START still completes, unmarked and unconsumed, and a review-v1 START
   activation      after it still proves the same immutable record against the later HEAD
D  no migration    every pre-activation Event, Work and record is left exactly as it was
```

with and without a remote, the START entry pins of F1 §6.4 (malformed, unknown and
non-reproducing activations fail closed; activation never selects review-v1), and the
totality allowance of F1 §10.2 driven by real interrupted terminal stages.
"""

from __future__ import annotations

import json
from unittest import mock

from helpers import completing_executor, scripted_executor
from test_work_review_runtime import git, git_bytes
from test_work_terminal import TerminalCase

from workline import gitops
from workline import start as st
from workline import start_review
from workline import work_terminal_activation as wta
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.mutation import MutationController
from workline.review import paths as review_paths
from workline.review import records, serialize, workcommit
from workline.review import validate as review_validate
from workline.review.store import ReviewStore
from workline.review.validate import validate_review
from workline.state import ProjectView
from workline.validate import validate_project

REL = review_paths.WORK_TERMINAL_ACTIVATION_REL
EVENTS = ".workline/events/events.jsonl"
TOTALITY = (
    review_validate.ACTIVATION_PREFIX_MISMATCH,
    review_validate.COMPLETION_MARKER_INVALID,
    review_validate.COMPLETION_MARKER_CONTRADICTION,
    review_validate.COMPLETION_UNCONSUMED,
    review_validate.CONSUMPTION_UNBOUND,
)


class Crash(BaseException):
    """A process death at a chosen instant."""


class Gate3Case(TerminalCase):
    """A scratch Project with three Works, the form-L rule committed, and NO activation until the producer runs."""

    remote = True

    def simple_entry(self, store, phase_id, works=None, **kwargs):
        return super().simple_entry(store, phase_id, works or {"w1": "W1 done", "w2": "W2 done", "w3": "W3 done"}, **kwargs)

    def activate(self) -> None:
        """The fixture of the pre-activation batches is not used: activation comes from the producer only."""
        self.activation = None

    def setUp(self) -> None:
        super().setUp()
        self.works = dict(self.phase_entry.work_ids)
        self.assertIsNone(ReviewStore(self.store).read_activation())

    # --- helpers ---------------------------------------------------------------
    def produce(self) -> wta.ActivationResult:
        result = wta.activate_work_terminal_review(self.root, confirmed=True)
        self.assertEqual(result.status, "activated")
        return result

    def legacy(self, work_id: str) -> st.StartResult:
        result = st.start(self.store, work_id, "single-work", completing_executor(self.store))
        self.assertEqual(result.status, "completed", result)
        return result

    def reviewed(self, work_id: str, executor) -> tuple[st.StartResult, dict]:
        self.captured.clear()
        result = st.start(self.store, work_id, "single-work", executor, review=self.review())
        self.assertEqual(result.status, "completed", result)
        (record,) = self.captured
        return result, record

    def remote_ref(self) -> str:
        return git(self.remote_path(), "rev-parse", "--verify", "-q", "refs/heads/main", check=False) if self.remote else ""

    def completions(self, commit: str = "HEAD") -> dict[str, dict]:
        log = git_bytes(self.root, "show", f"{commit}:{EVENTS}").decode("utf-8")
        return {e["entity"]: e for e in (json.loads(line) for line in log.splitlines() if line.strip())
                if e["type"] == "work_completed"}

    def record_at(self, commit: str) -> bytes:
        return git_bytes(self.root, "show", f"{commit}:{REL}")

    def totality(self) -> list[str]:
        return [problem.code for problem in validate_review(self.store) if problem.code in TOTALITY]

    def reviewed_candidate(self, record: dict) -> dict:
        """The Candidate a completed Run froze, read back from its committed snapshot."""
        (run_id,) = [v for k, v in record["reserved_ids"].items() if k.startswith("review-run:work-result-v1:")]
        first = ReviewStore(self.store).gate_chain(run_id).generations[0]
        return ReviewStore(self.store).read_candidate_snapshot(first.candidate_hash).material["candidate"]


# --------------------------------------------------------------------------- A: the result-bearing Work


class ResultBearingGate3Tests(Gate3Case):
    def test_a_result_bearing_work_runs_the_whole_gate_3_path(self) -> None:
        w1, w2 = self.works["w1"], self.works["w2"]
        # legacy START works in the unactivated Project
        self.legacy(w2)
        self.assertNotIn("operation_contract", self.completions()[w2])
        # an explicit review-v1 START is refused at entry: nothing begun, nothing written, nothing sent
        head, remote, called = self.head(), self.remote_ref(), []
        with self.assertRaises(StopError) as raised:
            st.start(self.store, w1, "single-work", lambda ctx: called.append("run") or st.Completed(),
                     review=self.review())
        self.assertEqual(raised.exception.code, "review_not_activated")
        self.assertEqual((called, self.pending(), self.head(), self.remote_ref()), ([], [], head, remote))
        self.assertFalse(ReviewStore(self.store).exists(), "no Review Run, record or namespace was begun")
        # the human-confirmed activation: one commit, pushed to the approved destination
        activation = self.produce()
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), wta.ACTIVATION_COMMIT_MESSAGE)
        self.assertEqual((activation.pushed, self.remote_ref()), (True, activation.head))
        self.assertEqual(activation.activation_base_head, head)
        self.assertEqual(validate_project(self.store), [])
        # the review-v1 START runs Candidate, Review, Receipt, K1, its proof and push, the terminal stage,
        # the Consumption, K2, its proof and push, and completes
        _, record = self.reviewed(w1, self.completing(write={"out.txt": b"out\n"}, message="feat: out"))
        k2 = self.head()
        k1 = git(self.root, "rev-parse", "HEAD~1")
        self.assertEqual(self.delta(k1), [("A", "out.txt")])
        consumption = self.consumption(k2, record)
        self.assertEqual((consumption.artifact_kind, consumption.authorized_result_commit_sha), ("result_commit", k1))
        notes = record["notes"]
        self.assertEqual(notes["review_work_result_proof"]["result_commit"], k1)
        self.assertEqual(notes["review_work_terminal_proof"]["terminal_commit"], k2)
        self.assertEqual([push["payload"]["commit"] for push in self.pushes(record)], [k1, k2])
        self.assertEqual(self.remote_ref(), k2)
        completed = self.completions()[w1]
        self.assertEqual((completed["operation_contract"], completed["review_generation"]), ("review-v1", 3))
        self.assertEqual(consumption.terminal_event_id, completed["id"])
        self.assertEqual(ProjectView.load(self.store).work_state(w1).state, "completed")
        # the Candidate W9 re-derived at its base and at parent(K1) carries the Work's desired state (F2 §5.3)
        self.assertEqual(self.reviewed_candidate(record)["declared_base"]["work"]["desired_state"], "W1 done")
        # the activation is the same immutable record, and the Project validates, totality included
        self.assertEqual(self.record_at(k2), self.record_at(activation.head))
        self.assertEqual(validate_project(self.store), [])


class NoRemoteGate3Tests(Gate3Case):
    remote = False

    def test_without_a_remote_activation_and_a_review_v1_completion_are_local(self) -> None:
        activation = self.produce()
        self.assertFalse(activation.pushed)
        _, record = self.reviewed(self.works["w1"], self.completing(write={"out.txt": b"out\n"}))
        self.assertEqual(self.pushes(record), [])
        self.assertIn("review_work_result_proof", record["notes"])
        self.assertIn("review_work_terminal_proof", record["notes"])
        self.assertEqual(self.consumption(self.head(), record).artifact_kind, "result_commit")
        self.assertEqual(validate_project(self.store), [])

    def test_without_a_remote_an_empty_artifact_completes_locally(self) -> None:
        self.produce()
        _, record = self.reviewed(self.works["w1"], self.completing())
        consumption = self.consumption(self.head(), record)
        self.assertEqual((consumption.artifact_kind, consumption.authorized_result_commit_sha), ("empty", None))
        self.assertEqual(self.pushes(record), [])
        self.assertEqual(validate_project(self.store), [])


# --------------------------------------------------------------------------- B: the empty-artifact Work


class EmptyArtifactGate3Tests(Gate3Case):
    def test_an_empty_artifact_work_completes_with_no_k1(self) -> None:
        self.produce()
        sealed: list[str] = []
        real = start_review._seal

        def seal(*args, **kwargs):
            real(*args, **kwargs)
            sealed.append(self.head())

        with mock.patch.object(start_review, "_seal", side_effect=seal):
            _, record = self.reviewed(self.works["w1"], self.completing())
        k2 = self.head()
        self.assertEqual(git(self.root, "rev-parse", f"{k2}^"), sealed[0], "K2 sits on the Run's own lineage")
        self.assertTrue(all(e["payload"]["plan_class"] != "result" for e in record["effects"] if e["kind"] == "git_commit"))
        self.assertEqual(self.stage_of(record, f"{self.works['w1']}:results"), [])
        consumption = self.consumption(k2, record)
        self.assertEqual((consumption.artifact_kind, consumption.authorized_result_commit_sha), ("empty", None))
        self.assertEqual(self.reviewed_candidate(record)["declared_base"]["work"]["desired_state"], "W1 done")
        self.assertNotIn("review_work_result_proof", record["notes"])
        self.assertIsNone(record["notes"]["review_work_terminal_proof"]["result_commit"])
        (consumption_id,) = [v for k, v in record["reserved_ids"].items() if k.startswith("review-consumption:")]
        self.assertEqual(self.delta(k2), sorted([("M", EVENTS), ("A", review_paths.consumption_rel(consumption_id))]))
        self.assertEqual([push["payload"]["commit"] for push in self.pushes(record)], [k2])
        self.assertEqual(self.remote_ref(), k2)
        self.assertEqual(validate_project(self.store), [])


# --------------------------------------------------------------------------- C: legacy after activation


class LegacyAfterActivationTests(Gate3Case):
    def test_legacy_start_after_activation_is_unchanged_and_needs_no_consumption(self) -> None:
        activation = self.produce()
        captured: list[dict] = []
        real = st._start_locked

        def spy(store, work_id, mode, executor, review=None):
            captured.append({"review": review})
            return real(store, work_id, mode, executor, review)

        with mock.patch.object(st, "_start_locked", side_effect=spy):
            self.legacy(self.works["w2"])
        self.assertEqual(captured, [{"review": None}], "activation never selects review-v1 by itself")
        completed = self.completions()[self.works["w2"]]
        self.assertEqual(sorted(completed), ["at", "entity", "id", "type"], "no review-v1 marker, no metadata")
        self.assertEqual(ReviewStore(self.store).consumption_ids(), ())
        self.assertEqual(validate_project(self.store), [])
        # the activation decided against an earlier base is the same record, and a review-v1 START still
        # proves its prefix against the later HEAD
        self.assertGreater(len(self.completions()), 0)
        self.reviewed(self.works["w1"], self.completing(write={"out.txt": b"out\n"}))
        self.assertEqual(self.record_at("HEAD"), self.record_at(activation.head))
        self.assertEqual(validate_project(self.store), [])


# --------------------------------------------------------------------------- D: no migration


class NoMigrationTests(Gate3Case):
    def test_activation_migrates_nothing(self) -> None:
        w2 = self.works["w2"]
        self.legacy(w2)
        base = self.head()
        log = git_bytes(self.root, "show", f"{base}:{EVENTS}")
        tree = git(self.root, "ls-tree", "-r", base, "--", ".workline")
        state = ProjectView.load(self.store).work_state(w2).state
        activation = self.produce()
        k = activation.head
        self.assertEqual(git(self.root, "diff", "--name-only", base, k), REL)
        self.assertEqual(git_bytes(self.root, "show", f"{k}:{EVENTS}"), log)
        after = git(self.root, "ls-tree", "-r", k, "--", ".workline").splitlines()
        self.assertEqual([line for line in after if not line.endswith("\t" + REL)], tree.splitlines())
        self.assertEqual(ProjectView.load(self.store).work_state(w2).state, state)
        self.assertEqual(activation.legacy_event_count,
                         len([line for line in log.decode("utf-8").splitlines() if line.strip()]))
        review = ReviewStore(self.store)
        self.assertEqual((review.run_ids(), review.receipt_ids(), review.consumption_ids()), ((), (), ()))
        self.assertEqual(self.pending(), [])


# --------------------------------------------------------------------------- the START entry (F1 §6.4)


class StartEntryTests(Gate3Case):
    remote = False

    def hand_made(self, record: dict) -> None:
        self.commit_file(REL, serialize.canonical_bytes(record), "a hand-made activation record (fixture)")

    def refused_entry(self, error: type) -> BaseException:
        head, called = self.head(), []
        with self.assertRaises(error) as raised:
            st.start(self.store, self.works["w1"], "single-work", lambda ctx: called.append("run") or st.Completed(),
                     review=self.review())
        self.assertEqual((called, self.pending(), self.head()), ([], [], head))
        return raised.exception

    def test_a_malformed_activation_fails_closed_at_entry(self) -> None:
        self.hand_made({"schema": records.SCHEMA_ACTIVATION, "version": records.VERSION})
        self.refused_entry(ValidationError)

    def test_an_unknown_operation_contract_fails_closed_at_entry(self) -> None:
        good = records.WorkTerminalActivation("review-v1", 0, "a" * 64, self.head()).to_record()
        self.hand_made({**good, "operation_contract": "review-v2"})
        self.refused_entry(ValidationError)

    def test_a_prefix_the_history_no_longer_reproduces_fails_closed_at_entry(self) -> None:
        self.legacy(self.works["w2"])
        self.produce()
        lines = [json.loads(line) for line in git_bytes(self.root, "show", f"HEAD:{EVENTS}").decode("utf-8").splitlines()
                 if line.strip()]
        lines[0]["rewritten"] = "after the activation"
        self.commit_file(EVENTS, b"".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
                                          for e in lines), "rewrite a pre-activation Event")
        self.refused_entry(ReconcileRequired)

    def test_activation_never_selects_review_v1_and_never_upgrades_a_pending_legacy_start(self) -> None:
        waiting = st.start(self.store, self.works["w1"], "single-work", scripted_executor({"*": [st.QuestionWait("wait")]}))
        self.assertEqual(waiting.status, "question_wait")
        with self.assertRaises(StopError) as raised:
            wta.activate_work_terminal_review(self.root, confirmed=True)
        self.assertEqual(raised.exception.code, "pending_operation")
        (pending,) = self.pending()
        self.assertEqual(set(pending["invocation"]), {"operation", "work_id", "mode"})
        with self.assertRaises(ReconcileRequired) as mismatch:
            st.start(self.store, self.works["w1"], "single-work", self.completing(), review=self.review())
        self.assertEqual(mismatch.exception.reason, "review_marker_mismatch")
        self.assertEqual(self.pending(), [pending], "the pending legacy START is left exactly as it was")
        self.legacy(self.works["w1"])
        self.assertNotIn("operation_contract", self.completions()[self.works["w1"]])
        self.produce()


class OrphanActivationTests(Gate3Case):
    """F1 §6: activation is committed authority, so an activation lost before its commit activates nothing."""

    def test_an_activation_whose_commit_and_runtime_were_lost_admits_no_review_v1_start(self) -> None:
        head, remote = self.head(), self.remote_ref()
        # the producer applies its create and dies before its commit; then its runtime record is lost too
        with mock.patch.object(gitops, "finalize", side_effect=Crash):
            with self.assertRaises(Crash):
                wta.activate_work_terminal_review(self.root, confirmed=True)
        (record,) = self.pending()
        (self.store.mutations / f"{record['mutation_id']}.yaml").unlink()
        self.assertEqual(self.pending(), [])
        self.assertTrue((self.root / REL).is_file(), "the orphan: valid record bytes the working tree alone holds")
        self.assertEqual((git(self.root, "ls-tree", "HEAD", "--", REL), self.head()), ("", head))
        # validation refuses it rather than classifying by it
        self.assertIn("review_record_conflict", [problem.code for problem in validate_project(self.store)])
        # a review-v1 START is refused under the lock, before its mutation: nothing begun, written or sent
        called: list[str] = []
        with self.assertRaises(ReconcileRequired):
            st.start(self.store, self.works["w1"], "single-work", lambda ctx: called.append("run") or st.Completed(),
                     review=self.review())
        self.assertEqual((called, self.pending(), self.head(), self.remote_ref()), ([], [], head, remote))
        review = ReviewStore(self.store)
        self.assertEqual((review.run_ids(), review.candidate_snapshot_hashes(), review.task_input_ids()), ((), (), ()))
        # and the producer still never adopts it
        with self.assertRaises(ReconcileRequired) as raised:
            wta.activate_work_terminal_review(self.root, confirmed=True)
        self.assertIn("never adopted", str(raised.exception))
        self.assertEqual((self.head(), self.remote_ref()), (head, remote))


# --------------------------------------------------------------------------- the totality allowance (F1 §10.2)


class PendingTerminalStageTests(Gate3Case):
    remote = False

    def interrupt(self, condition) -> dict:
        real = MutationController.apply_effect

        def crash_at(controller, record):
            if condition(record):
                raise Crash()
            return real(controller, record)

        with mock.patch.object(MutationController, "apply_effect", crash_at):
            with self.assertRaises(Crash):
                st.start(self.store, self.works["w1"], "single-work", self.completing(write={"out.txt": b"out\n"}),
                         review=self.review())
        (record,) = [r for r in self.pending() if (r.get("invocation") or {}).get("operation") == "start"]
        return record

    def resume(self) -> None:
        def never(ctx):
            raise AssertionError("the executor ran again")

        result = st.start(self.store, self.works["w1"], "single-work", never, review=self.review())
        self.assertEqual(result.status, "completed")
        self.assertEqual(validate_project(self.store), [])

    def test_an_event_without_its_consumption_is_valid_only_under_its_own_pending_stage(self) -> None:
        self.produce()
        record = self.interrupt(lambda r: r["kind"] == "create_file" and "/consumptions/" in r["payload"]["path"])
        terminal = start_review.recorded_terminal(record)
        self.assertIsNotNone(terminal)
        self.assertEqual(self.store.read_events()[-1].to_record(), terminal.completed, "the event is applied")
        self.assertIsNone(ReviewStore(self.store).read_bytes(terminal.consumption_path), "its Consumption is not")
        self.assertEqual(self.totality(), [], "a recoverable half of one durable stage")
        # a pending stage excuses exactly its own completion, in exactly the log it wrote: another completion is
        # not its own, and while the log holds one the stage's own half is no longer the state its replay left
        log = self.store.events_jsonl.read_bytes()
        stray = {**terminal.completed, "id": "evt_01ARZ3NDEKTSV4RRFFQ69G5FAZ"}
        self.store.events_jsonl.write_bytes(log + json.dumps(stray, separators=(",", ":")).encode("utf-8") + b"\n")
        self.assertEqual(self.totality(), [review_validate.COMPLETION_UNCONSUMED] * 2)
        self.store.events_jsonl.write_bytes(log)
        self.assertEqual(self.totality(), [])
        self.resume()

    def test_a_consumption_someone_else_placed_is_no_recoverable_half(self) -> None:
        """Interrupted before the stage applied anything: a Consumption that appears with the recorded bytes is
        still not this mutation's own write, its replay could not commit it, and so nothing excuses it."""
        self.produce()
        record = self.interrupt(lambda r: r["kind"] == "append_event"
                                and r["payload"]["record"]["type"] == "work_target_removed")
        terminal = start_review.recorded_terminal(record)
        self.assertIsNotNone(terminal)
        self.assertIsNone(terminal.consumption_written)
        self.assertNotIn(terminal.completed["id"], [e.id for e in self.store.read_events()])
        self.assertEqual(self.totality(), [], "nothing of the stage applied: no one-sided state at all")
        target = self.root / terminal.consumption_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(terminal.consumption_content.encode("utf-8"))
        self.assertEqual(self.totality(), [review_validate.CONSUMPTION_UNBOUND])
        target.unlink()
        self.resume()

    def test_a_consumption_without_its_event_is_valid_only_while_its_replay_can_finish(self) -> None:
        """The stage applied whole, then the two events were taken back out of the log exactly: the replay finds
        the log it recorded and the Consumption it wrote, so it is a recoverable half - and nothing looser is."""
        self.produce()
        real = workcommit.terminal_commit_effect
        calls: list[int] = []

        def crash_once(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise Crash()
            return real(*args, **kwargs)

        with mock.patch.object(workcommit, "terminal_commit_effect", side_effect=crash_once):
            with self.assertRaises(Crash):
                st.start(self.store, self.works["w1"], "single-work", self.completing(write={"out.txt": b"out\n"}),
                         review=self.review())
            (record,) = [r for r in self.pending() if (r.get("invocation") or {}).get("operation") == "start"]
            terminal = start_review.recorded_terminal(record)
            self.assertIsNotNone(terminal)
            self.assertIsNotNone(terminal.consumption_written, "the stage wrote its Consumption itself")
            whole = self.store.events_jsonl.read_bytes()
            lines = whole.split(b"\n")
            self.assertEqual([json.loads(line)["type"] for line in lines[-3:-1]], ["work_target_removed", "work_completed"])
            before = b"\n".join(lines[:-3]) + b"\n"
            # a log that is not exactly the one the replay recorded finding: the half is not recoverable
            self.store.events_jsonl.write_bytes(before + lines[-4] + b"\n")
            self.assertEqual(self.totality(), [review_validate.CONSUMPTION_UNBOUND])
            # exactly the recorded log, the events unapplied and the Consumption its own: recoverable
            self.store.events_jsonl.write_bytes(before)
            self.assertEqual(self.totality(), [])
            self.resume()
        types = [e.type for e in self.store.read_events() if e.entity == self.works["w1"]]
        self.assertEqual(types.count("work_completed"), 1)

    def test_a_pending_legacy_start_excuses_nothing(self) -> None:
        self.produce()
        waiting = st.start(self.store, self.works["w2"], "single-work", scripted_executor({"*": [st.QuestionWait("wait")]}))
        self.assertEqual(waiting.status, "question_wait")
        log = self.store.events_jsonl.read_bytes()
        completed = {"id": "evt_01ARZ3NDEKTSV4RRFFQ69G5FAZ", "type": "work_completed", "entity": self.works["w2"],
                     "at": "2026-10-01T00:00:00Z", "operation_contract": "review-v1",
                     "review_receipt_id": "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV", "review_run_id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                     "review_generation": 3}
        self.store.events_jsonl.write_bytes(log + json.dumps(completed, separators=(",", ":")).encode("utf-8") + b"\n")
        self.assertEqual(self.totality(), [review_validate.COMPLETION_UNCONSUMED])
        self.store.events_jsonl.write_bytes(log)
