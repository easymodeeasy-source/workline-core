"""P2 §28 M: the exact physical projection - E equals Kp byte for byte, and CP5 and CP6 are each required."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest
from unittest import mock

from helpers import git
from planning_helpers import (
    Crash, PlanningTestCase, Reviewer, blob_at, crash_at, design, move_branch, noncanonical_registration, plan,
    plumb_commit, registered, rr, run_ids,
)
from workline import gitcmd
from workline import mutation as mutation_module
from workline import roadmap as rm
from workline.errors import ReconcileRequired, StopError
from workline.review import planning, publication, records, serialize
from workline.review import paths as review_paths
from workline.review.store import ReviewStore

ROADMAP_YAML = ".workline/relations/roadmap.yaml"
RELATED_YAML = ".workline/relations/related.yaml"


class _ProjectionCase(PlanningTestCase):
    """A review-v1 Roadmap creation on a P whose roadmap.yaml already holds another Roadmap's relations."""

    remote = False

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project(remote=self.remote)
        self.earlier = rm.create_roadmap(self.store, plan("Earlier Roadmap"))
        self.result = self.reviewed_roadmap(self.store)
        self.reg = registered(self.store, self.result)
        self.repo = self.store.root
        self.material = self.reg.material
        self.context = self.context_of(self.result.review_run_id)
        self.expected = rr.expected_projection(self.store, self.material, self.context, self.reg.parent)

    def context_of(self, run_id: str) -> dict:
        chain = self.chain(self.store, run_id)
        task_id = chain.generations[0].accepted_tasks[0]["task_id"]
        return ReviewStore(self.store).read_task_input(task_id).request_envelope["context"]

    def roadmap_path(self) -> str:
        return rr.entity_paths(self.material)[0]

    def consumption_for(self, kp: str, **overrides) -> str:
        first = self.chain(self.store, self.result.review_run_id).generations[0]
        claims = rr.persisted_result_claims(self.material, first.operation_identity, kp, self.reg.parent, self.expected,
                                            None, self.context)
        claims["branch"] = "refs/heads/main"
        claims.update(overrides)
        consumption = replace(self.reg.consumption, persisted_result=serialize.canonical_data(claims))
        return serialize.canonical_text(consumption.to_record())

    def hand_made(self, changes: dict[str, bytes], **overrides) -> tuple[str, str]:
        """A hand-made Kp on P (the registration blobs with ``changes``) and its metadata commit."""
        blobs = {**self.reg.registration_blobs(self.store), **changes}
        kp = plumb_commit(self.store, self.reg.parent, blobs, "a hand-made registration commit")
        km = plumb_commit(self.store, kp, {self.reg.consumption_path: self.consumption_for(kp, **overrides)},
                          "a hand-made metadata commit")
        return kp, km

    def run_of(self, commit: str):
        wanted = planning.candidate_hash(self.material)
        (found,) = [r for r in publication.registered_runs(self.repo, commit) if r.candidate_hash == wanted]
        return found

    def proof(self, commit: str):
        return publication.committed_planning_proof(self.repo, commit, self.run_of(commit))

    def semantic_problem(self, kp: str) -> str | None:
        return rr.semantic_problem(self.material, rr.committed_view(self.store, self.reg.parent),
                                   rr.committed_view(self.store, kp))

    def assert_physical_only(self, kp: str, km: str) -> None:
        """CP6 (the meaning) passes, CP5 (the bytes) fails, and the barrier holds."""
        self.assertIsNotNone(rr.delta_problem(self.repo, self.expected, kp))
        self.assertIsNone(self.semantic_problem(kp), "the same meaning")
        self.assertEqual("CP5", self.proof(km)[0])
        self.assertIn("CP5 fails", publication.barrier_problem(self.repo, km))


