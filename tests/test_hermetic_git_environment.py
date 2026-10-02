"""The two Git environment classes of a review-v1 Work operation (P3 F3 §7.1.9, IP-25/IP-8/IP-10).

Git obeys its inherited environment as readily as its command line. An inherited
``GIT_AUTHOR_NAME`` writes someone else's name onto a commit; an inherited
``GIT_OBJECT_DIRECTORY`` makes the repository's own commit invisible. So every Git
invocation of this operation runs in an environment the implementation builds, in one
frozen order:

```text
STRIP  ->  CAPTURE  ->  NEUTRALIZE  ->  HERMETIC EXECUTION
```

Class A is the strip alone, so the configured identity can still be read; class B is the
strip plus the allowlist, with configuration neutralized and the captured identity
injected. Reversing the two middle steps breaks it in one direction or the other: capture
before strip is poisonable, neutralize before capture makes a global-only identity
unreadable.

This is the foundation only. Nothing dispatches to it: no persistence identity names it,
the review-v1 Work path stays unavailable, and the tests below pin that.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from helpers import WorklineTestCase, git
from workline import gitcmd
from workline.errors import StopError
from workline.review import hermetic, paths as review_paths
from workline.store import ProjectStore

#: A hostile ambient environment of the shape M-61 and M-63 measured.
HOSTILE = {
    "GIT_AUTHOR_NAME": "Attacker",
    "GIT_AUTHOR_EMAIL": "evil@x",
    "GIT_COMMITTER_NAME": "AttackerC",
    "GIT_COMMITTER_EMAIL": "evilc@x",
    "GIT_INDEX_FILE": "hostile-index",
    "GIT_OBJECT_DIRECTORY": "hostile-objects",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES": "hostile-alt",
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "user.name",
    "GIT_CONFIG_VALUE_0": "ConfigEnvAttacker",
    "GIT_DIR": "hostile-dir",
    "GIT_WORK_TREE": "hostile-work-tree",
}

DATE = "1700000000 +0000"


class EnvironmentCase(WorklineTestCase):
    """A Project with a configured identity, and a hostile ambient environment around it."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        git(self.store.root, "config", "user.name", "Real Person")
        git(self.store.root, "config", "user.email", "real@proj")

    def hostile(self):
        return mock.patch.dict(os.environ, HOSTILE)


class StripTests(EnvironmentCase):
    """The strip is universal: no inherited GIT_* survives, in either class."""

    def test_every_inherited_git_variable_is_removed(self) -> None:
        with self.hostile():
            stripped = hermetic.stripped_environment()
        self.assertEqual([name for name in stripped if name.upper().startswith("GIT_")], [])

    def test_no_name_is_excused_from_the_strip(self) -> None:
        for name in HOSTILE:
            with self.subTest(variable=name):
                with mock.patch.dict(os.environ, {name: "hostile"}):
                    self.assertNotIn(name, hermetic.stripped_environment())

    def test_a_lowercase_git_prefixed_name_is_removed_too(self) -> None:
        """The comparison folds case, because the name is what Git reads, not its spelling here."""
        with mock.patch.dict(os.environ, {"git_author_name": "Attacker"}):
            self.assertNotIn("git_author_name", hermetic.stripped_environment())

    def test_everything_that_is_not_a_git_variable_is_kept(self) -> None:
        with mock.patch.dict(os.environ, {"PATH_LIKE_MARKER": "kept", **HOSTILE}):
            stripped = hermetic.stripped_environment()
        self.assertEqual(stripped["PATH_LIKE_MARKER"], "kept")

    def test_the_process_environment_is_not_modified(self) -> None:
        with mock.patch.dict(os.environ, HOSTILE):
            hermetic.stripped_environment()
            self.assertEqual(os.environ["GIT_AUTHOR_NAME"], "Attacker")


class ClassATests(EnvironmentCase):
    """The identity capture: the strip, and nothing injected."""

    def test_class_a_injects_nothing(self) -> None:
        with self.hostile():
            self.assertEqual(hermetic.class_a_environment(), hermetic.stripped_environment())

    def test_class_a_carries_no_neutralization_variable(self) -> None:
        """Injecting them here is what made the capture impossible (M-64)."""
        with self.hostile():
            environment = hermetic.class_a_environment()
        for name in ("GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_ATTR_NOSYSTEM"):
            with self.subTest(variable=name):
                self.assertNotIn(name, environment)

    def test_it_captures_the_configured_identity(self) -> None:
        found = hermetic.capture_identity(self.store.root)
        self.assertEqual((found.name, found.email), ("Real Person", "real@proj"))

    def test_a_hostile_ambient_identity_cannot_poison_the_capture(self) -> None:
        with self.hostile():
            found = hermetic.capture_identity(self.store.root)
        self.assertEqual((found.name, found.email), ("Real Person", "real@proj"))

    def test_a_hostile_git_config_env_cannot_poison_the_capture(self) -> None:
        """GIT_CONFIG_COUNT/KEY_0/VALUE_0 is configuration injected through the environment."""
        with mock.patch.dict(
            os.environ,
            {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "user.name", "GIT_CONFIG_VALUE_0": "ConfigEnvAttacker"},
        ):
            self.assertEqual(hermetic.capture_identity(self.store.root).name, "Real Person")

    def test_local_configuration_overrides_global(self) -> None:
        """``--get`` reads the merged configuration with ordinary precedence."""
        home = self.new_dir("home")
        (home / ".gitconfig").write_text(
            "[user]\n\tname = Global Person\n\temail = global@example.com\n", encoding="utf-8", newline="\n"
        )
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            found = hermetic.capture_identity(self.store.root)
        self.assertEqual((found.name, found.email), ("Real Person", "real@proj"))

    def test_a_global_only_identity_is_readable(self) -> None:
        """M-64: this is the case premature neutralization makes impossible."""
        bare = self.new_dir("global-only")
        git(bare, "init", "-b", "main")
        home = self.new_dir("home-global")
        (home / ".gitconfig").write_text(
            "[user]\n\tname = Global Person\n\temail = global@example.com\n", encoding="utf-8", newline="\n"
        )
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home), **HOSTILE}):
            found = hermetic.capture_identity(bare)
        self.assertEqual((found.name, found.email), ("Global Person", "global@example.com"))


