"""A recovery finalization is proven against the display it decided on, not the one shown now (BL-047).

A cancel, a hold and START's plan exclusion each end in one commit whose message
shows a reader which Work it was about, by the display the Project showed that
Work under. Proving a recorded finalization rebuilt that message from the Work's
display *now*, so a person renumbering a Work - a display has no uniqueness rule,
nothing is looked up by it, a duplicate leaves the Project valid (BL-045) -
refused an operation whose decision was recorded, whose commit may already have
been made and pushed, and left only the record to close. It stayed
``reconcile required`` for good, blocked every other Work behind its write scope,
and said the record held the wrong thing when the record was right.

Each of the three now records the display it decided on with its decision - in
the save before the one that records the commit - and proves the recorded message
against that. A record written before START kept one is proven by the shape of
its own finalization instead: which kind of message it is, and that it carries a
display at all. That still tells a cancel's commit from a hold's, a derive's, a
branch's, a completion's, a plan exclusion's, a fix-planned or a result commit,
and from anything that is not one of them; only two displays of the same kind
cannot be told apart, which is the one thing such a record cannot show at all.
"""

from __future__ import annotations

import re
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from workline import gitops
from workline import start as st
from workline import yamlish
from workline.create import RelationSpec, WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, StopError
from workline.mutation import Mutation, MutationController
from workline.ops import DECIDED_DISPLAY, Replan, finalization_message, finalization_proven
from workline.state import ProjectView
from workline.store import ProjectStore

#: Every message an operation writes for a Work, so a finalization proof is shown to tell them apart.
OTHER_KINDS = [
    "chore(workline): derive from W-01",
    "chore(workline): branch from W-01",
    "chore(workline): complete W-01",
    "chore(workline): W-01 NG; fix planned",
    "chore(workline): W-01 W1",
    "not a workline message",
]


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


def after_recording(pattern: str):
    """Stop right after a stage matching ``pattern`` is durably recorded, none of it applied."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        real(mutation, stage, effects)
        if re.search(pattern, stage):
            raise Interrupted(f"recorded {stage}")

    return mock.patch.object(Mutation, "add_effects", fire)


def around_push(*, pushed: bool):
    """Stop just before (``pushed=False``) or just after (``pushed=True``) the push of a commit stage."""
    real = MutationController.apply_effect

    def fire(controller, record):
        ours = record["kind"] == "git_push"
        if ours and not pushed:
            raise Interrupted("committed, not pushed")
        result = real(controller, record)
        if ours and pushed:
            raise Interrupted("pushed")
        return result

    return mock.patch.object(MutationController, "apply_effect", fire)


def before_committing():
    """Stop once everything before the finalization is applied, before that commit is recorded."""

    def fire(*args, **kwargs):
        raise Interrupted("before the commit is recorded")

    return mock.patch.object(gitops, "finalize", fire)


class DisplayCase(WorklineTestCase):
    """A Project, and the ways a person changes a Work file while an operation waits to be finished."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.root = self.store.root

    # the Work file, as a person edits it --------------------------------------
    def work_path(self, work_id: str):
        return self.root / ProjectStore.entity_rel_path("work", work_id)

    def set_meta(self, work_id: str, key: str, value: str) -> str:
        path = self.work_path(work_id)
        before = path.read_text(encoding="utf-8")
        after = re.sub(rf"^{key}: .*$", f"{key}: {value}", before, count=1, flags=re.MULTILINE)
        self.assertNotEqual(after, before, f"{key} not changed in {path}")
        path.write_text(after, encoding="utf-8", newline="\n")
        return before

    def restore(self, work_id: str, text: str) -> None:
        self.work_path(work_id).write_text(text, encoding="utf-8", newline="\n")

    def commit_work_file(self, work_id: str, message: str) -> None:
        relative = ProjectStore.entity_rel_path("work", work_id)
        git(self.root, "add", "--", relative)
        git(self.root, "commit", "-q", "-m", message, "--", relative)

    def append_body(self, work_id: str, line: str) -> None:
        path = self.work_path(work_id)
        path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + f"\n\n{line}\n", encoding="utf-8", newline="\n")

    # observation ---------------------------------------------------------------
    def display(self, work_id: str) -> str:
        return ProjectView.load(self.store).works[work_id].display

    def subjects(self) -> list[str]:
        return git(self.root, "log", "--format=%s").splitlines()

    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote_path(), "rev-parse", "main").strip()

    def pending(self) -> list[dict]:
        return MutationController(self.store).list_pending()

    def interrupt(self, window, call) -> dict:
        with window, self.assertRaises(Interrupted):
            call()
        (record,) = self.pending()
        return record

    def snapshot(self) -> dict:
        return {
            "records": {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))},
            "head": self.head(),
            "remote": self.remote_head(),
        }

    def record_of(self, mutation_id: str) -> dict:
        path = MutationController(self.store).intent_path(mutation_id)
        return yamlish.load(path.read_text(encoding="utf-8"))

    def edit_record(self, mutation_id: str, change) -> None:
        path = MutationController(self.store).intent_path(mutation_id)
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8")

    def set_recorded_message(self, mutation_id: str, message: str) -> None:
        def change(record):
            for effect in record["effects"]:
                if effect["kind"] == "git_commit":
                    effect["payload"]["message"] = message

        self.edit_record(mutation_id, change)

    def drop_recorded_display(self, mutation_id: str) -> None:
        """The record as one written before the display was recorded with the decision holds it.

        A cancel and a hold recorded a decision of their own before this change,
        so only the display leaves them; a plan exclusion's decision is the
        display, so the whole of it goes.
        """
        def change(record):
            for effect in record["effects"]:
                payload = effect.get("payload", {})
                payload.pop("exclusion", None)
                for decision in payload.values():
                    if isinstance(decision, dict) and DECIDED_DISPLAY in decision:
                        decision.pop(DECIDED_DISPLAY)

        self.edit_record(mutation_id, change)

    def assertUntouched(self, call, before: dict) -> ReconcileRequired:
        with self.assertRaises(ReconcileRequired) as caught:
            call()
        after = self.snapshot()
        self.assertEqual(after["records"], before["records"], "the record must be left exactly as it is")
        self.assertEqual(after["head"], before["head"])
        self.assertEqual(after["remote"], before["remote"])
        self.assertTrue(self.pending(), "a refused retry leaves the mutation pending")
        return caught.exception


