"""The resulting tree's checkout capability: can a fresh clone still read the Review records?

P3 F3 §7.9.1 through §7.9.5, IP-13.

By the time a Work seals it has already written canonical Review records, and P1
requires those to stay exactly readable from a fresh clone. So the seal's
precondition is the canonical form-L claim - the same rule ``skills/review``
freezes for P2 - proven over the RESULTING TREE rather than over HEAD, plus P1's
strict reader over every record that tree already holds.

The decisive property these tests hold is the one §7.9.6 was corrected for: an
unsafe resulting tree stays EXPRESSIBLE. The capability refuses, and the Context
is still built, still canonical and still hashes the same. A verdict is derived,
never stored.
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
from workline.errors import StopError, ValidationError
from workline.ids import new_id
from workline.implementation import package_directory
from workline.review import hermetic, paths as review_paths, records, resulting_tree as rt, serialize
from workline.review import work_checkout as wc, work_context as wctx
from workline.review.committed import CommittedReviewStore
from workline.review.store import GateChain, ReviewStore

CANONICAL_LINE = ".workline/review/** !text eol=lf -filter -ident -working-tree-encoding\n"
ZERO_40 = "0" * 40
WORKSPACE = Path(__file__).resolve().parents[1]


def clean_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}


class CapabilityCase(WorklineTestCase):
    """A Project whose base carries the canonical Review rule, and helpers to change it."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        git(self.store.root, "config", "user.name", "Real Person")
        git(self.store.root, "config", "user.email", "real@proj")
        self.hermetic = hermetic.enter(self.store)
        self.write(".gitattributes", CANONICAL_LINE)
        self.write("a.txt", "x\n")
        self.base = self.commit("base with the canonical rule")

    def write(self, relative: str, text: str) -> None:
        path = self.store.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def commit(self, message: str) -> str:
        git(self.store.root, "add", "-A")
        git(self.store.root, "commit", "-m", message, "--no-verify")
        return git(self.store.root, "rev-parse", "HEAD").strip()

    def blob(self, data: bytes) -> tuple[str, str]:
        return gitcmd.hash_blob(self.store.root, data), hashlib.sha256(data).hexdigest()

    def added(self, path: str, data: bytes) -> rt.Entry:
        oid, digest = self.blob(data)
        return rt.Entry(path, "A", "absent", "000000", ZERO_40, "file", "100644", oid, digest)

    def rewritten_attributes(self, data: bytes) -> rt.Entry:
        held = rt.tree_entries(self.hermetic, rt.root_tree_id(self.hermetic, self.base))[".gitattributes"]
        oid, digest = self.blob(data)
        return rt.Entry(".gitattributes", "M", "file", "100644", held.oid, "file", "100644", oid, digest)

    def capability(self, entries, payloads=None, *, base: str | None = None, expect: str | None = None):
        with rt.composed(self.store, self.hermetic, base or self.base, entries, payloads or {}) as composition:
            return wc.require_resulting_tree_capability(self.store, self.hermetic, composition, expect=expect)

    def refusal(self, call, code: str) -> StopError:
        with self.assertRaises(StopError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def supersession_bytes(self) -> tuple[str, bytes]:
        record = records.Supersession(
            superseded_receipt_id=new_id("review_receipt"),
            review_run_id=new_id("review_run"),
            superseding_generation=2,
            reason="superseded for the fixture",
        )
        text = ReviewStore.render(record.to_record())
        return review_paths.supersession_rel(record.superseded_receipt_id), text.encode("utf-8")


# --------------------------------------------------------------------------- the frozen identities


class IdentityTests(unittest.TestCase):
    """The Work capability identity is its own, and never P2's."""

    def test_the_work_capability_contract_is_frozen(self) -> None:
        self.assertEqual(wc.WORK_CHECKOUT_CONTRACT, "review-v1-work-checkout-capability-v1")
        self.assertEqual(wc.FORM_IDENTITY, "form-L")
        self.assertEqual(wc.REVIEW_NAMESPACE, ".workline/review/**")

    def test_the_planning_capability_contract_is_untouched(self) -> None:
        from workline.review import checkout

        self.assertEqual(checkout.CHECKOUT_CONTRACT, "review-v1-planning-checkout-v1")
        self.assertNotEqual(wc.WORK_CHECKOUT_CONTRACT, checkout.CHECKOUT_CONTRACT)

    def test_the_canonical_rule_and_form_are_the_ones_skills_review_freezes(self) -> None:
        from workline.review import checkout

        self.assertIs(wc.CANONICAL_RULE, checkout.CANONICAL_RULE)
        self.assertIs(wc.FORM_L, checkout.FORM_L)
        self.assertEqual(
            wc.CANONICAL_RULE, b".workline/review/** !text eol=lf -filter -ident -working-tree-encoding"
        )


# --------------------------------------------------------------------------- the four layers


class CapabilityLayerTests(CapabilityCase):
    """§7.9.3: four layers, all required, over the resulting tree."""

    def test_a_safe_resulting_tree_is_capable(self) -> None:
        data = b"added\n"
        found = self.capability([self.added("added.txt", data)], {"added.txt": data})
        self.assertEqual(found.capability_contract, wc.WORK_CHECKOUT_CONTRACT)
        self.assertEqual(found.form, "form-L")
        self.assertEqual(found.namespace, ".workline/review/**")

    def test_a_tree_with_no_entries_at_all_is_still_proven(self) -> None:
        found = self.capability([])
        self.assertEqual(found.resulting_tree, rt.root_tree_id(self.hermetic, self.base))

    def test_layer_1_the_last_rule_must_be_the_canonical_one(self) -> None:
        for label, data in (
            ("a material rule after it", CANONICAL_LINE.encode() + b"*.txt text\n"),
            ("no canonical rule at all", b"*.md -text\n"),
            ("an empty source", b""),
            ("a weakened form", b".workline/review/** !text -filter -ident -working-tree-encoding\n"),
            ("a wider pattern", b".workline/** !text eol=lf -filter -ident -working-tree-encoding\n"),
        ):
            with self.subTest(case=label):
                entry = self.rewritten_attributes(data)
                self.refusal(lambda entry=entry, data=data: self.capability([entry], {".gitattributes": data}),
                             "review_checkout_unsafe")

    def test_layer_1_a_nul_byte_makes_the_source_partial(self) -> None:
        data = CANONICAL_LINE.encode() + b"\0*.txt text\n"
        entry = self.rewritten_attributes(data)
        self.assertIn("NUL", str(self.refusal(
            lambda: self.capability([entry], {".gitattributes": data}), "review_checkout_unsafe")))

    def test_layer_1_the_root_source_must_be_a_regular_blob(self) -> None:
        held = rt.tree_entries(self.hermetic, rt.root_tree_id(self.hermetic, self.base))[".gitattributes"]
        entry = rt.Entry(".gitattributes", "M", "file", "100644", held.oid, "symlink", "120000",
                         self.blob(b"elsewhere")[0], self.blob(b"elsewhere")[1])
        self.refusal(lambda: self.capability([entry], {".gitattributes": b"elsewhere"}),
                     "review_checkout_unsafe")

    def test_layer_1_a_removed_root_source_is_unsafe(self) -> None:
        held = rt.tree_entries(self.hermetic, rt.root_tree_id(self.hermetic, self.base))[".gitattributes"]
        entry = rt.Entry(".gitattributes", "D", "file", "100644", held.oid, "absent", "000000", ZERO_40, None)
        self.refusal(lambda: self.capability([entry], {}), "review_checkout_unsafe")

    def test_layer_2_no_deeper_source_below_workline(self) -> None:
        for path in (".workline/.gitattributes", ".workline/review/.gitattributes",
                     ".workline/review/gates/.gitattributes"):
            with self.subTest(path=path):
                data = b"*.yaml text\n"
                entry = self.added(path, data)
                error = self.refusal(lambda entry=entry, data=data, path=path:
                                     self.capability([entry], {path: data}), "review_checkout_unsafe")
                self.assertIn(path, str(error))

    def test_layer_2_a_deeper_source_is_refused_even_when_its_rules_look_harmless(self) -> None:
        data = b"# nothing at all\n"
        entry = self.added(".workline/review/.gitattributes", data)
        self.refusal(lambda: self.capability([entry], {".workline/review/.gitattributes": data}),
                     "review_checkout_unsafe")

    def test_layer_3_is_asked_against_the_exact_resulting_tree(self) -> None:
        seen: list[tuple[str, ...]] = []
        real = gitcmd.run_git_bytes

        def recording(repo, *args, **kwargs):
            if "check-attr" in args:
                seen.append(args)
            return real(repo, *args, **kwargs)

        with rt.composed(self.store, self.hermetic, self.base, [], {}) as composition:
            with mock.patch.object(gitcmd, "run_git_bytes", recording):
                wc.require_resulting_tree_capability(self.store, self.hermetic, composition)
            self.assertTrue(any(f"--source={composition.tree}" in args for args in seen))

    def test_layer_3_a_question_git_cannot_answer_is_unknown(self) -> None:
        with mock.patch.object(gitcmd, "check_attributes", return_value=None):
            self.refusal(lambda: self.capability([]), "review_checkout_unknown")

    def test_layer_4_a_filter_driver_named_unset_makes_the_printed_form_prove_nothing(self) -> None:
        git(self.store.root, "config", "filter.unset.clean", "cat")
        self.refusal(lambda: self.capability([]), "review_checkout_unsafe")

    def test_layer_4_a_hostile_info_attributes_is_caught_although_the_tree_is_safe(self) -> None:
        """The tree is unchanged; layer 4 judges the environment this repository actually has."""
        info = self.store.root / ".git" / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "attributes").write_text(".workline/review/** text\n", encoding="utf-8", newline="\n")
        self.refusal(lambda: self.capability([]), "review_checkout_unsafe")

    def test_a_capability_asked_about_another_tree_is_unknown(self) -> None:
        self.refusal(lambda: self.capability([], expect="9" * 40), "review_checkout_unknown")


