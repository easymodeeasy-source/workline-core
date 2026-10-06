"""P6 (``WORKLINE_COMPLETION_SPRINT`` §15 / §30): Project-local Adaptive Review Policy - the semantic core.

Inert, as :mod:`workline.review.p4` and :mod:`workline.review.history` are: no
Project lock, no mutation, no Git and no lifecycle. It reads - the configured
Workline root's runtime authority, and canonical Review records through any
Review reader - and it decides nothing that progresses anything. The one owner
that writes what this module defines is :mod:`workline.project_policy`
(``project-policy-change``), through the ordinary Mutation Controller.

```text
surfaces      the fixed two-surface v1 registry; nothing learned adds a third (§30.2, §30.3)
baseline      the canonical read-only GlobalPolicyBaseline loader, source_mode derived-baseline (§15.9, §30.4)
profile       the strict canonical Project Profile, its lineage and its compatibility (§15.12, §30.5, §30.7)
effective     the normalized Effective Policy a new P6-capable Run freezes (§15.13, §30.6)
candidate     the normalized PolicyChangeCandidate and the fixed mechanical meta-verifier (§15.14-§15.19, §30.8-§30.10)
records       the immutable change and evaluation records (§30.19, §30.23)
learning      evaluation, active experiments, overlap and environment attribution (§15.24-§15.26, §30.23-§30.25)
review kind   the Policy Review adapter identities: project-policy-change-v1 (§30.12-§30.14)
consumption   the persisted-policy projection Consumption v3 binds (§30.21-§30.22)
```

Project learning may change how Workline verifies correctness, never what
correctness means: everything outside the two registered surfaces is outside
the adaptive registry, and a Profile can neither reclassify a surface nor invent
one. The Profile is canonical by explicit Workline ownership - exact path,
schema and loader - and is therefore never shadow authority (§15.27).
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from ..errors import ReconcileRequired, StopError, ValidationError
from ..ids import is_valid_id
from . import history, paths, records, serialize

# --------------------------------------------------------------------------- identities (§30.4, §30.12, §30.16)

#: The P6-capable Effective Policy family identity (R6-1): every NEW first Run of a P4-capable Formal Review binds
#: it, with or without a Project Profile. A cycle keeps the policy of its first Run; an existing Run is read only
#: from its own stored identity - never upgraded by file presence, current code or shape.
P6_POLICY_ID = "review-v1-p6-policy-v1"
#: The request-envelope key under which a P6-capable Run binds its frozen normalized Effective Policy.
EFFECTIVE_POLICY_KEY = "effective_policy"
#: The request-envelope key a P6 discovery request carries: whether the task is a required slot or a holdout.
DISCOVERY_ROLE_KEY = "discovery_role"
ROLE_REQUIRED = "required"
ROLE_HOLDOUT = "holdout"
DISCOVERY_ROLES = (ROLE_REQUIRED, ROLE_HOLDOUT)

#: The Policy Review kind (§30.12).
REVIEW_KIND = "project-policy-change-v1"
TARGET_IDENTITY = "project-policy"
AUTHORIZED_OPERATION_STAGE = "project-policy-change:persist-profile"
#: The Policy Review contract: a member of the P4-capable contract family (P4 discovery / adjudication / G1-G5),
#: with no Repair Batch branch.
POLICY_CHANGE_CONTRACT = records.P6_POLICY_CHANGE_CONTRACT
#: The internal operation owner of every physical write under ``.workline/review/policy/`` (§30.15).
OWNER = "project-policy-change"
OPERATION = "project-policy-change"
OPERATION_EVALUATION = "project-policy-evaluation"

BASELINE_CONTRACT = "review-v1-p6-global-baseline-v1"
#: The Global POLICY version of the derived baseline (FC-RB7-3): it counts Global policy changes - derived is 1,
#: and RB7 increments it by one per Global change. Schema evolution goes through the record version / contract.
BASELINE_VERSION = 1
SOURCE_MODE_DERIVED = "derived-baseline"
#: The closed sets a stored Effective Policy's baseline identity is read against (FC-RB7-2 b): RB7 extends these
#: tables when it materializes Global policy, and every stored P6 Run envelope keeps reading.
SOURCE_MODES = (SOURCE_MODE_DERIVED,)
BASELINE_VERSIONS = (BASELINE_VERSION,)
#: R6-2 / FC-RB7-5: the compatibility interpretation an Effective Policy binds. Before RB7: exact equality of the
#: policy-semantic projection of the baseline a Profile was written under (recovered from its change record) and of
#: the current one. RB7 adds its versioned total adapter here, without an Effective Policy schema v2.
COMPATIBILITY_EXACT_DERIVED_SEMANTIC = "review-v1-p6-exact-derived-semantic-v1"
COMPATIBILITY_INTERPRETATIONS = (COMPATIBILITY_EXACT_DERIVED_SEMANTIC,)
#: FC-RB7-6: who an active experiment comes from, and the identity kind it is named by. Only Project-origin
#: experiments (an applied Project Policy Change) exist before RB7; RB7 adds a Global origin here.
ORIGIN_PROJECT = "project"
EXPERIMENT_ORIGINS: Mapping[str, str] = {ORIGIN_PROJECT: "review_policy_change"}
#: The loader / schema / default-semantics identity a Profile and the baseline bind (§15.9, §30.5).
LOADER_SEMANTICS_IDENTITY = "review-v1-p6-policy-loader-v1"
META_RULES_ID = "review-v1-p6-meta-rules-v1"
ADAPTER_IDENTITY = "project-policy-adapter-v1"
PROJECTION_SEMANTICS_VERSION = "review-v1-p6-policy-projection-v1"
PERSISTED_POLICY_CONTRACT = "review-v1-p6-persisted-policy-v1"
POLICY_PUBLICATION_CONTRACT = "review-v1-p6-policy-publication-v1"
DISCOVERY_INSTRUCTION_NOTE = "a Policy Review discovery reviews normalized policy semantics, never an imperative patch"

SCHEMA_BASELINE = "review-p6-global-baseline"
SCHEMA_META_RULES = "review-p6-meta-rules"
SCHEMA_PROFILE = "review-p6-project-profile"
SCHEMA_EFFECTIVE = "review-p6-effective-policy"
SCHEMA_REQUEST = "review-p6-policy-change-request"
SCHEMA_CANDIDATE = "review-p6-policy-change-candidate"
SCHEMA_CHANGE = "review-p6-policy-change"
SCHEMA_EVALUATION_REQUEST = "review-p6-policy-evaluation-request"
SCHEMA_EVALUATION = "review-p6-policy-evaluation"
SCHEMA_CONTEXT = "review-p6-policy-context"
SCHEMA_EVIDENCE = "review-p6-policy-evidence"
RECORD_VERSION = 1

#: The Workline-root authorities the derived baseline binds (§30.4): registry.md and the review / roadmap / start
#: Skills, each as the SHA-256 of its bytes with CRLF read as LF.
BASELINE_AUTHORITY_IDS = ("registry", "skills/review", "skills/roadmap", "skills/start")

# --------------------------------------------------------------------------- the P6 catalogue

CODE_SURFACE_UNKNOWN = "review_p6_surface_unknown"
CODE_SURFACE_NON_ADAPTIVE = "review_p6_surface_non_adaptive"
CODE_SETTING_INVALID = "review_p6_setting_invalid"
CODE_RECLASSIFIED = "review_p6_surface_reclassified"
CODE_PROFILE_INVALID = "review_p6_profile_invalid"
CODE_PROFILE_INCOMPATIBLE = "review_p6_profile_incompatible"
CODE_LINEAGE_INVALID = "review_p6_lineage_invalid"
CODE_BASELINE_UNAVAILABLE = "review_p6_baseline_unavailable"
CODE_CANDIDATE_INVALID = "review_p6_candidate_invalid"
CODE_SINGLE_EVENT = "review_p6_single_event"
CODE_DUPLICATE_EVIDENCE = "review_p6_duplicate_evidence"
CODE_EVIDENCE_INVALID = "review_p6_evidence_invalid"
CODE_DIRECTION_INVALID = "review_p6_direction_invalid"
CODE_LIGHTENING_UNMEASURED = "review_p6_lightening_unmeasured"
CODE_GUARD_INVALID = "review_p6_guard_invalid"
CODE_OVERLAP_UNRESOLVED = "review_p6_overlap_unresolved"
CODE_FORBIDDEN_CHANGE = "review_p6_forbidden_change"
CODE_BEFORE_STATE_CONFLICT = "review_p6_before_state_conflict"
CODE_DISCOVERY_SLOTS_UNMET = "review_p6_discovery_slots_unmet"
CODE_HOLDOUT_UNBOUND = "review_p6_holdout_unbound"
CODE_HOLDOUT_NOT_APPLICABLE = "review_p6_holdout_not_applicable"
CODE_HOLDOUT_UNSETTLED = "review_p6_holdout_unsettled"
CODE_HOLDOUT_FAILED = "review_p6_holdout_failed"
CODE_EVALUATION_INVALID = "review_p6_evaluation_invalid"
CODE_ENVIRONMENT_UNATTRIBUTED = "review_p6_environment_unattributed"
CODE_HUMAN_WAIT = "review_p6_human_wait"
CODE_NOT_AUTHORIZED = "review_p6_not_authorized"
CODE_POLICY_REVIEW_INVALID = "review_p6_policy_review_invalid"
#: RB6B-M5: a stored P6-capable request whose frozen Effective Policy does not read under this build. A validation /
#: refusal code (ValidationError), never a reclassification of the request as another family's or as v1.
CODE_EFFECTIVE_POLICY_UNREADABLE = "review_p6_effective_policy_unreadable"
STOP_CODES = (
    CODE_SURFACE_UNKNOWN,
    CODE_SURFACE_NON_ADAPTIVE,
    CODE_SETTING_INVALID,
    CODE_RECLASSIFIED,
    CODE_PROFILE_INVALID,
    CODE_PROFILE_INCOMPATIBLE,
    CODE_LINEAGE_INVALID,
    CODE_BASELINE_UNAVAILABLE,
    CODE_CANDIDATE_INVALID,
    CODE_SINGLE_EVENT,
    CODE_DUPLICATE_EVIDENCE,
    CODE_EVIDENCE_INVALID,
    CODE_DIRECTION_INVALID,
    CODE_LIGHTENING_UNMEASURED,
    CODE_GUARD_INVALID,
    CODE_OVERLAP_UNRESOLVED,
    CODE_FORBIDDEN_CHANGE,
    CODE_BEFORE_STATE_CONFLICT,
    CODE_DISCOVERY_SLOTS_UNMET,
    CODE_HOLDOUT_UNBOUND,
    CODE_HOLDOUT_NOT_APPLICABLE,
    CODE_HOLDOUT_UNSETTLED,
    CODE_HOLDOUT_FAILED,
    CODE_EVALUATION_INVALID,
    CODE_ENVIRONMENT_UNATTRIBUTED,
    CODE_HUMAN_WAIT,
    CODE_NOT_AUTHORIZED,
    CODE_POLICY_REVIEW_INVALID,
)

#: The P6 validation / refusal codes raised as ValidationError, never as a STOP (RB6B-M5).
VALIDATION_CODES = (CODE_EFFECTIVE_POLICY_UNREADABLE,)

REASON_PROFILE_BEFORE_MISMATCH = "review_p6_profile_before_mismatch"
REASON_PERSISTED_MISMATCH = "review_p6_persisted_mismatch"
REASON_CHAIN_INVALID = "review_p6_chain_invalid"
REASON_PUBLICATION_INVALID = "review_p6_publication_invalid"
REASON_RECORD_CONFLICT = "review_p6_record_conflict"
RECONCILE_REASONS = (
    REASON_PROFILE_BEFORE_MISMATCH,
    REASON_PERSISTED_MISMATCH,
    REASON_CHAIN_INVALID,
    REASON_PUBLICATION_INVALID,
    REASON_RECORD_CONFLICT,
)


def stop(code: str, message: str) -> StopError:
    """A P6 STOP (built here so every caller raises a code of this catalogue)."""
    if code not in STOP_CODES:
        raise ValueError(f"not a P6 STOP code: {code!r}")
    return StopError(message, code=code)


def reconcile(message: str, reason: str) -> ReconcileRequired:
    if reason not in RECONCILE_REASONS:
        raise ValueError(f"not a P6 reconcile reason: {reason!r}")
    return ReconcileRequired(f"{message}: reconcile required", reason=reason)


def _invalid(message: str, code: str = "review_record_invalid") -> ValidationError:
    return ValidationError(message, code=code)


# --------------------------------------------------------------------------- the fixed two-surface registry (§30.2)

CLASS_MANDATORY = "mandatory"
CLASS_DEFAULT = "default"
CLASS_ADAPTIVE = "adaptive"
STRENGTH_CLASSES = (CLASS_MANDATORY, CLASS_DEFAULT, CLASS_ADAPTIVE)

SURFACE_REQUIRED_SLOTS = "review.discovery.required_slots"
SURFACE_EXTRA_SCOPE_STEPS = "review.reverification.extra_scope_steps"
STRENGTH_ORDER_HIGHER = "higher_integer_is_stronger"


@dataclass(frozen=True)
class PolicySurface:
    """One registered Project-adaptable Review execution surface: a fixed Global / meta-policy fact."""

    policy_surface_id: str
    strength_class: str
    global_setting: int
    minimum: int
    maximum: int
    applies_to: str
    measurement_channel: str
    meaning: str

    def in_range(self, value: object) -> bool:
        return type(value) is int and self.minimum <= value <= self.maximum

    def to_record(self) -> dict[str, Any]:
        return {
            "policy_surface_id": self.policy_surface_id,
            "strength_class": self.strength_class,
            "global_setting": self.global_setting,
            "allowed_range": {"minimum": self.minimum, "maximum": self.maximum},
            "strength_order": STRENGTH_ORDER_HIGHER,
            "applies_to": self.applies_to,
            "measurement_channel": self.measurement_channel,
            "meaning": self.meaning,
        }


SURFACES: tuple[PolicySurface, ...] = (
    PolicySurface(
        SURFACE_REQUIRED_SLOTS, CLASS_DEFAULT, 1, 1, 4,
        "P4-capable Formal Review discovery",
        "discovery_holdout_slots",
        "setting N requires N durably accepted discovery task slots, all settled before adjudication; slots beyond "
        "one bind distinct reviewer identity/version pairs; actor identity/version is invocation binding, never "
        "Profile data; one reviewer is the absolute floor",
    ),
    PolicySurface(
        SURFACE_EXTRA_SCOPE_STEPS, CLASS_ADAPTIVE, 0, 0, 3,
        "P4-capable post-repair reverification",
        "reverification_holdout_checks",
        "setting N widens the P4 minimum reverification by N semantic impact levels (LOCAL < SHARED < CONTRACT < "
        "FOUNDATION), capped at FOUNDATION; the P4 minimum stays mandatory and is never verified less",
    ),
)
SURFACE_BY_ID: Mapping[str, PolicySurface] = {surface.policy_surface_id: surface for surface in SURFACES}

#: §15.11 / §30.3: the absolute non-adaptive surface. A proposal naming any of it is never a Project Policy Change
#: Candidate - it is refused mechanically, whatever an external reviewer said.
NON_ADAPTIVE: tuple[tuple[str, str], ...] = (
    ("lifecycle", "Roadmap/Phase/Work and lifecycle/completion semantics"),
    ("completion", "lifecycle/completion semantics"),
    ("roadmap", "Roadmap/Phase/Work semantics"),
    ("phase", "Roadmap/Phase/Work semantics"),
    ("work", "Roadmap/Phase/Work semantics"),
    ("human", "H-1 through H-4 and the HUMAN decision boundary"),
    ("finding", "Problem/Improvement meaning"),
    ("category", "Problem/Improvement meaning"),
    ("severity", "HIGH/MID/LOW meaning and blocking semantics"),
    ("blocking", "HIGH/MID/LOW meaning and blocking semantics"),
    ("requirement", "product/user requirement meaning"),
    ("routing", "canonical authority/routing rules"),
    ("authority", "canonical authority/routing rules"),
    ("mutation", "Mutation/Git safety invariants"),
    ("git", "Mutation/Git safety invariants"),
    ("security", "non-negotiable security/destructive-operation rules"),
    ("destructive", "non-negotiable security/destructive-operation rules"),
    ("authorization", "Review-v1 authorization/Consumption correctness"),
    ("consumption", "Review-v1 authorization/Consumption correctness"),
    ("capability", "Project-local capability approval boundary"),
    ("approval", "Project-local capability approval boundary"),
    # RB8-FC-07: self-hosting is a Mutation/Git safety boundary, never a learned adaptation
    ("self_hosting", "self-hosting (Mutation/Git safety invariants)"),
)
_SURFACE_ID = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\Z")


def surface_problem(policy_surface_id: object) -> tuple[str, str] | None:
    """``(code, message)`` when ``policy_surface_id`` is not an adaptable registered surface; ``None`` when it is.

    An unknown surface is not adaptable (§15.10); one naming the absolute
    non-adaptive surface (§15.11) is refused with its own code. The registry is
    fixed: nothing learned adds to it, and a Profile never reclassifies it.
    """
    if not isinstance(policy_surface_id, str):
        # RB6B-L1: an unhashable or non-text identity is a coded refusal, never a TypeError
        return CODE_SURFACE_UNKNOWN, (f"{policy_surface_id!r} is not a policy surface identity; an unknown surface is "
                                      "not adaptable")
    if policy_surface_id in SURFACE_BY_ID:
        surface = SURFACE_BY_ID[policy_surface_id]
        if surface.strength_class == CLASS_MANDATORY:
            return CODE_SURFACE_NON_ADAPTIVE, f"{policy_surface_id} is mandatory and cannot be adapted"
        return None
    text = policy_surface_id if isinstance(policy_surface_id, str) else ""
    segments = text.lower().replace("-", "_").split(".") if text else []
    for segment in segments:
        for prefix, described in NON_ADAPTIVE:
            if segment == prefix or segment.startswith(prefix + "_") or segment.endswith("_" + prefix):
                return CODE_SURFACE_NON_ADAPTIVE, (
                    f"{policy_surface_id!r} names the absolute non-adaptive surface ({described}); Project learning may "
                    "change how Workline verifies correctness, never what correctness means"
                )
    return CODE_SURFACE_UNKNOWN, (
        f"{policy_surface_id!r} is not one of the registered adaptive surfaces "
        f"({', '.join(SURFACE_BY_ID)}); an unknown surface is not adaptable and no learned process adds one"
    )


def bound_global_settings(baseline_record: Mapping[str, Any]) -> dict[str, int]:
    """The Global setting of every surface, read from a baseline RECORD - positive runtime evidence (FC-RB7-1 / -8).

    A Profile's Global settings are those of the baseline record its change
    record binds (:func:`written_under`); the current baseline's come from the
    baseline object. Global policy versions above the derived 1 are runtime
    data RB7's loader / adapter resolves - never rows of a code table here.
    """
    found: dict[str, int] = {}
    for item in baseline_record["surfaces"]:
        found[str(item["policy_surface_id"])] = int(item["global_setting"])
    return found


def require_surface(policy_surface_id: object) -> PolicySurface:
    problem = surface_problem(policy_surface_id)
    if problem is not None:
        raise stop(*problem)
    return SURFACE_BY_ID[str(policy_surface_id)]


# --------------------------------------------------------------------------- impact-scaled reverification (§30.2 B)

#: P4's frozen impact order (§12.14 / §30.2).
IMPACT_ORDER = (records.IMPACT_LOCAL, records.IMPACT_SHARED, records.IMPACT_CONTRACT, records.IMPACT_FOUNDATION)


def widened_impact_levels(impact_class: str, extra_scope_steps: int) -> tuple[str, ...]:
    """The impact levels a repair is reverified at: its own, widened by ``extra_scope_steps``, capped at FOUNDATION.

    Never below the P4 minimum: the repair's own level is always included, so a
    Profile can only add verification.
    """
    if impact_class not in IMPACT_ORDER:
        raise _invalid(f"not an impact class: {impact_class!r}")
    if type(extra_scope_steps) is not int or extra_scope_steps < 0:
        raise _invalid(f"extra_scope_steps is a non-negative integer, not {extra_scope_steps!r}")
    start = IMPACT_ORDER.index(impact_class)
    end = min(start + extra_scope_steps, len(IMPACT_ORDER) - 1)
    return IMPACT_ORDER[start:end + 1]


# --------------------------------------------------------------------------- the fixed meta-rules (§15.10, §15.15-§15.19, §15.25)

SINGLE_EVENT_FLOOR = 2
DIRECTION_STRENGTHEN = "strengthen"
DIRECTION_LIGHTEN = "lighten"
DIRECTION_TEMPORARY_GUARD = "temporary_guard"
DIRECTION_ADJUST = "adjust"
DIRECTION_ROLLBACK = "rollback"
CHANGE_DIRECTIONS = (DIRECTION_STRENGTHEN, DIRECTION_LIGHTEN, DIRECTION_TEMPORARY_GUARD, DIRECTION_ADJUST,
                     DIRECTION_ROLLBACK)
#: An override's effect relative to the Global setting.
OVERRIDE_DIRECTIONS = (DIRECTION_STRENGTHEN, DIRECTION_LIGHTEN)
OVERLAP_PROVEN_DISJOINT = "proven_disjoint"
OVERLAP_KNOWN = "known_overlap"
OVERLAP_UNRESOLVED = "overlap_unresolved"
OVERLAP_CLASSES = (OVERLAP_PROVEN_DISJOINT, OVERLAP_KNOWN, OVERLAP_UNRESOLVED)
_OVERLAP_STRICTNESS = {OVERLAP_PROVEN_DISJOINT: 0, OVERLAP_UNRESOLVED: 1, OVERLAP_KNOWN: 2}
HOLDOUT_SELECTION_ALL_RELEVANT = "all_relevant"
RESULT_RETAIN = "retain"
RESULT_ADJUST = "adjust"
RESULT_ROLLBACK = "rollback"
RESULT_INCONCLUSIVE = "inconclusive"
EVALUATION_RESULTS = (RESULT_RETAIN, RESULT_ADJUST, RESULT_ROLLBACK, RESULT_INCONCLUSIVE)
NEXT_END_OBSERVATION = "end_observation"
NEXT_CONTINUE_OBSERVATION = "continue_observation"
NEXT_NEW_CANDIDATE = "new_candidate_required"
NEXT_ACTIONS = (NEXT_END_OBSERVATION, NEXT_CONTINUE_OBSERVATION, NEXT_NEW_CANDIDATE)
ENVIRONMENT_WINDOW_SPLIT = "window_split"
ENVIRONMENT_IRRELEVANCE_PROOF = "irrelevance_proof"
ENVIRONMENT_BASES = (ENVIRONMENT_WINDOW_SPLIT, ENVIRONMENT_IRRELEVANCE_PROOF)

META_RULES: dict[str, Any] = {
    serialize.SCHEMA_KEY: SCHEMA_META_RULES,
    serialize.VERSION_KEY: RECORD_VERSION,
    "meta_rules_id": META_RULES_ID,
    "strength_classes": {
        CLASS_MANDATORY: "Project policy cannot disable or lighten it",
        CLASS_DEFAULT: "Global standard; Project may strengthen; Project may lighten only under the stronger lightening contract",
        CLASS_ADAPTIVE: "Project may strengthen or lighten inside an explicitly bounded allowed range",
    },
    "classification_rule": "classification and allowed ranges are fixed Global/meta-policy facts; a Profile never "
                           "reclassifies or invents a surface; an unknown or unclassified surface is not adaptable",
    "non_adaptive": sorted({described for _, described in NON_ADAPTIVE}),
    "single_event_floor": SINGLE_EVENT_FLOOR,
    "single_event_rule": "permanent strengthen, lighten and adjust need at least two distinct relevant P5 opportunity "
                         "references under a frozen Relevant Opportunity definition, duplicate sources rejected; an "
                         "eligibility floor, never a claim that two events prove truth",
    "opportunity_rule": "the denominator is Relevant Opportunity, never raw Review count; an unexercised surface is not "
                        "an opportunity; only supported causality counts as confirmed",
    "temporary_guard_rule": "one serious supported escape may create a temporary_guard only when it strengthens inside "
                            "the allowed range, changes no correctness or authority meaning and carries reevaluation "
                            "or expiry criteria; it never becomes permanent without the normal repeated-evidence path: "
                            "a reviewed strengthen superseding it at its setting under the single-event floor",
    "lightening_rule": "every downward setting change freezes the pre-change stronger behaviour as an independent "
                       "all_relevant holdout; without it the lightening is not authorized; the change never weakens "
                       "the channel that measures it",
    "pre_change_rule": "a Policy Change is reviewed under the pre-change Effective Policy and these fixed meta-rules; "
                       "the proposed after-state never selects fewer reviewers or checks for the review authorizing it",
    "overlap_rule": "two experiments on one surface are known_overlap; experiments on the two v1 surfaces measure "
                    "disjoint channels and are proven_disjoint; only proven_disjoint observes concurrently; "
                    "known_overlap and overlap_unresolved serialize or are explicitly superseded; a Candidate "
                    "supersedes only experiments on its own surface and never ends a lightening below the behaviour "
                    "its holdout measures",
    "overlap_classes": list(OVERLAP_CLASSES),
    "environment_rule": "a material environment identity change during an observation window needs a window split or a "
                        "positive irrelevance proof; otherwise the result is inconclusive; chronology is never causality",
    "evaluation_results": list(EVALUATION_RESULTS),
    "evaluation_rule": "an evaluation never rewrites the Profile; adjust and rollback need a new reviewed Candidate; "
                       "inconclusive is not success; retain ends observation only after the frozen minimum of "
                       "distinct relevant opportunities observed under the change (its holdout in force); a "
                       "temporary_guard never ends observation by evaluation",
    "lineage_rule": "a Profile is applied only when a stored Policy Change produced it: version 1 from absence, then "
                    "+1 with the exact parent; a Profile no change produced is never an Effective Policy",
    "compatibility_rule": "a Profile is applied only when its compatibility with the current Global baseline is "
                          "positively proven: exact derived-baseline compatibility while the baseline source_mode is "
                          "derived-baseline, the versioned total compatibility adapter once RB7 materializes Global "
                          "policy; otherwise "
                          "no guess, no dropped override, no new Run under that Profile",
}


def meta_rules_record() -> dict[str, Any]:
    return serialize.canonical_data(META_RULES)


def meta_rules_digest() -> str:
    return serialize.digest(meta_rules_record())


# --------------------------------------------------------------------------- the GlobalPolicyBaseline loader (§15.9, §30.4)

BASELINE_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "contract", "baseline_version", "source_mode",
    "global_policy_identity", "root_authority_digests", "meta_rules_id", "meta_rules_digest", "surfaces",
    "loader_semantics_identity", "source_policy_identities",
)


@dataclass(frozen=True)
class GlobalPolicyBaseline:
    """The normalized, read-only logical representation of current Global Review policy.

    ``source_mode`` is ``derived-baseline`` until RB7 materializes Global policy;
    RB7 keeps this interface (:func:`load_global_baseline`). Its canonical
    digest is the Global baseline identity Review Context and Project Profiles
    bind.
    """

    record: dict[str, Any]

    @property
    def digest(self) -> str:
        return serialize.digest(self.record)

    @property
    def version(self) -> int:
        return int(self.record["baseline_version"])

    @property
    def source_mode(self) -> str:
        return str(self.record["source_mode"])

    @property
    def global_policy_identity(self) -> str:
        return str(self.record["global_policy_identity"])

    @property
    def semantic_projection(self) -> dict[str, Any]:
        """The policy-semantic identity (R6-2): what exact derived-baseline compatibility compares."""
        return semantic_projection(self.record)

    @property
    def semantic_digest(self) -> str:
        return semantic_digest(self.record)

    def surface(self, policy_surface_id: str) -> dict[str, Any]:
        for item in self.record["surfaces"]:
            if item["policy_surface_id"] == policy_surface_id:
                return item
        raise _invalid(f"the Global baseline holds no surface {policy_surface_id!r}")

    def global_setting(self, policy_surface_id: str) -> int:
        return int(self.surface(policy_surface_id)["global_setting"])


SCHEMA_SEMANTIC = "review-p6-baseline-semantics"


def semantic_projection(baseline_record: Mapping[str, Any]) -> dict[str, Any]:
    """The normalized POLICY-SEMANTIC identity of a baseline record (R6-2 item 2).

    Included: each surface's id, strength class, allowed range and Global
    setting; the fixed meta-rules identity and digest; the loader semantics
    identity; and the Global POLICY version. Excluded, as provenance and not
    policy semantics: ``source_mode``, ``root_authority_digests`` and
    ``source_policy_identities``. A text-only Workline-root edit changes the
    canonical baseline digest and leaves this projection unchanged.
    """
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_SEMANTIC, serialize.VERSION_KEY: RECORD_VERSION,
        "baseline_version": baseline_record["baseline_version"],
        "surfaces": [
            {"policy_surface_id": item["policy_surface_id"], "strength_class": item["strength_class"],
             "allowed_range": dict(item["allowed_range"]), "global_setting": item["global_setting"]}
            for item in baseline_record["surfaces"]
        ],
        "meta_rules_id": baseline_record["meta_rules_id"],
        "meta_rules_digest": baseline_record["meta_rules_digest"],
        "loader_semantics_identity": baseline_record["loader_semantics_identity"],
    })


def semantic_digest(baseline_record: Mapping[str, Any]) -> str:
    return serialize.digest(semantic_projection(baseline_record))


def baseline_record_problems(record: object, described: str) -> list[str]:
    """Structure only: a baseline record as a change record binds it (any Global policy version, any source mode).

    Whether its policy semantics equal the current baseline's is the
    compatibility decision's (:func:`compatibility_problem`), never this one's.
    """
    if not isinstance(record, dict) or set(record) != set(BASELINE_FIELDS):
        return [f"{described} does not hold exactly the baseline record fields"]
    if record.get(serialize.SCHEMA_KEY) != SCHEMA_BASELINE or record.get(serialize.VERSION_KEY) != RECORD_VERSION \
            or record.get("contract") != BASELINE_CONTRACT:
        return [f"{described} is not a {BASELINE_CONTRACT} baseline record"]
    if type(record.get("baseline_version")) is not int or record["baseline_version"] < 1:
        return [f"{described} names no positive Global policy version"]
    surfaces = record.get("surfaces")
    if not isinstance(surfaces, list) or any(
        not isinstance(item, dict) or not {"policy_surface_id", "strength_class", "allowed_range", "global_setting"}
        <= set(item) or not isinstance(item.get("allowed_range"), dict) for item in surfaces
    ):
        return [f"{described} surfaces are not surface records"]
    return []


def source_policy_identities() -> list[dict[str, str]]:
    """The existing planning / Work / P4 / P5 policy identities the derived baseline proves its starting point from."""
    from . import p4, planning, work_review

    return [
        {"id": "planning", "policy_id": planning.POLICY_ID, "digest": planning.policy_hash()},
        {"id": "work", "policy_id": work_review.POLICY_ID, "digest": work_review.policy_hash()},
        {"id": "p4", "policy_id": p4.POLICY_ID, "digest": p4.policy_hash(p4.POLICY_ID)},
        {"id": "p5", "policy_id": p4.P5_POLICY_ID, "digest": p4.policy_hash(p4.P5_POLICY_ID)},
        {"id": "p6", "policy_id": P6_POLICY_ID, "digest": p4.family_policy_hash(P6_POLICY_ID)},
    ]


def baseline_authority_digests(workline_root: Path) -> list[dict[str, str]]:
    """``registry.md`` and the review / roadmap / start Skills of the configured Workline root, read-only."""
    from ..registry import resolve_skill

    found: list[dict[str, str]] = []
    for authority_id in BASELINE_AUTHORITY_IDS:
        try:
            if authority_id == "registry":
                path = Path(workline_root) / "registry.md"
            else:
                path = resolve_skill(Path(workline_root), authority_id).path
            data = Path(path).read_bytes()
        except (OSError, StopError) as exc:
            raise stop(CODE_BASELINE_UNAVAILABLE,
                       f"the Global policy baseline cannot be derived: {authority_id} cannot be resolved or read ({exc})"
                       ) from exc
        found.append({"id": authority_id, "digest": hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()})
    return found


def baseline_record(authority: Sequence[Mapping[str, str]], sources: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """The canonical derived baseline over exact ``authority`` digests and ``sources`` identities."""
    surfaces = [surface.to_record() for surface in SURFACES]
    identity = serialize.digest({
        serialize.SCHEMA_KEY: SCHEMA_BASELINE + "-identity", serialize.VERSION_KEY: RECORD_VERSION,
        "contract": BASELINE_CONTRACT, "meta_rules_digest": meta_rules_digest(), "surfaces": surfaces,
        "source_policy_identities": [dict(item) for item in sources],
    })
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_BASELINE,
        serialize.VERSION_KEY: RECORD_VERSION,
        "contract": BASELINE_CONTRACT,
        "baseline_version": BASELINE_VERSION,
        "source_mode": SOURCE_MODE_DERIVED,
        "global_policy_identity": identity,
        "root_authority_digests": [dict(item) for item in authority],
        "meta_rules_id": META_RULES_ID,
        "meta_rules_digest": meta_rules_digest(),
        "surfaces": surfaces,
        "loader_semantics_identity": LOADER_SEMANTICS_IDENTITY,
        "source_policy_identities": [dict(item) for item in sources],
    })


def load_global_baseline(workline_root: Path) -> GlobalPolicyBaseline:
    """The canonical read-only GlobalPolicyBaseline loader (§30.4); it never writes the Workline root.

    Before RB7 it derives the baseline exactly and reproducibly from the
    current canonical runtime authority (registry.md and the review, roadmap
    and start Skills), the fixed meta-rules, the two surface definitions and
    the existing planning / Work / P4 / P5 policy identities. RB7 keeps this
    interface when it materializes Global policy.
    """
    record = baseline_record(baseline_authority_digests(workline_root), source_policy_identities())
    parse_baseline(record, "the derived Global policy baseline")
    return GlobalPolicyBaseline(record)


def parse_baseline(record: object, described: str) -> GlobalPolicyBaseline:
    """A baseline record, strictly: exactly its fields, the fixed registry and meta-rules, derived mode."""
    found = records._require_mapping(record, described)
    serialize.require_schema(found, SCHEMA_BASELINE, RECORD_VERSION, described)
    records._require_exact_fields(found, BASELINE_FIELDS, described)
    if found.get("contract") != BASELINE_CONTRACT or found.get("baseline_version") != BASELINE_VERSION:
        raise _invalid(f"{described} is not a {BASELINE_CONTRACT} version {BASELINE_VERSION} baseline")
    if found.get("source_mode") != SOURCE_MODE_DERIVED:
        raise _invalid(f"{described} source_mode is {found.get('source_mode')!r}, not {SOURCE_MODE_DERIVED}")
    if found.get("surfaces") != [surface.to_record() for surface in SURFACES]:
        raise _invalid(f"{described} does not carry exactly the fixed two-surface registry")
    if found.get("meta_rules_digest") != meta_rules_digest() or found.get("meta_rules_id") != META_RULES_ID:
        raise _invalid(f"{described} does not bind the fixed meta-rules")
    if found.get("loader_semantics_identity") != LOADER_SEMANTICS_IDENTITY:
        raise _invalid(f"{described} binds another loader semantics identity")
    return GlobalPolicyBaseline(serialize.canonical_data(found))


# --------------------------------------------------------------------------- the canonical Project Profile (§15.12, §30.5)

PROFILE_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "profile_version", "parent_profile_digest", "global_baseline_digest",
    "global_baseline_version", "loader_semantics_identity", "overrides", "active_experiment_refs",
)
OVERRIDE_FIELDS = ("policy_surface_id", "strength_class", "setting", "direction", "supporting_policy_change_id")


def _override_problems(item: object, described: str) -> list[tuple[str, str]]:
    if not isinstance(item, dict):
        return [(CODE_PROFILE_INVALID, f"{described} is not a mapping")]
    if set(item) != set(OVERRIDE_FIELDS):
        return [(CODE_PROFILE_INVALID, f"{described} does not hold exactly {', '.join(OVERRIDE_FIELDS)}")]
    problem = surface_problem(item["policy_surface_id"])
    if problem is not None:
        return [(problem[0], f"{described}: {problem[1]}")]
    surface = SURFACE_BY_ID[item["policy_surface_id"]]
    found: list[tuple[str, str]] = []
    if item["strength_class"] != surface.strength_class:
        found.append((CODE_RECLASSIFIED, f"{described} classifies {surface.policy_surface_id} as "
                                         f"{item['strength_class']!r}; it is {surface.strength_class} and a Profile "
                                         "never reclassifies a surface"))
    setting = item["setting"]
    if not surface.in_range(setting):
        found.append((CODE_SETTING_INVALID, f"{described} sets {surface.policy_surface_id} to {setting!r}, outside "
                                            f"{surface.minimum}..{surface.maximum}"))
    elif item["direction"] not in OVERRIDE_DIRECTIONS:
        found.append((CODE_PROFILE_INVALID, f"{described} direction {item['direction']!r} is not strengthen or lighten"))
    if not isinstance(item["supporting_policy_change_id"], str) or not is_valid_id(
            item["supporting_policy_change_id"], "review_policy_change"):
        found.append((CODE_PROFILE_INVALID, f"{described} names no review_policy_change id"))
    return found


@dataclass(frozen=True)
class ProjectProfile:
    """The current normalized Project-local policy state - never a free-form configuration file.

    Absence (no file) is valid and means no local override. Its fields are
    exactly :data:`PROFILE_FIELDS`: no actor or provider credential, no
    script, no absolute path, no field this build does not know.
    """

    profile_version: int
    parent_profile_digest: str | None
    global_baseline_digest: str
    global_baseline_version: int
    loader_semantics_identity: str
    overrides: tuple[dict[str, Any], ...]
    active_experiment_refs: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        return {
            serialize.SCHEMA_KEY: SCHEMA_PROFILE,
            serialize.VERSION_KEY: RECORD_VERSION,
            "profile_version": self.profile_version,
            "parent_profile_digest": self.parent_profile_digest,
            "global_baseline_digest": self.global_baseline_digest,
            "global_baseline_version": self.global_baseline_version,
            "loader_semantics_identity": self.loader_semantics_identity,
            "overrides": [dict(item) for item in self.overrides],
            "active_experiment_refs": list(self.active_experiment_refs),
        }

    @property
    def digest(self) -> str:
        return serialize.digest(self.to_record())

    def text(self) -> str:
        return serialize.canonical_text(self.to_record())

    def setting_of(self, policy_surface_id: str) -> int | None:
        for item in self.overrides:
            if item["policy_surface_id"] == policy_surface_id:
                return int(item["setting"])
        return None

    def override_of(self, policy_surface_id: str) -> dict[str, Any] | None:
        for item in self.overrides:
            if item["policy_surface_id"] == policy_surface_id:
                return dict(item)
        return None

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "ProjectProfile":
        problems = profile_problems(record, described)
        if problems:
            code, message = problems[0]
            raise ValidationError(message, code=code)
        return ProjectProfile(
            profile_version=int(record["profile_version"]),
            parent_profile_digest=record["parent_profile_digest"],
            global_baseline_digest=str(record["global_baseline_digest"]),
            global_baseline_version=int(record["global_baseline_version"]),
            loader_semantics_identity=str(record["loader_semantics_identity"]),
            overrides=tuple(dict(item) for item in record["overrides"]),
            active_experiment_refs=tuple(record["active_experiment_refs"]),
        )


def profile_problems(record: object, described: str) -> list[tuple[str, str]]:
    """Every way ``record`` is not a strict canonical Project Profile (structure only, no baseline)."""
    if not isinstance(record, dict):
        return [(CODE_PROFILE_INVALID, f"{described} is not a mapping")]
    if record.get(serialize.SCHEMA_KEY) != SCHEMA_PROFILE or record.get(serialize.VERSION_KEY) != RECORD_VERSION:
        return [(CODE_PROFILE_INVALID, f"{described} is not a {SCHEMA_PROFILE} version {RECORD_VERSION} record")]
    if set(record) != set(PROFILE_FIELDS):
        unknown = sorted(set(record) - set(PROFILE_FIELDS))
        missing = sorted(set(PROFILE_FIELDS) - set(record))
        return [(CODE_PROFILE_INVALID, f"{described} holds unknown field(s) {unknown} or lacks {missing}; a Profile is "
                                       "never free-form configuration")]
    found: list[tuple[str, str]] = []
    version = record["profile_version"]
    if type(version) is not int or version < 1:
        found.append((CODE_PROFILE_INVALID, f"{described} profile_version is {version!r}, not a positive integer"))
    parent = record["parent_profile_digest"]
    if version == 1 and parent is not None:
        found.append((CODE_LINEAGE_INVALID, f"{described} is version 1 and names a parent; the first Profile has none"))
    if type(version) is int and version > 1 and (not isinstance(parent, str) or records.DIGEST_RE.match(parent) is None):
        found.append((CODE_LINEAGE_INVALID, f"{described} is version {version} and names no exact parent digest"))
    if not isinstance(record["global_baseline_digest"], str) or records.DIGEST_RE.match(record["global_baseline_digest"]) is None:
        found.append((CODE_PROFILE_INVALID, f"{described} global_baseline_digest is not a digest"))
    if type(record["global_baseline_version"]) is not int or record["global_baseline_version"] < 1:
        found.append((CODE_PROFILE_INVALID, f"{described} global_baseline_version is not a positive Global policy "
                                            "version"))
    # RB6B-L9: structure only. WHICH loader semantics the Profile binds is the compatibility decision's
    # (:func:`compatibility_problem`): a well-formed Profile of another loader reads as incompatible, never malformed.
    loader = record["loader_semantics_identity"]
    if not isinstance(loader, str) or records.public_safe_problem(loader, limit=records.P4_MAX_LABEL) is not None:
        found.append((CODE_PROFILE_INVALID, f"{described} loader_semantics_identity is not a bounded label"))
    overrides = record["overrides"]
    if not isinstance(overrides, list):
        found.append((CODE_PROFILE_INVALID, f"{described} overrides is not a list"))
        overrides = []
    for index, item in enumerate(overrides):
        found.extend(_override_problems(item, f"{described} override {index}"))
    # RB6B-L1: only text identities are compared; a non-text one is already refused above, coded
    surfaces = [item["policy_surface_id"] for item in overrides
                if isinstance(item, dict) and isinstance(item.get("policy_surface_id"), str)]
    if len(surfaces) != len(set(surfaces)):
        found.append((CODE_PROFILE_INVALID, f"{described} holds two overrides of one surface"))
    elif all(isinstance(value, str) for value in surfaces) and surfaces != sorted(surfaces):
        found.append((CODE_PROFILE_INVALID, f"{described} overrides are not sorted by policy_surface_id"))
    refs = record["active_experiment_refs"]
    if not isinstance(refs, list) or any(not isinstance(ref, str) or not is_valid_id(ref, "review_policy_change")
                                         for ref in refs):
        found.append((CODE_PROFILE_INVALID, f"{described} active_experiment_refs is not a list of policy change ids"))
    elif refs != sorted(set(refs)):
        found.append((CODE_PROFILE_INVALID, f"{described} active_experiment_refs is not sorted and duplicate-free"))
    return found


def parse_profile_bytes(raw: bytes, described: str) -> tuple[ProjectProfile, str]:
    """The canonical read boundary of the Profile: canonical bytes, strict schema, exact round trip."""
    try:
        data, text = serialize.parse_canonical(raw, described)
    except ValidationError as exc:
        raise ValidationError(f"{described} is not canonical: {exc}", code=CODE_PROFILE_INVALID) from exc
    profile = ProjectProfile.from_record(data, described)
    # RB6B-L2: byte-exact canonical form. ``true`` for an integer round-trips as Python data (True == 1) and not as
    # bytes; with this check one Profile has one digest - the digest of its exact bytes is its record's digest.
    if raw != profile.text().encode("utf-8") \
            or serialize.canonical_data(profile.to_record()) != serialize.canonical_data(data):
        raise ValidationError(f"{described} is not exactly the canonical bytes of its schema record",
                              code=CODE_PROFILE_INVALID)
    return profile, text


def written_under(profile: ProjectProfile, reader: Any) -> tuple[dict[str, Any] | None, str | None]:
    """The baseline record ``profile`` was written under, recovered positively from immutable evidence (R6-2 item 3).

    The applicable change record is the one whose ``after_profile_digest`` is
    the Profile's digest - exactly one, found by exact digest, never "newest" -
    and the baseline record it binds must digest to its own baseline digest and
    to the Profile's. ``(record, None)``, or ``(None, why)`` for any missing,
    ambiguous or unequal link.
    """
    digest = profile.digest
    try:
        matching = [change for change in (reader.read_policy_change(change_id) for change_id in reader.policy_change_ids())
                    if change["after_profile_digest"] == digest]
    except (ValidationError, KeyError, TypeError) as exc:
        return None, f"the policy change records do not read ({exc})"
    if len(matching) != 1:
        return None, (f"{len(matching)} applied policy change record(s) produced the current Profile; exactly one "
                      "must, found by its exact digest")
    bound = matching[0]["global_baseline"]
    if serialize.digest(bound) != matching[0]["global_baseline_digest"] \
            or matching[0]["global_baseline_digest"] != profile.global_baseline_digest:
        return None, ("the baseline record the Profile's change record binds does not digest to the Profile's "
                      "global_baseline_digest")
    if bound["baseline_version"] != profile.global_baseline_version:
        return None, "the Profile's Global policy version is not the version of the baseline it was written under"
    return dict(bound), None


def compatibility_problem(profile: ProjectProfile, baseline: GlobalPolicyBaseline, reader: Any) -> str | None:
    """Why ``profile`` cannot be applied under ``baseline``, or ``None`` - the ONLY compatibility decision (FC-RB7-5).

    §30.7 before RB7, as R6-2 rules it: exact equality of the policy-semantic
    projection of the baseline the Profile was written under (recovered from
    its change record, :func:`written_under`) and of the current baseline. A
    text-only Workline-root edit keeps a Profile compatible; a change to the
    surfaces, meta-rules, loader semantics or Global policy version does not,
    until RB7's versioned total adapter proves otherwise. Anything that cannot
    be proven is incompatible: no guess, no merge, no dropped override.
    """
    if profile.loader_semantics_identity != LOADER_SEMANTICS_IDENTITY:
        return "the Profile binds another loader semantics identity"
    bound, problem = written_under(profile, reader)
    if bound is None:
        return f"the baseline the Profile was written under cannot be recovered: {problem}"
    problems = override_global_problems(profile, reader)
    if problems:
        return problems[0]
    if semantic_projection(bound) != baseline.semantic_projection:
        return ("the policy semantics of the Global baseline the Profile was written under are not the current "
                "baseline's (exact derived-baseline compatibility); no override is guessed, merged or dropped")
    for item in profile.overrides:
        surface = baseline.surface(item["policy_surface_id"])
        if item["strength_class"] != surface["strength_class"]:
            return f"the Profile classifies {item['policy_surface_id']} differently from the Global baseline"
    return None


def override_global_problems(profile: ProjectProfile, reader: Any) -> list[str]:
    """Each override against the Global in force when THAT override was decided (FC-RB7-8 / -9).

    That Global is the baseline record bound by the change record the
    override's ``supporting_policy_change_id`` names - positive evidence,
    never a code table and never the current Global: the change set this
    exact setting on this surface, and the override neither restates that
    Global setting nor sits on the other side of it from its direction. A
    Project may stay stricter than a later Global default. Always performed,
    by the reader-aware compatibility decision; never skipped.
    """
    found: list[str] = []
    for item in profile.overrides:
        surface_id = str(item["policy_surface_id"])
        change_id = str(item["supporting_policy_change_id"])
        try:
            change = reader.read_policy_change(change_id) if reader.policy_change_exists(change_id) else None
        except (ValidationError, KeyError, TypeError, AttributeError):
            change = None
        if change is None:
            found.append(f"the override of {surface_id} names policy change {change_id}, which is not stored")
            continue
        if change["affected_policy_surface"] != surface_id or change["after_setting"] != item["setting"]:
            found.append(f"the override of {surface_id} is not the setting its supporting policy change {change_id} "
                         "decided")
            continue
        global_settings = bound_global_settings(change["global_baseline"])
        if surface_id not in global_settings:
            found.append(f"the Profile overrides {surface_id}, which the baseline it was decided under does not hold")
            continue
        global_setting = global_settings[surface_id]
        if item["setting"] == global_setting:
            found.append(f"the Profile restates the Global setting of {surface_id}; an override exists only to differ "
                         "from it")
        elif item["direction"] != (DIRECTION_STRENGTHEN if item["setting"] > global_setting else DIRECTION_LIGHTEN):
            found.append(f"the Profile's override of {surface_id} says direction {item['direction']!r}, and its setting "
                         "is the other side of the Global setting")
    return found


def profile_overlay(profile: ProjectProfile | None, baseline: GlobalPolicyBaseline) -> dict[str, int]:
    """The ONE overlay of a Profile on the Global baseline (FC-RB7-5): every surface's effective setting.

    The Global setting from the baseline object (FC-RB7-1), replaced by the
    Profile's override where it holds one. An absent Profile is the baseline.
    """
    found: dict[str, int] = {}
    for surface in SURFACES:
        override = None if profile is None else profile.setting_of(surface.policy_surface_id)
        found[surface.policy_surface_id] = baseline.global_setting(surface.policy_surface_id) if override is None \
            else override
    return found


# --------------------------------------------------------------------------- active experiments and the Effective Policy (§30.6, §30.24)

@dataclass(frozen=True)
class ActiveExperiment:
    """One applied Policy Change whose experiment contract still governs observation and holdout."""

    policy_change_id: str
    policy_surface_id: str
    direction: str
    holdout_setting: int | None

    #: FC-RB7-6: Project-origin experiments only before RB7; the holdout aggregation is origin-agnostic.
    origin: str = ORIGIN_PROJECT

    def to_record(self) -> dict[str, Any]:
        return {
            "origin": self.origin,
            "policy_change_id": self.policy_change_id,
            "policy_surface_id": self.policy_surface_id,
            "direction": self.direction,
            "holdout_setting": self.holdout_setting,
        }


EFFECTIVE_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "policy_id", "family_policy_digest", "global_baseline", "profile",
    "compatibility", "settings", "meta_rules_digest", "loader_semantics_identity", "active_experiments",
)
ACTIVE_EXPERIMENT_FIELDS = ("origin", "policy_change_id", "policy_surface_id", "direction", "holdout_setting")


def effective_policy_record(baseline: GlobalPolicyBaseline, profile: ProjectProfile | None,
                            active: Sequence[ActiveExperiment]) -> dict[str, Any]:
    """The normalized Effective Policy: Global baseline + Profile or explicit absence (+ the active holdout plan)."""
    from . import p4

    settings = profile_overlay(profile, baseline)
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_EFFECTIVE,
        serialize.VERSION_KEY: RECORD_VERSION,
        "policy_id": P6_POLICY_ID,
        "family_policy_digest": p4.family_policy_hash(P6_POLICY_ID),
        "global_baseline": {
            "contract": BASELINE_CONTRACT, "baseline_version": baseline.version, "digest": baseline.digest,
            "source_mode": baseline.source_mode,
        },
        "profile": None if profile is None else {"profile_version": profile.profile_version, "digest": profile.digest},
        "compatibility": COMPATIBILITY_EXACT_DERIVED_SEMANTIC,
        "settings": settings,
        "meta_rules_digest": meta_rules_digest(),
        "loader_semantics_identity": LOADER_SEMANTICS_IDENTITY,
        "active_experiments": [item.to_record() for item in sorted(active, key=lambda e: (e.policy_surface_id,
                                                                                         e.origin,
                                                                                         e.policy_change_id))],
    })


def parse_effective_policy(record: object, described: str) -> dict[str, Any]:
    """A stored Effective Policy record, strictly; what a P6-capable Run's requests bind under ``effective_policy``."""
    from . import p4

    found = records._require_mapping(record, described)
    serialize.require_schema(found, SCHEMA_EFFECTIVE, RECORD_VERSION, described)
    records._require_exact_fields(found, EFFECTIVE_FIELDS, described)
    if found["policy_id"] != P6_POLICY_ID or found["family_policy_digest"] != p4.family_policy_hash(P6_POLICY_ID):
        raise _invalid(f"{described} does not bind the P6 family policy this build implements")
    baseline = records._require_mapping(found["global_baseline"], f"{described} global_baseline")
    records._require_exact_fields(baseline, ("contract", "baseline_version", "digest", "source_mode"),
                                  f"{described} global_baseline")
    if baseline["contract"] != BASELINE_CONTRACT or baseline["baseline_version"] not in BASELINE_VERSIONS \
            or baseline["source_mode"] not in SOURCE_MODES:
        raise _invalid(f"{described} binds a Global baseline this loader does not read")
    records._require_digest(baseline, "digest", f"{described} global_baseline")
    profile = found["profile"]
    if profile is not None:
        profile = records._require_mapping(profile, f"{described} profile")
        records._require_exact_fields(profile, ("profile_version", "digest"), f"{described} profile")
        records._require_int(profile, "profile_version", f"{described} profile", minimum=1)
        records._require_digest(profile, "digest", f"{described} profile")
    if found["compatibility"] not in COMPATIBILITY_INTERPRETATIONS:
        raise _invalid(f"{described} binds a compatibility interpretation this build does not read")
    settings = records._require_mapping(found["settings"], f"{described} settings")
    if set(settings) != set(SURFACE_BY_ID):
        raise _invalid(f"{described} settings are not exactly the two registered surfaces")
    for surface_id, value in settings.items():
        if not SURFACE_BY_ID[surface_id].in_range(value):
            raise _invalid(f"{described} sets {surface_id} to {value!r}, outside its allowed range")
    if found["meta_rules_digest"] != meta_rules_digest() or found["loader_semantics_identity"] != LOADER_SEMANTICS_IDENTITY:
        raise _invalid(f"{described} binds other meta-rules or loader semantics than this build")
    active = records._require_list(found, "active_experiments", described)
    keys = []
    for item in active:
        entry = records._require_mapping(item, f"{described} active experiment")
        records._require_exact_fields(entry, ACTIVE_EXPERIMENT_FIELDS, f"{described} active experiment")
        kind = EXPERIMENT_ORIGINS.get(entry["origin"])
        if kind is None:
            raise _invalid(f"{described} names an active experiment of an origin this build does not read")
        records._require_id(entry, "policy_change_id", kind, f"{described} active experiment")
        surface = SURFACE_BY_ID.get(entry["policy_surface_id"])
        if surface is None or entry["direction"] not in CHANGE_DIRECTIONS:
            raise _invalid(f"{described} names an active experiment on no registered surface or direction")
        holdout = entry["holdout_setting"]
        if holdout is not None and (not surface.in_range(holdout) or holdout <= settings[surface.policy_surface_id]):
            raise _invalid(f"{described} holds a holdout that is not stronger than the effective setting")
        keys.append((entry["policy_surface_id"], entry["origin"], entry["policy_change_id"]))
    if keys != sorted(set(keys)):
        raise _invalid(f"{described} active experiments are not sorted and duplicate-free")
    return serialize.canonical_data(found)


