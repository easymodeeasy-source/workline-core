"""Canonical Review paths, and the proof that a write to one stays inside the Project.

Two things live here because they are the same question asked twice: *which*
path a Review record belongs at, and *whether the bytes written there actually
land inside this Project*.

The second is ``R1`` §9. Immediately before a Review create is applied, the
writer walks from the Project root down to the target's parent and proves, with
no-follow semantics, that every component that already exists is a plain
in-Project directory. A symlink, a junction, any other reparse point, or a
component whose identity cannot be established is refused. The parent's identity
is then taken again at the create boundary and compared, so a component swapped
between the walk and the write cannot redirect Review bytes out of the Project.

This is a positive proof, not a search for something suspicious: a component
that cannot be shown to be an ordinary directory is refused, which is the
opposite of refusing only what is recognisably wrong.

P7 (§31.4 / §31.50): the Project namespace is one of two described Review
namespaces (:mod:`workline.review.namespace`). Every public name here is the
PROJECT descriptor's value or delegates to it, byte for byte and refusal for
refusal, so nothing that reads a Project's Review records changes; the root
policy Review namespace is reached only through its own descriptor.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import ValidationError
from ..ids import is_valid_id
from ..store import WORKLINE_DIR

from . import namespace as _namespace

_PROJECT = _namespace.PROJECT_REVIEW_NAMESPACE

#: The one canonical Review namespace, created lazily on first Review write.
#: A Project that never uses Review keeps exactly the shape it has today.
REVIEW_DIR = _PROJECT.root

GATES_DIR = _PROJECT.gates_dir
RECEIPTS_DIR = _PROJECT.receipts_dir
CONSUMPTIONS_DIR = _PROJECT.consumptions_dir
SUPERSESSIONS_DIR = _PROJECT.supersessions_dir
CANDIDATE_SNAPSHOTS_DIR = _PROJECT.candidate_snapshots_dir
TASK_INPUTS_DIR = _PROJECT.task_inputs_dir
ACTIVATION_DIR = _PROJECT.activation_dir
#: The P4 record areas (§12.22 / §27.5): raw discovery reports, adjudications, Repair Batches and Results.
REPORTS_DIR = _PROJECT.reports_dir
ADJUDICATIONS_DIR = _PROJECT.adjudications_dir
REPAIR_BATCHES_DIR = _PROJECT.repair_batches_dir
REPAIR_RESULTS_DIR = _PROJECT.repair_results_dir
#: The P5 durable history namespace (§13.3 / §28.3): immutable create-only record families, each one level
#: below it, and nothing else - no index, no cache, no mutable "current history" file. P5 defines five; RB5 adds
#: the sixth, ``achievements`` (§14.18 / §32.32): Phase completion and Roadmap achievement evidence, which is
#: audit evidence and never lifecycle truth. The families are declared once, by the PROJECT descriptor
#: (:mod:`workline.review.namespace`); these names are its re-exports.
HISTORY_DIR = _PROJECT.history_dir
HISTORY_RUNS = _namespace.HISTORY_RUNS
HISTORY_FINDINGS = _namespace.HISTORY_FINDINGS
HISTORY_REPAIRS = _namespace.HISTORY_REPAIRS
HISTORY_RELATIONS = _namespace.HISTORY_RELATIONS
HISTORY_HUMAN_DECISIONS = _namespace.HISTORY_HUMAN_DECISIONS
HISTORY_ACHIEVEMENTS = _namespace.HISTORY_ACHIEVEMENTS
HISTORY_FAMILIES = _namespace.HISTORY_FAMILIES
#: The identity kind a history record of each family is named by (§28.4): Run / Finding / Repair history
#: reuses its immutable source record's stable ID; relations, Human Decision Evidence and achievement evidence
#: (§32.32, reserved through ``Mutation.reserve_id``) allocate one.
HISTORY_FAMILY_KINDS = _namespace.HISTORY_FAMILY_KINDS

#: The P6 Project-local Review policy namespace (§15.23 / §30.17): the one mutable canonical Profile, written only
#: by the dedicated Profile CAS effect of the ``project-policy-change`` owner, and two immutable create-only
#: evidence families one level below it. Nothing else lives here - no index, no cache, no free-form configuration.
POLICY_DIR = _PROJECT.policy_dir
POLICY_PROFILE_NAME = _namespace.POLICY_PROFILE_NAME
POLICY_PROFILE_REL = _PROJECT.policy_profile_rel
POLICY_CHANGES = _namespace.POLICY_CHANGES
POLICY_EVALUATIONS = _namespace.POLICY_EVALUATIONS
POLICY_FAMILIES = _namespace.POLICY_FAMILIES
#: The identity kind a policy evidence record of each family is named by (§30.16).
POLICY_FAMILY_KINDS = _namespace.POLICY_FAMILY_KINDS

#: The ephemeral Review area. Never canonical truth, never evidence, never the
#: only material an accepted task can be reconstructed from (``R1`` §3).
RUNTIME_REVIEW_DIR = f"{WORKLINE_DIR}/runtime/review"

#: Scratch directories the committed-result loader materializes a commit's canonical Project files into.
RUNTIME_PROOFS_DIR = f"{RUNTIME_REVIEW_DIR}/proofs"
#: The runtime copies of reviewer reports, read only to return findings after a resume.
RUNTIME_REPORTS_DIR = f"{RUNTIME_REVIEW_DIR}/reports"
#: The Workline-owned empty directory the planning commit primitive names as ``core.hooksPath``.
RUNTIME_NO_HOOKS_DIR = f"{RUNTIME_REVIEW_DIR}/no-hooks"
#: The Workline-owned empty file a hermetic (class B) Git invocation names as ``GIT_CONFIG_GLOBAL``,
#: so no global configuration takes part in it (``F3`` §7.1.9).
RUNTIME_NO_CONFIG_FILE = f"{RUNTIME_REVIEW_DIR}/no-config"
#: Throw-away bare directories the committed attribute evaluation runs in.
RUNTIME_ATTR_EVAL_DIR = f"{RUNTIME_REVIEW_DIR}/attr-eval"
#: Throw-away repositories the Work attribute-pin capability probe measures in (``F3`` §7.7).
#: A probe repository is created under a fresh name here and removed again; nothing in it is
#: this Project's repository, index, worktree or refs.
RUNTIME_ATTR_PROBE_DIR = f"{RUNTIME_REVIEW_DIR}/attr-probe"
#: Throw-away repositories the resulting tree of a frozen Candidate is composed in (``F3`` §7.9.2).
#: The composition borrows this Project's objects read-only and writes its own; the tree it builds
#: exists before K1 does, and nothing in it is this Project's repository, index, worktree or refs.
RUNTIME_RESULTING_TREE_DIR = f"{RUNTIME_REVIEW_DIR}/resulting-tree"
#: The isolated index files a ``review-v1-work-local-v2`` commit is built in (``F3`` §7.1.2 O-1). One per
#: recorded commit effect, created fresh and discarded again; never the repository's real index, and a
#: partially built one is never reused across an attempt or a resume.
RUNTIME_WORK_INDEX_DIR = f"{RUNTIME_REVIEW_DIR}/work-index"
#: The isolated verification workspaces of a frozen Work Candidate (``F2`` §13.4 V-2, IP-6): a scratch
#: repository borrowing this Project's objects read-only, and the workspace it materializes. Never
#: canonical, never authorization, removed once the verification has read it back.
RUNTIME_WORK_VERIFY_DIR = f"{RUNTIME_REVIEW_DIR}/work-verify"


def runtime_report_rel(review_task_id: str) -> str:
    """The runtime report copy of ``review_task_id``: never authority, never settlement material."""
    _require_id(review_task_id, "review_task")
    return f"{RUNTIME_REPORTS_DIR}/{review_task_id}.yaml"

WORK_TERMINAL_ACTIVATION_REL = f"{ACTIVATION_DIR}/work-terminal-v1.yaml"

#: The directories a Review namespace may hold, and nothing else (the PROJECT descriptor's, in canonical order;
#: P6 §30.17 appended ``policy`` after P5's history).
REVIEW_SUBDIRS = _PROJECT.subdirs

#: Gate generation files are zero-padded to this width.
GENERATION_WIDTH = _namespace.GENERATION_WIDTH

#: The scope-only same-run serialization token (``R2`` §4 / ``R3`` §2). No file
#: is ever created at this path, it is never committed, and it is never Review
#: truth. It exists so that an unfinished generation mutation for a Review Run
#: mechanically overlaps any later attempt for the same run - including the case
#: where the physical generation file already appeared before its ``applied``
#: flag was saved, and a new invocation would otherwise compute N+2.
SERIALIZATION_TOKEN = _namespace.SERIALIZATION_TOKEN

#: ``000001.yaml`` for generation 1, and the generation a gate filename names (``R2`` §6): the one implementation.
generation_name = _namespace.generation_name
generation_of_name = _namespace.generation_of_name


def run_dir(review_run_id: str) -> str:
    return _PROJECT.run_dir(review_run_id)


def gate_rel(review_run_id: str, generation: int) -> str:
    return _PROJECT.gate_rel(review_run_id, generation)


def serialization_token_rel(review_run_id: str) -> str:
    """The scope-only token path for ``review_run_id``. Nothing is ever written here."""
    return _PROJECT.serialization_token_rel(review_run_id)


def receipt_rel(receipt_id: str) -> str:
    return _PROJECT.receipt_rel(receipt_id)


def consumption_rel(consumption_id: str) -> str:
    return _PROJECT.consumption_rel(consumption_id)


def supersession_rel(superseded_receipt_id: str) -> str:
    return _PROJECT.supersession_rel(superseded_receipt_id)


def candidate_snapshot_rel(candidate_hash: str) -> str:
    return _PROJECT.candidate_snapshot_rel(candidate_hash)


def task_input_rel(review_task_id: str) -> str:
    return _PROJECT.task_input_rel(review_task_id)


def report_rel(result_digest: str) -> str:
    """A P4 raw discovery report, named by its own canonical digest (the settled ``result_digest``)."""
    return _PROJECT.report_rel(result_digest)


def adjudication_rel(review_run_id: str) -> str:
    """The one P4 adjudication of ``review_run_id``."""
    return _PROJECT.adjudication_rel(review_run_id)


def repair_batch_rel(repair_batch_id: str) -> str:
    return _PROJECT.repair_batch_rel(repair_batch_id)


def repair_result_rel(repair_batch_id: str) -> str:
    """The Repair Result of ``repair_batch_id``: one batch, at most one result."""
    return _PROJECT.repair_result_rel(repair_batch_id)


def history_family_dir(family: str) -> str:
    """The directory of one P5 history record family."""
    return _PROJECT.history_family_dir(family)


def history_rel(family: str, identifier: str) -> str:
    """``history/<family>/<identifier>.yaml``, the identifier being of the family's own identity kind."""
    return _PROJECT.history_rel(family, identifier)


