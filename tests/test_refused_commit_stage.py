"""A commit refused for bytes it cannot show are its own leaves no Git stage in the record (BL-053).

A START interrupted at a question wait has already committed the cycle it
replays. When a person changes an owned ledger while it waits, the replay's
``_Session._commit`` finds that path different from HEAD and finalizes again -
so the Git stage it records carries nothing of this mutation's own, only the
person's change. ``gitops.finalize`` wrote that stage into the record and only
then applied it, where BL-043 refused the person's bytes exactly as it should.
Refusing was right; leaving the stage behind was not.

That stage is a commit this mutation never made and never can. Once the person
restores their change its paths hold nothing left to commit, so it is
classified applied - with the ID of no commit at all. With a remote, the push
recorded beside it can then never name what it publishes and every retry is
``reconcile required`` (BL-050 L1). Without one the resume goes on, until the
same mutation writes that path again: the stage is classified unapplied once
more, refused by BL-043 once more, and the extra Git stage between two
derivations makes ``_derivations_to_reuse`` refuse the record's shape. A
recorded move loses its proof the same way: BL-052 passes over the one Git
stage a cycle's own replay can leave between a registration and the removal of
the target, and a refused stage is a second one.

The proof a commit is held to right before it is staged is now made before its
stage is written into the record as well. The two moments answer the same
question of the same working tree, for two windows: nothing this mutation
cannot show is its own is written down as a Git stage, and a change another
subject makes after the stage is recorded is still refused where it always was
(F0d). The person's bytes stay exactly where they are, HEAD and the remote do
not move, and once they restore them the operation goes on as the uninterrupted
one does.
"""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import completing_executor
from test_current_cycle_dependency_resume import ROADMAP_YAML, CycleCase
from test_recorded_move_dependency import Interrupted
from test_replay_sweep_commit import SweepCase, after_the_move_is_registered, after_the_target_removal_is_recorded
from workline import start as st
from workline.errors import ReconcileRequired
from workline.mutation import Mutation, MutationController

#: What a commit refused for bytes it cannot account for says.
REFUSED = "cannot show the change it would commit is its own"
#: What a push that cannot name the commit its Git stage made says (BL-050 L1).
UNNAMED = "cannot show which commit it publishes"
#: A person's line in the relation ledger: legal YAML, and no relation of theirs.
NOTE = b"# person's note\n"


class RefusedCommitCase(CycleCase):
    """W1 derives Fix and waits for it, its next attempt asks a question, and a person edits the ledger."""

    #: Each derivation makes W1 wait for what it derived; the twin cases override this to derive without one.
    self_dependency = True

    def first(self) -> st.Derive:
        return self.waits("fix") if self.self_dependency else self.waits(others=("fix",))

    def script(self) -> dict:
        return {("W1", 1): self.first(), ("W1", 2): st.Hold("waiting")}

    def held_twin(self) -> dict:
        return self.twin(lambda: self.script())

    def asked(self) -> str:
        return self.ask(self.first())

    def hold(self):
        return self.starting({("W1", 2): st.Hold("waiting")})

    def edit_ledger(self) -> bytes:
        """The person appends a line to the relation ledger; what it held before is returned."""
        path = self.root / ROADMAP_YAML
        original = path.read_bytes()
        path.write_bytes(original + NOTE)
        return original

    def restore_ledger(self, original: bytes) -> None:
        (self.root / ROADMAP_YAML).write_bytes(original)

    def effect_count(self) -> int:
        return len(self.pending()[0].get("effects") or [])

    def commit_stages(self) -> list[dict]:
        return [e for e in self.pending()[0].get("effects") or [] if e["kind"] == "git_commit"]

    def assertRefusedWithoutRecording(self, call) -> ReconcileRequired:
        """The commit is refused, and the record holds exactly the stages and effects it held before.

        This is what BL-053 adds: before it, the refused commit's Git stage was
        written into the record and stayed there. Everything else the refusal
        always promised is asserted here too - the person's bytes are left as
        they are, and HEAD and the remote do not move (BL-043).
        """
        stages, effects = self.stage_names(), self.effect_count()
        head, remote = self.head(), self.remote_head()
        ledger = (self.root / ROADMAP_YAML).read_bytes()
        with self.assertRaises(ReconcileRequired) as refused:
            call()
        self.assertIn(REFUSED, str(refused.exception))
        self.assertEqual(self.stage_names(), stages)
        self.assertEqual(self.effect_count(), effects)
        self.assertEqual((self.root / ROADMAP_YAML).read_bytes(), ledger)
        self.assertEqual((self.head(), self.remote_head()), (head, remote))
        return refused.exception

    def assertNoNeverMadeCommit(self) -> None:
        """Every commit the record holds as applied names the commit this mutation made."""
        for effect in self.commit_stages():
            if effect.get("applied") is True:
                self.assertIsInstance(effect.get("commit_id"), str, effect)


