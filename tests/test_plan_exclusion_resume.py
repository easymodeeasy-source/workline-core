"""A plan exclusion carries its own interrupted mutation to the end (BL-029).

Plan exclusion - of a Phase, of a Phase Work (a normal Work or an unstarted
integration) and, owned by START, of a standalone Work - records its
``plan_excluded`` event and then applies its replan: the new Works with the
relations they carry, the removals, the commit and the push. Once its own event
was applied, running the same request again refused itself: its precondition and
its structure precheck read the Project with that event (and the replan's
applied part) in it, its replan resolved removals the mutation had already
applied, and its registration counted a recorded integration a second time.
Nothing could finish the mutation, and its uncommitted event log stopped every
operation that writes it.

The replan is now part of the mutation's invocation, durable before the first ID
is reserved, and an unfinished mutation of the slot is continued only when its
record proves it is this request's own: the same request, its reservations, its
stages in order, the one event, the registration / relations / removals this
request decides with those IDs, and applied effects that are a prefix of what it
recorded. The request is then decided on the Project without the effects the
mutation applied, the recorded registration and removals are read back instead
of decided again, and everything still to come is checked before any recorded
effect is replayed. A record that proves anything less - a record without a
request, another request, several records, an edited stage or reservation - is
``reconcile required`` in every window and left exactly as it is.

Where the retry may replay and record stays the Git recovery contract's: the
decision carries its branch (BL-036), the commit takes it over, and a recorded
commit is made only on that branch (BL-035), after independent commits (BL-032),
and never recognised by its message alone (BL-033).
"""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git, scripted_executor
from test_decision_branch_binding import DECIDED_ON, DecisionCase, after_recording
from test_recorded_commit_resume import EVENT_LOG, MAIN, Interrupted, after_applying
from workline import gitops, ops
from workline import roadmap as rm
from workline import start as st
from workline import yamlish
from workline.create import RelatedSpec, RelationSpec, WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, SpecViolation, StopError
from workline.ids import new_id
from workline.mutation import FILE_EFFECT_KINDS, Mutation, MutationController
from workline.ops import Replan
from workline.state import ProjectView
from workline.store import WORKLINE_DIR, Relation, render_relations
from workline.validate import validate_project


def after_deciding(module):
    """Stop right after the owner reserved the replan's IDs, nothing recorded."""
    real = module.plan_replan

    def fire(*args, **kwargs):
        real(*args, **kwargs)
        raise Interrupted("plan_replan")

    return mock.patch.object(module, "plan_replan", fire)


def before_applying(kind: str):
    real = MutationController.apply_effect

    def fire(controller, record):
        if record["kind"] == kind:
            raise Interrupted(f"before {kind}")
        return real(controller, record)

    return mock.patch.object(MutationController, "apply_effect", fire)


def before_completing():
    def fire(mutation):
        raise Interrupted("before complete")

    return mock.patch.object(Mutation, "complete", fire)


# window -> (interruption, effect kinds a resume of a Work replacement still has to execute; None: all of them)
WINDOWS = {
    "IDs reserved": (lambda module: after_deciding(module), None),
    "event recorded": (lambda module: after_recording(r"^event$"), None),
    "event applied": (lambda module: after_applying(r"^event$"), ["write_file", "add_relation", "remove_relation", "git_commit", "git_push"]),
    "works recorded": (lambda module: after_recording(r"^replan:works$"), ["write_file", "add_relation", "remove_relation", "git_commit", "git_push"]),
    "works applied": (lambda module: after_applying(r"^replan:works$"), ["remove_relation", "git_commit", "git_push"]),
    "removals recorded": (lambda module: after_recording(r"^replan:remove$"), ["remove_relation", "git_commit", "git_push"]),
    "removals applied": (lambda module: after_applying(r"^replan:remove$"), ["git_commit", "git_push"]),
    "commit recorded": (lambda module: after_recording(r"^finalize$"), ["git_commit", "git_push"]),
    "committed": (lambda module: before_applying("git_push"), ["git_push"]),
    "pushed": (lambda module: before_completing(), []),
}
FRESH = ["append_event", "write_file", "add_relation", "remove_relation", "git_commit", "git_push"]
LEGACY = "before this operation recorded what it"


