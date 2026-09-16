"""A replan resume is not refused by display numbering a foreign Work changed (BL-045).

A cancel's replan and a plan exclusion's replan both prove their recorded
registration stage by rebuilding it and comparing it to what the record holds.
The rebuild took the display each new Work is written with from the Works the
Project holds now, less the mutation's own - so a Work registered by anything
else while the mutation was pending renumbered every rebuilt display, a recorded
stage nothing had touched no longer matched, and the resume was ``reconcile
required``. The same foreign Work arriving before the stage was recorded changed
nothing at all: the same interruption on the same plan finished or refused
according only to which window the foreign Work landed in.

A display is how a Project shows a Work, not part of what the Work is: there is
no uniqueness rule for it, nothing is looked up by it, a duplicate display and a
gap leave ``validate_project`` with no problems, and a projection stands a new
Work up under ``W-??``. The rebuilt registration now takes each display from the
stage that recorded it, so the proof rests on what a registration is - the
effect kinds, the paths, the stable Work IDs, the rest of each Work's
frontmatter and its whole body, the derivation details, the reserved relation
and derivation IDs, the relation payloads and the order they are recorded in -
and a resume writes the display its own stage recorded, never a newly allocated
one. Only a display the Project would refuse to hold at all leaves a stage
unproven.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable
import unittest

from helpers import WorklineTestCase, git
from test_decision_branch_binding import after_recording
from test_recorded_commit_resume import Interrupted, after_applying
from workline import gitcmd
from workline import ops
from workline import roadmap as rm
from workline import start as st
from workline import yamlish
from workline.create import RelatedSpec, RelationSpec, WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, StopError
from workline.ids import new_id
from workline.mutation import MutationController
from workline.ops import Replan
from workline.state import ProjectView
from workline.store import WORK_DESIRED_HEADING, ProjectStore, render_body, render_entity
from workline.validate import validate_project

#: Every foreign Work this file registers shows this display, which no allocation would produce here.
FOREIGN_DISPLAY = "W-90"


@dataclass(frozen=True)
class Scenario:
    """One replan of one owner: how to run it again, the stage its registration is recorded under, what it registers."""

    owner: str
    target: str
    stage: str
    keys: tuple[str, ...]
    names: tuple[str, ...]
    subject: str
    call: Callable[[], object]


class DisplayNumberingCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.rid = self.pa = None
        #: Foreign Work files left untracked here, which are no operation's to stage or commit.
        self.untracked: list[str] = []

    # ------------------------------------------------------------------ reading
    def relation(self, rel_type: str, a: str, b: str) -> str:
        (found,) = [r.id for r in ProjectView.load(self.store).roadmap_relations
                    if (r.type, r.from_id, r.to) == (rel_type, a, b)]
        return found

    def displays(self) -> dict[str, str]:
        """Every Work the Project holds, as name -> display."""
        return {w.name: w.display for w in ProjectView.load(self.store).works.values()}

    def display_of(self, name: str) -> str:
        (found,) = [w.display for w in ProjectView.load(self.store).works.values() if w.name == name]
        return found

    def edges(self) -> list[tuple[str, str, str]]:
        return sorted((r.type, r.from_id, r.to) for r in ProjectView.load(self.store).roadmap_relations)

    def subjects(self) -> list[str]:
        return git(self.store.root, "log", "--format=%s").splitlines()

    def head(self) -> str:
        return git(self.store.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote_path(), "rev-parse", "main").strip()

    def dirty(self) -> list[str]:
        return [line[3:] for line in git(self.store.root, "status", "--porcelain", "--untracked-files=all").splitlines()
                if ".workline/runtime/" not in line]

    def snapshot(self) -> dict:
        root = self.store.root
        return {
            "records": {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))},
            "files": {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
                      if p.is_file() and ".git" not in p.relative_to(root).parts
                      and "runtime" not in p.relative_to(root).parts},
            "head": self.head(),
            "on": git(root, "symbolic-ref", "--quiet", "HEAD", check=False).strip(),
            "remote": self.remote_head(),
            "dirty": self.dirty(),
        }

    def registered(self, pending: dict, scenario: Scenario) -> dict[str, str]:
        """The stable Work ID the record reserved for each new Work."""
        return {key: pending["reserved_ids"][f"{scenario.stage}:work:{key}"] for key in scenario.keys}

    def recorded_displays(self, pending: dict, scenario: Scenario) -> dict[str, str]:
        """The display the recorded registration stage writes each new Work with."""
        found = {}
        for key, work_id in self.registered(pending, scenario).items():
            (content,) = [e["payload"]["content"] for e in pending["effects"]
                          if e["stage"] == scenario.stage and e["kind"] == "write_file"
                          and e["payload"]["path"] == ProjectStore.entity_rel_path("work", work_id)]
            found[key] = yamlish.load_frontmatter(content)[0]["display"]
        return found

    # ------------------------------------------------------------------ writing
    def foreign_work(self, name: str = "Foreign", *, display: str = FOREIGN_DISPLAY, in_phase: bool = False,
                     commit: bool = False, work_id: str | None = None) -> tuple[str, str]:
        """A Work this operation did not register, as its own entity file on disk.

        No Workline owner can register one while a replan's mutation is pending:
        every operation that could claims one of the same ledgers, so opening it
        is ``reconcile required`` on the write scope. What a resume actually
        meets is the file - a Work another clone registered, arriving by a pull
        or a merge, or one a human wrote. ``commit`` is whether it was committed
        (as a pull brings it) or is still untracked here.
        """
        work_id = work_id or new_id("work")
        meta: dict[str, object] = {"id": work_id, "display": display, "type": "work"}
        if in_phase:
            meta["phase_id"] = self.pa
            meta["origin"] = {"type": "roadmap", "roadmap_id": self.rid, "phase_id": self.pa}
        else:
            meta["origin"] = {"type": "standalone"}
        rel_path = ProjectStore.entity_rel_path("work", work_id)
        file = self.store.root / rel_path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(render_entity(meta, render_body(name, [(WORK_DESIRED_HEADING, "foreign")])),
                        encoding="utf-8", newline="\n")
        if commit:
            git(self.store.root, "add", "--", rel_path)
            git(self.store.root, "commit", "-q", "-m", f"chore: {name}", "--", rel_path)
        else:
            self.untracked.append(rel_path)
        return work_id, rel_path

    def edit_record(self, pending: dict, change) -> None:
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8")

    @staticmethod
    def stage_effects(record: dict, stage: str) -> list[dict]:
        return [e for e in record["effects"] if e["stage"] == stage]

    @staticmethod
    def work_write(record: dict, stage: str, work_id: str) -> dict:
        (effect,) = [e for e in record["effects"] if e["stage"] == stage and e["kind"] == "write_file"
                     and e["payload"]["path"] == ProjectStore.entity_rel_path("work", work_id)]
        return effect

    @staticmethod
    def with_display(content: str, display: object) -> str:
        """``content`` with its frontmatter display replaced, as a record holding another display would read."""
        meta, body = yamlish.load_frontmatter(content)
        if display is None:
            meta.pop("display", None)
        else:
            meta["display"] = display
        return render_entity(meta, body)

    # ---------------------------------------------------------------- scenarios
    def phase(self, **entry):
        roadmap = self.simple_roadmap(self.store)
        self.rid, self.pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        return self.simple_entry(self.store, self.pa, **entry)

    def cancel_replacement(self, keys: dict[str, str] | None = None) -> Scenario:
        """START cancels W1, and the decision's replan registers the Works replacing it (BL-030)."""
        keys = keys or {"r": "R"}
        (self.store.root / "doc.md").write_text("doc\n", encoding="utf-8", newline="\n")
        git(self.store.root, "add", "--", "doc.md")
        git(self.store.root, "commit", "-q", "-m", "docs: doc", "--", "doc.md")
        git(self.store.root, "push", "-q", "origin", "main")
        entry = self.phase(works={"w1": "W1", "w2": "W2"})
        w1, i1 = entry.work_ids["w1"], entry.integration_id
        first = next(iter(keys))
        replan = Replan(
            remove_relation_ids=(self.relation("requires_completion", w1, i1),),
            add_relations=tuple(RelationSpec("requires_completion", key, i1) for key in keys),
            new_works={
                key: WorkSpec(
                    name, f"{name} replaces W1", phase_id=self.pa, roadmap_id=self.rid,
                    related=(RelatedSpec("must_read", "doc.md"),) if key == first else (),
                    derivation_detail="W1 was the wrong cut" if key == first else None,
                )
                for key, name in keys.items()
            },
        )
        cancel = st.Cancel(replan, "superseded")
        return Scenario(
            "START cancel", w1, f"{w1}:cancel:0:works", tuple(keys), tuple(keys.values()),
            f"chore(workline): cancel {self.display_of('W1')}",
            lambda: st.start(self.store, w1, "single-work", lambda ctx: cancel),
        )

    def phase_work_exclusion(self, keys: dict[str, str] | None = None) -> Scenario:
        """Roadmap excludes the Phase Work W2 from the plan and registers its replacements (BL-029)."""
        keys = keys or {"w3": "W3"}
        entry = self.phase(works={"w1": "W1", "w2": "W2"})
        w2, i1 = entry.work_ids["w2"], entry.integration_id
        replan = Replan(
            remove_relation_ids=(self.relation("requires_completion", w2, i1),),
            add_relations=tuple(RelationSpec("requires_completion", key, i1) for key in keys),
            new_works={key: WorkSpec(name, name.lower(), phase_id=self.pa, roadmap_id=self.rid)
                       for key, name in keys.items()},
        )
        return Scenario(
            "Roadmap plan exclusion", w2, "replan:works", tuple(keys), tuple(keys.values()),
            f"chore(workline): plan_excluded {w2}",  # Roadmap names the entity; START's standalone one names the display
            lambda: rm.plan_exclude_work(self.store, w2, replan),
        )

    def standalone_exclusion(self, keys: dict[str, str] | None = None) -> Scenario:
        """START excludes the standalone Work S2 from the plan and registers its replacements (BL-029)."""
        keys = keys or {"s4": "S4"}
        s2 = create_standalone_work(self.store, WorkSpec("S2", "s2")).work_id
        s3 = create_standalone_work(self.store, WorkSpec("S3", "s3")).work_id
        s1 = create_standalone_work(self.store, WorkSpec("S1", "s1")).work_id
        st.plan_exclude_standalone_work(
            self.store, s1, Replan(add_relations=(RelationSpec("requires_completion", s2, s3),))
        )
        replan = Replan(
            remove_relation_ids=(self.relation("requires_completion", s2, s3),),
            add_relations=tuple(RelationSpec("requires_completion", key, s3) for key in keys),
            new_works={key: WorkSpec(name, name.lower()) for key, name in keys.items()},
        )
        return Scenario(
            "START plan exclusion", s2, "replan:works", tuple(keys), tuple(keys.values()),
            f"chore(workline): plan_excluded {self.display_of('S2')}",
            lambda: st.plan_exclude_standalone_work(self.store, s2, replan),
        )

    OWNERS = ("cancel_replacement", "phase_work_exclusion", "standalone_exclusion")

    # ------------------------------------------------------------------ running
    def interrupt(self, scenario: Scenario, window=after_recording) -> dict:
        with window(f"^{re.escape(scenario.stage)}$"), self.assertRaises(Interrupted):
            scenario.call()
        (pending,) = MutationController(self.store).list_pending()
        return pending

    def assertFinished(self, scenario: Scenario, result) -> None:
        """The operation finished once, on its own commit, and left the Project valid and nothing of its own behind."""
        self.assertIsNotNone(result)
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(self.subjects().count(scenario.subject), 1)
        self.assertEqual(self.head(), self.remote_head())
        self.assertEqual(sorted(self.dirty()), sorted(self.untracked))
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(len(self.edges()), len(set(self.edges())))
        self.assertEqual([name for name in scenario.names if name in self.displays()], list(scenario.names))

    def assertRefusedUntouched(self, call, error: type[StopError] = ReconcileRequired) -> StopError:
        """The retry STOPs having changed nothing at all - no record, no file, no commit."""
        before = self.snapshot()
        with self.assertRaises(error) as refused:
            call()
        self.assertEqual(self.snapshot(), before)
        return refused.exception

    def each_owner(self, body, owners: tuple[str, ...] | None = None) -> None:
        """``body(case, factory)`` for each owner, on its own Project, so one owner's Git never reaches another's."""
        for factory in owners or self.OWNERS:
            with self.subTest(owner=factory):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    body(case, factory)
                finally:
                    case.doCleanups()


