"""Caller input the canonical writer and reader cannot carry is refused before anything is begun (RB10 N3).

N3(a), Human decision HD-1: a Roadmap, Phase or Work name is written as the entity's H1 and read back as one line
of it, stripped; a section is written under its ``##`` heading and read back up to the next one. A name holding a
line break (LF, CR, CRLF, or a line separator ``str.splitlines`` honours), surrounding whitespace, or a heading,
and section text that adds or splits a heading, used to be registered and then read back as another value - the
name truncated to its first line, a section cut short, a heading the reader takes for a sibling section. Such a
request is now refused before its mutation is opened, before any ID is reserved and before anything is written:
``input_unrepresentable``. A multiline section stays supported: its line ends are the reader's to fold (CRLF and a
lone CR read as LF, BL-056), and both the writer and the reader strip it.

N3(b): a value Python can hold but the recovery record cannot carry - text with a lone surrogate, a float, a tuple,
a mapping key that is not text, an empty mapping key, a sequence inside a sequence, a relation endpoint that names
nothing - used to escape as a raw ``UnicodeEncodeError`` / ``YamlishError`` / ``TypeError``: after the execution
lock was taken (and left held for the rest of the process, with a temporary file behind), after IDs were reserved,
or with a pending mutation its own record could not resume. It is refused the same way now.

The public caller surfaces enumerated (the bounded N3(b) inventory) are the legacy Roadmap creation, Phase
addition, Phase entry, direct standalone CREATE, Related maintenance and Roadmap plan exclusion (with its replan),
the Roadmap lifecycle operations whose holder description names their entity, and the replan text a START cancel
or standalone plan exclusion decides through the shared replan helper (``ops.plan_replan``). A START derivation's
text is START's own boundary and is held. Review-v1 planning keeps its own canonical-input preflight.
"""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import WorklineTestCase, git, scripted_executor
from workline import create as cr
from workline import input_validation
from workline import oplock
from workline import roadmap as rm
from workline import start as st
from workline.create import RelatedSpec, WorkSpec
from workline.errors import StopError, ValidationError
from workline.mutation import MutationController
from workline.ops import Replan
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.state import ProjectView
from workline.store import (
    PHASE_DESIRED_HEADING,
    ROADMAP_BACKGROUND_HEADING,
    ROADMAP_DESIRED_HEADING,
    ROADMAP_OUT_OF_SCOPE_HEADING,
    ROADMAP_SCOPE_HEADING,
    WORK_DESIRED_HEADING,
    ProjectStore,
)

CODE = "input_unrepresentable"
LONE = chr(0xD800)
LS, PS, NEL = "\N{LINE SEPARATOR}", "\N{PARAGRAPH SEPARATOR}", "\x85"
COND = {"kind": "path_glob", "pattern": "src/*.py"}

#: Names the canonical reader would read back as another name, each with what it reads back as.
LOSSY_NAMES = {
    "LF": ("Name\nsecond", "Name"),
    "CR": ("Name\rsecond", "Name"),
    "CRLF": ("Name\r\nsecond", "Name"),
    "trailing LF": ("Name\n", "Name"),
    "U+2028": (f"Name{LS}second", "Name"),
    "U+2029": (f"Name{PS}second", "Name"),
    "NEL": (f"Name{NEL}second", "Name"),
    "form feed": ("Name\x0csecond", "Name"),
    "file separator": ("Name\x1csecond", "Name"),
    "trailing space": ("Name ", "Name"),
    "leading space": (" Name", "Name"),
    "ideographic space": ("　名前", "名前"),
    "heading injected": ("Name\n## 注入\nINJECTED", "Name"),
}

#: Names that are one identity the reader returns exactly.
VALID_NAMES = ("日本語の名前", "C# 入門 — 改訂版 🚀", "a\tb", "# hashed", "x ## not a heading", "Ω≈ç√")