class ClassAFailureTests(WorklineTestCase):
    """Identity is captured or the operation stops. There is no third answer."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.home = self.new_dir("empty-home")

    def capture(self):
        with mock.patch.dict(os.environ, {"HOME": str(self.home), "USERPROFILE": str(self.home)}):
            return hermetic.capture_identity(self.store.root)

    def refused(self) -> StopError:
        with self.assertRaises(StopError) as caught:
            self.capture()
        self.assertEqual(caught.exception.code, "review_identity_unavailable")
        return caught.exception

    def test_no_identity_at_all_stops(self) -> None:
        self.refused()

    def test_a_name_without_an_email_stops(self) -> None:
        git(self.store.root, "config", "user.name", "Only Name")
        self.assertIn("user.email", str(self.refused()))

    def test_an_email_without_a_name_stops(self) -> None:
        git(self.store.root, "config", "user.email", "only@mail")
        self.assertIn("user.name", str(self.refused()))

    def test_an_empty_configured_value_is_never_accepted(self) -> None:
        git(self.store.root, "config", "user.name", "")
        git(self.store.root, "config", "user.email", "real@proj")
        self.refused()

    def test_nothing_is_synthesized_from_the_operating_system(self) -> None:
        """No OS user, no hostname email, no placeholder - the failure is the whole answer."""
        message = str(self.refused())
        self.assertNotIn(os.environ.get("USERNAME", "\0no-such-value\0"), message)

    def test_git_var_is_not_a_fallback(self) -> None:
        """M-63: ``git var`` invents an identity where ``config --get`` refuses to."""
        git(self.store.root, "config", "user.email", "only@mail")
        found = gitcmd.run_git(self.store.root, "var", "GIT_AUTHOR_IDENT", check=False)
        self.assertTrue(found.ok, "git var would have answered here")
        self.refused()


class ClassBTests(EnvironmentCase):
    """The hermetic environment: the strip, the allowlist, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.hermetic = hermetic.enter(self.store)

    def git_names(self, environment: dict[str, str]) -> set[str]:
        return {name for name in environment if name.upper().startswith("GIT_")}

    def test_the_mandatory_allowlist_is_exactly_the_frozen_set(self) -> None:
        with self.hostile():
            environment = hermetic.enter(self.store).environment()
        self.assertEqual(self.git_names(environment), set(hermetic.CLASS_B_ALLOWLIST))
        self.assertEqual(len(hermetic.CLASS_B_ALLOWLIST), 6)

    def test_each_allowlisted_value_is_exact(self) -> None:
        environment = self.hermetic.environment()
        for name, value in hermetic.CLASS_B_FIXED_VALUES.items():
            with self.subTest(variable=name):
                self.assertEqual(environment[name], value)

    def test_no_inherited_git_variable_leaks_into_class_b(self) -> None:
        with self.hostile():
            environment = hermetic.enter(self.store).environment()
        for name in HOSTILE:
            with self.subTest(variable=name):
                self.assertNotIn(name, self.git_names(environment))
        self.assertNotIn("ConfigEnvAttacker", "".join(environment.values()))

    def test_configuration_is_neutralized_by_an_empty_workline_owned_file(self) -> None:
        environment = self.hermetic.environment()
        self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")
        named = environment["GIT_CONFIG_GLOBAL"]
        self.assertTrue(os.path.isfile(named))
        self.assertEqual(os.path.getsize(named), 0)
        self.assertTrue(named.endswith(os.path.normpath(review_paths.RUNTIME_NO_CONFIG_FILE).split(os.sep)[-1]))

    def test_neutralized_configuration_hides_a_global_identity(self) -> None:
        """M-64, and the whole reason the identity is captured in class A and injected here.

        The neutralization removes the SYSTEM and GLOBAL sources. A Project whose identity
        lives only there reads back empty under class B - which is exactly the case that
        would make an ordinary Project uncommittable without the class A capture (M-51).
        """
        bare = self.new_dir("global-only")
        git(bare, "init", "-b", "main")
        home = self.new_dir("home-global-b")
        (home / ".gitconfig").write_text(
            "[user]\n\tname = Global Person\n\temail = global@example.com\n", encoding="utf-8", newline="\n"
        )
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            captured = hermetic.capture_identity(bare)
            under_class_b = gitcmd.run_git(
                bare, "config", "--get", "user.name", check=False, env=self.hermetic.environment()
            )
        self.assertEqual(captured.name, "Global Person")
        self.assertFalse(under_class_b.ok)
        self.assertEqual(under_class_b.stdout.strip(), "")

    def test_repository_local_configuration_is_not_neutralized(self) -> None:
        """Stated because it is the other half of the rule: the Project's own config is the Project's."""
        found = gitcmd.run_git(
            self.store.root, "config", "--get", "user.name", check=False, env=self.hermetic.environment()
        )
        self.assertTrue(found.ok)
        self.assertEqual(found.stdout.strip(), "Real Person")

    def test_literal_pathspecs_is_set(self) -> None:
        self.assertEqual(self.hermetic.environment()["GIT_LITERAL_PATHSPECS"], "1")

    def test_object_semantics_are_set(self) -> None:
        environment = self.hermetic.environment()
        self.assertEqual(environment["GIT_NO_REPLACE_OBJECTS"], "1")
        self.assertEqual(environment["GIT_NO_LAZY_FETCH"], "1")

    def test_the_index_file_appears_only_when_one_is_named(self) -> None:
        self.assertNotIn("GIT_INDEX_FILE", self.hermetic.environment())
        named = self.hermetic.environment(index_file="isolated.index")
        self.assertEqual(named["GIT_INDEX_FILE"], "isolated.index")

    def test_the_identity_appears_only_on_the_commit_environment(self) -> None:
        plain = self.hermetic.environment()
        for name in hermetic.CLASS_B_IDENTITY_VARIABLES:
            with self.subTest(variable=name):
                self.assertNotIn(name, plain)

    def test_the_commit_environment_injects_the_captured_identity_and_one_date(self) -> None:
        environment = self.hermetic.commit_environment(DATE)
        self.assertEqual(environment["GIT_AUTHOR_NAME"], "Real Person")
        self.assertEqual(environment["GIT_AUTHOR_EMAIL"], "real@proj")
        self.assertEqual(environment["GIT_COMMITTER_NAME"], "Real Person")
        self.assertEqual(environment["GIT_COMMITTER_EMAIL"], "real@proj")
        self.assertEqual(environment["GIT_AUTHOR_DATE"], DATE)
        self.assertEqual(environment["GIT_COMMITTER_DATE"], DATE)

    def test_the_commit_environment_adds_nothing_beyond_the_identity(self) -> None:
        added = self.git_names(self.hermetic.commit_environment(DATE)) - self.git_names(self.hermetic.environment())
        self.assertEqual(added, set(hermetic.CLASS_B_IDENTITY_VARIABLES))

    def test_an_identity_cannot_be_injected_without_a_timestamp(self) -> None:
        with self.assertRaises(StopError) as caught:
            self.hermetic.commit_environment("")
        self.assertEqual(caught.exception.code, "review_commit_date_unavailable")


