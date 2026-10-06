"""P6 §30.38: learning, holdout and evaluation - the fixed meta-rules a Policy Change is held to (§15.15-§15.26).

* one opportunity never makes a permanent adaptation; a duplicate is never a second opportunity; the denominator is
  Relevant Opportunity (distinct Review Runs that exercised the surface), never raw record count;
* a temporary_guard strengthens only, originates from one serious supported escape and never becomes permanent
  through an evaluation;
* both lightening surfaces keep the pre-change behaviour as an all_relevant holdout; a reverification holdout check
  settles before the Repair Result and a failed one blocks;
* retain / adjust / rollback / inconclusive: retain ends observation only after the frozen minimum of opportunities
  OBSERVED UNDER the change; adjust and rollback need a new Candidate; inconclusive is never success;
* only proven_disjoint experiments observe concurrently; supersede stays on the Candidate's own surface;
* a material environment change needs a window split or a positive irrelevance proof that is stored evidence;
* a settled experiment ref leaves the effective active set.

Unit level, over an in-memory reader whose records are the exact typed facts the meta-rules read (RB6B-M10).
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
from types import SimpleNamespace
from typing import Any
import unittest

from helpers import WORKLINE_ROOT
from workline.errors import StopError, ValidationError
from workline.review import history, p4, paths, policy, records, serialize

from test_review_p4_records import adjudication_fixture, batch_fixture
from test_review_p4_evidence import REPAIR_TASK, coverage

REQ = policy.SURFACE_REQUIRED_SLOTS
EXTRA = policy.SURFACE_EXTRA_SCOPE_STEPS
NEW_ID = "rpc_" + "9" * 26


def ident(prefix: str, number: int) -> str:
    return f"{prefix}_{number:026d}"


def digest_of(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


_BASELINE: list[policy.GlobalPolicyBaseline] = []


def baseline() -> policy.GlobalPolicyBaseline:
    if not _BASELINE:
        _BASELINE.append(policy.load_global_baseline(WORKLINE_ROOT))
    return _BASELINE[0]


def discovery_envelope(effective: dict[str, Any]) -> dict[str, Any]:
    """The fields of a P6 discovery request the frozen-policy reader reads (its generation-1 request)."""
    return {serialize.SCHEMA_KEY: p4.SCHEMA_DISCOVERY_REQUEST, "policy_id": p4.P6_POLICY_ID,
            policy.EFFECTIVE_POLICY_KEY: effective, policy.DISCOVERY_ROLE_KEY: policy.ROLE_REQUIRED}


class World:
    """An in-memory Review reader: stored P5 history, policy change / evaluation records and Runs' frozen policies."""

    def __init__(self) -> None:
        self.history: dict[tuple[str, str], Any] = {}
        self.changes: dict[str, dict[str, Any]] = {}
        self.evaluations: dict[str, dict[str, Any]] = {}
        self.envelopes: dict[str, dict[str, Any]] = {}
        self.profile: policy.ProjectProfile | None = None

    # the reader ------------------------------------------------------------------------------
    def read_history(self, family: str, identifier: str) -> Any:
        try:
            return self.history[(family, identifier)]
        except KeyError:
            raise ValidationError(f"{family}/{identifier} is not stored", code="review_p5_history_missing") from None

    def history_digest(self, family: str, identifier: str) -> str:
        self.read_history(family, identifier)
        return digest_of(family, identifier)

    def policy_change_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.changes))

    def policy_change_exists(self, change_id: str) -> bool:
        return change_id in self.changes

    def read_policy_change(self, change_id: str) -> dict[str, Any]:
        return self.changes[change_id]

    def policy_evaluation_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.evaluations))

    def read_policy_evaluation(self, evaluation_id: str) -> dict[str, Any]:
        return self.evaluations[evaluation_id]

    def policy_evaluation_digest(self, evaluation_id: str) -> str:
        if evaluation_id not in self.evaluations:
            raise ValidationError(f"evaluation {evaluation_id} is not stored", code="review_record_invalid")
        return digest_of("evaluation", evaluation_id)

    def gate_chain(self, review_run_id: str) -> Any:
        if review_run_id not in self.envelopes:
            return None
        return SimpleNamespace(review_run_id=review_run_id,
                               generations=[SimpleNamespace(accepted_tasks=[{"task_id": review_run_id}])])

    def read_task_input(self, task_id: str) -> Any:
        return SimpleNamespace(request_envelope=self.envelopes[task_id])

    def read_profile(self) -> policy.ProjectProfile | None:
        return self.profile

    # stored facts ----------------------------------------------------------------------------
    def ref(self, family: str, identifier: str) -> policy.EvidenceRef:
        return policy.EvidenceRef(family, identifier, self.history_digest(family, identifier)
                                  if family != policy.POLICY_EVIDENCE_EVALUATIONS
                                  else self.policy_evaluation_digest(identifier))

    def run(self, number: int, *, generation: int = 2, disposition: str = history.DISPOSITION_CONSUMED,
            frozen: dict[str, Any] | None = None) -> policy.EvidenceRef:
        run_id = ident("rr", number)
        self.history[(paths.HISTORY_RUNS, run_id)] = SimpleNamespace(
            review_run_id=run_id, gate_generation=generation, durable_disposition=disposition)
        if frozen is not None:
            self.envelopes[run_id] = discovery_envelope(frozen)
        return self.ref(paths.HISTORY_RUNS, run_id)

    def finding(self, number: int, run: int, *, severity: str = "HIGH",
                category: str = records.OUTCOME_PROBLEM) -> policy.EvidenceRef:
        finding_id = ident("rfd", number)
        self.history[(paths.HISTORY_FINDINGS, finding_id)] = SimpleNamespace(
            finding_id=finding_id, review_run_id=ident("rr", run), severity=severity, category=category)
        return self.ref(paths.HISTORY_FINDINGS, finding_id)

    def repair(self, number: int, run: int) -> policy.EvidenceRef:
        batch_id = ident("rrb", number)
        self.history[(paths.HISTORY_REPAIRS, batch_id)] = SimpleNamespace(
            repair_batch_id=batch_id, source_review_run_id=ident("rr", run))
        return self.ref(paths.HISTORY_REPAIRS, batch_id)

    def relation(self, number: int, target_kind: str, target_id: str, *,
                 relation_type: str = history.RELATION_DOWNSTREAM_ESCAPE,
                 status: str = history.CAUSAL_SUPPORTED) -> policy.EvidenceRef:
        relation_id = ident("rhr", number)
        self.history[(paths.HISTORY_RELATIONS, relation_id)] = SimpleNamespace(
            relation_id=relation_id, relation_type=relation_type, confirmed=status == history.CAUSAL_SUPPORTED,
            target=SimpleNamespace(kind=target_kind, id=target_id))
        return self.ref(paths.HISTORY_RELATIONS, relation_id)

    def evaluation(self, number: int, change_id: str, result: str,
                   evidence: tuple[policy.EvidenceRef, ...] = ()) -> policy.EvidenceRef:
        evaluation_id = ident("rpe", number)
        self.evaluations[evaluation_id] = {
            "evaluation_id": evaluation_id, "policy_change_id": change_id, "result": result,
            "next_action": policy.NEXT_END_OBSERVATION if result == policy.RESULT_RETAIN else policy.NEXT_NEW_CANDIDATE,
            "evidence": [item.to_record() for item in evidence],
        }
        return self.ref(policy.POLICY_EVIDENCE_EVALUATIONS, evaluation_id)

    def change(self, number: int, surface: str, direction: str, before: int, after: int, *,
               minimum: int = 2, continued: bool = True) -> str:
        change_id = ident("rpc", number)
        self.changes[change_id] = {
            "policy_change_id": change_id, "affected_policy_surface": surface, "direction": direction,
            "before_setting": before, "after_setting": after,
            "holdout_plan": None if after >= before else {"policy_surface_id": surface, "holdout_setting": before,
                                                          "selection": policy.HOLDOUT_SELECTION_ALL_RELEVANT},
            "observation_window": {"minimum_opportunities": minimum, "maximum_opportunities": 10},
            "measurement_contract": {"version": "m1", "metric": "supported Problems per relevant Run",
                                     "continued_observation_permitted": continued},
            "environment_identity": {**ENVIRONMENT_FROZEN, "global_baseline_digest": baseline().digest},
        }
        return change_id


