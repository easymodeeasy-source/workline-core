"""RB1 §29.32: one StatusModel, two renderings - deterministic JSON and a recovery-first human text.

Neither rendering reads anything; the JSON carries schema and version, stable
IDs apart from display text, explicit unknowns, and nothing about the caller;
and a later Review Block that adds fields leaves every base field as it was.
"""

from __future__ import annotations

import builtins
import copy
import json
import os
from pathlib import Path
import unittest
from unittest import mock

from helpers import cwd
from status_helpers import StatusCase, append_events
from workline import status

LIFECYCLE_REASONS = {
    None, "no_active_roadmap", "multiple_active_roadmaps", "no_unique_roadmap", "no_started_phase",
    "multiple_started_phases", "no_unique_phase", "no_work_in_flight", "multiple_targets",
    "ambiguous_startable_candidates", "no_startable_phase", "all_active_phases_complete", "no_startable_work",
    "pending_mutation_unresolved", "structure_invalid", "project_changed_during_status",
    # RB5 (§32.41 / §32.42, I-9): a next Phase held back by a reviewed predecessor's open evidence obligation - pin
    # widened additively (disclosed)
    "phase_evidence_not_ready",
}
TOP_LEVEL = {"schema", "version", "snapshot_consistency", "snapshot_reason", "project", "authority", "git", "lifecycle",
             "pending", "validation", "review", "completion", "policy"}


def keys_anywhere(value, found=None) -> set[str]:
    found = set() if found is None else found
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            keys_anywhere(item, found)
    elif isinstance(value, list):
        for item in value:
            keys_anywhere(item, found)
    return found


