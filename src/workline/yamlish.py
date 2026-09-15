"""Minimal YAML subset reader / writer (standard library only).

Workline canonical files are written and read only by Workline, so a strict
subset is sufficient: block mappings, block sequences, empty flow ``[]`` /
``{}``, and scalars (``str`` / ``int`` / ``bool`` / ``null``). Strings that
could be misread are emitted double-quoted with JSON escapes, which is valid
YAML. Anything outside the subset raises ``YamlishError`` (fail closed).

A string may hold any text, U+0085 / U+2028 / U+2029 included. Those three
end a line for ``str.splitlines`` but not for JSON, so the writer escapes them
and the reader never ends a line at one inside a double-quoted scalar
(:data:`LINE_SEPARATORS`).
"""

from __future__ import annotations

import json
import re
from typing import Any

INDENT = "  "

_PLAIN_SAFE = re.compile("^[A-Za-z0-9_　-鿿＀-￯][A-Za-z0-9_./:@+ 　-鿿＀-￯-]*$")
_INT_RE = re.compile(r"^-?(0|[1-9][0-9]*)$")
_RESERVED = {
    "true", "false", "null", "yes", "no", "on", "off", "~",
    "True", "False", "Null", "TRUE", "FALSE", "NULL", "Yes", "No", "On", "Off", "YES", "NO", "ON", "OFF",
}


#: The line boundaries ``str.splitlines`` knows that JSON leaves as they are when it keeps non-ASCII text:
#: NEL, LINE SEPARATOR and PARAGRAPH SEPARATOR. Inside a string they are text, never where a line ends.
LINE_SEPARATORS = ("\x85", "\N{LINE SEPARATOR}", "\N{PARAGRAPH SEPARATOR}")


class YamlishError(ValueError):
    """Raised when text is outside the supported YAML subset."""


def escape_line_separators(json_text: str) -> str:
    """``json_text`` with every U+0085 / U+2028 / U+2029 written as its JSON escape.

    ``json.dumps(..., ensure_ascii=False)`` keeps them raw, which is valid JSON,
    but a reader that takes lines as ``str.splitlines`` does ends a line inside
    the string there. Escaped, a string stays on the one physical line it is
    written on and reads back as the same text. JSON allows them nowhere
    outside a string, so replacing them anywhere in JSON text changes strings
    only; every other character is written exactly as before.
    """
    for separator in LINE_SEPARATORS:
        json_text = json_text.replace(separator, "\\u%04x" % ord(separator))
    return json_text


# --------------------------------------------------------------------------- dump

def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise YamlishError("float scalars are not supported")
    if not isinstance(value, str):
        raise YamlishError(f"unsupported scalar type: {type(value).__name__}")
    if (
        value
        and _PLAIN_SAFE.match(value)
        and value not in _RESERVED
        and not _INT_RE.match(value)
        and value == value.strip()
        and ": " not in value
        and " #" not in value
        and not value.endswith(":")
    ):
        return value
    return escape_line_separators(json.dumps(value, ensure_ascii=False))


def _dump_lines(value: Any, depth: int, out: list[str]) -> None:
    pad = INDENT * depth
    if isinstance(value, dict):
        if not value:
            out.append(f"{pad}{{}}")
            return
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise YamlishError("mapping keys must be non-empty strings")
            key_text = _scalar(key)
            if isinstance(item, dict):
                if item:
                    out.append(f"{pad}{key_text}:")
                    _dump_lines(item, depth + 1, out)
                else:
                    out.append(f"{pad}{key_text}: {{}}")
            elif isinstance(item, list):
                if item:
                    out.append(f"{pad}{key_text}:")
                    _dump_lines(item, depth + 1, out)
                else:
                    out.append(f"{pad}{key_text}: []")
            else:
                out.append(f"{pad}{key_text}: {_scalar(item)}")
        return
    if isinstance(value, list):
        if not value:
            out.append(f"{pad}[]")
            return
        for item in value:
            if isinstance(item, dict):
                if not item:
                    out.append(f"{pad}- {{}}")
                    continue
                first = True
                for key, sub in item.items():
                    key_text = _scalar(key)
                    prefix = f"{pad}- " if first else f"{pad}  "
                    first = False
                    if isinstance(sub, (dict, list)) and sub:
                        out.append(f"{prefix}{key_text}:")
                        _dump_lines(sub, depth + 2, out)
                    elif isinstance(sub, dict):
                        out.append(f"{prefix}{key_text}: {{}}")
                    elif isinstance(sub, list):
                        out.append(f"{prefix}{key_text}: []")
                    else:
                        out.append(f"{prefix}{key_text}: {_scalar(sub)}")
            elif isinstance(item, list):
                raise YamlishError("nested sequences are not supported")
            else:
                out.append(f"{pad}- {_scalar(item)}")
        return
    out.append(f"{pad}{_scalar(value)}")


