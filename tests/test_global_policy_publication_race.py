"""P7 §31.56 / §31.39 / §16.21: the root publication race - exact commits only, never a rebase, never twice.

Every row runs a real Global Policy Change against a copied root with a local
bare remote (never a production remote) that logs every ref update it receives.

* remote movement before Kp, and between Kp and Km: no push, reconcile; the
  local commits are never rebased, cherry-picked or reset, and a retry of the
  same request is refused the same way;
* an unreadable destination, a changed push locator, a locator Git does not
  read as itself: nothing is pushed;
* the exact Kp / Km SHA is published, never the branch tip;
* no fetch moves a local ref (objects only, no ``FETCH_HEAD``);
* an already-published Kp (the push landed, its fact was not recorded) is
  recovered without a second push; a refused push is retried by the same
  request and publishes each commit once.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from global_policy_helpers import (
    BRANCH, KM_SUBJECT, KP_SUBJECT, REFUSE_FLAG, Crash, GlobalPolicyCase, crash_at, owner,
)
from helpers import git
from workline import gitcmd


class PublicationRaceTests(GlobalPolicyCase):
    remote = True

    # fixtures ------------------------------------------------------------------
    def other_clone_pushes(self, name: str = "other") -> str:
        """Another clone moves the remote ``main`` past whatever it holds; returns the new remote tip."""
        assert self.bare is not None
        other = self.tmp / name
        git(self.tmp, "clone", "-q", str(self.bare), str(other))
        git(other, "config", "user.name", "someone-else")
        git(other, "config", "user.email", "else@example.invalid")
        (other / f"{name}.txt").write_text("another clone's work\n", encoding="utf-8")
        git(other, "add", f"{name}.txt")
        git(other, "commit", "-q", "-m", "another clone's commit")
        git(other, "push", "-q", "origin", "main")
        return git(other, "rev-parse", "HEAD").strip()

    def local_refs(self) -> dict[str, str]:
        listed = self.git("for-each-ref", "--format=%(refname) %(objectname)")
        return dict(line.split(" ", 1) for line in listed.splitlines() if line)

    def assertNothingRebased(self, kp: str, moved: str) -> None:
        """The local branch still holds the owner's own commit exactly where it made it, and never the move."""
        self.assertEqual([kp], self.commits_with(KP_SUBJECT))
        self.assertEqual("0", git(self.root, "rev-list", "--count", "--merges", "HEAD").strip())
        holds = subprocess.run(["git", "-C", str(self.root), "merge-base", "--is-ancestor", moved, "HEAD"],
                               capture_output=True).returncode
        self.assertNotEqual(0, holds, "the remote's move is never merged, rebased onto or cherry-picked into the branch")
        self.assertFalse(any(self.subject(commit) == "another clone's commit"
                             for commit in self.git("rev-list", "HEAD").split()))

    # remote movement -----------------------------------------------------------
    def test_remote_movement_before_kp_is_reconcile_and_nothing_is_pushed(self) -> None:
        gp = owner()
        moved = self.other_clone_pushes()
        refs = self.local_refs()
        self.stops("", self.change, reason=gp.REASON_PUBLICATION_INVALID)
        self.assertEqual(moved, self.remote_tip())
        self.assertEqual([moved], [line.split()[1] for line in self.remote_log()])
        (kp,) = self.commits_with(KP_SUBJECT)
        self.assertNothingRebased(kp, moved)
        self.assertEqual({key: value for key, value in refs.items() if key != BRANCH},
                         {key: value for key, value in self.local_refs().items() if key != BRANCH},
                         "no fetch moves a local ref")
        self.assertFalse((self.root / ".git" / "FETCH_HEAD").exists())
        # the same request is refused the same way, and still pushes nothing
        self.stops("", self.change, reason=gp.REASON_PUBLICATION_INVALID)
        self.assertEqual(moved, self.remote_tip())
        self.assertEqual([kp], self.commits_with(KP_SUBJECT))
        self.assertEqual([], self.commits_with(KM_SUBJECT), "no Consumption is made on an unpublished Kp")

    def test_remote_movement_between_kp_and_km_publishes_no_km(self) -> None:
        gp = owner()
        with crash_at(gp, "_consumption_bytes"):
            with self.assertRaises(Crash):
                self.change()
        (kp,) = self.commits_with(KP_SUBJECT)
        self.assertEqual(kp, self.remote_tip(), "Kp was published before the Consumption was decided")
        moved = self.other_clone_pushes()
        self.stops("", self.change, reason=gp.REASON_PUBLICATION_INVALID)
        self.assertEqual(moved, self.remote_tip())
        (km,) = self.commits_with(KM_SUBJECT)
        self.assertEqual([kp], self.parents(km), "Km is made exactly on Kp and never moved onto the remote tip")
        self.assertNothingRebased(kp, moved)
        self.assertNotIn(km, [line.split()[1] for line in self.remote_log()])

    # unreadable / changed / rewritten destinations -------------------------------
    def test_an_unreadable_destination_pushes_nothing(self) -> None:
        assert self.bare is not None
        gp = owner()
        with crash_at(gp, "_publish"):
            with self.assertRaises(Crash):
                self.change()
        hidden = self.bare.with_name(self.bare.name + "-hidden")
        os.replace(self.bare, hidden)
        try:
            with self.assertRaises(Exception):
                self.change()
        finally:
            os.replace(hidden, self.bare)
        self.assertEqual([], self.remote_log())
        self.assertEqual(1, len(self.pending_records()), "the mutation waits for its exact publication")
        result = self.applied()  # once the destination reads again, the same request publishes exactly
        self.assertEqual(result.metadata_commit, self.remote_tip())

    def test_a_changed_push_locator_is_refused_before_anything_is_pushed(self) -> None:
        gp = owner()
        with crash_at(gp, "_publish"):
            with self.assertRaises(Crash):
                self.change()
        elsewhere = self.tmp / "elsewhere.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(elsewhere))
        self.git("remote", "set-url", "--push", "origin", str(elsewhere))
        self.stops("review_p7_authorization_mismatch", self.change)
        self.assertEqual([], self.remote_log())
        self.assertEqual("", git(elsewhere, "for-each-ref").strip(), "nothing reaches the other locator")

    def test_a_locator_git_does_not_read_as_itself_is_not_read_or_pushed(self) -> None:
        assert self.bare is not None
        gp = owner()
        decoy = self.tmp / "decoy.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(decoy))
        alias = "workline-test-alias:root"
        # the push still resolves to the authorized locator; a READ of that locator would reach the decoy
        self.git("remote", "set-url", "origin", alias)
        self.git("config", f"url.{self.bare}.pushInsteadOf", alias)
        self.git("config", f"url.{decoy}.insteadOf", str(self.bare))
        self.assertEqual(str(self.bare), gitcmd.push_locators(self.root, "origin")[0])
        self.stops("", self.change, reason=gp.REASON_PUBLICATION_INVALID)
        self.assertEqual([], self.remote_log())
        self.assertEqual("", git(decoy, "for-each-ref").strip())

    # exactness and duplicates ----------------------------------------------------
    def test_the_exact_commits_are_published_never_the_branch_tip(self) -> None:
        pushed: list[str] = []
        real = gitcmd.push

        def push(repo: Path, remote: str, refspec: str):
            pushed.append(refspec)
            return real(repo, remote, refspec)

        with mock.patch.object(gitcmd, "push", push):
            result = self.applied()
        self.assertEqual([f"{result.policy_commit}:{BRANCH}", f"{result.metadata_commit}:{BRANCH}"], pushed)
        for refspec in pushed:
            self.assertFalse(refspec.startswith("+"))
            self.assertNotIn("HEAD", refspec)

    def test_an_already_published_kp_is_recovered_without_a_second_push(self) -> None:
        start = self.remote_tip()
        with crash_at(gitcmd, "push", after=True):
            with self.assertRaises(Crash):
                self.change()
        (kp,) = self.commits_with(KP_SUBJECT)
        self.assertEqual([f"{start} {kp} {BRANCH}"], self.remote_log())
        result = self.applied()
        self.assertEqual(kp, result.policy_commit)
        self.assertEqual([f"{start} {kp} {BRANCH}", f"{kp} {result.metadata_commit} {BRANCH}"], self.remote_log())

    def test_a_refused_push_is_retried_by_the_same_request_and_lands_once(self) -> None:
        assert self.bare is not None
        start = self.remote_tip()
        flag = self.bare / REFUSE_FLAG
        flag.write_text("refuse\n", encoding="utf-8")
        with self.assertRaises(Exception):
            self.change()
        self.assertEqual(start, self.remote_tip())
        flag.unlink()
        result = self.applied()
        self.assertEqual([f"{start} {result.policy_commit} {BRANCH}",
                          f"{result.policy_commit} {result.metadata_commit} {BRANCH}"], self.remote_log())

    def test_a_destination_already_past_the_commit_is_published_already(self) -> None:
        """The destination moved on past Kp (it holds Kp): Kp is published, and nothing is pushed for it again."""
        gp = owner()
        with crash_at(gitcmd, "push", after=True):
            with self.assertRaises(Crash):
                self.change()
        (kp,) = self.commits_with(KP_SUBJECT)
        moved = self.other_clone_pushes()  # on top of Kp
        self.stops("", self.change, reason=gp.REASON_PUBLICATION_INVALID)  # Km is not a fast-forward of the move
        lines = self.remote_log()
        self.assertEqual(2, len(lines))
        self.assertEqual([kp, moved], [line.split()[1] for line in lines])
        self.assertTrue(any(record["effects"] for record in self.pending_records()))


if __name__ == "__main__":
    unittest.main()
