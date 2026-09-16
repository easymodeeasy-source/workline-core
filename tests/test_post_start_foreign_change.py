"""A change another subject makes to an owned path after an operation begins (BL-043).

An operation owns a path because one of its effects writes somewhere in it. ``git add`` and
``git commit --only`` then carry whatever the working tree holds there, so a change another subject
wrote to that path after the operation began was as much "different from HEAD" as the operation's own
writes: it was staged, committed under the operation's own message, pushed to the approved remote,
reported as success, and ``validate_project`` called the result clean. Worse, a rewrite between the
executor returning and the result commit committed the other subject's bytes *instead of* the Work's
own product, and a ledger re-render silently destroyed a line it could not reproduce, or took a
well-formed foreign record over as one of the operation's own relations.

Now every write to a Project file records what its path held before it and what it wrote there, a
path an operation commits that no effect of its writes is recorded by its owner (an executor result,
a file already holding exactly what the operation would have written), and both the next write to a
path and the commit that would carry it happen only while it still holds exactly that. Owning the
path is not owning the bytes. Where it cannot be shown, nothing is staged, committed or pushed, the
change is left exactly where it is, and the operation stops as ``reconcile required``.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git, scripted_executor
from workline import roadmap as rm
from workline import start as st
from workline.create import RelationSpec, WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, StopError
from workline.ids import new_id
from workline.mutation import Mutation, MutationController
from workline.ops import Replan
from workline.state import ProjectView
from workline.store import WORKLINE_DIR
from workline.validate import validate_project
from workline.yamlish import dump, load

EVENT_LOG = f"{WORKLINE_DIR}/events/events.jsonl"
ROADMAP_YAML = f"{WORKLINE_DIR}/relations/roadmap.yaml"
#: A legal event another subject appends: well-formed, and about a Work this operation is not running.
FOREIGN_EVENT_ID = "evt_01FOREIGN0000000000000000"
#: A relation ID another subject could plausibly write: a valid ULID, so nothing but ownership tells it apart.
FOREIGN_RELATION_ID = new_id("relation")
FOREIGN_COMMENT = "# FOREIGN-COMMENT"


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


# --------------------------------------------------------------------------- the windows
def after_first_event(inject):
    """Another subject writes right after this operation's first event is applied (F0a)."""
    real = MutationController.apply_effect
    state = {"fired": False}

    def apply_effect(controller, record):
        result = real(controller, record)
        if record["kind"] == "append_event" and not state["fired"]:
            state["fired"] = True
            inject()
        return result

    return mock.patch.object(MutationController, "apply_effect", apply_effect), state


def after_commit_recorded(inject, *, nth: int = 1):
    """Another subject writes once the ``nth`` commit of this operation is recorded, before it is made (F0d).

    Recording a commit is the last thing an operation does before its Git stage runs, so this is the
    narrowest window the operation itself can be stopped in - and the one the investigation found
    published a malformed log to the remote before anything noticed.
    """
    real = Mutation.add_effects
    state = {"seen": 0, "fired": False}

    def add_effects(mutation, stage, effects):
        real(mutation, stage, effects)
        if any(effect.kind == "git_commit" for effect in effects):
            state["seen"] += 1
            if state["seen"] == nth:
                state["fired"] = True
                inject()

    return mock.patch.object(Mutation, "add_effects", add_effects), state


def before_applying(kind: str):
    """Stop with an effect of ``kind`` recorded and not applied."""
    real = MutationController.apply_effect
    state = {"fired": False}

    def apply_effect(controller, record):
        if record["kind"] == kind and not state["fired"]:
            state["fired"] = True
            raise Interrupted(f"recorded {kind}, not applied")
        return real(controller, record)

    return mock.patch.object(MutationController, "apply_effect", apply_effect), state


def before_pushing(nth: int = 1):
    """Stop with this operation's ``nth`` commit made and its push not made."""
    real = MutationController.apply_effect
    state = {"seen": 0}

    def apply_effect(controller, record):
        if record["kind"] == "git_push":
            state["seen"] += 1
            if state["seen"] == nth:
                raise Interrupted("committed, not pushed")
        return real(controller, record)

    return mock.patch.object(MutationController, "apply_effect", apply_effect)


