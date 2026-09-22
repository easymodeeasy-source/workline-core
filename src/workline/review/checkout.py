"""The checkout capability for Review paths, and the readability of the existing Review namespace.

A canonical Review record is read only in its canonical bytes (``R1`` §4), and
Git's checkout can rewrite bytes: line-end conversion, clean and smudge filters,
``$Id$`` expansion, re-encoding. So review-v1 planning writes a Review record
only where it has positively proven that Git reproduces the committed LF bytes
of Review paths in this repository and in every fresh clone of the commit that
stores them (``skills/review``, ``review-v1-planning-checkout-v1``).

P2 v1 supports exactly one configuration - the canonical Review-attribute rule,
the last attribute rule of HEAD's root ``.gitattributes``, with no
``.gitattributes`` below ``.workline/``:

```text
.workline/review/** !text eol=lf -filter -ident -working-tree-encoding
```

The proof has four layers, and every one is required:

1. **Raw committed source.** HEAD's root tree holds exactly one entry whose name
   folds to ``.gitattributes``: the regular blob ``.gitattributes``, mode
   ``100644``. Its bytes hold no NUL (Git stops reading an attributes blob at
   the first one), and their last attribute rule - the last line that is not
   blank and not a comment - is exactly the canonical rule.
2. **No deeper committed ``.gitattributes``.** Nothing below ``.workline/`` in
   HEAD's tree has a name that folds to ``.gitattributes``.
3. **Committed evaluation** (a cross-check): the committed attribute files of
   HEAD alone print form L.
4. **Effective evaluation** of this repository, every source included, prints
   form L, and no filter driver named ``unset`` is configured.

``git check-attr``'s printed words never prove an attribute state by
themselves: a literal ``filter=unset`` prints what ``-filter`` prints. That is
why layers 1 and 2 read the raw committed bytes, and layer 4 refuses a driver
the literal would select.

A failed layer is ``review_checkout_unsafe``; an object or a Git question that
cannot be read or answered well enough to decide a layer is
``review_checkout_unknown``. Unsupported is not unsafe: a refused configuration
is one P2 v1 does not prove, not one proven to change bytes. Workline never
writes ``.gitattributes`` or ``info/attributes``.
"""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import shutil

from .. import gitcmd
from ..errors import StopError, ValidationError
from ..store import ProjectStore
from . import paths

#: The one Review checkout configuration P2 v1 supports, byte for byte.
CANONICAL_RULE = b".workline/review/** !text eol=lf -filter -ident -working-tree-encoding"

#: The attributes the checkout capability evaluates, in the order ``check-attr`` is asked for them.
ATTRIBUTES = ("text", "eol", "filter", "ident", "working-tree-encoding")

#: What both evaluations must print for a Review path under the canonical rule.
FORM_L = {"text": "unspecified", "eol": "lf", "filter": "unset", "ident": "unset", "working-tree-encoding": "unset"}

CHECKOUT_CONTRACT = "review-v1-planning-checkout-v1"

GITATTRIBUTES = ".gitattributes"
REGULAR_FILE_MODE = "100644"


def fold(name: str) -> str:
    """``name`` with every non-ASCII character dropped and ASCII letters lowered.

    A case-insensitive filesystem reads ``.GITATTRIBUTES`` as
    ``.gitattributes``, and Git itself takes ``.gitattributes`` with ignorable
    non-ASCII code points for that name on HFS+; dropping every non-ASCII
    character refuses a superset of those names.
    """
    return "".join(character.lower() for character in name if character.isascii())


def _unsafe(message: str) -> StopError:
    return StopError(f"the checkout capability for Review paths does not hold: {message}", code="review_checkout_unsafe")


def _unknown(message: str) -> StopError:
    return StopError(
        f"the checkout capability for Review paths cannot be decided: {message}", code="review_checkout_unknown"
    )


def last_attribute_rule(data: bytes) -> bytes | None:
    """The last line of ``data`` that is neither blank nor a comment, as bytes; None when there is none."""
    last: bytes | None = None
    for line in data.split(b"\n"):
        stripped = line.lstrip(b" \t")
        if not stripped or stripped.startswith(b"#"):
            continue
        last = line
    return last


