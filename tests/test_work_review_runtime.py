"""Batch C: the Work Review runtime, from the review-v1 START entry through the seal (``F3`` §5.1 steps 1-16).

What these tests hold:

* the review-v1 entry (F1): the selector is validated before the lock, the lock names only the
  static marker, activation is proven under the lock before the mutation opens, and the F1-D3
  marker matrix refuses a mismatch with the record left untouched;
* the ownership order (§5.1 5b-6): a reserved or unprojectable declaration is refused before any
  ownership is asserted, before the precheck and before any Candidate or Review record;
* the Candidate (F2 §5-§7, A-3) for every object kind - file, executable, symlink, gitlink,
  deletion - and both no-K1 shapes, built from the bound witnesses and the committed base;
* the snapshot material reconstructs the exact Candidate from a fresh clone, and the isolated
  verification (IP-6) never reads the primary working tree and never needs a K1;
* the resulting tree and the Context v2 bind the proof target, never a verdict;
* generations 1, 2 and 3 in order, each committed by its own Work-mode generation mutation;
* the checkout-capability decision: capable seals, unsafe or unknown stops before generation 3;
* the activation the entry proves is a fixture here (Gate 3's producer has its own tests), and
  legacy START and planning are untouched;
* ``declared_base.work.desired_state`` is the Work's canonical desired-state section at the
  committed base, in the Candidate and in the request envelope (F2 §5.3, §12.3);
* the Work Policy promises only what P3 keeps: a LOW finding is non-blocking and bound only by
  digest, and the Policy record is the one the Review Skill declares.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, WorklineTestCase
from workline import start as st
from workline import start_review
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.mutation import MutationController, WriteScope
from workline.review import (
    gate,
    hermetic,
    records,
    resulting_tree,
    serialize,
    work_checkout,
    work_context,
    work_review,
    work_verify,
)
from workline.review import paths as review_paths
from workline.review.store import ReviewStore
from workline.state import ProjectView
from workline.store import WORK_DESIRED_HEADING, ProjectStore

WINDOWS = sys.platform == "win32"
FORM_L = b".workline/review/** !text eol=lf -filter -ident -working-tree-encoding\n"
#: What a test that stops after the seal raises in place of the terminal path (see ``ReviewCase``).
TERMINAL_UNAVAILABLE = "test_stopped_after_seal"


def git(where: Path, *args: str, check: bool = True, input: bytes | None = None) -> str:
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    environment.update({
        "GIT_AUTHOR_NAME": "Real Person", "GIT_AUTHOR_EMAIL": "real@proj",
        "GIT_COMMITTER_NAME": "Real Person", "GIT_COMMITTER_EMAIL": "real@proj",
    })
    found = subprocess.run(["git", "-C", str(where), *args], capture_output=True, env=environment, input=input)
    if check and found.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {where}: {found.stderr.decode('utf-8', 'replace')}")
    return found.stdout.decode("utf-8", "replace").strip()


def git_bytes(where: Path, *args: str) -> bytes:
    found = subprocess.run(["git", "-C", str(where), *args], capture_output=True)
    if found.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {found.stderr!r}")
    return found.stdout


def prefix_digest(log: bytes) -> tuple[int, str]:
    """work-terminal-activation-digest-v1, computed independently of the implementation (F1 §9.1)."""
    text = log.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    events = [json.loads(line) for line in text.split("\n") if line.strip()]
    canonical = b"".join(
        json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
        for event in events
    )
    return len(events), hashlib.sha256(canonical).hexdigest()


class Reviewer:
    """A reviewer that answers every task it is given, and remembers what it was given."""

    def __init__(self, status: str = "completed", findings: tuple = (), identity: str = "reviewer-x",
                 version: str = "1", before=None) -> None:
        self.status, self.findings, self.identity, self.version = status, findings, identity, version
        self.before = before
        self.tasks: list[work_review.WorkReviewTask] = []

    def __call__(self, task: work_review.WorkReviewTask) -> work_review.WorkReviewReport:
        self.tasks.append(task)
        if self.before is not None:
            self.before(task)
        return work_review.WorkReviewReport(task.task_id, self.identity, self.version, self.status, self.findings)


class ReviewCase(WorklineTestCase):
    """A real, activated Project: one registered Work, the canonical form-L rule committed.

    ``stop_after_seal`` keeps these tests about F3 §5.1 steps 1-16: the terminal path of a sealed
    Run (steps 17-37) is replaced by a STOP, so what these tests read is the state the seal
    leaves. The terminal path has its own tests (``test_work_terminal``), which turn it off.
    """

    remote = False
    stop_after_seal = True
    #: Whether the Phase also gets a human_confirmation Work (``self.phase_entry.confirmation_id``).
    confirmation = False

    def setUp(self) -> None:
        super().setUp()
        if self.stop_after_seal:
            def stop(session, sealed):
                raise StopError(f"stopped after sealing Run {sealed.run.review_run_id} for this test",
                                code=TERMINAL_UNAVAILABLE)

            patcher = mock.patch.object(start_review, "terminalize", side_effect=stop)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.store = self.new_project(remote=self.remote)
        self.root = self.store.root
        git(self.root, "config", "user.name", "Real Person")
        git(self.root, "config", "user.email", "real@proj")
        (self.root / ".gitattributes").write_bytes(FORM_L)
        git(self.root, "add", ".gitattributes")
        git(self.root, "commit", "-m", "form L", "--no-verify")
        roadmap = self.simple_roadmap(self.store)
        self.phase_entry = entry = self.simple_entry(self.store, roadmap.phase_ids["a"], confirmation=self.confirmation)
        self.work_id = entry.work_ids["w1"]
        self.prepare()
        self.activate()

    def prepare(self) -> None:
        """What a test class commits before activation (nothing by default)."""

    # --- fixtures --------------------------------------------------------------
    def activate(self) -> None:
        head = git(self.root, "rev-parse", "HEAD")
        count, digest = prefix_digest(git_bytes(self.root, "show", "HEAD:.workline/events/events.jsonl"))
        record = records.WorkTerminalActivation("review-v1", count, digest, head)
        path = self.root / ".workline" / "review" / "activation" / "work-terminal-v1.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(serialize.canonical_bytes(record.to_record()))
        git(self.root, "add", "--", ".workline/review/activation/work-terminal-v1.yaml")
        git(self.root, "commit", "-m", "activation fixture", "--no-verify")
        self.activation = record

    def commit_file(self, path: str, data: bytes, message: str = "seed") -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        git(self.root, "add", "--", path)
        git(self.root, "commit", "-m", message, "--no-verify")

    def review(self, reviewer: Reviewer | None = None) -> work_review.WorkReview:
        self.reviewer = reviewer or Reviewer()
        return work_review.WorkReview(self.reviewer, "reviewer-x", "1")

    def completing(self, *, write: dict[str, bytes] | None = None, delete: tuple[str, ...] = (),
                   declare: tuple[str, ...] | None = None, message: str | None = None, act=None):
        def execute(ctx: st.ExecutionContext):
            for path, data in (write or {}).items():
                target = self.root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            for path in delete:
                (self.root / path).unlink()
            if act is not None:
                act()
            results = tuple(write or {}) if declare is None else declare
            return st.Completed(results, message=message, deleted_paths=delete)

        return execute

    def run_start(self, executor, review=None, *, expect: str | None = TERMINAL_UNAVAILABLE):
        """START under review-v1; in this batch a sealed Run stops before the terminal (Batch D's)."""
        selector = review or self.review()
        if expect is None:
            return st.start(self.store, self.work_id, "single-work", executor, review=selector)
        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", executor, review=selector)
        self.assertEqual(raised.exception.code, expect, raised.exception)
        return raised.exception

    def pending(self) -> list[dict]:
        return MutationController(self.store).list_pending()

    def start_record(self) -> dict:
        found = [record for record in self.pending() if (record.get("invocation") or {}).get("operation") == "start"]
        self.assertEqual(len(found), 1, found)
        return found[0]

    def run_id(self) -> str:
        record = self.start_record()
        (run_id,) = [value for key, value in record["reserved_ids"].items() if key.startswith("review-run:work-result-v1:")]
        return run_id

    def chain(self):
        return ReviewStore(self.store).gate_chain(self.run_id())

    def candidate(self) -> dict:
        first = self.chain().generations[0]
        return ReviewStore(self.store).read_candidate_snapshot(first.candidate_hash).material["candidate"]

    def snapshot(self) -> records.CandidateSnapshot:
        return ReviewStore(self.store).read_candidate_snapshot(self.chain().generations[0].candidate_hash)

    def context(self) -> dict:
        first = self.chain().generations[0]
        task_input = ReviewStore(self.store).read_task_input(str(first.accepted_tasks[0]["task_id"]))
        return task_input.request_envelope["context"]

    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD")

    def tree_of(self, commit: str) -> str:
        return git(self.root, "rev-parse", f"{commit}^{{tree}}")

    def subjects(self, count: int) -> list[str]:
        return git(self.root, "log", f"-{count}", "--format=%s").splitlines()


# --------------------------------------------------------------------------- the entry (F1)


class EntryTests(ReviewCase):
    def test_the_selector_is_validated_before_the_lock_and_before_any_project_state(self) -> None:
        bad = work_review.WorkReview(Reviewer(), "reviewer-x", "1", contract="review-v1-work-v2")
        with mock.patch.object(st, "project_operation", side_effect=AssertionError("the lock was taken")):
            for selector in (bad, object(), work_review.WorkReview(Reviewer(), " padded", "1"),
                             work_review.WorkReview(Reviewer(), "two\nlines", "1"), True):
                with self.subTest(selector=selector), self.assertRaises(ValidationError) as raised:
                    st.start(self.store, self.work_id, "single-work", self.completing(), review=selector)
                self.assertEqual(raised.exception.code, "review_contract_invalid")
        self.assertEqual(self.pending(), [])

    def test_the_lock_holder_names_only_the_static_contract_marker(self) -> None:
        seen: list[dict] = []
        real = st.project_operation

        def spy(store, owner, details):
            seen.append(dict(details))
            return real(store, owner, details)

        with mock.patch.object(st, "project_operation", side_effect=spy):
            self.run_start(self.completing(write={"out.txt": b"out\n"}))
        self.assertEqual(seen, [{"review_contract": "review-v1-work-v1"}])

    def test_an_unactivated_project_refuses_under_the_lock_with_nothing_written(self) -> None:
        git(self.root, "rm", "-q", "--", ".workline/review/activation/work-terminal-v1.yaml")
        git(self.root, "commit", "-m", "deactivate fixture", "--no-verify")
        before = self.head()
        called: list[str] = []
        self.run_start(lambda ctx: called.append("run") or st.Completed(), expect="review_not_activated")
        self.assertEqual((called, self.pending(), self.head()), ([], [], before))

    def test_an_activation_prefix_that_does_not_reproduce_fails_closed(self) -> None:
        path = self.root / ".workline" / "review" / "activation" / "work-terminal-v1.yaml"
        forged = records.WorkTerminalActivation("review-v1", self.activation.legacy_event_count, "0" * 64,
                                                self.activation.activation_base_head)
        path.write_bytes(serialize.canonical_bytes(forged.to_record()))
        git(self.root, "commit", "-am", "forge", "--no-verify")
        with self.assertRaises(ReconcileRequired):
            st.start(self.store, self.work_id, "single-work", self.completing(), review=self.review())
        self.assertEqual(self.pending(), [])

    def test_the_markers_are_written_at_mutation_open_and_are_not_slot_identity(self) -> None:
        self.run_start(self.completing(write={"out.txt": b"out\n"}))
        invocation = self.start_record()["invocation"]
        self.assertEqual(invocation, {
            "operation": "start", "work_id": self.work_id, "mode": "single-work",
            "review_contract": "review-v1-work-v1", "publication_contract": "review-v1-split-v1",
        })

    def open_pending(self, invocation: dict) -> None:
        from workline.oplock import project_operation
        from workline.start import LEDGER_FILES

        with project_operation(self.store, "start", {"work_id": self.work_id}):
            MutationController(self.store).open("start", invocation, WriteScope(entities=(self.work_id,), files=LEDGER_FILES))

    def test_the_marker_matrix_refuses_every_mismatch_and_leaves_the_record_untouched(self) -> None:
        live = {"operation": "start", "work_id": self.work_id, "mode": "single-work"}
        cases = {
            "legacy record, review-v1 retry": (live, True),
            "review-v1 record, legacy retry": ({**live, **start_review.invocation(self.work_id, "single-work")}, False),
            "partial record, review-v1 retry": ({**live, "review_contract": "review-v1-work-v1"}, True),
            "partial record, legacy retry": ({**live, "publication_contract": "review-v1-split-v1"}, False),
            "other contract, review-v1 retry": ({**live, "review_contract": "review-v1-work-v9",
                                                 "publication_contract": "review-v1-split-v1"}, True),
        }
        from workline.oplock import project_operation

        for name, (recorded, review_v1) in cases.items():
            with self.subTest(case=name):
                with project_operation(self.store, "start", {"work_id": self.work_id}):
                    for record in self.pending():
                        MutationController(self.store).load(record["mutation_id"]).abandon()
                self.open_pending(recorded)
                (before,) = self.pending()
                with self.assertRaises(ReconcileRequired) as raised:
                    st.start(self.store, self.work_id, "single-work", self.completing(),
                             review=self.review() if review_v1 else None)
                self.assertEqual(raised.exception.reason, "review_marker_mismatch")
                self.assertEqual(self.pending(), [before])

    def test_a_transform_in_the_attribute_source_refuses_before_the_lock(self) -> None:
        (self.root / ".gitattributes").write_bytes(FORM_L + b"*.txt filter=lfs\n")
        git(self.root, "commit", "-am", "a transform", "--no-verify")
        before = self.head()
        with mock.patch.object(st, "project_operation", side_effect=AssertionError("the lock was taken")):
            with self.assertRaises(StopError) as raised:
                st.start(self.store, self.work_id, "single-work", self.completing(), review=self.review())
        self.assertEqual(raised.exception.code, "review_git_transform")
        self.assertEqual((self.pending(), self.head()), ([], before))


class RemoteEntryTests(ReviewCase):
    remote = True

    def test_a_project_with_a_remote_needs_the_publication_capable_git_before_the_lock(self) -> None:
        from workline import gitcmd

        with mock.patch.object(gitcmd, "running_git_version", return_value=(2, 30, 9)), \
                mock.patch.object(st, "project_operation", side_effect=AssertionError("the lock was taken")):
            with self.assertRaises(StopError) as raised:
                st.start(self.store, self.work_id, "single-work", self.completing(), review=self.review())
        self.assertEqual(raised.exception.code, "review_git_unsupported")
        self.assertEqual(self.pending(), [])


# --------------------------------------------------------------------------- 5b-6: the ownership order


class OwnershipOrderTests(ReviewCase):
    def assert_nothing_asserted(self) -> None:
        record = self.start_record()
        self.assertNotIn("own_content", record.get("notes") or {})
        self.assertFalse([key for key in record.get("reserved_ids") or {} if key.startswith("review-run:")])
        self.assertEqual(list((self.root / ".workline" / "review").glob("candidate-snapshots/*")), [])

    def test_a_reserved_declaration_is_refused_before_ownership_and_before_the_precheck(self) -> None:
        precheck = mock.patch.object(st, "completion_precheck", side_effect=AssertionError("precheck ran"))
        with precheck, self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work",
                     self.completing(declare=(".workline/review/gates/x.yaml",)), review=self.review())
        self.assertEqual(raised.exception.reason, "review_reserved_namespace")
        self.assert_nothing_asserted()

    def test_the_event_log_is_reserved_too(self) -> None:
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work",
                     self.completing(declare=(".workline/events/events.jsonl",)), review=self.review())
        self.assertEqual(raised.exception.reason, "review_reserved_namespace")
        self.assert_nothing_asserted()

    def test_a_declared_directory_is_unprojectable_before_the_candidate(self) -> None:
        (self.root / "adir").mkdir()
        (self.root / "adir" / "f.txt").write_bytes(b"f\n")
        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", self.completing(declare=("adir",)), review=self.review())
        self.assertEqual(raised.exception.code, "review_candidate_unavailable")
        self.assert_nothing_asserted()


