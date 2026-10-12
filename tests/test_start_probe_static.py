"""RB11 RT-1a static rows: T-B40 (check IDs, rendered fields byte-equal), the ALLOW list, the probe's own surface.

T-B40 (rev-11 TFI §B.1; PO-45): every raising call of start.py, and of the ops.py
helpers START passes ``refuse`` to (``_recorded_stages``, ``_recorded_progress``),
carries a check ID attached after construction - ``raise with_check(<expr>, "<id>")`` -
with no constructor or factory signature change; the exception expression of
every call is the base's exactly (so its message, ``code``, ``reason`` and
``str(exc)`` are), except the one T-01 / T-02 wording correction (PO-12); every
ALLOW ID names a class-R call of ADM §A.2 in the reader it belongs to; and
Roadmap's and START's plan exclusion, which share ``ops._refusal``, raise exactly
what they raised before.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
import unittest
from unittest import mock

from helpers import WorklineTestCase
from rb11_raise_base import BASE_RAISES
from workline import errors, ops, start as st, start_probe
from workline.errors import (
    GitError, ProjectOperationBusy, ReconcileRequired, SpecViolation, StopError, ValidationError, with_check,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "workline"
START = SRC / "start.py"
OPS = SRC / "ops.py"
OPS_HELPERS = ("_recorded_stages", "_recorded_progress")
OPS_IDS = {"ops.832", "ops.851", "ops.853", "ops.857", "ops.863"}

#: ADM §A.2 (rev-11, frozen), restated independently: the ALLOW calls by step, and the reader each lives in.
ADM_ALLOW = {
    "S3.4": ({"start.2274", "ops.832", "start.2278", "start.2282", "start.2298", "start.2305", "start.2309",
              "start.2312", "start.2314", "start.2318", "start.2454", "start.2457", "start.2463", "start.2471",
              "start.2477", "start.2488", "start.2495", "start.2504", "start.2510", "start.2518", "start.2542",
              "start.2544", "start.2547", "start.2550", "start.2557", "start.2568"},
             {"_read_cancel_record", "_prove_cancel", "reserved_id"}),
    "S5.1": ({"start.1530", "start.1540", "start.1552"}, {"_completion_to_finish"}),
    "S5.2": ({"start.2750", "start.2758", "ops.832", "start.2767", "start.2769", "start.2774", "start.2784",
              "start.2786", "start.2788", "start.2793", "start.2800", "start.2811", "start.2817"}, {"_hold_to_finish"}),
    "S5.3": ({"start.3002", "start.3010", "start.3021", "ops.832", "start.3027", "start.3030", "start.3033",
              "start.3038", "start.3053.between"}, {"_derivations_to_reuse"}),
    "S5.4": ({"ops.832", "start.3260", "start.3274", "start.3281"}, {"_derive_move_to_finish"}),
    "S7.3": ({"start.900"}, {"_refused_result"}),
}
#: ADM §A.2 / §41.5: the calls that are never on the allowlist (V / H / FS / I / RS), whatever factory they share.
ADM_EXCLUDED = {
    "start.2461", "start.2465", "start.2573", "start.2601", "start.2611", "start.2217", "start.1546", "start.2830",
    "start.2832", "start.3053.uncommitted", "start.3271", "start.3283", "start.3431", "start.3455", "start.3787",
    "start.3710", "start.920", "start.3512", "ops.851", "ops.853", "ops.857", "ops.863",
}
#: The T-01 / T-02 correction (PO-12 adopted): the only exception expression whose text differs from the base.
CORRECTED = "start.3512"
OLD_CLAUSE = "which that classifier does not prove for a START record"
NEW_CLAUSE = "which that classifier does not prove for this record, because this refusal depends on the Project's current state"


def _raises(path: Path) -> list[tuple[ast.Raise, str | None]]:
    """Every ``raise <expr>`` of ``path`` with the function it is in."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[ast.Raise, str | None]] = []

    def visit(node: ast.AST, function: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
            else:
                if isinstance(child, ast.Raise) and child.exc is not None:
                    found.append((child, function))
                visit(child, function)

    visit(tree, None)
    return found


def _wrapped(node: ast.Raise) -> tuple[ast.expr, list[str]]:
    """The exception expression inside ``with_check(...)`` and the check ID(s) it is given."""
    call = node.exc
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "with_check", \
        f"line {node.lineno}: not raised through with_check"
    assert len(call.args) == 2 and not call.keywords, f"line {node.lineno}: with_check(<exception>, <id>) exactly"
    inner, given = call.args
    if isinstance(given, ast.Constant) and isinstance(given.value, str):
        return inner, [given.value]
    assert isinstance(given, ast.IfExp) and all(isinstance(side, ast.Constant) for side in (given.body, given.orelse)), \
        f"line {node.lineno}: a check ID is a literal, or a branch between two literals"
    return inner, [given.body.value, given.orelse.value]


def _base_dump(check: str) -> str:
    return ast.dump(ast.parse(BASE_RAISES[check], mode="eval").body)


class CheckIdTests(unittest.TestCase):
    """T-B40: identity by check ID, attached after construction, nothing rendered changed."""

    def start_sites(self) -> dict[str, tuple[ast.expr, str | None]]:
        sites: dict[str, tuple[ast.expr, str | None]] = {}
        for node, function in _raises(START):
            inner, ids = _wrapped(node)
            for check in ids:
                self.assertNotIn(check, sites, f"check ID {check} used twice")
                sites[check] = (inner, function)
        return sites

    def test_every_raising_call_of_start_carries_a_check_id_and_raises_the_base_exception(self) -> None:
        sites = self.start_sites()
        base_start = {key for key in BASE_RAISES if key.startswith("start.")}
        named = {check if not check.startswith("start.3053.") else "start.3053" for check in sites}
        self.assertEqual(named, base_start, "one check ID per raising call of the base, and no other")
        for check, (inner, _function) in sites.items():
            base = check if not check.startswith("start.3053.") else "start.3053"
            with self.subTest(check=check):
                if check == CORRECTED:
                    continue
                self.assertEqual(ast.dump(inner), _base_dump(base), "the exception expression changed")

    def test_the_t01_t02_correction_changes_the_wording_alone(self) -> None:
        inner, _ = self.start_sites()[CORRECTED]
        source = ast.unparse(inner)
        base = ast.unparse(ast.parse(BASE_RAISES[CORRECTED], mode="eval").body)
        self.assertIn(OLD_CLAUSE.split(" for ")[0], base)
        self.assertNotIn(OLD_CLAUSE, source)
        self.assertEqual(ast.dump(ast.parse(base.replace(  # the clause swapped back gives the base exactly
            "which that classifier does not prove for a START record: reconcile required",
            NEW_CLAUSE + ": reconcile required"), mode="eval").body).replace("\\'", "'"),
            ast.dump(ast.parse(source, mode="eval").body).replace("\\'", "'"))
        call = inner
        self.assertEqual(call.func.id, "ReconcileRequired")
        self.assertEqual(ast.unparse([k for k in call.keywords if k.arg == "reason"][0].value),
                         "CODE_WORK_REVIEW_CLOSES_REVIEWED_PHASE", "reason unchanged")

    def test_the_two_ops_helpers_carry_their_check_ids_and_nothing_else_in_ops_changed_its_raises(self) -> None:
        wrapped = {}
        for node, function in _raises(OPS):
            call = node.exc
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "with_check":
                inner, ids = _wrapped(node)
                self.assertIn(function, OPS_HELPERS, f"ops.py line {node.lineno}: a check ID outside the two helpers")
                for check in ids:
                    wrapped[check] = inner
            else:
                self.assertNotIn(function, OPS_HELPERS, f"ops.py line {node.lineno}: a helper raise without an ID")
        self.assertEqual(set(wrapped), OPS_IDS)
        for check, inner in wrapped.items():
            with self.subTest(check=check):
                self.assertEqual(ast.dump(inner), _base_dump(check))

    def test_no_constructor_or_factory_signature_changed(self) -> None:
        self.assertEqual(list(inspect.signature(ops._refusal).parameters), ["record", "described"])
        self.assertEqual(list(inspect.signature(st._cancel_refusal).parameters), ["record"])
        self.assertEqual(list(inspect.signature(st._hold_refusal).parameters), ["mutation"])
        self.assertEqual(list(inspect.signature(st._derivation_refusal).parameters), ["mutation"])
        self.assertEqual(list(inspect.signature(st._move_finalization_refusal).parameters),
                         ["mutation", "move", "stage", "message"])
        self.assertEqual(list(inspect.signature(ReconcileRequired).parameters), ["message", "reason"])
        self.assertEqual(list(inspect.signature(StopError).parameters), ["message", "code"])

    def test_with_check_renders_nothing(self) -> None:
        for build in (lambda: ReconcileRequired("a reconcile: reconcile required"),
                      lambda: ReconcileRequired("planning", reason="review_marker_mismatch"),
                      lambda: StopError("stop", code="x"), lambda: ValidationError("bad"), lambda: SpecViolation("no"),
                      lambda: GitError("git"), lambda: ProjectOperationBusy("busy", {"pid": 1}), lambda: KeyError("k")):
            plain, checked = build(), with_check(build(), "start.0")
            with self.subTest(type=type(plain).__name__):
                self.assertIs(type(checked), type(plain))
                self.assertEqual((str(checked), repr(checked), checked.args), (str(plain), repr(plain), plain.args))
                for attribute in ("message", "code", "reason", "holder"):
                    self.assertEqual(getattr(checked, attribute, None), getattr(plain, attribute, None))
                self.assertEqual(checked.check_id, "start.0")
                self.assertFalse(hasattr(plain, "check_id"))

    def test_errors_adds_only_the_helper(self) -> None:
        tree = ast.parse((SRC / "errors.py").read_text(encoding="utf-8"))
        functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
        self.assertEqual(functions, {"with_check", "implementation_error"})
        self.assertEqual(classes, ["WorklineError", "StopError", "ReconcileRequired", "ValidationError", "SpecViolation",
                                   "GitError", "ProjectOperationBusy", "ProjectOperationNested", "ForeignProjectMutation",
                                   "SelfHostingUnsupported", "PythonUnsupported", "ImplementationUnverified",
                                   "ImplementationMismatch"])
        (helper,) = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "with_check"]
        assigns = [node for node in ast.walk(helper) if isinstance(node, ast.Assign)]
        self.assertEqual([ast.unparse(node) for node in assigns], ["exc.check_id = check_id"], "one attribute, set")


