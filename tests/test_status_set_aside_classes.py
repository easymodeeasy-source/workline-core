"""RB1 post-P4 carry (Control Plane §3): Review ``set_aside`` for every Review Run class, by its own canonical reader.

Classes, each read by the one fail-closed reader its Review contract owns (never a parser in ``review/status.py``):

* A - legacy Work request (v1 / v2): ``work_review.request_set_aside``, unchanged (``test_status_set_aside``);
* B - legacy planning request: ``planning.request_set_aside`` (new, additive; recovery's own reading untouched);
* C / D - P4 Work / planning discovery requests: ``p4.set_aside_named`` (new, additive), which reuses
  ``p4.proven_successor`` for a Run named as repaired and proves the G4 HUMAN_WAIT of a Run named by a Human decision.

The records here are built by the canonical builders (``planning.request_envelope``, ``p4.discovery_request``,
``p4.task_input``, ``p4.accepted_descriptor``) and only the one field under test is perturbed afterwards, with every
digest that binds it recomputed, so each refusal is the linkage reader's and never a provenance mismatch. The
positive P4 repaired / Human-decision linkages come from the real owner flows (``test_status_set_aside_p4_flows``).

Run IDs sort the successor BEFORE its predecessor: nothing may be read from ID, filename or age order.
"""

from __future__ import annotations

import ast
import inspect
import json
import textwrap
from typing import Any, Callable

from test_status_set_aside import (
    ABSENT, PREDECESSOR, RAW_REQUEST, RAW_VERSION, ROADMAP, SUCCESSOR, THIRD, WORK, SetAsideCase, aside,
    consumption_id_of, receipt_id_of, work_envelope,
)
from workline import status
from workline.review import p4, paths, planning, records, serialize, work_review
from workline.review import status as review_status

from test_review_gate_generation import gate_record

PHASE = "p_01ARZ3NDEKTSV4RRFFQ69G5FAV"
RAW_ACTOR = "RAW-ACTOR-IDENTITY-carry"
RAW_DECISION = p4.HumanDecision("hd-raw-carry-1", p4.DECISION_CONFIRMED)
OTHER_DECISION = p4.HumanDecision("hd-raw-carry-2", p4.DECISION_CHANGED)
PLANNING_KINDS = (planning.KIND_ROADMAP, planning.KIND_PHASE_ENTRY)


def planning_consumption(run_id: str, kind: str, target: str, operation: str) -> dict:
    """A version 2 planning Consumption of ``run_id``'s generation-3 Receipt, read back by its own reader."""
    result: dict[str, Any] = {
        "contract": records.PERSISTED_RESULT_CONTRACT, "request_digest": "1" * 64, "registration_commit": "2" * 40,
        "registration_parent": "3" * 40, "branch": "refs/heads/main", "registration_delta_digest": "4" * 64,
        "semantic_projection_digest": "5" * 64, "adapter_identity": records.PLANNING_ADAPTER_IDENTITY[kind],
        "loader_identity": "6" * 64,
    }
    if kind == planning.KIND_ROADMAP:
        result.update(roadmap_id=target, phase_ids=[], relation_ids=[])
    else:
        result.update(phase_id=target, roadmap_id=ROADMAP, work_ids=[], integration_work_id=WORK,
                      confirmation_work_id=None, roadmap_relation_ids=[], related_relation_ids=[],
                      canonical_first_work_id=None)
    record = records.PlanningConsumption(
        consumption_id=consumption_id_of(run_id), receipt_id=receipt_id_of(run_id), review_run_id=run_id,
        review_generation=3, review_kind=kind, authorized_candidate_hash="a" * 64, operation_identity=operation,
        operation_mutation_id="mut_" + run_id.split("_", 1)[1], target_identity=target, persisted_result=result,
    ).to_record()
    records.consumption_from_record(record, "the fixture")  # its own reader accepts it
    return record


def p4_task_id(run_id: str, index: int) -> str:
    return "rtk_P" + str(index) + run_id.split("_", 1)[1][2:]


