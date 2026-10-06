"""RB10 N4: explicit Human-invoked recovery disposition (``WORKLINE_COMPLETION_SPRINT.md`` §35).

The record, its path and parser (§35.2, §35.3, §35.12), the Human / API boundary
(§35.4, §35.23), the mutation target (§35.5-§35.8, §35.24), idempotency
(§35.14, §35.26), RB1 status (§35.16), validation (§35.18) and clone / runtime
loss (§35.19). The Review target is ``test_recovery_disposition_review``; the
interruption matrix (§35.27) is ``test_recovery_disposition_interruptions``.
"""

from __future__ import annotations

import contextlib
import inspect
import io
import json
import re
from pathlib import Path
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, copy_workline_root, cwd, git, launcher_command, run_python
from status_helpers import StatusCase, tree_snapshot
from workline import cli, gitcmd, push_pin, status
from workline import recovery_disposition as rd
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.mutation import MutationController, WriteScope
from workline.oplock import project_operation
from workline.store import PushPin, ProjectStore

LEDGERS = (".workline/events/events.jsonl", ".workline/relations/roadmap.yaml", ".workline/relations/related.yaml")
REASON = "the interrupted pin attempt was replaced by a manual pin review"
SOME_MUTATION = "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV"
SOME_RUN = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"
#: The pin of ``tests/test_project_start_recovery.py``: no CLI command is cleanup, repair or recovery of Project開始.
FORBIDDEN_COMMAND = r"clean|prune|purge|repair|reconcile|abandon|retry|recover"


class Crash(Exception):
    """A process death between two steps (never a StopError, so nothing is abandoned on the way out)."""


def commands() -> set[str]:
    return set(re.findall(r'add_parser\(\s*"([^"]+)"', inspect.getsource(cli)))


class DispositionCase(StatusCase):
    """A Project whose interrupted pin maintenance RB1 proves ``pending_reconcile_required``."""

    def reconcile_pin(self, name: str = "proj") -> str:
        """Pin maintenance wrote project.yaml and died before its Git stage; then the file was changed by hand."""
        self.store = self.new_project(name, remote=True, pin=False)
        with mock.patch.object(push_pin.gitops, "finalize", side_effect=Crash("killed")), self.assertRaises(Crash):
            push_pin.pin_push_destination(self.store.root, [self.remote_url(name)])
        (record,) = MutationController(self.store).list_pending()
        other = PushPin("origin", (self.remote_url(name), str(self.tmp / f"{name}-elsewhere.git")))
        self.store.project_yaml.write_text(self.store.project_yaml_with_pin(other), encoding="utf-8")
        classification, _ = status.pending_classification(self.store, record["mutation_id"])
        self.assertEqual(classification, status.PENDING_RECONCILE)
        return str(record["mutation_id"])

    def resumable_pin(self) -> str:
        self.store = self.new_project(remote=True, pin=False)
        with mock.patch.object(push_pin.gitops, "finalize", side_effect=Crash("killed")), self.assertRaises(Crash):
            push_pin.pin_push_destination(self.store.root, [self.remote_url()])
        (record,) = MutationController(self.store).list_pending()
        return str(record["mutation_id"])

    def open_start(self, store: ProjectStore, work_id: str = "w_01ARZ3NDEKTSV4RRFFQ69G5FAV") -> str:
        with project_operation(store, "start", {}):
            mutation = MutationController(store).open(
                "start", {"operation": "start", "work_id": work_id, "mode": "single-work"},
                WriteScope(entities=(work_id,), files=LEDGERS),
            )
        return mutation.id

    def dispose(self, target: str, reason: str = REASON) -> rd.DispositionResult:
        return rd.dispose_recovery(self.store.root, target, reason, confirmed=True)

    def runtime(self, target: str) -> bytes:
        return (self.store.mutations / f"{target}.yaml").read_bytes()

    def record_files(self) -> list[str]:
        directory = self.store.root / ".workline" / "recovery" / "dispositions"
        return sorted(path.name for path in directory.iterdir()) if directory.exists() else []

    def disposition_commits(self) -> list[str]:
        return [s for s in git(self.store.root, "log", "--format=%s").splitlines() if s.startswith("chore(workline): set aside")]

    def head(self) -> str:
        return git(self.store.root, "rev-parse", "HEAD").strip()

    def stable_tree(self) -> dict:
        """The Project's bytes outside what Git refreshes and what the lock leaves (``.git``, runtime/locks)."""
        return {path: entry for path, entry in tree_snapshot(self.store.root).items()
                if not path.startswith(".git/") and path != ".git" and not path.startswith(".workline/runtime/locks")}

    def assertRefused(self, code: str, call, *args, **kwargs) -> StopError:
        before = (self.stable_tree(), self.head())
        with self.assertRaises(StopError) as raised:
            call(*args, **kwargs)
        found = raised.exception
        self.assertEqual(getattr(found, "reason", None) or found.code, code, found)
        self.assertEqual((self.stable_tree(), self.head()), before, "a refusal changed nothing")
        return found


