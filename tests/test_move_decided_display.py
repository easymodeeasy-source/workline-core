"""A recorded move is proven against the display it was decided on, not the one shown now (BL-048).

A derivation that removes its Work's target - a temporary move, or a human
confirmation judged NG, which reaches START as one - ends that Work's cycle in
one commit whose message shows the Work by its display: ``chore(workline):
branch from <display>``, or ``chore(workline): <display> NG; fix planned``. A
resume finishes such a move from its record (BL-046), and it proved the recorded
commit by rebuilding that message from the Work the Project holds *now*. A
display has no uniqueness rule and nothing is looked up by it (BL-045), so a
person renumbering the Work after the move's commit was recorded - before the
commit was made, before it was pushed, or after, with only the record left to
close - refused the move for good. Every retry stopped the same way, the pending
record kept its write scope over the ledgers so no other operation in the
Project could run, and the refusal said the record held the wrong derivations
when the record was right.

The derivation now keeps the display it was decided on in the entry that keeps
the decision, in the save before its registration stage. A resume proves the
recorded commit exactly against the message rendered from that display, and a
commit it still has to make carries that message too. A derivation kept before
displays were is proven by the shape of its own finalization - BL-047's rule,
extended to a message whose display is followed by more text - and every other
proof of the move (its stable Work ID, its stages, its removal event, its
commit's kinds and paths, its branch and commit identity) is unchanged.
"""

from __future__ import annotations

import re
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from workline import start as st
from workline import yamlish
from workline.create import WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, StopError
from workline.mutation import Mutation, MutationController
from workline.ops import DECIDED_DISPLAY, finalization_message, finalization_proven
from workline.state import ProjectView
from workline.store import WORKLINE_DIR, ProjectStore
from workline.validate import validate_project

#: Every other message an operation writes for a Work, so a move's proof is shown to tell them apart.
OTHER_KINDS = [
    "chore(workline): derive from W-01",
    "chore(workline): complete W-01",
    "chore(workline): cancel W-01",
    "chore(workline): hold W-01",
    "chore(workline): plan_excluded W-01",
    "chore(workline): W-01 W1",
    "chore(workline): create W-01",
    "not a workline message",
]


def branch_message(display: str) -> str:
    """The message a temporary move commits, written out: what START has always rendered for it."""
    return f"chore(workline): branch from {display}"


def ng_message(display: str) -> str:
    """The message a human confirmation judged NG commits, written out."""
    return f"chore(workline): {display} NG; fix planned"


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


# --------------------------------------------------------------------------- interruption windows
def after_recording(pattern: str):
    """Stop right after a stage matching ``pattern`` is durably recorded, none of it applied."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        real(mutation, stage, effects)
        if re.search(pattern, stage):
            raise Interrupted(f"recorded {stage}")

    return mock.patch.object(Mutation, "add_effects", fire)


def before_recording(pattern: str):
    """Stop with a stage matching ``pattern`` about to be recorded."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        if re.search(pattern, stage):
            raise Interrupted(f"about to record {stage}")
        return real(mutation, stage, effects)

    return mock.patch.object(Mutation, "add_effects", fire)


def around_push(*, pushed: bool):
    """Stop just before, or just after, the push of the move's own ``commit:<n>`` stage.

    A completion finalizes under ``<Work>:finalize:<n>``, so an ``outer`` run's
    earlier pushes pass.
    """
    real = MutationController.apply_effect

    def fire(controller, record):
        ours = record["kind"] == "git_push" and re.fullmatch(r"commit:\d+", record["stage"]) is not None
        if ours and not pushed:
            raise Interrupted("committed, not pushed")
        result = real(controller, record)
        if ours and pushed:
            raise Interrupted("pushed, not recorded as pushed")
        return result

    return mock.patch.object(MutationController, "apply_effect", fire)


def before_closing():
    """Stop with every effect applied and the record not closed yet."""

    def fire(mutation):
        raise Interrupted("everything applied, the record not closed")

    return mock.patch.object(Mutation, "complete", fire)


#: Every window the move can stop in once it is decided, and what each has left to do. "decision kept" is
#: built from the record, as BL-046 builds it: a kill between keeping the decision and recording its stage.
MOVE_WINDOWS = {
    "decision kept": lambda: after_recording(r":derive:0$"),
    "registration recorded": lambda: after_recording(r":derive:0$"),
    "removal applied": lambda: before_recording(r"^commit:0$"),
    "commit recorded": lambda: after_recording(r"^commit:0$"),
    "committed": lambda: around_push(pushed=False),
    "pushed": lambda: around_push(pushed=True),
    "not closed": before_closing,
}