ENVIRONMENT = policy.EnvironmentInput(("discovery 1",), ("planning-validator",), "py3")
ENVIRONMENT_FROZEN = {"measurement_contract_version": "m1", **ENVIRONMENT.to_record()}


def state_of(world: World, overrides: dict[str, tuple[int, str]] | None = None,
             active: tuple[str, ...] = ()) -> policy.PolicyState:
    """A current PolicyState: a Profile holding ``overrides`` ({surface: (setting, supporting id)}) and ``active``."""
    found = []
    for surface_id, (value, supporting) in sorted((overrides or {}).items()):
        surface = policy.SURFACE_BY_ID[surface_id]
        found.append({"policy_surface_id": surface_id, "strength_class": surface.strength_class, "setting": value,
                      "direction": "strengthen" if value > surface.global_setting else "lighten",
                      "supporting_policy_change_id": supporting})
    profile = None
    if found or active:
        profile = policy.ProjectProfile(
            profile_version=1, parent_profile_digest=None, global_baseline_digest=baseline().digest,
            global_baseline_version=1, loader_semantics_identity=policy.LOADER_SEMANTICS_IDENTITY,
            overrides=tuple(found), active_experiment_refs=tuple(sorted(active)))
    world.profile = profile
    experiments = policy.active_experiments(world, profile)
    return policy.PolicyState(baseline(), profile, experiments,
                              policy.effective_policy_record(baseline(), profile, experiments))


def request(surface: str, direction: str, after: int, evidence: tuple[policy.EvidenceRef, ...], *,
            opportunities: tuple[policy.EvidenceRef, ...] | None = None, supersedes: tuple[str, ...] = (),
            rolls_back: str | None = None, overlap: str = policy.OVERLAP_PROVEN_DISJOINT,
            reevaluation: str | None = None) -> dict[str, Any]:
    ordered = tuple(sorted(evidence, key=lambda ref: (ref.family, ref.id)))
    chosen = ordered if opportunities is None else tuple(sorted(opportunities, key=lambda ref: (ref.family, ref.id)))
    if direction == policy.DIRECTION_TEMPORARY_GUARD and reevaluation is None:
        reevaluation = "reevaluate after five relevant Runs or expire in thirty days"
    return policy.request_record(policy.PolicyChangeRequest(
        policy_surface_id=surface, direction=direction, after_setting=after, evidence=ordered,
        opportunity_definition="every Review Run whose discovery settled", opportunities=chosen,
        expected_effect="more supported Problems found per relevant Run",
        validation_plan="compare supported findings per relevant run before and after",
        measurement_contract=policy.MeasurementContract("m1", "supported Problems per relevant Run", True),
        observation_window=policy.ObservationWindow(2, 10), success_criteria="more supported Problems per Run",
        rollback_threshold="no extra supported Problem after ten Runs", environment=ENVIRONMENT,
        overlap_classification=overlap, supersedes=tuple(sorted(supersedes)), rolls_back=rolls_back,
        reevaluation=reevaluation,
    ))


