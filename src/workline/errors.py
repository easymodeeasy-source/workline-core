"""Exception hierarchy for Workline operations.

The hierarchy mirrors the stop contracts of ``rules/git``:

* ``WorklineError``          base class
* ``StopError``              the operation must STOP (no automatic repair)
* ``ReconcileRequired``      a STOP whose cause is a recovery / expectation mismatch
* ``ValidationError``        a payload or structure failed validation (also a STOP)
* ``SpecViolation``          a caller asked for something the live spec forbids
* ``ProjectOperationBusy``   another process holds the Project execution lock
* ``ProjectOperationNested`` a top-level operation started inside a running one
* ``ForeignProjectMutation`` an operation targets a Project other than the one it runs in
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class WorklineError(Exception):
    """Base class for every Workline error."""


class StopError(WorklineError):
    """The current operation must stop without automatic repair."""

    def __init__(self, message: str, *, code: str = "stop") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ReconcileRequired(StopError):
    """Recovery state cannot be resolved automatically (``reconcile required``)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="reconcile_required")


class ValidationError(StopError):
    """Payload or structural validation failed."""

    def __init__(self, message: str, *, code: str = "validation_failed") -> None:
        super().__init__(message, code=code)


class SpecViolation(StopError):
    """The requested action is forbidden by the live specification."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="spec_violation")


class GitError(StopError):
    """A git command failed."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="git_error")


class ProjectOperationBusy(StopError):
    """Another process is executing a Workline operation on the same Project.

    Transient contention, not a recovery conflict: nothing was written, and the
    operation can be run again once the other one has finished. ``holder`` is
    the diagnostic description the holder left, when one could be read.
    """

    def __init__(self, message: str, holder: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="project_operation_busy")
        self.holder = holder


class ProjectOperationNested(StopError):
    """A top-level operation was started inside a running one on the same Project."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="project_operation_nested")


class ForeignProjectMutation(StopError):
    """A state-changing operation targets a Project other than the one it was started in.

    Raised before the Project execution lock is taken, so nothing was written.
    ``context_root`` is the Workline Project or Git repository the operation was
    started from (None when it was inside neither); ``target_root`` is the
    folder it would have changed.
    """

    def __init__(self, message: str, *, context_root: Path | None = None, target_root: Path | None = None) -> None:
        super().__init__(message, code="foreign_project_mutation")
        self.context_root = context_root
        self.target_root = target_root