class ClassesCase(SetAsideCase):
    @staticmethod
    def identity(kind: str) -> tuple[str, str]:
        if kind == work_review.REVIEW_KIND:
            return WORK, work_review.operation_identity(WORK)
        target = ROADMAP if kind == planning.KIND_ROADMAP else PHASE
        return target, "plan:" + target  # the operation identity SetAsideCase.work_run gives a planning Run

    def planning_v1(self, run_id: str, *, set_aside: list[dict], kind: str = planning.KIND_ROADMAP,
                    edit: Callable[[dict], Any] | None = None, consumed: bool = False, **chain: Any) -> None:
        """A v1 planning Run whose request :func:`planning.request_envelope` builds (perturbed by ``edit``).

        ``consumed`` adds the version 2 planning Consumption of its generation-3 Receipt.
        """
        envelope = planning.request_envelope(kind, {"note": RAW_REQUEST}, {"note": RAW_REQUEST}, set_aside)
        if edit is not None:
            edit(envelope)
        target, operation = self.identity(kind)
        self.work_run(run_id, envelope=envelope, kind=kind, target=target, **chain)
        if consumed:
            self.put(paths.consumption_rel(consumption_id_of(run_id)), planning_consumption(run_id, kind, target, operation))

    def p4_run(
        self, run_id: str, *, kind: str = work_review.REVIEW_KIND, set_aside: tuple | list = (), generation: int = 1,
        succession: dict | None = None, decision: p4.HumanDecision | None = None,
        viewpoints: tuple[str, ...] = ("correctness",), contract: str | None = None,
        edit: Callable[[dict, int], Any] | None = None, bind: bool = True, write: tuple[int, ...] | None = None,
        v1_task: bool = False,
    ) -> None:
        """A P4 Run at generation 1: one discovery TaskInput per viewpoint, built by the canonical P4 builders.

        ``edit(envelope, index)`` perturbs one discovery request before its TaskInput (and so its digests) is
        built; ``bind=False`` breaks the accepted descriptor's task_input_digest; ``write`` names the
        TaskInputs actually stored; ``v1_task`` adds a v1 Work task beside the P4 ones.
        """
        target, operation = self.identity(kind)
        if contract is None:
            contract = work_review.P4_CONTRACT if kind == work_review.REVIEW_KIND else planning.P4_CONTRACT
        descriptors = []
        for index, viewpoint in enumerate(viewpoints):
            envelope = p4.discovery_request(
                review_contract=contract, review_kind=kind, viewpoint=viewpoint, candidate={"note": RAW_REQUEST},
                context={"note": RAW_REQUEST}, requirement=p4.requirement_record(kind, {"note": RAW_REQUEST}),
                candidate_generation=generation, succession=succession, set_aside_runs=list(set_aside),
                human_decision=decision,
            )
            if edit is not None:
                edit(envelope, index)
            task_input = p4.task_input(
                task_id=p4_task_id(run_id, index), task_slot=p4.discovery_slot(viewpoint),
                task_kind=p4.TASK_KIND_DISCOVERY, actor_identity=RAW_ACTOR, actor_version="1", envelope=envelope,
                candidate_hash="a" * 64, candidate_material_digest="9" * 64, review_context_hash="b" * 64,
                accepted_generation=1,
            )
            if write is None or index in write:
                self.put(paths.task_input_rel(task_input.task_id), task_input.to_record())
            descriptor = p4.accepted_descriptor(task_input)
            descriptors.append(descriptor if bind else dict(descriptor, task_input_digest="0" * 64))
        if v1_task:
            v1 = work_envelope(WORK, [], run_id)
            record = {
                "schema": records.SCHEMA_TASK_INPUT, "version": records.VERSION, "task_id": p4_task_id(run_id, 9),
                "task_slot": work_review.TASK_SLOT, "task_kind": work_review.TASK_KIND,
                "reviewer_identity": RAW_ACTOR, "reviewer_version": "1", "request_envelope": v1,
                "request_digest": serialize.digest(v1), "candidate_hash": "a" * 64,
                "reconstruction_mode": records.RECONSTRUCTION_SNAPSHOT, "candidate_material_digest": "9" * 64,
                "review_context_hash": "b" * 64, "effective_policy_hash": "c" * 64, "accepted_generation": 1,
            }
            self.put(paths.task_input_rel(p4_task_id(run_id, 9)), record)
            descriptors.append({
                "task_id": p4_task_id(run_id, 9), "task_slot": work_review.TASK_SLOT,
                "task_kind": work_review.TASK_KIND, "reviewer_identity": RAW_ACTOR, "reviewer_version": "1",
                "candidate_hash": "a" * 64, "candidate_material_digest": "9" * 64,
                "reconstruction_mode": records.RECONSTRUCTION_SNAPSHOT, "request_digest": serialize.digest(v1),
                "task_input_digest": serialize.digest(record), "review_context_hash": "b" * 64,
                "effective_policy_hash": "c" * 64,
            })
        self.put(paths.gate_rel(run_id, 1), gate_record(
            1, review_run_id=run_id, review_kind=kind, target_identity=target, operation_identity=operation,
            accepted_tasks=descriptors, effective_policy_hash=p4.policy_hash(),
        ))

    def states(self) -> dict[str, str]:
        return {run_id: entry["state"] for run_id, entry in self.entries().items()}

    def assert_refused(self, code: str, *, kept: dict[str, str], namer: str = SUCCESSOR, reader: str) -> dict:
        entries = self.entries()
        entry = entries[namer]
        self.assertEqual(entry["state"], "invalid", entry)
        self.assertEqual(entry["reason"]["code"], code, entry["reason"])
        self.assertIn(namer, entry["reason"]["message"])
        self.assertIn(reader, entry["reason"]["message"])
        for run_id, state in kept.items():
            self.assertEqual(entries[run_id]["state"], state, entries[run_id])
        self.assertNotIn("set_aside", [found["state"] for found in entries.values()])
        return entry


