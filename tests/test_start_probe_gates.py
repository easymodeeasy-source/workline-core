"""RB11 RT-1a repair rows (review RB11RT-REVIEW-9c85f30: RTR-1, RTR-3, RTR-6).

* RTR-1 (T-B03 / §41.5 "920 filesystem"): a READABLE kept refused result - left by a real START that refused its own
  result over a pre-existing change - is never followed: START would finish the Work from it
  (``_reuse_refused_result``, 916 / 920 or its writes), so the probe ends ``unknown_or_invalid`` at S7.3, never S8.
* RTR-6: the individual S7.2 gates (terminal, roadmap_inactive, read targets, protected targets, the COMPLETED branch)
  and the outer-mode "not followed" guards, each a row of its own.
* RTR-3 (BRIEF §41.3 "no other reason value"): the reason codes S6.1 may report.
"""

from __future__ import annotations

import unittest
from unittest import mock

from start_probe_helpers import EVENT_LOG, Interrupted, ProbeCase
from status_helpers import append_events
from workline import start as st, start_probe
from workline.ids import new_id
from workline.mutation import Mutation
from workline.store import Relation, render_relations

AT = "2026-10-12T00:00:00+00:00"


class GateCase(ProbeCase):
    def add_related(self, from_id: str, rel_type: str, to: str) -> None:
        relations = self.store.read_relation_file("related")
        relations.append(Relation(new_id("relation"), rel_type, from_id, to))
        self.store.related_yaml.write_text(render_relations(relations), encoding="utf-8", newline="")

    def finished_but_not_closed(self, outcome) -> dict:
        """A START that did everything, its record pending only because the close itself was interrupted."""
        with mock.patch.object(Mutation, "complete", side_effect=Interrupted("before the record is closed")):
            with self.assertRaises(Interrupted):
                st.start(self.store, self.w1, "single-work", outcome)
        return self.the_record()

    def to_outer(self) -> None:
        self.edit(lambda r: r["invocation"].__setitem__("mode", "outer"))


class KeptRefusedResultTests(GateCase):
    """RTR-1: a readable kept refused result."""

    def refused_over_a_preexisting_change(self) -> dict:
        (self.store.root / "result_w1.txt").write_text("the person's own text\n", encoding="utf-8")

        def done(ctx):
            (self.store.root / "result_w1.txt").write_text("the Work's result\n", encoding="utf-8")
            return st.Completed(("result_w1.txt",))

        with self.assertRaises(st.StopError) as refused:
            st.start(self.store, self.w1, "single-work", done)
        self.assertEqual(refused.exception.code, "dirty_overlap")
        record = self.the_record()
        note = record["notes"]["refused_result"]
        self.assertTrue(st._reusable_result(note), "a kept result START reads back")
        self.assertEqual(note["work_id"], self.w1)
        return record

    def test_while_the_change_is_still_there_start_refuses_at_916_and_the_probe_never_says_resumable(self) -> None:
        self.refused_over_a_preexisting_change()
        found = self.assertUnknown()
        self.assertEqual((found.step, found.check_id), ("S7.3", None), found)
        refused = self.real_start()
        self.assertEqual((refused.code, refused.check_id), ("dirty_overlap", "start.916"))

    def test_once_the_person_resolved_it_start_finishes_from_the_kept_result_and_the_probe_still_does_not_claim(self) -> None:
        self.refused_over_a_preexisting_change()
        (self.store.root / "result_w1.txt").unlink()  # the person discarded their own change
        found = self.assertUnknown()
        self.assertEqual((found.step, found.check_id), ("S7.3", None), found)
        result = st.start(self.store, self.w1, "single-work", self.unasked())
        self.assertEqual(result.status, "completed", "START finished the Work from the kept result")
        self.assertEqual((self.store.root / "result_w1.txt").read_text(encoding="utf-8"), "the Work's result\n")

    def unasked(self):
        from start_probe_helpers import never

        return never


