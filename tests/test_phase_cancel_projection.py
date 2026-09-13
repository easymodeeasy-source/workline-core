"""A Phase cancel that would leave the plan unreplanned is refused before it writes (BL-026).

Cancelling a Phase appends one lifecycle event and then commits and pushes it. A
cancelled Phase never completes, so a Phase that still requires its completion -
or still plans to return to it - is left unreplanned (``dependency_unreplanned``,
``return_to_unreplanned``). Structural validation found that only in the
postcheck, which runs after the commit and the push: the cancellation reached
the remote first and was refused afterwards, its mutation stayed pending, and
every operation then stopped on the structure it had published.

The cancellation is now projected onto the state the request meets and checked
by the same structural validation before any mutation is opened, the way plan
exclusion and a Work cancel already check theirs. What that refuses is exactly
what the postcheck used to find after publishing; a cancel nothing waits for goes
the way it always went, and an interrupted cancel still carries its own mutation
to the end (BL-025).
"""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import completing_executor
from test_lifecycle_resume import STILL_TO_RUN, WINDOWS, Interrupted, LifecycleCase, before
from workline import roadmap as rm
from workline import start as st
from workline.errors import SpecViolation, ValidationError
from workline.mutation import MutationController
from workline.ops import Replan
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.state import ProjectView
from workline.validate import validate_project, validate_structure

PROJECTION_REFUSAL = "phase cancel: structure would be invalid: "

# Interrupted once the mutation exists and before it has decided its event.
RESUME_WINDOWS = {"intent": lambda: before(rm, "event_effects"), **WINDOWS}
RESUME_STILL_TO_RUN = {"intent": ["append_event", "git_commit", "git_push"], **STILL_TO_RUN}


class CancelCase(LifecycleCase):
    def plan(self, phases: str = "ab", relations=(), name: str = "proj") -> rm.RoadmapResult:
        """A Project with one Roadmap of Phases named by ``phases``; relations use those keys."""
        self.name = name
        self.store = self.new_project(name, remote=True)
        roadmap = self.simple_roadmap(self.store, {key: (f"Phase {key.upper()}", key.upper()) for key in phases}, relations)
        self.rid = roadmap.roadmap_id
        self.phase = dict(roadmap.phase_ids)
        return roadmap

    def relation(self, rel_type: str, a: str, b: str) -> str:
        (found,) = [
            r.id for r in ProjectView.load(self.store).roadmap_relations
            if (r.type, r.from_id, r.to) == (rel_type, self.phase[a], self.phase[b])
        ]
        return found

    def complete(self, key: str) -> None:
        entry = self.simple_entry(self.store, self.phase[key])
        self.assertEqual(st.start(self.store, entry.entry_work_id, "outer", completing_executor(self.store)).status, "phase_complete")

    def watched(self, call):
        """Run ``call``; report every mutation it began and every effect it executed, and its refusal."""
        began: list[dict] = []
        executed: list[str] = []
        real_begin, real_apply = MutationController.begin, MutationController.apply_effect

        def begin(controller, owner, invocation, scope):
            began.append(invocation)
            return real_begin(controller, owner, invocation, scope)

        def apply_effect(controller, record):
            executed.append(record["kind"])
            return real_apply(controller, record)

        refusal = None
        with mock.patch.object(MutationController, "begin", begin), \
                mock.patch.object(MutationController, "apply_effect", apply_effect):
            try:
                call()
            except SpecViolation as exc:
                refusal = exc
        return refusal, began, executed

    def assertRefusedBeforeWriting(self, key: str) -> SpecViolation:
        """Cancelling ``key`` is refused with nothing opened, applied, committed or pushed."""
        before_refusal = self.snapshot()
        lifecycle = self.lifecycle(self.phase[key])

        refusal, began, executed = self.watched(lambda: rm.cancel_phase(self.store, self.phase[key]))

        self.assertIsNotNone(refusal, "the cancel was not refused")
        self.assertEqual(refusal.code, "spec_violation")
        self.assertTrue(str(refusal).startswith(PROJECTION_REFUSAL), str(refusal))
        self.assertEqual(began, [])  # no recovery record, not even an abandoned one
        self.assertEqual(executed, [])
        self.assertEqual(self.snapshot(), before_refusal)  # event log, records, HEAD and remote
        self.assertEqual(self.lifecycle(self.phase[key]), lifecycle)
        self.assertEqual(self.events_of(self.phase[key], "phase_cancelled"), [])
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(self.dirty(), [])
        return refusal

    def assertCancelled(self, key: str) -> None:
        """Cancelling ``key`` goes the way it always went: one event, one commit, pushed, nothing left."""
        refusal, began, executed = self.watched(lambda: rm.cancel_phase(self.store, self.phase[key]))

        self.assertIsNone(refusal)
        self.assertEqual(began, [{"entity": self.phase[key], "operation": "phase-cancel"}])
        self.assertEqual(executed, ["append_event", "git_commit", "git_push"])
        self.assertEqual(self.lifecycle(self.phase[key]), "cancelled")
        self.assertEqual(len(self.events_of(self.phase[key], "phase_cancelled")), 1)
        self.assertEqual(self.subjects()[0], f"chore(workline): phase_cancelled {self.phase[key]}")
        self.assertEqual(self.head(), self.remote_head())
        self.assertEqual(MutationController(self.store).list_records(), [])  # completed and cleaned up (BL-019)
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(self.dirty(), [])


