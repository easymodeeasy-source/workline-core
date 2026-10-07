"""P7 (``WORKLINE_COMPLETION_SPRINT`` §16 / §31): Global Promotion and the Global Policy Change Review - the semantic core.

Inert, as :mod:`workline.review.policy` and :mod:`workline.review.p4` are: no
lock, no Git, no file read or write, no mutation and no lifecycle. Canonical
records are read only through reader objects the caller passes in; what this
module defines is written by the one Workline-root owner,
:mod:`workline.global_policy` (``global-policy-change``), through the
single-purpose root maintenance runtime (:mod:`workline.root_maintenance`).

```text
request       the caller's normalized Global Policy Change / evaluation request; never a Project path (§31.14)
sources       read-only H-3 source snapshots of explicitly named Projects and their B0/B1 witness (§31.15-§31.16)
independence  proven_independent | known_correlated | independence_unresolved from positive facts only (§31.17)
clusters      correlated evidence is one cluster; only mutually proven-independent clusters count (§31.18)
eligibility   the mechanical strengthen / stronger lighten floors and the exact-rollback exception (§31.19-§31.20)
compatibility the total Profile v1 adapter and its proof; the R6-2 projection decides when it applies (§31.21)
packet        the immutable Promotion Packet: evidence, never authorization (§31.23)
candidate     the clone-safe Candidate material and the root Review Context (§31.24-§31.25, §16.20)
review        the root requests over P4, the reviewer floors, the meta-verifier and the history-free G4 (§31.25-§31.28)
recovery      the root kind's classification over the one shared discovery core (§31.29, RB7C-2, R8)
records       the change record, the Patch Note, the Consumption v4 projection, the evaluation (§31.33-§31.43)
experiments   the Global-origin active experiments the next Run boundary freezes (§16.10, FC-RB7-6)
```

The root Review is the common P4 Review under a NON-history root family policy
(CP RB7-PREP item 1, RB7C-1): its requests bind no history contract, no prior
history, no set-aside summary, no decision evidence and no Project Effective
Policy; its G4 terminal states are read from the validated Gate chain, and no
P5 history record is ever built for it. A Global Policy Change is reviewed
under the PRE-CHANGE Global policy and the fixed root meta-rules, which the
Candidate and the Context bind; the proposed after-state never selects the
strength of the Review that authorizes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence

from ..errors import ReconcileRequired, StopError, ValidationError
from ..ids import is_valid_id
from . import namespace, p4, policy, records, serialize

if TYPE_CHECKING:  # imported lazily inside recovery_adapter() only (RB7-F's loader imports this module lazily)
    from . import recovery

# --------------------------------------------------------------------------- identities (§31.25, RB7_FOUNDATION_INTERFACES §1 / §5.1)

#: The root Review kind, target and contract: the frozen values ``records`` owns (PSW IR-RB7-1). Stated here so this
#: inert core reads before the shared records change lands; the WAIT_PSW_IR_RB7_1 pin proves they are exactly the
#: records' constants.
REVIEW_KIND = "global-policy-change-v1"
TARGET_IDENTITY = "global-policy"
CONTRACT = "review-v1-global-policy-change-p4-v1"
#: The non-history root family policy (``p4.ROOT_POLICY_ID``, PSW IR-RB7-2; WAIT_PSW_IR_RB7_2 pins the equality).
POLICY_ID = "review-v1-p7-root-policy-v1"
AUTHORIZED_OPERATION_STAGE = "global-policy-change:persist-global-policy"
#: The owner operations (``root_maintenance.OPERATIONS``; this core never imports the runtime).
OPERATION = "global-policy-change"
OPERATION_EVALUATION = "global-policy-evaluation"
#: The root PersistedProjectionAdapter: the committed ``global-policy.yaml`` read through the canonical loader.
PERSISTED_ADAPTER_IDENTITY = "global-policy-adapter-v1"
#: The versioned total Profile compatibility adapter (§31.21), the identity the P6 loader declares once.
ADAPTER_V1_IDENTITY = policy.COMPATIBILITY_TOTAL_ADAPTER_V1
PROJECTION_SEMANTICS_VERSION = "review-v1-p7-global-policy-projection-v1"
RECORD_VERSION = 1

DIRECTION_STRENGTHEN = policy.DIRECTION_STRENGTHEN
DIRECTION_LIGHTEN = policy.DIRECTION_LIGHTEN
DIRECTION_ADJUST = policy.DIRECTION_ADJUST
DIRECTION_ROLLBACK = policy.DIRECTION_ROLLBACK
DIRECTIONS = (DIRECTION_STRENGTHEN, DIRECTION_LIGHTEN, DIRECTION_ADJUST, DIRECTION_ROLLBACK)

RELATION_INDEPENDENT = "proven_independent"
RELATION_CORRELATED = "known_correlated"
RELATION_UNRESOLVED = "independence_unresolved"
RELATIONS = (RELATION_INDEPENDENT, RELATION_CORRELATED, RELATION_UNRESOLVED)

RESULT_RETAIN = policy.RESULT_RETAIN
RESULT_ADJUST = policy.RESULT_ADJUST
RESULT_ROLLBACK = policy.RESULT_ROLLBACK
RESULT_INCONCLUSIVE = policy.RESULT_INCONCLUSIVE
EVALUATION_RESULTS = (RESULT_RETAIN, RESULT_ADJUST, RESULT_ROLLBACK, RESULT_INCONCLUSIVE)

OUTCOME_AUTHORIZATION_READY = "authorization_ready"
OUTCOME_NOT_AUTHORIZED = "not_authorized"
OUTCOME_HUMAN_WAIT = "human_wait"

SCHEMA_CHANGE_REQUEST = "review-p7-global-change-request"
SCHEMA_EVALUATION_REQUEST = "review-p7-global-evaluation-request"
SCHEMA_SOURCE_SNAPSHOT = "review-p7-source-snapshot"
SCHEMA_PACKET = "review-p7-promotion-packet"
SCHEMA_COMPATIBILITY_PROOF = "review-p7-compatibility-proof"
SCHEMA_CANDIDATE = "review-p7-global-policy-candidate"
SCHEMA_CONTEXT = "review-p7-root-review-context"
SCHEMA_CHANGE = "review-p7-global-policy-change"
SCHEMA_EVALUATION = "review-p7-global-policy-evaluation"
#: The Evidence a root Run binds (its gate ``evidence_digest``): the Packet and its source snapshots, by digest.
SCHEMA_EVIDENCE = "review-p7-root-evidence"

#: The eligibility floors (§31.19): strengthen and ordinary adjust, and the stronger lightening floor.
FLOOR_STRENGTHEN = "strengthen"
FLOOR_LIGHTEN = "lighten"
FLOORS = (FLOOR_STRENGTHEN, FLOOR_LIGHTEN)
#: What eligibility rests on: an independent cross-Project trend, or the exact-rollback exception (§31.20).
BASIS_CROSS_PROJECT = "cross_project"
BASIS_EXACT_ROLLBACK = "exact_rollback"
#: The fixed v1 floors: source lineages and mutually proven-independent clusters each floor needs.
FLOOR_LINEAGES = {FLOOR_STRENGTHEN: 2, FLOOR_LIGHTEN: 3}
FLOOR_CLUSTERS = {FLOOR_STRENGTHEN: 2, FLOOR_LIGHTEN: 3}
#: The discovery-slot floor of the root Review (§31.26): strengthen / ordinary adjust / exact rollback, and lighten.
SLOT_FLOOR = {FLOOR_STRENGTHEN: 2, FLOOR_LIGHTEN: 3}
#: An explicit finite source list (§31.14), bounded so the cluster count is an exhaustive, deterministic search.
MAX_SOURCES = 16

# --------------------------------------------------------------------------- the P7 core catalogue (RB7_FOUNDATION_INTERFACES §5.6)

CODE_REQUEST_INVALID = "review_p7_request_invalid"
CODE_SURFACE_REFUSED = "review_p7_surface_refused"
CODE_SOURCE_UNAVAILABLE = "review_p7_source_unavailable"
CODE_SOURCE_INVALID = "review_p7_source_invalid"
CODE_NOT_ELIGIBLE = "review_p7_not_eligible"
CODE_ROLLBACK_INEXACT = "review_p7_rollback_inexact"
CODE_COMPATIBILITY_UNPROVEN = "review_p7_compatibility_unproven"
CODE_REVIEWER_FLOOR_UNMET = "review_p7_reviewer_floor_unmet"
CODE_META_VERIFIER_FAILED = "review_p7_meta_verifier_failed"
CODE_EVALUATION_INVALID = "review_p7_evaluation_invalid"
STOP_CODES = (
    CODE_REQUEST_INVALID,
    CODE_SURFACE_REFUSED,
    CODE_SOURCE_UNAVAILABLE,
    CODE_SOURCE_INVALID,
    CODE_NOT_ELIGIBLE,
    CODE_ROLLBACK_INEXACT,
    CODE_COMPATIBILITY_UNPROVEN,
    CODE_REVIEWER_FLOOR_UNMET,
    CODE_META_VERIFIER_FAILED,
    CODE_EVALUATION_INVALID,
)

REASON_CANDIDATE_MISMATCH = "review_p7_candidate_mismatch"
REASON_CHAIN_INVALID = "review_p7_chain_invalid"
RECONCILE_REASONS = (REASON_CANDIDATE_MISMATCH, REASON_CHAIN_INVALID)


def stop(code: str, message: str) -> StopError:
    """A P7 core STOP (built here so every caller raises a code of this catalogue)."""
    if code not in STOP_CODES:
        raise ValueError(f"not a P7 core STOP code: {code!r}")
    return StopError(message, code=code)


def reconcile(message: str, reason: str) -> ReconcileRequired:
    if reason not in RECONCILE_REASONS:
        raise ValueError(f"not a P7 core reconcile reason: {reason!r}")
    return ReconcileRequired(f"{message}: reconcile required", reason=reason)


def _invalid(message: str) -> ValidationError:
    """A malformed canonical record or input: the reused ``review_record_invalid``."""
    return ValidationError(message, code="review_record_invalid")


# --------------------------------------------------------------------------- small shape helpers

_SOURCE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_MECHANISM_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
#: The P5 Run disposition of a Run left at canonical HUMAN_WAIT (``history.DISPOSITION_HUMAN_WAIT``). This core never
#: imports the history module (AO-3); the test pins the equality.
_P5_HUMAN_WAIT = "human_wait"


def _is_id(value: object, kind: str) -> bool:
    """``value`` is exactly one ID of ``kind`` (the ID pattern's ``$`` would also admit a trailing newline)."""
    return isinstance(value, str) and "\n" not in value and is_valid_id(value, kind)


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and records.DIGEST_RE.fullmatch(value) is not None


def _is_commit(value: object) -> bool:
    return isinstance(value, str) and records._FULL_COMMIT.fullmatch(value) is not None


def _label_problem(value: object) -> str | None:
    return records.public_safe_problem(value, limit=records.P4_MAX_LABEL)


def _text_problem(value: object) -> str | None:
    return records.public_safe_problem(value)


def _sorted_unique(values: Sequence[Any]) -> bool:
    return list(values) == sorted(set(values))


def _canonical(value: Mapping[str, Any]) -> dict[str, Any]:
    return serialize.canonical_data(dict(value))


def _require_global(record: object, described: str) -> dict[str, Any]:
    """A strict Global policy record (the P6 loader's one definition, §31.22)."""
    return policy.parse_global_policy(record, described)


def _settings(global_policy: Mapping[str, Any]) -> dict[str, int]:
    return policy.global_policy_settings(global_policy)


def _lightens(before_setting: int, after_setting: int) -> bool:
    """Whether a setting change lightens, by the surface's fixed strength order (higher integer is stronger)."""
    return after_setting < before_setting


# =========================================================================== requests (§31.14, RB7_FOUNDATION_INTERFACES §5.2)

@dataclass(frozen=True)
class SourceProject:
    """One explicitly named source Project: a caller label (persisted) and its root (read-only; NEVER persisted)."""

    source_id: str
    root: Path


@dataclass(frozen=True)
class GlobalPolicyChangeRequest:
    """What a caller asks ``global-policy-change`` to promote: normalized data, never an imperative patch.

    ``evidence`` maps each ``source_id`` to its explicit evidence references
    (:data:`REF_RECORD` / :data:`REF_PROVENANCE`). ``rollback_of`` and
    ``rollback_evaluation_id`` name the exact-rollback exception (§31.20).
    """

    policy_surface_id: str
    direction: str
    after_setting: int
    generalized_mechanism_id: str
    summary: str
    expected_effect: str
    measurement_contract: Mapping[str, Any]
    rollback_contract: Mapping[str, Any]
    sources: tuple[SourceProject, ...]
    evidence: Mapping[str, tuple[Mapping[str, Any], ...]]
    rollback_of: str | None = None
    rollback_evaluation_id: str | None = None


@dataclass(frozen=True)
class GlobalPolicyEvaluationRequest:
    """One observation of an applied Global Policy Change (§31.41): evidence, never a policy write."""

    global_policy_change_id: str
    result: str
    rationale: str
    environment: Mapping[str, Any]
    sources: tuple[SourceProject, ...]
    evidence: Mapping[str, tuple[Mapping[str, Any], ...]]


# --------------------------------------------------------------------------- the evidence reference shape (C's, §31.15)

#: A reference to one canonical record a source Project's committed Review holds, by family, identity and digest.
REF_RECORD = "record"
#: The source's explicit structured provenance (§16.4, §31.17): exactly one per source. Every identity is an opaque
#: SHA-256 (never a path, URL or repository name); ``None`` means not declared - unknown, never "none".
REF_PROVENANCE = "provenance"
REF_KINDS = (REF_RECORD, REF_PROVENANCE)
RECORD_REF_FIELDS = ("kind", "family", "id", "digest")
PROVENANCE_FIELDS = ("kind", "lineage", "copy_sources", "incidents", "implementations", "dependencies", "mechanism",
                     "environment")
DEPENDENCY_FIELDS = ("identity", "common_cause")
CAUSE_CAUSAL = "causal"
CAUSE_RULED_OUT = "ruled_out"
CAUSE_UNKNOWN = "unknown"
COMMON_CAUSES = (CAUSE_CAUSAL, CAUSE_RULED_OUT, CAUSE_UNKNOWN)
ENVIRONMENT_FIELDS = ("reviewers", "check_adapters", "toolchain", "dependencies")

#: The P6 Project-local change records a source may cite (Project-local policy outcomes, §16.9).
FAMILY_POLICY_CHANGES = "policy-changes"
FAMILY_POLICY_EVALUATIONS = policy.POLICY_EVIDENCE_EVALUATIONS
#: The record families a source reference may name: the P5 history families and the P6 change / evaluation records.
RECORD_FAMILIES = tuple(policy.EVIDENCE_FAMILIES) + (FAMILY_POLICY_CHANGES,)
_HISTORY_FAMILIES = tuple(namespace.HISTORY_FAMILIES)


def _record_kind(family: str) -> str:
    if family == FAMILY_POLICY_CHANGES:
        return "review_policy_change"
    if family == FAMILY_POLICY_EVALUATIONS:
        return "review_policy_evaluation"
    return namespace.HISTORY_FAMILY_KINDS[family]


def _digest_list_problem(value: object, described: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or any(not _is_digest(item) for item in value):
        return f"{described} is not a list of opaque SHA-256 identities"
    if len(set(value)) != len(value):
        return f"{described} names one identity twice"
    return None


def _environment_problem(value: object, described: str) -> str | None:
    if not isinstance(value, Mapping) or set(value) != set(ENVIRONMENT_FIELDS):
        return f"{described} is not exactly {{{', '.join(ENVIRONMENT_FIELDS)}}}"
    for name in ("reviewers", "check_adapters", "dependencies"):
        items = value[name]
        if not isinstance(items, (list, tuple)) or len(set(items)) != len(items):
            return f"{described} {name} is not a duplicate-free list"
        for item in items:
            problem = _label_problem(item)
            if problem is not None:
                return f"{described} {name}: {problem}"
    problem = _label_problem(value["toolchain"])
    if problem is not None:
        return f"{described} toolchain: {problem}"
    return None


def _normal_environment(value: Mapping[str, Any]) -> dict[str, Any]:
    return {"reviewers": sorted(value["reviewers"]), "check_adapters": sorted(value["check_adapters"]),
            "toolchain": value["toolchain"], "dependencies": sorted(value["dependencies"])}


def _ref_problem(ref: object, described: str) -> str | None:
    """Why ``ref`` is not one evidence reference of C's shape, or ``None``."""
    if not isinstance(ref, Mapping) or ref.get("kind") not in REF_KINDS:
        return f"{described} is not a {' / '.join(REF_KINDS)} reference"
    if ref["kind"] == REF_RECORD:
        if set(ref) != set(RECORD_REF_FIELDS):
            return f"{described} is not exactly {{{', '.join(RECORD_REF_FIELDS)}}}"
        if ref["family"] not in RECORD_FAMILIES:
            return f"{described} family {ref['family']!r} is not one of {', '.join(RECORD_FAMILIES)}"
        if not _is_id(ref["id"], _record_kind(ref["family"])):
            return f"{described} id is not a {_record_kind(ref['family'])} id"
        if not _is_digest(ref["digest"]):
            return f"{described} digest is not a SHA-256"
        return None
    if set(ref) != set(PROVENANCE_FIELDS):
        return f"{described} is not exactly {{{', '.join(PROVENANCE_FIELDS)}}}"
    if ref["lineage"] is not None and not _is_digest(ref["lineage"]):
        return f"{described} lineage is not an opaque SHA-256 lineage fingerprint"
    for name in ("copy_sources", "incidents", "implementations"):
        problem = _digest_list_problem(ref[name], f"{described} {name}")
        if problem is not None:
            return problem
    dependencies = ref["dependencies"]
    if dependencies is not None:
        if not isinstance(dependencies, (list, tuple)):
            return f"{described} dependencies is not a list"
        identities = []
        for item in dependencies:
            if not isinstance(item, Mapping) or set(item) != set(DEPENDENCY_FIELDS) or not _is_digest(item["identity"]) \
                    or item["common_cause"] not in COMMON_CAUSES:
                return (f"{described} dependency is not exactly {{identity: SHA-256, common_cause: "
                        f"{' | '.join(COMMON_CAUSES)}}}")
            identities.append(item["identity"])
        if len(set(identities)) != len(identities):
            return f"{described} names one dependency twice"
    mechanism = ref["mechanism"]
    if mechanism is not None and (not isinstance(mechanism, str) or _MECHANISM_ID.match(mechanism) is None):
        return f"{described} mechanism is not a generalized mechanism identity"
    if ref["environment"] is not None:
        problem = _environment_problem(ref["environment"], f"{described} environment")
        if problem is not None:
            return problem
    return None


def _normal_ref(ref: Mapping[str, Any]) -> dict[str, Any]:
    """One reference in canonical form: identity lists sorted (a list says the same whatever order it was built in)."""
    if ref["kind"] == REF_RECORD:
        return {"kind": REF_RECORD, "family": ref["family"], "id": ref["id"], "digest": ref["digest"]}
    return {
        "kind": REF_PROVENANCE,
        "lineage": ref["lineage"],
        **{name: None if ref[name] is None else sorted(ref[name])
           for name in ("copy_sources", "incidents", "implementations")},
        "dependencies": None if ref["dependencies"] is None else sorted(
            ({"identity": item["identity"], "common_cause": item["common_cause"]} for item in ref["dependencies"]),
            key=lambda item: item["identity"]),
        "mechanism": ref["mechanism"],
        "environment": None if ref["environment"] is None else _normal_environment(ref["environment"]),
    }


def _ref_order(ref: Mapping[str, Any]) -> tuple[Any, ...]:
    return (0,) if ref["kind"] == REF_PROVENANCE else (1, ref["family"], ref["id"])


def _evidence_problems(refs: object, described: str) -> list[str]:
    """Every way ``refs`` is not one source's evidence: exactly one provenance, distinct record references."""
    if not isinstance(refs, (list, tuple)):
        return [f"{described} is not a sequence of evidence references"]
    found: list[str] = []
    for index, ref in enumerate(refs):
        problem = _ref_problem(ref, f"{described} reference {index}")
        if problem is not None:
            found.append(problem)
    if found:
        return found
    provenance = [ref for ref in refs if ref["kind"] == REF_PROVENANCE]
    if len(provenance) != 1:
        found.append(f"{described} declares its provenance {len(provenance)} times; exactly once")
    keys = [(ref["family"], ref["id"]) for ref in refs if ref["kind"] == REF_RECORD]
    if len(set(keys)) != len(keys):
        found.append(f"{described} names one record twice; a duplicate is never a second observation")
    return found


def _normal_evidence(refs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted((_normal_ref(ref) for ref in refs), key=_ref_order)


def _provenance_of(evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return next(dict(ref) for ref in evidence if ref["kind"] == REF_PROVENANCE)


def _record_refs_of(evidence: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{"family": ref["family"], "id": ref["id"], "digest": ref["digest"]}
            for ref in evidence if ref["kind"] == REF_RECORD]


def _sources_and_evidence(sources: object, evidence: object, code: str) -> tuple[list[str], dict[str, Any]]:
    """The source ids (sorted) and their normalized evidence, from the caller's dataclass input; never a path."""
    if not isinstance(sources, tuple) or any(type(item) is not SourceProject for item in sources):
        raise stop(code, "sources is a tuple of SourceProject")
    ids = [item.source_id for item in sources]
    for item in sources:
        if not isinstance(item.source_id, str) or _SOURCE_ID.match(item.source_id) is None:
            raise stop(code, f"source id {item.source_id!r} is not a lowercase machine label")
        if not isinstance(item.root, Path):
            raise stop(code, f"source {item.source_id} names no root path (read-only, never persisted)")
    if len(set(ids)) != len(ids):
        raise stop(code, "two sources share one source id")
    if len(ids) > MAX_SOURCES:
        raise stop(code, f"{len(ids)} sources; an explicit finite source list holds at most {MAX_SOURCES}")
    if not isinstance(evidence, Mapping) or set(evidence) != set(ids):
        raise stop(code, "evidence names exactly the sources, by source id")
    normal: dict[str, Any] = {}
    for source_id in sorted(ids):
        problems = _evidence_problems(evidence[source_id], f"the evidence of source {source_id}")
        if problems:
            raise stop(code, "; ".join(problems))
        normal[source_id] = _normal_evidence(evidence[source_id])
    return sorted(ids), normal


# --------------------------------------------------------------------------- the change request record

MEASUREMENT_FIELDS = ("version", "metric", "success_criteria", "minimum_opportunities", "minimum_clusters",
                      "continued_observation_permitted")
ROLLBACK_REQUEST_FIELDS = ("threshold",)
REQUEST_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "policy_surface_id", "direction", "after_setting",
    "generalized_mechanism_id", "summary", "expected_effect", "measurement_contract", "rollback_contract", "sources",
    "evidence", "rollback_of", "rollback_evaluation_id",
)


def _measurement_problem(value: object, described: str) -> str | None:
    if not isinstance(value, Mapping) or set(value) != set(MEASUREMENT_FIELDS):
        return f"{described} is not exactly {{{', '.join(MEASUREMENT_FIELDS)}}}"
    for name, check in (("version", _label_problem), ("metric", _text_problem), ("success_criteria", _text_problem)):
        problem = check(value[name])
        if problem is not None:
            return f"{described} {name}: {problem}"
    for name in ("minimum_opportunities", "minimum_clusters"):
        if type(value[name]) is not int or value[name] < 1:
            return f"{described} {name} is not a positive integer"
    if type(value["continued_observation_permitted"]) is not bool:
        return f"{described} continued_observation_permitted is not a boolean"
    return None


def _evidence_map_problems(record: Mapping[str, Any], described: str) -> list[str]:
    sources = record["sources"]
    if not isinstance(sources, list) or any(not isinstance(item, str) or _SOURCE_ID.match(item) is None
                                            for item in sources) or not _sorted_unique(sources):
        return [f"{described} sources is not a sorted duplicate-free list of source labels"]
    if len(sources) > MAX_SOURCES:
        return [f"{described} names more than {MAX_SOURCES} sources"]
    evidence = record["evidence"]
    if not isinstance(evidence, Mapping) or sorted(evidence) != sources:
        return [f"{described} evidence is not keyed by exactly its sources"]
    found: list[str] = []
    for source_id in sources:
        problems = _evidence_problems(evidence[source_id], f"{described} evidence of {source_id}")
        if problems:
            found.extend(problems)
        elif list(evidence[source_id]) != _normal_evidence(evidence[source_id]):
            found.append(f"{described} evidence of {source_id} is not in canonical order")
    return found


def request_problems(record: object) -> list[tuple[str, str]]:
    """Every coded reason ``record`` is not a canonical Global Policy Change request - coded, never a crash."""
    try:
        return _request_problems(record)
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        return [(CODE_REQUEST_INVALID, f"the request is malformed ({type(exc).__name__}: {exc})")]


def _request_problems(record: object) -> list[tuple[str, str]]:
    if not isinstance(record, Mapping) or set(record) != set(REQUEST_FIELDS) \
            or record.get(serialize.SCHEMA_KEY) != SCHEMA_CHANGE_REQUEST \
            or record.get(serialize.VERSION_KEY) != RECORD_VERSION:
        return [(CODE_REQUEST_INVALID, "the request does not hold exactly the Global Policy Change request fields")]
    surface = policy.surface_problem(record["policy_surface_id"])
    if surface is not None:
        return [(CODE_SURFACE_REFUSED, f"{surface[1]}; a proposal needing a new surface or meta-rule is Workline-root "
                                       "implementation work, never adaptive promotion")]
    found: list[tuple[str, str]] = []
    if record["direction"] not in DIRECTIONS:
        found.append((CODE_REQUEST_INVALID, f"direction {record['direction']!r} is not one of {', '.join(DIRECTIONS)}"))
    if not policy.SURFACE_BY_ID[record["policy_surface_id"]].in_range(record["after_setting"]):
        found.append((CODE_REQUEST_INVALID, f"after_setting {record['after_setting']!r} is outside the fixed range"))
    mechanism = record["generalized_mechanism_id"]
    if not isinstance(mechanism, str) or _MECHANISM_ID.match(mechanism) is None:
        found.append((CODE_REQUEST_INVALID, f"generalized_mechanism_id {mechanism!r} is not a lowercase mechanism "
                                            "identity"))
    for name in ("summary", "expected_effect"):
        problem = _text_problem(record[name])
        if problem is not None:
            found.append((CODE_REQUEST_INVALID, f"{name} is not H-3 public-safe text: {problem}"))
    problem = _measurement_problem(record["measurement_contract"], "measurement_contract")
    if problem is not None:
        found.append((CODE_REQUEST_INVALID, problem))
    rollback = record["rollback_contract"]
    if not isinstance(rollback, Mapping) or set(rollback) != set(ROLLBACK_REQUEST_FIELDS) \
            or _text_problem(rollback["threshold"]) is not None:
        found.append((CODE_REQUEST_INVALID, "rollback_contract is not exactly {threshold: public-safe text}"))
    for message in _evidence_map_problems(record, "the request"):
        found.append((CODE_REQUEST_INVALID, message))
    rollback_of, evaluation_id = record["rollback_of"], record["rollback_evaluation_id"]
    if (rollback_of is None) != (evaluation_id is None):
        found.append((CODE_REQUEST_INVALID, "the exact-rollback exception names its change and the evaluation proving "
                                            "the threshold fired, together"))
    if rollback_of is not None:
        if record["direction"] != DIRECTION_ROLLBACK:
            found.append((CODE_REQUEST_INVALID, "only a rollback names the change it exactly rolls back"))
        if not _is_id(rollback_of, "review_global_policy_change"):
            found.append((CODE_REQUEST_INVALID, "rollback_of is not a review_global_policy_change id"))
        if not _is_id(evaluation_id, "review_global_policy_evaluation"):
            found.append((CODE_REQUEST_INVALID, "rollback_evaluation_id is not a review_global_policy_evaluation id"))
    elif isinstance(record["sources"], list) and not record["sources"]:
        found.append((CODE_REQUEST_INVALID, "a promotion names its explicit sources; only the exact-rollback exception "
                                            "needs no fresh cross-Project trend"))
    return found


def _require_request(record: object) -> dict[str, Any]:
    problems = request_problems(record)
    if problems:
        code, message = problems[0]
        raise stop(code, f"invalid Global Policy Change request: {message}")
    return _canonical(record)  # type: ignore[arg-type]


def request_record(request: GlobalPolicyChangeRequest) -> dict[str, Any]:
    """The canonical, path-free record of a change request; ``review_p7_request_invalid`` when it is not one."""
    if type(request) is not GlobalPolicyChangeRequest:
        raise stop(CODE_REQUEST_INVALID, f"a Global Policy Change request is a GlobalPolicyChangeRequest, not "
                                         f"{type(request).__name__}")
    ids, evidence = _sources_and_evidence(request.sources, request.evidence, CODE_REQUEST_INVALID)
    for name in ("measurement_contract", "rollback_contract"):
        if not isinstance(getattr(request, name), Mapping):
            raise stop(CODE_REQUEST_INVALID, f"{name} is a mapping")
    record = {
        serialize.SCHEMA_KEY: SCHEMA_CHANGE_REQUEST, serialize.VERSION_KEY: RECORD_VERSION,
        "policy_surface_id": request.policy_surface_id, "direction": request.direction,
        "after_setting": request.after_setting, "generalized_mechanism_id": request.generalized_mechanism_id,
        "summary": request.summary, "expected_effect": request.expected_effect,
        "measurement_contract": dict(request.measurement_contract), "rollback_contract": dict(request.rollback_contract),
        "sources": ids, "evidence": evidence,
        "rollback_of": request.rollback_of, "rollback_evaluation_id": request.rollback_evaluation_id,
    }
    return _require_request(record)


def request_digest(record: Mapping[str, Any]) -> str:
    return serialize.digest(dict(record))


def operation_identity(request_digest: str) -> str:
    """``global-policy-change:<request digest>``: the stable operation identity the root Runs and Consumption bind."""
    if not _is_digest(request_digest):
        raise stop(CODE_REQUEST_INVALID, "an operation identity is built from an exact request digest")
    return f"{OPERATION}:{request_digest}"


# --------------------------------------------------------------------------- the evaluation request record

EVALUATION_ENVIRONMENT_FIELDS = ("window_start", "window_end", "basis", "basis_digest")
EVALUATION_REQUEST_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "global_policy_change_id", "result", "rationale", "environment",
    "sources", "evidence",
)


def _evaluation_environment_problem(value: object) -> str | None:
    if not isinstance(value, Mapping) or set(value) != set(EVALUATION_ENVIRONMENT_FIELDS):
        return f"environment is not exactly {{{', '.join(EVALUATION_ENVIRONMENT_FIELDS)}}}"
    for name in ("window_start", "window_end"):
        problem = _environment_problem(value[name], f"environment {name}")
        if problem is not None:
            return problem
    if value["basis"] not in (None,) + policy.ENVIRONMENT_BASES:
        return f"environment basis is not one of {', '.join(policy.ENVIRONMENT_BASES)}"
    if (value["basis"] is None) != (value["basis_digest"] is None):
        return "an environment basis carries its evidence digest, and only a basis does"
    if value["basis_digest"] is not None and not _is_digest(value["basis_digest"]):
        return "environment basis_digest is not a SHA-256"
    return None


def evaluation_request_problems(record: object) -> list[str]:
    """Every reason ``record`` is not a canonical Global Policy evaluation request - never a crash."""
    try:
        return _evaluation_request_problems(record)
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        return [f"the evaluation request is malformed ({type(exc).__name__}: {exc})"]


def _evaluation_request_problems(record: object) -> list[str]:
    if not isinstance(record, Mapping) or set(record) != set(EVALUATION_REQUEST_FIELDS) \
            or record.get(serialize.SCHEMA_KEY) != SCHEMA_EVALUATION_REQUEST \
            or record.get(serialize.VERSION_KEY) != RECORD_VERSION:
        return ["the request does not hold exactly the Global Policy evaluation request fields"]
    found: list[str] = []
    if not _is_id(record["global_policy_change_id"], "review_global_policy_change"):
        found.append("global_policy_change_id is not a review_global_policy_change id")
    if record["result"] not in EVALUATION_RESULTS:
        found.append(f"result {record['result']!r} is not one of {', '.join(EVALUATION_RESULTS)}")
    problem = _text_problem(record["rationale"])
    if problem is not None:
        found.append(f"rationale is not H-3 public-safe text: {problem}")
    problem = _evaluation_environment_problem(record["environment"])
    if problem is not None:
        found.append(problem)
    evidence_problems = _evidence_map_problems(record, "the evaluation request")
    found.extend(evidence_problems)
    if problem is None and not evidence_problems and record["environment"]["basis_digest"] is not None:
        digests = {ref["digest"] for refs in record["evidence"].values() for ref in refs if ref["kind"] == REF_RECORD}
        if record["environment"]["basis_digest"] not in digests:
            found.append("the environment basis (window split / positive irrelevance proof) is one of the evaluation's "
                         "evidence records, named by its digest; an arbitrary digest proves nothing")
    return found


def evaluation_request_record(request: GlobalPolicyEvaluationRequest) -> dict[str, Any]:
    """The canonical, path-free record of an evaluation request; ``review_p7_evaluation_invalid`` otherwise."""
    if type(request) is not GlobalPolicyEvaluationRequest:
        raise stop(CODE_EVALUATION_INVALID, f"an evaluation request is a GlobalPolicyEvaluationRequest, not "
                                            f"{type(request).__name__}")
    ids, evidence = _sources_and_evidence(request.sources, request.evidence, CODE_EVALUATION_INVALID)
    environment = request.environment
    if not isinstance(environment, Mapping):
        raise stop(CODE_EVALUATION_INVALID, "environment is a mapping")
    problem = _evaluation_environment_problem(environment)
    if problem is not None:
        raise stop(CODE_EVALUATION_INVALID, f"invalid Global Policy evaluation request: {problem}")
    record = {
        serialize.SCHEMA_KEY: SCHEMA_EVALUATION_REQUEST, serialize.VERSION_KEY: RECORD_VERSION,
        "global_policy_change_id": request.global_policy_change_id, "result": request.result,
        "rationale": request.rationale,
        "environment": {"window_start": _normal_environment(environment["window_start"]),
                        "window_end": _normal_environment(environment["window_end"]),
                        "basis": environment["basis"], "basis_digest": environment["basis_digest"]},
        "sources": ids, "evidence": evidence,
    }
    problems = evaluation_request_problems(record)
    if problems:
        raise stop(CODE_EVALUATION_INVALID, "invalid Global Policy evaluation request: " + "; ".join(problems))
    return _canonical(record)


def evaluation_operation_identity(request_digest: str) -> str:
    """``global-policy-evaluation:<request digest>``."""
    if not _is_digest(request_digest):
        raise stop(CODE_EVALUATION_INVALID, "an operation identity is built from an exact request digest")
    return f"{OPERATION_EVALUATION}:{request_digest}"


# =========================================================================== source snapshots (§31.15-§31.16)

SNAPSHOT_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "source_id", "head", "provenance", "records", "opportunities",
    "escapes", "local_outcomes", "semantic_surfaces", "unresolved_human", "profile",
)
#: One Relevant Opportunity: its Run, the Global policy version and the EFFECTIVE setting of the surface the Run froze
#: (``None`` both when the Run froze no Effective Policy), and the Global-origin experiments it froze.
OPPORTUNITY_FIELDS = ("review_run_id", "global_policy_version", "setting", "global_changes")
#: An escape / recurrence fact among a source's records: a supported relation, or a serious supported Problem.
ESCAPE_SERIOUS_PROBLEM = "serious_problem"
ESCAPE_FIELDS = ("family", "id", "digest", "kind")
#: A Project-local P6 outcome a source cites: its change records and its evaluation records.
OUTCOME_FIELDS = {
    FAMILY_POLICY_CHANGES: ("family", "id", "digest", "policy_surface_id", "direction", "before_setting",
                            "after_setting"),
    FAMILY_POLICY_EVALUATIONS: ("family", "id", "digest", "policy_change_id", "result", "next_action"),
}
WITNESS_FIELDS = ("source_id", "head", "records", "profile")


def _stored_digest(reader: Any, ref: Mapping[str, Any]) -> str:
    family, identifier = str(ref["family"]), str(ref["id"])
    if family == FAMILY_POLICY_CHANGES:
        return str(reader.policy_change_digest(identifier))
    if family == FAMILY_POLICY_EVALUATIONS:
        return str(reader.policy_evaluation_digest(identifier))
    return str(reader.history_digest(family, identifier))


def _opportunity_entry(reader: Any, review_run_id: str, surface_id: str) -> dict[str, Any]:
    """One Relevant Opportunity of ``surface_id``, with what its Run froze - positive proof of what it ran under.

    The Global policy version, the surface's EFFECTIVE setting (the Profile
    overlay on the Global: the behaviour that Run actually exercised) and the
    Global-origin experiments. A Run that froze no Effective Policy (a P4 / P5
    Run) has neither version nor setting: unknown, never assumed.
    """
    frozen = policy.frozen_effective_policy(reader, review_run_id)
    if frozen is None:
        return {"review_run_id": review_run_id, "global_policy_version": None, "setting": None, "global_changes": []}
    return {
        "review_run_id": review_run_id,
        "global_policy_version": int(frozen["global_baseline"]["baseline_version"]),
        "setting": int(frozen["settings"][surface_id]),
        "global_changes": sorted({str(item["policy_change_id"]) for item in frozen["active_experiments"]
                                  if item["origin"] == policy.ORIGIN_GLOBAL}),
    }


def source_snapshot(source_id: str, reader: Any, head: str, evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The read-only H-3 source snapshot of one explicitly named Project (§31.15).

    ``reader`` is the committed Review reader of the source at ``head``
    (``CommittedReviewStore(source_root, head)``, built by the owner). Only the
    records ``evidence`` names are read - nothing is listed, crawled or
    written - and each must be stored with exactly the digest named:
    ``review_p7_source_invalid`` otherwise. The snapshot binds facts and
    digests only: the source label, its HEAD, the declared provenance, the
    record references, the Relevant Opportunities of every fixed surface with
    the Global policy each Run froze, the supported escape / recurrence facts,
    the Project-local P6 outcomes, the semantic surfaces, any unresolved HUMAN
    boundary, and the Profile state witness. No path, transcript or locator.
    """
    if not isinstance(source_id, str) or _SOURCE_ID.match(source_id) is None:
        raise stop(CODE_SOURCE_INVALID, f"source id {source_id!r} is not a lowercase machine label")
    if not _is_commit(head):
        raise stop(CODE_SOURCE_INVALID, f"source {source_id} HEAD {head!r} is not a full commit id")
    problems = _evidence_problems(evidence, f"the evidence of source {source_id}")
    if problems:
        raise stop(CODE_SOURCE_INVALID, "; ".join(problems))
    normal = _normal_evidence(evidence)
    refs = _record_refs_of(normal)
    found_records: list[dict[str, Any]] = []
    escapes: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    surfaces: set[str] = set()
    human_wait: set[str] = set()
    decided: set[str] = set()
    opportunities: dict[str, set[str]] = {surface.policy_surface_id: set() for surface in policy.SURFACES}
    for ref in refs:
        described = f"source {source_id} record {ref['family']}/{ref['id']}"
        try:
            stored = _stored_digest(reader, ref)
        except ValidationError as exc:
            raise stop(CODE_SOURCE_INVALID, f"{described} is not stored at {head} or does not read ({exc})") from exc
        if stored != ref["digest"]:
            raise stop(CODE_SOURCE_INVALID, f"{described} digests to {stored}, not the {ref['digest']} the request names")
        found_records.append(dict(ref))
        family = ref["family"]
        try:
            if family == FAMILY_POLICY_CHANGES:
                change = reader.read_policy_change(ref["id"])
                outcomes.append({**ref, "policy_surface_id": str(change["affected_policy_surface"]),
                                 "direction": str(change["direction"]), "before_setting": int(change["before_setting"]),
                                 "after_setting": int(change["after_setting"])})
                continue
            if family == FAMILY_POLICY_EVALUATIONS:
                evaluation = reader.read_policy_evaluation(ref["id"])
                outcomes.append({**ref, "policy_change_id": str(evaluation["policy_change_id"]),
                                 "result": str(evaluation["result"]), "next_action": str(evaluation["next_action"])})
                continue
            found = reader.read_history(family, ref["id"])
        except (ValidationError, KeyError, TypeError) as exc:
            raise stop(CODE_SOURCE_INVALID, f"{described} does not read ({exc})") from exc
        if family == namespace.HISTORY_RUNS and getattr(found, "durable_disposition", None) == _P5_HUMAN_WAIT:
            human_wait.add(str(ref["id"]))
        if family == namespace.HISTORY_HUMAN_DECISIONS:
            decided.add(str(getattr(found, "affected_review_run_id", "")))
        surface_label = getattr(found, "semantic_surface", None)
        if isinstance(surface_label, str):
            surfaces.add(surface_label)
        surfaces.update(str(item) for item in (getattr(found, "semantic_surfaces", None) or ()))
        if family == namespace.HISTORY_RELATIONS and bool(getattr(found, "confirmed", False)):
            escapes.append({**ref, "kind": str(found.relation_type)})
        elif family == namespace.HISTORY_FINDINGS and policy.serious_escape(reader, ref):
            escapes.append({**ref, "kind": ESCAPE_SERIOUS_PROBLEM})
        for surface in policy.SURFACES:
            try:
                identity = policy.opportunity(reader, ref, surface.policy_surface_id)
            except (ValidationError, KeyError, TypeError, AttributeError):
                identity = None
            if identity is not None:
                opportunities[surface.policy_surface_id].add(str(identity))
    try:
        profile = reader.read_profile()
    except ValidationError as exc:
        raise stop(CODE_SOURCE_INVALID, f"the Project Profile of source {source_id} does not read ({exc})") from exc
    snapshot: dict[str, Any] = {
        serialize.SCHEMA_KEY: SCHEMA_SOURCE_SNAPSHOT, serialize.VERSION_KEY: RECORD_VERSION,
        "source_id": source_id, "head": head,
        "provenance": {key: value for key, value in _provenance_of(normal).items() if key != "kind"},
        "records": found_records,
        "opportunities": {surface_id: [_opportunity_entry(reader, run_id, surface_id) for run_id in sorted(run_ids)]
                          for surface_id, run_ids in sorted(opportunities.items())},
        "escapes": escapes,
        "local_outcomes": outcomes,
        "semantic_surfaces": sorted(surfaces),
        "unresolved_human": sorted(human_wait - decided),
        "profile": None if profile is None else {"profile_version": int(profile.profile_version),
                                                 "digest": str(profile.digest)},
    }
    try:
        return parse_source_snapshot(snapshot, f"the source snapshot of {source_id}")
    except ValidationError as exc:
        raise stop(CODE_SOURCE_INVALID, f"the evidence of source {source_id} does not form a public-safe snapshot "
                                        f"({exc})") from exc


def parse_source_snapshot(record: object, described: str) -> dict[str, Any]:
    """A source snapshot, strictly (its fields, the reference shapes, sorted facts); ``review_record_invalid``."""
    found = records._require_mapping(record, described)
    serialize.require_schema(found, SCHEMA_SOURCE_SNAPSHOT, RECORD_VERSION, described)
    records._require_exact_fields(found, SNAPSHOT_FIELDS, described)
    if not isinstance(found["source_id"], str) or _SOURCE_ID.match(found["source_id"]) is None:
        raise _invalid(f"{described} source_id is not a source label")
    if not _is_commit(found["head"]):
        raise _invalid(f"{described} head is not a full commit id")
    provenance = found["provenance"]
    if not isinstance(provenance, Mapping) or "kind" in provenance:
        raise _invalid(f"{described} provenance is not a provenance mapping")
    problem = _ref_problem({"kind": REF_PROVENANCE, **provenance}, f"{described} provenance")
    if problem is not None:
        raise _invalid(problem)
    if _normal_ref({"kind": REF_PROVENANCE, **provenance}) != {"kind": REF_PROVENANCE, **provenance}:
        raise _invalid(f"{described} provenance is not in canonical order")
    refs = records._require_list(found, "records", described)
    for item in refs:
        if not isinstance(item, Mapping) or "kind" in item \
                or _ref_problem({"kind": REF_RECORD, **item}, described) is not None:
            raise _invalid(f"{described} names a malformed record reference")
    keys = [(item["family"], item["id"]) for item in refs]
    if keys != sorted(set(keys)):
        raise _invalid(f"{described} records are not sorted and duplicate-free")
    named = {(item["family"], item["id"], item["digest"]) for item in refs}
    opportunities = records._require_mapping(found["opportunities"], f"{described} opportunities")
    if sorted(opportunities) != sorted(policy.SURFACE_BY_ID):
        raise _invalid(f"{described} opportunities are not keyed by exactly the fixed surfaces")
    for surface_id, entries in opportunities.items():
        if not isinstance(entries, list):
            raise _invalid(f"{described} opportunities of {surface_id} is not a list")
        surface = policy.SURFACE_BY_ID[surface_id]
        for entry in entries:
            if not isinstance(entry, Mapping) or set(entry) != set(OPPORTUNITY_FIELDS) \
                    or not _is_id(entry["review_run_id"], "review_run") \
                    or (entry["global_policy_version"] is None) != (entry["setting"] is None) \
                    or (entry["global_policy_version"] is not None
                        and (type(entry["global_policy_version"]) is not int or entry["global_policy_version"] < 1
                             or not surface.in_range(entry["setting"]))) \
                    or not isinstance(entry["global_changes"], list) \
                    or any(not _is_id(item, "review_global_policy_change") for item in entry["global_changes"]) \
                    or not _sorted_unique(entry["global_changes"]):
                raise _invalid(f"{described} names a malformed opportunity of {surface_id}")
        runs = [entry["review_run_id"] for entry in entries]
        if runs != sorted(set(runs)):
            raise _invalid(f"{described} opportunities of {surface_id} are not sorted and duplicate-free")
    for name in ("escapes", "local_outcomes"):
        for item in records._require_list(found, name, described):
            if not isinstance(item, Mapping) or (item.get("family"), item.get("id"), item.get("digest")) not in named:
                raise _invalid(f"{described} {name} names a record the snapshot does not")
            if name == "escapes":
                if set(item) != set(ESCAPE_FIELDS) or _label_problem(item["kind"]) is not None:
                    raise _invalid(f"{described} names a malformed escape fact")
            elif set(item) != set(OUTCOME_FIELDS[item["family"]] if item["family"] in OUTCOME_FIELDS else ()):
                raise _invalid(f"{described} names a malformed Project-local outcome")
        keys = [(item["family"], item["id"]) for item in found[name]]
        if keys != sorted(set(keys)):
            raise _invalid(f"{described} {name} are not sorted and duplicate-free")
    for name in ("semantic_surfaces", "unresolved_human"):
        values = records._require_list(found, name, described)
        if not _sorted_unique(values) or any(_label_problem(value) is not None for value in values):
            raise _invalid(f"{described} {name} is not a sorted duplicate-free list of labels")
    if any(not _is_id(value, "review_run") for value in found["unresolved_human"]):
        raise _invalid(f"{described} unresolved_human names a non-Run identity")
    profile = found["profile"]
    if profile is not None:
        profile = records._require_mapping(profile, f"{described} profile")
        records._require_exact_fields(profile, ("profile_version", "digest"), f"{described} profile")
        records._require_int(profile, "profile_version", f"{described} profile", minimum=1)
        records._require_digest(profile, "digest", f"{described} profile")
    return serialize.canonical_data(found)


def source_witness(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """The bounded B0/B1 currentness witness of a snapshot (§31.16): HEAD, every bound record digest, the Profile."""
    found = parse_source_snapshot(snapshot, "the source snapshot")
    return serialize.canonical_data({key: found[key] for key in WITNESS_FIELDS})


def witness_problem(bound: Mapping[str, Any], current: Mapping[str, Any]) -> str | None:
    """Why the source evidence ``bound`` names is no longer current in ``current`` (a witness), or ``None``.

    Unrelated source HEAD movement does not invalidate: the bound immutable
    record digests and the Profile state witness must be unchanged (§31.16).
    """
    for name, value in (("bound", bound), ("current", current)):
        if not isinstance(value, Mapping) or set(value) != set(WITNESS_FIELDS):
            return f"the {name} witness is not exactly {{{', '.join(WITNESS_FIELDS)}}}"
    if bound["source_id"] != current["source_id"]:
        return "the two witnesses are of different sources"
    if list(bound["records"]) != list(current["records"]):
        return f"the bound evidence of source {bound['source_id']} changed"
    if bound["profile"] != current["profile"]:
        return f"the Profile state of source {bound['source_id']} changed"
    return None


# =========================================================================== independence and correlation (§31.17-§31.18)

BASIS_SAME_LINEAGE = "same_lineage"
BASIS_COPY_SOURCE = "copy_source"
BASIS_SAME_INCIDENT = "same_incident"
BASIS_SAME_IMPLEMENTATION = "same_implementation"
BASIS_CAUSAL_DEPENDENCY = "causal_dependency"
BASIS_DUPLICATE_OBSERVATION = "duplicate_observation"
BASIS_DISTINCT_LINEAGE = "distinct_lineage"
BASIS_DISTINCT_INCIDENT = "distinct_incident"
BASIS_DISTINCT_IMPLEMENTATION = "distinct_implementation"
BASIS_DEPENDENCIES_RULED_OUT = "shared_dependencies_ruled_out"
BASIS_LINEAGE_UNKNOWN = "lineage_unknown"
BASIS_COPY_SOURCES_UNKNOWN = "copy_sources_unknown"
BASIS_INCIDENT_UNKNOWN = "incident_unknown"
BASIS_IMPLEMENTATION_UNKNOWN = "implementation_unknown"
BASIS_DEPENDENCIES_UNKNOWN = "dependencies_unknown"
BASIS_DEPENDENCY_UNRESOLVED = "shared_dependency_unresolved"


def _overlaps(first: Sequence[str] | None, second: Sequence[str] | None) -> bool:
    return bool(first) and bool(second) and bool(set(first or ()) & set(second or ()))


def _copy_related(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    a_copies, b_copies = first["copy_sources"] or [], second["copy_sources"] or []
    return (first["lineage"] is not None and first["lineage"] in b_copies) \
        or (second["lineage"] is not None and second["lineage"] in a_copies) \
        or bool(set(a_copies) & set(b_copies))


def _shared_dependencies(first: Mapping[str, Any], second: Mapping[str, Any]) -> list[tuple[str, str]]:
    a = {item["identity"]: item["common_cause"] for item in first["dependencies"] or []}
    b = {item["identity"]: item["common_cause"] for item in second["dependencies"] or []}
    return [(a[identity], b[identity]) for identity in sorted(set(a) & set(b))]


def relation(a: Mapping[str, Any], b: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    """The independence relation of two source snapshots and its positive basis (§31.17); symmetric.

    ``known_correlated`` needs a positive shared causal fact: the same
    lineage, a copy / fork / template relation, a shared incident or causal
    instance, a shared affected implementation, a shared dependency declared
    causal, or a duplicate observation (one record digest in both).
    ``proven_independent`` needs positive distinctness of everything: both
    lineages known and not copy-related, both copy-source lists declared, both
    incident and implementation sets declared and disjoint, both dependency
    lists declared and every shared one ruled out as the common cause on both
    sides. Anything missing or uncertain is ``independence_unresolved``; no
    absence of correlation is ever read as independence.
    """
    first = parse_source_snapshot(a, "the first source snapshot")
    second = parse_source_snapshot(b, "the second source snapshot")
    if first["source_id"] == second["source_id"]:
        raise _invalid("a source is never related to itself")
    pa, pb = first["provenance"], second["provenance"]
    shared_dependencies = _shared_dependencies(pa, pb)
    correlated: list[str] = []
    if pa["lineage"] is not None and pa["lineage"] == pb["lineage"]:
        correlated.append(BASIS_SAME_LINEAGE)
    if _copy_related(pa, pb):
        correlated.append(BASIS_COPY_SOURCE)
    if _overlaps(pa["incidents"], pb["incidents"]):
        correlated.append(BASIS_SAME_INCIDENT)
    if _overlaps(pa["implementations"], pb["implementations"]):
        correlated.append(BASIS_SAME_IMPLEMENTATION)
    if any(CAUSE_CAUSAL in pair for pair in shared_dependencies):
        correlated.append(BASIS_CAUSAL_DEPENDENCY)
    if {item["digest"] for item in first["records"]} & {item["digest"] for item in second["records"]}:
        correlated.append(BASIS_DUPLICATE_OBSERVATION)
    if correlated:
        return RELATION_CORRELATED, tuple(sorted(correlated))
    unresolved: list[str] = []
    if pa["lineage"] is None or pb["lineage"] is None:
        unresolved.append(BASIS_LINEAGE_UNKNOWN)
    if pa["copy_sources"] is None or pb["copy_sources"] is None:
        unresolved.append(BASIS_COPY_SOURCES_UNKNOWN)
    if not pa["incidents"] or not pb["incidents"]:
        unresolved.append(BASIS_INCIDENT_UNKNOWN)
    if not pa["implementations"] or not pb["implementations"]:
        unresolved.append(BASIS_IMPLEMENTATION_UNKNOWN)
    if pa["dependencies"] is None or pb["dependencies"] is None:
        unresolved.append(BASIS_DEPENDENCIES_UNKNOWN)
    elif any(pair != (CAUSE_RULED_OUT, CAUSE_RULED_OUT) for pair in shared_dependencies):
        unresolved.append(BASIS_DEPENDENCY_UNRESOLVED)
    if unresolved:
        return RELATION_UNRESOLVED, tuple(sorted(unresolved))
    return RELATION_INDEPENDENT, tuple(sorted((BASIS_DISTINCT_LINEAGE, BASIS_DISTINCT_INCIDENT,
                                               BASIS_DISTINCT_IMPLEMENTATION, BASIS_DEPENDENCIES_RULED_OUT)))


def _require_snapshots(snapshots: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(snapshots, (list, tuple)):
        raise _invalid("the source snapshots are a sequence")
    parsed = [parse_source_snapshot(item, "a source snapshot") for item in snapshots]
    ids = [item["source_id"] for item in parsed]
    if len(set(ids)) != len(ids):
        raise _invalid("two source snapshots are of one source")
    return sorted(parsed, key=lambda item: item["source_id"])


def clustering(snapshots: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The correlation clusters and the pairwise relation matrix of ``snapshots`` (§31.18).

    ``{"clusters": [{"sources": [...]}, ...], "matrix": [{"sources", "relation", "basis"}, ...]}``.
    Known-correlated sources are one cluster (transitively); unresolved and
    independent pairs stay apart, and whether two clusters count separately
    is read from the matrix - only when every cross pair is proven
    independent. Deterministic: sorted by source id, never by position.
    """
    parsed = _require_snapshots(snapshots)
    ids = [item["source_id"] for item in parsed]
    parent = {source_id: source_id for source_id in ids}

    def root(source_id: str) -> str:
        while parent[source_id] != source_id:
            source_id = parent[source_id]
        return source_id

    matrix: list[dict[str, Any]] = []
    for first, second in combinations(parsed, 2):
        found, basis = relation(first, second)
        matrix.append({"sources": [first["source_id"], second["source_id"]], "relation": found, "basis": list(basis)})
        if found == RELATION_CORRELATED:
            a, b = root(first["source_id"]), root(second["source_id"])
            parent[max(a, b)] = min(a, b)
    groups: dict[str, list[str]] = {}
    for source_id in ids:
        groups.setdefault(root(source_id), []).append(source_id)
    clusters = sorted((sorted(members) for members in groups.values()), key=lambda members: members[0])
    return serialize.canonical_data({"clusters": [{"sources": members} for members in clusters], "matrix": matrix})


def _relation_of(matrix: Sequence[Mapping[str, Any]]) -> dict[frozenset[str], str]:
    return {frozenset(item["sources"]): str(item["relation"]) for item in matrix}


def _independent_clusters(clusters: Sequence[Sequence[str]], matrix: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    """The largest set of clusters that are mutually proven independent - exhaustive, the first in sorted order."""
    relations = _relation_of(matrix)

    def independent(first: Sequence[str], second: Sequence[str]) -> bool:
        return all(relations.get(frozenset((x, y))) == RELATION_INDEPENDENT for x in first for y in second)

    ordered = [list(cluster) for cluster in clusters]
    for size in range(len(ordered), 0, -1):
        for chosen in combinations(ordered, size):
            if all(independent(x, y) for x, y in combinations(chosen, 2)):
                return [list(cluster) for cluster in chosen]
    return []


def _lineage_groups(snapshots: Sequence[Mapping[str, Any]]) -> int:
    """How many distinct repository lineages the sources positively name (copies of one lineage are one)."""
    known = [item["provenance"] for item in snapshots if item["provenance"]["lineage"] is not None]
    parent = list(range(len(known)))

    def root(index: int) -> int:
        while parent[index] != index:
            index = parent[index]
        return index

    for i, j in combinations(range(len(known)), 2):
        if known[i]["lineage"] == known[j]["lineage"] or _copy_related(known[i], known[j]):
            parent[max(root(i), root(j))] = min(root(i), root(j))
    return len({root(index) for index in range(len(known))})


# =========================================================================== mechanical eligibility (§31.19-§31.20)

def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[._-]+", text.lower()) if token]


def _contains_tokens(haystack: list[str], needle: list[str]) -> bool:
    return bool(needle) and any(haystack[index:index + len(needle)] == needle
                                for index in range(len(haystack) - len(needle) + 1))


def _mechanism_specific(mechanism: str, snapshots: Sequence[Mapping[str, Any]]) -> bool:
    """§16.8: the mechanism names a source Project, or is one source's own semantic surface label verbatim."""
    tokens = _tokens(mechanism)
    for snapshot in snapshots:
        if _contains_tokens(tokens, _tokens(snapshot["source_id"])):
            return True
        if any(_tokens(label) == tokens for label in snapshot["semantic_surfaces"]):
            return True
    return False


def _word_floor(direction: str) -> str:
    """The floor the direction word alone implies; a movement that lightens raises it (:func:`promotion_packet`)."""
    return FLOOR_LIGHTEN if direction == DIRECTION_LIGHTEN else FLOOR_STRENGTHEN


def eligibility(request: Mapping[str, Any], snapshots: Sequence[Mapping[str, Any]],
                clusters: Mapping[str, Any]) -> dict[str, Any]:
    """The mechanical promotion eligibility of ``request`` over its snapshots and clusters (§31.19); never raises
    for "not eligible".

    The floor is the one the direction word implies (``lighten`` for a
    lightening, ``strengthen`` otherwise); a change whose movement lightens is
    held to the lighten floor by :func:`promotion_packet`, which knows the
    before setting (§31.26: never the direction word alone). An exact rollback
    (§31.20) rests on its exception and needs no fresh cross-Project trend;
    its exactness is :func:`exact_rollback_problem`'s.

    Without the pre-change setting this answer is PROVISIONAL under the
    lighten floor (``pre_change_setting`` is ``None``): it counts only the
    opportunities whose Run positively froze a setting, and
    :func:`promotion_packet` - the governing decision - then counts only those
    that exercised at least the pre-change (stronger) setting.
    """
    record = _require_request(request)
    return _eligibility(record, snapshots, clusters, _word_floor(record["direction"]), None)


def _exercised(entries: Sequence[Mapping[str, Any]], pre_change_setting: int | None) -> list[str]:
    """The opportunities that exercised the stronger pre-change behaviour (§31.19 L12023, §16.10 L4499).

    Only a Run that positively froze its effective setting of the surface
    counts, and only when that setting is at least the pre-change one: an
    opportunity under a lighter setting, or whose setting is unknown, says
    nothing about the behaviour a lightening removes. With no pre-change
    setting given (the provisional word-floor answer), every known setting
    counts.
    """
    return [str(entry["review_run_id"]) for entry in entries if entry["setting"] is not None
            and (pre_change_setting is None or entry["setting"] >= pre_change_setting)]


def _eligibility(record: Mapping[str, Any], snapshots: Sequence[Mapping[str, Any]], clusters: Mapping[str, Any],
                 floor: str, pre_change_setting: int | None) -> dict[str, Any]:
    """Eligibility under ``floor``; ``pre_change_setting`` is the surface's before setting where it is known."""
    parsed = _require_snapshots(snapshots)
    surface_id = record["policy_surface_id"]
    mechanism = record["generalized_mechanism_id"]
    problems: list[str] = []
    by_id = {item["source_id"]: item for item in parsed}
    if sorted(by_id) != list(record["sources"]) or any(
            _record_refs_of(record["evidence"][source_id]) != by_id[source_id]["records"]
            or {key: value for key, value in _provenance_of(record["evidence"][source_id]).items() if key != "kind"}
            != by_id[source_id]["provenance"] for source_id in by_id):
        problems.append("sources_mismatch")
    computed = clustering(parsed)
    if not isinstance(clusters, Mapping) or serialize.canonical_data(dict(clusters)) != computed:
        problems.append("clusters_mismatch")
    supporting: list[str] = []
    excluded: list[dict[str, Any]] = []
    for snapshot in parsed:
        reasons: list[str] = []
        if snapshot["provenance"]["mechanism"] != mechanism:
            reasons.append("mechanism_differs")
        if not snapshot["opportunities"][surface_id]:
            reasons.append("no_relevant_opportunity")
        if snapshot["unresolved_human"]:
            reasons.append("unresolved_human")
        if reasons:
            excluded.append({"source_id": snapshot["source_id"], "reasons": reasons})
        else:
            supporting.append(snapshot["source_id"])
    if any(snapshot["unresolved_human"] for snapshot in parsed):
        problems.append("unresolved_human")
    if _mechanism_specific(mechanism, parsed):
        problems.append("mechanism_project_specific")
    counted = [cluster["sources"] for cluster in computed["clusters"]
               if any(member in supporting for member in cluster["sources"])]
    independent = _independent_clusters(counted, computed["matrix"])
    lineages = _lineage_groups([by_id[source_id] for source_id in supporting])
    opportunities = {source_id: [entry["review_run_id"] for entry in by_id[source_id]["opportunities"][surface_id]]
                     for source_id in supporting}
    basis = BASIS_EXACT_ROLLBACK if record["rollback_of"] is not None else BASIS_CROSS_PROJECT
    if basis == BASIS_CROSS_PROJECT:
        if lineages < FLOOR_LINEAGES[floor]:
            problems.append("too_few_lineages")
        if len(independent) < FLOOR_CLUSTERS[floor]:
            problems.append("too_few_independent_clusters")
        exercised = {source_id: _exercised(by_id[source_id]["opportunities"][surface_id], pre_change_setting)
                     for source_id in supporting}
        if floor == FLOOR_LIGHTEN and any(
                sum(len(exercised.get(member, ())) for member in cluster) < policy.SINGLE_EVENT_FLOOR
                for cluster in independent):
            problems.append("unrepresentative_opportunities")
    return serialize.canonical_data({
        "eligible": not problems,
        "floor": floor,
        "problems": problems,
        "basis": basis,
        "pre_change_setting": pre_change_setting,
        "request_digest": request_digest(record),
        "policy_surface_id": surface_id,
        "generalized_mechanism_id": mechanism,
        "supporting_sources": supporting,
        "excluded_sources": excluded,
        "lineages": lineages,
        "independent_clusters": [{"sources": members} for members in independent],
        "opportunities": sum(len(items) for items in opportunities.values()),
        "holdout_required": floor == FLOOR_LIGHTEN,
    })


def exact_rollback_problem(request: Mapping[str, Any], before_global: Mapping[str, Any], change: Mapping[str, Any],
                           evaluation: Mapping[str, Any]) -> str | None:
    """Why ``request`` may not use the exact-rollback exception (§31.20), or ``None`` when it may.

    ``change`` is the stored change it rolls back and ``evaluation`` the stored
    evaluation that must prove the frozen rollback threshold fired: a
    ``rollback`` evaluation of that change under its frozen measurement
    contract, of the Global the change produced or of the current one. The
    rollback restores exactly the change's before setting on the same surface,
    whose current setting is still the change's after setting; the fixed
    meta-rules still admit that setting, and Profile compatibility stays total.
    """
    try:
        record = _require_request(request)
        before = _require_global(before_global, "the before Global policy")
        found_change = parse_change_record(change, "the rolled-back Global change")
        found_evaluation = parse_evaluation_record(evaluation, "the rollback evaluation")
    except (StopError, ValidationError) as exc:
        return f"the exact-rollback inputs do not read: {exc}"
    if record["direction"] != DIRECTION_ROLLBACK or record["rollback_of"] is None:
        return "the request does not use the exact-rollback exception"
    change_id = found_change["global_policy_change_id"]
    if record["rollback_of"] != change_id or record["rollback_evaluation_id"] != found_evaluation["evaluation_id"]:
        return "the request does not name exactly this change and this evaluation"
    if found_evaluation["global_policy_change_id"] != change_id or found_evaluation["result"] != RESULT_ROLLBACK:
        return f"no rollback evaluation of {change_id} proves its frozen rollback threshold fired"
    if found_evaluation["measurement_contract_digest"] != serialize.digest(dict(found_change["measurement_contract"])):
        return "the evaluation did not measure under the change's frozen measurement contract"
    if found_evaluation["evaluated_global_policy_digest"] not in (found_change["after_global_policy_digest"],
                                                                 policy.global_policy_digest(before)):
        return "the evaluation is not of the Global policy the change produced or of the current one"
    surface_id = found_change["policy_surface_id"]
    if record["policy_surface_id"] != surface_id:
        return f"the rollback is not on the change's own surface {surface_id}"
    if _settings(before)[surface_id] != found_change["after_setting"]:
        return f"the current {surface_id} setting is not the one {change_id} set; the change is not the one in force"
    if record["after_setting"] != found_change["before_setting"]:
        return f"the rollback target is not exactly {change_id}'s before setting {found_change['before_setting']}"
    if policy.surface_problem(surface_id) is not None \
            or not policy.SURFACE_BY_ID[surface_id].in_range(found_change["before_setting"]):
        return "the fixed meta-rules no longer admit the before setting"
    try:
        compatibility_proof(before, after_global_policy(before, record))
    except (StopError, ValidationError) as exc:
        return f"Profile compatibility is not total for the rollback: {exc}"
    return None


def require_exact_rollback(request: Mapping[str, Any], before_global: Mapping[str, Any], change: Mapping[str, Any],
                           evaluation: Mapping[str, Any]) -> None:
    problem = exact_rollback_problem(request, before_global, change, evaluation)
    if problem is not None:
        raise stop(CODE_ROLLBACK_INEXACT, f"the exact-rollback exception does not apply: {problem}; a non-exact "
                                          "rollback follows ordinary eligibility by its actual direction")


# =========================================================================== Profile compatibility adapter v1 (§31.21)

#: How adapter v1 interprets a Profile v1 override under a changed Global default: an absolute local setting, kept.
OVERRIDE_RULE = "absolute_local_override_preserved"
SUPPORTED_PROFILE_SCHEMA_VERSIONS = (policy.RECORD_VERSION,)
COMPATIBILITY_PROOF_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "adapter_identity", "profile_schema",
    "supported_profile_schema_versions", "loader_semantics_identity", "before_global_policy_digest",
    "after_global_policy_digest", "surfaces", "override_rule", "fields_preserved", "cases", "total",
)


def _settings_problem(settings: object, described: str) -> str | None:
    if not isinstance(settings, Mapping) or set(settings) != set(policy.SURFACE_BY_ID):
        return f"{described} do not set exactly the fixed surfaces"
    for surface_id, value in settings.items():
        if not policy.SURFACE_BY_ID[surface_id].in_range(value):
            return f"{described} set {surface_id} to {value!r}, outside its fixed range"
    return None


def adapter_v1_problem(profile: "policy.ProjectProfile | None", old_settings: Mapping[str, int],
                       new_settings: Mapping[str, int]) -> str | None:
    """Why adapter v1 cannot interpret ``profile`` under ``new_settings``, or ``None`` - total over Profile v1.

    Every structurally valid Profile v1 of the running loader semantics is
    interpreted (absence included); anything else - another Profile schema,
    another loader, a structurally invalid record - is refused, never guessed.
    A mandatory surface may never end below a stronger new Global default
    through an old local override (vacuous for v1: both surfaces are default /
    adaptive, §31.21), and the overlay stays inside every fixed range.
    """
    for name, settings in (("the old Global settings", old_settings), ("the new Global settings", new_settings)):
        problem = _settings_problem(settings, name)
        if problem is not None:
            return problem
    if profile is None:
        return None
    if type(profile) is not policy.ProjectProfile:
        return f"a {type(profile).__name__} is not a supported Project Profile schema (v1 only)"
    if profile.loader_semantics_identity != policy.LOADER_SEMANTICS_IDENTITY:
        return "the Profile binds another loader semantics identity; no adapter interprets it"
    try:
        record = profile.to_record()
    except (TypeError, AttributeError) as exc:
        return f"the Profile does not render as a Profile v1 record ({exc})"
    if record.get(serialize.VERSION_KEY) not in SUPPORTED_PROFILE_SCHEMA_VERSIONS:
        return "the Profile is not a supported schema version"
    structural = policy.profile_problems(record, "the Profile")
    if structural:
        return f"the Profile is not a valid Profile v1: {structural[0][1]}"
    for item in profile.overrides:
        surface = policy.SURFACE_BY_ID[item["policy_surface_id"]]
        if surface.strength_class == policy.CLASS_MANDATORY and item["setting"] < new_settings[surface.policy_surface_id]:
            return f"an old local override would weaken the stronger mandatory Global {surface.policy_surface_id}"
    return None


def adapt_profile_v1(profile: "policy.ProjectProfile | None", old_settings: Mapping[str, int],
                     new_settings: Mapping[str, int]) -> dict[str, int]:
    """The effective overlay of ``profile`` under the new Global: each override kept as its absolute local setting,
    every other surface at the new Global setting (§31.21). No Profile field is dropped, renamed or rewritten."""
    problem = adapter_v1_problem(profile, old_settings, new_settings)
    if problem is not None:
        raise stop(CODE_COMPATIBILITY_UNPROVEN, f"Profile compatibility adapter v1: {problem}")
    found: dict[str, int] = {}
    for surface in policy.SURFACES:
        override = None if profile is None else profile.setting_of(surface.policy_surface_id)
        found[surface.policy_surface_id] = int(new_settings[surface.policy_surface_id]) if override is None else override
    return found


def _local_semantics(profile: "policy.ProjectProfile | None") -> dict[str, int | None]:
    """The normalized local override semantics: each surface's absolute override, or ``None`` (follow Global)."""
    return {surface.policy_surface_id: None if profile is None else profile.setting_of(surface.policy_surface_id)
            for surface in policy.SURFACES}


def _profile_domain(old_settings: Mapping[str, int]) -> list["policy.ProjectProfile | None"]:
    """Every override-presence / setting / direction combination of Profile v1 over the two fixed surfaces."""
    choices: list[list[dict[str, Any] | None]] = []
    for surface in policy.SURFACES:
        options: list[dict[str, Any] | None] = [None]
        for value in range(surface.minimum, surface.maximum + 1):
            for direction in policy.OVERRIDE_DIRECTIONS:
                options.append({"policy_surface_id": surface.policy_surface_id, "strength_class": surface.strength_class,
                                "setting": value, "direction": direction,
                                "supporting_policy_change_id": "rpc_" + "0" * 26})
        choices.append(options)
    found: list[policy.ProjectProfile | None] = [None]
    stub = "0" * 64
    for first in choices[0]:
        for second in choices[1]:
            overrides = tuple(item for item in (first, second) if item is not None)
            found.append(policy.ProjectProfile(
                profile_version=1, parent_profile_digest=None, global_baseline_digest=stub,
                global_baseline_version=1, loader_semantics_identity=policy.LOADER_SEMANTICS_IDENTITY,
                overrides=overrides, active_experiment_refs=()))
    return found


def compatibility_proof(before_global: Mapping[str, Any], after_global: Mapping[str, Any]) -> dict[str, Any]:
    """The total Profile v1 compatibility proof of a Global change (§31.21, §16.11); ``review_p7_compatibility_unproven``.

    Exhaustive over the finite v1 domain: absence and every override
    presence / setting / direction combination of both surfaces. For each,
    adapter v1 keeps the normalized local override semantics, the overlay is
    exactly "the override, else the new Global setting" inside every fixed
    range, and no mandatory surface is weakened. The proof is a record whose
    digest the Packet, the Candidate, the change record and Consumption v4 bind.
    """
    before = _require_global(before_global, "the before Global policy")
    after = _require_global(after_global, "the after Global policy")
    if (before["loader_semantics_identity"], before["fixed_meta_rules_identity"]) \
            != (after["loader_semantics_identity"], after["fixed_meta_rules_identity"]):
        raise stop(CODE_COMPATIBILITY_UNPROVEN, "the two Global policies bind other loader semantics or meta-rules; "
                                                "adapter v1 interprets a changed Global setting only")
    old, new = _settings(before), _settings(after)
    cases = 0
    for profile in _profile_domain(old):
        problem = adapter_v1_problem(profile, old, new)
        if problem is not None:
            raise stop(CODE_COMPATIBILITY_UNPROVEN, f"Profile v1 case {cases + 1} is not interpreted: {problem}")
        overlay = adapt_profile_v1(profile, old, new)
        local = _local_semantics(profile)
        for surface in policy.SURFACES:
            surface_id = surface.policy_surface_id
            expected = new[surface_id] if local[surface_id] is None else local[surface_id]
            if overlay[surface_id] != expected or not surface.in_range(overlay[surface_id]):
                raise stop(CODE_COMPATIBILITY_UNPROVEN, f"Profile v1 case {cases + 1} does not keep its local override "
                                                        f"semantics on {surface_id}")
        cases += 1
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_COMPATIBILITY_PROOF, serialize.VERSION_KEY: RECORD_VERSION,
        "adapter_identity": ADAPTER_V1_IDENTITY,
        "profile_schema": policy.SCHEMA_PROFILE,
        "supported_profile_schema_versions": list(SUPPORTED_PROFILE_SCHEMA_VERSIONS),
        "loader_semantics_identity": policy.LOADER_SEMANTICS_IDENTITY,
        "before_global_policy_digest": policy.global_policy_digest(before),
        "after_global_policy_digest": policy.global_policy_digest(after),
        "surfaces": [{"policy_surface_id": surface.policy_surface_id, "strength_class": surface.strength_class,
                      "minimum": surface.minimum, "maximum": surface.maximum,
                      "before_setting": old[surface.policy_surface_id], "after_setting": new[surface.policy_surface_id]}
                     for surface in policy.SURFACES],
        "override_rule": OVERRIDE_RULE,
        "fields_preserved": list(policy.PROFILE_FIELDS),
        "cases": cases,
        "total": True,
    })


