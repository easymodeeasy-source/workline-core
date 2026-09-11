from __future__ import annotations

import unittest
from unittest import mock

from helpers import WorklineTestCase, git
from workline.durable import DurableWriteError
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.mutation import MATCHING, UNAPPLIED, Effect, MutationController, WriteScope
from workline.oplock import project_operation
from workline.store import WORKLINE_DIR, Event, Relation

SCOPE = WriteScope(entities=("w_01ARZ3NDEKTSV4RRFFQ69G5FAV",), files=(f"{WORKLINE_DIR}/events/events.jsonl",))
WORK_PATH = f"{WORKLINE_DIR}/works/w_01ARZ3NDEKTSV4RRFFQ69G5FAV.md"
WORK_TEXT = "---\nid: w_01ARZ3NDEKTSV4RRFFQ69G5FAV\ndisplay: W-01\ntype: work\norigin:\n  type: standalone\n---\n\n# W\n\n## このWorkで成立させる状態\nx\n"
OTHER_PATH = f"{WORKLINE_DIR}/works/w_01ARZ3NDEKTSV4RRFFQ69G5FAW.md"
OTHER_TEXT = WORK_TEXT.replace("5FAV", "5FAW")


class MutationControllerTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.controller = MutationController(self.store)
        # These tests drive the Mutation Controller directly, as a top-level
        # operation does: while holding the Project execution lock.
        lock = project_operation(self.store, "mutation-controller-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)

    def _begin(self, owner: str = "start", invocation: dict | None = None):
        return self.controller.open(owner, invocation or {"operation": "start", "work_id": "w_x"}, SCOPE)

    # intent durability ---------------------------------------------------------
    def test_intent_is_durable_before_first_domain_effect(self) -> None:
        mutation = self._begin()
        self.assertTrue(mutation.path.is_file())
        seen: list[bool] = []
        real_apply = self.controller.apply_effect

        def spy(record):
            seen.append(WORK_PATH in mutation.path.read_text(encoding="utf-8"))
            return real_apply(record)

        with mock.patch.object(self.controller, "apply_effect", spy):
            mutation.add_effects("s1", [Effect.write_file(WORK_PATH, WORK_TEXT)])
            mutation.apply()
        self.assertEqual(seen, [True])
        self.assertTrue(self.store.abs(WORK_PATH).is_file())

    def test_recovery_write_failure_stops_before_domain_effect(self) -> None:
        mutation = self._begin()
        with mock.patch("workline.mutation.durable_write_text", side_effect=DurableWriteError("disk")):
            with self.assertRaises(StopError) as ctx:
                mutation.add_effects("s1", [Effect.write_file(WORK_PATH, WORK_TEXT)])
        self.assertEqual(ctx.exception.code, "recovery_write_failed")
        self.assertFalse(self.store.abs(WORK_PATH).exists())
        # the on-disk intent still has no effects: nothing to resume
        self.assertEqual(self.controller.load(mutation.id).effects, [])

    def test_crash_before_first_write_leaves_nothing_to_resume(self) -> None:
        with mock.patch("workline.mutation.durable_write_text", side_effect=DurableWriteError("disk")):
            with self.assertRaises(StopError):
                self._begin()
        self.assertEqual(self.controller.list_pending(), [])
        mutation = self._begin()  # a fresh mutation starts normally
        self.assertFalse(mutation.resumed)

    # resume classification -----------------------------------------------------
    def test_crash_after_first_effect_resumes_and_skips_matching(self) -> None:
        mutation = self._begin()
        mutation.add_effects("s1", [Effect.write_file(WORK_PATH, WORK_TEXT), Effect.write_file(OTHER_PATH, OTHER_TEXT)])
        real_apply = self.controller.apply_effect
        calls = {"n": 0}

        def crash_after_first(record):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("crash")
            return real_apply(record)

        with mock.patch.object(self.controller, "apply_effect", crash_after_first):
            with self.assertRaises(RuntimeError):
                mutation.apply()
        self.assertTrue(self.store.abs(WORK_PATH).is_file())
        self.assertFalse(self.store.abs(OTHER_PATH).exists())

        resumed = self.controller.open("start", {"operation": "start", "work_id": "w_x"}, SCOPE)
        self.assertTrue(resumed.resumed)
        self.assertEqual(resumed.id, mutation.id)
        writes: list[str] = []
        real_apply2 = self.controller.apply_effect

        def spy(record):
            writes.append(record["payload"]["path"])
            return real_apply2(record)

        with mock.patch.object(self.controller, "apply_effect", spy):
            outcomes = resumed.apply()
        self.assertEqual(writes, [OTHER_PATH])
        self.assertEqual([c for _, c in outcomes], [MATCHING, UNAPPLIED])
        self.assertTrue(self.store.abs(OTHER_PATH).is_file())

    def test_conflicting_effect_requires_reconcile(self) -> None:
        mutation = self._begin()
        mutation.add_effects("s1", [Effect.write_file(WORK_PATH, WORK_TEXT)])
        mutation.apply()
        self.store.abs(WORK_PATH).write_text(WORK_TEXT + "tampered\n", encoding="utf-8")
        resumed = self.controller.load(mutation.id)
        with self.assertRaises(ReconcileRequired):
            resumed.apply()
        # no automatic overwrite
        self.assertTrue(self.store.abs(WORK_PATH).read_text(encoding="utf-8").endswith("tampered\n"))

    def test_dynamic_effect_is_recorded_before_it_runs(self) -> None:
        mutation = self._begin()
        mutation.add_effects("s1", [Effect.write_file(WORK_PATH, WORK_TEXT)])
        mutation.apply()
        event = Event("evt_01ARZ3NDEKTSV4RRFFQ69G5FAV", "work_started", "w_01ARZ3NDEKTSV4RRFFQ69G5FAV", "2026-01-01T00:00:00+00:00")
        seen: list[bool] = []
        real_apply = self.controller.apply_effect

        def spy(record):
            seen.append(event.id in mutation.path.read_text(encoding="utf-8"))
            return real_apply(record)

        with mock.patch.object(self.controller, "apply_effect", spy):
            mutation.add_effects("s2", [Effect.append_event(event)])
            mutation.apply()
        self.assertEqual(seen, [True])
        self.assertEqual([e.id for e in self.store.read_events()], [event.id])
        self.assertEqual([e["stage"] for e in mutation.effects], ["s1", "s2"])

    def test_reserved_ids_are_stable_across_resume(self) -> None:
        mutation = self._begin()
        first = mutation.reserve_id("work:0", "work")
        resumed = self.controller.load(mutation.id)
        self.assertEqual(resumed.reserve_id("work:0", "work"), first)

    # pending discovery ---------------------------------------------------------
    def test_pending_discovery_zero_one_many(self) -> None:
        invocation = {"operation": "start", "work_id": "w_x"}
        first = self.controller.open("start", invocation, SCOPE)
        self.assertFalse(first.resumed)
        again = self.controller.open("start", invocation, SCOPE)
        self.assertTrue(again.resumed)
        self.assertEqual(again.id, first.id)
        # a second pending record with the same identity → reconcile
        duplicate = self.controller.begin("start", invocation, SCOPE)
        with self.assertRaises(ReconcileRequired):
            self.controller.open("start", invocation, SCOPE)
        duplicate.complete()
        first.complete()
        fresh = self.controller.open("start", invocation, SCOPE)
        self.assertFalse(fresh.resumed)

    def test_other_owner_pending_mutation_requires_reconcile(self) -> None:
        pending = self.controller.open("roadmap", {"operation": "phase-entry", "phase_id": "p_x"}, SCOPE)
        with self.assertRaises(ReconcileRequired):
            self.controller.open("start", {"operation": "start", "work_id": "w_x"}, SCOPE)
        pending.complete()
        self.controller.open("start", {"operation": "start", "work_id": "w_x"}, SCOPE)

    def test_independent_scopes_do_not_block(self) -> None:
        other = self.controller.open("roadmap", {"operation": "x"}, WriteScope(entities=("p_a",), files=("a",)))
        mine = self.controller.open("start", {"operation": "y"}, WriteScope(entities=("w_b",), files=("b",)))
        self.assertNotEqual(other.id, mine.id)

    def test_unowned_runtime_record_requires_reconcile(self) -> None:
        self.store.mutations.mkdir(parents=True, exist_ok=True)
        (self.store.mutations / "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV.yaml").write_text("status: pending\n", encoding="utf-8")
        with self.assertRaises(ReconcileRequired):
            self.controller.list_pending()

    # validation ------------------------------------------------------------------
    def test_controller_validates_payloads_without_deciding_meaning(self) -> None:
        mutation = self._begin()
        with self.assertRaises(ValidationError):
            mutation.add_effects("bad-path", [Effect.write_file("../outside.md", "x")])
        with self.assertRaises(ValidationError):
            mutation.add_effects("bad-runtime", [Effect.write_file(f"{WORKLINE_DIR}/runtime/x.md", "x")])
        with self.assertRaises(ValidationError):
            mutation.add_effects("bad-rel", [Effect.add_relation("roadmap", Relation("rel_01ARZ3NDEKTSV4RRFFQ69G5FAV", "planned_next", "w_missing", "w_other"))])
        with self.assertRaises(ValidationError):
            mutation.add_effects("bad-event", [Effect.append_event(Event("evt_01ARZ3NDEKTSV4RRFFQ69G5FAV", "work_started", "w_01ARZ3NDEKTSV4RRFFQ69G5FAV", "t"))])
        self.assertEqual(mutation.effects, [])

    def test_terminal_event_exclusivity(self) -> None:
        mutation = self._begin()
        entity = "w_01ARZ3NDEKTSV4RRFFQ69G5FAV"
        mutation.add_effects("s1", [
            Effect.write_file(WORK_PATH, WORK_TEXT),
            Effect.append_event(Event("evt_01ARZ3NDEKTSV4RRFFQ69G5FA1", "work_completed", entity, "t")),
        ])
        mutation.apply()
        with self.assertRaises(ValidationError):
            mutation.add_effects("s2", [Effect.append_event(Event("evt_01ARZ3NDEKTSV4RRFFQ69G5FA2", "work_cancelled", entity, "t"))])

    # git effects -------------------------------------------------------------
    def test_git_commit_effect_is_idempotent_on_resume(self) -> None:
        mutation = self._begin()
        mutation.add_effects("s1", [Effect.write_file(WORK_PATH, WORK_TEXT)])
        mutation.apply()
        from workline import gitcmd

        mutation.add_effects("git", [Effect.git_commit("chore(workline): test commit", [WORK_PATH], gitcmd.head_commit(self.store.root))])
        mutation.apply()
        head = gitcmd.head_commit(self.store.root)
        outcomes = self.controller.load(mutation.id).apply()
        self.assertEqual(gitcmd.head_commit(self.store.root), head)
        self.assertEqual([c for _, c in outcomes], [MATCHING, MATCHING])
        self.assertEqual(git(self.store.root, "log", "-1", "--format=%s").strip(), "chore(workline): test commit")


if __name__ == "__main__":
    unittest.main()
