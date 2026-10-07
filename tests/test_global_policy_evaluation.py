"""P7 §31.57 / §31.41-§31.43 / §31.20: Global observation, evaluation and rollback, end to end.

Through :func:`workline.global_policy.record_global_policy_evaluation` and the
change owner:

* an evaluation is one immutable evaluation record, committed alone and
  published exactly - never a policy write (evaluation-only persistence,
  §31.42; statically too: the sub-operation's closed effect set has no
  policy replace);
* ``inconclusive`` is not success; ``retain`` ends observation; ``adjust`` and
  ``rollback`` call for a new reviewed Candidate;
* the exact rollback exception (§31.20) needs no fresh cross-Project trend and
  is a NEW higher Global version - never the old bytes again; a rollback that
  names the exception without its exact proof is ``review_p7_rollback_inexact``;
  a rollback that does not name it meets ordinary eligibility by its actual
  movement (the stronger lightening floor);
* correlated sources are one cluster: never many confirmations, for a change or
  for an evaluation (§31.43);
* the evaluation binds its environment (attribution) and its exact change.

``retain`` / ``adjust`` / ``rollback`` rest on Relevant Opportunities OBSERVED
under the change (a source Run that froze it as an active Global experiment):
those rows wait for RB7-F's Global-origin experiments (``OBSERVED_WAITS``).
"""

from __future__ import annotations

import ast
import unittest

from global_policy_helpers import (
    ENVIRONMENT, EVALUATION_SUBJECT, GLOBAL_POLICY_REL, KP_SUBJECT, OBSERVED_WAITS, SLOTS, GlobalPolicyCase,
    change_request, discovery_actors, evaluation_environment, evaluation_request, maintenance, observed_sources,
    owner, root_review, sources, wait_for,
)
from helpers import SRC
from workline.review import policy, serialize

OWNER_TEXT = (SRC / "workline" / "global_policy.py").read_text(encoding="utf-8")


def _code(exception: BaseException) -> str:
    return str(getattr(exception, "code", ""))


class EvaluationOnlyStaticTests(unittest.TestCase):
    def test_the_evaluation_sub_operation_plans_one_evaluation_record_and_nothing_else(self) -> None:
        tree = ast.parse(OWNER_TEXT)
        found = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_plan_evaluation"]
        self.assertEqual(1, len(found))
        body = ast.unparse(found[0])
        self.assertIn("root_maintenance.EFFECT_EVALUATION_CREATE", body)
        for other in ("EFFECT_GLOBAL_POLICY_REPLACE", "EFFECT_CHANGE_CREATE", "EFFECT_PATCH_NOTE_CREATE",
                      "EFFECT_PACKET_CREATE", "EFFECT_CONSUMPTION_CREATE", "EFFECT_REVIEW_CREATE"):
            with self.subTest(other=other):
                self.assertNotIn(other, body)

    @wait_for("WAIT_LEAF_RB7_B")
    def test_the_evaluation_operation_can_never_replace_the_policy(self) -> None:
        found = maintenance()
        effects = found.OPERATION_EFFECTS[found.OPERATION_EVALUATION]
        self.assertNotIn(found.EFFECT_GLOBAL_POLICY_REPLACE, effects)
        self.assertEqual({found.EFFECT_EVALUATION_CREATE, found.EFFECT_COMMIT, found.EFFECT_PUSH}, set(effects))


class _EvaluationCase(GlobalPolicyCase):
    source_count = 3

    def evaluation(self, change_id: str, **kwargs: object) -> object:
        return self.evaluate(evaluation_request(change_id, self.sources, **kwargs))

    def stored_evaluation(self, result: object) -> dict:
        raw = self.blob(result.commit, f"review-policy/evaluations/{result.evaluation_id}.yaml")
        return serialize.parse_canonical(raw, "the evaluation")[0]

    def assertEvaluationOnly(self, result: object, policy_before: bytes) -> None:
        self.assertEqual(result.commit, self.head())
        self.assertEqual(result.commit, self.commits_with(EVALUATION_SUBJECT)[0])
        delta = self.delta(result.commit)
        self.assertEqual({f"review-policy/evaluations/{result.evaluation_id}.yaml": "A"},
                         {path: item.status for path, item in delta.items()})
        self.assertEqual(policy_before, self.blob("HEAD", GLOBAL_POLICY_REL), "an evaluation never writes the policy")
        self.assertEqual([], self.pending_records())
        self.assertNoProjectNamespace()

    def refused(self, call: object, code_suffix: str) -> BaseException:
        head = self.head()
        with self.assertRaises(Exception) as raised:
            call()
        self.assertTrue(_code(raised.exception).endswith(code_suffix), f"{_code(raised.exception)}: {raised.exception}")
        self.assertEqual(head, self.head())
        self.assertEqual([], self.pending_records())
        return raised.exception


