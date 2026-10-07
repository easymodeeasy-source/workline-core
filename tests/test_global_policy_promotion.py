"""P7 Global promotion and correlation (``WORKLINE_COMPLETION_SPRINT`` §31.14-§31.23, §31.51; §16.28 rows), RB7-C.

Unit level over the inert core :mod:`workline.review.global_policy`:

* the request is explicit, finite and path-free; an unknown or non-adaptive surface is refused - adaptive promotion
  never creates a new meta-policy surface;
* a source snapshot reads only the records its evidence names (no crawl, no write), proves each by digest, and keeps
  H-3 facts only; its B0/B1 witness ignores unrelated HEAD movement and catches changed evidence;
* independence is positive evidence only: fork / template / same-incident / same-implementation / causal dependency /
  duplicate observation correlate; absence of known correlation is never independence; unresolved independence
  does not count and needs no HUMAN;
* eligibility: one Project (many Runs) never qualifies; >1 lineage and >=2 mutually proven-independent clusters for
  strengthen; >=3 / >=3 and representative opportunities that exercised the stronger pre-change setting for lighten
  (an unknown setting never counts), decided by the movement; an unexercised source is excluded; a Project-specific
  mechanism is refused;
* the Promotion Packet re-derives every part and is evidence, never authorization;
* :class:`EvaluationRecordTests`: the pure Global evaluation record and post-change independence (§31.41-§31.43);
  :class:`ExactRollbackTests` (§31.20); :class:`ActiveGlobalExperimentTests` (§16.10).

The in-memory fixtures here are RB7-C's own; the other RB7-C test files import them. Every Candidate binds the real
root family policy hash (``p4.family_policy_hash(p4.ROOT_POLICY_ID)``, IR-RB7-2): nothing is stubbed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
from typing import Any
import unittest

from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.review import global_policy as gp
from workline.review import namespace, p4, policy, serialize

SLOTS = policy.SURFACE_REQUIRED_SLOTS
STEPS = policy.SURFACE_EXTRA_SCOPE_STEPS
RUNS, FINDINGS, RELATIONS, DECISIONS = (namespace.HISTORY_RUNS, namespace.HISTORY_FINDINGS, namespace.HISTORY_RELATIONS,
                                        namespace.HISTORY_HUMAN_DECISIONS)
HEAD = "a" * 40
MECH = "discovery.second-reviewer.contract-drift"
ENV = {"reviewers": ["reviewer-a 1"], "check_adapters": ["pytest"], "toolchain": "py3.12", "dependencies": []}
PACKET_ID = "rpp_" + "1" * 26
CHANGE_ID = "rgc_" + "1" * 26
EVALUATION_ID = "rge_" + "1" * 26
RUN_ID = "rr_" + "7" * 26
RECEIPT_ID = "rcp_" + "7" * 26
SECRET_ROOT = Path(tempfile.gettempdir()) / "private-checkout-of-alpha"


def ident(prefix: str, number: int) -> str:
    return f"{prefix}_{number:026d}"


def digest_of(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- Global policies

V1 = policy.global_policy_record(1, None, {SLOTS: 1, STEPS: 0})


def successor(before: dict[str, Any], **settings: int) -> dict[str, Any]:
    named = {SLOTS: settings.get("slots", policy.global_policy_settings(before)[SLOTS]),
             STEPS: settings.get("steps", policy.global_policy_settings(before)[STEPS])}
    return policy.global_policy_record(before["global_policy_version"] + 1, policy.global_policy_digest(before), named)


V2_SLOTS3 = successor(V1, slots=3)


# --------------------------------------------------------------------------- evidence references

def provenance(n: int, **overrides: Any) -> dict[str, Any]:
    """Positive, distinct structured provenance for source ``n`` (each fact overridable)."""
    found = {
        "kind": gp.REF_PROVENANCE,
        "lineage": digest_of("lineage", n),
        "copy_sources": [],
        "incidents": [digest_of("incident", n)],
        "implementations": [digest_of("implementation", n)],
        "dependencies": [],
        "mechanism": MECH,
        "environment": dict(ENV),
    }
    found.update(overrides)
    return found


def record_ref(family: str, identifier: str, digest: str) -> dict[str, Any]:
    return {"kind": gp.REF_RECORD, "family": family, "id": identifier, "digest": digest}


def snapshot(source_id: str, n: int, *, runs: int = 2, surface: str = SLOTS, global_changes: tuple[str, ...] = (),
             ran_under: Any = None, human: tuple[str, ...] = (), semantic: tuple[str, ...] = (),
             records: list[dict[str, Any]] | None = None, **provenance_overrides: Any) -> dict[str, Any]:
    """A canonical source snapshot built directly (what :func:`gp.source_snapshot` would extract).

    ``ran_under``: the ``(Global policy version, effective setting)`` every Run froze, a list of one per Run, or
    ``None`` - the Runs froze no Effective Policy (unknown).
    """
    if records is None:
        records = [{"family": RUNS, "id": ident("rr", n * 100 + index), "digest": digest_of(source_id, index)}
                   for index in range(1, runs + 1)]
    runs_of = [item for item in records if item["family"] == RUNS]
    under = list(ran_under) if isinstance(ran_under, list) else [ran_under] * len(runs_of)
    entries = [{"review_run_id": item["id"], "global_policy_version": None if frozen is None else frozen[0],
                "setting": None if frozen is None else frozen[1], "global_changes": sorted(global_changes)}
               for item, frozen in zip(runs_of, under)]
    prov = provenance(n, **provenance_overrides)
    prov.pop("kind")
    found = {
        serialize.SCHEMA_KEY: gp.SCHEMA_SOURCE_SNAPSHOT, serialize.VERSION_KEY: gp.RECORD_VERSION,
        "source_id": source_id, "head": HEAD, "provenance": gp._normal_ref({"kind": "provenance", **prov}),
        "records": sorted(records, key=lambda item: (item["family"], item["id"])),
        "opportunities": {SLOTS: entries if surface == SLOTS else [], STEPS: entries if surface == STEPS else []},
        "escapes": [], "local_outcomes": [], "semantic_surfaces": sorted(semantic), "unresolved_human": sorted(human),
        "profile": None,
    }
    found["provenance"].pop("kind")
    return gp.parse_source_snapshot(found, f"the snapshot of {source_id}")


def evidence_of(found: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """The request evidence that names exactly ``found``'s provenance and records."""
    return tuple([{"kind": gp.REF_PROVENANCE, **found["provenance"]}]
                 + [record_ref(item["family"], item["id"], item["digest"]) for item in found["records"]])


MEASUREMENT = {"version": "m1", "metric": "supported Problems found per relevant Run",
               "success_criteria": "more supported Problems per relevant Run",
               "minimum_opportunities": 2, "minimum_clusters": 2, "continued_observation_permitted": True}


def change_request(snapshots: list[dict[str, Any]], *, surface: str = SLOTS, direction: str = "strengthen",
                   after: int = 2, mechanism: str = MECH, rollback_of: str | None = None,
                   rollback_evaluation_id: str | None = None, measurement: dict[str, Any] | None = None,
                   summary: str = "a second independent reviewer catches contract drift a single reviewer misses",
                   ) -> gp.GlobalPolicyChangeRequest:
    return gp.GlobalPolicyChangeRequest(
        policy_surface_id=surface, direction=direction, after_setting=after, generalized_mechanism_id=mechanism,
        summary=summary, expected_effect="fewer contract-drift escapes per relevant Run",
        measurement_contract=dict(measurement or MEASUREMENT),
        rollback_contract={"threshold": "no extra supported Problem after ten relevant Runs"},
        sources=tuple(gp.SourceProject(item["source_id"], SECRET_ROOT / item["source_id"]) for item in snapshots),
        evidence={item["source_id"]: evidence_of(item) for item in snapshots},
        rollback_of=rollback_of, rollback_evaluation_id=rollback_evaluation_id,
    )


def two_independent() -> list[dict[str, Any]]:
    return [snapshot("alpha", 1), snapshot("beta", 2)]


def three_independent(runs: int = 2, ran_under: Any = (2, 3)) -> list[dict[str, Any]]:
    """Three mutually independent sources whose Runs exercised ``ran_under`` (default: required slots 3, Global v2)."""
    return [snapshot("alpha", 1, runs=runs, ran_under=ran_under), snapshot("beta", 2, runs=runs, ran_under=ran_under),
            snapshot("gamma", 3, runs=runs, ran_under=ran_under)]


