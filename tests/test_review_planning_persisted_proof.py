"""P2 §28 E: the persisted proof over Kp - C-2(Kp) P1-P12, the planning commit primitive, hooks and signing."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from helpers import git
from planning_helpers import (
    CANONICAL_RULE, Crash, PlanningTestCase, Reviewer, crash_at, executable_registration, plan, rr, run_ids,
)
from workline import committed_view as committed_view_module
from workline import gitcmd
from workline import gitops
from workline import mutation as mutation_module
from workline import roadmap as rm
from workline import yamlish
from workline.errors import ReconcileRequired, StopError
from workline.review import publication, records, serialize
from workline.review import paths as review_paths
from workline.review.store import ReviewStore


class _KpCase(PlanningTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project(remote=True)
        self.other = rm.create_roadmap(self.store, plan("Other Roadmap")).roadmap_id
        self.reviewer = Reviewer()

    def run_plan(self):
        return self.reviewed_roadmap(self.store, self.reviewer)

    def proof_fails(self, item: str | None = None) -> ReconcileRequired:
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_persisted_proof_failed", raised.exception.reason)
        if item:
            self.assertIn(item, str(raised.exception))
        self.assertFalse(ReviewStore(self.store).consumption_ids(), "no Consumption")
        self.assertFalse([e for r in self.pending(self.store) for e in r["effects"] if e["kind"] == "git_push"], "no push")
        return raised.exception

    def barrier_holds_for_head(self) -> None:
        self.assertIsNotNone(publication.barrier_problem(self.store.root, self.head(self.store)))
        # every subsequent Workline publication of a history holding Kp is refused (a disjoint-scope legacy hold)
        with self.assertRaises(StopError) as raised:
            rm.hold_roadmap(self.store, self.other)
        self.assertEqual("review_publication_barrier", raised.exception.code)


def _kp_paths(paths: list[str]) -> bool:
    return any("/roadmaps/" in path for path in paths)


class ModeAndScopeTests(_KpCase):
    def test_a_changed_mode_is_detected(self) -> None:
        with executable_registration():
            self.proof_fails("P3")
        kp = self.head(self.store)
        roadmap = [p for p in git(self.store.root, "show", "--name-only", "--format=", kp).splitlines() if "/roadmaps/" in p][0]
        self.assertTrue(git(self.store.root, "ls-tree", kp, "--", roadmap).startswith("100755"), "the fixture changed the mode")
        self.barrier_holds_for_head()

    def test_an_extra_path_is_detected(self) -> None:
        real = gitcmd.contained_commit

        def commit_extra(repo, message, paths, hooks):
            if _kp_paths(paths):
                (Path(repo) / ".workline" / "derivations").mkdir(exist_ok=True)
                extra = ".workline/derivations/extra.md"
                (Path(repo) / extra).write_text("# extra\n", encoding="utf-8", newline="\n")
                git(repo, "add", extra)
                paths = list(paths) + [extra]
            real(repo, message, paths, hooks)

        with mock.patch.object(gitcmd, "contained_commit", commit_extra):
            self.proof_fails("P3")

    def test_a_missing_path_is_detected(self) -> None:
        real = gitcmd.contained_commit

        def commit_less(repo, message, paths, hooks):
            if _kp_paths(paths):
                paths = [p for p in paths if not p.endswith("roadmap.yaml")]
            real(repo, message, paths, hooks)

        with mock.patch.object(gitcmd, "contained_commit", commit_less):
            with self.assertRaises(ReconcileRequired) as raised:
                self.run_plan()
        # the ledger left uncommitted is either the proof's missing path or a commit that is not this mutation's own
        self.assertIn(raised.exception.reason, ("review_persisted_proof_failed", "review_commit_unowned"))
        self.assertFalse(ReviewStore(self.store).consumption_ids())

    def test_a_ledger_with_an_extra_relation_is_detected(self) -> None:
        real = gitcmd.contained_add

        def add_with_extra_relation(repo, paths, hooks):
            if _kp_paths(paths):
                ledger = Path(repo) / ".workline" / "relations" / "roadmap.yaml"
                data = yamlish.load(ledger.read_text(encoding="utf-8"))
                extra = dict(data["relations"][-1])
                extra["id"] = "rel_01ARZ3NDEKTSV4RRFFQ69G5FAV"
                data["relations"].append(extra)
                ledger.write_text(yamlish.dump(data), encoding="utf-8", newline="\n")
            real(repo, paths, hooks)

        with mock.patch.object(gitcmd, "contained_add", add_with_extra_relation):
            self.proof_fails("P3")


class CommittedReloadTests(_KpCase):
    def test_the_semantic_reload_uses_the_committed_result_loader(self) -> None:
        loaded: list[str] = []
        real = committed_view_module.committed_view

        def spy(store, commit):
            loaded.append(commit)
            return real(store, commit)

        with mock.patch.object(rr, "committed_view", spy):
            result = self.run_plan()
        consumption = ReviewStore(self.store).read_consumption(result.consumption_id)
        kp = consumption.persisted_result["registration_commit"]
        parent = consumption.persisted_result["registration_parent"]
        self.assertIn(kp, loaded)
        self.assertIn(parent, loaded)


class TransformTests(_KpCase):
    def test_a_transform_attribute_is_refused_by_the_preflight(self) -> None:
        for rule in ("*.md ident", "*.md working-tree-encoding=UTF-16", "*.yaml filter=lfs"):
            with self.subTest(rule=rule):
                store = self.planning_project(f"t{abs(hash(rule)) % 1000}", attributes=rule + "\n" + CANONICAL_RULE + "\n")
                with self.assertRaises(StopError) as raised:
                    self.reviewed_roadmap(store)
                self.assertEqual("review_git_transform", raised.exception.code)
                self.assertEqual((), run_ids(store))

    def test_a_transformation_forced_after_the_preflight_is_caught_by_the_proof(self) -> None:
        git(self.store.root, "config", "filter.shout.clean", "sed s/Phase/PHASE/")
        git(self.store.root, "config", "filter.shout.smudge", "cat")
        self.commit_attributes(self.store, "*.md filter=shout\n" + CANONICAL_RULE + "\n")
        with mock.patch.object(gitops, "require_no_planning_transform", lambda repo, paths: None):
            self.proof_fails("P3")


class HooksAndSigningTests(PlanningTestCase):
    def test_no_hook_and_no_signing_program_runs(self) -> None:
        store = self.planning_project(remote=True)
        marker = store.root.parent / "hook-ran.txt"
        hooks = store.root / ".git" / "hooks"
        custom = store.root.parent / "custom-hooks"
        custom.mkdir()
        script = f"#!/bin/sh\necho ran >> '{marker.as_posix()}'\ngit push origin HEAD:refs/heads/hooked 2>/dev/null\nexit 1\n"
        for directory in (hooks, custom):
            for name in ("pre-commit", "commit-msg", "post-commit", "prepare-commit-msg"):
                (directory / name).write_text(script, encoding="utf-8", newline="\n")
        signer = store.root.parent / "signer.sh"
        signer.write_text(f"#!/bin/sh\necho signed >> '{marker.as_posix()}'\nexit 1\n", encoding="utf-8", newline="\n")
        git(store.root, "config", "commit.gpgSign", "true")
        git(store.root, "config", "gpg.program", signer.as_posix())
        git(store.root, "config", "core.hooksPath", custom.as_posix())
        result = self.reviewed_roadmap(store)
        self.assertEqual("registered", result.status)
        self.assertFalse(marker.exists(), "no hook and no signing program ran")
        self.assertEqual("", git(store.root, "log", "-1", "--format=%GS").strip())
        self.assertEqual("", git(self.tmp, "--git-dir", str(self.remote_path()), "branch", "--list", "hooked").strip())


class UnownedKpTests(_KpCase):
    def test_a_kp_without_its_saved_id_is_unowned_and_the_barrier_holds(self) -> None:
        with crash_at(mutation_module, "_make_planning_commit", after=True,
                      when=lambda n, store, payload, paths: payload.get("base_exact") is True):
            with self.assertRaises(Crash):
                self.run_plan()
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_commit_unowned", raised.exception.reason)
        self.assertFalse(ReviewStore(self.store).consumption_ids())
        self.barrier_holds_for_head()


class P12Tests(_KpCase):
    """A generation 4, a Supersession or a Consumption of the Receipt in P's tree (fixture) is refused by P12."""

    def _in_parent_only(self, relative: str, record: dict) -> None:
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.run_plan()
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialize.canonical_text(record), encoding="utf-8", newline="\n")
        self.commit_all(self.store, "a person commits a Review record", relative)
        target.unlink()  # present in P's tree, absent from the working tree

    def _receipt(self):
        (run_id,) = run_ids(self.store)
        chain = self.chain(self.store, run_id)
        return run_id, chain

    def test_a_supersession_in_the_parent(self) -> None:
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.run_plan()
        run_id, chain = self._receipt()
        receipt_id = chain.latest.receipt_id
        relative = review_paths.supersession_rel(receipt_id)
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialize.canonical_text(records.Supersession(receipt_id, run_id, 4, "fixture").to_record()),
                          encoding="utf-8", newline="\n")
        self.commit_all(self.store, "a person commits a Supersession", relative)
        target.unlink()
        self.proof_fails("P12")

    def test_a_consumption_in_the_parent(self) -> None:
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.run_plan()
        run_id, chain = self._receipt()
        first = chain.generations[0]
        consumption = records.Consumption(
            "rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV", chain.latest.receipt_id, run_id, 3, "custom-kind", first.candidate_hash,
            first.operation_identity, "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV", None, None, first.target_identity, None,
        )
        relative = review_paths.consumption_rel(consumption.consumption_id)
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialize.canonical_text(consumption.to_record()), encoding="utf-8", newline="\n")
        self.commit_all(self.store, "a person commits a Consumption", relative)
        target.unlink()
        self.proof_fails("P12")

    def test_a_generation_4_in_the_parent(self) -> None:
        from dataclasses import replace

        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.run_plan()
        run_id, chain = self._receipt()
        fourth = replace(chain.latest, generation=4, previous_generation=3, previous_digest=chain.latest_digest,
                         status="open", receipt_id=None, authorized_operation_stage=None)
        relative = review_paths.gate_rel(run_id, 4)
        target = self.store.root / relative
        target.write_text(serialize.canonical_text(fourth.to_record()), encoding="utf-8", newline="\n")
        self.commit_all(self.store, "a person commits a generation 4", relative)
        target.unlink()
        self.proof_fails("P12")


if __name__ == "__main__":
    unittest.main()