def problems(world: World, state: policy.PolicyState, record: dict[str, Any]) -> list[str]:
    candidate = policy.build_candidate(record, NEW_ID, state, world)
    return [code for code, _ in policy.candidate_problems(candidate, state, world)]


def frozen_with(world: World, state: policy.PolicyState) -> dict[str, Any]:
    """The Effective Policy a Run resolved under ``state`` froze."""
    return dict(state.effective)


def evaluation(world: World, state: policy.PolicyState, change_id: str, result: str, next_action: str,
               evidence: tuple[policy.EvidenceRef, ...] = (), *, environment: policy.EnvironmentInput = ENVIRONMENT,
               basis: str | None = None, basis_digest: str | None = None) -> dict[str, Any]:
    ordered = tuple(sorted(evidence, key=lambda ref: (ref.family, ref.id)))
    found = policy.evaluation_request_record(policy.PolicyEvaluationRequest(
        policy_change_id=change_id, result=result, evidence=ordered, environment=environment,
        rationale="the observation window shows the expected effect", next_action=next_action,
        environment_basis=basis, environment_basis_digest=basis_digest))
    return policy.evaluation_record(found, ident("rpe", 999), state, world)


# =========================================================================== the single-event floor (§15.15, §30.9)

class SingleEventTests(unittest.TestCase):
    def test_one_opportunity_never_makes_a_permanent_adaptation(self) -> None:
        world = World()
        one = world.run(1)
        for surface, direction, after in ((REQ, policy.DIRECTION_STRENGTHEN, 2), (EXTRA, policy.DIRECTION_STRENGTHEN, 1)):
            with self.subTest(surface):
                evidence = (one,) if surface == REQ else (world.repair(1, 1),)
                self.assertIn(policy.CODE_SINGLE_EVENT, problems(world, state_of(world), request(
                    surface, direction, after, evidence)))
        self.assertEqual([], problems(world, state_of(world), request(REQ, policy.DIRECTION_STRENGTHEN, 2,
                                                                      (one, world.run(2)))))

    def test_a_duplicate_is_never_a_second_opportunity(self) -> None:
        world = World()
        run = world.run(1)
        finding = world.finding(1, run=1)
        # two refs of one Review Run are one opportunity
        self.assertIn(policy.CODE_SINGLE_EVENT, problems(world, state_of(world), request(
            REQ, policy.DIRECTION_STRENGTHEN, 2, (run, finding))))
        # the same source twice is refused outright
        with self.assertRaises(StopError) as raised:
            request(REQ, policy.DIRECTION_STRENGTHEN, 2, (run, run))
        self.assertEqual(policy.CODE_DUPLICATE_EVIDENCE, raised.exception.code)

    def test_a_relation_and_the_record_it_relates_are_one_opportunity(self) -> None:
        """RB6B-M2 (Scenario E): a relation is the opportunity of its target's Run, never a second identity."""
        world = World()
        repair = world.repair(1, run=1)
        induced = world.relation(1, history.ENDPOINT_REPAIR, ident("rrb", 1),
                                 relation_type=history.RELATION_REPAIR_INDUCED)
        self.assertIn(policy.CODE_SINGLE_EVENT, problems(world, state_of(world), request(
            EXTRA, policy.DIRECTION_STRENGTHEN, 3, (repair, induced))))
        finding = world.finding(2, run=2)
        recurrence = world.relation(2, history.ENDPOINT_FINDING, ident("rfd", 2),
                                    relation_type=history.RELATION_CROSS_RUN_RECURRENCE)
        self.assertIn(policy.CODE_SINGLE_EVENT, problems(world, state_of(world), request(
            REQ, policy.DIRECTION_STRENGTHEN, 2, (finding, recurrence))))
        self.assertEqual(ident("rr", 2), policy.opportunity(world, recurrence.to_record(), REQ))
        # a relation whose target's Run cannot be read is no opportunity at all
        dangling = world.relation(3, history.ENDPOINT_FINDING, ident("rfd", 77))
        self.assertIsNone(policy.opportunity(world, dangling.to_record(), REQ))

    def test_the_denominator_is_relevant_opportunity_and_an_unexercised_surface_is_none(self) -> None:
        world = World()
        settled = world.run(1)
        unsettled = world.run(2, generation=1)
        self.assertEqual(ident("rr", 1), policy.opportunity(world, settled.to_record(), REQ))
        self.assertIsNone(policy.opportunity(world, unsettled.to_record(), REQ), "discovery never settled")
        # extra_scope_steps is exercised only by a repaired Run; a no-finding Run is not an opportunity of it
        repaired = world.run(3, disposition=history.DISPOSITION_REPAIRED)
        self.assertIsNone(policy.opportunity(world, settled.to_record(), EXTRA))
        self.assertEqual(ident("rr", 3), policy.opportunity(world, repaired.to_record(), EXTRA))
        self.assertIsNone(policy.opportunity(world, world.finding(1, run=1).to_record(), EXTRA))
        # an unsupported relation is never confirmed causality
        weak = world.relation(1, history.ENDPOINT_RUN, ident("rr", 1), status=history.CAUSAL_UNRESOLVED)
        self.assertIsNone(policy.opportunity(world, weak.to_record(), REQ))
        self.assertIn(policy.CODE_SINGLE_EVENT, problems(world, state_of(world), request(
            REQ, policy.DIRECTION_STRENGTHEN, 2, (settled, unsettled))))

    def test_evidence_families_are_enumerated_not_derived(self) -> None:
        """RB6B-L11: a later history family is not P6 evidence until a reviewed contract admits it."""
        self.assertEqual((paths.HISTORY_RUNS, paths.HISTORY_FINDINGS, paths.HISTORY_REPAIRS, paths.HISTORY_RELATIONS,
                          paths.HISTORY_HUMAN_DECISIONS, policy.POLICY_EVIDENCE_EVALUATIONS), policy.EVIDENCE_FAMILIES)
        self.assertTrue(policy.evidence_ref_problems(
            {"family": "achievements", "id": ident("rr", 1), "digest": "a" * 64}, "ref"))


