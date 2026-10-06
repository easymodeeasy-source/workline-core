"""Shared fixtures for the read-only status tests (RB1 / BL-006).

``ReadOnlyBoundary`` makes the status boundary mechanical: for as long as it is
entered, every callable that could open a mutation, take a lock, write a file,
change Git or reach a network is replaced by one that records the attempt and
fails, every process launched is recorded, and the Project's whole tree - its
``.git`` included - is compared byte for byte before and after.
"""

from __future__ import annotations

import builtins
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from typing import Any, Callable
from unittest import mock

from helpers import WorklineTestCase, git
from workline import ids
from workline.store import Event, ProjectStore, Relation, render_event_line, render_relations

# Git subcommands a local read may run: no fetch / pull / push / ls-remote, and no write of index, ref or config.
READ_ONLY_GIT = frozenset({
    "rev-parse", "symbolic-ref", "status", "log", "ls-files", "ls-tree", "show", "cat-file", "rev-list",
    "merge-base", "diff", "for-each-ref", "check-ignore", "version", "remote", "var",
})
NETWORK_OR_WRITE_GIT = frozenset({
    "fetch", "pull", "push", "ls-remote", "clone", "commit", "add", "rm", "mv", "update-ref", "update-index",
    "write-tree", "commit-tree", "reset", "checkout", "switch", "restore", "merge", "rebase", "cherry-pick",
    "revert", "gc", "maintenance", "init", "stash", "tag", "branch", "notes", "config", "hash-object",
    "replace", "prune", "repack", "fsck", "submodule", "worktree", "apply", "am", "clean", "read-tree",
})
_OPTIONS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--exec-path"})

FORBIDDEN_CALLABLES: tuple[tuple[str, str], ...] = (
    ("workline.mutation", "MutationController.open"),
    ("workline.mutation", "MutationController.begin"),
    ("workline.mutation", "MutationController.load"),
    ("workline.mutation", "MutationController.apply_effect"),
    ("workline.mutation", "Mutation.reserve_id"),
    ("workline.mutation", "Mutation.add_effects"),
    ("workline.mutation", "Mutation.apply"),
    ("workline.mutation", "Mutation.complete"),
    ("workline.mutation", "Mutation.abandon"),
    ("workline.mutation", "Mutation.set_note"),
    ("workline.mutation", "Mutation.extend_scope"),
    ("workline.mutation", "Mutation._save"),
    ("workline.oplock", "project_operation"),
    ("workline.oplock", "note_mutation"),
    ("workline.durable", "durable_write_text"),
    ("workline.gitcmd", "add_paths"),
    ("workline.gitcmd", "commit_only"),
    ("workline.gitcmd", "push"),
    ("workline.gitcmd", "push_dry_run"),
    ("workline.gitcmd", "fetch_destination_branch"),
    ("workline.gitcmd", "destination_branch"),
    ("workline.gitcmd", "reads_itself"),
    ("workline.gitcmd", "init_main"),
    ("workline.gitcmd", "contained_add"),
    ("workline.gitcmd", "contained_commit"),
    ("workline.review.hermetic", "enter"),
    ("workline.work_terminal_activation", "activate_work_terminal_review"),
    ("workline.push_pin", "pin_push_destination"),
    ("workline.bootstrap", "backfill_bootstrap"),
)


def git_subcommand(argv: list[str]) -> tuple[str | None, list[str]]:
    """The git subcommand ``argv`` runs and the arguments after it (global options skipped)."""
    rest = list(argv[1:])
    while rest:
        head = rest.pop(0)
        if head in _OPTIONS_WITH_VALUE:
            if rest:
                rest.pop(0)
            continue
        if head.startswith("-"):
            continue
        return head, rest
    return None, []


def is_git(argv: list[str]) -> bool:
    name = Path(str(argv[0])).name.lower()
    return name in ("git", "git.exe")


class BoundaryViolation(AssertionError):
    pass


def tree_snapshot(root: Path) -> dict[str, tuple[str, str]]:
    """Every entry under ``root`` (``.git`` included): directories by kind, files by their exact bytes."""
    found: dict[str, tuple[str, str]] = {}
    for current, directories, files in os.walk(root, followlinks=False):
        base = Path(current)
        for name in directories:
            path = base / name
            found[path.relative_to(root).as_posix()] = ("link" if path.is_symlink() else "dir", "")
        for name in files:
            path = base / name
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as exc:
                digest = f"unreadable:{exc.errno}"
            found[path.relative_to(root).as_posix()] = ("file", digest)
    return found


