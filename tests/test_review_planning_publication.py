"""P2 §28 G: publication - windows, no push before proof, the discriminator, and the cross-operation barrier."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from helpers import git
from planning_helpers import (
    Crash, PlanningTestCase, Reviewer, crash_at, design, executable_registration, noncanonical_registration, plan, rr,
    run_ids,
)
from workline import gitcmd, gitops
from workline import mutation as mutation_module
from workline import roadmap as rm
from workline.errors import ReconcileRequired, StopError
from workline.mutation import Mutation, MutationController, _Refused, _recorded_publication
from workline.review import publication
from workline.review import paths as review_paths
from workline.review.store import ReviewStore

KM_MESSAGE = "record review consumption"


def _is_commit(message: str):
    """A ``when`` for the planning commit primitive: the commit whose message holds ``message``."""
    return lambda n, store, payload, paths: message in payload.get("message", "")


def _is_kp(n, store, payload, paths) -> bool:
    return payload.get("base_exact") is True


def _changed_authority():
    real = rr.planning._read_authority
    return mock.patch.object(
        rr.planning, "_read_authority", lambda path: real(path) + (b"\nchanged\n" if str(path).endswith("registry.md") else b"")
    )


class _PublishCase(PlanningTestCase):
    """A review-v1 Roadmap creation in a Project with a push destination and another, legacy Roadmap."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project(remote=True)
        self.other = rm.create_roadmap(self.store, plan("Other Roadmap")).roadmap_id
        self.published_before = self.remote_head()
        self.reviewer = Reviewer()

    def run_plan(self):
        return self.reviewed_roadmap(self.store, self.reviewer)

    def crash(self, target, name, **kwargs) -> None:
        with crash_at(target, name, **kwargs):
            with self.assertRaises(Crash):
                self.run_plan()

    def planning_record(self) -> dict:
        (record,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-create"]
        return record

    def stage_effect(self, stage: str) -> dict:
        (effect,) = [e for e in self.planning_record()["effects"] if e["stage"] == stage]
        return effect

    def pushes_recorded(self) -> list[dict]:
        return [e for e in self.planning_record()["effects"] if e["kind"] == "git_push"]

    def assert_published(self, result) -> None:
        self.assertEqual("registered", result.status)
        self.assertEqual(result.registration.head, self.remote_head())
        self.assertEqual([], self.pending(self.store))

    def assert_barrier(self, call) -> StopError:
        with self.assertRaises(StopError) as raised:
            call()
        self.assertEqual("review_publication_barrier", raised.exception.code)
        return raised.exception

    def hold_other(self):
        return rm.hold_roadmap(self.store, self.other)

    def nothing_published(self) -> None:
        self.assertEqual(self.published_before, self.remote_head(), "the destination received nothing")

    def registration_adders(self) -> list[str]:
        """The commits of HEAD's history that add the planning Roadmap's file (its registration commits)."""
        (run_id,) = run_ids(self.store)
        chain = self.chain(self.store, run_id)
        material = ReviewStore(self.store).read_candidate_snapshot(chain.generations[0].candidate_hash).material
        return git(self.store.root, "log", "--format=%H", "--diff-filter=A", "--", rr.entity_paths(material)[0]).split()


# --------------------------------------------------------------------------- §21.1 rows 19-34

class WindowTests(_PublishCase):
    """Interruption at every commit, proof and publish boundary: §21.1 rows 19-34 (row 25: CrossOperationBarrierTests)."""

    def test_row_19_registration_applied_before_the_pre_kp_proof(self) -> None:
        self.crash(rr, "_pre_kp_proof")
        self.assert_published(self.run_plan())

    def test_row_20_head_advanced_after_the_use_check(self) -> None:
        self.crash(rr, "_pre_kp_proof")
        (self.store.root / "notes.txt").write_text("a person's unrelated change\n", encoding="utf-8")
        advanced = self.commit_all(self.store, "an unrelated commit", "notes.txt")
        result = self.run_plan()
        self.assert_published(result)
        consumption = ReviewStore(self.store).read_consumption(result.consumption_id)
        self.assertEqual(advanced, consumption.persisted_result["registration_parent"])

    def test_row_21_kp_recorded_not_made(self) -> None:
        self.crash(mutation_module, "_make_planning_commit", when=_is_kp)
        base_head = self.stage_effect(rr.STAGE_KP)["payload"]["base_head"]
        result = self.run_plan()
        self.assert_published(result)
        consumption = ReviewStore(self.store).read_consumption(result.consumption_id)
        self.assertEqual(base_head, consumption.persisted_result["registration_parent"])

    def test_row_21_head_moved_before_kp_is_made(self) -> None:
        self.crash(mutation_module, "_make_planning_commit", when=_is_kp)
        (self.store.root / "notes.txt").write_text("moved\n", encoding="utf-8")
        self.commit_all(self.store, "HEAD moves", "notes.txt")
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_registration_base_moved", raised.exception.reason)
        self.assertEqual([], self.registration_adders(), "Kp is not made")
        self.nothing_published()

    def test_row_22_kp_made_without_its_saved_id(self) -> None:
        self.crash(mutation_module, "_make_planning_commit", after=True, when=_is_kp)
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_commit_unowned", raised.exception.reason)
        self.assertFalse(ReviewStore(self.store).consumption_ids())
        self.assert_barrier(self.hold_other)
        self.nothing_published()

    def test_row_23_kp_made_before_its_proof(self) -> None:
        self.crash(rr, "_c2_kp")
        self.assert_published(self.run_plan())

    def test_row_24_a_failed_proof_is_repeated_by_every_retry(self) -> None:
        with executable_registration():
            with self.assertRaises(ReconcileRequired) as first:
                self.run_plan()
        self.assertEqual("review_persisted_proof_failed", first.exception.reason)
        self.assertIn("C-2(Kp) P3 fails", str(first.exception))
        for _ in range(2):
            with self.assertRaises(ReconcileRequired) as again:
                self.run_plan()
            self.assertEqual("review_persisted_proof_failed", again.exception.reason)
            self.assertIn("C-2(Kp) P3 fails", str(again.exception))
        self.assertFalse(ReviewStore(self.store).consumption_ids())
        self.assertEqual(3, self.chain(self.store, run_ids(self.store)[0]).latest.generation, "no generation 4")
        self.assert_barrier(self.hold_other)
        self.nothing_published()

    def test_row_26_proof_passed_consumption_not_recorded(self) -> None:
        self.crash(rr, "_consumption_record")
        calls: list[str] = []
        real = rr._c2_kp

        def counted(*args, **kwargs):
            calls.append("c2_kp")
            return real(*args, **kwargs)

        with mock.patch.object(rr, "_c2_kp", counted):
            self.assert_published(self.run_plan())
        self.assertEqual(["c2_kp"], calls, "the proof runs again: the recorded Consumption effect is the checkpoint")

    def test_row_27_consumption_recorded_not_created(self) -> None:
        self.crash(MutationController, "_create_review_record", when=lambda n, self_, relative, content: "/consumptions/" in relative)
        self.assertFalse(ReviewStore(self.store).consumption_ids())
        self.assert_published(self.run_plan())

    def test_row_27_consumption_created_with_its_flag_unsaved_is_matching(self) -> None:
        self.crash(MutationController, "_create_review_record", after=True,
                   when=lambda n, self_, relative, content: "/consumptions/" in relative)
        self.assertFalse(self.stage_effect(rr.STAGE_CONSUMPTION)["applied"])
        self.assert_published(self.run_plan())

    def test_row_27_other_bytes_at_the_consumption_path_reconcile(self) -> None:
        self.crash(MutationController, "_create_review_record",
                   when=lambda n, self_, relative, content: "/consumptions/" in relative)
        path = self.store.root / self.stage_effect(rr.STAGE_CONSUMPTION)["payload"]["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("other: bytes\n", encoding="utf-8", newline="\n")
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertIsNone(raised.exception.reason, "the live create_file classification keeps reason None")
        self.assertFalse([e for e in self.planning_record()["effects"] if e["stage"] == rr.STAGE_KM])
        self.nothing_published()

    def test_row_28_km_not_recorded(self) -> None:
        self.crash(gitops, "review_commit_effect", when=lambda n, store, message, paths, **kw: KM_MESSAGE in message)
        self.assertTrue(self.stage_effect(rr.STAGE_CONSUMPTION)["applied"])
        self.assert_published(self.run_plan())

    def test_row_28_km_recorded_not_made(self) -> None:
        self.crash(mutation_module, "_make_planning_commit", when=_is_commit(KM_MESSAGE))
        self.assert_published(self.run_plan())

    def test_row_28_km_made_without_its_saved_id_is_unowned(self) -> None:
        self.crash(mutation_module, "_make_planning_commit", after=True, when=_is_commit(KM_MESSAGE))
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_commit_unowned", raised.exception.reason)
        self.assertEqual([], self.pushes_recorded())
        self.nothing_published()

    def test_row_29_km_made_before_its_proof(self) -> None:
        self.crash(rr, "_c2_km")
        self.assert_published(self.run_plan())

    def test_row_29_a_failing_metadata_proof_pushes_nothing(self) -> None:
        real = gitcmd.contained_commit

        def km_with_an_extra_path(repo, message, paths, hooks):
            if KM_MESSAGE in message:
                (Path(repo) / "extra.txt").write_text("carried along\n", encoding="utf-8", newline="\n")
                git(repo, "add", "extra.txt")
                paths = list(paths) + ["extra.txt"]
            real(repo, message, paths, hooks)

        with mock.patch.object(gitcmd, "contained_commit", km_with_an_extra_path):
            with self.assertRaises(ReconcileRequired) as raised:
                self.run_plan()
        self.assertEqual("review_metadata_commit_mismatch", raised.exception.reason)
        self.assertIn("M3", str(raised.exception))
        self.assertEqual([], self.pushes_recorded())
        self.assertNotIn(rr.NOTE_PUBLICATION_PROOF, self.planning_record()["notes"])
        with self.assertRaises(ReconcileRequired) as again:
            self.run_plan()
        self.assertEqual("review_metadata_commit_mismatch", again.exception.reason)
        self.assert_barrier(self.hold_other)
        self.nothing_published()

    def test_row_30_proof_passed_note_not_recorded(self) -> None:
        self.crash(Mutation, "set_note", when=lambda n, self_, key, value: key == rr.NOTE_PUBLICATION_PROOF)
        self.assertNotIn(rr.NOTE_PUBLICATION_PROOF, self.planning_record()["notes"])
        self.assert_published(self.run_plan())

    def test_row_31_note_recorded_push_stage_not_recorded(self) -> None:
        self.crash(gitops, "review_publication_effect")
        self.assertIn(rr.NOTE_PUBLICATION_PROOF, self.planning_record()["notes"])
        self.assertEqual([], self.pushes_recorded())
        self.assert_published(self.run_plan())

    def test_row_32_push_recorded_not_applied(self) -> None:
        self.crash(gitcmd, "push")
        self.nothing_published()
        self.assert_published(self.run_plan())

    def test_row_33_pushed_with_applied_unsaved_pushes_nothing_again(self) -> None:
        self.crash(gitcmd, "push", after=True)
        km = self.stage_effect(rr.STAGE_PUBLICATION)["payload"]["commit"]
        self.assertEqual(km, self.remote_head())
        with mock.patch.object(gitcmd, "push", side_effect=AssertionError("pushed again")):
            self.assert_published(self.run_plan())

    def test_row_34_published_before_complete(self) -> None:
        self.crash(Mutation, "complete", when=lambda n, self_: self_.invocation.get("operation") == "roadmap-create")
        self.assertNotEqual(self.published_before, self.remote_head())
        with mock.patch.object(gitcmd, "push", side_effect=AssertionError("pushed again")):
            self.assert_published(self.run_plan())


# --------------------------------------------------------------------------- no push before proof

class NoPushBeforeProofTests(_PublishCase):
    def test_no_git_push_is_recorded_before_c2_km_and_its_committed_planning_proof_pass(self) -> None:
        order: list[str] = []
        real_c2 = rr._c2_km
        real_proof = publication.committed_planning_proof
        real_add = Mutation.add_effects

        def c2(op, mutation, *args, **kwargs):
            self.assertFalse([e for e in mutation.effects if e["kind"] == "git_push"], "a push before C-2(Km)")
            found = real_c2(op, mutation, *args, **kwargs)
            order.append("c2_km passed")
            return found

        def proof(repo, commit, run):
            found = real_proof(repo, commit, run)
            order.append("committed proof " + ("passed" if found is None else "failed"))
            return found

        def add(self_, stage, effects):
            if any(effect.kind == "git_push" for effect in effects):
                order.append(f"push recorded in {stage}")
            return real_add(self_, stage, effects)

        with mock.patch.object(rr, "_c2_km", c2), mock.patch.object(publication, "committed_planning_proof", proof), \
                mock.patch.object(Mutation, "add_effects", add):
            self.assert_published(self.run_plan())
        pushed_at = order.index("push recorded in review-publication")
        # M6 runs the committed planning proof inside C-2(Km); the barrier runs it again before the stage is recorded
        self.assertEqual(["committed proof passed", "c2_km passed", "committed proof passed"], order[:pushed_at])
        self.assertEqual(1, order.count("push recorded in review-publication"))


# --------------------------------------------------------------------------- foreign commits

class ForeignCommitTests(_PublishCase):
    """A byte-identical Kp or Km made by another subject is never adopted or pushed as the operation's own (§18.2)."""

    def test_a_foreign_byte_identical_kp_is_unowned_and_never_published(self) -> None:
        self.crash(mutation_module, "_make_planning_commit", when=_is_kp)
        kp_effect = self.stage_effect(rr.STAGE_KP)
        git(self.store.root, "add", "--", *kp_effect["payload"]["paths"])
        git(self.store.root, "commit", "-q", "-m", kp_effect["payload"]["message"])
        foreign = self.head(self.store)
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_commit_unowned", raised.exception.reason)
        self.assertNotEqual(foreign, self.stage_effect(rr.STAGE_KP).get("commit_id"), "never adopted")
        self.assertFalse(ReviewStore(self.store).consumption_ids())
        self.assertIsNotNone(publication.barrier_problem(self.store.root, foreign))
        self.assert_barrier(self.hold_other)
        self.nothing_published()

    def test_a_foreign_byte_identical_km_is_unowned_and_reaches_the_destination_only_as_proven_history(self) -> None:
        self.crash(mutation_module, "_make_planning_commit", when=_is_commit(KM_MESSAGE))
        km_effect = self.stage_effect(rr.STAGE_KM)
        git(self.store.root, "add", "--", *km_effect["payload"]["paths"])
        git(self.store.root, "commit", "-q", "-m", km_effect["payload"]["message"])
        foreign = self.head(self.store)
        for _ in range(2):
            with self.assertRaises(ReconcileRequired) as raised:
                self.run_plan()
            self.assertEqual("review_commit_unowned", raised.exception.reason)
            self.assertEqual([], self.pushes_recorded(), "never pushed as its own")
        self.assertNotEqual(foreign, self.stage_effect(rr.STAGE_KM).get("commit_id"))
        self.nothing_published()
        # the committed planning proof passes for the foreign Km, so another operation's push carries it as history
        self.assertIsNone(publication.barrier_problem(self.store.root, foreign))
        held = self.hold_other()
        self.assertEqual(held.head, self.remote_head())
        self.assertEqual(foreign, git(self.store.root, "rev-parse", f"{held.head}~1").strip())


# --------------------------------------------------------------------------- branch, history, remote

class BranchAndHistoryTests(_PublishCase):
    def test_a_branch_switch_reconciles_and_the_bound_branch_continues(self) -> None:
        self.crash(rr, "_c2_kp")
        git(self.store.root, "checkout", "-q", "-b", "elsewhere")
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_persisted_proof_failed", raised.exception.reason)  # C-2(Kp) P2: HEAD off the bound branch
        self.assertFalse(ReviewStore(self.store).consumption_ids())
        self.nothing_published()
        git(self.store.root, "checkout", "-q", "main")
        self.assert_published(self.run_plan())

    def test_rewritten_history_reconciles(self) -> None:
        self.crash(rr, "_c2_km")
        km = self.stage_effect(rr.STAGE_KM)["commit_id"]
        git(self.store.root, "commit", "-q", "--amend", "--no-verify", "-m", "a rewritten metadata commit")
        self.assertNotEqual(km, self.head(self.store))
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertIsNone(raised.exception.reason, "the live classification of the recorded metadata commit")
        self.assertEqual([], self.pushes_recorded())
        self.nothing_published()


class RemoteAdvancementTests(_PublishCase):
    def setUp(self) -> None:
        super().setUp()
        self.crash(gitcmd, "push")
        self.km = self.stage_effect(rr.STAGE_PUBLICATION)["payload"]["commit"]

    def test_a_fast_forward_from_an_advanced_destination(self) -> None:
        git(self.store.root, "push", "-q", "origin", f"{self.km}~2:refs/heads/main")  # a generation commit, by hand
        self.assertNotEqual(self.published_before, self.remote_head())
        self.assert_published(self.run_plan())
        self.assertEqual(self.km, self.remote_head())

    def test_a_destination_ahead_holding_km_is_already_published(self) -> None:
        (self.store.root / "notes.txt").write_text("on top of Km\n", encoding="utf-8")
        ahead = self.commit_all(self.store, "a person's commit on top of Km", "notes.txt")
        git(self.store.root, "push", "-q", "origin", "HEAD:refs/heads/main")
        with mock.patch.object(gitcmd, "push", side_effect=AssertionError("pushed")):
            result = self.run_plan()
        self.assertEqual("registered", result.status)
        self.assertEqual(ahead, self.remote_head(), "left where it is")
        self.assertEqual([], self.pending(self.store))

    def test_a_diverged_destination_reconciles_and_nothing_is_forced(self) -> None:
        other = self.tmp / "another-clone"
        git(self.tmp, "clone", "-q", str(self.remote_path()), str(other))
        (other / "foreign.txt").write_text("foreign\n", encoding="utf-8")
        git(other, "add", "foreign.txt")
        git(other, "-c", "user.name=Other", "-c", "user.email=other@example.invalid", "commit", "-q", "-m", "foreign")
        git(other, "push", "-q", "origin", "HEAD:refs/heads/main")
        diverged = self.remote_head()
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertIsNone(raised.exception.reason, "the live push classification")
        self.assertEqual(diverged, self.remote_head(), "never forced")


class RetryPublishesExactlyKmTests(_PublishCase):
    def test_the_retry_pushes_exactly_km_whatever_the_branch_holds_by_then(self) -> None:
        self.crash(gitcmd, "push")
        km = self.stage_effect(rr.STAGE_PUBLICATION)["payload"]["commit"]
        (self.store.root / "notes.txt").write_text("local only\n", encoding="utf-8")
        local = self.commit_all(self.store, "a local commit on top of Km", "notes.txt")
        pushed: list[str] = []
        real = gitcmd.push

        def spy(repo, remote, refspec):
            pushed.append(refspec)
            return real(repo, remote, refspec)

        with mock.patch.object(gitcmd, "push", spy):
            result = self.run_plan()
        self.assertEqual("registered", result.status)
        self.assertEqual([f"{km}:refs/heads/main"], pushed)
        self.assertEqual(km, self.remote_head())
        self.assertNotEqual(local, self.remote_head())


# --------------------------------------------------------------------------- the discriminator

class DiscriminatorTests(PlanningTestCase):
    """The durable invocation selects the publication rule; shape and content never do (§18.5)."""

    MARKERS = {"review_contract": "review-v1-planning-v1", "publication_contract": "review-v1-planning-publication-v1"}

    def setUp(self) -> None:
        super().setUp()
        self.repo = self.planning_project().root

    def _effects(self, combined: bool, *, message: str = "m") -> list[dict]:
        commit = {"seq": 1, "stage": "finalize" if combined else rr.STAGE_KM, "kind": "git_commit",
                  "payload": {"message": message, "paths": ["a"], "base_head": "a" * 40, "branch": "refs/heads/main"},
                  "applied": True, "commit_id": "b" * 40}
        push = {"seq": 2, "stage": "finalize" if combined else rr.STAGE_PUBLICATION, "kind": "git_push",
                "payload": {"remote": "origin", "branch": "main", "locator": "x", "commit": "b" * 40}, "applied": False}
        return [commit, push]

    def test_legacy_is_the_current_combined_rule_unchanged(self) -> None:
        legacy = {"invocation": {"operation": "roadmap-create", "name": "n", "request": {}}}
        without_record = _recorded_publication(self.repo, self._effects(True), 1)
        self.assertIsInstance(without_record, str, "the live rule answers (here: it cannot show the fixture commit)")
        self.assertEqual(without_record, _recorded_publication(self.repo, self._effects(True), 1, legacy))

    def test_a_combined_pair_in_a_planning_mutation_is_refused(self) -> None:
        for invocation in (
            {"operation": "roadmap-create", **self.MARKERS},
            {"operation": "phase-entry", **self.MARKERS},
            {"operation": "roadmap-create", **self.MARKERS, "recovery_of_review_run_id": "rvr_01ARZ3NDEKTSV4RRFFQ69G5FAV"},
        ):
            refused = _recorded_publication(self.repo, self._effects(True), 1, {"invocation": invocation, "notes": {}})
            self.assertIsInstance(refused, _Refused)
            self.assertEqual("review_publication_contract_invalid", refused.reason)

    def test_a_push_in_a_generation_mutation_is_refused(self) -> None:
        for invocation in ({"operation": "review-generation", **self.MARKERS}, {"operation": "review-generation"}):
            for combined in (True, False):
                refused = _recorded_publication(self.repo, self._effects(combined), 1, {"invocation": invocation})
                self.assertEqual("review_publication_contract_invalid", refused.reason)

    def test_unknown_or_partial_markers_fail_closed(self) -> None:
        for invocation in (
            {"operation": "roadmap-create", "review_contract": "review-v1-planning-v1"},
            {"operation": "roadmap-create", "publication_contract": "review-v1-planning-publication-v1"},
            {"operation": "roadmap-create", "review_contract": "review-v2", "publication_contract": "review-v1-planning-publication-v1"},
            {"operation": "roadmap-create", "review_contract": "review-v1-planning-v1", "publication_contract": "other"},
            {"operation": "work-start", **self.MARKERS},
        ):
            for combined in (True, False):
                refused = _recorded_publication(self.repo, self._effects(combined), 1, {"invocation": invocation})
                self.assertIsInstance(refused, _Refused, invocation)
                self.assertEqual("review_publication_contract_invalid", refused.reason)

    def test_shape_and_content_never_select(self) -> None:
        legacy = {"invocation": {"operation": "roadmap-create", "name": "n", "request": {}}}
        # a planning-shaped pair (a push-only stage, the planning stage names, a consumption message) in a legacy mutation
        found = _recorded_publication(self.repo, self._effects(False, message=f"chore(workline): {KM_MESSAGE} rcs_x"), 1, legacy)
        self.assertIsInstance(found, str, "judged by the current-combined rule")
        # a planning mutation's push whose publication proof note does not name its commit publishes nothing
        planning_record = {"invocation": {"operation": "roadmap-create", **self.MARKERS}, "notes": {}}
        self.assertEqual("review_publication_invalid", _recorded_publication(self.repo, self._effects(False), 1, planning_record).reason)


class RemoteLessTests(PlanningTestCase):
    def test_a_remote_less_project_completes_without_a_push_or_a_barrier(self) -> None:
        store = self.planning_project()
        proofs: list[str] = []
        real = rr._c2_km

        def c2(*args, **kwargs):
            proofs.append("c2_km")
            return real(*args, **kwargs)

        with mock.patch.object(publication, "barrier_problem", side_effect=AssertionError("barrier evaluated")), \
                mock.patch.object(gitcmd, "push", side_effect=AssertionError("pushed")), mock.patch.object(rr, "_c2_km", c2):
            result = self.reviewed_roadmap(store)
        self.assertEqual("registered", result.status)
        self.assertEqual(["c2_km"], proofs, "C-2(Km) completes the operation")
        self.assertEqual([], self.pending(store))


# --------------------------------------------------------------------------- P2-CONTRACT-001: the barrier

class CrossOperationBarrierTests(_PublishCase):
    """§21.1 row 25: no Workline push of any operation publishes an unproven registration commit."""

    def test_an_unrelated_operation_waits_for_the_proof_and_is_then_published_on_top_of_km(self) -> None:
        self.crash(rr, "_c2_kp")
        kp = self.head(self.store)
        self.assert_barrier(self.hold_other)
        self.nothing_published()
        (hold,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-hold"]
        self.assertEqual({"event"}, {e["stage"] for e in hold["effects"]}, "its Git stage is not recorded")
        self.assertTrue(all(e["applied"] for e in hold["effects"]), "its domain effects are applied")
        self.assertEqual(kp, self.head(self.store), "and it made no commit")
        result = self.run_plan()
        self.assertEqual(result.registration.head, self.remote_head())
        held = self.hold_other()
        self.assertEqual(held.head, self.remote_head())
        self.assertEqual(result.registration.head, git(self.store.root, "rev-parse", f"{held.head}~1").strip())
        self.assertEqual([], self.pending(self.store))

    def test_a_stage_recorded_before_kp_and_made_on_kp_is_refused_at_classification_and_at_application(self) -> None:
        with crash_at(mutation_module, "_make_commit", when=lambda n, mutation, record: "roadmap_held" in record["payload"]["message"]):
            with self.assertRaises(Crash):
                self.hold_other()
        self.crash(rr, "_c2_kp")
        kp = self.head(self.store)
        pushed: list[str] = []
        real_push = gitcmd.push

        def spy(repo, remote, refspec):
            pushed.append(refspec)
            return real_push(repo, remote, refspec)

        with mock.patch.object(gitcmd, "push", spy):
            self.assert_barrier(self.hold_other)  # its commit is made on Kp, and the dry run shows a write
            (hold,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-hold"]
            hold_commit = [e for e in hold["effects"] if e["kind"] == "git_commit"][0]["commit_id"]
            self.assertEqual(kp, git(self.store.root, "rev-parse", f"{hold_commit}~1").strip(), "made on Kp")
            with mock.patch.object(MutationController, "_classify_push",
                                   lambda self_, payload, found: mutation_module.UNAPPLIED):
                self.assert_barrier(self.hold_other)  # classification patched: refused right before the push
        self.assertEqual([], pushed, "nothing pushed")
        self.nothing_published()
        result = self.run_plan()
        self.assertEqual(result.registration.head, self.remote_head())
        with mock.patch.object(gitcmd, "push", side_effect=AssertionError("a commit between Kp and Km pushed by itself")):
            self.hold_other()  # classified already published
        self.assertEqual(result.registration.head, self.remote_head())
        self.assertEqual([], self.pending(self.store))


class AnotherRunsUnprovenKpTests(_PublishCase):
    """§21.1 row 31: the barrier holds the planning push only while some registered Run of Km's history is unproven."""

    def test_another_runs_unproven_registration_commit_holds_the_planning_push(self) -> None:
        main_plan = plan("Main Roadmap", relations=False)
        # sealed, then the process dies before the use check (a merge between Kp and Km would fail M1)
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store, self.reviewer, main_plan)
        # a second clone registers another Run and loses its process before C-2(Kp): its Kp is unproven
        side = self.fresh_clone(self.remote_path(), "side")
        git(side.root, "remote", "set-url", "origin", str(self.remote_path()))
        self.enter(side.root)
        with crash_at(rr, "_c2_kp"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(side, Reviewer(), plan("Side Roadmap", relations=False))
        side_kp = self.head(side)
        # a person merges that history into the branch before this Run's use check
        self.enter(self.store.root)
        git(self.store.root, "fetch", "-q", str(side.root), "main:refs/heads/side")
        git(self.store.root, "-c", "user.name=Person", "-c", "user.email=person@example.invalid",
            "merge", "-q", "--no-ff", "--no-edit", "side")
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(self.store, self.reviewer, main_plan)
        self.assertEqual("review_publication_barrier", raised.exception.code)
        self.assertIn(side_kp, str(raised.exception), "the other Run's registration commit")
        record = self.planning_record()
        self.assertEqual([], self.pushes_recorded(), "the push stage is not recorded")
        self.assertTrue(any(e["stage"] == rr.STAGE_KM and e.get("applied") for e in record["effects"]), "Km is made")
        self.assertIn(rr.NOTE_PUBLICATION_PROOF, record["notes"], "C-2(Km) passed for this Run")
        self.nothing_published()


class RetryAfterProofTests(_PublishCase):
    def test_pushes_from_km_and_its_descendants_pass_once_the_proof_passes(self) -> None:
        self.crash(gitcmd, "push")
        km = self.stage_effect(rr.STAGE_PUBLICATION)["payload"]["commit"]
        self.assertIsNone(publication.barrier_problem(self.store.root, km))
        held = self.hold_other()  # a descendant of Km: the committed planning proof passes for it
        self.assertEqual(held.head, self.remote_head())
        self.assertEqual(km, git(self.store.root, "rev-parse", f"{held.head}~1").strip())
        with mock.patch.object(gitcmd, "push", side_effect=AssertionError("pushed")):
            result = self.run_plan()  # Km is already published: classified matching
        self.assertEqual("registered", result.status)
        self.assertEqual([], self.pending(self.store))

    def test_a_commit_between_kp_and_km_is_not_publishable_by_itself(self) -> None:
        self.crash(rr, "_c2_km")
        kp = self.stage_effect(rr.STAGE_KP)["commit_id"]
        km = self.stage_effect(rr.STAGE_KM)["commit_id"]
        self.assertIsNotNone(publication.barrier_problem(self.store.root, kp))
        self.assertIsNone(publication.barrier_problem(self.store.root, km))


class ProofFailureTests(_PublishCase):
    """A Kp proof failure keeps every later Workline push of a history holding Kp refused, legacy and review-v1."""

    def setUp(self) -> None:
        super().setUp()
        with noncanonical_registration():
            with self.assertRaises(ReconcileRequired) as raised:
                self.run_plan()
        self.assertEqual("review_persisted_proof_failed", raised.exception.reason)
        self.assertIn("C-2(Kp) P3 fails", str(raised.exception))
        self.kp = self.head(self.store)

    def legacy_create_is_refused(self, name: str) -> None:
        with self.assertRaises(StopError) as raised:
            rm.create_roadmap(self.store, plan(name))
        self.assertEqual("review_publication_barrier", raised.exception.code)
        self.nothing_published()

    def review_v1_is_refused_at_its_freeze(self) -> None:
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(self.store, Reviewer(), plan("Another Reviewed Roadmap"))
        self.assertEqual("review_publication_barrier", raised.exception.code)
        self.assertEqual([], [r for r in self.pending(self.store) if r["invocation"].get("name") == "Another Reviewed Roadmap"])
        self.nothing_published()

    def test_legacy_pushes_are_refused_and_review_v1_cannot_begin_beside_the_pending_planning_mutation(self) -> None:
        self.assert_barrier(self.hold_other)
        # while the planning mutation is pending, another Roadmap creation overlaps its scope (the live rule)
        with self.assertRaises(ReconcileRequired) as raised:
            self.reviewed_roadmap(self.store, Reviewer(), plan("Another Reviewed Roadmap"))
        self.assertIsNone(raised.exception.reason)
        self.nothing_published()

    def test_across_a_process_crash(self) -> None:
        with crash_at(gitops, "finalize"):
            with self.assertRaises(Crash):
                self.hold_other()
        self.assert_barrier(self.hold_other)
        self.assert_barrier(self.hold_other)
        self.nothing_published()
        # the review-v1 side, after the crash: every planning retry is refused and publishes nothing
        for _ in range(2):
            with self.assertRaises(ReconcileRequired) as raised:
                self.run_plan()
            # the fixture left other bytes in the registration file than the mutation wrote: the live replay refuses
            self.assertIsNone(raised.exception.reason)
            self.assertIn("applied with unexpected result", str(raised.exception))
        self.assertEqual([], self.pushes_recorded())
        self.assertEqual(self.kp, self.registration_adders()[0])
        self.nothing_published()

    def test_across_runtime_record_loss(self) -> None:
        for record in self.store.mutations.glob("*.yaml"):
            record.unlink()
        self.review_v1_is_refused_at_its_freeze()
        self.legacy_create_is_refused("After Record Loss")

    def test_across_a_deleted_runtime_directory(self) -> None:
        self.runtime_gone(self.store)
        self.review_v1_is_refused_at_its_freeze()
        self.legacy_create_is_refused("After Runtime Loss")

    def test_in_a_fresh_clone(self) -> None:
        clone = self.fresh_clone(self.store.root, "clone")
        git(clone.root, "remote", "set-url", "origin", str(self.remote_path()))  # the pinned destination
        self.assertEqual(self.kp, self.head(clone))
        self.assertIsNotNone(publication.barrier_problem(clone.root, self.kp))
        self.enter(clone.root)
        with self.assertRaises(StopError) as raised:
            rm.hold_roadmap(clone, self.other)
        self.assertEqual("review_publication_barrier", raised.exception.code)
        with self.assertRaises(StopError) as review_v1:
            self.reviewed_roadmap(clone, Reviewer(), plan("A Reviewed Roadmap In The Clone"))
        self.assertEqual("review_publication_barrier", review_v1.exception.code)
        self.nothing_published()


class RuntimeLossWithUnprovenKpTests(_PublishCase):
    """Runtime-record loss with Kp unproven: the barrier holds for good, and nothing lifts or bypasses it."""

    def setUp(self) -> None:
        super().setUp()
        self.base = rm.create_roadmap(self.store, plan("Base Roadmap"))
        self.published_before = self.remote_head()

    def test_roadmap_creation(self) -> None:
        self.crash(rr, "_c2_kp")
        self.runtime_gone(self.store)
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_recovery_incomplete", raised.exception.reason)
        with self.assertRaises(StopError) as frozen:
            self.reviewed_entry(self.store, self.base.phase_ids["a"])  # another review-v1 call with a destination
        self.assertEqual("review_publication_barrier", frozen.exception.code)
        self.assertEqual([], [r for r in self.pending(self.store) if r["invocation"].get("operation") == "phase-entry"])
        with self.assertRaises(StopError) as legacy:
            rm.create_roadmap(self.store, plan("Legacy Roadmap"))
        self.assertEqual("review_publication_barrier", legacy.exception.code)
        (created,) = [r for r in self.pending(self.store) if r["invocation"].get("name") == "Legacy Roadmap"]
        self.assertTrue(created["effects"] and all(e["applied"] for e in created["effects"]), "it registers")
        self.nothing_published()

    def test_phase_entry(self) -> None:
        phase_id = self.base.phase_ids["a"]
        with crash_at(rr, "_c2_kp"):
            with self.assertRaises(Crash):
                self.reviewed_entry(self.store, phase_id)
        self.runtime_gone(self.store)
        with self.assertRaises(StopError) as raised:
            self.reviewed_entry(self.store, phase_id)
        self.assertEqual("phase_already_expanded", raised.exception.code)
        with self.assertRaises(StopError) as legacy:
            rm.enter_phase(self.store, phase_id, design())
        self.assertEqual("phase_already_expanded", legacy.exception.code)
        self.assert_barrier(self.hold_other)
        self.nothing_published()


class ManualPushTests(_PublishCase):
    def test_a_manual_push_of_kp_is_detected_and_never_proof(self) -> None:
        self.crash(rr, "_c2_kp")
        kp = self.head(self.store)
        git(self.store.root, "push", "-q", "origin", f"{kp}:refs/heads/main")  # a person pushes Kp by hand
        self.assertEqual(kp, self.remote_head())
        self.assertIsNotNone(publication.barrier_problem(self.store.root, kp), "the destination is never read as proof")
        self.assert_barrier(self.hold_other)  # a legacy push of a descendant is still refused
        self.assertEqual(kp, self.remote_head())
        with mock.patch.object(rr, "delta_problem", lambda repo, expected, commit: "forced mismatch"):
            with self.assertRaises(ReconcileRequired) as raised:
                self.run_plan()
        self.assertEqual("review_persisted_proof_failed", raised.exception.reason)
        self.assertFalse(ReviewStore(self.store).consumption_ids(), "no Consumption although Kp is at the destination")
        result = self.run_plan()  # the planning resume proves Kp over local objects, then publishes Km
        self.assertEqual(result.registration.head, self.remote_head())
        held = self.hold_other()
        self.assertEqual(held.head, self.remote_head())

    def test_a_push_classified_already_published_writes_nothing_and_proves_nothing(self) -> None:
        with crash_at(gitcmd, "push"):
            with self.assertRaises(Crash):
                self.hold_other()  # the hold's commit is made, its push recorded and not applied
        (hold,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-hold"]
        hold_commit = [e for e in hold["effects"] if e["kind"] == "git_commit"][0]["commit_id"]
        self.crash(rr, "_c2_kp")
        kp = self.head(self.store)
        self.assertIs(True, gitcmd.descends_from(self.store.root, kp, hold_commit))
        git(self.store.root, "push", "-q", "origin", f"{kp}:refs/heads/main")
        with mock.patch.object(gitcmd, "push", side_effect=AssertionError("pushed")):
            self.hold_other()  # the destination holds its commit: already published, nothing written
        self.assertEqual(kp, self.remote_head())
        with self.assertRaises(StopError) as raised:
            rm.resume_roadmap(self.store, self.other)  # a later push that would write is still held
        self.assertEqual("review_publication_barrier", raised.exception.code)
        self.assertEqual(kp, self.remote_head())


class PersonsCommitTests(_PublishCase):
    def test_a_persons_commit_of_the_registration_begins_the_barrier_and_is_unowned(self) -> None:
        self.crash(mutation_module, "_make_planning_commit", when=_is_kp)
        self.assertIsNone(publication.barrier_problem(self.store.root, self.head(self.store)), "nothing registered yet")
        git(self.store.root, "add", "--", *self.stage_effect(rr.STAGE_KP)["payload"]["paths"])
        git(self.store.root, "commit", "-q", "-m", "a person commits the registration")
        self.assertIsNotNone(publication.barrier_problem(self.store.root, self.head(self.store)), "the barrier begins")
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_commit_unowned", raised.exception.reason)
        self.assert_barrier(self.hold_other)
        self.nothing_published()


class HistoryDoesNotHideKpTests(_PublishCase):
    def setUp(self) -> None:
        super().setUp()
        self.crash(rr, "_c2_kp")
        self.kp = self.head(self.store)
        self.parent = git(self.store.root, "rev-parse", f"{self.kp}~1").strip()
        self.roadmap = [p for p in git(self.store.root, "show", "--name-only", "--format=", self.kp).splitlines()
                        if "/roadmaps/" in p][0]

    def test_deleting_the_snapshot_does_not_hide_kp(self) -> None:
        snapshot = git(self.store.root, "ls-files", review_paths.CANDIDATE_SNAPSHOTS_DIR).split()[0]
        git(self.store.root, "rm", "-q", snapshot)
        git(self.store.root, "commit", "-q", "-m", "delete the snapshot")
        self.assertIsNotNone(publication.barrier_problem(self.store.root, self.head(self.store)))
        self.assert_barrier(self.hold_other)

    def test_reverting_the_registration_does_not_hide_kp(self) -> None:
        git(self.store.root, "revert", "--no-edit", self.kp)
        self.assertFalse((self.store.root / self.roadmap).exists())
        self.assertIsNotNone(publication.barrier_problem(self.store.root, self.head(self.store)))
        self.assert_barrier(self.hold_other)

    def test_a_merge_bringing_in_a_side_branch_with_kp_is_found(self) -> None:
        git(self.store.root, "branch", "side", self.kp)
        git(self.store.root, "checkout", "-q", "-b", "mainline", self.parent)
        (self.store.root / "mainline.txt").write_text("mainline\n", encoding="utf-8")
        self.commit_all(self.store, "mainline", "mainline.txt")
        git(self.store.root, "merge", "-q", "--no-edit", "side")
        self.assertIsNotNone(publication.barrier_problem(self.store.root, self.head(self.store)))

    def test_an_evil_merge_adding_a_reserved_path_is_found(self) -> None:
        git(self.store.root, "checkout", "-q", "-b", "plain", self.parent)
        (self.store.root / "plain.txt").write_text("plain\n", encoding="utf-8")
        self.commit_all(self.store, "plain", "plain.txt")
        git(self.store.root, "checkout", "-q", "-b", "evil", self.parent)
        git(self.store.root, "merge", "-q", "--no-commit", "--no-ff", "plain")
        git(self.store.root, "checkout", self.kp, "--", self.roadmap)
        git(self.store.root, "commit", "-q", "-m", "an evil merge")
        merge = self.head(self.store)
        self.assertEqual(2, len(gitcmd.commit_parents(self.store.root, merge)))
        self.assertIs(False, gitcmd.descends_from(self.store.root, merge, self.kp), "Kp itself is not in its history")
        self.assertIsNotNone(publication.barrier_problem(self.store.root, merge))


class UnparseableSnapshotTests(_PublishCase):
    def test_an_unparseable_planning_snapshot_in_the_pushed_history_holds_the_barrier(self) -> None:
        relative = f"{review_paths.CANDIDATE_SNAPSHOTS_DIR}/{'a' * 64}.yaml"
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("not: [a canonical record\n", encoding="utf-8", newline="\n")
        self.commit_all(self.store, "an unreadable snapshot", relative)
        self.assertIsNotNone(publication.barrier_problem(self.store.root, self.head(self.store)))
        self.assert_barrier(self.hold_other)
        self.nothing_published()


class NothingRegisteredTests(_PublishCase):
    """No barrier where nothing was registered: a legacy push proceeds in each state (Git >= P2_PUBLICATION_GIT_MIN)."""

    def legacy_push_proceeds(self) -> None:
        held = self.hold_other()
        self.assertEqual(held.head, self.remote_head())

    def latest(self) -> int:
        (run_id,) = run_ids(self.store)
        return self.chain(self.store, run_id).latest.generation

    def test_generation_1_only(self) -> None:
        self.crash(rr, "_launch_and_settle")
        self.assertEqual(1, self.latest())
        self.legacy_push_proceeds()

    def test_generation_2(self) -> None:
        self.crash(rr, "_seal")
        self.assertEqual(2, self.latest())
        self.legacy_push_proceeds()

    def test_generation_3_without_a_registration_commit(self) -> None:
        self.crash(rr, "_use_check")
        self.assertEqual(3, self.latest())
        self.legacy_push_proceeds()

    def test_generation_4(self) -> None:
        self.crash(rr, "_use_check")
        with _changed_authority():
            result = self.run_plan()
        self.assertEqual("stale", result.status)
        self.assertEqual(4, self.latest())
        self.legacy_push_proceeds()

    def test_not_authorized(self) -> None:
        result = self.reviewed_roadmap(self.store, Reviewer(status="declined"))
        self.assertEqual("not_authorized", result.status)
        self.legacy_push_proceeds()

    def test_stale_before_a_receipt(self) -> None:
        self.crash(rr, "_launch_and_settle")
        with _changed_authority():
            result = self.run_plan()
        self.assertEqual(("stale", None), (result.status, result.receipt_id))
        self.legacy_push_proceeds()


class LegacyOnlyTests(PlanningTestCase):
    def test_a_legacy_only_project_refuses_nothing_and_reads_one_path_limited_history(self) -> None:
        store = self.new_project(remote=True)
        directories: list[str] = []
        real = gitcmd.history_touches

        def spy(repo, commit, directory):
            directories.append(directory)
            return real(repo, commit, directory)

        with mock.patch.object(gitcmd, "history_touches", spy), \
                mock.patch.object(publication, "registered_runs", side_effect=AssertionError("no proof in a legacy history")), \
                mock.patch.object(gitcmd, "running_git_version", side_effect=AssertionError("no version needed")):
            result = rm.create_roadmap(store, plan())
            rm.hold_roadmap(store, result.roadmap_id)
        self.assertEqual(self.head(store), self.remote_head())
        self.assertEqual(".workline/review/candidate-snapshots/", publication.FAST_PATH_DIRECTORY)
        self.assertTrue(directories)
        self.assertEqual({publication.FAST_PATH_DIRECTORY}, set(directories))


if __name__ == "__main__":
    unittest.main()
