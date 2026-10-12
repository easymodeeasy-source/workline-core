"""Shared fixtures for the RB11 START owner probe tests (RT-1a; rev-11 TFI §B.1 - §B.4).

A pending START record is made by a real START that a deterministic test-only
interruption stops at a known window, then - for a row about one raising call -
edited so that exactly that call is its first refusal. Every row then asks two
things of the same bytes:

* the probe (status's read-only classifier, through :func:`workline.status.pending_classification`
  and :func:`workline.start_probe.inspect`), with the Project tree - ``.git`` included - compared
  byte for byte before and after;
* a real ``start()`` with an executor that fails the test if START ever asks it: the refusal START
  raises carries the same check ID (``errors.with_check``), and the record is left exactly as it was.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Callable, Iterator
from contextlib import contextmanager
from unittest import mock

from helpers import WorklineTestCase, git
from status_helpers import tree_snapshot
from workline import gitops, start as st, start_probe, status, yamlish
from workline.create import RelatedSpec, RelationSpec, WorkSpec
from workline.mutation import Mutation, MutationController, inspect_records
from workline.ops import Replan
from workline.state import ProjectView

EVENT_LOG = ".workline/events/events.jsonl"
ROADMAP = ".workline/relations/roadmap.yaml"


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone (never a StopError: nothing is abandoned)."""


class ExecutorAsked(AssertionError):
    """START asked its executor, which no row about a refusal may let it do."""


