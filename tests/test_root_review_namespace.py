"""Review namespace descriptors (``WORKLINE_COMPLETION_SPRINT`` §31.4 / §31.6 / §31.50, descriptor part; RB7-A).

* Project path compatibility: every ``review.paths`` constant and builder equals
  the PROJECT descriptor's - the same values, and for every refused input the same
  exception, code and message - so the delegation of ``paths.py`` to it is
  unobservable; the Project subdirectories stay exactly the pinned ones;
* root path shape: ``review-policy/review`` with exactly the §31.6 record areas;
  the root namespace refuses the history, policy (and Profile), Work-terminal
  activation and repair areas wherever they would be named;
* malformed / traversal / foreign-namespace paths are refused (fail closed);
* the root policy layout (§16.3) beside the root Review namespace;
* the module is pure, never reaches ``review.history`` (AO-3), never spells the
  Work-terminal activation path constant (AO-5), and carries no record rule of its
  own (no copied validation).

The §31.50 store / committed reader / validator / recovery rows need the shared
namespace refactor (IR-RB7-3 / IR-RB7-4) and are not here (map FLAG-6).
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
import re
import unittest

from workline import ids
from workline.errors import ValidationError
from workline.review import namespace, paths, policy
from workline.review.namespace import (
    NAMESPACES,
    PROJECT_REVIEW_NAMESPACE as PROJECT,
    ROOT_POLICY_LAYOUT as LAYOUT,
    ROOT_POLICY_REVIEW_NAMESPACE as ROOT,
    ReviewNamespace,
    RootPolicyLayout,
)

SOURCE = Path(namespace.__file__)
DIGEST = "0123456789abcdef" * 4


def outcome(function, *args):
    """What calling ``function(*args)`` does: its value, or the exception type, code and message it raises."""
    try:
        return ("value", function(*args))
    except Exception as exc:  # noqa: BLE001 - the comparison is the point, whatever is raised
        return (type(exc).__name__, getattr(exc, "code", None), str(exc))


def an(kind: str) -> str:
    return ids.new_id(kind)


def builder_cases() -> list[tuple[str, tuple]]:
    """Every record-path builder with accepted, wrongly kinded and malformed arguments."""
    rr, rcp, rcs, rtk = an("review_run"), an("review_receipt"), an("review_consumption"), an("review_task")
    rrb, rfd, rhr, rhd = an("review_repair_batch"), an("review_finding"), an("review_relation"), an("review_decision")
    rpc, rpe = an("review_policy_change"), an("review_policy_evaluation")
    malformed = ("", None, 5, "rr_short", rr.lower(), " " + rr, rr + "x", "../" + rr, rr + "/x")
    cases: list[tuple[str, tuple]] = []
    for name, good, wrong in (
        ("run_dir", rr, rcp), ("serialization_token_rel", rr, rcp), ("receipt_rel", rcp, rr),
        ("consumption_rel", rcs, rcp), ("supersession_rel", rcp, rcs), ("task_input_rel", rtk, rr),
        ("adjudication_rel", rr, rcp), ("repair_batch_rel", rrb, rfd), ("repair_result_rel", rrb, rr),
    ):
        cases += [(name, (good,)), (name, (wrong,))] + [(name, (bad,)) for bad in malformed]
    for name in ("candidate_snapshot_rel", "report_rel"):
        cases += [(name, (value,)) for value in (DIGEST, DIGEST.upper(), DIGEST[:-1], DIGEST + "0", "", None, 5)]
    for generation in (1, 12, 0, -3, True, 1.5, "2"):
        cases.append(("gate_rel", (rr, generation)))
    cases += [("gate_rel", (rcp, 1)), ("gate_rel", (None, 0))]
    for family in namespace.HISTORY_FAMILIES + ("achievements", "", None, "Runs", "runs/"):
        cases.append(("history_family_dir", (family,)))
    for family, good, wrong in ((namespace.HISTORY_RUNS, rr, rfd), (namespace.HISTORY_FINDINGS, rfd, rr),
                                (namespace.HISTORY_REPAIRS, rrb, rr), (namespace.HISTORY_RELATIONS, rhr, rhd),
                                (namespace.HISTORY_HUMAN_DECISIONS, rhd, rhr), ("achievements", rr, rr)):
        cases += [("history_rel", (family, good)), ("history_rel", (family, wrong)), ("history_rel", (family, None))]
    for family in namespace.POLICY_FAMILIES + ("profile", "", None):
        cases.append(("policy_family_dir", (family,)))
    for family, good, wrong in ((namespace.POLICY_CHANGES, rpc, rpe), (namespace.POLICY_EVALUATIONS, rpe, rpc),
                                ("profile", rpc, rpc)):
        cases += [("policy_record_rel", (family, good)), ("policy_record_rel", (family, wrong))]
    return cases


class ProjectPathCompatibilityTests(unittest.TestCase):
    """The PROJECT descriptor is ``paths.py``, value for value and refusal for refusal."""

    def test_the_constants_are_the_paths_constants(self) -> None:
        self.assertEqual(".workline/review", namespace.PROJECT_REVIEW_ROOT)
        for expected, actual in (
            (paths.REVIEW_DIR, PROJECT.root),
            (paths.REVIEW_DIR, namespace.PROJECT_REVIEW_ROOT),
            (paths.GATES_DIR, PROJECT.gates_dir),
            (paths.RECEIPTS_DIR, PROJECT.receipts_dir),
            (paths.CONSUMPTIONS_DIR, PROJECT.consumptions_dir),
            (paths.SUPERSESSIONS_DIR, PROJECT.supersessions_dir),
            (paths.CANDIDATE_SNAPSHOTS_DIR, PROJECT.candidate_snapshots_dir),
            (paths.TASK_INPUTS_DIR, PROJECT.task_inputs_dir),
            (paths.ACTIVATION_DIR, PROJECT.activation_dir),
            (paths.REPORTS_DIR, PROJECT.reports_dir),
            (paths.ADJUDICATIONS_DIR, PROJECT.adjudications_dir),
            (paths.REPAIR_BATCHES_DIR, PROJECT.repair_batches_dir),
            (paths.REPAIR_RESULTS_DIR, PROJECT.repair_results_dir),
            (paths.HISTORY_DIR, PROJECT.history_dir),
            (paths.POLICY_DIR, PROJECT.policy_dir),
            (paths.POLICY_PROFILE_REL, PROJECT.policy_profile_rel),
            (paths.REVIEW_SUBDIRS, PROJECT.subdirs),
            (paths.REVIEW_SUBDIRS, namespace.PROJECT_SUBDIRS),
            (paths.GENERATION_WIDTH, namespace.GENERATION_WIDTH),
            (paths.SERIALIZATION_TOKEN, namespace.SERIALIZATION_TOKEN),
            (paths.HISTORY_RUNS, namespace.HISTORY_RUNS),
            (paths.HISTORY_FINDINGS, namespace.HISTORY_FINDINGS),
            (paths.HISTORY_REPAIRS, namespace.HISTORY_REPAIRS),
            (paths.HISTORY_RELATIONS, namespace.HISTORY_RELATIONS),
            (paths.HISTORY_HUMAN_DECISIONS, namespace.HISTORY_HUMAN_DECISIONS),
            (paths.HISTORY_FAMILIES, namespace.HISTORY_FAMILIES),
            (paths.HISTORY_FAMILY_KINDS, namespace.HISTORY_FAMILY_KINDS),
            (paths.POLICY_PROFILE_NAME, namespace.POLICY_PROFILE_NAME),
            (paths.POLICY_CHANGES, namespace.POLICY_CHANGES),
            (paths.POLICY_EVALUATIONS, namespace.POLICY_EVALUATIONS),
            (paths.POLICY_FAMILIES, namespace.POLICY_FAMILIES),
            (paths.POLICY_FAMILY_KINDS, namespace.POLICY_FAMILY_KINDS),
        ):
            with self.subTest(expected=expected):
                self.assertEqual(expected, actual)
                self.assertIs(type(expected), type(actual))

    def test_the_project_subdirectories_are_exactly_the_pinned_ones(self) -> None:
        pinned = ("gates", "receipts", "consumptions", "supersessions", "candidate-snapshots", "task-inputs",
                  "activation", "reports", "adjudications", "repair-batches", "repair-results", "history", "policy")
        self.assertEqual(pinned, namespace.PROJECT_SUBDIRS)
        self.assertEqual(pinned, PROJECT.subdirs)
        self.assertEqual(pinned, paths.REVIEW_SUBDIRS)
        self.assertEqual(("project", True, True, True, True),
                         (PROJECT.name, PROJECT.history, PROJECT.policy, PROJECT.activation, PROJECT.repairs))

    def test_the_activation_area_holds_the_activation_path(self) -> None:
        """AO-5: the descriptor admits the area by flag; the path constant stays ``paths.py``'s."""
        self.assertTrue(paths.WORK_TERMINAL_ACTIVATION_REL.startswith(PROJECT.activation_dir + "/"))
        PROJECT.require_record_path(paths.WORK_TERMINAL_ACTIVATION_REL)
        self.assertFalse(ROOT.is_review_path(paths.WORK_TERMINAL_ACTIVATION_REL))

    def test_the_generation_names_are_the_paths_ones(self) -> None:
        for generation in (1, 2, 999999, 1000000, 0, -1, True, 1.0, "1", None):
            with self.subTest(generation=generation):
                self.assertEqual(outcome(paths.generation_name, generation), outcome(namespace.generation_name, generation))
        for name in ("000001.yaml", "000000.yaml", "1.yaml", "0000001.yaml", "00000a.yaml", "000001.yml", "000001",
                     "\uff10\uff10\uff10\uff10\uff10\uff11.yaml", "", None, 1):
            with self.subTest(name=name):
                self.assertEqual(outcome(paths.generation_of_name, name), outcome(namespace.generation_of_name, name))
        self.assertEqual("000001.yaml", namespace.generation_name(1))
        self.assertEqual(7, namespace.generation_of_name("000007.yaml"))

    def test_every_builder_returns_and_refuses_exactly_as_paths_does(self) -> None:
        values = 0
        for name, args in builder_cases():
            with self.subTest(builder=name, args=args):
                expected = outcome(getattr(paths, name), *args)
                self.assertEqual(expected, outcome(getattr(PROJECT, name), *args))
                values += expected[0] == "value"
        self.assertGreater(values, 20, "the corpus holds accepted inputs, not refusals alone")

    def test_the_builders_name_the_literal_project_paths(self) -> None:
        rr, rcp, rrb, rpc = an("review_run"), an("review_receipt"), an("review_repair_batch"), an("review_policy_change")
        self.assertEqual(f".workline/review/gates/{rr}/000003.yaml", PROJECT.gate_rel(rr, 3))
        self.assertEqual(f".workline/review/gates/{rr}/.generation-serialization", PROJECT.serialization_token_rel(rr))
        self.assertEqual(f".workline/review/supersessions/{rcp}.yaml", PROJECT.supersession_rel(rcp))
        self.assertEqual(f".workline/review/candidate-snapshots/{DIGEST}.yaml", PROJECT.candidate_snapshot_rel(DIGEST))
        self.assertEqual(f".workline/review/repair-results/{rrb}.yaml", PROJECT.repair_result_rel(rrb))
        self.assertEqual(f".workline/review/history/repairs/{rrb}.yaml", PROJECT.history_rel("repairs", rrb))
        self.assertEqual(f".workline/review/policy/changes/{rpc}.yaml", PROJECT.policy_record_rel("changes", rpc))
        self.assertEqual(".workline/review/policy/project-profile.yaml", PROJECT.policy_profile_rel)

    def path_corpus(self) -> list[object]:
        base = paths.REVIEW_DIR
        corpus: list[object] = [
            f"{base}/gates/rr_x/000001.yaml", f"{base}/gates/rr_x/.generation-serialization",
            f"{base}/gates/rr_x.yaml", f"{base}/gates/a/b/000001.yaml",
            f"{base}/history/achievements/x.yaml", f"{base}/history/runs/a/b.yaml", f"{base}/history/runs.yaml",
            f"{base}/policy/project-profile.yaml", f"{base}/policy/x.yaml", f"{base}/policy/profile/x.yaml",
            f"{base}/policy/changes/x.yml", f"{base}/unknown/x.yaml", f"{base}/x.yaml", base, base + "/",
            f"{base}/../x.yaml", f"{base}/receipts/../x.yaml", f"{base}//receipts/x.yaml", f"{base}/receipts/./x.yaml",
            f"{base}/receipts/x.yaml/", f"{base}\\receipts\\x.yaml", f"{base}/receipts\\x.yaml", f"{base}/receipts/x.yml",
            f"{base}/receipts/a/b.yaml", f"/{base}/receipts/x.yaml", f"{base}x/receipts/x.yaml",
            f"{namespace.ROOT_REVIEW_ROOT}/receipts/x.yaml", ".workline/runtime/review/reports/x.yaml",
            None, 5, b".workline/review/receipts/x.yaml", Path(f"{base}/receipts/x.yaml"),
        ]
        corpus += [f"{base}/{subdir}/x.yaml" for subdir in paths.REVIEW_SUBDIRS]
        corpus += [f"{base}/history/{family}/x.yaml" for family in paths.HISTORY_FAMILIES]
        corpus += [f"{base}/policy/{family}/x.yaml" for family in paths.POLICY_FAMILIES]
        return corpus

    def test_classification_and_shape_are_exactly_the_paths_ones(self) -> None:
        accepted = 0
        for relative in self.path_corpus():
            with self.subTest(relative=relative):
                self.assertEqual(paths.is_review_path(relative), PROJECT.is_review_path(relative))
                self.assertEqual(paths.is_policy_profile_path(relative), PROJECT.is_policy_profile_path(relative))
                self.assertEqual(outcome(paths.require_policy_profile_path, relative),
                                 outcome(PROJECT.require_policy_profile_path, relative))
                expected = outcome(paths.require_review_record_path, relative)
                self.assertEqual(expected, outcome(PROJECT.require_record_path, relative))
                self.assertEqual(outcome(paths.require_review_readable_path, relative),
                                 outcome(PROJECT.require_readable_path, relative))
                accepted += expected[0] == "value"
        self.assertGreater(accepted, 15, "the corpus holds accepted paths, not refusals alone")