def candidate_for(before: dict[str, Any], request: gp.GlobalPolicyChangeRequest, snapshots: list[dict[str, Any]],
                  *, change_id: str = CHANGE_ID) -> dict[str, Any]:
    """The full pure pipeline: request -> clusters -> eligibility -> after -> proof -> Packet -> Candidate."""
    record = gp.request_record(request)
    clusters = gp.clustering(snapshots)
    found = gp.eligibility(record, snapshots, clusters)
    after = gp.after_global_policy(before, record)
    proof = gp.compatibility_proof(before, after)
    packet = gp.promotion_packet(record, promotion_packet_id=PACKET_ID, global_policy_change_id=change_id,
                                 before_global=before, after_global=after, snapshots=snapshots, clusters=clusters,
                                 eligibility=found, proof=proof)
    return gp.candidate_material(packet, before, after, proof)


def applied_change(test: unittest.TestCase, before: dict[str, Any] = V1, **request: Any) -> dict[str, Any]:
    """The stored change record of an authorized strengthen of ``before`` (required slots 1 -> 2 by default)."""
    material = candidate_for(before, change_request(two_independent(), **request), two_independent())
    return gp.change_record(material, review_run_id=RUN_ID, receipt_id=RECEIPT_ID)


# --------------------------------------------------------------------------- an in-memory committed source reader

class SourceReader:
    """One source Project's committed Review records, read-only; every call is recorded (no crawl, no write)."""

    def __init__(self, source_id: str) -> None:
        self.source_id = source_id
        self.history: dict[tuple[str, str], Any] = {}
        self.changes: dict[str, dict[str, Any]] = {}
        self.evaluations: dict[str, dict[str, Any]] = {}
        self.profile: Any = None
        self.calls: list[str] = []

    # the reader (exactly what the core may call)
    def read_history(self, family: str, identifier: str) -> Any:
        self.calls.append("read_history")
        try:
            return self.history[(family, identifier)]
        except KeyError:
            raise ValidationError(f"{family}/{identifier} is not stored", code="review_record_missing") from None

    def history_digest(self, family: str, identifier: str) -> str:
        self.calls.append("history_digest")
        if (family, identifier) not in self.history:
            raise ValidationError(f"{family}/{identifier} is not stored", code="review_record_missing")
        return digest_of(self.source_id, family, identifier)

    def policy_change_digest(self, change_id: str) -> str:
        self.calls.append("policy_change_digest")
        if change_id not in self.changes:
            raise ValidationError(f"{change_id} is not stored", code="review_record_missing")
        return digest_of(self.source_id, "change", change_id)

    def read_policy_change(self, change_id: str) -> dict[str, Any]:
        self.calls.append("read_policy_change")
        return self.changes[change_id]

    def policy_evaluation_digest(self, evaluation_id: str) -> str:
        self.calls.append("policy_evaluation_digest")
        if evaluation_id not in self.evaluations:
            raise ValidationError(f"{evaluation_id} is not stored", code="review_record_missing")
        return digest_of(self.source_id, "evaluation", evaluation_id)

    def read_policy_evaluation(self, evaluation_id: str) -> dict[str, Any]:
        self.calls.append("read_policy_evaluation")
        return self.evaluations[evaluation_id]

    def read_profile(self) -> Any:
        self.calls.append("read_profile")
        return self.profile

    def gate_chain(self, review_run_id: str) -> Any:
        self.calls.append("gate_chain")
        return None

    # stored facts
    def ref(self, family: str, identifier: str) -> dict[str, Any]:
        return record_ref(family, identifier, digest_of(self.source_id, family, identifier))

    def run(self, number: int, *, generation: int = 2, disposition: str = "consumed") -> dict[str, Any]:
        run_id = ident("rr", number)
        self.history[(RUNS, run_id)] = SimpleNamespace(review_run_id=run_id, gate_generation=generation,
                                                       durable_disposition=disposition)
        return self.ref(RUNS, run_id)

    def finding(self, number: int, run: int, *, surface: str = "contract checks", severity: str = "HIGH") -> dict[str, Any]:
        finding_id = ident("rfd", number)
        self.history[(FINDINGS, finding_id)] = SimpleNamespace(
            finding_id=finding_id, review_run_id=ident("rr", run), severity=severity, category="Problem",
            semantic_surface=surface)
        return self.ref(FINDINGS, finding_id)

    def relation(self, number: int, run: int, *, confirmed: bool = True,
                 relation_type: str = "downstream_escape") -> dict[str, Any]:
        relation_id = ident("rhr", number)
        self.history[(RELATIONS, relation_id)] = SimpleNamespace(
            relation_id=relation_id, relation_type=relation_type, confirmed=confirmed, semantic_surface=None,
            target=SimpleNamespace(kind="review_run", id=ident("rr", run)))
        return self.ref(RELATIONS, relation_id)

    def decision(self, number: int, run: int) -> dict[str, Any]:
        decision_id = ident("rhd", number)
        self.history[(DECISIONS, decision_id)] = SimpleNamespace(review_decision_id=decision_id,
                                                                 affected_review_run_id=ident("rr", run))
        return self.ref(DECISIONS, decision_id)


# =========================================================================== the request (§31.14)

class RequestTests(unittest.TestCase):
    def test_the_request_is_canonical_explicit_and_path_free(self) -> None:
        snapshots = two_independent()
        record = gp.request_record(change_request(snapshots))
        text = serialize.canonical_text(record)
        self.assertNotIn(str(SECRET_ROOT), text)
        self.assertNotIn("private-checkout", text, "a source root is read-only input and never persisted")
        self.assertEqual(["alpha", "beta"], record["sources"])
        self.assertEqual(gp.SCHEMA_CHANGE_REQUEST, record[serialize.SCHEMA_KEY])
        reordered = change_request(list(reversed(snapshots)))
        reordered = gp.GlobalPolicyChangeRequest(**{**reordered.__dict__, "evidence": {
            key: tuple(reversed(value)) for key, value in reordered.evidence.items()}})
        self.assertEqual(record, gp.request_record(reordered), "one request has one canonical form and one identity")
        identity = gp.operation_identity(gp.request_digest(record))
        self.assertEqual(f"global-policy-change:{gp.request_digest(record)}", identity)

    def test_unknown_or_non_adaptive_surfaces_are_refused_and_no_surface_is_created(self) -> None:
        for surface in ("review.discovery.reviewer_count", "review.lifecycle.completion", "review.self_hosting.enabled",
                        "review.severity.blocking_rule", "global.git.force_push"):
            with self.subTest(surface=surface):
                with self.assertRaises(StopError) as raised:
                    gp.request_record(change_request(two_independent(), surface=surface))
                self.assertEqual(gp.CODE_SURFACE_REFUSED, raised.exception.code)
        self.assertEqual(2, len(policy.SURFACES), "adaptive promotion never adds a surface")

    def test_malformed_requests_are_refused_before_anything_is_read(self) -> None:
        snapshots = two_independent()
        good = change_request(snapshots)
        provenance_ref = dict(good.evidence["alpha"][0])

        def variant(**changes: Any) -> gp.GlobalPolicyChangeRequest:
            return gp.GlobalPolicyChangeRequest(**{**good.__dict__, **changes})

        cases = {
            "direction": variant(direction="tighten"),
            "range": variant(after_setting=5),
            "mechanism shape": variant(generalized_mechanism_id="Contract Drift"),
            "absolute path in text": variant(summary="see C:\\Users\\dev\\alpha\\notes.txt for the incident"),
            "credential in text": variant(expected_effect="token: ghp_abcdefghijklmnopqrstuvwxyz0123"),
            "measurement shape": variant(measurement_contract={**MEASUREMENT, "minimum_clusters": 0}),
            "rollback shape": variant(rollback_contract={"threshold": "x", "unit": "y"}),
            "duplicate source": variant(sources=(good.sources[0], good.sources[0])),
            "evidence keys": variant(evidence={"alpha": good.evidence["alpha"]}),
            "two provenances": variant(evidence={**good.evidence, "alpha": good.evidence["alpha"] + (provenance_ref,)}),
            "duplicate record": variant(evidence={**good.evidence, "alpha": good.evidence["alpha"]
                                                  + (good.evidence["alpha"][1],)}),
            "path as lineage": variant(evidence={**good.evidence, "alpha": (
                {**provenance_ref, "lineage": "/home/dev/alpha"},) + good.evidence["alpha"][1:]}),
            "source label": variant(sources=(gp.SourceProject("Alpha Project", SECRET_ROOT),) + good.sources[1:]),
            "no root": variant(sources=(gp.SourceProject("alpha", "C:/alpha"),) + good.sources[1:]),  # type: ignore
            "exception half": variant(direction="rollback", rollback_of=CHANGE_ID),
            "exception on strengthen": variant(rollback_of=CHANGE_ID, rollback_evaluation_id=EVALUATION_ID),
            "no source": variant(sources=(), evidence={}),
            "too many sources": variant(
                sources=tuple(gp.SourceProject(f"s{index}", SECRET_ROOT) for index in range(gp.MAX_SOURCES + 1)),
                evidence={f"s{index}": good.evidence["alpha"] for index in range(gp.MAX_SOURCES + 1)}),
        }
        for name, request in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(StopError) as raised:
                    gp.request_record(request)
                self.assertEqual(gp.CODE_REQUEST_INVALID, raised.exception.code)
        with self.assertRaises(StopError):
            gp.request_record(object())  # type: ignore[arg-type]

    def test_the_exact_rollback_exception_alone_needs_no_source(self) -> None:
        record = gp.request_record(change_request([], direction="rollback", after=1, rollback_of=CHANGE_ID,
                                                  rollback_evaluation_id=EVALUATION_ID))
        self.assertEqual([], record["sources"])


