"""P7 §31.55 (+ RB7C-5, RB7C-9, AO-2): the ``global-policy-change`` owner persists exactly the reviewed policy.

Static rows (they read the owner's source; nothing is imported):

* the ONE root push point (AO-2): ``gitcmd.push(`` occurs once, inside
  ``_publish``, after the authorization re-validation, the locator re-resolution
  and self-read, the destination read, the fast-forward proof, the dry run, the
  root C-2 proof and the publication barrier, in that order; the refspec is the
  exact ``<sha>:<full ref>``;
* commits are class B commit tree plans (``workcommit.build`` with
  ``ROOT_COMMIT_CONTRACT``, an ``update-ref`` compare-and-swap) - never the real
  index, never force / rebase / reset / amend / cherry-pick / stash;
* no history surface, no Project controller, store or namespace;
* the P7 owner catalogue is spelled once, in the catalogue.

End-to-end rows (§31.55): exact before state, disjoint dirt untouched, owned
dirt blocks before any effect, the Kp three-path delta and its semantic
round-trip, C-2 before any push, the exact refspec, Global Policy Consumption v4
next to the older versions, the Km Consumption delta, remote-less mode, a root
ignore rule on an owned path (RB7C-9), a hostile global configuration (RB7C-5),
the identity-unconfigured root, and the unmocked I-RB7-2 change. Leaf-review
rows: a second request beside a pending Kp (RB7DL-1), publication readiness read
before G4 / the seal (RB7DL-2), a HEAD without a materialized policy (RB7DL-5),
the import DAG by containment (RB7DL-6).
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
import unittest
from unittest import mock

from global_policy_helpers import (
    BRANCH, GLOBAL_POLICY_REL, KG_SUBJECT, KM_SUBJECT, KP_SUBJECT, RUNTIME_DIR, SLOTS, Crash, Discovery,
    GlobalPolicyCase, crash_at, discovery_actors, maintenance, owner, root_review, run_remote_less_change,
)
from helpers import SRC, git
from workline.review import policy, records, serialize
from workline.review.committed import CommittedReviewStore

OWNER_SOURCE = SRC / "workline" / "global_policy.py"
OWNER_TEXT = OWNER_SOURCE.read_text(encoding="utf-8")
OWNER_TREE = ast.parse(OWNER_TEXT)

FROZEN_STOP_CODES = ("review_p7_before_state_conflict", "review_p7_stale_candidate")
#: The whole D catalogue (Amendment 10 item 2): the frozen two and the admitted HEAD-not-materialized STOP; nothing else.
D_STOP_CODES = FROZEN_STOP_CODES + ("review_p7_global_policy_unavailable",)
FROZEN_REASONS = ("review_p7_persisted_mismatch", "review_p7_publication_invalid", "review_p7_run_unrecovered",
                  "review_p7_record_conflict")


def _function(name: str) -> ast.FunctionDef:
    found = [node for node in OWNER_TREE.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(found) != 1:
        raise AssertionError(f"global_policy.py defines {len(found)} top-level functions {name}")
    return found[0]


def _source(node: ast.AST) -> str:
    return ast.get_source_segment(OWNER_TEXT, node) or ""


def _docstring_free(node: ast.FunctionDef) -> str:
    """The function's source without its docstring (a docstring describes; it is not a call)."""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return "\n".join(_source(statement) for statement in body)


