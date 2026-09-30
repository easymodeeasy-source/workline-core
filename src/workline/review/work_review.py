"""Work Review (P3 F2 / F3): the review-v1 Work identities, records and reviewer contract.

Review-owned and inert, exactly as :mod:`workline.review.planning` is for P2: this
module reads, validates and renders. It holds no lock, opens no mutation, writes
no file and decides nothing about whether a Work completes - START owns that
(:mod:`workline.start_review`). What it fixes is the meaning of what a Work Review
Run records (``F2`` §4 - §15, as amended by ``F3`` §1.5):

```text
identities        the Work kind, its slot, stage, keys and contract strings (F2 §4)
Candidate         review-work-candidate: the reviewed artifact, declared base, activation (F2 §5 - §7, A-3)
snapshot material review-v1-work-snapshot-material-v1: the clone-safe payload envelope (F2 §9)
request envelope  review-work-request: the whole Candidate and Context (F2 §12.3)
Policy            review-work-policy: one static record, one required slot (F2 §10.4)
report            review-work-report: what the reviewer returned, and its result digest
adjudication      mechanical: the reviewer's severity is final, HIGH and MID block
Evidence          review-work-evidence: the frozen checks, the isolated verification and the
                  validity closure's digest (F2 §13 - §14)
```

Every record is canonical data under the P1 serializer, so each digest is a
statement about the canonical bytes a reader reproduces. The Work kind shares
the P1 records (``CandidateSnapshot``, ``TaskInput``, ``GateGeneration``,
``Receipt``) with planning, and nothing else: none of planning's record
semantics are reused, so a planning change can never silently redefine what a
Work Review was validated under.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
from typing import Any, Callable, Mapping, Sequence

from ..errors import ReconcileRequired, StopError, ValidationError
from . import closure, records, serialize
from . import work_context

# --------------------------------------------------------------------------- static identities (F2 §4.1)

REVIEW_KIND = work_context.REVIEW_KIND
REVIEW_CONTRACT = work_context.REVIEW_CONTRACT
PROJECTION_SEMANTICS_VERSION = work_context.PROJECTION_SEMANTICS_VERSION
ADAPTER_IDENTITY = work_context.ADAPTER_IDENTITY
TASK_KIND = "work-result-review-v1"
TASK_SLOT = "work-result-reviewer"
AUTHORIZED_OPERATION_STAGE = "start:work-terminal"
POLICY_ID = "review-v1-work-policy-v1"
INSTRUCTION = "review-v1-work-instruction-v1"
ADJUDICATION_RULE = "review-v1-work-adjudication-v1"
MATERIAL_CONTRACT = "review-v1-work-snapshot-material-v1"
PAYLOAD_ENCODING = "base64-rfc4648-v1"

#: The isolated verifier's own identity and version, which the Evidence identity binds (F2 §13.4 V-4).
VERIFIER_IDENTITY = "work-result-isolated-verifier"
VERIFIER_VERSION = "v1"
#: The mechanism identity every closure proof and dependency declaration of the Work kind names.
CLOSURE_MECHANISM = "work-result-closure"
CLOSURE_MECHANISM_VERSION = "v1"

SCHEMA_REQUEST_IDENTITY = "review-work-request-identity"
SCHEMA_CANDIDATE = "review-work-candidate"
SCHEMA_REQUEST = "review-work-request"
SCHEMA_POLICY = "review-work-policy"
SCHEMA_REPORT = "review-work-report"
SCHEMA_ADJUDICATION = "review-work-adjudication"
SCHEMA_OBLIGATIONS = "review-work-obligations"
SCHEMA_COVERAGE = "review-work-coverage"
SCHEMA_REPORT_SET = "review-work-report-set"
SCHEMA_EVIDENCE = "review-work-evidence"
SCHEMA_EVIDENCE_PAYLOAD = "review-work-evidence-payload"
SCHEMA_VERIFICATION = "review-work-isolated-verification"

RECORD_VERSION = 1
OPERATION = "start"

#: The two artifact kinds (F2 §6.1, §7.2 as amended by A-3). There is no third.
ARTIFACT_RESULT = "result_commit"
ARTIFACT_EMPTY = "empty"

#: The generation of a Work Run that seals, and the only one that issues a Receipt.
SEAL_GENERATION = 3

#: The object kinds and the modes each may take (F2 §6.3, §6.4). The Git tree entry is authoritative.
KIND_MODES: Mapping[str, tuple[str, ...]] = {
    "absent": ("000000",),
    "file": ("100644", "100755"),
    "symlink": ("120000",),
    "gitlink": ("160000",),
}
BYTE_KINDS = ("file", "symlink")
ENTRY_FIELDS = (
    "path", "status", "old_kind", "old_mode", "old_oid", "new_kind", "new_mode", "new_oid", "content_sha256",
)
_KIND_OF_MODE = {"100644": "file", "100755": "file", "120000": "symlink", "160000": "gitlink"}


def _unavailable(message: str) -> StopError:
    """F2 §6.5: the declared owned set cannot be projected exactly."""
    return StopError(f"the Work Candidate cannot be projected exactly: {message}; nothing is reviewed: STOP",
                     code="review_candidate_unavailable")


def _material_mismatch(message: str) -> ReconcileRequired:
    """F2 §9.7: every snapshot mismatch is reconcile_required, and nothing is substituted."""
    return ReconcileRequired(f"the Work Candidate snapshot is not valid reconstruction material: {message}: "
                             "reconcile required")


def _utf8(path: str) -> bytes:
    return path.encode("utf-8", "surrogatepass")


def git_blob_id(data: bytes, width: int) -> str:
    """Git's blob identity of ``data`` in the repository's own object format: SHA-1 at 40, SHA-256 at 64 (F2 §9.5)."""
    header = b"blob %d\0" % len(data)
    if width == 40:
        return hashlib.sha1(header + data).hexdigest()
    if width == 64:
        return hashlib.sha256(header + data).hexdigest()
    raise ValidationError(f"no Git object format has {width}-character ids", code="review_record_invalid")


# --------------------------------------------------------------------------- the selector and the reviewer interface (F1-D1, F2 §12)


@dataclass(frozen=True)
class WorkReviewFinding:
    severity: str  # HIGH | MID | LOW
    code: str      # non-empty, stripped, no line break
    message: str


@dataclass(frozen=True)
class WorkReviewReport:
    task_id: str
    reviewer_identity: str
    reviewer_version: str
    status: str  # completed | declined
    findings: tuple[WorkReviewFinding, ...] = ()


@dataclass(frozen=True)
class WorkReviewTask:
    task_id: str
    task_slot: str
    task_kind: str
    review_kind: str
    request_envelope: dict[str, Any]
    request_digest: str
    candidate_hash: str
    review_context_hash: str
    effective_policy_hash: str


@dataclass(frozen=True)
class WorkReview:
    """The review-v1 START selector: ``start(..., review=WorkReview(...))`` (F1-D1).

    A versioned contract string, never a flag: it selects the review-v1 Work
    START contract, whose durable markers START writes at mutation open. The
    reviewer identity and version are bound at the gate (F2 §12.1) and never
    in the START invocation.
    """

    reviewer: Callable[[WorkReviewTask], WorkReviewReport]
    reviewer_identity: str
    reviewer_version: str
    contract: str = REVIEW_CONTRACT


def _single_line_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip() and value.splitlines() == [value]


def _persistable_reviewer_text(value: object) -> bool:
    """Single-line text the canonical Review form carries and reads back as itself (F1-D1 item 3)."""
    if not _single_line_text(value):
        return False
    holder = {"reviewer_text": value}
    try:
        serialize.canonical_bytes(holder)
        return serialize.canonical_roundtrips(holder)
    except (ValidationError, ValueError, UnicodeError):
        return False


def validate_work_review(review: object) -> WorkReview:
    """The ``review`` argument, validated before the lock and before any Project state is read (F1-D1 item 4)."""
    if type(review) is not WorkReview:
        raise ValidationError(f"review must be a WorkReview, not {type(review).__name__}", code="review_contract_invalid")
    problems: list[str] = []
    if not isinstance(review.contract, str) or review.contract != REVIEW_CONTRACT:
        problems.append(f"contract {review.contract!r} is not {REVIEW_CONTRACT!r}")
    if not callable(review.reviewer):
        problems.append("reviewer is not callable")
    for name in ("reviewer_identity", "reviewer_version"):
        value = getattr(review, name)
        if _persistable_reviewer_text(value):
            continue
        problems.append(
            f"{name} must be non-empty single-line text without surrounding whitespace"
            if not _single_line_text(value)
            else f"{name} is text the canonical Review form cannot carry, so the accepted task could not record it"
        )
    if problems:
        raise ValidationError("invalid WorkReview: " + "; ".join(problems), code="review_contract_invalid")
    return review


# --------------------------------------------------------------------------- operation identity (F2 §4.2)


def request_identity_record(work_id: str) -> dict[str, Any]:
    return {
        serialize.SCHEMA_KEY: SCHEMA_REQUEST_IDENTITY, serialize.VERSION_KEY: RECORD_VERSION,
        "work_id": work_id, "review_contract": REVIEW_CONTRACT,
    }


def operation_identity(work_id: str) -> str:
    """``"start:" + SHA-256`` of the request identity record; the START mode is deliberately not in it."""
    return f"{OPERATION}:{serialize.digest(request_identity_record(work_id))}"


# --------------------------------------------------------------------------- Candidate entries (F2 §6.3)


def changing(entry: Mapping[str, Any]) -> bool:
    """An entry is CHANGING when any of its old kind, mode or id differs from the new one (F3 §6.7)."""
    return (entry["old_kind"], entry["old_mode"], entry["old_oid"]) != (entry["new_kind"], entry["new_mode"], entry["new_oid"])


def candidate_entry(
    path: str,
    old: tuple[str, str] | None,
    new_kind: str,
    new_mode: str,
    new_oid: str | None,
    content: bytes | None,
    width: int,
) -> dict[str, Any]:
    """One F2 §6.3 entry: ``old`` is the base tree's ``(mode, oid)`` at ``path`` or ``None``, the rest the witness.

    The Git tree entry is authoritative for the old side, and the bound witness
    for the new one; nothing here reads the filesystem.
    """
    zero = "0" * width
    if old is None:
        old_kind, old_mode, old_oid = "absent", "000000", zero
    else:
        old_mode, old_oid = old
        old_kind = _KIND_OF_MODE.get(old_mode)
        if old_kind is None:
            raise _unavailable(f"the base tree holds {path!r} with mode {old_mode}, which no Candidate kind names")
    if new_kind == "absent":
        if old is None:
            raise _unavailable(f"{path!r} is declared deleted and the base tree does not hold it")
        new_mode, new_oid = "000000", zero
    if new_kind not in KIND_MODES or new_mode not in KIND_MODES[new_kind]:
        raise _unavailable(f"{path!r} would be {new_kind} {new_mode}, which is not a Candidate kind and mode")
    if not isinstance(new_oid, str) or len(new_oid) != width:
        raise _unavailable(f"{path!r} names no full {width}-character object id")
    if new_kind in BYTE_KINDS:
        if content is None:
            raise _unavailable(f"{path!r} is a {new_kind} whose bytes were not bound")
        digest = hashlib.sha256(content).hexdigest()
    else:
        digest = None
    status = "A" if old_kind == "absent" else "D" if new_kind == "absent" else "M"
    return {
        "path": path, "status": status,
        "old_kind": old_kind, "old_mode": old_mode, "old_oid": old_oid,
        "new_kind": new_kind, "new_mode": new_mode, "new_oid": new_oid,
        "content_sha256": digest,
    }


def sorted_entries(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted((dict(entry) for entry in entries), key=lambda entry: _utf8(entry["path"]))
    paths = [entry["path"] for entry in ordered]
    if len(set(paths)) != len(paths):
        raise _unavailable("a path is declared more than once")
    return ordered


# --------------------------------------------------------------------------- Candidate (F2 §5, §6, §7; F3 §6.7)


def result_content(entries: Sequence[Mapping[str, Any]], message: str) -> dict[str, Any]:
    return {"artifact_kind": ARTIFACT_RESULT, "entries": sorted_entries(entries), "message": message}


def empty_content(
    entries: Sequence[Mapping[str, Any]], base_commit: str, declared_result: Sequence[str], declared_deleted: Sequence[str]
) -> dict[str, Any]:
    """The empty-artifact content: no declared path at all, or every declared entry inert (A-3)."""
    held = sorted_entries(entries)
    if any(changing(entry) for entry in held):
        raise _unavailable("an empty-artifact Candidate would hold a changing entry")
    return {
        "artifact_kind": ARTIFACT_EMPTY,
        "entries": held,
        "emptiness_proof": {
            "base_commit": base_commit,
            "declared_result_paths": sorted(set(declared_result), key=_utf8),
            "declared_deleted_paths": sorted(set(declared_deleted), key=_utf8),
            "owned_paths_differing_from_base": [],
        },
    }


def content_for(
    entries: Sequence[Mapping[str, Any]],
    *,
    message: str,
    base_commit: str,
    declared_result: Sequence[str],
    declared_deleted: Sequence[str],
) -> dict[str, Any]:
    """The discriminator of F3 §6.7: ``result_commit`` IFF at least one entry is CHANGING, else ``empty``."""
    if any(changing(entry) for entry in entries):
        return result_content(entries, message)
    return empty_content(entries, base_commit, declared_result, declared_deleted)


def candidate_record(content: dict[str, Any], declared_base: dict[str, Any], activation: dict[str, Any]) -> dict[str, Any]:
    """The canonical Work Candidate record: exactly six keys (F2 §5.1)."""
    record = serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_CANDIDATE,
        serialize.VERSION_KEY: RECORD_VERSION,
        "review_kind": REVIEW_KIND,
        "projection": {
            "projection_kind": "reviewed_artifact",
            "semantics_version": PROJECTION_SEMANTICS_VERSION,
            "content": content,
        },
        "declared_base": declared_base,
        "activation": activation,
    })
    _require_representable(record, "the Work Candidate")
    return record


def candidate_hash(candidate: dict[str, Any]) -> str:
    return serialize.digest(candidate)


def content_of(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return candidate["projection"]["content"]


def entries_of(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list(content_of(candidate)["entries"])


def artifact_kind(candidate: Mapping[str, Any]) -> str:
    return content_of(candidate)["artifact_kind"]


def _require_representable(record: dict[str, Any], described: str) -> None:
    try:
        serialize.canonical_bytes(record)
        representable = serialize.canonical_roundtrips(record)
    except (ValidationError, ValueError, UnicodeError) as exc:
        raise _unavailable(f"{described} cannot be carried by the canonical form: {exc}") from exc
    if not representable:
        raise _unavailable(f"{described} does not read back as itself in canonical form")


def is_work_candidate(material: object) -> bool:
    """Whether a snapshot's material is a Work Candidate envelope at all."""
    return (
        isinstance(material, dict)
        and material.get("material_contract") == MATERIAL_CONTRACT
        and isinstance(material.get("candidate"), dict)
        and material["candidate"].get(serialize.SCHEMA_KEY) == SCHEMA_CANDIDATE
    )