class PlanExclusionCase(WorklineTestCase):
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

    def snapshot(self) -> dict:
        canonical = {
            path.relative_to(self.store.root).as_posix(): path.read_bytes()
            for path in sorted(self.store.workline.rglob("*"))
            if path.is_file() and "runtime" not in path.relative_to(self.store.workline).parts
        }
        return {"records": self.record_bytes(), "files": canonical, "head": self.head(), "remote": self.remote_head()}

    def watching(self, call):
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

    def interrupt(self, call, window: str, module=rm) -> dict:
        stop, _ = WINDOWS[window]
        with stop(module), self.assertRaises(Interrupted):
            call()
        (pending,) = MutationController(self.store).list_pending()
        return pending

    def edit_record(self, pending: dict, change) -> None:
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8")

    def assertFinished(self, pending: dict, result, subject: str) -> None:
        self.assertEqual(result.mutation_id, pending["mutation_id"])
        self.assertEqual(result.status, "plan_excluded")
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(self.subjects().count(subject), 1)
        self.assertEqual(self.subjects()[0], subject)
        self.assertEqual(self.head(), self.remote_head())
        self.assertEqual(self.dirty(), [])
        self.assertEqual(len(self.edges()), len(set(self.edges())))

    def assertRefusedUntouched(self, call, error=ReconcileRequired) -> StopError:
        before = self.snapshot()
        with self.assertRaises(error) as refused:
            self.watching(call)
        self.assertEqual(self.snapshot(), before)
        return refused.exception

    # fixtures ---------------------------------------------------------------
    def phase(self, **entry):
        roadmap = self.simple_roadmap(self.store)
        self.rid, self.pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        return self.simple_entry(self.store, self.pa, **entry)

    def spec(self, name: str, **kwargs) -> WorkSpec:
        return WorkSpec(name, name.lower(), phase_id=self.pa, roadmap_id=self.rid, **kwargs)

    def replacement(self, key: str = "w3", **spec):
        """W2 excluded and replaced by W3 in front of the integration."""
        entry = self.phase(works={"w1": "W1", "w2": "W2"})
        w1, w2, integration = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id
        self.w1, self.w2, self.i1 = w1, w2, integration
        self.relation_w2 = self.relation("requires_completion", w2, integration)
        self.relation_w1 = self.relation("requires_completion", w1, integration)

        def replan(key=key, desired=None, addition="requires_completion", removals=None, **extra):
            fields = {**spec, **extra}
            name = fields.pop("name", "W3")
            return Replan(
                remove_relation_ids=removals if removals is not None else (self.relation_w2,),
                add_relations=(RelationSpec(addition, key, integration),),
                new_works={key: WorkSpec(name, desired or "w3", phase_id=self.pa, roadmap_id=self.rid, **fields)},
            )

        return w2, replan

    def integration_replacement(self):
        """An unstarted integration I1 excluded and replaced by I2."""
        entry = self.phase(works={"w1": "W1", "w2": "W2"})
        w1, w2, i1 = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id
        removals = (self.relation("requires_completion", w1, i1), self.relation("requires_completion", w2, i1))
        replan = Replan(remove_relation_ids=removals,
                        add_relations=(RelationSpec("requires_completion", w1, "i2"), RelationSpec("requires_completion", w2, "i2")),
                        new_works={"i2": self.spec("I2", work_kind="phase_integration_check")})
        return i1, replan

    def standalone_replacement(self):
        """S2 excluded and replaced by S4 in front of S3."""
        s1 = create_standalone_work(self.store, WorkSpec("S1", "s1")).work_id
        s2 = create_standalone_work(self.store, WorkSpec("S2", "s2")).work_id
        s3 = create_standalone_work(self.store, WorkSpec("S3", "s3")).work_id
        st.plan_exclude_standalone_work(self.store, s1, Replan(add_relations=(RelationSpec("requires_completion", s2, s3),)))
        replan = Replan(remove_relation_ids=(self.relation("requires_completion", s2, s3),),
                        add_relations=(RelationSpec("requires_completion", "s4", s3),),
                        new_works={"s4": WorkSpec("S4", "s4")})
        self.s3 = s3
        return s2, replan

    def each(self, windows, body) -> None:
        for window in windows:
            with self.subTest(window=window):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    body(case, window)
                finally:
                    case.doCleanups()


