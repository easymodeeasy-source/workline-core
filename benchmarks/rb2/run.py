"""RB2 benchmark runner: BL-007 cold-start recovery measurement (Completion Sprint tooling and evidence only).

Implements the frozen protocol of ``WORKLINE_COMPLETION_SPRINT.md`` §36 against
the supported RB1 surfaces of one measured Workline root ``R``:

* primary target   ``py -3 -I -B <R>/run-workline.py status <project-root> --json`` (fresh process per sample);
* secondary target ``py -3 -I -B <R>/run-workline.py validate-project <project-root>``;
* warm diagnostic  ``runpy.run_path(<R>/run-workline.py)["activate"]()`` then
  ``workline.status.render_json(workline.status.build_status(<project-root>))`` called repeatedly in one process.

It never edits ``R``: component timing (A-I, §36.12-§36.13) runs the launcher's
own ``main`` in a separate benchmark-only child that wraps the landed function
boundaries at runtime with ``perf_counter_ns`` spans; Git commands are counted
by ``GIT_TRACE2_EVENT`` and by that wrapper (§36.14). Headline numbers are the
uninstrumented cold-process wall times.

What is measured is deterministic local Workline recovery mechanics only - not
LLM reasoning, token generation or model context loading, human reading time,
editor startup or network latency (§36.3). Samples are cold-process, not
cold-disk: the OS file cache is not purged (§36.10).

Usage (from anywhere; ``-B`` keeps bytecode out of the worktree)::

    py -3 -B benchmarks/rb2/run.py series --workline-root <R> --fixtures <dir> --logs <dir> --label SMOKE --scales S
    py -3 -B benchmarks/rb2/run.py render --results <results.json> --out <file.md>

Only ``os``, ``sys`` and ``time`` are imported at module level: the ``_child``
modes run inside measured processes and must not pre-load what Workline imports.
"""

from __future__ import annotations

import os
import sys
import time

HARNESS_CONTRACT = "workline-rb2-harness"
HARNESS_VERSION = 1
LAUNCHER_NAME = "run-workline.py"

#: The exact RB1 bindings (§36.1): the read-only status command and its JSON flag, the validation command,
#: and the public status API the warm protocol calls after canonical launcher activation.
STATUS_COMMAND = "status"
STATUS_JSON_FLAG = "--json"
VALIDATE_COMMAND = "validate-project"
STATUS_SCHEMA = "workline-status"
STATUS_VERSION = 1
STATUS_API = ("workline.status", "build_status", "render_json")
VALIDATE_PASS_LINE = "project validation: PASS"
OPERATIONS = ("status", "validate")

STAGES = ("A", "B", "C", "D", "E", "F", "G", "H", "I")
STAGE_NAMES = {
    "A": "bootstrap/root resolution",
    "B": "implementation identity verification",
    "C": "registry parse/validation",
    "D": "router/Skill authority inventory",
    "E": "canonical Project load",
    "F": "validate-project",
    "G": "RB1 status derivation",
    "H": "local Git diagnostics (all Git subprocesses)",
    "I": "final JSON/render serialization and CLI output",
}

#: Launcher-level boundaries (``run-workline.py`` globals) -> stage.
LAUNCHER_SPANS = (
    ("_require_supported_python", "A"),
    ("_require_isolated_mode", "A"),
    ("_load_helper", "A"),
    ("_activate", "A"),
    ("_binds_invocation_project", "A"),
    ("_require_project_configured_for_this_root", "A"),
)
#: Landed Workline function boundaries -> stage. Every module attribute holding the same function object is
#: wrapped, so a name imported into another module (``from .validate import validate_project``) is covered too.
WORKLINE_SPANS = (
    ("workline.implementation", "loaded_implementation_problem", "B"),
    ("workline.implementation", "running_workline_root", "B"),
    ("workline.implementation", "configured_implementation_problem", "B"),
    ("workline.implementation", "require_configured_implementation", "B"),
    ("workline.context", "resolve_invocation_context", "A"),
    ("workline.registry", "validate_registry", "C"),
    ("workline.registry", "authority_inventory", "D"),
    ("workline.state", "ProjectView.load", "E"),
    ("workline.validate", "validate_project", "F"),
    ("workline.validate", "validate_project_yaml", "F"),
    ("workline.validate", "validate_structure", "F"),
    ("workline.review.validate", "validate_review", "F"),
    ("workline.self_hosting", "self_hosting_problem", "F"),
    ("workline.status", "build_status", "G"),
    ("workline.status", "read_witnesses", "G"),
    ("workline.status", "_project", "A"),
    ("workline.status", "_authority", "D"),
    ("workline.status", "_git_section", "H"),
    ("workline.status", "_pending", "G"),
    ("workline.status", "_lifecycle", "G"),
    ("workline.status", "_validation", "F"),
    ("workline.status", "_review", "G"),
    ("workline.status", "_assemble", "I"),
    ("workline.status", "render_json", "I"),
    ("workline.mutation", "inspect_records", "G"),
    ("workline.cli", "main", "I"),
    ("workline.gitcmd", "run_git", "H"),
    ("workline.gitcmd", "run_git_bytes", "H"),
)
GIT_BOUNDARIES = ("workline.gitcmd.run_git", "workline.gitcmd.run_git_bytes")
#: Fine-grained derivation spans (``--derivation-samples``): per-call overhead is larger, so they never
#: feed the headline and are reported as their own variant.
DERIVATION_SPANS = (
    ("workline.state", "ProjectView.events_for", "G"),
    ("workline.state", "ProjectView.relations_to", "G"),
    ("workline.state", "ProjectView.relations_from", "G"),
    ("workline.state", "ProjectView.phase_works", "G"),
)
#: What each derivation span repeats, and why one pass per command could replace the repeats (Trigger A rows).
DERIVATION_SCANS = {
    "state.ProjectView.events_for": "per-entity full Event-log scans (ProjectView.events_for) behind state derivation",
    "state.ProjectView.relations_to": "per-entity full roadmap-relation scans (ProjectView.relations_to)",
    "state.ProjectView.relations_from": "per-entity full roadmap-relation scans (ProjectView.relations_from)",
    "state.ProjectView.phase_works": "per-Phase full Work scans (ProjectView.phase_works)",
}

#: Git families that contact a remote: the harness never accepts one in a measured invocation (§36.14, §36.32).
NETWORK_GIT = frozenset({
    "fetch", "pull", "push", "ls-remote", "clone", "fetch-pack", "send-pack", "upload-pack", "receive-pack",
    "remote update", "remote prune", "remote show", "remote set-head", "archive --remote", "submodule",
})
#: Local read families a status / validate-project invocation is expected to run.
LOCAL_READ_GIT = frozenset({
    "rev-parse", "symbolic-ref", "status", "diff", "ls-files", "ls-tree", "cat-file", "check-ignore", "log",
    "show", "rev-list", "merge-base", "for-each-ref", "version", "var", "config", "remote", "remote get-url",
    "check-attr", "show-ref", "diff-tree", "diff-index", "diff-files", "name-rev", "describe",
})
FAMILY_TABLE = ("rev-parse", "symbolic-ref", "status", "diff", "ls-files", "ls-tree", "remote/config", "other")
_GIT_VALUE_OPTIONS = ("-c", "-C", "--git-dir", "--work-tree", "--namespace", "--config-env", "--exec-path")

_PC = time.perf_counter_ns


# =========================================================================== shared helpers (no heavy imports)


def git_family(args: "list[str] | tuple[str, ...]") -> str:
    """The family of a git argument list (``git`` itself and ``-C <repo>`` excluded): its subcommand.

    ``remote`` keeps its own subcommand (``remote get-url`` is a local config
    read, ``remote show`` contacts the remote). Global options are skipped.
    """
    items = [str(item) for item in args]
    index = 0
    while index < len(items):
        token = items[index]
        if token in _GIT_VALUE_OPTIONS:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    if index >= len(items):
        return "<none>"
    sub = items[index]
    if sub == "remote":
        following = [item for item in items[index + 1:] if not item.startswith("-")]
        if following:
            return f"remote {following[0]}"
    if sub == "archive" and "--remote" in items[index + 1:]:
        return "archive --remote"
    return sub


def table_family(family: str) -> str:
    """The §36.14 reporting family of ``family``."""
    if family in FAMILY_TABLE:
        return family
    if family == "config" or family == "remote" or family.startswith("remote "):
        return "remote/config"
    return "other"


def check_git_families(families: "dict[str, int] | list[str]") -> dict[str, list[str]]:
    """``network``: families the harness refuses; ``unclassified``: families outside the local-read allowlist."""
    names = sorted(set(families))
    return {
        "network": [name for name in names if name in NETWORK_GIT or name.split(" ")[0] in NETWORK_GIT],
        "unclassified": [name for name in names if name not in LOCAL_READ_GIT and name not in NETWORK_GIT
                         and name.split(" ")[0] not in NETWORK_GIT],
    }


# =========================================================================== child modes (inside measured processes)


class _Tracer:
    """Inclusive / exclusive ``perf_counter_ns`` spans over wrapped boundaries; nesting deduplicated."""

    def __init__(self) -> None:
        self.stack: list[list] = []
        self.spans: dict[str, list] = {}  # label -> [stage, count, inclusive_ns, exclusive_ns]
        self.git: list[list] = []  # [family, ns, parent_label, hermetic, argv_digest]
        self.events: dict[str, int] = {}

    def wrap(self, func, label: str, stage: str, *, git: bool = False):
        tracer = self

        def wrapped(*args, **kwargs):
            frame = [label, _PC(), 0]
            tracer.stack.append(frame)
            try:
                return func(*args, **kwargs)
            finally:
                end = _PC()
                tracer.stack.pop()
                inclusive = end - frame[1]
                if tracer.stack:
                    tracer.stack[-1][2] += inclusive
                entry = tracer.spans.get(label)
                if entry is None:
                    entry = tracer.spans[label] = [stage, 0, 0, 0]
                entry[1] += 1
                entry[2] += inclusive
                entry[3] += inclusive - frame[2]
                if git:
                    git_args = [str(item) for item in args[1:]]
                    parent = tracer.stack[-1][0] if tracer.stack else "<top>"
                    tracer.git.append([git_family(git_args), inclusive, parent, kwargs.get("env") is not None,
                                       "\x1f".join(git_args)])

        wrapped.__name__ = getattr(func, "__name__", label)
        wrapped.__qualname__ = getattr(func, "__qualname__", label)
        wrapped.__doc__ = getattr(func, "__doc__", None)
        wrapped.__wrapped__ = func
        return wrapped


def _patch_workline(tracer: _Tracer, spans, done: set) -> None:
    """Wrap each landed boundary once, in every loaded workline module that holds it."""
    for module_name, dotted, stage in spans:
        key = f"{module_name}.{dotted}"
        if key in done:
            continue
        module = sys.modules.get(module_name)
        if module is None:
            continue
        label = key.replace("workline.", "", 1)
        git = key in GIT_BOUNDARIES
        if "." in dotted:
            class_name, attribute = dotted.split(".", 1)
            owner = getattr(module, class_name)
            raw = owner.__dict__[attribute]
            if isinstance(raw, classmethod):
                setattr(owner, attribute, classmethod(tracer.wrap(raw.__func__, label, stage)))
            else:
                setattr(owner, attribute, tracer.wrap(raw, label, stage))
            done.add(key)
            continue
        original = getattr(module, dotted)
        wrapped = tracer.wrap(original, label, stage, git=git)
        for name, loaded in list(sys.modules.items()):
            if loaded is None or not (name == "workline" or name.startswith("workline.")):
                continue
            for attribute, value in list(vars(loaded).items()):
                if value is original:
                    setattr(loaded, attribute, wrapped)
        done.add(key)


