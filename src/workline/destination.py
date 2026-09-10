"""Push destination identity (``rules/git``).

Workline guarantees **which repository** a Project pushes to, and nothing
about **who** authenticates. Two independent statements are compared:

* the Project's pin (``.workline/project.yaml`` ``git.push``) — committed, so
  it travels to every clone, appears in review diffs, and is changed only
  through the human-confirmed pin maintenance operation;
* what Git itself resolves as the active push destination right now
  (``git remote get-url --push --all``, which already applies ``pushurl`` and
  ``pushInsteadOf``).

Both sides are **exact locators**, compared as text. Workline never tidies a
locator into a canonical form and never decides that two spellings mean the
same repository: ``https://host/r`` and ``https://host/r.git`` can be two
different repositories, so treating them as one would defeat the check itself.
The approved locator is also the locator every command is given, so the
repository Workline inspects is always the repository it pushes to.

Every check here is a configuration read: no network is touched, so a
push-performing operation can STOP at its entry — before any domain write,
before any mutation intent exists and before anything reaches a remote.

What this module deliberately does not do: verify the account that will
authenticate. HTTPS credential helpers, SSH identities, credential managers
and provider CLIs each choose an account by their own rules, and none of them
report that choice in a provider-neutral way. A verified destination is never
reported as a verified account.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import gitcmd, pushurl
from .errors import ReconcileRequired, StopError
from .store import ProjectStore, PushPin

DEFAULT_REMOTE = "origin"


@dataclass(frozen=True)
class PushDestination:
    """The single active push destination an operation is authorized to use."""

    remote: str
    locator: str  # exactly what Git resolved, secret-free, never rewritten


def resolve_active_push_locator(repo: Path, remote: str) -> str:
    """The one locator ``git push <remote>`` writes to, exactly as Git gives it.

    v1 supports exactly one active push destination. Fan-out pushes (several
    configured push URLs) are refused rather than half-verified.
    """
    configured = gitcmd.push_locators(repo, remote)
    if not configured:
        raise StopError(
            f"remote {remote} resolves to no push locator", code="push_destination_unresolved"
        )
    if len(configured) > 1:
        shown = ", ".join(pushurl.redact(locator) for locator in configured)
        raise StopError(
            f"remote {remote} has {len(configured)} active push destinations ({shown}); "
            "Workline pushes to exactly one destination",
            code="push_destination_multiple",
        )
    locator = configured[0]
    pushurl.ensure_no_secret(locator, f"remote {remote}")
    return locator


def _check(pin: PushPin, repo: Path) -> PushDestination:
    if pin.remote not in gitcmd.remotes(repo):
        raise StopError(
            f"the Project pins pushes to remote {pin.remote}, which this repository does not have",
            code="push_destination_remote_missing",
        )
    locator = resolve_active_push_locator(repo, pin.remote)
    if locator not in pin.allowed_urls:
        raise StopError(
            f"remote {pin.remote} now pushes to {locator}, which is not an approved destination of "
            f"this Project ({', '.join(pin.allowed_urls)}); STOP. This is a Project-specific safety "
            "setting: change it through the pin maintenance operation, never automatically. Two "
            "spellings of a repository are never assumed to be the same repository",
            code="push_destination_mismatch",
        )
    return PushDestination(pin.remote, locator)


def ensure_push_destination(store: ProjectStore) -> PushDestination | None:
    """Entry check for any operation that may push. None means "no remote".

    Called before the operation opens its mutation, so a STOP here leaves no
    intent record, no domain write, no commit and no network contact.
    """
    repo = store.root
    pin = store.read_push_pin()
    if pin is None:
        remotes = gitcmd.remotes(repo)
        if remotes:
            raise StopError(
                f"this Project has remote(s) ({', '.join(remotes)}) but no approved push destination; "
                "pin the destination once (workline pin-push-destination) before pushing",
                code="push_destination_unpinned",
            )
        return None  # remote-less Project: local finalization is the whole contract
    return _check(pin, repo)


def verify_recorded_destination(store: ProjectStore, remote: str, locator: str) -> None:
    """Confirm a recorded ``git_push`` still targets what it was recorded for.

    Runs before any network access on every resume: a mutation never follows a
    remote name to wherever it happens to point now, and never accepts a
    differently spelled locator as "the same place".
    """
    pin = store.read_push_pin()
    if pin is None:
        raise ReconcileRequired(
            "the recorded push destination cannot be confirmed: this Project no longer pins one"
        )
    if remote != pin.remote:
        raise ReconcileRequired(
            f"recorded push remote {remote} is not the Project's pinned remote {pin.remote}: reconcile required"
        )
    if locator not in pin.allowed_urls:
        raise ReconcileRequired(
            f"recorded push destination {locator} is no longer an approved destination of this "
            "Project: reconcile required"
        )
    current = resolve_active_push_locator(store.root, pin.remote)
    if current != locator:
        raise ReconcileRequired(
            f"push destination changed since this mutation was recorded (recorded {locator}, remote "
            f"{pin.remote} now resolves to {current}): reconcile required, not pushing"
        )
