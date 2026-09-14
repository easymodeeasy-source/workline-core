"""A recorded commit is still made after independent commits moved HEAD on (BL-032).

Every operation records its commit - the message, the paths it owns and the HEAD
it was decided on - before it makes it, and an operation interrupted in between,
or whose commit failed, resumes from that Git stage (``rules/git``: Multi-write
mutation, Commit / push).

That stopped working as soon as anything else committed first. An operation
whose write scope is independent may run while another one waits (BL-017), and
a person may commit at any time. HEAD was then no longer the recorded base, and
a recorded commit that was neither found under its message nor had its paths
committed already was classified "applied with an unexpected result": the retry
stopped with ``reconcile_required`` every time, although the commit had never
been made and nobody had touched its paths. ``validate_project`` reported
nothing, and every later operation whose scope overlapped stopped behind the
record.

The commit now also records the branch it was decided on. When such a commit is
still unmade and HEAD has moved, it is made on top of the new HEAD if the branch
only grew past it: the recorded base is an ancestor of HEAD, no commit since
then changed a recorded path, and HEAD is on the recorded branch. Everything
else stays a mismatch - a path committed on its own or with other content, a
path changed and changed back, another branch, a rewritten history, a base or a
branch the record does not show, a record written before the branch was
recorded, and any question Git cannot answer.
"""

from __future__ import annotations

from itertools import product
import os
import re
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from workline import bootstrap as bs
from workline import gitcmd, gitops
from workline import roadmap as rm
from workline import start as st
from workline import yamlish
from workline.create import RelatedSpec, RelationSpec, WorkSpec, create_standalone_work
from workline.errors import GitError, StopError, ValidationError
from workline.ids import new_id
from workline.mutation import Mutation, MutationController
from workline.ops import Replan
from workline.phase_create import PhaseSpec
from workline.state import ProjectView
from workline.store import BOOTSTRAP_REL_PATH, WORKLINE_DIR
from workline.validate import validate_project

EVENT_LOG = f"{WORKLINE_DIR}/events/events.jsonl"
ROADMAP_RELATIONS = f"{WORKLINE_DIR}/relations/roadmap.yaml"
MAIN = "refs/heads/main"
REFUSE_FLAG = "workline-test-refuse-commit"
HOOK = f"""#!/bin/sh
if [ -f "$(git rev-parse --git-dir)/{REFUSE_FLAG}" ]; then
  echo "commit refused by the pre-commit hook" >&2
  exit 1
fi
exit 0
"""


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


# --------------------------------------------------------------------------- windows
def in_commit_stage(window: str, pattern: str, refuse):
    """Stop in the Git stage of the first stage matching ``pattern`` that records a commit.

    ``commit recorded``: right after the stage is durably recorded, nothing of it made.
    ``commit refused``: the stage is recorded and its real ``git commit`` is refused by
    the Project's pre-commit hook; nothing is injected.
    """
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        real(mutation, stage, effects)
        if re.search(pattern, stage) and any(effect.kind == "git_commit" for effect in effects):
            if window == "commit recorded":
                raise Interrupted(f"recorded {stage}")
            refuse(True)

    return mock.patch.object(Mutation, "add_effects", fire)


def before_push(pattern: str):
    """Stop with the commit of the stage matching ``pattern`` made and its push not."""
    real = MutationController.apply_effect

    def fire(controller, record):
        if record["kind"] == "git_push" and re.search(pattern, record["stage"]):
            raise Interrupted("committed, not pushed")
        return real(controller, record)

    return mock.patch.object(MutationController, "apply_effect", fire)


def after_applying(pattern: str):
    """Stop right after the call that applied a stage matching ``pattern``."""
    real = Mutation.apply

    def fire(mutation):
        before = {e["seq"] for e in mutation.record.get("effects") or [] if e.get("applied")}
        outcome = real(mutation)
        if any(e.get("applied") and e["seq"] not in before and re.search(pattern, e["stage"])
               for e in mutation.record.get("effects") or []):
            raise Interrupted(f"applied {pattern}")
        return outcome

    return mock.patch.object(Mutation, "apply", fire)


WINDOWS = ("commit recorded", "commit refused")