# --------------------------------------------------------------------------- 10-11: the Candidate for every kind


class CandidateKindTests(ReviewCase):
    def entry(self, path: str) -> dict:
        (found,) = [entry for entry in work_review.entries_of(self.candidate()) if entry["path"] == path]
        return found

    def payloads(self) -> dict[str, bytes]:
        width = len(self.head())
        return work_review.read_material(self.snapshot(), self.chain().generations[0].candidate_hash, width).payloads

    def test_a_new_regular_file(self) -> None:
        self.run_start(self.completing(write={"docs/out.txt": b"out\r\nbytes\n"}, message="feat: out"))
        candidate = self.candidate()
        content = candidate["projection"]["content"]
        self.assertEqual((content["artifact_kind"], content["message"]), ("result_commit", "feat: out"))
        entry = self.entry("docs/out.txt")
        self.assertEqual((entry["status"], entry["old_kind"], entry["new_kind"], entry["new_mode"]), ("A", "absent", "file", "100644"))
        self.assertEqual(entry["new_oid"], git(self.root, "hash-object", "--no-filters", "docs/out.txt"))
        self.assertEqual(entry["content_sha256"], hashlib.sha256(b"out\r\nbytes\n").hexdigest())
        self.assertEqual(self.payloads(), {"docs/out.txt": b"out\r\nbytes\n"})

    def test_an_executable_file_keeps_the_mode_git_records(self) -> None:
        self.commit_file("tool.sh", b"#!/bin/sh\n")
        git(self.root, "update-index", "--chmod=+x", "tool.sh")
        git(self.root, "commit", "-m", "executable", "--no-verify")
        self.run_start(self.completing(write={"tool.sh": b"#!/bin/sh\necho hi\n"}))
        entry = self.entry("tool.sh")
        self.assertEqual((entry["status"], entry["old_mode"], entry["new_mode"]), ("M", "100755", "100755"))

    def test_a_symlink_is_its_link_object(self) -> None:
        git(self.root, "config", "core.symlinks", "false" if WINDOWS else "true")
        if WINDOWS:
            target = git(self.root, "hash-object", "-w", "--stdin", input=b"old-target")
            git(self.root, "update-index", "--add", "--cacheinfo", f"120000,{target},link")
            git(self.root, "commit", "-m", "link", "--no-verify")
            git(self.root, "checkout", "--", "link")
            act = lambda: (self.root / "link").write_bytes(b"new-target")  # noqa: E731
        else:
            act = lambda: os.symlink("new-target", self.root / "link")  # noqa: E731
        self.run_start(self.completing(declare=("link",), act=act))
        entry = self.entry("link")
        self.assertEqual((entry["new_kind"], entry["new_mode"]), ("symlink", "120000"))
        self.assertEqual(self.payloads(), {"link": b"new-target"})

    def test_a_gitlink_is_its_commit_and_carries_no_payload(self) -> None:
        # line-end-free content: the submodule is cloned under this machine's own configuration, and
        # a line-end conversion there would read as a pre-existing change to it
        subrepo = self.new_dir("subrepo")
        git(subrepo, "init", "-b", "main")
        (subrepo / "a.txt").write_bytes(b"a")
        git(subrepo, "add", "-A")
        git(subrepo, "commit", "-m", "sub base", "--no-verify")
        git(self.root, "-c", "protocol.file.allow=always", "-c", "core.autocrlf=false", "submodule", "add",
            subrepo.as_uri(), "sub")
        git(self.root, "commit", "-m", "add sub", "--no-verify")
        moved: list[str] = []

        def advance() -> None:
            working = self.root / "sub"
            (working / "b.txt").write_bytes(b"b")
            git(working, "add", "-A")
            git(working, "commit", "-m", "sub advance", "--no-verify")
            moved.append(git(working, "rev-parse", "HEAD"))

        self.run_start(self.completing(declare=("sub",), act=advance))
        entry = self.entry("sub")
        self.assertEqual((entry["new_kind"], entry["new_mode"], entry["new_oid"], entry["content_sha256"]),
                         ("gitlink", "160000", moved[0], None))
        self.assertEqual(self.payloads(), {})

    def test_a_deletion_is_explicit_absence(self) -> None:
        self.commit_file("old.txt", b"old\n")
        self.run_start(self.completing(delete=("old.txt",)))
        entry = self.entry("old.txt")
        self.assertEqual((entry["status"], entry["new_kind"], entry["new_mode"], entry["content_sha256"]),
                         ("D", "absent", "000000", None))
        self.assertEqual(entry["new_oid"], "0" * len(self.head()))
        self.assertEqual(self.payloads(), {})

    def test_no_declared_path_is_the_empty_artifact(self) -> None:
        self.run_start(self.completing())
        content = self.candidate()["projection"]["content"]
        self.assertEqual(content, {
            "artifact_kind": "empty", "entries": [],
            "emptiness_proof": {
                "base_commit": self.candidate()["declared_base"]["base_commit"], "declared_result_paths": [],
                "declared_deleted_paths": [], "owned_paths_differing_from_base": [],
            },
        })
        self.assertEqual(self.snapshot().material["payloads"], [])

    def test_an_all_inert_declaration_is_empty_and_keeps_its_entries_and_payloads(self) -> None:
        self.commit_file("same.txt", b"same\n")
        self.run_start(self.completing(write={"same.txt": b"same\n"}))
        content = self.candidate()["projection"]["content"]
        self.assertEqual(content["artifact_kind"], "empty")
        self.assertEqual([entry["path"] for entry in content["entries"]], ["same.txt"])
        self.assertFalse(work_review.changing(content["entries"][0]))
        self.assertEqual(content["emptiness_proof"]["declared_result_paths"], ["same.txt"])
        self.assertEqual(self.payloads(), {"same.txt": b"same\n"})


