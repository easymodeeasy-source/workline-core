"""A new mutation's FIRST durable save holds its initial notes (RB5 §32.4, IR-A; written by the shared-surface writer).

The CP note-window ruling: a fresh RB5-capable START records ``phase_integration_semantics`` in the same save that
creates its recovery record, so no crash window leaves a record that would resume as legacy. So:

* ``MutationController.open(owner, invocation, scope, *, notes=None)`` and ``begin(..., notes=None)``: a NEW
  mutation's one creating save holds the given JSON-safe notes (a copy, normalized as the invocation is);
* a RESUMED (matched) mutation ignores ``notes``: a resumed note-less record stays note-less, byte for byte;
* ``None`` (every existing caller) saves ``notes: {}`` exactly as before; the method names stay as pinned.
"""

from __future__ import annotations

import copy
import inspect
from unittest import mock

from helpers import WorklineTestCase
from workline import mutation as mutation_module
from workline import oplock, yamlish
from workline.errors import ValidationError
from workline.mutation import Mutation, MutationController, WriteScope
from workline.oplock import project_operation

NOTE = {"phase_integration_semantics": "phase-integration-review-v1"}
INVOCATION = {"operation": "ir-a-test", "n": 1}


class Crash(BaseException):
    """A process death at a chosen instant (never caught by an ``except Exception``)."""


