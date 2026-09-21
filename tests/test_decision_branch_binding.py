"""A decision is finalized only on the branch it was decided on (BL-036).

An operation decides Project content - a lifecycle event, a registration, a Related change, a Project's own
files - records it, applies it, and only then records the commit that finalizes it (``rules/git``: Multi-write
mutation, Commit / push). The commit recorded its branch from the moment it was recorded (BL-032 / BL-035), but
nothing recorded where the decision itself had been made. An operation interrupted after its decision was
recorded or applied and before its commit was recorded was retried on whatever branch HEAD was on: after a
person checked out another branch, the retry recorded the commit there, made and pushed it, returned success
and closed its mutation. The branch the decision was made on and its remote never received it, and
``validate_project`` reported nothing. START's completion, hold and the whole outer continuation, Roadmap
lifecycle and registration, Related maintenance, direct CREATE, bootstrap backfill, pin maintenance and
Project開始 all did so.

A stage that decides Project content now carries where it was decided - the full name of the branch HEAD was
on, or none on a detached HEAD, and the commit HEAD was at - in the same durable save. Until the commit that
finalizes it is recorded, the mutation is replayed and recorded only while HEAD is still on that branch over a
history holding that commit; the commit recorded then names that same branch, and the recorded commit's own
branch guards it from there. Anywhere else the retry stops with nothing replayed, recorded, committed or pushed,
and back on the branch the same retry goes on. START decides what a Work produced only once its executor has
returned, so a branch change before that - by the executor, during a question wait - binds nothing. A decision
recorded without its branch, and a question Git cannot answer, show no branch and stop.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from helpers import WORKLINE_ROOT, completing_executor, cwd, git
from test_recorded_commit_resume import MAIN, CommitWindowCase, Interrupted, after_applying
from workline import bootstrap as bs
from workline import gitcmd, gitops
from workline import roadmap as rm
from workline import start as st
from workline import yamlish
from workline.create import RelatedSpec, WorkSpec, create_standalone_work
from workline.errors import GitError, StopError
from workline.mutation import CLOSED_RECORD_FIELDS, EFFECT_KINDS, INTENT_VERSION, Mutation, MutationController
from workline.ops import Replan
from workline.phase_create import PhaseSpec
from workline.project_start import project_start
from workline.push_pin import pin_push_destination
from workline.store import ProjectStore
from workline.validate import validate_project

SIDE = "refs/heads/side"
#: The key under which a decided effect records where it was decided (rules/git: Commit / push).
DECIDED_ON = "decided_on"


def after_recording(pattern: str):
    """Stop right after a stage matching ``pattern`` is durably recorded, none of it applied."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        real(mutation, stage, effects)
        if re.search(pattern, stage):
            raise Interrupted(f"recorded {stage}")

    return mock.patch.object(Mutation, "add_effects", fire)


