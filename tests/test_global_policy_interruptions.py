"""P7 §31.58 (all 23 points) + RB7C-2: root runtime-loss recovery and resume, through the shared discovery core.

For every interruption point the change is killed there (:class:`Crash`, a
simulated process death nothing catches) and the same request is run again:

* **resume** - the runtime survived: the same request finishes, with the same
  Packet, change, Run and task identities, and nothing is duplicated (one
  Packet, one Run, one change record, one Patch Note, one policy version, one
  Consumption, one Kp, one Km, each publication once);
* **runtime loss** - ``.workline-root-runtime/`` deleted whole: before anything
  canonical the request is a new Candidate; with root Review records committed
  it REDISCOVERS the same Run through ``recovery.discover_kind_in`` and rebinds
  its canonical IDs (§31.11); uncommitted owned writes are owned-path dirt that
  stops before anything (no adoption by guess); a committed change record
  without its Consumption is ``review_p7_run_unrecovered`` - a Kp is never
  inferred from Git history (CP_EARLY L35); a completed change is never applied
  again.

Plus the window between a commit's ``update-ref`` and its ``ref_moved`` fact for
Kp and Km, with and without a remote (RB7DL-3, Amendment 10 item 1), the R8 root
analogue (a G4 HUMAN_WAIT Run stays the same canonical Run through runtime loss,
with no set-aside, Receipt, Kp or Consumption, stably), a blocking G4 that stays
terminal, the static "one discovery core" check, and the strong form "no
``<root>/.workline`` at any point".
"""

from __future__ import annotations

import ast
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Callable, Iterator
import unittest
from unittest import mock

from global_policy_helpers import (
    KG_SUBJECT, KM_SUBJECT, KP_SUBJECT, Crash, Discovery, GlobalPolicyCase, authorize, claim, crash_at,
    discovery_actors, maintenance, owner, root_review,
)
from helpers import SRC
from workline import gitcmd
from workline.review import workcommit

OWNER_TEXT = (SRC / "workline" / "global_policy.py").read_text(encoding="utf-8")
MAINTENANCE_SOURCE = SRC / "workline" / "root_maintenance.py"

RESUMED = "resumed"
FRESH = "fresh"            # nothing canonical: a new Candidate (new IDs are fine), applied
REDISCOVERED = "rediscovered"  # the same Run found canonically, its IDs rebound, applied
DIRTY = "dirty"            # uncommitted owned writes: dirty_overlap before anything
UNRECOVERED = "unrecovered"  # a committed change without its Consumption: review_p7_run_unrecovered
SETTLED = "settled"        # the change is complete: nothing is applied again


# --------------------------------------------------------------------------- crash predicates

def _mutation() -> Any:
    return maintenance().RootMutation


def _nth_ref_moved(nth: int) -> Callable[..., bool]:
    seen = {"n": 0}

    def when(_n: int, _mutation: Any, _index: int, facts: Any) -> bool:
        if facts.get("ref_moved") is True:
            seen["n"] += 1
            return seen["n"] == nth
        return False

    return when


def _prepared(stage: str) -> Callable[..., bool]:
    def when(_n: int, mutation: Any, index: int, facts: Any) -> bool:
        return facts.get("ref_moved") is False and mutation.effects()[index]["payload"]["stage"] == stage

    return when


def _planning(stage: str) -> Callable[..., bool]:
    return lambda _n, _op, _mutation, found, *_rest: found == stage


def _applying(kind: Callable[[], str]) -> Callable[..., bool]:
    return lambda _n, mutation, index: mutation.effects()[index]["kind"] == kind()


def _adding_push(stage: str) -> Callable[..., bool]:
    return lambda _n, _mutation, kind, payload: kind == maintenance().EFFECT_PUSH and payload["stage"] == stage


def _nth(nth: int) -> Callable[..., bool]:
    return lambda n, *_args, **_kwargs: n == nth


@dataclass(frozen=True)
class Point:
    number: int
    name: str
    crash: Callable[[], Any]       # a context manager factory that kills the first matching call
    after_loss: str                # what the same request meets after runtime loss
    remote: bool = False


