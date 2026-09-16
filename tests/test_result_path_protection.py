"""A result path that was already changed when START began (BL-042).

START records which paths were already changed when it began and refuses a commit that overlaps them
(``dirty_overlap``, BL-041). Which paths a Work's result owns is known only once the executor returns,
so that refusal was made after the executor had already written over what the person had not committed
there - and then the operation could never be finished: the snapshot is recorded once, so committing
that change, discarding it, even a wholly clean working tree, met the same refusal, every retry ran the
executor over their file again, a derivation added another Work, derivation detail and relations each
time, and every other operation writing a ledger stopped behind the record.

Now the paths that were already changed are read before the executor runs; a result path among them is
refused with what the person had put back exactly as it stood; the executor's own result is kept in the
record so the retry finishes the same Work without asking the executor again; a derivation is refused
before a Work, a derivation detail or a relation of it is recorded; and the snapshot is narrowed, before
anything of a run is written, to the paths that are still changed - so once the person commits or
discards their change the same START goes on. The snapshot is never widened and never narrowed by which
paths the operation itself wrote, so an executor's own output can never become a change from before it,
and a path carrying both cannot be committed as the operation's own.
"""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import WorklineTestCase, git
from workline import roadmap as rm
from workline import start as st
from workline.errors import StopError
from workline.mutation import MutationController
from workline.ops import Replan
from workline.state import ProjectView
from workline.store import WORKLINE_DIR
from workline.validate import validate_project

EVENT_LOG = f"{WORKLINE_DIR}/events/events.jsonl"
ROADMAP_YAML = f"{WORKLINE_DIR}/relations/roadmap.yaml"
DRAFT = "someone else's draft\n"


class Died(RuntimeError):
    """A deterministic executor failure, injected by the test alone."""


def before_bl042_derive():
    """The implementation before this change, whose derivation looked at the overlap only at its commit."""
    return mock.patch.object(st, "_derive_ledgers", lambda specs, relations: [])


class ResultPathCase(WorklineTestCase):
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

    # executors ---------------------------------------------------------------
    def completing(self, path: str | None = None, *, varying: bool = False):
        """Writes one result file and reports completion; ``varying`` writes different bytes each call."""
        name = path or self.result

        def execute(ctx: st.ExecutionContext):
            self.ran.append(ctx.work.id)
            body = f"{ctx.work.name} produced" + (f" {len(self.ran)}" if varying else "") + "\n"
            (self.root / name).write_text(body, encoding="utf-8")
            return st.Completed((name,))

        return execute

    def returning(self, outcome):
        def execute(ctx: st.ExecutionContext):
            self.ran.append(ctx.work.id)
            return outcome

        return execute

    def start(self, executor, work_id: str | None = None, mode: str = "single-work"):
        return lambda: st.start(self.store, work_id or self.w1, mode, executor)

    # the person's changes -----------------------------------------------------
    def draft_at(self, path: str, body: str = DRAFT) -> None:
        """An untracked file the person has not committed."""
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def tracked_draft_at(self, path: str, body: str = DRAFT) -> None:
        """A tracked file the person has modified and not committed."""
        (self.root / path).write_text("committed baseline\n", encoding="utf-8")
        self.commit(path, "person: baseline")
        (self.root / path).write_text(body, encoding="utf-8")

    def append_to(self, path: str, text: str = "\n") -> None:
        with open(self.root / path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    def commit(self, path: str, message: str = "person: my own change") -> None:
        git(self.root, "add", "--", path)
        git(self.root, "commit", "-q", "-m", message, "--", path)
        git(self.root, "push", "-q", "origin", "main")

    # observation --------------------------------------------------------------
    def body(self, path: str | None = None) -> str | None:
        target = self.root / (path or self.result)
        return target.read_text(encoding="utf-8") if target.exists() else None

    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote_path(), "rev-parse", "main").strip()

    def dirty(self) -> list[str]:
        lines = git(self.root, "status", "--porcelain", "--untracked-files=all").splitlines()
        return sorted(line.strip() for line in lines if ".workline/runtime/" not in line)

    def pending(self) -> list[dict]:
        return [r for r in MutationController(self.store).list_records() if r["status"] == "pending"]

    def stages(self) -> list[str]:
        return sorted({e["stage"] for r in self.pending() for e in r["effects"]})

    def counts(self) -> tuple[int, int, int]:
        """Works, roadmap relations, and recorded effects - what a refused derivation must not add."""
        view = ProjectView.load(self.store)
        return len(view.works), len(view.roadmap_relations), sum(len(r["effects"]) for r in self.pending())

    def events_of(self, work_id: str) -> list[str]:
        return [e.type for e in ProjectView.load(self.store).events_for(work_id)]

    def assertRefusedWithBytesKept(self, call, path: str, expected: str | None) -> StopError:
        """Refused for ``path``, with what the person had there exactly as it was and nothing committed."""
        head = self.head()
        with self.assertRaises(StopError) as refused:
            call()
        self.assertEqual(refused.exception.code, "dirty_overlap")
        self.assertIn(path, refused.exception.message)
        self.assertEqual(self.body(path), expected)
        self.assertEqual((self.head(), self.remote_head()), (head, head))
        return refused.exception