class AllowListTests(unittest.TestCase):
    """Every ALLOW ID maps to a class-R call of ADM §A.2, in the reader of its step; none is an excluded call."""

    def test_the_allow_list_is_adm_a2_exactly(self) -> None:
        self.assertEqual({step: set(ids) for step, ids in start_probe.ALLOW.items()},
                         {step: ids for step, (ids, _) in ADM_ALLOW.items()})

    def test_each_allow_id_is_a_raising_call_of_the_reader_of_its_step(self) -> None:
        where: dict[str, set[str | None]] = {}
        for node, function in _raises(START):
            for check in _wrapped(node)[1]:
                where.setdefault(check, set()).add(function)
        for node, function in _raises(OPS):
            call = node.exc
            if isinstance(call, ast.Call) and getattr(call.func, "id", None) == "with_check":
                for check in _wrapped(node)[1]:
                    where.setdefault(check, set()).add(function)
        for step, (ids, readers) in ADM_ALLOW.items():
            for check in ids:
                with self.subTest(step=step, check=check):
                    expected = {"_recorded_stages"} if check == "ops.832" else readers
                    self.assertTrue(where.get(check), f"{check} is no raising call")
                    self.assertLessEqual(where[check], expected)

    def test_no_allow_id_is_an_excluded_call(self) -> None:
        allowed = set().union(*start_probe.ALLOW.values())
        self.assertEqual(allowed & ADM_EXCLUDED, set())