def workline_state(store: ProjectStore) -> dict[str, bytes | None]:
    """Every entry under ``.workline`` (runtime included, the execution lock's own area aside), byte for byte."""
    found: dict[str, bytes | None] = {}
    for path in sorted((store.root / ".workline").rglob("*")):
        relative = path.relative_to(store.root).as_posix()
        if "/runtime/locks" in relative:
            continue
        if relative in (".workline/runtime", ".workline/runtime/tmp") and path.is_dir():
            continue
        found[relative] = path.read_bytes() if path.is_file() else None
    return found


class InputCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def base(self) -> None:
        """Roadmap R (Phase A entered: W1 + integration I1; Phase B not entered) and standalone Work S."""
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A done"), "b": ("Phase B", "B done")})
        self.rid, self.pa, self.pb = roadmap.roadmap_id, roadmap.phase_ids["a"], roadmap.phase_ids["b"]
        entry = self.simple_entry(self.store, self.pa)
        self.w1, self.i1 = entry.work_ids["w1"], entry.integration_id
        self.solo = cr.create_standalone_work(self.store, WorkSpec("Solo", "solo done")).work_id

    def assertRefusedBeforeAnything(self, call, code: str = CODE) -> StopError:
        """Refused with ``code``; nothing under .workline changed, no record, no temporary file, the lock released."""
        before = workline_state(self.store)
        head = git(self.store.root, "rev-parse", "HEAD")
        with self.assertRaises(StopError) as refused:
            call()
        self.assertEqual(refused.exception.code, code, refused.exception.message)
        self.assertEqual(workline_state(self.store), before, "no mutation record, reservation, temporary file or write")
        self.assertEqual(git(self.store.root, "rev-parse", "HEAD"), head, "no commit")
        self.assertIsNone(oplock.held_lock(self.store), "the execution lock is not left held")
        with oplock.project_operation(self.store, "a later operation"):
            pass
        return refused.exception

    def names(self) -> dict[str, str]:
        view = ProjectView.load(self.store)
        return {e.id: e.name for e in [*view.roadmaps.values(), *view.phases.values(), *view.works.values()]}


# --------------------------------------------------------------------------- N3(a): single-line identity text