class CommitWindowCase(WorklineTestCase):
    def build(self, name: str = "proj", *, bootstrap: bool = True) -> None:
        """A Project with a remote: a Roadmap of Phases A, B and C, and Phase A entered with W1 and W2."""
        self.name = name
        self.store = self.new_project(name, remote=True)
        self.root = self.store.root
        for file in ("notes.md", "a.md", "b.md"):
            (self.root / file).write_text(f"{file}\n", encoding="utf-8")
        git(self.root, "add", "notes.md", "a.md", "b.md")
        git(self.root, "commit", "-q", "-m", "docs: seed notes", "--", "notes.md", "a.md", "b.md")
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B"), "c": ("Phase C", "C")})
        self.rid = roadmap.roadmap_id
        self.pa, self.pb, self.pc = (roadmap.phase_ids[key] for key in "abc")
        entry = self.simple_entry(self.store, self.pa, {"w1": "W1", "w2": "W2"})
        self.w1, self.w2, self.integration = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id
        if not bootstrap:  # a Project from before the bootstrap Skill, so that backfill has something to commit
            git(self.root, "rm", "-q", "--", BOOTSTRAP_REL_PATH)
            git(self.root, "commit", "-q", "-m", "chore: a Project from before the bootstrap Skill")
            git(self.root, "push", "-q", "origin", "main:main")
        hooks = self.root / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        (hooks / "pre-commit").write_text(HOOK, encoding="utf-8", newline="\n")
        os.chmod(hooks / "pre-commit", 0o755)
        git(self.root, "config", "core.hooksPath", hooks.as_posix())
        self.assertEqual(self.head(), self.remote_head())
        self.assertEqual(self.dirty(), [])

    # operations ---------------------------------------------------------------
    def operation(self, name: str):
        """An operation to interrupt: (call, the stage whose commit is interrupted)."""
        store = self.store
        start = lambda: st.start(store, self.w1, "single-work", completing_executor(store))  # noqa: E731
        return {
            "phase hold": (lambda: rm.hold_phase(store, self.pb), r"^finalize$"),
            "phase addition": (lambda: rm.add_phases(store, self.rid, {"z": PhaseSpec("Phase Z", "Z")}), r"^finalize$"),
            "roadmap creation": (lambda: rm.create_roadmap(store, rm.RoadmapPlan(
                "Second", "背景", "達成したい状態", {"s": PhaseSpec("Phase S", "S")})), r"^finalize$"),
            "phase entry": (lambda: rm.enter_phase(store, self.pc, rm.PhaseEntryDesign(
                {"x": rm.WorkDesign("X", "x")}, rm.WorkDesign("IC", "ic"))), r"^finalize$"),
            "related maintenance": (lambda: rm.maintain_work_related(
                store, self.w2, add=(RelatedSpec("must_read", "a.md"),)), r"^finalize$"),
            "start results": (start, rf"^{self.w1}:results:0$"),
            "start finalization": (start, rf"^{self.w1}:finalize:0$"),
        }[name]

    def independent(self, name: str):
        """A commit independent of the interrupted operation: another Workline operation's, or a person's."""
        store = self.store
        return {
            "related maintenance": lambda: rm.maintain_work_related(store, self.w1, add=(RelatedSpec("must_read", "b.md"),)),
            "phase addition": lambda: rm.add_phases(store, self.rid, {"y": PhaseSpec("Phase Y", "Y")}),
            "roadmap creation": lambda: rm.create_roadmap(store, rm.RoadmapPlan(
                "Other", "背景", "達成したい状態", {"o": PhaseSpec("Phase O", "O")})),
            "phase hold": lambda: rm.hold_phase(store, self.pb),
            "human commit": lambda: self.human_commit({"notes.md": "notes\nby a person\n"}, "docs: a note"),
            "human commit pushed": lambda: self.human_commit({"notes.md": "notes\npushed\n"}, "docs: a note", push=True),
            "bootstrap backfill": lambda: bs.backfill_bootstrap(self.root),
        }[name]

    # running ------------------------------------------------------------------
    def refuse_commits(self, on: bool) -> None:
        flag = self.root / ".git" / REFUSE_FLAG
        if on:
            flag.write_text("refuse\n", encoding="utf-8")
        elif flag.exists():
            flag.unlink()

    def interrupt(self, call, pattern: str, window: str) -> dict:
        """Run ``call`` into ``window``; return the record it leaves pending."""
        known = {p["mutation_id"] for p in MutationController(self.store).list_pending()}
        try:
            if window == "committed":
                with before_push(pattern), self.assertRaises(Interrupted):
                    call()
            else:
                expected = Interrupted if window == "commit recorded" else GitError
                with in_commit_stage(window, pattern, self.refuse_commits), self.assertRaises(expected):
                    call()
        finally:
            self.refuse_commits(False)
        (pending,) = [p for p in MutationController(self.store).list_pending() if p["mutation_id"] not in known]
        return pending

    def counting(self, call, executed: list[str], stages: list[str] | None = None):
        """Run ``call``, recording the kind (and, given ``stages``, the stage) of every effect it actually executes."""
        real = MutationController.apply_effect

        def watch(controller, record):
            executed.append(record["kind"])
            if stages is not None:
                stages.append(record["stage"])
            return real(controller, record)

        with mock.patch.object(MutationController, "apply_effect", watch):
            return call()

    def human_commit(self, files: dict[str, str], message: str, *, push: bool = False) -> str:
        for path, text in files.items():
            (self.root / path).write_text(text, encoding="utf-8", newline="\n")
        git(self.root, "add", "--", *files)
        git(self.root, "commit", "-q", "-m", message, "--", *files)
        if push:
            git(self.root, "push", "-q", "origin", "main:main")
        return self.head()

    def push_from_another_clone(self) -> None:
        other = self.tmp / f"{self.name}-other-clone"
        git(self.tmp, "clone", "-q", str(self.remote_path(self.name)), str(other))
        (other / "elsewhere.md").write_text("pushed from another clone\n", encoding="utf-8")
        git(other, "add", "elsewhere.md")
        git(other, "commit", "-q", "-m", "docs: pushed from another clone")
        git(other, "push", "-q", "origin", "main:main")

    def edit_recorded_commit(self, pending: dict, change) -> None:
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        (effect,) = [e for e in record["effects"] if e["kind"] == "git_commit"]
        change(effect["payload"])
        path.write_text(yamlish.dump(record), encoding="utf-8")

    # observation --------------------------------------------------------------
    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote_path(self.name), "rev-parse", "main").strip()

    def dirty(self) -> list[str]:
        status = git(self.root, "status", "--porcelain", "--untracked-files=all").splitlines()
        return [line for line in status if ".workline/runtime/" not in line]

    def pending_ids(self) -> list[str]:
        return [p["mutation_id"] for p in MutationController(self.store).list_pending()]

    def recorded_commit(self, pending: dict, pattern: str = ".") -> dict:
        (effect,) = [e for e in pending["effects"] if e["kind"] == "git_commit" and re.search(pattern, e["stage"])]
        return effect["payload"]

    def blobs(self, paths: list[str], commit: str | None = None) -> dict[str, str | None]:
        """Each path's blob in ``commit``, or what ``git add`` would store for it now (None: no such file)."""
        if commit is not None:
            return {path: (git(self.root, "ls-tree", commit, "--", path).split() or [None] * 3)[2] for path in paths}
        return {
            path: git(self.root, "hash-object", "--path", path, str(self.root / path)).strip()
            if (self.root / path).exists() else None
            for path in paths
        }

    def made_with(self, message: str, since: str) -> str:
        """The one commit since ``since`` that carries ``message``."""
        found = [sha for sha in git(self.root, "rev-list", f"{since}..HEAD").split()
                 if git(self.root, "log", "-1", "--format=%B", sha).strip() == message.strip()]
        self.assertEqual(len(found), 1, f"commits carrying {message!r} since {since}: {found}")
        return found[0]

    def parent(self, commit: str) -> str:
        return git(self.root, "rev-parse", f"{commit}^").strip()

    def snapshot(self) -> dict:
        """Everything a refused retry must leave exactly as it was."""
        return {
            "records": {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))},
            "events": self.store.events_jsonl.read_bytes(),
            "roadmap relations": (self.root / ROADMAP_RELATIONS).read_bytes(),
            "head": self.head(),
            "branch": git(self.root, "symbolic-ref", "HEAD").strip(),
            "main": git(self.root, "rev-parse", "main").strip(),
            "remote": self.remote_head(),
            "dirty": self.dirty(),
        }

    def assertMadeOnTop(self, operation: str, independent: str, window: str) -> None:
        """The interrupted commit is made once, exactly as decided, on top of the independent commit."""
        call, pattern = self.operation(operation)
        pending = self.interrupt(call, pattern, window)
        (stage,) = {e["stage"] for e in pending["effects"] if e["kind"] == "git_commit" and re.search(pattern, e["stage"])}
        recorded = self.recorded_commit(pending, pattern)
        decided = self.blobs(recorded["paths"])
        self.independent(independent)()
        moved_to = self.head()
        self.assertNotEqual(moved_to, recorded["base_head"])
        self.assertEqual(git(self.root, "rev-list", "--full-history", f"{recorded['base_head']}..{moved_to}",
                             "--", *recorded["paths"]), "")  # the independent commit left the paths alone
        executed: list[str] = []
        stages: list[str] = []

        result = self.counting(call, executed, stages)

        self.assertEqual(result.mutation_id, pending["mutation_id"])
        ran = list(zip(stages, executed))
        self.assertEqual(ran.count((stage, "git_commit")), 1)
        # Nothing recorded before it runs again. A push recorded before it is replayed as it always was: it
        # pushes whatever the branch holds, so a person's unpushed commit is published with it (not new here).
        self.assertTrue(all(kind == "git_push" for _, kind in ran[:ran.index((stage, "git_commit"))]), ran)
        made = self.made_with(recorded["message"], moved_to)
        self.assertEqual(self.parent(made), moved_to)
        changed = git(self.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "--no-renames", made).split()
        self.assertTrue(changed and set(changed) <= set(recorded["paths"]), changed)
        self.assertEqual(self.blobs(recorded["paths"], made), decided)
        self.assertEqual(self.head(), self.remote_head())
        self.assertNothingLeftOver()
        (record,) = [r for r in MutationController(self.store).list_records() if r["mutation_id"] == pending["mutation_id"]]
        self.assertEqual(record["status"], "completed")
        self.assertEqual(recorded["branch"], MAIN)

    def assertNothingLeftOver(self) -> None:
        self.assertEqual(self.pending_ids(), [])
        self.assertEqual(self.dirty(), [])
        self.assertEqual(validate_project(self.store), [])

    def assertStopsUntouched(self, call) -> None:
        """The retry refuses at the recorded commit, having executed nothing and changed nothing."""
        before, executed = self.snapshot(), []
        with self.assertRaises(StopError) as stopped:
            self.counting(call, executed)
        self.assertEqual(stopped.exception.code, "reconcile_required")
        self.assertIn("(git_commit) applied with unexpected result", stopped.exception.message)
        self.assertEqual(executed, [])
        self.assertEqual(self.snapshot(), before)