def compatibility_proof_digest(proof: Mapping[str, Any]) -> str:
    return serialize.digest(dict(proof))


# --------------------------------------------------------------------------- R6-2: which interpretation applies (RB7-F step 4)

def compatibility_interpretation(old_baseline_record: Mapping[str, Any],
                                 new_baseline_record: Mapping[str, Any]) -> str:
    """The compatibility interpretation the next Run boundary applies to a Profile written under ``old``.

    Equal policy-semantic projections (R6-2) - the initial materialization and
    every text-only root edit included - keep the exact derived-semantic
    interpretation; only a real changed Global projection uses the total
    adapter v1 (CP RB7-PREP item 4).
    """
    if policy.semantic_projection(old_baseline_record) == policy.semantic_projection(new_baseline_record):
        return policy.COMPATIBILITY_EXACT_DERIVED_SEMANTIC
    return ADAPTER_V1_IDENTITY


def projection_change_problem(old_baseline_record: Mapping[str, Any],
                              new_baseline_record: Mapping[str, Any]) -> str | None:
    """Why adapter v1 cannot bridge two baseline projections, or ``None``.

    Adapter v1 bridges a changed Global policy version and changed Global
    settings only; a change of any surface's identity, class or range, of the
    meta-rules or of the loader semantics is not a Global Policy Change it
    interprets (no guess, no merge).
    """
    old = policy.semantic_projection(old_baseline_record)
    new = policy.semantic_projection(new_baseline_record)
    if old == new:
        return None

    def fixed(projection: Mapping[str, Any]) -> dict[str, Any]:
        return {**{key: value for key, value in projection.items() if key not in ("baseline_version", "surfaces")},
                "surfaces": [{key: value for key, value in item.items() if key != "global_setting"}
                             for item in projection["surfaces"]]}

    if fixed(old) != fixed(new):
        return ("the Global baselines differ beyond the Global policy version and settings (surfaces, meta-rules or "
                "loader semantics); adapter v1 does not interpret that")
    return None


