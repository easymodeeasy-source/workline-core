"""A valid replan's registration is judged on the structure the replan leaves (BL-028).

Plan exclusion and START's Work cancel decide a replan - relations to remove,
relations to add, Works to register - and project the whole result before the
terminal event is recorded. ``ops.apply_replan`` then applies it in stages: the
event, the new Works with the relations they carry, the removals, then the
commit and the push. The registration core checked the structure right after
applying its stage, while a relation the replan was about to remove still
pointed at the Work or Phase it had just excluded. A replan its owner had
accepted failed there: event and new Works applied, removals not, the mutation
pending, and every later structural precheck refusing the Project.

The registration now leaves the relations the replan has decided to remove out
of every structure check it makes. Nothing else moves: the stages keep their
names and their order, the removals are still applied after the registration, a
registration refused for any other reason is refused where and how it was, and
every other registration is checked on the Project exactly as it is.
"""

from __future__ import annotations

import re
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git, scripted_executor
from workline import roadmap as rm
from workline import start as st
from workline.create import RelatedSpec, RelationSpec, WorkSpec, create_standalone_work, register_works
from workline.errors import SpecViolation, StopError, ValidationError
from workline.ids import new_id
from workline.mutation import Effect, Mutation, MutationController, WriteScope, utc_now
from workline.oplock import project_operation
from workline.ops import Replan
from workline.state import ProjectView
from workline.store import Event
from workline.validate import validate_project


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


def after_recording(pattern: str):
    """Stop right after a stage matching ``pattern`` is recorded, none of it applied."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        real(mutation, stage, effects)
        if re.search(pattern, stage):
            raise Interrupted(stage)

    return mock.patch.object(Mutation, "add_effects", fire)


def after_applying(pattern: str):
    """Stop right after the call that applied a stage matching ``pattern``."""
    real = Mutation.apply

    def fire(mutation):
        before = {e["seq"] for e in mutation.record.get("effects") or [] if e.get("applied")}
        outcome = real(mutation)
        if any(e.get("applied") and e["seq"] not in before and re.search(pattern, e["stage"])
               for e in mutation.record.get("effects") or []):
            raise Interrupted(pattern)
        return outcome

    return mock.patch.object(Mutation, "apply", fire)


def after_deciding():
    """Stop once the replan's IDs are reserved and nothing is recorded."""
    real = rm.plan_replan

    def fire(*args, **kwargs):
        real(*args, **kwargs)
        raise Interrupted("plan_replan")

    return mock.patch.object(rm, "plan_replan", fire)


class ReplanCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)

    # observation -------------------------------------------------------------
    def relation(self, rel_type: str, a: str, b: str) -> str:
        (found,) = [r.id for r in ProjectView.load(self.store).roadmap_relations if (r.type, r.from_id, r.to) == (rel_type, a, b)]
        return found

    def edges(self) -> list[tuple[str, str, str]]:
        return sorted((r.type, r.from_id, r.to) for r in ProjectView.load(self.store).roadmap_relations)

    def named(self, name: str) -> list[str]:
        return [w.id for w in ProjectView.load(self.store).works.values() if w.name == name]

    def events(self, entity: str) -> list[str]:
        return [e.type for e in ProjectView.load(self.store).events if e.entity == entity]

    def subjects(self) -> list[str]:
        return git(self.store.root, "log", "--format=%s").splitlines()

    def head(self) -> str:
        return git(self.store.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote_path(), "rev-parse", "main").strip()

    def dirty(self) -> list[str]:
        return [line for line in git(self.store.root, "status", "--porcelain", "--untracked-files=all").splitlines()
                if ".workline/runtime/" not in line]

    def record_bytes(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))}

    def watching(self, call):
        """Run ``call``; return its result, the stages it recorded and the effect kinds it executed."""
        stages: list[str] = []
        executed: list[str] = []
        real_add, real_apply = Mutation.add_effects, MutationController.apply_effect

        def add(mutation, stage, effects):
            real_add(mutation, stage, effects)
            stages.append(stage)

        def apply(controller, record):
            executed.append(record["kind"])
            return real_apply(controller, record)

        with mock.patch.object(Mutation, "add_effects", add), mock.patch.object(MutationController, "apply_effect", apply):
            result = call()
        return result, stages, executed

    def assertFinished(self, subject: str) -> None:
        """Done once: nothing pending, the structure valid, one commit, pushed, nothing left over."""
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(self.subjects().count(subject), 1)
        self.assertEqual(self.subjects()[0], subject)
        self.assertEqual(self.head(), self.remote_head())
        self.assertEqual(self.dirty(), [])
        self.assertEqual(len(self.edges()), len(set(self.edges())))

    # fixtures ---------------------------------------------------------------
    def phase(self, **entry):
        roadmap = self.simple_roadmap(self.store)
        self.rid, self.pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        return self.simple_entry(self.store, self.pa, **entry)

    def spec(self, name: str, **kwargs) -> WorkSpec:
        return WorkSpec(name, name.lower(), phase_id=self.pa, roadmap_id=self.rid, **kwargs)

    def replacement(self, **spec):
        """W2 excluded and replaced by W3 in front of the integration."""
        entry = self.phase(works={"w1": "W1", "w2": "W2"})
        w2, integration = entry.work_ids["w2"], entry.integration_id
        replan = Replan(
            remove_relation_ids=(self.relation("requires_completion", w2, integration),),
            add_relations=(RelationSpec("requires_completion", "w3", integration),),
            new_works={"w3": self.spec("W3", **spec)},
        )
        return entry, replan

    def integration_moved_before_confirmation(self):
        """START cancels I1 and re-integrates through I2, which the confirmation now waits for."""
        entry = self.phase(confirmation=True)
        w1, i1, c1 = entry.work_ids["w1"], entry.integration_id, entry.confirmation_id
        st.start(self.store, w1, "single-work", completing_executor(self.store))
        replan = Replan(
            remove_relation_ids=(self.relation("requires_completion", w1, i1), self.relation("requires_completion", i1, c1)),
            add_relations=(RelationSpec("requires_completion", w1, "i2"), RelationSpec("requires_completion", "i2", c1)),
            new_works={"i2": self.spec("I2", work_kind="phase_integration_check")},
        )
        return entry, replan, lambda: st.start(self.store, i1, "single-work", scripted_executor({i1: [st.Cancel(replan, "scope")]}))


