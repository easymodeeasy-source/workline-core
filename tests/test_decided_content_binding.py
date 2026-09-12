"""A resumed mutation must be the same request, not merely the same slot (BL-024).

An operation that is interrupted leaves a pending recovery record, and a retry
continues it instead of starting again. Continuing is only correct when the
retry is asking for the same thing: an invocation that says which operation and
which name or label - but not what the caller decided - makes two materially
different requests look like one. The second then resumes the first's record,
skips the stages it already recorded, and returns success while the Project
keeps what the first request decided. The postchecks do not catch it: they check
that the entity exists, never that it holds what this request asked for.

So every operation whose caller decides content records a canonical identity of
that content in its own invocation, durable before the first ID is reserved. The
same request still resumes the same mutation with the same reserved IDs; a
request that decided something else is refused before anything is opened or
replayed, and the pending record - its effects, its reserved IDs and its pending
status - is left exactly as it was, for a human to reconcile. A record written
before its owner recorded an identity proves neither request, so it is refused
the same way.

Operations whose mutation carries no caller-decided payload are unchanged, and
so is START, whose decisions belong to each attempt rather than to the mutation.
"""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, scripted_executor
from workline import create as cr
from workline import gitops
from workline import roadmap as rm
from workline import start as st
from workline import yamlish
from workline.create import RelatedSpec, RelationSpec, WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, SpecViolation
from workline.mutation import Mutation, MutationController
from workline.ops import Replan
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.state import ProjectView
from workline.store import PHASE_DESIRED_HEADING, WORK_DESIRED_HEADING
from workline.validate import validate_project


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


class BindingCase(WorklineTestCase):
    """Interruption points, and the observations every owner's tests share."""

    # interruption ----------------------------------------------------------
    def after_stage(self, module, attr: str, stage: str):
        """Interrupt once the named registration stage has recorded and applied."""
        real = getattr(module, attr)

        def fire(mutation, name, *args, **kwargs):
            result = real(mutation, name, *args, **kwargs)
            if name == stage:
                raise Interrupted(f"after {attr}({stage})")
            return result

        return mock.patch.object(module, attr, fire)

    def after_recording(self, stage: str):
        """Interrupt with the stage's effects durably recorded but none of them applied."""
        real = Mutation.add_effects

        def fire(mutation, name, effects):
            real(mutation, name, effects)
            if name == stage:
                raise Interrupted(f"after add_effects({stage})")

        return mock.patch.object(Mutation, "add_effects", fire)

    def before_recording(self, stage: str):
        """Interrupt with the IDs reserved and the stage never recorded."""
        real = Mutation.add_effects

        def fire(mutation, name, effects):
            if name == stage:
                raise Interrupted(f"before add_effects({stage})")
            real(mutation, name, effects)

        return mock.patch.object(Mutation, "add_effects", fire)

    def before_effects(self, module, attr: str):
        """Interrupt after the mutation is opened and before it decides anything."""

        def fire(*args, **kwargs):
            raise Interrupted(attr)

        return mock.patch.object(module, attr, fire)

    # observation -----------------------------------------------------------
    def pending(self) -> dict:
        (record,) = MutationController(self.store).list_pending()
        return record

    def live_ids(self) -> set[str]:
        """Every stable ID the Project now holds, so a reservation can be shown to be the one used."""
        view = ProjectView.load(self.store)
        return (
            set(view.roadmaps)
            | set(view.phases)
            | set(view.works)
            | {relation.id for relation in view.roadmap_relations}
            | {relation.id for relation in view.related}
        )

    def record_bytes(self) -> dict[str, bytes]:
        return {path.name: path.read_bytes() for path in sorted(self.store.mutations.glob("*.yaml"))}

    def assertRefused(self, before: dict[str, bytes], call, *args, **kwargs) -> str:
        """The retry STOPs for reconciliation and every recovery record stays as it was."""
        with self.assertRaises(ReconcileRequired) as raised:
            call(*args, **kwargs)
        message = str(raised.exception)
        self.assertIn("reconcile required", message)
        # The record holds its own status, effects and reserved IDs, so byte
        # equality is the whole claim: nothing abandoned, replaced or rolled back.
        self.assertEqual(self.record_bytes(), before)
        return message

    def strip_the_request(self, record: dict, key: str | None = None) -> bytes:
        """The record as an owner wrote it before it recorded what it had decided.

        ``key`` also puts back the label that owner would have derived, for the
        owners whose default label this change alters.
        """
        path = MutationController(self.store).intent_path(record["mutation_id"])
        data = yamlish.load(path.read_text(encoding="utf-8"))
        del data["invocation"]["request"]
        if key is not None:
            data["invocation"]["key"] = key
        path.write_text(yamlish.dump(data), encoding="utf-8")
        return path.read_bytes()

    def assertLegacyRefused(self, record: dict, call, *args, _key: str | None = None, **kwargs) -> None:
        recorded = self.strip_the_request(record, _key)

        message = self.assertRefused(self.record_bytes(), call, *args, **kwargs)

        self.assertIn(record["mutation_id"], message)
        self.assertIn("before this operation recorded what it", message)
        path = MutationController(self.store).intent_path(record["mutation_id"])
        self.assertEqual(path.read_bytes(), recorded)