class RootNamespaceShapeTests(unittest.TestCase):
    """``review-policy/review``: the §31.6 record areas, and none of the Project-only ones."""

    def test_the_root_descriptor(self) -> None:
        self.assertEqual("review-policy/review", ROOT.root)
        self.assertEqual("review-policy/review", namespace.ROOT_REVIEW_ROOT)
        self.assertEqual("review-policy", namespace.ROOT_POLICY_DIR)
        self.assertEqual(("gates", "receipts", "consumptions", "supersessions", "candidate-snapshots", "task-inputs",
                          "reports", "adjudications"), ROOT.subdirs)
        self.assertEqual(ROOT.subdirs, namespace.ROOT_SUBDIRS)
        self.assertEqual(("root-policy", False, False, False, False),
                         (ROOT.name, ROOT.history, ROOT.policy, ROOT.activation, ROOT.repairs))
        self.assertEqual((PROJECT, ROOT), NAMESPACES)
        self.assertTrue(set(ROOT.subdirs) < set(PROJECT.subdirs))

    def test_the_root_builders_name_paths_under_the_root(self) -> None:
        rr, rcp, rcs, rtk = an("review_run"), an("review_receipt"), an("review_consumption"), an("review_task")
        base = "review-policy/review"
        for actual, expected in (
            (ROOT.gates_dir, f"{base}/gates"), (ROOT.receipts_dir, f"{base}/receipts"),
            (ROOT.consumptions_dir, f"{base}/consumptions"), (ROOT.supersessions_dir, f"{base}/supersessions"),
            (ROOT.candidate_snapshots_dir, f"{base}/candidate-snapshots"), (ROOT.task_inputs_dir, f"{base}/task-inputs"),
            (ROOT.reports_dir, f"{base}/reports"), (ROOT.adjudications_dir, f"{base}/adjudications"),
            (ROOT.run_dir(rr), f"{base}/gates/{rr}"), (ROOT.gate_rel(rr, 2), f"{base}/gates/{rr}/000002.yaml"),
            (ROOT.serialization_token_rel(rr), f"{base}/gates/{rr}/.generation-serialization"),
            (ROOT.receipt_rel(rcp), f"{base}/receipts/{rcp}.yaml"),
            (ROOT.consumption_rel(rcs), f"{base}/consumptions/{rcs}.yaml"),
            (ROOT.supersession_rel(rcp), f"{base}/supersessions/{rcp}.yaml"),
            (ROOT.candidate_snapshot_rel(DIGEST), f"{base}/candidate-snapshots/{DIGEST}.yaml"),
            (ROOT.task_input_rel(rtk), f"{base}/task-inputs/{rtk}.yaml"),
            (ROOT.report_rel(DIGEST), f"{base}/reports/{DIGEST}.yaml"),
            (ROOT.adjudication_rel(rr), f"{base}/adjudications/{rr}.yaml"),
        ):
            with self.subTest(expected=expected):
                self.assertEqual(expected, actual)
                if not actual.endswith(".generation-serialization") and actual.endswith(".yaml"):
                    ROOT.require_record_path(actual)
        for subdir in ROOT.subdirs:
            self.assertEqual(f"{base}/{subdir}", ROOT.dir(subdir))

    def test_the_root_builders_validate_exactly_as_the_project_ones(self) -> None:
        """One validation: the same refusal, code and message under either root."""
        for name, args in builder_cases():
            if name.startswith(("history", "policy", "repair")):
                continue
            with self.subTest(builder=name, args=args):
                project, root = outcome(getattr(PROJECT, name), *args), outcome(getattr(ROOT, name), *args)
                if project[0] == "value":
                    self.assertEqual(("value", namespace.ROOT_REVIEW_ROOT + project[1][len(PROJECT.root):]), root)
                else:
                    self.assertEqual(project, root)

    def test_the_project_only_areas_are_refused(self) -> None:
        rr, rrb, rpc = an("review_run"), an("review_repair_batch"), an("review_policy_change")
        refusals = [
            ("history_dir", lambda: ROOT.history_dir), ("policy_dir", lambda: ROOT.policy_dir),
            ("policy_profile_rel", lambda: ROOT.policy_profile_rel), ("activation_dir", lambda: ROOT.activation_dir),
            ("repair_batches_dir", lambda: ROOT.repair_batches_dir),
            ("repair_results_dir", lambda: ROOT.repair_results_dir),
            ("history_family_dir", lambda: ROOT.history_family_dir("runs")),
            ("history_family_dir unknown", lambda: ROOT.history_family_dir("achievements")),
            ("history_rel", lambda: ROOT.history_rel("runs", rr)),
            ("policy_family_dir", lambda: ROOT.policy_family_dir("changes")),
            ("policy_record_rel", lambda: ROOT.policy_record_rel("changes", rpc)),
            ("repair_batch_rel", lambda: ROOT.repair_batch_rel(rrb)),
            ("repair_result_rel", lambda: ROOT.repair_result_rel(rrb)),
            ("repair_batch_rel malformed", lambda: ROOT.repair_batch_rel(None)),
            ("require_policy_profile_path", lambda: ROOT.require_policy_profile_path(f"{ROOT.root}/policy/project-profile.yaml")),
        ]
        refusals += [(f"dir {subdir}", lambda subdir=subdir: ROOT.dir(subdir))
                     for subdir in ("history", "policy", "activation", "repair-batches", "repair-results", "unknown",
                                    "", "..", "gates/x", None)]
        for label, refused in refusals:
            with self.subTest(label):
                with self.assertRaises(ValidationError) as raised:
                    refused()
                self.assertEqual("review_namespace_invalid", raised.exception.code)

    def test_the_root_record_shape(self) -> None:
        base = ROOT.root
        accepted = [f"{base}/gates/rr_x/000001.yaml"] + [f"{base}/{subdir}/x.yaml" for subdir in ROOT.subdirs
                                                          if subdir != "gates"]
        for relative in accepted:
            with self.subTest(accepted=relative):
                ROOT.require_record_path(relative)
                ROOT.require_readable_path(relative)
                self.assertTrue(ROOT.is_review_path(relative))
        refused = [
            # the Project-only areas, in their Project shapes, under the root
            f"{base}/history/runs/x.yaml", f"{base}/history/human-decisions/x.yaml", f"{base}/policy/changes/x.yaml",
            f"{base}/policy/evaluations/x.yaml", f"{base}/policy/project-profile.yaml",
            f"{base}/activation/work-terminal-v1.yaml", f"{base}/activation/x.yaml", f"{base}/repair-batches/x.yaml",
            f"{base}/repair-results/x.yaml", f"{base}/history/x.yaml", f"{base}/policy/x.yaml",
            # malformed / traversal
            base, base + "/", f"{base}/x.yaml", f"{base}/unknown/x.yaml", f"{base}/gates/x.yaml",
            f"{base}/gates/a/b/000001.yaml", f"{base}/receipts/a/b.yaml", f"{base}/receipts/x.yml",
            f"{base}/receipts/x.yaml/", f"{base}/../x.yaml", f"{base}/receipts/../x.yaml", f"{base}//receipts/x.yaml",
            f"{base}/receipts/./x.yaml", f"{base}\\receipts\\x.yaml", f"{base}/receipts\\x.yaml", f"/{base}/receipts/x.yaml",
            f"{base}x/receipts/x.yaml", "review-policy/receipts/x.yaml", "review-policy/global-policy.yaml",
            "review-policy/changes/x.yaml",
            # the other namespace
            f"{paths.REVIEW_DIR}/receipts/x.yaml", f"{paths.REVIEW_DIR}/gates/rr_x/000001.yaml",
            None, 5, b"review-policy/review/receipts/x.yaml", Path(f"{base}/receipts/x.yaml"),
        ]
        for relative in refused:
            with self.subTest(refused=relative):
                for check in (ROOT.require_record_path, ROOT.require_readable_path):
                    with self.assertRaises(ValidationError) as raised:
                        check(relative)
                    self.assertEqual("review_containment", raised.exception.code)

    def test_the_root_has_no_profile(self) -> None:
        for relative in (f"{ROOT.root}/policy/project-profile.yaml", paths.POLICY_PROFILE_REL, None):
            with self.subTest(relative=relative):
                self.assertFalse(ROOT.is_policy_profile_path(relative))
                with self.assertRaises(ValidationError):
                    ROOT.require_readable_path(relative)
        self.assertTrue(PROJECT.is_policy_profile_path(paths.POLICY_PROFILE_REL))

    def test_the_namespaces_are_disjoint(self) -> None:
        rcp = an("review_receipt")
        self.assertFalse(PROJECT.is_review_path(ROOT.receipt_rel(rcp)))
        self.assertFalse(ROOT.is_review_path(PROJECT.receipt_rel(rcp)))
        with self.assertRaises(ValidationError):
            PROJECT.require_record_path(ROOT.receipt_rel(rcp))
        with self.assertRaises(ValidationError):
            ROOT.require_record_path(PROJECT.receipt_rel(rcp))
        self.assertFalse(ROOT.root.startswith(namespace.PROJECT_REVIEW_ROOT))
        self.assertNotIn(".workline", ROOT.root.split("/"))


