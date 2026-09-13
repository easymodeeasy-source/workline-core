"""A registration the postcheck would refuse is refused before any of it is written (BL-027).

Phase CREATE and CREATE's registration core recorded a stage's effects, applied
them to the Project's files, and only then ran the registration postcheck's
structure check. A request that check refuses - a Phase or Work required to
follow a cancelled or plan-excluded predecessor, a return to a cancelled Phase,
a cycle, a duplicate edge - was refused only after its files and relations were
written: the mutation stayed pending with its effects applied, the Project was
left invalid, and every operation that checks structure stopped behind it, the
replan that would have repaired it included. Roadmap creation also wrote its
Roadmap before Phase CREATE checked its Phases, and Phase entry wrote its normal
Works before the integration and confirmation were checked, so even a request
refused for its payload left a mutation that could no longer be abandoned.

The postcheck's own rule now runs first, on the Project as the registration
would leave it: the effects about to be recorded - and, when a resumed mutation
recorded some already, the ones not applied yet - are read the way the store
will read them back. A request it refuses writes nothing, and a mutation this
run began is abandoned. The refusal is the postcheck's, reported as the
postcheck reported it, only earlier. Roadmap creation decides and checks its
Phases before the Roadmap is recorded, Phase entry checks every stage's payload
before the first stage is recorded, and a resumed registration is checked before
its recorded effects are replayed. A registration nothing refuses is written the
way it always was.
"""

from __future__ import annotations

from contextlib import ExitStack
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git, scripted_executor
from workline import create as cr
from workline import gitcmd, yamlish
from workline import phase_create as pc
from workline import roadmap as rm
from workline import start as st
from workline.create import RelatedSpec, RelationSpec, WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, StopError
from workline.ids import new_id
from workline.mutation import Mutation, MutationController
from workline.ops import Replan
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.state import ProjectView
from workline.store import WORKLINE_DIR
from workline.validate import validate_project

UNKNOWN_PHASE = "p_01ARZ3NDEKTSV4RRFFQ69G5FAV"
UNKNOWN_WORK = "w_01ARZ3NDEKTSV4RRFFQ69G5FAV"


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


def after_recording(stage: str):
    """Stop with ``stage`` durably recorded and none of its effects applied."""
    real = Mutation.add_effects

    def fire(mutation, name, effects):
        real(mutation, name, effects)
        if name == stage:
            raise Interrupted(f"after add_effects({stage})")

    return mock.patch.object(Mutation, "add_effects", fire)


def before_recording(stage: str):
    """Stop with the stage decided and never recorded."""
    real = Mutation.add_effects

    def fire(mutation, name, effects):
        if name == stage:
            raise Interrupted(f"before add_effects({stage})")
        real(mutation, name, effects)

    return mock.patch.object(Mutation, "add_effects", fire)


def before_applying(kind: str):
    """Stop just before the first effect of ``kind`` runs."""
    real = MutationController.apply_effect

    def fire(controller, record):
        if record["kind"] == kind:
            raise Interrupted(f"before {kind}")
        return real(controller, record)

    return mock.patch.object(MutationController, "apply_effect", fire)


