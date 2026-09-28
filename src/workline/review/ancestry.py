"""RAW commit ancestry: the only authority for parentage, range and descent (``F3`` §7.1.8, IP-26).

Git has two different answers to "what are this commit's parents". The REVISION
VIEW — what ``rev-list``, ``log``, ``merge-base`` and every revision walker say —
is produced after applying ``refs/replace``, ``.git/info/grafts`` and
``.git/shallow``. The COMMIT OBJECT holds the literal ``parent <oid>`` headers
that were stored. They differ, and the difference is attacker-controllable:
measured, a graft file made ``merge-base --is-ancestor`` answer FALSE for a
genuine ancestor while the object still named the true parent (M-57), and a
shallow clone made the walker report a commit with two stored parents as a root
(M-59).

So every ancestry answer a P3 proof rests on is read here, from the stored
object, and from nothing else. ``gitcmd.commit_parents`` and
``gitcmd.descends_from`` are the two calls that are lied to; they remain for
their existing non-proof callers and back nothing in this module.

Three answers, and they are not interchangeable:

```text
a tuple of oids   what the stored object says, which may be empty for a root
False             asked and answered: this is not an ancestor
UNKNOWN           the question could not be answered, and FAILS CLOSED
```

UNKNOWN is never False, never an empty tuple and never a root. A named parent
whose object is not here makes the whole answer UNKNOWN, because reading it as
"the walk ended, so this is a root" is exactly how a shallow boundary would
forge a lineage.

Everything here runs through Unit 1's class B authority
(:meth:`HermeticGit.run_bytes`), which is what puts ``GIT_NO_REPLACE_OBJECTS``
and ``GIT_NO_LAZY_FETCH`` on the actual invocation — the first so an oid means
the object it names rather than a ``refs/replace`` view (M-58), the second so a
missing object is a local failure rather than a fetch in the middle of a proof.

This is a reader. Nothing dispatches to it yet: no proof, no lineage rule and no
persistence path calls it, and the units that will are not implemented.
"""

from __future__ import annotations

from collections import deque
import enum

from .. import gitcmd
from .hermetic import HermeticGit

#: The frozen bound on one public ancestry evaluation (``F3`` §7.1.8, IP26-B1).
#: Not configurable, not derived and not overridable: crossing it turns a
#: provable answer into UNKNOWN, so the value is the contract's, not a setting.
P3_RAW_ANCESTRY_STEP_BUDGET = 4096

#: What a commit object's header block ends with. Literal bytes, because a lone
#: CR is not a blank line and must not be allowed to look like one.
_HEADER_TERMINATOR = b"\n\n"

#: A parent declaration, exactly.
_PARENT_PREFIX = b"parent "

#: The object type ``cat-file commit`` must be reading. MEASURED: given an
#: ANNOTATED TAG's oid, ``cat-file commit`` PEELS it and prints the tagged
#: commit with exit 0 - so without this check a tag's oid would be answered with
#: another object's parents. A tree and a blob are refused by Git itself.
_COMMIT_TYPE = b"commit"


class Answer(enum.Enum):
    """The non-tuple answers, as values that cannot be mistaken for data.

    ``UNKNOWN`` is not ``False``, not ``()`` and not a root; ``NON_LINEAR`` is
    not ``UNKNOWN``, so a caller can tell "this range holds a merge" from "this
    range could not be read". Both are truthy, so neither collapses into a
    falsy answer by accident.
    """

    UNKNOWN = "unknown"
    NON_LINEAR = "non_linear"


UNKNOWN = Answer.UNKNOWN
NON_LINEAR = Answer.NON_LINEAR


def is_full_oid(value: object) -> bool:
    """Whether ``value`` names an object by its full lowercase hexadecimal id.

    The repository's established grammar (:func:`gitcmd.full_commit_id`): 40 hex
    for SHA-1, 64 for SHA-256, lowercase, matched exactly. Nothing else is an
    input here - not an abbreviation Git would happily resolve, not ``HEAD``,
    not a branch name, not ``<oid>^`` or ``<oid>^{commit}``. A revision
    expression is not an object id, and this module never asks Git to turn one
    into one.
    """
    return gitcmd.full_commit_id(value)


def _parse_parents(raw: bytes, oid: str) -> tuple[str, ...] | Answer:
    """The literal ``parent`` headers of a stored commit object, in stored order.

    ``raw`` is the object's bytes, undecoded. The header block is everything
    before the FIRST literal ``b"\\n\\n"``, and that terminator MUST BE THERE: an
    object whose bytes never reach an empty line has no header block, so it is
    not parsed at all and the answer is UNKNOWN. Taking the whole object as its
    own header block instead would fail OPEN twice over - message text would be
    read as headers, and an object with nothing header-shaped in it would be
    reported as a genuine root. A lone CR is not that terminator; it is an
    ordinary byte of some header's value and ends nothing.

    Message text below the boundary is not parsed at all, so a message line
    reading ``parent <something>`` is not a parent.

    A malformed ``parent`` line makes the whole answer UNKNOWN rather than a
    shorter list: returning the parents before it would be reporting a commit as
    having fewer parents than it stores, which is the one error this module
    exists to prevent.
    """
    block, terminator, _message = raw.partition(_HEADER_TERMINATOR)
    if not terminator:
        return UNKNOWN
    parents: list[str] = []
    for line in block.split(b"\n"):
        if not line.startswith(_PARENT_PREFIX):
            continue
        try:
            named = line[len(_PARENT_PREFIX):].decode("ascii")
        except UnicodeDecodeError:
            return UNKNOWN
        # A parent is a full oid of the SAME width as the commit naming it: one
        # repository is one object format, so a 40-hex commit citing a 64-hex
        # parent is a malformed object, not a mixed-format history.
        if not is_full_oid(named) or len(named) != len(oid):
            return UNKNOWN
        parents.append(named)
    return tuple(parents)


