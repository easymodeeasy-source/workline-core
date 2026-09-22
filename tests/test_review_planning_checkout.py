"""P2 §28 J: the checkout capability - the canonical Review-attribute rule, proven in four layers, and nothing else."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import unittest
from unittest import mock

from helpers import git
from planning_helpers import (
    CANONICAL_RULE, Crash, PlanningTestCase, Reviewer, blob_at, crash_at, design, plan, rr, run_ids,
)
from workline import gitcmd, gitops
from workline import roadmap as rm
from workline.errors import StopError
from workline.review import checkout, planning
from workline.review import paths as review_paths
from workline.review.store import ReviewStore
from workline.store import ProjectStore
from workline.validate import validate_project

FORM_L = dict(checkout.FORM_L)
PROBE_PATH = review_paths.gate_rel("rr_01ARZ3NDEKTSV4RRFFQ69G5FAV", 1)
UNSET_DRIVER = "[filter \"unset\"]\n\tsmudge = sed s/a/X/g\n\tclean = cat\n"


def review_records(store) -> list[str]:
    return [p for p in git(store.root, "ls-tree", "-r", "--name-only", "HEAD", "--", ".workline/review").split()]


def review_files(store) -> list[str]:
    """Every Review record file in the working tree (a fixture's attributes file is not one)."""
    folder = store.root / ".workline" / "review"
    return sorted(p.relative_to(store.root).as_posix() for p in folder.rglob("*.yaml")) if folder.exists() else []


@contextmanager
def environment(env: dict | None):
    """``env`` over the process environment; a system configuration given there is read (GIT_CONFIG_NOSYSTEM unset)."""
    with mock.patch.dict(os.environ, env or {}):
        if env and "GIT_CONFIG_SYSTEM" in env:
            os.environ.pop("GIT_CONFIG_NOSYSTEM", None)
        yield


class _CheckoutCase(PlanningTestCase):
    def evaluations(self, store, relatives=(PROBE_PATH,)) -> dict[str, dict[str, str]]:
        """What the production committed (layer 3) and effective (layer 4) evaluations print for a Review path."""
        captured: dict[str, dict[str, str]] = {}
        real = checkout._printed_problems

        def spy(printed, described):
            captured["committed" if "committed" in described else "effective"] = next(iter(printed.values()))
            return real(printed, described)

        head = self.head(store)
        with mock.patch.object(checkout, "_printed_problems", spy):
            for layer in (lambda: checkout.require_committed_evaluation(store, head, list(relatives)),
                          lambda: checkout.require_effective_evaluation(store, list(relatives))):
                try:
                    layer()
                except StopError:
                    pass
        return captured

    def refused_at_the_freeze(self, store, code: str = "review_checkout_unsafe") -> StopError:
        reviewer = Reviewer()
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(store, reviewer)
        self.assertEqual(code, raised.exception.code)
        self.assertEqual([], review_files(store), "no Review record")
        self.assertEqual([], reviewer.tasks)
        self.assertEqual([], [r for r in self.pending(store) if r["invocation"].get("operation") == "roadmap-create"],
                         "the planning mutation abandoned")
        self.assertFalse(any((store.root / ".workline" / "roadmaps").glob("*.md")), "nothing written")
        return raised.exception

    def assert_clone_keeps_every_record(self, source: Path, name: str, *config: str, env: dict | None = None) -> None:
        with environment(env):
            clone = self.fresh_clone(source, name, *config)
        records = review_records(clone)
        self.assertTrue(records)
        for relative in records:
            self.assertEqual(blob_at(clone, "HEAD", relative), (clone.root / relative).read_bytes(), relative)


class NoRuleTests(_CheckoutCase):
    def test_core_autocrlf_with_no_attributes_file_at_all_is_refused_at_the_freeze(self) -> None:
        store = self.new_project()  # no .gitattributes anywhere
        self.assertFalse((store.root / ".gitattributes").exists())
        git(store.root, "config", "core.autocrlf", "true")
        self.assertIn("root .gitattributes", str(self.refused_at_the_freeze(store)))

    def test_core_autocrlf_with_no_rule_is_refused_at_the_freeze(self) -> None:
        store = self.planning_project(attributes="* text=auto\n")
        git(store.root, "config", "core.autocrlf", "true")
        self.refused_at_the_freeze(store)

    def test_a_rule_only_in_info_attributes_fails_layer_1(self) -> None:
        store = self.planning_project(attributes="* text=auto\n")
        (store.root / ".git" / "info").mkdir(exist_ok=True)
        (store.root / ".git" / "info" / "attributes").write_text(CANONICAL_RULE + "\n", encoding="utf-8", newline="\n")
        self.assertIn("root .gitattributes", str(self.refused_at_the_freeze(store)))


class CanonicalSourceTests(_CheckoutCase):
    def test_a_the_canonical_rule_passes_every_layer_and_a_run_completes_under_autocrlf(self) -> None:
        store = self.planning_project(attributes="* text=auto\n*.png binary\n" + CANONICAL_RULE + "\n")
        git(store.root, "config", "core.autocrlf", "true")
        self.assertEqual({"committed": FORM_L, "effective": FORM_L}, self.evaluations(store))
        result = self.reviewed_roadmap(store)
        self.assertEqual("registered", result.status)
        context = ReviewStore(store).read_task_input(
            self.chain(store, result.review_run_id).generations[0].accepted_tasks[0]["task_id"]).request_envelope["context"]
        self.assertEqual(checkout.CHECKOUT_CONTRACT, context["checkout_capability"])
        self.assert_clone_keeps_every_record(store.root, "clone", "core.autocrlf=true")


class LiteralLookalikeTests(_CheckoutCase):
    """B, C, D, E: a literal value in place of a state prints what the state prints, and layer 1 refuses it."""

    def refused(self, rule: str, printed: dict | None = None) -> None:
        store = self.planning_project(f"p{abs(hash(rule)) % 100000}", attributes=rule + "\n")
        if printed is not None:
            self.assertEqual({"committed": printed, "effective": printed}, self.evaluations(store))
        self.refused_at_the_freeze(store)

    def test_b_a_literal_filter(self) -> None:
        self.refused(CANONICAL_RULE.replace("-filter", "filter=unset"), FORM_L)

    def test_c_a_literal_ident(self) -> None:
        self.refused(CANONICAL_RULE.replace("-ident", "ident=unset"), FORM_L)

    def test_d_a_literal_working_tree_encoding(self) -> None:
        self.refused(CANONICAL_RULE.replace("-working-tree-encoding", "working-tree-encoding=unset"), FORM_L)

    def test_e_text_lookalikes(self) -> None:
        for replacement, text in (("-text", "unset"), ("text=unset", "unset"), ("text=unspecified", "unspecified")):
            with self.subTest(replacement):
                self.refused(CANONICAL_RULE.replace("!text", replacement), {**FORM_L, "text": text})

    def test_a_nul_byte_before_the_canonical_rule_fails_layer_1(self) -> None:
        store = self.planning_project("nulbyte", attributes=b"\0\n" + CANONICAL_RULE.encode() + b"\n")
        self.assertEqual({name: "unspecified" for name in checkout.ATTRIBUTES}, self.evaluations(store)["committed"])
        self.assertIn("NUL", str(self.refused_at_the_freeze(store)))


class FormBTests(_CheckoutCase):
    FORM_B = {"text": "unset", "eol": "unspecified", "filter": "unset", "ident": "unset", "working-tree-encoding": "unset"}

    def test_form_b_is_printed_and_refused(self) -> None:
        store = self.planning_project(attributes="* text=auto\n.workline/review/** -text -filter -ident -working-tree-encoding\n")
        self.assertEqual({"committed": self.FORM_B, "effective": self.FORM_B}, self.evaluations(store))
        self.refused_at_the_freeze(store)


class DeeperOverrideTests(_CheckoutCase):
    """F: any .gitattributes below .workline/ fails layer 2, whatever the evaluations print."""

    def refused_with(self, relative: str, text: str, printed: dict[str, str] | None,
                     first: str = "review_checkout_unsafe") -> None:
        store = self.planning_project(f"d{abs(hash(relative + text)) % 100000}")
        target = store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        git(store.root, "add", "-f", "--", relative)
        git(store.root, "commit", "-q", "-m", "a deeper attributes file")
        if printed is not None:
            self.assertEqual(printed, self.evaluations(store)["committed"])
        with self.assertRaises(StopError) as layer_2:
            checkout.require_no_deeper_attributes(store.root, self.head(store))
        self.assertEqual("review_checkout_unsafe", layer_2.exception.code)
        self.assertIn("below .workline/", str(layer_2.exception))
        self.refused_at_the_freeze(store, first)

    def test_f_asking_eol_crlf(self) -> None:
        self.refused_with(".workline/.gitattributes", "* eol=crlf\n", {**FORM_L, "eol": "crlf"})

    def test_f_holding_a_comment_only(self) -> None:
        self.refused_with(".workline/.gitattributes", "# nothing\n", FORM_L)

    def test_f_a_gates_directory_asking_a_literal_filter(self) -> None:
        # the file also sits in the Review namespace, whose readability discovery checks first (§12.2 step 1)
        self.refused_with(".workline/review/gates/.gitattributes", "*.yaml filter=unset\n", FORM_L,
                          "review_namespace_unreadable")

    def test_f_the_case_variant(self) -> None:
        self.refused_with(".workline/.GITATTRIBUTES", "* eol=crlf\n", None)


class RuleAfterTests(_CheckoutCase):
    """G, H: another attribute rule after the canonical one fails layer 1; comments and blank lines do not."""

    def test_g_a_rule_after_it(self) -> None:
        for after, printed in (("*.png binary", FORM_L), ("* text=auto", {**FORM_L, "text": "auto"})):
            with self.subTest(after):
                store = self.planning_project(f"g{abs(hash(after)) % 100000}", attributes=CANONICAL_RULE + "\n" + after + "\n")
                self.assertEqual(printed, self.evaluations(store)["committed"])
                self.refused_at_the_freeze(store)

    def test_h_comments_and_blank_lines_after_it(self) -> None:
        store = self.planning_project(attributes=CANONICAL_RULE + "\n\n# a comment\n   # an indented comment\n\t\n")
        checkout.require_checkout_capability(store, [PROBE_PATH])
        self.assertEqual("registered", self.reviewed_roadmap(store).status)


class HostileConfigurationTests(_CheckoutCase):
    """I: hostile global and system configuration; the in-tree canonical rule outranks all of it."""

    RULES = {
        "eol": "*.yaml eol=crlf",
        "filter with a driver unset": "*.yaml filter=unset",
        "ident": "*.yaml ident",
        "working-tree-encoding": "*.yaml working-tree-encoding=UTF-16",
        "text eol": "*.yaml text eol=crlf",
        "crlf": "*.yaml crlf",
        "-crlf": "*.yaml -crlf",
        "crlf=input": "*.yaml crlf=input",
    }

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()
        self.assertEqual("registered", self.reviewed_roadmap(self.store).status)
        self.relatives = review_records(self.store)

    def configuration(self, name: str, rules: list[str], *, all_at_once: bool, driver: bool, scope: str) -> dict:
        folder = self.tmp / f"config-{name}"
        folder.mkdir()
        attributes = folder / "attributes"
        attributes.write_text("\n".join(rules) + "\n", encoding="utf-8", newline="\n")
        core = "\tautocrlf = false\n\teol = crlf\n" if all_at_once else "\tautocrlf = true\n"
        text = f"[core]\n{core}\tattributesFile = {attributes.as_posix()}\n" + (UNSET_DRIVER if driver else "")
        config = folder / "gitconfig"
        config.write_text(text, encoding="utf-8", newline="\n")
        return {"GIT_CONFIG_GLOBAL": str(config)} if scope == "global" else {"GIT_CONFIG_SYSTEM": str(config)}

    def check(self, name: str, rules: list[str], *, all_at_once: bool = False, driver: bool = False,
              scope: str = "global") -> None:
        env = self.configuration(name, rules, all_at_once=all_at_once, driver=driver, scope=scope)
        with environment(env):
            if scope == "system":
                self.assertNotIn("GIT_CONFIG_NOSYSTEM", os.environ, "the system configuration is read")
            self.assertEqual({"committed": FORM_L, "effective": FORM_L}, self.evaluations(self.store, self.relatives))
            if driver:
                # §14.5 layer 4: a filter driver named unset is configured, so the printed form L proves nothing here
                with self.assertRaises(StopError) as raised:
                    checkout.require_checkout_capability(self.store, self.relatives)
                self.assertEqual("review_checkout_unsafe", raised.exception.code)
                self.assertIn("filter driver named unset", str(raised.exception))
            else:
                checkout.require_checkout_capability(self.store, self.relatives)
        self.assert_clone_keeps_every_record(self.store.root, f"clone-{name}", env=env)

    def test_i_each_hostile_global_rule_under_core_autocrlf(self) -> None:
        for described, rule in self.RULES.items():
            with self.subTest(described):
                self.check(described.replace(" ", "-"), [rule], driver="driver" in described)

    def test_i_all_at_once_as_global_and_as_system_configuration(self) -> None:
        for scope in ("global", "system"):
            with self.subTest(scope):
                self.check(f"all-{scope}", list(self.RULES.values()), all_at_once=True, driver=True, scope=scope)
                self.check(f"all-no-driver-{scope}", list(self.RULES.values()), all_at_once=True, scope=scope)


class InfoAttributesTests(_CheckoutCase):
    """J: this repository's info/attributes is covered by the effective evaluation."""

    def local_rule(self, store, rule: str) -> None:
        info = store.root / ".git" / "info"
        info.mkdir(exist_ok=True)
        (info / "attributes").write_text(rule + "\n", encoding="utf-8", newline="\n")

    def test_j_an_eol_override(self) -> None:
        store = self.planning_project()
        self.local_rule(store, ".workline/review/** eol=crlf")
        self.assertEqual({**FORM_L, "eol": "crlf"}, self.evaluations(store)["effective"])
        self.refused_at_the_freeze(store)

    def test_j_a_literal_filter_with_a_driver_unset(self) -> None:
        store = self.planning_project()
        self.local_rule(store, ".workline/review/** filter=unset")
        git(store.root, "config", "filter.unset.smudge", "sed s/a/X/g")
        self.assertEqual(FORM_L, self.evaluations(store)["effective"])
        with self.assertRaises(StopError) as raised:
            checkout.require_checkout_capability(store, [PROBE_PATH])
        self.assertEqual("review_checkout_unsafe", raised.exception.code)
        self.assertIn("filter driver named unset", str(raised.exception))
        # at the freeze the transform preflight (§14.3 part 1) refuses the same driver first, before any write
        self.refused_at_the_freeze(store, "review_git_transform")

    def test_j_a_literal_filter_with_no_driver_selects_nothing(self) -> None:
        store = self.planning_project()
        self.local_rule(store, ".workline/review/** filter=unset")
        checkout.require_checkout_capability(store, [PROBE_PATH])
        self.assertEqual("registered", self.reviewed_roadmap(store).status)


class LiteralFilterExploitTests(_CheckoutCase):
    def test_k_the_committed_literal_would_change_a_clones_bytes_so_it_is_refused(self) -> None:
        source = self.planning_project("canonical")
        self.assertEqual("registered", self.reviewed_roadmap(source).status)
        record = review_records(source)[0]
        literal = self.planning_project("literal", attributes=CANONICAL_RULE.replace("-filter", "filter=unset") + "\n")
        target = literal.root / record
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob_at(source, "HEAD", record))
        self.commit_all(literal, "a Review record under the literal rule", record)
        config = self.tmp / "driver.gitconfig"
        config.write_text(UNSET_DRIVER, encoding="utf-8", newline="\n")
        env = {"GIT_CONFIG_GLOBAL": str(config)}
        with mock.patch.dict(os.environ, env):
            self.assertEqual({"committed": FORM_L, "effective": FORM_L}, self.evaluations(literal))
            with self.assertRaises(StopError) as raised:
                checkout.require_raw_source(literal.root, self.head(literal))
            self.assertEqual("review_checkout_unsafe", raised.exception.code)
            clone = self.fresh_clone(literal.root, "literal-clone")
        self.assertNotEqual(blob_at(clone, "HEAD", record), (clone.root / record).read_bytes(), "the driver changed it")
        self.assert_clone_keeps_every_record(source.root, "canonical-clone", env=env)


