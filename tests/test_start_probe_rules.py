"""RB11 RT-1a, the admission rule itself, unit by unit (ADM §A.1 / §A.2; PO-30, PO-45).

A refusal START's walk meets is ``pending_reconcile_required`` only when all three hold:
it is a ``ReconcileRequired``; it carries a check ID (``errors.with_check``); and that
ID is on the ALLOW list of the very step START was at. Nothing else - the message
text, ``code``, ``reason``, an ALLOW ID of another step - ever admits one.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from workline import start_probe
from workline.errors import ReconcileRequired, StopError, ValidationError, with_check
from workline.store import ProjectStore


def walk() -> start_probe._Walk:
    return start_probe._Walk(ProjectStore(Path(".")), {"mutation_id": "mut_x", "invocation": {}}, [])


class AdmissionRuleTests(unittest.TestCase):
    def decide(self, step: str, exc: BaseException) -> start_probe.StartProbe:
        return walk().refused(step, exc).found

    def test_an_allow_id_of_its_own_step_on_a_reconcile_is_admitted(self) -> None:
        for step, ids in start_probe.ALLOW.items():
            for check in ids:
                with self.subTest(step=step, check=check):
                    found = self.decide(step, with_check(ReconcileRequired("x: reconcile required"), check))
                    self.assertEqual((found.classification, found.check_id, found.step),
                                     (start_probe.PENDING_RECONCILE, check, step))

    def test_an_allow_id_of_another_step_is_never_admitted(self) -> None:
        steps = list(start_probe.ALLOW) + ["S1.2", "S3.1", "S3.5", "S4.2", "S6.2", "S7.1", "S7.2", "S8"]
        for step in steps:
            for owner, ids in start_probe.ALLOW.items():
                for check in ids:
                    if check in start_probe.ALLOW.get(step, frozenset()):
                        continue
                    with self.subTest(step=step, check=check):
                        found = self.decide(step, with_check(ReconcileRequired("x: reconcile required"), check))
                        self.assertEqual(found.classification, start_probe.UNKNOWN_OR_INVALID)

    def test_never_by_message_code_or_reason(self) -> None:
        for exc in (ReconcileRequired("a cancel recorded without its decision: reconcile required"),
                    ReconcileRequired("x", reason="review_marker_mismatch"),
                    with_check(ReconcileRequired("x: reconcile required"), "start.2461"),
                    with_check(ReconcileRequired("x: reconcile required"), "start.9999"),
                    with_check(ReconcileRequired("x: reconcile required"), 2282)):
            with self.subTest(exc=repr(exc), check=getattr(exc, "check_id", None)):
                self.assertEqual(self.decide("S3.4", exc).classification, start_probe.UNKNOWN_OR_INVALID)

    def test_only_a_reconcile_is_admitted(self) -> None:
        for exc in (with_check(StopError("x", code="reconcile_required"), "start.2282"),
                    with_check(ValidationError("x"), "start.2282"), with_check(KeyError("x"), "start.2282")):
            with self.subTest(type=type(exc).__name__):
                self.assertEqual(self.decide("S3.4", exc).classification, start_probe.UNKNOWN_OR_INVALID)

    def test_an_unknown_reason_names_the_step_and_the_check_and_nothing_else(self) -> None:
        """RB11 repair RTR-3: the reason is today's code; its message names the step and the check ID only."""
        secret = "PAYLOAD-from-the-record-31f"
        for exc in (with_check(ReconcileRequired(f"{secret}: reconcile required"), "start.2461"),
                    with_check(StopError(f"{secret}", code="dirty_overlap"), "start.916"),
                    ValidationError(f"{secret}", code=f"{secret}-code")):
            with self.subTest(exc=type(exc).__name__):
                found = self.decide("S3.4", exc)
                self.assertEqual((found.code, found.check_id), (start_probe.NO_PROBE, getattr(exc, "check_id", None)))
                self.assertNotIn(secret, found.message)
                self.assertNotIn(exc.code, found.message, "not even the refusal's own code")
                self.assertIn("S3.4", found.message)

    def test_the_s1_1_other_value_reason_is_todays_text_exactly(self) -> None:
        """RB11 repair RTR-4: the base status.py message for an owner without a probe, word for word."""
        found = start_probe.inspect(ProjectStore(Path(".")), {"owner": "start", "invocation": {"operation": "zz"}}, [])
        self.assertEqual((found.code, found.message), (
            "no_read_only_resume_probe",
            "no read-only proof of how start would resume this record exists; status does not assume one"))

    def test_a_write_start_would_make_is_never_a_refusal(self) -> None:
        found = self.decide("S7.2", start_probe._ProbeWouldWrite("would write"))
        self.assertEqual((found.classification, found.code), (start_probe.UNKNOWN_OR_INVALID, start_probe.NO_PROBE))

    def test_inspect_never_raises(self) -> None:
        found = start_probe.inspect(ProjectStore(Path("Z:/no-such-project")), {"invocation": None}, [])
        self.assertEqual(found.classification, start_probe.UNKNOWN_OR_INVALID)


if __name__ == "__main__":
    unittest.main()
