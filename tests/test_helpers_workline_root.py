"""The shared test helper ``copy_workline_root`` (IR-RB7-6, RB7C-7 / RB8 I-RB7-3; written by the shared-surface writer).

A copied Workline root carries what the real root's loader and runtime rely on: the root ``.gitignore`` (which
ignores ``.workline-root-runtime/``) and, when the root tracks it, the materialized Global policy file - byte for
byte - besides the registry, launcher, canonical Skills and sources it always carried. No ``.workline`` is created.
"""

from __future__ import annotations

import unittest

from helpers import LAUNCHER_NAME, WORKLINE_ROOT, WorklineTestCase, copy_workline_root

GLOBAL_POLICY = ("review-policy", "global-policy.yaml")


class CopyWorklineRootTests(WorklineTestCase):
    def test_the_copy_carries_the_gitignore_and_the_tracked_global_policy(self) -> None:
        copied = copy_workline_root(self.tmp / "root")
        for parts in ((".gitignore",), GLOBAL_POLICY, ("registry.md",), (LAUNCHER_NAME,)):
            source = WORKLINE_ROOT.joinpath(*parts)
            if not source.is_file():
                continue
            with self.subTest(path="/".join(parts)):
                self.assertEqual(source.read_bytes(), copied.joinpath(*parts).read_bytes())
        self.assertTrue((copied / ".gitignore").is_file())
        self.assertEqual(WORKLINE_ROOT.joinpath(*GLOBAL_POLICY).is_file(), copied.joinpath(*GLOBAL_POLICY).is_file())
        self.assertFalse((copied / ".workline").exists())
        self.assertEqual({"review-policy/global-policy.yaml"} if copied.joinpath(*GLOBAL_POLICY).is_file() else set(),
                         {path.relative_to(copied).as_posix() for path in (copied / "review-policy").rglob("*")
                          if path.is_file()} if (copied / "review-policy").exists() else set(),
                         "only the Global policy file comes along from review-policy/")

    def test_a_replacement_registry_still_replaces_only_the_registry(self) -> None:
        copied = copy_workline_root(self.tmp / "root", registry="# registry\n")
        self.assertEqual("# registry\n", (copied / "registry.md").read_text(encoding="utf-8"))
        self.assertEqual((WORKLINE_ROOT / ".gitignore").read_bytes(), (copied / ".gitignore").read_bytes())


if __name__ == "__main__":
    unittest.main()
