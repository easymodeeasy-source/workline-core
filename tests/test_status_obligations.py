"""RB1-R10 (§9.7, §29.18, §29.30): Review status projects P4 blocking obligations, from P4's own reading of them.

Per Run, by the Review contract generation 1 binds explicitly:

* v1 (legacy) Work / planning Run: ``not_available_by_contract``, count ``None`` - exactly as before;
* P4 Run before its canonical adjudication (G1-G3): ``pending``, count ``None`` - never 0;
* P4 Run with a valid canonical adjudication: ``available`` with the count ``p4.blocking_obligations`` derives
  (every Problem the cycle's Repair Batch holds plus every unresolved HUMAN decision, a coverage gap once);
* P4 obligation records that do not read or contradict their bindings: the Run is ``invalid`` with the exact code,
  and no count is ever shown; an ``invalid`` Run's existing reason stays authoritative.

``pending_obligations`` aggregates the Runs that are neither v1 nor terminal, deterministically; consumed,
invalidated and set-aside Runs never contribute, a Run without adjudication makes it ``pending`` and a Run that does
not read makes it ``invalid``. No Finding, report, reviewer or request material reaches the output, status stays
read-only, and the JSON is deterministic with its schema and version unchanged.

Every record is built by the canonical P4 builders (``p4.discovery_request``, ``p4.task_input``,
``p4.report_record``, ``p4.adjudication_request``, ``p4.normalize_adjudication``, ``p4.adjudication``,
``p4.obligations_record``, ``p4.repair_batch``, ``p4.repair_request``, ``records.Receipt`` ...); a perturbation is
applied afterwards and only where a test says so. Run IDs sort the successor BEFORE its predecessor.
"""

from __future__ import annotations

import ast
import inspect
import json
import textwrap
from typing import Any, Callable

from test_review_authorization import consumption_record
from test_review_p4_strategy import CAUSAL, prior_cycle
from test_status_set_aside import (
    ABSENT, FOURTH, PREDECESSOR, RAW_REQUEST, SUCCESSOR, THIRD, WORK, aside, consumption_id_of, receipt_id_of,
)
from test_status_set_aside_classes import (
    PLANNING_KINDS, RAW_ACTOR, RAW_DECISION, ClassesCase, kinds, p4_task_id, planning_consumption,
)
from workline import status
from workline.errors import ValidationError
from workline.review import p4, paths, planning, records, serialize, work_review
from workline.review import status as review_status
from workline.review.store import ReviewStore

WORK_KIND = work_review.REVIEW_KIND
CONTRACTS = {WORK_KIND: work_review.P4_CONTRACT, **{kind: planning.P4_CONTRACT for kind in PLANNING_KINDS}}
STAGES = {
    WORK_KIND: work_review.AUTHORIZED_OPERATION_STAGE,
    **{kind: planning.KINDS[kind].authorized_operation_stage for kind in PLANNING_KINDS},
}
NA = {"status": "not_available_by_contract", "count": None}
PENDING = {"status": "pending", "count": None}
INVALID = {"status": "invalid", "count": None}

#: Material only the stored P4 records carry; none of it may reach the status output.
RAW_CLAIM = "RAW-CLAIM-TEXT-r10"
RAW_STATEMENT = "RAW-FINDING-STATEMENT-r10"
RAW_LABEL = "raw-label-r10"
RAW_REASON = "RAW-ADJUDICATION-REASON-r10"
RAW_ADJUDICATOR = "RAW-ADJUDICATOR-r10"
RAW_REPAIRER = "RAW-REPAIRER-r10"
RAW_PURPOSE = "RAW-REPAIR-PURPOSE-r10"
RAW_GAP = "RAW-NOT-INSPECTED-SURFACE-r10"
RAW_VALUE = "RAW-MALFORMED-VALUE-r10"
MATERIAL = (
    RAW_CLAIM, RAW_STATEMENT, RAW_LABEL, RAW_REASON, RAW_ADJUDICATOR, RAW_REPAIRER, RAW_PURPOSE, RAW_GAP, RAW_VALUE,
    RAW_REQUEST, RAW_ACTOR, RAW_DECISION.decision_id, "request_envelope", "set_aside_runs", "coverage_gaps",
    "repair_identity", "semantic_surface", p4.ADJUDICATION_INSTRUCTION, p4.DISCOVERY_INSTRUCTION,
)

#: The §12.4 answers each outcome is reached by.
FLAGS = {
    p4.OUTCOME_UNSUPPORTED: (False, False, False, False),
    p4.OUTCOME_HUMAN: (True, True, False, False),
    p4.OUTCOME_PROBLEM: (True, False, True, False),
    p4.OUTCOME_IMPROVEMENT: (True, False, False, True),
    p4.OUTCOME_DISMISSED: (True, False, False, False),
}

Decide = Callable[[str, int], p4.P4ClaimDisposition]


def decide(outcome: str, *, severity: str = "MID", repair: str = "a", disposition: str | None = None,
           relation: str = p4.RELATION_A_NEW, **links: Any) -> Decide:
    """The adjudicator's answer for one raw claim; Problem / Improvement Findings carry raw text and labels.

    Claims sharing ``repair`` (and category) are one Finding (§27.7 merge). A Finding's default disposition is
    the canonical one for its blocking (H-4): repair_required when it blocks, else retained_history_only.
    """
    def build(task_id: str, index: int) -> p4.P4ClaimDisposition:
        supported, human, fails, better = FLAGS[outcome]
        fields: dict[str, Any] = {}
        if outcome in (p4.OUTCOME_PROBLEM, p4.OUTCOME_IMPROVEMENT):
            blocking = p4.is_blocking(outcome, severity, relation)
            fields = dict(
                severity=severity, statement=RAW_STATEMENT, semantic_surface=f"{RAW_LABEL}-surface-{repair}",
                repair_identity=f"{RAW_LABEL}-repair-{repair}",
                disposition=disposition or (p4.DISPOSITION_REPAIR_REQUIRED if blocking
                                            else p4.DISPOSITION_RETAINED_HISTORY_ONLY),
            )
        return p4.P4ClaimDisposition(
            task_id=task_id, claim_index=index, supported=supported, requirement_decision_required=human,
            fails_requirement=fails, better_alternative=better, outcome=outcome, reason=RAW_REASON, relation=relation,
            **fields, **links,
        )
    return build


