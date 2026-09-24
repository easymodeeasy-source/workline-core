"""How a recorded ``write_file`` is classified for each line ending of the decided text (BL-056).

The Mutation Controller writes a ``write_file`` payload as given - UTF-8, no line
ending translated (``durable_write_text``) - and the Project reader reads every
file with universal newlines: CRLF and a lone CR (one no LF follows) both read as
LF (``store.as_read_back``). The classifier compares the file as the reader reads
it with the recorded content read back the same way, so the operation's own write
is applied, matching, whatever line ends its text holds.

Before BL-056 the classifier folded only CRLF in the recorded content: the own
write of a text holding a lone CR was classified applied with an unexpected
result, and the next replay of the record stopped ``reconcile required`` on every
retry of the same request. On the baseline these pins held the lone CR, mixed and
trailing lone CR shapes as ``applied_mismatch`` and a Roadmap creation with a
lone CR or mixed line ends in its desired state as stranded; those are the only
rows the change moved.

These pins state, for each line-end shape of the decided text, what the writer
puts on disk, what the reader reads, how the operation's own write is
classified, and what a Roadmap creation carrying the text in its desired state
does end to end.

The rest pins what the rule means beyond that matrix: the classification is the
reader's text meaning and nothing else (``ClassificationTests``); whose bytes a
file holds is still the own-bytes proof's to show (``OwnBytesTests``); every
writer that stranded now completes on its first invocation
(``FirstInvocationTests``); a record the baseline left stranded resumes as it
is, while a person's change to it stays refused exactly as the CRLF twin's is
(``StrandedRecordTests``); what succeeded on the baseline still succeeds
(``CompatibilityTests``); and a Review record is still compared byte for byte
(``ReviewCreateTests``).
"""

from __future__ import annotations

from contextlib import contextmanager
import io
from itertools import product
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, NamedTuple
import unittest
from unittest import mock

from helpers import WorklineTestCase, git, scripted_executor
from test_recorded_move_dependency import Interrupted, after_recording, before_recording
from test_review_authorization import RECEIPT_ID, receipt_record
from workline import create as cr
from workline import gitcmd
from workline import mutation as mu
from workline import roadmap as rm
from workline import start as st
from workline.create import WorkSpec
from workline.errors import ReconcileRequired
from workline.ids import new_id
from workline.mutation import MATCHING, MISMATCH, UNAPPLIED, Effect, MutationController, WriteScope
from workline.oplock import project_operation
from workline.phase_create import PhaseSpec
from workline.push_pin import pin_push_destination
from workline.review import paths, serialize
from workline.state import ProjectView
from workline.store import (
    PHASE_DESIRED_HEADING,
    ROADMAP_BACKGROUND_HEADING,
    ROADMAP_DESIRED_HEADING,
    ROADMAP_OUT_OF_SCOPE_HEADING,
    ROADMAP_SCOPE_HEADING,
    WORK_DESIRED_HEADING,
    WORKLINE_DIR,
    ProjectStore,
    render_body,
    render_entity,
)


class Shape(NamedTuple):
    #: the decided text
    text: str
    #: what the Project reader reads in the section that holds it
    read: str
    #: how the operation's own write of a file ending in it is classified
    own_write: str
    #: whether a Roadmap creation carrying it in its desired state completes (a section is rendered stripped)
    roadmap: bool


SHAPES = {
    "plain": Shape("abc", "abc", MATCHING, True),
    "LF": Shape("a\nb", "a\nb", MATCHING, True),
    "CRLF": Shape("a\r\nb", "a\nb", MATCHING, True),
    "lone CR": Shape("a\rb", "a\nb", MATCHING, True),
    "mixed": Shape("a\r\nb\rc\n", "a\nb\nc", MATCHING, True),
    "trailing lone CR": Shape("abc\r", "abc", MATCHING, True),
    "LF at end": Shape("abc\n", "abc", MATCHING, True),
    "CRLF at end": Shape("abc\r\n", "abc", MATCHING, True),
}

#: The shapes whose own write the baseline classified ``applied_mismatch``: the rows BL-056 moved.
BASELINE_MISMATCH = ("lone CR", "mixed", "trailing lone CR")

LONE_CR = "a\rb"
CRLF = "a\r\nb"


def blob(root: Path, spec: str) -> bytes:
    """The bytes Git stores for ``spec`` (``<rev>:<path>``), untranslated."""
    return subprocess.run(["git", "-C", str(root), "cat-file", "blob", spec], capture_output=True, check=True).stdout


def work_text(work_id: str, text: str) -> str:
    """A standalone Work whose desired-state section is ``text``, at the very end of the file."""
    return (
        f"---\nid: {work_id}\ndisplay: W-01\ntype: work\norigin:\n  type: standalone\n---\n\n"
        f"# W\n\n## {WORK_DESIRED_HEADING}\n{text}"
    )