class ClassBConfigurationTests(EnvironmentCase):
    """The ``-c`` settings every class B invocation carries, including IP-10."""

    def setUp(self) -> None:
        super().setUp()
        self.hermetic = hermetic.enter(self.store)
        self.settings = dict(
            argument.split("=", 1)
            for argument in self.hermetic.configuration_arguments()
            if argument != "-c"
        )

    def test_line_endings_are_configuration_not_attributes(self) -> None:
        """IP-10: measured, core.autocrlf=true normalizes CRLF check-in content anyway (M-23)."""
        self.assertEqual(self.settings["core.autocrlf"], "false")
        self.assertEqual(self.settings["core.eol"], "lf")

    def test_the_frozen_controls_are_all_present(self) -> None:
        for key, value in hermetic.CLASS_B_CONFIGURATION:
            with self.subTest(setting=key):
                self.assertEqual(self.settings[key], value)

    def test_hooks_are_a_workline_owned_empty_directory(self) -> None:
        named = self.settings["core.hooksPath"]
        self.assertTrue(os.path.isdir(named))
        self.assertEqual(os.listdir(named), [])

    def test_the_hooks_directory_is_reproven_on_every_use(self) -> None:
        """A hook can be dropped there at any later moment, so it is proven immediately before use."""
        named = self.settings["core.hooksPath"]
        (self.store.root / review_paths.RUNTIME_NO_HOOKS_DIR / "pre-commit").write_text("#!/bin/sh\n")
        with self.assertRaises(StopError) as caught:
            self.hermetic.configuration_arguments()
        self.assertEqual(caught.exception.code, "review_hooks_path_invalid")
        self.assertTrue(os.path.isdir(named))

    def test_no_attribute_pin_is_carried_by_the_ordinary_class_b_form(self) -> None:
        """IP-8(b) qualifies the invocations that RESOLVE attributes, not every class B one.

        The pin belongs to :meth:`attribute_configuration_arguments`, which
        composes from these arguments; an ordinary class B command - a
        ``cat-file``, an ``update-ref`` - resolves no attribute and carries none.
        """
        self.assertNotIn("attr.tree", self.settings)
        self.assertNotIn("GIT_ATTR_SOURCE", self.hermetic.environment())


class EntryCheckTests(EnvironmentCase):
    """The §7.1.9 entry reads. Defence in depth, reported rather than silent."""

    def test_a_graft_file_stops_at_entry(self) -> None:
        info = self.store.root / ".git" / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "grafts").write_text("dead beef\n", encoding="utf-8", newline="\n")
        with self.assertRaises(StopError) as caught:
            hermetic.enter(self.store)
        self.assertEqual(caught.exception.code, "review_repository_grafted")

    def test_an_ordinary_project_has_no_promisor_remote(self) -> None:
        self.assertEqual(hermetic.enter(self.store).promisor_remotes, ())

    def test_a_promisor_remote_is_read_and_reported(self) -> None:
        git(self.store.root, "config", "remote.origin.promisor", "true")
        self.assertEqual(hermetic.enter(self.store).promisor_remotes, ("origin",))

    def test_the_promisor_read_is_not_poisoned_by_a_hostile_environment(self) -> None:
        with self.hostile():
            self.assertEqual(hermetic.enter(self.store).promisor_remotes, ())