def history_run_rel(review_run_id: str) -> str:
    """The one Run summary of ``review_run_id``."""
    return history_rel(HISTORY_RUNS, review_run_id)


def history_finding_rel(finding_id: str) -> str:
    """The one Finding summary of the P4 Finding ``finding_id``."""
    return history_rel(HISTORY_FINDINGS, finding_id)


def history_repair_rel(repair_batch_id: str) -> str:
    """The one Repair summary of the P4 Repair Batch ``repair_batch_id``."""
    return history_rel(HISTORY_REPAIRS, repair_batch_id)


def history_relation_rel(relation_id: str) -> str:
    """One later / cross-run relation record."""
    return history_rel(HISTORY_RELATIONS, relation_id)


def history_decision_rel(decision_id: str) -> str:
    """One Human Decision Evidence record."""
    return history_rel(HISTORY_HUMAN_DECISIONS, decision_id)


def history_achievement_rel(achievement_evidence_id: str) -> str:
    """One Phase completion / Roadmap achievement evidence record (§14.18 / §32.32)."""
    return history_rel(HISTORY_ACHIEVEMENTS, achievement_evidence_id)


def policy_family_dir(family: str) -> str:
    """The directory of one P6 policy evidence family (``changes`` / ``evaluations``)."""
    return _PROJECT.policy_family_dir(family)


