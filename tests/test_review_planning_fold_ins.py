"""P2 §28 S: the reason attribute and catalogue, base_exact, the delta record, and the Git minimums."""

from __future__ import annotations

import ast
from dataclasses import replace
import re
from pathlib import Path
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, cwd, git
from planning_helpers import (
    CANONICAL_RULE, Crash, PlanningTestCase, Reviewer, crash_at, design, noncanonical_registration, plan, plumb_commit,
    registered, rr, run_ids, state_entries,
)
from workline import errors, gitcmd, gitops
from workline import mutation as mutation_module
from workline import roadmap as rm
from workline.errors import ReconcileRequired, StopError
from workline.mutation import MutationController
from workline.project_start import project_start
from workline.review import planning, publication, serialize
from workline.review.store import ReviewStore
from workline.store import ProjectStore

SRC = Path(rr.__file__).parent

#: §25.1: every reason a ReconcileRequired P2 raises carries.
CATALOGUE_REASONS = {
    "review_marker_mismatch", "review_recovery_incomplete", "review_recovery_ambiguous", "review_discovery_changed",
    "review_recovery_reservation_conflict", "review_setup_invalid", "review_binding_moved", "review_chain_invalid",
    "review_task_invalid", "review_generation_owner_conflict", "review_candidate_mismatch", "review_receipt_invalid",
    "review_registration_base_moved", "review_registration_currency_changed", "review_registration_projection_mismatch",
    "review_commit_unowned", "review_persisted_proof_failed", "review_metadata_commit_mismatch",
    "review_publication_invalid", "review_publication_contract_invalid",
}
#: §25.1: every StopError / ValidationError code the contract uses (P2's, the live ones it keeps, and P1's).
CATALOGUE_CODES = {
    "review_contract_invalid", "review_create_unsupported", "review_git_unsupported", "review_candidate_unrepresentable",
    "review_base_uncommitted", "review_entry_not_canonical", "review_entry_ambiguous", "review_context_unavailable",
    "review_reviewer_failed", "review_report_invalid", "review_reviewer_mismatch", "review_git_transform",
    "review_checkout_unsafe", "review_checkout_unknown", "review_namespace_unreadable", "review_hooks_path_invalid",
    "review_publication_barrier", "validation_failed", "postcheck_failed", "structure_invalid", "dirty_overlap",
    "phase_already_expanded", "ambiguous_startable_candidates", "phase_blocked", "spec_violation",
    "review_not_persisted", "review_persistence_unknown", "review_roundtrip_mismatch", "review_callback_unknown",
    "review_callback_conflict", "review_consumption_conflict", "review_generation_conflict", "review_generation_pending",
    "review_path_ignored", "review_committability_unknown", "review_containment", "review_record_invalid",
    "review_record_noncanonical", "review_record_missing", "review_record_version", "review_gate_chain",
    "review_namespace_invalid", "review_projection_invalid", "review_dependency_invalid", "review_adapter_unresolved",
}
#: The modules P2 adds, or the parts it adds to live modules.
P2_MODULES = [
    SRC / "roadmap_review.py", SRC / "committed_view.py", SRC / "review" / "planning.py", SRC / "review" / "recovery.py",
    SRC / "review" / "publication.py", SRC / "review" / "checkout.py", SRC / "review" / "committed.py",
    SRC / "mutation.py", SRC / "gitops.py", SRC / "roadmap.py",
]


#: The modules only P2 has: every ReconcileRequired they build carries a reason.
P2_ONLY_MODULES = [
    SRC / "roadmap_review.py", SRC / "committed_view.py", SRC / "review" / "planning.py", SRC / "review" / "recovery.py",
    SRC / "review" / "publication.py", SRC / "review" / "checkout.py", SRC / "review" / "committed.py",
]
#: The functions P2 adds to live modules: the same holds inside them (the live code beside them keeps reason None).
P2_FUNCTIONS_IN_LIVE_MODULES = {
    "mutation.py": {"_bind_recovered_reservations", "conflict", "_make_planning_commit", "require_base",
                    "_planning_publication", "_publication_contract", "_require_publication_barrier",
                    "_validate_planning_commit", "_no_hooks_directory", "planned_write"},
    "roadmap.py": {"require_marker_compatible", "planning_marker"},
    "gitops.py": {"require_no_planning_transform", "review_commit_effect", "review_publication_effect"},
}
CONTRACT = WORKLINE_ROOT / "REVIEW_SYSTEM_P2_INTEGRATION_CONTRACT.md"


