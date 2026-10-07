"""P7 namespace refactor of the shared Review readers (§31.4 / §31.50; IR-RB7-3, written by the shared-surface writer).

* ``review.paths`` keeps every public name with exactly its pre-refactor value and delegates to the PROJECT
  descriptor (RB7-A's ``review.namespace``), so nothing that reads a Project's Review records changes;
* ``ReviewStore(store)`` is the PROJECT reader, unchanged; ``ReviewStore.for_namespace(root, namespace)`` and
  ``CommittedReviewStore(repo, commit, namespace=)`` read the root policy Review (``review-policy/review``) through
  the same parsers, chain rules and indexes, with no ``ProjectStore`` for the root;
* under the root namespace every Project-only reader (history, the Profile and policy records, activation, repairs)
  refuses with ``review_namespace_invalid``, and ``validate.review_problems`` skips the Project-only passes and
  refuses a Project-only area as an unknown entry;
* the two namespaces never see each other's records, and nothing creates ``<root>/.workline``.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from helpers import WorklineTestCase, git, rmtree
from workline.errors import ValidationError
from workline.review import paths, records, serialize, validate
from workline.review.committed import CommittedReviewStore
from workline.review.namespace import PROJECT_REVIEW_NAMESPACE as PROJECT, ROOT_POLICY_REVIEW_NAMESPACE as ROOT
from workline.review.namespace import ReviewNamespace
from workline.review.store import ReviewStore
from workline.store import ProjectStore

RUN = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"
FILLER = "f" * 64


def chain(count: int, *, kind: str = "global-policy-change-v1", target: str = "global-policy") -> list:
    found: list[records.GateGeneration] = []
    previous = None
    for number in range(1, count + 1):
        item = records.GateGeneration(
            review_run_id=RUN, generation=number, previous_generation=None if number == 1 else number - 1,
            previous_digest=previous, review_kind=kind, target_identity=target, operation_identity="op:" + "e" * 64,
            candidate_hash="a" * 64, review_context_hash="b" * 64, effective_policy_hash="c" * 64,
            evidence_digest=FILLER, coverage_digest=FILLER, raw_report_set_digest=FILLER, adjudication_digest=FILLER,
            obligation_digest=FILLER, accepted_tasks=(), settled_tasks=(), status=records.GATE_STATUS_OPEN,
            receipt_id=None, authorized_operation_stage=None,
        )
        found.append(item)
        previous = serialize.digest(item.to_record())
    return found


class PathsTests(unittest.TestCase):
    def test_every_public_project_value_is_its_pre_refactor_value(self) -> None:
        base = {
            "REVIEW_DIR": ".workline/review", "GATES_DIR": ".workline/review/gates",
            "RECEIPTS_DIR": ".workline/review/receipts", "CONSUMPTIONS_DIR": ".workline/review/consumptions",
            "SUPERSESSIONS_DIR": ".workline/review/supersessions",
            "CANDIDATE_SNAPSHOTS_DIR": ".workline/review/candidate-snapshots",
            "TASK_INPUTS_DIR": ".workline/review/task-inputs", "ACTIVATION_DIR": ".workline/review/activation",
            "REPORTS_DIR": ".workline/review/reports", "ADJUDICATIONS_DIR": ".workline/review/adjudications",
            "REPAIR_BATCHES_DIR": ".workline/review/repair-batches",
            "REPAIR_RESULTS_DIR": ".workline/review/repair-results", "HISTORY_DIR": ".workline/review/history",
            "POLICY_DIR": ".workline/review/policy", "POLICY_PROFILE_NAME": "project-profile.yaml",
            "POLICY_PROFILE_REL": ".workline/review/policy/project-profile.yaml",
            "WORK_TERMINAL_ACTIVATION_REL": ".workline/review/activation/work-terminal-v1.yaml",
            "GENERATION_WIDTH": 6, "SERIALIZATION_TOKEN": ".generation-serialization",
            "HISTORY_FAMILIES": ("runs", "findings", "repairs", "relations", "human-decisions"),
            "POLICY_FAMILIES": ("changes", "evaluations"),
            "REVIEW_SUBDIRS": ("gates", "receipts", "consumptions", "supersessions", "candidate-snapshots",
                               "task-inputs", "activation", "reports", "adjudications", "repair-batches",
                               "repair-results", "history", "policy"),
            "RUNTIME_REVIEW_DIR": ".workline/runtime/review",
        }
        for name, value in base.items():
            with self.subTest(name=name):
                self.assertEqual(value, getattr(paths, name))
        self.assertEqual(f".workline/review/gates/{RUN}/000002.yaml", paths.gate_rel(RUN, 2))
        self.assertEqual(f".workline/review/history/runs/{RUN}.yaml", paths.history_run_rel(RUN))
        self.assertEqual(2, paths.generation_of_name("000002.yaml"))
        for refused, code in (("README.md", "review_containment"), (".workline/review/gates/x.yaml", "review_containment"),
                              ("review-policy/review/receipts/x.yaml", "review_containment")):
            with self.subTest(refused=refused), self.assertRaises(ValidationError) as raised:
                paths.require_review_record_path(refused)
            self.assertEqual(code, raised.exception.code)
        paths.require_review_readable_path(paths.POLICY_PROFILE_REL)

    def test_every_project_path_builders_refusal_is_its_pre_refactor_code_and_message(self) -> None:
        """RB7PSW-3: literals taken from the base blob ``src/workline/review/paths.py`` at 9822de2 (before the
        delegation to the PROJECT descriptor), so a change to a descriptor builder's refusal fails here even though
        ``paths`` and the descriptor now run the same code."""
        rows = (
            ("receipt_rel", ("x",), "review_record_invalid", "not a review_receipt id: 'x'"),
            ("receipt_rel", (RUN,), "review_record_invalid", f"not a review_receipt id: '{RUN}'"),
            ("consumption_rel", ("x",), "review_record_invalid", "not a review_consumption id: 'x'"),
            ("supersession_rel", ("x",), "review_record_invalid", "not a review_receipt id: 'x'"),
            ("candidate_snapshot_rel", ("A" * 64,), "review_record_invalid",
             f"candidate_hash is not a lowercase hex SHA-256: '{'A' * 64}'"),
            ("candidate_snapshot_rel", ("abc",), "review_record_invalid",
             "candidate_hash is not a lowercase hex SHA-256: 'abc'"),
            ("task_input_rel", (RUN,), "review_record_invalid", f"not a review_task id: '{RUN}'"),
            ("report_rel", ("g" * 64,), "review_record_invalid",
             f"result_digest is not a lowercase hex SHA-256: '{'g' * 64}'"),
            ("adjudication_rel", ("x",), "review_record_invalid", "not a review_run id: 'x'"),
            ("repair_batch_rel", ("x",), "review_record_invalid", "not a review_repair_batch id: 'x'"),
            ("repair_result_rel", (RUN,), "review_record_invalid", f"not a review_repair_batch id: '{RUN}'"),
            ("history_rel", ("index", RUN), "review_record_invalid", "not a Review history family: 'index'"),
            ("history_rel", ("runs", "rfd_01ARZ3NDEKTSV4RRFFQ69G5F10"), "review_record_invalid",
             "not a review_run id: 'rfd_01ARZ3NDEKTSV4RRFFQ69G5F10'"),
            ("policy_record_rel", ("profiles", "x"), "review_record_invalid",
             "not a Review policy evidence family: 'profiles'"),
            ("policy_record_rel", ("changes", RUN), "review_record_invalid", f"not a review_policy_change id: '{RUN}'"),
            ("require_policy_profile_path", (".workline/review/policy/other.yaml",), "review_containment",
             "'.workline/review/policy/other.yaml' is not the canonical Project Profile "
             ".workline/review/policy/project-profile.yaml"),
        )
        for name, args, code, message in rows:
            for owner, label in ((paths, "paths"), (PROJECT, "PROJECT")):
                with self.subTest(builder=name, args=args, owner=label), self.assertRaises(ValidationError) as raised:
                    getattr(owner, name)(*args)
                self.assertEqual((code, message), (raised.exception.code, str(raised.exception)))


class Root(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="workline-rb7-namespace-"))
        self.addCleanup(rmtree, self.root)

    def put(self, relative: str, record: dict | None = None, raw: bytes | None = None) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw if raw is not None else serialize.canonical_bytes(record))

    def put_chain(self, namespace, generations) -> None:
        for item in generations:
            self.put(namespace.gate_rel(item.review_run_id, item.generation), item.to_record())


class StoreTests(Root):
    def test_the_project_reader_is_unchanged_and_names_its_namespace(self) -> None:
        reader = ReviewStore(ProjectStore(self.root))
        self.assertIs(PROJECT, reader.namespace)
        twin = ReviewStore.for_namespace(self.root, PROJECT)
        self.assertEqual((PROJECT, Path(self.root)), (twin.namespace, Path(twin.root)))
        self.assertIsInstance(twin.store, ProjectStore)
        self.put_chain(PROJECT, chain(2, kind="work-result-v1", target="w_01ARZ3NDEKTSV4RRFFQ69G5FAV"))
        self.assertEqual(reader.gate_chain(RUN), twin.gate_chain(RUN))
        self.assertEqual([], validate.review_problems(reader))

    def test_the_root_reader_reads_the_root_review_through_the_shared_rules(self) -> None:
        reader = ReviewStore.for_namespace(self.root, ROOT)
        self.assertIs(ROOT, reader.namespace)
        self.assertIsNone(reader.store, "the Workline root is not a Project")
        self.assertFalse(reader.exists())
        self.put_chain(ROOT, chain(2))
        self.assertTrue(reader.exists())
        self.assertEqual((RUN,), reader.run_ids())
        found = reader.gate_chain(RUN)
        self.assertEqual(2, found.latest.generation)
        self.assertEqual([], validate.review_problems(reader))
        self.assertFalse((self.root / ".workline").exists(), "nothing creates <root>/.workline")
        self.assertEqual((), ReviewStore.for_namespace(self.root, PROJECT).run_ids(), "the Project sees no root record")
        broken = chain(3)
        self.put(ROOT.gate_rel(RUN, 3), {**broken[2].to_record(), "previous_digest": "0" * 64})
        with self.assertRaises(ValidationError) as raised:
            reader.gate_chain(RUN)
        self.assertEqual("review_gate_chain", raised.exception.code, "the one chain rule")

    def test_only_a_described_namespace_is_ever_bound(self) -> None:
        """RB7PSW-2: ``_bind`` checks membership in ``namespace.NAMESPACES``, not only the type - a constructed
        descriptor (even one with PROJECT's flags) is never bound, so no Project-only path site reads under it."""
        constructed = (
            ReviewNamespace("project", "elsewhere/review", PROJECT.subdirs, history=True, policy=True, activation=True,
                            repairs=True),
            ReviewNamespace(ROOT.name, "elsewhere/review", ROOT.subdirs, history=False, policy=False, activation=False,
                            repairs=False),
        )
        for namespace in (*constructed, "review-policy/review", None):
            with self.subTest(namespace=namespace), self.assertRaises(ValidationError) as raised:
                ReviewStore.for_namespace(self.root, namespace)
            self.assertEqual("review_namespace_invalid", raised.exception.code)
        self.assertFalse((self.root / ".workline").exists())
        self.assertIs(ROOT, ReviewStore.for_namespace(self.root, ROOT).namespace)

    def test_for_namespace_makes_only_the_working_tree_reader(self) -> None:
        """Note 2 of the RB7 batch review: a committed reader is bound by its own constructor's ``namespace=``."""
        self.assertIs(ReviewStore, type(ReviewStore.for_namespace(self.root, ROOT)))
        with self.assertRaises(TypeError):
            CommittedReviewStore.for_namespace(self.root, ROOT)

    def test_every_project_only_reader_refuses_under_the_root_namespace(self) -> None:
        reader = ReviewStore.for_namespace(self.root, ROOT)
        calls = {
            "history_ids": lambda: reader.history_ids(paths.HISTORY_RUNS),
            "read_history": lambda: reader.read_history(paths.HISTORY_RUNS, RUN),
            "history_exists": lambda: reader.history_exists(paths.HISTORY_RUNS, RUN),
            "run_history_ids": reader.run_history_ids,
            "run_history": lambda: reader.run_history(RUN),
            "read_profile_bytes": reader.read_profile_bytes,
            "read_profile": reader.read_profile,
            "profile_digest": reader.profile_digest,
            "read_policy_change": lambda: reader.read_policy_change("rpc_01ARZ3NDEKTSV4RRFFQ69G5FAV"),
            "policy_change_ids": reader.policy_change_ids,
            "policy_evaluation_ids": reader.policy_evaluation_ids,
            "read_activation": reader.read_activation,
            "activation_exists": reader.activation_exists,
            "repair_batch_ids": reader.repair_batch_ids,
            "repair_result_ids": reader.repair_result_ids,
            "read_repair_batch": lambda: reader.read_repair_batch("rrb_01ARZ3NDEKTSV4RRFFQ69G5FAV"),
        }
        for name, call in calls.items():
            with self.subTest(reader=name), self.assertRaises(ValidationError) as raised:
                call()
            self.assertEqual("review_namespace_invalid", raised.exception.code)

    def test_each_reader_reads_only_inside_its_own_namespace(self) -> None:
        root_reader = ReviewStore.for_namespace(self.root, ROOT)
        project_reader = ReviewStore(ProjectStore(self.root))
        for reader, foreign in ((root_reader, PROJECT.gate_rel(RUN, 1)), (project_reader, ROOT.gate_rel(RUN, 1))):
            with self.subTest(namespace=reader.namespace.name), self.assertRaises(ValidationError) as raised:
                reader.read_bytes(foreign)
            self.assertEqual("review_containment", raised.exception.code)
        with self.assertRaises(ValidationError):
            root_reader.read_bytes(paths.POLICY_PROFILE_REL)
        with self.assertRaises(ValidationError):
            ReviewStore.for_namespace(self.root, "review-policy/review")  # type: ignore[arg-type]

    def test_a_project_only_area_under_the_root_review_is_an_unknown_entry(self) -> None:
        reader = ReviewStore.for_namespace(self.root, ROOT)
        self.put_chain(ROOT, chain(1))
        for area in ("history", "policy", "activation", "repair-batches"):
            with self.subTest(area=area):
                (self.root / ROOT.root / area).mkdir()
                self.assertIn("review_namespace_invalid", [p.code for p in validate.review_problems(reader)])
                (self.root / ROOT.root / area).rmdir()
        self.assertEqual([], validate.review_problems(reader))


class CommittedTests(WorklineTestCase):
    def test_the_committed_reader_is_bound_to_one_namespace(self) -> None:
        repo = self.new_dir("root")
        git(repo, "init", "-b", "main")
        writer = Root("put")
        writer.root = repo
        writer.put_chain(ROOT, chain(2))
        writer.put_chain(PROJECT, chain(1, kind="work-result-v1", target="w_01ARZ3NDEKTSV4RRFFQ69G5FAV"))
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "both namespaces")
        head = git(repo, "rev-parse", "HEAD").strip()
        committed = CommittedReviewStore(repo, head, namespace=ROOT)
        self.assertIs(ROOT, committed.namespace)
        self.assertIsNone(committed.store)
        self.assertEqual(2, committed.gate_chain(RUN).latest.generation)
        self.assertEqual([], validate.review_problems(committed))
        with self.assertRaises(ValidationError) as raised:
            committed.history_ids(paths.HISTORY_RUNS)
        self.assertEqual("review_namespace_invalid", raised.exception.code)
        project = CommittedReviewStore(repo, head)
        self.assertIs(PROJECT, project.namespace)
        self.assertEqual(1, project.gate_chain(RUN).latest.generation)
        self.assertFalse(any(path.startswith("review-policy") for path in project._tree))
        self.assertFalse(any(path.startswith(".workline") for path in committed._tree))
        constructed = ReviewNamespace(ROOT.name, ".workline/review", ROOT.subdirs, history=False, policy=False,
                                      activation=False, repairs=False)
        with self.assertRaises(ValidationError) as raised:  # RB7PSW-2: refused before any tree is listed
            CommittedReviewStore(repo, head, namespace=constructed)
        self.assertEqual("review_namespace_invalid", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
