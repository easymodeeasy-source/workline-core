"""RB1 §29.27: B0 / B1 - a read without the lock says when the Project changed under it, and then claims nothing.

Each change is made from inside the read itself (``status._collect`` is wrapped),
so it lands between the B0 and B1 witnesses exactly as a concurrent writer's
would.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import unittest
from unittest import mock

from helpers import git
from status_helpers import StatusCase, append_events
from workline import status
from workline.mutation import MutationController, WriteScope
from workline.oplock import project_operation

LEDGERS = (".workline/events/events.jsonl", ".workline/relations/roadmap.yaml", ".workline/relations/related.yaml")


def make_link(target: Path, link: Path) -> None:
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def remove_link(link: Path) -> None:
    if os.name == "nt":
        os.rmdir(link)
    else:
        link.unlink()


class SnapshotTests(StatusCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        roadmap = self.simple_roadmap(self.store)
        self.works = self.simple_entry(self.store, roadmap.phase_ids["a"], {"w1": "W1 done", "w2": "W2 done"}).work_ids
        append_events(self.store, ("work_started", self.works["w1"]), ("work_target_added", self.works["w1"]))
        self.calls = 0

    def during_read(self, change, *, times: int = 1) -> dict:
        """Build the model while ``change`` runs inside the read, ``times`` times (``0`` for every read)."""
        real = status._collect

        def collect(root):
            self.calls += 1
            body = real(root)
            if times == 0 or self.calls <= times:
                change(self.calls)
            return body

        with mock.patch.object(status, "_collect", collect):
            return json.loads(status.render_json(status.build_status(self.store.root)))

    def assertChanging(self, data: dict) -> None:
        self.assertEqual((data["snapshot_consistency"], data["snapshot_reason"]),
                         ("changing", "project_changed_during_status"))
        life = data["lifecycle"]
        for group, name in (("current", "roadmap"), ("current", "phase"), ("current", "work"), ("next", "phase"),
                            ("next", "work")):
            self.assertEqual((life[group][name]["id"], life[group][name]["reason"]),
                             (None, "project_changed_during_status"), f"{group}.{name}")
        self.assertEqual(life["current"]["work"]["candidates"], [self.works["w1"]], "observed facts stay")
        self.assertEqual(data["validation"]["status"], "pass", "independent diagnostics are still returned")

    # ------------------------------------------------------------------ stable
    def test_a_stable_read(self) -> None:
        data = self.during_read(lambda n: None)
        self.assertEqual((data["snapshot_consistency"], data["snapshot_reason"]), ("stable_read", None))
        self.assertEqual(data["lifecycle"]["current"]["work"]["id"], self.works["w1"])
        self.assertEqual(self.calls, 1)

    # ------------------------------------------------------------------ each witness
    def test_head_moves(self) -> None:
        self.assertChanging(self.during_read(lambda n: git(self.store.root, "commit", "--allow-empty", "-q", "-m", f"c{n}"), times=0))

    def test_the_branch_changes(self) -> None:
        self.assertChanging(self.during_read(lambda n: git(self.store.root, "checkout", "-q", "-b", f"other-{n}"), times=0))

    def test_canonical_content_changes(self) -> None:
        work_file = self.store.entity_path("work", self.works["w2"])

        def change(n):
            work_file.write_text(work_file.read_text(encoding="utf-8") + f"\nnote {n}\n", encoding="utf-8")

        self.assertChanging(self.during_read(change, times=0))

    def test_a_canonical_entry_is_added(self) -> None:
        self.assertChanging(self.during_read(
            lambda n: (self.store.root / ".workline" / "derivations" / f"extra-{n}.md").write_text("x", encoding="utf-8"),
            times=0,
        ))

    def test_a_canonical_entry_is_removed(self) -> None:
        extras = [self.store.root / ".workline" / f"extra-{n}.md" for n in (1, 2)]
        for path in extras:
            path.write_text("x", encoding="utf-8")
        self.assertChanging(self.during_read(lambda n: extras[n - 1].unlink(), times=0))

    def test_an_indirection_changes_its_target_and_is_never_followed(self) -> None:
        targets = [self.tmp / f"target-{n}" for n in (0, 1, 2)]
        for target in targets:
            target.mkdir()
            (target / "inside.txt").write_text(f"{target.name}\n", encoding="utf-8")
        link = self.store.root / ".workline" / "linked"
        make_link(targets[0], link)
        fingerprint = status.canonical_fingerprint(self.store.root)
        (targets[0] / "inside.txt").write_text("changed behind the link\n", encoding="utf-8")
        self.assertEqual(status.canonical_fingerprint(self.store.root), fingerprint, "the link is never followed")
        inventory = dict((entry[0], entry[1]) for entry in status.canonical_inventory(self.store.root))
        self.assertEqual(inventory[".workline/linked"], "indirection")
        self.assertNotIn(".workline/linked/inside.txt", inventory)

        def repoint(n):
            remove_link(link)
            make_link(targets[n], link)

        self.assertChanging(self.during_read(repoint, times=0))

    def test_the_runtime_area_is_not_part_of_the_fingerprint(self) -> None:
        fingerprint = status.canonical_fingerprint(self.store.root)
        (self.store.root / ".workline" / "runtime" / "locks").mkdir(parents=True, exist_ok=True)
        (self.store.root / ".workline" / "runtime" / "locks" / "holder.json").write_text("{}", encoding="utf-8")
        (self.store.root / ".workline" / "runtime" / "tmp").mkdir(parents=True, exist_ok=True)
        (self.store.root / ".workline" / "runtime" / "tmp" / "x").write_text("y", encoding="utf-8")
        self.assertEqual(status.canonical_fingerprint(self.store.root), fingerprint)

    def open_start(self, work: str) -> str:
        with project_operation(self.store, "start", {}):
            return MutationController(self.store).open(
                "start", {"operation": "start", "work_id": work, "mode": "single-work"},
                WriteScope(entities=(work,), files=LEDGERS),
            ).id

    def test_same_mutation_id_but_its_bytes_change(self) -> None:
        mutation_id = self.open_start(self.works["w2"])
        record = self.store.mutations / f"{mutation_id}.yaml"

        def change(n):
            record.write_bytes(record.read_bytes() + f"# touched {n}\n".encode("utf-8"))

        data = self.during_read(change, times=0)
        self.assertEqual(data["snapshot_consistency"], "changing")
        self.assertEqual(data["lifecycle"]["current"]["work"]["reason"], "project_changed_during_status",
                         "changing outranks the pending-mutation reason")

    def test_a_pending_mutation_is_added(self) -> None:
        def change(n):
            if n == 1:
                self.open_start(self.works["w2"])
            else:
                for path in self.store.mutations.glob("*.yaml"):
                    path.unlink()

        self.assertChanging(self.during_read(change, times=0))

    def test_a_pending_mutation_is_removed(self) -> None:
        self.open_start(self.works["w2"])
        self.store.mutations.mkdir(parents=True, exist_ok=True)

        def change(n):
            files = sorted(self.store.mutations.glob("*.yaml"))
            if files:
                files[0].unlink()
            else:
                self.open_start(self.works["w2"])

        data = self.during_read(change, times=0)
        self.assertEqual(data["snapshot_consistency"], "changing")

    # ------------------------------------------------------------------ bounded retry
    def test_one_retry_recovers_one_transient_change(self) -> None:
        data = self.during_read(lambda n: git(self.store.root, "commit", "--allow-empty", "-q", "-m", "once"), times=1)
        self.assertEqual(data["snapshot_consistency"], "stable_read")
        self.assertEqual(self.calls, 2)
        self.assertEqual(data["lifecycle"]["current"]["work"]["id"], self.works["w1"])
        self.assertEqual(data["git"]["head"], git(self.store.root, "rev-parse", "HEAD").strip())

    def test_a_repeated_change_never_loops(self) -> None:
        data = self.during_read(lambda n: git(self.store.root, "commit", "--allow-empty", "-q", "-m", f"again {n}"), times=0)
        self.assertEqual(self.calls, 2, "one read and one immediate rebuild, nothing more")
        self.assertChanging(data)

    def test_the_changing_model_renders_no_current_or_next_claim(self) -> None:
        real = status._collect

        def collect(root):
            body = real(root)
            git(self.store.root, "commit", "--allow-empty", "-q", "-m", "moving")
            return body

        with mock.patch.object(status, "_collect", collect):
            model = status.build_status(self.store.root)
        text = status.render_human(model)
        self.assertIn("snapshot: changing (project_changed_during_status)", text)
        self.assertNotIn(f"Work: {self.works['w1']}", text)


if __name__ == "__main__":
    unittest.main()
