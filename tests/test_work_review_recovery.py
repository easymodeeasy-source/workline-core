"""RB3-C1 / P3-F4: post-commit recovery of a review-v1 Work (``WORKLINE_COMPLETION_SPRINT.md`` §11, §26).

What these tests hold, end to end on a real activated Project (a fixture activation record), and on the
pure primitives:

* Class A: an exact operation-owned K1 whose normal C-2(K1) no longer holds - A2, an implementation change
  between K1 and its proof that makes the bound Context stale; A1, an operation-owned persistence transform -
  is checkpointed, the first Run invalidated by exactly its generation 4 and Supersession(R1), a successor Run
  reviews C2 (frozen from the committed K1 and its parent alone) under a version 2 request setting the first Run
  aside, its generation 3 is K_adopt, exact K_adopt is published first, the terminal Consumption binds R2 and K1,
  and K_terminal's parent is K_adopt (§26.23, §26.25, §26.26);
* C2 for every object kind, inert entries kept (§26.23);
* a non-authorizing successor stops without any repair loop (§26.24);
* request v1 / v2, the successor reservation key, the generation-4 shape and no generation 5, the old Receipt
  never consumed after generation 4, and the publication validator's adopted-result role (§26.21, §26.22, §26.25).

The refusals live in ``test_work_review_adoption_refusals`` and the interruption matrix in
``test_work_review_adoption_interruptions``.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from types import SimpleNamespace
import unittest
from unittest import mock

from test_work_review_runtime import WINDOWS, Reviewer, git
from test_work_terminal import TerminalCase

from workline import start as st
from workline import start_review
from workline.errors import ReconcileRequired, ValidationError
from workline.ids import new_id
from workline.review import gate, records, serialize, validate, work_context, work_review, workcommit
from workline.review import hermetic
from workline.review import paths as review_paths
from workline.review.store import ReviewStore
from workline.state import ProjectView


class Upgrade:
    """An implementation change between K1 and its proof: the bound Context no longer recomputes (A2).

    The loader identity is the content identity of the running implementation; once ``on``, every Context
    computed - the proof's recomputation and the replacement's fresh one alike - names the changed one.
    """

    def __init__(self) -> None:
        self.on = False

    def install(self, case, *, after_k1: bool = True) -> "Upgrade":
        real_loader = work_context.loader_identity

        def loader(directory):
            value = real_loader(directory)
            return hashlib.sha256(f"upgraded:{value}".encode()).hexdigest() if self.on else value

        patchers = [mock.patch.object(work_context, "loader_identity", side_effect=loader)]
        if after_k1:
            real_commit = start_review._result_commit

            def result_commit(*args, **kwargs):
                made = real_commit(*args, **kwargs)
                self.on = True
                return made

            patchers.append(mock.patch.object(start_review, "_result_commit", side_effect=result_commit))
        for patcher in patchers:
            patcher.start()
            case.addCleanup(patcher.stop)
        return self


TRAILER = "\n\nPersisted-by: workline"


def transform_message(case) -> None:
    """An operation-owned persistence transform of K1's message (A1): K1 differs from the Candidate only there."""
    real = workcommit.result_plan

    def plan(*args, message, **kwargs):
        return real(*args, message=message if message.endswith(TRAILER) else message + TRAILER, **kwargs)

    patcher = mock.patch.object(workcommit, "result_plan", side_effect=plan)
    patcher.start()
    case.addCleanup(patcher.stop)


