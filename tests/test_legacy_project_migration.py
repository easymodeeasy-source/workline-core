"""BL-011: the canonical Legacy Project migration procedure, proven on a disposable representative legacy Project.

WORKLINE_COMPLETION_SPRINT §17.1 - §17.11 and §33.1 - §33.13 / §33.22. The procedure is canonical in
``skills/roadmap`` (Legacy Project migration). This module is the fixture / acceptance proof of that
procedure and nothing more: there is no migration controller, owner, schema or Skill behind it. Every step
is an existing owner's ordinary operation - Project開始, Roadmap creation, the review-v1 Phase entry, START,
START's Phase Integration Review, the RB6 shadow-authority detector, the read-only ``status`` CLI, canonical
validation and the RB5 Roadmap achievement. The read-only inventory and the A-F table below are the
migration session's own working record (§33.3: procedure evidence, not a canonical persistent schema); they
never reach ``.workline``.

The legacy Project is built in a temporary directory; no real Project is touched or backfilled.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import textwrap
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, cwd, git, launcher_command, run_python
from planning_helpers import CANONICAL_RULE, Reviewer
from rb5_run_helpers import IntegrationRunCase, phase_review
from test_implementation_identity import activation, driver_command

from workline import achievement as ach
from workline import ids
from workline import roadmap as rm
from workline import shadow_authority as sa
from workline import start as st
from workline.create import RelatedSpec
from workline.errors import StopError, ValidationError
from workline.mutation import MutationController
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.project_start import project_start
from workline.registry import REQUIRED_SKILL_IDS
from workline.review import fsafe
from workline.review import integration as ri
from workline.review.store import ReviewStore
from workline.state import ProjectView
from workline.store import BOOTSTRAP_REL_PATH, ProjectStore
from workline.validate import validate_project

ROADMAP_SKILL = WORKLINE_ROOT / ".claude" / "skills" / "roadmap" / "SKILL.md"
PROJECT_START_SKILL = WORKLINE_ROOT / ".claude" / "skills" / "project-start" / "SKILL.md"
REGISTRY = WORKLINE_ROOT / "registry.md"
SRC = WORKLINE_ROOT / "src" / "workline"

#: A private operator note inside the legacy tracker: it must never reach Workline canonical history (§33.3).
PRIVATE = "PRIVATE-NOTE-7Q3K"
CLAIM = "This file is the source of truth for what to do next."

TRACKER_SKILL = ".claude/skills/legacy-tracker/SKILL.md"
LINT_SKILL = ".claude/skills/domain-lint/SKILL.md"
CALLER_SKILL = ".claude/skills/ask-workline/SKILL.md"

#: The representative legacy Project (§17.11, §33.13): every kind of authority the procedure must sort.
LEGACY: dict[str, str] = {
    # a legacy state / progression tracker with a current (in-progress) and a future obligation
    "NOTES.md": (
        "# Notes\n\n"
        f"{CLAIM}\n\n"
        "Current task: export the monthly report as CSV (in progress; the parser part is done).\n"
        "Next task: add the summary page, after the CSV export.\n"
        "Done: the initial importer.\n\n"
        f"Operator note: {PRIVATE} (not for publication).\n"
    ),
    # a legacy plan / Roadmap-like authority that also carries one still-applicable safety rule
    "PLAN.md": (
        "# Plan\n\n"
        "Milestone 1: CSV export of the monthly report.\n"
        "Milestone 2: summary page.\n\n"
        "Rule: exported files never contain the internal_id column.\n"
    ),
    # named TODO, but a domain glossary the product team owns: the name never decides the class
    "TODO.md": (
        "# Glossary and open product questions\n\n"
        "Owned by the product team.\n\n"
        "- monthly report: the report of one calendar month\n"
        "- summary page: one page per monthly report\n"
    ),
    # stricter Project-specific safety
    "CONTRACT.md": "# Contract\n\n- Run the domain linter before every commit that touches src/.\n",
    # a distinct domain authority
    "docs/domain/spec.md": "# Report specification\n\nA monthly report has one row per account.\n",
    # Project-local automation that keeps a parallel progression in NOTES.md (overlaps Workline)
    TRACKER_SKILL: (
        "---\nname: legacy-tracker\ndescription: Keeps the project notes up to date.\n---\n\n"
        "This Skill decides the next Work from NOTES.md and marks the current Work done in NOTES.md.\n"
    ),
    # a distinct domain capability
    LINT_SKILL: (
        "---\nname: domain-lint\ndescription: Lint the report schema.\n---\n\n"
        "Lint the domain glossary in TODO.md and docs/domain/spec.md against the export schema.\n"
    ),
    # a caller of the canonical owner that keeps no Workline state of its own
    CALLER_SKILL: (
        "---\nname: ask-workline\ndescription: Ask the project's planner what is next.\n---\n\n"
        "Ask Workline to pick the next Work, then run START for it.\n"
    ),
    # a derived, read-only view
    "STATUS.md": "# Build status (generated by CI; do not edit)\n\nlast build: green\n",
    # historical evidence
    "CHANGELOG.md": "# Changelog\n\n- 0.1: the initial importer\n",
    # obsolete
    "scripts/old_release.sh": "#!/bin/sh\necho 'manual release (replaced)'\n",
    "OLD_PROCESS.md": "# Old release process\n\nRun scripts/old_release.sh by hand. Replaced; nobody uses it any more.\n",
}

#: The migration session's A-F table (§17.3 / §33.4): one class per responsibility, decided by responsibility.
CLASSIFICATION: tuple[tuple[str, str, str], ...] = (
    ("NOTES.md", "current / next task tracking (legacy progression)", "A"),
    ("PLAN.md", "milestone plan (legacy Roadmap)", "A"),
    ("PLAN.md", "export safety rule: no internal_id column in exported files", "C"),
    ("TODO.md", "product glossary and open product questions", "B"),
    ("CONTRACT.md", "stricter Project-specific safety", "C"),
    ("docs/domain/spec.md", "report domain specification", "B"),
    (TRACKER_SKILL, "Skill keeping the current / next task in NOTES.md", "A"),
    (LINT_SKILL, "domain lint capability", "B"),
    (CALLER_SKILL, "caller of the canonical Workline owner, no own state", "B"),
    ("STATUS.md", "CI-generated dashboard", "D"),
    ("CHANGELOG.md", "release history", "E"),
    ("scripts/old_release.sh", "replaced manual release script", "F"),
    ("OLD_PROCESS.md", "replaced release procedure", "F"),
)

#: Files the RB6 detector must never read: prose and data, whatever their names say (§33.10).
NEVER_READ = ("NOTES.md", "PLAN.md", "TODO.md", "CONTRACT.md", "docs/domain/spec.md", "STATUS.md", "CHANGELOG.md",
              "OLD_PROCESS.md", "scripts/old_release.sh")


# --------------------------------------------------------------------------- the migration session's working record


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_only_git(root: Path, *args: str) -> str:
    """One Git read of the preflight, with optional locks off (``skills/roadmap``: no index stat-cache write-back)."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    done = subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args], capture_output=True, env=env)
    return done.stdout.decode("utf-8", "replace") if done.returncode == 0 else ""