# --------------------------------------------------------------------------- the recorded request
class RequestIdentityTests(PlanExclusionCase):
    def test_the_replan_is_recorded_before_the_first_id_is_reserved(self) -> None:
        w2, replan = self.replacement(related=(RelatedSpec("must_read", "a.md"),), derivation_detail=" why ")
        seen: list[object] = []
        reserve = Mutation.reserve_id

        def watch(mutation, key, kind):
            if not seen:
                seen.append(yamlish.load(mutation.path.read_text(encoding="utf-8"))["invocation"].get("request"))
            return reserve(mutation, key, kind)

        with mock.patch.object(Mutation, "reserve_id", watch):
            pending = self.interrupt(lambda: rm.plan_exclude_work(self.store, w2, replan()), "IDs reserved")

        request = {
            "version": 1,
            "target": w2,
            "new_works": [{
                "key": "w3", "name": "W3", "desired_state": "w3", "phase_id": self.pa, "roadmap_id": self.rid,
                "work_kind": None, "confirmation_target": None,
                "related": [{"type": "must_read", "to": "a.md", "condition": None}], "derivation_detail": "why",
            }],
            "add_relations": [{"type": "requires_completion", "from": "w3", "to": self.i1}],
            "remove_relation_ids": [self.relation_w2],
        }
        self.assertEqual(seen, [request])
        self.assertEqual(pending["invocation"], {"operation": "work-plan-exclude", "entity": w2, "request": request})
        self.assertEqual(ops._plan_exclusion_request(w2, replan()), request)

    def test_what_rendering_strips_is_one_request_and_everything_else_is_two(self) -> None:
        def identity(**changes) -> dict:
            fields = {"remove_relation_ids": ("rel_1",), "add_relations": (RelationSpec("requires_completion", "n", "w_i"),),
                      "new_works": {"n": WorkSpec("N", "n")}}
            fields.update(changes)
            return ops._plan_exclusion_request("w_t", Replan(**fields))

        base = identity()
        self.assertEqual(identity(new_works={"n": WorkSpec("N", "\n  n  ")}), base)
        for label, other in {
            "name whitespace": identity(new_works={"n": WorkSpec("N ", "n")}),
            "new Work key": identity(new_works={"m": WorkSpec("N", "n")}, add_relations=(RelationSpec("requires_completion", "m", "w_i"),)),
            "desired state": identity(new_works={"n": WorkSpec("N", "other")}),
            "derivation detail present but empty": identity(new_works={"n": WorkSpec("N", "n", derivation_detail="  ")}),
            "endpoint spelled as an ID": identity(add_relations=(RelationSpec("requires_completion", "w_n", "w_i"),)),
            "addition type": identity(add_relations=(RelationSpec("planned_next", "n", "w_i"),)),
            "removal": identity(remove_relation_ids=("rel_2",)),
            "removal order": identity(remove_relation_ids=("rel_2", "rel_1")),
            "declared order of new Works": identity(new_works={"n": WorkSpec("N", "n"), "m": WorkSpec("M", "m")}),
            "other target": ops._plan_exclusion_request("w_other", Replan(remove_relation_ids=("rel_1",),
                            add_relations=(RelationSpec("requires_completion", "n", "w_i"),), new_works={"n": WorkSpec("N", "n")})),
        }.items():
            with self.subTest(label):
                self.assertNotEqual(other, base)
        two = identity(new_works={"n": WorkSpec("N", "n"), "m": WorkSpec("M", "m")})
        swapped = identity(new_works={"m": WorkSpec("M", "m"), "n": WorkSpec("N", "n")})
        self.assertNotEqual(two, swapped)