# =========================================================================== source snapshots (§31.15-§31.16)

class SourceSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reader = SourceReader("alpha")
        self.refs = [self.reader.run(1), self.reader.run(2), self.reader.finding(3, 1)]
        self.evidence = (provenance(1),) + tuple(self.refs)

    def test_only_the_named_records_are_read_and_nothing_is_listed_or_written(self) -> None:
        found = gp.source_snapshot("alpha", self.reader, HEAD, self.evidence)
        self.assertEqual(sorted((ref["family"], ref["id"]) for ref in self.refs),
                         [(item["family"], item["id"]) for item in found["records"]])
        allowed = {"read_history", "history_digest", "read_profile", "gate_chain", "policy_change_digest",
                   "read_policy_change", "policy_evaluation_digest", "read_policy_evaluation"}
        self.assertLessEqual(set(self.reader.calls), allowed, "no listing, crawl or write: explicit reads only")
        self.assertFalse(any(call.endswith("_ids") for call in self.reader.calls))

    def test_a_snapshot_is_h3_facts_and_digests_only(self) -> None:
        found = gp.source_snapshot("alpha", self.reader, HEAD, self.evidence)
        text = serialize.canonical_text(found)
        self.assertNotIn(str(SECRET_ROOT), text)
        self.assertEqual([ident("rr", 1), ident("rr", 2)],
                         [entry["review_run_id"] for entry in found["opportunities"][SLOTS]])
        self.assertEqual(["contract checks"], found["semantic_surfaces"])
        self.assertEqual(HEAD, found["head"])

    def test_evidence_the_source_does_not_hold_exactly_is_refused(self) -> None:
        wrong_digest = dict(self.refs[0], digest=digest_of("other"))
        missing = record_ref(RUNS, ident("rr", 99), digest_of("x"))
        for name, evidence in (("digest", (provenance(1), wrong_digest)), ("missing", (provenance(1), missing))):
            with self.subTest(case=name):
                with self.assertRaises(StopError) as raised:
                    gp.source_snapshot("alpha", self.reader, HEAD, evidence)
                self.assertEqual(gp.CODE_SOURCE_INVALID, raised.exception.code)
        with self.assertRaises(StopError) as raised:
            gp.source_snapshot("alpha", self.reader, "HEAD", self.evidence)
        self.assertEqual(gp.CODE_SOURCE_INVALID, raised.exception.code)

    def test_an_unexercised_run_is_no_relevant_opportunity(self) -> None:
        reader = SourceReader("beta")
        evidence = (provenance(2), reader.run(5, generation=1))
        found = gp.source_snapshot("beta", reader, HEAD, evidence)
        self.assertEqual([], found["opportunities"][SLOTS], "discovery never settled: the surface was not exercised")

    def test_an_unresolved_human_boundary_is_witnessed_until_decided(self) -> None:
        reader = SourceReader("gamma")
        waiting = reader.run(7, disposition=gp._P5_HUMAN_WAIT)
        found = gp.source_snapshot("gamma", reader, HEAD, (provenance(3), waiting))
        self.assertEqual([ident("rr", 7)], found["unresolved_human"])
        decided = gp.source_snapshot("gamma", reader, HEAD, (provenance(3), waiting, reader.decision(8, 7)))
        self.assertEqual([], decided["unresolved_human"])

    def test_only_supported_relations_are_escape_evidence(self) -> None:
        refs = (provenance(1), self.reader.relation(4, 1), self.reader.relation(5, 2, confirmed=False))
        found = gp.source_snapshot("alpha", self.reader, HEAD, refs)
        self.assertEqual([ident("rhr", 4)], [item["id"] for item in found["escapes"]])

    def test_project_local_policy_outcomes_are_cited_by_digest_and_are_no_opportunity(self) -> None:
        change_id, evaluation_id = ident("rpc", 1), ident("rpe", 1)
        self.reader.changes[change_id] = {"affected_policy_surface": SLOTS, "direction": "strengthen",
                                          "before_setting": 1, "after_setting": 2}
        self.reader.evaluations[evaluation_id] = {"policy_change_id": change_id, "result": "retain",
                                                  "next_action": "end_observation"}
        refs = (provenance(1), record_ref(gp.FAMILY_POLICY_CHANGES, change_id, digest_of("alpha", "change", change_id)),
                record_ref(gp.FAMILY_POLICY_EVALUATIONS, evaluation_id,
                           digest_of("alpha", "evaluation", evaluation_id)))
        found = gp.source_snapshot("alpha", self.reader, HEAD, refs)
        self.assertEqual([(gp.FAMILY_POLICY_CHANGES, SLOTS, 2), (gp.FAMILY_POLICY_EVALUATIONS, None, None)],
                         [(item["family"], item.get("policy_surface_id"), item.get("after_setting"))
                          for item in found["local_outcomes"]])
        self.assertEqual({SLOTS: [], STEPS: []}, found["opportunities"])

    def test_an_opportunity_records_the_effective_setting_its_run_froze(self) -> None:
        baseline = policy.parse_baseline(policy.materialized_baseline_record(V1, (), ()), "the baseline")
        overridden = policy.ProjectProfile(
            profile_version=1, parent_profile_digest=None, global_baseline_digest=digest_of("baseline"),
            global_baseline_version=1, loader_semantics_identity=policy.LOADER_SEMANTICS_IDENTITY,
            overrides=({"policy_surface_id": SLOTS, "strength_class": "default", "setting": 3,
                        "direction": "strengthen", "supporting_policy_change_id": ident("rpc", 1)},),
            active_experiment_refs=())
        reader = SourceReader("delta")
        ref = reader.run(9)
        envelope = {serialize.SCHEMA_KEY: p4.SCHEMA_DISCOVERY_REQUEST, "policy_id": p4.P6_POLICY_ID,
                    policy.EFFECTIVE_POLICY_KEY: policy.effective_policy_record(baseline, overridden, ()),
                    policy.DISCOVERY_ROLE_KEY: policy.ROLE_REQUIRED}
        reader.gate_chain = lambda run_id: SimpleNamespace(  # type: ignore[method-assign]
            review_run_id=run_id, generations=[SimpleNamespace(accepted_tasks=[{"task_id": run_id}])])
        reader.read_task_input = lambda task_id: SimpleNamespace(request_envelope=envelope)  # type: ignore[attr-defined]
        found = gp.source_snapshot("delta", reader, HEAD, (provenance(4), ref))
        self.assertEqual({"review_run_id": ident("rr", 9), "global_policy_version": 1, "setting": 3,
                          "global_changes": []}, found["opportunities"][SLOTS][0],
                         "the Project overlay the Run exercised, not the Global default")
        unknown = gp.source_snapshot("alpha", self.reader, HEAD, self.evidence)
        self.assertEqual({None}, {entry["setting"] for entry in unknown["opportunities"][SLOTS]})

    def test_a_malformed_opportunity_does_not_read(self) -> None:
        found = snapshot("alpha", 1, ran_under=(2, 3))
        entry = found["opportunities"][SLOTS][0]
        for name, bad in (("version without setting", {**entry, "setting": None}),
                          ("setting without version", {**entry, "global_policy_version": None}),
                          ("setting out of range", {**entry, "setting": 9}),
                          ("no setting field", {key: value for key, value in entry.items() if key != "setting"})):
            with self.subTest(case=name):
                opportunities = {**found["opportunities"], SLOTS: [bad] + found["opportunities"][SLOTS][1:]}
                with self.assertRaises(ValidationError):
                    gp.parse_source_snapshot({**found, "opportunities": opportunities}, "the snapshot")

    def test_escapes_and_local_outcomes_have_one_canonical_form(self) -> None:
        refs = (provenance(1), self.reader.relation(4, 1), self.reader.relation(5, 2))
        found = gp.source_snapshot("alpha", self.reader, HEAD, refs)
        self.assertEqual([ident("rhr", 4), ident("rhr", 5)], [item["id"] for item in found["escapes"]])
        for name, escapes in (("reordered", list(reversed(found["escapes"]))),
                              ("duplicated", found["escapes"] + found["escapes"][:1])):
            with self.subTest(case=name):
                with self.assertRaises(ValidationError):
                    gp.parse_source_snapshot({**found, "escapes": escapes}, "the snapshot")

    def test_b0_b1_witness_ignores_unrelated_head_movement_and_catches_changed_evidence(self) -> None:
        bound = gp.source_witness(gp.source_snapshot("alpha", self.reader, HEAD, self.evidence))
        moved = gp.source_witness(gp.source_snapshot("alpha", self.reader, "b" * 40, self.evidence))
        self.assertIsNone(gp.witness_problem(bound, moved))
        self.reader.profile = SimpleNamespace(profile_version=1, digest=digest_of("profile"))
        changed = gp.source_witness(gp.source_snapshot("alpha", self.reader, "b" * 40, self.evidence))
        self.assertIn("Profile", gp.witness_problem(bound, changed) or "")
        fewer = gp.source_witness(gp.source_snapshot("alpha", self.reader, HEAD, self.evidence[:-1]))
        self.assertIn("evidence", gp.witness_problem(bound, fewer) or "")

    def test_a_post_change_run_is_witnessed_by_the_global_experiment_it_froze(self) -> None:
        baseline = policy.parse_baseline(
            policy.materialized_baseline_record(successor(V1, slots=2), (), ()), "the baseline")
        active = (policy.ActiveExperiment(CHANGE_ID, SLOTS, "strengthen", None, origin=policy.ORIGIN_GLOBAL),)
        effective = policy.effective_policy_record(baseline, None, active)
        reader = SourceReader("delta")
        ref = reader.run(9)
        envelope = {serialize.SCHEMA_KEY: p4.SCHEMA_DISCOVERY_REQUEST, "policy_id": p4.P6_POLICY_ID,
                    policy.EFFECTIVE_POLICY_KEY: effective, policy.DISCOVERY_ROLE_KEY: policy.ROLE_REQUIRED}
        reader.gate_chain = lambda run_id: SimpleNamespace(  # type: ignore[method-assign]
            review_run_id=run_id, generations=[SimpleNamespace(accepted_tasks=[{"task_id": run_id}])])
        reader.read_task_input = lambda task_id: SimpleNamespace(request_envelope=envelope)  # type: ignore[attr-defined]
        found = gp.source_snapshot("delta", reader, HEAD, (provenance(4), ref))
        self.assertEqual([CHANGE_ID], found["opportunities"][SLOTS][0]["global_changes"])
        self.assertEqual((2, 2), (found["opportunities"][SLOTS][0]["global_policy_version"],
                                  found["opportunities"][SLOTS][0]["setting"]))


