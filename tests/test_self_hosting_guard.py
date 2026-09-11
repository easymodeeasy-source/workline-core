"""BL-012: a Workline root is never changed as a Workline Project of its own.

Self-hosting is unsupported under the current Workline rules. A state-changing
operation runs only when the Project root and its Workline root are proven to be
different directories, compared by file identity. Project開始 refuses a target
that is its Workline root, and every operation on an established Project that
already has that shape STOPs after the Project context and before the Workline
implementation check and the execution lock, writing nothing. Reading such a
Project stays possible, and validating it reports the topology instead of
passing.

No test here makes the real repository a self-hosting target: every Workline
root involved is a copy in a temporary directory. The established self-hosted
Project is assembled by the test itself, since no Workline operation can create
one.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import textwrap
import unittest
from unittest import mock

from helpers import (
    WORKLINE_ROOT,
    WorklineTestCase,
    completing_executor,
    copy_workline_root,
    cwd,
    git,
    launcher_command,
    run_python,
    scripted_executor,
)
from test_implementation_identity import BOOTSTRAP_SHA256, activation, driver_command, workline_state

from workline import bootstrap as bs
from workline import gitcmd, oplock, self_hosting, yamlish
from workline import project_start as ps
from workline import roadmap as rm
from workline import start as st
from workline.bootstrap import render_bootstrap
from workline.create import RelatedSpec, WorkSpec, create_standalone_work
from workline.errors import ForeignProjectMutation, ImplementationMismatch, SelfHostingUnsupported, StopError
from workline.mutation import INTENT_VERSION, MutationController
from workline.phase_create import PhaseSpec
from workline.push_pin import pin_push_destination
from workline.registry import validate_registry
from workline.state import ProjectView
from workline.store import (
    BOOTSTRAP_REL_PATH,
    PHASE_EVENTS,
    ROADMAP_EVENTS,
    WORK_EVENTS,
    Event,
    ProjectStore,
    render_project_yaml,
)
from workline.validate import validate_project, validate_project_yaml

SELF_HOSTING = "workline_self_hosting_unsupported"
REGISTRY = WORKLINE_ROOT / "registry.md"
PUSH_URL = "https://example.invalid/workline.git"


# --------------------------------------------------------------------------- helpers

def tree(root: Path) -> dict[str, str]:
    """Every file and directory under ``root``, ``.git`` included, file contents hashed."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "<dir>"
        for path in sorted(root.rglob("*"))
    }


def codes(problems) -> set[str]:
    return {problem.code for problem in problems}


def undeterminable(first: Path, second: Path):
    """Patch ``os.path.samefile`` so that it cannot tell whether ``first`` and ``second`` are one directory."""
    real = os.path.samefile

    def key(path) -> str:
        return os.path.normcase(os.path.realpath(path))

    blocked = {key(first), key(second)}

    def samefile(a, b):
        if {key(a), key(b)} == blocked:
            raise PermissionError(13, "file identity unavailable")
        return real(a, b)

    return mock.patch.object(os.path, "samefile", samefile)


def short_name(path: Path) -> Path | None:
    """The 8.3 short spelling of ``path``, when the volume provides one that differs."""
    if os.name != "nt":
        return None
    import ctypes

    buffer = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer)):
        return None
    return Path(buffer.value) if buffer.value.lower() != str(path).lower() else None


