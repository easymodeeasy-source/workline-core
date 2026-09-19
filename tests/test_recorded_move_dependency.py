"""START finishes a recorded move that made the moving Work wait, instead of stopping on it (BL-049).

A derivation that removes its Work's target - a temporary move, a human
confirmation judged NG - may register, with the Works it moves to, a
``requires_completion`` from one of them into the moving Work itself. The NG
always does (its re-integration must be complete before the confirmation is
confirmed again), and a ``Derive(move=True)`` does whenever its executor decides
the Work waits for its fix. That dependency is checked when the Work is run
again, never between the registration and the removal of the target: the
uninterrupted cycle goes straight from one to the other.

A resume interrupted in that gap - the registration recorded, applied in part or
in full, the removal not recorded yet - re-entered the cycle through the
precheck that guards running a Work. That precheck met the move's own new
dependency, reported it as an unfinished dependency and stopped, on every retry,
before the recorded cycle could be replayed (BL-046 does that replay), while the
pending record held off every other START, CREATE and Roadmap operation that
could have satisfied it.

The precheck of that continuation now leaves out exactly the relations the
move's own recorded registration added into the Work - and only once the record
shows that move: this mutation resumed, its derivations proven, the Work still
carrying its target, the move the last derivation of the cycle, its
registration the last stage recorded and exactly the one the move decides, each
relation under the ID reserved for it and held by the Project exactly so. A
dependency the Project held before, one another subject added, and a record that
cannot show the move are checked exactly as before; a stage that is not the
move's registration is ``reconcile required`` and nothing of the cycle runs.

BL-051 made the same rule the cycle's, not only the move's: every proven
registration of the continued cycle - one that kept the target as much as the
move - is its own, so the two tests at the end of ``MoveTests`` that pinned the
BL-049 boundary now pin the cycle's (``tests/test_current_cycle_dependency_resume.py``
holds the rest).
"""

from __future__ import annotations

import re
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from workline import start as st
from workline import yamlish
from workline.create import RelationSpec, WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, StopError
from workline.ids import new_id
from workline.mutation import Mutation, MutationController
from workline.state import ProjectView
from workline.store import WORKLINE_DIR
from workline.validate import validate_project

ROADMAP_YAML = f"{WORKLINE_DIR}/relations/roadmap.yaml"
WORK_STARTED = ["work_started", "work_target_added"]
MOVED = WORK_STARTED + ["work_target_removed"]
NG_THEN_CONFIRMED = MOVED + ["work_target_added", "work_target_removed", "work_completed"]


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


# --------------------------------------------------------------------------- interruption windows
def before_keeping():
    """Stop after the executor returned the derivation and before the record keeps it."""
    real = Mutation.set_note

    def fire(mutation, key, value):
        if key == st._DERIVATIONS:
            raise Interrupted("before keeping the derivation")
        return real(mutation, key, value)

    return mock.patch.object(Mutation, "set_note", fire)


def before_recording(pattern: str):
    """Stop with a stage matching ``pattern`` about to be recorded."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        if re.search(pattern, stage):
            raise Interrupted(f"about to record {stage}")
        return real(mutation, stage, effects)

    return mock.patch.object(Mutation, "add_effects", fire)


def after_recording(pattern: str):
    """Stop right after a stage matching ``pattern`` is recorded, none of it applied."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        real(mutation, stage, effects)
        if re.search(pattern, stage):
            raise Interrupted(f"recorded {stage}")

    return mock.patch.object(Mutation, "add_effects", fire)


def after_writing_one(pattern: str):
    """Stop once exactly one effect of a stage matching ``pattern`` is applied and flagged."""
    real = MutationController.apply_effect
    seen = {"n": 0}

    def fire(controller, record):
        if re.search(pattern, record["stage"]):
            if seen["n"] >= 1:
                raise Interrupted(f"applied one effect of {record['stage']}")
            seen["n"] += 1
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


def before_pushing(stage: str):
    """Stop with the commit of ``stage`` made and its push not made."""
    real = MutationController.apply_effect

    def fire(controller, record):
        if record["kind"] == "git_push" and record["stage"] == stage:
            raise Interrupted(f"{stage} committed, not pushed")
        return real(controller, record)

    return mock.patch.object(MutationController, "apply_effect", fire)