class DescriptorTests(unittest.TestCase):
    def test_a_descriptor_is_immutable(self) -> None:
        for descriptor in NAMESPACES:
            with self.subTest(descriptor.name):
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    descriptor.root = "elsewhere"  # type: ignore[misc]
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    descriptor.history = True  # type: ignore[misc]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            LAYOUT.review_dir = ".workline/review"  # type: ignore[misc]

    def test_an_incoherent_descriptor_is_refused(self) -> None:
        root_flags = dict(history=False, policy=False, activation=False, repairs=False)
        project_flags = dict(history=True, policy=True, activation=True, repairs=True)
        incoherent = [
            ("root subdirs, history admitted", ("root-policy", ROOT.root, namespace.ROOT_SUBDIRS),
             dict(root_flags, history=True)),
            ("root subdirs, activation admitted", ("root-policy", ROOT.root, namespace.ROOT_SUBDIRS),
             dict(root_flags, activation=True)),
            ("project subdirs, no flags", ("root-policy", ROOT.root, namespace.PROJECT_SUBDIRS), root_flags),
            ("history dir without the flag", ("root-policy", ROOT.root, namespace.ROOT_SUBDIRS + ("history",)),
             root_flags),
            ("unknown subdir", ("root-policy", ROOT.root, namespace.ROOT_SUBDIRS + ("extra",)), root_flags),
            ("missing gates", ("root-policy", ROOT.root, namespace.ROOT_SUBDIRS[1:]), root_flags),
            ("reordered", ("root-policy", ROOT.root, tuple(reversed(namespace.ROOT_SUBDIRS))), root_flags),
            ("list subdirs", ("root-policy", ROOT.root, list(namespace.ROOT_SUBDIRS)), root_flags),
            ("one repair area only", ("project", PROJECT.root, tuple(s for s in namespace.PROJECT_SUBDIRS
                                                                      if s != "repair-results")), project_flags),
            ("non-boolean flag", ("root-policy", ROOT.root, namespace.ROOT_SUBDIRS), dict(root_flags, history=0)),
            ("empty name", ("", ROOT.root, namespace.ROOT_SUBDIRS), root_flags),
        ]
        incoherent += [(f"root {root!r}", ("root-policy", root, namespace.ROOT_SUBDIRS), root_flags)
                       for root in ("", "/review-policy/review", "review-policy/review/", "review-policy//review",
                                    "review-policy/./review", "../review", "review-policy\\review", "C:/review",
                                    None)]
        for label, args, flags in incoherent:
            with self.subTest(label):
                with self.assertRaises(ValidationError) as raised:
                    ReviewNamespace(*args, **flags)
                self.assertEqual("review_namespace_invalid", raised.exception.code)
        self.assertEqual(ROOT, ReviewNamespace("root-policy", ROOT.root, namespace.ROOT_SUBDIRS, **root_flags))
        self.assertEqual(PROJECT, ReviewNamespace("project", PROJECT.root, namespace.PROJECT_SUBDIRS, **project_flags))