# ------------------------------------------------------- what a display is not
class DisplayIsNotIdentityTests(DisplayNumberingCase):
    def test_a_duplicate_display_and_a_gap_leave_the_project_with_no_problems(self) -> None:
        self.phase(works={"w1": "W1", "w2": "W2"})
        held = self.displays()
        self.assertEqual(sorted(held.values()), ["W-01", "W-02", "W-03"])
        duplicate, _ = self.foreign_work("Duplicate", display=held["W1"])
        gap, _ = self.foreign_work("Gap", display="W-90")

        self.assertEqual(validate_project(self.store), [])
        view = ProjectView.load(self.store)
        self.assertEqual(view.works[duplicate].display, held["W1"])  # two Works show the same number
        self.assertEqual(view.works[gap].display, "W-90")  # and the numbering may skip
        # Every Work is held under its stable ID; no mapping is keyed by a display.
        self.assertEqual(sorted(view.works), sorted(w.id for w in view.works.values()))
        self.assertLess(len({w.display for w in view.works.values()}), len(view.works))

    def test_a_projection_stands_a_new_work_up_with_no_number_at_all(self) -> None:
        self.phase(works={"w1": "W1"})
        projected = ops.projected_view(
            ProjectView.load(self.store),
            add_works={new_id("work"): WorkSpec("P", "p", phase_id=self.pa, roadmap_id=self.rid)},
        )
        (placeholder,) = [w.display for w in projected.works.values() if w.name == "P"]
        self.assertEqual(placeholder, "W-??")
        ops.validate_projection(projected, "display placeholder")  # and that projection is accepted


