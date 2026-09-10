"""Post-project Skill discovery: Project-side bootstrap, router, backfill."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from helpers import WORKLINE_ROOT, WorklineTestCase, git
from workline import bootstrap as bs
from workline.errors import StopError
from workline.project_start import INITIAL_COMMIT_MESSAGE, project_start
from workline.registry import (
    CONTEXT_PRE_PROJECT,
    CONTEXT_PROJECT,
    CONTEXT_ROUTER,
    PROJECT_ROUTER_SKILL_ID,
    PROJECT_START_SKILL_ID,
    REQUIRED_RULE_IDS,
    REQUIRED_SKILL_IDS,
    SKILL_ID_PREFIX,
    resolve_skill,
    router_candidates,
    skill_inventory,
)
from workline.store import BOOTSTRAP_REL_PATH, ProjectStore
from workline.validate import validate_project

def _non_runtime_status(repo: Path) -> list[str]:
    """Porcelain status minus Workline runtime metadata, which is never committed."""
    lines = git(repo, "status", "--porcelain", "--untracked-files=all").splitlines()
    return [line for line in lines if ".workline/runtime/" not in line]


CANONICAL = (
    ".workline/project.yaml",
    ".workline/relations/roadmap.yaml",
    ".workline/relations/related.yaml",
    ".workline/events/events.jsonl",
)


class SyntheticRootMixin:
    """A throwaway Workline root whose registry can be extended at will.

    Used to prove that adding a Skill centrally needs no Project-side change.
    """

    def synthetic_root(self, name: str = "wl") -> Path:
        root = self.tmp / name
        root.mkdir(parents=True)
        self.write_registry(root)
        return root

    def _context_of(self, skill_id: str) -> str:
        if skill_id == PROJECT_START_SKILL_ID:
            return CONTEXT_PRE_PROJECT
        if skill_id == PROJECT_ROUTER_SKILL_ID:
            return CONTEXT_ROUTER
        return CONTEXT_PROJECT

    def write_registry(self, root: Path, extra: dict[str, str] | None = None) -> None:
        lines = ["# registry", ""]
        for rule_id in REQUIRED_RULE_IDS:
            lines += [f"<!-- workline-id: {rule_id} -->", ""]
        entries = {skill_id: self._context_of(skill_id) for skill_id in REQUIRED_SKILL_IDS}
        entries.update(extra or {})
        for skill_id, context in entries.items():
            target = f"{skill_id}/SKILL.md"
            lines += [
                f"<!-- workline-id: {skill_id} -->",
                f"<!-- workline-target: {target} -->",
                f"<!-- workline-context: {context} -->",
                "",
            ]
            path = root / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {skill_id}\n", encoding="utf-8")
        (root / "registry.md").write_text("\n".join(lines), encoding="utf-8")


class ProjectStartCreatesBootstrapTests(WorklineTestCase):
    """1, 2, 3: the bootstrap is created and the commit stays narrow."""

    def test_project_start_creates_the_bootstrap(self) -> None:
        root = self.new_dir()
        project_start(root, WORKLINE_ROOT)
        path = root / BOOTSTRAP_REL_PATH
        self.assertTrue(path.is_file(), path)
        self.assertEqual(path.read_text(encoding="utf-8"), bs.render_bootstrap())
        store = ProjectStore(root)
        self.assertEqual(bs.bootstrap_state(store), bs.MATCHING)
        self.assertTrue(bs.bootstrap_tracked(store))
        self.assertEqual(validate_project(store), [])

    def test_commit_scope_is_workline_plus_bootstrap_only(self) -> None:
        root = self.new_dir()
        git(root, "init", "-b", "main")
        (root / "tracked.txt").write_text("v1\n", encoding="utf-8")
        git(root, "add", "tracked.txt")
        git(root, "commit", "-m", "user commit")
        # pre-existing dirty state of every kind
        (root / "tracked.txt").write_text("v2 uncommitted\n", encoding="utf-8")
        (root / "untracked.txt").write_text("mine\n", encoding="utf-8")
        (root / "staged.txt").write_text("staged\n", encoding="utf-8")
        git(root, "add", "staged.txt")

        project_start(root, WORKLINE_ROOT)

        committed = set(git(root, "show", "--name-only", "--format=", "HEAD").split())
        self.assertEqual(committed, {*CANONICAL, BOOTSTRAP_REL_PATH})
        status = git(root, "status", "--porcelain", "--untracked-files=all")
        self.assertIn(" M tracked.txt", status)
        self.assertIn("?? untracked.txt", status)
        self.assertIn("A  staged.txt", status)
        self.assertEqual((root / "untracked.txt").read_text(encoding="utf-8"), "mine\n")

    def test_other_project_skills_are_untouched(self) -> None:
        root = self.new_dir()
        other = root / ".claude" / "skills" / "house-style" / "SKILL.md"
        other.parent.mkdir(parents=True)
        other.write_text("---\nname: house-style\n---\n\n# mine\n", encoding="utf-8")
        original = other.read_text(encoding="utf-8")

        project_start(root, WORKLINE_ROOT)

        self.assertEqual(other.read_text(encoding="utf-8"), original)
        committed = set(git(root, "show", "--name-only", "--format=", "HEAD").split())
        self.assertNotIn(".claude/skills/house-style/SKILL.md", committed)
        self.assertIn("?? .claude/skills/house-style/", git(root, "status", "--porcelain"))


class BootstrapConflictTests(WorklineTestCase):
    """4, 5: matching is idempotent; differing content STOPs."""

    def test_matching_bootstrap_is_not_recreated(self) -> None:
        root = self.new_dir()
        path = root / BOOTSTRAP_REL_PATH
        path.parent.mkdir(parents=True)
        path.write_text(bs.render_bootstrap(), encoding="utf-8")

        result = project_start(root, WORKLINE_ROOT)

        self.assertEqual(result.status, "initialized")
        self.assertEqual(path.read_text(encoding="utf-8"), bs.render_bootstrap())
        # committed exactly once, still the expected bootstrap
        committed = set(git(root, "show", "--name-only", "--format=", "HEAD").split())
        self.assertEqual(committed, {*CANONICAL, BOOTSTRAP_REL_PATH})
        self.assertEqual(bs.bootstrap_state(ProjectStore(root)), bs.MATCHING)

    def test_differing_bootstrap_stops_without_overwrite(self) -> None:
        root = self.new_dir()
        path = root / BOOTSTRAP_REL_PATH
        path.parent.mkdir(parents=True)
        path.write_text("# someone else owns this\n", encoding="utf-8")

        with self.assertRaises(StopError) as ctx:
            project_start(root, WORKLINE_ROOT)

        self.assertEqual(ctx.exception.code, "bootstrap_conflict")
        self.assertEqual(path.read_text(encoding="utf-8"), "# someone else owns this\n")
        self.assertFalse((root / ".workline").exists())

    def test_bootstrap_path_ignored_stops(self) -> None:
        root = self.new_dir()
        git(root, "init", "-b", "main")
        (root / ".gitignore").write_text(".claude/\n", encoding="utf-8")
        git(root, "add", ".gitignore")
        git(root, "commit", "-m", "ignore claude dir")

        with self.assertRaises(StopError) as ctx:
            project_start(root, WORKLINE_ROOT)

        self.assertEqual(ctx.exception.code, "bootstrap_path_ignored")
        self.assertFalse((root / BOOTSTRAP_REL_PATH).exists())


class BootstrapContentTests(unittest.TestCase):
    """6, 7: the bootstrap embeds no root path and no Skill inventory."""

    def test_bootstrap_holds_no_workline_root_path(self) -> None:
        text = bs.render_bootstrap()
        self.assertNotIn(str(WORKLINE_ROOT), text)
        self.assertNotIn(WORKLINE_ROOT.as_posix(), text)
        # no absolute path of any shape (drive letter, UNC or POSIX root)
        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", text))
        self.assertNotIn("\\\\", text)
        # the root is resolved from the Project instead
        self.assertIn(".workline/project.yaml", text)

    def test_bootstrap_knows_only_the_router_skill_id(self) -> None:
        text = bs.render_bootstrap()
        mentioned = set(re.findall(r"skills/[a-z0-9-]+", text))
        self.assertEqual(mentioned, {PROJECT_ROUTER_SKILL_ID})
        # and no name -> id routing table
        self.assertNotIn("->", text)
        self.assertNotIn("=>", text)

    def test_bootstrap_is_discoverable_as_a_claude_skill(self) -> None:
        text = bs.render_bootstrap()
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---")[1]
        self.assertIn(f"name: {bs.BOOTSTRAP_SKILL_NAME}", frontmatter)
        self.assertIn("description:", frontmatter)
        self.assertEqual(BOOTSTRAP_REL_PATH, ".claude/skills/workline/SKILL.md")


class DynamicDiscoveryTests(WorklineTestCase, SyntheticRootMixin):
    """8, 9, 11, 12: the inventory is read from the registry every time."""

    def test_inventory_comes_from_the_registry(self) -> None:
        root = self.synthetic_root()
        text = (root / "registry.md").read_text(encoding="utf-8")
        registered = set(re.findall(r"<!-- workline-id: (skills/[a-z0-9-]+) -->", text))
        self.assertEqual(set(skill_inventory(root)), registered)

    def test_new_central_skill_needs_no_project_change(self) -> None:
        """The most important guarantee of this design."""
        wl = self.synthetic_root()
        project = self.new_dir("proj")
        project_start(project, wl)
        bootstrap = project / BOOTSTRAP_REL_PATH
        before_bytes = bootstrap.read_bytes()
        before_head = git(project, "rev-parse", "HEAD").strip()
        self.assertNotIn("skills/review", skill_inventory(wl))

        # a Skill is added centrally, and only centrally
        self.write_registry(wl, extra={"skills/review": CONTEXT_PROJECT})

        self.assertIn("skills/review", skill_inventory(wl))
        self.assertIn("skills/review", router_candidates(wl))
        self.assertEqual(resolve_skill(wl, "skills/review").context, CONTEXT_PROJECT)
        # the Project did not change by a single byte
        self.assertEqual(bootstrap.read_bytes(), before_bytes)
        self.assertEqual(git(project, "rev-parse", "HEAD").strip(), before_head)
        self.assertEqual(_non_runtime_status(project), [])

    def test_router_never_routes_to_itself(self) -> None:
        root = self.synthetic_root()
        self.assertEqual(skill_inventory(root)[PROJECT_ROUTER_SKILL_ID].context, CONTEXT_ROUTER)
        self.assertNotIn(PROJECT_ROUTER_SKILL_ID, router_candidates(root))

    def test_established_project_never_routes_to_project_start(self) -> None:
        root = self.synthetic_root()
        self.assertEqual(skill_inventory(root)[PROJECT_START_SKILL_ID].context, CONTEXT_PRE_PROJECT)
        self.assertNotIn(PROJECT_START_SKILL_ID, router_candidates(root))
        # exclusion is structural, not a hard-coded name list
        for skill_id, entry in skill_inventory(root).items():
            with self.subTest(skill=skill_id):
                self.assertEqual(entry.selectable_in_project, entry.context == CONTEXT_PROJECT)

    def test_a_pre_project_skill_added_later_is_still_excluded(self) -> None:
        root = self.synthetic_root()
        self.write_registry(root, extra={"skills/import-legacy": CONTEXT_PRE_PROJECT})
        self.assertIn("skills/import-legacy", skill_inventory(root))
        self.assertNotIn("skills/import-legacy", router_candidates(root))

    def test_real_repository_router_candidates(self) -> None:
        candidates = router_candidates(WORKLINE_ROOT)
        self.assertNotIn(PROJECT_START_SKILL_ID, candidates)
        self.assertNotIn(PROJECT_ROUTER_SKILL_ID, candidates)
        self.assertIn("skills/roadmap", candidates)
        self.assertIn("skills/start", candidates)


class BrokenRoutingTests(WorklineTestCase, SyntheticRootMixin):
    """10: broken authority stops; it never degrades into a guess."""

    def test_missing_registry_stops(self) -> None:
        root = self.synthetic_root()
        (root / "registry.md").unlink()
        with self.assertRaises(StopError) as ctx:
            skill_inventory(root)
        self.assertEqual(ctx.exception.code, "registry_invalid")

    def test_duplicate_skill_id_stops(self) -> None:
        root = self.synthetic_root()
        registry = root / "registry.md"
        registry.write_text(
            registry.read_text(encoding="utf-8")
            + f"\n<!-- workline-id: {PROJECT_ROUTER_SKILL_ID} -->\n"
            f"<!-- workline-target: {PROJECT_ROUTER_SKILL_ID}/SKILL.md -->\n"
            f"<!-- workline-context: {CONTEXT_ROUTER} -->\n",
            encoding="utf-8",
        )
        with self.assertRaises(StopError) as ctx:
            skill_inventory(root)
        self.assertEqual(ctx.exception.code, "registry_invalid")

    def test_broken_target_stops(self) -> None:
        root = self.synthetic_root()
        (root / PROJECT_ROUTER_SKILL_ID / "SKILL.md").unlink()
        with self.assertRaises(StopError) as ctx:
            skill_inventory(root)
        self.assertEqual(ctx.exception.code, "registry_invalid")

    def test_missing_context_stops(self) -> None:
        root = self.synthetic_root()
        registry = root / "registry.md"
        registry.write_text(
            registry.read_text(encoding="utf-8").replace(
                f"<!-- workline-context: {CONTEXT_ROUTER} -->", ""
            ),
            encoding="utf-8",
        )
        with self.assertRaises(StopError) as ctx:
            skill_inventory(root)
        self.assertEqual(ctx.exception.code, "registry_invalid")

    def test_unregistered_skill_id_has_no_fallback(self) -> None:
        root = self.synthetic_root()
        with self.assertRaises(StopError) as ctx:
            resolve_skill(root, "skills/roadmpa")  # near-miss of skills/roadmap
        self.assertEqual(ctx.exception.code, "routing_error")

    def test_every_registered_skill_is_validated_not_just_required(self) -> None:
        root = self.synthetic_root()
        self.write_registry(root, extra={"skills/review": CONTEXT_PROJECT})
        (root / "skills/review/SKILL.md").unlink()
        with self.assertRaises(StopError) as ctx:
            skill_inventory(root)
        self.assertEqual(ctx.exception.code, "registry_invalid")


class BackfillTests(WorklineTestCase):
    """13, 14, 15: backfill adds one file and nothing else."""

    def _legacy_project(self, *, remote: bool = False) -> ProjectStore:
        """A Project as the previous ProjectSTART left it: no bootstrap."""
        store = self.new_project(remote=remote)
        git(store.root, "rm", "-q", "--cached", BOOTSTRAP_REL_PATH)
        (store.root / BOOTSTRAP_REL_PATH).unlink()
        git(store.root, "commit", "-m", "legacy project without bootstrap")
        if remote:
            git(store.root, "push", "-u", "origin", "main")
        self.assertEqual(bs.bootstrap_state(store), bs.ABSENT)
        return store

    def _domain_snapshot(self, store: ProjectStore) -> dict[str, str]:
        snapshot = {p: (store.root / p).read_text(encoding="utf-8") for p in CANONICAL}
        for entity in sorted(store.workline.rglob("*.md")):
            snapshot[entity.relative_to(store.root).as_posix()] = entity.read_text(encoding="utf-8")
        return snapshot

    def test_backfill_adds_only_the_bootstrap(self) -> None:
        store = self._legacy_project()
        roadmap = self.simple_roadmap(store)
        before = self._domain_snapshot(store)
        before_head = git(store.root, "rev-parse", "HEAD").strip()

        result = bs.backfill_bootstrap(store.root)

        self.assertEqual(result.status, "created")
        self.assertFalse(result.pushed)  # no remote
        self.assertEqual(bs.bootstrap_state(store), bs.MATCHING)
        self.assertTrue(bs.bootstrap_tracked(store))
        # exactly one new commit, touching exactly one path
        self.assertEqual(
            git(store.root, "log", "--format=%s", f"{before_head}..HEAD").splitlines(),
            [bs.BACKFILL_COMMIT_MESSAGE],
        )
        self.assertEqual(
            set(git(store.root, "show", "--name-only", "--format=", "HEAD").split()),
            {BOOTSTRAP_REL_PATH},
        )
        # canonical domain state is byte-identical and the Roadmap still resolves
        self.assertEqual(self._domain_snapshot(store), before)
        self.assertEqual(validate_project(store), [])
        self.assertIn(roadmap.roadmap_id, {p.stem for p in (store.workline / "roadmaps").iterdir()})

    def test_backfill_is_idempotent(self) -> None:
        store = self._legacy_project()
        first = bs.backfill_bootstrap(store.root)
        head = git(store.root, "rev-parse", "HEAD").strip()

        second = bs.backfill_bootstrap(store.root)

        self.assertEqual(first.status, "created")
        self.assertEqual(second.status, "already_present")
        self.assertIsNone(second.mutation_id)
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(_non_runtime_status(store.root), [])

    def test_backfill_conflict_stops(self) -> None:
        store = self._legacy_project()
        path = store.root / BOOTSTRAP_REL_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# not ours\n", encoding="utf-8")
        head = git(store.root, "rev-parse", "HEAD").strip()

        with self.assertRaises(StopError) as ctx:
            bs.backfill_bootstrap(store.root)

        self.assertEqual(ctx.exception.code, "bootstrap_conflict")
        self.assertEqual(path.read_text(encoding="utf-8"), "# not ours\n")
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), head)

    def test_backfill_pushes_when_a_remote_exists(self) -> None:
        store = self._legacy_project(remote=True)

        result = bs.backfill_bootstrap(store.root)

        self.assertEqual(result.status, "created")
        self.assertTrue(result.pushed)
        local = git(store.root, "rev-parse", "HEAD").strip()
        remote = git(self.remote_path(), "rev-parse", "main").strip()
        self.assertEqual(local, remote)

    def test_backfill_leaves_other_skills_alone(self) -> None:
        store = self._legacy_project()
        other = store.root / ".claude" / "skills" / "house-style" / "SKILL.md"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text("# mine\n", encoding="utf-8")

        bs.backfill_bootstrap(store.root)

        self.assertEqual(other.read_text(encoding="utf-8"), "# mine\n")
        self.assertEqual(
            set(git(store.root, "show", "--name-only", "--format=", "HEAD").split()),
            {BOOTSTRAP_REL_PATH},
        )

    def test_backfill_refuses_a_non_project(self) -> None:
        root = self.new_dir("plain")
        git(root, "init", "-b", "main")
        (root / "a.txt").write_text("a\n", encoding="utf-8")
        git(root, "add", "a.txt")
        git(root, "commit", "-m", "not a workline project")

        with self.assertRaises(StopError) as ctx:
            bs.backfill_bootstrap(root)

        self.assertEqual(ctx.exception.code, "not_a_project")
        self.assertFalse((root / BOOTSTRAP_REL_PATH).exists())
        self.assertFalse((root / ".workline").exists())

    def test_backfill_does_not_initialize_a_broken_project(self) -> None:
        store = self._legacy_project()
        store.project_yaml.unlink()
        with self.assertRaises(StopError) as ctx:
            bs.backfill_bootstrap(store.root)
        self.assertEqual(ctx.exception.code, "not_a_project")
        self.assertFalse((store.root / BOOTSTRAP_REL_PATH).exists())


class CanonicalRouterSkillTests(unittest.TestCase):
    """The router exists where Claude Code and the registry both expect it."""

    REPO_ROOT = Path(__file__).resolve().parents[1]

    def test_router_skill_file_exists(self) -> None:
        skill = self.REPO_ROOT / ".claude" / "skills" / "project-router" / "SKILL.md"
        self.assertTrue(skill.is_file(), skill)
        text = skill.read_text(encoding="utf-8")
        self.assertIn(".workline/project.yaml", text.split("---")[1])

    def test_router_declares_no_fixed_skill_inventory(self) -> None:
        skill = self.REPO_ROOT / ".claude" / "skills" / "project-router" / "SKILL.md"
        mentioned = set(re.findall(r"skills/[a-z0-9-]+", skill.read_text(encoding="utf-8")))
        self.assertEqual(mentioned - {PROJECT_ROUTER_SKILL_ID}, set())

    def test_registry_declares_a_context_for_every_skill(self) -> None:
        text = (self.REPO_ROOT / "registry.md").read_text(encoding="utf-8")
        ids = re.findall(r"<!-- workline-id: (skills/[a-z0-9-]+) -->", text)
        self.assertEqual(len(ids), len(set(ids)))
        inventory = skill_inventory(self.REPO_ROOT)
        self.assertEqual(set(ids), set(inventory))
        for skill_id in ids:
            self.assertTrue(skill_id.startswith(SKILL_ID_PREFIX))

    def test_authority_statement_is_not_a_fixed_skill_count(self) -> None:
        text = (self.REPO_ROOT / "registry.md").read_text(encoding="utf-8")
        self.assertNotIn("5 `SKILL.md`", text)
        self.assertIn("registry-routed canonical Skills", text)


if __name__ == "__main__":
    unittest.main()