# =========================================================================== independence (§31.17) and clusters (§31.18)

class IndependenceTests(unittest.TestCase):
    def test_positive_distinctness_of_every_fact_proves_independence(self) -> None:
        relation, basis = gp.relation(snapshot("alpha", 1), snapshot("beta", 2))
        self.assertEqual(gp.RELATION_INDEPENDENT, relation)
        self.assertIn(gp.BASIS_DISTINCT_LINEAGE, basis)

    def test_positive_shared_causal_facts_correlate(self) -> None:
        lineage = digest_of("lineage", 1)
        cases = {
            gp.BASIS_SAME_LINEAGE: {"lineage": lineage},
            gp.BASIS_COPY_SOURCE: {"copy_sources": [lineage]},  # a fork / copy of alpha
            gp.BASIS_SAME_INCIDENT: {"incidents": [digest_of("incident", 1)]},
            gp.BASIS_SAME_IMPLEMENTATION: {"implementations": [digest_of("implementation", 1)]},
        }
        for basis, overrides in cases.items():
            with self.subTest(basis=basis):
                found, why = gp.relation(snapshot("alpha", 1), snapshot("beta", 2, **overrides))
                self.assertEqual(gp.RELATION_CORRELATED, found)
                self.assertIn(basis, why)
        template = digest_of("template")
        found, why = gp.relation(snapshot("alpha", 1, copy_sources=[template]),
                                 snapshot("beta", 2, copy_sources=[template]))
        self.assertEqual((gp.RELATION_CORRELATED, (gp.BASIS_COPY_SOURCE,)), (found, why), "one template")
        shared = digest_of("shared library")
        found, why = gp.relation(
            snapshot("alpha", 1, dependencies=[{"identity": shared, "common_cause": gp.CAUSE_CAUSAL}]),
            snapshot("beta", 2, dependencies=[{"identity": shared, "common_cause": gp.CAUSE_RULED_OUT}]))
        self.assertEqual(gp.RELATION_CORRELATED, found)
        self.assertIn(gp.BASIS_CAUSAL_DEPENDENCY, why)
        record = {"family": RUNS, "id": ident("rr", 5), "digest": digest_of("one observation")}
        found, why = gp.relation(snapshot("alpha", 1, records=[record]), snapshot("beta", 2, records=[record]))
        self.assertIn(gp.BASIS_DUPLICATE_OBSERVATION, why)

    def test_absence_of_known_correlation_is_never_independence(self) -> None:
        shared = digest_of("shared library")
        cases = {
            gp.BASIS_LINEAGE_UNKNOWN: {"lineage": None},
            gp.BASIS_COPY_SOURCES_UNKNOWN: {"copy_sources": None},
            gp.BASIS_INCIDENT_UNKNOWN: {"incidents": None},
            gp.BASIS_IMPLEMENTATION_UNKNOWN: {"implementations": []},
            gp.BASIS_DEPENDENCIES_UNKNOWN: {"dependencies": None},
            gp.BASIS_DEPENDENCY_UNRESOLVED: {"dependencies": [{"identity": shared, "common_cause": gp.CAUSE_UNKNOWN}]},
        }
        for basis, overrides in cases.items():
            with self.subTest(basis=basis):
                other = {"dependencies": [{"identity": shared, "common_cause": gp.CAUSE_RULED_OUT}]} \
                    if basis == gp.BASIS_DEPENDENCY_UNRESOLVED else {}
                found, why = gp.relation(snapshot("alpha", 1, **other), snapshot("beta", 2, **overrides))
                self.assertEqual(gp.RELATION_UNRESOLVED, found)
                self.assertIn(basis, why)
        found, _ = gp.relation(
            snapshot("alpha", 1, dependencies=[{"identity": shared, "common_cause": gp.CAUSE_RULED_OUT}]),
            snapshot("beta", 2, dependencies=[{"identity": shared, "common_cause": gp.CAUSE_RULED_OUT}]))
        self.assertEqual(gp.RELATION_INDEPENDENT, found, "a shared dependency positively ruled out on both sides")

    def test_the_relation_is_symmetric(self) -> None:
        pairs = [(snapshot("alpha", 1), snapshot("beta", 2, copy_sources=[digest_of("lineage", 1)])),
                 (snapshot("alpha", 1, incidents=None), snapshot("beta", 2)),
                 (snapshot("alpha", 1), snapshot("beta", 2))]
        for first, second in pairs:
            self.assertEqual(gp.relation(first, second), gp.relation(second, first))


class ClusteringTests(unittest.TestCase):
    def test_correlation_is_one_cluster_transitively_and_unresolved_stays_apart(self) -> None:
        snapshots = [snapshot("alpha", 1), snapshot("beta", 2, copy_sources=[digest_of("lineage", 1)]),
                     snapshot("gamma", 3, incidents=[digest_of("incident", 2)]), snapshot("delta", 4, incidents=None)]
        found = gp.clustering(snapshots)
        self.assertEqual([{"sources": ["alpha", "beta", "gamma"]}, {"sources": ["delta"]}], found["clusters"])
        self.assertEqual(6, len(found["matrix"]))
        self.assertEqual(found, gp.clustering(list(reversed(snapshots))), "never by position")


# =========================================================================== eligibility (§31.19)

def elig(snapshots: list[dict[str, Any]], **request: Any) -> dict[str, Any]:
    record = gp.request_record(change_request(snapshots, **request))
    return gp.eligibility(record, snapshots, gp.clustering(snapshots))