class _Refusals:
    """What a module's refusals name: resolved reasons and codes, what cannot be resolved, reasonless P2 raises."""

    def __init__(self) -> None:
        self.reasons: set = set()
        self.codes: set[str] = set()
        self.unresolved: list[str] = []
        self.reasonless: list[str] = []


def _call_name(node: ast.Call) -> str:
    return node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")


def _values(node: ast.AST, names: dict[str, set]) -> set | None:
    """The text values ``node`` can take: a literal, a conditional of literals, or a name bound to literals."""
    if isinstance(node, ast.Constant) and (node.value is None or isinstance(node.value, str)):
        return {node.value}
    if isinstance(node, ast.IfExp):
        body, orelse = _values(node.body, names), _values(node.orelse, names)
        return None if body is None or orelse is None else body | orelse
    if isinstance(node, ast.Name) and node.id in names:
        return set(names[node.id])
    return None


def _own_calls(scope: ast.AST) -> list[ast.Call]:
    """The calls in ``scope`` itself, not in a function nested in it."""
    calls: list[ast.Call] = []
    pending = list(ast.iter_child_nodes(scope))
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Call):
            calls.append(node)
        pending.extend(ast.iter_child_nodes(node))
    return calls


def _refusals(path: Path) -> _Refusals:
    found = _Refusals()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    p2_only = path in P2_ONLY_MODULES
    p2_functions = P2_FUNCTIONS_IN_LIVE_MODULES.get(path.name, set())
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names: dict[str, set] = {}
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.setdefault(target.id, set()).add(node.value.value)
        for node in _own_calls(scope):
            name = _call_name(node)
            where = f"{path.name}:{node.lineno}"
            if name == "ReconcileRequired":
                reason = [keyword.value for keyword in node.keywords if keyword.arg == "reason"]
                if not reason:
                    if p2_only or scope.name in p2_functions:
                        found.reasonless.append(where)
                    continue
                if isinstance(reason[0], ast.Attribute) and reason[0].attr == "reason":
                    continue  # a _Refused's reason: every _Refused construction is resolved below
                if scope.name == "_reconcile" and isinstance(reason[0], ast.Name) and reason[0].id == "reason":
                    continue  # the helper passes its caller's reason on: every _reconcile call is resolved below
                values = _values(reason[0], names)
                if values is None:
                    found.unresolved.append(where)
                else:
                    found.reasons |= values
            elif name in ("_reconcile", "_Refused") and len(node.args) >= 2:
                values = _values(node.args[1], names)
                if values is None:
                    found.unresolved.append(where)
                else:
                    found.reasons |= values
            elif name in ("StopError", "ValidationError"):
                for keyword in node.keywords:
                    if keyword.arg == "code" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                        found.codes.add(keyword.value.value)
    return found


def _raised(path: Path) -> tuple[set[str], set[str]]:
    """The reasons and codes of every P2 refusal constructed in ``path`` (``None``, the live reason, left out)."""
    found = _refusals(path)
    return {reason for reason in found.reasons if reason is not None}, found.codes


def _contract_catalogue() -> tuple[set[str], set[str], set[str]]:
    """§25.1 as the frozen contract states it: the ReconcileRequired reasons, the codes, the non-exception reasons."""
    text = CONTRACT.read_text(encoding="utf-8")
    section = text[text.index("### 25.1 Error and reason catalogue"):text.index("## 26. Authority changes")]
    reasons: set[str] = set()
    codes: set[str] = set()
    other: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        names = set(re.findall(r"`([a-z_]+)`", cells[0]))
        if "ReconcileRequired" in cells[1] and "reason" in cells[1]:
            reasons |= names
        elif "no exception" in cells[1]:
            other |= names
        else:
            codes |= names
    return reasons, codes, other


def _contract_uses() -> set[str]:
    """Every code or reason the contract names where something raises or reports one."""
    text = CONTRACT.read_text(encoding="utf-8")
    used: set[str] = set()
    for pattern in (r"code `([a-z_]+)`", r"reason `([a-z_]+)`", r"`StopError` `([a-z_]+)`", r"`ValidationError` `([a-z_]+)`"):
        used |= set(re.findall(pattern, text))
    for group in re.findall(r"`(?:ReconcileRequired|StopError)` \(([^)]*)\)", text):
        used |= set(re.findall(r"`([a-z_]+)`", group))
    return used


