"""RB11 RT-1a: the probe's domain, the read-only proof, the replay rule and START's post-replay flow.

Rows (rev-11 TFI §A.2, §B.1): T-A22, T-B04, T-B05, T-B05a..T-B05g, T-B07, T-B07b,
T-B09, T-B09b, T-B09c, T-B45, T-B46, T-B48, T-B49, T-B50, T-B52. Every probe here
is asked through status (``pending_classification``) with the Project tree, ``.git``
included, compared byte for byte (``ProbeCase.probe``).
"""

from __future__ import annotations

import os
import shutil
import unittest
from unittest import mock

from helpers import completing_executor, git
import status_helpers
from start_probe_helpers import EVENT_LOG, Interrupted, ProbeCase, after_recording, before_finalizing
from status_helpers import ReadOnlyBoundary, add_roadmap_relation, append_events
from workline import gitcmd, recovery_disposition as rd, start as st, start_probe, status
from workline.errors import StopError
from workline.mutation import MutationController, WriteScope
from workline.oplock import project_operation
from workline.phase_integration import PHASE_INTEGRATION_REVIEW_V1
from workline.review import work_invocation
from workline.review.records import P4_WORK_CONTRACT

REASON = "status proves this record a dead end"


def open_record(store, owner: str, invocation: dict, entities=(), files=st.LEDGER_FILES) -> str:
    with project_operation(store, owner, {}):
        return MutationController(store).open(owner, invocation, WriteScope(entities=tuple(entities), files=tuple(files))).id