def after_recording(pattern: str):
    """Stop right after a stage matching ``pattern`` is durably recorded, none of it applied."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        real(mutation, stage, effects)
        if re.search(pattern, stage):
            raise Interrupted(f"recorded {stage}")

    return mock.patch.object(Mutation, "add_effects", fire)


def after_applying(pattern: str):
    """Stop right after the call that applied a stage matching ``pattern``."""
    real = Mutation.apply

    def fire(mutation):
        before = {e["seq"] for e in mutation.record.get("effects") or [] if e.get("applied")}
        outcome = real(mutation)
        if any(e.get("applied") and e["seq"] not in before and re.search(pattern, e["stage"])
               for e in mutation.record.get("effects") or []):
            raise Interrupted(f"applied {pattern}")
        return outcome

    return mock.patch.object(Mutation, "apply", fire)


def before_finalizing():
    """Stop when a Git stage is about to be recorded (``gitops.finalize``), nothing of it recorded."""
    return mock.patch.object(st.gitops, "finalize", side_effect=Interrupted("before the Git stage"))


def never(ctx: st.ExecutionContext):
    raise ExecutorAsked(f"START asked its executor for {ctx.work.id}")


class ProbeCase(WorklineTestCase):
    """A Project, a Phase with two Works, and the record and probe helpers every RT-1a row uses."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        roadmap = self.simple_roadmap(self.store)
        self.rid, self.pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        self.entry = self.simple_entry(self.store, self.pa, {"w1": "W1", "w2": "W2"})
        self.w1, self.w2 = self.entry.work_ids["w1"], self.entry.work_ids["w2"]
        self.i1 = self.entry.integration_id

    # ---------------------------------------------------------------- the Project
    def rel(self, rel_type: str, a: str, b: str) -> str:
        (found,) = [r.id for r in ProjectView.load(self.store).roadmap_relations
                    if (r.type, r.from_id, r.to) == (rel_type, a, b)]
        return found

    def commit_by_hand(self, *paths: str, message: str = "human: commit") -> None:
        git(self.store.root, "add", "--", *paths)
        git(self.store.root, "commit", "-q", "-m", message, "--", *paths)

    # ---------------------------------------------------------------- records
    def pending(self) -> list[dict[str, Any]]:
        return [item.record for item in inspect_records(self.store)
                if item.record is not None and item.record.get("status") == "pending"]

    def the_record(self) -> dict[str, Any]:
        (record,) = [r for r in self.pending() if r["owner"] == st.OWNER]
        return record

    def record_path(self, record: dict[str, Any]):
        return self.store.mutations / f"{record['mutation_id']}.yaml"

    def write_record(self, record: dict[str, Any]) -> None:
        self.record_path(record).write_text(yamlish.dump(record), encoding="utf-8", newline="\n")

    def edit(self, change: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
        """Edit the one pending START record in place (its bytes), as a hand-edited record would be."""
        record = copy.deepcopy(self.the_record())
        change(record)
        self.write_record(record)
        return record

    # ---------------------------------------------------------------- record parts
    @staticmethod
    def effects(record: dict[str, Any], stage: str | None = None, kind: str | None = None) -> list[dict[str, Any]]:
        return [e for e in record["effects"]
                if (stage is None or e["stage"] == stage) and (kind is None or e["kind"] == kind)]

    @staticmethod
    def stages(record: dict[str, Any]) -> list[str]:
        found: list[str] = []
        for effect in record["effects"]:
            if effect["stage"] not in found:
                found.append(effect["stage"])
        return found

    @staticmethod
    def event_effect(record: dict[str, Any], event_type: str) -> dict[str, Any]:
        (found,) = [e for e in record["effects"] if e["kind"] == "append_event"
                    and e["payload"]["record"]["type"] == event_type]
        return found

    # ---------------------------------------------------------------- fixtures
    def interrupt(self, window, call) -> dict[str, Any]:
        with window, self.assertRaises(Interrupted):
            call()
        return self.the_record()

    def cancel_replan(self, *, works: bool = True, removal: bool = True, relations: int = 2) -> Replan:
        additions = [RelationSpec("requires_completion", "n1" if works else self.w2, self.i1)]
        if relations > 1:
            additions.append(RelationSpec("requires_completion", "n1" if works else self.w2, self.w2 if works else self.i1))
        return Replan(
            remove_relation_ids=(self.rel("requires_completion", self.w1, self.i1),) if removal else (),
            add_relations=tuple(additions[:relations]),
            new_works={"n1": WorkSpec("N1", "n1", phase_id=self.pa, roadmap_id=self.rid)} if works else {},
        )

    def cancel_record(self, window: str = "commit recorded", replan: Replan | None = None,
                      reason: str = "scope") -> dict[str, Any]:
        """W1 cancelled with ``replan`` by a single-work START, stopped at ``window``."""
        replan = self.cancel_replan() if replan is None else replan
        windows = {
            "cancel recorded": lambda: after_recording(rf"^{self.w1}:lifecycle:1$"),
            "works applied": lambda: after_applying(rf"^{self.w1}:cancel:0:(works|relations)$"),
            "removals applied": lambda: after_applying(rf"^{self.w1}:cancel:0:remove$"),
            "before commit": before_finalizing,
            "commit recorded": lambda: after_recording(r"^commit:\d+$"),
        }
        return self.interrupt(windows[window](), lambda: st.start(
            self.store, self.w1, "single-work", lambda ctx: st.Cancel(replan, reason)))

    def hold_record(self, *, committed: bool = False) -> dict[str, Any]:
        """W1 held by a single-work START, stopped before (or right after recording) its Git stage."""
        window = after_recording(r"^commit:\d+$") if committed else before_finalizing()
        return self.interrupt(window, lambda: st.start(self.store, self.w1, "single-work", lambda ctx: st.Hold("later")))

    def completion_record(self) -> dict[str, Any]:
        """W1 completed by a single-work START, stopped before its finalization commit is recorded."""
        def done(ctx):
            (self.store.root / "result_w1.txt").write_text("w1\n", encoding="utf-8")
            return st.Completed(("result_w1.txt",))

        window = mock.patch.object(st._Session, "_finalize_completion", side_effect=Interrupted("before finalize"))
        return self.interrupt(window, lambda: st.start(self.store, self.w1, "single-work", done))

    def question_wait_record(self, work_id: str | None = None, mode: str = "single-work") -> dict[str, Any]:
        """A START that asked a question: pending, its Work IN_PROGRESS with its target, nothing else decided."""
        result = st.start(self.store, work_id or self.w1, mode, lambda ctx: st.QuestionWait("which one?"))
        self.assertEqual(result.status, "question_wait")
        return self.the_record()

    def derive(self, key: str = "f1", *, move: bool = False) -> st.Derive:
        return st.Derive({key: st.DerivedWork(f"Fix {key}", f"{key} fixed")}, move=move)

    def derivation_record(self, count: int = 1, *, move: bool = False) -> dict[str, Any]:
        """W1 decided ``count`` derivations (the last one a move when ``move``), then asked a question / stopped."""
        outcomes = [self.derive(f"f{index}") for index in range(count - 1)]
        if move:
            outcomes.append(self.derive(f"f{count - 1}", move=True))
            calls = iter(outcomes)
            window = after_recording(r"^commit:\d+$") if count == 1 else after_recording(rf"^commit:{count - 1}$")
            return self.interrupt(window, lambda: st.start(self.store, self.w1, "single-work", lambda ctx: next(calls)))
        outcomes.append(self.derive(f"f{count - 1}"))
        calls = iter(outcomes)

        def execute(ctx):
            return next(calls, st.QuestionWait("next?"))

        result = st.start(self.store, self.w1, "single-work", execute)
        self.assertEqual(result.status, "question_wait")
        return self.the_record()

    # ---------------------------------------------------------------- asking
    @contextmanager
    def unchanged_tree(self) -> Iterator[None]:
        """The whole Project tree, ``.git`` included, byte for byte the same around the block (T-A22 / T-B07)."""
        before = tree_snapshot(self.store.root)
        yield
        after = tree_snapshot(self.store.root)
        changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
        self.assertEqual(changed, [], "the probe changed the Project")

    def probe(self, mutation_id: str | None = None) -> start_probe.StartProbe:
        """The probe for one pending START record: status's own entry point and the internal walk agree."""
        records = self.pending()
        target = mutation_id or self.the_record()["mutation_id"]
        self.last_target = target
        (record,) = [r for r in records if r["mutation_id"] == target]
        with self.unchanged_tree():
            classification, reason = status.pending_classification(self.store, target)
            found = start_probe.inspect(self.store, record, records)
        self.assertEqual((classification, reason), (found.classification, found.reason()))
        return found

    def real_start(self, work_id: str | None = None, mode: str = "single-work"):
        """A real START of the record's invocation; its refusal (or result), with the record bytes compared."""
        record = self.the_record()
        path = self.record_path(record)
        before = path.read_bytes()
        try:
            outcome: Any = st.start(self.store, work_id or record["invocation"]["work_id"],
                                    mode if work_id else record["invocation"]["mode"], never)
        except ExecutorAsked:
            raise
        except Exception as exc:  # the refusal START raised
            outcome = exc
            self.assertTrue(path.is_file(), "START's refusal took the record away")
            if path.read_bytes() != before:
                # START saves its own record once before its next domain step (``extend_scope`` in run_work):
                # the save time is all that may differ - nothing it decided, recorded or noted
                after = yamlish.load(path.read_text(encoding="utf-8"))
                kept = yamlish.load(before.decode("utf-8"))
                after.pop("updated_at"), kept.pop("updated_at")
                self.assertEqual(after, kept, "START's refusal changed the record")
        return outcome

    def assertReconcileAt(self, check: str) -> start_probe.StartProbe:
        """T-B01 / T-B02: the probe says reconcile with ``check``; a real START refuses at that same call."""
        found = self.probe()
        self.assertEqual((found.classification, found.check_id), (start_probe.PENDING_RECONCILE, check), found)
        self.assertEqual(found.code, "reconcile_required")
        refused = self.real_start()
        self.assertIsInstance(refused, st.ReconcileRequired, refused)
        self.assertEqual(getattr(refused, "check_id", None), check, refused)
        self.assertEqual(found.message, str(refused), "the reason is START's own refusal, exactly")
        return found

    def assertUnknown(self, check: str | None = None, *, code: str = start_probe.NO_PROBE,
                      start_check: str | None = None) -> start_probe.StartProbe:
        """``unknown_or_invalid``; with ``check``, the walk ended at that (non-ALLOW) call, and START refuses there."""
        found = self.probe()
        self.assertEqual(found.classification, start_probe.UNKNOWN_OR_INVALID, found)
        self.assertEqual(found.code, code, found)
        self.assertNotDisposable()
        if check is not None:
            self.assertEqual(found.check_id, check, found)
        if start_check is not None:
            refused = self.real_start()
            self.assertIsInstance(refused, Exception, refused)
            self.assertEqual(getattr(refused, "check_id", None), start_check, refused)
        return found

    def assertResumable(self) -> start_probe.StartProbe:
        found = self.probe()
        self.assertEqual(found.classification, start_probe.PENDING_RESUMABLE, found)
        self.assertNotDisposable()
        return found

    def assertNotDisposable(self, mutation_id: str | None = None) -> None:
        """T-B15, must-not-widen: N4 refuses the START record just probed exactly as it refused every START record
        before RB11 (``recovery_disposition_target_ineligible``) - or, with another record pending, for that
        (``recovery_disposition_pending_operation``) - and writes nothing: no disposition, no commit, the record's
        bytes unchanged."""
        from workline import recovery_disposition as rd
        from workline.errors import StopError

        target = mutation_id or self.last_target
        path = self.store.mutations / f"{target}.yaml"
        before = (path.read_bytes(), git(self.store.root, "rev-parse", "HEAD"))
        dispositions = self.store.root / ".workline" / "recovery" / "dispositions"
        with self.assertRaises(StopError) as refused:
            rd.dispose_recovery(self.store.root, target, "status does not prove this record a dead end", confirmed=True)
        self.assertIn(refused.exception.code,
                      ("recovery_disposition_target_ineligible", "recovery_disposition_pending_operation"),
                      refused.exception)
        self.assertEqual((path.read_bytes(), git(self.store.root, "rev-parse", "HEAD")), before)
        self.assertFalse(dispositions.is_dir() and any(dispositions.iterdir()), "a disposition was written")


def start_dead_end(case: WorklineTestCase, name: str = "proj"):
    """A Project with one pending START record whose first refusal is an ALLOW call (2282).

    W1 cancelled by a single-work START, stopped right after its commit stage
    was recorded, the cancel's decision then gone from the record - a cancel
    recorded without its decision, which START refuses from the record alone
    (``pending_reconcile_required`` at ``start.2282``). Returns the store, the
    record's mutation ID and the Work IDs.
    """
    store = case.new_project(name)
    roadmap = case.simple_roadmap(store)
    pa, rid = roadmap.phase_ids["a"], roadmap.roadmap_id
    entry = case.simple_entry(store, pa, {"w1": "W1", "w2": "W2"})
    w1, w2, i1 = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id
    (into,) = [r.id for r in ProjectView.load(store).roadmap_relations
               if (r.type, r.from_id, r.to) == ("requires_completion", w1, i1)]
    replan = Replan(remove_relation_ids=(into,), add_relations=(RelationSpec("requires_completion", "n1", i1),),
                    new_works={"n1": WorkSpec("N1", "n1", phase_id=pa, roadmap_id=rid)})
    with after_recording(r"^commit:\d+$"), case.assertRaises(Interrupted):
        st.start(store, w1, "single-work", lambda ctx: st.Cancel(replan, "scope"))
    (record,) = MutationController(store).list_pending()
    for effect in record["effects"]:
        if effect["kind"] == "append_event" and effect["payload"]["record"]["type"] == "work_cancelled":
            effect["payload"].pop("cancel")
    (store.mutations / f"{record['mutation_id']}.yaml").write_text(yamlish.dump(record), encoding="utf-8", newline="\n")
    found = start_probe.inspect(store, record, [record])
    case.assertEqual((found.classification, found.check_id), (start_probe.PENDING_RECONCILE, "start.2282"))
    return store, record["mutation_id"], {"w1": w1, "w2": w2, "i1": i1, "pa": pa}
