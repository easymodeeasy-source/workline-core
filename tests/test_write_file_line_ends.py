"""How a recorded ``write_file`` is classified for each line ending of the decided text (BL-056).

The Mutation Controller writes a ``write_file`` payload as given - UTF-8, no line
ending translated (``durable_write_text``) - and the Project reader reads every
file with universal newlines: CRLF and a lone CR (one no LF follows) both read as
LF (``store.as_read_back``). The classifier reads the file the reader's way and
compares it with the recorded content with only CRLF folded, so the operation's
own write of a text holding a lone CR is classified applied with an unexpected
result, and the next replay of the record stops ``reconcile required`` - on every
retry of the same request.

These pins state, for each line-end shape of the decided text, what the writer
puts on disk, what the reader reads, how the operation's own write is
classified, and what a Roadmap creation carrying the text in its desired state
does end to end.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import NamedTuple
import unittest

from helpers import WorklineTestCase, git
from workline import roadmap as rm
from workline.errors import ReconcileRequired
from workline.ids import new_id
from workline.mutation import MATCHING, MISMATCH, Effect, MutationController, WriteScope
from workline.oplock import project_operation
from workline.phase_create import PhaseSpec
from workline.state import ProjectView
from workline.store import (
    ROADMAP_DESIRED_HEADING,
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
    "lone CR": Shape("a\rb", "a\nb", MISMATCH, False),
    "mixed": Shape("a\r\nb\rc\n", "a\nb\nc", MISMATCH, False),
    "trailing lone CR": Shape("abc\r", "abc", MISMATCH, True),
    "LF at end": Shape("abc\n", "abc", MATCHING, True),
    "CRLF at end": Shape("abc\r\n", "abc", MATCHING, True),
}


def blob(root: Path, spec: str) -> bytes:
    """The bytes Git stores for ``spec`` (``<rev>:<path>``), untranslated."""
    return subprocess.run(["git", "-C", str(root), "cat-file", "blob", spec], capture_output=True, check=True).stdout


def work_text(work_id: str, text: str) -> str:
    """A standalone Work whose desired-state section is ``text``, at the very end of the file."""
    return (
        f"---\nid: {work_id}\ndisplay: W-01\ntype: work\norigin:\n  type: standalone\n---\n\n"
        f"# W\n\n## {WORK_DESIRED_HEADING}\n{text}"
    )


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


if __name__ == "__main__":
    unittest.main()
