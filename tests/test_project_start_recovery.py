"""BL-022: a Project開始 stopped before its first effect can be run again.

A new Project開始 settles its predictable pre-effect STOPs — ``git init`` when
the folder needs a repository, bootstrap committability, pre-existing changes
that cannot be separated — before its recovery intent exists, so they leave no
``.workline`` behind; a repository it initialized may stay and is the existing
one on the next run. A pending Project開始 resumes as the same mutation. A
``.workline`` proven to hold nothing but Project開始 intents for this very
folder, each closed as abandoned before its first effect, is started again as a
new mutation with those records left byte for byte. Any other partial
``.workline`` STOPs as ``partial_workline``, and a record Workline cannot
confirm as ``reconcile_required``.

Every Project here is a temporary folder. The records the earlier order left —
intent first, checks after — are written by the Mutation Controller inside the
authorization Project開始 grants its own target root, as that order wrote them;
the classification under test is never bypassed. These run on Windows; nothing
here claims that POSIX was exercised.
"""

from __future__ import annotations

import hashlib
import inspect
import os
from pathlib import Path
import re
import textwrap
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, WorklineTestCase, cwd, git, launcher_command, run_python
from test_implementation_identity import BOOTSTRAP_SHA256, activation, driver_command

from workline import cli, gitcmd, gitops, oplock, yamlish
from workline import project_start as ps
from workline.bootstrap import render_bootstrap
from workline.context import _pre_project_authorization
from workline.create import WorkSpec, create_standalone_work
from workline.errors import GitError, StopError
from workline.mutation import INTENT_MARKER, INTENT_VERSION, Mutation, MutationController, WriteScope
from workline.store import BOOTSTRAP_REL_PATH, Event, ProjectStore, render_project_yaml
from workline.validate import validate_project

PARTIAL = "partial_workline"
RECONCILE = "reconcile_required"
CANONICAL = (
    ".workline/project.yaml",
    ".workline/relations/roadmap.yaml",
    ".workline/relations/related.yaml",
    ".workline/events/events.jsonl",
)
DECLARED = sorted((*CANONICAL, BOOTSTRAP_REL_PATH))
# Every field of a Project開始 intent that was opened and then closed.
CLOSED_INTENT_FIELDS = {
    "workline", "version", "mutation_id", "owner", "status", "created_at", "updated_at",
    "invocation", "write_scope", "reserved_ids", "notes", "effects", "completed_at",
}
# The fields the Mutation Controller itself needs to confirm Workline ownership of a record.
OWNERSHIP_FIELDS = {"workline", "version", "mutation_id", "owner", "status", "invocation", "write_scope"}
WORK_ID = "w_01ARZ3NDEKTSV4RRFFQ69G5FAV"
PUSH_URL = "https://example.invalid/project.git"


# --------------------------------------------------------------------------- helpers

def slug(label: str) -> str:
    return re.sub(r"\W+", "-", label).strip("-")


def tree(path: Path) -> dict[str, str]:
    """Every entry under ``path``, file contents hashed."""
    if not path.exists():
        return {}
    return {
        entry.relative_to(path).as_posix(): hashlib.sha256(entry.read_bytes()).hexdigest() if entry.is_file() else "<dir>"
        for entry in sorted(path.rglob("*"))
    }


def repository(repo: Path) -> dict[str, object]:
    """What a user keeps in Git: HEAD, index entries, configuration and worktree status."""
    return {
        "head": git(repo, "rev-parse", "--verify", "--quiet", "HEAD", check=False).strip(),
        "index": git(repo, "ls-files", "-s"),
        "config": (repo / ".git" / "config").read_bytes(),
        "status": status(repo),
    }


def status(repo: Path) -> str:
    return git(repo, "status", "--porcelain", "--untracked-files=all")


def records(root: Path) -> dict[str, dict]:
    """Every recovery record of ``root`` by mutation ID, as the Mutation Controller reads them."""
    return {record["mutation_id"]: record for record in MutationController(ProjectStore(root)).list_records()}


def record_bytes(root: Path) -> dict[str, bytes]:
    mutations = ProjectStore(root).mutations
    return {path.name: path.read_bytes() for path in sorted(mutations.iterdir())} if mutations.is_dir() else {}


def committed(root: Path) -> set[str]:
    return set(git(root, "show", "--name-only", "--format=", "HEAD").split())


def ignore_bootstrap(root: Path) -> Path:
    """A .gitignore that keeps the bootstrap from ever being committed."""
    path = root / ".gitignore"
    path.write_text(".claude/\n", encoding="utf-8")
    return path


def user_repository(root: Path) -> None:
    git(root, "init", "-b", "main")
    (root / "tracked.txt").write_text("v1\n", encoding="utf-8")
    git(root, "add", "tracked.txt")
    git(root, "commit", "-m", "user commit")