# --------------------------------------------------------------------------- cancel
class CancelCase(DisplayCase):
    def setUp(self) -> None:
        super().setUp()
        roadmap = self.simple_roadmap(self.store)
        self.phase = roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, self.phase, confirmation=True)
        self.w1, self.i1, self.c1 = entry.work_ids["w1"], entry.integration_id, entry.confirmation_id
        st.start(self.store, self.w1, "single-work", completing_executor(self.store))
        self.replan = Replan(
            remove_relation_ids=(self.relation(self.w1, self.i1), self.relation(self.i1, self.c1)),
            add_relations=(RelationSpec("requires_completion", self.w1, "i2"), RelationSpec("requires_completion", "i2", self.c1)),
            new_works={"i2": WorkSpec("I2", "i2", phase_id=self.phase, roadmap_id=roadmap.roadmap_id,
                                      work_kind="phase_integration_check")},
        )
        self.cancel = st.Cancel(self.replan, "scope")

    def relation(self, from_id: str, to: str) -> str:
        (found,) = [r.id for r in ProjectView.load(self.store).roadmap_relations
                    if (r.type, r.from_id, r.to) == ("requires_completion", from_id, to)]
        return found

    def executor(self, ctx: st.ExecutionContext):
        return self.cancel if ctx.work.id == self.i1 else completing_executor(self.store)(ctx)

    def run_cancel(self):
        return st.start(self.store, self.i1, "single-work", self.executor)


CANCEL_WINDOWS = {
    "decision recorded": lambda: after_recording(r":lifecycle:1$"),
    "replan recorded": lambda: after_recording(r":cancel:0:(works|relations)$"),
    "before the commit": before_committing,
    "commit recorded": lambda: after_recording(r"^commit:\d+$"),
    "committed": lambda: around_push(pushed=False),
    "pushed": lambda: around_push(pushed=True),
}


