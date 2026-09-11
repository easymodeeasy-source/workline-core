from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .bootstrap import backfill_bootstrap
from .create import RelatedSpec, WorkSpec, create_standalone_work
from .errors import StopError
from .implementation import require_configured_implementation
from .project_start import project_start
from .push_pin import pin_push_destination
from .registry import validate_registry
from .store import ProjectStore
from .validate import validate_project


def _related(items: list[str] | None, rel_type: str) -> list[RelatedSpec]:
    return [RelatedSpec(rel_type, target) for target in (items or [])]


def _require_project_implementation(store: ProjectStore) -> None:
    """A Project's canonical validation never PASSes under another Workline implementation.

    A project.yaml without a readable Workline root cannot PASS either; its
    validation reports that problem itself.
    """
    try:
        configured_root = store.workline_root()
    except StopError:
        return
    require_configured_implementation(configured_root)


def _tolerant_output() -> None:
    """Never let an unencodable character turn a STOP report into a traceback.

    Console encodings differ (cp932, cp1252, ...); a message the operator needs
    to read must survive one that cannot represent every character in it.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except (OSError, ValueError):
                pass


def main(argv: list[str] | None = None) -> int:
    _tolerant_output()
    parser = argparse.ArgumentParser(prog="workline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-registry", help="validate a Workline root registry")
    validate.add_argument("root", nargs="?", default=".")

    start = subparsers.add_parser("project-start", help="initialize a folder as a Workline Project")
    start.add_argument("project_root")
    start.add_argument("--workline-root", required=True)
    start.add_argument(
        "--expected-push-url",
        help="the push destination you approve for this Project; pinned only when the remote already resolves to it",
    )
    start.add_argument("--push-remote", default="origin")

    pin = subparsers.add_parser(
        "pin-push-destination",
        help="approve the push destination of an established Workline Project (human-confirmed, idempotent)",
    )
    pin.add_argument("project_root", nargs="?", default=".")
    pin.add_argument("--url", action="append", required=True, help="approved push destination (repeatable)")
    pin.add_argument("--remote", default="origin")

    check = subparsers.add_parser("validate-project", help="validate a Project's canonical structure")
    check.add_argument("project_root", nargs="?", default=".")

    backfill = subparsers.add_parser(
        "backfill-bootstrap",
        help="add the Project-side bootstrap Skill to an established Workline Project (idempotent)",
    )
    backfill.add_argument("project_root", nargs="?", default=".")

    create = subparsers.add_parser("create-work", help="create a standalone Work (direct CREATE invocation)")
    create.add_argument("project_root")
    create.add_argument("--name", required=True)
    create.add_argument("--desired-state", required=True)
    create.add_argument("--must-read", action="append")
    create.add_argument("--obey", action="append")
    create.add_argument("--realizes", action="append")
    create.add_argument("--must-update", action="append")

    args = parser.parse_args(argv)

    try:
        if args.command == "validate-registry":
            result = validate_registry(Path(args.root))
            if result.ok:
                print("registry validation: PASS")
                return 0
            for problem in result.problems:
                print(f"{problem.code}: {problem.message}")
            return 1

        if args.command == "project-start":
            result = project_start(
                Path(args.project_root),
                Path(args.workline_root),
                expected_push_url=args.expected_push_url,
                push_remote=args.push_remote,
            )
            print(f"project-start: {result.status} ({result.project_root}) head={result.head}")
            if result.pinned_url:
                print(f"push destination: {result.pinned_url}")
            elif result.unpinned_remotes:
                print(
                    "push destination: unpinned (remotes: "
                    + ", ".join(result.unpinned_remotes)
                    + "); pin it with `workline pin-push-destination` before any operation that pushes"
                )
            return 0

        if args.command == "pin-push-destination":
            result = pin_push_destination(Path(args.project_root), args.url, remote=args.remote)
            print(
                f"pin-push-destination: {result.status} ({result.project_root}) "
                f"{result.remote} -> {result.url} head={result.head} pushed={result.pushed}"
            )
            return 0

        if args.command == "validate-project":
            store = ProjectStore(Path(args.project_root))
            _require_project_implementation(store)
            problems = validate_project(store)
            if not problems:
                print("project validation: PASS")
                return 0
            for problem in problems:
                print(f"{problem.code}: {problem.message}")
            return 1

        if args.command == "backfill-bootstrap":
            result = backfill_bootstrap(Path(args.project_root))
            print(
                f"backfill-bootstrap: {result.status} ({result.project_root}) "
                f"head={result.head} pushed={result.pushed}"
            )
            return 0

        if args.command == "create-work":
            related = (
                _related(args.must_read, "must_read")
                + _related(args.obey, "obey")
                + _related(args.realizes, "realizes")
                + _related(args.must_update, "must_update")
            )
            spec = WorkSpec(args.name, args.desired_state, related=tuple(related))
            result = create_standalone_work(ProjectStore(Path(args.project_root)), spec)
            print(f"create-work: {result.work_id} head={result.head}")
            return 0
    except StopError as exc:
        print(f"STOP [{exc.code}]: {exc.message}")
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
