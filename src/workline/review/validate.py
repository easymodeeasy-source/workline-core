"""Structural validation of a Project's Review namespace.

A separate pass from ``ProjectView`` validation, and deliberately so (``R1``
§11). Review records are not lifecycle truth, so they are not loaded by the
thing that derives lifecycle; they are checked here, where a problem with them
can be reported without any of them ever reaching ``state.py``.

The baseline is that a Project with no ``.workline/review/`` is valid. Review
capability arrives lazily with the first Review write, and a Project that never
uses it keeps exactly the shape it has today.

Everything else fails closed: an unknown entry, a file where a directory
belongs, a symlink or reparse point anywhere in the namespace, a malformed
record, a name that does not match the identity inside the file, a
non-contiguous generation chain, a duplicate logical ID, a conflicting
immutable fact, malformed provenance, or a contradictory activation state.

P3 activation semantics are not applied. An absent activation record means
review-v1 Work terminalization is not activated, which is the state P1 leaves
every Project in, and no terminal event is classified by anything here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..errors import ValidationError
from ..store import ProjectStore
from . import paths, records
from .store import ReviewStore


@dataclass(frozen=True)
class ReviewProblem:
    code: str
    message: str


def validate_review(store: ProjectStore) -> list[ReviewProblem]:
    """Structural problems in this Project's Review namespace; empty when there are none."""
    review = ReviewStore(store)
    if not review.exists():
        return []  # a Project that has never used Review is a valid Project
    problems: list[ReviewProblem] = []
    problems.extend(_namespace_shape(review))
    if problems:
        # A namespace whose shape is wrong cannot be read record by record
        # without reporting the same broken thing repeatedly.
        return problems
    problems.extend(_gates(review))
    problems.extend(_receipts(review))
    problems.extend(_consumptions(review))
    problems.extend(_supersessions(review))
    problems.extend(_provenance(review))
    problems.extend(_activation(review))
    return problems


def _problem(exc: ValidationError) -> ReviewProblem:
    return ReviewProblem(getattr(exc, "code", None) or "review_invalid", str(exc))


def _namespace_shape(review: ReviewStore) -> list[ReviewProblem]:
    """Only the seven known directories, each a plain directory, and nothing else."""
    problems: list[ReviewProblem] = []
    root = review.review
    if root.is_symlink():
        return [ReviewProblem("review_containment", f"{paths.REVIEW_DIR} is a symlink or reparse point")]
    try:
        entries = sorted(root.iterdir())
    except OSError as exc:
        return [ReviewProblem("review_namespace_invalid", f"{paths.REVIEW_DIR} unreadable: {exc}")]
    for entry in entries:
        if entry.name not in paths.REVIEW_SUBDIRS:
            problems.append(
                ReviewProblem(
                    "review_namespace_invalid",
                    f"{paths.REVIEW_DIR} holds unknown entry {entry.name}",
                )
            )
            continue
        if entry.is_symlink():
            problems.append(
                ReviewProblem("review_containment", f"{paths.REVIEW_DIR}/{entry.name} is a symlink or reparse point")
            )
        elif not entry.is_dir():
            problems.append(
                ReviewProblem(
                    "review_namespace_invalid", f"{paths.REVIEW_DIR}/{entry.name} is a file where a directory belongs"
                )
            )
    return problems


def _gates(review: ReviewStore) -> list[ReviewProblem]:
    problems: list[ReviewProblem] = []
    try:
        run_ids = review.run_ids()
    except ValidationError as exc:
        return [_problem(exc)]
    for review_run_id in run_ids:
        try:
            chain = review.gate_chain(review_run_id)
        except ValidationError as exc:
            problems.append(_problem(exc))
            continue
        if chain is None:
            problems.append(
                ReviewProblem(
                    "review_namespace_invalid",
                    f"{paths.run_dir(review_run_id)} holds no gate generation; an empty Review Run directory "
                    "is not a state a Review Run reaches",
                )
            )
            continue
        problems.extend(_chain_facts(review, chain))
    return problems


def _chain_facts(review: ReviewStore, chain: Any) -> list[ReviewProblem]:
    """Facts a validated chain must agree with itself and the rest of the namespace about."""
    problems: list[ReviewProblem] = []
    first = chain.generations[0]
    for found in chain.generations:
        for field_name in ("review_kind", "target_identity"):
            if getattr(found, field_name) != getattr(first, field_name):
                problems.append(
                    ReviewProblem(
                        "review_gate_chain",
                        f"Review Run {chain.review_run_id} generation {found.generation} changes {field_name}; "
                        "a Run's kind and target are immutable facts",
                    )
                )
        if found.receipt_id is not None and not review.receipt_exists(found.receipt_id):
            problems.append(
                ReviewProblem(
                    "review_record_missing",
                    f"Review Run {chain.review_run_id} generation {found.generation} issues receipt "
                    f"{found.receipt_id}, which is not stored",
                )
            )
    issued = [found.receipt_id for found in chain.generations if found.receipt_id is not None]
    if len(set(issued)) != len(issued):
        problems.append(
            ReviewProblem(
                "review_gate_chain",
                f"Review Run {chain.review_run_id} issues the same receipt from two generations",
            )
        )
    for found in chain.generations:
        if found.sealed and found.unsettled_task_ids():
            problems.append(
                ReviewProblem(
                    "review_gate_chain",
                    f"Review Run {chain.review_run_id} generation {found.generation} is sealed with "
                    f"unsettled accepted task(s): {', '.join(found.unsettled_task_ids())}",
                )
            )
    return problems


