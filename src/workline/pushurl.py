"""Inspection of push locators — secrets only, never identity.

A push destination is identified by the **exact locator Git itself resolves**
(``git remote get-url --push --all``). This module never rewrites one:

* ``https://host/repo`` and ``https://host/repo.git`` may be different
  repositories on some servers, so nothing here strips ``.git``;
* the same goes for a trailing ``/``, path case, and every other
  provider-dependent way of spelling a repository path;
* an ``https`` locator and an ``ssh`` locator are never inferred to point at
  the same repository.

Approving both spellings is a human decision recorded in the pin, not an
inference Workline makes. A false negative (one repository refused because it
is spelled differently) is the accepted price; a false positive (two
repositories treated as one) is not.

What is left here is parsing for one purpose: detecting and masking
credentials. A locator that carries them is refused before it is stored,
compared or printed.
"""

from __future__ import annotations

from .errors import StopError

SECRET_CODE = "push_destination_secret"


def _split_authority(authority: str) -> tuple[str, str]:
    """``[userinfo@]host[:port]`` → (userinfo, hostport)."""
    if "@" in authority:
        userinfo, _, hostport = authority.rpartition("@")
        return userinfo, hostport
    return "", authority


def _is_scp_syntax(text: str) -> bool:
    """``user@host:path`` (never ``C:/...``, never a locator with a scheme)."""
    if "://" in text:
        return False
    head, separator, _ = text.partition(":")
    if not separator or "/" in head or "\\" in head:
        return False
    return len(head) > 1 or "@" in head


def _authority_of(locator: str) -> str | None:
    """The authority part of ``locator``; None for a local filesystem path."""
    text = locator.strip()
    if "://" in text:
        return text.partition("://")[2].partition("/")[0]
    if _is_scp_syntax(text):
        return text.partition(":")[0]
    return None


def userinfo_of(locator: str) -> str:
    authority = _authority_of(locator)
    return _split_authority(authority)[0] if authority else ""


def scheme_of(locator: str) -> str:
    text = locator.strip()
    return text.partition("://")[0].lower() if "://" in text else ""


def is_secret_bearing(locator: str) -> bool:
    """Whether ``locator`` carries credentials.

    A password component is a secret under any scheme. Over http(s) even a
    bare user name is refused: that is where tokens are carried, and account
    identity does not belong in a file that travels to every clone. An ssh
    user name (``git@host``) is a transport detail, not a credential.
    """
    userinfo = userinfo_of(locator)
    if not userinfo:
        return False
    if ":" in userinfo:
        return True
    return scheme_of(locator) in ("http", "https")


def redact(locator: str) -> str:
    """``locator`` with credential userinfo masked — safe for messages and logs.

    The rest of the text is left exactly as it was: a redacted locator is for
    reading, never for storing or comparing.
    """
    text = str(locator).strip()
    if not is_secret_bearing(text):
        return text
    return text.replace(f"{userinfo_of(text)}@", "***@", 1)


def ensure_no_secret(locator: str, context: str) -> None:
    """STOP (fail-closed) when ``locator`` carries credentials. Never echo it raw."""
    if is_secret_bearing(locator):
        raise StopError(
            f"{context}: the locator carries credentials ({redact(locator)}); "
            "use a credential-free locator and let a credential helper supply the account",
            code=SECRET_CODE,
        )
