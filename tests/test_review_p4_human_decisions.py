"""P4-R7 (Work): repeated HUMAN_WAIT decisions inside one pending START mutation (G-4).

A Work START stays pending across HUMAN_WAIT, and a current cycle may wait more than once, so the START's
durable Human-decision binding is one per waiting Run (waiting Review Run ID -> decision), never one per
mutation. T-H1 .. T-H6 drive the real START owner with scripted, terminating actors (``Crash`` is the
BaseException a killed process looks like); nothing here shortcuts production code.
"""

from __future__ import annotations

from typing import Any
from unittest import mock

from test_review_p4_planning import Discovery
from test_review_p4_work import P4WorkCase, work_p4
from test_work_terminal import Crash
from workline import start as st
from workline import start_review as sr
from workline.errors import StopError
from workline.review import p4, records
from workline.review.store import ReviewStore

D1 = p4.HumanDecision("hd-1", p4.DECISION_CONFIRMED)
D1_OTHER = p4.HumanDecision("hd-1b", p4.DECISION_CHANGED)
D2 = p4.HumanDecision("hd-2", p4.DECISION_CHANGED)


def human() -> tuple[p4.P4Claim, ...]:
    return (p4.P4Claim("HIGH", "human", "which format?"),)


class HumanDecisionCase(P4WorkCase):
    def setUp(self) -> None:
        super().setUp()
        # RB4 (Orchestrator decision on the P5-default STOP): every Run these tests create belongs to an explicitly
        # P4-ONLY cycle (the test-only seam; GAP-A item 5 keeps a cycle's first-Run family), so a resume with only
        # p4.HumanDecision is proven unchanged. The P5 twins live in tests/test_review_p5_human_decisions.py.
        from p5_helpers import p4_only_cycle

        seam = p4_only_cycle()
        seam.__enter__()
        self.addCleanup(seam.__exit__, None, None, None)
        self.executor = self.completing(write={"out.txt": b"out\n"}, message="feat: out")

    def start_p4(self, discovery: Discovery, decision: p4.HumanDecision | None = None) -> Any:
        return st.start(self.store, self.work_id, "single-work", self.executor, review=work_p4(discovery, decision=decision))

    def stops(self, code: str, discovery: Discovery, decision: p4.HumanDecision | None = None) -> StopError:
        with self.assertRaises(StopError) as raised:
            self.start_p4(discovery, decision)
        self.assertEqual(code, raised.exception.code, raised.exception)
        return raised.exception

    def crashes(self, name: str, discovery: Discovery, decision: p4.HumanDecision, *, after: bool) -> None:
        """Kill the START at the first call of ``start_review.<name>`` in this invocation (after it returns when
        ``after``)."""
        original = getattr(sr, name)
        calls = {"n": 0}

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            calls["n"] += 1
            if calls["n"] != 1:
                return original(*args, **kwargs)
            if after:
                original(*args, **kwargs)
            raise Crash(f"crash at {name}")

        with mock.patch.object(sr, name, side_effect=wrapper):
            with self.assertRaises(Crash):
                self.start_p4(discovery, decision)

    def bindings(self) -> dict[str, dict]:
        return dict((self.start_record().get("notes") or {}).get(sr.NOTE_P4_DECISIONS) or {})

    def mutation_id(self) -> str:
        return str(self.start_record()["mutation_id"])

    def envelope(self, run_id: str) -> dict:
        review = ReviewStore(self.store)
        first = review.gate_chain(run_id).generations[0]
        return review.read_task_input(str(first.accepted_tasks[0]["task_id"])).request_envelope

    def successor_of(self, run_id: str, reserved: dict[str, str]) -> str | None:
        return reserved.get(f"review-successor-run:{run_id}")

    def wait_first(self, discovery: Discovery) -> str:
        """Invocation 1: no decision, Run A waits at G4 and the START stays pending."""
        self.stops(p4.CODE_HUMAN_WAIT, discovery)
        (waiting,) = self.runs()
        self.assertEqual(4, len(ReviewStore(self.store).gate_chain(waiting).generations))
        self.assertEqual({}, self.bindings())
        return waiting

    def assert_aside_once(self, expected: dict[str, str]) -> None:
        """Every Run is set aside exactly once, as ``human_decision``, by exactly the Run expected to name it."""
        review = ReviewStore(self.store)
        named: dict[str, list[tuple[str, str]]] = {}
        for run_id in self.runs():
            for item in self.envelope(run_id)["set_aside_runs"]:
                named.setdefault(str(item["review_run_id"]), []).append((run_id, str(item["reason"])))
        self.assertEqual({aside: [(by, p4.SET_ASIDE_HUMAN_DECISION)] for aside, by in expected.items()}, named)
        for aside in expected:
            self.assertEqual(4, len(review.gate_chain(aside).generations), f"{aside} stays immutable at G4")
            self.assertEqual(p4.HUMAN_WAIT, review.read_adjudication(aside).outcome)