def profile_compatibility_problem(profile: "policy.ProjectProfile | None", old_baseline_record: Mapping[str, Any],
                                  new_baseline_record: Mapping[str, Any]) -> str | None:
    """The P7 compatibility decision of ``profile`` (written under ``old``) under ``new``: ``None`` when proven."""
    if compatibility_interpretation(old_baseline_record, new_baseline_record) \
            == policy.COMPATIBILITY_EXACT_DERIVED_SEMANTIC:
        return None
    problem = projection_change_problem(old_baseline_record, new_baseline_record)
    if problem is not None:
        return problem
    return adapter_v1_problem(profile, policy.bound_global_settings(old_baseline_record),
                              policy.bound_global_settings(new_baseline_record))


# =========================================================================== the after-state and the Promotion Packet (§31.22-§31.23)

def after_global_policy(before_global: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    """The proposed after Global policy: the exact next version, parent = the before digest, one surface set (§31.22).

    The direction word must agree with the movement - a strengthen raises, a
    lighten lowers (higher integer is stronger) - and the setting must change.
    """
    before = _require_global(before_global, "the before Global policy")
    record = _require_request(request)
    surface_id = record["policy_surface_id"]
    settings = _settings(before)
    before_setting, after_setting = settings[surface_id], int(record["after_setting"])
    if after_setting == before_setting:
        raise stop(CODE_REQUEST_INVALID, f"the request changes no setting: {surface_id} is already {before_setting}")
    direction = record["direction"]
    if direction == DIRECTION_STRENGTHEN and _lightens(before_setting, after_setting):
        raise stop(CODE_REQUEST_INVALID, f"a strengthen raises {surface_id}; {before_setting} -> {after_setting} "
                                         "lightens it")
    if direction == DIRECTION_LIGHTEN and not _lightens(before_setting, after_setting):
        raise stop(CODE_REQUEST_INVALID, f"a lighten lowers {surface_id}; {before_setting} -> {after_setting} "
                                         "strengthens it")
    settings[surface_id] = after_setting
    return policy.global_policy_record(before["global_policy_version"] + 1, policy.global_policy_digest(before), settings)


def movement_floor(before_global: Mapping[str, Any], after_global: Mapping[str, Any]) -> str:
    """The floor a Global change is held to by its movement: ``lighten`` whenever the one changed setting lowers."""
    before = _require_global(before_global, "the before Global policy")
    after = _require_global(after_global, "the after Global policy")
    problem = policy.global_policy_successor_problem(before, after)
    if problem is not None:
        raise _invalid(problem)
    old, new = _settings(before), _settings(after)
    changed = [surface_id for surface_id in sorted(old) if old[surface_id] != new[surface_id]]
    if len(changed) != 1:
        raise _invalid(f"a Global Policy Change sets exactly one surface; {len(changed)} differ")
    return FLOOR_LIGHTEN if _lightens(old[changed[0]], new[changed[0]]) else FLOOR_STRENGTHEN


PACKET_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "promotion_packet_id", "global_policy_change_id",
    "before_global_policy_version", "before_global_policy_digest", "after_global_policy", "after_global_policy_digest",
    "policy_surface_id", "strength_class", "direction", "before_setting", "after_setting", "generalized_mechanism_id",
    "summary", "source_snapshots", "clusters", "relation_matrix", "eligibility", "relevant_opportunities",
    "local_outcomes", "escape_evidence", "expected_effect", "measurement_contract", "success_criteria",
    "rollback_contract", "supported_profile_schema_versions", "compatibility_adapter_identity",
    "compatibility_proof_digest", "environment_diversity", "rollback_exception",
)
ROLLBACK_CONTRACT_FIELDS = ("threshold", "unit")
ROLLBACK_UNIT_FIELDS = ("policy_surface_id", "restore_setting", "restore_global_policy_digest")
ROLLBACK_EXCEPTION_FIELDS = ("global_policy_change_id", "evaluation_id")
DIVERSITY_FIELDS = ("toolchains", "reviewers", "check_adapters", "dependencies", "undeclared_sources")