class AdoptionCase(TerminalCase):
    """A Class-A adoption fixture over the terminal harness (remote by default)."""

    def never(self, ctx):
        raise AssertionError("the executor ran again")

    def resume(self, reviewer=None):
        return st.start(self.store, self.work_id, "single-work", self.never, review=self.review(reviewer))

    def adoption_ids(self, record: dict) -> dict:
        reserved = record["reserved_ids"]
        (initial,) = [value for key, value in reserved.items() if key.startswith("review-run:work-result-v1:")]
        successor = reserved.get(f"review-successor-run:{initial}")
        found = {"initial": initial, "successor": successor, "r1": reserved[f"review-receipt:{initial}:3"]}
        if successor is not None:
            found["r2"] = reserved.get(f"review-receipt:{successor}:3")
        return found

    def assert_adopted(self, record: dict, *, remote: bool = True) -> dict:
        """The whole Class-A topology the completed record and the repository hold, and nothing twice."""
        ids = self.adoption_ids(record)
        notes = record["notes"]
        checkpoint, adopted, terminal = (notes[start_review.NOTE_CLASS_A], notes[start_review.NOTE_ADOPTED_PROOF],
                                         notes[start_review.NOTE_TERMINAL_PROOF])
        k1, k_adopt, k_terminal = checkpoint["k1"], adopted["k_adopt"], terminal["terminal_commit"]
        self.assertEqual(self.head(), k_terminal)
        self.assertEqual((adopted["k1"], terminal["result_commit"], terminal["adopted_commit"]), (k1, k1, k_adopt))
        # K1 is the commit the S-c1 stage made (C-1), and the checkpoint binds its stage and parent
        (k1_effect,) = [e for e in record["effects"] if e["stage"] == checkpoint["result_stage"]]
        self.assertEqual((k1_effect["commit_id"], k1_effect["prepared_commit_id"]), (k1, k1))
        self.assertEqual(git(self.root, "rev-parse", f"{k1}^"), checkpoint["parent_k1"])
        # the lineage: K1 -> old G4 -> successor G1 -> G2 -> G3 = K_adopt -> K_terminal, one parent each
        chain = git(self.root, "rev-list", "--first-parent", f"{k1}..{k_terminal}").splitlines()
        self.assertEqual(chain[0], k_terminal)
        self.assertEqual(list(reversed(chain[1:])),
                         [adopted["old_generation_4_commit"], *adopted["successor_generation_commits"]])
        self.assertEqual(chain[1], k_adopt)
        for commit in chain:
            self.assertEqual(len(git(self.root, "rev-list", "--parents", "-n", "1", commit).split()), 2)
        # the old Run: G4 + Supersession(R1) in one commit; the successor: G1 - G3 + R2, R2 in K_adopt
        review = ReviewStore(self.store)
        old_chain, new_chain = review.gate_chain(ids["initial"]), review.gate_chain(ids["successor"])
        self.assertEqual([g.generation for g in old_chain.generations], [1, 2, 3, 4])
        self.assertEqual([g.generation for g in new_chain.generations], [1, 2, 3])
        fourth = old_chain.latest
        self.assertEqual((fourth.status, fourth.receipt_id, fourth.authorized_operation_stage),
                         (records.GATE_STATUS_OPEN, None, None))
        self.assertEqual(fourth.evidence_digest, serialize.digest(
            work_review.invalidation_evidence_record(ids["r1"], "work_class_a_replacement")))
        supersession = review.read_supersession(ids["r1"])
        self.assertEqual((supersession.review_run_id, supersession.superseding_generation, supersession.reason),
                         (ids["initial"], 4, "work_class_a_replacement"))
        self.assertEqual(self.delta(adopted["old_generation_4_commit"]), sorted([
            ("A", review_paths.gate_rel(ids["initial"], 4)), ("A", review_paths.supersession_rel(ids["r1"]))]))
        self.assertEqual(self.delta(k_adopt), sorted([
            ("A", review_paths.gate_rel(ids["successor"], 3)), ("A", review_paths.receipt_rel(ids["r2"]))]))
        # the successor reviewed C2 under a version 2 request setting the first Run aside
        task = review.read_task_input(str(new_chain.generations[0].accepted_tasks[0]["task_id"]))
        self.assertEqual(task.request_envelope["version"], 2)
        self.assertEqual(task.request_envelope["set_aside_runs"],
                         [{"review_run_id": ids["initial"], "reason": "work_class_a_replacement"}])
        c2 = review.read_candidate_snapshot(new_chain.generations[0].candidate_hash).material["candidate"]
        self.assertEqual(c2["declared_base"]["base_commit"], checkpoint["parent_k1"])
        self.assertEqual(task.request_envelope["context"]["review_checkout_capability"]["resulting_tree"],
                         self.tree_of(k1))
        # exactly one of each: Supersession, Receipts (R1, R2), Consumption (of R2), terminal event
        self.assertEqual(sorted(review.superseded_receipt_ids()), [ids["r1"]])
        self.assertEqual(sorted(review.receipt_ids()), sorted([ids["r1"], ids["r2"]]))
        self.assertEqual(sorted(review.run_ids()), sorted([ids["initial"], ids["successor"]]))
        (consumption,) = review.consumptions()
        self.assertEqual((consumption.receipt_id, consumption.authorized_result_commit_sha, consumption.artifact_kind),
                         (ids["r2"], k1, "result_commit"))
        completed = [e for e in self.events_for("HEAD") if e["type"] == "work_completed"]
        self.assertEqual(len(completed), 1)
        self.assertEqual((completed[0]["review_run_id"], completed[0]["review_receipt_id"]),
                         (ids["successor"], ids["r2"]))
        # K_terminal: exactly the event log and the Consumption, on K_adopt; no artifact delta after K1
        self.assertEqual(git(self.root, "rev-parse", f"{k_terminal}^"), k_adopt)
        self.assertEqual(self.delta(k_terminal), sorted([
            ("A", review_paths.consumption_rel(consumption.consumption_id)), ("M", ".workline/events/events.jsonl")]))
        after_k1 = git(self.root, "diff", "--name-only", k1, k_terminal).splitlines()
        self.assertTrue(all(path.startswith(".workline/review/") or path == ".workline/events/events.jsonl"
                            for path in after_k1), after_k1)
        # publication: exactly K_adopt then K_terminal, push-only, never K1 alone
        pushes = self.pushes(record)
        self.assertEqual([push["payload"]["commit"] for push in pushes], [k_adopt, k_terminal] if remote else [])
        for push in pushes:
            self.assertEqual([e["kind"] for e in record["effects"] if e["stage"] == push["stage"]], ["git_push"])
        if remote:
            self.assertEqual(self.remote_main(), k_terminal)
            self.assertEqual(adopted["destination"]["locator"], self.remote_url())
            # the published lineage carries K1 with the whole replacement authorization material
            for commit in (k1, adopted["old_generation_4_commit"], *adopted["successor_generation_commits"]):
                self.assertEqual(git(self.remote_path(), "merge-base", "--is-ancestor", commit, k_terminal,
                                     check=False), "")
                self.assertEqual(git(self.remote_path(), "cat-file", "-t", commit), "commit")
        else:
            self.assertIsNone(adopted["destination"])
        self.assertNotIn(start_review.NOTE_RESULT_PROOF, notes)
        # completed, valid, nothing left open
        self.assertEqual(ProjectView.load(self.store).work_state(self.work_id).state, "completed")
        self.assertEqual(validate.validate_review(self.store), [])
        self.assertEqual(self.pending(), [])
        return ids


