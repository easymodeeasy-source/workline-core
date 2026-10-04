"""A registration owner refuses a change from before it that overlaps what it writes, before its first effect (RB10 N2).

Every state-changing operation notes, once, which paths were already changed when it began
(``gitops.record_preexisting_dirty``), and its Git stage refuses a commit that overlaps them (``dirty_overlap``).
Lifecycle decisions, plan exclusions and START already made that refusal before their first effect (BL-041). The
legacy registration owners did not: Roadmap creation, Phase addition, Phase entry, direct CREATE and Related
maintenance recorded and applied their effects first - the Roadmap file and its Phases, the Phase files, every Work
of a Phase entry's stages, the Work and its Related, the Related edges - and met the overlap only at their Git
stage, with a pending mutation no retry could finish while the person's change stayed.

Each of them now proves, on that very snapshot, against the exact paths it writes - the entity files under the IDs
it has reserved, ``roadmap.yaml`` / ``related.yaml`` only when it writes them, every stage of a Phase entry up front
- that nothing overlaps, before the first effect is recorded (``gitops.ensure_separable_before_effects``). A
person's change there is refused as ``dirty_overlap`` with nothing written, committed or pushed and the person's
bytes left exactly as they were; a change anywhere else is left alone; once the person commits or discards theirs,
the same request goes through. The snapshot is still taken once and read again on resume, never retaken.
"""

from __future__ import annotations

from contextlib import contextmanager
import unittest
from unittest import mock

from helpers import WorklineTestCase, git
from workline import create as cr
from workline import gitops
from workline import mutation as mu
from workline import roadmap as rm
from workline.create import RelatedSpec, WorkSpec
from workline.errors import StopError
from workline.ids import new_id
from workline.mutation import Mutation, MutationController
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.state import ProjectView
from workline.store import (
    PHASE_DESIRED_HEADING,
    ROADMAP_BACKGROUND_HEADING,
    ROADMAP_DESIRED_HEADING,
    WORK_DESIRED_HEADING,
    WORKLINE_DIR,
    ProjectStore,
    render_body,
    render_entity,
)

ROADMAP_YAML = f"{WORKLINE_DIR}/relations/roadmap.yaml"
RELATED_YAML = f"{WORKLINE_DIR}/relations/related.yaml"
EVENT_LOG = f"{WORKLINE_DIR}/events/events.jsonl"
OVERLAP = gitops.OVERLAP_MESSAGE
PERSON = "# a person's change, not committed yet\n"


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


@contextmanager
def reserving(kind: str, *wanted: str | None):
    """The n-th ID of ``kind`` a mutation reserves is ``wanted[n]`` (``None``: a fresh one), so a test can dirty its path first."""
    real = mu.new_id
    queue = list(wanted)

    def fake(asked: str) -> str:
        if asked == kind and queue:
            chosen = queue.pop(0)
            if chosen is not None:
                return chosen
        return real(asked)

    with mock.patch.object(mu, "new_id", fake):
        yield


def domain_state(store: ProjectStore) -> dict[str, bytes]:
    """Every canonical file under .workline (the runtime area aside), byte for byte."""
    return {
        path.relative_to(store.root).as_posix(): path.read_bytes()
        for path in sorted((store.root / WORKLINE_DIR).rglob("*"))
        if path.is_file() and "/runtime/" not in path.relative_to(store.root).as_posix() + "/"
    }


class OverlapCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.root = self.store.root

    def base(self, relations: bool = False) -> None:
        """Roadmap R with Phases A and B (A entered: W1 + I1); a standalone Work S; all committed and pushed."""
        roadmap = self.simple_roadmap(
            self.store, {"a": ("Phase A", "A done"), "b": ("Phase B", "B done")},
            [("planned_next", "a", "b")] if relations else (),
        )
        self.rid, self.pa, self.pb = roadmap.roadmap_id, roadmap.phase_ids["a"], roadmap.phase_ids["b"]
        entry = self.simple_entry(self.store, self.pa)
        self.w1, self.i1 = entry.work_ids["w1"], entry.integration_id

    def remote_head(self) -> str:
        """The approved destination's ``main`` - empty while nothing was pushed yet."""
        return git(self.remote_path(), "rev-parse", "--verify", "-q", "refs/heads/main", check=False).strip()

    def dirty(self, relative: str, change: str = PERSON) -> bytes:
        """The person's change at ``relative``: appended to a tracked file, or a new untracked one."""
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (path.read_bytes() if path.exists() else b"") + change.encode("utf-8")
        path.write_bytes(data)
        return data

    def person_entity(self, kind: str, entity_id: str, roadmap_id: str | None = None) -> str:
        """A person's own draft of an entity, untracked, at the path the operation is about to reserve.

        It reads as a valid entity - the canonical reader reads every entity file, and a file it could not read
        would stop the operation's structure precheck long before any registration - so only the overlap stops it.
        """
        meta: dict = {"id": entity_id, "display": "X-99", "type": kind}
        if kind == "work":
            meta["origin"] = {"type": "standalone"}
            body = render_body("A person's draft", [(WORK_DESIRED_HEADING, "draft")])
        elif kind == "phase":
            meta["roadmap_id"] = roadmap_id
            body = render_body("A person's draft", [(PHASE_DESIRED_HEADING, "draft")])
        else:
            body = render_body("A person's draft", [(ROADMAP_BACKGROUND_HEADING, "b"), (ROADMAP_DESIRED_HEADING, "d")])
        relative = ProjectStore.entity_rel_path(kind, entity_id)
        (self.root / relative).write_text(render_entity(meta, body), encoding="utf-8", newline="\n")
        return relative

    def discard(self, relative: str) -> None:
        tracked = git(self.root, "ls-files", "--", relative).strip()
        if tracked:
            git(self.root, "checkout", "--", relative)
        else:
            (self.root / relative).unlink()

    def assertRefusedBeforeTheFirstEffect(self, call, dirty: str) -> None:
        """``dirty_overlap`` naming ``dirty``, with no domain write, no commit, no push and the person's bytes intact."""
        held = (self.root / dirty).read_bytes()
        before = {k: v for k, v in domain_state(self.store).items() if k != dirty}
        head, remote = git(self.root, "rev-parse", "HEAD"), self.remote_head()
        with self.assertRaises(StopError) as refused:
            call()
        self.assertEqual(refused.exception.code, "dirty_overlap", refused.exception.message)
        self.assertTrue(refused.exception.message.startswith(OVERLAP), refused.exception.message)
        self.assertIn(dirty, refused.exception.message)
        self.assertEqual((self.root / dirty).read_bytes(), held, "the person's bytes are untouched")
        self.assertEqual({k: v for k, v in domain_state(self.store).items() if k != dirty}, before, "no domain write")
        self.assertEqual((git(self.root, "rev-parse", "HEAD"), self.remote_head()), (head, remote), "no commit, no push")
        self.assertEqual(MutationController(self.store).list_pending(), [], "the mutation is abandoned")
        for record in MutationController(self.store).list_records():
            self.assertEqual(record["effects"], [], "no effect was recorded")

    def assertFinishedLeaving(self, unrelated: str, data: bytes) -> None:
        """The operation committed and pushed; the unrelated change is still there, uncommitted."""
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(git(self.root, "rev-parse", "HEAD").strip(), self.remote_head(), "committed and pushed")
        self.assertEqual((self.root / unrelated).read_bytes(), data)
        self.assertIn(unrelated, git(self.root, "status", "--porcelain", "--untracked-files=all"))


# --------------------------------------------------------------------------- Roadmap creation

