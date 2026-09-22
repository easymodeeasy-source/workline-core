"""P2 §28 D: semantic projection and currency - round trips, reader loss, R9, and currency at every moment."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock

from helpers import git
from planning_helpers import Crash, PlanningTestCase, Reviewer, crash_at, design, plan, rr, run_ids
from workline import gitcmd
from workline import mutation as mutation_module
from workline import roadmap as rm
from workline.errors import ReconcileRequired, SpecViolation, StopError, ValidationError
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.review import planning, publication, serialize
from workline.review import paths as review_paths
from workline.review.store import ReviewStore


def changed_authority():
    real = planning._read_authority

    def changed(path):
        data = real(path)
        return data + b"\n<!-- authority changed -->\n" if str(path).endswith("registry.md") else data

    return mock.patch.object(planning, "_read_authority", changed)


def changed_policy():
    return mock.patch.dict(planning.POLICY_RECORD, {"repair": "a changed repair rule"})


def changed_loader(tmp: Path):
    """The running implementation with one package file changed: the production identity over a changed copy."""
    real = planning.loader_identity
    target = Path(tmp) / "changed-implementation" / "workline"

    def changed(directory):
        if not target.exists():
            shutil.copytree(directory, target, ignore=shutil.ignore_patterns("__pycache__"))
            module = target / "review" / "planning.py"
            module.write_bytes(module.read_bytes() + b"\n# one changed package file\n")
        return real(target)

    return mock.patch.object(planning, "loader_identity", changed)


class _CurrencyCase(PlanningTestCase):
    """A review-v1 Roadmap creation whose plan names an existing Phase X of another Roadmap."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project(remote=True)
        other = rm.create_roadmap(self.store, rm.RoadmapPlan("Other", "背景", "状態", {"x": PhaseSpec("X", "X が成立する")}))
        self.x = other.phase_ids["x"]
        self.the_plan = rm.RoadmapPlan(
            "Planned", "背景", "状態",
            {"a": PhaseSpec("A", "A が成立する"), "b": PhaseSpec("B", "B が成立する")},
            (PhaseRelationSpec("planned_next", self.x, "a"), PhaseRelationSpec("planned_next", "a", "b")),
        )
        self.reviewer = Reviewer()

    def run_plan(self):
        return self.reviewed_roadmap(self.store, self.reviewer, self.the_plan)

    def crash(self, target, name, **kwargs) -> None:
        with crash_at(target, name, **kwargs):
            with self.assertRaises(Crash):
                self.run_plan()

    def run_id(self) -> str:
        (found,) = run_ids(self.store)
        return found

    def no_kp_no_consumption(self) -> None:
        self.assertFalse(any("create roadmap Planned" in s or "create roadmap R-02" in s for s in self.subjects(self.store)))
        self.assertFalse(ReviewStore(self.store).consumption_ids())
        chain = self.chain(self.store, self.run_id())
        self.assertEqual(3, chain.latest.generation, "never generation 4 once the registration began")


def _factor_context(factor: str, test: _CurrencyCase):
    if factor == "authority":
        return changed_authority()
    if factor == "policy":
        return changed_policy()
    if factor == "loader":
        return changed_loader(test.tmp)
    raise AssertionError(factor)


