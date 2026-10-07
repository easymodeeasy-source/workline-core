"""RB5 I-9 on the landed RB7 status (written by the shared-surface writer): the completion slot and the next-Phase
narrowing (§32.41 / §32.42 / §32.51, RB8-FC-08).

* ``completion`` reads the Project alone: per Phase its mode, generated completeness, basis, coverage, the latest
  Phase Integration Review of its marked integration, its current evidence and progression-readiness; per Roadmap
  its completeness, readiness and the ``roadmap_achieved`` binding;
* the next Phase is narrowed exactly as ``roadmap.select_phase`` narrows it: a candidate whose reviewed predecessor
  holds no valid current-basis evidence is held back (``phase_evidence_not_ready``), and status and Roadmap agree;
* each Roadmap entry's ``human_objective`` (I-9b, §32.51 / §14.28) reports Human-required / objective-unmet status
  only where canonical input supports it: the latest Integration Review Run's stored Phase outcome, the Roadmap's
  unresolved G4 HUMAN_WAIT Runs and its open downstream confirmations - never an invented Roadmap judgement;
* status stays read-only, and RB7's ``policy.root_maintenance`` model and human line are untouched.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from helpers import completing_executor
from rb5_run_helpers import Adjudicator, Discovery, IntegrationRunCase, answering_executor, claim, phase_review
from status_helpers import ReadOnlyBoundary
from workline import phase_integration as pi
from workline import roadmap as rm
from workline import roadmap_review as rr
from workline import start as st
from workline import start_review as sr
from workline import status
from workline.errors import StopError
from workline.review import integration as ri
from workline.review import p4, paths
from workline.review.store import ReviewStore
from workline.state import ProjectView


class CompletionSlotTests(IntegrationRunCase):
    def data(self, root: Path) -> dict:
        return status.build_status(root).data

    def reviewed(self):
        store, phase_a, ids = self.marked_project(next_phase=True)
        self.assertEqual("completed", self.integrate(store, ids["integration"]).status)
        roadmap_id = self.roadmap_of(store, phase_a)
        return store, phase_a, ids, roadmap_id

    def test_a_reviewed_phase_with_its_evidence_is_ready_and_its_successor_is_next(self) -> None:
        store, phase_a, ids, roadmap_id = self.reviewed()
        (run_id,) = self.integration_runs(store, ids["integration"])
        (evidence,) = ReviewStore(store).phase_completion_evidence()
        with ReadOnlyBoundary(store.root) as boundary:
            data = self.data(store.root)
        self.assertEqual([], boundary.violations)
        self.assertEqual([], boundary.paths_written)
        self.assertEqual({}, boundary.changed(), "status changed bytes under the Project (RB5PR1B-5)")
        completion = data["completion"]
        self.assertEqual("available", completion["status"])
        phase = {item["phase_id"]: item for item in completion["phases"]}[phase_a]
        self.assertEqual(("phase-integration-review-v1", True, True, ids["integration"]),
                         (phase["completion_mode"], phase["generated_complete"], phase["progression_ready"],
                          phase["covering_integration_id"]))
        self.assertEqual({"status": "ready", "achievement_evidence_id": evidence.achievement_evidence_id},
                         phase["evidence"])
        self.assertEqual({"review_run_id": run_id, "disposition": "consumed"}, phase["latest_integration_review"])
        self.assertEqual("covered", phase["coverage"]["status"])
        (roadmap,) = completion["roadmaps"]
        self.assertEqual((roadmap_id, True, []), (roadmap["roadmap_id"], roadmap["every_reviewed_phase_progression_ready"],
                                                  roadmap["unready_phases"]))
        next_phase = data["lifecycle"]["next"]["phase"]
        selected = rm.select_phase(store, roadmap_id)
        self.assertEqual(selected.id if selected is not None else None, next_phase["id"])
        self.assertNotIn("phase_evidence_not_ready", [item["code"] for item in data["lifecycle"]["blockers"]])
        human = status.render_human(status.build_status(store.root))
        self.assertIn(f"phase-integration-review-v1 complete=True evidence=ready ready=True", human)
        achievement = human[human.index("\nAchievement\n"):human.index("\nPolicy\n")]
        self.assertTrue(achievement.startswith("\nAchievement\n  available\n"))
        self.assertIn("root maintenance:", human[human.index("\nPolicy\n"):], "RB7's line stays under Policy")
        self.assertIn("root_maintenance", data["policy"])

    def test_without_valid_evidence_the_successor_is_held_back_by_status_and_roadmap_alike(self) -> None:
        store, phase_a, ids, roadmap_id = self.reviewed()
        for record in (store.root / paths.HISTORY_DIR / paths.HISTORY_ACHIEVEMENTS).glob("*.yaml"):
            record.unlink()  # the evidence obligation is open again (a working-tree loss, for the row only)
        data = self.data(store.root)
        phase = {item["phase_id"]: item for item in data["completion"]["phases"]}[phase_a]
        self.assertEqual(({"status": "missing", "achievement_evidence_id": None}, False),
                         (phase["evidence"], phase["progression_ready"]))
        (roadmap,) = data["completion"]["roadmaps"]
        self.assertEqual([{"phase_id": phase_a, "evidence_status": "missing"}], roadmap["unready_phases"])
        self.assertFalse(roadmap["every_reviewed_phase_progression_ready"])
        lifecycle = data["lifecycle"]
        blocked = [item for item in lifecycle["blockers"] if item["code"] == "phase_evidence_not_ready"]
        self.assertEqual(1, len(blocked))
        self.assertEqual([phase_a], blocked[0]["ids"])
        self.assertIsNone(lifecycle["next"]["phase"]["id"])
        self.assertEqual("phase_evidence_not_ready", lifecycle["next"]["phase"]["reason"])
        self.assertIsNone(rm.select_phase(store, roadmap_id), "Roadmap holds the same Phase back")

    def test_an_unreadable_achievement_record_withholds_only_the_next_phase(self) -> None:
        """RB5PR1B-1: a Review-history read failure never blanks the lifecycle section - the inventory and every
        other blocker stay, one blocker names the failure, and only the next-Phase selection is withheld."""
        store, phase_a, ids, roadmap_id = self.reviewed()
        other = self.simple_roadmap(store, {"z": ("Phase Z", "Z が成立する")})
        self.assertEqual("roadmap_held", rm.hold_roadmap(store, other.roadmap_id).status)
        (record,) = (store.root / paths.HISTORY_DIR / paths.HISTORY_ACHIEVEMENTS).glob("*.yaml")
        record.write_bytes(b"schema: not-an-achievement\n")
        data = self.data(store.root)
        lifecycle = data["lifecycle"]
        self.assertEqual("available", lifecycle["status"])
        self.assertIn(phase_a, [item["id"] for item in lifecycle["phases"]])
        self.assertTrue(lifecycle["works"] or lifecycle["roadmaps"])
        codes = [item["code"] for item in lifecycle["blockers"]]
        self.assertIn("roadmap_held", codes, "every other blocker stays")
        failures = [item for item in lifecycle["blockers"] if item["code"].startswith("review_record_")]
        self.assertEqual(1, len(failures))
        self.assertEqual([], failures[0]["ids"])
        next_phase = lifecycle["next"]["phase"]
        self.assertEqual((None, failures[0]["code"], None), (next_phase["id"], next_phase["reason"], next_phase["basis"]))
        self.assertTrue(next_phase["candidates"], "the observed candidate set is kept")
        self.assertEqual("unavailable", data["completion"]["status"], "the completion section's own failure is correct")
        self.assertEqual("available", data["lifecycle"]["status"])

    def test_a_stale_reviewed_phase_never_points_at_the_achievement_check(self) -> None:
        """RB5PR1B-2: status filters complete reviewed Phases exactly as ``roadmap.unready_reviewed_phases`` does
        (lifecycle ``COMPLETE``). In this composition the generated-state reader already applies the reviewed
        predicate (``ProjectView.phase_completion`` -> ``phase_integration.completion_reasons``), so a reviewed Phase
        whose coverage went stale is not lifecycle-complete at all: status and Roadmap agree, and neither says
        all_active_phases_complete / "run the achievement check"."""
        from helpers import completing_executor
        from workline import phase_integration as pi
        from workline import start as st
        from workline.state import COMPLETE, ProjectView

        store, phase_a, ids = self.marked_project("stale", confirmation=True)
        self.assertEqual("completed", self.integrate(store, ids["integration"]).status)
        late = self.add_late_work(store, phase_a)  # added while the confirmation keeps the Phase open
        for work in (ids["confirmation"], late):
            self.assertEqual("completed", st.start(store, work, "single-work", completing_executor(store)).status)
        roadmap_id = self.roadmap_of(store, phase_a)
        view = ProjectView.load(store)
        self.assertEqual(pi.COVERAGE_STALE, pi.coverage_status(view, phase_a).status)
        self.assertEqual(pi.phase_generated_complete(view, phase_a), view.phase_state(phase_a) == COMPLETE,
                         "the two completion predicates agree in this composition")
        self.assertFalse(view.all_active_phases_complete(roadmap_id))
        self.assertEqual([], rm.unready_reviewed_phases(store, view, roadmap_id))
        data = self.data(store.root)
        phase = {item["phase_id"]: item for item in data["completion"]["phases"]}[phase_a]
        self.assertEqual(("stale", False, False), (phase["coverage"]["status"], phase["generated_complete"],
                                                   phase["progression_ready"]))
        self.assertNotEqual("all_active_phases_complete", data["lifecycle"]["next"]["phase"]["reason"])
        self.assertNotIn("achievement check", rm.diagnose_no_candidate(store, roadmap_id))

    def test_a_legacy_only_project_reads_nothing_new(self) -> None:
        store = self.new_project("legacy")
        roadmap = self.simple_roadmap(store, {"a": ("A", "A holds"), "b": ("B", "B holds")},
                                      (("requires_completion", "a", "b"),))
        data = self.data(store.root)
        self.assertEqual({"legacy"}, {item["completion_mode"] for item in data["completion"]["phases"]})
        self.assertEqual({"not_applicable"}, {item["evidence"]["status"] for item in data["completion"]["phases"]})
        self.assertNotIn("phase_evidence_not_ready", [item["code"] for item in data["lifecycle"]["blockers"]])
        selected = rm.select_phase(store, roadmap.roadmap_id)
        self.assertEqual(selected.id if selected is not None else None, data["lifecycle"]["next"]["phase"]["id"])


class ObligationAdjudicator(Adjudicator):
    """The scripted adjudicator whose ``not_satisfied`` outcome also names one explicit unmet objective obligation."""

    def __call__(self, task: Any) -> Any:
        found = super().__call__(task)
        return dataclasses.replace(found, phase_outcome=dataclasses.replace(
            found.phase_outcome, unmet_objective_obligations=("every-work-covered",)))


class HumanObjectiveTests(IntegrationRunCase):
    """I-9b: ``completion.roadmaps[].human_objective`` and its one human line, each read inside the read-only
    boundary."""

    NOT_APPLICABLE = {"status": "not_applicable", "human_required": [], "objective_unmet": []}
    NONE = {"status": "none", "human_required": [], "objective_unmet": []}

    def observe(self, store) -> tuple[dict, str]:
        with ReadOnlyBoundary(store.root) as boundary:
            data = status.build_status(store.root).data
            human = status.render_human(status.build_status(store.root))
        self.assertEqual([], boundary.violations)
        self.assertEqual([], boundary.paths_written)
        self.assertEqual({}, boundary.changed(), "status changed bytes under the Project")
        self.assertEqual("available", data["completion"]["status"])
        return data, human[human.index("\nAchievement\n"):human.index("\nPolicy\n") + 1]

    def roadmap_entry(self, data: dict, roadmap_id: str) -> dict:
        return {item["roadmap_id"]: item for item in data["completion"]["roadmaps"]}[roadmap_id]

    def assert_no_line(self, achievement: str, roadmap_id: str) -> None:
        self.assertNotIn(f"  {roadmap_id} human=", achievement)

    def test_a_legacy_only_roadmap_reads_nothing_new(self) -> None:
        store = self.new_project("legacy")
        roadmap = self.simple_roadmap(store, {"a": ("A", "A holds")})
        data, achievement = self.observe(store)
        self.assertEqual(self.NOT_APPLICABLE, self.roadmap_entry(data, roadmap.roadmap_id)["human_objective"])
        self.assert_no_line(achievement, roadmap.roadmap_id)

    def test_an_objectively_satisfied_reviewed_phase_requires_nothing(self) -> None:
        store, phase_a, ids = self.marked_project("satisfied")
        self.assertEqual("completed", self.integrate(store, ids["integration"]).status)
        roadmap_id = self.roadmap_of(store, phase_a)
        (run_id,) = self.integration_runs(store, ids["integration"])
        review = ReviewStore(store)
        self.assertEqual(ri.OBJECTIVELY_SATISFIED,
                         p4.bound_adjudication(review, review.gate_chain(run_id)).phase_outcome["outcome"])
        data, achievement = self.observe(store)
        self.assertEqual(self.NONE, self.roadmap_entry(data, roadmap_id)["human_objective"])
        self.assert_no_line(achievement, roadmap_id)

    def test_a_human_wait_run_is_one_unresolved_human_decision(self) -> None:
        store, phase_a, ids = self.marked_project("human-wait")
        selector = phase_review(Discovery(claim("human")), adjudicator=Adjudicator())
        with self.assertRaises(StopError) as raised:
            self.integrate(store, ids["integration"], selector, executor=answering_executor(st.Completed()))
        self.assertEqual(p4.CODE_HUMAN_WAIT, raised.exception.code)
        roadmap_id = self.roadmap_of(store, phase_a)
        (run_id,) = self.integration_runs(store, ids["integration"])
        data, achievement = self.observe(store)
        found = self.roadmap_entry(data, roadmap_id)["human_objective"]
        self.assertEqual("human_required", found["status"])
        self.assertEqual([{"kind": "review_human_wait", "id": run_id, "target_id": ids["integration"]}],
                         [item for item in found["human_required"] if item["kind"] == "review_human_wait"])
        self.assertEqual([{"kind": "phase_outcome", "id": run_id, "phase_id": phase_a,
                           "outcome": ri.DESIRED_STATE_CHANGE_REQUIRED}],
                         [item for item in found["human_required"] if item["kind"] != "review_human_wait"],
                         "the same Run's stored Phase outcome asks for a desired-state change")
        self.assertEqual([], found["objective_unmet"])
        # the same Run is the §32.44 reader's unresolved HUMAN decision (one owner, its prose unchanged)
        _, unresolved = rr.achievement_open_items(store, ProjectView.load(store), roadmap_id, None)
        self.assertEqual(1, len(unresolved))
        self.assertIn(run_id, unresolved[0])
        self.assertIn(f"\n  {roadmap_id} human=2 objective_unmet=-\n", achievement)

    def test_an_open_confirmation_is_required_until_it_completes(self) -> None:
        store, phase_a, ids = self.marked_project("confirm")
        selector = phase_review(Discovery(), adjudicator=Adjudicator(ri.HUMAN_CONFIRMATION_REQUIRED))
        self.assertEqual("completed", self.integrate(store, ids["integration"], selector).status)
        roadmap_id = self.roadmap_of(store, phase_a)
        view = ProjectView.load(store)
        (confirmation,) = [w.id for w in view.effective_works(phase_a) if w.work_kind == pi.CONFIRMATION_KIND]
        review = ReviewStore(store)
        (run_id,) = [found for found in self.integration_runs(store, ids["integration"])
                     if review.gate_chain(found).latest.sealed]
        state = view.work_state(confirmation).state
        self.assertNotEqual("completed", state)
        data, achievement = self.observe(store)
        self.assertEqual({"status": "human_required", "objective_unmet": [], "human_required": [
            {"kind": "confirmation", "id": confirmation, "phase_id": phase_a, "state": state},
            {"kind": "phase_outcome", "id": run_id, "phase_id": phase_a, "outcome": ri.HUMAN_CONFIRMATION_REQUIRED},
        ]}, self.roadmap_entry(data, roadmap_id)["human_objective"])
        self.assertIn(f"\n  {roadmap_id} human=2 objective_unmet=-\n", achievement)
        self.assertEqual("completed", st.start(store, confirmation, "single-work", completing_executor(store)).status)
        data, achievement = self.observe(store)
        self.assertEqual(self.NONE, self.roadmap_entry(data, roadmap_id)["human_objective"],
                         "a confirmed, closed Phase's human_confirmation_required outcome is history")
        self.assert_no_line(achievement, roadmap_id)

    def test_a_not_satisfied_outcome_lists_its_unmet_objective_obligation(self) -> None:
        store, phase_a, ids = self.marked_project("not-satisfied")
        selector = phase_review(Discovery(claim("problem")), adjudicator=ObligationAdjudicator())
        with self.assertRaises(StopError) as raised:
            self.integrate(store, ids["integration"], selector, executor=answering_executor(st.Completed()))
        self.assertEqual(sr.CODE_INTEGRATION_REPAIR_PLAN_INVALID, raised.exception.code)
        roadmap_id = self.roadmap_of(store, phase_a)
        (run_id,) = self.integration_runs(store, ids["integration"])
        self.assertEqual(ri.BRANCH_DOMAIN_REPAIR_REQUIRED,
                         ReviewStore(store).read_adjudication(run_id).integration_disposition)
        data, achievement = self.observe(store)
        self.assertEqual({"status": "objective_unmet", "human_required": [], "objective_unmet": [
            {"phase_id": phase_a, "review_run_id": run_id, "unmet_objective_obligations": ["every-work-covered"]},
        ]}, self.roadmap_entry(data, roadmap_id)["human_objective"])
        self.assertIn(f"\n  {roadmap_id} human=0 objective_unmet={phase_a}\n", achievement)