# --------------------------------------------------------------------------- valid replans finish
class ValidReplanTests(ReplanCase):
    def test_a_work_plan_exclusion_replaces_the_work(self) -> None:
        entry, replan = self.replacement()
        w1, w2, integration = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id

        result, stages, executed = self.watching(lambda: rm.plan_exclude_work(self.store, w2, replan))

        self.assertEqual(result.status, "plan_excluded")
        # the same stages in the same order: the removal is still applied after the registration
        self.assertEqual(stages, ["event", "replan:works", "replan:remove", "finalize"])
        self.assertEqual(executed, ["append_event", "write_file", "add_relation", "remove_relation", "git_commit", "git_push"])
        (w3,) = self.named("W3")
        self.assertNotIn(("requires_completion", w2, integration), self.edges())
        self.assertIn(("requires_completion", w3, integration), self.edges())
        self.assertEqual(self.events(w2), ["plan_excluded"])
        self.assertFinished(f"chore(workline): plan_excluded {w2}")
        self.assertEqual(st.start(self.store, w1, "outer", completing_executor(self.store)).status, "phase_complete")

    def test_a_start_cancel_moves_the_confirmation_to_a_new_integration(self) -> None:
        entry, replan, cancel = self.integration_moved_before_confirmation()
        w1, i1, c1 = entry.work_ids["w1"], entry.integration_id, entry.confirmation_id

        result, stages, executed = self.watching(cancel)

        self.assertEqual(result.status, "cancelled")
        self.assertEqual([re.sub(r"^w_\w+:", "<I1>:", stage) for stage in stages],
                         ["<I1>:lifecycle:0", "<I1>:lifecycle:1", "<I1>:cancel:0:works", "<I1>:cancel:0:remove", "commit:0"])
        self.assertEqual(executed[4:], ["write_file", "add_relation", "add_relation", "remove_relation", "remove_relation",
                                        "git_commit", "git_push"])
        (i2,) = self.named("I2")
        self.assertEqual([e for e in self.edges() if e[0] == "requires_completion"],
                         sorted([("requires_completion", w1, i2), ("requires_completion", i2, c1)]))
        self.assertEqual(self.events(i1)[-2:], ["work_target_removed", "work_cancelled"])
        self.assertEqual(self.events(i1).count("work_cancelled"), 1)
        self.assertFinished(f"chore(workline): cancel {ProjectView.load(self.store).works[i1].display}")
        self.assertEqual(st.start(self.store, i2, "outer", completing_executor(self.store)).status, "phase_complete")

    def test_a_standalone_plan_exclusion_replaces_the_work(self) -> None:
        s1 = create_standalone_work(self.store, WorkSpec("S1", "s1")).work_id
        s2 = create_standalone_work(self.store, WorkSpec("S2", "s2")).work_id
        s3 = create_standalone_work(self.store, WorkSpec("S3", "s3")).work_id
        st.plan_exclude_standalone_work(self.store, s1, Replan(add_relations=(RelationSpec("requires_completion", s2, s3),)))
        replan = Replan(remove_relation_ids=(self.relation("requires_completion", s2, s3),),
                        add_relations=(RelationSpec("requires_completion", "s4", s3),),
                        new_works={"s4": WorkSpec("S4", "s4")})

        result = st.plan_exclude_standalone_work(self.store, s2, replan)

        self.assertEqual(result.status, "plan_excluded")
        (s4,) = self.named("S4")
        self.assertEqual(self.edges(), [("requires_completion", s4, s3)])
        display = ProjectView.load(self.store).works[s2].display
        self.assertFinished(f"chore(workline): plan_excluded {display}")

    def test_a_phase_plan_exclusion_registers_a_new_work(self) -> None:
        roadmap = self.simple_roadmap(self.store, {"b": ("Phase B", "B"), "c": ("Phase C", "C")},
                                      [("requires_completion", "b", "c")])
        pb, pc = roadmap.phase_ids["b"], roadmap.phase_ids["c"]
        replan = Replan(remove_relation_ids=(self.relation("requires_completion", pb, pc),),
                        new_works={"n": WorkSpec("N", "covers what B was for")})

        result = rm.plan_exclude_phase(self.store, pb, replan)

        self.assertEqual(result.status, "plan_excluded")
        self.assertEqual(len(self.named("N")), 1)
        self.assertEqual(self.edges(), [])
        self.assertFinished(f"chore(workline): plan_excluded {pb}")
        self.assertEqual(rm.hold_phase(self.store, pc).status, "phase_held")

    def test_a_cancelled_work_that_a_fix_returns_to_is_replaced(self) -> None:
        entry = self.phase()
        w1, i1 = entry.work_ids["w1"], entry.integration_id
        st.start(self.store, w1, "single-work",
                 scripted_executor({w1: [st.Derive({"f": st.DerivedWork("F", "fixed", return_to=True)}, move=True)]}))
        (f,) = self.named("F")
        replan = Replan(remove_relation_ids=(self.relation("return_to", f, w1), self.relation("requires_completion", w1, i1)),
                        add_relations=(RelationSpec("requires_completion", "r", i1),), new_works={"r": self.spec("R")})

        result = st.start(self.store, w1, "single-work", scripted_executor({w1: [st.Cancel(replan, "superseded")]}))

        self.assertEqual(result.status, "cancelled")
        self.assertNotIn(("return_to", f, w1), self.edges())
        self.assertFinished(f"chore(workline): cancel {ProjectView.load(self.store).works[w1].display}")
        self.assertEqual(st.start(self.store, f, "outer", completing_executor(self.store)).status, "phase_complete")

    def test_a_cycle_only_through_a_removed_relation_is_not_a_cycle(self) -> None:
        entry = self.phase(works={"w1": "W1", "w2": "W2", "w3": "W3"}, requires_completion=(("w1", "w2"),))
        w1, w2, w3, i1 = entry.work_ids["w1"], entry.work_ids["w2"], entry.work_ids["w3"], entry.integration_id
        replan = Replan(
            remove_relation_ids=(self.relation("requires_completion", w1, w2), self.relation("requires_completion", w3, i1)),
            add_relations=(RelationSpec("requires_completion", w2, "n"), RelationSpec("requires_completion", "n", w1),
                           RelationSpec("requires_completion", "n", i1)),
            new_works={"n": self.spec("N")},
        )

        self.assertEqual(rm.plan_exclude_work(self.store, w3, replan).status, "plan_excluded")

        self.assertFinished(f"chore(workline): plan_excluded {w3}")
        self.assertEqual(st.start(self.store, w2, "outer", completing_executor(self.store)).status, "phase_complete")

    def test_an_edge_removed_and_added_again_is_not_a_duplicate(self) -> None:
        s0 = create_standalone_work(self.store, WorkSpec("S0", "s0")).work_id
        s1 = create_standalone_work(self.store, WorkSpec("S1", "s1")).work_id
        s2 = create_standalone_work(self.store, WorkSpec("S2", "s2")).work_id
        s3 = create_standalone_work(self.store, WorkSpec("S3", "s3")).work_id
        st.plan_exclude_standalone_work(self.store, s0, Replan(add_relations=(RelationSpec("requires_completion", s2, s3),)))
        old = self.relation("requires_completion", s2, s3)
        replan = Replan(remove_relation_ids=(old,), add_relations=(RelationSpec("requires_completion", s2, s3),),
                        new_works={"s4": WorkSpec("S4", "s4")})

        self.assertEqual(st.plan_exclude_standalone_work(self.store, s1, replan).status, "plan_excluded")

        (edge,) = ProjectView.load(self.store).roadmap_relations
        self.assertEqual((edge.type, edge.from_id, edge.to), ("requires_completion", s2, s3))
        self.assertNotEqual(edge.id, old)
        self.assertFinished(f"chore(workline): plan_excluded {ProjectView.load(self.store).works[s1].display}")


