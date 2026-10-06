"""Review namespace descriptors: where a Review lives, and the exact shape of a path inside it (§31.4 / §31.6).

A Review namespace is described, never discovered. Two immutable descriptors
exist, and nothing else names a Review root:

* :data:`PROJECT_REVIEW_NAMESPACE` - ``.workline/review`` of a Workline Project,
  byte-for-byte the layout :mod:`workline.review.paths` has always had, with the
  Project-only areas: P5 history, the P6 policy namespace and its Profile, the
  Work-terminal activation area, and the P4 Repair Batch / Result areas;
* :data:`ROOT_POLICY_REVIEW_NAMESPACE` - ``review-policy/review`` of the Workline
  root, where the Global Policy Change Review keeps its canonical P1-P4 records.
  It admits exactly the record areas the root contract uses (§31.6) and none of
  the Project-only ones: no history, no policy, no activation, no repair.

This module is pure: it reads, writes and resolves nothing. It answers *which*
path a record belongs at and whether a path string has the exact shape of one.
Whether the directories on the way are plain, contained directories is proven
where the path is used (:mod:`workline.review.fsafe`), and what a record means is
decided by the one shared reader and validator - a descriptor carries no record,
chain, Receipt or Consumption rule of its own.

The Workline root's own policy families (``global-policy.yaml``, Promotion
Packets, change and evaluation records, Patch Notes) live beside the root Review
namespace, not inside it (§16.3); :data:`ROOT_POLICY_LAYOUT` names them.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ValidationError
from ..ids import is_valid_id
from ..store import WORKLINE_DIR

#: The Project Review root (today's ``paths.REVIEW_DIR``).
PROJECT_REVIEW_ROOT = f"{WORKLINE_DIR}/review"
#: The Workline root's policy directory (§16.3) and the root Review root inside it (§31.4).
ROOT_POLICY_DIR = "review-policy"
ROOT_REVIEW_ROOT = f"{ROOT_POLICY_DIR}/review"

#: The two descriptor names.
PROJECT_NAMESPACE_NAME = "project"
ROOT_POLICY_NAMESPACE_NAME = "root-policy"

#: Gate generation files are zero-padded to this width.
GENERATION_WIDTH = 6

#: The scope-only same-run serialization token (``R2`` §4 / ``R3`` §2). No file is ever created at this path, it is
#: never committed, and it is never Review truth.
SERIALIZATION_TOKEN = ".generation-serialization"

#: The P5 durable history families (§13.3 / §28.3), Project only.
HISTORY_RUNS = "runs"
HISTORY_FINDINGS = "findings"
HISTORY_REPAIRS = "repairs"
HISTORY_RELATIONS = "relations"
HISTORY_HUMAN_DECISIONS = "human-decisions"
HISTORY_FAMILIES = (HISTORY_RUNS, HISTORY_FINDINGS, HISTORY_REPAIRS, HISTORY_RELATIONS, HISTORY_HUMAN_DECISIONS)
#: The identity kind a history record of each family is named by (§28.4).
HISTORY_FAMILY_KINDS = {
    HISTORY_RUNS: "review_run",
    HISTORY_FINDINGS: "review_finding",
    HISTORY_REPAIRS: "review_repair_batch",
    HISTORY_RELATIONS: "review_relation",
    HISTORY_HUMAN_DECISIONS: "review_decision",
}

#: The P6 Project-local policy namespace (§15.23 / §30.17), Project only: one mutable Profile and two immutable
#: create-only evidence families one level below it.
POLICY_PROFILE_NAME = "project-profile.yaml"
POLICY_CHANGES = "changes"
POLICY_EVALUATIONS = "evaluations"
POLICY_FAMILIES = (POLICY_CHANGES, POLICY_EVALUATIONS)
#: The identity kind a policy evidence record of each family is named by (§30.16).
POLICY_FAMILY_KINDS = {
    POLICY_CHANGES: "review_policy_change",
    POLICY_EVALUATIONS: "review_policy_evaluation",
}

#: Every Review subdirectory, in canonical order (today's ``paths.REVIEW_SUBDIRS``).
PROJECT_SUBDIRS = (
    "gates",
    "receipts",
    "consumptions",
    "supersessions",
    "candidate-snapshots",
    "task-inputs",
    "activation",
    "reports",
    "adjudications",
    "repair-batches",
    "repair-results",
    "history",
    "policy",
)
#: The root Review subdirectories (§31.6): the P1-P4 record areas the root contract uses. The root contract has no
#: Repair Batch, so it has no repair areas; it has no history, policy or activation area at all.
ROOT_SUBDIRS = (
    "gates",
    "receipts",
    "consumptions",
    "supersessions",
    "candidate-snapshots",
    "task-inputs",
    "reports",
    "adjudications",
)

#: The areas only a flag admits, and the subdirectories each one is.
_ACTIVATION_SUBDIRS = ("activation",)
_REPAIR_SUBDIRS = ("repair-batches", "repair-results")
_HISTORY_SUBDIRS = ("history",)
_POLICY_SUBDIRS = ("policy",)
#: The subdirectories whose records are not flat: gates are ``gates/<run>/<generation>.yaml``, history and policy
#: evidence are ``<area>/<family>/<id>.yaml``.
_NESTED_SUBDIRS = ("gates", "history", "policy")


def generation_name(generation: int) -> str:
    """``000001.yaml`` for generation 1. The filename is the generation, zero padded."""
    if type(generation) is not int or generation < 1:
        raise ValidationError(f"a Review generation is a positive integer, not {generation!r}", code="review_gate_chain")
    return f"{generation:0{GENERATION_WIDTH}d}.yaml"


def generation_of_name(name: str) -> int | None:
    """The generation a gate filename names, or ``None`` when it names none.

    Validated as an integer in its own right rather than through ``kind_of``: a
    generation is not an allocated identifier, and the padding is exact -
    ``1.yaml`` and ``0000001.yaml`` name nothing.
    """
    if not isinstance(name, str) or not name.endswith(".yaml"):
        return None
    stem = name[: -len(".yaml")]
    if len(stem) != GENERATION_WIDTH or not stem.isdigit() or not stem.isascii():
        return None
    value = int(stem)
    return value if value >= 1 else None


def _require_id(value: str, kind: str) -> None:
    if not is_valid_id(value, kind):
        raise ValidationError(f"not a {kind} id: {value!r}", code="review_record_invalid")


def _require_digest(value: str, described: str) -> None:
    from .records import DIGEST_RE

    if not isinstance(value, str) or DIGEST_RE.match(value) is None:
        raise ValidationError(f"{described} is not a lowercase hex SHA-256: {value!r}", code="review_record_invalid")


def _invalid(message: str) -> ValidationError:
    return ValidationError(message, code="review_namespace_invalid")


def _require_relative_root(root: object, described: str) -> None:
    """A descriptor root is a plain repository-relative POSIX path: no absolute, empty, dot or traversal component."""
    if not isinstance(root, str) or not root:
        raise _invalid(f"{described} root is not a repository-relative path: {root!r}")
    if root.startswith("/") or "\\" in root or ":" in root:
        raise _invalid(f"{described} root is not a repository-relative POSIX path: {root!r}")
    if any(part in ("", ".", "..") for part in root.split("/")):
        raise _invalid(f"{described} root holds an empty, dot or traversal component: {root!r}")


@dataclass(frozen=True)
class ReviewNamespace:
    """One canonical Review namespace: its root, its exact subdirectories, and the Project-only areas it admits.

    ``subdirs`` is exactly what the flags admit, in canonical order; a descriptor
    that says otherwise is refused at construction. A disabled area is refused
    with ``review_namespace_invalid`` wherever it would be named.
    """

    name: str
    root: str
    subdirs: tuple[str, ...]
    history: bool
    policy: bool
    activation: bool
    repairs: bool

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise _invalid(f"a Review namespace is named: {self.name!r}")
        for flag in ("history", "policy", "activation", "repairs"):
            if type(getattr(self, flag)) is not bool:
                raise _invalid(f"the {self.name} Review namespace flag {flag} is not a boolean")
        _require_relative_root(self.root, f"the {self.name} Review namespace")
        expected = tuple(subdir for subdir in PROJECT_SUBDIRS if self._admits(subdir))
        if type(self.subdirs) is not tuple or self.subdirs != expected:
            raise _invalid(
                f"the {self.name} Review namespace subdirectories {self.subdirs!r} are not exactly {expected!r}"
            )

    def _admits(self, subdir: str) -> bool:
        if subdir in _ACTIVATION_SUBDIRS:
            return self.activation
        if subdir in _REPAIR_SUBDIRS:
            return self.repairs
        if subdir in _HISTORY_SUBDIRS:
            return self.history
        if subdir in _POLICY_SUBDIRS:
            return self.policy
        return True

    # ------------------------------------------------------------------ directories

    def dir(self, subdir: str) -> str:
        """``<root>/<subdir>`` for one of this namespace's own subdirectories; any other is refused."""
        if subdir not in self.subdirs:
            raise _invalid(f"the {self.name} Review namespace has no {subdir!r} area")
        return f"{self.root}/{subdir}"

    @property
    def gates_dir(self) -> str:
        return self.dir("gates")

    @property
    def receipts_dir(self) -> str:
        return self.dir("receipts")

    @property
    def consumptions_dir(self) -> str:
        return self.dir("consumptions")

    @property
    def supersessions_dir(self) -> str:
        return self.dir("supersessions")

    @property
    def candidate_snapshots_dir(self) -> str:
        return self.dir("candidate-snapshots")

    @property
    def task_inputs_dir(self) -> str:
        return self.dir("task-inputs")

    @property
    def reports_dir(self) -> str:
        return self.dir("reports")

    @property
    def adjudications_dir(self) -> str:
        return self.dir("adjudications")

    @property
    def repair_batches_dir(self) -> str:
        """Repairs only."""
        return self.dir("repair-batches")

    @property
    def repair_results_dir(self) -> str:
        """Repairs only."""
        return self.dir("repair-results")

    @property
    def history_dir(self) -> str:
        """History only."""
        return self.dir("history")

    @property
    def policy_dir(self) -> str:
        """Policy only."""
        return self.dir("policy")

    @property
    def policy_profile_rel(self) -> str:
        """The one canonical Profile path. Policy only."""
        return f"{self.policy_dir}/{POLICY_PROFILE_NAME}"

    @property
    def activation_dir(self) -> str:
        """The Work-terminal activation area. Activation only."""
        return self.dir("activation")

    # ------------------------------------------------------------------ record paths

    def run_dir(self, review_run_id: str) -> str:
        _require_id(review_run_id, "review_run")
        return f"{self.gates_dir}/{review_run_id}"

    def gate_rel(self, review_run_id: str, generation: int) -> str:
        return f"{self.run_dir(review_run_id)}/{generation_name(generation)}"

    def serialization_token_rel(self, review_run_id: str) -> str:
        """The scope-only token path for ``review_run_id``. Nothing is ever written here."""
        return f"{self.run_dir(review_run_id)}/{SERIALIZATION_TOKEN}"

    def receipt_rel(self, receipt_id: str) -> str:
        _require_id(receipt_id, "review_receipt")
        return f"{self.receipts_dir}/{receipt_id}.yaml"

    def consumption_rel(self, consumption_id: str) -> str:
        _require_id(consumption_id, "review_consumption")
        return f"{self.consumptions_dir}/{consumption_id}.yaml"

    def supersession_rel(self, superseded_receipt_id: str) -> str:
        _require_id(superseded_receipt_id, "review_receipt")
        return f"{self.supersessions_dir}/{superseded_receipt_id}.yaml"

    def candidate_snapshot_rel(self, candidate_hash: str) -> str:
        _require_digest(candidate_hash, "candidate_hash")
        return f"{self.candidate_snapshots_dir}/{candidate_hash}.yaml"

    def task_input_rel(self, review_task_id: str) -> str:
        _require_id(review_task_id, "review_task")
        return f"{self.task_inputs_dir}/{review_task_id}.yaml"

    def report_rel(self, result_digest: str) -> str:
        """A P4 raw discovery report, named by its own canonical digest (the settled ``result_digest``)."""
        _require_digest(result_digest, "result_digest")
        return f"{self.reports_dir}/{result_digest}.yaml"

    def adjudication_rel(self, review_run_id: str) -> str:
        """The one P4 adjudication of ``review_run_id``."""
        _require_id(review_run_id, "review_run")
        return f"{self.adjudications_dir}/{review_run_id}.yaml"

    def repair_batch_rel(self, repair_batch_id: str) -> str:
        """Repairs only."""
        directory = self.repair_batches_dir
        _require_id(repair_batch_id, "review_repair_batch")
        return f"{directory}/{repair_batch_id}.yaml"

    def repair_result_rel(self, repair_batch_id: str) -> str:
        """The Repair Result of ``repair_batch_id``: one batch, at most one result. Repairs only."""
        directory = self.repair_results_dir
        _require_id(repair_batch_id, "review_repair_batch")
        return f"{directory}/{repair_batch_id}.yaml"

    def history_family_dir(self, family: str) -> str:
        """The directory of one P5 history record family. History only."""
        directory = self.history_dir
        if family not in HISTORY_FAMILIES:
            raise ValidationError(f"not a Review history family: {family!r}", code="review_record_invalid")
        return f"{directory}/{family}"

    def history_rel(self, family: str, identifier: str) -> str:
        """``history/<family>/<identifier>.yaml``, the identifier of the family's own identity kind. History only."""
        directory = self.history_family_dir(family)
        _require_id(identifier, HISTORY_FAMILY_KINDS[family])
        return f"{directory}/{identifier}.yaml"

    def policy_family_dir(self, family: str) -> str:
        """The directory of one P6 policy evidence family (``changes`` / ``evaluations``). Policy only."""
        directory = self.policy_dir
        if family not in POLICY_FAMILIES:
            raise ValidationError(f"not a Review policy evidence family: {family!r}", code="review_record_invalid")
        return f"{directory}/{family}"

    def policy_record_rel(self, family: str, identifier: str) -> str:
        """``policy/<family>/<identifier>.yaml``, the identifier of the family's own identity kind. Policy only."""
        directory = self.policy_family_dir(family)
        _require_id(identifier, POLICY_FAMILY_KINDS[family])
        return f"{directory}/{identifier}.yaml"

    # ------------------------------------------------------------------ classification and shape

    def is_review_path(self, relative: object) -> bool:
        """Whether ``relative`` is inside this Review namespace."""
        return isinstance(relative, str) and relative.startswith(self.root + "/")

    def is_policy_profile_path(self, relative: object) -> bool:
        """Whether ``relative`` is exactly this namespace's canonical Profile path. Never, without a policy area."""
        return self.policy and relative == self.policy_profile_rel

    def require_policy_profile_path(self, relative: str) -> None:
        """Refuse every path but the exact canonical Profile (§15.27: only the exact path is authority)."""
        if not self.is_policy_profile_path(relative):
            raise ValidationError(
                f"{relative!r} is not the canonical Project Profile {self.policy_profile_rel}", code="review_containment"
            )

    def require_record_path(self, relative: str) -> None:
        """Refuse ``relative`` unless it has the exact shape of a canonical Review record path of this namespace.

        Structural only: which directory, how deep, a ``.yaml`` leaf, no
        traversal, no empty or dot component. ``gates/<run>/<generation>.yaml``
        and one flat level in every other admitted record area; the two-level
        ``history/<family>/<id>.yaml`` and ``policy/<family>/<id>.yaml`` only
        where the namespace has those areas. The mutable Profile is never a
        record path. Whether the directories on the way are plain, contained
        directories is proven where the path is used, by a handle-bound no-follow
        walk, because a check on a path string says nothing about what it
        resolves to by the time it is opened.
        """
        if not self.is_review_path(relative):
            raise ValidationError(f"not a canonical Review path: {relative!r}", code="review_containment")
        parts = relative.split("/")
        if any(part in ("", ".", "..") or "\\" in part for part in parts):
            raise ValidationError(f"a Review path holds no traversal or empty component: {relative!r}", code="review_containment")
        below = parts[len(self.root.split("/")):]
        if not below[-1].endswith(".yaml"):
            raise ValidationError(f"a Review record is a .yaml file: {relative!r}", code="review_containment")
        if below[0] == "gates" and len(below) == 3:
            return
        if below[0] in self.subdirs and below[0] not in _NESTED_SUBDIRS and len(below) == 2:
            return
        if self.history and below[0] == "history" and len(below) == 3 and below[1] in HISTORY_FAMILIES:
            return
        if self.policy and below[0] == "policy" and len(below) == 3 and below[1] in POLICY_FAMILIES:
            return
        raise ValidationError(f"not a canonical Review record location: {relative!r}", code="review_containment")

    def require_readable_path(self, relative: str) -> None:
        """A path a Review reader may read: a canonical record, or - only with a policy area - the exact Profile.

        Reading only. The immutable create admits record paths alone
        (:meth:`require_record_path`).
        """
        if self.is_policy_profile_path(relative):
            return
        self.require_record_path(relative)


