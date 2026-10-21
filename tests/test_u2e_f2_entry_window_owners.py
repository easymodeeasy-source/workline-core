"""RB11 U2-E lane F2 (core): the same ENTRY WINDOW in the owners that open their mutation before the Git readiness check.

See ``test_u2e_f2_p6_entry_window`` for the P6 owner and the rule. This module drives the OTHER owners that were found,
by running them on a detached HEAD, to leave a pending, effect-free, reservation-free owner mutation behind
(``gitops.ensure_git_ready`` after ``MutationController.open``, outside every ``abandon_on_stop``):

* START's standalone plan exclusion (``start.plan_exclude_standalone_work``): the stranded record held the Work and
  the three ledgers, so EVERY later plan exclusion, lifecycle operation and CREATE was refused ``reconcile required``;
* every Roadmap operation that opens through ``roadmap._open`` (Roadmap / Phase creation, Phase entry, hold / resume /
  cancel, plan exclusion, ...): shown here through Roadmap creation and a Phase hold.

Controls that already followed the rule (direct CREATE) and the helper both repairs use
(``mutation.abandon_new_on_stop``) are pinned too.
"""

from __future__ import annotations

from typing import Any

from helpers import WorklineTestCase, completing_executor, git
from planning_helpers import Crash, PlanningTestCase, crash_at
from workline import gitops
from workline import roadmap as rm
from workline import start as st
from workline.create import WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, StopError
from workline.mutation import MutationController, WriteScope
from workline.oplock import project_operation
from workline.state import ProjectView
from workline.validate import validate_project


class OwnerCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.root = self.store.root

    def detach(self) -> str:
        branch = git(self.root, "symbolic-ref", "--short", "HEAD").strip()
        git(self.root, "checkout", "-q", "--detach", "HEAD")
        return branch

    def reattach(self, branch: str) -> None:
        git(self.root, "checkout", "-q", branch)

    def pending(self) -> list[dict[str, Any]]:
        return MutationController(self.store).list_pending()

    def records(self, operation: str) -> list[dict[str, Any]]:
        """EVERY record of ``operation``, whatever its status."""
        return [record for record in MutationController(self.store).list_records()
                if (record.get("invocation") or {}).get("operation") == operation]

    def assert_closed_empty(self, record: dict[str, Any]) -> None:
        self.assertEqual(("abandoned", [], {}), (record["status"], record["effects"], record["reserved_ids"]))

    def problems(self) -> list[str]:
        return [f"{problem.code}: {problem.message}" for problem in validate_project(self.store)]


# =========================================================================== START standalone plan exclusion

class PlanExclusionEntryWindowTests(OwnerCase):
    def setUp(self) -> None:
        super().setUp()
        self.a, self.b = (create_standalone_work(self.store, WorkSpec(name, name.lower())).work_id for name in ("A", "B"))

    def test_a_detached_head_leaves_no_pending_owner(self) -> None:
        head = git(self.root, "rev-parse", "HEAD").strip()
        self.detach()
        with self.assertRaises(StopError) as raised:
            st.plan_exclude_standalone_work(self.store, self.a)
        self.assertEqual("detached_head", raised.exception.code)
        self.assertEqual([], self.pending())
        (record,) = self.records("start-plan-exclude")
        self.assert_closed_empty(record)
        self.assertEqual(head, git(self.root, "rev-parse", "HEAD").strip())

    def test_nothing_is_refused_afterwards(self) -> None:
        """The stranded record held the Work and the ledgers: another plan exclusion and a CREATE were refused."""
        branch = self.detach()
        with self.assertRaises(StopError):
            st.plan_exclude_standalone_work(self.store, self.a)
        self.reattach(branch)
        create_standalone_work(self.store, WorkSpec("C", "c"))
        self.assertEqual("plan_excluded", st.plan_exclude_standalone_work(self.store, self.b).status)
        self.assertEqual("plan_excluded", st.plan_exclude_standalone_work(self.store, self.a).status,
                         "the very request that was stopped, retried on a branch")
        self.assertEqual([], self.pending())
        self.assertEqual([], self.problems())

    def test_a_resumed_effect_free_record_is_kept_on_a_detached_head(self) -> None:
        """A record a crash left (the process died in the window) is only RESUMED by the retry: never abandoned there."""
        with crash_at(gitops, "ensure_git_ready"), self.assertRaises(Crash):
            st.plan_exclude_standalone_work(self.store, self.a)
        (pending,) = self.pending()
        self.assertEqual(("pending", []), (pending["status"], pending["effects"]))
        branch = self.detach()
        with self.assertRaises(StopError) as raised:
            st.plan_exclude_standalone_work(self.store, self.a)
        self.assertEqual("detached_head", raised.exception.code)
        self.assertEqual([pending["mutation_id"]], [record["mutation_id"] for record in self.pending()],
                         "the record the crash left is not this call's to abandon")
        self.reattach(branch)
        result = st.plan_exclude_standalone_work(self.store, self.a)
        self.assertEqual((pending["mutation_id"], "plan_excluded"), (result.mutation_id, result.status))
        self.assertEqual([], self.pending())