# --------------------------------------------------------------------------- 11-12: reconstruction and isolated verification


class ReconstructionTests(ReviewCase):
    def setUp(self) -> None:
        super().setUp()
        self.run_start(self.completing(write={"out.txt": b"frozen\n"}))

    def test_the_snapshot_reconstructs_the_exact_candidate_in_a_fresh_clone(self) -> None:
        clone = self.tmp / "fresh-clone"
        git(self.tmp, "clone", "--quiet", "--no-local", str(self.root), str(clone))
        git(clone, "config", "user.name", "Clone Person")
        git(clone, "config", "user.email", "clone@proj")
        store = ProjectStore(clone)
        self.assertFalse((clone / ".workline" / "runtime").exists())
        first = ReviewStore(store).gate_chain(self.run_id()).generations[0]
        snapshot = ReviewStore(store).read_candidate_snapshot(first.candidate_hash)
        reconstruction = work_review.read_material(snapshot, first.candidate_hash, len(self.head()))
        self.assertEqual(reconstruction.payloads, {"out.txt": b"frozen\n"})
        verified = work_verify.verify(store, hermetic.enter(store), reconstruction,
                                      resulting_tree_id=self.context()["review_checkout_capability"]["resulting_tree"])
        self.assertEqual(verified.verified_entries, 1)

    def test_verification_never_reads_the_primary_working_tree(self) -> None:
        (self.root / "out.txt").write_bytes(b"changed after the freeze\n")
        first = self.chain().generations[0]
        reconstruction = work_review.read_material(self.snapshot(), first.candidate_hash, len(self.head()))
        work_verify.verify(self.store, hermetic.enter(self.store), reconstruction,
                           resulting_tree_id=self.context()["review_checkout_capability"]["resulting_tree"])
        self.assertEqual((self.root / "out.txt").read_bytes(), b"changed after the freeze\n")
        self.assertEqual(list((self.root / review_paths.RUNTIME_WORK_VERIFY_DIR).glob("*")), [])

    def test_a_payload_that_disagrees_with_its_entry_is_never_substituted(self) -> None:
        snapshot = self.snapshot()
        original = snapshot.material["payloads"][0]["data"]
        self.assertTrue(original.endswith("="), original)
        for name, data in (("other bytes", work_review.encode_payload(b"other!\n")), ("unpadded", original.rstrip("=")),
                           ("line-broken", original[:4] + "\n" + original[4:])):
            material = json.loads(json.dumps(snapshot.material))
            material["payloads"][0]["data"] = data
            forged = records.CandidateSnapshot(
                candidate_hash=snapshot.candidate_hash, reconstruction_mode=snapshot.reconstruction_mode,
                projection_semantics_version=snapshot.projection_semantics_version, material=material, builder=None,
            )
            with self.subTest(forged=name), self.assertRaises(ReconcileRequired):
                work_review.read_material(forged, snapshot.candidate_hash, len(self.head()))

    def test_a_verification_against_another_tree_fails_closed(self) -> None:
        first = self.chain().generations[0]
        reconstruction = work_review.read_material(self.snapshot(), first.candidate_hash, len(self.head()))
        with self.assertRaises(ReconcileRequired):
            work_verify.verify(self.store, hermetic.enter(self.store), reconstruction,
                               resulting_tree_id=self.tree_of("HEAD"))

    def test_no_commit_carries_the_result_before_its_k1(self) -> None:
        self.assertEqual(git(self.root, "log", "--format=%H", "--", "out.txt"), "")
        self.assertIn("out.txt", git(self.root, "status", "--porcelain", "--untracked-files=all"))