class RedirectAndUnknownTests(_CheckoutCase):
    def test_an_attribute_source_redirect(self) -> None:
        for described, setup, env in (
            ("attr.tree", lambda store: git(store.root, "config", "attr.tree", "HEAD~1"), {}),
            ("GIT_ATTR_SOURCE", lambda store: None, {"GIT_ATTR_SOURCE": "HEAD~1"}),
        ):
            with self.subTest(described):
                store = self.planning_project(described.replace(".", "-").lower())
                setup(store)
                with mock.patch.dict(os.environ, env):
                    self.assertEqual({name: "unspecified" for name in checkout.ATTRIBUTES}, self.evaluations(store)["effective"])
                    self.refused_at_the_freeze(store)

    def test_check_attr_unanswerable_or_the_attributes_blob_unreadable_is_unknown(self) -> None:
        store = self.planning_project()
        with mock.patch.object(gitcmd, "check_attributes", lambda *args, **kwargs: None):
            with self.assertRaises(StopError) as raised:
                checkout.require_checkout_capability(store, [PROBE_PATH])
            self.assertEqual("review_checkout_unknown", raised.exception.code)
            with mock.patch.object(gitops, "require_no_planning_transform", lambda repo, paths: None):
                self.refused_at_the_freeze(store, "review_checkout_unknown")
        real = gitcmd.read_blob
        attributes_blob = git(store.root, "rev-parse", "HEAD:.gitattributes").strip()
        with mock.patch.object(gitcmd, "read_blob", lambda repo, oid: None if oid == attributes_blob else real(repo, oid)):
            self.refused_at_the_freeze(store, "review_checkout_unknown")