def suffix(run_id: str) -> str:
    return run_id.split("_", 1)[1]


class ObligationsCase(ClassesCase):
    """P4 Runs G1 .. G6 on disk, each record from its canonical builder."""

    def gate(self, run_id: str, gates: list[dict], **changes: Any) -> dict:
        """The next generation: the previous one with ``changes``, chained by digest (the owners' ``replace``)."""
        previous = gates[-1]
        record = dict(previous, generation=previous["generation"] + 1, previous_generation=previous["generation"],
                      previous_digest=serialize.digest(previous), **changes)
        self.put(paths.gate_rel(run_id, record["generation"]), record)
        gates.append(record)
        return record

    def p4_records(
        self, run_id: str, *, kind: str = WORK_KIND, decided: tuple[Decide, ...] = (),
        gaps: tuple[tuple[str, str], ...] = (), objective_holds: bool = True, generations: int = 4,
        fifth: str | None = None, sixth: bool = False, consumed: bool = False, prior: Any = None,
        **request: Any,
    ) -> dict[str, Any]:
        """A P4 Run of ``kind`` up to ``generations`` (``fifth`` = ``seal`` | ``repair`` from G5 on).

        ``decided`` answers one raw claim each (all in the first discovery report); ``gaps`` are that report's
        not-inspected surfaces with their adjudicated resolution. ``request`` goes to the G1 builder.
        """
        contract = CONTRACTS[kind]
        target, operation = self.identity(kind)
        self.p4_run(run_id, kind=kind, **request)
        review = ReviewStore(self.store)
        gates = [review.read_gate(run_id, 1).to_record()]
        built: dict[str, Any] = {"gates": gates}
        if generations == 1:
            return built
        discovery = list(gates[0]["accepted_tasks"])
        reports: list[tuple[str, str, dict]] = []
        for index, task in enumerate(discovery):
            claims = tuple(p4.P4Claim("HIGH", "claim", RAW_CLAIM) for _ in decided) if index == 0 else ()
            not_inspected = tuple(surface for surface, _ in gaps) if index == 0 else ()
            returned = p4.P4DiscoveryReport(
                str(task["task_id"]), str(task["reviewer_identity"]), str(task["reviewer_version"]), "completed",
                claims, p4.P4Coverage(("result",), ("behaviour",), (), not_inspected),
            )
            record = p4.report_record(returned, task, review_kind=kind, review_contract=contract)
            digest = serialize.digest(record)
            self.put(paths.report_rel(digest), record)
            reports.append((str(task["task_id"]), digest, record))
        settled = [{"task_id": task_id, "status": p4.settled_status(record), "result_digest": digest,
                    "settled_generation": 2} for task_id, digest, record in reports]
        self.gate(run_id, gates, settled_tasks=settled,
                  raw_report_set_digest=serialize.digest(p4.report_set_record(settled)))
        if generations == 2:
            return built
        adjudication_task = p4_task_id(run_id, 7)
        request_record = p4.adjudication_request(
            review_contract=contract, review_kind=kind, review_run_id=run_id, candidate_hash="a" * 64,
            candidate_generation=1, review_context_hash="b" * 64,
            requirement=p4.requirement_record(kind, {"note": RAW_REQUEST}),
            reports=[{"task_id": task_id, "result_digest": digest} for task_id, digest, _ in reports],
            prior=p4.NO_PRIOR if prior is None else prior.prior_record(), evidence_ids=[],
        )
        task_input = p4.task_input(
            task_id=adjudication_task, task_slot=p4.SLOT_ADJUDICATOR, task_kind=p4.TASK_KIND_ADJUDICATION,
            actor_identity=RAW_ADJUDICATOR, actor_version="1", envelope=request_record, candidate_hash="a" * 64,
            candidate_material_digest="9" * 64, review_context_hash="b" * 64,
            accepted_generation=p4.ADJUDICATION_ACCEPT_GENERATION,
        )
        self.put(paths.task_input_rel(adjudication_task), task_input.to_record())
        descriptor = p4.accepted_descriptor(task_input)
        third = self.gate(run_id, gates, accepted_tasks=gates[-1]["accepted_tasks"] + [descriptor])
        if generations == 3:
            return built
        first_report = reports[0][0]
        returned_adjudication = p4.P4AdjudicationReturn(
            task_id=adjudication_task, adjudicator_identity=RAW_ADJUDICATOR, adjudicator_version="1",
            objective_holds=objective_holds,
            dispositions=tuple(build(first_report, index) for index, build in enumerate(decided)),
            coverage_gaps=tuple(
                p4.P4CoverageGap(first_report, surface, resolution,
                                 ("evidence-r10",) if resolution == p4.GAP_COVERED else ())
                for surface, resolution in gaps
            ),
            repair_purpose=RAW_PURPOSE,
        )
        normalized = p4.normalize_adjudication(returned_adjudication, descriptor, reports, prior)
        finding_ids = [f"rfd_{suffix(run_id)[:22]}{suffix(run_id)[-2:]}{index:02d}"
                       for index in range(10, 10 + len(normalized.drafts))]
        adjudication = p4.adjudication(
            normalized, finding_ids, review_run_id=run_id,
            gate_record=records.GateGeneration.from_record(third, "generation 3"),
            candidate_generation=1 if prior is None else 2, review_contract=contract, descriptor=descriptor,
            reports=reports, prior=prior,
        )
        record = adjudication.to_record()
        digest = serialize.digest(record)
        self.put(paths.adjudication_rel(run_id), record)
        fourth = self.gate(
            run_id, gates, adjudication_digest=digest,
            obligation_digest=serialize.digest(p4.obligations_record(adjudication)),
            settled_tasks=third["settled_tasks"] + [{"task_id": adjudication_task, "status": records.TASK_SETTLED_OK,
                                                     "result_digest": digest, "settled_generation": 4}],
        )
        built.update(adjudication=adjudication, digest=digest)
        if fifth == "seal":
            receipt_id = receipt_id_of(run_id)
            self.put(paths.receipt_rel(receipt_id), records.Receipt(
                receipt_id=receipt_id, review_run_id=run_id, review_generation=p4.SEAL_GENERATION, review_kind=kind,
                target_identity=target, operation_identity=operation, authorized_candidate_hash="a" * 64,
                review_context_hash="b" * 64, effective_policy_hash=p4.policy_hash(),
                coverage_hash=fourth["coverage_digest"], adjudication_hash=fourth["adjudication_digest"],
                obligation_digest=fourth["obligation_digest"], unresolved_obligations=0,
                authorized_operation_stage=STAGES[kind],
            ).to_record())
            self.gate(run_id, gates, status=records.GATE_STATUS_SEALED, receipt_id=receipt_id,
                      authorized_operation_stage=STAGES[kind])
            if sixth:
                self.put(paths.supersession_rel(receipt_id), records.Supersession(
                    receipt_id, run_id, p4.INVALIDATION_GENERATION, p4.INVALIDATION_STALE_RECEIPT,
                ).to_record())
                self.gate(run_id, gates, status=records.GATE_STATUS_OPEN, receipt_id=None,
                          authorized_operation_stage=None, evidence_digest=serialize.digest(
                              p4.invalidation_evidence_record(receipt_id, p4.INVALIDATION_STALE_RECEIPT)))
            if consumed:
                if kind == WORK_KIND:
                    consumption = consumption_record(
                        consumption_id=consumption_id_of(run_id), receipt_id=receipt_id, review_run_id=run_id,
                        review_generation=p4.SEAL_GENERATION, review_kind=kind, target_identity=target,
                        operation_identity=operation,
                    )
                else:
                    consumption = dict(planning_consumption(run_id, kind, target, operation),
                                       review_generation=p4.SEAL_GENERATION)
                records.consumption_from_record(consumption, "the fixture")  # its own reader accepts it
                self.put(paths.consumption_rel(consumption_id_of(run_id)), consumption)
        elif fifth == "repair":
            batch_id = "rrb_" + suffix(run_id)
            batch = p4.repair_batch(adjudication, digest, repair_batch_id=batch_id, allowed_result_surface=["out.txt"])
            self.put(paths.repair_batch_rel(batch_id), batch.to_record())
            repair_task = p4_task_id(run_id, 8)
            repair_input = p4.task_input(
                task_id=repair_task, task_slot=p4.SLOT_REPAIR, task_kind=p4.TASK_KIND_REPAIR,
                actor_identity=RAW_REPAIRER, actor_version="1", envelope=p4.repair_request(
                    review_contract=contract, review_kind=kind, review_run_id=run_id, candidate_hash="a" * 64,
                    candidate_generation=1, requirement=p4.requirement_record(kind, {"note": RAW_REQUEST}),
                    repair_batch_id=batch_id, repair_batch_digest=serialize.digest(batch.to_record()),
                    allowed_result_surface=batch.allowed_result_surface, strategy=batch.strategy,
                    evidence_constraints=(),
                ), candidate_hash="a" * 64, candidate_material_digest="9" * 64, review_context_hash="b" * 64,
                accepted_generation=p4.REPAIR_ACCEPT_GENERATION,
            )
            self.put(paths.task_input_rel(repair_task), repair_input.to_record())
            fifth_record = self.gate(run_id, gates,
                                     accepted_tasks=fourth["accepted_tasks"] + [p4.accepted_descriptor(repair_input)])
            built.update(batch=batch)
            if sixth:
                self.gate(run_id, gates, settled_tasks=fifth_record["settled_tasks"] + [{
                    "task_id": repair_task, "status": records.TASK_SETTLED_OK, "result_digest": "5" * 64,
                    "settled_generation": p4.REPAIR_SETTLE_GENERATION,
                }])
        return built

    def rewrite(self, run_id: str, record: dict, *, gates: list[dict] | None = None) -> None:
        """Store ``record`` as the Run's adjudication; with ``gates``, generation 4 re-binds it (digests recomputed)."""
        self.put(paths.adjudication_rel(run_id), record)
        if gates is not None:
            found = records.P4Adjudication.from_record(serialize.canonical_data(record), "the perturbed adjudication")
            fourth = dict(gates[3], adjudication_digest=serialize.digest(record),
                          obligation_digest=serialize.digest(p4.obligations_record(found)))
            self.put(paths.gate_rel(run_id, 4), fourth)

    def review(self) -> dict[str, Any]:
        found = review_status.review_status(self.store)
        self.assertEqual((found["namespace"]["status"], found["runs"]["status"]), ("present", "available"), found)
        return found

    def runs(self) -> dict[str, dict]:
        return {entry["review_run_id"]: entry for entry in self.review()["runs"]["entries"]}

    def obligations(self, run_id: str) -> dict:
        return self.runs()[run_id]["blocking_obligations"]

    def summary(self) -> dict:
        return self.review()["pending_obligations"]


