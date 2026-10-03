"""RB3-C1 / P3-F4: what is never adopted (``WORKLINE_COMPLETION_SPRINT.md`` §11.3, §11.4, §11.18.7, §26.8, §26.18, §26.23).

Class A is explicit and fail-closed. These tests hold that every other post-commit state stays reconcile (or
STOP) and leaves nothing of a replacement behind - no checkpoint, no generation 4, no Supersession, no successor
reservation, no push:

* the classifier itself, over one real K1 whose authorization went stale, against each hard safety fact: a
  person's commit on K1, HEAD on another branch, an unreadable raw parent, an unreadable delta, a tampered
  Review namespace, an existing Consumption, unprovable ownership, a contradictory activation, a durable
  publication or terminal effect, an already published K1 (the historical escape), a divergent or unreadable
  destination, and a K1 whose authorization is still current;
* end to end: Class B (a K1 delta outside the declaration), the historical escape, an old result-publication
  effect recorded but not applied when the authorization goes stale (§26.18), and a terminal stage already
  durable when it does.
"""

from __future__ import annotations

import json
import os
import subprocess
from types import SimpleNamespace
from unittest import mock

from test_work_review_runtime import git
from test_work_review_recovery import Upgrade
from test_work_terminal import Crash, TerminalCase

from workline import gitcmd, gitops
from workline import start as st
from workline import start_review
from workline.errors import GitError, ReconcileRequired, StopError
from workline.ids import new_id
from workline.mutation import MutationController
from workline.review import hermetic, records, serialize, workcommit
from workline.review import paths as review_paths
from workline.review.store import ReviewStore


class RefusalCase(TerminalCase):
    def never(self, ctx):
        raise AssertionError("the executor ran again")

    def to_k1(self) -> str:
        """Run the completion up to its exact K1, and stop there: the S-c1 commit made, its proof not yet run."""
        with mock.patch.object(start_review, "prove_result", side_effect=Crash()), self.assertRaises(Crash):
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                     review=self.review())
        record = self.start_record()
        (effect,) = [e for e in record["effects"] if str(e["stage"]).startswith(f"{self.work_id}:results:")]
        self.assertEqual(effect["commit_id"], self.head())
        return effect["commit_id"]

    def publish_by_hand(self, commit: str) -> None:
        """Someone else puts ``commit`` at the destination's main: its objects, then the branch."""
        git(self.root, "push", "-q", str(self.remote_path()), f"{commit}:refs/heads/by-hand")
        git(self.remote_path(), "update-ref", "refs/heads/main", commit)

    def assert_nothing_adopted(self, before: dict | None = None) -> None:
        record = self.start_record()
        self.assertNotIn(start_review.NOTE_CLASS_A, record["notes"])
        self.assertNotIn(start_review.NOTE_ADOPTED_PROOF, record["notes"])
        self.assertEqual([k for k in record["reserved_ids"] if k.startswith("review-successor-run:")], [])
        review = ReviewStore(self.store)
        (run_id,) = review.run_ids()
        self.assertLessEqual(len(review.gate_chain(run_id).generations), 3)
        self.assertEqual(review.superseded_receipt_ids(), ())
        if before is not None:
            self.assertEqual(len(record["effects"]), len(before["effects"]))
            self.assertEqual(record["reserved_ids"], before["reserved_ids"])


# --------------------------------------------------------------------------- the classifier, fact by fact