# =========================================================================== Roadmap operations (roadmap._open)

class RoadmapEntryWindowTests(OwnerCase):
    def test_a_detached_head_during_roadmap_creation_leaves_no_pending_owner(self) -> None:
        branch = self.detach()
        with self.assertRaises(StopError) as raised:
            self.simple_roadmap(self.store)
        self.assertEqual("detached_head", raised.exception.code)
        self.assertEqual([], self.pending())
        (record,) = self.records("roadmap-create")
        self.assert_closed_empty(record)
        self.reattach(branch)
        # ANOTHER Roadmap request was refused ("opened for a different request"); the same one is a fresh record
        self.simple_roadmap(self.store, {"x": ("Phase X", "x is true")})
        self.assertEqual([], self.pending())
        self.assertEqual([], self.problems())

    def test_the_same_roadmap_request_retried_creates_once(self) -> None:
        branch = self.detach()
        with self.assertRaises(StopError):
            self.simple_roadmap(self.store)
        self.reattach(branch)
        result = self.simple_roadmap(self.store)
        self.assertEqual([], self.pending())
        self.assertEqual(1, len(ProjectView.load(self.store).roadmaps))
        self.assertIn(result.roadmap_id, ProjectView.load(self.store).roadmaps)
        self.assertEqual([], self.problems())

    def test_a_detached_head_during_a_phase_hold_does_not_block_other_lifecycle_operations(self) -> None:
        roadmap = self.simple_roadmap(self.store)
        phase_id = roadmap.phase_ids["a"]
        branch = self.detach()
        with self.assertRaises(StopError) as raised:
            rm.hold_phase(self.store, phase_id)
        self.assertEqual("detached_head", raised.exception.code)
        self.assertEqual([], self.pending())
        (record,) = self.records("phase-hold")
        self.assert_closed_empty(record)
        self.reattach(branch)
        # the Roadmap's own hold shares the event log with the Phase hold: it was refused ``reconcile required``
        rm.hold_roadmap(self.store, roadmap.roadmap_id)
        rm.resume_roadmap(self.store, roadmap.roadmap_id)
        rm.hold_phase(self.store, phase_id)
        self.assertEqual([], self.pending())
        self.assertEqual([], self.problems())

    def test_a_resumed_roadmap_record_is_kept_on_a_detached_head(self) -> None:
        with crash_at(gitops, "ensure_git_ready"), self.assertRaises(Crash):
            self.simple_roadmap(self.store)
        (pending,) = self.pending()
        branch = self.detach()
        with self.assertRaises(StopError) as raised:
            self.simple_roadmap(self.store)
        self.assertEqual("detached_head", raised.exception.code)
        self.assertEqual([pending["mutation_id"]], [record["mutation_id"] for record in self.pending()])
        self.reattach(branch)
        self.simple_roadmap(self.store)
        self.assertEqual([], self.pending())
        self.assertEqual([], self.problems())


class ReviewedRoadmapEntryWindowTests(PlanningTestCase):
    """The review-v1 Roadmap creation opens through the same ``roadmap._open``."""

    def test_a_detached_head_during_a_review_v1_roadmap_creation_leaves_no_pending_owner(self) -> None:
        store = self.planning_project()
        branch = git(store.root, "symbolic-ref", "--short", "HEAD").strip()
        git(store.root, "checkout", "-q", "--detach", "HEAD")
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(store)
        self.assertEqual("detached_head", raised.exception.code)
        self.assertEqual([], MutationController(store).list_pending())
        (record,) = [r for r in MutationController(store).list_records()
                     if (r.get("invocation") or {}).get("operation") == "roadmap-create"]
        self.assertEqual(("abandoned", [], {}), (record["status"], record["effects"], record["reserved_ids"]))
        git(store.root, "checkout", "-q", branch)
        result = self.reviewed_roadmap(store)
        self.assertEqual([], MutationController(store).list_pending())
        self.assertIn(result.registration.roadmap_id, ProjectView.load(store).roadmaps)
        self.assertEqual([], [problem.code for problem in validate_project(store)])


# =========================================================================== controls

