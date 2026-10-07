from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import root_maintenance
from .bootstrap import backfill_bootstrap
from .create import RelatedSpec, WorkSpec, create_standalone_work
from .errors import StopError
from .implementation import require_configured_implementation, running_workline_root
from .project_start import project_start
from .push_pin import pin_push_destination
from .pushurl import redact
from .recovery_disposition import dispose_recovery
from .registry import validate_registry
from .status import build_status, render_human, render_json
from .store import ProjectStore
from .validate import validate_project
from .work_terminal_activation import activate_work_terminal_review


#: The one CLI command that is not bound to the Workline root of the Project it is started from: it reads any
#: Project, from anywhere, and changes nothing (``rules/git``: Read-only status).
READ_ONLY_STATUS_COMMAND = "status"


def binds_invocation_project(argv: list[str]) -> bool:
    """Whether the launcher binds this invocation to the configured Workline root of the caller's Project.

    Every command is bound, except exactly ``status`` given as the command: its
    parser has no option or subcommand that writes, so no mutation-capable
    command can be selected through this exception. Anything else - another
    command, an unknown one, no command, or ``status`` not in the command
    position - stays bound.
    """
    return not (len(argv) > 0 and argv[0] == READ_ONLY_STATUS_COMMAND)


#: P7 root policy maintenance (§31.12). Both are BOUND like every command but ``status``
#: (:func:`binds_invocation_project` is unchanged): inside a Project configured to another Workline root the
#: launcher refuses them before anything is imported; their target is always the launcher's own root, never a
#: caller Project's configured root, and the mutation-capable one also refuses inside any Project (RB7C-6).
ROOT_STATUS_COMMAND = "root-policy-maintenance-status"
ROOT_AUTHORIZE_COMMAND = "root-policy-maintenance-authorize"


def _launcher_root() -> Path:
    """The Workline root this process runs the implementation of: the only root its root commands touch."""
    found = running_workline_root()
    if found is None:
        raise StopError(
            "the Workline root whose implementation this process runs cannot be proven; nothing was read or written",
            code="workline_implementation_unavailable",
        )
    return found


