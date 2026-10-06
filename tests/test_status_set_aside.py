"""RB1-R9 (§29.18, §29.30): Review ``set_aside`` is projected from positive successor evidence, and from nothing else.

A Run is ``set_aside`` only when the stored request of another Work Run - the
task input its generation 1 accepted, bound by digest - names it, read by the
one Work request-version reader ``work_review.request_set_aside`` (F4 §11.6,
§11.18.6), and it is another Run of the same Review kind and operation
identity. Precedence holds: an invalidated, consumed or unreadable Run keeps
its state; the naming Run keeps its own. A malformed or contradictory linkage
sets nothing aside and makes the naming Run ``invalid`` with its exact code.
No request payload or reviewer output reaches the model, and the projection is
read-only.

The Run IDs are chosen so that the successor sorts BEFORE its predecessor:
nothing may be read from ID, filename or age order.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil

from status_helpers import StatusCase
from workline import cli, status
from workline.review import paths, planning, records, serialize, work_review

from test_review_authorization import consumption_record, receipt_record
from test_review_gate_generation import gate_record

WORK = "w_01ARZ3NDEKTSV4RRFFQ69G5FAV"
OTHER_WORK = "w_01ARZ3NDEKTSV4RRFFQ69G5FAW"
ROADMAP = "r_01ARZ3NDEKTSV4RRFFQ69G5FAV"

PREDECESSOR = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAZ"
SUCCESSOR = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"
THIRD = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAX"
FOURTH = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAY"
ABSENT = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAT"

#: Text that only the stored request carries; it must never reach the status model.
RAW_REQUEST = "RAW-REQUEST-PAYLOAD-r9"
RAW_VERSION = "RAW-VERSION-PAYLOAD-r9"
RESULT_DIGEST = "7" * 64  # the settled task's reviewer result digest


def _suffix(run_id: str) -> str:
    return run_id.split("_", 1)[1]


def task_id_of(run_id: str) -> str:
    return "rtk_" + _suffix(run_id)


def receipt_id_of(run_id: str) -> str:
    return "rcp_" + _suffix(run_id)


def consumption_id_of(run_id: str) -> str:
    return "rcs_" + _suffix(run_id)


def work_envelope(work_id: str, set_aside: list[dict] | None, review_run_id: str, *, mention: str = "") -> dict:
    """The canonical writer's envelope: version 1 when ``set_aside`` is None, else version 2."""
    candidate = {
        "declared_base": {"work": {"work_id": work_id, "display": "W1", "name": "Work one", "desired_state": None}},
        "note": RAW_REQUEST + mention,
    }
    context = {"note": RAW_REQUEST}
    return work_review.request_envelope(candidate, context, set_aside, review_run_id=review_run_id)


def aside(*pairs: tuple[str, str]) -> list[dict]:
    return [{"review_run_id": run_id, "reason": reason} for run_id, reason in pairs]


