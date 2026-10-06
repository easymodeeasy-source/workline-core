"""P6 §30.40, policy persistence windows 10-21: interruption / recovery after the G5 Receipt.

Each row stops the process at one instant of the persistence chain of a Policy Change - change record + exact
Profile CAS -> Kp -> C-2(Kp) -> publish Kp -> Policy Consumption v3 + P5 Run summary -> Km -> C-2(Km) -> publish Km
-> complete - and runs the same request again. The techniques are the repo's own: ``Mutation.add_effects`` /
``MutationController.apply_effect`` windows (recorded but not applied; applied with its flag not saved),
``crash_at`` around the owner's proof steps, and the REAL pre-receive hook of the local bare remote refusing a push.
Every retry must end ``applied`` with the §30.40 retry invariants
(``project_policy_helpers.InterruptionCase.assert_invariants``) - except the two windows where a Git stage's commit
was made and the interruption kept its ID from being saved (13b / 18b): there the established P3 / P4 contract is a
fail-closed reconcile with nothing published (``UnownedCommitCase``), and the retry invariants hold on what is left.
"""

from __future__ import annotations

from project_policy_helpers import (
    KM_SUBJECT, KP_SUBJECT, Crash, InterruptionCase, Interrupted, after_effect, after_recording, before_effect,
    before_owner_completion, crash_at,
)
from workline import project_policy
from workline.errors import ReconcileRequired
from workline.review import paths, policy

STATE = project_policy.STAGE_POLICY
PROFILE = paths.POLICY_PROFILE_REL
CONSUMPTIONS = paths.consumption_rel("rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV").rsplit("/", 1)[0] + "/"
RUN_SUMMARIES = paths.history_run_rel("rr_01ARZ3NDEKTSV4RRFFQ69G5FAV").rsplit("/", 1)[0] + "/"


class UnownedCommitCase(InterruptionCase):
    """A Git stage whose commit was made just before the interruption kept its ID from being saved.

    The established P3 / P4 contract for this window (``tests/test_review_planning_publication.py`` row 22,
    ``UnownedKpTests``): a commit the record holds without the ID of a commit this mutation made cannot be shown to
    be its own, so the proof fails closed - reconcile required, nothing published, nothing forced, nothing rewritten -
    and the §30.40 retry invariants hold on what is left: the same pending mutation and reserved IDs, one change
    record, no Profile version skip, no duplicate Consumption or publication.
    """

    def unowned(self, stage: str) -> None:
        remote_before = self.remote_main() if self.template == "remote" else None
        request = self.request()  # the same request again: its evidence is what it was when first asked
        with after_effect("git_commit", stage), self.assertRaises(Interrupted):
            self.change(request)
        (pending,) = self.policy_pending()
        with self.assertRaises(ReconcileRequired) as raised:
            self.change(request)
        self.assertIn(raised.exception.reason, policy.RECONCILE_REASONS)
        (again,) = self.policy_pending()
        self.assertEqual((pending["mutation_id"], pending["reserved_ids"]), (again["mutation_id"], again["reserved_ids"]))
        review = self.review_store
        self.assertEqual(1, len(review.policy_change_ids()), "no duplicate change record")
        self.assertEqual((1, None), (review.read_profile().profile_version, review.read_profile().parent_profile_digest))
        self.assertEqual(1, len(self.commits_with(KP_SUBJECT)), "no second Kp")
        kp = self.commits_with(KP_SUBJECT)[0]
        if stage == project_policy.STAGE_KP:
            self.assertEqual([], self.commits_with(KM_SUBJECT))
            self.assertEqual([], self.policy_consumptions())
            published = []
        else:
            self.assertEqual(1, len(self.commits_with(KM_SUBJECT)), "no second Km")
            self.assertEqual(1, len(self.policy_consumptions()), "no duplicate Consumption")
            published = [kp] if self.template == "remote" else []
        if self.template == "remote":
            self.assertEqual(published[-1] if published else remote_before, self.remote_main(),
                             "the unowned commit is never published")
            self.assertEqual(published, [new for _, new, _ in self.pushes()])
            self.assert_fast_forward_pushes()


class PolicyStateWindows(InterruptionCase):
    # 10. change record effect
    def test_w10a_policy_state_recorded_not_applied(self) -> None:
        self.interrupted(lambda: after_recording(STATE), Interrupted)

    def test_w10b_change_record_created_flag_not_saved(self) -> None:
        self.interrupted(lambda: after_effect("create_file", STATE), Interrupted)

    # 11. Profile CAS effect
    def test_w11_profile_cas_applied_flag_not_saved(self) -> None:
        self.interrupted(lambda: after_effect("replace_review_profile", STATE), Interrupted)

    # 12. partial application of either policy-state effect
    def test_w12a_change_record_applied_profile_not(self) -> None:
        self.interrupted(lambda: before_effect("replace_review_profile", STATE), Interrupted)

    def test_w12b_change_record_bytes_recorded_not_placed(self) -> None:
        self.interrupted(lambda: before_effect("create_file", STATE), Interrupted)