class HumanDecisionCycleTests(HumanDecisionCase):
    def test_h1_two_waits_two_decisions_one_pending_start_to_completion(self) -> None:
        """T-H1: A waits -> D1 -> successor B -> B waits -> D2 -> successor C -> completion, one START mutation."""
        discovery = Discovery(human(), human(), ())
        a = self.wait_first(discovery)
        mutation_id = self.mutation_id()
        # D1 exits A's wait; B is born from it, waits too, and D1 (already spent on A) never exits B's wait
        self.stops(p4.CODE_HUMAN_WAIT, discovery, D1)
        self.assertEqual(mutation_id, self.mutation_id(), "the same pending START, no competing mutation")
        (b,) = [run for run in self.runs() if run != a]
        self.assertEqual({a: D1.to_record()}, self.bindings())
        self.assertEqual(D1.to_record(), self.envelope(b)["human_decision"])
        # D2 exits B's wait in the same pending START; C authorizes and the terminal path completes
        result, record = self.complete(self.executor, review=work_p4(discovery, decision=D2))
        self.assertEqual(mutation_id, record["mutation_id"])
        self.assertEqual({a: D1.to_record(), b: D2.to_record()}, record["notes"][sr.NOTE_P4_DECISIONS])
        consumption = self.consumption(self.head(), record)
        (c,) = [run for run in self.runs() if run not in (a, b)]
        self.assertEqual(c, consumption.review_run_id)
        self.assertEqual(D2.to_record(), self.envelope(c)["human_decision"], "the exact decision of B's wait")
        self.assertEqual(b, self.successor_of(a, record["reserved_ids"]))
        self.assertEqual(c, self.successor_of(b, record["reserved_ids"]))
        self.assert_aside_once({a: b, b: c})
        review = ReviewStore(self.store)
        self.assertEqual(3, len(review.run_ids()))
        self.assertEqual(1, len(review.receipt_ids()))
        self.assertEqual(1, len(review.consumption_ids()))
        named = {review.gate_chain(run).generations[0].candidate_hash for run in (a, b, c)}
        self.assertEqual(sorted(named), sorted(review.candidate_snapshot_hashes()), "no snapshot no Run names")
        self.assertEqual(6, len(review.task_input_ids()), "one discovery + one adjudication task per Run")
        self.assertEqual(5, len(review.gate_chain(c).generations))
        self.assertEqual(p4.SEAL_GENERATION, consumption.review_generation)
        self.assertEqual([], self.problems())

    def test_h4_a_later_wait_binds_a_later_distinct_decision(self) -> None:
        """T-H4: D2 for B after D1 for A is accepted, bound to B, and named by B's successor's request."""
        discovery = Discovery(human(), human(), human())
        a = self.wait_first(discovery)
        self.stops(p4.CODE_HUMAN_WAIT, discovery, D1)
        (b,) = [run for run in self.runs() if run != a]
        self.stops(p4.CODE_HUMAN_WAIT, discovery, D2)
        self.assertEqual({a: D1.to_record(), b: D2.to_record()}, self.bindings())
        (c,) = [run for run in self.runs() if run not in (a, b)]
        self.assertEqual(D2.to_record(), self.envelope(c)["human_decision"])
        self.assert_aside_once({a: b, b: c})
        self.assertEqual(1, len(self.pending()), "still the one pending START")


