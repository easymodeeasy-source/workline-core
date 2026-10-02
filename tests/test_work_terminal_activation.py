"""Gate 3: the Work-terminal activation producer, its owner guard, the one digest, and activation totality.

P3 F1 §8 freezes the producer: a dedicated, human-confirmed Project maintenance
operation with its own owner (``work-terminal-activation``) and its own mutation,
started only while nothing else is pending, deciding the four frozen fields from
HEAD's COMMITTED event log, committing the record in its own mutation and pushing
that commit to the approved destination. F1 §8.2 makes the owner mechanical, at
effect validation. F1 §9 freezes the digest, implemented once. F1 §10 freezes the
totality validation that Gate 3 switches on.

What these tests hold (the activated Projects here are disposable, never a real one):

* confirmation is required, and without it nothing is locked, opened or written;
* every precondition refuses before a mutation exists: not a Project, a foreign
  context, self-hosting, a pending mutation of any owner (a pending legacy START
  above all), a Review namespace that does not read canonically, detached HEAD,
  a change at the activation path, an unavailable Gate 1 or Gate 2;
* the record: exactly the frozen fields, N and the digest from the committed log
  (not the working tree), CRLF and blank lines normalized, metadata hashed;
* one commit holding the record and nothing else, pushed only to the pinned
  destination, local without a remote; no domain state touched;
* idempotence that never moves the boundary, contradictions that reconcile,
  generic recovery of an interrupted activation, and the event-log claim that
  keeps a lifecycle operation from opening beside a pending activation;
* only the activation owner creates the record, in any spelling of its
  directory; every other Review record stays owner-agnostic;
* the totality validation over synthetic states (the pending-stage allowance is
  driven by a real interrupted START in ``test_work_terminal_activation_e2e``).
"""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, WorklineTestCase, completing_executor, launcher_command, run_python, scripted_executor
from helpers import git as config_free_git
from test_review_authorization import CONSUMPTION_ID, EVENT_ID, OTHER_CONSUMPTION, RECEIPT_ID, RUN_ID, consumption_record
from test_self_hosting_guard import SelfHostingTestCase
from test_work_review_runtime import FORM_L, git, git_bytes, prefix_digest

from workline import gitcmd, gitops
from workline import start as st
from workline import start_review
from workline import work_terminal_activation as wta
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.mutation import Effect, Mutation, MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import activation as work_activation
from workline.review import paths as review_paths
from workline.review import records, serialize
from workline.review import validate as review_validate
from workline.review.store import ReviewStore
from workline.review.validate import validate_review
from workline.store import ACTIVATION_OWNERS, PIN_OWNERS, ProjectStore
from workline.validate import validate_project

REL = review_paths.WORK_TERMINAL_ACTIVATION_REL
EVENTS = ".workline/events/events.jsonl"
WORK = "w_01ARZ3NDEKTSV4RRFFQ69G5FAV"
TOTALITY = (
    review_validate.ACTIVATION_PREFIX_MISMATCH,
    review_validate.COMPLETION_MARKER_INVALID,
    review_validate.COMPLETION_MARKER_CONTRADICTION,
    review_validate.COMPLETION_UNCONSUMED,
    review_validate.CONSUMPTION_UNBOUND,
)


class Crash(BaseException):
    """A process death at a chosen instant."""


def completion(event_id: str = EVENT_ID, entity: str = WORK, **metadata: object) -> dict:
    """A review-v1 work_completed record: the lifecycle fields and exactly the frozen metadata."""
    return {
        "id": event_id, "type": "work_completed", "entity": entity, "at": "2026-10-01T00:00:00Z",
        "operation_contract": "review-v1", "review_receipt_id": RECEIPT_ID, "review_run_id": RUN_ID,
        "review_generation": 3, **metadata,
    }


def legacy_completion(event_id: str, entity: str = WORK) -> dict:
    return {"id": event_id, "type": "work_completed", "entity": entity, "at": "2026-10-01T00:00:00Z"}


class ActivationCase(WorklineTestCase):
    """A disposable established Project with a committed Git identity and the canonical form-L rule."""

    remote = False
    pin = True

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=self.remote, pin=self.pin)
        self.root = self.store.root
        git(self.root, "config", "user.name", "Real Person")
        git(self.root, "config", "user.email", "real@proj")
        self.commit_file(".gitattributes", FORM_L, "form L")

    # --- fixtures ---------------------------------------------------------------
    def commit_file(self, path: str, data: bytes, message: str = "seed") -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        config_free_git(self.root, "add", "--", path)
        config_free_git(self.root, "commit", "-q", "-m", message, "--no-verify")

    def with_works(self) -> dict[str, str]:
        roadmap = self.simple_roadmap(self.store)
        entry = self.simple_entry(self.store, roadmap.phase_ids["a"], {"w1": "W1 done", "w2": "W2 done"})
        return dict(entry.work_ids)

    def with_events(self) -> dict[str, str]:
        """Works, and one of them completed by a legacy START, so the committed event log holds Events."""
        works = self.with_works()
        done = st.start(self.store, works["w2"], "single-work", completing_executor(self.store))
        self.assertEqual(done.status, "completed")
        self.assertTrue(work_activation.parse_event_log(self.committed_log()))
        return works

    def activate(self) -> wta.ActivationResult:
        return wta.activate_work_terminal_review(self.root, confirmed=True)

    def refused(self, code: str, call=None) -> StopError:
        with self.assertRaises(StopError) as raised:
            (call or self.activate)()
        self.assertEqual(raised.exception.code, code, raised.exception)
        return raised.exception

    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD")

    def pending(self) -> list[dict]:
        return MutationController(self.store).list_pending()

    def records_seen(self) -> list[tuple[str, str]]:
        return [(r["mutation_id"], r["status"]) for r in MutationController(self.store).list_records()]

    def committed_log(self, commit: str = "HEAD") -> bytes:
        return git_bytes(self.root, "show", f"{commit}:{EVENTS}")

    def record_at(self, commit: str) -> dict:
        data, _ = serialize.parse_canonical(git_bytes(self.root, "show", f"{commit}:{REL}"), "activation")
        return data

    def assertNothingBegun(self, head: str, seen: list[tuple[str, str]]) -> None:
        self.assertEqual(self.head(), head)
        self.assertEqual(self.records_seen(), seen)
        self.assertFalse((self.root / REL).exists())

    def append_events(self, *events: dict) -> None:
        log = self.store.events_jsonl
        data = log.read_bytes()
        if data and not data.endswith(b"\n"):
            data += b"\n"
        log.write_bytes(data + b"".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
                                        for e in events))

    def put_record(self, relative: str, record: dict) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(serialize.canonical_bytes(record))

    def totality(self) -> list[str]:
        return [problem.code for problem in validate_review(self.store) if problem.code in TOTALITY]