# =========================================================================== temporary_guard (§15.15, §30.9)

class TemporaryGuardTests(unittest.TestCase):
    def test_a_guard_originates_from_one_serious_supported_escape(self) -> None:
        """RB6B-L3: one ordinary Run is not an escape; a supported escape relation or a HIGH / MID Problem is."""
        world = World()
        ordinary = world.run(1)
        self.assertIn(policy.CODE_GUARD_INVALID, problems(world, state_of(world), request(
            REQ, policy.DIRECTION_TEMPORARY_GUARD, 4, (ordinary,))))
        low = world.finding(1, run=1, severity="LOW")
        self.assertIn(policy.CODE_GUARD_INVALID, problems(world, state_of(world), request(
            REQ, policy.DIRECTION_TEMPORARY_GUARD, 4, (low,))))
        escape = world.relation(1, history.ENDPOINT_RUN, ident("rr", 2))
        world.run(2)
        self.assertEqual([], problems(world, state_of(world), request(REQ, policy.DIRECTION_TEMPORARY_GUARD, 4,
                                                                      (escape,))))
        serious = world.finding(2, run=3, severity="MID")
        self.assertEqual([], problems(world, state_of(world), request(REQ, policy.DIRECTION_TEMPORARY_GUARD, 2,
                                                                      (serious,))))

    def test_a_guard_only_strengthens_and_carries_its_reevaluation(self) -> None:
        world = World()
        change = world.change(1, REQ, policy.DIRECTION_STRENGTHEN, 1, 3)
        escape = world.finding(1, run=1)
        state = state_of(world, {REQ: (3, change)}, (change,))
        self.assertIn(policy.CODE_GUARD_INVALID, problems(world, state, request(
            REQ, policy.DIRECTION_TEMPORARY_GUARD, 2, (escape,), supersedes=(change,), overlap=policy.OVERLAP_KNOWN)))
        with self.assertRaises(StopError) as raised:
            policy.request_record(replace(_raw_request(REQ, policy.DIRECTION_TEMPORARY_GUARD, 4, (escape,)),
                                          reevaluation=None))
        self.assertEqual(policy.CODE_GUARD_INVALID, raised.exception.code)

    def test_a_guard_never_ends_observation_into_permanence(self) -> None:
        """RB6B-H1 (Scenario D): no evaluation makes a guard permanent - not even with plenty of observed evidence."""
        world = World()
        guard = world.change(1, REQ, policy.DIRECTION_TEMPORARY_GUARD, 1, 4, minimum=1)
        state = state_of(world, {REQ: (4, guard)}, (guard,))
        observed = tuple(world.run(number, frozen=state.effective) for number in (1, 2, 3))
        with self.assertRaises(StopError) as raised:
            evaluation(world, state, guard, policy.RESULT_RETAIN, policy.NEXT_END_OBSERVATION, observed)
        self.assertEqual(policy.CODE_GUARD_INVALID, raised.exception.code)
        # a stored retain of a guard (written around the owner) settles nothing and is a validation Problem
        world.evaluation(1, guard, policy.RESULT_RETAIN, observed)
        self.assertEqual(set(), policy.ended_experiments(world))
        self.assertEqual((guard,), tuple(item.policy_change_id for item in state_of(world, {REQ: (4, guard)},
                                                                                     (guard,)).active))

    def test_the_repeated_evidence_path_makes_a_guard_permanent(self) -> None:
        """§15.15: a reviewed strengthen superseding the guard at its setting, under the two-opportunity floor."""
        world = World()
        guard = world.change(1, REQ, policy.DIRECTION_TEMPORARY_GUARD, 1, 3)
        state = state_of(world, {REQ: (3, guard)}, (guard,))
        one, two = world.run(1), world.run(2)
        confirm = request(REQ, policy.DIRECTION_STRENGTHEN, 3, (one, two), supersedes=(guard,),
                          overlap=policy.OVERLAP_KNOWN)
        self.assertEqual([], problems(world, state, confirm))
        candidate = policy.build_candidate(confirm, NEW_ID, state, world)
        self.assertEqual([{"policy_surface_id": REQ, "strength_class": policy.CLASS_DEFAULT, "setting": 3,
                           "direction": "strengthen", "supporting_policy_change_id": NEW_ID}],
                         candidate["after_profile"]["overrides"])
        self.assertEqual([NEW_ID], candidate["after_profile"]["active_experiment_refs"])
        self.assertIn(policy.CODE_SINGLE_EVENT, problems(world, state, request(
            REQ, policy.DIRECTION_STRENGTHEN, 3, (one,), supersedes=(guard,), overlap=policy.OVERLAP_KNOWN)))
        # without superseding the guard the same Candidate changes nothing and is refused
        self.assertIn(policy.CODE_DIRECTION_INVALID, problems(world, state, request(
            REQ, policy.DIRECTION_STRENGTHEN, 3, (one, two), overlap=policy.OVERLAP_KNOWN)))