# --------------------------------------------------------------------------- OB-T1 .. OB-T8: one Run


class PerRunTests(ObligationsCase):
    def test_ob_t1_legacy_runs_stay_not_available_by_contract(self) -> None:
        """OB-T1: v1 Work (v1 / v2 request, open / sealed / consumed) and v1 planning Runs: unchanged."""
        self.work_run(PREDECESSOR, generations=3, consumed=True)
        self.work_run(THIRD, generations=3)
        self.work_run(SUCCESSOR, set_aside=aside((FOURTH, "review_context_changed")))
        self.work_run(FOURTH, generations=1)
        self.planning_v1("rr_01ARZ3NDEKTSV4RRFFQ69G5FAQ", set_aside=[])
        self.planning_v1("rr_01ARZ3NDEKTSV4RRFFQ69G5FAR", set_aside=[], kind=planning.KIND_PHASE_ENTRY,
                         generations=3)
        review = self.review()
        entries = review["runs"]["entries"]
        self.assertEqual(len(entries), 6)
        for entry in entries:
            with self.subTest(run=entry["review_run_id"], state=entry["state"]):
                self.assertEqual(entry["blocking_obligations"], NA)
        self.assertEqual(review["pending_obligations"], {"status": "not_available_by_contract"})
        self.assertEqual({entry["state"] for entry in entries}, {"consumed", "sealed", "open", "set_aside"})

    def test_ob_t2_p4_before_its_adjudication_is_pending_never_zero(self) -> None:
        """OB-T2: G1 .. G3 of every P4 kind - the contract is recognized, the count is not reported, not even 0."""
        for kind in kinds():
            for generations in (1, 2, 3):
                with self.subTest(kind=kind, generations=generations):
                    self.reset_review()
                    self.p4_records(SUCCESSOR, kind=kind, generations=generations,
                                    decided=(decide(p4.OUTCOME_PROBLEM, severity="HIGH"),))
                    entry = self.runs()[SUCCESSOR]
                    self.assertEqual((entry["state"], entry["latest_generation"], entry["reason"]),
                                     ("open", generations, None))
                    self.assertEqual(entry["blocking_obligations"], PENDING)
                    self.assertEqual(self.summary(), {"status": "pending", "count": None,
                                                      "review_run_ids": [SUCCESSOR]})
        with self.subTest("an adjudication stored before generation 4 binds it is not read"):
            self.reset_review()
            self.p4_records(PREDECESSOR, decided=(decide(p4.OUTCOME_PROBLEM, severity="HIGH"),))
            self.p4_records(SUCCESSOR, generations=3, decided=(decide(p4.OUTCOME_PROBLEM, severity="HIGH"),))
            self.put(paths.adjudication_rel(SUCCESSOR),
                     ReviewStore(self.store).read_adjudication(PREDECESSOR).to_record())
            self.assertEqual(self.obligations(SUCCESSOR), PENDING)

    def test_ob_t3_authorization_ready_is_zero_and_a_seal_adds_zero(self) -> None:
        """OB-T3: AUTHORIZATION_READY at G4, sealed at G5: ``available`` 0."""
        decided = (decide(p4.OUTCOME_UNSUPPORTED), decide(p4.OUTCOME_DISMISSED),
                   decide(p4.OUTCOME_PROBLEM, severity="LOW", repair="low"),
                   decide(p4.OUTCOME_IMPROVEMENT, severity="HIGH", repair="better"))
        for kind in kinds():
            for fifth in (None, "seal"):
                with self.subTest(kind=kind, fifth=fifth):
                    self.reset_review()
                    built = self.p4_records(SUCCESSOR, kind=kind, decided=decided, fifth=fifth,
                                            gaps=((RAW_GAP, p4.GAP_NOT_APPLICABLE),))
                    self.assertEqual(built["adjudication"].outcome, p4.AUTHORIZATION_READY)
                    entry = self.runs()[SUCCESSOR]
                    self.assertEqual(entry["state"], "open" if fifth is None else "sealed")
                    self.assertEqual(entry["blocking_obligations"], {"status": "available", "count": 0})
                    self.assertEqual(self.summary(), {"status": "available", "count": 0,
                                                      "review_run_ids": [SUCCESSOR]})

    def test_ob_t4_one_blocking_problem_is_one(self) -> None:
        """OB-T4: one blocking Problem - at G4, while its repair is accepted (G5) and settled (G6)."""
        for kind in kinds():
            for fifth, sixth in ((None, False), ("repair", False), ("repair", True)):
                with self.subTest(kind=kind, fifth=fifth, sixth=sixth):
                    self.reset_review()
                    built = self.p4_records(SUCCESSOR, kind=kind, fifth=fifth, sixth=sixth,
                                            decided=(decide(p4.OUTCOME_PROBLEM, severity="HIGH"),))
                    self.assertEqual(built["adjudication"].outcome, p4.REPAIR_REQUIRED)
                    entry = self.runs()[SUCCESSOR]
                    self.assertEqual((entry["state"], entry["reason"]), ("open", None))
                    self.assertEqual(entry["blocking_obligations"], {"status": "available", "count": 1})
                    self.assertEqual(self.summary(), {"status": "available", "count": 1,
                                                      "review_run_ids": [SUCCESSOR]})

    def test_ob_t5_several_blocking_problems_are_counted_as_findings_not_claims(self) -> None:
        """OB-T5: HIGH, MID and two claims merged into one MID Finding: 3 Findings from 4 claims; LOW adds none."""
        built = self.p4_records(SUCCESSOR, decided=(
            decide(p4.OUTCOME_PROBLEM, severity="HIGH", repair="a"),
            decide(p4.OUTCOME_PROBLEM, severity="MID", repair="b"),
            decide(p4.OUTCOME_PROBLEM, severity="MID", repair="c"),
            decide(p4.OUTCOME_PROBLEM, severity="MID", repair="c"),
            decide(p4.OUTCOME_PROBLEM, severity="LOW", repair="d"),
        ))
        found = built["adjudication"]
        self.assertEqual((len(found.entries), len(found.findings)), (5, 4))
        self.assertEqual((found.obligations["problem_high"], found.obligations["problem_mid"]), (1, 2))
        self.assertEqual(self.obligations(SUCCESSOR), {"status": "available", "count": 3})
        self.assertEqual(self.summary()["count"], 3)

    def test_ob_t6_an_unresolved_human_decision_counts_exactly_once(self) -> None:
        """OB-T6: HUMAN_WAIT - a HUMAN claim, a HUMAN / targeted-check coverage gap, never a gap twice."""
        cases = (
            ("one HUMAN claim", (decide(p4.OUTCOME_HUMAN),), (), 1),
            ("a HUMAN coverage gap", (), ((RAW_GAP, p4.GAP_HUMAN),), 1),
            ("a targeted-check coverage gap", (), ((RAW_GAP, p4.GAP_TARGETED_CHECK),), 1),
            ("a HUMAN claim and a HUMAN coverage gap", (decide(p4.OUTCOME_HUMAN),), ((RAW_GAP, p4.GAP_HUMAN),), 2),
            ("a HUMAN claim, a blocking Problem and a resolved gap",
             (decide(p4.OUTCOME_HUMAN), decide(p4.OUTCOME_PROBLEM, severity="HIGH")),
             ((RAW_GAP, p4.GAP_COVERED),), 2),
        )
        for kind in kinds():
            for name, decided, gaps, expected in cases:
                with self.subTest(kind=kind, case=name):
                    self.reset_review()
                    found = self.p4_records(SUCCESSOR, kind=kind, decided=decided, gaps=gaps)["adjudication"]
                    self.assertEqual(found.outcome, p4.HUMAN_WAIT)
                    entry = self.runs()[SUCCESSOR]
                    self.assertEqual((entry["state"], entry["latest_generation"]), ("open", 4))
                    self.assertEqual(entry["blocking_obligations"], {"status": "available", "count": expected})
                    if gaps and gaps[0][1] != p4.GAP_COVERED:
                        # the summary names the gap twice (human and coverage_unresolved): the trap is real
                        self.assertEqual(found.obligations["human"] + found.obligations["coverage_unresolved"],
                                         expected + 1)

    def test_ob_t7_low_and_improvement_never_add(self) -> None:
        """OB-T7: one blocking Problem stays 1 beside LOW history / future work / no action and every Improvement."""
        base = (decide(p4.OUTCOME_PROBLEM, severity="MID", repair="blocking"),)
        others = (
            decide(p4.OUTCOME_PROBLEM, severity="LOW", repair="history"),
            decide(p4.OUTCOME_PROBLEM, severity="LOW", repair="future",
                   disposition=p4.DISPOSITION_FUTURE_WORK_CANDIDATE),
            decide(p4.OUTCOME_PROBLEM, severity="LOW", repair="none", disposition=p4.DISPOSITION_NO_ACTION),
            decide(p4.OUTCOME_IMPROVEMENT, severity="HIGH", repair="i-high"),
            decide(p4.OUTCOME_IMPROVEMENT, severity="MID", repair="i-mid",
                   disposition=p4.DISPOSITION_FUTURE_WORK_CANDIDATE),
            decide(p4.OUTCOME_IMPROVEMENT, severity="LOW", repair="i-low", disposition=p4.DISPOSITION_NO_ACTION),
        )
        for decided, expected in ((base, 1), (base + others, 1), (others, 0)):
            with self.subTest(claims=len(decided)):
                self.reset_review()
                found = self.p4_records(SUCCESSOR, decided=decided)["adjudication"]
                self.assertEqual(len(found.findings), len(decided))
                self.assertEqual(self.obligations(SUCCESSOR), {"status": "available", "count": expected})

    def test_ob_t8_current_cycle_repair_obligations_follow_p4_exactly(self) -> None:
        """OB-T8: a LOW deliberately repaired this cycle and a repair-induced LOW block as P4 makes them block.

        P4 treats a deliberate current-cycle repair as blocking authorization: the outcome is REPAIR_REQUIRED and
        the one Repair Batch holds it. The count is exactly the canonical Repair Batch's Findings plus HUMAN.
        """
        deliberate = decide(p4.OUTCOME_PROBLEM, severity="LOW", repair="deliberate",
                            disposition=p4.DISPOSITION_REPAIRED_CURRENT_CYCLE)
        cases = (
            ("a deliberate LOW repair alone", (deliberate,), 1),
            ("a deliberate LOW repair beside a HIGH", (deliberate, decide(p4.OUTCOME_PROBLEM, severity="HIGH")), 2),
            ("a deliberate LOW repair beside a LOW kept as history",
             (deliberate, decide(p4.OUTCOME_PROBLEM, severity="LOW", repair="history")), 1),
        )
        for name, decided, expected in cases:
            with self.subTest(case=name):
                self.reset_review()
                built = self.p4_records(SUCCESSOR, decided=decided, fifth="repair")
                found = built["adjudication"]
                self.assertEqual(found.outcome, p4.REPAIR_REQUIRED)
                self.assertEqual(found.obligations["problem_high"] + found.obligations["problem_mid"], expected - 1)
                self.assertEqual(len(built["batch"].finding_ids), expected, "the canonical Repair Batch holds them")
                self.assertEqual(self.obligations(SUCCESSOR), {"status": "available", "count": expected})
        with self.subTest(case="a repair-induced LOW Problem in the next cycle (P4's reader on the stored records)"):
            self.reset_review()
            built = self.p4_records(SUCCESSOR, prior=prior_cycle(), decided=(
                decide(p4.OUTCOME_PROBLEM, severity="LOW", relation=p4.RELATION_C_REPAIR_INDUCED,
                       linked_repair_batch_ids=(prior_cycle().repair_batch.repair_batch_id,),
                       causal_evidence_digest=CAUSAL),
                decide(p4.OUTCOME_PROBLEM, severity="LOW", repair="history"),
            ))
            finding = built["adjudication"].findings[0]
            self.assertEqual((finding["relation"], finding["severity"], finding["blocking"]),
                             (p4.RELATION_C_REPAIR_INDUCED, "LOW", True))
            review = ReviewStore(self.store)
            self.assertEqual(p4.blocking_obligations(review, SUCCESSOR, review.gate_chain(SUCCESSOR)), 1)
        with self.subTest(case="count 0 exactly when the outcome is AUTHORIZATION_READY"):
            sweep = (
                ((decide(p4.OUTCOME_DISMISSED),), p4.AUTHORIZATION_READY),
                ((deliberate,), p4.REPAIR_REQUIRED),
                ((decide(p4.OUTCOME_HUMAN), deliberate), p4.HUMAN_WAIT),
                ((decide(p4.OUTCOME_IMPROVEMENT, severity="HIGH"),), p4.AUTHORIZATION_READY),
            )
            for decided, outcome in sweep:
                self.reset_review()
                found = self.p4_records(SUCCESSOR, decided=decided)["adjudication"]
                self.assertEqual(found.outcome, outcome)
                count = self.obligations(SUCCESSOR)["count"]
                self.assertEqual(count == 0, outcome == p4.AUTHORIZATION_READY)
                included, _ = p4.repair_finding_ids(found)
                self.assertEqual(count, len(included) + found.obligations["human"])


