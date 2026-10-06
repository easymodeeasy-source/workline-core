"""RB2 benchmark fixture generator (Completion Sprint tooling and evidence only).

Builds one deterministic, disposable Workline Project for a BL-007 cold-start
recovery measurement (``WORKLINE_COMPLETION_SPRINT.md`` §36.5-§36.9). It is not
Workline runtime authority: no runtime code, status, validation or routing reads
anything it writes, and nothing here is a Workline mutation path.

Every canonical file is produced by the landed canonical renderers of the
measured Workline root - ``store.render_entity`` / ``render_body`` /
``render_relations`` / ``render_event_line`` / ``render_project_yaml``,
``bootstrap.render_bootstrap``, the Review record constructors
(``records.GateGeneration`` / ``records.Receipt``) with ``ReviewStore.render``,
and the recovery-record shape of ``MutationController.begin`` dumped by
``yamlish.dump``. No field is invented. Identities are valid Workline IDs
derived from the generator contract and seed - never ``new_id()`` - and every
timestamp is synthetic, so one seed and scale always produce the same logical
fixture. The fixture is admitted to measurement only after the landed
``validate-project`` passes on it (``run.py``).

Fixture layout (``<target>`` must not exist yet, or be an empty directory)::

    <target>/project/        the Workline Project (local Git repository, no remote)
    <target>/manifest.json   counts, digests and Git identity (outside the Project)

Usage::

    py -3 -B benchmarks/rb2/generate.py --workline-root <R> --scale S --target <dir> [--seed N]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

GENERATOR_CONTRACT = "workline-rb2-fixture"
GENERATOR_VERSION = 1
DEFAULT_SEED = 7007  # BL-007

#: scale -> (Works, Works per Phase). ``T`` is the reduced test scale (§36.29); S/M/L follow §36.6.
SCALES: dict[str, tuple[int, int]] = {
    "T": (12, 4),
    "S": (30, 10),
    "M": (300, 10),
    "L": (3000, 10),
}
#: The Event target is ten Events per Work (§36.6: ~30/300, ~300/3,000, ~3,000/30,000).
EVENTS_PER_WORK = 10

WORKLINE_ROOT_PLACEHOLDER = "<workline-root>"
PROJECT_ROOT_PLACEHOLDER = "<project-root>"
PROJECT_DIR = "project"
MANIFEST = "manifest.json"

#: Synthetic, fixed Git identity and dates: the fixture commit is reproducible for the same bytes.
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "workline-rb2-benchmark",
    "GIT_AUTHOR_EMAIL": "rb2-benchmark@example.invalid",
    "GIT_COMMITTER_NAME": "workline-rb2-benchmark",
    "GIT_COMMITTER_EMAIL": "rb2-benchmark@example.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
}
FIXTURE_COMMIT_MESSAGE = "workline rb2 benchmark fixture"
#: Setup-only Git options (never used by a measured invocation): no hooks, no signing, bytes as written.
_SETUP_GIT_OPTIONS = ("-c", "core.autocrlf=false", "-c", "core.safecrlf=false", "-c", "commit.gpgsign=false")

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)
_BASE_MS = int(_BASE_TIME.timestamp() * 1000)
#: The push destination the representative pending pin record names. ``.invalid`` never resolves, and no
#: measured path contacts it: the benchmark Project has no remote, so the owner probe stops before any locator.
PENDING_PIN_URL = "https://example.invalid/workline-rb2/benchmark.git"


class GeneratorError(Exception):
    """The generator refuses: nothing outside the disposable target was touched."""


# --------------------------------------------------------------------------- workline binding


def load_workline(workline_root: Path) -> Any:
    """The ``workline`` package of ``workline_root`` (imported from ``<root>/src``), proven by origin.

    Fixture setup is benchmark tooling, not a Workline invocation: it imports the
    measured root's canonical renderers directly, and refuses a ``workline``
    loaded from anywhere else (an editable install of another checkout).
    """
    root = Path(workline_root).resolve()
    source = root / "src"
    expected = (source / "workline").resolve()
    if "workline" not in sys.modules:
        if str(source) not in sys.path:
            sys.path.insert(0, str(source))
    import workline  # noqa: PLC0415

    found = Path(workline.__file__).resolve().parent
    if found != expected:
        raise GeneratorError(
            f"the loaded workline package is not the measured root's (loaded {found.name} from another checkout)"
        )
    return workline


# --------------------------------------------------------------------------- deterministic identity


def _crockford(value: int) -> str:
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


class IdSource:
    """Valid Workline IDs in the ULID layout, derived only from the contract, the seed and an order counter."""

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.counter = 0

    def next(self, prefix: str, label: str) -> str:
        self.counter += 1
        material = f"{GENERATOR_CONTRACT}/{GENERATOR_VERSION}:{self.seed}:{prefix}:{label}:{self.counter}"
        random80 = int(hashlib.sha256(material.encode("ascii")).hexdigest()[:20], 16)
        value = ((_BASE_MS + self.counter) & ((1 << 48) - 1)) << 80 | random80
        return f"{prefix}_{_crockford(value)}"


def _at(second: int) -> str:
    return (_BASE_TIME + timedelta(seconds=second)).isoformat(timespec="seconds")


def _digest_of(seed: int, label: str) -> str:
    return hashlib.sha256(f"{GENERATOR_CONTRACT}:{seed}:{label}".encode("ascii")).hexdigest()


# --------------------------------------------------------------------------- the logical plan


@dataclass
class WorkPlan:
    id: str
    display: str
    name: str
    phase_id: str
    roadmap_id: str
    integration: bool
    events: list[str] = field(default_factory=list)  # lifecycle event types, in order


@dataclass
class PhasePlan:
    id: str
    display: str
    name: str
    roadmap_id: str
    group: str  # historical | done | current | future
    works: list[WorkPlan] = field(default_factory=list)


@dataclass
class Plan:
    scale: str
    seed: int
    roadmaps: list[tuple[str, str, str, bool]]  # (id, display, name, achieved)
    phases: list[PhasePlan]
    relations: list[tuple[str, str, str, str]]  # (id, type, from, to)
    related: list[tuple[str, str, str, str, dict[str, Any]]]  # (id, type, from, to, extra)
    events: list[tuple[str, str, str, str]]  # (id, type, entity, at)
    current_work_id: str
    review: dict[str, str]
    pending_mutation_id: str

    @property
    def works(self) -> list[WorkPlan]:
        return [work for phase in self.phases for work in phase.works]


def phase_groups(phase_count: int) -> tuple[int, int, int, int]:
    """(historical, done, current, future) Phase counts: a finished Roadmap, then one active one."""
    historical = max(1, phase_count * 4 // 10)
    done = phase_count * 3 // 10
    future = phase_count - historical - done - 1
    if future < 1:
        raise GeneratorError(f"{phase_count} Phases leave no unstarted Phase")
    return historical, done, 1, future


def build_plan(scale: str, seed: int = DEFAULT_SEED) -> Plan:
    """The logical fixture for ``scale`` and ``seed``: entities, relations and an Event history, in order."""
    if scale not in SCALES:
        raise GeneratorError(f"unknown scale {scale!r}; known: {', '.join(SCALES)}")
    work_count, per_phase = SCALES[scale]
    if work_count % per_phase:
        raise GeneratorError(f"scale {scale}: {work_count} Works do not fill whole Phases of {per_phase}")
    ids = IdSource(seed)
    phase_count = work_count // per_phase
    historical, done, _current, _future = phase_groups(phase_count)

    finished_roadmap = ids.next("r", "roadmap")
    active_roadmap = ids.next("r", "roadmap")
    roadmaps = [
        (finished_roadmap, "R-01", "Benchmark Roadmap (finished)", True),
        (active_roadmap, "R-02", "Benchmark Roadmap (active)", False),
    ]
    phases: list[PhasePlan] = []
    work_number = 0
    for index in range(phase_count):
        if index < historical:
            group, roadmap_id = "historical", finished_roadmap
        elif index < historical + done:
            group, roadmap_id = "done", active_roadmap
        elif index == historical + done:
            group, roadmap_id = "current", active_roadmap
        else:
            group, roadmap_id = "future", active_roadmap
        phase = PhasePlan(ids.next("p", "phase"), f"P-{index + 1:02d}", f"Benchmark Phase {index + 1}", roadmap_id, group)
        for slot in range(per_phase):
            work_number += 1
            integration = slot == per_phase - 1
            name = f"Integration of P-{index + 1:02d}" if integration else f"Benchmark Work {work_number}"
            phase.works.append(
                WorkPlan(ids.next("w", "work"), f"W-{work_number:02d}", name, phase.id, roadmap_id, integration)
            )
        phases.append(phase)

    # roadmap relations: the planned order and dependency between consecutive Phases of one Roadmap, and inside
    # each Phase the shape Phase entry registers (planned_next among normal Works, requires_completion of every
    # normal Work -> the integration check).
    relations: list[tuple[str, str, str, str]] = []
    for roadmap_id, *_rest in roadmaps:
        members = [phase for phase in phases if phase.roadmap_id == roadmap_id]
        for first, second in zip(members, members[1:]):
            relations.append((ids.next("rel", "relation"), "planned_next", first.id, second.id))
            relations.append((ids.next("rel", "relation"), "requires_completion", first.id, second.id))
    for phase in phases:
        normal = [work for work in phase.works if not work.integration]
        integration = phase.works[-1]
        for first, second in zip(normal, normal[1:]):
            relations.append((ids.next("rel", "relation"), "planned_next", first.id, second.id))
        for work in normal:
            relations.append((ids.next("rel", "relation"), "requires_completion", work.id, integration.id))

    # Related records: one per Work (rotating types), and a conditional one on every fifth Work.
    rotating = ("must_read", "obey", "realizes", "must_update")
    related: list[tuple[str, str, str, str, dict[str, Any]]] = []
    for number, work in enumerate((w for phase in phases for w in phase.works), start=1):
        rel_type = rotating[number % len(rotating)]
        related.append((ids.next("rel", "related"), rel_type, work.id, f"docs/topic-{number % 17:02d}.md", {}))
        if number % 5 == 0:
            related.append((
                ids.next("rel", "related"), "conditional_must_read", work.id, f"docs/module-{number % 7}.md",
                {"condition": {"kind": "path_glob", "pattern": f"src/module_{number % 7}/*.py"}},
            ))

    # lifecycle: finished Phases complete, the current Phase half done with one Work in flight, the rest unstarted.
    completed: list[WorkPlan] = []
    current_work: WorkPlan | None = None
    for phase in phases:
        if phase.group in ("historical", "done"):
            completed.extend(phase.works)
        elif phase.group == "current":
            normal = [work for work in phase.works if not work.integration]
            finished = (len(normal) - 1) // 2
            completed.extend(normal[:finished])
            current_work = normal[finished]
    assert current_work is not None
    target = EVENTS_PER_WORK * work_count
    fixed = 1 + 2  # roadmap_achieved; the in-flight Work's work_started + work_target_added
    pairs = max(0, target - fixed - 3 * len(completed)) // 2
    for index, work in enumerate(completed):
        extra = pairs // len(completed) + (1 if index < pairs % len(completed) else 0)
        history = ["work_started", "work_target_added"]
        for cycle in range(extra):
            history += ["work_held", "work_resumed"] if cycle % 2 == 0 else ["work_target_removed", "work_target_added"]
        history.append("work_completed")
        work.events = history
    current_work.events = ["work_started", "work_target_added"]

    events: list[tuple[str, str, str, str]] = []
    second = 0

    def emit(event_type: str, entity: str) -> None:
        nonlocal second
        second += 1
        events.append((ids.next("evt", "event"), event_type, entity, _at(second)))

    achieved = False
    for phase in phases:
        if phase.group != "historical" and not achieved:
            emit("roadmap_achieved", finished_roadmap)  # the finished Roadmap closes before the active one runs
            achieved = True
        for work in phase.works:
            if work is current_work:
                continue
            for event_type in work.events:
                emit(event_type, work.id)
    for event_type in current_work.events:
        emit(event_type, current_work.id)

    review = {
        "review_run_id": ids.next("rr", "review-run"),
        "receipt_id": ids.next("rcp", "review-receipt"),
    }
    pending_mutation_id = ids.next("mut", "pending-mutation")
    return Plan(scale, seed, roadmaps, phases, relations, related, events, current_work.id, review, pending_mutation_id)


# --------------------------------------------------------------------------- rendering


def render_files(plan: Plan, wl: Any, workline_root_text: str) -> dict[str, bytes]:
    """Every committed file of the fixture, by the canonical renderers, as exact bytes (LF line ends)."""
    from workline import bootstrap, store  # noqa: PLC0415
    from workline.review import paths, records  # noqa: PLC0415
    from workline.review.store import ReviewStore  # noqa: PLC0415

    files: dict[str, str] = {}
    files[store.PROJECT_YAML_REL] = store.render_project_yaml(Path(workline_root_text))
    files[store.BOOTSTRAP_REL_PATH] = bootstrap.render_bootstrap()
    for roadmap_id, display, name, _achieved in plan.roadmaps:
        sections = [
            (store.ROADMAP_BACKGROUND_HEADING, "RB2 benchmark fixture background."),
            (store.ROADMAP_DESIRED_HEADING, f"{name}: every planned Phase is complete."),
        ]
        meta = {"id": roadmap_id, "display": display, "type": "roadmap"}
        files[store.ProjectStore.entity_rel_path("roadmap", roadmap_id)] = store.render_entity(
            meta, store.render_body(name, sections)
        )
    for phase in plan.phases:
        meta = {"id": phase.id, "display": phase.display, "type": "phase", "roadmap_id": phase.roadmap_id}
        body = store.render_body(phase.name, [(store.PHASE_DESIRED_HEADING, f"{phase.name} is integrated.")])
        files[store.ProjectStore.entity_rel_path("phase", phase.id)] = store.render_entity(meta, body)
        for work in phase.works:
            meta = {
                "id": work.id,
                "display": work.display,
                "type": "work",
                "phase_id": work.phase_id,
                "origin": {"type": "roadmap", "roadmap_id": work.roadmap_id, "phase_id": work.phase_id},
            }
            if work.integration:
                meta["work_kind"] = "phase_integration_check"
            body = store.render_body(work.name, [(store.WORK_DESIRED_HEADING, f"{work.name} holds.")])
            files[store.ProjectStore.entity_rel_path("work", work.id)] = store.render_entity(meta, body)
    files[f"{store.WORKLINE_DIR}/relations/roadmap.yaml"] = store.render_relations(
        [store.Relation(rid, rtype, src, dst) for rid, rtype, src, dst in plan.relations]
    )
    files[f"{store.WORKLINE_DIR}/relations/related.yaml"] = store.render_relations(
        [store.Relation(rid, rtype, src, dst, dict(extra)) for rid, rtype, src, dst, extra in plan.related]
    )
    files[f"{store.WORKLINE_DIR}/events/events.jsonl"] = "".join(
        store.render_event_line(store.Event(eid, etype, entity, at)) + "\n" for eid, etype, entity, at in plan.events
    )

    # One bounded Review Run closure: an open generation, its sealed successor, and the Receipt it issues.
    run_id, receipt_id = plan.review["review_run_id"], plan.review["receipt_id"]
    common = dict(
        review_run_id=run_id,
        review_kind="work_formal",
        target_identity=plan.current_work_id,
        operation_identity="start",
        candidate_hash=_digest_of(plan.seed, "candidate"),
        review_context_hash=_digest_of(plan.seed, "context"),
        effective_policy_hash=_digest_of(plan.seed, "policy"),
        evidence_digest=_digest_of(plan.seed, "evidence"),
        coverage_digest=_digest_of(plan.seed, "coverage"),
        raw_report_set_digest=_digest_of(plan.seed, "raw-reports"),
        adjudication_digest=_digest_of(plan.seed, "adjudication"),
        obligation_digest=_digest_of(plan.seed, "obligations"),
        accepted_tasks=(),
        settled_tasks=(),
    )
    first = records.GateGeneration(
        generation=1, previous_generation=None, previous_digest=None, status=records.GATE_STATUS_OPEN,
        receipt_id=None, authorized_operation_stage=None, **common,
    )
    second = records.GateGeneration(
        generation=2, previous_generation=1, previous_digest=ReviewStore.digest(first.to_record()),
        status=records.GATE_STATUS_SEALED, receipt_id=receipt_id, authorized_operation_stage="work-terminal", **common,
    )
    receipt = records.Receipt(
        receipt_id=receipt_id, review_run_id=run_id, review_generation=2, review_kind="work_formal",
        target_identity=plan.current_work_id, operation_identity="start",
        authorized_candidate_hash=common["candidate_hash"], review_context_hash=common["review_context_hash"],
        effective_policy_hash=common["effective_policy_hash"], coverage_hash=common["coverage_digest"],
        adjudication_hash=common["adjudication_digest"], obligation_digest=common["obligation_digest"],
        unresolved_obligations=0, authorized_operation_stage="work-terminal",
    )
    for relative, record, reader in (
        (paths.gate_rel(run_id, 1), first.to_record(), records.GateGeneration.from_record),
        (paths.gate_rel(run_id, 2), second.to_record(), records.GateGeneration.from_record),
        (paths.receipt_rel(receipt_id), receipt.to_record(), records.Receipt.from_record),
    ):
        # through the canonical reader as well: a record the reader refuses is never written
        if reader(record, relative).to_record() != record:
            raise GeneratorError(f"the canonical Review reader does not round-trip {relative}")
        files[relative] = ReviewStore.render(record)
    return {relative: text.encode("utf-8") for relative, text in files.items()}


def pending_record(plan: Plan, project_root_text: str) -> tuple[str, bytes]:
    """The one intentional uncommitted runtime record: a pending push-destination pin, as ``begin`` writes it."""
    from workline import mutation, push_pin, store, yamlish  # noqa: PLC0415

    invocation = {"operation": push_pin.OWNER, "project_root": project_root_text, "remote": "origin", "urls": [PENDING_PIN_URL]}
    record = {
        "workline": mutation.INTENT_MARKER,
        "version": mutation.INTENT_VERSION,
        "mutation_id": plan.pending_mutation_id,
        "owner": push_pin.OWNER,
        "status": "pending",
        "created_at": _at(0),
        "updated_at": _at(0),
        "invocation": json.loads(json.dumps(invocation, sort_keys=True)),
        "write_scope": mutation.WriteScope(files=(store.PROJECT_YAML_REL,)).to_record(),
        "reserved_ids": {},
        "notes": {},
        "effects": [],
    }
    return f"{store.MUTATIONS_DIR}/{plan.pending_mutation_id}.yaml", yamlish.dump(record).encode("utf-8")


def logical_digest(files: dict[str, bytes]) -> str:
    """SHA-256 over the sorted (path, SHA-256 of bytes) pairs: the portable identity of the logical fixture."""
    material = json.dumps(
        sorted([relative, hashlib.sha256(data).hexdigest()] for relative, data in files.items()),
        ensure_ascii=True, separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("ascii")).hexdigest()


def counts(plan: Plan, files: dict[str, bytes], pending: tuple[str, bytes]) -> dict[str, Any]:
    """What the fixture holds (§36.15), counted from the plan and the exact rendered bytes."""

    def by_type(items: list[tuple]) -> dict[str, int]:
        found: dict[str, int] = {}
        for item in items:
            found[item[1]] = found.get(item[1], 0) + 1
        return dict(sorted(found.items()))

    def size(prefix: str) -> int:
        return sum(len(data) for relative, data in files.items() if relative.startswith(prefix))

    works = plan.works
    states = {"completed": 0, "in_progress": 0, "unstarted": 0}
    for work in works:
        if not work.events:
            states["unstarted"] += 1
        elif work.events[-1] == "work_completed":
            states["completed"] += 1
        else:
            states["in_progress"] += 1
    groups: dict[str, int] = {}
    for phase in plan.phases:
        groups[phase.group] = groups.get(phase.group, 0) + 1
    return {
        "roadmaps": len(plan.roadmaps),
        "phases": len(plan.phases),
        "phase_groups": groups,
        "works": len(works),
        "work_states": states,
        "roadmap_relations": len(plan.relations),
        "roadmap_relations_by_type": by_type(plan.relations),
        "related": len(plan.related),
        "related_by_type": by_type(plan.related),
        "events": len(plan.events),
        "events_by_type": by_type(plan.events),
        "event_log_bytes": len(files[".workline/events/events.jsonl"]),
        "relation_bytes": size(".workline/relations/"),
        "entity_bytes": size(".workline/roadmaps/") + size(".workline/phases/") + size(".workline/works/"),
        "review_records": sum(1 for relative in files if relative.startswith(".workline/review/")),
        "review_bytes": size(".workline/review/"),
        "pending_records": 1,
        "pending_bytes": len(pending[1]),
        "canonical_files": len(files),
        "canonical_bytes": sum(len(data) for data in files.values()),
    }


# --------------------------------------------------------------------------- writing


def _git(project: Path, *args: str, env_extra: dict[str, str] | None = None) -> str:
    env = dict(os.environ)
    env.update(GIT_IDENTITY)
    env.update(env_extra or {})
    completed = subprocess.run(
        ["git", "-C", str(project), *_SETUP_GIT_OPTIONS, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    if completed.returncode != 0:
        raise GeneratorError(f"git {args[0]} failed ({completed.returncode}): {completed.stderr.strip()}")
    return completed.stdout


def _inside(path: Path, directory: Path) -> bool:
    return path == directory or directory in path.parents


def _write(base: Path, relative: str, data: bytes) -> None:
    target = (base / relative).resolve()
    if not _inside(target, base):
        raise GeneratorError(f"refusing to write outside the disposable target: {relative}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(data)


def generate(target: str | os.PathLike[str], scale: str, workline_root: str | os.PathLike[str],
             seed: int = DEFAULT_SEED, *, allowed_base: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Write the fixture for ``scale`` into ``target`` and return its manifest (also written as manifest.json).

    Refuses a ``target`` that is not empty, that lies inside the Workline root,
    or - when ``allowed_base`` is given - outside ``allowed_base``. Writes only
    under ``target``; Git runs only inside ``<target>/project``.
    """
    root = Path(workline_root).resolve()
    if not (root / "run-workline.py").is_file():
        raise GeneratorError("the Workline root has no run-workline.py launcher")
    base = Path(target).resolve()
    if allowed_base is not None and not _inside(base, Path(allowed_base).resolve()):
        raise GeneratorError("the fixture target lies outside the allowed disposable fixture base")
    if _inside(base, root) or _inside(root, base):
        raise GeneratorError("the fixture target overlaps the Workline root")
    if base.exists() and (not base.is_dir() or any(base.iterdir())):
        raise GeneratorError("the fixture target already exists and is not an empty directory")
    wl = load_workline(root)
    plan = build_plan(scale, seed)

    portable = render_files(plan, wl, WORKLINE_ROOT_PLACEHOLDER)
    portable_pending = pending_record(plan, PROJECT_ROOT_PLACEHOLDER)
    base.mkdir(parents=True, exist_ok=True)
    project = base / PROJECT_DIR
    project.mkdir()
    project = project.resolve()
    files = render_files(plan, wl, str(root))
    pending = pending_record(plan, str(project))

    for relative, data in sorted(files.items()):
        _write(project, relative, data)
    _git(project, "init", "-q", "-b", "main")
    hooks = base / "no-hooks"
    hooks.mkdir()
    _git(project, "add", "-A")
    _git(project, "-c", f"core.hooksPath={hooks}", "commit", "-q", "--no-verify", "-m", FIXTURE_COMMIT_MESSAGE)
    head = _git(project, "rev-parse", "HEAD").strip()
    tree = _git(project, "rev-parse", "HEAD^{tree}").strip()
    # step 2 of §36.9: only the intentional runtime pending record stays uncommitted
    _write(project, pending[0], pending[1])

    manifest = {
        "generator_contract": GENERATOR_CONTRACT,
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "scale": scale,
        "scale_spec": {"works": SCALES[scale][0], "works_per_phase": SCALES[scale][1],
                       "events_target": EVENTS_PER_WORK * SCALES[scale][0]},
        "counts": counts(plan, files, pending),
        "logical_digest": logical_digest({**portable, portable_pending[0]: portable_pending[1]}),
        "logical_canonical_digest": logical_digest(portable),
        "git": {"head": head, "tree": tree, "commits": 1, "remotes": 0,
                "note": "the commit and tree IDs bind the configured Workline root path in project.yaml"},
        "current_work_id": plan.current_work_id,
        "review": dict(plan.review),
        "pending_mutation_id": plan.pending_mutation_id,
        "pending_record": pending[0],
    }
    with open(base / MANIFEST, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="generate.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--workline-root", required=True)
    parser.add_argument("--scale", required=True, choices=sorted(SCALES))
    parser.add_argument("--target", required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--allowed-base")
    args = parser.parse_args(argv)
    try:
        manifest = generate(args.target, args.scale, args.workline_root, args.seed, allowed_base=args.allowed_base)
    except GeneratorError as exc:
        print(f"generate: REFUSED: {exc}")
        return 1
    print(json.dumps({"scale": manifest["scale"], "counts": manifest["counts"],
                      "logical_digest": manifest["logical_digest"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
