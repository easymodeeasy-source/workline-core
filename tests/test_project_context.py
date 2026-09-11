"""BL-001: an established Workline Project is changed only from its own context.

The invocation context is resolved from the working directory when a top-level
operation starts. A caller working in another Project, in the Workline root or
anywhere else STOPs as ``foreign_project_mutation`` before the execution lock
and leaves the target exactly as it was, while reading another Project stays
open. Initial Project開始 is the pre-project exception; its mutation is
authorized only by a running ``project_start()``, for its own root.
"""

from __future__ import annotations

import contextlib
import hashlib
import inspect
import io
import os
from pathlib import Path
import shutil
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, WorklineTestCase, completing_executor, cwd, git, scripted_executor
from test_operation_lock import ExecutionLockTestCase

from workline import bootstrap as bs
from workline import gitcmd, oplock
from workline import project_start as ps
from workline import roadmap as rm
from workline import start as st
from workline.cli import main as cli_main
from workline.context import (
    GIT_REPOSITORY,
    NO_CONTEXT,
    PROJECT,
    pre_project_authorized,
    resolve_invocation_context,
    same_directory,
)
from workline.create import RelatedSpec, WorkSpec, create_standalone_work
from workline.errors import ForeignProjectMutation, ProjectOperationBusy, StopError
from workline.mutation import MutationController, WriteScope
from workline.phase_create import PhaseSpec
from workline.push_pin import pin_push_destination
from workline.state import ProjectView
from workline.store import BOOTSTRAP_REL_PATH, PROJECT_YAML_REL, ProjectStore, PushPin
from workline.validate import validate_project, validate_structure