# --------------------------------------------------------------------------- what the person had
class KeepsWhatThePersonHadTests(ResultPathCase):
    def test_an_untracked_draft_at_a_result_path_is_put_back(self) -> None:
        self.draft_at(self.result)

        refusal = self.assertRefusedWithBytesKept(self.start(self.completing()), self.result, DRAFT)

        self.assertIn("put back as it stood before this operation", refusal.message)
        self.assertEqual((self.ran, self.stages()), ([self.w1], [f"{self.w1}:lifecycle:0"]))
        self.assertEqual(self.dirty(), sorted([f"?? {self.result}", f"M {EVENT_LOG}"]))

    def test_a_tracked_modification_at_a_result_path_is_put_back(self) -> None:
        self.tracked_draft_at(self.result)

        self.assertRefusedWithBytesKept(self.start(self.completing()), self.result, DRAFT)

        self.assertEqual(self.ran, [self.w1])

    def test_a_tracked_modification_a_deletion_result_removes_is_put_back(self) -> None:
        """A Work that deletes a tracked file the person had modified leaves the file, and their bytes, there."""
        doomed = "doomed.txt"
        self.tracked_draft_at(doomed)

        def deleting(ctx: st.ExecutionContext):
            self.ran.append(ctx.work.id)
            (self.root / doomed).unlink()
            return st.Completed(deleted_paths=(doomed,))

        self.assertRefusedWithBytesKept(self.start(deleting), doomed, DRAFT)

        self.assertTrue((self.root / doomed).exists())
        self.assertEqual(self.ran, [self.w1])

    def test_an_untracked_deletion_the_person_had_not_committed_is_put_back(self) -> None:
        """A tracked file the person had deleted without committing is not taken over as this Work's result."""
        gone = "gone.txt"
        (self.root / gone).write_text("committed\n", encoding="utf-8")
        self.commit(gone, "person: baseline")
        (self.root / gone).unlink()

        self.assertRefusedWithBytesKept(self.start(self.completing(gone)), gone, None)

        self.assertEqual(self.ran, [self.w1])

    def test_a_clean_result_path_completes_and_is_committed(self) -> None:
        result = self.start(self.completing())()

        self.assertEqual((result.status, self.ran), ("completed", [self.w1]))
        self.assertEqual((self.dirty(), self.head(), self.pending()), ([], self.remote_head(), []))
        self.assertEqual((self.body(), validate_project(self.store)), ("W1 produced\n", []))

    def test_a_change_the_executor_does_not_touch_is_left_alone(self) -> None:
        self.draft_at("notes.txt")

        result = self.start(self.completing())()

        self.assertEqual((result.status, self.body("notes.txt")), ("completed", DRAFT))
        self.assertEqual((self.dirty(), self.head()), (["?? notes.txt"], self.remote_head()))
        self.assertEqual(validate_project(self.store), [])