def _environment_diversity(snapshots: Sequence[Mapping[str, Any]], supporting: Sequence[str]) -> dict[str, Any]:
    found: dict[str, set[str]] = {"toolchains": set(), "reviewers": set(), "check_adapters": set(),
                                  "dependencies": set()}
    undeclared: list[str] = []
    for snapshot in snapshots:
        if snapshot["source_id"] not in supporting:
            continue
        environment = snapshot["provenance"]["environment"]
        if environment is None:
            undeclared.append(snapshot["source_id"])
            continue
        found["toolchains"].add(environment["toolchain"])
        for name in ("reviewers", "check_adapters", "dependencies"):
            found[name].update(environment[name])
    return {**{name: sorted(values) for name, values in found.items()}, "undeclared_sources": sorted(undeclared)}


def _packet_evidence(snapshots: Sequence[Mapping[str, Any]], supporting: Sequence[str],
                     surface_id: str) -> dict[str, Any]:
    return {
        "relevant_opportunities": [
            {"source_id": snapshot["source_id"],
             "opportunities": [entry["review_run_id"] for entry in snapshot["opportunities"][surface_id]]}
            for snapshot in snapshots if snapshot["source_id"] in supporting],
        "local_outcomes": [{"source_id": snapshot["source_id"], **item}
                           for snapshot in snapshots for item in snapshot["local_outcomes"]],
        "escape_evidence": [{"source_id": snapshot["source_id"], **item}
                            for snapshot in snapshots for item in snapshot["escapes"]],
        "environment_diversity": _environment_diversity(snapshots, supporting),
    }