class DomainTests(ProbeCase):
    """S1.1 / S1.2 / S2.0: the probe's domain is checked by the probe itself (status selects by owner only)."""

    def assertNotProbed(self, invocation: dict, code: str, *, echoed: str | None = None) -> None:
        mutation_id = open_record(self.store, "start", invocation, (self.w1,))
        found = self.probe(mutation_id)
        self.assertEqual((found.classification, found.code), (start_probe.UNKNOWN_OR_INVALID, code), found)
        self.assertIn(found.step, ("S1.1", "S1.2"))
        if echoed is not None:
            self.assertNotIn(echoed, found.message, "no record value is echoed")
        with self.assertRaises(StopError) as refused:
            rd.dispose_recovery(self.store.root, mutation_id, REASON, confirmed=True)
        self.assertEqual(refused.exception.code, "recovery_disposition_target_ineligible")

    def test_t_b05e_start_plan_exclusion_records_get_the_fixed_reason_and_never_1552(self) -> None:
        """(i) a resumable plan exclusion and (ii) one stranded the T-28 way: both get the fixed reason, never 1552."""
        from workline.create import WorkSpec, create_standalone_work
        from workline.ops import Replan

        standalone = create_standalone_work(self.store, WorkSpec("S", "s")).work_id
        with before_finalizing(), self.assertRaises(Interrupted):
            st.plan_exclude_standalone_work(self.store, standalone, Replan())
        (record,) = [r for r in self.pending() if r["owner"] == "start"]
        found = self.probe(record["mutation_id"])
        self.assertEqual((found.classification, found.code),
                         (start_probe.UNKNOWN_OR_INVALID, start_probe.NOT_PROBED_PLAN_EXCLUSION), found)
        self.assertIsNone(found.check_id)
        with self.assertRaises(StopError) as refused:
            rd.dispose_recovery(self.store.root, record["mutation_id"], REASON, confirmed=True)
        self.assertEqual(refused.exception.code, "recovery_disposition_target_ineligible")

    def test_t_b05e_a_t28_stranded_plan_exclusion_record(self) -> None:
        self.assertNotProbed({"operation": "start-plan-exclude", "work_id": self.w1,
                              "request": {"version": 1, "bogus": True}}, start_probe.NOT_PROBED_PLAN_EXCLUSION)

    def test_t_b05f_a_work_review_generation_record(self) -> None:
        self.assertNotProbed({"operation": "review-generation", "review_run_id": "rr_x", "generation": 1,
                              "planning_mutation_id": "mut_x", "review_kind": "work-review-v1"},
                             start_probe.NOT_PROBED_GENERATION)

    def test_t_b05g_an_integration_generation_record(self) -> None:
        self.assertNotProbed({"operation": "review-generation", "review_run_id": "rr_y", "generation": 2,
                              "planning_mutation_id": "mut_y", "review_kind": "phase-integration-review-v1"},
                             start_probe.NOT_PROBED_GENERATION)

    def test_t_b05g_an_unknown_operation_keeps_todays_reason_and_is_not_echoed(self) -> None:
        self.assertNotProbed({"operation": "x-unknown-7f3", "work_id": self.w1}, start_probe.NO_PROBE, echoed="x-unknown-7f3")

    def test_t_b05_shapes_the_probe_cannot_positively_parse(self) -> None:
        for label, invocation in (
            ("a Work named by a number", {"operation": "start", "work_id": 7, "mode": "single-work"}),
            ("an extra key", {"operation": "start", "work_id": self.w1, "mode": "single-work", "extra": "x"}),
            ("a key missing", {"operation": "start", "work_id": self.w1}),
        ):
            with self.subTest(label):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    case.assertNotProbed(invocation, start_probe.NO_PROBE)
                finally:
                    case.doCleanups()

    def test_t_b05c_t_b05d_marker_shapes(self) -> None:
        """X-P (the P4 Work contract markers) and X-M (partial, unknown or extra markers): never probed."""
        live = {"operation": "start", "work_id": self.w1, "mode": "single-work"}
        for label, extra in (
            ("X-P: the P4 Work contract", work_invocation.markers(P4_WORK_CONTRACT)),
            ("X-M: one marker", {"review_contract": work_invocation.REVIEW_CONTRACT}),
            ("X-M: an unknown marker value", {"review_contract": "review-v9", "publication_contract": "x"}),
            ("X-M: an extra marker", {**work_invocation.markers(), "recovery_of_review_run_id": "rr_x"}),
        ):
            with self.subTest(label):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    case.assertNotProbed({**live, **extra}, start_probe.NO_PROBE)
                finally:
                    case.doCleanups()

    def test_t_b05b_x_i_a_phase_integration_semantics_note(self) -> None:
        self.question_wait_record()
        self.edit(lambda r: r["notes"].__setitem__("phase_integration_semantics", PHASE_INTEGRATION_REVIEW_V1))
        found = self.assertUnknown()
        self.assertEqual(found.step, "S1.2")
        with self.assertRaises(StopError) as refused:
            rd.dispose_recovery(self.store.root, self.the_record()["mutation_id"], REASON, confirmed=True)
        self.assertEqual(refused.exception.code, "recovery_disposition_target_ineligible")

    def test_t_b09_t_b09b_t_b09c_review_v1_records_stage_1b_dropped(self) -> None:
        """RT-1b is dropped with PO-05 evidence: every review-v1 START record stays unknown_or_invalid (no admission),
        with or without a reserved / begun Work Review Run or a Work-mode commit stage."""
        live = {"operation": "start", "work_id": self.w1, "mode": "single-work", **work_invocation.markers()}
        mutation_id = open_record(self.store, "start", live, (self.w1,))
        for label, change in (
            ("no Run, no Work-mode commit (stage 1b)", lambda r: None),
            ("a reserved Work Review Run (X-R)", lambda r: r["reserved_ids"].__setitem__(f"review-run:work-review-v1:{self.w1}", "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV")),
            ("an applied S-c0 Work-mode commit (stage 2)", lambda r: r["effects"].append(
                {"seq": 1, "stage": f"{self.w1}:s-c0:0", "kind": "git_commit", "applied": True,
                 "payload": {"mode": "review-v1-work-local-v2", "message": "x", "paths": ["x"]}})),
        ):
            with self.subTest(label):
                self.edit(change)
                found = self.probe(mutation_id)
                self.assertEqual((found.classification, found.code, found.step),
                                 (start_probe.UNKNOWN_OR_INVALID, start_probe.NO_PROBE, "S1.2"), found)
                with self.assertRaises(StopError) as refused:
                    rd.dispose_recovery(self.store.root, mutation_id, REASON, confirmed=True)
                self.assertEqual(refused.exception.code, "recovery_disposition_target_ineligible")

    def test_t_b52_a_mode_start_refuses_first_is_never_a_reconcile(self) -> None:
        """S2.0: mode not in MODES with an ALLOW defect (a cancel without its decision): START's first refusal is the
        ValidationError, so the probe's is too."""
        self.cancel_record()
        self.edit(lambda r: (self.event_effect(r, "work_cancelled")["payload"].pop("cancel"),
                             r["invocation"].__setitem__("mode", "sideways")))
        found = self.assertUnknown()
        self.assertEqual(found.step, "S2.0")
        refused = self.real_start()
        self.assertEqual((refused.code, refused.check_id), ("validation_failed", "start.3630"))


