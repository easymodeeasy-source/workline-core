"""RB1 §29.28 / §29.13: current and next are the existing selection semantics, projected - never a new algorithm.

The Work continuation status reports is :func:`workline.selection.work_continuation`,
and START's same-Phase continuation (``start._Session.next_work``) calls that
same function (B-H1). :class:`HelperAgreesWithStartTests` proves both halves:
the call path (START and status hold the one function object, and
``next_work`` hands it exactly its scope and returns its ``choose()``), and
the semantics (helper, START and a verbatim copy of START's pre-B-H1
continuation body give the same answer - Work or STOP code and message - on
every fixture). The Phase selection is Roadmap's own
(:meth:`ProjectView.startable_phases` + ``planned_next`` preference), checked
against ``roadmap.select_phase``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import inspect
import random
import re
import tempfile
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor
from status_helpers import StatusCase, add_roadmap_relation, append_events
from workline import roadmap as rm
from workline import selection
from workline import start as st
from workline import status
from workline.errors import StopError
from workline.mutation import MutationController, WriteScope
from workline.oplock import project_operation
from workline.phase_create import PhaseSpec
from workline.state import IN_PROGRESS, ProjectView
from workline.store import Entity, Event, ProjectStore, Relation, render_relations

LEDGERS = (".workline/events/events.jsonl", ".workline/relations/roadmap.yaml", ".workline/relations/related.yaml")


# --------------------------------------------------------------------------- the helper is START's calculation


def reference_next_work(view: ProjectView, phase_id: str | None, entry: Entity) -> Entity | None:
    """START's continuation as ``start._Session.next_work`` computed it at 5a09d82, before B-H1 - verbatim, frozen.

    The oracle the shared helper must keep agreeing with: B-H1 moved this
    calculation behind :func:`workline.selection.work_continuation` and must not
    have changed what it answers.
    """
    works = view.effective_works(phase_id) if phase_id else st.standalone_scope(view, entry.id)
    inflight = [w for w in works if view.work_state(w.id).state == IN_PROGRESS and view.work_state(w.id).has_target]
    if len(inflight) > 1:
        raise StopError("multiple Works carry a target: " + ", ".join(w.id for w in inflight), code="multiple_targets")
    if inflight:
        return inflight[0]
    startable = view.startable_works(phase_id, works if phase_id is None else None)
    # a Work that a still-active branch plans to return to waits for that branch
    pending_returns = {
        r.to for r in view.roadmap_relations
        if r.type == "return_to" and r.from_id in view.works and not view.work_state(r.from_id).terminal
    }
    startable = [w for w in startable if w.id not in pending_returns] or startable
    # The plan decides which Work comes next. When it leaves several equally
    # planned, the continuation STOPs instead of separating them by the order
    # they were read in.
    return view.choose_startable(startable, "Work")


def outcome(call):
    try:
        found = call()
    except StopError as exc:
        return ("stop", exc.code, str(exc))
    return ("work", None if found is None else found.id)


_SEQUENCES = (
    (),
    ("work_started",),
    ("work_started", "work_target_added"),
    ("work_started", "work_held"),
    ("work_started", "work_target_added", "work_target_removed"),
    ("work_started", "work_target_added", "work_target_removed", "work_completed"),
    ("work_cancelled",),
    ("plan_excluded",),
    ("work_started", "work_held", "work_resumed"),
)


class HelperAgreesWithStartTests(unittest.TestCase):
    """B-H1 guard: START calls the shared helper, and the helper answers what START's own continuation answered."""

    PHASE = "p_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    ROADMAP = "r_01ARZ3NDEKTSV4RRFFQ69G5FAV"

    def setUp(self) -> None:
        self.store = ProjectStore(Path(tempfile.gettempdir()) / "never-read")

    def view(self, works, relations=(), events=(), *, phase_events=()) -> ProjectView:
        view = ProjectView(self.store)
        view.roadmaps = {self.ROADMAP: Entity(self.ROADMAP, "roadmap", {"id": self.ROADMAP, "display": "R-1"}, "# R\n", "")}
        view.phases = {
            self.PHASE: Entity(self.PHASE, "phase", {"id": self.PHASE, "display": "P-1", "roadmap_id": self.ROADMAP}, "# P\n", "")
        }
        view.works = {
            work_id: Entity(work_id, "work", {"id": work_id, "display": f"W-{n}", "phase_id": phase, "work_kind": kind},
                            f"# {work_id}\n", "")
            for n, (work_id, phase, kind) in enumerate(works)
        }
        view.works = dict(sorted(view.works.items()))
        view.roadmap_relations = [Relation(f"rel_{n:04d}", t, a, b) for n, (t, a, b) in enumerate(relations)]
        view.events = [Event(f"evt_{n:04d}", t, e, "at") for n, (t, e) in enumerate(list(phase_events) + list(events))]
        return view

    def agree(self, view: ProjectView, phase_id: str | None, entry: str) -> tuple:
        entity = view.works[entry]
        works = view.effective_works(phase_id) if phase_id else st.standalone_scope(view, entry)
        continuation = selection.work_continuation(view, phase_id, works)
        start_says = outcome(lambda: st._Session.next_work(None, view, phase_id, entity, None))  # START's call path
        reference_says = outcome(lambda: reference_next_work(view, phase_id, entity))  # START before B-H1, frozen
        helper_says = outcome(continuation.choose)
        self.assertEqual(reference_says, start_says)
        self.assertEqual(helper_says, start_says)
        selected = continuation.selected
        self.assertEqual(None if start_says[0] == "stop" else start_says[1], None if selected is None else selected.id)
        return start_says

    # ------------------------------------------------------------------ the call path
    def test_start_and_status_hold_the_one_helper(self) -> None:
        from workline import status

        self.assertIs(st.work_continuation, selection.work_continuation)
        self.assertIs(status.work_continuation, selection.work_continuation)
        source = inspect.getsource(st._Session.next_work)
        self.assertIn("work_continuation(view, phase_id, works).choose()", source)
        for copied in ("pending_returns", "choose_startable", "startable_works", "has_target"):
            with self.subTest(copied=copied):
                self.assertNotIn(copied, source, "START no longer computes the continuation itself")

    def test_next_work_hands_the_helper_its_scope_and_returns_its_choice(self) -> None:
        a, b, c = self.ids(3)
        cases = (
            (self.view([(a, self.PHASE, None), (b, self.PHASE, None)], [("planned_next", a, b)]), self.PHASE, a),
            (self.view([(a, None, None), (b, None, None), (c, None, None)], [("planned_next", a, b)]), None, b),
        )
        for view, phase_id, entry in cases:
            with self.subTest(phase_id=phase_id):
                calls = []
                real = selection.work_continuation

                def spy(view_, phase_, works_):
                    found = real(view_, phase_, works_)
                    calls.append((view_, phase_, [w.id for w in works_], found))
                    return found

                with mock.patch.object(st, "work_continuation", spy):
                    answer = st._Session.next_work(None, view, phase_id, view.works[entry], None)
                expected_scope = view.effective_works(phase_id) if phase_id else st.standalone_scope(view, entry)
                self.assertEqual(len(calls), 1, "next_work asks the shared helper exactly once")
                seen_view, seen_phase, seen_scope, continuation = calls[0]
                self.assertIs(seen_view, view)
                self.assertEqual(seen_phase, phase_id)
                self.assertEqual(seen_scope, [w.id for w in expected_scope])
                self.assertIs(answer, continuation.choose())

    def ids(self, count: int, prefix: str = "w_01ARZ3NDEKTSV4RRFFQ69G5F") -> list[str]:
        alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
        return [prefix + alphabet[n // 32] + alphabet[n % 32] for n in range(count)]

    def test_representative_fixtures(self) -> None:
        a, b, c, d = self.ids(4)
        p = self.PHASE
        in_phase = [(w, p, None) for w in (a, b, c)]
        cases = {
            "three equal": (in_phase, [], []),
            "planned after a finished one": (in_phase, [("planned_next", a, b)],
                                             [("work_started", a), ("work_target_added", a), ("work_target_removed", a),
                                              ("work_completed", a)]),
            "one in flight": (in_phase, [], [("work_started", b), ("work_target_added", b)]),
            "two in flight": (in_phase, [], [("work_started", a), ("work_target_added", a), ("work_started", c),
                                             ("work_target_added", c)]),
            "return_to waits": (in_phase + [(d, p, None)], [("return_to", a, b), ("planned_next", c, d)],
                                [("work_started", a), ("work_held", a)]),
            "return_to leaves nothing else": (in_phase[:2], [("return_to", a, b)], [("work_started", a), ("work_held", a)]),
            "dependency blocks": (in_phase, [("requires_completion", a, b), ("requires_completion", a, c)], []),
            "in progress without target": (in_phase, [("planned_next", b, a)], [("work_started", a)]),
            "nothing startable": (in_phase, [], [(t, w) for w in (a, b, c) for t in ("work_cancelled",)]),
            "cancelled predecessor holds nothing": (in_phase, [("planned_next", a, b)],
                                                    [("work_cancelled", a), ("work_cancelled", c)]),
            "integration last": ([(a, p, None), (b, p, "phase_integration_check")], [("requires_completion", a, b)], []),
        }
        for name, (works, relations, events) in cases.items():
            with self.subTest(name):
                self.agree(self.view(works, relations, events), p, works[0][0])
        held = self.view(in_phase, [], [], phase_events=[("phase_held", p)])
        self.assertEqual(self.agree(held, p, a), ("work", None))

    def test_standalone_scope(self) -> None:
        a, b, c = self.ids(3)
        works = [(a, None, None), (b, None, None), (c, None, None)]
        for relations in ([], [("planned_next", a, b)], [("planned_next", a, b), ("requires_completion", b, c)]):
            with self.subTest(relations=relations):
                for entry in (a, b, c):
                    self.agree(self.view(works, relations, []), None, entry)

    def test_seeded_random_fixtures(self) -> None:
        generator = random.Random(20261003)
        for case in range(400):
            count = generator.randint(1, 5)
            work_ids = self.ids(count)
            generator.shuffle(work_ids)
            works = [(w, self.PHASE, "phase_integration_check" if n == count - 1 and generator.random() < 0.3 else None)
                     for n, w in enumerate(work_ids)]
            events = []
            for w in work_ids:
                events += [(t, w) for t in generator.choice(_SEQUENCES)]
            relations = []
            for i, first in enumerate(work_ids):
                for second in work_ids[i + 1:]:
                    roll = generator.random()
                    if roll < 0.2:
                        relations.append(("planned_next", first, second))
                    elif roll < 0.3:
                        relations.append(("planned_next", second, first))
                    elif roll < 0.4:
                        relations.append(("requires_completion", first, second))
                    elif roll < 0.5:
                        relations.append(("return_to", first, second))
            phase_events = [("phase_held", self.PHASE)] if generator.random() < 0.05 else []
            view = self.view(works, relations, events, phase_events=phase_events)
            with self.subTest(case=case):
                self.agree(view, self.PHASE, work_ids[0])


# --------------------------------------------------------------------------- status on real Projects


class LifecycleStatusTests(StatusCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def phase_with_works(self, works=("w1", "w2"), **kwargs):
        self.roadmap = self.simple_roadmap(self.store)
        self.phase = self.roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, self.phase, {key: f"{key} done" for key in works}, **kwargs)
        return entry.work_ids

    def start_view(self) -> ProjectView:
        return ProjectView.load(self.store)

    def lifecycle(self) -> dict:
        data = self.data()
        self.assertEqual(data["lifecycle"]["status"], "available", data["lifecycle"])
        return data["lifecycle"]

    def test_a_unique_active_roadmap_and_no_started_phase(self) -> None:
        works = self.phase_with_works()
        life = self.lifecycle()
        self.assertEqual(life["current"]["roadmap"]["id"], self.roadmap.roadmap_id)
        self.assertEqual((life["current"]["phase"]["id"], life["current"]["phase"]["reason"]), (None, "no_started_phase"))
        self.assertEqual(life["next"]["phase"]["id"], self.phase, "the one startable Phase, as Roadmap selects it")
        self.assertEqual(rm.select_phase(self.store, self.roadmap.roadmap_id).id, self.phase)
        self.assertEqual((life["next"]["work"]["id"], life["next"]["work"]["reason"]), (None, "no_started_phase"))
        self.assertEqual(life["works"], [], "no Phase is current, so no Work scope is established")
        self.assertEqual(set(works), {"w1", "w2"}, "the Works exist all the same")

    def test_multiple_active_roadmaps_are_an_ambiguity(self) -> None:
        first = self.simple_roadmap(self.store)
        second = rm.create_roadmap(self.store, rm.RoadmapPlan(
            "Second Roadmap", "背景", "もう一つの達成したい状態", {"x": PhaseSpec("Phase X", "X が成立する")}
        ))
        life = self.lifecycle()
        current = life["current"]["roadmap"]
        self.assertEqual((current["id"], current["reason"]), (None, "multiple_active_roadmaps"))
        self.assertEqual(current["candidates"], sorted([first.roadmap_id, second.roadmap_id]))
        self.assertEqual(life["current"]["phase"]["reason"], "no_unique_roadmap")
        self.assertIn("multiple_active_roadmaps", [b["code"] for b in life["blockers"]])

    def test_a_unique_started_phase_and_one_in_flight_work(self) -> None:
        works = self.phase_with_works()
        append_events(self.store, ("work_started", works["w1"]), ("work_target_added", works["w1"]))
        life = self.lifecycle()
        self.assertEqual(life["current"]["phase"]["id"], self.phase)
        self.assertEqual(life["current"]["work"]["id"], works["w1"])
        self.assertEqual((life["next"]["work"]["id"], life["next"]["work"]["basis"]), (works["w1"], "in_flight"))

    def test_multiple_started_phases_are_an_ambiguity(self) -> None:
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A が成立する"), "b": ("Phase B", "B が成立する")})
        first = self.simple_entry(self.store, roadmap.phase_ids["a"]).work_ids["w1"]
        second = self.simple_entry(self.store, roadmap.phase_ids["b"]).work_ids["w1"]
        append_events(self.store, ("work_started", first), ("work_started", second))
        life = self.lifecycle()
        phase = life["current"]["phase"]
        self.assertEqual((phase["id"], phase["reason"]), (None, "multiple_started_phases"))
        self.assertEqual(phase["candidates"], sorted(roadmap.phase_ids.values()))
        self.assertEqual(life["current"]["work"]["reason"], "multiple_started_phases")

    def test_multiple_target_works_are_a_blocker(self) -> None:
        works = self.phase_with_works()
        append_events(self.store, ("work_started", works["w1"]), ("work_target_added", works["w1"]),
                      ("work_started", works["w2"]), ("work_target_added", works["w2"]))
        life = self.lifecycle()
        self.assertEqual((life["current"]["work"]["id"], life["current"]["work"]["reason"]), (None, "multiple_targets"))
        self.assertEqual(life["current"]["work"]["candidates"], sorted([works["w1"], works["w2"]]))
        self.assertEqual(life["next"]["work"]["id"], None)
        self.assertIn({"code": "multiple_targets", "ids": sorted([works["w1"], works["w2"]])}, life["blockers"])

    def test_work_continuation_exactly_matches_start(self) -> None:
        """return_to and planned_next filtering: status names exactly what START's continuation names."""
        works = self.phase_with_works(("w1", "w2", "w3", "w4"), entry="w1")
        append_events(self.store, ("work_started", works["w1"]), ("work_held", works["w1"]))
        add_roadmap_relation(self.store, "return_to", works["w1"], works["w2"])
        add_roadmap_relation(self.store, "planned_next", works["w3"], works["w4"])
        life = self.lifecycle()
        view = self.start_view()
        expected = st._Session.next_work(None, view, self.phase, view.works[works["w1"]], None)
        self.assertEqual(life["next"]["work"]["id"], expected.id)
        self.assertEqual(life["next"]["work"]["id"], works["w3"])
        self.assertNotIn(works["w2"], life["next"]["work"]["candidates"], "a Work a live branch returns to waits")

    def test_ambiguous_work_candidates_are_returned_not_guessed(self) -> None:
        works = self.phase_with_works(("w1", "w2", "w3"), entry="w1")
        append_events(self.store, ("work_started", works["w1"]))  # the Phase is started; nothing carries a target
        life = self.lifecycle()
        nxt = life["next"]["work"]
        view = self.start_view()
        with self.assertRaises(StopError) as raised:
            st._Session.next_work(None, view, self.phase, view.works[works["w1"]], None)
        self.assertEqual(raised.exception.code, "ambiguous_startable_candidates")
        self.assertEqual((nxt["id"], nxt["reason"]), (None, "ambiguous_startable_candidates"))
        self.assertEqual(nxt["preferred"], sorted(works[k] for k in ("w1", "w2", "w3")))

    def test_phase_preference_exactly_matches_roadmap(self) -> None:
        roadmap = self.simple_roadmap(
            self.store, {k: (k.upper(), f"{k} が成立する") for k in ("a", "b", "c")},
            relations=(("planned_next", "a", "b"),),
        )
        life = self.lifecycle()
        with self.assertRaises(StopError) as raised:
            rm.select_phase(self.store, roadmap.roadmap_id)
        self.assertEqual(raised.exception.code, "ambiguous_startable_candidates")
        self.assertEqual(life["next"]["phase"]["id"], None, "c is as recommended as a")
        self.assertEqual(life["next"]["phase"]["reason"], "ambiguous_startable_candidates")
        self.assertEqual(life["next"]["phase"]["preferred"], sorted([roadmap.phase_ids["a"], roadmap.phase_ids["c"]]))

    def test_phase_preference_names_the_head_roadmap_names(self) -> None:
        roadmap = self.simple_roadmap(
            self.store, {k: (k.upper(), f"{k} が成立する") for k in ("a", "b")},
            relations=(("planned_next", "a", "b"),),
        )
        life = self.lifecycle()
        self.assertEqual(life["next"]["phase"]["id"], rm.select_phase(self.store, roadmap.roadmap_id).id)
        self.assertEqual(life["next"]["phase"]["id"], roadmap.phase_ids["a"])

    def test_no_candidate_is_diagnosed(self) -> None:
        works = self.phase_with_works(("w1",))
        append_events(self.store, ("work_started", works["w1"]), ("work_held", works["w1"]))
        life = self.lifecycle()
        self.assertEqual((life["next"]["work"]["id"], life["next"]["work"]["reason"]), (None, "no_startable_work"))
        codes = {b["code"] for b in life["blockers"]}
        self.assertIn("work_held", codes)
        self.assertIn("dependency_unsatisfied", codes, "the integration waits for the held Work")

    def test_standalone_candidates_invent_no_implicit_entry(self) -> None:
        from workline.create import WorkSpec, create_standalone_work

        first = create_standalone_work(self.store, WorkSpec("Doc", "docs exist")).work_id
        second = create_standalone_work(self.store, WorkSpec("Other", "other exists")).work_id
        life = self.lifecycle()
        self.assertEqual(life["standalone"]["startable"], sorted([first, second]))
        self.assertEqual((life["standalone"]["selected"], life["standalone"]["reason"]),
                         (None, "standalone_requires_explicit_entry"))
        self.assertEqual(life["next"]["work"]["id"], None)

    def test_a_pending_progression_mutation_withholds_current_and_next(self) -> None:
        works = self.phase_with_works()
        append_events(self.store, ("work_started", works["w1"]), ("work_target_added", works["w1"]))
        with project_operation(self.store, "start", {}):
            mutation = MutationController(self.store).open(
                "start", {"operation": "start", "work_id": works["w1"], "mode": "single-work"},
                WriteScope(entities=(works["w1"],), files=LEDGERS),
            )
        life = self.lifecycle()
        for group, name in (("current", "roadmap"), ("current", "phase"), ("current", "work"), ("next", "phase"),
                            ("next", "work")):
            with self.subTest(f"{group}.{name}"):
                self.assertEqual(life[group][name]["id"], None)
                self.assertEqual(life[group][name]["reason"], "pending_mutation_unresolved")
        self.assertEqual(life["current"]["work"]["candidates"], [works["w1"]], "the observation stays")
        self.assertIn({"code": "pending_mutation_unresolved", "ids": [mutation.id]}, life["blockers"])

    def test_no_filename_mtime_or_record_order_changes_a_result(self) -> None:
        works = self.phase_with_works(("w1", "w2", "w3"), planned_next=(("w3", "w1"), ("w1", "w2")))
        append_events(self.store, ("work_started", works["w3"]), ("work_target_added", works["w3"]),
                      ("work_target_removed", works["w3"]), ("work_completed", works["w3"]))
        before = self.data()["lifecycle"]
        self.assertEqual(before["next"]["work"]["id"], works["w1"])
        for n, path in enumerate(sorted((self.store.root / ".workline").rglob("*.md"))):
            stamp = 1_600_000_000 + (997 * n) % 5000
            os.utime(path, (stamp, stamp))
        relations = self.store.read_roadmap_relations()
        self.assertGreater(len(relations), 2)
        self.store.roadmap_yaml.write_text(render_relations(list(reversed(relations))), encoding="utf-8", newline="")
        self.assertEqual(self.data()["lifecycle"], before)


if __name__ == "__main__":
    unittest.main()