def _child_component(launcher: str, out_path: str, argv: list[str], derivation: bool) -> int:
    start = _PC()
    tracer = _Tracer()

    def audit(event, args):
        if event == "subprocess.Popen":
            tracer.events["subprocess"] = tracer.events.get("subprocess", 0) + 1
            name = os.path.basename(str(args[0] or (args[1][0] if args[1] else ""))).lower()
            if not name.startswith("git"):
                tracer.events["non_git_subprocess"] = tracer.events.get("non_git_subprocess", 0) + 1
        elif event.startswith("socket."):
            tracer.events[event] = tracer.events.get(event, 0) + 1

    sys.addaudithook(audit)
    import runpy

    loaded = runpy.run_path(launcher, run_name="__workline_rb2_launcher__")
    launcher_globals = loaded["main"].__globals__
    harness_ns = _PC() - start
    done: set = set()
    spans = WORKLINE_SPANS + (DERIVATION_SPANS if derivation else ())

    # wrapping the landed boundaries is harness work: its own span, outside A-I
    install = tracer.wrap(lambda: _patch_workline(tracer, spans, done), "harness.install_spans", "harness")

    for name, stage in LAUNCHER_SPANS:
        original = launcher_globals[name]
        if name == "_load_helper":
            def load_helper(root, _original=original):
                helper = _original(root)
                helper.loaded_implementation_problem = tracer.wrap(
                    helper.loaded_implementation_problem, "launcher.loaded_implementation_problem", "B"
                )
                return helper

            launcher_globals[name] = tracer.wrap(load_helper, "launcher._load_helper", stage)
        elif name == "_activate":
            def activate(modules, argv=None, _original=original):
                import importlib

                real_import = importlib.import_module
                importlib.import_module = tracer.wrap(real_import, "launcher.import_workline", "A")
                try:
                    return _original(modules, argv)
                finally:
                    importlib.import_module = real_import
                    install()

            launcher_globals[name] = tracer.wrap(activate, "launcher._activate", stage)
        elif name == "_require_project_configured_for_this_root":
            def configured(_original=original):
                install()
                return _original()

            launcher_globals[name] = tracer.wrap(configured, f"launcher.{name}", stage)
        else:
            launcher_globals[name] = tracer.wrap(original, f"launcher.{name}", stage)

    code = launcher_globals["main"](argv)
    sys.stdout.flush()
    total_ns = _PC() - start

    import json

    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump({
            "mode": "component",
            "exit": code,
            "in_process_ns": total_ns,
            "harness_ns": harness_ns,
            "spans": tracer.spans,
            "git": tracer.git,
            "events": tracer.events,
            "derivation_spans": derivation,
            "python": sys.version.split()[0],
        }, handle)
    return int(code or 0)


def _child_warm(launcher: str, out_path: str, project: str, calls: int) -> int:
    start = _PC()
    import runpy

    activate = runpy.run_path(launcher, run_name="__workline_rb2_launcher__")["activate"]
    activate()
    activated = _PC()
    import importlib
    from pathlib import Path

    status = importlib.import_module(STATUS_API[0])
    build, render = getattr(status, STATUS_API[1]), getattr(status, STATUS_API[2])
    imported = _PC()
    root = Path(project)
    samples: list[int] = []
    texts: list[str] = []
    for _ in range(calls):
        began = _PC()
        text = render(build(root))
        samples.append(_PC() - began)
        texts.append(text)

    import hashlib
    import json

    digests = sorted({hashlib.sha256(text.encode("utf-8")).hexdigest() for text in texts})
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump({
            "mode": "warm",
            "activation_ns": activated - start,
            "api_import_ns": imported - activated,
            "calls_ns": samples,
            "digests": digests,
            "python": sys.version.split()[0],
        }, handle)
    return 0


def _child_router(launcher: str, out_path: str) -> int:
    """Bootstrap steps 3-6 by the canonical implementation: router resolution and the router's inventory read.

    The Project-side bootstrap Skill resolves ``skills/project-router`` from the
    configured root's validated registry and reads that canonical ``SKILL.md``;
    the router then reads the registered Skill inventory at call time. Only the
    local resolution and file reads are measured - never model interpretation.
    """
    start = _PC()
    import runpy

    runpy.run_path(launcher, run_name="__workline_rb2_launcher__")["activate"]()
    activated = _PC()
    from pathlib import Path

    from workline import registry

    root = Path(os.path.dirname(os.path.abspath(launcher)))
    entry = registry.resolve_skill(root, registry.PROJECT_ROUTER_SKILL_ID)
    router_bytes = entry.path.read_bytes()
    resolved = _PC()
    candidates = registry.router_candidates(root)
    skill_bytes = sum(len(candidate.path.read_bytes()) for candidate in candidates.values())
    inventoried = _PC()

    import json

    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump({
            "mode": "router",
            "activation_ns": activated - start,
            "router_resolution_ns": resolved - activated,
            "router_inventory_ns": inventoried - resolved,
            "router_bytes": len(router_bytes),
            "candidates": len(candidates),
            "candidate_skill_bytes": skill_bytes,
        }, handle)
    return 0


def _portable_file(filename: str, root: str) -> str:
    if filename == "~":
        return "<built-in>"
    normalized = os.path.normcase(os.path.abspath(filename)) if filename and not filename.startswith("<") else filename
    source = os.path.normcase(os.path.join(root, "src")) + os.sep
    stdlib = os.path.normcase(os.path.dirname(os.__file__)) + os.sep
    if normalized.startswith(source):
        return "src/" + normalized[len(source):].replace(os.sep, "/")
    if normalized.startswith(stdlib):
        return "<stdlib>/" + normalized[len(stdlib):].replace(os.sep, "/")
    if normalized.startswith("<"):
        return normalized
    return "<other>/" + os.path.basename(normalized)


def _child_profile(launcher: str, out_path: str, argv: list[str]) -> int:
    import cProfile
    import runpy

    loaded = runpy.run_path(launcher, run_name="__workline_rb2_launcher__")
    root = os.path.dirname(os.path.abspath(launcher))
    profile = cProfile.Profile()
    began = _PC()
    profile.enable()
    code = loaded["main"](argv)
    profile.disable()
    sys.stdout.flush()
    elapsed = _PC() - began

    import json
    import pstats

    stats = pstats.Stats(profile).stats
    total_tt = sum(value[2] for value in stats.values())
    rows = []
    for (filename, line, function), (cc, nc, tt, ct, _callers) in stats.items():
        rows.append([_portable_file(filename, root), line, function, nc, tt, ct])
    rows.sort(key=lambda row: -row[5])
    by_cum = rows[:60]
    by_tot = sorted(rows, key=lambda row: -row[4])[:60]
    workline = [row for row in rows if row[0].startswith("src/workline/")
                and (row[5] >= 0.001 * total_tt or row[0] in ("src/workline/state.py", "src/workline/validate.py"))]
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump({
            "mode": "profile",
            "exit": code,
            "profiled_ns": elapsed,
            "total_tottime_s": total_tt,
            "top_cumulative": by_cum,
            "top_tottime": by_tot,
            "workline": workline,
        }, handle)
    return int(code or 0)


def _child_main(argv: list[str]) -> int:
    mode, launcher, out_path = argv[0], argv[1], argv[2]
    rest = argv[3:]
    if mode == "component":
        derivation = rest[0] == "derivation"
        return _child_component(launcher, out_path, rest[2:], derivation)
    if mode == "warm":
        return _child_warm(launcher, out_path, rest[0], int(rest[1]))
    if mode == "profile":
        return _child_profile(launcher, out_path, rest[1:])
    if mode == "router":
        return _child_router(launcher, out_path)
    raise SystemExit(f"unknown child mode {mode}")


# =========================================================================== parent side

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "_child":
    raise SystemExit(_child_main(sys.argv[2:]))

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import platform  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import statistics  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

HERE = Path(__file__).resolve().parent


class HarnessStop(Exception):
    """A frozen §36.32 stop condition, or an admission refusal: nothing is claimed."""