class ProbeSurfaceTests(unittest.TestCase):
    """The probe module: it lists no pending records, opens nothing, never enters hermetic, never runs an executor."""

    SOURCE = (SRC / "start_probe.py").read_text(encoding="utf-8")

    def calls(self) -> set[str]:
        return {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                for node in ast.walk(ast.parse(self.SOURCE)) if isinstance(node, ast.Call)}

    def test_it_names_no_write_lock_open_list_or_hermetic_entry(self) -> None:
        calls = self.calls()
        for forbidden in ("list_pending", "list_records", "open", "begin", "apply", "add_effects", "reserve_id",
                          "complete", "abandon", "_save", "apply_effect", "project_operation", "note_mutation",
                          "durable_write_text", "write_text", "write_bytes", "mkdir", "unlink", "enter", "read_only",
                          "finalize", "commit_stage", "_commit", "_lifecycle", "start", "executor", "set_note",
                          "extend_scope"):
            with self.subTest(call=forbidden):
                self.assertNotIn(forbidden, calls)
        imported: set[str] = set()
        for node in ast.walk(ast.parse(self.SOURCE)):
            if isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        for forbidden in ("hermetic", "review.hermetic", "start_integration_review", "start_review", "oplock",
                          "durable", "history"):
            with self.subTest(imported=forbidden):
                self.assertNotIn(forbidden, imported)

    def test_the_read_only_mutation_refuses_every_write_path(self) -> None:
        mutation = start_probe._ProbeMutation(mock.Mock(store=None, intent_path=lambda m: Path("x")),
                                              {"mutation_id": "mut_x", "owner": "start", "status": "pending",
                                               "invocation": {}, "write_scope": {"entities": [], "files": []},
                                               "effects": []}, resumed=True)
        for name, args in (("reserve_id", ("k", "work")), ("add_effects", ("s", [])), ("apply", ()),
                           ("complete", ()), ("abandon", ()), ("_save", ())):
            with self.subTest(write=name), self.assertRaises(start_probe._ProbeWouldWrite):
                getattr(mutation, name)(*args)
        self.assertFalse(issubclass(start_probe._ProbeWouldWrite, StopError), "never taken for a refusal")