class RunWorkGateTests(GateCase):
    """RTR-6: each S7.2 gate on its own (START refuses there; the probe ends there, never past it)."""

    def assertGate(self, start_code: str, start_check: str, words: str) -> None:
        found = self.assertUnknown()
        self.assertEqual(found.step, "S7.2", found)
        self.assertIn(words, found.message)
        refused = self.real_start()
        self.assertEqual((refused.code, refused.check_id), (start_code, start_check))

    def test_terminal(self) -> None:
        self.question_wait_record()
        # someone else cancelled W1 by hand, its edge into the integration taken away as a cancel's replan would
        append_events(self.store, ("work_target_removed", self.w1), ("work_cancelled", self.w1))
        into = self.rel("requires_completion", self.w1, self.i1)
        kept = [r for r in self.store.read_roadmap_relations() if r.id != into]
        self.store.roadmap_yaml.write_text(render_relations(kept), encoding="utf-8", newline="")
        self.assertGate("spec_violation", "start.547", "terminal")

    def test_roadmap_inactive(self) -> None:
        self.question_wait_record()
        append_events(self.store, ("roadmap_held", self.rid))
        self.assertGate("roadmap_inactive", "start.567", "Roadmap is not active")

    def test_read_targets(self) -> None:
        self.question_wait_record()
        self.add_related(self.w1, "must_read", "missing.md")
        found = self.assertUnknown(start_check="start.272")
        self.assertEqual((found.step, found.check_id), ("S7.2", "start.272"), found)

    def test_protected_read_targets(self) -> None:
        self.question_wait_record()
        (self.store.root / "a-directory").mkdir()
        (self.store.root / "a-directory" / "inside.txt").write_text("x\n", encoding="utf-8")
        append_events(self.store, ("work_started", self.w2))
        self.add_related(self.w2, "must_read", "a-directory")
        found = self.assertUnknown(start_check="start.705")
        self.assertEqual((found.step, found.check_id), ("S7.2", "start.705"), found)

    def test_the_completed_branch_single_work_is_resumable_and_start_finishes_without_its_executor(self) -> None:
        self.finished_but_not_closed(lambda ctx: st.Completed())
        found = self.assertResumable()
        self.assertEqual(found.step, "S7.2")
        result = self.real_start()
        self.assertEqual(result.status, "completed")


class OuterGuardTests(GateCase):
    """RTR-6: where an outer continuation would go on after a finish, the probe does not follow it."""

    def test_after_the_completed_branch(self) -> None:
        """Outer mode never reaches the COMPLETED branch of the Work it finished: START's continuation chooses the next
        Work (an unstarted W2, whose lifecycle START writes first), and the probe ends there."""
        self.finished_but_not_closed(lambda ctx: st.Completed())
        self.to_outer()
        found = self.assertUnknown()
        self.assertEqual(found.step, "S7.2")
        self.assertIn("lifecycle first", found.message)

    def test_after_a_committed_move(self) -> None:
        self.finished_but_not_closed(lambda ctx: self.derive("f0", move=True))
        self.assertEqual(self.assertResumable().step, "S7.1")
        self.to_outer()
        found = self.assertUnknown()
        self.assertEqual(found.step, "S7.1")
        self.assertIn("not followed", found.message)

    def test_an_ambiguous_outer_selection(self) -> None:
        self.question_wait_record(mode="outer")
        append_events(self.store, ("work_started", self.w2), ("work_target_added", self.w2))
        found = self.assertUnknown()
        self.assertEqual(found.step, "S7.1", found)


class ReplayReasonTests(GateCase):
    """RTR-3: S6.1 reports only the replay codes the frozen text names; any other code is no_read_only_resume_probe."""

    def test_an_environmental_replay_reconcile_is_reported_with_todays_reason(self) -> None:
        self.question_wait_record()
        log = self.store.root / EVENT_LOG
        started = self.event_effect(self.the_record(), "work_started")["payload"]["record"]
        log.write_bytes(log.read_bytes().replace(started["at"].encode(), b"2001-01-01T00:00:00+00:00"))
        found = self.assertUnknown(code=start_probe.NO_PROBE)
        self.assertEqual(found.step, "S6.1")

    def test_an_effect_of_an_unknown_kind_is_reported_with_todays_reason(self) -> None:
        self.question_wait_record()
        self.edit(lambda r: r["effects"].append(
            {"seq": 99, "stage": "stray:0", "kind": "bogus_kind", "payload": {"x": 1}, "applied": True}))
        found = self.assertUnknown(code=start_probe.NO_PROBE)
        self.assertEqual(found.step, "S6.1")
        self.assertNotIn("bogus_kind", found.message, "no record data in the reason")

    def test_a_work_mode_commit_keeps_its_named_code(self) -> None:
        self.question_wait_record()
        self.edit(lambda r: r["effects"].append(
            {"seq": 99, "stage": "stray:0", "kind": "git_commit", "applied": True,
             "payload": {"mode": "review-v1-work-local-v2", "message": "x", "paths": ["x"]}}))
        found = self.assertUnknown(code=start_probe.WORK_COMMIT_NOT_INSPECTABLE)
        self.assertEqual(found.step, "S6.1")

    def test_the_reason_codes_are_exactly_the_six_the_frozen_text_names(self) -> None:
        self.assertEqual(
            {start_probe.NO_PROBE, start_probe.NOT_PROBED_GENERATION, start_probe.NOT_PROBED_PLAN_EXCLUSION,
             start_probe.POST_REPLAY_NOT_READ_ONLY, start_probe.PUSH_NEEDS_NETWORK,
             start_probe.WORK_COMMIT_NOT_INSPECTABLE},
            {"no_read_only_resume_probe", "start_operation_not_probed_review_generation",
             "start_operation_not_probed_plan_exclusion", "post_replay_not_read_only",
             "push_classification_requires_network", "work_commit_replay_not_inspectable"})
        self.assertEqual(start_probe._NAMED_REPLAY_CODES,
                         {"push_classification_requires_network", "work_commit_replay_not_inspectable"})


if __name__ == "__main__":
    unittest.main()
