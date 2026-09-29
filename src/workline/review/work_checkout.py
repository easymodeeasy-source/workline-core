"""The resulting tree's checkout capability: can a fresh clone still read the Review records?

``F3`` §7.9.1 states the problem the previous draft left open. By the time a Work
seals, it has ALREADY written canonical Review records - the CandidateSnapshot,
the TaskInput, the gate generations - and is about to write the Receipt. P1
requires those to remain exactly readable from a fresh clone; that is the whole
reason they are canonical rather than runtime. A Candidate that introduces
attributes covering ``.workline/review/**`` would make them read transformed, and
"the reviewer sees the rule" is not a mechanical safety property.

§7.9.3 does not invent a proof. It reuses the canonical one - the same form-L
rule ``skills/review`` already freezes for P2 - with the tree under test being
the RESULTING TREE rather than HEAD:

```text
.workline/review/** !text eol=lf -filter -ident -working-tree-encoding

form L   text: unspecified   eol: lf   filter: unset   ident: unset   working-tree-encoding: unset

1. the raw bytes of the resulting tree's root .gitattributes hold no NUL and their LAST attribute
   rule is exactly that line;
2. the resulting tree holds no entry under .workline/ whose name folds to .gitattributes;
3. the evaluation of the resulting tree's committed .gitattributes ALONE prints form L;
4. this repository's effective evaluation - info/attributes, global and system included - prints
   form L, and no filter driver named `unset` is configured.

failure -> review_checkout_unsafe        undeterminable -> review_checkout_unknown
```

Why the rule ASSIGNS rather than leaving things unspecified: ``eol=lf`` produces
LF on checkout **regardless of the reader's** ``core.autocrlf`` **or**
``core.eol``, which is the one thing a fresh clone cannot promise. A "nothing
applies under a neutralized test config" test proves nothing about a real clone
(M-23), which is why that formulation is withdrawn.

**Two scopes, never conflated** (§7.9.4):

```text
FORM-L COVERAGE     the namespace as a PATTERN, so it covers records that exist in the resulting
                    tree AND the sealing generation, the Receipt and the Consumption that do not
                    exist yet. No identifier is needed for any of them, and none is reserved here.
STRICT-READER CHECK only records that ALREADY EXIST in the resulting tree - every Run's, not this
                    one's. A record that has not been written cannot be read, and its future
                    readability is what form-L guarantees.
```

The second condition is separate from attributes: every canonical Review record
present in the resulting tree must still read under P1's STRICT reader. That is
the same condition ``skills/review`` already makes a precondition of writing any
Review record, evaluated over the state this authorization would bring about.

This is a callable foundation. Nothing seals, issues a Receipt, writes a
generation or reserves an identifier here; the Work Review Context binds the
tree this proof is ABOUT (§7.9.6) and never its verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import shutil
import stat
from typing import Mapping, Sequence

from .. import gitcmd
from ..errors import StopError, ValidationError
from ..store import ProjectStore
from . import fsafe, paths, records, serialize
from .checkout import (
    ATTRIBUTES,
    CANONICAL_RULE,
    FORM_L,
    GITATTRIBUTES,
    REGULAR_FILE_MODE,
    fold,
    last_attribute_rule,
    require_effective_evaluation,
)
from .hermetic import HermeticGit
from .resulting_tree import Composition
from .store import ReviewStore

#: The Work checkout-capability contract identity the Context binds (``F3`` §7.9.6).
#: Distinct from P2's ``review-v1-planning-checkout-v1``: that contract is about READING planning
#: Review records back from HEAD, this one about the tree a Work authorization would bring about.
WORK_CHECKOUT_CONTRACT = "review-v1-work-checkout-capability-v1"

#: The form identity and the namespace the claim is about, both bound into the Context.
FORM_IDENTITY = "form-L"
REVIEW_NAMESPACE = ".workline/review/**"

#: A path inside the namespace that need not exist: the form-L claim is over the PATTERN, so a
#: future record - the sealing generation, the Receipt, the Consumption - is covered without an
#: identifier (§7.9.4). Only used to ASK the evaluator about the namespace.
NAMESPACE_WITNESS = f"{paths.REVIEW_DIR}/gates/0/000001.yaml"

#: Where a `.gitattributes` below this prefix would defeat the root rule (layer 2).
WORKLINE_PREFIX = f"{paths.WORKLINE_DIR}/"


def _unsafe(message: str) -> StopError:
    return StopError(
        f"the checkout capability of the resulting tree does not hold: {message}", code="review_checkout_unsafe"
    )


def _unknown(message: str) -> StopError:
    return StopError(
        f"the checkout capability of the resulting tree cannot be decided: {message}",
        code="review_checkout_unknown",
    )


# --------------------------------------------------------------------------- the strict reader over a tree


class ResultingTreeReviewStore(ReviewStore):
    """P1's strict Review reader, reading from a composed resulting tree.

    The same shape ``CommittedReviewStore`` already uses over a commit, moved to
    a tree that exists only inside the contained composition. Exactly three
    things are overridden - what entries exist, what bytes a record holds, and
    whether the namespace exists at all - and everything built on them is
    inherited unchanged: the canonical parse, the round-trip check, the record
    classes, the chain invariants. A lax bespoke parser here would be the one
    thing this check exists to prevent.
    """

    def __init__(self, store: ProjectStore, composition: Composition) -> None:
        super().__init__(store)
        self.composition = composition
        self._tree = {
            path: entry
            for path, entry in composition.entries(trees=True).items()
            if path == paths.REVIEW_DIR or path.startswith(paths.REVIEW_DIR + "/")
        }

    def exists(self) -> bool:
        return any(path.startswith(paths.REVIEW_DIR + "/") for path in self._tree)

    def entries(self, relative_dir: str) -> list[fsafe.Entry] | None:
        prefix = relative_dir.rstrip("/") + "/"
        if relative_dir != paths.REVIEW_DIR and self._tree.get(relative_dir) is None:
            return None
        if relative_dir == paths.REVIEW_DIR and not self.exists():
            return None
        found: list[fsafe.Entry] = []
        for path, entry in sorted(self._tree.items()):
            if not path.startswith(prefix) or "/" in path[len(prefix):]:
                continue
            found.append(
                fsafe.Entry(
                    path[len(prefix):],
                    is_dir=entry.type == "tree",
                    is_file=entry.type == "blob" and entry.mode == REGULAR_FILE_MODE,
                    is_indirection=entry.mode == "120000" or entry.type == "commit",
                )
            )
        return found

    def read_bytes(self, relative: str) -> bytes | None:
        paths.require_review_record_path(relative)
        found = self._tree.get(relative)
        if found is None:
            return None
        if found.type != "blob" or found.mode != REGULAR_FILE_MODE:
            raise ValidationError(
                f"the resulting tree holds {relative} as {found.type} {found.mode}, not a regular file record",
                code="review_record_invalid",
            )
        return self.composition.read_blob(found.oid)

    def gate_chain(self, review_run_id: str):
        """The validated chain for ``review_run_id``, read from the resulting tree.

        Overridden because the inherited one walks the FILESYSTEM, which holds
        none of this: it would answer ``None`` for a run that exists only in the
        tree, and the chain invariants would never run. Tree-backed, so the same
        shape the committed reader already uses over a commit.
        """
        run_dir = paths.run_dir(review_run_id)
        listed = self.entries(run_dir)
        if listed is None:
            return None
        numbers: list[int] = []
        for entry in listed:
            if entry.name == paths.SERIALIZATION_TOKEN:
                raise ValidationError(
                    f"the resulting tree holds {run_dir}/{paths.SERIALIZATION_TOKEN}, a scope-only token "
                    "that is never created",
                    code="review_namespace_invalid",
                )
            if entry.is_indirection:
                raise ValidationError(
                    f"the resulting tree holds {run_dir}/{entry.name} as an indirection", code="review_containment"
                )
            number = paths.generation_of_name(entry.name)
            if number is None or not entry.is_file:
                raise ValidationError(
                    f"the resulting tree holds {run_dir}/{entry.name}, which is not a gate generation file",
                    code="review_namespace_invalid",
                )
            numbers.append(number)
        if not numbers:
            return None
        numbers.sort()
        expected = list(range(records.FIRST_GENERATION, records.FIRST_GENERATION + len(numbers)))
        if numbers != expected:
            raise ValidationError(
                f"Review Run {review_run_id} in the resulting tree has a non-contiguous generation chain: "
                f"found {numbers}, expected {expected}",
                code="review_gate_chain",
            )
        generations = []
        digests: list[str] = []
        for number in numbers:
            relative = paths.gate_rel(review_run_id, number)
            raw = self.read_bytes(relative)
            if raw is None:
                raise ValidationError(
                    f"the resulting tree lost {relative} while it was read", code="review_namespace_unreadable"
                )
            found, text = self._parse(
                raw, f"Review gate {relative} of the resulting tree", records.GateGeneration.from_record
            )
            if number > records.FIRST_GENERATION and found.previous_digest != digests[-1]:
                raise ValidationError(
                    f"Review gate {relative} names predecessor digest {found.previous_digest}, but generation "
                    f"{number - 1} digests to {digests[-1]}",
                    code="review_gate_chain",
                )
            generations.append(found)
            digests.append(serialize.digest_of_text(text))
        return generations


def review_record_paths(composition: Composition) -> list[str]:
    """Every canonical Review record path the resulting tree holds, over the CLOSED namespace.

    Every Run's records, not this one's (§7.9.4): a Candidate can leave this Run
    untouched and still corrupt an OLDER record on fresh checkout.

    An entry under the closed namespace that is NOT a regular file record is
    refused here rather than skipped. Skipping it would be a fail-open: a symlink
    or a gitlink where a canonical record belongs would never be enumerated,
    never read, and so never refused, while the namespace it sits in is exactly
    the one this proof exists to guarantee.
    """
    prefix = paths.REVIEW_DIR + "/"
    known = tuple(f"{prefix}{name}/" for name in paths.REVIEW_SUBDIRS)
    found: list[str] = []
    for path, entry in sorted(composition.entries().items()):
        if not path.startswith(prefix):
            continue
        if not path.startswith(known):
            raise _unsafe(f"the resulting tree holds {path}, which is not inside the closed Review namespace")
        if entry.type != "blob" or entry.mode != REGULAR_FILE_MODE:
            raise _unsafe(
                f"the resulting tree holds {path} as {entry.type} {entry.mode}; a canonical Review record is "
                f"a regular blob, mode {REGULAR_FILE_MODE}"
            )
        found.append(path)
    return found


# --------------------------------------------------------------------------- the four layers


def _require_raw_rule(composition: Composition) -> None:
    """Layer 1: the resulting tree's root ``.gitattributes`` ends with the canonical rule, verbatim."""
    listing = composition.entries()
    named = [path for path in listing if fold(path) == GITATTRIBUTES]
    if not named:
        raise _unsafe(f"the resulting tree holds no root {GITATTRIBUTES}, so it carries no canonical Review rule")
    if len(named) != 1:
        raise _unsafe(f"the resulting tree holds {len(named)} root entries folding to {GITATTRIBUTES}")
    entry = listing[named[0]]
    if named[0] != GITATTRIBUTES or entry.type != "blob" or entry.mode != REGULAR_FILE_MODE:
        raise _unsafe(
            f"the resulting tree holds {named[0]!r} as {entry.type} {entry.mode}; the canonical rule lives in "
            f"the regular blob {GITATTRIBUTES}, mode {REGULAR_FILE_MODE}"
        )
    data = composition.read_blob(entry.oid)
    if b"\0" in data:
        raise _unsafe(f"the resulting tree's {GITATTRIBUTES} holds a NUL byte, so Git reads only part of it")
    last = last_attribute_rule(data)
    if last is None:
        raise _unsafe(f"the resulting tree's {GITATTRIBUTES} holds no attribute rule at all")
    if last.rstrip(b" \t") != CANONICAL_RULE:
        raise _unsafe(
            "the last attribute rule of the resulting tree's root "
            f"{GITATTRIBUTES} is {last.decode('utf-8', 'replace')!r}, not the canonical Review rule"
        )