class ReadOnlyTests(ProbeCase):
    """T-A22 / T-B07 / T-B07b: identical bytes, no lock, no scratch, Git with its optional locks off."""

    def boundary(self):
        # git grep reads HEAD's committed tree only (START's _in_head_event_log); every other rule is the RB1 one
        return mock.patch.object(status_helpers, "READ_ONLY_GIT", status_helpers.READ_ONLY_GIT | {"grep"})

    def test_t_a22_status_with_a_start_record_writes_nothing_and_takes_no_lock(self) -> None:
        for builder in (self.question_wait_record, self.hold_record, self.cancel_record):
            with self.subTest(builder.__name__):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    builder_of_case = getattr(case, builder.__name__)
                    builder_of_case()
                    seen: list[str | None] = []
                    real_run = gitcmd.subprocess.run

                    def watching(*args, **kwargs):
                        seen.append(os.environ.get("GIT_OPTIONAL_LOCKS") if kwargs.get("env") is None
                                    else kwargs["env"].get("GIT_OPTIONAL_LOCKS"))
                        return real_run(*args, **kwargs)

                    record = case.the_record()
                    with case.boundary(), ReadOnlyBoundary(case.store.root) as boundary:
                        model = status.build_status(case.store.root)
                        with mock.patch.object(gitcmd.subprocess, "run", watching):
                            start_probe.inspect(case.store, record, case.pending())
                    self.assertEqual(boundary.violations, [])
                    self.assertEqual(boundary.paths_written, [])
                    self.assertEqual(boundary.changed(), {})
                    self.assertTrue(seen)
                    self.assertEqual(set(seen), {"0"}, "every Git command of the probe runs with its optional locks off")
                    (entry,) = model.get("pending")["records"]
                    self.assertIn(entry["classification"], status.RESUME_CLASSIFICATIONS)
                    self.assertFalse(case.store.lock_holder.exists())
                finally:
                    case.doCleanups()

    def test_t_b07b_status_with_the_review_runtime_area_absent_creates_nothing(self) -> None:
        self.question_wait_record()
        review_runtime = self.store.root / ".workline" / "runtime" / "review"
        if review_runtime.exists():
            shutil.rmtree(review_runtime)
        self.assertResumable()
        self.assertFalse(review_runtime.exists())


class ResumableTests(ProbeCase):
    """T-B04 / T-B05a / T-B46: pending_resumable proven positively, each gate of run_work evaluated read-only."""

    def test_t_b04_t_b05a_a_question_wait_record_every_step_passing(self) -> None:
        record = self.question_wait_record()
        found = self.assertResumable()
        self.assertEqual(found.step, "S8")
        with self.assertRaises(StopError) as refused:
            rd.dispose_recovery(self.store.root, record["mutation_id"], REASON, confirmed=True)
        self.assertEqual(refused.exception.code, "recovery_disposition_target_ineligible")
        asked: list[str] = []
        result = st.start(self.store, self.w1, "single-work", lambda ctx: asked.append(ctx.work.id) or st.QuestionWait("again"))
        self.assertEqual((asked, result.mutation_id), ([self.w1], record["mutation_id"]), "START resumes it and asks again")

    def test_t_b46_a_failing_run_work_gate_after_a_clear_replay(self) -> None:
        cases = {
            "dependency_unsatisfied": lambda case: add_roadmap_relation(case.store, "requires_completion", case.w2, case.w1),
            "phase_inactive": lambda case: append_events(case.store, ("phase_held", case.pa)),
        }
        for label, change in cases.items():
            with self.subTest(label):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    case.question_wait_record()
                    change(case)
                    found = case.assertUnknown()
                    refused = case.real_start()
                    self.assertIsInstance(refused, StopError, refused)
                    self.assertEqual((found.step, refused.code), ("S7.2", label), found)
                finally:
                    case.doCleanups()

    def test_t_b46_a_dirty_event_log_before_the_first_effect(self) -> None:
        mutation_id = open_record(self.store, "start", {"operation": "start", "work_id": self.w1, "mode": "single-work"}, (self.w1,))
        # a change to the event log from before this START: a blank line the person added and did not commit
        (self.store.root / EVENT_LOG).write_text((self.store.root / EVENT_LOG).read_text(encoding="utf-8") + "\n",
                                                 encoding="utf-8", newline="")
        found = self.probe(mutation_id)
        self.assertEqual((found.classification, found.step), (start_probe.UNKNOWN_OR_INVALID, "S7.2"), found)
        with self.assertRaises(StopError) as refused:
            st.start(self.store, self.w1, "single-work", completing_executor(self.store))
        self.assertEqual(refused.exception.code, "dirty_overlap")


