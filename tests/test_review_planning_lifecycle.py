"""P2 §28 H: lifecycle separation - Review metadata never alters lifecycle, and P3 stays inactive."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import unittest

from helpers import completing_executor, git
from planning_helpers import Crash, PlanningTestCase, Reviewer, crash_at, design, plan, rr, run_ids
from workline import roadmap as rm
from workline import start as st
from workline import state
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.review import paths as review_paths
from workline.review.store import ReviewStore
from workline.state import ProjectView
from workline.validate import validate_structure

#: SHA-256 of ``src/workline/state.py`` (LF line ends). Pinned at the implementation baseline de3681c
#: (6f86107ceee1536b55ff0c85b2f1bd3fca17ee0b83e4ef38885d184be1d0e6da); re-pinned for the one authorized change
#: since, the RB2-H1 in-memory ``events_for`` index (Control Plane-frozen, §36.22 step 4), which changes no derivation
#: and keeps state.py free of Review (feea1dc4af4105a535d10bd11eb9b1ece762e28bcff88f5ba7ab040ced2dd772).
#: Re-pinned for the RB5 reviewed completion predicate (§32.9; RB5 integration I-2, row R05): ``phase_completion``
#: adds ``phase_integration.completion_reasons`` - entity / event / relation truth only - once every legacy check
#: holds, through a function-local import. state.py stays free of Review.
STATE_PY_BASELINE_SHA256 = "0b2a42bed8c301e889d4663f40fea3da71a377cae71d07a09209e84e05f0f479"
#: Re-pinned for Sprint 41.31, Table P pin P1 (units AM-H1 and AM-H2): two definitions of state.py differ from the baseline.
#: ``ProjectView.unsatisfied_dependencies`` also reads the ``requires_completion`` a Work's own Phase waits on - only for a Work
#: that carries the Roadmap-time registration provenance marker (AM-H1) and, as AM-H2 requires, only while that Work is
#: ``unstarted`` - in the one predicate that START, the probe, status and the startable listings read.
#: ``ProjectView.phase_completion`` keeps its old reading through ``include_phase=False``. The Human's wording approval of
#: Sprint 41.31 is pending (this pin is not that approval): if the section is not approved, the two hunks are reverted and
#: this pin returns to ``STATE_PY_BASELINE_SHA256``. The baseline pin above stays as the record of production main 41d27c00,
#: and ``STATE_PY_BASELINE_OF_THE_ALLOWED_DEFINITIONS`` records what the two allowed definitions were. Every other definition
#: of state.py must stay byte-identical to the baseline (``STATE_PY_DEFINITION_DIGESTS``), so the re-pin cannot hide any other
#: change. state.py stays free of Review. The values are MEASURED from the final state.py, never predicted.
STATE_PY_D2_SHA256 = "8c40213743f19583b6b8995be89feecb136bcf546f97f78b060ea532daab66b5"
STATE_PY_ALLOWED_CHANGES = frozenset({"ProjectView.phase_completion", "ProjectView.unsatisfied_dependencies"})
STATE_PY_BASELINE_OF_THE_ALLOWED_DEFINITIONS = {
    "ProjectView.phase_completion": "a3e4bd1f67b71dc0bd99bb01c294994326b944ee41fa58816dded18f8632f943",
    "ProjectView.unsatisfied_dependencies": "d15aa2b29602edb09b8d878a2dd87d35734c89f504b6ffc2c78ed4c1a15bfa11",
}
STATE_PY_DEFINITION_DIGESTS = {
    "<module>": "a9025bf41aeae88615b93a36d04cb004da7c2b39add86ab5b33e80b618ae8e76",
    "PhaseCompletion": "b967cea056af5d8f61ef896df2d64a0f1a62d6721697adb5ad73fb18b6441808",
    "ProjectView": "869d7d8f589071b8562061ee434d47bae2dd57b4528f8636b4d20f42b6067db4",
    "ProjectView.active_phases": "bc43ab010bbc5d634186405b6643504d891ba183c91f2c03e166a5552c60787b",
    "ProjectView.all_active_phases_complete": "c8f760267be34186f63dcdd6ceef56c41fb91891a8890d63d6bc9ccc7112c971",
    "ProjectView.choose_startable": "712c85c6b02faa62d7678e4d0feb3e869cd07f133c1e11948be1b347110a553c",
    "ProjectView.dependencies_satisfied": "5a039059ac6503d2c65f56974aa5c97c872c2aef77d33cac70d256cc0a9c6886",
    "ProjectView.effective_works": "a05d087f8f38060e634c801ddb737898a2c059d1e2eb085efb3e94a14dfc04cc",
    "ProjectView.entity_state_label": "55bcea68a310eee2d33f30adc0a9536818c7dd858aae1537b0218ec904c65d14",
    "ProjectView.events_for": "1160595552cc4d8ec604f23aa767e4c0b25b7df4fba98a02362427961967f36f",
    "ProjectView.integrations": "33d5f80222ac2bec9bd0b610cf963fc6d507a58bdee4e33a1fa23b7d3a573d29",
    "ProjectView.load": "6704a655447310c38e12085f9b56e4cf823c9b8078f2c112410499cc8dbdae16",
    "ProjectView.phase_completion": "a36a74fbdb1a9f7866070ceea46087862afd53385b4a3a0c226b4a9dbd31d0bc",
    "ProjectView.phase_lifecycle": "f1dfd1c20e6403a24c684b4db2530c199e92d03b5ae00f895b84b85690077692",
    "ProjectView.phase_state": "7aa5d763dd4776120dfe7748804cdc132e19ca8c09a40c71788fd56cc0471d2f",
    "ProjectView.phase_works": "a1b74ad4df6f152843437ded2a20fa621adee138005776776f7969dd6afec7c3",
    "ProjectView.planned_next_preference": "a88714082081bfa5f77da5a8036665102d23b5f9f162f238f10c2e3fff8e23a4",
    "ProjectView.related_from": "8681f2771b8a24f283d7fb3c220d93631198c3785724a002a98800f3ee4372b2",
    "ProjectView.relations_from": "7e3edec106db20b77756a729826b7c8bed737c41e530d57e657eb5e104c811bb",
    "ProjectView.relations_to": "97b169f7128c6ae61968484d3cca8b7025bd15cd36c581e770f74f067d324e70",
    "ProjectView.roadmap_lifecycle": "530211d37c37535568a53ded91364523b9e769ef8a622f3fb1b9dc56f8fea04f",
    "ProjectView.roadmap_phases": "82e23e06c5be43ab3a423a6718770a39e4919a03df27ad1cb77baeac80971073",
    "ProjectView.startable_phases": "5bba63e0ab30cb4c14436841e975454e1d601357cde6f8b3ccb95875e2e2ffe0",
    "ProjectView.startable_works": "ea484408cf3ba3a6b7d87715c86c09e917f6f3fc7b89714a04c36af69c06fcca",
    "ProjectView.unfinished_integrations": "5e9cf4c73e05859999298d0067ef21d9fcec4469aca9ff02f4ca647d7a5dbeae",
    "ProjectView.unsatisfied_dependencies": "4f7505f70a4ab47dd3a7e0f84a422c70f0c2556a5fc49d88601f26eea9e95312",
    "ProjectView.with_effects": "d3ec65b3da744d5fbec2d99807b02e5d8a3020be45f6a5c18b0dd239ac735217",
    "ProjectView.work_entered_execution": "45f02f5c7110f3250e704770b5aaa7a4ee8fd4dcd277fce1f64fa84713256d57",
    "ProjectView.work_state": "505bae335fd0c9996bfa9f251a6192ad9193d1116eb9a4c581144b787acf8256",
    "WorkState": "1ca04467a2c94ed8c1d9ab9d208934d81f25d6cfd9d8e941d1be13484b11106d",
    "WorkState.excluded": "b95d77c1a2c503dd22691571fbf553f4b14f1e660c37bba678f85b42b9a0b068",
    "WorkState.terminal": "693ea5461ed3b6ed9a6f425fe4305e881cf9847fe7f55fce4c3164dc9a164e25",
    "derive_phase_lifecycle": "20f1ed3f15a753c46c4440b2890cb0000586e7df368bca10b28aea871137b36e",
    "derive_roadmap_lifecycle": "dd94073f8132206bcae933c08d7992437f6453de0f3e544ceb56f2c50e665c2f",
    "derive_work_state": "0d9c411328d048d897a51cd5f6f7f0f493f81bdd6dffbeac22293fba7876a992",
}
EVENT_LOG = ".workline/events/events.jsonl"


def definition_digests(source: str) -> dict[str, str]:
    """SHA-256 of every definition's own source lines (nested definitions excluded) plus the module residue.

    A container (class, or a function with nested definitions) is hashed without its nested definitions, so a change
    inside a method changes only that method's digest.
    """
    tree = ast.parse(source)
    lines = source.split("\n")
    defs = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

    def span(node: ast.AST) -> tuple[int, int]:
        first = node.decorator_list[0].lineno if getattr(node, "decorator_list", None) else node.lineno
        return first - 1, node.end_lineno

    digests: dict[str, str] = {}

    def scope(name: str, body: list, first: int, last: int) -> None:
        owned = set(range(first, last))
        for node in body:
            if isinstance(node, defs):
                start, end = span(node)
                owned -= set(range(start, end))
                scope(f"{name}.{node.name}" if name != "<module>" else node.name, node.body, start, end)
        digests[name] = hashlib.sha256("\n".join(lines[i] for i in sorted(owned)).encode("utf-8")).hexdigest()

    scope("<module>", tree.body, 0, len(lines))
    return digests


def lifecycle_facts(view: ProjectView) -> dict:
    """Everything lifecycle and progression derive, keyed by display so two Projects built alike compare equal."""
    display = {entity.id: entity.display for kind in (view.roadmaps, view.phases, view.works) for entity in kind.values()}
    return {
        "roadmaps": {r.display: (r.name, view.roadmap_lifecycle(r.id)) for r in view.roadmaps.values()},
        "phases": {p.display: (p.name, view.phase_state(p.id), view.phase_lifecycle(p.id)) for p in view.phases.values()},
        "works": {w.display: (w.name, w.work_kind, view.work_state(w.id).state) for w in view.works.values()},
        "startable": {p.display: [display[w.id] for w in view.startable_works(p.id)] for p in view.phases.values()},
        "relations": sorted((r.type, display.get(r.from_id), display.get(r.to)) for r in view.roadmap_relations),
        "related": sorted((r.type, display.get(r.from_id), r.to) for r in view.related),
        "events": [(e.type, display.get(e.entity)) for e in view.events],
    }


class EndStateTests(PlanningTestCase):
    def test_gated_and_legacy_end_states_are_equal(self) -> None:
        legacy = self.planning_project("legacy")
        created = rm.create_roadmap(legacy, plan())
        rm.enter_phase(legacy, created.phase_ids["a"], design())
        legacy_facts = lifecycle_facts(ProjectView.load(legacy))
        gated = self.planning_project("gated")
        result = self.reviewed_roadmap(gated)
        self.reviewed_entry(gated, result.registration.phase_ids["a"])
        self.assertEqual(legacy_facts, lifecycle_facts(ProjectView.load(gated)))
        self.assertEqual(
            (legacy.root / EVENT_LOG).read_bytes() if (legacy.root / EVENT_LOG).exists() else b"",
            (gated.root / EVENT_LOG).read_bytes() if (gated.root / EVENT_LOG).exists() else b"",
            "a review-v1 Roadmap creation or Phase entry writes no event",
        )

    def test_generation_4_and_the_supersession_change_no_lifecycle_fact(self) -> None:
        store = self.planning_project()
        before = lifecycle_facts(ProjectView.load(store))
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        real = rr.planning._read_authority
        from unittest import mock

        with mock.patch.object(rr.planning, "_read_authority",
                               lambda path: real(path) + (b"\nchanged\n" if str(path).endswith("registry.md") else b"")):
            result = self.reviewed_roadmap(store)
        self.assertEqual("stale", result.status)
        self.assertTrue(ReviewStore(store).supersession_exists(result.receipt_id))
        self.assertEqual(before, lifecycle_facts(ProjectView.load(store)))


class TamperedRecordTests(PlanningTestCase):
    def test_a_tampered_record_stops_only_the_gated_operation_relying_on_it(self) -> None:
        store = self.planning_project()
        other = rm.create_roadmap(store, plan("Other Roadmap")).roadmap_id
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        before = lifecycle_facts(ProjectView.load(store))
        (run_id,) = run_ids(store)
        receipt = store.root / review_paths.receipt_rel(self.chain(store, run_id).latest.receipt_id)
        receipt.write_bytes(receipt.read_bytes().replace(b"\n", b"\r\n"))  # no longer canonical
        self.assertEqual(before, lifecycle_facts(ProjectView.load(store)), "lifecycle is not reinterpreted")
        self.assertEqual([], validate_structure(ProjectView.load(store)))
        rm.hold_roadmap(store, other)  # an operation that relies on no Review record proceeds
        with self.assertRaises((ReconcileRequired, StopError, ValidationError)) as raised:
            self.reviewed_roadmap(store)  # the gated operation relying on the record stops
        self.assertEqual(("ReconcileRequired", "review_receipt_invalid"),
                         (type(raised.exception).__name__, getattr(raised.exception, "reason", None)))


class StatePyTests(unittest.TestCase):
    def _source(self) -> str:
        return Path(state.__file__).read_bytes().decode("utf-8").replace("\r\n", "\n")

    def test_state_py_is_the_pinned_d2_form_and_free_of_review(self) -> None:
        data = self._source().encode("utf-8")
        self.assertEqual(STATE_PY_D2_SHA256, hashlib.sha256(data).hexdigest())
        self.assertNotIn(b"review", data.lower())

    def test_every_definition_but_the_two_allowed_is_byte_identical_to_the_baseline(self) -> None:
        digests = definition_digests(self._source())
        self.assertEqual(STATE_PY_DEFINITION_DIGESTS, digests)
        # the allowed definitions are exactly the ones that differ from the baseline record
        self.assertEqual(STATE_PY_ALLOWED_CHANGES, set(STATE_PY_BASELINE_OF_THE_ALLOWED_DEFINITIONS))
        for name in STATE_PY_ALLOWED_CHANGES:
            self.assertNotEqual(STATE_PY_BASELINE_OF_THE_ALLOWED_DEFINITIONS[name], digests[name], name)
        for name, digest in digests.items():
            if name not in STATE_PY_ALLOWED_CHANGES:
                self.assertEqual(STATE_PY_DEFINITION_DIGESTS[name], digest, name)

    @staticmethod
    def _with_a_new_first_line(source: str, header: str) -> str:
        head, sep, rest = source.partition(header)
        body_start = rest.index(":\n") + 2
        return head + sep + rest[:body_start] + "        _ = 0\n" + rest[body_start:]

    def test_a_change_to_any_other_definition_fails_the_guard(self) -> None:
        source = self._source()
        # negative controls on in-memory copies: one new line in a definition that is NOT allowed to change ...
        for header in ("def dependencies_satisfied", "def roadmap_lifecycle"):
            self.assertIn(header, source)
            changed = self._with_a_new_first_line(source, header)
            self.assertNotEqual(STATE_PY_DEFINITION_DIGESTS, definition_digests(changed), header)
        # ... a change to an allowed definition is caught as well, because its new form is pinned too ...
        changed = self._with_a_new_first_line(source, "def unsatisfied_dependencies")
        self.assertNotEqual(STATE_PY_DEFINITION_DIGESTS, definition_digests(changed))
        # ... a module-level line and a new definition are changes too
        self.assertNotEqual(STATE_PY_DEFINITION_DIGESTS, definition_digests("# changed\n" + source))
        self.assertNotEqual(STATE_PY_DEFINITION_DIGESTS, definition_digests(source + "\n\ndef extra() -> None:\n    pass\n"))


class P3InactiveTests(PlanningTestCase):
    def _completed_first_work(self, store, *, reviewed: bool):
        if reviewed:
            result = self.reviewed_roadmap(store)
            entry = self.reviewed_entry(store, result.registration.phase_ids["a"]).registration
        else:
            created = rm.create_roadmap(store, plan())
            entry = rm.enter_phase(store, created.phase_ids["a"], design())
        started = st.start(store, entry.work_ids["w1"], "single-work", completing_executor(store))
        view = ProjectView.load(store)
        events = [e.type for e in view.events_for(entry.work_ids["w1"])]
        subjects = git(store.root, "log", "-2", "--format=%s").splitlines()
        return started.status, events, subjects

    def test_start_completion_is_unchanged_and_nothing_activates_p3(self) -> None:
        legacy = self._completed_first_work(self.planning_project("legacy"), reviewed=False)
        gated_store = self.planning_project("gated")
        gated = self._completed_first_work(gated_store, reviewed=True)
        self.assertEqual(legacy, gated)
        review = ReviewStore(gated_store)
        self.assertIsNone(review.read_activation())
        self.assertFalse((gated_store.root / review_paths.WORK_TERMINAL_ACTIVATION_REL).exists())
        self.assertEqual(2, len(review.consumption_ids()), "the two planning Consumptions only: no Work-terminal one")


class NoCrossOperationPreconditionTests(PlanningTestCase):
    def test_a_legacy_phase_entry_on_a_review_v1_roadmap_proceeds(self) -> None:
        store = self.planning_project()
        result = self.reviewed_roadmap(store)
        entry = rm.enter_phase(store, result.registration.phase_ids["a"], design())
        self.assertTrue(entry.work_ids)

    def test_a_review_v1_phase_entry_on_a_legacy_roadmap_proceeds(self) -> None:
        store = self.planning_project()
        created = rm.create_roadmap(store, plan())
        result = self.reviewed_entry(store, created.phase_ids["a"])
        self.assertEqual("registered", result.status)


class HeldBackOperationTests(PlanningTestCase):
    def test_a_legacy_operation_held_back_by_the_barrier_applied_exactly_its_usual_effects(self) -> None:
        store = self.planning_project(remote=True)
        other = rm.create_roadmap(store, plan("Other Roadmap")).roadmap_id
        with crash_at(rr, "_c2_kp"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        committed_log = git(store.root, "show", f"HEAD:{EVENT_LOG}", check=False)
        with self.assertRaises(StopError) as raised:
            rm.hold_roadmap(store, other)
        self.assertEqual("review_publication_barrier", raised.exception.code)
        changed = [line[3:] for line in git(store.root, "status", "--porcelain", "--untracked-files=all").splitlines()
                   if not line[3:].startswith(".workline/runtime/")]
        self.assertEqual([EVENT_LOG], changed, "its only effect is its event")
        applied = (store.root / EVENT_LOG).read_text(encoding="utf-8")
        self.assertTrue(applied.startswith(committed_log))
        (line,) = applied[len(committed_log):].splitlines()
        self.assertIn('"roadmap_held"', line)
        self.assertIn(other, line)
        self.assertEqual("held", ProjectView.load(store).roadmap_lifecycle(other))
        self.reviewed_roadmap(store)  # the planning retry proves Kp and publishes Km
        held = rm.hold_roadmap(store, other)  # only its commit and push waited
        self.assertEqual([EVENT_LOG], git(store.root, "show", "--name-only", "--format=", held.head).split())
        self.assertEqual(applied, git(store.root, "show", f"{held.head}:{EVENT_LOG}"))
        self.assertEqual(held.head, self.remote_head())


if __name__ == "__main__":
    unittest.main()