def by_attempt(log: list[str], script: dict, default=None):
    """Executor scripted by Work name and ``ctx.attempt``, so a resumed cycle is asked what an uninterrupted one is."""

    def execute(ctx: st.ExecutionContext):
        log.append(f"{ctx.work.name}#{ctx.attempt}")
        outcome = script.get((ctx.work.name, ctx.attempt), script.get(ctx.work.name))
        if outcome is None:
            if default is None:
                raise AssertionError(f"no outcome scripted for {ctx.work.name} attempt {ctx.attempt}")
            return default(ctx)
        return outcome(ctx) if callable(outcome) else outcome

    return execute


# --------------------------------------------------------------------------- the Project, and what it can show
class MoveCase(WorklineTestCase):
    """A Phase with W1 and its integration - and a human confirmation after it, when the case needs one."""

    confirmation = False

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.root = self.store.root
        self.ran: list[str] = []
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A")})
        self.pa = roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, self.pa, {"w1": "W1 done"}, confirmation=self.confirmation)
        self.w1, self.i1, self.h1 = entry.work_ids["w1"], entry.integration_id, entry.confirmation_id

    # calls ---------------------------------------------------------------------
    def completing(self):
        return by_attempt(self.ran, {}, default=completing_executor(self.store))

    def interrupt(self, window, call) -> dict:
        with window(), self.assertRaises(Interrupted):
            call()
        (pending,) = MutationController(self.store).list_pending()
        return pending

    def keep_without_recording(self, window, call, stage: str) -> dict:
        """The record a kill between keeping the decision and recording its stage leaves (as BL-046 builds it)."""
        self.interrupt(window, call)
        self.edit_record(lambda record: record.update({"effects": [e for e in record["effects"] if e["stage"] != stage]}))
        return MutationController(self.store).list_pending()[0]

    def watching(self, call) -> tuple[object, list[str], list[str]]:
        """Run ``call``, returning its result and every effect kind applied and stage recorded meanwhile."""
        executed: list[str] = []
        stages: list[str] = []
        real_apply, real_add = MutationController.apply_effect, Mutation.add_effects

        def apply(controller, record):
            executed.append(record["kind"])
            return real_apply(controller, record)

        def add(mutation, stage, effects):
            stages.append(stage)
            return real_add(mutation, stage, effects)

        with mock.patch.object(MutationController, "apply_effect", apply), mock.patch.object(Mutation, "add_effects", add):
            return call(), executed, stages

    def edit_record(self, change) -> None:
        (pending,) = MutationController(self.store).list_pending()
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8")

    # observation ---------------------------------------------------------------
    def named(self, name: str) -> list[str]:
        return sorted(w.id for w in ProjectView.load(self.store).works.values() if w.name == name)

    def events(self, work_id: str) -> list[str]:
        return [e.type for e in ProjectView.load(self.store).events if e.entity == work_id]

    def relations(self) -> list[tuple[str, str, str]]:
        view = ProjectView.load(self.store)
        name = {w.id: w.name for w in view.works.values()}
        return sorted((r.type, name.get(r.from_id, r.from_id), name.get(r.to, r.to)) for r in view.roadmap_relations)

    def derivation_files(self) -> int:
        area = self.root / f"{WORKLINE_DIR}/derivations"
        return len(list(area.glob("*.md"))) if area.is_dir() else 0

    def display(self, work_id: str) -> str:
        return ProjectView.load(self.store).works[work_id].display

    def subjects(self) -> list[str]:
        return git(self.root, "log", "--format=%s").splitlines()

    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote_path(), "rev-parse", "main").strip()

    def dirty(self) -> list[str]:
        status = git(self.root, "status", "--porcelain", "--untracked-files=all").splitlines()
        return [line for line in status if ".workline/runtime/" not in line]

    def pending(self) -> list[dict]:
        return MutationController(self.store).list_pending()

    def stage_names(self) -> list[str]:
        names: list[str] = []
        for effect in self.pending()[0].get("effects") or []:
            if effect["stage"] not in names:
                names.append(effect["stage"])
        return names

    def snapshot(self) -> dict:
        """Everything a refused resume must leave exactly as it was: the records byte for byte, the Project, Git."""
        return {
            "records": {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))},
            "files": {p.relative_to(self.root).as_posix(): p.read_bytes()
                      for p in sorted((self.root / ".workline").rglob("*"))
                      if p.is_file() and "runtime" not in p.relative_to(self.root).parts},
            "head": self.head(),
            "remote": self.remote_head(),
            "dirty": self.dirty(),
        }

    # assertions ------------------------------------------------------------------
    def assertStoppedUntouched(self, call, code: str) -> StopError:
        """Refused with ``code``: no executor asked, no stage recorded, no effect applied, nothing changed."""
        ran, before = list(self.ran), self.snapshot()
        with self.assertRaises(StopError) as refused:
            call()
        self.assertEqual(refused.exception.code, code)
        self.assertEqual(self.ran, ran)
        self.assertEqual(self.snapshot(), before)
        return refused.exception

    def assertNotReplayed(self, call) -> ReconcileRequired:
        """Refused as ``reconcile required`` before the cycle replays anything: no executor, no stage, no commit."""
        ran, head, remote, stages_before = list(self.ran), self.head(), self.remote_head(), self.stage_names()
        derived: list[str] = []
        real = st._Session._derive

        def derive(session, *args, **kwargs):
            derived.append("called")
            return real(session, *args, **kwargs)

        with mock.patch.object(st._Session, "_derive", derive), self.assertRaises(ReconcileRequired) as refused:
            call()
        self.assertEqual((derived, self.ran), ([], ran))
        self.assertEqual(self.stage_names(), stages_before)
        self.assertEqual((self.head(), self.remote_head()), (head, remote))
        return refused.exception