class HostileExecutionTests(EnvironmentCase):
    """What the environment is for: Git does what the Project says, not what the caller exported."""

    def test_a_hostile_object_directory_no_longer_redirects_a_class_b_command(self) -> None:
        """M-61: ambient, the repository's own commit is invisible; under class B it is there."""
        empty_objects = self.new_dir("empty-objects")
        redirect = {name: value for name, value in os.environ.items() if not name.upper().startswith("GIT_")}
        redirect["GIT_OBJECT_DIRECTORY"] = str(empty_objects)
        ambient = gitcmd.run_git(self.store.root, "cat-file", "-e", "HEAD", check=False, env=redirect)
        self.assertFalse(ambient.ok, "the ambient hostile environment should hide the commit")

        with mock.patch.dict(os.environ, {"GIT_OBJECT_DIRECTORY": str(empty_objects)}):
            found = hermetic.enter(self.store).run("cat-file", "-e", "HEAD", check=False)
        self.assertTrue(found.ok)

    def test_a_commit_carries_the_configured_identity_not_the_ambient_one(self) -> None:
        """M-63 end to end, read back off the raw object."""
        with self.hostile():
            built = hermetic.enter(self.store)
            tree = built.run("hash-object", "-w", "-t", "tree", "--stdin").stdout.strip() or self.empty_tree(built)
            made = subprocess.run(
                ["git", "-C", str(self.store.root), *built.configuration_arguments(),
                 "commit-tree", "--no-gpg-sign", "-m", "hermetic", tree],
                capture_output=True, text=True, env=built.commit_environment(DATE),
            ).stdout.strip()
        raw = gitcmd.run_git(self.store.root, "cat-file", "commit", made).stdout
        self.assertIn("author Real Person <real@proj> " + DATE, raw)
        self.assertIn("committer Real Person <real@proj> " + DATE, raw)
        for hostile in ("Attacker", "evil@x", "AttackerC", "evilc@x"):
            with self.subTest(value=hostile):
                self.assertNotIn(hostile, raw)

    def empty_tree(self, built) -> str:
        found = subprocess.run(
            ["git", "-C", str(self.store.root), "hash-object", "-w", "-t", "tree", "--stdin"],
            input=b"", capture_output=True, env=built.environment(),
        )
        return found.stdout.decode().strip()


class OrderingTests(EnvironmentCase):
    """The order is the mechanism, so the API is what enforces it."""

    def test_a_hermetic_environment_is_reached_only_through_the_ordered_entry(self) -> None:
        """There is no way to hold one without an identity captured before neutralization."""
        git(self.store.root, "config", "--unset", "user.name")
        home = self.new_dir("home-unset")
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            with self.assertRaises(StopError) as caught:
                hermetic.enter(self.store)
        self.assertEqual(caught.exception.code, "review_identity_unavailable")

    def test_the_captured_identity_is_what_class_b_injects(self) -> None:
        built = hermetic.enter(self.store)
        self.assertEqual(built.commit_environment(DATE)["GIT_AUTHOR_NAME"], built.identity.name)


class GateBoundaryTests(unittest.TestCase):
    """The foundation is inert: it builds environments and dispatches nothing."""

    def test_raw_ancestry_lives_in_its_own_unit_not_in_this_one(self) -> None:
        """IP-26 has since landed in the unit that owns it (``review.ancestry``).

        This pinned its absence while Unit 1 was the unit being built. What still has to
        hold is the separation: the class B authority learned to return BYTES, which is a
        generic execution primitive, and learned no ancestry. No parent reader, no walk and
        no step budget lives here, and the revision-view helpers stay where they are,
        backing no proof.
        """
        from workline.review import ancestry

        for name in ("RAW_PARENTS", "raw_parents", "raw_descends_from", "raw_range",
                     "P3_RAW_ANCESTRY_STEP_BUDGET"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(hermetic, name))
                self.assertFalse(hasattr(hermetic.HermeticGit, name))
        self.assertTrue(hasattr(hermetic.HermeticGit, "run_bytes"))
        self.assertTrue(hasattr(ancestry, "raw_parents"))
        self.assertTrue(hasattr(gitcmd, "commit_parents"))
        self.assertTrue(hasattr(gitcmd, "descends_from"))

    def test_the_attribute_pin_machinery_lives_outside_this_unit(self) -> None:
        """IP-8(b)/IP-11/IP-12 landed as their own foundation; this module only composes the arguments."""
        from workline.review import attributes

        self.assertEqual(gitcmd.P3_WORK_ATTR_PIN_GIT_MIN, (2, 43, 0))
        self.assertNotIn("attr.tree", "".join(f"{k}={v}" for k, v in hermetic.CLASS_B_CONFIGURATION))
        self.assertTrue(hasattr(hermetic.HermeticGit, "attribute_configuration_arguments"))
        for name in ("require_work_attribute_source", "probe_attribute_pin", "parse_source",
                     "require_attribute_pin_capability", "MATERIAL_ATTRIBUTES"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(hermetic, name))
                self.assertTrue(hasattr(attributes, name))

    def test_the_work_persistence_engine_lives_outside_this_unit(self) -> None:
        """P3 F3 Batch B made the Work identity dispatchable; this ordered-gate pin is retired.

        The separation that still holds: the engine is its own module built ON the class B
        authority, and the class B authority learned no commit machinery of its own - only the
        generic writing runner every class B write goes through.
        """
        from workline import mutation
        from workline.errors import ValidationError
        from workline.review import workcommit

        self.assertEqual(mutation.PLANNING_COMMIT_MODE, "review-v1-planning-local-v1")
        self.assertEqual(mutation.WORK_COMMIT_MODE, "review-v1-work-local-v2")
        self.assertTrue(hasattr(workcommit, "CommitTreePlan"))
        self.assertTrue(hasattr(hermetic.HermeticGit, "execute"))
        for name in ("CommitTreePlan", "build", "replay", "refresh_real_index", "PREPARED_COMMIT"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(hermetic, name))
                self.assertFalse(hasattr(hermetic.HermeticGit, name))
        with self.assertRaises(ValidationError):
            mutation._validate_planning_commit({"mode": "review-v1-work-local-v1", "paths": [], "message": "m"})

    def test_gate_3_activation_is_still_not_produced(self) -> None:
        from workline.review import records
        from workline.review.store import ReviewStore

        self.assertTrue(hasattr(records, "WorkTerminalActivation"))
        for writer in ("write_activation", "create_activation", "activate", "produce_activation"):
            with self.subTest(writer=writer):
                self.assertFalse(hasattr(ReviewStore, writer))

    def test_gate_1_and_gate_2_are_preserved(self) -> None:
        from workline.review import records
        from workline.store import EVENT_LIFECYCLE_FIELDS

        self.assertEqual(EVENT_LIFECYCLE_FIELDS, ("id", "type", "entity", "at"))
        self.assertIn("artifact_kind", records.Consumption.__dataclass_fields__)
        self.assertEqual(records.CONSUMPTION_ARTIFACT_KINDS, ("result_commit", "empty"))

    def test_the_planning_primitive_still_builds_its_own_environment(self) -> None:
        """The planning identity is not redefined: P2 keeps its own hooks proof and its own commands."""
        from workline import mutation

        self.assertTrue(hasattr(mutation, "_no_hooks_directory"))
        self.assertTrue(hasattr(gitcmd, "contained_add"))
        self.assertTrue(hasattr(gitcmd, "contained_commit"))