class DecisionCase(CommitWindowCase):
    """A Project with a remote (``CommitWindowCase.build``) and the decisions its owners record."""

    def setUp(self) -> None:
        super().setUp()
        self.ran: list[str] = []

    # decisions ------------------------------------------------------------------
    def decision(self, name: str):
        """(call, the stage whose decision is interrupted, the stage last applied before its commit)."""
        store = self.store
        if name in ("start completion", "outer completion", "start hold"):
            mode = "outer" if name == "outer completion" else "single-work"
            executor = self.holding() if name == "start hold" else completing_executor(store, self.ran)
            stage = rf"^{self.w1}:lifecycle:1$"
            return lambda: st.start(store, self.w1, mode, executor), stage, stage
        if name in ("phase hold", "phase cancel"):
            operation = rm.hold_phase if name == "phase hold" else rm.cancel_phase
            phase = self.pb if name == "phase hold" else self.pc
            return lambda: operation(store, phase), r"^event$", r"^event$"
        if name == "phase entry":
            design = rm.PhaseEntryDesign({"x": rm.WorkDesign("X", "x")}, rm.WorkDesign("IC", "ic"))
            return lambda: rm.enter_phase(store, self.pc, design), r"^works$", r"^integration$"
        if name == "phase addition":
            return lambda: rm.add_phases(store, self.rid, {"z": PhaseSpec("Phase Z", "Z")}), r"^phases$", r"^phases$"
        if name == "roadmap creation":
            plan = rm.RoadmapPlan("Second", "背景", "達成したい状態", {"s": PhaseSpec("Phase S", "S")})
            return lambda: rm.create_roadmap(store, plan), r"^roadmap$", r"^phases$"
        if name == "related maintenance":
            return (lambda: rm.maintain_work_related(store, self.w2, add=(RelatedSpec("must_read", "a.md"),)),
                    r"^related$", r"^related$")
        if name == "direct creation":
            return lambda: create_standalone_work(store, WorkSpec("Solo", "solo")), r"^register$", r"^register$"
        if name == "bootstrap backfill":
            return lambda: bs.backfill_bootstrap(self.root), r"^bootstrap$", r"^bootstrap$"
        if name == "pin maintenance":
            return lambda: pin_push_destination(self.root, [self.remote_url(self.name)]), r"^pin$", r"^pin$"
        if name == "project start":
            return self.initialize, r"^create$", r"^create$"
        raise AssertionError(name)

    def holding(self):
        def execute(ctx):
            self.ran.append(ctx.work.id)
            return st.Hold("later")
        return execute

    def world(self, name: str, decision: str) -> None:
        """The Project (or the folder) ``decision`` needs."""
        if decision == "project start":
            self.repository(name)
        elif decision == "pin maintenance":
            self.name = name
            self.store = self.new_project(name, remote=True, pin=False)
            self.root = self.store.root
            git(self.root, "push", "-q", "origin", "main:main")
        else:
            self.build(name, bootstrap=decision != "bootstrap backfill")
        self.ran = []

    def repository(self, name: str, *, committed: bool = True, detached: bool = False) -> None:
        """A folder holding a repository on main, for Project開始 (no remote)."""
        self.name = name
        self.root = self.new_dir(name)
        git(self.root, "init", "-q", "-b", "main")
        if committed:
            (self.root / "notes.md").write_text("notes\n", encoding="utf-8")
            git(self.root, "add", "notes.md")
            git(self.root, "commit", "-q", "-m", "docs: notes")
        if detached:
            git(self.root, "checkout", "-q", "--detach")
        self.store = ProjectStore(self.root)

    def initialize(self):
        with cwd(WORKLINE_ROOT):
            return project_start(self.root, WORKLINE_ROOT)

    # running ------------------------------------------------------------------------
    def stop_in(self, window, call) -> dict:
        """Run ``call`` into ``window``; return the record it leaves pending."""
        known = {p["mutation_id"] for p in MutationController(self.store).list_pending()}
        with window, self.assertRaises(Interrupted):
            call()
        (pending,) = [p for p in MutationController(self.store).list_pending() if p["mutation_id"] not in known]
        return pending

    def decided(self, decision: str) -> tuple:
        """Interrupt ``decision`` with its last canonical stage applied and its commit not recorded (W2)."""
        call, _, last = self.decision(decision)
        return call, self.stop_in(after_applying(last), call)

    # observation --------------------------------------------------------------------
    def on(self) -> str | None:
        return git(self.root, "symbolic-ref", "--quiet", "HEAD", check=False).strip() or None

    def snapshot(self) -> dict:
        """Everything a refused retry must leave exactly as it was - the records byte for byte."""
        remote = self.remote_path(self.name)
        return {
            "records": {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))},
            "files": {p.relative_to(self.root).as_posix(): p.read_bytes()
                      for p in sorted((self.root / ".workline").rglob("*"))
                      if p.is_file() and "runtime" not in p.relative_to(self.root).parts},
            "head": git(self.root, "rev-parse", "--verify", "--quiet", "HEAD", check=False).strip(),
            "on": self.on(),
            "refs": git(self.root, "for-each-ref", "--format=%(refname) %(objectname)"),
            "remote refs": git(remote, "for-each-ref", "--format=%(refname) %(objectname)") if remote.exists() else None,
            "index": git(self.root, "diff", "--cached", "--name-status"),
            "dirty": self.dirty(),
        }

    def assertStopsUntouched(self, call, *, fragment: str = "no recorded commit finalizes") -> StopError:
        """The retry stops before replaying anything: no effect executed, no executor run, nothing changed."""
        before, ran, executed = self.snapshot(), list(self.ran), []
        with self.assertRaises(StopError) as stopped:
            self.counting(call, executed)
        self.assertEqual(stopped.exception.code, "reconcile_required", stopped.exception.message)
        self.assertIn(fragment, stopped.exception.message)
        self.assertEqual(executed, [])
        self.assertEqual(self.ran, ran)
        self.assertEqual(self.snapshot(), before)
        return stopped.exception

    def assertFinalizedHere(self, pending: dict) -> None:
        """The same mutation finished: its commit is on the branch HEAD is on - and at its remote - and nothing is left."""
        records = {r["mutation_id"]: r for r in MutationController(self.store).list_records()}
        self.assertEqual(records[pending["mutation_id"]]["status"], "completed")
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(self.dirty(), [])
        self.assertEqual(validate_project(self.store), [])
        remote = self.remote_path(self.name)
        if remote.exists():
            branch = self.on().removeprefix("refs/heads/")
            self.assertEqual(git(remote, "rev-parse", branch).strip(), self.head())

    def strip_bindings(self, pending: dict) -> None:
        """Rewrite the record as an implementation before BL-036 wrote it: no decision carries its branch."""
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        for effect in record["effects"]:
            effect.pop(DECIDED_ON, None)
        path.write_text(yamlish.dump(record), encoding="utf-8")