def _raw_request(surface: str, direction: str, after: int, evidence: tuple[policy.EvidenceRef, ...]
                 ) -> policy.PolicyChangeRequest:
    ordered = tuple(sorted(evidence, key=lambda ref: (ref.family, ref.id)))
    return policy.PolicyChangeRequest(
        policy_surface_id=surface, direction=direction, after_setting=after, evidence=ordered,
        opportunity_definition="every Review Run whose discovery settled", opportunities=ordered,
        expected_effect="more supported Problems found per relevant Run", validation_plan="compare per relevant run",
        measurement_contract=policy.MeasurementContract("m1", "supported Problems per relevant Run", True),
        observation_window=policy.ObservationWindow(2, 10), success_criteria="more supported Problems per Run",
        rollback_threshold="no extra supported Problem after ten Runs", environment=ENVIRONMENT,
        overlap_classification=policy.OVERLAP_PROVEN_DISJOINT,
        reevaluation="reevaluate after five relevant Runs" if direction == policy.DIRECTION_TEMPORARY_GUARD else None,
    )


# =========================================================================== lightening and holdout (§15.17, §30.10-§30.11)

class LighteningHoldoutTests(unittest.TestCase):
    def test_both_lightening_surfaces_keep_the_old_behaviour_as_holdout(self) -> None:
        world = World()
        for surface, before, after in ((REQ, 3, 2), (EXTRA, 2, 1)):
            with self.subTest(surface):
                change = world.change(10 + before, surface, policy.DIRECTION_STRENGTHEN, 0, before)
                state = state_of(world, {surface: (before, change)}, (change,))
                evidence = (world.run(before * 10), world.run(before * 10 + 1)) if surface == REQ else (
                    world.run(before * 10 + 2, disposition=history.DISPOSITION_REPAIRED),
                    world.run(before * 10 + 3, disposition=history.DISPOSITION_REPAIRED))
                record = request(surface, policy.DIRECTION_LIGHTEN, after, evidence, supersedes=(change,),
                                 overlap=policy.OVERLAP_KNOWN)
                candidate = policy.build_candidate(record, NEW_ID, state, world)
                self.assertEqual({"policy_surface_id": surface, "holdout_setting": before,
                                  "selection": policy.HOLDOUT_SELECTION_ALL_RELEVANT}, candidate["holdout_plan"])
                self.assertEqual([], [code for code, _ in policy.candidate_problems(candidate, state, world)])
                unmeasured = serialize.canonical_data(candidate)
                unmeasured["holdout_plan"] = None
                self.assertIn(policy.CODE_LIGHTENING_UNMEASURED,
                              [code for code, _ in policy.candidate_problems(unmeasured, state, world)])

    def test_the_effective_policy_runs_the_removed_behaviour_as_holdout(self) -> None:
        world = World()
        slots = world.change(1, REQ, policy.DIRECTION_LIGHTEN, 3, 2)
        steps = world.change(2, EXTRA, policy.DIRECTION_LIGHTEN, 2, 1)
        state = state_of(world, {REQ: (2, slots), EXTRA: (1, steps)}, (slots, steps))
        self.assertEqual(1, policy.required_holdout_slots(state.effective))
        self.assertEqual(((records.IMPACT_LOCAL, records.IMPACT_SHARED), (records.IMPACT_CONTRACT,)),
                         policy.reverification_levels(state.effective, records.IMPACT_LOCAL))

    def test_a_reverification_holdout_settles_before_the_repair_result_and_a_failure_blocks(self) -> None:
        """§30.11: accepted holdout settles before authorization; a supported defect it finds blocks (fail closed)."""
        world = World()
        steps = world.change(1, EXTRA, policy.DIRECTION_LIGHTEN, 1, 0)
        effective = state_of(world, {}, (steps,)).effective
        self.assertEqual(((records.IMPACT_LOCAL,), (records.IMPACT_SHARED,)),
                         policy.reverification_levels(effective, records.IMPACT_LOCAL))
        found = adjudication_fixture()
        batch = batch_fixture(found, "a" * 64)
        required = (p4.P4Verification("focused_tests", "pass"), p4.P4Verification("direct_consumers", "pass"))

        def result(*verification: p4.P4Verification) -> records.P4RepairResult:
            returned = p4.P4RepairReturn(
                task_id=REPAIR_TASK, repair_identity="repairer", repair_version="v1", status="completed", proposal={},
                repaired_surface=("src/a.py",), impact_class=p4.IMPACT_LOCAL, coverage_check=coverage(),
                verification=required + verification, causal_summary="changed the parser")
            return p4.repair_result(batch=batch, source_candidate_generation=1, result_candidate_hash="b" * 64,
                                    result_candidate_material_digest="c" * 64, repair_task_id=REPAIR_TASK,
                                    returned=returned, evidence=(), kind_checks=(), effective_policy=effective)

        with self.assertRaises(StopError) as raised:
            result()
        self.assertEqual(policy.CODE_HOLDOUT_UNSETTLED, raised.exception.code)
        with self.assertRaises(StopError) as raised:
            result(p4.P4Verification("integration_checks", "fail"), p4.P4Verification("representative_callers", "pass"))
        self.assertEqual(policy.CODE_HOLDOUT_FAILED, raised.exception.code)
        settled = result(p4.P4Verification("integration_checks", "pass"),
                         p4.P4Verification("representative_callers", "pass"))
        completed = {item["id"] for item in settled.reverification["completed"]}
        self.assertLessEqual({"integration_checks", "representative_callers"}, completed,
                             "holdout results stay in the existing completed list")

    def test_the_discovery_holdout_is_bound_exactly_and_independently(self) -> None:
        world = World()
        slots = world.change(1, REQ, policy.DIRECTION_LIGHTEN, 3, 2)
        effective = state_of(world, {REQ: (2, slots)}, (slots,)).effective
        bind = lambda viewpoint, identity: SimpleNamespace(viewpoint=viewpoint, identity=identity, version="1")
        required = (bind("a", "r1"), bind("b", "r2"))
        self.assertEqual(policy.CODE_HOLDOUT_UNBOUND, policy.discovery_slots_problem(effective, required, ())[0])
        self.assertEqual(policy.CODE_HOLDOUT_UNBOUND,
                         policy.discovery_slots_problem(effective, required, (bind("h", "r1"),))[0])
        self.assertIsNone(policy.discovery_slots_problem(effective, required, (bind("h", "h1"),)))
        self.assertEqual(policy.CODE_DISCOVERY_SLOTS_UNMET,
                         policy.discovery_slots_problem(effective, required[:1], (bind("h", "h1"),))[0])
        plain = state_of(World()).effective
        self.assertEqual(policy.CODE_HOLDOUT_NOT_APPLICABLE,
                         policy.discovery_slots_problem(plain, required[:1], (bind("h", "h1"),))[0])