class RecordingCase(EnvironmentCase):
    """Watch the argv and environment of every Git command ``enter`` actually runs."""

    def setUp(self) -> None:
        super().setUp()
        self.calls: list[tuple[tuple[str, ...], dict]] = []
        real = gitcmd.run_git

        def recording(repo, *args, **kwargs):
            self.calls.append((args, kwargs))
            return real(repo, *args, **kwargs)

        patcher = mock.patch.object(gitcmd, "run_git", recording)
        patcher.start()
        self.addCleanup(patcher.stop)

    def call_with(self, needle: str) -> tuple[tuple[str, ...], dict]:
        found = [call for call in self.calls if needle in call[0]]
        self.assertEqual(len(found), 1, f"expected exactly one {needle} invocation, saw {len(found)}")
        return found[0]

    def settings_of(self, args: tuple[str, ...]) -> dict[str, str]:
        return dict(
            argument.split("=", 1)
            for position, argument in enumerate(args)
            if position > 0 and args[position - 1] == "-c"
        )


class EntryInvocationEnvelopeTests(RecordingCase):
    """Every entry Git read is a class B invocation IN FULL, not only in its environment.

    §7.1.9 names the class B invocations and does not exempt the entry reads from any part
    of the class: the allowlist AND the frozen configuration controls, IP-10 among them.
    """

    def entry_calls(self):
        hermetic.enter(self.store)
        return (
            ("promisor read", self.call_with("--get-regexp")),
            ("shallow read", self.call_with("--is-shallow-repository")),
        )

    def test_each_entry_read_carries_the_exact_class_b_environment(self) -> None:
        for label, (args, kwargs) in self.entry_calls():
            with self.subTest(invocation=label):
                environment = kwargs["env"]
                names = {name for name in environment if name.upper().startswith("GIT_")}
                self.assertEqual(names, set(hermetic.CLASS_B_ALLOWLIST))

    def test_each_entry_read_carries_the_frozen_configuration_controls(self) -> None:
        for label, (args, _) in self.entry_calls():
            settings = self.settings_of(args)
            for key, value in hermetic.CLASS_B_CONFIGURATION:
                with self.subTest(invocation=label, setting=key):
                    self.assertEqual(settings.get(key), value)

    def test_each_entry_read_carries_ip_10(self) -> None:
        """IP-10 applies to every class B invocation, not only to those that write files."""
        for label, (args, _) in self.entry_calls():
            settings = self.settings_of(args)
            with self.subTest(invocation=label):
                self.assertEqual(settings.get("core.autocrlf"), "false")
                self.assertEqual(settings.get("core.eol"), "lf")

    def test_each_entry_read_carries_the_proven_hooks_directory(self) -> None:
        for label, (args, _) in self.entry_calls():
            named = self.settings_of(args).get("core.hooksPath")
            with self.subTest(invocation=label):
                self.assertTrue(named and os.path.isdir(named))
                self.assertEqual(os.listdir(named), [])

    def test_a_hook_dropped_before_entry_stops_the_entry_reads(self) -> None:
        """The hooks proof is not skipped for entry calls: it is the same proof, at the same time."""
        hooks = self.store.root / review_paths.RUNTIME_NO_HOOKS_DIR
        hooks.mkdir(parents=True, exist_ok=True)
        (hooks / "reference-transaction").write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
        with self.assertRaises(StopError) as caught:
            hermetic.enter(self.store)
        self.assertEqual(caught.exception.code, "review_hooks_path_invalid")

    def test_no_commit_identity_or_date_reaches_a_non_commit_entry_read(self) -> None:
        for label, (_, kwargs) in self.entry_calls():
            for name in hermetic.CLASS_B_IDENTITY_VARIABLES:
                with self.subTest(invocation=label, variable=name):
                    self.assertNotIn(name, kwargs["env"])

    def test_no_index_file_reaches_a_non_index_entry_read(self) -> None:
        for label, (_, kwargs) in self.entry_calls():
            with self.subTest(invocation=label):
                self.assertNotIn("GIT_INDEX_FILE", kwargs["env"])

    def test_class_a_did_not_inherit_the_class_b_controls(self) -> None:
        """The repair must not have leaked the configuration envelope backwards into the capture."""
        hermetic.enter(self.store)
        captures = [call for call in self.calls if "--get" in call[0] and "user.name" in call[0]]
        self.assertTrue(captures)
        for args, kwargs in captures:
            self.assertNotIn("-c", args)
            self.assertEqual(
                {name for name in kwargs["env"] if name.upper().startswith("GIT_")}, set()
            )

    def test_the_identity_is_still_captured_before_any_class_b_invocation(self) -> None:
        """STRIP -> CAPTURE -> NEUTRALIZE -> HERMETIC EXECUTION, proven by call order."""
        hermetic.enter(self.store)
        first_class_b = min(
            position for position, (args, _) in enumerate(self.calls) if "-c" in args
        )
        last_capture = max(
            position for position, (args, _) in enumerate(self.calls) if "--get" in args and "user.email" in args
        )
        self.assertLess(last_capture, first_class_b)


