"""The Work Review Context, version 2: what the Review is launched against (``F3`` §7.9.6).

F2 §10.1 froze a nine-field record. A-4 adds exactly one field and raises the
version, and §7.9.6 states the whole replacement record because the P1 reader is
strict about unknown fields - a partial description would not be
implementation-complete:

```text
{
  schema:  "review-work-context"        version: 2
  review_kind:                  "work-result-v1"
  review_contract:              "review-v1-work-v1"
  projection_semantics_version: "work-result-projection-v1"
  adapter_identity:             "work-result-adapter-v1"
  loader_identity:              <content identity of the running implementation package>
  authority:                    [ {id, digest} ... ]              F2 §10.2, unchanged
  git_persistence:              "review-v1-work-local-v2"         F2 §10.3 as amended by A-7
  activation:                   <the activation binding of F2 §11>
  review_checkout_capability: {
      capability_contract: "review-v1-work-checkout-capability-v1"
      form:                "form-L"
      namespace:           ".workline/review/**"
      base_tree:           <the full object id of PRE_S_C0_BASE's tree>
      resulting_tree:      <the full object id of the resulting tree, §7.9.2>
  }
}
```

**The Context binds the PROOF TARGET, never a passing verdict.** The previous
draft carried ``base_tree_verdict`` and ``resulting_tree_verdict``, both fixed at
``"capable"``. That was a defect: it made an unsafe resulting tree
*unrepresentable*, so such a Candidate could never build a Context, never reach
generation 1 and never be reviewed - contradicting §7.9.2's boundary that it
stays expressible and reviewable. Withdrawn. No verdict is a field here, so
every capability outcome - capable, unsafe, unknown - yields the SAME valid,
immutable Context.

**The two trees are different things.** ``base_tree`` is the ROOT TREE of
``PRE_S_C0_BASE`` - the committed HEAD immediately BEFORE S-c0 - and not its
commit id and not ``declared_base.base_commit``. ``resulting_tree`` is the tree
the frozen Candidate produces over ``declared_base``. §7.1.11 proves the two
bases carry the same attribute-source state; it does not make their tree
identities equal.

``review_context_hash`` is the SHA-256 of the canonical bytes of the whole
version 2 record, computed exactly as F2 §10.1 computes it for version 1. The
capability mapping is inside those bytes, so changing either tree id changes the
hash - and changing a verdict is impossible, because there is none.

A version 1 record is NOT a Context of this contract version, and a version 2
record is not readable as version 1. There is no upgrade path and no tolerant
unknown field: a Run whose Context is v1 is not a Run of the review-v1 Work
contract F3 freezes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .. import gitcmd
from ..errors import StopError
from . import serialize

#: The record kind, unchanged from F2 §10.1: the same kind, at a new version.
SCHEMA_CONTEXT = "review-work-context"
CONTEXT_VERSION = 2

#: The schema the loader identity digests under. Work's own, so the Work Context is never
#: coupled to planning's record semantics.
SCHEMA_IMPLEMENTATION = "review-work-implementation"
IMPLEMENTATION_VERSION = 1

#: The frozen identities of ``F3`` §7.9.6 / F2 §4.3.
REVIEW_KIND = "work-result-v1"
REVIEW_CONTRACT = "review-v1-work-v1"
PROJECTION_SEMANTICS_VERSION = "work-result-projection-v1"
ADAPTER_IDENTITY = "work-result-adapter-v1"

#: F2 §10.3 as amended by A-7: same field, same meaning, new value. P2 planning keeps
#: ``review-v1-planning-local-v1``, which this never redefines.
GIT_PERSISTENCE = "review-v1-work-local-v2"

#: The Work authority set of F2 §10.2, in the contract's order, and ONLY these.
#: ``skills/roadmap`` and ``skills/phase-create`` own planning and cannot affect what a Work result
#: means; binding them would make an unrelated planning edit invalidate every Work Review. The four
#: ``rules/*`` need no entry of their own - measured, their text lives inside ``registry.md`` (M-7).
AUTHORITY_IDS = ("registry", "skills/start", "skills/review", "skills/create")

#: The operation contract the activation binding carries in the clear (F2 §11.2).
OPERATION_CONTRACT = "review-v1"

#: The fields of the whole record, and of the nested mapping. Exactly these, none nullable.
CONTEXT_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "review_kind", "review_contract",
    "projection_semantics_version", "adapter_identity", "loader_identity", "authority",
    "git_persistence", "activation", "review_checkout_capability",
)
CAPABILITY_FIELDS = ("capability_contract", "form", "namespace", "base_tree", "resulting_tree")
ACTIVATION_FIELDS = ("record_digest", "operation_contract", "activation_base_head")


def _unavailable(message: str) -> StopError:
    return StopError(f"the Work review Context cannot be computed: {message}", code="review_context_unavailable")


def _invalid(message: str) -> StopError:
    return StopError(f"the Work review Context is not of this contract version: {message}",
                     code="review_context_invalid")


def _lf_digest(data: bytes) -> str:
    """SHA-256 of bytes with CRLF read as LF - the same rule F2 §10.2 and P2 both use."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def authority_digests(workline_root: Path) -> list[dict[str, str]]:
    """``registry.md`` and the three Work Skills, each digested under the F2 §10.2 rule."""
    from ..registry import resolve_skill

    found: list[dict[str, str]] = []
    for authority_id in AUTHORITY_IDS:
        try:
            if authority_id == "registry":
                path = Path(workline_root) / "registry.md"
            else:
                path = resolve_skill(Path(workline_root), authority_id).path
            data = Path(path).read_bytes()
        except (OSError, StopError) as exc:
            raise _unavailable(f"{authority_id} cannot be resolved or read: {exc}") from exc
        found.append({"id": authority_id, "digest": _lf_digest(data)})
    return found


