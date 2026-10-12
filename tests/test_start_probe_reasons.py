"""RB11 RT-1a: the reason values of an ``unknown_or_invalid`` result are a closed set of exactly six.

Control Plane clarification of RRR-1 (option (b); Sprint §41.29; clarification record §2.2): rev-11
BRIEF §41.3's "no other reason value" is qualified by the values BRIEF §41.5, ADM §A.1 S6.2 and TFI
T-B09 / T-B45 / T-B48 name. The permitted set is the closed union of the six values below - no alias,
no seventh value. An explicitly named value is never collapsed into ``no_read_only_resume_probe``;
every other code a replay or a refusal carries is reported as ``no_read_only_resume_probe``.

* ``ClosedSetTests``: the set itself, and the fail-closed guard (``_closed_reason``).
* ``EmissionSiteTests``: a static reading of ``start_probe.py`` - every site that can give an
  ``unknown_or_invalid`` result passes no code, a constant of the set, or one of the two
  value-dependent forms whose values are proven members.
* ``SixWayTests``: the one place mapping each value to the end-to-end case that triggers it; each
  case is run here, and the value is observed in what the probe actually returned.
* ``NoSeventhValueTests``: replay and refusal codes outside the set give ``no_read_only_resume_probe``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
import unittest
from unittest import mock

from start_probe_helpers import ProbeCase
from workline import start_probe
from workline.errors import ReconcileRequired, StopError, ValidationError, with_check
from workline.mutation import REPLAY_RECONCILE, REPLAY_UNPROVEN, ReplayProbe
from workline.store import ProjectStore

#: The six values, literally, each with the frozen clause that names it (clarification record §2.2).
SIX = frozenset({
    "no_read_only_resume_probe",  # BRIEF §41.3 L239 ("today's no_read_only_resume_probe"); ADM §A.1 S1.1 L191
    "start_operation_not_probed_review_generation",  # BRIEF §41.3 L239-240 (via ADM §A.1 S1.1); ADM §A.1 S1.1 L191
    "start_operation_not_probed_plan_exclusion",  # BRIEF §41.3 L239-240 (via ADM §A.1 S1.1); ADM §A.1 S1.1 L191
    "push_classification_requires_network",  # BRIEF §41.5 L265; TFI T-B45 L258
    "work_commit_replay_not_inspectable",  # BRIEF §41.5 L267; TFI T-B09 L247
    "post_replay_not_read_only",  # ADM §A.1 S6.2 L212; TFI T-B48 L261 (and TFI-F18 L622)
})

#: The six-way mapping: each value, and the end-to-end case (module, class, test) that triggers it.
TRIGGERS: dict[str, tuple[str, str, str]] = {
    "no_read_only_resume_probe": (
        "test_start_probe_flow", "DomainTests",
        "test_t_b05g_an_unknown_operation_keeps_todays_reason_and_is_not_echoed"),
    "start_operation_not_probed_review_generation": (
        "test_start_probe_flow", "DomainTests", "test_t_b05f_a_work_review_generation_record"),
    "start_operation_not_probed_plan_exclusion": (
        "test_start_probe_flow", "DomainTests",
        "test_t_b05e_start_plan_exclusion_records_get_the_fixed_reason_and_never_1552"),
    "push_classification_requires_network": (
        "test_start_probe_flow", "PushTests", "test_t_b45_a_record_holding_a_push_is_never_classified_offline"),
    "work_commit_replay_not_inspectable": (
        "test_start_probe_gates", "ReplayReasonTests", "test_a_work_mode_commit_keeps_its_named_code"),
    "post_replay_not_read_only": (
        "test_start_probe_flow", "ReplayTests", "test_t_b48_an_unapplied_completion_with_its_finalize_commit"),
}

#: End-to-end cases whose replay meets a code that is not one of the six (the last item: a code the unchanged replay
#: gives in the case): each gives no_read_only_resume_probe and no other value.
NOT_NAMED: tuple[tuple[str, str, str, str], ...] = (
    ("test_start_probe_flow", "EnvironmentalReplayTests", "test_an_applied_event_changed_by_someone_else_then_put_back",
     "reconcile_required"),
    ("test_start_probe_gates", "ReplayReasonTests",
     "test_an_environmental_replay_reconcile_is_reported_with_todays_reason", "reconcile_required"),
    ("test_start_probe_gates", "ReplayReasonTests", "test_an_effect_of_an_unknown_kind_is_reported_with_todays_reason",
     "effect_kind_unknown"),
)

#: The constants of start_probe.py that name a member of the set.
CONSTANTS = ("NO_PROBE", "NOT_PROBED_GENERATION", "NOT_PROBED_PLAN_EXCLUSION", "PUSH_NEEDS_NETWORK",
             "WORK_COMMIT_NOT_INSPECTABLE", "POST_REPLAY_NOT_READ_ONLY")


def walk() -> start_probe._Walk:
    return start_probe._Walk(ProjectStore(Path(".")), {"mutation_id": "mut_x", "invocation": {}}, [])


def observe(module: str, cls: str, method: str) -> tuple[unittest.TestResult, list[start_probe.StartProbe], list[str]]:
    """Run one test of another module; its result, every probe answer it got and every replay code the probe met."""
    case = getattr(importlib.import_module(module), cls)(method)
    seen: list[start_probe.StartProbe] = []
    replays: list[str] = []
    real_inspect, real_replay = start_probe.inspect, start_probe.replay_probe

    def spy(*args, **kwargs):
        found = real_inspect(*args, **kwargs)
        seen.append(found)
        return found

    def replay(*args, **kwargs):
        answer = real_replay(*args, **kwargs)
        replays.append(answer.code)
        return answer

    result = unittest.TestResult()
    with mock.patch.object(start_probe, "inspect", spy), mock.patch.object(start_probe, "replay_probe", replay):
        case.run(result)
    return result, seen, replays


def unknown_codes(seen: list[start_probe.StartProbe]) -> set[str]:
    return {found.code for found in seen if found.classification == start_probe.UNKNOWN_OR_INVALID}


class ClosedSetTests(unittest.TestCase):
    def test_the_set_is_exactly_the_six_values(self) -> None:
        self.assertEqual(len(SIX), 6)
        self.assertEqual(start_probe.UNKNOWN_REASONS, SIX)
        self.assertEqual({getattr(start_probe, name) for name in CONSTANTS}, SIX)
        self.assertIn("UNKNOWN_REASONS", start_probe.__all__)

    def test_the_value_dependent_sites_draw_only_from_the_set(self) -> None:
        self.assertEqual(start_probe._NAMED_REPLAY_CODES,
                         {"push_classification_requires_network", "work_commit_replay_not_inspectable"})
        self.assertLessEqual(start_probe._NAMED_REPLAY_CODES, SIX)
        self.assertEqual(set(start_probe._OTHER_OPERATIONS.values()),
                         {"start_operation_not_probed_review_generation", "start_operation_not_probed_plan_exclusion"})
        self.assertLessEqual(set(start_probe._OTHER_OPERATIONS.values()), SIX)

    def test_each_member_is_kept_as_it_is(self) -> None:
        for code in sorted(SIX):
            with self.subTest(code=code):
                found = walk().unknown("S6.1", "a message", code).found
                self.assertEqual((found.classification, found.code), (start_probe.UNKNOWN_OR_INVALID, code))

    def test_a_code_outside_the_set_is_reported_as_no_probe(self) -> None:
        """Fail closed: whatever reaches ``unknown`` outside the six becomes no_read_only_resume_probe."""
        for code in ("reconcile_required", "record_not_replayable", "effect_kind_unknown", "mutation_not_pending",
                     "structure_invalid", "git_error", "a_seventh_value", "No_Read_Only_Resume_Probe",
                     "no_read_only_resume_probe ", "", None, 7):
            with self.subTest(code=code):
                found = walk().unknown("S6.1", "a message", code).found
                self.assertEqual((found.classification, found.code, found.step),
                                 (start_probe.UNKNOWN_OR_INVALID, "no_read_only_resume_probe", "S6.1"))

    def test_the_default_of_unknown_is_no_probe(self) -> None:
        default = inspect.signature(start_probe._Walk.unknown).parameters["code"].default
        self.assertEqual(default, "no_read_only_resume_probe")


class EmissionSiteTests(unittest.TestCase):
    """Every ``unknown_or_invalid`` emission site of start_probe.py, read statically."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tree = ast.parse(Path(start_probe.__file__).read_text(encoding="utf-8"))
        cls.parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(cls.tree):
            for child in ast.iter_child_nodes(node):
                cls.parents[child] = node

    def enclosing(self, node: ast.AST) -> list[ast.AST]:
        chain = []
        while node in self.parents:
            node = self.parents[node]
            chain.append(node)
        return chain

    def guarded_by(self, node: ast.AST, test: str) -> bool:
        return any(isinstance(up, ast.If) and ast.unparse(up.test) == test for up in self.enclosing(node))

    def function_of(self, node: ast.AST) -> ast.FunctionDef:
        return next(up for up in self.enclosing(node) if isinstance(up, ast.FunctionDef))

    def form_of(self, call: ast.Call, code: ast.expr | None) -> str:
        """The form of the code a site passes; anything not listed here fails the test."""
        if code is None:
            return "default"
        if isinstance(code, ast.Name) and code.id in CONSTANTS:
            self.assertIn(getattr(start_probe, code.id), SIX)
            return code.id
        if isinstance(code, ast.Name) and code.id == "fixed":
            # S1.1: bound from _OTHER_OPERATIONS (whose values are members) and passed only when it is one
            self.assertTrue(self.guarded_by(call, "fixed is not None"), ast.unparse(call))
            binds = [node for node in ast.walk(self.function_of(call)) if isinstance(node, ast.Assign)
                     and [ast.unparse(t) for t in node.targets] == ["fixed"]]
            self.assertEqual([ast.unparse(node.value) for node in binds],
                             ["_OTHER_OPERATIONS.get(operation) if isinstance(operation, str) else None"])
            return "fixed"
        if isinstance(code, ast.Attribute) and ast.unparse(code) == "replay.code":
            # S6.1: passed only when it is one of _NAMED_REPLAY_CODES (whose values are members)
            self.assertTrue(self.guarded_by(call, "replay.code in _NAMED_REPLAY_CODES"), ast.unparse(call))
            return "replay.code"
        if isinstance(code, ast.Call) and ast.unparse(code) == "_closed_reason(code)":
            self.assertEqual(self.function_of(call).name, "unknown")
            return "_closed_reason(code)"
        self.fail(f"an unknown_or_invalid site passes a code of an unlisted form: {ast.unparse(call)}")

    def sites(self) -> list[tuple[ast.Call, str]]:
        found = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr == "unknown":
                self.assertEqual(ast.unparse(node.func.value), "self", ast.unparse(node))
                given = [k.value for k in node.keywords if k.arg == "code"]
                code = node.args[2] if len(node.args) > 2 else (given[0] if given else None)
                found.append((node, self.form_of(node, code)))
            elif isinstance(node.func, ast.Name) and node.func.id == "StartProbe":
                self.assertFalse([k for k in node.keywords if k.arg in ("classification", "code")], ast.unparse(node))
                first = node.args[0]
                self.assertIsInstance(first, ast.Name, ast.unparse(node))
                self.assertIn(first.id, ("PENDING_RESUMABLE", "PENDING_RECONCILE", "UNKNOWN_OR_INVALID"))
                if first.id == "UNKNOWN_OR_INVALID":
                    found.append((node, self.form_of(node, node.args[1])))
        return found

    def test_every_site_passes_no_code_or_a_member(self) -> None:
        forms = sorted(form for _, form in self.sites())
        # the two inspect() fallbacks (NO_PROBE), the guard in _Walk.unknown, S1.1 (fixed and default), S6.1 (named
        # and default), S6.2 (two POST_REPLAY_NOT_READ_ONLY) and the default of every other unknown() call
        self.assertEqual(set(forms), {"default", "NO_PROBE", "_closed_reason(code)", "fixed", "replay.code",
                                      "POST_REPLAY_NOT_READ_ONLY"})
        self.assertEqual(forms.count("NO_PROBE"), 2)
        self.assertEqual(forms.count("_closed_reason(code)"), 1)
        self.assertEqual(forms.count("fixed"), 1)
        self.assertEqual(forms.count("replay.code"), 1)
        self.assertEqual(forms.count("POST_REPLAY_NOT_READ_ONLY"), 2)

    def test_the_classification_is_never_given_another_way(self) -> None:
        """UNKNOWN_OR_INVALID is read only as the first argument of a StartProbe, and no StartProbe is copied."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name) and node.id == "UNKNOWN_OR_INVALID" and isinstance(node.ctx, ast.Load):
                call = self.parents[node]
                self.assertTrue(isinstance(call, ast.Call) and ast.unparse(call.func) == "StartProbe"
                                and call.args and call.args[0] is node, ast.unparse(call))
            if isinstance(node, ast.Call):
                self.assertNotIn(ast.unparse(node.func), ("replace", "dataclasses.replace", "copy.copy"))


class SixWayTests(unittest.TestCase):
    """Each value with its triggering case (TRIGGERS), run here and observed in the probe's own answers."""

    def assertTriggers(self, value: str) -> None:
        module, cls, method = TRIGGERS[value]
        result, seen, _ = observe(module, cls, method)
        self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
        self.assertEqual(result.testsRun, 1)
        self.assertIn(value, unknown_codes(seen), f"{cls}.{method}")
        self.assertLessEqual(unknown_codes(seen), SIX)

    def test_the_mapping_names_each_value_once(self) -> None:
        self.assertEqual(set(TRIGGERS), SIX)
        self.assertEqual(len(set(TRIGGERS.values())), 6)

    def test_no_read_only_resume_probe(self) -> None:
        self.assertTriggers("no_read_only_resume_probe")

    def test_start_operation_not_probed_review_generation(self) -> None:
        self.assertTriggers("start_operation_not_probed_review_generation")

    def test_start_operation_not_probed_plan_exclusion(self) -> None:
        self.assertTriggers("start_operation_not_probed_plan_exclusion")

    def test_push_classification_requires_network(self) -> None:
        self.assertTriggers("push_classification_requires_network")

    def test_work_commit_replay_not_inspectable(self) -> None:
        self.assertTriggers("work_commit_replay_not_inspectable")

    def test_post_replay_not_read_only(self) -> None:
        self.assertTriggers("post_replay_not_read_only")