class RegistrationCase(WorklineTestCase):
    def plan(self, phases: str = "ab", relations=(), name: str = "proj", *, roadmap: bool = True) -> None:
        """A Project with a remote and, unless told otherwise, one Roadmap of the Phases named by ``phases``."""
        self.name = name
        self.store = self.new_project(name, remote=True)
        if roadmap:
            made = self.simple_roadmap(self.store, {k: (f"Phase {k.upper()}", k.upper()) for k in phases}, relations)
            self.rid = made.roadmap_id
            self.phase = dict(made.phase_ids)

    def add(self, phases: str = "c", relations=(), **kwargs):
        specs = {key: PhaseSpec(f"Phase {key.upper()}", key.upper()) for key in phases}
        return lambda: rm.add_phases(self.store, self.rid, specs, tuple(relations), **kwargs)

    def relation(self, rel_type: str, a: str, b: str) -> str:
        (found,) = [r.id for r in ProjectView.load(self.store).roadmap_relations if (r.type, r.from_id, r.to) == (rel_type, a, b)]
        return found

    def expanded_with_excluded_work(self, key: str, how: str) -> tuple[str, str]:
        """Phase ``key`` expanded with W1 and W2, and W2 then plan-excluded or cancelled with its dependency replanned."""
        made = self.simple_entry(self.store, self.phase[key], {"w1": "W1", "w2": "W2"})
        w1, w2 = made.work_ids["w1"], made.work_ids["w2"]
        replan = Replan(remove_relation_ids=(self.relation("requires_completion", w2, made.integration_id),))
        if how == "plan_excluded":
            rm.plan_exclude_work(self.store, w2, replan)
        else:
            st.start(self.store, w2, "single-work", scripted_executor({w2: [st.Cancel(replan)]}))
        return w1, w2

    def cancel_behind_workline(self, entity: str, event_type: str) -> None:
        """A lifecycle event appended and committed by hand, the way no Workline operation would."""
        with open(self.store.events_jsonl, "a", encoding="utf-8", newline="\n") as handle:
            handle.write('{"id":"%s","type":"%s","entity":"%s","at":"2026-01-01T00:00:00+00:00"}\n'
                         % (new_id("event"), event_type, entity))
        git(self.store.root, "add", f"{WORKLINE_DIR}/events/events.jsonl")
        git(self.store.root, "commit", "-q", "-m", "hand edit")

    # observation -----------------------------------------------------------
    def head(self) -> str | None:
        return gitcmd.head_commit(self.store.root)

    def remote_head(self) -> str:
        return git(self.remote_path(self.name), "rev-parse", "--verify", "--quiet", "refs/heads/main", check=False).strip()

    def dirty(self) -> list[str]:
        status = git(self.store.root, "status", "--porcelain", "--untracked-files=all").splitlines()
        return [line for line in status if ".workline/runtime/" not in line]

    def canonical(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.store.root).as_posix(): path.read_bytes()
            for path in sorted(self.store.workline.rglob("*"))
            if path.is_file() and "runtime" not in path.relative_to(self.store.workline).parts
        }

    def record_bytes(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))}

    def records(self) -> dict[str, dict]:
        """Every recovery record as it reads, apart from the time it was last saved.

        A resumed registration saves its record again when it re-declares its
        scope, before its check runs, exactly as it did before the check existed.
        """
        out = {}
        for path in sorted(self.store.mutations.glob("*.yaml")):
            record = yamlish.load(path.read_text(encoding="utf-8"))
            record.pop("updated_at")
            out[path.name] = record
        return out

    def snapshot(self) -> dict:
        """Everything a refused registration must leave exactly as it was, apart from its own abandoned record."""
        return {"files": self.canonical(), "head": self.head(), "remote": self.remote_head(), "dirty": self.dirty()}

    def watched(self, call):
        """Run ``call``; report its STOP, every stage it recorded and every effect it executed."""
        recorded: list[str] = []
        executed: list[str] = []
        real_add, real_apply = Mutation.add_effects, MutationController.apply_effect

        def add_effects(mutation, stage, effects):
            real_add(mutation, stage, effects)
            recorded.append(stage)

        def apply_effect(controller, record):
            executed.append(record["kind"])
            return real_apply(controller, record)

        refusal = None
        with mock.patch.object(Mutation, "add_effects", add_effects), \
                mock.patch.object(MutationController, "apply_effect", apply_effect):
            try:
                call()
            except StopError as exc:
                refusal = exc
        return refusal, recorded, executed

    def assertRefusedBeforeWriting(self, call) -> StopError:
        """``call`` STOPs with nothing recorded, applied, committed or pushed, and leaves no pending record."""
        before = self.snapshot()
        known = {record["mutation_id"] for record in MutationController(self.store).list_records()}

        refusal, recorded, executed = self.watched(call)

        self.assertIsNotNone(refusal, "the registration was not refused")
        self.assertEqual(recorded, [])
        self.assertEqual(executed, [])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(MutationController(self.store).list_pending(), [])
        for record in MutationController(self.store).list_records():
            if record["mutation_id"] not in known:  # the one this request began, and gave up
                self.assertEqual((record["status"], record["effects"]), ("abandoned", []))
        self.assertEqual(validate_project(self.store), [])
        return refusal

    def unchecked(self) -> ExitStack:
        """Registration the way it ran before its check moved ahead of its effects."""
        stack = ExitStack()
        nothing = lambda *args, **kwargs: None  # noqa: E731
        stack.enter_context(mock.patch.object(cr, "refuse_invalid_work_writes", nothing))
        stack.enter_context(mock.patch.object(pc, "refuse_invalid_phase_writes", nothing))
        stack.enter_context(mock.patch.object(rm, "refuse_invalid_phase_writes", nothing))
        stack.enter_context(mock.patch.object(rm, "refuse_invalid_work_writes", nothing))
        stack.enter_context(mock.patch.object(rm, "validate_work_specs", nothing))
        stack.enter_context(mock.patch.object(rm, "decide_phases", lambda *args, **kwargs: mock.Mock(effects=())))
        return stack

    def assertTheRefusalThePostcheckGave(self, refusal: StopError, call) -> None:
        """The same request, run as before, writes its effects and then fails with this same refusal.

        IDs are compared by the reservation that issued them: the refused request
        abandoned its record, so the run below reserves its own.
        """
        refused = {r["mutation_id"]: r for r in MutationController(self.store).list_records()}
        with self.unchecked():
            before, recorded, executed = self.watched(call)
        self.assertIsNotNone(before)
        self.assertTrue(executed, "the old order wrote nothing, so it proves nothing")
        self.assertEqual((before.code, type(before)), (refusal.code, type(refusal)))
        (pending,) = MutationController(self.store).list_pending()
        (abandoned,) = [r for r in refused.values() if r["status"] == "abandoned" and r["invocation"] == pending["invocation"]][-1:]
        expected = str(before)
        for key, value in pending["reserved_ids"].items():
            if key in abandoned["reserved_ids"]:
                expected = expected.replace(value, abandoned["reserved_ids"][key])
        self.assertEqual(str(refusal), expected)
        self.assertNotEqual(validate_project(self.store), [])  # what the refusal now prevents


