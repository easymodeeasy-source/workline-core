"""Canonical Review serialization and the digests taken over it.

A Review record has exactly one canonical rendering. The same semantic record
renders to the same UTF-8 bytes, with LF line ends, wherever and whenever it is
rendered, and the file on disk holds those bytes and nothing else. Every Review
digest is taken over that rendering (``R1``):

```text
digest = SHA-256(versioned canonical UTF-8 serialization bytes)
```

so a digest is a statement about the canonical bytes a reader can reproduce,
never about an in-memory mapping that happened to be assembled a particular way
and never about the Git blob the path holds after Git's own filters
(``R6`` binds that separately).

Determinism comes from one rule applied everywhere: mapping keys are emitted in
ascending Unicode code point order, at every depth. A record therefore cannot
render two ways because a caller built its mapping in a different order, and a
digest cannot change because a field moved. Ordered data - accepted task
descriptors, dependency lists - keeps the order it is given, because that order
is part of what the record says; only key order is normalized.

The schema/version identity is inside the canonical bytes, not beside them, so
a record that changes meaning under a new version can never collide with the
old one's digest.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .. import yamlish
from ..errors import ValidationError

#: The canonical text encoding of every Review record, and of the bytes every
#: Review digest is taken over.
ENCODING = "utf-8"

#: Every Review record carries these two fields. They are part of the canonical
#: bytes, so a version change is a digest change.
SCHEMA_KEY = "schema"
VERSION_KEY = "version"


def canonical_data(value: Any) -> Any:
    """``value`` with every mapping's keys in ascending code point order, at every depth.

    Sequences keep their order: a list in a Review record says something by
    being in the order it is in. Only key order is normalized, and only because
    a mapping says the same thing whatever order it was built in.

    Fails closed on anything the canonical form cannot represent exactly - a
    non-string key, a float, a value outside the scalar set the canonical
    writer supports - rather than rendering something a reader would read back
    as a different value.
    """
    if isinstance(value, dict):
        rendered: dict[str, Any] = {}
        for key in sorted(value, key=_key_order):
            rendered[key] = canonical_data(value[key])
        return rendered
    if isinstance(value, (list, tuple)):
        return [canonical_data(item) for item in value]
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    raise ValidationError(
        f"a Review record cannot hold {type(value).__name__}: {value!r}",
        code="review_record_invalid",
    )


def _key_order(key: object) -> str:
    if not isinstance(key, str):
        raise ValidationError(
            f"a Review record mapping key must be text, not {type(key).__name__}: {key!r}",
            code="review_record_invalid",
        )
    return key


def canonical_text(record: dict[str, Any]) -> str:
    """The one canonical rendering of ``record``: UTF-8 text, LF line ends, sorted keys.

    This is what the file holds and what every digest is taken over, so the two
    can never drift apart: there is one renderer and it is this one.
    """
    if not isinstance(record, dict):
        raise ValidationError("a Review record is a mapping", code="review_record_invalid")
    return yamlish.dump(canonical_data(record))


def canonical_bytes(record: dict[str, Any]) -> bytes:
    """The canonical text of ``record`` as the bytes a digest is taken over."""
    return canonical_text(record).encode(ENCODING)


def digest(record: dict[str, Any]) -> str:
    """``SHA-256`` of the canonical bytes of ``record``, lowercase hex.

    The versioned canonical form is inside those bytes, so this identifies the
    record as a reader reproduces it, not as a writer assembled it.
    """
    return hashlib.sha256(canonical_bytes(record)).hexdigest()


def digest_of_text(text: str) -> str:
    """``SHA-256`` of ``text`` encoded canonically, lowercase hex.

    For the case where the canonical bytes are already in hand - a file just
    read back, say - and re-rendering them would only risk saying something
    different from what is actually stored.
    """
    return hashlib.sha256(text.encode(ENCODING)).hexdigest()


def parse(text: str, described: str) -> dict[str, Any]:
    """The mapping ``text`` holds, or a STOP naming ``described``.

    A Review record is a mapping. Anything else - a sequence, a scalar, text
    outside the supported subset - is refused rather than coerced.
    """
    try:
        data = yamlish.load(text)
    except yamlish.YamlishError as exc:
        raise ValidationError(f"{described} unreadable: {exc}", code="review_record_invalid") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{described} is not a mapping", code="review_record_invalid")
    return data


def require_schema(record: dict[str, Any], schema: str, version: int, described: str) -> None:
    """Refuse ``record`` unless it declares exactly ``schema`` at exactly ``version``.

    An unknown or later version is never read by guessing which fields still
    mean what they used to. A record whose version this build does not
    implement is a STOP, so that a newer Project read by an older Workline
    fails closed instead of being half-understood.
    """
    found_schema = record.get(SCHEMA_KEY)
    found_version = record.get(VERSION_KEY)
    if found_schema != schema:
        raise ValidationError(
            f"{described} declares schema {found_schema!r}, not {schema!r}",
            code="review_record_invalid",
        )
    if found_version != version:
        raise ValidationError(
            f"{described} declares version {found_version!r}, which this build does not read "
            f"(it reads {schema} version {version})",
            code="review_record_version",
        )


def canonical_roundtrips(record: dict[str, Any]) -> bool:
    """Whether the canonical rendering of ``record`` reads back as the same data.

    A record is only canonical if a reader gets it back. This is what keeps a
    value that renders ambiguously - text a reader would take for a number, say
    - from being written and then read as something else.
    """
    expected = canonical_data(record)
    try:
        return yamlish.load(canonical_text(record)) == expected
    except yamlish.YamlishError:
        return False