def _receipts(review: ReviewStore) -> list[ReviewProblem]:
    problems: list[ReviewProblem] = []
    try:
        receipt_ids = review.receipt_ids()
    except ValidationError as exc:
        return [_problem(exc)]
    for receipt_id in receipt_ids:
        try:
            receipt = review.read_receipt(receipt_id)
        except ValidationError as exc:
            problems.append(_problem(exc))
            continue
        try:
            chain = review.gate_chain(receipt.review_run_id)
        except ValidationError as exc:
            problems.append(_problem(exc))
            continue
        if chain is None:
            problems.append(
                ReviewProblem(
                    "review_record_missing",
                    f"receipt {receipt_id} names Review Run {receipt.review_run_id}, which has no gate chain",
                )
            )
            continue
        try:
            generation = chain.generation(receipt.review_generation)
        except ValidationError as exc:
            problems.append(_problem(exc))
            continue
        if generation.receipt_id != receipt_id:
            problems.append(
                ReviewProblem(
                    "review_record_conflict",
                    f"receipt {receipt_id} says it was issued by generation {receipt.review_generation}, "
                    f"which issues {generation.receipt_id!r}",
                )
            )
        if not generation.sealed:
            problems.append(
                ReviewProblem(
                    "review_record_conflict",
                    f"receipt {receipt_id} was issued by generation {receipt.review_generation}, which is "
                    f"{generation.status}; only a {records.GATE_STATUS_SEALED} generation issues one",
                )
            )
        if generation.candidate_hash != receipt.authorized_candidate_hash:
            problems.append(
                ReviewProblem(
                    "review_record_conflict",
                    f"receipt {receipt_id} authorizes candidate {receipt.authorized_candidate_hash}, "
                    f"but its generation reviewed {generation.candidate_hash}",
                )
            )
    return problems


def _consumptions(review: ReviewStore) -> list[ReviewProblem]:
    problems: list[ReviewProblem] = []
    try:
        by_receipt = review.consumption_by_receipt()
        review.consumption_by_terminal_event()
    except ValidationError as exc:
        return [_problem(exc)]
    for receipt_id, consumption in by_receipt.items():
        if not review.receipt_exists(receipt_id):
            problems.append(
                ReviewProblem(
                    "review_record_missing",
                    f"consumption {consumption.consumption_id} consumes receipt {receipt_id}, which is not stored",
                )
            )
            continue
        try:
            receipt = review.read_receipt(receipt_id)
        except ValidationError as exc:
            problems.append(_problem(exc))
            continue
        if receipt.authorized_candidate_hash != consumption.authorized_candidate_hash:
            problems.append(
                ReviewProblem(
                    "review_record_conflict",
                    f"consumption {consumption.consumption_id} names candidate "
                    f"{consumption.authorized_candidate_hash}, but receipt {receipt_id} authorized "
                    f"{receipt.authorized_candidate_hash}",
                )
            )
        if receipt.review_run_id != consumption.review_run_id:
            problems.append(
                ReviewProblem(
                    "review_record_conflict",
                    f"consumption {consumption.consumption_id} and receipt {receipt_id} name different Review Runs",
                )
            )
    return problems


def _supersessions(review: ReviewStore) -> list[ReviewProblem]:
    problems: list[ReviewProblem] = []
    try:
        superseded_ids = review.superseded_receipt_ids()
    except ValidationError as exc:
        return [_problem(exc)]
    for receipt_id in superseded_ids:
        try:
            supersession = review.read_supersession(receipt_id)
        except ValidationError as exc:
            problems.append(_problem(exc))
            continue
        if not review.receipt_exists(receipt_id):
            problems.append(
                ReviewProblem(
                    "review_record_missing",
                    f"supersession names receipt {receipt_id}, which is not stored",
                )
            )
            continue
        try:
            receipt = review.read_receipt(receipt_id)
        except ValidationError as exc:
            problems.append(_problem(exc))
            continue
        if receipt.review_run_id != supersession.review_run_id:
            problems.append(
                ReviewProblem(
                    "review_record_conflict",
                    f"supersession of {receipt_id} names Review Run {supersession.review_run_id}, "
                    f"but the receipt names {receipt.review_run_id}",
                )
            )
    return problems