class SelfHostingTestCase(WorklineTestCase):
    def directory_link(self, target: Path, link: Path) -> Path | None:
        """A junction (Windows) or symlink to ``target``, removed after the test, or None where refused."""
        try:
            if os.name == "nt":
                import _winapi

                _winapi.CreateJunction(str(target), str(link))
            else:
                os.symlink(target, link, target_is_directory=True)
        except (ImportError, AttributeError, OSError):
            return None
        self.addCleanup(os.rmdir if os.name == "nt" else os.unlink, link)
        return link

    def spellings(self, root: Path, *, relative: bool = True) -> dict[str, object]:
        """Other names for ``root``; the relative one is meant for use from ``self.tmp``."""
        spelled: dict[str, object] = {
            "trailing separator": f"{root}{os.sep}",
            "dot segments": root / "src" / "..",
        }
        if relative:
            spelled["relative"] = Path(os.path.relpath(root, self.tmp))
        if os.name == "nt":
            spelled["case"] = str(root).swapcase()
            spelled["forward slashes"] = str(root).replace("\\", "/")
        link = self.directory_link(root, self.tmp / f"{root.name}-link")
        if link is not None:
            spelled["junction or symlink"] = link
        short = short_name(root)
        if short is not None:
            spelled["8.3 short name"] = short
        return spelled

    def assertSelfHostingStop(self, raised: SelfHostingUnsupported, project_root: object, workline_root: object) -> None:
        self.assertEqual(raised.code, SELF_HOSTING)
        self.assertIn(str(project_root), raised.message)
        self.assertIn(str(workline_root), raised.message)
        self.assertIn("unsupported under the current Workline rules", raised.message)
        self.assertIn("nothing was written", raised.message)
        self.assertNotRegex(raised.message, r"BL-\d|BACKLOG")

    def self_hosted_project(self) -> tuple[ProjectStore, dict[str, str]]:
        """A copy of this Workline root that is an established Project configured with itself.

        Assembled by hand, because no Workline operation creates this shape: a
        normal Project is started elsewhere and given a Roadmap, Works and a
        START waiting on a question; its canonical files, bootstrap and recovery
        records are then copied into a Workline root copy whose project.yaml
        names that copy, and committed there.
        """
        source = self.new_project("source")
        plan = rm.RoadmapPlan(
            "Self-hosted", "background", "desired state", {"a": PhaseSpec("A", "A done"), "b": PhaseSpec("B", "B done")}
        )
        roadmap = rm.create_roadmap(source, plan)
        entry = self.simple_entry(source, roadmap.phase_ids["a"], {"w1": "W1 done", "w2": "W2 done"})
        standalone = create_standalone_work(source, WorkSpec("Standalone", "done"))
        waiting = st.start(source, entry.work_ids["w1"], "single-work", scripted_executor({"*": [st.QuestionWait("waiting")]}))
        self.assertEqual(waiting.status, "question_wait")

        root = copy_workline_root(self.tmp / "self-hosted")
        shutil.copytree(source.workline, root / ".workline", ignore=shutil.ignore_patterns("locks", "tmp"))
        (root / BOOTSTRAP_REL_PATH).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source.root / BOOTSTRAP_REL_PATH, root / BOOTSTRAP_REL_PATH)
        store = ProjectStore(root)
        store.project_yaml.write_text(render_project_yaml(root), encoding="utf-8")
        git(root, "init", "-q", "-b", "main")
        git(root, "add", "-A", "--", ".", ":(exclude).workline/runtime")
        git(root, "commit", "-q", "-m", "a Workline root configured as its own Project (test fixture)")
        self.enter(root)

        self.assertTrue(bs.is_established_project(store))
        self.assertTrue(any(p["owner"] == st.OWNER for p in MutationController(store).list_pending()))
        return store, {
            "roadmap": roadmap.roadmap_id,
            "phase_a": roadmap.phase_ids["a"],
            "phase_b": roadmap.phase_ids["b"],
            "waiting": entry.work_ids["w1"],
            "unstarted": entry.work_ids["w2"],
            "standalone": standalone.work_id,
        }

    def assertEveryAttemptStops(self, store: ProjectStore, attempts: dict) -> None:
        self.assertFalse(store.locks.exists())
        before = workline_state(store)
        for label, attempt in attempts.items():
            with self.subTest(operation=label):
                with self.assertRaises(SelfHostingUnsupported) as ctx:
                    attempt()
                self.assertSelfHostingStop(ctx.exception, store.root, store.workline_root())
                self.assertFalse(store.locks.exists())
                self.assertIsNone(oplock.held_lock(store))
                self.assertEqual(workline_state(store), before)


# --------------------------------------------------------------------------- file identity