def _string_constants(tree: ast.AST) -> list[str]:
    """Every string constant that is not a docstring."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body \
                and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
            docstrings.add(id(node.body[0].value))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]


def _git_arguments(tree: ast.AST) -> list[str]:
    """The first argument of every class B Git call (``<git>.run(`` / ``.run_bytes(`` / ``.execute(``)."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("run", "run_bytes", "execute") and node.args \
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            found.append(node.args[0].value)
    return found


class OnePushPointTests(unittest.TestCase):
    """AO-2: one root push point, holding the authorization, the root proof and the barrier, in the frozen order."""

    ORDER = (
        "root_maintenance.publication_binding(",
        "destination.resolve_active_push_locator(",
        "gitcmd.reads_itself(",
        "gitcmd.destination_branch(",
        "gitcmd.descends_from(",
        "gitcmd.push_dry_run(",
        "_require_root_proof(",
        "publication.require_barrier_clear(",
        "gitcmd.push(",
    )

    def test_the_owner_pushes_at_exactly_one_place_inside_publish(self) -> None:
        self.assertEqual(1, OWNER_TEXT.count("gitcmd.push("), "one root push point")
        publish = _docstring_free(_function("_publish"))
        self.assertEqual(1, publish.count("gitcmd.push("))
        for node in OWNER_TREE.body:
            if isinstance(node, ast.FunctionDef) and node.name != "_publish":
                with self.subTest(function=node.name):
                    self.assertNotIn("gitcmd.push(", _source(node))

    def test_every_check_runs_before_the_push_in_the_frozen_order(self) -> None:
        publish = _docstring_free(_function("_publish"))
        positions = []
        for item in self.ORDER:
            with self.subTest(call=item):
                self.assertIn(item, publish)
            positions.append(publish.index(item))
        self.assertEqual(sorted(positions), positions, "authorization, locator, destination, fast-forward, dry run, "
                                                       "root proof, barrier, then the push")

    def test_the_refspec_is_the_exact_commit_to_the_full_ref_and_never_forced(self) -> None:
        publish = _docstring_free(_function("_publish"))
        self.assertIn('refspec = f"{commit}:{ref}"', publish)
        self.assertEqual(1, publish.count("refspec ="))
        for forced in ("+{", "--force", "force-with-lease", "--mirror", "--all"):
            with self.subTest(forced=forced):
                self.assertNotIn(forced, OWNER_TEXT)

    def test_the_root_proof_is_the_c2_of_the_stage_the_push_publishes(self) -> None:
        proof = _docstring_free(_function("_require_root_proof"))
        for name in ("_c2_kp(", "_c2_km(", "_c2_evaluation("):
            with self.subTest(proof=name):
                self.assertIn(name, proof)


class ClassBCommitTests(unittest.TestCase):
    """RB7C-5: every root commit is a class B commit tree plan; the real index is never what is committed."""

    def test_commits_are_built_from_plans_and_moved_by_compare_and_swap(self) -> None:
        commit = _docstring_free(_function("_finish_commit"))
        self.assertIn("workcommit.build(", commit)
        self.assertIn('"update-ref", ref, prepared.commit, parent', commit)
        self.assertIn("workcommit.ref_value(", commit)
        self.assertIn("workcommit.refresh_real_index(", commit)
        self.assertLess(commit.index("mutation.mark_effect("), commit.index('"update-ref"'),
                        "the prepared commit is recorded before any ref moves")
        plan = _docstring_free(_function("_commit_plan"))
        self.assertIn("ROOT_COMMIT_CONTRACT", plan)
        self.assertIn("workcommit.CommitTreePlan(", plan)

    def test_the_only_git_commands_are_reads_object_writes_and_the_ref_cas(self) -> None:
        self.assertEqual({"ls-tree", "cat-file", "hash-object", "update-ref"}, set(_git_arguments(OWNER_TREE)))

    def test_a_ref_moved_before_its_fact_is_proven_as_an_object_never_rebuilt(self) -> None:
        """Amendment 10 item 1: tree, one parent and message of the recorded prepared commit, read from the object;
        the admission at resume and the finishing of the commit both require it."""
        proof = _docstring_free(_function("_prepared_object_problem"))
        for read in ('"cat-file", "-t"', '"cat-file", "commit"', "FACT_PREPARED_TREE", 'payload.get("parent")',
                     'payload.get("message")'):
            with self.subTest(read=read):
                self.assertIn(read, proof)
        self.assertIn("_prepared_object_problem(", _docstring_free(_function("_require_resume_basis")))
        commit = _docstring_free(_function("_finish_commit"))
        self.assertLess(commit.index("_prepared_object_problem("), commit.index("workcommit.build("),
                        "an already-moved ref is proven first; only a commit never moved is built")

    def test_no_history_rewrite_and_no_working_tree_commit(self) -> None:
        constants = set(_string_constants(OWNER_TREE))
        # the Git command set itself is pinned exactly above; no history-rewriting word or flag is spelled anywhere
        for word in ("rebase", "reset", "--amend", "amend", "cherry-pick", "stash", "--force", "-f", "--hard",
                     "--force-with-lease"):
            with self.subTest(word=word):
                self.assertNotIn(word, constants)
        for name in ("contained_add", "contained_commit", "commit_only", "add_paths", "MutationController",
                     "_make_planning_commit", "isolated_index_path"):
            with self.subTest(name=name):
                self.assertNotIn(name, OWNER_TEXT)


class BoundaryTests(unittest.TestCase):
    """No history surface, no Project controller / store / namespace, no second chain or discovery."""

    #: §0 Import DAG for D, plus what Amendment 10 admits, by basis. Every relative import D makes is one of these.
    DAG = frozenset({
        # the three leaves D sits on: A, B, C
        "review.namespace", "root_maintenance", "review.global_policy",
        # D's own §0 line
        "review.store", "review.committed", "review.validate", "review.recovery", "review.publication",
        "review.workcommit", "review.hermetic", "gitcmd", "destination", "pushurl", "implementation", "review.planning",
        # Amendment 10 item 4: read-only walk / read_file of the working-tree Global policy
        "review.fsafe",
        # the record layer the A / B / C lines rest on (errors, ids, policy, p4, records, serialize)
        "errors", "ids", "review.p4", "review.policy", "review.records", "review.serialize",
        # review.gate for its pure reservation key builders (§0 bars only next_generation_scope /
        # pending_generation_mutations; the attribute subtest below pins the builders)
        "review.gate",
    })
    #: The names D may use of the modules §0 admits only in part.
    PARTIAL = {
        "planning": {"loader_identity"},
        "gate": {"review_run_key", "review_task_key", "review_receipt_key", "review_consumption_key",
                 "review_finding_key"},
        "fsafe": {"walk"},
    }

    def test_imports_are_contained_in_the_frozen_dag(self) -> None:
        relative: set[str] = set()
        for node in ast.walk(OWNER_TREE):
            if isinstance(node, ast.ImportFrom) and node.level >= 1:
                self.assertEqual(1, node.level, "D imports only from its own package")
                if node.module is None:
                    relative.update(alias.name for alias in node.names)
                elif node.module == "review":
                    relative.update(f"review.{alias.name}" for alias in node.names)
                else:
                    relative.add(node.module)
                if node.module == "implementation":
                    self.assertEqual(["package_directory"], [alias.name for alias in node.names])
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                for name in names:
                    self.assertFalse(name.split(".")[0] == "workline", f"{name}: D imports its package relatively")
        self.assertLessEqual(relative, self.DAG, f"outside the §0 DAG: {sorted(relative - self.DAG)}")
        for module, admitted in self.PARTIAL.items():
            used = {node.attr for node in ast.walk(OWNER_TREE) if isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name) and node.value.id == module}
            with self.subTest(module=module):
                self.assertTrue(used, f"{module} is imported and used")
                self.assertLessEqual(used, admitted)

    def test_imports_stay_inside_the_frozen_dag(self) -> None:
        imported: set[str] = set()
        for node in ast.walk(OWNER_TREE):
            if isinstance(node, ast.ImportFrom):
                imported.add(f"{'.' * node.level}{node.module or ''}")
                imported.update(f"{'.' * node.level}{node.module or ''}:{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        for forbidden in (".review:history", ".review.history", ".mutation", ".project_policy", ".gitops", ".oplock",
                          ".self_hosting", ".roadmap", ".roadmap_review", ".start", ".start_review", ".store",
                          ".:mutation", ".:project_policy", ".:gitops", ".:oplock", ".:store", ".:roadmap",
                          ".:start", ".review:checkout"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, imported)

    def test_no_history_function_and_no_project_only_helper_is_named(self) -> None:
        for name in ("g4_history", "not_authorized_history", "prior_history_references", "prior_history_records",
                     "consumed_run_summary", "require_history_ready", "history.", "next_generation_scope",
                     "pending_generation_mutations", "require_persisted", "validate_settlement(store",
                     "ProjectStore", "project_operation", "discover_kind(", "record_preexisting_dirty",
                     "review_commit_effect", "review_publication_effect", "gitops."):
            with self.subTest(name=name):
                self.assertNotIn(name, OWNER_TEXT)

    def test_the_owner_never_names_the_project_namespace(self) -> None:
        for value in _string_constants(OWNER_TREE):
            with self.subTest(value=value[:40]):
                self.assertFalse(value == ".workline" or value.startswith(".workline/"))
        self.assertNotIn("WORKLINE_DIR", OWNER_TEXT)

    def test_recovery_is_the_shared_discovery_core_only(self) -> None:
        self.assertEqual(1, OWNER_TEXT.count("discover_kind_in("))
        for walk in ("_matching_runs", "run_ids(", "gates_dir", "GATES_DIR", "generation_of_name", "_clean_run"):
            with self.subTest(walk=walk):
                self.assertNotIn(walk, OWNER_TEXT)
        discover = _docstring_free(_function("_discover"))
        self.assertIn("root_maintenance.pending_for_run(", discover)
        self.assertIn("_NS", discover)


class CatalogueSourceTests(unittest.TestCase):
    """The P7 one-catalogue rule, read from the source: each owner code spelled once, in the catalogue."""

    def test_each_p7_literal_is_spelled_once_and_catalogued(self) -> None:
        literals = [value for value in _string_constants(OWNER_TREE) if value.startswith("review_p7_")]
        self.assertEqual(len(set(literals)), len(literals), "each P7 code is spelled once")
        assigned: dict[str, str] = {}
        for node in OWNER_TREE.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                    and isinstance(node.value, ast.Constant) and str(node.value.value).startswith("review_p7_"):
                assigned[node.targets[0].id] = node.value.value
        self.assertEqual(set(literals), set(assigned.values()), "a P7 literal is only ever a catalogue constant")
        tuples: dict[str, list[str]] = {}
        for node in OWNER_TREE.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
                    and node.targets[0].id in ("STOP_CODES", "RECONCILE_REASONS") and isinstance(node.value, ast.Tuple):
                tuples[node.targets[0].id] = [element.id for element in node.value.elts if isinstance(element, ast.Name)]
        catalogued = {assigned[name] for names in tuples.values() for name in names}
        self.assertEqual(set(assigned.values()), catalogued)
        stops = {assigned[name] for name in tuples["STOP_CODES"]}
        reasons = {assigned[name] for name in tuples["RECONCILE_REASONS"]}
        self.assertEqual(set(D_STOP_CODES), stops, "the D catalogue exactly (no unreachable code is catalogued)")
        self.assertEqual(set(FROZEN_REASONS), reasons)
        self.assertFalse(stops & reasons)
        self.assertNotIn("review_p6_", OWNER_TEXT)

    def test_the_frozen_public_shapes(self) -> None:
        classes = {node.name: node for node in OWNER_TREE.body if isinstance(node, ast.ClassDef)}

        def fields(name: str) -> list[str]:
            return [item.target.id for item in classes[name].body if isinstance(item, ast.AnnAssign)]

        self.assertEqual(["discovery", "adjudicator"], fields("GlobalPolicyReview"))
        self.assertEqual(["status", "global_policy_change_id", "promotion_packet_id", "review_run_id", "receipt_id",
                          "consumption_id", "global_policy_version", "global_policy_digest", "policy_commit",
                          "metadata_commit", "mutation_id", "findings", "detail"], fields("GlobalPolicyChangeResult"))
        self.assertEqual(["evaluation_id", "global_policy_change_id", "result", "next_action", "commit", "mutation_id"],
                         fields("GlobalPolicyEvaluationResult"))
        change = _function("change_global_policy").args
        self.assertEqual(["workline_root", "request"], [arg.arg for arg in change.args])
        self.assertEqual(["review"], [arg.arg for arg in change.kwonlyargs])
        evaluation = _function("record_global_policy_evaluation").args
        self.assertEqual(["workline_root", "request"], [arg.arg for arg in evaluation.args])
        self.assertEqual([], evaluation.kwonlyargs)
        self.assertEqual(["review"], [arg.arg for arg in _function("validate_global_policy_review").args.args])
        self.assertIn('ROOT_COMMIT_CONTRACT = "review-v1-p7-root-commit-v1"', OWNER_TEXT)
        for status in ('STATUS_APPLIED = "applied"', 'STATUS_NOT_AUTHORIZED = "not_authorized"',
                       'STATUS_HUMAN_WAIT = "human_wait"'):
            self.assertIn(status, OWNER_TEXT)


class CatalogueTests(unittest.TestCase):
    """The owner's ``stop`` / ``reconcile`` raise only catalogued values."""

    def test_stop_and_reconcile_refuse_an_undeclared_value(self) -> None:
        gp = owner()
        for code in FROZEN_STOP_CODES:
            self.assertIn(code, gp.STOP_CODES)
            self.assertEqual(code, gp.stop(code, "x").code)
        for reason in FROZEN_REASONS:
            self.assertIn(reason, gp.RECONCILE_REASONS)
            found = gp.reconcile("x", reason)
            self.assertEqual(reason, found.reason)
            self.assertTrue(str(found).endswith(": reconcile required"))
        with self.assertRaises(ValueError):
            gp.stop("review_p7_not_declared", "x")
        with self.assertRaises(ValueError):
            gp.reconcile("x", "review_p7_not_declared")
        self.assertEqual("global-policy-change", gp.OWNER)
        self.assertEqual("global-policy-evaluation", gp.OPERATION_EVALUATION)

    def test_the_review_argument_is_validated_before_anything_is_read(self) -> None:
        gp = owner()
        from workline.errors import ValidationError

        with self.assertRaises(ValidationError) as raised:
            gp.validate_global_policy_review(object())
        self.assertEqual("review_contract_invalid", raised.exception.code)


# =========================================================================== end to end (§31.55)

class RemoteLessChangeTests(GlobalPolicyCase):
    def test_kp_is_exactly_the_reviewed_three_paths_and_round_trips(self) -> None:
        base = self.head()
        before = self.policy_record()
        result = self.applied()
        gp = owner()
        self.assertEqual(2, result.global_policy_version)
        kp, km = result.policy_commit, result.metadata_commit
        self.assertEqual([km, kp], self.commits_with(KM_SUBJECT) + self.commits_with(KP_SUBJECT))
        self.assertEqual(km, self.head())
        # base-exact chain: Kg1 .. Kg5 -> Kp -> Km, each on its immediately expected parent
        chain = list(reversed(self.commits_with(KG_SUBJECT)))
        self.assertEqual(5, len(chain))
        self.assertEqual([base], self.parents(chain[0]))
        for earlier, later in zip(chain, chain[1:] + [kp, km]):
            self.assertEqual([earlier], self.parents(later))
        # Kp: exactly global-policy.yaml (M), changes/<rgc>.yaml (A), patch-notes/<rgc>.md (A)
        change_path = f"review-policy/changes/{result.global_policy_change_id}.yaml"
        note_path = f"review-policy/patch-notes/{result.global_policy_change_id}.md"
        delta = self.delta(kp)
        self.assertEqual({GLOBAL_POLICY_REL: "M", change_path: "A", note_path: "A"},
                         {path: item.status for path, item in delta.items()})
        self.assertEqual({"100644"}, {item.mode for item in delta.values()})
        after = self.policy_record(kp)
        self.assertIsNone(policy.global_policy_successor_problem(before, after))
        self.assertEqual(2, policy.global_policy_settings(after)[SLOTS])
        self.assertEqual(policy.global_policy_digest(after), result.global_policy_digest)
        self.assertEqual(policy.global_policy_bytes(after), delta[GLOBAL_POLICY_REL].data)
        # semantic round-trip through the canonical loader (materialized mode)
        baseline = policy.load_global_baseline(self.root)
        self.assertEqual(policy.SOURCE_MODE_MATERIALIZED, baseline.source_mode)
        self.assertEqual(policy.global_policy_digest(after), baseline.global_policy_identity)
        self.assertEqual(policy.global_policy_projection(after), baseline.semantic_projection)
        # Km: exactly the Global Policy Consumption v4
        consumption_path = f"review-policy/review/consumptions/{result.consumption_id}.yaml"
        km_delta = self.delta(km)
        self.assertEqual({consumption_path: "A"}, {path: item.status for path, item in km_delta.items()})
        record, _ = serialize.parse_canonical(km_delta[consumption_path].data, "the Consumption")
        self.assertEqual(records.GLOBAL_POLICY_CONSUMPTION_VERSION, record["version"])
        consumption = records.consumption_from_record(record, "the Consumption")
        self.assertIsInstance(consumption, records.GlobalPolicyConsumption)
        persisted = consumption.persisted_global_policy
        self.assertEqual((kp, self.parents(kp)[0], BRANCH),
                         (persisted["policy_commit"], persisted["policy_parent"], persisted["branch"]))
        self.assertEqual(result.global_policy_change_id, persisted["global_policy_change_id"])
        self.assertEqual(result.promotion_packet_id, persisted["promotion_packet_id"])
        self.assertEqual(serialize.digest(policy.global_policy_projection(after)), persisted["normalized_projection_hash"])
        self.assertEqual(result.receipt_id, consumption.receipt_id)
        self.assertEqual("global-policy", consumption.target_identity)
        self.assertNotIn("terminal_event_id", record)
        # nothing else: no Project namespace, a clean tree, the runtime completed
        self.assertNoProjectNamespace()
        self.assertEqual([], self.dirty())
        self.assertEqual([], self.pending_records())
        self.assertEqual([gp.STATUS_APPLIED], [result.status])

    def test_version_4_is_read_by_its_own_reader_and_the_older_readers_keep_their_meaning(self) -> None:
        result = self.applied()
        raw = self.blob(result.metadata_commit, f"review-policy/review/consumptions/{result.consumption_id}.yaml")
        record, _ = serialize.parse_canonical(raw, "the Consumption")
        self.assertIsInstance(records.consumption_from_record(record, "v4"), records.GlobalPolicyConsumption)
        for version in (1, 2, 3):
            with self.subTest(relabelled=version):
                with self.assertRaises(Exception):
                    records.consumption_from_record({**record, "version": version}, f"v{version}-labelled")
        # the evidence sources' own (version 2 planning) Consumptions still read exactly as before
        source = self.sources[0].root
        found = CommittedReviewStore(source, git(source, "rev-parse", "HEAD").strip()).consumptions()
        self.assertTrue(found)
        self.assertTrue(all(isinstance(item, records.PlanningConsumption) for item in found))

    def test_the_patch_note_and_change_record_are_explanation_and_evidence(self) -> None:
        result = self.applied()
        note = self.blob(result.policy_commit, f"review-policy/patch-notes/{result.global_policy_change_id}.md")
        self.assertNotIn(b"\r", note)
        for source in self.sources:
            self.assertNotIn(str(source.root).encode("utf-8"), note)
        change = self.blob(result.policy_commit, f"review-policy/changes/{result.global_policy_change_id}.yaml")
        parsed = serialize.parse_canonical(change, "the change")[0]
        self.assertEqual((result.receipt_id, result.review_run_id), (parsed["receipt_id"], parsed["review_run_id"]))
        self.assertNotIn(result.policy_commit, change.decode("utf-8"), "a change record does not guess its commit")
        for source in self.sources:
            self.assertNotIn(str(source.root), change.decode("utf-8"))

    def test_unrelated_dirt_stays_untouched_and_uncommitted(self) -> None:
        (self.root / "notes.txt").write_text("a person's note\n", encoding="utf-8")
        readme = self.root / "registry.md"
        readme.write_bytes(readme.read_bytes() + b"\n<!-- a person's edit -->\n")
        unrelated = self.root / "review-policy" / "README.local"
        unrelated.write_text("outside every owned path\n", encoding="utf-8")
        result = self.applied()
        for commit in [result.policy_commit, result.metadata_commit] + self.commits_with(KG_SUBJECT):
            with self.subTest(commit=commit):
                self.assertFalse({"notes.txt", "registry.md", "review-policy/README.local"} & set(self.delta(commit)))
        self.assertEqual("a person's note\n", (self.root / "notes.txt").read_text(encoding="utf-8"))
        self.assertTrue(readme.read_bytes().endswith(b"<!-- a person's edit -->\n"))
        self.assertEqual({" M registry.md", "?? notes.txt", "?? review-policy/README.local"}, set(self.dirty()))

    def test_owned_path_dirt_blocks_before_any_effect(self) -> None:
        cases = {
            "a person's Global policy edit": (GLOBAL_POLICY_REL, None),
            "an untracked change record": ("review-policy/changes/rgc_0000000000000000000000000Z.yaml", b"x: 1\n"),
            "an untracked root Review file": ("review-policy/review/gates/stray.yaml", b"x: 1\n"),
        }
        for label, (relative, data) in cases.items():
            with self.subTest(case=label):
                head = self.head()
                target = self.root / relative
                original = target.read_bytes() if target.exists() else None
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data if data is not None else (original or b"") + b"# edited\n")
                self.stops("dirty_overlap", self.change)
                self.assertEqual(head, self.head())
                self.assertEqual([], self.pending_records())
                self.assertEqual([], self.tracked("review-policy/promotion-packets/"))
                if original is None:
                    target.unlink()
                else:
                    target.write_bytes(original)
        self.assertNoProjectNamespace()

    def test_a_root_ignore_rule_on_an_owned_path_stops_before_the_first_effect(self) -> None:
        exclude = Path(self.git("rev-parse", "--git-path", "info/exclude").strip())
        exclude = exclude if exclude.is_absolute() else self.root / exclude
        for rule in ("review-policy/review/", "review-policy/changes/", "*.md"):
            with self.subTest(rule=rule):
                head = self.head()
                exclude.parent.mkdir(parents=True, exist_ok=True)
                exclude.write_text(rule + "\n", encoding="utf-8")
                self.stops("review_path_ignored", self.change)
                self.assertEqual(head, self.head())
                self.assertEqual([], self.pending_records())
                self.assertFalse((self.root / "review-policy" / "promotion-packets").exists())
                self.assertFalse((self.root / "review-policy" / "review").exists())
                exclude.write_text("", encoding="utf-8")

    def test_a_hostile_global_configuration_commits_the_reviewed_bytes(self) -> None:
        """RB7C-5: line-ending conversion, an attributes file, a failing hook and commit signing in the global
        configuration take no part in a root commit; the committed bytes are the reviewed bytes and C-2 holds."""
        hooks = self.new_dir("hostile-hooks")
        (hooks / "pre-commit").write_text("#!/bin/sh\necho mangled > review-policy/global-policy.yaml\nexit 1\n",
                                          encoding="utf-8", newline="\n")
        attributes = self.tmp / "hostile-attributes"
        attributes.write_text("* text eol=crlf\n", encoding="utf-8")
        hostile = self.tmp / "hostile-global.gitconfig"
        hostile.write_text(
            "[core]\n\tautocrlf = true\n\teol = crlf\n"
            f"\thooksPath = {hooks.as_posix()}\n\tattributesFile = {attributes.as_posix()}\n"
            "[commit]\n\tgpgSign = true\n[gpg]\n\tprogram = workline-test-no-such-gpg\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(hostile)}):
            result = self.applied()
        after = self.policy_record(result.policy_commit)
        self.assertEqual(policy.global_policy_bytes(after), self.blob(result.policy_commit, GLOBAL_POLICY_REL))
        self.assertNotIn(b"\r\n", self.blob(result.policy_commit, GLOBAL_POLICY_REL))
        self.assertEqual(2, policy.global_policy_settings(after)[SLOTS])

    def test_an_identity_unconfigured_root_stops_at_entry_and_writes_nothing(self) -> None:
        self.git("config", "--unset", "user.name")
        home = self.new_dir("empty-home")
        head = self.head()
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home), "XDG_CONFIG_HOME": str(home)}):
            self.stops("review_identity_unavailable", self.change)
        self.assertEqual(head, self.head())
        self.assertEqual([], self.pending_records())
        self.assertFalse((self.root / "review-policy" / "promotion-packets").exists())

    def test_a_moved_global_policy_is_a_before_state_conflict_with_nothing_opened(self) -> None:
        """The Candidate binds the exact committed Global policy; a moved one is never reviewed or written over."""
        with crash_at(owner(), "_launch_discovery"):
            with self.assertRaises(Crash):
                self.change()
        runs = self.run_ids()
        self.assertEqual(1, len(runs))
        self.drop_runtime()
        before = self.policy_record()
        moved = policy.global_policy_record(2, policy.global_policy_digest(before),
                                            {SLOTS: 1, policy.SURFACE_EXTRA_SCOPE_STEPS: 1})
        (self.root / GLOBAL_POLICY_REL).write_bytes(policy.global_policy_bytes(moved))
        git(self.root, "commit", "-q", "-am", "a person's Global policy commit")
        head = self.head()
        gp = owner()
        self.stops(gp.CODE_BEFORE_STATE_CONFLICT, self.change)
        self.assertEqual(head, self.head())
        self.assertEqual([], self.pending_records())
        self.assertEqual(runs, self.run_ids())

    def test_unexpected_head_movement_is_reconcile_never_a_rebase(self) -> None:
        with crash_at(owner(), "_launch_discovery"):
            with self.assertRaises(Crash):
                self.change()
        (self.root / "unrelated.txt").write_text("x\n", encoding="utf-8")
        git(self.root, "add", "unrelated.txt")
        git(self.root, "commit", "-q", "-m", "a person's commit on the root branch")
        head = self.head()
        gp = owner()
        self.stops("", self.change, reason=gp.REASON_RECORD_CONFLICT)
        self.assertEqual(head, self.head())
        self.assertEqual(1, len(self.pending_records()), "the pending mutation is reconciled, never rebased or reset")

    def test_a_second_request_while_one_is_pending_is_refused(self) -> None:
        with crash_at(owner(), "_launch_discovery"):
            with self.assertRaises(Crash):
                self.change()
        other = self.request(after=3)
        self.stops("", lambda: self.change(other), reason=maintenance().REASON_MUTATION_CONFLICT)
        self.applied()  # the pending request resumes and finishes

    def test_a_second_request_after_a_pending_kp_meets_the_single_writer_refusal(self) -> None:
        """RB7DL-1: the change record of a Kp a PENDING root mutation recorded is that mutation's - its Kp identity
        is durable - so another request meets the single-writer refusal, never the manual-reconciliation boundary."""
        with crash_at(owner(), "_c2_kp"):
            with self.assertRaises(Crash):
                self.change()
        (kp,) = self.commits_with(KP_SUBJECT)
        self.assertEqual([], self.commits_with(KM_SUBJECT))
        head = self.head()
        self.stops("", lambda: self.change(self.request(after=3)), reason=maintenance().REASON_MUTATION_CONFLICT)
        self.assertEqual(head, self.head())
        self.assertEqual(1, len(self.pending_records()), "only the first request's mutation is pending")
        result = self.applied()  # the pending request resumes from its recorded Kp and finishes
        self.assertEqual(([kp], 2), (self.commits_with(KP_SUBJECT), result.global_policy_version))
        self.assertEqual(result.metadata_commit, self.head())

    def test_a_root_head_without_a_global_policy_stops_at_entry(self) -> None:
        """RB7DL-5: a root whose HEAD commits no review-policy/global-policy.yaml is not materialized there
        (§31.2 / §31.3); no Global Policy Change begins on it, and nothing is written or left pending."""
        git(self.root, "rm", "-q", GLOBAL_POLICY_REL)
        git(self.root, "commit", "-q", "-m", "a root without a materialized Global policy")
        head = self.head()
        self.stops(owner().CODE_GLOBAL_POLICY_UNAVAILABLE, self.change)
        self.assertEqual(head, self.head())
        self.assertEqual([], self.pending_records())
        self.assertEqual([], self.runtime_records(), "no root mutation is even opened")
        self.assertFalse((self.root / GLOBAL_POLICY_REL).exists(), "the owner never materializes the policy itself")
        self.assertNoProjectNamespace()

    def test_a_remote_added_mid_run_is_never_left_unpublished(self) -> None:
        """RB7DL-2: the root was remote-less at entry and gains a remote while discovery runs; §31.28's publication
        readiness is re-read before G4, so no Receipt, change or Kp is made for a root that now has a remote."""
        late = self.tmp / "late-remote.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(late))
        root = self.root

        class AddingRemote(Discovery):
            def __call__(self, task):
                if not git(root, "remote").strip():
                    git(root, "remote", "add", "origin", str(late))
                return super().__call__(task)

        review = root_review(AddingRemote(viewpoint="correctness", identity="discovery-1"),
                             Discovery(viewpoint="safety", identity="discovery-2"))
        self.stops("review_p7_authorization_required", lambda: self.change(review=review))
        self.assertEqual([], self.tracked("review-policy/review/receipts/"))
        self.assertEqual([], self.tracked("review-policy/changes/"))
        self.assertEqual([], self.commits_with(KP_SUBJECT))
        self.assertEqual("", git(late, "for-each-ref").strip(), "nothing reaches the remote")

    def test_publication_readiness_is_read_now_against_the_frozen_binding(self) -> None:
        """RB7DL-2: None remote-less as frozen; True only for exactly the frozen binding; False otherwise."""
        gp = owner()
        binding = maintenance().PublicationBinding("origin", BRANCH, "locator")
        frozen = {"remote": "origin", "branch": BRANCH}
        cases = (
            (None, None, None),
            (None, frozen, False),                  # the frozen remote is gone
            (binding, frozen, True),
            (binding, None, False),                 # a remote added after a remote-less freeze
            (binding, {"remote": "upstream", "branch": BRANCH}, False),
            (binding, {"remote": "origin", "branch": "refs/heads/other"}, False),
        )
        op = mock.Mock(root=self.root)
        for found, frozen_binding, expected in cases:
            with self.subTest(found=found, frozen=frozen_binding):
                with mock.patch.object(maintenance(), "publication_binding", return_value=found):
                    self.assertIs(expected, gp._publication_ready(op, frozen_binding))


