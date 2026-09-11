from __future__ import annotations

import unittest

from helpers import WorklineTestCase, completing_executor, git
from workline import start as st
from workline.create import RelatedSpec, RelationSpec, WorkSpec, create_standalone_work, register_works
from workline.errors import SpecViolation, StopError, ValidationError
from workline.mutation import MutationController, WriteScope
from workline.oplock import project_operation
from workline.state import ProjectView
from workline.validate import validate_project


class CreateRegistrationCoreTests(WorklineTestCase):
    def test_roadmap_child_invocation_registers_without_git(self) -> None:
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        phase_id = roadmap.phase_ids["a"]
        head = git(store.root, "rev-parse", "HEAD").strip()
        # the registration core joins the Project execution lock its caller holds
        lock = project_operation(store, "registration-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        controller = MutationController(store)
        mutation = controller.open("roadmap", {"operation": "phase-entry", "phase_id": phase_id}, WriteScope(entities=(phase_id,)))
        spec = WorkSpec("W1", "w1 done", phase_id=phase_id, roadmap_id=roadmap.roadmap_id,
                        related=(RelatedSpec("must_read", "README.md"), RelatedSpec("conditional_must_read", "docs/x.md", {"kind": "path_glob", "pattern": "src/*.py"})))
        result = register_works(mutation, "works", {"w1": spec, "w2": WorkSpec("W2", "w2 done", phase_id=phase_id, roadmap_id=roadmap.roadmap_id)},
                                [RelationSpec("planned_next", "w1", "w2")])
        view = ProjectView.load(store)
        w1 = view.works[result.work_ids["w1"]]
        self.assertEqual(w1.meta["origin"], {"type": "roadmap", "roadmap_id": roadmap.roadmap_id, "phase_id": phase_id})
        self.assertEqual(w1.phase_id, phase_id)
        self.assertEqual(w1.display, "W-01")
        self.assertNotIn("state", w1.meta)
        self.assertNotIn("work_kind", w1.meta)
        self.assertEqual(view.work_state(w1.id).state, "unstarted")
        self.assertEqual(view.events, [])
        self.assertEqual([r.type for r in view.related_from(w1.id)], ["must_read", "conditional_must_read"])
        self.assertEqual([(r.type, r.from_id, r.to) for r in view.roadmap_relations if r.from_id == w1.id], [("planned_next", w1.id, result.work_ids["w2"])])
        # registration core is not a Git finalizer
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(mutation.status, "pending")
        # the same mutation resumes with the same IDs and does not duplicate
        again = register_works(mutation, "works", {"w1": spec, "w2": WorkSpec("W2", "w2 done", phase_id=phase_id, roadmap_id=roadmap.roadmap_id)},
                               [RelationSpec("planned_next", "w1", "w2")])
        self.assertEqual(again.work_ids, result.work_ids)
        self.assertEqual(len(ProjectView.load(store).works), 2)

    def test_registration_core_rejects_spec_violations(self) -> None:
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        phase_id = roadmap.phase_ids["a"]
        lock = project_operation(store, "registration-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        mutation = MutationController(store).open("roadmap", {"operation": "phase-entry", "phase_id": phase_id}, WriteScope())
        with self.assertRaises(ValidationError):  # vague condition
            register_works(mutation, "s1", {"w": WorkSpec("W", "d", phase_id=phase_id, roadmap_id=roadmap.roadmap_id,
                                                          related=(RelatedSpec("conditional_must_read", "x", {"kind": "path_glob", "pattern": "if relevant"}),))})
        with self.assertRaises(ValidationError):  # standalone special work
            register_works(mutation, "s2", {"w": WorkSpec("W", "d", work_kind="phase_integration_check")})
        with self.assertRaises(ValidationError):  # confirmation_target on normal work
            register_works(mutation, "s3", {"w": WorkSpec("W", "d", phase_id=phase_id, roadmap_id=roadmap.roadmap_id, confirmation_target="w")})
        with self.assertRaises(SpecViolation):  # two integrations in one phase
            register_works(mutation, "s4", {
                "i1": WorkSpec("I1", "d", phase_id=phase_id, roadmap_id=roadmap.roadmap_id, work_kind="phase_integration_check"),
                "i2": WorkSpec("I2", "d", phase_id=phase_id, roadmap_id=roadmap.roadmap_id, work_kind="phase_integration_check"),
            })
        self.assertEqual(ProjectView.load(store).works, {})

    def test_start_child_invocation_participates_in_start_mutation(self) -> None:
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        entry = self.simple_entry(store, roadmap.phase_ids["a"])
        w1 = entry.work_ids["w1"]
        seen_mutations: list[str] = []

        def executor(ctx: st.ExecutionContext):
            seen_mutations.append(ctx.mutation_id)
            if ctx.attempt == 1:
                return st.Derive({"fix": st.DerivedWork("Fix", "fixed", derivation_detail="found a gap")})
            (store.root / "r.txt").write_text("x", encoding="utf-8")
            return st.Completed(("r.txt",))

        result = st.start(store, w1, "single-work", executor)
        self.assertEqual(result.status, "completed")
        view = ProjectView.load(store)
        fix = next(w for w in view.works.values() if w.name == "Fix")
        self.assertEqual(fix.phase_id, roadmap.phase_ids["a"])
        derived = [r for r in view.roadmap_relations if r.type == "derived"]
        self.assertEqual([(r.from_id, r.to) for r in derived], [(w1, fix.id)])
        self.assertTrue(any(p.name.startswith("der_") for p in store.derivations.iterdir()))
        mutation = MutationController(store).load(result.mutation_id)
        self.assertTrue(any(e["kind"] == "write_file" and fix.id in e["payload"]["path"] for e in mutation.effects))
        self.assertEqual(mutation.status, "completed")
        self.assertIn(fix.path, git(store.root, "ls-files"))


class CreateDirectInvocationTests(WorklineTestCase):
    def test_standalone_direct_creation_commits_and_pushes(self) -> None:
        store = self.new_project(remote=True)
        result = create_standalone_work(store, WorkSpec("Standalone", "done standalone", related=(RelatedSpec("obey", "docs/rules.md"),)))
        view = ProjectView.load(store)
        work = view.works[result.work_id]
        self.assertEqual(work.meta["origin"], {"type": "standalone"})
        self.assertIsNone(work.phase_id)
        self.assertEqual(view.work_state(work.id).state, "unstarted")
        self.assertEqual(git(store.root, "log", "-1", "--format=%s").strip(), "chore(workline): create W-01")
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), git(self.remote_path(), "rev-parse", "main").strip())
        self.assertEqual(validate_project(store), [])
        self.assertEqual(git(store.root, "status", "--porcelain").strip().splitlines(), [l for l in git(store.root, "status", "--porcelain").splitlines() if ".workline/runtime" in l])

    def test_direct_invocation_rejects_phase_and_special_works(self) -> None:
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        with self.assertRaises(SpecViolation):
            create_standalone_work(store, WorkSpec("X", "d", phase_id=roadmap.phase_ids["a"], roadmap_id=roadmap.roadmap_id))
        with self.assertRaises(SpecViolation):
            create_standalone_work(store, WorkSpec("X", "d", work_kind="human_confirmation"))

    def test_duplicate_retry_resumes_same_work(self) -> None:
        store = self.new_project(remote=True)
        # The push fails transiently while the approved destination stays the
        # same: the remote is unreachable, not a different repository.
        bare = self.remote_path()
        away = self.tmp / "proj-remote-away.git"
        bare.rename(away)
        spec = WorkSpec("Retry", "retry done")
        with self.assertRaises(StopError):
            create_standalone_work(store, spec)
        works_before = [p.name for p in store.entity_dir("work").iterdir()]
        self.assertEqual(len(works_before), 1)
        away.rename(bare)
        result = create_standalone_work(store, spec)
        self.assertTrue(result.resumed)
        self.assertEqual([p.name for p in store.entity_dir("work").iterdir()], works_before)
        self.assertEqual(git(store.root, "log", "--format=%s").splitlines()[0], "chore(workline): create W-01")
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), git(self.remote_path(), "rev-parse", "main").strip())
        # a later, independent creation of the same name is a new Work (the mutation completed)
        second = create_standalone_work(store, spec)
        self.assertFalse(second.resumed)
        self.assertEqual(len(list(store.entity_dir("work").iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
