"""Batch D: proof, publication and terminal for a review-v1 Work (``F3`` §5.1 steps 17-37, §8-§20).

What these tests hold, end to end and pre-activation (a fixture activation record; Gate 3 stays off):

* a result-bearing Work: Candidate, generations, Receipt, K1 (exactly the changing entries), the
  result-proof note, the exact push of K1, the three-effect terminal stage, the Consumption naming
  K1, K2 (exactly the event log and the Consumption), the terminal-proof note, the exact push of K2
  and the recorded completion;
* an empty Work - no declared path, and all-inert - with no K1 anywhere, an explicit "empty"
  Consumption and a K2 on the own-Review lineage; no remote means no push and every proof still;
* the hostile and interrupted cases: foreign lineage, a replacement object the RAW reader ignores,
  grafts, disagreeing artifact kinds, a malformed terminal stage, a missing proof note, a push before
  its proof, a push naming the wrong commit, a branch that moved after K1 was prepared, a destination
  that changed, a K1 or K2 that is not exact, and an interrupted terminal stage that resumes without
  duplicate events; legacy completion keeps its own recognition.
"""

from __future__ import annotations

import json
import subprocess
import unittest
from unittest import mock

from test_work_review_runtime import ReviewCase, git, git_bytes

from workline import gitcmd
from workline import start as st
from workline import start_review
from workline.errors import ReconcileRequired, StopError
from workline.mutation import Effect, MutationController
from workline.oplock import project_operation
from workline.review import hermetic, records, serialize, workcommit
from workline.review import paths as review_paths
from workline.review.store import ReviewStore
from workline.state import ProjectView


class Crash(BaseException):
    """A process death at a chosen instant."""


class TerminalCase(ReviewCase):
    remote = True
    stop_after_seal = False

    def setUp(self) -> None:
        super().setUp()
        self.captured: list[dict] = []
        real = start_review.require_recorded_completion

        def capture(session, sealed, git_, k2, consumption_path):
            real(session, sealed, git_, k2, consumption_path)
            self.captured.append(json.loads(json.dumps(session.mutation.record)))

        patcher = mock.patch.object(start_review, "require_recorded_completion", side_effect=capture)
        patcher.start()
        self.addCleanup(patcher.stop)

    # --- helpers ---------------------------------------------------------------
    def complete(self, executor, review=None):
        result = st.start(self.store, self.work_id, "single-work", executor, review=review or self.review())
        self.assertEqual(result.status, "completed", result)
        (record,) = self.captured
        return result, record

    def delta(self, commit: str) -> list[tuple[str, str]]:
        lines = git(self.root, "diff-tree", "-r", "--no-commit-id", "--no-renames", "--name-status", f"{commit}^",
                    commit).splitlines()
        return sorted(tuple(line.split("\t", 1)) for line in lines)

    def remote_main(self) -> str:
        return git(self.remote_path(), "rev-parse", "main")

    def pushes(self, record: dict) -> list[dict]:
        return [effect for effect in record["effects"] if effect["kind"] == "git_push"]

    def stage_of(self, record: dict, prefix: str) -> list[dict]:
        return [effect for effect in record["effects"] if str(effect["stage"]).startswith(prefix + ":")]

    def consumption(self, commit: str, record: dict) -> records.Consumption:
        (consumption_id,) = [value for key, value in record["reserved_ids"].items() if key.startswith("review-consumption:")]
        raw = git_bytes(self.root, "show", f"{commit}:{review_paths.consumption_rel(consumption_id)}")
        return records.Consumption.from_record(serialize.parse(raw.decode("utf-8"), "consumption"), "consumption")

    def events_for(self, commit: str) -> list[dict]:
        log = git_bytes(self.root, "show", f"{commit}:.workline/events/events.jsonl").decode("utf-8")
        return [json.loads(line) for line in log.splitlines() if line.strip() and json.loads(line)["entity"] == self.work_id]


# --------------------------------------------------------------------------- the result-bearing topology