def require_raw_source(repo: Path, head: str) -> None:
    """Layer 1: HEAD's raw root ``.gitattributes`` ends with the canonical Review-attribute rule."""
    entries = gitcmd.tree_entries(repo, head, recursive=False)
    if entries is None:
        raise _unknown(f"Git cannot list the root tree of {head}")
    named = [entry for entry in entries if fold(entry.path) == GITATTRIBUTES]
    if not named:
        raise _unsafe(f"{head} holds no root {GITATTRIBUTES}, so it carries no canonical Review-attribute rule")
    if len(named) != 1:
        raise _unsafe(
            f"{head}'s root tree holds {len(named)} entries whose name folds to {GITATTRIBUTES}: "
            + ", ".join(entry.path for entry in named)
        )
    entry = named[0]
    if entry.path != GITATTRIBUTES or entry.type != "blob" or entry.mode != REGULAR_FILE_MODE:
        raise _unsafe(
            f"{head}'s root {entry.path!r} is {entry.type} {entry.mode}; the canonical rule lives in the regular "
            f"blob {GITATTRIBUTES}, mode {REGULAR_FILE_MODE}"
        )
    data = gitcmd.read_blob(repo, entry.oid)
    if data is None:
        raise _unknown(f"Git cannot read the blob {entry.oid} of {head}'s root {GITATTRIBUTES}")
    if b"\0" in data:
        raise _unsafe(f"{head}'s root {GITATTRIBUTES} holds a NUL byte, where Git stops reading it")
    rule = last_attribute_rule(data)
    if rule != CANONICAL_RULE:
        found = "no attribute rule" if rule is None else repr(rule.decode("utf-8", "replace"))
        raise _unsafe(
            f"the last attribute rule of {head}'s root {GITATTRIBUTES} is {found}, not the canonical Review-attribute "
            f"rule {CANONICAL_RULE.decode()!r}"
        )


def require_no_deeper_attributes(repo: Path, head: str) -> None:
    """Layer 2: HEAD holds no entry below ``.workline/`` whose name folds to ``.gitattributes``."""
    entries = gitcmd.tree_entries(repo, head, [".workline"], recursive=True, trees=True)
    if entries is None:
        raise _unknown(f"Git cannot list what {head} holds below .workline/")
    deeper = sorted(
        entry.path for entry in entries
        if entry.path.startswith(".workline/") and fold(entry.path.rsplit("/", 1)[-1]) == GITATTRIBUTES
    )
    if deeper:
        raise _unsafe(
            f"{head} holds {', '.join(deeper)} below .workline/, which outranks the root rule for the paths below it"
        )


def _printed_problems(printed: dict[str, dict[str, str]], described: str) -> list[str]:
    problems: list[str] = []
    for path, values in sorted(printed.items()):
        if values != FORM_L:
            shown = ", ".join(f"{name}: {values.get(name)}" for name in ATTRIBUTES)
            problems.append(f"{described} prints {shown} for {path}")
    return problems


def _objects_directory(repo: Path) -> Path | None:
    result = gitcmd.run_git(repo, "rev-parse", "--git-path", "objects", check=False)
    text = result.stdout.strip()
    if not result.ok or not text:
        return None
    found = Path(text)
    if not found.is_absolute():
        found = Path(repo) / found
    return found.resolve() if found.is_dir() else None


def require_committed_evaluation(store: ProjectStore, head: str, relatives: list[str]) -> None:
    """Layer 3: the committed ``.gitattributes`` files of HEAD alone print form L for every path.

    Evaluated with ``git check-attr --source=<HEAD>`` against a fresh, empty
    bare directory whose object store borrows this repository's, with no
    system or global configuration and an empty attributes file, so no
    ``info/attributes``, system or global source takes part. The directory is
    removed afterwards.
    """
    objects = _objects_directory(store.root)
    if objects is None:
        raise _unknown("Git cannot name this repository's object directory")
    found_format = gitcmd.run_git(store.root, "rev-parse", "--show-object-format", check=False)
    object_format = found_format.stdout.strip() if found_format.ok else ""
    if not object_format:
        raise _unknown("Git cannot name this repository's object format")
    scratch = store.root / paths.RUNTIME_ATTR_EVAL_DIR / secrets.token_hex(8)
    try:
        scratch.mkdir(parents=True, exist_ok=False)
        bare = scratch / "eval.git"
        # the borrowed objects are read only by a repository of the same object format (SHA-1 or SHA-256)
        created = gitcmd.run_git(
            None, "init", "--bare", "--quiet", "--template=", f"--object-format={object_format}", str(bare), check=False
        )
        if not created.ok:
            raise _unknown(f"Git cannot create the evaluation directory: {created.stderr.strip()}")
        alternates = bare / "objects" / "info" / "alternates"
        alternates.parent.mkdir(parents=True, exist_ok=True)
        alternates.write_text(objects.as_posix() + "\n", encoding="utf-8", newline="\n")
        empty = scratch / "empty"
        empty.write_bytes(b"")
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
        env.update({"GIT_ATTR_NOSYSTEM": "1", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(empty)})
        printed = gitcmd.check_attributes(
            None,
            relatives,
            ATTRIBUTES,
            before=(f"--git-dir={bare}", "-c", f"core.attributesFile={empty}"),
            options=(f"--source={head}",),
            env=env,
            cwd=scratch,
        )
    except OSError as exc:
        raise _unknown(f"the committed evaluation could not be prepared: {exc}") from exc
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if printed is None:
        raise _unknown(f"git check-attr --source={head} did not answer")
    problems = _printed_problems(printed, f"the committed evaluation of {head}")
    if problems:
        raise _unsafe("; ".join(problems))