# --------------------------------------------------------------------------- the same request finishes
class SameRequestResumeTests(PlanExclusionCase):
    def test_a_work_replacement_finishes_from_every_window(self) -> None:
        def body(case, window):
            w2, replan = case.replacement()
            pending = case.interrupt(lambda: rm.plan_exclude_work(case.store, w2, replan()), window)

            result, stages, executed = case.watching(lambda: rm.plan_exclude_work(case.store, w2, replan()))

            still = WINDOWS[window][1]
            case.assertEqual(executed, FRESH if still is None else still)
            recorded = {e["stage"] for e in pending["effects"]}
            case.assertEqual(stages, [s for s in ["event", "replan:works", "replan:remove", "finalize"] if s not in recorded])
            case.assertEqual(len(case.named("W3")), 1)
            case.assertEqual(case.events(w2), ["plan_excluded"])
            case.assertFinished(pending, result, f"chore(workline): plan_excluded {w2}")

        self.each(WINDOWS, body)

    def test_a_standalone_replacement_finishes(self) -> None:
        def body(case, window):
            s2, replan = case.standalone_replacement()
            pending = case.interrupt(lambda: st.plan_exclude_standalone_work(case.store, s2, replan), window, st)

            result, _, executed = case.watching(lambda: st.plan_exclude_standalone_work(case.store, s2, replan))

            case.assertEqual(executed, WINDOWS[window][1])
            (s4,) = case.named("S4")
            case.assertEqual(case.edges(), [("requires_completion", s4, case.s3)])
            display = ProjectView.load(case.store).works[s2].display
            case.assertFinished(pending, result, f"chore(workline): plan_excluded {display}")

        self.each(("event applied", "removals applied", "committed"), body)

    def test_a_phase_exclusion_finishes(self) -> None:
        def no_replan(case, window):
            roadmap = case.simple_roadmap(case.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B")})
            pb = roadmap.phase_ids["b"]
            pending = case.interrupt(lambda: rm.plan_exclude_phase(case.store, pb), window)
            result, _, executed = case.watching(lambda: rm.plan_exclude_phase(case.store, pb))
            case.assertEqual(executed, {"event applied": ["git_commit", "git_push"], "committed": ["git_push"]}[window])
            case.assertFinished(pending, result, f"chore(workline): plan_excluded {pb}")

        def with_replan(case, window):
            roadmap = case.simple_roadmap(case.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B")}, [("requires_completion", "b", "a")])
            pa, pb = roadmap.phase_ids["a"], roadmap.phase_ids["b"]
            replan = Replan(remove_relation_ids=(case.relation("requires_completion", pb, pa),), new_works={"n": WorkSpec("N", "n")})
            pending = case.interrupt(lambda: rm.plan_exclude_phase(case.store, pb, replan), window)
            result, _, executed = case.watching(lambda: rm.plan_exclude_phase(case.store, pb, replan))
            case.assertEqual(executed, ["remove_relation", "git_commit", "git_push"])
            case.assertEqual(len(case.named("N")), 1)
            case.assertEqual(case.edges(), [])
            case.assertFinished(pending, result, f"chore(workline): plan_excluded {pb}")
            case.assertEqual(rm.hold_phase(case.store, pa).status, "phase_held")

        self.each(("event applied", "committed"), no_replan)
        self.each(("works applied",), with_replan)

    def test_an_integration_replacement_does_not_count_the_integration_twice(self) -> None:
        def body(case, window):
            i1, replan = case.integration_replacement()
            pending = case.interrupt(lambda: rm.plan_exclude_work(case.store, i1, replan), window)

            result, _, executed = case.watching(lambda: rm.plan_exclude_work(case.store, i1, replan))

            case.assertEqual(executed.count("write_file"), 1 if window == "event applied" else 0)
            case.assertEqual(len(case.named("I2")), 1)
            case.assertEqual(len(ProjectView.load(case.store).unfinished_integrations(case.pa)), 1)
            case.assertFinished(pending, result, f"chore(workline): plan_excluded {i1}")

        self.each(("event applied", "works applied", "removals applied"), body)

    def test_a_finished_plan_exclusion_asked_again_is_refused_as_before(self) -> None:
        w2, replan = self.replacement()
        rm.plan_exclude_work(self.store, w2, replan())

        refusal = self.assertRefusedUntouched(lambda: rm.plan_exclude_work(self.store, w2, replan()), SpecViolation)

        self.assertIn(f"plan_excluded is only for unstarted Works; {w2} is plan_excluded", str(refusal))


# --------------------------------------------------------------------------- another request is refused
class ChangedRequestTests(PlanExclusionCase):
    def test_a_changed_replan_is_refused_in_every_window(self) -> None:
        variants = {
            "new Work key": lambda case, replan: replan(key="w4"),
            "new Work name": lambda case, replan: replan(name="W3 renamed"),
            "desired state": lambda case, replan: replan(desired="changed"),
            "addition": lambda case, replan: replan(addition="planned_next"),
            "removal added": lambda case, replan: replan(removals=(case.relation_w2, case.relation_w1)),
            "removal dropped": lambda case, replan: replan(removals=()),
        }

        def body(case, window):
            w2, replan = case.replacement()
            pending = case.interrupt(lambda: rm.plan_exclude_work(case.store, w2, replan()), window)
            for label, change in variants.items():
                refusal = case.assertRefusedUntouched(lambda: rm.plan_exclude_work(case.store, w2, change(case, replan)))
                case.assertIn(pending["mutation_id"], str(refusal), label)
                case.assertIn("different request", str(refusal), label)
            # and the same request still finishes it
            result = rm.plan_exclude_work(case.store, w2, replan())
            case.assertFinished(pending, result, f"chore(workline): plan_excluded {w2}")

        self.each(("IDs reserved", "event applied", "removals applied", "committed"), body)


# --------------------------------------------------------------------------- the record has to prove it
class RecordProofTests(PlanExclusionCase):
    def test_a_record_without_its_request_is_left_for_reconciliation_in_every_window(self) -> None:
        def body(case, window):
            w2, replan = case.replacement()
            pending = case.interrupt(lambda: rm.plan_exclude_work(case.store, w2, replan()), window)
            case.edit_record(pending, lambda record: record["invocation"].pop("request"))

            refusal = case.assertRefusedUntouched(lambda: rm.plan_exclude_work(case.store, w2, replan()))

            case.assertIn(LEGACY, str(refusal))
            case.assertIn(pending["mutation_id"], str(refusal))

        self.each(("IDs reserved", "event applied", "committed"), body)

    def test_several_unfinished_records_are_left_for_reconciliation(self) -> None:
        w2, replan = self.replacement()
        pending = self.interrupt(lambda: rm.plan_exclude_work(self.store, w2, replan()), "works applied")
        twin = new_id("mutation")
        record = yamlish.load(MutationController(self.store).intent_path(pending["mutation_id"]).read_text(encoding="utf-8"))
        record["mutation_id"] = twin
        MutationController(self.store).intent_path(twin).write_text(yamlish.dump(record), encoding="utf-8")

        refusal = self.assertRefusedUntouched(lambda: rm.plan_exclude_work(self.store, w2, replan()))

        self.assertIn(twin, str(refusal))

    def test_an_edited_stage_is_left_for_reconciliation(self) -> None:
        def edit(kind, change):
            def edited(record):
                for effect in record["effects"]:
                    if effect["kind"] == kind:
                        change(effect["payload"])
            return edited

        cases = {
            "event type (applied)": ("event applied", edit("append_event", lambda p: p["record"].update(type="work_cancelled"))),
            "new Work content (recorded)": ("works recorded", edit("write_file", lambda p: p.update(content=p["content"].replace("w3", "else")))),
            "removal id (recorded)": ("removals recorded", edit("remove_relation", lambda p: p["record"].update(id=new_id("relation")))),
            "commit message (committed)": ("committed", edit("git_commit", lambda p: p.update(message=p["message"] + " edited"))),
        }

        def body(case, label):
            window, change = cases[label]
            w2, replan = case.replacement()
            pending = case.interrupt(lambda: rm.plan_exclude_work(case.store, w2, replan()), window)
            case.edit_record(pending, change)

            refusal = case.assertRefusedUntouched(lambda: rm.plan_exclude_work(case.store, w2, replan()))

            case.assertIn(f"{pending['mutation_id']} was recorded for this request, but its record holds", str(refusal))

        self.each(cases, body)

    def test_a_reservation_that_does_not_match_is_left_for_reconciliation(self) -> None:
        def renamed(record):
            record["reserved_ids"]["replan:works:work:zz"] = record["reserved_ids"].pop("replan:works:work:w3")

        def disagrees_with_stage(record):
            record["reserved_ids"]["replan:works:work:w3"] = new_id("work")

        cases = {
            "renamed key (IDs reserved)": ("IDs reserved", renamed),
            "Work ID the registration did not use (works applied)": ("works applied", disagrees_with_stage),
        }

        def body(case, label):
            window, change = cases[label]
            w2, replan = case.replacement()
            pending = case.interrupt(lambda: rm.plan_exclude_work(case.store, w2, replan()), window)
            case.edit_record(pending, change)

            refusal = case.assertRefusedUntouched(lambda: rm.plan_exclude_work(case.store, w2, replan()))

            case.assertIn(pending["mutation_id"], str(refusal))

        self.each(cases, body)

    def test_an_effect_taken_back_after_its_commit_was_recorded_is_left_for_reconciliation(self) -> None:
        """The commit is recorded only after every file effect is applied; one found unapplied was undone by someone else."""
        w2, replan = self.replacement()
        pending = self.interrupt(lambda: rm.plan_exclude_work(self.store, w2, replan()), "commit recorded")
        (removal,) = [e["payload"]["record"] for e in pending["effects"] if e["kind"] == "remove_relation"]
        relations = self.store.read_roadmap_relations() + [Relation.from_record(removal)]
        self.store.roadmap_yaml.write_text(render_relations(relations), encoding="utf-8")

        refusal = self.assertRefusedUntouched(lambda: rm.plan_exclude_work(self.store, w2, replan()))

        self.assertIn("not applied although a later stage is recorded", str(refusal))


# --------------------------------------------------------------------------- nothing is replayed ahead of a refusal
class ReplayBeforeApplyTests(PlanExclusionCase):
    def assertRefusedBeforeReplay(self, call, pending: dict, error) -> StopError:
        (event,) = [e["payload"]["record"]["id"] for e in pending["effects"] if e["kind"] == "append_event"]
        refusal = self.assertRefusedUntouched(call, error)  # no record touched, nothing written, committed or pushed
        self.assertNotIn(event, [e.id for e in ProjectView.load(self.store).events])
        return refusal

    def commit_hand_edit(self) -> None:
        git(self.store.root, "add", "-A", WORKLINE_DIR + "/events", WORKLINE_DIR + "/relations")
        git(self.store.root, "commit", "-q", "-m", "hand edit")

    def test_a_registration_the_project_no_longer_takes_is_refused_before_the_event_is_replayed(self) -> None:
        w2, replan = self.replacement()
        pending = self.interrupt(lambda: rm.plan_exclude_work(self.store, w2, replan()), "event recorded")
        with open(self.store.events_jsonl, "a", encoding="utf-8", newline="\n") as log:
            log.write('{"id":"%s","type":"phase_cancelled","entity":"%s","at":"2026-01-01T00:00:00+00:00"}\n' % (new_id("event"), self.pa))
        self.commit_hand_edit()

        refusal = self.assertRefusedBeforeReplay(lambda: rm.plan_exclude_work(self.store, w2, replan()), pending, SpecViolation)

        self.assertIn(f"work w3: Phase {self.pa} is cancelled", str(refusal))

    def test_a_replan_the_project_no_longer_takes_is_refused_before_the_event_is_replayed(self) -> None:
        w2, replan = self.replacement()
        pending = self.interrupt(lambda: rm.plan_exclude_work(self.store, w2, replan()), "event recorded")
        relations = self.store.read_roadmap_relations() + [Relation(new_id("relation"), "requires_completion", w2, self.w1)]
        self.store.roadmap_yaml.write_text(render_relations(relations), encoding="utf-8")
        self.commit_hand_edit()

        refusal = self.assertRefusedBeforeReplay(lambda: rm.plan_exclude_work(self.store, w2, replan()), pending, SpecViolation)

        self.assertIn("plan exclusion replan: structure would be invalid", str(refusal))

    def test_a_commit_that_could_not_separate_its_paths_is_refused_before_the_event_is_replayed(self) -> None:
        """The pre-existing change the first attempt noted overlaps what the commit would carry.

        A plan exclusion now refuses that change before its event (BL-041), so the record is the one a first attempt
        that went on anyway left behind.
        """
        w2, replan = self.replacement()
        roadmap_yaml = self.store.roadmap_yaml
        roadmap_yaml.write_text(roadmap_yaml.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaises(StopError) as refused:
            rm.plan_exclude_work(self.store, w2, replan())
        self.assertEqual((refused.exception.code, MutationController(self.store).list_pending()), ("dirty_overlap", []))
        with mock.patch.object(gitops, "ensure_separable_before_effects", lambda mutation, paths: None):
            pending = self.interrupt(lambda: rm.plan_exclude_work(self.store, w2, replan()), "event recorded")
        self.assertIn(f"{WORKLINE_DIR}/relations/roadmap.yaml", pending["notes"]["preexisting_dirty"])

        refusal = self.assertRefusedBeforeReplay(lambda: rm.plan_exclude_work(self.store, w2, replan()), pending, StopError)

        self.assertEqual(refusal.code, "dirty_overlap")


# --------------------------------------------------------------------------- the Git recovery contract carries the rest
class CommitRecoveryTests(DecisionCase):
    """A resumed plan exclusion reaches its Git stage and is carried there like any other decision.

    The decision's branch is recorded with its event and replan and taken over by
    its commit (BL-036); a recorded commit is made only on that branch (BL-035),
    on top of independent commits (BL-032), and never recognised by its message
    alone (BL-033). A record that does not show the branch is not resumed by
    guessing it, and that is a different refusal from a record without a request.
    """

    def replacement(self):
        """The call that excludes W2 of Phase A and replaces it by W3 in front of the integration."""
        (removed,) = [r.id for r in ProjectView.load(self.store).roadmap_relations
                      if (r.type, r.from_id, r.to) == ("requires_completion", self.w2, self.integration)]
        replan = Replan(
            remove_relation_ids=(removed,),
            add_relations=(RelationSpec("requires_completion", "w3", self.integration),),
            new_works={"w3": WorkSpec("W3", "w3", phase_id=self.pa, roadmap_id=self.rid)},
        )
        return lambda: rm.plan_exclude_work(self.store, self.w2, replan)

    def message(self) -> str:
        return f"chore(workline): plan_excluded {self.w2}"

    def record(self, pending: dict) -> dict:
        (record,) = [r for r in MutationController(self.store).list_records() if r["mutation_id"] == pending["mutation_id"]]
        return record

    def test_a_commit_recorded_and_not_made_is_made_by_the_same_retry(self) -> None:
        for index, window in enumerate(("commit recorded", "commit refused")):
            with self.subTest(window=window):
                self.build(f"commit-{index}")
                call = self.replacement()
                pending = self.interrupt(call, r"^finalize$", window)
                base = self.recorded_commit(pending)["base_head"]
                executed: list[str] = []

                result = self.counting(call, executed)

                self.assertEqual((result.status, result.mutation_id), ("plan_excluded", pending["mutation_id"]))
                self.assertEqual(executed, ["git_commit", "git_push"])  # nothing decided is applied again
                self.assertEqual(self.parent(self.made_with(self.message(), base)), base)
                self.assertFinalizedHere(pending)

    def test_a_recorded_commit_is_made_on_top_of_an_independent_commit(self) -> None:
        self.build()
        call = self.replacement()
        pending = self.interrupt(call, r"^finalize$", "commit recorded")
        moved_to = self.human_commit({"notes.md": "notes\nby a person\n"}, "docs: a note")
        executed: list[str] = []

        result = self.counting(call, executed)

        self.assertEqual((result.status, result.mutation_id), ("plan_excluded", pending["mutation_id"]))
        self.assertEqual(executed, ["git_commit", "git_push"])
        self.assertEqual(self.parent(self.made_with(self.message(), moved_to)), moved_to)
        self.assertFinalizedHere(pending)

    def test_another_branch_neither_replays_nor_records_nor_commits(self) -> None:
        windows = {
            "event recorded": (lambda call: self.stop_in(after_recording(r"^event$"), call), "no recorded commit finalizes"),
            "removals applied": (lambda call: self.stop_in(after_applying(r"^replan:remove$"), call), "no recorded commit finalizes"),
            "commit recorded": (lambda call: self.interrupt(call, r"^finalize$", "commit recorded"), "applied with unexpected result"),
        }
        for index, (window, (stop, fragment)) in enumerate(windows.items()):
            with self.subTest(window=window):
                self.build(f"branch-{index}")
                call = self.replacement()
                pending = stop(call)
                decided_at = self.head()
                git(self.root, "checkout", "-q", "-b", "side")

                self.assertStopsUntouched(call, fragment=fragment)  # no event, Work, relation, removal or Git stage

                git(self.root, "checkout", "-q", "main")
                call()
                self.assertFinalizedHere(pending)
                effects = self.record(pending)["effects"]
                decided = [effect.get(DECIDED_ON) for effect in effects if effect["kind"] in FILE_EFFECT_KINDS]
                self.assertEqual(decided, [{"branch": MAIN, "head": decided_at}] * len(decided))
                (commit,) = [effect["payload"] for effect in effects if effect["kind"] == "git_commit"]
                self.assertEqual((commit["branch"], commit["base_head"]), (MAIN, decided_at))  # the decision handed on

    def test_a_same_message_commit_is_not_taken_for_the_recorded_commit(self) -> None:
        self.build()
        call = self.replacement()
        pending = self.interrupt(call, r"^finalize$", "commit recorded")
        foreign = self.human_commit({"notes.md": "notes\nsomeone else's change\n"}, self.message())
        executed: list[str] = []

        result = self.counting(call, executed)

        self.assertEqual((result.status, result.mutation_id), ("plan_excluded", pending["mutation_id"]))
        self.assertEqual(executed, ["git_commit", "git_push"])
        made = self.made_with(self.message(), foreign)
        self.assertEqual(self.parent(made), foreign)
        self.assertEqual(git(self.root, "show", "--name-only", "--format=", foreign).split(), ["notes.md"])
        self.assertIn(EVENT_LOG, git(self.root, "show", "--name-only", "--format=", made).split())
        self.assertFinalizedHere(pending)

    def test_a_record_that_does_not_show_its_branch_or_its_request_is_not_resumed(self) -> None:
        cases = {
            "a commit without its branch": (
                "commit recorded", lambda pending: self.edit_recorded_commit(pending, lambda payload: payload.pop("branch")),
                "applied with unexpected result"),
            "decisions without their branch": ("removals applied", self.strip_bindings, "without the branch they were decided on"),
            "a record without its request": ("removals applied", self.strip_request, LEGACY),
        }
        for index, (label, (window, strip, fragment)) in enumerate(cases.items()):
            with self.subTest(label):
                self.build(f"unshown-{index}")
                call = self.replacement()
                if window == "commit recorded":
                    pending = self.interrupt(call, r"^finalize$", window)
                else:
                    pending = self.stop_in(after_applying(r"^replan:remove$"), call)
                strip(pending)

                refusal = self.assertStopsUntouched(call, fragment=fragment)

                if fragment != LEGACY:
                    self.assertNotIn(LEGACY, refusal.message)

    def strip_request(self, pending: dict) -> None:
        """Rewrite the record as an implementation before BL-029 wrote it: the invocation has no request."""
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        record["invocation"].pop("request")
        path.write_text(yamlish.dump(record), encoding="utf-8")


# --------------------------------------------------------------------------- START's own resume (BL-031)
class StartTerminalFinalizationTests(PlanExclusionCase):
    """A standalone plan exclusion and START share an owner, never a record.

    START finishes a terminal finalization it recorded before anything else
    (BL-031, ``start._completion_to_finish``), reading only the mutation its own
    invocation opens. A standalone plan exclusion resumes only a record of its own
    slot. Neither reads the other's record; each still stops on the other's
    unfinished mutation through the write scope, exactly as before.
    """

    def test_start_never_reads_an_unfinished_plan_exclusion_as_its_own(self) -> None:
        z = create_standalone_work(self.store, WorkSpec("Z", "z")).work_id
        s2, replan = self.standalone_replacement()
        pending = self.interrupt(lambda: st.plan_exclude_standalone_work(self.store, s2, replan), "removals applied", st)
        seen: list[dict] = []
        real = st._completion_to_finish

        def watch(mutation, work_id, mode):
            seen.append(mutation.invocation)
            return real(mutation, work_id, mode)

        with mock.patch.object(st, "_completion_to_finish", watch):
            before = self.snapshot()
            with self.assertRaises(ReconcileRequired) as refused:
                st.start(self.store, z, "single-work", completing_executor(self.store))
            self.assertEqual(self.snapshot(), before)
            self.assertIn(pending["mutation_id"], str(refused.exception))  # stopped on the write scope, when opening
            self.assertEqual(seen, [])  # before START ever read a record as its own

            result = st.plan_exclude_standalone_work(self.store, s2, replan)
            self.assertEqual(result.mutation_id, pending["mutation_id"])
            self.assertEqual(seen, [])  # the plan exclusion's own resume reads nothing of START's

            self.assertEqual(st.start(self.store, z, "single-work", completing_executor(self.store)).status, "completed")
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(self.dirty(), [])

    def test_a_plan_exclusion_never_takes_over_starts_unfinished_completion(self) -> None:
        z = create_standalone_work(self.store, WorkSpec("Z", "z")).work_id
        t = create_standalone_work(self.store, WorkSpec("T", "t")).work_id
        with after_applying(rf"^{z}:lifecycle:1$"), self.assertRaises(Interrupted):
            st.start(self.store, z, "single-work", completing_executor(self.store))
        (start_record,) = MutationController(self.store).list_pending()
        before = self.snapshot()

        # The same Work: START's record is not in the plan exclusion's slot, so it is neither resumed nor refused
        # as a plan exclusion without a request; the precondition reads Z as before.
        with self.assertRaises(SpecViolation) as same_work:
            st.plan_exclude_standalone_work(self.store, z)
        self.assertIn(f"plan_excluded is only for unstarted Works; {z} is completed", str(same_work.exception))
        # Another Work: stopped on START's write scope when the mutation is opened.
        with self.assertRaises(ReconcileRequired) as other_work:
            st.plan_exclude_standalone_work(self.store, t)
        self.assertIn(start_record["mutation_id"], str(other_work.exception))
        self.assertNotIn(LEGACY, str(other_work.exception))
        self.assertEqual(self.snapshot(), before)

        # START finishes its own completion (BL-031), and the plan exclusion then goes ahead.
        finished = st.start(self.store, z, "single-work", completing_executor(self.store))
        self.assertEqual((finished.status, finished.mutation_id), ("completed", start_record["mutation_id"]))
        self.assertEqual(st.plan_exclude_standalone_work(self.store, t).status, "plan_excluded")
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(self.head(), self.remote_head())


# --------------------------------------------------------------------------- neighbours stay as they were
class NeighbourTests(PlanExclusionCase):
    def test_an_uninterrupted_plan_exclusion_is_unchanged(self) -> None:
        w2, replan = self.replacement()

        result, stages, executed = self.watching(lambda: rm.plan_exclude_work(self.store, w2, replan()))

        self.assertEqual(stages, ["event", "replan:works", "replan:remove", "finalize"])  # BL-028's order
        self.assertEqual(executed, FRESH)
        self.assertEqual(result.status, "plan_excluded")
        self.assertEqual(MutationController(self.store).list_records(), [])  # cleaned up (BL-019)
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(self.head(), self.remote_head())

    def test_a_start_cancel_after_its_event_finishes_from_its_own_decision(self) -> None:
        """A START cancel is carried on from the decision it recorded (BL-030), never as a plan exclusion."""
        entry = self.phase(confirmation=True)
        w1, i1, c1 = entry.work_ids["w1"], entry.integration_id, entry.confirmation_id
        st.start(self.store, w1, "single-work", completing_executor(self.store))
        replan = Replan(
            remove_relation_ids=(self.relation("requires_completion", w1, i1), self.relation("requires_completion", i1, c1)),
            add_relations=(RelationSpec("requires_completion", w1, "i2"), RelationSpec("requires_completion", "i2", c1)),
            new_works={"i2": self.spec("I2", work_kind="phase_integration_check")},
        )
        cancel = lambda: st.start(self.store, i1, "single-work", scripted_executor({i1: [st.Cancel(replan, "scope")]}))  # noqa: E731
        with after_applying(r":cancel:\d+:remove$"), self.assertRaises(Interrupted):
            cancel()
        (pending,) = MutationController(self.store).list_pending()
        resumed: list[object] = []
        real = ops._resume_plan_exclusion

        def watch(*args, **kwargs):
            resumed.append(args)
            return real(*args, **kwargs)

        with mock.patch.object(ops, "_resume_plan_exclusion", watch), mock.patch.object(st, "_resume_plan_exclusion", watch):
            result, stages, executed = self.watching(cancel)

        self.assertEqual((result.status, result.mutation_id), ("cancelled", pending["mutation_id"]))
        self.assertEqual(resumed, [])  # the plan exclusion's resume never reads it
        self.assertEqual(stages, ["commit:0"])
        self.assertEqual(executed, ["git_commit", "git_push"])
        self.assertEqual(len(self.named("I2")), 1)
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(self.head(), self.remote_head())

    def test_another_operation_on_the_target_never_takes_the_record_over(self) -> None:
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B")})
        pb = roadmap.phase_ids["b"]
        pending = self.interrupt(lambda: rm.plan_exclude_phase(self.store, pb), "event recorded")

        self.assertRefusedUntouched(lambda: rm.cancel_phase(self.store, pb))

        self.assertEqual(rm.plan_exclude_phase(self.store, pb).mutation_id, pending["mutation_id"])


if __name__ == "__main__":
    unittest.main()