# --------------------------------------------------------------------------- refused before it writes
class UnreplannedCancelTests(CancelCase):
    def test_a_phase_another_still_requires_is_refused_before_anything_is_written(self) -> None:
        self.plan("ab", [("requires_completion", "a", "b")])
        a, b = self.phase["a"], self.phase["b"]

        refusal = self.assertRefusedBeforeWriting("a")

        self.assertEqual(
            str(refusal),
            PROJECTION_REFUSAL + f"{self.relation('requires_completion', 'a', 'b')}: requires_completion predecessor {a} is cancelled",
        )
        # Nothing was published, so nothing stands in the way of the next operation.
        view = ProjectView.load(self.store)
        self.assertEqual(view.phase_state(b), "unstarted")
        self.assertEqual([p.id for p in view.startable_phases(self.rid)], [a])
        self.assertEqual(rm.hold_phase(self.store, b).status, "phase_held")
        self.assertEqual(validate_project(self.store), [])

    def test_the_successor_waits_whatever_state_it_or_its_predecessor_is_in(self) -> None:
        cases = {
            "successor held": lambda: rm.hold_phase(self.store, self.phase["b"]),
            "predecessor held": lambda: rm.hold_phase(self.store, self.phase["a"]),
            "predecessor and successor complete": lambda: (self.complete("a"), self.complete("b")),
        }
        for index, (label, arrange) in enumerate(cases.items()):
            with self.subTest(label):
                self.plan("ab", [("requires_completion", "a", "b")], name=f"state-{index}")
                arrange()
                self.assertRefusedBeforeWriting("a")

    def test_a_phase_another_plans_to_return_to_is_refused(self) -> None:
        self.plan("ab", [("return_to", "b", "a")])

        refusal = self.assertRefusedBeforeWriting("a")

        self.assertIn(f"{self.relation('return_to', 'b', 'a')}: return_to target {self.phase['a']} is cancelled", str(refusal))

    def test_every_waiting_phase_is_named_in_one_refusal(self) -> None:
        self.plan("abc", [("requires_completion", "a", "b"), ("requires_completion", "a", "c")])

        refusal = self.assertRefusedBeforeWriting("a")

        self.assertIn(self.relation("requires_completion", "a", "b"), str(refusal))
        self.assertIn(self.relation("requires_completion", "a", "c"), str(refusal))

    def test_a_successor_in_another_roadmap_still_waits(self) -> None:
        self.plan("a")
        other = rm.create_roadmap(self.store, rm.RoadmapPlan(
            "Other", "背景", "達成したい状態", {"x": PhaseSpec("Phase X", "X")},
            (PhaseRelationSpec("requires_completion", self.phase["a"], "x"),),
        ))

        self.assertRefusedBeforeWriting("a")

        self.assertEqual(rm.hold_phase(self.store, other.phase_ids["x"]).status, "phase_held")

    def test_it_refuses_exactly_what_the_postcheck_found_after_publishing(self) -> None:
        """The projection is the canonical validation, not a rule of its own.

        In the same Project, the cancel is first asked for as it is now, and then
        the way it ran before, without the projection: that run publishes the
        cancellation and its postcheck reports the problems the refusal named.
        """
        structures = {
            "requires_completion": ("ab", [("requires_completion", "a", "b")]),
            "return_to": ("ab", [("return_to", "b", "a")]),
            "both, and two successors": ("abc", [("requires_completion", "a", "b"), ("return_to", "c", "a"),
                                                 ("requires_completion", "a", "c")]),
        }
        for index, (label, (phases, relations)) in enumerate(structures.items()):
            with self.subTest(label):
                self.plan(phases, relations, name=f"same-{index}")
                refusal = self.assertRefusedBeforeWriting("a")

                with mock.patch.object(rm, "validate_projection", lambda *args, **kwargs: None):
                    with self.assertRaises(ValidationError) as published:
                        rm.cancel_phase(self.store, self.phase["a"])

                self.assertEqual(published.exception.code, "structure_invalid")
                self.assertTrue(str(published.exception).startswith("postcheck: "))
                self.assertEqual(self.head(), self.remote_head())  # what the refusal now prevents
                problems = validate_structure(ProjectView.load(self.store))
                self.assertEqual(str(refusal), PROJECTION_REFUSAL + "; ".join(p.message for p in problems))