# --------------------------------------------------------------------------- W1 / W2 on another branch
class OtherBranchTests(DecisionCase):
    OWNERS = ("start completion", "outer completion", "start hold", "phase hold", "phase cancel", "phase entry",
              "phase addition", "roadmap creation", "related maintenance", "direct creation", "bootstrap backfill",
              "pin maintenance", "project start")

    def test_a_decision_is_not_finalized_on_another_branch_by_any_owner(self) -> None:
        for index, owner in enumerate(self.OWNERS):
            with self.subTest(owner=owner):
                self.world(f"other-{index}", owner)
                call, pending = self.decided(owner)
                ran = list(self.ran)
                git(self.root, "checkout", "-q", "-b", "side")

                self.assertStopsUntouched(call)

                git(self.root, "checkout", "-q", "main")
                call()
                self.assertFinalizedHere(pending)
                self.assertEqual(self.on(), MAIN)
                if owner != "outer completion":  # the one commit sits right on the decided base, which side never left
                    self.assertEqual(git(self.root, "rev-parse", "side").strip(), git(self.root, "rev-parse", "HEAD~1").strip())
                if owner in ("start completion", "outer completion"):
                    self.assertEqual(self.ran[:len(ran)], ran)
                    self.assertEqual(self.ran.count(self.w1), 1)  # the executor was not asked again

    def test_a_decision_recorded_and_not_applied_is_not_replayed_on_another_branch(self) -> None:
        for index, owner in enumerate(("start completion", "phase hold", "phase entry", "project start")):
            with self.subTest(owner=owner):
                self.world(f"recorded-{index}", owner)
                call, decided, _ = self.decision(owner)
                pending = self.stop_in(after_recording(decided), call)
                git(self.root, "checkout", "-q", "-b", "side")

                self.assertStopsUntouched(call)

                git(self.root, "checkout", "-q", "main")
                call()
                self.assertFinalizedHere(pending)

    def test_every_other_place_stops_and_the_decided_branch_goes_on(self) -> None:
        places = {
            "a branch with an independent commit": lambda: (
                git(self.root, "checkout", "-q", "-b", "side"),
                self.human_commit({"notes.md": "notes\non side\n"}, "docs: on side")),
            "a branch with the history rewritten": lambda: (
                git(self.root, "checkout", "-q", "-b", "side"),
                git(self.root, "commit", "-q", "--amend", "--only", "-m", "chore: rewritten")),
            "the same branch with the history rewritten": lambda: git(self.root, "commit", "-q", "--amend", "--only", "-m", "chore: rewritten"),
        }
        for index, ((label, move), owner) in enumerate((p, o) for p in places.items() for o in ("start completion", "phase hold")):
            with self.subTest(place=label, owner=owner):
                self.world(f"place-{index}", owner)
                call, pending = self.decided(owner)
                decided_at = self.head()
                move()

                self.assertStopsUntouched(call)

                if label.startswith("the same branch"):
                    git(self.root, "reset", "-q", "--keep", decided_at)
                else:
                    git(self.root, "checkout", "-q", "main")
                call()
                self.assertFinalizedHere(pending)
                self.assertEqual(self.on(), MAIN)

    def test_a_decision_made_on_another_branch_stops_on_main(self) -> None:
        for index, owner in enumerate(("start completion", "phase hold")):
            with self.subTest(owner=owner):
                self.world(f"from-side-{index}", owner)
                git(self.root, "checkout", "-q", "-b", "side")
                git(self.root, "push", "-q", "origin", "side")
                call, pending = self.decided(owner)
                git(self.root, "checkout", "-q", "main")

                self.assertStopsUntouched(call)

                git(self.root, "checkout", "-q", "side")
                call()
                self.assertFinalizedHere(pending)
                self.assertEqual((self.on(), git(self.root, "rev-parse", "main").strip()),
                                 (SIDE, self.remote_head()))