# --------------------------------------------------------------------------- 11a-11b: the resulting tree and the Context v2


class ContextTests(ReviewCase):
    def test_the_context_binds_the_exact_proof_target_and_no_verdict(self) -> None:
        pre_base = self.head()
        self.run_start(self.completing(write={"out.txt": b"frozen\n"}))
        context = self.context()
        work_context.require_context(context)
        base_commit = self.candidate()["declared_base"]["base_commit"]
        index = self.tmp / "expected-index"
        environment = {**{k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")},
                       "GIT_INDEX_FILE": str(index)}
        subprocess.run(["git", "-C", str(self.root), "read-tree", base_commit], check=True, env=environment)
        blob = git(self.root, "hash-object", "-w", "--no-filters", "out.txt")
        subprocess.run(["git", "-C", str(self.root), "update-index", "--add", "--cacheinfo", f"100644,{blob},out.txt"],
                       check=True, env=environment)
        expected = subprocess.run(["git", "-C", str(self.root), "write-tree"], capture_output=True, text=True,
                                  env=environment, check=True).stdout.strip()
        capability = context["review_checkout_capability"]
        self.assertEqual(capability, {
            "capability_contract": "review-v1-work-checkout-capability-v1", "form": "form-L",
            "namespace": ".workline/review/**", "base_tree": self.tree_of(pre_base), "resulting_tree": expected,
        })
        self.assertEqual(context["activation"], {
            "record_digest": serialize.digest(self.activation.to_record()), "operation_contract": "review-v1",
            "activation_base_head": self.activation.activation_base_head,
        })
        self.assertEqual(context["activation"], self.candidate()["activation"])
        self.assertEqual(context["git_persistence"], "review-v1-work-local-v2")

    def test_the_declared_base_is_read_from_the_committed_state_after_s_c0(self) -> None:
        self.run_start(self.completing(write={"out.txt": b"frozen\n"}))
        base = self.candidate()["declared_base"]
        self.assertEqual(self.subjects(4)[-1], f"chore(workline): enter {ProjectView.load(self.store).works[self.work_id].display}")
        self.assertEqual(git(self.root, "show", "--name-only", "--format=", base["base_commit"]).split(),
                         [".workline/events/events.jsonl"])
        self.assertEqual(base["work"]["work_id"], self.work_id)
        self.assertEqual(base["work"]["state"], "in_progress")
        self.assertEqual(base["branch"], git(self.root, "symbolic-ref", "HEAD"))


# --------------------------------------------------------------------------- the Work's desired state at the base


class DesiredStateTests(ReviewCase):
    """``declared_base.work.desired_state`` is the Work's canonical body section, never a frontmatter key."""

    #: the Phase entry is given it padded; the canonical section is its stripped text, both lines kept
    desired = "W1 の成果が成立している\n二行目もそのまま"

    def simple_entry(self, store, phase_id, works=None, **kwargs):
        return super().simple_entry(store, phase_id, works or {"w1": f"  {self.desired}\n"}, **kwargs)

    def assert_carried(self) -> None:
        self.assertEqual(self.candidate()["declared_base"]["work"]["desired_state"], self.desired)
        first = self.chain().generations[0]
        stored = ReviewStore(self.store).read_task_input(str(first.accepted_tasks[0]["task_id"]))
        self.assertEqual(stored.request_envelope["work"]["desired_state"], self.desired)
        (task,) = self.reviewer.tasks
        self.assertEqual(task.request_envelope["work"]["desired_state"], self.desired)

    def test_the_work_is_rendered_with_the_section_and_no_frontmatter_key(self) -> None:
        work = ProjectView.load(self.store).works[self.work_id]
        raw = git_bytes(self.root, "show", f"HEAD:{work.path}")
        self.assertIn(f"## {WORK_DESIRED_HEADING}\n{self.desired}\n".encode("utf-8"), raw)
        self.assertNotIn(b"desired_state", raw)
        self.assertNotIn("desired_state", work.meta)

    def test_a_result_bearing_candidate_and_its_request_carry_the_desired_state(self) -> None:
        self.run_start(self.completing(write={"out.txt": b"x\n"}))
        self.assertEqual(self.candidate()["projection"]["content"]["artifact_kind"], "result_commit")
        self.assert_carried()

    def test_an_empty_artifact_candidate_and_its_request_carry_the_same_desired_state(self) -> None:
        self.run_start(self.completing())
        self.assertEqual(self.candidate()["projection"]["content"]["artifact_kind"], "empty")
        self.assert_carried()

    def test_an_uncommitted_change_to_the_work_body_never_reaches_the_declared_base(self) -> None:
        base, branch = self.head(), git(self.root, "symbolic-ref", "HEAD")
        work = ProjectView.load(self.store).works[self.work_id]
        path = self.root / work.path
        changed = "作業ツリーだけの変更"
        path.write_bytes(path.read_bytes().replace(self.desired.encode("utf-8"), changed.encode("utf-8")))
        self.assertEqual(ProjectView.load(self.store).works[self.work_id].section(WORK_DESIRED_HEADING), changed)
        found = start_review.declared_base(self.store, hermetic.enter(self.store), base, branch, self.work_id)
        self.assertEqual(found["work"]["desired_state"], self.desired)
        # only a commit moves it, and the earlier base still reads what it held
        git(self.root, "add", "--", work.path)
        git(self.root, "commit", "-m", "edit the Work body", "--no-verify")
        moved = start_review.declared_base(self.store, hermetic.enter(self.store), self.head(), branch, self.work_id)
        self.assertEqual(moved["work"]["desired_state"], changed)
        self.assertEqual(start_review.declared_base(self.store, hermetic.enter(self.store), base, branch, self.work_id), found)


# --------------------------------------------------------------------------- 13-16: the generations, in order


class GenerationOrderTests(ReviewCase):
    def test_generation_one_is_committed_before_the_reviewer_is_called(self) -> None:
        seen: list[bool] = []

        def committed(task) -> None:
            run_id = self.run_id()
            for path in (review_paths.gate_rel(run_id, 1), review_paths.task_input_rel(task.task_id),
                         review_paths.candidate_snapshot_rel(task.candidate_hash)):
                seen.append(bool(git(self.root, "ls-tree", "HEAD", "--", path)))
            seen.append(ReviewStore(self.store).next_generation(run_id) == 2)

        self.run_start(self.completing(write={"out.txt": b"x\n"}), self.review(Reviewer(before=committed)))
        self.assertEqual(seen, [True, True, True, True])

    def test_each_generation_is_its_own_work_mode_commit_in_order(self) -> None:
        self.run_start(self.completing(write={"out.txt": b"x\n"}))
        run_id = self.run_id()
        subjects = self.subjects(3)
        self.assertEqual(subjects, [f"chore(workline): record review generation {n} of {run_id}" for n in (3, 2, 1)])
        for offset, generation in ((2, 1), (1, 2), (0, 3)):
            commit = git(self.root, "rev-parse", f"HEAD~{offset}")
            parents = git(self.root, "rev-list", "--parents", "-n", "1", commit).split()[1:]
            self.assertEqual(len(parents), 1)
            delta = git(self.root, "diff-tree", "-r", "--no-commit-id", "--name-status", commit).splitlines()
            self.assertTrue(all(line.startswith("A\t.workline/review/") for line in delta), delta)
            self.assertIn(f"A\t{review_paths.gate_rel(run_id, generation)}", delta)
        chain = self.chain()
        self.assertEqual([g.generation for g in chain.generations], [1, 2, 3])
        self.assertEqual(chain.generations[1].settled_tasks[0]["status"], "completed")

    def test_the_task_the_reviewer_receives_is_rebuilt_from_the_stored_task_input(self) -> None:
        self.run_start(self.completing(write={"out.txt": b"x\n"}))
        (task,) = self.reviewer.tasks
        stored = ReviewStore(self.store).read_task_input(task.task_id)
        self.assertEqual((task.task_slot, task.task_kind, task.review_kind), (
            "work-result-reviewer", "work-result-review-v1", "work-result-v1"))
        self.assertEqual(task.request_envelope, stored.request_envelope)
        self.assertEqual(task.request_envelope["candidate"], self.candidate())

    def test_a_capable_resulting_tree_seals_and_issues_the_receipt(self) -> None:
        self.run_start(self.completing(write={"out.txt": b"x\n"}))
        third = self.chain().latest
        self.assertTrue(third.sealed)
        receipt = ReviewStore(self.store).read_receipt(str(third.receipt_id))
        self.assertEqual((receipt.authorized_operation_stage, receipt.target_identity, receipt.authorized_candidate_hash),
                         ("start:work-terminal", self.work_id, third.candidate_hash))
        self.assertEqual(receipt.operation_identity, work_review.operation_identity(self.work_id))

    def test_a_declined_review_is_never_sealed(self) -> None:
        with self.assertRaises(ReconcileRequired):
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"x\n"}),
                     review=self.review(Reviewer(status="declined")))
        chain = self.chain()
        self.assertEqual((chain.latest.generation, chain.latest.status), (2, "open"))
        self.assertEqual(self.start_record()["notes"]["review_seal_refusal"]["code"], "not_authorized")

    def test_an_interrupted_run_resumes_from_its_records_without_the_executor(self) -> None:
        class Crash(BaseException):
            pass

        def crash(task) -> None:
            raise Crash()

        with self.assertRaises(Crash):
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"x\n"}),
                     review=self.review(Reviewer(before=crash)))
        self.assertEqual(self.chain().latest.generation, 1)
        self.run_start(lambda ctx: (_ for _ in ()).throw(AssertionError("the executor ran again")))
        self.assertEqual(self.chain().latest.generation, 3)