def effective_policy_hash(record: Mapping[str, Any]) -> str:
    return serialize.digest(dict(record))


def setting(effective: Mapping[str, Any], policy_surface_id: str) -> int:
    return int(effective["settings"][policy_surface_id])


def holdout_setting(effective: Mapping[str, Any], policy_surface_id: str) -> int | None:
    """The strongest holdout an active lightening experiment freezes for ``policy_surface_id``, or ``None``."""
    found = [int(item["holdout_setting"]) for item in effective["active_experiments"]
             if item["policy_surface_id"] == policy_surface_id and item["holdout_setting"] is not None]
    return max(found) if found else None


def required_holdout_slots(effective: Mapping[str, Any]) -> int:
    """How many discovery holdout slots a P6 Run must accept beside its required ones (§30.10-§30.11)."""
    held = holdout_setting(effective, SURFACE_REQUIRED_SLOTS)
    return 0 if held is None else held - setting(effective, SURFACE_REQUIRED_SLOTS)


def reverification_levels(effective: Mapping[str, Any], impact_class: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(required levels, holdout-only levels)`` of a repair under ``effective`` (§30.2 B, §30.10)."""
    required = widened_impact_levels(impact_class, setting(effective, SURFACE_EXTRA_SCOPE_STEPS))
    held = holdout_setting(effective, SURFACE_EXTRA_SCOPE_STEPS)
    if held is None:
        return required, ()
    wider = widened_impact_levels(impact_class, held)
    return required, tuple(level for level in wider if level not in required)


# --------------------------------------------------------------------------- reading the Project's policy state

@dataclass(frozen=True)
class PolicyState:
    """The current Global baseline, the Profile or its explicit absence, the active experiments, and the result."""

    baseline: GlobalPolicyBaseline
    profile: ProjectProfile | None
    active: tuple[ActiveExperiment, ...]
    effective: dict[str, Any]

    @property
    def effective_hash(self) -> str:
        return effective_policy_hash(self.effective)

    @property
    def profile_digest(self) -> str | None:
        return None if self.profile is None else self.profile.digest

    @property
    def profile_version(self) -> int | None:
        return None if self.profile is None else self.profile.profile_version


def ended_experiments(reader: Any) -> set[str]:
    """Policy change ids a terminal evaluation (``end_observation``) has settled (§30.24).

    RB6B-H1: only a terminal evaluation that :func:`retain_problem` accepts
    settles a ref - one of a temporary_guard never does, and neither does one
    whose evidence does not prove the frozen minimum of opportunities observed
    under the change. Such a record is a validation Problem
    (:func:`policy_problems`) and never ends a holdout channel.
    """
    ended: set[str] = set()
    for evaluation_id in reader.policy_evaluation_ids():
        found = reader.read_policy_evaluation(evaluation_id)
        if found["next_action"] != NEXT_END_OBSERVATION:
            continue
        change_id = str(found["policy_change_id"])
        if not reader.policy_change_exists(change_id):
            continue
        if retain_problem(reader, reader.read_policy_change(change_id), found["evidence"]) is None:
            ended.add(change_id)
    return ended


def active_experiments(reader: Any, profile: ProjectProfile | None) -> tuple[ActiveExperiment, ...]:
    """Profile ``active_experiment_refs`` minus refs ended by a terminal evaluation, each read from its change record."""
    if profile is None:
        return ()
    ended = ended_experiments(reader)
    found: list[ActiveExperiment] = []
    for ref in profile.active_experiment_refs:
        if ref in ended:
            continue
        if not reader.policy_change_exists(ref):
            raise stop(CODE_PROFILE_INVALID, f"the Project Profile names active experiment {ref}, whose change record is "
                                             "not stored")
        change = reader.read_policy_change(ref)
        plan = change["holdout_plan"]
        found.append(ActiveExperiment(ref, str(change["affected_policy_surface"]), str(change["direction"]),
                                      None if plan is None else int(plan["holdout_setting"])))
    return tuple(found)


def resolve_policy_state(reader: Any, workline_root: Path, *, require_compatible: bool = True) -> PolicyState:
    """The Effective Policy a NEW P6-capable Run freezes now, read from canonical state only (§15.13, §30.6).

    An absent Profile is valid and is the Global baseline. A malformed Profile,
    or one the current baseline cannot be exactly reconciled with, fails
    closed: no guess, no merge, no dropped override, no new Run (§30.7).
    """
    baseline = load_global_baseline(workline_root)
    try:
        profile = reader.read_profile()
    except ValidationError as exc:
        raise stop(CODE_PROFILE_INVALID, f"the canonical Project Profile does not read: {exc}; no new Review Run is "
                                         "started under it (policy maintenance / reconcile)") from exc
    require_lineage(reader, profile)
    if profile is not None and require_compatible:
        problem = compatibility_problem(profile, baseline, reader)
        if problem is not None:
            raise stop(CODE_PROFILE_INCOMPATIBLE, f"{problem}: no new Review Run is started under this Profile "
                                                  "(policy maintenance / reconcile)")
    active = active_experiments(reader, profile)
    return PolicyState(baseline, profile, active, effective_policy_record(baseline, profile, active))


def require_lineage(reader: Any, profile: ProjectProfile | None) -> None:
    """RB6B-M3: the Profile a new Run would freeze is one the Policy Change operation produced - or a STOP.

    Its lineage is proven from the immutable change records exactly as
    validation proves it (:func:`lineage_problems`): version 1 from absence,
    then +1 with the exact parent, each version produced by a stored change,
    and every override and experiment ref backed by one. A Profile no change
    produced (a direct edit outside ``project-policy-change``) never becomes
    an Effective Policy. Absence with no change record stays valid.
    """
    changes: dict[str, Mapping[str, Any]] = {}
    try:
        for change_id in reader.policy_change_ids():
            changes[change_id] = reader.read_policy_change(change_id)
    except ValidationError as exc:
        raise stop(CODE_LINEAGE_INVALID, f"the policy change records do not read ({exc}); no new Review Run is started "
                                         "(policy maintenance / reconcile)") from exc
    problems = lineage_problems(profile, changes)
    if problems:
        raise stop(CODE_LINEAGE_INVALID, f"the Project Profile's lineage is not proven: {problems[0][1]}; a Profile no "
                                         "Policy Change produced never becomes an Effective Policy, and no new Review "
                                         "Run is started (policy maintenance / reconcile)")


def new_run_effective_policy(reader: Any, workline_root: Path, policy_id: str, discovery: Sequence[Any],
                             holdout: Sequence[Any] = ()) -> dict[str, Any] | None:
    """The Effective Policy a NEW P4-capable Run freezes (R6-1), kind-generic (FC-RB5-4 / FC-RB5-5).

    ``policy_id`` is the family policy the owner's dispatch chose for the Run
    (a new first Run: the P6-capable default; a successor: its cycle's).
    For a P6-capable Run: the current GlobalPolicyBaseline + Profile or its
    explicit absence, fail closed on an incompatible Profile, and the bound
    discovery actors held to ``required_slots`` and the holdout plan. For a P4
    or P5 Run: ``None`` - and a holdout binding is refused, never ignored.
    Everything is checked before any reservation or effect.
    """
    if policy_id != P6_POLICY_ID:
        if holdout:
            raise stop(CODE_HOLDOUT_NOT_APPLICABLE, f"a {policy_id} Run is not P6-capable, so no holdout discovery slot "
                                                    "applies to it; nothing is reserved")
        return None
    state = resolve_policy_state(reader, workline_root)
    problem = discovery_slots_problem(state.effective, discovery, holdout)
    if problem is not None:
        raise stop(*problem)
    return state.effective


def current_effective_policy_hash(reader: Any, workline_root: Path) -> str:
    """The Effective Policy hash a NEW P6-capable Run of ANY P4-capable kind would freeze now (FC-RB5-4).

    Pure and kind-generic: GlobalPolicyBaseline + the canonical Profile or its
    explicit absence; an incompatible Profile fails closed.
    """
    return resolve_policy_state(reader, workline_root).effective_hash


# --------------------------------------------------------------------------- P5 evidence references (§30.31)

POLICY_EVIDENCE_EVALUATIONS = "policy-evaluations"
#: RB6B-L11: enumerated, never derived from ``paths.HISTORY_FAMILIES`` - a later history family (RB5's
#: achievements) is not P6 evidence until a reviewed contract admits it.
EVIDENCE_FAMILIES = (paths.HISTORY_RUNS, paths.HISTORY_FINDINGS, paths.HISTORY_REPAIRS, paths.HISTORY_RELATIONS,
                     paths.HISTORY_HUMAN_DECISIONS, POLICY_EVIDENCE_EVALUATIONS)
EVIDENCE_FIELDS = ("family", "id", "digest")


def _evidence_kind(family: str) -> str:
    return "review_policy_evaluation" if family == POLICY_EVIDENCE_EVALUATIONS else paths.HISTORY_FAMILY_KINDS[family]


def evidence_ref_problems(value: object, described: str) -> list[str]:
    if not isinstance(value, dict) or set(value) != set(EVIDENCE_FIELDS):
        return [f"{described} is not exactly {{family, id, digest}}"]
    if value["family"] not in EVIDENCE_FAMILIES:
        return [f"{described} family {value['family']!r} is not a P5 history family or policy evaluations"]
    if not isinstance(value["id"], str) or not is_valid_id(value["id"], _evidence_kind(value["family"])):
        return [f"{described} id is not a {_evidence_kind(value['family'])} id"]
    if not isinstance(value["digest"], str) or records.DIGEST_RE.match(value["digest"]) is None:
        return [f"{described} digest is not a digest"]
    return []


def stored_evidence_digest(reader: Any, ref: Mapping[str, Any]) -> str:
    """The canonical digest of the stored record ``ref`` names; raises when it is not stored or does not read."""
    if ref["family"] == POLICY_EVIDENCE_EVALUATIONS:
        return reader.policy_evaluation_digest(str(ref["id"]))
    return reader.history_digest(str(ref["family"]), str(ref["id"]))


def opportunity(reader: Any, ref: Mapping[str, Any], policy_surface_id: str) -> str | None:
    """The Relevant Opportunity identity ``ref`` is for ``policy_surface_id``, or ``None`` when it is not one.

    The denominator is Relevant Opportunity, never raw Review count: two refs
    of one Review Run are one opportunity; a surface the referenced Run never
    exercised is no opportunity; only a ``supported`` relation counts.

    Every identity is a Review Run ID (RB6B-M2). A relation is causal evidence
    ABOUT its target, so it is the opportunity of the Run its target belongs
    to (the Run itself, a Finding's Run, a Repair Batch's source Run): naming
    a record together with its own relation is one opportunity, never two. A
    target whose Run cannot be resolved from stored history is none.
    """
    family, identifier = str(ref["family"]), str(ref["id"])
    if family == POLICY_EVIDENCE_EVALUATIONS:
        return None  # an evaluation is evidence about an experiment, not an opportunity of the surface
    found = reader.read_history(family, identifier)
    repair_surface = policy_surface_id == SURFACE_EXTRA_SCOPE_STEPS
    if family == paths.HISTORY_RUNS:
        if repair_surface:
            return found.review_run_id if found.durable_disposition == history.DISPOSITION_REPAIRED else None
        return found.review_run_id if found.gate_generation >= 2 else None
    if family == paths.HISTORY_FINDINGS:
        return None if repair_surface else found.review_run_id
    if family == paths.HISTORY_REPAIRS:
        return found.source_review_run_id
    if family == paths.HISTORY_RELATIONS:
        if not found.confirmed:
            return None
        if repair_surface and found.relation_type != history.RELATION_REPAIR_INDUCED:
            return None
        return _endpoint_run(reader, found.target)
    if family == paths.HISTORY_HUMAN_DECISIONS:
        return None if repair_surface else found.affected_review_run_id
    return None


def _endpoint_run(reader: Any, endpoint: Any) -> str | None:
    """The Review Run a relation endpoint belongs to, read from stored history; ``None`` when it cannot be proven."""
    try:
        if endpoint.kind == history.ENDPOINT_RUN:
            return str(endpoint.id)
        if endpoint.kind == history.ENDPOINT_FINDING:
            return str(reader.read_history(paths.HISTORY_FINDINGS, str(endpoint.id)).review_run_id)
        if endpoint.kind == history.ENDPOINT_REPAIR:
            return str(reader.read_history(paths.HISTORY_REPAIRS, str(endpoint.id)).source_review_run_id)
    except (ValidationError, KeyError, TypeError, AttributeError):
        return None
    return None


#: The relation types that are escapes: what a temporary_guard may originate from (RB6B-L3).
ESCAPE_RELATIONS = (history.RELATION_DOWNSTREAM_ESCAPE, history.RELATION_REPAIR_INDUCED)
SERIOUS_SEVERITIES = ("HIGH", "MID")


def serious_escape(reader: Any, ref: Mapping[str, Any]) -> bool:
    """Whether ``ref`` is one serious supported escape (§15.15, §30.9; RB6B-L3).

    A ``supported`` downstream_escape / repair_induced relation, or a stored
    (hence supported) HIGH / MID Problem Finding. Anything unreadable is not.
    """
    family = str(ref["family"])
    try:
        if family == paths.HISTORY_RELATIONS:
            found = reader.read_history(family, str(ref["id"]))
            return bool(found.confirmed) and found.relation_type in ESCAPE_RELATIONS
        if family == paths.HISTORY_FINDINGS:
            found = reader.read_history(family, str(ref["id"]))
            return found.category == records.OUTCOME_PROBLEM and found.severity in SERIOUS_SEVERITIES
    except (ValidationError, KeyError, TypeError, AttributeError):
        return False
    return False


def frozen_effective_policy(reader: Any, review_run_id: str) -> dict[str, Any] | None:
    """The Effective Policy Review Run ``review_run_id`` froze in its own generation-1 request, or ``None``."""
    from . import p4

    try:
        chain = reader.gate_chain(review_run_id)
        return None if chain is None else p4.run_effective_policy(reader, chain)
    except (ValidationError, KeyError, TypeError, AttributeError, IndexError):
        return None


def observed_opportunities(reader: Any, change: Mapping[str, Any], evidence: Iterable[Mapping[str, Any]]) -> set[str]:
    """The distinct Relevant Opportunities ``evidence`` proves were OBSERVED UNDER ``change`` (RB6B-H1).

    One per Review Run. A ref counts only when it is a Relevant Opportunity of
    the change's surface (that Run exercised the surface; :func:`opportunity`)
    AND that Run froze an Effective Policy listing the change as an active
    experiment - so it is post-change, observed under the change's frozen
    contract and, for a lightening, ran with the holdout the change froze (a
    Run is refused without it). Chronology is never the proof (§15.26).
    """
    surface_id = str(change["affected_policy_surface"])
    change_id = str(change["policy_change_id"])
    plan = change["holdout_plan"]
    found: set[str] = set()
    for ref in evidence:
        if ref["family"] == POLICY_EVIDENCE_EVALUATIONS:
            continue
        try:
            identity = opportunity(reader, ref, surface_id)
        except (ValidationError, KeyError, TypeError, AttributeError):
            continue
        if identity is None or identity in found:
            continue
        frozen = frozen_effective_policy(reader, identity)
        if frozen is None:
            continue
        if any(item["origin"] == ORIGIN_PROJECT and item["policy_change_id"] == change_id
               and (plan is None or item["holdout_setting"] == plan["holdout_setting"])
               for item in frozen["active_experiments"]):
            found.add(identity)
    return found


def retain_problem(reader: Any, change: Mapping[str, Any], evidence: Iterable[Mapping[str, Any]]) -> str | None:
    """Why a ``retain`` / ``end_observation`` of ``change`` is not allowed, or ``None`` (RB6B-H1, §15.15, §15.17).

    A temporary_guard never becomes permanent by an evaluation: a reviewed
    strengthen Candidate that meets the single-event floor and supersedes it
    does, or a rollback ends it. Any other experiment ends only after its
    frozen ``minimum_opportunities`` distinct relevant opportunities were
    observed under it (:func:`observed_opportunities`).
    """
    if change["direction"] == DIRECTION_TEMPORARY_GUARD:
        return (f"{change['policy_change_id']} is a temporary_guard, which never becomes permanent through an "
                "evaluation; a reviewed strengthen Candidate that meets the single-event floor and supersedes it does, "
                "or a rollback ends it")
    minimum = int(change["observation_window"]["minimum_opportunities"])
    observed = observed_opportunities(reader, change, evidence)
    if len(observed) < minimum:
        holdout = ", with its holdout in force," if change["holdout_plan"] is not None else ""
        return (f"retain ends the observation of {change['policy_change_id']}, and its frozen measurement contract needs "
                f"at least {minimum} distinct relevant opportunities observed under the change{holdout} that exercised "
                f"{change['affected_policy_surface']}; the evidence proves {len(observed)}")
    return None


# --------------------------------------------------------------------------- the Policy Change request (caller input)

REQUEST_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "policy_surface_id", "direction", "after_setting", "evidence",
    "opportunity_definition", "opportunities", "expected_effect", "validation_plan", "measurement_contract",
    "observation_window", "success_criteria", "rollback_threshold", "environment", "overlap_classification",
    "supersedes", "rolls_back", "reevaluation",
)
MEASUREMENT_FIELDS = ("version", "metric", "continued_observation_permitted")
WINDOW_FIELDS = ("minimum_opportunities", "maximum_opportunities")
ENVIRONMENT_INPUT_FIELDS = ("reviewers", "check_adapters", "toolchain", "dependencies")


@dataclass(frozen=True)
class EvidenceRef:
    family: str
    id: str
    digest: str

    def to_record(self) -> dict[str, str]:
        return {"family": self.family, "id": self.id, "digest": self.digest}


@dataclass(frozen=True)
class MeasurementContract:
    version: str
    metric: str
    continued_observation_permitted: bool

    def to_record(self) -> dict[str, Any]:
        return {"version": self.version, "metric": self.metric,
                "continued_observation_permitted": self.continued_observation_permitted}


@dataclass(frozen=True)
class ObservationWindow:
    minimum_opportunities: int
    maximum_opportunities: int

    def to_record(self) -> dict[str, int]:
        return {"minimum_opportunities": self.minimum_opportunities,
                "maximum_opportunities": self.maximum_opportunities}


@dataclass(frozen=True)
class EnvironmentInput:
    """The caller-declared material environment the measurement is attributed under (§15.26, §30.25)."""

    reviewers: tuple[str, ...]
    check_adapters: tuple[str, ...]
    toolchain: str
    dependencies: tuple[str, ...] = ()

    def to_record(self) -> dict[str, Any]:
        return {"reviewers": sorted(set(self.reviewers)), "check_adapters": sorted(set(self.check_adapters)),
                "toolchain": self.toolchain, "dependencies": sorted(set(self.dependencies))}


@dataclass(frozen=True)
class PolicyChangeRequest:
    """What a caller asks ``project-policy-change`` to propose: normalized data, never an imperative patch.

    ``opportunities`` is the Relevant Opportunity set, a subset of
    ``evidence``; both are exact P5 references (family, id, digest). The
    Project itself is implicit in the repository (§30.8).
    """

    policy_surface_id: str
    direction: str
    after_setting: int
    evidence: tuple[EvidenceRef, ...]
    opportunity_definition: str
    opportunities: tuple[EvidenceRef, ...]
    expected_effect: str
    validation_plan: str
    measurement_contract: MeasurementContract
    observation_window: ObservationWindow
    success_criteria: str
    rollback_threshold: str
    environment: EnvironmentInput
    overlap_classification: str
    supersedes: tuple[str, ...] = ()
    rolls_back: str | None = None
    reevaluation: str | None = None


def _text_problem(value: object, described: str, *, label: bool = False) -> str | None:
    """H-3: new public-safe policy text (the P5 summary rule), or a bounded public-safe label."""
    if label:
        problem = records.public_safe_problem(value, limit=records.P4_MAX_LABEL)
    else:
        problem = history.summary_problem(value)
    return None if problem is None else f"{described}: {problem}"


def request_record(request: object) -> dict[str, Any]:
    """The canonical record of a Policy Change request, refused before the lock when it is not representable."""
    if type(request) is not PolicyChangeRequest:
        raise stop(CODE_CANDIDATE_INVALID, f"a policy change request is a PolicyChangeRequest, not {type(request).__name__}")
    problems: list[str] = []
    for name in ("evidence", "opportunities", "supersedes"):
        if not isinstance(getattr(request, name), tuple):
            problems.append(f"{name} is not a tuple")
    if problems:
        raise stop(CODE_CANDIDATE_INVALID, "invalid policy change request: " + "; ".join(problems))
    for item in request.evidence + request.opportunities:
        if type(item) is not EvidenceRef:
            raise stop(CODE_CANDIDATE_INVALID, f"an evidence reference is {type(item).__name__}, not an EvidenceRef")
    for name, kind in (("measurement_contract", MeasurementContract), ("observation_window", ObservationWindow),
                       ("environment", EnvironmentInput)):
        if type(getattr(request, name)) is not kind:
            raise stop(CODE_CANDIDATE_INVALID, f"{name} is not a {kind.__name__}")
    record = {
        serialize.SCHEMA_KEY: SCHEMA_REQUEST, serialize.VERSION_KEY: RECORD_VERSION,
        "policy_surface_id": request.policy_surface_id, "direction": request.direction,
        "after_setting": request.after_setting,
        "evidence": [item.to_record() for item in request.evidence],
        "opportunity_definition": request.opportunity_definition,
        "opportunities": [item.to_record() for item in request.opportunities],
        "expected_effect": request.expected_effect, "validation_plan": request.validation_plan,
        "measurement_contract": request.measurement_contract.to_record(),
        "observation_window": request.observation_window.to_record(),
        "success_criteria": request.success_criteria, "rollback_threshold": request.rollback_threshold,
        "environment": request.environment.to_record(),
        "overlap_classification": request.overlap_classification,
        "supersedes": list(request.supersedes), "rolls_back": request.rolls_back, "reevaluation": request.reevaluation,
    }
    problems = request_problems(record)
    if problems:
        code, message = problems[0]
        raise stop(code, "invalid policy change request: " + message)
    return serialize.canonical_data(record)


def request_problems(record: Mapping[str, Any]) -> list[tuple[str, str]]:
    """The structural refusals of a request record, before any Project state is read - coded, never a crash."""
    try:
        return _request_problems(record)
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        return [(CODE_CANDIDATE_INVALID, f"the policy change request is malformed ({type(exc).__name__}: {exc})")]


def _request_problems(record: Mapping[str, Any]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if not isinstance(record, Mapping) or set(record) != set(REQUEST_FIELDS):
        return [(CODE_CANDIDATE_INVALID, "the request does not hold exactly the policy change request fields")]
    for name, fields in (("measurement_contract", MEASUREMENT_FIELDS), ("observation_window", WINDOW_FIELDS),
                         ("environment", ENVIRONMENT_INPUT_FIELDS)):
        if not isinstance(record[name], Mapping) or set(record[name]) != set(fields):
            return [(CODE_CANDIDATE_INVALID, f"the request's {name} does not hold exactly {', '.join(fields)}")]
    for name in ("evidence", "opportunities", "supersedes"):
        if not isinstance(record[name], list):
            return [(CODE_CANDIDATE_INVALID, f"the request's {name} is not a list")]
    for name in ("evidence", "opportunities"):
        if any(not isinstance(item, Mapping) or set(item) != set(EVIDENCE_FIELDS) for item in record[name]):
            return [(CODE_EVIDENCE_INVALID, f"a {name} reference is not exactly {{family, id, digest}}")]
    for name in ("reviewers", "check_adapters", "dependencies"):
        if not isinstance(record["environment"][name], list):
            return [(CODE_CANDIDATE_INVALID, f"the request's environment {name} is not a list")]
    surface = surface_problem(record["policy_surface_id"])
    if surface is not None:
        return [surface]
    if record["direction"] not in CHANGE_DIRECTIONS:
        found.append((CODE_DIRECTION_INVALID, f"direction {record['direction']!r} is not one of {CHANGE_DIRECTIONS}"))
    if not SURFACE_BY_ID[record["policy_surface_id"]].in_range(record["after_setting"]):
        found.append((CODE_SETTING_INVALID, f"after_setting {record['after_setting']!r} is outside the allowed range"))
    for name in ("evidence", "opportunities"):
        for index, item in enumerate(record[name]):
            for problem in evidence_ref_problems(item, f"{name} {index}"):
                found.append((CODE_EVIDENCE_INVALID, problem))
    keys = [(item["family"], item["id"]) for item in record["evidence"]]
    if len(keys) != len(set(keys)):
        found.append((CODE_DUPLICATE_EVIDENCE, "the evidence names one source twice; a duplicate is never a second "
                                               "opportunity"))
    if keys != sorted(keys):
        found.append((CODE_CANDIDATE_INVALID, "the evidence is not sorted by (family, id)"))
    opportunity_keys = [(item["family"], item["id"]) for item in record["opportunities"]]
    if len(opportunity_keys) != len(set(opportunity_keys)):
        found.append((CODE_DUPLICATE_EVIDENCE, "the Relevant Opportunity set names one source twice"))
    if opportunity_keys != sorted(opportunity_keys):
        found.append((CODE_CANDIDATE_INVALID, "the Relevant Opportunity set is not sorted by (family, id)"))
    named = {(item["family"], item["id"], item["digest"]) for item in record["evidence"]}
    if any((item["family"], item["id"], item["digest"]) not in named for item in record["opportunities"]):
        found.append((CODE_EVIDENCE_INVALID, "a Relevant Opportunity is not among the evidence references"))
    for name in ("opportunity_definition", "expected_effect", "validation_plan", "success_criteria",
                 "rollback_threshold"):
        problem = _text_problem(record[name], name)
        if problem:
            found.append((CODE_CANDIDATE_INVALID, problem))
    contract = record["measurement_contract"]
    for problem in (_text_problem(contract["version"], "measurement_contract version", label=True),
                    _text_problem(contract["metric"], "measurement_contract metric")):
        if problem:
            found.append((CODE_CANDIDATE_INVALID, problem))
    if type(contract["continued_observation_permitted"]) is not bool:
        found.append((CODE_CANDIDATE_INVALID, "measurement_contract continued_observation_permitted is not a boolean"))
    window = record["observation_window"]
    low, high = window["minimum_opportunities"], window["maximum_opportunities"]
    if type(low) is not int or type(high) is not int or low < 1 or high < low:
        found.append((CODE_CANDIDATE_INVALID, "observation_window is not 1 <= minimum <= maximum opportunities"))
    environment = record["environment"]
    if not environment["reviewers"]:
        found.append((CODE_CANDIDATE_INVALID, "the environment names no reviewer identity/version"))
    for name in ("reviewers", "check_adapters", "dependencies"):
        for item in environment[name]:
            problem = _text_problem(item, f"environment {name}", label=True)
            if problem:
                found.append((CODE_CANDIDATE_INVALID, problem))
    problem = _text_problem(environment["toolchain"], "environment toolchain", label=True)
    if problem:
        found.append((CODE_CANDIDATE_INVALID, problem))
    if record["overlap_classification"] not in OVERLAP_CLASSES:
        found.append((CODE_CANDIDATE_INVALID, f"overlap classification {record['overlap_classification']!r} is not one "
                                              f"of {OVERLAP_CLASSES}"))
    supersedes = record["supersedes"]
    if any(not isinstance(item, str) or not is_valid_id(item, "review_policy_change") for item in supersedes) \
            or supersedes != sorted(set(supersedes)):
        found.append((CODE_CANDIDATE_INVALID, "supersedes is not a sorted duplicate-free list of policy change ids"))
    rolls_back = record["rolls_back"]
    if (rolls_back is None) != (record["direction"] != DIRECTION_ROLLBACK):
        found.append((CODE_DIRECTION_INVALID, "rolls_back names the change a rollback restores, and only a rollback "
                                              "names one"))
    if rolls_back is not None and (not isinstance(rolls_back, str) or not is_valid_id(rolls_back, "review_policy_change")):
        found.append((CODE_CANDIDATE_INVALID, "rolls_back is not a policy change id"))
    reevaluation = record["reevaluation"]
    if (reevaluation is None) != (record["direction"] != DIRECTION_TEMPORARY_GUARD):
        found.append((CODE_GUARD_INVALID, "a temporary_guard carries its reevaluation / expiry criteria, and nothing "
                                          "else carries them"))
    if reevaluation is not None:
        problem = _text_problem(reevaluation, "reevaluation")
        if problem:
            found.append((CODE_GUARD_INVALID, problem))
    return found


def request_digest(record: Mapping[str, Any]) -> str:
    return serialize.digest(dict(record))


# --------------------------------------------------------------------------- the PolicyChangeCandidate (§15.14, §30.8)

CANDIDATE_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "policy_change_id", "target_identity", "request_digest",
    "before_profile", "before_effective_policy_digest", "global_baseline_digest", "after_profile",
    "affected_policy_surface", "strength_class", "direction", "before_setting", "after_setting", "evidence",
    "relevant_opportunity", "expected_effect", "validation_plan", "measurement_contract", "observation_window",
    "success_criteria", "rollback_threshold", "environment_identity", "overlap", "rollback_unit", "holdout_plan",
    "reevaluation", "supersedes", "rolls_back",
)


def expected_after_profile(state: PolicyState, policy_change_id: str, surface: PolicySurface, after_setting: int,
                           keep_refs: Iterable[str]) -> ProjectProfile:
    """The complete after Profile a change computes: the before Profile with only the affected override changed."""
    before = state.profile
    overrides = [dict(item) for item in (() if before is None else before.overrides)
                 if item["policy_surface_id"] != surface.policy_surface_id]
    global_setting = state.baseline.global_setting(surface.policy_surface_id)
    if after_setting != global_setting:
        overrides.append({
            "policy_surface_id": surface.policy_surface_id, "strength_class": surface.strength_class,
            "setting": after_setting,
            "direction": DIRECTION_STRENGTHEN if after_setting > global_setting else DIRECTION_LIGHTEN,
            "supporting_policy_change_id": policy_change_id,
        })
    overrides.sort(key=lambda item: item["policy_surface_id"])
    refs = sorted(set(keep_refs) | {policy_change_id})
    return ProjectProfile(
        profile_version=1 if before is None else before.profile_version + 1,
        parent_profile_digest=None if before is None else before.digest,
        global_baseline_digest=state.baseline.digest,
        global_baseline_version=state.baseline.version,
        loader_semantics_identity=LOADER_SEMANTICS_IDENTITY,
        overrides=tuple(overrides),
        active_experiment_refs=tuple(refs),
    )


def build_candidate(request: Mapping[str, Any], policy_change_id: str, state: PolicyState,
                    reader: Any) -> dict[str, Any]:
    """The normalized PolicyChangeCandidate of ``request`` (canonical record), built after ``policy_change_id``
    is reserved: the proposed Profile binds it (§30.16)."""
    surface = require_surface(request["policy_surface_id"])
    before_setting = setting(state.effective, surface.policy_surface_id)
    after_setting = int(request["after_setting"])
    removed = set(request["supersedes"])
    if request["rolls_back"] is not None:
        removed.add(str(request["rolls_back"]))
    keep = [item.policy_change_id for item in state.active if item.policy_change_id not in removed]
    after = expected_after_profile(state, policy_change_id, surface, after_setting, keep)
    holdout = None
    if after_setting < before_setting:
        holdout = {"policy_surface_id": surface.policy_surface_id, "holdout_setting": before_setting,
                   "selection": HOLDOUT_SELECTION_ALL_RELEVANT}
    environment = {
        "global_baseline_digest": state.baseline.digest,
        "profile_version": state.profile_version,
        "profile_digest": state.profile_digest,
        "measurement_contract_version": request["measurement_contract"]["version"],
        **dict(request["environment"]),
    }
    overlapping = [item.policy_change_id for item in state.active
                   if item.policy_change_id not in removed and item.policy_surface_id == surface.policy_surface_id]
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_CANDIDATE,
        serialize.VERSION_KEY: RECORD_VERSION,
        "policy_change_id": policy_change_id,
        "target_identity": TARGET_IDENTITY,
        "request_digest": request_digest(request),
        "before_profile": {"profile_version": state.profile_version, "digest": state.profile_digest},
        "before_effective_policy_digest": state.effective_hash,
        "global_baseline_digest": state.baseline.digest,
        "after_profile": after.to_record(),
        "affected_policy_surface": surface.policy_surface_id,
        "strength_class": surface.strength_class,
        "direction": request["direction"],
        "before_setting": before_setting,
        "after_setting": after_setting,
        "evidence": [dict(item) for item in request["evidence"]],
        "relevant_opportunity": {"definition": request["opportunity_definition"],
                                 "opportunities": [dict(item) for item in request["opportunities"]]},
        "expected_effect": request["expected_effect"],
        "validation_plan": request["validation_plan"],
        "measurement_contract": dict(request["measurement_contract"]),
        "observation_window": dict(request["observation_window"]),
        "success_criteria": request["success_criteria"],
        "rollback_threshold": request["rollback_threshold"],
        "environment_identity": environment,
        "overlap": {
            "classification": request["overlap_classification"],
            "active_experiment_refs": sorted(item.policy_change_id for item in state.active),
            "overlapping_refs": sorted(overlapping),
        },
        "rollback_unit": {"policy_surface_id": surface.policy_surface_id, "restore_setting": before_setting,
                          "profile_version": after.profile_version},
        "holdout_plan": holdout,
        "reevaluation": request["reevaluation"],
        "supersedes": list(request["supersedes"]),
        "rolls_back": request["rolls_back"],
    })


def candidate_hash(candidate: Mapping[str, Any]) -> str:
    return serialize.digest(dict(candidate))


def classify_overlap(policy_surface_id: str, active: Iterable[ActiveExperiment]) -> str:
    """The fixed overlap classifier (§15.25): one surface is known_overlap; the two v1 surfaces are disjoint."""
    return OVERLAP_KNOWN if any(item.policy_surface_id == policy_surface_id for item in active) else OVERLAP_PROVEN_DISJOINT


#: The bound environment identities a Candidate adds to the caller's environment (§15.26, §30.25).
ENVIRONMENT_BOUND_FIELDS = ("global_baseline_digest", "profile_version", "profile_digest", "measurement_contract_version")
#: The exact field set of every mapping a Candidate carries (RB6B-M8).
_CANDIDATE_MAPPINGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("before_profile", ("profile_version", "digest")),
    ("relevant_opportunity", ("definition", "opportunities")),
    ("measurement_contract", MEASUREMENT_FIELDS),
    ("observation_window", WINDOW_FIELDS),
    ("environment_identity", ENVIRONMENT_BOUND_FIELDS + ENVIRONMENT_INPUT_FIELDS),
    ("overlap", ("classification", "active_experiment_refs", "overlapping_refs")),
    ("rollback_unit", ("policy_surface_id", "restore_setting", "profile_version")),
)
HOLDOUT_PLAN_FIELDS = ("policy_surface_id", "holdout_setting", "selection")


def request_of_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """The Policy Change request a Candidate states, re-derived from the Candidate's own fields (RB6B-M8)."""
    environment = candidate["environment_identity"]
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_REQUEST, serialize.VERSION_KEY: RECORD_VERSION,
        "policy_surface_id": candidate["affected_policy_surface"], "direction": candidate["direction"],
        "after_setting": candidate["after_setting"],
        "evidence": [dict(item) for item in candidate["evidence"]],
        "opportunity_definition": candidate["relevant_opportunity"]["definition"],
        "opportunities": [dict(item) for item in candidate["relevant_opportunity"]["opportunities"]],
        "expected_effect": candidate["expected_effect"], "validation_plan": candidate["validation_plan"],
        "measurement_contract": dict(candidate["measurement_contract"]),
        "observation_window": dict(candidate["observation_window"]),
        "success_criteria": candidate["success_criteria"], "rollback_threshold": candidate["rollback_threshold"],
        "environment": {key: environment[key] for key in ENVIRONMENT_INPUT_FIELDS},
        "overlap_classification": candidate["overlap"]["classification"],
        "supersedes": list(candidate["supersedes"]), "rolls_back": candidate["rolls_back"],
        "reevaluation": candidate["reevaluation"],
    })


