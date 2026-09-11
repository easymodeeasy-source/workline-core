"""Workline implementation identity (``rules/git``: Workline implementation).

A Workline operation runs on a supported interpreter and with the
implementation of its configured Workline root ``R`` only: the source package
``<R>/src/workline``. ``R`` is ``workline.root`` in the Project's
``.workline/project.yaml``; for Project開始 it is the Workline root the new
Project is given.

A successful ``import workline`` proves nothing about where the code came from:
an ambient or editable install, ``PYTHONPATH``, the working directory or
another clone can each supply a ``workline`` package. Identity is decided from
the origin of what is actually loaded:

* ``workline`` is a regular source package whose ``__path__`` is exactly its
  own directory;
* every loaded ``workline.*`` module is a ``.py`` source file inside that
  directory;
* that directory is ``<R>/src/workline``, compared as a directory on disk
  (file identity), never as a string.

When no single source directory can be proven — a namespace, frozen or
built-in module, sourceless bytecode, an extension module, or modules loaded
from more than one place — it is ``workline_implementation_unverified``. A
single proven directory that is not ``<R>/src/workline`` is
``workline_implementation_mismatch``.

Two layers use this module:

* the canonical launcher ``<R>/run-workline.py`` loads this file straight from
  its path, before any ``workline`` import, and checks the process before and
  after it loads ``workline`` from ``<R>/src`` (Layer 1);
* inside the implementation, every state-changing operation on an established
  Project, Project開始 and ``validate-project`` check it again against the
  configured root, however ``workline`` was imported (Layer 2).

The launcher runs these checks before any Workline code is trusted, so they
use the standard library only and import nothing from Workline.

This guards against running the wrong interpreter or implementation by
mistake; it is not a security sandbox. Startup code of the selected
interpreter (``.pth`` files, ``sitecustomize``), deliberate changes to
``sys.modules`` or to these checks, and code that a driver or an executor runs
are outside it. It proves that the implementation is the configured root's
working tree — not that it is committed, clean or a release.
"""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import sys

MINIMUM_PYTHON = (3, 11)
PACKAGE = "workline"
LAUNCHER = "run-workline.py"

PYTHON_UNSUPPORTED = "workline_python_unsupported"
INVOCATION_NOT_ISOLATED = "workline_invocation_not_isolated"
IMPLEMENTATION_UNAVAILABLE = "workline_implementation_unavailable"
IMPLEMENTATION_UNVERIFIED = "workline_implementation_unverified"
IMPLEMENTATION_MISMATCH = "workline_implementation_mismatch"


class IdentityProblem:
    """Why this process may not run as the configured Workline implementation."""

    __slots__ = ("code", "message")

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"IdentityProblem({self.code!r}, {self.message!r})"


def package_directory(root: str | os.PathLike[str]) -> Path:
    """``<root>/src/workline``: where a Workline root keeps its implementation."""
    return Path(root) / "src" / PACKAGE


def canonical_invocation(root: str | os.PathLike[str]) -> str:
    """How to start Workline through ``root``'s launcher on this platform."""
    selector = "py -3" if os.name == "nt" else "python3"
    return f'{selector} -I -B "{Path(root) / LAUNCHER}" <command> ...'


def interpreter_description() -> str:
    version = ".".join(str(part) for part in sys.version_info[:3])
    return f"{sys.executable or 'an unknown executable'} (Python {version})"


def python_problem() -> IdentityProblem | None:
    """``workline_python_unsupported`` when this interpreter is older than Workline requires."""
    if tuple(sys.version_info[:2]) >= MINIMUM_PYTHON:
        return None
    required = ".".join(str(part) for part in MINIMUM_PYTHON)
    return IdentityProblem(
        PYTHON_UNSUPPORTED,
        f"Workline requires Python {required} or newer, but this process runs {interpreter_description()}; "
        "nothing was written",
    )


def _same_file(first: str | os.PathLike[str], second: str | os.PathLike[str]) -> bool:
    try:
        return os.path.samefile(first, second)
    except (OSError, ValueError):
        return False


