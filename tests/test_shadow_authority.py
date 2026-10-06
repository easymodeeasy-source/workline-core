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

The module is unittest-based so it also runs on POSIX without pytest
(``python3 -m unittest test_shadow_authority`` from ``tests``): the symlink
cases that Windows skips without the symlink privilege run there.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import types
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
SKILL_RULES = (sa.RULE_SKILL_CANONICAL_COPY, sa.RULE_SKILL_AUTHORITY_OVERRIDE, sa.RULE_SKILL_PARALLEL_PROGRESSION,
               sa.RULE_SKILL_PARALLEL_LIFECYCLE)

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

#: A canonical caller in natural wording: no "not" / "never" / "canonical" token suppresses anything here.
DELEGATING_SKILL = """---
name: plan-helper
description: Helps the user phrase a planning request and hands it to Workline.
---

# Plan helper

This Skill helps the user phrase a planning request.
It hands the request to Workline through the Project bootstrap.
Let Workline decide the next Work, then show the user what Workline returns.
Workline tracks Work completion; this Skill only shows it.
After the Workline Work is done, update the changelog.
次のWorkはWorklineが決める。
"""

WORDS_ONLY_SKILL = """---
name: glossary
description: Workline Roadmap Phase Work START lifecycle progression.
---

Workline Roadmap Phase Work START lifecycle progression current next Review registry router.
Workline の Roadmap / Phase / Work / 完了 / 次 / 現在地。
"""