# --------------------------------------------------------------------------- 15a: the checkout-capability decision


class CapabilityTests(ReviewCase):
    def test_an_unsafe_resulting_tree_stops_before_generation_three_and_a_retry_changes_nothing(self) -> None:
        executor = self.completing(write={".gitattributes": b"* text=auto\n"})
        self.run_start(executor, expect="review_checkout_unsafe")
        chain = self.chain()
        self.assertEqual((chain.latest.generation, chain.latest.status), (2, "open"))
        self.assertEqual(list((self.root / ".workline" / "review" / "receipts").glob("*")), [])
        self.assertEqual(self.start_record()["notes"]["review_seal_refusal"]["code"], "review_checkout_unsafe")
        self.assertEqual(gate.pending_generation_mutations(self.store, self.run_id()), [])
        before = self.head()
        self.run_start(executor, expect="review_checkout_unsafe")
        self.assertEqual((self.head(), self.chain().latest.generation), (before, 2))

    def test_an_unknown_capability_stops_and_a_transient_cause_can_be_retried(self) -> None:
        unknown = StopError("unanswerable", code="review_checkout_unknown")
        with mock.patch.object(work_checkout, "require_resulting_tree_capability", side_effect=unknown):
            self.run_start(self.completing(write={"out.txt": b"x\n"}), expect="review_checkout_unknown")
        self.assertEqual(self.chain().latest.generation, 2)
        self.run_start(lambda ctx: (_ for _ in ()).throw(AssertionError("the executor ran again")))
        self.assertTrue(self.chain().latest.sealed)
        self.assertIsNone(self.start_record()["notes"].get("review_seal_refusal"))