def _candidate_shape_problems(candidate: object) -> list[tuple[str, str]]:
    """Every structural defect of a Candidate, coded - so no later rule ever indexes a malformed field (RB6B-M8)."""
    if not isinstance(candidate, Mapping) or set(candidate) != set(CANDIDATE_FIELDS) \
            or candidate.get(serialize.SCHEMA_KEY) != SCHEMA_CANDIDATE \
            or candidate.get(serialize.VERSION_KEY) != RECORD_VERSION:
        return [(CODE_CANDIDATE_INVALID, "the Candidate does not hold exactly the PolicyChangeCandidate fields")]
    found: list[tuple[str, str]] = []
    for name, fields in _CANDIDATE_MAPPINGS:
        value = candidate[name]
        if not isinstance(value, Mapping) or set(value) != set(fields):
            found.append((CODE_CANDIDATE_INVALID, f"the Candidate's {name} does not hold exactly {', '.join(fields)}"))
    if not isinstance(candidate["after_profile"], Mapping):
        found.append((CODE_FORBIDDEN_CHANGE, "the Candidate's after Profile is not a Profile record"))
    plan = candidate["holdout_plan"]
    if plan is not None and (not isinstance(plan, Mapping) or set(plan) != set(HOLDOUT_PLAN_FIELDS)):
        found.append((CODE_LIGHTENING_UNMEASURED, "the Candidate's holdout plan is not exactly "
                                                  f"{', '.join(HOLDOUT_PLAN_FIELDS)}"))
    for name in ("evidence", "supersedes"):
        if not isinstance(candidate[name], list):
            found.append((CODE_CANDIDATE_INVALID, f"the Candidate's {name} is not a list"))
    if found:
        return found
    if not isinstance(candidate["relevant_opportunity"]["opportunities"], list):
        found.append((CODE_CANDIDATE_INVALID, "the Candidate's Relevant Opportunity set is not a list"))
    for name in ("active_experiment_refs", "overlapping_refs"):
        if not isinstance(candidate["overlap"][name], list):
            found.append((CODE_CANDIDATE_INVALID, f"the Candidate's overlap {name} is not a list"))
    for name in ("reviewers", "check_adapters", "dependencies"):
        if not isinstance(candidate["environment_identity"][name], list):
            found.append((CODE_CANDIDATE_INVALID, f"the Candidate's environment {name} is not a list"))
    if found:
        return found
    for item in list(candidate["evidence"]) + list(candidate["relevant_opportunity"]["opportunities"]):
        if not isinstance(item, Mapping) or set(item) != set(EVIDENCE_FIELDS):
            return [(CODE_EVIDENCE_INVALID, "an evidence reference of the Candidate is not exactly {family, id, digest}")]
    return []