def _provenance(review: ReviewStore) -> list[ReviewProblem]:
    """Every accepted task's reconstruction material must actually be stored and agree.

    An accepted task whose snapshot or task input is missing, or whose stored
    provenance digests do not match what the gate bound, cannot be rerun or
    retrieved after runtime loss - which is the whole point of the records
    being canonical rather than runtime (``R3`` §4).
    """
    problems: list[ReviewProblem] = []
    try:
        run_ids = review.run_ids()
    except ValidationError as exc:
        return [_problem(exc)]
    for review_run_id in run_ids:
        try:
            chain = review.gate_chain(review_run_id)
        except ValidationError:
            continue  # already reported by the gate pass
        if chain is None:
            continue
        # Each generation is a full snapshot, so a task accepted at generation N
        # is carried forward by every generation after it. Its provenance is one
        # fact and is checked once, against the generation that first accepted
        # it - which is what its task input records as ``accepted_generation``.
        first_seen: dict[str, tuple[int, dict[str, Any]]] = {}
        for generation in chain.generations:
            for task in generation.accepted_tasks:
                task_id = str(task["task_id"])
                if task_id not in first_seen:
                    first_seen[task_id] = (generation.generation, task)
                elif first_seen[task_id][1] != task:
                    problems.append(
                        ReviewProblem(
                            "review_provenance_conflict",
                            f"Review Run {review_run_id} carries accepted task {task_id} forward with different "
                            f"provenance at generation {generation.generation}; an accepted task is an immutable fact",
                        )
                    )
        for task_id, (generation_number, task) in sorted(first_seen.items()):
            problems.extend(_accepted_task_provenance(review, review_run_id, generation_number, task))
    return problems


def _accepted_task_provenance(
    review: ReviewStore, review_run_id: str, generation: int, task: dict[str, Any]
) -> list[ReviewProblem]:
    problems: list[ReviewProblem] = []
    where = f"Review Run {review_run_id} generation {generation} accepted task {task['task_id']}"
    candidate_hash = str(task["candidate_hash"])
    if not review.candidate_snapshot_exists(candidate_hash):
        problems.append(
            ReviewProblem("review_record_missing", f"{where} has no stored candidate snapshot {candidate_hash}")
        )
    else:
        try:
            found = review.candidate_material_digest(candidate_hash)
            if found != task["candidate_material_digest"]:
                problems.append(
                    ReviewProblem(
                        "review_provenance_conflict",
                        f"{where} bound candidate_material_digest {task['candidate_material_digest']}, "
                        f"but the stored snapshot digests to {found}",
                    )
                )
            snapshot = review.read_candidate_snapshot(candidate_hash)
            if snapshot.reconstruction_mode != task["reconstruction_mode"]:
                problems.append(
                    ReviewProblem(
                        "review_provenance_conflict",
                        f"{where} bound reconstruction mode {task['reconstruction_mode']}, "
                        f"but the stored snapshot is {snapshot.reconstruction_mode}",
                    )
                )
        except ValidationError as exc:
            problems.append(_problem(exc))
    task_id = str(task["task_id"])
    if not review.task_input_exists(task_id):
        problems.append(ReviewProblem("review_record_missing", f"{where} has no stored task input"))
        return problems
    try:
        found = review.task_input_digest(task_id)
        if found != task["task_input_digest"]:
            problems.append(
                ReviewProblem(
                    "review_provenance_conflict",
                    f"{where} bound task_input_digest {task['task_input_digest']}, "
                    f"but the stored task input digests to {found}",
                )
            )
        task_input = review.read_task_input(task_id)
        for field_name, bound in (
            ("request_digest", "request_digest"),
            ("candidate_hash", "candidate_hash"),
            ("review_context_hash", "review_context_hash"),
            ("effective_policy_hash", "effective_policy_hash"),
        ):
            if getattr(task_input, field_name) != task[bound]:
                problems.append(
                    ReviewProblem(
                        "review_provenance_conflict",
                        f"{where} bound {bound} {task[bound]}, but its stored task input says "
                        f"{getattr(task_input, field_name)}",
                    )
                )
        if task_input.accepted_generation != generation:
            problems.append(
                ReviewProblem(
                    "review_provenance_conflict",
                    f"{where} stores a task input accepted at generation {task_input.accepted_generation}",
                )
            )
    except ValidationError as exc:
        problems.append(_problem(exc))
    return problems


def _activation(review: ReviewStore) -> list[ReviewProblem]:
    """The activation record, if present, must parse. P1 creates none and activates nothing."""
    try:
        review.read_activation()
    except ValidationError as exc:
        return [_problem(exc)]
    return []
