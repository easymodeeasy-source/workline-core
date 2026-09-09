"""Exception hierarchy for Workline operations.

The hierarchy mirrors the stop contracts of ``rules/git``:

* ``WorklineError``      base class
* ``StopError``          the operation must STOP (no automatic repair)
* ``ReconcileRequired``  a STOP whose cause is a recovery / expectation mismatch
* ``ValidationError``    a payload or structure failed validation (also a STOP)
* ``SpecViolation``      a caller asked for something the live spec forbids
"""

from __future__ import annotations


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
