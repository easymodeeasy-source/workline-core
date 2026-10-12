"""RB11 RT-1a, the recorded-cancel step S3.4 of START's control flow (rev-11 TFI §B.1; ADM §A.1 S3.4, §A.2).

For every ALLOW raising call of ``_cancel_to_finish`` (``_read_cancel_record``,
``_prove_cancel``, and ``ops._recorded_stages`` through them) a record whose FIRST
refusal is that call: the probe says ``pending_reconcile_required`` with that
call's check ID, and a real ``start()`` refuses at that same call (T-B01 / T-B02,
PO-30). For the excluded calls of the same step - the ones that read the Project
view, HEAD or the filesystem through the very same ``refuse`` factory - the probe
says ``unknown_or_invalid`` (T-B03, T-B41), first refusal first (T-B43), and a
cancel the rest of the resume would refuse is never a reconcile (T-B29).
"""

from __future__ import annotations

import copy
import unittest

from start_probe_helpers import EVENT_LOG, ProbeCase
from status_helpers import append_events
from workline import start as st, start_probe
from workline.create import RelatedSpec, RelationSpec, WorkSpec, create_standalone_work
from workline.ids import new_id
from workline.ops import Replan
from workline.state import ProjectView
from workline.store import render_relations


class CancelCase(ProbeCase):
    def setUp(self) -> None:
        super().setUp()
        self.L1 = f"{self.w1}:lifecycle:1"
        self.WORKS = f"{self.w1}:cancel:0:works"
        self.REMOVE = f"{self.w1}:cancel:0:remove"

    def decision(self, record: dict) -> dict:
        return self.event_effect(record, "work_cancelled")["payload"]["cancel"]

    def resubject(self, old: str, new: str, *, mode: str | None = None) -> dict:
        """The record with every mention of ``old`` read as ``new`` - but its own invocation (and mode)."""
        from workline import yamlish

        record = self.the_record()
        text = yamlish.dump(record).replace(old, new)
        edited = yamlish.load(text)
        edited["invocation"] = dict(record["invocation"], **({"mode": mode} if mode else {}))
        self.write_record(edited)
        return edited