class RecoveryTestCase(WorklineTestCase):
    def start(self, root: Path, **kwargs) -> ps.ProjectStartResult:
        """Project開始 of ``root``, run from the Workline root as in real use."""
        with cwd(WORKLINE_ROOT):
            return ps.project_start(root, WORKLINE_ROOT, **kwargs)

    def assertStops(self, code: str, root: Path, **kwargs) -> StopError:
        with self.assertRaises(StopError) as ctx:
            self.start(root, **kwargs)
        self.assertEqual(ctx.exception.code, code, ctx.exception.message)
        self.assertNotRegex(ctx.exception.message, r"BL-\d|BACKLOG")
        return ctx.exception

    def assertNotRetried(self, root: Path, code: str = PARTIAL) -> StopError:
        """The STOP for a ``.workline`` not proven to be abandoned pre-effect residue: nothing in the folder changes."""

        def folder() -> tuple:
            git_state = repository(root) if (root / ".git").is_dir() else None
            return sorted(entry.name for entry in root.iterdir()), tree(root / ".workline"), git_state

        before = folder()
        raised = self.assertStops(code, root)
        self.assertEqual(folder(), before)
        if code == PARTIAL:
            self.assertIn("not repairing by guess", raised.message)
        return raised

    def assertInitialized(self, root: Path, result: ps.ProjectStartResult) -> None:
        self.assertEqual(result.status, "initialized")
        store = ProjectStore(root)
        self.assertEqual(validate_project(store), [])
        self.assertEqual(git(root, "log", "-1", "--format=%s").strip(), ps.INITIAL_COMMIT_MESSAGE)
        self.assertEqual(committed(root), {*CANONICAL, BOOTSTRAP_REL_PATH})
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(records(root)[result.mutation_id]["status"], "completed")

    def abandoned_start(self, root: Path, *, preexisting: list[str] | None = None) -> Path:
        """A Project開始 intent for ``root`` closed as abandoned before its first effect.

        What the earlier order left when a pre-effect check STOPped after the
        intent was written: opened by the Mutation Controller inside the
        authorization Project開始 grants its own target, given its snapshot of
        pre-existing changes when the STOP came after that, then abandoned.
        """
        store = ProjectStore(root)
        invocation = {"operation": ps.OWNER, "project_root": str(store.root)}
        scope = WriteScope(files=(*store.canonical_relative_paths, BOOTSTRAP_REL_PATH))
        with _pre_project_authorization(store.root):
            mutation = MutationController(store).open(ps.OWNER, invocation, scope)
            if preexisting is not None:
                mutation.set_note("preexisting_dirty", preexisting)
            mutation.abandon()
        return mutation.path

    def rewrite(self, path: Path, change) -> None:
        """Change a recovery record as data and write it back in the YAML subset Workline reads."""
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8", newline="\n")

    def directory_link(self, target: Path, link: Path) -> bool:
        """A junction (Windows) or symlink at ``link`` to ``target``; False where the platform refuses."""
        try:
            if os.name == "nt":
                import _winapi

                _winapi.CreateJunction(str(target), str(link))
            else:
                os.symlink(target, link, target_is_directory=True)
        except (ImportError, AttributeError, OSError):
            return False

        def remove() -> None:
            if os.path.lexists(link):
                (os.rmdir if os.name == "nt" else os.unlink)(link)

        self.addCleanup(remove)
        return True


# --------------------------------------------------------------------------- prevention