def loader_identity(package_directory: Path) -> str:
    """The content identity of the running implementation package: every ``*.py`` under it, CRLF as LF.

    A Work-side equivalent rather than a call into planning's: that function
    digests under ``review-planning-implementation``, which is planning's record
    semantics, and the Work Context must not be coupled to them. The rule is the
    same, so the value is deterministic for a given package.
    """
    directory = Path(package_directory)
    if not directory.is_dir():
        raise _unavailable(f"the implementation package {directory} is not a directory")
    files: list[dict[str, str]] = []
    try:
        for path in sorted(directory.rglob("*.py")):
            relative = PurePosixPath(directory.name) / PurePosixPath(path.relative_to(directory).as_posix())
            files.append({"path": str(relative), "digest": _lf_digest(path.read_bytes())})
    except OSError as exc:
        raise _unavailable(f"the implementation package cannot be read: {exc}") from exc
    files.sort(key=lambda item: item["path"])
    return serialize.digest({
        serialize.SCHEMA_KEY: SCHEMA_IMPLEMENTATION,
        serialize.VERSION_KEY: IMPLEMENTATION_VERSION,
        "files": files,
    })


def _require_full_oid(value: object, described: str) -> str:
    if not gitcmd.full_commit_id(value):
        raise _invalid(f"{described} is {value!r}, which is not a full lowercase 40- or 64-character object id")
    assert isinstance(value, str)
    return value


def capability_binding(base_tree: str, resulting_tree: str) -> dict[str, str]:
    """The nested mapping of exactly five keys (``F3`` §7.9.6).

    ``base_tree`` is PRE_S_C0_BASE's ROOT TREE id; ``resulting_tree`` is the id
    the composition returned. Both are tree identities, and the distinction from
    a commit id is not cosmetic: a commit id here would bind the wrong object and
    the seal would prove the wrong thing.
    """
    from .work_checkout import FORM_IDENTITY, REVIEW_NAMESPACE, WORK_CHECKOUT_CONTRACT

    return {
        "capability_contract": WORK_CHECKOUT_CONTRACT,
        "form": FORM_IDENTITY,
        "namespace": REVIEW_NAMESPACE,
        "base_tree": _require_full_oid(base_tree, "review_checkout_capability.base_tree"),
        "resulting_tree": _require_full_oid(resulting_tree, "review_checkout_capability.resulting_tree"),
    }


def activation_binding(record_digest: str, activation_base_head: str) -> dict[str, str]:
    """The activation binding of F2 §11.2, exactly three keys.

    ``legacy_event_count`` and ``legacy_event_prefix_sha256`` are NOT copied out:
    they are inside the record the digest covers, and copying them would create
    the second source of truth F1 prohibits.
    """
    if not isinstance(record_digest, str) or len(record_digest) != 64 or not all(
        character in "0123456789abcdef" for character in record_digest
    ):
        raise _invalid(f"the activation record digest {record_digest!r} is not a SHA-256 digest")
    return {
        "record_digest": record_digest,
        "operation_contract": OPERATION_CONTRACT,
        "activation_base_head": _require_full_oid(activation_base_head, "activation.activation_base_head"),
    }


def context_record(
    workline_root: Path,
    package_directory: Path,
    activation: Mapping[str, str],
    base_tree: str,
    resulting_tree: str,
) -> dict[str, Any]:
    """The whole Work Review Context v2 record, canonicalized.

    Built WHATEVER the resulting tree's capability turns out to be: the Context
    names which trees must be proven, under which capability contract, in which
    form, over which namespace - and claims nothing about whether either already
    passed (§7.9.6).
    """
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_CONTEXT,
        serialize.VERSION_KEY: CONTEXT_VERSION,
        "review_kind": REVIEW_KIND,
        "review_contract": REVIEW_CONTRACT,
        "projection_semantics_version": PROJECTION_SEMANTICS_VERSION,
        "adapter_identity": ADAPTER_IDENTITY,
        "loader_identity": loader_identity(package_directory),
        "authority": authority_digests(workline_root),
        "git_persistence": GIT_PERSISTENCE,
        "activation": _require_activation(activation),
        "review_checkout_capability": capability_binding(base_tree, resulting_tree),
    })