PROJECT_REVIEW_NAMESPACE = ReviewNamespace(
    PROJECT_NAMESPACE_NAME, PROJECT_REVIEW_ROOT, PROJECT_SUBDIRS,
    history=True, policy=True, activation=True, repairs=True,
)
ROOT_POLICY_REVIEW_NAMESPACE = ReviewNamespace(
    ROOT_POLICY_NAMESPACE_NAME, ROOT_REVIEW_ROOT, ROOT_SUBDIRS,
    history=False, policy=False, activation=False, repairs=False,
)
NAMESPACES = (PROJECT_REVIEW_NAMESPACE, ROOT_POLICY_REVIEW_NAMESPACE)


# --------------------------------------------------------------------------- root policy layout (§16.3, §31.48)

#: The root policy families :meth:`RootPolicyLayout.family_of` names.
FAMILY_REVIEW = "review"
FAMILY_PROMOTION_PACKET = "promotion-packet"
FAMILY_CHANGE = "change"
FAMILY_PATCH_NOTE = "patch-note"
FAMILY_EVALUATION = "evaluation"
FAMILY_GLOBAL_POLICY = "global-policy"
ROOT_POLICY_FAMILIES = (FAMILY_REVIEW, FAMILY_PROMOTION_PACKET, FAMILY_CHANGE, FAMILY_PATCH_NOTE, FAMILY_EVALUATION,
                        FAMILY_GLOBAL_POLICY)