class NewStartPreventionTests(RecoveryTestCase):
    def test_an_ignored_bootstrap_stops_before_any_workline_and_the_retry_initializes(self) -> None:
        root = self.new_dir()
        gitignore = ignore_bootstrap(root)

        self.assertStops("bootstrap_path_ignored", root)

        self.assertFalse((root / ".workline").exists())
        self.assertFalse((root / BOOTSTRAP_REL_PATH).exists())
        self.assertTrue((root / ".git").is_dir())  # the repository git init made stays
        self.assertIsNone(gitcmd.head_commit(root))
        self.assertEqual(gitignore.read_text(encoding="utf-8"), ".claude/\n")

        gitignore.unlink()  # the cause is fixed
        result = self.start(root)

        self.assertInitialized(root, result)
        self.assertFalse(result.resumed)
        self.assertEqual(git(root, "log", "--format=%s").splitlines(), [ps.INITIAL_COMMIT_MESSAGE])
        self.assertEqual(list(records(root)), [result.mutation_id])

    def test_every_pre_effect_stop_of_a_new_start_leaves_no_workline(self) -> None:
        def toplevel_elsewhere(root: Path):
            real = gitcmd.toplevel

            def toplevel(path):
                if Path(path).resolve() == root.resolve() and (root / ".git").exists():
                    return self.tmp  # git init ran, yet Git names another top-level
                return real(path)

            return mock.patch.object(gitcmd, "toplevel", toplevel)

        stops = [
            # (code, what goes wrong, whether a repository is left)
            ("bootstrap_path_unclear", lambda root: mock.patch.object(gitcmd, "is_ignored", return_value=None), True),
            ("git_init_failed", toplevel_elsewhere, True),
            ("git_error", lambda root: mock.patch.object(gitcmd, "init_main", side_effect=GitError("git init failed")), False),
            ("git_error", lambda root: mock.patch.object(gitcmd, "status_entries", side_effect=GitError("git status failed")), True),
        ]
        for number, (code, trouble, repository_left) in enumerate(stops):
            with self.subTest(stop=code, case=number):
                root = self.new_dir(f"stop-{number}")
                with trouble(root):
                    self.assertStops(code, root)
                self.assertFalse((root / ".workline").exists())
                self.assertEqual((root / ".git").is_dir(), repository_left)

    def test_a_dirty_overlap_stops_before_any_workline_and_the_retry_initializes(self) -> None:
        root = self.new_dir()
        git(root, "init", "-b", "main")
        bootstrap = root / BOOTSTRAP_REL_PATH
        bootstrap.parent.mkdir(parents=True)
        bootstrap.write_text("# an earlier file at the bootstrap path\n", encoding="utf-8")
        (root / "notes.txt").write_text("v1\n", encoding="utf-8")
        git(root, "add", BOOTSTRAP_REL_PATH, "notes.txt")
        git(root, "commit", "-m", "user commit")
        bootstrap.unlink()  # a tracked deletion nobody has committed yet
        (root / "notes.txt").write_text("v2 uncommitted\n", encoding="utf-8")
        before = repository(root)

        raised = self.assertStops("dirty_overlap", root)

        self.assertIn(BOOTSTRAP_REL_PATH, raised.message)
        self.assertFalse((root / ".workline").exists())
        self.assertEqual(repository(root), before)

        git(root, "rm", "--quiet", "--", BOOTSTRAP_REL_PATH)
        git(root, "commit", "-m", "remove the earlier file")
        result = self.start(root)

        self.assertInitialized(root, result)
        self.assertIn(" M notes.txt", status(root))
        self.assertEqual((root / "notes.txt").read_text(encoding="utf-8"), "v2 uncommitted\n")

    def test_a_pre_effect_stop_in_an_existing_repository_changes_nothing_there(self) -> None:
        root = self.new_dir()
        git(root, "init", "-b", "main")
        (root / "tracked.txt").write_text("v1\n", encoding="utf-8")
        ignore_bootstrap(root)
        git(root, "add", "tracked.txt", ".gitignore")
        git(root, "commit", "-m", "user commit")
        (root / "tracked.txt").write_text("v2 uncommitted\n", encoding="utf-8")
        (root / "untracked.txt").write_text("mine\n", encoding="utf-8")
        (root / "staged.txt").write_text("staged\n", encoding="utf-8")
        git(root, "add", "staged.txt")
        before = repository(root)
        names = ("tracked.txt", "untracked.txt", "staged.txt", ".gitignore")
        files = {name: (root / name).read_bytes() for name in names}

        self.assertStops("bootstrap_path_ignored", root)

        self.assertFalse((root / ".workline").exists())
        self.assertEqual(repository(root), before)
        self.assertEqual({name: (root / name).read_bytes() for name in names}, files)

    def test_a_new_start_records_the_snapshot_it_checked_before_any_effect(self) -> None:
        root = self.new_dir()
        (root / "mine.txt").write_text("mine\n", encoding="utf-8")
        steps: list[object] = []
        real_init, real_committable = gitcmd.init_main, ps.ensure_bootstrap_committable
        real_capture, real_separable = gitops.capture_preexisting_dirty, gitops.ensure_separable
        real_begin, real_set_note, real_add_effects = MutationController.begin, Mutation.set_note, Mutation.add_effects

        def init_main(path):
            steps.append("git init")
            return real_init(path)

        def committable(store):
            steps.append("bootstrap committable")
            return real_committable(store)

        def capture(repo):
            steps.append("capture")
            return real_capture(repo)

        def separable(preexisting, owned):
            steps.append(("separable", list(preexisting)))
            return real_separable(preexisting, owned)

        def begin(self_, owner, invocation, scope):
            mutation = real_begin(self_, owner, invocation, scope)
            steps.append("intent")
            # a change that appears once the intent exists is not part of the recorded snapshot
            (root / "late.txt").write_text("after the intent\n", encoding="utf-8")
            return mutation

        def set_note(self_, key, value):
            steps.append(("note", key, list(value)))
            return real_set_note(self_, key, value)

        def add_effects(self_, stage, effects):
            steps.append(("effects", stage))
            return real_add_effects(self_, stage, effects)

        with (
            mock.patch.object(gitcmd, "init_main", init_main),
            mock.patch.object(ps, "ensure_bootstrap_committable", committable),
            mock.patch.object(gitops, "capture_preexisting_dirty", capture),
            mock.patch.object(gitops, "ensure_separable", separable),
            mock.patch.object(MutationController, "begin", begin),
            mock.patch.object(Mutation, "set_note", set_note),
            mock.patch.object(Mutation, "add_effects", add_effects),
        ):
            result = self.start(root)

        self.assertEqual(steps[:7], [
            "git init",
            "bootstrap committable",
            "capture",
            ("separable", ["mine.txt"]),
            "intent",
            ("note", "preexisting_dirty", ["mine.txt"]),
            ("effects", "create"),
        ])
        self.assertInitialized(root, result)
        self.assertEqual(records(root)[result.mutation_id]["notes"], {"preexisting_dirty": ["mine.txt"]})
        self.assertIn("?? mine.txt", status(root))
        self.assertIn("?? late.txt", status(root))

    def test_an_untracked_file_identical_to_the_bootstrap_is_still_not_a_user_change(self) -> None:
        root = self.new_dir()
        user_repository(root)
        bootstrap = root / BOOTSTRAP_REL_PATH
        bootstrap.parent.mkdir(parents=True)
        bootstrap.write_text(render_bootstrap(), encoding="utf-8", newline="\n")

        result = self.start(root)

        self.assertInitialized(root, result)
        self.assertEqual(records(root)[result.mutation_id]["notes"], {"preexisting_dirty": []})
        self.assertEqual(bootstrap.read_bytes(), render_bootstrap().encode("utf-8"))