class CancelAllowTests(CancelCase):
    """T-B01 / T-B02 per ALLOW call of the cancel step."""

    def test_2274_effects_that_cannot_be_read(self) -> None:
        self.cancel_record()
        self.edit(lambda r: r["effects"][0].__setitem__("payload", "not a mapping"))
        self.assertReconcileAt("start.2274")

    def test_2275_ops_832_a_stage_recorded_in_two_places(self) -> None:
        self.cancel_record()

        def change(record):
            moved = record["effects"].pop(1)  # lifecycle:0's second event, after everything else
            record["effects"].append(moved)
        self.edit(change)
        self.assertReconcileAt("ops.832")

    def test_2278_more_than_one_work_cancelled(self) -> None:
        self.cancel_record()

        def change(record):
            cancelled = self.event_effect(record, "work_cancelled")
            record["effects"].insert(record["effects"].index(cancelled) + 1, copy.deepcopy(cancelled))
        self.edit(change)
        self.assertReconcileAt("start.2278")

    def test_2282_a_cancel_recorded_without_its_decision(self) -> None:
        self.cancel_record()
        self.edit(lambda r: self.event_effect(r, "work_cancelled")["payload"].pop("cancel"))
        self.assertReconcileAt("start.2282")

    def test_2298_a_cancel_stage_holding_other_than_lifecycle_events(self) -> None:
        self.cancel_record()
        self.edit(lambda r: self.event_effect(r, "work_target_removed")["payload"]["record"].__setitem__("extra", "x"))
        self.assertReconcileAt("start.2298")

    def test_2305_events_other_than_the_cancel_of_one_work(self) -> None:
        self.cancel_record()
        self.edit(lambda r: self.event_effect(r, "work_target_removed")["payload"]["record"].__setitem__("entity", self.w2))
        self.assertReconcileAt("start.2305")

    def test_2309_a_cancel_stage_under_another_name(self) -> None:
        self.cancel_record()

        def change(record):
            for effect in self.effects(record, self.L1):
                effect["stage"] = f"{self.w1}:lifecycle:7"
        self.edit(change)
        self.assertReconcileAt("start.2309")

    def test_2312_reservations_that_are_not_a_mapping(self) -> None:
        self.cancel_record()
        self.edit(lambda r: r.__setitem__("reserved_ids", []))
        self.assertReconcileAt("start.2312")

    def test_2314_cancel_events_under_unreserved_ids(self) -> None:
        self.cancel_record()
        self.edit(lambda r: r["reserved_ids"].__setitem__(f"{self.L1}:event:0", new_id("event")))
        self.assertReconcileAt("start.2314")

    def test_2318_cancel_events_carrying_more_than_the_decision(self) -> None:
        self.cancel_record()
        self.edit(lambda r: self.event_effect(r, "work_target_removed")["payload"].__setitem__("extra", 1))
        self.assertReconcileAt("start.2318")

    def test_2454_a_decision_in_another_form(self) -> None:
        self.cancel_record()
        self.edit(lambda r: self.decision(r).__setitem__("version", 9))
        self.assertReconcileAt("start.2454")

    def test_2457_a_decision_naming_another_work(self) -> None:
        self.cancel_record()
        self.edit(lambda r: self.decision(r).__setitem__("work_id", self.w2))
        self.assertReconcileAt("start.2457")

    def test_2463_a_single_work_start_cancelling_another_work(self) -> None:
        self.cancel_record()
        self.resubject(self.w1, self.w2)
        self.assertReconcileAt("start.2463")

    def test_2471_a_replan_prefix_the_cancel_does_not_record(self) -> None:
        self.cancel_record()
        self.edit(lambda r: self.decision(r).__setitem__("prefix", f"{self.w1}:cancel:7"))
        self.assertReconcileAt("start.2471")

    def test_2477_replan_stages_in_another_order(self) -> None:
        self.cancel_record()

        def change(record):
            removal = self.effects(record, self.REMOVE)
            for effect in removal:
                record["effects"].remove(effect)
            first = record["effects"].index(self.effects(record, self.WORKS)[0])
            record["effects"][first:first] = removal
        self.edit(change)
        self.assertReconcileAt("start.2477")

    def test_2488_an_evidence_stage_other_than_the_phase_completion_evidence(self) -> None:
        self.cancel_record()

        def change(record):
            commit = self.effects(record, "commit:0")[0]
            stray = dict(copy.deepcopy(self.effects(record, self.REMOVE)[0]), stage=f"{self.w1}:cancel:0:achievement")
            record["effects"].insert(record["effects"].index(commit), stray)
        self.edit(change)
        self.assertReconcileAt("start.2488")

    def test_2495_a_commit_stage_under_another_name(self) -> None:
        self.cancel_record()
        self.edit(lambda r: [e.__setitem__("stage", "commit:1") for e in self.effects(r, "commit:0")])
        self.assertReconcileAt("start.2495")

    def test_2504_a_terminal_stage_before_the_cancel_no_commit_finalized(self) -> None:
        self.cancel_record()
        self.edit(lambda r: self.event_effect(r, "work_target_added")["payload"]["record"].__setitem__("type", "work_completed"))
        self.assertReconcileAt("start.2504")

    def test_2510_no_id_reserved_for_a_new_work(self) -> None:
        self.cancel_record()
        self.edit(lambda r: r["reserved_ids"].pop(f"{self.WORKS}:work:n1"))
        self.assertReconcileAt("start.2510")

    def test_2518_one_reserved_id_used_twice(self) -> None:
        self.cancel_record()
        self.edit(lambda r: r["reserved_ids"].__setitem__(f"{self.WORKS}:rel:1", r["reserved_ids"][f"{self.WORKS}:rel:0"]))
        self.assertReconcileAt("start.2518")

    def test_2542_new_works_the_registration_cannot_write(self) -> None:
        self.cancel_record()
        self.edit(lambda r: self.effects(r, self.WORKS, "write_file")[0]["payload"].__setitem__("path", ["not", "a", "path"]))
        self.assertReconcileAt("start.2542")

    def test_2544_a_works_stage_other_than_the_registration_decided(self) -> None:
        self.cancel_record()

        def change(record):
            payload = self.effects(record, self.WORKS, "write_file")[0]["payload"]
            payload["content"] = payload["content"].replace("# N1", "# N2")
        self.edit(change)
        self.assertReconcileAt("start.2544")

    def test_2547_a_relations_stage_other_than_the_decided_additions(self) -> None:
        replan = Replan(remove_relation_ids=(self.rel("requires_completion", self.w1, self.i1),),
                        add_relations=(RelationSpec("planned_next", self.w2, self.i1),))
        self.cancel_record(replan=replan)
        self.edit(lambda r: self.effects(r, f"{self.w1}:cancel:0:relations")[0]["payload"]["record"].__setitem__("type", "requires_completion"))
        self.assertReconcileAt("start.2547")

    def test_2550_a_remove_stage_other_than_the_decided_removals(self) -> None:
        self.cancel_record()
        self.edit(lambda r: self.effects(r, self.REMOVE)[0]["payload"]["record"].__setitem__("to", self.w2))
        self.assertReconcileAt("start.2550")

    def test_2557_file_effects_that_cannot_be_read(self) -> None:
        self.cancel_record()

        def change(record):
            stray = {"seq": 0, "stage": "stray:0", "kind": "write_file", "payload": {"content": "x"}, "applied": True}
            record["effects"].insert(record["effects"].index(self.effects(record, self.L1)[0]), stray)
        self.edit(change)
        self.assertReconcileAt("start.2557")

    def test_2568_a_commit_stage_other_than_the_commit_carrying_the_cancel(self) -> None:
        self.cancel_record()
        self.edit(lambda r: self.effects(r, "commit:0")[0]["payload"].__setitem__("message", "chore(workline): hold W-01"))
        self.assertReconcileAt("start.2568")