def by_attempt(log: list[str], script: dict, default=None):
    """Executor scripted by Work name and ``ctx.attempt``, so a resumed cycle is asked what an uninterrupted one is."""

    def execute(ctx: st.ExecutionContext):
        log.append(f"{ctx.work.name}#{ctx.attempt}")
        outcome = script.get((ctx.work.name, ctx.attempt), script.get(ctx.work.name))
        if outcome is None:
            if default is None:
                raise AssertionError(f"no outcome scripted for {ctx.work.name} attempt {ctx.attempt}")
            return default(ctx)
        return outcome(ctx) if callable(outcome) else outcome

    return execute


class MoveDisplayCase(WorklineTestCase):
    """A Project, the move under test, and the ways a person changes a Work file while it waits to be finished."""

    target: str

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.root = self.store.root
        self.ran: list[str] = []

    # the Work file, as a person edits it --------------------------------------
    def work_path(self, work_id: str):
        return self.root / ProjectStore.entity_rel_path("work", work_id)

    def set_meta(self, work_id: str, key: str, value: str) -> None:
        path = self.work_path(work_id)
        before = path.read_text(encoding="utf-8")
        after = re.sub(rf"^{key}: .*$", f"{key}: {value}", before, count=1, flags=re.MULTILINE)
        self.assertNotEqual(after, before, f"{key} not changed in {path}")
        path.write_text(after, encoding="utf-8", newline="\n")

    def commit_work_file(self, work_id: str, message: str) -> None:
        relative = ProjectStore.entity_rel_path("work", work_id)
        git(self.root, "add", "--", relative)
        git(self.root, "commit", "-q", "-m", message, "--", relative)

    def append_body(self, work_id: str, line: str) -> None:
        path = self.work_path(work_id)
        path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + f"\n\n{line}\n", encoding="utf-8", newline="\n")

    # the record ------------------------------------------------------------------
    def pending(self) -> list[dict]:
        return MutationController(self.store).list_pending()

    def record_path(self):
        (pending,) = self.pending()
        return MutationController(self.store).intent_path(pending["mutation_id"])

    def edit_record(self, change) -> None:
        path = self.record_path()
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8")

    def entries(self) -> list[dict]:
        (pending,) = self.pending()
        return pending["notes"][st._DERIVATIONS]["derivations"]

    def set_recorded_message(self, message: str) -> None:
        def change(record):
            for effect in record["effects"]:
                if effect["kind"] == "git_commit" and effect["stage"].startswith("commit:"):
                    effect["payload"]["message"] = message

        self.edit_record(change)

    def drop_recorded_display(self) -> None:
        """The record as a derivation kept before its display was holds it."""

        def change(record):
            for entry in record["notes"][st._DERIVATIONS]["derivations"]:
                entry.pop(DECIDED_DISPLAY, None)

        self.edit_record(change)

    # observation ---------------------------------------------------------------
    def display(self, work_id: str) -> str:
        return ProjectView.load(self.store).works[work_id].display

    def named(self, name: str) -> list[str]:
        return sorted(w.id for w in ProjectView.load(self.store).works.values() if w.name == name)

    def events(self, work_id: str) -> list[str]:
        return [e.type for e in ProjectView.load(self.store).events if e.entity == work_id]

    def subjects(self) -> list[str]:
        return git(self.root, "log", "--format=%s").splitlines()

    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote_path(), "rev-parse", "main").strip()

    def dirty(self) -> list[str]:
        status = git(self.root, "status", "--porcelain", "--untracked-files=all").splitlines()
        return [line for line in status if ".workline/runtime/" not in line]

    def snapshot(self) -> dict:
        """Everything a refused resume must leave exactly as it was: the records byte for byte, the Project, Git."""
        return {
            "records": {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))},
            "files": {p.relative_to(self.root).as_posix(): p.read_bytes()
                      for p in sorted((self.root / ".workline").rglob("*"))
                      if p.is_file() and "runtime" not in p.relative_to(self.root).parts},
            "head": self.head(),
            "remote": self.remote_head(),
            "dirty": self.dirty(),
        }

    def watching(self, call, executed: list[str], stages: list[str]):
        real_apply, real_add = MutationController.apply_effect, Mutation.add_effects

        def apply(controller, record):
            executed.append(record["kind"])
            return real_apply(controller, record)

        def add(mutation, stage, effects):
            stages.append(stage)
            return real_add(mutation, stage, effects)

        with mock.patch.object(MutationController, "apply_effect", apply), mock.patch.object(Mutation, "add_effects", add):
            return call()

    def interrupt(self, window: str, call) -> None:
        with MOVE_WINDOWS[window](), self.assertRaises(Interrupted):
            call()
        if window == "decision kept":
            stage = f"{self.target}:derive:0"
            self.edit_record(lambda record: record.update(
                {"effects": [e for e in record["effects"] if e["stage"] != stage]}))
        self.assertEqual(len(self.pending()), 1)

    def assertUntouched(self, call) -> ReconcileRequired:
        """Refused before anything is replayed, recorded or run, with the record, the Project and Git as they were."""
        before, ran, executed, stages = self.snapshot(), list(self.ran), [], []
        with self.assertRaises(ReconcileRequired) as refused:
            self.watching(call, executed, stages)
        self.assertEqual((executed, stages, self.ran), ([], [], ran))
        self.assertEqual(self.snapshot(), before)
        return refused.exception