class AlreadyGuardedOwnerControlTests(OwnerCase):
    def test_direct_create_on_a_detached_head_leaves_no_pending_owner(self) -> None:
        """Direct CREATE has always guarded the window (``abandon_on_stop`` around Git readiness): the convention."""
        self.detach()
        with self.assertRaises(StopError) as raised:
            create_standalone_work(self.store, WorkSpec("A", "a"))
        self.assertEqual("detached_head", raised.exception.code)
        self.assertEqual([], self.pending())

    def test_start_of_a_work_on_a_detached_head_opens_no_record_at_all(self) -> None:
        """START's Work run path asks Git before it opens its mutation (``start.py``): no record of any status."""
        work_id = create_standalone_work(self.store, WorkSpec("A", "a")).work_id
        before = MutationController(self.store).list_records()
        self.detach()
        with self.assertRaises(StopError) as raised:
            st.start(self.store, work_id, "single-work", completing_executor(self.store))
        self.assertEqual("detached_head", raised.exception.code)
        self.assertEqual(before, MutationController(self.store).list_records())


# =========================================================================== AM-A: exactly the seven Roadmap operations

class CoveredRoadmapOperationTests(OwnerCase):
    """Each covered operation, on a detached HEAD, leaves a closed empty record and blocks nothing."""

    def roadmap_and_phase(self):
        roadmap = self.simple_roadmap(self.store)
        return roadmap.roadmap_id, roadmap.phase_ids["a"]

    def assert_window_closed(self, operation: str, call) -> None:
        branch = self.detach()
        with self.assertRaises(StopError) as raised:
            call()
        self.assertEqual("detached_head", raised.exception.code)
        self.assertEqual([], self.pending())
        record = self.records(operation)[-1]
        self.assert_closed_empty(record)
        self.reattach(branch)

    def test_phase_resume(self) -> None:
        _, phase_id = self.roadmap_and_phase()
        rm.hold_phase(self.store, phase_id)
        self.assert_window_closed("phase-resume", lambda: rm.resume_phase(self.store, phase_id))
        rm.resume_phase(self.store, phase_id)
        self.assertEqual([], self.pending())

    def test_phase_cancel(self) -> None:
        _, phase_id = self.roadmap_and_phase()
        self.assert_window_closed("phase-cancel", lambda: rm.cancel_phase(self.store, phase_id))
        rm.cancel_phase(self.store, phase_id)
        self.assertEqual([], self.pending())

    def test_roadmap_hold(self) -> None:
        roadmap_id, _ = self.roadmap_and_phase()
        self.assert_window_closed("roadmap-hold", lambda: rm.hold_roadmap(self.store, roadmap_id))
        rm.hold_roadmap(self.store, roadmap_id)
        self.assertEqual([], self.pending())

    def test_roadmap_resume(self) -> None:
        roadmap_id, _ = self.roadmap_and_phase()
        rm.hold_roadmap(self.store, roadmap_id)
        self.assert_window_closed("roadmap-resume", lambda: rm.resume_roadmap(self.store, roadmap_id))
        rm.resume_roadmap(self.store, roadmap_id)
        self.assertEqual([], self.pending())

    def test_roadmap_cancel(self) -> None:
        roadmap_id, _ = self.roadmap_and_phase()
        self.assert_window_closed("roadmap-cancel", lambda: rm.cancel_roadmap(self.store, roadmap_id))
        rm.cancel_roadmap(self.store, roadmap_id)
        self.assertEqual([], self.pending())


class NotCoveredRoadmapOperationTests(OwnerCase):
    """Operations outside the F2 scope behave as at production main: a detached HEAD leaves the pending record."""

    def assert_left_pending(self, operation: str, call) -> None:
        self.detach()
        with self.assertRaises(StopError) as raised:
            call()
        self.assertEqual("detached_head", raised.exception.code)
        (pending,) = self.pending()
        self.assertEqual(operation, pending["invocation"]["operation"])

    def test_phase_entry_is_not_covered(self) -> None:
        phase_id = self.simple_roadmap(self.store).phase_ids["a"]
        self.assert_left_pending("phase-entry", lambda: self.simple_entry(self.store, phase_id))

    def test_roadmap_add_phases_is_not_covered(self) -> None:
        from workline.phase_create import PhaseSpec

        roadmap_id = self.simple_roadmap(self.store).roadmap_id
        self.assert_left_pending(
            "roadmap-add-phases", lambda: rm.add_phases(self.store, roadmap_id, {"b": PhaseSpec("Phase B", "B が成立する")})
        )

    def test_phase_plan_exclude_is_not_covered(self) -> None:
        phase_id = self.simple_roadmap(self.store).phase_ids["a"]
        self.assert_left_pending("phase-plan-exclude", lambda: rm.plan_exclude_phase(self.store, phase_id))

    def test_work_plan_exclude_is_not_covered(self) -> None:
        phase_id = self.simple_roadmap(self.store).phase_ids["a"]
        work_id = self.simple_entry(self.store, phase_id).work_ids["w1"]
        self.assert_left_pending("work-plan-exclude", lambda: rm.plan_exclude_work(self.store, work_id))

    def test_work_related_maintenance_is_not_covered(self) -> None:
        from workline.create import RelatedSpec

        phase_id = self.simple_roadmap(self.store).phase_ids["a"]
        work_id = self.simple_entry(self.store, phase_id).work_ids["w1"]
        self.assert_left_pending(
            "work-related-maintenance",
            lambda: rm.maintain_work_related(self.store, work_id, add=(RelatedSpec("must_read", "README.md"),)),
        )