# --------------------------------------------------------------------------- a human confirmation judged NG
class HumanNGCase(MoveCase):
    confirmation = True

    #: What the NG and the cycle after it leave: the Phase entry's two relations, and the NG's four.
    RELATIONS = sorted([
        ("requires_completion", "W1", "Integration"),
        ("requires_completion", "Integration", "Confirmation"),
        ("derived", "Confirmation", "F1"),
        ("derived", "Confirmation", "I2"),
        ("requires_completion", "F1", "I2"),
        ("requires_completion", "I2", "Confirmation"),
    ])

    def ng_executor(self):
        """The confirmation is judged NG once; confirmed again after its fix, it passes."""

        def ng(ctx: st.ExecutionContext):
            if self.named("F1"):
                return completing_executor(self.store)(ctx)
            return st.HumanNG({"f1": st.DerivedWork("F1", "defect fixed", derivation_detail="why F1")},
                              st.DerivedWork("I2", "re-integrated"))

        return by_attempt(self.ran, {("Confirmation", 1): ng}, default=completing_executor(self.store))

    def outer(self):
        return lambda: st.start(self.store, self.w1, "outer", self.ng_executor())

    def single(self):
        return lambda: st.start(self.store, self.h1, "single-work", self.ng_executor())

    def settle_before_the_confirmation(self) -> None:
        """W1 and the integration completed, committed and pushed by their own STARTs."""
        st.start(self.store, self.w1, "single-work", self.completing())
        st.start(self.store, self.i1, "single-work", self.completing())

    def stuck_windows(self) -> dict:
        """Every window between the NG's registration and the removal of the confirmation's target.

        The stage names hold this Project's IDs, so each is read when the window opens - a subTest
        that sets up a new Project gets windows over that Project's stages.
        """
        return {
            "registration recorded": lambda: after_recording(rf"^{self.h1}:derive:0$"),
            "one effect of it applied": lambda: after_writing_one(rf"^{self.h1}:derive:0$"),
            "registration applied": lambda: after_applying(rf"^{self.h1}:derive:0$"),
            "removal about to be recorded": lambda: before_recording(rf"^{self.h1}:lifecycle:1$"),
        }

    def assertStuckBeforeTheRemoval(self) -> None:
        view = ProjectView.load(self.store)
        state = view.work_state(self.h1)
        self.assertEqual((state.state, state.has_target), ("in_progress", True))
        self.assertEqual(self.stage_names()[-1], f"{self.h1}:derive:0")

    def assertOuterConverged(self, result, decided: str) -> None:
        """Exactly what the uninterrupted outer run leaves: the NG decided once, its Works once, one NG commit."""
        self.assertEqual(result.status, "phase_complete")
        self.assertEqual(self.ran, ["W1#1", "Integration#1", "Confirmation#1", "F1#1", "I2#1", "Confirmation#1"])
        self.assertEqual((len(self.named("F1")), len(self.named("I2")), len(self.named("Confirmation"))), (1, 1, 1))
        self.assertEqual(len(ProjectView.load(self.store).works), 5)
        self.assertEqual(self.relations(), self.RELATIONS)
        self.assertEqual(self.events(self.h1), NG_THEN_CONFIRMED)
        self.assertEqual(len(ProjectView.load(self.store).events), 22)
        self.assertEqual(self.derivation_files(), 1)
        self.assertEqual(self.subjects().count(f"chore(workline): {decided} NG; fix planned"), 1)
        self.assertEqual(sum(1 for s in self.subjects() if s.endswith(" NG; fix planned")), 1)
        self.assertEqual((self.pending(), self.dirty(), self.head()), ([], [], self.remote_head()))
        self.assertEqual(validate_project(self.store), [])