# =========================================================================== overlap and supersede (§15.25, §30.25)

class OverlapTests(unittest.TestCase):
    def test_only_proven_disjoint_observes_concurrently(self) -> None:
        world = World()
        other = world.change(1, EXTRA, policy.DIRECTION_STRENGTHEN, 0, 1)
        same = world.change(2, REQ, policy.DIRECTION_STRENGTHEN, 1, 2)
        evidence = (world.run(1), world.run(2))
        disjoint = state_of(world, {EXTRA: (1, other)}, (other,))
        self.assertEqual([], problems(world, disjoint, request(REQ, policy.DIRECTION_STRENGTHEN, 2, evidence)))
        overlapping = state_of(world, {REQ: (2, same)}, (same,))
        self.assertIn(policy.CODE_OVERLAP_UNRESOLVED, problems(world, overlapping, request(
            REQ, policy.DIRECTION_STRENGTHEN, 3, evidence)))
        self.assertIn(policy.CODE_OVERLAP_UNRESOLVED, problems(world, overlapping, request(
            REQ, policy.DIRECTION_STRENGTHEN, 3, evidence, overlap=policy.OVERLAP_KNOWN)))
        self.assertEqual([], problems(world, overlapping, request(REQ, policy.DIRECTION_STRENGTHEN, 3, evidence,
                                                                  supersedes=(same,), overlap=policy.OVERLAP_KNOWN)))

    def test_a_candidate_never_supersedes_another_surfaces_experiment(self) -> None:
        """RB6B-M1 (Scenario A): superseding the disjoint lightening would drop its holdout."""
        world = World()
        lightening = world.change(1, REQ, policy.DIRECTION_LIGHTEN, 3, 2)
        state = state_of(world, {REQ: (2, lightening)}, (lightening,))
        found = problems(world, state, request(EXTRA, policy.DIRECTION_STRENGTHEN, 1,
                                               (world.run(1, disposition=history.DISPOSITION_REPAIRED),
                                                world.run(2, disposition=history.DISPOSITION_REPAIRED)),
                                               supersedes=(lightening,)))
        self.assertIn(policy.CODE_OVERLAP_UNRESOLVED, found)

    def test_a_lightening_is_never_ended_below_the_behaviour_its_holdout_measures(self) -> None:
        world = World()
        lightening = world.change(1, REQ, policy.DIRECTION_LIGHTEN, 3, 2)
        state = state_of(world, {REQ: (2, lightening)}, (lightening,))
        evidence = (world.run(1), world.run(2))
        self.assertIn(policy.CODE_LIGHTENING_UNMEASURED, problems(world, state, request(
            REQ, policy.DIRECTION_LIGHTEN, 1, evidence, supersedes=(lightening,), overlap=policy.OVERLAP_KNOWN)))
        self.assertEqual([], problems(world, state, request(REQ, policy.DIRECTION_STRENGTHEN, 3, evidence,
                                                            supersedes=(lightening,), overlap=policy.OVERLAP_KNOWN)))


# =========================================================================== rollback (§15.24; RB6B-L4)