# --------------------------------------------------------------------------- the covered surface


class CoveredSurfaceTests(CapabilityCase):
    """§7.9.4: the pattern covers records that do not exist yet; the reader covers the ones that do."""

    def test_the_namespace_witness_needs_no_identifier(self) -> None:
        """A future generation, Receipt or Consumption is covered without being named."""
        self.assertTrue(wc.NAMESPACE_WITNESS.startswith(review_paths.REVIEW_DIR + "/"))
        found = self.capability([])
        self.assertEqual(found.namespace, ".workline/review/**")
        self.assertEqual(found.record_paths, ())

    def test_every_existing_record_of_every_run_is_enumerated(self) -> None:
        first, first_bytes = self.supersession_bytes()
        second, second_bytes = self.supersession_bytes()
        entries = [self.added(first, first_bytes), self.added(second, second_bytes)]
        found = self.capability(entries, {first: first_bytes, second: second_bytes})
        self.assertEqual(set(found.record_paths), {first, second})

    def test_an_entry_outside_the_closed_namespace_is_refused(self) -> None:
        data = b"stray\n"
        stray = f"{review_paths.REVIEW_DIR}/not-a-subdir/x.yaml"
        entry = self.added(stray, data)
        error = self.refusal(lambda: self.capability([entry], {stray: data}), "review_checkout_unsafe")
        self.assertIn("closed Review namespace", str(error))

    def test_the_closed_namespace_is_the_contracts_twelve_subdirectories(self) -> None:
        # P1's seven, then P4's four (WORKLINE_COMPLETION_SPRINT §12.22 / §27.5): every P4 record kind is
        # inside the closed namespace and its checkout/path-safety proof. Then P5's durable history
        # (§13.3 / §28.3), the one two-level area: history/<family>/<id>.yaml, read by its family's reader.
        self.assertEqual(review_paths.REVIEW_SUBDIRS, (
            "gates", "receipts", "consumptions", "supersessions",
            "candidate-snapshots", "task-inputs", "activation",
            "reports", "adjudications", "repair-batches", "repair-results",
            "history",
        ))