class CancelTests(CancelCase):
    def test_a_display_only_edit_still_finishes_the_cancel(self) -> None:
        """1-4: the display edited after the decision, in every window the cancel can stop in."""
        for window, make in CANCEL_WINDOWS.items():
            with self.subTest(window=window):
                self.setUp()
                self.interrupt(make(), self.run_cancel)
                decided = self.display(self.i1)
                self.set_meta(self.i1, "display", "W-99")
                result = self.run_cancel()
                self.assertEqual(result.status, "cancelled")
                self.assertEqual(result.work_id, self.i1)
                self.assertEqual(self.pending(), [])
                # The commit carries the display the cancel decided on, once, whichever window it stopped in.
                self.assertEqual(self.subjects().count(finalization_message("cancel", decided)), 1)
                self.assertNotIn(finalization_message("cancel", "W-99"), self.subjects())
                self.assertEqual(self.head(), self.remote_head())

    def test_b_control_no_edit(self) -> None:
        for window, make in CANCEL_WINDOWS.items():
            with self.subTest(window=window):
                self.setUp()
                self.interrupt(make(), self.run_cancel)
                decided = self.display(self.i1)
                self.assertEqual(self.run_cancel().status, "cancelled")
                self.assertEqual(self.subjects().count(finalization_message("cancel", decided)), 1)

    def test_c_control_edit_then_restore(self) -> None:
        self.interrupt(CANCEL_WINDOWS["pushed"](), self.run_cancel)
        before = self.set_meta(self.i1, "display", "W-99")
        self.restore(self.i1, before)
        self.assertEqual(self.run_cancel().status, "cancelled")

    def test_d_display_edit_committed_separately(self) -> None:
        """The person's renumbering is its own commit, so the tree is clean at the retry."""
        self.interrupt(CANCEL_WINDOWS["commit recorded"](), self.run_cancel)
        decided = self.display(self.i1)
        self.set_meta(self.i1, "display", "W-99")
        self.commit_work_file(self.i1, "docs: renumber")
        self.assertEqual(self.run_cancel().status, "cancelled")
        self.assertEqual(self.subjects().count(finalization_message("cancel", decided)), 1)

    def test_e_body_edit_is_unaffected(self) -> None:
        self.interrupt(CANCEL_WINDOWS["commit recorded"](), self.run_cancel)
        self.append_body(self.i1, "a note someone left")
        self.assertEqual(self.run_cancel().status, "cancelled")

    def test_f_stable_work_id_replacement_still_stops(self) -> None:
        """A Work file declaring another ID is refused where it always was, before any of this."""
        for window in ("commit recorded", "pushed"):
            with self.subTest(window=window):
                self.setUp()
                self.interrupt(CANCEL_WINDOWS[window](), self.run_cancel)
                self.set_meta(self.i1, "id", "w_01ARZ3NDEKTSV4RRFFQ69G5FAV")
                with self.assertRaises(StopError) as caught:
                    self.run_cancel()
                self.assertEqual(caught.exception.code, "entity_invalid")
                self.assertTrue(self.pending())

    def test_g_the_decision_records_the_display(self) -> None:
        record = self.record_of(self.interrupt(CANCEL_WINDOWS["decision recorded"](), self.run_cancel)["mutation_id"])
        (cancelled,) = [effect for effect in record["effects"]
                        if effect["kind"] == "append_event" and effect["payload"]["record"]["type"] == "work_cancelled"]
        self.assertEqual(cancelled["payload"]["cancel"][DECIDED_DISPLAY], "W-02")

    def test_h_a_new_record_is_held_to_the_exact_message(self) -> None:
        """Every other message an operation writes, and a tail of its own, is still refused."""
        for message in OTHER_KINDS + [
            finalization_message("hold", "W-02"),
            finalization_message("plan_excluded", "W-02"),
            finalization_message("cancel", "W-02 and more"),
            finalization_message("cancel", "W-99"),
            "chore(workline): cancel ",
        ]:
            with self.subTest(message=message):
                self.setUp()
                pending = self.interrupt(CANCEL_WINDOWS["commit recorded"](), self.run_cancel)
                self.set_recorded_message(pending["mutation_id"], message)
                before = self.snapshot()
                self.assertUntouched(self.run_cancel, before)

    def test_i_a_legacy_record_finishes_by_the_shape_of_its_finalization(self) -> None:
        """A record written before the display was recorded: the same display resumes, and so does another."""
        for display in ("W-02", "W-99"):
            with self.subTest(display=display):
                self.setUp()
                pending = self.interrupt(CANCEL_WINDOWS["commit recorded"](), self.run_cancel)
                self.drop_recorded_display(pending["mutation_id"])
                self.set_recorded_message(pending["mutation_id"], finalization_message("cancel", display))
                self.assertEqual(self.run_cancel().status, "cancelled")
                self.assertEqual(self.subjects().count(finalization_message("cancel", display)), 1)

    def test_j_a_legacy_record_still_refuses_another_kind_or_no_display(self) -> None:
        for message in OTHER_KINDS + [
            finalization_message("hold", "W-02"),
            finalization_message("plan_excluded", "W-02"),
            "chore(workline): cancel ",
            "chore(workline): cancel",
        ]:
            with self.subTest(message=message):
                self.setUp()
                pending = self.interrupt(CANCEL_WINDOWS["commit recorded"](), self.run_cancel)
                self.drop_recorded_display(pending["mutation_id"])
                self.set_recorded_message(pending["mutation_id"], message)
                before = self.snapshot()
                self.assertUntouched(self.run_cancel, before)

    def test_k_a_decision_carrying_an_unreadable_display_is_refused(self) -> None:
        for display in ("", 7, None, ["W-02"]):
            with self.subTest(display=display):
                self.setUp()
                pending = self.interrupt(CANCEL_WINDOWS["commit recorded"](), self.run_cancel)

                def change(record):
                    for effect in record["effects"]:
                        decision = effect.get("payload", {}).get("cancel")
                        if isinstance(decision, dict):
                            decision[DECIDED_DISPLAY] = display

                self.edit_record(pending["mutation_id"], change)
                before = self.snapshot()
                self.assertUntouched(self.run_cancel, before)


