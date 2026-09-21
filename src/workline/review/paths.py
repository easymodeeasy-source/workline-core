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
"""

from __future__ import annotations

from pathlib import Path

from ..errors import ValidationError
from ..ids import is_valid_id
from ..store import WORKLINE_DIR

#: The one canonical Review namespace, created lazily on first Review write.
#: A Project that never uses Review keeps exactly the shape it has today.
REVIEW_DIR = f"{WORKLINE_DIR}/review"

GATES_DIR = f"{REVIEW_DIR}/gates"
RECEIPTS_DIR = f"{REVIEW_DIR}/receipts"
CONSUMPTIONS_DIR = f"{REVIEW_DIR}/consumptions"
SUPERSESSIONS_DIR = f"{REVIEW_DIR}/supersessions"
CANDIDATE_SNAPSHOTS_DIR = f"{REVIEW_DIR}/candidate-snapshots"
TASK_INPUTS_DIR = f"{REVIEW_DIR}/task-inputs"
ACTIVATION_DIR = f"{REVIEW_DIR}/activation"

#: The ephemeral Review area. Never canonical truth, never evidence, never the
#: only material an accepted task can be reconstructed from (``R1`` §3).
RUNTIME_REVIEW_DIR = f"{WORKLINE_DIR}/runtime/review"

WORK_TERMINAL_ACTIVATION_REL = f"{ACTIVATION_DIR}/work-terminal-v1.yaml"

#: The directories a Review namespace may hold, and nothing else.
REVIEW_SUBDIRS = (
    "gates",
    "receipts",
    "consumptions",
    "supersessions",
    "candidate-snapshots",
    "task-inputs",
    "activation",
)

#: Gate generation files are zero-padded to this width.
GENERATION_WIDTH = 6

#: The scope-only same-run serialization token (``R2`` §4 / ``R3`` §2). No file
#: is ever created at this path, it is never committed, and it is never Review
#: truth. It exists so that an unfinished generation mutation for a Review Run
#: mechanically overlaps any later attempt for the same run - including the case
#: where the physical generation file already appeared before its ``applied``
#: flag was saved, and a new invocation would otherwise compute N+2.
SERIALIZATION_TOKEN = ".generation-serialization"


def generation_name(generation: int) -> str:
    """``000001.yaml`` for generation 1. The filename is the generation, zero padded."""
    if type(generation) is not int or generation < 1:
        raise ValidationError(f"a Review generation is a positive integer, not {generation!r}", code="review_gate_chain")
    return f"{generation:0{GENERATION_WIDTH}d}.yaml"


def generation_of_name(name: str) -> int | None:
    """The generation a gate filename names, or ``None`` when it names none.

    Validated as an integer in its own right rather than through ``kind_of``
    (``R2`` §6): a generation is not an allocated identifier, and the padding is
    exact - ``1.yaml`` and ``0000001.yaml`` name nothing.
    """
    if not isinstance(name, str) or not name.endswith(".yaml"):
        return None
    stem = name[: -len(".yaml")]
    if len(stem) != GENERATION_WIDTH or not stem.isdigit() or not stem.isascii():
        return None
    value = int(stem)
    return value if value >= 1 else None


def run_dir(review_run_id: str) -> str:
    _require_id(review_run_id, "review_run")
    return f"{GATES_DIR}/{review_run_id}"


def gate_rel(review_run_id: str, generation: int) -> str:
    return f"{run_dir(review_run_id)}/{generation_name(generation)}"


def serialization_token_rel(review_run_id: str) -> str:
    """The scope-only token path for ``review_run_id``. Nothing is ever written here."""
    return f"{run_dir(review_run_id)}/{SERIALIZATION_TOKEN}"


def receipt_rel(receipt_id: str) -> str:
    _require_id(receipt_id, "review_receipt")
    return f"{RECEIPTS_DIR}/{receipt_id}.yaml"


def consumption_rel(consumption_id: str) -> str:
    _require_id(consumption_id, "review_consumption")
    return f"{CONSUMPTIONS_DIR}/{consumption_id}.yaml"


def supersession_rel(superseded_receipt_id: str) -> str:
    _require_id(superseded_receipt_id, "review_receipt")
    return f"{SUPERSESSIONS_DIR}/{superseded_receipt_id}.yaml"


def candidate_snapshot_rel(candidate_hash: str) -> str:
    _require_digest(candidate_hash, "candidate_hash")
    return f"{CANDIDATE_SNAPSHOTS_DIR}/{candidate_hash}.yaml"


def task_input_rel(review_task_id: str) -> str:
    _require_id(review_task_id, "review_task")
    return f"{TASK_INPUTS_DIR}/{review_task_id}.yaml"


def is_review_path(relative: str) -> bool:
    """Whether ``relative`` is inside the canonical Review namespace."""
    return isinstance(relative, str) and relative.startswith(REVIEW_DIR + "/")


def _require_id(value: str, kind: str) -> None:
    if not is_valid_id(value, kind):
        raise ValidationError(f"not a {kind} id: {value!r}", code="review_record_invalid")


def _require_digest(value: str, described: str) -> None:
    from .records import DIGEST_RE

    if not isinstance(value, str) or DIGEST_RE.match(value) is None:
        raise ValidationError(f"{described} is not a lowercase hex SHA-256: {value!r}", code="review_record_invalid")


# --------------------------------------------------------------------------- record path shape

#: The Review subdirectories whose records sit directly inside them, by name.
_FLAT_RECORD_DIRS = ("receipts", "consumptions", "supersessions", "candidate-snapshots", "task-inputs", "activation")


def require_review_record_path(relative: str) -> None:
    """Refuse ``relative`` unless it has the exact shape of a canonical Review record path.

    Structural only: which directory, how deep, a ``.yaml`` leaf, no traversal,
    no empty or dot component. Whether the directories on the way are plain,
    in-Project directories is proven where the path is actually used - by a
    handle-bound, no-follow walk (:mod:`workline.review.fsafe`) - because a
    check on a path string, however careful, says nothing about what the path
    resolves to by the time it is opened.
    """
    if not is_review_path(relative):
        raise ValidationError(f"not a canonical Review path: {relative!r}", code="review_containment")
    parts = relative.split("/")
    if any(part in ("", ".", "..") or "\\" in part for part in parts):
        raise ValidationError(f"a Review path holds no traversal or empty component: {relative!r}", code="review_containment")
    below = parts[len(REVIEW_DIR.split("/")):]
    if not below[-1].endswith(".yaml"):
        raise ValidationError(f"a Review record is a .yaml file: {relative!r}", code="review_containment")
    if below[0] == "gates" and len(below) == 3:
        return
    if below[0] in _FLAT_RECORD_DIRS and len(below) == 2:
        return
    raise ValidationError(f"not a canonical Review record location: {relative!r}", code="review_containment")