class RollbackTests(unittest.TestCase):
    def test_a_rollback_restores_exactly_the_change_that_governs_the_surface(self) -> None:
        world = World()
        first = world.change(1, REQ, policy.DIRECTION_STRENGTHEN, 1, 2)
        second = world.change(2, REQ, policy.DIRECTION_STRENGTHEN, 2, 4)
        state = state_of(world, {REQ: (4, second)}, (second,))
        evidence = (world.run(1),)
        # Scenario B2: "rollback" of the superseded first change, three steps down - refused
        self.assertIn(policy.CODE_DIRECTION_INVALID, problems(world, state, request(
            REQ, policy.DIRECTION_ROLLBACK, 1, evidence, rolls_back=first, supersedes=(second,),
            overlap=policy.OVERLAP_KNOWN)))
        # the governing change restored exactly: one step, its own before setting, with the holdout it now needs
        record = request(REQ, policy.DIRECTION_ROLLBACK, 2, evidence, rolls_back=second, overlap=policy.OVERLAP_KNOWN)
        self.assertEqual([], problems(world, state, record))
        self.assertIn(policy.CODE_DIRECTION_INVALID, problems(world, state, request(
            REQ, policy.DIRECTION_ROLLBACK, 1, evidence, rolls_back=second, overlap=policy.OVERLAP_KNOWN)))


# =========================================================================== evaluations (§15.24, §30.23-§30.24)

class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = World()
        self.change = self.world.change(1, REQ, policy.DIRECTION_LIGHTEN, 3, 2, minimum=2)
        self.state = state_of(self.world, {REQ: (2, self.change)}, (self.change,))

    def observed(self, *numbers: int) -> tuple[policy.EvidenceRef, ...]:
        return tuple(self.world.run(number, frozen=self.state.effective) for number in numbers)

    def test_retain_without_observed_evidence_never_ends_a_holdout(self) -> None:
        """RB6B-H1 (Scenario C): no evidence, pre-change evidence or one Run never retains a lightening."""
        before = state_of(World()).effective
        pre_change = tuple(self.world.run(number, frozen=before) for number in (10, 11, 12))
        for name, evidence in (("no evidence", ()), ("pre-change Runs", pre_change), ("one Run", self.observed(1)),
                               ("one Run twice", self.observed(2) + (self.world.finding(1, run=2),))):
            with self.subTest(name), self.assertRaises(StopError) as raised:
                evaluation(self.world, self.state, self.change, policy.RESULT_RETAIN, policy.NEXT_END_OBSERVATION,
                           evidence)
            self.assertEqual(policy.CODE_EVALUATION_INVALID, raised.exception.code)

    def test_retain_needs_opportunities_observed_with_the_holdout_in_force(self) -> None:
        unholding = dict(self.state.effective)
        unholding["active_experiments"] = [dict(item, holdout_setting=None) for item in unholding["active_experiments"]]
        wrong = tuple(self.world.run(number, frozen=unholding) for number in (20, 21))
        with self.assertRaises(StopError):
            evaluation(self.world, self.state, self.change, policy.RESULT_RETAIN, policy.NEXT_END_OBSERVATION, wrong)
        record = evaluation(self.world, self.state, self.change, policy.RESULT_RETAIN, policy.NEXT_END_OBSERVATION,
                            self.observed(1, 2))
        self.assertEqual((policy.RESULT_RETAIN, policy.NEXT_END_OBSERVATION), (record["result"], record["next_action"]))

    def test_a_settled_experiment_leaves_the_effective_active_set(self) -> None:
        self.assertEqual(1, policy.required_holdout_slots(self.state.effective))
        self.world.evaluation(1, self.change, policy.RESULT_RETAIN, self.observed(1, 2))
        self.assertEqual({self.change}, policy.ended_experiments(self.world))
        after = state_of(self.world, {REQ: (2, self.change)}, (self.change,))
        self.assertEqual((), after.active)
        self.assertEqual(0, policy.required_holdout_slots(after.effective))

    def test_an_unfounded_stored_retain_settles_nothing(self) -> None:
        self.world.evaluation(1, self.change, policy.RESULT_RETAIN, self.observed(1))
        self.assertEqual(set(), policy.ended_experiments(self.world))
        self.assertEqual(1, policy.required_holdout_slots(
            state_of(self.world, {REQ: (2, self.change)}, (self.change,)).effective))

    def test_adjust_and_rollback_need_a_new_candidate_and_inconclusive_is_never_success(self) -> None:
        for result in (policy.RESULT_ADJUST, policy.RESULT_ROLLBACK):
            for wrong in (policy.NEXT_END_OBSERVATION, policy.NEXT_CONTINUE_OBSERVATION):
                with self.subTest(f"{result} then {wrong}"), self.assertRaises(StopError):
                    evaluation(self.world, self.state, self.change, result, wrong)
            self.assertEqual(policy.NEXT_NEW_CANDIDATE, evaluation(
                self.world, self.state, self.change, result, policy.NEXT_NEW_CANDIDATE)["next_action"])
        with self.assertRaises(StopError):
            evaluation(self.world, self.state, self.change, policy.RESULT_INCONCLUSIVE, policy.NEXT_END_OBSERVATION)
        self.assertEqual(policy.NEXT_CONTINUE_OBSERVATION, evaluation(
            self.world, self.state, self.change, policy.RESULT_INCONCLUSIVE,
            policy.NEXT_CONTINUE_OBSERVATION)["next_action"])
        strict = self.world.change(2, EXTRA, policy.DIRECTION_STRENGTHEN, 0, 1, continued=False)
        state = state_of(self.world, {REQ: (2, self.change), EXTRA: (1, strict)}, (self.change, strict))
        with self.assertRaises(StopError):
            evaluation(self.world, state, strict, policy.RESULT_INCONCLUSIVE, policy.NEXT_CONTINUE_OBSERVATION)

    def test_a_material_environment_change_needs_a_stored_positive_basis(self) -> None:
        """§15.26 / RB6B-L10: chronology is never causality; the basis is stored evidence, never any digest."""
        changed = policy.EnvironmentInput(("discovery 2",), ("planning-validator",), "py3")
        evidence = self.observed(1, 2)
        with self.assertRaises(StopError) as raised:
            evaluation(self.world, self.state, self.change, policy.RESULT_RETAIN, policy.NEXT_END_OBSERVATION,
                       evidence, environment=changed)
        self.assertEqual(policy.CODE_ENVIRONMENT_UNATTRIBUTED, raised.exception.code)
        self.assertEqual(policy.RESULT_INCONCLUSIVE, evaluation(
            self.world, self.state, self.change, policy.RESULT_INCONCLUSIVE, policy.NEXT_CONTINUE_OBSERVATION,
            evidence, environment=changed)["result"])
        with self.assertRaises(StopError) as raised:
            evaluation(self.world, self.state, self.change, policy.RESULT_RETAIN, policy.NEXT_END_OBSERVATION,
                       evidence, environment=changed, basis=policy.ENVIRONMENT_IRRELEVANCE_PROOF,
                       basis_digest="d" * 64)
        self.assertEqual(policy.CODE_ENVIRONMENT_UNATTRIBUTED, raised.exception.code)
        proof = self.world.finding(5, run=1, severity="LOW", category=records.OUTCOME_IMPROVEMENT)
        record = evaluation(self.world, self.state, self.change, policy.RESULT_RETAIN, policy.NEXT_END_OBSERVATION,
                            evidence + (proof,), environment=changed, basis=policy.ENVIRONMENT_IRRELEVANCE_PROOF,
                            basis_digest=proof.digest)
        self.assertEqual(proof.digest, record["environment_basis_digest"])
        tampered = dict(record, environment_basis_digest="e" * 64)
        with self.assertRaises(ValidationError):
            policy.parse_evaluation(tampered, "an evaluation")

    def test_an_evaluation_of_a_settled_or_unknown_experiment_is_refused(self) -> None:
        with self.assertRaises(StopError) as raised:
            evaluation(self.world, self.state, ident("rpc", 55), policy.RESULT_INCONCLUSIVE,
                       policy.NEXT_CONTINUE_OBSERVATION)
        self.assertEqual(policy.CODE_EVALUATION_INVALID, raised.exception.code)


