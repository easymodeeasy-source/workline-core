"""RB4 / P5 §28.6, OD-2: the planning push validator publishes the P5 Km only for a positively proven P5 Run.

``mutation._planning_publication``: a Km whose Consumption stage also carries a Run summary at
``.workline/review/history/runs/<review_run id>.yaml`` is published only when the planning owner's
``roadmap_review.p5_publication_problem`` proves - from the canonical stored Review identity in Km's own tree -
that the Run the summary names is the Run the Consumption consumes, and that this Run is explicitly P5-capable:
every generation-1 TaskInput binds the planning P4-family contract, the P5 policy and the history contract,
generation 1 binds the P5 Effective Policy, and the summary is its consumed summary of exactly that Consumption.
Being in the P4 family (the durable invocation marker) is no proof of P5 (GAP-A option 3). Pre-P5 and P4-only
planning keep the exact Consumption-only semantics.

* OD2-T1 legacy v1, Consumption only                                         accepted exactly as before
* OD2-T2 P4-only planning, Consumption only                                  accepted exactly as before
* OD2-T3 P5-capable planning Run + exact Run summary + Consumption           accepted
* OD2-T4 P4-only planning Run + Run summary + Consumption                    REFUSED
* OD2-T5 P4-family invocation, no positively proven P5 Run, extra summary    REFUSED
* OD2-T6 wrong Run ID / missing TaskInput / unreadable policy / mismatching history contract   REFUSED
* OD2-T7 two summaries, malformed summary path, missing Consumption, external changed path     still refused
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
from typing import Any, Callable
import unittest

from helpers import git, rmtree
from workline import mutation
from workline.ids import new_id
from workline.review import history, p4, paths, planning, records, serialize

RUN = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"
OTHER_RUN = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAW"
TASK = "rtk_01ARZ3NDEKTSV4RRFFQ69G5FA1"
CONSUMPTION_ID = "rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV"
RECEIPT_ID = new_id("review_receipt")
ROADMAP = new_id("roadmap")
KIND = "roadmap-plan-v1"
CANDIDATE = "a" * 64
OPERATION = "roadmap-create:" + "e" * 64
CONSUMPTION = paths.consumption_rel(CONSUMPTION_ID)
SUMMARY = paths.history_run_rel(RUN)
V1 = {"operation": "roadmap-create", "review_contract": "review-v1-planning-v1",
      "publication_contract": "review-v1-planning-publication-v1"}
P4_FAMILY = {**V1, "review_contract": "review-v1-planning-p4-v1"}


def text(record: dict[str, Any]) -> bytes:
    return serialize.canonical_text(record).encode("utf-8")


def first_gate(run_id: str, policy: str, task_input: records.TaskInput) -> records.GateGeneration:
    return records.GateGeneration(
        review_run_id=run_id, generation=1, previous_generation=None, previous_digest=None, review_kind=KIND,
        target_identity=ROADMAP, operation_identity=OPERATION, candidate_hash=CANDIDATE, review_context_hash="c" * 64,
        effective_policy_hash=p4.policy_hash(policy), evidence_digest="f" * 64, coverage_digest="f" * 64,
        raw_report_set_digest="f" * 64, adjudication_digest="f" * 64, obligation_digest="f" * 64,
        accepted_tasks=(p4.accepted_descriptor(task_input),), settled_tasks=(), status=records.GATE_STATUS_OPEN,
        receipt_id=None, authorized_operation_stage=None,
    )


def run_records(run_id: str = RUN, policy: str = p4.P5_POLICY_ID, *, gate_policy: str | None = None,
                edit: Callable[[dict[str, Any]], None] | None = None,
                task_input_present: bool = True) -> dict[str, bytes]:
    """The canonical generation 1 and TaskInput of one planning Run of the P4 family under ``policy``.

    ``edit`` changes the stored request envelope (its digest follows); ``gate_policy`` makes generation 1 bind
    another Effective Policy than the TaskInput's; ``task_input_present=False`` leaves the TaskInput out.
    """
    envelope = p4.discovery_request(
        review_contract=planning.P4_CONTRACT, review_kind=KIND, viewpoint="correctness", candidate={"c": 1},
        context={"x": 1}, requirement={"r": 1}, candidate_generation=1, succession=None, set_aside_runs=[],
        human_decision=None, policy_id=policy,
    )
    task_input = p4.task_input(task_id=TASK, task_slot=p4.discovery_slot("correctness"),
                               task_kind=p4.TASK_KIND_DISCOVERY, actor_identity="d", actor_version="1",
                               envelope=envelope, candidate_hash=CANDIDATE, candidate_material_digest="b" * 64,
                               review_context_hash="c" * 64, accepted_generation=1, policy_id=policy)
    if edit is not None:
        changed = dict(envelope)
        edit(changed)
        changed = serialize.canonical_data(changed)
        task_input = replace(task_input, request_envelope=changed, request_digest=serialize.digest(changed))
    found = {paths.gate_rel(run_id, 1): text(first_gate(run_id, gate_policy or policy, task_input).to_record())}
    if task_input_present:
        found[paths.task_input_rel(TASK)] = text(task_input.to_record())
    return found


def consumption(run_id: str = RUN) -> bytes:
    return text(records.PlanningConsumption(
        consumption_id=CONSUMPTION_ID, receipt_id=RECEIPT_ID, review_run_id=run_id, review_generation=5,
        review_kind=KIND, authorized_candidate_hash=CANDIDATE, operation_identity=OPERATION,
        operation_mutation_id=new_id("mutation"), target_identity=ROADMAP,
        persisted_result={
            "contract": records.PERSISTED_RESULT_CONTRACT, "request_digest": "a" * 64,
            "registration_commit": "1" * 40, "registration_parent": "2" * 40, "branch": "refs/heads/main",
            "registration_delta_digest": "b" * 64, "semantic_projection_digest": "c" * 64,
            "adapter_identity": records.PLANNING_ADAPTER_IDENTITY[KIND], "loader_identity": "d" * 64,
            "roadmap_id": ROADMAP, "phase_ids": [], "relation_ids": [],
        },
    ).to_record())


def summary(run_id: str = RUN, policy: str = p4.P5_POLICY_ID, *, disposition: str = history.DISPOSITION_CONSUMED,
            consumption_id: str = CONSUMPTION_ID) -> bytes:
    """The consumed Run summary of a sealed generation 5 of the Run (built by the history core)."""
    envelope = p4.discovery_request(
        review_contract=planning.P4_CONTRACT, review_kind=KIND, viewpoint="correctness", candidate={"c": 1},
        context={"x": 1}, requirement={"r": 1}, candidate_generation=1, succession=None, set_aside_runs=[],
        human_decision=None, policy_id=policy,
    )
    task_input = p4.task_input(task_id=TASK, task_slot=p4.discovery_slot("correctness"),
                               task_kind=p4.TASK_KIND_DISCOVERY, actor_identity="d", actor_version="1",
                               envelope=envelope, candidate_hash=CANDIDATE, candidate_material_digest="b" * 64,
                               review_context_hash="c" * 64, accepted_generation=1, policy_id=policy)
    sealed = replace(first_gate(run_id, policy, task_input), generation=5, previous_generation=4,
                     previous_digest="9" * 64, status=records.GATE_STATUS_SEALED, receipt_id=RECEIPT_ID,
                     authorized_operation_stage="roadmap-create:registration")
    consumed = disposition == history.DISPOSITION_CONSUMED
    return text(history.run_summary(sealed, durable_disposition=disposition, candidate_generation=1,
                                    receipt_id=RECEIPT_ID if consumed else None,
                                    consumption_id=consumption_id if consumed else None).to_record())


#: The Km of a P5-capable Run: its consumed summary and the Consumption of it.
P5_KM = {SUMMARY: summary(), CONSUMPTION: consumption()}


class PlanningPushTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="wl-p5-push-"))
        self.addCleanup(rmtree, self.base)
        self.repos = 0

    def repo(self) -> Path:
        """A fresh repository whose one commit is the registration commit."""
        self.repos += 1
        root = self.base / f"r{self.repos}"
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@example.invalid")
        git(root, "config", "user.name", "t")
        git(root, "config", "core.autocrlf", "false")
        self.write(root, {"registered.txt": b"registration\n"})
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "registration")
        return root

    @staticmethod
    def write(root: Path, files: dict[str, bytes]) -> None:
        for relative, data in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def verdict(self, invocation: dict, stage_paths: list[str], committed: dict[str, bytes],
                run: dict[str, bytes] | None = None):
        """The validator's verdict on a push of Km (``committed`` on top of the Run's committed ``run`` records)."""
        root = self.repo()
        registration = git(root, "rev-parse", "HEAD").strip()
        if run:
            self.write(root, run)
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "review records")
        self.write(root, committed)
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "metadata")
        km = git(root, "rev-parse", "HEAD").strip()
        effects = [
            {"stage": "review-registration-commit", "kind": "git_commit", "seq": 1, "applied": True,
             "commit_id": registration, "payload": {"branch": "refs/heads/main"}},
        ]
        effects += [{"stage": "review-consumption", "kind": "create_file", "seq": 2 + index, "applied": True,
                     "payload": {"path": path, "content": "x"}} for index, path in enumerate(stage_paths)]
        seq = 2 + len(stage_paths)
        effects.append({"stage": "review-consumption-commit", "kind": "git_commit", "seq": seq, "applied": True,
                        "commit_id": km, "payload": {"branch": "refs/heads/main"}})
        effects.append({"stage": "review-publication", "kind": "git_push", "seq": seq + 1, "applied": False,
                        "payload": {"commit": km, "branch": "main"}})
        record = {"invocation": invocation, "effects": effects,
                  "notes": {"publication_proof": {"metadata_commit": km, "registration_commit": registration}}}
        return mutation._planning_publication(root, effects, len(effects) - 1, record)

    def assert_accepted(self, found) -> None:
        self.assertIsInstance(found, mutation._Publication, getattr(found, "message", found))

    def assert_refused(self, found, *, unproven: bool = False) -> None:
        """Refused (``review_publication_invalid``); ``unproven``: by the positive P5 proof itself (OD-2)."""
        self.assertIsInstance(found, mutation._Refused)
        self.assertEqual("review_publication_invalid", found.reason)
        if unproven:
            self.assertIn("no P5-capable Run is proven", found.message)

    # OD2-T1 / OD2-T2: Consumption only - exactly as before, whatever (or whether any) Run records exist
    def test_od2_t1_a_legacy_v1_consumption_only_km_is_accepted_as_before(self) -> None:
        self.assert_accepted(self.verdict(V1, [CONSUMPTION], {CONSUMPTION: b"x\n"}))
        self.assert_accepted(self.verdict(V1, [CONSUMPTION], {CONSUMPTION: consumption()}, run_records()))

    def test_od2_t2_a_p4_only_consumption_only_km_is_accepted_as_before(self) -> None:
        self.assert_accepted(self.verdict(P4_FAMILY, [CONSUMPTION], {CONSUMPTION: b"x\n"}))
        self.assert_accepted(self.verdict(P4_FAMILY, [CONSUMPTION], {CONSUMPTION: consumption()},
                                          run_records(policy=p4.POLICY_ID)))

    # OD2-T3
    def test_od2_t3_a_p5_capable_run_with_its_exact_summary_and_consumption_is_accepted(self) -> None:
        self.assert_accepted(self.verdict(P4_FAMILY, [SUMMARY, CONSUMPTION], P5_KM, run_records()))
        self.assertIsNone(mutation_free_proof(self, P5_KM, run_records()))

    # OD2-T4
    def test_od2_t4_a_p4_only_run_with_a_summary_and_its_consumption_is_refused(self) -> None:
        km = {SUMMARY: summary(policy=p4.POLICY_ID), CONSUMPTION: consumption()}
        self.assert_refused(self.verdict(P4_FAMILY, [SUMMARY, CONSUMPTION], km, run_records(policy=p4.POLICY_ID)),
                            unproven=True)

    # OD2-T5
    def test_od2_t5_the_p4_family_marker_alone_never_proves_p5(self) -> None:
        for name, km, run in (
            ("no Review records at all", {SUMMARY: b"summary\n", CONSUMPTION: b"consumption\n"}, None),
            ("a P5 summary and Consumption, no Run", P5_KM, None),
        ):
            with self.subTest(name):
                self.assert_refused(self.verdict(P4_FAMILY, [SUMMARY, CONSUMPTION], km, run), unproven=True)

    # OD2-T6
    def test_od2_t6_a_wrong_run_or_an_unproven_stored_identity_is_refused(self) -> None:
        def unknown_policy(envelope: dict[str, Any]) -> None:
            envelope["policy_id"] = "review-v1-p9-policy-v1"

        def other_contract(envelope: dict[str, Any]) -> None:
            envelope[history.HISTORY_CONTRACT_KEY] = "review-v1-history-v0"

        def no_contract(envelope: dict[str, Any]) -> None:
            del envelope[history.HISTORY_CONTRACT_KEY]

        other_summary = paths.history_run_rel(OTHER_RUN)
        for name, stage, km, run in (
            ("summary of another Run than the consumed one", [other_summary, CONSUMPTION],
             {other_summary: summary(OTHER_RUN), CONSUMPTION: consumption()}, {**run_records(), **run_records(OTHER_RUN)}),
            ("Consumption of another Run than the summary's", [SUMMARY, CONSUMPTION],
             {SUMMARY: summary(), CONSUMPTION: consumption(OTHER_RUN)}, {**run_records(), **run_records(OTHER_RUN)}),
            ("missing TaskInput", [SUMMARY, CONSUMPTION], P5_KM, run_records(task_input_present=False)),
            ("unreadable policy", [SUMMARY, CONSUMPTION], P5_KM, run_records(edit=unknown_policy)),
            ("mismatching history contract", [SUMMARY, CONSUMPTION], P5_KM, run_records(edit=other_contract)),
            ("no history contract", [SUMMARY, CONSUMPTION], P5_KM, run_records(edit=no_contract)),
            ("generation 1 binds the P4 Effective Policy", [SUMMARY, CONSUMPTION], P5_KM,
             run_records(gate_policy=p4.POLICY_ID)),
            ("the summary is not the consumed one of this Consumption", [SUMMARY, CONSUMPTION],
             {SUMMARY: summary(consumption_id="rcs_01ARZ3NDEKTSV4RRFFQ69G5FAW"), CONSUMPTION: consumption()},
             run_records()),
            ("the summary is not canonical", [SUMMARY, CONSUMPTION], {SUMMARY: b"summary\n", CONSUMPTION: consumption()},
             run_records()),
            ("the Consumption is not canonical", [SUMMARY, CONSUMPTION], {SUMMARY: summary(), CONSUMPTION: b"x\n"},
             run_records()),
        ):
            with self.subTest(name):
                self.assert_refused(self.verdict(P4_FAMILY, stage, km, run), unproven=True)

    # OD2-T7: the earlier refusals still hold, a proven P5 Run beside them or not
    def test_od2_t7_the_shape_refusals_still_hold_beside_a_proven_p5_run(self) -> None:
        other = paths.history_run_rel(OTHER_RUN)
        for name, invocation, stage, km in (
            ("two summaries", P4_FAMILY, [SUMMARY, other, CONSUMPTION], {**P5_KM, other: summary(OTHER_RUN)}),
            ("a summary outside history/runs", P4_FAMILY, [paths.history_finding_rel("rfd_01ARZ3NDEKTSV4RRFFQ69G5FAV"),
                                                           CONSUMPTION],
             {paths.history_finding_rel("rfd_01ARZ3NDEKTSV4RRFFQ69G5FAV"): summary(), CONSUMPTION: consumption()}),
            ("a summary under a malformed ID", P4_FAMILY, [f"{paths.HISTORY_DIR}/{paths.HISTORY_RUNS}/not-an-id.yaml",
                                                          CONSUMPTION],
             {f"{paths.HISTORY_DIR}/{paths.HISTORY_RUNS}/not-an-id.yaml": summary(), CONSUMPTION: consumption()}),
            ("a summary under a non-Run ID", P4_FAMILY,
             [f"{paths.HISTORY_DIR}/{paths.HISTORY_RUNS}/rfd_01ARZ3NDEKTSV4RRFFQ69G5FAV.yaml", CONSUMPTION],
             {f"{paths.HISTORY_DIR}/{paths.HISTORY_RUNS}/rfd_01ARZ3NDEKTSV4RRFFQ69G5FAV.yaml": summary(),
              CONSUMPTION: consumption()}),
            ("a summary with no Consumption", P4_FAMILY, [SUMMARY], {SUMMARY: summary()}),
            ("Km changes a path outside what the stage wrote", P4_FAMILY, [SUMMARY, CONSUMPTION],
             {**P5_KM, "other.txt": b"other\n"}),
            ("a v1 stage carrying a summary", V1, [SUMMARY, CONSUMPTION], P5_KM),
        ):
            with self.subTest(name):
                self.assert_refused(self.verdict(invocation, stage, km, run_records()))
        self.assert_refused(self.verdict(V1, [CONSUMPTION], {CONSUMPTION: consumption(), SUMMARY: summary()},
                                         run_records()))


def mutation_free_proof(case: PlanningPushTests, km: dict[str, bytes], run: dict[str, bytes]) -> str | None:
    """The owner's positive P5 proof itself, over the same committed records (no mutation record involved)."""
    from workline import roadmap_review

    root = case.repo()
    case.write(root, {**run, **km})
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "records")
    return roadmap_review.p5_publication_problem(root, git(root, "rev-parse", "HEAD").strip(), SUMMARY, CONSUMPTION)


if __name__ == "__main__":
    unittest.main()