class RoadmapCreationTests(OverlapCase):
    PLAN = rm.RoadmapPlan("New", "BG", "DS", {"x": PhaseSpec("PX", "X"), "y": PhaseSpec("PY", "Y")},
                          (PhaseRelationSpec("planned_next", "x", "y"),))

    def test_a_changed_roadmap_yaml_is_refused_and_a_retry_after_discarding_it_succeeds(self) -> None:
        self.base(relations=True)
        self.dirty(ROADMAP_YAML)
        self.assertRefusedBeforeTheFirstEffect(lambda: rm.create_roadmap(self.store, self.PLAN), ROADMAP_YAML)
        self.discard(ROADMAP_YAML)
        created = rm.create_roadmap(self.store, self.PLAN)
        self.assertIn(created.roadmap_id, ProjectView.load(self.store).roadmaps)

    def test_its_own_entity_paths_are_known_before_its_first_effect(self) -> None:
        """The Roadmap file and the second Phase's file, under the IDs reserved for them, before anything is recorded."""
        for kind, label in (("roadmap", "the Roadmap file"), ("phase", "a Phase file")):
            with self.subTest(label):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    case.base()
                    reserved = new_id(kind)
                    path = case.person_entity(kind, reserved, case.rid)
                    wanted = (None, reserved) if kind == "phase" else (reserved,)
                    with reserving(kind, *wanted):
                        case.assertRefusedBeforeTheFirstEffect(lambda: rm.create_roadmap(case.store, case.PLAN), path)
                    case.discard(path)
                    with reserving(kind, *wanted):
                        rm.create_roadmap(case.store, case.PLAN)
                    case.assertIn(path, git(case.root, "ls-files", "--", path))
                finally:
                    case.doCleanups()

    def test_a_ledger_it_does_not_write_is_left_alone(self) -> None:
        """No Phase relation decided: ``roadmap.yaml`` is not written, so a change there does not stop it."""
        self.base()
        data = self.dirty(ROADMAP_YAML)
        rm.create_roadmap(self.store, rm.RoadmapPlan("Solo", "BG", "DS", {"x": PhaseSpec("PX", "X")}))
        self.assertFinishedLeaving(ROADMAP_YAML, data)

    def test_committing_the_change_first_also_clears_the_way(self) -> None:
        self.base(relations=True)
        self.dirty(ROADMAP_YAML)
        self.assertRefusedBeforeTheFirstEffect(lambda: rm.create_roadmap(self.store, self.PLAN), ROADMAP_YAML)
        git(self.root, "add", "--", ROADMAP_YAML)
        git(self.root, "commit", "-q", "-m", "docs: the person's note", "--", ROADMAP_YAML)
        created = rm.create_roadmap(self.store, self.PLAN)
        self.assertFalse(created.resumed)
        self.assertEqual(MutationController(self.store).list_pending(), [])


# --------------------------------------------------------------------------- Phase addition

class PhaseAdditionTests(OverlapCase):
    def test_a_changed_roadmap_yaml_with_decided_relations_is_refused(self) -> None:
        self.base()
        self.dirty(ROADMAP_YAML)
        call = lambda: rm.add_phases(self.store, self.rid, {"n": PhaseSpec("PN", "N")},  # noqa: E731
                                     (PhaseRelationSpec("planned_next", self.pb, "n"),))
        self.assertRefusedBeforeTheFirstEffect(call, ROADMAP_YAML)
        self.discard(ROADMAP_YAML)
        self.assertEqual(set(call().phase_ids), {"n"})

    def test_the_new_phase_file_is_checked_and_an_unwritten_ledger_is_left_alone(self) -> None:
        self.base()
        reserved = new_id("phase")
        path = self.person_entity("phase", reserved, self.rid)
        with reserving("phase", reserved):
            self.assertRefusedBeforeTheFirstEffect(lambda: rm.add_phases(self.store, self.rid, {"n": PhaseSpec("PN", "N")}), path)
        self.discard(path)
        data = self.dirty(ROADMAP_YAML)
        rm.add_phases(self.store, self.rid, {"n": PhaseSpec("PN", "N")})
        self.assertFinishedLeaving(ROADMAP_YAML, data)


# --------------------------------------------------------------------------- Phase entry: every stage up front