# --------------------------------------------------------------------------- nothing else moves
class UnchangedRefusalTests(ReplanCase):
    """A replan refused for anything but the relations it removes is refused where and how it was."""

    def assertRefusedAfterTheEventOnly(self, call, code: str, message: str, kept: tuple[str, str, str]) -> None:
        with self.assertRaises(StopError) as refused:
            call()
        self.assertEqual(refused.exception.code, code)
        self.assertIn(message, refused.exception.message)
        (record,) = MutationController(self.store).list_pending()
        self.assertEqual([(e["stage"], e["kind"]) for e in record["effects"]], [("event", "append_event")])
        self.assertIn(kept, self.edges())  # the removal was not applied on its own

    def test_a_replacement_whose_payload_the_registration_refuses(self) -> None:
        for label, spec in (("related", {"related": (RelatedSpec("bogus_type", "a.md"),)}),
                            ("confirmation_target", {"confirmation_target": "w1"})):
            with self.subTest(payload=label):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    (case.store.root / "a.md").write_text("a\n", encoding="utf-8")
                    entry, replan = case.replacement(**spec)
                    w2, i1 = entry.work_ids["w2"], entry.integration_id
                    message = ("work w3: unknown related type bogus_type" if label == "related"
                               else "work w3: confirmation_target is only for human_confirmation Works")
                    case.assertRefusedAfterTheEventOnly(lambda: rm.plan_exclude_work(case.store, w2, replan),
                                                        "validation_failed", message, ("requires_completion", w2, i1))
                finally:
                    case.doCleanups()

    def test_a_phase_relation_carried_with_new_works(self) -> None:
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B"), "c": ("Phase C", "C")},
                                      [("requires_completion", "b", "c")])
        pa, pb, pc = (roadmap.phase_ids[k] for k in ("a", "b", "c"))
        replan = Replan(remove_relation_ids=(self.relation("requires_completion", pb, pc),),
                        add_relations=(RelationSpec("requires_completion", pa, pc),),
                        new_works={"n": WorkSpec("N", "n")})
        self.assertRefusedAfterTheEventOnly(lambda: rm.plan_exclude_phase(self.store, pb, replan), "validation_failed",
                                            "relation 0: endpoint unresolvable", ("requires_completion", pb, pc))

    def test_a_replan_its_owner_refuses_writes_nothing(self) -> None:
        """The removals a replan names never make a replan valid that its owner's projection refuses."""
        cases = {
            "removal that does not repair": lambda case, w1, w2, i1: (
                (case.relation("requires_completion", w1, i1),), (RelationSpec("requires_completion", "w3", i1),)),
            "cycle that remains": lambda case, w1, w2, i1: (
                (case.relation("requires_completion", w2, i1),),
                (RelationSpec("requires_completion", i1, "w3"), RelationSpec("requires_completion", "w3", i1))),
            "duplicate edge": lambda case, w1, w2, i1: (
                (case.relation("requires_completion", w2, i1),),
                (RelationSpec("requires_completion", "w3", i1), RelationSpec("requires_completion", w1, i1))),
        }
        for label, decide in cases.items():
            with self.subTest(replan=label):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    entry = case.phase(works={"w1": "W1", "w2": "W2"})
                    w1, w2, i1 = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id
                    removals, additions = decide(case, w1, w2, i1)
                    replan = Replan(remove_relation_ids=removals, add_relations=additions, new_works={"w3": case.spec("W3")})
                    edges, events, head = case.edges(), ProjectView.load(case.store).events, case.head()

                    with case.assertRaises(SpecViolation) as refused:
                        rm.plan_exclude_work(case.store, w2, replan)

                    case.assertIn("plan exclusion replan: structure would be invalid", refused.exception.message)
                    case.assertEqual((case.edges(), ProjectView.load(case.store).events, case.head()), (edges, events, head))
                    case.assertEqual(MutationController(case.store).list_pending(), [])
                    case.assertEqual(case.named("W3"), [])
                finally:
                    case.doCleanups()