def policy_record_rel(family: str, identifier: str) -> str:
    """``policy/<family>/<identifier>.yaml``, the identifier being of the family's own identity kind."""
    return _PROJECT.policy_record_rel(family, identifier)


def policy_change_rel(policy_change_id: str) -> str:
    """The one immutable change record of the applied Policy Change ``policy_change_id``."""
    return policy_record_rel(POLICY_CHANGES, policy_change_id)


def policy_evaluation_rel(evaluation_id: str) -> str:
    """The one immutable observation evaluation ``evaluation_id``."""
    return policy_record_rel(POLICY_EVALUATIONS, evaluation_id)


def is_policy_profile_path(relative: object) -> bool:
    """Whether ``relative`` is exactly the canonical Project Profile path - and nothing that resembles it."""
    return _PROJECT.is_policy_profile_path(relative)


def require_policy_profile_path(relative: str) -> None:
    """Refuse every path but the exact canonical Project Profile (§15.27: only the exact path is authority)."""
    _PROJECT.require_policy_profile_path(relative)


def is_review_path(relative: str) -> bool:
    """Whether ``relative`` is inside the canonical Review namespace."""
    return _PROJECT.is_review_path(relative)


def _require_id(value: str, kind: str) -> None:
    if not is_valid_id(value, kind):
        raise ValidationError(f"not a {kind} id: {value!r}", code="review_record_invalid")


# --------------------------------------------------------------------------- record path shape


def require_review_record_path(relative: str) -> None:
    """Refuse ``relative`` unless it has the exact shape of a canonical Review record path.

    Structural only: which directory, how deep, a ``.yaml`` leaf, no traversal,
    no empty or dot component - ``gates/<run>/<generation>.yaml``, one flat
    level in every other record area, and the two-level P5 history
    (``history/<family>/<id>.yaml``, §28.3) and P6 policy evidence
    (``policy/<family>/<id>.yaml``, §30.17) areas; the mutable Profile is not a
    record this rule admits (§30.18). Whether the directories on the way are
    plain, in-Project directories is proven where the path is actually used -
    by a handle-bound, no-follow walk (:mod:`workline.review.fsafe`) - because a
    check on a path string, however careful, says nothing about what the path
    resolves to by the time it is opened. The PROJECT descriptor's rule
    (:meth:`workline.review.namespace.ReviewNamespace.require_record_path`).
    """
    _PROJECT.require_record_path(relative)


def require_review_readable_path(relative: str) -> None:
    """A path a Review reader may read: a canonical Review record, or the exact canonical Project Profile (P6).

    Reading only. The immutable create still admits record paths alone
    (:func:`require_review_record_path`), so the Profile is never created or
    replaced by anything but its dedicated compare-and-replace effect.
    """
    _PROJECT.require_readable_path(relative)
