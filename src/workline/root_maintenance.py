"""Workline-root policy maintenance runtime (P7, ``WORKLINE_COMPLETION_SPRINT`` §31.8-§31.13, §31.30, §31.46).

The Workline root is never a Workline Project. Its Global policy is maintained
by two dedicated root operations - ``global-policy-change`` and its evaluation
sub-operation ``global-policy-evaluation`` - and by the local publication
authorization they need when the root has a remote. This module is the one
single-purpose runtime those operations run on. It owns:

* **the root runtime area** ``.workline-root-runtime/`` (§31.8), ignored by the
  root's own rules, holding the lock, the diagnostic holder description, the
  root mutation records, the publication authorization, the temporary area and
  the class B Git scratch. Nothing there is policy authority, Review authority
  or evidence, and it may disappear: losing it never authorizes adoption by
  guess. Every write there is noncanonical, durable, and refuses indirection;
* **the root entry checks** (RB7C-6): the target is the running
  implementation's own root, holds no ``.workline`` entry at all, and is its
  own Git top level; a mutation-capable root entry invoked from inside a
  Workline Project is refused before the lock;
* **the root maintenance lock** (§31.9) on ``global-policy.lock``, through the
  same OS primitive the Project execution lock uses and nothing else of it: no
  Project context, no ``ProjectStore``, no Project lock, no forced unlock, no
  stale-lock cleanup;
* **the class B root Git entry** (RB7C-5, N-3): every root commit is class B,
  entered with the root-runtime scratch, and a root whose identity is not
  configured STOPs ``review_identity_unavailable`` there, before any effect;
* **the single-purpose root mutation** (§31.10, §31.11): one schema, a closed
  set of canonical effects inside the root policy layout, replay-stable
  reservations, durable intent before every effect;
* **the publication authorization** (§31.12, §31.13), bound to an opaque local
  repository identity so a copy in another clone or worktree authorizes
  nothing, and never inferred from ``origin``;
* **the committability preflight** (RB7C-9) over the whole closed effect set;
* **the read-only status report** (§31.46, RB7C-4).

What it never does: create ``<workline-root>/.workline/`` (no code path here
names it except to refuse it), construct a ``ProjectStore`` for the root, take
or touch a Project lock, write a path outside the root policy layout through
the mutation, or decide Review semantics.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import threading
from types import MappingProxyType
from typing import Any, Iterator, Mapping, Sequence

from . import context, destination, gitcmd, ids, implementation, oplock, pushurl
from .durable import durable_write_text
from .errors import GitError, ReconcileRequired, StopError, ValidationError
from .review import fsafe, hermetic, serialize
from .review import policy as review_policy
from .review.namespace import ROOT_POLICY_LAYOUT, ROOT_POLICY_REVIEW_NAMESPACE

# --------------------------------------------------------------------------- layout and identities (§31.8)

RUNTIME_DIR = ".workline-root-runtime"
LOCK_REL = ".workline-root-runtime/global-policy.lock"
HOLDER_REL = ".workline-root-runtime/holder.json"  # diagnostic only; never read to decide
MUTATIONS_DIR = ".workline-root-runtime/mutations"  # <rpm_...>.yaml
AUTHORIZATION_REL = ".workline-root-runtime/maintenance-authorization.yaml"
TMP_DIR = ".workline-root-runtime/tmp"
TMP_PARTS = (".workline-root-runtime", "tmp")  # fsafe tmp_parts (same volume)
ROOT_GIT_SCRATCH = hermetic.ScratchPaths(".workline-root-runtime/no-hooks", ".workline-root-runtime/no-config")

OPERATION_CHANGE = "global-policy-change"
OPERATION_EVALUATION = "global-policy-evaluation"
OPERATIONS = (OPERATION_CHANGE, OPERATION_EVALUATION)
#: The lock operation of :func:`authorize`; it opens no root mutation.
OPERATION_AUTHORIZE = "root-policy-maintenance-authorize"
LOCK_OPERATIONS = (*OPERATIONS, OPERATION_AUTHORIZE)

MUTATION_SCHEMA = "workline-root-policy-mutation"
MUTATION_VERSION = 1
AUTHORIZATION_SCHEMA = "workline-root-maintenance-authorization"
AUTHORIZATION_CONTRACT = "workline-root-maintenance-authorization-v1"
AUTHORIZATION_VERSION = 1
STATUS_PENDING = "pending"
STATUS_COMPLETED = "completed"
STATUS_ABANDONED = "abandoned"
MUTATION_STATUSES = (STATUS_PENDING, STATUS_COMPLETED, STATUS_ABANDONED)
STATUS_KEY = "root_maintenance"

HOLDER_MARKER = "workline-root-maintenance-holder"
HOLDER_VERSION = 1
#: The domain tag of the opaque local repository identity (§31.13).
REPOSITORY_IDENTITY_SCHEMA = "workline-root-repository-identity"

MUTATION_FIELDS = (
    "schema", "version", "mutation_id", "operation", "status", "invocation", "branch", "base", "global_policy",
    "reserved_ids", "write_scope", "effects", "notes", "publication",
)
AUTHORIZATION_FIELDS = ("schema", "version", "contract", "repository_identity", "remote", "branch", "locator")

# --------------------------------------------------------------------------- the B catalogue (frozen + B's own)

CODE_ROOT_BINDING_MISMATCH = "review_p7_root_binding_mismatch"
CODE_ROOT_IS_PROJECT = "review_p7_root_is_project"
CODE_ROOT_PROJECT_CONTEXT = "review_p7_root_project_context"
CODE_ROOT_NOT_REPOSITORY = "review_p7_root_not_repository"
CODE_ROOT_RUNTIME_INVALID = "review_p7_root_runtime_invalid"
CODE_ROOT_RUNTIME_UNIGNORED = "review_p7_root_runtime_unignored"
CODE_ROOT_BUSY = "review_p7_root_busy"
CODE_ROOT_NESTED = "review_p7_root_nested"
CODE_ROOT_LOCK_UNAVAILABLE = "review_p7_root_lock_unavailable"
CODE_AUTHORIZATION_REQUIRED = "review_p7_authorization_required"
CODE_AUTHORIZATION_MISMATCH = "review_p7_authorization_mismatch"
CODE_AUTHORIZATION_INVALID = "review_p7_authorization_invalid"
CODE_REPOSITORY_IDENTITY_UNAVAILABLE = "review_p7_repository_identity_unavailable"
CODE_ROOT_EFFECT_REFUSED = "review_p7_root_effect_refused"
#: B's own (LEAF-READY): a root mutation or Git entry used without the root lock this process holds.
CODE_ROOT_LOCK_NOT_HELD = "review_p7_root_lock_not_held"
STOP_CODES = (
    CODE_ROOT_BINDING_MISMATCH,
    CODE_ROOT_IS_PROJECT,
    CODE_ROOT_PROJECT_CONTEXT,
    CODE_ROOT_NOT_REPOSITORY,
    CODE_ROOT_RUNTIME_INVALID,
    CODE_ROOT_RUNTIME_UNIGNORED,
    CODE_ROOT_BUSY,
    CODE_ROOT_NESTED,
    CODE_ROOT_LOCK_UNAVAILABLE,
    CODE_AUTHORIZATION_REQUIRED,
    CODE_AUTHORIZATION_MISMATCH,
    CODE_AUTHORIZATION_INVALID,
    CODE_REPOSITORY_IDENTITY_UNAVAILABLE,
    CODE_ROOT_EFFECT_REFUSED,
    CODE_ROOT_LOCK_NOT_HELD,
)

REASON_MUTATION_CONFLICT = "review_p7_root_mutation_conflict"
REASON_MUTATION_UNREADABLE = "review_p7_root_mutation_unreadable"
REASON_EFFECT_CONFLICT = "review_p7_root_effect_conflict"
#: B's own (LEAF-READY): a root mutation whose canonical effect may already be applied is never abandoned.
REASON_ABANDON_REFUSED = "review_p7_root_abandon_refused"
RECONCILE_REASONS = (
    REASON_MUTATION_CONFLICT,
    REASON_MUTATION_UNREADABLE,
    REASON_EFFECT_CONFLICT,
    REASON_ABANDON_REFUSED,
)

# Reused unchanged (never redefined here): review_path_ignored, review_committability_unknown (this module, the
# preflight and the runtime ignore check); review_identity_unavailable, review_hooks_path_invalid,
# review_no_config_file_invalid (review.hermetic through enter_git); push_destination_unresolved /
# push_destination_multiple / push_destination_secret (destination / pushurl).
CODE_PATH_IGNORED = "review_path_ignored"
CODE_COMMITTABILITY_UNKNOWN = "review_committability_unknown"
CODE_PUSH_DESTINATION_UNRESOLVED = "push_destination_unresolved"


def stop(code: str, message: str) -> StopError:
    """A root maintenance STOP (built here so every caller raises a code of this catalogue)."""
    if code not in STOP_CODES:
        raise ValueError(f"not a root maintenance STOP code: {code!r}")
    return StopError(message, code=code)


def reconcile(message: str, reason: str) -> ReconcileRequired:
    """A root maintenance reconcile (built here so every caller names a reason of this catalogue)."""
    if reason not in RECONCILE_REASONS:
        raise ValueError(f"not a root maintenance reconcile reason: {reason!r}")
    return ReconcileRequired(f"{message}: reconcile required", reason=reason)


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_FULL_REF = re.compile(r"refs/heads/\S+\Z")
_DATE = re.compile(r"[0-9]{1,15} [+-][0-9]{4}\Z")


def _full_ref(value: object) -> bool:
    return isinstance(value, str) and _FULL_REF.fullmatch(value) is not None and ".." not in value


def _reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


# --------------------------------------------------------------------------- entry checks (RB7C-6; before the lock)


def require_root_target(workline_root: Path) -> Path:
    """The resolved Workline root this process may maintain, or STOP before anything is read or written.

    (a) It is the root whose implementation this process runs
    (``implementation.running_workline_root``, compared by file identity), so
    only the root's own implementation maintains it; no proven running root or
    another one is ``review_p7_root_binding_mismatch``. (b) It holds no
    ``.workline`` entry at all - file, directory or link: the root is never a
    Workline Project, and a root carrying the Project namespace is the
    unsupported self-hosting layout (``review_p7_root_is_project``). (c) It is
    its own Git top level (``review_p7_root_not_repository``).
    """
    try:
        root = Path(workline_root).resolve()
    except OSError as exc:
        raise stop(CODE_ROOT_BINDING_MISMATCH, f"the Workline root {workline_root} cannot be resolved ({exc}); "
                   "nothing was written") from exc
    running = implementation.running_workline_root()
    if running is None or not _same_directory(root, running):
        raise stop(
            CODE_ROOT_BINDING_MISMATCH,
            f"the Workline root {root} is not the root whose implementation this process runs "
            f"({running if running is not None else 'none can be proven'}); a Workline root is maintained only by "
            "its own implementation. Nothing was written",
        )
    if os.path.lexists(root / ".workline"):
        raise stop(
            CODE_ROOT_IS_PROJECT,
            f"the Workline root {root} holds a .workline entry; the Workline root is never a Workline Project and "
            "root policy maintenance does not run on one. Nothing was written",
        )
    top = gitcmd.toplevel(root)
    if top is None or not _same_directory(top, root):
        raise stop(
            CODE_ROOT_NOT_REPOSITORY,
            f"the Workline root {root} is not the top level of its own Git repository; root policy maintenance "
            "commits in the root repository only. Nothing was written",
        )
    return root


def require_root_invocation() -> None:
    """STOP when this mutation-capable root entry was invoked from inside a Workline Project (RB7C-6 (c)).

    The invocation context is the working directory's (``context``), resolved
    once here. A caller inside a Project never has its configured Workline root
    silently become the target of a root mutation; outside a Project the
    binding is the launcher's own root.
    """
    found = context.resolve_invocation_context()
    if found.kind == context.PROJECT:
        raise stop(
            CODE_ROOT_PROJECT_CONTEXT,
            f"Workline-root policy maintenance was invoked {found.describe()}; it changes the Workline root and is "
            "run from the Workline root itself (or any directory that is not a Workline Project), never from "
            "inside a Project. Nothing was written",
        )


def _same_directory(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


# --------------------------------------------------------------------------- the runtime area (§31.8)


def _require_runtime_ignored(root: Path) -> None:
    """``.workline-root-runtime/`` is excluded by the root's own ignore rules - asked before anything is created."""
    ignored = gitcmd.is_ignored(root, RUNTIME_DIR + "/")
    if ignored is None:
        raise StopError(
            f"git cannot say whether {RUNTIME_DIR}/ is ignored in the Workline root, so its noncanonical runtime "
            "could reach a commit: STOP",
            code=CODE_COMMITTABILITY_UNKNOWN,
        )
    if not ignored:
        raise stop(
            CODE_ROOT_RUNTIME_UNIGNORED,
            f"{RUNTIME_DIR}/ is not ignored by the Workline root's own rules (its .gitignore carries it); the root "
            "maintenance runtime is never committable, and Workline does not edit ignore configuration. Nothing was "
            "written",
        )


