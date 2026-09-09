from __future__ import annotations

import argparse
from pathlib import Path

from .registry import validate_registry


def main() -> int:
    parser = argparse.ArgumentParser(prog="workline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-registry")
    validate.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()

    if args.command == "validate-registry":
        result = validate_registry(Path(args.root))
        if result.ok:
            print("registry validation: PASS")
            return 0
        for problem in result.problems:
            print(f"{problem.code}: {problem.message}")
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