def candidate_problems(candidate: Mapping[str, Any], state: PolicyState, reader: Any) -> list[tuple[str, str]]:
    """The fixed mechanical meta-verifier (§15.19, §30.14): every violation, whatever any reviewer said.

    It checks evidence provenance and the Relevant Opportunity basis, the
    affected surface identity, the strength class and the allowed range, that no
    forbidden correctness or authority change is carried, the lightening
    measurement contract, the experiment overlap state, the environment
    attribution, the exact rollback unit, the normalized before / after
    semantics, and that the persisted-projection adapter can read the after
    Profile. The candidate policy never weakens the rules authorizing it: every
    rule here is a fixed meta-rule, never a Profile setting.

    Self-contained (RB6B-M8): it re-derives the request from the Candidate's
    own fields, holds it to every structural and H-3 rule
    (:func:`request_problems`) and to the Candidate's ``request_digest``, and
    returns a coded problem for every malformed field - never an exception.
    """
    found = _candidate_shape_problems(candidate)
    if found:
        return found
    try:
        return _candidate_problems(candidate, state, reader)
    except (KeyError, TypeError, AttributeError, ValueError, IndexError) as exc:
        return [(CODE_CANDIDATE_INVALID, f"the Candidate is malformed ({type(exc).__name__}: {exc})")]