# --------------------------------------------------------------------------- pending Project開始

class PendingStartTests(RecoveryTestCase):
    def test_a_pending_start_resumes_as_the_same_mutation_with_its_recorded_snapshot(self) -> None:
        root = self.new_dir()
        (root / "mine.txt").write_text("mine\n", encoding="utf-8")
        with mock.patch.object(Mutation, "add_effects", side_effect=RuntimeError("crash before the first effect")):
            with self.assertRaises(RuntimeError):
                self.start(root)
        (pending,) = MutationController(ProjectStore(root)).list_pending()
        self.assertEqual((pending["effects"], pending["notes"]), ([], {"preexisting_dirty": ["mine.txt"]}))
        (root / "later.txt").write_text("changed before the resume\n", encoding="utf-8")

        result = self.start(root)

        self.assertInitialized(root, result)
        self.assertEqual((result.resumed, result.mutation_id), (True, pending["mutation_id"]))
        self.assertEqual(records(root)[result.mutation_id]["notes"], {"preexisting_dirty": ["mine.txt"]})
        self.assertIn("?? later.txt", status(root))

    def test_a_pending_start_without_a_snapshot_records_one_when_it_resumes(self) -> None:
        root = self.new_dir()
        with mock.patch.object(Mutation, "set_note", side_effect=RuntimeError("crash right after the intent")):
            with self.assertRaises(RuntimeError):
                self.start(root)
        (pending,) = MutationController(ProjectStore(root)).list_pending()
        self.assertEqual((pending["effects"], pending["notes"]), ([], {}))
        (root / "mine.txt").write_text("mine\n", encoding="utf-8")

        result = self.start(root)

        self.assertInitialized(root, result)
        self.assertEqual((result.resumed, result.mutation_id), (True, pending["mutation_id"]))
        self.assertEqual(records(root)[result.mutation_id]["notes"], {"preexisting_dirty": ["mine.txt"]})

    def test_a_process_that_dies_after_the_intent_leaves_a_start_that_resumes(self) -> None:
        root = self.new_dir()
        driver = activation(WORKLINE_ROOT) + textwrap.dedent(
            f"""\
            import os
            from pathlib import Path
            from workline import project_start as ps
            from workline.mutation import MutationController

            real_begin = MutationController.begin

            def begin_then_die(self, owner, invocation, scope):
                mutation = real_begin(self, owner, invocation, scope)
                print("INTENT " + mutation.id, flush=True)
                os._exit(3)

            MutationController.begin = begin_then_die
            ps.project_start(Path(r"{root}"), Path(r"{WORKLINE_ROOT}"))
            print("the process did not die", flush=True)
            """
        )

        died = run_python(driver_command(), cwd=self.tmp, stdin=driver)

        self.assertEqual(died.returncode, 3, died.stdout + died.stderr)
        mutation_id = re.search(r"INTENT (mut_\S+)", died.stdout).group(1)
        (pending,) = MutationController(ProjectStore(root)).list_pending()
        self.assertEqual((pending["mutation_id"], pending["effects"], pending["notes"]), (mutation_id, [], {}))
        self.assertTrue((root / ".git").is_dir())

        result = self.start(root)

        self.assertInitialized(root, result)
        self.assertEqual((result.resumed, result.mutation_id), (True, mutation_id))

    def test_a_stop_while_resuming_is_retried_as_a_new_mutation(self) -> None:
        root = self.new_dir()
        with mock.patch.object(Mutation, "set_note", side_effect=RuntimeError("crash right after the intent")):
            with self.assertRaises(RuntimeError):
                self.start(root)
        (pending,) = MutationController(ProjectStore(root)).list_pending()
        gitignore = ignore_bootstrap(root)  # the cause appears before the resume

        self.assertStops("bootstrap_path_ignored", root)

        closed = records(root)[pending["mutation_id"]]
        self.assertEqual((closed["status"], closed["effects"], closed["notes"]), ("abandoned", [], {}))
        self.assertEqual(MutationController(ProjectStore(root)).list_pending(), [])
        old = record_bytes(root)

        gitignore.unlink()
        result = self.start(root)

        self.assertInitialized(root, result)
        self.assertFalse(result.resumed)
        self.assertNotEqual(result.mutation_id, pending["mutation_id"])
        self.assertEqual({name: data for name, data in record_bytes(root).items() if name in old}, old)


# --------------------------------------------------------------------------- abandoned pre-effect residue

