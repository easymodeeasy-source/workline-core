"""RB3-C1 / P3-F4: the Class-A interruption matrix (``WORKLINE_COMPLETION_SPRINT.md`` §11.16, §26.24, §26.27).

One real Class-A adoption (A2) is interrupted at every row of §26.27 in turn - each a process death at that
instant - and continued by the same review-v1 START each time. Every row proves, before the next one is armed:

* the same durable identities on retry: every reservation, once made, keeps its value; the checkpoint, K1 and
  (once made) K_adopt never change;
* no new Candidate, Run, Receipt, Supersession or Consumption when one already exists, and never more than the
  topology has (two Runs, two Receipts, one Supersession, one Consumption);
* no branch-tip substitution, force or history rewrite: the branch and the destination only ever move forward;
* no fallback to legacy: the executor never runs again, and a legacy invocation is refused untouched;
* no duplicate publication: at most two pushes, of two distinct commits.

The recovery selector's state is read at each stop, so every retry is shown to select the same successor; the
reviewer's own failure and retry, a conflicting successor reservation, a changed destination and the
publication barrier are exercised on the way.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest import mock

from test_work_review_runtime import git
from test_work_review_recovery import AdoptionCase, Upgrade
from test_work_terminal import Crash

from workline import gitcmd
from workline import start as st
from workline import start_review
from workline.errors import ReconcileRequired, StopError
from workline.ids import new_id
from workline.mutation import Mutation, MutationController
from workline.review import gate, publication, workcommit
from workline.review import paths as review_paths
from workline.review.store import ReviewStore


class Faults:
    """One armed instant at a time; it fires once, as a process death there."""

    def __init__(self) -> None:
        self.armed: str | None = None
        self.fired: list[str] = []

    def arm(self, name: str) -> None:
        self.armed = name

    def hit(self, name: str) -> None:
        if self.armed == name:
            self.armed = None
            self.fired.append(name)
            raise Crash(name)


def _gate_generation(path: str) -> int | None:
    if not path.startswith(review_paths.GATES_DIR + "/"):
        return None
    name = path.rsplit("/", 1)[-1]
    return int(name.split(".", 1)[0]) if name.split(".", 1)[0].isdigit() else None


class InterruptionCase(AdoptionCase):
    def setUp(self) -> None:
        super().setUp()
        self.faults = faults = Faults()
        self.upgrade = Upgrade().install(self)
        self.reviewer = SimpleNamespace(tasks=[])

        real_apply = MutationController.apply_effect

        def apply_effect(controller, record):
            path = (record.get("payload") or {}).get("path") if record.get("kind") == "create_file" else None
            if isinstance(path, str):
                generation = _gate_generation(path)
                if generation is not None:
                    faults.hit(f"create-gate-{generation}")
                if path.startswith(review_paths.SUPERSESSIONS_DIR + "/"):
                    faults.hit("create-supersession")
                if path.startswith(review_paths.RECEIPTS_DIR + "/"):
                    faults.hit("create-receipt")
                if path.startswith(review_paths.CONSUMPTIONS_DIR + "/"):
                    faults.hit("create-consumption")
            return real_apply(controller, record)

        real_complete = Mutation.complete

        def complete(mutation):
            invocation = mutation.invocation
            if invocation.get("operation") == "review-generation":
                faults.hit(f"complete-generation-{invocation.get('generation')}")
            elif invocation.get("operation") == "start":
                faults.hit("complete-start")
            return real_complete(mutation)

        real_reserve = Mutation.reserve_id

        def reserve_id(mutation, key, kind):
            found = real_reserve(mutation, key, kind)
            if key.startswith(gate.SUCCESSOR_RUN_KEY_PREFIX):
                faults.hit("successor-reserved")
            return found

        real_persisted = workcommit.require_generation_persisted

        def persisted(mutation, expected):
            found = real_persisted(mutation, expected)
            faults.hit(f"generation-committed-{mutation.invocation.get('generation')}")
            return found

        real_post_commit, real_invalidate = start_review._post_commit, start_review._invalidate_predecessor
        real_write_note, real_prove_terminal = start_review._write_note, start_review.prove_terminal
        real_settlement, real_push, real_cas = gate.validate_settlement, gitcmd.push, workcommit._cas
        real_committable = gate.require_committable

        def committable(*args, **kwargs):
            faults.hit("committable")  # a generation mutation opened, nothing recorded in it yet
            return real_committable(*args, **kwargs)

        def post_commit(*args, **kwargs):
            faults.hit("k1-before-checkpoint")
            return real_post_commit(*args, **kwargs)

        def invalidate(*args, **kwargs):
            faults.hit("checkpoint-before-g4")
            return real_invalidate(*args, **kwargs)

        def write_note(mutation, key, value):
            faults.hit(f"before-note-{key}")
            return real_write_note(mutation, key, value)

        def prove_terminal(*args, **kwargs):
            faults.hit("before-terminal-proof")
            return real_prove_terminal(*args, **kwargs)

        def settlement(*args, **kwargs):
            faults.hit("settlement")
            return real_settlement(*args, **kwargs)

        def push(repo, remote, refspec):
            faults.hit("push-recorded")
            done = real_push(repo, remote, refspec)
            faults.hit("push-applied")
            return done

        def cas(git_, ref, commit, parent):
            faults.hit("cas")
            return real_cas(git_, ref, commit, parent)

        for patcher in (
            mock.patch.object(MutationController, "apply_effect", apply_effect),
            mock.patch.object(Mutation, "complete", complete),
            mock.patch.object(Mutation, "reserve_id", reserve_id),
            mock.patch.object(workcommit, "require_generation_persisted", side_effect=persisted),
            mock.patch.object(start_review, "_post_commit", side_effect=post_commit),
            mock.patch.object(start_review, "_invalidate_predecessor", side_effect=invalidate),
            mock.patch.object(start_review, "_write_note", side_effect=write_note),
            mock.patch.object(start_review, "prove_terminal", side_effect=prove_terminal),
            mock.patch.object(gate, "validate_settlement", side_effect=settlement),
            mock.patch.object(gate, "require_committable", side_effect=committable),
            mock.patch.object(gitcmd, "push", side_effect=push),
            mock.patch.object(workcommit, "_cas", side_effect=cas),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.seen: dict = {}

    # --- the reviewer, which can fail once for the successor -------------------------------------
    def reviewer_call(self):
        case = self

        def call(task):
            case.reviewer.tasks.append(task)
            if task.request_envelope.get("set_aside_runs") and case.faults.armed == "reviewer-raises":
                case.faults.armed = None
                case.faults.fired.append("reviewer-raises")
                raise RuntimeError("the reviewer's service is down")
            return start_review.work_review.WorkReviewReport(task.task_id, "reviewer-x", "1", "completed", ())

        return call

    def run_once(self, executor=None):
        selector = start_review.work_review.WorkReview(self.reviewer_call(), "reviewer-x", "1")
        return st.start(self.store, self.work_id, "single-work", executor or self.never, review=selector)

    def interrupt(self, name: str, expected_state: str | None, executor=None) -> dict:
        """Arm ``name``, run the START until it dies there, and check every invariant at that instant."""
        self.faults.arm(name)
        with self.assertRaises(Crash) as raised:
            self.run_once(executor)
        self.assertEqual(str(raised.exception), name)
        return self.check(name, expected_state)

    def check(self, name: str, expected_state: str | None) -> dict:
        record = self.start_record()
        review = ReviewStore(self.store)
        mutation = MutationController(self.store).load(record["mutation_id"])
        state = start_review.select_in_flight(mutation)
        observed = {
            "reserved": dict(record["reserved_ids"]),
            "checkpoint": record["notes"].get(start_review.NOTE_CLASS_A),
            "adopted": (record["notes"].get(start_review.NOTE_ADOPTED_PROOF) or {}).get("k_adopt"),
            "runs": review.run_ids(), "receipts": review.receipt_ids(),
            "supersessions": review.superseded_receipt_ids(), "consumptions": review.consumption_ids(),
            "snapshots": review.candidate_snapshot_hashes(), "tasks": review.task_input_ids(),
            "pushes": [e["payload"]["commit"] for e in record["effects"] if e["kind"] == "git_push"],
            "head": self.head(), "remote": self.remote_main() if self.remote else None,
            "state": None if state is None else state.state,
            "successor": None if state is None else state.successor_review_run_id,
        }
        with self.subTest(row=name):
            if expected_state is not None:
                self.assertEqual(observed["state"], expected_state)
            # never more than the topology has
            self.assertLessEqual(len(observed["runs"]), 2)
            self.assertLessEqual(len(observed["receipts"]), 2)
            self.assertLessEqual(len(observed["supersessions"]), 1)
            self.assertLessEqual(len(observed["consumptions"]), 1)
            self.assertLessEqual(len(observed["snapshots"]), 2)
            self.assertLessEqual(len(observed["tasks"]), 2)
            self.assertLessEqual(len(observed["pushes"]), 2)
            self.assertEqual(len(set(observed["pushes"])), len(observed["pushes"]))
            for run_id in observed["runs"]:
                self.assertLessEqual(len(review.gate_chain(run_id).generations), 4)
            previous = self.seen
            if previous:
                # the same durable identities on retry
                for key, value in previous["reserved"].items():
                    self.assertEqual(observed["reserved"].get(key), value, key)
                for field in ("checkpoint", "adopted", "successor"):
                    if previous[field] is not None:
                        self.assertEqual(observed[field], previous[field], field)
                for field in ("runs", "receipts", "supersessions", "consumptions", "snapshots", "tasks"):
                    self.assertTrue(set(previous[field]) <= set(observed[field]), field)
                self.assertEqual(observed["pushes"][: len(previous["pushes"])], previous["pushes"])
                # forward only: no rewrite, no force
                self.assertTrue(self.descends(self.root, observed["head"], previous["head"]))
                if self.remote and previous["remote"] != observed["remote"]:
                    self.assertTrue(self.descends(self.remote_path(), observed["remote"], previous["remote"]))
        self.seen = observed
        return observed

    def descends(self, where, commit: str, ancestor: str) -> bool:
        return subprocess.run(["git", "-C", str(where), "merge-base", "--is-ancestor", ancestor, commit]).returncode == 0

    def legacy_is_refused_untouched(self) -> None:
        before = self.start_record()
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work", self.never)
        self.assertEqual(raised.exception.reason, "review_marker_mismatch")
        self.assertEqual(self.start_record(), before)

    def finish(self) -> dict:
        result = self.run_once()
        self.assertEqual(result.status, "completed")
        return self.captured[-1]


class InterruptionMatrixTests(InterruptionCase):
    def test_rows_1_to_10_k1_checkpoint_old_g4_successor_reservation_and_review(self) -> None:
        S = start_review
        # 1  K1 exists before the Class-A checkpoint
        first = self.interrupt("k1-before-checkpoint", S.STATE_INITIAL,
                               executor=self.completing(write={"out.txt": b"out\n"}, message="feat: out"))
        self.assertIsNone(first["checkpoint"])
        k1 = self.head()
        # 2  the checkpoint is durable, old G4 is not
        second = self.interrupt("checkpoint-before-g4", S.STATE_CHECKPOINTED)
        self.assertEqual(second["checkpoint"]["k1"], k1)
        self.legacy_is_refused_untouched()
        # 2b old G4's generation mutation opened, nothing recorded in it yet (abandoned and reopened on retry)
        self.interrupt("committable", S.STATE_CHECKPOINTED)
        # 3  old G4's effects recorded, none applied: the G4 creates are the first gate-4 / Supersession of the Run
        self.interrupt("create-gate-4", S.STATE_CHECKPOINTED)
        # 4  old G4 partly applied: its gate is there, its Supersession is not
        self.interrupt("create-supersession", S.STATE_CHECKPOINTED)
        # 5  old G4 committed, its generation mutation not completed
        fifth = self.interrupt("complete-generation-4", S.STATE_CHECKPOINTED)
        self.assertEqual(len(fifth["supersessions"]), 1)
        # 6  the successor reserved, its generation 1 not begun
        sixth = self.interrupt("successor-reserved", S.STATE_SUCCESSOR_RESERVED)
        successor = sixth["successor"]
        self.assertIsNotNone(successor)
        # a conflicting successor reservation is reconcile, and leaves the record as it is
        self.conflicting_successor_is_refused()
        # 7  successor G1: its gate not yet applied, then its commit made but not completed
        self.interrupt("create-gate-1", S.STATE_SUCCESSOR_REVIEWING)
        self.interrupt("generation-committed-1", S.STATE_SUCCESSOR_REVIEWING)
        # 8  the reviewer launch fails (a STOP that settles nothing), then dies at settlement
        self.faults.arm("reviewer-raises")
        with self.assertRaises(StopError) as raised:
            self.run_once()
        self.assertEqual(raised.exception.code, "review_reviewer_failed")
        self.check("reviewer-raises", S.STATE_SUCCESSOR_REVIEWING)
        self.interrupt("settlement", S.STATE_SUCCESSOR_REVIEWING)
        # 9  successor G2: not yet applied
        self.interrupt("create-gate-2", S.STATE_SUCCESSOR_REVIEWING)
        # 10 successor G3: R2 not yet applied, then committed but not completed
        self.interrupt("create-receipt", S.STATE_SUCCESSOR_REVIEWING)
        self.interrupt("complete-generation-3", S.STATE_SUCCESSOR_REVIEWING)
        record = self.finish()
        ids = self.assert_adopted(record)
        self.assertEqual((ids["successor"], record["notes"][S.NOTE_CLASS_A]["k1"]), (successor, k1))
        # the old Run was never reviewed again: two tasks reviewed, the successor's one launched twice
        task_ids = [task.task_id for task in self.reviewer.tasks]
        self.assertEqual(len(set(task_ids)), 2)
        self.assertEqual(self.faults.fired, [
            "k1-before-checkpoint", "checkpoint-before-g4", "committable", "create-gate-4", "create-supersession",
            "complete-generation-4", "successor-reserved", "create-gate-1", "generation-committed-1",
            "reviewer-raises", "settlement", "create-gate-2", "create-receipt", "complete-generation-3",
        ])

    def conflicting_successor_is_refused(self) -> None:
        from workline import yamlish

        (pending,) = [r for r in self.pending() if (r.get("invocation") or {}).get("operation") == "start"]
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        original = path.read_bytes()
        data = yamlish.load(original.decode("utf-8"))
        data["reserved_ids"][gate.review_successor_run_key(new_id("review_run"))] = new_id("review_run")
        path.write_bytes(yamlish.dump(data).encode("utf-8"))
        try:
            with self.assertRaises(ReconcileRequired):
                self.run_once()
            after = yamlish.load(path.read_text(encoding="utf-8"))
            self.assertEqual((after["reserved_ids"], after["effects"], after.get("notes")),
                             (data["reserved_ids"], data["effects"], data.get("notes")))
        finally:
            path.write_bytes(original)

    def test_rows_11_to_18_k_adopt_publication_terminal_and_completion(self) -> None:
        S = start_review
        # 11 K_adopt proven, its proof note not yet written
        self.interrupt(f"before-note-{S.NOTE_ADOPTED_PROOF}", S.STATE_SUCCESSOR_SEALED,
                       executor=self.completing(write={"out.txt": b"out\n"}, message="feat: out"))
        remote = self.remote_main()
        # 12 the adopted-result publication recorded, not applied - then a changed destination and the barrier stop it
        twelfth = self.interrupt("push-recorded", S.STATE_SUCCESSOR_SEALED)
        k_adopt = twelfth["adopted"]
        self.assertEqual(twelfth["pushes"], [k_adopt])
        self.assertEqual(self.remote_main(), remote, "nothing published")
        self.destination_change_stops_the_push(remote)
        with mock.patch.object(publication, "require_barrier_clear",
                               side_effect=StopError("barrier", code="review_publication_barrier")):
            with self.assertRaises(StopError) as raised:
                self.run_once()
            self.assertEqual(raised.exception.code, "review_publication_barrier")
        self.assertEqual(self.remote_main(), remote, "the barrier still applies")
        # 13 the push applied, its applied flag not saved: the retry finds it published and pushes nothing again
        self.interrupt("push-applied", S.STATE_SUCCESSOR_SEALED)
        self.assertEqual(self.remote_main(), k_adopt, "exact K_adopt, never K1 alone")
        # 14 the terminal stage partly applied: its events, not its Consumption
        self.interrupt("create-consumption", S.STATE_SUCCESSOR_SEALED)
        # 15 K_terminal prepared, the branch not yet moved (the CAS is retried on THAT object)
        self.interrupt("cas", S.STATE_SUCCESSOR_SEALED)
        # 16 K_terminal made, its proof note not yet written
        sixteenth = self.interrupt("before-terminal-proof", S.STATE_SUCCESSOR_SEALED)
        self.assertEqual(git(self.root, "rev-parse", f"{sixteenth['head']}^"), k_adopt)
        # 17 the terminal publication recorded, not applied
        self.interrupt("push-recorded", S.STATE_SUCCESSOR_SEALED)
        self.assertEqual(self.remote_main(), k_adopt)
        # 18 the recorded-completion proof passed, the START mutation not yet completed
        self.interrupt("complete-start", S.STATE_SUCCESSOR_SEALED)
        record = self.finish()
        self.assert_adopted(record)
        self.assertEqual(self.faults.fired, [
            f"before-note-{S.NOTE_ADOPTED_PROOF}", "push-recorded", "push-applied", "create-consumption", "cas",
            "before-terminal-proof", "push-recorded", "complete-start",
        ])

    def destination_change_stops_the_push(self, remote: str) -> None:
        other = self.tmp / "other-remote.git"
        git(self.tmp, "init", "--bare", "-b", "main", str(other))
        git(self.root, "remote", "set-url", "origin", str(other))
        try:
            with self.assertRaises(StopError):
                self.run_once()
            self.assertEqual(git(other, "rev-list", "--all"), "")
        finally:
            git(self.root, "remote", "set-url", "origin", str(self.remote_path()))
        self.assertEqual(self.remote_main(), remote)


class NoRemoteInterruptionTests(InterruptionCase):
    remote = False

    def test_interrupted_k_adopt_and_terminal_without_a_remote_push_nothing(self) -> None:
        S = start_review
        self.interrupt("k1-before-checkpoint", S.STATE_INITIAL, executor=self.completing(write={"out.txt": b"out\n"}))
        self.interrupt("generation-committed-3", S.STATE_SUCCESSOR_REVIEWING)  # the successor's seal, K_adopt
        self.interrupt(f"before-note-{S.NOTE_ADOPTED_PROOF}", S.STATE_SUCCESSOR_SEALED)
        self.interrupt("create-consumption", S.STATE_SUCCESSOR_SEALED)
        self.interrupt("before-terminal-proof", S.STATE_SUCCESSOR_SEALED)
        record = self.finish()
        self.assert_adopted(record, remote=False)