def promotion_packet(request: Mapping[str, Any], *, promotion_packet_id: str, global_policy_change_id: str,
                     before_global: Mapping[str, Any], after_global: Mapping[str, Any],
                     snapshots: Sequence[Mapping[str, Any]], clusters: Mapping[str, Any],
                     eligibility: Mapping[str, Any], proof: Mapping[str, Any]) -> dict[str, Any]:
    """The immutable Promotion Packet (§31.23, §16.9): evidence, never authorization.

    Everything is re-derived from ``request``, the before Global and the
    snapshots, and the given parts must be exactly those derivations: the
    after-state, the clusters, the eligibility under the direction word, the
    compatibility proof. The Packet's eligibility is the one the MOVEMENT
    decides (a change that lowers the setting is held to the lighten floor
    whatever its direction word): ``review_p7_not_eligible`` when it fails.
    """
    record = _require_request(request)
    if not _is_id(promotion_packet_id, "review_promotion_packet") \
            or not _is_id(global_policy_change_id, "review_global_policy_change"):
        raise _invalid("a Promotion Packet is named by a review_promotion_packet id and its review_global_policy_change id")
    before = _require_global(before_global, "the before Global policy")
    after = _require_global(after_global, "the after Global policy")
    if after != after_global_policy(before, record):
        raise reconcile("the after Global policy is not the exact successor this request proposes",
                        REASON_CANDIDATE_MISMATCH)
    parsed = _require_snapshots(snapshots)
    computed_clusters = clustering(parsed)
    if not isinstance(clusters, Mapping) or serialize.canonical_data(dict(clusters)) != computed_clusters:
        raise reconcile("the clusters are not the clustering of these source snapshots", REASON_CANDIDATE_MISMATCH)
    if serialize.canonical_data(dict(eligibility)) != _eligibility(record, parsed, computed_clusters,
                                                                    _word_floor(record["direction"]), None):
        raise reconcile("the eligibility is not this request's over these snapshots", REASON_CANDIDATE_MISMATCH)
    if serialize.canonical_data(dict(proof)) != compatibility_proof(before, after):
        raise stop(CODE_COMPATIBILITY_UNPROVEN, "the compatibility proof is not the total adapter-v1 proof of this "
                                                "before / after Global policy")
    floor = movement_floor(before, after)
    governing = _eligibility(record, parsed, computed_clusters, floor, _settings(before)[record["policy_surface_id"]])
    if not governing["eligible"]:
        raise stop(CODE_NOT_ELIGIBLE, f"the promotion is not eligible under the {floor} floor: "
                                      f"{', '.join(governing['problems'])}; eligibility is only a floor, never a reason "
                                      "to guess")
    surface_id = record["policy_surface_id"]
    surface = policy.SURFACE_BY_ID[surface_id]
    before_setting, after_setting = _settings(before)[surface_id], _settings(after)[surface_id]
    packet = {
        serialize.SCHEMA_KEY: SCHEMA_PACKET, serialize.VERSION_KEY: RECORD_VERSION,
        "promotion_packet_id": promotion_packet_id, "global_policy_change_id": global_policy_change_id,
        "before_global_policy_version": before["global_policy_version"],
        "before_global_policy_digest": policy.global_policy_digest(before),
        "after_global_policy": after, "after_global_policy_digest": policy.global_policy_digest(after),
        "policy_surface_id": surface_id, "strength_class": surface.strength_class, "direction": record["direction"],
        "before_setting": before_setting, "after_setting": after_setting,
        "generalized_mechanism_id": record["generalized_mechanism_id"], "summary": record["summary"],
        "source_snapshots": [{"source_id": snapshot["source_id"], "digest": serialize.digest(snapshot),
                              "snapshot": snapshot} for snapshot in parsed],
        "clusters": computed_clusters["clusters"], "relation_matrix": computed_clusters["matrix"],
        "eligibility": governing,
        **_packet_evidence(parsed, governing["supporting_sources"], surface_id),
        "expected_effect": record["expected_effect"],
        "measurement_contract": dict(record["measurement_contract"]),
        "success_criteria": record["measurement_contract"]["success_criteria"],
        "rollback_contract": {"threshold": record["rollback_contract"]["threshold"],
                              "unit": {"policy_surface_id": surface_id, "restore_setting": before_setting,
                                       "restore_global_policy_digest": policy.global_policy_digest(before)}},
        "supported_profile_schema_versions": list(SUPPORTED_PROFILE_SCHEMA_VERSIONS),
        "compatibility_adapter_identity": ADAPTER_V1_IDENTITY,
        "compatibility_proof_digest": compatibility_proof_digest(proof),
        "rollback_exception": None if record["rollback_of"] is None else {
            "global_policy_change_id": record["rollback_of"], "evaluation_id": record["rollback_evaluation_id"]},
    }
    return parse_promotion_packet(packet, "the Promotion Packet")


def _request_of_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    """The request a Packet states (what eligibility reads), re-derived from the Packet's own fields and snapshots."""
    exception = packet["rollback_exception"]
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_CHANGE_REQUEST, serialize.VERSION_KEY: RECORD_VERSION,
        "policy_surface_id": packet["policy_surface_id"], "direction": packet["direction"],
        "after_setting": packet["after_setting"], "generalized_mechanism_id": packet["generalized_mechanism_id"],
        "summary": packet["summary"], "expected_effect": packet["expected_effect"],
        "measurement_contract": dict(packet["measurement_contract"]),
        "rollback_contract": {"threshold": packet["rollback_contract"]["threshold"]},
        "sources": [item["source_id"] for item in packet["source_snapshots"]],
        "evidence": {item["source_id"]: _normal_evidence(
            [{"kind": REF_PROVENANCE, **item["snapshot"]["provenance"]}]
            + [{"kind": REF_RECORD, **ref} for ref in item["snapshot"]["records"]])
            for item in packet["source_snapshots"]},
        "rollback_of": None if exception is None else exception["global_policy_change_id"],
        "rollback_evaluation_id": None if exception is None else exception["evaluation_id"],
    })


def parse_promotion_packet(record: object, described: str) -> dict[str, Any]:
    """A Promotion Packet, strictly: its fields, every derivation re-proven from its own content (§31.23)."""
    found = records._require_mapping(record, described)
    serialize.require_schema(found, SCHEMA_PACKET, RECORD_VERSION, described)
    records._require_exact_fields(found, PACKET_FIELDS, described)
    records._require_id(found, "promotion_packet_id", "review_promotion_packet", described)
    records._require_id(found, "global_policy_change_id", "review_global_policy_change", described)
    records._require_int(found, "before_global_policy_version", described, minimum=1)
    records._require_digest(found, "before_global_policy_digest", described)
    after = _require_global(found["after_global_policy"], f"{described} after_global_policy")
    if found["after_global_policy_digest"] != policy.global_policy_digest(after) \
            or after["global_policy_version"] != found["before_global_policy_version"] + 1 \
            or after["parent_global_policy_digest"] != found["before_global_policy_digest"]:
        raise _invalid(f"{described} after Global policy is not the exact successor of its before Global policy")
    surface_id = found["policy_surface_id"]
    surface = policy.SURFACE_BY_ID.get(surface_id) if isinstance(surface_id, str) else None
    if surface is None or policy.surface_problem(surface_id) is not None \
            or found["strength_class"] != surface.strength_class:
        raise _invalid(f"{described} names no adaptable registered surface with its fixed class")
    if found["direction"] not in DIRECTIONS or not surface.in_range(found["before_setting"]) \
            or found["after_setting"] != _settings(after)[surface_id] or found["before_setting"] == found["after_setting"]:
        raise _invalid(f"{described} direction or settings are not one change of its surface")
    snapshots = records._require_list(found, "source_snapshots", described)
    parsed = []
    for item in snapshots:
        entry = records._require_mapping(item, f"{described} source snapshot")
        records._require_exact_fields(entry, ("source_id", "digest", "snapshot"), f"{described} source snapshot")
        snapshot = parse_source_snapshot(entry["snapshot"], f"{described} source snapshot")
        if entry["source_id"] != snapshot["source_id"] or entry["digest"] != serialize.digest(snapshot):
            raise _invalid(f"{described} source snapshot is not named by its own source and digest")
        parsed.append(snapshot)
    if [item["source_id"] for item in parsed] != sorted({item["source_id"] for item in parsed}):
        raise _invalid(f"{described} source snapshots are not sorted and duplicate-free")
    computed = clustering(parsed)
    if found["clusters"] != computed["clusters"] or found["relation_matrix"] != computed["matrix"]:
        raise _invalid(f"{described} clusters and relation matrix are not its snapshots' clustering")
    for name, problem in (("summary", _text_problem(found["summary"])),
                          ("expected_effect", _text_problem(found["expected_effect"])),
                          ("measurement_contract", _measurement_problem(found["measurement_contract"], "it"))):
        if problem is not None:
            raise _invalid(f"{described} {name}: {problem}")
    if found["success_criteria"] != found["measurement_contract"]["success_criteria"]:
        raise _invalid(f"{described} success criteria are not its measurement contract's")
    rollback = records._require_mapping(found["rollback_contract"], f"{described} rollback_contract")
    records._require_exact_fields(rollback, ROLLBACK_CONTRACT_FIELDS, f"{described} rollback_contract")
    if _text_problem(rollback["threshold"]) is not None or rollback["unit"] != {
            "policy_surface_id": surface_id, "restore_setting": found["before_setting"],
            "restore_global_policy_digest": found["before_global_policy_digest"]}:
        raise _invalid(f"{described} rollback contract does not restore exactly the before setting")
    if found["supported_profile_schema_versions"] != list(SUPPORTED_PROFILE_SCHEMA_VERSIONS) \
            or found["compatibility_adapter_identity"] != ADAPTER_V1_IDENTITY:
        raise _invalid(f"{described} does not bind the total adapter v1 over Profile v1")
    records._require_digest(found, "compatibility_proof_digest", described)
    exception = found["rollback_exception"]
    if exception is not None:
        exception = records._require_mapping(exception, f"{described} rollback_exception")
        records._require_exact_fields(exception, ROLLBACK_EXCEPTION_FIELDS, f"{described} rollback_exception")
        if found["direction"] != DIRECTION_ROLLBACK:
            raise _invalid(f"{described} uses the exact-rollback exception and is not a rollback")
    stated = _request_of_packet(found)
    if request_problems(stated):
        raise _invalid(f"{described} does not state a valid request: {request_problems(stated)[0][1]}")
    floor = FLOOR_LIGHTEN if _lightens(found["before_setting"], found["after_setting"]) else FLOOR_STRENGTHEN
    governing = _eligibility(stated, parsed, computed, floor, found["before_setting"])
    if found["eligibility"] != governing or not governing["eligible"]:
        raise _invalid(f"{described} eligibility is not the eligible {floor}-floor result of its own evidence")
    evidence = _packet_evidence(parsed, governing["supporting_sources"], surface_id)
    if any(found[name] != serialize.canonical_data(value) for name, value in evidence.items()):
        raise _invalid(f"{described} evidence summaries are not its snapshots'")
    return serialize.canonical_data(found)


# =========================================================================== the Candidate and the root Review Context (§31.24-§31.25)