POINTS = (
    Point(1, "lock acquisition", lambda: crash_at(maintenance(), "enter_git"), FRESH),
    Point(2, "root mutation allocation", lambda: crash_at(maintenance(), "open_mutation", after=True), FRESH),
    Point(3, "packet and change id reservations",
          lambda: crash_at(_mutation(), "reserve_id", after=True, when=lambda _n, _m, _key, kind: kind == "review_run"),
          FRESH),
    Point(4, "g1 effects before commit", lambda: crash_at(workcommit, "build", when=_nth(1)), DIRTY),
    Point(5, "kg1", lambda: crash_at(_mutation(), "mark_effect", after=True, when=_nth_ref_moved(1)), REDISCOVERED),
    Point(6, "discovery return before g2", lambda: crash_at(owner(), "_plan_stage", when=_planning("kg2")),
          REDISCOVERED),
    Point(7, "kg2", lambda: crash_at(_mutation(), "mark_effect", after=True, when=_nth_ref_moved(2)), REDISCOVERED),
    Point(8, "g3", lambda: crash_at(owner(), "_plan_stage", after=True, when=_planning("kg3")), REDISCOVERED),
    Point(9, "adjudicator return before g4", lambda: crash_at(owner(), "_plan_stage", when=_planning("kg4")),
          REDISCOVERED),
    Point(10, "kg4", lambda: crash_at(_mutation(), "mark_effect", after=True, when=_nth_ref_moved(4)), REDISCOVERED),
    Point(11, "g5 receipt", lambda: crash_at(owner(), "_plan_stage", after=True, when=_planning("kg5")), REDISCOVERED),
    Point(12, "kg5", lambda: crash_at(_mutation(), "mark_effect", after=True, when=_nth_ref_moved(5)), REDISCOVERED),
    Point(13, "policy change and note effects", lambda: crash_at(owner(), "_plan_stage", after=True,
                                                                  when=_planning("kp")), REDISCOVERED),
    Point(14, "partial kp file apply",
          lambda: crash_at(_mutation(), "apply_effect", after=True,
                           when=_applying(lambda: maintenance().EFFECT_CHANGE_CREATE)), DIRTY),
    Point(15, "kp commit", lambda: crash_at(_mutation(), "mark_effect", after=True, when=_prepared("kp")), DIRTY),
    Point(16, "c2 kp", lambda: crash_at(owner(), "_c2_kp", when=_nth(1)), UNRECOVERED),
    Point(17, "kp publication record", lambda: crash_at(_mutation(), "add_effect", after=True,
                                                         when=_adding_push("kp")), UNRECOVERED, remote=True),
    Point(18, "kp already remote visible", lambda: crash_at(gitcmd, "push", after=True, when=_nth(1)), UNRECOVERED,
          remote=True),
    Point(19, "consumption", lambda: crash_at(owner(), "_plan_stage", after=True, when=_planning("km")), UNRECOVERED),
    Point(20, "km commit", lambda: crash_at(_mutation(), "mark_effect", after=True, when=_prepared("km")), DIRTY),
    Point(21, "c2 km", lambda: crash_at(owner(), "_c2_km", when=_nth(1)), SETTLED),
    Point(22, "km publication", lambda: crash_at(gitcmd, "push", after=True, when=_nth(2)), SETTLED, remote=True),
    Point(23, "completion", lambda: crash_at(_mutation(), "complete"), SETTLED),
)

#: RB7DL-3 (Amendment 8 / Amendment 10 item 1): the crash lands BETWEEN the ``update-ref`` compare-and-swap and the
#: ``ref_moved`` fact - the branch names the durably prepared commit and its move is not recorded. ``after=False`` on
#: the ref_moved mark of Kp (the 6th commit: Kg1-Kg5, Kp) and of Km (the 7th), remote-less and with a remote. The
#: resume admits exactly that prepared commit (its object proven) and finishes; after runtime loss Kp's window is the
#: reconciliation boundary (its identity was never saved anywhere that survived) and Km's a completed change.
CAS_WINDOW_POINTS = (
    Point(15, "kp ref moved before its fact", lambda: crash_at(_mutation(), "mark_effect", when=_nth_ref_moved(6)),
          UNRECOVERED),
    Point(20, "km ref moved before its fact", lambda: crash_at(_mutation(), "mark_effect", when=_nth_ref_moved(7)),
          SETTLED),
    Point(15, "kp ref moved before its fact", lambda: crash_at(_mutation(), "mark_effect", when=_nth_ref_moved(6)),
          UNRECOVERED, remote=True),
    Point(20, "km ref moved before its fact", lambda: crash_at(_mutation(), "mark_effect", when=_nth_ref_moved(7)),
          SETTLED, remote=True),
)


