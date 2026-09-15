"""A START cancel carries on from the decision it recorded (BL-030).

The executor decides a cancel: which new Works replace the cancelled one, which
relations are added and removed, and why. START kept none of that in its
recovery record - only the cancel's events and the IDs reserved for its replan -
so a cancel interrupted once its events were recorded could not be carried on:
the executor must not run a Work its own cancel made terminal, the Project shows
the decision only part-way, and entering the cancel again moved its stage
prefix, resolved removals that were already applied and registered a new
integration a second time. A single-work retry refused the cancelled Work and an
outer retry stopped, and the mutation stayed pending either way.

START now records the decision on the ``work_cancelled`` effect, in the save
that records the cancel's lifecycle events and the branch they are decided on.
A retry of the same START reads the record before it judges anything on the
Project: the decision and every effect recorded after it must be exactly what
that decision makes; the decision is judged again on the Project without the
cancel's own effects; whatever the rest would refuse is refused before anything
is replayed; and the cancel is then carried through what is left of it - without
asking the executor, with the prefix, the IDs, the removals and a recorded
registration taken from the record - to ``cancelled``, with nothing run after
it. A cancel recorded without a decision, a decision the record cannot keep
exactly, and a record that shows anything less are never carried on.
"""

from __future__ import annotations

import json
import re
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from workline import start as st
from workline import yamlish
from workline.create import RelatedSpec, RelationSpec, WorkSpec, create_standalone_work
from workline.errors import StopError
from workline.ids import new_id
from workline.mutation import CLOSED_RECORD_FIELDS, EFFECT_KINDS, INTENT_VERSION, Mutation, MutationController
from workline.ops import Replan
from workline.state import ProjectView
from workline.store import Relation, render_relations
from workline.validate import validate_project

EVENT_LOG = ".workline/events/events.jsonl"
ROADMAP = ".workline/relations/roadmap.yaml"
MAIN = "refs/heads/main"
#: The key of the ``work_cancelled`` payload that holds the cancel's decision, and the key of an effect's branch binding.
DECISION, DECIDED_ON = "cancel", "decided_on"


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