class CanonicalTests(_ProjectionCase):
    def test_a_roadmap_registration_is_exactly_e(self) -> None:
        paths = [entry.path for entry in self.expected.entries]
        self.assertEqual(sorted(rr.registration_paths(self.material)), sorted(paths))
        self.assertIn(ROADMAP_YAML, paths, "the whole ledger")
        self.assertTrue(blob_at(self.store, self.reg.parent, ROADMAP_YAML).strip(), "P's ledger already holds records")
        for entry in self.expected.entries:
            self.assertEqual(entry.content, blob_at(self.store, self.reg.kp, entry.path), entry.path)
        self.assertIsNone(rr.delta_problem(self.repo, self.expected, self.reg.kp))
        self.assertIsNone(self.proof(self.reg.km))

    def test_a_phase_entry_registration_is_exactly_e(self) -> None:
        condition = {"kind": "path_glob", "pattern": "src/*.py"}
        the_design = design(
            works={"w1": "W1 が成立する", "w2": "W2 が成立する", "w3": "W3 が成立する"},
            planned_next=(("w1", "w2"),), requires_completion=(("w1", "w3"),),
            related={"w1": (rr.RelatedSpec("must_read", "docs/a.md"),),
                     "w2": (rr.RelatedSpec("conditional_must_read", "src/x.py", condition),)},
        )
        entry = self.reviewed_entry(self.store, self.result.registration.phase_ids["a"], Reviewer(), the_design)
        found = registered(self.store, entry)
        context = self.context_of(entry.review_run_id)
        expected = rr.expected_projection(self.store, found.material, context, found.parent)
        paths = [e.path for e in expected.entries]
        self.assertEqual(sorted(rr.registration_paths(found.material)), sorted(paths))
        self.assertIn(ROADMAP_YAML, paths)
        self.assertIn(RELATED_YAML, paths)
        self.assertEqual(3 + 2, len([p for p in paths if "/works/" in p]), "every Work, the integration and the confirmation")
        for e in expected.entries:
            self.assertEqual(e.content, blob_at(self.store, found.kp, e.path), e.path)
        self.assertIsNone(rr.delta_problem(self.repo, expected, found.kp))
        (run,) = [r for r in publication.registered_runs(self.repo, found.km) if r.candidate_hash == planning.candidate_hash(found.material)]
        self.assertIsNone(publication.committed_planning_proof(self.repo, found.km, run))