# --------------------------------------------------------------------------- Phase addition
class PhaseAdditionTests(RegistrationCase):
    def refused_shapes(self):
        a, b = self.phase["a"], self.phase["b"]
        return {
            "requires a cancelled Phase": ("cancel", [PhaseRelationSpec("requires_completion", a, "c")],
                                           "requires_completion predecessor"),
            "requires a plan_excluded Phase": ("exclude", [PhaseRelationSpec("requires_completion", a, "c")],
                                               "requires_completion predecessor"),
            "returns to a cancelled Phase": ("cancel", [PhaseRelationSpec("return_to", "c", a)], "return_to target"),
            "joins two existing Phases": ("cancel", [PhaseRelationSpec("requires_completion", a, b)],
                                          "requires_completion predecessor"),
            "closes a cycle through the new Phase": (None, [PhaseRelationSpec("requires_completion", a, "c"),
                                                            PhaseRelationSpec("requires_completion", "c", a)], "cycle"),
            "repeats an edge of its own": (None, [PhaseRelationSpec("planned_next", a, "c"),
                                                  PhaseRelationSpec("planned_next", a, "c")], "duplicate edge"),
        }

    def test_a_phase_addition_the_postcheck_would_refuse_writes_nothing(self) -> None:
        for index, label in enumerate(("requires a cancelled Phase", "requires a plan_excluded Phase",
                                       "returns to a cancelled Phase", "joins two existing Phases",
                                       "closes a cycle through the new Phase", "repeats an edge of its own")):
            with self.subTest(label):
                self.plan(name=f"shape-{index}")
                prepare, relations, reason = self.refused_shapes()[label]
                if prepare == "cancel":
                    rm.cancel_phase(self.store, self.phase["a"])
                elif prepare == "exclude":
                    rm.plan_exclude_phase(self.store, self.phase["a"])

                refusal = self.assertRefusedBeforeWriting(self.add("c", relations))

                self.assertEqual(refusal.code, "postcheck_failed")
                self.assertTrue(str(refusal).startswith("postcheck: "), str(refusal))
                self.assertIn(reason, str(refusal))
                # Nothing is stranded: the replanned request and every other operation proceed.
                self.assertEqual(self.add("c")().resumed, False)
                self.assertEqual(rm.hold_phase(self.store, self.phase["b"]).status, "phase_held")
                self.assertEqual(validate_project(self.store), [])
                self.assertEqual(self.dirty(), [])

    def test_a_cycle_with_existing_relations_and_a_repeated_existing_edge_write_nothing(self) -> None:
        cases = {
            "cycle": ([PhaseRelationSpec("requires_completion", "b", "a")], "cycle"),
            "repeated existing edge": ([PhaseRelationSpec("requires_completion", "a", "b")], "duplicate edge"),
        }
        for index, (label, (relations, reason)) in enumerate(cases.items()):
            with self.subTest(label):
                self.plan(relations=[("requires_completion", "a", "b")], name=f"existing-{index}")
                resolved = [PhaseRelationSpec(r.type, self.phase[r.from_ref], self.phase[r.to_ref]) for r in relations]

                refusal = self.assertRefusedBeforeWriting(self.add("c", resolved))

                self.assertIn(reason, str(refusal))

    def test_the_refusal_is_the_one_the_postcheck_gave_after_writing(self) -> None:
        """The check is the postcheck's own rule, not a rule of its own."""
        self.plan()
        rm.cancel_phase(self.store, self.phase["a"])
        request = self.add("c", [PhaseRelationSpec("requires_completion", self.phase["a"], "c"),
                                 PhaseRelationSpec("return_to", "c", self.phase["a"])])

        refusal = self.assertRefusedBeforeWriting(request)

        self.assertTheRefusalThePostcheckGave(refusal, request)

    def test_a_phase_addition_nothing_refuses_is_registered_as_before(self) -> None:
        """The boundary: an excluded Phase refuses only a relation that still waits for, or returns to, it."""
        self.plan("abde")
        a, b, d, e = (self.phase[k] for k in "abde")
        rm.hold_phase(self.store, b)
        rm.cancel_phase(self.store, a)
        rm.cancel_phase(self.store, d)
        accepted = {
            "planned_next from a cancelled Phase": [PhaseRelationSpec("planned_next", a, "c")],
            "a cancelled Phase returning to the new one": [PhaseRelationSpec("return_to", a, "c")],
            "requires a held Phase": [PhaseRelationSpec("requires_completion", b, "c")],
            "a cancelled Phase required by a cancelled one": [PhaseRelationSpec("requires_completion", a, d)],
            "requires an active Phase": [PhaseRelationSpec("requires_completion", e, "c")],
        }
        for index, (label, relations) in enumerate(accepted.items()):
            with self.subTest(label):
                refusal, recorded, executed = self.watched(self.add("c", relations, invocation_key=f"k{index}"))

                self.assertIsNone(refusal)
                self.assertEqual(recorded, ["phases", "finalize"])
                self.assertEqual(executed, ["write_file"] + ["add_relation"] * len(relations) + ["git_commit", "git_push"])
                self.assertEqual(self.head(), self.remote_head())
                self.assertEqual(MutationController(self.store).list_pending(), [])
                self.assertEqual(validate_project(self.store), [])