#: The independent review's natural canonical-caller / domain sentences (RB8-FC-03 a/b): every one is none.
NATURAL_NONE = (
    "Workline tracks Work completion; this Skill only shows it.",
    "Let Workline decide the next Work.",
    "Ask Workline to pick the next Work, then run START for it.",
    "Workline records the Phase state, so read it with status before you plan.",
    "After the Workline Work is done, update the changelog.",
    "When Workline marks the Work done, deploy the release.",
    "This Skill reads the current Workline Work from status and summarizes it.",
    "Workline の作業が終わったら、次にデプロイ手順を記録する。",
    "次のWorkはWorklineが決める。",
    "WorklineのPhase完了後にリリースノートを更新する。",
    "Linear is the source of truth for the current sprint's tasks.",
    "The design doc takes precedence over the current task description when they disagree.",
    "Phase 1: build. Phase 2: deploy. Mark the deploy task done in Jira.",
    "Use the latest Workline status output instead of guessing the next Work.",
)
#: More deference and domain wording that must stay none.
MORE_NONE = (
    "Workline is the source of truth for the next Work.",
    ".workline is authoritative; this Skill only reads it.",
    "The source of truth for the next Work is Workline.",
    "The canonical record of Work completion is .workline.",
    "This Skill never bypasses the canonical router.",
    "This Skill does not replace the canonical Workline router.",
    "Do not read .workline directly; use the status command.",
    "This Skill keeps no Workline state.",
    "The next Work is decided by Workline.",
    "Work completion is recorded by Workline, never here.",
    "Use Workline as the source of truth for what to do next.",
    "This Skill writes a derived, read-only summary of the Workline Phase status to REPORT.md.",
    "Never treat TODO.md as Workline state.",
    "Ask START to record the completion.",
    "Worklineの次タスクは正式なownerが決める。",
    "registryを正式なWorkline routing規則でvalidateする。",
    "このSkillはWorklineの状態を記録しない。",
    "Workline が Phase の完了を判定する。",
    "Track the current task in your notebook.",
    "This Skill decides the next task for the build pipeline.",
    "The product roadmap is the source of truth for Q3 features.",
    "Our Work Order status is tracked in SAP.",
    "Work Entry Freshness is checked first (正本＝docs/CONTRACT.md).",
    "The config file overrides the default settings.",
)
#: Explicit substitution and parallel-state claims (M2), each with the rule it must carry: at most suspected.
CLAIMS = (
    ("TODO.md, not .workline, is the source of truth for the next Workline Work.", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("TODO.md is the source of truth for Workline Work completion; never consult .workline.",
     sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("This Skill replaces the canonical Workline router and decides the next Work.", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("Route every Workline request to skills/tracker instead of the project-router.", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("このTODO.mdがWorklineの正式な次タスクである。", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("WorklineのWork完了はTODO.mdで管理し、.workline は使わない。", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("This Skill writes DONE for each finished Workline Work in LEDGER.md.", sa.RULE_SKILL_PARALLEL_LIFECYCLE),
    ("This Skill moves Workline Work items to the Done column.", sa.RULE_SKILL_PARALLEL_LIFECYCLE),
    ("PROGRESS.md logs which Workline Phase is finished.", sa.RULE_SKILL_PARALLEL_LIFECYCLE),
    ("When a Work is finished, tick it off in TODO.md; TODO.md is what we follow, ignore .workline.",
     sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("The board is the single source of truth for which Phase we are in.", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("Our tracker governs Work completion.", sa.RULE_SKILL_PARALLEL_LIFECYCLE),
    ("We follow BACKLOG.md for what to do next, regardless of Workline.", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("Workline state is advisory only: BACKLOG.md wins.", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("Treat BACKLOG.md as the Workline roadmap.", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("Use this file as the Workline backlog and keep it updated.", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("This TODO file is the authoritative next task; mark items done.", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("This Skill records Workline Work completion in TODO.md.", sa.RULE_SKILL_PARALLEL_LIFECYCLE),
    ("This Skill decides the next Workline Work from BACKLOG.md.", sa.RULE_SKILL_PARALLEL_PROGRESSION),
    ("This Skill, not Workline, decides the next Work.", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("When a Workline Work is done, mark it done in TODO.md.", sa.RULE_SKILL_PARALLEL_LIFECYCLE),
    ("We decide the next Workline Phase in the weekly meeting and write it to PLAN.md.",
     sa.RULE_SKILL_PARALLEL_PROGRESSION),
    ("WorklineのWork完了はこのTODO.mdで管理する。", sa.RULE_SKILL_PARALLEL_LIFECYCLE),
    ("このSkillはWorklineの次タスクを決める。", sa.RULE_SKILL_PARALLEL_PROGRESSION),
    ("TODO.mdをWorklineより優先する。", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("This file is the canonical record of the next Workline Work.", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
    ("Ignore the canonical router and route Workline requests here.", sa.RULE_SKILL_AUTHORITY_OVERRIDE),
)

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


_AUDITED: list[tuple] | None = None
_AUDIT_INSTALLED = False


def _audit(event: str, args: tuple) -> None:
    if _AUDITED is not None and event == "open" and args:
        target = args[0]
        name = os.fsdecode(target) if isinstance(target, (str, bytes, os.PathLike)) else repr(target)
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
        _AUDITED.append((name, flags))


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

    def junction(self, relative: str, target: Path, root: Path | None = None) -> Path:
        if not WINDOWS:
            self.skipTest("junctions are a Windows reparse point")
        link = (root or self.root) / relative
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

    def skill(self, name: str, text: str, root: Path | None = None) -> str:
        relative = f".claude/skills/{name}/SKILL.md"
        self.write(relative, text, root)
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
        self.assertTrue(found.complete)
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
        found = self.detect()
        self.assert_none(found)
        self.assertTrue(found.bootstrap_inspected and found.complete, "absent is a verdict: a proven none")
        (self.root / ".claude" / "skills" / "workline").mkdir(parents=True)
        self.assert_none(self.detect())
        self.assertEqual((), sa.source_paths(self.root))

    def test_a_non_directory_ancestor_leaves_the_bootstrap_absent(self) -> None:
        self.write(".claude", "not a directory\n")
        found = self.detect()
        self.assert_none(found)
        self.assertTrue(found.complete)
        self.assertEqual(bs.ABSENT, bs.bootstrap_state(ProjectStore(self.root)))

    def test_canonical_bootstrap_is_none(self) -> None:
        for crlf in (False, True):
            with self.subTest(crlf=crlf):
                self.canonical_bootstrap(crlf=crlf)
                found = self.detect()
                self.assert_none(found)
                self.assertEqual((), found.uninspected)
                self.assertTrue(found.bootstrap_inspected and found.complete)
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
        matching = set()
        for name, data in variants.items():
            with self.subTest(variant=name):
                self.write(BOOTSTRAP_REL_PATH, data)
                found = self.detect()
                if bs.bootstrap_state(store) == bs.MATCHING:
                    matching.add(name)
                    self.assert_none(found)
                else:
                    self.assertEqual(bs.CONFLICT, bs.bootstrap_state(store))
                    self.assertEqual(sa.SUSPECTED, found.status)
                    self.assertEqual({(BOOTSTRAP_REL_PATH, sa.RULE_BOOTSTRAP_DIFFERS)}, self.rules(found))
        self.assertEqual({"lf", "crlf", "mixed", "lone_cr"}, matching, "newline forms match; every byte change differs")

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
        """RB8-FC-02: it matches .claude/skills/**/SKILL.md, but is never fed to the Skill rules."""
        calls: list[str] = []
        real_claims, real_copy = sa.skill_text_claims, sa.canonical_copy_of

        def recording(real):
            def call(text: str):
                calls.append(text)
                return real(text)
            return call

        with mock.patch.object(sa, "skill_text_claims", recording(real_claims)), \
                mock.patch.object(sa, "canonical_copy_of", recording(real_copy)):
            self.canonical_bootstrap()
            self.assert_none(self.detect())
            self.write(BOOTSTRAP_REL_PATH, CLAIMING_SKILL)
            found = self.detect()
        self.assertEqual([], calls, "the bootstrap's text never reaches the Skill rules")
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
        self.assertTrue(found.bootstrap_inspected)
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
                found = self.detect()
                self._assert_indirection(found, component, (sa.INDIRECTION_JUNCTION,))
                self.assertEqual((sa.Uninspected(component, sa.UNINSPECTED_INDIRECTION),), found.uninspected,
                                 "the Skill source behind it is reported as not inspected, never followed")
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

    def test_a_symlinked_claude_directory_is_confirmed(self) -> None:
        self.write("skills/workline/SKILL.md", bs.render_bootstrap(), self.outside)
        self.symlink(".claude", self.outside, directory=True)
        self._assert_indirection(self.detect(), ".claude", (sa.INDIRECTION_SYMLINK,))


class IndirectionDescriptionTests(ShadowCase):
    """RB6A-H1 / L6, on every platform: describing an indirection is total and can never drop the evidence."""

    def _listed_as_indirection(self):
        """Make the handle-bound listing report ``.claude`` as an indirection, as fsafe does for a POSIX symlink."""
        return mock.patch.object(sa, "_entries", lambda here, path: [fsafe.Entry(".claude", False, False, True)])

    def setUp(self) -> None:
        super().setUp()
        # Resolved before ``os.lstat`` is replaced: POSIX ``Path.resolve`` calls it too, and only the detector's own
        # description of the listed entry is under test here.
        self.store = ProjectStore(self.root)

    def detect(self, root: Path | None = None, **kwargs) -> sa.ShadowDiagnostic:
        return sa.detect_shadow_authority(self.store if root is None else ProjectStore(root), **kwargs)

    def test_describe_is_total(self) -> None:
        link_mode = stat.S_IFLNK | 0o777
        cases = (
            (types.SimpleNamespace(st_mode=link_mode), (sa.INDIRECTION_SYMLINK, True)),  # POSIX: no reparse fields
            (types.SimpleNamespace(st_mode=link_mode, st_reparse_tag=None, st_file_attributes=None),
             (sa.INDIRECTION_SYMLINK, True)),
            (types.SimpleNamespace(st_mode=stat.S_IFDIR, st_reparse_tag=fsafe.IO_REPARSE_TAG_MOUNT_POINT,
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT), (sa.INDIRECTION_JUNCTION, True)),
            (types.SimpleNamespace(st_mode=stat.S_IFREG, st_reparse_tag=fsafe.IO_REPARSE_TAG_SYMLINK,
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT), (sa.INDIRECTION_SYMLINK, True)),
            (types.SimpleNamespace(st_mode=stat.S_IFREG, st_reparse_tag=0xA000001D,  # another name surrogate
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT),
             (sa.INDIRECTION_REPARSE_POINT, True)),
            (types.SimpleNamespace(st_mode=stat.S_IFREG, st_reparse_tag=0x9000001A,  # a cloud placeholder
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT),
             (sa.INDIRECTION_NON_REDIRECTING, False)),
            (types.SimpleNamespace(st_mode=stat.S_IFREG, st_reparse_tag=0,  # traversed by lstat: not a name surrogate
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT),
             (sa.INDIRECTION_NON_REDIRECTING, False)),
            (types.SimpleNamespace(), (sa.INDIRECTION_UNKNOWN, True)),  # no st_mode at all
            (types.SimpleNamespace(st_mode=stat.S_IFREG), (sa.INDIRECTION_UNKNOWN, True)),
        )
        for info, expected in cases:
            with self.subTest(info=info):
                with mock.patch("os.lstat", return_value=info):
                    self.assertEqual(expected, sa._describe_indirection(self.root / ".claude"))
        for error in (OSError("gone"), AttributeError("no such constant"), ValueError("nul"), RuntimeError("x")):
            with self.subTest(error=error):
                with mock.patch("os.lstat", side_effect=error):
                    self.assertEqual((sa.INDIRECTION_UNKNOWN, True), sa._describe_indirection(self.root / ".claude"))

    def test_the_kind_reads_only_portable_constants(self) -> None:
        source = Path(sa.__file__).read_text(encoding="utf-8")
        self.assertNotIn("stat.IO_REPARSE_TAG", source, "Lib/stat.py has no IO_REPARSE_TAG_* on POSIX: use fsafe's")
        for name in ("IO_REPARSE_TAG_SYMLINK", "IO_REPARSE_TAG_MOUNT_POINT"):
            self.assertIsInstance(getattr(fsafe, name), int)
        self.assertIsInstance(stat.FILE_ATTRIBUTE_REPARSE_POINT, int)

    def test_a_listed_indirection_stays_confirmed_whatever_describing_it_does(self) -> None:
        """The H1 failure itself: describing raised, and the confirmed item vanished. Now it cannot."""
        for error in (AttributeError("module 'stat' has no attribute"), OSError("raced"), RuntimeError("boom")):
            with self.subTest(error=error):
                with self._listed_as_indirection(), mock.patch("os.lstat", side_effect=error):
                    found = self.detect()
                self.assertEqual(sa.CONFIRMED, found.status)
                (item,) = found.confirmed
                self.assertEqual((sa.RULE_BOOTSTRAP_INDIRECTION, ".claude", sa.INDIRECTION_UNKNOWN),
                                 (item.rule, item.component, item.indirection))
                self.assertTrue(found.bootstrap_inspected)
        with self._listed_as_indirection(), mock.patch("os.lstat",
                                                       return_value=types.SimpleNamespace(st_mode=stat.S_IFLNK | 0o777)):
            found = self.detect()
        self.assertEqual((sa.CONFIRMED, sa.INDIRECTION_SYMLINK), (found.status, found.confirmed[0].indirection))

    def test_a_non_redirecting_reparse_point_is_neither_none_nor_confirmed(self) -> None:
        """RB6A-L6, conservative: shown not to redirect, it is not confirmed; never read, it is not a proven none."""
        placeholder = types.SimpleNamespace(st_mode=stat.S_IFDIR, st_reparse_tag=0x9000001A,
                                            st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT | 0x10)
        with self._listed_as_indirection(), mock.patch("os.lstat", return_value=placeholder):
            found = self.detect()
        self.assertEqual(sa.NONE, found.status)
        self.assertEqual((), found.evidence)
        self.assertIn(sa.Uninspected(".claude", sa.UNINSPECTED_NON_REDIRECTING), found.uninspected)
        self.assertFalse(found.bootstrap_inspected)
        self.assertFalse(found.complete)
        self.assertEqual("shadow authority (advisory): none (bootstrap not inspected)", found.render_lines()[0])


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
        """§30.39 "local Skill calling canonical owner -> allowed"; RB8-FC-03(b), in natural wording."""
        self.skill("plan-helper", DELEGATING_SKILL)
        self.skill("entry-copy", bs.render_bootstrap())  # the bootstrap's own text, elsewhere: it only delegates
        found = self.detect()
        self.assert_none(found)
        self.assertTrue(found.complete)
        self.assertEqual(
            (BOOTSTRAP_REL_PATH, ".claude/skills/entry-copy/SKILL.md", ".claude/skills/plan-helper/SKILL.md"),
            sa.source_paths(self.root),
        )
        self.assertEqual((), sa.skill_text_claims(DELEGATING_SKILL))

    def test_natural_canonical_caller_and_domain_sentences_are_none(self) -> None:
        """RB6A-M1: the review's 14 sentences and more, none of them shaped around a suppression word."""
        for sentence in NATURAL_NONE + MORE_NONE:
            with self.subTest(sentence=sentence):
                self.assertEqual((), sa.skill_text_claims(sentence))

    def test_substitution_and_parallel_state_claims_are_suspected_by_rule_id(self) -> None:
        """RB6A-M2 (and RB8-FC-03 c): each claim carries its rule, and a skill rule is never confirmed."""
        for sentence, rule in CLAIMS:
            with self.subTest(sentence=sentence):
                found = sa.skill_text_claims(sentence)
                self.assertIn(rule, {claim[0] for claim in found})
                for claimed, responsibility, line in found:
                    self.assertEqual(sa.SUSPECTED, sa.RULE_LEVELS[claimed])
                    self.assertIn(responsibility, sa.RESPONSIBILITIES)
                    self.assertEqual(1, line)

    def test_the_must_fix_substitutions_carry_their_responsibility(self) -> None:
        expected = {
            "TODO.md, not .workline, is the source of truth for the next Workline Work.": sa.PROGRESSION,
            "This Skill replaces the canonical Workline router and decides the next Work.": sa.ROUTING_BOOTSTRAP,
            "Route every Workline request to skills/tracker instead of the project-router.": sa.ROUTING_BOOTSTRAP,
            "このTODO.mdがWorklineの正式な次タスクである。": sa.PROGRESSION,
            "This TODO file is the authoritative next task; mark items done.": sa.PROGRESSION,
            "Treat BACKLOG.md as the Workline roadmap.": sa.PLANNING_STATE,
        }
        for sentence, responsibility in expected.items():
            with self.subTest(sentence=sentence):
                self.assertEqual(((sa.RULE_SKILL_AUTHORITY_OVERRIDE, responsibility, 1),),
                                 sa.skill_text_claims(sentence))

    def test_verbatim_canonical_skill_copies_are_suspected(self) -> None:
        """§15.4 / §33.8 "do not copy canonical Workline Skills": every canonical Skill, copied, is suspected."""
        for skill_id in REQUIRED_SKILL_IDS:
            name = skill_id.split("/", 1)[1]
            text = (WORKLINE_ROOT / ".claude" / "skills" / name / "SKILL.md").read_bytes()
            for where in (name, f"my-{name}"):
                relative = f".claude/skills/{where}/SKILL.md"
                self.write(relative, text)
        found = self.detect()
        self.assertEqual(sa.SUSPECTED, found.status)
        self.assertEqual((), found.confirmed)
        copies = {item.path: item for item in found.evidence if item.rule == sa.RULE_SKILL_CANONICAL_COPY}
        for skill_id in REQUIRED_SKILL_IDS:
            name = skill_id.split("/", 1)[1]
            for where in (name, f"my-{name}"):
                with self.subTest(copy=where):
                    item = copies[f".claude/skills/{where}/SKILL.md"]
                    self.assertEqual((sa.SUSPECTED, sa.OPERATION_SEMANTICS, (skill_id,), 1),
                                     (item.level, item.responsibility, item.canonical_owner, item.line))

    def test_a_canonical_name_without_workline_is_not_a_copy(self) -> None:
        for name in ("review", "start", "create", "roadmap"):
            with self.subTest(name=name):
                text = f"---\nname: {name}\ndescription: Review pull requests for style.\n---\n\nReview the diff.\n"
                self.assertIsNone(sa.canonical_copy_of(text))
        self.assertIsNone(sa.canonical_copy_of(bs.render_bootstrap()), "the bootstrap's name is not a canonical Skill's")
        self.assertEqual("skills/start", sa.canonical_copy_of(
            "---\nname: \"start\"\ndescription: >\n  Execute a registered Workline Work.\n---\n"))

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
        for rule in SKILL_RULES + (sa.RULE_BOOTSTRAP_DIFFERS, sa.RULE_BOOTSTRAP_NOT_REGULAR_FILE):
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
        self.assertTrue(found.bootstrap_inspected)
        self.assertFalse(found.complete)
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


class LimitTests(ShadowCase):
    """RB6A-L4: every limit applies per Skill directory, so no name or order changes another Skill's result."""

    def setUp(self) -> None:
        super().setUp()
        self.canonical_bootstrap()

    def _build(self, root: Path, big: str) -> None:
        self.canonical_bootstrap(root)
        for index in range(6):
            self.write(f".claude/skills/{big}/part-{index}.md", "x", root)
        self.skill(big, CLAIMING_SKILL, root)
        for name in ("mmm-tracker", "nnn-tracker"):
            self.skill(name, CLAIMING_SKILL, root)

    def test_an_oversized_skill_directory_affects_only_itself_whatever_its_name(self) -> None:
        results = {}
        with mock.patch.object(sa, "MAX_UNIT_ENTRIES", 5):
            for big in ("aaa-big", "zzz-big"):
                root = self.new_dir(f"limit-{big}")
                self._build(root, big)
                found = self.detect(root)
                results[big] = found
                self.assertEqual((sa.Uninspected(f".claude/skills/{big}", sa.UNINSPECTED_LIMIT),), found.uninspected)
                self.assertNotIn(f".claude/skills/{big}/SKILL.md", {item.path for item in found.evidence})
                self.assertNotIn(f".claude/skills/{big}/SKILL.md", sa.source_paths(root))
        self.assertEqual(results["aaa-big"].evidence, results["zzz-big"].evidence)
        self.assertEqual({".claude/skills/mmm-tracker/SKILL.md", ".claude/skills/nnn-tracker/SKILL.md"},
                         {item.path for item in results["aaa-big"].evidence})

    def test_too_deep_or_too_many_skill_files_affect_only_their_directory(self) -> None:
        deep = "/".join(f"d{index}" for index in range(4))
        self.skill(f"deep/{deep}", CLAIMING_SKILL)
        for index in range(3):
            self.skill(f"many/s{index}", CLAIMING_SKILL)
        self.skill("plain", CLAIMING_SKILL)
        with mock.patch.object(sa, "MAX_SKILL_DEPTH", 3), mock.patch.object(sa, "MAX_UNIT_SKILL_FILES", 2):
            found = self.detect()
        self.assertEqual((sa.Uninspected(".claude/skills/deep", sa.UNINSPECTED_LIMIT),
                          sa.Uninspected(".claude/skills/many", sa.UNINSPECTED_LIMIT)), found.uninspected)
        self.assertEqual({".claude/skills/plain/SKILL.md"}, {item.path for item in found.evidence})

    def test_too_many_skill_directories_report_the_whole_source_and_no_partial_evidence(self) -> None:
        for name in ("aaa-tracker", "zzz-tracker", "domain"):
            self.skill(name, CLAIMING_SKILL if "tracker" in name else DOMAIN_SKILL)
        with mock.patch.object(sa, "MAX_SKILL_UNITS", 2):
            found = self.detect()
            paths = sa.source_paths(self.root)
        self.assertEqual((), found.evidence)
        self.assertEqual((sa.Uninspected(".claude/skills", sa.UNINSPECTED_LIMIT),), found.uninspected)
        self.assertFalse(found.complete)
        self.assertEqual((BOOTSTRAP_REL_PATH,), paths)


class OddNameTests(ShadowCase):
    """RB6A-L3: one name Windows cannot decode as UTF-16 never disables a whole source."""

    ODD = "odd-" + chr(0xD800) + "-name.txt"

    def test_an_undecodable_name_hides_neither_the_bootstrap_nor_the_skills(self) -> None:
        if not WINDOWS:
            self.skipTest("an unpaired UTF-16 surrogate in a file name is a Windows case")
        target = self.outside / "wl"
        target.mkdir()
        self.write("SKILL.md", bs.render_bootstrap(), target)
        (self.root / ".claude" / "skills").mkdir(parents=True)
        self.junction(".claude/skills/workline", target)
        tracker = self.skill("tracker", CLAIMING_SKILL)
        before = self.detect()
        for where in ("", ".claude/", ".claude/skills/", ".claude/skills/tracker/"):
            try:
                (self.root / (where + self.ODD)).write_bytes(b"x")
            except (OSError, UnicodeError):
                self.skipTest("this file system refuses an unpaired surrogate name")
        after = self.detect()
        self.assertEqual(before, after)
        self.assertEqual(sa.CONFIRMED, after.status)
        self.assertEqual({(BOOTSTRAP_REL_PATH, sa.RULE_BOOTSTRAP_INDIRECTION)} | {
            (tracker, rule) for rule in (sa.RULE_SKILL_PARALLEL_LIFECYCLE, sa.RULE_SKILL_PARALLEL_PROGRESSION,
                                         sa.RULE_SKILL_AUTHORITY_OVERRIDE)}, self.rules(after))
        self.assertEqual((), after.uninspected)


# --------------------------------------------------------------------------- RB8-FC-04: the read set


class ReadSetTests(ShadowCase):
    DECOYS = ("README.md", "BACKLOG.md", "TODO.md", "STATUS.md", "CLAUDE.md", "decoy-legacy-tracker.md",
              ".claude/CLAUDE.md", ".claude/settings.json", ".claude/commands/backlog.md", "docs/BACKLOG.md",
              ".claude/skills/README.md")
    SKILL_DECOYS = ("notes.md", "decoy-secret.env", "README.md", "skill.yaml", "SKILL.md.bak", "sub/README.md")

    def setUp(self) -> None:
        super().setUp()
        self.canonical_bootstrap()
        for name in self.DECOYS:
            self.write(name, CLAIMING_SKILL)
        for skill in ("tracker", "deploy"):
            self.skill(skill, CLAIMING_SKILL if skill == "tracker" else DOMAIN_SKILL)
            for name in self.SKILL_DECOYS:
                self.write(f".claude/skills/{skill}/{name}", CLAIMING_SKILL)
        self.decoy_names = {Path(name).name for name in self.DECOYS + self.SKILL_DECOYS}

    def test_source_paths_enumerates_exactly_the_three_v1_file_sources(self) -> None:
        self.assertEqual(
            (BOOTSTRAP_REL_PATH, ".claude/skills/deploy/SKILL.md", ".claude/skills/tracker/SKILL.md"),
            sa.source_paths(self.root),
        )

    def test_exactly_the_enumerated_files_are_read(self) -> None:
        """Every bound read, by its full Project-relative path: the read set IS ``source_paths``."""
        read: list[str] = []
        real = fsafe.SafeDirectory.read_file_bound

        def recording(directory, name):
            read.append(Path(os.path.relpath(os.path.join(directory.described, name), self.root)).as_posix())
            return real(directory, name)

        expected = sa.source_paths(self.root)
        with mock.patch.object(fsafe.SafeDirectory, "read_file_bound", recording):
            found = self.detect()
        self.assertEqual(list(expected), read)
        self.assertEqual({".claude/skills/tracker/SKILL.md"}, {item.path for item in found.evidence})

    def test_no_decoy_is_opened_at_the_operating_system_level(self) -> None:
        """Every open the platform performs: Windows ``NtCreateFile`` / ``CreateFileW``, POSIX ``open`` audit events."""
        expected = sa.source_paths(self.root)
        if WINDOWS:
            opened: list[tuple[str, bool]] = []
            real_nt, real_create = fsafe._nt_open, fsafe._CreateFileW

            def nt_open(root, name, access, share, disposition, options):
                opened.append((name, bool(access & fsafe._GENERIC_READ)))
                return real_nt(root, name, access, share, disposition, options)

            def create(path, access, share, attributes, disposition, flags, template):
                opened.append((os.path.basename(path), bool(access & fsafe._GENERIC_READ)))
                return real_create(path, access, share, attributes, disposition, flags, template)

            with mock.patch.object(fsafe, "_nt_open", nt_open), mock.patch.object(fsafe, "_CreateFileW", create):
                self.detect()
            data_reads = [name for name, reads in opened if reads]
        else:
            global _AUDITED, _AUDIT_INSTALLED
            if not _AUDIT_INSTALLED:
                sys.addaudithook(_audit)
                _AUDIT_INSTALLED = True
            _AUDITED = []
            try:
                self.detect()
            finally:
                audited, _AUDITED = _AUDITED, None
            opened = [(Path(name).name, not flags & getattr(os, "O_DIRECTORY", 0)) for name, flags in audited]
            data_reads = [name for name, reads in opened if reads]
        self.assertEqual(len(expected), len(data_reads), "one data open per enumerated source, and no other")
        self.assertEqual({"SKILL.md"}, set(data_reads))
        for decoy in self.decoy_names:
            with self.subTest(decoy=decoy):
                self.assertNotIn(decoy, {name for name, _ in opened})

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
                self.assertTrue(found.complete)

    def test_an_observation_confirms_alongside_static_suspicion_but_never_promotes_it(self) -> None:
        skill = self.skill("tracker", CLAIMING_SKILL)
        alone = self.detect()
        self.assertEqual(sa.SUSPECTED, alone.status)
        self.assertEqual(alone, self.detect(observed=()))
        seen = sa.ObservedEvidence(sa.OBSERVED_WRITE, "TODO.md", sa.PROGRESSION, "skills/start")
        found = self.detect(observed=(seen,))
        self.assertEqual(sa.CONFIRMED, found.status)
        self.assertEqual({"TODO.md"}, {item.path for item in found.confirmed})
        self.assertTrue(all(item.level == sa.SUSPECTED for item in found.evidence if item.path == skill))

    def test_observed_evidence_is_strict_and_frozen(self) -> None:
        good = dict(kind=sa.OBSERVED_WRITE, artifact="TODO.md", responsibility=sa.PROGRESSION, observed_by="skills/start")
        bad = (
            ("kind", "suspected"), ("kind", "semantic"), ("kind", "guess"), ("kind", "Write"),
            ("responsibility", "lifecycle"), ("responsibility", ""),
            ("artifact", ""), ("artifact", "/abs/TODO.md"), ("artifact", "C:/TODO.md"), ("artifact", "C:TODO.md"),
            ("artifact", "a\\b.md"), ("artifact", "../TODO.md"), ("artifact", "a/../b.md"), ("artifact", "./a.md"),
            ("artifact", "a//b.md"), ("artifact", "a/"), ("artifact", "TODO\n.md"), ("artifact", "x" * 513),
            ("artifact", ".workline/works/w.md"), ("artifact", ".WORKLINE/x"), ("artifact", ".workline"),
            ("artifact", ".workline."), ("artifact", ".workline "), ("artifact", ".workline./x"), ("artifact", "a./b"),
            ("artifact", "TODO.md::$DATA"), ("artifact", BOOTSTRAP_REL_PATH), ("artifact", BOOTSTRAP_REL_PATH.upper()),
            ("artifact", ".claude/skills/workline"), ("artifact", ".claude"), ("artifact", ".claude/skills"),
            ("observed_by", ""), ("observed_by", "Skills/Start"), ("observed_by", "skills/start/extra"),
            ("observed_by", "a guess"), ("observed_by", "skills/tracker"), ("observed_by", "attacker"),
            ("observed_by", "rules/anything"), ("observed_by", "start"),
            ("artifact", Path("TODO.md")), ("kind", None), ("observed_by", 1),
        )
        sa.ObservedEvidence(**good)
        sa.ObservedEvidence(**{**good, "artifact": ".claude/skills/workline/extra/SKILL.md"})  # a local Skill, not it
        for observer in sa.OBSERVERS:
            sa.ObservedEvidence(**{**good, "observed_by": observer})
        self.assertEqual(set(REQUIRED_SKILL_IDS) | {"project-policy-change"}, set(sa.OBSERVERS))
        for field_name, value in bad:
            with self.subTest(field=field_name, value=value):
                with self.assertRaises(ValueError):
                    sa.ObservedEvidence(**{**good, field_name: value})
        seen = sa.ObservedEvidence(**good)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            seen.kind = sa.OBSERVED_ROUTE  # type: ignore[misc]

    def test_anything_but_a_valid_observed_evidence_record_never_promotes(self) -> None:
        class Lookalike(sa.ObservedEvidence):
            pass

        def forged(**values):
            record = object.__new__(sa.ObservedEvidence)
            for name, value in values.items():
                object.__setattr__(record, name, value)
            return record

        smuggled = (
            {"kind": "write", "artifact": "TODO.md", "responsibility": "progression", "observed_by": "skills/start"},
            ("write", "TODO.md", "progression", "skills/start"),
            "confirmed",
            Lookalike(sa.OBSERVED_WRITE, "TODO.md", sa.PROGRESSION, "skills/start"),
            forged(kind="write", artifact="C:\\Users\\secret\\TODO.md", responsibility="progression",
                   observed_by="skills/start"),
            forged(kind="write", artifact=BOOTSTRAP_REL_PATH, responsibility="progression", observed_by="skills/start"),
            forged(kind="write", artifact="TODO.md"),
        )
        found = self.detect(observed=smuggled)
        self.assert_none(found)
        self.assertEqual(
            tuple(sa.Uninspected(f"observed[{index}]", sa.UNINSPECTED_OBSERVATION_REJECTED)
                  for index in range(len(smuggled))),
            found.uninspected,
        )
        self.assertNotIn("secret", json.dumps(found.to_json()))
        self.assertFalse(found.complete)


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
            {"status", "advisory", "bootstrap_inspected", "complete", "confirmed_count", "suspected_count", "evidence",
             "uninspected"},
            set(data),
        )
        self.assertEqual((sa.CONFIRMED, True, True, True, 1),
                         (data["status"], data["advisory"], data["bootstrap_inspected"], data["complete"],
                          data["confirmed_count"]))
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

    def test_the_entry_point_takes_a_project_root_path_or_a_store_and_refuses_anything_else(self) -> None:
        self.write(BOOTSTRAP_REL_PATH, "differs\n")
        expected = self.detect()
        self.assertEqual(expected, sa.detect_shadow_authority(str(self.root)))
        self.assertEqual(expected, sa.detect_shadow_authority(ProjectStore(self.root)))
        self.assertEqual(sa.source_paths(self.root), sa.source_paths(ProjectStore(self.root)))
        refused = sa.ShadowDiagnostic(sa.NONE, (), (sa.Uninspected(".", sa.UNINSPECTED_ROOT_REFUSED),))
        self.enter(self.root)  # the working directory holds a differing bootstrap: "" must never read it
        for value in ("", "   ", None, 5, b"proj", str(self.root) + "\0x", object()):
            with self.subTest(value=value):
                found = sa.detect_shadow_authority(value)  # type: ignore[arg-type]
                self.assertEqual(refused, found)
                self.assertFalse(found.bootstrap_inspected)
                self.assertEqual((), sa.source_paths(value))  # type: ignore[arg-type]

    def test_the_evidence_order_never_depends_on_the_hash_seed(self) -> None:
        """RB6A-L1: observations that differ only in their responsibility, in four separate processes."""
        self.skill("tracker", CLAIMING_SKILL)
        script = (
            "import json, sys\n"
            "from workline import shadow_authority as sa\n"
            "obs = [sa.ObservedEvidence('write', 'TODO.md', r, 'skills/start') for r in sa.RESPONSIBILITIES]\n"
            "obs += [sa.ObservedEvidence('route', 'TODO.md', r, o) for r in sa.RESPONSIBILITIES[:3] for o in sa.OBSERVERS]\n"
            "print(json.dumps(sa.detect_shadow_authority(sys.argv[1], observed=obs).to_json()))\n"
        )
        outputs = set()
        for seed in ("0", "1", "2", "3"):
            env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(Path(sa.__file__).resolve().parents[1])}
            completed = subprocess.run([sys.executable, "-B", "-c", script, str(self.root)], capture_output=True,
                                       text=True, env=env, timeout=300)
            self.assertEqual(0, completed.returncode, completed.stderr)
            outputs.add(completed.stdout)
        self.assertEqual(1, len(outputs), "one order, whatever the seed")

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

    def test_every_public_name_is_exported(self) -> None:
        """RB6A-L8: the vocabularies a consumer compares against are importable by name."""
        public: set[str] = set()
        for node in ast.parse(Path(sa.__file__).read_text(encoding="utf-8")).body:  # names this module defines
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                public.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                public.update(target.id for target in targets if isinstance(target, ast.Name))
        public = {name for name in public if not name.startswith("_")}
        self.assertIn("detect_shadow_authority", public)
        self.assertEqual(set(), public - set(sa.__all__))
        for name in sa.__all__:
            self.assertTrue(hasattr(sa, name), name)
        for group in (sa.SOURCES, sa.RESPONSIBILITIES, sa.UNINSPECTED_REASONS, sa.INDIRECTION_KINDS, sa.RULES):
            self.assertEqual(len(group), len(set(group)))


# --------------------------------------------------------------------------- §30.28 / §30.39: advisory only


class AdvisoryOnlyTests(ShadowCase):
    def test_the_detector_never_raises(self) -> None:
        missing = self.tmp / "missing"
        found = self.detect(missing)
        self.assert_none(found)
        self.assertEqual((sa.Uninspected(".", sa.UNINSPECTED_UNREADABLE),), found.uninspected)
        self.assertFalse(found.bootstrap_inspected)
        a_file = self.write("plain.txt", "x\n", self.tmp)
        self.assert_none(self.detect(a_file))

        def exploding():
            yield sa.ObservedEvidence(sa.OBSERVED_WRITE, "TODO.md", sa.PROGRESSION, "skills/start")
            raise RuntimeError("an observer failed")

        found = self.detect(observed=exploding())
        self.assertIn(sa.Uninspected("observed", sa.UNINSPECTED_FAILED), found.uninspected)
        self.skill("tracker", CLAIMING_SKILL)
        with mock.patch.object(sa, "_entries", side_effect=RuntimeError("listing failed")):
            found = self.detect()
        self.assertEqual({sa.Uninspected(BOOTSTRAP_REL_PATH, sa.UNINSPECTED_FAILED),
                          sa.Uninspected(".claude/skills", sa.UNINSPECTED_FAILED)}, set(found.uninspected))
        self.assertEqual(sa.NONE, found.status)
        self.assertFalse(found.bootstrap_inspected)
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
        seen = sa.ObservedEvidence(sa.OBSERVED_WRITE, "BACKLOG.md", sa.PROGRESSION, "skills/start")
        found = sa.detect_shadow_authority(root, observed=[seen])
        sa.source_paths(root)
        found.to_json()
        found.render_lines()
        after = (snapshot(root), snapshot(self.outside), git(root, "status", "--porcelain", "--untracked-files=all"),
                 git(root, "rev-parse", "HEAD"))
        self.assertEqual(sa.CONFIRMED, found.status)
        self.assertEqual(before, after, "the detector edits, deletes, migrates and backfills nothing")
        self.assertFalse((root / ".workline" / "runtime" / "locks" / "holder.json").exists(), "no lock is taken")

    def test_no_git_lock_mutation_or_process_is_reached_at_run_time(self) -> None:
        """RB6A-L7(c), transitively: whatever the module imports, nothing of that kind is called."""
        from workline import gitcmd, mutation, oplock

        self.canonical_bootstrap()
        self.skill("tracker", CLAIMING_SKILL)
        self.skill("start", (WORKLINE_ROOT / ".claude" / "skills" / "start" / "SKILL.md").read_text(encoding="utf-8"))
        boom = AssertionError("reached")
        with mock.patch.object(gitcmd, "run_git", side_effect=boom), \
                mock.patch.object(mutation.MutationController, "open", side_effect=boom), \
                mock.patch.object(oplock, "project_operation", side_effect=boom), \
                mock.patch("subprocess.Popen", side_effect=boom), \
                mock.patch("socket.socket", side_effect=boom):
            found = self.detect()
            sa.source_paths(self.root)
        self.assertEqual(sa.SUSPECTED, found.status)
        self.assertEqual((), found.uninspected)

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
                          "MutationController", "Effect", "project_operation", "validate"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, names)
        calls = {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                 for node in ast.walk(tree) if isinstance(node, ast.Call)}
        for forbidden in ("open", "write_text", "write_bytes", "mkdir", "makedirs", "unlink", "remove", "rename",
                          "rmdir", "rmtree", "symlink", "create_file_exclusive", "add_effects", "apply",
                          "commit", "push", "reserve_id", "backfill_bootstrap", "project_start", "system", "popen",
                          "utime", "chmod", "truncate"):
            with self.subTest(call=forbidden):
                self.assertNotIn(forbidden, calls)
        attributes: dict[str, set[str]] = {"bootstrap": set(), "fsafe": set()}
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in attributes:
                attributes[node.value.id].add(node.attr)
        self.assertEqual({"render_bootstrap", "_normalize"}, attributes["bootstrap"],
                         "only the canonical text and its normalization come from the bootstrap owner")
        self.assertEqual({"SafeDirectory", "Entry", "walk", "IO_REPARSE_TAG_MOUNT_POINT", "IO_REPARSE_TAG_SYMLINK"},
                         attributes["fsafe"])
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
        self.assertTrue(found.complete)
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

    def test_projectstart_is_unchanged_and_status_reports_none_for_a_fresh_project(self) -> None:
        """RB6A-IR-2, after RB6-F integrates status.py: §15.7 "RB6 does not change ProjectSTART" on the integrated tree."""
        from workline import project_start
        from workline.status import build_status

        store = self.new_project("project")
        policy = build_status(store.root).data["policy"]
        self.assertEqual(sa.detect_shadow_authority(store.root).to_json(), policy["shadow_authority"])
        self.assertEqual(sa.NONE, policy["shadow_authority"]["status"])
        self.assertTrue(policy["shadow_authority"]["complete"])
        self.assertEqual(bs.render_bootstrap().encode("utf-8"), (store.root / BOOTSTRAP_REL_PATH).read_bytes())
        tracked = git(store.root, "ls-files").splitlines()
        self.assertFalse([path for path in tracked if "shadow" in path.lower()])
        for module in (project_start, bs):
            self.assertNotIn("shadow_authority", Path(module.__file__).read_text(encoding="utf-8"))
        skill = (WORKLINE_ROOT / ".claude" / "skills" / "project-start" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("shadow", skill.lower())


class SharedIntegrationTests(ShadowCase):
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
