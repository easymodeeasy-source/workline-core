"""CP RB5 set C on the shared Review surfaces (written by the shared-surface writer).

Q-C2 (NARROW_PHASE_INTEGRATION_REPAIR_INDUCED_WORK_TARGET): a ``repair_induced`` relation may name a domain fix Work
only in the exact Phase Integration case - version 2 with the provenance of the fix Work's own validated version 2
``future_work_link``, from a Finding of a Phase Integration Run, binding the Work to an earlier Integration Finding of
the Run and strategy it names, on that Finding's surface. Everything else validates exactly as before.

Q-C3 (OPTION_I_RELATION_CHAIN): two consecutive supported B/C on one surface S is a relation chain - the current
Finding's supported B/C claim on S resolves to an earlier Integration Finding F1 (B: F1 itself; C: the fix Work's
link source), and F1 has a validated supported B/C predecessor on S. No Run order, newest Run, lexical ID or latest
record decides adjacency. ``p4.adjudication(strategy_change_required=)`` is the Phase Integration contract's alone.
"""

from __future__ import annotations

from dataclasses import replace
import unittest

from rb5_doubles import ident
from test_rb5_review_shared_surfaces import Directory, generations, integration_adjudication, integration_reports
from test_review_p4_adjudication import DESCRIPTOR, TASK_A, bound, disposition, finding_ids, gate, report, returned
from workline.errors import ValidationError
from workline.review import history, p4, paths, records, serialize
from workline.review import integration as ri

S, OTHER = "parser.boundary", "scheduler.timing"
EVIDENCE = ("e" * 64,)


def base_finding() -> history.FindingSummary:
    found = integration_adjudication(ri.PhaseOutcome(ri.NOT_SATISFIED, "d" * 64, "Not met.", ("objective-a",)),
                                     ri.BRANCH_DOMAIN_REPAIR_REQUIRED, claim=p4.OUTCOME_PROBLEM)
    return history.finding_summary(found, str(found.findings[0]["finding_id"]))


BASE = base_finding()


class ChainCase(Directory):
    """Integration Runs, their Finding summaries, fix Work links and B/C relations, laid down as canonical records."""

    def setUp(self) -> None:
        super().setUp()
        self.ordinal = 0

    def lay_run(self, number: int, kind: str = records.INTEGRATION_REVIEW_KIND) -> str:
        run = ident("rr", number)
        if self.review.gate_chain(run) is None:
            first = generations(run, ident("w", 1), "a" * 64, "f" * 64, 1)[0]
            self.put(paths.gate_rel(run, 1), replace(first, review_kind=kind).to_record())
        return run

    def finding(self, number: int, run: int, surface: str = S, relation_ids: tuple[str, ...] = (),
                kind: str = records.INTEGRATION_REVIEW_KIND) -> history.FindingSummary:
        found = replace(BASE, finding_id=ident("rfd", number), review_run_id=self.lay_run(run, kind),
                        semantic_surface=surface, relation_ids=tuple(relation_ids))
        self.put(paths.history_finding_rel(found.finding_id), found.to_record())
        return found

    def relation_id(self) -> str:
        self.ordinal += 1
        return ident("rhr", self.ordinal)

    def endpoint(self, found: history.FindingSummary) -> history.Endpoint:
        return history.endpoint(history.ENDPOINT_FINDING, found.finding_id, basis=history.BASIS_HISTORY,
                                digest=serialize.digest(found.to_record()))

    def keep(self, relation: history.Relation) -> history.Relation:
        self.put(paths.history_relation_rel(relation.relation_id), relation.to_record())
        return relation

    def fix_link(self, source: history.FindingSummary, work: str, strategy: str = "split.v1") -> history.Relation:
        return self.keep(history.future_work_link(
            self.relation_id(), source, work, status=history.CAUSAL_SUPPORTED, rationale="The fix Work.",
            supporting_evidence_digests=EVIDENCE,
            integration_provenance={"source_review_run_id": source.review_run_id, "strategy_id": strategy}))

    def recurrence(self, relation_id: str, later: history.FindingSummary, earlier: history.FindingSummary,
                   surface: str = S, status: str = history.CAUSAL_SUPPORTED) -> history.Relation:
        return self.keep(history.relation(
            relation_id, history.RELATION_CROSS_RUN_RECURRENCE, self.endpoint(later), self.endpoint(earlier),
            status=status, rationale="It recurs.", semantic_surface=surface,
            supporting_evidence_digests=EVIDENCE if status == history.CAUSAL_SUPPORTED else ()))

    def induced(self, relation_id: str, later: history.FindingSummary, link: history.Relation, surface: str = S,
                status: str = history.CAUSAL_SUPPORTED, provenance: dict | None = None) -> history.Relation:
        return self.keep(history.relation(
            relation_id, history.RELATION_REPAIR_INDUCED, self.endpoint(later),
            history.endpoint(history.ENDPOINT_WORK, link.target.id, basis=history.BASIS_PROJECT),
            status=status, rationale="The fix induced it.", semantic_surface=surface,
            supporting_evidence_digests=EVIDENCE if status == history.CAUSAL_SUPPORTED else (),
            integration_provenance=provenance or dict(link.integration_provenance)))

    def later_with(self, number: int, run: int, build, surface: str = S) -> history.FindingSummary:
        """A Finding whose own G4 relation (``build(relation_id, later)``) points at an earlier one."""
        relation_id = self.relation_id()
        later = self.finding(number, run, surface, relation_ids=(relation_id,))
        build(relation_id, later)
        return later


