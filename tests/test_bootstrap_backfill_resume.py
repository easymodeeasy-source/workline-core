"""An interrupted bootstrap backfill finishes its own mutation - and only its own (BL-034).

Bootstrap backfill looked at the bootstrap before it looked for its own unfinished record. Once its commit had
been recorded, anything that got interrupted afterwards - the commit refused by a hook after ``git add``, the push
refused by the remote, the process ending after the push - left a matching, tracked bootstrap, and the retry
returned ``already_present`` without ever opening the record: the bootstrap stayed staged and uncommitted, or
committed and unpushed, and the record stayed pending for good, so push-destination pin maintenance refused with
``pending_operation`` from then on. A retry that did resume (commit recorded, ``git add`` not run yet) made the
commit and the push and then reported ``postcheck: backfill commit missing``, because it looked for the commit
as HEAD having moved after the replay had already moved it.

The retry now asks the recovery records first. Its own record is continued as the same mutation, and the
backfill commit is looked for in the history since the base the commit was recorded on. The bootstrap is one
fixed text, though, so its content never shows whose it is: a bootstrap Git already holds is taken for the
backfill's only when the record holds the commit as made, and a record that decided nothing is closed without
committing or pushing anything. A record that cannot be shown to be this backfill's - two of them, one written
for another root, one in another shape, one that decided another bootstrap than this implementation writes -
is refused and left exactly as it is.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from helpers import WorklineTestCase, cwd, git
from test_recorded_commit_resume import HOOK, REFUSE_FLAG, Interrupted, after_applying
from workline import bootstrap as bs
from workline import yamlish
from workline.errors import GitError, StopError
from workline.ids import new_id
from workline.mutation import Mutation, MutationController
from workline.push_pin import pin_push_destination
from workline.store import BOOTSTRAP_REL_PATH, WORKLINE_DIR
from workline.validate import validate_project

MAIN = "refs/heads/main"
REFUSE_PUSH_FLAG = "workline-test-refuse-push"
REFUSE_PUSH_HOOK = f"""#!/bin/sh
# pre-receive hook of the bare remote: refuses every push while the flag exists
if [ -f "{REFUSE_PUSH_FLAG}" ]; then
  echo "push refused by the remote" >&2
  exit 1