def inventory(root: Path) -> dict:
    """The read-only migration inventory of one frozen target identity (§17.2 / §33.3), held in memory only."""
    files: dict[str, str] = {}
    for current, directories, names in os.walk(root):
        directories[:] = [name for name in directories if name != ".git"]
        for name in names:
            path = Path(current) / name
            files[path.relative_to(root).as_posix()] = _digest(path.read_bytes())
    info = os.stat(root)
    status = read_only_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    return {
        "root": os.path.realpath(root),
        "identity": (info.st_dev, info.st_ino),
        "toplevel": read_only_git(root, "rev-parse", "--show-toplevel").strip(),
        "branch": read_only_git(root, "symbolic-ref", "-q", "HEAD").strip() or None,
        "head": read_only_git(root, "rev-parse", "--verify", "-q", "HEAD").strip() or None,
        "status": sorted(entry[3:] for entry in status.split("\0") if entry),
        "files": files,
        "local_skills": sorted(path for path in files if path.startswith(".claude/skills/")),
        "prior_workline": sorted(path for path in files if path == BOOTSTRAP_REL_PATH or path.startswith(".workline/")),
    }


def material_changes(before: dict, after: dict) -> list[str]:
    """What changed between two inventories of one target: a non-empty answer means refresh before cutover."""
    changed = [key for key in ("root", "identity", "toplevel", "branch", "head", "status") if before[key] != after[key]]
    paths = set(before["files"]) | set(after["files"])
    return changed + sorted(path for path in paths if before["files"].get(path) != after["files"].get(path))


def git_state(root: Path) -> dict:
    """The repository bytes a read must leave alone: index (bytes and mtime), HEAD, refs, config, no lock."""
    git_dir = root / ".git"
    index = git_dir / "index"
    refs = {path.relative_to(git_dir).as_posix(): path.read_bytes() for path in sorted((git_dir / "refs").rglob("*"))
            if path.is_file()}
    return {
        "index": index.read_bytes(),
        "index_mtime": index.stat().st_mtime_ns,
        "head": (git_dir / "HEAD").read_bytes(),
        "refs": refs,
        "config": (git_dir / "config").read_bytes(),
        "index_lock": (git_dir / "index.lock").exists(),
    }


def work_ids_by_name(store: ProjectStore, phase_id: str) -> dict[str, str]:
    return {work.name: work.id for work in ProjectView.load(store).phase_works(phase_id)}


# --------------------------------------------------------------------------- the fresh session's view

_DRIVER = textwrap.dedent(
    """\
    import json
    from pathlib import Path
    from workline.state import ProjectView
    from workline.store import ProjectStore

    store = ProjectStore(Path.cwd())
    view = ProjectView.load(store)
    phase_id = {phase_id!r}
    obligations = {{}}
    for work in view.phase_works(phase_id):
        state = view.work_state(work.id)
        if state.terminal:
            continue
        obligations[work.id] = {{
            "state": state.state,
            "related": sorted([r.type, r.to, (store.root / r.to).is_file()] for r in view.related_from(work.id)),
            "requires": sorted([r.from_id, view.entity_state_label(r.from_id)]
                               for r in view.relations_to(work.id, "requires_completion")),
        }}
    print("FRESH " + json.dumps({{"configured_root": str(store.workline_root()), "obligations": obligations}},
                                sort_keys=True))
    """
)