# --------------------------------------------------------------------------- 1, 2: human confirmation


class ConfirmationTests(ActivationCase):
    def test_nothing_but_an_explicit_true_confirms(self) -> None:
        head, seen = self.head(), self.records_seen()
        with mock.patch.object(wta, "project_operation", side_effect=AssertionError("the lock was taken")):
            for value in (False, None, 1, "yes", "True", object()):
                with self.subTest(confirmed=value):
                    self.refused("work_terminal_activation_unconfirmed",
                                 lambda: wta.activate_work_terminal_review(self.root, confirmed=value))
            self.refused("work_terminal_activation_unconfirmed", lambda: wta.activate_work_terminal_review(self.root))
        self.assertNothingBegun(head, seen)
        self.assertEqual(self.pending(), [])

    def test_confirmation_is_refused_before_the_project_is_even_looked_at(self) -> None:
        """Not an absent record, not the Project's state, not the caller: only the explicit input confirms."""
        missing = self.tmp / "nowhere"
        self.refused("work_terminal_activation_unconfirmed", lambda: wta.activate_work_terminal_review(missing))


class CliTests(ActivationCase):
    """The canonical operator entry: the launcher's ``activate-work-terminal-review`` subcommand."""

    def run_cli(self, *args: str):
        return run_python(launcher_command(WORKLINE_ROOT, "activate-work-terminal-review", ".", *args), cwd=self.root)

    def test_the_subcommand_requires_its_confirmation_flag_and_then_activates_once(self) -> None:
        head, seen = self.head(), self.records_seen()
        refused = self.run_cli()
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        self.assertIn("STOP [work_terminal_activation_unconfirmed]", refused.stdout)
        self.assertNothingBegun(head, seen)
        done = self.run_cli("--confirm")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("activate-work-terminal-review: activated", done.stdout)
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), wta.ACTIVATION_COMMIT_MESSAGE)
        again = self.run_cli("--confirm")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn("activate-work-terminal-review: already_activated", again.stdout)


# --------------------------------------------------------------------------- 3 ... 10: preconditions


class PreconditionTests(ActivationCase):
    def test_only_an_established_project(self) -> None:
        plain = self.new_dir("plain")
        config_free_git(plain, "init", "-q", "-b", "main")
        self.refused("not_a_project", lambda: wta.activate_work_terminal_review(plain, confirmed=True))
        nested = self.root / "sub"
        nested.mkdir()
        self.refused("not_a_project", lambda: wta.activate_work_terminal_review(nested, confirmed=True))

    def test_a_foreign_project_context_is_refused_by_the_existing_guard(self) -> None:
        other = self.new_project("other")
        self.enter(self.root)
        head = git(other.root, "rev-parse", "HEAD")
        self.refused("foreign_project_mutation", lambda: wta.activate_work_terminal_review(other.root, confirmed=True))
        self.assertEqual(git(other.root, "rev-parse", "HEAD"), head)
        self.assertFalse((other.root / REL).exists())

    def test_another_pending_mutation_of_any_owner_refuses(self) -> None:
        with project_operation(self.store, "push-destination-pin", {}):
            MutationController(self.store).open(
                "push-destination-pin", {"operation": "push-destination-pin", "probe": True},
                WriteScope(files=(".workline/project.yaml",)),
            )
        head, seen = self.head(), self.records_seen()
        error = self.refused("pending_operation")
        self.assertIn("push-destination-pin", error.message)
        self.assertNothingBegun(head, seen)

    def test_a_pending_legacy_start_is_never_surprised(self) -> None:
        works = self.with_works()
        waiting = st.start(self.store, works["w1"], "single-work", scripted_executor({"*": [st.QuestionWait("hold on")]}))
        self.assertEqual(waiting.status, "question_wait")
        (legacy,) = self.pending()
        head, seen = self.head(), self.records_seen()
        self.refused("pending_operation")
        self.assertNothingBegun(head, seen)
        self.assertEqual(self.pending(), [legacy], "the pending START is left exactly as it was")
        # it finishes as the legacy START it always was, and only then may the Project be activated
        done = st.start(self.store, works["w1"], "single-work", completing_executor(self.store))
        self.assertEqual(done.status, "completed")
        self.assertNotIn("review_contract", legacy["invocation"])
        self.assertEqual(self.activate().status, "activated")

    def test_a_review_namespace_that_does_not_read_canonically_refuses(self) -> None:
        (self.root / review_paths.REVIEW_DIR / "unknown").mkdir(parents=True)
        head, seen = self.head(), self.records_seen()
        self.refused("review_namespace_unreadable")
        self.assertNothingBegun(head, seen)

    def test_a_review_v1_completion_in_history_is_never_activation(self) -> None:
        """No retroactive inference: a marker without an activation contradicts the Project and refuses."""
        self.append_events(completion())
        config_free_git(self.root, "commit", "-q", "-am", "a stray marker", "--no-verify")
        self.refused("review_namespace_unreadable")
        self.assertFalse((self.root / REL).exists())

    def test_detached_head_refuses(self) -> None:
        config_free_git(self.root, "checkout", "-q", "--detach")
        head, seen = self.head(), self.records_seen()
        self.refused("detached_head")
        self.assertNothingBegun(head, seen)

    def test_a_change_at_the_activation_path_refuses(self) -> None:
        record = records.WorkTerminalActivation("review-v1", 0, hashlib.sha256(b"").hexdigest(), self.head())
        self.commit_file(REL, serialize.canonical_bytes(record.to_record()), "a hand-made activation")
        (self.root / REL).unlink()
        head, seen = self.head(), self.records_seen()
        self.refused("dirty_overlap")
        self.assertEqual((self.head(), self.records_seen()), (head, seen))

    def test_an_unavailable_gate_makes_the_producer_unavailable(self) -> None:
        head, seen = self.head(), self.records_seen()
        stripped = lambda event: json.dumps({k: event.to_record()[k] for k in ("id", "type", "entity", "at")},
                                            ensure_ascii=False, separators=(",", ":"))
        with mock.patch.object(wta, "render_event_line", side_effect=stripped):
            self.assertIn("Gate 1", self.refused("work_terminal_activation_unavailable").message)
        with mock.patch.object(records, "CONSUMPTION_ARTIFACT_KINDS", ("result_commit",)):
            self.assertIn("Gate 2", self.refused("work_terminal_activation_unavailable").message)
        self.assertNothingBegun(head, seen)

    def test_the_gates_hold_in_this_implementation(self) -> None:
        wta.require_prerequisite_gates()


