"""RB4 / P5 GAP-D (ruling option a, §28.13 / §28.29): explicit future-Work provenance on a direct standalone CREATE.

``create_standalone_work(..., source_finding_id=...)`` (CLI ``create-work --source-finding-id``) creates the Work
under the existing CREATE rules and persists one ``future_work_link`` (``finding_id -> work_id``) in the SAME
commit, in the ruled order: the exact P5 Finding summary and adjudication validate before the mutation exists, one
replay-stable ``review_relation`` ID is reserved, the relation path joins the pre-effect dirty_overlap judgment,
committability / checkout capability are proven before the first effect, and the committed bytes are proven after
the commit. P5 never creates a Work; the link changes no dependency, selection or lifecycle. A CREATE without the
input is RB10's CREATE, request bytes included. The P5 Findings used here come from a real P5 planning Run.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
from typing import Any, Iterator
import unittest
from unittest import mock

from helpers import git
from p5_helpers import p4_only_cycle
from planning_helpers import Crash, crash_at, state_entries
from test_review_p4_planning import Discovery, P4PlanningCase, p4_review
from workline import cli, gitcmd
from workline import create as cr
from workline import mutation as mu
from workline import roadmap_review as rr
from workline.create import WorkSpec
from workline.errors import ReconcileRequired, StopError
from workline.mutation import MutationController
from workline.review import history, p4, paths, serialize
from workline.review.committed import CommittedReviewStore
from workline.review.store import ReviewStore
from workline.review.validate import validate_review
from workline.state import UNSTARTED, ProjectView
from workline.store import WORKLINE_DIR, ProjectStore
from workline.validate import validate_project

LOW = p4.P4Claim("LOW", "low", "a minor wording note")
IMPROVE = p4.P4Claim("MID", "improve", "a clearer phase name")
SPEC = WorkSpec("Clearer phase names", "every phase name says what the phase delivers")
RELATED = f"{WORKLINE_DIR}/relations/related.yaml"
FIXED_RELATION = "rhr_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def changed_by(store: ProjectStore, commit: str) -> list[str]:
    return sorted(git(store.root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).split())


def records_of(store: ProjectStore, owner: str = cr.DIRECT_OWNER) -> list[dict[str, Any]]:
    return [record for record in MutationController(store).list_records() if record.get("owner") == owner]


@contextmanager
def completing() -> Iterator[list[dict[str, Any]]]:
    """Each mutation's record as it completes (a fresh completed record removes its own file afterwards)."""
    seen: list[dict[str, Any]] = []
    real = mu.Mutation.complete

    def complete(mutation: mu.Mutation) -> None:
        real(mutation)
        seen.append(copy.deepcopy(mutation.record))

    with mock.patch.object(mu.Mutation, "complete", complete):
        yield seen


class FutureWorkLinkCase(P4PlanningCase):
    def p5_findings(self, *, remote: bool = False) -> tuple[ProjectStore, dict[str, str]]:
        """A Project whose registered Roadmap was reviewed by a P5 Run with one LOW Problem and one Improvement."""
        store = self.planning_project(remote=remote)
        result = self.reviewed_p4(store, p4_review(Discovery((LOW, IMPROVE))))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        review = ReviewStore(store)
        found = {review.finding_history(f).disposition: f for f in review.finding_history_ids()}
        self.assertEqual({"future_work_candidate", "retained_history_only"}, set(found))
        return store, found

    def link_of(self, store: ProjectStore, relation_id: str, finding_id: str, work_id: str) -> history.Relation:
        summary = ReviewStore(store).finding_history(finding_id)
        return history.future_work_link(
            relation_id, summary, work_id, status=history.CAUSAL_SUPPORTED, rationale=cr.FUTURE_WORK_LINK_RATIONALE,
            supporting_evidence_digests=[summary.adjudication_digest],
        )

    def assertRefusedBeforeAnything(self, store: ProjectStore, call, code: str) -> StopError:
        """``code``, and nothing at all: no mutation record, reservation, temporary file, write or commit."""
        before, head, records = state_entries(store), self.head(store), MutationController(store).list_records()
        with self.assertRaises(StopError) as refused:
            call()
        self.assertEqual(code, refused.exception.code, refused.exception.message)
        self.assertEqual(before, state_entries(store), "nothing under .workline changed")
        self.assertEqual(head, self.head(store), "no commit")
        self.assertEqual(records, MutationController(store).list_records(), "no mutation record")
        return refused.exception