# --------------------------------------------------------------------------- §35.28 (1): record, path, parser


class RecordTests(unittest.TestCase):
    def record(self, **changes) -> dict:
        found = rd.Disposition(rd.KIND_MUTATION, SOME_MUTATION, "a" * 64, "set aside by hand").to_record()
        found.update(changes)
        return found

    def text(self, **changes) -> bytes:
        from workline import yamlish

        return yamlish.dump(dict(sorted(self.record(**changes).items()))).encode("utf-8")

    def test_the_v1_record_is_exactly_its_nine_fields_and_round_trips_canonically(self) -> None:
        found = rd.Disposition(rd.KIND_REVIEW_RUN, SOME_RUN, "b" * 64, "no replacement will be made")
        text = rd.render(found)
        self.assertEqual(set(found.to_record()), set(rd.FIELDS))
        self.assertEqual(rd.parse(text.encode("utf-8"), SOME_RUN), found)
        self.assertEqual(found.target_state_contract, "review-run-recovery-v1")
        self.assertEqual((found.decision, found.decision_source), ("set_aside", "human"))
        self.assertNotIn("at", found.to_record(), "no timestamp: idempotency is structural")
        self.assertTrue(all(field not in text for field in ("created_at", "updated_at", "timestamp")))
        # a checkout that wrote CRLF for the committed LF reads the same record
        self.assertEqual(rd.parse(text.replace("\n", "\r\n").encode("utf-8"), SOME_RUN), found)

    def test_unknown_missing_or_disagreeing_fields_fail_closed(self) -> None:
        good = self.text()
        self.assertEqual(rd.parse(good, SOME_MUTATION).target_id, SOME_MUTATION)
        record = self.record()
        missing = dict(record)
        del missing["reason"]
        cases = {
            "extra field": dict(record, at="2026-01-01"),
            "missing field": missing,
            "other schema": dict(record, schema="workline-recovery-other"),
            "version 2": dict(record, version=2),
            "version text": dict(record, version="1"),
            "unknown kind": dict(record, target_kind="work"),
            "kind / id disagree": dict(record, target_kind="review_run"),
            "contract / kind disagree": dict(record, target_state_contract="review-run-recovery-v1"),
            "short digest": dict(record, target_state_digest="a" * 63),
            "upper digest": dict(record, target_state_digest="A" * 64),
            "decision": dict(record, decision="delete"),
            "source": dict(record, decision_source="ai"),
            "blank reason": dict(record, reason="  "),
            "untrimmed reason": dict(record, reason=" padded "),
            "multi-line reason": dict(record, reason="a\nb"),
            "another target": dict(record, target_id="mut_01ARZ3NDEKTSV4RRFFQ69G5FAW"),
        }
        from workline import yamlish

        for name, data in cases.items():
            with self.subTest(name), self.assertRaises(ValidationError) as raised:
                rd.parse(yamlish.dump(dict(sorted(data.items()))).encode("utf-8"), SOME_MUTATION)
            self.assertEqual(raised.exception.code, "recovery_disposition_invalid")
        for name, raw in {"unsorted keys": yamlish_unsorted(record), "not utf-8": b"\xff\xfe",
                          "not a mapping": b"- a\n"}.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                rd.parse(raw, SOME_MUTATION)

    def test_one_canonical_path_per_target_and_no_other_kind(self) -> None:
        self.assertEqual(rd.disposition_rel(SOME_MUTATION), f".workline/recovery/dispositions/{SOME_MUTATION}.yaml")
        self.assertEqual(rd.require_disposition_path(rd.disposition_rel(SOME_RUN)), SOME_RUN)
        for target in ("w_01ARZ3NDEKTSV4RRFFQ69G5FAV", "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV", "mut_x", "", None, 7):
            with self.subTest(target=target):
                self.assertIsNone(rd.target_kind(target))
                with self.assertRaises(ValidationError) as raised:
                    rd.disposition_rel(target)  # type: ignore[arg-type]
                self.assertEqual(raised.exception.code, "recovery_disposition_target_invalid")
        for path in (".workline/recovery/dispositions/w_01ARZ3NDEKTSV4RRFFQ69G5FAV.yaml",
                     f".workline/recovery/dispositions/{SOME_RUN}.yml",
                     f".workline/recovery/other/{SOME_RUN}.yaml",
                     f".workline/recovery/dispositions/x/{SOME_RUN}.yaml",
                     f".workline/RECOVERY/dispositions/{SOME_RUN}.yaml"):
            with self.subTest(path=path), self.assertRaises(ValidationError) as raised:
                rd.require_disposition_path(path)
            self.assertEqual(raised.exception.code, "recovery_disposition_path")
        for spelling in (".workline/recovery/x", ".workline/Recovery/x", ".workline/RECOVERY./x", ".workline/recovery /x"):
            self.assertTrue(rd.in_recovery_namespace(spelling), spelling)
        for other in (".workline/review/x", ".workline/recoveryx/y", "recovery/x", ".workline"):
            self.assertFalse(rd.in_recovery_namespace(other), other)

    def test_the_reason_is_trimmed_one_line_text(self) -> None:
        self.assertEqual(rd.normalize_reason("  a public-safe reason \t"), "a public-safe reason")
        self.assertEqual(rd.normalize_reason("日本語の理由"), "日本語の理由")
        for refused in ("", "   ", "a\nb", "a\rb", "a\x00b", "a\x85b", "a" + chr(0x2028) + "b", "a" + chr(0xD800), None, 3):
            with self.subTest(reason=repr(refused)), self.assertRaises(StopError) as raised:
                rd.normalize_reason(refused)
            self.assertEqual(raised.exception.code, "recovery_disposition_reason_invalid")

    def test_the_mutation_witness_is_domain_separated_over_exact_bytes(self) -> None:
        import hashlib

        raw = b"workline: workline-mutation-intent\r\n"
        self.assertNotEqual(rd.mutation_state_digest(raw), hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(rd.mutation_state_digest(raw), rd.mutation_state_digest(raw.replace(b"\r\n", b"\n")))
        self.assertRegex(rd.mutation_state_digest(raw), r"^[0-9a-f]{64}$")


def yamlish_unsorted(record: dict) -> bytes:
    from workline import yamlish

    return yamlish.dump(dict(reversed(sorted(record.items())))).encode("utf-8")


# --------------------------------------------------------------------------- §35.23: the Human / API boundary


class HumanBoundaryTests(DispositionCase):
    def test_without_confirmation_nothing_is_read_locked_or_written(self) -> None:
        target = self.reconcile_pin()
        before = tree_snapshot(self.store.root)
        tripwire = mock.Mock(side_effect=AssertionError("Project state was read before the confirmation"))
        with mock.patch.object(rd, "ProjectStore", tripwire), \
                mock.patch("workline.oplock.project_operation", tripwire), \
                mock.patch.object(gitcmd, "toplevel", tripwire), \
                mock.patch.object(MutationController, "list_records", tripwire):
            for confirmed in (False, None, 1, "yes", "True"):
                with self.subTest(confirmed=confirmed), self.assertRaises(StopError) as raised:
                    rd.dispose_recovery(self.store.root, target, REASON, confirmed=confirmed)  # type: ignore[arg-type]
                self.assertEqual(raised.exception.code, "recovery_disposition_unconfirmed")
            # not even a root that does not exist is looked at
            with self.assertRaises(StopError) as raised:
                rd.dispose_recovery(self.tmp / "nowhere", target, REASON)
            self.assertEqual(raised.exception.code, "recovery_disposition_unconfirmed")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = cli.main(["dispose-recovery", str(self.store.root), "--target", target, "--reason", REASON])
            self.assertEqual(code, 1)
            self.assertIn("STOP [recovery_disposition_unconfirmed]", output.getvalue())
        tripwire.assert_not_called()
        self.assertEqual(tree_snapshot(self.store.root), before, "no lock, record or byte appeared")

    def test_dispose_recovery_is_the_one_cli_command_the_retry_pin_exempts(self) -> None:
        self.assertEqual({c for c in commands() if re.search(FORBIDDEN_COMMAND, c)}, {"dispose-recovery"})
        help_text = io.StringIO()
        with contextlib.redirect_stdout(help_text), self.assertRaises(SystemExit):
            cli.main(["dispose-recovery", "-h"])
        text = " ".join(help_text.getvalue().split())
        for needle in ("--target", "--reason", "--confirm", "public-safe", "secret"):
            self.assertIn(needle, text)

    def test_a_missing_or_blank_reason_and_an_invalid_target_refuse_before_any_read(self) -> None:
        target = self.reconcile_pin()
        for reason in ("", "   ", "line one\nline two", None):
            self.assertRefused("recovery_disposition_reason_invalid", rd.dispose_recovery, self.store.root, target,
                               reason, confirmed=True)
        for bad in ("w_01ARZ3NDEKTSV4RRFFQ69G5FAV", "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV", target.lower(), "", "../x"):
            self.assertRefused("recovery_disposition_target_invalid", rd.dispose_recovery, self.store.root, bad,
                               REASON, confirmed=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["dispose-recovery", ".", "--target", target, "--confirm"])  # --reason is required

    def test_a_foreign_project_context_refuses_normally(self) -> None:
        target = self.reconcile_pin()
        project = self.store
        elsewhere = self.new_project("elsewhere")
        self.store = project
        before = (self.stable_tree(), self.runtime(target))
        with cwd(elsewhere.root), self.assertRaises(StopError) as raised:
            rd.dispose_recovery(project.root, target, REASON, confirmed=True)
        self.assertEqual(raised.exception.code, "foreign_project_mutation")
        self.assertEqual((self.stable_tree(), self.runtime(target)), before)
        self.assertFalse(project.locks.exists() and (project.locks / "holder.json").exists())

    def test_only_the_configured_implementation_may_run(self) -> None:
        target = self.reconcile_pin()
        other = copy_workline_root(self.tmp / "other-root")
        before = (self.stable_tree(), self.runtime(target))
        result = run_python(
            launcher_command(other, "dispose-recovery", ".", "--target", target, "--reason", REASON, "--confirm"),
            cwd=self.store.root,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("STOP [workline_implementation_mismatch]", result.stdout)
        self.assertEqual((self.stable_tree(), self.runtime(target)), before)

    def test_the_reason_is_stored_trimmed_and_the_cli_runs_the_same_operation(self) -> None:
        target = self.reconcile_pin()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(["dispose-recovery", ".", "--target", target, "--reason", f"  {REASON}  ", "--confirm"])
        self.assertEqual(code, 0, output.getvalue())
        self.assertIn(f"dispose-recovery: disposed ({self.store.root}) mutation {target}", output.getvalue())
        found = rd.read_disposition(self.store, target)
        self.assertEqual(found.reason, REASON)
        self.assertNotIn(REASON, git(self.store.root, "log", "-1", "--format=%B"), "the reason is not in the commit")
        self.assertEqual(git(self.store.root, "log", "-1", "--format=%s").strip(),
                         f"chore(workline): set aside recovery {target}")


# --------------------------------------------------------------------------- §35.24: the mutation target


class MutationTargetTests(DispositionCase):
    def test_a_pending_reconcile_required_mutation_is_disposed_and_its_record_is_left_byte_for_byte(self) -> None:
        target = self.reconcile_pin()
        before_bytes = self.runtime(target)
        project_yaml = self.store.project_yaml.read_bytes()
        base = self.head()

        result = self.dispose(target)

        self.assertEqual((result.status, result.target_kind, result.target_id), ("disposed", "mutation", target))
        self.assertTrue(result.pushed)
        self.assertEqual(self.runtime(target), before_bytes, "the target record is never edited")
        self.assertEqual(result.target_state_digest, rd.mutation_state_digest(before_bytes))
        # one commit of the record alone, published to the approved destination
        self.assertEqual(git(self.store.root, "rev-parse", "HEAD^").strip(), base)
        self.assertEqual(git(self.store.root, "diff-tree", "-r", "--no-commit-id", "--name-only", "HEAD").split(),
                         [rd.disposition_rel(target)])
        self.assertEqual(git(self.remote_path(), "rev-parse", "main").strip(), self.head())
        self.assertEqual(self.record_files(), [f"{target}.yaml"])
        self.assertEqual(self.store.project_yaml.read_bytes(), project_yaml, "an unrelated dirty path is untouched")
        self.assertIn(".workline/project.yaml", git(self.store.root, "status", "--porcelain"))
        # raw inspection still sees it; automatic discovery does not; an explicit load refuses
        raw = [r["mutation_id"] for r in MutationController(self.store).list_records() if r["status"] == "pending"]
        self.assertIn(target, raw)
        self.assertNotIn(target, [r["mutation_id"] for r in MutationController(self.store).list_pending()])
        with self.assertRaises(ReconcileRequired) as raised:
            MutationController(self.store).load(target)
        self.assertEqual(raised.exception.reason, "disposed_by_human")
        # nothing pending of the disposition itself, and its own record was cleaned up as a completed one
        self.assertEqual(MutationController(self.store).list_pending(), [])
        # RB1 status: disposed_by_human, with its detail, never completed or absent; validation passes it
        data = self.data()
        (entry,) = data["pending"]["records"]
        self.assertEqual((entry["mutation_id"], entry["classification"]), (target, status.DISPOSED_BY_HUMAN))
        self.assertEqual(entry["reason"]["code"], "disposed_by_human")
        self.assertEqual(entry["disposition"], {
            "state": "effective", "target_id": target, "path": rd.disposition_rel(target),
            "target_state_digest": rd.mutation_state_digest(before_bytes), "reason": REASON,
            "runtime_record": "present", "problem": None,
        })
        self.assertEqual([d["target_id"] for d in data["pending"]["dispositions"]], [target])
        self.assertEqual(data["pending"]["status"], "present")
        self.assertNotIn(target, [c["mutation_id"] for c in data["pending"]["closed"]], "not reported as closed")
        self.assertEqual([p for p in data["validation"]["problems"] if p["code"].startswith("recovery_disposition")], [])
        self.assertEqual(rd.namespace_problems(self.store), [])
        self.assertIn(f"Human disposition {target}: effective", status.render_human(self.model()))

    def test_a_disposed_mutation_is_never_resumed_by_its_owner_and_holds_no_other_owner_back(self) -> None:
        target = self.reconcile_pin()
        self.dispose(target)
        # its owner begins a fresh attempt instead of resuming the disposed record
        self.store.project_yaml.write_bytes(git(self.store.root, "show", "HEAD:.workline/project.yaml").encode("utf-8"))
        result = push_pin.pin_push_destination(self.store.root, [self.remote_url()])
        self.assertNotEqual(result.mutation_id, target)
        self.assertFalse(result.resumed)
        self.assertEqual(rd.mutation_target_state(self.store, target).state, rd.STATE_EFFECTIVE)
        self.assertEqual(self.data()["pending"]["records"][0]["classification"], status.DISPOSED_BY_HUMAN)

    def test_a_pending_resumable_mutation_is_refused(self) -> None:
        target = self.resumable_pin()
        found = self.assertRefused("recovery_disposition_target_ineligible", self.dispose, target)
        self.assertIn(status.PENDING_RESUMABLE, found.message)
        self.assertEqual(self.record_files(), [])

    def test_an_unknown_or_invalid_mutation_is_refused(self) -> None:
        self.store = self.new_project()
        target = self.open_start(self.store)
        found = self.assertRefused("recovery_disposition_target_ineligible", self.dispose, target)
        self.assertIn(status.UNKNOWN_OR_INVALID, found.message)

    def test_a_missing_abandoned_or_completed_mutation_is_refused(self) -> None:
        self.store = self.new_project()
        self.assertRefused("recovery_disposition_target_ineligible", self.dispose, SOME_MUTATION)
        with project_operation(self.store, "start", {}):
            mutation = MutationController(self.store).open(
                "start", {"operation": "start", "work_id": "w_01ARZ3NDEKTSV4RRFFQ69G5FAV", "mode": "single-work"},
                WriteScope(entities=("w_01ARZ3NDEKTSV4RRFFQ69G5FAV",), files=LEDGERS),
            )
            mutation.abandon()
        self.assertRefused("recovery_disposition_target_ineligible", self.dispose, mutation.id)
        path = self.store.mutations / f"{mutation.id}.yaml"
        path.write_bytes(path.read_bytes().replace(b"status: abandoned", b"status: completed"))
        self.assertRefused("recovery_disposition_target_ineligible", self.dispose, mutation.id)

    def test_another_pending_mutation_blocks_the_disposition(self) -> None:
        target = self.reconcile_pin()
        other = self.open_start(self.store)
        found = self.assertRefused("recovery_disposition_pending_operation", self.dispose, target)
        self.assertIn(other, found.message)
        self.assertEqual({r["mutation_id"] for r in MutationController(self.store).list_pending()}, {target, other})

    def test_target_bytes_changed_after_the_disposition_fail_closed(self) -> None:
        target = self.reconcile_pin()
        self.dispose(target)
        path = self.store.mutations / f"{target}.yaml"
        path.write_bytes(path.read_bytes() + b"edited_after_disposition: 1\n")
        with self.assertRaises(ReconcileRequired) as raised:
            MutationController(self.store).list_pending()
        self.assertEqual(raised.exception.reason, "recovery_disposition_invalid")
        with self.assertRaises(ReconcileRequired):
            MutationController(self.store).load(target)
        problems = [(code, message) for code, message in rd.namespace_problems(self.store)]
        self.assertEqual([code for code, _ in problems], ["recovery_disposition_conflict"])
        data = self.data()
        self.assertEqual(data["validation"]["status"], "failed")
        (entry,) = data["pending"]["records"]
        self.assertEqual(entry["classification"], status.PENDING_RECONCILE)
        self.assertEqual(entry["disposition"]["state"], "invalid")

    def test_the_runtime_record_absent_after_a_clone_or_runtime_loss_keeps_the_disposition_historical(self) -> None:
        target = self.reconcile_pin()
        self.dispose(target)
        clone = self.tmp / "clone"
        git(self.tmp, "clone", "-q", str(self.store.root), str(clone))
        for root in (clone, None):
            if root is None:  # the same working copy loses its runtime area
                (self.store.mutations / f"{target}.yaml").unlink()
                root = self.store.root
            with self.subTest(root=root.name):
                store = ProjectStore(root)
                self.assertEqual(rd.namespace_problems(store), [])
                state = rd.mutation_target_state(store, target)
                self.assertEqual((state.state, state.runtime_record), (rd.STATE_EFFECTIVE, "absent"))
                self.assertEqual(MutationController(store).list_pending(), [])
                data = self.data(root)
                (found,) = data["pending"]["dispositions"]
                self.assertEqual((found["target_id"], found["state"], found["runtime_record"]),
                                 (target, "effective", "absent"))
                self.assertEqual(data["pending"]["records"], [])
                self.assertFalse((store.mutations / f"{target}.yaml").exists(), "no record is fabricated")

    def test_explicit_load_and_open_paths_of_the_controller(self) -> None:
        target = self.reconcile_pin()
        with project_operation(self.store, rd.OWNER, {}):
            with self.assertRaises(ValidationError) as raised:
                MutationController(self.store).open(rd.OWNER, {"operation": rd.OWNER}, WriteScope(files=(rd.disposition_rel(target),)))
            self.assertEqual(raised.exception.code, "recovery_disposition_owner")
            for scope in (WriteScope(entities=("w_01ARZ3NDEKTSV4RRFFQ69G5FAV",), files=(rd.disposition_rel(target),)),
                          WriteScope(files=(rd.disposition_rel(target), ".workline/project.yaml")),
                          WriteScope(files=(".workline/project.yaml",))):
                with self.subTest(scope=scope), self.assertRaises(ValidationError):
                    rd.open_disposition_mutation(self.store, {"operation": rd.OWNER}, scope, target_mutation_id=target)
            # the target exempts only itself: without naming it, the pending pin mutation refuses the open
            with self.assertRaises(ReconcileRequired) as raised:
                rd.open_disposition_mutation(self.store, {"operation": rd.OWNER}, WriteScope(files=(rd.disposition_rel(target),)))
            self.assertEqual(raised.exception.reason, "recovery_disposition_pending_operation")
        self.assertEqual([r["owner"] for r in MutationController(self.store).list_pending()], [push_pin.OWNER])


# --------------------------------------------------------------------------- §35.12: the immutable create guards


class ControllerGuardTests(DispositionCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.controller = MutationController(self.store)

    def check(self, kind: str, path: str, owner: str, code: str) -> None:
        record = {"seq": 1, "stage": "s", "kind": kind, "payload": {"path": path, "content": "x: 1\n"}, "applied": False}
        with self.assertRaises(ValidationError) as raised:
            self.controller.validate_effect(record, [], owner)
        self.assertEqual(raised.exception.code, code, raised.exception)

    def test_only_the_disposition_owner_creates_and_only_its_exact_path(self) -> None:
        rel = rd.disposition_rel(SOME_MUTATION)
        for owner in ("start", "roadmap", "work-terminal-activation", "push-destination-pin", "review-generation"):
            for path in (rel, rel.replace("recovery", "RECOVERY"), rel.replace("recovery", "Recovery.")):
                with self.subTest(owner=owner, path=path):
                    self.check("create_file", path, owner, "recovery_disposition_owner")
        for path in (".workline/recovery/other.yaml", f".workline/recovery/dispositions/{SOME_MUTATION}.txt",
                     ".workline/recovery/dispositions/w_01ARZ3NDEKTSV4RRFFQ69G5FAV.yaml", rel.replace("recovery", "RECOVERY")):
            with self.subTest(path=path):
                self.check("create_file", path, rd.OWNER, "recovery_disposition_path")
        self.check("create_file", f".workline/review/receipts/rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV.yaml", rd.OWNER,
                   "recovery_disposition_owner")
        record = {"seq": 1, "stage": "s", "kind": "create_file", "payload": {"path": rel, "content": "x: 1\n"},
                  "applied": False}
        self.controller.validate_effect(record, [], rd.OWNER)  # the one allowed create

    def test_generic_write_file_never_reaches_the_namespace(self) -> None:
        rel = rd.disposition_rel(SOME_RUN)
        for owner in ("start", rd.OWNER, "push-destination-pin"):
            for path in (rel, rel.replace("recovery", "Recovery"), ".workline/recovery/anything.yaml"):
                with self.subTest(owner=owner, path=path):
                    self.check("write_file", path, owner, "recovery_disposition_immutable")

    def test_the_review_create_rules_are_unchanged(self) -> None:
        record = {"seq": 1, "stage": "s", "kind": "create_file",
                  "payload": {"path": ".workline/review/receipts/rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV.yaml", "content": "x"},
                  "applied": False}
        self.controller.validate_effect(record, [], "start")
        self.check("create_file", ".workline/review/activation/work-terminal-v1.yaml", "start",
                   "work_terminal_activation_owner")
        self.check("write_file", ".workline/review/receipts/rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV.yaml", "start",
                   "validation_failed")
        self.check("create_file", ".workline/works/w_01ARZ3NDEKTSV4RRFFQ69G5FAV.md", "start", "validation_failed")


# --------------------------------------------------------------------------- §35.7: the global barrier


class BarrierTests(DispositionCase):
    def test_a_pending_disposition_holds_every_other_owner_back_until_it_completes(self) -> None:
        target = self.reconcile_pin()
        with mock.patch("workline.mutation.Mutation.apply", side_effect=Crash("killed")), self.assertRaises(Crash):
            self.dispose(target)
        (own,) = [r for r in MutationController(self.store).list_pending() if r["owner"] == rd.OWNER]
        self.assertEqual([e["stage"] for e in own["effects"]], ["disposition"])
        for owner, invocation, scope in (
            ("start", {"operation": "start", "work_id": "w_01ARZ3NDEKTSV4RRFFQ69G5FAV", "mode": "single-work"},
             WriteScope(entities=("w_01ARZ3NDEKTSV4RRFFQ69G5FAV",), files=LEDGERS)),
            (push_pin.OWNER, {"operation": push_pin.OWNER}, WriteScope(files=(".workline/project.yaml",))),
            ("create-direct", {"operation": "create-direct"}, WriteScope(files=(".workline/relations/related.yaml",))),
        ):
            with self.subTest(owner=owner), project_operation(self.store, owner, {}), \
                    self.assertRaises(ReconcileRequired) as raised:
                MutationController(self.store).open(owner, invocation, scope)
            self.assertEqual(raised.exception.reason, "recovery_disposition_pending")
        # another disposition request is refused too, and leaves the pending one as it is
        with self.assertRaises(ReconcileRequired) as raised:
            self.dispose(target, "another reason entirely")
        self.assertEqual(raised.exception.reason, "recovery_disposition_conflict")
        result = self.dispose(target)  # the same request resumes and completes it
        self.assertEqual((result.status, result.mutation_id, result.resumed), ("disposed", own["mutation_id"], True))
        with project_operation(self.store, "start", {}):
            MutationController(self.store).open(
                "start", {"operation": "start", "work_id": "w_01ARZ3NDEKTSV4RRFFQ69G5FAV", "mode": "single-work"},
                WriteScope(entities=("w_01ARZ3NDEKTSV4RRFFQ69G5FAV",), files=LEDGERS),
            )


# --------------------------------------------------------------------------- §35.14 / §35.26: idempotency


class IdempotencyTests(DispositionCase):
    def test_the_same_request_is_already_disposed_and_a_conflicting_one_fails_closed(self) -> None:
        target = self.reconcile_pin()
        first = self.dispose(target)
        head, record = self.head(), (self.store.root / first.path).read_bytes()

        again = self.dispose(target, f"  {REASON} ")
        self.assertEqual((again.status, again.target_state_digest, again.mutation_id), (
            "already_disposed", first.target_state_digest, None))
        self.assertEqual(self.head(), head, "no second commit")
        self.assertEqual(self.disposition_commits(), [f"chore(workline): set aside recovery {target}"])

        self.assertRefused("recovery_disposition_conflict", self.dispose, target, "a different reason")
        # the same target, its state changed: the disposition no longer holds, so nothing reads past it
        path = self.store.mutations / f"{target}.yaml"
        path.write_bytes(path.read_bytes() + b"changed_after_disposition: 1\n")
        self.assertRefused("recovery_disposition_invalid", self.dispose, target)
        self.assertRefused("recovery_disposition_invalid", self.dispose, target, "a different reason")
        self.assertEqual(self.record_files(), [f"{target}.yaml"], "one canonical file per target")
        self.assertEqual((self.store.root / first.path).read_bytes(), record, "never overwritten, appended or chosen")
        self.assertNotIn("at:", record.decode("utf-8"))

    def test_an_uncommitted_record_no_pending_disposition_decided_is_never_adopted(self) -> None:
        target = self.reconcile_pin()
        decided = rd.Disposition(rd.KIND_MUTATION, target, rd.mutation_state_digest(self.runtime(target)), REASON)
        path = self.store.root / decided.path
        path.parent.mkdir(parents=True)
        path.write_text(rd.render(decided), encoding="utf-8")
        # written, not committed: not effective - the target is still active, and the record is not adopted
        self.assertIn(target, [r["mutation_id"] for r in MutationController(self.store).list_pending()])
        self.assertRefused("recovery_disposition_conflict", self.dispose, target)


# --------------------------------------------------------------------------- §35.18: validation


class ValidationTests(DispositionCase):
    def test_a_project_without_the_namespace_has_no_problem_and_a_broken_namespace_is_reported(self) -> None:
        self.store = self.new_project()
        self.assertEqual(rd.namespace_problems(self.store), [])
        directory = self.store.root / ".workline" / "recovery" / "dispositions"
        directory.mkdir(parents=True)
        (self.store.root / ".workline" / "recovery" / "stray.txt").write_text("x", encoding="utf-8")
        (directory / "notes.yaml").write_text("x: 1\n", encoding="utf-8")
        (directory / "w_01ARZ3NDEKTSV4RRFFQ69G5FAV.yaml").write_text("x: 1\n", encoding="utf-8")
        (directory / f"{SOME_MUTATION}.yaml").write_text("schema: nothing\n", encoding="utf-8")
        dangling = rd.Disposition(rd.KIND_REVIEW_RUN, SOME_RUN, "c" * 64, "gone")
        (directory / f"{SOME_RUN}.yaml").write_text(rd.render(dangling), encoding="utf-8")
        problems = rd.namespace_problems(self.store)
        codes = sorted(code for code, _ in problems)
        self.assertEqual(codes, ["recovery_disposition_conflict"] + ["recovery_disposition_invalid"] * 4, problems)
        self.assertTrue(any(SOME_RUN in message and "does not hold" in message for _, message in problems))
        found = [p for p in self.data()["validation"]["problems"] if p["code"].startswith("recovery_disposition")]
        self.assertEqual(len(found), 5)
        # a historical mutation disposition whose runtime record is absent is valid
        for name in ("notes.yaml", "w_01ARZ3NDEKTSV4RRFFQ69G5FAV.yaml", f"{SOME_RUN}.yaml"):
            (directory / name).unlink()
        (self.store.root / ".workline" / "recovery" / "stray.txt").unlink()
        historical = rd.Disposition(rd.KIND_MUTATION, SOME_MUTATION, "d" * 64, "historical")
        (directory / f"{SOME_MUTATION}.yaml").write_text(rd.render(historical), encoding="utf-8")
        self.assertEqual(rd.namespace_problems(self.store), [])

    def test_the_status_read_of_a_disposition_writes_nothing(self) -> None:
        target = self.reconcile_pin()
        self.dispose(target)
        data, _ = self.assertReadOnly(lambda: json.loads(status.render_json(status.build_status(self.store.root))))
        self.assertEqual(data["pending"]["records"][0]["classification"], status.DISPOSED_BY_HUMAN)
        self.assertEqual(data["schema"], "workline-status")
        self.assertEqual(data["version"], 1)


if __name__ == "__main__":
    unittest.main()
