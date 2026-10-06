"""RB10 N4: the interruption / recovery matrix of a Human recovery disposition (``WORKLINE_COMPLETION_SPRINT.md`` §35.27).

Ten points, for a mutation target (a Project with an approved remote, so the
Git stage commits and pushes) and for a Review Run target (remote-less, so
points 8 and 9 have no push to interrupt):

```text
 1 after Human admission, before the disposition mutation opens
 2 the disposition mutation opened, no effect
 3 the disposition effect recorded
 4 the immutable file created, before its applied flag is saved
 5 the disposition file applied
 6 the commit stage recorded
 7 the commit made, before its applied flag is saved
 8 the push stage recorded
 9 the push made, before its applied flag is saved
10 everything applied, before the disposition mutation completes
```

After the interruption, and after the same request is run again, each point
holds: one disposition record, with the same target digest and reason; the
target mutation / Review records never rewritten; no duplicate commit or
publication; no automatic resume of the disposed target; and no other
operation begins while the disposition itself is pending.

Point 7 with a remote inherits the Mutation Controller's rule for a commit made
right before an interruption kept its ID from being saved (BL-037 / BL-050): no
recorded push can show which commit it publishes, so the retry stops at
``reconcile required`` and publishes nothing, and the pending disposition goes
on holding every other owner back.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest import mock

from test_recovery_disposition import REASON, DispositionCase
from test_recovery_disposition_review import ReviewTargetCase
from test_work_terminal import Crash

from workline import gitcmd
from workline import recovery_disposition as rd
from workline.errors import ReconcileRequired
from workline.mutation import Mutation, MutationController, WriteScope
from workline.oplock import project_operation
from workline.review.store import ReviewStore

SUBJECT = "chore(workline): set aside recovery "
LEDGERS = (".workline/events/events.jsonl", ".workline/relations/roadmap.yaml", ".workline/relations/related.yaml")


def _after(real, condition=lambda *args, **kwargs: True):
    """A replacement that does the real thing, then dies (when ``condition`` holds for the call)."""

    def call(*args, **kwargs):
        result = real(*args, **kwargs)
        if condition(*args, **kwargs):
            raise Crash("killed right after it")
        return result

    return call


@contextmanager
def interruption(point: int):
    """Kill the disposition at ``point`` of the matrix."""
    real_apply_effect = MutationController.apply_effect
    if point == 1:
        patcher = mock.patch.object(rd, "open_disposition_mutation", side_effect=Crash("killed"))
    elif point == 2:
        patcher = mock.patch.object(rd, "_witness", side_effect=Crash("killed"))
    elif point == 3:
        patcher = mock.patch.object(Mutation, "apply", side_effect=Crash("killed"))
    elif point == 4:
        patcher = mock.patch.object(MutationController, "apply_effect", autospec=True, side_effect=_after(
            real_apply_effect, lambda self, record: record["kind"] == "create_file"))
    elif point == 5:
        patcher = mock.patch("workline.gitops.finalize", side_effect=Crash("killed"))
    elif point == 6:
        patcher = mock.patch.object(gitcmd, "commit_only", side_effect=Crash("killed"))
    elif point == 7:
        patcher = mock.patch.object(gitcmd, "commit_only", side_effect=_after(gitcmd.commit_only))
    elif point == 8:
        patcher = mock.patch.object(gitcmd, "push", side_effect=Crash("killed"))
    elif point == 9:
        patcher = mock.patch.object(gitcmd, "push", side_effect=_after(gitcmd.push))
    elif point == 10:
        patcher = mock.patch.object(Mutation, "complete", side_effect=Crash("killed"))
    else:  # pragma: no cover - the matrix has ten points
        raise ValueError(point)
    with patcher:
        yield


class MatrixMixin:
    """The checks every point shares; a case provides the target, its bytes, a disposition and the Git view."""

    def own_pending(self) -> list[dict]:
        return [r for r in MutationController(self.store).list_records()
                if r["status"] == "pending" and r["owner"] == rd.OWNER]

    def subjects(self) -> list[str]:
        return [s for s in self.git_text("log", "--format=%s").splitlines() if s.startswith(SUBJECT)]

    def assert_barrier(self) -> None:
        """No other owner begins while the disposition is pending."""
        work = "w_01ARZ3NDEKTSV4RRFFQ69G5FAV"
        with project_operation(self.store, "start", {}), self.assertRaises(ReconcileRequired) as raised:
            MutationController(self.store).open("start", {"operation": "start", "work_id": work, "mode": "single-work"},
                                                WriteScope(entities=(work,), files=LEDGERS))
        self.assertEqual(raised.exception.reason, "recovery_disposition_pending")

    def run_point(self, point: int) -> None:
        target = self.prepare_target()
        before = self.target_bytes(target)
        with interruption(point), self.assertRaises(Crash):
            self.dispose(target)
        # after the interruption: the target untouched, at most one record, no duplicate commit
        self.assertEqual(self.target_bytes(target), before)
        files = self.record_names()
        self.assertLessEqual(len(files), 1)
        self.assertLessEqual(len(self.subjects()), 1)
        pending = self.own_pending()
        self.assertEqual(len(pending), 0 if point == 1 else 1)
        if pending:
            self.assert_barrier()
        self.assert_not_resumed(target)
        decided = None
        if pending and pending[0]["effects"]:
            decided = rd.parse(pending[0]["effects"][0]["payload"]["content"].encode("utf-8"), target)

        if self.stuck(point):
            with self.assertRaises(ReconcileRequired):
                self.dispose(target)
            self.assertEqual(len(self.own_pending()), 1, "the disposition stays pending, holding every owner back")
            self.assert_barrier()
            self.assertEqual(self.subjects(), [SUBJECT + target])
            self.assert_unpublished()
            self.assertEqual(self.target_bytes(target), before)
            return

        result = self.dispose(target)
        self.assertEqual(result.status, "disposed")
        self.assertEqual(result.resumed, point != 1)
        # one record, the same digest and reason; one commit; the target never rewritten nor resumed
        self.assertEqual(self.record_names(), [f"{target}.yaml"])
        found = rd.read_disposition(self.store, target)
        self.assertEqual((found.reason, found.target_state_digest), (REASON, result.target_state_digest))
        if decided is not None:
            self.assertEqual(found, decided)
        self.assertEqual(self.subjects(), [SUBJECT + target])
        self.assertEqual(self.target_bytes(target), before)
        self.assertEqual(self.own_pending(), [])
        self.assert_published()
        self.assert_disposed(target)


class MutationTargetMatrix(MatrixMixin, DispositionCase):
    def prepare_target(self) -> str:
        return self.reconcile_pin()

    def target_bytes(self, target: str) -> bytes:
        return self.runtime(target)

    def record_names(self) -> list[str]:
        return self.record_files()

    def git_text(self, *args: str) -> str:
        from helpers import git

        return git(self.store.root, *args)

    def stuck(self, point: int) -> bool:
        return point == 7

    def assert_not_resumed(self, target: str) -> None:
        state = rd.mutation_target_state(self.store, target)
        active = [r["mutation_id"] for r in MutationController(self.store).list_pending()]
        # active until the disposition is committed, inactive after; never resumed or rewritten either way
        self.assertEqual(target in active, state.state != rd.STATE_EFFECTIVE)

    def assert_published(self) -> None:
        from helpers import git

        self.assertEqual(git(self.remote_path(), "rev-parse", "main").strip(), self.head())
        remote = [s for s in git(self.remote_path(), "log", "--format=%s", "main").splitlines() if s.startswith(SUBJECT)]
        self.assertEqual(len(remote), 1, "published once")

    def assert_unpublished(self) -> None:
        from helpers import git

        found = git(self.remote_path(), "rev-parse", "--verify", "-q", "main", check=False).strip()
        self.assertNotEqual(found, self.head(), "nothing is published without the commit's recorded ID")

    def assert_disposed(self, target: str) -> None:
        self.assertNotIn(target, [r["mutation_id"] for r in MutationController(self.store).list_pending()])
        self.assertEqual(rd.mutation_target_state(self.store, target).state, rd.STATE_EFFECTIVE)


class ReviewTargetMatrix(MatrixMixin, ReviewTargetCase):
    def prepare_target(self) -> str:
        return self.orphan_at_generation_1()

    def dispose(self, target: str, reason: str = REASON):
        return rd.dispose_recovery(self.root, target, reason, confirmed=True)

    def target_bytes(self, target: str) -> dict[str, bytes]:
        return self.review_bytes()

    def record_names(self) -> list[str]:
        directory = self.root / ".workline" / "recovery" / "dispositions"
        return sorted(path.name for path in directory.iterdir()) if directory.exists() else []

    def git_text(self, *args: str) -> str:
        from helpers import git

        return git(self.root, *args)

    def stuck(self, point: int) -> bool:
        return False

    def assert_not_resumed(self, target: str) -> None:
        self.assertEqual(len(ReviewStore(self.store).gate_chain(target).generations), 1)

    def assert_published(self) -> None:
        pass  # remote-less

    def assert_unpublished(self) -> None:
        pass

    def assert_disposed(self, target: str) -> None:
        found = self.discovery()
        self.assertIsNone(found.recoverable)
        self.assertEqual(found.set_aside, ({"review_run_id": target, "reason": "disposed_by_human"},))


def _point(number: int):
    def test(self) -> None:
        self.run_point(number)

    test.__name__ = f"test_point_{number:02d}"
    return test


for _number in range(1, 11):
    setattr(MutationTargetMatrix, f"test_point_{_number:02d}", _point(_number))
for _number in (1, 2, 3, 4, 5, 6, 7, 10):  # 8 and 9 interrupt a push, which a remote-less Project has none of
    setattr(ReviewTargetMatrix, f"test_point_{_number:02d}", _point(_number))