class UnpinnedRemoteTests(ActivationCase):
    remote = True
    pin = False

    def test_a_remote_without_an_approved_destination_stops_before_anything(self) -> None:
        head, seen = self.head(), self.records_seen()
        self.refused("push_destination_unpinned")
        self.assertNothingBegun(head, seen)
        self.assertIsNone(self.store.read_push_pin(), "activation never pins a destination")


class SelfHostedActivationTests(SelfHostingTestCase):
    def test_self_hosting_stays_refused(self) -> None:
        store, _ = self.self_hosted_project()
        self.assertEveryAttemptStops(
            store, {"work-terminal activation": lambda: wta.activate_work_terminal_review(store.root, confirmed=True)}
        )


# --------------------------------------------------------------------------- 11 ... 18, 21, 23, 26: the record


class RecordTests(ActivationCase):
    def test_the_record_is_the_four_frozen_fields_decided_from_head(self) -> None:
        self.with_events()
        base = self.head()
        count, digest = prefix_digest(self.committed_log())
        captured: list[dict] = []
        real = Mutation.complete

        def spy(mutation: Mutation) -> None:
            captured.append(json.loads(json.dumps(mutation.record)))
            real(mutation)

        with mock.patch.object(Mutation, "complete", spy):
            result = self.activate()
        k = self.head()
        self.assertEqual((result.status, result.head, result.resumed, result.pushed), ("activated", k, False, False))
        self.assertEqual(self.record_at(k), {
            "schema": "review-work-terminal-activation", "version": 1, "operation_contract": "review-v1",
            "legacy_event_count": count, "legacy_event_prefix_sha256": digest, "activation_base_head": base,
        })
        self.assertGreater(count, 0)
        self.assertEqual((result.legacy_event_count, result.legacy_event_prefix_sha256, result.activation_base_head),
                         (count, digest, base))
        # one commit on the base, holding the record and nothing else, under the stable message
        self.assertEqual(git(self.root, "rev-parse", f"{k}^"), base)
        self.assertEqual(git(self.root, "diff-tree", "-r", "--no-commit-id", "--name-only", k), REL)
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", k), wta.ACTIVATION_COMMIT_MESSAGE)
        self.assertEqual(wta.ACTIVATION_COMMIT_MESSAGE, "chore(workline): activate review-v1 Work terminalization")
        # its own owner and mutation: one create of the record, then the ordinary commit, no push without a remote
        (record,) = captured
        self.assertEqual(record["owner"], "work-terminal-activation")
        self.assertEqual(record["invocation"],
                         {"operation": "work-terminal-activation", "project_root": str(self.root.resolve())})
        self.assertEqual([(e["stage"], e["kind"]) for e in record["effects"]],
                         [("activation", "create_file"), ("commit", "git_commit")])
        self.assertNotIn("base", record["effects"][0]["payload"], "an immutable create carries no base")
        self.assertNotIn("mode", record["effects"][1]["payload"], "the ordinary infrastructure commit, not a Work commit")
        self.assertEqual(self.pending(), [])
        self.assertEqual(validate_project(self.store), [])

    def test_the_committed_event_log_is_the_authority_never_the_working_tree(self) -> None:
        self.with_events()
        count, digest = prefix_digest(self.committed_log())
        events = self.store.events_jsonl.read_bytes().decode("utf-8").splitlines()
        extra = json.loads(events[-1])
        extra["id"] = "evt_01ARZ3NDEKTSV4RRFFQ69G5FAZ"
        self.append_events(extra)
        result = self.activate()
        self.assertEqual((result.legacy_event_count, result.legacy_event_prefix_sha256), (count, digest))
        self.assertEqual(len(work_activation.parse_event_log(self.store.events_jsonl.read_bytes())), count + 1)

    def test_crlf_and_blank_physical_lines_do_not_change_the_digest(self) -> None:
        self.with_events()
        count, digest = prefix_digest(self.committed_log())
        lines = [line for line in self.committed_log().decode("utf-8").split("\n") if line.strip()]
        self.commit_file(EVENTS, ("\r\n\r\n".join(lines) + "\r\n\r\n").encode("utf-8"), "CRLF and blank lines")
        self.assertIn(b"\r\n\r\n", self.committed_log())
        result = self.activate()
        self.assertEqual((result.legacy_event_count, result.legacy_event_prefix_sha256), (count, digest))

    def test_event_metadata_is_part_of_the_digest(self) -> None:
        self.with_events()
        plain_count, plain_digest = prefix_digest(self.committed_log())
        lines = [json.loads(line) for line in self.committed_log().decode("utf-8").splitlines() if line.strip()]
        lines[0]["carried_note"] = {"kept": ["as", "written"]}
        self.commit_file(EVENTS, b"".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
                                          for e in lines), "metadata on an Event")
        count, digest = prefix_digest(self.committed_log())
        result = self.activate()
        self.assertEqual((result.legacy_event_count, result.legacy_event_prefix_sha256), (count, digest))
        self.assertEqual(count, plain_count)
        self.assertNotEqual(digest, plain_digest)

    def test_activation_touches_no_domain_state(self) -> None:
        self.with_events()
        before = {path: (self.root / path).read_bytes() for path in
                  (EVENTS, ".workline/relations/roadmap.yaml", ".workline/relations/related.yaml")}
        entities = sorted(p.relative_to(self.root).as_posix() for p in (self.root / ".workline").rglob("*.md"))
        base = self.head()
        self.activate()
        self.assertEqual(git(self.root, "diff", "--name-only", base, "HEAD"), REL)
        self.assertEqual({path: (self.root / path).read_bytes() for path in before}, before)
        self.assertEqual(sorted(p.relative_to(self.root).as_posix() for p in (self.root / ".workline").rglob("*.md")),
                         entities)