class NameTests(InputCase):
    """Every legacy registration surface refuses a name the reader would read back as another one."""

    def surfaces(self, name: str) -> dict:
        self_ = self
        return {
            "Roadmap name": lambda: rm.create_roadmap(self_.store, rm.RoadmapPlan(name, "BG", "DS", {"x": PhaseSpec("PX", "X")})),
            "Phase name (creation)": lambda: rm.create_roadmap(self_.store, rm.RoadmapPlan("R2", "BG", "DS", {"x": PhaseSpec(name, "X")})),
            "Phase name (addition)": lambda: rm.add_phases(self_.store, self_.rid, {"n": PhaseSpec(name, "N")}),
            "Work name (entry)": lambda: rm.enter_phase(self_.store, self_.pb, rm.PhaseEntryDesign(
                {"w": rm.WorkDesign(name, "W")}, rm.WorkDesign("Int", "I"))),
            "integration name": lambda: rm.enter_phase(self_.store, self_.pb, rm.PhaseEntryDesign(
                {"w": rm.WorkDesign("W", "W")}, rm.WorkDesign(name, "I"))),
            "confirmation name": lambda: rm.enter_phase(self_.store, self_.pb, rm.PhaseEntryDesign(
                {"w": rm.WorkDesign("W", "W")}, rm.WorkDesign("Int", "I"), rm.WorkDesign(name, "C"))),
            "standalone Work name": lambda: cr.create_standalone_work(self_.store, WorkSpec(name, "S")),
        }

    def test_a_name_read_back_as_another_name_is_refused_on_every_surface(self) -> None:
        self.base()
        for label, (name, read) in LOSSY_NAMES.items():
            for surface, call in self.surfaces(name).items():
                with self.subTest(name=label, surface=surface):
                    error = self.assertRefusedBeforeAnything(call)
                    self.assertIn("cannot be stored and read back as the same value", error.message)
                    if "\n## " not in name:
                        self.assertIn(f"reads back as the name {read!r}", error.message)

    def test_a_replan_new_work_name_is_refused_before_any_id_is_reserved(self) -> None:
        self.base()
        for label, (name, _) in LOSSY_NAMES.items():
            with self.subTest(name=label):
                replan = Replan(new_works={"n": WorkSpec(name, "n", phase_id=self.pa, roadmap_id=self.rid)})
                with self.assertRaises(ValidationError) as refused:
                    rm.plan_exclude_phase(self.store, self.pb, replan)
                self.assertEqual(refused.exception.code, CODE)
                self.assertEqual(MutationController(self.store).list_pending(), [])
                for record in MutationController(self.store).list_records():
                    if record["status"] == "abandoned":
                        self.assertEqual(record["reserved_ids"], {}, "abandoned before any reservation")
                        self.assertEqual(record["effects"], [])
                self.assertEqual(ProjectView.load(self.store).phase_lifecycle(self.pb), "active")

    def test_valid_unicode_identities_are_registered_and_read_back_exactly(self) -> None:
        self.base()
        for index, name in enumerate(VALID_NAMES):
            with self.subTest(name=name):
                work_id = cr.create_standalone_work(self.store, WorkSpec(name, f"{name} done")).work_id
                self.assertEqual(self.names()[work_id], name)
        created = rm.create_roadmap(self.store, rm.RoadmapPlan("ロードマップ ✓", "背景", "状態", {"x": PhaseSpec("フェーズ #1", "X")}))
        self.assertEqual(self.names()[created.roadmap_id], "ロードマップ ✓")
        self.assertEqual(self.names()[created.phase_ids["x"]], "フェーズ #1")

    def test_a_blank_name_keeps_its_own_refusal(self) -> None:
        """A blank name is the owner's to refuse, with the report it always had."""
        self.base()
        with self.assertRaises(ValidationError) as refused:
            cr.create_standalone_work(self.store, WorkSpec("   ", "s"))
        self.assertEqual((refused.exception.code, refused.exception.message), ("validation_failed", "work work: name is required"))
        with self.assertRaises(ValidationError) as roadmap:
            rm.create_roadmap(self.store, rm.RoadmapPlan(" ", "BG", "DS", {"x": PhaseSpec("PX", "X")}))
        self.assertEqual(roadmap.exception.message, "Roadmap needs name, background and desired state")


# --------------------------------------------------------------------------- N3(a): Markdown sections

