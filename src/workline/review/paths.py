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

import os
from pathlib import Path
import stat
from typing import Any

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


# --------------------------------------------------------------------------- containment / no-follow

def _reparse(info: os.stat_result) -> bool:
    """Whether ``info`` describes a reparse point - a junction, a symlink, or anything else with one.

    Windows junctions are directories to ``S_ISDIR`` and are followed by every
    ordinary path operation, so directory-ness alone proves nothing there.
    ``st_file_attributes`` carries the reparse flag; ``st_reparse_tag`` is
    nonzero for every reparse kind. Either one is enough to refuse.
    """
    attributes = getattr(info, "st_file_attributes", 0)
    if attributes and attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        return True
    return bool(getattr(info, "st_reparse_tag", 0))


def _identity(info: os.stat_result) -> tuple[Any, Any]:
    """What identifies a directory across two looks at it.

    ``st_dev``/``st_ino`` are meaningful on POSIX and, on Windows, are filled in
    from the volume serial number and file index by CPython, which is exactly
    the pair that changes when a component is swapped for another directory.
    """
    return (info.st_dev, info.st_ino)


def directory_identity(path: Path) -> tuple[Any, Any]:
    """The identity of the existing plain directory at ``path``, or a STOP.

    No-follow: ``lstat`` describes the component itself, so a symlink or
    junction standing where a directory is expected is seen as what it is
    instead of as whatever it points at.
    """
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise ValidationError(
            f"a Review write cannot show what {path} is: {exc}", code="review_containment"
        ) from exc
    if _reparse(info):
        raise ValidationError(
            f"a Review write refuses {path}: it is a symlink, junction or other reparse point, "
            "and a Review record is written only through plain in-Project directories",
            code="review_containment",
        )
    if not stat.S_ISDIR(info.st_mode):
        raise ValidationError(
            f"a Review write refuses {path}: a plain directory is expected there",
            code="review_containment",
        )
    return _identity(info)


def prove_containment(root: Path, relative: str) -> tuple[Any, Any] | None:
    """Prove every existing component of ``relative`` is a plain in-Project directory.

    Walks root -> ... -> parent with :func:`directory_identity`. A component
    that does not exist yet is one of the lazily created ones: there is nothing
    there to prove, and the walk stops, because a component *after* a gap could
    only be reached through the gap.

    Returns the target parent's identity when the parent already exists, and
    ``None`` when it does not. That distinction is what
    :func:`require_proven_parent` needs: an existing parent can be swapped
    between this proof and the write, and a parent this operation is about to
    create cannot have been proven beforehand and is proven by the second walk
    instead.
    """
    return _walk_to_parent(root, relative)


def _walk_to_parent(root: Path, relative: str) -> tuple[Any, Any] | None:
    """Prove root -> ... -> parent, returning the parent's identity or ``None`` if it is absent."""
    if not is_review_path(relative):
        raise ValidationError(
            f"containment is proven for canonical Review paths; {relative!r} is not one", code="review_containment"
        )
    parts = relative.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValidationError(f"a Review path holds no traversal: {relative!r}", code="review_containment")
    root = Path(root)
    directory_identity(root)
    current = root
    identity: tuple[Any, Any] | None = None
    for part in parts[:-1]:
        current = current / part
        if not current.exists() and not current.is_symlink():
            return None  # not created yet; the create boundary proves what it actually writes into
        identity = directory_identity(current)
    return identity


def require_proven_parent(root: Path, relative: str, expected: tuple[Any, Any] | None) -> None:
    """Re-prove the whole chain at the create boundary, and refuse a parent that changed.

    The walk is done again, in full, so that every component the bytes will
    actually pass through is shown to be a plain in-Project directory *now* -
    including the ones this operation created a moment ago, which no earlier
    walk could have proven.

    When the parent already existed, its identity must still be the one
    :func:`prove_containment` proved. A component replaced with a link in the
    window between the two walks changes that identity, so it is a refusal
    rather than a redirect. When the parent did not exist, this walk is the
    proof, and there is nothing to compare it against.
    """
    found = _walk_to_parent(root, relative)
    parent = Path(root) / Path(relative).parent
    if found is None:
        raise ValidationError(
            f"the directory a Review record is written into does not exist at the moment of writing ({parent}); "
            "nothing is written: reconcile required",
            code="review_containment",
        )
    if expected is not None and found != expected:
        raise ValidationError(
            f"the directory a Review record would be written into changed while it was being written "
            f"({parent}); nothing is written: reconcile required",
            code="review_containment",
        )