# ------------------------------------------- the resume a foreign Work refused
class ForeignWorkResumeTests(DisplayNumberingCase):
    def test_a_replan_resumes_when_a_foreign_work_arrived_after_its_registration_was_recorded(self) -> None:
        """BL-045 itself, in both windows where the registration is already recorded."""
        def body(case, factory, window):
            scenario = getattr(case, factory)()
            pending = case.interrupt(scenario, window)
            recorded = case.recorded_displays(pending, scenario)
            registered = case.registered(pending, scenario)
            case.foreign_work()

            case.assertFinished(scenario, scenario.call())
            case.assertEqual({key: ProjectView.load(case.store).works[work_id].display
                              for key, work_id in registered.items()}, recorded)

        for window, label in ((after_recording, "recorded"), (after_applying, "applied")):
            self.each_owner(lambda case, factory, w=window: body(case, factory, w))

    def test_the_resume_writes_the_display_its_stage_recorded_and_never_renumbers_it(self) -> None:
        """What is written is the record's display; the record itself is not rewritten to the live numbering."""
        def body(case, factory):
            scenario = getattr(case, factory)()
            pending = case.interrupt(scenario)
            registered = case.registered(pending, scenario)
            recorded = case.recorded_displays(pending, scenario)
            held = len(ProjectView.load(case.store).works)
            case.foreign_work()
            case.foreign_work("Second", display="W-91")
            # The record is never rewritten to the live numbering, which is now two Works further on.
            live = {key: f"W-{held + 2 + offset + 1:02d}" for offset, key in enumerate(scenario.keys)}
            case.assertNotEqual(live, recorded)

            case.assertFinished(scenario, scenario.call())

            view = ProjectView.load(case.store)
            case.assertEqual({key: view.works[work_id].display for key, work_id in registered.items()}, recorded)
            case.assertNotIn(list(live.values())[0], [w.display for w in view.works.values()])

        self.each_owner(body)

    def test_every_kind_of_foreign_work_resumes_the_same_way(self) -> None:
        """Standalone or in the same Phase, named as the new Work or not, committed there or untracked here."""
        variants = {
            "standalone": {},
            "same Phase": {"in_phase": True},
            "same name as the new Work": {"name": "<new>"},
            "different name": {"name": "Something else"},
            "committed": {"commit": True},
            "untracked": {"commit": False},
        }
        for label, foreign in variants.items():
            for factory in self.OWNERS:
                with self.subTest(foreign=label, owner=factory):
                    case = type(self)(self._testMethodName)
                    case.setUp()
                    try:
                        scenario = getattr(case, factory)()
                        if foreign.get("in_phase") and case.pa is None:
                            continue  # a standalone Work's exclusion has no Phase to share
                        kwargs = dict(foreign)
                        if kwargs.get("name") == "<new>":
                            kwargs["name"] = scenario.names[0]
                        pending = case.interrupt(scenario)
                        registered = case.registered(pending, scenario)
                        recorded = case.recorded_displays(pending, scenario)
                        foreign_id, _ = case.foreign_work(**kwargs)
                        case.assertNotIn(foreign_id, registered.values())

                        case.assertFinished(scenario, scenario.call())
                        case.assertEqual({key: ProjectView.load(case.store).works[work_id].display
                                          for key, work_id in registered.items()}, recorded)
                    finally:
                        case.doCleanups()

    def test_the_foreign_work_is_left_byte_for_byte_as_it_was_and_no_commit_carries_it(self) -> None:
        def body(case, factory):
            scenario = getattr(case, factory)()
            pending = case.interrupt(scenario)
            registered = set(case.registered(pending, scenario).values())
            foreign_id, rel_path = case.foreign_work("Foreign")
            content = (case.store.root / rel_path).read_bytes()

            case.assertFinished(scenario, scenario.call())

            case.assertEqual((case.store.root / rel_path).read_bytes(), content)  # not overwritten
            case.assertIn(rel_path, case.dirty())  # not staged
            case.assertEqual(git(case.store.root, "log", "--format=%H", "--", rel_path).strip(), "")  # not committed
            head_files = git(case.store.root, "show", "--name-only", "--format=", "HEAD").split()
            case.assertNotIn(rel_path, head_files)
            view = ProjectView.load(case.store)
            case.assertEqual(view.works[foreign_id].name, "Foreign")  # nothing took its ID
            case.assertNotIn(foreign_id, registered)
            for relation in list(view.roadmap_relations) + list(view.related):
                case.assertNotIn(foreign_id, (relation.from_id, relation.to))  # not pulled into a relation

        self.each_owner(body)

    def test_a_foreign_work_that_arrived_before_the_registration_was_recorded_still_finishes(self) -> None:
        """The control: the same plan, the same foreign Work, one window earlier - which always worked."""
        def body(case, factory):
            scenario = getattr(case, factory)()
            case.foreign_work()
            case.assertFinished(scenario, scenario.call())

        self.each_owner(body)

    def test_the_answer_no_longer_depends_on_which_window_the_foreign_work_arrived_in(self) -> None:
        """Before the stage or after it, the same request on the same plan reaches the same answer."""
        answers: dict[tuple[str, str], str] = {}
        for factory in self.OWNERS:
            for when in ("before the stage", "after the stage"):
                with self.subTest(owner=factory, when=when):
                    case = type(self)(self._testMethodName)
                    case.setUp()
                    try:
                        scenario = getattr(case, factory)()
                        if when == "after the stage":
                            case.interrupt(scenario)
                        case.foreign_work()
                        try:
                            case.assertFinished(scenario, scenario.call())
                        except StopError as stopped:
                            answers[(factory, when)] = stopped.code
                        else:
                            answers[(factory, when)] = "finished"
                    finally:
                        case.doCleanups()
        self.assertEqual(answers, {(factory, when): "finished"
                                   for factory in self.OWNERS
                                   for when in ("before the stage", "after the stage")})

    def test_several_new_works_keep_the_whole_numbering_their_stage_recorded(self) -> None:
        def body(case, factory):
            scenario = getattr(case, factory)({"a": "First", "b": "Second"})
            pending = case.interrupt(scenario)
            registered = case.registered(pending, scenario)
            recorded = case.recorded_displays(pending, scenario)
            case.foreign_work()

            case.assertFinished(scenario, scenario.call())

            view = ProjectView.load(case.store)
            case.assertEqual({key: view.works[work_id].display for key, work_id in registered.items()}, recorded)
            numbers = [int(recorded[key].split("-")[1]) for key in scenario.keys]
            case.assertEqual(numbers, [numbers[0], numbers[0] + 1])  # consecutive, as the stage allocated them

        self.each_owner(body)

    def test_an_uninterrupted_operation_numbers_its_new_works_exactly_as_before(self) -> None:
        def body(case, factory):
            scenario = getattr(case, factory)({"a": "First", "b": "Second"})
            held = len(ProjectView.load(case.store).works)

            case.assertFinished(scenario, scenario.call())

            case.assertEqual([case.display_of(name) for name in scenario.names],
                             [f"W-{held + 1:02d}", f"W-{held + 2:02d}"])

        self.each_owner(body)


