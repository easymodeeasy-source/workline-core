"""The Work Review Context, version 2: what the Review is launched against.

P3 F3 §7.9.6, §7.9.7, F2 §10.1, §10.2, §10.3, §11, amendment A-4.

Version 2 adds exactly one field to F2 §10.1's nine and raises the version. The
field names the PROOF TARGET - which two trees, under which capability contract,
in which form, over which namespace - and never a verdict. The previous draft
carried ``base_tree_verdict`` and ``resulting_tree_verdict`` fixed at
``"capable"``, which made an unsafe resulting tree unrepresentable; that is
withdrawn, and these tests hold the withdrawal.

The strict reader is the other half. A version 1 record is not a Context of this
contract version and is never upgraded, a version 2 record is not readable as
version 1, and there is no tolerant unknown field in either direction.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from workline.errors import StopError
from workline.implementation import package_directory
from workline.review import serialize, work_context as wctx

WORKSPACE = Path(__file__).resolve().parents[1]
BASE_TREE = "a" * 40
RESULTING_TREE = "b" * 40
RECORD_DIGEST = "c" * 64
ACTIVATION_HEAD = "d" * 40
SHA256_TREE = "e" * 64


def activation() -> dict[str, str]:
    return wctx.activation_binding(RECORD_DIGEST, ACTIVATION_HEAD)


def record(base_tree: str = BASE_TREE, resulting_tree: str = RESULTING_TREE) -> dict:
    return wctx.context_record(
        WORKSPACE, package_directory(WORKSPACE), activation(), base_tree, resulting_tree
    )


class ContextCase(unittest.TestCase):
    def refusal(self, call, code: str = "review_context_invalid") -> StopError:
        with self.assertRaises(StopError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        return caught.exception


# --------------------------------------------------------------------------- the frozen record


class FrozenRecordTests(ContextCase):
    """§7.9.6 states the WHOLE replacement record, because the P1 reader is strict about fields."""

    def setUp(self) -> None:
        self.built = record()

    def test_the_schema_is_unchanged_and_the_version_is_two(self) -> None:
        self.assertEqual(self.built[serialize.SCHEMA_KEY], "review-work-context")
        self.assertEqual(self.built[serialize.VERSION_KEY], 2)

    def test_exactly_one_field_is_added_to_the_f2_record(self) -> None:
        """F2 §10.1 freezes ten keys; version 2 adds `review_checkout_capability` and nothing else."""
        f2_keys = {
            serialize.SCHEMA_KEY, serialize.VERSION_KEY, "review_kind", "review_contract",
            "projection_semantics_version", "adapter_identity", "loader_identity", "authority",
            "git_persistence", "activation",
        }
        self.assertEqual(len(f2_keys), 10)
        self.assertEqual(set(self.built), set(wctx.CONTEXT_FIELDS))
        self.assertEqual(set(wctx.CONTEXT_FIELDS) - f2_keys, {"review_checkout_capability"})
        self.assertEqual(f2_keys - set(wctx.CONTEXT_FIELDS), set())

    def test_the_nine_f2_fields_keep_their_names_and_meanings(self) -> None:
        self.assertEqual(self.built["review_kind"], "work-result-v1")
        self.assertEqual(self.built["review_contract"], "review-v1-work-v1")
        self.assertEqual(self.built["projection_semantics_version"], "work-result-projection-v1")
        self.assertEqual(self.built["adapter_identity"], "work-result-adapter-v1")
        self.assertEqual(len(self.built["loader_identity"]), 64)
        self.assertIsInstance(self.built["authority"], list)
        self.assertEqual(set(self.built["activation"]), set(wctx.ACTIVATION_FIELDS))

    def test_the_git_persistence_identity_is_the_amended_work_one(self) -> None:
        """F2 §10.3 as amended by A-7: same field, same meaning, new value."""
        self.assertEqual(self.built["git_persistence"], "review-v1-work-local-v2")
        self.assertNotEqual(self.built["git_persistence"], "review-v1-work-local-v1")
        self.assertNotEqual(self.built["git_persistence"], "review-v1-planning-local-v1")

    def test_planning_keeps_its_own_persistence_identity(self) -> None:
        from workline import mutation
        from workline.review import planning

        self.assertEqual(mutation.PLANNING_COMMIT_MODE, "review-v1-planning-local-v1")
        self.assertEqual(planning.GIT_PERSISTENCE, "review-v1-planning-local-v1")

    def test_the_capability_mapping_is_exactly_five_keys_none_nullable(self) -> None:
        capability = self.built["review_checkout_capability"]
        self.assertEqual(set(capability), set(wctx.CAPABILITY_FIELDS))
        self.assertEqual(len(capability), 5)
        for key, value in capability.items():
            with self.subTest(key=key):
                self.assertIsInstance(value, str)
                self.assertTrue(value)

    def test_the_capability_mapping_names_the_target_and_no_verdict(self) -> None:
        capability = self.built["review_checkout_capability"]
        self.assertEqual(capability["capability_contract"], "review-v1-work-checkout-capability-v1")
        self.assertEqual(capability["form"], "form-L")
        self.assertEqual(capability["namespace"], ".workline/review/**")
        self.assertEqual(capability["base_tree"], BASE_TREE)
        self.assertEqual(capability["resulting_tree"], RESULTING_TREE)
        for forbidden in ("base_tree_verdict", "resulting_tree_verdict", "capability_status",
                          "verdict", "safe", "authorized", "capable"):
            with self.subTest(field=forbidden):
                self.assertNotIn(forbidden, capability)
                self.assertNotIn(forbidden, self.built)

    def test_the_activation_binding_carries_no_second_source_of_truth(self) -> None:
        """F2 §11.2: the prefix digest and count are inside the record the digest covers."""
        found = self.built["activation"]
        self.assertEqual(found["operation_contract"], "review-v1")
        self.assertEqual(found["record_digest"], RECORD_DIGEST)
        self.assertEqual(found["activation_base_head"], ACTIVATION_HEAD)
        for forbidden in ("legacy_event_count", "legacy_event_prefix_sha256"):
            with self.subTest(field=forbidden):
                self.assertNotIn(forbidden, found)
                self.assertNotIn(forbidden, self.built)

    def test_the_record_is_canonical(self) -> None:
        self.assertTrue(serialize.canonical_roundtrips(self.built))


# --------------------------------------------------------------------------- the authority set


class AuthorityTests(ContextCase):
    """F2 §10.2: the Work authorities, and only those."""

    def test_the_work_authority_set_is_exactly_four(self) -> None:
        self.assertEqual(wctx.AUTHORITY_IDS, ("registry", "skills/start", "skills/review", "skills/create"))

    def test_planning_only_authorities_are_not_bound(self) -> None:
        """Binding them would make an unrelated planning edit invalidate every Work Review."""
        for excluded in ("skills/roadmap", "skills/phase-create", "skills/project-start", "skills/project-router"):
            with self.subTest(authority=excluded):
                self.assertNotIn(excluded, wctx.AUTHORITY_IDS)

    def test_the_planning_authority_set_is_not_copied(self) -> None:
        from workline.review import planning

        self.assertNotEqual(set(wctx.AUTHORITY_IDS), set(planning.AUTHORITY_IDS))
        self.assertIn("skills/start", wctx.AUTHORITY_IDS)
        self.assertNotIn("skills/start", planning.AUTHORITY_IDS)

    def test_each_authority_is_the_lf_digest_of_its_bytes(self) -> None:
        found = wctx.authority_digests(WORKSPACE)
        self.assertEqual([item["id"] for item in found], list(wctx.AUTHORITY_IDS))
        registry = (WORKSPACE / "registry.md").read_bytes()
        expected = hashlib.sha256(registry.replace(b"\r\n", b"\n")).hexdigest()
        self.assertEqual(found[0]["digest"], expected)
        for item in found:
            with self.subTest(authority=item["id"]):
                self.assertEqual(set(item), {"id", "digest"})
                self.assertEqual(len(item["digest"]), 64)

    def test_an_authority_that_cannot_be_read_is_never_silently_omitted(self) -> None:
        missing = WORKSPACE / "does-not-exist"
        self.refusal(lambda: wctx.authority_digests(missing), "review_context_unavailable")


class LoaderIdentityTests(ContextCase):
    """The content identity of the running implementation package."""

    def test_it_is_deterministic(self) -> None:
        directory = package_directory(WORKSPACE)
        self.assertEqual(wctx.loader_identity(directory), wctx.loader_identity(directory))
        self.assertEqual(len(wctx.loader_identity(directory)), 64)

    def test_it_is_the_work_schema_not_plannings(self) -> None:
        """The rule is the same; the record kind is Work's, so the Context is not coupled to planning."""
        from workline.review import planning

        self.assertEqual(wctx.SCHEMA_IMPLEMENTATION, "review-work-implementation")
        self.assertNotEqual(wctx.SCHEMA_IMPLEMENTATION, planning.SCHEMA_IMPLEMENTATION)

    def test_a_package_that_is_not_a_directory_is_refused(self) -> None:
        self.refusal(lambda: wctx.loader_identity(WORKSPACE / "README.md"), "review_context_unavailable")