class DirectoryIdentityTests(SelfHostingTestCase):
    def test_same_distinct_missing_and_undetermined(self) -> None:
        a, b = self.new_dir("a"), self.new_dir("b")
        self.assertEqual(self_hosting.directory_identity(a, a), self_hosting.SAME)
        self.assertEqual(self_hosting.directory_identity(a, b), self_hosting.DISTINCT)
        self.assertEqual(self_hosting.directory_identity(a, self.tmp / "absent"), self_hosting.MISSING)
        self.assertEqual(self_hosting.directory_identity(self.tmp / "absent", a), self_hosting.MISSING)
        with undeterminable(a, b):
            self.assertEqual(self_hosting.directory_identity(a, b), self_hosting.UNDETERMINED)

    def test_the_stop_names_both_roots_and_no_backlog_item(self) -> None:
        a, b = self.new_dir("a"), self.new_dir("b")
        with self.assertRaises(SelfHostingUnsupported) as same:
            self_hosting.refuse_self_hosting(a, a)
        self.assertSelfHostingStop(same.exception, a, a)
        self.assertIn("itself", same.exception.message)
        with undeterminable(a, b), self.assertRaises(SelfHostingUnsupported) as unproven:
            self_hosting.refuse_self_hosting(a, b)
        self.assertSelfHostingStop(unproven.exception, a, b)
        self.assertIn("cannot be proven to be a different directory", unproven.exception.message)
        self.assertIsNone(self_hosting.self_hosting_problem(a, b))
        self.assertEqual(SelfHostingUnsupported("why").code, self_hosting.CODE)


# --------------------------------------------------------------------------- initial Project開始

class InitialProjectStartTests(SelfHostingTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = copy_workline_root(self.tmp / "wl")
        self.enter(self.tmp)

    def test_a_project_start_for_a_different_folder_is_unaffected(self) -> None:
        target = self.new_dir("target")
        self.assertEqual(self_hosting.directory_identity(target, WORKLINE_ROOT), self_hosting.DISTINCT)
        self.assertEqual(ps.project_start(target, WORKLINE_ROOT).status, "initialized")
        self.assertEqual(validate_project(ProjectStore(target)), [])

    def test_the_workline_root_itself_is_refused_before_anything_is_written(self) -> None:
        before = tree(self.root)
        with self.assertRaises(SelfHostingUnsupported) as ctx:
            ps.project_start(self.root, self.root)
        self.assertSelfHostingStop(ctx.exception, self.root, self.root)
        self.assertEqual(tree(self.root), before)
        for created in (".git", ".workline", BOOTSTRAP_REL_PATH):
            self.assertFalse((self.root / created).exists(), created)

    def test_the_launcher_refuses_project_start_of_its_own_workline_root(self) -> None:
        before = tree(self.root)
        result = run_python(launcher_command(self.root, "project-start", self.root, "--workline-root", self.root), cwd=self.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(f"STOP [{SELF_HOSTING}]", result.stdout)
        self.assertEqual(tree(self.root), before)
        self.assertFalse((self.root / ".git").exists())

    def test_every_spelling_of_the_same_directory_is_refused(self) -> None:
        spellings = self.spellings(self.root)
        before = tree(self.root)
        for label, spelled in spellings.items():
            for target, workline, which in ((spelled, self.root, "Project root"), (self.root, spelled, "Workline root")):
                with self.subTest(spelling=label, spelled=which), cwd(self.tmp):
                    with self.assertRaises(SelfHostingUnsupported):
                        ps.project_start(target, workline)
        if "junction or symlink" in spellings:
            link = spellings["junction or symlink"]
            result = run_python(launcher_command(self.root, "project-start", link, "--workline-root", self.root), cwd=self.tmp)
            self.assertIn(f"STOP [{SELF_HOSTING}]", result.stdout, result.stdout + result.stderr)
        self.assertEqual(tree(self.root), before)

    def test_a_target_that_is_not_a_git_repository_stops_before_git_init(self) -> None:
        self.assertIsNone(gitcmd.toplevel(self.root))
        with self.assertRaises(SelfHostingUnsupported):
            ps.project_start(self.root, self.root)
        self.assertFalse((self.root / ".git").exists())
        self.assertIsNone(gitcmd.toplevel(self.root))

    def test_a_repository_target_keeps_its_head_index_config_and_status(self) -> None:
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "a Workline root under version control")
        git(self.root, "config", "workline.test.marker", "kept")
        head = git(self.root, "rev-parse", "HEAD")
        index = git(self.root, "ls-files", "-s")
        status = git(self.root, "status", "--porcelain", "--untracked-files=all")
        config = (self.root / ".git" / "config").read_bytes()
        before = tree(self.root)

        with self.assertRaises(SelfHostingUnsupported):
            ps.project_start(self.root, self.root)
        result = run_python(launcher_command(self.root, "project-start", self.root, "--workline-root", self.root), cwd=self.root)
        self.assertIn(f"STOP [{SELF_HOSTING}]", result.stdout, result.stdout + result.stderr)

        self.assertEqual(tree(self.root), before)
        self.assertEqual((self.root / ".git" / "config").read_bytes(), config)
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), head)
        self.assertEqual(git(self.root, "ls-files", "-s"), index)
        self.assertEqual(git(self.root, "status", "--porcelain", "--untracked-files=all"), status)

    def test_a_foreign_context_is_reported_before_self_hosting(self) -> None:
        before = tree(self.root)
        self.new_project("elsewhere")  # working inside another Project from now on
        with self.assertRaises(ForeignProjectMutation):
            ps.project_start(self.root, self.root)
        self.assertEqual(tree(self.root), before)

    def test_self_hosting_is_reported_before_an_implementation_mismatch(self) -> None:
        other = copy_workline_root(self.tmp / "other")
        # this test process runs the repository implementation, which is not the copy's
        with self.assertRaises(SelfHostingUnsupported):
            ps.project_start(self.root, self.root)
        result = run_python(launcher_command(other, "project-start", self.root, "--workline-root", self.root), cwd=self.tmp)
        self.assertIn(f"STOP [{SELF_HOSTING}]", result.stdout, result.stdout + result.stderr)
        self.assertNotIn("workline_implementation_mismatch", result.stdout)

    def test_a_missing_workline_root_keeps_its_existing_stop(self) -> None:
        target = self.new_dir("target")
        with self.assertRaises(StopError) as ctx:
            ps.project_start(target, self.tmp / "absent")
        self.assertEqual(ctx.exception.code, "workline_root_missing")
        self.assertEqual(list(target.iterdir()), [])