def claim(relation_type: str, family: str, target: str, surface: str | None = S,
          status: str = history.CAUSAL_SUPPORTED) -> p4.RelationDraft:
    found = p4.P5RelationClaim(relation_type, TASK_A, 0, family, target, status, "Supported by Evidence.", surface,
                               EVIDENCE if status == history.CAUSAL_SUPPORTED else ())
    return p4.RelationDraft(found, ident("rfd", 99), (0,))


# --------------------------------------------------------------------------- Q-C2


class NarrowFixTargetTests(ChainCase):
    def setUp(self) -> None:
        super().setUp()
        self.f0 = self.finding(10, 0)
        self.link = self.fix_link(self.f0, ident("w", 50), "split.v1")
        self.f1 = self.finding(11, 1)

    def problems(self, relation: history.Relation, work_ids=None) -> list[str]:
        return [code for code, _ in history.relation_problems(self.review, relation, work_ids=work_ids)]

    def test_the_valid_narrow_shape_is_accepted(self) -> None:
        relation = self.induced(self.relation_id(), self.f1, self.link)
        record = relation.to_record()
        self.assertEqual(history.RELATION_PROVENANCE_VERSION, record["version"])
        self.assertEqual(relation, history.Relation.from_record(record, "narrow"))
        self.assertEqual([], self.problems(relation, work_ids={ident("w", 50)}))
        self.assertEqual(self.link, history.integration_fix_link(self.review, ident("w", 50)))

    def test_the_old_repair_batch_target_is_unchanged(self) -> None:
        repair = history.relation(
            self.relation_id(), history.RELATION_REPAIR_INDUCED, self.endpoint(self.f1),
            history.endpoint(history.ENDPOINT_REPAIR, ident("rrb", 1), basis=history.BASIS_HISTORY, digest="d" * 64),
            status=history.CAUSAL_SUPPORTED, rationale="The repair induced it.", semantic_surface=S,
            supporting_evidence_digests=EVIDENCE)
        record = repair.to_record()
        self.assertEqual(history.RECORD_VERSION, record["version"])
        self.assertEqual(set(history.RELATION_FIELDS), set(record))
        self.assertEqual(repair, history.Relation.from_record(record, "repair batch target"))
        with self.assertRaises(ValidationError):  # a Repair Batch target never carries integration provenance
            history.Relation.from_record({**record, "version": history.RELATION_PROVENANCE_VERSION,
                                          history.INTEGRATION_PROVENANCE_KEY: dict(self.link.integration_provenance)},
                                         "repair batch with provenance")

    def test_a_work_target_without_the_integration_provenance_is_refused(self) -> None:
        valid = self.induced(self.relation_id(), self.f1, self.link).to_record()
        plain = {key: value for key, value in valid.items() if key != history.INTEGRATION_PROVENANCE_KEY}
        with self.assertRaises(ValidationError):
            history.Relation.from_record({**plain, "version": history.RECORD_VERSION}, "an arbitrary Work target")
        for other in (history.RELATION_CROSS_RUN_RECURRENCE, history.RELATION_DOWNSTREAM_ESCAPE):
            with self.subTest(other=other), self.assertRaises(ValidationError):
                history.Relation.from_record({**valid, "relation_type": other}, f"{other} with provenance")

    def test_a_non_integration_source_finding_is_refused(self) -> None:
        source = self.finding(20, 9, kind="work-result-v1")
        relation = self.induced(self.relation_id(), source, self.link)
        self.assertIn(history.PROBLEM_CONFLICT, self.problems(relation))

    def test_a_work_without_a_version_2_link_is_refused(self) -> None:
        orphan = history.relation(
            self.relation_id(), history.RELATION_REPAIR_INDUCED, self.endpoint(self.f1),
            history.endpoint(history.ENDPOINT_WORK, ident("w", 77), basis=history.BASIS_PROJECT),
            status=history.CAUSAL_SUPPORTED, rationale="No link.", semantic_surface=S,
            supporting_evidence_digests=EVIDENCE, integration_provenance=dict(self.link.integration_provenance))
        self.assertIn(history.PROBLEM_MISSING, self.problems(orphan))
        plain_link = self.keep(history.future_work_link(self.relation_id(), self.f0, ident("w", 78),
                                                         status=history.CAUSAL_SUPPORTED, rationale="v1 only.",
                                                         supporting_evidence_digests=EVIDENCE))
        self.assertIsNone(history.integration_fix_link(self.review, plain_link.target.id), "a version 1 link is none")

    def test_a_link_to_another_finding_or_run_is_refused(self) -> None:
        other = self.finding(30, 3)
        relation = self.induced(self.relation_id(), self.f1, self.link,
                                provenance={"source_review_run_id": other.review_run_id, "strategy_id": "split.v1"})
        self.assertIn(history.PROBLEM_CONFLICT, self.problems(relation))
        strategy = self.induced(self.relation_id(), self.f1, self.link,
                                provenance={"source_review_run_id": self.f0.review_run_id, "strategy_id": "other.v1"})
        self.assertIn(history.PROBLEM_CONFLICT, self.problems(strategy))
        same_run = self.finding(12, 0)
        self.assertIn(history.PROBLEM_CONFLICT, self.problems(self.induced(self.relation_id(), same_run, self.link)))

    def test_a_mismatched_surface_is_refused(self) -> None:
        relation = self.induced(self.relation_id(), self.f1, self.link, surface=OTHER)
        self.assertIn(history.PROBLEM_CONFLICT, self.problems(relation))

    def test_two_links_for_one_work_are_a_conflict_never_a_choice(self) -> None:
        self.fix_link(self.finding(13, 2), ident("w", 50), "split.v2")
        with self.assertRaises(ValidationError) as raised:
            history.integration_fix_link(self.review, ident("w", 50))
        self.assertEqual(history.PROBLEM_CONFLICT, raised.exception.code)

    def test_previously_valid_records_validate_exactly_as_before(self) -> None:
        recurrence = self.recurrence(self.relation_id(), self.f1, self.f0)
        plain_link = history.future_work_link(self.relation_id(), self.f0, ident("w", 60),
                                              status=history.CAUSAL_SUPPORTED, rationale="v1.",
                                              supporting_evidence_digests=EVIDENCE)
        for relation in (recurrence, plain_link, self.link):
            with self.subTest(relation=relation.relation_type, version=relation.to_record()["version"]):
                self.assertEqual(relation, history.Relation.from_record(relation.to_record(), "old shape"))
        self.assertEqual([], self.problems(recurrence))
        self.assertEqual([], self.problems(self.link))

    def test_the_g4_owner_records_a_fix_work_claim_only_when_it_passes_the_fix_works(self) -> None:
        found = integration_adjudication(ri.PhaseOutcome(ri.NOT_SATISFIED, "d" * 64, "Not met.", ("objective-a",)),
                                         ri.BRANCH_DOMAIN_REPAIR_REQUIRED, claim=p4.OUTCOME_PROBLEM)
        made = p4.P5RelationClaim(history.RELATION_REPAIR_INDUCED, TASK_A, 0, p4.FIX_WORK_FAMILY, ident("w", 50),
                                  history.CAUSAL_SUPPORTED, "Supported by Evidence.", S, EVIDENCE)
        answer = replace(returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM)), relation_claims=(made,))
        with self.assertRaises(Exception) as refused:
            p4.relation_drafts(answer, found, [], policy_id=p4.P6_POLICY_ID)
        self.assertIn("not in the bound validated prior-history reference set", str(refused.exception))
        fix_works = {ident("w", 50): self.link}
        drafts = p4.relation_drafts(answer, found, [], policy_id=p4.P6_POLICY_ID, fix_works=fix_works)
        source = history.finding_summary(found, drafts[0].finding_id, relation_ids=(ident("rhr", 90),))
        record = p4.relation_record(drafts[0], ident("rhr", 90), source, [], fix_works=fix_works)
        self.assertEqual((history.ENDPOINT_WORK, ident("w", 50)), record.target.identity)
        self.assertEqual(dict(self.link.integration_provenance), dict(record.integration_provenance))
        other = replace(made, relation_type=history.RELATION_CROSS_RUN_RECURRENCE)
        with self.assertRaises(Exception):
            p4.relation_drafts(replace(answer, relation_claims=(other,)), found, [], policy_id=p4.P6_POLICY_ID,
                               fix_works=fix_works)


    def test_a_non_integration_adjudication_is_never_given_fix_works(self) -> None:
        """RB5RT-2: Q-C2 condition 1 at the producer - refused before any record is built or written."""
        reports = bound(report(TASK_A, "correctness", [("HIGH", "x", "claim one")]))
        normalized = p4.normalize_adjudication(returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM)), DESCRIPTOR,
                                               reports, None)
        found = p4.adjudication(normalized, finding_ids(len(normalized.drafts)), review_run_id=ident("rr", 1),
                                gate_record=gate(), candidate_generation=1, review_contract=p4.WORK_CONTRACT,
                                descriptor=DESCRIPTOR, reports=reports, prior=None, policy_id=p4.P6_POLICY_ID)
        made = p4.P5RelationClaim(history.RELATION_REPAIR_INDUCED, TASK_A, 0, p4.FIX_WORK_FAMILY, ident("w", 50),
                                  history.CAUSAL_SUPPORTED, "Supported by Evidence.", S, EVIDENCE)
        answer = replace(returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM)), relation_claims=(made,))
        before = self.review.history_ids(paths.HISTORY_RELATIONS)
        for fix_works in ({ident("w", 50): self.link}, {}):
            with self.subTest(fix_works=bool(fix_works)):
                with self.assertRaises(Exception) as refused:
                    p4.relation_drafts(answer, found, [], policy_id=p4.P6_POLICY_ID, fix_works=fix_works)
                self.assertEqual(p4.CODE_ADJUDICATION_INVALID, refused.exception.code)
                self.assertIn("only a Phase Integration adjudication names integration fix Works",
                              str(refused.exception))
                with self.assertRaises(Exception) as history_refused:
                    p4.g4_history(found, gate(generation=4), (), (), [], fix_works=fix_works)
                self.assertEqual(p4.CODE_ADJUDICATION_INVALID, history_refused.exception.code)
        self.assertEqual(before, self.review.history_ids(paths.HISTORY_RELATIONS), "nothing is written")
        self.assertEqual((), p4.relation_drafts(replace(answer, relation_claims=()), found, [],
                                                policy_id=p4.P6_POLICY_ID), "without fix_works: as before")