# --------------------------------------------------------------------------- the strict reader


class StrictReaderTests(CapabilityCase):
    """§7.9.4's second condition: every record already in the tree still reads under P1."""

    def test_a_valid_record_in_the_resulting_tree_reads(self) -> None:
        path, data = self.supersession_bytes()
        found = self.capability([self.added(path, data)], {path: data})
        self.assertEqual(found.record_paths, (path,))

    def test_non_canonical_bytes_are_refused(self) -> None:
        path, data = self.supersession_bytes()
        loose = data.replace(b"reason: superseded for the fixture\n", b"reason:  superseded for the fixture\n")
        entry = self.added(path, loose)
        self.refusal(lambda: self.capability([entry], {path: loose}), "review_checkout_unsafe")

    def test_an_unknown_record_field_is_refused(self) -> None:
        path, data = self.supersession_bytes()
        extended = data.replace(b"schema: review-supersession\n", b"extra: 1\nschema: review-supersession\n")
        entry = self.added(path, extended)
        self.refusal(lambda: self.capability([entry], {path: extended}), "review_checkout_unsafe")

    def test_a_record_of_the_wrong_schema_at_a_canonical_path_is_refused(self) -> None:
        path, data = self.supersession_bytes()
        wrong = data.replace(b"review-supersession", b"review-receipt")
        entry = self.added(path, wrong)
        self.refusal(lambda: self.capability([entry], {path: wrong}), "review_checkout_unsafe")

    def test_arbitrary_bytes_at_a_canonical_review_path_are_refused(self) -> None:
        path, _ = self.supersession_bytes()
        junk = b"not a record at all\n"
        entry = self.added(path, junk)
        self.refusal(lambda: self.capability([entry], {path: junk}), "review_checkout_unsafe")

    def test_an_indirection_where_a_record_belongs_is_refused(self) -> None:
        path, data = self.supersession_bytes()
        target = b"../../../etc/passwd"
        oid, digest = self.blob(target)
        entry = rt.Entry(path, "A", "absent", "000000", ZERO_40, "symlink", "120000", oid, digest)
        self.refusal(lambda: self.capability([entry], {path: target}), "review_checkout_unsafe")

    def test_a_broken_generation_chain_is_refused(self) -> None:
        """A gate directory whose generations do not start at the first one is not a chain."""
        review_run_id = new_id("review_run")
        relative = f"{review_paths.run_dir(review_run_id)}/000004.yaml"
        data = b"schema: review-gate\nversion: 1\n"
        entry = self.added(relative, data)
        self.refusal(lambda: self.capability([entry], {relative: data}), "review_checkout_unsafe")

    def test_the_reader_is_the_p1_one_and_not_a_bespoke_parser(self) -> None:
        self.assertTrue(issubclass(wc.ResultingTreeReviewStore, ReviewStore))
        for inherited in ("read_receipt", "read_consumption", "read_candidate_snapshot",
                          "read_task_input", "gate_chain", "digest", "render"):
            with self.subTest(name=inherited):
                self.assertTrue(hasattr(wc.ResultingTreeReviewStore, inherited))