class ResultBearingTests(TerminalCase):
    def test_a_result_bearing_work_is_proven_published_and_completed_through_k1_and_k2(self) -> None:
        result, record = self.complete(self.completing(write={"out.txt": b"out\n"}, message="feat: out"))
        k2 = self.head()
        k1 = git(self.root, "rev-parse", "HEAD~1")
        self.assertEqual(result.head, k2)
        # K1 carries the reviewed artifact and nothing else, with the Candidate's message exactly
        self.assertEqual(self.delta(k1), [("A", "out.txt")])
        self.assertEqual(git(self.root, "log", "-1", "--format=%B", k1), "feat: out")
        # K2 carries exactly the terminal projection, on K1
        (consumption_id,) = [v for k, v in record["reserved_ids"].items() if k.startswith("review-consumption:")]
        self.assertEqual(self.delta(k2), sorted([("M", ".workline/events/events.jsonl"),
                                                 ("A", review_paths.consumption_rel(consumption_id))]))
        self.assertEqual(git(self.root, "rev-parse", f"{k2}^"), k1)
        # both notes, each naming exactly its commit
        notes = record["notes"]
        self.assertEqual(notes["review_work_result_proof"]["result_commit"], k1)
        self.assertEqual(notes["review_work_result_proof"]["base_commit"], git(self.root, "rev-parse", f"{k1}^"))
        terminal = notes["review_work_terminal_proof"]
        self.assertEqual((terminal["terminal_commit"], terminal["result_commit"], terminal["artifact_kind"]),
                         (k2, k1, "result_commit"))
        # the terminal stage: two events then the Consumption, and the Consumption names K1
        (stage,) = {effect["stage"] for effect in record["effects"] if effect["kind"] == "create_file"}
        self.assertEqual([e["kind"] for e in record["effects"] if e["stage"] == stage],
                         ["append_event", "append_event", "create_file"])
        consumption = self.consumption(k2, record)
        self.assertEqual((consumption.artifact_kind, consumption.authorized_result_commit_sha), ("result_commit", k1))
        self.assertEqual(consumption.terminal_event_id, terminal["terminal_event_ids"][1])
        tail = self.events_for(k2)[-2:]
        self.assertEqual([(e["type"], e["id"]) for e in tail],
                         list(zip(("work_target_removed", "work_completed"), terminal["terminal_event_ids"])))
        self.assertEqual(tail[1]["operation_contract"], "review-v1")
        self.assertEqual(tail[1]["review_generation"], 3)
        # exactly two pushes, each push-only and naming its commit; the destination holds K2 over K1
        pushes = self.pushes(record)
        self.assertEqual([push["payload"]["commit"] for push in pushes], [k1, k2])
        for push in pushes:
            self.assertEqual([e["kind"] for e in record["effects"] if e["stage"] == push["stage"]], ["git_push"])
        self.assertEqual(self.remote_main(), k2)
        # completed, and nothing left open
        self.assertEqual(ProjectView.load(self.store).work_state(self.work_id).state, "completed")
        self.assertEqual(self.pending(), [])
        self.assertEqual(git(self.root, "status", "--porcelain", "--", "out.txt", ".workline/events", ".workline/review"), "")

    def test_every_commit_of_the_operation_is_work_mode_and_commit_only(self) -> None:
        _, record = self.complete(self.completing(write={"out.txt": b"out\n"}))
        commits = [effect for effect in record["effects"] if effect["kind"] == "git_commit"]
        self.assertEqual([c["payload"]["plan_class"] for c in commits], ["entry", "result", "terminal"])
        self.assertTrue(all(c["payload"]["mode"] == "review-v1-work-local-v2" for c in commits))
        for commit in commits:
            self.assertEqual([e["kind"] for e in record["effects"] if e["stage"] == commit["stage"]], ["git_commit"])

    def test_an_interrupted_terminal_stage_resumes_without_duplicate_events(self) -> None:
        real = workcommit.terminal_commit_effect
        calls: list[int] = []

        def crash_once(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise Crash()
            return real(*args, **kwargs)

        with mock.patch.object(workcommit, "terminal_commit_effect", side_effect=crash_once):
            with self.assertRaises(Crash):
                st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                         review=self.review())
            result = st.start(self.store, self.work_id, "single-work",
                              lambda ctx: (_ for _ in ()).throw(AssertionError("the executor ran again")),
                              review=self.review())
        self.assertEqual(result.status, "completed")
        types = [event["type"] for event in self.events_for("HEAD")]
        self.assertEqual(types.count("work_completed"), 1)
        self.assertEqual(types[-2:], ["work_target_removed", "work_completed"])

    def test_outer_mode_returns_with_the_one_review_v1_completion(self) -> None:
        result = st.start(self.store, self.work_id, "outer", self.completing(write={"out.txt": b"out\n"}),
                          review=self.review())
        self.assertEqual((result.status, result.completed_work_ids), ("completed", (self.work_id,)))
        self.assertEqual(self.pending(), [])