# --------------------------------------------------------------------------- A2 and A1, end to end


class AdoptionTests(AdoptionCase):
    def test_a2_adopts_the_exact_k1_through_a_successor_review_and_publishes_k_adopt_first(self) -> None:
        from workline import gitcmd

        Upgrade().install(self)
        refspecs: list[str] = []
        real_push = gitcmd.push

        def push(repo, remote, refspec):
            refspecs.append(refspec)
            return real_push(repo, remote, refspec)

        with mock.patch.object(gitcmd, "push", side_effect=push):
            result, record = self.complete(self.completing(write={"out.txt": b"out\n"}, message="feat: out"))
        self.assertEqual(result.status, "completed")
        ids = self.assert_adopted(record)
        # exact refspecs, never forced: K_adopt first, then K_terminal
        adopted = record["notes"][start_review.NOTE_ADOPTED_PROOF]["k_adopt"]
        self.assertEqual(refspecs, [f"{adopted}:refs/heads/main", f"{self.head()}:refs/heads/main"])
        checkpoint = record["notes"][start_review.NOTE_CLASS_A]
        self.assertEqual((checkpoint["classification"], checkpoint["reason"]), ("A2", "a2:review_context_changed"))
        self.assertEqual(checkpoint["destination"], "behind")
        # the reviewer saw the first Candidate, then C2 - which, for A2, is the same artifact
        first, second = self.reviewer.tasks
        self.assertEqual(second.request_envelope["candidate"]["projection"],
                         first.request_envelope["candidate"]["projection"])
        self.assertNotEqual(second.request_envelope["context"]["loader_identity"],
                            first.request_envelope["context"]["loader_identity"])
        # every proof re-derives from the record and the committed objects alone
        git_ = hermetic.enter(self.store)
        k_adopt = record["notes"][start_review.NOTE_ADOPTED_PROOF]["k_adopt"]
        k_terminal = self.head()
        self.assertEqual(start_review.prove_terminal(self.store, git_, record, k_terminal),
                         record["notes"][start_review.NOTE_TERMINAL_PROOF])
        self.check_publication_validator(record, k_adopt, ids)
        self.check_old_receipt_never_consumed(record, ids)

    def check_publication_validator(self, record: dict, k_adopt: str, ids: dict) -> None:
        """§26.25: exactly one adopted-result role; a normal and an adopted role never coexist; no note, no push."""
        effects = record["effects"]
        (first,) = [index for index, effect in enumerate(effects) if effect["kind"] == "git_push"][:1]
        self.assertEqual(start_review.work_publication(self.store, effects, first, record),
                         (k_adopt, "refs/heads/main"))
        k1 = record["notes"][start_review.NOTE_CLASS_A]["k1"]

        def refused(change, what, reason="review_publication_invalid"):
            forged = json.loads(json.dumps(record))
            change(forged)
            with self.subTest(case=what):
                with self.assertRaises(ReconcileRequired) as raised:
                    start_review.work_publication(self.store, forged["effects"], first, forged)
                if reason is not None:
                    self.assertEqual(raised.exception.reason, reason)

        refused(lambda r: r["notes"].pop(start_review.NOTE_ADOPTED_PROOF), "no adopted-result note")
        refused(lambda r: r["notes"][start_review.NOTE_ADOPTED_PROOF].update(k_adopt=k1), "a note naming another commit")
        refused(lambda r: r["notes"].update({start_review.NOTE_RESULT_PROOF: {
            "contract": start_review.PROOF_CONTRACT, "result_commit": k_adopt}}), "a normal-result role beside it")
        refused(lambda r: (r["effects"][first]["payload"].update(commit=k1),
                           r["notes"].update({start_review.NOTE_RESULT_PROOF: {
                               "contract": start_review.PROOF_CONTRACT, "result_commit": k1}})),
                "K1 pushed under the normal result role in a Class-A completion")
        # V-7 re-derives the adopted-result proof before an unapplied push: after the terminal it no longer holds
        refused(lambda r: r["effects"][first].update(applied=False), "re-proven after its terminal: not current", None)

        def as_normal(r):
            r["notes"].pop(start_review.NOTE_CLASS_A)
            r["reserved_ids"] = {k: v for k, v in r["reserved_ids"].items() if not k.startswith("review-successor-run:")}

        refused(as_normal, "an adopted-result role in a normal completion")

    def check_old_receipt_never_consumed(self, record: dict, ids: dict) -> None:
        """§26.22: after generation 4 the first Run is never continued and R1 is never consumable."""
        old = start_review.work_record(record).initial
        with self.assertRaises(ReconcileRequired) as raised:
            start_review.continue_run(SimpleNamespace(store=self.store, mutation=None), old)
        self.assertIn("invalidated at generation 4", str(raised.exception))
        consumption = ReviewStore(self.store).consumptions()[0]
        forged = records.Consumption(**{**consumption.__dict__, "consumption_id": new_id("review_consumption"),
                                        "receipt_id": ids["r1"], "review_run_id": ids["initial"],
                                        "terminal_event_id": new_id("event")})
        path = self.root / review_paths.consumption_rel(forged.consumption_id)
        path.write_bytes(serialize.canonical_bytes(forged.to_record()))
        try:
            messages = [problem.message for problem in validate.review_problems(ReviewStore(self.store))]
            self.assertTrue(any("superseded" in message for message in messages), messages)
        finally:
            path.unlink()