class CancelExcludedTests(CancelCase):
    """T-B03 / T-B41: the same step's view, HEAD and filesystem refusals - same factories - are never a reconcile."""

    def test_2461_the_cancelled_work_does_not_resolve(self) -> None:
        self.cancel_record()
        self.resubject(self.w1, new_id("work"))
        self.assertUnknown("start.2461", start_check="start.2461")

    def test_2465_the_cancelled_work_outside_the_phase_of_the_entry(self) -> None:
        standalone = create_standalone_work(self.store, WorkSpec("S", "s")).work_id
        self.cancel_record()
        self.resubject(self.w1, standalone, mode="outer")
        self.assertUnknown("start.2465", start_check="start.2465")

    def test_2571_ops_853_a_file_effect_applied_with_an_unexpected_result(self) -> None:
        record = self.cancel_record()
        written = self.store.root / self.effects(record, self.WORKS, "write_file")[0]["payload"]["path"]
        # still a Work the Project reads, but not the bytes the cancel wrote: classified applied_mismatch
        written.write_text(written.read_text(encoding="utf-8").replace("# N1", "# N1 edited by someone else"),
                           encoding="utf-8")
        self.assertUnknown("ops.853", start_check="ops.853")

    def test_2573_cancel_events_already_in_head(self) -> None:
        self.cancel_record("before commit")
        self.commit_by_hand(EVENT_LOG)
        self.assertUnknown("start.2573", start_check="start.2573")

    def test_2601_a_cancel_judged_on_a_view_it_never_stood_on(self) -> None:
        self.cancel_record("before commit")
        # someone else held the Work in between: without the cancel it stands held, not in progress
        append_events(self.store, ("work_target_removed", self.w1), ("work_held", self.w1))
        self.assertUnknown("start.2601", start_check="start.2601")

    def test_2611_a_relation_to_remove_the_project_no_longer_holds(self) -> None:
        self.cancel_record("works applied")
        view = ProjectView.load(self.store)
        kept = [r for r in view.roadmap_relations if r.id != self.rel("requires_completion", self.w1, self.i1)]
        (self.store.root / ".workline" / "relations" / "roadmap.yaml").write_text(render_relations(kept), encoding="utf-8")
        self.assertUnknown("start.2611", start_check="start.2611")

    def test_t_b43_a_view_refusal_first_then_the_record_defect_once_the_view_is_restored(self) -> None:
        """T-B43: first refusal 2465 (V) with a later R defect (2471): unknown; the view put back: reconcile at 2471."""
        self.cancel_record()
        self.resubject(self.w1, self.w2, mode="outer")
        self.edit(lambda r: self.decision(r).__setitem__("prefix", f"{self.w2}:cancel:7"))
        work_file = self.store.root / ".workline" / "works" / f"{self.w2}.md"
        original = work_file.read_bytes()
        work_file.write_bytes(original.replace(self.pa.encode(), new_id("phase").encode()))
        self.assertUnknown("start.2465", start_check="start.2465")
        work_file.write_bytes(original)
        self.assertReconcileAt("start.2471")

    def test_t_b29_a_cancel_the_rest_of_the_resume_would_refuse_is_never_a_reconcile(self) -> None:
        """T-B29 (CONTEXT, BL-077): a stranded cancel (_refuse_before_replay, V) stays unknown_or_invalid; N4 refuses."""
        (self.store.root / "doc.md").write_text("doc\n", encoding="utf-8")
        replan = Replan(remove_relation_ids=(self.rel("requires_completion", self.w1, self.i1),),
                        add_relations=(RelationSpec("requires_completion", "r", self.i1),),
                        new_works={"r": WorkSpec("R", "r", phase_id=self.pa, roadmap_id=self.rid,
                                                 related=(RelatedSpec("bogus_type", "doc.md"),))})
        self.cancel_record("cancel recorded", replan)
        found = self.assertUnknown()
        self.assertEqual(found.step, "S3.4")
        refused = self.real_start()
        self.assertEqual(refused.code, "validation_failed")
        self.assertIsNone(getattr(refused, "check_id", None))


class CancelReadOnlyTests(CancelCase):
    def test_a_proven_cancel_whose_replay_would_write_is_not_claimed(self) -> None:
        """S6.2 on the cancel path: the recorded commit is not applied yet, so nothing after the replay is claimed."""
        self.cancel_record()
        self.assertUnknown(code=start_probe.POST_REPLAY_NOT_READ_ONLY)


if __name__ == "__main__":
    unittest.main()