class RootPolicyLayoutTests(unittest.TestCase):
    """§16.3: the Global policy file and four evidence families beside the root Review namespace."""

    def test_the_layout(self) -> None:
        self.assertEqual(RootPolicyLayout(), LAYOUT)
        self.assertEqual(
            ("review-policy", "review-policy/global-policy.yaml", "review-policy/promotion-packets",
             "review-policy/changes", "review-policy/evaluations", "review-policy/patch-notes", "review-policy/review"),
            (LAYOUT.root, LAYOUT.global_policy_rel, LAYOUT.promotion_packets_dir, LAYOUT.changes_dir,
             LAYOUT.evaluations_dir, LAYOUT.patch_notes_dir, LAYOUT.review_dir))
        self.assertEqual(policy.GLOBAL_POLICY_REL, LAYOUT.global_policy_rel)
        self.assertEqual(ROOT.root, LAYOUT.review_dir)
        self.assertEqual(namespace.ROOT_POLICY_DIR, LAYOUT.root)
        for directory in (LAYOUT.promotion_packets_dir, LAYOUT.changes_dir, LAYOUT.evaluations_dir,
                          LAYOUT.patch_notes_dir):
            with self.subTest(directory=directory):
                self.assertTrue(directory.startswith(LAYOUT.root + "/"))
                self.assertFalse(ROOT.is_review_path(directory + "/x.yaml"), "outside the root Review namespace")

    def test_an_incoherent_layout_is_refused(self) -> None:
        """RB7AL-1: every named path inside ``root``; the review dir is the root Review namespace's root."""
        for label, values in (
            ("review dir elsewhere in root", dict(review_dir="review-policy/other-review")),
            ("review dir is the Project namespace", dict(review_dir=paths.REVIEW_DIR)),
            ("family dir outside root", dict(changes_dir="elsewhere/changes")),
            ("family dir is root itself", dict(evaluations_dir="review-policy")),
            ("family dir through traversal", dict(patch_notes_dir="review-policy/../patch-notes")),
            ("policy file outside root", dict(global_policy_rel="global-policy.yaml")),
            ("policy file absolute", dict(global_policy_rel="/review-policy/global-policy.yaml")),
            ("non-string dir", dict(promotion_packets_dir=None)),
            ("another root", dict(root="other-policy")),
            ("absolute root", dict(root="/review-policy")),
        ):
            with self.subTest(label):
                with self.assertRaises(ValidationError) as raised:
                    RootPolicyLayout(**values)
                self.assertEqual("review_namespace_invalid", raised.exception.code)
        self.assertEqual(LAYOUT, RootPolicyLayout(**{field.name: getattr(LAYOUT, field.name)
                                                     for field in dataclasses.fields(LAYOUT)}))

    def test_the_owned_prefixes_are_the_closed_root_scope(self) -> None:
        self.assertEqual(("review-policy/review/", "review-policy/promotion-packets/", "review-policy/changes/",
                          "review-policy/evaluations/", "review-policy/patch-notes/", "review-policy/global-policy.yaml"),
                         LAYOUT.owned_prefixes())

    def test_the_builders_refuse_a_wrong_or_malformed_id(self) -> None:
        rr, rpc, rpe = an("review_run"), an("review_policy_change"), an("review_policy_evaluation")
        for builder in (LAYOUT.promotion_packet_rel, LAYOUT.global_change_rel, LAYOUT.patch_note_rel,
                        LAYOUT.global_evaluation_rel):
            for value in (rr, rpc, rpe, "", None, 5, "rgc_short", "../x", Path("x")):
                with self.subTest(builder=builder.__name__, value=value):
                    with self.assertRaises(ValidationError) as raised:
                        builder(value)
                    self.assertEqual("review_record_invalid", raised.exception.code)

    def test_family_of_names_the_policy_file_and_root_review_records(self) -> None:
        rr, rcs = an("review_run"), an("review_consumption")
        self.assertEqual("global-policy", LAYOUT.family_of("review-policy/global-policy.yaml"))
        self.assertEqual("review", LAYOUT.family_of(ROOT.gate_rel(rr, 1)))
        self.assertEqual("review", LAYOUT.family_of(ROOT.consumption_rel(rcs)))
        self.assertEqual("review", LAYOUT.family_of(ROOT.adjudication_rel(rr)))
        self.assertEqual(namespace.ROOT_POLICY_FAMILIES,
                         ("review", "promotion-packet", "change", "patch-note", "evaluation", "global-policy"))

    def test_family_of_is_none_for_anything_else(self) -> None:
        rr, rpc = an("review_run"), an("review_policy_change")
        for relative in (
            None, 5, b"review-policy/global-policy.yaml", Path("review-policy/global-policy.yaml"), "",
            "review-policy", "review-policy/", "review-policy/global-policy.yml", "review-policy/global-policy.yaml/",
            "/review-policy/global-policy.yaml", "review-policy/./global-policy.yaml", "review-policy\\global-policy.yaml",
            "review-policy/review", "review-policy/review/", ROOT.serialization_token_rel(rr),
            f"review-policy/review/history/runs/{rr}.yaml", "review-policy/review/policy/project-profile.yaml",
            "review-policy/review/activation/work-terminal-v1.yaml", f"review-policy/review/repair-batches/{rr}.yaml",
            f"review-policy/review/../changes/{rr}.yaml", f"{paths.REVIEW_DIR}/receipts/x.yaml",
            "review-policy/changes", "review-policy/changes/", "review-policy/changes/.yaml",
            f"review-policy/changes/{rr}.yaml", f"review-policy/changes/{rpc}.yaml",
            f"review-policy/evaluations/{rpc}.yaml", f"review-policy/patch-notes/{rpc}.md",
            f"review-policy/promotion-packets/{rr}.yaml", "review-policy/changes/../global-policy.yaml",
            "review-policy/changes/a/b.yaml", "review-policy/other/x.yaml", "review-policy/policy/changes/x.yaml",
        ):
            with self.subTest(relative=relative):
                self.assertIsNone(LAYOUT.family_of(relative))