class SectionTests(InputCase):
    def test_section_text_that_adds_or_splits_a_heading_is_refused(self) -> None:
        self.base()
        cases = {
            "background repeating its own heading": rm.RoadmapPlan("R2", f"BG\n## {ROADMAP_BACKGROUND_HEADING}\nx", "DS", {"x": PhaseSpec("P", "X")}),
            "background injecting the desired-state heading": rm.RoadmapPlan("R2", f"BG\n## {ROADMAP_DESIRED_HEADING}\nINJ", "DS", {"x": PhaseSpec("P", "X")}),
            "desired state injecting a new section": rm.RoadmapPlan("R2", "BG", "DS\n## 注入\ny", {"x": PhaseSpec("P", "X")}),
            "scope injecting out-of-scope": rm.RoadmapPlan("R2", "BG", "DS", {"x": PhaseSpec("P", "X")}, scope=f"s\n## {ROADMAP_OUT_OF_SCOPE_HEADING}\nz"),
            "a heading through CRLF": rm.RoadmapPlan("R2", "BG\r\n## 注入\r\nx", "DS", {"x": PhaseSpec("P", "X")}),
            "a heading through a lone CR": rm.RoadmapPlan("R2", "BG\r## 注入", "DS", {"x": PhaseSpec("P", "X")}),
            "section text starting with a heading": rm.RoadmapPlan("R2", "## 注入\nx", "DS", {"x": PhaseSpec("P", "X")}),
            "a Phase desired state repeating its heading": rm.RoadmapPlan("R2", "BG", "DS", {"x": PhaseSpec("P", f"a\n## {PHASE_DESIRED_HEADING}\nb")}),
        }
        for label, plan in cases.items():
            with self.subTest(label):
                error = self.assertRefusedBeforeAnything(lambda plan=plan: rm.create_roadmap(self.store, plan))
                self.assertIn("section heading", error.message)
        for label, call in {
            "entry Work desired state": lambda: rm.enter_phase(self.store, self.pb, rm.PhaseEntryDesign(
                {"w": rm.WorkDesign("W", f"a\n## {WORK_DESIRED_HEADING}\nb")}, rm.WorkDesign("Int", "I"))),
            "integration desired state": lambda: rm.enter_phase(self.store, self.pb, rm.PhaseEntryDesign(
                {"w": rm.WorkDesign("W", "W")}, rm.WorkDesign("Int", "i\n## 他\nj"))),
            "standalone Work desired state": lambda: cr.create_standalone_work(self.store, WorkSpec("S2", "s\n## 他\nt")),
            "added Phase desired state": lambda: rm.add_phases(self.store, self.rid, {"n": PhaseSpec("PN", "n\n## 他")}),
        }.items():
            with self.subTest(label):
                self.assertRefusedBeforeAnything(call)

    def test_multiline_sections_round_trip(self) -> None:
        """Multiline text stays supported: lists, blank lines, an H1 or deeper heading line, and the reader's line ends."""
        self.base()
        background = "line one\n\n- item a\n- item b\n\n# not a section\n### sub heading\n```\ncode\n```"
        plan = rm.RoadmapPlan(
            "Multiline", background, "state\r\nwith CRLF", {"x": PhaseSpec("P", "a\rb")},
            scope="  scope text  \n", out_of_scope=f"other{LS}text",
        )
        created = rm.create_roadmap(self.store, plan)
        view = ProjectView.load(self.store)
        roadmap = view.roadmaps[created.roadmap_id]
        self.assertEqual(roadmap.section(ROADMAP_BACKGROUND_HEADING), background)
        self.assertEqual(roadmap.section(ROADMAP_DESIRED_HEADING), "state\nwith CRLF")
        self.assertEqual(roadmap.section(ROADMAP_SCOPE_HEADING), "scope text")
        self.assertEqual(roadmap.section(ROADMAP_OUT_OF_SCOPE_HEADING), f"other{LS}text")
        self.assertEqual(view.phases[created.phase_ids["x"]].section(PHASE_DESIRED_HEADING), "a\nb")
        work_id = cr.create_standalone_work(self.store, WorkSpec("Multi", "a\n\nb\n- c", derivation_detail="d\n## any\n# text")).work_id
        self.assertEqual(ProjectView.load(self.store).works[work_id].section(WORK_DESIRED_HEADING), "a\n\nb\n- c")

    def test_the_proof_is_the_live_writer_and_reader(self) -> None:
        """Each refusal is what the canonical reader really reads back: render, read back, compare."""
        input_validation.require_entity_text("work", "W", [(WORK_DESIRED_HEADING, "a\r\nb")], "w")
        with self.assertRaises(ValidationError):
            input_validation.require_entity_text("work", "W\x1e", [(WORK_DESIRED_HEADING, "a")], "w")
        with self.assertRaises(ValidationError):
            input_validation.require_entity_text("roadmap", "R", [(ROADMAP_BACKGROUND_HEADING, "x\n## y"), (ROADMAP_DESIRED_HEADING, "d")], "r")


# --------------------------------------------------------------------------- N3(b): what the record cannot carry