CANDIDATE_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "review_kind", "target_identity", "promotion_packet_id",
    "promotion_packet_digest", "promotion_packet", "global_policy_change_id", "direction", "policy_surface_id",
    "before_setting", "after_setting", "before_global_policy", "before_global_policy_digest", "after_global_policy",
    "after_global_policy_digest", "normalized_projection_hash", "compatibility_proof", "compatibility_adapter_identity",
    "compatibility_proof_digest", "root_meta_policy", "required_discovery_slots", "expected_kp",
)
ROOT_META_POLICY_FIELDS = ("root_policy_id", "root_policy_hash", "meta_rules_id", "meta_rules_digest",
                           "loader_semantics_identity")
EXPECTED_KP_FIELDS = ("paths", "global_policy_digest", "normalized_projection_hash")
CONTEXT_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "review_kind", "contract", "root_policy_id", "root_policy_hash",
    "persisted_adapter_identity", "projection_semantics_version", "loader_identity", "loader_semantics_identity",
    "meta_rules_id", "meta_rules_digest", "before_global_policy_version", "before_global_policy_digest",
    "namespace_root",
)


def _root_policy_hash() -> str:
    """The static ``effective_policy_hash`` of every root Run (RB7C-1): the root family policy's own digest."""
    return p4.family_policy_hash(POLICY_ID)


def root_meta_policy() -> dict[str, Any]:
    """The fixed root meta-policy identity the Candidate binds and the meta-verifier re-checks (§31.24, §31.28)."""
    return {
        "root_policy_id": POLICY_ID, "root_policy_hash": _root_policy_hash(),
        "meta_rules_id": policy.META_RULES_ID, "meta_rules_digest": policy.meta_rules_digest(),
        "loader_semantics_identity": policy.LOADER_SEMANTICS_IDENTITY,
    }


def normalized_projection_hash(global_policy: Mapping[str, Any]) -> str:
    """What C-2(Kp), the Candidate and Consumption v4 compare: the loader's semantic projection of the record."""
    return serialize.digest(policy.global_policy_projection(_require_global(global_policy, "the Global policy")))


def expected_kp(global_policy_change_id: str, after_global: Mapping[str, Any]) -> dict[str, Any]:
    """Kp's exact delta and projection (§31.32, §31.35): the policy file, the change record and the Patch Note."""
    after = _require_global(after_global, "the after Global policy")
    layout = namespace.ROOT_POLICY_LAYOUT
    return {
        "paths": sorted([layout.global_policy_rel, layout.global_change_rel(global_policy_change_id),
                         layout.patch_note_rel(global_policy_change_id)]),
        "global_policy_digest": policy.global_policy_digest(after),
        "normalized_projection_hash": normalized_projection_hash(after),
    }


def required_discovery_slots(before_global: Mapping[str, Any], after_global: Mapping[str, Any], *,
                             exact_rollback: bool) -> int:
    """The root Review's required discovery slots (§31.26), from the PRE-CHANGE Global policy.

    ``max(2, before required_slots)`` for a strengthen, an ordinary adjust and
    an exact rollback; ``max(3, before required_slots)`` when the change
    lightens - decided from the before / after setting and the fixed strength
    order, never from the direction word. The proposed after-policy never
    lowers the strength of the Review authorizing it.
    """
    if type(exact_rollback) is not bool:
        raise _invalid("exact_rollback is a boolean")
    movement = movement_floor(before_global, after_global)  # exactly one setting of the exact next version
    floor = FLOOR_STRENGTHEN if exact_rollback else movement
    before = _settings(_require_global(before_global, "the before Global policy"))
    return max(SLOT_FLOOR[floor], before[policy.SURFACE_REQUIRED_SLOTS])


def candidate_material(packet: Mapping[str, Any], before_global: Mapping[str, Any], after_global: Mapping[str, Any],
                       proof: Mapping[str, Any]) -> dict[str, Any]:
    """The clone-safe Global Policy Change Candidate material (§31.24, RB7_FOUNDATION_INTERFACES §8.1).

    It reconstructs, without runtime memory: the exact Packet, the exact
    before Global policy, the exact after Global policy and its normalized
    projection, the compatibility proof, the root meta-policy identity, the
    required discovery slots and the exact expected Kp.
    """
    found = parse_promotion_packet(packet, "the Promotion Packet")
    before = _require_global(before_global, "the before Global policy")
    after = _require_global(after_global, "the after Global policy")
    if found["before_global_policy_digest"] != policy.global_policy_digest(before) \
            or found["after_global_policy"] != after:
        raise reconcile("the before / after Global policy is not the Packet's", REASON_CANDIDATE_MISMATCH)
    computed = compatibility_proof(before, after)
    if serialize.canonical_data(dict(proof)) != computed or found["compatibility_proof_digest"] != serialize.digest(computed):
        raise reconcile("the compatibility proof is not the Packet's", REASON_CANDIDATE_MISMATCH)
    material = {
        serialize.SCHEMA_KEY: SCHEMA_CANDIDATE, serialize.VERSION_KEY: RECORD_VERSION,
        "review_kind": REVIEW_KIND, "target_identity": TARGET_IDENTITY,
        "promotion_packet_id": found["promotion_packet_id"], "promotion_packet_digest": serialize.digest(found),
        "promotion_packet": found, "global_policy_change_id": found["global_policy_change_id"],
        "direction": found["direction"], "policy_surface_id": found["policy_surface_id"],
        "before_setting": found["before_setting"], "after_setting": found["after_setting"],
        "before_global_policy": before, "before_global_policy_digest": policy.global_policy_digest(before),
        "after_global_policy": after, "after_global_policy_digest": policy.global_policy_digest(after),
        "normalized_projection_hash": normalized_projection_hash(after),
        "compatibility_proof": computed, "compatibility_adapter_identity": ADAPTER_V1_IDENTITY,
        "compatibility_proof_digest": serialize.digest(computed),
        "root_meta_policy": root_meta_policy(),
        "required_discovery_slots": required_discovery_slots(
            before, after, exact_rollback=found["rollback_exception"] is not None),
        "expected_kp": expected_kp(found["global_policy_change_id"], after),
    }
    return parse_candidate_material(material, "the Global Policy Change Candidate")


def parse_candidate_material(record: object, described: str) -> dict[str, Any]:
    """Candidate material, strictly: every part re-derived from the exact Packet and Global policies it carries."""
    found = records._require_mapping(record, described)
    serialize.require_schema(found, SCHEMA_CANDIDATE, RECORD_VERSION, described)
    records._require_exact_fields(found, CANDIDATE_FIELDS, described)
    if (found["review_kind"], found["target_identity"]) != (REVIEW_KIND, TARGET_IDENTITY):
        raise _invalid(f"{described} is not a {REVIEW_KIND} Candidate of the {TARGET_IDENTITY} target")
    packet = parse_promotion_packet(found["promotion_packet"], f"{described} promotion_packet")
    before = _require_global(found["before_global_policy"], f"{described} before_global_policy")
    after = _require_global(found["after_global_policy"], f"{described} after_global_policy")
    expected = {
        "promotion_packet_id": packet["promotion_packet_id"], "promotion_packet_digest": serialize.digest(packet),
        "global_policy_change_id": packet["global_policy_change_id"], "direction": packet["direction"],
        "policy_surface_id": packet["policy_surface_id"], "before_setting": packet["before_setting"],
        "after_setting": packet["after_setting"], "before_global_policy_digest": policy.global_policy_digest(before),
        "after_global_policy_digest": policy.global_policy_digest(after),
        "normalized_projection_hash": normalized_projection_hash(after),
        "compatibility_adapter_identity": ADAPTER_V1_IDENTITY,
    }
    for key, value in expected.items():
        if found[key] != value:
            raise _invalid(f"{described} {key} is not its Packet's / Global policies'")
    if packet["before_global_policy_digest"] != expected["before_global_policy_digest"] \
            or packet["after_global_policy"] != after:
        raise _invalid(f"{described} Global policies are not its Packet's")
    if _settings(before)[packet["policy_surface_id"]] != packet["before_setting"]:
        raise _invalid(f"{described} before setting is not the before Global policy's")
    movement_floor(before, after)  # exactly one setting - the Packet's own surface - of the exact next version
    proof = records._require_mapping(found["compatibility_proof"], f"{described} compatibility_proof")
    try:
        total = compatibility_proof(before, after)
    except StopError as exc:
        raise _invalid(f"{described} compatibility is not total: {exc}") from exc
    if proof != total or found["compatibility_proof_digest"] != serialize.digest(total) \
            or packet["compatibility_proof_digest"] != serialize.digest(total):
        raise _invalid(f"{described} compatibility proof is not the total proof its Packet binds")
    meta = records._require_mapping(found["root_meta_policy"], f"{described} root_meta_policy")
    records._require_exact_fields(meta, ROOT_META_POLICY_FIELDS, f"{described} root_meta_policy")
    records._require_digest(meta, "root_policy_hash", f"{described} root_meta_policy")
    records._require_digest(meta, "meta_rules_digest", f"{described} root_meta_policy")
    slots = found["required_discovery_slots"]
    if slots != required_discovery_slots(before, after, exact_rollback=packet["rollback_exception"] is not None):
        raise _invalid(f"{described} required discovery slots are not the pre-change floor")
    if found["expected_kp"] != expected_kp(packet["global_policy_change_id"], after):
        raise _invalid(f"{described} expected Kp is not the exact three-path delta of its after policy")
    return serialize.canonical_data(found)


def candidate_hash(material: Mapping[str, Any]) -> str:
    return serialize.digest(dict(material))


def candidate_snapshot(material: Mapping[str, Any]) -> records.CandidateSnapshot:
    """The P1 CandidateSnapshot (snapshot mode) carrying the complete Candidate material."""
    found = parse_candidate_material(material, "the Global Policy Change Candidate")
    return records.CandidateSnapshot(
        candidate_hash=candidate_hash(found), reconstruction_mode=records.RECONSTRUCTION_SNAPSHOT,
        projection_semantics_version=PROJECTION_SEMANTICS_VERSION, material=found, builder=None,
    )


def review_context(before_global: Mapping[str, Any], *, loader_identity: str) -> dict[str, Any]:
    """The root Review Context (RB7_FOUNDATION_INTERFACES §8.4); its digest is every root Run's review_context_hash.

    It binds the kind, the contract, the root family policy and its static
    hash, the persisted-projection adapter, the loader / schema / meta-rules
    identities (§16.20) and the PRE-CHANGE Global policy the Review is held
    under - never the proposed after-state.
    """
    before = _require_global(before_global, "the before Global policy")
    if not _is_digest(loader_identity):
        raise _invalid("the loader identity is a SHA-256")
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_CONTEXT, serialize.VERSION_KEY: RECORD_VERSION,
        "review_kind": REVIEW_KIND, "contract": CONTRACT, "root_policy_id": POLICY_ID,
        "root_policy_hash": _root_policy_hash(), "persisted_adapter_identity": PERSISTED_ADAPTER_IDENTITY,
        "projection_semantics_version": PROJECTION_SEMANTICS_VERSION, "loader_identity": loader_identity,
        "loader_semantics_identity": policy.LOADER_SEMANTICS_IDENTITY, "meta_rules_id": policy.META_RULES_ID,
        "meta_rules_digest": policy.meta_rules_digest(),
        "before_global_policy_version": before["global_policy_version"],
        "before_global_policy_digest": policy.global_policy_digest(before),
        "namespace_root": namespace.ROOT_POLICY_REVIEW_NAMESPACE.root,
    })


def parse_review_context(record: object, described: str) -> dict[str, Any]:
    found = records._require_mapping(record, described)
    serialize.require_schema(found, SCHEMA_CONTEXT, RECORD_VERSION, described)
    records._require_exact_fields(found, CONTEXT_FIELDS, described)
    fixed = {"review_kind": REVIEW_KIND, "contract": CONTRACT, "root_policy_id": POLICY_ID,
             "root_policy_hash": _root_policy_hash(), "meta_rules_digest": policy.meta_rules_digest(),
             "persisted_adapter_identity": PERSISTED_ADAPTER_IDENTITY,
             "projection_semantics_version": PROJECTION_SEMANTICS_VERSION,
             "loader_semantics_identity": policy.LOADER_SEMANTICS_IDENTITY, "meta_rules_id": policy.META_RULES_ID,
             "namespace_root": namespace.ROOT_POLICY_REVIEW_NAMESPACE.root}
    for key, value in fixed.items():
        if found[key] != value:
            raise _invalid(f"{described} {key} is not the root Review's")
    for key in ("loader_identity", "before_global_policy_digest"):
        records._require_digest(found, key, described)
    records._require_int(found, "before_global_policy_version", described, minimum=1)
    return serialize.canonical_data(found)


def requirement(material: Mapping[str, Any]) -> dict[str, Any]:
    """The decided requirement a root Review is adjudicated against: the fixed root meta-rules and the exact
    pre-change Global policy, by identity (§31.25)."""
    found = parse_candidate_material(material, "the Global Policy Change Candidate")
    meta = found["root_meta_policy"]
    return p4.requirement_record(REVIEW_KIND, {
        "root_policy_hash": meta["root_policy_hash"], "meta_rules_digest": meta["meta_rules_digest"],
        "before_global_policy_digest": found["before_global_policy_digest"],
        "promotion_packet_digest": found["promotion_packet_digest"],
        "required_discovery_slots": found["required_discovery_slots"],
    })


def evidence_record(material: Mapping[str, Any]) -> dict[str, Any]:
    """The Evidence a root Run binds (its ``evidence_digest``): the Packet and each source snapshot, by digest."""
    found = parse_candidate_material(material, "the Global Policy Change Candidate")
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_EVIDENCE, serialize.VERSION_KEY: RECORD_VERSION,
        "promotion_packet_digest": found["promotion_packet_digest"],
        "source_snapshots": [{"source_id": item["source_id"], "digest": item["digest"]}
                             for item in found["promotion_packet"]["source_snapshots"]],
    })


# =========================================================================== the root Review over P4 (§31.25-§31.27, RB7C-1)

def reviewer_floor_problem(discovery: Sequence["p4.DiscoveryBinding"], adjudicator: "p4.ActorBinding",
                           required: int) -> str | None:
    """Why the bound reviewers do not meet the root Review's floor (§31.26), or ``None``.

    At least ``required`` discovery slots, every one bound to a distinct
    reviewer identity / version pair (all counted slots are distinct), and one
    separately bound adjudicator actor.
    """
    if type(required) is not int or required < SLOT_FLOOR[FLOOR_STRENGTHEN]:
        return f"a root Review requires at least {SLOT_FLOOR[FLOOR_STRENGTHEN]} discovery slots, not {required!r}"
    if not isinstance(discovery, (tuple, list)) or any(type(item) is not p4.DiscoveryBinding for item in discovery):
        return "discovery is a sequence of DiscoveryBinding"
    if type(adjudicator) is not p4.ActorBinding:
        return f"the adjudicator is one ActorBinding, not {type(adjudicator).__name__}"
    for binding in list(discovery) + [adjudicator]:
        if not callable(binding.actor):
            return "a bound reviewer actor is not callable"
        for name in ("identity", "version"):
            problem = _label_problem(getattr(binding, name))
            if problem is not None:
                return f"a bound reviewer {name} is not a public-safe label: {problem}"
    viewpoints = [binding.viewpoint for binding in discovery]
    try:
        for viewpoint in viewpoints:
            p4.discovery_slot(viewpoint)
    except ValidationError as exc:
        return str(exc)
    if len(set(viewpoints)) != len(viewpoints):
        return "two discovery slots share one viewpoint"
    pairs = [(binding.identity, binding.version) for binding in discovery]
    if len(set(pairs)) != len(pairs):
        return "two discovery slots bind one reviewer identity/version; every counted slot binds a distinct one"
    if len(discovery) < required:
        return (f"the root Review requires {required} discovery slot(s) bound to distinct reviewer identity/version "
                f"pairs, and the invocation binds {len(discovery)}")
    return None


def require_reviewer_floor(discovery: Sequence["p4.DiscoveryBinding"], adjudicator: "p4.ActorBinding",
                           required: int) -> None:
    problem = reviewer_floor_problem(discovery, adjudicator, required)
    if problem is not None:
        raise stop(CODE_REVIEWER_FLOOR_UNMET, f"{problem}; nothing is reserved or launched")


def discovery_request(*, material: Mapping[str, Any], context: Mapping[str, Any], viewpoint: str,
                      evidence_ids: Sequence[str] = ()) -> dict[str, Any]:
    """One root discovery request: the common P4 request under the root contract and the non-history root policy.

    Candidate generation 1, no succession, no set-aside Run, no Human decision;
    no history contract, prior history, set-aside summary, decision evidence or
    Effective Policy is bound (RB7C-1 (a)).
    """
    found = parse_candidate_material(material, "the Global Policy Change Candidate")
    context_record = parse_review_context(context, "the root Review Context")
    return p4.discovery_request(
        review_contract=CONTRACT, review_kind=REVIEW_KIND, viewpoint=viewpoint, candidate=found,
        context=context_record, requirement=requirement(found), candidate_generation=1, succession=None,
        set_aside_runs=(), human_decision=None, evidence_ids=evidence_ids, policy_id=POLICY_ID,
    )


def adjudication_request(*, review_run_id: str, candidate_hash: str, review_context_hash: str,
                         requirement: Mapping[str, Any], reports: Sequence[Mapping[str, Any]],
                         evidence_ids: Sequence[str]) -> dict[str, Any]:
    """The root adjudication request: the common P4 adjudication under the root policy, with no prior cycle."""
    return p4.adjudication_request(
        review_contract=CONTRACT, review_kind=REVIEW_KIND, review_run_id=review_run_id, candidate_hash=candidate_hash,
        candidate_generation=1, review_context_hash=review_context_hash, requirement=dict(requirement),
        reports=reports, prior=p4.NO_PRIOR, evidence_ids=evidence_ids, policy_id=POLICY_ID,
    )


# --------------------------------------------------------------------------- the mechanical root meta-verifier (§31.28)

#: The facts the owner gathers (Amendment 7: six keys). ``rollback_change`` / ``rollback_evaluation`` are the stored
#: change and evaluation records the exact-rollback exception names (canonical mappings read from committed objects),
#: both ``None`` when the exception is not used.
FACT_FIELDS = ("current_before_global_digest", "sources_current", "source_problems", "publication_ready",
               "rollback_change", "rollback_evaluation")