class RemoteRecordTests(ActivationCase):
    remote = True

    def test_the_activation_commit_is_pushed_to_the_pinned_destination_only(self) -> None:
        captured: list[dict] = []
        real = Mutation.complete

        def spy(mutation: Mutation) -> None:
            captured.append(json.loads(json.dumps(mutation.record)))
            real(mutation)

        with mock.patch.object(Mutation, "complete", spy):
            result = self.activate()
        self.assertTrue(result.pushed)
        self.assertEqual(git(self.remote_path(), "rev-parse", "main"), result.head)
        (record,) = captured
        (push,) = [e for e in record["effects"] if e["kind"] == "git_push"]
        self.assertEqual((push["payload"]["remote"], push["payload"]["locator"]), ("origin", self.remote_url()))
        self.assertEqual(push["payload"]["branch"], "main")
        self.assertEqual(self.store.read_push_pin().allowed_urls, (self.remote_url(),), "the pin is unchanged")


# --------------------------------------------------------------------------- 24, 25: one activation per Project


class IdempotenceTests(ActivationCase):
    def test_an_activated_project_answers_already_activated_and_the_boundary_never_moves(self) -> None:
        works = self.with_events()
        first = self.activate()
        data = (self.root / REL).read_bytes()
        done = st.start(self.store, works["w1"], "single-work", completing_executor(self.store))
        self.assertEqual(done.status, "completed")
        head, seen = self.head(), self.records_seen()
        again = self.activate()
        self.assertEqual(again.status, "already_activated")
        self.assertEqual(
            (again.legacy_event_count, again.legacy_event_prefix_sha256, again.activation_base_head),
            (first.legacy_event_count, first.legacy_event_prefix_sha256, first.activation_base_head),
        )
        self.assertLess(again.legacy_event_count, len(work_activation.parse_event_log(self.committed_log())))
        self.assertEqual((self.head(), self.records_seen(), (self.root / REL).read_bytes()), (head, seen, data))
        self.assertIsNone(again.mutation_id)

    def test_a_working_tree_record_that_is_not_the_committed_one_reconciles(self) -> None:
        self.activate()
        changed = records.WorkTerminalActivation("review-v1", 5, "b" * 64, "c" * 40)
        self.put_record(REL, changed.to_record())
        with self.assertRaises(ReconcileRequired):
            self.activate()
        self.assertEqual((self.root / REL).read_bytes(), serialize.canonical_bytes(changed.to_record()))

    def test_an_activation_whose_prefix_no_longer_reproduces_reconciles(self) -> None:
        self.with_events()
        self.activate()
        lines = [json.loads(line) for line in self.committed_log().decode("utf-8").splitlines() if line.strip()]
        lines[0]["at"] = "1999-01-01T00:00:00Z"
        self.commit_file(EVENTS, b"".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
                                          for e in lines), "rewrite a pre-activation Event")
        head = self.head()
        with self.assertRaises(ReconcileRequired) as raised:
            self.activate()
        self.assertIn("no longer reproduces", str(raised.exception))
        self.assertEqual(self.head(), head)

    def test_a_malformed_or_unknown_record_fails_closed_through_the_reader(self) -> None:
        for name, record in (
            ("malformed", {"schema": records.SCHEMA_ACTIVATION, "version": records.VERSION}),
            ("unknown contract", {**records.WorkTerminalActivation("review-v1", 0, "a" * 64, "b" * 40).to_record(),
                                  "operation_contract": "review-v2"}),
            ("unknown version", {**records.WorkTerminalActivation("review-v1", 0, "a" * 64, "b" * 40).to_record(),
                                 "version": 2}),
        ):
            with self.subTest(name):
                self.put_record(REL, record)
                with self.assertRaises(ValidationError):
                    self.activate()
                self.assertEqual(self.pending(), [])

    def test_an_uncommitted_record_is_never_adopted(self) -> None:
        record = records.WorkTerminalActivation("review-v1", 0, hashlib.sha256(b"").hexdigest(), self.head())
        self.put_record(REL, record.to_record())
        head = self.head()
        with self.assertRaises(ReconcileRequired) as raised:
            self.activate()
        self.assertIn("never adopted", str(raised.exception))
        self.assertEqual((self.head(), self.pending()), (head, []))