# --------------------------------------------------------------------------- made on top
class IndependentCommitTests(CommitWindowCase):
    """Whatever committed in between - an independent Workline operation or a person - the commit is made after it."""

    def test_a_hold_is_committed_after_each_kind_of_independent_commit(self) -> None:
        cases = [(kind, "commit recorded") for kind in (
            "related maintenance",  # a disjoint scope, writing a file of its own
            "phase addition",  # the same Roadmap, another entity
            "roadmap creation",  # another Roadmap
            "human commit",
            "human commit pushed",
            "bootstrap backfill",
        )] + [("related maintenance", "commit refused"), ("human commit", "commit refused")]
        for index, (independent, window) in enumerate(cases):
            with self.subTest(independent=independent, window=window):
                self.build(f"kind-{index}", bootstrap=independent != "bootstrap backfill")
                self.assertMadeOnTop("phase hold", independent, window)
                # the event log the hold owns no longer holds anything up
                self.assertEqual(rm.hold_phase(self.store, self.pc).status, "phase_held")

    def test_every_owner_commits_after_an_independent_commit(self) -> None:
        cases = [(operation, independent, "commit recorded") for operation, independent in (
            ("related maintenance", "phase hold"),  # the independent commit only appends an event
            ("phase addition", "phase hold"),
            ("roadmap creation", "related maintenance"),
            ("phase entry", "phase hold"),
            ("start results", "human commit"),
            ("start finalization", "human commit"),
            ("start finalization", "bootstrap backfill"),
        )] + [("phase entry", "phase hold", "commit refused"), ("start finalization", "human commit", "commit refused")]
        for index, (operation, independent, window) in enumerate(cases):
            with self.subTest(operation=operation, independent=independent, window=window):
                self.build(f"owner-{index}", bootstrap=independent != "bootstrap backfill")
                self.assertMadeOnTop(operation, independent, window)

    def test_two_unfinished_commits_are_both_made_in_either_order(self) -> None:
        for index, (window, order) in enumerate(product(("commit recorded", "committed"), ("hold first", "maintenance first"))):
            with self.subTest(maintenance_window=window, order=order):
                self.build(f"both-{index}")
                hold, pattern = self.operation("phase hold")
                maintenance = self.independent("related maintenance")
                held = self.interrupt(hold, pattern, "commit recorded")
                maintained = self.interrupt(maintenance, r"^finalize$", window)

                results = [call() for call in ((hold, maintenance) if order == "hold first" else (maintenance, hold))]

                self.assertEqual({r.mutation_id for r in results}, {held["mutation_id"], maintained["mutation_id"]})
                for pending in (held, maintained):
                    recorded = self.recorded_commit(pending)
                    self.made_with(recorded["message"], recorded["base_head"])
                self.assertEqual(self.head(), self.remote_head())
                self.assertNothingLeftOver()

    def test_a_branch_that_moved_on_remotely_is_committed_on_once_pulled(self) -> None:
        self.build()
        call, pattern = self.operation("phase hold")
        pending = self.interrupt(call, pattern, "commit recorded")
        self.push_from_another_clone()
        git(self.root, "pull", "-q", "--ff-only", "origin", "main")
        pulled, executed = self.head(), []

        result = self.counting(call, executed)

        self.assertEqual((result.status, result.mutation_id), ("phase_held", pending["mutation_id"]))
        self.assertEqual(executed, ["git_commit", "git_push"])
        self.assertEqual(self.parent(self.made_with(self.recorded_commit(pending)["message"], pulled)), pulled)
        self.assertEqual(self.head(), self.remote_head())
        self.assertNothingLeftOver()