class ReadOnlyBoundary:
    """Enter around a status call: every forbidden callable fails loudly, and every process is recorded."""

    def __init__(self, *roots: Path) -> None:
        self.roots = [Path(root).resolve() for root in roots]
        self.violations: list[str] = []
        self.commands: list[list[str]] = []
        self.paths_written: list[str] = []
        self._stack = ExitStack()
        self._before: dict[Path, dict[str, tuple[str, str]]] = {}

    # ---------------------------------------------------------------- patching
    def _forbid(self, owner: Any, name: str, label: str) -> None:
        def refuse(*_args: Any, **_kwargs: Any) -> Any:
            self.violations.append(label)
            raise BoundaryViolation(f"status called {label}")

        self._stack.enter_context(mock.patch.object(owner, name, refuse))

    def _inside(self, path: Any) -> bool:
        try:
            target = Path(os.fspath(path)).resolve()
        except (TypeError, ValueError, OSError):
            return False
        return any(target == root or root in target.parents for root in self.roots)

    def _watch_write(self, owner: Any, name: str, label: str, *, path_arg: int = 0, self_is_path: bool = False) -> None:
        original = getattr(owner, name)
        boundary = self

        def watched(*args: Any, **kwargs: Any) -> Any:
            target = args[0] if self_is_path else (args[path_arg] if len(args) > path_arg else None)
            if target is not None and boundary._inside(target):
                boundary.paths_written.append(f"{label} {target}")
                raise BoundaryViolation(f"status wrote through {label} at {target}")
            return original(*args, **kwargs)

        self._stack.enter_context(mock.patch.object(owner, name, watched))

    def __enter__(self) -> "ReadOnlyBoundary":
        for root in self.roots:
            self._before[root] = tree_snapshot(root)
        import importlib

        for module_name, dotted in FORBIDDEN_CALLABLES:
            module = importlib.import_module(module_name)
            owner: Any = module
            parts = dotted.split(".")
            for part in parts[:-1]:
                owner = getattr(owner, part)
            self._forbid(owner, parts[-1], f"{module_name}.{dotted}")
        # The same callables imported by name into any other loaded workline module.
        for name in ("project_operation", "durable_write_text", "pin_push_destination", "backfill_bootstrap",
                     "activate_work_terminal_review"):
            for module_name, module in list(sys.modules.items()):
                if module is None or not module_name.startswith("workline"):
                    continue
                if module_name in ("workline.oplock", "workline.durable") or not hasattr(module, name):
                    continue
                if callable(getattr(module, name)):
                    self._forbid(module, name, f"{module_name}.{name}")
        boundary = self
        real_popen = subprocess.Popen

        class RecordingPopen(real_popen):  # type: ignore[misc, valid-type]
            def __init__(self, args: Any, *rest: Any, **kwargs: Any) -> None:
                argv = [str(part) for part in (args if isinstance(args, (list, tuple)) else [args])]
                boundary.commands.append(argv)
                if not is_git(argv):
                    boundary.violations.append(f"process {argv[0]}")
                    raise BoundaryViolation(f"status launched a process that is not git: {argv}")
                subcommand, after = git_subcommand(argv)
                if subcommand in NETWORK_OR_WRITE_GIT or subcommand not in READ_ONLY_GIT:
                    boundary.violations.append(f"git {subcommand}")
                    raise BoundaryViolation(f"status ran git {subcommand}: {argv}")
                if subcommand == "remote" and after and after[0] not in ("get-url",):
                    boundary.violations.append(f"git remote {after[0]}")
                    raise BoundaryViolation(f"status ran git remote {after[0]}: {argv}")
                super().__init__(args, *rest, **kwargs)

        self._stack.enter_context(mock.patch.object(subprocess, "Popen", RecordingPopen))
        for name in ("system", "startfile"):
            if hasattr(os, name):
                self._forbid(os, name, f"os.{name}")

        def no_network(*_args: Any, **_kwargs: Any) -> Any:
            self.violations.append("network")
            raise BoundaryViolation("status opened a network connection")

        self._stack.enter_context(mock.patch.object(socket.socket, "connect", no_network))
        self._stack.enter_context(mock.patch.object(socket, "create_connection", no_network))
        for owner, name in ((Path, "write_text"), (Path, "write_bytes"), (Path, "mkdir"), (Path, "unlink"),
                            (Path, "rmdir"), (Path, "rename"), (Path, "replace"), (Path, "touch"), (Path, "symlink_to")):
            self._watch_write(owner, name, f"Path.{name}", self_is_path=True)
        for owner, name in ((os, "mkdir"), (os, "makedirs"), (os, "remove"), (os, "unlink"), (os, "rmdir"),
                            (os, "rename"), (os, "replace"), (shutil, "rmtree"), (shutil, "move")):
            self._watch_write(owner, name, f"{owner.__name__}.{name}")
        for owner, name in ((os, "rename"), (os, "replace"), (shutil, "copy"), (shutil, "copy2"), (shutil, "copyfile"),
                            (shutil, "move")):
            self._watch_write(owner, name, f"{owner.__name__}.{name} (destination)", path_arg=1)
        real_open = builtins.open

        def guarded_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if any(flag in mode for flag in ("w", "a", "x", "+")) and boundary._inside(file):
                boundary.paths_written.append(f"open({mode}) {file}")
                raise BoundaryViolation(f"status opened {file} for writing")
            return real_open(file, mode, *args, **kwargs)

        self._stack.enter_context(mock.patch.object(builtins, "open", guarded_open))
        real_os_open = os.open

        def guarded_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> Any:
            writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC)
            if writing and boundary._inside(path):
                boundary.paths_written.append(f"os.open {path}")
                raise BoundaryViolation(f"status opened {path} for writing")
            return real_os_open(path, flags, *args, **kwargs)

        self._stack.enter_context(mock.patch.object(os, "open", guarded_os_open))
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self._stack.close()

    # ---------------------------------------------------------------- verdict
    def changed(self) -> dict[str, list[str]]:
        report: dict[str, list[str]] = {}
        for root, before in self._before.items():
            after = tree_snapshot(root)
            differing = sorted(
                path for path in set(before) | set(after) if before.get(path) != after.get(path)
            )
            if differing:
                report[str(root)] = differing
        return report

    def git_subcommands(self) -> set[str]:
        return {git_subcommand(argv)[0] or "" for argv in self.commands if is_git(argv)}