# --------------------------------------------------------------------------- an established self-hosted Project

class SelfHostedProjectTests(SelfHostingTestCase):
    def test_start_and_its_resume_stop(self) -> None:
        store, ids = self.self_hosted_project()
        self.assertEveryAttemptStops(
            store,
            {
                "START": lambda: st.start(store, ids["unstarted"], "single-work", completing_executor(store)),
                "START resume": lambda: st.start(store, ids["waiting"], "single-work", completing_executor(store)),
                "standalone plan exclusion": lambda: st.plan_exclude_standalone_work(store, ids["standalone"]),
            },
        )
        # the waiting START is neither resumed nor discarded
        self.assertTrue(any(p["owner"] == st.OWNER for p in MutationController(store).list_pending()))

    def test_roadmap_mutations_stop(self) -> None:
        store, ids = self.self_hosted_project()
        design = rm.PhaseEntryDesign({"w": rm.WorkDesign("W", "W done")}, rm.WorkDesign("Integration", "integrated"))
        another = rm.RoadmapPlan("Another", "background", "desired state", {"x": PhaseSpec("X", "X done")})
        self.assertEveryAttemptStops(
            store,
            {
                "Roadmap create": lambda: rm.create_roadmap(store, another),
                "Phase addition": lambda: rm.add_phases(store, ids["roadmap"], {"c": PhaseSpec("C", "C done")}),
                "Phase entry": lambda: rm.enter_phase(store, ids["phase_b"], design),
                "Phase hold": lambda: rm.hold_phase(store, ids["phase_b"]),
                "Phase resume": lambda: rm.resume_phase(store, ids["phase_b"]),
                "Phase cancel": lambda: rm.cancel_phase(store, ids["phase_b"]),
                "Phase plan exclusion": lambda: rm.plan_exclude_phase(store, ids["phase_b"]),
                "Work plan exclusion": lambda: rm.plan_exclude_work(store, ids["unstarted"]),
                "Roadmap hold": lambda: rm.hold_roadmap(store, ids["roadmap"]),
                "Roadmap resume": lambda: rm.resume_roadmap(store, ids["roadmap"]),
                "Roadmap cancel": lambda: rm.cancel_roadmap(store, ids["roadmap"]),
            },
        )

    def test_direct_create_and_related_maintenance_stop(self) -> None:
        store, ids = self.self_hosted_project()
        self.assertEveryAttemptStops(
            store,
            {
                "direct CREATE": lambda: create_standalone_work(store, WorkSpec("Refused", "never registered")),
                "related maintenance": lambda: rm.maintain_work_related(
                    store, ids["unstarted"], add=(RelatedSpec("must_read", "registry.md"),)
                ),
            },
        )

    def test_bootstrap_backfill_and_push_pin_stop(self) -> None:
        store, _ = self.self_hosted_project()
        self.assertEveryAttemptStops(
            store,
            {
                "bootstrap backfill": lambda: bs.backfill_bootstrap(store.root),
                "push destination pin": lambda: pin_push_destination(store.root, [PUSH_URL]),
            },
        )

    def test_recording_roadmap_achieved_stops(self) -> None:
        store, ids = self.self_hosted_project()
        self.assertEveryAttemptStops(
            store, {"roadmap_achieved": lambda: rm.evaluate_achievement(store, ids["roadmap"], "achieved")}
        )

    def test_project_start_again_stops_instead_of_reporting_already_initialized(self) -> None:
        store, _ = self.self_hosted_project()
        self.assertEveryAttemptStops(store, {"Project開始 again": lambda: ps.project_start(store.root, store.root)})

    def test_the_project_operation_itself_stops_before_the_lock(self) -> None:
        store, _ = self.self_hosted_project()

        def hold_the_lock() -> None:
            with oplock.project_operation(store, "probe"):
                self.fail("an unsupported self-hosted Project must never hold the execution lock")

        self.assertEveryAttemptStops(store, {"project operation": hold_the_lock})

    def test_a_configured_root_spelled_another_way_is_still_the_project_root(self) -> None:
        store, _ = self.self_hosted_project()
        for label, spelled in self.spellings(store.root, relative=False).items():
            with self.subTest(spelling=label):
                store.project_yaml.write_text(render_project_yaml(spelled), encoding="utf-8")
                with self.assertRaises(SelfHostingUnsupported):
                    create_standalone_work(store, WorkSpec("Refused", "never registered"))
                self.assertIn(SELF_HOSTING, codes(validate_project(store)))
                self.assertFalse(store.locks.exists())

    def test_a_foreign_context_and_another_implementation_are_ordered_around_self_hosting(self) -> None:
        store, _ = self.self_hosted_project()
        before = workline_state(store)
        # this test process runs the repository implementation, not the copy's: self-hosting is reported first
        with self.assertRaises(SelfHostingUnsupported):
            create_standalone_work(store, WorkSpec("Refused", "never registered"))
        # from inside another Project, the target is foreign before anything else is looked at
        self.new_project("elsewhere")
        with self.assertRaises(ForeignProjectMutation):
            create_standalone_work(ProjectStore(store.root), WorkSpec("Refused", "never registered"))
        self.assertFalse(store.locks.exists())
        self.assertEqual(workline_state(store), before)

    def test_the_canonical_launcher_and_api_run_but_every_change_stops(self) -> None:
        store, ids = self.self_hosted_project()
        root = store.root
        before = workline_state(store)
        for args in (
            ("create-work", ".", "--name", "Refused", "--desired-state", "never registered"),
            ("backfill-bootstrap", "."),
            ("pin-push-destination", ".", "--url", PUSH_URL),
        ):
            with self.subTest(command=args[0]):
                result = run_python(launcher_command(root, *args), cwd=root)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(f"STOP [{SELF_HOSTING}]", result.stdout)

        registry = run_python(launcher_command(root, "validate-registry", "."), cwd=root)
        self.assertEqual(registry.returncode, 0, registry.stdout + registry.stderr)
        validation = run_python(launcher_command(root, "validate-project", "."), cwd=root)
        self.assertEqual(validation.returncode, 1, validation.stdout + validation.stderr)
        self.assertIn(f"{SELF_HOSTING}: ", validation.stdout)

        operation = textwrap.dedent(
            f"""\
            import json
            from pathlib import Path
            from workline import roadmap as rm, start as st
            from workline.errors import StopError
            from workline.state import ProjectView
            from workline.store import ProjectStore

            store = ProjectStore(Path.cwd())
            outcomes = {{}}
            for label, attempt in (
                ("Roadmap hold", lambda: rm.hold_roadmap(store, {ids["roadmap"]!r})),
                ("START", lambda: st.start(store, {ids["unstarted"]!r}, "single-work", lambda ctx: st.Completed())),
            ):
                try:
                    attempt()
                    outcomes[label] = "ran"
                except StopError as exc:
                    outcomes[label] = exc.code
            outcomes["works read"] = len(ProjectView.load(store).works)
            print("OUTCOMES " + json.dumps(outcomes))
            """
        )
        driven = run_python(driver_command(), cwd=root, stdin=activation(root) + operation)
        self.assertEqual(driven.returncode, 0, driven.stdout + driven.stderr)
        outcomes = json.loads(driven.stdout.split("OUTCOMES ", 1)[1].splitlines()[0])
        self.assertEqual((outcomes["Roadmap hold"], outcomes["START"]), (SELF_HOSTING, SELF_HOSTING))
        self.assertEqual(outcomes["works read"], len(ProjectView.load(store).works))
        self.assertFalse(store.locks.exists())
        self.assertEqual(workline_state(store), before)

    def test_another_roots_launcher_is_still_refused_when_the_process_starts(self) -> None:
        store, _ = self.self_hosted_project()
        other = copy_workline_root(self.tmp / "other")
        before = workline_state(store)
        for args in (("validate-project", "."), ("create-work", ".", "--name", "Refused", "--desired-state", "never")):
            with self.subTest(command=args[0]):
                result = run_python(launcher_command(other, *args), cwd=store.root)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("STOP [workline_implementation_mismatch]", result.stdout)
        self.assertEqual(workline_state(store), before)

    def test_reading_a_self_hosted_project_stays_possible(self) -> None:
        store, ids = self.self_hosted_project()
        before = workline_state(store)

        view = ProjectView.load(store)
        self.assertIn(ids["unstarted"], view.works)
        self.assertEqual(store.read_entity("roadmap", ids["roadmap"]).id, ids["roadmap"])
        self.assertIsInstance(rm.startable_phases(store, ids["roadmap"]), list)
        self.assertIsInstance(rm.diagnose_no_candidate(store, ids["roadmap"]), str)
        self.assertTrue(any(p["owner"] == st.OWNER for p in MutationController(store).list_pending()))
        self.assertEqual(rm.evaluate_achievement(store, ids["roadmap"], "not_achieved").status, "not_ready")
        self.assertTrue(validate_registry(store.root).ok)

        self.assertFalse(store.locks.exists())
        self.assertEqual(workline_state(store), before)

    def test_validation_reports_self_hosting_and_never_passes(self) -> None:
        store, _ = self.self_hosted_project()
        problems = validate_project(store)
        self.assertEqual(codes(problems), {SELF_HOSTING})
        self.assertIn(str(store.root), problems[0].message)
        # project.yaml validation and the established-Project decision are not about topology
        self.assertEqual(validate_project_yaml(store), [])
        self.assertTrue(bs.is_established_project(store))

    def test_validation_still_reports_other_problems_beside_self_hosting(self) -> None:
        store, ids = self.self_hosted_project()
        store.entity_path("phase", ids["phase_a"]).unlink()  # its Works now belong to a Phase that is gone
        found = codes(validate_project(store))
        self.assertIn(SELF_HOSTING, found)
        self.assertTrue(found - {SELF_HOSTING}, found)


