"""A cycle continues past a registration another subject committed before its Git stage was recorded (BL-054).

A derivation's registration is finalized by a Git stage of this mutation's own,
and a resume shows the record holds exactly that one Git stage between two
derivations (``_derivations_to_reuse``). It holds none at all when, while the
START is interrupted between applying that registration and recording its Git
stage, another subject commits the working tree - a person meaning to commit
their own work with ``git add -A && git commit`` takes the operation's
uncommitted registration along. The resume then finds those paths no longer
different from HEAD, so ``_Session._commit`` records no stage, and the record
ends up holding two derivations side by side.

Before this change every later resume of that record was ``reconcile required``
for its shape, on every retry, and no Git action the person could take changed
it: undoing or discarding their commit does not put a stage back into a record.
Every other operation of that Project stopped on the pending mutation, and
``validate_project`` showed nothing. Recovery needed the record edited by hand.

A missing Git stage is not read as a commit. Nothing is adopted, nothing is
identified, no commit ID is written and no push can publish by it (BL-050). What
is shown instead is the thing that Git stage was there to establish, and only
that: the stage is made of nothing but a registration's own effects, every one
of them is applied, the branch it was decided on already holds - committed -
exactly the bytes this mutation wrote for each whole file and each relation it
added under the ID reserved for it, and the stage is the registration that
derivation decided, compared exactly as the replay compares it. Anything short
of that refuses exactly as it did before.

This is not BL-053, which stops a Git stage this mutation never made from being
recorded at all - there the record holds one stage too many, here none at all.
It is not BL-052 either, which passes over at most one legitimate Git stage of
its own between a move's registration and the removal of the target: that bound
is unchanged, and "none" is allowed only on the proof below, never by widening a
count. And it is not the commit-after-crash SAFE_STOP of ``rules/git``, where
the Git stage *is* recorded and the person's own recovery works.
"""

from __future__ import annotations

import unittest

from helpers import git
from test_current_cycle_dependency_resume import EVENT_LOG, ROADMAP_YAML, CycleCase
from test_recorded_move_dependency import Interrupted, after_recording, before_recording
from workline import start as st
from workline import yamlish
from workline.errors import ReconcileRequired, StopError
from workline.ids import new_id
from workline.mutation import MutationController
from workline.state import ProjectView

#: What a record whose derivations are not separated by the commit that carries one says.
SHAPE = "and the derivation after it, where a derivation records only the commit that carries it"
#: What a commit refused for bytes it cannot account for says (BL-043 / BL-053).
REFUSED = "cannot show the change it would commit is its own"
#: A person's line in the relation ledger: legal YAML, and no relation of theirs.
NOTE = b"# person's note\n"


def before_the_registration_is_committed():
    """Stop with the first derivation's registration applied and its Git stage about to be recorded."""
    return before_recording(r"^commit:0$")


def after_the_second_registration(work_id: str):
    """Stop right after the second derivation's registration stage is recorded."""
    return before_recording(rf"^commit:\d+$|^{work_id}:lifecycle:1$")


