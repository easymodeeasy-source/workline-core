"""ULID-like stable identifier generation.

Identifiers are ``<prefix>_<26 Crockford base32 chars>``. The 26 characters
encode 48 bits of millisecond timestamp followed by 80 random bits, which is
the ULID layout. Only the standard library is used.
"""

from __future__ import annotations

import re
import secrets
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")

PREFIXES = {
    "mutation": "mut",
    "roadmap": "r",
    "phase": "p",
    "work": "w",
    "relation": "rel",
    "event": "evt",
    "derivation": "der",
    # Review (``skills/review``). Review allocates its stable identities here,
    # through the same generator and the same ``Mutation.reserve_id`` semantics
    # as every other kind, so that a Review ID is replay-stable for exactly the
    # reason a Work ID is. A Review generation is not among them: it is a
    # positive integer scoped to one Review Run, and Candidate / Context /
    # Policy / Coverage / Adjudication / obligation identities are digests of
    # content rather than allocated IDs.
    "review_run": "rr",
    "review_receipt": "rcp",
    "review_consumption": "rcs",
    "review_task": "rtk",
    # P4 (§12.5 / §12.8): a normalized Finding and a Repair Batch are stable
    # owner-mutation reservations too, so a replay reserves the same identity.
    "review_finding": "rfd",
    "review_repair_batch": "rrb",
    # P5 (§28.4): the only genuinely new durable history facts - a later or
    # cross-run relation, and Human Decision Evidence - get their own Review
    # kinds, never the Project-domain ``relation`` kind, and prefixes that
    # cannot be read as ``rel_`` or ``rr_``. Run / Finding / Repair history
    # reuses the identity of its immutable source record and allocates nothing.
    "review_relation": "rhr",
    "review_decision": "rhd",
}

# Longest first, so that ``rr_``/``rcp_``/``rcs_``/``rtk_``/``rfd_``/``rrb_``/``rhr_``/``rhd_``
# are read as themselves rather than as the Roadmap prefix ``r`` followed by text.
_ID_RE = re.compile(r"^(mut|rel|rcp|rcs|rtk|rfd|rrb|rhr|rhd|rr|evt|der|r|p|w)_([0-9A-HJKMNP-TV-Z]{26})$")


def new_ulid(now_ms: int | None = None) -> str:
    """Return a fresh 26 character ULID-like string."""
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    value = (now_ms & ((1 << 48) - 1)) << 80 | int.from_bytes(secrets.token_bytes(10), "big")
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def new_id(kind: str) -> str:
    """Return a new stable ID for ``kind`` (``mutation`` / ``roadmap`` / ...)."""
    return f"{PREFIXES[kind]}_{new_ulid()}"


def kind_of(identifier: str) -> str | None:
    """Return the entity kind encoded in ``identifier`` or ``None`` if malformed."""
    match = _ID_RE.match(identifier or "")
    if not match:
        return None
    prefix = match.group(1)
    for kind, candidate in PREFIXES.items():
        if candidate == prefix:
            return kind
    return None


def is_valid_id(identifier: str, kind: str | None = None) -> bool:
    found = kind_of(identifier)
    if found is None:
        return False
    return kind is None or found == kind