class EligibilityTests(unittest.TestCase):
    def test_many_runs_in_one_project_never_qualify_alone(self) -> None:
        found = elig([snapshot("alpha", 1, runs=12)])
        self.assertFalse(found["eligible"])
        self.assertIn("too_few_lineages", found["problems"])
        self.assertIn("too_few_independent_clusters", found["problems"])
        lineage = digest_of("lineage", 1)
        copies = [snapshot("alpha", 1, runs=5), snapshot("beta", 2, runs=5, lineage=lineage),
                  snapshot("gamma", 3, runs=5, copy_sources=[lineage])]
        found = elig(copies)
        self.assertFalse(found["eligible"], "repository copies of one Project are one lineage and one cluster")
        self.assertEqual(1, found["lineages"])

    def test_the_strengthen_floor_is_two_lineages_and_two_independent_clusters(self) -> None:
        found = elig(two_independent())
        self.assertTrue(found["eligible"], found["problems"])
        self.assertEqual((gp.FLOOR_STRENGTHEN, 2, 2), (found["floor"], found["lineages"],
                                                      len(found["independent_clusters"])))

    def test_fork_template_and_incident_correlation_never_count_separately(self) -> None:
        for overrides in ({"copy_sources": [digest_of("lineage", 1)]}, {"incidents": [digest_of("incident", 1)]},
                          {"implementations": [digest_of("implementation", 1)]}):
            with self.subTest(overrides=overrides):
                found = elig([snapshot("alpha", 1), snapshot("beta", 2, **overrides)])
                self.assertFalse(found["eligible"])
                self.assertIn("too_few_independent_clusters", found["problems"])

    def test_unresolved_independence_does_not_count_and_needs_no_human(self) -> None:
        found = elig([snapshot("alpha", 1), snapshot("beta", 2, implementations=None)])
        self.assertFalse(found["eligible"])
        self.assertEqual(["too_few_independent_clusters"], found["problems"])
        self.assertNotIn("unresolved_human", found["problems"])

    def test_the_lighten_floor_is_stronger(self) -> None:
        found = elig(two_independent(), direction="lighten", after=1)
        self.assertFalse(found["eligible"])
        self.assertEqual(gp.FLOOR_LIGHTEN, found["floor"])
        self.assertEqual({"too_few_lineages", "too_few_independent_clusters"}, set(found["problems"]))
        self.assertEqual([{"source_id": "alpha", "reasons": ["no_exercised_opportunity"]},
                          {"source_id": "beta", "reasons": ["no_exercised_opportunity"]}], found["excluded_sources"],
                         "a source whose setting is unknown exercised nothing under the lighten floor")
        provisional = elig(three_independent(), direction="lighten", after=1)
        self.assertTrue(provisional["eligible"], provisional["problems"])
        self.assertIsNone(provisional["pre_change_setting"], "without the before setting the answer is provisional")
        thin = elig(three_independent(runs=1), direction="lighten", after=1)
        self.assertEqual(["unrepresentative_opportunities"], thin["problems"])
        self.assertTrue(thin["holdout_required"])

    def test_opportunities_whose_setting_is_unknown_never_satisfy_the_lighten_floor(self) -> None:
        unknown = elig(three_independent(ran_under=None), direction="lighten", after=1)
        self.assertEqual({"too_few_lineages", "too_few_independent_clusters"}, set(unknown["problems"]))
        self.assertEqual({("no_exercised_opportunity",)}, {tuple(item["reasons"]) for item in unknown["excluded_sources"]})
        self.assertEqual([], unknown["supporting_sources"])
        self.assertNotIn("no_exercised_opportunity", gp.STOP_CODES + gp.RECONCILE_REASONS,
                         "an exclusion reason of the eligibility record, never a catalogue code")
        strengthen = elig(three_independent(ran_under=None))
        self.assertTrue(strengthen["eligible"], "the strengthen floor needs no setting")
        self.assertEqual([], strengthen["excluded_sources"])

    def test_a_source_never_counted_merely_because_a_check_was_never_exercised(self) -> None:
        unexercised = snapshot("gamma", 3, runs=0, records=[{"family": FINDINGS, "id": ident("rfd", 9),
                                                             "digest": digest_of("gamma", 9)}])
        found = elig([snapshot("alpha", 1), unexercised])
        self.assertFalse(found["eligible"])
        self.assertEqual([{"source_id": "gamma", "reasons": ["no_relevant_opportunity"]}], found["excluded_sources"])

    def test_the_same_generalized_mechanism_and_no_project_specific_workaround(self) -> None:
        found = elig([snapshot("alpha", 1), snapshot("beta", 2, mechanism="other.mechanism")])
        self.assertEqual([{"source_id": "beta", "reasons": ["mechanism_differs"]}], found["excluded_sources"])
        self.assertFalse(found["eligible"])
        named = [snapshot("alpha", 1, mechanism="alpha.billing-workaround"),
                 snapshot("beta", 2, mechanism="alpha.billing-workaround")]
        self.assertIn("mechanism_project_specific", elig(named, mechanism="alpha.billing-workaround")["problems"])
        local = [snapshot("alpha", 1, semantic=("invoice-renderer",), mechanism="invoice-renderer"),
                 snapshot("beta", 2, mechanism="invoice-renderer")]
        self.assertIn("mechanism_project_specific", elig(local, mechanism="invoice-renderer")["problems"])

    def test_an_unresolved_human_boundary_blocks_eligibility(self) -> None:
        found = elig([snapshot("alpha", 1, human=(ident("rr", 101),)), snapshot("beta", 2), snapshot("gamma", 3)])
        self.assertFalse(found["eligible"])
        self.assertIn("unresolved_human", found["problems"])

    def test_inputs_that_do_not_match_the_request_are_never_eligible(self) -> None:
        snapshots = two_independent()
        record = gp.request_record(change_request(snapshots))
        found = gp.eligibility(record, snapshots, {"clusters": [{"sources": ["alpha", "beta"]}], "matrix": []})
        self.assertIn("clusters_mismatch", found["problems"])
        other = [snapshots[0], snapshot("beta", 2, runs=3)]
        self.assertIn("sources_mismatch", gp.eligibility(record, other, gp.clustering(other))["problems"])

    def test_the_exact_rollback_exception_rests_on_no_trend(self) -> None:
        record = gp.request_record(change_request([], direction="rollback", after=1, rollback_of=CHANGE_ID,
                                                  rollback_evaluation_id=EVALUATION_ID))
        found = gp.eligibility(record, [], gp.clustering([]))
        self.assertTrue(found["eligible"])
        self.assertEqual(gp.BASIS_EXACT_ROLLBACK, found["basis"])


# =========================================================================== the Promotion Packet (§31.22-§31.23)