# --------------------------------------------------------------------------- 19: generic recovery of its own mutation


class InterruptionTests(ActivationCase):
    def setUp(self) -> None:
        super().setUp()
        self.works = self.with_works()

    def interrupted(self) -> dict:
        base = self.head()
        with mock.patch.object(gitops, "finalize", side_effect=Crash):
            with self.assertRaises(Crash):
                self.activate()
        (record,) = self.pending()
        self.assertEqual(record["owner"], wta.OWNER)
        self.assertTrue((self.root / REL).is_file(), "the create applied; the commit never ran")
        self.assertEqual(self.head(), base)
        return record

    def test_an_interrupted_activation_resumes_by_its_own_record_and_commits_once(self) -> None:
        record = self.interrupted()
        base = record["effects"][0]
        decided = json.loads(json.dumps(base["payload"]["content"]))
        result = self.activate()
        self.assertEqual((result.status, result.resumed, result.mutation_id), ("activated", True, record["mutation_id"]))
        self.assertEqual(git_bytes(self.root, "show", f"HEAD:{REL}").decode("utf-8"), decided)
        self.assertEqual(git(self.root, "rev-list", "--count", f"{result.activation_base_head}..HEAD"), "1")
        self.assertEqual(self.pending(), [])

    def test_a_record_changed_while_interrupted_is_never_overwritten(self) -> None:
        self.interrupted()
        tampered = serialize.canonical_bytes(records.WorkTerminalActivation("review-v1", 1, "d" * 64, "e" * 40).to_record())
        (self.root / REL).write_bytes(tampered)
        with self.assertRaises(ReconcileRequired):
            self.activate()
        self.assertEqual((self.root / REL).read_bytes(), tampered)
        self.assertEqual(len(self.pending()), 1)

    def test_no_lifecycle_operation_opens_beside_a_pending_activation(self) -> None:
        record = self.interrupted()
        head = self.head()
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.works["w1"], "single-work", completing_executor(self.store))
        self.assertIn(record["mutation_id"], str(raised.exception))
        self.assertEqual(self.head(), head)
        self.assertEqual(self.activate().status, "activated")
        self.assertEqual(st.start(self.store, self.works["w1"], "single-work", completing_executor(self.store)).status,
                         "completed")

    def test_another_pending_mutation_keeps_the_interrupted_activation_waiting(self) -> None:
        own = self.interrupted()
        with project_operation(self.store, "push-destination-pin", {}):
            MutationController(self.store).open(
                "push-destination-pin", {"operation": "push-destination-pin", "probe": True},
                WriteScope(files=(".workline/project.yaml",)),
            )
        self.refused("pending_operation")
        self.assertIn(own["mutation_id"], [r["mutation_id"] for r in self.pending()])


class RemoteInterruptionTests(ActivationCase):
    remote = True

    def test_an_activation_interrupted_before_its_push_publishes_that_commit_on_resume(self) -> None:
        with mock.patch.object(gitcmd, "push", side_effect=Crash):
            with self.assertRaises(Crash):
                self.activate()
        local = self.head()
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), wta.ACTIVATION_COMMIT_MESSAGE)
        self.assertNotEqual(git(self.remote_path(), "rev-parse", "--verify", "-q", "refs/heads/main", check=False), local)
        result = self.activate()
        self.assertEqual((result.status, result.resumed, result.head), ("activated", True, local))
        self.assertEqual(git(self.remote_path(), "rev-parse", "main"), local)


# --------------------------------------------------------------------------- 20: the owner guard