# --------------------------------------------------------------------------- still cancelled
class CancelStillProceedsTests(CancelCase):
    def test_a_phase_nothing_waits_for_is_cancelled_as_before(self) -> None:
        structures = {
            "no relation": [],
            "only a successor itself": [("requires_completion", "b", "a")],
            "only planned_next": [("planned_next", "a", "b")],
            "the one returning": [("return_to", "a", "b")],
        }
        for index, (label, relations) in enumerate(structures.items()):
            with self.subTest(label):
                self.plan("ab", relations, name=f"free-{index}")
                self.assertCancelled("a")

    def test_a_held_or_complete_phase_nothing_waits_for_is_cancelled(self) -> None:
        cases = {
            "held": lambda: rm.hold_phase(self.store, self.phase["a"]),
            "complete": lambda: self.complete("a"),
        }
        for index, (label, arrange) in enumerate(cases.items()):
            with self.subTest(label):
                self.plan("ab", name=f"ended-{index}")
                arrange()
                self.assertCancelled("a")

    def test_a_successor_already_out_of_the_plan_holds_nothing_back(self) -> None:
        for index, exclude in enumerate(("cancel", "plan exclusion")):
            with self.subTest(exclude):
                self.plan("ab", [("requires_completion", "a", "b"), ("return_to", "b", "a")], name=f"out-{index}")
                if exclude == "cancel":
                    self.assertCancelled("b")
                else:
                    rm.plan_exclude_phase(self.store, self.phase["b"])
                self.assertCancelled("a")

    def test_replanning_the_dependency_first_lets_the_cancel_through(self) -> None:
        self.plan("abc", [("requires_completion", "a", "b")])
        self.assertRefusedBeforeWriting("a")

        rm.plan_exclude_phase(self.store, self.phase["c"], Replan(remove_relation_ids=(self.relation("requires_completion", "a", "b"),)))

        self.assertCancelled("a")
        self.assertEqual(ProjectView.load(self.store).phase_state(self.phase["b"]), "unstarted")

    def test_only_the_phases_still_waiting_matter(self) -> None:
        self.plan("abc", [("requires_completion", "a", "b"), ("requires_completion", "a", "c")])
        self.assertCancelled("b")
        self.assertRefusedBeforeWriting("a")  # c still waits
        self.assertCancelled("c")
        self.assertCancelled("a")

    def test_a_dependency_in_another_roadmap_does_not_stop_it(self) -> None:
        self.plan("a")
        rm.create_roadmap(self.store, rm.RoadmapPlan(
            "Other", "背景", "達成したい状態", {"x": PhaseSpec("Phase X", "X"), "y": PhaseSpec("Phase Y", "Y")},
            (PhaseRelationSpec("requires_completion", "x", "y"),),
        ))

        self.assertCancelled("a")

    def test_an_already_terminal_phase_is_refused_as_before(self) -> None:
        """The terminal precondition answers first: a second terminal event is not reported as structure."""
        self.plan("abc", [("requires_completion", "a", "c"), ("requires_completion", "b", "c")])
        self.assertCancelled("c")
        self.assertCancelled("a")
        rm.plan_exclude_phase(self.store, self.phase["b"])

        for key in "ab":
            with self.subTest(key):
                before_refusal = self.snapshot()
                refusal, began, executed = self.watched(lambda: rm.cancel_phase(self.store, self.phase[key]))
                self.assertEqual(str(refusal), f"Phase {self.phase[key]} already terminal")
                self.assertEqual((began, executed), ([], []))
                self.assertEqual(self.snapshot(), before_refusal)


