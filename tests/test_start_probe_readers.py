"""RB11 RT-1a, the post-open readers S5.1 - S5.4 and the refused-result note S7.3 (rev-11 TFI §B.1; ADM §A.2).

Per ALLOW raising call of ``_completion_to_finish`` (S5.1), ``_hold_to_finish``
(S5.2), ``_derivations_to_reuse`` (S5.3), ``_derive_move_to_finish`` (S5.4) and
``_Session._refused_result`` (900, S7.3): a record whose first refusal is that
call is ``pending_reconcile_required`` with its check ID, and a real ``start()``
refuses there too (T-B01 / T-B02). The excluded calls of the same readers - HEAD,
view and mixed checks through the same ``refuse`` factories - stay
``unknown_or_invalid`` (T-B03, T-B41, T-B44); START's guards are honoured
(T-B47); and 900 is evaluated only under every condition of S7.3 (T-B51).

``ops.832`` reached through the move reader (3234) is never a record's first
refusal: the derivations reader (3022) runs the same ``_recorded_stages`` over the
same effects first (ADM §A.1 S5.3 before S5.4), so that row is pinned at 3022.
"""

from __future__ import annotations

import copy
import unittest

from helpers import completing_executor, git
from start_probe_helpers import EVENT_LOG, ProbeCase, after_recording, before_finalizing
from workline import start as st, start_probe
from workline.ids import new_id
from workline.mutation import Mutation, MutationController, WriteScope, _content_digest
from workline.oplock import project_operation
from workline.store import Event, render_event_line

AT = "2026-10-12T00:00:00+00:00"


def event_effect(stage: str, event_type: str, entity: str, event_id: str | None = None) -> dict:
    return {"seq": 0, "stage": stage, "kind": "append_event", "applied": True,
            "payload": {"record": {"id": event_id or new_id("event"), "type": event_type, "entity": entity, "at": AT}}}


class ReaderCase(ProbeCase):
    def move_record(self, *, committed: bool = True) -> dict:
        window = after_recording(r"^commit:\d+$") if committed else before_finalizing()
        return self.interrupt(window, lambda: st.start(self.store, self.w1, "single-work",
                                                       lambda ctx: self.derive("f0", move=True)))

    def note(self, record: dict, key: str) -> dict:
        return record["notes"][key]


class CompletionTests(ReaderCase):
    """S5.1, operation "start" only."""

    def test_1530_more_than_one_unfinished_terminal_work(self) -> None:
        self.completion_record()
        self.edit(lambda r: r["effects"].append(event_effect(f"{self.w2}:lifecycle:0", "work_completed", self.w2)))
        self.assertReconcileAt("start.1530")

    def test_1540_a_completion_recorded_in_another_form(self) -> None:
        self.completion_record()
        self.edit(lambda r: r["reserved_ids"].__setitem__(f"{self.w1}:lifecycle:1:event:0", new_id("event")))
        self.assertReconcileAt("start.1540")

    def test_1552_another_terminal_event_without_its_commit(self) -> None:
        self.question_wait_record()
        self.edit(lambda r: r["effects"].append(event_effect(f"{self.w1}:lifecycle:1", "plan_excluded", self.w1)))
        self.assertReconcileAt("start.1552")

    def test_1546_completion_events_already_in_head_are_not_a_reconcile(self) -> None:
        self.completion_record()
        self.commit_by_hand(EVENT_LOG)
        self.assertUnknown("start.1546", start_check="start.1546")


