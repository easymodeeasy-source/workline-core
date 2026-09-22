"""P2 §28 K: C-2(Km) and the committed planning proof - CP1-CP13, one fixture history per item, and the barrier."""

from __future__ import annotations

from dataclasses import replace
import unittest
from unittest import mock

from helpers import git
from planning_helpers import (
    Crash, PlanningTestCase, Reviewer, blob_at, crash_at, move_branch, plan, plumb_commit, registered, rr, run_ids,
)
from workline import gitcmd
from workline import mutation as mutation_module
from workline import roadmap as rm
from workline import yamlish
from workline.errors import ReconcileRequired, StopError
from workline.mutation import Mutation
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.review import planning, publication, records, serialize
from workline.review import paths as review_paths
from workline.review.store import ReviewStore

OTHER_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


class _ProvenCase(PlanningTestCase):
    """A published review-v1 Roadmap creation; fixture histories are built on its commits with plumbing only."""

    the_plan = None

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project(remote=True)
        other = rm.create_roadmap(self.store, rm.RoadmapPlan("Other", "背景", "状態", {"x": PhaseSpec("X", "X が成立する")}))
        self.other, self.x = other.roadmap_id, other.phase_ids["x"]
        self.result = self.reviewed_roadmap(self.store, Reviewer(), self.plan_for_x())
        self.reg = registered(self.store, self.result)
        self.repo = self.store.root
        self.published = self.remote_head()
        self.assertEqual(self.reg.km, self.published)
        self.run_id = self.result.review_run_id
        self.receipt_id = self.result.receipt_id

    def plan_for_x(self) -> rm.RoadmapPlan:
        return rm.RoadmapPlan(
            "Planned", "背景", "状態",
            {"a": PhaseSpec("A", "A が成立する"), "b": PhaseSpec("B", "B が成立する")},
            (PhaseRelationSpec("planned_next", self.x, "a"), PhaseRelationSpec("planned_next", "a", "b")),
        )

    # fixtures ------------------------------------------------------------------
    def blobs(self) -> dict[str, bytes]:
        return self.reg.registration_blobs(self.store)

    def consumption_text(self, consumption=None, **result_changes) -> str:
        consumption = consumption or self.reg.consumption
        if result_changes:
            consumption = replace(consumption, persisted_result={**consumption.persisted_result, **result_changes})
        return serialize.canonical_text(consumption.to_record())

    def km_on(self, parent: str, text: str | None = None, extra: dict | None = None) -> str:
        return plumb_commit(self.store, parent, {self.reg.consumption_path: text or self.consumption_text(), **(extra or {})},
                            "a fixture metadata commit")

    def registration_on(self, parent: str, blobs: dict[str, bytes] | None = None) -> str:
        return plumb_commit(self.store, parent, dict(blobs or self.blobs()), "a fixture registration commit")

    def run_of(self, commit: str):
        wanted = planning.candidate_hash(self.reg.material)
        (found,) = [r for r in publication.registered_runs(self.repo, commit) if r.candidate_hash == wanted]
        return found

    # assertions --------------------------------------------------------------------
    def assert_fails(self, commit: str, item: str) -> None:
        failed = publication.committed_planning_proof(self.repo, commit, self.run_of(commit))
        self.assertIsNotNone(failed, f"the proof passed for {commit}")
        self.assertEqual(item, failed[0], failed)
        problem = publication.barrier_problem(self.repo, commit)
        self.assertIsNotNone(problem)
        self.assertIn(f"{item} fails", problem)

    def assert_push_refused(self, commit: str) -> None:
        """A legacy push of a history ending at ``commit`` is refused, and the destination keeps what it had."""
        move_branch(self.store, commit)
        with self.assertRaises(StopError) as raised:
            rm.hold_roadmap(self.store, self.other)
        self.assertEqual("review_publication_barrier", raised.exception.code)
        self.assertEqual(self.published, self.remote_head())

    def gate_4(self) -> str:
        chain = self.chain(self.store, self.run_id)
        fourth = replace(chain.latest, generation=4, previous_generation=3, previous_digest=chain.latest_digest,
                         status="open", receipt_id=None, authorized_operation_stage=None)
        return serialize.canonical_text(fourth.to_record())

    def supersession(self) -> str:
        return serialize.canonical_text(records.Supersession(self.receipt_id, self.run_id, 4, "fixture").to_record())