class HumanNGResumeTests(HumanNGCase):
    def test_an_ng_stopped_before_its_removal_finishes_from_its_record(self) -> None:
        """Outer: every window from the registration to the removal ends as the uninterrupted run does."""
        for window, make in self.stuck_windows().items():
            with self.subTest(window=window):
                self.setUp()
                self.interrupt(make, self.outer())
                self.assertStuckBeforeTheRemoval()
                decided = self.display(self.h1)
                self.assertOuterConverged(self.outer()(), decided)

    def test_a_single_work_ng_adds_only_what_the_uninterrupted_one_adds(self) -> None:
        """The same mutation, its recorded registration applied once, then only the removal, the commit and its push."""
        for window in ("registration recorded", "registration applied", "removal about to be recorded"):
            with self.subTest(window=window):
                self.setUp()
                self.settle_before_the_confirmation()
                pending = self.interrupt(self.stuck_windows()[window], self.single())
                self.assertEqual(self.ran, ["W1#1", "Integration#1", "Confirmation#1"])
                unapplied = [e["kind"] for e in pending["effects"] if not e.get("applied")]
                result, executed, stages = self.watching(self.single())
                self.assertEqual((result.status, result.work_id, result.mutation_id), ("moved", self.h1, pending["mutation_id"]))
                # the resume replays what the record holds (the registration, where it was not applied yet),
                # then records and applies what the uninterrupted NG records after it - and nothing else
                self.assertEqual(stages, [f"{self.h1}:lifecycle:1", "commit:0"])
                self.assertEqual(executed, unapplied + ["append_event", "git_commit", "git_push"])
                self.assertEqual(self.ran, ["W1#1", "Integration#1", "Confirmation#1"])  # the NG is not decided again
                self.assertEqual(self.events(self.h1), MOVED)
                self.assertEqual((len(self.named("F1")), len(self.named("I2"))), (1, 1))
                self.assertEqual(self.relations(), self.RELATIONS)
                self.assertEqual(self.derivation_files(), 1)
                self.assertEqual(self.subjects()[0], f"chore(workline): {self.display(self.h1)} NG; fix planned")
                self.assertEqual((self.pending(), self.dirty(), self.head()), ([], [], self.remote_head()))

    def test_the_windows_around_it_are_unchanged(self) -> None:
        """Before the decision is kept the NG is asked again; after the removal the record finishes it."""
        windows = {
            "before the decision is kept": before_keeping,
            "decision kept, stage not recorded": None,
            "removal recorded": lambda: after_recording(rf"^{self.h1}:lifecycle:1$"),
            "removal applied": lambda: before_recording(r"^commit:0$"),
            "commit recorded": lambda: after_recording(r"^commit:0$"),
            "committed, not pushed": lambda: before_pushing("commit:0"),
        }
        for window, make in windows.items():
            with self.subTest(window=window):
                self.setUp()
                decided = self.display(self.h1)
                if make is None:
                    self.keep_without_recording(lambda: after_recording(rf"^{self.h1}:derive:0$"), self.outer(),
                                                f"{self.h1}:derive:0")
                else:
                    self.interrupt(make, self.outer())
                result = self.outer()()
                if window == "before the decision is kept":
                    # nothing was decided yet, so that cycle is asked again - the contract as it was
                    self.assertEqual(self.ran[:4], ["W1#1", "Integration#1", "Confirmation#1", "Confirmation#1"])
                    self.ran[3:4] = []
                self.assertOuterConverged(result, decided)

    def test_the_confirmation_s_display_changed_meanwhile_is_not_its_ng_s(self) -> None:
        """BL-048: the NG commit made by the resume carries the display the NG was decided on."""
        self.interrupt(self.stuck_windows()["registration applied"], self.outer())
        decided = self.display(self.h1)
        path = self.root / ProjectView.load(self.store).works[self.h1].path
        text = path.read_text(encoding="utf-8")
        path.write_text(re.sub(r"(?m)^display: .*$", "display: W-99", text, count=1), encoding="utf-8")
        git(self.root, "add", path.relative_to(self.root).as_posix())
        git(self.root, "-c", "core.hooksPath=/dev/null", "commit", "-m", "person: renumber the confirmation")
        result = self.outer()()
        self.assertEqual(result.status, "phase_complete")
        self.assertEqual(self.subjects().count(f"chore(workline): {decided} NG; fix planned"), 1)
        self.assertNotIn("chore(workline): W-99 NG; fix planned", self.subjects())
        self.assertEqual(self.ran, ["W1#1", "Integration#1", "Confirmation#1", "F1#1", "I2#1", "Confirmation#1"])

    def test_a_stuck_ng_no_longer_holds_the_project(self) -> None:
        """Other operations wait for the pending NG; once it is resumed they go on."""
        self.settle_before_the_confirmation()
        self.interrupt(self.stuck_windows()["registration applied"], self.single())
        f1 = self.named("F1")[0]
        for label, call in (
            ("START", lambda: st.start(self.store, f1, "single-work", self.completing())),
            ("CREATE", lambda: create_standalone_work(self.store, WorkSpec("S", "s done"))),
            ("Roadmap", lambda: self.simple_roadmap(self.store, {"b": ("Phase B", "B")})),
        ):
            with self.subTest(blocked=label):
                with self.assertRaises(ReconcileRequired) as refused:
                    call()
                self.assertIn("overlaps the planned write scope", str(refused.exception))
        self.assertEqual(self.single()().status, "moved")
        self.assertEqual(self.pending(), [])
        self.assertEqual(st.start(self.store, f1, "single-work", self.completing()).status, "completed")
        created = create_standalone_work(self.store, WorkSpec("S", "s done"))
        self.assertEqual(self.named("S"), [created.work_id])
        roadmap = self.simple_roadmap(self.store, {"b": ("Phase B", "B")})
        self.assertEqual(len(roadmap.phase_ids), 1)
        self.assertEqual((self.pending(), validate_project(self.store)), ([], []))


