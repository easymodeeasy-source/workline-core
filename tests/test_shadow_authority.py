"""BL-055 shadow-authority detector (RB6 §30.26-§30.28, focused tests §30.39; contract §15.1-§15.7, §15.27).

The detector is read-only and advisory. It reads exactly three v1 sources - the
exact Project bootstrap path, ``.claude/skills/**/SKILL.md`` and structured
observations handed in by canonical router / owner code - and classifies them
``none`` / ``suspected`` / ``confirmed``. Filename and vocabulary never confirm,
indirection is identified without being followed, and nothing is ever written.

Two §30.39 bullets - "shadow advisory does not fail validation" and "no
ProjectSTART change" - are covered here as far as the leaf reaches; the part
that needs the shared validate-project / status / router integration (RB6-F)
is written now and skipped as ``WAIT_SHARED_INTEGRATION`` with the exact
assertion it will make.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, WorklineTestCase, git, launcher_command, run_python
from workline import bootstrap as bs
from workline import shadow_authority as sa
from workline.registry import REQUIRED_RULE_IDS, REQUIRED_SKILL_IDS
from workline.review import fsafe
from workline.store import BOOTSTRAP_REL_PATH, ProjectStore
from workline.validate import validate_project

WINDOWS = sys.platform == "win32"
WAIT_IR1 = "WAIT_SHARED_INTEGRATION: RB6A-IR-1 (validate-project advisory display, cli.py)"
WAIT_IR2 = "WAIT_SHARED_INTEGRATION: RB6A-IR-2 (RB1 status policy section shadow fields, status.py)"
WAIT_IR3 = "WAIT_SHARED_INTEGRATION: RB6A-IR-3 (project-router Skill text, §30.29)"

CLAIMING_SKILL = """---
name: tracker
description: Keeps the Project's own task list.
---

# Tracker

This Skill records Workline Work completion in TODO.md.
This Skill decides the next Workline Work from BACKLOG.md.
TODO.md overrides .workline state.
"""

DOMAIN_SKILL = """---
name: deploy
description: Build and deploy the web application.
---

# Deploy

Phase 1: build the bundle. Phase 2: upload it.
Mark the release done in the release notes when the upload finishes.
The deployment runbook is the source of truth for server names.
"""

DELEGATING_SKILL = """---
name: plan-helper
description: Helps the user phrase a planning request and hands it to Workline.
---

# Plan helper

This Skill keeps no Workline state.
It hands every Workline request to the canonical project-router through the Project bootstrap.
For current or next Work it runs the canonical read-only status: py -3 -I -B "<R>/run-workline.py" status <project-root>.
"""

WORDS_ONLY_SKILL = """---
name: glossary
description: Workline Roadmap Phase Work START lifecycle progression.
---