class ForeignChangeCase(WorklineTestCase):
    """A Project with a remote, one Phase entered, and one Work ready to run."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.root = self.store.root
        self.ran: list[str] = []
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B")})
        self.rid, self.pa, self.pb = roadmap.roadmap_id, roadmap.phase_ids["a"], roadmap.phase_ids["b"]
        entry = self.simple_entry(self.store, self.pa)
        self.w1, self.i1 = entry.work_ids["w1"], entry.integration_id
        self.result = f"result_{ProjectView.load(self.store).works[self.w1].display}.txt"
        self.base = self.head()

    # executors ----------------------------------------------------------------
    def completing(self, body: str = "the Work's own result\n"):
        def execute(ctx: st.ExecutionContext):
            self.ran.append(ctx.work.id)
            (self.root / self.result).write_text(body, encoding="utf-8")
            return st.Completed((self.result,))

        return execute

    def start(self, executor=None, work_id: str | None = None, mode: str = "single-work"):
        runner = executor if executor is not None else self.completing()
        return lambda: st.start(self.store, work_id or self.w1, mode, runner)

    # what another subject writes ----------------------------------------------
    def append_foreign_event(self) -> None:
        """One legal event another subject appends to the log - the same shape Workline writes."""
        record = {"id": FOREIGN_EVENT_ID, "type": "work_held", "entity": self.i1, "at": "2026-01-01T00:00:00+00:00"}
        with open(self.root / EVENT_LOG, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    def edit_first_event_line(self) -> None:
        """Another subject rewrites a line already in the log rather than adding one."""
        path = self.root / EVENT_LOG
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        record = json.loads(lines[0])
        record["at"] = "1999-12-31T23:59:59+00:00"
        lines[0] = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        path.write_text("".join(lines), encoding="utf-8", newline="")

    def append_malformed(self) -> None:
        with open(self.root / EVENT_LOG, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("not json at all\n")

    def overwrite_result(self, body: str = "another subject's bytes\n") -> None:
        (self.root / self.result).write_text(body, encoding="utf-8")

    def append_to_ledger(self, text: str) -> None:
        path = self.root / ROADMAP_YAML
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8", newline="")

    # observation ---------------------------------------------------------------
    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote_path(), "rev-parse", "main").strip()

    def log_text(self) -> str:
        return (self.root / EVENT_LOG).read_text(encoding="utf-8")

    def committed(self, path: str) -> str:
        return git(self.root, "show", f"HEAD:{path}", check=False)

    def published(self, path: str) -> str:
        return git(self.remote_path(), "show", f"main:{path}", check=False)

    def pending(self) -> list[dict]:
        return [r for r in MutationController(self.store).list_records() if r["status"] == "pending"]

    def record_bytes(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))}

    def assertUnpublished(self, marker: str, path: str) -> None:
        """The change is still where its writer left it, and in no commit here or on the remote."""
        self.assertIn(marker, (self.root / path).read_text(encoding="utf-8"))
        self.assertNotIn(marker, self.committed(path))
        self.assertNotIn(marker, self.published(path))

    def assertRefused(self, call, *, expect: str) -> StopError:
        """The operation stops as ``reconcile required``, naming the path it could not show is its own."""
        with self.assertRaises(ReconcileRequired) as refused:
            call()
        self.assertEqual(refused.exception.code, "reconcile_required")
        self.assertIn(expect, refused.exception.message)
        return refused.exception


class CancelCase(ForeignChangeCase):
    """Two standalone Works, one cancelled with a replan whose relation the ledger commit carries."""

    def setUp(self) -> None:
        super().setUp()
        self.s1 = create_standalone_work(self.store, WorkSpec("S1", "s1")).work_id
        self.s2 = create_standalone_work(self.store, WorkSpec("S2", "s2")).work_id
        self.replan = Replan(new_works={"k": WorkSpec("K", "k")},
                             add_relations=(RelationSpec("planned_next", self.s1, "k"),))

    def cancel(self):
        return st.start(self.store, self.s2, "single-work",
                        scripted_executor({self.s2: [st.Cancel(self.replan, "not needed")]}))


# --------------------------------------------------------------------------- A: not committed
class ForeignBytesAreNotCommittedTests(CancelCase):
    def test_a_legal_event_another_subject_appends_after_the_start_is_not_committed(self) -> None:
        """F0a: the worst case of the three, because nothing about the line looks wrong."""
        patch, state = after_first_event(self.append_foreign_event)
        with patch:
            self.assertRefused(self.start(), expect=EVENT_LOG)

        self.assertTrue(state["fired"])
        self.assertUnpublished(FOREIGN_EVENT_ID, EVENT_LOG)
        # and the lifecycle state it carries never became canon
        self.assertNotIn("work_held", self.published(EVENT_LOG))

    def test_a_line_another_subject_rewrites_after_the_start_is_not_committed(self) -> None:
        patch, state = after_first_event(self.edit_first_event_line)
        with patch:
            self.assertRefused(self.start(), expect=EVENT_LOG)

        self.assertTrue(state["fired"])
        self.assertUnpublished("1999-12-31", EVENT_LOG)

    def test_a_malformed_line_another_subject_appends_is_neither_erased_nor_published(self) -> None:
        """The last window: the line lands once the commit that carries the log is recorded (F0d)."""
        patch, state = after_commit_recorded(self.append_malformed, nth=2)
        with patch:
            with self.assertRaises(StopError) as refused:
                self.start()()

        self.assertTrue(state["fired"])
        # Reading the log for the Git stage refuses such a line before ownership is ever asked,
        # which is an accident of this payload and no defence - what matters is where it stops.
        self.assertEqual(refused.exception.code, "events_invalid")
        self.assertUnpublished("not json at all", EVENT_LOG)
        self.assertEqual(self.published(EVENT_LOG), self.committed(EVENT_LOG))

    def test_a_result_another_subject_rewrites_before_its_commit_loses_neither_result(self) -> None:
        """P1: Workline's own product must not be replaced in its own result commit, nor put back over theirs."""
        patch, state = after_commit_recorded(self.overwrite_result)
        with patch:
            self.assertRefused(self.start(), expect=self.result)

        self.assertTrue(state["fired"])
        self.assertEqual((self.root / self.result).read_text(encoding="utf-8"), "another subject's bytes\n")
        self.assertEqual(self.committed(self.result), "")  # no result commit was made at all
        self.assertEqual(self.ran, [self.w1])

    def test_a_later_commit_of_the_same_operation_does_not_absorb_it(self) -> None:
        """F0e: contamination is not confined to the commit that "should" carry the path."""
        entry = self.simple_entry(self.store, self.pb, {"x": "X done", "y": "Y done"}, entry="x")

        patch, state = after_commit_recorded(self.append_foreign_event, nth=3)
        with patch:
            with self.assertRaises(ReconcileRequired):
                st.start(self.store, entry.work_ids["x"], "outer", completing_executor(self.store, self.ran))

        self.assertTrue(state["fired"])
        self.assertUnpublished(FOREIGN_EVENT_ID, EVENT_LOG)
        self.assertEqual(self.ran[:1], [entry.work_ids["x"]])  # the Work that finished before it still did

    def test_a_roadmap_phase_hold_refuses_it_the_same_way(self) -> None:
        """G1: the proof sits in the shared Git stage, not in START."""
        patch, state = after_first_event(self.append_foreign_event)
        with patch:
            self.assertRefused(lambda: rm.hold_phase(self.store, self.pb), expect=EVENT_LOG)

        self.assertTrue(state["fired"])
        self.assertUnpublished(FOREIGN_EVENT_ID, EVENT_LOG)
        self.assertNotIn("phase_held", self.published(EVENT_LOG))  # nor the operation's own decision

    def test_a_resume_between_a_commit_and_its_push_refuses_rather_than_publishing(self) -> None:
        """R1: the resume closed the mutation as success, publishing the change with it.

        What this mutation wrote reaches back past the interruption: the events it appended in its
        first run hold what it left in the log, so the append its second run makes is refused before
        it writes, rather than after the log has been made to match again.
        """
        with before_pushing(nth=1):
            with self.assertRaises(Interrupted):
                self.start()()
        self.append_foreign_event()

        self.assertRefused(self.start(), expect=EVENT_LOG)

        self.assertUnpublished(FOREIGN_EVENT_ID, EVENT_LOG)
        self.assertNotIn("work_completed", self.log_text())  # nothing was written on top of it either

    def test_a_relation_ledger_another_subject_edits_before_the_commit_is_not_committed(self) -> None:
        """P4: a line in the ledger a replan's commit would carry."""
        patch, state = after_commit_recorded(lambda: self.append_to_ledger(FOREIGN_COMMENT + "\n"))
        with patch:
            self.assertRefused(self.cancel, expect=ROADMAP_YAML)

        self.assertTrue(state["fired"])
        self.assertUnpublished(FOREIGN_COMMENT, ROADMAP_YAML)


