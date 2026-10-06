"""P6 §30.33: the canonical runtime authority (Skills, rules/git) carries P6 - and the identities it binds are pinned.

* the P6 Review Policy block in ``skills/review`` equals ``p4.P6_POLICY_RECORD`` byte for byte, after the P5 block;
* the review Skill names every P6 code and reason; the roadmap / start Skills state the P6 owner duties inside their
  Review-v1 sections; the project-router states the BL-055 wording outcomes; rules/git states the exact Profile CAS
  and publication contract; no Skill or routing entry is added;
* RB6B-M5: the meta-rules, the P6 family policy record and the loader semantics identity are pinned as literals, so
  any change to them forces a new identity rather than a silent reclassification of stored P6 Runs.
"""

from __future__ import annotations

import ast
import re
import unittest

from helpers import WORKLINE_ROOT
from workline.review import history, p4, policy, serialize

#: RB6B-M5 literal pins. Changing any of these changes what every stored P6 Run binds: a new identity is due.
META_RULES_DIGEST = "01fb30c824b82a2dbb8aebd20943815d78dd2546f8610dba57e66517255e20a5"
P6_FAMILY_POLICY_HASH = "38f548c24aa086d18ee37b9229a38f19a53893d23349be6caf7479ca14c63e6b"
LOADER_SEMANTICS_IDENTITY = "review-v1-p6-policy-loader-v1"


def read(*parts: str) -> str:
    return WORKLINE_ROOT.joinpath(*parts).read_text(encoding="utf-8").replace("\r\n", "\n")


def section(text: str, start: str, end: str | None) -> str:
    begin = text.index(start)
    return text[begin:] if end is None else text[begin:text.index(end, begin)]


class IdentityPinTests(unittest.TestCase):
    def test_the_p6_identities_are_pinned_literals(self) -> None:
        self.assertEqual(META_RULES_DIGEST, policy.meta_rules_digest())
        self.assertEqual(P6_FAMILY_POLICY_HASH, p4.family_policy_hash(p4.P6_POLICY_ID))
        self.assertEqual(LOADER_SEMANTICS_IDENTITY, policy.LOADER_SEMANTICS_IDENTITY)


class ReviewSkillTests(unittest.TestCase):
    def test_the_p6_policy_block_equals_the_code_constant_and_follows_the_p5_block(self) -> None:
        text = read(".claude", "skills", "review", "SKILL.md")
        heading = text.index("## P6 Review Policy")
        self.assertLess(text.index("## P5 Review Policy"), text.index("## P6 Project-local Adaptive Policy"))
        self.assertLess(text.index("## P6 Project-local Adaptive Policy"), heading)
        block = re.search(r"```yaml\n(.*?)```", text[heading:], re.S)
        self.assertIsNotNone(block)
        self.assertEqual(serialize.canonical_text(p4.P6_POLICY_RECORD), block.group(1))
        p5 = re.search(r"```yaml\n(.*?)```", text[text.index("## P5 Review Policy"):], re.S)
        self.assertEqual(serialize.canonical_text(p4.P5_POLICY_RECORD), p5.group(1), "the P5 block is unchanged")

    def test_the_review_skill_names_every_p6_code_reason_and_rule(self) -> None:
        text = section(read(".claude", "skills", "review", "SKILL.md"), "## P6 Project-local Adaptive Policy",
                       "## P6 Review Policy")
        for name in policy.STOP_CODES + policy.RECONCILE_REASONS + policy.VALIDATION_CODES:
            with self.subTest(name=name):
                self.assertIn(f"`{name}`", text)
        for phrase in (policy.SURFACE_REQUIRED_SLOTS, policy.SURFACE_EXTRA_SCOPE_STEPS, "`replace_review_profile`",
                       "`.workline/review/policy/project-profile.yaml`", "`project-policy-change`", policy.REVIEW_KIND,
                       policy.TARGET_IDENTITY, policy.AUTHORIZED_OPERATION_STAGE, policy.POLICY_CHANGE_CONTRACT,
                       p4.P6_POLICY_ID, "R6-1", "R6-2", "derived-baseline", "holdout", "`retain`", "`inconclusive`",
                       "temporary_guard", "`proven_disjoint`", "backfill"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


class OwnerSkillTests(unittest.TestCase):
    PHRASES = ("R6-1", p4.P6_POLICY_ID, "`holdout_discovery`", "`review_p6_discovery_slots_unmet`",
               "`review_p6_holdout_unbound`", "`review_p6_holdout_unsettled`", "`review_p6_holdout_failed`",
               "`review_p6_profile_incompatible`", "`review_p6_lineage_invalid`", "`review.reverification.extra_scope_steps`",
               "open Runは途中でpolicyを変えない",
               # RB6FR2B-1: a successor keeps the cycle's family policy and freezes its OWN Effective Policy (§30.6)
               "修理の後継とHuman decisionでの新しいRunはcycleの最初のRunのpolicy（family）を保ち、自分のEffective Policyを"
               "開始時に新しく解決して凍結する（cycleの最初のRunのEffective Policyは引き継がない）")
    #: RB6FR2B-1: the clause the code contradicts never comes back.
    FORBIDDEN = ("cycleの最初のRunのpolicyとそのEffective Policyを保ち",)

    def test_the_roadmap_skill_states_p6_inside_its_review_v1_section(self) -> None:
        planning = section(read(".claude", "skills", "roadmap", "SKILL.md"), "## Review-v1 planning", "## Mutation / Git")
        for phrase in self.PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, planning)
        for phrase in self.FORBIDDEN:
            with self.subTest(forbidden=phrase):
                self.assertNotIn(phrase, read(".claude", "skills", "roadmap", "SKILL.md"))

    def test_the_start_skill_states_p6_inside_its_review_v1_section(self) -> None:
        work = section(read(".claude", "skills", "start", "SKILL.md"), "## Review-v1 Work", "## outer continuation")
        for phrase in self.PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, work)
        for phrase in self.FORBIDDEN:
            with self.subTest(forbidden=phrase):
                self.assertNotIn(phrase, read(".claude", "skills", "start", "SKILL.md"))