# --------------------------------------------------------------------------- OB-T9: fail closed


class FailClosedTests(ObligationsCase):
    def assert_invalid(self, code: str, *, run_id: str = SUCCESSOR, message: str | None = None) -> dict:
        entry = self.runs()[run_id]
        self.assertEqual(entry["state"], "invalid", entry)
        self.assertEqual(entry["reason"]["code"], code, entry["reason"])
        self.assertIn(run_id, entry["reason"]["message"])
        if message is not None:
            self.assertIn(message, entry["reason"]["message"])
        self.assertEqual(entry["blocking_obligations"], INVALID)
        self.assertEqual(self.summary(), {"status": "invalid", "count": None, "review_run_ids": [run_id]})
        for leaked in MATERIAL:
            self.assertNotIn(leaked, json.dumps(entry))
        return entry

    def blocking(self, **options: Any) -> dict[str, Any]:
        return self.p4_records(SUCCESSOR, decided=(decide(p4.OUTCOME_PROBLEM, severity="HIGH"),), **options)

    def test_ob_t9_malformed_or_contradictory_obligation_material(self) -> None:
        """OB-T9: no count is guessed; the Run is ``invalid`` with the exact code; nothing raw is quoted."""
        def missing(built: dict) -> None:
            (self.store.root / paths.adjudication_rel(SUCCESSOR)).unlink()

        def another_adjudication(built: dict) -> None:
            record = built["adjudication"].to_record()
            record["findings"][0]["statement"] = "another statement"
            self.rewrite(SUCCESSOR, record)

        def other_obligations(built: dict) -> None:
            gates = built["gates"]
            self.put(paths.gate_rel(SUCCESSOR, 4),
                     dict(gates[3], obligation_digest=serialize.digest(p4.obligations_record(None))))

        def inconsistent(built: dict) -> None:
            record = built["adjudication"].to_record()
            record["findings"][0].update(blocking=False, disposition=p4.DISPOSITION_RETAINED_HISTORY_ONLY)
            self.rewrite(SUCCESSOR, record, gates=built["gates"])

        def another_candidate(built: dict) -> None:
            record = dict(built["adjudication"].to_record(), candidate_hash="c" * 64)
            self.rewrite(SUCCESSOR, record, gates=built["gates"])

        def raw_value(built: dict) -> None:
            record = built["adjudication"].to_record()
            record["findings"][0]["severity"] = RAW_VALUE
            self.rewrite(SUCCESSOR, record)

        def noncanonical(built: dict) -> None:
            target = self.store.root / paths.adjudication_rel(SUCCESSOR)
            target.write_bytes(target.read_bytes() + b"\n\n")

        def not_a_p4_chain(built: dict) -> None:
            gates = built["gates"]
            self.put(paths.gate_rel(SUCCESSOR, 4), dict(gates[3], settled_tasks=gates[2]["settled_tasks"]))

        cases: tuple[tuple[str, dict, Callable[[dict], None] | None, str, str], ...] = (
            ("the bound adjudication is missing", {}, missing, "review_record_missing", "does not read"),
            ("generation 4 binds another adjudication", {}, another_adjudication, "review_record_conflict",
             "does not bind its stored adjudication"),
            ("generation 4 binds other obligations", {}, other_obligations, "review_record_conflict",
             "does not bind its adjudication's obligations"),
            ("an adjudication inconsistent in itself", {}, inconsistent, "review_record_invalid",
             "not consistent in itself"),
            ("an adjudication of another Candidate", {}, another_candidate, "review_record_conflict",
             "not of this Run's Candidate"),
            ("a malformed adjudication value", {}, raw_value, "review_record_invalid", "does not read"),
            ("an adjudication not stored canonically", {}, noncanonical, None, "does not read"),
            ("a seal after REPAIR_REQUIRED", {"fifth": "seal"}, None, "review_record_conflict",
             "generation 5 does not follow"),
            ("a generation after 4 binding other obligations", {"fifth": "repair"}, "later", "review_record_conflict",
             "a later generation binds other obligations"),
            ("a generation 4 that does not settle the adjudication", {}, not_a_p4_chain, "review_gate_chain",
             "not a P4 chain"),
        )
        for name, options, perturb, code, message in cases:
            with self.subTest(case=name):
                self.reset_review()
                built = self.blocking(**options)
                if perturb == "later":
                    gates = built["gates"]
                    self.put(paths.gate_rel(SUCCESSOR, 5), dict(gates[4], obligation_digest="0" * 64))
                elif perturb is not None:
                    perturb(built)
                if code is None:  # the stored-record reader's own code: read from that reader itself
                    with self.assertRaises(ValidationError) as raised:
                        ReviewStore(self.store).read_adjudication(SUCCESSOR)
                    code = raised.exception.code
                    self.assertTrue(code.startswith("review_record_"), code)
                entry = self.assert_invalid(code, message=message)
                self.assertNotIn(RAW_VALUE, json.dumps(entry))
        with self.subTest(case="a HUMAN_WAIT sealed at G5"):
            self.reset_review()
            self.p4_records(SUCCESSOR, decided=(decide(p4.OUTCOME_HUMAN),), fifth="seal")
            self.assert_invalid("review_record_conflict", message="generation 5 does not follow")
        with self.subTest(case="an Improvement disposed as a current-cycle repair: count and outcome disagree"):
            self.reset_review()
            built = self.p4_records(SUCCESSOR, decided=(decide(p4.OUTCOME_IMPROVEMENT),))
            record = built["adjudication"].to_record()
            record["findings"][0]["disposition"] = p4.DISPOSITION_REPAIRED_CURRENT_CYCLE
            record.update(outcome=p4.REPAIR_REQUIRED, repair_purpose="repair it")
            found = records.P4Adjudication.from_record(serialize.canonical_data(record), "the perturbed adjudication")
            self.assertEqual(p4.adjudication_problems(found), [], "P4's own consistency check does not see it")
            self.rewrite(SUCCESSOR, record, gates=built["gates"])
            self.assert_invalid("review_record_invalid", message="obligations and its outcome disagree")

    def test_ob_t9_an_existing_invalid_reason_stays_authoritative(self) -> None:
        """OB-T9: a Run already ``invalid`` keeps its own reason; obligations only say ``invalid``, never a count."""
        with self.subTest(case="a Receipt that does not read, beside a broken adjudication"):
            self.p4_records(SUCCESSOR, decided=(decide(p4.OUTCOME_DISMISSED),), fifth="seal")
            (self.store.root / paths.receipt_rel(receipt_id_of(SUCCESSOR))).write_bytes(b"schema: nonsense\n")
            (self.store.root / paths.adjudication_rel(SUCCESSOR)).unlink()
            entry = self.runs()[SUCCESSOR]
            self.assertEqual((entry["state"], entry["receipt"]["status"]), ("invalid", "invalid"))
            self.assertNotIn("blocking obligations", entry["reason"]["message"])
            self.assertEqual(entry["blocking_obligations"], INVALID)
        with self.subTest(case="a valid count under an invalid set-aside linkage"):
            self.reset_review()
            self.p4_records(SUCCESSOR, decided=(decide(p4.OUTCOME_PROBLEM, severity="HIGH"),),
                            set_aside=aside((ABSENT, "set_aside")))
            entry = self.runs()[SUCCESSOR]
            self.assertEqual((entry["state"], entry["reason"]["code"]), ("invalid", "review_record_conflict"))
            self.assertIn(ABSENT, entry["reason"]["message"])
            self.assertEqual(entry["blocking_obligations"], INVALID)
            self.assertEqual(self.summary(), {"status": "invalid", "count": None, "review_run_ids": [SUCCESSOR]})
        with self.subTest(case="a P4 Run whose chain does not read: its generation 1 still shows the contract"):
            self.reset_review()
            built = self.p4_records(SUCCESSOR, decided=(decide(p4.OUTCOME_PROBLEM, severity="HIGH"),))
            self.p4_records(PREDECESSOR, decided=(decide(p4.OUTCOME_DISMISSED),))
            self.put(paths.gate_rel(SUCCESSOR, 3), dict(built["gates"][2], previous_digest="0" * 64))
            entries = self.runs()
            self.assertEqual((entries[SUCCESSOR]["state"], entries[SUCCESSOR]["reason"]["code"]),
                             ("invalid", "review_gate_chain"))
            self.assertEqual(entries[SUCCESSOR]["blocking_obligations"], INVALID)
            self.assertEqual(entries[PREDECESSOR]["blocking_obligations"], {"status": "available", "count": 0})
            self.assertEqual(self.summary(), {"status": "invalid", "count": None,
                                              "review_run_ids": [SUCCESSOR, PREDECESSOR]})
        with self.subTest(case="a legacy Run whose chain does not read stays not_available_by_contract"):
            self.reset_review()
            self.work_run(SUCCESSOR, generations=2)
            first = ReviewStore(self.store).read_gate(SUCCESSOR, 1).to_record()
            self.put(paths.gate_rel(SUCCESSOR, 2), dict(first, generation=2, previous_generation=1,
                                                        previous_digest="0" * 64))
            entry = self.runs()[SUCCESSOR]
            self.assertEqual((entry["state"], entry["blocking_obligations"]), ("invalid", NA))
            self.assertEqual(self.summary(), {"status": "not_available_by_contract"})