# --------------------------------------------------------------------------- hold
class HoldCase(DisplayCase):
    def setUp(self) -> None:
        super().setUp()
        roadmap = self.simple_roadmap(self.store)
        entry = self.simple_entry(self.store, roadmap.phase_ids["a"], {"w1": "W1 done", "w2": "W2 done"}, entry="w1")
        self.w1 = entry.work_ids["w1"]

    def run_hold(self, reason: object = "later"):
        return st.start(self.store, self.w1, "single-work", lambda ctx: st.Hold(reason))


HOLD_WINDOWS = {
    "decision recorded": lambda: after_recording(r":lifecycle:1$"),
    "committed": lambda: around_push(pushed=False),
}


class HoldTests(HoldCase):
    def test_a_display_only_edit_still_finishes_the_hold(self) -> None:
        for window, make in HOLD_WINDOWS.items():
            with self.subTest(window=window):
                self.setUp()
                self.interrupt(make(), self.run_hold)
                decided = self.display(self.w1)
                self.set_meta(self.w1, "display", "W-99")
                result = self.run_hold()
                self.assertEqual((result.status, result.detail), ("held", "later"))
                self.assertEqual(self.pending(), [])
                self.assertEqual(self.subjects().count(finalization_message("hold", decided)), 1)
                self.assertNotIn(finalization_message("hold", "W-99"), self.subjects())

    def test_b_controls(self) -> None:
        for window, make in HOLD_WINDOWS.items():
            with self.subTest(window=window, control="no edit"):
                self.setUp()
                self.interrupt(make(), self.run_hold)
                self.assertEqual(self.run_hold().status, "held")
            with self.subTest(window=window, control="edit then restore"):
                self.setUp()
                self.interrupt(make(), self.run_hold)
                self.restore(self.w1, self.set_meta(self.w1, "display", "W-99"))
                self.assertEqual(self.run_hold().status, "held")

    def test_c_the_decision_records_the_display_beside_the_reason(self) -> None:
        record = self.record_of(self.interrupt(HOLD_WINDOWS["decision recorded"](), self.run_hold)["mutation_id"])
        (held,) = [effect for effect in record["effects"]
                   if effect["kind"] == "append_event" and effect["payload"]["record"]["type"] == "work_held"]
        self.assertEqual(held["payload"]["hold"], {"version": 1, "reason": "later", DECIDED_DISPLAY: "W-01"})

    def test_d_a_reason_the_record_cannot_keep_records_no_decision_and_still_finishes(self) -> None:
        """BL-044's rule is untouched: such a reason records no decision at all, display included.

        The display is kept beside the reason, not instead of it, so a hold that
        recorded neither is finished exactly as one written before START kept
        either: by the shape of its own finalization, whatever the Project shows
        the Work as now.
        """
        pending = self.interrupt(HOLD_WINDOWS["decision recorded"](), lambda: self.run_hold(1.5))
        (held,) = [effect for effect in self.record_of(pending["mutation_id"])["effects"]
                   if effect["kind"] == "append_event" and effect["payload"]["record"]["type"] == "work_held"]
        self.assertEqual(set(held["payload"]), {"record"})
        self.set_meta(self.w1, "display", "W-99")
        result = self.run_hold(1.5)
        self.assertEqual((result.status, result.detail), ("held", None))
        self.assertEqual(self.subjects().count(finalization_message("hold", "W-99")), 1)

    def test_e_a_new_record_is_held_to_the_exact_message(self) -> None:
        for message in OTHER_KINDS + [finalization_message("cancel", "W-01"),
                                      finalization_message("hold", "W-99"),
                                      finalization_message("hold", "W-01 and more")]:
            with self.subTest(message=message):
                self.setUp()
                pending = self.interrupt(HOLD_WINDOWS["committed"](), self.run_hold)
                self.set_recorded_message(pending["mutation_id"], message)
                before = self.snapshot()
                self.assertUntouched(self.run_hold, before)

    def test_f_a_legacy_record_finishes_by_shape_and_refuses_another_kind(self) -> None:
        pending = self.interrupt(HOLD_WINDOWS["committed"](), self.run_hold)
        self.drop_recorded_display(pending["mutation_id"])
        self.assertEqual(self.run_hold().status, "held")
        for message in OTHER_KINDS + [finalization_message("cancel", "W-01"), "chore(workline): hold "]:
            with self.subTest(message=message):
                self.setUp()
                pending = self.interrupt(HOLD_WINDOWS["committed"](), self.run_hold)
                self.drop_recorded_display(pending["mutation_id"])
                self.set_recorded_message(pending["mutation_id"], message)
                before = self.snapshot()
                self.assertUntouched(self.run_hold, before)