class ClassifierTests(RefusalCase):
    def session(self, record: dict | None = None):
        mutation = MutationController(self.store).load(self.start_record()["mutation_id"])
        if record is not None:
            mutation = SimpleNamespace(record=record, id=mutation.id)
        return SimpleNamespace(store=self.store, mutation=mutation, review=self.review(),
                               activation=start_review.require_activation(self.store),
                               destination=gitops.ensure_push_destination(self.store))

    def classify(self, k1: str, *, record: dict | None = None, session=None):
        session = session or self.session(record)
        run = start_review.work_record(session.mutation.record).run
        chain = ReviewStore(self.store).gate_chain(run.review_run_id)
        sealed = start_review.Sealed(run, start_review.run_material(self.store, run, chain), chain)
        return start_review.classify_post_commit(session, sealed, hermetic.enter(self.store), k1)

    def test_every_hard_fact_is_established_on_its_own_and_unknown_is_never_a(self) -> None:
        k1 = self.to_k1()
        upgrade = Upgrade().install(self, after_k1=False)
        # the authorization is still current: the proof failed for no reason Class A covers
        self.assertEqual(self.classify(k1).kind, start_review.CLASS_C)
        upgrade.on = True
        found = self.classify(k1)
        self.assertEqual((found.kind, found.reason, found.destination), ("A2", "a2:review_context_changed", "behind"))
        self.assertTrue(found.adoptable)
        bare, remote_before = self.remote_path(), self.remote_main()

        def expect(kind, what, reason=None, **kwargs):
            got = self.classify(k1, **kwargs)
            with self.subTest(case=what):
                self.assertEqual(got.kind, kind, got)
                self.assertFalse(got.adoptable)
                if reason is not None:
                    self.assertEqual(got.reason, reason)

        # Class C: ownership, ref and lineage
        self.commit_file("person.txt", b"theirs\n", "a person's commit")
        expect(start_review.CLASS_C, "a person's commit on K1")
        git(self.root, "reset", "-q", "--hard", k1)
        git(self.root, "checkout", "-q", "-b", "elsewhere")
        expect(start_review.CLASS_C, "HEAD on another branch")
        git(self.root, "checkout", "-q", "main")
        real_stored = workcommit._stored_commit
        with mock.patch.object(workcommit, "_stored_commit",
                               side_effect=lambda g, c: None if c == k1 else real_stored(g, c)):
            expect(start_review.CLASS_C, "K1's stored object / raw parent unreadable")
        with mock.patch.object(workcommit, "_tree_delta", side_effect=StopError("no delta", code="x")):
            expect(start_review.CLASS_C, "the complete delta unavailable")
        # Class C: the Review namespace and the Receipt
        junk = self.root / ".workline" / "review" / "gates" / "junk.txt"
        junk.write_bytes(b"junk")
        expect(start_review.CLASS_C, "a tampered Review namespace")
        junk.unlink()
        record = self.start_record()
        receipt = record["reserved_ids"][[k for k in record["reserved_ids"] if k.startswith("review-receipt:")][0]]
        run = start_review.work_record(record).run
        consumption = records.Consumption(
            consumption_id=new_id("review_consumption"), receipt_id=receipt, review_run_id=run.review_run_id,
            review_generation=3, review_kind="work-result-v1",
            authorized_candidate_hash=ReviewStore(self.store).gate_chain(run.review_run_id).generations[0].candidate_hash,
            operation_identity=start_review.work_review.operation_identity(self.work_id),
            operation_mutation_id=new_id("mutation"),
            terminal_event_id=new_id("event"), terminal_event_type="work_completed", target_identity=self.work_id,
            authorized_result_commit_sha=k1, artifact_kind="result_commit",
        )
        path = self.root / review_paths.consumption_rel(consumption.consumption_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(serialize.canonical_bytes(consumption.to_record()))
        expect(start_review.CLASS_C, "an existing Consumption of R1")
        path.unlink()
        path.parent.rmdir()
        # Class C: ownership unprovable, activation contradictory
        forged = json.loads(json.dumps(record))
        for effect in forged["effects"]:
            if str(effect["stage"]).startswith(f"{self.work_id}:results:"):
                effect["commit_id"] = git(self.root, "rev-parse", f"{k1}^")
        expect(start_review.CLASS_C, "K1 not the commit S-c1 made", record=forged)
        session = self.session()
        session.activation = start_review.Activation(session.activation.record, "f" * 64)
        expect(start_review.CLASS_C, "a contradictory activation", session=session)
        # not eligible: a durable publication or terminal effect is never reinterpreted
        destination = self.store.read_push_pin()
        for what, extra in (
            ("a durable publication effect", {"seq": 99, "stage": "x-publication:0", "kind": "git_push", "applied": False,
                                              "payload": {"remote": destination.remote, "branch": "main",
                                                          "locator": destination.allowed_urls[0], "commit": k1}}),
            ("a durable terminal event", {"seq": 99, "stage": f"{self.work_id}:lifecycle:9", "kind": "append_event",
                                          "applied": False, "payload": {"record": {
                                              "id": new_id("event"), "type": "work_completed", "entity": self.work_id,
                                              "at": "2026-10-03T00:00:00Z"}}}),
        ):
            forged = json.loads(json.dumps(record))
            forged["effects"].append(extra)
            expect(start_review.NOT_ELIGIBLE, what, start_review.REASON_CLASS_A_INELIGIBLE, record=forged)
        # the remote precondition: published -> historical escape; divergent -> C; unreadable -> STOP
        self.publish_by_hand(k1)
        expect(start_review.ESCAPED, "K1 already at the approved destination", start_review.REASON_ALREADY_PUBLISHED)
        other = git(self.root, "commit-tree", f"{remote_before}^{{tree}}", "-p", remote_before, "-m", "someone else's")
        git(self.root, "push", "-q", str(bare), f"{other}:refs/heads/other")
        git(bare, "update-ref", "refs/heads/main", other)
        expect(start_review.CLASS_C, "a divergent destination", start_review.REASON_DESTINATION_DIVERGENT)
        git(bare, "update-ref", "refs/heads/main", remote_before)
        with mock.patch.object(gitcmd, "destination_branch", side_effect=GitError("cannot read")):
            with self.assertRaises(StopError):
                self.classify(k1)
        self.assertTrue(self.classify(k1).adoptable)
        # nothing above wrote anything: no checkpoint, no G4, no successor, the record as it was
        self.assert_nothing_adopted(record)

    def test_an_already_published_k1_is_a_historical_escape_and_nothing_is_adopted(self) -> None:
        k1 = self.to_k1()
        before = self.start_record()
        self.publish_by_hand(k1)  # someone published K1 by hand
        Upgrade().install(self, after_k1=False).on = True
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work", self.never, review=self.review())
        self.assertEqual(raised.exception.reason, start_review.REASON_ALREADY_PUBLISHED)
        self.assertIn("historical", str(raised.exception))
        self.assert_nothing_adopted(before)
        self.assertEqual(self.remote_main(), k1)


# --------------------------------------------------------------------------- end to end


class ClassBTests(RefusalCase):
    remote = False

    def test_a_k1_delta_outside_the_declaration_is_class_b_and_never_adopted(self) -> None:
        from workline import yamlish

        k1 = self.to_k1()
        # the K1 this mutation's S-c1 names carries a path nobody declared
        extra = git(self.root, "hash-object", "-w", "--stdin", input=b"not declared\n")
        index = self.tmp / "forge.index"
        environment = {**os.environ, "GIT_INDEX_FILE": str(index)}
        subprocess.run(["git", "-C", str(self.root), "read-tree", k1], check=True, env=environment)
        subprocess.run(["git", "-C", str(self.root), "update-index", "--add", "--cacheinfo",
                        f"100644,{extra},stray.txt"], check=True, env=environment)
        tree = subprocess.run(["git", "-C", str(self.root), "write-tree"], check=True, env=environment,
                              capture_output=True, text=True).stdout.strip()
        parent = git(self.root, "rev-parse", f"{k1}^")
        message = git(self.root, "log", "-1", "--format=%B", k1)
        forged = git(self.root, "commit-tree", tree, "-p", parent, input=message.encode("utf-8"))
        git(self.root, "update-ref", "refs/heads/main", forged, k1)
        git(self.root, "reset", "-q", "--hard", forged)
        (pending,) = self.pending()
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        data = yamlish.load(path.read_text(encoding="utf-8"))
        for effect in data["effects"]:
            if str(effect["stage"]).startswith(f"{self.work_id}:results:"):
                effect["commit_id"] = effect["prepared_commit_id"] = forged
                effect["prepared_tree"] = tree
                effect["payload"]["paths"] = ["out.txt", "stray.txt"]
        path.write_bytes(yamlish.dump(data).encode("utf-8"))
        before = self.start_record()
        Upgrade().install(self, after_k1=False).on = True
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work", self.never, review=self.review())
        self.assertEqual(raised.exception.reason, start_review.REASON_CLASS_B)
        self.assertIn("stray.txt", str(raised.exception))
        self.assert_nothing_adopted(before)
        self.assertEqual(self.head(), forged, "nothing is reverted, repaired or rewritten")


class IncompatibleEffectTests(RefusalCase):
    def test_a_recorded_unapplied_result_publication_then_stale_authorization_is_never_class_a(self) -> None:
        """§26.18: the old publication effect is durable but not applied; automatic Class A is unavailable."""
        remote = self.remote_main()
        with mock.patch.object(gitcmd, "push", side_effect=Crash()), self.assertRaises(Crash):
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                     review=self.review())
        before = self.start_record()
        (push,) = [e for e in before["effects"] if e["kind"] == "git_push"]
        self.assertFalse(push["applied"])
        Upgrade().install(self, after_k1=False).on = True
        with self.assertRaises(ReconcileRequired):
            st.start(self.store, self.work_id, "single-work", self.never, review=self.review())
        self.assert_nothing_adopted(before)
        after = self.start_record()
        self.assertEqual([e for e in after["effects"] if e["kind"] == "git_push"], [push],
                         "the effect is neither rewritten nor deleted, and nothing is appended behind it")
        self.assertEqual(self.remote_main(), remote)

    def test_a_durable_terminal_stage_then_stale_authorization_is_never_class_a(self) -> None:
        with mock.patch.object(workcommit, "terminal_commit_effect", side_effect=Crash()), self.assertRaises(Crash):
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                     review=self.review())
        before = self.start_record()
        self.assertTrue(any(e["kind"] == "create_file" for e in before["effects"]), "the terminal stage is durable")
        Upgrade().install(self, after_k1=False).on = True
        with self.assertRaises(ReconcileRequired):
            st.start(self.store, self.work_id, "single-work", self.never, review=self.review())
        record = self.start_record()
        self.assertNotIn(start_review.NOTE_CLASS_A, record["notes"])
        self.assertEqual([k for k in record["reserved_ids"] if k.startswith("review-successor-run:")], [])
        self.assertEqual(ReviewStore(self.store).superseded_receipt_ids(), ())