# --------------------------------------------------------------------------- Q-C3


class RelationChainTests(ChainCase):
    """F0 (Run 0) <- F1 (Run 1) <- the current claim (Run 2 or later); fix Works W0 (from F0) and W1 (from F1)."""

    def setUp(self) -> None:
        super().setUp()
        self.f0 = self.finding(10, 0)
        self.w0 = self.fix_link(self.f0, ident("w", 50), "split.v1")

    def f1(self, how: str, surface: str = S, status: str = history.CAUSAL_SUPPORTED) -> history.FindingSummary:
        if how == "B":
            return self.later_with(11, 1, lambda rid, later: self.recurrence(rid, later, self.f0, surface, status),
                                   surface)
        return self.later_with(11, 1, lambda rid, later: self.induced(rid, later, self.w0, surface, status), surface)

    def required(self, drafts, fix_works=None) -> bool:
        return p4.integration_strategy_change_required(self.review, drafts, fix_works=fix_works)

    def current(self, how: str, f1: history.FindingSummary, surface: str = S, status: str = history.CAUSAL_SUPPORTED):
        if how == "B":
            return [claim(history.RELATION_CROSS_RUN_RECURRENCE, paths.HISTORY_FINDINGS, f1.finding_id, surface,
                          status)], None
        w1 = self.fix_link(f1, ident("w", 51), "split.v2")
        return [claim(history.RELATION_REPAIR_INDUCED, p4.FIX_WORK_FAMILY, ident("w", 51), surface, status)], \
            {ident("w", 51): w1}

    def test_bb_cc_bc_and_cb_on_one_surface_require_strategy_change(self) -> None:
        for earlier, later in (("B", "B"), ("C", "C"), ("B", "C"), ("C", "B")):
            with self.subTest(chain=earlier + later):
                self.setUp()
                f1 = self.f1(earlier)
                self.assertEqual({S}, history.bc_relation_surfaces(self.review, f1.finding_id))
                drafts, fix_works = self.current(later, f1)
                self.assertTrue(self.required(drafts, fix_works))

    def test_different_surfaces_are_not_required(self) -> None:
        f1 = self.f1("B", surface=OTHER)
        drafts, _ = self.current("B", f1, surface=S)
        self.assertFalse(self.required(drafts))
        self.setUp()
        f1 = self.f1("B")
        drafts, _ = self.current("B", f1, surface=OTHER)
        self.assertFalse(self.required(drafts))

    def test_unresolved_or_insufficient_evidence_is_not_required(self) -> None:
        for status in (history.CAUSAL_UNRESOLVED, history.CAUSAL_INSUFFICIENT_EVIDENCE):
            with self.subTest(earlier=status):
                self.setUp()
                f1 = self.f1("B", status=status)
                self.assertEqual(frozenset(), history.bc_relation_surfaces(self.review, f1.finding_id))
                self.assertFalse(self.required(self.current("B", f1)[0]))
            with self.subTest(current=status):
                self.setUp()
                f1 = self.f1("B")
                self.assertFalse(self.required(self.current("B", f1, status=status)[0]))

    def test_a_new_and_no_relation_are_not_required(self) -> None:
        f1 = self.f1("B")
        self.assertFalse(self.required([]), "A_NEW: no supported B/C claim at all")
        escape = claim(history.RELATION_DOWNSTREAM_ESCAPE, paths.HISTORY_FINDINGS, f1.finding_id)
        self.assertFalse(self.required([escape]))
        lone = self.finding(12, 1)  # an earlier Finding with no predecessor of its own
        self.assertFalse(self.required(self.current("B", lone)[0]))

    def test_a_chain_through_a_non_adjacent_earlier_run_is_required(self) -> None:
        f1 = self.f1("B")
        self.finding(20, 2)  # a Run between F1 and the current one, unrelated to the chain
        drafts, _ = self.current("B", f1)
        self.assertTrue(self.required(drafts), "no immediately-previous-Run requirement")

    def test_a_predecessor_that_is_not_an_integration_finding_never_counts(self) -> None:
        work = self.finding(30, 8, kind="work-result-v1")
        f1 = self.later_with(31, 9, lambda rid, later: self.recurrence(rid, later, work))
        self.assertEqual(frozenset(), history.bc_relation_surfaces(self.review, f1.finding_id))