# --------------------------------------------------------------------------- A: legacy Work requests


class LegacyWorkRequestTests(ClassesCase):
    def test_a_legacy_work_requests_are_read_exactly_as_before(self) -> None:
        """Tests 1 and 2: v1 names nothing, v2 sets aside, and refusals read exactly as RB1-R9 wrote them."""
        self.assertIs(review_status._V1_READERS[work_review.REVIEW_KIND][1], work_review.request_set_aside)
        self.work_run(PREDECESSOR, generations=2)
        self.work_run(THIRD, set_aside=None)
        self.work_run(SUCCESSOR, set_aside=aside((PREDECESSOR, "review_context_changed")))
        self.assertEqual(self.states(), {PREDECESSOR: "set_aside", THIRD: "open", SUCCESSOR: "open"})
        self.reset_review()
        refused = work_envelope(WORK, aside((PREDECESSOR, "set_aside")), SUCCESSOR)
        refused["version"] = RAW_VERSION
        self.work_run(PREDECESSOR)
        self.work_run(SUCCESSOR, envelope=refused)
        self.assertEqual(self.entries()[SUCCESSOR]["reason"], {
            "code": "review_record_invalid",
            "message": f"the request of Work Review Run {SUCCESSOR} is refused by the Work request version reader "
                       "(version 1 names no Run; version 2 names exactly its validated list, in canonical order)",
        })
        (self.store.root / paths.task_input_rel("rtk_" + SUCCESSOR.split("_", 1)[1])).unlink()
        self.assertEqual(self.entries()[SUCCESSOR]["reason"], {
            "code": "review_record_missing",
            "message": f"the task input rtk_{SUCCESSOR.split('_', 1)[1]} of Work Review Run {SUCCESSOR} does not read",
        })
        self.assertEqual(self.entries()[PREDECESSOR]["state"], "open")


# --------------------------------------------------------------------------- B: legacy planning requests