# --------------------------------------------------------------------------- the person resolves it
class ConvergesOnceResolvedTests(ResultPathCase):
    def test_committing_the_contested_path_lets_the_same_start_finish(self) -> None:
        self.draft_at(self.result)
        call = self.start(self.completing())
        self.assertRefusedWithBytesKept(call, self.result, DRAFT)

        self.commit(self.result)
        result = call()

        self.assertEqual((result.status, self.body()), ("completed", "W1 produced\n"))
        self.assertEqual((self.dirty(), self.head(), self.pending()), ([], self.remote_head(), []))
        self.assertEqual(validate_project(self.store), [])

    def test_discarding_the_contested_path_lets_the_same_start_finish(self) -> None:
        self.draft_at(self.result)
        call = self.start(self.completing())
        self.assertRefusedWithBytesKept(call, self.result, DRAFT)

        (self.root / self.result).unlink()
        result = call()

        self.assertEqual((result.status, self.body()), ("completed", "W1 produced\n"))
        self.assertEqual((self.dirty(), self.head(), self.pending()), ([], self.remote_head(), []))

    def test_a_tracked_modification_checked_out_again_lets_the_same_start_finish(self) -> None:
        self.tracked_draft_at(self.result)
        call = self.start(self.completing())
        self.assertRefusedWithBytesKept(call, self.result, DRAFT)

        git(self.root, "checkout", "--", self.result)
        result = call()

        self.assertEqual((result.status, self.body()), ("completed", "W1 produced\n"))
        self.assertEqual((self.dirty(), self.head(), self.pending()), ([], self.remote_head(), []))

    def test_a_clean_tree_is_not_refused_for_a_path_that_was_only_changed_at_entry(self) -> None:
        """The recorded snapshot names paths for the life of the mutation; a name alone no longer refuses."""
        self.draft_at(self.result)
        call = self.start(self.completing())
        self.assertRefusedWithBytesKept(call, self.result, DRAFT)

        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "person: everything")
        git(self.root, "push", "-q", "origin", "main")
        self.assertEqual(self.dirty(), [])

        self.assertEqual(call().status, "completed")
        self.assertEqual((self.dirty(), self.head(), self.pending()), ([], self.remote_head(), []))

    def test_a_retry_before_the_person_resolves_it_refuses_again_and_keeps_their_bytes(self) -> None:
        self.draft_at(self.result)
        call = self.start(self.completing())
        self.assertRefusedWithBytesKept(call, self.result, DRAFT)

        for _ in range(2):
            self.assertRefusedWithBytesKept(call, self.result, DRAFT)

        self.assertEqual((self.ran, self.stages()), ([self.w1], [f"{self.w1}:lifecycle:0"]))


# --------------------------------------------------------------------------- the result the refusal keeps
class KeepsTheResultTests(ResultPathCase):
    def test_the_executor_is_asked_once_across_the_refusal_and_the_retry(self) -> None:
        self.draft_at(self.result)
        call = self.start(self.completing())
        self.assertRefusedWithBytesKept(call, self.result, DRAFT)
        self.assertRefusedWithBytesKept(call, self.result, DRAFT)

        self.commit(self.result)

        self.assertEqual((call().status, self.ran), ("completed", [self.w1]))

    def test_the_committed_result_is_the_one_the_executor_returned(self) -> None:
        """An executor whose result differs on every call shows the retry used the one it already returned."""
        self.draft_at(self.result)
        call = self.start(self.completing(varying=True))
        self.assertRefusedWithBytesKept(call, self.result, DRAFT)

        self.commit(self.result)
        self.assertEqual(call().status, "completed")

        self.assertEqual(self.body(), "W1 produced 1\n")
        self.assertEqual(git(self.root, "show", f"HEAD~1:{self.result}"), "W1 produced 1\n")

    def test_a_deletion_result_is_made_again_after_the_persons_file_was_put_back(self) -> None:
        doomed = "doomed.txt"
        self.tracked_draft_at(doomed)

        def deleting(ctx: st.ExecutionContext):
            self.ran.append(ctx.work.id)
            (self.root / doomed).unlink()
            return st.Completed(deleted_paths=(doomed,))

        call = self.start(deleting)
        self.assertRefusedWithBytesKept(call, doomed, DRAFT)
        self.commit(doomed)

        self.assertEqual((call().status, self.ran), ("completed", [self.w1]))
        self.assertFalse((self.root / doomed).exists())
        self.assertEqual((self.dirty(), self.head()), ([], self.remote_head()))

    def test_outer_mode_does_not_ask_a_completed_works_executor_again(self) -> None:
        entry = self.simple_entry(self.store, self.pb, {"w1": "one", "w2": "two"}, entry="w1")
        first, second = entry.work_ids["w1"], entry.work_ids["w2"]
        view = ProjectView.load(self.store)
        names = {w: view.works[w].display for w in (first, second)}
        self.draft_at(f"result_{names[second]}.txt")

        def execute(ctx: st.ExecutionContext):
            self.ran.append(ctx.work.id)
            (self.root / f"result_{ctx.work.display}.txt").write_text(f"{ctx.work.name}\n", encoding="utf-8")
            return st.Completed((f"result_{ctx.work.display}.txt",))

        call = self.start(execute, work_id=first, mode="outer")
        with self.assertRaises(StopError) as refused:
            call()
        self.assertEqual((refused.exception.code, self.ran), ("dirty_overlap", [first, second]))
        self.assertEqual(self.body(f"result_{names[second]}.txt"), DRAFT)

        with self.assertRaises(StopError):
            call()
        self.assertEqual(self.ran, [first, second])  # neither Work's executor is asked again