# --------------------------------------------------------------------------- an interrupted cancel
class InterruptedCancelTests(CancelCase):
    def test_an_interrupted_cancel_still_resumes_from_every_window(self) -> None:
        """Projected once, from the state without its own event: a retry never refuses itself (BL-025)."""
        for index, window in enumerate(RESUME_WINDOWS):
            with self.subTest(window=window):
                self.plan("ab", [("requires_completion", "a", "b"), ("return_to", "b", "a")], name=f"resume-{index}")
                rm.plan_exclude_phase(self.store, self.phase["b"])
                with RESUME_WINDOWS[window]():
                    with self.assertRaises(Interrupted):
                        rm.cancel_phase(self.store, self.phase["a"])
                (pending,) = MutationController(self.store).list_pending()

                result, executed = self.run_counting_effects(lambda: rm.cancel_phase(self.store, self.phase["a"]))

                self.assertEqual(executed, RESUME_STILL_TO_RUN[window])
                if window == "intent":
                    # Nothing was reserved before the event was decided; the retry reserves exactly that.
                    (record,) = MutationController(self.store).list_records()
                    self.assertEqual(pending["reserved_ids"], {})
                    self.assertEqual(list(record["reserved_ids"]), ["event:event:0"])
                    pending = {**pending, "reserved_ids": record["reserved_ids"]}
                self.assertCarriedToTheEnd(pending, result, self.phase["a"], "phase_cancelled")

    def test_a_retry_is_refused_before_it_applies_what_has_become_unreplanned(self) -> None:
        """A Phase added meanwhile requires the one being cancelled: the recorded event is not applied."""
        for index, window in enumerate(("intent", "event recorded")):
            with self.subTest(window=window):
                self.plan("a", name=f"meanwhile-{index}")
                with RESUME_WINDOWS[window]():
                    with self.assertRaises(Interrupted):
                        rm.cancel_phase(self.store, self.phase["a"])
                (pending,) = MutationController(self.store).list_pending()
                # Phase addition writes only Roadmap relations, so the unfinished cancel does not stop it.
                rm.add_phases(self.store, self.rid, {"c": PhaseSpec("Phase C", "C")},
                              (PhaseRelationSpec("requires_completion", self.phase["a"], "c"),))
                before_refusal = self.snapshot()

                refusal, began, executed = self.watched(lambda: rm.cancel_phase(self.store, self.phase["a"]))

                self.assertIsNotNone(refusal)
                self.assertTrue(str(refusal).startswith(PROJECTION_REFUSAL), str(refusal))
                self.assertEqual((began, executed), ([], []))
                self.assertEqual(self.snapshot(), before_refusal)  # the record is left exactly as it was
                self.assertEqual(self.lifecycle(self.phase["a"]), "active")
                self.assertEqual([p["mutation_id"] for p in MutationController(self.store).list_pending()],
                                 [pending["mutation_id"]])
                self.assertEqual(validate_project(self.store), [])

    def test_a_cancel_already_published_is_left_for_reconciliation(self) -> None:
        """What the earlier implementation published is not repaired, and not written over."""
        self.plan("ab", [("requires_completion", "a", "b")])
        with mock.patch.object(rm, "validate_projection", lambda *args, **kwargs: None):
            with self.assertRaises(ValidationError):
                rm.cancel_phase(self.store, self.phase["a"])
        (pending,) = MutationController(self.store).list_pending()
        before_refusal = self.snapshot()

        with self.assertRaises(ValidationError) as raised:
            rm.cancel_phase(self.store, self.phase["a"])

        self.assertEqual(raised.exception.code, "structure_invalid")
        self.assertTrue(str(raised.exception).startswith("precheck: dependency_unreplanned: "))
        self.assertEqual(self.snapshot(), before_refusal)
        self.assertEqual([p["mutation_id"] for p in MutationController(self.store).list_pending()], [pending["mutation_id"]])

    def test_a_refused_cancel_leaves_another_unfinished_mutation_to_finish(self) -> None:
        cases = {
            "a hold of the same Phase": ("ab", [("requires_completion", "a", "b")], "a",
                                         lambda: rm.hold_phase(self.store, self.phase["a"]), "phase_held"),
            "a cancel of another Phase": ("abc", [("requires_completion", "b", "c")], "b",
                                          lambda: rm.cancel_phase(self.store, self.phase["a"]), "phase_cancelled"),
        }
        for index, (label, (phases, relations, refused, unfinished, event_type)) in enumerate(cases.items()):
            with self.subTest(label):
                self.plan(phases, relations, name=f"other-{index}")
                pending = self.interrupt(unfinished, "event applied")
                before_refusal = self.snapshot()

                refusal, began, executed = self.watched(lambda: rm.cancel_phase(self.store, self.phase[refused]))

                self.assertIsNotNone(refusal)
                self.assertTrue(str(refusal).startswith(PROJECTION_REFUSAL), str(refusal))
                self.assertEqual((began, executed), ([], []))
                self.assertEqual(self.snapshot(), before_refusal)

                result = unfinished()
                self.assertCarriedToTheEnd(pending, result, self.phase["a"], event_type)


if __name__ == "__main__":
    unittest.main()