class AbandonedResidueRetryTests(RecoveryTestCase):
    def test_one_abandoned_start_is_started_again_as_a_new_mutation(self) -> None:
        root = self.new_dir()
        path = self.abandoned_start(root)
        old = path.read_bytes()

        result = self.start(root)

        self.assertInitialized(root, result)
        self.assertFalse(result.resumed)
        self.assertNotEqual(result.mutation_id, path.stem)
        self.assertEqual(path.read_bytes(), old)
        statuses = {mutation_id: record["status"] for mutation_id, record in records(root).items()}
        self.assertEqual(statuses, {path.stem: "abandoned", result.mutation_id: "completed"})

    def test_several_abandoned_starts_are_started_again_and_left_byte_for_byte(self) -> None:
        root = self.new_dir()
        paths = [
            self.abandoned_start(root),
            self.abandoned_start(root, preexisting=[]),
            self.abandoned_start(root, preexisting=["gone.txt"]),
        ]
        old = record_bytes(root)
        self.assertEqual(len(old), 3)

        result = self.start(root)

        self.assertInitialized(root, result)
        self.assertNotIn(result.mutation_id, [path.stem for path in paths])
        now = record_bytes(root)
        self.assertEqual({name: data for name, data in now.items() if name in old}, old)
        self.assertEqual(len(now), 4)

    def test_the_abandoned_snapshot_is_never_carried_over(self) -> None:
        root = self.new_dir()
        user_repository(root)
        # the earlier STOP saw a deleted file at the bootstrap path, committed since then
        path = self.abandoned_start(root, preexisting=[BOOTSTRAP_REL_PATH, "gone.txt"])
        (root / "mine.txt").write_text("mine\n", encoding="utf-8")

        result = self.start(root)

        self.assertInitialized(root, result)
        self.assertEqual(records(root)[result.mutation_id]["notes"], {"preexisting_dirty": ["mine.txt"]})
        self.assertEqual(records(root)[path.stem]["notes"], {"preexisting_dirty": [BOOTSTRAP_REL_PATH, "gone.txt"]})

    def test_a_snapshot_holding_a_nested_repository_entry_is_started_again(self) -> None:
        root = self.new_dir()
        nested = root / "sub"
        nested.mkdir()
        git(nested, "init", "-q", "-b", "main")
        (nested / "f.txt").write_text("x\n", encoding="utf-8")
        (root / "plain" / "deep").mkdir(parents=True)
        (root / "plain" / "deep" / "g.txt").write_text("y\n", encoding="utf-8")
        # Git reports an untracked nested repository as its directory, with a trailing slash
        snapshot = ["plain/deep/g.txt", "sub/"]
        path = self.abandoned_start(root, preexisting=snapshot)
        old = path.read_bytes()

        result = self.start(root)

        self.assertInitialized(root, result)
        self.assertEqual(path.read_bytes(), old)
        self.assertEqual(records(root)[result.mutation_id]["notes"], {"preexisting_dirty": snapshot})

    def test_an_abandoned_start_next_to_the_repository_it_initialized(self) -> None:
        root = self.new_dir()
        git(root, "init", "-b", "main")
        self.abandoned_start(root)

        result = self.start(root)

        self.assertInitialized(root, result)
        self.assertEqual(git(root, "log", "--format=%s").splitlines(), [ps.INITIAL_COMMIT_MESSAGE])

    def test_current_changes_are_captured_afresh_and_never_committed(self) -> None:
        root = self.new_dir()
        user_repository(root)
        self.abandoned_start(root, preexisting=[])
        (root / "tracked.txt").write_text("v2 uncommitted\n", encoding="utf-8")
        (root / "untracked.txt").write_text("mine\n", encoding="utf-8")
        (root / "staged.txt").write_text("staged\n", encoding="utf-8")
        git(root, "add", "staged.txt")

        result = self.start(root)

        self.assertInitialized(root, result)
        self.assertEqual(
            records(root)[result.mutation_id]["notes"],
            {"preexisting_dirty": ["staged.txt", "tracked.txt", "untracked.txt"]},
        )
        self.assertEqual(git(root, "log", "--format=%s").splitlines(), [ps.INITIAL_COMMIT_MESSAGE, "user commit"])
        lines = status(root)
        self.assertIn(" M tracked.txt", lines)
        self.assertIn("?? untracked.txt", lines)
        self.assertIn("A  staged.txt", lines)

    def test_a_retry_that_stops_again_adds_no_record(self) -> None:
        root = self.new_dir()
        git(root, "init", "-b", "main")
        self.abandoned_start(root)
        old = record_bytes(root)
        gitignore = ignore_bootstrap(root)

        self.assertStops("bootstrap_path_ignored", root)

        self.assertEqual(record_bytes(root), old)
        gitignore.unlink()
        self.assertInitialized(root, self.start(root))

    def test_the_records_left_behind_block_no_later_operation(self) -> None:
        root = self.new_dir()
        path = self.abandoned_start(root)
        old = path.read_bytes()
        self.start(root)
        store = ProjectStore(root)
        self.enter(root)

        work = create_standalone_work(store, WorkSpec("After the retry", "the Project works as usual"))

        self.assertTrue(store.entity_exists("work", work.work_id))
        self.assertEqual(path.read_bytes(), old)
        self.assertEqual(MutationController(store).list_pending(), [])
        checked = run_python(launcher_command(WORKLINE_ROOT, "validate-project", "."), cwd=root)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_the_retry_through_the_canonical_launcher(self) -> None:
        root = self.new_dir()
        path = self.abandoned_start(root)
        old = path.read_bytes()

        started = run_python(
            launcher_command(WORKLINE_ROOT, "project-start", root, "--workline-root", WORKLINE_ROOT), cwd=self.tmp
        )

        self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
        self.assertIn("project-start: initialized", started.stdout)
        self.assertEqual(path.read_bytes(), old)
        checked = run_python(launcher_command(WORKLINE_ROOT, "validate-project", "."), cwd=root)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_an_established_project_is_still_already_initialized(self) -> None:
        store = self.new_project()
        path = self.abandoned_start(store.root)
        head = gitcmd.head_commit(store.root)

        result = self.start(store.root)

        self.assertEqual((result.status, result.head), ("already_initialized", head))
        self.assertTrue(path.is_file())