class FourMomentsTests(_CurrencyCase):
    """P2-CONTRACT-003: authority text, Policy, loader identity and a declared-base fact, changed at four moments."""

    # after the review, before the registration: generation 4, stale
    def _moment_1(self, change) -> None:
        self.crash(rr, "_use_check")
        with change:
            result = self.run_plan()
        self.assertEqual("stale", result.status)
        self.assertEqual(4, self.chain(self.store, self.run_id()).latest.generation)

    def test_moment_1_authority(self) -> None:
        self._moment_1(changed_authority())

    def test_moment_1_policy(self) -> None:
        self._moment_1(changed_policy())

    def test_moment_1_loader(self) -> None:
        self._moment_1(changed_loader(self.tmp))

    def test_moment_1_declared_base(self) -> None:
        self.crash(rr, "_use_check")
        rm.hold_phase(self.store, self.x)
        result = self.run_plan()
        self.assertEqual(("stale", planning.STALE_DECLARED_BASE), (result.status, result.detail))
        self.assertEqual(4, self.chain(self.store, self.run_id()).latest.generation)
        self.assertTrue(ReviewStore(self.store).supersession_exists(result.receipt_id))

    def test_the_changed_loader_is_a_changed_package_file(self) -> None:
        from workline.implementation import package_directory

        package = package_directory(self.store.workline_root())
        with changed_loader(self.tmp):
            changed = planning.loader_identity(package)
        self.assertNotEqual(planning.loader_identity(package), changed)
        copy = self.tmp / "changed-implementation" / "workline"
        differing = [path.relative_to(copy).as_posix() for path in copy.rglob("*.py")
                     if path.read_bytes() != (package / path.relative_to(copy)).read_bytes()]
        self.assertEqual(["review/planning.py"], differing)

    # after the first registration stage, before Kp is recorded: the pre-Kp currency proof refuses
    def _moment_2(self, change, reason: str = "review_registration_currency_changed") -> None:
        self.crash(rm, "register_phases")
        with change:
            with self.assertRaises(ReconcileRequired) as raised:
                self.run_plan()
        self.assertEqual(reason, raised.exception.reason)
        self.no_kp_no_consumption()
        self.assertFalse([e for r in self.pending(self.store) for e in r["effects"] if e["kind"] == "git_push"])

    def test_moment_2_authority(self) -> None:
        self._moment_2(changed_authority())

    def test_moment_2_policy(self) -> None:
        self._moment_2(changed_policy())

    def test_moment_2_loader(self) -> None:
        self._moment_2(changed_loader(self.tmp))

    def test_moment_2_declared_base(self) -> None:
        self.crash(rm, "register_phases")
        rm.hold_phase(self.store, self.x)  # a disjoint-scope operation commits after the registration began
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_registration_currency_changed", raised.exception.reason)
        self.no_kp_no_consumption()

    # after the Kp stage is recorded, before it is made: the pre-replay proof refuses, Kp is not made
    def _crash_before_kp_is_made(self) -> None:
        self.crash(mutation_module, "_make_planning_commit",
                   when=lambda n, store, payload, paths: payload.get("base_exact") is True)
        (record,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-create"]
        self.assertTrue(any(e["stage"] == rr.STAGE_KP for e in record["effects"]))

    def _moment_3(self, change) -> None:
        self._crash_before_kp_is_made()
        with change:
            with self.assertRaises(ReconcileRequired) as raised:
                self.run_plan()
        self.assertEqual("review_registration_currency_changed", raised.exception.reason)
        self.no_kp_no_consumption()

    def test_moment_3_authority(self) -> None:
        self._moment_3(changed_authority())

    def test_moment_3_policy(self) -> None:
        self._moment_3(changed_policy())

    def test_moment_3_loader(self) -> None:
        self._moment_3(changed_loader(self.tmp))

    def test_moment_3_declared_base(self) -> None:
        self._crash_before_kp_is_made()
        rm.hold_phase(self.store, self.x)
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        # HEAD is no longer the recorded parent: the base-exact Kp is refused before any replay
        self.assertEqual("review_registration_base_moved", raised.exception.reason)
        self.no_kp_no_consumption()

    # after Kp is made: C-2(Kp) P12 refuses, no Consumption, the barrier holds
    def _moment_4(self, change) -> None:
        self.crash(rr, "_c2_kp")
        kp = self.head(self.store)
        with change:
            with self.assertRaises(ReconcileRequired) as raised:
                self.run_plan()
        self.assertEqual("review_persisted_proof_failed", raised.exception.reason)
        self.assertIn("P12", str(raised.exception))
        self.assertFalse(ReviewStore(self.store).consumption_ids())
        self.assertIsNotNone(publication.barrier_problem(self.store.root, kp))

    def test_moment_4_authority(self) -> None:
        self._moment_4(changed_authority())

    def test_moment_4_policy(self) -> None:
        self._moment_4(changed_policy())

    def test_moment_4_loader(self) -> None:
        self._moment_4(changed_loader(self.tmp))

    def test_moment_4_declared_base_hold_after_kp_waits_for_the_publication(self) -> None:
        """With a push destination a hold after Kp cannot commit: its push would publish Kp (§18.7, §21.1 row 25)."""
        self.crash(rr, "_c2_kp")
        kp = self.head(self.store)
        with self.assertRaises(StopError) as raised:
            rm.hold_phase(self.store, self.x)
        self.assertEqual("review_publication_barrier", raised.exception.code)
        self.assertEqual(kp, self.head(self.store), "the hold made no commit")
        result = self.run_plan()
        self.assertEqual("registered", result.status)
        consumption = ReviewStore(self.store).read_consumption(result.consumption_id)
        self.assertEqual(kp, consumption.persisted_result["registration_commit"])
        held = rm.hold_phase(self.store, self.x)
        self.assertEqual(held.head, self.remote_head())

    def test_moment_4_declared_base_committed_after_kp_is_not_on_its_parent(self) -> None:
        """Remote-less, the hold commits on top of Kp; P12 reads the declared base on Kp's parent P (§13.1, §15.3)."""
        store = self.planning_project("local")
        other = rm.create_roadmap(store, rm.RoadmapPlan("Other", "背景", "状態", {"x": PhaseSpec("X", "X が成立する")}))
        x = other.phase_ids["x"]
        the_plan = rm.RoadmapPlan(
            "Planned", "背景", "状態",
            {"a": PhaseSpec("A", "A が成立する"), "b": PhaseSpec("B", "B が成立する")},
            (PhaseRelationSpec("planned_next", x, "a"), PhaseRelationSpec("planned_next", "a", "b")),
        )
        with crash_at(rr, "_c2_kp"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store, Reviewer(), the_plan)
        kp = self.head(store)
        rm.hold_phase(store, x)
        self.assertEqual(kp, git(store.root, "rev-parse", "HEAD~1").strip(), "the hold committed on top of Kp")
        result = self.reviewed_roadmap(store, Reviewer(), the_plan)
        self.assertEqual("registered", result.status)
        consumption = ReviewStore(store).read_consumption(result.consumption_id)
        self.assertEqual(kp, consumption.persisted_result["registration_commit"])

    def test_moment_4_declared_base_difference_on_the_parent_is_p12(self) -> None:
        """Fixture: the pre-Kp proof bypassed, Kp is made on a P holding the changed fact; C-2(Kp) names P12, never P9."""
        self.crash(rm, "register_phases")
        rm.hold_phase(self.store, self.x)  # committed and published: nothing unproven is in its history yet
        with mock.patch.object(rr, "_pre_kp_proof", lambda *args, **kwargs: None):
            with self.assertRaises(ReconcileRequired) as raised:
                self.run_plan()
        self.assertEqual("review_persisted_proof_failed", raised.exception.reason)
        self.assertIn("C-2(Kp) P12", str(raised.exception))
        self.assertFalse(ReviewStore(self.store).consumption_ids())
        self.assertIsNotNone(publication.barrier_problem(self.store.root, self.head(self.store)))


class IndependentAdvanceTests(_CurrencyCase):
    def test_a_disjoint_scope_operations_commit_lets_kp_be_made_on_the_new_head(self) -> None:
        unrelated = rm.create_roadmap(self.store, rm.RoadmapPlan("Unrelated", "背景", "状態", {"u": PhaseSpec("U", "U")}))
        self.crash(rm, "register_phases")
        (record,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-create"]
        use_check_head = record["notes"][rr.NOTE_USE_CHECK_HEAD]
        held = rm.hold_roadmap(self.store, unrelated.roadmap_id)  # the event log only: no planning-owned path
        self.assertEqual(held.head, self.remote_head())
        result = self.run_plan()
        self.assertEqual("registered", result.status)
        persisted = ReviewStore(self.store).read_consumption(result.consumption_id).persisted_result
        self.assertEqual(held.head, persisted["registration_parent"], "Kp is made on the new HEAD")
        self.assertNotEqual(use_check_head, persisted["registration_parent"], "P is not use_check_head")
        self.assertEqual(self.head(self.store), self.remote_head())

    def test_an_independent_commit_touching_nothing_planned_lets_kp_be_made_on_the_new_head(self) -> None:
        self.crash(rm, "register_phases")
        (self.store.root / "notes.txt").write_text("unrelated\n", encoding="utf-8")
        advanced = self.commit_all(self.store, "an unrelated commit", "notes.txt")
        result = self.run_plan()
        self.assertEqual("registered", result.status)
        consumption = ReviewStore(self.store).read_consumption(result.consumption_id)
        self.assertEqual(advanced, consumption.persisted_result["registration_parent"])

    def test_a_commit_touching_a_planning_owned_path_moves_the_base(self) -> None:
        self.crash(rm, "register_phases")
        roadmap_file = sorted((self.store.root / ".workline" / "roadmaps").glob("*.md"))[-1]
        self.commit_all(self.store, "a person commits the Roadmap file", roadmap_file.relative_to(self.store.root).as_posix())
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_registration_base_moved", raised.exception.reason)
        self.no_kp_no_consumption()

    def test_a_commit_changing_a_declared_base_fact(self) -> None:
        self.crash(rm, "register_phases")
        rm.hold_phase(self.store, self.x)
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_registration_currency_changed", raised.exception.reason)

    def test_a_history_that_no_longer_holds_use_check_head(self) -> None:
        self.crash(mutation_module, "_make_planning_commit",
                   when=lambda n, store, payload, paths: payload.get("base_exact") is True)
        git(self.store.root, "reset", "-q", "--soft", "HEAD~1")
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_registration_base_moved", raised.exception.reason)


class KpParentTests(_CurrencyCase):
    def test_head_moved_between_the_record_and_the_commit(self) -> None:
        real = gitcmd.contained_add

        def add_then_advance(repo, paths, hooks):
            real(repo, paths, hooks)
            if any(path.endswith(".md") and "/roadmaps/" in path for path in paths):
                (repo / "late.txt").write_text("late\n", encoding="utf-8")
                git(repo, "add", "late.txt")
                git(repo, "commit", "-q", "--only", "-m", "a late commit", "late.txt")

        with mock.patch.object(gitcmd, "contained_add", add_then_advance):
            with self.assertRaises(ReconcileRequired) as raised:
                self.run_plan()
        self.assertEqual("review_registration_base_moved", raised.exception.reason)
        self.assertEqual("a late commit", self.subjects(self.store)[0], "Kp is not made")
        # and never by the independent-advancement path on a resume
        with self.assertRaises(ReconcileRequired) as again:
            self.run_plan()
        self.assertEqual("review_registration_base_moved", again.exception.reason)

    def test_a_kp_forced_onto_another_parent(self) -> None:
        from workline import yamlish

        self.crash(rr, "_c2_kp")
        (record,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-create"]
        kp = [e for e in record["effects"] if e["stage"] == rr.STAGE_KP][0]
        kp["commit_id"] = git(self.store.root, "rev-parse", "HEAD~1").strip()  # a commit on another parent
        path = self.store.mutations / f"{record['mutation_id']}.yaml"
        path.write_text(yamlish.dump(record), encoding="utf-8", newline="\n")
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_persisted_proof_failed", raised.exception.reason)
        self.assertIn("P2", str(raised.exception))
        self.assertFalse(ReviewStore(self.store).consumption_ids())


class CommittedBaseTests(_CurrencyCase):
    def test_an_uncommitted_declared_base_change_after_the_use_check_changes_nothing(self) -> None:
        self.crash(rm, "register_phases")
        events = self.store.root / ".workline" / "events" / "events.jsonl"
        events.write_text(
            events.read_text(encoding="utf-8")
            + '{"id":"evt_01ARZ3NDEKTSV4RRFFQ69G5FAV","type":"phase_held","entity":"' + self.x + '","at":"2026-01-01T00:00:00+00:00"}\n',
            encoding="utf-8", newline="\n",
        )
        result = self.run_plan()
        self.assertEqual("registered", result.status)

    def test_a_named_entity_present_only_in_the_working_tree(self) -> None:
        store = self.planning_project("wt-only")
        other = rm.create_roadmap(store, rm.RoadmapPlan("Other", "背景", "状態", {"x": PhaseSpec("X", "X が成立する")}))
        git(store.root, "reset", "-q", "--soft", "HEAD~1")  # the Phase is in the working tree, not in HEAD
        the_plan = rm.RoadmapPlan("Planned", "背景", "状態", {"a": PhaseSpec("A", "A")},
                                  (PhaseRelationSpec("planned_next", other.phase_ids["x"], "a"),))
        with self.assertRaises(ValidationError) as raised:
            self.reviewed_roadmap(store, Reviewer(), the_plan)
        self.assertEqual("review_base_uncommitted", raised.exception.code)
        self.assertEqual((), run_ids(store))
        self.assertEqual([], [r for r in self.pending(store) if r["invocation"].get("operation") == "roadmap-create"])


class StaleBeforeTheSealTests(_CurrencyCase):
    def test_a_declared_base_change_before_the_seal_is_stale_and_writes_nothing(self) -> None:
        self.crash(rr, "_launch_and_settle")
        rm.hold_phase(self.store, self.x)
        result = self.run_plan()
        self.assertEqual(("stale", planning.STALE_DECLARED_BASE, None), (result.status, result.detail, result.receipt_id))
        self.assertEqual(1, self.chain(self.store, self.run_id()).latest.generation)
        self.assertFalse(ReviewStore(self.store).superseded_receipt_ids())


class RoundTripTests(PlanningTestCase):
    POINTS = {
        "_setup_new_run": "the representability check (§7.6)",
        "_registration_flow": "the working-tree round trip (§15.1 step 2)",
        "_c2_kp": "the persisted proof, P8",
        "_prove": "the committed planning proof, CP6",
    }

    def test_round_trips_are_exact_at_all_three_points(self) -> None:
        store = self.planning_project(remote=True)
        seen: dict[tuple[str, str], list[bool]] = {}
        real = rr.semantic_projection

        def spy(material, view, selection_view=None):
            found = real(material, view, selection_view)
            frame = sys._getframe(1)
            while frame is not None and frame.f_code.co_name not in self.POINTS:
                frame = frame.f_back
            point = frame.f_code.co_name if frame is not None else "elsewhere"
            seen.setdefault((material["review_kind"], point), []).append(found == rr.reviewed_projection(material))
            return found

        with mock.patch.object(rr, "semantic_projection", spy):
            roadmap = self.reviewed_roadmap(store)
            self.reviewed_entry(store, roadmap.registration.phase_ids["a"])
        for kind in (planning.KIND_ROADMAP, planning.KIND_PHASE_ENTRY):
            for point, described in self.POINTS.items():
                with self.subTest(kind=kind, point=described):
                    self.assertIn((kind, point), seen)
                    self.assertTrue(all(seen[(kind, point)]), "exact")
        self.assertNotIn("elsewhere", {point for _, point in seen})


class ReaderLossTests(PlanningTestCase):
    """Every loss the production reader makes of a caller value is refused before Review (§7.6)."""

    def test_reader_loss_inputs_are_unrepresentable(self) -> None:
        store = self.planning_project()
        phase = {"a": PhaseSpec("A", "A")}
        cases = {
            "trailing space in a name": rm.RoadmapPlan("Roadmap ", "背景", "状態", phase),
            "a leading space in a name": rm.RoadmapPlan(" Roadmap", "背景", "状態", phase),
            "a trailing newline in a name": rm.RoadmapPlan("Roadmap\n", "背景", "状態", phase),
            "a second line in a name": rm.RoadmapPlan("RM\nsecond line", "背景", "状態", phase),
            "a heading injected through the name": rm.RoadmapPlan("RM\n## 達成したい状態\nINJECTED", "背景", "状態", phase),
            "a heading injected into a section": rm.RoadmapPlan("R", "背景\n## 注入", "状態", phase),
            "the desired-state heading in the background": rm.RoadmapPlan("R", "BG\n## 達成したい状態\nINJECTED", "DS", phase),
            "a lone CR": rm.RoadmapPlan("R", "背景\rつづき", "状態", phase),
            "CRLF": rm.RoadmapPlan("R", "背景\r\nつづき", "状態", phase),
            "CRLF in the desired state": rm.RoadmapPlan("R", "背景", "line1\r\nline2", phase),
            "a heading line in the desired state": rm.RoadmapPlan("R", "背景", "x\n## other\ny", phase),
            "U+2028 in a name": rm.RoadmapPlan("R\u2028S", "背景", "状態", phase),
            "U+2028 in a Phase name": rm.RoadmapPlan("R", "背景", "状態", {"a": PhaseSpec("A\u2028B", "A")}),
            "a trailing space in a Phase name": rm.RoadmapPlan("R", "背景", "状態", {"a": PhaseSpec("A ", "A")}),
            "a Phase desired state repeating its heading": rm.RoadmapPlan(
                "R", "背景", "状態", {"a": PhaseSpec("A", "A\n## 成立させたい状態\nB")}),
        }
        for label, the_plan in cases.items():
            with self.subTest(label):
                with self.assertRaises(ValidationError) as raised:
                    self.reviewed_roadmap(store, Reviewer(), the_plan)
                self.assertEqual("review_candidate_unrepresentable", raised.exception.code)
                self.assertEqual((), run_ids(store), "refused before any Review record")
                self.assertFalse(any((store.root / ".workline" / "roadmaps").glob("*.md")))
                self.assertEqual([], self.pending(store))

    def test_phase_entry_reader_loss_inputs_are_unrepresentable(self) -> None:
        store = self.planning_project()
        phase_id = rm.create_roadmap(store, plan()).phase_ids["a"]

        def entry(name: str, desired: str) -> rm.PhaseEntryDesign:
            return rm.PhaseEntryDesign(
                {"w1": rm.WorkDesign(name, desired, ())},
                rm.WorkDesign("Integration", "全Workの統合確認が取れている", ()),
                rm.WorkDesign("Confirmation", "人間が成果を確認した"),
                planned_next=(), requires_completion=(), entry=None,
            )

        cases = {
            "a newline in a Work name": entry("W\nsecond", "W が成立する"),
            "a trailing space in a Work name": entry("W ", "W が成立する"),
            "CRLF in a Work desired state": entry("W", "line1\r\nline2"),
            "a Work desired state repeating its heading": entry("W", "a\n## このWorkで成立させる状態\nb"),
            "a lone CR in a Work desired state": entry("W", "a\rb"),
        }
        for label, the_design in cases.items():
            with self.subTest(label):
                with self.assertRaises(ValidationError) as raised:
                    self.reviewed_entry(store, phase_id, Reviewer(), the_design)
                self.assertEqual("review_candidate_unrepresentable", raised.exception.code)
                self.assertEqual((), run_ids(store), "refused before any Review record")
                self.assertFalse(any((store.root / ".workline" / "works").glob("*.md")))
                self.assertEqual([], self.pending(store))


class PhaseEntryRoadmapHoldTests(PlanningTestCase):
    """§28 D names the declared-base factor "a hold of the Phase's Roadmap committed by a disjoint-scope operation in a
    crash window". For a review-v1 Phase entry that hold is refused by the live Roadmap-state check the frozen entry
    order runs first on every call (§5.6 step 2), before any currency evaluation; the planning mutation stays pending,
    and once the Roadmap is resumed the flow goes on. (For a Roadmap creation, a hold of a named Phase's Roadmap is no
    declared-base fact: phase lifecycle and state read the Phase's own events; FourMomentsTests hold the Phase itself.)
    """

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project(remote=True)
        created = rm.create_roadmap(self.store, plan())
        self.roadmap_id, self.phase_id = created.roadmap_id, created.phase_ids["a"]

    def entry(self):
        return self.reviewed_entry(self.store, self.phase_id)

    def crash(self, target, name, **kwargs) -> None:
        with crash_at(target, name, **kwargs):
            with self.assertRaises(Crash):
                self.entry()

    def held_then_refused(self) -> dict:
        (before,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "phase-entry"]
        held = rm.hold_roadmap(self.store, self.roadmap_id)
        self.assertEqual(held.head, self.remote_head(), "the disjoint-scope operation committed and published")
        with self.assertRaises(StopError) as raised:
            self.entry()
        self.assertEqual("roadmap_held", raised.exception.code, "the live Roadmap-state check, §5.6 step 2")
        (after,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "phase-entry"]
        self.assertEqual(before, after, "the planning mutation stays pending, untouched")
        self.assertFalse(ReviewStore(self.store).consumption_ids())
        rm.resume_roadmap(self.store, self.roadmap_id)
        return before

    def test_moment_1_after_the_review_before_the_registration(self) -> None:
        self.crash(rr, "_use_check")
        self.held_then_refused()
        result = self.entry()  # the Roadmap is active again: the declared base is the Candidate's
        self.assertEqual("registered", result.status)
        self.assertEqual([1, 2, 3], [g.generation for g in self.chain(self.store, result.review_run_id).generations])

    def test_moment_2_after_the_first_registration_stage(self) -> None:
        self.crash(rm, "register_works", when=lambda n, mutation, stage, specs, relations: stage == "integration")
        self.held_then_refused()
        result = self.entry()  # P descends from use_check_head through event-log commits only
        self.assertEqual("registered", result.status)

    def test_moment_3_after_the_kp_stage_is_recorded_before_it_is_made(self) -> None:
        self.crash(mutation_module, "_make_planning_commit",
                   when=lambda n, store, payload, paths: payload.get("base_exact") is True)
        self.held_then_refused()
        with self.assertRaises(ReconcileRequired) as raised:
            self.entry()  # HEAD is no longer the recorded parent: base_exact refuses before any replay
        self.assertEqual("review_registration_base_moved", raised.exception.reason)
        self.assertFalse(any("expand phase" in subject for subject in self.subjects(self.store)))


class R9Tests(PlanningTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()
        _, self.phase_id = self.roadmap_and_phase(self.store)

    def _entry(self, the_design):
        return self.reviewed_entry(self.store, self.phase_id, Reviewer(), the_design)

    def test_entry_a_unique_a(self) -> None:
        result = self._entry(design(entry="w1"))
        self.assertEqual(result.registration.work_ids["w1"], result.registration.entry_work_id)

    def test_entry_b_unique_a(self) -> None:
        with self.assertRaises(StopError) as raised:
            self._entry(design(entry="w2"))
        self.assertEqual("review_entry_not_canonical", raised.exception.code)
        self.assertEqual((), run_ids(self.store))

    def test_entry_a_ambiguous_a_among_the_ties(self) -> None:
        with self.assertRaises(StopError) as raised:
            self._entry(design(planned_next=(), entry="w1"))
        self.assertEqual("review_entry_ambiguous", raised.exception.code)
        self.assertEqual((), run_ids(self.store))

    def test_no_entry_unique_a(self) -> None:
        result = self._entry(design())
        self.assertEqual(result.registration.work_ids["w1"], result.registration.entry_work_id)
        material = self._material(result)
        self.assertEqual({"key": "w1", "id": result.registration.work_ids["w1"]},
                         planning.candidate_content(material)["canonical_first_work"])

    def test_no_entry_ambiguous(self) -> None:
        with self.assertRaises(StopError) as raised:
            self._entry(design(planned_next=()))
        self.assertEqual("ambiguous_startable_candidates", raised.exception.code)
        self.assertEqual([], self.pending(self.store))

    def test_no_entry_none_startable(self) -> None:
        other = rm.enter_phase(self.store, self._phase_b(), design(works={"z": "Z"}, planned_next=(), confirmation=False))
        blocker = other.work_ids["z"]
        result = self._entry(design(works={"w1": "W1"}, planned_next=(), requires_completion=((blocker, "w1"),)))
        self.assertIsNone(result.registration.entry_work_id)
        self.assertIsNone(planning.candidate_content(self._material(result))["canonical_first_work"])

    def test_entry_a_none_startable_is_the_live_refusal(self) -> None:
        other = rm.enter_phase(self.store, self._phase_b(), design(works={"z": "Z"}, planned_next=(), confirmation=False))
        with self.assertRaises(SpecViolation):
            self._entry(design(works={"w1": "W1"}, planned_next=(), requires_completion=((other.work_ids["z"], "w1"),), entry="w1"))
        self.assertEqual([], self.pending(self.store))

    def _phase_b(self) -> str:
        from workline.state import ProjectView

        view = ProjectView.load(self.store)
        return [p.id for p in view.phases.values() if p.id != self.phase_id][0]

    def _material(self, result):
        return ReviewStore(self.store).read_candidate_snapshot(self.chain(self.store, result.review_run_id).generations[0].candidate_hash).material


if __name__ == "__main__":
    unittest.main()