def tree(root: Path) -> dict[str, str]:
    """Every directory and file under ``root``, ``.git`` and runtime included, file contents hashed."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "<dir>"
        for path in sorted(root.rglob("*"))
    }


def forget_lock_area(store: ProjectStore) -> None:
    """Remove the runtime lock area, so a test can show that a foreign caller never creates it."""
    shutil.rmtree(store.locks, ignore_errors=True)


class ContextResolutionTests(WorklineTestCase):
    def test_a_project_wins_and_the_nearest_git_boundary_ends_the_walk(self) -> None:
        project = self.new_project("proj")
        self.assertTrue((project.root / ".git").is_dir())  # both markers in one directory: a Project
        deep = project.root / "docs" / "deep"
        deep.mkdir(parents=True)
        nested = project.root / "vendor" / "lib"
        (nested / "src").mkdir(parents=True)
        git(nested, "init", "-b", "main")
        linked = self.new_dir("linked-checkout")
        (linked / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
        (linked / "sub").mkdir()
        repo = self.new_dir("repo")
        git(repo, "init", "-b", "main")
        (repo / "a" / "b").mkdir(parents=True)

        cases = {
            "project root": (project.root, PROJECT, project.root),
            "project subdirectory": (deep, PROJECT, project.root),
            "nested repository inside the project": (nested / "src", GIT_REPOSITORY, nested),
            "a .git file": (linked / "sub", GIT_REPOSITORY, linked),
            "plain repository": (repo / "a" / "b", GIT_REPOSITORY, repo),
        }
        for label, (where, kind, root) in cases.items():
            with self.subTest(case=label), cwd(where):
                context = resolve_invocation_context()
                self.assertEqual(context.kind, kind)
                self.assertTrue(same_directory(context.root, root), (context.root, root))

        plain = self.new_dir("plain")
        with cwd(plain):
            outside = resolve_invocation_context()
        self.assertNotEqual(outside.kind, PROJECT)
        if outside.kind == NO_CONTEXT:
            self.assertIsNone(outside.root)

    def test_directory_identity_is_not_string_identity(self) -> None:
        one, two = self.new_dir("one"), self.new_dir("two")
        self.assertTrue(same_directory(one, Path(f"{one}{os.sep}")))
        self.assertTrue(same_directory(one, two / ".." / "one"))
        if os.name == "nt":
            self.assertTrue(same_directory(one, Path(str(one).swapcase())))
        self.assertFalse(same_directory(one, two))
        self.assertFalse(same_directory(one, self.tmp / "missing"))


class ForeignMutationTests(WorklineTestCase):
    def test_the_projects_own_context_changes_it_from_anywhere_inside(self) -> None:
        store = self.new_project()
        deep = store.root / "docs" / "deep"
        deep.mkdir(parents=True)
        roadmap = self.simple_roadmap(store)
        with cwd(deep):
            created = create_standalone_work(store, WorkSpec("From a subdirectory", "done"))
            entry = self.simple_entry(store, roadmap.phase_ids["a"])
        view = ProjectView.load(store)
        self.assertIn(created.work_id, view.works)
        self.assertIn(entry.work_ids["w1"], view.works)
        self.assertEqual(validate_project(store), [])

    def test_start_from_another_project_writes_nothing(self) -> None:
        b = self.new_project("b")
        work = create_standalone_work(b, WorkSpec("Theirs", "done")).work_id
        a = self.new_project("a")
        forget_lock_area(b)
        before_b, before_a = tree(b.root), tree(a.root)
        ran: list[str] = []
        with self.assertRaises(ForeignProjectMutation) as ctx:
            st.start(b, work, "single-work", completing_executor(b, ran))
        self.assertEqual(ctx.exception.code, "foreign_project_mutation")
        self.assertIn(str(b.root), ctx.exception.message)
        self.assertIn(str(a.root), ctx.exception.message)
        self.assertEqual(ran, [])
        self.assertEqual(tree(b.root), before_b)
        self.assertEqual(tree(a.root), before_a)
        self.assertFalse(b.locks.exists())

    def test_roadmap_operations_from_another_project_write_nothing(self) -> None:
        b = self.new_project("b")
        roadmap = self.simple_roadmap(b, {"a": ("Phase A", "A done"), "b": ("Phase B", "B done")})
        phase_a, phase_b = roadmap.phase_ids["a"], roadmap.phase_ids["b"]
        entry = self.simple_entry(b, phase_a, {"w1": "W1 done", "w2": "W2 done"})
        w1, w2 = entry.work_ids["w1"], entry.work_ids["w2"]
        standalone = create_standalone_work(b, WorkSpec("Standalone", "done")).work_id
        self.new_project("a")
        forget_lock_area(b)
        before = tree(b.root)
        attempts = {
            "roadmap-create": lambda: self.simple_roadmap(b),
            "phase-add": lambda: rm.add_phases(b, roadmap.roadmap_id, {"late": PhaseSpec("Late", "late done")}),
            "phase-entry": lambda: self.simple_entry(b, phase_b),
            "phase-hold": lambda: rm.hold_phase(b, phase_a),
            "phase-cancel": lambda: rm.cancel_phase(b, phase_b),
            "roadmap-hold": lambda: rm.hold_roadmap(b, roadmap.roadmap_id),
            "roadmap-resume": lambda: rm.resume_roadmap(b, roadmap.roadmap_id),
            "phase-plan-exclude": lambda: rm.plan_exclude_phase(b, phase_b),
            "work-plan-exclude": lambda: rm.plan_exclude_work(b, w2),
            "related-maintenance": lambda: rm.maintain_work_related(b, w2, add=(RelatedSpec("must_read", "README.md"),)),
            "achievement": lambda: rm.evaluate_achievement(b, roadmap.roadmap_id, "achieved"),
            "handoff": lambda: rm.handoff(b, phase_a, completing_executor(b), w1),
            "start": lambda: st.start(b, w1, "single-work", completing_executor(b)),
            "standalone-plan-exclude": lambda: st.plan_exclude_standalone_work(b, standalone),
        }
        for operation, attempt in attempts.items():
            with self.subTest(operation=operation):
                with self.assertRaises(ForeignProjectMutation):
                    attempt()
        self.assertEqual(tree(b.root), before)
        self.assertFalse(b.locks.exists())

    def test_direct_create_from_another_project_stops(self) -> None:
        b = self.new_project("b")
        self.new_project("a")
        before = tree(b.root)
        with self.assertRaises(ForeignProjectMutation):
            create_standalone_work(b, WorkSpec("Theirs", "done"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli_main(["create-work", str(b.root), "--name", "Theirs", "--desired-state", "done"])
        self.assertEqual(code, 1)
        self.assertIn("STOP [foreign_project_mutation]", out.getvalue())
        self.assertEqual(tree(b.root), before)
        self.assertFalse(b.locks.exists())

    def test_maintenance_from_another_project_stops(self) -> None:
        b = self.new_project("b", remote=True, pin=False)
        git(b.root, "rm", "-q", "--cached", BOOTSTRAP_REL_PATH)
        (b.root / BOOTSTRAP_REL_PATH).unlink()
        git(b.root, "commit", "-m", "a Project from before the bootstrap")
        git(b.root, "push", "-u", "origin", "main")
        self.new_project("a")
        before, remote_before = tree(b.root), tree(self.remote_path("b"))
        attempts = {
            "bootstrap-backfill": lambda: bs.backfill_bootstrap(b.root),
            "push-destination-pin": lambda: pin_push_destination(b.root, [self.remote_url("b")]),
        }
        for operation, attempt in attempts.items():
            with self.subTest(operation=operation):
                with self.assertRaises(ForeignProjectMutation):
                    attempt()
        self.assertEqual(tree(b.root), before)
        self.assertEqual(tree(self.remote_path("b")), remote_before)
        self.assertFalse(b.locks.exists())

        # from inside B the same maintenance simply runs
        with cwd(b.root):
            pin_push_destination(b.root, [self.remote_url("b")])
            self.assertEqual(bs.backfill_bootstrap(b.root).status, "created")
        self.assertEqual(b.read_push_pin(), PushPin("origin", (self.remote_url("b"),)))

    def test_reading_another_project_is_allowed_and_writes_nothing(self) -> None:
        b = self.new_project("b")
        roadmap = self.simple_roadmap(b)
        entry = self.simple_entry(b, roadmap.phase_ids["a"])
        self.new_project("a")
        forget_lock_area(b)
        before = tree(b.root)

        view = ProjectView.load(b)
        work = view.works[entry.work_ids["w1"]]
        self.assertEqual(validate_project(b), [])
        self.assertEqual(validate_structure(view), [])
        rm.startable_phases(b, roadmap.roadmap_id)
        self.assertTrue(rm.diagnose_no_candidate(b, roadmap.roadmap_id))
        self.assertEqual(MutationController(b).list_pending(), [])
        self.assertEqual(rm.evaluate_achievement(b, roadmap.roadmap_id, "not_achieved").status, "not_ready")
        self.assertIn(work.path, st.reading_plan(b, view, work))
        self.assertTrue(bs.is_established_project(b))
        self.assertEqual(bs.bootstrap_state(b), bs.MATCHING)
        self.assertTrue(bs.bootstrap_tracked(b))
        self.assertIsNone(oplock.read_holder(b))
        self.assertEqual(gitcmd.current_branch(b.root), "main")
        self.assertIsNotNone(gitcmd.head_commit(b.root))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli_main(["validate-project", str(b.root)]), 0)
        self.assertIn("PASS", out.getvalue())

        self.assertEqual(tree(b.root), before)
        self.assertFalse(b.locks.exists())

    def test_an_achievement_judgement_reads_but_recording_it_is_a_mutation(self) -> None:
        b = self.new_project("b")
        roadmap = self.simple_roadmap(b)
        entry = self.simple_entry(b, roadmap.phase_ids["a"])
        rm.handoff(b, roadmap.phase_ids["a"], completing_executor(b), entry.entry_work_id)
        self.new_project("a")
        before = tree(b.root)
        for judgement, status in (
            ("human_confirmation", "human_confirmation_required"),
            ("not_achieved", "not_achieved"),
            ("desired_state_change", "desired_state_change_required"),
        ):
            with self.subTest(judgement=judgement):
                self.assertEqual(rm.evaluate_achievement(b, roadmap.roadmap_id, judgement).status, status)
        with self.assertRaises(ForeignProjectMutation):
            rm.evaluate_achievement(b, roadmap.roadmap_id, "achieved")
        self.assertEqual(tree(b.root), before)

        with cwd(b.root):
            self.assertEqual(rm.evaluate_achievement(b, roadmap.roadmap_id, "achieved").status, "achieved")

    def test_a_nested_repository_is_not_its_parent_project(self) -> None:
        store = self.new_project()
        nested = store.root / "vendor" / "lib"
        (nested / "src").mkdir(parents=True)
        git(nested, "init", "-b", "main")
        before = tree(store.root)
        with cwd(nested / "src"):
            context = resolve_invocation_context()
            self.assertEqual(context.kind, GIT_REPOSITORY)
            self.assertTrue(same_directory(context.root, nested))
            with self.assertRaises(ForeignProjectMutation):
                create_standalone_work(store, WorkSpec("From a nested repository", "done"))
        self.assertEqual(tree(store.root), before)


class PathIdentityTests(WorklineTestCase):
    def _directory_link(self, target: Path, link: Path) -> Path | None:
        """A junction (Windows) or symlink to ``target``, or None where the platform refuses one."""
        try:
            if os.name == "nt":
                import _winapi

                _winapi.CreateJunction(str(target), str(link))
            else:
                os.symlink(target, link, target_is_directory=True)
        except (ImportError, AttributeError, OSError):
            return None
        # rmdir removes a junction itself and never what it points to
        self.addCleanup(os.rmdir if os.name == "nt" else os.unlink, link)
        return link

    def test_the_same_project_under_another_spelling_is_not_foreign(self) -> None:
        store = self.new_project("b")
        spellings = {"relative": Path("."), "trailing separator": Path(f"{store.root}{os.sep}")}
        if os.name == "nt":
            spellings["case"] = Path(str(store.root).swapcase())
        link = self._directory_link(store.root, self.tmp / "b-link")
        if link is not None:
            spellings["junction or symlink"] = link
        for label, spelled in spellings.items():
            with self.subTest(spelling=label):
                created = create_standalone_work(ProjectStore(spelled), WorkSpec(f"Spelled {label}", "done"))
                self.assertIn(created.work_id, ProjectView.load(store).works)

        if link is None:
            return
        with cwd(link):  # working inside the Project through the link
            create_standalone_work(store, WorkSpec("Through the link", "done"))
        self.new_project("a")  # through the link B is still B, and B is foreign here
        with self.assertRaises(ForeignProjectMutation):
            create_standalone_work(ProjectStore(link), WorkSpec("Foreign through the link", "done"))


class ProjectStartContextTests(WorklineTestCase):
    def test_project_start_runs_from_any_context_that_is_not_another_project(self) -> None:
        plain = self.new_dir("plain")
        contexts = {
            "workline-root": lambda target: WORKLINE_ROOT,
            "plain-directory": lambda target: plain,
            "the-target-itself": lambda target: target,
            "inside-the-target": lambda target: target / "sub",
        }
        for label, where in contexts.items():
            with self.subTest(context=label):
                target = self.new_dir(f"target-{label}")
                (target / "sub").mkdir()
                with cwd(where(target)):
                    self.assertNotEqual(resolve_invocation_context().kind, PROJECT)
                    self.assertEqual(ps.project_start(target, WORKLINE_ROOT).status, "initialized")
                self.assertEqual(validate_project(ProjectStore(target)), [])

    def test_project_start_from_inside_another_project_writes_nothing(self) -> None:
        a = self.new_project("a")
        target = self.new_dir("b")
        before = tree(a.root)
        for where in (a.root, a.root / ".workline"):
            with self.subTest(where=where.name), cwd(where):
                with self.assertRaises(ForeignProjectMutation) as ctx:
                    ps.project_start(target, WORKLINE_ROOT)
                self.assertEqual(ctx.exception.code, "foreign_project_mutation")
        self.assertEqual(list(target.iterdir()), [])
        self.assertEqual(tree(a.root), before)

    def test_no_workline_project_is_created_inside_an_established_one(self) -> None:
        a = self.new_project("a")
        # the parent repository ignores the folder, so Git alone would allow a new repository there
        (a.root / ".gitignore").write_text("nested/\n", encoding="utf-8")
        git(a.root, "add", ".gitignore")
        git(a.root, "commit", "-m", "ignore nested")
        nested = a.root / "nested"
        nested.mkdir()
        before = tree(a.root)
        with cwd(WORKLINE_ROOT):
            with self.assertRaises(StopError) as ctx:
                ps.project_start(nested, WORKLINE_ROOT)
        self.assertEqual(ctx.exception.code, "nested_workline_project")
        for where in (a.root, nested):
            with self.subTest(where=where.name), cwd(where):
                with self.assertRaises(ForeignProjectMutation):
                    ps.project_start(nested, WORKLINE_ROOT)
        self.assertEqual(list(nested.iterdir()), [])
        self.assertEqual(tree(a.root), before)


class MutationControllerAuthorizationTests(WorklineTestCase):
    SCOPE = WriteScope(files=(PROJECT_YAML_REL,))

    def test_the_project_start_owner_name_authorizes_nothing(self) -> None:
        b = self.new_project("b")
        plain = self.new_dir("plain")
        before = tree(b.root)
        cases = (
            ("an established Project, from its own context", ProjectStore(b.root), b.root),
            ("an established Project, from the Workline root", ProjectStore(b.root), WORKLINE_ROOT),
            ("a folder that is not a Project yet, from inside it", ProjectStore(plain), plain),
        )
        for label, store, where in cases:
            with self.subTest(case=label), cwd(where):
                invocation = {"operation": ps.OWNER, "project_root": str(store.root)}
                with self.assertRaises(StopError) as ctx:
                    MutationController(store).open(ps.OWNER, invocation, self.SCOPE)
                self.assertEqual(ctx.exception.code, "pre_project_authorization_required")
        self.assertEqual(tree(b.root), before)
        self.assertEqual(list(plain.iterdir()), [])

    def test_a_real_project_start_authorizes_only_its_own_root_while_it_runs(self) -> None:
        target, other = self.new_dir("target"), self.new_dir("other")
        seen: list[tuple[bool, bool]] = []
        real = ps.gitops.record_preexisting_dirty

        def observe(mutation, repo, **kwargs):
            seen.append((pre_project_authorized(target), pre_project_authorized(other)))
            return real(mutation, repo, **kwargs)

        with mock.patch.object(ps.gitops, "record_preexisting_dirty", observe):
            self.assertEqual(ps.project_start(target, WORKLINE_ROOT).status, "initialized")
        self.assertTrue(seen)
        self.assertEqual(set(seen), {(True, False)})
        self.assertFalse(pre_project_authorized(target))

        # withdrawn when Project開始 fails part-way, and granted again to the call that resumes it
        crashed = self.new_dir("crashed")
        with mock.patch.object(ps.gitops, "finalize", side_effect=RuntimeError("crash before commit")):
            with self.assertRaises(RuntimeError):
                ps.project_start(crashed, WORKLINE_ROOT)
        self.assertFalse(pre_project_authorized(crashed))
        resumed = ps.project_start(crashed, WORKLINE_ROOT)
        self.assertEqual((resumed.status, resumed.resumed), ("initialized", True))

    def test_the_python_api_cannot_reach_another_project(self) -> None:
        b = self.new_project("b")
        a = self.new_project("a")
        forget_lock_area(b)
        before = tree(b.root)
        scope = WriteScope(entities=("w_x",))

        with self.assertRaises(ForeignProjectMutation):
            with oplock.project_operation(b, "probe"):
                self.fail("a foreign operation must never hold the lock")
        with self.assertRaises(ForeignProjectMutation):
            self.simple_roadmap(b)
        with self.assertRaises(StopError) as ctx:
            MutationController(b).open("roadmap", {"operation": "probe"}, scope)
        self.assertEqual(ctx.exception.code, "operation_lock_required")
        with oplock.project_operation(a, "outer"):  # holding its own Project's lock changes nothing for B
            for owner, code in (("roadmap", "operation_lock_required"), (ps.OWNER, "pre_project_authorization_required")):
                with self.subTest(owner=owner):
                    with self.assertRaises(StopError) as ctx:
                        MutationController(b).open(owner, {"operation": "probe"}, scope)
                    self.assertEqual(ctx.exception.code, code)
        self.assertEqual(tree(b.root), before)
        self.assertFalse(b.locks.exists())


class ContextLifetimeTests(WorklineTestCase):
    def test_the_authorization_is_decided_once_when_the_operation_starts(self) -> None:
        store = self.new_project()
        work = create_standalone_work(store, WorkSpec("Wanders off", "done")).work_id
        elsewhere = self.new_dir("elsewhere")
        complete = completing_executor(store)

        def wandering(ctx: st.ExecutionContext):
            os.chdir(elsewhere)  # the executor's own working directory is its business
            return complete(ctx)

        self.assertEqual(st.start(store, work, "single-work", wandering).status, "completed")
        self.assertEqual(MutationController(store).list_pending(), [])
        # the next top-level operation is decided afresh, from where the process is now
        self.assertTrue(same_directory(Path.cwd(), elsewhere))
        with self.assertRaises(ForeignProjectMutation):
            create_standalone_work(store, WorkSpec("After wandering", "done"))

    def test_nothing_reopens_the_boundary(self) -> None:
        b = self.new_project("b")
        self.new_project("a")
        overrides = {"WORKLINE_ALLOW_FOREIGN": "1", "WORKLINE_ALLOW_FOREIGN_PROJECT": "1"}
        with mock.patch.dict(os.environ, overrides):
            with self.assertRaises(ForeignProjectMutation):
                create_standalone_work(b, WorkSpec("Override", "x"))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as rejected:
            cli_main(["create-work", str(b.root), "--name", "X", "--desired-state", "x", "--allow-foreign-project"])
        self.assertEqual(rejected.exception.code, 2)
        entries = (
            oplock.project_operation,
            st.start,
            rm.create_roadmap,
            create_standalone_work,
            bs.backfill_bootstrap,
            pin_push_destination,
            ps.project_start,
        )
        for entry in entries:
            with self.subTest(entry=entry.__name__):
                names = set(inspect.signature(entry).parameters)
                self.assertEqual({name for name in names if "foreign" in name or "allow" in name}, set())


class CrossSessionResumeTests(ExecutionLockTestCase):
    def test_a_question_wait_resumes_from_the_same_project_in_any_session(self) -> None:
        a = self.new_project("a")
        b = self.new_project("b")
        work = create_standalone_work(b, WorkSpec("Ask first", "answered")).work_id
        waiting = st.start(b, work, "single-work", scripted_executor({work: [st.QuestionWait("which colour?")]}))
        self.assertEqual(waiting.status, "question_wait")
        intent = MutationController(b).intent_path(waiting.mutation_id)
        recorded = intent.read_bytes()
        before = tree(b.root)

        # a session working in Project A cannot resume B's START, in this process or in one of its own
        with cwd(a.root), self.assertRaises(ForeignProjectMutation):
            st.start(b, work, "single-work", completing_executor(b))
        foreign = self.spawn("start_complete", b, "session-in-a", cwd=a.root, work_id=work)
        self.assertEqual(self.outcome(foreign, "session-in-a")["code"], "foreign_project_mutation")
        self.assertEqual(intent.read_bytes(), recorded)
        self.assertEqual(tree(b.root), before)

        # another session that opens Project B directly resumes the very same mutation
        another_session = {**os.environ, "CLAUDE_CODE_SESSION_ID": "another-session"}
        resumer = self.spawn("start_complete", b, "session-in-b", env=another_session, work_id=work)
        report = self.outcome(resumer, "session-in-b")
        self.assertEqual((report["outcome"], report["mutation_id"]), ("completed", waiting.mutation_id))
        self.assertEqual(MutationController(b).list_pending(), [])
        self.assertEqual(validate_project(b), [])


class ForeignBusyTests(ExecutionLockTestCase):
    def test_a_foreign_caller_is_refused_before_the_lock_is_even_opened(self) -> None:
        a = self.new_project("a")
        b = self.new_project("b")
        work = create_standalone_work(b, WorkSpec("Busy", "done")).work_id
        holder = self.spawn("hold_lock", b, "holder")
        self.wait_ready(holder, "holder")
        description = b.lock_holder.read_bytes()
        opened: list[str] = []
        real_open = os.open

        def watching(path, *args, **kwargs):
            opened.append(os.path.normcase(os.fspath(path)))
            return real_open(path, *args, **kwargs)

        with cwd(a.root), mock.patch.object(oplock.os, "open", watching):
            with self.assertRaises(ForeignProjectMutation):
                st.start(b, work, "single-work", completing_executor(b))
        self.assertNotIn(os.path.normcase(str(b.lock_file)), opened)
        self.assertEqual(b.lock_holder.read_bytes(), description)

        # the same request from inside B meets the running writer, exactly as before
        with self.assertRaises(ProjectOperationBusy):
            st.start(b, work, "single-work", completing_executor(b))
        self.assertEqual(self.release(holder, "holder")["outcome"], "released")
        self.assertEqual(st.start(b, work, "single-work", completing_executor(b)).status, "completed")


if __name__ == "__main__":
    unittest.main()