class ValidSourceTests(FutureWorkLinkCase):
    def test_a_valid_source_lands_the_work_and_its_link_in_one_commit_with_exact_bytes(self) -> None:
        store, findings = self.p5_findings(remote=True)
        source = findings["future_work_candidate"]
        summary_rel = paths.history_finding_rel(source)
        before = {rel: (store.root / rel).read_bytes() for rel in (summary_rel, f"{WORKLINE_DIR}/relations/roadmap.yaml",
                                                                   f"{WORKLINE_DIR}/events/events.jsonl")}
        view_before = ProjectView.load(store)
        phase_works = {phase: [w.id for w in view_before.phase_works(phase)] for phase in view_before.phases}
        base = self.head(store)

        with completing() as completed:
            created = cr.create_standalone_work(store, SPEC, source_finding_id=source)

        # one commit, made by the CREATE, carrying exactly the Work and its link; and it is published
        self.assertEqual([created.head], git(store.root, "rev-list", f"{base}..HEAD").split())
        (relation_id,) = ReviewStore(store).relation_history_ids()
        link_rel = paths.history_relation_rel(relation_id)
        work_rel = ProjectStore.entity_rel_path("work", created.work_id)
        self.assertEqual(sorted([work_rel, link_rel]), changed_by(store, created.head))
        self.assertEqual(created.head, self.remote_head(), "the one CREATE commit is the published one")
        # exact bytes: the canonical future_work_link of that Finding and that Work
        expected = self.link_of(store, relation_id, source, created.work_id)
        self.assertEqual(serialize.canonical_text(expected.to_record()).encode("utf-8"),
                         gitcmd.blob_at(store.root, created.head, link_rel))
        self.assertEqual((history.RELATION_FUTURE_WORK_LINK, (history.ENDPOINT_FINDING, source),
                          (history.ENDPOINT_WORK, created.work_id)),
                         (expected.relation_type, expected.source.identity, expected.target.identity))
        committed = CommittedReviewStore(store.root, created.head)
        self.assertEqual([], history.relation_problems(committed, committed.relation_history(relation_id),
                                                       work_ids={created.work_id}))
        # the relation ID is the one reservation, under its replay-stable key; the request records the source
        (record,) = completed
        self.assertEqual("completed", record["status"])
        self.assertEqual(relation_id, record["reserved_ids"][history.review_relation_key(source, 1)])
        self.assertEqual({**cr.direct_request_identity(SPEC), "source_finding_id": source},
                         record["invocation"]["request"])
        self.assertIn(link_rel, record["write_scope"]["files"])
        self.assertEqual(["register", cr.PROVENANCE_STAGE, "finalize"],
                         list(dict.fromkeys(effect["stage"] for effect in record["effects"])))
        # provenance only: no Finding rewrite, no Roadmap relation, no event, no Phase membership, no lifecycle
        for rel, data in before.items():
            self.assertEqual(data, (store.root / rel).read_bytes(), rel)
        view = ProjectView.load(store)
        self.assertIsNone(view.works[created.work_id].phase_id)
        self.assertEqual(UNSTARTED, view.work_state(created.work_id).state)
        self.assertEqual([], view.events_for(created.work_id))
        self.assertEqual(phase_works, {phase: [w.id for w in view.phase_works(phase)] for phase in view.phases})
        # and everything validates: Project, Review namespace, cross-source history with the Project's Works
        self.assertEqual([], validate_project(store))
        self.assertEqual([], validate_review(store))
        self.assertEqual([], history.history_problems(ReviewStore(store), work_ids=set(view.works)))