def _runtime_directory(root: Path, parts: Sequence[str], *, create: bool) -> Path | None:
    """``root`` / ``parts`` as plain directories under the runtime area, walked without following anything.

    Each component is examined with ``lstat`` and must be a plain directory -
    never a link, a junction or any reparse point - else
    ``review_p7_root_runtime_invalid``. A missing one is created when
    ``create`` (``mkdir`` never follows the name it creates), otherwise
    ``None`` is the answer.
    """
    if not parts or parts[0] != RUNTIME_DIR:
        raise ValueError(f"not a root runtime directory: {'/'.join(parts)!r}")
    path = Path(root)
    for part in parts:
        path = path / part
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            if not create:
                return None
            try:
                os.mkdir(path)
            except FileExistsError:
                pass
            except OSError as exc:
                raise stop(CODE_ROOT_RUNTIME_INVALID, f"{path} cannot be created as a root runtime directory "
                           f"({exc}); STOP") from exc
            try:
                info = os.lstat(path)
            except OSError as exc:
                raise stop(CODE_ROOT_RUNTIME_INVALID, f"{path} cannot be examined ({exc}); STOP") from exc
        except OSError as exc:
            raise stop(CODE_ROOT_RUNTIME_INVALID, f"{path} cannot be examined ({exc}); STOP") from exc
        if not stat.S_ISDIR(info.st_mode) or _reparse(info):
            raise stop(
                CODE_ROOT_RUNTIME_INVALID,
                f"{path} is not a plain directory (a file, a link or a reparse point is never followed); the root "
                "maintenance runtime is refused: STOP",
            )
    return path


def _require_plain_or_absent(path: Path) -> None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise stop(CODE_ROOT_RUNTIME_INVALID, f"{path} cannot be examined ({exc}); STOP") from exc
    if not stat.S_ISREG(info.st_mode) or _reparse(info):
        raise stop(CODE_ROOT_RUNTIME_INVALID, f"{path} is not a plain file (a link or a reparse point is never "
                   "followed or replaced); STOP")


def _write_runtime(root: Path, relative: str, text: str) -> None:
    """Write one noncanonical runtime file durably: plain parents, no indirection, temporary file in ``tmp/``."""
    parts = relative.split("/")
    directory = _runtime_directory(root, parts[:-1], create=True)
    tmp = _runtime_directory(root, TMP_PARTS, create=True)
    target = directory / parts[-1]
    _require_plain_or_absent(target)
    try:
        durable_write_text(target, text, tmp_dir=tmp)
    except (OSError, UnicodeError) as exc:
        raise stop(CODE_ROOT_RUNTIME_INVALID, f"{relative} cannot be written durably ({exc}); STOP") from exc


def _read_runtime(root: Path, relative: str) -> bytes | None:
    """The bytes of one runtime file, read relative to held directories without following anything; None if absent.

    Raises the fsafe containment refusal for an indirection anywhere on the way.
    """
    parts = relative.split("/")
    chain = fsafe.walk(Path(root), parts[:-1])
    if chain is None:
        return None
    with chain:
        return chain.last.read_file(parts[-1])


def tmp_directory(lock: "RootLock") -> Path:
    """The proven root runtime temporary directory (``.workline-root-runtime/tmp``) - for an isolated index, say.

    Only under the held root lock; created as a plain directory when absent.
    """
    _require_held(lock)
    found = _runtime_directory(lock.root, TMP_PARTS, create=True)
    assert found is not None
    return found


# --------------------------------------------------------------------------- the root lock (§31.9)


@dataclass
class RootLock:
    """The Workline-root policy maintenance lock this process holds."""

    root: Path
    operation: str
    details: dict[str, Any]


_held: RootLock | None = None
_held_guard = threading.Lock()