def require_effective_evaluation(store: ProjectStore, relatives: list[str]) -> None:
    """Layer 4: this repository's effective attributes print form L, and no filter driver named ``unset`` exists."""
    printed = gitcmd.check_attributes(store.root, relatives, ATTRIBUTES)
    if printed is None:
        raise _unknown("git check-attr did not answer for this repository")
    problems = _printed_problems(printed, "the effective evaluation of this repository")
    if problems:
        raise _unsafe("; ".join(problems))
    drivers = gitcmd.config_names_matching(store.root, r"^filter\.unset\.")
    if drivers is None:
        raise _unknown("Git cannot say whether a filter driver named unset is configured")
    if drivers:
        raise _unsafe(
            "a filter driver named unset is configured (" + ", ".join(sorted(drivers)) + "); a literal filter=unset "
            "would select it, so the printed form L proves nothing"
        )


def require_checkout_capability(store: ProjectStore, relatives: list[str]) -> None:
    """All four layers for every path of ``relatives``, or ``review_checkout_unsafe`` / ``review_checkout_unknown``."""
    head = gitcmd.head_commit(store.root)
    if head is None or not gitcmd.full_commit_id(head):
        raise _unknown("HEAD does not name a commit, so no committed rule can be read")
    require_raw_source(store.root, head)
    require_no_deeper_attributes(store.root, head)
    checked = sorted(set(relatives))
    if not checked:
        return
    require_committed_evaluation(store, head, checked)
    require_effective_evaluation(store, checked)


def committed_review_paths(store: ProjectStore) -> list[str]:
    """Every Review record path HEAD holds (``git ls-tree -r --name-only <HEAD> -- .workline/review/``)."""
    head = gitcmd.head_commit(store.root)
    if head is None:
        return []
    entries = gitcmd.tree_entries(store.root, head, [paths.REVIEW_DIR], recursive=True)
    if entries is None:
        raise _unknown("Git cannot list the Review records HEAD holds")
    return sorted(entry.path for entry in entries if paths.is_review_path(entry.path))


# --------------------------------------------------------------------------- namespace readability

def require_namespace_readable(store: ProjectStore) -> None:
    """Every record already in the Review namespace reads through ``ReviewStore``, or ``review_namespace_unreadable``.

    The unchanged P1 strict reader applied to every existing record before a
    review-v1 planning call adds one, so Review state is added only to a
    namespace whose every physical record is canonical. Cross-record findings
    (a half-written stage a lost runtime left) are not refused here.
    """
    from .store import ReviewStore
    from .validate import _namespace_shape

    review = ReviewStore(store)
    try:
        if not review.exists():
            return
        shape = _namespace_shape(review)
        if shape:
            raise ValidationError("; ".join(problem.message for problem in shape), code=shape[0].code)
        for review_run_id in review.run_ids():
            review.gate_chain(review_run_id)
        for receipt_id in review.receipt_ids():
            review.read_receipt(receipt_id)
        for consumption_id in review.consumption_ids():
            review.read_consumption(consumption_id)
        for receipt_id in review.superseded_receipt_ids():
            review.read_supersession(receipt_id)
        for candidate_hash in review.candidate_snapshot_hashes():
            review.read_candidate_snapshot(candidate_hash)
        for task_id in review.task_input_ids():
            review.read_task_input(task_id)
        review.read_activation()
    except ValidationError as exc:
        raise StopError(
            f"the existing Review namespace does not read canonically ({exc.code}: {exc}); nothing is written",
            code="review_namespace_unreadable",
        ) from exc