# --------------------------------------------------------------------------- Roadmap creation
class RoadmapCreationTests(RegistrationCase):
    def creation(self, phases=None, relations=(), name: str = "R2"):
        phases = phases or {"x": PhaseSpec("Phase X", "X"), "y": PhaseSpec("Phase Y", "Y")}
        plan = rm.RoadmapPlan(name, "背景", "達成したい状態", phases, tuple(relations))
        return lambda: rm.create_roadmap(self.store, plan)

    def test_a_creation_phase_create_would_refuse_writes_not_even_the_roadmap(self) -> None:
        cases = {
            "blank Phase name": ({"x": PhaseSpec(" ", "X")}, (), "validation_failed", "phase x: name is required"),
            "blank Phase desired state": ({"x": PhaseSpec("Phase X", "\n")}, (), "validation_failed",
                                          "phase x: desired state is required"),
            "unknown relation type": (None, [PhaseRelationSpec("follows", "x", "y")], "validation_failed",
                                      "phase relation 0: unknown type follows"),
            "self relation": (None, [PhaseRelationSpec("planned_next", "x", "x")], "validation_failed",
                              "phase relation 0: self relation"),
            "unresolvable endpoint": (None, [PhaseRelationSpec("planned_next", UNKNOWN_PHASE, "x")], "validation_failed",
                                      f"phase relation 0: endpoint unresolvable: {UNKNOWN_PHASE}"),
            "Work endpoint": (None, [PhaseRelationSpec("planned_next", UNKNOWN_WORK, "x")], "validation_failed",
                              f"phase relation 0: mixed or invalid endpoint {UNKNOWN_WORK}"),
            "cycle among its Phases": (None, [PhaseRelationSpec("requires_completion", "x", "y"),
                                              PhaseRelationSpec("requires_completion", "y", "x")], "postcheck_failed",
                                       "postcheck: requires_completion graph contains a cycle"),
            "a repeated edge": (None, [PhaseRelationSpec("planned_next", "x", "y"), PhaseRelationSpec("planned_next", "x", "y")],
                                "postcheck_failed", "postcheck: "),
        }
        for index, (label, (phases, relations, code, message)) in enumerate(cases.items()):
            with self.subTest(label):
                self.plan(name=f"payload-{index}")

                refusal = self.assertRefusedBeforeWriting(self.creation(phases, relations))

                self.assertEqual(refusal.code, code)
                self.assertTrue(str(refusal).startswith(message), str(refusal))
                self.assertEqual(len(ProjectView.load(self.store).roadmaps), 1)
                # The same name is free again: a corrected plan is a new creation, not a stranded one.
                result = self.creation()()
                self.assertFalse(result.resumed)
                self.assertEqual(MutationController(self.store).list_pending(), [])
                self.assertEqual(validate_project(self.store), [])

    def test_a_creation_that_requires_another_roadmaps_excluded_phase_writes_nothing(self) -> None:
        for how in ("cancel", "exclude"):
            with self.subTest(how):
                self.plan(name=f"other-{how}")
                a = self.phase["a"]
                (rm.cancel_phase if how == "cancel" else rm.plan_exclude_phase)(self.store, a)
                request = self.creation(relations=[PhaseRelationSpec("requires_completion", a, "x")])

                refusal = self.assertRefusedBeforeWriting(request)

                self.assertEqual(refusal.code, "postcheck_failed")
                self.assertIn(f"requires_completion predecessor {a} is", str(refusal))
                self.assertTheRefusalThePostcheckGave(refusal, request)

    def test_a_first_roadmap_with_a_cycle_writes_nothing(self) -> None:
        self.plan(roadmap=False)
        request = self.creation({"a": PhaseSpec("A", "A"), "b": PhaseSpec("B", "B")},
                                [PhaseRelationSpec("requires_completion", "a", "b"), PhaseRelationSpec("requires_completion", "b", "a")],
                                name="R1")

        self.assertRefusedBeforeWriting(request)

        self.assertFalse(self.creation({"a": PhaseSpec("A", "A"), "b": PhaseSpec("B", "B")},
                                       [PhaseRelationSpec("requires_completion", "a", "b")], name="R1")().resumed)

    def test_a_creation_nothing_refuses_is_registered_as_before(self) -> None:
        self.plan()
        rm.cancel_phase(self.store, self.phase["b"])
        request = self.creation(relations=[PhaseRelationSpec("requires_completion", self.phase["a"], "x"),
                                           PhaseRelationSpec("planned_next", self.phase["b"], "y"),
                                           PhaseRelationSpec("requires_completion", "x", "y")])

        refusal, recorded, executed = self.watched(request)

        self.assertIsNone(refusal)
        self.assertEqual(recorded, ["roadmap", "phases", "finalize"])
        self.assertEqual(executed, ["write_file"] * 3 + ["add_relation"] * 3 + ["git_commit", "git_push"])
        self.assertEqual(MutationController(self.store).list_records(), [])  # completed and cleaned up (BL-019)
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(self.dirty(), [])


