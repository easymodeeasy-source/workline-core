"""A START derivation's text is refused before it is kept or registered when the record or reader cannot carry it.

RB10 N3 (HD-1), START's own boundary: the Works a ``Derive`` (or a ``HumanNG``'s fix Works) decides carry the
executor's text. A name the canonical reader would read back as another name (a line break, a ``str.splitlines``
separator, surrounding whitespace, a heading), a desired state that adds or splits a section heading, and a value
the recovery record cannot carry (a lone surrogate, a tuple in a condition, an endpoint that names nothing) are
refused as ``input_unrepresentable`` before the derivation is kept and before its registration reserves an ID.
Before this, the first group was registered and read back as something else, and the second crashed after the
executor ran, inside the registration. A derivation the record already holds is carried on from that record.
"""

from __future__ import annotations

import unittest

from helpers import WorklineTestCase, scripted_executor
from workline import start as st
from workline.create import RelatedSpec, RelationSpec
from workline.errors import ValidationError
from workline.mutation import MutationController
from workline.state import ProjectView

CODE = "input_unrepresentable"
LONE = chr(0xD800)
COND = {"kind": "path_glob", "pattern": "src/*.py"}


class DerivationInputTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        roadmap = self.simple_roadmap(self.store)
        self.w1 = self.simple_entry(self.store, roadmap.phase_ids["a"]).work_ids["w1"]

    def names(self) -> set[str]:
        return {work.name for work in ProjectView.load(self.store).works.values()}

    def assertRefusedBeforeKeptOrRegistered(self, derive: st.Derive) -> None:
        before = self.names()
        with self.assertRaises(ValidationError) as refused:
            # Completed() follows so that a derivation that is NOT refused ends this START instead of being decided
            # again and again (the scripted executor repeats its last outcome): a regression fails, it never hangs.
            st.start(self.store, self.w1, "single-work", scripted_executor({self.w1: [derive, st.Completed()]}))
        self.assertEqual(CODE, refused.exception.code, refused.exception.message)
        self.assertEqual(before, self.names(), "no Work registered")
        for record in MutationController(self.store).list_pending():
            self.assertNotIn("derivations", record.get("notes") or {}, "the derivation was not kept")
            self.assertFalse([key for key in record.get("reserved_ids") or {} if ":derive" in key], "no ID reserved")
        self.assertEqual([], sorted(p.name for p in self.store.tmp.iterdir()), "no temporary file")

    def test_a_derived_name_or_desired_state_read_back_as_another_value_is_refused(self) -> None:
        for label, work in {
            "LF in the name": st.DerivedWork("Fix\nit", "fixed"),
            "padded name": st.DerivedWork(" Fix ", "fixed"),
            "U+2028 in the name": st.DerivedWork("Fix\N{LINE SEPARATOR}it", "fixed"),
            "heading in the desired state": st.DerivedWork("Fix", "a\n## このWorkで成立させる状態\nb"),
        }.items():
            with self.subTest(label):
                self.assertRefusedBeforeKeptOrRegistered(st.Derive({"fix": work}))

    def test_a_value_the_record_cannot_carry_is_refused_instead_of_crashing(self) -> None:
        for label, derive in {
            "lone surrogate in the name": st.Derive({"fix": st.DerivedWork(f"Fix{LONE}", "fixed")}),
            "tuple in a condition": st.Derive({"fix": st.DerivedWork(
                "Fix", "fixed", related=(RelatedSpec("conditional_must_read", "x.md", {**COND, "t": ("a",)}),))}),
            "an endpoint that names nothing": st.Derive(
                {"fix": st.DerivedWork("Fix", "fixed")}, relations=(RelationSpec("planned_next", "fix", 3),)),
        }.items():
            with self.subTest(label):
                self.assertRefusedBeforeKeptOrRegistered(derive)

    def test_a_valid_derivation_still_registers_and_a_retry_completes(self) -> None:
        refused = st.Derive({"fix": st.DerivedWork("Fix\nit", "fixed")})
        with self.assertRaises(ValidationError):
            st.start(self.store, self.w1, "single-work", scripted_executor({self.w1: [refused, st.Completed()]}))
        derive = st.Derive({"fix": st.DerivedWork("Fix", "a\n- multiline\r\nwith CRLF")})
        result = st.start(self.store, self.w1, "single-work", scripted_executor({self.w1: [derive, st.Completed()]}))
        self.assertEqual("completed", result.status)
        self.assertIn("Fix", self.names())


if __name__ == "__main__":
    unittest.main()