def reader(data: bytes) -> str:
    """``data`` as the Project reader reads a file holding it: UTF-8, universal newlines (``Path.read_text``)."""
    return io.TextIOWrapper(io.BytesIO(data), encoding="utf-8").read()


def has_lone_cr(text: str) -> bool:
    return "\r" in text.replace("\r\n", "")


def lone_crs(data: bytes) -> int:
    return data.count(b"\r") - data.count(b"\r\n")


_ID = re.compile(r"\b(mut|rel|evt|der|r|p|w)_[0-9A-HJKMNP-TV-Z]{26}\b")


def without_ids(message: str) -> str:
    """``message`` with entity, mutation and commit IDs left out, so that two Projects' messages compare."""
    return re.sub(r"\b[0-9a-f]{40}\b", "<commit>", _ID.sub(lambda m: f"<{m.group(1)}>", message))


# --------------------------------------------------------------------------- the rule before BL-056

_CLASSIFY = MutationController.classify


def classified_before_bl056(controller: MutationController, record: dict[str, Any]) -> str:
    """``MutationController.classify`` as it was before BL-056: a write's recorded text folded for CRLF alone."""
    if record["kind"] != "write_file":
        return _CLASSIFY(controller, record)
    payload = record["payload"]
    path = controller.store.abs(payload["path"])
    if not path.exists():
        return UNAPPLIED
    try:
        current = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return MISMATCH
    if current == payload["content"].replace("\r\n", "\n"):
        return MATCHING
    base = payload.get("base")
    if base is not None and current == base.replace("\r\n", "\n"):
        return UNAPPLIED
    return MISMATCH


@contextmanager
def the_baseline_classifier():
    """Classify every recorded effect as the baseline did, to leave exactly the record a pre-BL-056 run left."""
    with mock.patch.object(MutationController, "classify", classified_before_bl056):
        yield


# --------------------------------------------------------------------------- the matrix

class OwnWriteTests(WorklineTestCase):
    """The operation's own write of each shape: the bytes it leaves, the reading, the classification, the replay."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.controller = MutationController(self.store)
        # driven as a top-level operation drives the Mutation Controller: while holding the Project execution lock
        lock = project_operation(self.store, "line-end-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)

    def write(self, text: str):
        """Record and apply one write of a new Work holding ``text``; its ID, path, content and mutation."""
        work_id = new_id("work")
        path = f"{WORKLINE_DIR}/works/{work_id}.md"
        content = work_text(work_id, text)
        mutation = self.controller.open("start", {"operation": "line-ends", "work_id": work_id}, WriteScope((work_id,)))
        mutation.add_effects("s1", [Effect.write_file(path, content)])
        mutation.apply()
        return work_id, path, content, mutation

    def test_the_writer_keeps_the_decided_bytes(self) -> None:
        for label, shape in SHAPES.items():
            with self.subTest(label):
                _, path, content, _ = self.write(shape.text)
                self.assertEqual(content.encode("utf-8"), self.store.abs(path).read_bytes())

    def test_the_reader_reads_every_line_end_as_lf(self) -> None:
        written = {label: self.write(shape.text)[0] for label, shape in SHAPES.items()}
        view = ProjectView.load(self.store)
        for label, shape in SHAPES.items():
            with self.subTest(label):
                self.assertEqual(shape.read, view.works[written[label]].section(WORK_DESIRED_HEADING))

    def test_how_the_own_write_is_classified(self) -> None:
        for label, shape in SHAPES.items():
            with self.subTest(label):
                _, _, _, mutation = self.write(shape.text)
                self.assertEqual(shape.own_write, self.controller.classify(mutation.effects[0]))

    def test_the_next_replay_of_the_record(self) -> None:
        """The next stage's apply classifies the write again, before anything after it."""
        for label, shape in SHAPES.items():
            with self.subTest(label):
                _, _, _, mutation = self.write(shape.text)
                if shape.own_write == MATCHING:
                    self.assertEqual([(1, MATCHING)], mutation.apply())
                    continue
                with self.assertRaises(ReconcileRequired) as raised:
                    mutation.apply()
                self.assertIn("effect 1 (write_file) applied with unexpected result", raised.exception.message)

    def test_the_rule_the_stranded_records_below_are_made_with(self) -> None:
        """``classified_before_bl056`` classifies the matrix exactly as the baseline pins held the live code."""
        for label, shape in SHAPES.items():
            with self.subTest(label):
                _, _, _, mutation = self.write(shape.text)
                expected = MISMATCH if label in BASELINE_MISMATCH else MATCHING
                self.assertEqual(expected, classified_before_bl056(self.controller, mutation.effects[0]))