# --------------------------------------------------------------------------- the no-K1 topology


class EmptyArtifactTests(TerminalCase):
    def test_no_declared_path_has_no_k1_and_one_push(self) -> None:
        sealed_head: list[str] = []
        real = start_review._seal

        def seal(*args, **kwargs):
            real(*args, **kwargs)
            sealed_head.append(self.head())

        with mock.patch.object(start_review, "_seal", side_effect=seal):
            _, record = self.complete(self.completing())
        k2 = self.head()
        self.assertEqual(git(self.root, "rev-parse", f"{k2}^"), sealed_head[0])
        self.assertEqual(self.stage_of(record, f"{self.work_id}:results"), [])
        self.assertTrue(all(e["payload"]["plan_class"] != "result" for e in record["effects"] if e["kind"] == "git_commit"))
        consumption = self.consumption(k2, record)
        self.assertEqual((consumption.artifact_kind, consumption.authorized_result_commit_sha), ("empty", None))
        self.assertNotIn("review_work_result_proof", record["notes"])
        self.assertIsNone(record["notes"]["review_work_terminal_proof"]["result_commit"])
        self.assertEqual([push["payload"]["commit"] for push in self.pushes(record)], [k2])
        self.assertEqual(self.remote_main(), k2)

    def test_an_all_inert_declaration_is_empty_and_proven_by_containment(self) -> None:
        self.commit_file("same.txt", b"same\n")
        _, record = self.complete(self.completing(write={"same.txt": b"same\n"}))
        consumption = self.consumption(self.head(), record)
        self.assertEqual(consumption.artifact_kind, "empty")
        self.assertEqual(len(self.pushes(record)), 1)
        self.assertEqual(self.stage_of(record, f"{self.work_id}:results"), [])


class NoRemoteTests(TerminalCase):
    remote = False

    def test_no_remote_publishes_nothing_and_proves_everything(self) -> None:
        _, record = self.complete(self.completing(write={"out.txt": b"out\n"}))
        self.assertEqual(self.pushes(record), [])
        self.assertIn("review_work_result_proof", record["notes"])
        self.assertIn("review_work_terminal_proof", record["notes"])
        self.assertEqual(ProjectView.load(self.store).work_state(self.work_id).state, "completed")


# --------------------------------------------------------------------------- hostile and interrupted cases