def _render_root_status(report: dict) -> str:
    """The human rendering of :func:`root_maintenance.status_report` (the same model; never a locator)."""
    found = report["global_policy"]
    authorization = report["authorization"]
    pending = report["pending_mutation"]
    lines = [
        f"global policy: {found['source_mode']} v{found['version']} {found['digest']}",
        f"current change: {report['current_change_id'] or 'none'}",
        f"evaluations: {', '.join(report['evaluation_ids']) or 'none'}",
        "authorization: " + authorization["status"] + (
            f" (remote {authorization['remote']}, branch {authorization['branch']})"
            if authorization.get("remote") else ""),
        "pending root mutation: " + ("none" if pending is None else
                                     f"{pending['mutation_id']} {pending['operation']} {pending['status']}"
                                     + (f" at {pending['stage']}" if pending.get("stage") else "")),
        f"next-boundary adapter: {report['next_boundary_adapter_identity']}",
    ]
    return "\n".join(lines) + "\n"


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

    activation = subparsers.add_parser(
        "activate-work-terminal-review",
        help="activate review-v1 Work terminalization for an established Workline Project "
        "(per Project, one-time, human-confirmed; review-v1 stays a per-invocation START opt-in)",
    )
    activation.add_argument("project_root", nargs="?", default=".")
    activation.add_argument(
        "--confirm",
        action="store_true",
        help="state that a human has confirmed this Project-specific Workline rule change (required)",
    )

    disposition = subparsers.add_parser(
        "dispose-recovery",
        help="set one pending mutation or Review Run aside from automatic recovery by explicit Human disposition "
        "(human-confirmed maintenance; the old state stays as evidence and nothing is deleted or completed)",
    )
    disposition.add_argument("project_root", nargs="?", default=".")
    disposition.add_argument(
        "--target", required=True, help="the exact stable ID of the pending mutation (mut_...) or Review Run (rr_...)"
    )
    disposition.add_argument(
        "--reason",
        required=True,
        help="why it is set aside: one line, committed as canonical Project data - keep it public-safe, with no "
        "secret or private raw material",
    )
    disposition.add_argument(
        "--confirm",
        action="store_true",
        help="state that a human has decided this target must no longer be considered for automatic resume (required)",
    )

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
    create.add_argument("--source-finding-id")

    status = subparsers.add_parser(
        READ_ONLY_STATUS_COMMAND,
        help="report the read-only status of a Workline Project (any Project, from anywhere; writes nothing)",
    )
    status.add_argument("project_root")
    status.add_argument("--json", action="store_true", help="print the versioned machine-readable status model")

    # P7 (§31.12, RB7C-6): Workline-root policy maintenance of THIS launcher's own Workline root - never a Project.
    root_status = subparsers.add_parser(
        ROOT_STATUS_COMMAND,
        help="report the read-only policy maintenance status of this launcher's Workline root "
        "(no lock, no write, no remote contact, no repair; the push locator is never shown)",
    )
    root_status.add_argument("--json", action="store_true", help="print the machine-readable report")
    root_authorize = subparsers.add_parser(
        ROOT_AUTHORIZE_COMMAND,
        help="record the Human-approved root publication authorization of this launcher's Workline root "
        "(run from the Workline root, never from inside a Workline Project)",
    )
    root_authorize.add_argument("--remote", required=True, help="the remote name, exactly as configured")
    root_authorize.add_argument("--branch", required=True, help="the exact full destination branch ref (refs/heads/...)")
    root_authorize.add_argument("--locator", required=True, help="the exact active push locator you approve")

    args = parser.parse_args(argv)

    if args.command == READ_ONLY_STATUS_COMMAND:
        # A diagnostic: every condition the Project is in is a field of the model, never a failed command.
        model = build_status(Path(args.project_root))
        sys.stdout.write(render_json(model) if args.json else render_human(model))
        sys.stdout.flush()
        return 0

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

        if args.command == "activate-work-terminal-review":
            result = activate_work_terminal_review(Path(args.project_root), confirmed=args.confirm)
            print(
                f"activate-work-terminal-review: {result.status} ({result.project_root}) "
                f"legacy_event_count={result.legacy_event_count} activation_base_head={result.activation_base_head} "
                f"head={result.head} pushed={result.pushed}"
            )
            return 0

        if args.command == "dispose-recovery":
            result = dispose_recovery(Path(args.project_root), args.target, args.reason, confirmed=args.confirm)
            print(
                f"dispose-recovery: {result.status} ({result.project_root}) {result.target_kind} {result.target_id} "
                f"target_state_digest={result.target_state_digest} record={result.path} head={result.head} "
                f"pushed={result.pushed}"
            )
            return 0

        if args.command == "validate-project":
            store = ProjectStore(Path(args.project_root))
            _require_project_implementation(store)
            problems = validate_project(store)
            # RB6A-IR-1 (§30.30, §30.28): the BL-055 shadow-authority diagnostic is advisory - shown after the
            # verdict and only when it has something to say; never a Problem, never a change to PASS / FAIL or the
            # exit code. ``validate.py`` stays free of it (it never imports the detector).
            from .shadow_authority import detect_shadow_authority

            diagnostic = detect_shadow_authority(store)
            advisory = diagnostic.render_lines() if (diagnostic.evidence or diagnostic.uninspected) else []
            if not problems:
                print("project validation: PASS")
                for line in advisory:
                    print(line)
                return 0
            for problem in problems:
                print(f"{problem.code}: {problem.message}")
            for line in advisory:
                print(line)
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
            if args.source_finding_id is None:
                result = create_standalone_work(ProjectStore(Path(args.project_root)), spec)
            else:
                # explicit future-Work provenance (P5 GAP-D): one future_work_link in the CREATE commit
                result = create_standalone_work(
                    ProjectStore(Path(args.project_root)), spec, source_finding_id=args.source_finding_id
                )
            print(f"create-work: {result.work_id} head={result.head}")
            return 0

        if args.command == ROOT_STATUS_COMMAND:
            report = root_maintenance.status_report(_launcher_root())
            sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n" if args.json
                             else _render_root_status(report))
            sys.stdout.flush()
            return 0

        if args.command == ROOT_AUTHORIZE_COMMAND:
            found = root_maintenance.authorize(_launcher_root(), remote=args.remote, branch=args.branch,
                                               locator=args.locator)
            print(f"{ROOT_AUTHORIZE_COMMAND}: remote={found.remote} branch={found.branch} "
                  f"locator={redact(found.locator)}")
            return 0
    except StopError as exc:
        print(f"STOP [{exc.code}]: {exc.message}")
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
