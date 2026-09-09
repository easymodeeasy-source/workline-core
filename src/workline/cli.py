from __future__ import annotations

import argparse
from pathlib import Path

from .create import RelatedSpec, WorkSpec, create_standalone_work
from .errors import StopError
from .project_start import project_start
from .registry import validate_registry
from .store import ProjectStore
from .validate import validate_project


def _related(items: list[str] | None, rel_type: str) -> list[RelatedSpec]:
    return [RelatedSpec(rel_type, target) for target in (items or [])]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="workline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-registry", help="validate a Workline root registry")
    validate.add_argument("root", nargs="?", default=".")

    start = subparsers.add_parser("project-start", help="initialize a folder as a Workline Project")
    start.add_argument("project_root")
    start.add_argument("--workline-root", required=True)

    check = subparsers.add_parser("validate-project", help="validate a Project's canonical structure")
    check.add_argument("project_root", nargs="?", default=".")

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
            result = project_start(Path(args.project_root), Path(args.workline_root))
            print(f"project-start: {result.status} ({result.project_root}) head={result.head}")
            return 0

        if args.command == "validate-project":
            problems = validate_project(ProjectStore(Path(args.project_root)))
            if not problems:
                print("project validation: PASS")
                return 0
            for problem in problems:
                print(f"{problem.code}: {problem.message}")
            return 1

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
