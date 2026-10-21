"""field-feedback item 2 (core side): a mutation-overlap refusal is a guard working as designed, and says why and what is safe.

The refusal itself - and what it refuses - is unchanged; only its message now names the overlapping scope and the
ways forward the contract provides, so nobody reaches for a plain Git commit around it.
"""

from __future__ import annotations

from helpers import WorklineTestCase
from test_mutation import SCOPE
from workline.errors import ReconcileRequired
from workline.mutation import MutationController, WriteScope
from workline.oplock import project_operation


class OverlapDiagnosisTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.controller = MutationController(self.store)
        lock = project_operation(self.store, "mutation-controller-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)

    def test_the_refusal_names_the_overlap_and_the_formal_ways_forward(self) -> None:
        self.controller.open("roadmap", {"operation": "phase-entry", "phase_id": "p_x"}, SCOPE)
        with self.assertRaises(ReconcileRequired) as raised:
            self.controller.open("start", {"operation": "start", "work_id": "w_x"}, SCOPE)
        message = raised.exception.message
        self.assertIn("overlaps the planned write scope: reconcile required", message, "the refusal is unchanged")
        for shared in SCOPE.entities + SCOPE.files:
            self.assertIn(shared, message)
        for way in ("working as designed", "route the contract provides for its owner", ".workline/runtime"):
            self.assertIn(way, message)
        # RB11INT-C-1: no owner is told to "resume" what the contract does not let it resume, and the START hint is
        # given only when the record that holds the scope is a START
        self.assertNotIn("resume or finish", message)
        self.assertNotIn("Human decision", message)
        # AM-C2: the text never recommends a recovery route the contract does not provide for the owner of that record
        # (the dispose-recovery gate admits no owner of this kind), so it names none.
        self.assertNotIn("dispose-recovery", message)

    def test_a_pending_start_names_the_decision_that_continues_it_and_no_other_owner_does(self) -> None:
        self.controller.open("start", {"operation": "start", "work_id": "w_x"}, SCOPE)
        with self.assertRaises(ReconcileRequired) as raised:
            self.controller.open("roadmap", {"operation": "phase-entry", "phase_id": "p_x"}, SCOPE)
        message = raised.exception.message
        self.assertIn("a START waiting on a Human decision continues once the decision is supplied", message)
        self.assertIn("overlaps the planned write scope: reconcile required", message)

    def test_an_unbounded_pending_scope_is_named_as_such(self) -> None:
        self.controller.open("roadmap", {"operation": "x"}, WriteScope())
        with self.assertRaises(ReconcileRequired) as raised:
            self.controller.open("start", {"operation": "y"}, SCOPE)
        self.assertIn("its scope is unbounded", raised.exception.message)

    def test_a_truly_independent_scope_still_does_not_block(self) -> None:
        self.controller.open("roadmap", {"operation": "x"}, WriteScope(entities=("p_a",), files=("a",)))
        self.controller.open("start", {"operation": "y"}, WriteScope(entities=("w_b",), files=("b",)))