class MissingStageCase(CycleCase):
    """W1 derives twice in one cycle, and a person commits the working tree after the first registration."""

    #: Each derivation makes W1 wait for what it derived; the twin cases override this to derive without one.
    self_dependency = True
    #: Whether the cycle's second derivation removes W1's target.
    moves = False

    # the cycle ---------------------------------------------------------------
    def first(self) -> st.Derive:
        return self.waits("fix1") if self.self_dependency else self.waits(others=("fix1",))

    def second(self) -> st.Derive:
        if self.self_dependency:
            return self.waits("fix2", move=self.moves)
        return self.waits(others=("fix2",), move=self.moves)

    def asking(self) -> dict:
        """What the cycle decides: two derivations, and - where the second keeps the target - a question after them."""
        script = {("W1", 1): self.first(), ("W1", 2): self.second()}
        if not self.moves:
            script[("W1", 3)] = st.QuestionWait("which way?")
        return script

    def answering(self) -> dict:
        return {("W1", 3): st.Hold("done deriving")}

    def whole(self) -> dict:
        """The same cycle with nothing interrupted and no question: what the twin runs."""
        script = {("W1", 1): self.first(), ("W1", 2): self.second()}
        if not self.moves:
            script[("W1", 3)] = st.Hold("done deriving")
        return script

    # the person ---------------------------------------------------------------
    def person_commits(self, message: str = "person: my own work") -> str:
        """The person commits the working tree, taking the operation's uncommitted registration along."""
        git(self.root, "add", "-A")
        git(self.root, "-c", "user.name=person", "-c", "user.email=p@example.invalid", "commit", "-m", message)
        return self.head()

    def person_commits_the_works_only(self, message: str = "person: only the new files") -> str:
        """The person commits the files the registration wrote whole, leaving the relation ledger out."""
        (pending,) = self.pending()
        written = sorted({e["payload"]["path"] for e in pending["effects"] if e["kind"] == "write_file"})
        git(self.root, "add", "--", *written)
        git(self.root, "-c", "user.name=person", "-c", "user.email=p@example.invalid", "commit", "-m", message)
        return self.head()

    # the record BL-054 is about ------------------------------------------------
    def interrupted(self) -> None:
        """Stop with the first registration applied and its Git stage not recorded."""
        with before_the_registration_is_committed(), self.assertRaises(Interrupted):
            self.starting(self.asking())()

    def swept(self) -> str:
        """The record this closes: the first registration committed by another subject, with no Git stage of its own.

        The cycle runs on to its second derivation, and - where that one keeps
        the target - to the question its next attempt asks, exactly as an
        uninterrupted one does. The person's commit is returned.
        """
        self.interrupted()
        taken = self.person_commits()
        if self.moves:
            # A move ends the cycle, so the record only holds both derivations once the second
            # one is recorded; one more interruption puts the run there.
            with after_the_second_registration(self.w1), self.assertRaises(Interrupted):
                self.starting(self.asking())()
        else:
            asked = self.starting(self.asking())()
            self.assertEqual(asked.status, "question_wait")
        self.assertEqual(self.between(), [])
        return taken

    def between(self) -> list[str]:
        """The stages the record holds between the two registrations of this cycle."""
        names = self.stage_names()
        return names[names.index(f"{self.w1}:derive:0") + 1: names.index(f"{self.w1}:derive:1")]

    def resume(self):
        return self.starting(self.answering() if not self.moves else {})()

    # record surgery ------------------------------------------------------------
    def rewrite_record(self, change) -> None:
        (pending,) = self.pending()
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8")

    def registration_effects(self, record: dict) -> list[dict]:
        return [e for e in record["effects"] if e["stage"] == f"{self.w1}:derive:0"]

    # assertions ----------------------------------------------------------------
    def assertStoppedUnchanged(self, call, message: str = SHAPE) -> StopError:
        """Refused without running the cycle, and without applying anything of it.

        The Project is what it was: no executor asked, no stage recorded, no Work,
        relation or derivation detail written, HEAD and the remote unmoved. The
        Project side is what tells a proof made before anything is replayed from
        one made after: a record shown to be unusable only at the replay has had
        :meth:`Mutation.apply` write its unapplied effects first.
        """
        ran, stages = list(self.ran), self.stage_names()
        head, remote = self.head(), self.remote_head()
        works, relations, details = self.outcome()["works"], self.relations(), self.derivation_files()
        with self.assertRaises(StopError) as refused:
            call()
        self.assertIn(message, str(refused.exception))
        self.assertEqual((self.ran, self.stage_names()), (ran, stages))
        self.assertEqual((self.head(), self.remote_head()), (head, remote))
        self.assertEqual((self.outcome()["works"], self.relations(), self.derivation_files()),
                         (works, relations, details))
        return refused.exception

    def assertConverged(self, result, expected: dict, calls: list[str]) -> None:
        """The cycle ended as the uninterrupted one does: same canonical state, same executor calls, nothing pending."""
        self.assertEqual(result.status, "moved" if self.moves else "held")
        self.assertEqual(self.ran, calls)
        self.assertEqual(len(self.named("Fix1")), 1)
        self.assertEqual(len(self.named("Fix2")), 1)
        self.assertEqual(self.derivation_files(), 2)
        self.assertEqual(self.pending(), [])
        self.assertEqual(validate_problems(self.store), 0)
        self.assertEqual(self.settled(self.outcome()), self.settled(expected))


def validate_problems(store) -> int:
    from workline.validate import validate_project

    return len(validate_project(store))