# --------------------------------------------------------------------------- a temporary move
class MoveCase(MoveDisplayCase):
    def setUp(self) -> None:
        super().setUp()
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A")})
        entry = self.simple_entry(self.store, roadmap.phase_ids["a"], {"w1": "W1 done"})
        self.w1 = self.target = entry.work_ids["w1"]
        self.i1 = entry.integration_id

    def moving(self):
        script = {("W1", 1): st.Derive({"fix": st.DerivedWork("Fix", "Fix done", derivation_detail="why Fix")}, move=True)}
        return st.start(self.store, self.w1, "single-work", by_attempt(self.ran, script, completing_executor(self.store)))

    def fix_id(self) -> str:
        (pending,) = self.pending()
        return pending["reserved_ids"][f"{self.w1}:derive:0:work:fix"]

    def assertMovedOnce(self, result, decided: str) -> None:
        """What one uninterrupted move leaves: one fix Work, one move commit with the decided display, pushed, closed."""
        self.assertEqual((result.status, result.work_id), ("moved", self.w1))
        self.assertEqual(self.ran, ["W1#1"])  # the executor was asked once, by the run that decided the move
        (fix,) = self.named("Fix")
        self.assertEqual(
            sorted((r.type, r.from_id, r.to) for r in ProjectView.load(self.store).roadmap_relations),
            sorted([("requires_completion", self.w1, self.i1), ("derived", self.w1, fix),
                    ("requires_completion", fix, self.i1)]),
        )
        self.assertEqual(len(list((self.root / WORKLINE_DIR / "derivations").glob("*.md"))), 1)
        self.assertEqual(self.events(self.w1), ["work_started", "work_target_added", "work_target_removed"])
        self.assertEqual(self.subjects().count(branch_message(decided)), 1)
        self.assertEqual(sum(1 for s in self.subjects() if s.startswith("chore(workline): branch from ")), 1)
        self.assertEqual(self.pending(), [])
        self.assertEqual(self.head(), self.remote_head())
        self.assertEqual(validate_project(self.store), [])
        (record,) = [r for r in MutationController(self.store).list_records() if r["owner"] == "start"]
        stages: list[str] = []
        for effect in record["effects"]:
            if effect["stage"] not in stages:
                stages.append(effect["stage"])
        self.assertEqual(stages, [f"{self.w1}:lifecycle:0", f"{self.w1}:derive:0", f"{self.w1}:lifecycle:1", "commit:0"])


