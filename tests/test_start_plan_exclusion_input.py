"""START's standalone plan exclusion refuses a request its record cannot carry before anything is begun (RB10 N3(b)).

A target or a replan holding a value the recovery record cannot carry - text with a lone surrogate, a tuple in a
condition, a removal ID that names nothing - used to escape as a raw ``UnicodeEncodeError`` / ``YamlishError`` when
the mutation was opened. It is refused as ``input_unrepresentable`` before the execution lock, or before the
mutation is opened, exactly as Roadmap's plan exclusion refuses it. A replan whose new Work name the canonical
reader would read back as another name is refused where every replan is decided (``ops.plan_replan``).
"""

from __future__ import annotations

import unittest

from helpers import WorklineTestCase
from workline import oplock
from workline import start as st
from workline.create import RelatedSpec, WorkSpec, create_standalone_work
from workline.errors import ValidationError
from workline.mutation import MutationController
from workline.ops import Replan
from workline.state import ProjectView

CODE = "input_unrepresentable"
LONE = chr(0xD800)
COND = {"kind": "path_glob", "pattern": "src/*.py"}


class StandalonePlanExclusionInputTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.solo = create_standalone_work(self.store, WorkSpec("Solo", "solo done")).work_id

    def assertRefusedBeforeAnything(self, call) -> None:
        records = MutationController(self.store).list_records()
        with self.assertRaises(ValidationError) as refused:
            call()
        self.assertEqual(CODE, refused.exception.code, refused.exception.message)
        self.assertEqual(records, MutationController(self.store).list_records(), "no mutation was opened")
        self.assertEqual("unstarted", ProjectView.load(self.store).work_state(self.solo).state)
        self.assertEqual([], sorted(p.name for p in self.store.tmp.iterdir()), "no temporary file")
        self.assertIsNone(oplock.held_lock(self.store))

    def test_values_the_record_cannot_carry_are_refused(self) -> None:
        for label, replan in {
            "lone surrogate in a new Work name": Replan(new_works={"n": WorkSpec(f"N{LONE}", "n")}),
            "lone surrogate in a new Work's Related target": Replan(new_works={"n": WorkSpec(
                "N", "n", related=(RelatedSpec("must_read", f"a{LONE}"),))}),
            "tuple in a condition": Replan(new_works={"n": WorkSpec(
                "N", "n", related=(RelatedSpec("conditional_must_read", "x.md", {**COND, "t": ("a",)}),))}),
            "lone surrogate in a removal ID": Replan(remove_relation_ids=(f"rel_{LONE}",)),
            "an unhashable removal ID": Replan(remove_relation_ids=(["rel"],)),
        }.items():
            with self.subTest(label):
                self.assertRefusedBeforeAnything(lambda replan=replan: st.plan_exclude_standalone_work(self.store, self.solo, replan))
        self.assertRefusedBeforeAnything(lambda: st.plan_exclude_standalone_work(self.store, 5))

    def test_a_valid_replan_still_excludes(self) -> None:
        result = st.plan_exclude_standalone_work(self.store, self.solo, Replan(new_works={"n": WorkSpec("New", "a\r\nb")}))
        self.assertEqual("plan_excluded", result.status)
        self.assertIn("New", {work.name for work in ProjectView.load(self.store).works.values()})


if __name__ == "__main__":
    unittest.main()