# --------------------------------------------------------------------------- B: not erased
class ForeignBytesAreNotErasedTests(CancelCase):
    def test_a_line_a_ledger_re_render_cannot_reproduce_is_left_alone(self) -> None:
        """E1: the replay destroyed it and committed the erasure, which no check at the commit can see."""
        patch, state = before_applying("add_relation")
        with patch:
            with self.assertRaises(Interrupted):
                self.cancel()
        self.assertTrue(state["fired"])
        self.append_to_ledger(FOREIGN_COMMENT + "\n")
        held = (self.root / ROADMAP_YAML).read_bytes()

        self.assertRefused(self.cancel, expect=ROADMAP_YAML)

        self.assertEqual((self.root / ROADMAP_YAML).read_bytes(), held)  # not re-rendered over
        self.assertUnpublished(FOREIGN_COMMENT, ROADMAP_YAML)


# --------------------------------------------------------------------------- C: not adopted
class ForeignBytesAreNotAdoptedTests(CancelCase):
    def test_a_well_formed_foreign_relation_record_does_not_become_one_of_its_own(self) -> None:
        """E2b: a valid ULID and the renderer's own shape - nothing but ownership tells it apart."""
        patch, state = before_applying("add_relation")
        with patch:
            with self.assertRaises(Interrupted):
                self.cancel()
        self.assertTrue(state["fired"])
        self.relations_before = len(ProjectView.load(self.store).roadmap_relations)
        self.append_to_ledger(
            f"  - id: {FOREIGN_RELATION_ID}\n    type: planned_next\n    from: {self.s1}\n    to: {self.s2}\n"
        )

        held = (self.root / ROADMAP_YAML).read_bytes()

        self.assertRefused(self.cancel, expect=ROADMAP_YAML)

        # Not re-rendered at all: the record is neither taken into the ledger Workline writes back
        # nor dropped from it, and the relation the replan decided was never written either.
        self.assertEqual((self.root / ROADMAP_YAML).read_bytes(), held)
        self.assertUnpublished(FOREIGN_RELATION_ID, ROADMAP_YAML)
        self.assertEqual(len(ProjectView.load(self.store).roadmap_relations), self.relations_before + 1)