# --------------------------------------------------------------------------- START plan exclusion
class ExclusionCase(DisplayCase):
    def setUp(self) -> None:
        super().setUp()
        self.s1 = create_standalone_work(self.store, WorkSpec("S1", "s1")).work_id
        self.s2 = create_standalone_work(self.store, WorkSpec("S2", "s2")).work_id
        self.replan = Replan(add_relations=(RelationSpec("planned_next", self.s1, self.s2),))

    def run_exclusion(self):
        return st.plan_exclude_standalone_work(self.store, self.s1, self.replan)


EXCLUSION_WINDOWS = {
    "event recorded": lambda: after_recording(r"^event$"),
    "committed": lambda: around_push(pushed=False),
}


class ExclusionTests(ExclusionCase):
    def test_a_display_only_edit_still_finishes_the_exclusion(self) -> None:
        for window, make in EXCLUSION_WINDOWS.items():
            with self.subTest(window=window):
                self.setUp()
                self.interrupt(make(), self.run_exclusion)
                decided = self.display(self.s1)
                self.set_meta(self.s1, "display", "W-99")
                self.assertEqual(self.run_exclusion().status, "plan_excluded")
                self.assertEqual(self.pending(), [])
                self.assertEqual(self.subjects().count(finalization_message("plan_excluded", decided)), 1)
                self.assertNotIn(finalization_message("plan_excluded", "W-99"), self.subjects())

    def test_b_controls(self) -> None:
        for window, make in EXCLUSION_WINDOWS.items():
            with self.subTest(window=window, control="no edit"):
                self.setUp()
                self.interrupt(make(), self.run_exclusion)
                self.assertEqual(self.run_exclusion().status, "plan_excluded")
            with self.subTest(window=window, control="edit then restore"):
                self.setUp()
                self.interrupt(make(), self.run_exclusion)
                self.restore(self.s1, self.set_meta(self.s1, "display", "W-99"))
                self.assertEqual(self.run_exclusion().status, "plan_excluded")

    def test_c_stable_work_id_replacement_still_stops(self) -> None:
        self.interrupt(EXCLUSION_WINDOWS["committed"](), self.run_exclusion)
        self.set_meta(self.s1, "id", "w_01ARZ3NDEKTSV4RRFFQ69G5FAV")
        with self.assertRaises(StopError) as caught:
            self.run_exclusion()
        self.assertEqual(caught.exception.code, "entity_invalid")
        self.assertTrue(self.pending())

    def test_d_the_event_records_the_display(self) -> None:
        record = self.record_of(self.interrupt(EXCLUSION_WINDOWS["event recorded"](), self.run_exclusion)["mutation_id"])
        (event,) = [effect for effect in record["effects"] if effect["stage"] == "event"]
        self.assertEqual(event["payload"]["exclusion"], {"version": 1, DECIDED_DISPLAY: self.display(self.s1)})

    def test_e_a_new_record_is_held_to_the_exact_message(self) -> None:
        for message in OTHER_KINDS + [finalization_message("cancel", "W-01"),
                                      finalization_message("plan_excluded", "W-99"),
                                      finalization_message("plan_excluded", "W-01 and more")]:
            with self.subTest(message=message):
                self.setUp()
                pending = self.interrupt(EXCLUSION_WINDOWS["committed"](), self.run_exclusion)
                self.set_recorded_message(pending["mutation_id"], message)
                before = self.snapshot()
                self.assertUntouched(self.run_exclusion, before)

    def test_f_a_legacy_record_finishes_by_shape_and_refuses_another_kind(self) -> None:
        pending = self.interrupt(EXCLUSION_WINDOWS["committed"](), self.run_exclusion)
        self.drop_recorded_display(pending["mutation_id"])
        self.assertEqual(self.run_exclusion().status, "plan_excluded")
        for message in OTHER_KINDS + [finalization_message("cancel", "W-01"), "chore(workline): plan_excluded "]:
            with self.subTest(message=message):
                self.setUp()
                pending = self.interrupt(EXCLUSION_WINDOWS["committed"](), self.run_exclusion)
                self.drop_recorded_display(pending["mutation_id"])
                self.set_recorded_message(pending["mutation_id"], message)
                before = self.snapshot()
                self.assertUntouched(self.run_exclusion, before)

    def test_g_a_recorded_decision_that_is_not_one_is_refused(self) -> None:
        for decision in ({"version": 2, DECIDED_DISPLAY: "W-01"}, {"version": 1}, {"version": 1, DECIDED_DISPLAY: ""},
                         {"version": 1, DECIDED_DISPLAY: "W-01", "extra": 1}, "W-01"):
            with self.subTest(decision=decision):
                self.setUp()
                pending = self.interrupt(EXCLUSION_WINDOWS["committed"](), self.run_exclusion)

                def change(record):
                    for effect in record["effects"]:
                        if effect["stage"] == "event":
                            effect["payload"]["exclusion"] = decision

                self.edit_record(pending["mutation_id"], change)
                before = self.snapshot()
                self.assertUntouched(self.run_exclusion, before)