@wait_for()
class EvaluationTests(_EvaluationCase):
    def test_inconclusive_is_one_immutable_evaluation_never_success_and_no_policy_write(self) -> None:
        change = self.applied()
        policy_before = self.blob("HEAD", GLOBAL_POLICY_REL)
        result = self.evaluation(change.global_policy_change_id, result="inconclusive")
        self.assertEqual(("inconclusive", change.global_policy_change_id),
                         (result.result, result.global_policy_change_id))
        self.assertNotEqual(policy.NEXT_END_OBSERVATION, result.next_action, "inconclusive ends no observation")
        self.assertIn(result.next_action, policy.NEXT_ACTIONS)
        self.assertEvaluationOnly(result, policy_before)
        stored = self.stored_evaluation(result)
        self.assertEqual((change.global_policy_digest, 2),
                         (stored["evaluated_global_policy_digest"], stored["evaluated_global_policy_version"]))

    def test_the_evaluation_binds_its_environment_and_its_exact_change(self) -> None:
        change = self.applied()
        later = {**ENVIRONMENT, "toolchain": "py3-next"}
        result = self.evaluation(change.global_policy_change_id, environment=evaluation_environment(ENVIRONMENT, later))
        stored = self.stored_evaluation(result)
        self.assertEqual("py3-next", stored["environment"]["window_end"]["toolchain"])
        self.assertEqual(change.global_policy_change_id, stored["global_policy_change_id"])
        text = self.blob(result.commit, f"review-policy/evaluations/{result.evaluation_id}.yaml").decode("utf-8")
        for source in self.sources:
            self.assertNotIn(str(source.root), text, "no source path in a canonical root record")

    def test_an_evaluation_of_a_change_head_does_not_commit_writes_nothing(self) -> None:
        self.refused(lambda: self.evaluation("rgc_" + "0" * 26), "evaluation_invalid")

    def test_the_same_evaluation_request_resumes_with_the_same_evaluation_id(self) -> None:
        from global_policy_helpers import Crash, crash_at

        change = self.applied()
        request = evaluation_request(change.global_policy_change_id, self.sources)
        with crash_at(owner(), "_c2_evaluation"):
            with self.assertRaises(Crash):
                self.evaluate(request)
        (pending,) = self.pending_records()
        reserved = [value for key, value in pending["reserved_ids"].items() if key == owner().EVALUATION_KEY]
        result = self.evaluate(request)
        self.assertEqual(reserved, [result.evaluation_id])
        self.assertEqual(1, len(self.commits_with(EVALUATION_SUBJECT)))

    def test_a_later_change_is_a_new_packet_and_a_new_higher_version(self) -> None:
        first = self.applied()
        second = self.applied(self.request(direction="strengthen", after=3))
        self.assertEqual(3, second.global_policy_version)
        self.assertNotEqual(first.promotion_packet_id, second.promotion_packet_id)
        record = self.policy_record()
        self.assertEqual(policy.global_policy_digest(self.policy_record(first.policy_commit)),
                         record["parent_global_policy_digest"])
        self.assertEqual(3, policy.global_policy_settings(record)[SLOTS])

    def test_a_rollback_naming_the_exception_without_its_proof_is_inexact(self) -> None:
        change = self.applied()
        inconclusive = self.evaluation(change.global_policy_change_id)  # proves no threshold fired
        for evaluation_id in (inconclusive.evaluation_id, "rge_" + "0" * 26):
            with self.subTest(evaluation_id=evaluation_id):
                self.refused(lambda: self.change(change_request(
                    self.sources, direction="rollback", after=1, rollback_of=change.global_policy_change_id,
                    rollback_evaluation_id=evaluation_id)), "rollback_inexact")
        self.assertEqual(1, len(self.commits_with(KP_SUBJECT)))

    def test_a_rollback_without_the_exception_meets_the_lightening_floor(self) -> None:
        self.applied()
        # the movement lightens: three proven-independent clusters whose opportunities exercised the stronger
        # behaviour - evidence from before the change exercised none of it, from two sources or from three
        for found in (self.sources[:2], self.sources):
            with self.subTest(sources=len(found)):
                self.refused(lambda: self.change(change_request(found, direction="rollback", after=1),
                                                 review=root_review(reviewers=3)), "not_eligible")


@wait_for()
class CorrelationTests(_EvaluationCase):
    """§31.17 / §31.18: copies of one lineage are one cluster - one confirmation."""

    correlated = True

    def test_correlated_sources_never_make_a_change_eligible(self) -> None:
        self.refused(self.change, "not_eligible")
        self.assertEqual([], self.tracked("review-policy/promotion-packets/"))


