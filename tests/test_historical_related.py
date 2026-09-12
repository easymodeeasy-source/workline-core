"""BL-009: historical Related evidence versus a Work's current read obligation.

A Related edge records what a Work had to read. While that Work can still run,
the edge is a current obligation: START resolves every ``must_read``, every
applicable ``conditional_must_read`` and the ``obey`` chain before the Work
executes, and STOPs when one is gone. Once the Work is terminal the same edge is
historical evidence: it is kept exactly as recorded, a later Work may delete its
target, and that absence alone never makes the Project invalid.

Workline does not create the state its own rule refuses to run in: a Work may
not declare a deletion result that removes what another started, non-terminal
Work still has to read. No route for editing a started Work's Related edges is
added here; the Roadmap route stays unstarted-only.
"""

from __future__ import annotations

import inspect
from pathlib import Path
import unittest

from helpers import WorklineTestCase, completing_executor, git, scripted_executor
from workline import gitcmd
from workline import roadmap as rm
from workline import start as st
from workline.create import RelatedSpec
from workline.errors import SpecViolation, StopError
from workline.mutation import MutationController
from workline.state import ProjectView
from workline.store import ProjectStore
from workline.validate import validate_project

AUTHORITY = "A.md"
MISSING = "docs/gone.md"
BACKLOG = Path(__file__).resolve().parents[1] / "BACKLOG.md"


def events_of(store: ProjectStore, work_id: str) -> list[str]:
    return [e.type for e in ProjectView.load(store).events if e.entity == work_id]


def related_of(store: ProjectStore, work_id: str) -> list[tuple[str, str]]:
    return sorted((r.type, r.to) for r in ProjectView.load(store).related_from(work_id))


class HistoricalRelatedCase(WorklineTestCase):
    """A Phase whose Works carry the given Related specs, over seeded tracked files."""

    def seed(self, store: ProjectStore, files: dict[str, str]) -> None:
        for name, text in files.items():
            path = store.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        git(store.root, "add", "--", *files)
        git(store.root, "commit", "-m", "seed tracked files")

    def phase_with(self, store: ProjectStore, works: dict[str, tuple]) -> rm.PhaseEntryResult:
        roadmap = self.simple_roadmap(store)
        design = rm.PhaseEntryDesign(
            {key: rm.WorkDesign(key.upper(), f"{key} が成立する", related) for key, related in works.items()},
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
        )
        return rm.enter_phase(store, roadmap.phase_ids["a"], design)

    def deleting_executor(self, store: ProjectStore, *, delete: tuple[str, ...]):
        """Executor that removes tracked files and declares them as deletion results."""

        def execute(ctx: st.ExecutionContext):
            for name in delete:
                (store.root / name).unlink()
            return st.Completed(deleted_paths=delete)

        return execute

    def recording_executor(self, seen: list):
        def execute(ctx: st.ExecutionContext):
            seen.append(list(ctx.reading_plan))
            return st.Completed()

        return execute

    def assertReadTargetMissing(self, raised: StopError, work_id: str, target: str, relation_type: str) -> None:
        self.assertEqual(raised.code, "related_target_missing")
        for expected in (work_id, target, relation_type):
            self.assertIn(expected, raised.message)
        self.assertRegex(raised.message, r"relation rel_")


