"""P7 root policy Review discovery and readability on the shared recovery / checkout surfaces (IR-RB7-4).

Written by the shared-surface writer (§31.29 / §31.58, addendum RB7C-2, R8, RB7AL-3):

* ``recovery.discover_kind_in`` runs the ONE discovery core over the Workline root's Review namespace: the same
  matching from HEAD's history and the working tree, the same whole-Run proof under the Run's own P4 contract, the
  adapter's classification and ``review_recovery_ambiguous`` - with no Human disposition step, the owner's
  ``pending`` hook in place of the Project's pending generation mutations, the persistence boundary against the
  repository and no history Run-summary path; ``adapter.classify`` receives the repository ``Path``;
* ``discover_kind`` / ``_discover`` keep their signatures (the P6 owner's and RB5's adapters plug into them);
* ``checkout.require_namespace_readable_in`` reads every record of the namespace strictly, and gates every
  Project-only area (repair, history, policy, activation) on the namespace's own flag - it never calls their
  readers under the root, and never catches their refusal.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest import mock

from helpers import WorklineTestCase, git

from workline.errors import ReconcileRequired, StopError
from workline.review import checkout, p4, recovery, records, serialize
from workline.review.namespace import PROJECT_REVIEW_NAMESPACE, ROOT_POLICY_REVIEW_NAMESPACE
from workline.review.store import ReviewStore
from workline.store import ProjectStore

ROOT = ROOT_POLICY_REVIEW_NAMESPACE
CONTRACT = records.P7_GLOBAL_POLICY_CHANGE_CONTRACT
KIND = records.GLOBAL_POLICY_REVIEW_KIND
OPERATION = "global-policy-change:" + "e" * 64
RUN, OTHER_RUN = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV", "rr_01ARZ3NDEKTSV4RRFFQ69G5FAW"
TASK, OTHER_TASK = "rtk_01ARZ3NDEKTSV4RRFFQ69G5FAV", "rtk_01ARZ3NDEKTSV4RRFFQ69G5FAW"
CANDIDATE, CONTEXT, FILLER = "a" * 64, "b" * 64, "f" * 64

PROJECT_ONLY_READERS = ("repair_batch_ids", "repair_result_ids", "read_repair_batch", "read_repair_result",
                        "history_ids", "read_history", "read_profile", "policy_change_ids", "policy_evaluation_ids",
                        "read_policy_change", "read_policy_evaluation", "read_activation")


def root_run(review_run_id: str, task_id: str, operation: str = OPERATION) -> dict[str, dict]:
    """A generation-1 root policy Review Run (the open acceptance of one discovery task) as its records."""
    envelope = p4.discovery_request(
        review_contract=CONTRACT, review_kind=KIND, viewpoint="correctness", candidate={"candidate_hash": CANDIDATE},
        context={"context": "root"}, requirement={"requirement": "r"}, candidate_generation=1, succession=None,
        set_aside_runs=(), human_decision=None, policy_id=p4.ROOT_POLICY_ID,
    )
    task = p4.task_input(
        task_id=task_id, task_slot=p4.discovery_slot("correctness"), task_kind=p4.TASK_KIND_DISCOVERY,
        actor_identity="reviewer-a", actor_version="1", envelope=envelope, candidate_hash=CANDIDATE,
        candidate_material_digest="c" * 64, review_context_hash=CONTEXT, accepted_generation=1,
        policy_id=p4.ROOT_POLICY_ID,
    )
    gate = records.GateGeneration(
        review_run_id=review_run_id, generation=1, previous_generation=None, previous_digest=None, review_kind=KIND,
        target_identity=records.GLOBAL_POLICY_TARGET_IDENTITY, operation_identity=operation, candidate_hash=CANDIDATE,
        review_context_hash=CONTEXT, effective_policy_hash=p4.family_policy_hash(p4.ROOT_POLICY_ID),
        evidence_digest=FILLER, coverage_digest=FILLER, raw_report_set_digest=FILLER, adjudication_digest=FILLER,
        obligation_digest=FILLER, accepted_tasks=(p4.accepted_descriptor(task),), settled_tasks=(),
        status=records.GATE_STATUS_OPEN, receipt_id=None, authorized_operation_stage=None,
    )
    snapshot = records.CandidateSnapshot(CANDIDATE, records.RECONSTRUCTION_SNAPSHOT, "p7-root-test-v1",
                                         {"candidate": "root"}, None)
    return {
        ROOT.gate_rel(review_run_id, 1): gate.to_record(),
        ROOT.task_input_rel(task_id): task.to_record(),
        ROOT.candidate_snapshot_rel(CANDIDATE): snapshot.to_record(),
    }


class RootCase(WorklineTestCase):
    """A bare Git repository standing for the Workline root: one seed commit, no ``.workline``."""

    def setUp(self) -> None:
        super().setUp()
        self.repo = self.new_dir("root")
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "seed.txt").write_bytes(b"seed\n")
        self.commit("seed")
        self.pending_calls: list[str] = []
        self.pending: dict[str, list] = {}
        self.classified: list[tuple] = []

    def commit(self, message: str) -> None:
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", message, "--no-verify")

    def lay(self, found: dict[str, dict], *, commit: bool = True) -> None:
        for relative, record in found.items():
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(serialize.canonical_bytes(record))
        if commit:
            self.commit("root Review records (fixture)")

    def adapter(self, reason: str | None = None) -> recovery.RecoveryAdapter:
        def classify(owner, review, head, found, named_aside, currency):
            self.classified.append((owner, review.namespace, head, found.review_run_id, found.contract))
            return reason
        return recovery.RecoveryAdapter(shape=lambda chain: None, named=lambda review, found: [], classify=classify)

    def hook(self, review_run_id: str) -> list:
        self.pending_calls.append(review_run_id)
        return self.pending.get(review_run_id, [])

    def discover(self, adapter: recovery.RecoveryAdapter | None = None,
                 operation: str = OPERATION) -> recovery.Discovery:
        return recovery.discover_kind_in(self.repo, ROOT, KIND, operation, adapter or self.adapter(), pending=self.hook)


class RootDiscoveryTests(RootCase):
    def test_a_root_run_is_discovered_by_the_one_core_and_classified_with_the_repository_path(self) -> None:
        self.lay(root_run(RUN, TASK))
        found = self.discover()
        self.assertIsNotNone(found.recoverable)
        self.assertEqual((RUN, CONTRACT), (found.recoverable.review_run_id, found.recoverable.contract))
        self.assertEqual((), found.set_aside)
        self.assertEqual([RUN], self.pending_calls, "the owner's pending hook replaces the Project's")
        [(owner, namespace, head, run, contract)] = self.classified
        self.assertIsInstance(owner, Path)
        self.assertNotIsInstance(owner, ProjectStore)
        self.assertEqual(self.repo.resolve(), Path(owner).resolve())
        self.assertIs(ROOT, namespace)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), head)
        self.assertFalse((self.repo / ".workline").exists(), "no Project store is ever made for the root")

    def test_another_operation_or_no_run_matches_nothing(self) -> None:
        self.assertEqual(recovery.Discovery(None, ()), self.discover())
        self.lay(root_run(RUN, TASK, operation="global-policy-change:" + "d" * 64))
        self.assertEqual(recovery.Discovery(None, ()), self.discover())
        self.assertEqual([], self.classified)

    def test_the_adapters_set_aside_reason_is_carried(self) -> None:
        self.lay(root_run(RUN, TASK))
        found = self.discover(self.adapter("not_authorized"))
        self.assertEqual(recovery.Discovery(None, ({"review_run_id": RUN, "reason": "not_authorized"},)), found)

    def test_a_pending_root_mutation_holding_the_run_leaves_it_incomplete(self) -> None:
        self.lay(root_run(RUN, TASK))
        self.pending[RUN] = [{"mutation_id": "rpm_01ARZ3NDEKTSV4RRFFQ69G5FAV"}]
        with self.assertRaises(ReconcileRequired) as raised:
            self.discover()
        self.assertEqual("review_recovery_incomplete", raised.exception.reason)
        self.assertEqual([], self.classified)

    def test_two_recoverable_root_runs_are_ambiguous_never_chosen(self) -> None:
        self.lay({**root_run(RUN, TASK), **root_run(OTHER_RUN, OTHER_TASK)})
        with self.assertRaises(ReconcileRequired) as raised:
            self.discover()
        self.assertEqual("review_recovery_ambiguous", raised.exception.reason)

    def test_an_uncommitted_root_run_is_incomplete(self) -> None:
        self.lay(root_run(RUN, TASK), commit=False)
        with self.assertRaises(ReconcileRequired) as raised:
            self.discover()
        self.assertEqual("review_recovery_incomplete", raised.exception.reason)

    def test_no_human_disposition_is_read_under_the_root(self) -> None:
        """R8 / RB7C-2: the root has no Human disposition store, and the core never looks for one there."""
        self.lay(root_run(RUN, TASK))
        with mock.patch.object(recovery, "_human_dispositions", side_effect=AssertionError("read under the root")), \
                mock.patch.object(recovery.gate, "pending_generation_mutations",
                                  side_effect=AssertionError("the Project's pending mutations under the root")):
            self.assertEqual(RUN, self.discover().recoverable.review_run_id)

    def test_the_readability_check_runs_first(self) -> None:
        self.lay(root_run(RUN, TASK))
        (self.repo / ROOT.receipt_rel("rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV")).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / ROOT.receipt_rel("rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV")).write_bytes(b"schema: x\n")
        with self.assertRaises(StopError) as raised:
            self.discover()
        self.assertEqual("review_namespace_unreadable", raised.exception.code)
        self.assertEqual([], self.classified)

    def test_a_project_namespace_is_never_discovered_by_the_root_entry(self) -> None:
        with self.assertRaises(ValueError):
            recovery.discover_kind_in(self.repo, PROJECT_REVIEW_NAMESPACE, KIND, OPERATION, self.adapter(),
                                      pending=self.hook)

    def test_the_project_entries_keep_their_signatures(self) -> None:
        self.assertEqual(["store", "review_kind", "operation_identity", "adapter"],
                         list(inspect.signature(recovery.discover_kind).parameters))
        self.assertEqual(["store", "review_kind", "operation_identity", "currency", "adapter", "held"],
                         list(inspect.signature(recovery._discover).parameters))
        self.assertEqual(["repo", "namespace", "review_kind", "operation_identity", "adapter", "pending"],
                         list(inspect.signature(recovery.discover_kind_in).parameters))
        self.assertEqual(inspect.Parameter.KEYWORD_ONLY,
                         inspect.signature(recovery.discover_kind_in).parameters["pending"].kind)
        self.assertTrue(callable(recovery.p4_reconstruction_problem))


class RootReadabilityTests(RootCase):
    def test_a_repository_with_no_root_namespace_reads(self) -> None:
        self.assertIsNone(checkout.require_namespace_readable_in(self.repo, ROOT))

    def test_an_unreadable_root_record_is_refused(self) -> None:
        self.lay(root_run(RUN, TASK))
        self.assertIsNone(checkout.require_namespace_readable_in(self.repo, ROOT))
        (self.repo / ROOT.task_input_rel(TASK)).write_bytes(b"schema: x\n")
        with self.assertRaises(StopError) as raised:
            checkout.require_namespace_readable_in(self.repo, ROOT)
        self.assertEqual("review_namespace_unreadable", raised.exception.code)

    def test_a_project_only_area_under_the_root_is_refused_by_its_shape(self) -> None:
        for area in ("history", "policy", "activation", "repair-batches"):
            with self.subTest(area=area):
                (self.repo / ROOT.root / area).mkdir(parents=True)
                with self.assertRaises(StopError) as raised:
                    checkout.require_namespace_readable_in(self.repo, ROOT)
                self.assertEqual("review_namespace_unreadable", raised.exception.code)
                (self.repo / ROOT.root / area).rmdir()

    def test_project_only_readers_are_never_called_under_the_root(self) -> None:
        """RB7AL-3: an explicit namespace guard - never a call whose refusal is caught (that would read a real
        unreadable record as readable)."""
        self.lay(root_run(RUN, TASK))
        patches = [mock.patch.object(ReviewStore, name, side_effect=AssertionError(f"{name} under the root"))
                   for name in PROJECT_ONLY_READERS]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.assertIsNone(checkout.require_namespace_readable_in(self.repo, ROOT))

    def test_the_project_check_still_reads_every_project_only_area(self) -> None:
        project = self.new_dir("project")
        (project / PROJECT_REVIEW_NAMESPACE.root).mkdir(parents=True)
        called: list[str] = []

        def recorder(name: str):
            def reader(*args, **kwargs):
                called.append(name)
                return () if name.endswith("_ids") else None
            return reader

        with mock.patch.multiple(ReviewStore, **{name: recorder(name) for name in PROJECT_ONLY_READERS}):
            checkout.require_namespace_readable(ProjectStore(project))
        self.assertEqual({"repair_batch_ids", "repair_result_ids", "history_ids", "read_profile", "policy_change_ids",
                          "policy_evaluation_ids", "read_activation"}, set(called))