class LineageTests(TerminalCase):
    def seal_then(self, act):
        real = start_review._seal

        def seal(*args, **kwargs):
            real(*args, **kwargs)
            act()

        return mock.patch.object(start_review, "_seal", side_effect=seal)

    def assert_refused_at_step_17(self, raised, remote: str) -> None:
        """Cumulative repair B-3: lineage precedes 17a, so a refusal leaves nothing of 17a or later durable.

        No K1, no K2, no push - and neither a reserved Consumption identifier nor its path in the
        write scope, nor any terminal stage: the frozen order (§5.1 17 -> 17a -> 17b -> 18) says none
        of them may exist yet, and Mutation.reserve_id / extend_scope are each a durable save.
        """
        self.assertEqual(raised.exception.reason, "review_registration_base_moved")
        record = self.start_record()
        self.assertEqual([key for key in record.get("reserved_ids") or {} if key.startswith("review-consumption:")], [])
        scope = (record.get("write_scope") or {}).get("files") or []
        self.assertEqual([path for path in scope if path.startswith(".workline/review/consumptions/")], [])
        stages = {str(effect["stage"]).rsplit(":", 1)[0] for effect in record["effects"]}
        for prefix in ("results", "results-publication", "finalize", "finalize-publication"):
            self.assertNotIn(f"{self.work_id}:{prefix}", stages)
        self.assertEqual([e for e in record["effects"] if e["kind"] == "create_file"], [], "no terminal stage")
        self.assertEqual([e for e in record["effects"] if e["kind"] == "append_event"
                          and e["payload"]["record"]["type"] in ("work_target_removed", "work_completed")], [])
        self.assertEqual(self.pushes(record), [])
        self.assertEqual(self.remote_main(), remote)
        self.assertEqual(git(self.root, "log", "--format=%H", "--", "out.txt"), "", "no K1")

    def test_a_foreign_commit_after_the_seal_fails_the_lineage_and_nothing_is_made_or_pushed(self) -> None:
        remote = self.remote_main()
        with self.seal_then(lambda: self.commit_file("person.txt", b"theirs\n", "a person's commit")):
            with self.assertRaises(ReconcileRequired) as raised:
                st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                         review=self.review())
        self.assert_refused_at_step_17(raised, remote)
        self.assertEqual(self.subjects(1), ["a person's commit"])

    def test_an_unanswerable_lineage_fails_closed_before_k1(self) -> None:
        from workline.review import ancestry

        remote = self.remote_main()
        with mock.patch.object(ancestry, "raw_range", return_value=ancestry.UNKNOWN):
            with self.assertRaises(ReconcileRequired) as raised:
                st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                         review=self.review())
        self.assert_refused_at_step_17(raised, remote)

    def test_an_unanswerable_descent_from_the_declared_base_fails_closed_before_k1(self) -> None:
        """L-1 unanswerable - the RAW reader cannot show the base is an ancestor - from the seal on."""
        from workline.review import ancestry

        remote = self.remote_main()
        unknown = mock.patch.object(ancestry, "raw_descends_from", return_value=ancestry.UNKNOWN)
        self.addCleanup(unknown.stop)
        with self.seal_then(unknown.start):
            with self.assertRaises(ReconcileRequired) as raised:
                st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                         review=self.review())
        self.assertIn("L-1", str(raised.exception))
        self.assert_refused_at_step_17(raised, remote)

    def test_head_moved_off_the_declared_branch_fails_closed_before_k1(self) -> None:
        remote = self.remote_main()
        with self.seal_then(lambda: git(self.root, "checkout", "-q", "-b", "elsewhere")):
            with self.assertRaises(ReconcileRequired) as raised:
                st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                         review=self.review())
        self.assertIn("L-3", str(raised.exception))
        self.assert_refused_at_step_17(raised, remote)

    def test_an_empty_artifact_measured_to_k2s_parent_reserves_nothing_when_refused(self) -> None:
        remote = self.remote_main()
        with self.seal_then(lambda: self.commit_file("person.txt", b"theirs\n", "a person's commit")):
            with self.assertRaises(ReconcileRequired) as raised:
                st.start(self.store, self.work_id, "single-work", self.completing(), review=self.review())
        self.assert_refused_at_step_17(raised, remote)
        self.assertEqual(self.subjects(1), ["a person's commit"])

    def test_the_lineage_reads_stored_parents_and_a_replacement_object_changes_nothing(self) -> None:
        _, record = self.complete(self.completing(write={"out.txt": b"out\n"}))
        k1 = record["notes"]["review_work_result_proof"]["result_commit"]
        parent = git(self.root, "rev-parse", f"{k1}^")
        generation_two = git(self.root, "rev-parse", f"{parent}^")
        # a parentless stand-in for generation 2: every revision-view reader now loses the base
        forged = git(self.root, "commit-tree", f"{generation_two}^{{tree}}", "-m", "forged")
        git(self.root, "replace", generation_two, forged)
        wr = start_review.work_record(record)
        chain = ReviewStore(self.store).gate_chain(wr.run.review_run_id)
        base = ReviewStore(self.store).read_candidate_snapshot(chain.generations[0].candidate_hash).material["candidate"]["declared_base"]
        viewed = subprocess.run(["git", "-C", str(self.root), "merge-base", "--is-ancestor", base["base_commit"], parent])
        self.assertNotEqual(viewed.returncode, 0, "the replacement must change the revision view")
        # the RAW reader walks the stored parents: the base is still an ancestor, and every commit between is own
        start_review.require_lineage(hermetic.enter(self.store), wr.run, chain, base, parent)

    def test_a_grafted_repository_is_refused_before_anything_is_begun(self) -> None:
        graft = self.root / ".git" / "info" / "grafts"
        graft.parent.mkdir(parents=True, exist_ok=True)
        graft.write_text(self.head() + "\n", encoding="utf-8")
        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", self.completing(), review=self.review())
        self.assertEqual(raised.exception.code, "review_repository_grafted")
        self.assertEqual(self.pending(), [])