class HoldTests(ReaderCase):
    """S5.2, reached only when no completion is finishing."""

    def setUp(self) -> None:
        super().setUp()
        self.L1 = f"{self.w1}:lifecycle:1"

    def test_2750_more_than_one_work_held(self) -> None:
        self.hold_record()

        def change(record):
            held = self.event_effect(record, "work_held")
            record["effects"].insert(record["effects"].index(held) + 1, copy.deepcopy(held))
        self.edit(change)
        self.assertReconcileAt("start.2750")

    def test_2758_effects_that_cannot_be_read(self) -> None:
        self.hold_record()
        self.edit(lambda r: r["effects"][0].__setitem__("payload", "not a mapping"))
        self.assertReconcileAt("start.2758")

    def test_2759_ops_832_a_stage_recorded_in_two_places(self) -> None:
        self.hold_record()
        self.edit(lambda r: r["effects"].append(r["effects"].pop(1)))
        self.assertReconcileAt("ops.832")

    def test_2767_a_hold_of_something_that_is_not_a_work(self) -> None:
        self.hold_record()
        self.edit(lambda r: self.event_effect(r, "work_held")["payload"]["record"].__setitem__("entity", "not-a-work"))
        self.assertReconcileAt("start.2767")

    def test_2769_a_single_work_start_holding_another_work(self) -> None:
        self.hold_record()
        self.edit(lambda r: self.event_effect(r, "work_held")["payload"]["record"].__setitem__("entity", self.w2))
        self.assertReconcileAt("start.2769")

    def test_2774_a_hold_stage_under_another_name(self) -> None:
        self.hold_record()
        self.edit(lambda r: [e.__setitem__("stage", f"{self.w1}:lifecycle:7") for e in self.effects(r, self.L1)])
        self.assertReconcileAt("start.2774")

    def test_2784_a_hold_stage_holding_other_than_its_events(self) -> None:
        self.hold_record()
        self.edit(lambda r: self.event_effect(r, "work_target_removed")["payload"]["record"].__setitem__("extra", "x"))
        self.assertReconcileAt("start.2784")

    def test_2786_other_events_than_the_hold_of_one_work(self) -> None:
        self.hold_record()
        self.edit(lambda r: self.event_effect(r, "work_target_removed")["payload"]["record"].__setitem__("type", "work_started"))
        self.assertReconcileAt("start.2786")

    def test_2788_hold_events_under_unreserved_ids(self) -> None:
        self.hold_record()
        self.edit(lambda r: r["reserved_ids"].__setitem__(f"{self.L1}:event:0", new_id("event")))
        self.assertReconcileAt("start.2788")

    def test_2793_hold_events_carrying_more_than_the_reason(self) -> None:
        self.hold_record()
        self.edit(lambda r: self.event_effect(r, "work_target_removed")["payload"].__setitem__("extra", 1))
        self.assertReconcileAt("start.2793")

    def test_2800_a_hold_decision_in_another_form(self) -> None:
        self.hold_record()
        self.edit(lambda r: self.event_effect(r, "work_held")["payload"]["hold"].__setitem__("version", 9))
        self.assertReconcileAt("start.2800")

    def test_2811_a_decision_before_the_hold_no_commit_finalizes(self) -> None:
        self.hold_record()

        def change(record):
            stray = {"seq": 0, "stage": "stray:0", "kind": "write_file", "applied": True,
                     "payload": {"path": "stray.txt", "content": "x\n"}}
            record["effects"].insert(record["effects"].index(self.effects(record, self.L1)[0]), stray)
        self.edit(change)
        self.assertReconcileAt("start.2811")

    def test_2817_stages_after_the_hold_other_than_its_commit(self) -> None:
        self.hold_record(committed=True)
        self.edit(lambda r: [e.__setitem__("stage", "commit:5") for e in self.effects(r, "commit:0")])
        self.assertReconcileAt("start.2817")

    def test_2830_the_hold_commit_check_reads_the_view_and_is_not_a_reconcile(self) -> None:
        self.hold_record(committed=True)
        self.edit(lambda r: self.effects(r, "commit:0")[0]["payload"].__setitem__("message", "chore(workline): cancel W-01"))
        self.assertUnknown("start.2830", start_check="start.2830")

    def test_2832_hold_events_already_in_head_are_not_a_reconcile(self) -> None:
        self.hold_record()
        self.commit_by_hand(EVENT_LOG)
        self.assertUnknown("start.2832", start_check="start.2832")


