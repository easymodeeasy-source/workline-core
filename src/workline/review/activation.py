"""``work-terminal-activation-digest-v1``: the one implementation (P3 F1 §9, P1 R4 §4.1).

The activation record (``.workline/review/activation/work-terminal-v1.yaml``)
fixes which Events of a Project are pre-activation legacy: its first
``legacy_event_count`` parsed Events, bound by ``legacy_event_prefix_sha256``.
Everything that produces or proves that binding computes it here, so the
producer that writes the record, the review-v1 START that is admitted by it,
the C-2 proofs that re-check it at K1 and K2, and the validation that classifies
a Project's completions by it can never disagree about what the digest means:

```text
1. read the event log (a commit's blob, or the working tree's bytes)
2. parse it exactly as the canonical Event reader does: blank physical lines are
   ignored, CRLF and a lone CR read as LF, every other line is one complete Event
3. N = the number of parsed Events
4. each of the first N, as the canonical record form of its Event - every
   schema-allowed field, the carried metadata included - rendered as JSON with
   keys sorted by code point, the separators "," and ":", UTF-8 without ASCII
   escaping, no NaN or Infinity, and exactly one LF after it
5. legacy_event_prefix_sha256 = SHA-256 of those lines in event order, lowercase hex
```

This is deliberately NOT the Review record renderer, and the record's own
digest (``serialize.digest`` of the activation record, which F2 binds into a
Candidate and a Context) is a different identity over different material: that
one is over the record, this one is over the Events (F1 §9.2, F2 §11).

Hashing parsed Events rather than raw bytes is what makes the digest stable
across CRLF-to-LF and blank-line normalization, and still change whenever a
pre-activation Event is changed, reordered, deleted, inserted or has its
metadata mutated. Its identity is the pair (this algorithm, the Event schema
in force): an Event carries its non-lifecycle metadata through the carrier of
Gate 1, and that metadata is part of what is hashed.

Nothing here reads a working tree path by itself, holds a lock or writes.
``None`` always means "cannot be shown", and never "legacy".

The record itself is committed canonical authority (F1 §6): a Project is
activated by the record its current HEAD commits, held unchanged by its working
tree, and never by bytes that only look like one. :func:`current_activation` is
the one check of that, which START's entry and the Project's validation share.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from ..errors import ValidationError
from ..store import EVENT_LIFECYCLE_FIELDS, Event
from .paths import WORK_TERMINAL_ACTIVATION_REL
from .records import WorkTerminalActivation

if TYPE_CHECKING:  # pragma: no cover
    from .hermetic import HermeticGit, ReadOnlyGit
    from .store import ReviewStore

#: The algorithm this module implements, by its frozen name (F1 §9.4).
DIGEST_ALGORITHM = "work-terminal-activation-digest-v1"


def parse_event_log(data: bytes) -> list[dict[str, Any]] | None:
    """The canonical record form of every Event ``data`` holds, in order; ``None`` when it is not an event log.

    Parsed exactly as the canonical Event reader parses (``ProjectStore.read_events``):
    UTF-8, CRLF and a lone CR read as LF, a record ends at LF, a blank physical
    line is skipped, and every other line is one JSON object holding the four
    lifecycle fields as text. Each is returned as its Event's record form, so a
    field the Event model would not carry could never be hashed either.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    parsed: list[dict[str, Any]] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(record, dict) or not all(isinstance(record.get(key), str) for key in EVENT_LIFECYCLE_FIELDS):
            return None
        try:
            parsed.append(Event.from_record(record).to_record())
        except ValidationError:
            return None
    return parsed


