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
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from ..errors import ValidationError
from ..store import EVENT_LIFECYCLE_FIELDS, Event

if TYPE_CHECKING:  # pragma: no cover
    from .hermetic import HermeticGit

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