# --------------------------------------------------------------------------- identity that cannot be decided, a missing root

class UndeterminedAndMissingRootTests(SelfHostingTestCase):
    def test_a_project_not_proven_apart_from_its_workline_root_is_not_changed(self) -> None:
        store = self.new_project()
        before = workline_state(store)
        with undeterminable(store.root, store.workline_root()):
            self.assertEqual(self_hosting.directory_identity(store.root, store.workline_root()), self_hosting.UNDETERMINED)
            with self.assertRaises(SelfHostingUnsupported) as ctx:
                create_standalone_work(store, WorkSpec("Unproven", "never registered"))
            self.assertIn("cannot be proven to be a different directory", ctx.exception.message)
            self.assertIn(SELF_HOSTING, codes(validate_project(store)))
        self.assertFalse(store.locks.exists())
        self.assertEqual(workline_state(store), before)
        self.assertEqual(validate_project(store), [])  # with its identity available again it is an ordinary Project

    def test_project_start_is_refused_when_the_target_cannot_be_proven_apart(self) -> None:
        target = self.new_dir("target")
        self.enter(self.tmp)
        with undeterminable(target, WORKLINE_ROOT), self.assertRaises(SelfHostingUnsupported):
            ps.project_start(target, WORKLINE_ROOT)
        self.assertEqual(list(target.iterdir()), [])

    def test_a_missing_workline_root_is_not_reported_as_self_hosting(self) -> None:
        store = self.new_project()
        missing = self.tmp / "moved-away"
        store.project_yaml.write_text(render_project_yaml(missing), encoding="utf-8")
        git(store.root, "commit", "-q", "-am", "point at a Workline root that is gone")
        self.assertEqual(self_hosting.directory_identity(store.root, missing), self_hosting.MISSING)

        found = codes(validate_project(store))
        self.assertIn("workline_root_missing", found)
        self.assertNotIn(SELF_HOSTING, found)
        with self.assertRaises(ImplementationMismatch):  # what an operation already reported for this case
            create_standalone_work(store, WorkSpec("Missing root", "never registered"))
        self.assertFalse(store.locks.exists())

    def test_an_ordinary_project_is_untouched_by_the_guard(self) -> None:
        store = self.new_project()
        self.assertEqual(self_hosting.directory_identity(store.root, store.workline_root()), self_hosting.DISTINCT)
        self.assertIsNone(self_hosting.self_hosting_problem(store.root, store.workline_root()))
        self.assertEqual(validate_project(store), [])
        created = create_standalone_work(store, WorkSpec("Ordinary", "done"))
        self.assertIn(created.work_id, ProjectView.load(store).works)