# --------------------------------------------------------------------------- what still stops
class HumanNGStillStopsTests(HumanNGCase):
    def hand_add(self, from_id: str) -> str:
        """A person's own relation line, making the confirmation wait for ``from_id``."""
        relation = new_id("relation")
        path = self.root / ROADMAP_YAML
        path.write_bytes(path.read_bytes().rstrip(b"\n") + (
            f"\n  - id: {relation}\n    type: requires_completion\n    from: {from_id}\n    to: {self.h1}\n"
        ).encode("utf-8"))
        return relation

    def test_a_relation_a_person_added_still_stops_the_resume(self) -> None:
        """Only the NG's own relation is left out; the person's is reported, and nothing is written for it."""
        self.interrupt(self.stuck_windows()["registration applied"], self.outer())
        f1, i2 = self.named("F1")[0], self.named("I2")[0]
        original = (self.root / ROADMAP_YAML).read_bytes()
        self.hand_add(f1)
        refused = self.assertStoppedUntouched(self.outer(), "dependency_unsatisfied")
        self.assertIn(f1, str(refused))
        self.assertNotIn(i2, str(refused))
        (self.root / ROADMAP_YAML).write_bytes(original)
        self.assertOuterConverged(self.outer()(), self.display(self.h1))

    def test_a_person_s_change_to_the_fix_work_is_still_refused(self) -> None:
        """A fix Work file the NG wrote and a person changed is refused by the replay itself, as it always was."""
        self.interrupt(self.stuck_windows()["registration applied"], self.outer())
        path = self.root / ProjectView.load(self.store).works[self.named("F1")[0]].path
        original = path.read_bytes()
        path.write_bytes(original + b"\nperson's note\n")
        head, remote = self.head(), self.remote_head()
        with self.assertRaises(ReconcileRequired) as refused:
            self.outer()()
        self.assertIn("applied with unexpected result", str(refused.exception))
        self.assertEqual((self.head(), self.remote_head()), (head, remote))
        self.assertEqual(path.read_bytes(), original + b"\nperson's note\n")
        self.assertEqual(self.ran, ["W1#1", "Integration#1", "Confirmation#1"])
        path.write_bytes(original)
        self.assertOuterConverged(self.outer()(), self.display(self.h1))

    def test_a_person_s_change_to_a_file_the_ng_goes_on_to_write_or_commit_is_still_refused(self) -> None:
        """BL-043: the continuation checks the bytes it writes and commits exactly as the uninterrupted NG does."""
        event_log = f"{WORKLINE_DIR}/events/events.jsonl"
        for label, rel, added, refusal in (
            ("event log the removal appends to", event_log, b"\n", f"would write {event_log}, which no longer holds"),
            ("relation ledger the NG commit carries", ROADMAP_YAML, b"# person's note\n",
             "cannot show the change it would commit is its own"),
        ):
            with self.subTest(changed=label):
                self.setUp()
                self.interrupt(self.stuck_windows()["registration applied"], self.outer())
                path = self.root / rel
                original = path.read_bytes()
                path.write_bytes(original + added)
                head, remote = self.head(), self.remote_head()
                for _ in range(2):
                    with self.assertRaises(ReconcileRequired) as refused:
                        self.outer()()
                    self.assertIn(refusal, str(refused.exception))
                self.assertEqual(path.read_bytes(), original + added)  # neither taken in nor written over
                self.assertEqual((self.head(), self.remote_head(), self.ran),
                                 (head, remote, ["W1#1", "Integration#1", "Confirmation#1"]))
                path.write_bytes(original)
                self.assertOuterConverged(self.outer()(), self.display(self.h1))

    def test_a_resume_on_another_branch_than_the_ng_was_decided_on_is_refused(self) -> None:
        """BL-036: the move is continued only on the branch its registration was decided on."""
        self.interrupt(self.stuck_windows()["registration applied"], self.outer())
        git(self.root, "checkout", "-q", "-b", "elsewhere")
        head, remote = self.head(), self.remote_head()
        with self.assertRaises(ReconcileRequired):
            self.outer()()
        self.assertEqual((self.head(), self.remote_head()), (head, remote))
        self.assertEqual((self.ran, self.events(self.h1)), (["W1#1", "Integration#1", "Confirmation#1"], WORK_STARTED))
        self.assertEqual(self.stage_names()[-1], f"{self.h1}:derive:0")
        git(self.root, "checkout", "-q", "main")
        self.assertOuterConverged(self.outer()(), self.display(self.h1))

    def tamper(self, change) -> None:
        stage = f"{self.h1}:derive:0"

        def edit(record: dict) -> None:
            for effect in record["effects"]:
                if effect["stage"] == stage:
                    change(record, effect)

        self.edit_record(edit)

    def is_the_ng_s_own(self, effect: dict) -> bool:
        record = effect["payload"].get("record") if effect["kind"] == "add_relation" else None
        return isinstance(record, dict) and (record["type"], record["to"]) == ("requires_completion", self.h1)

    def test_a_registration_other_than_the_ng_makes_is_refused_before_anything_runs(self) -> None:
        """What the record holds must be the NG's registration, compared exactly, before its relation is left out."""

        def reserved(record: dict, effect: dict) -> None:
            if self.is_the_ng_s_own(effect):
                key = next(k for k, v in record["reserved_ids"].items() if v == effect["payload"]["record"]["id"])
                record["reserved_ids"][key] = new_id("relation")

        def relation_id(record: dict, effect: dict) -> None:
            if self.is_the_ng_s_own(effect):
                effect["payload"]["record"]["id"] = new_id("relation")

        def target(record: dict, effect: dict) -> None:
            if self.is_the_ng_s_own(effect):
                effect["payload"]["record"]["to"] = self.i1

        def relation_type(record: dict, effect: dict) -> None:
            if self.is_the_ng_s_own(effect):
                effect["payload"]["record"]["type"] = "planned_next"

        def work_body(record: dict, effect: dict) -> None:
            if effect["kind"] == "write_file" and "defect fixed" in effect["payload"].get("content", ""):
                effect["payload"]["content"] = effect["payload"]["content"].replace("defect fixed", "something else")

        for label, window, change in (
            ("reserved relation ID", "registration applied", reserved),
            ("reserved relation ID", "registration recorded", reserved),
            ("relation ID", "registration recorded", relation_id),
            ("relation target", "registration recorded", target),
            ("relation type", "registration recorded", relation_type),
            ("registration payload", "registration recorded", work_body),
        ):
            with self.subTest(tampered=label, window=window):
                self.setUp()
                self.interrupt(self.stuck_windows()[window], self.outer())
                self.tamper(change)
                refused = self.assertNotReplayed(self.outer())
                self.assertIn("other than the registration the derivation it decided makes", str(refused))
                self.assertEqual(self.events(self.h1), WORK_STARTED)

    def test_a_record_the_mutation_controller_refuses_is_still_refused_there(self) -> None:
        """An applied relation whose record was changed is refused by the replay itself, as before."""
        for label, change in (("relation target", lambda e: e["payload"]["record"].update({"to": self.i1})),
                              ("relation type", lambda e: e["payload"]["record"].update({"type": "planned_next"})),
                              ("relation ID", lambda e: e["payload"]["record"].update({"id": new_id("relation")}))):
            with self.subTest(tampered=label):
                self.setUp()
                self.interrupt(self.stuck_windows()["registration applied"], self.outer())
                self.tamper(lambda record, effect: change(effect) if self.is_the_ng_s_own(effect) else None)
                head, remote = self.head(), self.remote_head()
                with self.assertRaises(ReconcileRequired):
                    self.outer()()
                self.assertEqual((self.head(), self.remote_head(), self.ran),
                                 (head, remote, ["W1#1", "Integration#1", "Confirmation#1"]))

    def test_a_record_that_cannot_show_the_move_keeps_the_precheck(self) -> None:
        """No kept derivations, or ones that no longer speak for every derivation: nothing is left out."""
        for label, change in (("no derivations kept", lambda notes: notes.pop(st._DERIVATIONS)),
                              ("derivations incomplete", lambda notes: notes[st._DERIVATIONS].update(
                                  {"complete": False, "derivations": []}))):
            with self.subTest(record=label):
                self.setUp()
                self.interrupt(self.stuck_windows()["registration applied"], self.outer())
                self.edit_record(lambda record: change(record["notes"]))
                refused = self.assertStoppedUntouched(self.outer(), "dependency_unsatisfied")
                self.assertIn(self.named("I2")[0], str(refused))

    def test_a_derivation_kept_before_displays_were_is_still_its_own_move(self) -> None:
        """BL-048's legacy entry proves the move all the same; its commit is shown by the NG's shape."""
        self.interrupt(self.stuck_windows()["registration applied"], self.outer())
        self.edit_record(lambda record: record["notes"][st._DERIVATIONS]["derivations"][0].pop("display"))
        self.assertOuterConverged(self.outer()(), self.display(self.h1))


