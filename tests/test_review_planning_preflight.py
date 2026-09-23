"""P2 §28 O: the canonical-input preflight - a caller value the canonical form cannot carry begins nothing."""

from __future__ import annotations

from contextlib import contextmanager
import json
import sys
from typing import Iterator
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, run_python
from planning_helpers import (
    Crash, PlanningTestCase, Reviewer, blob_at, condition, crash_at, design, plan, registered, rr, run_ids, state_entries,
)
from test_review_planning_writer_input import CONDITIONAL, RELATED_YAML, _WriterCase, conditional
from workline import oplock
from workline import roadmap as rm
from workline import yamlish
from workline.errors import StopError, ValidationError
from workline.mutation import MutationController
from workline.phase_create import PhaseSpec
from workline.review import planning, recovery, serialize

BASE = {"kind": "path_glob", "pattern": "src/*.py"}
LONE_SURROGATE = "\ud800"


class _PreflightCase(PlanningTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()
        self.phase_id = rm.create_roadmap(self.store, plan()).phase_ids["a"]

    def entry(self, the_design, reviewer: Reviewer | None = None):
        return self.reviewed_entry(self.store, self.phase_id, reviewer or Reviewer(), the_design)

    @staticmethod
    def entries(store) -> dict:
        """Every entry under .workline, directories included (the execution lock aside): entry for entry, byte for byte."""
        return state_entries(store)

    def assert_refused_with_nothing_begun(self, the_design) -> ValidationError:
        before = self.entries(self.store)
        reviewer = Reviewer()
        with self.assertRaises(ValidationError) as raised:
            self.entry(the_design, reviewer)
        self.assertEqual("review_candidate_unrepresentable", raised.exception.code)
        self.assertIn("cannot be canonicalized", str(raised.exception))
        self.assertEqual(before, self.entries(self.store),
                         "mutations, runtime tmp, reservations, the Review namespace and domain files: entry for entry")
        self.assertEqual([], reviewer.tasks)
        return raised.exception


class RefusalTests(_PreflightCase):
    def test_a_float(self) -> None:
        self.assert_refused_with_nothing_begun(design(related=conditional({**BASE, "weight": 1.5})))

    def test_b_a_tuple(self) -> None:
        self.assert_refused_with_nothing_begun(design(related=conditional({**BASE, "extra": ("a", "b")})))

    def test_c_non_text_keys_at_the_top_and_inside_a_sequence_item(self) -> None:
        for described, cond in {
            "an integer key": {**BASE, 1: "x"},
            "a boolean key": {**BASE, True: "x"},
            "a tuple key": {**BASE, ("a",): "x"},
            "an integer key in a sequence item": {**BASE, "items": [{1: "x"}]},
            "a boolean key in a sequence item": {**BASE, "items": [{True: "x"}]},
            "a tuple key in a sequence item": {**BASE, "items": [{("a",): "x"}]},
        }.items():
            with self.subTest(described):
                error = self.assert_refused_with_nothing_begun(design(related=conditional(cond)))
                self.assertNotIsInstance(error, TypeError)

    def test_values_the_canonical_form_cannot_carry_inside_a_nested_mapping(self) -> None:
        for described, cond in {
            "a float": {**BASE, "nested": {"x": 1.5}},
            "a tuple": {**BASE, "nested": {"x": ("a", "b")}},
            "a non-text key": {**BASE, "nested": {1: "x"}},
            "an empty key": {**BASE, "nested": {"": "x"}},
            "a sequence inside a sequence": {**BASE, "nested": {"x": [["a"]]}},
        }.items():
            with self.subTest(described):
                self.assert_refused_with_nothing_begun(design(related=conditional(cond)))

    def test_d_an_empty_key_directly_in_a_condition(self) -> None:
        self.assert_refused_with_nothing_begun(design(related=conditional({**BASE, "": "x"})))

    def test_d_an_empty_key_inside_a_sequence_item_passes(self) -> None:
        result = self.entry(design(related=conditional({**BASE, "items": [{"": "kept"}]})))
        self.assertEqual("registered", result.status)
        self.assertIn(b"kept", blob_at(self.store, registered(self.store, result).kp, RELATED_YAML))

    def test_e_a_sequence_inside_a_sequence(self) -> None:
        self.assert_refused_with_nothing_begun(design(related=conditional({**BASE, "extra": [["a"]]})))

    def test_j_a_lone_surrogate_in_a_condition_or_a_work_name(self) -> None:
        for described, the_design in {
            "in a condition": design(related=conditional({**BASE, "note": LONE_SURROGATE})),
            "in a Work name": rm.PhaseEntryDesign(
                {"w1": rm.WorkDesign(f"W1 {LONE_SURROGATE}", "W1 が成立する")},
                rm.WorkDesign("Integration", "全Workの統合確認が取れている"), entry="w1",
            ),
        }.items():
            with self.subTest(described):
                self.assert_refused_with_nothing_begun(the_design)


class PassTests(_WriterCase):
    """F, G, H: key order, nested mappings and extra entries pass, and give one Candidate, W, E and result."""

    def _both(self, one: dict, two: dict) -> None:
        first = self.registered_entry("one", design(related=conditional(one)))
        second = self.registered_entry("two", design(related=conditional(two)))
        self.assert_one_writer_input(first, second)
        found = first["found"]
        self.assertEqual(found.consumption.persisted_result["work_ids"],
                         second["found"].consumption.persisted_result["work_ids"], "the same result")

    def test_f_key_order_only(self) -> None:
        self._both(condition("pattern"), condition("kind"))

    def test_g_a_valid_nested_mapping_at_several_depths(self) -> None:
        self._both({**BASE, "scope": {"z": {"b": 1, "a": 2}, "y": [{"k": 1, "j": 2}]}},
                   {"scope": {"y": [{"j": 2, "k": 1}], "z": {"a": 2, "b": 1}}, **BASE})

    def test_h_valid_extra_fields_lose_no_entry(self) -> None:
        one = {**BASE, "note": "text", "count": 3, "flags": [True, None], "meta": {"b": "x", "a": "y"}}
        self._both(one, dict(reversed(list(one.items()))))
        related = self.registered_entry("three", design(related=conditional(one)))["bytes"][RELATED_YAML].decode("utf-8")
        for kept in ("note: text", "count: 3", "- true", "- null", "b: x", "a: y"):
            self.assertIn(kept, related)


class LegacyTests(PlanningTestCase):
    """I: the legacy API keeps the baseline outcomes of §29 item 7, and runs no preflight."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()
        self.phase_id = rm.create_roadmap(self.store, plan()).phase_ids["a"]

    def legacy(self, cond=None, *, the_design=None):
        with mock.patch.object(rr, "require_canonical_input", side_effect=AssertionError("preflight ran")):
            return rm.enter_phase(self.store, self.phase_id, the_design or design(related=conditional(cond)))

    def records(self) -> list[dict]:
        return MutationController(self.store).list_pending()

    def test_a_float_an_empty_key_and_a_nested_sequence_fail_in_save_with_nothing_recorded(self) -> None:
        for described, cond in {"a float": {**BASE, "weight": 1.5}, "an empty key": {**BASE, "": "x"},
                                 "a nested sequence": {**BASE, "extra": [["a"]]}}.items():
            with self.subTest(described):
                with self.assertRaises(yamlish.YamlishError):
                    self.legacy(cond)
                self.assertEqual([], self.records())

    def test_a_non_text_key_fails_in_json_with_nothing_recorded(self) -> None:
        with self.assertRaises(TypeError):
            self.legacy({**BASE, 1: "x"})
        self.assertEqual([], self.records())

    def test_a_lone_surrogate_fails_in_the_utf8_write_and_leaves_a_temporary_file(self) -> None:
        tmp = self.store.root / ".workline" / "runtime" / "tmp"
        before = set(tmp.iterdir()) if tmp.exists() else set()
        with self.assertRaises(UnicodeEncodeError):
            self.legacy({**BASE, "note": LONE_SURROGATE})
        self.assertEqual([], self.records())
        self.assertTrue(set(tmp.iterdir()) - before, "a temporary file is left")

    def test_a_tuple_strands_a_pending_mutation_with_no_effect(self) -> None:
        with self.assertRaises(yamlish.YamlishError):
            self.legacy({**BASE, "extra": ("a", "b")})
        (record,) = self.records()
        self.assertEqual([], record["effects"])
        self.assertNotIn("review_contract", record["invocation"])


class RetryTests(_PreflightCase):
    def test_k_a_pending_valid_mutation_and_the_same_valid_caller_resume(self) -> None:
        the_design = design(related=conditional(condition("kind")))
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.entry(the_design)
        (pending,) = self.pending(self.store)
        result = self.entry(design(related=conditional(condition("kind"))))
        self.assertEqual(("registered", pending["mutation_id"]), (result.status, result.mutation_id))

    def test_l_an_invalid_caller_against_a_pending_mutation_is_refused_and_the_record_untouched(self) -> None:
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.entry(design(related=conditional(condition("kind"))))
        (pending,) = self.pending(self.store)
        path = self.store.mutations / f"{pending['mutation_id']}.yaml"
        before = path.read_bytes()
        self.assert_refused_with_nothing_begun(design(related=conditional({**BASE, "weight": 1.5})))
        self.assertEqual(before, path.read_bytes())


class RecoveryTests(_PreflightCase):
    def setUp(self) -> None:
        super().setUp()
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.entry(design(related=conditional(condition("pattern"))))
        (self.run_id,) = run_ids(self.store)
        self.runtime_gone(self.store)

    def test_m_a_valid_caller_in_another_key_order_recovers_the_same_run(self) -> None:
        result = self.entry(design(related=conditional(condition("kind"))))
        self.assertEqual(("registered", self.run_id), (result.status, result.review_run_id))

    def test_m_an_unrepresentable_caller_is_refused_before_discovery(self) -> None:
        review_before = {k: v for k, v in state_entries(self.store).items() if k.startswith(".workline/review")}
        with mock.patch.object(recovery, "discover", side_effect=AssertionError("discovery ran")):
            self.assert_refused_with_nothing_begun(design(related=conditional({**BASE, "weight": 1.5})))
        self.assertEqual(review_before, {k: v for k, v in state_entries(self.store).items() if k.startswith(".workline/review")})


class SemanticValidationTests(_PreflightCase):
    def test_an_unsupported_condition_kind_is_the_live_refusal_before_open(self) -> None:
        bad = {"kind": "regex", "pattern": "src/.*"}
        before = state_entries(self.store)
        with self.assertRaises(ValidationError) as review_v1:
            self.entry(design(related=conditional(bad)))
        self.assertEqual("validation_failed", review_v1.exception.code)
        self.assertEqual(before, state_entries(self.store), "nothing begun")
        with self.assertRaises(ValidationError) as legacy:
            rm.enter_phase(self.store, self.phase_id, design(related=conditional(bad)))
        self.assertEqual((legacy.exception.code, str(legacy.exception)), (review_v1.exception.code, str(review_v1.exception)))


class OneSerializerTests(_PreflightCase):
    def test_the_preflight_uses_the_p1_serializer(self) -> None:
        seen: list[object] = []
        real = serialize.canonical_data

        def spy(value):
            seen.append(value)
            return real(value)

        with mock.patch.object(serialize, "canonical_data", side_effect=ValidationError("patched", code="review_record_invalid")):
            self.assert_refused_with_nothing_begun(design(related=conditional(condition("kind"))))
        the_design = design(related=conditional(condition("kind")))
        with mock.patch.object(serialize, "canonical_data", spy), crash_at(MutationController, "begin"):
            with self.assertRaises(Crash):
                self.entry(the_design)
        self.assertTrue(seen, "the preflight ran the P1 serializer before anything was begun")
        self.assertEqual(rm.design_identity(the_design), seen[0], "first on the request identity")


# --------------------------------------------------------------------------- §21.3 O10 at the execution lock
#: A legacy call with a lone surrogate in the value its lock description names, run in a child process: the
#: failure leaves the lock held for the rest of that process, and only the process's end releases it.
LEGACY_CHILD = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from workline import oplock
from workline import roadmap as rm
from workline.errors import StopError
from workline.phase_create import PhaseSpec
from workline.store import ProjectStore

store = ProjectStore(Path(sys.argv[2]))
lone = chr(0xD800)
phases = {"a": PhaseSpec("Phase A", "A done")}
the_design = rm.PhaseEntryDesign({"w1": rm.WorkDesign("W1", "W1 done")}, rm.WorkDesign("Integration", "integrated"))
calls = {
    "roadmap-create": lambda: rm.create_roadmap(store, rm.RoadmapPlan("Legacy " + lone, "background", "desired", phases)),
    "phase-entry": lambda: rm.enter_phase(store, sys.argv[3] + lone, the_design),
}
report = {}
try:
    calls[sys.argv[4]]()
    report["first"] = "returned"
except Exception as exc:
    report["first"] = type(exc).__name__
report["held_in_this_process"] = oplock.held_lock(store) is not None
try:
    rm.create_roadmap(store, rm.RoadmapPlan("Next", "background", "desired", phases))
    report["next"] = "returned"
except StopError as exc:
    report["next"] = exc.code
print(json.dumps(report))
"""


class LockHolderTests(PlanningTestCase):
    """§21.3 O10 on the way into the lock (P2-PROD-REVIEW-001).

    The execution lock writes its holder description - diagnostic only - as UTF-8 as soon as it is taken, before
    the block that releases it (``oplock``). A review-v1 caller value placed there that cannot be encoded, a lone
    surrogate, would escape as a raw ``UnicodeEncodeError`` with the lock left held, before the canonical-input
    preflight could refuse it. The review-v1 description therefore names only the static marker; the legacy one
    is unchanged.
    """

    REVIEW_V1_DETAILS = {"review_contract": planning.PLANNING_CONTRACT}

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()
        self.phase_id = rm.create_roadmap(self.store, plan()).phase_ids["a"]

    @contextmanager
    def holders(self) -> Iterator[list[tuple[str, dict]]]:
        """(operation, details) of each holder description, read inside the lock where the operation's code starts."""
        seen: list[tuple[str, dict]] = []
        real = rm._stop_on_structure

        def precheck(store, context):
            if context == "precheck":
                holder = oplock.read_holder(store)
                seen.append((holder["operation"], holder["details"]))
            return real(store, context)

        with mock.patch.object(rm, "_stop_on_structure", precheck):
            yield seen

    def assert_released(self) -> None:
        """No holder and no temporary file left, and this process takes the lock again."""
        self.assertIsNone(oplock.held_lock(self.store))
        self.assertFalse(self.store.lock_holder.exists())
        self.assertEqual([], sorted(path.name for path in self.store.tmp.iterdir()))
        with oplock.project_operation(self.store, "a later operation"):
            pass

    def test_a_lone_surrogate_in_a_roadmap_name_is_the_preflight_refusal(self) -> None:
        before = state_entries(self.store)
        reviewer = Reviewer()
        with self.holders() as seen, self.assertRaises(ValidationError) as raised:
            self.reviewed_roadmap(self.store, reviewer, plan(f"Planned {LONE_SURROGATE} Roadmap"))
        self.assertEqual("review_candidate_unrepresentable", raised.exception.code)
        self.assertIn("cannot be canonicalized", str(raised.exception))
        self.assertEqual([("roadmap-create", self.REVIEW_V1_DETAILS)], seen, "no caller value in the description")
        self.assertEqual(before, state_entries(self.store),
                         "no mutation, reservation, Review record, Roadmap file or runtime file: entry for entry")
        self.assertEqual([], self.pending(self.store))
        self.assertEqual((), run_ids(self.store))
        self.assertEqual([], reviewer.tasks)
        self.assert_released()
        # the next operation takes the lock and runs: a plan whose every value the canonical form carries
        self.assertEqual("registered", self.reviewed_roadmap(self.store, Reviewer(), plan("Another Roadmap")).status)

    def test_a_lone_surrogate_anywhere_else_in_a_roadmap_plan_is_the_same_refusal(self) -> None:
        for described, the_plan in {
            "the background": rm.RoadmapPlan("R", f"背景 {LONE_SURROGATE}", "状態", {"a": PhaseSpec("A", "A")}),
            "the desired state": rm.RoadmapPlan("R", "背景", f"状態 {LONE_SURROGATE}", {"a": PhaseSpec("A", "A")}),
            "the scope": rm.RoadmapPlan("R", "背景", "状態", {"a": PhaseSpec("A", "A")}, scope=f"範囲 {LONE_SURROGATE}"),
            "a Phase name": rm.RoadmapPlan("R", "背景", "状態", {"a": PhaseSpec(f"A {LONE_SURROGATE}", "A")}),
            "a Phase desired state": rm.RoadmapPlan("R", "背景", "状態", {"a": PhaseSpec("A", f"A {LONE_SURROGATE}")}),
        }.items():
            with self.subTest(described):
                before = state_entries(self.store)
                with self.assertRaises(ValidationError) as raised:
                    self.reviewed_roadmap(self.store, Reviewer(), the_plan)
                self.assertEqual("review_candidate_unrepresentable", raised.exception.code)
                self.assertEqual(before, state_entries(self.store))
                self.assert_released()

    def test_a_lone_surrogate_in_a_phase_id_meets_the_live_phase_check(self) -> None:
        """The Phase ID is no part of the request identity (§5.6): it names the slot. The live check that the named
        Phase resolves - §5.6 step 2, which runs in every branch (§5.8) - refuses it, with nothing begun."""
        before = state_entries(self.store)
        reviewer = Reviewer()
        with self.holders() as seen, self.assertRaises(ValidationError) as raised:
            self.reviewed_entry(self.store, self.phase_id + LONE_SURROGATE, reviewer)
        self.assertEqual("validation_failed", raised.exception.code)
        self.assertTrue(str(raised.exception).startswith("Phase unresolvable: "), "the live refusal, unchanged")
        self.assertEqual([("phase-entry", self.REVIEW_V1_DETAILS)], seen, "no caller value in the description")
        self.assertEqual(before, state_entries(self.store))
        self.assertEqual([], self.pending(self.store))
        self.assertEqual([], reviewer.tasks)
        self.assert_released()
        # the next operation takes the lock and runs: the entry of the Phase the caller meant
        self.assertEqual("registered", self.reviewed_entry(self.store, self.phase_id, Reviewer()).status)

    def test_the_legacy_description_is_unchanged(self) -> None:
        with self.holders() as seen:
            rm.create_roadmap(self.store, plan("Legacy Roadmap"))
            rm.enter_phase(self.store, self.phase_id, design())
        self.assertEqual([("roadmap-create", {"name": "Legacy Roadmap"}), ("phase-entry", {"phase_id": self.phase_id})],
                         seen)

    def test_legacy_keeps_its_live_outcome(self) -> None:
        """§5.6 Legacy: a legacy invocation keeps its live outcome, serializer errors included. Its description
        still names the caller's value, so a lone surrogate there fails in the holder's UTF-8 write, leaves a
        temporary file, and holds the lock for the rest of that process; the end of the process releases it."""
        for operation in ("roadmap-create", "phase-entry"):
            with self.subTest(operation):
                tmp_before = set(self.store.tmp.iterdir())
                completed = run_python(
                    [sys.executable, "-I", "-B", "-c", LEGACY_CHILD,
                     str(WORKLINE_ROOT / "src"), str(self.store.root), self.phase_id, operation],
                    cwd=self.store.root,
                )
                reports = [line for line in completed.stdout.splitlines() if line.startswith("{")]
                self.assertTrue(reports, f"the child reported nothing: {completed.stdout}\n{completed.stderr}")
                self.assertEqual(
                    {"first": "UnicodeEncodeError", "held_in_this_process": True, "next": "project_operation_nested"},
                    json.loads(reports[-1]),
                )
                (left,) = set(self.store.tmp.iterdir()) - tmp_before
                self.assertTrue(left.name.startswith(".holder.json."), left.name)
                self.assertEqual([], self.pending(self.store), "no mutation was opened")
                with oplock.project_operation(self.store, "after the child"):
                    pass


if __name__ == "__main__":
    unittest.main()