# --------------------------------------------------------------------------- the rule itself
class FinalizationProofTests(unittest.TestCase):
    """What the shared proof accepts, kind by kind, with and without a recorded display."""

    def test_a_with_a_recorded_display_only_that_exact_message(self) -> None:
        for kind in ("cancel", "hold", "plan_excluded"):
            with self.subTest(kind=kind):
                self.assertTrue(finalization_proven(kind, "W-02", finalization_message(kind, "W-02")))
                for message in [finalization_message(kind, "W-99"),
                                finalization_message(kind, "W-02 and more"),
                                finalization_message(kind, "W-02").rstrip(),
                                finalization_message(kind, ""), None, 7]:
                    if message == finalization_message(kind, "W-02"):
                        continue
                    self.assertFalse(finalization_proven(kind, "W-02", message), message)

    def test_b_without_one_that_kind_carrying_a_display(self) -> None:
        for kind in ("cancel", "hold", "plan_excluded"):
            with self.subTest(kind=kind):
                for display in ("W-02", "W-99", "W-02 and more", " "):
                    self.assertTrue(finalization_proven(kind, None, finalization_message(kind, display)), display)
                others = [finalization_message(other, "W-02") for other in ("cancel", "hold", "plan_excluded")
                          if other != kind]
                for message in others + OTHER_KINDS + [finalization_message(kind, ""),
                                                       finalization_message(kind, "").rstrip(), "", None, 7]:
                    self.assertFalse(finalization_proven(kind, None, message), message)


if __name__ == "__main__":
    unittest.main()