def _source_file(module: object) -> Path | None:
    """The ``.py`` file ``module`` was loaded from, or None when no source origin can be proven."""
    spec = getattr(module, "__spec__", None)
    if spec is not None:
        origin = spec.origin if getattr(spec, "has_location", False) else None
    else:
        origin = getattr(module, "__file__", None)
    if not isinstance(origin, str) or not os.path.normcase(origin).endswith(".py"):
        return None
    if not os.path.isfile(origin):
        return None
    return Path(origin)


def _inside(path: Path, directory: Path) -> bool:
    return any(_same_file(parent, directory) for parent in path.parents)


def _unverified(root: str | os.PathLike[str], reason: str) -> IdentityProblem:
    return IdentityProblem(
        IMPLEMENTATION_UNVERIFIED,
        f"cannot prove that the running Workline implementation is the one of the Workline root {root} "
        f"({package_directory(root)}): {reason}; interpreter {interpreter_description()}. "
        f"Run Workline through {canonical_invocation(root)}; nothing was written",
    )


def _mismatch(root: str | os.PathLike[str], actual: Path) -> IdentityProblem:
    return IdentityProblem(
        IMPLEMENTATION_MISMATCH,
        f"this operation requires the Workline implementation of the Workline root {root} "
        f"({package_directory(root)}), but the loaded implementation is {actual}; "
        f"interpreter {interpreter_description()}. Run Workline through {canonical_invocation(root)}; "
        "nothing was written",
    )


def loaded_implementation_problem(
    root: str | os.PathLike[str],
    *,
    allow_unloaded: bool = False,
    modules: Mapping[str, object] | None = None,
) -> IdentityProblem | None:
    """Whether every loaded ``workline`` / ``workline.*`` module is ``root``'s implementation.

    ``allow_unloaded`` accepts a process that has loaded no Workline module yet
    (the launcher, before it loads one). ``modules`` is ``sys.modules`` unless
    given.
    """
    loaded = sys.modules if modules is None else modules
    names = sorted(name for name in list(loaded) if name == PACKAGE or name.startswith(PACKAGE + "."))
    if not names:
        if allow_unloaded:
            return None
        return _unverified(root, "no Workline implementation is loaded in this process")

    package = loaded.get(PACKAGE)
    init = _source_file(package) if package is not None else None
    if init is None:
        return _unverified(root, f"the loaded {PACKAGE} package has no source file origin")
    if init.name != "__init__.py" or not hasattr(package, "__path__"):
        return _mismatch(root, init)  # a plain module named workline: never a Workline root's package
    directory = init.parent
    locations = list(getattr(package, "__path__"))
    if len(locations) != 1 or not _same_file(locations[0], directory):
        return _unverified(root, f"{PACKAGE}.__path__ is not exactly its package directory {directory}")

    for name in names:
        if name == PACKAGE:
            continue
        source = _source_file(loaded[name])
        if source is None:
            return _unverified(root, f"{name} has no source file origin")
        if not _inside(source, directory):
            return _unverified(root, f"{name} is loaded from {source.parent}, not from {directory}")

    if not _same_file(directory, package_directory(root)):
        return _mismatch(root, directory)
    return None


def configured_implementation_problem(configured_root: str | os.PathLike[str]) -> IdentityProblem | None:
    """Layer 2: this interpreter and the loaded implementation, against the configured Workline root."""
    return python_problem() or loaded_implementation_problem(configured_root)


def require_configured_implementation(configured_root: str | os.PathLike[str]) -> None:
    """STOP unless this process runs the configured Workline root's implementation on a supported Python.

    Layer 2, called from inside the imported package. The launcher loads this
    file on its own before it trusts any Workline code and never calls this.
    """
    problem = configured_implementation_problem(configured_root)
    if problem is not None:
        from .errors import implementation_error

        raise implementation_error(problem)


__all__ = [
    "IMPLEMENTATION_MISMATCH",
    "IMPLEMENTATION_UNAVAILABLE",
    "IMPLEMENTATION_UNVERIFIED",
    "INVOCATION_NOT_ISOLATED",
    "LAUNCHER",
    "MINIMUM_PYTHON",
    "PYTHON_UNSUPPORTED",
    "IdentityProblem",
    "canonical_invocation",
    "configured_implementation_problem",
    "loaded_implementation_problem",
    "package_directory",
    "python_problem",
    "require_configured_implementation",
]