# ------------------------------------------------- what still leaves it unproven
class StillRefusedTests(DisplayNumberingCase):
    def test_a_work_already_registered_at_a_reserved_id_still_stops(self) -> None:
        """A reserved path another Work squats on: the registration's own write no longer replays."""
        def body(case, factory):
            scenario = getattr(case, factory)()
            pending = case.interrupt(scenario)
            (work_id,) = case.registered(pending, scenario).values()
            case.foreign_work("Squatter", work_id=work_id)

            case.assertRefusedUntouched(scenario.call)

        self.each_owner(body)

    def test_a_stage_registering_another_work_still_stops(self) -> None:
        def body(case, factory):
            scenario = getattr(case, factory)()
            pending = case.interrupt(scenario)
            (work_id,) = case.registered(pending, scenario).values()
            case.foreign_work()
            other = new_id("work")

            with case.subTest(tampered="the path the Work is written to"):
                case.edit_record(pending, lambda record: case.work_write(record, scenario.stage, work_id)["payload"]
                                 .update(path=ProjectStore.entity_rel_path("work", other)))
                case.assertRefusedUntouched(scenario.call)
            with case.subTest(tampered="the stable ID in the Work"):
                case.edit_record(pending, lambda record: case.work_write(record, scenario.stage, other)["payload"]
                                 .update(path=ProjectStore.entity_rel_path("work", work_id)))
                case.edit_record(pending, lambda record: case.work_write(record, scenario.stage, work_id)["payload"]
                                 .update(content=case.work_write(record, scenario.stage, work_id)["payload"]["content"]
                                         .replace(work_id, other, 1)))
                case.assertRefusedUntouched(scenario.call)

        self.each_owner(body)

    def test_a_stage_whose_relations_are_not_the_ones_this_request_adds_still_stops(self) -> None:
        def body(case, factory):
            scenario = getattr(case, factory)()
            pending = case.interrupt(scenario)
            case.foreign_work()

            def retype(record):
                (effect,) = [e for e in case.stage_effects(record, scenario.stage) if e["kind"] == "add_relation"
                             and e["payload"]["file"] == "roadmap"]
                effect["payload"]["record"]["type"] = "planned_next"

            case.edit_record(pending, retype)
            case.assertRefusedUntouched(scenario.call)

        self.each_owner(body)

    def test_a_tampered_work_still_stops(self) -> None:
        def tampers(content: str, work_id: str) -> dict[str, str]:
            meta, body = yamlish.load_frontmatter(content)
            renamed = dict(meta)
            renamed["type"] = "phase"
            return {
                "the Work's name": content.replace("# ", "# Other ", 1),
                "the desired state": content.replace("replaces", "does not replace").replace("w3", "other")
                                            .replace("s4", "other").replace("first", "other").replace("second", "other"),
                "the entity type": render_entity(renamed, body),
                "a frontmatter key nothing decided": render_entity({**meta, "note": "added"}, body),
            }

        def body(case, factory):
            scenario = getattr(case, factory)()
            pending = case.interrupt(scenario)
            (work_id,) = case.registered(pending, scenario).values()
            case.foreign_work()
            original = case.work_write(pending, scenario.stage, work_id)["payload"]["content"]
            for label, tampered in tampers(original, work_id).items():
                if tampered == original:
                    continue
                with case.subTest(tampered=label):
                    case.edit_record(pending, lambda record, text=tampered: case.work_write(
                        record, scenario.stage, work_id)["payload"].update(content=text))
                    case.assertRefusedUntouched(scenario.call)
            case.edit_record(pending, lambda record: case.work_write(
                record, scenario.stage, work_id)["payload"].update(content=original))
            with case.subTest(tampered="nothing"):
                case.assertFinished(scenario, scenario.call())  # the same record, untampered, still finishes

        self.each_owner(body)

    def test_a_display_the_project_would_refuse_to_hold_still_stops(self) -> None:
        """A display is not identity, but a stage that records none at all proves no registration."""
        def body(case, factory):
            scenario = getattr(case, factory)()
            pending = case.interrupt(scenario)
            (work_id,) = case.registered(pending, scenario).values()
            case.foreign_work()
            original = case.work_write(pending, scenario.stage, work_id)["payload"]["content"]
            unreadable = original.replace("---\n", "", 1)
            for label, content in {
                "an empty display": case.with_display(original, ""),
                "no display": case.with_display(original, None),
                "a display that is not a string": case.with_display(original, 4),
                "frontmatter that cannot be read": unreadable,
            }.items():
                with case.subTest(recorded=label):
                    case.edit_record(pending, lambda record, text=content: case.work_write(
                        record, scenario.stage, work_id)["payload"].update(content=text))
                    case.assertRefusedUntouched(scenario.call)
            with case.subTest(recorded="no write for the new Work at all"):
                case.edit_record(pending, lambda record: record.__setitem__(
                    "effects", [e for e in record["effects"]
                                if not (e["stage"] == scenario.stage and e["kind"] == "write_file"
                                        and e["payload"]["path"] == ProjectStore.entity_rel_path("work", work_id))]))
                case.assertRefusedUntouched(scenario.call)

        self.each_owner(body)

    def test_a_stage_that_records_its_registration_in_another_order_still_stops(self) -> None:
        def body(case, factory):
            scenario = getattr(case, factory)({"a": "First", "b": "Second"})
            pending = case.interrupt(scenario)
            case.foreign_work()

            def swap(record):
                writes = [e for e in case.stage_effects(record, scenario.stage) if e["kind"] == "write_file"]
                first, second = writes[0]["payload"], writes[1]["payload"]
                first["path"], second["path"] = second["path"], first["path"]
                first["content"], second["content"] = second["content"], first["content"]

            case.edit_record(pending, swap)
            case.assertRefusedUntouched(scenario.call)

        self.each_owner(body)

    def test_a_stage_holding_an_effect_this_request_never_decided_still_stops(self) -> None:
        def body(case, factory):
            scenario = getattr(case, factory)()
            pending = case.interrupt(scenario)
            case.foreign_work()

            def append(record):
                extra = dict(case.stage_effects(record, scenario.stage)[0])
                extra["seq"] = max(e["seq"] for e in record["effects"]) + 1
                extra["payload"] = {**extra["payload"], "path": f".workline/works/{new_id('work')}.md"}
                record["effects"].append(extra)

            case.edit_record(pending, append)
            case.assertRefusedUntouched(scenario.call)

        self.each_owner(body)