class RootPolicyLayoutIdTests(unittest.TestCase):
    """The four evidence families: one flat level, the family's own ID kind and suffix."""

    def test_the_builders(self) -> None:
        rpp, rgc, rge = an("review_promotion_packet"), an("review_global_policy_change"), an("review_global_policy_evaluation")
        self.assertEqual(f"review-policy/promotion-packets/{rpp}.yaml", LAYOUT.promotion_packet_rel(rpp))
        self.assertEqual(f"review-policy/changes/{rgc}.yaml", LAYOUT.global_change_rel(rgc))
        self.assertEqual(f"review-policy/patch-notes/{rgc}.md", LAYOUT.patch_note_rel(rgc))
        self.assertEqual(f"review-policy/evaluations/{rge}.yaml", LAYOUT.global_evaluation_rel(rge))
        for builder, wrong in ((LAYOUT.promotion_packet_rel, rgc), (LAYOUT.global_change_rel, rge),
                               (LAYOUT.patch_note_rel, rpp), (LAYOUT.global_evaluation_rel, rgc),
                               (LAYOUT.global_change_rel, rgc + "\n"), (LAYOUT.global_change_rel, rgc.lower())):
            with self.subTest(builder=builder.__name__, wrong=wrong):
                with self.assertRaises(ValidationError) as raised:
                    builder(wrong)
                self.assertEqual("review_record_invalid", raised.exception.code)

    def test_family_of_the_evidence_families(self) -> None:
        rpp, rgc, rge = an("review_promotion_packet"), an("review_global_policy_change"), an("review_global_policy_evaluation")
        for builder, value, family in ((LAYOUT.promotion_packet_rel, rpp, "promotion-packet"),
                                       (LAYOUT.global_change_rel, rgc, "change"),
                                       (LAYOUT.patch_note_rel, rgc, "patch-note"),
                                       (LAYOUT.global_evaluation_rel, rge, "evaluation")):
            with self.subTest(family=family):
                relative = builder(value)
                self.assertEqual(family, LAYOUT.family_of(relative))
                self.assertTrue(any(relative.startswith(prefix) for prefix in LAYOUT.owned_prefixes()
                                    if prefix.endswith("/")))
        for relative in (
            f"review-policy/changes/{rge}.yaml", f"review-policy/evaluations/{rgc}.yaml",
            f"review-policy/promotion-packets/{rgc}.yaml", f"review-policy/patch-notes/{rge}.md",
            f"review-policy/changes/{rgc}.md", f"review-policy/patch-notes/{rgc}.yaml",
            f"review-policy/promotion-packets/{rpp}.md", f"review-policy/changes/{rgc}\n.yaml",
            f"review-policy/changes/{rgc.lower()}.yaml", f"review-policy/changes/{rgc}/x.yaml",
            f"review-policy/changes/sub/{rgc}.yaml", f"review-policy/review/changes/{rgc}.yaml",
            f"review-policy/changes/{rgc}.yaml.yaml",
        ):
            with self.subTest(relative=relative):
                self.assertIsNone(LAYOUT.family_of(relative))