class AdjudicationKeywordTests(unittest.TestCase):
    def adjudicate(self, contract: str, **extra: object) -> records.P4Adjudication:
        reports = bound(report(TASK_A, "correctness", [("HIGH", "x", "claim one")]))
        normalized = p4.normalize_adjudication(returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM)), DESCRIPTOR,
                                               reports, None)
        return p4.adjudication(normalized, finding_ids(len(normalized.drafts)), review_run_id=ident("rr", 1),
                               gate_record=gate(), candidate_generation=1, review_contract=contract,
                               descriptor=DESCRIPTOR, reports=reports, prior=None, **extra)

    def integration(self, **extra: object) -> records.P4Adjudication:
        reports = integration_reports()
        normalized = p4.normalize_adjudication(returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM)), DESCRIPTOR,
                                               reports, None)
        return p4.adjudication(
            normalized, finding_ids(len(normalized.drafts)), review_run_id=ident("rr", 1),
            gate_record=gate(review_run_id=ident("rr", 1), review_kind=records.INTEGRATION_REVIEW_KIND,
                             target_identity=ident("w", 1)),
            candidate_generation=1, review_contract=records.P4_PHASE_INTEGRATION_CONTRACT, descriptor=DESCRIPTOR,
            reports=reports, prior=None, policy_id=p4.P6_POLICY_ID,
            phase_outcome=ri.PhaseOutcome(ri.NOT_SATISFIED, "d" * 64, "Not met.", ("objective-a",)),
            integration_disposition=ri.BRANCH_DOMAIN_REPAIR_REQUIRED, **extra)

    def test_the_keyword_is_refused_outside_the_integration_contract(self) -> None:
        for contract in (p4.WORK_CONTRACT, p4.PLANNING_CONTRACT):
            for value in (True, False):
                with self.subTest(contract=contract, value=value), self.assertRaises(ValidationError) as raised:
                    self.adjudicate(contract, strategy_change_required=value)
                self.assertEqual("review_record_invalid", raised.exception.code)
        with self.assertRaises(ValidationError):
            self.integration(strategy_change_required=1)

    def test_non_integration_bytes_are_unchanged(self) -> None:
        for contract in (p4.WORK_CONTRACT, p4.PLANNING_CONTRACT):
            with self.subTest(contract=contract):
                record = self.adjudicate(contract).to_record()
                self.assertEqual(record, self.adjudicate(contract, strategy_change_required=None).to_record())
                self.assertFalse(record["obligations"]["strategy_change_required"])

    def test_the_integration_contract_records_the_chain_answer(self) -> None:
        plain = self.integration().to_record()
        self.assertFalse(plain["obligations"]["strategy_change_required"])
        self.assertEqual(plain, self.integration(strategy_change_required=False).to_record())
        required = self.integration(strategy_change_required=True).to_record()
        self.assertTrue(required["obligations"]["strategy_change_required"])
        self.assertEqual({key: value for key, value in plain.items() if key != "obligations"},
                         {key: value for key, value in required.items() if key != "obligations"})
        self.assertEqual({**plain["obligations"], "strategy_change_required": True}, required["obligations"])


if __name__ == "__main__":
    unittest.main()
