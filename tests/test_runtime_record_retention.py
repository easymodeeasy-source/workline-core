"""Retention of runtime recovery records (BL-019).

A recovery record exists so an interrupted operation can be resumed. Once a
mutation has closed as completed, nothing reads its record: a resume looks only
at pending records, and the Project開始 residue proof accepts only abandoned
ones. So the mutation that wrote such a record takes it away again - but only
where it can show that doing so loses nothing.

What is never removed: a pending record, an abandoned record, a record a
mutation resumed rather than wrote from the beginning, and any record an earlier
mutation left behind. Everything unproven is kept.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git, scripted_executor
from workline import gitcmd
from workline import roadmap as rm
from workline import start as st
from workline import yamlish
from workline.create import RelatedSpec
from workline.errors import StopError
from workline.mutation import CLOSED_RECORD_FIELDS, Mutation, MutationController
from workline.project_start import _CLOSED_INTENT_FIELDS
from workline.store import MUTATIONS_DIR, ProjectStore


class RetentionCase(WorklineTestCase):
    """A Project with one Phase and two Works, plus record helpers."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        roadmap = self.simple_roadmap(self.store)
        entry = self.simple_entry(self.store, roadmap.phase_ids["a"], {"w1": "W1 done", "w2": "W2 done"})
        self.w1 = entry.work_ids["w1"]
        self.w2 = entry.work_ids["w2"]

    # observation -----------------------------------------------------------
    def records(self) -> dict[str, str]:
        """Every record on disk as ``mutation_id -> status``, read as plain data."""
        return {
            path.stem: yamlish.load(path.read_text(encoding="utf-8"))["status"]
            for path in sorted(self.store.mutations.glob("*.yaml"))
        }

    def record_bytes(self) -> dict[str, bytes]:
        return {path.name: path.read_bytes() for path in sorted(self.store.mutations.glob("*.yaml"))}

    def relative(self, name: str) -> str:
        return f"{MUTATIONS_DIR}/{name}"

    # producing records -----------------------------------------------------
    def complete_work(self, work_id: str) -> None:
        st.start(self.store, work_id, "single-work", completing_executor(self.store))

    def pending_work(self, work_id: str) -> str:
        """Leave ``work_id`` waiting on a question: its mutation stays pending."""
        st.start(self.store, work_id, "single-work", scripted_executor({"*": [st.QuestionWait("why?")]}))
        (pending,) = MutationController(self.store).list_pending()
        return pending["mutation_id"]

    def tracked_at_completion(self, *, in_head: bool):
        """Put this run's own record into Git in the instant before cleanup looks.

        The record is created inside the operation, so it can only become
        tracked while the operation runs. Hooking the save that writes the
        closing status puts it in Git exactly between that write and the
        cleanup, with ``resumed`` still False - which is what makes the index
        and HEAD conditions the reason the record survives, rather than the
        resumed condition short-circuiting ahead of them.
        """
        save = Mutation._save

        def save_then_track(mutation: Mutation) -> None:
            save(mutation)
            if mutation.record["status"] != "completed":
                return
            relative = f"{MUTATIONS_DIR}/{mutation.path.name}"
            git(mutation.store.root, "add", "--", relative)
            if in_head:
                git(mutation.store.root, "commit", "-m", "someone committed the record")
                git(mutation.store.root, "rm", "--cached", "-q", "--", relative)

        return mock.patch.object(Mutation, "_save", save_then_track)

    def watch_removability(self):
        """Record what the eligibility proof answered, and whether it ran at all."""
        answers: list[tuple[bool, bool]] = []
        removable = Mutation._own_record_removable

        def watch(mutation: Mutation) -> bool:
            answer = removable(mutation)
            answers.append((mutation.resumed, answer))
            return answer

        return mock.patch.object(Mutation, "_own_record_removable", watch), answers

    def abandoned_start(self) -> str:
        """A Work whose must_read target is missing STOPs before it records an effect."""
        design = rm.PhaseEntryDesign(
            {"r": rm.WorkDesign("R", "r done", (RelatedSpec("must_read", "MISSING.md"),))},
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
        )
        phase = self.simple_roadmap(self.store, {"b": ("Phase B", "B が成立する")}).phase_ids["b"]
        entry = rm.enter_phase(self.store, phase, design)
        before = set(self.records())
        with self.assertRaises(StopError):
            st.start(self.store, entry.work_ids["r"], "single-work", completing_executor(self.store))
        (added,) = set(self.records()) - before
        return added