class NoRemoteAdoptionTests(AdoptionCase):
    remote = False

    def test_a1_adopts_k1s_persisted_message_with_no_push(self) -> None:
        transform_message(self)
        result, record = self.complete(self.completing(write={"out.txt": b"out\n"}, message="feat: out"))
        self.assertEqual(result.status, "completed")
        ids = self.assert_adopted(record, remote=False)
        checkpoint = record["notes"][start_review.NOTE_CLASS_A]
        self.assertEqual((checkpoint["classification"], checkpoint["reason"], checkpoint["destination"]),
                         ("A1", "a1:message", "no-remote"))
        k1 = checkpoint["k1"]
        self.assertEqual(git(self.root, "log", "-1", "--format=%B", k1), "feat: out" + TRAILER)
        review = ReviewStore(self.store)
        old_first = review.gate_chain(ids["initial"]).generations[0]
        new_first = review.gate_chain(ids["successor"]).generations[0]
        old = review.read_candidate_snapshot(old_first.candidate_hash).material["candidate"]
        new = review.read_candidate_snapshot(new_first.candidate_hash).material["candidate"]
        self.assertEqual(old["projection"]["content"]["message"], "feat: out")
        self.assertEqual(new["projection"]["content"]["message"], "feat: out" + TRAILER)
        self.assertEqual(new["projection"]["content"]["entries"], old["projection"]["content"]["entries"])
        # C2 is declared on parent(K1), so its Context binds parent(K1)'s tree - a fresh Context, a fresh Review
        self.assertNotEqual(old_first.review_context_hash, new_first.review_context_hash)
        self.assertEqual(len(self.reviewer.tasks), 2)