# --------------------------------------------------------------------------- the hash


class ContextHashTests(ContextCase):
    """§7.9.6: the capability mapping is inside the canonical bytes, so the hash binds it."""

    def test_the_hash_is_the_digest_of_the_canonical_bytes(self) -> None:
        built = record()
        self.assertEqual(wctx.context_hash(built), serialize.digest(built))
        self.assertEqual(len(wctx.context_hash(built)), 64)

    def test_changing_the_resulting_tree_changes_the_hash(self) -> None:
        self.assertNotEqual(
            wctx.context_hash(record(resulting_tree="f" * 40)), wctx.context_hash(record())
        )

    def test_changing_the_base_tree_changes_the_hash(self) -> None:
        self.assertNotEqual(wctx.context_hash(record(base_tree="f" * 40)), wctx.context_hash(record()))

    def test_the_same_inputs_give_the_same_hash(self) -> None:
        self.assertEqual(wctx.context_hash(record()), wctx.context_hash(record()))

    def test_a_record_that_does_not_validate_is_never_hashed(self) -> None:
        broken = dict(record())
        broken.pop("activation")
        self.refusal(lambda: wctx.context_hash(broken))


# --------------------------------------------------------------------------- strict validation


class StrictValidationTests(ContextCase):
    """No tolerant unknown field, no upgrade path, and no nullable nested key."""

    def test_a_valid_record_passes(self) -> None:
        wctx.require_context(record())

    def test_a_version_one_record_is_not_a_context_of_this_contract_version(self) -> None:
        """§7.9.6: a v1 record cannot silently pass as v2, and is never upgraded."""
        v1 = dict(record())
        v1[serialize.VERSION_KEY] = 1
        v1.pop("review_checkout_capability")
        error = self.refusal(lambda: wctx.require_context(v1))
        self.assertIn("version", str(error))

    def test_a_version_one_shaped_record_is_not_completed_by_inference(self) -> None:
        v1 = dict(record())
        v1[serialize.VERSION_KEY] = 1
        self.refusal(lambda: wctx.require_context(v1))

    def test_a_version_three_record_is_refused(self) -> None:
        future = dict(record())
        future[serialize.VERSION_KEY] = 3
        self.refusal(lambda: wctx.require_context(future))

    def test_an_extra_top_level_field_is_refused(self) -> None:
        extended = dict(record())
        extended["checkout_capability"] = "review-v1-planning-checkout-v1"
        self.refusal(lambda: wctx.require_context(extended))

    def test_a_missing_top_level_field_is_refused(self) -> None:
        for field in wctx.CONTEXT_FIELDS:
            with self.subTest(field=field):
                short = {key: value for key, value in record().items() if key != field}
                self.refusal(lambda short=short: wctx.require_context(short))

    def test_a_wrong_frozen_identity_is_refused(self) -> None:
        for field, wrong in (
            (serialize.SCHEMA_KEY, "review-planning-context"),
            ("review_kind", "planning-roadmap-v1"),
            ("review_contract", "review-v1-planning-v1"),
            ("projection_semantics_version", "planning-projection-v1"),
            ("adapter_identity", "planning-adapter-v1"),
            ("git_persistence", "review-v1-work-local-v1"),
            ("git_persistence", "review-v1-planning-local-v1"),
        ):
            with self.subTest(field=field, wrong=wrong):
                broken = dict(record())
                broken[field] = wrong
                self.refusal(lambda broken=broken: wctx.require_context(broken))

    def test_a_capability_mapping_of_the_wrong_shape_is_refused(self) -> None:
        for label, capability in (
            ("extra key", {**record()["review_checkout_capability"], "verdict": "capable"}),
            ("missing key", {k: v for k, v in record()["review_checkout_capability"].items() if k != "form"}),
            ("null value", {**record()["review_checkout_capability"], "resulting_tree": None}),
            ("not a mapping", "form-L"),
        ):
            with self.subTest(case=label):
                broken = dict(record())
                broken["review_checkout_capability"] = capability
                self.refusal(lambda broken=broken: wctx.require_context(broken))

    def test_a_wrong_capability_identity_is_refused(self) -> None:
        for field, wrong in (
            ("capability_contract", "review-v1-planning-checkout-v1"),
            ("form", "form-M"),
            ("namespace", ".workline/**"),
        ):
            with self.subTest(field=field):
                broken = dict(record())
                broken["review_checkout_capability"] = {**broken["review_checkout_capability"], field: wrong}
                self.refusal(lambda broken=broken: wctx.require_context(broken))

    def test_a_tree_identity_that_is_not_a_full_object_id_is_refused(self) -> None:
        for field in ("base_tree", "resulting_tree"):
            for wrong in ("HEAD", "main", BASE_TREE[:12], BASE_TREE.upper(), BASE_TREE + "0", "", None, 1):
                with self.subTest(field=field, value=wrong):
                    broken = dict(record())
                    broken["review_checkout_capability"] = {**broken["review_checkout_capability"], field: wrong}
                    self.refusal(lambda broken=broken: wctx.require_context(broken))

    def test_both_object_widths_are_accepted_for_a_tree_identity(self) -> None:
        wctx.require_context(record(base_tree=SHA256_TREE, resulting_tree=SHA256_TREE))
        self.assertEqual(len(record(base_tree=SHA256_TREE)["review_checkout_capability"]["base_tree"]), 64)

    def test_a_malformed_activation_binding_is_refused(self) -> None:
        for label, binding in (
            ("extra key", {**activation(), "legacy_event_count": 3}),
            ("missing key", {k: v for k, v in activation().items() if k != "record_digest"}),
            ("wrong operation contract", {**activation(), "operation_contract": "review-v2"}),
            ("short digest", {**activation(), "record_digest": "abc"}),
            ("bad base head", {**activation(), "activation_base_head": "HEAD"}),
            ("not a mapping", "review-v1"),
        ):
            with self.subTest(case=label):
                broken = dict(record())
                broken["activation"] = binding
                self.refusal(lambda broken=broken: wctx.require_context(broken))

    def test_an_invalid_authority_list_is_refused(self) -> None:
        good = record()["authority"]
        for label, authority in (
            ("reordered", list(reversed(good))),
            ("planning set", [{"id": "skills/roadmap", "digest": "a" * 64}]),
            ("extra entry", good + [{"id": "skills/roadmap", "digest": "a" * 64}]),
            ("extra key", [{**good[0], "path": "x"}] + good[1:]),
            ("short digest", [{**good[0], "digest": "abc"}] + good[1:]),
            ("not a list", "registry"),
        ):
            with self.subTest(case=label):
                broken = dict(record())
                broken["authority"] = authority
                self.refusal(lambda broken=broken: wctx.require_context(broken))

    def test_a_loader_identity_that_is_not_a_digest_is_refused(self) -> None:
        broken = dict(record())
        broken["loader_identity"] = "not a digest"
        self.refusal(lambda: wctx.require_context(broken))

    def test_something_that_is_not_a_mapping_is_refused(self) -> None:
        for value in (None, "review-work-context", 2, ["review-work-context"]):
            with self.subTest(value=value):
                self.refusal(lambda value=value: wctx.require_context(value))