# --------------------------------------------------------------------------- direct CREATE
D1 = WorkSpec("Solo", "D1 が成立する")
D2 = WorkSpec("Solo", "D2 が成立する")


class DirectCreateBindingTests(BindingCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        for name in ("a.md", "b.md"):
            (self.store.root / name).write_text(f"{name}\n", encoding="utf-8")

    def interrupt(self, spec: WorkSpec = D1, *, point: str = "registered") -> dict:
        points = {
            "intent only": lambda: self.before_effects(gitops, "ensure_git_ready"),
            "recorded": lambda: self.after_recording("register"),
            "registered": lambda: self.after_stage(cr, "register_works", "register"),
        }
        with points[point]():
            with self.assertRaises(Interrupted):
                create_standalone_work(self.store, spec)
        return self.pending()

    def stored_desired(self) -> list[str]:
        view = ProjectView.load(self.store)
        return [(w.section(WORK_DESIRED_HEADING) or "").strip() for w in view.works.values()]

    # the recorded identity -------------------------------------------------
    def test_the_record_holds_what_the_request_decided(self) -> None:
        pending = self.interrupt()

        request = pending["invocation"]["request"]
        self.assertEqual(request["version"], cr.DIRECT_REQUEST_VERSION)
        self.assertEqual(request["name"], "Solo")
        self.assertEqual(request["desired_state"], "D1 が成立する")
        self.assertEqual(request["related"], [])
        self.assertIsNone(request["derivation_detail"])

    def test_the_request_is_on_disk_before_the_first_id_is_reserved(self) -> None:
        """The window in which a record exists but is bound to nothing is closed."""
        seen: list[object] = []
        reserve = Mutation.reserve_id

        def watch(mutation: Mutation, key: str, kind: str) -> str:
            if not seen:
                record = yamlish.load(mutation.path.read_text(encoding="utf-8"))
                seen.append(record["invocation"].get("request"))
            return reserve(mutation, key, kind)

        with mock.patch.object(Mutation, "reserve_id", watch):
            create_standalone_work(self.store, D1)

        self.assertEqual(seen, [cr.direct_request_identity(D1)])

    def test_a_name_that_differs_only_in_whitespace_is_a_different_request(self) -> None:
        """Rendering writes the name as given, so its whitespace reaches the Project."""
        self.assertNotEqual(cr.direct_request_identity(WorkSpec("Solo ", "same")),
                            cr.direct_request_identity(WorkSpec("Solo", "same")))

    def test_an_absent_derivation_detail_differs_from_an_empty_one(self) -> None:
        absent = cr.direct_request_identity(WorkSpec("Solo", "same"))
        empty = cr.direct_request_identity(WorkSpec("Solo", "same", derivation_detail="  "))

        self.assertIsNone(absent["derivation_detail"])
        self.assertEqual(empty["derivation_detail"], "")
        self.assertNotEqual(absent, empty)

    # resume ----------------------------------------------------------------
    def test_the_same_request_carries_the_create_forward(self) -> None:
        for point in ("intent only", "recorded", "registered"):
            with self.subTest(point=point):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    pending = case.interrupt(point=point)

                    result = create_standalone_work(case.store, D1)

                    case.assertTrue(result.resumed)
                    case.assertEqual(result.mutation_id, pending["mutation_id"])
                    for key, value in pending["reserved_ids"].items():
                        case.assertIn(value, case.live_ids(), key)  # nothing stranded
                    case.assertEqual(case.stored_desired(), ["D1 が成立する"])  # exactly one Work
                    case.assertEqual(validate_project(case.store), [])
                finally:
                    case.doCleanups()

    def test_whitespace_that_rendering_strips_still_resumes(self) -> None:
        pending = self.interrupt()

        result = create_standalone_work(self.store, WorkSpec("Solo", "\n  D1 が成立する  \n"))

        self.assertEqual(result.mutation_id, pending["mutation_id"])
        self.assertEqual(self.stored_desired(), ["D1 が成立する"])

    # refusal ---------------------------------------------------------------
    def test_a_different_desired_state_is_refused(self) -> None:
        pending = self.interrupt()
        before = self.record_bytes()

        message = self.assertRefused(before, create_standalone_work, self.store, D2)

        self.assertIn(pending["mutation_id"], message)
        self.assertIn("different request", message)
        self.assertEqual(self.stored_desired(), ["D1 が成立する"])  # and no second Work

    def test_a_different_related_edge_is_refused(self) -> None:
        spec = WorkSpec("Solo", "same", related=(RelatedSpec("must_read", "a.md"),))
        other = WorkSpec("Solo", "same", related=(RelatedSpec("must_read", "b.md"),))
        self.interrupt(spec)
        before = self.record_bytes()

        self.assertRefused(before, create_standalone_work, self.store, other)

        view = ProjectView.load(self.store)
        self.assertEqual([r.to for r in view.related], ["a.md"])

    def test_a_condition_that_differs_only_in_true_versus_one_is_refused(self) -> None:
        """Python reads ``True`` and ``1`` as one value; the record keeps them apart."""
        def spec(flag: object) -> WorkSpec:
            condition = {"kind": "path_glob", "pattern": "src/*.py", "recursive": flag}
            return WorkSpec("Solo", "same", related=(RelatedSpec("conditional_must_read", "a.md", condition),))

        self.interrupt(spec(True))
        before = self.record_bytes()

        self.assertRefused(before, create_standalone_work, self.store, spec(1))

    def test_an_added_derivation_detail_is_refused(self) -> None:
        self.interrupt(WorkSpec("Solo", "same"))
        before = self.record_bytes()

        self.assertRefused(before, create_standalone_work, self.store,
                           WorkSpec("Solo", "same", derivation_detail="どこから来たか"))

    def test_a_legacy_record_is_left_for_reconciliation(self) -> None:
        pending = self.interrupt()

        self.assertLegacyRefused(pending, create_standalone_work, self.store, D1)


# --------------------------------------------------------------------------- Roadmap creation
def plan(**overrides) -> rm.RoadmapPlan:
    fields = {
        "name": "R",
        "background": "D1 の背景",
        "desired_state": "D1 の達成したい状態",
        "phases": {"a": PhaseSpec("Phase A", "A が成立する"), "b": PhaseSpec("Phase B", "B が成立する")},
        "relations": (PhaseRelationSpec("planned_next", "a", "b"),),
    }
    fields.update(overrides)
    return rm.RoadmapPlan(**fields)


class RoadmapCreationBindingTests(BindingCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def interrupt(self, requested: rm.RoadmapPlan | None = None, *, point: str = "recorded") -> dict:
        points = {
            "intent only": lambda: self.before_effects(gitops, "ensure_git_ready"),
            "recorded": lambda: self.after_recording("roadmap"),
            "phases": lambda: self.after_stage(rm, "register_phases", "phases"),
        }
        with points[point]():
            with self.assertRaises(Interrupted):
                rm.create_roadmap(self.store, requested or plan())
        return self.pending()

    def shape(self) -> dict:
        view = ProjectView.load(self.store)
        return {
            "roadmaps": sorted(r.name for r in view.roadmaps.values()),
            "phases": sorted(p.name for p in view.phases.values()),
            "relations": sorted((r.type, r.from_id, r.to) for r in view.roadmap_relations),
        }

    # the recorded identity -------------------------------------------------
    def test_the_record_holds_the_whole_plan(self) -> None:
        pending = self.interrupt()

        request = pending["invocation"]["request"]
        self.assertEqual(request["version"], rm.ROADMAP_REQUEST_VERSION)
        self.assertEqual(request["name"], "R")
        self.assertEqual(request["background"], "D1 の背景")
        self.assertEqual([p["key"] for p in request["phases"]], ["a", "b"])
        self.assertEqual(request["phases"][0]["name"], "Phase A")
        self.assertEqual(request["relations"], [{"type": "planned_next", "from": "a", "to": "b"}])
        self.assertIsNone(request["scope"])
        self.assertIsNone(request["out_of_scope"])

    def test_an_optional_section_records_presence_apart_from_content(self) -> None:
        """``render`` includes it on truthiness, so blank is present-and-empty and absent is absent."""
        for field in ("scope", "out_of_scope"):
            with self.subTest(section=field):
                absent = rm.roadmap_request_identity(plan(**{field: None}))
                blank = rm.roadmap_request_identity(plan(**{field: "   "}))
                filled = rm.roadmap_request_identity(plan(**{field: " 範囲 "}))

                self.assertIsNone(absent[field])
                self.assertEqual(blank[field], "")
                self.assertEqual(filled[field], "範囲")
                self.assertEqual(absent, rm.roadmap_request_identity(plan(**{field: ""})))

    # resume ----------------------------------------------------------------
    def test_the_same_plan_carries_the_creation_forward(self) -> None:
        for point in ("intent only", "recorded", "phases"):
            with self.subTest(point=point):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    pending = case.interrupt(point=point)
                    reserved = dict(pending["reserved_ids"])

                    result = rm.create_roadmap(case.store, plan())

                    case.assertTrue(result.resumed)
                    case.assertEqual(result.mutation_id, pending["mutation_id"])
                    for key, value in reserved.items():
                        case.assertIn(value, case.live_ids(), key)  # nothing stranded
                    case.assertEqual(case.shape()["phases"], ["Phase A", "Phase B"])
                    case.assertEqual(validate_project(case.store), [])
                finally:
                    case.doCleanups()

    def test_whitespace_that_rendering_strips_still_resumes(self) -> None:
        pending = self.interrupt()

        result = rm.create_roadmap(self.store, plan(
            background="\n D1 の背景 \n",
            desired_state="  D1 の達成したい状態",
            phases={"a": PhaseSpec("Phase A", " A が成立する\n"), "b": PhaseSpec("Phase B", "B が成立する  ")},
        ))

        self.assertEqual(result.mutation_id, pending["mutation_id"])
        self.assertEqual(self.shape()["phases"], ["Phase A", "Phase B"])

    # refusal ---------------------------------------------------------------
    def test_every_decided_part_of_the_plan_refuses_a_retry(self) -> None:
        variants = {
            "background": plan(background="D2 の背景"),
            "desired state": plan(desired_state="D2 の達成したい状態"),
            "scope added": plan(scope="範囲"),
            "out of scope added": plan(out_of_scope="範囲外"),
            "phase name": plan(phases={"a": PhaseSpec("Phase A", "A が成立する"),
                                       "b": PhaseSpec("RENAMED", "B が成立する")}),
            "phase desired state": plan(phases={"a": PhaseSpec("Phase A", "別の状態"),
                                                "b": PhaseSpec("Phase B", "B が成立する")}),
            "phase key": plan(phases={"a": PhaseSpec("Phase A", "A が成立する"),
                                      "z": PhaseSpec("Phase B", "B が成立する")},
                              relations=()),
            "declared order": plan(phases={"b": PhaseSpec("Phase B", "B が成立する"),
                                           "a": PhaseSpec("Phase A", "A が成立する")}),
            "relation": plan(relations=(PhaseRelationSpec("planned_next", "b", "a"),)),
            "relation removed": plan(relations=()),
        }
        for label, retry in variants.items():
            with self.subTest(part=label):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    case.interrupt()
                    before = case.record_bytes()

                    case.assertRefused(before, rm.create_roadmap, case.store, retry)

                    case.assertEqual(case.shape(), {"roadmaps": [], "phases": [], "relations": []})
                finally:
                    case.doCleanups()

    def test_the_refusal_comes_before_a_recorded_effect_is_replayed(self) -> None:
        pending = self.interrupt(point="recorded")
        self.assertEqual([effect.get("applied") for effect in pending["effects"]], [False])
        before = self.record_bytes()

        self.assertRefused(before, rm.create_roadmap, self.store, plan(background="D2 の背景"))

        # the recorded effect is still unapplied: nothing of D1 was written
        self.assertEqual(self.shape(), {"roadmaps": [], "phases": [], "relations": []})
        self.assertEqual([e.get("applied") for e in self.pending()["effects"]], [False])

    def test_a_legacy_record_is_left_for_reconciliation(self) -> None:
        pending = self.interrupt()

        self.assertLegacyRefused(pending, rm.create_roadmap, self.store, plan())


# --------------------------------------------------------------------------- Phase addition
class PhaseAdditionBindingTests(BindingCase):
    ADDED = {"y": PhaseSpec("Y", "Y が成立する"), "z": PhaseSpec("Z", "Z が成立する")}

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.roadmap = self.simple_roadmap(self.store).roadmap_id

    def add(self, phases=None, relations=(), **kwargs):
        return rm.add_phases(self.store, self.roadmap, phases or dict(self.ADDED), relations, **kwargs)

    def interrupt(self, phases=None, relations=(), *, point: str = "registered", **kwargs) -> dict:
        points = {
            "intent only": lambda: self.before_effects(rm, "register_phases"),
            "recorded": lambda: self.after_recording("phases"),
            "registered": lambda: self.after_stage(rm, "register_phases", "phases"),
        }
        with points[point]():
            with self.assertRaises(Interrupted):
                self.add(phases, relations, **kwargs)
        return self.pending()

    def added_phases(self) -> dict[str, str]:
        view = ProjectView.load(self.store)
        return {p.name: (p.section(PHASE_DESIRED_HEADING) or "").strip() for p in view.phases.values()}

    # the recorded identity -------------------------------------------------
    def test_the_record_holds_the_phases_it_decided(self) -> None:
        pending = self.interrupt(relations=(PhaseRelationSpec("planned_next", "y", "z"),))

        request = pending["invocation"]["request"]
        self.assertEqual([p["key"] for p in request["phases"]], ["y", "z"])
        self.assertEqual(request["phases"][1], {"key": "z", "name": "Z", "desired_state": "Z が成立する"})
        self.assertEqual(request["relations"], [{"type": "planned_next", "from": "y", "to": "z"}])

    def test_the_held_roadmap_flag_is_not_part_of_the_request(self) -> None:
        """It gates a held Roadmap and reaches no effect, so it decides nothing that is written."""
        self.assertNotIn("future_plan_change", rm.phase_addition_request_identity(dict(self.ADDED), ()))

    # resume ----------------------------------------------------------------
    def test_the_same_request_carries_the_addition_forward(self) -> None:
        for point in ("intent only", "recorded", "registered"):
            with self.subTest(point=point):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    pending = case.interrupt(point=point)
                    reserved = dict(pending["reserved_ids"])

                    result = case.add()

                    case.assertTrue(result.resumed)
                    case.assertEqual(result.mutation_id, pending["mutation_id"])
                    for key, value in reserved.items():
                        case.assertIn(value, case.live_ids(), key)  # nothing stranded
                    case.assertEqual(sorted(case.added_phases()), ["Phase A", "Y", "Z"])
                    case.assertEqual(validate_project(case.store), [])
                finally:
                    case.doCleanups()

    def test_the_held_roadmap_flag_alone_still_resumes(self) -> None:
        pending = self.interrupt(future_plan_change=True)

        result = self.add(future_plan_change=False)

        self.assertEqual(result.mutation_id, pending["mutation_id"])
        self.assertEqual(sorted(self.added_phases()), ["Phase A", "Y", "Z"])

    def test_whitespace_that_rendering_strips_still_resumes(self) -> None:
        pending = self.interrupt()

        result = self.add({"y": PhaseSpec("Y", "  Y が成立する"), "z": PhaseSpec("Z", "Z が成立する\n\n")})

        self.assertEqual(result.mutation_id, pending["mutation_id"])
        self.assertEqual(self.added_phases()["Z"], "Z が成立する")

    # refusal ---------------------------------------------------------------
    def test_a_different_phase_desired_state_is_refused(self) -> None:
        self.interrupt()
        before = self.record_bytes()

        self.assertRefused(before, self.add, {"y": PhaseSpec("Y", "Y が成立する"), "z": PhaseSpec("Z", "別の状態")})

        self.assertEqual(self.added_phases()["Z"], "Z が成立する")

    def test_a_different_relation_set_is_refused(self) -> None:
        self.interrupt(relations=(PhaseRelationSpec("planned_next", "y", "z"),))
        before = self.record_bytes()

        self.assertRefused(before, self.add, None, (PhaseRelationSpec("planned_next", "z", "y"),))

    def test_under_one_label_a_different_order_or_name_is_refused(self) -> None:
        """The label is the caller's; only the recorded request says what was decided."""
        variants = {
            "declared order": {"z": PhaseSpec("Z", "Z が成立する"), "y": PhaseSpec("Y", "Y が成立する")},
            "name whitespace": {"y": PhaseSpec("Y ", "Y が成立する"), "z": PhaseSpec("Z", "Z が成立する")},
            "phase key": {"y": PhaseSpec("Y", "Y が成立する"), "other": PhaseSpec("Z", "Z が成立する")},
        }
        for label, retry in variants.items():
            with self.subTest(part=label):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    case.interrupt(invocation_key="K")
                    before = case.record_bytes()

                    case.assertRefused(before, case.add, retry, (), invocation_key="K")
                finally:
                    case.doCleanups()

    def test_a_held_roadmap_refuses_before_the_mutation_is_touched(self) -> None:
        """The lifecycle gate runs before ``_open``, so a refused retry abandons nothing."""
        rm.hold_roadmap(self.store, self.roadmap)
        pending = self.interrupt(point="intent only", future_plan_change=True)
        self.assertEqual(pending["effects"], [])
        before = self.record_bytes()

        with self.assertRaises(SpecViolation) as raised:
            self.add(future_plan_change=False)

        self.assertIn("held", str(raised.exception))
        self.assertEqual(self.record_bytes(), before)
        self.assertEqual(self.pending()["status"], "pending")  # not abandoned

    def test_a_held_roadmap_does_not_hide_an_unresumable_record(self) -> None:
        """The lifecycle fact says nothing about the record this request cannot continue."""
        rm.hold_roadmap(self.store, self.roadmap)
        self.interrupt(point="intent only", future_plan_change=True)
        before = self.record_bytes()

        self.assertRefused(before, self.add, {"y": PhaseSpec("Y", "別の状態"), "z": PhaseSpec("Z", "Z が成立する")},
                           (), future_plan_change=False)

    def test_a_legacy_record_is_left_for_reconciliation(self) -> None:
        pending = self.interrupt()

        self.assertLegacyRefused(pending, self.add)


# --------------------------------------------------------------------------- related maintenance
class RelatedMaintenanceBindingTests(BindingCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        roadmap = self.simple_roadmap(self.store)
        entry = self.simple_entry(self.store, roadmap.phase_ids["a"])
        self.work = entry.work_ids["w1"]
        for name in ("a.md", "b.md", "c.md"):
            (self.store.root / name).write_text(f"{name}\n", encoding="utf-8")

    def maintain(self, add=(), remove=(), **kwargs):
        return rm.maintain_work_related(self.store, self.work, add=add, remove_relation_ids=remove, **kwargs)

    def interrupt(self, add=(), remove=(), *, point: str = "recorded", **kwargs) -> dict:
        points = {
            "intent only": lambda: self.before_effects(gitops, "ensure_git_ready"),
            "reserved": lambda: self.before_recording("related"),
            "recorded": lambda: self.after_recording("related"),
            "applied": lambda: self.before_effects(rm, "_finalize"),
        }
        with points[point]():
            with self.assertRaises(Interrupted):
                self.maintain(add, remove, **kwargs)
        return self.pending()

    def edges(self) -> list[tuple[str, str]]:
        view = ProjectView.load(self.store)
        return sorted((r.type, r.to) for r in view.related_from(self.work))

    # the recorded identity -------------------------------------------------
    def test_the_record_holds_the_request_structurally(self) -> None:
        pending = self.interrupt((RelatedSpec("must_read", "a.md"), RelatedSpec("obey", "b.md")))

        request = pending["invocation"]["request"]
        self.assertEqual(request["add"], [{"type": "must_read", "to": "a.md", "condition": None},
                                          {"type": "obey", "to": "b.md", "condition": None}])
        self.assertEqual(request["remove"], [])

    def test_the_printable_label_is_not_an_identity(self) -> None:
        """It joins caller text with separators it does not escape, so two requests spell one label."""
        collide = (RelatedSpec("must_read", "a: | +obey:b"),)
        apart = (RelatedSpec("must_read", "a"), RelatedSpec("obey", "b"))

        self.assertEqual(rm._related_request_key(collide, ()), rm._related_request_key(apart, ()))
        self.assertNotEqual(rm.related_request_identity(collide, ()), rm.related_request_identity(apart, ()))

    def test_a_colliding_label_is_refused_rather_than_resumed(self) -> None:
        self.interrupt((RelatedSpec("must_read", "a: | +obey:b"),))
        before = self.record_bytes()

        self.assertRefused(before, self.maintain, (RelatedSpec("must_read", "a"), RelatedSpec("obey", "b")))

    # request-local duplicates ----------------------------------------------
    def test_a_repeated_edge_is_the_same_request_as_one(self) -> None:
        edge = RelatedSpec("must_read", "a.md")
        pending = self.interrupt((edge, edge))

        result = self.maintain((edge,))

        self.assertEqual(result.mutation_id, pending["mutation_id"])
        self.assertEqual(self.edges(), [("must_read", "a.md")])

    def test_a_repeated_removal_is_the_same_request_as_one(self) -> None:
        existing = self.maintain((RelatedSpec("must_read", "a.md"),)).added[0]
        pending = self.interrupt(remove=(existing, existing))

        result = self.maintain(remove=(existing,))

        self.assertEqual(result.mutation_id, pending["mutation_id"])
        self.assertEqual(self.edges(), [])

    def test_a_repeated_edge_keeps_the_reservations_the_first_attempt_issued(self) -> None:
        """The reservation key is the position in the request, so the repeats must fold first."""
        e, f = RelatedSpec("must_read", "a.md"), RelatedSpec("obey", "b.md")
        pending = self.interrupt((e, e, f), point="reserved")
        reserved = dict(pending["reserved_ids"])
        self.assertEqual(sorted(reserved), ["related:add:0", "related:add:1"])

        result = self.maintain((e, f))

        self.assertEqual(result.mutation_id, pending["mutation_id"])
        self.assertEqual(sorted(result.added), sorted(reserved.values()))  # nothing stranded
        self.assertEqual(self.edges(), [("must_read", "a.md"), ("obey", "b.md")])

    # resume ----------------------------------------------------------------
    def test_the_same_request_carries_the_maintenance_forward(self) -> None:
        for point in ("intent only", "reserved", "recorded"):
            with self.subTest(point=point):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    add = (RelatedSpec("must_read", "a.md"),)
                    pending = case.interrupt(add, point=point)

                    result = case.maintain(add)

                    case.assertTrue(result.resumed)
                    case.assertEqual(result.mutation_id, pending["mutation_id"])
                    case.assertEqual(case.edges(), [("must_read", "a.md")])
                    case.assertEqual(validate_project(case.store), [])
                finally:
                    case.doCleanups()

    # refusal ---------------------------------------------------------------
    def test_a_different_add_under_one_label_is_refused(self) -> None:
        self.interrupt((RelatedSpec("must_read", "a.md"),), invocation_key="K")
        before = self.record_bytes()

        self.assertRefused(before, self.maintain, (RelatedSpec("must_read", "b.md"),), (), invocation_key="K")

        self.assertEqual(self.edges(), [])

    def test_a_subset_retry_is_refused_instead_of_reported_as_nothing_to_do(self) -> None:
        """The check runs before the no-op fast path, which never reaches the mutation."""
        both = (RelatedSpec("must_read", "a.md"), RelatedSpec("obey", "b.md"))
        self.interrupt(both, point="recorded", invocation_key="K")
        rm.maintain_work_related(self.store, self.work, add=both, remove_relation_ids=(), invocation_key="K")
        self.assertEqual(self.edges(), [("must_read", "a.md"), ("obey", "b.md")])
        self.interrupt((RelatedSpec("must_read", "c.md"),), invocation_key="K")
        before = self.record_bytes()

        self.assertRefused(before, self.maintain, (both[0],), (), invocation_key="K")

    def test_a_condition_that_differs_only_in_true_versus_one_is_refused(self) -> None:
        def add(flag: object) -> tuple[RelatedSpec, ...]:
            condition = {"kind": "path_glob", "pattern": "src/*.py", "recursive": flag}
            return (RelatedSpec("conditional_must_read", "a.md", condition),)

        self.interrupt(add(True), invocation_key="K")
        before = self.record_bytes()

        self.assertRefused(before, self.maintain, add(1), (), invocation_key="K")

    def test_a_legacy_record_under_the_unfolded_label_is_still_found(self) -> None:
        """Folding this request's repeats moves its default label, so the old one is searched too."""
        edge = RelatedSpec("must_read", "a.md")
        pending = self.interrupt((edge, edge), point="applied")
        self.assertEqual(pending["invocation"]["key"], rm._related_request_key((edge,), ()))
        # the edge is already there, so the retry would otherwise find nothing to do
        self.assertEqual(self.edges(), [("must_read", "a.md")])

        self.assertLegacyRefused(pending, self.maintain, (edge, edge),
                                 _key=rm._related_request_key((edge, edge), ()))

    def test_a_legacy_record_is_left_for_reconciliation(self) -> None:
        for key in (None, "K"):
            with self.subTest(label="default" if key is None else "explicit"):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    add = (RelatedSpec("must_read", "a.md"),)
                    extra = {} if key is None else {"invocation_key": key}
                    pending = case.interrupt(add, **extra)

                    case.assertLegacyRefused(pending, case.maintain, add, (), **extra)
                finally:
                    case.doCleanups()


# --------------------------------------------------------------------------- what stays as it was
class UnchangedOperationTests(BindingCase):
    """Operations whose mutation carries no caller-decided payload keep their behaviour."""

    def measure(self, name: str, exclude, setup, *, window: str) -> dict[str, object]:
        """Interrupt one plan exclusion, retry it with a different replan, and look."""
        self.store = self.new_project(name)
        target, replan_for, marks = setup(self.store)
        module = st if exclude is st.plan_exclude_standalone_work else rm
        points = {
            "intent only": lambda: self.before_effects(module, "plan_replan"),
            "event recorded": lambda: self.after_recording("event"),
        }
        with points[window]():
            with self.assertRaises(Interrupted):
                exclude(self.store, target, replan_for(0))
        pending = self.pending()

        exclude(self.store, target, replan_for(1))

        view = ProjectView.load(self.store)
        observed = {work.name for work in view.works.values()} | {
            f"{r.type}:{r.from_id}:{r.to}" for r in view.roadmap_relations
        }
        return {
            "status": MutationController(self.store).load(pending["mutation_id"]).status,
            "kept the retry's own content": marks[1] in observed,
            "kept nothing of the first": marks[0] not in observed,
            "problems": validate_project(self.store),
        }

    def test_the_plan_excludes_keep_their_measured_behaviour(self) -> None:
        """A retry takes the record over, but the store ends up holding the retry's own content.

        Nothing the first request decided survives, so this is not the defect
        BL-024 names, and these three operations are left exactly as they were.
        """
        def replacement_work(store, target):
            def replan_for(index: int) -> Replan:
                name = ("Replacement One", "Replacement Two")[index]
                return Replan(new_works={"n": WorkSpec(name, f"D{index + 1} state")})

            return target, replan_for, ("Replacement One", "Replacement Two")

        def standalone(store):
            return replacement_work(store, create_standalone_work(store, WorkSpec("Target", "t")).work_id)

        def phase(store):
            roadmap = self.simple_roadmap(store, {"a": ("Phase A", "A"), "b": ("Phase B", "B")})
            return replacement_work(store, roadmap.phase_ids["b"])

        def phase_work(store):
            """A Phase Work's replan corrects relations: a new Work registers before removals apply."""
            roadmap = self.simple_roadmap(store)
            entry = self.simple_entry(store, roadmap.phase_ids["a"], {"w1": "W1", "w2": "W2", "w3": "W3"})
            w1, w2, w3 = (entry.work_ids[key] for key in ("w1", "w2", "w3"))
            view = ProjectView.load(store)
            orphaned = tuple(r.id for r in view.roadmap_relations if w2 in (r.from_id, r.to))
            pairs = ((w1, w3), (w3, w1))

            def replan_for(index: int) -> Replan:
                return Replan(
                    remove_relation_ids=orphaned,
                    add_relations=(RelationSpec("requires_completion", *pairs[index]),),
                )

            return w2, replan_for, tuple(f"requires_completion:{a}:{b}" for a, b in pairs)

        cases = {
            "start-plan-exclude": (st.plan_exclude_standalone_work, standalone),
            "phase-plan-exclude": (rm.plan_exclude_phase, phase),
            "work-plan-exclude": (rm.plan_exclude_work, phase_work),
        }
        for index, (label, (exclude, setup)) in enumerate(cases.items()):
            for window in ("intent only", "event recorded"):
                with self.subTest(operation=label, window=window):
                    case = type(self)(self._testMethodName)
                    case.setUp()
                    try:
                        seen = case.measure(f"{index}-{window[0]}", exclude, setup, window=window)
                        case.assertEqual(seen["status"], "completed")
                        case.assertTrue(seen["kept the retry's own content"])
                        case.assertTrue(seen["kept nothing of the first"])
                        case.assertEqual(seen["problems"], [])
                    finally:
                        case.doCleanups()

    def test_start_still_decides_per_attempt(self) -> None:
        """START's decisions belong to the attempt, not to one bound mutation."""
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        work = self.simple_entry(store, roadmap.phase_ids["a"]).work_ids["w1"]

        waiting = st.start(store, work, "single-work", scripted_executor({work: [st.QuestionWait("which colour?")]}))
        finished = st.start(store, work, "single-work", completing_executor(store))

        self.assertEqual(waiting.status, "question_wait")
        # The second attempt decides something else and carries the same
        # mutation forward: binding an attempt's outcome into the invocation
        # would have refused exactly this.
        self.assertEqual(finished.mutation_id, waiting.mutation_id)
        self.assertEqual(finished.status, "completed")
        self.assertEqual(validate_project(store), [])


if __name__ == "__main__":
    unittest.main()
