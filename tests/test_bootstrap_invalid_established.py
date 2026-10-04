"""An established Project whose canonical state is broken is reported as broken, never as no Project (RB10 N6-3).

``is_established_project`` answered yes or no: a missing ``project.yaml``, an untracked one and an unreadable
``related.yaml`` all came back as "no", and the bootstrap backfill reported every one of them as ``not_a_project``
- describing a Project with an intact identity and one corrupt ledger as absence, and losing the reason.

Identity and validity are two questions now (``bootstrap.project_establishment``). No identity - ``project.yaml``
missing, or not tracked by the Project repository - is still ``not_a_project``. An established Project whose
``project.yaml`` does not validate, or whose Roadmap relations, Related relations or event log the canonical reader
cannot read, STOPs with that reader's or validator's own code and reason. Either way the backfill writes nothing,
begins no mutation, and never treats the Project as one to initialize or repair. The boolean predicate stays for
callers that only need yes or no.
"""

from __future__ import annotations

import unittest

from helpers import WorklineTestCase, git
from workline import bootstrap as bs
from workline.errors import StopError
from workline.mutation import MutationController
from workline.store import BOOTSTRAP_REL_PATH, WORKLINE_DIR, ProjectStore

PROJECT_YAML = f"{WORKLINE_DIR}/project.yaml"
ROADMAP_YAML = f"{WORKLINE_DIR}/relations/roadmap.yaml"
RELATED_YAML = f"{WORKLINE_DIR}/relations/related.yaml"
EVENT_LOG = f"{WORKLINE_DIR}/events/events.jsonl"


def tree(store: ProjectStore) -> dict[str, bytes | None]:
    """Every entry of the Project's working tree outside .git and the execution lock, byte for byte."""
    found: dict[str, bytes | None] = {}
    for path in sorted(store.root.rglob("*")):
        relative = path.relative_to(store.root).as_posix()
        if relative == ".git" or relative.startswith(".git/") or "/runtime/locks" in relative:
            continue
        if relative in (f"{WORKLINE_DIR}/runtime", f"{WORKLINE_DIR}/runtime/tmp") and path.is_dir():
            continue
        found[relative] = path.read_bytes() if path.is_file() else None
    return found


class InvalidEstablishedCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.simple_roadmap(self.store)
        # As the previous ProjectSTART left a Project: no bootstrap, so the backfill would have something to do.
        git(self.store.root, "rm", "-q", "--cached", BOOTSTRAP_REL_PATH)
        (self.store.root / BOOTSTRAP_REL_PATH).unlink()
        git(self.store.root, "commit", "-q", "-m", "a Project from before the bootstrap")

    def corrupt(self, relative: str, data: bytes, *, commit: bool = False) -> None:
        (self.store.root / relative).write_bytes(data)
        if commit:
            git(self.store.root, "commit", "-q", "-m", "corrupt", "--", relative)

    def assertBackfillRefused(self, code: str, reason: str) -> StopError:
        before, head = tree(self.store), git(self.store.root, "rev-parse", "HEAD")
        with self.assertRaises(StopError) as refused:
            bs.backfill_bootstrap(self.store.root)
        self.assertEqual(refused.exception.code, code, refused.exception.message)
        self.assertIn(reason, refused.exception.message)
        self.assertEqual(tree(self.store), before, "nothing written, nothing repaired, no bootstrap")
        self.assertEqual(git(self.store.root, "rev-parse", "HEAD"), head, "nothing committed")
        self.assertFalse((self.store.root / BOOTSTRAP_REL_PATH).exists())
        self.assertEqual(MutationController(self.store).list_pending(), [], "no backfill mutation was begun")
        return refused.exception


class StructuralCauseTests(InvalidEstablishedCase):
    def test_an_unreadable_related_yaml_reports_its_own_cause(self) -> None:
        for committed in (False, True):
            with self.subTest(committed=committed):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    case.corrupt(RELATED_YAML, b"relations: [\n", commit=committed)
                    error = case.assertBackfillRefused("relations_invalid", RELATED_YAML)
                    case.assertNotIn("not_a_project", error.message)
                    found = bs.project_establishment(case.store)
                    case.assertEqual((found.status, found.code), (bs.INVALID, "relations_invalid"))
                    case.assertFalse(bs.is_established_project(case.store))
                finally:
                    case.doCleanups()

    def test_a_malformed_related_record(self) -> None:
        self.corrupt(RELATED_YAML, b"relations:\n  - id: rel_x\n    type: must_read\n")
        self.assertBackfillRefused("relations_invalid", "relation record malformed")

    def test_an_unreadable_roadmap_yaml(self) -> None:
        self.corrupt(ROADMAP_YAML, b"relations:\n- [nested]\n")
        self.assertBackfillRefused("relations_invalid", ROADMAP_YAML)

    def test_a_missing_ledger(self) -> None:
        (self.store.root / RELATED_YAML).unlink()
        self.assertBackfillRefused("relations_invalid", "missing relation file")

    def test_an_unreadable_event_log(self) -> None:
        self.corrupt(EVENT_LOG, b'{"id": "evt_x"\n')
        self.assertBackfillRefused("events_invalid", "events line 1 malformed")

    def test_invalid_project_yaml_content(self) -> None:
        text = (self.store.root / PROJECT_YAML).read_text(encoding="utf-8")
        cases = {
            "rules missing": (text.split("rules:")[0], "rules missing"),
            "a malformed push pin": (text + "git:\n  push: nope\n", "git.push must be a mapping"),
        }
        for label, (content, reason) in cases.items():
            with self.subTest(label):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    case.corrupt(PROJECT_YAML, content.encode("utf-8"), commit=True)
                    case.assertBackfillRefused("project_yaml_invalid", reason)
                finally:
                    case.doCleanups()


class NoIdentityTests(WorklineTestCase):
    def test_a_folder_without_project_yaml_is_not_a_project(self) -> None:
        root = self.new_dir("plain")
        git(root, "init", "-q", "-b", "main")
        (root / "a.txt").write_text("a\n", encoding="utf-8")
        git(root, "add", "a.txt")
        git(root, "commit", "-q", "-m", "not a Workline Project")
        found = bs.project_establishment(ProjectStore(root))
        self.assertEqual((found.status, found.code), (bs.NOT_ESTABLISHED, "not_a_project"))
        with self.assertRaises(StopError) as refused:
            bs.backfill_bootstrap(root)
        self.assertEqual(refused.exception.code, "not_a_project")
        self.assertFalse((root / ".workline").exists(), "never initialized")

    def test_an_untracked_project_yaml_is_no_identity_yet(self) -> None:
        store = self.new_project()
        git(store.root, "rm", "-q", "--cached", PROJECT_YAML)
        git(store.root, "commit", "-q", "-m", "untrack project.yaml")
        found = bs.project_establishment(store)
        self.assertEqual((found.status, found.code), (bs.NOT_ESTABLISHED, "not_a_project"))
        with self.assertRaises(StopError) as refused:
            bs.backfill_bootstrap(store.root)
        self.assertEqual(refused.exception.code, "not_a_project")
        self.assertIn("not tracked", refused.exception.message)

    def test_a_valid_project_is_established(self) -> None:
        store = self.new_project()
        found = bs.project_establishment(store)
        self.assertEqual((found.status, found.code), (bs.ESTABLISHED, None))
        self.assertTrue(bs.is_established_project(store))
        self.assertEqual(bs.backfill_bootstrap(store.root).status, "already_present")


if __name__ == "__main__":
    unittest.main()
