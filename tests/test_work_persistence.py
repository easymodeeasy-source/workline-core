"""Batch B: the object-driven Work persistence engine (``F3`` §7.1.1-§7.1.4, IP-19/22/17/18/24/20/1/23).

What these tests hold:

* every Work-mode commit commits a COMMIT TREE PLAN - its bytes from the PARENT OBJECT plus
  this mutation's recorded effects (checked against the digest recorded before writing), or
  from the bound ownership witness - and never a reread of the working tree;
* O-1 ... O-8 exactly: isolated index, exact-parent seed, parent agreement, raw hash-object
  checked against the plan, index placement by identity, the planned tree, commit-tree with
  exact message and no hook / no signature, a DURABLE prepared id before the CAS, the CAS,
  C-1 only after read-back, the isolated index discarded;
* the resume matrix of §7.1.3, rows A-G, decided from the operation's own record - never
  the branch tip - with RAW ancestry for row F;
* the real index refreshed only after C-1, only for own paths, only where the entry is still
  the one the commit replaced, under an exclusive index.lock; a person's staged entry is
  never overwritten, an unknown lock is never deleted, and a failure never un-owns K;
* the closed persistence-mode set and the generation dispatch by durable review_kind.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

from helpers import WorklineTestCase
from workline import mutation as mutation_module
from workline import ops
from workline import roadmap_review as rr
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.ids import new_id
from workline.mutation import MATCHING, UNAPPLIED, Effect, MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import ancestry, hermetic, ownership, work_invocation, workcommit
from workline.review import paths as review_paths
from workline.start import LEDGER_FILES

WINDOWS = sys.platform == "win32"
FORM_L = b".workline/review/** !text eol=lf -filter -ident -working-tree-encoding\n"
NOTE = ".workline/test-note.md"


class Crash(Exception):
    """A process death at a chosen instant."""


def git(where: Path, *args: str, check: bool = True, input: bytes | None = None) -> str:
    """Test-fixture Git only, with a clean environment and a fixed identity."""
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    environment.update({
        "GIT_AUTHOR_NAME": "Real Person", "GIT_AUTHOR_EMAIL": "real@proj",
        "GIT_COMMITTER_NAME": "Real Person", "GIT_COMMITTER_EMAIL": "real@proj",
    })
    found = subprocess.run(["git", "-C", str(where), *args], capture_output=True, env=environment, input=input)
    if check and found.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {where}: {found.stderr.decode('utf-8', 'replace')}")
    return found.stdout.decode("utf-8", "replace").strip()


def make_junction(link: Path, target: Path) -> bool:
    if WINDOWS:
        found = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
        return found.returncode == 0
    link.symlink_to(target, target_is_directory=True)
    return True


class PersistenceCase(WorklineTestCase):
    """A real Project with one registered Work, the canonical form-L rule committed, the lock held."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.root = self.store.root
        git(self.root, "config", "user.name", "Real Person")
        git(self.root, "config", "user.email", "real@proj")
        (self.root / ".gitattributes").write_bytes(FORM_L)
        git(self.root, "add", ".gitattributes")
        git(self.root, "commit", "-m", "form L", "--no-verify")
        roadmap = self.simple_roadmap(self.store)
        entry = self.simple_entry(self.store, roadmap.phase_ids["a"])
        self.work_id = entry.work_ids["w1"]
        lock = project_operation(self.store, "start", {"work_id": self.work_id, "mode": "single-work"})
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        self.git = hermetic.enter(self.store)
        self.base = self.head()
        self.branch = git(self.root, "symbolic-ref", "HEAD")

    # --- helpers ---------------------------------------------------------------
    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD")

    def open(self, *, review: bool = True, invocation: dict | None = None):
        chosen = invocation or {"operation": "start", "work_id": self.work_id, "mode": "single-work"}
        if review and invocation is None:
            chosen = {**chosen, **work_invocation.markers()}
        return MutationController(self.store).open("start", chosen, WriteScope(entities=(self.work_id,), files=LEDGER_FILES))

    def reload(self, mutation):
        return MutationController(self.store).load(mutation.id)

    def entry_events(self, mutation, stage: str = "entry-events") -> None:
        mutation.add_effects(stage, ops.event_effects(mutation, stage, self.work_id, ["work_started", "work_target_added"]))
        mutation.apply()

    def note_stage(self, mutation, content: str = "our note\n", stage: str = "note") -> None:
        mutation.add_effects(stage, [Effect.write_file(NOTE, content)])
        mutation.apply()

    def plan(self, mutation, plan_class: str, message: str = "chore(workline): a work commit"):
        effects = mutation.effects
        return workcommit.effect_plan(
            self.git, parent=self.head(), ref=self.branch, message=message, plan_class=plan_class,
            effects=workcommit.finalized_effects(effects, len(effects)),
        )

    def record_commit(self, mutation, plan_class: str = workcommit.CLASS_WORK_STAGE, stage: str = "commit",
                      message: str = "chore(workline): a work commit"):
        plan = self.plan(mutation, plan_class, message)
        mutation.add_effects(stage, [workcommit.commit_effect(plan, attr_basis=self.base)])
        return mutation.stage_effects(stage)[0]

    def commit_record(self, mutation, stage: str = "commit") -> dict:
        return self.reload(mutation).stage_effects(stage)[0]

    def blob(self, commit: str, path: str) -> bytes:
        found = subprocess.run(["git", "-C", str(self.root), "cat-file", "blob", f"{commit}:{path}"], capture_output=True)
        self.assertEqual(found.returncode, 0, found.stderr)
        return found.stdout

    def index_entry(self, path: str) -> str:
        return git(self.root, "ls-files", "--stage", "--", path)

    def person_commits(self, name: str = "person.txt") -> str:
        (self.root / name).write_bytes(b"a person's change\n")
        git(self.root, "add", name)
        git(self.root, "commit", "-m", "a person's commit", "--no-verify")
        return self.head()