class PolicyCommitWindows(UnownedCommitCase):
    # 13. Kp commit
    def test_w13a_kp_recorded_not_made(self) -> None:
        self.interrupted(lambda: after_recording(project_policy.STAGE_KP), Interrupted)

    def test_w13b_kp_made_without_its_saved_id_is_unowned_and_never_published(self) -> None:
        self.unowned(project_policy.STAGE_KP)

    # 14. C-2(Kp)
    def test_w14a_before_c2_kp(self) -> None:
        self.interrupted(lambda: crash_at(project_policy, "_c2_kp"), Crash)

    def test_w14b_c2_kp_proven_nothing_published(self) -> None:
        self.interrupted(lambda: crash_at(project_policy, "_c2_kp", after=True), Crash)
        self.assertEqual(2, len(self.pushes()), "Kp then Km, each once")

    # 15. Kp publication
    def test_w15a_kp_publication_recorded_not_pushed(self) -> None:
        self.interrupted(lambda: after_recording(project_policy.STAGE_KP_PUBLICATION), Interrupted)

    def test_w15b_kp_pushed_flag_not_saved(self) -> None:
        self.interrupted(lambda: after_effect("git_push", project_policy.STAGE_KP_PUBLICATION), Interrupted)

    def test_w15c_kp_push_refused_by_the_remote_hook(self) -> None:
        self.refuse_pushes(True)
        self.addCleanup(self.refuse_pushes, False)
        self.interrupted(lambda: _nothing(), Exception, between=lambda: self.refuse_pushes(False))


class ConsumptionWindows(UnownedCommitCase):
    # 16. Consumption
    def test_w16a_consumption_recorded_not_applied(self) -> None:
        self.interrupted(lambda: after_recording(project_policy.STAGE_CONSUMPTION), Interrupted)

    def test_w16b_consumption_created_flag_not_saved(self) -> None:
        self.interrupted(lambda: after_effect("create_file", project_policy.STAGE_CONSUMPTION,
                                              path=lambda found: found.startswith(CONSUMPTIONS)), Interrupted)

    # 17. P5 Run summary
    def test_w17_run_summary_created_consumption_not(self) -> None:
        self.interrupted(lambda: after_effect("create_file", project_policy.STAGE_CONSUMPTION,
                                              path=lambda found: found.startswith(RUN_SUMMARIES)), Interrupted)

    # 18. Km commit
    def test_w18a_km_recorded_not_made(self) -> None:
        self.interrupted(lambda: after_recording(project_policy.STAGE_KM), Interrupted)

    def test_w18b_km_made_without_its_saved_id_is_unowned_and_never_published(self) -> None:
        self.unowned(project_policy.STAGE_KM)

    # 19. C-2(Km)
    def test_w19a_before_c2_km(self) -> None:
        self.interrupted(lambda: crash_at(project_policy, "_c2_km"), Crash)

    def test_w19b_c2_km_proven_not_published(self) -> None:
        self.interrupted(lambda: crash_at(project_policy, "_c2_km", after=True), Crash)


class PublicationAndCompletionWindows(InterruptionCase):
    # 20. Km publication
    def test_w20a_km_publication_recorded_not_pushed(self) -> None:
        self.interrupted(lambda: after_recording(project_policy.STAGE_KM_PUBLICATION), Interrupted)

    def test_w20b_km_pushed_flag_not_saved(self) -> None:
        self.interrupted(lambda: after_effect("git_push", project_policy.STAGE_KM_PUBLICATION), Interrupted)

    def test_w20c_km_push_refused_by_the_remote_hook(self) -> None:
        real = project_policy._c2_km

        def c2_km_then_refuse(*args, **kwargs):
            found = real(*args, **kwargs)
            self.refuse_pushes(True)
            return found

        from unittest import mock

        self.addCleanup(self.refuse_pushes, False)
        self.interrupted(lambda: mock.patch.object(project_policy, "_c2_km", c2_km_then_refuse), Exception,
                         between=lambda: self.refuse_pushes(False))
        news = [new for _, new, _ in self.pushes()]
        self.assertEqual(2, len(news), "Kp once (before the refusal), Km once (after it)")

    # 21. completion
    def test_w21_everything_done_owner_not_completed(self) -> None:
        self.interrupted(before_owner_completion, Interrupted)
        self.assertEqual((0, 0), (self.discovery_calls, self.adjudicator_calls))


class PersistenceWindowsRemoteLess(UnownedCommitCase):
    template = "local"

    def test_w11_profile_cas_applied_flag_not_saved_remote_less(self) -> None:
        self.interrupted(lambda: after_effect("replace_review_profile", STATE), Interrupted)

    def test_w13b_kp_made_without_its_saved_id_remote_less(self) -> None:
        self.unowned(project_policy.STAGE_KP)

    def test_w18b_km_made_without_its_saved_id_remote_less(self) -> None:
        self.unowned(project_policy.STAGE_KM)

    def test_w21_owner_not_completed_remote_less(self) -> None:
        self.interrupted(before_owner_completion, Interrupted)


class _Nothing:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> bool:
        return False


def _nothing() -> _Nothing:
    return _Nothing()


if __name__ == "__main__":
    import unittest

    unittest.main()