# --------------------------------------------------------------------------- where the decision was made
class DecidedBranchTests(DecisionCase):
    def test_the_decided_branch_resumes_the_same_mutation(self) -> None:
        moves = {
            "stayed": lambda: None,
            "left and came back": lambda: (git(self.root, "checkout", "-q", "-b", "side"), git(self.root, "checkout", "-q", "main")),
            "grew by an independent commit": lambda: self.human_commit({"notes.md": "notes\nby a person\n"}, "docs: a note"),
        }
        for index, ((label, move), owner) in enumerate((m, o) for m in moves.items() for o in ("start completion", "phase hold")):
            with self.subTest(move=label, owner=owner):
                self.world(f"decided-{index}", owner)
                call, pending = self.decided(owner)
                ran = list(self.ran)
                move()
                executed: list[str] = []

                self.counting(call, executed)

                # nothing decided is applied again and one commit is made (an earlier stage's recorded push may
                # also publish the independent commit: BL-032's residual, not this one)
                self.assertEqual([kind for kind in executed if kind != "git_push"], ["git_commit"])
                self.assertEqual(self.ran, ran)
                self.assertFinalizedHere(pending)

    def test_a_decision_made_on_another_branch_resumes_there(self) -> None:
        self.world("on-side", "start completion")
        git(self.root, "checkout", "-q", "-b", "side")
        git(self.root, "push", "-q", "origin", "side")
        call, pending = self.decided("start completion")

        call()

        self.assertFinalizedHere(pending)
        self.assertEqual(self.on(), SIDE)
        self.assertEqual(git(self.root, "rev-parse", "main").strip(), self.remote_head())  # main never received it

    def test_a_decision_carries_where_it_was_made_and_hands_it_to_its_commit(self) -> None:
        self.world("shape", "start completion")
        call, _, _ = self.decision("start completion")
        pending = self.interrupt(call, rf"^{self.w1}:finalize:0$", "commit refused")
        by_stage: dict[str, list] = {}
        for effect in pending["effects"]:
            by_stage.setdefault(effect["stage"].split(":", 1)[1], []).append(effect)
        (commit,) = [e for e in by_stage["finalize:0"] if e["kind"] == "git_commit"]
        binding = {"branch": MAIN, "head": commit["payload"]["base_head"]}

        self.assertEqual([DECIDED_ON in e for e in by_stage["lifecycle:0"]], [False, False])  # opened before the executor ran
        self.assertEqual([e.get(DECIDED_ON) for e in by_stage["lifecycle:1"]], [binding, binding])
        self.assertTrue(all(DECIDED_ON not in e for e in by_stage["results:0"] + by_stage["finalize:0"]))
        self.assertEqual(commit["payload"]["branch"], binding["branch"])
        self.assertEqual(set(pending), CLOSED_RECORD_FIELDS - {"completed_at"})
        # once the commit is recorded, the recorded commit's own branch decides (BL-035), not the binding
        git(self.root, "checkout", "-q", "-b", "side")
        self.assertStopsUntouched(call, fragment="applied with unexpected result")
        # and a branch that only grew still takes the commit (BL-032)
        git(self.root, "checkout", "-q", "main")
        grown = self.human_commit({"notes.md": "notes\ngrown\n"}, "docs: grown")
        call()
        self.assertEqual(self.parent(self.made_with(f"chore(workline): complete {self.display(self.w1)}", grown)), grown)
        self.assertFinalizedHere(pending)

    def display(self, work_id: str) -> str:
        from workline.state import ProjectView

        return ProjectView.load(self.store).works[work_id].display

    def test_a_commit_is_recorded_only_where_its_decision_was_made(self) -> None:
        cases = {
            "HEAD moved before the commit was recorded": lambda real: lambda store, message, paths, *, destination: (
                git(self.root, "checkout", "-q", "-b", "side"), real(store, message, paths, destination=destination))[1],
            "the commit names another branch": lambda real: lambda store, message, paths, *, destination: [
                gitops.Effect(e.kind, {**e.payload, "branch": "refs/heads/other"}) if e.kind == "git_commit" else e
                for e in real(store, message, paths, destination=destination)],
        }
        for index, (label, double) in enumerate(cases.items()):
            with self.subTest(case=label):
                self.world(f"handoff-{index}", "phase hold")
                call, _, _ = self.decision("phase hold")
                with mock.patch.object(gitops, "finalize_effects", double(gitops.finalize_effects)), \
                        self.assertRaises(StopError) as stopped:
                    call()
                self.assertEqual(stopped.exception.code, "reconcile_required")
                (pending,) = MutationController(self.store).list_pending()
                self.assertEqual([e["stage"] for e in pending["effects"]], ["event"])  # the commit was not recorded
                self.assertEqual(self.head(), self.remote_head())
                git(self.root, "checkout", "-q", "main")
                call()
                self.assertFinalizedHere(pending)


