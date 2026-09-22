"""The committed-result loader: a Project as of one exact commit, read from raw Git objects.

Given a commit C, this materializes exactly C's canonical Project files from the
bytes Git stores for them - ``git ls-tree`` and ``git cat-file blob``: no
checkout, no smudge, no line-end conversion - into a fresh scratch directory
under ``.workline/runtime/review/proofs/``, and reads them with the production
loader, ``ProjectView.load(ProjectStore(<that directory>))``, unchanged.

```text
.workline/project.yaml
.workline/roadmaps/*.md   .workline/phases/*.md   .workline/works/*.md
.workline/relations/roadmap.yaml   .workline/relations/related.yaml
.workline/events/events.jsonl
```

It parses nothing itself: there is no second Project parser. Every materialized
entry must be a regular file blob of mode ``100644``; a symlink, a gitlink, an
executable or a tree where a canonical file belongs is refused. Review records,
derivation detail, runtime data and everything outside ``.workline/`` are not
materialized, because ``ProjectView`` does not read them.

What it gives - ``ProjectView`` as of an exact commit - is read by the review-v1
planning proofs, the freeze's committed basis and working-tree compatibility
check, recovery discovery and the currency evaluations, and is the base the
expected physical projection is computed on. Nothing that decides lifecycle or
progression reads it: the Project's lifecycle is still what ``state.py`` derives
from the working tree.

The scratch directory is removed once it has been read; a leftover is runtime
residue and nothing reads it.
"""

from __future__ import annotations

from contextlib import contextmanager
import re
import secrets
import shutil
from pathlib import Path
from typing import Iterator

from . import gitcmd
from .review import paths as review_paths
from .state import ProjectView
from .store import WORKLINE_DIR, ProjectStore

#: The canonical Project files outside the entity directories that the committed view carries.
LEDGER_FILES = (
    f"{WORKLINE_DIR}/project.yaml",
    f"{WORKLINE_DIR}/relations/roadmap.yaml",
    f"{WORKLINE_DIR}/relations/related.yaml",
    f"{WORKLINE_DIR}/events/events.jsonl",
)

#: An entity file sits directly inside its kind's directory.
_ENTITY_FILE = re.compile(rf"^{re.escape(WORKLINE_DIR)}/(roadmaps|phases|works)/[^/]+\.md$")

REGULAR_FILE_MODE = "100644"


class CommittedReadError(Exception):
    """A commit's canonical Project files cannot be read exactly from its objects."""


def is_materialized_path(path: str) -> bool:
    """Whether ``path`` is one of the canonical Project files the committed view carries."""
    return path in LEDGER_FILES or _ENTITY_FILE.match(path) is not None


def canonical_entries(repo: Path, commit: str) -> list[gitcmd.TreeEntry]:
    """The tree entries of ``commit`` that are its canonical Project files, each proven a regular ``100644`` blob."""
    entries = gitcmd.tree_entries(repo, commit, [WORKLINE_DIR], recursive=True, trees=True)
    if entries is None:
        raise CommittedReadError(f"Git cannot list the canonical Project files of {commit}")
    selected: list[gitcmd.TreeEntry] = []
    for entry in entries:
        if not is_materialized_path(entry.path):
            if _below_materialized(entry.path):
                raise CommittedReadError(
                    f"{commit} holds {entry.path}, inside a path where a canonical Project file belongs"
                )
            continue
        if entry.type != "blob" or entry.mode != REGULAR_FILE_MODE:
            raise CommittedReadError(
                f"{commit} holds {entry.path} as {entry.type} {entry.mode}, not a regular file blob of mode "
                f"{REGULAR_FILE_MODE}"
            )
        selected.append(entry)
    return selected


def _below_materialized(path: str) -> bool:
    parts = path.split("/")
    return any(is_materialized_path("/".join(parts[:end])) for end in range(1, len(parts)))


def materialize(repo: Path, commit: str, directory: Path) -> None:
    """Write ``commit``'s canonical Project files, byte for byte as Git stores them, below ``directory``."""
    for entry in canonical_entries(repo, commit):
        data = gitcmd.read_blob(repo, entry.oid)
        if data is None:
            raise CommittedReadError(f"Git cannot read the blob {entry.oid} {commit} holds at {entry.path}")
        target = directory / entry.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def scratch_directory(store: ProjectStore) -> Path:
    """A fresh directory for one materialization, inside the Project's Review runtime area."""
    return store.root / review_paths.RUNTIME_PROOFS_DIR / secrets.token_hex(8)


@contextmanager
def materialized(store: ProjectStore, commit: str) -> Iterator[ProjectStore]:
    """``commit``'s canonical Project files in a scratch directory, as a ``ProjectStore``; removed afterwards."""
    directory = scratch_directory(store)
    directory.mkdir(parents=True, exist_ok=False)
    try:
        materialize(store.root, commit, directory)
        yield ProjectStore(directory)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def committed_view(store: ProjectStore, commit: str) -> ProjectView:
    """``ProjectView`` as of ``commit``: its canonical files materialized from raw blobs, read by the production loader."""
    with materialized(store, commit) as scratch:
        return ProjectView.load(scratch)