class ReviewerFloorEntryTests(GlobalPolicyCase):
    def test_too_few_distinct_reviewers_launch_nothing(self) -> None:
        head = self.head()
        one = Discovery()
        same = (Discovery(), Discovery(viewpoint="safety"))  # two viewpoints, one reviewer identity / version
        for review in (root_review(one), root_review(*same)):
            with self.subTest(reviewers=len(review.discovery)):
                with self.assertRaises(Exception) as raised:
                    self.change(review=review)
                self.assertTrue(str(getattr(raised.exception, "code", "")).endswith("reviewer_floor_unmet"),
                                str(raised.exception))
                self.assertEqual(head, self.head())
                self.assertEqual([], self.pending_records())
        self.assertEqual([], one.tasks)


class RemoteChangeTests(GlobalPolicyCase):
    remote = True

    def test_exact_kp_then_exact_km_are_published_never_forced(self) -> None:
        start = self.remote_tip()
        result = self.applied()
        self.assertEqual([f"{start} {result.policy_commit} {BRANCH}", f"{result.policy_commit} {result.metadata_commit} "
                          f"{BRANCH}"], self.remote_log())
        self.assertEqual(result.metadata_commit, self.remote_tip())
        for kg in self.commits_with(KG_SUBJECT):
            with self.subTest(kg=kg):
                self.assertFalse(any(line.split()[1] == kg for line in self.remote_log()),
                                 "a root Review generation commit is never pushed on its own")

    def test_nothing_is_pushed_before_the_root_proof_and_the_barrier(self) -> None:
        from workline import gitcmd
        from workline.review import publication

        order: list[str] = []
        gp = owner()
        real_proof, real_barrier, real_push = gp._require_root_proof, publication.require_barrier_clear, gitcmd.push

        def proof(*args, **kwargs):
            order.append(f"proof:{args[2]}")
            return real_proof(*args, **kwargs)

        def barrier(repo, commit):
            order.append("barrier")
            return real_barrier(repo, commit)

        def push(repo, remote, refspec):
            order.append(f"push:{refspec}")
            return real_push(repo, remote, refspec)

        with mock.patch.object(gp, "_require_root_proof", proof), \
                mock.patch.object(publication, "require_barrier_clear", barrier), \
                mock.patch.object(gitcmd, "push", push):
            result = self.applied()
        self.assertEqual(["proof:kp", "barrier", f"push:{result.policy_commit}:{BRANCH}",
                          "proof:km", "barrier", f"push:{result.metadata_commit}:{BRANCH}"], order)

    def test_a_failed_root_proof_publishes_nothing(self) -> None:
        start = self.remote_tip()
        gp = owner()
        failing = mock.Mock(side_effect=gp.reconcile("C-2(Kp) refused by the test", gp.REASON_PERSISTED_MISMATCH))
        with mock.patch.object(gp, "_require_root_proof", failing):
            self.stops("", self.change, reason=gp.REASON_PERSISTED_MISMATCH)
        self.assertEqual(start, self.remote_tip())
        self.assertEqual([], self.remote_log())
        self.assertEqual(1, len(self.commits_with(KP_SUBJECT)), "Kp is made locally and never published unproven")

    def test_a_revoked_authorization_stops_before_any_receipt_or_kp(self) -> None:
        """RB7DL-2: the authorization is revoked while discovery runs; §31.28's publication readiness is re-read
        before G4 and before the seal, so no Receipt, change record or Kp is made and nothing is pushed."""
        authorization = self.root / RUNTIME_DIR / "maintenance-authorization.yaml"

        class Revoking(Discovery):
            def __call__(self, task):
                if authorization.exists():
                    authorization.unlink()
                return super().__call__(task)

        start = self.remote_tip()
        review = root_review(Revoking(viewpoint="correctness", identity="discovery-1"),
                             Discovery(viewpoint="safety", identity="discovery-2"))
        self.stops("review_p7_authorization_required", lambda: self.change(review=review))
        self.assertEqual([], self.tracked("review-policy/review/receipts/"))
        self.assertEqual([], self.tracked("review-policy/changes/"))
        self.assertEqual([], self.commits_with(KP_SUBJECT))
        self.assertEqual([], self.remote_log())
        self.assertEqual(start, self.remote_tip())

    def test_a_remote_with_no_authorization_does_not_start(self) -> None:
        (self.root / RUNTIME_DIR / "maintenance-authorization.yaml").unlink()
        head = self.head()
        self.stops("review_p7_authorization_required", self.change)
        self.assertEqual(head, self.head())
        self.assertEqual([], self.pending_records())


class UnmockedRootChangeTests(GlobalPolicyCase):
    """I-RB7-2: a change in a copied root through the copy's own implementation, nothing stood in for."""

    def test_run_remote_less_change_applies_in_the_copy(self) -> None:
        found = run_remote_less_change(self.root, self.sources)
        self.assertEqual("applied", found["status"])
        self.assertEqual(found["metadata_commit"], self.head())
        self.assertEqual(2, policy.global_policy_settings(self.policy_record())[SLOTS])
        self.assertNoProjectNamespace()


if __name__ == "__main__":
    unittest.main()