class ParserEquivalentTests(_ProjectionCase):
    """C, D, E, F, G, H: other bytes with the same meaning, or one wrong byte: CP5 fails, the barrier holds."""

    def test_c_parser_equivalent_entity_bytes(self) -> None:
        path = self.roadmap_path()
        text = blob_at(self.store, self.reg.kp, path).decode("utf-8")
        lines = text.split("\n")
        id_line, display_line = lines[1], lines[2]
        variants = {
            "reordered frontmatter keys": text.replace(id_line + "\n" + display_line, display_line + "\n" + id_line, 1),
            "a quoted scalar": text.replace(display_line, display_line.replace(": ", ': "', 1) + '"', 1),
            "no blank line after the frontmatter": text.replace("---\n\n", "---\n", 1),
            "an extra trailing blank line": text + "\n",
        }
        for described, variant in variants.items():
            with self.subTest(described):
                self.assertNotEqual(text, variant)
                self.assert_physical_only(*self.hand_made({path: variant.encode("utf-8")}))

    def test_c_the_planning_mutations_own_proof_fails_at_p3(self) -> None:
        with noncanonical_registration():
            with self.assertRaises(ReconcileRequired) as raised:
                self.reviewed_roadmap(self.store, Reviewer(), plan("Another Planned Roadmap"))
        self.assertEqual("review_persisted_proof_failed", raised.exception.reason)
        self.assertIn("C-2(Kp) P3 fails", str(raised.exception))

    def test_d_crlf(self) -> None:
        for path in (self.roadmap_path(), ROADMAP_YAML):
            with self.subTest(path):
                data = blob_at(self.store, self.reg.kp, path)
                self.assert_physical_only(*self.hand_made({path: data.replace(b"\n", b"\r\n")}))

    def test_e_ledger_layout(self) -> None:
        text = blob_at(self.store, self.reg.kp, ROADMAP_YAML).decode("utf-8")
        first_record = text.split("  - ", 2)[1]
        record_lines = first_record.rstrip("\n").split("\n")
        reordered = "\n".join([record_lines[0]] + list(reversed(record_lines[1:]))) + "\n"
        variants = {
            "record keys reordered": text.replace(first_record, reordered, 1),
            "an extra top-level key": text + "extra: kept\n",
        }
        for described, variant in variants.items():
            with self.subTest(described):
                self.assertNotEqual(text, variant)
                self.assert_physical_only(*self.hand_made({ROADMAP_YAML: variant.encode("utf-8")}))

    def test_f_a_blank_line_anywhere(self) -> None:
        phase = rr.entity_paths(self.material)[1]
        data = blob_at(self.store, self.reg.kp, phase)
        self.assert_physical_only(*self.hand_made({phase: data.replace(b"\n\n", b"\n\n\n", 1)}))

    def test_g_one_wrong_blob(self) -> None:
        phase = rr.entity_paths(self.material)[1]
        data = blob_at(self.store, self.reg.kp, phase)
        kp, km = self.hand_made({phase: data.replace("A が成立する".encode("utf-8"), "A が成立した".encode("utf-8"))})
        self.assertIsNotNone(rr.delta_problem(self.repo, self.expected, kp))
        self.assertEqual("CP5", self.proof(km)[0])

    def test_h_right_meaning_wrong_display(self) -> None:
        path = self.roadmap_path()
        text = blob_at(self.store, self.reg.kp, path).decode("utf-8")
        display_line = text.split("\n")[2]
        self.assertTrue(display_line.startswith("display: R-"))
        self.assert_physical_only(*self.hand_made({path: text.replace(display_line, "display: R-09", 1).encode("utf-8")}))


class SemanticOnlyTests(_ProjectionCase):
    def test_i_right_bytes_wrong_meaning(self) -> None:
        real = rr.RoadmapPlanAdapter.normalize_persisted

        def other_meaning(self_, loaded):
            found = real(self_, loaded)
            return rr.reviewed_artifact(found.semantics_version, {"another": "meaning"})

        with mock.patch.object(rr.RoadmapPlanAdapter, "normalize_persisted", other_meaning):
            self.assertIsNone(rr.delta_problem(self.repo, self.expected, self.reg.kp), "CP5 passes")
            self.assertEqual("CP6", self.proof(self.reg.km)[0])
            self.assertIn("CP6 fails", publication.barrier_problem(self.repo, self.reg.km))


class ForgedConsumptionTests(_ProjectionCase):
    def test_j_a_consumption_carrying_the_digest_of_the_actual_delta(self) -> None:
        path = self.roadmap_path()
        noncanonical = blob_at(self.store, self.reg.kp, path) + b"\n"
        blobs = {**self.reg.registration_blobs(self.store), path: noncanonical}
        kp = plumb_commit(self.store, self.reg.parent, blobs, "a hand-made registration commit")
        actual = gitcmd.commit_delta(self.repo, self.reg.parent, kp)
        actual_record = planning.delta_record(self.reg.parent, kp, [
            {"path": e.path, "status": e.status, "old_mode": e.old_mode, "new_mode": e.new_mode,
             "old_blob": e.old_blob, "new_blob": e.new_blob} for e in actual
        ])
        forged_digest = serialize.digest(actual_record)
        self.assertNotEqual(self.expected.delta_digest(kp), forged_digest, "CP9 compares with E's digest")
        km = plumb_commit(self.store, kp, {self.reg.consumption_path: self.consumption_for(kp, registration_delta_digest=forged_digest)})
        self.assertEqual("CP5", self.proof(km)[0])
        with mock.patch.object(rr, "delta_problem", lambda repo, expected, commit: None):
            self.assertEqual("CP9", self.proof(km)[0], "legitimizes nothing even past CP5")