class MoveDisplayTests(MoveCase):
    def test_a_display_only_edit_still_finishes_the_move(self) -> None:
        """In every window: moved, once, with the commit carrying the display the move was decided on."""
        for window in MOVE_WINDOWS:
            with self.subTest(window=window):
                self.setUp()
                self.interrupt(window, self.moving)
                decided = self.display(self.w1)
                self.set_meta(self.w1, "display", "W-99")
                result = self.moving()
                self.assertMovedOnce(result, decided)
                self.assertNotIn(branch_message("W-99"), self.subjects())
                self.assertEqual(self.display(self.w1), "W-99")  # the person's edit is theirs, left uncommitted
                self.assertEqual(self.dirty(), [f" M {ProjectStore.entity_rel_path('work', self.w1)}"])

    def test_b_controls_no_edit_restore_and_body(self) -> None:
        for window in ("commit recorded", "pushed"):
            for control in ("no edit", "edit then restore", "body edit"):
                with self.subTest(window=window, control=control):
                    self.setUp()
                    self.interrupt(window, self.moving)
                    decided = self.display(self.w1)
                    if control == "edit then restore":
                        original = self.work_path(self.w1).read_bytes()
                        self.set_meta(self.w1, "display", "W-99")
                        self.work_path(self.w1).write_bytes(original)
                    elif control == "body edit":
                        self.append_body(self.w1, "a note someone left")
                    self.assertMovedOnce(self.moving(), decided)

    def test_c_a_display_edit_committed_separately_still_finishes_the_move(self) -> None:
        """The person's renumbering is its own commit, so HEAD moved and the tree is clean at the retry."""
        for window in ("commit recorded", "committed", "pushed", "not closed"):
            with self.subTest(window=window):
                self.setUp()
                self.interrupt(window, self.moving)
                decided = self.display(self.w1)
                self.set_meta(self.w1, "display", "W-99")
                self.commit_work_file(self.w1, "docs: renumber")
                self.assertMovedOnce(self.moving(), decided)
                self.assertEqual(self.subjects().count("docs: renumber"), 1)

    def test_d_a_stable_work_id_replacement_still_stops(self) -> None:
        """A Work file declaring another ID is refused where it always was, before any of this."""
        for window in ("commit recorded", "pushed"):
            with self.subTest(window=window):
                self.setUp()
                self.interrupt(window, self.moving)
                self.set_meta(self.w1, "id", "w_01ARZ3NDEKTSV4RRFFQ69G5FAV")
                before = self.snapshot()["records"]
                with self.assertRaises(StopError) as caught:
                    self.moving()
                self.assertEqual(caught.exception.code, "entity_invalid")
                self.assertEqual(self.snapshot()["records"], before)
                self.assertTrue(self.pending())

    def test_e_a_foreign_edit_of_the_fix_work_is_still_refused(self) -> None:
        """A file the move wrote is held to what it wrote: that refusal is its own, and stays."""
        for window in ("commit recorded", "pushed"):
            with self.subTest(window=window):
                self.setUp()
                self.interrupt(window, self.moving)
                self.set_meta(self.fix_id(), "display", "W-98")
                refused = self.assertUntouched(self.moving)
                self.assertIn("applied with unexpected result", str(refused))

    def test_f_the_decision_keeps_the_display_it_was_decided_on(self) -> None:
        self.interrupt("registration recorded", self.moving)
        (entry,) = self.entries()
        self.assertEqual(set(entry), {"work_id", "stage", "outcome", "moved_by", DECIDED_DISPLAY})
        self.assertEqual((entry["moved_by"], entry[DECIDED_DISPLAY]), ("derive", self.display(self.w1)))

    def test_g_a_new_record_is_held_to_the_exact_message(self) -> None:
        """Another display, a tail, another kind: refused, whatever the Work is shown as now."""
        self.interrupt("commit recorded", self.moving)
        original = self.record_path().read_bytes()
        decided = self.display(self.w1)
        for message, display in [(branch_message("W-99"), None),
                                 (branch_message(decided + " and more"), None),
                                 (branch_message(""), None),
                                 ("chore(workline): branch from", None),
                                 (ng_message(decided), None),
                                 *[(other, None) for other in OTHER_KINDS],
                                 # the message rewritten to what the Project shows now is not the decided one
                                 (branch_message("W-99"), "W-99")]:
            with self.subTest(message=message, display=display):
                path = self.record_path()
                work_file = self.work_path(self.w1).read_bytes()
                self.set_recorded_message(message)
                if display is not None:
                    self.set_meta(self.w1, "display", display)
                refused = self.assertUntouched(self.moving)
                self.assertIn("other than the commit carrying the move", str(refused))
                path.write_bytes(original)
                self.work_path(self.w1).write_bytes(work_file)
        self.assertMovedOnce(self.moving(), decided)  # the record the refusals left is still the move's own

    def test_h_a_legacy_record_finishes_by_the_shape_of_its_finalization(self) -> None:
        """A derivation kept before displays were: the same display resumes, and so does another, of that kind."""
        for recorded in ("decided", "W-42"):
            with self.subTest(recorded=recorded):
                self.setUp()
                self.interrupt("commit recorded", self.moving)
                decided = self.display(self.w1)
                display = decided if recorded == "decided" else recorded
                self.drop_recorded_display()
                self.set_recorded_message(branch_message(display))
                self.set_meta(self.w1, "display", "W-99")
                self.assertMovedOnce(self.moving(), display)

    def test_i_a_legacy_record_still_refuses_other_kinds_and_an_empty_display(self) -> None:
        self.interrupt("commit recorded", self.moving)
        self.drop_recorded_display()
        original = self.record_path().read_bytes()
        decided = self.display(self.w1)
        for message in [branch_message(""), "chore(workline): branch from",
                        ng_message(decided), *OTHER_KINDS]:
            with self.subTest(message=message):
                self.set_recorded_message(message)
                self.assertUntouched(self.moving)
                self.record_path().write_bytes(original)
        self.assertMovedOnce(self.moving(), decided)

    def test_j_a_legacy_record_commits_a_move_it_has_not_committed_with_the_display_shown_now(self) -> None:
        """Nothing recorded the display it was decided on, so the commit is made as it always was."""
        self.interrupt("removal applied", self.moving)
        self.drop_recorded_display()
        self.set_meta(self.w1, "display", "W-99")
        self.assertMovedOnce(self.moving(), "W-99")

    def test_k_a_derivation_entry_this_start_does_not_read_back_is_refused(self) -> None:
        self.interrupt("commit recorded", self.moving)
        original = self.record_path().read_bytes()
        decided = self.display(self.w1)
        for label, change in {
            "empty display": lambda entry: entry.update({DECIDED_DISPLAY: ""}),
            "display not a string": lambda entry: entry.update({DECIDED_DISPLAY: 7}),
            "display null": lambda entry: entry.update({DECIDED_DISPLAY: None}),
            "display a list": lambda entry: entry.update({DECIDED_DISPLAY: ["W-01"]}),
            "unknown field": lambda entry: entry.update({"extra": 1}),
            "display other than the message's": lambda entry: entry.update({DECIDED_DISPLAY: "W-42"}),
        }.items():
            with self.subTest(entry=label):
                self.edit_record(lambda record: change(record["notes"][st._DERIVATIONS]["derivations"][0]))
                self.assertUntouched(self.moving)
                self.record_path().write_bytes(original)
        self.assertMovedOnce(self.moving(), decided)

    def test_l_a_display_the_record_cannot_keep_leaves_the_decision_kept_without_it(self) -> None:
        """Never an incomplete list over a display: the derivation is reused, and its move proven by shape."""
        real = st._read_back

        def unkept_display(value):
            entries = value.get("derivations") if isinstance(value, dict) else None
            if isinstance(entries, list) and any(isinstance(e, dict) and DECIDED_DISPLAY in e for e in entries):
                return st._UNKEPT
            return real(value)

        with mock.patch.object(st, "_read_back", unkept_display):
            self.interrupt("commit recorded", self.moving)
        note = self.pending()[0]["notes"][st._DERIVATIONS]
        self.assertTrue(note["complete"])
        (entry,) = note["derivations"]
        self.assertEqual(set(entry), {"work_id", "stage", "outcome", "moved_by"})
        decided = self.display(self.w1)
        self.set_meta(self.w1, "display", "W-99")
        self.assertMovedOnce(self.moving(), decided)

    def test_m_the_project_is_not_held_behind_the_move(self) -> None:
        """While the move is pending every other operation waits on it; once it resumes, they run again."""
        self.interrupt("pushed", self.moving)
        fix = self.fix_id()
        decided = self.display(self.w1)
        self.set_meta(self.w1, "display", "W-99")
        with self.assertRaises(ReconcileRequired) as blocked:
            create_standalone_work(self.store, WorkSpec("Other", "other done"))
        self.assertIn("overlaps the planned write scope", str(blocked.exception))
        self.assertMovedOnce(self.moving(), decided)
        create_standalone_work(self.store, WorkSpec("Other", "other done"))
        self.assertEqual(st.start(self.store, fix, "single-work", completing_executor(self.store)).status, "completed")
        self.assertEqual(self.pending(), [])

    def test_n_a_refused_move_says_which_message_it_decided(self) -> None:
        self.interrupt("commit recorded", self.moving)
        original = self.record_path().read_bytes()
        self.set_recorded_message("chore(workline): derive from W-01")
        refused = str(self.assertUntouched(self.moving))
        for part in ("a move of", "'chore(workline): derive from W-01'", "'chore(workline): branch from W-01'",
                     "the display 'W-01' it was decided on", "not part of this proof"):
            self.assertIn(part, refused)
        self.record_path().write_bytes(original)
        self.drop_recorded_display()
        self.set_recorded_message("chore(workline): cancel W-01")
        refused = str(self.assertUntouched(self.moving))
        self.assertIn("a message of the form 'chore(workline): branch from <display>'", refused)