class ConsumptionReservationTests(TerminalCase):
    """B-3: the FIRST durable Consumption reservation follows a successful step-17 lineage proof, exactly once."""

    def consumption_ids(self, record: dict) -> list[str]:
        return [value for key, value in (record.get("reserved_ids") or {}).items() if key.startswith("review-consumption:")]

    def test_the_reservation_follows_a_proven_lineage_and_is_made_once(self) -> None:
        from workline.mutation import Mutation

        order: list = []
        real_lineage, real_reserve = start_review.require_lineage, Mutation.reserve_id

        def lineage(*args, **kwargs):
            real_lineage(*args, **kwargs)
            order.append("lineage proven")

        def reserve(mutation, key, kind):
            identifier = real_reserve(mutation, key, kind)
            if key.startswith("review-consumption:"):
                order.append(("reserved", identifier))
            return identifier

        with mock.patch.object(start_review, "require_lineage", side_effect=lineage), \
                mock.patch.object(Mutation, "reserve_id", reserve):
            _, record = self.complete(self.completing(write={"out.txt": b"out\n"}))
        first = next(index for index, step in enumerate(order) if isinstance(step, tuple))
        self.assertIn("lineage proven", order[:first], "a proven lineage precedes the first reservation")
        self.assertEqual({step[1] for step in order if isinstance(step, tuple)}, set(self.consumption_ids(record)))
        (consumption_id,) = self.consumption_ids(record)
        self.assertEqual(record["write_scope"]["files"].count(review_paths.consumption_rel(consumption_id)), 1)
        self.assertEqual(self.consumption(self.head(), record).consumption_id, consumption_id)

    def test_an_interrupted_terminal_phase_resumes_with_the_same_reservation(self) -> None:
        real = start_review._result_commit
        calls: list[int] = []

        def crash_once(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise Crash()
            return real(*args, **kwargs)

        with mock.patch.object(start_review, "_result_commit", side_effect=crash_once):
            with self.assertRaises(Crash):
                st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                         review=self.review())
            reserved = self.consumption_ids(self.start_record())
            self.assertEqual(len(reserved), 1, "reserved once, after its lineage, before S-c1")
            result = st.start(self.store, self.work_id, "single-work",
                              lambda ctx: (_ for _ in ()).throw(AssertionError("the executor ran again")),
                              review=self.review())
        self.assertEqual(result.status, "completed")
        (record,) = self.captured
        self.assertEqual(self.consumption_ids(record), reserved, "the resumed run reused it, and reserved no other")
        self.assertEqual(record["write_scope"]["files"].count(review_paths.consumption_rel(reserved[0])), 1)
        self.assertEqual(self.consumption(self.head(), record).consumption_id, reserved[0])

    def test_a_reservation_already_held_is_left_exactly_as_it_is_when_the_lineage_then_fails(self) -> None:
        """A pending record holding a reservation is neither discarded nor reinterpreted: lineage decides first."""
        remote = self.remote_main()
        with mock.patch.object(start_review, "_result_commit", side_effect=Crash()), self.assertRaises(Crash):
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                     review=self.review())
        before = self.start_record()
        self.assertEqual(len(self.consumption_ids(before)), 1)
        self.commit_file("person.txt", b"theirs\n", "a person's commit")
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work",
                     lambda ctx: (_ for _ in ()).throw(AssertionError("the executor ran again")), review=self.review())
        self.assertEqual(raised.exception.reason, "review_registration_base_moved")
        after = self.start_record()
        self.assertEqual((after["reserved_ids"], after["write_scope"]), (before["reserved_ids"], before["write_scope"]))
        self.assertEqual({str(e["stage"]) for e in after["effects"]}, {str(e["stage"]) for e in before["effects"]})
        self.assertEqual(git(self.root, "log", "--format=%H", "--", "out.txt"), "")
        self.assertEqual(self.remote_main(), remote)