class ReplayTests(ProbeCase):
    """T-B48: a replay that would write is never followed; neither 900 nor a post-replay gate is evaluated."""

    def test_t_b48_an_unapplied_completion_with_its_finalize_commit(self) -> None:
        def done(ctx):
            (self.store.root / "result_w1.txt").write_text("w1\n", encoding="utf-8")
            return st.Completed(("result_w1.txt",))

        self.interrupt(after_recording(rf"^{self.w1}:finalize:\d+$"),
                       lambda: st.start(self.store, self.w1, "single-work", done))
        self.edit(lambda r: r["notes"].__setitem__("refused_result", {"version": 9}))  # 900 if it were evaluated
        found = self.assertUnknown(code=start_probe.POST_REPLAY_NOT_READ_ONLY)
        self.assertEqual(found.step, "S6.2")

    def test_t_b48_an_effect_flagged_applied_that_classifies_unapplied(self) -> None:
        self.question_wait_record()
        git(self.store.root, "checkout", "--", EVENT_LOG)  # the lifecycle events the record holds as applied are gone
        found = self.assertUnknown(code=start_probe.POST_REPLAY_NOT_READ_ONLY)
        self.assertEqual(found.step, "S6.2")


class PushTests(ProbeCase):
    def setUp(self) -> None:
        super(ProbeCase, self).setUp()
        self.store = self.new_project(remote=True)
        roadmap = self.simple_roadmap(self.store)
        self.rid, self.pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        self.entry = self.simple_entry(self.store, self.pa, {"w1": "W1", "w2": "W2"})
        self.w1, self.w2 = self.entry.work_ids["w1"], self.entry.work_ids["w2"]
        self.i1 = self.entry.integration_id

    def test_t_b45_a_record_holding_a_push_is_never_classified_offline(self) -> None:
        self.hold_record(committed=True)
        found = self.assertUnknown(code="push_classification_requires_network")
        self.assertEqual(found.step, "S6.1")

    def test_t_b49_iv_the_publication_barrier_is_excluded_from_the_claim(self) -> None:
        """T-B49 (iv): with the barrier not clear the hold finish path is still pending_resumable - the probe never
        asks the barrier, which is a publication precondition (ADM §A.1 S7.1 (i)); START itself does stop there."""
        from workline.review import publication

        self.hold_record()
        problem = mock.patch.object(publication, "barrier_problem", return_value="a registration commit is not proven")
        with problem as asked:
            found = self.assertResumable()
            self.assertEqual(asked.call_count, 0, "the probe never asks the publication barrier")
            with self.assertRaises(StopError) as refused:
                st.start(self.store, self.w1, "single-work", completing_executor(self.store))
        self.assertEqual(refused.exception.code, "review_publication_barrier")
        self.assertEqual(found.step, "S7.1")