def require_candidate(candidate: object, width: int) -> dict[str, Any]:
    """``candidate`` as a Work Candidate of exactly the frozen shape, or reconcile (F2 §5 - §7, F3 §6.7)."""
    if not isinstance(candidate, dict) or candidate.get(serialize.SCHEMA_KEY) != SCHEMA_CANDIDATE:
        raise _material_mismatch("the material does not carry a Work Candidate")
    if candidate.get(serialize.VERSION_KEY) != RECORD_VERSION:
        raise _material_mismatch("the Work Candidate is not version 1")
    if set(candidate) != {serialize.SCHEMA_KEY, serialize.VERSION_KEY, "review_kind", "projection", "declared_base", "activation"}:
        raise _material_mismatch("the Work Candidate does not hold exactly its six keys")
    if candidate.get("review_kind") != REVIEW_KIND:
        raise _material_mismatch(f"the Candidate names the kind {candidate.get('review_kind')!r}")
    projection = candidate.get("projection")
    if (
        not isinstance(projection, dict)
        or set(projection) != {"projection_kind", "semantics_version", "content"}
        or projection.get("projection_kind") != "reviewed_artifact"
        or projection.get("semantics_version") != PROJECTION_SEMANTICS_VERSION
        or not isinstance(projection.get("content"), dict)
    ):
        raise _material_mismatch("the Candidate does not carry the Work reviewed-artifact projection")
    content = projection["content"]
    kind = content.get("artifact_kind")
    entries = content.get("entries")
    if not isinstance(entries, list):
        raise _material_mismatch("the Candidate's entries are not a list")
    zero = "0" * width
    for index, entry in enumerate(entries):
        _require_entry(entry, index, width, zero)
    if [entry["path"] for entry in entries] != [entry["path"] for entry in sorted(entries, key=lambda e: _utf8(e["path"]))]:
        raise _material_mismatch("the Candidate's entries are not ordered by path UTF-8 bytes")
    if len({entry["path"] for entry in entries}) != len(entries):
        raise _material_mismatch("the Candidate holds one path twice")
    moving = any(changing(entry) for entry in entries)
    base = candidate.get("declared_base") if isinstance(candidate.get("declared_base"), dict) else {}
    if kind == ARTIFACT_RESULT:
        if set(content) != {"artifact_kind", "entries", "message"} or not isinstance(content.get("message"), str):
            raise _material_mismatch("a result_commit Candidate carries exactly artifact_kind, entries and message")
        if not moving:
            raise _material_mismatch("a result_commit Candidate holds no changing entry (F3 §6.7)")
    elif kind == ARTIFACT_EMPTY:
        proof = content.get("emptiness_proof")
        if set(content) != {"artifact_kind", "entries", "emptiness_proof"} or not isinstance(proof, dict):
            raise _material_mismatch("an empty Candidate carries exactly artifact_kind, entries and emptiness_proof")
        if moving:
            raise _material_mismatch("an empty Candidate holds a changing entry (F3 §6.7)")
        if (
            set(proof) != {"base_commit", "declared_result_paths", "declared_deleted_paths", "owned_paths_differing_from_base"}
            or proof.get("base_commit") != base.get("base_commit")
            or proof.get("owned_paths_differing_from_base") != []
            or not isinstance(proof.get("declared_result_paths"), list)
            or not isinstance(proof.get("declared_deleted_paths"), list)
        ):
            raise _material_mismatch("the empty Candidate's emptiness proof is not of the frozen shape")
        declared = sorted(set(proof["declared_result_paths"]) | set(proof["declared_deleted_paths"]), key=_utf8)
        if declared != [entry["path"] for entry in entries]:
            raise _material_mismatch("the empty Candidate's entries are not exactly its declared paths")
    else:
        raise _material_mismatch(f"the Candidate names the artifact kind {kind!r}")
    return candidate


