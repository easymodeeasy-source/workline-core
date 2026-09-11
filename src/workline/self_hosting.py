"""Unsupported self-hosting (``rules/git``: Unsupported self-hosting).

Self-hosting — managing a Workline root as a Workline Project of its own — is
unsupported under the current Workline rules. A state-changing operation runs
only when the Project root and its Workline root are proven to be different
directories on disk. The Workline root is ``workline.root`` in an established
Project's ``.workline/project.yaml``, or the Workline root Project開始 is given.

Directories are compared by file identity (``os.path.samefile``), never by the
way they are spelled, so a case difference, other separators, a trailing
separator, ``..``, a relative path, a symlink or junction, or a short name
cannot slip past the check:

* the same directory STOPs as ``workline_self_hosting_unsupported``;
* different directories pass;
* when both exist but their identity cannot be determined, they are not proven
  to be different, and the operation STOPs all the same;
* a Workline root that does not exist cannot be the Project root, so it is left
  to the checks that already report a missing root.

The check comes after the Project context, so a foreign caller is told that
first, and before the Workline implementation check and the Project execution
lock, so a STOP writes nothing. Reading such a Project stays possible, and its
canonical validation reports the topology as a problem instead of passing it.

Nothing here repairs a Project that already has this shape: ``project.yaml``
is not rewritten and ``.workline`` is not removed, and nothing turns the check
off. It is a temporary guard, to be reconsidered if self-hosting is ever
designed and supported.
"""

from __future__ import annotations

import errno
import os

from .errors import SelfHostingUnsupported

CODE = "workline_self_hosting_unsupported"

SAME = "same"
DISTINCT = "distinct"
MISSING = "missing"
UNDETERMINED = "undetermined"

_ERROR_INVALID_NAME = 123  # Windows: a path that cannot name anything


def _absent(path: str | os.PathLike[str]) -> bool:
    """Whether ``path`` certainly names nothing on disk."""
    try:
        os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return True
    except OSError as exc:
        return getattr(exc, "winerror", None) == _ERROR_INVALID_NAME or exc.errno == errno.ENAMETOOLONG
    except ValueError:  # an embedded NUL character cannot name a file
        return True
    return False


def directory_identity(first: str | os.PathLike[str], second: str | os.PathLike[str]) -> str:
    """``same`` | ``distinct`` | ``missing`` | ``undetermined``, decided by file identity."""
    try:
        return SAME if os.path.samefile(first, second) else DISTINCT
    except (OSError, ValueError):
        pass
    if _absent(first) or _absent(second):
        return MISSING
    return UNDETERMINED


def self_hosting_problem(project_root: str | os.PathLike[str], workline_root: str | os.PathLike[str]) -> str | None:
    """Why ``project_root`` may not be changed as a Project of ``workline_root``, or None."""
    identity = directory_identity(project_root, workline_root)
    if identity == SAME:
        return (
            f"the Project root {project_root} is the Workline root {workline_root} itself: self-hosting a "
            "Workline root is unsupported under the current Workline rules, so no state-changing Workline "
            "operation runs on it"
        )
    if identity == UNDETERMINED:
        return (
            f"the Project root {project_root} cannot be proven to be a different directory from the Workline "
            f"root {workline_root}: self-hosting a Workline root is unsupported under the current Workline rules, "
            "so no state-changing Workline operation runs on it"
        )
    return None


def refuse_self_hosting(project_root: str | os.PathLike[str], workline_root: str | os.PathLike[str]) -> None:
    """STOP a state-changing operation unless ``project_root`` is proven apart from ``workline_root``."""
    problem = self_hosting_problem(project_root, workline_root)
    if problem is not None:
        raise SelfHostingUnsupported(f"{problem}; nothing was written")


__all__ = [
    "CODE",
    "DISTINCT",
    "MISSING",
    "SAME",
    "UNDETERMINED",
    "directory_identity",
    "refuse_self_hosting",
    "self_hosting_problem",
]
