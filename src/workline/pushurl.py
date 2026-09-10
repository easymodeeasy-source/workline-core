"""Push destination URL normalization and secret detection.

Two Projects can only be compared destination-for-destination if both sides
are written in one canonical form, so every URL that reaches a pin, an effect
payload or a comparison passes through :func:`normalize` first.

Normalization is deliberately conservative and provider-neutral:

* scheme and host are case-folded, the default port for the scheme is dropped;
* one trailing ``/`` and one trailing ``.git`` are removed;
* scp syntax (``user@host:path``) becomes its canonical ``ssh://`` form;
* the path case is **never** folded — providers differ on it;
* an ``https`` URL and an ``ssh`` URL are never inferred to be the same
  repository. A Project that legitimately uses both pins both.

Secret detection is fail-closed: a URL that carries credentials is never
stored, never compared and never printed back — callers STOP and the message
carries the redacted form only.
"""

from __future__ import annotations

from .errors import StopError, ValidationError

DEFAULT_PORTS = {"ssh": "22", "http": "80", "https": "443", "git": "9418"}
SECRET_CODE = "push_destination_secret"


def _split_authority(authority: str) -> tuple[str, str]:
    """``[userinfo@]host[:port]`` → (userinfo, hostport)."""
    if "@" in authority:
        userinfo, _, hostport = authority.rpartition("@")
        return userinfo, hostport
    return "", authority


def _is_scp_syntax(text: str) -> bool:
    """``user@host:path`` (never ``C:/...``, never a URL with a scheme)."""
    if "://" in text:
        return False
    head, separator, _ = text.partition(":")
    if not separator or "/" in head:
        return False
    return len(head) > 1 or "@" in head


def _parts(url: str) -> tuple[str, str, str] | None:
    """(scheme, authority, path) for a URL / scp form; None for a local path."""
    text = url.replace("\\", "/")
    if "://" in text:
        scheme, _, rest = text.partition("://")
        authority, separator, path = rest.partition("/")
        return scheme, authority, (separator + path if separator else "")
    if _is_scp_syntax(text):
        authority, _, path = text.partition(":")
        return "ssh", authority, "/" + path.lstrip("/")
    return None


def _strip_path(path: str) -> str:
    trimmed = path.rstrip("/")
    if trimmed.endswith(".git"):
        trimmed = trimmed[: -len(".git")]
    return trimmed


def normalize(url: str) -> str:
    """Canonical comparison form of ``url``; STOP when it is not usable."""
    if not isinstance(url, str) or not url.strip():
        raise ValidationError("push destination URL is empty", code="push_destination_invalid")
    text = url.strip()
    parts = _parts(text)
    if parts is None:  # local path / filesystem remote
        return _strip_path(text.replace("\\", "/"))
    scheme, authority, path = parts
    scheme = scheme.lower()
    userinfo, hostport = _split_authority(authority)
    if not hostport:
        raise ValidationError(f"push destination URL has no host: {redact(text)}", code="push_destination_invalid")
    host, separator, port = hostport.partition(":")
    host = host.lower()
    if separator and port == DEFAULT_PORTS.get(scheme):
        separator, port = "", ""
    authority = f"{userinfo}@{host}" if userinfo else host
    return f"{scheme}://{authority}{separator}{port}{_strip_path(path)}"


def userinfo_of(url: str) -> str:
    parts = _parts(url.strip())
    if parts is None:
        return ""
    return _split_authority(parts[1])[0]


def scheme_of(url: str) -> str:
    parts = _parts(url.strip())
    return parts[0].lower() if parts else ""


def is_secret_bearing(url: str) -> bool:
    """Whether ``url`` carries credentials.

    A password component is a secret under any scheme. Over http(s) even a
    bare username is refused: that is where tokens are carried, and account
    identity does not belong in a file that travels to every clone. An ssh
    user name (``git@host``) is a transport detail, not a credential.
    """
    userinfo = userinfo_of(url)
    if not userinfo:
        return False
    if ":" in userinfo:
        return True
    return scheme_of(url) in ("http", "https")


def redact(url: str) -> str:
    """``url`` with credential userinfo replaced — safe for messages and logs.

    An ssh user name is a transport detail and stays readable; anything this
    module counts as a secret is masked.
    """
    text = str(url).strip()
    if not is_secret_bearing(text):
        return text
    scheme, authority, path = _parts(text)  # secret-bearing implies a parsable URL
    hostport = _split_authority(authority)[1]
    return f"{scheme}://***@{hostport}{path}"


def ensure_no_secret(url: str, context: str) -> None:
    """STOP (fail-closed) when ``url`` carries credentials. Never echo it raw."""
    if is_secret_bearing(url):
        raise StopError(
            f"{context}: the URL carries credentials ({redact(url)}); "
            "use a credential-free URL and let a credential helper supply the account",
            code=SECRET_CODE,
        )


def accept(url: str, context: str) -> str:
    """Secret check first, then normalize: the only way a URL enters Workline."""
    ensure_no_secret(url, context)
    return normalize(url)
