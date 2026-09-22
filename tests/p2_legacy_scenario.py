"""A legacy Roadmap creation and Phase entry, recorded in a form that compares across implementations.

The P2 test contract holds the legacy path to the implementation baseline byte for byte (§28 A, §28 N item G):
``p2_legacy_baseline.json`` is this scenario's record made on the baseline ``de3681c``, and the test runs the same
scenario on the current code and compares. The scenario imports only what the baseline has.

Everything the two runs cannot share is normalized: the temporary and Workline-root paths, commit IDs (by order of
first appearance) and timestamps. IDs are deterministic, so every entity file, ledger, invocation, recorded effect,
commit and push is compared as written.
"""

from __future__ import annotations

from dataclasses import asdict
import itertools
from pathlib import Path
import re
from typing import Any
from unittest import mock

from helpers import WORKLINE_ROOT, git
from workline import ids, yamlish
from workline import roadmap as rm
from workline.create import RelatedSpec
from workline.mutation import Mutation
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.store import ProjectStore

PLAN = rm.RoadmapPlan(
    "Legacy Roadmap", "計画の背景", "達成したい状態",
    {"a": PhaseSpec("Phase A", "A が成立する"), "b": PhaseSpec("Phase B", "B が成立する")},
    (PhaseRelationSpec("planned_next", "a", "b"),),
    scope="   ",
)
DESIGN = rm.PhaseEntryDesign(
    {
        "w1": rm.WorkDesign("W1", "W1 が成立する",
                            (RelatedSpec("conditional_must_read", "src/x.py", {"pattern": "src/*.py", "kind": "path_glob"}),)),
        "w2": rm.WorkDesign("W2", "W2 が成立する"),
    },
    rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
    rm.WorkDesign("Confirmation", "人間が成果を確認した"),
    planned_next=(("w1", "w2"),),
)
COMMIT_ID = re.compile(r"\b[0-9a-f]{40}\b")


class _ProcessEnds(BaseException):
    """The process ends right before the mutation completes."""


def _deterministic_ids():
    counter = itertools.count(1)

    def next_ulid(now_ms: int | None = None) -> str:
        value = next(counter)
        chars = []
        for _ in range(26):
            chars.append("0123456789ABCDEFGHJKMNPQRSTVWXYZ"[value & 31])
            value >>= 5
        return "".join(reversed(chars))

    return mock.patch.object(ids, "new_ulid", next_ulid)


def _ends_before_complete():
    real = Mutation.complete
    ended: list[bool] = []

    def complete(self_):
        if not ended:
            ended.append(True)
            raise _ProcessEnds()
        return real(self_)

    return mock.patch.object(Mutation, "complete", complete)


def _without_times(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _without_times(v) for k, v in value.items() if not str(k).endswith("_at")}
    if isinstance(value, list):
        return [_without_times(v) for v in value]
    return value


def _pending(store: ProjectStore) -> list[dict]:
    found = []
    for path in sorted(store.mutations.glob("*.yaml")):
        record = yamlish.load(path.read_text(encoding="utf-8"))
        if record.get("status") == "pending":
            found.append(_without_times(record))
    return found


def _commit(store: ProjectStore, remote: Path) -> dict:
    head = git(store.root, "rev-parse", "HEAD").strip()
    changed = git(store.root, "diff-tree", "--no-commit-id", "-r", "--name-status", "--no-renames", "HEAD").splitlines()
    files = {}
    for line in changed:
        status, path = line.split("\t", 1)
        files[path] = [status, None if status == "D" else git(store.root, "show", f"HEAD:{path}")]
    return {
        "head": head,
        "subject": git(store.root, "log", "-1", "--format=%s").strip(),
        "parents": len(git(store.root, "log", "-1", "--format=%P").split()),
        "files": files,
        "published": git(store.root, "--git-dir", str(remote), "rev-parse", "refs/heads/main").strip(),
    }


def _normalized(value: Any, tmp: Path) -> Any:
    """Paths and commit IDs replaced by what both runs share."""
    replacements = []
    for root, name in ((Path(tmp), "<tmp>"), (WORKLINE_ROOT, "<workline>")):
        for form in {str(root), root.as_posix(), str(root).replace("\\", "\\\\")}:
            replacements.append((form, name))
    replacements.sort(key=lambda pair: -len(pair[0]))
    symbols: dict[str, str] = {}

    def text(found: str) -> str:
        for old, new in replacements:
            found = found.replace(old, new)
        return COMMIT_ID.sub(lambda match: symbols.setdefault(match.group(0), f"<C{len(symbols) + 1}>"), found)

    def walk(item: Any) -> Any:
        if isinstance(item, dict):
            return {text(str(k)): walk(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [walk(v) for v in item]
        if isinstance(item, str):
            return text(item)
        return item

    return walk(value)


def run_scenario(case) -> dict:
    """The legacy scenario on the code imported, in ``case`` (a ``helpers.WorklineTestCase``)."""
    record: dict[str, Any] = {}
    with _deterministic_ids():
        store = case.new_project("legacy", remote=True)
        remote = case.remote_path("legacy")
        with _ends_before_complete():
            try:
                rm.create_roadmap(store, PLAN)
            except _ProcessEnds:
                pass
        record["create:pending"] = _pending(store)
        created = rm.create_roadmap(store, PLAN)
        record["create:result"] = asdict(created)
        record["create:commit"] = _commit(store, remote)
        with _ends_before_complete():
            try:
                rm.enter_phase(store, created.phase_ids["a"], DESIGN)
            except _ProcessEnds:
                pass
        record["entry:pending"] = _pending(store)
        entered = rm.enter_phase(store, created.phase_ids["a"], DESIGN)
        record["entry:result"] = asdict(entered)
        record["entry:commit"] = _commit(store, remote)
        record["pending:after"] = _pending(store)
    return _normalized(record, case.tmp)