class PlanningRequestTests(ClassesCase):
    def test_b_a_valid_planning_request_sets_its_predecessor_aside(self) -> None:
        """Test 3: a valid planning successor request (its canonical reader) -> the predecessor ``set_aside``."""
        for kind in PLANNING_KINDS:
            for generations, reason in ((1, planning.STALE_CONTEXT), (2, planning.SET_ASIDE_NOT_AUTHORIZED),
                                        (3, planning.SET_ASIDE_SET_ASIDE)):
                with self.subTest(kind=kind, predecessor_generations=generations):
                    self.reset_review()
                    self.planning_v1(PREDECESSOR, set_aside=[], kind=kind, generations=generations)
                    self.planning_v1(SUCCESSOR, set_aside=aside((PREDECESSOR, reason)), kind=kind)
                    entries = self.entries()
                    self.assertEqual(
                        (entries[PREDECESSOR]["state"], entries[PREDECESSOR]["reason"],
                         entries[PREDECESSOR]["latest_generation"], entries[PREDECESSOR]["review_kind"]),
                        ("set_aside", None, generations, kind),
                    )
                    self.assertEqual((entries[SUCCESSOR]["state"], entries[SUCCESSOR]["reason"]), ("open", None))

    def test_b_the_successor_keeps_its_own_state_and_names_compose(self) -> None:
        """Test 9 (B): the naming Run keeps open / sealed / consumed; successive successors each set theirs aside."""
        for generations, consumed, expected in ((1, False, "open"), (3, False, "sealed"), (3, True, "consumed")):
            with self.subTest(successor=expected):
                self.reset_review()
                self.planning_v1(PREDECESSOR, set_aside=[])
                self.planning_v1(THIRD, set_aside=aside((PREDECESSOR, planning.STALE_POLICY)))
                self.planning_v1(SUCCESSOR, set_aside=aside((THIRD, planning.STALE_DECLARED_BASE)),
                                 generations=generations, consumed=consumed)
                self.assertEqual(self.states(), {PREDECESSOR: "set_aside", THIRD: "set_aside", SUCCESSOR: expected})

    def test_b_an_empty_list_or_a_mention_elsewhere_sets_nothing_aside(self) -> None:
        self.planning_v1(PREDECESSOR, set_aside=[], generations=2)
        self.planning_v1(SUCCESSOR, set_aside=[], edit=lambda envelope: envelope["candidate"].update(note=PREDECESSOR))
        self.assertEqual(self.states(), {PREDECESSOR: "open", SUCCESSOR: "open"})

    def test_b_invalidated_and_consumed_keep_their_state(self) -> None:
        """Tests 7 and 8 (B)."""
        self.planning_v1(PREDECESSOR, set_aside=[], generations=4)
        self.planning_v1(THIRD, set_aside=[], generations=3, consumed=True)
        self.planning_v1(SUCCESSOR, set_aside=aside((PREDECESSOR, planning.SET_ASIDE_INVALIDATED),
                                                    (THIRD, planning.SET_ASIDE_CONSUMED)))
        self.assertEqual(self.states(), {PREDECESSOR: "invalidated", THIRD: "consumed", SUCCESSOR: "open"})

    def test_b_a_request_the_planning_reader_refuses(self) -> None:
        """Test 6 (B): every shape the writer never writes is refused, never normalized; nothing is set aside."""

        def items(*pairs: tuple[str, str]) -> Callable[[dict], None]:
            return lambda envelope: envelope.update(set_aside_runs=aside(*pairs))

        cases: dict[str, Callable[[dict], None]] = {
            "unsorted": items((PREDECESSOR, "set_aside"), (THIRD, "set_aside")),
            "twice": items((PREDECESSOR, "set_aside"), (PREDECESSOR, "consumed")),
            "extra item key": lambda e: e["set_aside_runs"][0].update(note="x"),
            "no reason identity": lambda e: e["set_aside_runs"][0].update(reason="Not A Reason"),
            "not a review_run id": lambda e: e["set_aside_runs"][0].update(review_run_id="rr_nope"),
            "not a list": lambda e: e.update(set_aside_runs={"review_run_id": PREDECESSOR, "reason": "set_aside"}),
            "names itself": items((SUCCESSOR, "set_aside"), (PREDECESSOR, "set_aside")),
            "unknown version": lambda e: e.update(version=RAW_VERSION),
            "missing field": lambda e: e.pop("context"),
            "extra field": lambda e: e.update(extra=RAW_REQUEST),
            "not a planning request": lambda e: e.update(schema=work_review.SCHEMA_REQUEST),
            "not a planning kind": lambda e: e.update(review_kind=work_review.REVIEW_KIND),
        }
        for name, edit in cases.items():
            with self.subTest(name):
                self.reset_review()
                self.planning_v1(PREDECESSOR, set_aside=[])
                self.planning_v1(THIRD, set_aside=[], generations=3)
                self.planning_v1(SUCCESSOR, set_aside=aside((PREDECESSOR, "set_aside"), (THIRD, "set_aside")),
                                 edit=edit)
                self.assert_refused("review_record_invalid", kept={PREDECESSOR: "open", THIRD: "sealed"},
                                    reader="planning request reader")

    def test_b_names_that_contradict_the_namespace(self) -> None:
        cases = (
            ("a Work Run", lambda: self.work_run(THIRD, generations=1), {THIRD: "open"}),
            ("a Run this namespace does not hold", lambda: None, {}),
        )
        for name, make_third, kept in cases:
            with self.subTest(name):
                self.reset_review()
                self.planning_v1(PREDECESSOR, set_aside=[])
                make_third()
                named = THIRD if kept else ABSENT
                self.planning_v1(SUCCESSOR, set_aside=aside((PREDECESSOR, "set_aside"), (named, "set_aside")))
                entry = self.entries()[SUCCESSOR]
                self.assertEqual((entry["state"], entry["reason"]["code"]), ("invalid", "review_record_conflict"))
                self.assertIn(named, entry["reason"]["message"])
                self.assertEqual(self.entries()[PREDECESSOR]["state"], "open")

    def test_recovery_keeps_its_own_tolerant_planning_reading(self) -> None:
        """The new reader is additive: recovery's planning adapter is the same function, reading as before."""
        from workline.review import recovery

        self.assertIs(recovery.PLANNING.named, recovery._planning_named)
        source = inspect.getsource(recovery._planning_named)
        self.assertNotIn("request_set_aside", source)
        self.assertIn('envelope.get("set_aside_runs") or []', source)