# --------------------------------------------------------------------------- what is removed
class CompletedRecordTests(RetentionCase):
    def test_a_completed_operation_leaves_no_record_of_its_own(self) -> None:
        before = self.records()
        self.complete_work(self.w1)

        self.assertEqual(self.records(), before)

    def test_the_record_is_there_while_the_operation_is_still_open(self) -> None:
        mutation_id = self.pending_work(self.w1)

        self.assertEqual(self.records(), {mutation_id: "pending"})
        self.assertTrue((self.store.mutations / f"{mutation_id}.yaml").is_file())

    def test_a_fresh_project_carries_no_runtime_record_and_no_git_noise(self) -> None:
        root = self.new_dir("fresh")
        from helpers import WORKLINE_ROOT, cwd
        from workline.project_start import project_start

        with cwd(WORKLINE_ROOT):
            project_start(root, WORKLINE_ROOT)

        store = ProjectStore(root)
        self.assertEqual(sorted(store.mutations.glob("*.yaml")), [])
        self.assertEqual(git(root, "status", "--porcelain", "--untracked-files=all").strip(), "")

    def test_each_operation_cleans_up_only_after_its_own_work_is_finished(self) -> None:
        # Two operations in a row: neither leaves anything, and the second sees
        # an empty runtime area rather than the first one's leftovers.
        self.complete_work(self.w1)
        self.assertEqual(self.records(), {})
        self.complete_work(self.w2)
        self.assertEqual(self.records(), {})
        self.assertEqual(git(self.store.root, "status", "--porcelain", "--", MUTATIONS_DIR).strip(), "")


# --------------------------------------------------------------------------- what is kept
class KeptRecordTests(RetentionCase):
    def test_a_pending_record_survives_and_still_resumes_as_the_same_mutation(self) -> None:
        mutation_id = self.pending_work(self.w1)
        kept = self.record_bytes()

        # An unrelated question: does anything else disturb it? Nothing may.
        self.assertEqual(self.records(), {mutation_id: "pending"})
        self.assertEqual(self.record_bytes(), kept)

        result = st.start(self.store, self.w1, "single-work", completing_executor(self.store))
        self.assertEqual((result.status, result.mutation_id), ("completed", mutation_id))

    def test_an_abandoned_record_survives_untouched(self) -> None:
        mutation_id = self.abandoned_start()
        kept = self.record_bytes()

        self.assertEqual(self.records()[mutation_id], "abandoned")
        self.complete_work(self.w1)

        self.assertEqual(self.records()[mutation_id], "abandoned")
        self.assertEqual(self.record_bytes(), kept)

    def test_a_resumed_mutation_keeps_its_record_when_it_completes(self) -> None:
        mutation_id = self.pending_work(self.w1)

        result = st.start(self.store, self.w1, "single-work", completing_executor(self.store))

        self.assertEqual(result.mutation_id, mutation_id)
        self.assertEqual(self.records(), {mutation_id: "completed"})

    def test_a_record_edited_while_its_operation_waited_is_kept(self) -> None:
        """The reason a resumed record is never removed, as a sequence.

        The extra field is tolerated on load and written back on save, so by the
        time the mutation completes, the bytes on disk are exactly what it just
        wrote - and would pass a content comparison. Only "this run never
        resumed it" keeps the edit.
        """
        mutation_id = self.pending_work(self.w1)
        path = self.store.mutations / f"{mutation_id}.yaml"
        record = yamlish.load(path.read_text(encoding="utf-8"))
        record["someone_elses_note"] = "do not delete me"
        path.write_text(yamlish.dump(record), encoding="utf-8")

        st.start(self.store, self.w1, "single-work", completing_executor(self.store))

        self.assertTrue(path.is_file())
        self.assertEqual(yamlish.load(path.read_text(encoding="utf-8"))["someone_elses_note"], "do not delete me")

    def test_another_mutations_record_is_left_alone_by_a_completing_operation(self) -> None:
        """A pending bootstrap backfill declares a scope no Work touches.

        So an ordinary Work runs to completion beside it. The Work removes its
        own record and leaves the other one exactly as it found it.
        """
        from workline import bootstrap as bs
        from workline import gitops

        (self.store.root / ".claude" / "skills" / "workline" / "SKILL.md").unlink()
        with mock.patch.object(gitops, "record_preexisting_dirty", side_effect=RuntimeError("interrupted")):
            with self.assertRaises(RuntimeError):
                bs.backfill_bootstrap(self.store.root)
        kept = self.record_bytes()
        self.assertEqual(list(self.records().values()), ["pending"])

        st.start(self.store, self.w1, "single-work", completing_executor(self.store))

        self.assertEqual(self.record_bytes(), kept)

    def test_an_open_record_blocking_an_overlapping_operation_is_still_untouched(self) -> None:
        mutation_id = self.pending_work(self.w1)
        kept = self.record_bytes()

        with self.assertRaises(StopError) as raised:
            self.complete_work(self.w2)

        self.assertEqual(raised.exception.code, "reconcile_required")
        self.assertEqual(self.record_bytes(), kept)
        self.assertEqual(self.records(), {mutation_id: "pending"})