# --------------------------------------------------------------------------- Phase entry
class PhaseEntryTests(RegistrationCase):
    def design(self, **kwargs) -> rm.PhaseEntryDesign:
        fields = {
            "works": {"x": rm.WorkDesign("X", "x"), "y": rm.WorkDesign("Y", "y")},
            "integration": rm.WorkDesign("Integration", "int"),
            "entry": "y",
        }
        fields.update(kwargs)
        return rm.PhaseEntryDesign(**fields)

    def test_an_expansion_requiring_an_excluded_work_writes_nothing(self) -> None:
        for how in ("plan_excluded", "cancelled"):
            with self.subTest(how):
                self.plan(name=f"excluded-{how}")
                _, w2 = self.expanded_with_excluded_work("a", how)
                request = lambda: rm.enter_phase(self.store, self.phase["b"], self.design(requires_completion=((w2, "x"),)))  # noqa: E731

                refusal = self.assertRefusedBeforeWriting(request)

                self.assertEqual(refusal.code, "postcheck_failed")
                self.assertIn(f"requires_completion predecessor {w2} is {how}", str(refusal))
                self.assertTheRefusalThePostcheckGave(refusal, request)

    def test_a_later_stage_refused_for_its_payload_writes_no_earlier_stage(self) -> None:
        cases = {
            "integration name": self.design(integration=rm.WorkDesign(" ", "int")),
            "integration desired state": self.design(integration=rm.WorkDesign("Integration", "  ")),
            "integration Related": self.design(integration=rm.WorkDesign("Integration", "int", (RelatedSpec("must_skim", "x.md"),))),
            "confirmation name": self.design(human_confirmation=rm.WorkDesign("", "confirmed")),
            "confirmation Related condition": self.design(human_confirmation=rm.WorkDesign(
                "Confirm", "confirmed", (RelatedSpec("conditional_must_read", "x.md", {"kind": "path_glob", "pattern": "if needed"}),))),
        }
        for index, (label, design) in enumerate(cases.items()):
            with self.subTest(label):
                self.plan(name=f"stage-{index}")

                refusal = self.assertRefusedBeforeWriting(lambda: rm.enter_phase(self.store, self.phase["a"], design))

                self.assertEqual(refusal.code, "validation_failed")
                self.assertEqual(ProjectView.load(self.store).phase_works(self.phase["a"]), [])
                # The Phase is not stranded: a corrected design expands it, and it runs.
                entry = self.simple_entry(self.store, self.phase["a"], confirmation=True)
                self.assertTrue(entry.expanded)
                result = st.start(self.store, entry.entry_work_id, "outer", completing_executor(self.store))
                self.assertEqual(result.status, "phase_complete")

    def test_the_first_payload_problem_is_still_reported_first(self) -> None:
        self.plan()
        design = self.design(works={"x": rm.WorkDesign("X", "x", (RelatedSpec("must_skim", "a.md"),)), "y": rm.WorkDesign("Y", "y")},
                             integration=rm.WorkDesign("", "int"))

        refusal = self.assertRefusedBeforeWriting(lambda: rm.enter_phase(self.store, self.phase["a"], design))

        self.assertEqual(str(refusal), "work x: unknown related type must_skim")

    def test_an_expansion_nothing_refuses_is_registered_as_before(self) -> None:
        self.plan()
        made = self.simple_entry(self.store, self.phase["a"])
        st.start(self.store, made.entry_work_id, "outer", completing_executor(self.store))
        design = self.design(works={"x": rm.WorkDesign("X", "x", (RelatedSpec("must_read", ".workline/project.yaml"),)),
                                    "y": rm.WorkDesign("Y", "y")},
                             human_confirmation=rm.WorkDesign("Confirm", "confirmed"),
                             requires_completion=((made.entry_work_id, "x"),), planned_next=(("x", "y"),), entry="x")

        refusal, recorded, executed = self.watched(lambda: rm.enter_phase(self.store, self.phase["b"], design))

        self.assertIsNone(refusal)
        self.assertEqual(recorded, ["works", "integration", "confirmation", "finalize"])
        self.assertEqual(executed.count("write_file"), 4)
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(validate_project(self.store), [])
        view = ProjectView.load(self.store)
        (confirmation,) = [w for w in view.phase_works(self.phase["b"]) if w.work_kind == "human_confirmation"]
        (integration,) = [w for w in view.phase_works(self.phase["b"]) if w.work_kind == "phase_integration_check"]
        self.assertEqual(confirmation.meta["confirmation_target"], integration.id)