class RulesAndRouterTests(unittest.TestCase):
    def test_rules_git_states_the_exact_profile_cas_and_publication_contract(self) -> None:
        registry = read("registry.md")
        rules = section(registry, "<!-- workline-id: rules/git -->", "<!-- workline-id: rules/ai-decision -->")
        for phrase in ("`project-policy-change`", "`replace_review_profile`", "`.workline/review/policy/project-profile.yaml`",
                       policy.POLICY_PUBLICATION_CONTRACT, "`base_exact`", "`rules/human-confirmation`"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rules)
        self.assertNotIn("skills/project-policy", registry, "no new routing entry")

    def test_the_router_resolves_noncanonical_wording_by_meaning(self) -> None:
        router = read(".claude", "skills", "project-router", "SKILL.md")
        self.assertLess(router.index("## 選択の失敗"), router.index("## 非canonicalな言い回し"))
        self.assertLess(router.index("## 非canonicalな言い回し"), router.index("## canonical implementation first"))


#: The P6 producers: whole modules, or the P6 functions of shared modules (the scan the P2 catalogue sets P6 apart for).
P6_PRODUCERS = {
    ("review", "policy.py"): None,
    ("project_policy.py",): None,
    ("mutation.py",): {"_guard_policy_record", "_validate_profile_replacement", "_classify_profile_replacement",
                       "_replace_review_profile", "bind_policy_recovery", "_policy_publication"},
    ("review", "recovery.py"): {"discover_kind", "p4_reconstruction_problem"},
    ("review", "publication.py"): {"policy_change_adders", "policy_namespace_adders", "committed_policy_proof",
                                   "_prove_policy", "consumptions_mentioning", "committed_policy_state_problem"},
    # RB6FR3-3: the P6 functions of p4.py (the frozen Effective Policy reader, the reverification holdout) and of
    # review/validate.py (the policy record and compatibility Problems, which it constructs as ``ReviewProblem``)
    ("review", "p4.py"): {"effective_policy_of_envelope", "repair_result"},
    ("review", "validate.py"): {"_policy_records", "_policy_compatibility"},
}
#: Where a bare ``CODE_*`` / ``REASON_*`` name resolves: the scanned module's own constants (p4.py has its own).
_LOCAL_CONSTANTS = {("review", "p4.py"): p4}
#: ORCH-RB6-1-R11: the functions whose returned ``(code, message)`` a producer raises as ``stop(*problem)``.
STARRED_SOURCES = {"surface_problem", "discovery_slots_problem"}
#: The pre-P6 codes / reasons the P6 owner reuses unchanged (each exists at the base commit 61b0b9dd).
SHARED_PRE_P6 = {"detached_head", "review_contract_invalid", "review_not_persisted", "review_persistence_unknown",
                 "review_reviewer_failed", "review_reviewer_mismatch", "review_recovery_reservation_conflict",
                 "review_recovery_incomplete", "review_record_invalid",
                 # RB6FR3-3: review/validate.py's pre-P6 record conflict Problem (21 uses at 61b0b9dd)
                 "review_record_conflict"}
