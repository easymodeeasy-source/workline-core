"""P6 §30.37: ``project-policy-change`` persistence, the Profile CAS, Kp / Km and Policy Consumption v3.

Every flow runs through ``project_policy.change_project_policy`` / ``record_policy_evaluation`` on a real evidence
Project (``project_policy_helpers``); effect-level tests open a mutation through the real Mutation Controller under
the Project execution lock. Covered (frozen bullets of §30.37, plus the §30.23 evaluation bullets):

* the owner is exactly ``project-policy-change`` (§15.20, §30.15);
* a before-Profile conflict fails closed, never overwrites (§30.18, §30.22);
* the change record is immutable (§30.17, §30.19);
* the dedicated Profile CAS applies to the exact Profile path only; generic Review writes stay immutable-only (§30.18);
* indirection is refused (§30.18);
* Kp exact delta, the semantic projection proof, no publication before proof (§30.20, §30.22);
* Policy Consumption v3, v1 / v2 compatibility (§30.21);
* Km exact metadata delta, exact Kp / Km publication to a LOCAL bare remote, remote-less operation (§30.20);
* rollback = a new higher Profile version (§15.22, §30.5);
* evaluations: retain / inconclusive never change the Profile, adjust / rollback need a new Candidate, an evaluation
  retry keeps its evaluation_id (§15.24, §30.23, §30.40).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, git, rmtree
from planning_helpers import plan
from project_policy_helpers import (
    EVALUATION_SUBJECT, GENERATION_SUBJECT, KM_SUBJECT, KP_SUBJECT, Crash, Discovery, Interrupted, PolicyCase,
    after_effect, after_recording, change_request, crash_at, evaluation_request, planning_review, policy_review,
    two_reviewers,
)
from workline import gitcmd, gitops, mutation as mutation_module, project_policy, store as store_module
from workline import roadmap as rm
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.implementation import package_directory
from workline.mutation import Effect, Mutation, MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import p4, paths, planning, policy, records, serialize
from workline.review.store import ReviewStore

PROFILE = paths.POLICY_PROFILE_REL
OTHER_RPC = "rpc_01ARZ3NDEKTSV4RRFFQ69G5FB0"


def make_junction(link: Path, target: Path) -> bool:
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
    return made.returncode == 0


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def foreign_profile(setting: int = 3) -> policy.ProjectProfile:
    """A well-formed Profile v1 no project-policy-change wrote (an override no stored change supports)."""
    surface = policy.SURFACE_BY_ID[policy.SURFACE_REQUIRED_SLOTS]
    return policy.ProjectProfile(
        profile_version=1, parent_profile_digest=None,
        global_baseline_digest=policy.load_global_baseline(WORKLINE_ROOT).digest, global_baseline_version=1,
        loader_semantics_identity=policy.LOADER_SEMANTICS_IDENTITY,
        overrides=({"policy_surface_id": surface.policy_surface_id, "strength_class": surface.strength_class,
                    "setting": setting, "direction": "strengthen", "supporting_policy_change_id": OTHER_RPC},),
        active_experiment_refs=(),
    )


class EffectCase(PolicyCase):
    """Effect-level tests: a mutation opened under the Project execution lock through the real controller."""

    def setUp(self) -> None:
        super().setUp()
        self.lock = project_operation(self.store, "rb6c-effect-test")
        self.lock.__enter__()
        self.addCleanup(self.lock.__exit__, None, None, None)
        self.opened = 0

    def open(self, owner: str = project_policy.OWNER) -> Mutation:
        self.opened += 1
        return MutationController(self.store).open(owner, {"operation": "rb6c-effect-test", "n": self.opened},
                                                   WriteScope(files=(PROFILE, f"{paths.POLICY_DIR}/x-{self.opened}")))

    def refused(self, effect: Effect, owner: str = project_policy.OWNER, code: str | None = None) -> None:
        found = self.open(owner)
        with self.assertRaises(ValidationError) as raised:
            found.add_effects("rb6c", [effect])
        if code is not None:
            self.assertEqual(code, raised.exception.code)
        self.assertEqual([], found.effects, "nothing is recorded")
        found.abandon()


# =========================================================================== owner

class OwnerTests(PolicyCase):
    def test_the_owner_is_exactly_project_policy_change(self) -> None:
        self.assertEqual("project-policy-change", project_policy.OWNER)
        self.assertEqual(("project-policy-change",), store_module.POLICY_CHANGE_OWNERS)
        opened: list[tuple[str, dict[str, Any]]] = []
        real = MutationController.open

        def spy(controller, owner, invocation, scope):
            opened.append((owner, dict(invocation)))
            return real(controller, owner, invocation, scope)

        head = self.commit_of()
        with mock.patch.object(MutationController, "open", spy):
            result = self.applied()
        self.assertEqual({project_policy.OWNER}, {owner for owner, _ in opened})
        (owner_invocation,) = {serialize.digest(inv): inv for _, inv in opened
                               if inv.get("operation") == project_policy.OPERATION}.values()
        self.assertEqual({"operation", "request_digest", "review_contract", "publication_contract"}, set(owner_invocation))
        self.assertEqual(policy.POLICY_CHANGE_CONTRACT, owner_invocation["review_contract"])
        self.assertEqual(policy.POLICY_PUBLICATION_CONTRACT, owner_invocation["publication_contract"])
        generations = [inv for _, inv in opened if inv.get("operation") == "review-generation"]
        self.assertEqual(5, len({inv["generation"] for inv in generations}))
        self.assertEqual({result.mutation_id}, {inv["policy_mutation_id"] for inv in generations})
        # physical Profile mutation and policy evidence only, never Project lifecycle
        for commit in self.git("rev-list", f"{head}..HEAD").split():
            for path in self.delta(commit):
                self.assertTrue(path.startswith(paths.REVIEW_DIR + "/"), f"{commit} writes {path}")
        # no Project-facing domain Skill
        skills = {entry.name for entry in (WORKLINE_ROOT / ".claude" / "skills").iterdir()}
        self.assertNotIn("project-policy-change", skills)
        self.assertNotIn("project-policy", skills)


class OwnerGuardTests(EffectCase):
    def test_no_other_owner_writes_the_policy_namespace(self) -> None:
        text = foreign_profile().text()
        for owner in ("roadmap-create", "start", "review-generation", "work-terminal-activation"):
            with self.subTest(owner):
                self.refused(Effect.replace_review_profile(PROFILE, text, None), owner, "review_policy_owner")
                self.refused(Effect.create_file(paths.policy_change_rel(OTHER_RPC), "x: 1\n"), owner,
                             "review_policy_owner")
                self.refused(Effect.create_file(paths.policy_evaluation_rel("rpe_01ARZ3NDEKTSV4RRFFQ69G5FAV"),
                                                "x: 1\n"), owner, "review_policy_owner")
        self.assertIsNone(self.profile_bytes())


# =========================================================================== the Profile CAS

class ProfileCasTests(EffectCase):
    def test_the_dedicated_profile_cas_applies_to_the_exact_profile_path_only(self) -> None:
        text = foreign_profile().text()
        for bad in (
            paths.policy_change_rel(OTHER_RPC), f"{paths.POLICY_DIR}/Project-Profile.yaml",
            f"{paths.POLICY_DIR}/project-profile.yml", f"{paths.POLICY_DIR}/project-profile.yaml.tmp",
            f"{paths.POLICY_DIR}/../policy/project-profile.yaml", ".workline\\review\\policy\\project-profile.yaml",
            f"./{PROFILE}", f"/{PROFILE}", "project-profile.yaml", ".workline/project.yaml",
            paths.receipt_rel("rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV"), f"{paths.REVIEW_DIR}/project-profile.yaml",
        ):
            with self.subTest(bad):
                self.refused(Effect.replace_review_profile(bad, text, None))
        for name, effect in (
            ("an extra payload key", Effect("replace_review_profile", {"path": PROFILE, "content": text,
                                                                        "expected_digest": None, "force": True})),
            ("a malformed expectation", Effect.replace_review_profile(PROFILE, text, "ABC")),
            ("no content", Effect.replace_review_profile(PROFILE, "", None)),
            ("a no-op replace", Effect.replace_review_profile(PROFILE, text, sha(text.encode("utf-8")))),
        ):
            with self.subTest(name):
                self.refused(effect)
        twice = self.open()
        with self.assertRaises(ValidationError):
            twice.add_effects("rb6c", [Effect.replace_review_profile(PROFILE, text, None),
                                       Effect.replace_review_profile(PROFILE, foreign_profile(4).text(), None)])
        self.assertEqual([], twice.effects)
        twice.abandon()
        self.assertIsNone(self.profile_bytes())

    def test_the_cas_classifies_unapplied_matching_and_mismatch_and_never_overwrites(self) -> None:
        first, second, third = (foreign_profile(n).text() for n in (2, 3, 4))
        # target == expected prior (absence) -> unapplied -> written
        created = self.open()
        created.add_effects("rb6c", [Effect.replace_review_profile(PROFILE, first, None)])
        self.assertEqual([(1, mutation_module.UNAPPLIED)], created.apply())
        self.assertEqual(first.encode("utf-8"), self.profile_bytes())
        created.complete()
        # target == expected prior bytes -> unapplied -> replaced
        replaced = self.open()
        replaced.add_effects("rb6c", [Effect.replace_review_profile(PROFILE, second, sha(first.encode("utf-8")))])
        self.assertEqual([(1, mutation_module.UNAPPLIED)], replaced.apply())
        self.assertEqual(second.encode("utf-8"), self.profile_bytes())
        self.assertEqual([(1, mutation_module.MATCHING)], replaced.apply(), "a replay writes nothing")
        replaced.complete()
        # target == exact new -> matching replay, nothing written
        replay = self.open()
        replay.add_effects("rb6c", [Effect.replace_review_profile(PROFILE, second, sha(first.encode("utf-8")))])
        self.assertEqual([(1, mutation_module.MATCHING)], replay.apply())
        replay.complete()
        # anything else -> mismatch: reconcile, never overwritten
        stale = self.open()
        stale.add_effects("rb6c", [Effect.replace_review_profile(PROFILE, third, sha(first.encode("utf-8")))])
        with self.assertRaises(ReconcileRequired):
            stale.apply()
        self.assertEqual(second.encode("utf-8"), self.profile_bytes(), "no overwrite on a before-state mismatch")

    def test_an_expected_absence_never_replaces_a_present_profile(self) -> None:
        target = self.root / PROFILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(foreign_profile(2).text().encode("utf-8"))
        found = self.open()
        found.add_effects("rb6c", [Effect.replace_review_profile(PROFILE, foreign_profile(3).text(), None)])
        with self.assertRaises(ReconcileRequired):
            found.apply()
        self.assertEqual(foreign_profile(2).text().encode("utf-8"), self.profile_bytes())


    def test_an_unsupported_containment_capability_refuses_before_any_write(self) -> None:
        from workline.review import fsafe

        text = foreign_profile().text()
        with mock.patch.object(fsafe._Backend, "PINS_HELD_DIRECTORIES", False):
            found = self.open()
            with self.assertRaises((ValidationError, StopError)):
                found.add_effects("rb6c", [Effect.replace_review_profile(PROFILE, text, None)])
            self.assertEqual([], found.effects, "a replace that cannot be contained is never recorded")
            found.abandon()
        recorded = self.open()
        recorded.add_effects("rb6c", [Effect.replace_review_profile(PROFILE, text, None)])
        with mock.patch.object(fsafe._Backend, "PINS_HELD_DIRECTORIES", False):
            with self.assertRaises((ValidationError, StopError)):
                recorded.apply()
        self.assertIsNone(self.profile_bytes(), "refused before the write")


class GenericReviewWriteTests(EffectCase):
    def test_generic_review_writes_stay_immutable_only(self) -> None:
        text = foreign_profile().text()
        # the generic update primitive never reaches a Review path - the Profile included
        self.refused(Effect.write_file(PROFILE, text))
        self.refused(Effect.write_file(PROFILE, text, base=""))
        self.refused(Effect.write_file(paths.policy_change_rel(OTHER_RPC), "x: 1\n"))
        # the immutable create never creates or replaces the Profile
        found = self.open()
        try:
            found.add_effects("rb6c", [Effect.create_file(PROFILE, text)])
        except ValidationError:
            pass
        else:
            with self.assertRaises((ValidationError, ReconcileRequired, StopError)):
                found.apply()
        self.assertIsNone(self.profile_bytes(), "the immutable create never writes the mutable Profile")

    def test_an_existing_policy_record_is_never_rewritten(self) -> None:
        record = paths.policy_change_rel(OTHER_RPC)
        first = self.open()
        first.add_effects("rb6c", [Effect.create_file(record, "original: 1\n")])
        first.apply()
        first.complete()
        second = self.open()
        second.add_effects("rb6c", [Effect.create_file(record, "rewritten: 2\n")])
        with self.assertRaises(ReconcileRequired):
            second.apply()
        self.assertEqual(b"original: 1\n", (self.root / record).read_bytes())


@unittest.skipUnless(os.name == "nt", "junctions are a Windows mechanism")
class IndirectionTests(EffectCase):
    def outside(self) -> Path:
        found = self.tmp / "outside"
        found.mkdir(exist_ok=True)
        return found

    def junction(self, link: Path, target: Path) -> None:
        if not make_junction(link, target):
            self.skipTest("cannot create a junction here")
        self.addCleanup(lambda: os.rmdir(link) if os.path.lexists(link) else None)

    def assert_outside_untouched(self, outside: Path) -> None:
        self.assertEqual([], sorted(p.name for p in outside.iterdir()), "nothing was written through the indirection")

    def test_a_junction_at_the_policy_directory_is_never_followed(self) -> None:
        outside = self.outside()
        self.junction(self.root / paths.POLICY_DIR, outside)
        with self.assertRaises(ValidationError):
            ReviewStore(self.store).read_profile()
        found = self.open()
        found.add_effects("rb6c", [Effect.replace_review_profile(PROFILE, foreign_profile().text(), None)])
        with self.assertRaises((ReconcileRequired, ValidationError)):
            found.apply()
        self.assert_outside_untouched(outside)
        self.assertIn("review_containment", [line.split(":")[0] for line in self.problems()])

    def test_a_junction_at_the_review_directory_is_never_followed(self) -> None:
        outside = self.outside()
        review_dir = self.root / paths.REVIEW_DIR
        moved = self.tmp / "review-moved"
        review_dir.rename(moved)
        self.addCleanup(lambda: moved.rename(review_dir) if moved.exists() and not os.path.lexists(review_dir) else None)
        self.junction(review_dir, outside)
        found = self.open()
        found.add_effects("rb6c", [Effect.replace_review_profile(PROFILE, foreign_profile().text(), None)])
        with self.assertRaises((ReconcileRequired, ValidationError)):
            found.apply()
        self.assert_outside_untouched(outside)

    def test_a_symlinked_profile_is_never_followed(self) -> None:
        outside = self.outside()
        victim = outside / "victim.yaml"
        victim.write_bytes(foreign_profile(2).text().encode("utf-8"))
        target = self.root / PROFILE
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.symlink_to(victim)
        except OSError as exc:  # WinError 1314: no symlink privilege
            self.skipTest(f"cannot create a file symlink here ({exc})")
        with self.assertRaises(ValidationError):
            ReviewStore(self.store).read_profile()
        found = self.open()
        found.add_effects("rb6c", [Effect.replace_review_profile(PROFILE, foreign_profile(3).text(),
                                                                 sha(victim.read_bytes()))])
        with self.assertRaises((ReconcileRequired, ValidationError)):
            found.apply()
        self.assertEqual(foreign_profile(2).text().encode("utf-8"), victim.read_bytes())



@unittest.skipUnless(os.name == "nt", "junctions are a Windows mechanism")
class OwnerIndirectionTests(PolicyCase):
    def test_the_owner_refuses_a_policy_directory_junction_before_any_write(self) -> None:
        outside = self.tmp / "outside"
        outside.mkdir()
        link = self.root / paths.POLICY_DIR
        if not make_junction(link, outside):
            self.skipTest("cannot create a junction here")
        self.addCleanup(lambda: os.rmdir(link) if os.path.lexists(link) else None)
        head = self.commit_of()
        with self.assertRaises((ValidationError, StopError, ReconcileRequired)):
            self.change()
        self.assertEqual([], sorted(p.name for p in outside.iterdir()), "nothing was written through the junction")
        self.assertEqual(head, self.commit_of())
        self.assertEqual([], self.policy_runs())


# =========================================================================== persistence: Kp / Km / Consumption

class PersistenceTests(PolicyCase):
    """Remote-less (template ``local``): the same local proof and commit boundaries, without a push (§30.20)."""

    def test_kp_and_km_are_exact_and_remote_less_operation_pushes_nothing(self) -> None:
        stages: list[tuple[str, str, list[str]]] = []
        real = Mutation.add_effects

        def spy(mutation, stage, effects):
            stages.append((mutation.owner, stage, [effect.kind for effect in effects]))
            return real(mutation, stage, effects)

        before = self.state()
        with mock.patch.object(Mutation, "add_effects", spy):
            result = self.applied()
        review = self.review_store
        snapshot = review.read_candidate_snapshot(review.gate_chain(result.review_run_id).generations[0].candidate_hash)
        candidate = snapshot.material
        after = policy.ProjectProfile.from_record(dict(candidate["after_profile"]), "after")
        kp, km = str(result.policy_commit), str(result.metadata_commit)
        change_path = paths.policy_change_rel(result.policy_change_id)
        # Kp: on the sealed G5, exactly the change record and the reviewed Profile bytes
        (g5,) = [c for c in self.commits_with(GENERATION_SUBJECT)
                 if self.subject(c) == f"{GENERATION_SUBJECT}5 of {result.review_run_id}"]
        self.assertEqual([g5], self.parents(kp))
        self.assertEqual(f"{KP_SUBJECT}{result.policy_change_id}", self.subject(kp))
        change_bytes = serialize.canonical_bytes(policy.change_record(candidate, review_run_id=result.review_run_id,
                                                                      receipt_id=str(result.receipt_id),
                                                                      baseline_record=before.baseline.record))
        global_settings = policy.bound_global_settings(before.baseline.record)
        delta = self.delta(kp)
        self.assertEqual({change_path, PROFILE}, set(delta))
        self.assertEqual(("A", "100644", change_bytes), (delta[change_path].status, delta[change_path].mode,
                                                         delta[change_path].data))
        self.assertEqual(("A", "100644", after.text().encode("utf-8")),
                         (delta[PROFILE].status, delta[PROFILE].mode, delta[PROFILE].data))
        self.assertIsNone(policy.persisted_projection_problem(candidate["after_profile"], delta[PROFILE].data,
                                                              global_settings))
        self.assertEqual(1, after.profile_version)
        self.assertIsNone(after.parent_profile_digest)
        self.assertEqual(before.baseline.digest, after.global_baseline_digest)
        self.assertEqual((result.profile_version, result.profile_digest), (after.profile_version, after.digest))
        # Km: on Kp, exactly the consumed Run summary and the Policy Consumption
        summary_path = paths.history_run_rel(result.review_run_id)
        consumption_path = paths.consumption_rel(str(result.consumption_id))
        self.assertEqual([kp], self.parents(km))
        self.assertEqual(f"{KM_SUBJECT}{result.consumption_id}", self.subject(km))
        delta = self.delta(km)
        self.assertEqual({summary_path, consumption_path}, set(delta))
        for path in (summary_path, consumption_path):
            self.assertEqual(("A", "100644"), (delta[path].status, delta[path].mode))
            self.assertEqual((self.root / path).read_bytes(), delta[path].data)
        for path in (change_path, PROFILE):
            self.assertEqual(self.blob(kp, path), self.blob(km, path))
        self.assertEqual(km, self.commit_of())
        self.assertEqual([], self.dirty())
        # remote-less: the same stages, no publication stage and no push
        policy_stages = [stage for owner, stage, _ in stages if owner == project_policy.OWNER]
        for stage in ("policy-state", "policy-commit", "policy-consumption", "policy-consumption-commit"):
            self.assertIn(stage, policy_stages)
        self.assertNotIn("policy-publication", policy_stages)
        self.assertNotIn("policy-consumption-publication", policy_stages)
        self.assertEqual([], [kinds for _, _, kinds in stages if "git_push" in kinds])
        self.assertEqual([], self.policy_pending())
        self.assertEqual([], self.problems())

    def test_policy_consumption_v3_binds_the_exact_persisted_policy(self) -> None:
        before = self.state()
        result = self.applied()
        review = self.review_store
        consumption = review.read_consumption(str(result.consumption_id))
        self.assertIsInstance(consumption, records.PolicyConsumption)
        record = consumption.to_record()
        self.assertEqual(3, record[serialize.VERSION_KEY])
        self.assertEqual(policy.REVIEW_KIND, consumption.review_kind)
        self.assertEqual(policy.TARGET_IDENTITY, consumption.target_identity)
        self.assertEqual((result.receipt_id, result.review_run_id, 5),
                         (consumption.receipt_id, consumption.review_run_id, consumption.review_generation))
        chain = review.gate_chain(result.review_run_id)
        self.assertEqual(chain.generations[0].candidate_hash, consumption.authorized_candidate_hash)
        self.assertEqual(result.mutation_id, consumption.operation_mutation_id)
        self.assertIsNone(consumption.terminal_event_id, "no Work terminal event is invented")
        self.assertIsNone(consumption.work_id)
        persisted = consumption.persisted_policy
        self.assertEqual(set(records.PERSISTED_POLICY_FIELDS), set(persisted))
        after = review.read_profile()
        kp = str(result.policy_commit)
        self.assertEqual({
            "contract": records.PERSISTED_POLICY_CONTRACT, "policy_change_id": result.policy_change_id,
            "before_profile_version": None, "before_profile_digest": None,
            "after_profile_version": 1, "after_profile_digest": after.digest,
            "global_baseline_digest": before.baseline.digest,
            "normalized_projection_hash": policy.projection_hash(after, policy.bound_global_settings(before.baseline.record)),
            "policy_commit": kp, "policy_parent": self.parents(kp)[0], "branch": "refs/heads/main",
            "adapter_identity": records.POLICY_ADAPTER_IDENTITY,
            "loader_identity": planning.loader_identity(package_directory(self.store.workline_root())),
        }, {key: value for key, value in persisted.items() if key != "policy_delta_digest"})
        self.assertRegex(persisted["policy_delta_digest"], r"\A[0-9a-f]{64}\Z")
        # one Receipt, at most one Consumption
        self.assertEqual([result.consumption_id], [c.consumption_id for c in self.policy_consumptions()])
        self.assertEqual([result.receipt_id], [c.receipt_id for c in self.policy_consumptions()])
        self.assertEqual(record, records.consumption_from_record(serialize.canonical_data(record), "c").to_record())

    def test_v1_and_v2_consumptions_keep_their_exact_meaning(self) -> None:
        from test_review_authorization import consumption_record

        result = self.applied()
        review = self.review_store
        planning_consumptions = [c for c in review.consumptions() if isinstance(c, records.PlanningConsumption)]
        self.assertEqual(2, len(planning_consumptions), "the evidence Runs' version 2 Consumptions read as before")
        v1 = consumption_record()
        found = records.consumption_from_record(serialize.canonical_data(v1), "v1")
        self.assertIs(type(found), records.Consumption)
        self.assertEqual(serialize.canonical_data(v1), serialize.canonical_data(found.to_record()))
        v2 = planning_consumptions[0].to_record()
        self.assertEqual(2, v2[serialize.VERSION_KEY])
        v3 = review.read_consumption(str(result.consumption_id)).to_record()
        for name, record in (
            ("a version 3 record of a planning kind", {**v3, "review_kind": "roadmap-plan-v1"}),
            ("a version 3 record of a Work kind", {**v3, "review_kind": "work_formal"}),
            ("a version 2 record of the policy kind", {**v2, "review_kind": policy.REVIEW_KIND}),
            ("a version 3 Policy Consumption read as version 2", {**v3, serialize.VERSION_KEY: 2}),
            ("a version 3 Policy Consumption read as version 1", {**v3, serialize.VERSION_KEY: 1}),
            ("an unknown version", {**v3, serialize.VERSION_KEY: 4}),
            ("a skipped Profile version", {**v3, "persisted_policy": {**v3["persisted_policy"],
                                                                      "after_profile_version": 2}}),
        ):
            with self.subTest(name), self.assertRaises(ValidationError):
                records.consumption_from_record(serialize.canonical_data(record), name)
        # a Policy Receipt consumed by anything but a version 3 Policy Consumption is a validation Problem
        receipt = review.read_receipt(str(result.receipt_id))
        rogue_id = "rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV"
        rogue = consumption_record(consumption_id=rogue_id, receipt_id=receipt.receipt_id,
                                   review_run_id=receipt.review_run_id, review_generation=5,
                                   authorized_candidate_hash=receipt.authorized_candidate_hash)
        (self.root / paths.consumption_rel(rogue_id)).write_bytes(serialize.canonical_bytes(rogue))
        codes = [line.split(":")[0] for line in self.problems()]
        self.assertIn("review_record_conflict", codes)


class SemanticProjectionTests(PolicyCase):
    template = "remote"

    def test_the_projection_adapter_accepts_exactly_the_reviewed_bytes(self) -> None:
        after = foreign_profile(2)
        exact = after.text().encode("utf-8")
        settings = policy.bound_global_settings(policy.load_global_baseline(WORKLINE_ROOT).record)
        self.assertIsNone(policy.persisted_projection_problem(after.to_record(), exact, settings))
        for name, raw in (
            ("CRLF", exact.replace(b"\n", b"\r\n")),
            ("a trailing blank line", exact + b"\n"),
            ("a BOM", b"\xef\xbb\xbf" + exact),
            ("another setting", foreign_profile(3).text().encode("utf-8")),
            ("absent", None),
        ):
            with self.subTest(name):
                self.assertIsNotNone(policy.persisted_projection_problem(after.to_record(), raw, settings))

    def assert_not_published(self, remote_before: str | None) -> None:
        self.assertEqual(remote_before, self.remote_main(), "nothing was published")
        self.assertEqual([], self.pushes())
        self.assertEqual([], self.policy_consumptions())
        self.assertEqual([], self.commits_with(KM_SUBJECT))

    def test_a_kp_whose_profile_bytes_differ_is_refused_and_never_published(self) -> None:
        real = gitcmd.contained_add

        def add(repo, paths_, hooks):
            if PROFILE in paths_:
                target = Path(repo) / PROFILE
                target.write_bytes(target.read_bytes() + b"\n")
            real(repo, paths_, hooks)

        remote_before = self.remote_main()
        with mock.patch.object(gitcmd, "contained_add", add), self.assertRaises(ReconcileRequired) as raised:
            self.change()
        self.assertEqual(policy.REASON_PERSISTED_MISMATCH, raised.exception.reason)
        self.assert_not_published(remote_before)

    def test_a_kp_with_an_extra_path_is_refused_and_never_published(self) -> None:
        real = gitcmd.contained_commit

        def commit(repo, message, paths_, hooks):
            real(repo, message, paths_, hooks)
            if PROFILE in paths_:
                (Path(repo) / "extra.txt").write_text("extra\n", encoding="utf-8")
                git(repo, "add", "extra.txt")
                git(repo, "-c", f"core.hooksPath={hooks}", "commit", "-q", "--amend", "--no-edit", "--no-verify")

        remote_before = self.remote_main()
        with mock.patch.object(gitcmd, "contained_commit", commit), self.assertRaises(ReconcileRequired):
            self.change()
        self.assert_not_published(remote_before)


class PublicationTests(PolicyCase):
    template = "remote"

    def test_exact_kp_then_exact_km_are_published_fast_forward_only(self) -> None:
        events: list[tuple[str, str]] = []
        real_kp, real_km, real_apply = project_policy._c2_kp, project_policy._c2_km, MutationController.apply_effect

        def c2_kp(*args, **kwargs):
            found = real_kp(*args, **kwargs)
            events.append(("proof", found[0]))
            return found

        def c2_km(*args, **kwargs):
            found = real_km(*args, **kwargs)
            events.append(("proof", found))
            return found

        def apply_effect(controller, record):
            if record["kind"] == "git_push":
                events.append(("push", record["payload"]["commit"]))
                self.assertNotIn("force", record["payload"])
            return real_apply(controller, record)

        remote_before = self.remote_main()
        with mock.patch.object(project_policy, "_c2_kp", c2_kp), mock.patch.object(project_policy, "_c2_km", c2_km), \
                mock.patch.object(MutationController, "apply_effect", apply_effect):
            result = self.applied()
        kp, km = str(result.policy_commit), str(result.metadata_commit)
        first_push = events.index(("push", kp))
        self.assertIn(("proof", kp), events[:first_push], "no push of Kp before its C-2 proof")
        self.assertIn(("proof", km), events[:events.index(("push", km))], "no push of Km before its C-2 proof")
        self.assertEqual(1, events.count(("push", kp)))
        self.assertEqual(1, events.count(("push", km)))
        self.assertEqual(km, self.remote_main())
        self.assertEqual([(remote_before, kp, "refs/heads/main"), (kp, km, "refs/heads/main")], self.pushes(),
                         "exactly Kp, then exactly Km")
        self.assert_fast_forward_pushes()
        self.assertEqual([], self.problems())


class NoForceTests(PolicyCase):
    template = "remote"

    def test_a_remote_that_moved_on_is_never_forced(self) -> None:
        other = self.tmp / "other-clone"
        git(self.tmp, "clone", "-q", str(self.remote), str(other))
        git(other, "config", "user.email", "t@example.invalid")
        git(other, "config", "user.name", "t")
        (other / "notes.txt").write_text("a person's note" + chr(10), encoding="utf-8")
        git(other, "add", "notes.txt")
        git(other, "commit", "-q", "-m", "docs: a person's note")
        git(other, "push", "-q", "origin", "main")
        foreign = git(other, "rev-parse", "HEAD").strip()
        self.assertEqual(foreign, self.remote_main())
        before = list(self.pushes())
        with self.assertRaises((ReconcileRequired, StopError)):
            self.change()
        self.assertEqual(foreign, self.remote_main(), "the remote's own history is never overwritten")
        self.assertEqual(before, self.pushes(), "nothing is pushed over it")
        self.assert_fast_forward_pushes()


class PublicationValidatorTests(unittest.TestCase):
    """The policy push validator (``mutation._policy_publication``): exactly Kp / Km, each only after its proof."""

    INVOCATION = {"operation": "project-policy-change", "request_digest": "a" * 64,
                  "review_contract": policy.POLICY_CHANGE_CONTRACT,
                  "publication_contract": policy.POLICY_PUBLICATION_CONTRACT}

    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp(prefix="wl-p6c-push-"))
        self.addCleanup(rmtree, self.repo)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@example.invalid")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "config", "core.autocrlf", "false")
        self.base = self.commit({"base.txt": "base\n"})
        self.change_path = paths.policy_change_rel(OTHER_RPC)
        self.kp = self.commit({self.change_path: "change\n", PROFILE: "profile\n"})
        self.meta = [paths.history_run_rel("rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"),
                     paths.consumption_rel("rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV")]
        self.km = self.commit({self.meta[0]: "summary\n", self.meta[1]: "consumption\n"})

    def commit(self, files: dict[str, str]) -> str:
        for relative, text in files.items():
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "c")
        return git(self.repo, "rev-parse", "HEAD").strip()

    def effects(self, *, kp: str | None = None, km: str | None = None) -> list[dict[str, Any]]:
        kp, km = kp or self.kp, km or self.km
        return [
            {"seq": 1, "stage": "policy-commit", "kind": "git_commit", "applied": True, "commit_id": self.kp,
             "payload": {"branch": "refs/heads/main", "paths": sorted([self.change_path, PROFILE])}},
            {"seq": 2, "stage": "policy-publication", "kind": "git_push", "applied": False,
             "payload": {"commit": kp, "branch": "main"}},
            {"seq": 3, "stage": "policy-consumption-commit", "kind": "git_commit", "applied": True,
             "commit_id": self.km, "payload": {"branch": "refs/heads/main", "paths": sorted(self.meta)}},
            {"seq": 4, "stage": "policy-consumption-publication", "kind": "git_push", "applied": False,
             "payload": {"commit": km, "branch": "main"}},
        ]

    def verdict(self, effects: list[dict[str, Any]], position: int, proof: dict[str, Any] | None,
                invocation: dict[str, Any] | None = None):
        record = {"invocation": invocation or self.INVOCATION, "effects": effects,
                  "notes": {} if proof is None else {"policy_publication_proof": proof}}
        return mutation_module._recorded_publication(self.repo, effects, position, record)

    def test_the_policy_invocation_selects_the_policy_publication_contract(self) -> None:
        self.assertEqual("policy", mutation_module._publication_contract(self.INVOCATION))
        self.assertNotEqual("policy", mutation_module._publication_contract({**self.INVOCATION, "extra": 1}))

    def test_exactly_the_proven_kp_and_km_are_published(self) -> None:
        proof = {"contract": "p", "policy_commit": self.kp, "metadata_commit": self.km}
        found = self.verdict(self.effects(), 1, proof)
        self.assertIsInstance(found, mutation_module._Publication, getattr(found, "message", found))
        self.assertEqual((self.kp, "refs/heads/main"), (found.commit, found.ref))
        found = self.verdict(self.effects(), 3, proof)
        self.assertIsInstance(found, mutation_module._Publication, getattr(found, "message", found))
        self.assertEqual(self.km, found.commit)

    def test_nothing_is_published_before_or_beside_its_proof(self) -> None:
        proven = {"contract": "p", "policy_commit": self.kp, "metadata_commit": self.km}
        for name, effects, position, proof in (
            ("no proof note at all", self.effects(), 1, None),
            ("a proof note not naming Kp", self.effects(), 1, {**proven, "policy_commit": self.base}),
            ("Km before its proof (metadata_commit not yet proven)", self.effects(), 3,
             {**proven, "metadata_commit": None}),
            ("a push of another commit than its stage made", self.effects(kp=self.km),
             1, {**proven, "policy_commit": self.km}),
            ("a push of the branch base", self.effects(kp=self.base), 1, {**proven, "policy_commit": self.base}),
        ):
            with self.subTest(name):
                self.assertIsInstance(self.verdict(effects, position, proof), mutation_module._Refused)
        combined = self.effects()
        combined[1] = {**combined[1], "stage": "policy-commit"}
        self.assertIsInstance(self.verdict(combined, 1, proven), mutation_module._Refused,
                              "a push sharing its commit's stage is refused")


# =========================================================================== before-Profile conflict

class BeforeConflictTests(PolicyCase):
    def commit_foreign_profile(self, data: bytes) -> None:
        target = self.root / PROFILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.git("add", "--", PROFILE)
        self.git("commit", "-q", "-m", "docs: a person edits the Project Profile")

    def test_a_before_state_that_moved_after_the_freeze_stops_with_nothing_written(self) -> None:
        request = self.request()
        with crash_at(project_policy, "_accept"), self.assertRaises(Crash):
            self.change(request)
        foreign = foreign_profile(3).text().encode("utf-8")
        self.commit_foreign_profile(foreign)
        head = self.commit_of()
        with self.assertRaises(StopError) as raised:
            self.change(request)
        self.assertEqual(policy.CODE_BEFORE_STATE_CONFLICT, raised.exception.code)
        self.assertEqual(foreign, self.profile_bytes())
        self.assertEqual(head, self.commit_of())
        self.assertEqual((), self.review_store.policy_change_ids())
        self.assertEqual([], self.policy_receipts())

    def test_the_profile_cas_never_overwrites_a_moved_profile(self) -> None:
        request = self.request()
        with after_recording(project_policy.STAGE_POLICY), self.assertRaises(Interrupted):
            self.change(request)
        foreign = foreign_profile(3).text().encode("utf-8")
        self.commit_foreign_profile(foreign)
        with self.assertRaises(ReconcileRequired):
            self.change(request)
        self.assertEqual(foreign, self.profile_bytes(), "no overwrite on a before-state mismatch")
        self.assertEqual([], self.commits_with(KP_SUBJECT))
        self.assertEqual([], self.policy_consumptions())


class BeforeConflictProfiledTests(PolicyCase):
    template = "profiled"

    def test_a_replace_never_overwrites_a_profile_that_is_not_its_exact_prior(self) -> None:
        (first,) = self.review_store.policy_change_ids()
        request = self.request(after=3, supersedes=(first,), overlap=policy.OVERLAP_KNOWN)
        with after_recording(project_policy.STAGE_POLICY), self.assertRaises(Interrupted):
            self.change(request, two_reviewers())
        target = self.root / PROFILE
        foreign = target.read_bytes().replace(b"setting: 2", b"setting: 4")
        self.assertNotEqual(foreign, target.read_bytes())
        target.write_bytes(foreign)
        with self.assertRaises(ReconcileRequired):
            self.change(request, two_reviewers())
        self.assertEqual(foreign, self.profile_bytes(), "no overwrite on a before-state mismatch")
        self.assertEqual(1, len(self.commits_with(KP_SUBJECT)), "only the template's own Kp")


# =========================================================================== the change record, rollback

class ChangeRecordAndRollbackTests(PolicyCase):
    template = "profiled"

    def test_rollback_is_a_new_higher_profile_version_and_never_rewrites_history(self) -> None:
        review = self.review_store
        (first,) = review.policy_change_ids()
        first_change = review.read_policy_change(first)
        v1_bytes = self.profile_bytes()
        v1 = review.read_profile()
        (first_kp,) = self.commits_with(KP_SUBJECT)
        first_record_bytes = (self.root / paths.policy_change_rel(first)).read_bytes()
        history_before = self.git("rev-list", "HEAD").split()
        rollback = self.request(direction=policy.DIRECTION_ROLLBACK, after=1, rolls_back=first,
                                expected_effect="the single discovery reviewer is restored")
        with self.assertRaises(StopError) as raised:
            self.change(rollback, policy_review())
        self.assertEqual(policy.CODE_DISCOVERY_SLOTS_UNMET, raised.exception.code,
                         "a rollback is reviewed under the pre-change policy too")
        result = self.applied(rollback, two_reviewers())
        v2 = self.review_store.read_profile()
        self.assertEqual(2, v2.profile_version, "a rollback is a NEW higher Profile version")
        self.assertEqual(v1.digest, v2.parent_profile_digest)
        self.assertIsNone(v2.setting_of(policy.SURFACE_REQUIRED_SLOTS))
        self.assertEqual(1, policy.setting(self.state().effective, policy.SURFACE_REQUIRED_SLOTS))
        self.assertEqual((result.policy_change_id,), v2.active_experiment_refs)
        change = self.review_store.read_policy_change(result.policy_change_id)
        self.assertEqual((policy.DIRECTION_ROLLBACK, 2, 1, 1, v1.digest, 2),
                         (change["direction"], change["before_setting"], change["after_setting"],
                          change["before_profile_version"], change["before_profile_digest"],
                          change["after_profile_version"]))
        persisted = self.review_store.read_consumption(str(result.consumption_id)).persisted_policy
        self.assertEqual((1, v1.digest, 2, v2.digest),
                         (persisted["before_profile_version"], persisted["before_profile_digest"],
                          persisted["after_profile_version"], persisted["after_profile_digest"]))
        # no reset / revert / history rewrite: every earlier commit is still in the branch history
        self.assertEqual(history_before, self.git("rev-list", "HEAD").split()[-len(history_before):])
        self.assertEqual(v1_bytes, self.blob(first_kp, PROFILE))
        kp = str(result.policy_commit)
        delta = self.delta(kp)
        self.assertEqual("M", delta[PROFILE].status)
        self.assertEqual("A", delta[paths.policy_change_rel(result.policy_change_id)].status)
        # the first change record is immutable: same bytes, never in the rollback's delta
        self.assertNotIn(paths.policy_change_rel(first), delta)
        self.assertEqual(first_record_bytes, (self.root / paths.policy_change_rel(first)).read_bytes())
        self.assertEqual(first_change, self.review_store.read_policy_change(first))
        self.assertEqual([], self.problems())

    def test_the_change_record_is_immutable_evidence(self) -> None:
        review = self.review_store
        (first,) = review.policy_change_ids()
        relative = paths.policy_change_rel(first)
        stored = (self.root / relative).read_bytes()
        record = review.read_policy_change(first)
        self.assertEqual(stored, serialize.canonical_bytes(record))
        self.assertEqual(set(policy.CHANGE_FIELDS), set(record))
        # R6-2 item 3: it binds the complete baseline record the Candidate was reviewed under, by its exact digest
        self.assertEqual(record["global_baseline_digest"], serialize.digest(record["global_baseline"]))
        self.assertEqual(record["global_baseline_digest"],
                         review.read_candidate_snapshot(
                             review.gate_chain(record["review_run_id"]).generations[0].candidate_hash
                         ).material["global_baseline_digest"])
        profile = review.read_profile()
        chain = review.gate_chain(record["review_run_id"])
        self.assertEqual((chain.generations[0].candidate_hash, chain.latest.receipt_id),
                         (record["candidate_hash"], record["receipt_id"]))
        self.assertEqual((None, None, 1, profile.digest),
                         (record["before_profile_version"], record["before_profile_digest"],
                          record["after_profile_version"], record["after_profile_digest"]))
        # a tampered change record is a validation Problem, never silently re-read
        tampered = stored.replace(profile.digest.encode("ascii"), b"0" * 64)
        self.assertNotEqual(stored, tampered)
        (self.root / relative).write_bytes(tampered)
        self.assertNotEqual([], self.problems())


# =========================================================================== evaluations

class EvaluationTests(PolicyCase):
    template = "profiled"

    def first(self) -> str:
        (found,) = self.review_store.policy_change_ids()
        return found

    def evaluate(self, **kwargs: Any) -> project_policy.PolicyEvaluationResult:
        return project_policy.record_policy_evaluation(self.store, evaluation_request(self.first(), self.refs(),
                                                                                      **kwargs))

    def assert_profile_unchanged(self, before: bytes | None, head_before: str) -> None:
        self.assertEqual(before, self.profile_bytes())
        self.assertEqual(before, self.blob("HEAD", PROFILE))
        self.assertNotIn(PROFILE, self.git("diff", "--name-only", head_before, "HEAD").split())

    def assert_one_evaluation_commit(self, result: project_policy.PolicyEvaluationResult) -> None:
        relative = paths.policy_evaluation_rel(result.evaluation_id)
        (commit,) = self.commits_with(EVALUATION_SUBJECT)
        self.assertEqual(f"{EVALUATION_SUBJECT}{result.evaluation_id}", self.subject(commit))
        delta = self.delta(commit)
        self.assertEqual({relative}, set(delta))
        self.assertEqual(("A", "100644"), (delta[relative].status, delta[relative].mode))
        self.assertEqual((result.evaluation_id,), self.review_store.policy_evaluation_ids())

    def observed_runs(self) -> tuple[policy.EvidenceRef, ...]:
        """Two Review Runs AFTER the change: P6-capable (R6-1), two reviewers (required_slots 2), the change active."""
        before_runs = set(self.review_store.run_history_ids())
        for name in ("Observed One", "Observed Two"):
            rm.create_roadmap(self.store, plan(name), review=planning_review(reviewers=2))
        observed = tuple(ref for ref in self.refs() if ref.id not in before_runs)
        self.assertEqual(2, len(observed))
        review = self.review_store
        for ref in observed:
            frozen = p4.run_effective_policy(review, review.gate_chain(ref.id))
            self.assertIsNotNone(frozen, "a new Run is P6-capable and freezes its Effective Policy")
            self.assertIn(self.first(), [item["policy_change_id"] for item in frozen["active_experiments"]])
            self.assertEqual(2, policy.setting(frozen, policy.SURFACE_REQUIRED_SLOTS))
        return observed

    def test_retain_without_post_change_observation_is_refused(self) -> None:
        """§15.15 / §15.17: evidence from before the change never shows the change worked (RB6B-H1)."""
        before, head = self.profile_bytes(), self.commit_of()
        with self.assertRaises(StopError) as raised:
            self.evaluate(result=policy.RESULT_RETAIN, next_action=policy.NEXT_END_OBSERVATION)
        self.assertEqual(policy.CODE_EVALUATION_INVALID, raised.exception.code)
        self.assertEqual(head, self.commit_of(), "nothing is written for a refused retain")
        self.assertEqual(before, self.profile_bytes())
        self.assertEqual((), self.review_store.policy_evaluation_ids())
        self.assertEqual((self.first(),), tuple(item.policy_change_id for item in self.state().active))

    def test_retain_records_evidence_only_and_never_rewrites_the_profile(self) -> None:
        observed = self.observed_runs()
        before, head = self.profile_bytes(), self.commit_of()
        profile = self.review_store.read_profile()
        result = project_policy.record_policy_evaluation(self.store, evaluation_request(
            self.first(), observed, result=policy.RESULT_RETAIN, next_action=policy.NEXT_END_OBSERVATION))
        self.assert_profile_unchanged(before, head)
        self.assert_one_evaluation_commit(result)
        record = self.review_store.read_policy_evaluation(result.evaluation_id)
        self.assertEqual((self.first(), profile.profile_version, profile.digest),
                         (record["policy_change_id"], record["evaluated_profile_version"],
                          record["evaluated_profile_digest"]))
        self.assertEqual(self.review_store.read_policy_change(self.first())["measurement_contract"],
                         record["measurement_contract"])
        # the terminal evaluation settles the ref without rewriting the Profile merely to remove its string
        self.assertEqual((self.first(),), self.review_store.read_profile().active_experiment_refs)
        self.assertEqual((), self.state().active)
        self.assertEqual([], self.problems())

    def test_inconclusive_never_changes_the_profile_and_is_never_success(self) -> None:
        before, head = self.profile_bytes(), self.commit_of()
        with self.assertRaises(StopError) as raised:
            self.evaluate(result=policy.RESULT_INCONCLUSIVE, next_action=policy.NEXT_END_OBSERVATION)
        self.assertEqual(policy.CODE_EVALUATION_INVALID, raised.exception.code)
        self.assertEqual(head, self.commit_of(), "nothing is written for a refused evaluation")
        result = self.evaluate(result=policy.RESULT_INCONCLUSIVE, next_action=policy.NEXT_CONTINUE_OBSERVATION)
        self.assert_profile_unchanged(before, head)
        self.assert_one_evaluation_commit(result)
        self.assertEqual((self.first(),), tuple(item.policy_change_id for item in self.state().active),
                         "continued observation keeps the experiment active")
        self.assertEqual([], self.problems())

    def test_inconclusive_continues_only_where_the_frozen_contract_permits_it(self) -> None:
        request = self.request(after=3, supersedes=(self.first(),), overlap=policy.OVERLAP_KNOWN, continued=False)
        strict = self.applied(request, two_reviewers())
        before, head = self.profile_bytes(), self.commit_of()
        frozen = evaluation_request(strict.policy_change_id, self.refs(), result=policy.RESULT_INCONCLUSIVE,
                                    next_action=policy.NEXT_CONTINUE_OBSERVATION)
        with self.assertRaises(StopError) as raised:
            project_policy.record_policy_evaluation(self.store, frozen)
        self.assertEqual(policy.CODE_EVALUATION_INVALID, raised.exception.code)
        self.assertEqual(head, self.commit_of())
        result = project_policy.record_policy_evaluation(self.store, evaluation_request(
            strict.policy_change_id, self.refs(), result=policy.RESULT_INCONCLUSIVE,
            next_action=policy.NEXT_NEW_CANDIDATE))
        self.assertEqual(policy.NEXT_NEW_CANDIDATE, result.next_action)
        self.assert_profile_unchanged(before, head)

    def test_adjust_and_rollback_record_evidence_and_need_a_new_candidate(self) -> None:
        before, head = self.profile_bytes(), self.commit_of()
        for result_name in (policy.RESULT_ADJUST, policy.RESULT_ROLLBACK):
            for wrong in (policy.NEXT_END_OBSERVATION, policy.NEXT_CONTINUE_OBSERVATION):
                with self.subTest(result_name, next_action=wrong), self.assertRaises(StopError):
                    self.evaluate(result=result_name, next_action=wrong)
        adjust = self.evaluate(result=policy.RESULT_ADJUST, next_action=policy.NEXT_NEW_CANDIDATE)
        rollback = self.evaluate(result=policy.RESULT_ROLLBACK, next_action=policy.NEXT_NEW_CANDIDATE)
        self.assertNotEqual(adjust.evaluation_id, rollback.evaluation_id)
        self.assert_profile_unchanged(before, head)
        self.assertEqual((self.first(),), tuple(item.policy_change_id for item in self.state().active),
                         "an adjust / rollback evaluation leaves the experiment to a new Candidate")
        # the Profile changes only through a new reviewed Candidate
        change = self.applied(self.request(direction=policy.DIRECTION_ROLLBACK, after=1, rolls_back=self.first()),
                              two_reviewers())
        self.assertEqual(2, self.review_store.read_profile().profile_version)
        self.assertNotEqual(before, self.profile_bytes())
        self.assertTrue(change.policy_commit)
        self.assertEqual([], self.problems())


class EvaluationRetryTests(PolicyCase):
    """§30.40: an evaluation retry keeps the same evaluation_id and never changes the Profile."""

    template = "profiled"

    def windows(self):
        def reserved(calls, mutation, key, kind):
            return kind == "review_policy_evaluation"

        def completing(mutation):
            raise Interrupted("before completion")

        return (
            ("evaluation_id reserved", lambda: crash_at(Mutation, "reserve_id", after=True, when=reserved), Crash),
            ("evaluation stage recorded", lambda: after_recording(project_policy.STAGE_EVALUATION), Interrupted),
            ("evaluation record created, flag not saved",
             lambda: after_effect("create_file", project_policy.STAGE_EVALUATION), Interrupted),
            ("evaluation commit made, flag not saved",
             lambda: after_effect("git_commit", project_policy.STAGE_EVALUATION_FINALIZE), Interrupted),
            ("before completion", lambda: mock.patch.object(Mutation, "complete", completing), Interrupted),
        )

    def test_an_evaluation_retry_keeps_its_evaluation_id(self) -> None:
        (first,) = self.review_store.policy_change_ids()
        for name, window, expected in self.windows():
            with self.subTest(name):
                self.store = self._fresh()
                request = evaluation_request(first, self.refs(), result=policy.RESULT_INCONCLUSIVE,
                                             next_action=policy.NEXT_CONTINUE_OBSERVATION)
                before = self.profile_bytes()
                with window(), self.assertRaises(expected):
                    project_policy.record_policy_evaluation(self.store, request)
                (pending,) = [record for record in self.owner_pending()
                              if record["invocation"].get("operation") == project_policy.OPERATION_EVALUATION]
                (reserved,) = [value for key, value in pending["reserved_ids"].items()
                               if key.startswith(project_policy.POLICY_EVALUATION_KEY)]
                result = project_policy.record_policy_evaluation(self.store, request)
                self.assertEqual(reserved, result.evaluation_id, "the retry keeps the evaluation_id")
                self.assertEqual((reserved,), self.review_store.policy_evaluation_ids(), "one evaluation record")
                self.assertEqual(1, len(self.commits_with(EVALUATION_SUBJECT)), "one evaluation commit")
                self.assertEqual(before, self.profile_bytes(), "never a Profile change")
                self.assertEqual([], self.owner_pending())
                self.assertEqual([], self.problems())

    def _fresh(self):
        from project_policy_helpers import _restore

        self.store = _restore(self, self.template)
        self.root = self.store.root
        return self.store


if __name__ == "__main__":
    unittest.main()
