"""P5 §28.25 (with §28.3 / §28.4 / §28.15 / §28.16): history records, paths, IDs, readers and structural checks.

* the five history path families, the two-level record-path rule, and the 12-entry closed namespace;
* the two new Review ID kinds and their reservation-key helpers;
* strict schemas: canonical round-trip, unknown / missing field, schema, version, contract, vocabulary;
* the GAP-F seam: ``authorized`` / ``historical_escape`` are refused by the one named predicate;
* H-3: bounded single-line public-safe text, P-9 on new inputs only, no transcript / CoT / free-map field;
* ``ReviewStore`` readers: filename == identity, canonical bytes, enumeration, absent namespace;
* structural validation in ``validate.review_problems`` and both closed-namespace readers;
* immutable create-only collision of a history record.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from helpers import WorklineTestCase, rmtree
from workline import ids
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.mutation import MATCHING, Effect, MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import ReviewStore, checkout, fsafe, history, p4, paths, records, serialize, validate, work_checkout
from workline.store import ProjectStore

from test_review_p4_adjudication import RUN, TASK_A, adjudicate, bound, disposition, report, returned
from test_review_p4_records import adjudication_fixture, batch_fixture, result_fixture

CREATE_ONLY = unittest.skipUnless(fsafe.immutable_create_supported(), "the immutable Review create is fail-closed here")

CANDIDATE = "a" * 64
CONTEXT = "b" * 64
FILLER = "f" * 64
TARGET = "w_01ARZ3NDEKTSV4RRFFQ69G5FAV"
OPERATION = "start:" + "e" * 64
KIND = "work-result-v1"
RECEIPT = "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV"
CONSUMPTION = "rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV"
MUTATION = "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV"
RELATION = "rhr_01ARZ3NDEKTSV4RRFFQ69G5FAV"
OTHER_RELATION = "rhr_01ARZ3NDEKTSV4RRFFQ69G5FAW"
DECISION = "rhd_01ARZ3NDEKTSV4RRFFQ69G5FAV"
WORK = "w_01ARZ3NDEKTSV4RRFFQ69G5FAW"
OTHER_RUN = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAW"


# --------------------------------------------------------------------------- source fixtures


def generation(number: int, previous_digest: str | None, *, adjudication_digest: str = FILLER, sealed: bool = False,
               run: str = RUN) -> records.GateGeneration:
    """One gate generation of the fixture Run (no tasks: the history checks read the chain's identities only)."""
    return records.GateGeneration(
        review_run_id=run, generation=number, previous_generation=None if number == 1 else number - 1,
        previous_digest=previous_digest, review_kind=KIND, target_identity=TARGET, operation_identity=OPERATION,
        candidate_hash=CANDIDATE, review_context_hash=CONTEXT, effective_policy_hash=p4.policy_hash(),
        evidence_digest=FILLER, coverage_digest=FILLER, raw_report_set_digest=FILLER,
        adjudication_digest=adjudication_digest, obligation_digest=FILLER, accepted_tasks=(), settled_tasks=(),
        status=records.GATE_STATUS_SEALED if sealed else records.GATE_STATUS_OPEN,
        receipt_id=RECEIPT if sealed else None, authorized_operation_stage="terminal" if sealed else None,
    )


def chain(count: int, *, adjudication: records.P4Adjudication | None = None, seal_at: int | None = None,
          run: str = RUN) -> list[records.GateGeneration]:
    """Generations 1..count; from G4 on they bind ``adjudication``, and ``seal_at`` seals with the Receipt."""
    found: list[records.GateGeneration] = []
    previous = None
    bound_digest = FILLER if adjudication is None else serialize.digest(adjudication.to_record())
    for number in range(1, count + 1):
        item = generation(number, previous, adjudication_digest=bound_digest if number >= 4 else FILLER,
                          sealed=number == seal_at, run=run)
        found.append(item)
        previous = serialize.digest(item.to_record())
    return found


def receipt(adjudication_digest: str = FILLER) -> records.Receipt:
    return records.Receipt(
        receipt_id=RECEIPT, review_run_id=RUN, review_generation=5, review_kind=KIND, target_identity=TARGET,
        operation_identity=OPERATION, authorized_candidate_hash=CANDIDATE, review_context_hash=CONTEXT,
        effective_policy_hash=p4.policy_hash(), coverage_hash=FILLER, adjudication_hash=adjudication_digest,
        obligation_digest=FILLER, unresolved_obligations=0, authorized_operation_stage="terminal",
    )


def consumption(consumption_id: str = CONSUMPTION) -> records.Consumption:
    return records.Consumption(
        consumption_id=consumption_id, receipt_id=RECEIPT, review_run_id=RUN, review_generation=5, review_kind=KIND,
        authorized_candidate_hash=CANDIDATE, operation_identity=OPERATION, operation_mutation_id=MUTATION,
        terminal_event_id=None, terminal_event_type=None, target_identity=TARGET, authorized_result_commit_sha=None,
    )


def snapshot() -> records.CandidateSnapshot:
    return records.CandidateSnapshot(
        candidate_hash=CANDIDATE, reconstruction_mode=records.RECONSTRUCTION_SNAPSHOT,
        projection_semantics_version="v1", material={"payload": "the exact Work snapshot payload"}, builder=None,
    )


def human_reports() -> list:
    return bound(report(TASK_A, "correctness", [("HIGH", "x", "is the limit 10 or 20")]))


def human_adjudication() -> records.P4Adjudication:
    return adjudicate(human_reports(), returned(disposition(TASK_A, 0, p4.OUTCOME_HUMAN)))


def ready_reports() -> list:
    return bound(report(TASK_A, "correctness", [("LOW", "x", "a clearer name exists")]))


def ready_adjudication() -> records.P4Adjudication:
    """AUTHORIZATION_READY with one non-blocking Improvement Finding."""
    return adjudicate(ready_reports(), returned(disposition(TASK_A, 0, p4.OUTCOME_IMPROVEMENT, severity="LOW")))


def repair_reports() -> list:
    return bound(report(TASK_A, "correctness", [("HIGH", "x", "the claim")]))


def summary_fixture(**overrides: object) -> history.RunSummary:
    """A structurally valid human_wait Run summary (its sources are not consulted)."""
    values: dict = dict(
        review_run_id=RUN, review_kind=KIND, target_identity=TARGET, operation_identity=OPERATION,
        candidate_hash=CANDIDATE, candidate_generation=1, review_context_hash=CONTEXT,
        effective_policy_hash=p4.policy_hash(), evidence_digest=FILLER, coverage_digest=FILLER, gate_generation=4,
        gate_digest="d" * 64, adjudication_digest="c" * 64, finding_ids=(), repair_batch_id=None, receipt_id=None,
        consumption_id=None, durable_disposition=history.DISPOSITION_HUMAN_WAIT,
    )
    values.update(overrides)
    return history.RunSummary(**values)


def relation_fixture(**overrides: object) -> dict:
    record = history.relation(
        RELATION, history.RELATION_CROSS_RUN_RECURRENCE,
        history.endpoint(history.ENDPOINT_FINDING, "rfd_01ARZ3NDEKTSV4RRFFQ69G5F10", basis=history.BASIS_HISTORY,
                         digest="1" * 64),
        history.endpoint(history.ENDPOINT_FINDING, "rfd_01ARZ3NDEKTSV4RRFFQ69G5F11", basis=history.BASIS_SOURCE,
                         digest="2" * 64),
        status=history.CAUSAL_SUPPORTED, rationale="the same parser invariant failed again",
        semantic_surface="parser", supporting_evidence_digests=["3" * 64],
    ).to_record()
    record.update(overrides)
    return record


#: The caller's G-4 decision identity: a field of the evidence, never its filename identity (GAP-G).
CALLER_DECISION = "decision:2026-10-04.limit"


def human_decision_fixture(found: records.P4Adjudication | None = None, *, changed: bool = True,
                           review_decision_id: str = DECISION) -> history.HumanDecisionEvidence:
    found = found or human_adjudication()
    return history.human_decision_evidence(
        review_decision_id, found, decision_id=CALLER_DECISION,
        decision_disposition=history.DECISION_REQUIREMENT_CHANGED if changed else history.DECISION_REQUIREMENT_CONFIRMED,
        affected_entries=[found.entries[0]], question_summary="Is the limit 10 or 20?",
        decision_summary="The limit is 20." if changed else "The documented limit applies.",
        authority_identity="registry.md#rules/limits",
        action_class=history.ACTION_RESUME_CHANGED if changed else history.ACTION_RESUME_CONFIRMED,
        source_digests=["4" * 64], effect_digests=["5" * 64] if changed else [],
    )


def every_record() -> dict[str, object]:
    """One structurally valid record of every history family (sources not laid down)."""
    repair = adjudication_fixture()
    digest = serialize.digest(repair.to_record())
    batch = batch_fixture(repair, digest)
    result = result_fixture(batch)
    finding_id = str(repair.findings[0]["finding_id"])
    return {
        paths.HISTORY_RUNS: summary_fixture(),
        paths.HISTORY_FINDINGS: history.finding_summary(repair, finding_id),
        paths.HISTORY_REPAIRS: history.repair_summary(repair, batch, result, source_candidate_material_digest="9" * 64),
        paths.HISTORY_RELATIONS: history.Relation.from_record(relation_fixture(), "relation"),
        paths.HISTORY_HUMAN_DECISIONS: human_decision_fixture(),
    }


class HistoryCase(unittest.TestCase):
    """A bare directory read through ``ReviewStore``: records laid down as their exact canonical bytes."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="workline-p5-history-"))
        self.addCleanup(rmtree, self.root)
        self.store = ProjectStore(self.root)
        self.review = ReviewStore(self.store)

    def put(self, relative: str, record: dict | None = None, raw: bytes | None = None) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw if raw is not None else serialize.canonical_bytes(record))

    def put_history(self, family: str, found: object, identifier: str | None = None) -> str:
        identifier = identifier or history.record_identity(family, found)
        relative = paths.history_rel(family, identifier)
        self.put(relative, found.to_record())  # type: ignore[attr-defined]
        return relative

    def put_chain(self, generations: list[records.GateGeneration]) -> None:
        for item in generations:
            self.put(paths.gate_rel(item.review_run_id, item.generation), item.to_record())

    def put_reports(self, reports: list) -> None:
        for _, digest, record in reports:
            self.put(paths.report_rel(digest), record)

    def put_adjudication(self, found: records.P4Adjudication) -> str:
        self.put(paths.adjudication_rel(found.review_run_id), found.to_record())
        return serialize.digest(found.to_record())

    def codes(self) -> list[str]:
        return [problem.code for problem in validate.review_problems(self.review)]


# --------------------------------------------------------------------------- identities, IDs, keys


class IdentityTests(unittest.TestCase):
    def test_the_history_contract_is_one_constant_distinct_from_every_v1_p3_p4_identity(self) -> None:
        from workline.review import planning, work_checkout as wc, work_context, work_invocation

        others: set[str] = set()
        for module in (records, p4, planning, wc, work_context, work_invocation, checkout):
            for name, value in vars(module).items():
                # RB4-OWNER: p4 re-exports the P5 policy identity for its family dispatch; it declares nothing new
                if module is p4 and name in ("P5_POLICY_ID", "DEFAULT_POLICY_ID"):
                    self.assertEqual(history.P5_POLICY_ID, value)
                    continue
                if name.isupper() and isinstance(value, str) and value.startswith("review-"):
                    others.add(value)
        self.assertEqual("review-v1-history-v1", history.HISTORY_CONTRACT)
        self.assertNotIn(history.HISTORY_CONTRACT, others)
        self.assertTrue({p4.POLICY_ID, records.P4_PLANNING_CONTRACT, records.P4_WORK_CONTRACT} <= others)
        # GAP-A (3): the P5-capable Effective Policy is one more constant, distinct from every v1 / P4 identity
        # and from the history contract; it is a per-Run stored policy, never an owner marker.
        self.assertEqual("review-v1-p5-policy-v1", history.P5_POLICY_ID)
        self.assertNotIn(history.P5_POLICY_ID, others | {history.HISTORY_CONTRACT})
        self.assertNotIn(history.P5_POLICY_ID, records.P4_CONTRACTS)

    def test_the_schemas_are_new_and_distinct(self) -> None:
        existing = {value for name, value in vars(records).items() if name.startswith("SCHEMA_")}
        existing |= {value for name, value in vars(p4).items() if name.startswith("SCHEMA_")}
        self.assertEqual(5, len(set(history.SCHEMAS)))
        self.assertEqual(set(), set(history.SCHEMAS) & existing)

    def test_the_closed_vocabularies_are_the_frozen_ones(self) -> None:
        self.assertEqual({"authorized", "repaired_to_next_candidate", "human_wait", "not_authorized", "invalidated",
                          "set_aside", "consumed", "historical_escape"}, set(history.RUN_DISPOSITIONS))
        self.assertEqual(("supported", "unresolved", "insufficient_evidence"), history.CAUSAL_STATUSES)
        self.assertEqual({"cross_run_recurrence", "repair_induced", "downstream_escape", "future_work_link"},
                         set(history.RELATION_TYPES))
        self.assertEqual({"repaired_current_cycle", "retained_history_only", "future_work_candidate",
                          "no_action_after_adjudication", "repair_required"}, set(history.FINDING_DISPOSITIONS))
        self.assertEqual(("Problem", "Improvement"), history.FINDING_CATEGORIES)
        self.assertEqual(p4.DECISION_DISPOSITIONS, history.DECISION_DISPOSITIONS)
        self.assertEqual(p4._DECISION_ID.pattern, history.DECISION_ID_PATTERN.pattern)
        self.assertEqual(set(history.ACTION_CLASSES), set(history.DECISION_ACTIONS.values()))
        self.assertEqual(set(history.DECISION_DISPOSITIONS), set(history.DECISION_ACTIONS))
        self.assertEqual("not_required_by_contract", history.HISTORY_NOT_REQUIRED)


class IdKindTests(unittest.TestCase):
    def test_the_two_new_kinds_round_trip_and_cannot_be_read_as_relation_or_run(self) -> None:
        for kind in ("review_relation", "review_decision"):
            with self.subTest(kind=kind):
                identifier = ids.new_id(kind)
                self.assertEqual(kind, ids.kind_of(identifier))
                prefix = ids.PREFIXES[kind]
                self.assertFalse(prefix.startswith("rel") or prefix.startswith("rr"), prefix)
        self.assertEqual("review_relation", ids.kind_of(RELATION))
        self.assertEqual("review_decision", ids.kind_of(DECISION))
        self.assertEqual("relation", ids.kind_of("rel_01ARZ3NDEKTSV4RRFFQ69G5FAV"))
        self.assertEqual("review_run", ids.kind_of(RUN))
        self.assertEqual("roadmap", ids.kind_of("r_01ARZ3NDEKTSV4RRFFQ69G5FAV"))
        self.assertEqual(len(ids.PREFIXES), len(set(ids.PREFIXES.values())), "every prefix names one kind")

    def test_every_earlier_kind_keeps_its_prefix(self) -> None:
        earlier = {"mutation": "mut", "roadmap": "r", "phase": "p", "work": "w", "relation": "rel", "event": "evt",
                   "derivation": "der", "review_run": "rr", "review_receipt": "rcp", "review_consumption": "rcs",
                   "review_task": "rtk", "review_finding": "rfd", "review_repair_batch": "rrb"}
        self.assertEqual(earlier, {kind: prefix for kind, prefix in ids.PREFIXES.items() if kind in earlier})
        # P6 (§30.16) adds the two policy kinds after P5's two; nothing else is added.
        self.assertEqual(set(earlier) | {"review_relation", "review_decision", "review_policy_change",
                                         "review_policy_evaluation"}, set(ids.PREFIXES))

    def test_reservation_keys_are_replay_stable_and_never_a_run_key(self) -> None:
        self.assertEqual(f"review-relation:{RUN}:1", history.review_relation_key(RUN, 1))
        self.assertEqual(history.review_relation_key(RUN, 2), history.review_relation_key(RUN, 2))
        self.assertEqual(f"review-decision:{RUN}", history.review_decision_key(RUN))
        for key in (history.review_relation_key(RUN, 1), history.review_decision_key(RUN)):
            self.assertFalse(key.startswith("review-run:"))
        for call in (
            lambda: history.review_relation_key("not-an-id", 1),
            lambda: history.review_relation_key(RUN, 0),
            lambda: history.review_relation_key(RUN, True),
            lambda: history.review_relation_key("a:b", 1),
            lambda: history.review_decision_key(RELATION),
            lambda: history.review_decision_key(""),
        ):
            with self.subTest(call=call), self.assertRaises(ValidationError):
                call()


# --------------------------------------------------------------------------- paths


class PathTests(unittest.TestCase):
    def test_the_five_families_have_the_frozen_shapes(self) -> None:
        finding = "rfd_01ARZ3NDEKTSV4RRFFQ69G5F10"
        batch = "rrb_01ARZ3NDEKTSV4RRFFQ69G5FAB"
        self.assertEqual(f".workline/review/history/runs/{RUN}.yaml", paths.history_run_rel(RUN))
        self.assertEqual(f".workline/review/history/findings/{finding}.yaml", paths.history_finding_rel(finding))
        self.assertEqual(f".workline/review/history/repairs/{batch}.yaml", paths.history_repair_rel(batch))
        self.assertEqual(f".workline/review/history/relations/{RELATION}.yaml", paths.history_relation_rel(RELATION))
        self.assertEqual(f".workline/review/history/human-decisions/{DECISION}.yaml",
                         paths.history_decision_rel(DECISION))
        self.assertEqual(("runs", "findings", "repairs", "relations", "human-decisions"), paths.HISTORY_FAMILIES)

    def test_each_family_takes_only_its_own_identity_kind(self) -> None:
        for call, value in ((paths.history_run_rel, RELATION), (paths.history_finding_rel, RUN),
                            (paths.history_repair_rel, RUN), (paths.history_relation_rel, "rel_01ARZ3NDEKTSV4RRFFQ69G5FAV"),
                            (paths.history_decision_rel, RELATION), (paths.history_run_rel, "../x")):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                call(value)
        with self.assertRaises(ValidationError):
            paths.history_family_dir("index")

    def test_the_record_path_rule_admits_exactly_history_family_id(self) -> None:
        for family in paths.HISTORY_FAMILIES:
            paths.require_review_record_path(f"{paths.HISTORY_DIR}/{family}/x.yaml")
        for refused in (
            f"{paths.HISTORY_DIR}/x.yaml",
            f"{paths.HISTORY_DIR}/runs/a/b.yaml",
            f"{paths.HISTORY_DIR}/index/x.yaml",
            f"{paths.HISTORY_DIR}/runs/x.json",
            f"{paths.HISTORY_DIR}/runs/../x.yaml",
            f"{paths.REVIEW_DIR}/receipts/nested/x.yaml",
            f"{paths.REVIEW_DIR}/gates/x.yaml",
        ):
            with self.subTest(refused=refused), self.assertRaises(ValidationError):
                paths.require_review_record_path(refused)

    def test_history_is_the_twelfth_closed_namespace_entry(self) -> None:
        # P6 (§30.17) appends ``policy`` after it; history stays the twelfth entry.
        self.assertEqual(13, len(paths.REVIEW_SUBDIRS))
        self.assertEqual("history", paths.REVIEW_SUBDIRS[11])
        self.assertEqual("policy", paths.REVIEW_SUBDIRS[-1])
        self.assertEqual(paths.HISTORY_DIR, f"{paths.REVIEW_DIR}/history")


# --------------------------------------------------------------------------- strict schemas


class SchemaTests(unittest.TestCase):
    def test_every_family_round_trips_canonically(self) -> None:
        for family, found in every_record().items():
            with self.subTest(family=family):
                record = found.to_record()  # type: ignore[attr-defined]
                text = serialize.canonical_text(record)
                data, stored = serialize.parse_canonical(text.encode("utf-8"), family)
                again = history.parse_history(family, data, family)
                self.assertEqual(serialize.canonical_data(record), serialize.canonical_data(again.to_record()))
                self.assertEqual(text, stored)
                self.assertEqual(history.HISTORY_CONTRACT, record["history_contract"])

    def test_every_family_is_strict(self) -> None:
        for family, found in every_record().items():
            base = serialize.canonical_data(found.to_record())  # type: ignore[attr-defined]
            mutations = {
                "unknown field": lambda r: r.update(transcript="the whole chat"),
                "missing field": lambda r: r.pop("history_contract"),
                "other schema": lambda r: r.update(schema="review-p4-adjudication"),
                "other contract": lambda r: r.update(history_contract="review-v1-history-v2"),
            }
            for name, mutate in mutations.items():
                record = dict(base)
                mutate(record)
                with self.subTest(family=family, mutation=name), self.assertRaises(ValidationError):
                    history.parse_history(family, record, name)
            later = {**base, "version": 2}
            with self.subTest(family=family, mutation="later version"), self.assertRaises(ValidationError) as raised:
                history.parse_history(family, later, "later")
            self.assertEqual("review_record_version", raised.exception.code)

    def test_run_summary_vocabulary_and_identities_are_strict(self) -> None:
        base = summary_fixture().to_record()
        for name, change in {
            "unknown disposition": {"durable_disposition": "done"},
            "bad run id": {"review_run_id": RELATION},
            "bad digest": {"gate_digest": "D" * 64},
            "zero generation": {"gate_generation": 0},
            "bool generation": {"candidate_generation": True},
            "duplicate finding": {"finding_ids": ["rfd_01ARZ3NDEKTSV4RRFFQ69G5F10"] * 2},
            "finding of another kind": {"finding_ids": [RUN]},
        }.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                history.RunSummary.from_record({**base, **change}, name)

    def test_each_disposition_has_its_own_shape(self) -> None:
        batch = "rrb_01ARZ3NDEKTSV4RRFFQ69G5FAB"
        valid = {
            "consumed": dict(durable_disposition="consumed", receipt_id=RECEIPT, consumption_id=CONSUMPTION),
            "repaired": dict(durable_disposition="repaired_to_next_candidate", repair_batch_id=batch),
            "human_wait": dict(durable_disposition="human_wait"),
            "invalidated": dict(durable_disposition="invalidated", receipt_id=RECEIPT),
            "not_authorized": dict(durable_disposition="not_authorized", adjudication_digest=None),
            "set_aside": dict(durable_disposition="set_aside", receipt_id=RECEIPT),
        }
        for name, change in valid.items():
            with self.subTest(valid=name):
                found = summary_fixture(**change)
                history.RunSummary.from_record(found.to_record(), name)
        refused = {
            "consumed without receipt": dict(durable_disposition="consumed", consumption_id=CONSUMPTION),
            "consumption on another disposition": dict(durable_disposition="set_aside", consumption_id=CONSUMPTION),
            "consumed with repair": dict(durable_disposition="consumed", receipt_id=RECEIPT, consumption_id=CONSUMPTION,
                                         repair_batch_id=batch),
            "repaired without batch": dict(durable_disposition="repaired_to_next_candidate"),
            "repaired with receipt": dict(durable_disposition="repaired_to_next_candidate", repair_batch_id=batch,
                                          receipt_id=RECEIPT),
            "human_wait without adjudication": dict(durable_disposition="human_wait", adjudication_digest=None),
            "human_wait with receipt": dict(durable_disposition="human_wait", receipt_id=RECEIPT),
            "invalidated without receipt": dict(durable_disposition="invalidated"),
            "not_authorized with receipt": dict(durable_disposition="not_authorized", receipt_id=RECEIPT,
                                                adjudication_digest=None),
            "not_authorized after an adjudication": dict(durable_disposition="not_authorized"),
            "findings without adjudication": dict(durable_disposition="set_aside", adjudication_digest=None,
                                                  finding_ids=("rfd_01ARZ3NDEKTSV4RRFFQ69G5F10",)),
        }
        for name, change in refused.items():
            with self.subTest(refused=name), self.assertRaises(ValidationError):
                history.RunSummary.from_record(summary_fixture(**change).to_record(), name)

    def test_gap_f_the_reserved_vocabulary_is_recognized_and_nothing_produces_it(self) -> None:
        # GAP-F (a): schema vocabulary != a producible source fact. The reader recognizes both reserved values;
        # no builder produces either; source validation refuses a stored one (test_review_history_projection).
        self.assertEqual(("authorized", "historical_escape"), history.DISPOSITIONS_WITHOUT_TRANSITION)
        for disposition_value in history.RUN_DISPOSITIONS:
            with self.subTest(disposition=disposition_value):
                self.assertEqual(disposition_value not in ("authorized", "historical_escape"),
                                 history.disposition_admitted(disposition_value))
        self.assertFalse(history.disposition_admitted("done"))
        self.assertFalse(history.disposition_admitted(None))
        for value in ("authorized", "historical_escape"):
            record = summary_fixture(durable_disposition=value, adjudication_digest=None, receipt_id=RECEIPT).to_record()
            with self.subTest(reader=value):
                self.assertEqual(value, history.RunSummary.from_record(record, value).durable_disposition)
            gate = generation(5, "d" * 64, sealed=True)
            with self.subTest(builder=value), self.assertRaises(ValidationError) as raised:
                history.run_summary(gate, durable_disposition=value, candidate_generation=1, receipt_id=RECEIPT)
            self.assertEqual(history.CODE_DISPOSITION_UNSUPPORTED, raised.exception.code)

    def test_relation_shape(self) -> None:
        history.Relation.from_record(relation_fixture(), "valid")
        source = relation_fixture()["source"]
        work = {"kind": "work", "id": WORK, "basis": "project", "digest": None}
        batch = {"kind": "review_repair_batch", "id": "rrb_01ARZ3NDEKTSV4RRFFQ69G5FAB", "basis": "source",
                 "digest": "6" * 64}
        run = {"kind": "review_run", "id": OTHER_RUN, "basis": "history", "digest": "7" * 64}
        accepted = {
            "future_work_link": dict(relation_type="future_work_link", target=work, semantic_surface=None),
            "repair_induced": dict(relation_type="repair_induced", target=batch),
            "downstream_escape to a run": dict(relation_type="downstream_escape", target=run, semantic_surface=None),
            "unresolved without evidence": dict(status="unresolved", supporting_evidence_digests=[]),
            "insufficient without evidence": dict(status="insufficient_evidence", supporting_evidence_digests=[]),
        }
        for name, change in accepted.items():
            with self.subTest(accepted=name):
                found = history.Relation.from_record(relation_fixture(**change), name)
                self.assertEqual(found.status == "supported", found.confirmed)
        refused = {
            "unknown type": dict(relation_type="related"),
            "unknown status": dict(status="likely"),
            "supported without evidence": dict(supporting_evidence_digests=[]),
            "recurrence without surface": dict(semantic_surface=None),
            "recurrence to a work": dict(target=work),
            "future work to a finding": dict(relation_type="future_work_link"),
            "future work from a run": dict(relation_type="future_work_link", source=run, target=work),
            "self relation": dict(target=source),
            "work on a review basis": dict(relation_type="future_work_link", target={**work, "basis": "history"}),
            "work with a digest": dict(relation_type="future_work_link", target={**work, "digest": "6" * 64}),
            "review record on a project basis": dict(target={**source, "basis": "project"}),
            "unsorted evidence": dict(supporting_evidence_digests=["9" * 64, "3" * 64]),
            "endpoint extra field": dict(target={**batch, "note": "x"}),
            "multi-line rationale": dict(rationale="one\ntwo"),
        }
        for name, change in refused.items():
            with self.subTest(refused=name), self.assertRaises(ValidationError):
                history.Relation.from_record(relation_fixture(**change), name)

    def test_human_decision_evidence_shape(self) -> None:
        base = human_decision_fixture().to_record()
        found = history.HumanDecisionEvidence.from_record(base, "valid")
        # GAP-G: the filename identity is the reserved review_decision ID; the caller's decision is a field.
        self.assertEqual((DECISION, CALLER_DECISION, "requirement_changed"),
                         (found.review_decision_id, found.decision_id, found.decision_disposition))
        self.assertEqual(DECISION, history.record_identity(paths.HISTORY_HUMAN_DECISIONS, found))
        confirmed = human_decision_fixture(changed=False)
        self.assertEqual(((), history.ACTION_RESUME_CONFIRMED), (confirmed.effect_digests, confirmed.action_class))
        entry = base["affected_entries"][0]
        refused = {
            "no reference": dict(affected_entries=[], affected_coverage_gaps=[]),
            "duplicate entry": dict(affected_entries=[entry, entry]),
            "entry extra field": dict(affected_entries=[{**entry, "note": "x"}]),
            "unknown action": dict(action_class="requirement_waived"),
            "action of the other disposition": dict(action_class=history.ACTION_RESUME_CONFIRMED),
            "unknown disposition": dict(decision_disposition="requirement_waived"),
            "evidence identity of another kind": dict(review_decision_id=RELATION),
            "caller decision id not a stable identity": dict(decision_id="the decision of tuesday"),
            "caller decision id missing": dict(decision_id=""),
            "changed without an effect digest": dict(effect_digests=[]),
            "no source digest": dict(source_digests=[]),
            "no authority identity": dict(authority_identity=None),
            "transcript summary": dict(decision_summary="User: yes\nAssistant: ok"),
            "email in a summary": dict(question_summary="ask alice@example.com"),
            "path authority": dict(authority_identity="C:\\Users\\me\\spec.md"),
        }
        for name, change in refused.items():
            with self.subTest(refused=name), self.assertRaises(ValidationError):
                history.HumanDecisionEvidence.from_record({**base, **change}, name)
        gap = {"task_id": TASK_A, "surface": "the error path"}
        found = history.HumanDecisionEvidence.from_record({**base, "affected_coverage_gaps": [gap]}, "gap")
        self.assertEqual((gap,), found.affected_coverage_gaps)

    def test_repair_summary_shape(self) -> None:
        base = every_record()[paths.HISTORY_REPAIRS].to_record()  # type: ignore[attr-defined]
        material = base["causal_material"]
        refused = {
            "no finding": dict(finding_ids=[]),
            "unknown result": dict(durable_result="repaired"),
            "same candidate": dict(result_candidate_hash=base["source_candidate_hash"]),
            "evidence two ways": dict(evidence_reusable_ids=["e1"], evidence_unknown_ids=["e1"]),
            "class on ordinary": dict(strategy_change_class="widen_scope"),
            "material extra field": dict(causal_material={**material, "payload": "bytes"}),
            "material missing field": dict(causal_material={k: v for k, v in material.items() if k != "reverification_digest"}),
        }
        for name, change in refused.items():
            with self.subTest(refused=name), self.assertRaises(ValidationError):
                history.RepairSummary.from_record({**base, **change}, name)


# --------------------------------------------------------------------------- H-3 sanitation


class SanitationTests(unittest.TestCase):
    def test_new_summaries_are_bounded_single_line_public_safe_text(self) -> None:
        self.assertIsNone(history.summary_problem("The limit is 20 for every caller."))
        for value in ("", " padded", "one\ntwo", "tab\there", "x" * 2001, "see C:\\Users\\me\\a.txt",
                      "token=abcdef123456", "ghp_" + "a" * 30, "/home/alice/notes", "write to bob@example.org",
                      "a\N{RIGHT-TO-LEFT OVERRIDE}b", "line\N{LINE SEPARATOR}break", None, 7):
            with self.subTest(value=value):
                self.assertIsNotNone(history.summary_problem(value))

    def test_a_copied_p4_statement_keeps_exactly_p4s_rule_never_a_stricter_one(self) -> None:
        statement = "the notifier mails ops@example.org on every retry"
        self.assertIsNone(records.public_safe_problem(statement))
        found = adjudicate(bound(report(TASK_A, "correctness", [("LOW", "x", "c")])),
                           returned(disposition(TASK_A, 0, p4.OUTCOME_IMPROVEMENT, severity="LOW",
                                                statement=statement)))
        summary = history.finding_summary(found, str(found.findings[0]["finding_id"]))
        self.assertEqual(statement, summary.summary)

    def test_no_field_can_carry_a_transcript_reasoning_secret_or_free_map(self) -> None:
        forbidden = ("transcript", "thought", "reasoning", "deliberation", "prompt", "conversation", "chat", "secret",
                     "credential", "password", "token", "metadata", "extra", "notes", "raw", "payload", "path")
        tuples = {
            "run": history.RUN_SUMMARY_FIELDS, "finding": history.FINDING_SUMMARY_FIELDS,
            "repair": history.REPAIR_SUMMARY_FIELDS, "material": history.CAUSAL_MATERIAL_FIELDS,
            "relation": history.RELATION_FIELDS, "endpoint": history.ENDPOINT_FIELDS,
            "human": history.HUMAN_DECISION_FIELDS, "entry": history.AFFECTED_ENTRY_FIELDS,
            "gap": history.AFFECTED_GAP_FIELDS,
        }
        for name, fields in tuples.items():
            for field in fields:
                with self.subTest(record=name, field=field):
                    self.assertFalse(any(word in field for word in forbidden), field)

    def test_every_mapping_valued_field_has_a_closed_field_set(self) -> None:
        closed = {"causal_material", "source", "target", "affected_entries", "affected_coverage_gaps"}
        for family, found in every_record().items():
            for key, value in found.to_record().items():  # type: ignore[attr-defined]
                is_mapping = isinstance(value, dict) or (isinstance(value, list) and value and isinstance(value[0], dict))
                if is_mapping:
                    with self.subTest(family=family, field=key):
                        self.assertIn(key, closed)

    def test_no_candidate_payload_byte_is_copied_into_history(self) -> None:
        repair = adjudication_fixture()
        batch = batch_fixture(repair, serialize.digest(repair.to_record()))
        snapshot_text = serialize.canonical_text(snapshot().to_record())
        found = history.repair_summary(repair, batch, result_fixture(batch),
                                       source_candidate_material_digest=serialize.digest_of_text(snapshot_text))
        text = serialize.canonical_text(found.to_record())
        self.assertNotIn("the exact Work snapshot payload", text)
        self.assertIn(serialize.digest_of_text(snapshot_text), text, "the snapshot is referenced by its digest")


# --------------------------------------------------------------------------- store readers and structural checks


class StoreTests(HistoryCase):
    def test_every_family_reads_by_its_identity(self) -> None:
        for family, found in every_record().items():
            identifier = history.record_identity(family, found)
            self.put_history(family, found)
            with self.subTest(family=family):
                self.assertEqual(found, self.review.read_history(family, identifier))
                self.assertEqual((identifier,), self.review.history_ids(family))
                self.assertTrue(self.review.history_exists(family, identifier))
                self.assertEqual(serialize.digest(found.to_record()), self.review.history_digest(family, identifier))  # type: ignore[attr-defined]
        named = {
            paths.HISTORY_RUNS: (self.review.run_history, self.review.run_history_ids),
            paths.HISTORY_FINDINGS: (self.review.finding_history, self.review.finding_history_ids),
            paths.HISTORY_REPAIRS: (self.review.repair_history, self.review.repair_history_ids),
            paths.HISTORY_RELATIONS: (self.review.relation_history, self.review.relation_history_ids),
            paths.HISTORY_HUMAN_DECISIONS: (self.review.human_decision_history, self.review.human_decision_history_ids),
        }
        for family, (read, list_ids) in named.items():
            with self.subTest(named=family):
                (identifier,) = list_ids()
                self.assertEqual(self.review.read_history(family, identifier), read(identifier))

    def test_a_record_under_another_identity_is_refused(self) -> None:
        found = summary_fixture()
        self.put_history(paths.HISTORY_RUNS, found, identifier=OTHER_RUN)
        with self.assertRaises(ValidationError) as raised:
            self.review.run_history(OTHER_RUN)
        self.assertEqual("review_record_invalid", raised.exception.code)
        self.assertIn("review_record_invalid", self.codes())

    def test_noncanonical_bytes_are_refused(self) -> None:
        relative = paths.history_run_rel(RUN)
        self.put(relative, raw=serialize.canonical_bytes(summary_fixture().to_record()).replace(b"\n", b"\r\n"))
        with self.assertRaises(ValidationError) as raised:
            self.review.run_history(RUN)
        self.assertEqual("review_record_noncanonical", raised.exception.code)

    def test_a_pre_p5_namespace_without_history_is_valid_and_holds_none(self) -> None:
        self.put_chain(chain(2))
        self.assertEqual([], self.codes())
        for family in paths.HISTORY_FAMILIES:
            self.assertEqual((), self.review.history_ids(family))
        self.assertEqual([], history.history_problems(self.review, work_ids=None))
        self.assertEqual((), history.load_history(self.review).problems)

    def test_a_valid_orphan_history_record_is_structurally_valid_and_its_source_is_reported_missing(self) -> None:
        self.put_history(paths.HISTORY_RUNS, summary_fixture())
        self.assertEqual([], self.codes(), "structural validation never reads the source")
        self.assertIn(history.PROBLEM_MISSING, [code for code, _ in history.history_problems(self.review, work_ids=None)])

    def test_the_history_tree_is_closed(self) -> None:
        cases = {
            "unknown family": (f"{paths.HISTORY_DIR}/index/x.yaml", "review_namespace_invalid"),
            "file in history": (f"{paths.HISTORY_DIR}/index.yaml", "review_namespace_invalid"),
            "nested in a family": (f"{paths.HISTORY_DIR}/runs/nested/x.yaml", "review_namespace_invalid"),
            "foreign name in a family": (f"{paths.HISTORY_DIR}/runs/{RELATION}.yaml", "review_namespace_invalid"),
            "non-record in a family": (f"{paths.HISTORY_DIR}/runs/notes.txt", "review_namespace_invalid"),
        }
        for name, (relative, code) in cases.items():
            with self.subTest(name):
                rmtree(self.root / ".workline")
                self.put(relative, raw=b"schema: x\n")
                self.assertIn(code, self.codes())
                with self.assertRaises(StopError) as raised:
                    checkout.require_namespace_readable(self.store)
                self.assertEqual("review_namespace_unreadable", raised.exception.code)

    def test_a_history_file_where_the_namespace_directory_belongs_is_refused(self) -> None:
        self.put(f"{paths.REVIEW_DIR}/history", raw=b"x\n")
        self.assertEqual(["review_namespace_invalid"], self.codes())

    def test_a_malformed_record_is_a_structural_problem_everywhere(self) -> None:
        for name, record in {
            "unknown disposition": {**summary_fixture().to_record(), "durable_disposition": "done"},
            "unknown field": {**summary_fixture().to_record(), "reasoning": "because"},
            "later version": {**summary_fixture().to_record(), "version": 2},
        }.items():
            with self.subTest(name):
                rmtree(self.root / ".workline")
                self.put(paths.history_run_rel(RUN), record)
                self.assertTrue(self.codes())
                with self.assertRaises(StopError) as raised:
                    checkout.require_namespace_readable(self.store)
                self.assertEqual("review_namespace_unreadable", raised.exception.code)

    def test_gap_f_a_reserved_disposition_is_structurally_readable_and_refused_only_by_source_validation(self) -> None:
        # GAP-B / GAP-F: the shared readers recognize the vocabulary; only the cross-source check refuses it.
        for value in history.DISPOSITIONS_WITHOUT_TRANSITION:
            with self.subTest(value):
                rmtree(self.root / ".workline")
                self.put_history(paths.HISTORY_RUNS, summary_fixture(durable_disposition=value, adjudication_digest=None,
                                                                     receipt_id=RECEIPT))
                self.assertEqual([], self.codes())
                checkout.require_namespace_readable(self.store)
                work_checkout._read_every_record(self.review, [paths.history_run_rel(RUN)])
                self.assertIn(history.CODE_DISPOSITION_UNSUPPORTED,
                              [code for code, _ in history.history_problems(self.review, work_ids=None)])

    def test_valid_history_reads_through_the_closed_namespace_readers(self) -> None:
        written = [self.put_history(family, found) for family, found in every_record().items()]
        checkout.require_namespace_readable(self.store)
        work_checkout._read_every_record(self.review, written)
        self.assertEqual([], self.codes())

    def test_the_resulting_tree_reader_refuses_a_history_path_no_family_reads(self) -> None:
        # Never skipped (P-12 of P4): an unknown family or an extra level is refused by the reader itself; a
        # filename of the wrong identity kind is the strict reader's refusal, which the capability turns unsafe.
        for relative, code in (
            (f"{paths.HISTORY_DIR}/index/x.yaml", "review_checkout_unsafe"),
            (f"{paths.HISTORY_DIR}/runs/a/b.yaml", "review_checkout_unsafe"),
            (f"{paths.HISTORY_DIR}/runs/{RELATION}.yaml", "review_record_invalid"),
        ):
            with self.subTest(relative=relative):
                with self.assertRaises(StopError) as raised:
                    work_checkout._read_every_record(self.review, [relative])
                self.assertEqual(code, raised.exception.code)

    def test_the_store_gains_readers_only(self) -> None:
        for name in vars(ReviewStore):
            if "history" in name:
                with self.subTest(name=name):
                    self.assertFalse(any(word in name for word in ("write", "create", "put", "save", "delete")))


class CreateOnlyTests(WorklineTestCase):
    @CREATE_ONLY
    def test_a_history_record_is_immutable_create_only(self) -> None:
        store = self.new_project()
        lock = project_operation(store, "p5-history-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        found = summary_fixture()
        relative = paths.history_run_rel(RUN)
        controller = MutationController(store)
        first = controller.open("start", {"operation": "p5-test", "n": 1}, WriteScope(files=(relative,)))
        first.add_effects("review", [Effect.create_file(relative, serialize.canonical_text(found.to_record()))])
        first.apply()
        self.assertEqual([MATCHING], [classification for _, classification in first.apply()])
        first.complete()
        other = summary_fixture(gate_digest="e" * 64)
        clash = controller.open("start", {"operation": "p5-test", "n": 2}, WriteScope(files=(relative,)))
        clash.add_effects("review", [Effect.create_file(relative, serialize.canonical_text(other.to_record()))])
        with self.assertRaises(ReconcileRequired):
            clash.apply()
        self.assertEqual(serialize.canonical_bytes(found.to_record()), (store.root / relative).read_bytes())
        self.assertEqual(found, ReviewStore(store).run_history(RUN))


if __name__ == "__main__":
    unittest.main()