# --------------------------------------------------------------------------- a human confirmation judged NG
NG_WINDOWS = ("commit recorded", "committed", "pushed")


class HumanNGDisplayTests(MoveDisplayCase):
    """The NG of a human confirmation moves its target too, and its message holds the display mid-way."""

    def setUp(self) -> None:
        super().setUp()
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A")})
        entry = self.simple_entry(self.store, roadmap.phase_ids["a"], {"w1": "W1 done"}, confirmation=True)
        self.w1, self.h1 = entry.work_ids["w1"], entry.confirmation_id
        self.target = self.h1

    def ng_run(self):
        def ng(ctx: st.ExecutionContext):
            if self.named("F1"):
                return completing_executor(self.store)(ctx)
            return st.HumanNG({"f1": st.DerivedWork("F1", "defect fixed", derivation_detail="why F1")},
                              st.DerivedWork("I2", "re-integrated"))

        executor = by_attempt(self.ran, {("Confirmation", 1): ng}, default=completing_executor(self.store))
        return st.start(self.store, self.w1, "outer", executor)

    def assertFinishedOnce(self, result, decided: str) -> None:
        self.assertEqual(result.status, "phase_complete")
        self.assertEqual((len(self.named("F1")), len(self.named("I2")), len(self.named("Confirmation"))), (1, 1, 1))
        self.assertEqual(self.events(self.h1), ["work_started", "work_target_added", "work_target_removed",
                                                "work_target_added", "work_target_removed", "work_completed"])
        self.assertEqual(self.subjects().count(ng_message(decided)), 1)
        self.assertEqual(sum(1 for s in self.subjects() if s.endswith(" NG; fix planned")), 1)
        # the NG is not decided again; the confirmation's next cycle is asked, as uninterrupted
        self.assertEqual(self.ran, ["W1#1", "Integration#1", "Confirmation#1", "F1#1", "I2#1", "Confirmation#1"])
        self.assertEqual((self.pending(), self.head()), ([], self.remote_head()))
        self.assertEqual(validate_project(self.store), [])

    def test_a_display_only_edit_still_finishes_the_ng(self) -> None:
        for window in NG_WINDOWS:
            with self.subTest(window=window):
                self.setUp()
                self.interrupt(window, self.ng_run)
                decided = self.display(self.h1)
                (entry,) = self.entries()
                self.assertEqual((entry["moved_by"], entry[DECIDED_DISPLAY]), ("human_ng", decided))
                self.set_meta(self.h1, "display", "W-99")
                self.assertFinishedOnce(self.ng_run(), decided)
                self.assertNotIn(ng_message("W-99"), self.subjects())

    def test_b_a_new_record_is_held_to_the_exact_message(self) -> None:
        self.interrupt("commit recorded", self.ng_run)
        original = self.record_path().read_bytes()
        decided = self.display(self.h1)
        for message in [ng_message("W-99"),
                        ng_message(decided) + " and more",
                        ng_message(""),
                        f"chore(workline): {decided}",
                        branch_message(decided),
                        finalization_message("cancel", decided),
                        f"chore(workline): {decided} Confirmation"]:
            with self.subTest(message=message):
                self.set_recorded_message(message)
                refused = self.assertUntouched(self.ng_run)
                self.assertIn("a human confirmation judged NG of", str(refused))
                self.record_path().write_bytes(original)
        self.assertFinishedOnce(self.ng_run(), decided)

    def test_c_a_legacy_record_is_proven_by_prefix_middle_and_suffix(self) -> None:
        self.interrupt("commit recorded", self.ng_run)
        self.drop_recorded_display()
        original = self.record_path().read_bytes()
        decided = self.display(self.h1)
        for message in ["chore(workline):  NG; fix planned",        # nothing where the display goes
                        f"chore(workline): {decided}",               # no fix-planned suffix
                        "chore(workline): ",                          # the prefix alone
                        f"chore(workline): {decided} NG; fix planned and more",
                        branch_message(decided),
                        finalization_message("cancel", decided),
                        f"chore(workline): {decided} Confirmation"]:
            with self.subTest(message=message):
                self.set_recorded_message(message)
                self.assertUntouched(self.ng_run)
                self.record_path().write_bytes(original)
        # that kind, carrying a display: another one than it was decided on resumes too
        self.set_recorded_message(ng_message("W-42"))
        self.set_meta(self.h1, "display", "W-99")
        self.assertFinishedOnce(self.ng_run(), "W-42")