# --------------------------------------------------------------------------- the eligibility proof
class RemovalProofTests(RetentionCase):
    def test_a_record_the_index_holds_is_kept(self) -> None:
        """A record that became tracked while the operation ran is not removed.

        Nothing of this Project's history would be lost by keeping it; deleting
        it would stage the removal of a file Git tracks, which ``rules/git``
        forbids.
        """
        watch, answers = self.watch_removability()
        with watch, self.tracked_at_completion(in_head=False):
            self.complete_work(self.w1)

        (mutation_id,) = self.records()
        relative = self.relative(f"{mutation_id}.yaml")
        self.assertEqual(answers, [(False, False)])  # never resumed, and still refused
        self.assertEqual(gitcmd.tracked_under(self.store.root, relative), [relative])
        self.assertTrue((self.store.mutations / f"{mutation_id}.yaml").is_file())

    def test_a_record_only_head_holds_is_kept(self) -> None:
        """``git rm --cached`` leaves the index empty while HEAD keeps the file.

        An index-only question answers "untracked" here, so this is the case
        that shows HEAD is asked as well.
        """
        watch, answers = self.watch_removability()
        with watch, self.tracked_at_completion(in_head=True):
            self.complete_work(self.w1)

        (mutation_id,) = self.records()
        relative = self.relative(f"{mutation_id}.yaml")
        self.assertEqual(answers, [(False, False)])
        self.assertEqual(gitcmd.tracked_under(self.store.root, relative), [])
        self.assertEqual(gitcmd.head_paths(self.store.root, relative), [relative])
        self.assertTrue((self.store.mutations / f"{mutation_id}.yaml").is_file())

    def test_a_record_a_resumed_operation_committed_is_kept(self) -> None:
        """The same protection through the resumed path, end to end."""
        mutation_id = self.pending_work(self.w1)
        relative = self.relative(f"{mutation_id}.yaml")
        git(self.store.root, "add", "--", relative)
        git(self.store.root, "commit", "-m", "someone committed the recovery record")
        committed = (self.store.mutations / f"{mutation_id}.yaml").read_bytes()

        st.start(self.store, self.w1, "single-work", completing_executor(self.store))

        self.assertTrue((self.store.mutations / f"{mutation_id}.yaml").is_file())
        self.assertEqual(gitcmd.head_paths(self.store.root, relative), [relative])
        # Reported as modified, never as removed: writing its own closing status
        # is what the owning mutation may do to its own recovery metadata, and it
        # predates this retention rule. Deleting a committed file must not happen.
        status = git(self.store.root, "status", "--porcelain", "--", relative).strip()
        self.assertEqual(status[:2].strip(), "M")
        self.assertNotIn("D", status[:2])
        self.assertNotEqual((self.store.mutations / f"{mutation_id}.yaml").read_bytes(), committed)

    def test_a_record_that_cannot_be_read_is_kept(self) -> None:
        read_bytes = Path.read_bytes

        def unreadable_record(path: Path) -> bytes:
            if path.suffix == ".yaml" and path.parent.name == "mutations":
                raise OSError("cannot read the record")
            return read_bytes(path)

        with mock.patch.object(Path, "read_bytes", unreadable_record):
            self.complete_work(self.w1)

        self.assertEqual(list(self.records().values()), ["completed"])

    def test_an_unanswerable_index_question_keeps_the_record(self) -> None:
        with mock.patch.object(gitcmd, "tracked_under", return_value=None):
            self.complete_work(self.w1)

        self.assertEqual(list(self.records().values()), ["completed"])

    def test_an_unanswerable_head_question_keeps_the_record(self) -> None:
        with mock.patch.object(gitcmd, "head_paths", return_value=None):
            self.complete_work(self.w1)

        self.assertEqual(list(self.records().values()), ["completed"])

    def test_a_missing_git_keeps_the_record_and_the_operation_still_succeeds(self) -> None:
        from workline.errors import GitError

        with mock.patch.object(gitcmd, "head_paths", side_effect=GitError("git executable not found")):
            self.complete_work(self.w1)

        self.assertEqual(list(self.records().values()), ["completed"])

    def test_a_record_that_is_not_a_plain_file_is_kept(self) -> None:
        seen: list[bool] = []
        real = Mutation._own_record_removable

        def watch(mutation: Mutation) -> bool:
            answer = real(mutation)
            seen.append(answer)
            return answer

        # A reparse point / non-regular record: os.lstat reports it as such.
        class _Link:
            st_mode = stat.S_IFLNK | 0o644
            st_file_attributes = 0

        with mock.patch.object(Mutation, "_own_record_removable", watch):
            with mock.patch.object(os, "lstat", return_value=_Link()):
                self.complete_work(self.w1)

        self.assertEqual(seen, [False])
        self.assertEqual(list(self.records().values()), ["completed"])

    def test_a_record_with_an_unexpected_field_is_kept(self) -> None:
        """An implementation that only compared bytes would remove this one."""
        real = Mutation._save

        def save_with_extra(mutation: Mutation) -> None:
            mutation.record["arrived_from_somewhere"] = True
            real(mutation)

        with mock.patch.object(Mutation, "_save", save_with_extra):
            self.complete_work(self.w1)

        (status,) = self.records().values()
        self.assertEqual(status, "completed")

    def test_a_record_with_a_non_integer_version_is_kept(self) -> None:
        real = Mutation._save

        def save_with_bool_version(mutation: Mutation) -> None:
            mutation.record["version"] = True  # True == 1, but it is not an int
            real(mutation)

        with mock.patch.object(Mutation, "_save", save_with_bool_version):
            self.complete_work(self.w1)

        self.assertEqual(len(self.records()), 1)

    def test_a_record_changed_after_the_last_save_is_kept(self) -> None:
        real = Mutation._save

        def save_then_let_someone_else_write(mutation: Mutation) -> None:
            real(mutation)
            if mutation.record["status"] == "completed":
                mutation.path.write_text("# replaced by someone else\n", encoding="utf-8")

        with mock.patch.object(Mutation, "_save", save_then_let_someone_else_write):
            self.complete_work(self.w1)

        (path,) = sorted(self.store.mutations.glob("*.yaml"))
        self.assertEqual(path.read_text(encoding="utf-8"), "# replaced by someone else\n")

    def test_an_unremovable_record_does_not_fail_the_operation_or_repeat_its_effects(self) -> None:
        head_before = gitcmd.head_commit(self.store.root)
        events_before = self.store.events_jsonl.read_text(encoding="utf-8")

        with mock.patch.object(type(self.store.mutations), "unlink", side_effect=OSError("locked")):
            result = st.start(self.store, self.w1, "single-work", completing_executor(self.store))

        self.assertEqual(result.status, "completed")
        self.assertEqual(list(self.records().values()), ["completed"])
        # The domain effects ran exactly once.
        self.assertNotEqual(gitcmd.head_commit(self.store.root), head_before)
        events_after = self.store.events_jsonl.read_text(encoding="utf-8")
        self.assertTrue(events_after.startswith(events_before))
        self.assertEqual(events_after.count('"work_completed"'), 1)

    def test_a_leftover_completed_record_does_not_disturb_the_next_operation(self) -> None:
        """What an interrupted cleanup leaves: status written, file still there."""
        with mock.patch.object(type(self.store.mutations), "unlink", side_effect=OSError("interrupted")):
            self.complete_work(self.w1)
        leftover = self.records()
        self.assertEqual(list(leftover.values()), ["completed"])

        self.complete_work(self.w2)

        self.assertEqual(self.records(), leftover)