class GraftsPredicateTests(EnvironmentCase):
    """The contract refuses a graft file that is PRESENT AND NON-EMPTY, and only that."""

    def grafts_path(self):
        info = self.store.root / ".git" / "info"
        info.mkdir(parents=True, exist_ok=True)
        return info / "grafts"

    def refusal(self) -> StopError:
        with self.assertRaises(StopError) as caught:
            hermetic.enter(self.store)
        self.assertEqual(caught.exception.code, "review_repository_grafted")
        return caught.exception

    def test_an_absent_graft_file_is_allowed(self) -> None:
        self.assertFalse(os.path.lexists(self.grafts_path()))
        self.assertIsNotNone(hermetic.enter(self.store))

    def test_an_empty_graft_file_is_allowed(self) -> None:
        """§21.14 B: "if present and non-empty". An empty file grafts nothing."""
        self.grafts_path().write_bytes(b"")
        self.assertIsNotNone(hermetic.enter(self.store))

    def test_a_non_empty_graft_file_stops(self) -> None:
        self.grafts_path().write_text("dead beef\n", encoding="utf-8", newline="\n")
        self.assertIn("non-empty", str(self.refusal()))

    def test_a_single_byte_graft_file_stops(self) -> None:
        self.grafts_path().write_bytes(b"\n")
        self.refusal()

    def test_a_directory_at_the_graft_path_fails_closed(self) -> None:
        """Not "empty file allowed" but "arbitrary object allowed": what cannot be proven empty is refused."""
        self.grafts_path().mkdir()
        self.assertIn("not an ordinary file", str(self.refusal()))

    def test_a_symlink_at_the_graft_path_fails_closed(self) -> None:
        target = self.store.root / "graft-target"
        target.write_bytes(b"")
        try:
            os.symlink(target, self.grafts_path())
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"file symlinks are refused here: {exc}")
        self.assertIn("not an ordinary file", str(self.refusal()))


class ShallowRepositoryTests(WorklineTestCase):
    """A genuine shallow repository, cloned for the test, is refused at entry."""

    def source(self):
        """A disposable source with two commits, so a depth-1 clone is genuinely shallow."""
        source = self.new_dir("shallow-source")
        git(source, "init", "-b", "main")
        git(source, "config", "user.name", "Real Person")
        git(source, "config", "user.email", "real@proj")
        for number in (1, 2):
            (source / f"f{number}.txt").write_text(f"{number}\n", encoding="utf-8", newline="\n")
            git(source, "add", f"f{number}.txt")
            git(source, "commit", "-m", f"c{number}")
        return source

    def cloned(self, *, depth: int | None):
        source = self.source()
        target = self.new_dir(f"clone-depth-{depth}")
        arguments = ["clone", "-q"]
        if depth is not None:
            arguments += [f"--depth={depth}"]
        git(self.tmp, *arguments, source.resolve().as_uri(), str(target))
        git(target, "config", "user.name", "Real Person")
        git(target, "config", "user.email", "real@proj")
        (target / ".workline").mkdir(exist_ok=True)
        return ProjectStore(target)

    def test_a_full_clone_passes_the_shallow_check(self) -> None:
        store = self.cloned(depth=None)
        self.assertFalse((store.root / ".git" / "shallow").exists())
        self.assertIsNotNone(hermetic.enter(store))

    def test_a_shallow_clone_stops_at_entry(self) -> None:
        store = self.cloned(depth=1)
        self.assertTrue((store.root / ".git" / "shallow").exists(), "the clone is genuinely shallow")
        with self.assertRaises(StopError) as caught:
            hermetic.enter(store)
        self.assertEqual(caught.exception.code, "review_repository_shallow")

    def test_the_shallow_query_travels_through_the_complete_class_b_envelope(self) -> None:
        store = self.cloned(depth=1)
        seen: list[tuple[tuple[str, ...], dict]] = []
        real = gitcmd.run_git

        def recording(repo, *args, **kwargs):
            seen.append((args, kwargs))
            return real(repo, *args, **kwargs)

        with mock.patch.object(gitcmd, "run_git", recording):
            with self.assertRaises(StopError):
                hermetic.enter(store)
        query = [call for call in seen if "--is-shallow-repository" in call[0]]
        self.assertEqual(len(query), 1)
        args, kwargs = query[0]
        settings = dict(
            argument.split("=", 1)
            for position, argument in enumerate(args)
            if position > 0 and args[position - 1] == "-c"
        )
        for key, value in hermetic.CLASS_B_CONFIGURATION:
            with self.subTest(setting=key):
                self.assertEqual(settings.get(key), value)
        self.assertIn("core.hooksPath", settings)
        self.assertEqual(
            {name for name in kwargs["env"] if name.upper().startswith("GIT_")},
            set(hermetic.CLASS_B_ALLOWLIST),
        )