def context_hash(record: Mapping[str, Any]) -> str:
    """``SHA-256`` of the canonical bytes of the whole record, as F2 §10.1 computes it for version 1."""
    require_context(record)
    return serialize.digest(dict(record))


def _require_activation(activation: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(activation, Mapping) or set(activation) != set(ACTIVATION_FIELDS):
        raise _invalid(f"the activation binding must carry exactly {sorted(ACTIVATION_FIELDS)}")
    if activation["operation_contract"] != OPERATION_CONTRACT:
        raise _invalid(
            f"the activation binding names the operation contract {activation['operation_contract']!r}, "
            f"not {OPERATION_CONTRACT!r}"
        )
    return activation_binding(activation["record_digest"], activation["activation_base_head"])


def require_context(record: Mapping[str, Any]) -> None:
    """Strictly validate a Work Context v2; anything else is refused rather than adapted.

    No tolerant unknown field, no v1 to v2 upgrade and no v2 read as v1. A record
    whose field set does not match its version exactly is not a Context of this
    contract version, and inferring ``review_checkout_capability`` for a v1
    record would invent the very claim the version exists to state.
    """
    if not isinstance(record, Mapping):
        raise _invalid("the Context is not a mapping")
    if record.get(serialize.SCHEMA_KEY) != SCHEMA_CONTEXT:
        raise _invalid(f"the schema is {record.get(serialize.SCHEMA_KEY)!r}, not {SCHEMA_CONTEXT!r}")
    if record.get(serialize.VERSION_KEY) != CONTEXT_VERSION:
        raise _invalid(
            f"the version is {record.get(serialize.VERSION_KEY)!r}; a Context at another version is not a "
            f"Context of this contract version and is never upgraded"
        )
    unknown, missing = set(record) - set(CONTEXT_FIELDS), set(CONTEXT_FIELDS) - set(record)
    if unknown or missing:
        raise _invalid(
            "the field set does not match version 2 exactly"
            + (f"; unexpected {sorted(unknown)}" if unknown else "")
            + (f"; missing {sorted(missing)}" if missing else "")
        )
    for field, expected in (
        ("review_kind", REVIEW_KIND),
        ("review_contract", REVIEW_CONTRACT),
        ("projection_semantics_version", PROJECTION_SEMANTICS_VERSION),
        ("adapter_identity", ADAPTER_IDENTITY),
        ("git_persistence", GIT_PERSISTENCE),
    ):
        if record[field] != expected:
            raise _invalid(f"{field} is {record[field]!r}, not {expected!r}")
    if not isinstance(record["loader_identity"], str) or len(record["loader_identity"]) != 64:
        raise _invalid("loader_identity is not a SHA-256 digest")
    _require_authority(record["authority"])
    _require_activation(record["activation"])
    _require_capability(record["review_checkout_capability"])


def _require_authority(authority: object) -> None:
    if not isinstance(authority, list) or [
        item.get("id") if isinstance(item, Mapping) else None for item in authority
    ] != list(AUTHORITY_IDS):
        raise _invalid(f"the authority list must be exactly {list(AUTHORITY_IDS)}, in that order")
    for item in authority:
        if set(item) != {"id", "digest"}:
            raise _invalid("an authority entry must carry exactly id and digest")
        if not isinstance(item["digest"], str) or len(item["digest"]) != 64:
            raise _invalid(f"the digest of {item['id']} is not a SHA-256 digest")


def _require_capability(capability: object) -> None:
    from .work_checkout import FORM_IDENTITY, REVIEW_NAMESPACE, WORK_CHECKOUT_CONTRACT

    if not isinstance(capability, Mapping) or set(capability) != set(CAPABILITY_FIELDS):
        raise _invalid(f"review_checkout_capability must carry exactly {sorted(CAPABILITY_FIELDS)}")
    for field, expected in (
        ("capability_contract", WORK_CHECKOUT_CONTRACT),
        ("form", FORM_IDENTITY),
        ("namespace", REVIEW_NAMESPACE),
    ):
        if capability[field] != expected:
            raise _invalid(f"review_checkout_capability.{field} is {capability[field]!r}, not {expected!r}")
    _require_full_oid(capability["base_tree"], "review_checkout_capability.base_tree")
    _require_full_oid(capability["resulting_tree"], "review_checkout_capability.resulting_tree")