# --------------------------------------------------------------------------- a derivation
class DerivationTests(ResultPathCase):
    def derive(self):
        return st.Derive({"fix": st.DerivedWork("Fix it", "fixed", derivation_detail="because")})

    def test_a_derivation_records_nothing_when_its_relation_file_was_already_changed(self) -> None:
        self.append_to(ROADMAP_YAML)
        before = self.counts()

        with self.assertRaises(StopError) as refused:
            self.start(self.returning(self.derive()))()

        self.assertEqual((refused.exception.code, self.ran), ("dirty_overlap", [self.w1]))
        self.assertIn(ROADMAP_YAML, refused.exception.message)
        self.assertEqual(self.counts(), (before[0], before[1], 2))  # the opening lifecycle events alone
        self.assertEqual(self.stages(), [f"{self.w1}:lifecycle:0"])
        self.assertEqual(list((self.root / WORKLINE_DIR / "derivations").glob("*.md")), [])

    def test_retries_add_no_work_no_relation_and_no_effect(self) -> None:
        self.append_to(ROADMAP_YAML)
        call = self.start(self.returning(self.derive()))
        with self.assertRaises(StopError):
            call()
        after = self.counts()

        for _ in range(3):
            with self.assertRaises(StopError) as refused:
                call()
            self.assertEqual(refused.exception.code, "dirty_overlap")
            self.assertEqual(self.counts(), after)

        self.assertEqual(self.ran, [self.w1])  # nor is the executor asked again

    def test_the_derivation_finishes_from_its_record_once_the_change_is_committed(self) -> None:
        self.append_to(ROADMAP_YAML)
        outcomes = [self.derive(), st.Completed()]

        def execute(ctx: st.ExecutionContext):
            self.ran.append(ctx.work.id)
            return outcomes[min(len(self.ran), len(outcomes)) - 1]

        call = self.start(execute)
        with self.assertRaises(StopError):
            call()
        self.assertEqual(self.ran, [self.w1])

        self.commit(ROADMAP_YAML)
        result = call()

        self.assertEqual(result.status, "completed")
        self.assertEqual(self.ran, [self.w1, self.w1])  # the refused cycle is not run again; the next one is
        derived = [w for w in ProjectView.load(self.store).works.values() if w.name == "Fix it"]
        self.assertEqual(len(derived), 1)
        self.assertEqual((self.dirty(), self.head(), self.pending()), ([], self.remote_head(), []))
        self.assertEqual(validate_project(self.store), [])

    def test_a_clean_derivation_still_registers(self) -> None:
        outcomes = [self.derive(), st.Completed()]

        def execute(ctx: st.ExecutionContext):
            self.ran.append(ctx.work.id)
            return outcomes[min(len(self.ran), len(outcomes)) - 1]

        self.assertEqual(self.start(execute)().status, "completed")
        self.assertEqual(len([w for w in ProjectView.load(self.store).works.values() if w.name == "Fix it"]), 1)
        self.assertEqual((self.dirty(), self.pending(), validate_project(self.store)), ([], [], []))


