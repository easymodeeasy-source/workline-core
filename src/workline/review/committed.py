"""Committed Review reading: the P1 reader over one commit's Git objects, and what a history added.

``ReviewStore`` reads the working tree. The publication barrier, the committed
planning proof and recovery discovery must read the same records from committed
objects instead - raw blobs, never checked-out bytes - with the same P1 parser
and record classes. :class:`CommittedReviewStore` is exactly that: the unchanged
``ReviewStore``, whose one byte source and one directory listing are the tree of
a given commit (``git ls-tree``, ``git cat-file blob``), so every canonical-bytes
check, every schema and version check, every chain rule and every uniqueness
index is the P1 one, applied to what the commit holds.

The history reads name what was *added* anywhere in a commit's history, every
parent of a merge followed - a path deleted or reverted afterwards is still
found, because what was once added is what the barrier must account for.

Nothing here reads a runtime record, a note, a remote or a working-tree file,
and nothing evaluates an attribute: committed objects alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import gitcmd
from ..errors import ValidationError
from ..store import ProjectStore
from . import fsafe, paths, records, serialize
from .records import CandidateSnapshot, GateGeneration
from .store import GateChain, ReviewStore, _chain_invariants

REGULAR_FILE_MODE = "100644"


def _unreadable(message: str) -> ValidationError:
    return ValidationError(message, code="review_record_missing")


class CommittedReviewStore(ReviewStore):
    """The P1 Review reader over the tree of one commit.

    ``read_bytes`` returns the raw blob a canonical Review path holds in that
    tree (only a regular ``100644`` blob is a record), ``entries`` lists a
    directory of that tree, and ``gate_chain`` validates a Run's chain from it;
    everything built on them - parsing, identity checks, provenance, indexes -
    is inherited unchanged.
    """

    def __init__(self, repo: Path, commit: str) -> None:
        super().__init__(ProjectStore(repo))
        self.repo = Path(repo)
        self.commit = commit
        listed = gitcmd.tree_entries(self.repo, commit, [paths.REVIEW_DIR], recursive=True, trees=True)
        if listed is None:
            raise _unreadable(f"Git cannot list the Review records of {commit}")
        self._tree: dict[str, gitcmd.TreeEntry] = {entry.path: entry for entry in listed}

    # the one byte source ---------------------------------------------------
    def entry(self, relative: str) -> gitcmd.TreeEntry | None:
        return self._tree.get(relative)

    def blob_id(self, relative: str) -> str | None:
        """The blob ID of the regular file record at ``relative``; None when the commit holds none there."""
        found = self._tree.get(relative)
        if found is None or found.type != "blob" or found.mode != REGULAR_FILE_MODE:
            return None
        return found.oid

    def exists(self) -> bool:
        return any(path.startswith(paths.REVIEW_DIR + "/") for path in self._tree)

    def entries(self, relative_dir: str) -> list[fsafe.Entry] | None:
        prefix = relative_dir.rstrip("/") + "/"
        if relative_dir != paths.REVIEW_DIR and self._tree.get(relative_dir, None) is None:
            return None
        if relative_dir == paths.REVIEW_DIR and not self.exists():
            return None
        found: list[fsafe.Entry] = []
        for path, entry in sorted(self._tree.items()):
            if not path.startswith(prefix) or "/" in path[len(prefix):]:
                continue
            name = path[len(prefix):]
            indirection = entry.mode == "120000" or entry.type == "commit"
            found.append(
                fsafe.Entry(
                    name,
                    is_dir=entry.type == "tree",
                    is_file=entry.type == "blob" and entry.mode == REGULAR_FILE_MODE,
                    is_indirection=indirection,
                )
            )
        return found

    def read_bytes(self, relative: str) -> bytes | None:
        paths.require_review_record_path(relative)
        found = self._tree.get(relative)
        if found is None:
            return None
        if found.type != "blob" or found.mode != REGULAR_FILE_MODE:
            raise ValidationError(
                f"{self.commit} holds {relative} as {found.type} {found.mode}, not a regular file record",
                code="review_record_invalid",
            )
        data = gitcmd.read_blob(self.repo, found.oid)
        if data is None:
            raise _unreadable(f"Git cannot read the blob {found.oid} {self.commit} holds at {relative}")
        return data

    def gate_chain(self, review_run_id: str) -> GateChain | None:
        run_dir = paths.run_dir(review_run_id)
        listed = self.entries(run_dir)
        if listed is None:
            return None
        numbers: list[int] = []
        for entry in listed:
            if entry.name == paths.SERIALIZATION_TOKEN:
                raise ValidationError(
                    f"{self.commit} holds {run_dir}/{paths.SERIALIZATION_TOKEN}, a scope-only token that is never created",
                    code="review_namespace_invalid",
                )
            if entry.is_indirection:
                raise ValidationError(f"{self.commit} holds {run_dir}/{entry.name} as an indirection", code="review_containment")
            number = paths.generation_of_name(entry.name)
            if number is None or not entry.is_file:
                raise ValidationError(
                    f"{self.commit} holds {run_dir}/{entry.name}, which is not a gate generation file",
                    code="review_namespace_invalid",
                )
            numbers.append(number)
        if not numbers:
            return None
        numbers.sort()
        expected = list(range(records.FIRST_GENERATION, records.FIRST_GENERATION + len(numbers)))
        if numbers != expected:
            raise ValidationError(
                f"Review Run {review_run_id} in {self.commit} has a non-contiguous chain: found {numbers}",
                code="review_gate_chain",
            )
        generations: list[GateGeneration] = []
        digests: list[str] = []
        for number in numbers:
            relative = paths.gate_rel(review_run_id, number)
            raw = self.read_bytes(relative)
            if raw is None:
                raise _unreadable(f"{self.commit} lost {relative} while it was read")
            found, text = self._parse(raw, f"Review gate {relative} at {self.commit}", GateGeneration.from_record)
            self._require_gate_identity(found, review_run_id, number, relative)
            if number > records.FIRST_GENERATION and found.previous_digest != digests[-1]:
                raise ValidationError(
                    f"Review gate {relative} at {self.commit} names predecessor digest {found.previous_digest}, "
                    f"but generation {number - 1} digests to {digests[-1]}",
                    code="review_gate_chain",
                )
            generations.append(found)
            digests.append(serialize.digest_of_text(text))
        _chain_invariants(review_run_id, generations)
        return GateChain(review_run_id, tuple(generations), tuple(digests))

    # conveniences ------------------------------------------------------------
    def read_record_text(self, relative: str) -> str | None:
        raw = self.read_bytes(relative)
        if raw is None:
            return None
        _, text = serialize.parse_canonical(raw, f"{relative} at {self.commit}")
        return text

    def runs_with_candidate(self, candidate_hash: str) -> list[str]:
        """The Runs in this tree whose generation 1 names ``candidate_hash``, read by the P1 reader."""
        found: list[str] = []
        for review_run_id in self.run_ids():
            relative = paths.gate_rel(review_run_id, records.FIRST_GENERATION)
            raw = self.read_bytes(relative)
            if raw is None:
                continue
            gate, _ = self._parse(raw, f"Review gate {relative} at {self.commit}", GateGeneration.from_record)
            if gate.candidate_hash == candidate_hash:
                found.append(review_run_id)
        return found


# --------------------------------------------------------------------------- what a history added

def added_in_history(repo: Path, commit: str, targets: "list[str] | tuple[str, ...]") -> list[tuple[str, list[str]]]:
    """Every commit in ``commit``'s history that adds any of ``targets``, with the paths it adds; STOP-free, raises on no answer."""
    found = gitcmd.added_paths(repo, commit, list(targets))
    if found is None:
        raise _unreadable(f"Git cannot read what the history of {commit} added under {', '.join(targets)}")
    return found


