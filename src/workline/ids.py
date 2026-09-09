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
}

_ID_RE = re.compile(r"^(mut|r|p|w|rel|evt|der)_([0-9A-HJKMNP-TV-Z]{26})$")


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