# --------------------------------------------------------------------------- A: with a remote
class RemoteTests(RefusedCommitCase):
    def test_the_refused_commit_leaves_no_git_stage_in_the_record(self) -> None:
        """A: the refusal is the one BL-043 always made, and the record is untouched by it."""
        self.asked()
        self.edit_ledger()

        self.assertRefusedWithoutRecording(self.hold())

        self.assertEqual(self.stage_names(), [f"{self.w1}:lifecycle:0", f"{self.w1}:derive:0", "commit:0"])
        self.assertNoNeverMadeCommit()

    def test_the_record_does_not_grow_however_often_it_is_retried(self) -> None:
        """A: the person leaves their line where it is; every retry refuses the same way and records nothing."""
        self.asked()
        self.edit_ledger()

        for _ in range(3):
            self.assertRefusedWithoutRecording(self.hold())

        self.assertEqual(self.effect_count(), len(self.pending()[0]["effects"]))
        self.assertNoNeverMadeCommit()

    def test_once_they_restore_it_the_cycle_ends_as_the_uninterrupted_one_does(self) -> None:
        """A: no permanent BL-050 L1 stop - the resume converges on what the uninterrupted cycle leaves."""
        expected = self.held_twin()
        self.setUp()
        self.asked()
        original = self.edit_ledger()
        self.assertRefusedWithoutRecording(self.hold())

        self.restore_ledger(original)

        self.assertEqual(self.hold()().status, "held")
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2"])
        self.assertEqual(self.settled(self.outcome()), self.settled(expected))
        self.assertEqual(self.head(), self.remote_head())
        self.assertEqual(self.pending(), [])

    def test_the_push_of_the_cycle_never_loses_the_commit_it_publishes(self) -> None:
        """A: BL-050 L1 - no recorded push is left beside a commit without an ID, so none is refused for it."""
        self.asked()
        original = self.edit_ledger()
        self.assertRefusedWithoutRecording(self.hold())
        self.restore_ledger(original)

        result = self.hold()()

        self.assertEqual(result.status, "held")
        self.assertEqual(self.head(), self.remote_head())


# --------------------------------------------------------------------------- B: without a remote
class RemotelessTests(RefusedCommitCase):
    remote = False

    def test_the_refused_commit_leaves_no_git_stage_in_the_record(self) -> None:
        """B: the same refusal, the same untouched record, with no push recorded beside the commit."""
        self.asked()
        self.edit_ledger()

        self.assertRefusedWithoutRecording(self.hold())

        self.assertEqual(self.stage_names(), [f"{self.w1}:lifecycle:0", f"{self.w1}:derive:0", "commit:0"])

    def test_the_same_mutation_writes_that_ledger_again_and_nothing_is_reclassified(self) -> None:
        """B: the cycle goes on to decide another derivation, which writes the ledger the refusal named.

        With the refused stage in the record this is where it came back: classified
        unapplied once more by the new write, refused by BL-043 again, and its
        shape refused by ``_derivations_to_reuse`` on the retry after that.
        """
        expected = self.twin(lambda: {
            ("W1", 1): self.first(),
            ("W1", 2): self.waits(others=("more",)),
            ("W1", 3): st.Hold("waiting"),
        })
        self.setUp()
        self.asked()
        original = self.edit_ledger()
        self.assertRefusedWithoutRecording(self.hold())
        self.restore_ledger(original)

        again = self.starting({("W1", 2): self.waits(others=("more",)), ("W1", 3): st.QuestionWait("?")})
        self.assertEqual(again().status, "question_wait")
        self.assertEqual(self.starting({("W1", 3): st.Hold("waiting")})().status, "held")

        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2", "W1#3", "W1#3"])
        self.assertEqual(self.settled(self.outcome()), self.settled(expected))
        self.assertEqual(self.pending(), [])

    def test_the_derivations_of_the_cycle_keep_the_shape_a_replay_can_read(self) -> None:
        """B: exactly one Git stage between the two derivations - what ``_derivations_to_reuse`` requires."""
        self.asked()
        original = self.edit_ledger()
        self.assertRefusedWithoutRecording(self.hold())
        self.restore_ledger(original)
        self.starting({("W1", 2): self.waits(others=("more",)), ("W1", 3): st.QuestionWait("?")})()

        stages = self.stage_names()
        between = stages[stages.index(f"{self.w1}:derive:0") + 1: stages.index(f"{self.w1}:derive:1")]

        self.assertEqual(between, ["commit:0"])