def _is_exact_id(value: object, kind: str) -> bool:
    """``value`` is exactly one ID of ``kind``: the ID pattern's ``$`` would also admit one trailing newline."""
    return isinstance(value, str) and "\n" not in value and is_valid_id(value, kind)


def _require_exact_id(value: object, kind: str) -> None:
    if not _is_exact_id(value, kind):
        raise ValidationError(f"not a {kind} id: {value!r}", code="review_record_invalid")


@dataclass(frozen=True)
class RootPolicyLayout:
    """The Workline root's policy layout (§16.3): the Global policy file, four evidence families, the root Review.

    Everything here is outside every Project, and the evidence families are
    outside the root Review namespace: only the root controller's closed effects
    create them. :meth:`family_of` classifies exact shapes and refuses nothing,
    so a caller can refuse an effect whose path is not one of them.
    """

    root: str = ROOT_POLICY_DIR
    global_policy_rel: str = f"{ROOT_POLICY_DIR}/global-policy.yaml"
    promotion_packets_dir: str = f"{ROOT_POLICY_DIR}/promotion-packets"
    changes_dir: str = f"{ROOT_POLICY_DIR}/changes"
    evaluations_dir: str = f"{ROOT_POLICY_DIR}/evaluations"
    patch_notes_dir: str = f"{ROOT_POLICY_DIR}/patch-notes"
    review_dir: str = ROOT_REVIEW_ROOT

    def promotion_packet_rel(self, promotion_packet_id: str) -> str:
        _require_exact_id(promotion_packet_id, "review_promotion_packet")
        return f"{self.promotion_packets_dir}/{promotion_packet_id}.yaml"

    def global_change_rel(self, global_policy_change_id: str) -> str:
        _require_exact_id(global_policy_change_id, "review_global_policy_change")
        return f"{self.changes_dir}/{global_policy_change_id}.yaml"

    def patch_note_rel(self, global_policy_change_id: str) -> str:
        _require_exact_id(global_policy_change_id, "review_global_policy_change")
        return f"{self.patch_notes_dir}/{global_policy_change_id}.md"

    def global_evaluation_rel(self, evaluation_id: str) -> str:
        _require_exact_id(evaluation_id, "review_global_policy_evaluation")
        return f"{self.evaluations_dir}/{evaluation_id}.yaml"

    def _review_namespace(self) -> ReviewNamespace:
        if self.review_dir == ROOT_POLICY_REVIEW_NAMESPACE.root:
            return ROOT_POLICY_REVIEW_NAMESPACE
        return ReviewNamespace(ROOT_POLICY_NAMESPACE_NAME, self.review_dir, ROOT_SUBDIRS,
                               history=False, policy=False, activation=False, repairs=False)

    def family_of(self, relative: object) -> str | None:
        """The root policy family ``relative`` is exactly a path of, or ``None``.

        ``review`` for a canonical root Review record path; one flat level of a
        correctly kinded ID with the family's own suffix for the four evidence
        families; the exact Global policy path. Anything else - traversal, a
        deeper or shallower path, a wrong ID kind or suffix, a directory, a
        non-string - is ``None``.
        """
        if not isinstance(relative, str):
            return None
        if relative == self.global_policy_rel:
            return FAMILY_GLOBAL_POLICY
        namespace = self._review_namespace()
        if namespace.is_review_path(relative):
            try:
                namespace.require_record_path(relative)
            except ValidationError:
                return None
            return FAMILY_REVIEW
        for family, directory, kind, suffix in (
            (FAMILY_PROMOTION_PACKET, self.promotion_packets_dir, "review_promotion_packet", ".yaml"),
            (FAMILY_CHANGE, self.changes_dir, "review_global_policy_change", ".yaml"),
            (FAMILY_PATCH_NOTE, self.patch_notes_dir, "review_global_policy_change", ".md"),
            (FAMILY_EVALUATION, self.evaluations_dir, "review_global_policy_evaluation", ".yaml"),
        ):
            if not relative.startswith(directory + "/"):
                continue
            leaf = relative[len(directory) + 1:]
            if "/" in leaf or not leaf.endswith(suffix):
                return None
            return family if _is_exact_id(leaf[: -len(suffix)], kind) else None
        return None

    def owned_prefixes(self) -> tuple[str, ...]:
        """The closed root scope: the root Review and the four family directories (``/``-terminated), the policy file."""
        return (
            self.review_dir + "/",
            self.promotion_packets_dir + "/",
            self.changes_dir + "/",
            self.evaluations_dir + "/",
            self.patch_notes_dir + "/",
            self.global_policy_rel,
        )


ROOT_POLICY_LAYOUT = RootPolicyLayout()