class InvalidSourceTests(FutureWorkLinkCase):
    def test_an_invalid_or_missing_source_stops_before_any_effect(self) -> None:
        store, findings = self.p5_findings()
        source = findings["future_work_candidate"]
        cases = {
            "not a review_finding ID": ("x", history.CODE_HISTORY_INVALID),
            "a Work ID": ("w_01ARZ3NDEKTSV4RRFFQ69G5FAV", history.CODE_HISTORY_INVALID),
            "no such Finding": ("rfd_01ARZ3NDEKTSV4RRFFQ69G5FAV", history.CODE_HISTORY_MISSING),
        }
        for label, (value, code) in cases.items():
            with self.subTest(label):
                self.assertRefusedBeforeAnything(
                    store, lambda value=value: cr.create_standalone_work(store, SPEC, source_finding_id=value), code)
        with self.subTest("a summary only the working tree holds is not a committed one"):
            summary_rel = paths.history_finding_rel(source)
            committed = (store.root / summary_rel).read_bytes()
            git(store.root, "rm", "-q", "--cached", summary_rel)
            git(store.root, "commit", "-q", "-m", "drop the summary from the committed state")
            self.assertRefusedBeforeAnything(
                store, lambda: cr.create_standalone_work(store, SPEC, source_finding_id=source),
                history.CODE_HISTORY_MISSING)
            (store.root / summary_rel).write_bytes(committed)
            self.commit_all(store, "restore the summary", summary_rel)
        with self.subTest("a committed summary that disagrees with its adjudication"):
            summary = ReviewStore(store).finding_history(source)
            record = {**summary.to_record(), "severity": "HIGH" if summary.severity != "HIGH" else "LOW"}
            (store.root / summary_rel).write_bytes(serialize.canonical_text(record).encode("utf-8"))
            self.commit_all(store, "tamper with the summary", summary_rel)
            self.assertRefusedBeforeAnything(
                store, lambda: cr.create_standalone_work(store, SPEC, source_finding_id=source),
                history.CODE_HISTORY_INVALID)
        self.assertEqual([], store.list_entities("work"), "P5 never created a Work, and no refused CREATE did")
        self.assertEqual([], records_of(store))

    def test_a_finding_of_a_p4_only_run_is_not_a_p5_source(self) -> None:
        store = self.planning_project()
        with p4_only_cycle():
            result = self.reviewed_p4(store, p4_review(Discovery((IMPROVE,))))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        review = ReviewStore(store)
        adjudication = review.read_adjudication(str(result.review_run_id))
        (finding_id,) = [str(finding["finding_id"]) for finding in adjudication.findings]
        with self.subTest("a P4-only Run writes no Finding summary"):
            self.assertRefusedBeforeAnything(
                store, lambda: cr.create_standalone_work(store, SPEC, source_finding_id=finding_id),
                history.CODE_HISTORY_MISSING)
        with self.subTest("a summary written for it by hand is still not a P5 source"):
            forged = history.finding_summary(adjudication, finding_id)
            rel = paths.history_finding_rel(finding_id)
            (store.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (store.root / rel).write_bytes(serialize.canonical_text(forged.to_record()).encode("utf-8"))
            self.commit_all(store, "a hand-written summary", rel)
            self.assertEqual([], history.finding_summary_problems(ReviewStore(store), forged),
                             "it agrees with its adjudication; only the Run's stored policy says it is not P5")
            error = self.assertRefusedBeforeAnything(
                store, lambda: cr.create_standalone_work(store, SPEC, source_finding_id=finding_id),
                history.CODE_HISTORY_INVALID)
            self.assertIn("not a P5 Run", error.message)
        self.assertEqual([], store.list_entities("work"))


class DirtyOverlapTests(FutureWorkLinkCase):
    def test_a_dirty_relation_path_is_refused_before_any_effect_and_the_retry_succeeds(self) -> None:
        store, findings = self.p5_findings()
        source = findings["future_work_candidate"]
        real = mu.new_id

        def fixed(kind: str) -> str:
            return FIXED_RELATION if kind == "review_relation" else real(kind)

        link_rel = paths.history_relation_rel(FIXED_RELATION)
        persons = b"a person's own file\n"
        (store.root / link_rel).parent.mkdir(parents=True, exist_ok=True)
        (store.root / link_rel).write_bytes(persons)
        head = self.head(store)
        with mock.patch.object(mu, "new_id", fixed):
            with self.assertRaises(StopError) as refused:
                cr.create_standalone_work(store, SPEC, source_finding_id=source)
            self.assertEqual("dirty_overlap", refused.exception.code, refused.exception.message)
            self.assertIn(link_rel, refused.exception.message)
            (record,) = records_of(store)
            self.assertEqual(("abandoned", []), (record["status"], record["effects"]), "refused before its first effect")
            self.assertEqual([], store.list_entities("work"), "no Work file was written")
            self.assertEqual(persons, (store.root / link_rel).read_bytes(), "the person's bytes are left alone")
            self.assertEqual(head, self.head(store))
            # the person discards it; the same CREATE then runs and takes the path
            (store.root / link_rel).unlink()
            created = cr.create_standalone_work(store, SPEC, source_finding_id=source)
        self.assertEqual(sorted([ProjectStore.entity_rel_path("work", created.work_id), link_rel]),
                         changed_by(store, created.head))
        self.assertEqual((FIXED_RELATION,), ReviewStore(store).relation_history_ids())


class ReplayTests(FutureWorkLinkCase):
    def test_replay_and_retry_keep_one_relation_id_and_one_record(self) -> None:
        store, findings = self.p5_findings()
        source = findings["future_work_candidate"]
        base = self.head(store)
        # 1. the process dies after the reservation and before the first effect
        with crash_at(cr, "_require_link_recordable"), self.assertRaises(Crash):
            cr.create_standalone_work(store, SPEC, source_finding_id=source)
        (pending,) = self.pending(store)
        key = history.review_relation_key(source, 1)
        relation_id = pending["reserved_ids"][key]
        self.assertEqual([], pending["effects"])
        # another source for the same pending request is another request: refused, nothing taken over
        with self.assertRaises(ReconcileRequired):
            cr.create_standalone_work(store, SPEC, source_finding_id=findings["retained_history_only"])
        self.assertEqual([pending], self.pending(store))
        # 2. the retry dies at its commit: the Work and the link are written, nothing is committed
        with crash_at(gitcmd, "commit_only"), self.assertRaises(Crash):
            cr.create_standalone_work(store, SPEC, source_finding_id=source)
        (pending,) = self.pending(store)
        self.assertEqual(relation_id, pending["reserved_ids"][key])
        self.assertEqual(base, self.head(store))
        link_rel = paths.history_relation_rel(relation_id)
        self.assertTrue((store.root / link_rel).is_file())
        # 3. the next retry finishes the same mutation with the same IDs: one Work, one relation, one commit
        created = cr.create_standalone_work(store, SPEC, source_finding_id=source)
        self.assertTrue(created.resumed)
        self.assertEqual(pending["mutation_id"], created.mutation_id)
        self.assertEqual((relation_id,), ReviewStore(store).relation_history_ids())
        self.assertEqual([created.work_id], [entity.id for entity in store.list_entities("work")])
        self.assertEqual([created.head], git(store.root, "rev-list", f"{base}..HEAD").split())
        self.assertEqual(sorted([ProjectStore.entity_rel_path("work", created.work_id), link_rel]),
                         changed_by(store, created.head))
        (record,) = records_of(store)
        self.assertEqual(("completed", relation_id), (record["status"], record["reserved_ids"][key]))
        self.assertEqual(1, sum(1 for effect in record["effects"] if effect["kind"] == "create_file"))
        self.assertEqual(serialize.canonical_text(self.link_of(store, relation_id, source, created.work_id).to_record())
                         .encode("utf-8"), gitcmd.blob_at(store.root, created.head, link_rel))
        self.assertEqual([], validate_review(store))


class WithoutSourceTests(FutureWorkLinkCase):
    def test_without_a_source_the_create_is_rb10s_create(self) -> None:
        # the request identity is exactly RB10's (pinned by test_decided_content_binding): no new key
        self.assertEqual(
            {"version": 1, "name": SPEC.name, "desired_state": SPEC.desired_state.strip(), "related": [],
             "derivation_detail": None},
            cr.direct_request_identity(SPEC),
        )
        store = self.new_project()
        base = self.head(store)
        with completing() as completed:
            created = cr.create_standalone_work(store, SPEC)
        (record,) = completed
        self.assertEqual({"operation": cr.DIRECT_OWNER, "name": SPEC.name, "key": SPEC.name,
                          "request": cr.direct_request_identity(SPEC)}, record["invocation"])
        self.assertEqual([RELATED], record["write_scope"]["files"])
        self.assertEqual(["register:work:work"], sorted(record["reserved_ids"]))
        self.assertEqual(["register", "finalize"], list(dict.fromkeys(effect["stage"] for effect in record["effects"])))
        self.assertEqual([ProjectStore.entity_rel_path("work", created.work_id)], changed_by(store, created.head))
        self.assertEqual([created.head], git(store.root, "rev-list", f"{base}..HEAD").split())
        self.assertFalse((store.root / paths.REVIEW_DIR).exists(), "no Review namespace is touched")
        # an explicit None is the same call
        other = WorkSpec("Second", "a second Work")
        with completing() as completed:
            cr.create_standalone_work(store, other, source_finding_id=None)
        (record,) = completed
        self.assertEqual({"operation": cr.DIRECT_OWNER, "name": "Second", "key": "Second",
                          "request": cr.direct_request_identity(other)}, record["invocation"])
        # RB10 N2 is unchanged: a pre-existing change to a path it will write (here its derivation detail, under the
        # ID it reserves) is refused before any effect, and nothing of the Review namespace is part of it
        real = mu.new_id
        derivation_id = real("derivation")
        detail_rel = f"{WORKLINE_DIR}/derivations/{derivation_id}.md"
        (store.root / detail_rel).parent.mkdir(parents=True, exist_ok=True)
        (store.root / detail_rel).write_text("a person's draft\n", encoding="utf-8")
        with mock.patch.object(mu, "new_id", lambda kind: derivation_id if kind == "derivation" else real(kind)):
            with self.assertRaises(StopError) as refused:
                cr.create_standalone_work(store, WorkSpec("Third", "a third Work", derivation_detail="why"))
        self.assertEqual("dirty_overlap", refused.exception.code)
        self.assertIn(detail_rel, refused.exception.message)
        self.assertEqual([], self.pending(store))
        self.assertFalse((store.root / paths.REVIEW_DIR).exists())

    def test_the_cli_flag_passes_the_source_and_its_absence_changes_nothing(self) -> None:
        result = cr.CreateResult("w_x", "m_x", None, False)
        for argv, expected in (
            (["create-work", ".", "--name", "N", "--desired-state", "S"], {}),
            (["create-work", ".", "--name", "N", "--desired-state", "S", "--source-finding-id", "rfd_x"],
             {"source_finding_id": "rfd_x"}),
        ):
            with self.subTest(argv=argv[-1]), mock.patch.object(cli, "create_standalone_work",
                                                                 return_value=result) as called:
                self.assertEqual(0, cli.main(argv))
                (call,) = called.call_args_list
                self.assertEqual(2, len(call.args))
                self.assertEqual(WorkSpec("N", "S"), call.args[1])
                self.assertEqual(expected, call.kwargs, "without the flag the call is exactly the old one")


if __name__ == "__main__":
    unittest.main()