# --------------------------------------------------------------------------- the plan and its sources


class PlanTests(PersistenceCase):
    """IP-19 / IP-22: the plan names the exact parent, ref, message, contract and changed entries only."""

    def test_the_entry_events_commit_carries_the_event_log_alone(self) -> None:
        mutation = self.open()
        self.entry_events(mutation)
        parent_log = self.blob(self.base, workcommit.EVENT_LOG)
        record = self.record_commit(mutation, workcommit.CLASS_ENTRY)
        mutation.apply()
        made = self.commit_record(mutation)["commit_id"]
        self.assertEqual(self.head(), made)
        self.assertEqual(git(self.root, "rev-parse", f"{made}^"), self.base)
        changed = git(self.root, "diff-tree", "--no-commit-id", "--name-only", "-r", self.base, made).splitlines()
        self.assertEqual(changed, [workcommit.EVENT_LOG])
        committed = self.blob(made, workcommit.EVENT_LOG)
        self.assertTrue(committed.startswith(parent_log))
        self.assertEqual(record["payload"]["plan_class"], "entry")

    def test_the_plan_is_self_checking_against_its_parent(self) -> None:
        mutation = self.open()
        self.note_stage(mutation)
        plan = self.plan(mutation, workcommit.CLASS_WORK_STAGE)
        (entry,) = plan.entries
        self.assertEqual((entry.path, entry.old_mode, entry.old_oid, entry.new_mode), (NOTE, None, None, "100644"))
        wrong = workcommit.CommitTreePlan(plan.parent, plan.ref, plan.message, plan.contract, plan.plan_class, (
            workcommit.PlanEntry(NOTE, "100644", "1" * 40, entry.new_mode, entry.new_oid, entry.material),))
        index = workcommit.isolated_index_path(self.root, mutation.id, 99)
        with self.assertRaises(StopError) as caught:
            workcommit.build(self.git, wrong, index=index, date=workcommit.commit_date())
        self.assertEqual(caught.exception.code, "review_commit_plan_invalid")
        self.assertIn("parent", caught.exception.message)
        self.assertFalse(index.exists())

    def test_material_comes_from_the_parent_object_not_the_working_tree(self) -> None:
        """A foreign append to the event log after this mutation wrote never enters the commit (M-56)."""
        mutation = self.open()
        self.entry_events(mutation)
        record = self.record_commit(mutation, workcommit.CLASS_ENTRY)
        written = (self.root / workcommit.EVENT_LOG).read_bytes()
        foreign = ('{"id":"%s","type":"work_resumed","entity":"%s","at":"2026-01-01T00:00:00+00:00"}\n'
                   % (new_id("event"), self.work_id)).encode()
        (self.root / workcommit.EVENT_LOG).write_bytes(written + foreign)
        mutation.apply()
        made = self.commit_record(mutation)["commit_id"]
        self.assertEqual(self.blob(made, workcommit.EVENT_LOG), written)
        self.assertTrue((self.root / workcommit.EVENT_LOG).read_bytes().endswith(foreign),
                        "the person's change is left in place")
        self.assertEqual(record["payload"]["paths"], [workcommit.EVENT_LOG])

    def test_relation_ledgers_are_rendered_from_the_parent_object(self) -> None:
        from workline.store import Relation

        mutation = self.open()
        relation = Relation(new_id("relation"), "must_read", self.work_id, "README.md")
        mutation.add_effects("rel", [Effect.add_relation("related", relation), Effect.write_file(NOTE, "n\n")])
        mutation.apply()
        self.record_commit(mutation)
        mutation.apply()
        made = self.commit_record(mutation)["commit_id"]
        ledger = self.blob(made, ".workline/relations/related.yaml")
        self.assertEqual(ledger, (self.root / ".workline/relations/related.yaml").read_bytes())
        self.assertIn(relation.id.encode(), ledger)

    def test_a_disagreement_with_the_recorded_digest_stops_before_anything_is_committed(self) -> None:
        mutation = self.open()
        self.note_stage(mutation)
        for effect in mutation.record["effects"]:
            if effect["kind"] == "write_file":
                effect["wrote"] = "sha256:" + "0" * 64
        mutation._save()
        with self.assertRaises(StopError) as caught:
            self.record_commit(mutation)
        self.assertEqual(caught.exception.code, "review_commit_plan_invalid")
        self.assertEqual(self.head(), self.base)
        self.assertFalse(mutation.has_stage("commit"), "a commit that cannot be planned leaves no Git stage")

    def test_unrelated_working_tree_changes_never_enter_the_commit(self) -> None:
        (self.root / "unrelated.txt").write_bytes(b"untracked\n")
        (self.root / "README.md").write_bytes(b"a tracked file changed by a person\n")
        mutation = self.open()
        self.note_stage(mutation)
        self.record_commit(mutation)
        mutation.apply()
        made = self.commit_record(mutation)["commit_id"]
        self.assertEqual(git(self.root, "diff-tree", "--no-commit-id", "--name-only", "-r", self.base, made).splitlines(),
                         [NOTE])

    def test_an_empty_delta_is_never_committed(self) -> None:
        plan = workcommit.CommitTreePlan(self.base, self.branch, "m", workcommit.CONTRACT, "work-stage", ())
        with self.assertRaises(StopError) as caught:
            workcommit.build(self.git, plan, index=workcommit.isolated_index_path(self.root, "mut_x", 1),
                             date=workcommit.commit_date())
        self.assertIn("empty delta", caught.exception.message)