# --------------------------------------------------------------------------- interruption windows
def after_recording(pattern: str):
    """Stop right after a stage matching ``pattern`` is durably recorded, none of it applied."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        real(mutation, stage, effects)
        if re.search(pattern, stage):
            raise Interrupted(f"recorded {stage}")

    return mock.patch.object(Mutation, "add_effects", fire)


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


def around_push(pattern: str, *, pushed: bool):
    """Stop just before (``pushed=False``) or just after the push of a stage matching ``pattern``."""
    real = MutationController.apply_effect

    def fire(controller, record):
        ours = record["kind"] == "git_push" and re.search(pattern, record["stage"])
        if ours and not pushed:
            raise Interrupted("committed, not pushed")
        result = real(controller, record)
        if ours and pushed:
            raise Interrupted("pushed")
        return result

    return mock.patch.object(MutationController, "apply_effect", fire)


def before_committing():
    """Stop once the replan is applied and validated, before the commit carrying the cancel is recorded."""

    def fire(*args, **kwargs):
        raise Interrupted("before the commit is recorded")

    return mock.patch.object(st.gitops, "finalize", fire)


def cancel_windows(work_id: str) -> dict:
    lifecycle = rf"^{work_id}:lifecycle:1$"
    return {
        "cancel recorded": lambda: after_recording(lifecycle),  # C2 / C3: the decision and the events, one save
        "cancel applied": lambda: after_applying(lifecycle),  # C4
        "works recorded": lambda: after_recording(rf"^{work_id}:cancel:0:(works|relations)$"),  # C5
        "works applied": lambda: after_applying(rf"^{work_id}:cancel:0:(works|relations)$"),  # C6
        "removals recorded": lambda: after_recording(rf"^{work_id}:cancel:0:remove$"),  # C7
        "removals applied": lambda: after_applying(rf"^{work_id}:cancel:0:remove$"),  # C8
        "replan validated": before_committing,  # C8, its structural validation passed
        "commit recorded": lambda: after_recording(r"^commit:\d+$"),  # C9
        "committed": lambda: around_push(r"^commit:\d+$", pushed=False),  # C10
        "pushed": lambda: around_push(r"^commit:\d+$", pushed=True),  # C11
    }


# What a retry of the confirmation repoint still has to execute from each window.
REPOINT_LEFT = {
    "cancel recorded": ["append_event", "append_event", "write_file", "add_relation", "add_relation",
                        "remove_relation", "remove_relation", "git_commit", "git_push"],
    "cancel applied": ["write_file", "add_relation", "add_relation", "remove_relation", "remove_relation", "git_commit", "git_push"],
    "works recorded": ["write_file", "add_relation", "add_relation", "remove_relation", "remove_relation", "git_commit", "git_push"],
    "works applied": ["remove_relation", "remove_relation", "git_commit", "git_push"],
    "removals recorded": ["remove_relation", "remove_relation", "git_commit", "git_push"],
    "removals applied": ["git_commit", "git_push"],
    "replan validated": ["git_commit", "git_push"],
    "commit recorded": ["git_commit", "git_push"],
    "committed": ["git_push"],
    "pushed": [],
}
REPOINT_STAGES = ["<I1>:lifecycle:0", "<I1>:lifecycle:1", "<I1>:cancel:0:works", "<I1>:cancel:0:remove", "commit:0"]


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


class CancelCase(WorklineTestCase):
    def build(self, name: str = "proj") -> None:
        self.name = name
        self.store = self.new_project(name, remote=True)
        self.ran: list[str] = []

    def setUp(self) -> None:
        super().setUp()
        self.build()

    # fixtures ---------------------------------------------------------------
    def rel(self, rel_type: str, a: str, b: str) -> str:
        (found,) = [r.id for r in ProjectView.load(self.store).roadmap_relations if (r.type, r.from_id, r.to) == (rel_type, a, b)]
        return found

    def executor(self, outcomes: dict | None = None):
        """Completes every Work with a result file, except the Works given another outcome (callables are called)."""
        done = completing_executor(self.store, self.ran)
        outcomes = outcomes or {}

        def execute(ctx: st.ExecutionContext):
            if ctx.work.id not in outcomes:
                return done(ctx)
            self.ran.append(ctx.work.id)
            outcome = outcomes[ctx.work.id]
            return outcome(ctx) if callable(outcome) else outcome

        return execute

    def repoint(self, mode: str = "single-work"):
        """I1 cancelled after W1 completed; I2 replaces it and the confirmation now waits for I2 (BL-028 (B))."""
        roadmap = self.simple_roadmap(self.store)
        self.rid, self.pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, self.pa, confirmation=True)
        w1, i1, c1 = entry.work_ids["w1"], entry.integration_id, entry.confirmation_id
        st.start(self.store, w1, "single-work", completing_executor(self.store))
        replan = Replan(
            remove_relation_ids=(self.rel("requires_completion", w1, i1), self.rel("requires_completion", i1, c1)),
            add_relations=(RelationSpec("requires_completion", w1, "i2"), RelationSpec("requires_completion", "i2", c1)),
            new_works={"i2": WorkSpec("I2", "i2", phase_id=self.pa, roadmap_id=self.rid, work_kind="phase_integration_check")},
        )
        cancel = st.Cancel(replan, "scope")
        return entry, cancel, lambda: st.start(self.store, i1, mode, self.executor({i1: cancel}))

    def replacement(self):
        """W1 cancelled and replaced by R, which must read documents and records why it was derived."""
        self.human_commit({"doc.md": "doc\n"}, "docs: doc", push=True)
        roadmap = self.simple_roadmap(self.store)
        self.rid, self.pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, self.pa, {"w1": "W1", "w2": "W2"})
        w1, i1 = entry.work_ids["w1"], entry.integration_id
        replan = Replan(
            remove_relation_ids=(self.rel("requires_completion", w1, i1),),
            add_relations=(RelationSpec("requires_completion", "007", i1),),
            new_works={"007": WorkSpec(
                "置き換え R", "  replaces W1\n", phase_id=self.pa, roadmap_id=self.rid,
                related=(RelatedSpec("must_read", "doc.md"),
                         RelatedSpec("conditional_must_read", "doc.md", {"kind": "path_glob", "pattern": "*.md", "why": "docs"})),
                derivation_detail="W1 was the wrong cut",
            )},
        )
        cancel = st.Cancel(replan, "superseded")
        return entry, cancel, lambda: st.start(self.store, w1, "single-work", self.executor({w1: cancel}))

    def standalone_chain(self, *names: str) -> list[str]:
        ids = [create_standalone_work(self.store, WorkSpec(name, name.lower())).work_id for name in names]
        if len(ids) > 1:
            helper = create_standalone_work(self.store, WorkSpec("Helper", "helper")).work_id
            relations = tuple(RelationSpec("planned_next", a, b) for a, b in zip(ids, ids[1:]))
            st.plan_exclude_standalone_work(self.store, helper, Replan(add_relations=relations))
        return ids

    def human_commit(self, files: dict[str, str], message: str, *, push: bool = False) -> str:
        for path, content in files.items():
            (self.store.root / path).write_text(content, encoding="utf-8", newline="\n")
        git(self.store.root, "add", "--", *files)
        git(self.store.root, "commit", "-q", "-m", message, "--", *files)
        if push:
            git(self.store.root, "push", "-q", "origin", "main")
        return self.head()

    # running ------------------------------------------------------------------
    def interrupt(self, window, call) -> dict:
        with window(), self.assertRaises(Interrupted):
            call()
        (pending,) = MutationController(self.store).list_pending()
        return pending

    def watching(self, call, executed: list[str], stages: list[str] | None = None):
        real_apply, real_add = MutationController.apply_effect, Mutation.add_effects

        def watch(controller, record):
            executed.append(record["kind"])
            return real_apply(controller, record)

        def add(mutation, stage, effects):
            real_add(mutation, stage, effects)
            if stages is not None:
                stages.append(stage)

        with mock.patch.object(MutationController, "apply_effect", watch), mock.patch.object(Mutation, "add_effects", add):
            return call()

    # observation --------------------------------------------------------------
    def display(self, work_id: str) -> str:
        return ProjectView.load(self.store).works[work_id].display

    def subjects(self) -> list[str]:
        return git(self.store.root, "log", "--format=%s").splitlines()

    def head(self) -> str:
        return git(self.store.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote_path(self.name), "rev-parse", "main").strip()

    def dirty(self) -> list[str]:
        status = git(self.store.root, "status", "--porcelain", "--untracked-files=all").splitlines()
        return [line for line in status if ".workline/runtime/" not in line]

    def snapshot(self) -> dict:
        """Everything a refused retry must leave exactly as it was: the records byte for byte, the Project, Git."""
        root = self.store.root
        return {
            "records": {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))},
            "files": {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted((root / ".workline").rglob("*"))
                      if p.is_file() and "runtime" not in p.relative_to(root).parts},
            "head": self.head(),
            "on": git(root, "symbolic-ref", "--quiet", "HEAD", check=False).strip(),
            "remote": self.remote_head(),
            "dirty": self.dirty(),
        }

    def edges(self) -> list[tuple[str, str, str]]:
        return sorted((r.type, r.from_id, r.to) for r in ProjectView.load(self.store).roadmap_relations)

    def named(self, name: str) -> list[str]:
        return [w.id for w in ProjectView.load(self.store).works.values() if w.name == name]

    def introduced_by(self, work_id: str, event_type: str) -> list[str]:
        """For each such event in the log, the subject of the commit that brought it into the event log."""
        found = []
        for event in ProjectView.load(self.store).events:
            if event.entity == work_id and event.type == event_type:
                subjects = git(self.store.root, "log", "--format=%s", "-S", event.id, "--", EVENT_LOG).splitlines()
                found.append(subjects[-1] if subjects else "uncommitted")
        return found

    def edit_record(self, pending: dict, change) -> None:
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8")

    @staticmethod
    def cancel_effect(record: dict, work_id: str) -> dict:
        (effect,) = [e for e in record["effects"] if e["kind"] == "append_event"
                     and e["payload"]["record"]["type"] == "work_cancelled" and e["payload"]["record"]["entity"] == work_id]
        return effect

    def record_of(self, mutation_id: str) -> dict:
        (record,) = [r for r in MutationController(self.store).list_records() if r["mutation_id"] == mutation_id]
        return record

    def assertCancelled(self, work_id: str) -> None:
        """The cancel was carried by its own commit, once, and pushed; nothing is left behind."""
        subject = f"chore(workline): cancel {self.display(work_id)}"
        self.assertEqual(self.introduced_by(work_id, "work_cancelled"), [subject])
        self.assertEqual(self.subjects().count(subject), 1)
        self.assertEqual(self.head(), self.remote_head())
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(self.dirty(), [])
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(len(self.edges()), len(set(self.edges())))

    def assertStoppedUntouched(self, pending_ids: list[str], call, code: str = "reconcile_required") -> StopError:
        """The retry STOPs having executed nothing, asked no executor and changed nothing at all."""
        before, ran, executed = self.snapshot(), list(self.ran), []
        with self.assertRaises(StopError) as stopped:
            self.watching(call, executed)
        self.assertEqual(stopped.exception.code, code, stopped.exception.message)
        self.assertEqual(executed, [])
        self.assertEqual(self.ran, ran)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(sorted(p["mutation_id"] for p in MutationController(self.store).list_pending()), sorted(pending_ids))
        return stopped.exception


# --------------------------------------------------------------------------- the record
class DecisionRecordTests(CancelCase):
    def test_the_decision_is_durable_in_the_save_that_records_the_cancel_events_and_their_branch(self) -> None:
        entry, _, call = self.repoint()
        i1 = entry.integration_id
        saves: list[dict] = []
        real_save = Mutation._save

        def save(mutation):
            real_save(mutation)
            on_disk = yamlish.load(mutation.path.read_text(encoding="utf-8"))
            if on_disk["invocation"].get("work_id") == i1:
                saves.append(on_disk)

        stages: list[str] = []
        with mock.patch.object(Mutation, "_save", save):
            result = self.watching(call, [], stages)

        self.assertEqual((result.status, result.detail), ("cancelled", "scope"))
        with_events = [i for i, r in enumerate(saves) if any(
            e["kind"] == "append_event" and e["payload"]["record"]["type"] == "work_cancelled" for e in r["effects"])]
        with_decision = [i for i, r in enumerate(saves) if any(DECISION in e["payload"] for e in r["effects"])]
        self.assertEqual(with_events[0], with_decision[0])  # one save: never the events without their decision
        lifecycle = [e for e in saves[with_events[0]]["effects"] if e["stage"] == f"{i1}:lifecycle:1"]
        self.assertEqual([DECISION in e["payload"] for e in lifecycle], [False, True])  # on the work_cancelled effect only
        binding = lifecycle[0][DECIDED_ON]
        self.assertEqual(([e[DECIDED_ON] for e in lifecycle], binding["branch"]), ([binding, binding], MAIN))  # and its branch
        (commit,) = [e for e in saves[-1]["effects"] if e["kind"] == "git_commit"]
        self.assertEqual(commit["payload"]["branch"], binding["branch"])  # which the commit takes over
        # Nothing else about the record changed: the same stages in the same order, no new field, kind or version.
        self.assertEqual([re.sub(r"^w_\w+:", "<I1>:", s) for s in stages], REPOINT_STAGES)
        self.assertEqual(set(saves[-1]), CLOSED_RECORD_FIELDS)
        self.assertEqual((INTENT_VERSION, EFFECT_KINDS),
                         (1, ("write_file", "add_relation", "remove_relation", "append_event", "git_commit", "git_push")))
        # and the closed record of an uninterrupted cancel is still taken away (BL-019)
        self.assertNotIn(result.mutation_id, {r["mutation_id"] for r in MutationController(self.store).list_records()})

    def test_the_decision_holds_what_the_executor_decided_exactly(self) -> None:
        entry, cancel, call = self.replacement()
        w1, i1 = entry.work_ids["w1"], entry.integration_id
        (removed,) = [r.to_record() for r in ProjectView.load(self.store).roadmap_relations if r.id in cancel.replan.remove_relation_ids]
        pending = self.interrupt(cancel_windows(w1)["cancel recorded"], call)

        decision = self.cancel_effect(pending, w1)["payload"][DECISION]

        self.assertEqual(decision, {
            "version": 1,
            "work_id": w1,
            "prefix": f"{w1}:cancel:0",
            "reason": "superseded",
            "new_works": [{
                "key": "007", "name": "置き換え R", "desired_state": "  replaces W1\n", "phase_id": self.pa,
                "roadmap_id": self.rid, "work_kind": None, "confirmation_target": None,
                "related": [{"type": "must_read", "to": "doc.md", "condition": None},
                            {"type": "conditional_must_read", "to": "doc.md",
                             "condition": {"kind": "path_glob", "pattern": "*.md", "why": "docs"}}],
                "derivation_detail": "W1 was the wrong cut",
            }],
            "add_relations": [{"type": "requires_completion", "from": "007", "to": i1}],
            "remove_relations": [removed],
        })
        # The IDs stay the record's reservations; the decision does not repeat them.
        reserved = pending["reserved_ids"]
        self.assertNotIn(reserved[f"{w1}:cancel:0:works:work:007"], canonical(decision))
        self.assertNotIn(reserved[f"{w1}:cancel:0:works:rel:0"], canonical(decision))


# --------------------------------------------------------------------------- what a record can keep (U5)
class DecisionValueTests(CancelCase):
    def test_every_value_a_cancel_takes_is_kept_exactly_and_carried_on(self) -> None:
        reasons = {
            "text a record has to quote": '  why: "not needed" # after all\n\tsecond line\r\n',
            "text that reads as another value": "null",
            "empty text": "",
            "non-ASCII text": "不要になった",
            "a number": 7,
            "a flag": True,
            "nothing": None,
            "a list": ["one", "two"],
            "a mapping": {"why": "not needed", "count": 2},
            "text holding a next line (U+0085)": "not\x85needed",
            "text holding a line separator (U+2028)": "not\N{LINE SEPARATOR}needed",
            "text holding a paragraph separator (U+2029)": "not\N{PARAGRAPH SEPARATOR}needed",
        }
        works = [create_standalone_work(self.store, WorkSpec(f"S{index}", f"s{index}")).work_id for index in range(len(reasons))]
        for work, (label, reason) in zip(works, reasons.items()):
            with self.subTest(reason=label):
                call = lambda: st.start(self.store, work, "single-work", self.executor({work: st.Cancel(Replan(), reason)}))  # noqa: E731,B023
                pending = self.interrupt(cancel_windows(work)["cancel applied"], call)
                self.assertEqual(canonical(self.cancel_effect(pending, work)["payload"][DECISION]["reason"]), canonical(reason))

                result = call()

                self.assertEqual((result.status, result.mutation_id), ("cancelled", pending["mutation_id"]))
                self.assertEqual((type(result.detail), canonical(result.detail)), (type(reason), canonical(reason)))
                self.assertEqual(self.ran.count(work), 1)
                self.assertCancelled(work)

    def test_a_value_the_record_cannot_keep_refuses_the_cancel_before_anything_of_it_is_recorded(self) -> None:
        cases = {
            "a fraction": (Replan(), 1.5, "cancel.reason (float)"),
            "a tuple": (Replan(), ("not", "needed"), "cancel.reason (tuple)"),
            "an object": (Replan(), object(), "cancel.reason (object)"),
            "text holding a lone surrogate": (Replan(), "not" + chr(0xD800) + "needed", "cancel.reason (str)"),
            "a list in a list": (Replan(), [["not", "needed"]], "cancel.reason (list)"),
            "a key that reads back as text": (Replan(), [{1: "not needed"}], "cancel.reason[0] (dict)"),
            "a new Work's key that is a tuple": (
                lambda work: Replan(new_works={("t",): WorkSpec("T", "t")}), "replaced", "cancel.new_works[0].key (tuple)"),
            "a Related that is no RelatedSpec": (
                lambda work: Replan(new_works={"t": WorkSpec("T", "t", related=({"type": "must_read", "to": "x.md"},))}),
                "replaced", "the replan is not one a cancel decision can record"),
            "a new Work's name that is not text": (
                lambda work: Replan(new_works={"t": WorkSpec(5, "t")}), "replaced", "new Works in another form"),
        }
        works = [create_standalone_work(self.store, WorkSpec(f"S{index}", f"s{index}")).work_id for index in range(len(cases))]
        for work, (label, (replan, reason, fragment)) in zip(works, cases.items()):
            with self.subTest(value=label):
                before = self.snapshot()
                decided = st.Cancel(replan(work) if callable(replan) else replan, reason)
                call = lambda: st.start(self.store, work, "single-work", self.executor({work: decided}))  # noqa: E731,B023

                with self.assertRaises(StopError) as refused:
                    call()

                self.assertEqual(refused.exception.code, "validation_failed", refused.exception.message)
                self.assertIn(fragment, refused.exception.message)
                self.assertIn("nothing of it is recorded", refused.exception.message)
                (pending,) = MutationController(self.store).list_pending()
                # Only the Work's opening lifecycle is recorded: no cancel event, no replan stage, no decision.
                self.assertEqual([e["stage"] for e in pending["effects"]], [f"{work}:lifecycle:0", f"{work}:lifecycle:0"])
                self.assertEqual([e["payload"]["record"]["type"] for e in pending["effects"]], ["work_started", "work_target_added"])
                self.assertEqual(ProjectView.load(self.store).work_state(work).state, "in_progress")
                self.assertEqual((self.head(), self.remote_head()), (before["head"], before["remote"]))
                # Nothing was decided, so a retry asks the executor again, as for any outcome not recorded yet.
                result = st.start(self.store, work, "single-work", self.executor({work: st.Cancel(Replan(), "not needed")}))
                self.assertEqual((result.status, result.detail, result.mutation_id), ("cancelled", "not needed", pending["mutation_id"]))
                self.assertEqual(self.ran.count(work), 2)
                self.assertCancelled(work)


# --------------------------------------------------------------------------- the same START again
class ResumeWindowTests(CancelCase):
    def test_every_window_carries_on_only_what_is_left_of_the_cancel(self) -> None:
        for index, window in enumerate(REPOINT_LEFT):
            with self.subTest(window=window):
                self.build(f"repoint-{index}")
                entry, _, call = self.repoint()
                w1, i1, c1 = entry.work_ids["w1"], entry.integration_id, entry.confirmation_id
                pending = self.interrupt(cancel_windows(i1)[window], call)
                self.assertEqual(self.ran, [i1])

                executed: list[str] = []
                stages: list[str] = []
                # Nothing of the cancel is decided again: not its prefix, its IDs or its removals.
                with mock.patch.object(st, "plan_replan", side_effect=AssertionError("the replan was decided again")):
                    result = self.watching(call, executed, stages)

                self.assertEqual((result.status, result.work_id, result.detail, result.mutation_id),
                                 ("cancelled", i1, "scope", pending["mutation_id"]))
                self.assertEqual(self.ran, [i1])  # the executor was not asked again
                self.assertEqual(executed, REPOINT_LEFT[window])  # nothing applied twice, nothing left out
                recorded = list(dict.fromkeys(e["stage"] for e in pending["effects"]))
                # the prefix and every stage name are the record's: exactly the stages still missing follow, in order
                self.assertEqual([re.sub(r"^w_\w+:", "<I1>:", s) for s in recorded + stages], REPOINT_STAGES)
                (i2,) = self.named("I2")  # registered once: the recorded integration is not counted twice
                self.assertEqual([e for e in self.edges() if e[0] == "requires_completion"],
                                 sorted([("requires_completion", w1, i2), ("requires_completion", i2, c1)]))
                self.assertCancelled(i1)
                record = self.record_of(pending["mutation_id"])
                self.assertEqual(record["status"], "completed")
                self.assertEqual(record["reserved_ids"], pending["reserved_ids"])  # nothing reserved again
                (commit,) = [e for e in record["effects"] if e["kind"] == "git_commit"]
                self.assertEqual(commit["payload"]["branch"], self.cancel_effect(record, i1)[DECIDED_ON]["branch"])

    def test_related_and_derivation_come_from_the_decision_and_the_record(self) -> None:
        for index, window in enumerate(("cancel applied", "works recorded", "works applied")):
            with self.subTest(window=window):
                self.build(f"replace-{index}")
                entry, _, call = self.replacement()
                w1 = entry.work_ids["w1"]
                pending = self.interrupt(cancel_windows(w1)[window], call)

                result = call()

                self.assertEqual((result.status, result.detail), ("cancelled", "superseded"))
                (r,) = self.named("置き換え R")
                view = ProjectView.load(self.store)
                self.assertEqual([(x.type, x.to, x.extra.get("condition")) for x in view.related_from(r)],
                                 [("must_read", "doc.md", None),
                                  ("conditional_must_read", "doc.md", {"kind": "path_glob", "pattern": "*.md", "why": "docs"})])
                self.assertIn("replaces W1", view.works[r].body)
                derivations = sorted((self.store.root / ".workline" / "derivations").glob("*.md"))
                self.assertEqual(len(derivations), 1)
                self.assertIn("W1 was the wrong cut", derivations[0].read_text(encoding="utf-8"))
                self.assertEqual(self.ran, [w1])
                self.assertCancelled(w1)
                reserved = self.record_of(pending["mutation_id"])["reserved_ids"]
                self.assertEqual({k: v for k, v in reserved.items() if k in pending["reserved_ids"]}, pending["reserved_ids"])


# --------------------------------------------------------------------------- before the decision is recorded (C0 / C1)
class ExecutorWindowTests(CancelCase):
    def test_the_executor_failing_leaves_nothing_decided_and_runs_again(self) -> None:
        (s1,) = self.standalone_chain("S1")
        attempts: list[int] = []

        def outcome(ctx):
            attempts.append(ctx.attempt)
            if len(attempts) == 1:
                raise Interrupted("the executor failed before returning")
            return st.Cancel(Replan(), "not needed")

        call = lambda: st.start(self.store, s1, "single-work", self.executor({s1: outcome}))  # noqa: E731
        with self.assertRaises(Interrupted):
            call()
        (pending,) = MutationController(self.store).list_pending()

        result = call()

        self.assertEqual((result.status, result.mutation_id), ("cancelled", pending["mutation_id"]))
        self.assertEqual(len(attempts), 2)
        self.assertCancelled(s1)

    def test_before_the_cancel_is_recorded_the_retry_decides_again(self) -> None:
        real_plan = st.plan_replan

        def reserved_then_stopped(*args, **kwargs):
            real_plan(*args, **kwargs)
            raise Interrupted("IDs reserved")

        def events_reserved_then_stopped():
            real_add = Mutation.add_effects

            def fire(mutation, stage, effects):
                if any(e.kind == "append_event" and e.payload["record"]["type"] == "work_cancelled" for e in effects):
                    raise Interrupted("event IDs reserved, stage not recorded")
                return real_add(mutation, stage, effects)

            return mock.patch.object(Mutation, "add_effects", fire)

        windows = {
            "replan IDs reserved": lambda: mock.patch.object(st, "plan_replan", reserved_then_stopped),
            "event IDs reserved": events_reserved_then_stopped,
        }
        for index, (label, window) in enumerate(windows.items()):
            with self.subTest(window=label):
                self.build(f"decide-{index}")
                entry, cancel, call = self.replacement()
                w1 = entry.work_ids["w1"]
                pending = self.interrupt(window, call)
                self.assertFalse(any(DECISION in e["payload"] for e in pending["effects"]))
                changed = st.Cancel(Replan(remove_relation_ids=cancel.replan.remove_relation_ids,
                                           add_relations=(RelationSpec("requires_completion", "s", entry.integration_id),),
                                           new_works={"s": WorkSpec("S", "s", phase_id=self.pa, roadmap_id=self.rid)}),
                                    "second thoughts")

                result = st.start(self.store, w1, "single-work", self.executor({w1: changed}))

                self.assertEqual((result.status, result.detail, result.mutation_id), ("cancelled", "second thoughts", pending["mutation_id"]))
                self.assertEqual((self.named("置き換え R"), len(self.named("S"))), ([], 1))
                self.assertEqual(self.ran, [w1, w1])
                self.assertCancelled(w1)


# --------------------------------------------------------------------------- once the decision is recorded
class RecordedDecisionTests(CancelCase):
    def test_a_retry_whose_executor_would_decide_otherwise_carries_on_the_recorded_decision(self) -> None:
        def raises(ctx):
            raise AssertionError("the executor must not be asked about a Work its recorded cancel made terminal")

        for index, (label, other) in enumerate({
            "another cancel": st.Cancel(Replan(), "changed my mind"),
            "a completion": st.Completed(),
            "an executor that fails": raises,
        }.items()):
            with self.subTest(retry=label):
                self.build(f"changed-{index}")
                entry, _, call = self.repoint()
                i1 = entry.integration_id
                pending = self.interrupt(cancel_windows(i1)["cancel applied"], call)

                result = st.start(self.store, i1, "single-work", self.executor({i1: other}))

                self.assertEqual((result.status, result.detail, result.mutation_id), ("cancelled", "scope", pending["mutation_id"]))
                self.assertEqual(self.ran, [i1])
                self.assertEqual(len(self.named("I2")), 1)
                self.assertCancelled(i1)

    def test_a_cancelled_work_is_still_not_started_again_once_the_cancel_is_done(self) -> None:
        entry, _, call = self.repoint()
        i1 = entry.integration_id
        self.interrupt(cancel_windows(i1)["cancel applied"], call)
        self.assertEqual(call().status, "cancelled")

        with self.assertRaises(StopError) as refused:
            call()

        self.assertEqual(refused.exception.code, "spec_violation")
        self.assertIn("is cancelled", refused.exception.message)

    def test_another_mode_or_another_work_does_not_take_the_cancel_over(self) -> None:
        entry, _, call = self.repoint()
        i1, c1 = entry.integration_id, entry.confirmation_id
        pending = self.interrupt(cancel_windows(i1)["cancel recorded"], call)

        for label, other in (("another mode", lambda: st.start(self.store, i1, "outer", self.executor())),
                             ("another Work", lambda: st.start(self.store, c1, "single-work", self.executor()))):
            with self.subTest(retry=label):
                self.assertStoppedUntouched([pending["mutation_id"]], other)

        self.assertEqual(call().status, "cancelled")
        self.assertCancelled(i1)


# --------------------------------------------------------------------------- outer (U2)
class OuterTests(CancelCase):
    def test_an_outer_start_finishes_the_cancel_and_goes_no_further(self) -> None:
        for index, window in enumerate(("cancel recorded", "cancel applied", "commit recorded", "committed", "pushed")):
            with self.subTest(window=window):
                self.build(f"outer-{index}")
                s1, s2, s3 = self.standalone_chain("S1", "S2", "S3")
                call = lambda: st.start(self.store, s1, "outer", self.executor({s2: st.Cancel(Replan(), "not needed")}))  # noqa: E731,B023
                pending = self.interrupt(cancel_windows(s2)[window], call)

                result = call()

                self.assertEqual((result.status, result.work_id, result.detail, result.mutation_id),
                                 ("cancelled", s2, "not needed", pending["mutation_id"]))
                self.assertEqual(self.ran, [s1, s2])  # S3 did not run, S2 was not asked again
                self.assertEqual(ProjectView.load(self.store).work_state(s3).state, "unstarted")
                self.assertEqual(self.introduced_by(s1, "work_completed"), [f"chore(workline): complete {self.display(s1)}"])
                self.assertCancelled(s2)

    def test_an_outer_start_finishes_a_phase_replan_before_anything_else(self) -> None:
        entry = self.simple_entry(self.store, self.simple_roadmap(self.store).phase_ids["a"], {"w1": "one", "w2": "two"},
                                  planned_next=(("w1", "w2"),))
        w1, w2, i1 = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id
        cancel = st.Cancel(Replan(remove_relation_ids=(self.rel("requires_completion", w2, i1),)), "not needed")
        call = lambda: st.start(self.store, w1, "outer", self.executor({w2: cancel}))  # noqa: E731
        pending = self.interrupt(cancel_windows(w2)["cancel applied"], call)
        self.assertNotEqual(validate_project(self.store), [])  # the Project shows the cancel part-way

        result = call()

        self.assertEqual((result.status, result.work_id, result.mutation_id), ("cancelled", w2, pending["mutation_id"]))
        self.assertEqual(self.ran, [w1, w2])  # the integration did not run
        self.assertCancelled(w2)


# --------------------------------------------------------------------------- a record without a decision (U4)
class LegacyRecordTests(CancelCase):
    def test_a_cancel_recorded_without_a_decision_is_never_carried_on_even_once_its_commit_is_recorded(self) -> None:
        cases = (("single-work", "cancel recorded"), ("single-work", "removals applied"), ("single-work", "commit recorded"),
                 ("single-work", "committed"), ("outer", "cancel applied"), ("outer", "commit recorded"))
        for index, (mode, window) in enumerate(cases):
            with self.subTest(mode=mode, window=window):
                self.build(f"legacy-{index}")
                entry, _, call = self.repoint(mode)
                i1 = entry.integration_id
                pending = self.interrupt(cancel_windows(i1)[window], call)
                self.edit_record(pending, lambda record: self.cancel_effect(record, i1)["payload"].pop(DECISION))  # noqa: B023

                refused = self.assertStoppedUntouched([pending["mutation_id"]], call)

                self.assertIn("without the decision", refused.message)


# --------------------------------------------------------------------------- what the record has to show
class RecordProofTests(CancelCase):
    """Only a decision the record shows, with only effects that decision makes, is carried on."""

    def test_a_record_that_does_not_show_its_decision_is_not_carried_on(self) -> None:
        def decision(record, i1):
            return self.cancel_effect(record, i1)["payload"][DECISION]

        def written(record):
            return [e for e in record["effects"] if e["kind"] == "write_file"][0]["payload"]

        def stages_swapped(record, i1):
            works = [e for e in record["effects"] if e["stage"] == f"{i1}:cancel:0:works"]
            removals = [e for e in record["effects"] if e["stage"] == f"{i1}:cancel:0:remove"]
            rest = [e for e in record["effects"] if e not in works and e not in removals]
            record["effects"] = rest + removals + works
            for seq, effect in enumerate(record["effects"], start=1):
                effect["seq"] = seq

        tampers = {
            "a decision that is not a mapping": ("works applied", lambda r, i1, w1: self.cancel_effect(r, i1)["payload"].update({DECISION: "scope"})),
            "another version": ("works applied", lambda r, i1, w1: decision(r, i1).update(version=2)),
            "a field missing": ("works applied", lambda r, i1, w1: decision(r, i1).pop("prefix")),
            "another Work": ("works applied", lambda r, i1, w1: decision(r, i1).update(work_id=w1)),
            "another prefix": ("works applied", lambda r, i1, w1: decision(r, i1).update(prefix=f"{i1}:cancel:1")),
            "another new Work than recorded": ("works applied", lambda r, i1, w1: decision(r, i1)["new_works"][0].update(name="I3")),
            "another removal than the Project held": (
                "cancel applied", lambda r, i1, w1: decision(r, i1)["remove_relations"][0].update(type="planned_next")),
            "the decision on another event": ("works applied", lambda r, i1, w1: [
                e for e in r["effects"] if e["stage"] == f"{i1}:lifecycle:1"][0]["payload"].update({DECISION: decision(r, i1)})),
            "another reservation": ("works applied", lambda r, i1, w1: r["reserved_ids"].update({f"{i1}:cancel:0:works:rel:0": new_id("relation")})),
            "a stage it never records": ("works applied", lambda r, i1, w1: r["effects"].append({
                "seq": len(r["effects"]) + 1, "stage": f"{i1}:cancel:0:relations", "kind": "add_relation", "applied": False,
                "payload": {"file": "roadmap", "record": {"id": new_id("relation"), "type": "planned_next", "from": w1, "to": i1}}})),
            "its stages in another order": ("removals applied", lambda r, i1, w1: stages_swapped(r, i1)),
            "another Work recorded": ("works recorded", lambda r, i1, w1: written(r).update(content=written(r)["content"].replace("I2", "I3"))),
            "another commit recorded": ("commit recorded", lambda r, i1, w1: [
                e for e in r["effects"] if e["kind"] == "git_commit"][0]["payload"].update(message="chore(workline): something else")),
        }
        for index, (label, (window, tamper)) in enumerate(tampers.items()):
            with self.subTest(tamper=label):
                self.build(f"tamper-{index}")
                entry, _, call = self.repoint()
                i1, w1 = entry.integration_id, entry.work_ids["w1"]
                pending = self.interrupt(cancel_windows(i1)[window], call)
                self.edit_record(pending, lambda record: tamper(record, i1, w1))  # noqa: B023

                self.assertStoppedUntouched([pending["mutation_id"]], call)

    def test_a_relation_the_project_no_longer_holds_as_the_cancel_found_it_is_not_removed(self) -> None:
        entry, _, call = self.repoint()
        i1, c1 = entry.integration_id, entry.confirmation_id
        pending = self.interrupt(cancel_windows(i1)["works applied"], call)
        view = ProjectView.load(self.store)
        retyped = [Relation(r.id, "planned_next", r.from_id, r.to) if (r.from_id, r.to) == (i1, c1) else r for r in view.roadmap_relations]
        (self.store.root / ROADMAP).write_text(render_relations(retyped), encoding="utf-8", newline="\n")

        refused = self.assertStoppedUntouched([pending["mutation_id"]], call)

        self.assertIn("no longer holds as the cancel found it", refused.message)

    def test_two_records_of_the_same_start_are_not_carried_on(self) -> None:
        entry, _, call = self.repoint()
        pending = self.interrupt(cancel_windows(entry.integration_id)["works applied"], call)
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        twin = new_id("mutation")
        MutationController(self.store).intent_path(twin).write_text(
            path.read_text(encoding="utf-8").replace(pending["mutation_id"], twin), encoding="utf-8")

        self.assertStoppedUntouched([pending["mutation_id"], twin], call)


# --------------------------------------------------------------------------- where it was decided (BL-036 / BL-035 / BL-032)
class BranchTests(CancelCase):
    def test_a_cancel_is_carried_on_only_on_the_branch_it_was_decided_on(self) -> None:
        for index, window in enumerate(("cancel applied", "works applied")):
            with self.subTest(window=window):
                self.build(f"branch-{index}")
                entry, _, call = self.repoint()
                i1 = entry.integration_id
                pending = self.interrupt(cancel_windows(i1)[window], call)
                git(self.store.root, "checkout", "-q", "-b", "side")

                refused = self.assertStoppedUntouched([pending["mutation_id"]], call)

                self.assertIn("no recorded commit finalizes that yet", refused.message)
                git(self.store.root, "checkout", "-q", "main")
                result = call()
                self.assertEqual((result.status, result.mutation_id), ("cancelled", pending["mutation_id"]))
                self.assertEqual(self.ran, [i1])
                self.assertCancelled(i1)
                self.assertEqual(git(self.store.root, "rev-parse", "side").strip(), git(self.store.root, "rev-parse", "HEAD~1").strip())
                (commit,) = [e for e in self.record_of(pending["mutation_id"])["effects"] if e["kind"] == "git_commit"]
                self.assertEqual(commit["payload"]["branch"], MAIN)

    def test_a_recorded_commit_is_made_only_on_its_own_branch(self) -> None:
        entry, _, call = self.repoint()
        i1 = entry.integration_id
        pending = self.interrupt(cancel_windows(i1)["commit recorded"], call)
        git(self.store.root, "checkout", "-q", "-b", "side")

        refused = self.assertStoppedUntouched([pending["mutation_id"]], call)

        self.assertIn("applied with unexpected result", refused.message)
        git(self.store.root, "checkout", "-q", "main")
        self.assertEqual(call().status, "cancelled")
        self.assertCancelled(i1)

    def test_an_independent_commit_on_the_decided_branch_does_not_stop_the_cancel(self) -> None:
        for index, window in enumerate(("cancel applied", "commit recorded")):
            with self.subTest(window=window):
                self.build(f"grown-{index}")
                self.human_commit({"notes.md": "notes\n"}, "docs: notes", push=True)
                entry, _, call = self.repoint()
                i1 = entry.integration_id
                pending = self.interrupt(cancel_windows(i1)[window], call)
                grown = self.human_commit({"notes.md": "notes\nby a person\n"}, "docs: a note")

                result = call()

                self.assertEqual((result.status, result.mutation_id), ("cancelled", pending["mutation_id"]))
                subject = f"chore(workline): cancel {self.display(i1)}"
                made = git(self.store.root, "log", "--format=%H %s").splitlines()
                (cancel_commit,) = [line.split(" ", 1)[0] for line in made if line.split(" ", 1)[1] == subject]
                self.assertEqual(git(self.store.root, "rev-parse", f"{cancel_commit}~1").strip(), grown)
                self.assertCancelled(i1)


# --------------------------------------------------------------------------- the checks a cancel always had
class PreflightTests(CancelCase):
    def test_a_decision_the_project_no_longer_allows_is_refused_before_anything_is_replayed(self) -> None:
        """BL-026: the cancel's projection is judged again, on the Project the decision was made on."""
        entry, _, call = self.repoint()
        i1, c1 = entry.integration_id, entry.confirmation_id
        pending = self.interrupt(cancel_windows(i1)["cancel recorded"], call)
        # A person makes the confirmation return to the integration being cancelled, which the replan does not cover.
        view = ProjectView.load(self.store)
        (self.store.root / ROADMAP).write_text(
            render_relations(view.roadmap_relations + [Relation(new_id("relation"), "return_to", c1, i1)]), encoding="utf-8", newline="\n")

        refused = self.assertStoppedUntouched([pending["mutation_id"]], call, code="spec_violation")

        self.assertIn("cancel replan: structure would be invalid", refused.message)
        self.assertEqual(self.introduced_by(i1, "work_cancelled"), [])  # the recorded events were not replayed

    def test_an_unreplanned_cancel_is_still_refused_before_it_is_recorded(self) -> None:
        """BL-026: a cancel whose replan leaves the structure invalid records nothing of the cancel, decision or not."""
        entry = self.simple_entry(self.store, self.simple_roadmap(self.store).phase_ids["a"])
        w1 = entry.work_ids["w1"]
        call = lambda: st.start(self.store, w1, "single-work", self.executor({w1: st.Cancel()}))  # noqa: E731

        with self.assertRaises(StopError) as refused:
            call()

        self.assertEqual(refused.exception.code, "spec_violation")
        (pending,) = MutationController(self.store).list_pending()
        self.assertFalse(any(e["payload"]["record"]["type"] == "work_cancelled" for e in pending["effects"]))
        self.assertEqual(self.introduced_by(w1, "work_cancelled"), [])

    def test_a_registration_the_core_refuses_is_refused_before_the_retry_writes_anything(self) -> None:
        """BL-027: what the registration core refuses before recording, the retry refuses before replaying or saving."""
        roadmap = self.simple_roadmap(self.store)
        rid, pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, pa, {"w1": "W1", "w2": "W2"})
        w1, i1 = entry.work_ids["w1"], entry.integration_id
        cancel = st.Cancel(Replan(remove_relation_ids=(self.rel("requires_completion", w1, i1),),
                                  add_relations=(RelationSpec("requires_completion", "r", i1),),
                                  new_works={"r": WorkSpec("R", "r", phase_id=pa, roadmap_id=rid,
                                                           related=(RelatedSpec("bogus_type", "doc.md"),))}), "superseded")
        call = lambda: st.start(self.store, w1, "single-work", self.executor({w1: cancel}))  # noqa: E731
        with self.assertRaises(StopError) as first:
            call()
        self.assertEqual(first.exception.code, "validation_failed")  # as before: refused once the cancel events were applied
        (pending,) = MutationController(self.store).list_pending()

        refused = self.assertStoppedUntouched([pending["mutation_id"]], call, code="validation_failed")

        self.assertIn("unknown related type bogus_type", refused.message)

    def test_a_recorded_cancel_the_rest_would_refuse_is_not_replayed(self) -> None:
        """The check before replay: recorded, unapplied cancel events are not applied when the rest of the cancel would be refused."""
        roadmap = self.simple_roadmap(self.store)
        rid, pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, pa, {"w1": "W1", "w2": "W2"})
        w1, i1 = entry.work_ids["w1"], entry.integration_id
        cancel = st.Cancel(Replan(remove_relation_ids=(self.rel("requires_completion", w1, i1),),
                                  add_relations=(RelationSpec("requires_completion", "r", i1),),
                                  new_works={"r": WorkSpec("R", "r", phase_id=pa, roadmap_id=rid,
                                                           related=(RelatedSpec("bogus_type", "doc.md"),))}), "superseded")
        call = lambda: st.start(self.store, w1, "single-work", self.executor({w1: cancel}))  # noqa: E731
        pending = self.interrupt(cancel_windows(w1)["cancel recorded"], call)

        refused = self.assertStoppedUntouched([pending["mutation_id"]], call, code="validation_failed")

        self.assertIn("unknown related type bogus_type", refused.message)
        self.assertEqual(self.introduced_by(w1, "work_cancelled"), [])  # the recorded events were not replayed

    def test_a_commit_that_cannot_be_separated_is_refused_before_anything_is_replayed(self) -> None:
        """A change to the event log from before START would stop the cancel's commit; the retry stops before replaying."""
        (s1,) = self.standalone_chain("S1")
        with open(self.store.events_jsonl, "a", encoding="utf-8", newline="\n") as log:
            log.write("\n")
        call = lambda: st.start(self.store, s1, "single-work", self.executor({s1: st.Cancel(Replan(), "not needed")}))  # noqa: E731
        pending = self.interrupt(cancel_windows(s1)["cancel recorded"], call)

        self.assertStoppedUntouched([pending["mutation_id"]], call, code="dirty_overlap")

        self.assertEqual(self.introduced_by(s1, "work_cancelled"), [])

    def test_cancel_events_someone_else_committed_are_not_reported_as_cancelled(self) -> None:
        (s1,) = self.standalone_chain("S1")
        call = lambda: st.start(self.store, s1, "single-work", self.executor({s1: st.Cancel(Replan(), "not needed")}))  # noqa: E731
        pending = self.interrupt(cancel_windows(s1)["cancel applied"], call)
        git(self.store.root, "add", "--", EVENT_LOG)
        git(self.store.root, "commit", "-q", "-m", "someone committed the event log", "--", EVENT_LOG)

        refused = self.assertStoppedUntouched([pending["mutation_id"]], call)

        self.assertIn("a commit it did not record already holds those events", refused.message)
        self.assertNotEqual(self.head(), self.remote_head())  # nothing was pushed on its behalf

    def test_an_intermediate_structure_is_judged_as_the_cancel_leaves_it(self) -> None:
        """BL-028: between its events and its removals the Project is invalid; the cancel is not refused for that."""
        entry, _, call = self.repoint()
        i1 = entry.integration_id
        self.interrupt(cancel_windows(i1)["removals recorded"], call)
        self.assertNotEqual(validate_project(self.store), [])

        self.assertEqual(call().status, "cancelled")
        self.assertCancelled(i1)