class SetAsideCase(StatusCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def put(self, relative: str, record: dict) -> None:
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(serialize.canonical_bytes(record))

    def reset_review(self) -> None:
        shutil.rmtree(self.store.root / ".workline" / "review", ignore_errors=True)

    def work_run(
        self, run_id: str, *, envelope: dict | None = None, set_aside: list[dict] | None = None, work: str = WORK,
        generations: int = 1, consumed: bool = False, bind: bool = True, kind: str = work_review.REVIEW_KIND,
        target: str | None = None,
    ) -> None:
        """A Run's canonical records: its task input, its generations 1..n, its Receipt and Consumption."""
        target = target or work
        operation = work_review.operation_identity(work) if kind == work_review.REVIEW_KIND else "plan:" + target
        task_id = task_id_of(run_id)
        if envelope is None:
            envelope = work_envelope(work, set_aside, run_id)
        task_input = {
            "schema": records.SCHEMA_TASK_INPUT, "version": records.VERSION, "task_id": task_id,
            "task_slot": work_review.TASK_SLOT, "task_kind": work_review.TASK_KIND,
            "reviewer_identity": "reviewer-a", "reviewer_version": "1",
            "request_envelope": envelope, "request_digest": serialize.digest(envelope),
            "candidate_hash": "a" * 64, "reconstruction_mode": records.RECONSTRUCTION_SNAPSHOT,
            "candidate_material_digest": "9" * 64, "review_context_hash": "b" * 64,
            "effective_policy_hash": "c" * 64, "accepted_generation": 1,
        }
        self.put(paths.task_input_rel(task_id), task_input)
        bound = task_input if bind else dict(task_input, reviewer_version="2")
        descriptor = {
            "task_id": task_id, "task_slot": work_review.TASK_SLOT, "task_kind": work_review.TASK_KIND,
            "reviewer_identity": "reviewer-a", "reviewer_version": "1", "candidate_hash": "a" * 64,
            "candidate_material_digest": "9" * 64, "reconstruction_mode": records.RECONSTRUCTION_SNAPSHOT,
            "request_digest": serialize.digest(envelope), "task_input_digest": serialize.digest(bound),
            "review_context_hash": "b" * 64, "effective_policy_hash": "c" * 64,
        }
        settled = [{"task_id": task_id, "status": records.TASK_SETTLED_OK, "result_digest": RESULT_DIGEST,
                    "settled_generation": 2}]
        common = {
            "review_run_id": run_id, "review_kind": kind, "target_identity": target, "operation_identity": operation,
            "accepted_tasks": [descriptor],
        }
        shapes = {
            1: {},
            2: {"settled_tasks": settled},
            3: {"settled_tasks": settled, "status": records.GATE_STATUS_SEALED, "receipt_id": receipt_id_of(run_id),
                "authorized_operation_stage": work_review.AUTHORIZED_OPERATION_STAGE},
            4: {"settled_tasks": settled},
        }
        previous = None
        for generation in range(1, generations + 1):
            record = gate_record(generation, previous_digest=previous, **common, **shapes[generation])
            self.put(paths.gate_rel(run_id, generation), record)
            previous = serialize.digest(record)
        if generations >= 3:
            self.put(paths.receipt_rel(receipt_id_of(run_id)), receipt_record(
                receipt_id=receipt_id_of(run_id), review_run_id=run_id, review_generation=3, review_kind=kind,
                target_identity=target, operation_identity=operation,
                authorized_operation_stage=work_review.AUTHORIZED_OPERATION_STAGE,
            ))
        if consumed:
            self.put(paths.consumption_rel(consumption_id_of(run_id)), consumption_record(
                consumption_id=consumption_id_of(run_id), receipt_id=receipt_id_of(run_id), review_run_id=run_id,
                review_generation=3, review_kind=kind, target_identity=target, operation_identity=operation,
            ))

    def planning_run(self, run_id: str, *, set_aside: list[dict]) -> None:
        envelope = planning.request_envelope(planning.KIND_ROADMAP, {"note": RAW_REQUEST}, {"note": RAW_REQUEST},
                                             set_aside)
        self.work_run(run_id, envelope=envelope, kind=planning.KIND_ROADMAP, target=ROADMAP)

    def entries(self) -> dict[str, dict]:
        review = self.data()["review"]
        self.assertEqual((review["status"], review["runs"]["status"]), ("available", "available"), review)
        return {entry["review_run_id"]: entry for entry in review["runs"]["entries"]}


class SetAsideProjectionTests(SetAsideCase):
    def test_r9_t1_a_valid_version_2_successor_sets_its_predecessor_aside(self) -> None:
        for generations, reason in ((1, "review_context_changed"), (2, "not_authorized"), (3, "set_aside")):
            with self.subTest(predecessor_generations=generations):
                self.reset_review()
                self.work_run(PREDECESSOR, set_aside=None, generations=generations)
                self.work_run(SUCCESSOR, set_aside=aside((PREDECESSOR, reason)))
                entries = self.entries()
                predecessor = entries[PREDECESSOR]
                self.assertEqual(predecessor["state"], "set_aside", predecessor)
                self.assertEqual(
                    (predecessor["review_kind"], predecessor["target_identity"], predecessor["latest_generation"],
                     predecessor["reason"]),
                    (work_review.REVIEW_KIND, WORK, generations, None),
                )

    def test_r9_t2_the_successor_keeps_its_own_state(self) -> None:
        for generations, consumed, expected in ((1, False, "open"), (3, False, "sealed"), (3, True, "consumed")):
            with self.subTest(successor=expected):
                self.reset_review()
                self.work_run(PREDECESSOR, generations=1)
                self.work_run(SUCCESSOR, set_aside=aside((PREDECESSOR, "review_context_changed")),
                              generations=generations, consumed=consumed)
                entries = self.entries()
                self.assertEqual(entries[SUCCESSOR]["state"], expected, entries[SUCCESSOR])
                self.assertIsNone(entries[SUCCESSOR]["reason"])
                self.assertEqual(entries[PREDECESSOR]["state"], "set_aside")

    def test_every_run_a_valid_request_names_is_set_aside_and_names_compose(self) -> None:
        # FOURTH sets aside THIRD; SUCCESSOR, later, sets aside PREDECESSOR and FOURTH: three set aside, one open.
        self.work_run(PREDECESSOR, generations=2)
        self.work_run(THIRD, generations=1)
        self.work_run(FOURTH, set_aside=aside((THIRD, "review_declared_base_changed")), generations=1)
        self.work_run(SUCCESSOR, set_aside=aside((FOURTH, "review_context_changed"), (PREDECESSOR, "not_authorized")))
        states = {run_id: entry["state"] for run_id, entry in self.entries().items()}
        self.assertEqual(states, {PREDECESSOR: "set_aside", THIRD: "set_aside", FOURTH: "set_aside", SUCCESSOR: "open"})

    def test_r9_t3_a_version_1_request_sets_nothing_aside(self) -> None:
        self.work_run(PREDECESSOR, generations=1)
        self.work_run(SUCCESSOR, set_aside=None, generations=1)
        envelope = work_envelope(WORK, None, SUCCESSOR)
        self.assertEqual(envelope["version"], work_review.REQUEST_VERSION_V1)
        self.assertNotIn("set_aside_runs", envelope)
        states = {run_id: entry["state"] for run_id, entry in self.entries().items()}
        self.assertEqual(states, {PREDECESSOR: "open", SUCCESSOR: "open"})

    def test_no_set_aside_from_order_age_or_an_id_mentioned_elsewhere(self) -> None:
        # A version 2 request with an empty list, whose payload mentions the other Run's ID, sets nothing aside;
        # nor does anything about the two Runs' order, age or generation count.
        self.work_run(PREDECESSOR, generations=2)
        self.work_run(SUCCESSOR, envelope=work_envelope(WORK, [], SUCCESSOR, mention=PREDECESSOR), generations=3)
        states = {run_id: entry["state"] for run_id, entry in self.entries().items()}
        self.assertEqual(states, {PREDECESSOR: "open", SUCCESSOR: "sealed"})

    def test_r9_t5_same_run_invalidation_stays_invalidated(self) -> None:
        self.work_run(PREDECESSOR, generations=4)
        self.work_run(SUCCESSOR, set_aside=aside((PREDECESSOR, work_review.INVALIDATION_CLASS_A)), generations=3)
        entries = self.entries()
        self.assertEqual((entries[PREDECESSOR]["state"], entries[PREDECESSOR]["latest_generation"]), ("invalidated", 4))
        self.assertEqual(entries[PREDECESSOR]["receipt"]["status"], "superseded")
        self.assertEqual(entries[SUCCESSOR]["state"], "sealed")

    def test_r9_t6_consumed_stays_consumed(self) -> None:
        self.work_run(PREDECESSOR, generations=3, consumed=True)
        self.work_run(SUCCESSOR, set_aside=aside((PREDECESSOR, "consumed")))
        entries = self.entries()
        self.assertEqual(entries[PREDECESSOR]["state"], "consumed")
        self.assertEqual(entries[PREDECESSOR]["consumption"]["consumption_id"], consumption_id_of(PREDECESSOR))
        self.assertEqual(entries[SUCCESSOR]["state"], "open")

    def test_a_sealed_run_whose_consumption_cannot_be_read_is_never_set_aside(self) -> None:
        self.work_run(PREDECESSOR, generations=3)
        self.work_run(SUCCESSOR, set_aside=aside((PREDECESSOR, "set_aside")))
        broken = self.store.root / paths.consumption_rel(consumption_id_of(FOURTH))
        broken.parent.mkdir(parents=True, exist_ok=True)
        broken.write_bytes(b"schema: nonsense\n")
        entries = self.entries()
        self.assertEqual((entries[PREDECESSOR]["state"], entries[PREDECESSOR]["consumption"]["status"]),
                         ("sealed", "unavailable"))

    def test_a_named_run_whose_own_records_do_not_read_stays_invalid(self) -> None:
        self.work_run(PREDECESSOR, generations=1)
        self.put(paths.gate_rel(PREDECESSOR, 3), gate_record(3, review_run_id=PREDECESSOR))
        self.work_run(SUCCESSOR, set_aside=aside((PREDECESSOR, "review_context_changed")))
        entries = self.entries()
        self.assertEqual((entries[PREDECESSOR]["state"], entries[PREDECESSOR]["reason"]["code"]),
                         ("invalid", "review_gate_chain"))
        self.assertEqual((entries[SUCCESSOR]["state"], entries[SUCCESSOR]["reason"]), ("open", None))

    def test_planning_requests_are_read_by_the_planning_reader(self) -> None:
        # R9 left planning unread (residual R9-1: only a tolerant reader existed). The post-P4 carry adds the
        # fail-closed planning.request_set_aside, so a valid planning request now sets its predecessor aside
        # (class B, test_status_set_aside_classes).
        self.work_run(PREDECESSOR, generations=1, kind=planning.KIND_ROADMAP, target=ROADMAP,
                      envelope=planning.request_envelope(planning.KIND_ROADMAP, {}, {}, []))
        self.planning_run(SUCCESSOR, set_aside=aside((PREDECESSOR, planning.SET_ASIDE_NOT_AUTHORIZED)))
        states = {run_id: entry["state"] for run_id, entry in self.entries().items()}
        self.assertEqual(states, {PREDECESSOR: "set_aside", SUCCESSOR: "open"})


class MalformedLinkageTests(SetAsideCase):
    """R9-T4: a linkage that does not read, or contradicts the namespace, sets nothing aside - never silently."""

    def assert_refused(self, code: str, *, kept: dict[str, str], namer: str = SUCCESSOR) -> dict:
        entries = self.entries()
        entry = entries[namer]
        self.assertEqual(entry["state"], "invalid", entry)
        self.assertEqual(entry["reason"]["code"], code, entry["reason"])
        self.assertIn(namer, entry["reason"]["message"])
        for run_id, state in kept.items():
            self.assertEqual(entries[run_id]["state"], state, entries[run_id])
        self.assertNotIn("set_aside", [found["state"] for found in entries.values()])
        return entry

    def valid_v2(self) -> dict:
        return work_envelope(WORK, aside((PREDECESSOR, "review_context_changed"), (THIRD, "not_authorized")),
                             SUCCESSOR)

    def test_r9_t4_a_request_the_version_reader_refuses(self) -> None:
        unsorted = self.valid_v2()
        unsorted["set_aside_runs"] = list(reversed(unsorted["set_aside_runs"]))
        twice = self.valid_v2()
        twice["set_aside_runs"] = aside((PREDECESSOR, "review_context_changed"), (PREDECESSOR, "not_authorized"))
        extra_key = self.valid_v2()
        extra_key["set_aside_runs"][0] = dict(extra_key["set_aside_runs"][0], note="x")
        no_reason = self.valid_v2()
        no_reason["set_aside_runs"][0] = dict(no_reason["set_aside_runs"][0], reason="Not A Reason")
        not_an_id = self.valid_v2()
        not_an_id["set_aside_runs"][0] = dict(not_an_id["set_aside_runs"][0], review_run_id="rr_nope")
        not_a_list = self.valid_v2()
        not_a_list["set_aside_runs"] = {"review_run_id": PREDECESSOR, "reason": "set_aside"}
        itself = self.valid_v2()
        itself["set_aside_runs"] = aside((SUCCESSOR, "set_aside"), (PREDECESSOR, "set_aside"))  # canonical order
        v1_with_list = work_envelope(WORK, None, SUCCESSOR)
        v1_with_list["set_aside_runs"] = aside((PREDECESSOR, "set_aside"))
        unknown_version = self.valid_v2()
        unknown_version["version"] = RAW_VERSION
        missing_field = self.valid_v2()
        del missing_field["work"]
        not_a_request = dict(self.valid_v2(), schema="review-planning-request")
        for name, envelope in (
            ("unsorted", unsorted), ("twice", twice), ("extra key", extra_key), ("no reason identity", no_reason),
            ("not a review_run id", not_an_id), ("not a list", not_a_list), ("names itself", itself),
            ("version 1 with set_aside_runs", v1_with_list), ("unknown version", unknown_version),
            ("missing field", missing_field), ("not a Work request", not_a_request),
        ):
            with self.subTest(name):
                self.reset_review()
                self.work_run(PREDECESSOR, generations=1)
                self.work_run(THIRD, generations=3)
                self.work_run(SUCCESSOR, envelope=envelope, generations=3)
                entry = self.assert_refused("review_record_invalid", kept={PREDECESSOR: "open", THIRD: "sealed"})
                self.assertIn("version reader", entry["reason"]["message"])

    def test_r9_t4_a_task_input_that_does_not_read_or_is_not_bound(self) -> None:
        self.work_run(PREDECESSOR, generations=1)
        self.work_run(SUCCESSOR, envelope=self.valid_v2(), bind=False)
        self.work_run(THIRD, generations=1)
        self.assert_refused("review_provenance_conflict", kept={PREDECESSOR: "open", THIRD: "open"})
        (self.store.root / paths.task_input_rel(task_id_of(SUCCESSOR))).unlink()
        self.assert_refused("review_record_missing", kept={PREDECESSOR: "open", THIRD: "open"})

    def test_r9_t4_names_that_contradict_the_namespace(self) -> None:
        cases = (
            ("a Run of another Work", lambda: self.work_run(THIRD, work=OTHER_WORK, generations=1), {THIRD: "open"}),
            ("a planning Run", lambda: self.planning_run(THIRD, set_aside=[]), {THIRD: "open"}),
            ("a Run this namespace does not hold", lambda: None, {}),
        )
        for name, make_third, kept in cases:
            with self.subTest(name):
                self.reset_review()
                self.work_run(PREDECESSOR, generations=1)
                make_third()
                named = THIRD if kept else ABSENT
                self.work_run(SUCCESSOR, set_aside=aside((PREDECESSOR, "review_context_changed"), (named, "set_aside")))
                entry = self.assert_refused("review_record_conflict", kept={PREDECESSOR: "open", **kept})
                self.assertIn(named, entry["reason"]["message"])

    def test_r9_t4_a_naming_cycle(self) -> None:
        self.work_run(PREDECESSOR, set_aside=aside((SUCCESSOR, "set_aside")), generations=1)
        self.work_run(SUCCESSOR, set_aside=aside((PREDECESSOR, "set_aside")), generations=3)
        self.work_run(THIRD, set_aside=aside((PREDECESSOR, "set_aside")), generations=1)
        entries = self.entries()
        for run_id in (PREDECESSOR, SUCCESSOR):
            with self.subTest(run_id):
                self.assertEqual((entries[run_id]["state"], entries[run_id]["reason"]["code"]),
                                 ("invalid", "review_record_conflict"))
        self.assertEqual((entries[THIRD]["state"], entries[THIRD]["reason"]), ("open", None))


class SetAsideBoundaryTests(SetAsideCase):
    def fixture(self) -> None:
        self.work_run(PREDECESSOR, generations=3)
        self.work_run(SUCCESSOR, set_aside=aside((PREDECESSOR, "set_aside")), generations=3, consumed=True)
        malformed = work_envelope(WORK, None, THIRD)
        malformed["version"] = RAW_VERSION
        self.work_run(THIRD, envelope=malformed, generations=1)

    def test_r9_t7_no_request_or_reviewer_content_is_emitted(self) -> None:
        self.fixture()
        model = self.model()
        text = status.render_json(model) + status.render_human(model)
        states = {entry["review_run_id"]: entry["state"] for entry in json.loads(status.render_json(model))["review"]["runs"]["entries"]}
        self.assertEqual(states, {PREDECESSOR: "set_aside", SUCCESSOR: "consumed", THIRD: "invalid"})
        self.assertIn("set_aside", status.render_human(model))
        for leaked in (RAW_REQUEST, RAW_VERSION, RESULT_DIGEST, "set_aside_runs", "request_envelope", "instruction",
                       work_review.INSTRUCTION[:40], "reviewer-a"):
            with self.subTest(leaked=leaked):
                self.assertNotIn(leaked, text)

    def test_r9_t8_the_projection_stays_read_only(self) -> None:
        self.fixture()
        root = self.store.root

        def call() -> dict:
            model = status.build_status(root)
            text = status.render_json(model)
            status.render_human(model)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = cli.main(["status", str(root), "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(output.getvalue(), text)
            return json.loads(text)

        data, boundary = self.assertReadOnly(call, root)
        self.assertNotIn("fetch", boundary.git_subcommands())
        states = {entry["review_run_id"]: entry["state"] for entry in data["review"]["runs"]["entries"]}
        self.assertEqual(states[PREDECESSOR], "set_aside")


if __name__ == "__main__":
    import unittest

    unittest.main()