# --------------------------------------------------------------------------- the primitive's properties


class PrimitiveTests(PersistenceCase):
    """O-1 ... O-8, measured on the real repository."""

    def committed(self) -> tuple[object, str]:
        mutation = self.open()
        self.note_stage(mutation)
        self.record_commit(mutation, message="exact message, no newline")
        mutation.apply()
        return mutation, self.commit_record(mutation)["commit_id"]

    def test_the_message_is_committed_byte_for_byte(self) -> None:
        _, made = self.committed()
        body = subprocess.run(["git", "-C", str(self.root), "cat-file", "commit", made], capture_output=True).stdout
        self.assertTrue(body.endswith(b"\n\nexact message, no newline"), body)

    def test_no_hook_runs(self) -> None:
        hooks = self.root / ".git" / "hooks"
        marker = self.tmp / "hook-ran"
        for name in ("pre-commit", "commit-msg", "post-commit", "reference-transaction", "post-index-change"):
            (hooks / name).write_text(f"#!/bin/sh\necho {name} >> '{marker.as_posix()}'\n", encoding="utf-8", newline="\n")
            os.chmod(hooks / name, 0o755)
        self.committed()
        self.assertFalse(marker.exists(), marker.read_text() if marker.exists() else "")

    def test_no_signature_is_applied(self) -> None:
        git(self.root, "config", "commit.gpgSign", "true")
        git(self.root, "config", "gpg.program", str(self.tmp / "no-such-gpg"))
        _, made = self.committed()
        body = git(self.root, "cat-file", "commit", made)
        self.assertNotIn("gpgsig", body)

    def test_the_isolated_index_is_discarded_and_the_real_one_is_never_used_to_build(self) -> None:
        mutation, _ = self.committed()
        directory = self.root / review_paths.RUNTIME_WORK_INDEX_DIR
        self.assertEqual(list(directory.iterdir()) if directory.exists() else [], [])

    def test_a_stale_isolated_index_from_an_earlier_attempt_is_never_reused(self) -> None:
        mutation = self.open()
        self.note_stage(mutation)
        record = self.record_commit(mutation)
        stale = workcommit.isolated_index_path(self.root, mutation.id, int(record["seq"]))
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_bytes(b"garbage from a crashed attempt")
        mutation.apply()
        self.assertFalse(stale.exists())
        self.assertEqual(self.head(), self.commit_record(mutation)["commit_id"])

    def test_raw_bytes_are_stored_exactly_even_under_autocrlf(self) -> None:
        git(self.root, "config", "core.autocrlf", "true")
        mutation = self.open()
        self.note_stage(mutation, content="crlf line\r\nlf line\n")
        self.record_commit(mutation)
        mutation.apply()
        made = self.commit_record(mutation)["commit_id"]
        self.assertEqual(self.blob(made, NOTE), b"crlf line\r\nlf line\n")

    def test_the_real_index_is_refreshed_for_own_paths(self) -> None:
        mutation, made = self.committed()
        blob = git(self.root, "rev-parse", f"{made}:{NOTE}")
        self.assertIn(blob, self.index_entry(NOTE))
        self.assertEqual(git(self.root, "status", "--porcelain", "--", NOTE), "")
        self.assertEqual(self.commit_record(mutation)[workcommit.INDEX_REFRESH], {"refreshed": [NOTE], "foreign": []})