def _require_no_deeper_source(composition: Composition) -> None:
    """Layer 2: nothing below ``.workline/`` folds to ``.gitattributes`` in the resulting tree."""
    deeper = [
        path
        for path in composition.entries(trees=True)
        if path.startswith(WORKLINE_PREFIX) and fold(path.rsplit("/", 1)[-1]) == GITATTRIBUTES
    ]
    if deeper:
        raise _unsafe(
            "the resulting tree holds " + ", ".join(sorted(deeper)) + ", which would override the canonical rule"
        )


def _printed_problems(printed: Mapping[str, Mapping[str, str]], described: str) -> list[str]:
    problems: list[str] = []
    for path, values in sorted(printed.items()):
        if dict(values) != FORM_L:
            shown = ", ".join(f"{name}: {values.get(name)}" for name in ATTRIBUTES)
            problems.append(f"{described} prints {shown} for {path}")
    return problems


def _require_committed_evaluation(
    composition: Composition, hermetic: HermeticGit, relatives: Sequence[str]
) -> None:
    """Layer 3: the resulting tree's committed attributes ALONE print form L.

    Asked inside the contained composition, with ``--source`` naming the exact
    resulting tree, an empty ``core.attributesFile`` and the class B envelope's
    neutralized system and global sources - so no ``info/attributes``, global or
    system source takes part. That isolation is layer 3's whole point; layer 4 is
    where the real environment is judged.
    """
    empty = Path(composition.repository) / "empty-attributes"
    try:
        empty.write_bytes(b"")
    except OSError as exc:
        raise _unknown(f"the committed evaluation could not be prepared: {exc}") from exc
    printed = gitcmd.check_attributes(
        composition.repository,
        list(relatives),
        ATTRIBUTES,
        before=(*hermetic.configuration_arguments(), "-c", f"core.attributesFile={empty}"),
        options=(f"--source={composition.tree}",),
        env=hermetic.environment(),
    )
    if printed is None:
        raise _unknown(f"git check-attr --source={composition.tree} did not answer")
    problems = _printed_problems(printed, f"the committed evaluation of the resulting tree {composition.tree}")
    if problems:
        raise _unsafe("; ".join(problems))