def adding_commits(repo: Path, commit: str, path: str) -> list[str]:
    """The commits in ``commit``'s history that add exactly ``path``."""
    return [listed for listed, added in added_in_history(repo, commit, [path]) if path in added]


def read_candidate_snapshot_blob(repo: Path, adding_commit: str, path: str) -> CandidateSnapshot:
    """The Candidate snapshot ``adding_commit`` holds at ``path``, read by the P1 reader from its raw blob."""
    raw = gitcmd.blob_at(repo, adding_commit, path)
    if raw is None:
        raise _unreadable(f"Git cannot read {path} at {adding_commit}")
    described = f"Review candidate snapshot {path} at {adding_commit}"
    found, _ = ReviewStore._parse(raw, described, CandidateSnapshot.from_record)
    expected = path.rsplit("/", 1)[-1][: -len(".yaml")] if path.endswith(".yaml") else None
    if found.candidate_hash != expected:
        raise ValidationError(f"{described} declares candidate {found.candidate_hash}, not the one its name names",
                              code="review_record_invalid")
    return found


def parse_record(raw: bytes, described: str, parse: Any) -> tuple[Any, str]:
    """The P1 read boundary over raw bytes: canonical, schema-valid, round-tripping."""
    return ReviewStore._parse(raw, described, parse)