class PacketTests(unittest.TestCase):
    def build(self, before: dict[str, Any] = V1, snapshots: list[dict[str, Any]] | None = None,
              **request: Any) -> dict[str, Any]:
        snapshots = two_independent() if snapshots is None else snapshots
        record = gp.request_record(change_request(snapshots, **request))
        clusters = gp.clustering(snapshots)
        after = gp.after_global_policy(before, record)
        return gp.promotion_packet(record, promotion_packet_id=PACKET_ID, global_policy_change_id=CHANGE_ID,
                                   before_global=before, after_global=after, snapshots=snapshots, clusters=clusters,
                                   eligibility=gp.eligibility(record, snapshots, clusters),
                                   proof=gp.compatibility_proof(before, after))

    def test_the_packet_binds_its_evidence_and_is_never_authorization(self) -> None:
        packet = self.build()
        self.assertEqual(set(gp.PACKET_FIELDS), set(packet))
        self.assertEqual((1, policy.global_policy_digest(V1)), (packet["before_global_policy_version"],
                                                                packet["before_global_policy_digest"]))
        self.assertEqual(2, packet["after_global_policy"]["global_policy_version"])
        self.assertEqual((1, 2, "default"), (packet["before_setting"], packet["after_setting"], packet["strength_class"]))
        self.assertEqual([1], packet["supported_profile_schema_versions"])
        self.assertEqual(policy.COMPATIBILITY_TOTAL_ADAPTER_V1, packet["compatibility_adapter_identity"])
        self.assertEqual({"policy_surface_id": SLOTS, "restore_setting": 1,
                          "restore_global_policy_digest": policy.global_policy_digest(V1)},
                         packet["rollback_contract"]["unit"])
        self.assertFalse({"receipt_id", "authorized", "authorization"} & set(packet))
        self.assertEqual(set(gp.ROLLBACK_UNIT_FIELDS), set(packet["rollback_contract"]["unit"]))
        self.assertEqual(set(gp.DIVERSITY_FIELDS), set(packet["environment_diversity"]))
        self.assertEqual(["py3.12"], packet["environment_diversity"]["toolchains"])
        self.assertEqual([{"source_id": "alpha", "opportunities": [ident("rr", 101), ident("rr", 102)]},
                          {"source_id": "beta", "opportunities": [ident("rr", 201), ident("rr", 202)]}],
                         packet["relevant_opportunities"])
        self.assertEqual(packet, gp.parse_promotion_packet(packet, "the Packet"))
        self.assertNotIn(str(SECRET_ROOT), serialize.canonical_text(packet))

    def test_a_tampered_packet_does_not_read(self) -> None:
        packet = self.build()
        for name, value in (("eligibility", {**packet["eligibility"], "lineages": 9}),
                            ("clusters", [{"sources": ["alpha", "beta"]}]),
                            ("after_setting", 3),
                            ("source_snapshots", [{**packet["source_snapshots"][0], "digest": "0" * 64}]
                             + packet["source_snapshots"][1:])):
            with self.subTest(field=name):
                with self.assertRaises(ValidationError):
                    gp.parse_promotion_packet({**packet, name: value}, "the Packet")

    def test_lightening_counts_only_opportunities_that_exercised_the_stronger_behaviour(self) -> None:
        # §31.19 L12023 / §16.10 L4499: Global required slots 3 -> 2; what was exercised at 1 or 2 says nothing about 3
        excluded, thin = "too_few_independent_clusters", "unrepresentative_opportunities"
        cases = {
            "ran under Global v1 (slots 1)": ((1, 1), excluded),
            "ran under a lighter Project setting 2": ((2, 2), excluded),
            "setting unknown (no frozen Effective Policy)": (None, excluded),
            "ran under the pre-change setting 3": ((2, 3), None),
            "ran under a stricter Project setting 4": ((2, 4), None),
            "one exercised and one lighter Run per source": ([(2, 3), (1, 1)], thin),
        }
        for name, (ran_under, problem) in cases.items():
            with self.subTest(case=name):
                snapshots = three_independent(ran_under=ran_under)
                if problem is None:
                    packet = self.build(V2_SLOTS3, snapshots=snapshots, direction="lighten", after=2)
                    self.assertEqual((gp.FLOOR_LIGHTEN, 3, True), (packet["eligibility"]["floor"],
                                                                   packet["eligibility"]["pre_change_setting"],
                                                                   packet["eligibility"]["eligible"]))
                    continue
                with self.assertRaises(StopError) as raised:
                    self.build(V2_SLOTS3, snapshots=snapshots, direction="lighten", after=2)
                self.assertEqual(gp.CODE_NOT_ELIGIBLE, raised.exception.code)
                self.assertIn(problem, str(raised.exception))

    def test_a_source_that_exercised_only_the_lighter_behaviour_is_not_counted_and_blocks_nothing(self) -> None:
        # RB7CD-1, §31.19 L12025: "no source counted" - an exclusion, never a refusal; the floors are "at least"
        snapshots = three_independent() + [snapshot("delta", 4, ran_under=(1, 1))]
        packet = self.build(V2_SLOTS3, snapshots=snapshots, direction="lighten", after=2)
        found = packet["eligibility"]
        self.assertTrue(found["eligible"], found["problems"])
        self.assertEqual(["alpha", "beta", "gamma"], found["supporting_sources"])
        self.assertEqual([{"source_id": "delta", "reasons": ["no_exercised_opportunity"]}], found["excluded_sources"])
        self.assertEqual(packet, gp.parse_promotion_packet(packet, "the Packet"))

    def test_an_unexercised_cluster_never_displaces_a_qualifying_independent_triple(self) -> None:
        # RB7CD-1 second face: "alpha" sorts first, ran only lighter, and is unresolved with beta (a shared dependency
        # whose common cause it leaves unknown); it must not be chosen over the exercised triple beta / gamma / kappa
        shared = digest_of("shared library")
        snapshots = [snapshot("alpha", 1, ran_under=(1, 1),
                              dependencies=[{"identity": shared, "common_cause": gp.CAUSE_UNKNOWN}]),
                     snapshot("beta", 2, ran_under=(2, 3),
                              dependencies=[{"identity": shared, "common_cause": gp.CAUSE_RULED_OUT}]),
                     snapshot("gamma", 3, ran_under=(2, 3)), snapshot("kappa", 4, ran_under=(2, 3))]
        self.assertEqual(gp.RELATION_UNRESOLVED, gp.relation(snapshots[0], snapshots[1])[0])
        self.assertEqual(gp.RELATION_INDEPENDENT, gp.relation(snapshots[0], snapshots[2])[0])
        found = self.build(V2_SLOTS3, snapshots=snapshots, direction="lighten", after=2)["eligibility"]
        self.assertTrue(found["eligible"], found["problems"])
        self.assertEqual([{"sources": ["beta"]}, {"sources": ["gamma"]}, {"sources": ["kappa"]}],
                         found["independent_clusters"])

    def test_one_run_shared_by_a_project_and_its_fork_is_one_opportunity(self) -> None:
        # RB7CD-2, §31.18: repeated Runs in one causal incident never multiply eligibility - distinct Runs per cluster
        def pair(name: str, n: int, *, own_run: bool) -> list[dict[str, Any]]:
            shared = {"family": RUNS, "id": ident("rr", n * 100), "digest": digest_of(name, "shared run")}
            first = [shared] + ([{"family": RUNS, "id": ident("rr", n * 100 + 1), "digest": digest_of(name, "own")}]
                                if own_run else [])
            return [snapshot(name, n, records=first, ran_under=(2, 3)),
                    snapshot(f"{name}-fork", n + 10, records=[shared], ran_under=(2, 3),
                             lineage=digest_of("lineage", n))]

        for own_run, eligible in ((False, False), (True, True)):
            with self.subTest(distinct_runs_per_cluster=2 if own_run else 1):
                snapshots = pair("alpha", 1, own_run=own_run) + pair("beta", 2, own_run=own_run) \
                    + pair("gamma", 3, own_run=own_run)
                clusters = gp.clustering(snapshots)["clusters"]
                self.assertEqual([["alpha", "alpha-fork"], ["beta", "beta-fork"], ["gamma", "gamma-fork"]],
                                 [cluster["sources"] for cluster in clusters])
                if eligible:
                    found = self.build(V2_SLOTS3, snapshots=snapshots, direction="lighten", after=2)["eligibility"]
                    self.assertEqual((True, 3, 3), (found["eligible"], found["lineages"],
                                                    len(found["independent_clusters"])))
                    continue
                with self.assertRaises(StopError) as raised:
                    self.build(V2_SLOTS3, snapshots=snapshots, direction="lighten", after=2)
                self.assertEqual(gp.CODE_NOT_ELIGIBLE, raised.exception.code)
                self.assertIn("unrepresentative_opportunities", str(raised.exception))

    def test_a_thin_fourth_cluster_adds_context_and_never_subtracts(self) -> None:
        # RB7CE-1, §31.18 L11999 / §31.19 "at least": alpha exercised the pre-change setting once (four Runs were
        # lighter); beta / gamma / delta twice each - the qualifying triple is the witness set, alpha blocks nothing
        thin = [(2, 3), (1, 1), (1, 1), (1, 1), (1, 1)]
        snapshots = [snapshot("alpha", 1, runs=5, ran_under=thin)] + [
            snapshot(name, n, ran_under=(2, 3)) for name, n in (("beta", 2), ("gamma", 3), ("delta", 4))]
        packet = self.build(V2_SLOTS3, snapshots=snapshots, direction="lighten", after=2)
        found = packet["eligibility"]
        self.assertTrue(found["eligible"], found["problems"])
        self.assertEqual([{"sources": ["beta"]}, {"sources": ["delta"]}, {"sources": ["gamma"]}],
                         found["independent_clusters"])
        self.assertEqual(["alpha", "beta", "delta", "gamma"], found["supporting_sources"],
                         "a thin source is context, not an exclusion: it keeps its lineage")
        self.assertEqual(packet, gp.parse_promotion_packet(packet, "the Packet"))

    def test_a_thin_cluster_unresolved_with_a_qualifying_one_is_never_chosen(self) -> None:
        # RB7CE-1 unresolved-pair variant: alpha (one exercised Run) sorts first and is unresolved with beta
        shared = digest_of("shared library")
        snapshots = [snapshot("alpha", 1, runs=2, ran_under=[(2, 3), (1, 1)],
                              dependencies=[{"identity": shared, "common_cause": gp.CAUSE_UNKNOWN}]),
                     snapshot("beta", 2, ran_under=(2, 3),
                              dependencies=[{"identity": shared, "common_cause": gp.CAUSE_RULED_OUT}]),
                     snapshot("gamma", 3, ran_under=(2, 3)), snapshot("kappa", 4, ran_under=(2, 3))]
        self.assertEqual(gp.RELATION_UNRESOLVED, gp.relation(snapshots[0], snapshots[1])[0])
        found = self.build(V2_SLOTS3, snapshots=snapshots, direction="lighten", after=2)["eligibility"]
        self.assertTrue(found["eligible"], found["problems"])
        self.assertEqual([{"sources": ["beta"]}, {"sources": ["gamma"]}, {"sources": ["kappa"]}],
                         found["independent_clusters"])

    def test_too_few_clusters_and_too_thin_clusters_are_told_apart(self) -> None:
        # only two independent clusters at all: the cluster floor itself is unmet, whatever their support
        two = [snapshot("alpha", 1, ran_under=(2, 3)), snapshot("beta", 2, ran_under=(2, 3))]
        with self.assertRaises(StopError) as raised:
            self.build(V2_SLOTS3, snapshots=two, direction="lighten", after=2)
        self.assertIn("too_few_independent_clusters", str(raised.exception))
        self.assertNotIn("unrepresentative_opportunities", str(raised.exception))
        # three clusters, one thin: the shortfall is the thin cluster's
        thin = [snapshot("alpha", 1, runs=2, ran_under=[(2, 3), (1, 1)]), snapshot("beta", 2, ran_under=(2, 3)),
                snapshot("gamma", 3, ran_under=(2, 3))]
        with self.assertRaises(StopError) as raised:
            self.build(V2_SLOTS3, snapshots=thin, direction="lighten", after=2)
        self.assertIn("unrepresentative_opportunities", str(raised.exception))
        self.assertNotIn("too_few_independent_clusters", str(raised.exception))

    def test_a_change_that_lowers_the_setting_is_held_to_the_lighten_floor_whatever_its_word(self) -> None:
        with self.assertRaises(StopError) as raised:
            self.build(V2_SLOTS3, direction="adjust", after=2)
        self.assertEqual(gp.CODE_NOT_ELIGIBLE, raised.exception.code)
        packet = self.build(V2_SLOTS3, snapshots=three_independent(), direction="adjust", after=2)
        self.assertEqual(gp.FLOOR_LIGHTEN, packet["eligibility"]["floor"])
        self.assertTrue(packet["eligibility"]["holdout_required"])

    def test_the_direction_word_must_agree_with_the_movement_and_the_setting_must_change(self) -> None:
        for before, request in ((V2_SLOTS3, {"direction": "strengthen", "after": 2}),
                                (V1, {"direction": "lighten", "after": 2}), (V1, {"after": 1})):
            with self.subTest(request=request):
                with self.assertRaises(StopError) as raised:
                    gp.after_global_policy(before, gp.request_record(change_request(two_independent(), **request)))
                self.assertEqual(gp.CODE_REQUEST_INVALID, raised.exception.code)

    def test_parts_that_are_not_the_derivations_are_refused(self) -> None:
        snapshots = two_independent()
        record = gp.request_record(change_request(snapshots))
        clusters = gp.clustering(snapshots)
        after = gp.after_global_policy(V1, record)
        good = dict(promotion_packet_id=PACKET_ID, global_policy_change_id=CHANGE_ID, before_global=V1,
                    after_global=after, snapshots=snapshots, clusters=clusters,
                    eligibility=gp.eligibility(record, snapshots, clusters), proof=gp.compatibility_proof(V1, after))
        for name, value in (("clusters", {"clusters": [{"sources": ["alpha"]}, {"sources": ["beta"]}], "matrix": []}),
                            ("eligibility", {**good["eligibility"], "eligible": False}),
                            ("after_global", successor(V1, slots=3))):
            with self.subTest(part=name):
                with self.assertRaises(ReconcileRequired) as raised:
                    gp.promotion_packet(record, **{**good, name: value})
                self.assertEqual(gp.REASON_CANDIDATE_MISMATCH, raised.exception.reason)
        with self.assertRaises(StopError) as raised:
            gp.promotion_packet(record, **{**good, "proof": {**good["proof"], "cases": 1}})
        self.assertEqual(gp.CODE_COMPATIBILITY_UNPROVEN, raised.exception.code)