class ProvenTests(_ProvenCase):
    def test_the_real_history_passes_every_item(self) -> None:
        self.assertIsNone(publication.committed_planning_proof(self.repo, self.reg.km, self.run_of(self.reg.km)))
        self.assertIsNone(publication.barrier_problem(self.repo, self.reg.km))


class CP1Tests(_ProvenCase):
    def test_a_second_commit_adding_a_registration_path(self) -> None:
        roadmap = rr.entity_paths(self.reg.material)[0]
        removed = plumb_commit(self.store, self.reg.km, {roadmap: None}, "remove the Roadmap file")
        again = plumb_commit(self.store, removed, {roadmap: self.blobs()[roadmap]}, "add it again")
        self.assertEqual(2, len(self.run_of(again).registration_commits))
        self.assert_fails(again, "CP1")
        self.assert_push_refused(again)

    def test_a_registration_commit_adding_only_some_reserved_paths(self) -> None:
        blobs = self.blobs()
        del blobs[rr.entity_paths(self.reg.material)[-1]]
        partial = self.registration_on(self.reg.parent, blobs)
        self.assert_fails(self.km_on(partial, self.consumption_text(registration_commit=partial)), "CP1")

    def test_a_merge_adding_the_registration_paths(self) -> None:
        side = plumb_commit(self.store, self.reg.parent, {"side.txt": "side\n"}, "side")
        merge = plumb_commit(self.store, [self.reg.parent, side], {**self.blobs(), "side.txt": "side\n"}, "an evil merge")
        self.assertEqual([merge], list(self.run_of(merge).registration_commits))
        self.assert_fails(merge, "CP1")


class CP2Tests(_ProvenCase):
    def _on_changed_parent(self, changes: dict) -> str:
        parent = plumb_commit(self.store, self.reg.parent, changes, "a changed parent")
        return self.registration_on(parent)

    def test_the_parent_lacks_the_receipt(self) -> None:
        commit = self._on_changed_parent({review_paths.receipt_rel(self.receipt_id): None})
        self.assert_fails(commit, "CP2")
        self.assert_push_refused(commit)

    def test_the_parent_holds_a_supersession_of_the_receipt(self) -> None:
        self.assert_fails(self._on_changed_parent({review_paths.supersession_rel(self.receipt_id): self.supersession()}), "CP2")

    def test_the_parent_holds_a_generation_4(self) -> None:
        self.assert_fails(self._on_changed_parent({review_paths.gate_rel(self.run_id, 4): self.gate_4()}), "CP2")


class CP3Tests(_ProvenCase):
    def test_the_policy_the_run_names_is_not_provided(self) -> None:
        with mock.patch.dict(planning.POLICY_RECORD, {"repair": "a policy this implementation does not provide"}):
            self.assert_fails(self.reg.km, "CP3")
            self.assert_push_refused(self.reg.km)

    def test_a_task_input_that_is_not_the_accepted_one(self) -> None:
        chain = self.chain(self.store, self.run_id)
        task_id = chain.generations[0].accepted_tasks[0]["task_id"]
        task_input = ReviewStore(self.store).read_task_input(task_id)
        envelope = {**task_input.request_envelope, "context": {**task_input.request_envelope["context"], "extra": "x"}}
        forged = replace(task_input, request_envelope=envelope, request_digest=serialize.digest(envelope))
        parent = plumb_commit(self.store, self.reg.parent,
                              {review_paths.task_input_rel(task_id): serialize.canonical_text(forged.to_record())})
        self.assert_fails(self.registration_on(parent), "CP3")