class FreshCloneTests(_CheckoutCase):
    def test_a_fresh_clone_keeps_lf_reads_everything_and_passes_the_next_call(self) -> None:
        source = self.planning_project()
        first = self.reviewed_roadmap(source)
        config = self.tmp / "crlf.gitconfig"
        attributes = self.tmp / "crlf.attributes"
        attributes.write_text("*.yaml eol=crlf\n", encoding="utf-8", newline="\n")
        config.write_text(f"[core]\n\tattributesFile = {attributes.as_posix()}\n", encoding="utf-8", newline="\n")
        for name, clone_config, env in (("autocrlf", ("core.autocrlf=true",), {}),
                                        ("global-eol", (), {"GIT_CONFIG_GLOBAL": str(config)})):
            with self.subTest(name):
                self.assert_clone_keeps_every_record(source.root, name, *clone_config, env=env)
                clone = ProjectStore(self.tmp / name)
                git(clone.root, "remote", "remove", "origin")
                self.assertIsNotNone(ReviewStore(clone).gate_chain(first.review_run_id), "earlier Runs stay readable")
                self.assertEqual([], validate_project(clone))
                self.enter(clone.root)
                with mock.patch.dict(os.environ, env):
                    result = self.reviewed_roadmap(clone, Reviewer(), plan(f"A Roadmap In {name}"))
                self.assertEqual("registered", result.status)

    def test_unsafe_semantics_are_never_normalized(self) -> None:
        source = self.planning_project()
        self.reviewed_roadmap(source)
        clone = self.fresh_clone(source.root, "clone")
        git(clone.root, "remote", "remove", "origin")
        (clone.root / ".git" / "info").mkdir(exist_ok=True)
        (clone.root / ".git" / "info" / "attributes").write_text(".workline/review/** eol=crlf\n", encoding="utf-8")
        for relative in review_records(clone):
            (clone.root / relative).unlink()
        git(clone.root, "checkout", "--", ".workline/review")
        record = review_records(clone)[0]
        crlf = (clone.root / record).read_bytes()
        self.assertIn(b"\r\n", crlf)
        self.enter(clone.root)
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(clone, Reviewer(), plan("Another Roadmap"))
        self.assertEqual("review_namespace_unreadable", raised.exception.code)
        self.assertEqual("review_record_noncanonical", raised.exception.__cause__.code)
        self.assertEqual(crlf, (clone.root / record).read_bytes(), "no byte rewritten")