class PlanExclusionUnchangedTests(WorklineTestCase):
    """T-B40: Roadmap's and START's plan exclusion share ops._refusal and raise exactly today's exception."""

    def test_ops_refusal_builds_todays_exception(self) -> None:
        refuse = ops._refusal({"mutation_id": "mut_x"}, "plan exclusion of w_x")
        built = refuse("a reason")
        self.assertEqual(type(built), ReconcileRequired)
        self.assertEqual(str(built), "the unfinished plan exclusion of w_x mut_x was recorded for this request, but its "
                         "record holds a reason; nothing shows that continuing it carries out this request, and it is "
                         "left untouched: reconcile required")
        self.assertEqual((built.code, built.reason), ("reconcile_required", None))
        self.assertFalse(hasattr(built, "check_id"), "the factory attaches nothing: the raise site does")
        with self.assertRaises(ReconcileRequired) as raised:
            ops._recorded_stages([{"stage": "a"}, {"stage": "b"}, {"stage": "a"}], refuse)
        self.assertEqual(raised.exception.check_id, "ops.832")
        self.assertEqual(str(raised.exception), str(refuse("stage 'a' recorded in two places")))

    def test_roadmap_and_start_plan_exclusion_resume_refuse_as_before(self) -> None:
        import re
        from start_probe_helpers import Interrupted
        from workline import roadmap as rm, yamlish
        from workline.create import WorkSpec, create_standalone_work
        from workline.mutation import MutationController
        from workline.ops import Replan

        from workline.state import ProjectView

        def roadmap_case():
            store = self.new_project("roadmap-owned")
            roadmap = self.simple_roadmap(store)
            entry = self.simple_entry(store, roadmap.phase_ids["a"], {"w1": "W1", "w2": "W2"})
            (into,) = [r.id for r in ProjectView.load(store).roadmap_relations
                       if (r.type, r.from_id, r.to) == ("requires_completion", entry.work_ids["w2"], entry.integration_id)]
            return store, lambda: rm.plan_exclude_work(store, entry.work_ids["w2"], Replan(remove_relation_ids=(into,)))

        def start_case():
            store = self.new_project("start-owned")
            standalone = create_standalone_work(store, WorkSpec("S", "s")).work_id
            return store, lambda: st.plan_exclude_standalone_work(store, standalone, Replan())

        for label, case in (("roadmap", roadmap_case), ("start", start_case)):
            with self.subTest(owner=label):
                store, call = case()
                stop = Interrupted("before finalize")
                with mock.patch.object(st.gitops, "finalize", side_effect=stop), \
                        mock.patch.object(rm.gitops, "finalize", side_effect=stop):
                    with self.assertRaises(Interrupted):
                        call()
                (record,) = MutationController(store).list_pending()
                record["effects"].append(dict(record["effects"][0], stage="stray"))
                record["effects"].append(dict(record["effects"][0]))
                path = store.mutations / f"{record['mutation_id']}.yaml"
                path.write_text(yamlish.dump(record), encoding="utf-8", newline="\n")
                with self.assertRaises(ReconcileRequired) as raised:
                    call()
                self.assertEqual(raised.exception.check_id, "ops.832")
                self.assertIsNone(raised.exception.reason)
                self.assertTrue(re.fullmatch(
                    r"the unfinished plan exclusion of \S+ mut_\w+ was recorded for this request, but its record holds "
                    r"stage 'event' recorded in two places; nothing shows that continuing it carries out this request, "
                    r"and it is left untouched: reconcile required", str(raised.exception)), str(raised.exception))


if __name__ == "__main__":
    unittest.main()