class OwnerGuardTests(ActivationCase):
    CONTENT = serialize.canonical_text(records.WorkTerminalActivation("review-v1", 0, "a" * 64, "b" * 40).to_record())

    def record_create(self, owner: str, path: str) -> list[dict]:
        """Record one create under ``owner``; what reached the durable record is kept in ``self.durable``."""
        controller = MutationController(self.store)
        with project_operation(self.store, owner, {}):
            mutation = controller.open(owner, {"operation": "guard-probe", "path": path}, WriteScope(files=(path,)))
            try:
                mutation.add_effects("probe", [Effect.create_file(path, self.CONTENT)])
                return list(mutation.effects)
            finally:
                self.durable = json.loads(json.dumps(controller.load(mutation.id).record))
                controller.intent_path(mutation.id).unlink()

    def test_the_allowlist_is_the_activation_owner_alone(self) -> None:
        self.assertEqual(ACTIVATION_OWNERS, ("work-terminal-activation",))
        self.assertEqual(wta.OWNER, ACTIVATION_OWNERS[0])
        self.assertNotIn(wta.OWNER, PIN_OWNERS)

    def test_no_other_owner_records_the_activation_create(self) -> None:
        for owner in ("start", "roadmap", "create-direct", "push-destination-pin", "bootstrap-backfill",
                      "review-generation", "some-maintenance"):
            with self.subTest(owner=owner):
                with self.assertRaises(ValidationError) as raised:
                    self.record_create(owner, REL)
                self.assertEqual(raised.exception.code, "work_terminal_activation_owner")
                self.assertEqual(self.durable["effects"], [], "refused before the effect was written into the record")
        self.assertFalse((self.root / REL).exists())
        self.assertEqual(MutationController(self.store).list_records(), [])

    def test_every_spelling_of_the_activation_directory_is_guarded(self) -> None:
        for path in (".workline/review/ACTIVATION/work-terminal-v1.yaml", ".workline/review/Activation/WORK-TERMINAL-V1.yaml",
                     ".workline/review/activation/other.yaml", ".workline/review/activation/nested/x.yaml"):
            with self.subTest(path=path):
                with self.assertRaises(ValidationError) as raised:
                    self.record_create("start", path)
                self.assertEqual(raised.exception.code, "work_terminal_activation_owner")

    def test_the_activation_owner_creates_the_frozen_name_and_no_other(self) -> None:
        effects = self.record_create(wta.OWNER, REL)
        self.assertEqual([(e["kind"], e["payload"]["path"]) for e in effects], [("create_file", REL)])
        for path in (".workline/review/activation/other.yaml", ".workline/review/ACTIVATION/work-terminal-v1.yaml"):
            with self.subTest(path=path), self.assertRaises(ValidationError) as raised:
                self.record_create(wta.OWNER, path)
            self.assertEqual(raised.exception.code, "work_terminal_activation_owner")

    def test_every_other_review_record_stays_owner_agnostic(self) -> None:
        for path in (review_paths.receipt_rel(RECEIPT_ID), review_paths.consumption_rel(CONSUMPTION_ID)):
            with self.subTest(path=path):
                effects = self.record_create("start", path)
                self.assertEqual([e["payload"]["path"] for e in effects], [path])


# --------------------------------------------------------------------------- F1 §9: one digest implementation


