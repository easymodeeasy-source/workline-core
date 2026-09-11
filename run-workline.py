"""Canonical runtime entry of this Workline root (registry ``rules/git``: Workline implementation).

Start Workline only through the launcher of the configured Workline root R,
in isolated mode and without bytecode:

    Windows: py -3 -I -B "<R>\\run-workline.py" <command> ...
    POSIX:   python3 -I -B "<R>/run-workline.py" <command> ...

An operation without a CLI command uses the Python API in one isolated process
instead, importing it only after this file's activate() has passed there:

    import runpy

    activate = runpy.run_path(r"<R>/run-workline.py")["activate"]
    activate()

    # only after activation:
    from workline import roadmap as rm, start as st

Nothing is installed: the launcher runs R's working tree, <R>/src/workline. It
requires Python 3.11 or newer and isolated mode, turns bytecode writing off,
and proves by origin verification that every loaded workline module comes from
<R>/src/workline; inside an established Project it also requires that
Project's configured Workline root to be R. Isolated mode keeps PYTHONPATH,
user site-packages and the working directory out of the import path, but
system site-packages and their .pth startup code remain: the proof is the
origin check, not the flag.

It does not search for interpreters, re-execute itself, install packages,
create environments, use the network, change directory or run code other than
Workline. Activation is local to this process: no token, authorization, import
path, environment variable or file is handed to another process. This guards
against the wrong interpreter or implementation; it is not a security sandbox.

This file stays readable by old Python 3 releases, so that an unsupported
interpreter is told so instead of failing on syntax.
"""

import os
import sys

MINIMUM_PYTHON = (3, 11)

_HELPER_MODULE = "_workline_launcher_implementation"
_API_MODULES = ("workline", "workline.errors", "workline.implementation", "workline.store", "workline.context")
_CLI_MODULES = _API_MODULES + ("workline.cli",)


def _stop(code, message):
    line = "STOP [%s]: %s\n" % (code, message)
    stream = sys.stdout
    try:
        stream.write(line)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        stream.write(line.encode(encoding, "replace").decode(encoding))
    stream.flush()
    raise SystemExit(1)


def _invocation(launcher):
    if os.name == "nt":
        return 'py -3 -I -B "%s" <command> ...' % launcher
    return 'python3 -I -B "%s" <command> ...' % launcher


def _same_directory(first, second):
    try:
        return os.path.samefile(first, second)
    except (OSError, ValueError):
        return False


def _require_supported_python(launcher):
    if tuple(sys.version_info[:2]) < MINIMUM_PYTHON:
        _stop(
            "workline_python_unsupported",
            "Workline requires Python %s or newer, but %s runs Python %s; make py -3 (Windows) or python3 (POSIX) "
            "select a supported Python and run %s; nothing was written"
            % (
                ".".join(str(part) for part in MINIMUM_PYTHON),
                sys.executable,
                ".".join(str(part) for part in sys.version_info[:3]),
                _invocation(launcher),
            ),
        )


def _require_isolated_mode(launcher):
    if not getattr(sys.flags, "isolated", 0):
        _stop(
            "workline_invocation_not_isolated",
            "the Workline launcher runs only in isolated mode (-I); run %s; nothing was written" % _invocation(launcher),
        )


def _load_helper(root):
    """This root's implementation checks, loaded from their file before any workline import."""
    import importlib.util

    path = os.path.join(root, "src", "workline", "implementation.py")
    if not os.path.isfile(path):
        _stop(
            "workline_implementation_unavailable",
            "the Workline root %s has no implementation at %s; nothing was written" % (root, os.path.dirname(path)),
        )
    try:
        spec = importlib.util.spec_from_file_location(_HELPER_MODULE, path)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
    except Exception as exc:
        _stop(
            "workline_implementation_unavailable",
            "cannot load %s (%s: %s); nothing was written" % (path, type(exc).__name__, exc),
        )
    return helper


def _require(problem):
    if problem is not None:
        _stop(problem.code, problem.message)


def _require_project_configured_for_this_root():
    """Inside an established Project, only the launcher of its configured Workline root runs."""
    from workline.context import PROJECT, resolve_invocation_context
    from workline.errors import StopError
    from workline.implementation import require_configured_implementation
    from workline.store import ProjectStore

    try:
        context = resolve_invocation_context()
        if context.kind == PROJECT:
            require_configured_implementation(ProjectStore(context.root).workline_root())
    except StopError as exc:
        _stop(exc.code, exc.message)


def _activate(modules):
    launcher = os.path.realpath(os.path.abspath(__file__))
    _require_supported_python(launcher)
    _require_isolated_mode(launcher)
    sys.dont_write_bytecode = True
    root = os.path.dirname(launcher)

    helper = _load_helper(root)
    # Whatever the interpreter loaded at startup must already be this root's.
    # A foreign module is never evicted and re-imported: code it ran cannot be undone.
    _require(helper.loaded_implementation_problem(root, allow_unloaded=True))

    source = os.path.join(root, "src")
    if not os.path.isfile(os.path.join(source, "workline", "__init__.py")):
        _stop(
            "workline_implementation_unavailable",
            "the Workline root %s has no workline package in %s; nothing was written" % (root, source),
        )
    # Searched first, but not a proof by itself: the origin check below decides.
    if not (sys.path and _same_directory(sys.path[0], source)):
        sys.path.insert(0, source)

    import importlib

    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as exc:
            _require(helper.loaded_implementation_problem(root))
            _stop(
                "workline_implementation_unavailable",
                "cannot import %s from %s (%s: %s); nothing was written" % (name, source, type(exc).__name__, exc),
            )
    _require(helper.loaded_implementation_problem(root))
    _require_project_configured_for_this_root()


def activate():
    """Make this Workline root the implementation of the current process, or STOP.

    Call it in an isolated (-I) process before importing any Workline module,
    and import the Workline API only after it returns. It holds for this
    process alone and authorizes nothing: every operation still checks its
    Project context, its implementation and its execution lock.
    """
    _activate(_API_MODULES)


def main(argv=None):
    """Run a Workline CLI command with this Workline root's implementation."""
    _activate(_CLI_MODULES)
    from workline.cli import main as run_cli

    return run_cli(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