def _rollback_problems(candidate: Mapping[str, Any], state: PolicyState, reader: Any, surface: PolicySurface,
                       before_setting: int, after_setting: int) -> list[tuple[str, str]]:
    """A rollback restores exactly the change that governs the surface now (RB6B-L4)."""
    target = candidate["rolls_back"]
    governing = {item.policy_change_id: item for item in state.active}.get(str(target)) if isinstance(target, str) \
        else None
    if governing is None or governing.policy_surface_id != surface.policy_surface_id:
        return [(CODE_DIRECTION_INVALID, f"the rollback names {target}, which is not an active experiment on "
                                         f"{surface.policy_surface_id}; a rollback restores the change that governs "
                                         "the surface, never an earlier or settled one")]
    try:
        restored = reader.read_policy_change(str(target))
    except (ValidationError, KeyError, TypeError, AttributeError) as exc:
        return [(CODE_DIRECTION_INVALID, f"the rollback target {target} does not read ({exc})")]
    found: list[tuple[str, str]] = []
    if restored["affected_policy_surface"] != surface.policy_surface_id or restored["before_setting"] != after_setting \
            or restored["after_setting"] != before_setting:
        found.append((CODE_DIRECTION_INVALID, f"the rollback does not restore exactly the setting {target} replaced on "
                                              "the same surface"))
    override = None if state.profile is None else state.profile.override_of(surface.policy_surface_id)
    if override is not None and override["supporting_policy_change_id"] != target:
        found.append((CODE_DIRECTION_INVALID, f"the current override of {surface.policy_surface_id} is supported by "
                                              f"{override['supporting_policy_change_id']}, not {target}"))
    return found


