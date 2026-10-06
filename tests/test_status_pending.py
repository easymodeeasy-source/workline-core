"""RB1 §29.29: every recovery record is reported, each on its own, with how its owner's recovery would treat it.

``pending_resumable`` is said only where a read-only proof shows the owner's
recovery resumes the record; ``pending_reconcile_required`` only where it shows
that recovery stops as ``reconcile required``. Each such answer here is checked
against what the owner then actually does. Anything else is
``unknown_or_invalid`` with its exact reason - never an optimistic resume.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest import mock

from status_helpers import StatusCase
from workline import push_pin, status
from workline.errors import ReconcileRequired
from workline.mutation import MutationController, WriteScope, inspect_records
from workline.oplock import project_operation
from workline.store import PushPin

LEDGERS = (".workline/events/events.jsonl", ".workline/relations/roadmap.yaml", ".workline/relations/related.yaml")
PAYLOAD = "PAYLOAD-must-not-appear-7c41"


class Crash(Exception):
    """A process death between two steps (never a StopError, so nothing is abandoned on the way out)."""


class PendingStatusTests(StatusCase):
    def records(self, data: dict) -> dict[str, dict]:
        return {entry["filename"]: entry for entry in data["pending"]["records"]}

    def open_start(self, store, work_id: str) -> str:
        with project_operation(store, "start", {}):
            mutation = MutationController(store).open(
                "start", {"operation": "start", "work_id": work_id, "mode": "single-work"},
                WriteScope(entities=(work_id,), files=LEDGERS),
            )
        return mutation.id

    def interrupted_pin(self):
        """A pin maintenance stopped after it wrote project.yaml and before its Git stage."""
        store = self.new_project(remote=True, pin=False)
        with mock.patch.object(push_pin.gitops, "finalize", side_effect=Crash("killed")):
            with self.assertRaises(Crash):
                push_pin.pin_push_destination(store.root, [self.remote_url()])
        pending = MutationController(store).list_pending()
        self.assertEqual(len(pending), 1)
        return store, pending[0]

    # ------------------------------------------------------------------ none
    def test_none(self) -> None:
        self.store = self.new_project()
        data = self.data()
        self.assertEqual(data["pending"]["status"], status.PENDING_NONE)
        self.assertEqual(data["pending"]["records"], [])

    # ------------------------------------------------------------------ owner proofs
    def test_a_positively_resumable_record_of_a_known_owner(self) -> None:
        store, record = self.interrupted_pin()

        entry = self.data(store.root)["pending"]["records"][0]

        self.assertEqual(entry["classification"], status.PENDING_RESUMABLE, entry["reason"])
        self.assertEqual(entry["owner"], push_pin.OWNER)
        self.assertEqual(entry["mutation_id"], record["mutation_id"])
        self.assertEqual(entry["stages"], ["pin"])
        self.assertFalse(entry["affects_progression"], "pin maintenance writes project.yaml only")
        # ... and the owner does resume it.
        result = push_pin.pin_push_destination(store.root, [self.remote_url()])
        self.assertTrue(result.resumed)
        self.assertEqual(result.mutation_id, record["mutation_id"])
        self.assertEqual(self.data(store.root)["pending"]["status"], status.PENDING_NONE)

    def test_the_owner_probe_says_reconcile(self) -> None:
        store, record = self.interrupted_pin()
        other = PushPin("origin", (self.remote_url(), str(self.tmp / "elsewhere.git")))
        store.project_yaml.write_text(store.project_yaml_with_pin(other), encoding="utf-8")

        entry = self.data(store.root)["pending"]["records"][0]

        self.assertEqual(entry["classification"], status.PENDING_RECONCILE, entry["reason"])
        with self.assertRaises(ReconcileRequired):
            push_pin.pin_push_destination(store.root, [self.remote_url()])
        self.assertEqual(MutationController(store).list_pending()[0]["mutation_id"], record["mutation_id"])

    def test_an_owner_precondition_is_not_taken_for_a_resume(self) -> None:
        store, _ = self.interrupted_pin()
        with project_operation(store, "start", {}):
            MutationController(store).open("start", {"operation": "start", "work_id": "w_x", "mode": "single-work"},
                                           WriteScope(entities=("w_x",), files=LEDGERS))
        entries = [e for e in self.data(store.root)["pending"]["records"] if e["owner"] == push_pin.OWNER]
        self.assertEqual(entries[0]["classification"], status.UNKNOWN_OR_INVALID)
        self.assertEqual(entries[0]["reason"]["code"], "pending_operation")

    def test_a_structurally_valid_record_without_a_probe_is_unknown(self) -> None:
        self.store = self.new_project()
        roadmap = self.simple_roadmap(self.store)
        work = self.simple_entry(self.store, roadmap.phase_ids["a"]).work_ids["w1"]
        mutation_id = self.open_start(self.store, work)

        entry = self.data()["pending"]["records"][0]

        self.assertEqual(entry["mutation_id"], mutation_id)
        self.assertEqual(entry["owner"], "start")
        self.assertEqual(entry["classification"], status.UNKNOWN_OR_INVALID)
        self.assertEqual(entry["reason"]["code"], "no_read_only_resume_probe")
        self.assertTrue(entry["affects_progression"])
        self.assertEqual(entry["operation"], {"operation": "start", "work_id": work, "mode": "single-work"})
        self.assertEqual(entry["write_scope"], {"entities": [work], "files": sorted(LEDGERS)})

    def test_duplicate_records_of_one_invocation_are_reconcile(self) -> None:
        self.store = self.new_project()
        mutation_id = self.open_start(self.store, "w_01ARZ3NDEKTSV4RRFFQ69G5FAV")
        source = self.store.mutations / f"{mutation_id}.yaml"
        twin = "mut_01ARZ3NDEKTSV4RRFFQ69G5FAW"
        (self.store.mutations / f"{twin}.yaml").write_bytes(source.read_bytes().replace(mutation_id.encode(), twin.encode()))

        entries = self.data()["pending"]["records"]

        self.assertEqual({e["classification"] for e in entries}, {status.PENDING_RECONCILE})
        self.assertEqual({e["reason"]["code"] for e in entries}, {"duplicate_pending_invocation"})

    # ------------------------------------------------------------------ malformed
    def test_a_malformed_filename_is_reported_and_hides_nothing(self) -> None:
        self.store = self.new_project()
        mutation_id = self.open_start(self.store, "w_01ARZ3NDEKTSV4RRFFQ69G5FAV")
        (self.store.mutations / "notes.yaml").write_text("owner: someone\n", encoding="utf-8")

        records = self.records(self.data())

        stray = records["notes.yaml"]
        self.assertEqual((stray["parse_state"], stray["classification"]), ("filename_invalid", status.UNKNOWN_OR_INVALID))
        self.assertEqual(stray["reason"]["code"], "mutation_filename_invalid")
        self.assertIsNone(stray["owner"], "an unreadable record's owner is never guessed")
        valid = records[f"{mutation_id}.yaml"]
        self.assertEqual(valid["classification"], status.PENDING_RECONCILE)
        self.assertEqual(valid["reason"]["code"], "mutation_area_unreadable")
        # exactly what every owner meets: the strict reader stops on the stray file
        with self.assertRaises(ReconcileRequired):
            MutationController(self.store).list_pending()

    def test_a_malformed_record_is_reported_without_mutation(self) -> None:
        self.store = self.new_project()
        self.store.mutations.mkdir(parents=True, exist_ok=True)
        broken = self.store.mutations / "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV.yaml"
        broken.write_bytes(b"workline: workline-mutation-intent\nversion: 1\nowner: [\n")
        foreign = self.store.mutations / "mut_01ARZ3NDEKTSV4RRFFQ69G5FAW.yaml"
        foreign.write_text("workline: someone-else\nversion: 1\n", encoding="utf-8")
        before = (broken.read_bytes(), foreign.read_bytes())

        records = self.records(self.data())

        self.assertEqual(records[broken.name]["parse_state"], "unreadable")
        self.assertEqual(records[broken.name]["reason"]["code"], "mutation_record_unreadable")
        self.assertEqual(records[foreign.name]["parse_state"], "ownership_unconfirmed")
        self.assertEqual(records[foreign.name]["reason"]["code"], "mutation_record_ownership_unconfirmed")
        self.assertEqual(
            records[foreign.name]["reason"]["message"],
            f"cannot confirm Workline ownership of recovery record {foreign.name}",
            "the exact reason the strict reader stops with",
        )
        self.assertEqual((broken.read_bytes(), foreign.read_bytes()), before)

    def test_several_records_one_malformed_hides_none_of_the_others(self) -> None:
        self.store = self.new_project()
        first = self.open_start(self.store, "w_01ARZ3NDEKTSV4RRFFQ69G5FAV")
        with project_operation(self.store, "bootstrap-backfill", {}):
            second = MutationController(self.store).open(
                "bootstrap-backfill", {"operation": "bootstrap-backfill", "project_root": str(self.store.root)},
                WriteScope(files=(".claude/skills/workline/SKILL.md",)),
            ).id
        (self.store.mutations / "mut_01ARZ3NDEKTSV4RRFFQ69G5FAX.yaml").write_bytes(b"\xff")

        data = self.data()

        ids = [entry["mutation_id"] for entry in data["pending"]["records"]]
        self.assertEqual(ids, sorted(ids))
        self.assertIn(first, ids)
        self.assertIn(second, ids)
        self.assertIn("mut_01ARZ3NDEKTSV4RRFFQ69G5FAX", ids)
        self.assertEqual(len(inspect_records(self.store)), 3)

    # ------------------------------------------------------------------ safety
    def test_scope_and_invocation_are_reported_without_the_request_payload(self) -> None:
        self.store = self.new_project()
        invocation = {
            "operation": "create-direct", "name": PAYLOAD, "key": PAYLOAD,
            "request": {"version": 1, "name": PAYLOAD, "desired_state": PAYLOAD, "related": [],
                        "derivation_detail": None},
        }
        with project_operation(self.store, "create-direct", {}):
            MutationController(self.store).open("create-direct", invocation,
                                                WriteScope(files=(".workline/relations/related.yaml",)))

        data = self.data()
        text = json.dumps(data)
        human = status.render_human(self.model())

        self.assertNotIn(PAYLOAD, text)
        self.assertNotIn(PAYLOAD, human)
        entry = data["pending"]["records"][0]
        self.assertEqual(entry["operation"], {"operation": "create-direct"})
        self.assertEqual(entry["write_scope"], {"entities": [], "files": [".workline/relations/related.yaml"]})

    def test_a_credential_in_an_identifying_field_is_redacted(self) -> None:
        self.store = self.new_project()
        secret = "https://user:hunter2@example.invalid/repo.git"
        with project_operation(self.store, "push-destination-pin", {}):
            MutationController(self.store).open(
                "push-destination-pin",
                {"operation": "push-destination-pin", "project_root": str(self.store.root), "remote": secret,
                 "urls": [secret]},
                WriteScope(files=(".workline/project.yaml",)),
            )
        model = self.model()
        text = status.render_json(model) + status.render_human(model)
        self.assertNotIn("hunter2", text)
        entry = json.loads(status.render_json(model))["pending"]["records"][0]
        self.assertEqual(entry["operation"]["remote"], "https://***@example.invalid/repo.git")

    # ------------------------------------------------------------------ later additive states
    def test_disposed_by_human_is_a_value_of_the_same_field(self) -> None:
        self.assertIn(status.DISPOSED_BY_HUMAN, status.RESUME_CLASSIFICATIONS)
        self.store = self.new_project()
        self.open_start(self.store, "w_01ARZ3NDEKTSV4RRFFQ69G5FAV")
        model = self.model()
        data = json.loads(status.render_json(model))
        record = data["pending"]["records"][0]
        later = json.loads(json.dumps(data))
        later["pending"]["records"][0].update(classification=status.DISPOSED_BY_HUMAN, disposition={"by": "human"})
        injected = status.StatusModel(later)
        status.render_human(injected)  # the renderer takes the added state and field as they are
        rerendered = json.loads(status.render_json(injected))["pending"]["records"][0]
        for key in record:
            if key != "classification":
                self.assertEqual(rerendered[key], record[key], key)


if __name__ == "__main__":
    unittest.main()