class ResultPlanTests(PersistenceCase):
    """S-c1's plan from the bound witness: kinds, deletion, gitlink, and the staging race (M-36)."""

    def result(self, results=(), deletions=()):
        base = self.head()
        witnesses = ownership.bind_declarations(self.store, self.git, results, deletions, base)
        plan = workcommit.result_plan(self.git, parent=base, ref=self.branch, message="result", witnesses=witnesses)
        return witnesses, plan

    def commit_plan(self, plan) -> str:
        index = workcommit.isolated_index_path(self.root, "mut_test", 1)
        prepared = workcommit.build(self.git, plan, index=index, date=workcommit.commit_date())
        workcommit._cas(self.git, plan.ref, prepared.commit, plan.parent)
        return prepared.commit

    def test_a_deletion_and_an_executable_and_a_file(self) -> None:
        (self.root / "gone.txt").write_bytes(b"gone\n")
        (self.root / "tool.sh").write_bytes(b"#!/bin/sh\n")
        git(self.root, "add", "gone.txt", "tool.sh")
        git(self.root, "update-index", "--chmod=+x", "tool.sh")
        git(self.root, "commit", "-m", "base files", "--no-verify")
        (self.root / "gone.txt").unlink()
        (self.root / "tool.sh").write_bytes(b"#!/bin/sh\necho new\n")
        (self.root / "new.txt").write_bytes(b"new\r\n")
        _, plan = self.result(results=["tool.sh", "new.txt"], deletions=["gone.txt"])
        made = self.commit_plan(plan)
        listing = git(self.root, "ls-tree", "-r", made)
        self.assertNotIn("gone.txt", listing)
        self.assertIn("100755 blob", [line.split("\t")[0][:11] for line in listing.splitlines() if line.endswith("tool.sh")][0])
        self.assertEqual(self.blob(made, "new.txt"), b"new\r\n")

    def test_a_gitlink_is_placed_by_its_commit_id_and_writes_no_object(self) -> None:
        subrepo = self.new_dir("subrepo")
        git(subrepo, "init", "-b", "main")
        (subrepo / "a.txt").write_bytes(b"a\n")
        git(subrepo, "add", "-A")
        git(subrepo, "commit", "-m", "sub", "--no-verify")
        git(self.root, "-c", "protocol.file.allow=always", "submodule", "add", subrepo.as_uri(), "sub")
        git(self.root, "commit", "-m", "add sub", "--no-verify")
        (self.root / "sub" / "b.txt").write_bytes(b"b\n")
        git(self.root / "sub", "add", "-A")
        git(self.root / "sub", "commit", "-m", "sub advance", "--no-verify")
        moved = git(self.root / "sub", "rev-parse", "HEAD")
        witnesses, plan = self.result(results=["sub"])
        (entry,) = plan.entries
        self.assertEqual((entry.new_mode, entry.new_oid, entry.material), ("160000", moved, None))
        made = self.commit_plan(plan)
        self.assertIn(f"160000 commit {moved}\tsub", git(self.root, "ls-tree", made, "sub"))

    def test_inert_entries_are_not_in_the_delta(self) -> None:
        witnesses, plan = self.result(results=[".claude/skills/workline/SKILL.md"])
        self.assertEqual(plan.entries, ())
        self.assertEqual(len(witnesses), 1)

    def test_the_committed_entry_is_the_witnessed_one_with_an_ancestor_indirection_active(self) -> None:
        """IP-21's required regression (§21.12 O): the primitive resolves no working-tree pathname (M-36)."""
        (self.root / "dir").mkdir()
        (self.root / "dir" / "file.txt").write_bytes(b"base\n")
        git(self.root, "add", "dir/file.txt")
        git(self.root, "commit", "-m", "dir", "--no-verify")
        (self.root / "dir" / "file.txt").write_bytes(b"witnessed\n")
        (witness,), plan = self.result(results=["dir/file.txt"])
        (self.root / "dir").rename(self.root / "dir-moved")
        (self.root / "elsewhere").mkdir()
        (self.root / "elsewhere" / "file.txt").write_bytes(b"foreign bytes\n")
        if not make_junction(self.root / "dir", self.root / "elsewhere"):
            self.skipTest("this account cannot create a junction or a directory symlink")
        self.assertEqual((self.root / "dir" / "file.txt").read_bytes(), b"foreign bytes\n", "the redirection is active")
        made = self.commit_plan(plan)
        foreign = git(self.root, "hash-object", "--no-filters", "--stdin", input=b"foreign bytes\n")
        self.assertEqual(git(self.root, "rev-parse", f"{made}:dir/file.txt"), witness.identity)
        self.assertNotIn(foreign, git(self.root, "ls-tree", "-r", made))

    def test_the_candidate_must_agree_with_the_witnessed_plan(self) -> None:
        (self.root / "new.txt").write_bytes(b"new\n")
        base = self.head()
        witnesses = ownership.bind_declarations(self.store, self.git, ["new.txt"], [], base)
        good = [{"path": "new.txt", "old_mode": "000000", "old_oid": "0" * 40, "new_mode": "100644",
                 "new_oid": witnesses[0].identity}]
        workcommit.result_plan(self.git, parent=base, ref=self.branch, message="m", witnesses=witnesses,
                               candidate_entries=good)
        with self.assertRaises(StopError):
            workcommit.result_plan(self.git, parent=base, ref=self.branch, message="m", witnesses=witnesses,
                                   candidate_entries=[dict(good[0], new_mode="100755")])