fi
exit 0
"""


# --------------------------------------------------------------------------- where the backfill is interrupted
def stop_recording(stage: str, *, after: bool):
    """Stop the backfill right before, or right after, it durably records ``stage``."""
    real = Mutation.add_effects

    def fire(mutation, recorded, effects):
        if recorded == stage and not after:
            raise Interrupted(f"before recording {recorded}")
        real(mutation, recorded, effects)
        if recorded == stage:
            raise Interrupted(f"recorded {recorded}")

    return mock.patch.object(Mutation, "add_effects", fire)


def stop_after_executing(kind: str):
    """Stop right after an effect of ``kind`` really ran, before it is recorded as applied."""
    real = MutationController.apply_effect

    def fire(controller, record):
        real(controller, record)
        if record["kind"] == kind:
            raise Interrupted(f"{kind} done, not recorded")

    return mock.patch.object(MutationController, "apply_effect", fire)


def stop_before_complete():
    def fire(mutation):
        raise Interrupted("everything done, not completed")

    return mock.patch.object(Mutation, "complete", fire)


class BackfillCase(WorklineTestCase):
    def build(self, name: str = "proj", *, remote: bool = True) -> None:
        """A Project from before the bootstrap Skill, with a pinned remote unless ``remote`` is false."""
        self.name = name
        self.store = self.new_project(name, remote=remote)
        self.root = self.store.root
        self.remote = self.remote_path(name) if remote else None
        git(self.root, "rm", "-q", "--", BOOTSTRAP_REL_PATH)
        git(self.root, "commit", "-q", "-m", "chore: a Project from before the bootstrap Skill")
        hooks = self.root / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        (hooks / "pre-commit").write_text(HOOK, encoding="utf-8", newline="\n")
        os.chmod(hooks / "pre-commit", 0o755)
        git(self.root, "config", "core.hooksPath", hooks.as_posix())
        if remote:
            git(self.root, "push", "-q", "origin", "main:main")
            (self.remote / "hooks" / "pre-receive").write_text(REFUSE_PUSH_HOOK, encoding="utf-8", newline="\n")
        self.legacy = self.head()
        self.assertEqual(bs.bootstrap_state(self.store), bs.ABSENT)

    # interrupting -----------------------------------------------------------------------
    def interrupt(self, window: str) -> dict:
        """Run the backfill into ``window``; return the record it leaves pending."""
        flags = {"commit refused": self.root / ".git" / REFUSE_FLAG}
        if self.remote is not None:
            flags["push refused"] = self.remote / REFUSE_PUSH_FLAG
        stops = {
            "decided nothing": lambda: stop_recording("bootstrap", after=False),
            "bootstrap recorded": lambda: stop_recording("bootstrap", after=True),
            "bootstrap applied": lambda: after_applying(r"^bootstrap$"),
            "commit recorded": lambda: stop_recording("commit", after=True),
            "commit made": lambda: stop_after_executing("git_commit"),
            "pushed": lambda: stop_after_executing("git_push"),
            "not completed": stop_before_complete,
        }
        try:
            if window in flags:
                flags[window].write_text("refuse\n", encoding="utf-8")
                with self.assertRaises(GitError):
                    bs.backfill_bootstrap(self.root)
            else:
                with stops[window](), self.assertRaises(Interrupted):
                    bs.backfill_bootstrap(self.root)
        finally:
            for flag in flags.values():
                if flag.exists():
                    flag.unlink()
        (pending,) = MutationController(self.store).list_pending()
        return pending

    def retry(self, executed: list[str]):
        """The same backfill again, recording the kind of every effect it actually executes."""
        real = MutationController.apply_effect

        def watch(controller, record):
            executed.append(record["kind"])
            return real(controller, record)

        with mock.patch.object(MutationController, "apply_effect", watch):
            return bs.backfill_bootstrap(self.root)

    def edit_record(self, pending: dict, change) -> None:
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8")

    def commit_bootstrap(self, message: str, *, push: bool = False) -> None:
        """A person commits the expected bootstrap themselves."""
        path = self.root / BOOTSTRAP_REL_PATH
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(bs.render_bootstrap(), encoding="utf-8")
        git(self.root, "add", "--", BOOTSTRAP_REL_PATH)
        git(self.root, "commit", "-q", "-m", message, "--", BOOTSTRAP_REL_PATH)
        if push:
            git(self.root, "push", "-q", "origin", "main:main")

    # observing --------------------------------------------------------------------------
    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote, "rev-parse", "main").strip()

    def dirty(self) -> list[str]:
        status = git(self.root, "status", "--porcelain", "--untracked-files=all").splitlines()
        return [line for line in status if ".workline/runtime/" not in line]

    def statuses(self) -> dict[str, str]:
        return {r["mutation_id"]: r["status"] for r in MutationController(self.store).list_records()}

    def snapshot(self) -> dict:
        """Everything a refused retry must leave exactly as it was - the records byte for byte."""
        bootstrap = self.root / BOOTSTRAP_REL_PATH
        return {
            "records": {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))},
            "bootstrap": bootstrap.read_bytes() if bootstrap.exists() else None,
            "on": git(self.root, "symbolic-ref", "--quiet", "HEAD", check=False).strip(),
            "refs": git(self.root, "for-each-ref", "--format=%(refname) %(objectname)"),
            "remote refs": git(self.remote, "for-each-ref", "--format=%(refname) %(objectname)") if self.remote else None,
            "index": git(self.root, "diff", "--cached", "--name-status"),
            "dirty": self.dirty(),
        }

    def assertStopsUntouched(self, fragment: str) -> None:
        before, executed = self.snapshot(), []
        with self.assertRaises(StopError) as stopped:
            self.retry(executed)
        self.assertEqual(stopped.exception.code, "reconcile_required", stopped.exception.message)
        self.assertIn(fragment, stopped.exception.message)
        self.assertEqual(executed, [])
        self.assertEqual(self.snapshot(), before)

    def assertFinished(self, pending: dict, result, executed: list[str], expected: list[str]) -> None:
        """The same mutation finished: one backfill commit with the bootstrap alone, pushed, nothing left over."""
        self.assertEqual((result.status, result.mutation_id, result.resumed), ("created", pending["mutation_id"], True))
        self.assertEqual(executed, expected)
        self.assertEqual(self.statuses()[pending["mutation_id"]], "completed")
        self.assertEqual(MutationController(self.store).list_pending(), [])
        commits = git(self.root, "rev-list", f"{self.legacy}..HEAD", "--", BOOTSTRAP_REL_PATH).split()
        self.assertEqual(len(commits), 1, commits)
        self.assertEqual(git(self.root, "log", "-1", "--format=%B", commits[0]).strip(), bs.BACKFILL_COMMIT_MESSAGE)
        self.assertEqual(git(self.root, "show", "--name-only", "--format=", commits[0]).split(), [BOOTSTRAP_REL_PATH])
        self.assertEqual(bs.bootstrap_state(self.store), bs.MATCHING)
        self.assertEqual(self.dirty(), [])
        self.assertEqual(validate_project(self.store), [])
        if self.remote is not None:
            self.assertEqual(self.remote_head(), self.head())
            # nothing blocks the pin maintenance any more
            self.assertEqual(pin_push_destination(self.root, [self.remote_url(self.name)]).status, "already_pinned")
        again = bs.backfill_bootstrap(self.root)
        self.assertEqual((again.status, again.mutation_id), ("already_present", None))


# --------------------------------------------------------------------------- 1 / 7 / 8 / 9: its own interruption
class OwnInterruptionTests(BackfillCase):
    #: window -> what the retry still has to execute
    GIT_WINDOWS = {
        "commit recorded": ["git_commit", "git_push"],   # W3a: the retry used to fail its postcheck after pushing
        "commit refused": ["git_commit", "git_push"],    # W3b: the bootstrap staged, reported already present
        "push refused": ["git_push"],                    # W4: committed, never pushed, reported already present
        "pushed": [],                                    # W5: pushed, the record left pending for good
        "not completed": [],                             # W5: only the record left to close
    }

    def test_each_git_window_finishes_the_same_mutation(self) -> None:
        for index, (window, expected) in enumerate(self.GIT_WINDOWS.items()):
            with self.subTest(window=window):
                self.build(f"own-{index}")
                pending = self.interrupt(window)
                executed: list[str] = []

                result = self.retry(executed)

                self.assertFinished(pending, result, executed, expected)

    def test_without_a_remote(self) -> None:
        for index, (window, expected) in enumerate((("commit recorded", ["git_commit"]), ("commit refused", ["git_commit"]),
                                                    ("not completed", []))):
            with self.subTest(window=window):
                self.build(f"local-{index}", remote=False)
                pending = self.interrupt(window)
                executed: list[str] = []

                result = self.retry(executed)

                self.assertFinished(pending, result, executed, expected)

    def test_an_interruption_before_the_commit_still_converges(self) -> None:
        for index, (window, expected) in enumerate((
            ("decided nothing", ["write_file", "git_commit", "git_push"]),
            ("bootstrap recorded", ["write_file", "git_commit", "git_push"]),
            ("bootstrap applied", ["git_commit", "git_push"]),
        )):
            with self.subTest(window=window):
                self.build(f"before-{index}")
                pending = self.interrupt(window)
                executed: list[str] = []

                result = self.retry(executed)

                self.assertFinished(pending, result, executed, expected)


# --------------------------------------------------------------------------- 2 / 3: a bootstrap someone else committed
class ForeignBootstrapTests(BackfillCase):
    def test_without_an_unfinished_backfill_the_fast_path_is_unchanged(self) -> None:
        for index, push in enumerate((False, True)):
            with self.subTest(pushed=push):
                self.build(f"foreign-{index}")
                self.commit_bootstrap("docs: add the workline skill by hand", push=push)
                remote = self.remote_head()
                opened: list[str] = []
                real = MutationController.open

                def watch(controller, owner, invocation, scope):
                    opened.append(owner)
                    return real(controller, owner, invocation, scope)

                with mock.patch.object(MutationController, "open", watch):
                    result = bs.backfill_bootstrap(self.root)

                self.assertEqual((result.status, result.mutation_id, opened), ("already_present", None, []))
                self.assertEqual(self.remote_head(), remote)
                self.assertEqual(list(self.store.mutations.glob("*.yaml")) if self.store.mutations.is_dir() else [], [])

    def test_a_backfill_that_decided_nothing_is_closed_without_pushing_what_someone_else_committed(self) -> None:
        self.build("undecided")
        pending = self.interrupt("decided nothing")
        self.assertEqual(pending["effects"], [])
        self.commit_bootstrap("docs: add the workline skill by hand")
        remote, head = self.remote_head(), self.head()
        executed: list[str] = []

        result = self.retry(executed)

        self.assertEqual((result.status, result.mutation_id, executed), ("already_present", None, []))
        self.assertEqual(self.statuses()[pending["mutation_id"]], "abandoned")
        self.assertEqual((self.head(), self.remote_head()), (head, remote))  # the person's commit stays unpushed, theirs
        self.assertEqual(pin_push_destination(self.root, [self.remote_url(self.name)]).status, "already_pinned")

    def test_a_bootstrap_the_record_does_not_hold_as_committed_is_not_pushed_as_its_own(self) -> None:
        def pulled_from_another_clone():
            other = self.tmp / f"{self.name}-other"
            git(self.tmp, "clone", "-q", str(self.remote), str(other))
            with cwd(other):
                self.assertEqual(bs.backfill_bootstrap(other).status, "created")
            git(self.root, "pull", "-q", "--ff-only", "origin", "main")

        cases = {
            # its own commit, made just before the interruption kept it from being recorded as made (W4)
            "commit made, not recorded": ("commit made", lambda: None),
            "someone commits the bootstrap it staged": ("commit refused",
                                                        lambda: self.commit_bootstrap("docs: commit what was staged")),
            "someone commits it with the backfill's message": ("commit recorded",
                                                               lambda: self.commit_bootstrap(bs.BACKFILL_COMMIT_MESSAGE)),
            "another clone's backfill is pulled after it decided": ("bootstrap recorded", pulled_from_another_clone),
        }
        for index, (label, (window, then)) in enumerate(cases.items()):
            with self.subTest(case=label):
                self.build(f"unowned-{index}")
                self.interrupt(window)
                then()

                self.assertStopsUntouched("already holds the bootstrap")


# --------------------------------------------------------------------------- 4 / 5 / 6: a record it cannot show is its own
class UnprovableRecordTests(BackfillCase):
    def test_records_that_do_not_show_this_backfill_stop_untouched(self) -> None:
        def duplicate(pending):
            path = MutationController(self.store).intent_path(pending["mutation_id"])
            record = yamlish.load(path.read_text(encoding="utf-8"))
            record["mutation_id"] = new_id("mutation")
            (path.parent / f"{record['mutation_id']}.yaml").write_text(yamlish.dump(record), encoding="utf-8")

        def moved(record):
            record["invocation"]["project_root"] += "-before-it-moved"

        def branchless(record):
            for effect in record["effects"]:
                effect["payload"].pop("branch", None)

        def edited_bootstrap(record):
            record["effects"][0]["payload"]["content"] += "edited\n"

        def writes_more(record):
            record["effects"].append({"seq": 2, "stage": "bootstrap", "kind": "write_file", "applied": False,
                                      "payload": {"path": f"{WORKLINE_DIR}/project.yaml", "content": "workline: {}\n"}})

        cases = {
            "two unfinished backfills": ("commit refused", duplicate, "2 unfinished bootstrap backfills"),
            "recorded for another root, as a moved Project leaves it": ("commit refused", lambda p: self.edit_record(p, moved),
                                                                         "for another invocation"),
            "a commit recorded before commits carried their branch": ("commit refused", lambda p: self.edit_record(p, branchless),
                                                                       "without the branch"),
            "the decided bootstrap edited": ("commit refused", lambda p: self.edit_record(p, edited_bootstrap),
                                             "a bootstrap other than the one this Workline implementation writes"),
            "a record that writes more than the bootstrap": ("bootstrap recorded", lambda p: self.edit_record(p, writes_more),
                                                             "other stages"),
        }
        for index, (label, (window, change, fragment)) in enumerate(cases.items()):
            with self.subTest(case=label):
                self.build(f"unprovable-{index}")
                pending = self.interrupt(window)
                change(pending)

                self.assertStopsUntouched(fragment)

        with self.subTest(case="decided by an implementation with another bootstrap"):
            self.build("other-template")
            self.interrupt("bootstrap recorded")
            with mock.patch.object(bs, "_BOOTSTRAP_TEXT", bs._BOOTSTRAP_TEXT + "\n<!-- a later version -->\n"):
                self.assertStopsUntouched("a bootstrap other than the one this Workline implementation writes")


# --------------------------------------------------------------------------- the recorded commit, as for any owner
class RecordedCommitTests(BackfillCase):
    def test_a_commit_that_left_the_bootstrap_alone_neither_stops_it_nor_stands_in_for_it(self) -> None:
        cases = {
            "an independent commit": "docs: a note",                                   # BL-032: made on top of it
            "an unrelated commit with the backfill's message": bs.BACKFILL_COMMIT_MESSAGE,  # BL-033: not taken for it
        }
        for index, (label, message) in enumerate(cases.items()):
            with self.subTest(case=label):
                self.build(f"recorded-{index}")
                pending = self.interrupt("commit refused")
                (self.root / "notes.md").write_text("notes\n", encoding="utf-8")
                git(self.root, "add", "--", "notes.md")
                git(self.root, "commit", "-q", "-m", message, "--", "notes.md")
                independent = self.head()
                executed: list[str] = []

                result = self.retry(executed)

                self.assertFinished(pending, result, executed, ["git_commit", "git_push"])
                made = git(self.root, "rev-list", f"{self.legacy}..HEAD", "--", BOOTSTRAP_REL_PATH).split()
                self.assertEqual(git(self.root, "rev-parse", f"{made[0]}^").strip(), independent)


# --------------------------------------------------------------------------- 10: the branch guards now apply
class BranchTests(BackfillCase):
    def test_another_branch_stops_and_the_original_branch_goes_on(self) -> None:
        cases = {
            # the recorded commit guards its branch (BL-035)
            "commit refused": ("applied with unexpected result", ["git_commit", "git_push"]),
            # the decision guards its branch until its commit is recorded (BL-036)
            "bootstrap applied": ("no recorded commit finalizes", ["git_commit", "git_push"]),
        }
        for index, (window, (fragment, expected)) in enumerate(cases.items()):
            with self.subTest(window=window):
                self.build(f"branch-{index}")
                pending = self.interrupt(window)
                git(self.root, "checkout", "-q", "-b", "side")

                self.assertStopsUntouched(fragment)

                git(self.root, "checkout", "-q", "main")
                executed: list[str] = []
                result = self.retry(executed)
                self.assertFinished(pending, result, executed, expected)
                self.assertEqual(git(self.root, "symbolic-ref", "HEAD").strip(), MAIN)


if __name__ == "__main__":
    unittest.main()