class InFlightV1RequestTests(AdoptionCase):
    remote = False

    def test_a_first_run_frozen_with_a_v1_request_reconstructs_unchanged_and_is_replaced_by_a_v2_successor(self) -> None:
        """§26.21: a committed v1 TaskInput is read without mutation; the successor's request is v2 and names it."""
        real = work_review.request_envelope
        calls: list[int] = []

        def as_before_f4(candidate, context, set_aside=None, **kwargs):
            calls.append(1)
            return real(candidate, context) if len(calls) == 1 else real(candidate, context, set_aside, **kwargs)

        Upgrade().install(self)
        with mock.patch.object(work_review, "request_envelope", side_effect=as_before_f4):
            result, record = self.complete(self.completing(write={"out.txt": b"out\n"}))
        self.assertEqual(result.status, "completed")
        ids = self.assert_adopted(record, remote=False)
        review = ReviewStore(self.store)
        old_task = review.read_task_input(str(review.gate_chain(ids["initial"]).generations[0].accepted_tasks[0]["task_id"]))
        self.assertEqual(old_task.request_envelope["version"], 1)
        self.assertNotIn("set_aside_runs", old_task.request_envelope)
        self.assertEqual(work_review.request_set_aside(old_task.request_envelope, review_run_id=ids["initial"]), [])