# --------------------------------------------------------------------------- O-6a, the CAS and the resume matrix


class RecoveryMatrixTests(PersistenceCase):
    """§7.1.3 rows A-G, each decided from the durable record."""

    def pending(self):
        mutation = self.open()
        self.note_stage(mutation)
        self.record_commit(mutation)
        return mutation

    def crash_at(self, name: str, *, times: int = 1):
        real = getattr(workcommit, name)
        calls = {"n": 0}

        def crash(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] <= times:
                raise Crash(name)
            return real(*args, **kwargs)

        return mock.patch.object(workcommit, name, crash)

    def test_the_prepared_id_is_durable_before_the_ref_moves(self) -> None:
        mutation = self.pending()
        seen = {}
        real = workcommit._cas

        def observe(git_, ref, commit, parent):
            on_disk = MutationController(self.store).load(mutation.id).stage_effects("commit")[0]
            seen.update(prepared=on_disk.get(workcommit.PREPARED_COMMIT), head=self.head(), applied=on_disk.get("applied"))
            return real(git_, ref, commit, parent)

        with mock.patch.object(workcommit, "_cas", observe):
            mutation.apply()
        self.assertEqual(seen["head"], self.base, "the CAS had not run yet")
        self.assertEqual(seen["prepared"], self.head(), "the id the ref now holds was durable before it moved")
        self.assertFalse(seen["applied"], "O-6a is not C-1")

    def test_row_a_nothing_prepared_rebuilds_from_the_start(self) -> None:
        mutation = self.pending()
        with self.crash_at("build"), self.assertRaises(Crash):
            mutation.apply()
        again = self.reload(mutation)
        self.assertNotIn(workcommit.PREPARED_COMMIT, again.stage_effects("commit")[0])
        again.apply()
        self.assertEqual(self.head(), self.commit_record(mutation)["commit_id"])

    def test_row_b_prepared_and_ref_at_parent_retries_the_cas_of_that_exact_object(self) -> None:
        mutation = self.pending()
        with self.crash_at("_cas"), self.assertRaises(Crash):
            mutation.apply()
        again = self.reload(mutation)
        prepared = again.stage_effects("commit")[0][workcommit.PREPARED_COMMIT]
        self.assertEqual(self.head(), self.base)
        with mock.patch.object(workcommit, "build", side_effect=AssertionError("rebuilt")):
            outcome = again.apply()
        self.assertIn(UNAPPLIED, [value for _, value in outcome])
        self.assertEqual(self.head(), prepared)
        self.assertEqual(self.commit_record(mutation)["commit_id"], prepared)

    def test_row_c_the_cas_landed_and_c1_is_recovered_from_the_own_record(self) -> None:
        mutation = self.pending()
        with self.crash_at("_promote"), self.assertRaises(Crash):
            mutation.apply()
        again = self.reload(mutation)
        record = again.stage_effects("commit")[0]
        self.assertEqual(self.head(), record[workcommit.PREPARED_COMMIT])
        self.assertNotIn("commit_id", record)
        again.apply()
        self.assertEqual(self.commit_record(mutation)["commit_id"], record[workcommit.PREPARED_COMMIT])

    def test_without_the_checkpoint_the_live_rule_would_have_taken_the_branch_for_ownership(self) -> None:
        """M-41: the classifier never answers "nothing left to commit -> matching" for a Work-mode commit."""
        mutation = self.pending()
        with self.crash_at("_promote"), self.assertRaises(Crash):
            mutation.apply()
        record = self.reload(mutation).stage_effects("commit")[0]
        self.assertEqual(mutation_module.MutationController(self.store).classify(record), UNAPPLIED)
        record.pop(workcommit.PREPARED_COMMIT)
        self.assertEqual(mutation_module.MutationController(self.store).classify(record), mutation_module.MISMATCH)

    def test_row_d_the_ref_moved_elsewhere_is_reconciled_and_never_adopted(self) -> None:
        mutation = self.pending()
        with self.crash_at("_cas"), self.assertRaises(Crash):
            mutation.apply()
        moved = self.person_commits()
        with self.assertRaises(ReconcileRequired) as caught:
            self.reload(mutation).apply()
        self.assertEqual(caught.exception.reason, "review_registration_base_moved")
        self.assertEqual(self.head(), moved)
        self.assertNotIn("commit_id", self.commit_record(mutation))

    def test_row_e_a_missing_prepared_object_fails_closed(self) -> None:
        mutation = self.pending()
        with self.crash_at("_cas"), self.assertRaises(Crash):
            mutation.apply()
        again = self.reload(mutation)
        again.stage_effects("commit")[0][workcommit.PREPARED_COMMIT] = "a" * 40
        again._save()
        with self.assertRaises(ReconcileRequired) as caught:
            self.reload(mutation).apply()
        self.assertIn("no longer holds it", caught.exception.message)
        self.assertEqual(self.head(), self.base)

    def test_row_f_a_descendant_ref_is_reconciled_by_raw_ancestry(self) -> None:
        mutation = self.pending()
        with self.crash_at("_promote"), self.assertRaises(Crash):
            mutation.apply()
        prepared = self.head()
        self.person_commits()
        spied = []
        real = ancestry.raw_descends_from

        def spy(*args):
            spied.append(args[1:])
            return real(*args)

        with mock.patch.object(ancestry, "raw_descends_from", spy), \
                mock.patch("workline.gitcmd.descends_from", side_effect=AssertionError("the revision view")), \
                self.assertRaises(ReconcileRequired) as caught:
            self.reload(mutation).apply()
        self.assertIn("moved on past", caught.exception.message)
        self.assertIn((self.head(), prepared), spied)

    def test_row_f_is_decided_by_the_stored_objects_even_under_a_replace_ref(self) -> None:
        """A refs/replace view that would hide the descent changes nothing: RAW_PARENTS reads the object."""
        mutation = self.pending()
        with self.crash_at("_promote"), self.assertRaises(Crash):
            mutation.apply()
        on_top = self.person_commits()
        unrelated = git(self.root, "commit-tree", git(self.root, "rev-parse", f"{self.base}^{{tree}}"), "-m", "x")
        git(self.root, "replace", "-f", on_top, unrelated)
        with self.assertRaises(ReconcileRequired) as caught:
            self.reload(mutation).apply()
        self.assertIn("moved on past", caught.exception.message)

    def test_row_g_a_failed_index_refresh_never_un_owns_the_commit(self) -> None:
        mutation = self.pending()
        with self.crash_at("refresh_real_index"), self.assertRaises(Crash):
            mutation.apply()
        record = self.commit_record(mutation)
        self.assertTrue(record["applied"])
        self.assertEqual(record["commit_id"], self.head())
        self.assertNotIn(workcommit.INDEX_REFRESH, record)
        outcome = self.reload(mutation).apply()
        self.assertIn(MATCHING, [value for _, value in outcome])
        self.assertIn(workcommit.INDEX_REFRESH, self.commit_record(mutation))

    def test_a_cas_refused_by_a_concurrent_advance_is_reconciled(self) -> None:
        mutation = self.pending()
        real = workcommit._cas

        def advance_first(git_, ref, commit, parent):
            self.person_commits("racer.txt")
            return real(git_, ref, commit, parent)

        with mock.patch.object(workcommit, "_cas", advance_first), self.assertRaises(ReconcileRequired) as caught:
            mutation.apply()
        self.assertEqual(caught.exception.reason, "review_registration_base_moved")
        record = self.commit_record(mutation)
        self.assertIn(workcommit.PREPARED_COMMIT, record)
        self.assertNotEqual(self.head(), record[workcommit.PREPARED_COMMIT])

    def test_a_moved_branch_before_anything_is_prepared_is_never_committed_onto(self) -> None:
        """L-5: the independent-advance allowance does not exist for a Work-mode commit."""
        mutation = self.pending()
        self.person_commits()
        with self.assertRaises(ReconcileRequired) as caught:
            mutation.apply()
        self.assertEqual(caught.exception.reason, "review_registration_base_moved")