class DurableTests(InputCase):
    """The bounded N3(b) inventory: every malformed value a legacy surface admitted, refused before anything."""

    def test_each_inventory_case_is_refused_before_anything(self) -> None:
        self.base()
        float_c, tuple_c = {**COND, "w": 1.5}, {**COND, "t": ("a", "b")}

        def entry(**kw):
            return rm.PhaseEntryDesign(
                kw.pop("works", {"w": rm.WorkDesign("W", "W", kw.pop("related", ()))}), rm.WorkDesign("Int", "I"), **kw
            )

        cases = {
            # lone surrogates: each one used to fail in a UTF-8 write
            "Roadmap name, lone surrogate (lock leaked)": lambda: rm.create_roadmap(self.store, rm.RoadmapPlan(f"R{LONE}", "B", "D", {"x": PhaseSpec("P", "X")})),
            "Roadmap background, lone surrogate": lambda: rm.create_roadmap(self.store, rm.RoadmapPlan("R", f"B{LONE}", "D", {"x": PhaseSpec("P", "X")})),
            "Roadmap scope, lone surrogate": lambda: rm.create_roadmap(self.store, rm.RoadmapPlan("R", "B", "D", {"x": PhaseSpec("P", "X")}, scope=LONE)),
            "Phase key, lone surrogate": lambda: rm.create_roadmap(self.store, rm.RoadmapPlan("R", "B", "D", {f"k{LONE}": PhaseSpec("P", "X")})),
            "Phase relation endpoint, lone surrogate": lambda: rm.create_roadmap(self.store, rm.RoadmapPlan(
                "R", "B", "D", {"x": PhaseSpec("P", "X")}, (PhaseRelationSpec("planned_next", "x", f"y{LONE}"),))),
            "Roadmap ID (lock leaked)": lambda: rm.add_phases(self.store, self.rid + LONE, {"n": PhaseSpec("PN", "N")}),
            "Phase addition key label": lambda: rm.add_phases(self.store, self.rid, {"n": PhaseSpec("PN", "N")}, invocation_key=LONE),
            "Phase ID (lock leaked)": lambda: rm.enter_phase(self.store, self.pb + LONE, entry()),
            "Work key, lone surrogate": lambda: rm.enter_phase(self.store, self.pb, entry(works={f"k{LONE}": rm.WorkDesign("W", "W")})),
            "Related target, lone surrogate": lambda: rm.enter_phase(self.store, self.pb, entry(related=(RelatedSpec("must_read", f"a{LONE}"),))),
            "condition, lone surrogate": lambda: rm.enter_phase(self.store, self.pb, entry(related=(RelatedSpec("conditional_must_read", "x", {**COND, "n": LONE}),))),
            "requires_completion endpoint, lone surrogate": lambda: rm.enter_phase(self.store, self.pb, entry(
                works={"a": rm.WorkDesign("A", "a"), "b": rm.WorkDesign("B", "b")}, requires_completion=(("a", f"b{LONE}"),), entry="a")),
            "standalone name (lock leaked)": lambda: cr.create_standalone_work(self.store, WorkSpec(f"S{LONE}", "s")),
            "standalone derivation detail": lambda: cr.create_standalone_work(self.store, WorkSpec("S", "s", derivation_detail=LONE)),
            "standalone label": lambda: cr.create_standalone_work(self.store, WorkSpec("S", "s"), invocation_key=LONE),
            "maintained Work ID (lock leaked)": lambda: rm.maintain_work_related(self.store, self.w1 + LONE, add=(RelatedSpec("must_read", "d"),)),
            "maintained Related target": lambda: rm.maintain_work_related(self.store, self.w1, add=(RelatedSpec("must_read", LONE),)),
            "maintenance label": lambda: rm.maintain_work_related(self.store, self.w1, add=(RelatedSpec("must_read", "d"),), invocation_key=LONE),
            "plan exclusion removal ID": lambda: rm.plan_exclude_phase(self.store, self.pb, Replan(remove_relation_ids=(f"rel_{LONE}",))),
            "plan exclusion new Work name": lambda: rm.plan_exclude_phase(self.store, self.pb, Replan(new_works={"n": WorkSpec(f"N{LONE}", "n", phase_id=self.pa, roadmap_id=self.rid)})),
            "lifecycle entity ID (lock leaked)": lambda: rm.hold_phase(self.store, self.pa + LONE),
            "achievement Roadmap ID (lock leaked)": lambda: rm.evaluate_achievement(self.store, self.rid + LONE, "achieved"),
            # shapes the recovery record cannot carry
            "condition float": lambda: rm.enter_phase(self.store, self.pb, entry(related=(RelatedSpec("conditional_must_read", "x", float_c),))),
            "condition tuple (stranded a pending mutation)": lambda: rm.enter_phase(self.store, self.pb, entry(related=(RelatedSpec("conditional_must_read", "x", tuple_c),))),
            "condition non-text key": lambda: rm.enter_phase(self.store, self.pb, entry(related=(RelatedSpec("conditional_must_read", "x", {**COND, 1: "x"}),))),
            "condition empty key": lambda: rm.enter_phase(self.store, self.pb, entry(related=(RelatedSpec("conditional_must_read", "x", {**COND, "": "x"}),))),
            "condition nested sequence": lambda: rm.enter_phase(self.store, self.pb, entry(related=(RelatedSpec("conditional_must_read", "x", {**COND, "n": [["a"]]}),))),
            "standalone condition tuple (stranded)": lambda: cr.create_standalone_work(self.store, WorkSpec("S", "s", related=(RelatedSpec("conditional_must_read", "x", tuple_c),))),
            "maintained condition tuple (stranded)": lambda: rm.maintain_work_related(self.store, self.w1, add=(RelatedSpec("conditional_must_read", "x", tuple_c),)),
            "maintained condition mixed keys": lambda: rm.maintain_work_related(self.store, self.w1, add=(RelatedSpec("conditional_must_read", "x", {**COND, 1: "x"}),)),
            "replan condition tuple (stranded after the event)": lambda: rm.plan_exclude_phase(self.store, self.pb, Replan(new_works={"n": WorkSpec(
                "N", "n", phase_id=self.pa, roadmap_id=self.rid, related=(RelatedSpec("conditional_must_read", "x", tuple_c),))})),
            # endpoints and pairs that name nothing
            "Phase relation endpoint not text (stranded)": lambda: rm.create_roadmap(self.store, rm.RoadmapPlan(
                "R", "B", "D", {"x": PhaseSpec("P", "X"), "y": PhaseSpec("Q", "Y")}, (PhaseRelationSpec("planned_next", "x", 1),))),
            "planned_next endpoint not text (stranded)": lambda: rm.enter_phase(self.store, self.pb, entry(
                works={"a": rm.WorkDesign("A", "a"), "b": rm.WorkDesign("B", "b")}, planned_next=(("a", 2),), entry="a")),
            "planned_next triple": lambda: rm.enter_phase(self.store, self.pb, entry(
                works={"a": rm.WorkDesign("A", "a"), "b": rm.WorkDesign("B", "b")}, planned_next=(("a", "b", "c"),), entry="a")),
            "unhashable entry": lambda: rm.enter_phase(self.store, self.pb, entry(entry=["w"])),
            # values that are not text where text is read
            "Roadmap name not text": lambda: rm.create_roadmap(self.store, rm.RoadmapPlan(7, "B", "D", {"x": PhaseSpec("P", "X")})),
            "Roadmap name None": lambda: rm.create_roadmap(self.store, rm.RoadmapPlan(None, "B", "D", {"x": PhaseSpec("P", "X")})),
            "background not text": lambda: rm.create_roadmap(self.store, rm.RoadmapPlan("R", 5, "D", {"x": PhaseSpec("P", "X")})),
            "standalone name not text (stranded)": lambda: cr.create_standalone_work(self.store, WorkSpec(9, "s")),
            "standalone derivation detail not text": lambda: cr.create_standalone_work(self.store, WorkSpec("S", "s", derivation_detail=3)),
            "Related target not text (stranded)": lambda: cr.create_standalone_work(self.store, WorkSpec("S", "s", related=(RelatedSpec("must_read", 4),))),
            "integration missing": lambda: rm.enter_phase(self.store, self.pb, rm.PhaseEntryDesign({"w": rm.WorkDesign("W", "W")}, None)),
        }
        for label, call in cases.items():
            with self.subTest(label):
                error = self.assertRefusedBeforeAnything(call)
                self.assertIsInstance(error, ValidationError)

    def test_values_the_record_carries_stay_accepted(self) -> None:
        """What round-trips is not refused: extra condition fields, an empty key inside a sequence item, int keys."""
        self.base()
        extras = {**COND, "note": "t", "count": 3, "flags": [True, None], "meta": {"b": "x"}, "items": [{"": "kept"}]}
        entry = rm.enter_phase(self.store, self.pb, rm.PhaseEntryDesign(
            {1: rm.WorkDesign("W", "W", (RelatedSpec("conditional_must_read", "x", extras),))}, rm.WorkDesign("Int", "I")))
        (related,) = [r for r in ProjectView.load(self.store).related if r.from_id == entry.work_ids[1]]
        self.assertEqual(related.extra["condition"], extras)
        self.assertEqual(rm.add_phases(self.store, self.rid, {"n": PhaseSpec("PN", "N")}, invocation_key=5).phase_ids.keys(), {"n"})
        target = f"docs/a{LS}b.md\nsecond"
        work_id = cr.create_standalone_work(self.store, WorkSpec("S", "s", related=(RelatedSpec("must_read", target),))).work_id
        self.assertIn((work_id, target), {(r.from_id, r.to) for r in ProjectView.load(self.store).related})

    def test_the_durable_proof_is_the_record_format(self) -> None:
        for value in ({"a": 1}, {"a": [{"": 1}]}, {"a": True, "b": None}, {"t": "\x00\x85"}, {"n": -12345678901234567890}):
            input_validation.require_durable(value, "v")
        for value in ({"a": (1,)}, {"a": 1.0}, {1: "a"}, {"": 1}, {"a": [[1]]}, {"a": LONE}, {"a": {1, 2}}, {True: 1}):
            with self.subTest(value=repr(value)), self.assertRaises(ValidationError) as refused:
                input_validation.require_durable(value, "v")
            self.assertEqual(refused.exception.code, CODE)