class RoadmapCreationTests(WorklineTestCase):
    """A Roadmap creation carrying each shape in its desired state, uninterrupted, with a pinned remote."""

    def plan(self, text: str) -> rm.RoadmapPlan:
        return rm.RoadmapPlan("R", "BG", text, {"a": PhaseSpec("PA", "A")})

    def remote_main(self, name: str) -> str | None:
        return git(self.remote_path(name), "rev-parse", "--verify", "--quiet", "refs/heads/main", check=False).strip() or None

    def test_each_shape(self) -> None:
        for label, shape in SHAPES.items():
            with self.subTest(label):
                name = label.replace(" ", "-")
                store = self.new_project(name, remote=True)
                head = git(store.root, "rev-parse", "HEAD").strip()
                if shape.roadmap:
                    result = rm.create_roadmap(store, self.plan(shape.text))
                    roadmap_id = result.roadmap_id
                    self.assertEqual([], MutationController(store).list_pending())
                    self.assertNotEqual(head, result.head)
                    self.assertEqual(result.head, self.remote_main(name), "committed and pushed")
                else:
                    with self.assertRaises(ReconcileRequired) as raised:
                        rm.create_roadmap(store, self.plan(shape.text))
                    self.assertIn("effect 1 (write_file) applied with unexpected result", raised.exception.message)
                    (record,) = MutationController(store).list_pending()
                    roadmap_id = record["reserved_ids"]["roadmap"]
                    self.assertEqual(head, git(store.root, "rev-parse", "HEAD").strip(), "nothing committed")
                    self.assertIsNone(self.remote_main(name), "nothing pushed")
                    with self.assertRaises(ReconcileRequired):
                        rm.create_roadmap(store, self.plan(shape.text))  # the same request stops the same way
                    (again,) = MutationController(store).list_pending()
                    self.assertEqual(record["mutation_id"], again["mutation_id"])
                rendered = render_entity(
                    {"id": roadmap_id, "display": "R-01", "type": "roadmap"},
                    render_body("R", rm.roadmap_file_sections("BG", shape.text, None, None)),
                ).encode("utf-8")
                path = ProjectStore.entity_rel_path("roadmap", roadmap_id)
                self.assertEqual(rendered, store.abs(path).read_bytes(), "written as decided")
                if shape.roadmap:
                    self.assertEqual(rendered, blob(store.root, f"HEAD:{path}"), "committed as written")
                self.assertEqual(shape.read, ProjectView.load(store).roadmaps[roadmap_id].section(ROADMAP_DESIRED_HEADING))


# --------------------------------------------------------------------------- the comparison itself

#: Every text of up to four characters over ``a``, CR and LF: 121 texts.
DOMAIN = ["".join(chars) for size in range(5) for chars in product("a\r\n", repeat=size)]