def dump(value: Any) -> str:
    """Serialize ``value`` (mapping / sequence / scalar) to YAML text."""
    lines: list[str] = []
    _dump_lines(value, 0, lines)
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- load

def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if text == "":
        return None
    if text[0] == '"':
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise YamlishError(f"bad double-quoted scalar: {text}") from exc
    if text[0] == "'":
        if not text.endswith("'") or len(text) < 2:
            raise YamlishError(f"bad single-quoted scalar: {text}")
        return text[1:-1].replace("''", "'")
    if text == "[]":
        return []
    if text == "{}":
        return {}
    if text in ("null", "~", "Null", "NULL"):
        return None
    if text in ("true", "True", "TRUE"):
        return True
    if text in ("false", "False", "FALSE"):
        return False
    if _INT_RE.match(text):
        return int(text)
    if text[0] in "[{&*!|>%@`":
        raise YamlishError(f"unsupported scalar syntax: {text}")
    return text


def _quoted_end(text: str) -> int | None:
    """Where the double-quoted string ``text`` starts with ends (just past its closing quote); None while open."""
    end = 1
    while end < len(text):
        if text[end] == "\\":
            end += 2
            continue
        if text[end] == '"':
            return end + 1
        end += 1
    return None


def _split_key(text: str) -> tuple[str, str] | None:
    """Split ``key: value`` / ``key:``; return None when not a mapping entry."""
    if text.startswith('"'):
        end = _quoted_end(text)
        if end is None:
            return None
        try:
            key = json.loads(text[:end])
        except json.JSONDecodeError:
            return None
        rest = text[end:]
        if rest == ":":
            return key, ""
        if rest.startswith(": "):
            return key, rest[2:]
        return None
    index = 0
    while True:
        index = text.find(":", index)
        if index < 0:
            return None
        if index == len(text) - 1:
            return text[:index], ""
        if text[index + 1] == " ":
            return text[:index], text[index + 2 :]
        index += 1


def _inside_quoted_scalar(line: str) -> bool:
    """Whether ``line`` ends inside a double-quoted scalar, in the form the writer puts one.

    That is a string opening a key or a sequence item right after the
    indentation or the ``- ``, or opening a value right after its key's ``: ``
    - where :func:`_prepare`, :func:`_split_key` and :func:`_parse_scalar`
    read a double-quoted scalar whatever follows it on the line. A comment, a
    plain scalar or key that merely holds a quote, a quote after a string has
    ended, and a quote only some other whitespace leads to are not one.
    """
    text = line.lstrip(" ")
    if text.lstrip().startswith("#"):
        return False
    if text.startswith("- "):
        text = text[2:]
    if text.startswith('"'):
        end = _quoted_end(text)
        if end is None:
            return True
        if not text[end:].startswith(": "):
            return False
        text = text[end + 2:]
    else:
        entry = _split_key(text)
        if entry is None:
            return False
        text = entry[1]
    return text.startswith('"') and _quoted_end(text) is None


def _lines(text: str) -> list[str]:
    """The physical lines of ``text``: ``str.splitlines``, except inside a double-quoted scalar.

    A U+0085 / U+2028 / U+2029 inside a string is text. The writer escapes it
    (:func:`escape_line_separators`); a file written before it did holds it
    raw, inside the double-quoted scalar it belongs to, and there it does not
    end the line. Every other line boundary, and one of these three anywhere
    else, ends the line exactly as ``str.splitlines`` ends it, so text that
    holds no such string is split as it always was.
    """
    if not any(separator in text for separator in LINE_SEPARATORS):
        return text.splitlines()
    lines: list[str] = []
    current = ""
    for piece in text.splitlines(keepends=True):
        content = piece.splitlines()[0]
        current += content
        ending = piece[len(content):]
        if ending in LINE_SEPARATORS and _inside_quoted_scalar(current):
            current += ending
            continue
        lines.append(current)
        current = ""
    if current:
        lines.append(current)
    return lines