class ReasonAttributeTests(PlanningTestCase):
    def test_a_reconcile_required_keeps_its_code_and_carries_a_reason(self) -> None:
        built = ReconcileRequired("a live reconcile")
        self.assertEqual(("reconcile_required", None), (built.code, built.reason))
        p2 = ReconcileRequired("a P2 reconcile", reason="review_commit_unowned")
        self.assertEqual(("reconcile_required", "review_commit_unowned"), (p2.code, p2.reason))

    def test_a_live_reconcile_on_the_review_v1_path_has_no_reason(self) -> None:
        store = self.planning_project()
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        with self.assertRaises(ReconcileRequired) as raised:
            self.reviewed_roadmap(store, Reviewer(), rm.RoadmapPlan("Planned Roadmap", "another background", "状態",
                                                                    {"a": planning_phase("A")}))
        self.assertEqual(("reconcile_required", None), (raised.exception.code, raised.exception.reason))

    def test_every_reason_and_code_p2_raises_is_in_the_catalogue(self) -> None:
        reasons: set[str] = set()
        codes: set[str] = set()
        for path in P2_MODULES:
            found_reasons, found_codes = _raised(path)
            reasons |= found_reasons
            codes |= {code for code in found_codes if code.startswith("review_")}
        self.assertTrue(reasons >= {"review_commit_unowned", "review_persisted_proof_failed"})
        self.assertEqual(set(), reasons - CATALOGUE_REASONS, "a reason outside §25.1")
        self.assertEqual(set(), codes - CATALOGUE_CODES, "a code outside §25.1")

    def test_every_reconcile_required_p2_raises_names_a_catalogue_reason(self) -> None:
        for path in P2_MODULES:
            found = _refusals(path)
            with self.subTest(path.name):
                self.assertEqual([], found.unresolved, "a reason the scan cannot resolve to catalogue text")
                self.assertEqual([], found.reasonless, "a P2 ReconcileRequired without a reason")
                self.assertEqual(set(), found.reasons - CATALOGUE_REASONS - {None}, "a reason outside §25.1")
                if path in P2_ONLY_MODULES:
                    self.assertNotIn(None, found.reasons, "only live code keeps reason None")
        self.assertEqual({"review_publication_invalid", "review_publication_contract_invalid",
                          "review_registration_base_moved", "review_recovery_reservation_conflict", None},
                         _refusals(SRC / "mutation.py").reasons)

    def test_the_catalogue_is_the_contracts_and_covers_every_code_and_reason_it_names(self) -> None:
        reasons, codes, other = _contract_catalogue()
        self.assertEqual(CATALOGUE_REASONS, reasons)
        self.assertEqual(CATALOGUE_CODES, codes)
        self.assertEqual({"review_context_changed", "review_policy_changed", "review_declared_base_changed",
                          "invalidated", "consumed", "not_authorized", "set_aside"}, other)
        used = _contract_uses()
        self.assertTrue(used >= {"review_publication_barrier", "review_registration_base_moved", "review_checkout_unsafe",
                                 "review_recovery_incomplete", "dirty_overlap"})
        self.assertEqual(set(), used - reasons - codes - other, "a code or reason the contract uses outside §25.1")


def planning_phase(name: str):
    from workline.phase_create import PhaseSpec

    return PhaseSpec(name, f"{name} が成立する")