# --------------------------------------------------------------------------- commit-only pre-completion stages (F3 §4.3)


class CommitOnlyTests(ReviewCase):
    remote = True

    def test_a_derivation_under_review_v1_commits_without_a_push(self) -> None:
        remote_before = git(self.remote_path(), "rev-parse", "main")
        outcomes = [st.Derive({"extra": st.DerivedWork("Extra", "more")}), None]

        def execute(ctx):
            outcome = outcomes.pop(0)
            if outcome is not None:
                return outcome
            (self.root / "out.txt").write_bytes(b"x\n")
            return st.Completed(("out.txt",))

        self.run_start(execute)
        self.assertEqual(git(self.remote_path(), "rev-parse", "main"), remote_before)
        self.assertIn(f"chore(workline): derive from", "\n".join(self.subjects(8)))


# --------------------------------------------------------------------------- boundaries


# --------------------------------------------------------------------------- the Work Policy promises only what P3 keeps


class LowFindingTests(ReviewCase):
    def test_a_low_finding_does_not_block_and_is_bound_only_by_digest(self) -> None:
        finding = work_review.WorkReviewFinding("LOW", "wording", "consider a clearer name for out.txt")
        self.run_start(self.completing(write={"out.txt": b"x\n"}), self.review(Reviewer(findings=(finding,))))
        chain = self.chain()
        self.assertTrue(chain.latest.sealed, "a LOW finding is non-blocking")
        second = chain.generations[1]
        (settled,) = second.settled_tasks
        report = {
            serialize.SCHEMA_KEY: work_review.SCHEMA_REPORT, serialize.VERSION_KEY: work_review.RECORD_VERSION,
            "task_id": settled["task_id"], "reviewer_identity": "reviewer-x", "reviewer_version": "1",
            "status": "completed", "findings": [{"severity": "LOW", "code": "wording", "message": finding.message}],
        }
        self.assertEqual(settled["result_digest"], serialize.digest(report))
        adjudication = work_review.adjudication_record([(settled, report)])
        self.assertEqual([task["low"] for task in adjudication["tasks"]], [1])
        self.assertEqual(second.adjudication_digest, serialize.digest(adjudication))
        self.assertEqual(second.obligation_digest, work_review.empty_obligation_digest())
        # its text is in no committed record: P3 keeps none and returns none
        self.assertEqual(git(self.root, "grep", "-l", "-F", finding.message, "HEAD", "--", ".workline", check=False), "")