def _rollback_exception_problems(found: Mapping[str, Any], facts: Mapping[str, Any]) -> list[tuple[str, str]]:
    """§31.28 "rollback exception exactness when used", re-proven - never a label check alone (Amendment 7).

    Unused: both rollback facts are ``None``. Used: the Candidate is a rollback
    whose eligibility rests on the exception, the two facts are exactly the
    change and the evaluation the exception names, and
    :func:`exact_rollback_problem` holds over them, the request the Packet
    states and the before Global policy.
    """
    packet = found["promotion_packet"]
    exception = packet["rollback_exception"]
    change, evaluation = facts["rollback_change"], facts["rollback_evaluation"]
    if exception is None:
        if change is not None or evaluation is not None:
            return [(CODE_META_VERIFIER_FAILED, "rollback records are given for a Candidate that does not use the "
                                                "exact-rollback exception")]
        return []
    if found["direction"] != DIRECTION_ROLLBACK or packet["eligibility"]["basis"] != BASIS_EXACT_ROLLBACK:
        return [(CODE_ROLLBACK_INEXACT, "the exact-rollback exception is used by a Candidate that is not an exact "
                                        "rollback")]
    if not isinstance(change, Mapping) or not isinstance(evaluation, Mapping) \
            or change.get("global_policy_change_id") != exception["global_policy_change_id"] \
            or evaluation.get("evaluation_id") != exception["evaluation_id"]:
        return [(CODE_ROLLBACK_INEXACT, "the stored change and evaluation the exact-rollback exception names are not "
                                        "both given")]
    problem = exact_rollback_problem(_request_of_packet(packet), found["before_global_policy"], change, evaluation)
    if problem is not None:
        return [(CODE_ROLLBACK_INEXACT, f"the exact-rollback exception does not hold: {problem}")]
    return []