class DerivationTests(ReaderCase):
    """S5.3, reached only when neither a completion nor a hold is to finish."""

    def setUp(self) -> None:
        super().setUp()
        self.D0 = f"{self.w1}:derive:0"

    def entries(self, record: dict) -> list:
        return self.note(record, "derivations")["derivations"]

    def test_3002_a_derivation_note_in_another_form(self) -> None:
        self.derivation_record()
        self.edit(lambda r: self.note(r, "derivations").__setitem__("version", 9))
        self.assertReconcileAt("start.3002")

    def test_3010_derivations_of_another_work_in_a_single_work_start(self) -> None:
        self.derivation_record()
        self.edit(lambda r: self.entries(r)[0].__setitem__("work_id", self.w2))
        self.assertReconcileAt("start.3010")

    def test_3021_effects_that_cannot_be_read(self) -> None:
        self.derivation_record()
        self.edit(lambda r: r["effects"][0].__setitem__("payload", "not a mapping"))
        self.assertReconcileAt("start.3021")

    def test_3022_ops_832_a_stage_recorded_in_two_places(self) -> None:
        self.derivation_record()
        self.edit(lambda r: r["effects"].append(r["effects"].pop(1)))
        found = self.assertReconcileAt("ops.832")
        self.assertEqual(found.step, "S5.3")

    def test_3027_derivations_out_of_their_stage_order(self) -> None:
        self.derivation_record()
        self.edit(lambda r: self.entries(r)[0].__setitem__("stage", f"{self.w1}:derive:3"))
        self.assertReconcileAt("start.3027")

    def test_3030_a_registration_no_kept_decision_names(self) -> None:
        self.derivation_record()

        def change(record):
            extra = [dict(copy.deepcopy(e), stage=f"{self.w1}:derive:1") for e in self.effects(record, self.D0)]
            record["effects"].extend(extra)
        self.edit(change)
        self.assertReconcileAt("start.3030")

    def test_3033_a_move_with_another_derivation_after_it(self) -> None:
        self.derivation_record()

        def change(record):
            first = self.entries(record)[0]
            later = dict(copy.deepcopy(first), stage=f"{self.w1}:derive:1")
            first["outcome"]["move"] = True
            self.entries(record).append(later)
        self.edit(change)
        self.assertReconcileAt("start.3033")

    def test_3038_a_registration_without_the_branch_it_was_decided_on(self) -> None:
        self.derivation_record()
        self.edit(lambda r: [e.pop("decided_on", None) for e in self.effects(r, self.D0)])
        self.assertReconcileAt("start.3038")

    def test_3053_stages_between_two_derivations_other_than_the_carrying_commit(self) -> None:
        self.derivation_record(2)
        self.edit(lambda r: [e.__setitem__("stage", "stray:0") for e in self.effects(r, "commit:0")])
        self.assertReconcileAt("start.3053.between")

    def test_3053_no_stage_between_and_the_registration_not_committed_is_not_a_reconcile(self) -> None:
        record = self.derivation_record(2)
        self.edit(lambda r: [r["effects"].remove(e) for e in self.effects(r, "commit:0")])
        written = self.store.root / self.effects(record, self.D0, "write_file")[0]["payload"]["path"]
        written.write_text(written.read_text(encoding="utf-8") + "\nedited after the registration\n", encoding="utf-8")
        self.assertUnknown("start.3053.uncommitted", start_check="start.3053.uncommitted")

    def test_t_b44_3431_registration_reservations_compared_before_the_replay(self) -> None:
        self.derivation_record(2)

        def change(record):
            for effect in self.effects(record, "commit:0"):
                record["effects"].remove(effect)
            record["reserved_ids"].pop(f"{self.D0}:work:f0")
        self.edit(change)
        self.assertUnknown("start.3431", start_check="start.3431")

    def test_t_b44_3455_registration_compared_with_the_view_before_the_replay(self) -> None:
        self.derivation_record(2)

        def change(record):
            for effect in self.effects(record, "commit:0"):
                record["effects"].remove(effect)
            payload = self.effects(record, self.D0, "write_file")[0]["payload"]
            payload["content"] = payload["content"].replace("Fix f0", "Fix f0 (edited in the record)")
        self.edit(change)
        self.assertUnknown("start.3455", start_check="start.3455")

    def test_t_b44_3431_after_the_replay_too(self) -> None:
        self.derivation_record()
        self.edit(lambda r: r["reserved_ids"].pop(f"{self.D0}:work:f0"))
        found = self.assertUnknown("start.3431", start_check="start.3431")
        self.assertEqual(found.step, "S7.2")


class MoveTests(ReaderCase):
    """S5.4, reached only on recorded derivations."""

    def test_3260_a_removal_stage_other_than_the_move_records(self) -> None:
        self.move_record()
        self.edit(lambda r: self.event_effect(r, "work_target_removed")["payload"].__setitem__("extra", 1))
        self.assertReconcileAt("start.3260")

    def test_3274_a_move_commit_with_another_message(self) -> None:
        self.move_record()
        self.edit(lambda r: self.effects(r, "commit:0")[0]["payload"].__setitem__("message", "chore(workline): branch from W-99"))
        self.assertReconcileAt("start.3274")

    def test_3281_a_move_commit_carrying_other_paths(self) -> None:
        self.move_record()
        self.edit(lambda r: self.effects(r, "commit:0")[0]["payload"].__setitem__("paths", ["elsewhere.txt"]))
        self.assertReconcileAt("start.3281")

    def test_3271_the_move_commit_check_reads_the_view_and_is_not_a_reconcile(self) -> None:
        self.move_record()

        def change(record):
            commit = self.effects(record, "commit:0")[0]
            record["effects"].append(copy.deepcopy(commit))
        self.edit(change)
        self.assertUnknown("start.3271", start_check="start.3271")

    def test_3283_the_move_event_already_in_head_is_not_a_reconcile(self) -> None:
        self.move_record(committed=False)
        self.commit_by_hand(EVENT_LOG)
        self.assertUnknown("start.3283", start_check="start.3283")