class HistoricalEvidenceTests(HistoricalRelatedCase):
    """A completed Work's Related edge survives its target's later deletion."""

    def test_a_later_work_may_delete_a_completed_works_must_read_target(self) -> None:
        store = self.new_project()
        self.seed(store, {AUTHORITY: "authority\n"})
        entry = self.phase_with(store, {"reader": (RelatedSpec("must_read", AUTHORITY),), "deleter": ()})
        reader, deleter = entry.work_ids["reader"], entry.work_ids["deleter"]
        self.assertEqual(st.start(store, reader, "single-work", completing_executor(store)).status, "completed")
        history = related_of(store, reader)

        result = st.start(store, deleter, "single-work", self.deleting_executor(store, delete=(AUTHORITY,)))

        self.assertEqual(result.status, "completed")
        self.assertFalse((store.root / AUTHORITY).exists())
        self.assertNotIn(AUTHORITY, git(store.root, "ls-files").split())
        self.assertEqual(related_of(store, reader), history, "the historical edge is kept as recorded")
        self.assertEqual(related_of(store, reader), [("must_read", AUTHORITY)])
        self.assertEqual(validate_project(store), [], "a dangling historical edge is not a defect")
        self.assertEqual(ProjectView.load(store).work_state(reader).state, "completed")

    def test_a_historical_dangling_edge_is_not_a_later_works_obligation(self) -> None:
        store = self.new_project()
        self.seed(store, {AUTHORITY: "authority\n"})
        entry = self.phase_with(
            store, {"reader": (RelatedSpec("must_read", AUTHORITY),), "deleter": (), "later": ()}
        )
        reader, deleter, later = (entry.work_ids[key] for key in ("reader", "deleter", "later"))
        st.start(store, reader, "single-work", completing_executor(store))
        st.start(store, deleter, "single-work", self.deleting_executor(store, delete=(AUTHORITY,)))

        plans: list[list[str]] = []
        result = st.start(store, later, "single-work", self.recording_executor(plans))

        self.assertEqual(result.status, "completed")
        self.assertNotIn(AUTHORITY, plans[0], "another Work never inherits the historical target")
        # the terminal Work is refused as terminal, never as an unresolvable reading target
        with self.assertRaises(SpecViolation) as ctx:
            st.start(store, reader, "single-work", self.recording_executor(plans))
        self.assertIn("completed", ctx.exception.message)
        self.assertNotIn("must read", ctx.exception.message)
        self.assertEqual(len(plans), 1, "a completed Work is not executed again")

    def test_a_work_may_delete_what_it_itself_had_to_read(self) -> None:
        store = self.new_project()
        self.seed(store, {AUTHORITY: "authority\n"})
        entry = self.phase_with(store, {"retire": (RelatedSpec("must_read", AUTHORITY),)})
        retire = entry.work_ids["retire"]

        result = st.start(store, retire, "single-work", self.deleting_executor(store, delete=(AUTHORITY,)))

        self.assertEqual(result.status, "completed")
        self.assertEqual(related_of(store, retire), [("must_read", AUTHORITY)])
        self.assertEqual(validate_project(store), [])