# --------------------------------------------------------------------------- START and direct CREATE
class DerivedAndDirectCreationTests(RegistrationCase):
    def test_a_derived_work_requiring_an_excluded_work_is_not_registered(self) -> None:
        self.plan()
        w1, w2 = self.expanded_with_excluded_work("a", "plan_excluded")
        derive = st.Derive({"d": st.DerivedWork("D", "d")}, relations=(RelationSpec("requires_completion", w2, "d"),))
        works_before = set(ProjectView.load(self.store).works)
        head = self.head()

        refusal, recorded, executed = self.watched(
            lambda: st.start(self.store, w1, "single-work", scripted_executor({w1: [derive]})))

        self.assertEqual(refusal.code, "postcheck_failed")
        self.assertIn(f"requires_completion predecessor {w2} is plan_excluded", str(refusal))
        # START's own lifecycle is START's, recorded before the executor ran; no derived Work, no relation.
        self.assertEqual(executed, ["append_event", "append_event"])
        self.assertEqual([stage.split(":", 1)[1] for stage in recorded], ["lifecycle:0"])
        self.assertEqual(set(ProjectView.load(self.store).works), works_before)
        self.assertEqual(self.head(), head)
        self.assertEqual(validate_project(self.store), [])
        # START's mutation stays resumable, exactly as after any other STOP during execution.
        (pending,) = MutationController(self.store).list_pending()
        self.assertEqual(pending["invocation"]["work_id"], w1)
        result = st.start(self.store, w1, "single-work", completing_executor(self.store))
        self.assertEqual(result.status, "completed")
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(validate_project(self.store), [])

    def test_a_direct_creation_in_an_already_broken_project_writes_nothing(self) -> None:
        """The postcheck checks the whole Project, so it refuses here as before - now before the Work is written."""
        self.plan(relations=[("requires_completion", "a", "b")])
        self.cancel_behind_workline(self.phase["a"], "phase_cancelled")
        broken = validate_project(self.store)
        self.assertEqual([p.code for p in broken], ["dependency_unreplanned"])
        request = lambda: create_standalone_work(self.store, WorkSpec("Solo", "solo"))  # noqa: E731
        before = self.snapshot()

        refusal, recorded, executed = self.watched(request)

        self.assertEqual(refusal.code, "postcheck_failed")
        self.assertEqual((recorded, executed), ([], []))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(validate_project(self.store), broken)  # not repaired, and not made worse
        # Operations that check structure first still stop on it, as they always did.
        with self.assertRaises(StopError) as stopped:
            rm.hold_phase(self.store, self.phase["b"])
        self.assertEqual(stopped.exception.code, "structure_invalid")
        # Run as before, the same request writes its Work first and then gives this same refusal.
        with self.unchecked():
            old, _, executed = self.watched(request)
        self.assertEqual(executed, ["write_file"])
        self.assertEqual((type(old), old.code, str(old)), (type(refusal), refusal.code, str(refusal)))

    def test_a_direct_creation_nothing_refuses_is_registered_as_before(self) -> None:
        self.plan()
        spec = WorkSpec("Solo", "solo", related=(RelatedSpec("must_read", ".workline/project.yaml"),), derivation_detail="why")

        refusal, recorded, executed = self.watched(lambda: create_standalone_work(self.store, spec))

        self.assertIsNone(refusal)
        self.assertEqual(recorded, ["register", "finalize"])
        self.assertEqual(executed, ["write_file", "write_file", "add_relation", "git_commit", "git_push"])
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(self.dirty(), [])