# --------------------------------------------------------------------------- C: without the self-dependency
class NoSelfDependencyRemoteTests(RemoteTests):
    """C: the twin whose derivation registers no requires_completion into its own Work."""

    self_dependency = False


class NoSelfDependencyRemotelessTests(RemotelessTests):
    """C: the same twin without a remote."""

    self_dependency = False


# --------------------------------------------------------------------------- D: the move BL-052 proves
class MoveProofTests(SweepCase):
    """A cycle that derives once keeping its target and then moves it away, with the sweep commit already made.

    BL-052 passes over the one Git stage such a cycle's own replay can leave
    between the move's registration and the removal of the target. A stage left
    behind by a refused commit is a second one, which its proof does not pass
    over and must not: a commit that was never made is not a Git stage this
    START wrote. So the refused stage must not be recorded at all.
    """

    remote = False

    def swept_then_edited(self) -> bytes:
        """The swept record, then a person's line in the ledger - after everything of the cycle is committed."""
        run = lambda: self.starting(self.script())  # noqa: E731
        self.interrupt(after_the_move_is_registered, run())
        self.interrupt(_after_the_sweep_is_made, run())
        path = self.root / ROADMAP_YAML
        original = path.read_bytes()
        path.write_bytes(original + NOTE)
        return original

    def test_a_refused_commit_leaves_no_second_git_stage_before_the_removal(self) -> None:
        """D: the refusal records nothing, so the record keeps the one Git stage BL-052 reads."""
        original = self.swept_then_edited()
        stages = self.stage_names()

        with self.assertRaises(ReconcileRequired) as refused:
            self.starting(self.script())()

        self.assertIn(REFUSED, str(refused.exception))
        self.assertEqual(self.stage_names(), stages)
        self.assertEqual((self.root / ROADMAP_YAML).read_bytes(), original + NOTE)

    def test_the_move_is_still_proven_after_they_restore_it(self) -> None:
        """D: BL-052's proof holds - one legitimate Git stage between the registration and the removal."""
        original = self.swept_then_edited()
        with self.assertRaises(ReconcileRequired):
            self.starting(self.script())()
        (self.root / ROADMAP_YAML).write_bytes(original)
        self.interrupt(after_the_target_removal_is_recorded, self.starting(self.script()))

        registration, between, removal = self.shape()

        self.assertEqual(len(between), 1, f"{registration} .. {removal} holds {between}")
        self.assertEqual(self.starting(self.script())().status, "moved")


def _after_the_sweep_is_made():
    """Stop once a Git stage recorded after the move's registration has been applied."""
    from test_replay_sweep_commit import _move_registration, _removal_recorded

    real = Mutation.apply

    def fire(mutation):
        outcome = real(mutation)
        stage = _move_registration(mutation)
        if stage is None or _removal_recorded(mutation):
            return outcome
        names: list[str] = []
        for effect in mutation.effects:
            if effect["stage"] not in names:
                names.append(effect["stage"])
        made = [
            name for name in names[names.index(stage) + 1:]
            if all(e["kind"] in ("git_commit", "git_push") and e.get("applied")
                   for e in mutation.effects if e["stage"] == name)
        ]
        if made:
            raise Interrupted(f"the replay's commit {made[0]} is made")
        return outcome

    return mock.patch.object(Mutation, "apply", fire)