# --------------------------------------------------------------------------- A / B: the exact bug
class RemoteTests(MissingStageCase):
    remote = True

    def test_the_cycle_continues_after_a_person_committed_its_first_registration(self) -> None:
        """A: one interruption, one ordinary human commit, one question wait - and the answer finishes the cycle."""
        expected = self.twin(lambda: self.whole())
        self.setUp()
        self.swept()

        result = self.resume()

        self.assertConverged(result, expected, ["W1#1", "W1#2", "W1#3", "W1#3"])

    def test_every_retry_of_that_record_behaves_the_same(self) -> None:
        """A: the refusal it used to give was permanent; what replaces it is not a one-off either."""
        self.swept()
        self.assertEqual(self.resume().status, "held")
        self.assertEqual(self.pending(), [])

    def test_nothing_of_the_cycle_is_decided_or_registered_twice(self) -> None:
        """A: the executor is asked for the attempts an uninterrupted run asks, and for no others."""
        self.swept()

        self.resume()

        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#3", "W1#3"])
        self.assertEqual([len(self.named(name)) for name in ("Fix1", "Fix2")], [1, 1])
        self.assertEqual(self.events(self.w1).count("work_started"), 1)
        self.assertEqual(self.events(self.w1).count("work_target_added"), 1)
        self.assertEqual(self.derivation_files(), 2)
        self.assertEqual(len([r for r in self.relations() if r[1] == "W1" and r[0] == "derived"]), 2)


class RemotelessTests(RemoteTests):
    """B: the same meaning where the Project has no remote."""

    remote = False


# --------------------------------------------------------------------------- C / D: the cycle's own dependency
class NoSelfDependencyTests(RemoteTests):
    """D: the derivations do not make W1 wait for what they derived, so no dependency is left out (BL-051)."""

    self_dependency = False


# --------------------------------------------------------------------------- E / F: what the second derivation is
class MovingSecondTests(MissingStageCase):
    """E: the second derivation removes W1's target, so BL-052's proof runs over the same record."""

    moves = True

    def test_the_move_is_finished_from_the_record(self) -> None:
        expected = self.twin(lambda: self.whole())
        self.setUp()
        self.swept()

        result = self.resume()

        self.assertConverged(result, expected, ["W1#1", "W1#2"])
        self.assertEqual(self.events(self.w1), ["work_started", "work_target_added", "work_target_removed"])

    def test_the_move_commit_carries_the_display_it_was_decided_on(self) -> None:
        """E: BL-048 is untouched - the move's own commit is the one it decided, made by this mutation."""
        self.swept()
        decided = self.display(self.w1)

        self.resume()

        self.assertEqual(self.subjects().count(f"chore(workline): branch from {decided}"), 1)


class MovingSecondNoSelfDependencyTests(MovingSecondTests):
    self_dependency = False


# --------------------------------------------------------------------------- G: the uninterrupted twin
class UninterruptedTwinTests(MissingStageCase):
    def test_the_swept_record_ends_where_the_uninterrupted_cycle_does(self) -> None:
        """G: Works, relations, derivation details, lifecycle and canonical state match; the commits differ."""
        expected = self.twin(lambda: self.whole())
        self.setUp()
        self.swept()

        self.resume()

        self.assertEqual(self.settled(self.outcome()), self.settled(expected))
        # The one difference the contract allows: the person's commit carries the first registration,
        # where an uninterrupted run carries it under its own 'derive from' message.
        self.assertNotIn("person: my own work", expected["subjects"])
        self.assertIn("person: my own work", self.subjects())


