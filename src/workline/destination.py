"""Push destination identity (``rules/git``).

Workline guarantees **which repository** a Project pushes to, and nothing
about **who** authenticates. Two independent statements are compared:

* the Project's pin (``.workline/project.yaml`` ``git.push``) — committed, so
  it travels to every clone, appears in review diffs, and is changed only
  through the human-confirmed pin maintenance operation;
* what Git itself resolves as the active push destination right now
  (``git remote get-url --push --all``, which already applies ``pushurl`` and
  ``pushInsteadOf``).

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
    url: str  # normalized, secret-free, resolved from Git itself


def resolve_active_push_url(repo: Path, remote: str) -> str:
    """The one URL ``git push <remote>`` writes to, normalized.

    v1 supports exactly one active push destination. Fan-out pushes (several
    configured push URLs) are refused rather than half-verified.
    """
    configured = gitcmd.push_urls(repo, remote)
    if not configured:
        raise StopError(
            f"remote {remote} resolves to no push URL", code="push_destination_unresolved"
        )
    if len(configured) > 1:
        shown = ", ".join(pushurl.redact(url) for url in configured)
        raise StopError(
            f"remote {remote} has {len(configured)} active push destinations ({shown}); "
            "Workline pushes to exactly one destination",
            code="push_destination_multiple",
        )
    url = configured[0]
    pushurl.ensure_no_secret(url, f"remote {remote}")
    return pushurl.normalize(url)


def _check(pin: PushPin, repo: Path) -> PushDestination:
    if pin.remote not in gitcmd.remotes(repo):
        raise StopError(
            f"the Project pins pushes to remote {pin.remote}, which this repository does not have",
            code="push_destination_remote_missing",
        )
    url = resolve_active_push_url(repo, pin.remote)
    if url not in pin.allowed_urls:
        raise StopError(
            f"remote {pin.remote} now pushes to {url}, which is not an approved destination of this "
            f"Project ({', '.join(pin.allowed_urls)}); STOP. This is a Project-specific safety "
            "setting: change it through the pin maintenance operation, never automatically",
            code="push_destination_mismatch",
        )
    return PushDestination(pin.remote, url)


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


def verify_recorded_destination(store: ProjectStore, remote: str, url: str) -> None:
    """Confirm a recorded ``git_push`` still targets what it was recorded for.

    Runs before any network access on every resume: a mutation never follows
    a remote name to wherever it happens to point now.
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
    if url not in pin.allowed_urls:
        raise ReconcileRequired(
            f"recorded push destination {url} is no longer an approved destination of this Project: reconcile required"
        )
    current = resolve_active_push_url(store.root, pin.remote)
    if current != url:
        raise ReconcileRequired(
            f"push destination changed since this mutation was recorded (recorded {url}, remote "
            f"{pin.remote} now resolves to {current}): reconcile required, not pushing"
        )