class MigrationCase(IntegrationRunCase):
    """A disposable legacy Project, committed as its own repository on ``main``."""

    def legacy_project(self, name: str = "legacy", extra: dict[str, str] | None = None) -> Path:
        root = self.new_dir(name)
        git(root, "init", "-q", "-b", "main")
        for relative, text in {**LEGACY, **(extra or {})}.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "the legacy project")
        return root

    def fresh_session(self, root: Path, phase_id: str) -> tuple[dict, dict]:
        """Status and the read obligations, each from a new isolated process with no migration state (§33.11)."""
        status = run_python(launcher_command(WORKLINE_ROOT, "status", ".", "--json"), cwd=root)
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        driven = run_python(driver_command(), cwd=root,
                            stdin=activation(WORKLINE_ROOT) + _DRIVER.format(phase_id=phase_id))
        self.assertEqual(driven.returncode, 0, driven.stdout + driven.stderr)
        line = next(item for item in driven.stdout.splitlines() if item.startswith("FRESH "))
        return json.loads(status.stdout), json.loads(line[len("FRESH "):])

    def assertProvenNoShadow(self, shadow: dict) -> None:
        """The RB8 shadow gate (§33.10, CP ruling): confirmed none, and a proven result - never ``.get`` defaults."""
        self.assertIn(shadow["status"], (sa.NONE, sa.SUSPECTED, sa.CONFIRMED))
        self.assertEqual(shadow["confirmed_count"], 0)
        self.assertIs(shadow["bootstrap_inspected"], True)
        self.assertIs(shadow["complete"], True)


# --------------------------------------------------------------------------- the canonical procedure text


class RoadmapSkillPreflightTests(unittest.TestCase):
    """§33.2 / §33.22: the Roadmap Skill exposes only the narrow, read-only pre-Project migration preflight."""

    def setUp(self) -> None:
        self.skill = ROADMAP_SKILL.read_text(encoding="utf-8")
        self.section = self.skill[self.skill.index("## Legacy Project migration"):self.skill.index("## Review-v1 planning")]
        self.preflight = self.section[self.section.index("### Project開始前のread-only preflight（唯一の例外）"):
                                      self.section.index("### Migration inventory")]
        self.registry = REGISTRY.read_text(encoding="utf-8")

    def test_the_description_keeps_its_applicability_and_names_one_bounded_exception(self) -> None:
        description = self.skill.split("---")[1]
        self.assertIn("Use ONLY inside an established Workline Project (one that already has .workline/project.yaml) for "
                      "Roadmap creation, planning changes, Phase selection/entry, Roadmap or Phase hold/resume/cancel, "
                      "and achievement checks.", description)
        self.assertIn("One exception: Legacy Project migration, whose read-only preflight (inventory and A-F "
                      "classification of an existing project's legacy authority, writing nothing) may run before "
                      "ProjectSTART", description)
        self.assertIn("the migration itself is an ordinary Migration Roadmap after ProjectSTART", description)
        self.assertLess(len(description), 1024)

    def test_the_preflight_allows_four_things_and_forbids_six(self) -> None:
        allowed = self.preflight[:self.preflight.index("Project開始の前には次のどれも行わない。")]
        for item in ("- 対象のProject directory / repositoryを特定する",
                     "- 1つの固定したidentityに対するread-onlyのmigration inventory（下記）を取る",
                     "- legacy authorityを責任でA〜Fに分類する（下記）",
                     "- Project開始後の移行計画（Migration Roadmapの案）を準備する"):
            with self.subTest(allowed=item):
                self.assertIn(item, allowed)
        forbidden = self.preflight[self.preflight.index("Project開始の前には次のどれも行わない。"):]
        for item in ("- Roadmap / Phase / Workを作る", "- Gitを変更する（`git init`・commit・index・ref・configの変更を含む）",
                     "- legacy authorityをretire・削除・無効化する", "- canonical Skillをinstall / copyする",
                     "- `.workline` を作る", "- capabilityを変えるproject-local Skill / 自動化の変更をする"):
            with self.subTest(forbidden=item):
                self.assertIn(item, forbidden)
        self.assertIn("preflightは何も書かず、routingもしない", forbidden)
        self.assertIn("`git --no-optional-locks`", forbidden)

    def test_project_start_stays_the_only_establishment_owner(self) -> None:
        self.assertIn("Project開始（`skills/project-start`）は変わらず、Workline Projectを成立させる唯一のoperationである",
                      self.section)
        self.assertIn("Project開始はlegacy authorityの棚卸し、旧current stateの推測、historyの移行、旧自動化のretire、"
                      "移行の達成判定を行わない", self.section)
        self.assertIn("新しいlifecycle・Controller・Skill・永続schema・runtime operationではなく", self.section)
        project_start_skill = PROJECT_START_SKILL.read_text(encoding="utf-8")
        self.assertIn("Project開始は、Workline Projectを成立させる唯一のoperationであり、Project成立前に書き込む唯一の"
                      "Workline operationである", project_start_skill)
        self.assertIn("before a Workline Project exists", project_start_skill.split("---")[1])
        self.assertIn("Workline Projectを成立させるoperation、およびProject成立前に書き込むWorkline operationは、"
                      "Project開始（`pre-project`）だけである", self.registry)

    def test_the_registry_carve_out_is_prose_and_roadmap_stays_a_project_skill(self) -> None:
        carve_out = next(line for line in self.registry.splitlines() if "唯一の例外は `skills/roadmap` のLegacy Project migration" in line)
        self.assertNotIn("<!--", carve_out)
        self.assertIn("`skills/roadmap` のcontextは `project` のままであり、新しいcontext値を作らない", carve_out)
        self.assertIn("<!-- workline-id: skills/roadmap -->\n<!-- workline-target: .claude/skills/roadmap/SKILL.md -->\n"
                      "<!-- workline-context: project -->", self.registry)
        self.assertEqual(set(re.findall(r"<!-- workline-context: ([a-z-]+) -->", self.registry)),
                         {"pre-project", "router", "project"})

    def test_the_procedure_names_every_frozen_step(self) -> None:
        for phrase in (
            "### Migration inventory", "これは手順のevidenceであり、新しいcanonicalな永続schemaではない",
            "inventoryを取り直して照合してから進む",
            "### A〜F分類（責任で決め、file名で決めない）", "ROADMAP・TODO・BACKLOG・STATUS・CLAUDE等の名前やvocabularyはclassを決めない",
            "### Project開始はcutoverの境界", "長く続く2-controller modeに頼らない",
            "### Migration Roadmap", "過去の `work_started` / `work_completed`", "過去のReview Run / Receipt",
            "lifecycleへbackfillしない",
            "### Local safety / domain authorityの保持", "移行はCを決して弱めない",
            "### Project-local Skill・自動化・hook", "canonical Workline SkillをProjectへcopyしない",
            "### 重なるlegacy authorityのretire", "keywordの一致でretireしない", "B / Cの責任をretireしない",
            "### Shadow-authority check", "`confirmed_count` が0、`bootstrap_inspected`、`complete`",
            "detectorに移行・retire・修復をさせない",
            "### Fresh-session standalone recovery", "retireしたlegacy progression authorityが、現在のWorkline stateの再構成に必要なら、移行は終わっていない",
            "### Migration achievement", "Migration Roadmapは、別のcompletion / achievementの仕組みを作らない",
            "通常のPhase達成evidence（RB5）とRoadmap achievementの意味とevidenceに従う",
        ):
            with self.subTest(phrase=phrase[:40]):
                self.assertIn(phrase, self.section)