# --------------------------------------------------------------------------- before a decision nothing is bound
class UndecidedTests(DecisionCase):
    def test_a_work_decides_its_branch_only_once_its_executor_has_returned(self) -> None:
        with self.subTest(case="the executor moves to another branch"):
            self.world("executor-moves", "start completion")
            done = completing_executor(self.store, self.ran)

            def moving(ctx):
                git(self.root, "checkout", "-q", "-b", "feature")
                return done(ctx)

            result = st.start(self.store, self.w1, "single-work", moving)
            self.assertEqual((result.status, self.on()), ("completed", "refs/heads/feature"))
            self.assertEqual(git(self.remote_path(self.name), "rev-parse", "feature").strip(), self.head())
            self.assertEqual(git(self.root, "rev-parse", "main").strip(), self.remote_head())
        with self.subTest(case="the outer executor of the second Work moves"):
            self.world("outer-executor-moves", "outer completion")
            done = completing_executor(self.store, self.ran)

            def moving_second(ctx):
                if ctx.work.id == self.w2:
                    git(self.root, "checkout", "-q", "-b", "feature")
                return done(ctx)

            result = st.start(self.store, self.w1, "outer", moving_second)
            self.assertEqual((result.status, self.ran), ("phase_complete", [self.w1, self.w2, self.integration]))
            self.assertEqual(self.on(), "refs/heads/feature")
        with self.subTest(case="a question wait resumed on another branch"):
            self.world("question", "start completion")
            waiting = st.start(self.store, self.w1, "single-work", lambda ctx: st.QuestionWait("which?"))
            (pending,) = MutationController(self.store).list_pending()
            self.assertEqual(waiting.status, "question_wait")
            self.assertTrue(all(DECIDED_ON not in e for e in pending["effects"]))
            git(self.root, "checkout", "-q", "-b", "side")
            result = st.start(self.store, self.w1, "single-work", completing_executor(self.store, self.ran))
            self.assertEqual((result.status, self.on()), ("completed", SIDE))
            self.assertFinalizedHere(pending)
        with self.subTest(case="an executor interrupted before it returned"):
            self.world("executor-interrupted", "start completion")
            done = completing_executor(self.store, self.ran)

            def interrupted(ctx):
                done(ctx)
                raise Interrupted("executor interrupted")

            with self.assertRaises(Interrupted):
                st.start(self.store, self.w1, "single-work", interrupted)
            (pending,) = MutationController(self.store).list_pending()
            git(self.root, "checkout", "-q", "-b", "side")
            result = st.start(self.store, self.w1, "single-work", completing_executor(self.store, self.ran))
            self.assertEqual((result.status, self.on(), self.ran), ("completed", SIDE, [self.w1, self.w1]))
            self.assertFinalizedHere(pending)
        with self.subTest(case="a lifecycle operation that reserved its event and recorded nothing"):
            self.world("reserved", "phase hold")
            real = Mutation.reserve_id

            def reserve_then_stop(mutation, key, kind):
                identifier = real(mutation, key, kind)
                if key.startswith("event:event:"):
                    raise Interrupted("reserved")
                return identifier

            with mock.patch.object(Mutation, "reserve_id", reserve_then_stop), self.assertRaises(Interrupted):
                rm.hold_phase(self.store, self.pb)
            git(self.root, "checkout", "-q", "-b", "side")
            self.assertEqual(rm.hold_phase(self.store, self.pb).status, "phase_held")
            self.assertEqual(self.on(), SIDE)