class CurrentObligationTests(HistoricalRelatedCase):
    """A Work that can still run must be able to read what it was told to read."""

    def test_start_stops_when_a_must_read_target_is_missing(self) -> None:
        store = self.new_project()
        entry = self.phase_with(store, {"reader": (RelatedSpec("must_read", MISSING),)})
        reader = entry.work_ids["reader"]
        seen: list[list[str]] = []

        with self.assertRaises(StopError) as ctx:
            st.start(store, reader, "single-work", self.recording_executor(seen))

        self.assertReadTargetMissing(ctx.exception, reader, MISSING, "must_read")
        self.assertEqual(seen, [], "the executor never ran")
        self.assertEqual(events_of(store, reader), [], "no lifecycle event was written")
        self.assertEqual(ProjectView.load(store).work_state(reader).state, "unstarted")
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(related_of(store, reader), [("must_read", MISSING)], "nothing was repaired automatically")

    def test_start_stops_when_an_obey_target_is_missing(self) -> None:
        store = self.new_project()
        entry = self.phase_with(store, {"reader": (RelatedSpec("obey", MISSING),)})
        reader = entry.work_ids["reader"]

        with self.assertRaises(StopError) as ctx:
            st.start(store, reader, "single-work", completing_executor(store))

        self.assertReadTargetMissing(ctx.exception, reader, MISSING, "obey")

    def test_an_applicable_conditional_must_read_target_must_resolve(self) -> None:
        store = self.new_project()
        self.seed(store, {"src/app.py": "x = 1\n"})
        condition = {"kind": "path_glob", "pattern": "src/*.py"}
        entry = self.phase_with(store, {"reader": (RelatedSpec("conditional_must_read", MISSING, condition),)})
        reader = entry.work_ids["reader"]

        with self.assertRaises(StopError) as ctx:
            st.start(store, reader, "single-work", completing_executor(store))

        self.assertReadTargetMissing(ctx.exception, reader, MISSING, "conditional_must_read")

    def test_a_conditional_must_read_that_does_not_apply_stops_nothing(self) -> None:
        store = self.new_project()
        condition = {"kind": "path_glob", "pattern": "nothing/here/*.py"}
        entry = self.phase_with(store, {"reader": (RelatedSpec("conditional_must_read", MISSING, condition),)})
        reader = entry.work_ids["reader"]
        seen: list[list[str]] = []

        result = st.start(store, reader, "single-work", self.recording_executor(seen))

        self.assertEqual(result.status, "completed")
        self.assertNotIn(MISSING, seen[0], "a condition that does not apply is not a reading obligation")

    def test_an_externally_deleted_target_stops_the_next_start(self) -> None:
        store = self.new_project()
        self.seed(store, {AUTHORITY: "authority\n"})
        entry = self.phase_with(store, {"reader": (RelatedSpec("must_read", AUTHORITY),)})
        reader = entry.work_ids["reader"]
        git(store.root, "rm", "-q", "--", AUTHORITY)  # removed outside any Workline operation
        git(store.root, "commit", "-m", "external removal")

        with self.assertRaises(StopError) as ctx:
            st.start(store, reader, "single-work", completing_executor(store))

        self.assertReadTargetMissing(ctx.exception, reader, AUTHORITY, "must_read")
        self.assertEqual(related_of(store, reader), [("must_read", AUTHORITY)], "no automatic repair")
        self.assertEqual(validate_project(store), [], "the refusal is at execution, not a structural rewrite")


class DeletionGuardTests(HistoricalRelatedCase):
    """Workline's own deletion never takes away what a started Work still has to read."""

    def reader_and_deleter(self, store: ProjectStore) -> tuple[str, str]:
        self.seed(store, {AUTHORITY: "authority\n"})
        entry = self.phase_with(store, {"reader": (RelatedSpec("must_read", AUTHORITY),), "deleter": ()})
        return entry.work_ids["reader"], entry.work_ids["deleter"]

    def assertDeletionRefused(self, store: ProjectStore, reader: str, deleter: str) -> None:
        head = gitcmd.head_commit(store.root)

        with self.assertRaises(StopError) as ctx:
            st.start(store, deleter, "single-work", self.deleting_executor(store, delete=(AUTHORITY,)))

        self.assertEqual(ctx.exception.code, "completion_precheck_failed")
        for expected in (AUTHORITY, reader, "must_read"):
            self.assertIn(expected, ctx.exception.message)
        self.assertNotEqual(ProjectView.load(store).work_state(deleter).state, "completed")
        self.assertEqual(gitcmd.head_commit(store.root), head, "the deletion was not committed")
        self.assertIn(AUTHORITY, git(store.root, "ls-files").split(), "the file is still tracked")
        self.assertEqual(related_of(store, reader), [("must_read", AUTHORITY)], "no Related edge was rewritten")

    def test_a_held_works_current_read_target_cannot_be_deleted(self) -> None:
        store = self.new_project()
        reader, deleter = self.reader_and_deleter(store)
        held = st.start(store, reader, "single-work", scripted_executor({"*": [st.Hold("waiting")]}))
        self.assertEqual((held.status, ProjectView.load(store).work_state(reader).state), ("held", "held"))

        self.assertDeletionRefused(store, reader, deleter)

    def test_an_in_progress_works_current_read_target_cannot_be_deleted(self) -> None:
        store = self.new_project()
        reader, deleter = self.reader_and_deleter(store)
        moved = st.start(
            store,
            reader,
            "single-work",
            scripted_executor({"*": [st.Derive({"fix": st.DerivedWork("Fix", "fixed")}, move=True)]}),
        )
        self.assertEqual((moved.status, ProjectView.load(store).work_state(reader).state), ("moved", "in_progress"))

        self.assertDeletionRefused(store, reader, deleter)

    def test_an_unstarted_works_target_may_still_be_deleted_and_stops_that_work_later(self) -> None:
        store = self.new_project()
        reader, deleter = self.reader_and_deleter(store)

        result = st.start(store, deleter, "single-work", self.deleting_executor(store, delete=(AUTHORITY,)))

        self.assertEqual(result.status, "completed", "future plan is not protected by this guard")
        self.assertEqual(ProjectView.load(store).work_state(reader).state, "unstarted")
        with self.assertRaises(StopError) as ctx:
            st.start(store, reader, "single-work", completing_executor(store))
        self.assertReadTargetMissing(ctx.exception, reader, AUTHORITY, "must_read")