def _candidate_problems(candidate: Mapping[str, Any], state: PolicyState, reader: Any) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if candidate["target_identity"] != TARGET_IDENTITY or not isinstance(candidate["policy_change_id"], str) \
            or not is_valid_id(candidate["policy_change_id"], "review_policy_change"):
        found.append((CODE_CANDIDATE_INVALID, "the Candidate is not a project-policy Candidate with a policy change id"))
    surface_issue = surface_problem(candidate["affected_policy_surface"])
    if surface_issue is not None:
        return found + [surface_issue]
    surface = SURFACE_BY_ID[candidate["affected_policy_surface"]]
    # RB6B-M8: the request the Candidate states, held to every request rule and to the digest it binds - so a
    # Receipt never seals a Candidate its change record would refuse
    stated = request_of_candidate(candidate)
    found.extend(request_problems(stated))
    if request_digest(stated) != candidate["request_digest"]:
        found.append((CODE_CANDIDATE_INVALID, "the Candidate's request_digest is not the digest of the request its own "
                                              "fields state"))
    if candidate["strength_class"] != surface.strength_class:
        found.append((CODE_RECLASSIFIED, f"the Candidate classifies {surface.policy_surface_id} as "
                                         f"{candidate['strength_class']!r}; the fixed class is {surface.strength_class}"))
    # before state: exact, current, compatible
    if candidate["before_profile"] != {"profile_version": state.profile_version, "digest": state.profile_digest}:
        found.append((CODE_BEFORE_STATE_CONFLICT, "the Candidate's before Profile is not the current Profile (or its "
                                                  "explicit absence)"))
    if candidate["before_effective_policy_digest"] != state.effective_hash:
        found.append((CODE_BEFORE_STATE_CONFLICT, "the Candidate's before Effective Policy is not the current one"))
    if candidate["global_baseline_digest"] != state.baseline.digest:
        found.append((CODE_PROFILE_INCOMPATIBLE, "the Candidate binds another Global baseline than the current one"))
    before_setting, after_setting = candidate["before_setting"], candidate["after_setting"]
    if before_setting != setting(state.effective, surface.policy_surface_id):
        found.append((CODE_BEFORE_STATE_CONFLICT, "the Candidate's before setting is not the effective setting"))
    if not surface.in_range(after_setting):
        found.append((CODE_SETTING_INVALID, f"after setting {after_setting!r} is outside {surface.minimum}.."
                                            f"{surface.maximum}"))
        return found
    direction = candidate["direction"]
    active_by_id = {item.policy_change_id: item for item in state.active}
    supersedes = [str(ref) for ref in candidate["supersedes"]]
    # RB6B-H1: the one Candidate that keeps the setting is a strengthen superseding an active temporary_guard at that
    # setting - the normal repeated-evidence path that makes a guard permanent (§15.15)
    confirms_guard = direction == DIRECTION_STRENGTHEN and after_setting == before_setting and any(
        ref in active_by_id and active_by_id[ref].direction == DIRECTION_TEMPORARY_GUARD
        and active_by_id[ref].policy_surface_id == surface.policy_surface_id for ref in supersedes)
    if after_setting == before_setting and not confirms_guard:
        found.append((CODE_DIRECTION_INVALID, "the Candidate changes no setting; only a strengthen superseding an active "
                                              "temporary_guard at its setting keeps it"))
    if direction in (DIRECTION_STRENGTHEN, DIRECTION_TEMPORARY_GUARD) and not after_setting > before_setting \
            and not confirms_guard:
        found.append((CODE_DIRECTION_INVALID if direction == DIRECTION_STRENGTHEN else CODE_GUARD_INVALID,
                      f"a {direction} moves the setting upward in the strength order"))
    if direction == DIRECTION_LIGHTEN and not after_setting < before_setting:
        found.append((CODE_DIRECTION_INVALID, "a lighten moves the setting downward"))
    if direction == DIRECTION_TEMPORARY_GUARD and candidate["reevaluation"] is None:
        found.append((CODE_GUARD_INVALID, "a temporary_guard carries explicit reevaluation / expiry criteria"))
    if direction == DIRECTION_ROLLBACK:
        found.extend(_rollback_problems(candidate, state, reader, surface, before_setting, after_setting))
    # lightening: the stronger pre-change behaviour stays an independent all_relevant holdout (§30.10)
    expected_holdout = None if after_setting >= before_setting else {
        "policy_surface_id": surface.policy_surface_id, "holdout_setting": before_setting,
        "selection": HOLDOUT_SELECTION_ALL_RELEVANT}
    if candidate["holdout_plan"] != expected_holdout:
        found.append((CODE_LIGHTENING_UNMEASURED,
                      "a downward change freezes the pre-change stronger behaviour as an all_relevant holdout and an "
                      "upward one carries none; the change never weakens the channel that measures it"))
    # evidence provenance and the Relevant Opportunity basis (§30.9, §30.31)
    evidence = list(candidate["evidence"])
    keys = [(item.get("family"), item.get("id")) for item in evidence]
    if len(keys) != len(set(keys)):
        found.append((CODE_DUPLICATE_EVIDENCE, "the Candidate names one evidence source twice"))
    for index, item in enumerate(evidence):
        for problem in evidence_ref_problems(item, f"evidence {index}"):
            found.append((CODE_EVIDENCE_INVALID, problem))
    if not evidence:
        found.append((CODE_SINGLE_EVENT, "the Candidate names no evidence; raw run count is never evidence"))
    opportunities = list(candidate["relevant_opportunity"]["opportunities"])
    identities: set[str] = set()
    serious = False
    for item in evidence:
        if evidence_ref_problems(item, "evidence"):
            continue
        try:
            stored = stored_evidence_digest(reader, item)
        except (ValidationError, KeyError, TypeError, AttributeError) as exc:
            found.append((CODE_EVIDENCE_INVALID, f"evidence {item['family']}/{item['id']} is not stored or does not "
                                                 f"read ({exc})"))
            continue
        if stored != item["digest"]:
            found.append((CODE_EVIDENCE_INVALID, f"evidence {item['family']}/{item['id']} digests to {stored}, not "
                                                 f"{item['digest']}"))
            continue
        if item in opportunities:
            try:
                identity = opportunity(reader, item, surface.policy_surface_id)
            except (ValidationError, KeyError, TypeError, AttributeError):
                identity = None
            if identity is not None:
                identities.add(identity)
                serious = serious or serious_escape(reader, item)
    if any(item not in evidence for item in opportunities):
        found.append((CODE_EVIDENCE_INVALID, "a Relevant Opportunity is not among the evidence"))
    floor = {DIRECTION_STRENGTHEN: SINGLE_EVENT_FLOOR, DIRECTION_LIGHTEN: SINGLE_EVENT_FLOOR,
             DIRECTION_ADJUST: SINGLE_EVENT_FLOOR, DIRECTION_TEMPORARY_GUARD: 1, DIRECTION_ROLLBACK: 0}.get(direction, 1)
    if len(identities) < floor:
        found.append((CODE_SINGLE_EVENT,
                      f"a {direction} needs at least {floor} distinct relevant opportunities that exercised "
                      f"{surface.policy_surface_id}, and the evidence proves {len(identities)}; one event never makes a "
                      "permanent adaptation"))
    # RB6B-L3: a temporary_guard originates from one SERIOUS SUPPORTED ESCAPE, not from any one opportunity
    if direction == DIRECTION_TEMPORARY_GUARD and not serious:
        found.append((CODE_GUARD_INVALID, "a temporary_guard originates from one serious supported escape: a supported "
                                          "downstream_escape / repair_induced relation or a supported HIGH / MID "
                                          "Problem Finding among its Relevant Opportunities"))
    # the normalized before / after semantics: nothing but the affected override and the experiment refs changes
    rolls_back = candidate["rolls_back"]
    removed = set(supersedes) | ({str(rolls_back)} if rolls_back else set())
    unknown = sorted(set(supersedes) - set(active_by_id))
    if unknown:
        found.append((CODE_OVERLAP_UNRESOLVED, f"the Candidate supersedes {unknown}, which are not active experiments"))
    # RB6B-M1: supersede resolves an overlap on the Candidate's OWN surface; another surface's experiment is disjoint
    # and is never ended by this Candidate (that would drop its measuring channel)
    foreign = sorted(ref for ref in supersedes
                     if ref in active_by_id and active_by_id[ref].policy_surface_id != surface.policy_surface_id)
    if foreign:
        found.append((CODE_OVERLAP_UNRESOLVED, f"the Candidate supersedes {foreign}, experiments on another surface; "
                                               "only an overlapping experiment on its own surface is superseded"))
    # a lightening experiment this Candidate ends keeps its measuring channel unless the Candidate restores at least
    # the behaviour that channel measures; otherwise the lightening must be settled first (serialize)
    for ref in sorted(removed):
        ended = active_by_id.get(ref)
        if ended is not None and ended.holdout_setting is not None and after_setting < ended.holdout_setting:
            found.append((CODE_LIGHTENING_UNMEASURED,
                          f"the Candidate ends lightening experiment {ref} and keeps the setting below its holdout "
                          f"setting {ended.holdout_setting}; a lightened behaviour never stays without the channel "
                          "that measures it - settle that experiment first"))
    keep = [item.policy_change_id for item in state.active if item.policy_change_id not in removed]
    expected = expected_after_profile(state, str(candidate["policy_change_id"]), surface, int(after_setting), keep)
    if candidate["after_profile"] != expected.to_record():
        found.append((CODE_FORBIDDEN_CHANGE, "the proposed after Profile changes more than the affected surface's "
                                             "override and its own experiment reference; correctness and authority "
                                             "never change through a Policy Change"))
    try:
        ProjectProfile.from_record(dict(candidate["after_profile"]), "the proposed after Profile")
    except ValidationError as exc:
        found.append((CODE_FORBIDDEN_CHANGE, f"the proposed after Profile is not a canonical Profile: {exc}"))
    # overlap (§15.25): only proven_disjoint observes concurrently
    remaining = [item for item in state.active if item.policy_change_id not in removed]
    computed = classify_overlap(surface.policy_surface_id, remaining)
    declared = candidate["overlap"]["classification"]
    if declared not in OVERLAP_CLASSES or _OVERLAP_STRICTNESS[declared] < _OVERLAP_STRICTNESS[computed]:
        found.append((CODE_OVERLAP_UNRESOLVED, f"the Candidate declares {declared!r}, weaker than the fixed classifier's "
                                               f"{computed}"))
    elif declared != OVERLAP_PROVEN_DISJOINT and remaining:
        found.append((CODE_OVERLAP_UNRESOLVED, f"{declared}: an overlapping experiment must serialize, be explicitly "
                                               "superseded or be combined into one compound Candidate; it never "
                                               "observes concurrently"))
    if candidate["overlap"] != {"classification": declared, "active_experiment_refs": sorted(active_by_id),
                                "overlapping_refs": sorted(item.policy_change_id for item in remaining
                                                           if item.policy_surface_id == surface.policy_surface_id)}:
        found.append((CODE_OVERLAP_UNRESOLVED, "the Candidate's overlap record is not the fixed classifier's view"))
    # environment attribution and the exact rollback unit
    environment = candidate["environment_identity"]
    if (environment["global_baseline_digest"], environment["profile_version"], environment["profile_digest"],
            environment["measurement_contract_version"]) != (
            state.baseline.digest, state.profile_version, state.profile_digest,
            candidate["measurement_contract"]["version"]):
        found.append((CODE_ENVIRONMENT_UNATTRIBUTED, "the Candidate's environment identity does not bind the current "
                                                     "baseline, Profile and measurement contract"))
    if candidate["rollback_unit"] != {"policy_surface_id": surface.policy_surface_id, "restore_setting": before_setting,
                                      "profile_version": expected.profile_version}:
        found.append((CODE_CANDIDATE_INVALID, "the rollback unit is not exactly the affected surface's pre-change setting"))
    return found