def meta_verifier_problems(material: Mapping[str, Any], facts: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Every failed item of the fixed mechanical root meta-verifier (§31.28), coded; external approval never overrides.

    ``facts`` (gathered by the owner, :data:`FACT_FIELDS`): the current
    before-Global digest, whether the bound source evidence is still current
    (and the problems when not), the root publication readiness (``None`` for
    a remote-less root), and the stored change / evaluation records an
    exact-rollback exception names (``None`` when unused; re-proven by
    :func:`exact_rollback_problem`). Every other item is re-derived from the Candidate material itself,
    against the fixed registry, the fixed meta-rules and this build's root
    meta-policy - never against the proposed after-state.
    """
    try:
        found = parse_candidate_material(material, "the Global Policy Change Candidate")
    except (StopError, ValidationError) as exc:
        return [(CODE_META_VERIFIER_FAILED, f"the Candidate material does not reconstruct: {exc}")]
    problems: list[tuple[str, str]] = []
    if not isinstance(facts, Mapping) or set(facts) != set(FACT_FIELDS):
        return [(CODE_META_VERIFIER_FAILED, f"the verification facts are not exactly {', '.join(FACT_FIELDS)}")]
    packet = found["promotion_packet"]
    before, after = found["before_global_policy"], found["after_global_policy"]
    surface_id = found["policy_surface_id"]
    # the affected surface is a registered adaptable surface, in its fixed range
    surface = policy.surface_problem(surface_id)
    if surface is not None:
        problems.append((CODE_SURFACE_REFUSED, surface[1]))
    elif not policy.SURFACE_BY_ID[surface_id].in_range(found["after_setting"]):
        problems.append((CODE_META_VERIFIER_FAILED, f"the proposed {surface_id} setting is outside its fixed range"))
    # the before Global policy still matches
    if facts["current_before_global_digest"] != found["before_global_policy_digest"]:
        problems.append((CODE_META_VERIFIER_FAILED, "the current Global policy is not the before Global policy the "
                                                    "Candidate was reviewed under"))
    # no fixed meta-rule changed; the root meta-policy is this build's
    if (before["fixed_meta_rules_identity"], after["fixed_meta_rules_identity"]) != (policy.META_RULES_ID,) * 2 \
            or (before["loader_semantics_identity"], after["loader_semantics_identity"]) \
            != (policy.LOADER_SEMANTICS_IDENTITY,) * 2:
        problems.append((CODE_META_VERIFIER_FAILED, "a fixed meta-rule or the loader semantics changed"))
    try:
        current_meta = root_meta_policy()
    except ValidationError as exc:
        current_meta = None
        problems.append((CODE_META_VERIFIER_FAILED, f"the root meta-policy of this build does not read ({exc})"))
    if current_meta is not None and found["root_meta_policy"] != current_meta:
        problems.append((CODE_META_VERIFIER_FAILED, "the root meta-policy the Candidate binds is not this build's"))
    # no correctness / authority surface changed: exactly one setting of the exact next version
    try:
        floor = movement_floor(before, after)
    except ValidationError as exc:
        floor = None
        problems.append((CODE_META_VERIFIER_FAILED, f"the after Global policy is not one change of the before: {exc}"))
    # source currency
    source_problems = facts["source_problems"]
    if not isinstance(source_problems, (list, tuple)):
        problems.append((CODE_META_VERIFIER_FAILED, "the source problems are not a list"))
    elif facts["sources_current"] is not True or source_problems:
        detail = "; ".join(str(item) for item in source_problems) or "not positively revalidated"
        problems.append((CODE_META_VERIFIER_FAILED, f"the bound source evidence is not current: {detail}"))
    # independence / cluster eligibility under the stronger lightening floor where it lightens
    exception = packet["rollback_exception"]
    if floor is not None:
        snapshots = [item["snapshot"] for item in packet["source_snapshots"]]
        recomputed = _eligibility(_request_of_packet(packet), snapshots, clustering(snapshots), floor,
                                  found["before_setting"])
        if recomputed != packet["eligibility"] or not recomputed["eligible"]:
            problems.append((CODE_NOT_ELIGIBLE, f"the {floor}-floor eligibility does not hold: "
                                                f"{', '.join(recomputed['problems']) or 'it is not the Packet result'}"))
        slots = required_discovery_slots(before, after, exact_rollback=exception is not None)
        if found["required_discovery_slots"] != slots:
            problems.append((CODE_META_VERIFIER_FAILED, "the required discovery slots are not the pre-change floor"))
    # rollback exception exactness when used (Amendment 7): re-proven over the stored change and evaluation records
    problems.extend(_rollback_exception_problems(found, facts))
    # total Profile compatibility
    try:
        proof = compatibility_proof(before, after)
    except StopError as exc:
        problems.append((CODE_COMPATIBILITY_UNPROVEN, str(exc)))
    else:
        if found["compatibility_proof"] != proof:
            problems.append((CODE_COMPATIBILITY_UNPROVEN, "the bound compatibility proof is not the total proof"))
    # observation / rollback feasibility
    unit = packet["rollback_contract"]["unit"]
    if unit["restore_setting"] != found["before_setting"] or not policy.SURFACE_BY_ID[surface_id].in_range(
            unit["restore_setting"]) or not policy.SURFACE_BY_ID[surface_id].measurement_channel:
        problems.append((CODE_META_VERIFIER_FAILED, "the change cannot be observed or rolled back exactly"))
    # persisted-projection adapter availability
    try:
        projection = normalized_projection_hash(after)
    except ValidationError as exc:
        problems.append((CODE_META_VERIFIER_FAILED, f"the persisted-projection adapter cannot read the after policy "
                                                    f"({exc})"))
    else:
        if projection != found["normalized_projection_hash"] \
                or found["expected_kp"]["normalized_projection_hash"] != projection:
            problems.append((CODE_META_VERIFIER_FAILED, "the persisted projection is not the Candidate's after-state"))
    # root publication readiness where required
    if facts["publication_ready"] is False:
        problems.append((CODE_META_VERIFIER_FAILED, "the root publication is not ready (authorization / destination)"))
    elif facts["publication_ready"] not in (True, None):
        problems.append((CODE_META_VERIFIER_FAILED, "publication readiness is true, false or none (remote-less)"))
    return problems


def require_meta_verifier(material: Mapping[str, Any], facts: Mapping[str, Any]) -> None:
    """STOP ``review_p7_meta_verifier_failed`` on any failed item - whatever any reviewer said (§31.28)."""
    problems = meta_verifier_problems(material, facts)
    if problems:
        code, message = problems[0]
        raise stop(CODE_META_VERIFIER_FAILED, f"the fixed root meta-verifier refuses the Candidate ({code}: {message})"
                                              + (f" and {len(problems) - 1} more" if len(problems) > 1 else "")
                                              + "; external reviewer approval never bypasses a mechanical item")


# --------------------------------------------------------------------------- G4 without P5 history (RB7C-1 (e), R8)

def _require_root_chain(chain: Any) -> None:
    first = chain.generations[0]
    if first.review_kind != REVIEW_KIND or first.target_identity != TARGET_IDENTITY:
        raise reconcile(f"Review Run {chain.review_run_id} is not a {REVIEW_KIND} Run of the {TARGET_IDENTITY} target",
                        REASON_CHAIN_INVALID)
    problems = p4.chain_problems(chain)
    if problems:
        raise reconcile(f"Review Run {chain.review_run_id} is not a P4 chain: " + "; ".join(problems),
                        REASON_CHAIN_INVALID)
    if p4.shape_of(chain) == p4.SHAPE_REPAIR or p4.repairs(CONTRACT):
        raise reconcile(f"Review Run {chain.review_run_id} takes a repair branch; the root contract has no Repair Batch",
                        REASON_CHAIN_INVALID)


def discovery_declined(chain: Any) -> bool:
    """Whether a discovery task of the Run settled as declined/failed: the Run is final and never authorizes."""
    return len(chain.generations) >= p4.DISCOVERY_SETTLE_GENERATION and any(
        task["status"] != records.TASK_SETTLED_OK for task in chain.generation(p4.DISCOVERY_SETTLE_GENERATION).settled_tasks)


def g4_outcome(chain: Any, adjudication_outcome: str | None) -> str:
    """The root Run's G4 outcome, read from its validated Gate chain alone (§31.27, RB7C-1 (e)).

    A declined discovery task is terminal ``not_authorized`` whatever the
    adjudication says (the verdict :func:`recovery_adapter` gives the same Run).
    ``REPAIR_REQUIRED`` under the non-repairing root contract is terminal
    ``not_authorized`` (no Receipt, no Repair Batch); ``HUMAN_WAIT`` is the
    canonical HUMAN_WAIT of the SAME Run, never set aside (R8); an
    authorization-ready G4 (or its G5 seal) is ``authorization_ready``. No P5
    history record is built: the root policy binds no history contract.
    """
    _require_root_chain(chain)
    state = p4.run_state(chain, adjudication_outcome)
    if state not in (p4.STATE_G4_REPAIR, p4.STATE_G4_HUMAN, p4.STATE_G4_READY, p4.STATE_G5_SEALED):
        raise reconcile(f"Review Run {chain.review_run_id} is at {state}, which has no G4 outcome",
                        REASON_CHAIN_INVALID)
    if discovery_declined(chain):
        return OUTCOME_NOT_AUTHORIZED  # the same verdict recovery gives the Run (recovery_adapter)
    if state == p4.STATE_G4_REPAIR:
        return OUTCOME_NOT_AUTHORIZED
    if state == p4.STATE_G4_HUMAN:
        return OUTCOME_HUMAN_WAIT
    return OUTCOME_AUTHORIZATION_READY


# --------------------------------------------------------------------------- root recovery classification (§31.29, RB7C-2)

SETTLED_CONSUMED = "consumed"
SETTLED_NOT_AUTHORIZED = "not_authorized"
SETTLED_INVALIDATED = "invalidated"


def _shape(chain: Any) -> str | None:
    problems = p4.chain_problems(chain)
    if problems:
        return "is not a P4 chain: " + "; ".join(problems)
    if p4.shape_of(chain) == p4.SHAPE_REPAIR:
        return "takes a repair branch the root contract does not have"
    return None


def recovery_adapter(*, promotion_packet_id: str | None, candidate_hash: str | None,
                     consumed: Callable[[str], bool]) -> "recovery.RecoveryAdapter":
    """The root kind's adapter over the ONE shared discovery core (``recovery.discover_kind_in``, RB7C-2).

    ``shape``     the P4 shape without a repair branch;
    ``named``     none: nothing is set aside automatically (no repair successor; a changed proposal is a new Packet);
    ``classify``  (the repository path first, under the root namespace):

    ```text
    not the root contract / kind / target            reconcile review_p7_chain_invalid
    Candidate does not reconstruct its Packet        reconcile review_p7_candidate_mismatch
    a Receipt of it consumed (``consumed``)          consumed
    G6 invalidation of its seal                      invalidated (the explicit supersession path)
    a declined discovery / G4 REPAIR_REQUIRED        not_authorized (terminal: no Receipt, no Repair Batch)
    another Packet / Candidate than the bound one    reconcile review_p7_candidate_mismatch (never two in flight)
    G4 HUMAN_WAIT                                     recoverable: the SAME Run, waiting (R8)
    otherwise                                         recoverable (a stale basis is re-proven by the owner)
    ```

    ``promotion_packet_id`` / ``candidate_hash`` are the Packet and Candidate
    the caller binds; ``None`` (both) when it binds none yet - after runtime
    loss, discovery itself finds the Run, whose own Packet / Candidate
    identity is still proven. ``consumed(receipt_id)`` answers whether a
    Global Policy Consumption of that Receipt is stored. Never newest or
    timestamp selection: several recoverable Runs are the core's
    ``review_recovery_ambiguous``.
    """
    from . import recovery

    if (promotion_packet_id is None) != (candidate_hash is None):
        raise _invalid("the bound Packet and Candidate are named together, or neither is")
    if promotion_packet_id is not None and (not _is_id(promotion_packet_id, "review_promotion_packet")
                                            or not _is_digest(candidate_hash)):
        raise _invalid("the bound Packet is a review_promotion_packet id and the Candidate a SHA-256")
    if not callable(consumed):
        raise _invalid("consumed is a callable over Receipt ids")

    def classify(repo: Any, review: Any, head: Any, found: Any, named_aside: Any, currency: Any) -> str | None:
        chain = found.chain
        run_id = found.review_run_id
        first = chain.generations[0]
        if found.contract != CONTRACT or first.review_kind != REVIEW_KIND or first.target_identity != TARGET_IDENTITY:
            raise reconcile(f"Review Run {run_id} of the {REVIEW_KIND} kind binds contract {found.contract} / target "
                            f"{first.target_identity}", REASON_CHAIN_INVALID)
        try:
            material = parse_candidate_material(found.material, f"the Candidate of Review Run {run_id}")
        except (StopError, ValidationError) as exc:
            raise reconcile(f"the Candidate of Review Run {run_id} does not reconstruct its Packet: {exc}",
                            REASON_CANDIDATE_MISMATCH) from exc
        if candidate_hash_of(material) != first.candidate_hash:
            raise reconcile(f"Review Run {run_id}'s Candidate material is not the Candidate its generation 1 names",
                            REASON_CANDIDATE_MISMATCH)
        receipts = [str(generation.receipt_id) for generation in chain.generations if generation.receipt_id]
        if any(consumed(receipt_id) for receipt_id in receipts):
            return SETTLED_CONSUMED
        latest = chain.latest
        if latest.generation == p4.INVALIDATION_GENERATION and p4.shape_of(chain) == p4.SHAPE_SEAL:
            return SETTLED_INVALIDATED
        if discovery_declined(chain):
            return SETTLED_NOT_AUTHORIZED
        if latest.generation == p4.ADJUDICATION_SETTLE_GENERATION:
            try:
                outcome = review.read_adjudication(run_id).outcome
            except ValidationError as exc:
                raise reconcile(f"the adjudication of Review Run {run_id} does not read: {exc}",
                                REASON_CHAIN_INVALID) from exc
            if g4_outcome(chain, outcome) == OUTCOME_NOT_AUTHORIZED:
                return SETTLED_NOT_AUTHORIZED
        if promotion_packet_id is not None and (material["promotion_packet_id"], first.candidate_hash) \
                != (promotion_packet_id, candidate_hash):
            raise reconcile(f"Review Run {run_id} reviews another Promotion Packet / Candidate of this operation; two "
                            "Candidates are never in flight for one request", REASON_CANDIDATE_MISMATCH)
        return None

    return recovery.RecoveryAdapter(shape=_shape, named=lambda review, found: [], classify=classify)


def candidate_hash_of(material: Mapping[str, Any]) -> str:
    """The Candidate hash of validated material (:func:`candidate_hash` of the canonical material)."""
    return candidate_hash(serialize.canonical_data(dict(material)))


# =========================================================================== persistence records (§31.33-§31.37)

CHANGE_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "global_policy_change_id", "promotion_packet_id",
    "promotion_packet_digest", "candidate_hash", "review_run_id", "receipt_id", "before_global_policy_version",
    "before_global_policy_digest", "after_global_policy_version", "after_global_policy_digest", "policy_surface_id",
    "before_setting", "after_setting", "direction", "generalized_mechanism_id", "compatibility_adapter_identity",
    "compatibility_proof_digest", "expected_effect", "measurement_contract", "rollback_contract", "summary",
)


def change_record(material: Mapping[str, Any], *, review_run_id: str, receipt_id: str) -> dict[str, Any]:
    """The immutable Global change record of an authorized Candidate (§31.33), built from it exactly.

    It binds the Packet, the Candidate, the Review Run and Receipt, the exact
    before / after Global identities, the surface and settings, the
    generalized mechanism, the compatibility adapter and proof, the expected
    effect, the measurement contract and the rollback contract. It never
    guesses its own commit SHA.
    """
    found = parse_candidate_material(material, "the Global Policy Change Candidate")
    packet = found["promotion_packet"]
    record = {
        serialize.SCHEMA_KEY: SCHEMA_CHANGE, serialize.VERSION_KEY: RECORD_VERSION,
        "global_policy_change_id": found["global_policy_change_id"],
        "promotion_packet_id": found["promotion_packet_id"],
        "promotion_packet_digest": found["promotion_packet_digest"], "candidate_hash": candidate_hash(found),
        "review_run_id": review_run_id, "receipt_id": receipt_id,
        "before_global_policy_version": found["before_global_policy"]["global_policy_version"],
        "before_global_policy_digest": found["before_global_policy_digest"],
        "after_global_policy_version": found["after_global_policy"]["global_policy_version"],
        "after_global_policy_digest": found["after_global_policy_digest"],
        "policy_surface_id": found["policy_surface_id"], "before_setting": found["before_setting"],
        "after_setting": found["after_setting"], "direction": found["direction"],
        "generalized_mechanism_id": packet["generalized_mechanism_id"],
        "compatibility_adapter_identity": found["compatibility_adapter_identity"],
        "compatibility_proof_digest": found["compatibility_proof_digest"],
        "expected_effect": packet["expected_effect"], "measurement_contract": dict(packet["measurement_contract"]),
        "rollback_contract": dict(packet["rollback_contract"]), "summary": packet["summary"],
    }
    return parse_change_record(record, "the Global change record")


def parse_change_record(record: object, described: str) -> dict[str, Any]:
    """A stored Global change record, strictly (schema, fields, identities, one change of one surface, H-3 text)."""
    found = records._require_mapping(record, described)
    serialize.require_schema(found, SCHEMA_CHANGE, RECORD_VERSION, described)
    records._require_exact_fields(found, CHANGE_FIELDS, described)
    records._require_id(found, "global_policy_change_id", "review_global_policy_change", described)
    records._require_id(found, "promotion_packet_id", "review_promotion_packet", described)
    records._require_id(found, "review_run_id", "review_run", described)
    records._require_id(found, "receipt_id", "review_receipt", described)
    for key in ("promotion_packet_digest", "candidate_hash", "before_global_policy_digest",
                "after_global_policy_digest", "compatibility_proof_digest"):
        records._require_digest(found, key, described)
    before_version = records._require_int(found, "before_global_policy_version", described, minimum=1)
    if records._require_int(found, "after_global_policy_version", described, minimum=2) != before_version + 1:
        raise _invalid(f"{described} is not exactly one Global policy version")
    surface = policy.SURFACE_BY_ID.get(found["policy_surface_id"]) if isinstance(found["policy_surface_id"], str) \
        else None
    if surface is None or not surface.in_range(found["before_setting"]) or not surface.in_range(found["after_setting"]) \
            or found["before_setting"] == found["after_setting"]:
        raise _invalid(f"{described} is not one change of one registered surface inside its range")
    if found["direction"] not in DIRECTIONS:
        raise _invalid(f"{described} direction is not a Global change direction")
    if not isinstance(found["generalized_mechanism_id"], str) \
            or _MECHANISM_ID.match(found["generalized_mechanism_id"]) is None:
        raise _invalid(f"{described} names no generalized mechanism identity")
    if found["compatibility_adapter_identity"] != ADAPTER_V1_IDENTITY:
        raise _invalid(f"{described} does not bind the total adapter v1")
    for key in ("expected_effect", "summary"):
        problem = _text_problem(found[key])
        if problem is not None:
            raise _invalid(f"{described} {key} is not public-safe text: {problem}")
    problem = _measurement_problem(found["measurement_contract"], f"{described} measurement_contract")
    if problem is not None:
        raise _invalid(problem)
    rollback = records._require_mapping(found["rollback_contract"], f"{described} rollback_contract")
    records._require_exact_fields(rollback, ROLLBACK_CONTRACT_FIELDS, f"{described} rollback_contract")
    if _text_problem(rollback["threshold"]) is not None or rollback["unit"] != {
            "policy_surface_id": found["policy_surface_id"], "restore_setting": found["before_setting"],
            "restore_global_policy_digest": found["before_global_policy_digest"]}:
        raise _invalid(f"{described} rollback contract does not restore exactly the before setting")
    return serialize.canonical_data(found)


def patch_note_bytes(change: Mapping[str, Any]) -> bytes:
    """The deterministic Patch Note of a change record (§31.34, §16.22): UTF-8, LF, from sanitized fields only.

    It explains the affected surface, the before / after setting, the
    direction, the generalized evidence basis, the expected effect, the
    observation contract and the rollback condition. It names no Project
    path, transcript, secret or private source detail, and it is explanation
    only: ``review-policy/global-policy.yaml`` is the policy authority.
    """
    found = parse_change_record(change, "the Global change record")
    measurement = found["measurement_contract"]
    rollback = found["rollback_contract"]
    stronger = "lighter" if _lightens(found["before_setting"], found["after_setting"]) else "stronger"
    lines = [
        f"# Global Policy Change {found['global_policy_change_id']}",
        "",
        f"{found['summary']}",
        "",
        f"- Surface: `{found['policy_surface_id']}`",
        f"- Setting: {found['before_setting']} -> {found['after_setting']} ({found['direction']}; Global behaviour "
        f"becomes {stronger})",
        f"- Global policy: version {found['before_global_policy_version']} ({found['before_global_policy_digest']}) "
        f"-> version {found['after_global_policy_version']} ({found['after_global_policy_digest']})",
        f"- Generalized mechanism: `{found['generalized_mechanism_id']}`",
        f"- Evidence basis: Promotion Packet {found['promotion_packet_id']} ({found['promotion_packet_digest']}), "
        f"reviewed by Review Run {found['review_run_id']}, authorized by Receipt {found['receipt_id']}",
        f"- Expected effect: {found['expected_effect']}",
        f"- Observation: {measurement['metric']} (measurement contract {measurement['version']}); success: "
        f"{measurement['success_criteria']}; at least {measurement['minimum_opportunities']} relevant opportunities in "
        f"at least {measurement['minimum_clusters']} independent clusters",
        f"- Rollback condition: {rollback['threshold']}; restores `{found['policy_surface_id']}` to "
        f"{rollback['unit']['restore_setting']} as a new Global policy version",
        f"- Compatibility: {found['compatibility_adapter_identity']} ({found['compatibility_proof_digest']})",
        "",
        f"This Patch Note is explanation only; {namespace.ROOT_POLICY_LAYOUT.global_policy_rel} is the policy authority.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def persisted_global_policy(material: Mapping[str, Any], *, global_policy_change_id: str, policy_commit: str,
                            policy_parent: str, branch: str, policy_delta_digest: str,
                            loader_identity: str) -> dict[str, Any]:
    """The ``persisted_global_policy`` mapping Global Policy Consumption v4 binds (§31.37, §8.6)."""
    found = parse_candidate_material(material, "the Global Policy Change Candidate")
    if global_policy_change_id != found["global_policy_change_id"]:
        raise reconcile("the persisted change is not the Candidate's", REASON_CANDIDATE_MISMATCH)
    if not _is_commit(policy_commit) or not _is_commit(policy_parent) or policy_commit == policy_parent:
        raise _invalid("the policy commit Kp and its parent are two full commit ids")
    if not isinstance(branch, str) or records._FULL_BRANCH.fullmatch(branch) is None:
        raise _invalid(f"the branch is not a full branch ref: {branch!r}")
    if not _is_digest(policy_delta_digest) or not _is_digest(loader_identity):
        raise _invalid("the policy delta digest and the loader identity are SHA-256 digests")
    return serialize.canonical_data({
        "contract": records.PERSISTED_GLOBAL_POLICY_CONTRACT,
        "global_policy_change_id": global_policy_change_id,
        "promotion_packet_id": found["promotion_packet_id"],
        "promotion_packet_digest": found["promotion_packet_digest"],
        "before_global_policy_version": found["before_global_policy"]["global_policy_version"],
        "before_global_policy_digest": found["before_global_policy_digest"],
        "after_global_policy_version": found["after_global_policy"]["global_policy_version"],
        "after_global_policy_digest": found["after_global_policy_digest"],
        "normalized_projection_hash": found["normalized_projection_hash"],
        "policy_commit": policy_commit, "policy_parent": policy_parent, "branch": branch,
        "policy_delta_digest": policy_delta_digest,
        "compatibility_adapter_identity": found["compatibility_adapter_identity"],
        "compatibility_adapter_digest": found["compatibility_proof_digest"],
        "loader_identity": loader_identity,
    })


# =========================================================================== Global observation / evaluation (§31.41-§31.43)

EVALUATION_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "evaluation_id", "global_policy_change_id",
    "evaluated_global_policy_version", "evaluated_global_policy_digest", "measurement_contract_digest",
    "source_snapshots", "clusters", "environment", "result", "rationale", "next_action",
)


def _material_environment_change(environment: Mapping[str, Any]) -> list[str]:
    start, end = environment["window_start"], environment["window_end"]
    return [name for name in ENVIRONMENT_FIELDS if start[name] != end[name]]


def _observed_under(snapshots: Sequence[Mapping[str, Any]], change: Mapping[str, Any]) -> dict[str, list[str]]:
    """Per source, the Relevant Opportunities of the change's surface whose Run froze the change as an active
    Global experiment - positive proof the Run was observed under it; chronology is never causality (§31.43)."""
    surface_id, change_id = change["policy_surface_id"], change["global_policy_change_id"]
    return {snapshot["source_id"]: [entry["review_run_id"] for entry in snapshot["opportunities"][surface_id]
                                    if change_id in entry["global_changes"]]
            for snapshot in snapshots}


def _next_action(result: str, change: Mapping[str, Any]) -> str:
    if result == RESULT_RETAIN:
        return policy.NEXT_END_OBSERVATION
    if result == RESULT_INCONCLUSIVE and change["measurement_contract"]["continued_observation_permitted"]:
        return policy.NEXT_CONTINUE_OBSERVATION
    return policy.NEXT_NEW_CANDIDATE


def _observation_problem(result: str, change: Mapping[str, Any], snapshots: Sequence[Mapping[str, Any]],
                         computed: Mapping[str, Any]) -> str | None:
    observed = _observed_under(snapshots, change)
    total = sum(len(items) for items in observed.values())
    if result in (RESULT_ADJUST, RESULT_ROLLBACK) and total < 1:
        return (f"a {result} rests on at least one relevant opportunity observed under "
                f"{change['global_policy_change_id']}; chronology alone is never causal evidence")
    if result == RESULT_RETAIN:
        clusters = [cluster["sources"] for cluster in computed["clusters"]
                    if any(observed[member] for member in cluster["sources"])]
        independent = _independent_clusters(clusters, computed["matrix"])
        measurement = change["measurement_contract"]
        if total < measurement["minimum_opportunities"] or len(independent) < measurement["minimum_clusters"]:
            return (f"retain ends observation only after the frozen minimum: {measurement['minimum_opportunities']} "
                    f"relevant opportunities observed under the change in {measurement['minimum_clusters']} mutually "
                    f"independent clusters; the evidence proves {total} in {len(independent)} (correlated Projects "
                    "are one confirmation)")
    return None


def evaluation_record(request: Mapping[str, Any], *, evaluation_id: str, change: Mapping[str, Any],
                      evaluated_global: Mapping[str, Any], snapshots: Sequence[Mapping[str, Any]],
                      clusters: Mapping[str, Any]) -> dict[str, Any]:
    """The immutable Global evaluation record (§31.41, §8.5); ``review_p7_evaluation_invalid`` otherwise.

    The evaluated Global must be one the change is in force in. Post-change
    evidence uses the same independence model: only opportunities observed
    under the change count, and correlated Projects are one cluster. A
    material environment change during the observation window needs a window
    split or a positive irrelevance proof (an evidence record, by digest), or
    the result is inconclusive. ``next_action``: retain ends observation,
    adjust and rollback need a new Candidate, inconclusive is never success.
    It writes no policy.
    """
    problems = evaluation_request_problems(request)
    if problems:
        raise stop(CODE_EVALUATION_INVALID, "invalid Global Policy evaluation request: " + "; ".join(problems))
    record = _canonical(request)
    if not _is_id(evaluation_id, "review_global_policy_evaluation"):
        raise stop(CODE_EVALUATION_INVALID, "an evaluation is named by a review_global_policy_evaluation id")
    try:
        found_change = parse_change_record(change, "the evaluated Global change")
        evaluated = _require_global(evaluated_global, "the evaluated Global policy")
        parsed = _require_snapshots(snapshots)
    except ValidationError as exc:
        raise stop(CODE_EVALUATION_INVALID, f"the evaluation inputs do not read: {exc}") from exc
    change_id = found_change["global_policy_change_id"]
    if record["global_policy_change_id"] != change_id:
        raise stop(CODE_EVALUATION_INVALID, f"the request evaluates {record['global_policy_change_id']}, not {change_id}")
    surface_id = found_change["policy_surface_id"]
    if evaluated["global_policy_version"] < found_change["after_global_policy_version"] \
            or _settings(evaluated)[surface_id] != found_change["after_setting"]:
        raise stop(CODE_EVALUATION_INVALID, f"{change_id} is not in force in the evaluated Global policy version "
                                            f"{evaluated['global_policy_version']}")
    by_id = {item["source_id"]: item for item in parsed}
    if sorted(by_id) != list(record["sources"]) or any(
            _record_refs_of(record["evidence"][source_id]) != by_id[source_id]["records"]
            or {key: value for key, value in _provenance_of(record["evidence"][source_id]).items() if key != "kind"}
            != by_id[source_id]["provenance"] for source_id in by_id):
        raise stop(CODE_EVALUATION_INVALID, "the source snapshots are not of exactly the evidence the request names")
    computed = clustering(parsed)
    if not isinstance(clusters, Mapping) or serialize.canonical_data(dict(clusters)) != computed:
        raise stop(CODE_EVALUATION_INVALID, "the clusters are not the clustering of these source snapshots")
    result = record["result"]
    changed = _material_environment_change(record["environment"])
    if changed and record["environment"]["basis"] is None and result != RESULT_INCONCLUSIVE:
        raise stop(CODE_EVALUATION_INVALID, f"the material environment changed during the observation window "
                                            f"({', '.join(changed)}); without a window split or a positive irrelevance "
                                            "proof the result is inconclusive")
    problem = _observation_problem(result, found_change, parsed, computed)
    if problem is not None:
        raise stop(CODE_EVALUATION_INVALID, problem)
    evaluation = {
        serialize.SCHEMA_KEY: SCHEMA_EVALUATION, serialize.VERSION_KEY: RECORD_VERSION,
        "evaluation_id": evaluation_id, "global_policy_change_id": change_id,
        "evaluated_global_policy_version": evaluated["global_policy_version"],
        "evaluated_global_policy_digest": policy.global_policy_digest(evaluated),
        "measurement_contract_digest": serialize.digest(dict(found_change["measurement_contract"])),
        "source_snapshots": [{"source_id": item["source_id"], "digest": serialize.digest(item), "snapshot": item}
                             for item in parsed],
        "clusters": computed, "environment": dict(record["environment"]), "result": result,
        "rationale": record["rationale"], "next_action": _next_action(result, found_change),
    }
    return parse_evaluation_record(evaluation, "the Global evaluation record")


def parse_evaluation_record(record: object, described: str) -> dict[str, Any]:
    """A stored Global evaluation record, strictly (§8.5)."""
    found = records._require_mapping(record, described)
    serialize.require_schema(found, SCHEMA_EVALUATION, RECORD_VERSION, described)
    records._require_exact_fields(found, EVALUATION_FIELDS, described)
    records._require_id(found, "evaluation_id", "review_global_policy_evaluation", described)
    records._require_id(found, "global_policy_change_id", "review_global_policy_change", described)
    records._require_int(found, "evaluated_global_policy_version", described, minimum=2)
    records._require_digest(found, "evaluated_global_policy_digest", described)
    records._require_digest(found, "measurement_contract_digest", described)
    snapshots = []
    for item in records._require_list(found, "source_snapshots", described):
        entry = records._require_mapping(item, f"{described} source snapshot")
        records._require_exact_fields(entry, ("source_id", "digest", "snapshot"), f"{described} source snapshot")
        snapshot = parse_source_snapshot(entry["snapshot"], f"{described} source snapshot")
        if entry["source_id"] != snapshot["source_id"] or entry["digest"] != serialize.digest(snapshot):
            raise _invalid(f"{described} source snapshot is not named by its own source and digest")
        snapshots.append(snapshot)
    if [item["source_id"] for item in snapshots] != sorted({item["source_id"] for item in snapshots}):
        raise _invalid(f"{described} source snapshots are not sorted and duplicate-free")
    if found["clusters"] != clustering(snapshots):
        raise _invalid(f"{described} clusters are not its snapshots' clustering")
    problem = _evaluation_environment_problem(found["environment"])
    if problem is not None:
        raise _invalid(f"{described} {problem}")
    result, next_action = found["result"], found["next_action"]
    if result not in EVALUATION_RESULTS or next_action not in policy.NEXT_ACTIONS:
        raise _invalid(f"{described} result or next action is not in the fixed vocabulary")
    if (result == RESULT_RETAIN) != (next_action == policy.NEXT_END_OBSERVATION):
        raise _invalid(f"{described}: only retain ends an observation")
    if result in (RESULT_ADJUST, RESULT_ROLLBACK) and next_action != policy.NEXT_NEW_CANDIDATE:
        raise _invalid(f"{described}: adjust and rollback need a new reviewed Candidate")
    if _material_environment_change(found["environment"]) and found["environment"]["basis"] is None \
            and result != RESULT_INCONCLUSIVE:
        raise _invalid(f"{described}: a material environment change without a basis is inconclusive")
    if found["environment"]["basis_digest"] is not None and found["environment"]["basis_digest"] not in {
            ref["digest"] for snapshot in snapshots for ref in snapshot["records"]}:
        raise _invalid(f"{described} environment basis is not one of its evidence records")
    problem = _text_problem(found["rationale"])
    if problem is not None:
        raise _invalid(f"{described} rationale is not public-safe text: {problem}")
    return serialize.canonical_data(found)


# --------------------------------------------------------------------------- Global-origin experiments (§16.10, FC-RB7-6)

def active_global_experiments(changes: Sequence[Mapping[str, Any]], evaluations: Sequence[Mapping[str, Any]],
                              current_global: Mapping[str, Any]) -> tuple["policy.ActiveExperiment", ...]:
    """The Global-origin experiments the next Run boundary freezes beside the Project's (``origin = global``).

    The lineage of the current Global policy is followed back through the
    change records by exact digest (never "newest"): each surface's latest
    change in it is an active experiment until a retain evaluation of it ends
    observation; an earlier change on the same surface is superseded by the
    later one. A lightening freezes its pre-change stronger setting as the
    independent holdout (§16.10). A Global version above 1 that no stored
    change produced, or two changes of one version, is refused.
    """
    current = _require_global(current_global, "the current Global policy")
    parsed_changes = [parse_change_record(item, "a Global change record") for item in changes]
    parsed_evaluations = [parse_evaluation_record(item, "a Global evaluation record") for item in evaluations]
    by_after: dict[str, dict[str, Any]] = {}
    for change in parsed_changes:
        if change["after_global_policy_digest"] in by_after:
            raise _invalid(f"two Global changes produce Global policy {change['after_global_policy_digest']}")
        by_after[change["after_global_policy_digest"]] = change
    lineage: list[dict[str, Any]] = []
    digest, version = policy.global_policy_digest(current), current["global_policy_version"]
    while version > 1:
        change = by_after.get(digest)
        if change is None or change["after_global_policy_version"] != version:
            raise _invalid(f"Global policy version {version} was produced by no stored Global change")
        lineage.append(change)
        digest, version = change["before_global_policy_digest"], change["before_global_policy_version"]
    ended = {item["global_policy_change_id"] for item in parsed_evaluations
             if item["next_action"] == policy.NEXT_END_OBSERVATION}
    found: list[policy.ActiveExperiment] = []
    seen: set[str] = set()
    for change in lineage:  # newest first along the exact-digest lineage
        surface_id = change["policy_surface_id"]
        if surface_id in seen:
            continue
        seen.add(surface_id)
        if change["global_policy_change_id"] in ended:
            continue
        found.append(policy.ActiveExperiment(
            policy_change_id=change["global_policy_change_id"], policy_surface_id=surface_id,
            direction=change["direction"],
            holdout_setting=change["before_setting"] if _lightens(change["before_setting"], change["after_setting"])
            else None,
            origin=policy.ORIGIN_GLOBAL,
        ))
    return tuple(sorted(found, key=lambda item: (item.policy_surface_id, item.origin, item.policy_change_id)))