# =========================================================================== the exact-rollback exception (§31.20)

def evaluation_request(change_id: str, result: str, snapshots: list[dict[str, Any]], *,
                       end_env: dict[str, Any] | None = None, basis: str | None = None,
                       basis_digest: str | None = None) -> dict[str, Any]:
    return gp.evaluation_request_record(gp.GlobalPolicyEvaluationRequest(
        global_policy_change_id=change_id, result=result,
        rationale="the frozen measurement over the observation window", environment={
            "window_start": dict(ENV), "window_end": dict(end_env or ENV), "basis": basis, "basis_digest": basis_digest},
        sources=tuple(gp.SourceProject(item["source_id"], SECRET_ROOT) for item in snapshots),
        evidence={item["source_id"]: evidence_of(item) for item in snapshots}))


def observed(change_id: str, runs: int = 2) -> list[dict[str, Any]]:
    return [snapshot("alpha", 11, runs=runs, global_changes=(change_id,), ran_under=(2, 2)),
            snapshot("beta", 12, runs=runs, global_changes=(change_id,), ran_under=(2, 2))]


def evaluate(change: dict[str, Any], result: str, snapshots: list[dict[str, Any]], *,
             evaluated: dict[str, Any] | None = None, **environment: Any) -> dict[str, Any]:
    request = evaluation_request(change["global_policy_change_id"], result, snapshots, **environment)
    return gp.evaluation_record(request, evaluation_id=EVALUATION_ID, change=change,
                                evaluated_global=evaluated or successor(V1, slots=2), snapshots=snapshots,
                                clusters=gp.clustering(snapshots))


class ExactRollbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.change = applied_change(self)
        self.after = successor(V1, slots=2)
        self.evaluation = evaluate(self.change, gp.RESULT_ROLLBACK, observed(CHANGE_ID))

    def request(self, **overrides: Any) -> dict[str, Any]:
        fields = dict(direction="rollback", after=1, rollback_of=CHANGE_ID, rollback_evaluation_id=EVALUATION_ID)
        fields.update(overrides)
        return gp.request_record(change_request([], **fields))

    def test_an_exact_rollback_needs_no_fresh_trend(self) -> None:
        self.assertIsNone(gp.exact_rollback_problem(self.request(), self.after, self.change, self.evaluation))
        gp.require_exact_rollback(self.request(), self.after, self.change, self.evaluation)

    def test_a_non_exact_rollback_takes_ordinary_eligibility(self) -> None:
        retained = evaluate(self.change, gp.RESULT_RETAIN, observed(CHANGE_ID))
        cases = {
            "threshold not fired": (self.request(), self.after, retained),
            "not the before setting": (self.request(after=3), self.after, self.evaluation),
            "another surface": (self.request(surface=STEPS, after=1), self.after, self.evaluation),
            "change not in force": (self.request(), successor(self.after, slots=4), self.evaluation),
        }
        for name, (request, before, evaluation) in cases.items():
            with self.subTest(case=name):
                self.assertIsNotNone(gp.exact_rollback_problem(request, before, self.change, evaluation))
        with self.assertRaises(StopError) as raised:
            gp.require_exact_rollback(self.request(after=3), self.after, self.change, self.evaluation)
        self.assertEqual(gp.CODE_ROLLBACK_INEXACT, raised.exception.code)

    def test_a_rollback_is_a_new_higher_version(self) -> None:
        after = gp.after_global_policy(self.after, self.request())
        self.assertEqual((3, policy.global_policy_digest(self.after)),
                         (after["global_policy_version"], after["parent_global_policy_digest"]))
        self.assertEqual(policy.global_policy_settings(V1), policy.global_policy_settings(after))
        self.assertNotEqual(policy.global_policy_digest(V1), policy.global_policy_digest(after))


# =========================================================================== the Global evaluation record (§31.41-§31.43)

class EvaluationRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.change = applied_change(self)

    def test_retain_ends_observation_after_the_frozen_minimum_in_independent_clusters(self) -> None:
        found = evaluate(self.change, gp.RESULT_RETAIN, observed(CHANGE_ID))
        self.assertEqual((gp.RESULT_RETAIN, policy.NEXT_END_OBSERVATION), (found["result"], found["next_action"]))
        self.assertEqual(found, gp.parse_evaluation_record(found, "the evaluation"))
        self.assertEqual(serialize.digest(dict(self.change["measurement_contract"])), found["measurement_contract_digest"])

    def test_correlated_projects_never_become_many_confirmations(self) -> None:
        lineage = digest_of("lineage", 11)
        correlated = [snapshot("alpha", 11, runs=3, global_changes=(CHANGE_ID,), ran_under=(2, 2)),
                      snapshot("beta", 12, runs=3, global_changes=(CHANGE_ID,), ran_under=(2, 2), lineage=lineage)]
        with self.assertRaises(StopError) as raised:
            evaluate(self.change, gp.RESULT_RETAIN, correlated)
        self.assertEqual(gp.CODE_EVALUATION_INVALID, raised.exception.code)

    def test_one_post_change_run_named_by_a_project_and_its_fork_is_one_observation(self) -> None:
        # RB7CE-2, §31.18: the retain gate counts distinct observed Runs, as the eligibility floor does
        change = applied_change(self, measurement={**MEASUREMENT, "minimum_opportunities": 2, "minimum_clusters": 1})

        def project_and_fork(own_run: bool) -> list[dict[str, Any]]:
            shared = {"family": RUNS, "id": ident("rr", 1100), "digest": digest_of("alpha", "post-change run")}
            first = [shared] + ([{"family": RUNS, "id": ident("rr", 1101), "digest": digest_of("alpha", "own")}]
                                if own_run else [])
            return [snapshot("alpha", 11, records=first, global_changes=(CHANGE_ID,), ran_under=(2, 2)),
                    snapshot("alpha-fork", 21, records=[shared], global_changes=(CHANGE_ID,), ran_under=(2, 2),
                             lineage=digest_of("lineage", 11))]

        with self.assertRaises(StopError) as raised:
            evaluate(change, gp.RESULT_RETAIN, project_and_fork(own_run=False))
        self.assertEqual(gp.CODE_EVALUATION_INVALID, raised.exception.code)
        self.assertIn("proves 1 in 1", str(raised.exception))
        found = evaluate(change, gp.RESULT_RETAIN, project_and_fork(own_run=True))
        self.assertEqual(policy.NEXT_END_OBSERVATION, found["next_action"])

    def test_chronology_alone_is_never_causal_evidence(self) -> None:
        unobserved = [snapshot("alpha", 11, ran_under=(2, 2)), snapshot("beta", 12, ran_under=(2, 2))]
        for result in (gp.RESULT_RETAIN, gp.RESULT_ADJUST, gp.RESULT_ROLLBACK):
            with self.subTest(result=result):
                with self.assertRaises(StopError) as raised:
                    evaluate(self.change, result, unobserved)
                self.assertEqual(gp.CODE_EVALUATION_INVALID, raised.exception.code)

    def test_adjust_rollback_and_inconclusive_are_never_success(self) -> None:
        for result, action in ((gp.RESULT_ADJUST, policy.NEXT_NEW_CANDIDATE),
                               (gp.RESULT_ROLLBACK, policy.NEXT_NEW_CANDIDATE),
                               (gp.RESULT_INCONCLUSIVE, policy.NEXT_CONTINUE_OBSERVATION)):
            with self.subTest(result=result):
                self.assertEqual(action, evaluate(self.change, result, observed(CHANGE_ID))["next_action"])
        final = applied_change(self, measurement={**MEASUREMENT, "continued_observation_permitted": False})
        self.assertEqual(policy.NEXT_NEW_CANDIDATE, evaluate(final, gp.RESULT_INCONCLUSIVE, [])["next_action"])

    def test_a_material_environment_change_needs_a_window_split_or_irrelevance_proof(self) -> None:
        changed = {**ENV, "toolchain": "py3.13"}
        with self.assertRaises(StopError) as raised:
            evaluate(self.change, gp.RESULT_RETAIN, observed(CHANGE_ID), end_env=changed)
        self.assertEqual(gp.CODE_EVALUATION_INVALID, raised.exception.code)
        inconclusive = evaluate(self.change, gp.RESULT_INCONCLUSIVE, observed(CHANGE_ID), end_env=changed)
        self.assertEqual(gp.RESULT_INCONCLUSIVE, inconclusive["result"])
        snapshots = observed(CHANGE_ID)
        proof = snapshots[0]["records"][0]["digest"]
        found = evaluate(self.change, gp.RESULT_RETAIN, snapshots, end_env=changed, basis="window_split",
                         basis_digest=proof)
        self.assertEqual("window_split", found["environment"]["basis"])
        with self.assertRaises(StopError) as raised:
            evaluate(self.change, gp.RESULT_RETAIN, snapshots, end_env=changed, basis="irrelevance_proof",
                     basis_digest=digest_of("arbitrary"))
        self.assertEqual(gp.CODE_EVALUATION_INVALID, raised.exception.code)

    def test_an_evaluation_is_of_a_global_the_change_is_in_force_in(self) -> None:
        with self.assertRaises(StopError) as raised:
            evaluate(self.change, gp.RESULT_RETAIN, observed(CHANGE_ID), evaluated=successor(successor(V1, slots=2),
                                                                                              slots=3))
        self.assertEqual(gp.CODE_EVALUATION_INVALID, raised.exception.code)

    def test_an_evaluation_writes_no_policy(self) -> None:
        found = evaluate(self.change, gp.RESULT_RETAIN, observed(CHANGE_ID))
        self.assertEqual(set(gp.EVALUATION_FIELDS), set(found))
        self.assertFalse({"settings", "global_policy", "after_global_policy"} & set(found))
        self.assertEqual(policy.global_policy_digest(successor(V1, slots=2)), found["evaluated_global_policy_digest"])

    def test_a_malformed_evaluation_request_is_refused(self) -> None:
        snapshots = observed(CHANGE_ID)
        good = gp.GlobalPolicyEvaluationRequest(
            global_policy_change_id=CHANGE_ID, result=gp.RESULT_RETAIN, rationale="the frozen measurement",
            environment={"window_start": dict(ENV), "window_end": dict(ENV), "basis": None, "basis_digest": None},
            sources=tuple(gp.SourceProject(item["source_id"], SECRET_ROOT) for item in snapshots),
            evidence={item["source_id"]: evidence_of(item) for item in snapshots})
        self.assertEqual(gp.SCHEMA_EVALUATION_REQUEST, gp.evaluation_request_record(good)[serialize.SCHEMA_KEY])
        for name, changes in (("result", {"result": "success"}), ("change id", {"global_policy_change_id": RUN_ID}),
                              ("rationale", {"rationale": "see /home/dev/alpha/notes"}),
                              ("basis without digest", {"environment": {**good.environment, "basis": "window_split"}}),
                              ("environment shape", {"environment": {"window_start": dict(ENV)}})):
            with self.subTest(case=name):
                with self.assertRaises(StopError) as raised:
                    gp.evaluation_request_record(gp.GlobalPolicyEvaluationRequest(**{**good.__dict__, **changes}))
                self.assertEqual(gp.CODE_EVALUATION_INVALID, raised.exception.code)
        identity = gp.evaluation_operation_identity(gp.request_digest(gp.evaluation_request_record(good)))
        self.assertTrue(identity.startswith("global-policy-evaluation:"))

    def test_a_tampered_evaluation_does_not_read(self) -> None:
        found = evaluate(self.change, gp.RESULT_RETAIN, observed(CHANGE_ID))
        for name, value in (("next_action", policy.NEXT_CONTINUE_OBSERVATION), ("result", "success"),
                            ("clusters", {"clusters": [], "matrix": []}), ("rationale", "line one\nline two")):
            with self.subTest(field=name):
                with self.assertRaises(ValidationError):
                    gp.parse_evaluation_record({**found, name: value}, "the evaluation")


# =========================================================================== Global-origin experiments (§16.10, FC-RB7-6)

class ActiveGlobalExperimentTests(unittest.TestCase):
    def test_every_change_in_the_lineage_is_observed_until_retain_and_a_lightening_keeps_its_holdout(self) -> None:
        strengthen = applied_change(self)
        v2 = successor(V1, slots=2)
        found = gp.active_global_experiments([strengthen], [], v2)
        self.assertEqual([(CHANGE_ID, SLOTS, "strengthen", None, policy.ORIGIN_GLOBAL)],
                         [(item.policy_change_id, item.policy_surface_id, item.direction, item.holdout_setting,
                           item.origin) for item in found])
        retained = evaluate(strengthen, gp.RESULT_RETAIN, observed(CHANGE_ID))
        self.assertEqual((), gp.active_global_experiments([strengthen], [retained], v2))
        self.assertEqual((), gp.active_global_experiments([], [], V1), "version 1 is no learned change")

    def test_a_lightening_freezes_the_stronger_before_setting_as_its_holdout(self) -> None:
        snapshots = three_independent()
        material = candidate_for(V2_SLOTS3, change_request(snapshots, direction="lighten", after=2), snapshots)
        lighten = gp.change_record(material, review_run_id=RUN_ID, receipt_id=RECEIPT_ID)
        earlier = dict(applied_change(self, after=3), global_policy_change_id="rgc_" + "2" * 26)
        found = gp.active_global_experiments([earlier, lighten], [], successor(V2_SLOTS3, slots=2))
        self.assertEqual([(CHANGE_ID, 3)], [(item.policy_change_id, item.holdout_setting) for item in found],
                         "the later change on one surface supersedes the earlier one")

    def test_a_version_no_stored_change_produced_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            gp.active_global_experiments([], [], successor(V1, slots=2))
        change = applied_change(self)
        with self.assertRaises(ValidationError):
            gp.active_global_experiments([change, dict(change)], [], successor(V1, slots=2))


if __name__ == "__main__":
    unittest.main()