class BaseExactTests(PlanningTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()

    def crash_before_kp_is_made(self) -> None:
        with crash_at(mutation_module, "_make_planning_commit", when=lambda n, s, payload, paths: payload.get("base_exact") is True):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store)

    def test_an_unapplied_kp_on_its_base_is_made_after_the_pre_replay_proof(self) -> None:
        self.crash_before_kp_is_made()
        order: list[str] = []
        real_proof, real_make = rr._pre_kp_proof, mutation_module._make_planning_commit

        def proof(*args, **kwargs):
            order.append("pre-Kp proof")
            return real_proof(*args, **kwargs)

        def make(store, payload, paths):
            if payload.get("base_exact") is True:
                order.append("Kp made")
            return real_make(store, payload, paths)

        with mock.patch.object(rr, "_pre_kp_proof", proof), mock.patch.object(mutation_module, "_make_planning_commit", make):
            self.assertEqual("registered", self.reviewed_roadmap(self.store).status)
        self.assertEqual(["pre-Kp proof", "Kp made"], order)

    def test_an_independent_advance_is_a_mismatch_never_the_independent_advancement_path(self) -> None:
        self.crash_before_kp_is_made()
        (self.store.root / "notes.txt").write_text("independent\n", encoding="utf-8")
        self.commit_all(self.store, "an independent commit", "notes.txt")
        real = mutation_module._head_advanced_independently
        asked: list[dict] = []

        def spy(repo, payload, head):
            asked.append(payload)
            return real(repo, payload, head)

        with mock.patch.object(mutation_module, "_head_advanced_independently", spy):
            with self.assertRaises(ReconcileRequired) as raised:
                self.reviewed_roadmap(self.store)
        self.assertEqual("review_registration_base_moved", raised.exception.reason)
        self.assertFalse([p for p in asked if p.get("base_exact") is True], "never asked for a base-exact commit")

    def test_a_kp_recorded_applied_with_its_id_is_decided_by_that_id(self) -> None:
        with crash_at(rr, "_c2_kp"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store)
        kp = self.head(self.store)
        with mock.patch.object(mutation_module, "_make_planning_commit", side_effect=AssertionError("made again")):
            with crash_at(rr, "_consumption_record"):
                with self.assertRaises(Crash):
                    self.reviewed_roadmap(self.store)  # its ID shows it held: C-2(Kp) runs, nothing is made again
        git(self.store.root, "reset", "-q", "--hard", f"{kp}~1")  # the branch no longer holds that ID
        with self.assertRaises(ReconcileRequired) as raised:
            self.reviewed_roadmap(self.store)
        self.assertEqual("review_registration_base_moved", raised.exception.reason)

    def test_a_legacy_commit_keeps_the_independent_advancement_rule(self) -> None:
        other = rm.create_roadmap(self.store, plan("Other Roadmap")).roadmap_id
        with crash_at(mutation_module, "_make_commit", when=lambda n, mutation, record: "roadmap_held" in record["payload"]["message"]):
            with self.assertRaises(Crash):
                rm.hold_roadmap(self.store, other)
        (self.store.root / "notes.txt").write_text("independent\n", encoding="utf-8")
        advanced = self.commit_all(self.store, "an independent commit", "notes.txt")
        held = rm.hold_roadmap(self.store, other)
        self.assertEqual(advanced, git(self.store.root, "rev-parse", f"{held.head}~1").strip(), "made on the new HEAD")


class DeltaRecordTests(PlanningTestCase):
    def assert_object_id(self, value, length: int) -> None:
        self.assertIsInstance(value, str)
        self.assertRegex(value, "^[0-9a-f]{%d}$" % length)

    def assert_types(self, record: dict, length: int, parent: str, commit: str) -> None:
        self.assertEqual({"schema", "version", "parent", "commit", "entries"}, set(record))
        self.assertEqual(("review-planning-delta", 1), (record["schema"], record["version"]))
        self.assertIs(int, type(record["version"]))
        self.assert_object_id(record["parent"], length)
        self.assert_object_id(record["commit"], length)
        self.assertEqual((parent, commit), (record["parent"], record["commit"]))
        paths = [entry["path"] for entry in record["entries"]]
        self.assertEqual(sorted(paths, key=lambda path: path.encode("utf-8")), paths, "sorted by path, bytewise")
        for entry in record["entries"]:
            self.assertEqual({"path", "status", "old_mode", "new_mode", "old_blob", "new_blob"}, set(entry))
            self.assertIsInstance(entry["path"], str)
            self.assertIn(entry["status"], ("A", "M"))
            self.assertIsInstance(entry["old_mode"], str)
            self.assertIsInstance(entry["new_mode"], str)
            self.assertEqual("000000" if entry["status"] == "A" else "100644", entry["old_mode"])
            self.assertEqual("100644", entry["new_mode"])
            for key in ("old_blob", "new_blob"):
                self.assert_object_id(entry[key], length)
            self.assertEqual(entry["status"] == "A", entry["old_blob"] == "0" * length)

    def test_every_scalar_has_its_type_and_integer_modes_digest_differently(self) -> None:
        store = self.planning_project()
        result = self.reviewed_roadmap(store)
        found = registered(store, result)
        context = ReviewStore(store).read_task_input(
            self.chain(store, result.review_run_id).generations[0].accepted_tasks[0]["task_id"]).request_envelope["context"]
        expected = rr.expected_projection(store, found.material, context, found.parent)
        record = expected.delta_record(found.kp)
        self.assert_types(record, 40, found.parent, found.kp)
        self.assertEqual({"A", "M"}, {entry["status"] for entry in record["entries"]}, "added files and a changed ledger")
        self.assertIn("0" * 40, [entry["old_blob"] for entry in record["entries"]], "the zero ID for an added path")
        integer_modes = {**record, "entries": [{**e, "old_mode": int(e["old_mode"]), "new_mode": int(e["new_mode"])}
                                               for e in record["entries"]]}
        forged_digest = serialize.digest(integer_modes)
        self.assertNotEqual(expected.delta_digest(found.kp), forged_digest)
        forged = replace(found.consumption, persisted_result={**found.consumption.persisted_result,
                                                              "registration_delta_digest": forged_digest})
        km = plumb_commit(store, found.kp, {found.consumption_path: serialize.canonical_text(forged.to_record())})
        (run,) = [r for r in publication.registered_runs(store.root, km)
                  if r.candidate_hash == planning.candidate_hash(found.material)]
        self.assertEqual("CP9", publication.committed_planning_proof(store.root, km, run)[0])

    def test_a_sha256_repository_gives_64_character_ids_and_a_64_character_zero_id(self) -> None:
        root = self.tmp / "sha256"
        root.mkdir()
        git(root, "init", "-q", "--object-format=sha256", "-b", "main")
        with cwd(WORKLINE_ROOT):
            project_start(root, WORKLINE_ROOT)
        self.enter(root)
        store = ProjectStore(root)
        self.commit_attributes(store, "* text=auto\n" + CANONICAL_RULE + "\n")
        result = self.reviewed_roadmap(store)
        self.assertEqual("registered", result.status)
        found = registered(store, result)
        self.assertEqual(64, len(found.kp))
        context = ReviewStore(store).read_task_input(
            self.chain(store, result.review_run_id).generations[0].accepted_tasks[0]["task_id"]).request_envelope["context"]
        record = rr.expected_projection(store, found.material, context, found.parent).delta_record(found.kp)
        self.assert_types(record, 64, found.parent, found.kp)
        self.assertIn("0" * 64, [entry["old_blob"] for entry in record["entries"]])