class PhaseEntryTests(OverlapCase):
    def design(self, *, confirmation_related: bool = False) -> rm.PhaseEntryDesign:
        return rm.PhaseEntryDesign(
            {"w": rm.WorkDesign("W", "W done")},
            rm.WorkDesign("Int", "integrated"),
            rm.WorkDesign("Conf", "confirmed", (RelatedSpec("must_read", "docs/x.md"),) if confirmation_related else ()),
        )

    def test_a_later_stage_path_is_refused_before_the_first_stage_writes(self) -> None:
        """The integration's own file - written by the second stage, under an ID reserved for it up front."""
        self.base()
        integration = new_id("work")
        path = self.person_entity("work", integration)
        with reserving("work", None, integration):
            self.assertRefusedBeforeTheFirstEffect(lambda: rm.enter_phase(self.store, self.pb, self.design()), path)
        self.assertEqual(ProjectView.load(self.store).phase_works(self.pb), [], "no stage was applied")
        self.discard(path)
        with reserving("work", None, integration):
            result = rm.enter_phase(self.store, self.pb, self.design())
        self.assertEqual(result.integration_id, integration)

    def test_related_yaml_written_only_by_the_last_stage_is_refused_up_front(self) -> None:
        self.base()
        self.dirty(RELATED_YAML)
        self.assertRefusedBeforeTheFirstEffect(
            lambda: rm.enter_phase(self.store, self.pb, self.design(confirmation_related=True)), RELATED_YAML
        )
        self.discard(RELATED_YAML)
        rm.enter_phase(self.store, self.pb, self.design(confirmation_related=True))

    def test_roadmap_yaml_is_always_written_and_always_checked(self) -> None:
        self.base()
        self.dirty(ROADMAP_YAML)
        self.assertRefusedBeforeTheFirstEffect(lambda: rm.enter_phase(self.store, self.pb, self.design()), ROADMAP_YAML)

    def test_a_change_to_a_file_it_does_not_write_is_left_alone(self) -> None:
        """A blank line appended to the event log - a change the log reader still reads - and nothing written there."""
        self.base()
        data = self.dirty(EVENT_LOG, "\n")
        rm.enter_phase(self.store, self.pb, self.design())
        self.assertFinishedLeaving(EVENT_LOG, data)

    def test_before_rb10_the_first_stages_were_applied_and_the_git_stage_stopped(self) -> None:
        """The defect, kept as a record: without the check up front the expansion applied every stage first."""
        self.base()
        self.dirty(RELATED_YAML)
        with mock.patch.object(gitops, "ensure_separable_before_effects", lambda mutation, paths: None):
            with self.assertRaises(StopError) as stopped:
                rm.enter_phase(self.store, self.pb, self.design(confirmation_related=True))
        self.assertEqual(stopped.exception.code, "dirty_overlap")
        (pending,) = MutationController(self.store).list_pending()
        self.assertTrue(pending["effects"], "a stranded mutation with its stages applied")


# --------------------------------------------------------------------------- direct CREATE

class DirectCreateTests(OverlapCase):
    def test_the_work_file_and_its_derivation_detail_are_checked(self) -> None:
        for kind in ("work", "derivation"):
            with self.subTest(kind):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    reserved = new_id(kind)
                    if kind == "work":
                        path = case.person_entity("work", reserved)
                    else:
                        path = f"{WORKLINE_DIR}/derivations/{reserved}.md"
                        case.dirty(path)
                    spec = WorkSpec("Solo", "solo done", derivation_detail="why")
                    with reserving(kind, reserved):
                        case.assertRefusedBeforeTheFirstEffect(lambda: cr.create_standalone_work(case.store, spec), path)
                    case.discard(path)
                    with reserving(kind, reserved):
                        cr.create_standalone_work(case.store, spec)
                    case.assertIn(path, git(case.root, "ls-files", "--", path))
                finally:
                    case.doCleanups()

    def test_related_yaml_only_when_the_work_has_related(self) -> None:
        self.base()
        data = self.dirty(RELATED_YAML)
        cr.create_standalone_work(self.store, WorkSpec("Plain", "plain done"))
        self.assertFinishedLeaving(RELATED_YAML, data)
        spec = WorkSpec("Linked", "linked done", related=(RelatedSpec("must_read", "docs/x.md"),))
        self.assertRefusedBeforeTheFirstEffect(lambda: cr.create_standalone_work(self.store, spec), RELATED_YAML)
        self.discard(RELATED_YAML)
        cr.create_standalone_work(self.store, spec)

    def test_roadmap_yaml_is_not_its_path(self) -> None:
        """A standalone CREATE writes no Roadmap relation, so ``roadmap.yaml`` is never added to what it checks."""
        self.base()
        data = self.dirty(ROADMAP_YAML)
        cr.create_standalone_work(self.store, WorkSpec("Alone", "alone done"))
        self.assertFinishedLeaving(ROADMAP_YAML, data)


# --------------------------------------------------------------------------- Related maintenance