class ForeignKpTests(PlanningTestCase):
    def test_k_a_foreign_kp_with_es_bytes_clears_for_its_history_and_is_never_adopted(self) -> None:
        store = self.planning_project()
        with crash_at(mutation_module, "_make_planning_commit", when=lambda n, s, payload, paths: payload.get("base_exact") is True):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        (record,) = [r for r in self.pending(store) if r["invocation"].get("operation") == "roadmap-create"]
        kp_effect = [e for e in record["effects"] if e["stage"] == rr.STAGE_KP][0]
        git(store.root, "add", "--", *kp_effect["payload"]["paths"])
        git(store.root, "commit", "-q", "-m", "a person's registration commit")
        foreign = self.head(store)
        with self.assertRaises(ReconcileRequired) as raised:
            self.reviewed_roadmap(store)
        self.assertEqual("review_commit_unowned", raised.exception.reason)
        (run_id,) = run_ids(store)
        chain = self.chain(store, run_id)
        first = chain.generations[0]
        material = ReviewStore(store).read_candidate_snapshot(first.candidate_hash).material
        context = ReviewStore(store).read_task_input(first.accepted_tasks[0]["task_id"]).request_envelope["context"]
        parent = kp_effect["payload"]["base_head"]
        expected = rr.expected_projection(store, material, context, parent)
        self.assertIsNone(rr.delta_problem(store.root, expected, foreign), "E's bytes exactly")
        claims = rr.persisted_result_claims(material, first.operation_identity, foreign, parent, expected, None, context)
        claims["branch"] = "refs/heads/main"
        consumption = records.PlanningConsumption(
            consumption_id="rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV", receipt_id=chain.latest.receipt_id, review_run_id=run_id,
            review_generation=3, review_kind=first.review_kind, authorized_candidate_hash=first.candidate_hash,
            operation_identity=first.operation_identity, operation_mutation_id=record["mutation_id"],
            target_identity=first.target_identity, persisted_result=serialize.canonical_data(claims),
        )
        km = plumb_commit(store, foreign, {review_paths.consumption_rel(consumption.consumption_id):
                                           serialize.canonical_text(consumption.to_record())})
        self.assertIsNone(publication.barrier_problem(store.root, km), "rule B: publishable history, not an adopted commit")

    def test_l_a_foreign_kp_with_the_same_meaning_in_other_bytes_holds(self) -> None:
        store = self.planning_project()
        with crash_at(mutation_module, "_make_planning_commit", when=lambda n, s, payload, paths: payload.get("base_exact") is True):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        (record,) = [r for r in self.pending(store) if r["invocation"].get("operation") == "roadmap-create"]
        kp_effect = [e for e in record["effects"] if e["stage"] == rr.STAGE_KP][0]
        roadmap = [p for p in kp_effect["payload"]["paths"] if "/roadmaps/" in p][0]
        (store.root / roadmap).write_bytes((store.root / roadmap).read_bytes() + b"\n")
        git(store.root, "add", "--", *kp_effect["payload"]["paths"])
        git(store.root, "commit", "-q", "-m", "a person's registration commit, re-formatted")
        self.assertIsNotNone(publication.barrier_problem(store.root, self.head(store)))