# --------------------------------------------------------------------------- outer continuation, cancel
class ContinuationTests(DecisionCase):
    def test_an_outer_start_does_not_move_on_past_a_decision_it_cannot_finalize_here(self) -> None:
        self.world("outer", "outer completion")
        call, pending = self.decided("outer completion")
        git(self.root, "checkout", "-q", "-b", "side")

        self.assertStopsUntouched(call)
        self.assertEqual(self.ran, [self.w1])  # neither the next Work nor the integration ran

        git(self.root, "checkout", "-q", "main")
        result = call()
        self.assertEqual((result.status, self.ran), ("phase_complete", [self.w1, self.w2, self.integration]))
        self.assertFinalizedHere(pending)

    def test_a_cancel_is_carried_on_only_on_the_branch_it_was_decided_on(self) -> None:
        """Interrupted with its replan applied and its commit not recorded, a cancel resumes from its decision (BL-030)."""
        for mode, cancelled in (("outer", "w2"), ("single-work", "w1")):
            with self.subTest(mode=mode):
                self.world(f"{mode}-cancel", "outer completion" if mode == "outer" else "start completion")
                work = getattr(self, cancelled)
                cancel = st.Cancel(Replan(remove_relation_ids=(self.requirement(work),)), "not needed")
                call = lambda: st.start(self.store, self.w1, mode, self.cancelling({work: cancel}))  # noqa: E731,B023
                pending = self.stop_in(after_applying(rf"^{work}:cancel:\d+:remove$"), call)
                ran = list(self.ran)
                git(self.root, "checkout", "-q", "-b", "side")

                self.assertStopsUntouched(call)  # the cancel was decided on main: nothing replayed or committed on side

                git(self.root, "checkout", "-q", "main")
                executed: list[str] = []
                result = self.counting(call, executed)
                self.assertEqual((result.status, result.work_id, result.mutation_id), ("cancelled", work, pending["mutation_id"]))
                self.assertEqual(executed, ["git_commit", "git_push"])  # only what was left: its commit, on main
                self.assertEqual(self.ran, ran)  # neither the executor nor the next Work ran
                (commit,) = [e for e in MutationController(self.store).list_records()
                             if e["mutation_id"] == pending["mutation_id"]][0]["effects"][-2:-1]
                self.assertEqual(commit["payload"]["branch"], MAIN)  # the decision's branch, handed to its commit
                self.assertFinalizedHere(pending)

    def requirement(self, work_id: str) -> str:
        from workline.state import ProjectView

        (relation,) = [r.id for r in ProjectView.load(self.store).roadmap_relations
                       if (r.type, r.from_id, r.to) == ("requires_completion", work_id, self.integration)]
        return relation

    def cancelling(self, outcomes: dict):
        done = completing_executor(self.store, self.ran)

        def execute(ctx):
            if ctx.work.id in outcomes:
                self.ran.append(ctx.work.id)
                return outcomes[ctx.work.id]
            return done(ctx)

        return execute