class WorkPolicyAuthorityTests(unittest.TestCase):
    def test_the_skill_policy_block_equals_the_code_constant(self) -> None:
        text = (WORKLINE_ROOT / ".claude" / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8")
        block = re.search(r"```yaml\n(.*?)```", text[text.index("**Work Review Policy**"):], re.S)
        self.assertIsNotNone(block, "the Review Skill declares the Work Policy record in a yaml block")
        declared = serialize.parse(block.group(1), "the Work Review Policy")
        self.assertEqual(serialize.canonical_data(work_review.POLICY_RECORD), serialize.canonical_data(declared))
        self.assertEqual(serialize.canonical_text(work_review.POLICY_RECORD), block.group(1))
        self.assertEqual(work_review.policy_hash(), serialize.digest(declared))

    def test_the_low_disposition_promises_no_channel_p3_does_not_have(self) -> None:
        low = work_review.POLICY_RECORD["low_disposition"]
        self.assertTrue(low.startswith("non-blocking;"), low)
        self.assertNotIn("returned to the caller", low)
        self.assertNotIn("findings", {field.name for field in dataclasses.fields(st.StartResult)})


class BoundaryTests(unittest.TestCase):
    def sources(self) -> dict[str, str]:
        from workline.implementation import package_directory

        package = package_directory(Path(__file__).resolve().parents[1])
        return {path.relative_to(package).as_posix(): path.read_text(encoding="utf-8") for path in package.rglob("*.py")}

    def test_only_the_activation_producer_builds_an_activation_record(self) -> None:
        """Gate 3 (P3 F1 §8): the record is decided by its one producer; no START or Review code builds one."""
        for name, text in self.sources().items():
            if name in ("review/records.py", "work_terminal_activation.py"):
                continue
            with self.subTest(module=name):
                self.assertNotIn("WorkTerminalActivation(", text)
        self.assertIn("WorkTerminalActivation(", self.sources()["work_terminal_activation.py"])

    def test_legacy_start_never_imports_the_work_review_path(self) -> None:
        source = self.sources()["start.py"]
        for line in source.splitlines():
            if line.startswith(("from ", "import ")):
                self.assertNotIn("start_review", line)
                self.assertNotIn("work_review", line)


if __name__ == "__main__":
    unittest.main()