# --------------------------------------------------------------------------- the real index (§7.1.4)


class RealIndexTests(PersistenceCase):
    def pending(self, content: str = "our note\n"):
        mutation = self.open()
        self.note_stage(mutation, content=content)
        self.record_commit(mutation)
        return mutation

    def test_a_persons_staged_entries_survive_on_own_and_unrelated_paths(self) -> None:
        mutation = self.pending()
        (self.root / "b.txt").write_bytes(b"their unrelated staged change\n")
        git(self.root, "add", "b.txt")
        unrelated_before = self.index_entry("b.txt")
        ours = (self.root / NOTE).read_bytes()
        (self.root / NOTE).write_bytes(b"their staged version of our path\n")
        git(self.root, "add", "--", NOTE)
        theirs = self.index_entry(NOTE)
        (self.root / NOTE).write_bytes(ours)
        mutation.apply()
        self.assertEqual(self.index_entry(NOTE), theirs, "a person's staging intent is never overwritten")
        self.assertEqual(self.index_entry("b.txt"), unrelated_before)
        self.assertEqual(self.commit_record(mutation)[workcommit.INDEX_REFRESH], {"refreshed": [], "foreign": [NOTE]})
        self.assertEqual(self.blob(self.head(), NOTE), ours, "the commit carries the planned bytes regardless")

    def test_an_already_current_entry_needs_no_write(self) -> None:
        mutation = self.pending()
        git(self.root, "add", "--", NOTE)
        mutation.apply()
        self.assertEqual(self.commit_record(mutation)[workcommit.INDEX_REFRESH], {"refreshed": [], "foreign": []})

    def test_an_unknown_lock_is_never_deleted_and_stops_at_reconciliation(self) -> None:
        mutation = self.pending()
        lock = self.root / ".git" / "index.lock"
        lock.write_bytes(b"")
        with mock.patch.object(workcommit, "LOCK_ATTEMPTS", 2), mock.patch.object(workcommit, "LOCK_WAIT_SECONDS", 0.01):
            with self.assertRaises(StopError) as caught:
                mutation.apply()
        self.assertEqual(caught.exception.code, workcommit.LOCK_RECONCILIATION_CODE)
        self.assertTrue(lock.exists(), "a lock of unknown ownership is never deleted")
        record = self.commit_record(mutation)
        self.assertTrue(record["applied"])
        self.assertEqual(record["commit_id"], self.head(), "C-1 stands")
        lock.unlink()
        self.reload(mutation).apply()
        self.assertEqual(self.commit_record(mutation)[workcommit.INDEX_REFRESH], {"refreshed": [NOTE], "foreign": []})

    def test_brief_contention_is_waited_out(self) -> None:
        """Ordinary brief contention: a lock that appears right as the refresh starts and goes away again."""
        mutation = self.pending()
        real = workcommit._git_dir
        armed = []

        def arm(git_):
            directory = real(git_)
            lock = directory / "index.lock"
            lock.write_bytes(b"")
            releaser = threading.Timer(0.3, lock.unlink)
            releaser.start()
            armed.append(releaser)
            return directory

        with mock.patch.object(workcommit, "_git_dir", arm):
            mutation.apply()
        self.assertEqual(len(armed), 1, "the lock was held when the refresh began")
        self.assertEqual(self.commit_record(mutation)[workcommit.INDEX_REFRESH]["refreshed"], [NOTE])

    def test_the_index_is_left_exactly_as_it_was_when_the_transaction_fails(self) -> None:
        mutation = self.pending()
        before = (self.root / ".git" / "index").read_bytes()
        with mock.patch.object(workcommit, "_publish_snapshot", side_effect=OSError("disk full")):
            with self.assertRaises(StopError) as caught:
                mutation.apply()
        self.assertEqual(caught.exception.code, workcommit.CLEANUP_CHECKPOINT_CODE)
        self.assertEqual((self.root / ".git" / "index").read_bytes(), before)
        self.assertFalse((self.root / ".git" / "index.lock").exists(), "the lock this operation created is released")
        self.assertTrue(self.commit_record(mutation)["applied"])


