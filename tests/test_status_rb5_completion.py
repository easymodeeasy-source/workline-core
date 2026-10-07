"""RB5 I-9 on the landed RB7 status (written by the shared-surface writer): the completion slot and the next-Phase
narrowing (§32.41 / §32.42 / §32.51, RB8-FC-08).

* ``completion`` reads the Project alone: per Phase its mode, generated completeness, basis, coverage, the latest
  Phase Integration Review of its marked integration, its current evidence and progression-readiness; per Roadmap
  its completeness, readiness and the ``roadmap_achieved`` binding;
* the next Phase is narrowed exactly as ``roadmap.select_phase`` narrows it: a candidate whose reviewed predecessor
  holds no valid current-basis evidence is held back (``phase_evidence_not_ready``), and status and Roadmap agree;
* status stays read-only, and RB7's ``policy.root_maintenance`` model and human line are untouched.
"""

from __future__ import annotations

from pathlib import Path

from rb5_run_helpers import IntegrationRunCase
from status_helpers import ReadOnlyBoundary
from workline import roadmap as rm
from workline import status
from workline.review import paths
from workline.review.store import ReviewStore


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