class GuardTests(ReaderCase):
    def test_t_b47_the_hold_reader_is_not_asked_while_a_completion_is_finishing(self) -> None:
        """T-B47: an outer record whose last stage is a provable unfinished completion also holds an earlier hold
        stage that 2817 would refuse: the probe follows START's guard and never says reconcile from the hold reader;
        a real START finishes the completion."""
        self.completion_record()
        hold_stage = f"{self.w2}:lifecycle:0"
        removed, held = new_id("event"), new_id("event")

        def change(record):
            record["invocation"]["mode"] = "outer"
            first_other = self.effects(record, f"{self.w1}:results:0")[0]
            at = record["effects"].index(first_other)
            record["effects"][at:at] = [event_effect(hold_stage, "work_target_removed", self.w2, removed),
                                        event_effect(hold_stage, "work_held", self.w2, held)]
            record["reserved_ids"][f"{hold_stage}:event:0"] = removed
            record["reserved_ids"][f"{hold_stage}:event:1"] = held
        record = self.edit(change)
        with open(self.store.events_jsonl, "a", encoding="utf-8", newline="") as log:
            for event_id, kind in ((removed, "work_target_removed"), (held, "work_held")):
                log.write(render_event_line(Event(event_id, kind, self.w2, AT)) + "\n")
        # the hold events are this record's own in this scenario: its last event-log write holds the log as it is now
        record = self.edit(lambda r: self.event_effect(r, "work_completed").__setitem__(
            "wrote", _content_digest(self.store.events_jsonl)))
        # read on its own, the hold reader refuses this record at 2817 (stages after the hold) ...
        alone = Mutation(MutationController(self.store), copy.deepcopy(record), resumed=True)
        with self.assertRaises(st.ReconcileRequired) as refused:
            st._hold_to_finish(alone, self.w1, "outer")
        self.assertEqual(refused.exception.check_id, "start.2817")
        # ... but START never asks it while a completion is finishing (start.py:3797), and neither does the probe
        found = self.probe()
        self.assertNotEqual(found.classification, start_probe.PENDING_RECONCILE, found)
        self.assertEqual((found.classification, found.step), (start_probe.PENDING_RESUMABLE, "S7.1"), found)
        st.start(self.store, self.w1, "outer", completing_executor(self.store))
        self.assertIn("chore(workline): complete W-01", git(self.store.root, "log", "--format=%s"))


class RefusedResultTests(ReaderCase):
    """T-B51: 900 only under S7.3 - the replay writes nothing, the Work runs with its target, no cycle replay."""

    GARBAGE = {"version": 9}

    def test_i_an_unreadable_refused_result_where_every_condition_holds(self) -> None:
        self.question_wait_record()
        self.edit(lambda r: r["notes"].__setitem__("refused_result", self.GARBAGE))
        found = self.assertReconcileAt("start.900")
        self.assertEqual(found.step, "S7.3")

    def test_ii_the_work_lacks_its_target_so_start_writes_its_lifecycle_first(self) -> None:
        with project_operation(self.store, "start", {}):
            mutation = MutationController(self.store).open(
                "start", {"operation": "start", "work_id": self.w2, "mode": "single-work"},
                WriteScope(entities=(self.w2,), files=st.LEDGER_FILES))
            mutation.set_note("refused_result", self.GARBAGE)
        found = self.assertUnknown()
        self.assertEqual(found.step, "S7.2")
        self.assertIsNone(found.check_id)

    def test_iii_the_cycle_has_recorded_derivations_to_replay(self) -> None:
        self.derivation_record()
        self.edit(lambda r: r["notes"].__setitem__("refused_result", self.GARBAGE))
        found = self.assertUnknown()
        self.assertEqual(found.step, "S7.3")
        self.assertIsNone(found.check_id)


if __name__ == "__main__":
    unittest.main()