# --------------------------------------------------------------------------- canonical fixtures


def append_events(store: ProjectStore, *pairs: tuple[str, str]) -> list[str]:
    """Append lifecycle events ``(type, entity)`` straight to the event log (a fixture, not an operation)."""
    lines = []
    identifiers = []
    for kind, entity in pairs:
        identifier = ids.new_id("event")
        identifiers.append(identifier)
        lines.append(render_event_line(Event(identifier, kind, entity, "2026-10-03T00:00:00+00:00")) + "\n")
    with open(store.events_jsonl, "a", encoding="utf-8", newline="") as handle:
        handle.write("".join(lines))
    return identifiers


def add_roadmap_relation(store: ProjectStore, rel_type: str, from_id: str, to: str) -> str:
    """Append one relation to ``roadmap.yaml`` (a fixture, not an operation)."""
    relations = store.read_roadmap_relations()
    identifier = ids.new_id("relation")
    relations.append(Relation(identifier, rel_type, from_id, to))
    store.roadmap_yaml.write_text(render_relations(relations), encoding="utf-8", newline="")
    return identifier


def status_json(root: Path) -> dict[str, Any]:
    from workline.status import build_status, render_json

    return json.loads(render_json(build_status(root)))


class StatusCase(WorklineTestCase):
    """A WorklineTestCase with the status model at hand."""

    def model(self, root: Path | None = None):
        from workline.status import build_status

        return build_status(root or self.store.root)

    def data(self, root: Path | None = None) -> dict[str, Any]:
        return status_json(root or self.store.root)

    def assertReadOnly(self, call: Callable[[], Any], *roots: Path) -> Any:
        with ReadOnlyBoundary(*(roots or (self.store.root,))) as boundary:
            result = call()
        self.assertEqual(boundary.violations, [], boundary.violations)
        self.assertEqual(boundary.paths_written, [], boundary.paths_written)
        self.assertEqual(boundary.changed(), {}, "status changed bytes under the Project")
        return result, boundary


__all__ = [
    "BoundaryViolation",
    "NETWORK_OR_WRITE_GIT",
    "READ_ONLY_GIT",
    "ReadOnlyBoundary",
    "StatusCase",
    "add_roadmap_relation",
    "append_events",
    "git",
    "git_subcommand",
    "status_json",
    "tree_snapshot",
]