def require_candidate(candidate: Mapping[str, Any], state: PolicyState, reader: Any) -> None:
    problems = candidate_problems(candidate, state, reader)
    if problems:
        code, message = problems[0]
        raise stop(code, f"the PolicyChangeCandidate is refused by the fixed meta-verifier: {message}"
                         + (f" (and {len(problems) - 1} more)" if len(problems) > 1 else ""))


# --------------------------------------------------------------------------- the immutable change record (§30.19)

CHANGE_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "policy_change_id", "candidate_hash", "review_run_id", "receipt_id",
    "before_profile_version", "before_profile_digest", "after_profile_version", "after_profile_digest",
    "global_baseline_digest", "affected_policy_surface", "strength_class", "direction", "before_setting",
    "after_setting", "evidence", "measurement_contract", "observation_window", "success_criteria",
    "rollback_threshold", "rollback_unit", "environment_identity", "overlap_classification", "holdout_plan",
    "reevaluation", "expected_effect_summary", "global_baseline",
)


def change_record(candidate: Mapping[str, Any], *, review_run_id: str, receipt_id: str,
                  baseline_record: Mapping[str, Any]) -> dict[str, Any]:
    """The immutable change record of an authorized Candidate, built from it exactly (§30.19).

    It also binds the complete normalized baseline record the Candidate was
    reviewed under (§30.19 "at least"; R6-2 item 3): its digest is the
    Candidate's, so the baseline a Profile was written under is recovered from
    immutable evidence, never guessed.
    """
    if serialize.digest(dict(baseline_record)) != candidate["global_baseline_digest"]:
        raise _invalid("the baseline record is not the one the Candidate was reviewed under")
    after = ProjectProfile.from_record(dict(candidate["after_profile"]), "the after Profile")
    record = serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_CHANGE, serialize.VERSION_KEY: RECORD_VERSION,
        "policy_change_id": candidate["policy_change_id"], "candidate_hash": candidate_hash(candidate),
        "review_run_id": review_run_id, "receipt_id": receipt_id,
        "before_profile_version": candidate["before_profile"]["profile_version"],
        "before_profile_digest": candidate["before_profile"]["digest"],
        "after_profile_version": after.profile_version, "after_profile_digest": after.digest,
        "global_baseline_digest": candidate["global_baseline_digest"],
        "affected_policy_surface": candidate["affected_policy_surface"],
        "strength_class": candidate["strength_class"], "direction": candidate["direction"],
        "before_setting": candidate["before_setting"], "after_setting": candidate["after_setting"],
        "evidence": [dict(item) for item in candidate["evidence"]],
        "measurement_contract": dict(candidate["measurement_contract"]),
        "observation_window": dict(candidate["observation_window"]),
        "success_criteria": candidate["success_criteria"], "rollback_threshold": candidate["rollback_threshold"],
        "rollback_unit": dict(candidate["rollback_unit"]),
        "environment_identity": dict(candidate["environment_identity"]),
        "overlap_classification": candidate["overlap"]["classification"],
        "holdout_plan": None if candidate["holdout_plan"] is None else dict(candidate["holdout_plan"]),
        "reevaluation": candidate["reevaluation"],
        "expected_effect_summary": candidate["expected_effect"],
        "global_baseline": dict(baseline_record),
    })
    parse_change(record, "the policy change record")
    return record


def parse_change(record: object, described: str) -> dict[str, Any]:
    """A stored change record, strictly (schema, fields, identities, H-3 text)."""
    found = records._require_mapping(record, described)
    serialize.require_schema(found, SCHEMA_CHANGE, RECORD_VERSION, described)
    records._require_exact_fields(found, CHANGE_FIELDS, described)
    records._require_id(found, "policy_change_id", "review_policy_change", described)
    records._require_digest(found, "candidate_hash", described)
    records._require_id(found, "review_run_id", "review_run", described)
    records._require_id(found, "receipt_id", "review_receipt", described)
    before_version, before_digest = found["before_profile_version"], found["before_profile_digest"]
    if (before_version is None) != (before_digest is None):
        raise _invalid(f"{described} names a before Profile version without its digest, or the reverse")
    if before_version is not None:
        records._require_int(found, "before_profile_version", described, minimum=1)
        records._require_digest(found, "before_profile_digest", described)
    after_version = records._require_int(found, "after_profile_version", described, minimum=1)
    if after_version != (1 if before_version is None else before_version + 1):
        raise _invalid(f"{described} skips a Profile version", code="review_record_invalid")
    records._require_digest(found, "after_profile_digest", described)
    records._require_digest(found, "global_baseline_digest", described)
    problems = baseline_record_problems(found["global_baseline"], f"{described} global_baseline")
    if problems:
        raise _invalid(problems[0])
    if serialize.digest(found["global_baseline"]) != found["global_baseline_digest"]:
        raise _invalid(f"{described} binds a baseline record that does not digest to its global_baseline_digest")
    surface = SURFACE_BY_ID.get(found["affected_policy_surface"])
    if surface is None or found["strength_class"] != surface.strength_class:
        raise _invalid(f"{described} names no registered surface with its fixed class")
    if found["direction"] not in CHANGE_DIRECTIONS:
        raise _invalid(f"{described} direction is not a change direction")
    if not surface.in_range(found["before_setting"]) or not surface.in_range(found["after_setting"]):
        raise _invalid(f"{described} settings are outside the surface range")
    for index, item in enumerate(records._require_list(found, "evidence", described)):
        problems = evidence_ref_problems(item, f"{described} evidence {index}")
        if problems:
            raise _invalid(problems[0])
    for name in ("success_criteria", "rollback_threshold", "expected_effect_summary"):
        problem = history.summary_problem(found[name])
        if problem is not None:
            raise _invalid(f"{described} {name} is not public-safe text: {problem}")
    if found["reevaluation"] is not None and history.summary_problem(found["reevaluation"]) is not None:
        raise _invalid(f"{described} reevaluation is not public-safe text")
    if found["overlap_classification"] not in OVERLAP_CLASSES:
        raise _invalid(f"{described} overlap classification is not one of {OVERLAP_CLASSES}")
    plan = found["holdout_plan"]
    if plan is not None:
        plan = records._require_mapping(plan, f"{described} holdout_plan")
        records._require_exact_fields(plan, ("policy_surface_id", "holdout_setting", "selection"),
                                      f"{described} holdout_plan")
        if plan["policy_surface_id"] != surface.policy_surface_id or plan["selection"] != HOLDOUT_SELECTION_ALL_RELEVANT \
                or plan["holdout_setting"] != found["before_setting"] or not found["after_setting"] < found["before_setting"]:
            raise _invalid(f"{described} holdout plan is not the pre-change setting of its own lightening")
    elif found["after_setting"] < found["before_setting"]:
        raise _invalid(f"{described} lightens without a holdout plan")
    return serialize.canonical_data(found)


# --------------------------------------------------------------------------- evaluations (§15.24, §30.23-§30.25)

EVALUATION_REQUEST_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "policy_change_id", "result", "evidence", "environment",
    "environment_basis", "environment_basis_digest", "rationale", "next_action",
)
EVALUATION_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "evaluation_id", "policy_change_id", "evaluated_profile_version",
    "evaluated_profile_digest", "measurement_contract", "evidence", "environment_identity", "environment_basis",
    "environment_basis_digest", "result", "rationale_summary", "next_action",
)


@dataclass(frozen=True)
class PolicyEvaluationRequest:
    """One observation evaluation of an applied Policy Change: evidence, never a Profile mutation."""

    policy_change_id: str
    result: str
    evidence: tuple[EvidenceRef, ...]
    environment: EnvironmentInput
    rationale: str
    next_action: str
    environment_basis: str | None = None
    environment_basis_digest: str | None = None


def evaluation_request_record(request: object) -> dict[str, Any]:
    if type(request) is not PolicyEvaluationRequest:
        raise stop(CODE_EVALUATION_INVALID, f"an evaluation request is a PolicyEvaluationRequest, not "
                                            f"{type(request).__name__}")
    if not isinstance(request.evidence, tuple) or any(type(item) is not EvidenceRef for item in request.evidence) \
            or type(request.environment) is not EnvironmentInput:
        raise stop(CODE_EVALUATION_INVALID, "an evaluation request carries EvidenceRef evidence and an EnvironmentInput")
    record = serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_EVALUATION_REQUEST, serialize.VERSION_KEY: RECORD_VERSION,
        "policy_change_id": request.policy_change_id, "result": request.result,
        "evidence": [item.to_record() for item in request.evidence], "environment": request.environment.to_record(),
        "environment_basis": request.environment_basis, "environment_basis_digest": request.environment_basis_digest,
        "rationale": request.rationale, "next_action": request.next_action,
    })
    problems: list[str] = []
    if not isinstance(record["policy_change_id"], str) or not is_valid_id(record["policy_change_id"],
                                                                          "review_policy_change"):
        problems.append("policy_change_id is not a policy change id")
    if record["result"] not in EVALUATION_RESULTS:
        problems.append(f"result {record['result']!r} is not one of {EVALUATION_RESULTS}")
    if record["next_action"] not in NEXT_ACTIONS:
        problems.append(f"next_action {record['next_action']!r} is not one of {NEXT_ACTIONS}")
    for index, item in enumerate(record["evidence"]):
        problems.extend(evidence_ref_problems(item, f"evidence {index}"))
    keys = [(item["family"], item["id"]) for item in record["evidence"]]
    if keys != sorted(set(keys)):
        problems.append("the evidence is not sorted and duplicate-free")
    if record["environment_basis"] not in (None,) + ENVIRONMENT_BASES:
        problems.append("environment_basis is not window_split or irrelevance_proof")
    if (record["environment_basis"] is None) != (record["environment_basis_digest"] is None):
        problems.append("an environment basis carries its evidence digest, and only a basis does")
    if record["environment_basis_digest"] is not None and (
            not isinstance(record["environment_basis_digest"], str)
            or records.DIGEST_RE.match(record["environment_basis_digest"]) is None):
        problems.append("environment_basis_digest is not a digest")
    problem = history.summary_problem(record["rationale"])
    if problem is not None:
        problems.append(f"rationale: {problem}")
    if problems:
        raise stop(CODE_EVALUATION_INVALID, "invalid policy evaluation request: " + "; ".join(problems))
    return record