# --------------------------------------------------------------------------- a completion is still BL-031's
class CompletionNeighbourTests(CancelCase):
    def test_an_interrupted_completion_is_still_finalized_by_its_own_resume(self) -> None:
        entry = self.simple_entry(self.store, self.simple_roadmap(self.store).phase_ids["a"])
        w1 = entry.work_ids["w1"]
        call = lambda: st.start(self.store, w1, "single-work", self.executor())  # noqa: E731
        pending = self.interrupt(lambda: after_applying(rf"^{w1}:lifecycle:1$"), call)
        seen: list[object] = []
        real = st._cancel_to_finish

        def watch(*args):
            found = real(*args)
            seen.append(found)
            return found

        executed: list[str] = []
        with mock.patch.object(st, "_cancel_to_finish", watch):
            result = self.watching(call, executed)

        self.assertEqual((result.status, result.mutation_id), ("completed", pending["mutation_id"]))
        self.assertEqual(seen, [None])  # a record without a cancel is not read as one
        self.assertEqual(executed, ["git_commit", "git_push"])
        self.assertEqual(self.ran, [w1])
        self.assertEqual(self.introduced_by(w1, "work_completed"), [f"chore(workline): complete {self.display(w1)}"])


if __name__ == "__main__":
    unittest.main()