# --------------------------------------------------------------------------- modes and dispatch (IP-1, IP-23)


class ModeTests(PersistenceCase):
    def test_the_closed_mode_set(self) -> None:
        self.assertEqual(mutation_module.COMMIT_MODES, ("review-v1-planning-local-v1", "review-v1-work-local-v2"))
        with self.assertRaises(ValidationError):
            mutation_module._validate_planning_commit({"mode": "review-v1-work-local-v1", "paths": ["x"], "message": "m"})
        with self.assertRaises(ValidationError):
            mutation_module._validate_planning_commit({"mode": "review-v1-work-local-v3", "paths": ["x"], "message": "m"})
        mutation_module._validate_planning_commit({"mode": "review-v1-planning-local-v1", "paths": ["x"], "message": "m"})

    def test_a_work_mutation_commits_only_in_the_work_mode(self) -> None:
        mutation = self.open()
        self.note_stage(mutation)
        for effect in (Effect.git_commit("m", [NOTE], self.base, self.branch),):
            with self.assertRaises(ValidationError):
                mutation.add_effects("legacy-commit", [effect])
        planning = Effect.git_commit("m", [NOTE], self.base, self.branch)
        planning.payload["mode"] = mutation_module.PLANNING_COMMIT_MODE
        with self.assertRaises(ValidationError):
            mutation.add_effects("planning-commit", [planning])

    def test_a_legacy_mutation_never_records_the_work_mode(self) -> None:
        mutation = self.open(review=False)
        mutation.add_effects("note", [Effect.write_file(NOTE, "n\n")])
        mutation.apply()
        plan = self.plan(mutation, workcommit.CLASS_WORK_STAGE)
        with self.assertRaises(ValidationError):
            mutation.add_effects("commit", [workcommit.commit_effect(plan, attr_basis=self.base)])

    def test_partial_markers_record_no_commit_at_all(self) -> None:
        invocation = {"operation": "start", "work_id": self.work_id, "mode": "single-work",
                      "review_contract": "review-v1-work-v1"}
        mutation = self.open(invocation=invocation)
        mutation.add_effects("note", [Effect.write_file(NOTE, "n\n")])
        mutation.apply()
        with self.assertRaises(ValidationError):
            mutation.add_effects("commit", [Effect.git_commit("m", [NOTE], self.base, self.branch)])

    def test_the_work_payload_shape_is_closed(self) -> None:
        mutation = self.open()
        self.note_stage(mutation)
        good = workcommit.commit_effect(self.plan(mutation, workcommit.CLASS_WORK_STAGE), attr_basis=self.base)
        for key, value in (("attr_basis", "HEAD"), ("plan_class", "other"), ("commit_date", "yesterday"),
                           ("base_exact", True), ("branch", "main")):
            with self.subTest(key=key):
                payload = dict(good.payload, **{key: value})
                with self.assertRaises(ValidationError):
                    mutation_module._validate_planning_commit(payload)

    def test_a_work_generation_commits_in_the_work_mode(self) -> None:
        run_id = new_id("review_run")
        gate_path = review_paths.gate_rel(run_id, 1)
        invocation = {"operation": "review-generation", "review_kind": "work-result-v1", "review_run_id": run_id,
                      "generation": 1, "transition": "accept", "persistence_basis": self.base}
        gen = MutationController(self.store).open(
            "start", invocation, WriteScope(files=(gate_path, review_paths.serialization_token_rel(run_id))))
        gen.add_effects(rr.STAGE_GENERATION, [Effect.create_file(gate_path, "record: 1\n")])
        with mock.patch.object(rr.gitops, "review_commit_effect", side_effect=AssertionError("planning primitive")):
            rr._finish_generation(self.store, gen)
        commit = gen.stage_effects(rr.STAGE_GENERATION_COMMIT)[0]
        self.assertEqual(commit["payload"]["mode"], "review-v1-work-local-v2")
        self.assertEqual(commit["payload"]["plan_class"], "generation")
        self.assertEqual(self.blob(commit["commit_id"], gate_path), b"record: 1\n")
        self.assertEqual(gen.status, "completed")

    def test_a_planning_generation_keeps_the_planning_primitive(self) -> None:
        run_id = new_id("review_run")
        gate_path = review_paths.gate_rel(run_id, 1)
        invocation = {"operation": "review-generation", "review_kind": "roadmap-plan-v1", "review_run_id": run_id,
                      "generation": 1, "transition": "accept"}
        gen = MutationController(self.store).open(
            "roadmap", invocation, WriteScope(files=(gate_path, review_paths.serialization_token_rel(run_id))))
        gen.add_effects(rr.STAGE_GENERATION, [Effect.create_file(gate_path, "record: 1\n")])
        with mock.patch.object(workcommit, "generation_commit_effect", side_effect=AssertionError("work primitive")):
            rr._finish_generation(self.store, gen)
        commit = gen.stage_effects(rr.STAGE_GENERATION_COMMIT)[0]
        self.assertEqual(commit["payload"]["mode"], "review-v1-planning-local-v1")
        self.assertNotIn(workcommit.PREPARED_COMMIT, commit)

    def test_a_work_generation_without_its_persistence_basis_records_nothing(self) -> None:
        run_id = new_id("review_run")
        gate_path = review_paths.gate_rel(run_id, 1)
        invocation = {"operation": "review-generation", "review_kind": "work-result-v1", "review_run_id": run_id,
                      "generation": 1, "transition": "accept"}
        gen = MutationController(self.store).open(
            "start", invocation, WriteScope(files=(gate_path, review_paths.serialization_token_rel(run_id))))
        gen.add_effects(rr.STAGE_GENERATION, [Effect.create_file(gate_path, "record: 1\n")])
        with self.assertRaises(StopError):
            rr._finish_generation(self.store, gen)
        self.assertFalse(gen.has_stage(rr.STAGE_GENERATION_COMMIT))


if __name__ == "__main__":
    unittest.main()