# --------------------------------------------------------------------------- H: zero stages are not simply allowed
class ZeroStageProofTests(MissingStageCase):
    """H: every way the proof can fail still refuses, with the record, HEAD and the remote left as they are."""

    def test_a_registration_effect_not_recorded_applied_shows_nothing(self) -> None:
        self.swept()
        self.rewrite_record(lambda record: self.registration_effects(record)[0].update({"applied": False}))

        self.assertStoppedUnchanged(lambda: self.resume())

    def test_a_registration_without_what_it_wrote_shows_nothing(self) -> None:
        """A record written before a mutation recorded what it writes keeps the behaviour it had."""
        self.swept()
        self.rewrite_record(lambda record: [e.pop("wrote", None) for e in self.registration_effects(record)])

        self.assertStoppedUnchanged(lambda: self.resume())

    def test_a_registration_without_the_branch_it_was_decided_on_shows_nothing(self) -> None:
        self.swept()
        self.rewrite_record(lambda record: [e.pop("decided_on", None) for e in self.registration_effects(record)])

        self.assertStoppedUnchanged(lambda: self.resume(), "recorded without the branch it was decided on")

    def test_a_head_that_is_not_where_the_registration_was_decided_shows_nothing(self) -> None:
        self.swept()
        git(self.root, "checkout", "-q", "-b", "side")

        self.assertStoppedUnchanged(lambda: self.resume())

        git(self.root, "checkout", "-q", "main")
        self.assertEqual(self.resume().status, "held")

    def test_a_derived_work_the_project_no_longer_holds_as_written_shows_nothing(self) -> None:
        """The Project state must be the registration's own: a Work file changed since is not it."""
        self.swept()
        path = self.store.entity_path("work", self.named("Fix1")[0])
        path.write_text(path.read_text(encoding="utf-8") + "\na line nobody recorded\n", encoding="utf-8")

        self.assertStoppedUnchanged(lambda: self.resume())

    def test_a_relation_the_committed_ledger_does_not_hold_shows_nothing(self) -> None:
        """The person committed the new files and left the ledger out: the registration is not in the committed state."""
        self.interrupted()
        self.person_commits_the_works_only()
        asked = self.starting(self.asking())()
        self.assertEqual(asked.status, "question_wait")
        # the ledger was still uncommitted, so the replay did record a Git stage for it
        self.assertNotEqual(self.between(), [])

    def test_a_reserved_relation_id_the_registration_does_not_use_shows_nothing(self) -> None:
        self.swept()
        self.rewrite_record(
            lambda record: record["reserved_ids"].update({f"{self.w1}:derive:0:rel:0": new_id("relation")})
        )

        self.assertStoppedUnchanged(lambda: self.resume(), "reconcile required")

    def test_a_decision_naming_another_work_shows_nothing(self) -> None:
        self.swept()
        self.rewrite_record(
            lambda record: record["notes"][st._DERIVATIONS]["derivations"][0]["outcome"]["works"][0]["work"].update(
                {"name": "Renamed"}
            )
        )

        self.assertStoppedUnchanged(lambda: self.resume(), "reconcile required")

    def test_a_tampered_decision_is_refused_before_its_registration_is_replayed(self) -> None:
        """The proof runs before anything is applied: a record it cannot show writes nothing at all.

        Read against the alternative of showing nothing here and letting the
        replay refuse: that one applies the recorded effects it finds unapplied
        first, so a record whose decision was rewritten would leave the Works of
        its next derivation written on disk before stopping.
        """
        self.interrupted()
        self.person_commits()
        with before_recording(rf"^{self.w1}:derive:1$"), self.assertRaises(Interrupted):
            self.starting(self.asking())()
        # the second registration is recorded and not applied, with no Git stage before it
        with after_recording(rf"^{self.w1}:derive:1$"), self.assertRaises(Interrupted):
            self.starting(self.asking())()
        self.assertEqual(self.between(), [])
        self.assertEqual(self.named("Fix2"), [])
        self.rewrite_record(
            lambda record: record["notes"][st._DERIVATIONS]["derivations"][0]["outcome"]["works"][0]["work"].update(
                {"name": "Renamed"}
            )
        )

        self.assertStoppedUnchanged(lambda: self.resume(), "reconcile required")

        self.assertEqual(self.named("Fix2"), [], "nothing of the next derivation is written")
        self.assertEqual(self.derivation_files(), 1)

    def test_a_relation_id_the_committed_ledger_does_not_hold_shows_nothing(self) -> None:
        """The registration must be in the committed state, relations included, not only its whole files.

        The reserved ID and the effect that adds it are rewritten together, so the
        record stays consistent with itself and with the decision; what it is not
        is in the ledger HEAD holds.
        """
        self.swept()
        fresh = new_id("relation")

        def retag(record: dict) -> None:
            record["reserved_ids"][f"{self.w1}:derive:0:rel:0"] = fresh
            for effect in self.registration_effects(record):
                if effect["kind"] == "add_relation" and effect["payload"]["record"].get("id"):
                    effect["payload"]["record"]["id"] = fresh
                    break

        self.rewrite_record(retag)

        self.assertStoppedUnchanged(lambda: self.resume(), "reconcile required")

    def test_a_stage_holding_more_than_a_registration_shows_nothing(self) -> None:
        """A registration stage is the Works it writes and the relations it adds, and nothing else."""
        self.swept()
        self.rewrite_record(
            lambda record: record["effects"].insert(
                next(i for i, e in enumerate(record["effects"]) if e["stage"] == f"{self.w1}:derive:1"),
                {
                    "seq": 998, "stage": f"{self.w1}:derive:0", "kind": "append_event", "applied": True,
                    "payload": {"record": {"id": new_id("event"), "type": "work_resumed", "entity": self.w1,
                                           "at": "2026-01-01T00:00:00Z"}},
                },
            )
        )

        self.assertStoppedUnchanged(lambda: self.resume(), "reconcile required")

    def test_a_stage_between_the_two_registrations_is_read_as_it_always_was(self) -> None:
        """A lifecycle, a result or any other stage there is not a missing Git stage, and never was one."""
        self.swept()
        self.rewrite_record(
            lambda record: record["effects"].insert(
                next(i for i, e in enumerate(record["effects"]) if e["stage"] == f"{self.w1}:derive:1"),
                {
                    "seq": 999, "stage": f"{self.w1}:lifecycle:9", "kind": "append_event", "applied": True,
                    "payload": {"record": {"id": new_id("event"), "type": "work_resumed", "entity": self.w1,
                                           "at": "2026-01-01T00:00:00Z"}},
                },
            )
        )

        self.assertStoppedUnchanged(lambda: self.resume())