class UnsafeResidueTests(RecoveryTestCase):
    def test_a_record_not_proven_abandoned_before_its_first_effect_is_not_retried(self) -> None:
        files = list(DECLARED)
        effect = {
            "seq": 1,
            "stage": "create",
            "kind": "write_file",
            "payload": {"path": ".workline/project.yaml", "content": "x"},
            "applied": False,
        }
        changes = {
            "an effect": lambda r: r.update(effects=[effect]),
            "a reserved ID": lambda r: r.update(reserved_ids={"work:0": WORK_ID}),
            "another owner": lambda r: r.update(owner="bootstrap-backfill"),
            "completed": lambda r: r.update(status="completed"),
            "pending for another owner": lambda r: r.update(status="pending", owner="roadmap"),
            "another Project root": lambda r: r["invocation"].update(project_root=str(self.tmp / "elsewhere")),
            "an extra invocation field": lambda r: r["invocation"].update(expected_push_url=PUSH_URL),
            "an invocation without its root": lambda r: r["invocation"].pop("project_root"),
            "a scope subset": lambda r: r["write_scope"].update(files=files[1:]),
            "a scope superset": lambda r: r["write_scope"].update(files=sorted([*files, ".workline/roadmaps/r.md"])),
            "a duplicated scope path": lambda r: r["write_scope"].update(files=sorted([*files, files[0]])),
            "a scope out of canonical order": lambda r: r["write_scope"].update(files=files[::-1]),
            "scope entities": lambda r: r["write_scope"].update(entities=[WORK_ID]),
            "an unknown note": lambda r: r.update(notes={"reason": "left over"}),
            "an unsorted snapshot": lambda r: r.update(notes={"preexisting_dirty": ["b.txt", "a.txt"]}),
            "a duplicated snapshot path": lambda r: r.update(notes={"preexisting_dirty": ["a.txt", "a.txt"]}),
            "a runtime path in the snapshot": lambda r: r.update(notes={"preexisting_dirty": [".workline/runtime/x"]}),
            "a snapshot that is not paths": lambda r: r.update(notes={"preexisting_dirty": [1]}),
            "an unknown top-level field": lambda r: r.update(origin="elsewhere"),
            "a version that is not a number": lambda r: r.update(version=True),
            "an unreadable timestamp": lambda r: r.update(created_at="yesterday"),
            "an empty timestamp": lambda r: r.update(completed_at=""),
        }
        for label, change in changes.items():
            with self.subTest(record=label):
                root = self.new_dir(slug(label))
                self.rewrite(self.abandoned_start(root), change)
                self.assertNotRetried(root)

    def test_a_snapshot_path_workline_could_not_have_recorded_is_not_retried(self) -> None:
        malformed = ("../outside", "/absolute", "a/./b", "a//b", "./a", "a/..", "a//", "/", "C:/drive", "//server/share")
        for number, path in enumerate(malformed):
            with self.subTest(snapshot_path=path):
                root = self.new_dir(f"snapshot-{number}")
                record = self.abandoned_start(root, preexisting=[path])
                old = record_bytes(root)

                self.assertNotRetried(root)

                self.assertEqual(record_bytes(root), old)
                self.assertEqual(list(records(root)), [record.stem])

    def test_each_missing_field_stops_as_partial_or_as_unconfirmed_ownership(self) -> None:
        for field in sorted(CLOSED_INTENT_FIELDS):
            expected = RECONCILE if field in OWNERSHIP_FIELDS else PARTIAL
            with self.subTest(missing=field, expected=expected):
                root = self.new_dir(f"missing-{field}")
                self.rewrite(self.abandoned_start(root), lambda r: r.pop(field))
                self.assertNotRetried(root, expected)

    def test_records_workline_cannot_confirm_stop_as_reconcile_required(self) -> None:
        cases = {
            "a yaml file that is not a mutation": lambda path: (path.parent / "notes.yaml").write_text(
                "status: abandoned\n", encoding="utf-8"
            ),
            "malformed YAML": lambda path: path.write_text("workline: [unclosed\n", encoding="utf-8"),
            "an unsupported intent version": lambda path: self.rewrite(path, lambda r: r.update(version=INTENT_VERSION + 1)),
            "another intent marker": lambda path: self.rewrite(path, lambda r: r.update(workline="someone-else")),
        }
        for label, change in cases.items():
            with self.subTest(record=label):
                root = self.new_dir(slug(label))
                change(self.abandoned_start(root))
                self.assertNotRetried(root, RECONCILE)

    def test_anything_but_recovery_records_in_workline_is_not_retried(self) -> None:
        def file(relative: str, text: str = "x\n"):
            def write(root: Path) -> None:
                path = root / ".workline" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")

            return write

        def directory(relative: str):
            return lambda root: (root / ".workline" / relative).mkdir(parents=True)

        additions = {
            "project.yaml": file("project.yaml", render_project_yaml(WORKLINE_ROOT)),
            "relations": file("relations/roadmap.yaml", "relations: []\n"),
            "events": file("events/events.jsonl", ""),
            "an empty roadmaps directory": directory("roadmaps"),
            "an empty phases directory": directory("phases"),
            "an empty works directory": directory("works"),
            "an empty derivations directory": directory("derivations"),
            "another file in .workline": file("notes.txt"),
            "a lock area": file("runtime/locks/project.lock", ""),
            "another runtime file": file("runtime/notes.txt"),
            "another runtime directory": directory("runtime/cache"),
            "a leftover temporary file": file("runtime/tmp/.mut_x.yaml.1.abcd.tmp", "partial"),
            "a file that is not a record": file("runtime/mutations/README.txt"),
            "a directory among the records": directory("runtime/mutations/sub"),
        }
        for label, add in additions.items():
            with self.subTest(content=label):
                root = self.new_dir(slug(label))
                self.abandoned_start(root)
                add(root)
                self.assertNotRetried(root)

    def test_a_workline_without_any_record_is_not_retried(self) -> None:
        layouts = {
            "an empty .workline": [".workline"],
            "an empty runtime area": [".workline/runtime"],
            "an empty mutation area": [".workline/runtime/mutations", ".workline/runtime/tmp"],
            "only a temporary area": [".workline/runtime/tmp"],
        }
        for label, directories in layouts.items():
            with self.subTest(layout=label):
                root = self.new_dir(slug(label))
                for relative in directories:
                    (root / relative).mkdir(parents=True)
                self.assertNotRetried(root)

    def test_a_workline_the_repository_holds_is_not_retried(self) -> None:
        for state in ("staged", "committed", "in HEAD only"):
            with self.subTest(state=state):
                root = self.new_dir(slug(state))
                git(root, "init", "-b", "main")
                relative = self.abandoned_start(root).relative_to(root).as_posix()
                git(root, "add", relative)
                if state != "staged":
                    git(root, "commit", "-m", "a recovery record committed by hand")
                if state == "in HEAD only":
                    git(root, "rm", "--quiet", "--cached", "--", relative)
                raised = self.assertNotRetried(root)
                self.assertIn(relative, raised.message)

    def test_indirection_in_the_residue_is_not_retried(self) -> None:
        for relative in (".workline", ".workline/runtime", ".workline/runtime/mutations"):
            with self.subTest(linked=relative):
                root = self.new_dir(slug(relative))
                self.abandoned_start(root)
                real = self.tmp / f"{root.name}-real"
                (root / relative).rename(real)
                if not self.directory_link(real, root / relative):
                    self.skipTest("directory links are refused here")
                self.assertNotRetried(root)
        with self.subTest(linked="a recovery record"):
            root = self.new_dir("linked-record")
            path = self.abandoned_start(root)
            real = self.tmp / "record-elsewhere.yaml"
            path.rename(real)
            try:
                os.symlink(real, path)
            except OSError:
                self.skipTest("file symlinks are refused here")
            self.assertNotRetried(root)

    def test_a_dangling_workline_link_is_not_retried(self) -> None:
        root = self.new_dir()
        target = self.tmp / "workline-link-target"
        target.mkdir()
        if not self.directory_link(target, root / ".workline"):
            self.skipTest("directory links are refused here")
        target.rmdir()  # the link now points nowhere
        self.assertFalse((root / ".workline").exists())
        self.assertTrue(os.path.lexists(root / ".workline"))

        self.assertNotRetried(root)

        self.assertFalse((root / ".git").exists())
        self.assertFalse(target.exists())
        self.assertEqual(sorted(entry.name for entry in root.iterdir()), [".workline"])
        self.assertEqual(MutationController(ProjectStore(root)).list_records(), [])

    def test_records_left_in_a_folder_that_has_moved_are_not_retried(self) -> None:
        before_move = self.new_dir("before-move")
        path = self.abandoned_start(before_move)
        moved = before_move.rename(self.tmp / "after-move")

        raised = self.assertNotRetried(moved)

        self.assertIn(path.stem, raised.message)

    def test_a_bootstrap_conflict_still_stops_first(self) -> None:
        root = self.new_dir()
        path = self.abandoned_start(root)
        old = path.read_bytes()
        bootstrap = root / BOOTSTRAP_REL_PATH
        bootstrap.parent.mkdir(parents=True)
        bootstrap.write_text("# someone else owns this\n", encoding="utf-8")

        self.assertStops("bootstrap_conflict", root)

        self.assertEqual(bootstrap.read_text(encoding="utf-8"), "# someone else owns this\n")
        self.assertEqual(record_bytes(root), {path.name: old})
        self.assertFalse((root / ".git").exists())

    def test_the_push_destination_check_is_not_bypassed(self) -> None:
        with self.subTest(left="a repository"):
            root = self.new_dir("repository-left")
            gitignore = ignore_bootstrap(root)
            self.assertStops("bootstrap_path_ignored", root)
            gitignore.unlink()
            self.assertStops("push_destination_remote_missing", root, expected_push_url=PUSH_URL)
            self.assertFalse((root / ".workline").exists())
        with self.subTest(left="a repository and an abandoned start"):
            root = self.new_dir("repository-and-record-left")
            git(root, "init", "-b", "main")
            path = self.abandoned_start(root)
            old = path.read_bytes()
            self.assertStops("push_destination_remote_missing", root, expected_push_url=PUSH_URL)
            self.assertEqual(record_bytes(root), {path.name: old})