# --------------------------------------------------------------------------- digest shape


class DigestShapeTests(ContextCase):
    """A canonical identity field holds a SHA-256 digest, not a 64-character string.

    Length alone is not the shape. ``"z" * 64`` is sixty-four characters and is
    not a digest of anything; neither is the uppercase spelling of a real one,
    which would make the same identity hash two different ways. Every one of
    these is a value the builder can never produce, and a strict reader that
    accepts what its builder cannot produce is not validating the field.
    """

    #: Right length, wrong alphabet or wrong case; then wrong length; then not text at all.
    NOT_DIGESTS = (
        "z" * 64,
        "A" * 64,
        "!" * 64,
        "a" * 63 + "g",
        "0123456789ABCDEF" * 4,
        hashlib.sha256(b"x").hexdigest().upper(),
        "a" * 63,
        "a" * 65,
        "",
        None,
        1,
        ["a" * 64],
    )

    def test_loader_identity_takes_a_digest_and_nothing_else(self) -> None:
        for wrong in self.NOT_DIGESTS:
            with self.subTest(value=wrong):
                broken = dict(record())
                broken["loader_identity"] = wrong
                self.refusal(lambda broken=broken: wctx.require_context(broken))

    def test_an_authority_digest_takes_a_digest_and_nothing_else(self) -> None:
        for wrong in self.NOT_DIGESTS:
            with self.subTest(value=wrong):
                broken = dict(record())
                good = broken["authority"]
                broken["authority"] = [{**good[0], "digest": wrong}] + list(good[1:])
                self.refusal(lambda broken=broken: wctx.require_context(broken))

    def test_the_activation_record_digest_takes_a_digest_and_nothing_else(self) -> None:
        for wrong in self.NOT_DIGESTS:
            with self.subTest(value=wrong):
                broken = dict(record())
                broken["activation"] = {**activation(), "record_digest": wrong}
                self.refusal(lambda broken=broken: wctx.require_context(broken))

    def test_the_activation_binding_refuses_the_same_values_when_it_is_built(self) -> None:
        """Not only on the way in: a Context is never BUILT around a non-digest either."""
        for wrong in self.NOT_DIGESTS:
            with self.subTest(value=wrong):
                self.refusal(lambda wrong=wrong: wctx.activation_binding(wrong, ACTIVATION_HEAD))

    def test_a_real_lowercase_digest_is_accepted_everywhere(self) -> None:
        digest = hashlib.sha256(b"a real one").hexdigest()
        built = dict(record())
        built["activation"] = {**activation(), "record_digest": digest}
        wctx.require_context(built)
        # what production itself builds keeps passing untouched
        found = record()
        wctx.require_context(found)
        self.assertRegex(found["loader_identity"], r"^[0-9a-f]{64}$")
        for item in found["authority"]:
            self.assertRegex(item["digest"], r"^[0-9a-f]{64}$")


# --------------------------------------------------------------------------- the unit boundary


class UnitBoundaryTests(unittest.TestCase):
    """Unit 4 builds the Context; nothing dispatches it, seals with it or reserves anything."""

    def test_nothing_in_production_dispatches_the_work_context(self) -> None:
        from workline import gitops, mutation, roadmap_review, start
        from workline.review import checkout, planning, publication

        for module in (gitops, mutation, roadmap_review, start, checkout, planning, publication):
            with self.subTest(module=module.__name__):
                self.assertFalse(hasattr(module, "work_context"))

    def test_no_consumption_identifier_is_reserved(self) -> None:
        """§7.9.4: form-L covers a future path without knowing its name."""
        import inspect

        source = inspect.getsource(wctx)
        self.assertNotIn("consumption_id", source)
        self.assertNotIn("reserve", source)

    def test_later_unit_machinery_is_still_absent(self) -> None:
        from workline import mutation

        self.assertFalse(hasattr(mutation, "WORK_COMMIT_MODE"))
        for name in ("CommitTreePlan", "prepared_commit_id", "seal", "issue_receipt"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(wctx, name))


if __name__ == "__main__":
    unittest.main()