class ObjectKindAdoptionTests(AdoptionCase):
    remote = False

    def prepare(self) -> None:
        self.commit_file("tool.sh", b"#!/bin/sh\n")
        git(self.root, "update-index", "--chmod=+x", "tool.sh")
        git(self.root, "commit", "-m", "executable", "--no-verify")
        self.commit_file("old.txt", b"old\n")
        self.commit_file("same.txt", b"same\n")
        git(self.root, "config", "core.symlinks", "false" if WINDOWS else "true")
        target = git(self.root, "hash-object", "-w", "--stdin", input=b"old-target")
        git(self.root, "update-index", "--add", "--cacheinfo", f"120000,{target},link")
        git(self.root, "commit", "-m", "link", "--no-verify")
        git(self.root, "checkout", "--", "link")
        subrepo = self.new_dir("subrepo")
        git(subrepo, "init", "-b", "main")
        (subrepo / "a.txt").write_bytes(b"a")
        git(subrepo, "add", "-A")
        git(subrepo, "commit", "-m", "sub base", "--no-verify")
        git(self.root, "-c", "protocol.file.allow=always", "-c", "core.autocrlf=false", "submodule", "add",
            subrepo.as_uri(), "sub")
        git(self.root, "commit", "-m", "add sub", "--no-verify")

    def test_c2_reconstructs_every_object_kind_and_keeps_inert_entries(self) -> None:
        def act() -> None:
            if WINDOWS:
                (self.root / "link").write_bytes(b"new-target")
            else:
                os.unlink(self.root / "link")
                os.symlink("new-target", self.root / "link")
            working = self.root / "sub"
            (working / "b.txt").write_bytes(b"b")
            git(working, "add", "-A")
            git(working, "commit", "-m", "sub advance", "--no-verify")

        Upgrade().install(self)
        executor = self.completing(write={"tool.sh": b"#!/bin/sh\necho hi\n", "same.txt": b"same\n"},
                                   delete=("old.txt",), declare=("tool.sh", "same.txt", "link", "sub"), act=act)
        result, record = self.complete(executor)
        self.assertEqual(result.status, "completed")
        ids = self.assert_adopted(record, remote=False)
        review = ReviewStore(self.store)
        old_first = review.gate_chain(ids["initial"]).generations[0]
        new_first = review.gate_chain(ids["successor"]).generations[0]
        old_snapshot = review.read_candidate_snapshot(old_first.candidate_hash)
        new_snapshot = review.read_candidate_snapshot(new_first.candidate_hash)
        old, new = old_snapshot.material["candidate"], new_snapshot.material["candidate"]
        # A2: C2 is exactly the first Candidate's artifact - every kind, the inert entry kept - on parent(K1)
        self.assertEqual(new["projection"], old["projection"])
        kinds = {entry["path"]: (entry["status"], entry["new_kind"], entry["new_mode"])
                 for entry in new["projection"]["content"]["entries"]}
        self.assertEqual(kinds, {
            "link": ("M", "symlink", "120000"), "old.txt": ("D", "absent", "000000"),
            "same.txt": ("M", "file", "100644"), "sub": ("M", "gitlink", "160000"), "tool.sh": ("M", "file", "100755"),
        })
        same = [e for e in new["projection"]["content"]["entries"] if e["path"] == "same.txt"][0]
        self.assertFalse(work_review.changing(same), "the inert declared entry stays in C2")
        self.assertEqual(new_snapshot.material["payloads"], old_snapshot.material["payloads"])
        self.assertNotEqual(new["declared_base"]["base_commit"], old["declared_base"]["base_commit"])


class NonAuthorizingSuccessorTests(AdoptionCase):
    remote = False

    def test_a_non_authorizing_successor_stops_and_invents_no_repair(self) -> None:
        finding = work_review.WorkReviewFinding("HIGH", "late-problem", "the replacement is not acceptable")
        reviewer = Reviewer()
        real_call = Reviewer.__call__

        def call(self_, task):
            if task.request_envelope.get("set_aside_runs"):
                self_.tasks.append(task)
                return work_review.WorkReviewReport(task.task_id, self_.identity, self_.version, "completed", (finding,))
            return real_call(self_, task)

        Upgrade().install(self)
        with mock.patch.object(Reviewer, "__call__", call):
            with self.assertRaises(ReconcileRequired) as raised:
                st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                         review=self.review(reviewer))
            self.assertIn("settled without authorizing", str(raised.exception))
            record = self.start_record()
            ids = self.adoption_ids(record)
            review = ReviewStore(self.store)
            self.assertEqual(len(review.gate_chain(ids["initial"]).generations), 4)
            self.assertEqual(len(review.gate_chain(ids["successor"]).generations), 2)
            self.assertEqual(record["notes"][start_review.NOTE_SEAL_REFUSAL]["review_run_id"], ids["successor"])
            self.assertNotIn(start_review.NOTE_ADOPTED_PROOF, record["notes"])
            calls = len(reviewer.tasks)
            # a retry stops the same way: no third Run, no successor of the successor, no new review
            with self.assertRaises(ReconcileRequired):
                self.resume(reviewer)
            again = self.start_record()
            self.assertEqual(again["reserved_ids"], record["reserved_ids"])
            self.assertEqual(sorted(ReviewStore(self.store).run_ids()), sorted([ids["initial"], ids["successor"]]))
            self.assertEqual(len(reviewer.tasks), calls)
            self.assertEqual([e for e in again["effects"] if e["kind"] == "git_push"], [])