def evaluation_record(request: Mapping[str, Any], evaluation_id: str, state: PolicyState, reader: Any) -> dict[str, Any]:
    """The immutable evaluation record of ``request`` against the current Profile, or a STOP (§30.23-§30.25)."""
    change_id = str(request["policy_change_id"])
    if state.profile is None or change_id not in {item.policy_change_id for item in state.active}:
        raise stop(CODE_EVALUATION_INVALID, f"{change_id} is not an active experiment of the current Profile; a settled "
                                            "or unknown experiment is not evaluated")
    change = reader.read_policy_change(change_id)
    result, next_action = request["result"], request["next_action"]
    allowed = {
        RESULT_RETAIN: (NEXT_END_OBSERVATION,),
        RESULT_ADJUST: (NEXT_NEW_CANDIDATE,),
        RESULT_ROLLBACK: (NEXT_NEW_CANDIDATE,),
        RESULT_INCONCLUSIVE: ((NEXT_CONTINUE_OBSERVATION, NEXT_NEW_CANDIDATE)
                              if change["measurement_contract"]["continued_observation_permitted"]
                              else (NEXT_NEW_CANDIDATE,)),
    }[result]
    if next_action not in allowed:
        raise stop(CODE_EVALUATION_INVALID,
                   f"a {result} evaluation's next action is {' or '.join(allowed)}, not {next_action}; inconclusive is "
                   "never success, and adjust / rollback need a new reviewed Candidate")
    # The observed environment: the current baseline and Profile, the frozen measurement contract, and the caller's
    # reviewer / adapter / toolchain / dependency identities. The Profile moves by the change itself, so it is bound
    # but not material; every other identity is compared with the change's frozen environment.
    environment = {
        "global_baseline_digest": state.baseline.digest,
        "profile_version": state.profile.profile_version,
        "profile_digest": state.profile.digest,
        "measurement_contract_version": change["measurement_contract"]["version"],
        **dict(request["environment"]),
    }
    material_change = _material_change(change["environment_identity"], environment)
    if material_change and request["environment_basis"] is None and result != RESULT_INCONCLUSIVE:
        raise stop(CODE_ENVIRONMENT_UNATTRIBUTED,
                   f"the material environment changed during the observation window ({', '.join(material_change)}); "
                   "without a window split or a positive irrelevance proof the result is inconclusive - chronology is "
                   "never causality")
    for item in request["evidence"]:
        try:
            stored = stored_evidence_digest(reader, item)
        except (ValidationError, KeyError, TypeError, AttributeError) as exc:
            raise stop(CODE_EVIDENCE_INVALID, f"evidence {item['family']}/{item['id']} is not stored ({exc})") from exc
        if stored != item["digest"]:
            raise stop(CODE_EVIDENCE_INVALID, f"evidence {item['family']}/{item['id']} digests to {stored}")
    # RB6B-L10: the positive environment basis is one of this evaluation's stored evidence references, by digest
    basis_digest = request["environment_basis_digest"]
    if basis_digest is not None and basis_digest not in {item["digest"] for item in request["evidence"]}:
        raise stop(CODE_ENVIRONMENT_UNATTRIBUTED,
                   "the environment basis (window split / positive irrelevance proof) is one of the evaluation's stored "
                   "evidence references, named by its digest; an arbitrary digest proves nothing")
    # RB6B-H1: retain ends observation only after the frozen minimum of opportunities observed under the change; a
    # temporary_guard never ends observation into permanence
    if result == RESULT_RETAIN:
        problem = retain_problem(reader, change, request["evidence"])
        if problem is not None:
            raise stop(CODE_GUARD_INVALID if change["direction"] == DIRECTION_TEMPORARY_GUARD else CODE_EVALUATION_INVALID,
                       problem)
    record = serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_EVALUATION, serialize.VERSION_KEY: RECORD_VERSION,
        "evaluation_id": evaluation_id, "policy_change_id": change_id,
        "evaluated_profile_version": state.profile.profile_version, "evaluated_profile_digest": state.profile.digest,
        "measurement_contract": dict(change["measurement_contract"]),
        "evidence": [dict(item) for item in request["evidence"]], "environment_identity": environment,
        "environment_basis": request["environment_basis"],
        "environment_basis_digest": request["environment_basis_digest"],
        "result": result, "rationale_summary": request["rationale"], "next_action": next_action,
    })
    parse_evaluation(record, "the policy evaluation record")
    return record


def _material_change(frozen: Mapping[str, Any], observed: Mapping[str, Any]) -> list[str]:
    """The material environment identities that differ between the change's frozen and the observed environment."""
    keys = ("global_baseline_digest", "measurement_contract_version", "reviewers", "check_adapters", "toolchain",
            "dependencies")
    return [key for key in keys if frozen.get(key) != observed.get(key)]


def parse_evaluation(record: object, described: str) -> dict[str, Any]:
    found = records._require_mapping(record, described)
    serialize.require_schema(found, SCHEMA_EVALUATION, RECORD_VERSION, described)
    records._require_exact_fields(found, EVALUATION_FIELDS, described)
    records._require_id(found, "evaluation_id", "review_policy_evaluation", described)
    records._require_id(found, "policy_change_id", "review_policy_change", described)
    records._require_int(found, "evaluated_profile_version", described, minimum=1)
    records._require_digest(found, "evaluated_profile_digest", described)
    if found["result"] not in EVALUATION_RESULTS or found["next_action"] not in NEXT_ACTIONS:
        raise _invalid(f"{described} result or next action is not in the fixed vocabulary")
    if (found["result"] == RESULT_RETAIN) != (found["next_action"] == NEXT_END_OBSERVATION):
        raise _invalid(f"{described}: only retain ends an observation")
    if found["result"] in (RESULT_ADJUST, RESULT_ROLLBACK) and found["next_action"] != NEXT_NEW_CANDIDATE:
        raise _invalid(f"{described}: adjust and rollback need a new reviewed Candidate")
    if found["environment_basis"] not in (None,) + ENVIRONMENT_BASES:
        raise _invalid(f"{described} environment basis is not in the fixed vocabulary")
    if (found["environment_basis"] is None) != (found["environment_basis_digest"] is None):
        raise _invalid(f"{described} environment basis and its digest disagree")
    for index, item in enumerate(records._require_list(found, "evidence", described)):
        problems = evidence_ref_problems(item, f"{described} evidence {index}")
        if problems:
            raise _invalid(problems[0])
    if found["environment_basis_digest"] is not None \
            and found["environment_basis_digest"] not in {item["digest"] for item in found["evidence"]}:
        raise _invalid(f"{described} environment basis is not one of its evidence references")
    problem = history.summary_problem(found["rationale_summary"])
    if problem is not None:
        raise _invalid(f"{described} rationale is not public-safe text: {problem}")
    return serialize.canonical_data(found)


# --------------------------------------------------------------------------- the Policy Review kind adapter (§30.12-§30.14)

def operation_identity(request_digest_value: str) -> str:
    return f"{OPERATION}:{request_digest_value}"


def context_record(workline_root: Path, baseline: GlobalPolicyBaseline) -> dict[str, Any]:
    """The Policy Review Context: the kind, contract, adapter, loader and the exact baseline it reviews against."""
    from ..implementation import package_directory
    from . import planning

    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_CONTEXT, serialize.VERSION_KEY: RECORD_VERSION,
        "review_kind": REVIEW_KIND, "contract": POLICY_CHANGE_CONTRACT, "adapter_identity": ADAPTER_IDENTITY,
        "projection_semantics_version": PROJECTION_SEMANTICS_VERSION,
        "loader_identity": planning.loader_identity(package_directory(workline_root)),
        "loader_semantics_identity": LOADER_SEMANTICS_IDENTITY,
        "global_baseline_digest": baseline.digest,
        "authority": [dict(item) for item in baseline.record["root_authority_digests"]],
        "meta_rules_digest": meta_rules_digest(),
    })


def snapshot_for(candidate: Mapping[str, Any]) -> records.CandidateSnapshot:
    """The P1 Candidate snapshot (snapshot mode) carrying the normalized Candidate as its material."""
    return records.CandidateSnapshot(
        candidate_hash=candidate_hash(candidate), reconstruction_mode=records.RECONSTRUCTION_SNAPSHOT,
        projection_semantics_version=PROJECTION_SEMANTICS_VERSION, material=dict(candidate), builder=None,
    )


def requirement(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """The decided requirement a Policy Review is adjudicated against: the fixed meta-rules and the exact before state."""
    from . import p4

    return p4.requirement_record(REVIEW_KIND, {
        "meta_rules_digest": meta_rules_digest(),
        "global_baseline_digest": candidate["global_baseline_digest"],
        "before_profile": dict(candidate["before_profile"]),
        "request_digest": candidate["request_digest"],
    })


def evidence_record(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """The Evidence a Policy Review binds: the exact P5 references the Candidate names, by digest."""
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_EVIDENCE, serialize.VERSION_KEY: RECORD_VERSION,
        "evidence": [dict(item) for item in candidate["evidence"]],
    })


def discovery_slots_problem(effective: Mapping[str, Any], required: Sequence[Any], holdout: Sequence[Any]) -> tuple[str, str] | None:
    """Whether bound discovery actors satisfy the Effective Policy (§30.2 A, §30.11, R6-1).

    ``required`` / ``holdout`` are DiscoveryBindings. ``required_slots`` N needs
    N required bindings over N distinct reviewer identity/version pairs; an
    active lightening experiment's holdout needs exactly its holdout slots,
    each an identity/version pair distinct from every required one. Holdout
    bindings no experiment selects are refused, never silently ignored.
    """
    needed = setting(effective, SURFACE_REQUIRED_SLOTS)
    pairs = {(binding.identity, binding.version) for binding in required}
    if len(required) < needed or len(pairs) < needed:
        return CODE_DISCOVERY_SLOTS_UNMET, (
            f"the Effective Policy requires {needed} discovery slot(s) bound to distinct reviewer identity/version "
            f"pairs, and the invocation binds {len(required)} over {len(pairs)} distinct pair(s)")
    wanted = required_holdout_slots(effective)
    if wanted and len(holdout) != wanted:
        return CODE_HOLDOUT_UNBOUND, (
            f"an active lightening experiment freezes {wanted} discovery holdout slot(s) as its independent measurement "
            f"channel, and the invocation binds {len(holdout)}; a lightened policy never runs without it")
    if not wanted and holdout:
        return CODE_HOLDOUT_NOT_APPLICABLE, "no active experiment selects a discovery holdout for this Run"
    viewpoints = [binding.viewpoint for binding in required] + [binding.viewpoint for binding in holdout]
    if len(viewpoints) != len(set(viewpoints)):
        return CODE_HOLDOUT_UNBOUND, "a holdout slot shares its viewpoint with another discovery slot"
    if any((binding.identity, binding.version) in pairs for binding in holdout) \
            or len({(binding.identity, binding.version) for binding in holdout}) != len(holdout):
        return CODE_HOLDOUT_UNBOUND, ("a holdout slot is bound to a reviewer identity/version that already serves "
                                      "another slot, so it is not independent measurement")
    return None


# --------------------------------------------------------------------------- the persisted-policy projection (§30.21-§30.22)

def normalized_projection(profile: ProjectProfile, global_settings: Mapping[str, int]) -> dict[str, Any]:
    """The semantic projection the PersistedProjectionAdapter compares: the Profile as the canonical loader reads it."""
    return serialize.canonical_data({
        "profile_version": profile.profile_version,
        "parent_profile_digest": profile.parent_profile_digest,
        "global_baseline_digest": profile.global_baseline_digest,
        "global_baseline_version": profile.global_baseline_version,
        "loader_semantics_identity": profile.loader_semantics_identity,
        "settings": {surface.policy_surface_id: (profile.setting_of(surface.policy_surface_id)
                                                 if profile.setting_of(surface.policy_surface_id) is not None
                                                 else int(global_settings[surface.policy_surface_id]))
                     for surface in SURFACES},
        "overrides": [dict(item) for item in profile.overrides],
        "active_experiment_refs": list(profile.active_experiment_refs),
    })


def projection_hash(profile: ProjectProfile, global_settings: Mapping[str, int]) -> str:
    return serialize.digest(normalized_projection(profile, global_settings))


def persisted_projection_problem(reviewed_after: Mapping[str, Any], persisted_raw: bytes | None,
                                 global_settings: Mapping[str, int]) -> str | None:
    """The PersistedProjectionAdapter (§30.22): ``None`` exactly when the committed bytes are the reviewed Profile.

    Both halves are required: the exact recorded bytes (no alternate byte shape
    is silently adopted), and the canonical loader's semantic round trip (no
    byte-equivalent-but-semantically-different Profile is accepted).
    """
    if persisted_raw is None:
        return "the committed tree holds no Project Profile"
    reviewed = ProjectProfile.from_record(dict(reviewed_after), "the reviewed after Profile")
    if persisted_raw != reviewed.text().encode("utf-8"):
        return "the committed Profile bytes are not the exact reviewed canonical bytes"
    try:
        loaded, _ = parse_profile_bytes(persisted_raw, "the committed Project Profile")
    except ValidationError as exc:
        return f"the committed Profile does not load canonically: {exc}"
    if normalized_projection(loaded, global_settings) != normalized_projection(reviewed, global_settings):
        return "the committed Profile does not round-trip to the reviewed after-state"
    return None


def adapter_identity() -> str:
    return ADAPTER_IDENTITY


# --------------------------------------------------------------------------- lineage / namespace validation (§30.30)

def lineage_problems(profile: ProjectProfile | None, changes: Mapping[str, Mapping[str, Any]]) -> list[tuple[str, str]]:
    """The Profile lineage proven from immutable change records: v1 from absence, then +1 with the exact parent.

    Every applied change record forms one chain from absence to the current
    Profile; a fork, a skipped version or a Profile no change produced is a
    validation Problem. A Project with no Profile and no change is valid.
    """
    found: list[tuple[str, str]] = []
    by_after: dict[int, Mapping[str, Any]] = {}
    for change_id, change in sorted(changes.items()):
        version = int(change["after_profile_version"])
        if version in by_after:
            found.append((CODE_LINEAGE_INVALID, f"two policy changes ({by_after[version]['policy_change_id']} and "
                                                f"{change_id}) produce Profile version {version}"))
            continue
        by_after[version] = change
    if profile is None:
        if by_after:
            found.append((CODE_LINEAGE_INVALID, "policy change records exist and the Project Profile is absent"))
        return found
    current = by_after.get(profile.profile_version)
    if current is None or current["after_profile_digest"] != profile.digest:
        found.append((CODE_LINEAGE_INVALID, f"no applied policy change produced the current Profile version "
                                            f"{profile.profile_version}"))
    if current is not None and current["before_profile_digest"] != profile.parent_profile_digest:
        found.append((CODE_LINEAGE_INVALID, "the Profile's parent digest is not the before Profile of the change that "
                                            "produced it"))
    for version in range(1, profile.profile_version + 1):
        change = by_after.get(version)
        if change is None:
            found.append((CODE_LINEAGE_INVALID, f"no applied policy change produced Profile version {version}"))
            continue
        previous = by_after.get(version - 1)
        expected_parent = None if version == 1 else (None if previous is None else previous["after_profile_digest"])
        if change["before_profile_digest"] != expected_parent:
            found.append((CODE_LINEAGE_INVALID, f"Profile version {version}'s change does not start from version "
                                                f"{version - 1}"))
    if max(by_after, default=0) > profile.profile_version:
        found.append((CODE_LINEAGE_INVALID, "a policy change produced a later Profile version than the current one"))
    for item in profile.overrides:
        if str(item["supporting_policy_change_id"]) not in changes:
            found.append((CODE_LINEAGE_INVALID, f"override of {item['policy_surface_id']} names policy change "
                                                f"{item['supporting_policy_change_id']}, which is not stored"))
    for ref in profile.active_experiment_refs:
        if ref not in changes:
            found.append((CODE_LINEAGE_INVALID, f"active experiment {ref} names no stored policy change"))
    return found


def policy_problems(reader: Any, workline_root: Path | None) -> list[tuple[str, str]]:
    """Normative P6 Review validation (§30.30): Profile, change and evaluation validity; absence is valid.

    Malformed or (when the Workline root is known) incompatible canonical
    Profile is a validation Problem. Shadow authority is never one.
    """
    found: list[tuple[str, str]] = []
    changes: dict[str, Mapping[str, Any]] = {}
    try:
        change_ids = reader.policy_change_ids()
    except ValidationError as exc:
        return [(exc.code or CODE_PROFILE_INVALID, str(exc))]
    for change_id in change_ids:
        try:
            changes[change_id] = reader.read_policy_change(change_id)
        except ValidationError as exc:
            found.append((exc.code or "review_record_invalid", str(exc)))
    evaluations: dict[str, Mapping[str, Any]] = {}
    try:
        evaluation_ids = reader.policy_evaluation_ids()
    except ValidationError as exc:
        return found + [(exc.code or "review_record_invalid", str(exc))]
    for evaluation_id in evaluation_ids:
        try:
            evaluations[evaluation_id] = reader.read_policy_evaluation(evaluation_id)
        except ValidationError as exc:
            found.append((exc.code or "review_record_invalid", str(exc)))
    for evaluation_id, evaluation in sorted(evaluations.items()):
        if str(evaluation["policy_change_id"]) not in changes:
            found.append((CODE_EVALUATION_INVALID, f"evaluation {evaluation_id} evaluates "
                                                   f"{evaluation['policy_change_id']}, which is not stored"))
        elif evaluation["next_action"] == NEXT_END_OBSERVATION:
            problem = retain_problem(reader, changes[str(evaluation["policy_change_id"])], evaluation["evidence"])
            if problem is not None:
                found.append((CODE_EVALUATION_INVALID, f"evaluation {evaluation_id} ends an observation it may not end "
                                                       f"(it settles nothing): {problem}"))
    try:
        profile = reader.read_profile()
    except ValidationError as exc:
        return found + [(exc.code or CODE_PROFILE_INVALID, f"the canonical Project Profile is malformed: {exc}")]
    found.extend(lineage_problems(profile, changes))
    if profile is not None and workline_root is not None:
        try:
            baseline = load_global_baseline(workline_root)
        except StopError as exc:
            return found + [(exc.code, str(exc))]
        problem = compatibility_problem(profile, baseline, reader)
        if problem is not None:
            found.append((CODE_PROFILE_INCOMPATIBLE, f"the canonical Project Profile is incompatible: {problem} "
                                                     "(policy maintenance / reconcile)"))
    return found