# --------------------------------------------------------------------------- the whole claim


@dataclass(frozen=True)
class Capability:
    """What one capability derivation proved, and over exactly which tree.

    Evidence, never a Context field: §7.9.6 withdrew the verdict fields because
    they made an unsafe resulting tree unrepresentable, and an unsafe Candidate
    must stay expressible and reviewable.
    """

    capability_contract: str
    form: str
    namespace: str
    resulting_tree: str
    record_paths: tuple[str, ...]


def require_resulting_tree_capability(
    store: ProjectStore,
    hermetic: HermeticGit,
    composition: Composition,
    *,
    expect: str | None = None,
) -> Capability:
    """The four layers of ``F3`` §7.9.3 over the exact resulting tree, plus P1's strict reader.

    ``expect`` names the tree the claim is supposed to be about - at seal time,
    the object id the Context bound - so a proof can never silently answer about
    a tree recomputed from something else.

    ```text
    every layer holds  ->  the Capability this returns
    any layer fails    ->  review_checkout_unsafe
    any question Git or the reader cannot answer  ->  review_checkout_unknown
    ```
    """
    if expect is not None and expect != composition.tree:
        raise _unknown(
            f"the capability was asked about {expect}, but the composition is {composition.tree}"
        )
    _require_raw_rule(composition)
    _require_no_deeper_source(composition)
    try:
        records = review_record_paths(composition)
    except StopError:
        raise
    # The namespace witness is a path that need not exist: form-L coverage is over the PATTERN, so
    # the sealing generation, the Receipt and a future Consumption are covered without identifiers.
    asked = sorted({*records, NAMESPACE_WITNESS})
    _require_committed_evaluation(composition, hermetic, asked)
    require_effective_evaluation(store, list(asked))
    _require_strict_reader(store, composition, records)
    return Capability(
        capability_contract=WORK_CHECKOUT_CONTRACT,
        form=FORM_IDENTITY,
        namespace=REVIEW_NAMESPACE,
        resulting_tree=composition.tree,
        record_paths=tuple(records),
    )