# --------------------------------------------------------------------------- the strong form: no .workline, ever

@contextmanager
def no_project_namespace(root: Path) -> Iterator[list[str]]:
    """Fail the test if anything creates a directory named ``.workline`` while the block runs (any path, any dir_fd)."""
    made: list[str] = []
    real_mkdir = os.mkdir

    def mkdir(path: Any, *args: Any, **kwargs: Any) -> None:
        if Path(os.fsdecode(path)).name == ".workline":
            made.append(os.fsdecode(path))
        return real_mkdir(path, *args, **kwargs)

    with mock.patch.object(os, "mkdir", mkdir):
        yield made
    if made or os.path.lexists(root / ".workline"):
        raise AssertionError(f"a .workline directory was created: {made}")


class InterruptionCase(GlobalPolicyCase):
    def reserved(self) -> dict[str, str]:
        """The reservations of the one pending root mutation (empty when there is none)."""
        pending = self.pending_records()
        return dict(pending[0]["reserved_ids"]) if pending else {}

    def interrupted(self, point: Point) -> dict[str, str]:
        with no_project_namespace(self.root), point.crash():
            with self.assertRaises(Crash):
                self.change()
        return self.reserved()

    def assertSingleApplied(self, result: Any) -> None:
        self.assertEqual(owner().STATUS_APPLIED, result.status, result.detail)
        self.assertEqual(1, len(self.tracked("review-policy/promotion-packets/")))
        self.assertEqual([result.review_run_id], self.run_ids())
        self.assertEqual([f"review-policy/changes/{result.global_policy_change_id}.yaml"],
                         self.tracked("review-policy/changes/"))
        self.assertEqual([f"review-policy/patch-notes/{result.global_policy_change_id}.md"],
                         self.tracked("review-policy/patch-notes/"))
        self.assertEqual([f"review-policy/review/consumptions/{result.consumption_id}.yaml"],
                         self.tracked("review-policy/review/consumptions/"))
        self.assertEqual(1, len(self.tracked("review-policy/review/receipts/")))
        self.assertEqual(5, len(self.commits_with(KG_SUBJECT)))
        self.assertEqual([result.policy_commit], self.commits_with(KP_SUBJECT))
        self.assertEqual([result.metadata_commit], self.commits_with(KM_SUBJECT))
        self.assertEqual(2, self.policy_record()["global_policy_version"])
        self.assertEqual([], self.pending_records())
        self.assertNoProjectNamespace()
        if self.bare is not None:
            self.assertEqual(2, len(self.remote_log()), "each of Kp and Km is published exactly once")
            self.assertEqual(result.metadata_commit, self.remote_tip())

    def assertSameIdentities(self, before: dict[str, str], result: Any) -> None:
        gp = owner()
        found = {result.promotion_packet_id, result.global_policy_change_id, result.review_run_id}
        for key, value in before.items():
            if key in (gp.PACKET_KEY, gp.CHANGE_KEY) or key.startswith("review-run:"):
                with self.subTest(key=key):
                    self.assertIn(value, found, "a recovered canonical ID is rebound, never reallocated")
        self.assertTrue(gp)

    # the two halves of every point -------------------------------------------------
    def resume_point(self, point: Point) -> None:
        before = self.interrupted(point)
        with no_project_namespace(self.root):
            result = self.change()
        self.assertSingleApplied(result)
        self.assertSameIdentities(before, result)

    def cas_window_resume(self, point: Point) -> None:
        """The crash left the branch AT the prepared commit with its move unrecorded; the resume adopts exactly it."""
        before = self.interrupted(point)
        (pending,) = self.pending_records()
        stage = "kp" if "kp" in point.name else "km"
        (commit,) = [effect for effect in pending["effects"]
                     if effect["kind"] == maintenance().EFFECT_COMMIT and effect["payload"]["stage"] == stage]
        self.assertIs(False, commit["facts"]["ref_moved"], "the move is not recorded")
        self.assertEqual(commit["facts"]["prepared_commit"], self.head(), "the branch already names the prepared commit")
        with no_project_namespace(self.root):
            result = self.change()
        self.assertSingleApplied(result)
        self.assertSameIdentities(before, result)
        made = result.policy_commit if stage == "kp" else result.metadata_commit
        self.assertEqual(commit["facts"]["prepared_commit"], made, "the very prepared commit, never a rebuilt one")

    def loss_point(self, point: Point) -> None:
        before = self.interrupted(point)
        runs = self.run_ids()
        head = self.head()
        self.drop_runtime()
        if self.bare is not None:
            # the authorization lives in the runtime too: after its loss a Human approves the publication again
            authorize(self.root)
        gp = owner()
        with no_project_namespace(self.root):
            if point.after_loss in (FRESH, REDISCOVERED):
                result = self.change()
                self.assertSingleApplied(result)
                if point.after_loss == REDISCOVERED:
                    self.assertEqual(runs, [result.review_run_id], "the same canonical Run is rediscovered")
                    self.assertSameIdentities(before, result)
            elif point.after_loss == DIRTY:
                self.stops("dirty_overlap", self.change)
                self.assertEqual(head, self.head())
                self.assertEqual([], self.pending_records())
            elif point.after_loss == UNRECOVERED:
                self.stops("", self.change, reason=gp.REASON_RUN_UNRECOVERED)
                self.assertEqual(head, self.head())
                self.assertEqual([], self.pending_records())
                self.assertEqual(1, len(self.commits_with(KP_SUBJECT)), "no Kp is made again or adopted")
            else:
                with self.assertRaises(Exception):
                    self.change()
                self.assertEqual(head, self.head())
                self.assertEqual(runs, self.run_ids(), "a completed change is never reviewed again")
                self.assertEqual(1, len(self.tracked("review-policy/promotion-packets/")))
                self.assertEqual(2, self.policy_record()["global_policy_version"], "no second policy version")
        self.assertNoProjectNamespace()