# --------------------------------------------------------------------------- the boundary and resume

class BoundaryTests(InputCase):
    def test_refused_before_the_mutation_is_opened_and_before_any_reservation(self) -> None:
        self.base()
        opened: list[str] = []
        real_open, real_reserve = MutationController.open, cr.Mutation.reserve_id

        def watch_open(controller, owner, invocation, scope):
            opened.append(owner)
            return real_open(controller, owner, invocation, scope)

        def watch_reserve(mutation, key, kind):
            opened.append(f"reserve {key}")
            return real_reserve(mutation, key, kind)

        with mock.patch.object(MutationController, "open", watch_open), mock.patch.object(cr.Mutation, "reserve_id", watch_reserve):
            for call in (
                lambda: rm.create_roadmap(self.store, rm.RoadmapPlan("R\nX", "B", "D", {"x": PhaseSpec("P", "X")})),
                lambda: rm.add_phases(self.store, self.rid, {"n": PhaseSpec("P\nN", "N")}),
                lambda: rm.enter_phase(self.store, self.pb, rm.PhaseEntryDesign({"w": rm.WorkDesign("W\nX", "W")}, rm.WorkDesign("I", "I"))),
                lambda: cr.create_standalone_work(self.store, WorkSpec("S\nX", "s")),
            ):
                with self.assertRaises(ValidationError):
                    call()
        self.assertEqual(opened, [], "no mutation opened and no ID reserved")

    def test_review_v1_keeps_its_own_preflight(self) -> None:
        """The legacy validator never runs on the review-v1 path (its vocabulary stays ``review_candidate_unrepresentable``)."""
        with mock.patch.object(input_validation, "require_roadmap_plan", side_effect=AssertionError("legacy ran")), \
                mock.patch.object(input_validation, "require_phase_entry_design", side_effect=AssertionError("legacy ran")):
            with self.assertRaises(StopError) as refused:
                rm.create_roadmap(self.store, rm.RoadmapPlan(f"R{LONE}", "B", "D", {"x": PhaseSpec("P", "X")}), review=object())
        self.assertNotEqual(refused.exception.code, CODE)

    def test_an_unfinished_mutation_of_the_same_request_is_carried_on_under_its_record(self) -> None:
        """A mutation recorded before this boundary existed, with a name the boundary now refuses, still finishes.

        Its record is the authority for what it already applied; refusing the retry would leave it unfinished.
        Simulated by recording it with the semantic check switched off, then interrupting before its Git stage.
        """
        self.base()

        class Interrupted(RuntimeError):
            pass

        spec = WorkSpec("Legacy\nname", "s")
        real = cr.gitops.finalize

        def interrupt(*args, **kwargs):
            raise Interrupted()

        with mock.patch.object(input_validation, "require_work_text", lambda *a, **k: None), \
                mock.patch.object(cr.gitops, "finalize", interrupt):
            with self.assertRaises(Interrupted):
                cr.create_standalone_work(self.store, spec)
        (pending,) = MutationController(self.store).list_pending()
        self.assertTrue(pending["effects"])
        with self.assertRaises(ValidationError):
            cr.create_standalone_work(self.store, WorkSpec("Fresh\nname", "s"))  # a new request is still refused
        result = cr.create_standalone_work(self.store, spec)
        self.assertEqual((result.resumed, result.mutation_id), (True, pending["mutation_id"]))
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertIs(real, cr.gitops.finalize)

    def test_a_stranded_record_of_a_shape_it_cannot_carry_is_refused_not_crashed(self) -> None:
        """The baseline left a pending mutation it could never resume (a tuple in a condition); a retry now refuses."""
        self.base()
        design = rm.PhaseEntryDesign(
            {"w": rm.WorkDesign("W", "W", (RelatedSpec("conditional_must_read", "x", {**COND, "t": ("a",)}),))},
            rm.WorkDesign("Int", "I"),
        )
        with mock.patch.object(input_validation, "require_phase_entry_design", lambda design: None), \
                mock.patch.object(input_validation, "require_durable", lambda value, described: None):
            with self.assertRaises(Exception) as crashed:
                rm.enter_phase(self.store, self.pb, design)
        self.assertNotIsInstance(crashed.exception, StopError, "the baseline crash")
        (stranded,) = MutationController(self.store).list_pending()
        self.assertEqual(stranded["effects"], [])
        record = (self.store.mutations / f"{stranded['mutation_id']}.yaml").read_bytes()
        with self.assertRaises(ValidationError) as refused:
            rm.enter_phase(self.store, self.pb, design)
        self.assertEqual(refused.exception.code, CODE)
        self.assertEqual((self.store.mutations / f"{stranded['mutation_id']}.yaml").read_bytes(), record, "left untouched")