P6_OWNER_CODE = "review_policy_owner"
_MODULES = {"policy": policy, "review_policy": policy, "p4": p4, "history": history}


def _resolve(node: ast.AST, local: object = policy) -> set[str] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        body, orelse = _resolve(node.body, local), _resolve(node.orelse, local)
        return None if body is None or orelse is None else body | orelse
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in _MODULES:
        found = getattr(_MODULES[node.value.id], node.attr, None)
        return {found} if isinstance(found, str) else None
    if isinstance(node, ast.Name) and node.id.startswith(("CODE_", "REASON_")):
        found = getattr(local, node.id, None)
        return {found} if isinstance(found, str) else None
    return None


def _call_name(node: ast.Call) -> str | None:
    return node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)


def _starred_source(function: ast.AST, call: ast.Call) -> bool:
    """Whether ``stop(*name)`` in ``function`` raises what one of :data:`STARRED_SOURCES` returned into ``name``."""
    starred = call.args[0].value
    if not isinstance(starred, ast.Name):
        return False
    return any(isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == starred.id
                                                     for target in node.targets)
               and isinstance(node.value, ast.Call) and _call_name(node.value) in STARRED_SOURCES
               for node in ast.walk(function))


def _outside_functions(tree: ast.Module) -> list[ast.AST]:
    """ORCH-RB6-1-N6: every node of a module outside its function definitions - module- and class-level statements
    and module-level lambdas - so a raising call there is scanned too."""
    found: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            found.append(child)
            visit(child)

    visit(tree)
    return found


def p6_raised() -> tuple[set[str], list[str]]:
    """Every reason / code the P6 producers raise, and what the scan cannot resolve (beyond pass-through helpers)."""
    found: set[str] = set()
    unresolved: list[str] = []
    for parts, functions in P6_PRODUCERS.items():
        path = WORKLINE_ROOT.joinpath("src", "workline", *parts)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        scopes = [tree] if functions is None else [node for node in ast.walk(tree)
                                                   if isinstance(node, ast.FunctionDef) and node.name in functions]
        if functions is not None:
            assert {scope.name for scope in scopes} == functions, f"{path.name}: {functions}"
        for scope in scopes:
            # a function: its own body; a whole module: each function's body, then everything outside every function
            enclosing = [(scope, list(ast.walk(scope)))] if isinstance(scope, ast.FunctionDef) else [
                (node, list(ast.walk(node))) for node in ast.walk(scope)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))] + [(scope, _outside_functions(scope))]
            for function, nodes in enclosing:
                for node in nodes:
                    if not isinstance(node, ast.Call):
                        continue
                    name = _call_name(node)
                    values: list[ast.AST] = []
                    if name == "ReconcileRequired":
                        values += [keyword.value for keyword in node.keywords if keyword.arg == "reason"]
                    elif name in ("StopError", "ValidationError"):
                        values += [keyword.value for keyword in node.keywords if keyword.arg == "code"]
                    elif name in ("_reconcile", "reconcile", "_invalid"):
                        if len(node.args) >= 2:
                            values.append(node.args[1])
                        # ORCH-RB6-1-R11: a keyword code too
                        values += [keyword.value for keyword in node.keywords if keyword.arg == "code"]
                    elif name == "stop" and node.args:
                        if isinstance(node.args[0], ast.Starred):
                            # ORCH-RB6-1-R11: stop(*problem) - its codes are the starred source's (scanned below)
                            if not _starred_source(function, node):
                                unresolved.append(f"{path.name}:{node.lineno} (stop(*...) of an unknown source)")
                            continue
                        values.append(node.args[0])
                    elif name == "ReviewProblem" and node.args:
                        values.append(node.args[0])  # RB6FR3-3: review/validate.py's Problem constructor
                    for value in values:
                        if isinstance(value, ast.Name) and value.id in ("code", "reason"):
                            continue  # a helper passing its caller's code / reason on: every call of it is scanned
                        resolved = _resolve(value, _LOCAL_CONSTANTS.get(parts, policy))
                        if resolved is None:
                            unresolved.append(f"{path.name}:{node.lineno}")
                        else:
                            found |= resolved
    return found, unresolved