def _require_entry(entry: object, index: int, width: int, zero: str) -> None:
    if not isinstance(entry, dict) or set(entry) != set(ENTRY_FIELDS):
        raise _material_mismatch(f"entry {index} does not carry exactly the frozen entry fields")
    path = entry["path"]
    if not isinstance(path, str) or not path:
        raise _material_mismatch(f"entry {index} names no path")
    for side in ("old", "new"):
        kind, mode, oid = entry[f"{side}_kind"], entry[f"{side}_mode"], entry[f"{side}_oid"]
        if kind not in KIND_MODES or mode not in KIND_MODES[kind]:
            raise _material_mismatch(f"entry {path!r} {side} side is {kind!r} {mode!r}")
        if not isinstance(oid, str) or len(oid) != width or any(c not in "0123456789abcdef" for c in oid):
            raise _material_mismatch(f"entry {path!r} {side} side names no full object id")
        if (kind == "absent") != (oid == zero):
            raise _material_mismatch(f"entry {path!r} {side} side pairs {kind} with {oid}")
    expected = "A" if entry["old_kind"] == "absent" else "D" if entry["new_kind"] == "absent" else "M"
    if entry["status"] != expected or (entry["old_kind"] == "absent" and entry["new_kind"] == "absent"):
        raise _material_mismatch(f"entry {path!r} says status {entry['status']!r} while its sides say {expected!r}")
    digest = entry["content_sha256"]
    if entry["new_kind"] in BYTE_KINDS:
        if not isinstance(digest, str) or records.DIGEST_RE.fullmatch(digest) is None:
            raise _material_mismatch(f"entry {path!r} carries no content_sha256")
    elif digest is not None:
        raise _material_mismatch(f"entry {path!r} is {entry['new_kind']} and carries a content_sha256")


