"""RB2 (BL-007) benchmark package: the harness itself (``WORKLINE_COMPLETION_SPRINT.md`` §36.29).

Only the reduced test scale ``T`` and the small scale ``S`` run here. Full M/L
measurement loops never run as unit tests (§36.34); they belong to
``benchmarks/rb2/run.py series`` outside normal CI.

Disposable fixtures go under ``$RB2_FIXTURE_BASE`` when it is set, else under a
fresh temporary directory, and are removed afterwards.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
BENCH = ROOT / "benchmarks" / "rb2"
PYTHON = [sys.executable]


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = _load("workline_rb2_run", BENCH / "run.py")
generate = run.load_generator()


def _force_remove(function, path, _exc_info):
    os.chmod(path, stat.S_IWRITE)
    function(path)


def snapshot(directory: Path) -> dict[str, str]:
    found = {}
    for current, directories, files in os.walk(directory):
        for name in directories + files:
            path = Path(current) / name
            found[path.relative_to(directory).as_posix()] = "dir" if path.is_dir() else str(path.stat().st_size)
    return found


class FixtureCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        configured = os.environ.get("RB2_FIXTURE_BASE")
        if configured:
            Path(configured).mkdir(parents=True, exist_ok=True)
        self.base = Path(tempfile.mkdtemp(prefix="rb2-test-", dir=configured or None)).resolve()
        self.addCleanup(shutil.rmtree, self.base, onerror=_force_remove)

    def fixture(self, scale: str = "T", name: str | None = None, **kwargs) -> tuple[Path, dict]:
        target = self.base / (name or f"{scale}-fixture")
        manifest = generate.generate(target, scale, ROOT, allowed_base=self.base, **kwargs)
        return target, manifest


# --------------------------------------------------------------------------- generator


class GeneratorTests(FixtureCase):
    def test_a_fixed_seed_and_scale_give_the_same_fixture(self) -> None:
        first = generate.build_plan("S", 11)
        second = generate.build_plan("S", 11)
        self.assertEqual(first, second)
        self.assertNotEqual(first.events, generate.build_plan("S", 12).events)
        _, one = self.fixture("T", "one")
        _, two = self.fixture("T", "two")
        self.assertEqual(one["logical_digest"], two["logical_digest"])
        self.assertEqual((one["git"]["head"], one["git"]["tree"]), (two["git"]["head"], two["git"]["tree"]))
        self.assertEqual(one["counts"], two["counts"])

    def test_identities_are_valid_workline_ids_and_never_wall_clock(self) -> None:
        from workline.ids import is_valid_id

        plan = generate.build_plan("T")
        for work in plan.works:
            self.assertTrue(is_valid_id(work.id, "work"))
        for event_id, *_rest in plan.events:
            self.assertTrue(is_valid_id(event_id, "event"))
        self.assertTrue(is_valid_id(plan.pending_mutation_id, "mutation"))
        self.assertTrue(is_valid_id(plan.review["review_run_id"], "review_run"))
        self.assertTrue(all(at.startswith("2026-01-01T") for *_rest, at in plan.events))

    def test_scale_topology(self) -> None:
        for scale, (works, _per_phase) in generate.SCALES.items():
            plan = generate.build_plan(scale)
            self.assertEqual(len(plan.works), works, scale)
            target = generate.EVENTS_PER_WORK * works
            self.assertLessEqual(abs(len(plan.events) - target), 0.2 * target, scale)
            groups = {phase.group for phase in plan.phases}
            self.assertEqual(groups >= {"historical", "current", "future"}, True, scale)
            states = [work.events[-1] if work.events else None for work in plan.works]
            self.assertIn("work_completed", states)
            self.assertIn(None, states)  # genuinely unstarted Works
            self.assertEqual(sum(1 for s in states if s == "work_target_added"), 1)  # one Work in flight

    def test_no_event_after_a_terminal_event(self) -> None:
        plan = generate.build_plan("S")
        terminal: set[str] = set()
        for _event_id, event_type, entity, _at in plan.events:
            self.assertNotIn(entity, terminal)
            if event_type in ("work_completed", "work_cancelled", "plan_excluded", "roadmap_achieved"):
                terminal.add(entity)

    def test_the_reduced_fixture_validates_quickly_in_process(self) -> None:
        from workline.store import ProjectStore
        from workline.validate import validate_project

        target, manifest = self.fixture("T")
        self.assertEqual(validate_project(ProjectStore(target / "project")), [])
        porcelain = subprocess.run(["git", "-C", str(target / "project"), "status", "--porcelain", "--untracked-files=all"],
                                   capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(porcelain, [f"?? {manifest['pending_record']}"])

    def test_the_generated_s_fixture_validates_through_the_launcher(self) -> None:
        target, _ = self.fixture("S")
        project = target / "project"
        completed = subprocess.run(run.validate_command(PYTHON, ROOT, project), cwd=project, capture_output=True,
                                   timeout=600)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(completed.stdout.decode().strip(), run.VALIDATE_PASS_LINE)

    def test_the_generator_never_writes_outside_its_target(self) -> None:
        sibling = self.base / "sibling"
        sibling.mkdir()
        (sibling / "keep.txt").write_text("keep", encoding="utf-8")
        before = snapshot(self.base)
        target, _ = self.fixture("T", "inside")
        after = snapshot(self.base)
        added = sorted(set(after) - set(before))
        self.assertTrue(added)
        self.assertTrue(all(path == "inside" or path.startswith("inside/") for path in added), added)
        self.assertEqual({k: v for k, v in after.items() if not k.startswith("inside")}, before)

    def test_the_generator_refuses_unsafe_targets(self) -> None:
        occupied = self.base / "occupied"
        occupied.mkdir()
        (occupied / "x").write_text("x", encoding="utf-8")
        with self.assertRaises(generate.GeneratorError):
            generate.generate(occupied, "T", ROOT, allowed_base=self.base)
        outside = Path(tempfile.gettempdir()) / "rb2-never-created"
        with self.assertRaises(generate.GeneratorError):
            generate.generate(outside, "T", ROOT, allowed_base=self.base)
        self.assertFalse(outside.exists())
        with self.assertRaises(generate.GeneratorError):
            generate.generate(ROOT / "benchmarks" / "rb2" / "never", "T", ROOT)
        self.assertFalse((ROOT / "benchmarks" / "rb2" / "never").exists())
        self.assertEqual(sorted(path.name for path in occupied.iterdir()), ["x"])


# --------------------------------------------------------------------------- runner


class RunnerTests(FixtureCase):
    def test_the_runner_binds_the_supported_launcher_commands(self) -> None:
        from workline import cli, status

        project = Path("project-root")
        self.assertEqual(run.status_command(["py", "-3"], ROOT, project),
                         ["py", "-3", "-I", "-B", str(ROOT / "run-workline.py"), "status", "project-root", "--json"])
        self.assertEqual(run.validate_command(["py", "-3"], ROOT, project),
                         ["py", "-3", "-I", "-B", str(ROOT / "run-workline.py"), "validate-project", "project-root"])
        self.assertEqual(run.STATUS_COMMAND, cli.READ_ONLY_STATUS_COMMAND)
        self.assertFalse(cli.binds_invocation_project([run.STATUS_COMMAND, "x", run.STATUS_JSON_FLAG]))
        self.assertEqual((run.STATUS_SCHEMA, run.STATUS_VERSION), (status.SCHEMA, status.VERSION))
        self.assertTrue(callable(getattr(status, run.STATUS_API[1])) and callable(getattr(status, run.STATUS_API[2])))
        expected = ["py", "-3"] if os.name == "nt" else ["python3"]
        self.assertEqual(run.python_command(), expected)
        self.assertEqual(run.portable(run.status_command(["py", "-3"], ROOT, ROOT.parent / "p"), ROOT, ROOT.parent / "p"),
                         "py -3 -I -B <workline-root>/run-workline.py status <project-root> --json")

    def test_every_landed_span_boundary_exists(self) -> None:
        import importlib

        for module_name, dotted, stage in run.WORKLINE_SPANS + run.DERIVATION_SPANS:
            owner = importlib.import_module(module_name)
            for part in dotted.split("."):
                owner = getattr(owner, part)
            self.assertTrue(callable(owner), f"{module_name}.{dotted}")
            self.assertIn(stage, run.STAGES)
        launcher = (ROOT / "run-workline.py").read_text(encoding="utf-8")
        for name, _stage in run.LAUNCHER_SPANS:
            self.assertIn(f"def {name}(", launcher)

    def test_the_runner_rejects_a_fixture_that_fails_validation(self) -> None:
        target, _ = self.fixture("T")
        events = target / "project" / ".workline" / "events" / "events.jsonl"
        with open(events, "a", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps({"id": "evt_01KDVDNA5BF8XVVAWSE7S5M64Z", "type": "work_started",
                                     "entity": "w_01KDVDNA5BF8XVVAWSE7S5M64Z", "at": "2026-01-01T00:00:00+00:00"}) + "\n")
        with self.assertRaises(run.HarnessStop) as raised:
            run.admit(target, ROOT, PYTHON)
        self.assertIn("fails validate-project", str(raised.exception))

    def test_the_runner_rejects_a_fixture_of_another_workline_root(self) -> None:
        target, _ = self.fixture("T")
        project_yaml = target / "project" / ".workline" / "project.yaml"
        text = project_yaml.read_text(encoding="utf-8")
        project_yaml.write_text(text.replace(json.dumps(str(ROOT)), json.dumps(str(self.base))), encoding="utf-8")
        with self.assertRaises(run.HarnessStop):
            run.admit(target, ROOT, PYTHON)

    def test_instrumented_and_uninstrumented_status_json_are_identical(self) -> None:
        target, _ = self.fixture("T")
        reference = run.admit(target, ROOT, PYTHON)
        work = self.base / "work"
        work.mkdir()
        project = (target / "project").resolve()
        for derivation in (False, True):
            data = run.component_run("T", "status", project, ROOT, PYTHON, work, reference, 0, derivation=derivation)
            self.assertTrue(data["output_identical"])
            stages = {entry[0] for entry in data["spans"].values()}
            self.assertTrue({"A", "B", "C", "D", "E", "F", "G", "H", "I"} <= stages, stages)
            self.assertTrue(data["git"])
            self.assertFalse(any(key.startswith("socket.") for key in data["events"]))
            self.assertEqual("state.ProjectView.events_for" in data["spans"], derivation)
            self.assertIn("harness.install_spans", data["spans"])
        validate = run.component_run("T", "validate", project, ROOT, PYTHON, work, reference, 0)
        self.assertTrue(validate["output_identical"])
        warm = run.warm_series("T", project, ROOT, PYTHON, 2, work, reference)
        self.assertTrue(warm["matches_cold_reference"])
        self.assertEqual(len(warm["calls_ns"]), 2)

    def test_a_measurement_run_leaves_the_fixture_unchanged(self) -> None:
        fixtures = self.base / "fixtures"
        logs = self.base / "logs"
        args = argparse.Namespace(
            workline_root=str(ROOT), fixtures=str(fixtures), logs=str(logs), label="SMOKE",
            measured_sha=subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                                        text=True).stdout.strip(),
            measured_note="test run", scales=["T"], seed=generate.DEFAULT_SEED, reps=1, warm_calls=2, component_samples=1, derivation_samples=1,
            sequence_reps=1, phases=["cold", "warm", "component", "sequence", "trace"], python=PYTHON,
            suites_dir=None, no_quiet_check=True,
        )
        fixtures.mkdir()
        fixture = run.ensure_fixture(fixtures, "T", ROOT, generate.DEFAULT_SEED)
        before = run.fixture_identity(fixture / "project")
        results = run.run_series(args)
        after = run.fixture_identity(fixture / "project")
        self.assertEqual(before, after)
        self.assertGreaterEqual(results["integrity_checks"], 5)
        summary_path = next(logs.glob("smoke-*/summary.md"))
        summary = summary_path.read_text(encoding="utf-8")
        self.assertEqual(run.public_safety_problems(summary), [])
        self.assertNotIn(str(fixtures), summary)
        self.assertNotIn(str(ROOT), summary)
        self.assertIn("does not benchmark LLM reasoning latency", summary)
        self.assertIn("## Limitations", summary)
        self.assertIn("Measured Workline status: test run", summary)
        trace = results["scales"]["T"]["trace2"]["status"]
        component = results["scales"]["T"]["component"]["status"][0]
        hermetic = sum(1 for row in component["git"] if row[3])
        self.assertEqual(trace["total"] + hermetic, len(component["git"]), "Trace2 sees every non-hermetic Git command")

    def test_no_network_git_command_is_accepted(self) -> None:
        for family in ("fetch", "push", "pull", "ls-remote", "clone", "remote show", "remote update"):
            self.assertEqual(run.check_git_families([family])["network"], [family])
        local = ["rev-parse", "symbolic-ref", "status", "ls-files", "ls-tree", "remote", "remote get-url", "cat-file"]
        self.assertEqual(run.check_git_families(local), {"network": [], "unclassified": []})
        self.assertEqual(run.git_family(["-c", "core.hooksPath=x", "ls-remote", "origin"]), "ls-remote")
        self.assertEqual(run.git_family(["remote", "get-url", "--push", "--all", "origin"]), "remote get-url")
        self.assertEqual(run.git_family(["--no-optional-locks", "status", "--porcelain=v1"]), "status")
        self.assertEqual(run.git_family(["remote"]), "remote")
        self.assertEqual(run.table_family("remote get-url"), "remote/config")
        self.assertEqual(run.table_family("cat-file"), "other")

    def test_the_summary_check_finds_absolute_paths_and_private_names(self) -> None:
        self.assertEqual(run.public_safety_problems("median 12.0 ms at <project-root>", []), [])
        self.assertTrue(run.public_safety_problems(r"read D:\tmp\x", []))
        self.assertTrue(run.public_safety_problems("read /home/someone/x", []))
        self.assertTrue(run.public_safety_problems("ran on host-name-xyz", ["host-name-xyz"]))
        self.assertTrue(run.public_safety_problems(f"cwd {ROOT}"))


# --------------------------------------------------------------------------- trigger arithmetic


class TriggerArithmeticTests(unittest.TestCase):
    def candidate(self, numerator: float, removable: str | None = "reused snapshot") -> dict:
        return {"name": "x", "numerator_ms": numerator, "supported": True, "removable": removable, "support": "span"}

    def test_trigger_a_is_strictly_more_than_half(self) -> None:
        self.assertFalse(run.evaluate_trigger_a([self.candidate(49.99)], 100.0)["trigger"])
        self.assertFalse(run.evaluate_trigger_a([self.candidate(50.0)], 100.0)["trigger"])
        self.assertTrue(run.evaluate_trigger_a([self.candidate(50.01)], 100.0)["trigger"])

    def test_trigger_a_needs_a_removable_supported_derivation(self) -> None:
        self.assertFalse(run.evaluate_trigger_a([self.candidate(90.0, removable=None)], 100.0)["trigger"])
        unsupported = {**self.candidate(90.0), "supported": False}
        self.assertFalse(run.evaluate_trigger_a([unsupported], 100.0)["trigger"])
        # two candidates below half each are never added into one claim
        self.assertFalse(run.evaluate_trigger_a([self.candidate(30.0), self.candidate(30.0)], 100.0)["trigger"])
        # a profiler estimate supports, it never proves (§36.17: ambiguous attribution is not-proven)
        estimate = run.evaluate_trigger_a([{**self.candidate(90.0), "estimate": True}], 100.0)
        self.assertFalse(estimate["trigger"])
        self.assertTrue(estimate["estimate_exceeds_half"])
        # a bound over a whole family is never one removable derivation
        bound = run.evaluate_trigger_a([{**self.candidate(95.0, removable=None), "bound": True}], 100.0)
        self.assertFalse(bound["trigger"])

    def test_trigger_a_above_half_inside_noise_is_non_robust(self) -> None:
        robust = run.evaluate_trigger_a([self.candidate(60.0)], 100.0, 110.0)
        self.assertTrue(robust["trigger"])
        self.assertFalse(robust["non_robust"])
        noisy = run.evaluate_trigger_a([self.candidate(52.0)], 100.0, 110.0)
        self.assertFalse(noisy["trigger"])
        self.assertTrue(noisy["non_robust"])
        self.assertEqual(run.decide(noisy["trigger"], ["false"], trigger_a_non_robust=noisy["non_robust"]),
                         "STOP_NON_ROBUST")

    def test_trigger_b_is_strictly_more_than_twelve_times_outside_noise(self) -> None:
        small = [10.0, 10.0, 10.0, 10.0, 10.0]
        self.assertEqual(run.evaluate_trigger_b(small, [119.9] * 5)["verdict"], "false")
        self.assertEqual(run.evaluate_trigger_b(small, [120.0] * 5)["verdict"], "false")
        self.assertEqual(run.evaluate_trigger_b(small, [120.1] * 5)["verdict"], "true")
        noisy_small = [8.0, 9.0, 10.0, 11.0, 12.0]
        noisy_large = [100.0, 115.0, 125.0, 135.0, 150.0]
        found = run.evaluate_trigger_b(noisy_small, noisy_large)
        self.assertGreater(found["ratio"], 12.0)
        self.assertEqual(found["verdict"], "non_robust")
        self.assertAlmostEqual(found["ratio"], 12.5)

    def test_one_outlier_does_not_make_super_linearity(self) -> None:
        small = [10.0] * 15
        large = [100.0] * 14 + [10_000.0]
        self.assertEqual(run.evaluate_trigger_b(small, large)["verdict"], "false")

    def test_the_decision_is_deterministic(self) -> None:
        self.assertEqual(run.decide(False, ["false", "false"]), "MEASURED_NO_OPT")
        self.assertEqual(run.decide(True, ["false"]), "MEASURED_TRIGGER_A")
        self.assertEqual(run.decide(False, ["false", "true"]), "MEASURED_TRIGGER_B")
        self.assertEqual(run.decide(True, ["true"]), "MEASURED_TRIGGER_A_AND_B")
        self.assertEqual(run.decide(False, ["non_robust", "false"]), "STOP_NON_ROBUST")
        self.assertEqual(run.decide(False, ["non_robust", "true"]), "MEASURED_TRIGGER_B")
        self.assertEqual(run.decide(False, ["false"], trigger_a_non_robust=True), "STOP_NON_ROBUST")
        for _ in range(3):
            self.assertEqual(run.decide(False, ["false", "false"]), "MEASURED_NO_OPT")

    def test_stage_accounting_deduplicates_nesting(self) -> None:
        sample = {
            "spans": {"outer": ["G", 1, 100_000_000, 40_000_000], "inner": ["E", 2, 60_000_000, 60_000_000],
                      "harness.install_spans": ["harness", 1, 5_000_000, 5_000_000]},
            "in_process_ns": 130_000_000, "harness_ns": 10_000_000, "wall_ns": 150_000_000,
        }
        stages = run.stage_samples([sample])
        self.assertEqual(stages["G"], [40.0])
        self.assertEqual(stages["E"], [60.0])
        self.assertEqual(stages["harness"], [15.0])
        self.assertEqual(stages["unassigned"], [15.0])
        self.assertEqual(stages["process_overhead"], [20.0])
        rows = run.label_table([sample])
        inner = next(row for row in rows if row["label"] == "inner")
        candidates = run.trigger_a_candidates(
            [{**inner, "label": "state.ProjectView.load"}],
            {"identical_repeat_removable_ms": 0.0, "identical_repeat_count": 0}, None, 130.0)
        load = candidates[0]
        self.assertAlmostEqual(load["numerator_ms"], 30.0)  # the second of two equal loads


if __name__ == "__main__":
    unittest.main()