# --------------------------------------------------------------------------- OB-T10 / OB-T11: the summary


class SummaryTests(ObligationsCase):
    def test_ob_t10_terminal_runs_never_contribute(self) -> None:
        """OB-T10: consumed, invalidated and set-aside Runs show their history and add nothing; v1 adds nothing."""
        consumed, invalidated = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAQ", "rr_01ARZ3NDEKTSV4RRFFQ69G5FAR"
        legacy = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAS"
        # PREDECESSOR (2 blocking) and THIRD (no adjudication yet) are set aside by SUCCESSOR's request
        self.p4_records(PREDECESSOR, decided=(decide(p4.OUTCOME_PROBLEM, severity="HIGH", repair="a"),
                                              decide(p4.OUTCOME_PROBLEM, severity="MID", repair="b")))
        self.p4_records(THIRD, generations=2)
        self.p4_records(SUCCESSOR, decided=(decide(p4.OUTCOME_HUMAN),),
                        set_aside=aside((PREDECESSOR, planning.STALE_CONTEXT), (THIRD, planning.STALE_CONTEXT)))
        self.p4_records(consumed, decided=(decide(p4.OUTCOME_DISMISSED),), fifth="seal", consumed=True)
        self.p4_records(invalidated, decided=(decide(p4.OUTCOME_DISMISSED),), fifth="seal", sixth=True)
        self.work_run(legacy, generations=1)
        entries = self.runs()
        self.assertEqual(
            {run_id: (entry["state"], entry["blocking_obligations"]) for run_id, entry in entries.items()},
            {
                PREDECESSOR: ("set_aside", {"status": "available", "count": 2}),
                THIRD: ("set_aside", PENDING),
                SUCCESSOR: ("open", {"status": "available", "count": 1}),
                consumed: ("consumed", {"status": "available", "count": 0}),
                invalidated: ("invalidated", {"status": "available", "count": 0}),
                legacy: ("open", NA),
            },
        )
        self.assertEqual(self.summary(), {"status": "available", "count": 1, "review_run_ids": [SUCCESSOR]})
        with self.subTest(case="only terminal P4 Runs: nothing current, so 0 - none is pending"):
            self.reset_review()
            self.p4_records(consumed, decided=(decide(p4.OUTCOME_DISMISSED),), fifth="seal", consumed=True)
            self.p4_records(invalidated, decided=(decide(p4.OUTCOME_DISMISSED),), fifth="seal", sixth=True)
            self.assertEqual(self.summary(), {"status": "available", "count": 0, "review_run_ids": []})
        with self.subTest(case="a Run waiting at G4 HUMAN_WAIT set aside by a Human decision's successor"):
            self.reset_review()
            self.p4_records(PREDECESSOR, decided=(decide(p4.OUTCOME_HUMAN),))
            self.p4_records(SUCCESSOR, generations=1, decision=RAW_DECISION,
                            set_aside=aside((PREDECESSOR, p4.SET_ASIDE_HUMAN_DECISION)))
            entries = self.runs()
            self.assertEqual((entries[PREDECESSOR]["state"], entries[PREDECESSOR]["blocking_obligations"]),
                             ("set_aside", {"status": "available", "count": 1}))
            self.assertEqual(self.summary(), {"status": "pending", "count": None, "review_run_ids": [SUCCESSOR]})

    def test_ob_t11_several_current_runs_aggregate_deterministically(self) -> None:
        """OB-T11: the sum over every current P4 Run, whatever their IDs; ``pending`` wherever the pending Run sorts."""
        ids = ("rr_01ARZ3NDEKTSV4RRFFQ69G5FAQ", "rr_01ARZ3NDEKTSV4RRFFQ69G5FAR", "rr_01ARZ3NDEKTSV4RRFFQ69G5FAS")
        shapes = {
            "human": dict(decided=(decide(p4.OUTCOME_HUMAN),)),
            "two blocking": dict(decided=(decide(p4.OUTCOME_PROBLEM, severity="HIGH", repair="a"),
                                          decide(p4.OUTCOME_PROBLEM, severity="MID", repair="b"))),
            "sealed": dict(decided=(decide(p4.OUTCOME_DISMISSED),), fifth="seal"),
            "pending": dict(generations=3),
        }
        orders = (("human", "two blocking", "sealed"), ("sealed", "human", "two blocking"),
                  ("two blocking", "sealed", "human"))
        texts = set()
        for order in orders:
            with self.subTest(order=order):
                self.reset_review()
                for run_id, kind, shape in zip(ids, kinds(), order):
                    self.p4_records(run_id, kind=kind, **shapes[shape])
                summary = self.summary()
                self.assertEqual(summary, {"status": "available", "count": 3, "review_run_ids": list(ids)})
                texts.add(json.dumps(summary, sort_keys=True))
        self.assertEqual(len(texts), 1)
        for position in range(3):
            with self.subTest(pending_at=position):
                self.reset_review()
                order = list(orders[0])
                order[position] = "pending"
                for run_id, kind, shape in zip(ids, kinds(), order):
                    self.p4_records(run_id, kind=kind, **shapes[shape])
                self.assertEqual(self.summary(), {"status": "pending", "count": None, "review_run_ids": list(ids)})