# --------------------------------------------------------------------------- snapshot material (F2 §9, A-3)


def encode_payload(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decode_payload(text: object, where: str) -> bytes:
    """Strict canonical Base64 (F2 §9.4.2): standard alphabet, padded, no whitespace, and re-encodes identically."""
    if not isinstance(text, str) or not text.isascii():
        raise _material_mismatch(f"the payload of {where} is not canonical Base64 text")
    try:
        data = base64.b64decode(text.encode("ascii"), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise _material_mismatch(f"the payload of {where} is not canonical Base64: {exc}") from exc
    if base64.b64encode(data).decode("ascii") != text:
        raise _material_mismatch(f"the payload of {where} is not the canonical Base64 of its bytes")
    return data


def snapshot_material(candidate: dict[str, Any], payload_bytes: Mapping[str, bytes]) -> dict[str, Any]:
    """The material envelope: one payload per file or symlink entry, inert ones included (F2 §9.4.1, A-3)."""
    payloads: list[dict[str, Any]] = []
    for entry in entries_of(candidate):
        if entry["new_kind"] not in BYTE_KINDS:
            continue
        data = payload_bytes.get(entry["path"])
        if data is None:
            raise _unavailable(f"the bytes of {entry['path']!r} were not bound")
        payloads.append({
            "path": entry["path"], "kind": entry["new_kind"], "encoding": PAYLOAD_ENCODING, "data": encode_payload(data),
        })
    payloads.sort(key=lambda item: _utf8(item["path"]))
    material = serialize.canonical_data({"material_contract": MATERIAL_CONTRACT, "candidate": candidate, "payloads": payloads})
    _require_representable({"material": material}, "the Candidate snapshot material")
    return material


def snapshot_for(material: dict[str, Any]) -> records.CandidateSnapshot:
    """The P1 Candidate snapshot (snapshot mode) carrying ``material``; builder null (F2 §9.1, §9.3)."""
    return records.CandidateSnapshot(
        candidate_hash=candidate_hash(material["candidate"]),
        reconstruction_mode=records.RECONSTRUCTION_SNAPSHOT,
        projection_semantics_version=PROJECTION_SEMANTICS_VERSION,
        material=material,
        builder=None,
    )


def material_digest(snapshot: records.CandidateSnapshot) -> str:
    """``candidate_material_digest``: the whole snapshot record, payload strings included (F2 §9.3)."""
    return serialize.digest(snapshot.to_record())


@dataclass(frozen=True)
class Reconstruction:
    """What a snapshot proves: the exact Candidate, and the exact bytes of every file and symlink it names."""

    candidate: dict[str, Any]
    payloads: dict[str, bytes]


def read_material(snapshot: records.CandidateSnapshot, run_candidate_hash: str, width: int) -> Reconstruction:
    """F2 §9.5 / §9.7 in full: the snapshot as reconstruction material, or reconcile - nothing is ever substituted."""
    if snapshot.reconstruction_mode != records.RECONSTRUCTION_SNAPSHOT:
        raise _material_mismatch(f"the reconstruction mode is {snapshot.reconstruction_mode!r}, not snapshot")
    if snapshot.projection_semantics_version != PROJECTION_SEMANTICS_VERSION:
        raise _material_mismatch(f"the projection semantics are {snapshot.projection_semantics_version!r}")
    if snapshot.builder is not None:
        raise _material_mismatch("a Work snapshot names a builder")
    material = snapshot.material
    if not isinstance(material, dict) or set(material) != {"material_contract", "candidate", "payloads"}:
        raise _material_mismatch("the material does not hold exactly material_contract, candidate and payloads")
    if material.get("material_contract") != MATERIAL_CONTRACT:
        raise _material_mismatch(f"the material contract is {material.get('material_contract')!r}")
    candidate = require_candidate(material.get("candidate"), width)
    if candidate_hash(candidate) != run_candidate_hash or snapshot.candidate_hash != run_candidate_hash:
        raise _material_mismatch("the material's Candidate does not digest to the Run's candidate_hash")
    payloads = material.get("payloads")
    if not isinstance(payloads, list):
        raise _material_mismatch("the payloads are not a list")
    by_entry = {entry["path"]: entry for entry in entries_of(candidate)}
    decoded: dict[str, bytes] = {}
    order: list[str] = []
    for index, payload in enumerate(payloads):
        if not isinstance(payload, dict) or set(payload) != {"path", "kind", "encoding", "data"}:
            raise _material_mismatch(f"payload {index} is not of the frozen shape")
        path = payload["path"]
        if not isinstance(path, str) or path in decoded:
            raise _material_mismatch(f"payload {index} names {path!r} twice or not at all")
        entry = by_entry.get(path)
        if entry is None:
            raise _material_mismatch(f"payload {path!r} has no Candidate entry")
        if entry["new_kind"] not in BYTE_KINDS:
            raise _material_mismatch(f"payload {path!r} is present for a {entry['new_kind']} entry")
        if payload["kind"] != entry["new_kind"]:
            raise _material_mismatch(f"payload {path!r} is {payload['kind']!r}, the entry {entry['new_kind']!r}")
        if payload["encoding"] != PAYLOAD_ENCODING:
            raise _material_mismatch(f"payload {path!r} is encoded {payload['encoding']!r}")
        data = decode_payload(payload["data"], repr(path))
        if hashlib.sha256(data).hexdigest() != entry["content_sha256"]:
            raise _material_mismatch(f"payload {path!r} does not digest to the entry's content_sha256")
        if git_blob_id(data, width) != entry["new_oid"]:
            raise _material_mismatch(f"payload {path!r} is not the Git blob the entry names")
        decoded[path] = data
        order.append(path)
    if order != sorted(order, key=_utf8):
        raise _material_mismatch("the payloads are not ordered by path UTF-8 bytes")
    missing = [path for path, entry in by_entry.items() if entry["new_kind"] in BYTE_KINDS and path not in decoded]
    if missing:
        raise _material_mismatch(f"no payload carries {sorted(missing, key=_utf8)}")
    return Reconstruction(candidate, decoded)


# --------------------------------------------------------------------------- Policy (F2 §10.4)

POLICY_RECORD: dict[str, Any] = {
    serialize.SCHEMA_KEY: SCHEMA_POLICY,
    serialize.VERSION_KEY: RECORD_VERSION,
    "policy_id": POLICY_ID,
    "slots": [{"review_kind": REVIEW_KIND, "task_slot": TASK_SLOT, "task_kind": TASK_KIND, "required": True}],
    "reviewer_identity_rule": "caller-declared identity and version, bound at acceptance; a settlement is accepted only from them",
    "report_statuses": ["completed", "declined"],
    "severities": ["HIGH", "MID", "LOW"],
    "blocking_severities": ["HIGH", "MID"],
    "low_disposition": "recorded in the report digest, returned to the caller, non-blocking",
    "declined_disposition": "the task settles failed; the Work completion is not authorized",
    "error_disposition": "no settlement; the same task is launched again by the next run",
    "timeout_disposition": "none imposed by Workline; a reviewer that gives up returns declined",
    "adjudication_rule": ADJUDICATION_RULE,
    "obligation_rule": "every HIGH or MID finding and every failed task is an unresolved obligation; P3 resolves none",
    "seal_rule": "every required task settled completed and zero unresolved obligations",
    "repair": "none; a not-authorized Work completion is not terminalized",
    "instruction": INSTRUCTION,
}


def policy_record() -> dict[str, Any]:
    return serialize.canonical_data(POLICY_RECORD)


def policy_hash() -> str:
    return serialize.digest(policy_record())


def policy_named(policy_id: object) -> dict[str, Any] | None:
    record = policy_record()
    return record if policy_id == record["policy_id"] else None


# --------------------------------------------------------------------------- request envelope, task input, descriptor (F2 §12)


def request_envelope(candidate: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """The request, carrying the Candidate and the Context WHOLE; ``work`` copies ``declared_base.work``."""
    work = candidate["declared_base"]["work"]
    envelope = serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_REQUEST,
        serialize.VERSION_KEY: RECORD_VERSION,
        "review_kind": REVIEW_KIND,
        "policy_id": POLICY_ID,
        "instruction": INSTRUCTION,
        "candidate": candidate,
        "context": context,
        "work": {
            "work_id": work["work_id"], "display": work["display"], "name": work["name"],
            "desired_state": work["desired_state"],
        },
    })
    _require_representable(envelope, "the Work review request")
    return envelope


def task_input_for(
    *,
    task_id: str,
    reviewer_identity: str,
    reviewer_version: str,
    envelope: dict[str, Any],
    snapshot: records.CandidateSnapshot,
    review_context_hash: str,
    effective_policy_hash: str,
) -> records.TaskInput:
    return records.TaskInput(
        task_id=task_id,
        task_slot=TASK_SLOT,
        task_kind=TASK_KIND,
        reviewer_identity=reviewer_identity,
        reviewer_version=reviewer_version,
        request_envelope=envelope,
        request_digest=serialize.digest(envelope),
        candidate_hash=snapshot.candidate_hash,
        reconstruction_mode=records.RECONSTRUCTION_SNAPSHOT,
        candidate_material_digest=material_digest(snapshot),
        review_context_hash=review_context_hash,
        effective_policy_hash=effective_policy_hash,
        accepted_generation=records.FIRST_GENERATION,
    )


def accepted_descriptor(task_input: records.TaskInput) -> dict[str, Any]:
    """The accepted task descriptor generation 1 carries: every P1 field, from the same sources as the task input."""
    return {
        "task_id": task_input.task_id,
        "task_slot": task_input.task_slot,
        "task_kind": task_input.task_kind,
        "reviewer_identity": task_input.reviewer_identity,
        "reviewer_version": task_input.reviewer_version,
        "candidate_hash": task_input.candidate_hash,
        "candidate_material_digest": task_input.candidate_material_digest,
        "reconstruction_mode": task_input.reconstruction_mode,
        "request_digest": task_input.request_digest,
        "task_input_digest": serialize.digest(task_input.to_record()),
        "review_context_hash": task_input.review_context_hash,
        "effective_policy_hash": task_input.effective_policy_hash,
    }


def task_from_input(task_input: records.TaskInput) -> WorkReviewTask:
    """The task the reviewer receives, rebuilt from the stored TaskInput and never from memory."""
    return WorkReviewTask(
        task_id=task_input.task_id,
        task_slot=task_input.task_slot,
        task_kind=task_input.task_kind,
        review_kind=REVIEW_KIND,
        request_envelope=serialize.canonical_data(task_input.request_envelope),
        request_digest=task_input.request_digest,
        candidate_hash=task_input.candidate_hash,
        review_context_hash=task_input.review_context_hash,
        effective_policy_hash=task_input.effective_policy_hash,
    )


def task_input_problems(
    task_input: records.TaskInput, material: Mapping[str, Any], run_candidate_hash: str, run_context_hash: str,
    run_policy_hash: str,
) -> list[str]:
    """What the P1 provenance comparison does not cover, and every Work launch and reconstruction checks."""
    problems: list[str] = []
    envelope = task_input.request_envelope
    if task_input.task_slot != TASK_SLOT or task_input.task_kind != TASK_KIND:
        problems.append("the task input is not a Work review task")
    if serialize.digest(envelope) != task_input.request_digest:
        problems.append("the task input's request_digest is not the digest of its request envelope")
    candidate = material.get("candidate") if isinstance(material, Mapping) else None
    if envelope.get("candidate") != candidate:
        problems.append("the request envelope's candidate is not the stored snapshot's Candidate")
    if not isinstance(candidate, dict) or candidate_hash(candidate) != run_candidate_hash:
        problems.append("the stored snapshot's Candidate does not digest to the Run's candidate_hash")
    context = envelope.get("context")
    if not isinstance(context, dict) or serialize.digest(context) != run_context_hash:
        problems.append("the request envelope's context does not digest to the Run's review_context_hash")
    else:
        try:
            work_context.require_context(context)
        except StopError as exc:
            problems.append(f"the request envelope's context is not a Work Context of this contract version: {exc}")
    named = policy_named(envelope.get("policy_id"))
    if named is None or serialize.digest(named) != run_policy_hash:
        problems.append("the request envelope names no policy whose digest is the Run's effective_policy_hash")
    if isinstance(candidate, dict) and isinstance(context, dict) and candidate.get("activation") != context.get("activation"):
        problems.append("the Candidate and the Context bind different activation records")
    if isinstance(candidate, dict):
        work = candidate.get("declared_base", {}).get("work", {})
        expected = {key: work.get(key) for key in ("work_id", "display", "name", "desired_state")}
        if envelope.get("work") != expected:
            problems.append("the request envelope's work block is not a copy of declared_base.work")
    return problems


# --------------------------------------------------------------------------- reports and adjudication

SEVERITIES = ("HIGH", "MID", "LOW")
BLOCKING = ("HIGH", "MID")
REPORT_STATUSES = ("completed", "declined")


def _report_invalid(message: str) -> StopError:
    return StopError(f"the reviewer's report is not valid: {message}; nothing is settled", code="review_report_invalid")


def report_record(report: object, descriptor: Mapping[str, Any]) -> dict[str, Any]:
    """The canonical report record of a reviewer's return, validated before anything is settled.

    ``review_report_invalid`` for anything that is not exactly a report for this
    task; ``review_reviewer_mismatch`` for a report from another reviewer
    identity or version than the one the task was accepted for (F2 §12.2).
    """
    if type(report) is not WorkReviewReport:
        raise _report_invalid(f"the reviewer returned {type(report).__name__}, not a WorkReviewReport")
    if report.task_id != descriptor["task_id"]:
        raise _report_invalid(f"it answers task {report.task_id!r}, not {descriptor['task_id']}")
    if report.status not in REPORT_STATUSES:
        raise _report_invalid(f"status {report.status!r} is not one of {', '.join(REPORT_STATUSES)}")
    if not isinstance(report.findings, tuple):
        raise _report_invalid("findings is not a tuple of WorkReviewFinding")
    findings: list[dict[str, Any]] = []
    for finding in report.findings:
        if type(finding) is not WorkReviewFinding:
            raise _report_invalid(f"a finding is {type(finding).__name__}, not a WorkReviewFinding")
        if finding.severity not in SEVERITIES:
            raise _report_invalid(f"a finding has severity {finding.severity!r}")
        if not _single_line_text(finding.code):
            raise _report_invalid(f"a finding has code {finding.code!r}")
        if not isinstance(finding.message, str):
            raise _report_invalid("a finding's message is not text")
        findings.append({"severity": finding.severity, "code": finding.code, "message": finding.message})
    if not isinstance(report.reviewer_identity, str) or not isinstance(report.reviewer_version, str):
        raise _report_invalid("the reviewer identity and version are not text")
    if report.reviewer_identity != descriptor["reviewer_identity"] or report.reviewer_version != descriptor["reviewer_version"]:
        raise StopError(
            f"task {descriptor['task_id']} was accepted for reviewer {descriptor['reviewer_identity']} "
            f"{descriptor['reviewer_version']}, and the report comes from {report.reviewer_identity} "
            f"{report.reviewer_version}; nothing is settled",
            code="review_reviewer_mismatch",
        )
    record = {
        serialize.SCHEMA_KEY: SCHEMA_REPORT,
        serialize.VERSION_KEY: RECORD_VERSION,
        "task_id": report.task_id,
        "reviewer_identity": report.reviewer_identity,
        "reviewer_version": report.reviewer_version,
        "status": report.status,
        "findings": findings,
    }
    try:
        serialize.canonical_bytes(record)
        representable = serialize.canonical_roundtrips(record)
    except (ValidationError, ValueError, UnicodeError) as exc:
        raise _report_invalid(f"it cannot be recorded canonically: {exc}") from exc
    if not representable:
        raise _report_invalid("it does not read back as itself in canonical form")
    return serialize.canonical_data(record)


def settled_status(record: Mapping[str, Any]) -> str:
    """How a report settles its task: ``declined`` settles ``failed``."""
    return records.TASK_SETTLED_OK if record["status"] == "completed" else records.TASK_SETTLED_FAILED


def adjudication_record(settled: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    tasks = []
    for task, report in settled:
        severities = [finding["severity"] for finding in report.get("findings") or []]
        tasks.append({
            "task_id": task["task_id"], "status": task["status"], "result_digest": task["result_digest"],
            "high": severities.count("HIGH"), "mid": severities.count("MID"), "low": severities.count("LOW"),
        })
    return {
        serialize.SCHEMA_KEY: SCHEMA_ADJUDICATION, serialize.VERSION_KEY: RECORD_VERSION,
        "rule": ADJUDICATION_RULE, "tasks": tasks,
    }


def obligations_record(settled: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    """Every HIGH or MID finding, in report order, and every failed task: P3 resolves none."""
    obligations: list[dict[str, Any]] = []
    for task, report in settled:
        for finding in report.get("findings") or []:
            if finding["severity"] in BLOCKING:
                obligations.append({
                    "task_id": task["task_id"], "kind": "finding", "severity": finding["severity"],
                    "code": finding["code"], "message": finding["message"],
                })
        if task["status"] == records.TASK_SETTLED_FAILED:
            obligations.append({
                "task_id": task["task_id"], "kind": "task_failed", "severity": "FAILED", "code": "task_failed",
                "message": "",
            })
    return {serialize.SCHEMA_KEY: SCHEMA_OBLIGATIONS, serialize.VERSION_KEY: RECORD_VERSION, "obligations": obligations}


def coverage_record(task_id: str, settled: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        serialize.SCHEMA_KEY: SCHEMA_COVERAGE, serialize.VERSION_KEY: RECORD_VERSION,
        "required": [{"task_slot": TASK_SLOT, "task_id": task_id}],
        "settled": [{"task_id": task["task_id"], "status": task["status"]} for task in settled],
    }


def report_set_record(settled: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        serialize.SCHEMA_KEY: SCHEMA_REPORT_SET, serialize.VERSION_KEY: RECORD_VERSION,
        "reports": [{"task_id": task["task_id"], "result_digest": task["result_digest"]} for task in settled],
    }


def empty_obligation_digest() -> str:
    return serialize.digest(obligations_record([]))


def authorizes(generation: records.GateGeneration) -> bool:
    """Whether a settled generation authorizes: every required task completed, and no unresolved obligation."""
    if not generation.settled_tasks or generation.unsettled_task_ids():
        return False
    if any(task["status"] != records.TASK_SETTLED_OK for task in generation.settled_tasks):
        return False
    return generation.obligation_digest == empty_obligation_digest()


# --------------------------------------------------------------------------- Evidence (F2 §13) and the validity closure (F2 §14)

#: The frozen Evidence checks of the Work kind, in their frozen order (F2 §13.2). Each is pass or not-applicable.
EVIDENCE_CHECKS = (
    "activation-valid", "candidate-projection", "object-kinds", "base-lineage", "own-bytes", "dirty-separability",
    "review-namespace", "completion-precheck",
)
CHECK_PASS = "pass"
CHECK_NOT_APPLICABLE = "not-applicable"


def check_results(declared: bool) -> list[dict[str, str]]:
    """Every frozen check's result. With no declared path, the per-path checks have nothing to apply to (F3 §6.2)."""
    per_path = ("object-kinds", "own-bytes", "dirty-separability")
    return [
        {"check": check, "result": CHECK_PASS if declared or check not in per_path else CHECK_NOT_APPLICABLE}
        for check in EVIDENCE_CHECKS
    ]


def verification_record(
    *,
    candidate_hash_value: str,
    candidate_material_digest: str,
    review_context_hash: str,
    effective_policy_hash: str,
    dependency_declaration: str,
    base_commit: str,
    resulting_tree: str,
    verified_entries: int,
) -> dict[str, Any]:
    """The isolated verification's logical result and the identities it binds (F2 §13.4 V-4, V-5)."""
    return {
        serialize.SCHEMA_KEY: SCHEMA_VERIFICATION, serialize.VERSION_KEY: RECORD_VERSION,
        "verifier_identity": VERIFIER_IDENTITY,
        "verifier_version": VERIFIER_VERSION,
        "adapter_identity": ADAPTER_IDENTITY,
        "candidate_hash": candidate_hash_value,
        "candidate_material_digest": candidate_material_digest,
        "review_context_hash": review_context_hash,
        "effective_policy_hash": effective_policy_hash,
        "dependency_declaration": dependency_declaration,
        "reconstruction": {
            "mode": records.RECONSTRUCTION_SNAPSHOT,
            "base_commit": base_commit,
            "resulting_tree": resulting_tree,
            "verified_entries": verified_entries,
        },
        "result": CHECK_PASS,
    }


def evidence_payload(checks: list[dict[str, str]], verification: dict[str, Any]) -> dict[str, Any]:
    """The versioned LOGICAL Evidence payload: the checks and the isolated verification (F2 §13.2)."""
    return {
        serialize.SCHEMA_KEY: SCHEMA_EVIDENCE_PAYLOAD, serialize.VERSION_KEY: RECORD_VERSION,
        "checks": checks, "verification": verification,
    }


def evidence_record(checks: list[dict[str, str]], verification: dict[str, Any], closure_digest: str) -> dict[str, Any]:
    """The Evidence record the gate binds: the logical payload plus the closure digest as one named entry (F2 §14.3).

    The closure's own ``evidence`` surface names the LOGICAL payload's digest,
    never this record's: this record carries the closure digest, so a closure
    naming this record's digest would have to contain a digest of itself.
    """
    return {
        serialize.SCHEMA_KEY: SCHEMA_EVIDENCE, serialize.VERSION_KEY: RECORD_VERSION,
        "checks": checks, "verification": verification, "closure_digest": closure_digest,
    }


def dependency_declaration(
    *,
    entry_identities: Sequence[str],
    base_commit: str,
    branch: str,
    object_identities: Sequence[str],
    provenance: Sequence[str],
    loader_identity: str,
    git_version: str,
) -> closure.EvidenceDeclaration:
    """F2 §13.6 exactly: what is observed, pinned, not required - and what stays unknown."""
    mechanism = (CLOSURE_MECHANISM, CLOSURE_MECHANISM_VERSION)
    observed = closure.observation(*mechanism)
    excluded = closure.exclusion(*mechanism)
    coverage = [
        closure.ClassCoverage(closure.REPOSITORY_FILES, closure.OBSERVED, observed, tuple(entry_identities),
                              "the Candidate's entries and the base tree entries, by exact path, mode and object"),
        closure.ClassCoverage(closure.GIT_STATE, closure.OBSERVED, observed,
                              (base_commit, branch, work_context.GIT_PERSISTENCE, *object_identities),
                              "base commit, branch, the object identities read, and the persistence identity"),
        closure.ClassCoverage(closure.REVIEW_PROVENANCE, closure.OBSERVED, observed, tuple(provenance),
                              "the Review provenance digests and the reviewer identity and version"),
        closure.ClassCoverage(closure.RUNTIME_TOOLCHAIN, closure.PINNED, None, (loader_identity, git_version),
                              "the loader identity and the running Git version"),
    ]
    for dependency_class in (closure.FILESYSTEM_EXTERNAL, closure.CLOCK, closure.RANDOMNESS, closure.LOCALE,
                             closure.HARDWARE, closure.CACHE_STATE):
        coverage.append(closure.ClassCoverage(dependency_class, closure.NOT_REQUIRED, excluded, (),
                                              "no Work Evidence check depends on it"))
    for dependency_class in (closure.ENVIRONMENT, closure.SUBPROCESS, closure.DYNAMIC_LIBRARIES, closure.NETWORK,
                             closure.EXTERNAL_SERVICE):
        coverage.append(closure.ClassCoverage(dependency_class, closure.UNKNOWN, None, (),
                                              "the reviewer and the isolated verifier may reach it, and nothing contains it"))
    return closure.EvidenceDeclaration(
        adapter_identity=ADAPTER_IDENTITY,
        implementation_version=VERIFIER_VERSION,
        required=(closure.REPOSITORY_FILES, closure.GIT_STATE, closure.REVIEW_PROVENANCE, closure.RUNTIME_TOOLCHAIN),
        coverage=tuple(coverage),
    )


def validity_closure(
    *,
    base_commit: str,
    branch: str,
    provenance: closure.ReviewProvenance,
    entry_identities: Sequence[str],
    activation_record_digest: str,
    evidence_payload_digest: str,
    loader_identity: str,
    git_version: str,
    declaration: closure.EvidenceDeclaration,
) -> closure.ReviewValidityClosure:
    """F2 §14.2: the live P1 closure specialized to the Work kind. Its completeness is unknown by construction."""
    proof = closure.enumeration(CLOSURE_MECHANISM, CLOSURE_MECHANISM_VERSION)
    provenance_record = provenance.to_record()
    surfaces = (
        closure.SurfaceClosure(closure.SURFACE_REVIEWED_ARTIFACT, closure.SURFACE_COVERED, tuple(entry_identities), proof),
        closure.SurfaceClosure(closure.SURFACE_REVIEW_PROVENANCE, closure.SURFACE_COVERED, tuple(
            str(provenance_record[key]) for key in (
                "candidate_hash", "candidate_material_digest", "task_input_digest", "request_digest",
                "review_context_hash", "effective_policy_hash",
            )
        ), proof),
        closure.SurfaceClosure(closure.SURFACE_REVIEW_CONTEXT, closure.SURFACE_COVERED,
                               (provenance.review_context_hash, activation_record_digest), proof),
        closure.SurfaceClosure(closure.SURFACE_EVIDENCE, closure.SURFACE_COVERED, (evidence_payload_digest,), proof),
        closure.SurfaceClosure(closure.SURFACE_POLICY, closure.SURFACE_COVERED, (provenance.effective_policy_hash,), proof),
        closure.SurfaceClosure(closure.SURFACE_GIT_SEMANTICS, closure.SURFACE_COVERED,
                               (work_context.GIT_PERSISTENCE, git_version, base_commit, branch), proof),
        closure.SurfaceClosure(closure.SURFACE_TOOL_RUNTIME, closure.SURFACE_COVERED, (loader_identity,), proof),
    )
    return closure.ReviewValidityClosure(
        version=1,
        base_commit_sha=base_commit,
        provenance=provenance,
        surfaces=surfaces,
        evidence_dependencies=(declaration,),
        git_semantics={
            "git_persistence": work_context.GIT_PERSISTENCE, "git_version": git_version,
            "base_commit": base_commit, "branch": branch,
        },
        completeness_basis="F2 §13.6: environment, subprocess, dynamic libraries, network and external services are unknown",
    )


def entry_identities(candidate: Mapping[str, Any]) -> list[str]:
    """The reviewed artifact's identities: each entry's new mode, path and object id.

    The path sits between two fixed tokens so that a path with leading or
    trailing whitespace still yields identity text the closure accepts.
    """
    return [f"{entry['new_mode']}\t{entry['path']}\t{entry['new_oid']}" for entry in entries_of(candidate)]


def base_identities(candidate: Mapping[str, Any]) -> list[str]:
    """The base tree entries the Candidate was measured against: each entry's old mode, path and object id."""
    return [f"{entry['old_mode']}\t{entry['path']}\t{entry['old_oid']}" for entry in entries_of(candidate)]