# --------------------------------------------------------------------------- what stays as it was

class RecoveryContractTests(RecoveryTestCase):
    def test_a_closed_intent_has_exactly_the_fields_the_retry_accepts(self) -> None:
        self.assertEqual((INTENT_MARKER, INTENT_VERSION), ("workline-mutation-intent", 1))
        self.assertEqual(set(ps._CLOSED_INTENT_FIELDS), CLOSED_INTENT_FIELDS)
        root = self.new_dir()
        record = yamlish.load(self.abandoned_start(root).read_text(encoding="utf-8"))
        self.assertEqual(set(record), CLOSED_INTENT_FIELDS)
        self.assertEqual(
            (record["workline"], record["version"], record["owner"], record["status"]),
            (INTENT_MARKER, INTENT_VERSION, ps.OWNER, "abandoned"),
        )
        self.assertEqual(record["invocation"], {"operation": ps.OWNER, "project_root": str(root.resolve())})
        self.assertEqual(record["write_scope"], {"entities": [], "files": DECLARED})
        self.assertEqual((record["reserved_ids"], record["notes"], record["effects"]), ({}, {}, []))

        started = self.new_dir("started")
        with mock.patch.object(Mutation, "set_note", side_effect=RuntimeError("crash right after the intent")):
            with self.assertRaises(RuntimeError):
                self.start(started)
        (pending,) = MutationController(ProjectStore(started)).list_pending()
        self.assertEqual(set(pending), CLOSED_INTENT_FIELDS - {"completed_at"})
        result = self.start(started)
        self.assertEqual(set(records(started)[result.mutation_id]), CLOSED_INTENT_FIELDS)

    def test_what_a_retried_start_writes_is_unchanged(self) -> None:
        root = self.new_dir()
        self.abandoned_start(root)

        result = self.start(root)

        self.assertInitialized(root, result)
        store = ProjectStore(root)
        self.assertEqual(hashlib.sha256(render_bootstrap().encode("utf-8")).hexdigest(), BOOTSTRAP_SHA256)
        self.assertEqual((root / BOOTSTRAP_REL_PATH).read_bytes(), render_bootstrap().encode("utf-8"))
        self.assertEqual(store.project_yaml.read_text(encoding="utf-8"), render_project_yaml(WORKLINE_ROOT))
        self.assertEqual(set(store.load_project_yaml()), {"workline", "rules"})
        self.assertEqual(store.events_jsonl.read_bytes(), b"")
        self.assertEqual(store.read_events(), [])
        self.assertEqual(set(Event("evt_x", "work_started", WORK_ID, "at").to_record()), {"id", "type", "entity", "at"})

    def test_the_retry_adds_no_cleanup_and_no_start_serialization(self) -> None:
        source = inspect.getsource(ps)
        for removal in ("unlink(", "rmtree(", "rmdir(", "os.remove(", ".rename(", "os.replace("):
            self.assertNotIn(removal, source)
        self.assertNotIn("oplock", source)
        self.assertNotIn("project_operation", source)
        self.assertEqual(
            {name for name in vars(MutationController) if not name.startswith("_")},
            {
                "intent_path", "list_records", "list_pending", "load", "require_execution_lock",
                "open", "begin", "validate_effect", "classify", "apply_effect",
            },
        )
        self.assertEqual(
            {name for name in vars(Mutation) if not name.startswith("_")},
            {
                "id", "owner", "invocation", "scope", "status", "effects", "reserve_id", "reserved", "note",
                "set_note", "extend_scope", "has_stage", "stage_effects", "add_effects", "apply", "complete", "abandon",
            },
        )
        commands = set(re.findall(r'add_parser\(\s*"([^"]+)"', inspect.getsource(cli)))
        self.assertIn("project-start", commands)
        self.assertEqual({c for c in commands if re.search(r"clean|prune|purge|repair|reconcile|abandon|retry|recover", c)}, set())
        self.assertEqual(
            list(inspect.signature(ps.project_start).parameters),
            ["project_root", "workline_root", "expected_push_url", "push_remote"],
        )

        root = self.new_dir()
        path = self.abandoned_start(root)
        store = ProjectStore(root)
        held: list[object] = []
        real_open = MutationController.open

        def open_(self_, owner, invocation, scope):
            held.append(oplock.held_lock(store))
            return real_open(self_, owner, invocation, scope)

        with mock.patch.object(MutationController, "open", open_):
            self.start(root)

        self.assertEqual(held, [None])
        self.assertFalse(store.locks.exists())
        self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