def starred_source_codes() -> tuple[set[str], list[str]]:
    """The codes :data:`STARRED_SOURCES` return as the first element of their ``(code, message)`` tuples."""
    tree = ast.parse(WORKLINE_ROOT.joinpath("src", "workline", "review", "policy.py").read_text(encoding="utf-8"))
    found: set[str] = set()
    unresolved: list[str] = []
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in STARRED_SOURCES]
    assert {function.name for function in functions} == STARRED_SOURCES
    for function in functions:
        for node in ast.walk(function):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            if isinstance(node.value, ast.Constant) and node.value.value is None:
                continue
            resolved = _resolve(node.value.elts[0]) if isinstance(node.value, ast.Tuple) and node.value.elts else None
            if resolved is None:
                unresolved.append(f"policy.py:{node.lineno}")
            else:
                found |= resolved
    return found, unresolved


class P6CatalogueScanTests(unittest.TestCase):
    """The positive P6 equivalent of the P2 catalogue scan, which sets the P6 family apart (CP condition 1)."""

    def test_every_code_and_reason_a_p6_producer_raises_is_catalogued(self) -> None:
        found, unresolved = p6_raised()
        self.assertEqual([], unresolved, "a reason / code the scan cannot resolve")
        starred, starred_unresolved = starred_source_codes()
        self.assertEqual([], starred_unresolved, "a starred source returns a code the scan cannot resolve")
        found |= starred
        catalogue = set(policy.STOP_CODES) | set(policy.RECONCILE_REASONS) | set(policy.VALIDATION_CODES)
        p6 = {value for value in found if value.startswith("review_p6_")}
        self.assertEqual(set(), p6 - catalogue, "a P6 code outside the policy.py catalogues")
        self.assertTrue({policy.REASON_RUN_UNRECOVERED, policy.REASON_PROFILE_BEFORE_MISMATCH,
                         policy.CODE_LINEAGE_INVALID, policy.CODE_DISCOVERY_SLOTS_UNMET,
                         policy.CODE_SURFACE_UNKNOWN} <= p6)
        other = found - p6 - {P6_OWNER_CODE}
        shared = (set(p4.STOP_CODES) | set(p4.RECONCILE_REASONS) | set(history.STOP_CODES)
                  | set(history.RECONCILE_REASONS) | SHARED_PRE_P6)
        self.assertEqual(set(), other - shared, "a non-P6 code a P6 producer raises that is not a pre-P6 code")

    def test_no_p6_code_collides_with_a_p2_p4_or_p5_code(self) -> None:
        from test_review_planning_fold_ins import CATALOGUE_CODES, CATALOGUE_REASONS

        p6 = set(policy.STOP_CODES) | set(policy.RECONCILE_REASONS) | set(policy.VALIDATION_CODES) | {P6_OWNER_CODE}
        earlier = (CATALOGUE_CODES | CATALOGUE_REASONS | set(p4.STOP_CODES) | set(p4.RECONCILE_REASONS)
                   | set(history.STOP_CODES) | set(history.RECONCILE_REASONS) | SHARED_PRE_P6)
        self.assertEqual(set(), p6 & earlier)
        self.assertTrue(all(value.startswith("review_p6_") for value in p6 - {P6_OWNER_CODE}))


if __name__ == "__main__":
    unittest.main()