class ClassificationTests(WorklineTestCase):
    """What the reader reads of the file, against what it would read of the recorded text - and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.controller = MutationController(self.store)
        self.path = f"{WORKLINE_DIR}/works/{new_id('work')}.md"
        self.file = self.store.abs(self.path)
        self.file.parent.mkdir(parents=True, exist_ok=True)

    def classify(self, held: bytes | None, content: str, base: str | None = None) -> tuple[str, str]:
        """A write of ``content`` from ``base``, with the file holding ``held``: classified now, and before BL-056."""
        if held is None:
            self.file.unlink(missing_ok=True)
        else:
            self.file.write_bytes(held)
        payload = {"path": self.path, "content": content}
        if base is not None:
            payload["base"] = base
        record = {"kind": "write_file", "payload": payload}
        return self.controller.classify(record), classified_before_bl056(self.controller, record)

    def test_examples(self) -> None:
        cases = {
            # label: (file bytes, recorded content, recorded base, now, before BL-056)
            "the own write of a lone CR": (b"a\rb", LONE_CR, None, MATCHING, MISMATCH),
            "the own write of CRLF, as before": (b"a\r\nb", CRLF, None, MATCHING, MATCHING),
            "the own write of LF, as before": (b"a\nb", "a\nb", None, MATCHING, MATCHING),
            "a CRLF write read back from a CRLF checkout, as before": (b"a\r\nb", "a\nb", None, MATCHING, MATCHING),
            "a lone CR turned into LF: the same text, whose bytes it is aside": (b"a\nb", LONE_CR, None, MATCHING, MISMATCH),
            "other text": (b"a\rc", LONE_CR, None, MISMATCH, MISMATCH),
            "one line end more": (b"a\r\rb", LONE_CR, None, MISMATCH, MISMATCH),
            "no line end": (b"ab", LONE_CR, None, MISMATCH, MISMATCH),
            "nothing written yet": (None, LONE_CR, None, UNAPPLIED, UNAPPLIED),
            "the base, still there, holding a lone CR": (b"x\ry", "new", "x\ry", UNAPPLIED, MISMATCH),
            "the base read back from other line ends": (b"x\ny", "new", "x\ry", UNAPPLIED, MISMATCH),
            "a CRLF base, as before": (b"x\r\ny", "new", "x\r\ny", UNAPPLIED, UNAPPLIED),
            "neither the base nor the write": (b"x\rz", "new", "x\ry", MISMATCH, MISMATCH),
        }
        for label, (held, content, base, now, before) in cases.items():
            with self.subTest(label):
                self.assertEqual((now, before), self.classify(held, content, base))

    def test_the_reader_decides_and_only_a_recorded_lone_cr_moved(self) -> None:
        """Every file against every recorded text of the domain.

        Matching exactly when the reader reads the same text: a file whose text
        means something else is never taken for the write, whatever its bytes.
        Against the rule before BL-056, nothing that was matching is refused, and
        a classification moved only for a recorded text holding a lone CR - a
        text of LF and CRLF alone is classified exactly as before.
        """
        for held, content in product(DOMAIN, DOMAIN):
            data = held.encode("utf-8")
            now, before = self.classify(data, content)
            same = reader(data) == reader(content.encode("utf-8"))
            self.assertEqual(MATCHING if same else MISMATCH, now, (held, content))
            if now != before:
                self.assertEqual((MATCHING, MISMATCH), (now, before), (held, content))
                self.assertTrue(has_lone_cr(content), (held, content))

    def test_the_base_is_read_back_the_same_way(self) -> None:
        """Every file against every recorded base of the domain, for a write the file does not hold."""
        for held, base in product(DOMAIN, DOMAIN):
            data = held.encode("utf-8")
            now, before = self.classify(data, "decided", base)
            same = reader(data) == reader(base.encode("utf-8"))
            self.assertEqual(UNAPPLIED if same else MISMATCH, now, (held, base))
            if now != before:
                self.assertEqual((UNAPPLIED, MISMATCH), (now, before), (held, base))
                self.assertTrue(has_lone_cr(base), (held, base))


class OwnBytesTests(WorklineTestCase):
    """What the classification does not tell apart, the own-bytes proof still refuses - for a lone CR as for CRLF."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.controller = MutationController(self.store)
        lock = project_operation(self.store, "line-end-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)

    def test_a_person_turning_the_line_ends_into_lf_is_not_committed_as_the_operation_s_own(self) -> None:
        root = self.store.root
        for label, text in (("lone CR", LONE_CR), ("CRLF", CRLF)):
            with self.subTest(label):
                work_id = new_id("work")
                path = f"{WORKLINE_DIR}/works/{work_id}.md"
                content = work_text(work_id, text)
                mutation = self.controller.open("start", {"operation": "line-ends", "work_id": work_id}, WriteScope((work_id,)))
                mutation.add_effects("s1", [Effect.write_file(path, content)])
                mutation.apply()
                self.assertEqual(mu._content_digest(self.store.abs(path)), mutation.effects[0]["wrote"], "its own bytes")
                edited = content.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
                self.store.abs(path).write_bytes(edited)
                self.assertEqual(MATCHING, self.controller.classify(mutation.effects[0]), "the same text")
                commit = Effect.git_commit("chore(workline): line ends", [path], gitcmd.head_commit(root), gitcmd.current_branch_ref(root))
                with self.assertRaises(ReconcileRequired) as raised:
                    mutation.add_effects("git", [commit])
                self.assertIn(f"no longer holds what this operation wrote there: {path}", raised.exception.message)
                self.assertFalse(mutation.has_stage("git"), "no commit recorded")
                self.assertEqual(edited, self.store.abs(path).read_bytes(), "the change is left as it is")


# --------------------------------------------------------------------------- real operations

class ProjectCase(WorklineTestCase):
    def remote_main(self, name: str = "proj") -> str | None:
        return git(self.remote_path(name), "rev-parse", "--verify", "--quiet", "refs/heads/main", check=False).strip() or None

    def pending(self, store: ProjectStore) -> list[dict[str, Any]]:
        return MutationController(store).list_pending()

    @staticmethod
    def dirty(store: ProjectStore) -> list[str]:
        """What ``git status`` shows outside the runtime area."""
        status = git(store.root, "status", "--porcelain", "--untracked-files=all").splitlines()
        return [line for line in status if f"{WORKLINE_DIR}/runtime/" not in line]

    def base_project(self, name: str = "proj"):
        """A Project with a pinned remote and Roadmap R0 of three Phases, the first entered with W1; entered."""
        store = self.new_project(name, remote=True)
        created = rm.create_roadmap(store, rm.RoadmapPlan(
            "R0", "BG0", "DS0", {"a": PhaseSpec("P0a", "A0"), "b": PhaseSpec("P0b", "B0"), "c": PhaseSpec("P0c", "C0")}
        ))
        entry = rm.enter_phase(store, created.phase_ids["a"], rm.PhaseEntryDesign(
            {"w1": rm.WorkDesign("W1", "W1 done")}, rm.WorkDesign("I0", "integrated")
        ))
        return store, created, entry.work_ids["w1"]

    def assert_finished(self, store: ProjectStore, name: str, written: list[str]) -> None:
        """Nothing pending, the working tree clean, HEAD pushed, and every file in ``written`` committed as it is."""
        self.assertEqual([], self.pending(store))
        self.assertEqual([], self.dirty(store))
        self.assertEqual(gitcmd.head_commit(store.root), self.remote_main(name), "pushed")
        for path in written:
            data = store.abs(path).read_bytes()
            self.assertGreater(lone_crs(data), 0, f"{path} keeps its lone CR")
            self.assertEqual(data, blob(store.root, f"HEAD:{path}"), f"{path} committed as written")


class FirstInvocationTests(ProjectCase):
    """Every writer that stranded on a lone CR completes on its first invocation, with a pinned remote."""

    @staticmethod
    def plan(separator: str) -> rm.RoadmapPlan:
        s = separator
        return rm.RoadmapPlan(
            f"R{s}M", f"BG{s}1", f"DS{s}2", {"a": PhaseSpec(f"P{s}A", f"A{s}3")}, scope=f"S{s}4", out_of_scope=f"O{s}5"
        )

    @staticmethod
    def reading(store: ProjectStore) -> list[list[tuple]]:
        """What the reader reads of every Roadmap and Phase, in creation order, without IDs."""
        view = ProjectView.load(store)
        headings = (ROADMAP_BACKGROUND_HEADING, ROADMAP_DESIRED_HEADING, ROADMAP_SCOPE_HEADING, ROADMAP_OUT_OF_SCOPE_HEADING)
        roadmaps = [(r.name, [r.section(h) for h in headings]) for r in view.roadmaps.values()]
        phases = [(p.name, p.section(PHASE_DESIRED_HEADING)) for p in view.phases.values()]
        return [roadmaps, phases]

    def test_roadmap_creation(self) -> None:
        twin = self.new_project("twin")
        rm.create_roadmap(twin, self.plan("\n"))
        store = self.new_project(remote=True)
        result = rm.create_roadmap(store, self.plan("\r"))
        self.assertFalse(result.resumed)
        written = [ProjectStore.entity_rel_path("roadmap", result.roadmap_id), ProjectStore.entity_rel_path("phase", result.phase_ids["a"])]
        self.assert_finished(store, "proj", written)
        self.assertEqual(self.reading(twin), self.reading(store), "read exactly as the LF twin is")
        self.assertEqual([[("R", ["BG\n1", "DS\n2", "S\n4", "O\n5"])], [("P", "A\n3")]], self.reading(store))

    def test_phase_addition(self) -> None:
        store, created, _ = self.base_project()
        result = rm.add_phases(store, created.roadmap_id, {"n": PhaseSpec("PN", LONE_CR)})
        path = ProjectStore.entity_rel_path("phase", result.phase_ids["n"])
        self.assert_finished(store, "proj", [path])
        self.assertEqual("a\nb", ProjectView.load(store).phases[result.phase_ids["n"]].section(PHASE_DESIRED_HEADING))

    def test_phase_entry(self) -> None:
        store = self.new_project(remote=True)
        created = rm.create_roadmap(store, rm.RoadmapPlan("R", "BG", "DS", {"a": PhaseSpec("PA", "A")}))
        design = rm.PhaseEntryDesign(
            {"w1": rm.WorkDesign("W1", LONE_CR)}, rm.WorkDesign("I", "i\rj"), rm.WorkDesign("C", "c\rd")
        )
        result = rm.enter_phase(store, created.phase_ids["a"], design)
        ids = {"w1": result.work_ids["w1"], "integration": result.integration_id, "confirmation": result.confirmation_id}
        self.assert_finished(store, "proj", [ProjectStore.entity_rel_path("work", w) for w in ids.values()])
        works = ProjectView.load(store).works
        self.assertEqual(
            {"w1": "a\nb", "integration": "i\nj", "confirmation": "c\nd"},
            {key: works[w].section(WORK_DESIRED_HEADING) for key, w in ids.items()},
        )

    def test_start_derivation(self) -> None:
        store, _, work_id = self.base_project()
        derived = st.DerivedWork("Fix", LONE_CR, derivation_detail="why\rnot")
        result = st.start(store, work_id, "single-work", scripted_executor({work_id: [st.Derive({"fix": derived}), st.Completed()]}))
        self.assertEqual("completed", result.status)
        (fix,) = [w for w in ProjectView.load(store).works.values() if w.name == "Fix"]
        (detail,) = sorted((store.root / WORKLINE_DIR / "derivations").glob("*.md"))
        self.assert_finished(store, "proj", [fix.path, store.rel(detail)])
        self.assertEqual("a\nb", fix.section(WORK_DESIRED_HEADING))
        self.assertEqual("# Derivation detail\n\nwhy\nnot\n", detail.read_text(encoding="utf-8"))

    def test_direct_standalone_creation(self) -> None:
        store = self.new_project(remote=True)
        result = cr.create_standalone_work(store, WorkSpec("S", LONE_CR))
        path = ProjectStore.entity_rel_path("work", result.work_id)
        self.assert_finished(store, "proj", [path])
        self.assertEqual("a\nb", ProjectView.load(store).works[result.work_id].section(WORK_DESIRED_HEADING))


class StrandedRecordTests(ProjectCase):
    """A record the baseline stranded resumes as it is; a person's change to it stays refused as for the CRLF twin.

    Each stranded record is made by the same request classified by the rule
    before BL-056 (``the_baseline_classifier``), so it is exactly the record a
    pre-BL-056 run left: its own write applied and a later stage recorded.
    """

    def strand(self, store: ProjectStore, call: Callable[[], Any]) -> dict[str, Any]:
        """Run ``call`` classified as the baseline did: it stops on its own write; the pending record it leaves."""
        with the_baseline_classifier():
            with self.assertRaises(ReconcileRequired) as raised:
                call()
        self.assertRegex(raised.exception.message, r"effect \d+ \(write_file\) applied with unexpected result")
        (record,) = self.pending(store)
        return record

    def interrupt(self, store: ProjectStore, call: Callable[[], Any], stage: str) -> dict[str, Any]:
        """Run ``call`` and stop it right after the stage matching ``stage`` is recorded; the pending record."""
        with after_recording(stage):
            with self.assertRaises(Interrupted):
                call()
        (record,) = self.pending(store)
        return record

    @staticmethod
    def own_writes(record: dict[str, Any], text: str) -> dict[str, dict[str, Any]]:
        """The applied writes of ``record`` whose text holds ``text``, by path."""
        return {
            effect["payload"]["path"]: effect
            for effect in record["effects"]
            if effect["kind"] == "write_file" and effect.get("applied") and text in effect["payload"]["content"]
        }

    def resume(self, store: ProjectStore, name: str, record: dict[str, Any], call: Callable[[], Any]):
        """Retry the stranded request: it resumes the same mutation and finishes it without writing its own write again."""
        writes = self.own_writes(record, LONE_CR)
        self.assertTrue(writes)
        before = {path: (store.abs(path).read_bytes(), os.stat(store.abs(path)).st_mtime_ns) for path in writes}
        for path, effect in writes.items():
            self.assertEqual(effect["payload"]["content"].encode("utf-8"), before[path][0], "the bytes it wrote")
            self.assertEqual(MATCHING, MutationController(store).classify(effect), "its own write, read as the reader reads it")
        applied: list[str | None] = []
        proved: set[str] = set()
        real_apply, real_proof = MutationController.apply_effect, mu._require_own_bytes_committed

        def applying(controller, effect):
            applied.append(mu.effect_path(effect))
            return real_apply(controller, effect)

        def proving(mutation, effects, position, effect):
            real_proof(mutation, effects, position, effect)
            proved.update(set(effect["payload"]["paths"]) & set(writes))

        with mock.patch.object(MutationController, "apply_effect", applying), mock.patch.object(mu, "_require_own_bytes_committed", proving):
            result = call()
        self.assertEqual(record["mutation_id"], result.mutation_id, "the same mutation resumed")
        self.assertFalse(set(writes) & set(applied), "its own write is not written again")
        self.assertEqual(set(writes), proved, "each is committed only after the own-bytes proof passed")
        for path, (data, mtime) in before.items():
            self.assertEqual((data, mtime), (store.abs(path).read_bytes(), os.stat(store.abs(path)).st_mtime_ns))
        self.assert_finished(store, name, list(writes))
        return result

    # untouched ------------------------------------------------------------------
    def test_a_stranded_roadmap_creation_resumes(self) -> None:
        store = self.new_project(remote=True)
        the_plan = rm.RoadmapPlan("R", "BG", LONE_CR, {"a": PhaseSpec("PA", "A")})
        record = self.strand(store, lambda: rm.create_roadmap(store, the_plan))
        self.assertEqual(["roadmap", "phases"], list(dict.fromkeys(e["stage"] for e in record["effects"])))
        result = self.resume(store, "proj", record, lambda: rm.create_roadmap(store, the_plan))
        self.assertTrue(result.resumed)
        self.assertEqual("a\nb", ProjectView.load(store).roadmaps[result.roadmap_id].section(ROADMAP_DESIRED_HEADING))

    def test_a_stranded_phase_entry_resumes(self) -> None:
        store = self.new_project(remote=True)
        phase_id = rm.create_roadmap(store, rm.RoadmapPlan("R", "BG", "DS", {"a": PhaseSpec("PA", "A")})).phase_ids["a"]
        design = rm.PhaseEntryDesign({"w1": rm.WorkDesign("W1", LONE_CR)}, rm.WorkDesign("I", "integrated"))
        record = self.strand(store, lambda: rm.enter_phase(store, phase_id, design))
        result = self.resume(store, "proj", record, lambda: rm.enter_phase(store, phase_id, design))
        self.assertEqual("a\nb", ProjectView.load(store).works[result.work_ids["w1"]].section(WORK_DESIRED_HEADING))

    def test_a_stranded_start_derivation_resumes(self) -> None:
        store, _, work_id = self.base_project()
        executor = scripted_executor({work_id: [st.Derive({"fix": st.DerivedWork("Fix", LONE_CR)}), st.Completed()]})
        record = self.strand(store, lambda: st.start(store, work_id, "single-work", executor))
        self.assertTrue(any(e["kind"] == "git_commit" for e in record["effects"]), "stranded with its Git stage recorded")
        result = self.resume(store, "proj", record, lambda: st.start(store, work_id, "single-work", executor))
        self.assertEqual("completed", result.status)
        self.assertEqual(["a\nb"], [w.section(WORK_DESIRED_HEADING) for w in ProjectView.load(store).works.values() if w.name == "Fix"])

    # moved on meanwhile -----------------------------------------------------
    def test_after_an_independent_commit_it_resumes_on_top_of_it(self) -> None:
        store, created, _ = self.base_project()
        the_plan = rm.RoadmapPlan("RN", "BG", "DS", {"n": PhaseSpec("PN", LONE_CR)})
        record = self.strand(store, lambda: rm.create_roadmap(store, the_plan))
        (commit,) = [e for e in record["effects"] if e["kind"] == "git_commit"]
        rm.hold_phase(store, created.phase_ids["c"])  # a disjoint-scope operation commits and pushes
        independent = gitcmd.head_commit(store.root)
        self.assertNotEqual(commit["payload"]["base_head"], independent)
        self.assertEqual(independent, self.remote_main())
        self.resume(store, "proj", record, lambda: rm.create_roadmap(store, the_plan))
        self.assertEqual(independent, git(store.root, "rev-parse", "HEAD^").strip(), "made on top of the independent commit")

    # a person's change ------------------------------------------------------
    def test_a_person_turning_the_lone_cr_into_lf_is_refused_as_for_crlf(self) -> None:
        """The record classifies as the reader reads it; the own-bytes proof refuses the edit before any commit."""
        windows = {
            "before the Git stage": (r"^phases$", lambda store, text: self._roadmap(store, text)),
            "with the Git stage recorded": (r"^commit:0$", lambda store, text: self._derivation(store, text)),
        }
        for number, (window, (stage, operation)) in enumerate(windows.items()):
            with self.subTest(window):
                outcomes = {}
                for label, text in (("lone CR", LONE_CR), ("CRLF", CRLF)):
                    name = f"{number}-{label.replace(' ', '-')}"
                    store, call = operation(self.base_project(name)[0], text)
                    record = self.strand(store, call) if text == LONE_CR else self.interrupt(store, call, stage)
                    (path,) = self.own_writes(record, text)
                    edited = store.abs(path).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                    store.abs(path).write_bytes(edited)
                    head, remote = gitcmd.head_commit(store.root), self.remote_main(name)
                    with self.assertRaises(ReconcileRequired) as raised:
                        call()
                    self.assertEqual(edited, store.abs(path).read_bytes(), "the change is left as it is")
                    self.assertEqual((head, remote), (gitcmd.head_commit(store.root), self.remote_main(name)), "nothing committed or pushed")
                    self.assertEqual([record["mutation_id"]], [p["mutation_id"] for p in self.pending(store)])
                    outcomes[label] = without_ids(raised.exception.message)
                self.assertIn("no longer holds what this operation wrote there", outcomes["lone CR"])
                self.assertEqual(outcomes["CRLF"], outcomes["lone CR"])

    def test_a_person_committing_after_the_git_stage_is_refused_as_for_crlf(self) -> None:
        """A commit the mutation did not make is not adopted: its push cannot show what it publishes."""
        outcomes = {}
        for label, text in (("lone CR", LONE_CR), ("CRLF", CRLF)):
            name = label.replace(" ", "-")
            store = self.new_project(name, remote=True)
            spec = WorkSpec("S", text)
            call = lambda: cr.create_standalone_work(store, spec)  # noqa: E731
            record = self.strand(store, call) if text == LONE_CR else self.interrupt(store, call, r"^finalize$")
            (path,) = self.own_writes(record, text)
            git(store.root, "add", "--", path)
            git(store.root, "commit", "-q", "-m", "person: commit the Work", "--", path)
            person = gitcmd.head_commit(store.root)
            with self.assertRaises(ReconcileRequired) as raised:
                call()
            self.assertEqual(person, gitcmd.head_commit(store.root), "no commit made on the person's")
            self.assertIsNone(self.remote_main(name), "nothing pushed")
            self.assertEqual([record["mutation_id"]], [p["mutation_id"] for p in self.pending(store)])
            outcomes[label] = without_ids(raised.exception.message)
        self.assertIn("cannot show which commit it publishes", outcomes["lone CR"])
        self.assertEqual(outcomes["CRLF"], outcomes["lone CR"])

    def _roadmap(self, store: ProjectStore, text: str):
        the_plan = rm.RoadmapPlan("RN", "BG", text, {"n": PhaseSpec("PN", "N")})
        return store, lambda: rm.create_roadmap(store, the_plan)

    def _derivation(self, store: ProjectStore, text: str):
        (work_id,) = [w.id for w in ProjectView.load(store).works.values() if w.name == "W1"]
        executor = scripted_executor({work_id: [st.Derive({"fix": st.DerivedWork("Fix", text)}), st.Completed()]})
        return store, lambda: st.start(store, work_id, "single-work", executor)


class CompatibilityTests(ProjectCase):
    """What succeeded on the baseline succeeds here unchanged: a CRLF checkout, and interrupted CRLF records."""

    def test_pin_maintenance_on_a_crlf_checkout(self) -> None:
        """A Project checked out as a Windows clone holds it - CRLF files, clean status - still changes its pin."""
        store = self.new_project(remote=True)
        rm.create_roadmap(store, rm.RoadmapPlan("R", "BG", "DS", {"a": PhaseSpec("PA", "A")}))
        git(store.root, "config", "core.autocrlf", "true")
        tracked = [line for line in git(store.root, "ls-files", "--", WORKLINE_DIR).splitlines() if line]
        for relative in tracked:
            (store.root / relative).unlink()
        git(store.root, "checkout", "--", *tracked)
        self.assertIn(b"\r\n", store.project_yaml.read_bytes(), "checked out with CRLF")
        self.assertEqual([], self.dirty(store), "and clean")
        url = self.remote_url()
        result = pin_push_destination(store.root, [url, url + "-alt"])
        self.assertEqual("pinned", result.status)
        self.assertEqual([], self.pending(store))
        self.assertEqual((url, url + "-alt"), store.read_push_pin().allowed_urls)
        self.assertEqual(gitcmd.head_commit(store.root), self.remote_main(), "committed and pushed")

    def test_an_interrupted_crlf_roadmap_creation_resumes(self) -> None:
        store = self.new_project(remote=True)
        the_plan = rm.RoadmapPlan("R", "BG", CRLF, {"a": PhaseSpec("PA", "A")})
        with before_recording(r"^phases$"):
            with self.assertRaises(Interrupted):
                rm.create_roadmap(store, the_plan)
        (record,) = self.pending(store)
        (effect,) = [e for e in record["effects"] if e["kind"] == "write_file"]
        data = store.abs(effect["payload"]["path"]).read_bytes()
        self.assertIn(CRLF.encode("utf-8"), data)
        result = rm.create_roadmap(store, the_plan)
        self.assertEqual((record["mutation_id"], True), (result.mutation_id, result.resumed))
        self.assertEqual([], self.pending(store))
        self.assertEqual(data, blob(store.root, f"HEAD:{effect['payload']['path']}"), "committed as written")
        self.assertEqual(gitcmd.head_commit(store.root), self.remote_main())

    def test_an_interrupted_crlf_start_derivation_resumes(self) -> None:
        store, _, work_id = self.base_project()
        executor = scripted_executor({work_id: [st.Derive({"fix": st.DerivedWork("Fix", CRLF)}), st.Completed()]})
        with before_recording(r"^commit:0$"):
            with self.assertRaises(Interrupted):
                st.start(store, work_id, "single-work", executor)
        (record,) = self.pending(store)
        (path,) = [e["payload"]["path"] for e in record["effects"] if e["kind"] == "write_file" and CRLF in e["payload"]["content"]]
        data = store.abs(path).read_bytes()
        result = st.start(store, work_id, "single-work", executor)
        self.assertEqual(("completed", record["mutation_id"]), (result.status, result.mutation_id))
        self.assertEqual([], self.pending(store))
        self.assertEqual(data, blob(store.root, f"HEAD:{path}"), "committed as written")
        self.assertEqual(gitcmd.head_commit(store.root), self.remote_main())


class ReviewCreateTests(WorklineTestCase):
    """A Review record's create is still classified by its exact bytes: nothing is read back for it."""

    def test_a_record_holding_other_line_ends_is_not_the_record(self) -> None:
        store = self.new_project()
        controller = MutationController(store)
        relative = paths.receipt_rel(RECEIPT_ID)
        text = serialize.canonical_text(receipt_record())
        record = {"kind": "create_file", "payload": {"path": relative, "content": text}}
        self.assertEqual(UNAPPLIED, controller.classify(record))
        target = store.root / relative
        target.parent.mkdir(parents=True)
        for label, held, expected in (
            ("the record", text, MATCHING),
            ("CRLF", text.replace("\n", "\r\n"), MISMATCH),
            ("lone CR", text.replace("\n", "\r"), MISMATCH),
        ):
            with self.subTest(label):
                target.write_bytes(held.encode("utf-8"))
                self.assertEqual(expected, controller.classify(record))


if __name__ == "__main__":
    unittest.main()
