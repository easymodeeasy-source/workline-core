"""An operation declares the canonical files it can write, not every file there is (BL-017).

A mutation's declared write scope is what decides whether an interrupted
operation and a new one are independent: a pending mutation that is not provably
independent of the planned scope stops the new operation as ``reconcile
required``. Every Roadmap operation used to declare all three shared ledgers -
Roadmap relations, Related relations and the event log - whatever it actually
wrote, so operations that never touch the same file looked like a conflict. A
Phase put on hold writes one event and nothing else, yet an unfinished one
stopped a Related correction, a Phase addition and a second Roadmap's creation.

Each operation now declares the ledgers it can write on any path it has. "Can",
not "did": scope is declared before the operation knows which path it takes, so
a conditional write still belongs in it, and two operations that can both write
one shared ledger are never independent - those files are rewritten whole.
Narrowing the declaration changes nothing about what may be written: the scope
is a conflict declaration, never a permission, and every effect is still bounded
by the entity and ledger sets recorded here.

Recovery records written before this are left exactly as they are, broad scope
and all, and go on stopping what they used to stop.
"""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, scripted_executor
from workline import roadmap as rm
from workline import start as st
from workline import yamlish
from workline.create import RelatedSpec, WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, StopError
from workline.mutation import Mutation, MutationController, WriteScope
from workline.ops import Replan
from workline.phase_create import PhaseSpec
from workline.state import ProjectView
from workline.store import WORKLINE_DIR
from workline.validate import validate_project

ROADMAP_RELATIONS = f"{WORKLINE_DIR}/relations/roadmap.yaml"
RELATED_RELATIONS = f"{WORKLINE_DIR}/relations/related.yaml"
EVENT_LOG = f"{WORKLINE_DIR}/events/events.jsonl"
LEDGERS = (ROADMAP_RELATIONS, RELATED_RELATIONS, EVENT_LOG)


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


def ledgers_written(record: dict) -> set[str]:
    """The shared ledgers this record's effects touch.

    Entity and derivation files are left out on purpose: each is named by an ID
    this mutation reserved, so no other operation can be writing the same one,
    and the declared entity set already covers them.
    """
    touched: set[str] = set()
    for effect in record["effects"]:
        kind, payload = effect["kind"], effect["payload"]
        if kind == "append_event":
            touched.add(EVENT_LOG)
        elif kind in ("add_relation", "remove_relation"):
            touched.add(f"{WORKLINE_DIR}/relations/{payload['file']}.yaml")
        elif kind == "write_file" and payload["path"] in LEDGERS:
            touched.add(payload["path"])
    return touched


class ScopeCase(WorklineTestCase):
    # observation -----------------------------------------------------------
    def captured(self) -> list[dict]:
        """Every mutation completed while :meth:`capture` was active."""
        return self._captured

    def capture(self):
        self._captured: list[dict] = []
        real = Mutation.complete

        def watch(mutation: Mutation):
            self._captured.append(yamlish.load(yamlish.dump(mutation.record)))
            return real(mutation)

        return mock.patch.object(Mutation, "complete", watch)

    def interrupt(self, fn, *args, **kwargs) -> dict:
        """Leave one pending mutation behind, stopped just before it finalizes."""

        def fire(*a, **k):
            raise Interrupted("before finalize")

        with mock.patch.object(rm, "_finalize", fire):
            with self.assertRaises(Interrupted):
                fn(*args, **kwargs)
        (record,) = MutationController(self.store).list_pending()
        return record

    def declared(self, record: dict) -> set[str]:
        return set(record["write_scope"]["files"])

    def record_bytes(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))}