class CheckedOutBeforeTheRuleTests(_CheckoutCase):
    def test_a_record_checked_out_before_the_rule_is_refused_and_never_normalized(self) -> None:
        source = self.planning_project()
        self.reviewed_roadmap(source)
        self.commit_attributes(source, "* text=auto\n", message="the Review rule removed")
        clone = self.fresh_clone(source.root, "clone", "core.autocrlf=true")  # checked out with no Review rule
        record = review_records(clone)[0]
        crlf = (clone.root / record).read_bytes()
        self.assertIn(b"\r\n", crlf, "the checkout converted the record")
        self.commit_attributes(source, "* text=auto\n" + CANONICAL_RULE + "\n", message="the Review rule back")
        git(clone.root, "pull", "-q", "--ff-only")  # the rule arrives; the unchanged record is not checked out again
        self.assertTrue(blob_at(clone, "HEAD", ".gitattributes").endswith(CANONICAL_RULE.encode("utf-8") + b"\n"),
                        "HEAD's committed root .gitattributes ends with the canonical rule again")
        self.assertEqual(crlf, (clone.root / record).read_bytes())
        git(clone.root, "remote", "remove", "origin")
        self.enter(clone.root)
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(clone, Reviewer(), plan("Another Roadmap"))
        self.assertEqual("review_namespace_unreadable", raised.exception.code)
        self.assertEqual("review_record_noncanonical", raised.exception.__cause__.code)
        self.assertEqual(crlf, (clone.root / record).read_bytes(), "no byte rewritten or normalized")