# --------------------------------------------------------------------------- the rule itself
class MoveFinalizationProofTests(unittest.TestCase):
    """What the shared proof accepts for the two move messages, and that BL-047's kinds accept what they did."""

    def test_a_the_move_messages_are_the_ones_start_writes(self) -> None:
        self.assertEqual(st._move_message("W-01", "derive"), "chore(workline): branch from W-01")
        self.assertEqual(st._move_message("W-01", "human_ng"), "chore(workline): W-01 NG; fix planned")
        for display in ("W-01", "W-02 and more", " "):
            self.assertEqual(finalization_message("branch", display), branch_message(display))
            self.assertEqual(finalization_message("human_ng", display), ng_message(display))

    def test_b_with_a_recorded_display_only_that_exact_message(self) -> None:
        for kind in ("branch", "human_ng"):
            with self.subTest(kind=kind):
                self.assertTrue(finalization_proven(kind, "W-02", finalization_message(kind, "W-02")))
                for message in [finalization_message(kind, "W-99"), finalization_message(kind, "W-02 and more"),
                                finalization_message(kind, "W-02") + " ", finalization_message(kind, ""), None, 7]:
                    self.assertFalse(finalization_proven(kind, "W-02", message), message)

    def test_c_without_one_that_kind_carrying_a_display(self) -> None:
        kinds = ("cancel", "hold", "plan_excluded", "branch", "human_ng")
        for kind in ("branch", "human_ng"):
            with self.subTest(kind=kind):
                for display in ("W-02", "W-99", "W-02 and more", " "):
                    self.assertTrue(finalization_proven(kind, None, finalization_message(kind, display)), display)
                others = [finalization_message(other, "W-02") for other in kinds if other != kind]
                refused = others + OTHER_KINDS + [
                    finalization_message(kind, ""),
                    finalization_message(kind, "").strip(),
                    "chore(workline): ",
                    "chore(workline): W-02",
                    "",
                    None,
                    7,
                ]
                if kind == "human_ng":
                    # anything after the fix-planned suffix is not that message; for a branch it is a display
                    refused.append(finalization_message(kind, "W-02") + " and more")
                for message in refused:
                    self.assertFalse(finalization_proven(kind, None, message), message)

    def test_d_the_kinds_bl047_proves_accept_exactly_what_they_did(self) -> None:
        """Their messages have nothing after the display, so the shape reduces to the prefix rule, unchanged."""
        prefixes = {"cancel": "chore(workline): cancel ", "hold": "chore(workline): hold ",
                    "plan_excluded": "chore(workline): plan_excluded "}

        def before(kind, decided, recorded):
            if not isinstance(recorded, str):
                return False
            if decided is not None:
                return recorded == f"{prefixes[kind]}{decided}"
            return recorded.startswith(prefixes[kind]) and len(recorded) > len(prefixes[kind])

        corpus = [None, 7, "", " ", "chore(workline): ", "chore(workline): branch from W-02", "not a workline message"]
        for prefix in prefixes.values():
            corpus += [prefix, prefix.rstrip(), f"{prefix}W-02", f"{prefix} ", f"{prefix}W-99",
                       f"{prefix}W-02 NG; fix planned", f"{prefix}W-02 and more"]
        corpus += [ng_message("W-02"), branch_message("W-02")]
        for kind, prefix in prefixes.items():
            self.assertEqual(finalization_message(kind, "W-02"), f"{prefix}W-02")
            for decided in (None, "W-02", "W-02 NG; fix planned"):
                for recorded in corpus:
                    with self.subTest(kind=kind, decided=decided, recorded=recorded):
                        self.assertEqual(finalization_proven(kind, decided, recorded),
                                         before(kind, decided, recorded))


if __name__ == "__main__":
    unittest.main()