class PublicationTests(TerminalCase):
    def edit_pending_record(self, change) -> None:
        from workline import yamlish

        (record,) = self.pending()
        path = MutationController(self.store).intent_path(record["mutation_id"])
        data = yamlish.load(path.read_text(encoding="utf-8"))
        change(data)
        path.write_bytes(yamlish.dump(data).encode("utf-8"))

    def crash_at_push(self):
        return mock.patch.object(gitcmd, "push", side_effect=Crash())

    def test_a_push_whose_proof_note_is_gone_publishes_nothing(self) -> None:
        remote = self.remote_main()
        with self.crash_at_push(), self.assertRaises(Crash):
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                     review=self.review())
        self.edit_pending_record(lambda data: data["notes"].pop("review_work_result_proof"))
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work", self.completing(), review=self.review())
        self.assertIn("V-3", str(raised.exception))
        self.assertEqual(self.remote_main(), remote)

    def test_a_changed_destination_stops_the_push(self) -> None:
        with self.crash_at_push(), self.assertRaises(Crash):
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                     review=self.review())
        other = self.tmp / "other-remote.git"
        git(self.tmp, "init", "--bare", "-b", "main", str(other))
        git(self.root, "remote", "set-url", "origin", str(other))
        with self.assertRaises(StopError):
            st.start(self.store, self.work_id, "single-work", self.completing(), review=self.review())
        self.assertEqual(git(other, "rev-list", "--all"), "")

    def own_mutation(self):
        (record,) = self.pending()
        return MutationController(self.store).load(record["mutation_id"])

    def test_a_push_before_its_proof_and_a_push_naming_another_commit_are_refused(self) -> None:
        remote = self.remote_main()
        with mock.patch.object(start_review, "prove_result", side_effect=Crash()), self.assertRaises(Crash):
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                     review=self.review())
        k1 = self.head()
        destination = self.store.read_push_pin()
        for name, commit in (("before its proof", k1), ("another commit", git(self.root, "rev-parse", "HEAD~1"))):
            with self.subTest(case=name), project_operation(self.store, "start", {"review_contract": "review-v1-work-v1"}):
                mutation = self.own_mutation()
                effect = Effect.git_push(destination.remote, "main", destination.allowed_urls[0])
                effect.payload["commit"] = commit
                stage = f"forged-publication-{len(name)}:0"
                mutation.add_effects(stage, [effect])
                with self.assertRaises(ReconcileRequired):
                    mutation.apply()
        self.assertEqual(self.remote_main(), remote)

    def test_a_branch_that_moved_after_k1_was_prepared_is_never_committed_onto(self) -> None:
        real = workcommit._cas

        def crash_on_result(git_, ref, commit, parent):
            if workcommit._stored_commit(git_, commit) and b"feat: out" in workcommit._stored_commit(git_, commit).message:
                raise Crash()
            return real(git_, ref, commit, parent)

        with mock.patch.object(workcommit, "_cas", side_effect=crash_on_result), self.assertRaises(Crash):
            st.start(self.store, self.work_id, "single-work",
                     self.completing(write={"out.txt": b"out\n"}, message="feat: out"), review=self.review())
        self.commit_file("person.txt", b"theirs\n", "a person's commit")
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work", self.completing(), review=self.review())
        self.assertEqual(raised.exception.reason, "review_registration_base_moved")
        self.assertEqual(self.subjects(1), ["a person's commit"])


class ExactnessTests(TerminalCase):
    remote = False

    def test_k1_and_k2_that_are_not_exact_fail_their_proofs(self) -> None:
        _, record = self.complete(self.completing(write={"out.txt": b"out\n"}))
        k2, k1 = self.head(), git(self.root, "rev-parse", "HEAD~1")
        git_ = hermetic.enter(self.store)
        # C-2(K2) re-executes from the record and the committed objects alone
        self.assertEqual(start_review.prove_terminal(self.store, git_, record, k2),
                         record["notes"]["review_work_terminal_proof"])
        # C-2(K1) is about the state before the consumption: once the terminal stage exists its W12 is false
        with self.assertRaises(ReconcileRequired) as raised:
            start_review.prove_result(self.store, git_, record, k1)
        self.assertIn("W12", str(raised.exception))
        # a commit the record's S-c1 did not make is never K1
        with self.assertRaises(ReconcileRequired) as raised:
            start_review.prove_result(self.store, git_, record, k2)
        self.assertEqual(raised.exception.reason, "review_commit_unowned")
        # a K2 whose delta is not the terminal projection
        forged = json.loads(json.dumps(record))
        for effect in forged["effects"]:
            if effect["kind"] == "git_commit" and effect["payload"]["plan_class"] == "terminal":
                effect["commit_id"] = k1
        with self.assertRaises(ReconcileRequired):
            start_review.prove_terminal(self.store, git_, forged, k1)

    def test_the_artifact_kinds_must_agree_and_are_never_derived_from_each_other(self) -> None:
        _, record = self.complete(self.completing(write={"out.txt": b"out\n"}))
        candidate = ReviewStore(self.store).read_candidate_snapshot(
            record["notes"]["review_work_terminal_proof"]["candidate_hash"]).material["candidate"]
        consumption = self.consumption(self.head(), record)
        k1 = record["notes"]["review_work_result_proof"]["result_commit"]
        start_review.require_artifact_kind_agreement(candidate, consumption, k1, "T8")
        for name, changed in (("kind", {"artifact_kind": "empty"}), ("no commit", {"authorized_result_commit_sha": None}),
                              ("absent kind", {"artifact_kind": None})):
            with self.subTest(case=name), self.assertRaises(ReconcileRequired):
                start_review.require_artifact_kind_agreement(
                    candidate, records.Consumption(**{**consumption.__dict__, **changed}), k1, "T8")