def _slug(point: Point) -> str:
    return f"{point.number:02d}_" + point.name.replace(" ", "_").replace("-", "_")


class LocalInterruptionTests(InterruptionCase):
    """Every remote-less §31.58 point, resumed and after runtime loss."""


class RemoteInterruptionTests(InterruptionCase):
    """The publication points (17, 18, 22) and a remote completion, resumed and after runtime loss."""

    remote = True


def _install() -> None:
    for point in POINTS:
        target = RemoteInterruptionTests if point.remote else LocalInterruptionTests
        setattr(target, f"test_{_slug(point)}_resumes", lambda self, p=point: self.resume_point(p))
        setattr(target, f"test_{_slug(point)}_after_runtime_loss", lambda self, p=point: self.loss_point(p))
    for point in CAS_WINDOW_POINTS:
        target = RemoteInterruptionTests if point.remote else LocalInterruptionTests
        setattr(target, f"test_{_slug(point)}_resumes", lambda self, p=point: self.cas_window_resume(p))
        setattr(target, f"test_{_slug(point)}_after_runtime_loss", lambda self, p=point: self.loss_point(p))
    completion = POINTS[-1]
    setattr(RemoteInterruptionTests, "test_23_completion_with_a_remote_resumes",
            lambda self: self.resume_point(completion))


_install()


class AllPointsTests(unittest.TestCase):
    def test_the_matrix_names_all_23_points_once(self) -> None:
        self.assertEqual(list(range(1, 24)), [point.number for point in POINTS])

    def test_the_cas_window_is_covered_for_kp_and_km_with_and_without_a_remote(self) -> None:
        self.assertEqual({(15, False), (15, True), (20, False), (20, True)},
                         {(point.number, point.remote) for point in CAS_WINDOW_POINTS})
        self.assertEqual({(15, UNRECOVERED), (20, SETTLED)}, {(point.number, point.after_loss) for point in
                                                              CAS_WINDOW_POINTS})
        for point in CAS_WINDOW_POINTS:
            with self.subTest(point=_slug(point), remote=point.remote):
                for name in (f"test_{_slug(point)}_resumes", f"test_{_slug(point)}_after_runtime_loss"):
                    target = RemoteInterruptionTests if point.remote else LocalInterruptionTests
                    self.assertTrue(callable(getattr(target, name, None)))


# --------------------------------------------------------------------------- R8: the root HUMAN_WAIT analogue