# --------------------------------------------------------------------------- what cannot be shown
class UnshownBranchTests(DecisionCase):
    def test_a_record_written_before_decisions_carried_their_branch(self) -> None:
        for index, (owner, where) in enumerate((o, w) for o in ("start completion", "phase hold") for w in ("main", "side")):
            with self.subTest(owner=owner, retried_on=where):
                self.world(f"legacy-{index}", owner)
                call, pending = self.decided(owner)
                self.strip_bindings(pending)
                if where == "side":
                    git(self.root, "checkout", "-q", "-b", "side")
                self.assertStopsUntouched(call, fragment="without the branch they were decided on")
        with self.subTest(owner="project start", retried_on="detached"):
            self.world("legacy-detached", "project start")
            call, pending = self.decided("project start")
            self.strip_bindings(pending)
            git(self.root, "checkout", "-q", "--detach")
            self.assertStopsUntouched(call, fragment="without the branch they were decided on")
        with self.subTest(case="only a Work's execution was opened"):
            self.world("legacy-opened", "start completion")
            st.start(self.store, self.w1, "single-work", lambda ctx: st.QuestionWait("which?"))
            (pending,) = MutationController(self.store).list_pending()
            self.strip_bindings(pending)
            self.assertEqual(st.start(self.store, self.w1, "single-work", completing_executor(self.store)).status, "completed")
        with self.subTest(case="the commit was recorded already"):
            self.world("legacy-recorded-commit", "phase hold")
            call, _, _ = self.decision("phase hold")
            pending = self.interrupt(call, r"^finalize$", "commit refused")
            self.strip_bindings(pending)
            call()  # its own branch, BL-035's to decide
            self.assertFinalizedHere(pending)

    def test_a_question_git_cannot_answer(self) -> None:
        real = gitcmd.run_git

        def unanswered(repo, *args, check=True):
            if args[:2] == ("symbolic-ref", "--quiet"):
                return gitcmd.GitResult(128, "", "fatal: cannot answer")
            return real(repo, *args, check=check)

        with self.subTest(when="resuming"):
            self.world("unanswered-resume", "phase hold")
            call, _ = self.decided("phase hold")
            with mock.patch.object(gitcmd, "run_git", unanswered):
                self.assertStopsUntouched(call)
        with self.subTest(when="deciding"):
            self.world("unanswered-decide", "phase hold")
            before = self.snapshot()
            with mock.patch.object(gitcmd, "run_git", unanswered), self.assertRaises(GitError):
                rm.hold_phase(self.store, self.pb)
            self.assertEqual([p["effects"] for p in MutationController(self.store).list_pending()], [[]])  # nothing recorded
            self.assertEqual({k: v for k, v in self.snapshot().items() if k != "records"},
                             {k: v for k, v in before.items() if k != "records"})
            self.assertEqual(rm.hold_phase(self.store, self.pb).status, "phase_held")  # once Git answers, it goes on

    def test_a_same_message_commit_on_the_other_branch_is_not_taken_for_the_decision(self) -> None:
        self.world("same-message", "start completion")
        call, _ = self.decided("start completion")
        git(self.root, "checkout", "-q", "-b", "side")
        from workline.state import ProjectView

        display = ProjectView.load(self.store).works[self.w1].display
        self.human_commit({"notes.md": "notes\nsame message\n"}, f"chore(workline): complete {display}")

        self.assertStopsUntouched(call)


# --------------------------------------------------------------------------- Project開始
class ProjectStartTests(DecisionCase):
    def test_a_detached_head_and_a_branch_without_commits(self) -> None:
        with self.subTest(case="decided on main, retried detached"):
            self.world("start-detached", "project start")
            call, pending = self.decided("project start")
            git(self.root, "checkout", "-q", "--detach")
            self.assertStopsUntouched(call)
            git(self.root, "checkout", "-q", "main")
            call()
            self.assertFinalizedHere(pending)
        with self.subTest(case="decided detached, retried detached and on a branch"):
            self.repository("start-on-detached", detached=True)
            call, pending = self.decided("project start")
            (binding,) = {e[DECIDED_ON]["branch"] for e in pending["effects"] if DECIDED_ON in e}
            self.assertIsNone(binding)
            git(self.root, "checkout", "-q", "-b", "side")
            self.assertStopsUntouched(call)
            git(self.root, "checkout", "-q", "--detach")
            call()
            self.assertFinalizedHere(pending)
            self.assertIsNone(self.on())
        with self.subTest(case="a branch with no commit yet"):
            self.repository("start-unborn", committed=False)
            call, pending = self.decided("project start")
            (binding,) = {(e[DECIDED_ON]["branch"], e[DECIDED_ON]["head"]) for e in pending["effects"] if DECIDED_ON in e}
            self.assertEqual(binding, (MAIN, None))
            git(self.root, "symbolic-ref", "HEAD", SIDE)
            self.assertStopsUntouched(call)
            git(self.root, "symbolic-ref", "HEAD", MAIN)
            call()
            self.assertFinalizedHere(pending)
            self.assertEqual(git(self.root, "rev-list", "--count", "HEAD").strip(), "1")