# ------------------------------------------------------ the contracts around it
class NeighbouringContractTests(DisplayNumberingCase):
    def test_a_resume_on_another_branch_still_stops_however_the_numbering_reads(self) -> None:
        """BL-036 / BL-038: the effects carry the branch they were decided on, and a display never excuses it."""
        def body(case, factory):
            scenario = getattr(case, factory)()
            case.interrupt(scenario)
            case.foreign_work()
            git(case.store.root, "checkout", "-q", "-b", "side")

            stopped = case.assertRefusedUntouched(scenario.call)
            case.assertIn("branch", stopped.message)
            case.assertEqual(gitcmd.current_branch(case.store.root), "side")

        self.each_owner(body)

    def test_a_change_that_was_there_before_the_operation_still_refuses_before_any_effect(self) -> None:
        """BL-041: the pre-existing dirty preflight still refuses before the first effect, with a foreign Work present."""
        scenario = self.phase_work_exclusion()
        self.foreign_work()  # a foreign Work changes nothing about this refusal
        log = self.store.root / ".workline/events/events.jsonl"
        before = log.read_text(encoding="utf-8")
        log.write_text(before + "\n", encoding="utf-8", newline="")
        files, head = self.snapshot()["files"], self.head()

        with self.assertRaises(StopError) as refused:
            scenario.call()

        self.assertEqual(refused.exception.code, "dirty_overlap")
        self.assertEqual(MutationController(self.store).list_pending(), [])  # the mutation is abandoned, not left pending
        self.assertEqual(self.snapshot()["files"], files)  # no event, no Work, no relation
        self.assertEqual(self.head(), head)
        self.assertEqual(log.read_text(encoding="utf-8"), before + "\n")  # and the change is still the human's
        self.assertEqual([name for name in scenario.names if name in self.displays()], [])  # nothing registered

    def test_the_cancel_decision_is_still_what_the_resume_is_carried_on_from(self) -> None:
        """BL-030: the decision is read back from the record, the executor is never asked again, and it must match."""
        scenario = self.cancel_replacement()
        pending = self.interrupt(scenario)
        self.foreign_work()
        asked: list[str] = []
        cancelled = st.Cancel(Replan(), "superseded")

        def refuse_to_decide(ctx):
            asked.append(ctx.work.id)
            return cancelled

        result = st.start(self.store, scenario.target, "single-work", refuse_to_decide)

        self.assertEqual(asked, [])  # carried on from the record, not decided again
        self.assertEqual((result.status, result.detail), ("cancelled", "superseded"))
        self.assertEqual(result.mutation_id, pending["mutation_id"])
        self.assertFinished(scenario, result)

    def test_a_record_of_another_request_is_still_never_carried_on(self) -> None:
        """BL-029: a plan exclusion continues only the record of this very request."""
        entry = self.phase(works={"w1": "W1", "w2": "W2"})
        w2, i1 = entry.work_ids["w2"], entry.integration_id
        removal = self.relation("requires_completion", w2, i1)
        first = Replan(remove_relation_ids=(removal,),
                       add_relations=(RelationSpec("requires_completion", "w3", i1),),
                       new_works={"w3": WorkSpec("W3", "w3", phase_id=self.pa, roadmap_id=self.rid)})
        other = Replan(remove_relation_ids=(removal,),
                       add_relations=(RelationSpec("requires_completion", "w3", i1),),
                       new_works={"w3": WorkSpec("W3", "something else", phase_id=self.pa, roadmap_id=self.rid)})
        scenario = Scenario("Roadmap plan exclusion", w2, "replan:works", ("w3",), ("W3",),
                            f"chore(workline): plan_excluded {w2}",
                            lambda: rm.plan_exclude_work(self.store, w2, first))
        self.interrupt(scenario)
        self.foreign_work()

        self.assertRefusedUntouched(lambda: rm.plan_exclude_work(self.store, w2, other))
        self.assertFinished(scenario, scenario.call())  # and this request's own record still finishes


if __name__ == "__main__":
    unittest.main()