def version(value):
    return mock.patch.object(gitcmd, "running_git_version", lambda: value)


class GitMinimumTests(PlanningTestCase):
    """The version reader patched to each version; the histories built for real and run through the production proof."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project(remote=True)
        self.other = rm.create_roadmap(self.store, plan("Other Roadmap")).roadmap_id

    def legacy_push(self) -> str:
        held = rm.hold_roadmap(self.store, self.other)
        self.assertEqual(held.head, self.remote_head())
        return held.head

    def test_a_2_40_0_passes_the_gate_and_the_publication_proof_runs(self) -> None:
        proofs: list[str] = []
        real = publication.committed_planning_proof
        with version((2, 40, 0)), mock.patch.object(publication, "committed_planning_proof",
                                                    lambda repo, commit, run: proofs.append(commit) or real(repo, commit, run)):
            result = self.reviewed_roadmap(self.store)
        self.assertEqual("registered", result.status)
        self.assertIn(result.registration.head, proofs)

    def test_b_2_39_refuses_review_v1_and_leaves_a_pending_mutation_untouched(self) -> None:
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store)
        (record,) = self.pending(self.store)
        path = self.store.mutations / f"{record['mutation_id']}.yaml"
        before = path.read_bytes()
        with version((2, 39, 5)):
            with self.assertRaises(StopError) as raised:
                self.reviewed_roadmap(self.store)
        self.assertEqual("review_git_unsupported", raised.exception.code)
        self.assertEqual(before, path.read_bytes())

    def test_b_2_39_stops_before_the_lock_and_writes_nothing(self) -> None:
        from workline import oplock

        phase_id = rm.create_roadmap(self.store, plan("A Roadmap To Enter")).phase_ids["a"]
        before = state_entries(self.store)
        head = self.head(self.store)
        with version((2, 39, 5)), mock.patch.object(oplock, "project_operation", side_effect=AssertionError("the lock")):
            for call in (lambda: self.reviewed_roadmap(self.store),
                         lambda: self.reviewed_entry(self.store, phase_id, Reviewer())):
                with self.assertRaises(StopError) as raised:
                    call()
                self.assertEqual("review_git_unsupported", raised.exception.code)
        self.assertEqual(before, state_entries(self.store))
        self.assertEqual(head, self.head(self.store))

    def test_b_2_39_a_legacy_invocation_registers_as_today(self) -> None:
        with version((2, 39, 5)):
            created = rm.create_roadmap(self.store, plan("A Legacy Roadmap"))
        self.assertEqual(created.head, self.remote_head())

    def publication_behaviour(self, found_version) -> None:
        with version(found_version):
            self.legacy_push()  # a history with no Candidate snapshot is cleared by the fast path
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store, Reviewer(), plan("Generation One Only"))
        runs: list[str] = []
        real = publication.registered_runs
        with version(found_version), mock.patch.object(publication, "registered_runs",
                                                       lambda repo, commit: runs.append(commit) or real(repo, commit)):
            rm.resume_roadmap(self.store, self.other)  # a snapshot and generation 1 only: no registration commit
        self.assertTrue(runs, "registered-Run discovery ran with the publication command set")
        self.assertEqual(self.head(self.store), self.remote_head())

    def test_b_the_publication_behaviour_on_2_39(self) -> None:
        self.publication_behaviour((2, 39, 5))

    def test_c_the_publication_behaviour_on_exactly_2_31_0(self) -> None:
        self.publication_behaviour((2, 31, 0))

    def valid_and_invalid_kp(self, found_version) -> None:
        valid = self.reviewed_roadmap(self.store)
        gitcmd.forget_object_answers()
        with version(found_version):
            self.assertIsNone(publication.barrier_problem(self.store.root, valid.registration.head))
            self.legacy_push()
        with noncanonical_registration():
            with self.assertRaises(ReconcileRequired) as raised:
                self.reviewed_roadmap(self.store, Reviewer(), plan("Invalid Registration"))
        self.assertEqual("review_persisted_proof_failed", raised.exception.reason)
        gitcmd.forget_object_answers()
        with version(found_version):
            self.assertIn("CP5 fails", publication.barrier_problem(self.store.root, self.head(self.store)))

    def test_b_a_valid_kp_km_history_passes_and_an_invalid_kp_holds_on_2_39(self) -> None:
        self.valid_and_invalid_kp((2, 39, 5))

    def test_c_a_valid_kp_km_history_passes_and_an_invalid_kp_holds_on_exactly_2_31_0(self) -> None:
        self.valid_and_invalid_kp((2, 31, 0))

    def test_d_2_30_9_clears_a_snapshot_free_history_and_refuses_one_holding_a_snapshot(self) -> None:
        with version((2, 30, 9)):
            self.legacy_push()
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store)
        with version((2, 30, 9)):
            with self.assertRaises(StopError) as raised:
                rm.resume_roadmap(self.store, self.other)
        self.assertEqual("review_publication_barrier", raised.exception.code)
        self.assertIn(publication.UNAVAILABLE_BELOW, str(raised.exception))
        self.assertNotIn("candidate", str(raised.exception), "names no Run")

    def test_e_an_unparseable_version(self) -> None:
        with version(None):
            with self.assertRaises(StopError) as raised:
                self.reviewed_roadmap(self.store)
            self.assertEqual("review_git_unsupported", raised.exception.code)
            self.legacy_push()  # the fast-path read ran and listed nothing
            with mock.patch.object(gitcmd, "history_touches", lambda repo, commit, directory: None):
                self.assertIsNotNone(publication.barrier_problem(self.store.root, self.head(self.store)))
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store)
        with version(None):
            problem = publication.barrier_problem(self.store.root, self.head(self.store))
        self.assertEqual(publication.UNAVAILABLE_UNKNOWN, problem)

    def pushes_on_2_31_0(self) -> None:
        with version((2, 31, 0)):
            self.legacy_push()

    def crashed(self, name: str) -> None:
        with crash_at(rr, name):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store)

    def test_f_generation_1_only(self) -> None:
        self.crashed("_launch_and_settle")
        self.pushes_on_2_31_0()

    def test_f_generation_2_only(self) -> None:
        self.crashed("_seal")
        self.pushes_on_2_31_0()

    def test_f_generation_3_without_a_registration_commit(self) -> None:
        self.crashed("_use_check")
        self.pushes_on_2_31_0()

    def test_f_generation_4_and_stale(self) -> None:
        self.crashed("_use_check")
        real = planning._read_authority
        with mock.patch.object(planning, "_read_authority",
                               lambda path: real(path) + (b"\nchanged\n" if str(path).endswith("registry.md") else b"")):
            self.assertEqual("stale", self.reviewed_roadmap(self.store).status)
        self.pushes_on_2_31_0()

    def test_f_not_authorized(self) -> None:
        self.assertEqual("not_authorized", self.reviewed_roadmap(self.store, Reviewer(status="declined")).status)
        self.pushes_on_2_31_0()


class NoAttributeEvaluationTests(PlanningTestCase):
    def test_the_barrier_and_the_proof_read_committed_objects_only(self) -> None:
        store = self.planning_project()
        found = registered(store, self.reviewed_roadmap(store))
        (run,) = [r for r in publication.registered_runs(store.root, found.km)
                  if r.candidate_hash == planning.candidate_hash(found.material)]
        broken = plumb_commit(store, found.km, {".workline/review/gates/" + run_ids(store)[0] + "/000002.yaml": "x: 1\n"})
        before = (publication.barrier_problem(store.root, found.km), publication.barrier_problem(store.root, broken))
        import shutil

        shutil.rmtree(store.root / ".workline" / "review")
        gitcmd.forget_object_answers()
        with mock.patch.object(gitcmd, "check_attributes", side_effect=AssertionError("check-attr ran")):
            after = (publication.barrier_problem(store.root, found.km), publication.barrier_problem(store.root, broken))
        self.assertEqual(before, after)
        self.assertIsNone(after[0])
        self.assertIn("CP4 fails", after[1])


class OneSpellingTests(PlanningTestCase):
    def test_the_add_history_read_always_runs_diff_merges_combined(self) -> None:
        reads: list[tuple] = []
        real = gitcmd.run_git_bytes

        def spy(repo, *args, **kwargs):
            if "log" in args and "--diff-filter=A" in args:
                reads.append(args)
            return real(repo, *args, **kwargs)

        store = self.planning_project(remote=True)
        other = rm.create_roadmap(store, plan("Other Roadmap")).roadmap_id
        with mock.patch.object(gitcmd, "run_git_bytes", spy):
            self.reviewed_roadmap(store)
            for found_version in ((2, 31, 0), (2, 54, 0)):
                gitcmd.forget_object_answers()
                with version(found_version):
                    (rm.hold_roadmap if found_version[1] == 31 else rm.resume_roadmap)(store, other)
        self.assertTrue(reads)
        for args in reads:
            self.assertIn("--diff-merges=combined", args)
            self.assertEqual(["--full-history", "--no-renames", "--diff-merges=combined", "--diff-filter=A", "--name-only", "-z"],
                             [a for a in args if a.startswith("-") and a != "--" and not a.startswith("--format")])



class AuthorityTextTests(unittest.TestCase):
    """§26: each rule has one normative owner; the Skills name rules/git instead of restating it."""

    @staticmethod
    def read(*parts: str) -> str:
        return WORKLINE_ROOT.joinpath(*parts).read_text(encoding="utf-8")

    def test_rules_git_carries_the_git_operation_rules_and_no_write_scope_list(self) -> None:
        registry = self.read("registry.md")
        rules_git = registry[registry.index("<!-- workline-id: rules/git -->"):registry.index("## AI Decision")]
        for phrase in (
            "review-v1 planning operation", "recovery planning mutation", "`recovery_of_review_run_id`",  # item 1
            "`review-v1-planning-local-v1`", "`core.hooksPath`", "`dirty_overlap`",  # item 2
            "`base_exact`", "`review_registration_base_moved`",  # item 3
            "expected physical projection",  # item 4
            "`review-v1-planning-publication-v1`", "`review-publication`", "C-2(Km)",  # item 5
            "publication barrier", "`.workline/review/candidate-snapshots/`", "fast-path read",  # item 6
            "`not_authorized`", "`stale`",  # item 7
            "### Git versions", "P2_REVIEW_GIT_MIN      = 2.40.0", "P2_PUBLICATION_GIT_MIN = 2.31.0",
            "`review_git_unsupported`", "`review_publication_barrier`",  # item 8
        ):
            with self.subTest(phrase):
                self.assertIn(phrase, rules_git)
        self.assertNotIn("consumptions/<consumption_id>.yaml", rules_git, "rules/git keeps no per-operation write scope")
        self.assertNotIn("予定write scopeは", rules_git)

    def test_the_roadmap_skill_carries_the_planning_operation_and_the_write_scope_exception(self) -> None:
        skill = self.read(".claude", "skills", "roadmap", "SKILL.md")
        section = skill[skill.index("## Review-v1 planning"):skill.index("## Mutation / Git")]
        for phrase in (
            "review=PlanningReview(...)", "`review_marker_mismatch`", "`P2_REVIEW_GIT_MIN`",
            "canonical-input preflight", "canonical recovery discovery", "phase_already_expanded",
            "R9のcanonical self-selection", "`review_base_uncommitted`", "`use_check_head`", "pre-Kp currency proof",
            "CanonicalPlanningWriterInput", "display base check", "`review_binding`", "recovery planning mutation",
            "`recovery_binding`", "pre-freeze resume setup", "`review_setup_invalid`", "`reason`",
        ):
            with self.subTest(phrase):
                self.assertIn(phrase, section)
        scope = skill[skill.index("各Roadmap operationが宣言する予定write scope"):]
        self.assertIn("1つだけ例外", scope)
        self.assertIn("`.workline/review/consumptions/<consumption_id>.yaml`", scope)
        self.assertIn("この規則はlegacy Phase entryのものである", skill, "the resumed-entry rule stays for legacy")

    def test_the_review_skill_carries_its_part_and_names_rules_git(self) -> None:
        skill = self.read(".claude", "skills", "review", "SKILL.md")
        for phrase in (
            "roadmap-plan-v1", "phase-entry-design-v1", "## Planning Review Policy", "PlanningReview(reviewer",
            "## Adjudication", "PlanningConsumption", "`review-planning-delta`", '`"100644"`', "64文字",
            "invalidate", "committed planning proof", "expected physical projection", "`set_aside_runs`",
            "## Checkout capability", "form L", ".workline/review/** !text eol=lf -filter -ident -working-tree-encoding",
            "subordinate", "NOT ACTIVATED",
        ):
            with self.subTest(phrase):
                self.assertIn(phrase, skill)
        self.assertIn("`rules/git`（Commit / push、Push destination、Git versions）が所有", skill)
        self.assertNotIn("2.31.0", skill, "the minimums are named, not restated")
        self.assertNotIn("2.40.0", skill)
        registry = self.read("registry.md")
        rules_git = registry[registry.index("<!-- workline-id: rules/git -->"):registry.index("## AI Decision")]
        for restated in ("--full-history", "--diff-merges", "gitops.finalize", "_classify_push"):
            with self.subTest(restated=restated):
                self.assertNotIn(restated, skill, "the barrier's reads and the push stage's mechanics belong to rules/git")
        self.assertIn("--full-history", rules_git, "rules/git is where the barrier's read is stated")


class StaticInvariantTests(unittest.TestCase):
    def test_every_push_point_holds_the_publication_barrier(self) -> None:
        mutation_text = (SRC / "mutation.py").read_text(encoding="utf-8")
        self.assertEqual(1, mutation_text.count("gitcmd.push("), "one place pushes")
        apply_effect = mutation_text[mutation_text.index("    def apply_effect("):]
        self.assertLess(apply_effect.index("_require_publication_barrier("), apply_effect.index("gitcmd.push("))
        classify = mutation_text[mutation_text.index("    def _classify_push("):mutation_text.index("    def _create_review_record(")]
        self.assertIn("_require_publication_barrier(", classify)
        gitops_text = (SRC / "gitops.py").read_text(encoding="utf-8")
        finalize = gitops_text[gitops_text.index("def finalize("):]
        self.assertIn("publication.require_barrier_clear(", finalize[:finalize.index("\ndef ")])
        for path in sorted(SRC.rglob("*.py")):
            if path.name != "mutation.py":
                self.assertNotIn("gitcmd.push(", path.read_text(encoding="utf-8"), path.name)

    def test_p3_stays_inactive_and_nothing_writes_an_activation_record(self) -> None:
        for path in sorted(SRC.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "WORK_TERMINAL_ACTIVATION_REL" in text:
                self.assertIn(path.name, ("paths.py", "store.py", "validate.py"), f"{path.name} names the activation path")

    def test_the_object_answer_cache_is_in_process_only(self) -> None:
        text = (SRC / "gitcmd.py").read_text(encoding="utf-8")
        cache = text[text.index("_OBJECT_ANSWERS"):]
        self.assertNotIn("open(", cache[:cache.index("def _remembered")], "never persisted")

    def test_the_publication_proof_reads_committed_objects_only_and_evaluates_no_attribute(self) -> None:
        for name in ("publication.py", "committed.py"):
            text = (SRC / "review" / name).read_text(encoding="utf-8").replace("CommittedReviewStore(", "")
            for forbidden in ("checkout", "check_attributes", "ReviewStore(", "read_text("):
                self.assertNotIn(forbidden, text, f"review/{name} uses {forbidden}")


if __name__ == "__main__":
    unittest.main()