def load_generator():
    import importlib.util

    spec = importlib.util.spec_from_file_location("workline_rb2_generate", HERE / "generate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("workline_rb2_generate", module)
    spec.loader.exec_module(module)
    return module


def python_command(override: "list[str] | None" = None) -> list[str]:
    """The supported interpreter selection of ``run-workline.py`` (``py -3`` on Windows, ``python3`` on POSIX)."""
    if override:
        return list(override)
    if os.name == "nt":
        return ["py", "-3"]
    return ["python3"]


def launcher_command(python: list[str], workline_root: Path, *args: str) -> list[str]:
    """The canonical launcher invocation: isolated, no bytecode, the configured root's ``run-workline.py``."""
    return [*python, "-I", "-B", str(Path(workline_root) / LAUNCHER_NAME), *args]


def status_command(python: list[str], workline_root: Path, project: Path) -> list[str]:
    return launcher_command(python, workline_root, STATUS_COMMAND, str(project), STATUS_JSON_FLAG)


def validate_command(python: list[str], workline_root: Path, project: Path) -> list[str]:
    return launcher_command(python, workline_root, VALIDATE_COMMAND, str(project))


def operation_command(operation: str, python: list[str], workline_root: Path, project: Path) -> list[str]:
    if operation == "status":
        return status_command(python, workline_root, project)
    if operation == "validate":
        return validate_command(python, workline_root, project)
    raise ValueError(operation)


def child_command(python: list[str], *args: str) -> list[str]:
    return [*python, "-I", "-B", str(HERE / "run.py"), "_child", *args]


def portable_python(python: list[str]) -> list[str]:
    """An interpreter given by absolute path is shown as ``<python>``: its location is machine-specific."""
    return ["<python>" if os.path.isabs(part) and Path(part).name.lower().startswith("python") else part
            for part in python]


def portable(command: list[str], workline_root: Path, project: Path | None = None) -> str:
    text = " ".join(f'"{part}"' if " " in part else part for part in portable_python(command))
    for value, placeholder in ((str(project) if project else None, "<project-root>"), (str(workline_root), "<workline-root>"),
                               (str(HERE), "<workline-root>/benchmarks/rb2")):
        if value:
            text = text.replace(value, placeholder)
    return text.replace("\\", "/")


def run_timed(command: list[str], cwd: Path, env: dict[str, str] | None = None, timeout: int = 3600) -> dict[str, Any]:
    """One fresh process: wall ns around creation, run, exit and pipe drain; exit status and exact output kept."""
    began = _PC()
    completed = subprocess.run(command, cwd=str(cwd), capture_output=True, env=env, timeout=timeout,
                               stdin=subprocess.DEVNULL)
    wall = _PC() - began
    return {"wall_ns": wall, "exit": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_read(project: Path, *args: str) -> str:
    completed = subprocess.run(["git", "--no-optional-locks", "-C", str(project), *args], capture_output=True)
    if completed.returncode != 0:
        raise HarnessStop(f"git {args[0]} failed on the fixture: {completed.stderr.decode('utf-8', 'replace').strip()}")
    return completed.stdout.decode("utf-8", "replace")


def _tree_digest(directory: Path, *, exclude_git: bool) -> str:
    entries = []
    for current, directories, files in os.walk(directory):
        base = Path(current)
        if exclude_git and base == directory and ".git" in directories:
            directories.remove(".git")
        directories.sort()
        for name in sorted(files):
            path = base / name
            relative = path.relative_to(directory).as_posix()
            entries.append([relative, _sha(path.read_bytes())])
        for name in directories:
            entries.append([(base / name).relative_to(directory).as_posix() + "/", "dir"])
    return _sha(json.dumps(sorted(entries), separators=(",", ":")).encode("utf-8"))


def fixture_identity(project: Path) -> dict[str, str]:
    """Canonical + runtime fixture bytes (``.git`` excluded), the whole ``.git``, HEAD/tree and porcelain status."""
    identity = {
        "worktree_digest": _tree_digest(project, exclude_git=True),
        "git_dir_digest": _tree_digest(project / ".git", exclude_git=False),
    }
    head_tree = _git_read(project, "rev-parse", "HEAD", "HEAD^{tree}").split()
    identity["head"], identity["tree"] = head_tree[0], head_tree[1]
    identity["porcelain_digest"] = _sha(_git_read(project, "status", "--porcelain=v1", "-z", "--untracked-files=all")
                                        .encode("utf-8"))
    return identity


def require_unchanged(before: dict[str, str], after: dict[str, str], where: str) -> None:
    differing = sorted(key for key in before if before[key] != after.get(key))
    if differing:
        raise HarnessStop(f"measurement mutated the fixture during {where}: {', '.join(differing)} changed")


# --------------------------------------------------------------------------- environment / quiet window


def _run_text(command: list[str], cwd: Path | None = None) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, cwd=str(cwd) if cwd else None, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unavailable ({type(exc).__name__})"
    return completed.stdout.decode("utf-8", "replace").strip()


def harness_identity(workline_root: Path, measured_sha: str) -> dict[str, Any]:
    """The harness commit, the measured Workline commit, and proof the runtime surfaces equal the measured one."""
    head = _run_text(["git", "-C", str(workline_root), "rev-parse", "HEAD"])
    runtime_paths = ["src", LAUNCHER_NAME, "registry.md", ".claude"]
    diff = subprocess.run(["git", "-C", str(workline_root), "diff", "--quiet", measured_sha, "HEAD", "--", *runtime_paths])
    dirty_runtime = _run_text(["git", "-C", str(workline_root), "status", "--porcelain", "--untracked-files=all", "--",
                               *runtime_paths])
    dirty_harness = _run_text(["git", "-C", str(workline_root), "status", "--porcelain", "--untracked-files=all", "--",
                               "benchmarks", "tests/test_rb2_benchmark.py"])
    pycache = sum(1 for _ in (workline_root / "src").rglob("*.pyc"))
    return {
        "harness_sha": head,
        "measured_workline_sha": measured_sha,
        "runtime_identical_to_measured": diff.returncode == 0 and not dirty_runtime,
        "runtime_dirty_entries": len(dirty_runtime.splitlines()) if dirty_runtime else 0,
        "harness_dirty_entries": len(dirty_harness.splitlines()) if dirty_harness else 0,
        "pyc_files_under_src": pycache,
    }


def environment_record(python: list[str], neutral_dir: Path) -> dict[str, Any]:
    probe = ("import sys, platform, json; print(json.dumps({'version': sys.version.split()[0], "
             "'implementation': platform.python_implementation(), 'bits': platform.architecture()[0]}))")
    try:
        interpreter = json.loads(_run_text([*python, "-I", "-c", probe]))
    except json.JSONDecodeError:
        interpreter = {"version": "unavailable"}
    git_config = {}
    for key in ("core.autocrlf", "core.fsmonitor", "core.untrackedCache", "core.preloadIndex", "feature.manyFiles"):
        # system + global values as a measured invocation inherits them (values only, never their file paths)
        value = _run_text(["git", "config", "--get", key], cwd=neutral_dir)
        git_config[key] = value or "unset"
    return {
        "python": interpreter,
        "python_command": " ".join(portable_python(python)),
        "git_version": _run_text(["git", "--version"]),
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unavailable",
        "logical_cpus": os.cpu_count(),
        "git_global_config": git_config,
        "page_cache": "not purged (cold-process, not cold-disk)",
    }


_QUIET_PS = (
    "$s=@(); for($i=0;$i -lt SAMPLES;$i++){"
    "$p=Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter \"Name='_Total'\";"
    "$d=Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk -Filter \"Name='_Total'\";"
    "$s+=[pscustomobject]@{cpu=[int]$p.PercentProcessorTime;disk_idle=[int]$d.PercentIdleTime;"
    "disk_queue=[int]$d.CurrentDiskQueueLength}; if($i -lt SAMPLES-1){Start-Sleep -Milliseconds 1000}};"
    "$t=(Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match 'pytest' }"
    " | Measure-Object).Count;"
    "[pscustomobject]@{samples=$s;pytest_processes=$t} | ConvertTo-Json -Compress -Depth 4"
)


def quiet_sample(samples: int = 5, suites_dir: Path | None = None) -> dict[str, Any]:
    """CPU / disk utilisation samples and the count of running pytest processes (counts only, no command lines)."""
    found: dict[str, Any] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    if os.name == "nt":
        text = _run_text(["powershell", "-NoProfile", "-Command", _QUIET_PS.replace("SAMPLES", str(samples))])
        try:
            data = json.loads(text)
            rows = data["samples"] if isinstance(data["samples"], list) else [data["samples"]]
            found["cpu_percent"] = [row["cpu"] for row in rows]
            found["disk_idle_percent"] = [row["disk_idle"] for row in rows]
            found["disk_queue"] = [row["disk_queue"] for row in rows]
            found["pytest_processes"] = int(data["pytest_processes"])
        except (json.JSONDecodeError, KeyError, TypeError):
            found["unavailable"] = "performance counters unreadable"
    else:
        try:
            found["loadavg"] = list(os.getloadavg())
        except OSError:
            found["unavailable"] = "loadavg unreadable"
    if suites_dir is not None and suites_dir.is_dir():
        active = 0
        for heartbeat in suites_dir.glob("*/HEARTBEAT"):
            if (heartbeat.parent / "SUMMARY.txt").exists():
                continue
            if time.time() - heartbeat.stat().st_mtime < 120:
                active += 1
        found["active_suites"] = active
    return found


def quiet_problem(sample: dict[str, Any]) -> str | None:
    if sample.get("pytest_processes"):
        return f"{sample['pytest_processes']} pytest process(es) running"
    if sample.get("active_suites"):
        return f"{sample['active_suites']} sharded suite(s) with a live heartbeat"
    return None


# --------------------------------------------------------------------------- fixtures and admission


def load_manifest(fixture: Path) -> dict[str, Any]:
    return json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))


def ensure_fixture(fixtures: Path, scale: str, workline_root: Path, seed: int) -> Path:
    generator = load_generator()
    fixture = fixtures / f"{scale}-seed{seed}-v{generator.GENERATOR_VERSION}"
    if (fixture / "manifest.json").is_file():
        manifest = load_manifest(fixture)
        if (manifest["generator_contract"], manifest["generator_version"], manifest["seed"], manifest["scale"]) != (
            generator.GENERATOR_CONTRACT, generator.GENERATOR_VERSION, seed, scale
        ):
            raise HarnessStop(f"fixture {fixture.name} was made by another generator contract/seed/scale")
        return fixture
    generator.generate(fixture, scale, workline_root, seed, allowed_base=fixtures)
    return fixture


def configured_root_of(project: Path) -> Path:
    """The ``workline.root`` the fixture's project.yaml names (a plain read; the launcher re-checks it)."""
    for line in (project / ".workline" / "project.yaml").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("root:"):
            value = stripped[len("root:"):].strip()
            if value.startswith(("'", '"')):
                value = json.loads(value) if value.startswith('"') else value.strip("'")
            return Path(value)
    raise HarnessStop("the fixture project.yaml names no workline.root")