class ScopeTests(unittest.TestCase):
    """§33.21 / §33.24: the procedure adds no Skill, controller, runtime owner, schema or ID kind."""

    def test_no_new_skill_or_routing(self) -> None:
        registry = REGISTRY.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r"<!-- workline-id: (skills/[a-z-]+) -->", registry)), set(REQUIRED_SKILL_IDS))
        skills = {path.name for path in (WORKLINE_ROOT / ".claude" / "skills").iterdir() if path.is_dir()}
        self.assertEqual(skills, {skill_id.split("/", 1)[1] for skill_id in REQUIRED_SKILL_IDS})

    def test_no_migration_controller_engine_or_schema(self) -> None:
        for module in ("project_start.py", "roadmap.py"):
            with self.subTest(module=module):
                self.assertNotRegex((SRC / module).read_text(encoding="utf-8"), r"(?i)migrat")
        self.assertEqual([], [path.name for path in SRC.rglob("*.py") if re.search(r"(?i)migrat|legacy", path.name)])
        self.assertEqual([], [kind for kind in ids.PREFIXES if re.search(r"(?i)migrat|legacy", kind)])
        self.assertEqual(list(inspect.signature(project_start).parameters),
                         ["project_root", "workline_root", "expected_push_url", "push_remote"])


# --------------------------------------------------------------------------- the read-only preflight