class RelatedMaintenanceTests(OverlapCase):
    def test_related_yaml_is_its_path_and_the_work_body_is_not(self) -> None:
        self.base()
        self.dirty(RELATED_YAML)
        call = lambda: rm.maintain_work_related(self.store, self.w1, add=(RelatedSpec("must_read", "docs/x.md"),))  # noqa: E731
        self.assertRefusedBeforeTheFirstEffect(call, RELATED_YAML)
        self.discard(RELATED_YAML)
        body = ProjectStore.entity_rel_path("work", self.w1)
        data = self.dirty(body)
        self.assertTrue(call().changed)
        self.assertFinishedLeaving(body, data)


# --------------------------------------------------------------------------- one snapshot, read again on resume

class SnapshotTests(OverlapCase):
    def test_the_snapshot_is_taken_once_and_never_adopts_the_operation_s_own_writes(self) -> None:
        """Interrupted after its first stage wrote the Roadmap file: the resume reads the same note and finishes."""
        self.base()
        data = self.dirty("notes.txt")
        real = Mutation.apply

        def interrupt_after_the_roadmap(mutation):
            outcome = real(mutation)
            if mutation.has_stage("roadmap") and not mutation.has_stage("phases"):
                raise Interrupted()
            return outcome

        plan = rm.RoadmapPlan("Resumed", "BG", "DS", {"x": PhaseSpec("PX", "X")})
        with mock.patch.object(Mutation, "apply", interrupt_after_the_roadmap):
            with self.assertRaises(Interrupted):
                rm.create_roadmap(self.store, plan)
        (pending,) = MutationController(self.store).list_pending()
        self.assertEqual(pending["notes"]["preexisting_dirty"], ["notes.txt"])
        written = [e["payload"]["path"] for e in pending["effects"] if e["kind"] == "write_file"]
        self.assertTrue(written and all(p in git(self.root, "status", "--porcelain", "--untracked-files=all") for p in written))

        result = rm.create_roadmap(self.store, plan)

        self.assertEqual((result.resumed, result.mutation_id), (True, pending["mutation_id"]))
        self.assertFinishedLeaving("notes.txt", data)

    def test_a_resumed_mutation_refuses_on_its_durable_note(self) -> None:
        """Interrupted right after its note was saved: the retry reads that note, refuses, and abandons it."""
        self.base(relations=True)
        self.dirty(ROADMAP_YAML)
        real = Mutation.set_note

        def interrupt_after_noting(mutation, key, value):
            real(mutation, key, value)
            if key == "preexisting_dirty":
                raise Interrupted()

        plan = rm.RoadmapPlan("Noted", "BG", "DS", {"x": PhaseSpec("PX", "X"), "y": PhaseSpec("PY", "Y")},
                              (PhaseRelationSpec("planned_next", "x", "y"),))
        with mock.patch.object(Mutation, "set_note", interrupt_after_noting):
            with self.assertRaises(Interrupted):
                rm.create_roadmap(self.store, plan)
        (pending,) = MutationController(self.store).list_pending()
        self.assertEqual(pending["notes"]["preexisting_dirty"], [ROADMAP_YAML])
        self.assertRefusedBeforeTheFirstEffect(lambda: rm.create_roadmap(self.store, plan), ROADMAP_YAML)
        self.discard(ROADMAP_YAML)
        self.assertFalse(rm.create_roadmap(self.store, plan).resumed, "a new mutation, with a new note")

    def test_a_mutation_that_recorded_effects_keeps_its_git_stage_rules(self) -> None:
        """A record whose effects were recorded under the older order is not refused here; its Git stage stays as it was."""
        self.base()
        self.dirty(RELATED_YAML)
        spec = WorkSpec("Older", "older done", related=(RelatedSpec("must_read", "docs/x.md"),))
        with mock.patch.object(gitops, "ensure_separable_before_effects", lambda mutation, paths: None):
            with self.assertRaises(StopError) as stopped:
                cr.create_standalone_work(self.store, spec)
        self.assertEqual(stopped.exception.code, "dirty_overlap")
        (pending,) = MutationController(self.store).list_pending()
        record = (self.store.mutations / f"{pending['mutation_id']}.yaml").read_bytes()
        with self.assertRaises(StopError) as again:
            cr.create_standalone_work(self.store, spec)
        self.assertEqual(again.exception.code, "dirty_overlap", "stopped at its Git stage, as before")
        self.assertEqual(MutationController(self.store).list_pending()[0]["effects"], pending["effects"])
        self.assertTrue(record)


if __name__ == "__main__":
    unittest.main()