def admit(fixture: Path, workline_root: Path, python: list[str]) -> dict[str, Any]:
    """§36.9 steps 3-4: identity recorded, the landed validate-project PASSes, status reads stably. Untimed."""
    manifest = load_manifest(fixture)
    project = (fixture / "project").resolve()
    configured = configured_root_of(project)
    try:
        same_root = os.path.samefile(configured, workline_root)
    except OSError:
        same_root = False
    if not same_root:
        raise HarnessStop(f"fixture {fixture.name} is configured for another Workline root than the measured one")
    identity = fixture_identity(project)
    if identity["head"] != manifest["git"]["head"] or identity["tree"] != manifest["git"]["tree"]:
        raise HarnessStop(f"fixture {fixture.name} HEAD/tree differs from its manifest")
    validated = run_timed(validate_command(python, workline_root, project), project)
    text = validated["stdout"].decode("utf-8", "replace").strip()
    if validated["exit"] != 0 or text != VALIDATE_PASS_LINE:
        raise HarnessStop(f"fixture {fixture.name} fails validate-project (exit {validated['exit']}): {text[:400]}")
    status = run_timed(status_command(python, workline_root, project), project)
    if status["exit"] != 0:
        raise HarnessStop(f"status exited {status['exit']} on fixture {fixture.name}")
    try:
        model = json.loads(status["stdout"].decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HarnessStop(f"status --json did not print the versioned JSON model: {exc}") from exc
    if (model.get("schema"), model.get("version")) != (STATUS_SCHEMA, STATUS_VERSION):
        raise HarnessStop(f"the status surface is not {STATUS_SCHEMA} v{STATUS_VERSION}: binding cannot be identified")
    if model["snapshot_consistency"] != "stable_read":
        raise HarnessStop(f"status did not read fixture {fixture.name} stably")
    if model["validation"]["status"] != "pass":
        raise HarnessStop(f"status reports validation {model['validation']['status']} on fixture {fixture.name}")
    lifecycle = model["lifecycle"]
    pending = model["pending"]["records"]
    runs = model["review"]["runs"]["entries"]
    return {
        "fixture": fixture.name,
        "identity": identity,
        "validate_stdout": text,
        "status_stdout_sha256": _sha(status["stdout"]),
        "status_lf_sha256": _sha(status["stdout"].replace(b"\r\n", b"\n")),
        "status_bytes": len(status["stdout"]),
        "untimed_wall_ms": {"validate": validated["wall_ns"] / 1e6, "status": status["wall_ns"] / 1e6},
        "facts": {
            "snapshot_consistency": model["snapshot_consistency"],
            "validation": model["validation"]["status"],
            "implementation": model["authority"]["implementation"]["status"],
            "registry": model["authority"]["registry"]["status"],
            "current_ids_present": {name: lifecycle["current"][name]["id"] is not None for name in ("roadmap", "phase", "work")},
            "next_ids_present": {name: lifecycle["next"][name]["id"] is not None for name in ("phase", "work")},
            "current_work_is_fixture_in_flight_work": lifecycle["current"]["work"]["id"] == manifest["current_work_id"],
            "blockers": [blocker["code"] for blocker in lifecycle["blockers"]],
            "pending": [{"owner": r["owner"], "classification": r["classification"], "reason": r["reason"]["code"],
                         "affects_progression": r["affects_progression"]} for r in pending],
            "review_runs": [{"review_kind": r["review_kind"], "state": r["state"], "receipt": r["receipt"]["status"],
                             "obligations": r["blocking_obligations"]["status"]} for r in runs],
            "review_activation": model["review"]["activation"]["status"],
            "dirty_entries": len(model["git"]["dirty"]["entries"]),
            "remote_publication_state": model["git"]["push_destination"]["remote_publication_state"],
        },
    }


# --------------------------------------------------------------------------- protocol batches


def cold_series(plan: list[tuple[str, Path]], workline_root: Path, python: list[str], reps: int,
                references: dict[str, dict[str, Any]], log) -> dict[str, dict[str, list[int]]]:
    """§36.10: fresh processes, scales round-robin with a rotating start, status and validate alternating first."""
    samples: dict[str, dict[str, list[int]]] = {scale: {"status": [], "validate": []} for scale, _ in plan}
    order: list[tuple[str, str]] = []
    for rep in range(reps):
        rotation = plan[rep % len(plan):] + plan[:rep % len(plan)]
        operations = OPERATIONS if rep % 2 == 0 else tuple(reversed(OPERATIONS))
        for scale, project in rotation:
            for operation in operations:
                result = run_timed(operation_command(operation, python, workline_root, project), project)
                reference = references[scale]
                if result["exit"] != 0:
                    raise HarnessStop(f"cold {operation} on {scale} exited {result['exit']}")
                if operation == "status" and _sha(result["stdout"]) != reference["status_stdout_sha256"]:
                    raise HarnessStop(f"cold status output on {scale} differs from the admitted reference")
                if operation == "validate" and result["stdout"].decode("utf-8", "replace").strip() != VALIDATE_PASS_LINE:
                    raise HarnessStop(f"cold validate-project on {scale} did not PASS")
                samples[scale][operation].append(result["wall_ns"])
                order.append((scale, operation))
        log(f"cold rep {rep + 1}/{reps} done")
    return samples


def warm_series(scale: str, project: Path, workline_root: Path, python: list[str], calls: int, run_dir: Path,
                reference: dict[str, Any]) -> dict[str, Any]:
    out = run_dir / f"warm-{scale}.json"
    result = run_timed(child_command(python, "warm", str(workline_root / LAUNCHER_NAME), str(out), str(project),
                                     str(calls)), project, timeout=6 * 3600)
    if result["exit"] != 0:
        raise HarnessStop(f"warm child on {scale} exited {result['exit']}: {result['stderr'][-400:]!r}")
    data = json.loads(out.read_text(encoding="utf-8"))
    data["wall_ns"] = result["wall_ns"]
    data["matches_cold_reference"] = data["digests"] == [reference["status_lf_sha256"]]
    if not data["matches_cold_reference"]:
        raise HarnessStop(f"warm status JSON on {scale} differs from the cold CLI JSON")
    out.unlink()
    return data


def component_run(scale: str, operation: str, project: Path, workline_root: Path, python: list[str], run_dir: Path,
                  reference: dict[str, Any], index: int, derivation: bool = False) -> dict[str, Any]:
    out = run_dir / f"component-{scale}-{operation}-{index}{'-derivation' if derivation else ''}.json"
    args = [STATUS_COMMAND, str(project), STATUS_JSON_FLAG] if operation == "status" else [VALIDATE_COMMAND, str(project)]
    command = child_command(python, "component", str(workline_root / LAUNCHER_NAME), str(out),
                            "derivation" if derivation else "plain", "--", *args)
    result = run_timed(command, project)
    if result["exit"] != 0:
        raise HarnessStop(f"component {operation} on {scale} exited {result['exit']}: {result['stderr'][-400:]!r}")
    data = json.loads(out.read_text(encoding="utf-8"))
    out.unlink()
    data["wall_ns"] = result["wall_ns"]
    if operation == "status":
        data["output_identical"] = _sha(result["stdout"]) == reference["status_stdout_sha256"]
        if not data["output_identical"]:
            raise HarnessStop(f"instrumented status JSON on {scale} is not byte-identical to the uninstrumented one")
    else:
        data["output_identical"] = result["stdout"].decode("utf-8", "replace").strip() == VALIDATE_PASS_LINE
        if not data["output_identical"]:
            raise HarnessStop(f"instrumented validate-project on {scale} did not PASS")
    families: dict[str, int] = {}
    for family, *_rest in data["git"]:
        families[family] = families.get(family, 0) + 1
    problems = check_git_families(families)
    if problems["network"]:
        raise HarnessStop(f"measured {operation} on {scale} ran network Git: {', '.join(problems['network'])}")
    if any(key.startswith("socket.") for key in data["events"]):
        raise HarnessStop(f"measured {operation} on {scale} opened a socket")
    # identical argv groups by digest only; the argv text (paths) is never kept
    for row in data["git"]:
        row[4] = _sha(row[4].encode("utf-8"))[:16]
    return data


SEQUENCE_STEPS = ("validate-registry", "router", "status", "validate-project")


def recovery_sequence(scale: str, project: Path, workline_root: Path, python: list[str], run_dir: Path,
                      reference: dict[str, Any], index: int) -> dict[str, Any]:
    """§36.12: the supported fresh-session recovery, mechanically - each step its own fresh process, in order.

    1. ``validate-registry <workline-root>`` - bootstrap steps 2-4 (configured root, registry read and validation);
    2. router child - bootstrap steps 5-6 and the router's call-time inventory (``registry.resolve_skill`` /
       ``router_candidates`` after ``activate()``, SKILL.md bytes read, never interpreted);
    3. ``status <project-root> --json`` - A-I inside one process;
    4. ``validate-project <project-root>``.
    """
    steps: dict[str, int] = {}
    registry = run_timed(launcher_command(python, workline_root, "validate-registry", str(workline_root)), project)
    if registry["exit"] != 0 or registry["stdout"].decode("utf-8", "replace").strip() != "registry validation: PASS":
        raise HarnessStop(f"validate-registry did not PASS in the {scale} recovery sequence")
    steps["validate-registry"] = registry["wall_ns"]
    out = run_dir / f"router-{scale}-{index}.json"
    router = run_timed(child_command(python, "router", str(workline_root / LAUNCHER_NAME), str(out)), project)
    if router["exit"] != 0:
        raise HarnessStop(f"router resolution failed in the {scale} recovery sequence: {router['stderr'][-400:]!r}")
    inner = json.loads(out.read_text(encoding="utf-8"))
    out.unlink()
    steps["router"] = router["wall_ns"]
    status = run_timed(status_command(python, workline_root, project), project)
    if status["exit"] != 0 or _sha(status["stdout"]) != reference["status_stdout_sha256"]:
        raise HarnessStop(f"status differs from the admitted reference in the {scale} recovery sequence")
    steps["status"] = status["wall_ns"]
    validated = run_timed(validate_command(python, workline_root, project), project)
    if validated["exit"] != 0 or validated["stdout"].decode("utf-8", "replace").strip() != VALIDATE_PASS_LINE:
        raise HarnessStop(f"validate-project did not PASS in the {scale} recovery sequence")
    steps["validate-project"] = validated["wall_ns"]
    return {"steps_ns": steps, "total_ns": sum(steps.values()), "router": inner}


def trace2_count(scale: str, operation: str, project: Path, workline_root: Path, python: list[str],
                 run_dir: Path) -> dict[str, Any]:
    """§36.14: Git's own Trace2 ``start`` events of one uninstrumented invocation, aggregated, raw trace discarded."""
    trace_dir = run_dir / f"trace2-{scale}-{operation}"
    trace_dir.mkdir()
    env = dict(os.environ)
    env["GIT_TRACE2_EVENT"] = str(trace_dir)
    try:
        result = run_timed(operation_command(operation, python, workline_root, project), project, env=env)
        families: dict[str, int] = {}
        nested = 0
        for path in sorted(trace_dir.iterdir()):
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("event") != "start":
                    continue
                if "/" in str(event.get("sid", "")):
                    nested += 1
                    continue
                argv = [str(item) for item in event.get("argv") or []][1:]
                family = git_family(argv[2:] if argv[:1] == ["-C"] else argv)
                families[family] = families.get(family, 0) + 1
    finally:
        shutil.rmtree(trace_dir, ignore_errors=True)
    if result["exit"] != 0:
        raise HarnessStop(f"trace2 {operation} on {scale} exited {result['exit']}")
    problems = check_git_families(families)
    if problems["network"]:
        raise HarnessStop(f"measured {operation} on {scale} ran network Git: {', '.join(problems['network'])}")
    return {"families": dict(sorted(families.items())), "total": sum(families.values()), "nested_starts": nested,
            "unclassified": problems["unclassified"]}


def profile_run(scale: str, operation: str, project: Path, workline_root: Path, python: list[str],
                run_dir: Path) -> dict[str, Any]:
    out = run_dir / f"profile-{scale}-{operation}.json"
    args = [STATUS_COMMAND, str(project), STATUS_JSON_FLAG] if operation == "status" else [VALIDATE_COMMAND, str(project)]
    result = run_timed(child_command(python, "profile", str(workline_root / LAUNCHER_NAME), str(out), "--", *args), project)
    if result["exit"] != 0:
        raise HarnessStop(f"profile {operation} on {scale} exited {result['exit']}")
    data = json.loads(out.read_text(encoding="utf-8"))
    out.unlink()
    data["wall_ns"] = result["wall_ns"]
    return data


# =========================================================================== statistics and triggers


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile (``fraction`` in (0, 1])."""
    ordered = sorted(values)
    rank = max(1, -(-int(round(fraction * 1000)) * len(ordered) // 1000))
    return ordered[min(rank, len(ordered)) - 1]


def quartiles(values: list[float]) -> tuple[float, float]:
    if len(values) < 2:
        return values[0], values[0]
    q = statistics.quantiles(values, n=4, method="inclusive")
    return q[0], q[2]


def summarize(values_ns: list[int]) -> dict[str, Any]:
    values = [value / 1e6 for value in values_ns]
    q1, q3 = quartiles(values)
    summary = {
        "n": len(values),
        "first_ms": values[0],
        "median_ms": statistics.median(values),
        "min_ms": min(values),
        "max_ms": max(values),
        "q1_ms": q1,
        "q3_ms": q3,
        "p95_ms": percentile(values, 0.95) if len(values) >= 20 else None,
        "samples_ms": values,
    }
    return summary


TRIGGER_A_THRESHOLD = 0.5
TRIGGER_B_THRESHOLD = 12.0


def evaluate_trigger_a(candidates: list[dict[str, Any]], denominator_ms: float,
                       denominator_q3_ms: float | None = None) -> dict[str, Any]:
    """§36.17: true only when one concrete removable derivation is supported for strictly more than 50%.

    Each candidate: ``name``, ``numerator_ms`` (deduplicated), ``supported``
    (backed by the component run), ``removable`` (why it is removable or
    reusable without semantic change; ``None`` when it is not) and optionally
    ``estimate`` (a profiler-share estimate: supporting evidence only, never a
    proof - ambiguous attribution is not-proven, §36.17). A proven candidate
    is robust when it also exceeds 50% of the upper-quartile denominator;
    otherwise the threshold conclusion is ``non_robust`` (§36.32).
    """
    rows = []
    for candidate in candidates:
        fraction = candidate["numerator_ms"] / denominator_ms if denominator_ms > 0 else 0.0
        proven = (bool(candidate.get("supported")) and bool(candidate.get("removable")) and not candidate.get("estimate")
                  and fraction > TRIGGER_A_THRESHOLD)
        conservative = (candidate["numerator_ms"] / denominator_q3_ms) if denominator_q3_ms else fraction
        rows.append({**candidate, "fraction": fraction, "exceeds_half": fraction > TRIGGER_A_THRESHOLD, "proven": proven,
                     "robust": proven and conservative > TRIGGER_A_THRESHOLD})
    return {
        "denominator_ms": denominator_ms,
        "denominator_q3_ms": denominator_q3_ms,
        "candidates": rows,
        "trigger": any(row["proven"] and row["robust"] for row in rows),
        "non_robust": any(row["proven"] and not row["robust"] for row in rows),
        "estimate_exceeds_half": any(row.get("estimate") and row["exceeds_half"] for row in rows),
    }


def evaluate_trigger_b(small_ms: list[float], large_ms: list[float]) -> dict[str, Any]:
    """§36.18: median ratio > 12x AND the excess outside observed run-to-run noise.

    Noise is the observed interquartile spread: the excess is outside it when
    even the conservative ratio Q1(larger) / Q3(smaller) exceeds 12x. A median
    ratio above 12x whose conservative ratio does not is ``non_robust`` (§36.32:
    STOP rather than claim); a median ratio at or below 12x is ``false``.
    """
    median_small, median_large = statistics.median(small_ms), statistics.median(large_ms)
    if median_small <= 0:
        return {"ratio": None, "conservative": None, "optimistic": None, "verdict": "unmeasurable"}
    q1_small, q3_small = quartiles(small_ms)
    q1_large, q3_large = quartiles(large_ms)
    ratio = median_large / median_small
    conservative = q1_large / q3_small if q3_small > 0 else None
    optimistic = q3_large / q1_small if q1_small > 0 else None
    if ratio <= TRIGGER_B_THRESHOLD:
        verdict = "false"
    elif conservative is not None and conservative > TRIGGER_B_THRESHOLD:
        verdict = "true"
    else:
        verdict = "non_robust"
    return {"ratio": ratio, "conservative": conservative, "optimistic": optimistic, "verdict": verdict,
            "median_small_ms": median_small, "median_large_ms": median_large}


def decide(trigger_a: bool, trigger_b_verdicts: list[str], trigger_a_non_robust: bool = False) -> str:
    """The frozen §36.19 decision; ``STOP_NON_ROBUST`` when a threshold conclusion cannot be drawn (§36.32)."""
    b_true = "true" in trigger_b_verdicts
    if not b_true and "non_robust" in trigger_b_verdicts:
        return "STOP_NON_ROBUST"
    if trigger_a_non_robust and not trigger_a:
        return "STOP_NON_ROBUST"
    if trigger_a and b_true:
        return "MEASURED_TRIGGER_A_AND_B"
    if trigger_a:
        return "MEASURED_TRIGGER_A"
    if b_true:
        return "MEASURED_TRIGGER_B"
    return "MEASURED_NO_OPT"


# --------------------------------------------------------------------------- component aggregation


def stage_samples(components: list[dict[str, Any]]) -> dict[str, list[float]]:
    """Per component sample: exclusive ms per stage (A-I), plus unassigned, harness and process overhead."""
    found: dict[str, list[float]] = {stage: [] for stage in STAGES}
    for name in ("unassigned", "harness", "process_overhead", "in_process", "wall"):
        found[name] = []
    for data in components:
        totals = {stage: 0 for stage in STAGES}
        harness = data["harness_ns"]
        for _label, (stage, _count, _inclusive, exclusive) in data["spans"].items():
            if stage in totals:
                totals[stage] += exclusive
            else:
                harness += exclusive
        for stage in STAGES:
            found[stage].append(totals[stage] / 1e6)
        assigned = sum(totals.values())
        found["harness"].append(harness / 1e6)
        found["unassigned"].append((data["in_process_ns"] - harness - assigned) / 1e6)
        found["in_process"].append(data["in_process_ns"] / 1e6)
        found["wall"].append(data["wall_ns"] / 1e6)
        found["process_overhead"].append((data["wall_ns"] - data["in_process_ns"]) / 1e6)
    return found


def label_table(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels: dict[str, dict[str, Any]] = {}
    for data in components:
        for label, (stage, count, inclusive, exclusive) in data["spans"].items():
            row = labels.setdefault(label, {"label": label, "stage": stage, "count": [], "inclusive": [], "exclusive": []})
            row["count"].append(count)
            row["inclusive"].append(inclusive / 1e6)
            row["exclusive"].append(exclusive / 1e6)
    rows = []
    for row in labels.values():
        rows.append({"label": row["label"], "stage": row["stage"], "count": int(statistics.median(row["count"])),
                     "inclusive_ms": statistics.median(row["inclusive"]), "exclusive_ms": statistics.median(row["exclusive"])})
    return sorted(rows, key=lambda row: (row["stage"], -row["exclusive_ms"]))


def git_tables(components: list[dict[str, Any]]) -> dict[str, Any]:
    """Median per-invocation Git counts and time by family, by calling span, and identical-argv repeats."""
    per_family: dict[str, list[int]] = {}
    per_family_ms: dict[str, list[float]] = {}
    per_parent: dict[str, list[float]] = {}
    repeats_ms: list[float] = []
    repeats_count: list[int] = []
    hermetic: list[int] = []
    totals: list[int] = []
    for data in components:
        counts: dict[str, int] = {}
        times: dict[str, float] = {}
        parents: dict[str, float] = {}
        groups: dict[str, list[tuple[float, str]]] = {}
        for family, ns, parent, is_hermetic, digest in data["git"]:
            counts[family] = counts.get(family, 0) + 1
            times[family] = times.get(family, 0.0) + ns / 1e6
            parents[parent] = parents.get(parent, 0.0) + ns / 1e6
            groups.setdefault(digest, []).append((ns / 1e6, parent))
        for family in set(per_family) | set(counts):
            per_family.setdefault(family, []).append(counts.get(family, 0))
            per_family_ms.setdefault(family, []).append(times.get(family, 0.0))
        for parent in set(per_parent) | set(parents):
            per_parent.setdefault(parent, []).append(parents.get(parent, 0.0))
        removable = 0.0
        repeated = 0
        for calls in groups.values():
            non_witness = [ms for ms, parent in calls if parent != "status.read_witnesses"]
            if len(calls) > 1 and len(non_witness) > 1:
                # beyond the first of an identical non-witness command: the B0/B1 witness re-reads are semantic
                removable += sum(non_witness) * (len(non_witness) - 1) / len(non_witness)
                repeated += len(non_witness) - 1
        repeats_ms.append(removable)
        repeats_count.append(repeated)
        hermetic.append(sum(1 for row in data["git"] if row[3]))
        totals.append(len(data["git"]))
    table: dict[str, int] = {name: 0 for name in FAMILY_TABLE}
    for family, values in per_family.items():
        table[table_family(family)] += int(statistics.median(values))
    return {
        "total": int(statistics.median(totals)) if totals else 0,
        "hermetic": int(statistics.median(hermetic)) if hermetic else 0,
        "families": {family: int(statistics.median(values)) for family, values in sorted(per_family.items())},
        "family_ms": {family: statistics.median(values) for family, values in sorted(per_family_ms.items())},
        "table": table,
        "by_parent_ms": {parent: statistics.median(values) for parent, values in sorted(per_parent.items())},
        "identical_repeat_count": int(statistics.median(repeats_count)) if repeats_count else 0,
        "identical_repeat_removable_ms": statistics.median(repeats_ms) if repeats_ms else 0.0,
    }


def _label_row(rows: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    for row in rows:
        if row["label"] == label:
            return row
    return None


def trigger_a_candidates(labels: list[dict[str, Any]], git: dict[str, Any], profile: dict[str, Any] | None,
                         in_process_ms: float, derivation: list[dict[str, Any]] | None = None,
                         stages: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Concrete repeated-derivation candidates of one operation at M, each deduplicated (§36.17).

    Rows marked ``bound`` are upper bounds over a whole family (every Git
    subprocess, all derivation stages): never a removable derivation by
    themselves, they show how far any optimization of that family could reach.
    """
    candidates = []

    def repeated(label: str, name: str, removable: str, use_inclusive: bool = False) -> None:
        row = _label_row(labels, label)
        if row is None:
            return
        base = row["inclusive_ms"] if use_inclusive else row["exclusive_ms"]
        count = row["count"]
        numerator = base * (count - 1) / count if count > 1 else 0.0
        candidates.append({
            "name": name, "numerator_ms": numerator, "calls": count, "supported": True,
            "removable": removable if count > 1 else None,
            "support": f"component span {label}: {count} call(s), {base:.1f} ms {'inclusive' if use_inclusive else 'exclusive'}",
        })

    repeated("state.ProjectView.load", "repeated canonical Project load (ProjectView.load) within one command",
             "the second load reads the same files between the same B0/B1 witnesses; one immutable snapshot can be "
             "reused (§36.22 step 2)")
    repeated("validate.validate_structure", "repeated structure validation (validate_structure) within one command",
             "the same validation over the same snapshot; its result can be reused (§36.22 step 1)")
    repeated("registry.validate_registry", "repeated registry validation (validate_registry) within one command",
             "the same registry bytes validated again within one command (§36.22 step 1)")
    repeated("implementation.configured_implementation_problem",
             "repeated configured-implementation identity check within one command",
             "the same question of the same loaded modules (§36.22 step 1)", use_inclusive=True)
    candidates.append({
        "name": "identical Git commands repeated within one command (B0/B1 witness re-reads excluded)",
        "numerator_ms": git["identical_repeat_removable_ms"], "calls": git["identical_repeat_count"],
        "supported": True,
        "removable": "the same local question asked again; batching equivalent reads keeps the questions (§36.22 step 3)"
        if git["identical_repeat_count"] else None,
        "support": f"component Git wrapper: {git['identical_repeat_count']} repeated identical command(s)",
    })
    if derivation:
        rows = label_table(derivation)
        for label, name in DERIVATION_SCANS.items():
            row = _label_row(rows, label)
            if row is None or row["count"] < 1:
                continue
            candidates.append({
                "name": name,
                "numerator_ms": row["exclusive_ms"] * (row["count"] - 1) / row["count"], "calls": row["count"],
                "supported": True,
                "removable": "each call rescans a whole immutable list of the one snapshot; one grouping pass per "
                             "command replaces the repeats (an in-memory index: §36.22 step 4, after steps 1-3)"
                if row["count"] > 1 else None,
                "support": f"derivation-span variant ({len(derivation)} sample(s), median): {row['count']} calls, "
                           f"{row['exclusive_ms']:.1f} ms exclusive (per-call wrapper overhead included: an over-estimate)",
            })
    if stages:
        git_ms = stages["H"]["median_ms"]
        derivation_ms = sum(stages[stage]["median_ms"] for stage in ("E", "F", "G"))
        candidates.append({
            "name": "BOUND: every local Git subprocess of the command (stage H)", "numerator_ms": git_ms,
            "calls": git.get("total"), "supported": True, "removable": None, "bound": True,
            "support": "component stage H median; not one derivation - the B0/B1 witnesses and each distinct "
                       "question are semantic",
        })
        candidates.append({
            "name": "BOUND: all canonical load + validation + status derivation (stages E+F+G)",
            "numerator_ms": derivation_ms, "calls": None, "supported": True, "removable": None, "bound": True,
            "support": "component stage medians E+F+G; not one derivation",
        })
    if profile:
        total = profile["total_tottime_s"]
        for row in profile["workline"]:
            if row[0] == "src/workline/state.py" and row[2] == "events_for":
                share = row[5] / total if total else 0.0
                candidates.append({
                    "name": "per-entity full Event-log scans (ProjectView.events_for) behind state derivation",
                    "numerator_ms": share * in_process_ms, "calls": row[3], "supported": True,
                    "removable": "one grouping of the immutable Event list per command replaces each O(E) rescan "
                                 "(an in-memory index: §36.22 step 4, after steps 1-3)",
                    "support": f"cProfile (supporting): {row[3]} calls, {share * 100:.1f}% of profiled time; "
                               "estimate = share x component in-process median (profiler overhead inflates call-heavy code)",
                    "estimate": True,
                })
    return candidates


def analyze(results: dict[str, Any]) -> dict[str, Any]:
    scales = [scale for scale in ("T", "S", "M", "L") if scale in results["scales"]]
    analysis: dict[str, Any] = {"cold": {}, "warm": {}, "stages": {}, "labels": {}, "git": {}, "trace2": {}}
    for scale in scales:
        data = results["scales"][scale]
        if "cold" in data:
            analysis["cold"][scale] = {op: summarize(data["cold"][op]) for op in OPERATIONS}
        if "warm" in data:
            analysis["warm"][scale] = summarize(data["warm"]["calls_ns"])
        if "component" in data:
            analysis["stages"][scale] = {}
            analysis["labels"][scale] = {}
            analysis["git"][scale] = {}
            for op in OPERATIONS:
                components = data["component"].get(op) or []
                if not components:
                    continue
                stages = stage_samples(components)
                analysis["stages"][scale][op] = {
                    name: {"median_ms": statistics.median(values), "samples_ms": values} for name, values in stages.items()
                }
                analysis["labels"][scale][op] = label_table(components)
                analysis["git"][scale][op] = git_tables(components)
        if "trace2" in data:
            analysis["trace2"][scale] = data["trace2"]
        if data.get("sequence"):
            runs = data["sequence"]
            analysis.setdefault("sequence", {})[scale] = {
                "n": len(runs),
                "steps_median_ms": {step: statistics.median(run["steps_ns"][step] / 1e6 for run in runs)
                                    for step in SEQUENCE_STEPS},
                "total": summarize([run["total_ns"] for run in runs]),
                "router_inner_median_ms": {
                    key: statistics.median(run["router"][key] / 1e6 for run in runs)
                    for key in ("activation_ns", "router_resolution_ns", "router_inventory_ns")
                },
                "router_candidates": runs[0]["router"]["candidates"],
            }

    # Trigger B: each operation and each A-I stage, S->M and M->L separately
    pairs = [(a, b) for a, b in (("S", "M"), ("M", "L")) if a in scales and b in scales]
    trigger_b: list[dict[str, Any]] = []
    for small, large in pairs:
        counts_small = results["scales"][small]["manifest"]["counts"]
        counts_large = results["scales"][large]["manifest"]["counts"]
        sizes = {"works_ratio": counts_large["works"] / counts_small["works"],
                 "events_ratio": counts_large["events"] / counts_small["events"]}
        for op in OPERATIONS:
            if small in analysis["cold"] and large in analysis["cold"]:
                row = evaluate_trigger_b(analysis["cold"][small][op]["samples_ms"], analysis["cold"][large][op]["samples_ms"])
                trigger_b.append({"pair": f"{small}->{large}", "subject": f"cold {op} (wall)", **sizes, **row})
            if op in analysis["stages"].get(small, {}) and op in analysis["stages"].get(large, {}):
                for stage in STAGES:
                    row = evaluate_trigger_b(analysis["stages"][small][op][stage]["samples_ms"],
                                             analysis["stages"][large][op][stage]["samples_ms"])
                    trigger_b.append({"pair": f"{small}->{large}", "subject": f"{op} stage {stage}", **sizes, **row})
        if small in analysis["warm"] and large in analysis["warm"]:
            row = evaluate_trigger_b(analysis["warm"][small]["samples_ms"], analysis["warm"][large]["samples_ms"])
            trigger_b.append({"pair": f"{small}->{large}", "subject": "warm status (diagnostic only)", "diagnostic": True,
                              **sizes, **row})
    analysis["trigger_b"] = trigger_b
    deciding = [row["verdict"] for row in trigger_b if not row.get("diagnostic") and row["verdict"] != "unmeasurable"]

    # Trigger A: representative M, uninstrumented cold median as the denominator
    trigger_a: dict[str, Any] = {}
    if "M" in analysis["cold"] and "M" in analysis["labels"]:
        for op in OPERATIONS:
            if op not in analysis["labels"]["M"]:
                continue
            profile = (results["scales"]["M"].get("profile") or {}).get(op)
            derivation = (results["scales"]["M"].get("component_derivation") or {}).get(op)
            in_process = analysis["stages"]["M"][op]["in_process"]["median_ms"]
            candidates = trigger_a_candidates(analysis["labels"]["M"][op], analysis["git"]["M"][op], profile, in_process,
                                              derivation, analysis["stages"]["M"][op])
            trigger_a[op] = evaluate_trigger_a(candidates, analysis["cold"]["M"][op]["median_ms"],
                                               analysis["cold"]["M"][op]["q3_ms"])
    analysis["trigger_a"] = trigger_a
    a_true = any(entry["trigger"] for entry in trigger_a.values())
    a_non_robust = any(entry["non_robust"] for entry in trigger_a.values())
    analysis["trigger_a_true"] = a_true
    analysis["trigger_a_non_robust"] = a_non_robust
    analysis["trigger_a_estimate_only"] = not a_true and any(entry["estimate_exceeds_half"] for entry in trigger_a.values())
    analysis["trigger_b_true"] = "true" in deciding
    analysis["decision"] = decide(a_true, deciding, trigger_a_non_robust=a_non_robust) if trigger_a else "INCOMPLETE"
    return analysis


# =========================================================================== rendering

LIMITATIONS = (
    "Cold-process, not cold-disk: the OS file cache is not purged, so repeated samples read warm file data.",
    "One machine, one OS: absolute times (especially Windows process creation, which every Git subprocess and the "
    "py launcher pay) are specific to it; the trigger decisions rest on ratios and shares measured on it.",
    "The quiet window pauses test processes; other non-test processes of the machine still run and are not "
    "controlled beyond the recorded CPU / disk samples.",
    "The canonical invocation writes no bytecode (-B) and none is present, so every cold sample compiles the imported "
    "Workline modules from source; that is the supported path, and it is measured as such (stage A).",
    "Component spans are instrumented: wrapper overhead is included, and the child preloads `runpy` (with "
    "`importlib.util`), so stage A import time is slightly under-stated there; headline numbers are uninstrumented.",
    "Derivation-span samples wrap very frequently called scans: their numerators over-state the scan cost a little.",
    "The profiler run is supporting evidence only; cProfile inflates call-heavy code.",
    "Git Trace2 cannot see the Review hermetic (class A/B) commands, which strip every inherited GIT_* variable by "
    "design; the complete count is the component wrapper's.",
    "Byte and count observations come from the generated fixture files, not from read counters in production readers.",
    "The pending fixture is a real owner's structurally valid record classified `unknown_or_invalid`: a positively "
    "resumable record would need a remote, which the benchmark Project must not have (§36.8-§36.9).",
    "The Review fixture is one P1-shape Run (no P4 Run, no Work-terminal activation): Review status cost is covered "
    "at O(1), not every Review contract path.",
    "Warm results are diagnostic only and never decide BL-007.",
)

_ABSOLUTE = re.compile(r"(?<![A-Za-z0-9<])[A-Za-z]:[\\/]|\\\\[A-Za-z0-9]|/(?:Users|home|tmp|mnt)/", re.IGNORECASE)


def public_safety_problems(text: str, private_words: "list[str] | None" = None) -> list[str]:
    """Absolute paths and private machine names a public-safe summary must not carry (§36.16)."""
    problems = []
    if _ABSOLUTE.search(text):
        problems.append(f"absolute path: {_ABSOLUTE.search(text).group(0)!r}")
    words = list(private_words or [])
    if private_words is None:
        try:
            import getpass
            import socket

            words = [socket.gethostname(), getpass.getuser()]
        except Exception:  # noqa: BLE001 - no name, nothing to compare
            words = []
    for word in words:
        if word and len(word) >= 3 and re.search(re.escape(word), text, re.IGNORECASE):
            problems.append("private machine/user name")
    return problems


def _ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.1f}"