class RuntimeLossAfterKmTests(_ProjectionCase):
    remote = True

    def test_m_an_unrelated_push_recomputes_e_from_committed_objects_only(self) -> None:
        with crash_at(gitcmd, "push"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store, Reviewer(), plan("Second Planned Roadmap"))
        second = registered_pending_km(self)
        self.runtime_gone(self.store)
        calls: list[str] = []
        real = rr.expected_projection

        def spy(store, material, context, parent):
            calls.append(parent)
            return real(store, material, context, parent)

        with mock.patch.object(rr, "expected_projection", spy):
            held = rm.hold_roadmap(self.store, self.earlier.roadmap_id)
        self.assertEqual(held.head, self.remote_head())
        self.assertIn(second["parent"], calls, "E on the second registration's P, from committed objects")

    def test_m_a_physical_mismatch_still_holds_after_runtime_loss_and_in_a_fresh_clone(self) -> None:
        kp, km = self.hand_made({self.roadmap_path(): blob_at(self.store, self.reg.kp, self.roadmap_path()) + b"\n"})
        git(self.store.root, "branch", "canonical", self.reg.km)  # keeps the canonical history reachable in the clone
        self.runtime_gone(self.store)
        self.assertIn("CP5 fails", publication.barrier_problem(self.repo, km))
        move_branch(self.store, km)
        with self.assertRaises(StopError) as raised:
            rm.hold_roadmap(self.store, self.earlier.roadmap_id)
        self.assertEqual("review_publication_barrier", raised.exception.code)
        clone = self.fresh_clone(self.store.root, "clone")
        self.assertIn("CP5 fails", publication.barrier_problem(clone.root, km))
        self.assertIsNone(publication.barrier_problem(clone.root, self.reg.km), "the canonical Kp passes there too")


def registered_pending_km(case: _ProjectionCase) -> dict:
    (record,) = [r for r in case.pending(case.store) if r["invocation"].get("operation") == "roadmap-create"]
    kp = [e for e in record["effects"] if e["stage"] == rr.STAGE_KP][0]
    return {"parent": kp["payload"]["base_head"], "kp": kp["commit_id"]}


class UpgradeTests(_ProjectionCase):
    def test_n1_another_loader_identity_reproducing_e_passes(self) -> None:
        with mock.patch.object(planning, "loader_identity", lambda directory: "f" * 64):
            self.assertIsNone(publication.barrier_problem(self.repo, self.reg.km))

    def test_n2_a_changed_renderer_display_allocation_or_planned_write_holds(self) -> None:
        real_effect = rm.roadmap_file_effect
        real_planned = rr.planned_write

        def one_more_byte(*args, **kwargs):
            effect = real_effect(*args, **kwargs)
            return replace(effect, payload={**effect.payload, "content": effect.payload["content"] + "\n"})

        def other_display(roadmap_id, display, name, sections):
            return real_effect(roadmap_id, "R-99", name, sections)

        def planned(store, record):
            found = real_planned(store, record)
            return None if found is None else (found[0], found[1] + ("\n" if record["kind"] == "add_relation" else ""))

        for described, patch in (
            ("renderer", mock.patch.object(rm, "roadmap_file_effect", one_more_byte)),
            ("display allocation", mock.patch.object(rm, "roadmap_file_effect", other_display)),
            ("planned write", mock.patch.object(rr, "planned_write", planned)),
        ):
            with self.subTest(described), patch:
                self.assertIn("CP5 fails", publication.barrier_problem(self.repo, self.reg.km))

    def test_n3_an_adapter_or_semantics_version_not_provided_holds(self) -> None:
        kind = planning.KINDS[planning.KIND_ROADMAP]
        for changed in (replace(kind, adapter_identity="roadmap-plan-adapter-v9"),
                        replace(kind, projection_semantics_version="roadmap-plan-projection-v9")):
            with self.subTest(changed), mock.patch.dict(planning.KINDS, {planning.KIND_ROADMAP: changed}):
                with self.assertRaises(rr.ExpectedUnavailable):
                    rr.expected_projection(self.store, self.material, self.context, self.reg.parent)
                self.assertIsNotNone(publication.barrier_problem(self.repo, self.reg.km))