class PartlyCommittedRegistrationTests(MissingStageCase):
    """H: the whole registration must be in the committed state, not only the files it wrote whole."""

    moves = True

    def test_a_registration_only_partly_in_the_committed_state_shows_nothing(self) -> None:
        """The person re-makes their commit over the new files alone, leaving the relations out of it.

        The proof's premise is that the Git stage is missing because what it
        would have carried is already committed. Half of it committed is not
        that, and continuing on it would take the premise for the part no
        history holds.
        """
        self.swept()
        (pending,) = self.pending()
        written = sorted({e["payload"]["path"] for e in pending["effects"]
                          if e["kind"] == "write_file" and e["stage"] == f"{self.w1}:derive:0"})
        git(self.root, "reset", "--mixed", "HEAD~1")
        git(self.root, "add", "--", *written)
        git(self.root, "-c", "user.name=person", "-c", "user.email=p@example.invalid",
            "commit", "-m", "person: only the new files")

        self.assertStoppedUnchanged(lambda: self.resume())


# --------------------------------------------------------------------------- I: BL-053 is untouched
class RefusedCommitStageTests(MissingStageCase):
    def test_a_commit_it_cannot_show_is_its_own_still_leaves_no_git_stage(self) -> None:
        """I: a person's ledger line during the resume is refused before any stage is recorded (BL-053)."""
        self.swept()
        path = self.root / ROADMAP_YAML
        original = path.read_bytes()
        path.write_bytes(original + NOTE)
        stages = self.stage_names()

        with self.assertRaises(ReconcileRequired) as refused:
            self.resume()

        self.assertIn(REFUSED, str(refused.exception))
        self.assertEqual(self.stage_names(), stages)
        self.assertEqual(path.read_bytes(), original + NOTE)

        path.write_bytes(original)
        self.assertEqual(self.resume().status, "held")


# --------------------------------------------------------------------------- J: publication
class PublicationTests(MissingStageCase):
    remote = True

    def test_the_persons_commit_is_never_taken_for_one_this_mutation_made(self) -> None:
        """J: no effect names it, nothing is published by it, and what is published is this mutation's own commit."""
        taken = self.swept()
        (pending,) = self.pending()
        made = [e for e in pending["effects"] if e["kind"] == "git_commit"]

        self.assertTrue(made, "the second derivation's own commit is recorded")
        self.assertNotIn(taken, [e.get("commit_id") for e in made])
        for effect in made:
            if effect.get("applied") is True:
                self.assertIsInstance(effect.get("commit_id"), str, effect)

        self.resume()

        self.assertEqual(self.head(), self.remote_head())
        self.assertNotIn(taken, [None])  # the person's commit exists...
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", taken).strip(), "person: my own work")


if __name__ == "__main__":
    unittest.main()