# --------------------------------------------------------------------------- the declared sets
class DeclaredScopeTests(ScopeCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B")})
        self.pa, self.pb = self.roadmap.phase_ids["a"], self.roadmap.phase_ids["b"]

    def test_each_operation_declares_the_ledgers_it_can_write(self) -> None:
        expected = {
            "roadmap-create": {ROADMAP_RELATIONS},
            "roadmap-add-phases": {ROADMAP_RELATIONS},
            "phase-entry": {ROADMAP_RELATIONS, RELATED_RELATIONS},
            "phase-hold": {EVENT_LOG},
            "phase-resume": {EVENT_LOG},
            "phase-cancel": {EVENT_LOG},
            "roadmap-hold": {EVENT_LOG},
            "roadmap-resume": {EVENT_LOG},
            "roadmap-cancel": {EVENT_LOG},
            "roadmap-achievement": {EVENT_LOG},
            "phase-plan-exclude": set(LEDGERS),
            "work-plan-exclude": set(LEDGERS),
            "work-related-maintenance": {RELATED_RELATIONS},
        }
        for operation, files in expected.items():
            with self.subTest(operation=operation):
                self.assertEqual(set(rm._ledgers(operation)), files)

    def test_an_operation_with_no_decision_recorded_declares_every_ledger(self) -> None:
        """Fail closed: a new operation over-declares rather than looking independent."""
        self.assertEqual(set(rm._ledgers("some-operation-added-later")), set(LEDGERS))

    def test_no_operation_declares_an_empty_scope(self) -> None:
        """An empty scope is treated as overlapping everything, so it would stop the Project."""
        for operation, files in rm.OPERATION_LEDGERS.items():
            with self.subTest(operation=operation):
                self.assertTrue(files)
                self.assertTrue(set(files) <= set(LEDGERS))

    def test_direct_create_declares_only_the_ledger_it_writes(self) -> None:
        """It passes no relations and records no event, so only Related can be written."""
        store = self.new_project("direct")
        with self.capture():
            create_standalone_work(store, WorkSpec("Solo", "s", related=(RelatedSpec("must_read", "x.md"),)))
        (record,) = self.captured()
        self.assertEqual(self.declared(record), {RELATED_RELATIONS})

    def test_start_declares_every_ledger_because_it_can_write_every_ledger(self) -> None:
        """START records events, registers derived Works and rewrites Roadmap relations."""
        self.assertEqual(set(st.LEDGER_FILES), set(LEDGERS))


# --------------------------------------------------------------------------- nothing is under-declared
class ContainmentTests(ScopeCase):
    """Every ledger an operation actually writes is one it declared."""

    def assertContained(self) -> None:
        for record in self.captured():
            operation = record["invocation"].get("operation")
            with self.subTest(operation=operation, mutation=record["mutation_id"]):
                self.assertTrue(
                    ledgers_written(record) <= self.declared(record),
                    f"{operation} wrote {sorted(ledgers_written(record) - self.declared(record))} "
                    f"outside its declared scope {sorted(self.declared(record))}",
                )

    def test_roadmap_operations_write_only_inside_their_declared_scope(self) -> None:
        self.store = self.new_project()
        with self.capture():
            roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B"), "c": ("Phase C", "C")})
            rid = roadmap.roadmap_id
            pa, pb, pc = (roadmap.phase_ids[k] for k in ("a", "b", "c"))
            added = rm.add_phases(self.store, rid, {"d": PhaseSpec("Phase D", "D")})
            rm.hold_phase(self.store, pb)
            rm.resume_phase(self.store, pb)
            rm.cancel_phase(self.store, pc)
            rm.hold_roadmap(self.store, rid)
            rm.resume_roadmap(self.store, rid)
            (self.store.root / "a.md").write_text("a\n", encoding="utf-8")
            entry = self.simple_entry(self.store, pa, {"w1": "W1", "w2": "W2"})
            w2 = entry.work_ids["w2"]
            rm.maintain_work_related(self.store, w2, add=(RelatedSpec("must_read", "a.md"),))
            existing = next(r.id for r in ProjectView.load(self.store).related)
            rm.maintain_work_related(self.store, w2, remove_relation_ids=(existing,))
            orphaned = tuple(r.id for r in ProjectView.load(self.store).roadmap_relations
                             if w2 in (r.from_id, r.to))
            rm.plan_exclude_work(self.store, w2, Replan(remove_relation_ids=orphaned))
            rm.plan_exclude_phase(self.store, added.phase_ids["d"], Replan())

        self.assertContained()
        self.assertEqual(validate_project(self.store), [])

    def test_a_phase_expansion_writes_only_inside_its_declared_scope(self) -> None:
        """Relations, Related and entity files - and no lifecycle event."""
        self.store = self.new_project()
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B")})
        (self.store.root / "d.md").write_text("d\n", encoding="utf-8")
        with self.capture():
            rm.enter_phase(self.store, roadmap.phase_ids["b"], rm.PhaseEntryDesign(
                {"x": rm.WorkDesign("X", "x", (RelatedSpec("must_read", "d.md"),)), "y": rm.WorkDesign("Y", "y")},
                rm.WorkDesign("I", "i"),
                rm.WorkDesign("C", "c"),
                planned_next=(("x", "y"),),
                requires_completion=(("x", "y"),),
            ))

        self.assertContained()
        (record,) = self.captured()
        self.assertNotIn(EVENT_LOG, ledgers_written(record))

    def test_a_replan_that_registers_works_stays_inside_the_plan_exclusion_scope(self) -> None:
        """A replan records the event, registers Works with Related, and adds Roadmap relations."""
        self.store = self.new_project()
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B")})
        (self.store.root / "a.md").write_text("a" + chr(10), encoding="utf-8")
        with self.capture():
            rm.plan_exclude_phase(self.store, roadmap.phase_ids["b"], Replan(
                new_works={
                    "n": WorkSpec("Replacement", "r", related=(RelatedSpec("must_read", "a.md"),)),
                    "m": WorkSpec("Follow up", "f"),
                },
                add_relations=(rm.RelationSpec("planned_next", "n", "m"),),
            ))

        self.assertContained()
        (record,) = self.captured()
        self.assertEqual(ledgers_written(record), {EVENT_LOG, ROADMAP_RELATIONS, RELATED_RELATIONS})

    def test_start_writes_only_inside_its_declared_scope(self) -> None:
        self.store = self.new_project()
        roadmap = self.simple_roadmap(self.store)
        entry = self.simple_entry(self.store, roadmap.phase_ids["a"], {"w1": "W1", "w2": "W2"})
        w1, w2 = entry.work_ids["w1"], entry.work_ids["w2"]
        (self.store.root / "r.md").write_text("r\n", encoding="utf-8")
        with self.capture():
            st.start(self.store, w1, "single-work", scripted_executor({w1: [st.QuestionWait("?")]}))
            st.start(self.store, w1, "single-work", completing_executor(self.store))
            st.start(self.store, w2, "single-work", scripted_executor({
                w2: [st.Derive({"d": st.DerivedWork(
                    "Derived", "d", (RelatedSpec("must_read", "r.md"),), derivation_detail="why")}),
                     st.Completed()],
                "*": [st.Completed()],
            }))

        self.assertContained()

    def test_direct_create_writes_only_inside_its_declared_scope(self) -> None:
        self.store = self.new_project()
        (self.store.root / "a.md").write_text("a\n", encoding="utf-8")
        with self.capture():
            create_standalone_work(self.store, WorkSpec("Plain", "p"))
            create_standalone_work(self.store, WorkSpec(
                "Rich", "r", related=(RelatedSpec("must_read", "a.md"),), derivation_detail="from here"))

        self.assertContained()


# --------------------------------------------------------------------------- the false conflicts
class IndependenceTests(ScopeCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B")})
        self.pa, self.pb = self.roadmap.phase_ids["a"], self.roadmap.phase_ids["b"]
        self.entry = self.simple_entry(self.store, self.pa, {"w1": "W1", "w2": "W2"})
        self.w2 = self.entry.work_ids["w2"]
        (self.store.root / "a.md").write_text("a\n", encoding="utf-8")

    def assertPendingKept(self, record: dict) -> None:
        """The interrupted operation is still there, untouched, waiting to be resumed."""
        path = MutationController(self.store).intent_path(record["mutation_id"])
        self.assertEqual(yamlish.load(path.read_text(encoding="utf-8"))["status"], "pending")

    def test_an_unfinished_lifecycle_event_does_not_block_a_related_correction(self) -> None:
        pending = self.interrupt(rm.hold_phase, self.store, self.pb)
        self.assertEqual(self.declared(pending), {EVENT_LOG})

        result = rm.maintain_work_related(self.store, self.w2, add=(RelatedSpec("must_read", "a.md"),))

        self.assertTrue(result.changed)
        self.assertPendingKept(pending)
        self.assertEqual(validate_project(self.store), [])

    def test_an_unfinished_lifecycle_event_does_not_block_a_phase_addition(self) -> None:
        pending = self.interrupt(rm.hold_phase, self.store, self.pb)

        result = rm.add_phases(self.store, self.roadmap.roadmap_id, {"z": PhaseSpec("Z", "z が成立する")})

        self.assertEqual(len(result.phase_ids), 1)
        self.assertPendingKept(pending)

    def test_an_unfinished_related_correction_does_not_block_a_lifecycle_event(self) -> None:
        pending = self.interrupt(rm.maintain_work_related, self.store, self.w2,
                                 add=(RelatedSpec("must_read", "a.md"),))
        self.assertEqual(self.declared(pending), {RELATED_RELATIONS})

        result = rm.hold_phase(self.store, self.pb)

        self.assertEqual(result.status, "phase_held")
        self.assertPendingKept(pending)

    def test_an_unfinished_roadmap_creation_does_not_block_a_lifecycle_event(self) -> None:
        pending = self.interrupt(rm.create_roadmap, self.store, rm.RoadmapPlan(
            "Second", "背景", "達成したい状態", {"a": PhaseSpec("P", "p")}))
        self.assertEqual(self.declared(pending), {ROADMAP_RELATIONS})

        result = rm.hold_phase(self.store, self.pb)

        self.assertEqual(result.status, "phase_held")
        self.assertPendingKept(pending)

    def test_an_unfinished_phase_expansion_does_not_block_a_lifecycle_event_elsewhere(self) -> None:
        pending = self.interrupt(rm.enter_phase, self.store, self.pb, rm.PhaseEntryDesign(
            {"x": rm.WorkDesign("X", "x")}, rm.WorkDesign("I", "i")))
        self.assertEqual(self.declared(pending), {ROADMAP_RELATIONS, RELATED_RELATIONS})

        result = rm.hold_roadmap(self.store, self.roadmap.roadmap_id)

        self.assertEqual(result.status, "roadmap_held")
        self.assertPendingKept(pending)


# --------------------------------------------------------------------------- the real conflicts
class ConflictTests(ScopeCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B")})
        self.pa, self.pb = self.roadmap.phase_ids["a"], self.roadmap.phase_ids["b"]
        self.entry = self.simple_entry(self.store, self.pa, {"w1": "W1", "w2": "W2"})
        self.w2 = self.entry.work_ids["w2"]
        (self.store.root / "a.md").write_text("a\n", encoding="utf-8")

    def assertStops(self, pending: dict, fn, *args, **kwargs) -> None:
        before = self.record_bytes()
        with self.assertRaises(ReconcileRequired) as raised:
            fn(*args, **kwargs)
        self.assertIn(pending["mutation_id"], str(raised.exception))
        self.assertEqual(self.record_bytes(), before)

    def test_two_operations_that_rewrite_one_ledger_still_stop(self) -> None:
        """``related.yaml`` is rewritten whole, so writing a different edge is not independence."""
        pending = self.interrupt(rm.maintain_work_related, self.store, self.w2,
                                 add=(RelatedSpec("must_read", "a.md"),))

        self.assertStops(pending, rm.enter_phase, self.store, self.pb, rm.PhaseEntryDesign(
            {"x": rm.WorkDesign("X", "x", (RelatedSpec("must_read", "a.md"),))}, rm.WorkDesign("I", "i")))

    def test_two_lifecycle_operations_still_stop(self) -> None:
        pending = self.interrupt(rm.hold_phase, self.store, self.pb)

        self.assertStops(pending, rm.hold_roadmap, self.store, self.roadmap.roadmap_id)

    def test_the_same_entity_still_stops_when_the_ledgers_are_disjoint(self) -> None:
        """Files decide nothing here: both operations are changing the same Phase."""
        pending = self.interrupt(rm.enter_phase, self.store, self.pb, rm.PhaseEntryDesign(
            {"x": rm.WorkDesign("X", "x")}, rm.WorkDesign("I", "i")))
        self.assertFalse(self.declared(pending) & {EVENT_LOG})
        self.assertIn(self.pb, pending["write_scope"]["entities"])

        self.assertStops(pending, rm.hold_phase, self.store, self.pb)

    def test_a_start_operation_still_stops_a_roadmap_one(self) -> None:
        """START declares every ledger because it can write every ledger."""
        pending_scope = WriteScope(entities=(self.entry.work_ids["w1"],), files=st.LEDGER_FILES)
        self.assertTrue(pending_scope.overlaps(WriteScope(files=rm._ledgers("phase-hold"))))
        self.assertTrue(pending_scope.overlaps(WriteScope(files=rm._ledgers("work-related-maintenance"))))
        self.assertTrue(pending_scope.overlaps(WriteScope(files=rm._ledgers("roadmap-create"))))


# --------------------------------------------------------------------------- records written before
class LegacyRecordTests(ScopeCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B")})
        self.pa, self.pb = self.roadmap.phase_ids["a"], self.roadmap.phase_ids["b"]
        self.entry = self.simple_entry(self.store, self.pa, {"w1": "W1", "w2": "W2"})
        (self.store.root / "a.md").write_text("a\n", encoding="utf-8")

    def widen(self, record: dict) -> bytes:
        """The record as the previous implementation wrote it: every ledger declared."""
        path = MutationController(self.store).intent_path(record["mutation_id"])
        data = yamlish.load(path.read_text(encoding="utf-8"))
        data["write_scope"]["files"] = sorted(LEDGERS)
        path.write_text(yamlish.dump(data), encoding="utf-8")
        return path.read_bytes()

    def test_a_record_written_before_keeps_the_scope_it_recorded(self) -> None:
        pending = self.interrupt(rm.hold_phase, self.store, self.pb)
        recorded = self.widen(pending)
        before = self.record_bytes()

        with self.assertRaises(ReconcileRequired) as raised:
            rm.maintain_work_related(self.store, self.entry.work_ids["w2"],
                                     add=(RelatedSpec("must_read", "a.md"),))

        self.assertIn(pending["mutation_id"], str(raised.exception))
        # not narrowed, not rewritten, not abandoned
        self.assertEqual(self.record_bytes(), before)
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        self.assertEqual(path.read_bytes(), recorded)
        self.assertEqual(yamlish.load(path.read_text(encoding="utf-8"))["status"], "pending")

    def test_resuming_a_record_written_before_does_not_narrow_it(self) -> None:
        real = Mutation.add_effects

        def fire(mutation, stage, effects):
            if stage == "event":
                raise Interrupted("before the event is recorded")
            real(mutation, stage, effects)

        with mock.patch.object(Mutation, "add_effects", fire):
            with self.assertRaises(Interrupted):
                rm.hold_phase(self.store, self.pb)
        (pending,) = MutationController(self.store).list_pending()
        self.assertEqual(pending["effects"], [])
        self.widen(pending)

        rm.hold_phase(self.store, self.pb)

        # the operation finished; its record was completed, never re-scoped
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(ProjectView.load(self.store).phase_state(self.pb), "held")


# --------------------------------------------------------------------------- the neighbours
class NeighbourRegressionTests(ScopeCase):
    """The narrowed scope does not disturb what the recovery contract already guarantees."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B")})
        self.pb = self.roadmap.phase_ids["b"]

    def test_an_interrupted_phase_expansion_still_resumes(self) -> None:
        """BL-023: the same design carries the same mutation forward."""
        design = rm.PhaseEntryDesign({"x": rm.WorkDesign("X", "x")}, rm.WorkDesign("I", "i"))
        pending = self.interrupt(rm.enter_phase, self.store, self.pb, design)

        result = rm.enter_phase(self.store, self.pb, design)

        self.assertTrue(result.expanded)
        self.assertEqual(result.mutation_id, pending["mutation_id"])  # the same mutation
        self.assertEqual(validate_project(self.store), [])

    def test_an_interrupted_expansion_still_refuses_another_design(self) -> None:
        """BL-024: a retry that decided something else is refused, record untouched."""
        pending = self.interrupt(rm.enter_phase, self.store, self.pb, rm.PhaseEntryDesign(
            {"x": rm.WorkDesign("X", "x")}, rm.WorkDesign("I", "i")))
        before = self.record_bytes()

        with self.assertRaises(StopError) as raised:
            rm.enter_phase(self.store, self.pb, rm.PhaseEntryDesign(
                {"x": rm.WorkDesign("X", "別の状態")}, rm.WorkDesign("I", "i")))

        self.assertEqual(raised.exception.code, "reconcile_required")
        self.assertEqual(self.record_bytes(), before)

    def test_a_roadmap_can_be_held_while_one_of_its_phases_is_half_expanded(self) -> None:
        """The interrupted expansion is recovery state, not a lock on the whole Roadmap.

        Holding the Roadmap writes one event; the expansion writes relations. They
        are independent, so the hold goes through - and the expansion, untouched,
        carries on to the end once the Roadmap is resumed.
        """
        design = rm.PhaseEntryDesign({"x": rm.WorkDesign("X", "x")}, rm.WorkDesign("I", "i"))
        pending = self.interrupt(rm.enter_phase, self.store, self.pb, design)

        self.assertEqual(rm.hold_roadmap(self.store, self.roadmap.roadmap_id).status, "roadmap_held")
        with self.assertRaises(StopError) as raised:
            rm.enter_phase(self.store, self.pb, design)
        self.assertEqual(raised.exception.code, "roadmap_held")  # the lifecycle rule, not the scope
        rm.resume_roadmap(self.store, self.roadmap.roadmap_id)
        result = rm.enter_phase(self.store, self.pb, design)

        self.assertTrue(result.expanded)
        self.assertEqual(result.mutation_id, pending["mutation_id"])
        self.assertEqual(validate_project(self.store), [])

    def test_an_interrupted_addition_still_refuses_another_request(self) -> None:
        """BL-024 on an operation whose scope changed: refusal comes before the scope check."""
        pending = self.interrupt(rm.add_phases, self.store, self.roadmap.roadmap_id,
                                 {"z": PhaseSpec("Z", "z が成立する")}, invocation_key="K")
        before = self.record_bytes()

        with self.assertRaises(StopError) as raised:
            rm.add_phases(self.store, self.roadmap.roadmap_id, {"z": PhaseSpec("Z", "別の状態")},
                          invocation_key="K")

        self.assertEqual(raised.exception.code, "reconcile_required")
        self.assertIn(pending["mutation_id"], str(raised.exception))
        self.assertEqual(self.record_bytes(), before)


if __name__ == "__main__":
    unittest.main()