# --------------------------------------------------------------------------- unchanged behaviour
class UnchangedTests(ForeignChangeCase):
    def test_a_start_with_no_foreign_change_completes_commits_and_pushes(self) -> None:
        result = self.start()()

        self.assertEqual((result.status, result.work_id), ("completed", self.w1))
        self.assertEqual(self.remote_head(), self.head())
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual((self.root / self.result).read_text(encoding="utf-8"), "the Work's own result\n")
        self.assertEqual(self.committed(self.result), "the Work's own result\n")

    def test_a_change_withdrawn_before_the_commit_leaves_the_operation_unaffected(self) -> None:
        """C1: the proof is about the state at the commit, not about what happened along the way."""
        def inject() -> None:
            self.append_foreign_event()
            path = self.root / EVENT_LOG
            path.write_text(
                "".join(line for line in path.read_text(encoding="utf-8").splitlines(keepends=True)
                        if FOREIGN_EVENT_ID not in line),
                encoding="utf-8", newline="",
            )

        patch, state = after_first_event(inject)
        with patch:
            result = self.start()()

        self.assertTrue(state["fired"])
        self.assertEqual(result.status, "completed")
        self.assertNotIn(FOREIGN_EVENT_ID, self.committed(EVENT_LOG))
        self.assertEqual(self.remote_head(), self.head())

    def test_a_change_at_a_path_no_commit_of_the_operation_carries_is_left_dirty(self) -> None:
        """The boundary is each commit's own path set; an unrelated file is not the operation's business."""
        patch, state = after_first_event(lambda: (self.root / "theirs.txt").write_text("mine\n", encoding="utf-8"))
        with patch:
            result = self.start()()

        self.assertTrue(state["fired"])
        self.assertEqual(result.status, "completed")
        self.assertEqual((self.root / "theirs.txt").read_text(encoding="utf-8"), "mine\n")
        self.assertIn("theirs.txt", git(self.root, "status", "--porcelain", "--untracked-files=all"))

    def test_a_result_rewritten_after_its_own_commit_is_left_dirty(self) -> None:
        """P2: a path no later commit of the operation carries is left alone, however it changed."""
        patch, state = after_commit_recorded(self.overwrite_result, nth=2)
        with patch:
            result = self.start()()

        self.assertTrue(state["fired"])
        self.assertEqual(result.status, "completed")
        self.assertEqual((self.root / self.result).read_text(encoding="utf-8"), "another subject's bytes\n")
        self.assertEqual(self.committed(self.result), "the Work's own result\n")

    def test_the_same_bytes_written_again_by_another_subject_cannot_be_told_apart(self) -> None:
        """The declared contract: what the operation produced is what the path holds, whoever last wrote it."""
        def inject() -> None:
            path = self.root / EVENT_LOG
            path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8", newline="")

        patch, state = after_first_event(inject)
        with patch:
            result = self.start()()

        self.assertTrue(state["fired"])
        self.assertEqual(result.status, "completed")

    def test_a_change_put_back_to_what_the_operation_wrote_goes_on(self) -> None:
        """Returning the file to the operation's own bytes is provably safe, so the operation finishes."""
        with before_pushing(nth=2):
            with self.assertRaises(Interrupted):
                self.start()()
        held = self.log_text()
        self.append_foreign_event()
        (self.root / EVENT_LOG).write_text(held, encoding="utf-8", newline="")

        result = self.start()()

        self.assertEqual(result.status, "completed")
        self.assertEqual(self.remote_head(), self.head())
        self.assertNotIn(FOREIGN_EVENT_ID, self.committed(EVENT_LOG))

    def test_a_change_made_after_the_last_commit_is_not_swept_into_the_push(self) -> None:
        """Interrupted between the finalization commit and its push: the push carries what was committed."""
        with before_pushing(nth=2):
            with self.assertRaises(Interrupted):
                self.start()()
        self.append_foreign_event()

        result = self.start()()

        self.assertEqual((result.status, self.ran), ("completed", [self.w1]))  # BL-031, unchanged
        self.assertIn(FOREIGN_EVENT_ID, self.log_text())
        self.assertNotIn(FOREIGN_EVENT_ID, self.published(EVENT_LOG))

    def test_a_refusal_leaves_the_record_exactly_as_it_was(self) -> None:
        """Nothing is replayed, recorded or repaired: the record a retry reads is byte for byte the same."""
        patch, state = after_commit_recorded(self.append_foreign_event, nth=2)
        with patch:
            self.assertRefused(self.start(), expect=EVENT_LOG)
        after_first = self.record_bytes()

        self.assertRefused(self.start(), expect=EVENT_LOG)

        self.assertTrue(state["fired"])
        self.assertEqual(self.record_bytes(), after_first)
        self.assertEqual(self.ran, [self.w1])  # and the executor is not asked again

    def test_a_record_written_before_this_proof_keeps_the_behaviour_it_had(self) -> None:
        """A mutation opened by the implementation before this change carries no account of its content."""
        with before_pushing(nth=1):
            with self.assertRaises(Interrupted):
                self.start()()
        path = self.store.mutations / f"{self.pending()[0]['mutation_id']}.yaml"
        record = load(path.read_text(encoding="utf-8"))
        record["notes"].pop("own_content", None)
        for effect in record["effects"]:
            effect.pop("held_before", None)
            effect.pop("wrote", None)
        path.write_text(dump(record), encoding="utf-8", newline="")
        self.append_foreign_event()

        result = self.start()()

        self.assertEqual(result.status, "completed")
        self.assertIn(FOREIGN_EVENT_ID, self.committed(EVENT_LOG))  # exactly as it behaved before
        self.assertEqual(self.remote_head(), self.head())