class RemovedAfterTests(ReplanCase):
    """What ``removed_after`` leaves out of the registration core's structure checks - and what it does not."""

    def dangling(self):
        """W2 plan_excluded by hand while W2 -> I1 still stands, inside an open mutation."""
        entry = self.phase(works={"w1": "W1", "w2": "W2"})
        w1, w2, i1 = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id
        lock = project_operation(self.store, "registration-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        mutation = MutationController(self.store).open("roadmap", {"operation": "work-plan-exclude", "entity": w2},
                                                       WriteScope(entities=(w2,)))
        mutation.add_effects("event", [Effect.append_event(Event(new_id("event"), "plan_excluded", w2, utc_now()))])
        mutation.apply()
        return mutation, i1, self.relation("requires_completion", w2, i1), self.relation("requires_completion", w1, i1)

    def register(self, mutation, key: str, i1: str, **kwargs):
        return register_works(mutation, key, {key: self.spec(key.upper())},
                              [RelationSpec("requires_completion", key, i1)], **kwargs)

    def test_the_named_removals_are_left_out_of_the_check_before_writing_and_of_the_postcheck(self) -> None:
        mutation, i1, dangling, _ = self.dangling()
        for key, refuse_before_apply in (("wa", True), ("wb", False)):
            with self.subTest(refuse_before_apply=refuse_before_apply):
                result = self.register(mutation, key, i1, removed_after=(dangling,), refuse_before_apply=refuse_before_apply)
                self.assertEqual(set(result.work_ids), {key})
                self.assertTrue(mutation.has_stage(key))
        self.assertIn(dangling, [r.id for r in ProjectView.load(self.store).roadmap_relations])  # nothing was removed

    def test_a_relation_that_is_not_named_is_still_refused_before_anything_is_written(self) -> None:
        mutation, i1, dangling, unrelated = self.dangling()
        for key, removed in (("wc", ()), ("wd", (unrelated,))):
            with self.subTest(removed_after=removed and "unrelated" or "none"):
                with self.assertRaises(ValidationError) as refused:
                    self.register(mutation, key, i1, removed_after=removed)
                self.assertEqual(refused.exception.code, "postcheck_failed")
                self.assertIn(f"{dangling}: requires_completion predecessor", refused.exception.message)
                self.assertFalse(mutation.has_stage(key))
                self.assertEqual(self.named(key.upper()), [])

    def test_a_relation_that_is_not_named_is_still_refused_by_the_postcheck(self) -> None:
        mutation, i1, dangling, unrelated = self.dangling()
        with self.assertRaises(ValidationError) as refused:
            self.register(mutation, "we", i1, removed_after=(unrelated,), refuse_before_apply=False)
        self.assertEqual(refused.exception.code, "postcheck_failed")
        self.assertIn(f"{dangling}: requires_completion predecessor", refused.exception.message)
        self.assertTrue(mutation.has_stage("we"))  # this caller asked for the old order: applied, then refused

    def test_the_cycle_check_leaves_the_named_removals_out(self) -> None:
        entry = self.phase(works={"w1": "W1", "w2": "W2"}, requires_completion=(("w1", "w2"),))
        w1, w2 = entry.work_ids["w1"], entry.work_ids["w2"]
        forward = self.relation("requires_completion", w1, w2)
        lock = project_operation(self.store, "registration-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        mutation = MutationController(self.store).open("roadmap", {"operation": "phase-entry", "phase_id": self.pa},
                                                       WriteScope(entities=(self.pa,)))
        back = [RelationSpec("requires_completion", w2, "n"), RelationSpec("requires_completion", "n", w1)]

        with self.assertRaises(ValidationError) as refused:
            register_works(mutation, "cycle", {"n": self.spec("N")}, back)
        self.assertIn("requires_completion would form a cycle", refused.exception.message)
        self.assertFalse(mutation.has_stage("cycle"))

        # The caller has decided to remove W1 -> W2 right after: without it there is no cycle.
        result = register_works(mutation, "named", {"n": self.spec("N")}, back, removed_after=(forward,))
        self.assertEqual(set(result.work_ids), {"n"})
        self.assertTrue(mutation.has_stage("named"))