# --------------------------------------------------------------------------- what BL-012 does not change

class UnchangedSurfaceTests(unittest.TestCase):
    def test_bootstrap_project_yaml_and_intent_format_are_unchanged(self) -> None:
        self.assertEqual(hashlib.sha256(render_bootstrap().encode("utf-8")).hexdigest(), BOOTSTRAP_SHA256)
        self.assertEqual(set(yamlish.load(render_project_yaml(Path("workline-root")))), {"workline", "rules"})
        self.assertEqual(INTENT_VERSION, 1)

    def test_the_event_schema_is_unchanged(self) -> None:
        self.assertEqual(Event("e", "t", "x", "a").to_record(), {"id": "e", "type": "t", "entity": "x", "at": "a"})
        self.assertEqual(
            WORK_EVENTS,
            (
                "work_started", "work_target_added", "work_target_removed", "work_held",
                "work_resumed", "work_completed", "work_cancelled", "plan_excluded",
            ),
        )
        self.assertEqual(PHASE_EVENTS, ("phase_held", "phase_resumed", "phase_cancelled", "plan_excluded"))
        self.assertEqual(ROADMAP_EVENTS, ("roadmap_held", "roadmap_resumed", "roadmap_cancelled", "roadmap_achieved"))

    def test_there_is_no_way_to_allow_self_hosting(self) -> None:
        self.assertEqual(
            list(inspect.signature(ps.project_start).parameters),
            ["project_root", "workline_root", "expected_push_url", "push_remote"],
        )
        self.assertEqual(list(inspect.signature(oplock.project_operation).parameters), ["store", "operation", "details"])
        self.assertEqual(list(inspect.signature(self_hosting.refuse_self_hosting).parameters), ["project_root", "workline_root"])
        source = Path(self_hosting.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(source, r"environ|getenv|allow[_-]?self")
        help_text = run_python(launcher_command(WORKLINE_ROOT, "project-start", "--help"), cwd=WORKLINE_ROOT).stdout
        self.assertIn("--workline-root", help_text)
        self.assertNotRegex(help_text.lower(), r"self.?host|allow")

    def test_the_rules_state_the_guard_without_a_backlog_item(self) -> None:
        text = REGISTRY.read_text(encoding="utf-8")
        self.assertIn("### Unsupported self-hosting", text)
        self.assertIn("`workline_self_hosting_unsupported`", text)
        self.assertNotRegex(text, r"BL-\d{3}")


if __name__ == "__main__":
    unittest.main()