class PromisorEntryTests(RecordingCase):
    """The promisor read is the real command, under the real neutralization."""

    def test_the_exact_command_is_run(self) -> None:
        hermetic.enter(self.store)
        args, _ = self.call_with("--get-regexp")
        self.assertIn("config", args)
        self.assertIn(r"^remote\..*\.promisor$", args)

    def test_a_repository_local_promisor_remote_is_observed(self) -> None:
        """Repository-local configuration is not neutralized, so the Project's own answer is read."""
        git(self.store.root, "config", "remote.origin.promisor", "true")
        self.assertEqual(hermetic.enter(self.store).promisor_remotes, ("origin",))

    def test_several_promisor_remotes_are_reported_in_order(self) -> None:
        git(self.store.root, "config", "remote.zulu.promisor", "true")
        git(self.store.root, "config", "remote.alpha.promisor", "true")
        self.assertEqual(hermetic.enter(self.store).promisor_remotes, ("alpha", "zulu"))

    def test_a_global_promisor_remote_is_not_visible_under_neutralization(self) -> None:
        """Global configuration takes no part in a class B invocation, by construction."""
        home = self.new_dir("home-promisor")
        (home / ".gitconfig").write_text(
            '[remote "global"]\n\tpromisor = true\n', encoding="utf-8", newline="\n"
        )
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            self.assertEqual(hermetic.enter(self.store).promisor_remotes, ())

    def test_a_hostile_config_environment_cannot_invent_a_promisor_remote(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "remote.injected.promisor",
                "GIT_CONFIG_VALUE_0": "true",
            },
        ):
            self.assertEqual(hermetic.enter(self.store).promisor_remotes, ())


# --------------------------------------------------------------------------- the read-only class B context