class PreflightInventoryTests(MigrationCase):
    """§17.2 / §33.2 - §33.4: one read-only observation of one frozen identity, classified by responsibility."""

    def test_the_inventory_is_read_only_against_one_frozen_identity(self) -> None:
        root = self.legacy_project()
        # a stale stat cache: a stat-refreshing `git status` would now rewrite the index
        changelog = root / "CHANGELOG.md"
        stamp = changelog.stat().st_mtime_ns + 5_000_000_000
        os.utime(changelog, ns=(stamp, stamp))
        before = git_state(root)
        tree_before = {path: _digest((root / path).read_bytes()) for path in LEGACY}

        found = inventory(root)

        self.assertEqual(git_state(root), before, "the inventory wrote no index, ref, config or lock")
        self.assertEqual({path: _digest((root / path).read_bytes()) for path in LEGACY}, tree_before)
        self.assertFalse(os.path.lexists(root / ".workline"))
        self.assertFalse(os.path.lexists(root / BOOTSTRAP_REL_PATH))
        self.assertTrue(os.path.samefile(found["toplevel"], root))
        self.assertEqual(found["branch"], "refs/heads/main")
        self.assertEqual(found["head"], git(root, "rev-parse", "HEAD").strip())
        self.assertEqual(found["status"], [])
        self.assertEqual(set(found["files"]), set(LEGACY))
        self.assertEqual(found["local_skills"], sorted((CALLER_SKILL, LINT_SKILL, TRACKER_SKILL)))
        self.assertEqual(found["prior_workline"], [])
        self.assertEqual(material_changes(found, inventory(root)), [], "the same frozen identity reads the same")

    def test_a_material_authority_change_before_cutover_forces_a_refresh(self) -> None:
        root = self.legacy_project()
        frozen = inventory(root)
        (root / "NOTES.md").write_bytes(LEGACY["NOTES.md"].replace("Next task", "Next task (moved up)").encode("utf-8"))
        self.assertEqual(material_changes(frozen, inventory(root)), ["status", "NOTES.md"])
        git(root, "commit", "-q", "-am", "a later legacy edit")
        refreshed = inventory(root)
        self.assertIn("head", material_changes(frozen, refreshed))
        self.assertEqual(material_changes(refreshed, inventory(root)), [], "the refreshed inventory is the one to migrate")

    def test_every_artifact_is_classified_a_to_f_by_responsibility_not_filename(self) -> None:
        root = self.legacy_project()
        found = inventory(root)
        classified = {path for path, _, _ in CLASSIFICATION}
        self.assertEqual(classified, set(found["files"]), "every inventoried artifact has a responsibility")
        self.assertEqual({klass for _, _, klass in CLASSIFICATION}, set("ABCDEF"))
        for path, responsibility, klass in CLASSIFICATION:
            with self.subTest(path=path, responsibility=responsibility):
                self.assertIn(klass, "ABCDEF")
        by_path: dict[str, set[str]] = {}
        for path, _, klass in CLASSIFICATION:
            by_path.setdefault(path, set()).add(klass)
        self.assertEqual(by_path["PLAN.md"], {"A", "C"}, "a file holding two responsibilities is classified per responsibility")
        self.assertEqual(by_path["TODO.md"], {"B"}, "TODO.md is domain authority here: the name decides nothing")
        self.assertEqual(by_path["STATUS.md"], {"D"}, "STATUS.md is a derived view, not a progression authority")
        self.assertEqual(by_path[TRACKER_SKILL], {"A"})
        self.assertEqual(by_path[CALLER_SKILL], {"B"}, "a canonical caller keeps no Workline state and is kept")

    def test_prior_workline_residue_is_inventoried_and_project_start_still_stops(self) -> None:
        """§17.2 "any prior Workline residue": a differing bootstrap stops Project開始 before it writes anything."""
        root = self.legacy_project(extra={BOOTSTRAP_REL_PATH: "---\nname: workline\n---\n\nan older entry\n"})
        found = inventory(root)
        self.assertEqual(found["prior_workline"], [BOOTSTRAP_REL_PATH])
        head = git(root, "rev-parse", "HEAD").strip()
        with cwd(WORKLINE_ROOT), self.assertRaises(StopError) as stopped:
            project_start(root, WORKLINE_ROOT)
        self.assertEqual(stopped.exception.code, "bootstrap_conflict")
        self.assertFalse(os.path.lexists(root / ".workline"))
        self.assertEqual(git(root, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(material_changes(found, inventory(root)), [])


# --------------------------------------------------------------------------- the whole procedure


class LegacyProjectMigrationAcceptanceTests(MigrationCase):
    """§17.11 / §33.13: inventory -> classification -> Project開始 -> Migration Roadmap -> preserve B / C ->
    retire A / F -> RB6 check -> fresh-session recovery -> validation -> RB5 achievement, in that order."""

    def test_the_procedure_end_to_end(self) -> None:
        root = self.legacy_project()
        frozen = inventory(root)
        legacy_head = frozen["head"]

        store = self.cutover(root, frozen)
        roadmap_id, cutover_id, carry_id = self.migration_roadmap(store)
        cutover = self.enter_cutover(store, cutover_id)
        before = sa.detect_shadow_authority(store.root)
        self.assertEqual({(item.path, item.level, item.rule) for item in before.evidence},
                         {(TRACKER_SKILL, sa.SUSPECTED, sa.RULE_SKILL_PARALLEL_PROGRESSION)},
                         "before retirement the overlapping legacy automation is suspected, never confirmed")
        self.assertProvenNoShadow(before.to_json())
        self.preserve_and_retire(store, cutover)
        self.shadow_check(store)
        carry = self.enter_carry(store, carry_id)
        self.assertEqual("completed", st.start(store, carry["csv"], "single-work", self.executor_writing(
            store, "src/export_csv.py", "def export(rows):\n    return rows  # without internal_id\n")).status)
        self.fresh_session_recovery(store, roadmap_id, carry_id, carry)
        self.assertEqual("completed", st.start(store, carry["summary"], "single-work", self.executor_writing(
            store, "src/summary_page.py", "def summary(report):\n    return report\n")).status)
        self.assertEqual("completed", self.integrate(store, carry["integration"], phase_review()).status)
        self.assertEqual(validate_project(store), [], "normal validation PASS")
        self.achieve(store, roadmap_id)
        self.no_fabrication(store, legacy_head, roadmap_id, (cutover_id, carry_id))
        self.preserved(store, frozen)

    # steps -----------------------------------------------------------------

    def cutover(self, root: Path, frozen: dict) -> ProjectStore:
        """§33.5: ordinary Project開始 is the cutover; it establishes its structure and bootstrap only."""
        self.assertEqual(material_changes(frozen, inventory(root)), [], "nothing moved since the inventory")
        with cwd(WORKLINE_ROOT):
            result = project_start(root, WORKLINE_ROOT)
        self.assertEqual(result.status, "initialized")
        self.enter(root)
        store = ProjectStore(root)
        self.assertEqual(git(root, "rev-parse", "HEAD~1").strip(), frozen["head"], "one initial commit on the legacy history")
        committed = git(root, "show", "--name-only", "--format=", "HEAD").split()
        self.assertTrue(committed)
        for path in committed:
            with self.subTest(committed=path):
                self.assertTrue(path.startswith(".workline/") or path == BOOTSTRAP_REL_PATH, path)
        for path, digest in frozen["files"].items():
            with self.subTest(legacy=path):
                self.assertEqual(_digest((root / path).read_bytes()), digest, "Project開始 changed no legacy file")
        self.assertEqual(sorted(p.parent.name for p in (root / ".claude" / "skills").glob("*/SKILL.md")),
                         ["ask-workline", "domain-lint", "legacy-tracker", "workline"],
                         "only the canonical bootstrap entry was added")
        # the Human prepares the Review checkout capability (rules/git; Workline never writes .gitattributes)
        self.commit_attributes(store, "* text=auto\n" + CANONICAL_RULE + "\n", message="review checkout capability")
        return store

    def migration_roadmap(self, store: ProjectStore) -> tuple[str, str, str]:
        """§33.6: an ordinary Roadmap whose Phases carry only genuine current / future obligations."""
        plan = rm.RoadmapPlan(
            "Migration to Workline",
            "The project ran on notes, a plan document and a tracker Skill; Workline now governs its planning.",
            "Every current and future obligation is canonical Workline state, the domain and stricter safety "
            "authority stay local and in force, and no legacy artifact still acts as a parallel controller.",
            {
                "cutover": PhaseSpec("Cutover", "Overlapping legacy authority is retired and local safety is preserved"),
                "carry": PhaseSpec("Current obligations", "The in-progress CSV export and the summary page are done"),
            },
            (PhaseRelationSpec("requires_completion", "cutover", "carry"),),
        )
        result = rm.create_roadmap(store, plan)
        return result.roadmap_id, result.phase_ids["cutover"], result.phase_ids["carry"]

    def enter_cutover(self, store: ProjectStore, phase_id: str) -> dict[str, str]:
        design = rm.PhaseEntryDesign(
            {
                "safety": rm.WorkDesign(
                    "Preserve the export safety rule",
                    "CONTRACT.md also holds the rule from PLAN.md that exported files never contain the internal_id "
                    "column, and none of its existing rules is weakened",
                    (RelatedSpec("must_read", "PLAN.md"), RelatedSpec("obey", "CONTRACT.md")),
                ),
                "notes": rm.WorkDesign(
                    "Mark the legacy tracker and plan historical",
                    "NOTES.md and PLAN.md claim no authority and say that the current and next Work are Workline state",
                ),
                "tracker": rm.WorkDesign(
                    "Retire the legacy tracker Skill",
                    "The legacy-tracker Skill no longer exists as Project-local automation, removed after the Human "
                    "confirmed the capability change",
                ),
                "obsolete": rm.WorkDesign(
                    "Remove the obsolete release process",
                    "The replaced release script and its process document are gone",
                ),
            },
            rm.WorkDesign("Integration", "The cutover holds as a whole"),
            planned_next=(("safety", "notes"), ("notes", "tracker"), ("tracker", "obsolete")),
        )
        result = rm.enter_phase(store, phase_id, design, review=Reviewer().review())
        self.assertEqual(result.status, "registered")
        found = work_ids_by_name(store, phase_id)
        return {"safety": found["Preserve the export safety rule"],
                "notes": found["Mark the legacy tracker and plan historical"],
                "tracker": found["Retire the legacy tracker Skill"],
                "obsolete": found["Remove the obsolete release process"],
                "integration": found["Integration"], "phase": phase_id}

    def preserve_and_retire(self, store: ProjectStore, ids_: dict[str, str]) -> None:
        """§33.7 - §33.9: preserve the still-applicable C rule first, then retire A and F through ordinary Works."""
        root = store.root

        def preserve(ctx):
            contract = root / "CONTRACT.md"
            contract.write_bytes(contract.read_bytes() + b"- Exported files never contain the internal_id column.\n")
            return st.Completed(("CONTRACT.md",))

        def mark_historical(ctx):
            banner = ("> Historical and non-authoritative since the Workline migration: the current and next Work "
                      "are Workline state.\n\n")
            for name in ("NOTES.md", "PLAN.md"):
                text = (root / name).read_bytes().decode("utf-8").replace(CLAIM + "\n\n", "")
                (root / name).write_bytes((banner + text).encode("utf-8"))
            return st.Completed(("NOTES.md", "PLAN.md"))

        def remove_tracker(ctx):
            shutil.rmtree(root / ".claude" / "skills" / "legacy-tracker")
            return st.Completed(deleted_paths=(TRACKER_SKILL,))

        def remove_obsolete(ctx):
            (root / "scripts" / "old_release.sh").unlink()
            (root / "scripts").rmdir()
            (root / "OLD_PROCESS.md").unlink()
            return st.Completed(deleted_paths=("OLD_PROCESS.md", "scripts/old_release.sh"))

        self.assertEqual("completed", st.start(store, ids_["safety"], "single-work", lambda ctx: preserve(ctx)).status)
        self.assertEqual("completed", st.start(store, ids_["notes"], "single-work", mark_historical).status)
        # a capability change: an ordinary question to the Human first, no Work made for it (rules/human-confirmation)
        asked = st.start(store, ids_["tracker"], "single-work",
                         lambda ctx: st.QuestionWait("Retiring legacy-tracker changes Project-local automation; may it go?"))
        self.assertEqual(asked.status, "question_wait")
        self.assertTrue((root / TRACKER_SKILL).is_file(), "nothing is retired before the Human answers")
        self.assertEqual("completed", st.start(store, ids_["tracker"], "single-work", remove_tracker).status)
        self.assertEqual("completed", st.start(store, ids_["obsolete"], "single-work", remove_obsolete).status)
        self.assertEqual("completed", self.integrate(store, ids_["integration"], phase_review()).status)
        self.assertEqual([], MutationController(store).list_pending())

        notes = (root / "NOTES.md").read_text(encoding="utf-8")
        self.assertNotIn(CLAIM, notes, "the normative claim is removed")
        self.assertIn("Historical and non-authoritative", notes)
        self.assertIn("Historical and non-authoritative", (root / "PLAN.md").read_text(encoding="utf-8"))
        for gone in (TRACKER_SKILL, "scripts/old_release.sh", "OLD_PROCESS.md"):
            with self.subTest(retired=gone):
                self.assertFalse(os.path.lexists(root / gone))

    def shadow_check(self, store: ProjectStore) -> None:
        """§33.10: the RB6 detector, narrow and read-only, finds no confirmed shadow and proves it."""
        root = store.root
        read: list[str] = []
        real = fsafe.SafeDirectory.read_file_bound

        def recording(directory, name):
            read.append(Path(os.path.relpath(os.path.join(directory.described, name), root)).as_posix())
            return real(directory, name)

        expected = sa.source_paths(root)
        with mock.patch.object(fsafe.SafeDirectory, "read_file_bound", recording):
            found = sa.detect_shadow_authority(root)
        self.assertEqual(list(expected), read, "the detector read exactly its v1 sources")
        self.assertEqual(set(expected), {BOOTSTRAP_REL_PATH, CALLER_SKILL, LINT_SKILL})
        for prose in NEVER_READ:
            with self.subTest(never_read=prose):
                self.assertNotIn(prose, read)
        self.assertEqual(found.confirmed, ())
        self.assertIs(found.bootstrap_inspected, True)
        self.assertIs(found.complete, True)
        self.assertEqual(found.evidence, (), "bootstrap, domain-lint and ask-workline are none")
        self.assertProvenNoShadow(found.to_json())

    def enter_carry(self, store: ProjectStore, phase_id: str) -> dict[str, str]:
        """The in-progress and the future obligation, with the legacy dependency between them and their authority."""
        design = rm.PhaseEntryDesign(
            {
                "csv": rm.WorkDesign(
                    "Finish the CSV export",
                    "The monthly report exports as CSV without the internal_id column (the parser part already exists)",
                    (RelatedSpec("must_read", "docs/domain/spec.md"), RelatedSpec("obey", "CONTRACT.md")),
                ),
                "summary": rm.WorkDesign(
                    "Add the summary page",
                    "Every monthly report has one summary page",
                    (RelatedSpec("must_read", "TODO.md"), RelatedSpec("obey", "CONTRACT.md")),
                ),
            },
            rm.WorkDesign("Integration", "The current obligations hold together"),
            requires_completion=(("csv", "summary"),),
        )
        result = rm.enter_phase(store, phase_id, design, review=Reviewer().review())
        self.assertEqual(result.status, "registered")
        found = work_ids_by_name(store, phase_id)
        return {"csv": found["Finish the CSV export"], "summary": found["Add the summary page"],
                "integration": found["Integration"]}

    def executor_writing(self, store: ProjectStore, relative: str, text: str):
        def execute(ctx):
            path = store.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
            return st.Completed((relative,))

        return execute

    def fresh_session_recovery(self, store: ProjectStore, roadmap_id: str, phase_id: str, carry: dict[str, str]) -> None:
        """§33.11: a new process, from canonical authority only, recovers the active state - and needs nothing retired.

        Absence of dependency, not an audit hook (RB8C-1): a byte copy of the Project with every retired legacy
        artifact deleted and committed answers exactly the same.
        """
        self.assertEqual([], MutationController(store).list_pending(), "between top-level operations (RB8C-9)")
        status, fresh = self.fresh_session(store.root, phase_id)

        self.assertEqual(status["snapshot_consistency"], "stable_read")
        configured = status["project"]["configured_workline_root"]
        self.assertTrue(os.path.samefile(configured["path"], WORKLINE_ROOT))
        self.assertTrue(os.path.samefile(fresh["configured_root"], WORKLINE_ROOT))
        lifecycle = status["lifecycle"]
        self.assertEqual(lifecycle["current"]["roadmap"]["id"], roadmap_id)
        self.assertEqual(lifecycle["current"]["phase"]["id"], phase_id)
        self.assertIsNone(lifecycle["current"]["work"]["id"])
        self.assertEqual(lifecycle["current"]["work"]["reason"], "no_work_in_flight")
        self.assertEqual(lifecycle["next"]["work"]["id"], carry["summary"])
        self.assertEqual(lifecycle["blockers"], [])
        self.assertEqual(status["validation"]["status"], "pass")
        self.assertEqual(status["policy"]["status"], "available")
        self.assertProvenNoShadow(status["policy"]["shadow_authority"])

        summary = fresh["obligations"][carry["summary"]]
        self.assertEqual(summary["requires"], [[carry["csv"], "completed"]], "the legacy dependency, satisfied")
        self.assertEqual(summary["related"], [["must_read", "TODO.md", True], ["obey", "CONTRACT.md", True]],
                         "the surviving domain and stricter safety authority")
        self.assertEqual(fresh["obligations"][carry["integration"]]["requires"],
                         sorted([[carry["csv"], "completed"], [carry["summary"], "unstarted"]]))

        recovered = self.tmp / "recovered"
        shutil.copytree(store.root, recovered, symlinks=True)
        retired = [path for path in ("NOTES.md", "PLAN.md", TRACKER_SKILL, "OLD_PROCESS.md", "scripts/old_release.sh")
                   if (recovered / path).exists()]
        self.assertEqual(retired, ["NOTES.md", "PLAN.md"], "the rest is already gone")
        git(recovered, "rm", "-q", "--", *retired)
        git(recovered, "commit", "-q", "-m", "drop the retired legacy authority")
        status_without, fresh_without = self.fresh_session(recovered, phase_id)
        for key in ("current", "next", "blockers"):
            with self.subTest(lifecycle=key):
                self.assertEqual(status_without["lifecycle"][key], lifecycle[key])
        self.assertEqual(fresh_without["obligations"], fresh["obligations"])
        self.assertEqual(status_without["validation"]["status"], "pass")
        self.assertProvenNoShadow(status_without["policy"]["shadow_authority"])

    def achieve(self, store: ProjectStore, roadmap_id: str) -> None:
        """§33.12: the Migration Roadmap closes through the ordinary RB5 achievement, nothing of its own."""
        review = ReviewStore(store)
        evidence = review.phase_completion_evidence()
        self.assertEqual(len(evidence), 2, "one current phase_completion evidence per reviewed Phase")
        with self.assertRaises(ValidationError):
            rm.evaluate_achievement(store, roadmap_id, "achieved")  # a reviewed Roadmap takes no legacy string
        decision = ach.RoadmapAchievementDecision(
            ach.JUDGEMENT_ACHIEVED, "migration-acceptance", "1",
            "Every current and future obligation is canonical Workline state and the legacy controller is retired.",
            tuple(sorted(item.achievement_evidence_id for item in evidence)),
        )
        result = rm.evaluate_achievement(store, roadmap_id, decision)
        self.assertEqual(result.status, "achieved")
        view = ProjectView.load(store)
        self.assertEqual([e.type for e in view.events_for(roadmap_id)], ["roadmap_achieved"])
        records = [review.read_achievement(found) for found in review.achievement_ids()]
        roadmap_records = [r.evidence for r in records if r.kind == ach.KIND_ROADMAP_ACHIEVEMENT]
        self.assertEqual(len(roadmap_records), 1)
        self.assertEqual(sorted(ref[1] for ref in roadmap_records[0].phase_evidence_refs),
                         sorted(item.achievement_evidence_id for item in evidence))
        self.assertEqual(roadmap_records[0].review_refs, (), "no pre-Project Review history is cited")
        self.assertEqual([], MutationController(store).list_pending())
        self.assertEqual(validate_project(store), [])

    def no_fabrication(self, store: ProjectStore, legacy_head: str, roadmap_id: str, phase_ids: tuple[str, ...]) -> None:
        """§33.6: no historical lifecycle, Review, Receipt, evidence or chronology; nothing private in canonical history."""
        root = store.root
        view = ProjectView.load(store)
        initial = git(root, "rev-list", "--reverse", f"{legacy_head}..HEAD").split()[0]
        self.assertEqual(git(root, "log", "-1", "--format=%s", initial).strip(), "chore(workline): initialize project")
        self.assertEqual(git(root, "show", f"{initial}:.workline/events/events.jsonl"), "",
                         "the cutover starts with an empty event log")
        self.assertEqual(git(root, "log", "--format=%H", legacy_head, "--", ".workline"), "",
                         "nothing was backfilled into the legacy history")
        self.assertEqual({e.type for e in view.events if e.type.startswith("phase_")}, set())
        entities = {roadmap_id, *phase_ids, *(w.id for p in phase_ids for w in view.phase_works(p))}
        self.assertEqual(set(view.works), entities - {roadmap_id, *phase_ids}, "every Work is a Migration Roadmap Work")
        for event in view.events:
            with self.subTest(event=event.id):
                self.assertIn(event.entity, entities)
        completed = [e.entity for e in view.events if e.type == "work_completed"]
        self.assertEqual(sorted(completed), sorted(view.works), "each Work completed once, by this migration")
        names = " ".join(w.name + " " + w.body for w in view.works.values())
        self.assertNotIn("importer", names, "already-finished legacy work is not backfilled")
        review = ReviewStore(store)
        runs: dict[str, list[str]] = {}
        for run_id in review.run_ids():
            first = review.gate_chain(run_id).generations[0]
            runs.setdefault(first.review_kind, []).append(first.target_identity)
        integrations = {w.id for p in phase_ids for w in view.integrations(p)}
        self.assertEqual(sorted(runs.pop(ri.REVIEW_KIND)), sorted(integrations), "one Run per migration integration")
        self.assertEqual(sum(len(found) for found in runs.values()), 2, "the two Phase entries, and no earlier Run")
        for path in sorted((root / ".workline").rglob("*")):
            relative = path.relative_to(root).as_posix()
            with self.subTest(canonical=relative):
                self.assertNotRegex(relative, r"(?i)migrat|legacy", "no migration namespace or record")
                if path.is_file():
                    self.assertNotIn(PRIVATE.encode("utf-8"), path.read_bytes())
        self.assertNotIn(PRIVATE, git(root, "log", "--format=%B", f"{legacy_head}..HEAD"))

    def preserved(self, store: ProjectStore, frozen: dict) -> None:
        """§33.7 / §33.8: B and C survive, and C is never weakened; D and E stay as non-authoritative history."""
        root = store.root
        for path in ("TODO.md", "docs/domain/spec.md", LINT_SKILL, CALLER_SKILL, "STATUS.md", "CHANGELOG.md"):
            with self.subTest(kept=path):
                self.assertEqual(_digest((root / path).read_bytes()), frozen["files"][path])
        contract = (root / "CONTRACT.md").read_bytes()
        self.assertTrue(contract.startswith(LEGACY["CONTRACT.md"].encode("utf-8")), "every existing safety rule is kept")
        self.assertIn(b"Exported files never contain the internal_id column.", contract, "the PLAN.md rule now lives in C")


if __name__ == "__main__":
    unittest.main()