# --------------------------------------------------------------------------- the pure primitives


def _candidate(work_id: str = "w_01J0000000000000000000000") -> dict:
    return {"declared_base": {"work": {"work_id": work_id, "display": "W1", "name": "W1", "desired_state": "done"}},
            "projection": {}}


class RequestVersionTests(unittest.TestCase):
    run_a, run_b, run_c = (new_id("review_run") for _ in range(3))

    def test_v1_is_built_and_read_exactly_as_before(self) -> None:
        envelope = work_review.request_envelope(_candidate(), {"k": "v"})
        self.assertEqual(envelope["version"], 1)
        self.assertNotIn("set_aside_runs", envelope)
        self.assertEqual(sorted(envelope), sorted(work_review.REQUEST_FIELDS_V1))
        self.assertEqual(work_review.request_set_aside(envelope), [])

    def test_an_ordinary_new_run_is_v2_with_an_empty_list(self) -> None:
        envelope = work_review.request_envelope(_candidate(), {"k": "v"}, [], review_run_id=self.run_a)
        self.assertEqual((envelope["version"], envelope["set_aside_runs"]), (2, []))
        self.assertEqual(work_review.request_set_aside(envelope, review_run_id=self.run_a), [])
        self.assertNotEqual(serialize.digest(envelope), serialize.digest(work_review.request_envelope(_candidate(), {"k": "v"})))

    def test_a_successor_request_names_its_predecessors_in_canonical_order(self) -> None:
        first, second = sorted([self.run_b, self.run_c])
        envelope = work_review.request_envelope(
            _candidate(), {"k": "v"},
            [{"review_run_id": second, "reason": "work_class_a_replacement"},
             {"review_run_id": first, "reason": "invalidated"}], review_run_id=self.run_a)
        self.assertEqual([item["review_run_id"] for item in envelope["set_aside_runs"]], [first, second])
        self.assertEqual(work_review.request_set_aside(envelope, review_run_id=self.run_a), envelope["set_aside_runs"])

    def test_duplicate_self_and_invalid_entries_fail_closed(self) -> None:
        good = {"review_run_id": self.run_b, "reason": "work_class_a_replacement"}
        for name, items in (
            ("duplicate", [good, dict(good)]),
            ("self", [{"review_run_id": self.run_a, "reason": "invalidated"}]),
            ("not a run id", [{"review_run_id": "w_01J0000000000000000000000", "reason": "invalidated"}]),
            ("extra field", [{**good, "note": "x"}]),
            ("blank reason", [{"review_run_id": self.run_b, "reason": " spaced"}]),
            ("line break", [{"review_run_id": self.run_b, "reason": "a\nb"}]),
            ("not a list", {"review_run_id": self.run_b}),
        ):
            with self.subTest(case=name), self.assertRaises(ValidationError):
                work_review.request_envelope(_candidate(), {"k": "v"}, items, review_run_id=self.run_a)

    def test_the_reader_refuses_every_other_shape(self) -> None:
        v2 = work_review.request_envelope(_candidate(), {"k": "v"},
                                          [{"review_run_id": self.run_b, "reason": "invalidated"},
                                           {"review_run_id": self.run_c, "reason": "invalidated"}],
                                          review_run_id=self.run_a)
        v1 = work_review.request_envelope(_candidate(), {"k": "v"})
        for name, envelope in (
            ("v1 with set_aside_runs", {**v1, "set_aside_runs": []}),
            ("v2 without set_aside_runs", {k: v for k, v in v2.items() if k != "set_aside_runs"}),
            ("v2 unsorted", {**v2, "set_aside_runs": list(reversed(v2["set_aside_runs"]))}),
            ("v2 extra field", {**v2, "extra": 1}),
            ("unknown version", {**v2, "version": 3}),
            ("another schema", {**v1, "schema": "review-planning-request"}),
        ):
            with self.subTest(case=name), self.assertRaises(ValidationError):
                work_review.request_set_aside(envelope, review_run_id=self.run_a)
        with self.assertRaises(ValidationError):
            work_review.request_set_aside(v2, review_run_id=self.run_b)  # a Run never sets itself aside