# --------------------------------------------------------------------------- the decisive regression


class StrictGateChainTests(CapabilityCase):
    """§7.9.4: the resulting-tree reader is P1's strict reader over another byte source.

    Not "it parses the YAML". A chain the canonical P1 readers refuse must be
    refused here, so every one of these builds the SAME logical records and
    asserts both readers refuse - the tree-backed one and ``CommittedReviewStore``
    over a real commit.
    """

    def gate(self, run_id: str, generation: int, previous_digest, **overrides) -> dict:
        fields = dict(
            review_run_id=run_id, generation=generation,
            previous_generation=None if generation == records.FIRST_GENERATION else generation - 1,
            previous_digest=previous_digest, review_kind="work-result-v1", target_identity="wk_target",
            operation_identity="op", candidate_hash="a" * 64, review_context_hash="b" * 64,
            effective_policy_hash="c" * 64, evidence_digest="d" * 64, coverage_digest="e" * 64,
            raw_report_set_digest="f" * 64, adjudication_digest="0" * 64, obligation_digest="1" * 64,
            accepted_tasks=(), settled_tasks=(), status="open", receipt_id=None,
        )
        fields.update(overrides)
        return records.GateGeneration(**fields).to_record()

    def chain(self, run_id: str, generations):
        """Entries and payloads placing ``generations`` at ``run_id``'s canonical gate paths."""
        entries, payloads = [], {}
        for number, record in generations:
            data = ReviewStore.render(record).encode("utf-8")
            relative = review_paths.gate_rel(run_id, number)
            entries.append(self.added(relative, data))
            payloads[relative] = data
        return entries, payloads

    def committed_refuses(self, run_id: str, generations) -> str:
        """The same records committed to a real commit, read by the canonical P1 committed reader."""
        for number, record in generations:
            self.write(review_paths.gate_rel(run_id, number), ReviewStore.render(record))
        commit = self.commit("records for the committed reader")
        reader = CommittedReviewStore(self.store.root, commit)
        try:
            reader.gate_chain(run_id)
        except ValidationError as exc:
            return exc.code or "ValidationError"
        return "ACCEPTED"

    def both_refuse(self, run_id: str, generations) -> None:
        entries, payloads = self.chain(run_id, generations)
        self.refusal(lambda: self.capability(entries, payloads), "review_checkout_unsafe")
        self.assertNotEqual(self.committed_refuses(run_id, generations), "ACCEPTED",
                            "the canonical committed reader must refuse this too")

    def test_the_override_calls_the_p1_helpers_rather_than_restating_them(self) -> None:
        import inspect

        source = inspect.getsource(wc.ResultingTreeReviewStore.gate_chain)
        self.assertIn("_require_gate_identity", source)
        self.assertIn("_chain_invariants", source)
        self.assertIn("GateChain(", source)

    def test_a_valid_chain_returns_a_validated_gate_chain(self) -> None:
        run_id = new_id("review_run")
        first = self.gate(run_id, 1, None)
        digest = serialize.digest_of_text(ReviewStore.render(first))
        second = self.gate(run_id, 2, digest)
        entries, payloads = self.chain(run_id, [(1, first), (2, second)])
        with rt.composed(self.store, self.hermetic, self.base, entries, payloads) as composition:
            found = wc.ResultingTreeReviewStore(self.store, composition).gate_chain(run_id)
        self.assertIsInstance(found, GateChain)
        self.assertEqual(len(found.generations), 2)

    def test_a_record_declaring_another_run_is_refused(self) -> None:
        run_a, run_b = new_id("review_run"), new_id("review_run")
        self.both_refuse(run_a, [(1, self.gate(run_b, 1, None))])

    def test_a_record_declaring_another_generation_is_refused(self) -> None:
        run_id = new_id("review_run")
        self.both_refuse(run_id, [(1, self.gate(run_id, 2, "a" * 64))])

    def test_an_immutable_fact_changing_across_generations_is_refused(self) -> None:
        """target_identity and review_kind are immutable facts of a Run (_chain_invariants)."""
        for field, changed in (("target_identity", "wk_other"), ("review_kind", "planning-roadmap-v1")):
            with self.subTest(field=field):
                run_id = new_id("review_run")
                first = self.gate(run_id, 1, None)
                digest = serialize.digest_of_text(ReviewStore.render(first))
                second = self.gate(run_id, 2, digest, **{field: changed})
                self.both_refuse(run_id, [(1, first), (2, second)])

    def accepted_task(self, **overrides) -> dict:
        task = {
            "task_id": new_id("review_task"), "task_kind": "work-result-review",
            "task_slot": "work-result-reviewer", "reviewer_identity": "r", "reviewer_version": "1",
            "candidate_hash": "a" * 64, "candidate_material_digest": "2" * 64,
            "reconstruction_mode": records.RECONSTRUCTION_SNAPSHOT, "request_digest": "3" * 64,
            "task_input_digest": "4" * 64, "review_context_hash": "b" * 64,
            "effective_policy_hash": "c" * 64,
        }
        task.update(overrides)
        return task

    def test_a_dropped_accepted_task_is_refused_by_the_invariants_alone(self) -> None:
        """Each record parses; only the cross-generation invariant makes the chain unlawful."""
        task = self.accepted_task()
        run_id = new_id("review_run")
        first = self.gate(run_id, 1, None, accepted_tasks=(task,))
        digest = serialize.digest_of_text(ReviewStore.render(first))
        second = self.gate(run_id, 2, digest, accepted_tasks=())
        # both records parse on their own - the chain is what refuses them
        for record in (first, second):
            records.GateGeneration.from_record(record, "probe")
        self.both_refuse(run_id, [(1, first), (2, second)])

    def test_the_dropped_task_is_caught_by_nothing_else_in_the_reader(self) -> None:
        """The differential itself: neutralize ONLY ``_chain_invariants`` and the chain is accepted.

        This is what makes the previous test evidence rather than assertion. Every
        other layer - the path/record identity binding, the canonical parse, the
        ``previous_digest`` link - passes this chain, so the refusal it produces
        can only have come from the cross-generation invariants.
        """
        task = self.accepted_task()
        run_id = new_id("review_run")
        first = self.gate(run_id, 1, None, accepted_tasks=(task,))
        digest = serialize.digest_of_text(ReviewStore.render(first))
        second = self.gate(run_id, 2, digest, accepted_tasks=())
        entries, payloads = self.chain(run_id, [(1, first), (2, second)])
        self.refusal(lambda: self.capability(entries, payloads), "review_checkout_unsafe")
        with mock.patch.object(wc, "_chain_invariants", lambda *_: None):
            found = self.capability(entries, payloads)
        self.assertEqual(found.capability_contract, wc.WORK_CHECKOUT_CONTRACT)

    def test_a_carried_task_whose_descriptor_changed_is_refused(self) -> None:
        first_task = self.accepted_task()
        changed_task = {**first_task, "reviewer_version": "2"}
        run_id = new_id("review_run")
        first = self.gate(run_id, 1, None, accepted_tasks=(first_task,))
        digest = serialize.digest_of_text(ReviewStore.render(first))
        second = self.gate(run_id, 2, digest, accepted_tasks=(changed_task,))
        for record in (first, second):
            records.GateGeneration.from_record(record, "probe")
        self.both_refuse(run_id, [(1, first), (2, second)])