class ScopeTests(HistoricalRelatedCase):
    """No new maintenance capability, and the existing one is untouched."""

    def test_no_related_maintenance_route_was_added_for_started_works(self) -> None:
        store = self.new_project()
        self.seed(store, {AUTHORITY: "authority\n"})
        entry = self.phase_with(store, {"reader": (RelatedSpec("must_read", AUTHORITY),), "other": ()})
        reader = entry.work_ids["reader"]
        st.start(store, reader, "single-work", scripted_executor({"*": [st.Hold("waiting")]}))
        existing = ProjectView.load(store).related_from(reader)[0].id

        with self.assertRaises(SpecViolation):
            rm.maintain_work_related(store, reader, add=(RelatedSpec("must_read", "B.md"),))
        with self.assertRaises(SpecViolation):
            rm.maintain_work_related(store, reader, remove_relation_ids=(existing,))

        public_st = {name for name in dir(st) if not name.startswith("_")}
        public_rm = {name for name in dir(rm) if not name.startswith("_")}
        self.assertEqual({name for name in public_st if "maintain" in name.lower()}, set())
        self.assertEqual({name for name in public_rm if "maintain" in name.lower()}, {"maintain_work_related"})
        for helper in (st.read_obligations, st.require_read_targets):
            source = inspect.getsource(helper)
            for writer in ("add_effects", "mutation", "durable_write", "commit", "reserve_id"):
                self.assertNotIn(writer, source, f"{helper.__name__} must stay read-only")

    def test_unstarted_related_maintenance_is_unchanged(self) -> None:
        store = self.new_project()
        self.seed(store, {AUTHORITY: "authority\n"})
        entry = self.phase_with(store, {"reader": (), "other": ()})
        reader = entry.work_ids["reader"]

        result = rm.maintain_work_related(store, reader, add=(RelatedSpec("must_read", AUTHORITY),))

        self.assertTrue(result.changed)
        self.assertEqual(related_of(store, reader), [("must_read", AUTHORITY)])
        self.assertEqual(events_of(store, reader), [], "related maintenance is not a lifecycle event")
        self.assertEqual(ProjectView.load(store).work_state(reader).state, "unstarted")
        self.assertEqual(validate_project(store), [])

    def test_backlog_tracks_the_correction_requirements_under_bl_020(self) -> None:
        text = BACKLOG.read_text(encoding="utf-8")
        section = text.split("### BL-020")[1].split("### BL-021")[0]
        for requirement in (
            "元の記録を物理削除・書換えしない",
            "訂正自体を正式な記録として残す",
            "downstream readerが訂正の存在を機械的に判定できる",
            "superseded / invalidatedなhistorical factを現在の真実として扱わない",
        ):
            self.assertIn(requirement, section)
        self.assertIn("BL-009", section, "the requirement's origin is traceable")


if __name__ == "__main__":
    unittest.main()