class CP4Tests(_ProvenCase):
    def test_a_run_record_changed_after_kp(self) -> None:
        commit = plumb_commit(self.store, self.reg.km, {review_paths.gate_rel(self.run_id, 2): "changed: true\n"})
        self.assert_fails(commit, "CP4")
        self.assert_push_refused(commit)

    def test_a_supersession_added_anywhere_in_the_history(self) -> None:
        added = plumb_commit(self.store, self.reg.km, {review_paths.supersession_rel(self.receipt_id): self.supersession()})
        removed = plumb_commit(self.store, added, {review_paths.supersession_rel(self.receipt_id): None})
        self.assert_fails(removed, "CP4")

    def test_a_generation_4_added(self) -> None:
        self.assert_fails(plumb_commit(self.store, self.reg.km, {review_paths.gate_rel(self.run_id, 4): self.gate_4()}), "CP4")


class CP5Tests(_ProvenCase):
    def test_registration_bytes_that_are_not_the_expected_projection(self) -> None:
        blobs = self.blobs()
        roadmap = rr.entity_paths(self.reg.material)[0]
        blobs[roadmap] = blobs[roadmap] + b"\n"
        kp = self.registration_on(self.reg.parent, blobs)
        km = self.km_on(kp, self.consumption_text(registration_commit=kp))
        self.assert_fails(km, "CP5")
        self.assert_push_refused(km)


class CP6Tests(_ProvenCase):
    def test_a_meaning_that_is_not_the_candidate(self) -> None:
        real = rr.RoadmapPlanAdapter.normalize_persisted

        def other_meaning(self_, loaded):
            found = real(self_, loaded)
            return rr.reviewed_artifact(found.semantics_version, {"another": "meaning"})

        with mock.patch.object(rr.RoadmapPlanAdapter, "normalize_persisted", other_meaning):
            self.assert_fails(self.reg.km, "CP6")
            self.assert_push_refused(self.reg.km)


class CP7Tests(_ProvenCase):
    def test_a_declared_base_that_is_not_the_candidates_on_the_parent(self) -> None:
        held = rm.hold_phase(self.store, self.x)
        events = ".workline/events/events.jsonl"
        hold_line = blob_at(self.store, held.head, events).splitlines(keepends=True)[-1]
        parent = plumb_commit(self.store, self.reg.parent, {events: blob_at(self.store, self.reg.parent, events) + hold_line})
        kp = self.registration_on(parent)
        self.assertIsNone(rr.delta_problem(self.repo, rr.expected_projection(
            self.store, self.reg.material, self._context(), parent), kp), "CP5 passes: the bytes are E's on that parent")
        km = self.km_on(kp, self.consumption_text(registration_commit=kp, registration_parent=parent))
        self.assert_fails(km, "CP7")

    def _context(self) -> dict:
        chain = self.chain(self.store, self.run_id)
        task_id = chain.generations[0].accepted_tasks[0]["task_id"]
        return ReviewStore(self.store).read_task_input(task_id).request_envelope["context"]


class CP8Tests(_ProvenCase):
    def test_no_consumption(self) -> None:
        self.assert_fails(self.reg.kp, "CP8")
        self.assert_push_refused(self.reg.kp)

    def test_a_consumption_that_does_not_name_the_run(self) -> None:
        forged = replace(self.reg.consumption, target_identity="r_" + OTHER_ID)
        self.assert_fails(self.km_on(self.reg.kp, self.consumption_text(forged)), "CP8")