def project_tree(root: Path) -> dict[str, str]:
    """Every directory and file under ``root``, ``.git`` and runtime included, file contents hashed."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "<dir>"
        for path in sorted(root.rglob("*"))
    }


class ReadOnlyClassBTests(EnvironmentCase):
    """Committed-object reads under the class B envelope: no identity, and nothing written into the Project."""

    def setUp(self) -> None:
        super().setUp()
        self.root = self.store.root
        (self.root / "kept.txt").write_bytes(b"committed bytes\n")
        git(self.root, "add", "kept.txt")
        git(self.root, "commit", "-q", "-m", "a committed file", "--no-verify")
        self.head = git(self.root, "rev-parse", "HEAD").strip()
        self.calls: list[tuple[tuple[str, ...], dict]] = []
        real = gitcmd.run_git_bytes

        def recording(repo, *args, **kwargs):
            self.calls.append((args, kwargs))
            return real(repo, *args, **kwargs)

        patcher = mock.patch.object(gitcmd, "run_git_bytes", recording)
        patcher.start()
        self.addCleanup(patcher.stop)

    def settings_of(self, args: tuple[str, ...]) -> dict[str, str]:
        return dict(argument.split("=", 1) for position, argument in enumerate(args)
                    if position > 0 and args[position - 1] == "-c")

    def outside_the_project(self, path: str) -> bool:
        resolved, root = Path(path).resolve(), self.root.resolve()
        return resolved != root and root not in resolved.parents

    def read_all(self, reader: hermetic.ReadOnlyGit) -> None:
        self.assertEqual(reader.run_bytes("rev-parse", "--verify", "HEAD^{commit}").stdout.decode().strip(), self.head)
        self.assertTrue(reader.run_bytes("ls-tree", "-z", "--full-tree", self.head, "--", "kept.txt").stdout)
        self.assertEqual(reader.run_bytes("cat-file", "blob", f"{self.head}:kept.txt").stdout, b"committed bytes\n")

    def test_every_read_carries_the_whole_class_b_envelope_from_scratch_outside_the_project(self) -> None:
        with hermetic.read_only(self.root) as reader:
            self.read_all(reader)
            self.assertEqual(len(self.calls), 3)
            for args, kwargs in self.calls:
                environment, settings = kwargs["env"], self.settings_of(args)
                with self.subTest(command=args[len(settings) * 2]):
                    self.assertEqual(sorted(k for k in environment if k.upper().startswith("GIT_")),
                                     sorted(hermetic.CLASS_B_ALLOWLIST))
                    for name, value in hermetic.CLASS_B_FIXED_VALUES.items():
                        self.assertEqual(environment[name], value)
                    for key, value in hermetic.CLASS_B_CONFIGURATION:
                        self.assertEqual(settings[key], value)
                    config, hooks = environment["GIT_CONFIG_GLOBAL"], settings["core.hooksPath"]
                    self.assertTrue(self.outside_the_project(config) and self.outside_the_project(hooks))
                    self.assertTrue(Path(config).is_file() and Path(config).stat().st_size == 0)
                    self.assertTrue(Path(hooks).is_dir() and not any(Path(hooks).iterdir()))
                    for name in hermetic.CLASS_B_IDENTITY_VARIABLES:
                        self.assertNotIn(name, environment)
                    self.assertNotIn("GIT_INDEX_FILE", environment)
            scratch = Path(self.calls[0][1]["env"]["GIT_CONFIG_GLOBAL"]).parent
        self.assertFalse(scratch.exists(), "the context's scratch is removed when it exits")

    def test_it_runs_the_same_class_b_configuration_as_the_write_capable_entry(self) -> None:
        """One definition of the envelope: the two differ only in where the two empty objects live."""
        with hermetic.read_only(self.root) as reader:
            read = self.settings_of(reader.configuration_arguments())
        written = self.settings_of(hermetic.enter(self.store).configuration_arguments())
        self.assertEqual({k: v for k, v in read.items() if k != "core.hooksPath"},
                         {k: v for k, v in written.items() if k != "core.hooksPath"})
        self.assertEqual(list(read), list(written))

    def test_a_hostile_inherited_environment_does_not_reach_a_read(self) -> None:
        empty_objects = self.new_dir("empty-objects")
        hostile = {**HOSTILE, "GIT_OBJECT_DIRECTORY": str(empty_objects), "GIT_INDEX_FILE": str(self.tmp / "hostile-index"),
                   "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": str(self.tmp)}
        with mock.patch.dict(os.environ, hostile), hermetic.read_only(self.root) as reader:
            self.read_all(reader)
            environment = reader.environment()
        for name in hostile:
            with self.subTest(name=name):
                self.assertNotIn(name, environment)
        self.assertFalse((self.tmp / "hostile-index").exists())

    def test_a_replacement_object_does_not_govern_a_read(self) -> None:
        found = subprocess.run(["git", "-C", str(self.root), "hash-object", "-w", "--stdin"], input=b"replaced\n",
                               capture_output=True, check=True)
        fake = found.stdout.decode().strip()
        original = git(self.root, "rev-parse", f"{self.head}:kept.txt").strip()
        git(self.root, "replace", original, fake)
        self.assertEqual(git(self.root, "cat-file", "blob", original), "replaced\n", "ambient Git follows the replacement")
        with hermetic.read_only(self.root) as reader:
            self.assertEqual(reader.run_bytes("cat-file", "blob", original).stdout, b"committed bytes\n")

    def test_no_identity_is_captured_and_none_is_needed(self) -> None:
        git(self.root, "config", "--unset", "user.name")
        git(self.root, "config", "--unset", "user.email")
        home = self.new_dir("home-unset")
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            with self.assertRaises(StopError) as refused:
                hermetic.enter(self.store)
            self.assertEqual(refused.exception.code, "review_identity_unavailable", "the write-capable entry still needs one")
            with mock.patch.object(hermetic, "capture_identity", side_effect=AssertionError("an identity was captured")):
                with hermetic.read_only(self.root) as reader:
                    self.read_all(reader)

    def test_the_project_is_unchanged_by_a_read(self) -> None:
        before = project_tree(self.root)
        with hermetic.read_only(self.root) as reader:
            self.read_all(reader)
        self.assertEqual(project_tree(self.root), before)

    def test_the_project_is_unchanged_by_a_failing_read_and_by_a_failing_body(self) -> None:
        before = project_tree(self.root)
        with hermetic.read_only(self.root) as reader:
            self.assertFalse(reader.run_bytes("cat-file", "blob", "0" * 40).ok)
            self.assertFalse(reader.run_bytes("ls-tree", "-z", "--full-tree", "0" * 40).ok)
        with self.assertRaises(RuntimeError), hermetic.read_only(self.root) as reader:
            scratch = Path(reader.environment()["GIT_CONFIG_GLOBAL"]).parent
            raise RuntimeError("the body failed")
        self.assertFalse(scratch.exists())
        self.assertEqual(project_tree(self.root), before)

    def test_it_can_run_nothing_but_committed_object_reads(self) -> None:
        for name in ("identity", "commit_environment", "execute", "attribute_configuration_arguments"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(hermetic.ReadOnlyGit, name))
        before = project_tree(self.root)
        with hermetic.read_only(self.root) as reader:
            for command in (("commit-tree", "-m", "x", "HEAD^{tree}"), ("hash-object", "-w", "kept.txt"),
                            ("update-ref", "refs/heads/x", "HEAD"), ("fetch", "origin"), ("push", "origin", "HEAD"),
                            ("status",), ()):
                with self.subTest(command=command), self.assertRaises(ValueError):
                    reader.run_bytes(*command)
        self.assertEqual(self.calls, [], "a refused command never reaches Git")
        self.assertEqual(project_tree(self.root), before)

    def test_each_scratch_object_is_reproven_immediately_before_use(self) -> None:
        with hermetic.read_only(self.root) as reader:
            hooks = Path(reader.configuration_arguments()[1].split("=", 1)[1])
            (hooks / "post-checkout").write_text("exit 0\n", encoding="utf-8")
            with self.assertRaises(StopError) as dropped:
                reader.run_bytes("rev-parse", "HEAD")
            self.assertEqual(dropped.exception.code, "review_hooks_path_invalid")
            (hooks / "post-checkout").unlink()
            config = Path(reader.environment()["GIT_CONFIG_GLOBAL"])
            config.write_text("[core]\n\thooksPath = elsewhere\n", encoding="utf-8")
            with self.assertRaises(StopError) as filled:
                reader.run_bytes("rev-parse", "HEAD")
            self.assertEqual(filled.exception.code, "review_no_config_file_invalid")

    def test_a_temporary_area_inside_the_project_is_refused_and_the_project_is_left_as_it_was(self) -> None:
        before = project_tree(self.root)
        inside = self.root / "scratch-inside"

        def mkdtemp(prefix: str = "") -> str:
            inside.mkdir()
            return str(inside)

        with mock.patch.object(hermetic.tempfile, "mkdtemp", side_effect=mkdtemp):
            with self.assertRaises(StopError) as refused, hermetic.read_only(self.root):
                self.fail("no context is given")
        self.assertEqual(refused.exception.code, "review_no_config_file_invalid")
        self.assertEqual(project_tree(self.root), before)

    def test_the_write_capable_entry_keeps_its_project_paths_and_its_identity(self) -> None:
        captured: list[Path] = []
        real = hermetic.capture_identity

        def capture(root):
            captured.append(root)
            return real(root)

        with mock.patch.object(hermetic, "capture_identity", side_effect=capture):
            built = hermetic.enter(self.store)
        self.assertEqual(captured, [self.store.root])
        self.assertEqual((built.identity.name, built.identity.email), ("Real Person", "real@proj"))
        self.assertEqual(built.environment()["GIT_CONFIG_GLOBAL"],
                         os.path.abspath(self.root / review_paths.RUNTIME_NO_CONFIG_FILE))
        self.assertEqual(self.settings_of(built.configuration_arguments())["core.hooksPath"],
                         os.path.abspath(self.root / review_paths.RUNTIME_NO_HOOKS_DIR))
        self.assertEqual(built.commit_environment(DATE)["GIT_AUTHOR_NAME"], "Real Person")


if __name__ == "__main__":
    unittest.main()