def _ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}x"


def render_summary(results: dict[str, Any], analysis: dict[str, Any]) -> str:
    env = results["environment"]
    ident = results["identity"]
    lines: list[str] = []
    out = lines.append
    label = results["label"]
    out(f"# WORKLINE RB2 performance measurement - BL-007 cold-start recovery ({label})")
    out("")
    if label != "OFFICIAL":
        out(f"> **{label}: not BL-007 evidence.** Harness debugging output; timings may be taken under load.")
        out("")
    out("Completion Sprint evidence only (`WORKLINE_COMPLETION_SPRINT.md` §36). No Workline runtime code, status, "
        "validation or routing reads this file.")
    out("")
    out("**What this does not claim (§36.3).** It measures deterministic local Workline recovery mechanics only. It "
        "does not benchmark LLM reasoning latency, token generation or model context loading, human reading time, "
        "editor/IDE startup, or network latency. `Cold-start recovery` here is not total agent wall-clock experience. "
        "Samples are cold-process, not cold-disk: the OS file cache is not purged.")
    out("")
    out("## Identity")
    out("")
    out(f"- Reviewed/Measured Workline SHA: `{ident['measured_workline_sha']}`"
        + (" (runtime surfaces at the harness commit are byte-identical to it: `src/`, `run-workline.py`, "
           "`registry.md`, `.claude/`)" if ident["runtime_identical_to_measured"] else " (**runtime differs - not valid**)"))
    if ident.get("note"):
        out(f"- Measured Workline status: {ident['note']}")
    out(f"- Benchmark harness SHA: `{ident['harness_sha']}`"
        + ("" if not ident["harness_dirty_entries"] else f" (**{ident['harness_dirty_entries']} uncommitted harness path(s)**)"))
    out(f"- Harness contract: `{HARNESS_CONTRACT}` v{HARNESS_VERSION}")
    out(f"- RB1 status command binding: `{results['binding']['status_cli']}`")
    out(f"- validate-project binding: `{results['binding']['validate_cli']}`")
    out(f"- RB1 status API binding (warm): {results['binding']['status_api']}")
    out(f"- Generator contract/seed: `{results['generator']['contract']}` v{results['generator']['version']}, "
        f"seed `{results['generator']['seed']}`")
    out(f"- Compiled bytecode under `<workline-root>/src` at measurement: {ident['pyc_files_under_src']} file(s)")
    out("")
    out("## Environment")
    out("")
    out(f"- Python: {env['python'].get('version')} ({env['python'].get('implementation', '?')}, "
        f"{env['python'].get('bits', '?')}), invoked as `{env['python_command']} -I -B`")
    out(f"- Git: {env['git_version']}; global config: "
        + ", ".join(f"{key}={value}" for key, value in env["git_global_config"].items()))
    out(f"- OS: {env['os']} {env['os_release']} ({env['os_version']}), {env['machine']}")
    out(f"- CPU: {env['processor']}; logical CPUs: {env['logical_cpus']}")
    out(f"- Page cache: {env['page_cache']}")
    quiet = results.get("quiet", {})
    out("- Quiet window: " + ("granted by the Orchestrator (`MEASURE_SLOT_GRANTED`)" if label == "OFFICIAL" else "none (smoke)"))
    for name in ("before", "after"):
        sample = quiet.get(name)
        if sample:
            out(f"  - {name}: CPU% {sample.get('cpu_percent')}, disk idle% {sample.get('disk_idle_percent')}, "
                f"disk queue {sample.get('disk_queue')}, pytest processes {sample.get('pytest_processes')}, "
                f"live sharded suites {sample.get('active_suites', 'n/a')}")
    boundaries = quiet.get("boundaries") or []
    if boundaries:
        out(f"  - batch boundaries checked: {len(boundaries)}; pytest processes seen at any boundary: "
            f"{max((b.get('pytest_processes') or 0) for b in boundaries)}")
    out("")
    out("## Fixtures (S/M/L actual counts + digests)")
    out("")
    out("| scale | Works | Phases | Roadmaps | completed / in progress / unstarted | roadmap relations | Related | "
        "Events | event-log bytes | entity bytes | Review records (bytes) | pending records (bytes) | logical digest |")
    out("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for scale, data in results["scales"].items():
        c = data["manifest"]["counts"]
        states = c["work_states"]
        out(f"| {scale} | {c['works']} | {c['phases']} | {c['roadmaps']} | {states['completed']} / "
            f"{states['in_progress']} / {states['unstarted']} | {c['roadmap_relations']} | {c['related']} | "
            f"{c['events']} | {c['event_log_bytes']:,} | {c['entity_bytes']:,} | {c['review_records']} "
            f"({c['review_bytes']:,}) | {c['pending_records']} ({c['pending_bytes']:,}) | "
            f"`{data['manifest']['logical_digest'][:16]}` |")
    out("")
    out("Each fixture: one local commit of the canonical files, no remote; only the intentional runtime pending "
        "record uncommitted; admitted only after the landed `validate-project` PASSed and status read it "
        "`stable_read` (§36.9).")
    out("")
    first = next(iter(results["scales"].values()))["admission"]["facts"]
    differing = [scale for scale, data in results["scales"].items() if data["admission"]["facts"] != first]
    if differing:
        out(f"- **Admission facts differ at {', '.join(differing)}** - see results.json; the lines below are the first scale's.")
    for record in first["pending"]:
        out(f"- Pending fixture (§36.8): one pending `{record['owner']}` record, classified by RB1 as "
            f"`{record['classification']}` (`{record['reason']}`), affects_progression={record['affects_progression']}. "
            "A structurally valid record of a real owner whose read-only probe runs; a positive resumability "
            "proof would need a remote, which §36.9 excludes.")
    for run in first["review_runs"]:
        out(f"- Review fixture (§36.8): one Review Run (`{run['review_kind']}`, generations 1 open -> 2 sealed) with "
            f"its Receipt: state `{run['state']}`, receipt `{run['receipt']}`, obligations `{run['obligations']}`; "
            f"Work-terminal activation `{first['review_activation']}`.")
    current = ", ".join(f"{name}={'selected' if present else 'none'}" for name, present in first["current_ids_present"].items())
    upcoming = ", ".join(f"{name}={'selected' if present else 'none'}" for name, present in first["next_ids_present"].items())
    out(f"- Selection (every scale): current {current}; next {upcoming}; blockers {first['blockers'] or 'none'}; "
        f"the current Work is the fixture's one in-flight Work: {first['current_work_is_fixture_in_flight_work']}.")
    out("")
    out("## Cold process (headline, uninstrumented)")
    out("")
    out("| scale | operation | n | first | median | q1 | q3 | p95 | max |")
    out("|---|---|---|---|---|---|---|---|---|")
    for scale, ops in analysis["cold"].items():
        for op in OPERATIONS:
            s = ops[op]
            out(f"| {scale} | {op} | {s['n']} | {_ms(s['first_ms'])} | **{_ms(s['median_ms'])}** | {_ms(s['q1_ms'])} | "
                f"{_ms(s['q3_ms'])} | {_ms(s['p95_ms'])} | {_ms(s['max_ms'])} |")
    out("")
    out("Milliseconds. p95 is nearest-rank and reported only for n >= 20. Scales ran round-robin with a rotating "
        "start, and status / validate-project alternated first (§36.10).")
    out("")
    out("## Warm process (diagnostic only)")
    out("")
    out("| scale | calls | first | median | q3 | p95 | max |")
    out("|---|---|---|---|---|---|---|")
    for scale, s in analysis["warm"].items():
        out(f"| {scale} | {s['n']} | {_ms(s['first_ms'])} | {_ms(s['median_ms'])} | {_ms(s['q3_ms'])} | "
            f"{_ms(s['p95_ms'])} | {_ms(s['max_ms'])} |")
    out("")
    out("## A-I stage table (component run, instrumented, exclusive time)")
    out("")
    for op in OPERATIONS:
        scales_with = [scale for scale in analysis["stages"] if op in analysis["stages"][scale]]
        if not scales_with:
            continue
        out(f"### {op}")
        out("")
        out("| stage | " + " | ".join(f"{scale} median ms" for scale in scales_with) + " |")
        out("|---|" + "---|" * len(scales_with))
        for stage in STAGES:
            out(f"| {stage} {STAGE_NAMES[stage]} | "
                + " | ".join(_ms(analysis["stages"][scale][op][stage]["median_ms"]) for scale in scales_with) + " |")
        for name, text in (("unassigned", "unassigned in-process (outside every span)"),
                           ("harness", "harness only (runpy load of the launcher, span installation; not A-I)"),
                           ("in_process", "in-process total"),
                           ("process_overhead", "interpreter start/exit + pipes (wall - in-process)"),
                           ("wall", "instrumented wall")):
            out(f"| {text} | " + " | ".join(_ms(analysis["stages"][scale][op][name]["median_ms"]) for scale in scales_with) + " |")
        out("")
        if "M" in analysis["labels"] and op in analysis["labels"]["M"]:
            out(f"Span detail at M ({op}): label, stage, calls, inclusive ms, exclusive ms.")
            out("")
            out("| span | stage | calls | inclusive | exclusive |")
            out("|---|---|---|---|---|")
            for row in analysis["labels"]["M"][op]:
                out(f"| `{row['label']}` | {row['stage']} | {row['count']} | {_ms(row['inclusive_ms'])} | "
                    f"{_ms(row['exclusive_ms'])} |")
            out("")
    out("Spans wrap the landed boundaries at runtime in a separate child running the launcher's own `main`; the "
        "instrumented status JSON was byte-identical to the uninstrumented one for every sample. Stage H is every Git "
        "subprocess wherever it was called from (its time is not also counted in the calling stage). "
        "Stage F includes `validate_structure` wherever it runs (also inside status lifecycle). Unassigned time is "
        "reported, not forced into a stage.")
    out("")
    if analysis.get("sequence"):
        out("## Mechanical recovery end-to-end (§36.12)")
        out("")
        out("Fresh-session recovery as the supported procedure runs it, one fresh process per step: "
            "`validate-registry <workline-root>` (bootstrap: configured root, registry read + validation), the router "
            "step (`activate()`, `registry.resolve_skill(skills/project-router)`, the router's call-time "
            "`router_candidates`, SKILL.md bytes read - never interpreted), `status --json` (A-I in one process), "
            "`validate-project`. A-D also run inside status itself; the status A-I table above is that process's split.")
        out("")
        out("| scale | n | validate-registry | router | status | validate-project | total median | total max |")
        out("|---|---|---|---|---|---|---|---|")
        for scale, seq in analysis["sequence"].items():
            steps = seq["steps_median_ms"]
            out(f"| {scale} | {seq['n']} | " + " | ".join(_ms(steps[step]) for step in SEQUENCE_STEPS)
                + f" | **{_ms(seq['total']['median_ms'])}** | {_ms(seq['total']['max_ms'])} |")
        first_seq = next(iter(analysis["sequence"].values()))
        inner = first_seq["router_inner_median_ms"]
        out("")
        out(f"Router step in-process (median, first scale): activation {_ms(inner['activation_ns'])} ms, router "
            f"resolution {_ms(inner['router_resolution_ns'])} ms, inventory of {first_seq['router_candidates']} "
            f"routable Skills {_ms(inner['router_inventory_ns'])} ms.")
        out("")
    out("## Git command counts (per invocation)")
    out("")
    out("| scale | operation | total | " + " | ".join(FAMILY_TABLE) + " | hermetic (env-stripped) | Trace2 visible |")
    out("|---|---|---|" + "---|" * len(FAMILY_TABLE) + "---|---|")
    for scale, ops in analysis["git"].items():
        for op, table in ops.items():
            trace = (analysis["trace2"].get(scale) or {}).get(op) or {}
            out(f"| {scale} | {op} | {table['total']} | " + " | ".join(str(table["table"][f]) for f in FAMILY_TABLE)
                + f" | {table['hermetic']} | {trace.get('total', 'n/a')} |")
    out("")
    if "M" in analysis["git"]:
        for op, table in analysis["git"]["M"].items():
            out(f"- M {op}: families {table['families']}; Git ms by calling span "
                + ", ".join(f"`{k}` {v:.1f}" for k, v in table["by_parent_ms"].items()))
    out("")
    out("Counted by a benchmark-only wrapper of `gitcmd.run_git` / `run_git_bytes` in the component run (all Git "
        "goes through them), cross-checked with Git Trace2 `start` events of an uninstrumented run. Trace2 cannot see "
        "the Review hermetic (class A/B) commands: they run with every inherited `GIT_*` variable stripped by design, "
        "so the Trace2 total is lower by exactly those. No network family was observed; no socket was opened.")
    out("")
    out("## Trigger A (§36.17)")
    out("")
    for op, entry in analysis.get("trigger_a", {}).items():
        out(f"### {op} - denominator: uninstrumented cold M median {_ms(entry['denominator_ms'])} ms")
        out("")
        out("| candidate | numerator ms | fraction | > 50% | removable without semantic change | support |")
        out("|---|---|---|---|---|---|")
        for row in entry["candidates"]:
            removable = row["removable"] or ("n/a (upper bound, not one derivation)" if row.get("bound") else "n/a (no repeat)")
            out(f"| {row['name']} | {_ms(row['numerator_ms'])} | {row['fraction'] * 100:.1f}% | "
                f"{'yes' if row['exceeds_half'] else 'no'} | {removable} | {row['support']} |")
        out("")
        out(f"Trigger A ({op}): **{'true' if entry['trigger'] else 'false'}**")
        out("")
    out(f"**Trigger A: {'true' if analysis['trigger_a_true'] else 'false'}**"
        + (" (only a profiler estimate exceeded 50%: ambiguous attribution is not-proven, §36.17)"
           if analysis.get("trigger_a_estimate_only") else "")
        + (" - a candidate exceeds 50% of the median but not of Q3: non-robust (§36.32)"
           if analysis.get("trigger_a_non_robust") else ""))
    out("")
    out("Rule: one concrete removable derivation, deduplicated for nesting, strictly above 50% of the uninstrumented "
        "cold M median; candidates are never added together; BOUND rows only show how far a whole family could reach; "
        "profiler rows are supporting estimates (cProfile inflates call-heavy code), never the proof.")
    out("")
    out("## Trigger B (§36.18)")
    out("")
    out("| pair | subject | Works x | Events x | median small | median large | median ratio | conservative "
        "Q1(L)/Q3(S) | verdict |")
    out("|---|---|---|---|---|---|---|---|---|")
    for row in analysis["trigger_b"]:
        out(f"| {row['pair']} | {row['subject']} | {row['works_ratio']:.1f} | {row['events_ratio']:.2f} | "
            f"{_ms(row.get('median_small_ms'))} | {_ms(row.get('median_large_ms'))} | {_ratio(row['ratio'])} | "
            f"{_ratio(row['conservative'])} | {row['verdict']} |")
    out("")
    out("Frozen condition: median ratio > 12x AND the excess outside observed run-to-run noise; the noise bound is "
        "the interquartile spread (conservative ratio Q1 of the larger scale over Q3 of the smaller must also exceed "
        "12x). `non_robust` = median above 12x but inside noise (STOP, §36.32). Warm rows are diagnostic and never decide.")
    out("")
    out(f"**Trigger B: {'true' if analysis['trigger_b_true'] else 'false'}**")
    out("")
    out("## Decision")
    out("")
    out(f"**{analysis['decision']}**")
    out("")
    out("## Canonical Project mutation during measurement")
    out("")
    integrity = results.get("integrity_checks", 0)
    out(f"none - {integrity} before/after identity check(s) of every fixture (worktree bytes incl. the runtime record, "
        "the whole `.git`, HEAD, tree, porcelain status) were unchanged.")
    out("")
    out("## Limitations")
    out("")
    for item in LIMITATIONS:
        out(f"- {item}")
    out("")
    out("## Commands (portable form)")
    out("")
    for name, command in results["binding"]["commands"].items():
        out(f"- {name}: `{command}`")
    out("")
    out("## Raw cold samples (ms)")
    out("")
    for scale, ops in analysis["cold"].items():
        for op in OPERATIONS:
            out(f"- {scale} {op}: " + ", ".join(f"{value:.1f}" for value in ops[op]["samples_ms"]))
    out("")
    return "\n".join(lines) + "\n"


# =========================================================================== orchestration


def run_series(args: argparse.Namespace) -> dict[str, Any]:
    workline_root = Path(args.workline_root).resolve()
    fixtures = Path(args.fixtures).resolve()
    logs = Path(args.logs).resolve()
    python = python_command(args.python)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = logs / f"{args.label.lower()}-{stamp}"
    run_dir.mkdir(parents=True)
    log_file = run_dir / "progress.log"

    def log(message: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {message}"
        print(line, flush=True)
        with open(log_file, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    suites = Path(args.suites_dir) if args.suites_dir else None
    results: dict[str, Any] = {"label": args.label, "harness": {"contract": HARNESS_CONTRACT, "version": HARNESS_VERSION}}
    results["identity"] = harness_identity(workline_root, args.measured_sha)
    if getattr(args, "measured_note", None):
        results["identity"]["note"] = args.measured_note
    if args.label == "OFFICIAL":
        if not results["identity"]["runtime_identical_to_measured"]:
            raise HarnessStop("the measured root's runtime surfaces differ from the measured Workline SHA")
        if results["identity"]["harness_dirty_entries"]:
            raise HarnessStop("the harness has uncommitted changes; an official series needs a committed harness")
    results["environment"] = environment_record(python, fixtures)
    generator = load_generator()
    results["generator"] = {"contract": generator.GENERATOR_CONTRACT, "version": generator.GENERATOR_VERSION,
                            "seed": args.seed}
    quiet: dict[str, Any] = {"boundaries": []}
    results["quiet"] = quiet

    def boundary(name: str) -> None:
        if args.no_quiet_check:
            return
        sample = quiet_sample(samples=1, suites_dir=suites)
        sample["boundary"] = name
        quiet["boundaries"].append(sample)
        problem = quiet_problem(sample)
        if problem and args.label == "OFFICIAL":
            raise HarnessStop(f"quiet window broken at {name}: {problem}; this series is discarded")

    if not args.no_quiet_check:
        quiet["before"] = quiet_sample(samples=5, suites_dir=suites)
        problem = quiet_problem(quiet["before"])
        if problem and args.label == "OFFICIAL":
            raise HarnessStop(f"quiet window not quiet at start: {problem}")
    plan: list[tuple[str, Path]] = []
    results["scales"] = {}
    for scale in args.scales:
        fixture = ensure_fixture(fixtures, scale, workline_root, args.seed)
        log(f"admitting {scale} ({fixture.name})")
        admission = admit(fixture, workline_root, python)
        manifest = load_manifest(fixture)
        results["scales"][scale] = {"manifest": {k: manifest[k] for k in ("counts", "logical_digest",
                                                                         "logical_canonical_digest", "scale_spec")},
                                    "admission": admission}
        plan.append((scale, (fixture / "project").resolve()))
    references = {scale: results["scales"][scale]["admission"] for scale, _ in plan}
    project_of = dict(plan)
    some_project = plan[0][1]
    results["binding"] = {
        "status_cli": portable(status_command(python, workline_root, some_project), workline_root, some_project),
        "validate_cli": portable(validate_command(python, workline_root, some_project), workline_root, some_project),
        "status_api": "`runpy.run_path(<workline-root>/run-workline.py)[\"activate\"]()`, then "
                      "`workline.status.render_json(workline.status.build_status(<project-root>))`",
        "commands": {
            "cold status": portable(status_command(python, workline_root, some_project), workline_root, some_project),
            "cold validate-project": portable(validate_command(python, workline_root, some_project), workline_root,
                                              some_project),
            "working directory": "<project-root>",
            "component child": portable(child_command(python, "component", "<launcher>", "<out>", "plain", "--",
                                                      STATUS_COMMAND, str(some_project), STATUS_JSON_FLAG),
                                        workline_root, some_project),
            "warm child": portable(child_command(python, "warm", "<launcher>", "<out>", str(some_project), "<calls>"),
                                   workline_root, some_project),
            "Git Trace2": "cold command with GIT_TRACE2_EVENT=<temporary directory outside the Project>",
        },
    }
    checks = 0

    def integrity(where: str, before: dict[str, dict[str, str]]) -> None:
        nonlocal checks
        for scale, project in plan:
            require_unchanged(before[scale], fixture_identity(project), where)
            checks += 1

    baseline = {scale: fixture_identity(project) for scale, project in plan}
    phases = set(args.phases)
    boundary("start")
    if "cold" in phases:
        log(f"cold series: {args.reps} reps x {len(plan)} scales x 2 operations")
        cold = cold_series(plan, workline_root, python, args.reps, references, log)
        for scale in cold:
            results["scales"][scale]["cold"] = cold[scale]
        integrity("cold", baseline)
        boundary("after cold")
    if "warm" in phases:
        for scale, project in plan:
            log(f"warm {scale}: {args.warm_calls} calls")
            results["scales"][scale]["warm"] = warm_series(scale, project, workline_root, python, args.warm_calls,
                                                           run_dir, references[scale])
        integrity("warm", baseline)
        boundary("after warm")
    if "component" in phases:
        for scale, _ in plan:
            results["scales"][scale]["component"] = {op: [] for op in OPERATIONS}
        for index in range(args.component_samples):
            for scale, project in plan:
                for op in OPERATIONS:
                    results["scales"][scale]["component"][op].append(
                        component_run(scale, op, project, workline_root, python, run_dir, references[scale], index))
            log(f"component sample {index + 1}/{args.component_samples} done")
        if args.derivation_samples:
            for scale, _ in plan:
                results["scales"][scale]["component_derivation"] = {op: [] for op in OPERATIONS}
            for index in range(args.derivation_samples):
                for scale, project in plan:
                    for op in OPERATIONS:
                        results["scales"][scale]["component_derivation"][op].append(
                            component_run(scale, op, project, workline_root, python, run_dir, references[scale], index,
                                          derivation=True))
                log(f"derivation-span sample {index + 1}/{args.derivation_samples} done")
        integrity("component", baseline)
        boundary("after component")
    if "sequence" in phases:
        for scale, _ in plan:
            results["scales"][scale]["sequence"] = []
        for index in range(args.sequence_reps):
            for scale, project in plan:
                results["scales"][scale]["sequence"].append(
                    recovery_sequence(scale, project, workline_root, python, run_dir, references[scale], index))
            log(f"recovery sequence {index + 1}/{args.sequence_reps} done")
        integrity("sequence", baseline)
        boundary("after sequence")
    if "trace" in phases:
        for scale, project in plan:
            results["scales"][scale]["trace2"] = {op: trace2_count(scale, op, project, workline_root, python, run_dir)
                                                  for op in OPERATIONS}
        log("trace2 counts done")
        integrity("trace2", baseline)
    if "profile" in phases:
        for scale, project in plan:
            results["scales"][scale]["profile"] = {op: profile_run(scale, op, project, workline_root, python, run_dir)
                                                   for op in OPERATIONS}
            log(f"profile {scale} done")
        integrity("profile", baseline)
    boundary("end")
    if not args.no_quiet_check:
        quiet["after"] = quiet_sample(samples=5, suites_dir=suites)
        problem = quiet_problem(quiet["after"])
        if problem and args.label == "OFFICIAL":
            raise HarnessStop(f"quiet window not quiet at the end: {problem}; this series is discarded")
    results["integrity_checks"] = checks
    results["run_dir"] = run_dir.name
    analysis = analyze(results) if {"cold", "component"} <= phases else {}
    results_path = run_dir / "results.json"
    results_path.write_text(json.dumps(results, indent=1, sort_keys=True, default=str), encoding="utf-8")
    if analysis:
        (run_dir / "analysis.json").write_text(json.dumps(analysis, indent=1, sort_keys=True), encoding="utf-8")
        summary = render_summary(results, analysis)
        problems = public_safety_problems(summary)
        if problems:
            raise HarnessStop(f"the rendered summary is not public-safe: {problems}")
        (run_dir / "summary.md").write_text(summary, encoding="utf-8")
        log(f"decision: {analysis['decision']}")
    log(f"results: {results_path}")
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run.py", description="RB2 BL-007 benchmark runner (Completion Sprint tooling)")
    sub = parser.add_subparsers(dest="command", required=True)
    series = sub.add_parser("series", help="admit fixtures and run the measurement protocol")
    series.add_argument("--workline-root", required=True)
    series.add_argument("--fixtures", required=True)
    series.add_argument("--logs", required=True)
    series.add_argument("--label", choices=("SMOKE", "OFFICIAL"), default="SMOKE")
    series.add_argument("--measured-sha", required=True)
    series.add_argument("--measured-note", help="public-safe one-line status of the measured SHA (e.g. not landed)")
    series.add_argument("--scales", nargs="+", default=["S", "M", "L"])
    series.add_argument("--seed", type=int, default=None)
    series.add_argument("--reps", type=int, default=15)
    series.add_argument("--warm-calls", type=int, default=30)
    series.add_argument("--component-samples", type=int, default=5)
    series.add_argument("--derivation-samples", type=int, default=3)
    series.add_argument("--sequence-reps", type=int, default=5)
    series.add_argument("--phases", nargs="+", default=["cold", "warm", "component", "sequence", "trace", "profile"])
    series.add_argument("--python", nargs="+")
    series.add_argument("--suites-dir")
    series.add_argument("--no-quiet-check", action="store_true")
    render = sub.add_parser("render", help="render a results.json into the public-safe summary")
    render.add_argument("--results", required=True)
    render.add_argument("--out", required=True)
    admission = sub.add_parser("admit", help="generate (when missing) and admit fixtures: validate-project + status once")
    admission.add_argument("--workline-root", required=True)
    admission.add_argument("--fixtures", required=True)
    admission.add_argument("--scales", nargs="+", default=["S", "M", "L"])
    admission.add_argument("--seed", type=int, default=None)
    admission.add_argument("--python", nargs="+")
    args = parser.parse_args(argv)
    try:
        if args.command == "admit":
            seed = load_generator().DEFAULT_SEED if args.seed is None else args.seed
            root = Path(args.workline_root).resolve()
            for scale in args.scales:
                began = _PC()
                fixture = ensure_fixture(Path(args.fixtures).resolve(), scale, root, seed)
                generated = (_PC() - began) / 1e6
                found = admit(fixture, root, python_command(args.python))
                print(json.dumps({"scale": scale, "fixture": fixture.name, "generation_or_reuse_ms": round(generated, 1),
                                  "untimed_wall_ms (ADMISSION, not evidence)": found["untimed_wall_ms"],
                                  "facts": found["facts"], "counts": load_manifest(fixture)["counts"]}, indent=1),
                      flush=True)
            return 0
        if args.command == "series":
            if args.label == "OFFICIAL" and (args.reps < 15 or args.warm_calls < 30):
                raise HarnessStop("an official series needs >= 15 cold samples and >= 30 warm calls per scale (§36.10-11)")
            if args.seed is None:
                args.seed = load_generator().DEFAULT_SEED
            run_series(args)
            return 0
        if args.command == "render":
            results = json.loads(Path(args.results).read_text(encoding="utf-8"))
            analysis = analyze(results)
            summary = render_summary(results, analysis)
            problems = public_safety_problems(summary)
            if problems:
                raise HarnessStop(f"the rendered summary is not public-safe: {problems}")
            Path(args.out).write_text(summary, encoding="utf-8", newline="\n")
            print(analysis["decision"])
            return 0
    except HarnessStop as exc:
        print(f"STOP: {exc}", flush=True)
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