class CP9Tests(_ProvenCase):
    def test_every_persisted_result_claim_is_re_proven(self) -> None:
        result = self.reg.consumption.persisted_result
        wrong = {
            "semantic_projection_digest": "0" * 64,
            "registration_delta_digest": "1" * 64,
            "request_digest": "2" * 64,
            "registration_parent": "f" * 40,
            "loader_identity": "3" * 64,
            "phase_ids": list(reversed(result["phase_ids"])),
            "relation_ids": list(reversed(result["relation_ids"])),
        }
        for key, value in wrong.items():
            with self.subTest(claim=key):
                self.assertNotEqual(value, result[key])
                self.assert_fails(self.km_on(self.reg.kp, self.consumption_text(**{key: value})), "CP9")

    def test_claims_the_version_2_reader_already_refuses_fail_at_cp8(self) -> None:
        """A claim whose form the reader checks - a branch that is not a full ref, a roadmap_id other than the
        target - never reads back as a Planning Consumption, so the first item that fails is CP8."""
        for key, value in (("branch", "main"), ("roadmap_id", "r_" + OTHER_ID)):
            with self.subTest(claim=key):
                self.assert_fails(self.km_on(self.reg.kp, self.consumption_text(**{key: value})), "CP8")

    def test_an_adapter_identity_mismatch(self) -> None:
        km = self.km_on(self.reg.kp, self.consumption_text(adapter_identity="phase-entry-design-adapter-v1"))
        failed = publication.committed_planning_proof(self.repo, km, self.run_of(km))
        # the version-2 reader refuses a Planning Consumption whose adapter is not its kind's (CP8: it must read back)
        self.assertIn(failed[0], ("CP8", "CP9"))
        self.assertIsNotNone(publication.barrier_problem(self.repo, km))


class CP10Tests(_ProvenCase):
    def test_another_planning_consumption_names_the_registration_commit(self) -> None:
        second = replace(self.reg.consumption, consumption_id="rcs_" + OTHER_ID, receipt_id="rcp_" + OTHER_ID)
        commit = plumb_commit(self.store, self.reg.km, {review_paths.consumption_rel(second.consumption_id): self.consumption_text(second)})
        self.assert_fails(commit, "CP10")
        self.assert_push_refused(commit)

    def test_another_planning_consumption_has_the_runs_kind_and_target(self) -> None:
        second = replace(self.reg.consumption, consumption_id="rcs_" + OTHER_ID, receipt_id="rcp_" + OTHER_ID)
        text = self.consumption_text(second, registration_commit="e" * 40)
        commit = plumb_commit(self.store, self.reg.km, {review_paths.consumption_rel(second.consumption_id): text})
        self.assert_fails(commit, "CP10")


class CP11Tests(_ProvenCase):
    def test_the_metadata_commit_parent_does_not_descend_from_kp(self) -> None:
        side = plumb_commit(self.store, self.reg.parent, {"side.txt": "side\n"}, "side")
        km = self.km_on(side)
        merge = plumb_commit(self.store, [self.reg.kp, km], {self.reg.consumption_path: self.consumption_text(), "side.txt": "side\n"},
                             "merge", base=self.reg.kp)
        self.assert_fails(merge, "CP11")
        self.assert_push_refused(merge)

    def test_a_planning_owned_path_touched_between_kp_and_the_metadata_commit_parent(self) -> None:
        gate = review_paths.gate_rel(self.run_id, 2)
        touched = plumb_commit(self.store, self.reg.kp, {gate: "touched: true\n"})
        restored = plumb_commit(self.store, touched, {gate: blob_at(self.store, self.reg.kp, gate)})
        self.assert_fails(self.km_on(restored), "CP11")

    def test_the_consumption_blob_changed_after_the_metadata_commit(self) -> None:
        changed = replace(self.reg.consumption, operation_mutation_id="mut_" + OTHER_ID)
        commit = plumb_commit(self.store, self.reg.km, {self.reg.consumption_path: self.consumption_text(changed)})
        self.assert_fails(commit, "CP11")

    def test_two_commits_add_the_consumption(self) -> None:
        removed = plumb_commit(self.store, self.reg.km, {self.reg.consumption_path: None})
        self.assert_fails(self.km_on(removed), "CP11")