# --------------------------------------------------------------------------- the replan text START decides

class StartDecisionTests(InputCase):
    """A replan START decides - a cancel's, a standalone plan exclusion's - is judged where every replan is decided.

    ``ops.plan_replan`` judges the new Works' text before any ID is reserved, whichever owner decided the replan.
    A START derivation's text is START's own boundary (``start.py``), held for a later candidate.
    """

    def test_a_cancel_replan_refuses_before_its_events(self) -> None:
        self.base()
        rel = next(r.id for r in ProjectView.load(self.store).roadmap_relations if r.from_id == self.w1 and r.to == self.i1)
        replan = Replan(remove_relation_ids=(rel,), new_works={"n": WorkSpec("N\nW", "n", phase_id=self.pa, roadmap_id=self.rid)})
        with self.assertRaises(ValidationError) as cancel:
            st.start(self.store, self.w1, "single-work", scripted_executor({self.w1: [st.Cancel(replan, "r")]}))
        self.assertEqual(cancel.exception.code, CODE)
        self.assertNotEqual(ProjectView.load(self.store).work_state(self.w1).state, "cancelled")
        self.assertIn(rel, {r.id for r in ProjectView.load(self.store).roadmap_relations}, "nothing of the replan applied")

    def test_a_standalone_plan_exclusion_refuses_before_its_event(self) -> None:
        self.base()
        before = workline_state(self.store)
        with self.assertRaises(ValidationError) as excluded:
            st.plan_exclude_standalone_work(self.store, self.solo, Replan(new_works={"n": WorkSpec("N\nW", "n")}))
        self.assertEqual(excluded.exception.code, CODE)
        self.assertEqual(ProjectView.load(self.store).work_state(self.solo).state, "unstarted")
        self.assertEqual({k: v for k, v in workline_state(self.store).items() if "/runtime/" not in k},
                         {k: v for k, v in before.items() if "/runtime/" not in k})


if __name__ == "__main__":
    unittest.main()