class FinishPathTests(ProbeCase):
    """T-B49: each finish path's local refusals, read only."""

    def test_i_finish_completion_with_the_work_gone_is_unknown(self) -> None:
        self.completion_record()
        self.edit(lambda r: r["invocation"].update(work_id=self.w2, mode="outer"))
        (self.store.root / ".workline" / "works" / f"{self.w1}.md").unlink()
        self.assertUnknown()
        refused = self.real_start()
        self.assertIsInstance(refused, StopError, refused)

    def test_ii_finish_hold_whose_commit_overlaps_preexisting_changes(self) -> None:
        self.hold_record()
        self.edit(lambda r: r["notes"].__setitem__("preexisting_dirty", [EVENT_LOG]))
        found = self.assertUnknown()
        self.assertEqual(found.step, "S7.1")
        refused = self.real_start()
        self.assertEqual(refused.code, "dirty_overlap")

    def test_iii_finish_hold_with_nothing_overlapping(self) -> None:
        self.hold_record()
        found = self.assertResumable()
        self.assertEqual(found.step, "S7.1")
        result = st.start(self.store, self.w1, "single-work", completing_executor(self.store))
        self.assertEqual(result.status, "held")

    def test_finish_completion_and_finish_move_with_nothing_overlapping(self) -> None:
        self.completion_record()
        self.assertEqual(self.assertResumable().step, "S7.1")
        self.assertEqual(st.start(self.store, self.w1, "single-work", completing_executor(self.store)).status,
                         "completed")

    def test_finish_move(self) -> None:
        self.interrupt(before_finalizing(), lambda: st.start(self.store, self.w1, "single-work",
                                                             lambda ctx: self.derive("f0", move=True)))
        self.assertEqual(self.assertResumable().step, "S7.1")
        self.assertEqual(st.start(self.store, self.w1, "single-work", completing_executor(self.store)).status, "moved")

    def test_v_a_stage_1b_record_is_unknown(self) -> None:
        live = {"operation": "start", "work_id": self.w1, "mode": "single-work", **work_invocation.markers()}
        mutation_id = open_record(self.store, "start", live, (self.w1,))
        self.assertEqual(self.probe(mutation_id).classification, start_probe.UNKNOWN_OR_INVALID)


class PendingSetTests(ProbeCase):
    """T-B50: the named Work, the disposition barrier, and N4's own record left out (``excluding``)."""

    def test_i_the_named_work_does_not_resolve(self) -> None:
        mutation_id = open_record(self.store, "start", {"operation": "start", "work_id": "w_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                                                        "mode": "single-work"}, ("w_01ARZ3NDEKTSV4RRFFQ69G5FAV",))
        found = self.probe(mutation_id)
        self.assertEqual((found.classification, found.step), (start_probe.UNKNOWN_OR_INVALID, "S3.1"))

    def test_ii_another_recovery_disposition_is_pending(self) -> None:
        self.question_wait_record()
        self.assertResumable()
        record = self.the_record()
        disposition = dict(record, mutation_id="mut_01ARZ3NDEKTSV4RRFFQ69G5FAW", owner="recovery-disposition",
                           invocation={"operation": "recovery-disposition", "target_id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"},
                           write_scope={"entities": [], "files": [".workline/recovery/dispositions/x.yaml"]},
                           effects=[], notes={}, reserved_ids={})
        self.write_record(disposition)
        found = self.probe(record["mutation_id"])
        self.assertEqual((found.classification, found.step), (start_probe.UNKNOWN_OR_INVALID, "S4.1"), found)

    def test_iii_n4_resuming_its_own_disposition_of_an_allow_dead_end(self) -> None:
        self.cancel_record()
        target = self.edit(lambda r: self.event_effect(r, "work_cancelled")["payload"].pop("cancel"))["mutation_id"]
        self.assertReconcileAt("start.2282")
        # N4 stopped right after it opened its own record, before it decided anything
        from workline import gitops

        with mock.patch.object(gitops, "record_preexisting_dirty", side_effect=Interrupted("after the disposition opened")):
            with self.assertRaises(Interrupted):
                rd.dispose_recovery(self.store.root, target, REASON, confirmed=True)
        (own,) = [r for r in self.pending() if r["owner"] == rd.OWNER]
        # START refuses this record at its cancel (S3.4) before it would ever meet the disposition barrier (S4.1),
        # so the dead end shows with N4's own record in the set; with it left out, as N4 asks (excluding), too
        classification, _ = status.pending_classification(self.store, target, excluding=(own["mutation_id"],))
        self.assertEqual(classification, status.PENDING_RECONCILE, "N4's own record is left out of the set")
        result = rd.dispose_recovery(self.store.root, target, REASON, confirmed=True)
        self.assertEqual((result.status, result.resumed), ("disposed", True))
        self.assertEqual(status.pending_classification(self.store, target)[0], status.DISPOSED_BY_HUMAN)


if __name__ == "__main__":
    unittest.main()