# =========================================================================== the self-contained meta-verifier (RB6B-M8)

class MetaVerifierShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = World()
        self.state = state_of(self.world)
        self.candidate = policy.build_candidate(
            request(REQ, policy.DIRECTION_STRENGTHEN, 2, (self.world.run(1), self.world.run(2))), NEW_ID, self.state,
            self.world)

    def codes(self, candidate: Any) -> list[str]:
        return [code for code, _ in policy.candidate_problems(candidate, self.state, self.world)]

    def test_the_valid_candidate_passes_and_its_request_is_re_derived_exactly(self) -> None:
        self.assertEqual([], self.codes(self.candidate))
        self.assertEqual(self.candidate["request_digest"],
                         policy.request_digest(policy.request_of_candidate(self.candidate)))

    def test_scenario_f_every_structural_and_h3_defect_is_a_coded_problem(self) -> None:
        tampered = serialize.canonical_data(self.candidate)
        tampered["request_digest"] = "0" * 64
        self.assertIn(policy.CODE_CANDIDATE_INVALID, self.codes(tampered))
        for name, change in (
            ("window min > max", lambda c: c["observation_window"].update(minimum_opportunities=9,
                                                                          maximum_opportunities=1)),
            ("secret text", lambda c: c.update(expected_effect="C:\\Users\\someone\\secret token=abc")),
            ("empty validation plan", lambda c: c.update(validation_plan="")),
        ):
            tampered = serialize.canonical_data(self.candidate)
            change(tampered)
            with self.subTest(name):
                self.assertIn(policy.CODE_CANDIDATE_INVALID, self.codes(tampered))

    def test_a_malformed_field_never_raises(self) -> None:
        for name, change in (
            ("measurement contract", lambda c: c.update(measurement_contract={"metric": "x"})),
            ("environment", lambda c: c.update(environment_identity=[])),
            ("evidence item", lambda c: c.update(evidence=["x"])),
            ("opportunities", lambda c: c["relevant_opportunity"].update(opportunities=None)),
            ("holdout plan", lambda c: c.update(holdout_plan={"x": 1})),
            ("unhashable surface", lambda c: c.update(affected_policy_surface=["x"])),
            ("missing field", lambda c: c.pop("overlap")),
        ):
            tampered = serialize.canonical_data(self.candidate)
            change(tampered)
            with self.subTest(name):
                found = self.codes(tampered)
                self.assertTrue(found, "a malformed Candidate is refused")
        self.assertTrue(self.codes("not a mapping"))

    def test_an_unhashable_surface_is_a_coded_refusal(self) -> None:
        """RB6B-L1."""
        self.assertEqual(policy.CODE_SURFACE_UNKNOWN, policy.surface_problem([])[0])
        self.assertEqual(policy.CODE_SURFACE_UNKNOWN, policy.surface_problem({"a": 1})[0])
        world = World()
        change = world.change(1, REQ, policy.DIRECTION_STRENGTHEN, 1, 2)
        record = state_of(world, {REQ: (2, change)}, (change,)).profile.to_record()
        record["overrides"][0]["policy_surface_id"] = ["x"]
        self.assertIn(policy.CODE_SURFACE_UNKNOWN, [code for code, _ in policy.profile_problems(record, "p")])


if __name__ == "__main__":
    unittest.main()