class ModulePurityTests(unittest.TestCase):
    """Pure descriptors: no IO, no history (AO-3), no activation path constant (AO-5), no record rule of its own."""

    def tree(self) -> ast.Module:
        return ast.parse(SOURCE.read_text(encoding="utf-8"))

    def test_the_module_imports_only_errors_ids_and_the_store_constant(self) -> None:
        tree = self.tree()
        top = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                top |= {("." * node.level + (node.module or ""), alias.name) for alias in node.names}
            self.assertNotIsInstance(node, ast.Import, "no plain module import")
        self.assertEqual({("__future__", "annotations"), ("dataclasses", "dataclass"), ("..errors", "ValidationError"),
                          ("..ids", "is_valid_id"), ("..store", "WORKLINE_DIR")}, top)
        nested = [(("." * node.level + (node.module or "")), tuple(alias.name for alias in node.names))
                  for function in ast.walk(tree) if isinstance(function, ast.FunctionDef)
                  for node in ast.walk(function) if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertEqual([(".records", ("DIGEST_RE",))], nested, "the one lazy import: the digest pattern")

    def test_the_module_never_reaches_history(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\bimport history\b|from \.history import|from \. import .*\bhistory\b"
                                    r"|from \.review import .*\bhistory\b|review\.history", text))
        modules = {node.module or "" for node in ast.walk(self.tree()) if isinstance(node, ast.ImportFrom)}
        self.assertFalse({module for module in modules if "history" in module})

    def test_the_module_never_spells_the_activation_path_constant(self) -> None:
        self.assertNotIn("WORK_TERMINAL_ACTIVATION_REL", SOURCE.read_text(encoding="utf-8"))
        self.assertNotIn("work-terminal-v1", SOURCE.read_text(encoding="utf-8"))

    def test_the_module_does_no_io_and_carries_no_record_rule(self) -> None:
        tree = self.tree()
        called = {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                  for node in ast.walk(tree) if isinstance(node, ast.Call)}
        for forbidden in ("open", "read_text", "read_bytes", "write_text", "write_bytes", "mkdir", "exists", "is_dir",
                          "is_file", "stat", "lstat", "unlink", "rename", "replace", "rmdir", "listdir", "scandir",
                          "iterdir", "walk", "resolve", "run", "parse_canonical", "review_problems", "chain_problems"):
            with self.subTest(call=forbidden):
                self.assertNotIn(forbidden, called)
        named = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)} | {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        for foreign in ("records", "serialize", "validate", "ReviewStore", "CommittedReviewStore", "fsafe", "gate",
                        "Receipt", "Consumption", "Supersession", "CandidateSnapshot"):
            with self.subTest(name=foreign):
                self.assertNotIn(foreign, named)

    def test_every_code_it_raises_is_a_catalogued_review_code(self) -> None:
        codes = {keyword.value.value for node in ast.walk(self.tree()) if isinstance(node, ast.Call)
                 for keyword in node.keywords
                 if keyword.arg == "code" and isinstance(keyword.value, ast.Constant)}
        self.assertEqual({"review_gate_chain", "review_record_invalid", "review_containment", "review_namespace_invalid"},
                         codes)
        literals = {node.value for node in ast.walk(self.tree()) if isinstance(node, ast.Constant)
                    and isinstance(node.value, str) and re.fullmatch(r"review_p\d_[a-z_]+", node.value)}
        self.assertEqual(set(), literals, "no P4-P7 code literal in the descriptor module")


if __name__ == "__main__":
    unittest.main()