class RuleRemovedTests(_CheckoutCase):
    def test_the_rule_removed_after_generation_1_stops_the_next_review_stage_and_the_run_continues_once_back(self) -> None:
        store = self.planning_project()
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        self.commit_attributes(store, "* text=auto\n")
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(store)
        self.assertEqual("review_checkout_unsafe", raised.exception.code)
        (pending,) = [r for r in self.pending(store) if r["invocation"].get("operation") == "roadmap-create"]
        self.assertEqual("pending", pending["status"])
        self.commit_attributes(store, "* text=auto\n" + CANONICAL_RULE + "\n")
        self.assertEqual("registered", self.reviewed_roadmap(store).status)


class TransformPreflightTests(_CheckoutCase):
    def test_a_committed_literal_filter_on_a_registration_path(self) -> None:
        attributes = "*.md filter=unset\n" + CANONICAL_RULE + "\n"
        with_driver = self.planning_project("driver", attributes=attributes)
        git(with_driver.root, "config", "filter.unset.clean", "cat")
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(with_driver)
        self.assertEqual("review_git_transform", raised.exception.code)
        self.assertEqual((), run_ids(with_driver))
        without = self.planning_project("plain", attributes=attributes)
        self.assertEqual("registered", self.reviewed_roadmap(without).status)


class LegacyTests(_CheckoutCase):
    def test_legacy_planning_evaluates_nothing_and_refuses_nothing_without_the_rule(self) -> None:
        store = self.new_project()
        with mock.patch.object(checkout, "require_checkout_capability", side_effect=AssertionError("evaluated")), \
                mock.patch.object(gitcmd, "check_attributes", side_effect=AssertionError("check-attr ran")):
            created = rm.create_roadmap(store, plan())
            rm.enter_phase(store, created.phase_ids["a"], design())
        self.assertFalse((store.root / ".workline" / "review").exists())


if __name__ == "__main__":
    unittest.main()