def _require_held(lock: RootLock) -> None:
    with _held_guard:
        held = _held
    if held is None or held is not lock:
        raise stop(
            CODE_ROOT_LOCK_NOT_HELD,
            "this root maintenance step runs only under the Workline-root policy maintenance lock this process "
            "holds; nothing was written",
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_holder(lock: RootLock) -> None:
    """The diagnostic holder description; it never fails the operation and nothing reads it to decide."""
    record = {
        "workline": HOLDER_MARKER,
        "version": HOLDER_VERSION,
        "operation": lock.operation,
        "details": lock.details,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "acquired_at": _utc_now(),
    }
    try:
        _write_runtime(lock.root, HOLDER_REL, json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    except (StopError, OSError, ValueError, TypeError):
        pass


def _clear_holder(root: Path) -> None:
    path = Path(root) / HOLDER_REL
    try:
        info = os.lstat(path)
        if stat.S_ISREG(info.st_mode) and not _reparse(info):
            path.unlink()
    except OSError:
        pass


def _busy_operation(root: Path) -> str | None:
    """The operation the recorded holder names, for the busy report only."""
    try:
        raw = _read_runtime(root, HOLDER_REL)
        data = json.loads(raw.decode("utf-8")) if raw is not None else None
    except (StopError, OSError, UnicodeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("workline") != HOLDER_MARKER:
        return None
    operation = data.get("operation")
    return operation if operation in LOCK_OPERATIONS else None


@contextmanager
def root_operation(workline_root: Path, operation: str, details: Mapping[str, Any] | None = None
                   ) -> Iterator[RootLock]:
    """Hold the Workline-root policy maintenance lock for one root operation, or STOP.

    Order: :func:`require_root_target`, :func:`require_root_invocation`, no
    root operation already running in this process (``review_p7_root_nested``),
    the runtime area ignored by the root's own rules - asked of the name before
    anything is created, so an unignored root gets nothing - and then the
    runtime directory proven plain (created when absent), the lock file opened
    and locked without waiting through the ``oplock`` primitive
    (``review_p7_root_busy`` when another process holds it, having written
    nothing; ``review_p7_root_lock_unavailable`` when it cannot be opened,
    locked or proven to be the file it names), the holder description written,
    the block run, and the lock released however the block exits.

    It takes no Project lock and builds no ``ProjectStore``; it never forces or
    cleans up a lock, and the holder description is never read to decide.
    """
    global _held
    if operation not in LOCK_OPERATIONS:
        raise ValueError(f"not a root maintenance operation: {operation!r}")
    root = require_root_target(workline_root)
    require_root_invocation()
    with _held_guard:
        running = _held
    if running is not None:
        raise stop(
            CODE_ROOT_NESTED,
            f"this process is already running {running.operation} on the Workline root; a root maintenance "
            "operation cannot start inside another one. Nothing was written",
        )
    _require_runtime_ignored(root)
    _runtime_directory(root, (RUNTIME_DIR,), create=True)
    lock_path = root / LOCK_REL
    _require_plain_or_absent(lock_path)
    try:
        fd = oplock.open_lock_file(lock_path)
    except OSError as exc:
        raise stop(CODE_ROOT_LOCK_UNAVAILABLE, f"cannot open the root maintenance lock {LOCK_REL}: {exc}") from exc
    try:
        locked = oplock.try_exclusive_lock(fd)
    except OSError as exc:
        os.close(fd)
        raise stop(CODE_ROOT_LOCK_UNAVAILABLE, f"cannot take the root maintenance lock {LOCK_REL}: {exc}") from exc
    if not locked:
        os.close(fd)
        holder = _busy_operation(root)
        raise stop(
            CODE_ROOT_BUSY,
            "another process holds the Workline-root policy maintenance lock"
            + (f" (recorded holder: {holder})" if holder else "")
            + "; nothing was written, run the operation again once it has finished",
        )
    try:
        proven = oplock.names_locked_file(fd, lock_path)
        _require_plain_or_absent(lock_path)
    except StopError:
        proven = False
    if not proven:
        _release(fd)
        raise stop(CODE_ROOT_LOCK_UNAVAILABLE,
                   f"the root maintenance lock {LOCK_REL} was replaced while it was being taken; STOP")
    lock = RootLock(root, operation, dict(details or {}))
    with _held_guard:
        raced = _held
        if raced is None:
            _held = lock
    if raced is not None:
        _release(fd)
        raise stop(CODE_ROOT_NESTED, f"this process is already running {raced.operation} on the Workline root; "
                   "nothing was written")
    try:
        _runtime_directory(root, TMP_PARTS, create=True)
        _write_holder(lock)
        yield lock
    finally:
        with _held_guard:
            _held = None
        # The description goes first, while the lock is still held, so it can never erase the next holder's.
        _clear_holder(root)
        _release(fd)


def _release(fd: int) -> None:
    try:
        oplock.release_exclusive_lock(fd)
    except OSError:
        pass
    os.close(fd)


def enter_git(lock: RootLock) -> hermetic.HermeticGit:
    """The class B Git of the root (RB7C-5): ``hermetic.enter_root(lock.root, ROOT_GIT_SCRATCH)``, under the lock.

    The class-B frozen order: the class A identity capture first - a root with
    no configured ``user.name`` / ``user.email`` STOPs
    ``review_identity_unavailable`` here, before the scratch exists and before
    any effect - then the grafts / shallow / promisor entry reads, then the two
    empty scratch objects under ``.workline-root-runtime/`` (a non-empty one is
    ``review_no_config_file_invalid`` / ``review_hooks_path_invalid``).
    """
    _require_held(lock)
    _runtime_directory(lock.root, (RUNTIME_DIR,), create=True)  # proven plain again before the scratch lives in it
    return hermetic.enter_root(lock.root, ROOT_GIT_SCRATCH)


# --------------------------------------------------------------------------- the single-purpose root mutation (§31.10, §31.11)

EFFECT_REVIEW_CREATE = "root-review-create"  # immutable create under review-policy/review (not consumptions/)
EFFECT_PACKET_CREATE = "promotion-packet-create"
EFFECT_CHANGE_CREATE = "global-change-create"
EFFECT_PATCH_NOTE_CREATE = "patch-note-create"
EFFECT_GLOBAL_POLICY_REPLACE = "global-policy-replace"  # exact CAS of review-policy/global-policy.yaml
EFFECT_CONSUMPTION_CREATE = "global-consumption-create"  # immutable create under review-policy/review/consumptions/
EFFECT_EVALUATION_CREATE = "global-evaluation-create"  # §31.42 evaluation sub-operation only
EFFECT_COMMIT = "root-commit"
EFFECT_PUSH = "root-push"
ROOT_EFFECT_KINDS = (
    EFFECT_REVIEW_CREATE, EFFECT_PACKET_CREATE, EFFECT_CHANGE_CREATE, EFFECT_PATCH_NOTE_CREATE,
    EFFECT_GLOBAL_POLICY_REPLACE, EFFECT_CONSUMPTION_CREATE, EFFECT_EVALUATION_CREATE, EFFECT_COMMIT, EFFECT_PUSH,
)
OPERATION_EFFECTS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    OPERATION_CHANGE: tuple(kind for kind in ROOT_EFFECT_KINDS if kind != EFFECT_EVALUATION_CREATE),
    OPERATION_EVALUATION: (EFFECT_EVALUATION_CREATE, EFFECT_COMMIT, EFFECT_PUSH),
})
RESERVATION_KINDS = (
    "review_run", "review_task", "review_receipt", "review_consumption",
    "review_promotion_packet", "review_global_policy_change", "review_global_policy_evaluation",
)
STAGES = ("kg1", "kg2", "kg3", "kg4", "kg5", "kp", "km", "evaluation")
#: Which stages each operation commits in, and which of them may ever be published: a Review generation commit
#: publishes nothing by itself (§16.14, §31.27); only Kp / Km and the evaluation commit reach the remote.
OPERATION_STAGES: Mapping[str, tuple[str, ...]] = MappingProxyType({
    OPERATION_CHANGE: ("kg1", "kg2", "kg3", "kg4", "kg5", "kp", "km"),
    OPERATION_EVALUATION: ("evaluation",),
})
PUSH_STAGES: Mapping[str, tuple[str, ...]] = MappingProxyType({
    OPERATION_CHANGE: ("kp", "km"),
    OPERATION_EVALUATION: ("evaluation",),
})

#: The root policy layout family each file effect kind writes (``ROOT_POLICY_LAYOUT.family_of``).
_KIND_FAMILY = {
    EFFECT_REVIEW_CREATE: "review",
    EFFECT_PACKET_CREATE: "promotion-packet",
    EFFECT_CHANGE_CREATE: "change",
    EFFECT_PATCH_NOTE_CREATE: "patch-note",
    EFFECT_GLOBAL_POLICY_REPLACE: "global-policy",
    EFFECT_CONSUMPTION_CREATE: "review",
    EFFECT_EVALUATION_CREATE: "evaluation",
}
FILE_EFFECT_KINDS = tuple(_KIND_FAMILY)
_CREATE_KINDS = tuple(kind for kind in FILE_EFFECT_KINDS if kind != EFFECT_GLOBAL_POLICY_REPLACE)
#: The families an operation's exact write scope may name.
_OPERATION_FAMILIES = {
    OPERATION_CHANGE: ("review", "promotion-packet", "change", "patch-note", "global-policy"),
    OPERATION_EVALUATION: ("evaluation",),
}
CREATE_PAYLOAD_FIELDS = ("path", "content", "sha256")
REPLACE_PAYLOAD_FIELDS = ("path", "content", "sha256", "expected_sha256", "expected_content")
COMMIT_PAYLOAD_FIELDS = ("stage", "parent", "ref", "message", "paths", "date")
PUSH_PAYLOAD_FIELDS = ("stage", "remote", "ref", "commit")
COMMIT_FACT_FIELDS = ("prepared_commit", "prepared_tree", "ref_moved")
PUSH_FACT_FIELDS = ("pushed",)
EFFECT_FIELDS = ("kind", "payload", "state", "facts")
STATE_INTENDED = "intended"
STATE_APPLIED = "applied"  # a file effect: its exact bytes are in place
STATE_MARKED = "marked"  # a commit / push effect: its facts are recorded
EFFECT_STATES = (STATE_INTENDED, STATE_APPLIED, STATE_MARKED)
APPLIED = "applied"
MATCHED = "matched"


def _refused(message: str) -> StopError:
    return stop(CODE_ROOT_EFFECT_REFUSED, f"{message}; the single-purpose root mutation writes nothing outside its "
                "closed effect set")


def _review_prefix() -> str:
    return ROOT_POLICY_LAYOUT.review_dir + "/"


def _consumption_prefix() -> str:
    return ROOT_POLICY_REVIEW_NAMESPACE.consumptions_dir + "/"


def _relative_shape(value: object) -> bool:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value or ":" in value \
            or "\0" in value:
        return False
    parts = value[:-1].split("/") if value.endswith("/") else value.split("/")
    return all(part not in ("", ".", "..") for part in parts)


def _family(relative: str) -> str | None:
    """The root policy family of an exact repository-relative path; a Review path must be a Review record path."""
    if not _relative_shape(relative) or relative.endswith("/"):
        return None
    family = ROOT_POLICY_LAYOUT.family_of(relative)
    if family == "review":
        try:
            ROOT_POLICY_REVIEW_NAMESPACE.require_record_path(relative)
        except ValidationError:
            return None
    return family


def _scope_entry_problem(entry: object, operation: str) -> str | None:
    if entry == _review_prefix():
        return None if operation == OPERATION_CHANGE else "only a global-policy-change scopes the root Review namespace"
    if not isinstance(entry, str):
        return f"a write scope entry is a repository-relative path, not {entry!r}"
    family = _family(entry)
    if family is None or family not in _OPERATION_FAMILIES[operation]:
        return f"{entry!r} is not a {operation} path of the root policy layout"
    return None


#: The root families whose exact path names a Promotion Packet / Global Policy Change / evaluation ID (Amendment 4).
_ID_FAMILIES = ("promotion-packet", "change", "patch-note", "evaluation")


def _scope_entry_id(entry: str) -> str | None:
    """The ``rpp_`` / ``rgc_`` / ``rge_`` ID an exact write-scope path names, or None."""
    if _family(entry) not in _ID_FAMILIES:
        return None
    return entry.rsplit("/", 1)[1].rsplit(".", 1)[0]


def _in_scope(relative: str, write_scope: Sequence[str]) -> bool:
    if relative in write_scope:
        return True
    return _review_prefix() in write_scope and relative.startswith(_review_prefix())


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _encodable(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        value.encode("utf-8")
    except UnicodeError:
        return False
    return True


def _canonical(value: object, described: str) -> Any:
    try:
        found = serialize.canonical_data(value)
        if isinstance(found, dict) and not serialize.canonical_roundtrips(found):
            raise ValidationError("does not read back as itself", code="review_record_invalid")
        if not isinstance(found, dict) and not serialize.canonical_roundtrips({"value": found}):
            raise ValidationError("does not read back as itself", code="review_record_invalid")
    except (ValidationError, RecursionError) as exc:
        raise _refused(f"{described} is not canonical record data ({exc})") from exc
    return found


def _payload_problem(kind: str, payload: Mapping[str, Any], record: Mapping[str, Any],
                     effects: Sequence[Mapping[str, Any]]) -> str | None:
    """Why ``payload`` is not an exact payload of ``kind`` inside this mutation, or None."""
    operation = record["operation"]
    if kind in _CREATE_KINDS or kind == EFFECT_GLOBAL_POLICY_REPLACE:
        fields = REPLACE_PAYLOAD_FIELDS if kind == EFFECT_GLOBAL_POLICY_REPLACE else CREATE_PAYLOAD_FIELDS
        if set(payload) != set(fields):
            return f"a {kind} effect carries exactly {', '.join(fields)}"
        path, content = payload["path"], payload["content"]
        if not isinstance(path, str) or _family(path) != _KIND_FAMILY[kind]:
            return f"{path!r} is not a {_KIND_FAMILY[kind]} path of the root policy layout"
        if kind == EFFECT_REVIEW_CREATE and path.startswith(_consumption_prefix()):
            return f"{path} is a Global Consumption; it is created only as {EFFECT_CONSUMPTION_CREATE}"
        if kind == EFFECT_CONSUMPTION_CREATE and not path.startswith(_consumption_prefix()):
            return f"{path} is not under {_consumption_prefix()}"
        if not _in_scope(path, record["write_scope"]):
            return f"{path} is outside this root mutation's write scope"
        if not _encodable(content) or payload["sha256"] != _sha256(content):
            return f"the {kind} content of {path} is not UTF-8 text whose sha256 the payload names"
        if kind == EFFECT_GLOBAL_POLICY_REPLACE:
            expected, expected_sha = payload["expected_content"], payload["expected_sha256"]
            if (expected is None) != (expected_sha is None):
                return "a Global policy replace names its expected prior state by content and sha256 together"
            if expected is not None and (not _encodable(expected) or expected_sha != _sha256(expected)):
                return "the expected prior Global policy is not UTF-8 text whose sha256 the payload names"
            if expected_sha == payload["sha256"]:
                return "a Global policy replace replaces the policy with different bytes; a no-op is not recorded"
        return None
    if kind == EFFECT_COMMIT:
        if set(payload) != set(COMMIT_PAYLOAD_FIELDS):
            return f"a {kind} effect carries exactly {', '.join(COMMIT_PAYLOAD_FIELDS)}"
        if payload["stage"] not in OPERATION_STAGES[operation]:
            return f"{payload['stage']!r} is not a commit stage of {operation}"
        if not gitcmd.full_commit_id(payload["parent"]):
            return "a root commit names its exact parent by a full commit id"
        if payload["ref"] != record["branch"]:
            return f"a root commit moves only the frozen branch {record['branch']}"
        if not isinstance(payload["message"], str) or not payload["message"].strip() or not _encodable(payload["message"]):
            return "a root commit carries a message"
        if not isinstance(payload["date"], str) or _DATE.fullmatch(payload["date"]) is None:
            return "a root commit carries the timestamp it is recorded with, in Git's <seconds> <offset> form"
        paths = payload["paths"]
        if not isinstance(paths, list) or not paths or not all(isinstance(item, str) for item in paths) \
                or paths != sorted(set(paths), key=lambda item: item.encode("utf-8", "surrogatepass")):
            return "a root commit names each changed path once, in path byte order"
        for item in paths:
            if _family(item) is None or not _in_scope(item, record["write_scope"]):
                return f"a root commit commits {item!r}, which is outside this root mutation's write scope"
        return None
    if kind == EFFECT_PUSH:
        if set(payload) != set(PUSH_PAYLOAD_FIELDS):
            return f"a {kind} effect carries exactly {', '.join(PUSH_PAYLOAD_FIELDS)}"
        publication = record["publication"]
        if publication is None:
            return "a remote-less root publishes nothing"
        if payload["stage"] not in PUSH_STAGES[operation]:
            return f"the {payload['stage']!r} commit is never published on its own"
        if payload["remote"] != publication["remote"] or payload["ref"] != publication["branch"]:
            return "a root push goes only to the frozen authorized remote and branch"
        if not gitcmd.full_commit_id(payload["commit"]):
            return "a root push publishes one commit named by its full id"
        prepared = [effect for effect in effects if effect["kind"] == EFFECT_COMMIT
                    and effect["payload"]["stage"] == payload["stage"] and isinstance(effect["facts"], dict)
                    and effect["facts"].get("prepared_commit") == payload["commit"] and effect["facts"]["ref_moved"]]
        if not prepared:
            return (f"a root push publishes only the recorded {payload['stage']} commit whose ref this mutation moved, "
                    "never a branch tip")
        return None
    return f"{kind!r} is not a root effect kind"


def _identity_key(effect: Mapping[str, Any]) -> tuple[str, str]:
    payload = effect["payload"]
    if effect["kind"] in FILE_EFFECT_KINDS:
        return ("path", str(payload["path"]))
    return (str(effect["kind"]), str(payload["stage"]))


class RootMutation:
    """One single-purpose root policy mutation, open under the held root lock (§31.10).

    Not the Project MutationController and not a framework: its record names
    one root operation, and its effects are the closed set of
    :data:`OPERATION_EFFECTS` inside the frozen write scope. Every change of
    the record is written durably before the step it records is taken (intent
    first), so a replay finds what was decided and never decides it again.
    """

    def __init__(self, lock: RootLock, record: dict[str, Any]) -> None:
        self._lock = lock
        self._record = record

    @property
    def mutation_id(self) -> str:
        return str(self._record["mutation_id"])

    @property
    def operation(self) -> str:
        return str(self._record["operation"])

    @property
    def record(self) -> Mapping[str, Any]:
        """A read-only view of the record as it is stored."""
        return MappingProxyType(copy.deepcopy(self._record))

    # bookkeeping ----------------------------------------------------------------------------------------------
    def _writable(self) -> None:
        _require_held(self._lock)
        if self._record["status"] != STATUS_PENDING:
            raise _refused(f"the root mutation {self.mutation_id} is {self._record['status']}")

    def _save(self, record: dict[str, Any]) -> None:
        found = _canonical(record, f"the root mutation {self.mutation_id}")
        _write_runtime(self._lock.root, _mutation_rel(self.mutation_id), serialize.canonical_text(found))
        self._record = found

    def _updated(self) -> dict[str, Any]:
        return copy.deepcopy(self._record)

    # reservations (§31.11) ------------------------------------------------------------------------------------
    def reserve_id(self, key: str, kind: str) -> str:
        """The stable ID reserved under ``key``: allocated and stored durably once, the same one on every replay."""
        self._writable()
        if kind not in RESERVATION_KINDS:
            raise _refused(f"{kind!r} is not a root reservation kind")
        if not isinstance(key, str) or not key:
            raise _refused("a reservation key is non-empty text")
        existing = self._record["reserved_ids"].get(key)
        if existing is not None:
            if ids.kind_of(existing) != kind:
                raise reconcile(f"the root mutation {self.mutation_id} reserved {existing} under {key}, which is a "
                                f"{ids.kind_of(existing)}, not a {kind}", REASON_MUTATION_CONFLICT)
            return str(existing)
        identifier = ids.new_id(kind)
        record = self._updated()
        record["reserved_ids"][key] = identifier
        self._save(record)
        return identifier

    def reserved(self, key: str) -> str | None:
        value = self._record["reserved_ids"].get(key)
        return str(value) if value is not None else None

    # notes ----------------------------------------------------------------------------------------------------
    def note(self, key: str) -> Any:
        return copy.deepcopy(self._record["notes"].get(key))

    def set_note(self, key: str, value: Any) -> None:
        self._writable()
        if not isinstance(key, str) or not key:
            raise _refused("a note key is non-empty text")
        record = self._updated()
        record["notes"][key] = _canonical(value, f"the note {key}")
        self._save(record)

    # effects --------------------------------------------------------------------------------------------------
    def effects(self) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(effect) for effect in self._record["effects"])

    def add_effect(self, kind: str, payload: Mapping[str, Any]) -> int:
        """Record the intent of one canonical effect durably and return its index (the same one on a replay).

        Refused (``review_p7_root_effect_refused``) unless ``kind`` is one of
        this operation's :data:`OPERATION_EFFECTS`, a file effect's path is of
        the family its kind writes and inside the write scope, and the payload
        is exactly the kind's. An effect already recorded for the same path
        (or the same commit / push stage) is that effect: the identical
        payload returns its index, a different one is
        ``review_p7_root_effect_conflict``.
        """
        self._writable()
        if kind not in ROOT_EFFECT_KINDS or kind not in OPERATION_EFFECTS[self.operation]:
            raise _refused(f"{kind!r} is not an effect of {self.operation}")
        if not isinstance(payload, Mapping):
            raise _refused(f"a {kind} payload is a mapping")
        found = _canonical(dict(payload), f"the {kind} payload")
        problem = _payload_problem(kind, found, self._record, self._record["effects"])
        if problem is not None:
            raise _refused(problem)
        if kind in FILE_EFFECT_KINDS:
            # Where no create can be kept inside the root, none is recorded either (P1 / P6 capability rule).
            fsafe.require_immutable_create()
        effect = {"kind": kind, "payload": found, "state": STATE_INTENDED, "facts": None}
        key = _identity_key(effect)
        for index, existing in enumerate(self._record["effects"]):
            if _identity_key(existing) != key:
                continue
            if existing["kind"] == kind and existing["payload"] == found:
                return index
            raise reconcile(f"the root mutation {self.mutation_id} already records another effect for "
                            f"{key[1]} ({existing['kind']})", REASON_EFFECT_CONFLICT)
        record = self._updated()
        record["effects"].append(effect)
        self._save(record)
        return len(record["effects"]) - 1

    def _effect(self, index: int) -> dict[str, Any]:
        if type(index) is not int or not 0 <= index < len(self._record["effects"]):
            raise _refused(f"the root mutation {self.mutation_id} records no effect {index!r}")
        return self._record["effects"][index]

    def apply_effect(self, index: int) -> str:
        """Apply one recorded file effect exactly: ``"applied"`` or ``"matched"`` (its bytes were already there).

        An immutable create goes through the fsafe no-follow, create-exclusive
        primitive (other bytes there: ``review_p7_root_effect_conflict``, nothing
        replaced); the Global policy replace through
        ``fsafe.compare_and_replace`` from its exact expected prior bytes (a
        mismatch: ``review_p7_root_effect_conflict``, no overwrite). Both are
        refused on POSIX before any write (``fsafe.require_immutable_create``).
        """
        self._writable()
        effect = self._effect(index)
        kind = effect["kind"]
        if kind not in FILE_EFFECT_KINDS:
            raise _refused(f"a {kind} effect is marked with its facts, not applied")
        payload = effect["payload"]
        outcome = _apply_file_effect(self._lock.root, kind, payload)
        if effect["state"] != STATE_APPLIED:
            record = self._updated()
            record["effects"][index]["state"] = STATE_APPLIED
            self._save(record)
        return outcome

    def mark_effect(self, index: int, facts: Mapping[str, Any]) -> None:
        """Record a commit's or a push's facts durably; what was recorded is never contradicted later.

        A commit: ``prepared_commit`` / ``prepared_tree`` (full ids, fixed once
        recorded) and ``ref_moved`` (only ever false -> true, and true only
        while the frozen branch names the prepared commit). The prepared commit
        is durable before any ref moves (RB7C-5, RB7BL-1): a commit's FIRST
        facts say ``ref_moved: false``, so a commit with no facts recorded never
        moved its ref through this mutation. A push: ``pushed`` (only ever
        false -> true).
        """
        self._writable()
        effect = self._effect(index)
        kind = effect["kind"]
        if kind not in (EFFECT_COMMIT, EFFECT_PUSH):
            raise _refused(f"a {kind} effect is applied, not marked")
        if not isinstance(facts, Mapping):
            raise _refused(f"{kind} facts are a mapping")
        found = dict(facts)
        previous = effect["facts"]
        if kind == EFFECT_COMMIT:
            if set(found) != set(COMMIT_FACT_FIELDS) or not gitcmd.full_commit_id(found["prepared_commit"]) \
                    or not gitcmd.full_commit_id(found["prepared_tree"]) or type(found["ref_moved"]) is not bool:
                raise _refused(f"root commit facts are exactly {', '.join(COMMIT_FACT_FIELDS)}")
            if previous is None:
                if found["ref_moved"]:
                    raise _refused(f"the {effect['payload']['stage']} commit of root mutation {self.mutation_id} "
                                   "records its prepared commit (ref_moved false) before its ref moves, never first "
                                   "as moved")
                named = gitcmd.branch_commit(self._lock.root, effect["payload"]["ref"])
                if named != effect["payload"]["parent"] and (
                        named is None or named == found["prepared_commit"]
                        or gitcmd.descends_from(self._lock.root, named, found["prepared_commit"]) is not False):
                    raise reconcile(f"{effect['payload']['ref']} already holds the {effect['payload']['stage']} "
                                    "commit, or cannot be read, while its prepared commit was never recorded; a ref "
                                    "moves only after the prepared commit is durable", REASON_EFFECT_CONFLICT)
            if previous is not None:
                if (previous["prepared_commit"], previous["prepared_tree"]) != (found["prepared_commit"],
                                                                                found["prepared_tree"]):
                    raise reconcile(f"the {effect['payload']['stage']} commit of root mutation {self.mutation_id} was "
                                    "recorded as another prepared commit", REASON_EFFECT_CONFLICT)
                if previous["ref_moved"] and not found["ref_moved"]:
                    raise reconcile(f"the {effect['payload']['stage']} commit of root mutation {self.mutation_id} "
                                    "was recorded with its ref moved", REASON_EFFECT_CONFLICT)
            if found["ref_moved"] and not (previous or {}).get("ref_moved"):
                named = gitcmd.branch_commit(self._lock.root, effect["payload"]["ref"])
                if named != found["prepared_commit"]:
                    raise reconcile(f"{effect['payload']['ref']} does not name the prepared "
                                    f"{effect['payload']['stage']} commit, so its move is not recorded",
                                    REASON_EFFECT_CONFLICT)
        else:
            if set(found) != set(PUSH_FACT_FIELDS) or type(found["pushed"]) is not bool:
                raise _refused(f"root push facts are exactly {', '.join(PUSH_FACT_FIELDS)}")
            if previous is not None and previous["pushed"] and not found["pushed"]:
                raise reconcile(f"the {effect['payload']['stage']} push of root mutation {self.mutation_id} was "
                                "recorded as done", REASON_EFFECT_CONFLICT)
        if previous == found:
            return
        record = self._updated()
        record["effects"][index]["facts"] = found
        record["effects"][index]["state"] = STATE_MARKED
        self._save(record)

    # closing --------------------------------------------------------------------------------------------------
    def complete(self) -> None:
        """Close the mutation as completed: only once every recorded effect is applied or marked done."""
        self._writable()
        for index, effect in enumerate(self._record["effects"]):
            if not _effect_done(effect):
                raise _refused(f"the root mutation {self.mutation_id} still has effect {index} ({effect['kind']}) "
                               "not done, so it is not completed")
        record = self._updated()
        record["status"] = STATUS_COMPLETED
        self._save(record)

    def abandon(self) -> None:
        """Close the mutation as abandoned: only while no canonical effect of it has been applied.

        Applied means recorded so, or found so now: a file effect whose exact
        bytes are at its path, a commit whose prepared commit the branch names
        or descends from - or, with no prepared commit recorded, whose branch
        is anywhere but its recorded parent - and any recorded push intent
        (whether it reached the remote cannot be known here). Anything of that
        kind is ``review_p7_root_abandon_refused``: such a mutation is completed
        or reconciled, never dropped.
        """
        self._writable()
        for index, effect in enumerate(self._record["effects"]):
            if _effect_may_be_applied(self._lock.root, effect):
                raise reconcile(f"the root mutation {self.mutation_id} may already have applied effect {index} "
                                f"({effect['kind']}), so it is not abandoned", REASON_ABANDON_REFUSED)
        record = self._updated()
        record["status"] = STATUS_ABANDONED
        self._save(record)


def _effect_done(effect: Mapping[str, Any]) -> bool:
    if effect["kind"] in FILE_EFFECT_KINDS:
        return effect["state"] == STATE_APPLIED
    facts = effect["facts"]
    if effect["kind"] == EFFECT_COMMIT:
        return isinstance(facts, dict) and facts.get("ref_moved") is True
    return isinstance(facts, dict) and facts.get("pushed") is True


def _effect_may_be_applied(root: Path, effect: Mapping[str, Any]) -> bool:
    kind = effect["kind"]
    if kind == EFFECT_PUSH:
        return True
    if kind == EFFECT_COMMIT:
        facts = effect["facts"]
        if isinstance(facts, dict) and facts.get("ref_moved"):
            return True
        named = gitcmd.branch_commit(root, effect["payload"]["ref"])
        if named is None:
            return True  # Git cannot say: not provably unapplied
        if not isinstance(facts, dict):
            # No prepared commit recorded (RB7BL-1): only the branch still at the recorded parent proves that
            # nothing moved; a branch anywhere else is not provably unapplied.
            return named != effect["payload"]["parent"]
        if named == facts["prepared_commit"]:
            return True
        return gitcmd.descends_from(root, named, facts["prepared_commit"]) is not False
    if effect["state"] == STATE_APPLIED:
        return True
    parts = effect["payload"]["path"].split("/")
    try:
        chain = fsafe.walk(Path(root), parts[:-1])
        if chain is None:
            return False
        with chain:
            stored = chain.last.read_file(parts[-1])
    except ValidationError:
        return True  # an indirection: not provably unapplied
    return stored is not None and stored == effect["payload"]["content"].encode("utf-8")


def _apply_file_effect(root: Path, kind: str, payload: Mapping[str, Any]) -> str:
    fsafe.require_immutable_create()
    relative = payload["path"]
    parts = relative.split("/")
    data = payload["content"].encode("utf-8")
    if kind == EFFECT_GLOBAL_POLICY_REPLACE:
        expected = payload["expected_content"]
        outcome = fsafe.compare_and_replace(Path(root), parts, None if expected is None else expected.encode("utf-8"),
                                            data, list(TMP_PARTS))
        if outcome == fsafe.CAS_REPLACED:
            return APPLIED
        if outcome == fsafe.CAS_MATCHING:
            return MATCHED
        raise reconcile(f"{relative} does not hold the exact prior Global policy this change was decided against; "
                        "the Global policy is never overwritten on a before-state mismatch", REASON_EFFECT_CONFLICT)
    name = parts[-1]
    with fsafe.walk(Path(root), parts[:-1], create=True) as parent, \
            fsafe.walk(Path(root), list(TMP_PARTS), create=True) as tmp:
        if parent.last.create_file_exclusive(name, data, tmp.last):
            return APPLIED
        if parent.last.read_file(name) == data:
            return MATCHED
    raise reconcile(f"{relative} already exists and does not hold the record this root mutation creates; an "
                    "immutable root record is never overwritten", REASON_EFFECT_CONFLICT)


def _strict(value: object) -> str:
    """A type-exact comparison key (``True`` is not ``1``) for a resume's frozen values."""
    return json.dumps(value, sort_keys=True, default=repr)


def _mutation_rel(mutation_id: str) -> str:
    return f"{MUTATIONS_DIR}/{mutation_id}.yaml"


_MUTATION_NAME = re.compile(r"(rpm_[0-9A-HJKMNP-TV-Z]{26})\.yaml\Z")


def _mutation_problem(record: object, mutation_id: str) -> str | None:
    """Why ``record`` is not exactly a root mutation record named ``mutation_id``, or None (RB7BL-4).

    Types and values are checked, not key sets alone: every value a later step
    dereferences - the write scope, each effect payload (re-checked with the very
    rule :meth:`RootMutation.add_effect` applied when it was recorded), each
    effect's state and facts - is proven here, so a corrupted record is
    ``review_p7_root_mutation_unreadable`` and never a crash further on. A value
    of a shape no check anticipated is caught here too and read the same way.
    """
    try:
        return _mutation_record_problem(record, mutation_id)
    except (TypeError, AttributeError, KeyError, IndexError, ValueError, RecursionError) as exc:
        return f"it holds a value of an unexpected shape ({type(exc).__name__})"


def _mutation_record_problem(record: object, mutation_id: str) -> str | None:
    if not isinstance(record, dict) or set(record) != set(MUTATION_FIELDS):
        return "it is not exactly the root mutation record fields"
    if record["schema"] != MUTATION_SCHEMA or record["version"] != MUTATION_VERSION:
        return f"it is not a {MUTATION_SCHEMA} version {MUTATION_VERSION} record"
    if record["mutation_id"] != mutation_id or not ids.is_valid_id(mutation_id, "root_policy_mutation"):
        return "its mutation_id is not the one its file is named by"
    operation = record["operation"]
    if not isinstance(operation, str) or operation not in OPERATIONS or not isinstance(record["status"], str) \
            or record["status"] not in MUTATION_STATUSES:
        return "it names no root operation or status"
    if not isinstance(record["invocation"], dict) or not record["invocation"] or not _full_ref(record["branch"]) \
            or not gitcmd.full_commit_id(record["base"]):
        return "its invocation, branch or base is malformed"
    global_policy = record["global_policy"]
    if not isinstance(global_policy, dict) or set(global_policy) != {"version", "digest"} \
            or type(global_policy["version"]) is not int or global_policy["version"] < 1 \
            or not isinstance(global_policy["digest"], str) or _DIGEST.fullmatch(global_policy["digest"]) is None:
        return "its Global policy version / digest is malformed"
    reserved = record["reserved_ids"]
    if not isinstance(reserved, dict) or any(not isinstance(key, str) or not key or not isinstance(value, str)
                                             or ids.kind_of(value) not in RESERVATION_KINDS
                                             for key, value in reserved.items()):
        return "its reserved IDs are malformed"
    scope = record["write_scope"]
    if not isinstance(scope, list) or not scope or not all(isinstance(entry, str) for entry in scope) \
            or scope != sorted(set(scope)) or any(_scope_entry_problem(entry, operation) for entry in scope):
        return "its write scope is malformed"
    publication = record["publication"]
    if publication is not None and (not isinstance(publication, dict) or set(publication) != {"remote", "branch"}
                                    or not isinstance(publication["remote"], str) or not publication["remote"]
                                    or publication["branch"] != record["branch"]):
        return "its publication binding is malformed"
    if not isinstance(record["notes"], dict) or any(not isinstance(key, str) or not key for key in record["notes"]) \
            or not isinstance(record["effects"], list):
        return "its notes or effects are malformed"
    seen: set[tuple[str, str]] = set()
    effects = record["effects"]
    for index, effect in enumerate(effects):
        if not isinstance(effect, dict) or set(effect) != set(EFFECT_FIELDS) or not isinstance(effect["kind"], str) \
                or effect["kind"] not in OPERATION_EFFECTS[operation] or not isinstance(effect["payload"], dict) \
                or not isinstance(effect["state"], str) or effect["state"] not in EFFECT_STATES:
            return f"effect {index} is malformed"
        kind, state, facts = effect["kind"], effect["state"], effect["facts"]
        if kind in FILE_EFFECT_KINDS:
            if facts is not None or state == STATE_MARKED:
                return f"effect {index} ({kind}) carries facts"
        elif kind == EFFECT_COMMIT:
            if (facts is None) != (state == STATE_INTENDED) or state == STATE_APPLIED:
                return f"effect {index} ({kind}) has a state its facts do not support"
            if facts is not None and (not isinstance(facts, dict) or set(facts) != set(COMMIT_FACT_FIELDS)
                                      or not gitcmd.full_commit_id(facts["prepared_commit"])
                                      or not gitcmd.full_commit_id(facts["prepared_tree"])
                                      or type(facts["ref_moved"]) is not bool):
                return f"effect {index} ({kind}) carries malformed facts"
        else:
            if (facts is None) != (state == STATE_INTENDED) or state == STATE_APPLIED:
                return f"effect {index} ({kind}) has a state its facts do not support"
            if facts is not None and (not isinstance(facts, dict) or set(facts) != set(PUSH_FACT_FIELDS)
                                      or type(facts["pushed"]) is not bool):
                return f"effect {index} ({kind}) carries malformed facts"
        problem = _payload_problem(kind, effect["payload"], record, effects[:index])
        if problem is not None:
            return f"effect {index} ({kind}) is not one this mutation could have recorded: {problem}"
        key = _identity_key(effect)
        if key in seen:
            return f"two effects are recorded for {key[1]}"
        seen.add(key)
    return None


def _scan_mutations(root: Path) -> list[dict[str, Any]]:
    """Every root mutation record in the runtime, read-only and without following anything; reconcile if unreadable."""
    parts = MUTATIONS_DIR.split("/")
    try:
        chain = fsafe.walk(Path(root), parts)
    except ValidationError as exc:
        raise reconcile(f"the root mutation records cannot be read without following an indirection ({exc})",
                        REASON_MUTATION_UNREADABLE) from exc
    if chain is None:
        return []
    found: list[dict[str, Any]] = []
    with chain:
        try:
            entries = chain.last.entries()
        except ValidationError as exc:
            raise reconcile(f"the root mutation records cannot be listed ({exc})", REASON_MUTATION_UNREADABLE) from exc
        for entry in sorted(entries, key=lambda item: item.name):
            matched = _MUTATION_NAME.fullmatch(entry.name)
            if matched is None or not entry.is_file or entry.is_indirection:
                raise reconcile(f"{MUTATIONS_DIR}/{entry.name} is not a root mutation record",
                                REASON_MUTATION_UNREADABLE)
            described = f"the root mutation record {MUTATIONS_DIR}/{entry.name}"
            try:
                raw = chain.last.read_file(entry.name)
                if raw is None:
                    continue
                record, _ = serialize.parse_canonical(raw, described)
            except ValidationError as exc:
                raise reconcile(f"{described} is unreadable ({exc})", REASON_MUTATION_UNREADABLE) from exc
            problem = _mutation_problem(record, matched.group(1))
            if problem is not None:
                raise reconcile(f"{described} is unreadable: {problem}", REASON_MUTATION_UNREADABLE)
            found.append(record)
    return found


def pending_mutations(workline_root: Path) -> list[dict[str, Any]]:
    """The pending root mutation records, read-only and without the lock; ``review_p7_root_mutation_unreadable``
    when the runtime holds anything that cannot be read as one (fail closed: never read past a record)."""
    return [record for record in _scan_mutations(Path(workline_root)) if record["status"] == STATUS_PENDING]


def pending_for_run(workline_root: Path, review_run_id: str) -> list[dict[str, Any]]:
    """The pending root mutations that create a record of root Review Run ``review_run_id`` (the recovery hook).

    The root analogue of a pending generation mutation holding the Run's
    serialization token (``gate.pending_generation_mutations``): a pending
    record with an :data:`EFFECT_REVIEW_CREATE` under
    ``ROOT_POLICY_REVIEW_NAMESPACE.run_dir(review_run_id) + "/"``. Read-only.
    """
    prefix = ROOT_POLICY_REVIEW_NAMESPACE.run_dir(review_run_id) + "/"
    return [record for record in pending_mutations(workline_root)
            if any(effect["kind"] == EFFECT_REVIEW_CREATE and str(effect["payload"]["path"]).startswith(prefix)
                   for effect in record["effects"])]


def open_mutation(lock: RootLock, invocation: Mapping[str, Any], *, branch: str, base: str,
                  global_policy_version: int, global_policy_digest: str, write_scope: Sequence[str],
                  publication: Mapping[str, Any] | None, rebind: Mapping[str, str] | None = None,
                  reserved: Mapping[str, str] | None = None) -> RootMutation:
    """Open - or resume - the one root mutation of this root operation, under the held lock.

    One pending root mutation at a time (single-writer root maintenance). A
    pending one whose ``invocation`` is canonically equal is returned as it is
    stored (a resume); any other pending one is
    ``review_p7_root_mutation_conflict``. A resume re-freezes nothing: the
    caller passes the record's frozen ``branch``, ``base``, Global policy
    version / digest and ``publication`` (read from :func:`pending_mutations`),
    and an argument that differs from the record is
    ``review_p7_root_mutation_conflict`` (RB7BL-2, §31.30: an unexpected HEAD
    or branch is reconciled, never silently replaced by the record's). The
    ``write_scope`` argument is not compared: its exact family paths name IDs
    the mutation itself reserved, so a resume reads ``record["write_scope"]``.
    Otherwise a new ``root_policy_mutation`` ID and a durable record.
    ``rebind`` (runtime-loss recovery only, §31.11) pre-seeds canonical IDs
    reconstructed from committed records and is refused while any pending
    record exists.

    ``reserved`` (Amendment 4: first-open reservations for the exact write
    scope) is accepted only when a NEW mutation is created - with a pending
    record it is ``review_p7_root_mutation_conflict`` - and never together with
    ``rebind`` (``review_p7_root_effect_refused``). Each item is a stable
    reservation key and an ID of a :data:`RESERVATION_KINDS` kind the caller
    allocated immediately before the open; the record's first durable write
    stores them, so :meth:`RootMutation.reserve_id` returns them from then on
    (§31.11: the first allocation stored durably, a retry returns the same ID).
    With ``reserved`` - or, on a recovery open, ``rebind`` - every exact
    write-scope path that names an ``rpp_`` / ``rgc_`` / ``rge_`` ID must name
    one of those IDs (``review_p7_root_effect_refused``), so no frozen scope
    path names an ID the mutation does not own. A call with neither behaves
    exactly as before.
    """
    _require_held(lock)
    if lock.operation not in OPERATIONS:
        raise _refused(f"the {lock.operation} lock opens no root mutation")
    if reserved is not None and rebind is not None:
        raise _refused("first-open reservations and a runtime-loss rebind are never given together")
    found_invocation = _canonical(dict(invocation), "the invocation") if isinstance(invocation, Mapping) else None
    if not isinstance(found_invocation, dict) or not found_invocation:
        raise _refused("a root mutation names its invocation by a non-empty mapping")
    pending = pending_mutations(lock.root)
    if pending:
        if len(pending) > 1:
            raise reconcile("the Workline root has " + str(len(pending)) + " pending root mutations ("
                            + ", ".join(record["mutation_id"] for record in pending) + ")", REASON_MUTATION_CONFLICT)
        existing = pending[0]
        if rebind is not None:
            raise reconcile(f"the pending root mutation {existing['mutation_id']} still exists, so nothing is rebound "
                            "beside it", REASON_MUTATION_CONFLICT)
        if reserved is not None:
            raise reconcile(f"the pending root mutation {existing['mutation_id']} already holds its reservations; a "
                            "resume passes none (reserved=None) and reads them from the record",
                            REASON_MUTATION_CONFLICT)
        if existing["operation"] != lock.operation or existing["invocation"] != found_invocation:
            raise reconcile(f"the pending root mutation {existing['mutation_id']} ({existing['operation']}) belongs to "
                            "another invocation; it is resumed with that invocation or reconciled first",
                            REASON_MUTATION_CONFLICT)
        given = {
            "branch": branch,
            "base": base,
            "global_policy": {"version": global_policy_version, "digest": global_policy_digest},
            "publication": dict(publication) if isinstance(publication, Mapping) else publication,
        }
        differing = sorted(name for name, value in given.items() if _strict(value) != _strict(existing[name]))
        if differing:
            raise reconcile(f"the pending root mutation {existing['mutation_id']} froze another "
                            + ", ".join(differing) + " than this resume passes; a resume re-freezes nothing and is "
                            "never silently given the record's values in place of the caller's",
                            REASON_MUTATION_CONFLICT)
        return RootMutation(lock, existing)
    if not _full_ref(branch):
        raise _refused(f"a root mutation freezes its branch by its full ref name, not {branch!r}")
    if not gitcmd.full_commit_id(base):
        raise _refused("a root mutation freezes its exact base commit by its full id")
    if type(global_policy_version) is not int or global_policy_version < 1 \
            or not isinstance(global_policy_digest, str) or _DIGEST.fullmatch(global_policy_digest) is None:
        raise _refused("a root mutation freezes the current Global policy version and its exact digest")
    if isinstance(write_scope, (str, bytes)) or not isinstance(write_scope, Sequence) or not write_scope:
        raise _refused("a root mutation freezes a non-empty write scope")
    for entry in write_scope:
        problem = _scope_entry_problem(entry, lock.operation)
        if problem is not None:
            raise _refused(problem)
    scope = sorted(set(write_scope))
    if publication is not None:
        if not isinstance(publication, Mapping) or set(publication) != {"remote", "branch"} \
                or not isinstance(publication["remote"], str) or not publication["remote"] \
                or publication["branch"] != branch:
            raise _refused("a root mutation's publication binding is exactly {remote, branch} of its own branch - "
                           "never a locator or a repository identity")
        bound: dict[str, str] | None = {"remote": publication["remote"], "branch": publication["branch"]}
    else:
        bound = None
    seeded: dict[str, str] = {}
    if rebind is not None:
        if not isinstance(rebind, Mapping):
            raise _refused("a rebind is a mapping of reservation keys to canonical IDs")
        for key, value in rebind.items():
            if not isinstance(key, str) or not key or not isinstance(value, str) \
                    or ids.kind_of(value) not in RESERVATION_KINDS:
                raise _refused(f"{value!r} is not a canonical ID a root mutation reserves")
            seeded[key] = value
    if reserved is not None:
        if not isinstance(reserved, Mapping):
            raise _refused("first-open reservations are a mapping of reservation keys to IDs")
        for key, value in reserved.items():
            if not isinstance(key, str) or not key or not isinstance(value, str) or "\n" in value \
                    or ids.kind_of(value) not in RESERVATION_KINDS:
                raise _refused(f"{value!r} is not an ID of a kind a root mutation reserves")
            seeded[key] = value
    if reserved is not None or rebind is not None:
        owned = set(seeded.values())
        for entry in scope:
            identifier = _scope_entry_id(entry)
            if identifier is not None and identifier not in owned:
                raise _refused(f"the write scope path {entry} names {identifier}, which this mutation does not "
                               "reserve")
    mutation_id = ids.new_id("root_policy_mutation")
    record = {
        "schema": MUTATION_SCHEMA,
        "version": MUTATION_VERSION,
        "mutation_id": mutation_id,
        "operation": lock.operation,
        "status": STATUS_PENDING,
        "invocation": found_invocation,
        "branch": branch,
        "base": base,
        "global_policy": {"version": global_policy_version, "digest": global_policy_digest},
        "reserved_ids": seeded,
        "write_scope": scope,
        "effects": [],
        "notes": {},
        "publication": bound,
    }
    mutation = RootMutation(lock, {"mutation_id": mutation_id, "operation": lock.operation,
                                   "status": STATUS_PENDING})
    mutation._save(record)
    return mutation


# --------------------------------------------------------------------------- authorization and repository identity (§31.12, §31.13)


@dataclass(frozen=True)
class Authorization:
    remote: str
    branch: str  # full destination ref, e.g. refs/heads/main
    locator: str  # the exact approved push locator (runtime-only; never in a canonical record or status)
    repository_identity: str


@dataclass(frozen=True)
class PublicationBinding:
    remote: str
    branch: str
    locator: str


def repository_identity(workline_root: Path) -> str:
    """The opaque local identity of the root repository instance (§31.13): never a path, never recorded canonically.

    SHA-256 over positive local facts only: the filesystem identity
    ``(st_dev, st_ino)`` of the root directory, that of its Git common
    directory, and its object format. Another clone has other directories;
    another worktree of the same repository has another root directory. Any
    fact unavailable is ``review_p7_repository_identity_unavailable``.
    """
    try:
        root = Path(workline_root).resolve()
        root_info = os.stat(root)
    except OSError as exc:
        raise stop(CODE_REPOSITORY_IDENTITY_UNAVAILABLE, f"the Workline root cannot be examined ({exc})") from exc
    common = gitcmd.git_common_dir(root)
    found_format = gitcmd.object_format(root)
    if common is None or not found_format:
        raise stop(CODE_REPOSITORY_IDENTITY_UNAVAILABLE,
                   "the Workline root's Git common directory or object format cannot be read")
    try:
        common_info = os.stat(common)
    except OSError as exc:
        raise stop(CODE_REPOSITORY_IDENTITY_UNAVAILABLE, f"the Git common directory cannot be examined ({exc})") from exc
    if not root_info.st_ino or not common_info.st_ino:
        raise stop(CODE_REPOSITORY_IDENTITY_UNAVAILABLE,
                   "this filesystem reports no file identity for the Workline root or its Git common directory")
    return serialize.digest({
        serialize.SCHEMA_KEY: REPOSITORY_IDENTITY_SCHEMA,
        serialize.VERSION_KEY: 1,
        "root": [int(root_info.st_dev), int(root_info.st_ino)],
        "git_common_dir": [int(common_info.st_dev), int(common_info.st_ino)],
        "object_format": found_format,
    })


def _active_locator(root: Path, remote: str) -> str:
    """``destination.resolve_active_push_locator``, with a locator Git cannot report at all read as unresolved."""
    try:
        return destination.resolve_active_push_locator(root, remote)
    except GitError as exc:
        raise StopError(f"the push locator of remote {remote} cannot be read ({exc})",
                        code=CODE_PUSH_DESTINATION_UNRESOLVED) from exc


def _authorization_from(record: object) -> Authorization | None:
    if not isinstance(record, dict) or set(record) != set(AUTHORIZATION_FIELDS):
        return None
    if record["schema"] != AUTHORIZATION_SCHEMA or record["version"] != AUTHORIZATION_VERSION \
            or record["contract"] != AUTHORIZATION_CONTRACT:
        return None
    remote, branch, locator, identity = (record["remote"], record["branch"], record["locator"],
                                         record["repository_identity"])
    if not isinstance(remote, str) or not remote or not _full_ref(branch) or not isinstance(locator, str) \
            or not locator or pushurl.is_secret_bearing(locator) or not isinstance(identity, str) \
            or _DIGEST.fullmatch(identity) is None:
        return None
    return Authorization(remote, branch, locator, identity)


def _authorization_state(root: Path) -> tuple[str, Authorization | None]:
    """``("absent" | "unreadable" | "present", authorization)``: read-only, no-follow, never repaired."""
    try:
        raw = _read_runtime(root, AUTHORIZATION_REL)
    except (ValidationError, OSError):
        return "unreadable", None
    if raw is None:
        return "absent", None
    try:
        record, _ = serialize.parse_canonical(raw, "the root maintenance authorization")
    except ValidationError:
        return "unreadable", None
    found = _authorization_from(record)
    return ("present", found) if found is not None else ("unreadable", None)


def read_authorization(workline_root: Path) -> Authorization | None:
    """The stored root maintenance authorization; ``None`` when absent or malformed. Read-only."""
    return _authorization_state(Path(workline_root))[1]


def authorize(workline_root: Path, *, remote: str, branch: str, locator: str) -> Authorization:
    """Record the Human-approved local root publication authorization (§31.12), mutation-capable.

    Refused from inside a Project (:func:`require_root_invocation`), then
    under the root lock: ``remote`` is one of the root's remotes, ``locator``
    carries no credentials (``push_destination_secret``) and is exactly the
    one active push locator Git resolves for it now (several:
    ``push_destination_multiple``; none or unreadable:
    ``push_destination_unresolved``), and ``branch`` is exactly the full ref
    of the root's current branch; anything else is
    ``review_p7_authorization_invalid`` and nothing is written. The record
    binds them to the opaque local repository identity; it is local, ignored
    and clone-specific, and never inferred from ``origin``.
    """
    require_root_invocation()
    with root_operation(workline_root, OPERATION_AUTHORIZE) as lock:
        root = lock.root
        if not isinstance(remote, str) or not remote or remote not in gitcmd.remotes(root):
            raise stop(CODE_AUTHORIZATION_INVALID, f"the Workline root has no remote {remote!r}; nothing was "
                       "authorized")
        if not isinstance(locator, str) or not locator:
            raise stop(CODE_AUTHORIZATION_INVALID, "an authorization names the exact approved push locator")
        pushurl.ensure_no_secret(locator, "the approved root push locator")
        active = _active_locator(root, remote)
        if active != locator:
            raise stop(CODE_AUTHORIZATION_INVALID,
                       f"remote {remote} does not push to the approved locator {pushurl.redact(locator)} now; "
                       "two spellings of a repository are never the same one. Nothing was authorized")
        current = gitcmd.current_branch_ref(root)
        if not _full_ref(branch) or branch != current:
            raise stop(CODE_AUTHORIZATION_INVALID,
                       f"{branch!r} is not the full ref of the Workline root's current branch ({current or 'none'}); "
                       "nothing was authorized")
        identity = repository_identity(root)
        record = {
            serialize.SCHEMA_KEY: AUTHORIZATION_SCHEMA,
            serialize.VERSION_KEY: AUTHORIZATION_VERSION,
            "contract": AUTHORIZATION_CONTRACT,
            "repository_identity": identity,
            "remote": remote,
            "branch": branch,
            "locator": locator,
        }
        _write_runtime(root, AUTHORIZATION_REL, serialize.canonical_text(record))
        return Authorization(remote, branch, locator, identity)


def _binding_problem(root: Path, found: Authorization) -> str | None:
    """Why ``found`` does not bind the root's publication now, or None. Reused STOPs of the locator propagate."""
    if repository_identity(root) != found.repository_identity:
        return "it was made for another repository instance (a copy in another clone or worktree authorizes nothing)"
    if found.remote not in gitcmd.remotes(root):
        return f"the root has no remote {found.remote} any more"
    if gitcmd.current_branch_ref(root) != found.branch:
        return f"the root is no longer on the authorized branch {found.branch}"
    if _active_locator(root, found.remote) != found.locator:
        return f"remote {found.remote} no longer pushes to the authorized locator"
    return None


def publication_binding(workline_root: Path) -> PublicationBinding | None:
    """The root's publication binding now, or STOP; ``None`` ONLY for a root with no remote at all (§31.12).

    With a remote, a valid authorization is required whose repository
    identity, remote, branch (the current branch's full ref) and locator (the
    active push locator Git resolves now) all match:
    ``review_p7_authorization_required`` when there is none (absent or
    unreadable), ``review_p7_authorization_mismatch`` when anything differs.
    It is never inferred from ``origin``. Read-only.
    """
    root = Path(workline_root).resolve()
    if not gitcmd.remotes(root):
        return None
    state, found = _authorization_state(root)
    if found is None:
        raise stop(
            CODE_AUTHORIZATION_REQUIRED,
            "the Workline root has a remote and no " + ("readable " if state == "unreadable" else "")
            + "root maintenance authorization; a Human approves the exact remote, branch and push locator once "
            "(root-policy-maintenance-authorize) before root policy maintenance publishes",
        )
    problem = _binding_problem(root, found)
    if problem is not None:
        raise stop(CODE_AUTHORIZATION_MISMATCH, f"the root maintenance authorization does not hold now: {problem}; "
                   "authorize again")
    return PublicationBinding(found.remote, found.branch, found.locator)


# --------------------------------------------------------------------------- committability (RB7C-9)


def _committability_probes(relative: str) -> list[str]:
    """The exact paths a preflight entry stands for: itself, or - for the Review prefix - its directories and a
    representative record of each, so a rule on any of them (or on ``*.yaml``) is seen."""
    if relative != _review_prefix():
        return [relative]
    namespace = ROOT_POLICY_REVIEW_NAMESPACE
    run = "rr_" + "0" * 26
    digest = "0" * 64
    probes = [relative] + [f"{namespace.root}/{subdir}/" for subdir in namespace.subdirs]
    builders = {
        "gates": lambda: namespace.gate_rel(run, 1),
        "receipts": lambda: namespace.receipt_rel("rcp_" + "0" * 26),
        "consumptions": lambda: namespace.consumption_rel("rcs_" + "0" * 26),
        "supersessions": lambda: namespace.supersession_rel("rcp_" + "0" * 26),
        "candidate-snapshots": lambda: namespace.candidate_snapshot_rel(digest),
        "task-inputs": lambda: namespace.task_input_rel("rtk_" + "0" * 26),
        "reports": lambda: namespace.report_rel(digest),
        "adjudications": lambda: namespace.adjudication_rel(run),
    }
    for subdir in namespace.subdirs:
        if subdir in builders:
            probes.append(builders[subdir]())
    return probes


def _owned(relative: object) -> bool:
    if not _relative_shape(relative):
        return False
    for prefix in ROOT_POLICY_LAYOUT.owned_prefixes():
        if prefix.endswith("/") and str(relative).startswith(prefix):
            return True
        if relative == prefix:
            return True
    return False


def require_committable(workline_root: Path, relatives: Sequence[str]) -> None:
    """Refuse a root effect set the root repository would not commit (RB7C-9), before the first canonical effect.

    Every entry lies inside ``ROOT_POLICY_LAYOUT.owned_prefixes()`` (else
    ``review_p7_root_effect_refused``); each is asked of Git's own ignore
    evaluation - for the ``review-policy/review/`` prefix entry, its
    directories and a representative record of each - and an ignored one is
    ``review_path_ignored``, an undeterminable one
    ``review_committability_unknown``. Workline never edits ignore
    configuration to make a root path committable. Read-only.
    """
    root = Path(workline_root)
    if isinstance(relatives, (str, bytes)):
        raise _refused("the committability preflight takes the whole effect set, not one path")
    for relative in relatives:
        if not _owned(relative):
            raise _refused(f"{relative!r} is outside the root policy layout")
        for probe in _committability_probes(relative):
            ignored = gitcmd.is_ignored(root, probe)
            if ignored is None:
                raise StopError(
                    f"git cannot say whether {probe} is ignored in the Workline root, so whether this root record "
                    "would reach the committed state cannot be shown: STOP",
                    code=CODE_COMMITTABILITY_UNKNOWN,
                )
            if ignored:
                raise StopError(
                    f"{probe} is excluded by the Workline root's ignore rules, so a root record written there would "
                    "never be committed; Workline does not change ignore configuration to make it committable: STOP",
                    code=CODE_PATH_IGNORED,
                )


# --------------------------------------------------------------------------- read-only status (§31.46, RB7C-4)


def _global_policy_digest(baseline: review_policy.GlobalPolicyBaseline) -> str:
    """The exact digest of the current Global policy record (what a change record's after digest names)."""
    if baseline.source_mode == review_policy.SOURCE_MODE_MATERIALIZED:
        return baseline.global_policy_identity
    return review_policy.global_policy_digest(review_policy.global_policy_from_baseline(baseline))


def _family_records(root: Path, directory: str, family: str, id_field: str) -> list[tuple[str, dict[str, Any]]]:
    """``(id, record)`` of each root record of ``family`` in ``directory``, read no-follow and canonical-only."""
    chain = fsafe.walk(root, directory.split("/"))
    if chain is None:
        return []
    found: list[tuple[str, dict[str, Any]]] = []
    with chain:
        for entry in sorted(chain.last.entries(), key=lambda item: item.name):
            relative = f"{directory}/{entry.name}"
            if ROOT_POLICY_LAYOUT.family_of(relative) != family:
                continue
            raw = chain.last.read_file(entry.name)
            if raw is None:
                continue
            record, _ = serialize.parse_canonical(raw, relative)
            identifier = entry.name.rsplit(".", 1)[0]
            if record.get(id_field) != identifier:
                raise ValidationError(f"{relative} does not name itself as {identifier}", code="review_record_invalid")
            found.append((identifier, record))
    return found


def _authorization_status(root: Path) -> dict[str, Any]:
    state, found = _authorization_state(root)
    try:
        has_remote = bool(gitcmd.remotes(root))
    except StopError:
        return {"status": "unreadable", "remote": None, "branch": None}
    named = {"remote": found.remote if found else None, "branch": found.branch if found else None}
    if not has_remote:
        return {"status": "not_required", **named}
    if state != "present" or found is None:
        return {"status": state, **named}
    try:
        problem = _binding_problem(root, found)
    except StopError:
        problem = "unprovable"
    return {"status": "valid" if problem is None else "mismatch", **named}


def _pending_summary(root: Path) -> dict[str, Any] | None:
    try:
        pending = pending_mutations(root)
    except (ReconcileRequired, ValidationError, OSError):
        pending = None  # reported as a reconcile need, never read past and never repaired
    if pending is None or len(pending) > 1:
        return {"mutation_id": None, "operation": None, "status": "reconcile_required", "stage": None}
    if not pending:
        return None
    record = pending[0]
    stage = None
    for effect in reversed(record["effects"]):
        if "stage" in effect["payload"]:
            stage = effect["payload"]["stage"]
            break
    return {"mutation_id": record["mutation_id"], "operation": record["operation"], "status": record["status"],
            "stage": stage}


def status_report(workline_root: Path) -> dict[str, Any]:
    """The read-only root maintenance diagnostics (§31.46), consumed by RB1 under ``policy.root_maintenance``.

    No lock, no runtime write, no remote contact, no repair. Exact keys:
    ``status``, ``global_policy`` (``source_mode`` / ``version`` / ``digest`` -
    the exact digest of the current Global policy record), ``current_change_id``
    (the change record whose ``after_global_policy_digest`` is that digest),
    ``evaluation_ids`` (of that change), ``authorization`` (``status`` -
    ``not_required`` / ``absent`` / ``valid`` / ``mismatch`` / ``unreadable`` -
    plus the approved ``remote`` and ``branch``, never the locator),
    ``pending_mutation`` (``mutation_id`` / ``operation`` / ``status`` /
    ``stage``) and ``next_boundary_adapter_identity``. No time, process, host or
    working-directory key at any depth, and the holder description is never
    read.

    Runtime state that cannot be read has its own value in the frozen keys
    (``authorization.status`` ``unreadable``, ``pending_mutation.status``
    ``reconcile_required``). A CANONICAL root record that cannot be read - the
    Global policy, a change or evaluation record that is not stored canonically,
    an indirection on the way to one - is never read past and never guessed
    around: the call raises its ``StopError`` (``review_record_noncanonical``,
    ``review_containment``, the loader's own STOP, ...) and the
    ``status`` key stays the constant ``available`` of the reports it does
    return. The RB1 caller isolates the call (IR-RB7-5:
    ``_isolated(lambda: root_maintenance.status_report(...))``), so the key then
    renders as ``unavailable`` with that code, and no other section is hidden
    (RB7BL-3).
    """
    root = Path(workline_root).resolve()
    baseline = review_policy.load_global_baseline(root)
    digest = _global_policy_digest(baseline)
    changes = _family_records(root, ROOT_POLICY_LAYOUT.changes_dir, "change", "global_policy_change_id")
    current = [identifier for identifier, record in changes if record.get("after_global_policy_digest") == digest]
    current_change_id = current[0] if len(current) == 1 else None
    evaluation_ids: list[str] = []
    if current_change_id is not None:
        evaluations = _family_records(root, ROOT_POLICY_LAYOUT.evaluations_dir, "evaluation", "evaluation_id")
        evaluation_ids = sorted(identifier for identifier, record in evaluations
                                if record.get("global_policy_change_id") == current_change_id)
    return {
        "status": "available",
        "global_policy": {"source_mode": baseline.source_mode, "version": baseline.version, "digest": digest},
        "current_change_id": current_change_id,
        "evaluation_ids": evaluation_ids,
        "authorization": _authorization_status(root),
        "pending_mutation": _pending_summary(root),
        "next_boundary_adapter_identity": (review_policy.COMPATIBILITY_EXACT_DERIVED_SEMANTIC if baseline.version == 1
                                           else review_policy.COMPATIBILITY_TOTAL_ADAPTER_V1),
    }


__all__ = [
    "APPLIED", "AUTHORIZATION_CONTRACT", "AUTHORIZATION_REL", "AUTHORIZATION_SCHEMA", "Authorization",
    "EFFECT_CHANGE_CREATE", "EFFECT_COMMIT", "EFFECT_CONSUMPTION_CREATE", "EFFECT_EVALUATION_CREATE",
    "EFFECT_GLOBAL_POLICY_REPLACE", "EFFECT_PACKET_CREATE", "EFFECT_PATCH_NOTE_CREATE", "EFFECT_PUSH",
    "EFFECT_REVIEW_CREATE", "HOLDER_REL", "LOCK_REL", "MATCHED", "MUTATIONS_DIR", "MUTATION_SCHEMA",
    "MUTATION_VERSION", "OPERATIONS", "OPERATION_AUTHORIZE", "OPERATION_CHANGE", "OPERATION_EFFECTS",
    "OPERATION_EVALUATION", "PublicationBinding", "RECONCILE_REASONS", "RESERVATION_KINDS", "ROOT_EFFECT_KINDS",
    "ROOT_GIT_SCRATCH", "RUNTIME_DIR", "RootLock", "RootMutation", "STAGES", "STATUS_ABANDONED", "STATUS_COMPLETED",
    "STATUS_KEY", "STATUS_PENDING", "STOP_CODES", "TMP_DIR", "TMP_PARTS", "authorize", "enter_git", "open_mutation",
    "pending_for_run", "pending_mutations", "publication_binding", "read_authorization", "reconcile",
    "repository_identity", "require_committable", "require_root_invocation", "require_root_target", "root_operation",
    "status_report", "stop", "tmp_directory",
]