class HumanDecisionRetryTests(HumanDecisionCase):
    def test_h2_the_same_decision_again_is_idempotent(self) -> None:
        """T-H2: re-supplying A's D1 creates no second successor, task or Run, and leaves the binding as it was."""
        discovery = Discovery(human(), human())
        a = self.wait_first(discovery)
        self.stops(p4.CODE_HUMAN_WAIT, discovery, D1)
        before = self.start_record()
        tasks = ReviewStore(self.store).task_input_ids()
        # D1 is spent on A's wait: it neither exits B's wait nor reserves anything new
        self.stops(p4.CODE_HUMAN_WAIT, discovery, D1)
        after = self.start_record()
        self.assertEqual(before["reserved_ids"], after["reserved_ids"])
        self.assertEqual({a: D1.to_record()}, self.bindings())
        self.assertEqual(2, len(self.runs()))
        self.assertEqual(tasks, ReviewStore(self.store).task_input_ids())

    def test_h3_a_different_decision_for_a_bound_wait_is_refused_and_changes_nothing(self) -> None:
        """T-H3: D1' for A, bound to D1 (before and after the successor's reservation), is
        ``review_p4_human_decision_invalid``."""
        discovery = Discovery(human(), human())
        a = self.wait_first(discovery)
        self.crashes("_p4_bind_decision", discovery, D1, after=True)
        self.assertEqual({a: D1.to_record()}, self.bindings())
        before = self.start_record()["reserved_ids"]
        self.assertIsNone(self.successor_of(a, before))
        self.stops(p4.CODE_HUMAN_DECISION_INVALID, discovery, D1_OTHER)
        self.assertEqual({a: D1.to_record()}, self.bindings(), "the binding is unchanged")
        self.assertEqual(before, self.start_record()["reserved_ids"])
        # the reservation window: D1 reserves the successor, the process dies before its G1, then D1' is refused
        self.crashes("_p4_accept", discovery, D1, after=False)
        reserved = self.start_record()["reserved_ids"]
        successor = self.successor_of(a, reserved)
        self.assertIsNotNone(successor)
        self.stops(p4.CODE_HUMAN_DECISION_INVALID, discovery, D1_OTHER)
        self.assertEqual({a: D1.to_record()}, self.bindings())
        self.assertEqual(reserved, self.start_record()["reserved_ids"])
        self.assertEqual([a], list(self.runs()), "no successor Run was begun")

    def test_h5_interrupted_after_binding_before_reservation_resumes_with_one_successor(self) -> None:
        """T-H5: killed after D1 is bound and before the successor is reserved; the retry keeps the binding and
        reserves exactly one successor."""
        discovery = Discovery(human(), human())
        a = self.wait_first(discovery)
        self.crashes("_p4_bind_decision", discovery, D1, after=True)
        self.assertEqual({a: D1.to_record()}, self.bindings())
        self.assertIsNone(self.successor_of(a, self.start_record()["reserved_ids"]))
        self.stops(p4.CODE_HUMAN_WAIT, discovery, D1)
        reserved = self.start_record()["reserved_ids"]
        (b,) = [run for run in self.runs() if run != a]
        self.assertEqual(b, self.successor_of(a, reserved))
        self.assertEqual(1, sum(1 for key in reserved if key.startswith("review-successor-run:")))
        self.assertEqual({a: D1.to_record()}, self.bindings())
        self.assertEqual(D1.to_record(), self.envelope(b)["human_decision"])
        self.assert_aside_once({a: b})

    def test_h6_interrupted_after_reservation_before_g1_keeps_the_reservation(self) -> None:
        """T-H6: killed after the successor's reservation and before its G1; the retry begins exactly that
        successor with exactly its reserved task, nothing duplicated."""
        discovery = Discovery(human(), human())
        a = self.wait_first(discovery)
        self.crashes("_p4_accept", discovery, D1, after=False)
        reserved = dict(self.start_record()["reserved_ids"])
        successor = self.successor_of(a, reserved)
        self.assertIsNotNone(successor)
        self.assertEqual([a], list(self.runs()))
        self.stops(p4.CODE_HUMAN_WAIT, discovery, D1)
        after = self.start_record()["reserved_ids"]
        self.assertEqual(reserved, {key: after[key] for key in reserved}, "every earlier reservation is kept")
        self.assertEqual(sorted([a, successor]), sorted(self.runs()))
        first = ReviewStore(self.store).gate_chain(successor).generations[0]
        discovery_task = str(first.accepted_tasks[0]["task_id"])
        self.assertIn(discovery_task, reserved.values(), "the successor's G1 accepts the task reserved before the kill")
        self.assertEqual(D1.to_record(), self.envelope(successor)["human_decision"])
        self.assertEqual(1, sum(1 for key in after if key.startswith("review-successor-run:")))
        self.assert_aside_once({a: successor})
        self.assertEqual(records.GATE_STATUS_OPEN, first.status)