def _require_strict_reader(store: ProjectStore, composition: Composition, records: Sequence[str]) -> None:
    """Every canonical Review record already in the resulting tree still reads under P1's strict reader."""
    reader = ResultingTreeReviewStore(store, composition)
    try:
        for relative in records:
            reader.read_bytes(relative)
        _read_every_record(reader, records)
    except ValidationError as exc:
        raise _unsafe(
            f"a canonical Review record of the resulting tree does not read under the strict reader: {exc}"
        ) from exc
    except StopError:
        raise


def _read_every_record(reader: ResultingTreeReviewStore, records: Sequence[str]) -> None:
    """Parse each record through its own typed reader, so the P1 invariants actually run."""
    prefix = paths.REVIEW_DIR + "/"
    runs: set[str] = set()
    for relative in records:
        rest = relative[len(prefix):]
        area, _, tail = rest.partition("/")
        stem = tail[:-5] if tail.endswith(".yaml") else tail
        if area == "gates":
            runs.add(stem.split("/")[0])
        elif area == "receipts":
            reader.read_receipt(stem)
        elif area == "consumptions":
            reader.read_consumption(stem)
        elif area == "supersessions":
            reader.read_supersession(stem)
        elif area == "candidate-snapshots":
            reader.read_candidate_snapshot(stem)
        elif area == "task-inputs":
            reader.read_task_input(stem)
        elif area == "activation":
            reader.read_activation()
    for review_run_id in sorted(runs):
        reader.gate_chain(review_run_id)