# --------------------------------------------------------------------------- a Derive(move=True) of any Work
class MoveTests(MoveCase):
    #: What W1's move to Fix leaves: the Phase entry's relation, and the move's three.
    RELATIONS = sorted([
        ("requires_completion", "W1", "Integration"),
        ("derived", "W1", "Fix"),
        ("requires_completion", "Fix", "Integration"),
        ("requires_completion", "Fix", "W1"),
    ])

    def moving(self, *, waits: bool = True):
        """W1 moves to Fix - and, with ``waits``, decides that it waits for Fix before it is run again."""
        relations = (RelationSpec("requires_completion", "fix", self.w1),) if waits else ()
        move = st.Derive({"fix": st.DerivedWork("Fix", "Fix done", derivation_detail="why Fix")}, relations=relations, move=True)
        return lambda: st.start(self.store, self.w1, "single-work", by_attempt(self.ran, {("W1", 1): move}, default=completing_executor(self.store)))

    def windows(self) -> dict:
        """Every window between the move's registration and the removal of W1's target, read when each opens."""
        return {
            "registration recorded": lambda: after_recording(rf"^{self.w1}:derive:0$"),
            "one effect of it applied": lambda: after_writing_one(rf"^{self.w1}:derive:0$"),
            "registration applied": lambda: after_applying(rf"^{self.w1}:derive:0$"),
            "removal about to be recorded": lambda: before_recording(rf"^{self.w1}:lifecycle:1$"),
        }

    def assertMovedOnce(self, result, pending: dict, relations: list) -> None:
        self.assertEqual((result.status, result.mutation_id), ("moved", pending["mutation_id"]))
        self.assertEqual(self.ran, ["W1#1"])
        self.assertEqual(self.events(self.w1), MOVED)
        self.assertEqual(len(self.named("Fix")), 1)
        self.assertEqual(self.relations(), relations)
        self.assertEqual(self.derivation_files(), 1)
        self.assertEqual(self.subjects().count(f"chore(workline): branch from {self.display(self.w1)}"), 1)
        self.assertEqual((self.pending(), self.dirty(), self.head()), ([], [], self.remote_head()))
        self.assertEqual(validate_project(self.store), [])

    def test_a_move_that_made_its_work_wait_finishes_from_its_record(self) -> None:
        for window, make in self.windows().items():
            with self.subTest(window=window):
                self.setUp()
                pending = self.interrupt(make, self.moving())
                result, _, stages = self.watching(self.moving())
                self.assertEqual(stages, [f"{self.w1}:lifecycle:1", "commit:0"])
                self.assertMovedOnce(result, pending, self.RELATIONS)

    def test_a_move_that_does_not_make_its_work_wait_is_unchanged(self) -> None:
        relations = [r for r in self.RELATIONS if r != ("requires_completion", "Fix", "W1")]
        for window, make in self.windows().items():
            with self.subTest(window=window):
                self.setUp()
                pending = self.interrupt(make, self.moving(waits=False))
                self.assertMovedOnce(self.moving(waits=False)(), pending, relations)

    def test_a_dependency_an_earlier_derivation_of_the_cycle_registered_is_its_own_too(self) -> None:
        """W1 first derived Fix1 and decided to wait for it, then moved to Fix2. BL-049 counted Fix1's dependency as
        another decision's and stopped; since BL-051 both are the cycle's own, and the move finishes from its record."""
        fix1 = st.DerivedWork("Fix1", "Fix1 done", derivation_detail="why Fix1")
        fix2 = st.DerivedWork("Fix2", "Fix2 done", derivation_detail="why Fix2")
        script = {("W1", 1): st.Derive({"fix1": fix1}, relations=(RelationSpec("requires_completion", "fix1", self.w1),)),
                  ("W1", 2): st.Derive({"fix2": fix2}, relations=(RelationSpec("requires_completion", "fix2", self.w1),), move=True)}
        call = lambda: st.start(self.store, self.w1, "single-work", by_attempt(self.ran, dict(script), default=completing_executor(self.store)))  # noqa: E731
        pending = self.interrupt(lambda: after_applying(rf"^{self.w1}:derive:1$"), call)
        decided = self.display(self.w1)
        result, _, stages = self.watching(call)
        self.assertEqual((result.status, result.mutation_id), ("moved", pending["mutation_id"]))
        # nothing is registered again: only the removal and Git stages (the replay of Fix1's derivation commits the
        # move's registration it finds uncommitted, the replay's own way), the move's commit last
        self.assertEqual([stage for stage in stages if not stage.startswith("commit:")], [f"{self.w1}:lifecycle:1"])
        self.assertEqual(self.subjects()[0], f"chore(workline): branch from {decided}")
        self.assertEqual(self.ran, ["W1#1", "W1#2"])  # neither derivation is decided again
        self.assertEqual((len(self.named("Fix1")), len(self.named("Fix2")), self.derivation_files()), (1, 1, 2))
        self.assertTrue({("requires_completion", "Fix1", "W1"), ("requires_completion", "Fix2", "W1")} <= set(self.relations()))
        self.assertEqual(self.events(self.w1), MOVED)
        self.assertEqual((self.pending(), self.dirty(), self.head()), ([], [], self.remote_head()))

    def test_a_dependency_a_work_is_opened_with_still_stops_it(self) -> None:
        """The precheck of a cycle opened here is the one it always was."""
        with self.assertRaises(StopError) as refused:
            st.start(self.store, self.i1, "single-work", self.completing())
        self.assertEqual(refused.exception.code, "dependency_unsatisfied")
        self.assertEqual((self.ran, self.pending()), ([], []))

    def test_a_derivation_that_does_not_move_is_its_cycle_s_own_too(self) -> None:
        """A derivation that keeps the target and makes its Work wait for its fix, then a question wait. BL-049 left
        this boundary out and the answer's resume stopped on that dependency with nothing interrupted; since BL-051
        the resume continues the same cycle at its next attempt, and the answer's move ends it as it would have."""
        fix = st.DerivedWork("Fix", "Fix done", derivation_detail="why Fix")
        script = {("W1", 1): st.Derive({"fix": fix}, relations=(RelationSpec("requires_completion", "fix", self.w1),)),
                  ("W1", 2): st.QuestionWait("which way?")}
        asked = st.start(self.store, self.w1, "single-work", by_attempt(self.ran, dict(script), default=completing_executor(self.store)))
        self.assertEqual(asked.status, "question_wait")
        answer = {("W1", 2): st.Derive({"other": st.DerivedWork("Other", "o done", derivation_detail="why")}, move=True)}
        result = st.start(self.store, self.w1, "single-work", by_attempt(self.ran, answer, default=completing_executor(self.store)))
        self.assertEqual((result.status, result.mutation_id), ("moved", asked.mutation_id))
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2"])  # the answer is asked of attempt 2, Fix is not derived again
        self.assertEqual((len(self.named("Fix")), len(self.named("Other")), self.derivation_files()), (1, 1, 2))
        self.assertIn(("requires_completion", "Fix", "W1"), self.relations())  # the dependency itself stays
        self.assertEqual(self.events(self.w1), MOVED)
        self.assertEqual((self.pending(), self.dirty(), self.head()), ([], [], self.remote_head()))


if __name__ == "__main__":
    unittest.main()