# --------------------------------------------------------------------------- neighbours
class NeighbouringGuaranteesTests(ForeignChangeCase):
    def test_a_change_that_was_there_before_the_operation_is_still_bl041s(self) -> None:
        """BL-041 owns the entry, this owns the content; the pre-existing case keeps its own refusal."""
        with open(self.root / EVENT_LOG, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n")

        with self.assertRaises(StopError) as refused:
            self.start()()

        self.assertEqual(refused.exception.code, "dirty_overlap")
        self.assertEqual(self.ran, [])
        self.assertEqual(self.pending(), [])

    def test_a_result_path_dirty_before_the_operation_is_still_bl042s(self) -> None:
        """BL-042 puts the person's bytes back and keeps the executor's result for the retry."""
        (self.root / self.result).write_text("someone else's draft\n", encoding="utf-8")

        with self.assertRaises(StopError) as refused:
            self.start()()

        self.assertEqual(refused.exception.code, "dirty_overlap")
        self.assertEqual((self.root / self.result).read_text(encoding="utf-8"), "someone else's draft\n")

        git(self.root, "add", "--", self.result)
        git(self.root, "commit", "-q", "-m", "person: my own draft", "--", self.result)
        result = self.start()()

        self.assertEqual((result.status, self.ran), ("completed", [self.w1]))  # the executor is not asked again
        self.assertEqual(self.committed(self.result), "the Work's own result\n")

    def test_a_terminal_finalization_resume_with_no_foreign_change_still_finishes_from_its_record(self) -> None:
        """BL-031: the executor is not asked again and the recorded stage is all that is left."""
        real = MutationController.apply_effect

        def stop_before_the_finalize_commit(controller, record):
            if record["kind"] == "git_commit" and "complete" in record["payload"]["message"]:
                raise Interrupted("completion applied, its commit not recorded")
            return real(controller, record)

        with mock.patch.object(MutationController, "apply_effect", stop_before_the_finalize_commit):
            with self.assertRaises(Interrupted):
                self.start()()

        result = self.start()()

        self.assertEqual((result.status, self.ran), ("completed", [self.w1]))
        self.assertEqual(self.remote_head(), self.head())
        self.assertEqual(validate_project(self.store), [])

    def test_a_recorded_hold_resume_with_no_foreign_change_is_unchanged(self) -> None:
        """BL-044: the Git stage is finished from the record, and this adds no proof it cannot meet."""
        holding = scripted_executor({self.w1: [st.Hold("waiting on someone")]})
        with before_pushing():
            with self.assertRaises(Interrupted):
                st.start(self.store, self.w1, "single-work", holding)

        result = st.start(self.store, self.w1, "single-work", holding)

        self.assertEqual((result.status, result.detail), ("held", "waiting on someone"))
        self.assertEqual(self.remote_head(), self.head())


if __name__ == "__main__":
    unittest.main()