class NotesCase(WorklineTestCase):
    """A Project with its execution lock held, every ``Mutation._save`` recorded."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        lock = project_operation(self.store, "ir-a-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        self.controller = MutationController(self.store)
        self.scope = WriteScope(files=("notes-test.txt",))
        self.saves: list[dict] = []
        original = Mutation._save

        def recording(mutation: Mutation) -> None:
            original(mutation)
            self.saves.append(copy.deepcopy(mutation.record))

        Mutation._save = recording  # type: ignore[method-assign]
        self.addCleanup(setattr, Mutation, "_save", original)

    def stored(self, mutation: Mutation) -> bytes:
        return self.controller.intent_path(mutation.id).read_bytes()


class InitialNotesTests(NotesCase):

    def test_the_first_save_of_a_new_mutation_already_holds_the_notes(self) -> None:
        mutation = self.controller.open("start", INVOCATION, self.scope, notes=NOTE)
        self.assertEqual(1, len(self.saves), "one creating save, and no second save for the note")
        self.assertEqual(NOTE, self.saves[0]["notes"])
        self.assertEqual(NOTE["phase_integration_semantics"], mutation.note("phase_integration_semantics"))
        self.assertEqual(NOTE, self.controller.load(mutation.id).record["notes"], "durable as saved")

    def test_begin_takes_the_same_notes(self) -> None:
        mutation = self.controller.begin("start", INVOCATION, self.scope, notes=NOTE)
        self.assertEqual([NOTE], [save["notes"] for save in self.saves])
        self.assertEqual(NOTE, self.controller.load(mutation.id).record["notes"])

    def test_a_resumed_mutation_ignores_the_notes_and_stays_as_it_recorded(self) -> None:
        legacy = self.controller.open("start", INVOCATION, self.scope)
        before = self.stored(legacy)
        self.saves.clear()
        resumed = self.controller.open("start", INVOCATION, self.scope, notes=NOTE)
        self.assertEqual(legacy.id, resumed.id)
        self.assertIsNone(resumed.note("phase_integration_semantics"), "a resumed note-less START stays legacy")
        self.assertEqual({}, resumed.record["notes"])
        self.assertEqual([], self.saves, "resuming saves nothing")
        self.assertEqual(before, self.stored(resumed))

    def test_a_resumed_noted_mutation_keeps_its_own_notes(self) -> None:
        first = self.controller.open("start", INVOCATION, self.scope, notes=NOTE)
        before = self.stored(first)
        resumed = self.controller.open("start", INVOCATION, self.scope, notes={"phase_integration_semantics": "x"})
        self.assertEqual(NOTE, resumed.record["notes"])
        self.assertEqual(before, self.stored(resumed))

    def test_no_notes_is_every_existing_callers_record_exactly(self) -> None:
        default = self.controller.open("start", INVOCATION, self.scope)
        explicit = self.controller.begin("start", {"operation": "ir-a-test", "n": 2}, self.scope, notes=None)
        for found in (default, explicit):
            with self.subTest(mutation=found.id):
                self.assertEqual({}, found.record["notes"])
        self.assertEqual([{}, {}], [save["notes"] for save in self.saves])
        # RB5PSWA-3: the frozen record key order, as a literal - not another product of the same code path
        self.assertEqual(["workline", "version", "mutation_id", "owner", "status", "created_at", "updated_at",
                          "invocation", "write_scope", "reserved_ids", "notes", "effects"], list(default.record))
        self.assertEqual(list(default.record), list(explicit.record))

    def test_without_notes_open_calls_begin_exactly_as_before(self) -> None:
        """Existing doubles of ``begin(self, owner, invocation, scope)`` (test_project_start_recovery) still fit."""
        original = MutationController.begin
        calls: list[tuple] = []

        def begin(controller, owner, invocation, scope):
            calls.append((owner, invocation))
            return original(controller, owner, invocation, scope)

        with mock.patch.object(MutationController, "begin", begin):
            found = self.controller.open("start", INVOCATION, self.scope)
        self.assertEqual([("start", INVOCATION)], calls)
        self.assertEqual({}, found.record["notes"])

    def test_the_notes_are_a_json_safe_copy_never_the_callers_object(self) -> None:
        given = {"phase_integration_semantics": "phase-integration-review-v1", "nested": {"b": [1, True, None]}}
        mutation = self.controller.open("start", INVOCATION, self.scope, notes=given)
        given["nested"]["b"].append("later")
        given["added"] = 1
        self.assertEqual({"phase_integration_semantics": "phase-integration-review-v1", "nested": {"b": [1, True, None]}},
                         self.controller.load(mutation.id).record["notes"])

    def test_notes_the_record_cannot_hold_are_refused_before_anything_is_saved(self) -> None:
        """RB5PSWA-1 / -2: the declared boundary is the record's own (RB10 N3(b), input_validation.require_durable),
        asserted against ``_initial_notes`` itself and against ``begin`` / ``open`` - by the exact refusal type, never
        a ValueError superclass a raw ``YamlishError`` out of the save would also satisfy - and nothing is saved."""
        cases = (
            ("not a mapping", [("x", 1)], TypeError),
            ("a non-text key", {1: "x"}, ValidationError),  # RB5PSWB-1: classified at every depth, the top included
            ("an empty key", {"": "x"}, ValidationError),
            ("a value JSON cannot carry", {"x": object()}, ValidationError),
            ("NaN", {"x": float("nan")}, ValidationError),
            ("a float", {"x": 1.5}, ValidationError),
            ("a sequence inside a sequence", {"x": [[1]]}, ValidationError),
            ("a nested non-text key", {"x": {1: "y"}}, ValidationError),
            ("a nested empty key", {"x": {"": "y"}}, ValidationError),
            ("a tuple", {"x": (1, 2)}, ValidationError),
            ("a lone surrogate value", {"x": "\ud800"}, ValidationError),
            ("a lone surrogate key", {"\ud800": "x"}, ValidationError),
        )
        for name, bad, expected in cases:
            with self.subTest(name):
                with self.assertRaises(Exception) as direct:
                    mutation_module._initial_notes(bad)
                self.assertIs(expected, type(direct.exception), f"_initial_notes itself refuses: {direct.exception!r}")
                if expected is ValidationError:
                    self.assertEqual("input_unrepresentable", direct.exception.code)
                invocation = {"operation": "ir-a-bad", "case": name}
                for call in (lambda: self.controller.begin("start", invocation, self.scope, notes=bad),
                             lambda: self.controller.open("start", invocation, self.scope, notes=bad)):
                    with self.assertRaises(Exception) as raised:
                        call()
                    self.assertIs(expected, type(raised.exception), repr(raised.exception))
                    if expected is ValidationError:
                        self.assertEqual("input_unrepresentable", raised.exception.code)
        self.assertEqual([], self.saves, "a refused note saves nothing")
        self.assertEqual([], MutationController(self.store).list_pending(), "and leaves no record")
        self.assertEqual([], [path.name for path in self.store.mutations.glob("*.yaml")])

    def test_the_signatures_add_one_keyword_only_parameter_and_no_method(self) -> None:
        for method in (MutationController.open, MutationController.begin):
            with self.subTest(method=method.__name__):
                parameters = inspect.signature(method).parameters
                self.assertEqual(["self", "owner", "invocation", "scope", "notes"], list(parameters))
                self.assertEqual(inspect.Parameter.KEYWORD_ONLY, parameters["notes"].kind)
                self.assertIsNone(parameters["notes"].default)
        self.assertEqual(
            {name for name in vars(MutationController) if not name.startswith("_")},
            {"intent_path", "list_records", "list_pending", "load", "require_execution_lock", "open", "begin",
             "validate_effect", "classify", "apply_effect"},
        )


class InitialNotesInterruptionTests(NotesCase):
    """CP set-B §12: no crash window in which a fresh noted operation is durable without its notes."""

    def test_the_very_first_durable_write_of_the_owner_record_holds_the_notes(self) -> None:
        writes: list[tuple[str, dict]] = []
        original = mutation_module.durable_write_text

        def recording(path, text, **kwargs):
            if path.parent == self.store.mutations:
                writes.append((path.name, yamlish.load(text)))
            return original(path, text, **kwargs)

        with mock.patch.object(mutation_module, "durable_write_text", side_effect=recording):
            found = self.controller.open("start", INVOCATION, self.scope, notes=NOTE)
        self.assertEqual([f"{found.id}.yaml"], [name for name, _ in writes], "the record is written once, and first")
        self.assertEqual(NOTE, writes[0][1]["notes"])

    def test_a_death_right_after_the_first_save_resumes_with_the_notes(self) -> None:
        with mock.patch.object(oplock, "note_mutation", side_effect=Crash("after the first save")):
            with self.assertRaises(Crash):
                self.controller.open("start", INVOCATION, self.scope, notes=NOTE)
        [pending] = MutationController(self.store).list_pending()
        self.assertEqual(NOTE, pending["notes"])
        resumed = MutationController(self.store).open("start", INVOCATION, self.scope)
        self.assertEqual(pending["mutation_id"], resumed.id)
        self.assertEqual(NOTE["phase_integration_semantics"], resumed.note("phase_integration_semantics"),
                         "never resumed as legacy")

    def test_a_death_inside_the_first_durable_write_leaves_no_record(self) -> None:
        with mock.patch.object(mutation_module, "durable_write_text", side_effect=Crash("inside the first write")):
            with self.assertRaises(Crash):
                self.controller.open("start", INVOCATION, self.scope, notes=NOTE)
        self.assertEqual([], MutationController(self.store).list_pending(), "absent, or noted - never note-less")

    def test_no_path_persists_a_new_owner_record_before_its_notes(self) -> None:
        begin = inspect.getsource(MutationController.begin)
        self.assertEqual(1, begin.count("._save()"), "begin saves once")
        self.assertLess(begin.index('"notes":'), begin.index("._save()"), "the notes are in the record it saves")
        opening = inspect.getsource(MutationController.open)
        self.assertNotIn("_save(", opening, "open persists only through begin")
        self.assertNotIn("_save(", inspect.getsource(Mutation.__init__))
