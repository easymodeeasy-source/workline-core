"""RB1 §29.31: validation, local Git / push destination, and authority - each read on its own, offline.

A broken part of a Project is reported where it is and with its exact reason,
and does not take the independent parts of the model with it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from helpers import WORKLINE_ROOT, copy_workline_root, git
from status_helpers import StatusCase
from workline import status
from workline.store import render_project_yaml

SECRET = "hunter2-s3cr3t"


class ValidationSectionTests(StatusCase):
    def test_validate_pass(self) -> None:
        self.store = self.new_project()
        validation = self.data()["validation"]
        self.assertEqual(validation, {"status": "pass", "reason": None, "problems": [], "implementation_verified": True})

    def test_an_invalid_project_yaml_still_yields_every_independent_section(self) -> None:
        self.store = self.new_project()
        self.simple_roadmap(self.store)
        self.store.project_yaml.write_text("workline: [unclosed\n", encoding="utf-8")
        data = self.data()
        self.assertTrue(data["project"]["established"])
        self.assertEqual(data["project"]["project_yaml"]["status"], "unreadable")
        self.assertEqual(data["project"]["project_yaml"]["reason"]["code"], "project_yaml_invalid")
        self.assertEqual(data["validation"]["status"], "failed")
        self.assertIn("project_yaml_invalid", [p["code"] for p in data["validation"]["problems"]])
        self.assertEqual(data["git"]["status"], "available")
        self.assertEqual(data["lifecycle"]["status"], "available", "the ledgers still read")
        self.assertEqual(data["pending"]["status"], "none")
        self.assertEqual(data["authority"]["implementation"]["status"], "unavailable")
        self.assertEqual(data["git"]["push_destination"]["approved_destination"]["status"], "invalid")

    def test_an_unreadable_ledger_still_yields_every_independent_section(self) -> None:
        self.store = self.new_project()
        self.store.related_yaml.write_text("relations: {broken\n", encoding="utf-8")
        data = self.data()
        self.assertEqual(data["lifecycle"]["status"], "unavailable")
        self.assertEqual(data["lifecycle"]["reason"]["code"], "relations_invalid")
        self.assertEqual(data["validation"]["status"], "failed")
        self.assertIn("structure_unreadable", [p["code"] for p in data["validation"]["problems"]])
        self.assertTrue(data["project"]["established"], "an invalid ledger is not 'not a project'")
        for section in ("git", "review"):
            self.assertEqual(data[section]["status"], "available", section)
        self.assertEqual(data["authority"]["implementation"]["status"], "match")
        human = status.render_human(self.model())
        self.assertIn("relations_invalid", human)

    def test_a_folder_that_is_not_a_project(self) -> None:
        plain = self.new_dir("plain")
        data = status_data = self.data(plain)
        self.assertFalse(data["project"]["established"])
        self.assertEqual(data["validation"]["status"], "unavailable")
        self.assertEqual(data["validation"]["reason"]["code"], "not_an_established_project")
        self.assertEqual(data["git"]["reason"]["code"], "not_a_git_repository")
        self.assertEqual(status_data["completion"], {"status": "not_available_by_contract"})

    def test_a_missing_root_is_a_model_not_a_crash(self) -> None:
        data = self.data(self.tmp / "nowhere")
        self.assertEqual(data["project"]["root_kind"], "missing")
        self.assertEqual(data["git"]["status"], "unavailable")
        self.assertEqual(data["snapshot_consistency"], "stable_read")


class GitSectionTests(StatusCase):
    def push(self) -> dict:
        return self.data()["git"]["push_destination"]

    def test_detached_head(self) -> None:
        self.store = self.new_project()
        git(self.store.root, "checkout", "-q", "--detach")
        data = self.data()["git"]
        self.assertEqual((data["detached"], data["branch_ref"], data["branch"]), (True, None, None))
        self.assertEqual(data["head"], git(self.store.root, "rev-parse", "HEAD").strip())

    def test_a_branch(self) -> None:
        self.store = self.new_project()
        data = self.data()["git"]
        self.assertEqual((data["detached"], data["branch_ref"], data["branch"]), (False, "refs/heads/main", "main"))
        self.assertTrue(data["toplevel_is_project_root"])

    def test_dirty_paths_are_deterministic(self) -> None:
        self.store = self.new_project()
        for name in ("zeta.txt", "alpha.txt", "mid/beta.txt"):
            path = self.store.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n", encoding="utf-8")
        self.store.project_yaml.write_text(self.store.project_yaml.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        first = self.data()["git"]["dirty"]
        self.assertEqual(first, self.data()["git"]["dirty"])
        paths = [entry["path"] for entry in first["entries"]]
        self.assertEqual(paths, sorted(paths))
        self.assertIn({"path": ".workline/project.yaml", "index": " ", "worktree": "M", "orig_path": None}, first["entries"])
        self.assertIn({"path": "mid/beta.txt", "index": "?", "worktree": "?", "orig_path": None}, first["entries"])

    def test_no_remote(self) -> None:
        self.store = self.new_project()
        push = self.push()
        self.assertEqual(push["remotes"], [])
        self.assertEqual(push["approved_destination"]["status"], "unpinned")
        self.assertEqual((push["problem"], push["local_locator_matches_pin"]), (None, None))
        self.assertEqual(push["remote_publication_state"], "not_checked")

    def test_an_unpinned_remote(self) -> None:
        self.store = self.new_project(remote=True, pin=False)
        push = self.push()
        self.assertEqual(push["remotes"], ["origin"])
        self.assertEqual(push["approved_destination"]["status"], "unpinned")
        self.assertEqual(push["problem"], "push_destination_unpinned")
        self.assertEqual(push["remote_publication_state"], "not_checked")

    def test_a_pinned_matching_locator(self) -> None:
        self.store = self.new_project(remote=True)
        push = self.push()
        self.assertEqual(push["approved_destination"],
                         {"status": "pinned", "remote": "origin", "allowed_urls": [self.remote_url()], "reason": None})
        self.assertEqual(push["active_local_push_locator"]["status"], "resolved")
        self.assertEqual(push["active_local_push_locator"]["locator"], self.remote_url())
        self.assertEqual((push["local_locator_matches_pin"], push["problem"]), (True, None))
        self.assertEqual(push["remote_publication_state"], "not_checked")

    def test_a_pinned_mismatching_locator(self) -> None:
        self.store = self.new_project(remote=True)
        other = str(self.tmp / "other.git")
        git(self.store.root, "remote", "set-url", "origin", other)
        push = self.push()
        self.assertEqual(push["active_local_push_locator"]["locator"], other)
        self.assertEqual((push["local_locator_matches_pin"], push["problem"]), (False, "push_destination_mismatch"))

    def test_multiple_push_locators(self) -> None:
        self.store = self.new_project(remote=True)
        git(self.store.root, "remote", "set-url", "--add", "--push", "origin", self.remote_url())
        git(self.store.root, "remote", "set-url", "--add", "--push", "origin", str(self.tmp / "second.git"))
        push = self.push()
        self.assertEqual(push["active_local_push_locator"]["status"], "multiple")
        self.assertEqual(len(push["active_local_push_locator"]["locators"]), 2)
        self.assertEqual((push["local_locator_matches_pin"], push["problem"]), (False, "push_destination_multiple"))

    def test_a_credential_bearing_locator_is_never_emitted(self) -> None:
        self.store = self.new_project(remote=True)
        git(self.store.root, "remote", "set-url", "--push", "origin", f"https://user:{SECRET}@example.invalid/r.git")
        data = self.data()
        text = json.dumps(data) + status.render_human(self.model())
        self.assertNotIn(SECRET, text)
        push = data["git"]["push_destination"]
        self.assertEqual(push["active_local_push_locator"]["status"], "secret_redacted")
        self.assertEqual(push["active_local_push_locator"]["locator"], "https://***@example.invalid/r.git")
        self.assertEqual((push["local_locator_matches_pin"], push["problem"]), (False, "push_destination_secret"))
        self.assertEqual(push["remote_publication_state"], "not_checked")


class AuthoritySectionTests(StatusCase):
    def configure_root(self, root: Path) -> None:
        self.store.project_yaml.write_text(render_project_yaml(root, self.store.read_push_pin()), encoding="utf-8")
        git(self.store.root, "add", ".workline/project.yaml")
        git(self.store.root, "commit", "-q", "-m", "configure another Workline root")

    def test_the_inventory_is_stable_ids_targets_and_digests_only(self) -> None:
        self.store = self.new_project()
        data = self.data()
        authority = data["authority"]
        self.assertEqual(authority["running_workline_root"]["path"], str(WORKLINE_ROOT))
        self.assertEqual(authority["implementation"], {"status": "match", "reason": None})
        registry = authority["registry"]
        self.assertEqual(registry["status"], "valid")
        self.assertEqual(registry["sha256"], hashlib.sha256((WORKLINE_ROOT / "registry.md").read_bytes()).hexdigest())
        entries = authority["inventory"]["entries"]
        self.assertEqual([e["id"] for e in entries], sorted(e["id"] for e in entries))
        for entry in entries:
            self.assertEqual(set(entry), {"id", "target", "context", "sha256"})
            if entry["id"].startswith("skills/"):
                expected = hashlib.sha256((WORKLINE_ROOT / entry["target"]).read_bytes()).hexdigest()
                self.assertEqual(entry["sha256"], expected)
            else:
                self.assertEqual((entry["target"], entry["sha256"]), (None, None))
        self.assertIn("skills/start", [e["id"] for e in entries])
        self.assertIn("rules/git", [e["id"] for e in entries])
        text = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("Project router", text, "no Skill or rule prose is copied")
        self.assertNotIn("Git履歴は積み上げる", text)

    def test_a_missing_configured_workline_root(self) -> None:
        self.store = self.new_project()
        self.configure_root(self.tmp / "gone")
        data = self.data()
        configured = data["project"]["configured_workline_root"]
        self.assertEqual((configured["status"], configured["exists"]), ("readable", False))
        self.assertEqual(data["authority"]["registry"]["reason"]["code"], "workline_root_missing")
        self.assertNotEqual(data["authority"]["implementation"]["status"], "match")
        self.assertIn("workline_root_missing", [p["code"] for p in data["validation"]["problems"]])
        self.assertEqual(data["git"]["status"], "available")

    def test_an_invalid_registry(self) -> None:
        self.store = self.new_project()
        text = (WORKLINE_ROOT / "registry.md").read_text(encoding="utf-8")
        other = copy_workline_root(self.tmp / "broken-root", registry=text.replace("<!-- workline-id: rules/git -->", ""))
        self.configure_root(other)
        data = self.data()
        registry = data["authority"]["registry"]
        self.assertEqual(registry["status"], "invalid")
        self.assertIn("required_rule_missing", [p["code"] for p in registry["problems"]])
        self.assertIsNotNone(registry["sha256"], "the bytes are still digested")
        self.assertEqual(data["authority"]["inventory"]["entries"], [], "no partial routing inventory")
        self.assertEqual(data["authority"]["inventory"]["reason"]["code"], "registry_invalid")

    def test_an_implementation_mismatch_is_a_fact_and_never_a_pass(self) -> None:
        self.store = self.new_project()
        other = copy_workline_root(self.tmp / "other-root")
        self.configure_root(other)
        data = self.data()
        self.assertEqual(data["authority"]["implementation"]["status"], "mismatch")
        self.assertEqual(data["authority"]["implementation"]["reason"]["code"], "workline_implementation_mismatch")
        self.assertEqual(data["authority"]["registry"]["status"], "valid")
        self.assertEqual(data["validation"]["implementation_verified"], False)
        self.assertNotEqual(data["validation"]["status"], "pass")
        self.assertEqual(data["validation"]["reason"]["code"], "workline_implementation_mismatch")


if __name__ == "__main__":
    unittest.main()