Workline Roadmap Phase Work START lifecycle progression current next Review registry router.
Workline の Roadmap / Phase / Work / 完了 / 次 / 現在地。
"""

# --------------------------------------------------------------------------- filesystem helpers


def make_junction(link: Path, target: Path) -> bool:
    """A junction at ``link`` -> ``target``, made in place without privilege (the ``review_attack`` technique)."""
    from review_attack import set_mount_point

    link.mkdir(parents=True)
    if set_mount_point(link, target) == "converted":
        return True
    link.rmdir()
    return False


def try_symlink(link: Path, target: Path, directory: bool) -> bool:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=directory)
        return True
    except (OSError, NotImplementedError):  # WinError 1314 without the symlink privilege
        return False


def is_indirection(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def snapshot(root: Path) -> list[tuple]:
    """Every entry under ``root`` but ``.git`` - kind, size, mtime, content digest - listed without following anything.

    ``.git`` is compared through Git itself (status, HEAD): ``git status`` may refresh its own index.
    """
    found: list[tuple] = []

    def visit(path: Path, relative: str) -> None:
        if relative == "./.git":
            return
        info = os.lstat(path)
        if is_indirection(info):
            found.append((relative, "indirection", getattr(info, "st_reparse_tag", 0), info.st_mtime_ns))
            return
        if stat.S_ISDIR(info.st_mode):
            found.append((relative, "directory", info.st_mtime_ns))
            for name in sorted(os.listdir(path)):
                visit(path / name, f"{relative}/{name}")
            return
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else None
        found.append((relative, "file", info.st_size, info.st_mtime_ns, digest))

    visit(root, ".")
    return found


_AUDITED: list[str] | None = None
_AUDIT_INSTALLED = False


def _audit(event: str, args: tuple) -> None:
    if _AUDITED is not None and event == "open" and args:
        target = args[0]
        _AUDITED.append(os.fsdecode(target) if isinstance(target, (str, bytes, os.PathLike)) else repr(target))


class ShadowCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.new_dir("proj")
        self.outside = self.new_dir("outside")

    def link_cleanup(self, link: Path) -> None:
        """Remove the indirection itself - never what it points at - before the temp tree goes."""

        def remove() -> None:
            if os.path.islink(link):
                os.unlink(link)
            elif os.path.lexists(link):
                os.rmdir(link)  # a junction: removes the mount point, not its target

        self.addCleanup(remove)

    def junction(self, relative: str, target: Path) -> Path:
        if not WINDOWS:
            self.skipTest("junctions are a Windows reparse point")
        link = self.root / relative
        if not make_junction(link, target):
            self.skipTest("cannot create a junction here")
        self.link_cleanup(link)
        return link

    def symlink(self, relative: str, target: Path, *, directory: bool) -> Path:
        link = self.root / relative
        if not try_symlink(link, target, directory):
            self.skipTest("cannot create a symlink here (WinError 1314 without the symlink privilege)")
        self.link_cleanup(link)
        return link

    def write(self, relative: str, data: str | bytes, root: Path | None = None) -> Path:
        path = (root or self.root) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
        return path

    def canonical_bootstrap(self, root: Path | None = None, *, crlf: bool = False) -> Path:
        text = bs.render_bootstrap()
        return self.write(BOOTSTRAP_REL_PATH, text.replace("\n", "\r\n") if crlf else text, root)

    def skill(self, name: str, text: str) -> str:
        relative = f".claude/skills/{name}/SKILL.md"
        self.write(relative, text)
        return relative

    def detect(self, root: Path | None = None, **kwargs) -> sa.ShadowDiagnostic:
        return sa.detect_shadow_authority(root or self.root, **kwargs)

    def assert_none(self, found: sa.ShadowDiagnostic) -> None:
        self.assertEqual(sa.NONE, found.status)
        self.assertEqual((), found.evidence)
        self.assertEqual((), found.confirmed)

    def rules(self, found: sa.ShadowDiagnostic) -> set[tuple[str, str]]:
        return {(item.path, item.rule) for item in found.evidence}


# --------------------------------------------------------------------------- §30.39: prose and filenames


class ProseIsNotASourceTests(ShadowCase):
    """README/BACKLOG/TODO/STATUS filename alone -> none; domain spec/CONTRACT -> none (§30.39, §15.2, §30.26)."""

    PROSE = (
        "README.md", "BACKLOG.md", "TODO.md", "STATUS.md", "CLAUDE.md", "ROADMAP.md",
        "docs/BACKLOG.md", ".claude/BACKLOG.md", ".claude/skills/TODO.md",
    )

    def test_readme_backlog_todo_status_files_are_never_sources(self) -> None:
        self.canonical_bootstrap()
        for name in self.PROSE:
            self.write(name, "This file is the authoritative Workline state and overrides .workline.\n"
                             "It records Workline Work completion and decides the next Workline Work.\n")
        found = self.detect()
        self.assert_none(found)
        self.assertEqual((), found.uninspected)
        self.assertEqual((BOOTSTRAP_REL_PATH,), sa.source_paths(self.root))

    def test_a_skill_named_like_a_tracker_is_none_by_name_alone(self) -> None:
        self.canonical_bootstrap()
        for name in ("backlog", "todo", "status", "roadmap", "start", "review", "BACKLOG"):
            self.skill(name, f"---\nname: {name}\ndescription: Formats the team's notes.\n---\n\nFormat the notes.\n")
        self.assert_none(self.detect())

    def test_domain_spec_and_contract_documents_are_none(self) -> None:
        self.canonical_bootstrap()
        self.write("CONTRACT.md", "Stricter safety: never push on Friday. This contract overrides Workline defaults "
                                  "for deployment safety, and the next Workline Work must keep it.\n")
        self.write("docs/spec.md", "Phase 1 builds the API. The spec is the source of truth for the next task.\n")
        self.write("config/domain.yaml", "workline: true\nnext_task: deploy\n")
        self.skill("deploy", DOMAIN_SKILL)
        self.assert_none(self.detect())

    def test_no_forbidden_filename_list_exists(self) -> None:
        source = Path(sa.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        for name in ("README", "README.md", "BACKLOG", "BACKLOG.md", "TODO", "TODO.md", "STATUS", "STATUS.md",
                     "CLAUDE.md", "ROADMAP.md"):
            with self.subTest(name=name):
                self.assertNotIn(name, literals, "the detector keeps no filename list")


# --------------------------------------------------------------------------- §30.39: the bootstrap


class BootstrapRuleTests(ShadowCase):
    def test_bootstrap_absent_is_no_evidence(self) -> None:
        self.assert_none(self.detect())
        (self.root / ".claude" / "skills" / "workline").mkdir(parents=True)
        self.assert_none(self.detect())
        self.assertEqual((), sa.source_paths(self.root))

    def test_a_non_directory_ancestor_leaves_the_bootstrap_absent(self) -> None:
        self.write(".claude", "not a directory\n")
        self.assert_none(self.detect())
        self.assertEqual(bs.ABSENT, bs.bootstrap_state(ProjectStore(self.root)))

    def test_canonical_bootstrap_is_none(self) -> None:
        for crlf in (False, True):
            with self.subTest(crlf=crlf):
                self.canonical_bootstrap(crlf=crlf)
                found = self.detect()
                self.assert_none(found)
                self.assertEqual((), found.uninspected)
                self.assertEqual((BOOTSTRAP_REL_PATH,), sa.source_paths(self.root))

    def test_the_canonical_identity_is_bootstrap_state_s_own(self) -> None:
        """For every ordinary file: none exactly when ``bootstrap_state`` says matching (imported, not restated)."""
        text = bs.render_bootstrap()
        variants = {
            "lf": text.encode("utf-8"),
            "crlf": text.replace("\n", "\r\n").encode("utf-8"),
            "mixed": text.replace("\n", "\r\n", 3).encode("utf-8"),
            "lone_cr": text.replace("\n", "\r").encode("utf-8"),
            "bom": b"\xef\xbb\xbf" + text.encode("utf-8"),
            "no_final_newline": text.rstrip("\n").encode("utf-8"),
            "extra_final_newline": (text + "\n").encode("utf-8"),
            "one_character": text.replace("canonical router", "canonical rooter", 1).encode("utf-8"),
            "empty": b"",
            "not_utf8": text.encode("utf-8") + b"\xff",
            "utf16": text.encode("utf-16"),
        }
        store = ProjectStore(self.root)
        for name, data in variants.items():
            with self.subTest(variant=name):
                self.write(BOOTSTRAP_REL_PATH, data)
                found = self.detect()
                if bs.bootstrap_state(store) == bs.MATCHING:
                    self.assert_none(found)
                else:
                    self.assertEqual(bs.CONFLICT, bs.bootstrap_state(store))
                    self.assertEqual(sa.SUSPECTED, found.status)
                    self.assertEqual({(BOOTSTRAP_REL_PATH, sa.RULE_BOOTSTRAP_DIFFERS)}, self.rules(found))
        self.assertTrue(variants["lf"] and variants["crlf"])

    def test_differing_regular_bootstrap_is_suspected(self) -> None:
        data = bs.render_bootstrap().replace("skills/project-router", "skills/my-router").encode("utf-8")
        self.write(BOOTSTRAP_REL_PATH, data)
        found = self.detect()
        self.assertEqual(sa.SUSPECTED, found.status)
        self.assertEqual((), found.confirmed)
        (item,) = found.evidence
        self.assertEqual(
            sa.ShadowEvidence(
                sa.SUSPECTED, sa.SOURCE_BOOTSTRAP, BOOTSTRAP_REL_PATH, sa.RULE_BOOTSTRAP_DIFFERS, sa.ROUTING_BOOTSTRAP,
                ("skills/project-start", "skills/project-router"), digest=hashlib.sha256(data).hexdigest(),
            ),
            item,
        )
        self.assertEqual((item,), found.suspected)

    def test_the_bootstrap_is_classified_only_by_the_bootstrap_rule(self) -> None:
        """RB8-FC-02: it matches .claude/skills/**/SKILL.md, but is never fed to the Skill text rule."""
        calls: list[str] = []
        real = sa.skill_text_claims

        def recording(text: str):
            calls.append(text)
            return real(text)

        with mock.patch.object(sa, "skill_text_claims", recording):
            self.canonical_bootstrap()
            self.assert_none(self.detect())
            self.write(BOOTSTRAP_REL_PATH, CLAIMING_SKILL)
            found = self.detect()
        self.assertEqual([], calls, "the bootstrap's text never reaches the Skill rule")
        self.assertEqual({(BOOTSTRAP_REL_PATH, sa.RULE_BOOTSTRAP_DIFFERS)}, self.rules(found))
        self.assertEqual(sa.SUSPECTED, found.status)

    def test_a_directory_at_the_bootstrap_path_is_suspected_and_not_read(self) -> None:
        (self.root / BOOTSTRAP_REL_PATH).mkdir(parents=True)
        found = self.detect()
        self.assertEqual(sa.SUSPECTED, found.status)
        self.assertEqual({(BOOTSTRAP_REL_PATH, sa.RULE_BOOTSTRAP_NOT_REGULAR_FILE)}, self.rules(found))
        self.assertEqual((), sa.source_paths(self.root))

    def test_an_oversized_bootstrap_differs_without_being_read(self) -> None:
        self.write(BOOTSTRAP_REL_PATH, b"x" * (sa.MAX_FILE_BYTES + 1))
        self.assertLess(len(bs.render_bootstrap().encode("utf-8")) * 4, sa.MAX_FILE_BYTES)
        found = self.detect()
        (item,) = found.evidence
        self.assertEqual((sa.SUSPECTED, sa.RULE_BOOTSTRAP_DIFFERS, None), (item.level, item.rule, item.digest))
        self.assertEqual((), sa.source_paths(self.root))

    # indirection: confirmed, never followed -----------------------------------
    def _assert_indirection(self, found: sa.ShadowDiagnostic, component: str, kinds: tuple[str, ...]) -> None:
        self.assertEqual(sa.CONFIRMED, found.status)
        (item,) = found.evidence
        self.assertEqual(found.confirmed, (item,))
        self.assertEqual(
            (sa.CONFIRMED, sa.SOURCE_BOOTSTRAP, BOOTSTRAP_REL_PATH, sa.RULE_BOOTSTRAP_INDIRECTION, sa.ROUTING_BOOTSTRAP),
            (item.level, item.source, item.path, item.rule, item.responsibility),
        )
        self.assertEqual(component, item.component)
        self.assertIn(item.indirection, kinds)
        self.assertIsNone(item.digest, "an indirection is never read")
        self.assertNotIn(BOOTSTRAP_REL_PATH, sa.source_paths(self.root))

    def test_a_junction_replacing_the_bootstrap_directory_is_confirmed_and_not_followed(self) -> None:
        target = self.outside / "workline"
        target.mkdir()
        self.write("SKILL.md", bs.render_bootstrap(), target)  # exactly canonical at the junction's target
        self.write("extra/SKILL.md", CLAIMING_SKILL, target)
        self.junction(".claude/skills/workline", target)
        found = self.detect()
        self._assert_indirection(found, ".claude/skills/workline", (sa.INDIRECTION_JUNCTION,))
        self.assertEqual((), found.uninspected, "the bootstrap's own indirection is reported once, as evidence")

    def test_a_junction_at_any_bootstrap_ancestor_is_confirmed(self) -> None:
        for component in (".claude", ".claude/skills"):
            with self.subTest(component=component):
                target = self.new_dir(f"elsewhere-{component.count('/')}")
                inner = BOOTSTRAP_REL_PATH[len(component) + 1:]
                self.write(inner, bs.render_bootstrap(), target)
                link = self.junction(component, target)
                self._assert_indirection(self.detect(), component, (sa.INDIRECTION_JUNCTION,))
                os.rmdir(link)

    def test_a_symlinked_bootstrap_file_is_confirmed_even_when_its_target_is_canonical(self) -> None:
        target = self.write("canonical-copy.md", bs.render_bootstrap(), self.outside)
        self.symlink(BOOTSTRAP_REL_PATH, target, directory=False)
        self._assert_indirection(self.detect(), BOOTSTRAP_REL_PATH, (sa.INDIRECTION_SYMLINK,))

    def test_a_dangling_bootstrap_symlink_is_confirmed(self) -> None:
        self.symlink(BOOTSTRAP_REL_PATH, self.outside / "missing.md", directory=False)
        self._assert_indirection(self.detect(), BOOTSTRAP_REL_PATH, (sa.INDIRECTION_SYMLINK,))

    def test_a_symlinked_bootstrap_directory_is_confirmed(self) -> None:
        self.write("SKILL.md", bs.render_bootstrap(), self.outside)
        self.symlink(".claude/skills/workline", self.outside, directory=True)
        self._assert_indirection(self.detect(), ".claude/skills/workline", (sa.INDIRECTION_SYMLINK,))


# --------------------------------------------------------------------------- §30.39: local Skills


class LocalSkillRuleTests(ShadowCase):
    def setUp(self) -> None:
        super().setUp()
        self.canonical_bootstrap()

    def test_a_distinct_domain_skill_is_none(self) -> None:
        """RB8-FC-03(a)."""
        self.skill("deploy", DOMAIN_SKILL)
        self.assert_none(self.detect())

    def test_a_skill_that_only_calls_the_canonical_owner_is_allowed(self) -> None:
        """§30.39 "local Skill calling canonical owner -> allowed"; RB8-FC-03(b)."""
        self.skill("plan-helper", DELEGATING_SKILL)
        self.skill("entry-copy", bs.render_bootstrap())  # the bootstrap's own text, elsewhere: it only delegates
        found = self.detect()
        self.assert_none(found)
        self.assertEqual(
            (BOOTSTRAP_REL_PATH, ".claude/skills/entry-copy/SKILL.md", ".claude/skills/plan-helper/SKILL.md"),
            sa.source_paths(self.root),
        )

    def test_workline_words_alone_cannot_confirm(self) -> None:
        self.skill("glossary", WORDS_ONLY_SKILL)
        self.assert_none(self.detect())
        for index in range(5):
            self.skill(f"tracker-{index}", CLAIMING_SKILL)
        found = self.detect()
        self.assertEqual(sa.SUSPECTED, found.status)
        self.assertEqual((), found.confirmed)
        self.assertTrue(all(item.level == sa.SUSPECTED for item in found.evidence))

    def test_a_parallel_state_claim_without_execution_evidence_is_at_most_suspected(self) -> None:
        """§30.39; RB8-FC-03(c): by rule ID, never confirmed from static text alone."""
        relative = self.skill("tracker", CLAIMING_SKILL)
        found = self.detect()
        self.assertEqual(sa.SUSPECTED, found.status)
        self.assertEqual(
            {(relative, sa.RULE_SKILL_PARALLEL_LIFECYCLE), (relative, sa.RULE_SKILL_PARALLEL_PROGRESSION),
             (relative, sa.RULE_SKILL_AUTHORITY_OVERRIDE)},
            self.rules(found),
        )
        by_rule = {item.rule: item for item in found.evidence}
        self.assertEqual(sa.LIFECYCLE_STATE, by_rule[sa.RULE_SKILL_PARALLEL_LIFECYCLE].responsibility)
        self.assertEqual(sa.PROGRESSION, by_rule[sa.RULE_SKILL_PARALLEL_PROGRESSION].responsibility)
        self.assertEqual(sa.LIFECYCLE_STATE, by_rule[sa.RULE_SKILL_AUTHORITY_OVERRIDE].responsibility)
        self.assertEqual((8, 9, 10), tuple(by_rule[rule].line for rule in (
            sa.RULE_SKILL_PARALLEL_LIFECYCLE, sa.RULE_SKILL_PARALLEL_PROGRESSION, sa.RULE_SKILL_AUTHORITY_OVERRIDE)))
        digest = hashlib.sha256(CLAIMING_SKILL.encode("utf-8")).hexdigest()
        for item in found.evidence:
            self.assertEqual((sa.SOURCE_LOCAL_SKILL, digest), (item.source, item.digest))
            self.assertEqual(sa.RESPONSIBILITY_OWNERS[item.responsibility], item.canonical_owner)

    def test_the_rb8_example_claim_is_suspected_by_rule_id(self) -> None:
        """RB8-FC-03(c): "this TODO file is the authoritative next task; mark items done"."""
        relative = self.skill("todo", "---\nname: todo\ndescription: Task list.\n---\n\n"
                                      "This TODO file is the authoritative next task; mark items done.\n")
        found = self.detect()
        self.assertEqual({(relative, sa.RULE_SKILL_AUTHORITY_OVERRIDE)}, self.rules(found))
        self.assertEqual(sa.PROGRESSION, found.evidence[0].responsibility)
        self.assertEqual(sa.SUSPECTED, found.status)

    def test_claims_in_japanese_are_read_and_denials_are_not_claims(self) -> None:
        claims = self.skill("ja", "WorklineのWork完了はこのTODO.mdで管理する。\nこのSkillはWorklineの次タスクを決める。\n")
        denies = self.skill("ja-deny", "このSkillはWorklineの状態を記録しない。\nWorklineの次タスクは正式なownerが決める。\n")
        found = self.detect()
        self.assertEqual({(claims, sa.RULE_SKILL_PARALLEL_LIFECYCLE), (claims, sa.RULE_SKILL_PARALLEL_PROGRESSION)},
                         self.rules(found))
        self.assertNotIn(denies, {item.path for item in found.evidence})

    def test_static_rule_levels_are_fixed_and_exported(self) -> None:
        for rule in (sa.RULE_SKILL_AUTHORITY_OVERRIDE, sa.RULE_SKILL_PARALLEL_PROGRESSION, sa.RULE_SKILL_PARALLEL_LIFECYCLE,
                     sa.RULE_BOOTSTRAP_DIFFERS, sa.RULE_BOOTSTRAP_NOT_REGULAR_FILE):
            self.assertEqual(sa.SUSPECTED, sa.RULE_LEVELS[rule])
        for rule in (sa.RULE_BOOTSTRAP_INDIRECTION, sa.RULE_OBSERVED_ROUTE, sa.RULE_OBSERVED_DELEGATION,
                     sa.RULE_OBSERVED_WRITE):
            self.assertEqual(sa.CONFIRMED, sa.RULE_LEVELS[rule])
        self.assertEqual(set(sa.RULES), set(sa.RULE_LEVELS))
        exported = set(sa.__all__)
        for name in dir(sa):
            if name.startswith("RULE_") and name != "RULE_LEVELS":
                with self.subTest(name=name):
                    self.assertIn(name, exported)
                    self.assertIn(getattr(sa, name), sa.RULES)

    def test_only_the_exact_bootstrap_path_is_exempt_from_the_skill_rule(self) -> None:
        nested = self.skill("workline/extra", CLAIMING_SKILL)
        top = ".claude/skills/SKILL.md"
        self.write(top, CLAIMING_SKILL)
        paths = {item.path for item in self.detect().evidence}
        self.assertEqual({nested, top}, paths)

    def test_the_result_depends_only_on_bytes_and_path_class(self) -> None:
        """RB8-FC-03(d): no mtime, no enumeration order, no filename list."""
        other = self.new_dir("other")
        self.canonical_bootstrap(other)
        names = ["b-tracker", "a-tracker", "c-domain", "d-helper"]
        texts = {"b-tracker": CLAIMING_SKILL, "a-tracker": CLAIMING_SKILL, "c-domain": DOMAIN_SKILL,
                 "d-helper": DELEGATING_SKILL}
        for name in names:
            self.skill(name, texts[name])
        for name in reversed(names):
            self.write(f".claude/skills/{name}/SKILL.md", texts[name], other)
            os.utime(other / ".claude" / "skills" / name / "SKILL.md", ns=(1_000_000_000, 1_000_000_000))
        first, second = self.detect(), self.detect(other)
        self.assertEqual(first, self.detect())
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(sa.source_paths(self.root), sa.source_paths(other))

    def test_an_indirection_inside_the_skill_tree_is_reported_not_followed(self) -> None:
        self.write("SKILL.md", CLAIMING_SKILL, self.outside)
        if WINDOWS:
            self.junction(".claude/skills/linked", self.outside)
        else:
            self.symlink(".claude/skills/linked", self.outside, directory=True)
        found = self.detect()
        self.assert_none(found)
        self.assertEqual((sa.Uninspected(".claude/skills/linked", sa.UNINSPECTED_INDIRECTION),), found.uninspected)
        self.assertEqual((BOOTSTRAP_REL_PATH,), sa.source_paths(self.root))

    def test_a_symlinked_skill_file_is_reported_not_followed(self) -> None:
        target = self.write("claims.md", CLAIMING_SKILL, self.outside)
        self.symlink(".claude/skills/x/SKILL.md", target, directory=False)
        found = self.detect()
        self.assert_none(found)
        self.assertEqual((sa.Uninspected(".claude/skills/x/SKILL.md", sa.UNINSPECTED_INDIRECTION),), found.uninspected)

    def test_unreadable_skill_inputs_are_uninspected_not_evidence(self) -> None:
        large = self.skill("large", "x")
        self.write(large, (CLAIMING_SKILL * (sa.MAX_FILE_BYTES // len(CLAIMING_SKILL) + 2)))
        binary = self.skill("binary", "x")
        self.write(binary, b"\xff\xfe\x00Workline" * 8)
        found = self.detect()
        self.assert_none(found)
        self.assertEqual(
            (sa.Uninspected(binary, sa.UNINSPECTED_UNDECODABLE), sa.Uninspected(large, sa.UNINSPECTED_TOO_LARGE)),
            found.uninspected,
        )
        self.assertNotIn(large, sa.source_paths(self.root))


# --------------------------------------------------------------------------- RB8-FC-04: the read set


class ReadSetTests(ShadowCase):
    DECOYS = ("README.md", "BACKLOG.md", "TODO.md", "STATUS.md", "CLAUDE.md", "decoy-legacy-tracker.md")
    SKILL_DECOYS = ("notes.md", "decoy-secret.env", "README.md", "skill.yaml")

    def setUp(self) -> None:
        super().setUp()
        self.canonical_bootstrap()
        for name in self.DECOYS:
            self.write(name, CLAIMING_SKILL)
        for skill in ("tracker", "deploy"):
            self.skill(skill, CLAIMING_SKILL if skill == "tracker" else DOMAIN_SKILL)
            for name in self.SKILL_DECOYS:
                self.write(f".claude/skills/{skill}/{name}", CLAIMING_SKILL)

    def test_source_paths_enumerates_exactly_the_three_v1_file_sources(self) -> None:
        self.assertEqual(
            (BOOTSTRAP_REL_PATH, ".claude/skills/deploy/SKILL.md", ".claude/skills/tracker/SKILL.md"),
            sa.source_paths(self.root),
        )

    def test_only_the_enumerated_files_are_read_and_no_decoy_is_opened(self) -> None:
        global _AUDITED, _AUDIT_INSTALLED
        if not _AUDIT_INSTALLED:
            sys.addaudithook(_audit)
            _AUDIT_INSTALLED = True
        read: list[str] = []
        real = fsafe.SafeDirectory.read_file_bound

        def recording(directory, name):
            read.append(name)
            return real(directory, name)

        expected = sa.source_paths(self.root)
        _AUDITED = []
        try:
            with mock.patch.object(fsafe.SafeDirectory, "read_file_bound", recording):
                found = self.detect()
        finally:
            audited, _AUDITED = _AUDITED, None
        self.assertEqual(len(expected), len(read), "one handle-bound read per enumerated source, and no other")
        self.assertEqual({"SKILL.md"}, set(read))
        opened = {Path(item).name for item in audited}
        for decoy in set(self.DECOYS) | set(self.SKILL_DECOYS):
            with self.subTest(decoy=decoy):
                self.assertNotIn(decoy, opened)
        self.assertEqual({".claude/skills/tracker/SKILL.md"}, {item.path for item in found.evidence})

    def test_nothing_is_opened_by_path(self) -> None:
        def refuse(*_args, **_kwargs):
            raise AssertionError("the detector never opens a file by path")

        with mock.patch("builtins.open", refuse), mock.patch("io.open", refuse):
            found = self.detect()
            sa.source_paths(self.root)
        self.assertEqual(sa.SUSPECTED, found.status)


# --------------------------------------------------------------------------- §30.39: observed evidence


class ObservedEvidenceTests(ShadowCase):
    def setUp(self) -> None:
        super().setUp()
        self.canonical_bootstrap()

    def test_structured_observed_noncanonical_route_delegation_and_write_are_confirmed(self) -> None:
        cases = (
            (sa.OBSERVED_ROUTE, sa.RULE_OBSERVED_ROUTE, ".claude/skills/backlog/SKILL.md", sa.OPERATION_SEMANTICS),
            (sa.OBSERVED_DELEGATION, sa.RULE_OBSERVED_DELEGATION, ".claude/skills/todo/SKILL.md", sa.LIFECYCLE_STATE),
            (sa.OBSERVED_WRITE, sa.RULE_OBSERVED_WRITE, "TODO.md", sa.PROGRESSION),
        )
        for kind, rule, artifact, responsibility in cases:
            with self.subTest(kind=kind):
                seen = sa.ObservedEvidence(kind, artifact, responsibility, "skills/project-router")
                found = self.detect(observed=[seen])
                self.assertEqual(sa.CONFIRMED, found.status)
                self.assertEqual(
                    (sa.ShadowEvidence(sa.CONFIRMED, sa.SOURCE_OBSERVED, artifact, rule, responsibility,
                                       sa.RESPONSIBILITY_OWNERS[responsibility], observed_by="skills/project-router"),),
                    found.confirmed,
                )

    def test_an_observation_confirms_alongside_static_suspicion_but_never_promotes_it(self) -> None:
        skill = self.skill("tracker", CLAIMING_SKILL)
        alone = self.detect()
        self.assertEqual(sa.SUSPECTED, alone.status)
        self.assertEqual(alone, self.detect(observed=()))
        seen = sa.ObservedEvidence(sa.OBSERVED_WRITE, "TODO.md", sa.PROGRESSION, "start")
        found = self.detect(observed=(seen,))
        self.assertEqual(sa.CONFIRMED, found.status)
        self.assertEqual({"TODO.md"}, {item.path for item in found.confirmed})
        self.assertTrue(all(item.level == sa.SUSPECTED for item in found.evidence if item.path == skill))

    def test_observed_evidence_is_strict_and_frozen(self) -> None:
        good = dict(kind=sa.OBSERVED_WRITE, artifact="TODO.md", responsibility=sa.PROGRESSION, observed_by="start")
        bad = (
            ("kind", "suspected"), ("kind", "semantic"), ("kind", "guess"), ("kind", "Write"),
            ("responsibility", "lifecycle"), ("responsibility", ""),
            ("artifact", ""), ("artifact", "/abs/TODO.md"), ("artifact", "C:/TODO.md"), ("artifact", "C:TODO.md"),
            ("artifact", "a\\b.md"), ("artifact", "../TODO.md"), ("artifact", "a/../b.md"), ("artifact", "./a.md"),
            ("artifact", "a//b.md"), ("artifact", "a/"), ("artifact", "TODO\n.md"), ("artifact", "x" * 513),
            ("artifact", ".workline/works/w.md"), ("artifact", ".WORKLINE/x"), ("artifact", ".workline"),
            ("observed_by", ""), ("observed_by", "Skills/Start"), ("observed_by", "skills/start/extra"),
            ("observed_by", "a guess"),
            ("artifact", Path("TODO.md")), ("kind", None), ("observed_by", 1),
        )
        sa.ObservedEvidence(**good)
        for field, value in bad:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    sa.ObservedEvidence(**{**good, field: value})
        seen = sa.ObservedEvidence(**good)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            seen.kind = sa.OBSERVED_ROUTE  # type: ignore[misc]

    def test_anything_but_an_observed_evidence_record_never_promotes(self) -> None:
        class Lookalike(sa.ObservedEvidence):
            pass

        smuggled = (
            {"kind": "write", "artifact": "TODO.md", "responsibility": "progression", "observed_by": "start"},
            ("write", "TODO.md", "progression", "start"),
            "confirmed",
            Lookalike(sa.OBSERVED_WRITE, "TODO.md", sa.PROGRESSION, "start"),
        )
        found = self.detect(observed=smuggled)
        self.assert_none(found)
        self.assertEqual(
            tuple(sa.Uninspected(f"observed[{index}]", sa.UNINSPECTED_OBSERVATION_REJECTED) for index in range(4)),
            found.uninspected,
        )


# --------------------------------------------------------------------------- the public result


class ResultShapeTests(ShadowCase):
    def test_the_result_is_frozen_json_ready_and_h3_safe(self) -> None:
        self.write(BOOTSTRAP_REL_PATH, "a private bootstrap: secret-marker-7f3a\n")
        self.skill("tracker", CLAIMING_SKILL + "unique-excerpt-marker-91c2 records Workline Work completion.\n")
        seen = sa.ObservedEvidence(sa.OBSERVED_DELEGATION, "TODO.md", sa.LIFECYCLE_STATE, "skills/project-router")
        found = self.detect(observed=[seen])
        with self.assertRaises(dataclasses.FrozenInstanceError):
            found.status = sa.NONE  # type: ignore[misc]
        data = found.to_json()
        text = json.dumps(data, ensure_ascii=True, sort_keys=True)
        self.assertEqual(data, json.loads(text))
        self.assertEqual(
            {"status", "advisory", "confirmed_count", "suspected_count", "evidence", "uninspected"}, set(data)
        )
        self.assertEqual((sa.CONFIRMED, True, 1), (data["status"], data["advisory"], data["confirmed_count"]))
        self.assertEqual(len(found.suspected), data["suspected_count"])
        for leaked in (str(self.tmp), str(self.root), self.tmp.name, "secret-marker-7f3a", "unique-excerpt-marker-91c2",
                       "records Workline Work"):
            self.assertNotIn(leaked, text)
        for item in found.evidence:
            self.assertFalse(Path(item.path).is_absolute())
            self.assertNotIn("\\", item.path)
            self.assertIn(item.rule, sa.RULES)
            self.assertEqual(sa.RULE_LEVELS[item.rule], item.level)
            self.assertIn(item.responsibility, sa.RESPONSIBILITIES)
        self.assertEqual(max((item.level for item in found.evidence), key=sa.LEVELS.index), found.status)
        self.assertTrue(found.advisory)
        lines = found.render_lines()
        self.assertEqual("shadow authority (advisory): confirmed", lines[0])
        self.assertTrue(all(str(self.tmp) not in line for line in lines))

    def test_the_entry_point_takes_a_project_root_path_or_a_store(self) -> None:
        self.write(BOOTSTRAP_REL_PATH, "differs\n")
        expected = self.detect()
        self.assertEqual(expected, sa.detect_shadow_authority(str(self.root)))
        self.assertEqual(expected, sa.detect_shadow_authority(ProjectStore(self.root)))
        self.assertEqual(sa.source_paths(self.root), sa.source_paths(ProjectStore(self.root)))

    def test_canonical_owner_ids_are_registry_ids(self) -> None:
        self.assertEqual(set(sa.RESPONSIBILITIES), set(sa.RESPONSIBILITY_OWNERS))
        for responsibility, owners in sa.RESPONSIBILITY_OWNERS.items():
            for owner in owners:
                with self.subTest(responsibility=responsibility, owner=owner):
                    if owner.startswith("skills/"):
                        self.assertIn(owner, REQUIRED_SKILL_IDS)
                    elif owner.startswith("rules/"):
                        self.assertIn(owner, REQUIRED_RULE_IDS)
                    else:
                        self.assertIn(owner, ("registry.md", "project-policy-change"))


# --------------------------------------------------------------------------- §30.28 / §30.39: advisory only


class AdvisoryOnlyTests(ShadowCase):
    def test_the_detector_never_raises(self) -> None:
        missing = self.tmp / "missing"
        self.assert_none(self.detect(missing))
        a_file = self.write("plain.txt", "x\n", self.tmp)
        self.assert_none(self.detect(a_file))

        def exploding():
            yield sa.ObservedEvidence(sa.OBSERVED_WRITE, "TODO.md", sa.PROGRESSION, "start")
            raise RuntimeError("an observer failed")

        found = self.detect(observed=exploding())
        self.assertIn(sa.Uninspected("observed", sa.UNINSPECTED_FAILED), found.uninspected)
        self.skill("tracker", CLAIMING_SKILL)
        with mock.patch.object(fsafe, "walk", side_effect=RuntimeError("listing failed")):
            found = self.detect()
        self.assertIn(sa.Uninspected(".claude/skills", sa.UNINSPECTED_FAILED), found.uninspected)
        self.assertEqual(sa.NONE, found.status)
        self.assertEqual((), sa.source_paths(missing))

    def test_no_auto_edit_delete_or_migration(self) -> None:
        store = self.new_project("project")
        root = store.root
        self.write(".claude/skills/tracker/SKILL.md", CLAIMING_SKILL, root)
        self.write("BACKLOG.md", CLAIMING_SKILL, root)
        self.write("SKILL.md", bs.render_bootstrap(), self.outside)
        if WINDOWS and make_junction(root / ".claude" / "skills" / "linked", self.outside):
            self.link_cleanup(root / ".claude" / "skills" / "linked")
        before = (snapshot(root), snapshot(self.outside), git(root, "status", "--porcelain", "--untracked-files=all"),
                  git(root, "rev-parse", "HEAD"))
        seen = sa.ObservedEvidence(sa.OBSERVED_WRITE, "BACKLOG.md", sa.PROGRESSION, "start")
        found = sa.detect_shadow_authority(root, observed=[seen])
        sa.source_paths(root)
        found.to_json()
        found.render_lines()
        after = (snapshot(root), snapshot(self.outside), git(root, "status", "--porcelain", "--untracked-files=all"),
                 git(root, "rev-parse", "HEAD"))
        self.assertEqual(sa.CONFIRMED, found.status)
        self.assertEqual(before, after, "the detector edits, deletes, migrates and backfills nothing")
        self.assertFalse((root / ".workline" / "runtime" / "locks" / "holder.json").exists(), "no lock is taken")

    def test_the_module_has_no_writer_lock_mutation_git_or_network_surface(self) -> None:
        tree = ast.parse(Path(sa.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        names = {name.rsplit(".", 1)[-1] for name in imported}
        for forbidden in ("mutation", "oplock", "gitops", "gitcmd", "durable", "subprocess", "socket", "urllib",
                          "http", "shutil", "tempfile", "project_start", "create", "start", "roadmap", "phase_create",
                          "MutationController", "Effect", "project_operation"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, names)
        calls = {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                 for node in ast.walk(tree) if isinstance(node, ast.Call)}
        for forbidden in ("open", "write_text", "write_bytes", "mkdir", "makedirs", "unlink", "remove", "rename",
                          "replace", "rmdir", "rmtree", "symlink", "create_file_exclusive", "add_effects", "apply",
                          "commit", "push", "reserve_id", "backfill_bootstrap", "project_start", "system", "popen",
                          "utime", "chmod", "truncate"):
            with self.subTest(call=forbidden):
                self.assertNotIn(forbidden, calls)
        walks = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == "walk"]
        self.assertTrue(walks)
        for node in walks:
            self.assertFalse(any(keyword.arg == "create" for keyword in node.keywords), "every walk is a no-create read")

    def test_shadow_advisory_does_not_fail_validation(self) -> None:
        """§30.39 / §30.30 (leaf part): planted shadow evidence never becomes a validate_project Problem."""
        store = self.new_project("project")
        root = store.root
        baseline = validate_project(store)
        self.assertEqual([], baseline)
        self.write(".claude/skills/tracker/SKILL.md", CLAIMING_SKILL, root)
        self.write(BOOTSTRAP_REL_PATH, bs.render_bootstrap() + "\nThis bootstrap overrides Workline state.\n", root)
        seen = sa.ObservedEvidence(sa.OBSERVED_DELEGATION, ".claude/skills/tracker/SKILL.md", sa.LIFECYCLE_STATE,
                                   "skills/project-router")
        self.assertEqual(sa.CONFIRMED, sa.detect_shadow_authority(root, observed=[seen]).status)
        self.assertEqual(baseline, validate_project(store))
        if WINDOWS:
            (root / BOOTSTRAP_REL_PATH).unlink()
            (root / ".claude" / "skills" / "workline").rmdir()
            self.write("SKILL.md", bs.render_bootstrap(), self.outside)
            if make_junction(root / ".claude" / "skills" / "workline", self.outside):
                self.link_cleanup(root / ".claude" / "skills" / "workline")
                self.assertEqual(sa.CONFIRMED, sa.detect_shadow_authority(root).status)
                self.assertEqual(baseline, validate_project(store))

    @unittest.skip(WAIT_IR1)
    def test_validate_project_cli_displays_the_advisory_without_changing_pass(self) -> None:
        """RB6A-IR-1, after RB6-F integrates cli.py: PASS stays PASS (exit 0) and the advisory is displayed."""
        store = self.new_project("project")
        root = store.root
        self.write(".claude/skills/tracker/SKILL.md", CLAIMING_SKILL, root)
        self.write(BOOTSTRAP_REL_PATH, "a differing bootstrap\n", root)
        expected = sa.detect_shadow_authority(root)
        self.assertEqual(sa.SUSPECTED, expected.status)
        result = run_python(launcher_command(WORKLINE_ROOT, "validate-project", root), cwd=root)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual("project validation: PASS", lines[0])
        self.assertEqual(expected.render_lines(), lines[1:1 + len(expected.render_lines())])
        clean = self.new_project("clean")
        result = run_python(launcher_command(WORKLINE_ROOT, "validate-project", clean.root), cwd=clean.root)
        self.assertEqual((0, ["project validation: PASS"]), (result.returncode, result.stdout.splitlines()))


# --------------------------------------------------------------------------- §30.39 / §15.7: ProjectSTART


class ProjectStartTests(ShadowCase):
    def test_a_fresh_projectstart_project_is_none_and_carries_no_shadow_state(self) -> None:
        store = self.new_project("project")
        found = sa.detect_shadow_authority(store.root)
        self.assert_none(found)
        self.assertEqual((), found.uninspected)
        self.assertEqual((BOOTSTRAP_REL_PATH,), sa.source_paths(store.root))
        self.assertEqual(bs.MATCHING, bs.bootstrap_state(store))
        tracked = git(store.root, "ls-files").splitlines()
        self.assertIn(BOOTSTRAP_REL_PATH, tracked)
        self.assertFalse([path for path in tracked if "shadow" in path.lower()], "ProjectSTART installs no shadow state")

    def test_projectstart_and_the_bootstrap_owner_do_not_call_the_detector(self) -> None:
        from workline import project_start

        for module in (project_start, bs):
            with self.subTest(module=module.__name__):
                self.assertNotIn("shadow_authority", Path(module.__file__).read_text(encoding="utf-8"))

    @unittest.skip(WAIT_IR2)
    def test_projectstart_is_unchanged_and_status_reports_none_for_a_fresh_project(self) -> None:
        """RB6A-IR-2, after RB6-F integrates status.py: §15.7 "RB6 does not change ProjectSTART" on the integrated tree."""
        from workline import project_start
        from workline.status import build_status

        store = self.new_project("project")
        policy = build_status(store.root).data["policy"]
        self.assertEqual(sa.detect_shadow_authority(store.root).to_json(), policy["shadow_authority"])
        self.assertEqual(sa.NONE, policy["shadow_authority"]["status"])
        self.assertEqual(bs.render_bootstrap().encode("utf-8"), (store.root / BOOTSTRAP_REL_PATH).read_bytes())
        tracked = git(store.root, "ls-files").splitlines()
        self.assertFalse([path for path in tracked if "shadow" in path.lower()])
        for module in (project_start, bs):
            self.assertNotIn("shadow_authority", Path(module.__file__).read_text(encoding="utf-8"))
        skill = (WORKLINE_ROOT / ".claude" / "skills" / "project-start" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("shadow", skill.lower())


class SharedIntegrationTests(ShadowCase):
    @unittest.skip(WAIT_IR2)
    def test_status_policy_section_carries_the_shadow_diagnostic(self) -> None:
        """RB6A-IR-2: the RB1 policy section carries ``shadow_authority`` = the detector's JSON, additively."""
        from workline.status import VERSION, build_status, render_human

        store = self.new_project("project")
        self.write(".claude/skills/tracker/SKILL.md", CLAIMING_SKILL, store.root)
        model = build_status(store.root)
        self.assertEqual(1, VERSION, "RB1 schema/version do not change")
        self.assertEqual(sa.detect_shadow_authority(store.root).to_json(), model.data["policy"]["shadow_authority"])
        self.assertEqual(sa.SUSPECTED, model.data["policy"]["shadow_authority"]["status"])
        self.assertEqual("pass", model.data["validation"]["status"], "the advisory never fails validation")
        self.assertIn("shadow authority (advisory): suspected", render_human(model))

    @unittest.skip(WAIT_IR3)
    def test_project_router_resolves_noncanonical_wording_by_meaning(self) -> None:
        """RB6A-IR-3: the canonical project-router text carries §30.29's four outcomes and no filename list."""
        text = (WORKLINE_ROOT / ".claude" / "skills" / "project-router" / "SKILL.md").read_text(encoding="utf-8")
        for required in (
            "## 非canonicalな言い回し",
            "意味がcanonical Workline責務に一意に対応する",
            "plainなdomain / document編集",
            "rules/human-confirmation",
            "存在しないWorkline operation / ownerを名乗る",
            "fallback・新設をしない",
            "BACKLOG / TODO / STATUSという名前はWorkline operationにならない",
            "forbidden-filename listは持たない",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