def raw_parents(hermetic: HermeticGit, oid: str) -> tuple[str, ...] | Answer:
    """The literal ``parent`` headers of the commit object ``oid`` names.

    ```text
    GIT_NO_REPLACE_OBJECTS=1  GIT_NO_LAZY_FETCH=1  git cat-file commit <oid>
    ```

    both supplied by the class B envelope this runs through, and the output read
    as BYTES. An empty tuple is a genuine root - a commit whose header block
    holds no ``parent`` line at all - and is a known answer, not UNKNOWN.

    UNKNOWN, failing closed, when the oid is not a full object id, when the
    object is not present, when it is not a commit, or when its header block
    cannot be parsed. A StopError from the hermetic authority itself - an
    invalid hooks directory, say - is NOT swallowed into UNKNOWN: a broken
    execution environment is a stop, not an ancestry answer.
    """
    if not is_full_oid(oid):
        return UNKNOWN
    # The type is checked first and separately because `cat-file commit` is not
    # a type check: given an annotated tag it peels to the tagged commit and
    # succeeds, which would answer one object's question with another object's
    # parents. `cat-file -t` names the object itself.
    typed = hermetic.run_bytes("cat-file", "-t", oid)
    if not typed.ok or typed.stdout.strip() != _COMMIT_TYPE:
        return UNKNOWN
    found = hermetic.run_bytes("cat-file", "commit", oid)
    if not found.ok:
        return UNKNOWN
    return _parse_parents(found.stdout, oid)


def raw_descends_from(hermetic: HermeticGit, commit: str, ancestor: str) -> bool | Answer:
    """Whether ``ancestor`` is ``commit`` or is reachable from it through stored parents.

    The canonical schedule of §7.1.8 IP26-B1, which is what makes the budget
    spend the same way every time: a FIFO queue seeded with ``commit``, the
    oldest oid taken first, parents appended in their literal stored header
    order, and an oid marked seen at first discovery so it is never requested
    twice within one evaluation. A depth-first walk is not a conforming
    schedule - it can spend the whole budget down one side of a merge and answer
    UNKNOWN where this answers YES.

    The budget is checked BEFORE each request, so the 4097th distinct object is
    not read at all rather than read and then discarded.

    A non-reflexive True always follows a SUCCESSFUL read of the ancestor's own
    object. An oid that merely appears in some other commit's header is not
    evidence that the object is here: answering True on the header alone would
    let a shallow boundary's named-but-absent parent stand as a proven ancestor.

    False means the queue emptied with every scheduled object read successfully
    and none of them equal to ``ancestor``. It never stands in for "could not
    tell" - anything unreadable has already returned UNKNOWN.
    """
    # Validated BEFORE the reflexive shortcut: two identical strings that are
    # not object ids are not an ancestry proof.
    if not is_full_oid(commit) or not is_full_oid(ancestor):
        return UNKNOWN
    if commit == ancestor:
        return True

    queue: deque[str] = deque([commit])
    seen = {commit}
    steps = 0
    while queue:
        current = queue.popleft()
        if steps == P3_RAW_ANCESTRY_STEP_BUDGET:
            return UNKNOWN
        parents = raw_parents(hermetic, current)
        steps += 1
        if parents is UNKNOWN:
            return UNKNOWN
        assert not isinstance(parents, Answer)
        if current == ancestor:
            return True
        for parent in parents:
            if parent not in seen:
                seen.add(parent)
                queue.append(parent)
    return False


def raw_range(hermetic: HermeticGit, base: str, head: str) -> tuple[str, ...] | Answer:
    """The commits from ``head`` down to, and excluding, ``base``, over stored parents.

    The single-parent shape §8.2 L-2 asks for, and not a general merge-DAG
    enumerator: L-2 requires every commit in its range to have exactly one
    parent, so a commit here that has more than one is the lineage refusal
    itself. This surfaces that as :data:`NON_LINEAR` and stops. It does not pick
    a parent to keep the range going and it does not enumerate both - either
    would manufacture a linear range the stored objects do not have.

    Returned in walk order, ``head`` first, with no sorting: a single-parent
    chain has exactly one order and this is it. ``base == head`` is the known
    empty range.

    UNKNOWN, failing closed, when an object cannot be read, when the budget
    would require a 4097th request, or when the walk reaches a genuine root
    without meeting ``base``. That last case is a state §8.2 L-1 - which proves
    ``base`` is an ancestor of the head before this range is asked for - has
    already excluded, so it is a contradiction rather than a shorter lawful
    range, and a truncated range is never returned as though it were one.
    """
    if not is_full_oid(base) or not is_full_oid(head):
        return UNKNOWN
    if base == head:
        return ()

    walked: list[str] = []
    current = head
    steps = 0
    while current != base:
        if steps == P3_RAW_ANCESTRY_STEP_BUDGET:
            return UNKNOWN
        parents = raw_parents(hermetic, current)
        steps += 1
        if parents is UNKNOWN:
            return UNKNOWN
        assert not isinstance(parents, Answer)
        if len(parents) > 1:
            return NON_LINEAR
        if not parents:
            # a genuine root, reached without meeting base
            return UNKNOWN
        walked.append(current)
        current = parents[0]
    return tuple(walked)