class RenderTests(StatusCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        roadmap = self.simple_roadmap(self.store)
        self.works = self.simple_entry(self.store, roadmap.phase_ids["a"]).work_ids
        append_events(self.store, ("work_started", self.works["w1"]), ("work_target_added", self.works["w1"]))

    def test_schema_and_version_are_exact_and_every_section_is_present(self) -> None:
        data = self.data()
        self.assertEqual((data["schema"], data["version"]), ("workline-status", 1))
        self.assertEqual(set(data), TOP_LEVEL)
        # RB5 (§32.51 / §14.28, I-9): an established Project's completion slot is available - pin updated deliberately
        # (was {"status": "not_available_by_contract"}, which a non-established folder still reports)
        self.assertEqual({"status", "phases", "roadmaps"}, set(data["completion"]))
        self.assertEqual("available", data["completion"]["status"])
        (phase,) = data["completion"]["phases"]
        self.assertEqual(("legacy", {"status": "not_applicable", "achievement_evidence_id": None}, None),
                         (phase["completion_mode"], phase["evidence"], phase["latest_integration_review"]))
        self.assertEqual({"phase_id", "roadmap_id", "completion_mode", "generated_complete", "basis_digest",
                          "covering_integration_id", "coverage", "latest_integration_review", "evidence",
                          "progression_ready", "downstream_confirmations"}, set(phase))
        (roadmap,) = data["completion"]["roadmaps"]
        # I-9b (§32.51 / §14.28): human_objective joins each Roadmap entry additively - pin updated deliberately (was
        # the five keys without human_objective); a legacy-only Roadmap reads nothing new
        self.assertEqual({"roadmap_id", "all_active_phases_generated_complete", "every_reviewed_phase_progression_ready",
                          "unready_phases", "achieved", "human_objective"}, set(roadmap))
        self.assertEqual({"event_id": None, "evidence_id": None, "binding": "ok"}, roadmap["achieved"])
        self.assertEqual({"status": "not_applicable", "human_required": [], "objective_unmet": []},
                         roadmap["human_objective"])
        # RB6 (§30.30, RB6A-IR-2): the RB1 policy placeholder is filled additively - pin updated deliberately
        self.assertEqual("available", data["policy"]["status"])
        # RB7 (§31.46, RB7C-4, IR-RB7-5): the root maintenance diagnostics join additively, isolated - pin updated
        # deliberately (was the seven keys without root_maintenance)
        self.assertEqual({"status", "global_baseline", "profile", "effective_policy", "experiments", "maintenance",
                          "shadow_authority", "root_maintenance"}, set(data["policy"]))
        self.assertIn(data["policy"]["root_maintenance"]["status"], ("available", "unavailable"))
        self.assertEqual({"status": "absent"}, data["policy"]["profile"])
        self.assertEqual({"status": "none", "problems": []}, data["policy"]["maintenance"])

    def test_json_bytes_are_deterministic(self) -> None:
        first = status.render_json(self.model())
        second = status.render_json(self.model())
        self.assertEqual(first, second)
        self.assertTrue(first.isascii())
        self.assertTrue(first.endswith("}\n"))
        self.assertEqual(first, json.dumps(json.loads(first), ensure_ascii=True, sort_keys=True, indent=2) + "\n")

    def test_stable_ids_and_enums_need_no_prose(self) -> None:
        data = self.data()
        life = data["lifecycle"]
        self.assertEqual(life["current"]["work"]["id"], self.works["w1"])
        self.assertEqual(life["current"]["roadmap"]["id"], life["roadmaps"][0]["id"])
        display = {entity["id"]: entity["display"] for entity in life["works"]}
        self.assertTrue(display[self.works["w1"]].startswith("W-"), "display text is a separate field")
        for group in ("current", "next"):
            for name, selected in life[group].items():
                with self.subTest(f"{group}.{name}"):
                    self.assertIn(selected["reason"], LIFECYCLE_REASONS)
        self.assertIn(data["snapshot_consistency"], ("stable_read", "changing"))
        self.assertIn(data["validation"]["status"], ("pass", "failed", "unavailable"))
        self.assertIn(data["pending"]["status"], ("none", "present", "unavailable"))
        self.assertIn(data["review"]["activation"]["status"], ("absent", "present", "invalid"))

    def test_the_target_cwd_and_an_external_cwd_give_the_same_bytes(self) -> None:
        outside = self.new_dir("outside")
        with cwd(self.store.root):
            inside = status.render_json(status.build_status("."))
        with cwd(outside):
            external = status.render_json(status.build_status(self.store.root))
        self.assertEqual(inside, external)

    def test_no_caller_cwd_time_pid_or_host_field(self) -> None:
        outside = self.new_dir("caller-place")
        with cwd(outside):
            text = status.render_json(status.build_status(self.store.root))
        self.assertNotIn(str(outside), text)
        self.assertNotIn(outside.name, text)
        keys = keys_anywhere(json.loads(text))
        for forbidden in ("cwd", "pid", "host", "hostname", "time", "timestamp", "at", "created_at", "updated_at",
                          "acquired_at", "generated_at"):
            with self.subTest(key=forbidden):
                self.assertNotIn(forbidden, keys)

    def test_the_human_rendering_reads_nothing(self) -> None:
        model = self.model()

        def refuse(*_args, **_kwargs):
            raise AssertionError("a renderer read something")

        with mock.patch.object(builtins, "open", refuse), mock.patch.object(os, "stat", refuse), \
                mock.patch.object(os, "lstat", refuse), mock.patch.object(Path, "read_bytes", refuse), \
                mock.patch.object(Path, "read_text", refuse), mock.patch("subprocess.Popen", refuse):
            text = status.render_human(model)
            json_text = status.render_json(model)
        self.assertTrue(text.startswith("Workline status (workline-status v1) - snapshot: stable_read"))
        self.assertEqual(json.loads(json_text), json.loads(json.dumps(model.data)))
        positions = [text.index("\n" + name + "\n") for name in status.HUMAN_SECTIONS]
        self.assertEqual(positions, sorted(positions), "sections in the recovery-first order")
        self.assertIn(self.works["w1"], text)

    def test_a_hand_made_model_renders_as_given(self) -> None:
        data = copy.deepcopy(self.data())
        data["lifecycle"]["current"]["work"]["id"] = "w_HANDMADE"
        model = status.StatusModel(data)
        self.assertIn("w_HANDMADE", status.render_human(model))
        self.assertEqual(json.loads(status.render_json(model)), data)

    def test_a_validation_error_stays_visible_in_the_human_rendering(self) -> None:
        self.store.related_yaml.write_text("relations: {broken\n", encoding="utf-8")
        text = status.render_human(self.model())
        self.assertIn("\nValidation\n  failed", text)
        self.assertIn("structure_unreadable", text)
        self.assertIn("validation failed", text, "Blocked/Waiting names it too")
        self.assertIn("Current\n  unavailable - relations_invalid", text)

    def test_a_failed_completion_reader_renders_one_status_line(self) -> None:
        """RB5PR2-5: the Achievement block prints its status exactly once - "unavailable - <reason>" when the
        completion reader failed, the bare status otherwise."""
        failed = copy.deepcopy(self.data())
        failed["completion"] = {"status": "unavailable", "reason": {"code": "review_record_invalid", "message": "x"}}
        text = status.render_human(status.StatusModel(failed))
        block = text[text.index("\nAchievement\n") + len("\nAchievement\n"):text.index("\nPolicy\n")].splitlines()
        self.assertEqual(["  unavailable - review_record_invalid: x"], [line for line in block if line])
        available = status.render_human(self.model())
        self.assertIn("\nAchievement\n  available\n", available)

    def test_additive_fields_leave_the_base_fields_as_they_are(self) -> None:
        base = self.data()
        later = copy.deepcopy(base)
        later["completion"] = {"status": "ready", "evidence": [{"id": "ev_1"}]}  # RB5
        later["policy"] = {"status": "active", "profile": {"id": "prof_1"}}  # RB6
        later["pending"]["disposition"] = {"status": "none"}  # RB10 N4
        later["lifecycle"]["achievement_hint"] = {"status": "none"}
        injected = status.StatusModel(later)
        rendered = json.loads(status.render_json(injected))
        for section in TOP_LEVEL - {"completion", "policy"}:
            with self.subTest(section=section):
                if isinstance(base[section], dict):
                    for key, value in base[section].items():
                        self.assertEqual(rendered[section][key], value, f"{section}.{key}")
                else:
                    self.assertEqual(rendered[section], base[section])
        text = status.render_human(injected)
        self.assertIn("\nAchievement\n  ready", text)
        self.assertIn("\nPolicy\n  active", text)
        self.assertEqual(status.SCHEMA, "workline-status")
        self.assertEqual(status.VERSION, 1)


if __name__ == "__main__":
    unittest.main()