class RecognitionTests(TerminalCase):
    remote = False

    def test_a_review_v1_terminal_stage_is_recognized_only_in_its_own_shape(self) -> None:
        with mock.patch.object(workcommit, "terminal_commit_effect", side_effect=Crash()), self.assertRaises(Crash):
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                     review=self.review())
        (pending,) = self.pending()
        mutation = MutationController(self.store).load(pending["mutation_id"])
        (stage,) = {effect["stage"] for effect in mutation.effects if effect["kind"] == "create_file"}
        self.assertTrue(st._recorded_completion(mutation, stage, self.work_id))
        # the legacy two-effect reading of the same stage is never accepted for a review-v1 mutation
        legacy = json.loads(json.dumps(mutation.record))
        legacy["effects"] = [e for e in legacy["effects"] if not (e["stage"] == stage and e["kind"] == "create_file")]
        mutation.record = legacy
        self.assertFalse(st._recorded_completion(mutation, stage, self.work_id))


# --------------------------------------------------------------------------- which commit each Work commit is pinned to


class PersistenceBasisTests(TerminalCase):
    """Cumulative repair B-2 - F3 §7.1.11 as corrected by C3-2, and §7.3 - for every Work commit class.

    Every Work-mode commit's DURABLE payload is read at its §7.3 preflight, and every pinned
    evaluation is recorded with HEAD at that instant. A pre-completion Work commit is pinned to
    its own exact recorded parent (``attr_basis == base_head``), and its preflight evaluated
    exactly its path set under exactly that basis while HEAD was still that parent - before the
    commit existed. Every generation commit, K1 and K2 are pinned to declared_base.base_commit.
    """

    confirmation = True

    def setUp(self) -> None:
        super().setUp()
        from workline.review import attributes

        self.payloads: list[dict] = []
        self.evaluations: list[tuple[str, tuple[str, ...], str]] = []
        real_preflight, real_evaluate = workcommit.preflight, attributes.require_pinned_path_evaluation

        def preflight(mutation, git_, record):
            self.payloads.append(json.loads(json.dumps(record["payload"])))
            return real_preflight(mutation, git_, record)

        def evaluate(store, git_, basis, paths):
            self.evaluations.append((basis, tuple(paths), self.head()))
            return real_evaluate(store, git_, basis, paths)

        for patcher in (mock.patch.object(workcommit, "preflight", side_effect=preflight),
                        mock.patch.object(attributes, "require_pinned_path_evaluation", side_effect=evaluate)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def of_class(self, plan_class: str) -> list[dict]:
        """The distinct commits of one class; a commit is preflighted when recorded and again when made."""
        found: dict[tuple, dict] = {}
        for payload in self.payloads:
            if payload["plan_class"] == plan_class:
                found.setdefault((payload["base_head"], tuple(payload["paths"]), payload["message"]), payload)
        return list(found.values())

    def assert_preflight_ran_under(self, payload: dict) -> None:
        """§7.3: exactly its paths, under exactly its basis, while HEAD was still its parent."""
        self.assertIn((payload["attr_basis"], tuple(payload["paths"]), payload["base_head"]), self.evaluations)

    def assert_pinned_to_its_own_parent(self, plan_class: str) -> list[dict]:
        commits = self.of_class(plan_class)
        self.assertTrue(commits, f"no {plan_class} commit was made")
        for payload in commits:
            with self.subTest(commit=payload["message"]):
                self.assertEqual(payload["attr_basis"], payload["base_head"], "C3-2: its own exact recorded parent")
                self.assert_preflight_ran_under(payload)
        return commits

    def declared_base(self, record: dict) -> str:
        (run_id,) = [v for k, v in record["reserved_ids"].items() if k.startswith("review-run:work-result-v1:")]
        chain = ReviewStore(self.store).gate_chain(run_id)
        snapshot = ReviewStore(self.store).read_candidate_snapshot(chain.generations[0].candidate_hash)
        return snapshot.material["candidate"]["declared_base"]["base_commit"]

    def test_a_derived_registration_is_pinned_to_its_parent_and_the_later_classes_to_the_declared_base(self) -> None:
        outcomes = [st.Derive({"extra": st.DerivedWork("Extra", "more")}), None]

        def execute(ctx):
            outcome = outcomes.pop(0)
            if outcome is not None:
                return outcome
            (self.root / "out.txt").write_bytes(b"out\n")
            return st.Completed(("out.txt",))

        _, record = self.complete(execute)
        (derived,) = self.assert_pinned_to_its_own_parent("work-stage")
        self.assertIn("derive from", derived["message"])
        base = self.declared_base(record)
        self.assertNotEqual(derived["base_head"], base, "made before the declared base existed, so never pinned to it")
        for entry in self.of_class("entry"):
            self.assertEqual(entry["attr_basis"], entry["base_head"], "S-c0: PRE_S_C0_BASE, its own exact parent")
            self.assert_preflight_ran_under(entry)
        later = self.of_class("generation") + self.of_class("result") + self.of_class("terminal")
        self.assertEqual([p["plan_class"] for p in later], ["generation"] * 3 + ["result", "terminal"])
        for payload in later:
            with self.subTest(commit=payload["message"]):
                self.assertEqual(payload["attr_basis"], base, "declared_base.base_commit")
                self.assert_preflight_ran_under(payload)
        # the durable record keeps exactly that basis for the commit it made
        recorded = [e["payload"] for e in record["effects"]
                    if e["kind"] == "git_commit" and e["payload"]["plan_class"] == "work-stage"]
        self.assertEqual([(p["attr_basis"], p["base_head"]) for p in recorded], [(derived["attr_basis"], derived["base_head"])])

    def test_a_move_is_pinned_to_its_own_parent(self) -> None:
        move = st.Derive({"fix": st.DerivedWork("Fix", "fixed", derivation_detail="why Fix")}, move=True)
        result = st.start(self.store, self.work_id, "single-work", lambda ctx: move, review=self.review())
        self.assertEqual(result.status, "moved")
        (moved,) = self.assert_pinned_to_its_own_parent("work-stage")
        self.assertEqual(moved["base_head"], git(self.root, "rev-parse", "HEAD~1"))
        self.assertEqual(self.of_class("generation") + self.of_class("result"), [], "a move is never reviewed")

    def test_a_human_ng_move_is_pinned_to_its_own_parent(self) -> None:
        from helpers import completing_executor

        for work in (self.work_id, self.phase_entry.integration_id):  # the confirmation's prerequisites, legacy
            self.assertEqual(st.start(self.store, work, "single-work", completing_executor(self.store)).status, "completed")
        self.payloads.clear()
        self.evaluations.clear()
        ng = st.HumanNG({"f1": st.DerivedWork("F1", "defect fixed", derivation_detail="why F1")},
                        st.DerivedWork("I2", "re-integrated"))
        result = st.start(self.store, self.phase_entry.confirmation_id, "single-work", lambda ctx: ng, review=self.review())
        self.assertEqual(result.status, "moved")
        (moved,) = self.assert_pinned_to_its_own_parent("work-stage")
        self.assertEqual(moved["base_head"], git(self.root, "rev-parse", "HEAD~1"))

    def test_a_hold_is_pinned_to_its_own_parent(self) -> None:
        result = st.start(self.store, self.work_id, "single-work", lambda ctx: st.Hold("waiting"), review=self.review())
        self.assertEqual(result.status, "held")
        (held,) = self.assert_pinned_to_its_own_parent("work-stage")
        self.assertEqual(held["base_head"], git(self.root, "rev-parse", "HEAD~1"))


if __name__ == "__main__":
    unittest.main()