class _Line:
    __slots__ = ("indent", "text", "number")

    def __init__(self, indent: int, text: str, number: int) -> None:
        self.indent = indent
        self.text = text
        self.number = number


def _prepare(text: str) -> list[_Line]:
    lines: list[_Line] = []
    for number, raw in enumerate(_lines(text), start=1):
        leading = raw[: len(raw) - len(raw.lstrip())]
        if "\t" in leading:
            raise YamlishError(f"line {number}: tabs are not allowed for indentation")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "---":
            raise YamlishError(f"line {number}: document markers are not supported inside a document")
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append(_Line(indent, raw[indent:].rstrip(), number))
    return lines


def _is_item(line: _Line) -> bool:
    return line.text.startswith("- ") or line.text == "-"


class _Parser:
    def __init__(self, lines: list[_Line]) -> None:
        self.lines = lines
        self.pos = 0

    def peek(self) -> _Line | None:
        return self.lines[self.pos] if self.pos < len(self.lines) else None

    def parse_block(self, indent: int) -> Any:
        line = self.peek()
        if line is None:
            return None
        if line.indent != indent:
            raise YamlishError(f"line {line.number}: unexpected indentation")
        if _is_item(line):
            return self.parse_sequence(indent)
        return self.parse_mapping(indent)

    def parse_mapping(self, indent: int) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while True:
            line = self.peek()
            if line is None or line.indent < indent:
                return result
            if line.indent > indent:
                raise YamlishError(f"line {line.number}: unexpected indentation")
            if _is_item(line):
                return result
            split = _split_key(line.text)
            if split is None:
                raise YamlishError(f"line {line.number}: expected 'key: value'")
            key, rest = split
            if key in result:
                raise YamlishError(f"line {line.number}: duplicate key {key!r}")
            self.pos += 1
            if rest.strip():
                result[key] = _parse_scalar(rest)
                continue
            nxt = self.peek()
            if nxt is None or nxt.indent < indent:
                result[key] = None
                continue
            if nxt.indent == indent:
                if _is_item(nxt):
                    result[key] = self.parse_sequence(indent)
                else:
                    result[key] = None
                continue
            result[key] = self.parse_block(nxt.indent)

    def parse_sequence(self, indent: int) -> list[Any]:
        result: list[Any] = []
        while True:
            line = self.peek()
            if line is None or line.indent < indent:
                return result
            if line.indent > indent:
                raise YamlishError(f"line {line.number}: unexpected indentation")
            if not _is_item(line):
                return result
            body = line.text[2:] if line.text != "-" else ""
            item_indent = indent + 2
            if not body.strip():
                self.pos += 1
                nxt = self.peek()
                if nxt is None or nxt.indent <= indent:
                    result.append(None)
                else:
                    result.append(self.parse_block(nxt.indent))
                continue
            if body.startswith("- "):
                raise YamlishError(f"line {line.number}: nested sequences are not supported")
            split = _split_key(body)
            if split is None:
                self.pos += 1
                result.append(_parse_scalar(body))
                continue
            # Mapping starting on the dash line: re-read the line as the first
            # entry of a mapping indented by two spaces.
            self.lines[self.pos] = _Line(item_indent, body, line.number)
            result.append(self.parse_mapping(item_indent))


def load(text: str) -> Any:
    """Parse YAML subset text. Empty / comment-only text yields ``None``."""
    lines = _prepare(text)
    if not lines:
        return None
    parser = _Parser(lines)
    value = parser.parse_block(lines[0].indent)
    rest = parser.peek()
    if rest is not None:
        raise YamlishError(f"line {rest.number}: trailing content")
    return value


# --------------------------------------------------------------------------- frontmatter

def dump_frontmatter(meta: dict[str, Any], body: str) -> str:
    """Render ``meta`` as a YAML frontmatter block followed by ``body``."""
    if not body.endswith("\n"):
        body += "\n"
    return "---\n" + dump(meta) + "---\n\n" + body


def load_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split ``text`` into (meta, body). Raises when the block is malformed."""
    if not text.startswith("---\n"):
        raise YamlishError("missing frontmatter start marker")
    end = text.find("\n---\n", 3)
    if end < 0:
        raise YamlishError("missing frontmatter end marker")
    meta = load(text[4 : end + 1])
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        raise YamlishError("frontmatter must be a mapping")
    body = text[end + 5 :]
    if body.startswith("\n"):
        body = body[1:]
    return meta, body