# --------------------------------------------------------------------------- the process really dies
KILL_ON_COMPLETION = """#!/bin/sh
# core.fsmonitor hook: once the Work's completion is in the event log, the Workline process dies.
flag="$(git rev-parse --git-dir)/workline-test-kill"
if [ -f "$flag" ] && grep -q -F '"type":"work_completed","entity":"'"$(cat "$flag")"'"' .workline/events/events.jsonl 2>/dev/null; then
  rm -f "$flag"
  "{python}" -c "import os, signal; os.kill(int(os.environ['WORKLINE_TEST_KILL_PID']), signal.SIGTERM)"
fi
exit 1
"""


class ProcessKillTests(DecisionCase):
    def test_a_start_killed_after_its_completion_does_not_finalize_on_another_branch(self) -> None:
        """No patching at all: the process running START dies right after the completion is applied (W2)."""
        self.world("killed", "start completion")
        hook = self.tmp / "kill-on-completion.sh"
        hook.write_text(KILL_ON_COMPLETION.replace("{python}", Path(sys.executable).as_posix()), encoding="utf-8", newline="\n")
        os.chmod(hook, 0o755)
        (self.root / ".git" / "workline-test-kill").write_text(self.w1, encoding="utf-8")
        git(self.root, "config", "core.fsmonitor", hook.as_posix())
        code = (
            "import os, sys\n"
            f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n"
            "import helpers\n"
            "from pathlib import Path\n"
            "from workline import start as st\n"
            "from workline.store import ProjectStore\n"
            "os.environ['WORKLINE_TEST_KILL_PID'] = str(os.getpid())\n"
            f"store = ProjectStore(Path({str(self.root)!r}))\n"
            f"st.start(store, {self.w1!r}, 'single-work', helpers.completing_executor(store))\n"
            "print('not killed')\n"
        )
        # The `git status` that ran the hook outlives the process it was started by; without optional locks it
        # never holds the index lock the steps below need.
        env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
        try:
            died = subprocess.run([sys.executable, "-B", "-c", code], cwd=str(self.root), capture_output=True, text=True, env=env)
        finally:
            git(self.root, "config", "--unset", "core.fsmonitor", check=False)
        self.assertNotEqual(died.returncode, 0, died.stdout + died.stderr)
        self.assertNotIn("not killed", died.stdout)
        (pending,) = MutationController(self.store).list_pending()
        stages = [e["stage"] for e in pending["effects"]]
        self.assertEqual((stages[-1], f"{self.w1}:finalize:0" in stages), (f"{self.w1}:lifecycle:1", False))
        self.assertTrue(all(e.get("applied") for e in pending["effects"]))
        git(self.root, "checkout", "-q", "-b", "side")

        call = lambda: st.start(self.store, self.w1, "single-work", completing_executor(self.store, self.ran))  # noqa: E731
        self.assertStopsUntouched(call)

        git(self.root, "checkout", "-q", "main")
        self.assertEqual(call().status, "completed")
        self.assertEqual(self.ran, [])  # the executor was not asked again
        self.assertFinalizedHere(pending)


# --------------------------------------------------------------------------- the record
class RecordShapeTests(DecisionCase):
    def test_the_binding_lives_in_the_decided_effects_and_changes_nothing_else(self) -> None:
        self.assertEqual((INTENT_VERSION, EFFECT_KINDS), (1, ("write_file", "create_file", "add_relation",
                                                                "remove_relation", "append_event", "git_commit",
                                                                "git_push")))
        self.world("record", "phase hold")
        rm.hold_phase(self.store, self.pb)
        self.assertEqual(list(self.store.mutations.glob("*.yaml")), [])  # a finished operation still removes its own record


if __name__ == "__main__":
    unittest.main()