# --------------------------------------------------------------------------- E: the window the later proof keeps
class ApplyWindowTests(RefusedCommitCase):
    """A change another subject writes after the stage is recorded and before its commit is made (F0d).

    The proof before the record cannot see this window - the bytes were this
    mutation's own when the stage was written down. The proof before the commit
    is what refuses it, exactly as it did before BL-053, which is why that one
    is not weakened into a single check.
    """

    def test_a_change_written_after_the_stage_is_recorded_is_still_refused(self) -> None:
        """E: the record-time proof passes, the apply-time proof refuses, and nothing is committed or pushed."""
        head, remote = self.head(), self.remote_head()
        recorded: list[str] = []
        path = self.root / ROADMAP_YAML
        real = Mutation.add_effects

        def add_effects(mutation, stage, effects):
            real(mutation, stage, effects)
            if any(effect.kind == "git_commit" for effect in effects) and not recorded:
                recorded.append(stage)
                path.write_bytes(path.read_bytes() + NOTE)

        with mock.patch.object(Mutation, "add_effects", add_effects), self.assertRaises(ReconcileRequired) as refused:
            self.starting({("W1", 1): self.first(), ("W1", 2): st.QuestionWait("?")})()

        self.assertEqual(recorded, ["commit:0"])  # the stage was recorded: its bytes were this mutation's own then
        self.assertIn(REFUSED, str(refused.exception))
        self.assertTrue(path.read_bytes().endswith(NOTE))  # the person's bytes are left exactly as they are
        self.assertEqual((self.head(), self.remote_head()), (head, remote))

    def test_the_record_time_proof_is_not_what_refuses_that_window(self) -> None:
        """E: once they restore it, the stage recorded in that window makes its commit and the run goes on."""
        path = self.root / ROADMAP_YAML
        fired: list[str] = []
        real = Mutation.add_effects

        def add_effects(mutation, stage, effects):
            real(mutation, stage, effects)
            if any(effect.kind == "git_commit" for effect in effects) and not fired:
                fired.append(stage)
                path.write_bytes(path.read_bytes() + NOTE)

        with mock.patch.object(Mutation, "add_effects", add_effects), self.assertRaises(ReconcileRequired):
            self.starting({("W1", 1): self.first(), ("W1", 2): st.QuestionWait("?")})()
        self.assertEqual(self.stage_names()[-1], "commit:0")  # recorded, and its commit not made
        path.write_bytes(path.read_bytes()[: -len(NOTE)])

        self.assertEqual(self.hold()().status, "held")

        self.assertEqual(self.pending(), [])
        self.assertEqual(self.head(), self.remote_head())


# --------------------------------------------------------------------------- what this does not change
class NeighbouringGuaranteesTests(RefusedCommitCase):
    def test_a_commit_of_this_mutations_own_bytes_is_recorded_as_it_always_was(self) -> None:
        """An uninterrupted cycle records and makes every Git stage it always did."""
        expected = self.held_twin()
        self.setUp()

        result, _, stages = self.watching(self.starting(self.script()))

        self.assertEqual(result.status, "held")
        self.assertEqual([name for name in stages if name.startswith("commit:")], ["commit:0", "commit:1"])
        self.assertEqual(self.settled(self.outcome()), self.settled(expected))

    def test_a_replay_with_nothing_of_its_own_left_records_no_git_stage_as_before(self) -> None:
        """Nothing of the cycle is uncommitted, so the replay finalizes nothing and only the hold's stages are recorded."""
        self.asked()

        result, _, stages = self.watching(self.hold())

        self.assertEqual(result.status, "held")
        self.assertEqual(stages, [f"{self.w1}:lifecycle:1", "commit:1"])
        self.assertEqual(self.pending(), [])

    def test_a_person_s_change_to_a_path_the_commit_does_not_carry_is_not_refused(self) -> None:
        """Only the paths a commit would carry are proved: a change elsewhere is left to its own owner."""
        self.asked()
        (self.root / "person.txt").write_text("person\n", encoding="utf-8")

        self.assertEqual(self.hold()().status, "held")

        self.assertEqual((self.root / "person.txt").read_text(encoding="utf-8"), "person\n")

    def test_a_record_written_before_a_mutation_recorded_its_content_keeps_its_behaviour(self) -> None:
        """A record carrying no account of what it wrote is committed as it always was (BL-043's own carve-out)."""
        self.asked()
        self.edit_record(_forget_what_it_wrote)

        self.assertEqual(self.hold()().status, "held")

        self.assertEqual(self.pending(), [])


def _forget_what_it_wrote(record: dict) -> None:
    record.get("notes", {}).pop("own_content", None)
    for effect in record["effects"]:
        effect.pop("held_before", None)
        effect.pop("wrote", None)


if __name__ == "__main__":
    unittest.main()
