"""RB11 U2-E lane F2 (core): P7 (Global Policy Change, Workline root) CONTROL for the entry-window finding.

P7 checks the root's branch and base in ``global_policy._freeze_entry`` BEFORE ``_open_change`` opens its root mutation,
so a detached HEAD leaves no root mutation record at all (measured, not read). Pinned so a later reordering is seen.
"""

from __future__ import annotations

import global_policy_helpers as gph
from workline.errors import StopError


class P7DetachedHeadControlTests(gph.GlobalPolicyCase):
    def test_a_detached_root_head_leaves_no_root_mutation_record_at_all(self) -> None:
        branch = self.git("symbolic-ref", "--short", "HEAD").strip()
        self.git("checkout", "-q", "--detach", "HEAD")
        with self.assertRaises(StopError) as raised:
            self.change()
        self.assertEqual("detached_head", raised.exception.code)
        self.assertEqual([], self.runtime_records(), "no record of any status: nothing was opened")
        self.assertEqual([], self.pending_records())
        self.git("checkout", "-q", branch)
        self.assertEqual("applied", self.change().status, "nothing is stranded")