# --------------------------------------------------------------------------- interrupted replans
class InterruptedReplanTests(ReplanCase):
    def test_the_same_request_finishes_from_before_the_event(self) -> None:
        for window, stop in (("IDs reserved", after_deciding), ("event recorded", lambda: after_recording(r"^event$"))):
            with self.subTest(window=window):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    entry, replan = case.replacement()
                    w2 = entry.work_ids["w2"]
                    with stop(), case.assertRaises(Interrupted):
                        rm.plan_exclude_work(case.store, w2, replan)
                    (pending,) = MutationController(case.store).list_pending()

                    result, _, executed = case.watching(lambda: rm.plan_exclude_work(case.store, w2, replan))

                    case.assertEqual(result.mutation_id, pending["mutation_id"])
                    case.assertEqual(executed, ["append_event", "write_file", "add_relation", "remove_relation", "git_commit", "git_push"])
                    case.assertEqual(len(case.named("W3")), 1)
                    case.assertEqual(case.events(w2), ["plan_excluded"])
                    case.assertFinished(f"chore(workline): plan_excluded {w2}")
                finally:
                    case.doCleanups()

    def test_the_same_start_cancel_finishes_from_before_its_event(self) -> None:
        entry, replan, cancel = self.integration_moved_before_confirmation()
        i1 = entry.integration_id
        real = st.plan_replan

        def decided(*args, **kwargs):
            real(*args, **kwargs)
            raise Interrupted("plan_replan")

        with mock.patch.object(st, "plan_replan", decided), self.assertRaises(Interrupted):
            cancel()
        (pending,) = MutationController(self.store).list_pending()

        result = cancel()

        self.assertEqual((result.status, result.mutation_id), ("cancelled", pending["mutation_id"]))
        self.assertEqual(len(self.named("I2")), 1)
        self.assertEqual(self.events(i1).count("work_cancelled"), 1)
        self.assertFinished(f"chore(workline): cancel {ProjectView.load(self.store).works[i1].display}")


class KnownResidualTests(ReplanCase):
    """Not part of BL-028, and kept as they were: a retry after the terminal event is applied is refused, untouched.

    Plan exclusion's own event makes its unstarted precondition refuse the retry
    (BL-025 residual (1)), and START refuses a Work its own cancel made terminal.
    """

    def assertRetryRefusedUntouched(self, retry, code: str) -> None:
        records = self.record_bytes()
        with self.assertRaises(StopError) as refused:
            retry()
        self.assertEqual(refused.exception.code, code)
        self.assertEqual(self.record_bytes(), records)

    def test_plan_exclusion_after_its_event(self) -> None:
        for window, stop, code in (
            ("event applied", lambda: after_applying(r"^event$"), "structure_invalid"),
            ("works applied", lambda: after_applying(r"^replan:works$"), "structure_invalid"),
            ("removals applied", lambda: after_applying(r"^replan:remove$"), "spec_violation"),
        ):
            with self.subTest(window=window):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    entry, replan = case.replacement()
                    w2 = entry.work_ids["w2"]
                    with stop(), case.assertRaises(Interrupted):
                        rm.plan_exclude_work(case.store, w2, replan)
                    case.assertRetryRefusedUntouched(lambda: rm.plan_exclude_work(case.store, w2, replan), code)
                finally:
                    case.doCleanups()

    def test_start_cancel_after_its_event(self) -> None:
        entry, replan, cancel = self.integration_moved_before_confirmation()
        with after_applying(r":cancel:\d+:remove$"), self.assertRaises(Interrupted):
            cancel()
        self.assertRetryRefusedUntouched(cancel, "spec_violation")


if __name__ == "__main__":
    unittest.main()
