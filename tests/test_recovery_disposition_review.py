"""RB10 N4: a Review Run target of an explicit Human recovery disposition (``WORKLINE_COMPLETION_SPRINT.md`` §35.25).

The Run is the one RB3-C1 option B leaves behind for a Human: a Work Review Run
of a recoverable shape whose START runtime record was lost, which every later
START of the Work stops at as ``review_recovery_incomplete`` (``_require_owner``,
unchanged). A disposition sets it aside by the same set-aside relation a
successor's request carries, with the stable reason ``disposed_by_human``; it
never writes generation 4 or a Supersession, never rewrites a Review record,
and is refused for anything recovery can resume, has resolved already, or
cannot show exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

from test_work_review_orphan_runs import OrphanCase, UNOWNED
from test_work_review_recovery import Upgrade
from test_work_terminal import Crash

from unittest import mock

from workline import recovery_disposition as rd
from workline import start as st
from workline import start_review
from workline.errors import ReconcileRequired, StopError
from workline.mutation import MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import paths as review_paths
from workline.review import recovery, validate, work_review
from workline.review.status import SET_ASIDE_SOURCE_HUMAN, review_status
from workline.review.store import ReviewStore
from workline.status import build_status, render_json

REASON = "the lost START will not be recovered; its Work starts over"
LEDGERS = (".workline/events/events.jsonl", ".workline/relations/roadmap.yaml", ".workline/relations/related.yaml")


class ReviewTargetCase(OrphanCase):
    def dispose(self, run_id: str, reason: str = REASON) -> rd.DispositionResult:
        return rd.dispose_recovery(self.root, run_id, reason, confirmed=True)

    def review_bytes(self) -> dict[str, bytes]:
        base = self.root / ".workline" / "review"
        return {path.relative_to(self.root).as_posix(): path.read_bytes() for path in base.rglob("*") if path.is_file()}

    def frozen(self) -> tuple:
        records = sorted((r["mutation_id"], r["status"]) for r in MutationController(self.store).list_records())
        return self.head(), self.review_bytes(), records, sorted((self.root / ".workline").rglob("recovery/**/*"))

    def assert_refused(self, code: str, run_id: str) -> StopError:
        before = self.frozen()
        with self.assertRaises(StopError) as raised:
            self.dispose(run_id)
        self.assertEqual(getattr(raised.exception, "reason", None) or raised.exception.code, code, raised.exception)
        self.assertEqual(self.frozen(), before, "a refusal writes nothing: no record, no Review byte, no commit")
        return raised.exception

    def discovery(self):
        return recovery.discover_work(self.store, work_review.operation_identity(self.work_id),
                                      currency=start_review._recovery_currency(self.store), owned=set())

    def run_entry(self, run_id: str) -> dict:
        (entry,) = [e for e in review_status(self.store)["runs"]["entries"] if e["review_run_id"] == run_id]
        return entry


class DisposedRunTests(ReviewTargetCase):
    def test_a_non_resumable_no_receipt_run_is_disposed_and_recovery_sets_it_aside_by_its_stable_code(self) -> None:
        orphan = self.orphan_at_generation_1()
        with self.assertRaises(ReconcileRequired) as raised:
            self.discovery()
        self.assertIn(UNOWNED, str(raised.exception))  # RB3-C1 option B, unchanged
        review_before, base = self.review_bytes(), self.head()

        result = self.dispose(orphan)

        self.assertEqual((result.status, result.target_kind, result.target_id, result.pushed),
                         ("disposed", "review_run", orphan, False))
        # no generation 4, no Supersession, no Review record written or rewritten
        self.assertEqual(self.review_bytes(), review_before)
        self.assertEqual(len(ReviewStore(self.store).gate_chain(orphan).generations), 1)
        self.assertEqual(list((self.root / review_paths.SUPERSESSIONS_DIR).glob("*")), [])
        self.assertEqual(git_lines(self, "rev-parse", "HEAD^"), [base])
        self.assertEqual(git_lines(self, "diff-tree", "-r", "--no-commit-id", "--name-only", "HEAD"), [result.path])
        self.assertEqual(result.target_state_digest, rd.review_run_state_digest(ReviewStore(self.store), orphan))
        self.assertEqual(rd.namespace_problems(self.store), [])
        self.assertEqual(validate.validate_review(self.store), [])
        # discovery sets it aside with the stable code; nothing is recoverable
        found = self.discovery()
        self.assertIsNone(found.recoverable)
        self.assertEqual(found.set_aside, ({"review_run_id": orphan, "reason": "disposed_by_human"},))
        # Review status: the existing set_aside, from the Human source; Receipt / Consumption as they are
        entry = self.run_entry(orphan)
        self.assertEqual((entry["state"], entry["set_aside_source"]), ("set_aside", SET_ASIDE_SOURCE_HUMAN))
        self.assertEqual((entry["receipt"]["status"], entry["consumption"]["status"]), ("none", "none"))

        # a fresh START proceeds; its first Run names the disposed Run by the stable code, never the free reason
        outcome = st.start(self.store, self.work_id, "single-work", self.completing(), review=self.review())
        self.assertEqual(outcome.status, "completed")
        own = self.first_run_of(self.captured[-1])
        envelope = self.request_of(own)
        self.assertEqual(envelope["set_aside_runs"], [{"review_run_id": orphan, "reason": "disposed_by_human"}])
        self.assertNotIn(REASON, json.dumps(envelope, ensure_ascii=False))
        self.assertEqual(validate.validate_review(self.store), [])
        self.assertEqual(rd.namespace_problems(self.store), [], "the new Run is not part of the disposed Run's witness")
        entry = self.run_entry(orphan)
        self.assertEqual((entry["state"], entry["set_aside_source"]), ("set_aside", SET_ASIDE_SOURCE_HUMAN))
        self.assertEqual(self.run_entry(own)["state"], "consumed")
        data = json.loads(render_json(build_status(self.root)))
        self.assertEqual([p for p in data["validation"]["problems"] if p["code"].startswith("recovery_disposition")], [])

    def test_a_changed_run_record_after_the_disposition_breaks_its_witness(self) -> None:
        orphan = self.orphan_at_generation_1()
        result = self.dispose(orphan)
        # a changed record of the Run
        task = ReviewStore(self.store).gate_chain(orphan).generations[0].accepted_tasks[0]["task_id"]
        relative = review_paths.task_input_rel(str(task))
        (self.root / relative).write_bytes((self.root / relative).read_bytes() + b"extra: 1\n")
        self.assertEqual(rd.review_run_target_state(self.store, orphan).state, rd.STATE_INVALID)
        self.assertEqual([code for code, _ in rd.namespace_problems(self.store)], ["recovery_disposition_conflict"])
        with self.assertRaises(StopError):
            self.discovery()
        (self.root / relative).write_bytes(git_bytes(self, "show", f"HEAD:{relative}"))
        self.assertEqual(rd.review_run_target_state(self.store, orphan).state, rd.STATE_EFFECTIVE)
        # a record added to the Run
        added = self.root / review_paths.run_dir(orphan) / "000002.yaml"
        added.write_bytes(b"added: after the disposition\n")
        self.assertEqual(rd.review_run_target_state(self.store, orphan).state, rd.STATE_INVALID)
        self.assertIn("recovery_disposition_conflict", [code for code, _ in rd.namespace_problems(self.store)])
        added.unlink()
        # a committed disposition that does not bind the Run's exact state: discovery fails closed on it
        path = self.root / result.path
        record = rd.parse(path.read_bytes(), orphan)
        tampered = rd.Disposition(record.target_kind, orphan, "0" * 64, record.reason)
        path.write_bytes(rd.render(tampered).encode("utf-8"))
        from helpers import git

        git(self.root, "add", "--", result.path)
        git(self.root, "commit", "-m", "tampered", "--no-verify")
        with self.assertRaises(ReconcileRequired) as raised:
            self.discovery()
        self.assertEqual(raised.exception.reason, "review_recovery_incomplete")
        self.assertIn("recovery disposition", str(raised.exception))
        with self.assertRaises(ReconcileRequired):
            st.start(self.store, self.work_id, "single-work", self.never, review=self.review())


class RefusedRunTests(ReviewTargetCase):
    def test_a_run_its_pending_start_holds_is_safely_recoverable_and_refused(self) -> None:
        self.to_generation_1()
        (record,) = self.start_records()
        found = self.assert_refused("recovery_disposition_pending_operation", self.first_run_of(record))
        self.assertIn(record["mutation_id"], found.message)

    def test_a_pending_generation_mutation_blocks(self) -> None:
        orphan = self.orphan_at_generation_1()
        with project_operation(self.store, start_review.OWNER, {}):
            generation = MutationController(self.store).open(
                start_review.OWNER, {"operation": "review-generation", "review_run_id": orphan, "generation": 2},
                WriteScope(files=(review_paths.serialization_token_rel(orphan), review_paths.gate_rel(orphan, 2))),
            )
        found = self.assert_refused("recovery_disposition_pending_operation", orphan)
        self.assertIn(generation.id, found.message)

    def test_a_replacement_start_in_progress_blocks(self) -> None:
        orphan = self.orphan_at_generation_1()
        with project_operation(self.store, "start", {}):
            replacement = MutationController(self.store).open(
                "start", {"operation": "start", "work_id": self.work_id, "mode": "outer"},
                WriteScope(entities=(self.work_id,), files=LEDGERS),
            )
        found = self.assert_refused("recovery_disposition_pending_operation", orphan)
        self.assertIn(replacement.id, found.message)

    def test_an_already_successor_set_aside_run_gets_no_second_meaning(self) -> None:
        stale = self.orphan_at_generation_1()
        Upgrade().install(self, after_k1=False).on = True
        self.assertEqual(st.start(self.store, self.work_id, "single-work", self.completing(),
                                  review=self.review()).status, "completed")
        named = self.request_of(self.first_run_of(self.captured[-1]))["set_aside_runs"]
        self.assertEqual(named, [{"review_run_id": stale, "reason": "review_context_changed"}])
        found = self.assert_refused("recovery_disposition_unnecessary", stale)
        self.assertIn("set_aside", found.message)

    def test_a_consumed_run_gets_no_second_meaning(self) -> None:
        self.assertEqual(st.start(self.store, self.work_id, "single-work", self.completing(),
                                  review=self.review()).status, "completed")
        consumed = self.first_run_of(self.captured[-1])
        found = self.assert_refused("recovery_disposition_unnecessary", consumed)
        self.assertIn("consumed", found.message)

    def test_a_current_sealed_unsuperseded_receipt_refuses_and_no_g4_or_supersession_is_written(self) -> None:
        with mock.patch.object(start_review, "_result_commit", side_effect=Crash()), self.assertRaises(Crash):
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                     review=self.review())
        sealed = self.lose_start()
        chain = ReviewStore(self.store).gate_chain(sealed)
        self.assertEqual((chain.latest.generation, chain.latest.sealed), (3, True))
        found = self.assert_refused("recovery_disposition_receipt_current", sealed)
        self.assertIn(chain.latest.receipt_id, found.message)
        self.assertEqual(len(ReviewStore(self.store).gate_chain(sealed).generations), 3)
        self.assertEqual(list((self.root / review_paths.SUPERSESSIONS_DIR).glob("*")), [])
        # a hand-written disposition of it does not hold either: validation and recovery refuse it
        record = rd.Disposition(rd.KIND_REVIEW_RUN, sealed, rd.review_run_state_digest(ReviewStore(self.store), sealed),
                                "by hand")
        path = self.root / record.path
        path.parent.mkdir(parents=True)
        path.write_bytes(rd.render(record).encode("utf-8"))
        problems = rd.namespace_problems(self.store)
        self.assertEqual([code for code, _ in problems], ["recovery_disposition_conflict"])
        self.assertIn("Receipt", problems[0][1])


def git_lines(case, *args: str) -> list[str]:
    from helpers import git

    return git(case.root, *args).split()


def git_bytes(case, *args: str) -> bytes:
    import subprocess

    return subprocess.run(["git", "-C", str(case.root), *args], capture_output=True, check=True).stdout