class SuccessorKeyTests(unittest.TestCase):
    def test_the_first_run_key_is_unchanged_and_the_successor_key_is_deterministic(self) -> None:
        run = new_id("review_run")
        self.assertEqual(gate.review_run_key("work-result-v1", "w_x"), "review-run:work-result-v1:w_x")
        self.assertEqual(gate.review_successor_run_key(run), f"review-successor-run:{run}")
        self.assertEqual(gate.review_successor_run_key(run), gate.review_successor_run_key(run))
        self.assertEqual(start_review.run_key("w_x"), "review-run:work-result-v1:w_x")
        for bad in ("", "rr:x", " " + run, new_id("work")):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                gate.review_successor_run_key(bad)


class GenerationShapeTests(unittest.TestCase):
    def chain(self):
        run = new_id("review_run")
        base = records.GateGeneration(
            review_run_id=run, generation=1, previous_generation=None, previous_digest=None,
            review_kind="work-result-v1", target_identity="w_x", operation_identity="start:x",
            candidate_hash="0" * 64, review_context_hash="1" * 64, effective_policy_hash="2" * 64,
            evidence_digest="3" * 64, coverage_digest="4" * 64, raw_report_set_digest="5" * 64,
            adjudication_digest="6" * 64, obligation_digest="7" * 64,
            accepted_tasks=({"task_id": "t"},), settled_tasks=(), status=records.GATE_STATUS_OPEN, receipt_id=None,
            authorized_operation_stage=None,
        )
        settled = ({"task_id": "t", "status": "completed", "result_digest": "8" * 64, "settled_generation": 2},)
        second = replace(base, generation=2, settled_tasks=settled)
        third = replace(second, generation=3, status=records.GATE_STATUS_SEALED, receipt_id="rcp_x",
                        authorized_operation_stage=work_review.AUTHORIZED_OPERATION_STAGE)
        fourth = replace(third, generation=4, status=records.GATE_STATUS_OPEN, receipt_id=None,
                         authorized_operation_stage=None)
        run_ = start_review.WorkRun("w_x", run, "t", "rcp_x")
        return run_, [base, second, third, fourth]

    def test_generation_4_is_accepted_only_as_the_open_invalidation_and_there_is_no_generation_5(self) -> None:
        run, generations = self.chain()
        start_review._require_shape(run, SimpleNamespace(generations=generations))
        self.assertEqual(start_review.TRANSITIONS[4], "invalidate")
        self.assertNotIn(5, start_review.TRANSITIONS)
        with self.assertRaises(ReconcileRequired) as raised:
            start_review._require_shape(run, SimpleNamespace(generations=generations + [replace(generations[3], generation=5)]))
        self.assertIn("no generation 5", str(raised.exception))
        for name, fourth in (("sealed", replace(generations[3], status=records.GATE_STATUS_SEALED)),
                             ("with a Receipt", replace(generations[3], receipt_id="rcp_y")),
                             ("dropping the settlement", replace(generations[3], settled_tasks=()))):
            with self.subTest(case=name), self.assertRaises(ReconcileRequired):
                start_review._require_shape(run, SimpleNamespace(generations=generations[:3] + [fourth]))


if __name__ == "__main__":
    unittest.main()