# --------------------------------------------------------------------------- what stays true elsewhere
class UnchangedBehaviourTests(RetentionCase):
    def test_the_closed_record_shape_matches_the_project_start_residue_proof(self) -> None:
        """Two places describe a closed record; they must describe the same one."""
        self.assertEqual(CLOSED_RECORD_FIELDS, _CLOSED_INTENT_FIELDS)

    def test_an_abandoned_project_start_residue_is_still_retried(self) -> None:
        """BL-022 recovery depends on the abandoned record still being there."""
        from helpers import WORKLINE_ROOT, cwd
        from workline import project_start as ps
        from workline.context import _pre_project_authorization
        from workline.mutation import WriteScope
        from workline.store import BOOTSTRAP_REL_PATH

        root = self.new_dir("residue")
        store = ProjectStore(root)
        invocation = {"operation": ps.OWNER, "project_root": str(store.root)}
        scope = WriteScope(files=(*store.canonical_relative_paths, BOOTSTRAP_REL_PATH))
        with _pre_project_authorization(store.root):
            mutation = MutationController(store).open(ps.OWNER, invocation, scope)
            mutation.abandon()
        self.assertTrue(mutation.path.is_file())
        kept = mutation.path.read_bytes()

        with cwd(WORKLINE_ROOT):
            result = ps.project_start(root, WORKLINE_ROOT)

        self.assertEqual(result.status, "initialized")
        self.assertEqual(mutation.path.read_bytes(), kept)

    def test_the_record_is_taken_away_only_after_every_effect_and_the_postcheck(self) -> None:
        """Nothing is cleaned up while the operation could still need to resume."""
        order: list[str] = []
        apply_effect = MutationController.apply_effect
        structure = st._structure_or_stop
        drop = Mutation._drop_own_record
        unlink = Path.unlink

        def note_effect(controller: MutationController, record: dict) -> None:
            apply_effect(controller, record)
            order.append(f"effect:{record['kind']}")

        def note_structure(store, context: str):
            view = structure(store, context)
            order.append(f"structure:{context}")
            return view

        def note_drop(mutation: Mutation) -> None:
            # Up to this instant the record is still on disk, so a crash
            # anywhere earlier leaves something to resume or to inspect.
            self.assertTrue(mutation.path.is_file())
            order.append("cleanup")
            drop(mutation)

        def note_unlink(path: Path, **kwargs: object) -> None:
            if path.suffix == ".yaml" and path.parent.name == "mutations":
                order.append("unlink")
            unlink(path, **kwargs)

        with (
            mock.patch.object(MutationController, "apply_effect", note_effect),
            mock.patch.object(st, "_structure_or_stop", note_structure),
            mock.patch.object(Mutation, "_drop_own_record", note_drop),
            mock.patch.object(Path, "unlink", note_unlink),
        ):
            self.complete_work(self.w1)

        # Exactly one attempt and exactly one removal, both after everything
        # else: a record removed early and written again would show up here as a
        # second pair.
        self.assertEqual(order.count("cleanup"), 1)
        self.assertEqual(order.count("unlink"), 1)
        self.assertEqual(order[-2:], ["cleanup", "unlink"])
        self.assertIn("effect:git_commit", order)
        self.assertIn("structure:postcheck", order)
        self.assertEqual(self.records(), {})

    def test_no_git_ignore_setting_is_created_or_changed(self) -> None:
        """The ignore decision: Workline owns no ignore rule anywhere."""
        exclude = self.store.root / ".git" / "info" / "exclude"
        before = exclude.read_bytes() if exclude.exists() else None

        self.complete_work(self.w1)
        self.pending_work(self.w2)

        self.assertEqual(exclude.read_bytes() if exclude.exists() else None, before)
        self.assertEqual([p.name for p in self.store.root.rglob(".gitignore")], [])
        self.assertEqual(git(self.store.root, "ls-files", "--", "*.gitignore").strip(), "")
        # Decidably not ignored: Workline added no rule, and it read none either.
        self.assertEqual(gitcmd.is_ignored(self.store.root, f"{MUTATIONS_DIR}/x.yaml"), False)

    def test_removal_happens_inside_the_operation_that_owns_the_lock(self) -> None:
        """Nothing is removed outside an operation's own authorization."""
        from workline.oplock import held_lock

        held: list[bool] = []
        real = Mutation._drop_own_record

        def watch(mutation: Mutation) -> None:
            held.append(held_lock(mutation.store) is not None)
            real(mutation)

        with mock.patch.object(Mutation, "_drop_own_record", watch):
            self.complete_work(self.w1)

        self.assertEqual(held, [True])


if __name__ == "__main__":
    unittest.main()