class NoSeventhValueTests(ProbeCase):
    """Codes outside the six - from a replay or from a refusal - are reported as no_read_only_resume_probe."""

    def at_s6_1(self, outcome: str, code: str) -> start_probe.StartProbe:
        """The probe of a record whose every step up to S6.1 passes, with the replay answering ``code``."""
        self.question_wait_record()
        answer = ReplayProbe(outcome, code, f"the replay says {code}")
        with mock.patch.object(start_probe, "replay_probe", return_value=answer) as asked:
            found = self.probe()
        self.assertTrue(asked.called)
        self.assertEqual((found.classification, found.step), (start_probe.UNKNOWN_OR_INVALID, "S6.1"), found)
        return found

    def test_replay_codes_outside_the_set(self) -> None:
        for outcome, code in ((REPLAY_RECONCILE, "reconcile_required"), (REPLAY_UNPROVEN, "record_not_replayable"),
                              (REPLAY_UNPROVEN, "effect_kind_unknown"), (REPLAY_UNPROVEN, "mutation_not_pending"),
                              (REPLAY_UNPROVEN, "git_error"), (REPLAY_UNPROVEN, "a_seventh_value"),
                              (REPLAY_RECONCILE, "post_replay_not_read_only_v2")):
            with self.subTest(code=code):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    found = case.at_s6_1(outcome, code)
                    self.assertEqual(found.code, "no_read_only_resume_probe", found)
                    self.assertNotIn(code, found.message, "the replay's own code is not echoed")
                finally:
                    case.doCleanups()

    def test_the_named_replay_codes_are_kept(self) -> None:
        """The other side of the same site: a named value is never collapsed into no_read_only_resume_probe."""
        for code in ("push_classification_requires_network", "work_commit_replay_not_inspectable"):
            with self.subTest(code=code):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    self.assertEqual(case.at_s6_1(REPLAY_UNPROVEN, code).code, code)
                finally:
                    case.doCleanups()

    def test_a_record_the_replay_cannot_read_end_to_end(self) -> None:
        """record_not_replayable from the unchanged replay itself: a commit effect recorded with no payload."""
        self.question_wait_record()
        self.edit(lambda r: r["effects"].append(
            {"seq": 99, "stage": "stray:0", "kind": "git_commit", "applied": True, "payload": None}))
        real, answers = start_probe.replay_probe, []

        def replay(*args, **kwargs):
            answers.append(real(*args, **kwargs))
            return answers[-1]

        with mock.patch.object(start_probe, "replay_probe", replay):
            found = self.assertUnknown(code="no_read_only_resume_probe")
        self.assertEqual(found.step, "S6.1")
        self.assertEqual({(a.outcome, a.code) for a in answers}, {(REPLAY_UNPROVEN, "record_not_replayable")})

    def test_the_end_to_end_replay_cases_give_no_probe_and_nothing_else(self) -> None:
        for module, cls, method, replay_code in NOT_NAMED:
            with self.subTest(case=f"{cls}.{method}"):
                result, seen, replays = observe(module, cls, method)
                self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
                self.assertIn(replay_code, replays)
                self.assertEqual(unknown_codes(seen), {"no_read_only_resume_probe"})

    def test_refusal_codes_outside_the_set(self) -> None:
        """A refusal that is not admitted carries its own code (here start.2607's structure_invalid among others);
        the reason is no_read_only_resume_probe, whatever that code is."""
        for exc in (with_check(ValidationError("start precheck: x", code="structure_invalid"), "start.2607"),
                    with_check(StopError("x", code="dirty_overlap"), "start.916"),
                    with_check(StopError("x", code="reconcile_required"), "start.2282"),
                    with_check(ReconcileRequired("x: reconcile required"), "start.9999"),
                    KeyError("x")):
            with self.subTest(exc=repr(exc)):
                found = walk().refused("S5.1", exc).found
                self.assertEqual((found.classification, found.code),
                                 (start_probe.UNKNOWN_OR_INVALID, "no_read_only_resume_probe"))


if __name__ == "__main__":
    unittest.main()