class CP12Tests(_ProvenCase):
    def test_an_extra_path_in_the_metadata_commit(self) -> None:
        km = self.km_on(self.reg.kp, extra={"extra.txt": "carried along\n"})
        self.assert_fails(km, "CP12")
        self.assert_push_refused(km)


class CP13Tests(_ProvenCase):
    """CP11 already refuses a touched path in a consistent history; CP13 is proven with that check neutralized."""

    def _neutralized(self):
        return mock.patch.object(gitcmd, "commits_touching", lambda repo, start, end, paths: [])

    def test_a_run_record_changed_in_the_metadata_commit_tree(self) -> None:
        gate = review_paths.gate_rel(self.run_id, 2)
        touched = plumb_commit(self.store, self.reg.kp, {gate: "touched: true\n"})
        km = self.km_on(touched)
        restored = plumb_commit(self.store, km, {gate: blob_at(self.store, self.reg.kp, gate)})
        with self._neutralized():
            self.assert_fails(restored, "CP13")

    def test_a_registration_path_changed_in_the_metadata_commit_tree(self) -> None:
        roadmap = rr.entity_paths(self.reg.material)[0]
        touched = plumb_commit(self.store, self.reg.kp, {roadmap: self.blobs()[roadmap] + b"x\n"})
        km = self.km_on(touched)
        restored = plumb_commit(self.store, km, {roadmap: self.blobs()[roadmap]})
        with self._neutralized():
            self.assert_fails(restored, "CP13")


class CrashBeforeC2KmTests(PlanningTestCase):
    """Km committed, a crash before C-2(Km), runtime deleted: an unrelated push publishes only after its own proof."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project(remote=True)
        self.other = rm.create_roadmap(self.store, plan("Other Roadmap")).roadmap_id
        self.before = self.remote_head()
        with crash_at(rr, "_c2_km"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store)
        (record,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-create"]
        self.km = [e for e in record["effects"] if e["stage"] == rr.STAGE_KM][0]["commit_id"]
        self.runtime_gone(self.store)

    def test_the_proof_passes_over_the_objects_and_the_push_publishes_without_the_note(self) -> None:
        real_note = Mutation.note

        def note(self_, key):
            if key == rr.NOTE_PUBLICATION_PROOF:
                raise AssertionError("the lost note was read")
            return real_note(self_, key)

        with mock.patch.object(Mutation, "note", note):
            held = rm.hold_roadmap(self.store, self.other)
        self.assertEqual(held.head, self.remote_head())
        self.assertEqual(self.km, git(self.store.root, "rev-parse", f"{held.head}~1").strip())

    def test_a_broken_proof_item_holds_the_push(self) -> None:
        run_id = run_ids(self.store)[0]
        broken = plumb_commit(self.store, self.km, {review_paths.gate_rel(run_id, 2): "changed: true\n"})
        move_branch(self.store, broken)
        with self.assertRaises(StopError) as raised:
            rm.hold_roadmap(self.store, self.other)
        self.assertEqual("review_publication_barrier", raised.exception.code)
        self.assertIn("CP4", str(raised.exception))
        self.assertEqual(self.before, self.remote_head())


class ClearsTests(PlanningTestCase):
    """Km committed and the committed planning proof passing: the barrier clears for every pusher and a fresh clone."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project(remote=True)
        self.other = rm.create_roadmap(self.store, plan("Other Roadmap")).roadmap_id

    def test_the_planning_mutations_own_push(self) -> None:
        result = self.reviewed_roadmap(self.store)
        self.assertEqual(result.registration.head, self.remote_head())

    def test_an_unrelated_operations_push(self) -> None:
        with crash_at(gitcmd, "push"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store)
        held = rm.hold_roadmap(self.store, self.other)
        self.assertEqual(held.head, self.remote_head())

    def test_from_a_fresh_clone(self) -> None:
        result = self.reviewed_roadmap(self.store)
        clone = self.fresh_clone(self.remote_path(), "clone")
        self.assertEqual(result.registration.head, self.head(clone))
        self.assertIsNone(publication.barrier_problem(clone.root, result.registration.head))
        self.enter(clone.root)
        held = rm.hold_roadmap(clone, self.other)
        self.assertEqual(held.head, self.remote_head())


