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

Reading is held to the same rules as writing:

```text
writer refuses indirection     reader refuses indirection
writer produces canonical bytes reader accepts only canonical bytes
writer treats facts as immutable reader enforces the immutable chain
```

Every directory is reached by the handle-bound, no-follow walk the writer uses
(:mod:`workline.review.fsafe`), so a symlink or junction anywhere in the
namespace is refused rather than followed to records outside the Project. Every
record passes the canonical read boundary (:func:`serialize.parse_canonical`)
before anything is taken from it.

``ProjectView`` / ``state.py`` never call anything here. Review records are not
lifecycle truth, and nothing in this module derives Work, Phase or Roadmap
state (``R1`` §10, ``R3`` §11).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..errors import ValidationError
from ..ids import is_valid_id
from ..store import ProjectStore
from . import fsafe, paths, records, serialize
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
    """One Review Run's validated, contiguous, full-snapshot generation chain.

    Holding one of these is the proof. It is constructed only when:

    * every generation from 1 to the last is present exactly once, its filename
      matches the generation inside it, and each names its predecessor and that
      predecessor's canonical digest (``R1`` §4);
    * the Run's kind and target never change;
    * every generation is a *full* snapshot of the durable task facts - an
      accepted task, and a settlement, once recorded, is carried forward
      exactly by every later generation, so a fact can never disappear by
      being left out (``R3`` §6);
    * every settlement names the generation it first appears in, which is
      later than the generation that accepted its task (``R3`` §3: the
      settlement is written as the next generation, after the accepted task
      reached the persistence boundary);
    * a sealed generation has no unsettled accepted task, and is followed, if
      at all, by an open generation (``R3`` §7-8).

    ``latest`` is therefore never "the highest number found" - it is the end of
    a chain that was validated as a whole.
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

    def has_generation(self, number: int) -> bool:
        return any(found.generation == number for found in self.generations)

    def generation(self, number: int) -> GateGeneration:
        for found in self.generations:
            if found.generation == number:
                return found
        raise ValidationError(
            f"Review Run {self.review_run_id} has no generation {number}", code="review_gate_chain"
        )

    def accepted_at(self, task_id: str) -> int | None:
        """The generation that first accepted ``task_id``, or ``None`` if none did."""
        for found in self.generations:
            if task_id in found.accepted_task_ids():
                return found.generation
        return None

    def accepted_descriptor(self, task_id: str) -> dict[str, Any] | None:
        for found in self.generations:
            for task in found.accepted_tasks:
                if str(task["task_id"]) == task_id:
                    return task
        return None

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


def _chain_invariants(review_run_id: str, generations: list[GateGeneration]) -> None:
    """Raise unless ``generations`` form one full-snapshot chain (see :class:`GateChain`)."""
    first = generations[0]
    accepted_at: dict[str, int] = {}
    for index, found in enumerate(generations):
        where = f"Review Run {review_run_id} generation {found.generation}"
        for name in ("review_kind", "target_identity"):
            if getattr(found, name) != getattr(first, name):
                raise ValidationError(
                    f"{where} changes {name}; a Review Run's kind and target are immutable facts",
                    code="review_gate_chain",
                )
        for task in found.accepted_tasks:
            accepted_at.setdefault(str(task["task_id"]), found.generation)
        if index > 0:
            previous = generations[index - 1]
            if previous.sealed and found.sealed:
                raise ValidationError(
                    f"{where} follows the seal at generation {previous.generation} with another seal; a sealed "
                    "generation is followed only by the open generation an invalidation creates",
                    code="review_gate_chain",
                )
            now_accepted = {str(task["task_id"]): task for task in found.accepted_tasks}
            for task in previous.accepted_tasks:
                task_id = str(task["task_id"])
                if task_id not in now_accepted:
                    raise ValidationError(
                        f"{where} drops accepted task {task_id}; a generation is a full snapshot and an accepted "
                        "task, once recorded, is carried forward by every later generation",
                        code="review_gate_chain",
                    )
                if now_accepted[task_id] != task:
                    raise ValidationError(
                        f"{where} carries accepted task {task_id} forward with a different descriptor; an accepted "
                        "task is an immutable fact",
                        code="review_gate_chain",
                    )
            now_settled = {str(task["task_id"]): task for task in found.settled_tasks}
            for task in previous.settled_tasks:
                task_id = str(task["task_id"])
                if task_id not in now_settled:
                    raise ValidationError(
                        f"{where} drops the settlement of task {task_id}; a settlement, once recorded, is carried "
                        "forward by every later generation",
                        code="review_gate_chain",
                    )
                if now_settled[task_id] != task:
                    raise ValidationError(
                        f"{where} carries the settlement of task {task_id} forward changed; a settlement is an "
                        "immutable fact",
                        code="review_gate_chain",
                    )
        before = {str(task["task_id"]) for task in generations[index - 1].settled_tasks} if index > 0 else set()
        for task in found.settled_tasks:
            task_id = str(task["task_id"])
            if task_id in before:
                continue  # carried forward, and already proven identical above
            if task["settled_generation"] != found.generation:
                raise ValidationError(
                    f"{where} first records the settlement of task {task_id} but names settled_generation "
                    f"{task['settled_generation']}; a settlement names the generation it first appears in",
                    code="review_gate_chain",
                )
            if found.generation <= accepted_at[task_id]:
                raise ValidationError(
                    f"{where} settles task {task_id} in the generation that accepted it; a settlement is written "
                    "as a later generation, once the accepted task has reached the persistence boundary",
                    code="review_gate_chain",
                )
        if found.sealed and found.unsettled_task_ids():
            raise ValidationError(
                f"{where} is sealed with unsettled accepted task(s): {', '.join(found.unsettled_task_ids())}",
                code="review_gate_chain",
            )


class ReviewStore:
    """Canonical Review record access for one Project."""

    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.root = store.root

    # paths ------------------------------------------------------------------
    def abs(self, relative: str) -> Path:
        return self.root / relative

    def _walk(self, relative_dir: str) -> fsafe.Chain | None:
        """The held, no-follow chain to ``relative_dir``; ``None`` if it does not exist yet."""
        return fsafe.walk(self.root, relative_dir.split("/"))

    def exists(self) -> bool:
        """Whether this Project has a Review namespace at all.

        A Project that has never used Review has none, and that is a valid
        Project (``R1`` §11). Nothing here creates it. An indirection where the
        namespace would be is refused, not reported as absent.
        """
        chain = self._walk(paths.REVIEW_DIR)
        if chain is None:
            return False
        chain.close()
        return True

    def entries(self, relative_dir: str) -> list[fsafe.Entry] | None:
        """The entries of ``relative_dir``, described without following any of them; ``None`` if it is absent."""
        chain = self._walk(relative_dir)
        if chain is None:
            return None
        with chain:
            return chain.last.entries()

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
    def read_bytes(self, relative: str) -> bytes | None:
        """The exact stored bytes at ``relative``, read through the held no-follow chain; ``None`` if absent."""
        paths.require_review_record_path(relative)
        parts = relative.split("/")
        chain = fsafe.walk(self.root, parts[:-1])
        if chain is None:
            return None
        with chain:
            return chain.last.read_file(parts[-1])

    def _read_record(
        self, relative: str, described: str, parse: Callable[[dict[str, Any], str], Any]
    ) -> tuple[Any, str]:
        """Read, prove canonical, and validate one record; ``(typed record, stored canonical text)``."""
        raw = self.read_bytes(relative)
        if raw is None:
            raise ValidationError(f"{described} not found: {relative}", code="review_record_missing")
        return self._parse(raw, described, parse)

    @staticmethod
    def _parse(raw: bytes, described: str, parse: Callable[[dict[str, Any], str], Any]) -> tuple[Any, str]:
        data, text = serialize.parse_canonical(raw, described)
        found = parse(data, described)
        # The typed record must say exactly what is stored - no field read one
        # way and rendered another - so the canonical bytes are its identity.
        if serialize.canonical_data(found.to_record()) != serialize.canonical_data(data):
            raise ValidationError(
                f"{described} does not round-trip through its schema unchanged", code="review_record_noncanonical"
            )
        return found, text

    # gate generations -------------------------------------------------------
    def run_ids(self) -> tuple[str, ...]:
        """Every Review Run that has a gate directory, in sorted order."""
        found_entries = self.entries(paths.GATES_DIR)
        if found_entries is None:
            return ()
        found: list[str] = []
        for entry in found_entries:
            if entry.is_indirection:
                raise ValidationError(
                    f"{paths.GATES_DIR}/{entry.name} is a symlink, junction or other reparse point",
                    code="review_containment",
                )
            if not entry.is_dir:
                raise ValidationError(
                    f"{paths.GATES_DIR} holds {entry.name}, which is not a plain Review Run directory",
                    code="review_namespace_invalid",
                )
            if not is_valid_id(entry.name, "review_run"):
                raise ValidationError(
                    f"{paths.GATES_DIR} holds {entry.name}, which is not a review_run id",
                    code="review_namespace_invalid",
                )
            found.append(entry.name)
        return tuple(found)

    def read_gate(self, review_run_id: str, generation: int) -> GateGeneration:
        relative = paths.gate_rel(review_run_id, generation)
        found, _ = self._read_record(relative, f"Review gate {relative}", GateGeneration.from_record)
        self._require_gate_identity(found, review_run_id, generation, relative)
        return found

    @staticmethod
    def _require_gate_identity(found: GateGeneration, review_run_id: str, generation: int, relative: str) -> None:
        if found.review_run_id != review_run_id:
            raise ValidationError(
                f"Review gate {relative} declares Review Run {found.review_run_id}, not {review_run_id}",
                code="review_record_invalid",
            )
        if found.generation != generation:
            raise ValidationError(
                f"Review gate {relative} declares generation {found.generation}, not {generation}",
                code="review_gate_chain",
            )

    def gate_chain(self, review_run_id: str) -> GateChain | None:
        """The validated chain for ``review_run_id``, or ``None`` when the run has none yet.

        Every generation is read inside one held chain to the run directory, so
        the whole chain is read from one directory that cannot be swapped out
        from under the reads. Validated as a whole (:class:`GateChain`) before
        anything is returned: the latest generation on its own cannot show that
        the chain behind it is intact.
        """
        chain = self._walk(paths.run_dir(review_run_id))
        if chain is None:
            return None
        with chain:
            numbers: list[int] = []
            for entry in chain.last.entries():
                if entry.name == paths.SERIALIZATION_TOKEN:
                    raise ValidationError(
                        f"{paths.run_dir(review_run_id)} holds a physical {paths.SERIALIZATION_TOKEN}; "
                        "that path is a scope-only token and is never created",
                        code="review_namespace_invalid",
                    )
                if entry.is_indirection:
                    raise ValidationError(
                        f"{paths.run_dir(review_run_id)}/{entry.name} is a symlink, junction or other reparse point",
                        code="review_containment",
                    )
                number = paths.generation_of_name(entry.name)
                if number is None or not entry.is_file:
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
                raw = chain.last.read_file(paths.generation_name(number))
                if raw is None:
                    raise ValidationError(f"Review gate {relative} disappeared while it was read", code="review_gate_chain")
                found, text = self._parse(raw, f"Review gate {relative}", GateGeneration.from_record)
                self._require_gate_identity(found, review_run_id, number, relative)
                if number > records.FIRST_GENERATION and found.previous_digest != digests[-1]:
                    raise ValidationError(
                        f"Review gate {relative} names predecessor digest {found.previous_digest}, "
                        f"but generation {number - 1} canonically digests to {digests[-1]}",
                        code="review_gate_chain",
                    )
                generations.append(found)
                digests.append(serialize.digest_of_text(text))
        _chain_invariants(review_run_id, generations)
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
        found, _ = self._read_record(relative, f"Review receipt {relative}", Receipt.from_record)
        if found.receipt_id != receipt_id:
            raise ValidationError(
                f"Review receipt {relative} declares receipt {found.receipt_id}, not the one its filename names",
                code="review_record_invalid",
            )
        return found

    def receipt_exists(self, receipt_id: str) -> bool:
        return self.read_bytes(paths.receipt_rel(receipt_id)) is not None

    def receipt_ids(self) -> tuple[str, ...]:
        return self._ids_in(paths.RECEIPTS_DIR, "review_receipt")

    # consumptions -----------------------------------------------------------
    def read_consumption(self, consumption_id: str) -> Consumption:
        relative = paths.consumption_rel(consumption_id)
        found, _ = self._read_record(relative, f"Review consumption {relative}", Consumption.from_record)
        if found.consumption_id != consumption_id:
            raise ValidationError(
                f"Review consumption {relative} declares consumption {found.consumption_id}, not the one its "
                "filename names",
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
        found, _ = self._read_record(relative, f"Review supersession {relative}", Supersession.from_record)
        if found.superseded_receipt_id != superseded_receipt_id:
            raise ValidationError(
                f"Review supersession {relative} declares receipt {found.superseded_receipt_id}, not the one its "
                "filename names",
                code="review_record_invalid",
            )
        return found

    def supersession_exists(self, superseded_receipt_id: str) -> bool:
        return self.read_bytes(paths.supersession_rel(superseded_receipt_id)) is not None

    def superseded_receipt_ids(self) -> tuple[str, ...]:
        # A supersession is named after the Receipt it supersedes.
        return self._ids_in(paths.SUPERSESSIONS_DIR, "review_receipt")

    # provenance -------------------------------------------------------------
    def read_candidate_snapshot(self, candidate_hash: str) -> CandidateSnapshot:
        found, _ = self._read_candidate_snapshot(candidate_hash)
        return found

    def _read_candidate_snapshot(self, candidate_hash: str) -> tuple[CandidateSnapshot, str]:
        relative = paths.candidate_snapshot_rel(candidate_hash)
        found, text = self._read_record(relative, f"Review candidate snapshot {relative}", CandidateSnapshot.from_record)
        if found.candidate_hash != candidate_hash:
            raise ValidationError(
                f"Review candidate snapshot {relative} declares candidate {found.candidate_hash}, not the one its "
                "filename names",
                code="review_record_invalid",
            )
        return found, text

    def candidate_snapshot_exists(self, candidate_hash: str) -> bool:
        return self.read_bytes(paths.candidate_snapshot_rel(candidate_hash)) is not None

    def read_task_input(self, review_task_id: str) -> TaskInput:
        found, _ = self._read_task_input(review_task_id)
        return found

    def _read_task_input(self, review_task_id: str) -> tuple[TaskInput, str]:
        relative = paths.task_input_rel(review_task_id)
        found, text = self._read_record(relative, f"Review task input {relative}", TaskInput.from_record)
        if found.task_id != review_task_id:
            raise ValidationError(
                f"Review task input {relative} declares task {found.task_id}, not the one its filename names",
                code="review_record_invalid",
            )
        return found, text

    def task_input_exists(self, review_task_id: str) -> bool:
        return self.read_bytes(paths.task_input_rel(review_task_id)) is not None

    def task_input_ids(self) -> tuple[str, ...]:
        return self._ids_in(paths.TASK_INPUTS_DIR, "review_task")

    def candidate_snapshot_hashes(self) -> tuple[str, ...]:
        """Every stored Candidate snapshot, by the candidate hash its filename must be, in sorted order.

        Read the way every Review directory is: no indirection, plain ``.yaml``
        files only, and a filename that is a lowercase-hex SHA-256 - so an
        unreferenced snapshot with an unknown name, a nested directory, or a
        reparse point in ``candidate-snapshots/`` fails closed here rather than
        being missed because nothing happened to reference it (``R1`` §11).
        """
        return self._stems_in(
            paths.CANDIDATE_SNAPSHOTS_DIR, lambda stem: records.DIGEST_RE.match(stem) is not None, "candidate_hash"
        )

    def candidate_material_digest(self, candidate_hash: str) -> str:
        """The provenance identity of the stored Candidate snapshot, over its exact canonical bytes.

        ``R3`` §5: this identifies *how* the Candidate is reconstructed. Two
        snapshots that rebuild the same artifact are still different provenance,
        which is why the digest is taken over the snapshot record rather than
        over the artifact it produces - and only over bytes the canonical read
        boundary has accepted.
        """
        _, text = self._read_candidate_snapshot(candidate_hash)
        return serialize.digest_of_text(text)

    def task_input_digest(self, review_task_id: str) -> str:
        """The provenance identity of the stored task input, over its exact canonical bytes."""
        _, text = self._read_task_input(review_task_id)
        return serialize.digest_of_text(text)

    def provenance_problems(self, task: dict[str, Any], accepted_generation: int) -> list[tuple[str, str]]:
        """Every way an accepted task, its stored task input and its stored Candidate snapshot disagree.

        ``(code, message)`` pairs; empty when the three agree exactly. The
        same identity appears in more than one of them - the reviewer, the task
        slot, the Candidate, the Context - and a matching task-input digest is
        not enough: every duplicated identity must be the same everywhere it
        appears, or a descriptor could name one reviewer while the stored
        request names another (``R3`` §4-5).
        """
        problems: list[tuple[str, str]] = []
        task_id = str(task["task_id"])
        where = f"accepted task {task_id}"
        if not self.task_input_exists(task_id):
            return [("review_record_missing", f"{where} has no stored task input")]
        try:
            task_input, task_input_text = self._read_task_input(task_id)
        except ValidationError as exc:
            return [(exc.code or "review_record_invalid", str(exc))]
        stored_digest = serialize.digest_of_text(task_input_text)
        if stored_digest != task["task_input_digest"]:
            problems.append(
                ("review_provenance_conflict",
                 f"{where} bound task_input_digest {task['task_input_digest']}, but the stored task input digests "
                 f"to {stored_digest}")
            )
        for name in (
            "task_slot",
            "task_kind",
            "reviewer_identity",
            "reviewer_version",
            "request_digest",
            "candidate_hash",
            "reconstruction_mode",
            "candidate_material_digest",
            "review_context_hash",
            "effective_policy_hash",
        ):
            if getattr(task_input, name) != task[name]:
                problems.append(
                    ("review_provenance_conflict",
                     f"{where} says {name} {task[name]!r}, and its stored task input says "
                     f"{getattr(task_input, name)!r}")
                )
        if task_input.accepted_generation != accepted_generation:
            problems.append(
                ("review_provenance_conflict",
                 f"{where} was accepted at generation {accepted_generation}, and its stored task input says "
                 f"accepted_generation {task_input.accepted_generation}")
            )
        candidate_hash = str(task["candidate_hash"])
        if not self.candidate_snapshot_exists(candidate_hash):
            problems.append(("review_record_missing", f"{where} has no stored candidate snapshot {candidate_hash}"))
            return problems
        try:
            snapshot, snapshot_text = self._read_candidate_snapshot(candidate_hash)
        except ValidationError as exc:
            problems.append((exc.code or "review_record_invalid", str(exc)))
            return problems
        material = serialize.digest_of_text(snapshot_text)
        for bound, described in ((task["candidate_material_digest"], "it"), (task_input.candidate_material_digest, "its stored task input")):
            if bound != material:
                problems.append(
                    ("review_provenance_conflict",
                     f"{where}: {described} binds candidate_material_digest {bound}, but the stored snapshot "
                     f"digests to {material}")
                )
        if snapshot.reconstruction_mode != task["reconstruction_mode"]:
            problems.append(
                ("review_provenance_conflict",
                 f"{where} names reconstruction mode {task['reconstruction_mode']}, but the stored snapshot is "
                 f"{snapshot.reconstruction_mode}")
            )
        return problems

    # activation -------------------------------------------------------------
    def activation_exists(self) -> bool:
        return self.read_bytes(paths.WORK_TERMINAL_ACTIVATION_REL) is not None

    def read_activation(self) -> WorkTerminalActivation | None:
        """The Work-terminal activation record, or ``None`` when review-v1 is not activated.

        P1 never creates one, so this returns ``None`` for every Project P1
        leaves behind. The reader exists so that the shape is frozen and
        validated now, and so that an absent record is a positive answer -
        "not activated" - rather than an unexamined gap.
        """
        relative = paths.WORK_TERMINAL_ACTIVATION_REL
        raw = self.read_bytes(relative)
        if raw is None:
            return None
        found, _ = self._parse(raw, f"Review activation {relative}", WorkTerminalActivation.from_record)
        return found

    # helpers ----------------------------------------------------------------
    def _ids_in(self, directory_rel: str, kind: str) -> tuple[str, ...]:
        return self._stems_in(directory_rel, lambda stem: is_valid_id(stem, kind), f"{kind} id")

    def _stems_in(
        self, directory_rel: str, valid_stem: Callable[[str], bool], name_description: str
    ) -> tuple[str, ...]:
        """The ``.yaml`` stems of ``directory_rel``, each a plain in-Project file whose name ``valid_stem`` accepts.

        The one enumeration every flat Review record directory is read through:
        no indirection, no nested directory, no non-``.yaml`` entry, and no
        filename that is not the identity a record there is named by.
        """
        found_entries = self.entries(directory_rel)
        if found_entries is None:
            return ()
        found: list[str] = []
        for entry in found_entries:
            if entry.is_indirection:
                raise ValidationError(
                    f"{directory_rel}/{entry.name} is a symlink, junction or other reparse point",
                    code="review_containment",
                )
            if not entry.is_file or not entry.name.endswith(".yaml"):
                raise ValidationError(
                    f"{directory_rel} holds {entry.name}, which is not a canonical Review record file",
                    code="review_namespace_invalid",
                )
            stem = entry.name[: -len(".yaml")]
            if not valid_stem(stem):
                raise ValidationError(
                    f"{directory_rel} holds {entry.name}, whose name is not a {name_description}",
                    code="review_namespace_invalid",
                )
            found.append(stem)
        return tuple(found)