# --------------------------------------------------------------------------- OB-T12 .. OB-T14: the boundary


class BoundaryTests(ObligationsCase):
    def fixture(self) -> None:
        self.p4_records(PREDECESSOR, decided=(decide(p4.OUTCOME_PROBLEM, severity="HIGH"), decide(p4.OUTCOME_HUMAN)),
                        gaps=((RAW_GAP, p4.GAP_HUMAN),), fifth=None)
        self.p4_records(THIRD, kind=planning.KIND_ROADMAP, fifth="repair", sixth=True,
                        decided=(decide(p4.OUTCOME_PROBLEM, severity="LOW", repair="deliberate",
                                        disposition=p4.DISPOSITION_REPAIRED_CURRENT_CYCLE),))
        self.p4_records(SUCCESSOR, kind=planning.KIND_PHASE_ENTRY, generations=2)
        self.p4_records(FOURTH, decided=(decide(p4.OUTCOME_IMPROVEMENT),))
        (self.store.root / paths.adjudication_rel(FOURTH)).unlink()
        self.work_run("rr_01ARZ3NDEKTSV4RRFFQ69G5FAQ", generations=3)

    def test_ob_t12_no_finding_report_reviewer_or_request_material_is_emitted(self) -> None:
        self.fixture()
        model = self.model()
        human = status.render_human(model)
        text = status.render_json(model) + human
        review = json.loads(status.render_json(model))["review"]
        obligations = {entry["review_run_id"]: entry["blocking_obligations"] for entry in review["runs"]["entries"]}
        self.assertEqual(obligations, {
            PREDECESSOR: {"status": "available", "count": 3}, THIRD: {"status": "available", "count": 1},
            SUCCESSOR: PENDING, FOURTH: INVALID, "rr_01ARZ3NDEKTSV4RRFFQ69G5FAQ": NA,
        })
        self.assertEqual(review["pending_obligations"]["status"], "invalid")
        for leaked in MATERIAL:
            with self.subTest(leaked=leaked):
                self.assertNotIn(leaked, text)
        self.assertIn("  pending obligations: invalid", human)
        self.assertIn("obligations available 3", human)
        self.assertIn("obligations pending", human)
        with self.subTest("a malformed stored value never reaches the Review section"):
            built = self.p4_records(FOURTH, decided=(decide(p4.OUTCOME_IMPROVEMENT),))
            record = built["adjudication"].to_record()
            record["findings"][0]["severity"] = RAW_VALUE
            self.rewrite(FOURTH, record)
            model = self.model()
            review = json.loads(status.render_json(model))["review"]
            human = status.render_human(model)
            block = human[human.index("\nReview\n"):human.index("\nValidation\n")]
            entry = {found["review_run_id"]: found for found in review["runs"]["entries"]}[FOURTH]
            self.assertEqual((entry["state"], entry["blocking_obligations"]), ("invalid", INVALID))
            for leaked in MATERIAL:
                self.assertNotIn(leaked, json.dumps(review))
                self.assertNotIn(leaked, block)

    def test_ob_t13_the_projection_stays_read_only(self) -> None:
        self.fixture()

        def call() -> dict:
            model = status.build_status(self.store.root)
            status.render_human(model)
            return json.loads(status.render_json(model))

        data, boundary = self.assertReadOnly(call, self.store.root)
        self.assertNotIn("fetch", boundary.git_subcommands())
        self.assertEqual(data["review"]["pending_obligations"]["status"], "invalid")
        from test_status_read_only import StaticCallGraphTests

        checker = StaticCallGraphTests("test_the_status_modules_name_no_write")
        for function in (p4.blocking_obligations, review_status._run_obligations, review_status._first_contracts,
                         review_status._project_obligations, review_status._pending_obligations):
            source = textwrap.dedent(inspect.getsource(function))
            ast.parse(source)
            checker.check(source, function.__name__)

    def test_ob_t14_deterministic_json_with_its_schema_and_version_unchanged(self) -> None:
        self.fixture()
        first, second = status.render_json(self.model()), status.render_json(self.model())
        self.assertEqual(first, second)
        data = json.loads(first)
        self.assertEqual((data["schema"], data["version"]), ("workline-status", 1))
        review = data["review"]
        self.assertEqual(set(review), {"status", "reason", "namespace", "activation", "runs", "pending_obligations"})
        self.assertEqual(set(review["pending_obligations"]), {"status", "count", "review_run_ids"})
        for entry in review["runs"]["entries"]:
            with self.subTest(run=entry["review_run_id"]):
                self.assertEqual(set(entry), set(review_status._run_entry(entry["review_run_id"])))
                self.assertEqual(set(entry["blocking_obligations"]), {"status", "count"})
        self.assertEqual(review_status.RUN_STATES,
                         ("open", "sealed", "invalidated", "set_aside", "consumed", "invalid"))


if __name__ == "__main__":
    import unittest

    unittest.main()