# =========================================================================== the helper

class AbandonNewOnStopTests(OwnerCase):
    """``mutation.abandon_new_on_stop``: abandon a STOP-ed, effect-free mutation THIS call began; never a resumed one."""

    OWNER = "roadmap"
    INVOCATION = {"operation": "u2e-f2-helper"}

    def opened(self, controller: MutationController) -> Any:
        return controller.open(self.OWNER, self.INVOCATION, WriteScope(files=(".workline/relations/roadmap.yaml",)))

    def test_a_new_mutation_is_abandoned_on_a_stop_and_the_stop_propagates(self) -> None:
        from workline.mutation import abandon_new_on_stop

        controller = MutationController(self.store)
        with project_operation(self.store, "u2e-f2-helper"):
            mutation = self.opened(controller)
            self.assertFalse(mutation.resumed)
            with self.assertRaises(StopError) as raised:
                with abandon_new_on_stop(mutation):
                    raise StopError("repository is in detached HEAD state", code="detached_head")
            self.assertEqual("detached_head", raised.exception.code)
            self.assertEqual("abandoned", mutation.status)
        self.assertEqual([], controller.list_pending())

    def test_any_other_stop_leaves_the_record_pending(self) -> None:
        """AM-A: no broad StopError swallowing - a reconcile required, or any other code, closes nothing."""
        from workline.mutation import abandon_new_on_stop

        controller = MutationController(self.store)
        with project_operation(self.store, "u2e-f2-helper"):
            mutation = self.opened(controller)
            with self.assertRaises(ReconcileRequired), abandon_new_on_stop(mutation):
                raise ReconcileRequired("reconcile required")
            self.assertEqual("pending", mutation.status)
            with self.assertRaises(StopError) as raised, abandon_new_on_stop(mutation):
                raise StopError("refused", code="u2e_refused")
            self.assertEqual("u2e_refused", raised.exception.code)
            self.assertEqual("pending", mutation.status)

    def test_a_record_that_holds_an_effect_is_never_abandoned(self) -> None:
        from workline.mutation import Effect, abandon_new_on_stop

        controller = MutationController(self.store)
        with project_operation(self.store, "u2e-f2-helper"):
            mutation = self.opened(controller)
            mutation.add_effects("s1", [Effect.write_file(".workline/relations/roadmap.yaml", "x\n")])
            self.assertTrue(mutation.effects)
            with self.assertRaises(StopError), abandon_new_on_stop(mutation):
                raise StopError("repository is in detached HEAD state", code="detached_head")
            self.assertEqual("pending", mutation.status)

    def test_a_failed_abandon_keeps_the_record_pending_and_reports_the_original_stop(self) -> None:
        from unittest import mock

        from workline.mutation import abandon_new_on_stop

        controller = MutationController(self.store)
        with project_operation(self.store, "u2e-f2-helper"):
            mutation = self.opened(controller)
            with mock.patch.object(type(mutation), "abandon", side_effect=OSError("disk")):
                with self.assertRaises(StopError) as raised, abandon_new_on_stop(mutation):
                    raise StopError("repository is in detached HEAD state", code="detached_head")
            self.assertEqual("detached_head", raised.exception.code)
            self.assertEqual("pending", mutation.status)

    def test_a_resumed_mutation_is_never_abandoned(self) -> None:
        from workline.mutation import abandon_new_on_stop

        controller = MutationController(self.store)
        with project_operation(self.store, "u2e-f2-helper"):
            first = self.opened(controller)  # left pending, as a process that ended would leave it
            resumed = self.opened(controller)
            self.assertTrue(resumed.resumed)
            self.assertEqual(first.id, resumed.id)
            with self.assertRaises(StopError), abandon_new_on_stop(resumed):
                raise StopError("repository is in detached HEAD state", code="detached_head")
            self.assertEqual("pending", resumed.status)
        self.assertEqual([first.id], [record["mutation_id"] for record in controller.list_pending()])

    def test_neither_a_non_stop_error_nor_success_closes_the_mutation(self) -> None:
        from workline.mutation import abandon_new_on_stop

        controller = MutationController(self.store)
        with project_operation(self.store, "u2e-f2-helper"):
            mutation = self.opened(controller)
            with self.assertRaises(Crash), abandon_new_on_stop(mutation):
                raise Crash("the process died")
            self.assertEqual("pending", mutation.status)
            with abandon_new_on_stop(mutation) as yielded:
                self.assertIs(mutation, yielded)
            self.assertEqual("pending", mutation.status)