# --------------------------------------------------------------------------- START
class StartTests(CommitWindowCase):
    def test_a_completion_is_finalized_after_an_independent_commit(self) -> None:
        """From each window before the completion commit is made, the START that recorded it continues."""
        windows = {
            "completion applied": lambda: after_applying(rf"^{self.w1}:lifecycle:1$"),  # BL-031: finalization not recorded
            "finalization recorded": lambda: in_commit_stage("commit recorded", rf"^{self.w1}:finalize:0$", self.refuse_commits),
            "finalization refused": lambda: in_commit_stage("commit refused", rf"^{self.w1}:finalize:0$", self.refuse_commits),
        }
        for index, window in enumerate(windows):
            with self.subTest(window=window):
                self.build(f"finalize-{index}")
                call = lambda: st.start(self.store, self.w1, "outer", completing_executor(self.store))  # noqa: E731
                try:
                    with windows[window](), self.assertRaises((Interrupted, GitError)):
                        call()
                finally:
                    self.refuse_commits(False)
                (pending,) = MutationController(self.store).list_pending()
                moved_to = self.human_commit({"notes.md": "notes\nduring the finalization\n"}, "docs: a note")

                result = call()

                self.assertEqual((result.status, result.mutation_id), ("phase_complete", pending["mutation_id"]))
                display = ProjectView.load(self.store).works[self.w1].display
                self.assertEqual(self.parent(self.made_with(f"chore(workline): complete {display}", moved_to)), moved_to)
                self.assertEqual(self.head(), self.remote_head())
                self.assertNothingLeftOver()

    def test_an_outer_cancel_is_committed_after_an_independent_commit(self) -> None:
        """The commit of a replan START recorded is carried the same way (a plan exclusion stops before it, BL-029)."""
        self.build()
        s1, s2, helper = (create_standalone_work(self.store, WorkSpec(n, n.lower())).work_id for n in ("S1", "S2", "Helper"))
        st.plan_exclude_standalone_work(self.store, helper, Replan(add_relations=(RelationSpec("planned_next", s1, s2),)))
        done = completing_executor(self.store)
        cancel = st.Cancel(Replan(), "not needed")
        call = lambda: st.start(self.store, s1, "outer", lambda ctx: cancel if ctx.work.id == s2 else done(ctx))  # noqa: E731
        pending = self.interrupt(call, r"^commit:\d+$", "commit recorded")
        moved_to = self.human_commit({"notes.md": "notes\nduring the cancel\n"}, "docs: a note")

        result = call()

        self.assertEqual((result.status, result.mutation_id), ("stopped", pending["mutation_id"]))
        self.assertEqual(self.parent(self.made_with(self.recorded_commit(pending, r"^commit:\d+$")["message"], moved_to)), moved_to)
        self.assertEqual(self.head(), self.remote_head())
        self.assertNothingLeftOver()