class ClosedActivationTests(CapabilityCase):
    """§7.9.4: the activation area holds exactly one canonical record path, and no other."""

    def activation_bytes(self) -> bytes:
        return ReviewStore.render(
            records.WorkTerminalActivation(
                operation_contract=records.OPERATION_CONTRACT_REVIEW_V1,
                activation_base_head="b" * 40, legacy_event_count=0,
                legacy_event_prefix_sha256=hashlib.sha256(b"").hexdigest(),
            ).to_record()
        ).encode("utf-8")

    def test_the_area_is_closed_by_p1s_own_rule_rather_than_a_restatement(self) -> None:
        import inspect

        self.assertIn("validate._activation", inspect.getsource(wc._require_closed_activation_area))
        # and P1's allowlist of modules that may name the activation path is left as P1 drew it
        source = Path(wc.__file__).read_text(encoding="utf-8")
        self.assertNotIn("WORK_TERMINAL_ACTIVATION_REL", source)

    def test_the_canonical_name_held_as_a_directory_is_refused(self) -> None:
        """Inherited from P1-REV-008 by calling it: the right name is not enough, it must be a plain file."""
        data = self.activation_bytes()
        nested = f"{review_paths.WORK_TERMINAL_ACTIVATION_REL}/child.yaml"
        self.refusal(lambda: self.capability([self.added(nested, data)], {nested: data}),
                     "review_checkout_unsafe")

    def test_the_one_canonical_activation_record_passes(self) -> None:
        data = self.activation_bytes()
        relative = review_paths.WORK_TERMINAL_ACTIVATION_REL
        found = self.capability([self.added(relative, data)], {relative: data})
        self.assertEqual(found.record_paths, (relative,))

    def test_an_unknown_activation_record_is_refused(self) -> None:
        data = self.activation_bytes()
        stray = f"{review_paths.ACTIVATION_DIR}/evil.yaml"
        error = self.refusal(lambda: self.capability([self.added(stray, data)], {stray: data}),
                             "review_checkout_unsafe")
        self.assertIn("evil.yaml", str(error))

    def test_an_unknown_activation_record_beside_the_valid_one_is_refused(self) -> None:
        data = self.activation_bytes()
        valid = review_paths.WORK_TERMINAL_ACTIVATION_REL
        stray = f"{review_paths.ACTIVATION_DIR}/evil.yaml"
        entries = [self.added(valid, data), self.added(stray, data)]
        self.refusal(lambda: self.capability(entries, {valid: data, stray: data}),
                     "review_checkout_unsafe")

    def test_a_nested_unknown_activation_entry_is_refused(self) -> None:
        data = self.activation_bytes()
        nested = f"{review_paths.ACTIVATION_DIR}/nested/evil.yaml"
        self.refusal(lambda: self.capability([self.added(nested, data)], {nested: data}),
                     "review_checkout_unsafe")

    def test_unknown_entries_in_every_other_subdirectory_stay_refused(self) -> None:
        data = b"schema: not-a-record\nversion: 1\n"
        for area in ("gates", "receipts", "consumptions", "supersessions",
                     "candidate-snapshots", "task-inputs"):
            with self.subTest(area=area):
                stray = f"{review_paths.REVIEW_DIR}/{area}/evil.yaml"
                self.refusal(lambda stray=stray: self.capability([self.added(stray, data)], {stray: data}),
                             "review_checkout_unsafe")


