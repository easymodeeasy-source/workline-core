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

import os
import subprocess
import unittest
from unittest import mock

from helpers import WorklineTestCase, git
from workline import gitcmd
from workline.errors import StopError
from workline.review import hermetic, paths as review_paths

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

    def test_no_attribute_pin_is_carried(self) -> None:
        """IP-8(b) is a later unit: nothing here resolves attributes against a tree."""
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

    def test_no_raw_ancestry_reader_exists_yet(self) -> None:
        """IP-26 is the next unit; the revision-view helpers stay as they are, backing no proof."""
        self.assertFalse(hasattr(hermetic, "RAW_PARENTS"))
        self.assertFalse(hasattr(hermetic, "raw_descends_from"))
        self.assertFalse(hasattr(hermetic, "raw_range"))
        self.assertTrue(hasattr(gitcmd, "commit_parents"))
        self.assertTrue(hasattr(gitcmd, "descends_from"))

    def test_no_attribute_pin_machinery_exists_yet(self) -> None:
        """IP-8(b)/IP-11/IP-12 are a later unit."""
        self.assertFalse(hasattr(gitcmd, "P3_WORK_ATTR_PIN_GIT_MIN"))
        self.assertNotIn("attr.tree", "".join(f"{k}={v}" for k, v in hermetic.CLASS_B_CONFIGURATION))

    def test_the_review_v1_work_persistence_identity_is_still_not_dispatchable(self) -> None:
        from workline import mutation

        self.assertEqual(mutation.PLANNING_COMMIT_MODE, "review-v1-planning-local-v1")
        self.assertFalse(hasattr(mutation, "WORK_COMMIT_MODE"))
        from workline.errors import ValidationError

        with self.assertRaises(ValidationError):
            mutation._validate_planning_commit({"mode": "review-v1-work-local-v2", "paths": [], "message": "m"})

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


if __name__ == "__main__":
    unittest.main()
