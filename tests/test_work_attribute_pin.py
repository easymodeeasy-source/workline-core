"""The Work attribute foundation: the pin, the probe, the source predicate, the pinned evaluation.

P3 F3 §7.1.9 class (b), §7.3, §7.7, §7.8, IP-8(b), IP-9, IP-11, IP-12.

Four separable questions, and the tests are grouped by them. Does the invocation
carry the pin, exactly, on top of the complete Unit 1 envelope? Does the running
Git honour it - measured here, on this machine, not inferred from a version
number? Is the pinned source itself free of any rule that would transform bytes?
And does an exact path set, evaluated against THAT source, agree with what the
commit would store?

The decisive one is M-22. The live planning evaluation asks with no ``--source``,
so it answers about the working tree, and a working tree can be changed by the
executor whose output is being judged. Every pinned test here is written so that
a regression to the working-tree source would fail it.

Real Git is driven throughout, in disposable repositories, because every hazard
these tests are about is Git's own behaviour rather than this code's arithmetic.
This is Unit 3 alone: the primitives exist and nothing dispatches to them.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from helpers import WorklineTestCase, git
from workline import gitcmd
from workline.errors import StopError
from workline.review import attributes, hermetic, paths as review_paths
from workline.store import ProjectStore

CANONICAL_LINE = ".workline/review/** !text eol=lf -filter -ident -working-tree-encoding\n"
OID = "0123456789abcdef0123456789abcdef01234567"
OID_256 = "0123456789abcdef" * 4


def clean_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}


class AttributeCase(WorklineTestCase):
    """A Project with an entered hermetic authority and helpers to build exact bases."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        git(self.store.root, "config", "user.name", "Real Person")
        git(self.store.root, "config", "user.email", "real@proj")
        self.hermetic = hermetic.enter(self.store)

    def write(self, relative: str, text: str) -> None:
        path = self.store.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def commit(self, message: str) -> str:
        git(self.store.root, "add", "-A")
        git(self.store.root, "commit", "-m", message, "--no-verify")
        return git(self.store.root, "rev-parse", "HEAD").strip()

    def base_with(self, *sources: tuple[str, str], ordinary: str = "a.txt") -> str:
        """A commit whose attribute sources are exactly ``sources``, plus one ordinary file."""
        for relative, text in sources:
            self.write(relative, text)
        self.write(ordinary, "x\n")
        return self.commit("base")

    def canonical_base(self, *extra: str) -> str:
        return self.base_with((".gitattributes", CANONICAL_LINE + "".join(extra)))

    def refusal(self, call, code: str = "review_git_transform") -> StopError:
        with self.assertRaises(StopError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        return caught.exception


# --------------------------------------------------------------------------- the declared floor


class GitFloorTests(unittest.TestCase):
    """IP-11: `rules/git` gains one threshold, and the two P2 ones do not move."""

    def test_the_work_attribute_floor_is_exactly_two_forty_three(self) -> None:
        self.assertEqual(gitcmd.P3_WORK_ATTR_PIN_GIT_MIN, (2, 43, 0))

    def test_the_two_planning_thresholds_are_unchanged(self) -> None:
        self.assertEqual(gitcmd.P2_REVIEW_GIT_MIN, (2, 40, 0))
        self.assertEqual(gitcmd.P2_PUBLICATION_GIT_MIN, (2, 31, 0))

    def test_the_three_thresholds_are_independent(self) -> None:
        """A Work floor is not derived from a planning one, and none is merged into another."""
        self.assertNotEqual(gitcmd.P3_WORK_ATTR_PIN_GIT_MIN, gitcmd.P2_REVIEW_GIT_MIN)
        self.assertNotEqual(gitcmd.P3_WORK_ATTR_PIN_GIT_MIN, gitcmd.P2_PUBLICATION_GIT_MIN)
        self.assertGreater(gitcmd.P3_WORK_ATTR_PIN_GIT_MIN, gitcmd.P2_REVIEW_GIT_MIN)

    def test_an_unknown_version_meets_the_work_floor_no_more_than_any_other(self) -> None:
        self.assertFalse(gitcmd.version_meets(None, gitcmd.P3_WORK_ATTR_PIN_GIT_MIN))
        self.assertFalse(gitcmd.version_meets((2, 42, 9), gitcmd.P3_WORK_ATTR_PIN_GIT_MIN))
        self.assertTrue(gitcmd.version_meets((2, 43, 0), gitcmd.P3_WORK_ATTR_PIN_GIT_MIN))


# --------------------------------------------------------------------------- the pin argument


class PinArgumentTests(AttributeCase):
    """IP-8(b): the attribute-resolving form is the class B one plus exactly two settings."""

    def settings(self, arguments: tuple[str, ...]) -> dict[str, str]:
        return dict(
            argument.split("=", 1)
            for position, argument in enumerate(arguments)
            if position > 0 and arguments[position - 1] == "-c"
        )

    def test_it_composes_from_the_class_b_arguments_rather_than_rebuilding_them(self) -> None:
        plain = self.hermetic.configuration_arguments()
        pinned = self.hermetic.attribute_configuration_arguments(OID)
        self.assertEqual(pinned[: len(plain)], plain)
        self.assertEqual(len(pinned), len(plain) + 4)

    def test_it_adds_the_pin_and_the_empty_attributes_file_and_nothing_else(self) -> None:
        added = set(self.settings(self.hermetic.attribute_configuration_arguments(OID))) - set(
            self.settings(self.hermetic.configuration_arguments())
        )
        self.assertEqual(added, {"attr.tree", "core.attributesFile"})

    def test_every_unit_one_control_is_still_carried(self) -> None:
        settings = self.settings(self.hermetic.attribute_configuration_arguments(OID))
        for key, value in hermetic.CLASS_B_CONFIGURATION:
            with self.subTest(setting=key):
                self.assertEqual(settings.get(key), value)
        self.assertIn("core.hooksPath", settings)

    def test_the_attributes_file_is_the_proven_empty_workline_file(self) -> None:
        named = self.settings(self.hermetic.attribute_configuration_arguments(OID))["core.attributesFile"]
        self.assertEqual(Path(named), (self.store.root / review_paths.RUNTIME_NO_CONFIG_FILE).resolve())
        self.assertTrue(os.path.isfile(named))
        self.assertEqual(os.path.getsize(named), 0)

    def test_the_attributes_file_is_reproven_on_every_use(self) -> None:
        """Content appearing there would become an attribute source of this very invocation."""
        named = self.store.root / review_paths.RUNTIME_NO_CONFIG_FILE
        named.write_text("*.txt text\n", encoding="utf-8", newline="\n")
        self.refusal(lambda: self.hermetic.attribute_configuration_arguments(OID), "review_no_config_file_invalid")

    def test_the_hooks_directory_is_still_reproven(self) -> None:
        (self.store.root / review_paths.RUNTIME_NO_HOOKS_DIR / "pre-commit").write_text("#!/bin/sh\n")
        self.refusal(lambda: self.hermetic.attribute_configuration_arguments(OID), "review_hooks_path_invalid")

    def test_both_object_formats_are_accepted(self) -> None:
        for source in (OID, OID_256):
            with self.subTest(width=len(source)):
                settings = self.settings(self.hermetic.attribute_configuration_arguments(source))
                self.assertEqual(settings["attr.tree"], source)

    def test_a_revision_expression_is_refused_before_git_is_asked(self) -> None:
        """A pin whose identity Git resolves at use time is not a pin."""
        for source in ("HEAD", "main", "refs/heads/main", OID[:12], OID.upper(), OID + "0", OID[:39],
                       f"{OID}^", f"{OID}^{{commit}}", "", "HEAD~1"):
            with self.subTest(source=source):
                self.refusal(lambda source=source: self.hermetic.attribute_configuration_arguments(source))


# --------------------------------------------------------------------------- the actual invocation


class PinnedInvocationTests(AttributeCase):
    """What the pinned evaluation actually runs, captured rather than declared."""

    def captured(self, basis: str, relatives: list[str]):
        seen: list[tuple[tuple[str, ...], dict]] = []
        real = gitcmd.run_git_bytes

        def recording(repo, *args, **kwargs):
            seen.append((args, dict(kwargs)))
            return real(repo, *args, **kwargs)

        with mock.patch.object(gitcmd, "run_git_bytes", recording):
            attributes.require_pinned_path_evaluation(self.store, self.hermetic, basis, relatives)
        found = [call for call in seen if "check-attr" in call[0]]
        self.assertTrue(found)
        return found[-1]

    def settings(self, arguments: tuple[str, ...]) -> dict[str, str]:
        return dict(
            argument.split("=", 1)
            for position, argument in enumerate(arguments)
            if position > 0 and arguments[position - 1] == "-c"
        )

    def test_the_exact_six_class_b_variables_and_nothing_else(self) -> None:
        base = self.canonical_base()
        _, kwargs = self.captured(base, ["a.txt"])
        names = {name for name in kwargs["env"] if name.upper().startswith("GIT_")}
        self.assertEqual(names, set(hermetic.CLASS_B_ALLOWLIST))
        self.assertEqual(len(hermetic.CLASS_B_ALLOWLIST), 6)

    def test_the_attribute_and_object_semantics_variables_are_on_the_invocation(self) -> None:
        base = self.canonical_base()
        _, kwargs = self.captured(base, ["a.txt"])
        for name in ("GIT_ATTR_NOSYSTEM", "GIT_CONFIG_NOSYSTEM", "GIT_NO_LAZY_FETCH",
                     "GIT_NO_REPLACE_OBJECTS", "GIT_LITERAL_PATHSPECS"):
            with self.subTest(variable=name):
                self.assertEqual(kwargs["env"][name], "1")
        self.assertEqual(os.path.getsize(kwargs["env"]["GIT_CONFIG_GLOBAL"]), 0)

    def test_the_pin_and_the_source_name_the_same_exact_basis(self) -> None:
        """The source the answer came from is mechanically the source the commit runs with."""
        base = self.canonical_base()
        args, _ = self.captured(base, ["a.txt"])
        self.assertEqual(self.settings(args)["attr.tree"], base)
        self.assertIn(f"--source={base}", args)

    def test_every_frozen_control_including_the_line_endings_is_carried(self) -> None:
        """IP-10 / M-23: core.autocrlf and core.eol are configuration the pin does not reach."""
        base = self.canonical_base()
        args, _ = self.captured(base, ["a.txt"])
        settings = self.settings(args)
        self.assertEqual(settings["core.autocrlf"], "false")
        self.assertEqual(settings["core.eol"], "lf")
        self.assertEqual(settings["core.fsmonitor"], "false")
        self.assertEqual(settings["commit.gpgSign"], "false")
        self.assertEqual(settings["gc.auto"], "0")
        self.assertEqual(settings["maintenance.auto"], "false")
        self.assertEqual(os.path.getsize(settings["core.attributesFile"]), 0)

    def test_no_identity_no_date_and_no_index_file(self) -> None:
        """An evaluation writes no commit and touches no index."""
        base = self.canonical_base()
        _, kwargs = self.captured(base, ["a.txt"])
        for name in (*hermetic.CLASS_B_IDENTITY_VARIABLES, "GIT_INDEX_FILE"):
            with self.subTest(variable=name):
                self.assertNotIn(name, kwargs["env"])

    def test_the_complete_material_set_is_asked_for(self) -> None:
        """M-23 / M-24 / M-25: not the old planning subset - text and eol bite on their own."""
        base = self.canonical_base()
        args, _ = self.captured(base, ["a.txt"])
        for name in ("text", "eol", "filter", "ident", "working-tree-encoding"):
            with self.subTest(attribute=name):
                self.assertIn(name, args)


class SystemAndGlobalNeutralizationTests(AttributeCase):
    """M-21: the sources outside the repository are proven inactive, not assumed to be."""

    def hostile_home(self) -> Path:
        home = self.new_dir("hostile-home")
        (home / "hostile-attributes").write_text("*.txt text\n", encoding="utf-8", newline="\n")
        (home / ".gitconfig").write_text(
            f"[core]\n\tattributesFile = {(home / 'hostile-attributes').as_posix()}\n",
            encoding="utf-8", newline="\n",
        )
        return home

    def test_a_hostile_global_attributes_file_is_active_without_the_envelope(self) -> None:
        """The control: this source really would reach the path if nothing neutralized it."""
        self.canonical_base()
        home = self.hostile_home()
        environment = {**clean_env(), "HOME": str(home), "USERPROFILE": str(home)}
        printed = subprocess.run(
            ["git", "-C", str(self.store.root), "check-attr", "text", "--", "a.txt"],
            capture_output=True, text=True, env=environment,
        ).stdout.strip()
        self.assertTrue(printed.endswith("set"), f"the hostile source should reach the path, got {printed!r}")

    def test_the_same_hostile_source_is_not_active_under_the_pinned_evaluation(self) -> None:
        base = self.canonical_base()
        home = self.hostile_home()
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            attributes.require_pinned_path_evaluation(self.store, self.hermetic, base, ["a.txt"])

    def test_the_neutralization_is_visible_on_the_invocation_itself(self) -> None:
        base = self.canonical_base()
        seen: list[dict] = []
        real = gitcmd.run_git_bytes

        def recording(repo, *args, **kwargs):
            if "check-attr" in args:
                seen.append({"args": args, "env": dict(kwargs.get("env") or {})})
            return real(repo, *args, **kwargs)

        with mock.patch.object(gitcmd, "run_git_bytes", recording):
            attributes.require_pinned_path_evaluation(self.store, self.hermetic, base, ["a.txt"])
        env, args = seen[-1]["env"], seen[-1]["args"]
        self.assertEqual(env["GIT_ATTR_NOSYSTEM"], "1")
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(os.path.getsize(env["GIT_CONFIG_GLOBAL"]), 0)
        named = [args[i + 1] for i, a in enumerate(args) if a == "-c" and args[i + 1].startswith("core.attributesFile=")]
        self.assertEqual(len(named), 1)
        self.assertEqual(os.path.getsize(named[0].split("=", 1)[1]), 0)


# --------------------------------------------------------------------------- the capability probe


class CapabilityProbeTests(AttributeCase):
    """§7.7.2 B / IP-11: the running Git is measured, not inferred from a version number."""

    def test_the_probe_passes_on_this_git_and_says_what_it_measured(self) -> None:
        measured = attributes.require_attribute_pin_capability(self.store, self.hermetic)
        self.assertEqual(measured.pinned, measured.raw)
        self.assertTrue(gitcmd.full_commit_id(measured.basis))

    def test_the_unpinned_control_stages_a_different_object(self) -> None:
        """The probe is testing something real: without the pin the working-tree rule applies."""
        measured = attributes.probe_attribute_pin(self.store, self.hermetic)
        if measured.control is None:
            self.skipTest("the unpinned control could not be staged on this Git")
        self.assertNotEqual(measured.control, measured.pinned)
        self.assertNotEqual(measured.control, measured.raw)

    def test_the_probe_uses_no_filter_program(self) -> None:
        """§7.7.2 B: the transform need only be detectable, so the probe has no external effect."""
        self.assertNotIn(b"filter", attributes.PROBE_RULE)
        self.assertEqual(attributes.PROBE_RULE, b"probe.txt text\n")
        self.assertIn(b"\r\n", attributes.PROBE_BYTES)

    def test_the_project_index_is_untouched(self) -> None:
        """`git add` is the mechanism under test, in a scratch repository, never the Work primitive."""
        index = self.store.root / ".git" / "index"
        before = index.read_bytes() if index.exists() else None
        attributes.require_attribute_pin_capability(self.store, self.hermetic)
        after = index.read_bytes() if index.exists() else None
        self.assertEqual(before, after)

    def test_no_project_ref_head_or_tracked_path_moves(self) -> None:
        self.canonical_base()
        head = git(self.store.root, "rev-parse", "HEAD").strip()
        refs = git(self.store.root, "show-ref")
        status = git(self.store.root, "status", "--porcelain")
        attributes.require_attribute_pin_capability(self.store, self.hermetic)
        self.assertEqual(git(self.store.root, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(git(self.store.root, "show-ref"), refs)
        self.assertEqual(git(self.store.root, "status", "--porcelain"), status)

    def test_the_scratch_repository_is_removed(self) -> None:
        attributes.require_attribute_pin_capability(self.store, self.hermetic)
        probe_root = self.store.root / review_paths.RUNTIME_ATTR_PROBE_DIR
        self.assertTrue(not probe_root.exists() or not list(probe_root.iterdir()))

    def test_the_probe_lives_under_the_runtime_area(self) -> None:
        self.assertTrue(review_paths.RUNTIME_ATTR_PROBE_DIR.startswith(".workline/runtime/"))

    def test_a_colliding_scratch_name_is_refused(self) -> None:
        with mock.patch.object(attributes.secrets, "token_hex", return_value="fixed"):
            (self.store.root / review_paths.RUNTIME_ATTR_PROBE_DIR / "fixed").mkdir(parents=True)
            self.refusal(lambda: attributes.probe_attribute_pin(self.store, self.hermetic),
                         "review_git_unsupported")

    def test_an_unknown_git_version_refuses_without_probing(self) -> None:
        with mock.patch.object(gitcmd, "running_git_version", return_value=None):
            with mock.patch.object(attributes, "probe_attribute_pin") as never:
                self.refusal(lambda: attributes.require_attribute_pin_capability(self.store, self.hermetic),
                             "review_git_unsupported")
                never.assert_not_called()

    def test_a_git_below_the_floor_refuses_without_probing(self) -> None:
        for version in ((2, 42, 9), (2, 40, 0), (1, 9, 0)):
            with self.subTest(version=version):
                with mock.patch.object(gitcmd, "running_git_version", return_value=version):
                    with mock.patch.object(attributes, "probe_attribute_pin") as never:
                        self.refusal(
                            lambda: attributes.require_attribute_pin_capability(self.store, self.hermetic),
                            "review_git_unsupported",
                        )
                        never.assert_not_called()

    def test_the_floor_version_itself_is_eligible_for_the_probe(self) -> None:
        with mock.patch.object(gitcmd, "running_git_version", return_value=(2, 43, 0)):
            with mock.patch.object(attributes, "probe_attribute_pin") as probed:
                attributes.require_attribute_pin_capability(self.store, self.hermetic)
                probed.assert_called_once()

    def test_a_floor_pass_never_substitutes_for_the_probe(self) -> None:
        """A version far above the floor with a Git that does not honour the pin still refuses."""
        staged = [None]

        def wrong(repo, hermetic_git, arguments):
            staged[0] = "wrong"
            return gitcmd.zero_object_id(OID)

        with mock.patch.object(gitcmd, "running_git_version", return_value=(2, 99, 0)):
            with mock.patch.object(attributes, "_staged_object", wrong):
                error = self.refusal(
                    lambda: attributes.require_attribute_pin_capability(self.store, self.hermetic),
                    "review_git_unsupported",
                )
        self.assertIn("does not honour the pin", str(error))
        self.assertEqual(staged[0], "wrong")

    def test_a_probe_that_cannot_be_answered_refuses(self) -> None:
        with mock.patch.object(attributes, "_staged_object", side_effect=OSError("no")):
            with self.assertRaises(OSError):
                attributes.probe_attribute_pin(self.store, self.hermetic)
        probe_root = self.store.root / review_paths.RUNTIME_ATTR_PROBE_DIR
        self.assertTrue(not probe_root.exists() or not list(probe_root.iterdir()),
                        "a failed probe still removes its scratch")

    def test_nothing_remembers_that_the_probe_passed(self) -> None:
        """IP-11: every operation proves the running Git before its first pinned commit."""
        attributes.require_attribute_pin_capability(self.store, self.hermetic)
        with mock.patch.object(gitcmd, "running_git_version", return_value=(2, 42, 0)):
            self.refusal(lambda: attributes.require_attribute_pin_capability(self.store, self.hermetic),
                         "review_git_unsupported")


class ProbeInvocationTests(AttributeCase):
    """§7.7: what the probe's staging command actually carries."""

    def captured(self):
        seen: list[tuple[str, tuple[str, ...], dict]] = []
        real = gitcmd.run_git_bytes

        def recording(repo, *args, **kwargs):
            seen.append((str(repo), args, dict(kwargs)))
            return real(repo, *args, **kwargs)

        with mock.patch.object(gitcmd, "run_git_bytes", recording):
            attributes.probe_attribute_pin(self.store, self.hermetic)
        adds = [call for call in seen if "add" in call[1]]
        self.assertEqual(len(adds), 2, "one unpinned control and one pinned measurement")
        return adds

    def test_the_staging_runs_in_the_scratch_repository_not_the_project(self) -> None:
        for repo, _, _ in self.captured():
            with self.subTest(repo=repo):
                self.assertIn(review_paths.RUNTIME_ATTR_PROBE_DIR.replace("/", os.sep), repo)
                self.assertNotEqual(Path(repo), self.store.root)

    def test_only_the_probe_path_is_ever_staged(self) -> None:
        for _, args, _ in self.captured():
            self.assertEqual(args[-2:], ("--", attributes.PROBE_PATH))

    def test_the_pinned_staging_carries_the_complete_envelope(self) -> None:
        _, (_, pinned_args, pinned_kwargs) = self.captured()
        settings = dict(
            argument.split("=", 1)
            for position, argument in enumerate(pinned_args)
            if position > 0 and pinned_args[position - 1] == "-c"
        )
        self.assertTrue(gitcmd.full_commit_id(settings["attr.tree"]))
        self.assertEqual(os.path.getsize(settings["core.attributesFile"]), 0)
        self.assertEqual(settings["core.autocrlf"], "false")
        self.assertEqual(settings["core.eol"], "lf")
        self.assertEqual(os.listdir(settings["core.hooksPath"]), [])
        env = pinned_kwargs["env"]
        for name in ("GIT_ATTR_NOSYSTEM", "GIT_CONFIG_NOSYSTEM", "GIT_NO_REPLACE_OBJECTS", "GIT_NO_LAZY_FETCH"):
            with self.subTest(variable=name):
                self.assertEqual(env[name], "1")
        self.assertNotIn("GIT_INDEX_FILE", env)

    def test_the_control_differs_from_the_pinned_run_only_in_the_pin(self) -> None:
        (_, control_args, _), (_, pinned_args, _) = self.captured()
        self.assertEqual(attributes._without_pin(pinned_args), control_args)


# --------------------------------------------------------------------------- the source parser


class SourceParserTests(unittest.TestCase):
    """IP-12: a parser over the source BYTES, and anything it cannot classify is a refusal."""

    def parse(self, data: bytes, directory: str = ""):
        return attributes.parse_source(data, "source", directory)

    def refuse(self, data: bytes) -> StopError:
        with self.assertRaises(StopError) as caught:
            self.parse(data)
        self.assertEqual(caught.exception.code, "review_git_transform")
        return caught.exception

    def material(self, data: bytes) -> tuple[str, ...]:
        return self.parse(data)[0].material

    def test_blank_lines_and_comments_contribute_nothing(self) -> None:
        self.assertEqual(self.parse(b"\n\n  \n# a comment\n\t# indented\n"), [])

    def test_an_ordinary_rule_is_parsed(self) -> None:
        rule = self.parse(b"*.bin -filter\n")[0]
        self.assertEqual(rule.pattern, "*.bin")
        self.assertEqual(rule.meaning, (("filter", "unset"),))

    def test_every_canonical_material_assignment_is_material(self) -> None:
        for line, name in (
            (b"*.txt text\n", "text"),
            (b"*.txt text=auto\n", "text"),
            (b"*.txt eol=lf\n", "eol"),
            (b"*.txt eol=crlf\n", "eol"),
            (b"*.bin filter=lfs\n", "filter"),
            (b"*.txt ident\n", "ident"),
            (b"*.txt working-tree-encoding=UTF-16\n", "working-tree-encoding"),
        ):
            with self.subTest(line=line):
                self.assertEqual(self.material(line), (name,))

    def test_the_crlf_alias_is_expanded_before_it_is_judged(self) -> None:
        """M-25: `generated/** crlf` is the escape a five-name set misses."""
        self.assertEqual(self.parse(b"generated/** crlf\n")[0].meaning, (("text", "set"),))
        self.assertEqual(self.material(b"generated/** crlf\n"), ("text",))

    def test_crlf_input_means_eol_lf_and_is_material(self) -> None:
        self.assertEqual(self.parse(b"**/*.txt crlf=input\n")[0].meaning, (("eol", "=lf"),))
        self.assertEqual(self.material(b"**/*.txt crlf=input\n"), ("eol",))

    def test_explicit_unsets_are_safe(self) -> None:
        for line in (b"*.txt -text\n", b"*.txt -crlf\n", b"*.bin -filter\n", b"*.txt -ident\n",
                     b"*.txt !text\n", b"*.txt -working-tree-encoding\n"):
            with self.subTest(line=line):
                self.assertEqual(self.material(line), ())

    def test_minus_crlf_is_minus_text(self) -> None:
        self.assertEqual(self.parse(b"*.txt -crlf\n")[0].meaning, (("text", "unset"),))

    def test_the_builtin_binary_macro_is_safe(self) -> None:
        """M-25: measured RAW, because its expansion only UNSETS text."""
        rule = self.parse(b"*.bin binary\n")[0]
        self.assertIn(("text", "unset"), rule.meaning)
        self.assertEqual(rule.material, ())

    def test_only_the_plain_builtin_binary_is_classified(self) -> None:
        for line in (b"*.bin -binary\n", b"*.bin !binary\n", b"*.bin binary=yes\n"):
            with self.subTest(line=line):
                self.refuse(line)

    def test_a_user_defined_macro_is_refused_wherever_it_appears(self) -> None:
        for data in (b"[attr]mine text filter=x\n", b"*.txt -text\n[attr]mine diff\n",
                     b"  [attr]mine -text\n"):
            with self.subTest(data=data):
                self.assertIn("macro", str(self.refuse(data)))

    def test_a_filter_named_unset_is_a_set_not_an_unset(self) -> None:
        """`filter=unset` selects a driver literally named unset; it is not `-filter`."""
        self.assertEqual(self.material(b"*.bin filter=unset\n"), ("filter",))
        self.assertEqual(self.material(b"*.bin -filter\n"), ())

    def test_a_syntactically_understood_non_material_attribute_is_not_material(self) -> None:
        for line in (b"*.txt diff\n", b"*.txt -merge\n", b"*.c diff=cpp\n", b"*.txt export-ignore\n"):
            with self.subTest(line=line):
                self.assertEqual(self.material(line), ())

    def test_a_nul_byte_refuses_because_git_reads_only_part_of_the_file(self) -> None:
        self.assertIn("NUL", str(self.refuse(b"*.txt -text\n\0*.txt text\n")))

    def test_a_carriage_return_refuses_rather_than_being_guessed_at(self) -> None:
        self.assertIn("carriage return", str(self.refuse(b"*.txt -text\r\n")))

    def test_bytes_that_are_not_utf8_refuse(self) -> None:
        self.refuse(b"*.txt \xff\xfe -text\n")

    def test_a_quoted_or_escaped_pattern_refuses(self) -> None:
        for data in (b'"a b.txt" -text\n', b"a\\ b.txt -text\n", b"a\\*.txt -text\n"):
            with self.subTest(data=data):
                self.refuse(data)

    def test_a_pattern_with_no_attribute_refuses(self) -> None:
        self.refuse(b"*.txt\n")

    def test_a_negative_pattern_refuses(self) -> None:
        """Git forbids one in an attributes file, so what it would mean here is not guessed at."""
        self.refuse(b"!*.txt -text\n")

    def test_an_anchored_pattern_is_ordinary_and_parsed(self) -> None:
        self.assertEqual(self.parse(b"/build/** -text\n")[0].pattern, "/build/**")
        self.assertEqual(self.material(b"/build/** text\n"), ("text",))

    def test_an_unclassifiable_token_refuses(self) -> None:
        for data in (b"*.txt =value\n", b"*.txt -\n", b"*.txt _leading\n", b"*.txt a b/c\n"):
            with self.subTest(data=data):
                self.refuse(data)

    def test_no_line_is_partially_understood(self) -> None:
        """A safe token before an unclassified one does not make the line safe."""
        self.refuse(b"*.txt -text [attr]x\n")
        self.refuse(b"*.txt -filter =nonsense\n")


# --------------------------------------------------------------------------- the sources, enumerated


class SourceEnumerationTests(AttributeCase):
    """§7.8.3: every .gitattributes at every depth, found by enumerating the tree."""

    def require(self, basis: str) -> None:
        attributes.require_work_attribute_source(self.store, self.hermetic, basis)

    def test_a_canonical_only_base_is_accepted(self) -> None:
        self.require(self.canonical_base())

    def test_a_material_rule_in_the_root_source_refuses(self) -> None:
        self.refusal(lambda: self.require(self.canonical_base("*.txt text\n")))

    def test_a_material_rule_in_a_nested_source_is_found(self) -> None:
        base = self.base_with((".gitattributes", CANONICAL_LINE), ("a/.gitattributes", "*.bin crlf\n"))
        self.assertIn("a/.gitattributes", str(self.refusal(lambda: self.require(base))))

    def test_a_material_rule_deep_in_the_tree_is_found(self) -> None:
        base = self.base_with((".gitattributes", CANONICAL_LINE),
                              ("a/b/c/.gitattributes", "*.txt working-tree-encoding=UTF-16\n"))
        self.assertIn("a/b/c/.gitattributes", str(self.refusal(lambda: self.require(base))))

    def test_several_sources_are_all_parsed_and_the_last_unsafe_one_still_refuses(self) -> None:
        base = self.base_with(
            (".gitattributes", CANONICAL_LINE + "*.bin -filter\n"),
            ("a/.gitattributes", "*.md -text\n"),
            ("a/b/.gitattributes", "*.log ident\n"),
        )
        self.assertIn("a/b/.gitattributes", str(self.refusal(lambda: self.require(base))))

    def test_safe_explicit_unsets_in_nested_sources_are_accepted(self) -> None:
        self.require(self.base_with(
            (".gitattributes", CANONICAL_LINE),
            ("a/.gitattributes", "*.md -text -filter\n"),
            ("a/b/.gitattributes", "*.bin binary\n"),
        ))

    def test_a_base_with_no_root_source_refuses_for_the_missing_canonical_rule(self) -> None:
        base = self.base_with(("a/.gitattributes", "*.md -text\n"))
        self.assertIn("canonical Review rule", str(self.refusal(lambda: self.require(base))))

    def test_an_unparseable_nested_source_refuses(self) -> None:
        """A real committed source whose syntax this version does not classify: not knowing is not a yes."""
        base = self.base_with((".gitattributes", CANONICAL_LINE), ("a/.gitattributes", '"a b.txt" -text\n'))
        self.assertIn("a/.gitattributes", str(self.refusal(lambda: self.require(base))))

    def test_the_enumeration_reads_the_basis_not_the_working_tree(self) -> None:
        """M-22, at the source level: a working-tree source the basis does not hold is not read."""
        base = self.canonical_base()
        self.write("a/.gitattributes", "*.txt text\n")
        self.require(base)

    def test_a_material_rule_added_after_the_basis_is_found_in_the_later_basis(self) -> None:
        self.canonical_base()
        self.write("a/.gitattributes", "*.txt text\n")
        later = self.commit("drifted")
        self.refusal(lambda: self.require(later))

    def failing(self, verb: str):
        """Make the class B reader's ``verb`` invocation fail, and nothing else.

        Patched at :meth:`HermeticGit.run_bytes`, which is the seam every source
        read now goes through, so what is being tested is Git refusing rather
        than a helper being mocked.
        """
        real = hermetic.HermeticGit.run_bytes

        def refusing(instance, *args, **kwargs):
            if verb in args:
                return gitcmd.GitBytes(returncode=128, stdout=b"", stderr=b"refused for the test")
            return real(instance, *args, **kwargs)

        return mock.patch.object(hermetic.HermeticGit, "run_bytes", refusing)

    def test_a_gitattributes_that_is_not_a_regular_blob_refuses(self) -> None:
        base = self.canonical_base()
        self.assertTrue(any(entry.path == ".gitattributes"
                            for entry in attributes._work_tree_entries(self.hermetic, base)))
        with mock.patch.object(attributes, "_work_tree_entries", return_value=[
            gitcmd.TreeEntry(mode="120000", type="blob", oid=OID, path=".gitattributes")
        ]):
            self.assertIn("120000", str(self.refusal(lambda: self.require(base))))

    def test_an_unreadable_source_blob_refuses(self) -> None:
        base = self.canonical_base()
        with self.failing("cat-file"):
            self.assertIn("cannot read", str(self.refusal(lambda: self.require(base))))

    def test_a_tree_git_cannot_enumerate_refuses(self) -> None:
        base = self.canonical_base()
        with self.failing("ls-tree"):
            self.assertIn("enumerate", str(self.refusal(lambda: self.require(base))))

    def test_a_listing_record_that_cannot_be_classified_refuses(self) -> None:
        """The byte parser accepts `<mode> <type> <full-oid>\\t<path>` and nothing else."""
        base = self.canonical_base()
        real = hermetic.HermeticGit.run_bytes
        for malformed in (b"100644 blob\tonly-two-fields\0",
                          b"100644 blob " + OID.encode() + b"no-tab\0",
                          b"100644 blob nothexoid\t.gitattributes\0",
                          b"100644 blob " + OID.encode() + b"\t\0"):
            with self.subTest(record=malformed[:34]):
                def answering(instance, *args, _m=malformed, **kwargs):
                    if "ls-tree" in args:
                        return gitcmd.GitBytes(returncode=0, stdout=_m, stderr=b"")
                    return real(instance, *args, **kwargs)

                with mock.patch.object(hermetic.HermeticGit, "run_bytes", answering):
                    self.refusal(lambda: self.require(base))


class SourceAuthorityTests(AttributeCase):
    """The source proof reads objects under the Unit 1 class B authority, and under nothing else.

    ``gitcmd.tree_entries`` / ``gitcmd.read_blob`` run with ``env=None`` and no
    class B configuration, so they see Git's ordinary ``refs/replace`` view and
    whatever ``GIT_*`` the parent process exported; they also memoize by
    ``(kind, repo, oid)`` with no environment in the key, so one answer taken
    under a poisoned view outlives the poison. Measured on the stopped
    candidate, both of those turned an unsafe basis into a PASS. These tests
    hold the repaired reader to the class B envelope on the ACTUAL invocations.
    """

    def require(self, basis: str) -> None:
        attributes.require_work_attribute_source(self.store, self.hermetic, basis)

    def plain(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.store.root), *args],
                              capture_output=True, text=True, env=clean_env())

    def two_bases(self) -> tuple[str, str]:
        """An UNSAFE basis (canonical + a material rule) and a SAFE one (canonical only)."""
        self.write(".gitattributes", CANONICAL_LINE + "*.txt text\n")
        self.write("a.txt", "x\n")
        unsafe = self.commit("unsafe")
        self.write(".gitattributes", CANONICAL_LINE)
        safe = self.commit("safe")
        return unsafe, safe

    def tearDown(self) -> None:
        # the generic cache is process-wide; no test may leak an answer into another
        gitcmd.forget_object_answers()
        super().tearDown()

    # ---- refs/replace ---------------------------------------------------

    def test_a_replacement_cannot_make_an_unsafe_basis_pass(self) -> None:
        """M-58/M-49: an oid means the object it names, never a refs/replace view."""
        unsafe, safe = self.two_bases()
        gitcmd.forget_object_answers()
        self.refusal(lambda: self.require(unsafe))
        self.plain("replace", "-f", unsafe, safe)
        self.assertTrue(self.plain("rev-parse", f"refs/replace/{unsafe}").returncode == 0,
                        "the replacement ref must really be installed")
        gitcmd.forget_object_answers()
        self.assertIn("text", str(self.refusal(lambda: self.require(unsafe))))

    def test_a_replacement_cannot_make_a_safe_basis_refuse(self) -> None:
        """The converse: the replacement is invisible in both directions."""
        unsafe, safe = self.two_bases()
        self.plain("replace", "-f", safe, unsafe)
        gitcmd.forget_object_answers()
        self.require(safe)

    def test_a_poisoned_generic_object_cache_cannot_reach_the_proof(self) -> None:
        """A false answer taken under the ordinary view must not survive into this proof."""
        unsafe, safe = self.two_bases()
        self.plain("replace", "-f", unsafe, safe)
        gitcmd.forget_object_answers()
        # seed the generic cache under the ordinary, replacement-honouring view
        seeded = gitcmd.tree_entries(self.store.root, unsafe, recursive=True)
        self.assertIsNotNone(seeded)
        for entry in seeded:
            if entry.path == ".gitattributes":
                cached = gitcmd.read_blob(self.store.root, entry.oid)
                self.assertNotIn(b"*.txt text", cached, "the seeded answer is the replacement's, as intended")
        # the proof must still read the ORIGINAL object, cache or no cache
        self.refusal(lambda: self.require(unsafe))
        self.plain("replace", "-d", unsafe)
        self.refusal(lambda: self.require(unsafe))

    def test_the_proof_takes_no_answer_from_the_generic_cache(self) -> None:
        """Stated directly: neither generic helper is called while the proof runs."""
        base = self.canonical_base()
        gitcmd.forget_object_answers()
        with mock.patch.object(gitcmd, "tree_entries", side_effect=AssertionError("tree_entries used")):
            with mock.patch.object(gitcmd, "read_blob", side_effect=AssertionError("read_blob used")):
                self.require(base)

    # ---- the inherited environment --------------------------------------

    def test_an_inherited_object_directory_is_stripped(self) -> None:
        """M-61: an exported GIT_OBJECT_DIRECTORY hides the repository's own objects."""
        unsafe, _ = self.two_bases()
        hostile = self.new_dir("hostile-objects")
        control = subprocess.run(
            ["git", "-C", str(self.store.root), "ls-tree", "-r", unsafe],
            capture_output=True, text=True, env={**clean_env(), "GIT_OBJECT_DIRECTORY": str(hostile)},
        )
        self.assertNotEqual(control.returncode, 0, "the hostile directory should really hide the objects")
        with mock.patch.dict(os.environ, {"GIT_OBJECT_DIRECTORY": str(hostile)}):
            gitcmd.forget_object_answers()
            # the strip is in force, so the basis is read and judged on its own content
            self.assertIn("text", str(self.refusal(lambda: self.require(unsafe))))

    def test_an_inherited_alternate_object_directory_is_stripped(self) -> None:
        unsafe, _ = self.two_bases()
        hostile = self.new_dir("hostile-alternates")
        with mock.patch.dict(os.environ, {"GIT_ALTERNATE_OBJECT_DIRECTORIES": str(hostile)}):
            gitcmd.forget_object_answers()
            self.assertIn("text", str(self.refusal(lambda: self.require(unsafe))))

    # ---- the actual invocations ------------------------------------------

    def captured(self, basis: str):
        seen: list[tuple[tuple[str, ...], dict]] = []
        real = gitcmd.run_git_bytes

        def recording(repo, *args, **kwargs):
            seen.append((args, dict(kwargs)))
            return real(repo, *args, **kwargs)

        with mock.patch.object(gitcmd, "run_git_bytes", recording):
            self.require(basis)
        return seen

    def settings(self, arguments: tuple[str, ...]) -> dict[str, str]:
        return dict(
            argument.split("=", 1)
            for position, argument in enumerate(arguments)
            if position > 0 and arguments[position - 1] == "-c"
        )

    def test_every_source_read_is_a_class_b_invocation(self) -> None:
        base = self.canonical_base()
        calls = self.captured(base)
        reads = [call for call in calls if "ls-tree" in call[0] or "cat-file" in call[0]]
        self.assertGreaterEqual(len(reads), 2, "one listing and at least one blob read")
        for args, kwargs in reads:
            with self.subTest(verb=args[:8]):
                names = {name for name in kwargs["env"] if name.upper().startswith("GIT_")}
                self.assertEqual(names, set(hermetic.CLASS_B_ALLOWLIST))
                self.assertEqual(kwargs["env"]["GIT_NO_REPLACE_OBJECTS"], "1")
                self.assertEqual(kwargs["env"]["GIT_NO_LAZY_FETCH"], "1")
                self.assertEqual(os.path.getsize(kwargs["env"]["GIT_CONFIG_GLOBAL"]), 0)
                self.assertNotIn("GIT_INDEX_FILE", kwargs["env"])
                for name in hermetic.CLASS_B_IDENTITY_VARIABLES:
                    self.assertNotIn(name, kwargs["env"])
                settings = self.settings(args)
                for key, value in hermetic.CLASS_B_CONFIGURATION:
                    self.assertEqual(settings.get(key), value)
                self.assertEqual(os.listdir(settings["core.hooksPath"]), [])

    def test_the_listing_is_the_exact_command(self) -> None:
        base = self.canonical_base()
        listings = [args for args, _ in self.captured(base) if "ls-tree" in args]
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0][-5:], ("ls-tree", "-z", "--full-tree", "-r", base))

    def test_no_attribute_pin_is_carried_by_a_raw_object_read(self) -> None:
        """Object reads need exact object semantics, not attribute resolution."""
        base = self.canonical_base()
        for args, _ in self.captured(base):
            if "ls-tree" in args or "cat-file" in args:
                with self.subTest(verb=args[:8]):
                    self.assertNotIn("attr.tree", self.settings(args))

    # ---- the exact basis --------------------------------------------------

    def test_only_an_exact_full_object_id_is_accepted_as_the_basis(self) -> None:
        base = self.canonical_base()
        branch = git(self.store.root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        # every one of these is refused by the identity guard itself; a well-formed 64-hex id is NOT
        # here, because that is a valid basis shape and belongs to the reader (see below)
        for basis in ("HEAD", branch, f"refs/heads/{branch}", base[:12], base.upper(), base + "0",
                      base[:39], f"{base}^", f"{base}^{{commit}}", f"{base}^{{tree}}", "", "HEAD~1"):
            with self.subTest(basis=basis):
                gitcmd.forget_object_answers()
                self.refusal(lambda basis=basis: self.require(basis))

    def test_an_invalid_basis_is_refused_before_git_is_asked(self) -> None:
        self.canonical_base()
        branch = git(self.store.root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        for basis in ("HEAD", branch, "0123456789ab", "", f"{OID}^"):
            with self.subTest(basis=basis):
                with mock.patch.object(gitcmd, "run_git_bytes",
                                       side_effect=AssertionError("Git was asked")) as never:
                    self.refusal(lambda basis=basis: self.require(basis))
                    never.assert_not_called()

    def test_a_full_object_id_of_either_width_reaches_the_reader(self) -> None:
        base = self.canonical_base()
        self.assertEqual(len(base), 40)
        self.require(base)
        # a well-formed 64-hex id this repository does not hold is refused by the READER, not the guard
        self.assertIn("enumerate", str(self.refusal(lambda: self.require(OID_256))))


class InfoAttributesTests(AttributeCase):
    """§7.8.3: the non-tree source the pin does not reach."""

    def info(self) -> Path:
        path = self.store.root / ".git" / "info" / "attributes"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def require(self, basis: str) -> None:
        attributes.require_work_attribute_source(self.store, self.hermetic, basis)

    def test_absent_contributes_no_rule(self) -> None:
        base = self.canonical_base()
        path = self.info()
        if path.exists():
            path.unlink()
        self.require(base)

    def test_a_safe_info_source_is_accepted(self) -> None:
        base = self.canonical_base()
        self.info().write_text("*.bin -filter\n# comment\n", encoding="utf-8", newline="\n")
        self.require(base)

    def test_a_material_info_source_refuses(self) -> None:
        base = self.canonical_base()
        self.info().write_text("*.txt text\n", encoding="utf-8", newline="\n")
        self.assertIn("info/attributes", str(self.refusal(lambda: self.require(base))))

    def test_a_material_alias_in_the_info_source_refuses(self) -> None:
        base = self.canonical_base()
        self.info().write_text("generated/** crlf\n", encoding="utf-8", newline="\n")
        self.refusal(lambda: self.require(base))

    def test_an_unparseable_info_source_refuses(self) -> None:
        base = self.canonical_base()
        self.info().write_bytes(b"*.txt \0 text\n")
        self.refusal(lambda: self.require(base))

    def test_a_second_canonical_rule_in_the_info_source_is_ambiguous(self) -> None:
        base = self.canonical_base()
        self.info().write_text(CANONICAL_LINE, encoding="utf-8", newline="\n")
        self.assertIn("which one governs", str(self.refusal(lambda: self.require(base))))

    def test_a_source_git_cannot_name_refuses(self) -> None:
        base = self.canonical_base()
        with mock.patch.object(hermetic.HermeticGit, "run",
                               return_value=gitcmd.GitResult(returncode=1, stdout="", stderr="no")):
            self.refusal(lambda: self.require(base))


# --------------------------------------------------------------------------- the reserved Review namespace


class CanonicalReviewRuleTests(AttributeCase):
    """§7.8.4: the one place an assignment is permitted, and required."""

    def require(self, basis: str) -> None:
        attributes.require_work_attribute_source(self.store, self.hermetic, basis)

    def test_the_canonical_form_is_accepted_although_eol_lf_is_material(self) -> None:
        """M-26: eol=lf normalizes on check-in, and is required all the same."""
        self.require(self.canonical_base())

    def test_the_canonical_form_is_required_not_merely_tolerated(self) -> None:
        base = self.base_with((".gitattributes", "*.bin -filter\n"))
        self.assertIn("canonical Review rule", str(self.refusal(lambda: self.require(base))))

    def test_every_weakened_form_of_the_review_rule_refuses(self) -> None:
        for line in (
            ".workline/review/** !text -filter -ident -working-tree-encoding\n",
            ".workline/review/** !text eol=crlf -filter -ident -working-tree-encoding\n",
            ".workline/review/** text eol=lf -filter -ident -working-tree-encoding\n",
            ".workline/review/** !text eol=lf filter=lfs -ident -working-tree-encoding\n",
            ".workline/review/** !text eol=lf -filter ident -working-tree-encoding\n",
            ".workline/review/** !text eol=lf -filter -ident working-tree-encoding=UTF-16\n",
            ".workline/review/** !text eol=lf -filter -ident -working-tree-encoding ident\n",
        ):
            with self.subTest(line=line.strip()):
                base = self.base_with((".gitattributes", line))
                self.refusal(lambda: self.require(base))
                git(self.store.root, "reset", "--hard", "HEAD~1")

    def test_a_broader_pattern_that_also_covers_review_paths_is_ordinary(self) -> None:
        for pattern in ("**/*", ".workline/**", "*.yaml", ".workline/review*", "**"):
            with self.subTest(pattern=pattern):
                base = self.base_with((".gitattributes", CANONICAL_LINE + f"{pattern} eol=lf\n"))
                self.refusal(lambda: self.require(base))
                git(self.store.root, "reset", "--hard", "HEAD~1")

    def test_a_canonical_looking_rule_in_a_nested_source_is_not_canonical(self) -> None:
        """From `a/.gitattributes` the same text denotes `a/.workline/review/**`.

        So it is judged by the ordinary rule - its ``eol=lf`` is a material
        assignment to a pattern outside the reserved namespace - and it does not
        satisfy the canonical requirement either.
        """
        base = self.base_with(("a/.gitattributes", CANONICAL_LINE))
        error = self.refusal(lambda: self.require(base))
        self.assertIn("a/.gitattributes", str(error))
        self.assertIn("eol", str(error))

    def test_a_nested_canonical_looking_rule_does_not_satisfy_the_requirement_either(self) -> None:
        base = self.base_with((".gitattributes", CANONICAL_LINE), ("a/.gitattributes", CANONICAL_LINE))
        self.refusal(lambda: self.require(base))

    def test_two_canonical_rules_are_ambiguous(self) -> None:
        base = self.base_with((".gitattributes", CANONICAL_LINE + CANONICAL_LINE))
        self.assertIn("which one governs", str(self.refusal(lambda: self.require(base))))

    def test_a_non_material_rule_inside_the_namespace_does_not_stand_in_for_the_canonical_one(self) -> None:
        base = self.base_with((".gitattributes", ".workline/review/** -filter\n"))
        self.refusal(lambda: self.require(base))

    def test_an_additional_namespace_rule_beside_the_canonical_one_refuses(self) -> None:
        """`.workline/review/** -eol` assigns nothing material and would still leave form L."""
        for extra in (".workline/review/** -eol\n", ".workline/review/gates/** -text\n",
                      ".workline/review/** -diff\n", ".workline/review/** filter=lfs\n"):
            with self.subTest(extra=extra.strip()):
                base = self.base_with((".gitattributes", CANONICAL_LINE + extra))
                found = str(self.refusal(lambda: self.require(base)))
                self.assertIn("Review", found)
                self.assertIn(".workline/review/", found)
                git(self.store.root, "reset", "--hard", "HEAD~1")

    def test_the_canonical_rule_is_matched_by_meaning_not_by_token_order(self) -> None:
        self.require(self.base_with(
            (".gitattributes", ".workline/review/** eol=lf -ident !text -working-tree-encoding -filter\n")
        ))

    def test_an_extra_attribute_on_the_canonical_rule_refuses(self) -> None:
        """Deliberate narrowness: the reserved namespace takes the canonical form and no other."""
        base = self.base_with(
            (".gitattributes", ".workline/review/** !text eol=lf -filter -ident -working-tree-encoding -diff\n")
        )
        self.assertIn("canonical form", str(self.refusal(lambda: self.require(base))))


# --------------------------------------------------------------------------- the pinned evaluation


class PinnedEvaluationTests(AttributeCase):
    """IP-9 / §7.3: an exact path set, against the source the commit will use."""

    def evaluate(self, basis: str, relatives: list[str]) -> None:
        attributes.require_pinned_path_evaluation(self.store, self.hermetic, basis, relatives)

    def test_ordinary_and_review_paths_pass_under_a_safe_base(self) -> None:
        base = self.canonical_base()
        self.evaluate(base, ["a.txt", "a/b/c.bin", ".workline/review/gates/x.yaml"])

    def test_an_empty_path_set_is_answerable(self) -> None:
        self.evaluate(self.canonical_base(), [])

    def test_a_material_rule_in_the_base_refuses_for_an_ordinary_path(self) -> None:
        """M-24: the pin faithfully honours the base, so it cannot rescue one.

        The rule is written for a path that does not exist yet, which is the
        shape §7.8.1 is about: a result path set is not known at entry.
        """
        for line, expected in (("future/** text\n", "text"), ("future/** eol=crlf\n", "eol"),
                               ("future/** working-tree-encoding=UTF-16\n", "working-tree-encoding"),
                               ("future/** filter=lfs\n", "filter"), ("future/** ident\n", "ident")):
            with self.subTest(line=line.strip()):
                base = self.base_with((".gitattributes", CANONICAL_LINE + line))
                found = str(self.refusal(lambda: self.evaluate(base, ["future/x.bin"])))
                self.assertIn(expected, found)
                git(self.store.root, "reset", "--hard", "HEAD~1")

    def test_the_compatibility_aliases_are_invisible_to_a_path_query_and_the_source_catches_them(self) -> None:
        """MEASURED here, and it is why §7.8's predicate is over the SOURCE and not over paths.

        ``crlf`` and ``crlf=input`` change stored bytes (M-25), but they are
        handled in Git's conversion layer rather than its attribute layer, so
        ``check-attr text`` prints ``unspecified`` for a path they govern. A
        path-wise check would pass them. The source parser expands the alias
        before judging, and refuses.
        """
        for line, asked in (("future/** crlf\n", "text"), ("future/** crlf=input\n", "eol")):
            with self.subTest(line=line.strip()):
                base = self.base_with((".gitattributes", CANONICAL_LINE + line))
                printed = gitcmd.check_attributes(
                    self.store.root, ["future/x.bin"], attributes.MATERIAL_ATTRIBUTES,
                    before=self.hermetic.attribute_configuration_arguments(base),
                    options=(f"--source={base}",), env=self.hermetic.environment(),
                )
                self.assertEqual(printed["future/x.bin"][asked], "unspecified",
                                 "the alias should be invisible to the path query")
                self.evaluate(base, ["future/x.bin"])
                self.refusal(lambda: attributes.require_work_attribute_source(self.store, self.hermetic, base))
                git(self.store.root, "reset", "--hard", "HEAD~1")

    def test_a_review_path_prints_exactly_form_l(self) -> None:
        """M-26: the canonical rule is material and is the required state there."""
        base = self.canonical_base()
        printed = gitcmd.check_attributes(
            self.store.root, [".workline/review/gates/x.yaml"], attributes.MATERIAL_ATTRIBUTES,
            before=self.hermetic.attribute_configuration_arguments(base),
            options=(f"--source={base}",), env=self.hermetic.environment(),
        )
        self.assertEqual(printed[".workline/review/gates/x.yaml"], attributes.FORM_L)

    def test_an_ordinary_path_may_not_take_the_review_form(self) -> None:
        """eol=lf outside the namespace is an ordinary material assignment and fails."""
        base = self.base_with((".gitattributes", CANONICAL_LINE + "docs/** eol=lf\n"))
        self.refusal(lambda: self.evaluate(base, ["docs/x.md"]))

    def test_a_review_path_whose_base_lacks_the_rule_fails_the_review_surface(self) -> None:
        base = self.base_with((".gitattributes", "*.bin -filter\n"))
        error = self.refusal(lambda: self.evaluate(base, [".workline/review/gates/x.yaml"]))
        self.assertIn("canonical form", str(error))

    def test_the_event_log_is_an_ordinary_path_for_attribute_purposes(self) -> None:
        base = self.canonical_base()
        self.evaluate(base, [".workline/events/events.jsonl"])
        material = self.base_with((".gitattributes", CANONICAL_LINE + ".workline/events/** text\n"))
        self.refusal(lambda: self.evaluate(material, [".workline/events/events.jsonl"]))

    def test_a_working_tree_rule_added_after_the_base_is_not_observed(self) -> None:
        """M-22, decisive: the evaluation and the storage cannot disagree."""
        base = self.canonical_base()
        self.write(".gitattributes", CANONICAL_LINE + "a.txt text\n")
        self.evaluate(base, ["a.txt"])
        unpinned = subprocess.run(
            ["git", "-C", str(self.store.root), "check-attr", "text", "--", "a.txt"],
            capture_output=True, text=True, env=clean_env(),
        ).stdout.strip()
        self.assertTrue(unpinned.endswith("set"), f"the working tree should see the new rule, got {unpinned!r}")

    def test_the_same_drift_is_caught_once_it_is_in_the_basis(self) -> None:
        self.canonical_base()
        self.write(".gitattributes", CANONICAL_LINE + "a.txt text\n")
        self.refusal(lambda: self.evaluate(self.commit("drifted"), ["a.txt"]))

    def test_a_filter_driver_named_unset_refuses(self) -> None:
        """The printed word `unset` proves nothing while a driver of that name exists."""
        base = self.canonical_base()
        git(self.store.root, "config", "filter.unset.clean", "cat")
        self.assertIn("unset", str(self.refusal(lambda: self.evaluate(base, ["a.txt"]))))

    def test_a_filter_driver_named_unspecified_refuses(self) -> None:
        base = self.canonical_base()
        git(self.store.root, "config", "filter.unspecified.clean", "cat")
        self.assertIn("unspecified", str(self.refusal(lambda: self.evaluate(base, ["a.txt"]))))

    def test_the_hazard_check_runs_even_for_an_empty_path_set(self) -> None:
        base = self.canonical_base()
        git(self.store.root, "config", "filter.unset.clean", "cat")
        self.refusal(lambda: self.evaluate(base, []))

    def test_a_question_git_cannot_answer_refuses(self) -> None:
        base = self.canonical_base()
        with mock.patch.object(gitcmd, "check_attributes", return_value=None):
            self.refusal(lambda: self.evaluate(base, ["a.txt"]))

    def test_an_unpinnable_basis_refuses_before_git_is_asked(self) -> None:
        for basis in ("HEAD", "main", OID[:12], ""):
            with self.subTest(basis=basis):
                self.refusal(lambda: self.evaluate(basis, ["a.txt"]))

    def test_a_path_whose_surface_is_not_decidable_refuses(self) -> None:
        base = self.canonical_base()
        for relative in ("/a.txt", "a\\b.txt", "./a.txt", "a/../b.txt", "a//b.txt", "C:/a.txt", ""):
            with self.subTest(relative=relative):
                self.refusal(lambda: self.evaluate(base, [relative]))


class ObjectFormatTests(WorklineTestCase):
    """Both widths: a basis is whatever identity its repository stores."""

    def project_with_format(self, object_format: str) -> ProjectStore:
        root = self.new_dir(f"fmt-{object_format}")
        made = subprocess.run(
            ["git", "init", "-q", "-b", "main", f"--object-format={object_format}", str(root)],
            capture_output=True, text=True,
        )
        if made.returncode != 0:
            self.skipTest(f"this Git cannot create a {object_format} repository: {made.stderr.strip()[:80]}")
        git(root, "config", "user.name", "A")
        git(root, "config", "user.email", "a@x")
        (root / ".workline").mkdir(exist_ok=True)
        (root / ".gitattributes").write_text(CANONICAL_LINE, encoding="utf-8", newline="\n")
        (root / "a.txt").write_text("x\n", encoding="utf-8", newline="\n")
        git(root, "add", "-A")
        git(root, "commit", "-m", "base")
        return ProjectStore(root)

    def check(self, object_format: str, width: int) -> None:
        store = self.project_with_format(object_format)
        built = hermetic.enter(store)
        base = git(store.root, "rev-parse", "HEAD").strip()
        self.assertEqual(len(base), width)
        attributes.require_work_attribute_source(store, built, base)
        attributes.require_pinned_path_evaluation(store, built, base, ["a.txt", ".workline/review/g/x.yaml"])
        measured = attributes.require_attribute_pin_capability(store, built)
        self.assertEqual(measured.pinned, measured.raw)
        self.assertEqual(len(measured.pinned), width)

    def test_sha1_forty_hex(self) -> None:
        self.check("sha1", 40)

    def test_sha256_sixty_four_hex(self) -> None:
        self.check("sha256", 64)


# --------------------------------------------------------------------------- the unit boundary


class UnitBoundaryTests(unittest.TestCase):
    """Unit 3 is a foundation. It builds primitives and dispatches nothing."""

    def test_the_attribute_foundation_lives_in_its_own_module(self) -> None:
        for name in ("require_work_attribute_source", "require_pinned_path_evaluation",
                     "require_attribute_pin_capability", "probe_attribute_pin", "parse_source"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(attributes, name))

    def test_hermetic_gained_only_generic_pinned_invocation_support(self) -> None:
        """The class B authority learned to carry a pin; it learned no Work orchestration."""
        self.assertTrue(hasattr(hermetic.HermeticGit, "attribute_configuration_arguments"))
        for name in ("require_work_attribute_source", "probe_attribute_pin", "parse_source",
                     "require_pinned_path_evaluation", "MATERIAL_ATTRIBUTES", "FORM_L"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(hermetic, name))
                self.assertFalse(hasattr(hermetic.HermeticGit, name))

    def test_nothing_in_production_dispatches_into_the_foundation(self) -> None:
        from workline import gitops, mutation, roadmap_review
        from workline.review import checkout, planning, publication

        for module in (gitops, mutation, roadmap_review, checkout, planning, publication):
            with self.subTest(module=module.__name__):
                self.assertFalse(hasattr(module, "attributes"))

    def test_the_planning_checkout_capability_is_untouched(self) -> None:
        from workline.review import checkout

        self.assertEqual(checkout.CHECKOUT_CONTRACT, "review-v1-planning-checkout-v1")
        self.assertEqual(checkout.ATTRIBUTES, ("text", "eol", "filter", "ident", "working-tree-encoding"))
        self.assertTrue(hasattr(checkout, "require_effective_evaluation"))
        self.assertTrue(hasattr(checkout, "require_committed_evaluation"))
        self.assertTrue(hasattr(checkout, "require_checkout_capability"))

    def test_the_planning_transform_refusal_is_untouched(self) -> None:
        from workline import gitops

        self.assertTrue(hasattr(gitops, "require_no_planning_transform"))

    def test_later_unit_machinery_is_still_absent(self) -> None:
        """The Work persistence engine (P3 F3 Batch B) landed as its own module; none of it lives here."""
        from workline import mutation
        from workline.review.store import ReviewStore

        self.assertEqual(mutation.WORK_COMMIT_MODE, "review-v1-work-local-v2")
        self.assertEqual(mutation.PLANNING_COMMIT_MODE, "review-v1-planning-local-v1")
        for name in ("CommitTreePlan", "prepared_commit_id", "compose_resulting_tree"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(attributes, name))
        for writer in ("write_activation", "create_activation", "activate", "produce_activation"):
            with self.subTest(writer=writer):
                self.assertFalse(hasattr(ReviewStore, writer))

    def test_no_reserved_namespace_ownership_rule_is_implemented_here(self) -> None:
        """A-5 belongs to the unit that owns declaration, not to the attribute foundation."""
        self.assertFalse(hasattr(attributes, "review_reserved_namespace"))
        self.assertNotIn("review_reserved_namespace", attributes.__doc__ or "")


if __name__ == "__main__":
    unittest.main()