class UnsafeTreeStaysExpressibleTests(CapabilityCase):
    """§7.9.2 / §7.9.6: unauthorizable is not unrepresentable."""

    def unsafe_composition(self):
        data = CANONICAL_LINE.encode() + b"*.txt text\n"
        return self.rewritten_attributes(data), {".gitattributes": data}

    def test_an_unsafe_resulting_tree_still_builds_a_valid_context_whose_hash_does_not_move(self) -> None:
        entry, payloads = self.unsafe_composition()
        pre_tree = rt.root_tree_id(self.hermetic, self.base)
        with rt.composed(self.store, self.hermetic, self.base, [entry], payloads) as composition:
            activation = wctx.activation_binding("a" * 64, self.base)
            record = wctx.context_record(
                WORKSPACE, package_directory(WORKSPACE), activation, pre_tree, composition.tree
            )
            before = wctx.context_hash(record)
            self.refusal(
                lambda: wc.require_resulting_tree_capability(self.store, self.hermetic, composition),
                "review_checkout_unsafe",
            )
            after = wctx.context_hash(record)
        self.assertEqual(before, after)
        self.assertEqual(record["review_checkout_capability"]["resulting_tree"], composition.tree)
        wctx.require_context(record)

    def test_the_context_carries_no_verdict_whatever_the_capability_says(self) -> None:
        entry, payloads = self.unsafe_composition()
        pre_tree = rt.root_tree_id(self.hermetic, self.base)
        tree = rt.resulting_tree_id(self.store, self.hermetic, self.base, [entry], payloads)
        activation = wctx.activation_binding("a" * 64, self.base)
        record = wctx.context_record(WORKSPACE, package_directory(WORKSPACE), activation, pre_tree, tree)
        flattened = str(record)
        for forbidden in ("verdict", "capable", "authorized", "safe", "status"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, set(record["review_checkout_capability"]))
        self.assertNotIn("base_tree_verdict", flattened)
        self.assertNotIn("resulting_tree_verdict", flattened)


if __name__ == "__main__":
    unittest.main()