def prefix_digest(records: Sequence[Mapping[str, Any]], count: int) -> str | None:
    """The digest of the first ``count`` of ``records``; ``None`` when there are fewer, or one is not plain JSON."""
    if type(count) is not int or count < 0 or len(records) < count:
        return None
    try:
        canonical = b"".join(
            json.dumps(dict(record), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
            + b"\n"
            for record in records[:count]
        )
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(canonical).hexdigest()


def committed_event_records(git: "HermeticGit", commit: str) -> list[dict[str, Any]] | None:
    """The parsed Events of ``commit``'s committed event log, read through class B; ``None`` when unreadable.

    The committed blob, never the working tree: what a commit holds is what
    every clone of it holds (F1 §9.5).
    """
    from .workcommit import EVENT_LOG  # here, not at import: the Review package is imported by the Mutation Controller

    found = git.run_bytes("cat-file", "blob", f"{commit}:{EVENT_LOG}")
    if not found.ok:
        return None
    return parse_event_log(found.stdout)


def committed_prefix_digest(git: "HermeticGit", commit: str, count: int) -> str | None:
    """The digest over the first ``count`` Events of ``commit``'s event log; ``None`` when that cannot be shown.

    An unreadable log, a line that is not an Event, or fewer than ``count``
    Events all make the prefix unprovable - never legacy.
    """
    records = committed_event_records(git, commit)
    return None if records is None else prefix_digest(records, count)


# --------------------------------------------------------------------------- the record as committed authority

#: How the working tree and current HEAD can hold the activation record. Only ``CURRENT`` can be activation.
NOT_ACTIVATED = "not_activated"  # neither holds one
CURRENT = "current"  # both hold exactly the same bytes
UNCOMMITTED = "uncommitted"  # the working tree holds one that HEAD does not commit
MISSING = "missing"  # HEAD commits one that the working tree does not hold
CHANGED = "changed"  # both hold one, and the bytes differ


class CommittedRecordUnreadable(ValidationError):
    """What HEAD holds at the activation path cannot be read as a record: never taken for "absent"."""


@dataclass(frozen=True)
class Currentness:
    """The activation record as current HEAD commits it and as the working tree holds it."""

    head: str | None
    state: str
    #: Read by the P1 reader from the exact bytes both hold; present only when ``state`` is ``CURRENT``.
    record: WorkTerminalActivation | None = None

    def conflict(self) -> str | None:
        """Why the working tree and HEAD disagree about the activation; ``None`` when they do not."""
        if self.state == UNCOMMITTED:
            return (f"the working tree holds an activation record that {self.head or 'HEAD'} does not commit; an "
                    "uncommitted record is never activation, and is never adopted")
        if self.state == MISSING:
            return (f"{self.head} commits an activation record that the working tree does not hold; a committed "
                    "activation is never read as absent")
        if self.state == CHANGED:
            return f"the working tree's activation record is not the record {self.head} commits"
        return None


def head_commit(git: "HermeticGit | ReadOnlyGit") -> str | None:
    """The commit HEAD names, read through class B; ``None`` when HEAD names none yet."""
    found = git.run_bytes("rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    commit = found.stdout.decode("ascii", "replace").strip() if found.ok else ""
    return commit or None


def committed_record_bytes(git: "HermeticGit | ReadOnlyGit", commit: str) -> bytes | None:
    """The exact blob ``commit`` holds at the activation path, read through class B; ``None`` when it holds none.

    Only a regular ``100644`` blob is a record. Anything else the commit holds
    there, and a listing or a blob Git cannot give, is
    :class:`CommittedRecordUnreadable` rather than absence.
    """
    listed = git.run_bytes("ls-tree", "-z", "--full-tree", commit, "--", WORK_TERMINAL_ACTIVATION_REL)
    if not listed.ok:
        raise CommittedRecordUnreadable(f"Git cannot list what {commit} holds at {WORK_TERMINAL_ACTIVATION_REL}",
                                        code="review_record_missing")
    held: list[str] | None = None
    for item in listed.stdout.split(b"\0"):
        if not item:
            continue
        head, separator, raw_path = item.partition(b"\t")
        fields = head.split(b" ")
        if not separator or len(fields) != 3:
            raise CommittedRecordUnreadable(f"Git's listing of {commit} holds an entry this reader cannot classify",
                                            code="review_record_invalid")
        if raw_path.decode("utf-8", "surrogateescape") == WORK_TERMINAL_ACTIVATION_REL:
            held = [field.decode("ascii", "replace") for field in fields]
    if held is None:
        return None
    mode, kind, oid = held
    if kind != "blob" or mode != "100644":
        raise CommittedRecordUnreadable(
            f"{commit} holds {WORK_TERMINAL_ACTIVATION_REL} as {kind} {mode}, not a record", code="review_record_invalid"
        )
    blob = git.run_bytes("cat-file", "blob", oid)
    if not blob.ok:
        raise CommittedRecordUnreadable(
            f"Git cannot read the blob {oid} {commit} holds at {WORK_TERMINAL_ACTIVATION_REL}", code="review_record_missing"
        )
    return blob.stdout


def read_record(raw: bytes) -> WorkTerminalActivation:
    """The activation record ``raw`` holds, through the P1 read boundary (canonical, schema-valid, round-tripping)."""
    from .committed import parse_record  # here, not at import: it brings in the whole Review store

    found, _ = parse_record(raw, f"Review activation {WORK_TERMINAL_ACTIVATION_REL}", WorkTerminalActivation.from_record)
    return found


def current_activation(review: "ReviewStore", git: "HermeticGit | ReadOnlyGit", head: str | None) -> Currentness:
    """The activation at ``head``: the record that commit holds, exactly as the working tree holds it (F1 §6).

    ```text
    working tree   HEAD       state
    absent         absent     NOT_ACTIVATED   genuinely not activated
    present        absent     UNCOMMITTED     never activation, and never adopted
    absent         present    MISSING         never read as "not activated"
    bytes differ              CHANGED         neither copy is taken
    the same bytes            CURRENT         read by the P1 reader: malformed or unsupported is its refusal
    ```

    The working tree is read by the Review store's own no-follow reader, and
    HEAD's blob through class B; the two are compared as exact bytes before
    either is parsed. Whether a ``CURRENT`` record's prefix proves is the
    caller's question (:func:`committed_prefix_digest`), asked of the event log
    it admits or classifies.
    """
    working = review.read_bytes(WORK_TERMINAL_ACTIVATION_REL)
    committed = None if head is None else committed_record_bytes(git, head)
    if working is None and committed is None:
        return Currentness(head, NOT_ACTIVATED)
    if committed is None:
        return Currentness(head, UNCOMMITTED)
    if working is None:
        return Currentness(head, MISSING)
    if working != committed:
        return Currentness(head, CHANGED)
    return Currentness(head, CURRENT, read_record(committed))