class BaseSensitivityTests(_ProjectionCase):
    def test_o_each_base_gets_its_own_whole_ledger_bytes_and_display_numbers(self) -> None:
        ledger = blob_at(self.store, self.reg.parent, ROADMAP_YAML).decode("utf-8")
        first_record = ledger.split("  - ", 2)[1]
        lines = first_record.rstrip("\n").split("\n")
        reformatted = ledger.replace(first_record, "\n".join([lines[0]] + list(reversed(lines[1:]))) + "\n", 1)
        earlier = self.earlier.roadmap_id
        extra_roadmap = blob_at(self.store, self.reg.parent, f".workline/roadmaps/{earlier}.md").decode("utf-8") \
            .replace(earlier, "r_01ARZ3NDEKTSV4RRFFQ69G5FAV").replace("display: R-01", "display: R-07")
        other_parent = plumb_commit(self.store, self.reg.parent, {
            ROADMAP_YAML: reformatted, ".workline/roadmaps/r_01ARZ3NDEKTSV4RRFFQ69G5FAV.md": extra_roadmap,
        }, "another legitimate base")
        other = rr.expected_projection(self.store, self.material, self.context, other_parent)
        mine = {e.path: e for e in self.expected.entries}
        theirs = {e.path: e for e in other.entries}
        self.assertEqual(set(mine), set(theirs))
        self.assertNotEqual(mine[ROADMAP_YAML].old_blob, theirs[ROADMAP_YAML].old_blob)
        self.assertEqual(mine[ROADMAP_YAML].content, theirs[ROADMAP_YAML].content, "the writer re-renders the ledger")
        self.assertNotEqual(mine[self.roadmap_path()].content, theirs[self.roadmap_path()].content, "another display number")
        self.assertIsNone(rr.delta_problem(self.repo, self.expected, self.reg.kp))
        kp_there = plumb_commit(self.store, other_parent, self.reg.registration_blobs(self.store))
        self.assertIsNotNone(rr.delta_problem(self.repo, other, kp_there), "Kp's bytes fail against the other P's projection")