class DestinationHoldsKmTests(PlanningTestCase):
    def test_km_pushed_by_hand_while_the_proof_fails(self) -> None:
        store = self.planning_project(remote=True)
        other = rm.create_roadmap(store, plan("Other Roadmap")).roadmap_id
        with crash_at(gitcmd, "push"):
            with self.assertRaises(Crash):
                rm.hold_roadmap(store, other)  # an older operation: its commit made, its push not
        with crash_at(rr, "_c2_km"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        (record,) = [r for r in self.pending(store) if r["invocation"].get("operation") == "roadmap-create"]
        km = [e for e in record["effects"] if e["stage"] == rr.STAGE_KM][0]["commit_id"]
        git(store.root, "push", "-q", "origin", f"{km}:refs/heads/main")  # a person pushes Km by hand
        failing = mock.patch.object(publication, "committed_planning_proof", lambda repo, commit, run: ("CP5", "fixture"))
        with failing:
            with self.assertRaises(ReconcileRequired) as raised:
                self.reviewed_roadmap(store)
            self.assertEqual("review_metadata_commit_mismatch", raised.exception.reason)
            (record,) = [r for r in self.pending(store) if r["invocation"].get("operation") == "roadmap-create"]
            self.assertEqual("pending", record["status"], "not completed as published")
            with mock.patch.object(gitcmd, "push", side_effect=AssertionError("pushed")):
                rm.hold_roadmap(store, other)  # already published: nothing is written, and nothing is proven by it
            with self.assertRaises(StopError) as refused:
                rm.resume_roadmap(store, other)  # a push that would write (event log only: no scope overlap)
            self.assertEqual("review_publication_barrier", refused.exception.code)
        self.assertEqual(km, self.remote_head())


class NoteTests(PlanningTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project(remote=True)
        with crash_at(rr.gitops, "review_publication_effect"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store)

    def test_a_deleted_note_is_never_assumed(self) -> None:
        (record,) = self.pending(self.store)
        path = self.store.mutations / f"{record['mutation_id']}.yaml"
        del record["notes"][rr.NOTE_PUBLICATION_PROOF]
        path.write_text(yamlish.dump(record), encoding="utf-8", newline="\n")
        calls: list[str] = []
        real = rr._c2_km

        def counted(*args, **kwargs):
            calls.append("c2_km")
            return real(*args, **kwargs)

        with mock.patch.object(rr, "_c2_km", counted):
            result = self.reviewed_roadmap(self.store)
        self.assertEqual(["c2_km"], calls)
        self.assertEqual(result.registration.head, self.remote_head())

    def test_after_full_runtime_loss_the_committed_proof_alone_decides(self) -> None:
        km = self.head(self.store)
        self.runtime_gone(self.store)
        self.assertIsNone(publication.barrier_problem(self.store.root, km))
        result = self.reviewed_roadmap(self.store)  # the consumed Run is set aside: a new Run, a second Roadmap
        self.assertEqual("registered", result.status)
        self.assertEqual(2, len(run_ids(self.store)))
        self.assertEqual(result.registration.head, self.remote_head())
        self.assertIs(True, gitcmd.descends_from(self.store.root, result.registration.head, km))


class UpgradeTests(PlanningTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()
        self.result = self.reviewed_roadmap(self.store)
        self.km = self.result.registration.head

    def test_a_changed_loader_identity_that_reproduces_every_byte_passes(self) -> None:
        with mock.patch.object(planning, "loader_identity", lambda directory: "sha256:" + "9" * 64):
            self.assertIsNone(publication.barrier_problem(self.store.root, self.km))

    def test_one_changed_expected_byte_holds(self) -> None:
        real = rm.roadmap_file_effect

        def one_byte(*args, **kwargs):
            effect = real(*args, **kwargs)
            return replace(effect, payload={**effect.payload, "content": effect.payload["content"] + "\n"})

        with mock.patch.object(rm, "roadmap_file_effect", one_byte):
            problem = publication.barrier_problem(self.store.root, self.km)
        self.assertIsNotNone(problem)
        self.assertIn("CP5 fails", problem)

    def test_an_adapter_or_semantics_version_not_provided_holds(self) -> None:
        kind = planning.KINDS[planning.KIND_ROADMAP]
        for changed in (replace(kind, adapter_identity="roadmap-plan-adapter-v2"),
                        replace(kind, projection_semantics_version="roadmap-plan-semantics-v2")):
            with self.subTest(changed=changed), mock.patch.dict(planning.KINDS, {planning.KIND_ROADMAP: changed}):
                self.assertIsNotNone(publication.barrier_problem(self.store.root, self.km))

    def test_a_policy_not_provided_holds(self) -> None:
        with mock.patch.dict(planning.POLICY_RECORD, {"repair": "not provided"}):
            problem = publication.barrier_problem(self.store.root, self.km)
        self.assertIn("CP3 fails", problem)


class ForeignKmTests(PlanningTestCase):
    def test_a_persons_commit_of_the_working_tree_consumption_is_unowned_and_clears_the_barrier(self) -> None:
        store = self.planning_project(remote=True)
        other = rm.create_roadmap(store, plan("Other Roadmap")).roadmap_id
        with crash_at(mutation_module, "_make_planning_commit",
                      when=lambda n, s, payload, paths: "record review consumption" in payload.get("message", "")):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        consumption = [p for p in git(store.root, "status", "--porcelain", "--untracked-files=all").splitlines() if "/consumptions/" in p]
        git(store.root, "add", "--", consumption[0][3:])
        git(store.root, "commit", "-q", "-m", "a person commits the Consumption")
        foreign = self.head(store)
        with self.assertRaises(ReconcileRequired) as raised:
            self.reviewed_roadmap(store)
        self.assertEqual("review_commit_unowned", raised.exception.reason)
        self.assertIsNone(publication.barrier_problem(store.root, foreign))
        held = rm.hold_roadmap(store, other)
        self.assertEqual(held.head, self.remote_head())


class LegacyOnlyPushTests(PlanningTestCase):
    def test_one_path_limited_history_read_per_commit_and_no_proof(self) -> None:
        store = self.new_project(remote=True)
        calls: list[str] = []
        reads: list[tuple] = []
        real_touches, real_run = gitcmd.history_touches, gitcmd.run_git

        def run(repo, *args, **kwargs):
            if "--full-history" in args and args[-1] == publication.FAST_PATH_DIRECTORY:
                reads.append(args)
            return real_run(repo, *args, **kwargs)

        def touches(repo, commit, directory):
            calls.append(commit)
            return real_touches(repo, commit, directory)

        with mock.patch.object(gitcmd, "history_touches", touches), mock.patch.object(gitcmd, "run_git", run), \
                mock.patch.object(publication, "registered_runs", side_effect=AssertionError("Runs were read")), \
                mock.patch.object(publication, "committed_planning_proof", side_effect=AssertionError("a proof ran")):
            result = rm.create_roadmap(store, plan())
        made = result.head
        before = gitcmd.commit_parents(store.root, made)[0]
        # §18.7: before the Git stage is recorded (HEAD), at classification and right before the push (the commit made)
        self.assertEqual([before, made, made], calls)
        # one path-limited read per commit: the same commit ID's answer is remembered within the process
        self.assertEqual([("rev-list", "--full-history", "-n", "1", commit, "--", publication.FAST_PATH_DIRECTORY)
                          for commit in (before, made)], reads)
        self.assertEqual(made, self.remote_head())


if __name__ == "__main__":
    unittest.main()