# --------------------------------------------------------------------------- what this must not change
class UnchangedTests(ResultPathCase):
    def test_a_hold_over_a_dirty_result_path_still_holds(self) -> None:
        self.draft_at(self.result)

        result = self.start(self.returning(st.Hold("later")))()

        self.assertEqual((result.status, self.body()), ("held", DRAFT))
        self.assertEqual((self.dirty(), self.head(), self.pending()), ([f"?? {self.result}"], self.remote_head(), []))

    def test_a_cancel_over_a_dirty_result_path_still_cancels(self) -> None:
        self.draft_at(self.result)
        view = ProjectView.load(self.store)
        relation = next(r for r in view.roadmap_relations if r.type == "requires_completion" and r.from_id == self.w1)

        result = self.start(self.returning(st.Cancel(Replan(remove_relation_ids=(relation.id,)), "not needed")))()

        self.assertEqual((result.status, self.body()), ("cancelled", DRAFT))
        self.assertEqual((self.dirty(), self.head(), self.pending()), ([f"?? {self.result}"], self.remote_head(), []))

    def test_a_cancel_over_a_dirty_replan_ledger_still_keeps_its_recorded_decision(self) -> None:
        """BL-030: the cancel stops at its Git stage, and its resume never asks the executor again."""
        self.append_to(ROADMAP_YAML)
        view = ProjectView.load(self.store)
        relation = next(r for r in view.roadmap_relations if r.type == "requires_completion" and r.from_id == self.w1)
        call = self.start(self.returning(st.Cancel(Replan(remove_relation_ids=(relation.id,)), "not needed")))

        for _ in range(3):
            with self.assertRaises(StopError) as refused:
                call()
            self.assertEqual(refused.exception.code, "dirty_overlap")

        self.assertEqual(self.ran, [self.w1])
        self.assertEqual(self.events_of(self.w1), ["work_started", "work_target_added", "work_target_removed", "work_cancelled"])

    def test_a_change_to_the_event_log_is_still_refused_before_the_executor(self) -> None:
        """BL-041: a path known before the first effect is refused with nothing recorded and no executor."""
        self.append_to(EVENT_LOG)

        with self.assertRaises(StopError) as refused:
            self.start(self.completing())()

        self.assertEqual((refused.exception.code, self.ran, self.pending()), ("dirty_overlap", [], []))
        self.assertEqual(self.dirty(), [f"M {EVENT_LOG}"])

    def test_the_opening_lifecycle_events_the_refusal_leaves_are_never_removed(self) -> None:
        """BL-020: what was recorded stays recorded; a refusal does not take back the Work's opening events."""
        self.draft_at(self.result)
        call = self.start(self.completing())
        self.assertRefusedWithBytesKept(call, self.result, DRAFT)

        self.assertEqual(self.events_of(self.w1), ["work_started", "work_target_added"])
        self.assertRefusedWithBytesKept(call, self.result, DRAFT)
        self.assertEqual(self.events_of(self.w1), ["work_started", "work_target_added"])
        self.assertEqual(len(self.pending()), 1)

    def test_an_executor_that_wrote_its_result_and_failed_still_resumes(self) -> None:
        """A clean START: the executor's own output must never become a change from before the operation."""
        state = {"fail": True}

        def execute(ctx: st.ExecutionContext):
            self.ran.append(ctx.work.id)
            (self.root / self.result).write_text("produced\n", encoding="utf-8")
            if state["fail"]:
                raise Died("died after writing its result")
            return st.Completed((self.result,))

        call = self.start(execute)
        with self.assertRaises(Died):
            call()
        self.assertEqual(self.pending()[0]["notes"]["preexisting_dirty"], [])

        state["fail"] = False
        self.assertEqual(call().status, "completed")
        self.assertEqual((self.dirty(), self.head(), self.pending()), ([], self.remote_head(), []))


# --------------------------------------------------------------------------- records made before this change
class LegacyRecordTests(ResultPathCase):
    """A record whose own writes are in the changed ledger cannot be told apart from the person's change.

    Those are the records the implementation before this change left behind. They are not repaired,
    not resumed on a guess and not grown: the refusal they already meet stays the refusal they meet,
    and nothing of the person's change is committed or pushed on their behalf.
    """

    def test_a_derivation_stuck_before_this_change_is_left_exactly_as_it_is(self) -> None:
        self.append_to(ROADMAP_YAML)
        derive = st.Derive({"fix": st.DerivedWork("Fix it", "fixed", derivation_detail="because")})
        call = self.start(self.returning(derive))
        head = self.head()

        with before_bl042_derive(), self.assertRaises(StopError) as stuck:
            call()

        self.assertEqual(stuck.exception.code, "dirty_overlap")
        stuck_counts = self.counts()
        self.assertGreater(stuck_counts[2], 2)  # the pre-change record applied its own writes over the change

        for _ in range(3):
            with self.assertRaises(StopError) as refused:
                call()
            self.assertEqual(refused.exception.code, "dirty_overlap")
            self.assertEqual(self.counts(), stuck_counts)  # neither repaired nor grown

        # The derivation this record decided is registered again from the record (BL-046), so the
        # executor is not asked a second time at all; the refusal it stops at is the same one.
        self.assertEqual(self.ran, [self.w1])
        self.assertEqual((self.head(), self.remote_head()), (head, head))  # nothing of theirs is committed or pushed
        self.assertIn(f"M {ROADMAP_YAML}", self.dirty())


if __name__ == "__main__":
    unittest.main()
