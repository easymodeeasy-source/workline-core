"""Read access to a Project's canonical Review records.

``ReviewStore`` is the only thing that reads ``.workline/review/``. It owns path
construction, parsing, schema and version checks, filename-to-content identity,
gate-chain validation, the predecessor digest, and the logical uniqueness
indexes Consumption depends on.

It is deliberately *not* an operation owner. It reads, validates and renders;
it never writes, never holds the Project lock, never opens a mutation and never
decides that anything should happen. Review gate state is written by the
top-level operation using the gate - Roadmap's mutation owner, START's mutation
owner - through the ordinary Mutation Controller (``R3`` §1). There is no
standalone Review progression controller, and this class is the closest thing
Review has to one precisely so that it can be shown to be inert.

``ProjectView`` / ``state.py`` never call anything here. Review records are not
lifecycle truth, and nothing in this module derives Work, Phase or Roadmap
state (``R1`` §10, ``R3`` §11).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import ValidationError
from ..store import ProjectStore
from . import paths, records, serialize
from .records import (
    CandidateSnapshot,
    Consumption,
    GateGeneration,
    Receipt,
    Supersession,
    TaskInput,
    WorkTerminalActivation,
)


@dataclass(frozen=True)
class GateChain:
    """One Review Run's validated, contiguous generation chain.

    Holding one of these is the proof: it is constructed only when every
    generation from 1 to the last is present exactly once, each names its
    predecessor and that predecessor's canonical digest, and every file's name
    matches the generation inside it. ``latest`` is therefore never "the highest
    number found" - it is the end of a chain that was validated as a whole
    (``R1`` §4).
    """

    review_run_id: str
    generations: tuple[GateGeneration, ...]
    digests: tuple[str, ...]

    @property
    def latest(self) -> GateGeneration:
        return self.generations[-1]

    @property
    def latest_digest(self) -> str:
        return self.digests[-1]

    @property
    def next_generation(self) -> int:
        return self.latest.generation + 1

    def generation(self, number: int) -> GateGeneration:
        for found in self.generations:
            if found.generation == number:
                return found
        raise ValidationError(
            f"Review Run {self.review_run_id} has no generation {number}", code="review_gate_chain"
        )

    def superseded_receipts(self) -> tuple[str, ...]:
        """Receipts issued by a sealed generation that a later generation has moved past.

        Supersession is derived here, from the validated chain, rather than
        stored as a state on the immutable file that would have to be rewritten
        to say it (``R1`` §4).
        """
        return tuple(
            found.receipt_id
            for found in self.generations[:-1]
            if found.receipt_id is not None and found.sealed
        )


class ReviewStore:
    """Canonical Review record access for one Project."""

    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.root = store.root
        self.review = store.root / paths.REVIEW_DIR

    # paths ------------------------------------------------------------------
    def abs(self, relative: str) -> Path:
        return self.root / relative

    def exists(self) -> bool:
        """Whether this Project has a Review namespace at all.

        A Project that has never used Review has none, and that is a valid
        Project (``R1`` §11). Nothing here creates it.
        """
        return self.review.is_dir()

    # rendering --------------------------------------------------------------
    @staticmethod
    def render(record: dict[str, Any]) -> str:
        """The canonical bytes a Review record is stored as, as text."""
        return serialize.canonical_text(record)

    @staticmethod
    def digest(record: dict[str, Any]) -> str:
        """``SHA-256`` over those canonical bytes - the identity a successor names."""
        return serialize.digest(record)

    # reading ----------------------------------------------------------------
    def _read(self, relative: str, described: str) -> dict[str, Any]:
        path = self.abs(relative)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValidationError(
                f"{described} is not a plain file: {relative}", code="review_containment"
            )
        try:
            text = path.read_text(encoding=serialize.ENCODING)
        except FileNotFoundError as exc:
            raise ValidationError(f"{described} not found: {relative}", code="review_record_missing") from exc
        except (OSError, UnicodeError) as exc:
            raise ValidationError(f"{described} unreadable: {relative}: {exc}", code="review_record_invalid") from exc
        return serialize.parse(text, described)

    def read_text(self, relative: str, described: str) -> str:
        """The exact stored text at ``relative``, for a digest over what is actually there."""
        try:
            return self.abs(relative).read_text(encoding=serialize.ENCODING)
        except FileNotFoundError as exc:
            raise ValidationError(f"{described} not found: {relative}", code="review_record_missing") from exc
        except (OSError, UnicodeError) as exc:
            raise ValidationError(f"{described} unreadable: {relative}: {exc}", code="review_record_invalid") from exc

    # gate generations -------------------------------------------------------
    def run_ids(self) -> tuple[str, ...]:
        """Every Review Run that has a gate directory, in sorted order."""
        gates = self.abs(paths.GATES_DIR)
        if not gates.is_dir():
            return ()
        found: list[str] = []
        for entry in sorted(gates.iterdir()):
            if not entry.is_dir() or entry.is_symlink():
                raise ValidationError(
                    f"{paths.GATES_DIR} holds {entry.name}, which is not a plain Review Run directory",
                    code="review_namespace_invalid",
                )
            from ..ids import is_valid_id

            if not is_valid_id(entry.name, "review_run"):
                raise ValidationError(
                    f"{paths.GATES_DIR} holds {entry.name}, which is not a review_run id",
                    code="review_namespace_invalid",
                )
            found.append(entry.name)
        return tuple(found)

    def read_gate(self, review_run_id: str, generation: int) -> GateGeneration:
        relative = paths.gate_rel(review_run_id, generation)
        described = f"Review gate {relative}"
        record = self._read(relative, described)
        found = GateGeneration.from_record(record, described)
        if found.review_run_id != review_run_id:
            raise ValidationError(
                f"{described} declares Review Run {found.review_run_id}, not {review_run_id}",
                code="review_record_invalid",
            )
        if found.generation != generation:
            raise ValidationError(
                f"{described} declares generation {found.generation}, not {generation}",
                code="review_gate_chain",
            )
        return found

    def gate_chain(self, review_run_id: str) -> GateChain | None:
        """The validated chain for ``review_run_id``, or ``None`` when the run has none yet.

        Validated as a whole before anything is returned: a gap, a duplicate, a
        filename that does not match its content, a predecessor that is not the
        generation before it, or a predecessor digest that is not the canonical
        digest of that generation's stored bytes is fail-closed. The latest
        generation is never read on its own, because on its own it cannot show
        that the chain behind it is intact.
        """
        directory = self.abs(paths.run_dir(review_run_id))
        if not directory.is_dir():
            return None
        numbers: list[int] = []
        for entry in sorted(directory.iterdir()):
            if entry.name == paths.SERIALIZATION_TOKEN:
                raise ValidationError(
                    f"{paths.run_dir(review_run_id)} holds a physical {paths.SERIALIZATION_TOKEN}; "
                    "that path is a scope-only token and is never created",
                    code="review_namespace_invalid",
                )
            number = paths.generation_of_name(entry.name)
            if number is None or entry.is_symlink() or not entry.is_file():
                raise ValidationError(
                    f"{paths.run_dir(review_run_id)} holds {entry.name}, which is not a gate generation file",
                    code="review_namespace_invalid",
                )
            numbers.append(number)
        if not numbers:
            return None
        numbers.sort()
        expected = list(range(records.FIRST_GENERATION, records.FIRST_GENERATION + len(numbers)))
        if numbers != expected:
            raise ValidationError(
                f"Review Run {review_run_id} has a non-contiguous generation chain: "
                f"found {numbers}, expected {expected}",
                code="review_gate_chain",
            )
        generations: list[GateGeneration] = []
        digests: list[str] = []
        for number in numbers:
            relative = paths.gate_rel(review_run_id, number)
            found = self.read_gate(review_run_id, number)
            stored_digest = serialize.digest_of_text(self.read_text(relative, f"Review gate {relative}"))
            if number > records.FIRST_GENERATION and found.previous_digest != digests[-1]:
                raise ValidationError(
                    f"Review gate {relative} names predecessor digest {found.previous_digest}, "
                    f"but generation {number - 1} canonically digests to {digests[-1]}",
                    code="review_gate_chain",
                )
            generations.append(found)
            digests.append(stored_digest)
        return GateChain(review_run_id, tuple(generations), tuple(digests))

    def next_generation(self, review_run_id: str) -> int:
        """The generation a new gate mutation for ``review_run_id`` would write.

        Derived only from the validated chain (``R2`` §3). This is *not* on its
        own a safe basis for opening that mutation: the owner must first find
        and settle any pending same-run generation mutation, because a physical
        generation file can exist before its ``applied`` flag was saved. See
        :func:`workline.review.gate.next_generation_scope`.
        """
        chain = self.gate_chain(review_run_id)
        return records.FIRST_GENERATION if chain is None else chain.next_generation

    # receipts ---------------------------------------------------------------
    def read_receipt(self, receipt_id: str) -> Receipt:
        relative = paths.receipt_rel(receipt_id)
        described = f"Review receipt {relative}"
        found = Receipt.from_record(self._read(relative, described), described)
        if found.receipt_id != receipt_id:
            raise ValidationError(
                f"{described} declares receipt {found.receipt_id}, not the one its filename names",
                code="review_record_invalid",
            )
        return found

    def receipt_exists(self, receipt_id: str) -> bool:
        return self.abs(paths.receipt_rel(receipt_id)).is_file()

    def receipt_ids(self) -> tuple[str, ...]:
        return self._ids_in(paths.RECEIPTS_DIR, "review_receipt")

    # consumptions -----------------------------------------------------------
    def read_consumption(self, consumption_id: str) -> Consumption:
        relative = paths.consumption_rel(consumption_id)
        described = f"Review consumption {relative}"
        found = Consumption.from_record(self._read(relative, described), described)
        if found.consumption_id != consumption_id:
            raise ValidationError(
                f"{described} declares consumption {found.consumption_id}, not the one its filename names",
                code="review_record_invalid",
            )
        return found

    def consumption_ids(self) -> tuple[str, ...]:
        return self._ids_in(paths.CONSUMPTIONS_DIR, "review_consumption")

    def consumptions(self) -> tuple[Consumption, ...]:
        return tuple(self.read_consumption(found) for found in self.consumption_ids())

    def consumption_by_receipt(self) -> dict[str, Consumption]:
        """``receipt_id -> Consumption``, refusing a second Consumption of one Receipt.

        The common invariant of ``R4`` §1: one authorization is used at most
        once. Building the index *is* the check - two Consumptions naming one
        Receipt cannot both be in a mapping, so the conflict is raised here
        rather than being left for a caller to notice.
        """
        index: dict[str, Consumption] = {}
        for found in self.consumptions():
            existing = index.get(found.receipt_id)
            if existing is not None:
                raise ValidationError(
                    f"Receipt {found.receipt_id} has two Consumptions ({existing.consumption_id} and "
                    f"{found.consumption_id}); one authorization is consumed at most once",
                    code="review_consumption_conflict",
                )
            index[found.receipt_id] = found
        return index

    def consumption_by_terminal_event(self) -> dict[str, Consumption]:
        """``terminal_event_id -> Consumption``, refusing two Consumptions of one event.

        Planning and Policy Consumptions name no terminal event and are absent
        from this index by design; they are unique by Receipt alone (``R4`` §7).
        """
        index: dict[str, Consumption] = {}
        for found in self.consumptions():
            if found.terminal_event_id is None:
                continue
            existing = index.get(found.terminal_event_id)
            if existing is not None:
                raise ValidationError(
                    f"terminal event {found.terminal_event_id} has two Consumptions "
                    f"({existing.consumption_id} and {found.consumption_id})",
                    code="review_consumption_conflict",
                )
            index[found.terminal_event_id] = found
        return index

    # supersessions ----------------------------------------------------------
    def read_supersession(self, superseded_receipt_id: str) -> Supersession:
        relative = paths.supersession_rel(superseded_receipt_id)
        described = f"Review supersession {relative}"
        found = Supersession.from_record(self._read(relative, described), described)
        if found.superseded_receipt_id != superseded_receipt_id:
            raise ValidationError(
                f"{described} declares receipt {found.superseded_receipt_id}, not the one its filename names",
                code="review_record_invalid",
            )
        return found

    def supersession_exists(self, superseded_receipt_id: str) -> bool:
        return self.abs(paths.supersession_rel(superseded_receipt_id)).is_file()

    def superseded_receipt_ids(self) -> tuple[str, ...]:
        return self._ids_in(paths.SUPERSESSIONS_DIR, "review_receipt")

    # provenance -------------------------------------------------------------
    def read_candidate_snapshot(self, candidate_hash: str) -> CandidateSnapshot:
        relative = paths.candidate_snapshot_rel(candidate_hash)
        described = f"Review candidate snapshot {relative}"
        found = CandidateSnapshot.from_record(self._read(relative, described), described)
        if found.candidate_hash != candidate_hash:
            raise ValidationError(
                f"{described} declares candidate {found.candidate_hash}, not the one its filename names",
                code="review_record_invalid",
            )
        return found

    def candidate_snapshot_exists(self, candidate_hash: str) -> bool:
        return self.abs(paths.candidate_snapshot_rel(candidate_hash)).is_file()

    def read_task_input(self, review_task_id: str) -> TaskInput:
        relative = paths.task_input_rel(review_task_id)
        described = f"Review task input {relative}"
        found = TaskInput.from_record(self._read(relative, described), described)
        if found.task_id != review_task_id:
            raise ValidationError(
                f"{described} declares task {found.task_id}, not the one its filename names",
                code="review_record_invalid",
            )
        return found

    def task_input_exists(self, review_task_id: str) -> bool:
        return self.abs(paths.task_input_rel(review_task_id)).is_file()

    def task_input_ids(self) -> tuple[str, ...]:
        return self._ids_in(paths.TASK_INPUTS_DIR, "review_task")

    def candidate_material_digest(self, candidate_hash: str) -> str:
        """The provenance identity of the stored Candidate snapshot, over its exact bytes.

        ``R3`` §5: this identifies *how* the Candidate is reconstructed. Two
        snapshots that rebuild the same artifact are still different provenance,
        which is why the digest is taken over the snapshot record rather than
        over the artifact it produces.
        """
        relative = paths.candidate_snapshot_rel(candidate_hash)
        self.read_candidate_snapshot(candidate_hash)  # refuse to digest something that does not parse
        return serialize.digest_of_text(self.read_text(relative, f"Review candidate snapshot {relative}"))

    def task_input_digest(self, review_task_id: str) -> str:
        """The provenance identity of the stored task input, over its exact bytes."""
        relative = paths.task_input_rel(review_task_id)
        self.read_task_input(review_task_id)
        return serialize.digest_of_text(self.read_text(relative, f"Review task input {relative}"))

    # activation -------------------------------------------------------------
    def activation_exists(self) -> bool:
        return self.abs(paths.WORK_TERMINAL_ACTIVATION_REL).is_file()

    def read_activation(self) -> WorkTerminalActivation | None:
        """The Work-terminal activation record, or ``None`` when review-v1 is not activated.

        P1 never creates one, so this returns ``None`` for every Project P1
        leaves behind. The reader exists so that the shape is frozen and
        validated now, and so that an absent record is a positive answer -
        "not activated" - rather than an unexamined gap.
        """
        if not self.activation_exists():
            return None
        relative = paths.WORK_TERMINAL_ACTIVATION_REL
        described = f"Review activation {relative}"
        return WorkTerminalActivation.from_record(self._read(relative, described), described)

    # helpers ----------------------------------------------------------------
    def _ids_in(self, directory_rel: str, kind: str) -> tuple[str, ...]:
        from ..ids import is_valid_id

        directory = self.abs(directory_rel)
        if not directory.is_dir():
            return ()
        found: list[str] = []
        for entry in sorted(directory.iterdir()):
            if entry.is_symlink() or not entry.is_file() or not entry.name.endswith(".yaml"):
                raise ValidationError(
                    f"{directory_rel} holds {entry.name}, which is not a canonical Review record file",
                    code="review_namespace_invalid",
                )
            # A supersession is named after the Receipt it supersedes, so its
            # directory is listed with ``review_receipt`` too.
            stem = entry.name[: -len(".yaml")]
            if not is_valid_id(stem, kind):
                raise ValidationError(
                    f"{directory_rel} holds {entry.name}, whose name is not a {kind} id",
                    code="review_namespace_invalid",
                )
            found.append(stem)
        return tuple(found)