# --------------------------------------------------------------------------- still a mismatch
class StillMismatchTests(CommitWindowCase):
    """Only a branch that provably grew past the commit is continued; everything else is left for a human."""

    def interrupted(self, operation: str = "phase hold", window: str = "commit recorded"):
        call, pattern = self.operation(operation)
        pending = self.interrupt(call, pattern, window)
        return call, pending, self.recorded_commit(pending, pattern)

    def other_event(self) -> str:
        return '{"id":"%s","type":"phase_held","entity":"%s","at":"2026-01-01T00:00:00+00:00"}\n' % (new_id("event"), self.pc)

    def test_a_recorded_path_committed_with_other_content(self) -> None:
        self.build()
        call, _, _ = self.interrupted()
        decided = self.store.events_jsonl.read_text(encoding="utf-8")
        committed = git(self.root, "show", f"HEAD:{EVENT_LOG}")
        other = self.other_event()
        self.human_commit({EVENT_LOG: committed + other}, "chore: a person recorded another event")
        (self.root / EVENT_LOG).write_text(committed + other + decided[len(committed):], encoding="utf-8", newline="\n")

        self.assertStopsUntouched(call)

    def test_part_of_the_recorded_paths_committed_on_its_own(self) -> None:
        for index, window in enumerate(WINDOWS):
            with self.subTest(window=window):
                self.build(f"partial-{index}")
                call, _, recorded = self.interrupted("phase entry", window)
                self.assertIn(ROADMAP_RELATIONS, recorded["paths"])
                self.assertGreater(len(recorded["paths"]), 1)
                git(self.root, "add", "--", ROADMAP_RELATIONS)
                git(self.root, "commit", "-q", "-m", "chore: a person committed part of it", "--", ROADMAP_RELATIONS)

                self.assertStopsUntouched(call)

    def test_one_recorded_path_committed_along_with_something_else(self) -> None:
        self.build()
        call, _, recorded = self.interrupted("roadmap creation")
        self.assertEqual(len(recorded["paths"]), 2)
        (phase_file,) = [p for p in recorded["paths"] if "/phases/" in p]
        (self.root / "notes.md").write_text("notes\nand a Phase\n", encoding="utf-8")
        git(self.root, "add", "--", "notes.md", phase_file)
        git(self.root, "commit", "-q", "-m", "docs: notes", "--", "notes.md", phase_file)

        self.assertStopsUntouched(call)

    def test_a_recorded_path_changed_and_changed_back(self) -> None:
        """The path ends up as it was, but someone changed what the commit owns in between."""
        self.build()
        call, _, recorded = self.interrupted()
        decided = self.store.events_jsonl.read_text(encoding="utf-8")
        committed = git(self.root, "show", f"HEAD:{EVENT_LOG}")
        self.human_commit({EVENT_LOG: committed + self.other_event()}, "chore: a person recorded another event")
        self.human_commit({EVENT_LOG: committed}, "chore: a person took it back")
        (self.root / EVENT_LOG).write_text(decided, encoding="utf-8", newline="\n")
        self.assertEqual(git(self.root, "diff", "--name-only", recorded["base_head"], "HEAD", "--", EVENT_LOG), "")

        self.assertStopsUntouched(call)

    def test_the_commit_someone_made_for_it_and_then_reverted(self) -> None:
        """A revert in the history is a decision about these paths; the commit is not made over it."""
        self.build()
        call, pending, recorded = self.interrupted()
        git(self.root, "commit", "-q", "-m", "chore: a person committed the hold", "--", EVENT_LOG)
        git(self.root, "revert", "--no-edit", "HEAD")
        self.assertEqual(git(self.root, "diff", "--name-only", recorded["base_head"], "HEAD", "--", EVENT_LOG), "")
        before, executed = self.snapshot(), []

        with self.assertRaises(StopError) as stopped:
            self.counting(call, executed)

        self.assertEqual(stopped.exception.code, "reconcile_required")
        self.assertIn("(git_commit) applied with unexpected result", stopped.exception.message)
        # the event the revert took out of the working tree is replayed, as it always was - and nothing more
        self.assertEqual(executed, ["append_event"])
        unchanged = ("records", "roadmap relations", "head", "branch", "main", "remote")
        self.assertEqual({k: self.snapshot()[k] for k in unchanged}, {k: before[k] for k in unchanged})
        self.assertEqual(self.pending_ids(), [pending["mutation_id"]])

    def test_another_branch(self) -> None:
        self.build()
        call, _, _ = self.interrupted()
        git(self.root, "checkout", "-q", "-b", "side")
        self.human_commit({"notes.md": "notes\non a side branch\n"}, "docs: work on a side branch")

        self.assertStopsUntouched(call)
        self.assertEqual(git(self.root, "rev-parse", "main").strip(), self.remote_head())

    def test_a_rewritten_history(self) -> None:
        rewrites = {
            "amended": lambda: git(self.root, "commit", "-q", "--amend", "--only", "-m", "chore: amended"),
            "reset and committed again": lambda: (git(self.root, "reset", "-q", "--soft", "HEAD~1"),
                                                  git(self.root, "commit", "-q", "-m", "chore: committed again")),
        }
        for index, rewrite in enumerate(rewrites):
            with self.subTest(rewrite=rewrite):
                self.build(f"rewrite-{index}")
                call, _, recorded = self.interrupted("related maintenance")
                rewrites[rewrite]()
                self.assertIn(recorded["base_head"], git(self.root, "rev-list", "--all", "--reflog"))
                self.assertNotIn(recorded["base_head"], git(self.root, "rev-list", "HEAD"))

                self.assertStopsUntouched(call)

    def test_a_base_the_record_does_not_name_as_a_commit(self) -> None:
        self.build()
        call, pending, recorded = self.interrupted()
        self.human_commit({"notes.md": "notes\nmoved on\n"}, "docs: a note")
        base = recorded["base_head"]
        bases = {
            "missing": lambda payload: payload.pop("base_head"),
            "null": lambda payload: payload.update(base_head=None),
            "a revision expression": lambda payload: payload.update(base_head="HEAD~1"),
            "abbreviated": lambda payload: payload.update(base_head=base[:12]),
            "upper case": lambda payload: payload.update(base_head=base.upper()),
            "no such object": lambda payload: payload.update(base_head="0" * 40),
            "not a commit": lambda payload: payload.update(base_head=git(self.root, "rev-parse", f"{base}^{{tree}}").strip()),
        }
        for label, change in bases.items():
            with self.subTest(base=label):
                self.edit_recorded_commit(pending, lambda payload: payload.update(base_head=base))
                self.edit_recorded_commit(pending, change)

                self.assertStopsUntouched(call)

    def test_a_record_that_does_not_show_the_branch(self) -> None:
        self.build()
        call, pending, _ = self.interrupted()
        self.human_commit({"notes.md": "notes\nmoved on\n"}, "docs: a note")
        branches = {
            # exactly what every implementation from before the branch was recorded writes
            "written before the branch was recorded": lambda payload: payload.pop("branch"),
            "null": lambda payload: payload.update(branch=None),
            "empty": lambda payload: payload.update(branch=""),
            "the short name": lambda payload: payload.update(branch="main"),
            "another branch": lambda payload: payload.update(branch="refs/heads/other"),
            "not text": lambda payload: payload.update(branch=5),
        }
        for label, change in branches.items():
            with self.subTest(branch=label):
                self.edit_recorded_commit(pending, lambda payload: payload.update(branch=MAIN))
                self.edit_recorded_commit(pending, change)
                if label.startswith("written before"):
                    (current,) = MutationController(self.store).list_pending()
                    self.assertEqual(set(self.recorded_commit(current)), {"message", "paths", "base_head"})

                self.assertStopsUntouched(call)

    def test_a_question_git_cannot_answer(self) -> None:
        self.build()
        call, _, _ = self.interrupted()
        self.human_commit({"notes.md": "notes\nmoved on\n"}, "docs: a note")
        real = gitcmd.run_git
        questions = {
            "which branch HEAD is on": ("symbolic-ref", "--quiet"),
            "whether the base is an ancestor of HEAD": ("merge-base", "--is-ancestor"),
            "which commits changed the paths": ("rev-list", "--full-history"),
        }
        for label, command in questions.items():
            with self.subTest(question=label):
                def unanswered(repo, *args, check=True, command=command):
                    if args[:2] == command:
                        return gitcmd.GitResult(128, "", "fatal: cannot answer")
                    return real(repo, *args, check=check)

                with mock.patch.object(gitcmd, "run_git", unanswered):
                    self.assertStopsUntouched(call)

    def test_a_remote_that_alone_moved_on_still_refuses_the_push(self) -> None:
        """Unchanged: HEAD is still the base, so the commit is made, and the push is refused as before."""
        self.build()
        call, pending, recorded = self.interrupted()
        self.push_from_another_clone()
        remote, executed = self.remote_head(), []

        with self.assertRaises(StopError) as stopped:
            self.counting(call, executed)

        self.assertEqual(stopped.exception.code, "reconcile_required")
        self.assertIn("would reject this push", stopped.exception.message)
        self.assertEqual(executed, ["git_commit"])
        self.assertEqual(self.parent(self.head()), recorded["base_head"])
        self.assertEqual(self.remote_head(), remote)
        self.assertEqual(self.pending_ids(), [pending["mutation_id"]])