class DisplayBaseTests(PlanningTestCase):
    """Display numbers are allocated by counting entity files: the entries must be HEAD's plus the operation's own."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()
        self.earlier = rm.create_roadmap(self.store, plan("Earlier Roadmap"))
        self.loose = ".workline/roadmaps/r_01ARZ3NDEKTSV4RRFFQ69G5FAW.md"
        (self.store.root / self.loose).write_text(self.roadmap_text("r_01ARZ3NDEKTSV4RRFFQ69G5FAW", "R-05"),
                                                  encoding="utf-8", newline="\n")
        self.commit_all(self.store, "a person adds a Roadmap file", self.loose)

    def roadmap_text(self, roadmap_id: str, display: str) -> str:
        source = (self.store.root / ".workline" / "roadmaps" / f"{self.earlier.roadmap_id}.md").read_text(encoding="utf-8")
        return source.replace(self.earlier.roadmap_id, roadmap_id).replace("display: R-01", f"display: {display}")

    def untracked_roadmap(self) -> Path:
        extra = self.store.root / ".workline" / "roadmaps" / "r_01ARZ3NDEKTSV4RRFFQ69G5FAX.md"
        extra.write_text(self.roadmap_text("r_01ARZ3NDEKTSV4RRFFQ69G5FAX", "R-08"), encoding="utf-8", newline="\n")
        return extra

    def assert_refused_with_nothing_recorded(self, stage: str | None = None) -> None:
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(self.store)
        self.assertEqual("dirty_overlap", raised.exception.code)
        (record,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-create"]
        if stage is None:
            self.assertEqual([], record["effects"], "nothing recorded")
        else:
            self.assertFalse([e for e in record["effects"] if e["stage"] == stage], "the next stage is not recorded")

    def assert_registered_as_e(self) -> None:
        result = self.reviewed_roadmap(self.store)
        found = registered(self.store, result)
        (run_id,) = run_ids(self.store)
        context = ReviewStore(self.store).read_task_input(
            self.chain(self.store, run_id).generations[0].accepted_tasks[0]["task_id"]).request_envelope["context"]
        expected = rr.expected_projection(self.store, found.material, context, found.parent)
        self.assertIsNone(rr.delta_problem(self.store.root, expected, found.kp), "Kp equals E")

    def test_an_untracked_entity_file_at_the_use_check(self) -> None:
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store)
        extra = self.untracked_roadmap()
        self.assert_refused_with_nothing_recorded()
        extra.unlink()
        self.assert_registered_as_e()

    def test_a_deleted_entity_file_at_the_use_check(self) -> None:
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store)
        loose = self.store.root / self.loose
        kept = loose.read_bytes()
        loose.unlink()
        self.assert_refused_with_nothing_recorded()
        loose.write_bytes(kept)
        self.assert_registered_as_e()

    def test_an_untracked_entity_file_before_a_later_registration_stage(self) -> None:
        with crash_at(rm, "register_phases"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store)
        extra = self.untracked_roadmap()
        self.assert_refused_with_nothing_recorded("phases")
        extra.unlink()
        self.assert_registered_as_e()

    def test_a_persons_commit_adding_an_entity_file_after_the_registration_began(self) -> None:
        with crash_at(rm, "register_phases"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store)
        source = (self.store.root / ".workline" / "roadmaps" / f"{self.earlier.roadmap_id}.md").read_text(encoding="utf-8")
        added = ".workline/roadmaps/r_01ARZ3NDEKTSV4RRFFQ69G5FAV.md"
        (self.store.root / added).write_text(
            source.replace(self.earlier.roadmap_id, "r_01ARZ3NDEKTSV4RRFFQ69G5FAV").replace("display: R-01", "display: R-09"),
            encoding="utf-8", newline="\n")
        self.commit_all(self.store, "a person adds a Roadmap file", added)
        with self.assertRaises(ReconcileRequired) as raised:
            self.reviewed_roadmap(self.store)
        self.assertEqual("review_registration_projection_mismatch", raised.exception.reason)
        (record,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-create"]
        self.assertFalse([e for e in record["effects"] if e["stage"] == rr.STAGE_KP], "no Kp")


class OneMechanismTests(PlanningTestCase):
    def _one_more_byte(self):
        real = rr.project_on

        def patched(store, material, base):
            found = real(store, material, base)
            entries = tuple(replace(e, content=e.content + b"\n", new_blob="0" * len(e.new_blob)) if "/roadmaps/" in e.path else e
                            for e in found.expected.entries)
            return replace(found, expected=replace(found.expected, entries=entries))

        return mock.patch.object(rr, "project_on", patched)

    def test_pre_kp_item_6_p3_p4_and_cp5_change_together(self) -> None:
        store = self.planning_project()
        with crash_at(rr, "_pre_kp_proof"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        with self._one_more_byte():
            with self.assertRaises(ReconcileRequired) as pre_kp:
                self.reviewed_roadmap(store)
        self.assertEqual("review_registration_projection_mismatch", pre_kp.exception.reason)
        with crash_at(rr, "_c2_kp"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        with self._one_more_byte():
            with self.assertRaises(ReconcileRequired) as c2:
                self.reviewed_roadmap(store)
        self.assertEqual("review_persisted_proof_failed", c2.exception.reason)
        self.assertIn("P3", str(c2.exception))
        result = self.reviewed_roadmap(store)
        found = registered(store, result)
        with self._one_more_byte():
            self.assertIn("CP5 fails", publication.barrier_problem(store.root, found.km))

    def test_no_module_under_review_renders_an_entity_or_a_ledger(self) -> None:
        review_dir = Path(rr.__file__).parent / "review"
        for path in sorted(review_dir.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for writer in ("render_relations(", "render_entity(", "dump_frontmatter(", "render_body(", "Effect.write_file(",
                           "roadmap_file_effect(", "planned_write("):
                self.assertNotIn(writer, text, f"{path.name} calls {writer}")


if __name__ == "__main__":
    unittest.main()
