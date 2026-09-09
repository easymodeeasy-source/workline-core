from __future__ import annotations

import unittest
from unittest import mock

from helpers import WorklineTestCase
from workline import yamlish
from workline.durable import DurableWriteError, durable_write_text


class YamlishTests(unittest.TestCase):
    def test_roundtrip_nested_structures(self) -> None:
        doc = {
            "workline": {"root": "D:\\AIproject\\workline core"},
            "relations": [],
            "items": [
                {"id": "rel_1", "type": "planned_next", "from": "p_1", "to": "p_2", "condition": {"kind": "path_glob", "pattern": "src/**"}},
                {"a": None, "b": True, "c": 3, "d": "multi\nline: x #y", "e": ""},
                "plain",
            ],
            "empty": {},
            "text": "日本語 テキスト",
            "numeric_string": "123",
            "colon": "a: b",
            "reserved": "null",
        }
        assert yamlish.load(yamlish.dump(doc)) == doc

    def test_frontmatter_roundtrip(self) -> None:
        text = yamlish.dump_frontmatter({"id": "w_x", "type": "work", "origin": {"type": "standalone"}}, "# name\n\n## state\nbody\n")
        meta, body = yamlish.load_frontmatter(text)
        self.assertEqual(meta, {"id": "w_x", "type": "work", "origin": {"type": "standalone"}})
        self.assertEqual(body, "# name\n\n## state\nbody\n")

    def test_common_hand_written_forms(self) -> None:
        self.assertEqual(yamlish.load("relations: []\n"), {"relations": []})
        self.assertEqual(yamlish.load("relations:\n- id: x\n  type: y\n"), {"relations": [{"id": "x", "type": "y"}]})
        self.assertEqual(yamlish.load("# comment\nrelations:\n  - id: x\n  - id: z\n"), {"relations": [{"id": "x"}, {"id": "z"}]})
        self.assertIsNone(yamlish.load("# only a comment\n"))

    def test_unsupported_syntax_fails_closed(self) -> None:
        with self.assertRaises(yamlish.YamlishError):
            yamlish.load("a: [1, 2]\n")
        with self.assertRaises(yamlish.YamlishError):
            yamlish.load("a: 1\na: 2\n")
        with self.assertRaises(yamlish.YamlishError):
            yamlish.load("a:\n\t- x\n")


class DurableWriteTests(WorklineTestCase):
    def test_write_is_atomic_and_uses_tmp_dir(self) -> None:
        target = self.tmp / "canon" / "file.txt"
        tmp_dir = self.tmp / "runtime" / "tmp"
        durable_write_text(target, "hello\n", tmp_dir=tmp_dir)
        self.assertEqual(target.read_text(encoding="utf-8"), "hello\n")
        self.assertEqual(list((self.tmp / "canon").iterdir()), [target])
        self.assertEqual(list(tmp_dir.iterdir()), [])

    def test_fsync_is_called_before_replace(self) -> None:
        calls: list[str] = []
        real_fsync = __import__("os").fsync
        real_replace = __import__("os").replace

        def fake_fsync(fd):
            calls.append("fsync")
            return real_fsync(fd)

        def fake_replace(src, dst):
            calls.append("replace")
            return real_replace(src, dst)

        with mock.patch("workline.durable.os.fsync", fake_fsync), mock.patch("workline.durable.os.replace", fake_replace):
            durable_write_text(self.tmp / "f.txt", "x")
        self.assertEqual(calls[:2], ["fsync", "replace"])

    def test_failure_leaves_no_partial_target(self) -> None:
        target = self.tmp / "f.txt"
        target.write_text("old", encoding="utf-8")
        with mock.patch("workline.durable.os.replace", side_effect=OSError("boom")):
            with self.assertRaises(DurableWriteError):
                durable_write_text(target, "new")
        self.assertEqual(target.read_text(encoding="utf-8"), "old")
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["f.txt"])


if __name__ == "__main__":
    unittest.main()
