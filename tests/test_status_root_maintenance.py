"""RB1 status carries the P7 root maintenance diagnostics, isolated (§31.46, RB7C-4; IR-RB7-5, shared-surface writer).

``policy.root_maintenance`` is exactly ``_isolated(lambda: root_maintenance.status_report(<configured root>))``:
the configured Workline root's read-only report, or - when the report raises, as it does by design on an unreadable
canonical root record - ``{"status": "unavailable", "reason": {"code": ...}}`` with every other section intact.
The Project's own ``policy.maintenance`` is unchanged by it.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from status_helpers import StatusCase
from workline import root_maintenance
from workline.errors import StopError, ValidationError


class RootMaintenanceStatusTests(StatusCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def test_the_key_is_the_configured_roots_report(self) -> None:
        seen: list[Path] = []

        def report(root: Path) -> dict:
            seen.append(Path(root))
            return {"status": "available", "marker": "report"}

        with mock.patch.object(root_maintenance, "status_report", side_effect=report):
            data = self.data()
        self.assertEqual({"status": "available", "marker": "report"}, data["policy"]["root_maintenance"])
        self.assertEqual([self.store.workline_root()], seen, "the configured root, read once")
        self.assertEqual(root_maintenance.STATUS_KEY, "root_maintenance")

    def test_a_raising_report_renders_that_key_unavailable_and_hides_nothing_else(self) -> None:
        """RB7BD-3: status_report raises by design on an unreadable canonical root record, and status.py's
        ``_isolated`` wrapping is the only guard - pinned here for a StopError and both ValidationErrors."""
        baseline = self.data()
        for raised in (ValidationError("the root record is not canonical", code="review_record_noncanonical"),
                       ValidationError("the root record escapes", code="review_containment"),
                       StopError("the Global policy does not load", code="review_policy_unavailable")):
            with self.subTest(code=raised.code):
                with mock.patch.object(root_maintenance, "status_report", side_effect=raised):
                    data = self.data()
                self.assertEqual({"status": "unavailable", "reason": {"code": raised.code, "message": str(raised)}},
                                 data["policy"]["root_maintenance"])
                self.assertEqual(set(baseline), set(data), "every status section is still present")
                self.assertEqual(set(baseline["policy"]), set(data["policy"]), "every policy part is still present")
                self.assertEqual({key: value for key, value in baseline["policy"].items() if key != "root_maintenance"},
                                 {key: value for key, value in data["policy"].items() if key != "root_maintenance"})
                self.assertEqual({key: value for key, value in baseline.items() if key != "policy"},
                                 {key: value for key, value in data.items() if key != "policy"})

    def test_the_projects_policy_maintenance_is_its_own(self) -> None:
        with mock.patch.object(root_maintenance, "status_report",
                               side_effect=ValidationError("x", code="review_record_noncanonical")):
            data = self.data()
        self.assertEqual({"status": "none", "problems": []}, data["policy"]["maintenance"])