# --------------------------------------------------------------------------- C / D: P4 Work and planning requests


def kinds() -> tuple[str, ...]:
    return (work_review.REVIEW_KIND,) + PLANNING_KINDS


class P4RequestTests(ClassesCase):
    def v1_run(self, run_id: str, kind: str, **chain: Any) -> None:
        if kind == work_review.REVIEW_KIND:
            self.work_run(run_id, set_aside=None, **chain)
        else:
            self.planning_v1(run_id, set_aside=[], kind=kind, **chain)

    def test_c_d_a_valid_p4_run_is_never_read_as_a_v1_request(self) -> None:
        """Test 4 (shape): a valid P4 Run - one discovery viewpoint or several - is never ``invalid`` for its schema."""
        for kind in kinds():
            for viewpoints in (("correctness",), ("correctness", "security")):
                with self.subTest(kind=kind, viewpoints=len(viewpoints)):
                    self.reset_review()
                    self.p4_run(SUCCESSOR, kind=kind, viewpoints=viewpoints)
                    entry = self.entries()[SUCCESSOR]
                    self.assertEqual((entry["state"], entry["reason"], entry["review_kind"]), ("open", None, kind))

    def test_c_d_a_p4_run_names_the_runs_its_recovery_set_aside(self) -> None:
        """Tests 4 and 5 (recovery-recorded reasons): a P4 first Run's validated list sets those Runs aside."""
        for kind in kinds():
            with self.subTest(kind=kind):
                self.reset_review()
                self.v1_run(PREDECESSOR, kind, generations=2)
                self.p4_run(THIRD, kind=kind)
                self.p4_run(SUCCESSOR, kind=kind, viewpoints=("correctness", "security"),
                            set_aside=aside((PREDECESSOR, planning.SET_ASIDE_NOT_AUTHORIZED),
                                            (THIRD, planning.STALE_CONTEXT)))
                entries = self.entries()
                self.assertEqual({run_id: entry["state"] for run_id, entry in entries.items()},
                                 {PREDECESSOR: "set_aside", THIRD: "set_aside", SUCCESSOR: "open"})
                self.assertEqual([entries[run_id]["reason"] for run_id in entries], [None, None, None])

    def test_c_d_precedence_invalidated_consumed_and_the_namers_own_state(self) -> None:
        """Tests 7, 8, 9 (C / D): invalidated and consumed stay; the P4 namer keeps its own state."""
        for kind in kinds():
            with self.subTest(kind=kind):
                self.reset_review()
                self.v1_run(PREDECESSOR, kind, generations=4)
                self.v1_run(THIRD, kind, generations=3, consumed=True)
                self.p4_run(SUCCESSOR, kind=kind, set_aside=aside((PREDECESSOR, planning.SET_ASIDE_INVALIDATED),
                                                                  (THIRD, planning.SET_ASIDE_CONSUMED)))
                self.assertEqual(self.states(), {PREDECESSOR: "invalidated", THIRD: "consumed", SUCCESSOR: "open"})

    def test_c_d_a_request_the_p4_linkage_reader_refuses(self) -> None:
        """Test 6 (C / D, request): each shape the P4 writer never writes is refused; nothing is set aside."""
        succession = p4.succession_record(PREDECESSOR, "a" * 64, "rrb_" + "0" * 26, "e" * 64)

        def items(*pairs: tuple[str, str]) -> Callable[[dict, int], None]:
            return lambda envelope, _index: envelope.update(set_aside_runs=aside(*pairs))

        cases: dict[str, tuple[dict, Callable[[dict, int], None]]] = {
            "unsorted": ({}, items((PREDECESSOR, "set_aside"), (THIRD, "set_aside"))),
            "twice": ({}, items((PREDECESSOR, "set_aside"), (PREDECESSOR, "consumed"))),
            "extra item key": ({}, lambda e, _i: e["set_aside_runs"][0].update(note="x")),
            "no reason identity": ({}, lambda e, _i: e["set_aside_runs"][0].update(reason="Not A Reason")),
            "not a review_run id": ({}, lambda e, _i: e["set_aside_runs"][0].update(review_run_id="rr_nope")),
            "not a list": ({}, lambda e, _i: e.update(set_aside_runs={"review_run_id": PREDECESSOR, "reason": "x"})),
            "names itself": ({}, items((SUCCESSOR, "set_aside"), (PREDECESSOR, "set_aside"))),
            "missing field": ({}, lambda e, _i: e.pop("human_decision")),
            "candidate generation 0": ({}, lambda e, _i: e.update(candidate_generation=0)),
            "candidate generation a bool": ({}, lambda e, _i: e.update(candidate_generation=True)),
            "generation 2 with no succession": ({}, lambda e, _i: e.update(candidate_generation=2)),
            "generation 1 with a succession": ({}, lambda e, _i: e.update(succession=succession)),
            "succession with an extra key": (
                {"generation": 2, "succession": succession, "set_aside": aside((PREDECESSOR, p4.SET_ASIDE_REPAIRED))},
                lambda e, _i: e["succession"].update(extra="x"),
            ),
            "succession naming its own Run": (
                {"generation": 2, "succession": p4.succession_record(SUCCESSOR, "a" * 64, "rrb_" + "0" * 26, "e" * 64),
                 "set_aside": aside((PREDECESSOR, p4.SET_ASIDE_REPAIRED))},
                lambda e, _i: None,
            ),
            "a successor naming more than its predecessor": (
                {"generation": 2, "succession": succession,
                 "set_aside": aside((PREDECESSOR, p4.SET_ASIDE_REPAIRED), (THIRD, "set_aside"))},
                lambda e, _i: None,
            ),
            "a successor naming its predecessor for another reason": (
                {"generation": 2, "succession": succession, "set_aside": aside((PREDECESSOR, "set_aside"))},
                lambda e, _i: None,
            ),
            "a Human-decision name with no decision": (
                {"set_aside": aside((PREDECESSOR, p4.SET_ASIDE_HUMAN_DECISION))}, lambda e, _i: None,
            ),
            "a decision that is not a Human-decision record": (
                {"decision": RAW_DECISION}, lambda e, _i: e["human_decision"].update(disposition=RAW_VERSION),
            ),
            "discovery requests that disagree": (
                {"viewpoints": ("correctness", "security")},
                lambda e, index: e.update(set_aside_runs=aside((PREDECESSOR, "set_aside"))) if index else None,
            ),
        }
        for kind in kinds():
            for name, (arguments, edit) in cases.items():
                with self.subTest(kind=kind, case=name):
                    self.reset_review()
                    self.v1_run(PREDECESSOR, kind)
                    self.v1_run(THIRD, kind, generations=3)
                    options = {"set_aside": aside((PREDECESSOR, "set_aside"), (THIRD, "set_aside")), **arguments}
                    self.p4_run(SUCCESSOR, kind=kind, edit=edit, **options)
                    self.assert_refused("review_record_invalid", kept={PREDECESSOR: "open", THIRD: "sealed"},
                                        reader="P4 linkage reader")
        for kind in kinds():
            with self.subTest(kind=kind, case="a P4 request under a task kind that is not its own: not P4, refused"):
                self.reset_review()
                self.v1_run(PREDECESSOR, kind)
                self.p4_run(SUCCESSOR, kind=kind, set_aside=aside((PREDECESSOR, "set_aside")),
                            edit=lambda e, _i: e.update(schema=p4.SCHEMA_ADJUDICATION_REQUEST))
                self.assert_refused("review_record_invalid", kept={PREDECESSOR: "open"}, reader="is refused by")

    def test_c_d_provenance_and_contract_refusals(self) -> None:
        """Test 6 (C / D, records): an unbound or missing TaskInput, mixed or foreign contracts set nothing aside."""
        named = aside((PREDECESSOR, "set_aside"))
        cases = (
            ("an unbound TaskInput", {"bind": False}, "review_provenance_conflict", "P4 linkage reader"),
            ("a missing TaskInput", {"viewpoints": ("correctness", "security"), "write": (0,)},
             "review_record_missing", "P4 linkage reader"),
            ("a v1 task beside the P4 ones", {"v1_task": True}, "review_record_conflict", "more than one Review contract"),
        )
        for kind in kinds():
            for name, options, code, reader in cases:
                with self.subTest(kind=kind, case=name):
                    self.reset_review()
                    self.v1_run(PREDECESSOR, kind)
                    self.p4_run(SUCCESSOR, kind=kind, set_aside=named, **options)
                    self.assert_refused(code, kept={PREDECESSOR: "open"}, reader=reader)
        with self.subTest("the P4 contract of another Review kind"):
            self.reset_review()
            self.v1_run(PREDECESSOR, work_review.REVIEW_KIND)
            self.p4_run(SUCCESSOR, set_aside=named, contract=planning.P4_CONTRACT)
            self.assert_refused("review_record_conflict", kept={PREDECESSOR: "open"},
                                reader="the P4 contract of another Review kind")

    def test_c_d_a_named_run_the_canonical_records_do_not_prove_set_aside(self) -> None:
        """Test 6 (C / D, linkage): a repaired name with no proven successor, a Human-decision name with no wait."""
        succession = p4.succession_record(PREDECESSOR, "a" * 64, "rrb_" + "0" * 26, "e" * 64)
        cases = (
            ("repaired, first-Run style, no successor proven", {"set_aside": aside((PREDECESSOR, p4.SET_ASIDE_REPAIRED))}),
            ("repaired, as the successor's predecessor", {"generation": 2, "succession": succession,
                                                          "set_aside": aside((PREDECESSOR, p4.SET_ASIDE_REPAIRED))}),
            ("a Human decision for a Run that never waited", {
                "set_aside": aside((PREDECESSOR, p4.SET_ASIDE_HUMAN_DECISION)), "decision": RAW_DECISION}),
        )
        for kind in kinds():
            for predecessor_is_p4 in (True, False):
                for name, options in cases:
                    with self.subTest(kind=kind, predecessor_p4=predecessor_is_p4, case=name):
                        self.reset_review()
                        if predecessor_is_p4:
                            self.p4_run(PREDECESSOR, kind=kind)
                        else:
                            self.v1_run(PREDECESSOR, kind, generations=2)
                        self.p4_run(SUCCESSOR, kind=kind, **options)
                        entry = self.assert_refused(p4.REASON_LINKAGE_INVALID, kept={PREDECESSOR: "open"},
                                                    reader="P4 linkage reader")
                        self.assertNotIn(RAW_DECISION.decision_id, json.dumps(entry))

    def test_c_d_names_that_contradict_the_namespace(self) -> None:
        for kind in kinds():
            other_kind = planning.KIND_ROADMAP if kind == work_review.REVIEW_KIND else work_review.REVIEW_KIND
            for name, make_third, kept in (
                ("a Run of another Review kind", lambda: self.v1_run(THIRD, other_kind), {THIRD: "open"}),
                ("a Run this namespace does not hold", lambda: None, {}),
            ):
                with self.subTest(kind=kind, case=name):
                    self.reset_review()
                    self.v1_run(PREDECESSOR, kind)
                    make_third()
                    named = THIRD if kept else ABSENT
                    self.p4_run(SUCCESSOR, kind=kind, set_aside=aside((PREDECESSOR, "set_aside"), (named, "set_aside")))
                    entry = self.entries()[SUCCESSOR]
                    self.assertEqual((entry["state"], entry["reason"]["code"]), ("invalid", "review_record_conflict"))
                    self.assertIn(named, entry["reason"]["message"])
                    self.assertEqual(self.entries()[PREDECESSOR]["state"], "open")