class HumanWaitTests(InterruptionCase):
    def human_review(self) -> Any:
        return root_review(*discovery_actors(2, claim("human", "MID", "a requirement decision is needed")))

    def test_a_g4_human_wait_run_survives_runtime_loss_as_the_same_run(self) -> None:
        gp = owner()
        review = self.human_review()
        first = self.change(review=review)
        self.assertEqual(gp.STATUS_HUMAN_WAIT, first.status, first.detail)
        self.assertIsNone(first.receipt_id)
        runs = self.run_ids()
        self.assertEqual([first.review_run_id], runs)
        head = self.head()
        for attempt in range(3):
            with self.subTest(attempt=attempt):
                self.drop_runtime()
                again = self.change(review=self.human_review())
                self.assertEqual(gp.STATUS_HUMAN_WAIT, again.status)
                self.assertEqual((first.review_run_id, first.global_policy_change_id, first.promotion_packet_id),
                                 (again.review_run_id, again.global_policy_change_id, again.promotion_packet_id))
                self.assertEqual(runs, self.run_ids(), "no new Run")
                self.assertEqual(head, self.head(), "nothing is committed for a waiting Run")
        self.assertEqual([], self.tracked("review-policy/review/receipts/"))
        self.assertEqual([], self.tracked("review-policy/review/supersessions/"), "nothing is set aside")
        self.assertEqual([], self.tracked("review-policy/review/consumptions/"))
        self.assertEqual([], self.tracked("review-policy/changes/"))
        self.assertEqual([], self.commits_with(KP_SUBJECT))
        self.assertEqual(1, self.policy_record()["global_policy_version"])
        self.assertNoProjectNamespace()

    def test_the_waiting_run_is_rediscovered_without_judging_the_invocations_actors(self) -> None:
        gp = owner()
        first = self.change(review=self.human_review())
        self.assertEqual(gp.STATUS_HUMAN_WAIT, first.status)
        self.drop_runtime()
        lone = Discovery(identity="someone-else")
        again = self.change(review=root_review(lone))  # below the floor: a waiting Run launches nothing
        self.assertEqual((gp.STATUS_HUMAN_WAIT, first.review_run_id), (again.status, again.review_run_id))
        self.assertEqual([], lone.tasks)


class BlockingG4Tests(InterruptionCase):
    def test_a_blocking_g4_stays_terminal_and_a_retry_is_a_new_run(self) -> None:
        gp = owner()
        blocking = root_review(*discovery_actors(2, claim("problem")))
        first = self.change(review=blocking)
        self.assertEqual(gp.STATUS_NOT_AUTHORIZED, first.status, first.detail)
        self.assertTrue(any(item["blocking"] for item in first.findings))
        self.drop_runtime()
        second = self.change(review=root_review(*discovery_actors(2, claim("problem"))))
        self.assertEqual(gp.STATUS_NOT_AUTHORIZED, second.status)
        self.assertNotEqual(first.review_run_id, second.review_run_id, "a terminal Run is never resumed")
        self.assertEqual(sorted([first.review_run_id, second.review_run_id]), self.run_ids())
        self.assertEqual([], self.tracked("review-policy/review/receipts/"))
        self.assertEqual([], self.tracked("review-policy/review/repair-batches/"), "no Repair Batch for the root")
        self.assertEqual(1, self.policy_record()["global_policy_version"])


# --------------------------------------------------------------------------- one discovery core (static)

class OneDiscoveryCoreTests(unittest.TestCase):
    """RB7C-2: the root has no Gate-chain or matching-run walk of its own; recovery is the shared core."""

    WALKS = ("_matching_runs", ".run_ids(", "GATES_DIR", "gates_dir", "generation_of_name", "discover_kind(",
             "_clean_run", "_clean_p4_run", "p4_record_paths")

    def test_the_owner_calls_the_shared_root_entry_once_and_walks_nothing_itself(self) -> None:
        self.assertEqual(1, OWNER_TEXT.count("review_recovery.discover_kind_in("))
        for walk in self.WALKS:
            with self.subTest(walk=walk):
                self.assertNotIn(walk, OWNER_TEXT)
        tree = ast.parse(OWNER_TEXT)
        loops_over_chains = [node for node in ast.walk(tree) if isinstance(node, (ast.For, ast.comprehension))
                             and "gate_chain" in ast.unparse(node.iter)]
        self.assertEqual([], loops_over_chains)

    def test_root_maintenance_discovers_nothing(self) -> None:
        text = MAINTENANCE_SOURCE.read_text(encoding="utf-8")
        for walk in self.WALKS + ("discover_kind_in(", "gate_chain("):
            with self.subTest(walk=walk):
                self.assertNotIn(walk, text)


if __name__ == "__main__":
    unittest.main()