# --------------------------------------------------------------------------- resume
class ResumeTests(RegistrationCase):
    ADDITION_WINDOWS = {
        "recorded": lambda: after_recording("phases"),
        "partly applied": lambda: before_applying("add_relation"),
    }

    def interrupted(self, window, call) -> dict:
        with window():
            with self.assertRaises(Interrupted):
                call()
        (pending,) = MutationController(self.store).list_pending()
        return pending

    def test_a_recorded_addition_the_project_no_longer_takes_is_refused_before_it_is_replayed(self) -> None:
        for index, (label, window) in enumerate(self.ADDITION_WINDOWS.items()):
            with self.subTest(label):
                self.plan(name=f"changed-{index}")
                a = self.phase["a"]
                request = self.add("c", [PhaseRelationSpec("requires_completion", a, "c")])
                pending = self.interrupted(window, request)
                # Nothing overlaps an addition's declared scope, so the cancel goes ahead while it waits.
                self.assertEqual(rm.cancel_phase(self.store, a).status, "phase_cancelled")
                records, files = self.record_bytes(), self.canonical()

                refusal, recorded, executed = self.watched(request)

                self.assertEqual(refusal.code, "postcheck_failed")
                self.assertIn(f"requires_completion predecessor {a} is cancelled", str(refusal))
                self.assertEqual((recorded, executed), ([], []))
                self.assertEqual(self.record_bytes(), records)  # the record is left exactly as it was
                self.assertEqual(self.canonical(), files)
                self.assertEqual(validate_project(self.store), [])
                (still,) = MutationController(self.store).list_pending()
                self.assertEqual(still["mutation_id"], pending["mutation_id"])
                self.assertIn(False, [effect["applied"] for effect in still["effects"]])

    def test_a_recorded_addition_the_project_still_takes_carries_on(self) -> None:
        for index, (label, window) in enumerate(self.ADDITION_WINDOWS.items()):
            with self.subTest(label):
                self.plan(name=f"unchanged-{index}")
                request = self.add("c", [PhaseRelationSpec("requires_completion", self.phase["a"], "c")])
                pending = self.interrupted(window, request)
                self.assertEqual(rm.hold_phase(self.store, self.phase["b"]).status, "phase_held")

                result = request()

                self.assertTrue(result.resumed)
                self.assertEqual(result.mutation_id, pending["mutation_id"])
                self.assertEqual(self.head(), self.remote_head())
                self.assertEqual(MutationController(self.store).list_pending(), [])
                self.assertEqual(validate_project(self.store), [])
                self.assertEqual(self.dirty(), [])

    def test_a_creation_whose_phases_the_project_no_longer_takes_keeps_only_its_roadmap(self) -> None:
        windows = {
            "Roadmap applied, Phases not recorded": (lambda: before_recording("phases"), "roadmap"),
            "Phases recorded": (lambda: after_recording("phases"), "phases"),
        }
        for index, (label, (window, last_stage)) in enumerate(windows.items()):
            with self.subTest(label):
                self.plan(name=f"creation-{index}")
                a = self.phase["a"]
                plan = rm.RoadmapPlan("R2", "背景", "達成したい状態", {"x": PhaseSpec("Phase X", "X")},
                                      (PhaseRelationSpec("requires_completion", a, "x"),))
                request = lambda: rm.create_roadmap(self.store, plan)  # noqa: E731
                pending = self.interrupted(window, request)
                self.assertEqual(pending["effects"][-1]["stage"], last_stage)
                self.assertEqual(rm.cancel_phase(self.store, a).status, "phase_cancelled")
                records, files = self.records(), self.canonical()

                refusal, recorded, executed = self.watched(request)

                self.assertEqual(refusal.code, "postcheck_failed")
                self.assertEqual((recorded, executed), ([], []))
                self.assertEqual(self.records(), records)
                self.assertEqual(self.canonical(), files)
                self.assertEqual(len(ProjectView.load(self.store).phases), 2)  # no Phase of R2 was written
                self.assertEqual(validate_project(self.store), [])

    def test_an_interrupted_creation_resumes_with_the_ids_its_phases_were_decided_with(self) -> None:
        self.plan()
        plan = rm.RoadmapPlan("R2", "背景", "達成したい状態", {"x": PhaseSpec("Phase X", "X"), "y": PhaseSpec("Phase Y", "Y")},
                              (PhaseRelationSpec("requires_completion", self.phase["a"], "x"), PhaseRelationSpec("planned_next", "x", "y")))
        pending = self.interrupted(lambda: before_recording("roadmap"), lambda: rm.create_roadmap(self.store, plan))
        reserved = dict(pending["reserved_ids"])
        self.assertEqual(sorted(reserved), ["phases:phase:x", "phases:phase:y", "phases:rel:0", "phases:rel:1", "roadmap"])

        result = rm.create_roadmap(self.store, plan)

        self.assertTrue(result.resumed)
        self.assertEqual(result.phase_ids, {"x": reserved["phases:phase:x"], "y": reserved["phases:phase:y"]})
        relations = {r.id for r in ProjectView.load(self.store).roadmap_relations}
        self.assertLessEqual({reserved["phases:rel:0"], reserved["phases:rel:1"]}, relations)
        self.assertEqual(validate_project(self.store), [])

    def test_a_recorded_expansion_the_project_no_longer_takes_is_refused_before_it_is_replayed(self) -> None:
        self.plan()
        solo = create_standalone_work(self.store, WorkSpec("Solo", "solo")).work_id
        design = rm.PhaseEntryDesign({"x": rm.WorkDesign("X", "x"), "y": rm.WorkDesign("Y", "y")},
                                     rm.WorkDesign("Integration", "int"), requires_completion=((solo, "x"),), entry="y")
        request = lambda: rm.enter_phase(self.store, self.phase["a"], design)  # noqa: E731
        pending = self.interrupted(lambda: after_recording("works"), request)
        # No Workline operation can exclude that Work while the expansion waits - START's declared scope
        # overlaps it - so the change is made by hand.
        with self.assertRaises(ReconcileRequired):
            st.plan_exclude_standalone_work(self.store, solo)
        self.cancel_behind_workline(solo, "plan_excluded")
        self.assertEqual(validate_project(self.store), [])
        records, files = self.record_bytes(), self.canonical()

        refusal, recorded, executed = self.watched(request)

        self.assertEqual(refusal.code, "postcheck_failed")
        self.assertIn(f"requires_completion predecessor {solo} is plan_excluded", str(refusal))
        self.assertEqual((recorded, executed), ([], []))
        self.assertEqual(self.record_bytes(), records)
        self.assertEqual(self.canonical(), files)
        (still,) = MutationController(self.store).list_pending()
        self.assertEqual(still["mutation_id"], pending["mutation_id"])

    def test_a_recorded_direct_creation_the_project_no_longer_takes_is_refused_before_it_is_applied(self) -> None:
        self.plan(relations=[("requires_completion", "a", "b")])
        request = lambda: create_standalone_work(self.store, WorkSpec("Solo", "solo"))  # noqa: E731
        pending = self.interrupted(lambda: after_recording("register"), request)
        self.cancel_behind_workline(self.phase["a"], "phase_cancelled")
        records, files = self.records(), self.canonical()

        refusal, recorded, executed = self.watched(request)

        self.assertEqual(refusal.code, "postcheck_failed")
        self.assertEqual((recorded, executed), ([], []))
        self.assertEqual(self.records(), records)
        self.assertEqual(self.canonical(), files)
        (still,) = MutationController(self.store).list_pending()
        self.assertEqual(still["mutation_id"], pending["mutation_id"])

    def test_a_different_request_still_never_takes_the_record_over(self) -> None:
        self.plan()
        request = self.add("c", [PhaseRelationSpec("requires_completion", self.phase["a"], "c")])
        self.interrupted(lambda: after_recording("phases"), request)
        rm.cancel_phase(self.store, self.phase["a"])
        records = self.record_bytes()

        with self.assertRaises(ReconcileRequired):
            rm.add_phases(self.store, self.rid, {"c": PhaseSpec("Phase C", "another")},
                          (PhaseRelationSpec("requires_completion", self.phase["a"], "c"),))

        self.assertEqual(self.record_bytes(), records)


# --------------------------------------------------------------------------- what is not projected
class ReplanRegistrationTests(RegistrationCase):
    def test_a_replan_registration_is_decided_by_its_owner_not_by_this_check(self) -> None:
        """The owner projects the whole replan before recording it; this check is not applied to one step of it."""
        self.plan()
        solo = create_standalone_work(self.store, WorkSpec("Solo", "solo")).work_id
        checked: list[tuple] = []
        real = cr.refuse_invalid_work_writes

        def note(mutation, effects=(), view=None):
            checked.append(tuple(e.payload.get("path") for e in effects if e.kind == "write_file"))
            return real(mutation, effects, view)

        with mock.patch.object(cr, "refuse_invalid_work_writes", note):
            result = st.plan_exclude_standalone_work(self.store, solo, Replan(new_works={"s2": WorkSpec("Solo 2", "s2")}))

        self.assertEqual(result.status, "plan_excluded")
        self.assertEqual(checked, [])
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(self.dirty(), [])


if __name__ == "__main__":
    unittest.main()