@wait_for()
class EvaluationCorrelationTests(_EvaluationCase):
    def test_correlated_post_change_evidence_is_one_cluster(self) -> None:
        change = self.applied()
        correlated = sources(self, 3, correlated=True)
        result = self.evaluate(evaluation_request(change.global_policy_change_id, correlated))
        stored = self.stored_evaluation(result)
        self.assertEqual(1, len(stored["clusters"]["clusters"]), "correlated Projects are never many confirmations")


@wait_for()
class RemoteEvaluationTests(_EvaluationCase):
    remote = True

    def test_the_evaluation_commit_is_published_exactly(self) -> None:
        change = self.applied()
        before = self.remote_tip()
        result = self.evaluation(change.global_policy_change_id)
        self.assertEqual(result.commit, self.remote_tip())
        self.assertEqual(f"{before} {result.commit} refs/heads/main", self.remote_log()[-1])
        self.assertEqual(3, len(self.remote_log()), "Kp, Km, then the evaluation commit - each once")


@wait_for(*OBSERVED_WAITS)
class ObservedEvaluationTests(_EvaluationCase):
    """retain / adjust / rollback rest on opportunities observed under the change (§31.43)."""

    def observed(self, change: object) -> tuple:
        """Three new source Projects of the copied root, reviewed under ``change`` (it is their active experiment)."""
        return observed_sources(self, self.root, 3)

    def test_retain_ends_observation_and_leaves_the_policy(self) -> None:
        change = self.applied()
        policy_before = self.blob("HEAD", GLOBAL_POLICY_REL)
        result = self.evaluate(evaluation_request(change.global_policy_change_id, self.observed(change),
                                                  result="retain", rationale="the expected effect held"))
        self.assertEqual(("retain", policy.NEXT_END_OBSERVATION), (result.result, result.next_action))
        self.assertEvaluationOnly(result, policy_before)

    def test_adjust_calls_for_a_new_reviewed_candidate(self) -> None:
        change = self.applied()
        policy_before = self.blob("HEAD", GLOBAL_POLICY_REL)
        result = self.evaluate(evaluation_request(change.global_policy_change_id, self.observed(change),
                                                  result="adjust", rationale="the effect holds and needs tuning"))
        self.assertEqual(policy.NEXT_NEW_CANDIDATE, result.next_action)
        self.assertEvaluationOnly(result, policy_before)

    def test_an_ordinary_lightening_rollback_needs_the_stronger_floor_and_is_a_new_version(self) -> None:
        change = self.applied()
        observed = self.observed(change)
        # three independent sources that exercised the stronger setting, but two reviewers: max(3, before slots)
        self.refused(lambda: self.change(change_request(observed, direction="rollback", after=1)),
                     "reviewer_floor_unmet")
        rollback = self.applied(change_request(observed, direction="rollback", after=1),
                                review=root_review(reviewers=3))
        self.assertEqual(3, rollback.global_policy_version, "a rollback is a new, higher version")
        self.assertEqual(1, policy.global_policy_settings(self.policy_record())[SLOTS])
        self.assertNotEqual(self.blob(f"{self.commits_with(KP_SUBJECT)[-1]}^", GLOBAL_POLICY_REL),
                            self.blob("HEAD", GLOBAL_POLICY_REL), "never the old bytes again: history moves forward")

    def test_an_exact_rollback_is_a_new_version_reviewed_without_a_fresh_trend(self) -> None:
        change = self.applied()
        v2 = self.policy_record()
        observed = self.observed(change)
        evaluation = self.evaluate(evaluation_request(change.global_policy_change_id, observed, result="rollback",
                                                      rationale="the frozen rollback threshold fired"))
        self.assertEqual(policy.NEXT_NEW_CANDIDATE, evaluation.next_action)
        # the exception needs no fresh cross-Project trend: one lineage, two reviewers (max(2, before slots))
        rollback = self.applied(change_request(observed[:1], direction="rollback", after=1,
                                               rollback_of=change.global_policy_change_id,
                                               rollback_evaluation_id=evaluation.evaluation_id),
                                review=root_review(*discovery_actors(2)))
        v3 = self.policy_record()
        self.assertEqual(3, rollback.global_policy_version)
        self.assertEqual(policy.global_policy_digest(v2), v3["parent_global_policy_digest"])
        self.assertEqual(1, policy.global_policy_settings(v3)[SLOTS])
        packet = serialize.parse_canonical(
            self.blob("HEAD", f"review-policy/promotion-packets/{rollback.promotion_packet_id}.yaml"), "the packet")[0]
        self.assertEqual({"global_policy_change_id": change.global_policy_change_id,
                          "evaluation_id": evaluation.evaluation_id}, packet["rollback_exception"])


if __name__ == "__main__":
    unittest.main()