class DigestTests(unittest.TestCase):
    LINES = [
        {"id": "evt_01ARZ3NDEKTSV4RRFFQ69G5FA1", "type": "work_started", "entity": WORK, "at": "2026-01-01T00:00:00Z"},
        {"id": "evt_01ARZ3NDEKTSV4RRFFQ69G5FA2", "type": "work_target_added", "entity": WORK, "at": "2026-01-01T00:00:01Z",
         "note": "日本語"},
    ]

    def log(self, separator: bytes = b"\n", blank: bool = False) -> bytes:
        rendered = [json.dumps(line, ensure_ascii=False, separators=(",", ":")).encode("utf-8") for line in self.LINES]
        joined = (separator + separator).join(rendered) if blank else separator.join(rendered)
        return joined + separator

    def test_parsing_ignores_line_ends_and_blank_lines_and_keeps_metadata(self) -> None:
        expected = [dict(line) for line in self.LINES]
        for data in (self.log(), self.log(b"\r\n"), self.log(b"\r"), self.log(b"\n", blank=True), self.log(b"\r\n", blank=True)):
            with self.subTest(data=data[:24]):
                self.assertEqual(work_activation.parse_event_log(data), expected)

    def test_the_digest_is_the_frozen_canonical_form(self) -> None:
        canonical = b"".join(
            json.dumps(line, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
            for line in self.LINES
        )
        records_ = work_activation.parse_event_log(self.log(b"\r\n", blank=True))
        self.assertEqual(work_activation.prefix_digest(records_, 2), hashlib.sha256(canonical).hexdigest())
        self.assertEqual(work_activation.prefix_digest(records_, 0), hashlib.sha256(b"").hexdigest())
        self.assertEqual(work_activation.DIGEST_ALGORITHM, "work-terminal-activation-digest-v1")

    def test_unprovable_is_never_a_digest(self) -> None:
        records_ = work_activation.parse_event_log(self.log())
        for count in (3, -1, True, "1"):
            with self.subTest(count=count):
                self.assertIsNone(work_activation.prefix_digest(records_, count))
        self.assertIsNone(work_activation.prefix_digest([{**self.LINES[0], "x": float("nan")}], 1))
        for data in (b"\xff\n", b"{not json}\n", b'{"id": "evt_x"}\n', b"[1, 2]\n"):
            with self.subTest(data=data):
                self.assertIsNone(work_activation.parse_event_log(data))

    def test_producer_start_entry_proofs_and_validation_share_the_one_implementation(self) -> None:
        start_source = inspect.getsource(start_review)
        self.assertFalse(hasattr(start_review, "activation_prefix_digest"))
        self.assertNotIn("hashlib", start_source)
        self.assertIn("work_activation.committed_prefix_digest(git, head, record.legacy_event_count)",
                      inspect.getsource(start_review.require_activation))
        self.assertIn("work_activation.committed_prefix_digest(git, at.commit, found.legacy_event_count)",
                      inspect.getsource(start_review._activation_at))
        decide = inspect.getsource(wta._decide)
        self.assertIn("work_activation.committed_event_records(git, head)", decide)
        self.assertIn("work_activation.prefix_digest(events, len(events))", decide)
        self.assertIn("work_activation.prefix_digest(events, count)", inspect.getsource(review_validate.activation_problems))
        self.assertIn("work_activation.parse_event_log(data)", inspect.getsource(review_validate._event_log))
        for module in (wta, start_review, review_validate):
            with self.subTest(module=module.__name__):
                self.assertNotIn("serialize.digest(events", inspect.getsource(module))


# --------------------------------------------------------------------------- F1 §10: totality, synthetic states


class TotalityTests(ActivationCase):
    def test_no_activation_classifies_nothing_by_position_and_refuses_a_marker(self) -> None:
        self.append_events(legacy_completion("evt_01ARZ3NDEKTSV4RRFFQ69G5FA3"))
        self.put_record(review_paths.consumption_rel(CONSUMPTION_ID), consumption_record())
        self.assertEqual(self.totality(), [], "unactivated: valid, and no Consumption totality is attempted")
        self.append_events(completion())
        self.assertEqual(self.totality(), [review_validate.COMPLETION_MARKER_CONTRADICTION])

    def test_below_the_boundary_is_legacy_and_needs_nothing(self) -> None:
        works = self.with_works()
        self.assertEqual(st.start(self.store, works["w1"], "single-work", completing_executor(self.store)).status,
                         "completed")
        result = self.activate()
        self.assertGreater(result.legacy_event_count, 0)
        self.assertEqual(validate_project(self.store), [])

    def test_an_unmarked_completion_after_the_boundary_is_legacy(self) -> None:
        self.activate()
        self.append_events(legacy_completion("evt_01ARZ3NDEKTSV4RRFFQ69G5FA3"))
        self.assertEqual(self.totality(), [])

    def test_a_review_v1_completion_needs_exactly_one_matching_consumption(self) -> None:
        self.activate()
        self.append_events(completion())
        self.assertEqual(self.totality(), [review_validate.COMPLETION_UNCONSUMED])
        self.put_record(review_paths.consumption_rel(CONSUMPTION_ID), consumption_record())
        self.assertEqual(self.totality(), [])
        for name, value in (("receipt_id", "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAW"), ("review_run_id", "rr_01ARZ3NDEKTSV4RRFFQ69G5FAW"),
                            ("review_generation", 4), ("target_identity", "w_01ARZ3NDEKTSV4RRFFQ69G5FAW")):
            with self.subTest(field=name):
                self.put_record(review_paths.consumption_rel(CONSUMPTION_ID), consumption_record(**{name: value}))
                self.assertEqual(self.totality(), [review_validate.COMPLETION_MARKER_CONTRADICTION])

    def test_an_unknown_or_malformed_marker_is_invalid_never_legacy(self) -> None:
        self.activate()
        for name, event in (
            ("unknown marker", completion(operation_contract="review-v2")),
            ("Review metadata without the marker", {k: v for k, v in completion().items() if k != "operation_contract"}),
            ("an extra key", completion(review_extra="x")),
            ("a malformed receipt", completion(review_receipt_id="not-an-id")),
            ("a boolean generation", completion(review_generation=True)),
        ):
            with self.subTest(name):
                log = self.store.events_jsonl.read_bytes()
                self.append_events(event)
                self.assertEqual(self.totality(), [review_validate.COMPLETION_MARKER_INVALID])
                self.store.events_jsonl.write_bytes(log)

    def test_a_consumption_without_a_review_v1_completion_is_unbound(self) -> None:
        self.activate()
        self.put_record(review_paths.consumption_rel(CONSUMPTION_ID), consumption_record())
        self.assertEqual(self.totality(), [review_validate.CONSUMPTION_UNBOUND], "its event is absent")
        self.append_events(legacy_completion(EVENT_ID))
        self.assertEqual(self.totality(), [review_validate.CONSUMPTION_UNBOUND], "its event is a legacy completion")

    def test_two_consumptions_of_one_completion_are_a_conflict(self) -> None:
        self.activate()
        self.append_events(completion())
        self.put_record(review_paths.consumption_rel(CONSUMPTION_ID), consumption_record())
        self.put_record(review_paths.consumption_rel(OTHER_CONSUMPTION),
                        consumption_record(consumption_id=OTHER_CONSUMPTION, receipt_id="rcp_01ARZ3NDEKTSV4RRFFQ69G5FAW"))
        self.assertIn("review_consumption_conflict", [p.code for p in validate_review(self.store)])

    def test_a_pre_activation_event_is_never_review_v1(self) -> None:
        self.append_events(completion())
        config_free_git(self.root, "commit", "-q", "-am", "a marked event before the boundary", "--no-verify")
        count, digest = prefix_digest(self.committed_log())
        record = records.WorkTerminalActivation("review-v1", count, digest, self.head())
        self.commit_file(REL, serialize.canonical_bytes(record.to_record()), "a hand-made activation (fixture)")
        self.put_record(review_paths.consumption_rel(CONSUMPTION_ID), consumption_record())
        codes = self.totality()
        self.assertIn(review_validate.COMPLETION_MARKER_CONTRADICTION, codes)
        self.assertIn(review_validate.CONSUMPTION_UNBOUND, codes)

    def test_a_malformed_activation_never_falls_back_to_legacy(self) -> None:
        self.activate()
        self.append_events(completion())
        self.put_record(REL, {"schema": records.SCHEMA_ACTIVATION, "version": records.VERSION})
        codes = [p.code for p in validate_review(self.store)]
        self.assertIn("review_record_invalid", codes)
        self.assertNotEqual(codes, [])

    def test_a_prefix_mismatch_never_falls_back_to_legacy(self) -> None:
        self.with_events()
        self.activate()
        self.append_events(completion())
        lines = self.store.events_jsonl.read_bytes().decode("utf-8").splitlines()
        first = json.loads(lines[0])
        first["at"] = "1999-01-01T00:00:00Z"
        lines[0] = json.dumps(first, ensure_ascii=False, separators=(",", ":"))
        self.store.events_jsonl.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        self.assertEqual(self.totality(), [review_validate.ACTIVATION_PREFIX_MISMATCH], "and nothing after it is classified")

    def test_the_committed_proof_reader_is_not_given_the_working_tree_pass_either(self) -> None:
        """The committed-authority check belongs to the Project's activation pass, never to one commit's reader."""
        self.assertNotIn("current_activation", inspect.getsource(review_validate.review_problems))
        self.assertIn("current_activation", inspect.getsource(review_validate._committed_activation))

    def test_the_committed_proof_reader_is_not_given_the_working_tree_pass(self) -> None:
        """``review_problems`` is what C-2 proofs read at one commit; the activation pass stays the Project's."""
        self.assertNotIn("activation_problems", inspect.getsource(review_validate.review_problems))
        self.assertIn("activation_problems(store, review)", inspect.getsource(review_validate.validate_review))


def project_tree(root: Path) -> dict[str, str]:
    """Every directory and file under ``root``, ``.git`` and runtime included, file contents hashed."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "<dir>"
        for path in sorted(root.rglob("*"))
    }


class CommittedAuthorityValidationTests(ActivationCase):
    """F1 §6: validation classifies only by the record current HEAD commits, exactly as the working tree holds it.

    Every validation here is also held to leave the Project exactly as it was: HEAD is read through the
    read-only class B context, which writes nothing into the Project and captures no identity.
    """

    def codes(self) -> list[str]:
        before = project_tree(self.root)
        found = [problem.code for problem in validate_project(self.store)]
        self.assertEqual(project_tree(self.root), before, "validation wrote into the Project")
        return found

    def test_a_record_only_the_working_tree_holds_is_a_conflict_and_classifies_nothing(self) -> None:
        count, digest = prefix_digest(self.committed_log())
        self.put_record(REL, records.WorkTerminalActivation("review-v1", count, digest, self.head()).to_record())
        self.assertEqual(self.codes(), ["review_record_conflict"])
        self.append_events(completion())
        self.assertEqual(self.totality(), [], "nothing is classified by an uncommitted record")
        self.assertIn("review_record_conflict", self.codes())

    def test_a_committed_record_deleted_from_the_working_tree_is_a_conflict(self) -> None:
        self.activate()
        (self.root / REL).unlink()
        self.assertEqual(self.codes(), ["review_record_conflict"])

    def test_a_committed_record_changed_in_the_working_tree_is_a_conflict(self) -> None:
        result = self.activate()
        changed = records.WorkTerminalActivation("review-v1", result.legacy_event_count,
                                                 result.legacy_event_prefix_sha256, "b" * 40)
        self.put_record(REL, changed.to_record())
        self.assertEqual(self.codes(), ["review_record_conflict"])

    def test_the_exact_committed_record_is_valid_and_classifies_as_before(self) -> None:
        self.activate()
        self.assertEqual(self.codes(), [])
        self.append_events(completion())
        self.assertEqual(self.totality(), [review_validate.COMPLETION_UNCONSUMED])
        self.put_record(review_paths.consumption_rel(CONSUMPTION_ID), consumption_record())
        self.assertEqual(self.totality(), [])

    def test_where_the_read_only_context_cannot_be_prepared_only_a_working_record_is_refused(self) -> None:
        """HEAD's record cannot be read then, so a working record is never taken for one; with none, nothing changes."""
        from workline.review import hermetic

        unavailable = StopError("no scratch for a read-only class B context here", code="review_no_config_file_invalid")
        with mock.patch.object(hermetic, "read_only", side_effect=unavailable):
            self.assertEqual(self.codes(), [], "a Project that claims no activation validates as it always did")
        self.activate()
        with mock.patch.object(hermetic, "read_only", side_effect=unavailable):
            self.assertEqual(self.codes(), ["review_no_config_file_invalid"])

    def test_validation_captures_no_identity_and_needs_none(self) -> None:
        from workline.review import hermetic

        self.activate()
        git(self.root, "config", "--unset", "user.name")
        git(self.root, "config", "--unset", "user.email")
        with mock.patch.object(hermetic, "capture_identity", side_effect=AssertionError("validation captured an identity")):
            self.assertEqual(self.codes(), [])
            (self.root / REL).unlink()
            self.assertEqual(self.codes(), ["review_record_conflict"], "HEAD's record is still read without one")


class ReadOnlyValidationTests(ActivationCase):
    """Validating a Project writes nothing into it - not a file, not a directory, not in ``.git`` or runtime."""

    def unchanged_codes(self, store: ProjectStore) -> list[str]:
        before = project_tree(store.root)
        found = [problem.code for problem in validate_project(store)]
        self.assertEqual(project_tree(store.root), before, "validation wrote into the Project")
        return found

    def test_a_legacy_project(self) -> None:
        self.assertEqual(self.unchanged_codes(self.store), [])
        self.assertFalse((self.root / review_paths.RUNTIME_REVIEW_DIR).exists())

    def test_a_project_with_review_records(self) -> None:
        self.activate()
        self.put_record(review_paths.consumption_rel(CONSUMPTION_ID), consumption_record())
        self.append_events(completion())
        self.unchanged_codes(self.store)  # whatever it reports, it writes nothing

    def test_another_activated_project_read_from_outside_it(self) -> None:
        self.activate()
        self.new_project("other")  # the test now works from inside another Project
        self.assertNotEqual(Path.cwd().resolve(), self.root.resolve())
        self.assertEqual(self.unchanged_codes(self.store), [])


class LifecycleIndependenceTests(unittest.TestCase):
    def test_state_derivation_reads_no_review_record_or_activation(self) -> None:
        from workline import state

        source = inspect.getsource(state)
        for needle in ("review", "activation", "Consumption"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, source.replace("reviewed", ""))


if __name__ == "__main__":
    unittest.main()