# --------------------------------------------------------------------------- tests 10 and 11 over every class


class ClassesBoundaryTests(ClassesCase):
    def fixture(self) -> None:
        # A (v2 Work), B (planning), C / D (P4, a recovery-recorded name), and refused P4 / planning requests
        self.work_run(PREDECESSOR, generations=3)
        self.work_run(SUCCESSOR, set_aside=aside((PREDECESSOR, "set_aside")), generations=3, consumed=True)
        self.planning_v1(THIRD, set_aside=[])
        self.p4_run("rr_01ARZ3NDEKTSV4RRFFQ69G5FAQ", kind=planning.KIND_ROADMAP,
                    set_aside=aside((THIRD, planning.STALE_CONTEXT)), decision=OTHER_DECISION)
        self.p4_run("rr_01ARZ3NDEKTSV4RRFFQ69G5FAR", set_aside=aside((PREDECESSOR, p4.SET_ASIDE_HUMAN_DECISION)),
                    decision=RAW_DECISION)
        self.planning_v1("rr_01ARZ3NDEKTSV4RRFFQ69G5FAS", set_aside=[],
                         edit=lambda envelope: envelope.update(version=RAW_VERSION))

    def test_no_request_or_reviewer_material_is_emitted(self) -> None:
        """Test 10."""
        self.fixture()
        model = self.model()
        text = status.render_json(model) + status.render_human(model)
        self.assertEqual(self.states(), {
            PREDECESSOR: "set_aside", SUCCESSOR: "consumed", THIRD: "set_aside",
            "rr_01ARZ3NDEKTSV4RRFFQ69G5FAQ": "open", "rr_01ARZ3NDEKTSV4RRFFQ69G5FAR": "invalid",
            "rr_01ARZ3NDEKTSV4RRFFQ69G5FAS": "invalid",
        })
        for leaked in (RAW_REQUEST, RAW_VERSION, RAW_ACTOR, RAW_DECISION.decision_id, OTHER_DECISION.decision_id,
                       "set_aside_runs", "request_envelope", p4.DISCOVERY_INSTRUCTION, planning.INSTRUCTION):
            with self.subTest(leaked=leaked):
                self.assertNotIn(leaked, text)

    def test_the_projection_stays_read_only(self) -> None:
        """Test 11: build + both renders under the read-only boundary; no write, lock, mutation, network."""
        self.fixture()

        def call() -> dict:
            model = status.build_status(self.store.root)
            status.render_human(model)
            return json.loads(status.render_json(model))

        data, boundary = self.assertReadOnly(call, self.store.root)
        self.assertNotIn("fetch", boundary.git_subcommands())
        states = {entry["review_run_id"]: entry["state"] for entry in data["review"]["runs"]["entries"]}
        self.assertEqual((states[PREDECESSOR], states[THIRD]), ("set_aside", "set_aside"))

    def test_the_new_readers_name_no_write(self) -> None:
        """Test 11 (static): the two new readers name no write, lock, mutation, commit, push or remote read."""
        from test_status_read_only import StaticCallGraphTests

        checker = StaticCallGraphTests("test_the_status_modules_name_no_write")
        for function in (planning.request_set_aside, p4.set_aside_named, p4._request_linkage,
                         p4._waits_for_another_decision, review_status._request_names, review_status._contracts,
                         review_status._v1_request_names):
            source = textwrap.dedent(inspect.getsource(function))
            ast.parse(source)
            checker.check(source, function.__name__)


if __name__ == "__main__":
    import unittest

    unittest.main()