# --------------------------------------------------------------------------- the recorded branch
class RecordedBranchTests(WorklineTestCase):
    def test_a_commit_records_the_full_name_of_its_branch_and_none_off_a_branch(self) -> None:
        store = self.new_project()
        (effect,) = gitops.finalize_effects(store, "chore: a commit", [EVENT_LOG], destination=None)
        self.assertEqual(effect.payload["branch"], MAIN)
        git(store.root, "checkout", "-q", "--detach")
        (effect,) = gitops.finalize_effects(store, "chore: a commit", [EVENT_LOG], destination=None)
        self.assertEqual(set(effect.payload), {"message", "paths", "base_head"})

    def test_only_the_full_name_of_a_branch_is_recorded(self) -> None:
        controller = MutationController(self.new_project())

        def commit(**branch):
            payload = {"message": "chore: a commit", "paths": [EVENT_LOG], "base_head": None, **branch}
            return {"seq": 1, "stage": "finalize", "kind": "git_commit", "payload": payload, "applied": False}

        controller.validate_effect(commit(), [], rm.OWNER)
        controller.validate_effect(commit(branch=MAIN), [], rm.OWNER)
        for branch in (None, "", "main", "refs/heads/", "refs/tags/v1", 5):
            with self.subTest(branch=branch), self.assertRaises(ValidationError):
                controller.validate_effect(commit(branch=branch), [], rm.OWNER)


# --------------------------------------------------------------------------- unchanged
class KnownResidualTests(CommitWindowCase):
    def test_a_commit_carrying_the_recorded_message_is_still_taken_for_it(self) -> None:
        """BL-033, unchanged: the recorded message is looked for before HEAD's movement is considered."""
        self.build()
        call, pattern = self.operation("phase hold")
        pending = self.interrupt(call, pattern, "commit recorded")
        self.human_commit({"notes.md": "notes\nsame message\n"}, self.recorded_commit(pending)["message"])
        executed: list[str] = []

        result = self.counting(call, executed)

        self.assertEqual((result.status, result.mutation_id), ("phase_held", pending["mutation_id"]))
        self.assertEqual(executed, ["git_push"])  # the recorded commit is never made
        self.assertEqual(self.dirty(), [f" M {EVENT_LOG}"])


if __name__ == "__main__":
    unittest.main()
