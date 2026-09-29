"""The Work attribute foundation: the pin, the probe that proves it, the source predicate, the pinned evaluation.

Git reads a path's attributes from the WORKING TREE when it stores an object, so
an executor that writes ``.gitattributes`` changes how this operation's own
commits store bytes. Measured (M-20): unpinned, a working-tree rule made the
committed object a filtered one and ran the filter program three times; pinned
to the base tree, the committed object was exactly ``git hash-object
--no-filters`` — F2 §6.3's ``Candidate.new_oid`` — and the filter ran zero
times. So every Work invocation that resolves attributes carries the pin
(``F3`` §7.1.9 class (b), IP-8(b)).

Four things are needed before a pinned commit can be trusted, and this module
owns all four:

```text
THE PIN            attr.tree = <exact persistence basis>, plus an empty
                   core.attributesFile, on top of the complete Unit 1 class B
                   envelope. HermeticGit composes it; nothing here rebuilds it.
THE PROBE          the running Git is PROVEN to honour attr.tree, on this
                   machine and on this run, before a pinned commit is made
                   (§7.7.2 B, IP-11). The declared floor is not the authority.
THE SOURCE         the pinned source itself is proven to carry no rule that
                   would transform bytes - over the SOURCE, which is finite,
                   never over paths, which are not known yet (§7.8, IP-12).
THE EVALUATION     an exact path set is evaluated against THAT SAME source, so
                   the evaluation and the storage cannot disagree (§7.3, IP-9).
```

Two refusals, both already live, and no third is introduced:

```text
review_git_unsupported   the running Git cannot be shown to honour the pin
review_git_transform     a source, or a path under it, is unsafe or unanswerable
```

The pin cannot rescue a base that is itself unsafe. Measured (M-24): with
``*.txt text`` in the BASE tree, a pinned stage came out normalized, because the
pin faithfully honours the base. That is why the source predicate exists and why
its surface is the complete one — ``text``, ``eol``, ``working-tree-encoding``,
``filter``, ``ident`` — with every compatibility alias expanded before it is
judged (M-23, M-25).

The supported source shape is deliberately NARROW and over-refuses. A base
carrying ``docs/** text`` is refused although no Work result may ever land under
``docs/``. That is an availability cost, never a correctness one, and the
contract states it as such (§7.8.2).

This is a foundation. Nothing dispatches to it: no Work operation, no
persistence identity and no commit path calls it, and the units that will are
not implemented. P2 planning keeps its own checkout capability
(``review/checkout.py``) unchanged — that contract is about READING Review
records back, this one is about what a Work commit STORES, and they are not the
same question.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import secrets
import shutil
import stat

from .. import gitcmd
from ..errors import StopError
from ..store import ProjectStore
from . import paths as review_paths
from .checkout import fold
from .hermetic import HermeticGit

#: The complete byte-transform surface (``F3`` §7.8.2). An ASSIGNMENT of any of
#: these changes stored bytes. ``eol`` is here on its own, without ``text``,
#: because measured it bites alone (M-25); ``text`` and ``eol`` are the two the
#: previous five-name draft of the live planning surface did not carry (M-24).
MATERIAL_ATTRIBUTES = ("text", "eol", "filter", "ident", "working-tree-encoding")

#: What ``check-attr`` must print for a path in the reserved Review namespace:
#: the canonical form L, and nothing else (``F3`` §7.3 step 3, §7.8.4).
FORM_L = {"text": "unspecified", "eol": "lf", "filter": "unset", "ident": "unset", "working-tree-encoding": "unset"}

#: What an ORDINARY path may print for every material attribute. Nothing else.
ORDINARY_STATES = ("unspecified", "unset")

#: The reserved Review namespace, and the ONE pattern that is positively confined to it.
REVIEW_NAMESPACE_PREFIX = ".workline/review/"
CANONICAL_REVIEW_PATTERN = ".workline/review/**"

#: The canonical Review rule's expanded meaning, exactly. ``skills/review`` writes it as
#: ``.workline/review/** !text eol=lf -filter -ident -working-tree-encoding``; this is
#: that line after alias expansion, sorted, and nothing may be added to or missing from it.
CANONICAL_REVIEW_MEANING = (
    ("eol", "=lf"),
    ("filter", "unset"),
    ("ident", "unset"),
    ("text", "unspecified"),
    ("working-tree-encoding", "unset"),
)

#: A filter driver with either of these names would be selected by a LITERAL assignment
#: ``filter=unset`` / ``filter=unspecified``, whose printed word is indistinguishable from a
#: real unset. The printed word never proves a state by itself, so both are refused.
HAZARD_FILTER_DRIVERS = ("unset", "unspecified")

GITATTRIBUTES = ".gitattributes"
INFO_ATTRIBUTES = "info/attributes"
REGULAR_FILE_MODE = "100644"

#: The bytes the capability probe stages. CRLF, so a ``text`` rule has something to normalize.
PROBE_BYTES = b"pinned\r\nprobe\r\n"
PROBE_PATH = "probe.txt"
#: The working-tree rule the probe writes, which the pin must make invisible.
PROBE_RULE = b"probe.txt text\n"
#: A fixed timestamp for the probe's throwaway base commit: a probe should not depend on the clock.
PROBE_DATE = "1700000000 +0000"

#: Git's own attribute-name shape: a letter or digit, then letters, digits, ``-``, ``_`` and ``.``.
_ATTR_NAME = re.compile(r"[A-Za-z0-9][-A-Za-z0-9_.]*\Z")

#: The pattern shape this contract version parses. Deliberately conservative: ordinary printable
#: ASCII without whitespace, quoting or backslash escaping, and never a leading ``!`` - Git forbids
#: a negative pattern in an attributes file, so what one would mean here is not something to guess
#: at. Anything else is unclassified, and unclassified is a refusal, not a pass (§7.8.2).
_PATTERN_SHAPE = re.compile(r"[-A-Za-z0-9_./*?\[\]]+\Z")


def _spell(name: str, state: str) -> str:
    """One expanded ``(name, state)`` pair back in the spelling a person writes it in."""
    if state == "unset":
        return f"-{name}"
    if state == "unspecified":
        return f"!{name}"
    if state.startswith("="):
        return f"{name}{state}"
    return name


def _transform(message: str) -> StopError:
    return StopError(f"the Work attribute source is not usable: {message}; nothing is committed: STOP",
                     code="review_git_transform")


def _unsupported(message: str) -> StopError:
    return StopError(f"the running Git cannot be shown to honour the attribute-source pin: {message}; "
                     "nothing is committed: STOP", code="review_git_unsupported")


# --------------------------------------------------------------------------- the source parser
#
# The predicate is over the SOURCE, never over paths. The result path set is not
# known before the executor runs (F2 §6.2), so `no material attribute applies to
# any path this operation will write` cannot be evaluated where the refusal has
# to happen. `generated/** filter=x` and `**/*.txt text` would both escape a
# path-wise probe entirely (§7.8.1).


@dataclass(frozen=True)
class Rule:
    """One attribute line of one source, with its attributes expanded to canonical meaning."""

    origin: str
    directory: str
    pattern: str
    meaning: tuple[tuple[str, str], ...]

    @property
    def root_relative(self) -> bool:
        """Whether this rule's pattern is anchored at the repository root.

        A pattern holding a ``/`` anywhere but its end is anchored to the
        DIRECTORY OF ITS SOURCE. So ``.workline/review/**`` in ``a/.gitattributes``
        denotes ``a/.workline/review/**`` and is not the canonical namespace at
        all - which is exactly the confusion §7.8.4's confinement rule exists to
        stop.
        """
        return self.directory == ""

    @property
    def material(self) -> tuple[str, ...]:
        """The material attributes this rule ASSIGNS. An unset or an unspecified assigns nothing."""
        return tuple(
            name for name, state in self.meaning
            if name in MATERIAL_ATTRIBUTES and (state == "set" or state.startswith("="))
        )

    @property
    def is_canonical_review(self) -> bool:
        """Whether this is the canonical Review rule, in the one place it can be confined to the namespace."""
        return self.root_relative and self.pattern == CANONICAL_REVIEW_PATTERN

    @property
    def claims_review_namespace(self) -> bool:
        """Whether the pattern, as written, is reaching for the Review namespace at root semantics."""
        return self.root_relative and self.pattern.startswith(REVIEW_NAMESPACE_PREFIX)


def _expand(token: str, origin: str) -> tuple[tuple[str, str], ...]:
    """One attribute token as canonical ``(name, state)`` pairs; unclassifiable is a refusal.

    ``state`` is ``"set"``, ``"unset"``, ``"unspecified"`` or ``"=<value>"``.
    Compatibility aliases are expanded HERE, before anything is judged, never
    matched as opaque words (M-25):

    ```text
    crlf        == text          -crlf == -text      !crlf == !text
    crlf=input  == eol=lf
    binary      == -diff -merge -text     the one built-in macro, and SAFE
    ```
    """
    if token.startswith("-"):
        name, state = token[1:], "unset"
    elif token.startswith("!"):
        name, state = token[1:], "unspecified"
    elif "=" in token:
        name, _, value = token.partition("=")
        state = f"={value}"
    else:
        name, state = token, "set"
    if not _ATTR_NAME.fullmatch(name):
        raise _transform(f"{origin} holds the attribute token {token!r}, which this parser does not understand")
    if name == "binary":
        # The built-in macro, and the ONE macro word the parser resolves rather than refuses
        # (§7.8.2 RULE 2). Measured RAW (M-25), because its expansion only UNSETS text. Any
        # other form of the word - `-binary`, `!binary`, `binary=x` - is not that built-in and
        # is not classified here: `-binary` would SET text, which is the opposite of safe.
        if state != "set":
            raise _transform(f"{origin} holds {token!r}; only the plain built-in macro `binary` is classified")
        return (("diff", "unset"), ("merge", "unset"), ("text", "unset"))
    if name == "crlf":
        if state == "=input":
            return (("eol", "=lf"),)
        if state.startswith("="):
            raise _transform(f"{origin} holds {token!r}; only `crlf=input` is a classified crlf assignment")
        return (("text", state),)
    return ((name, state),)


def parse_source(data: bytes, origin: str, directory: str) -> list[Rule]:
    """Every attribute rule of one source, parsed from its BYTES; anything unclassified is a refusal.

    The bytes, not ``git check-attr``'s answers for some paths: a path-wise probe
    cannot see a rule for a path that does not exist yet (§7.8.1).

    Refused, rather than partially understood: a NUL anywhere (Git stops reading
    an attributes file at the first one, so what follows is indeterminate), a
    carriage return in a line (whether it belongs to the pattern is not something
    this version measured), bytes that are not UTF-8, any ``[attr]`` macro
    DEFINITION (§7.8.2 RULE 3), and any pattern outside the conservative shape
    below. Blank lines and comments are understood and contribute nothing.
    """
    if b"\0" in data:
        raise _transform(f"{origin} holds a NUL byte, so Git reads only part of it and the rest is indeterminate")
    if b"\r" in data:
        raise _transform(f"{origin} holds a carriage return, which this parser does not classify")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _transform(f"{origin} is not UTF-8 ({exc})") from exc
    rules: list[Rule] = []
    for number, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip(" \t")
        if not stripped or stripped.startswith("#"):
            continue
        where = f"{origin} line {number}"
        if stripped.startswith("[attr]"):
            raise _transform(
                f"{where} defines the user macro {stripped!r}; a user-defined macro can expand to a material "
                "attribute and this contract version does not do expansion analysis"
            )
        fields = stripped.split()
        pattern, tokens = fields[0], fields[1:]
        if pattern.startswith('"') or "\\" in pattern:
            raise _transform(f"{where} holds the quoted or escaped pattern {pattern!r}, which this parser does "
                             "not classify")
        if not _PATTERN_SHAPE.fullmatch(pattern):
            raise _transform(f"{where} holds the pattern {pattern!r}, which is outside the shape this parser "
                             "classifies")
        if not tokens:
            raise _transform(f"{where} names the pattern {pattern!r} with no attribute, which this parser does "
                             "not classify")
        meaning: list[tuple[str, str]] = []
        for token in tokens:
            meaning.extend(_expand(token, where))
        rules.append(Rule(origin=origin, directory=directory, pattern=pattern, meaning=tuple(meaning)))
    return rules


# --------------------------------------------------------------------------- the sources, enumerated completely
#
# EVERY Git subprocess that decides this proof runs through the Unit 1 class B
# authority, and none of it goes through the generic object helpers.
#
# `gitcmd.tree_entries` and `gitcmd.read_blob` run with `env=None` and no class B
# configuration, so they inherit the ambient environment and Git's ordinary
# refs/replace view. MEASURED on the stopped candidate: with
# `git replace <unsafe original> <safe replacement>` installed, the source proof
# read the REPLACEMENT and answered PASS for a basis whose own object carries
# `*.txt text`; and with the roles reversed an unsafe replacement made a SAFE
# basis refuse. An oid must mean the object it names (M-58/M-49), so these reads
# need `GIT_NO_REPLACE_OBJECTS=1` - and they need the strip too, since an
# inherited `GIT_OBJECT_DIRECTORY` can hide the repository's own objects (M-61).
#
# Those helpers also memoize in a process-wide cache keyed by (kind, repo, oid)
# with no environment or replacement policy in the key, so one answer taken under
# a poisoned view outlives the poison. MEASURED: after removing the replace ref
# the false PASS was still served from that cache. Adding the right variables to
# a later command cannot undo an answer already taken under the wrong view, so
# this proof takes no answer from that cache at all. It runs once at entry and
# correctness dominates the saved subprocesses.


def _require_exact_basis(basis: object) -> None:
    """The persistence basis is an exact full object id, or nothing is read at all.

    Checked BEFORE any Git command, because the whole point of a pin is that the
    identity cannot move between the evaluation and the commit it governs.
    ``HEAD``, a branch, ``refs/heads/main``, an abbreviation Git would happily
    resolve, an uppercase spelling, a wrong width and every ``<oid>^...``
    revision expression are refused here rather than left to fail somewhere
    inside Git - the same exact-identity rule
    :meth:`HermeticGit.attribute_configuration_arguments` and
    :func:`require_pinned_path_evaluation` already hold to.
    """
    if not gitcmd.full_commit_id(basis):
        raise _transform(
            f"the persistence basis must be an exact full object id, and {basis!r} is not one; a basis Git "
            "resolves at use time can name a different object when the commit it governs is made"
        )


def _work_tree_entries(hermetic: HermeticGit, basis: str) -> list[gitcmd.TreeEntry]:
    """``git ls-tree -z --full-tree -r <basis>``, as a CLASS B invocation, parsed from bytes.

    No attribute pin is carried: this is asking what objects the basis holds, not
    what attributes apply to them, and making the object listing depend on
    attribute resolution would be circular.
    """
    listed = hermetic.run_bytes("ls-tree", "-z", "--full-tree", "-r", basis)
    if not listed.ok:
        raise _transform(f"Git cannot enumerate the tree of {basis}, so its attribute sources cannot be listed")
    entries: list[gitcmd.TreeEntry] = []
    for item in listed.stdout.split(b"\0"):
        if not item:
            continue
        head, separator, path = item.partition(b"\t")
        fields = head.split(b" ")
        if not separator or len(fields) != 3 or not path:
            raise _transform(f"Git's listing of {basis} holds a record this parser cannot classify")
        try:
            mode, kind, oid = (field.decode("ascii") for field in fields)
        except UnicodeDecodeError as exc:
            raise _transform(f"Git's listing of {basis} holds a non-ASCII mode, type or object id") from exc
        if not gitcmd.full_commit_id(oid):
            raise _transform(f"Git's listing of {basis} names {oid!r} where a full object id belongs")
        # Git writes a path's bytes as they are; surrogateescape keeps any byte that is not UTF-8 exactly,
        # which is what the repository's other raw readers do.
        entries.append(gitcmd.TreeEntry(mode, kind, oid, path.decode("utf-8", "surrogateescape")))
    return entries


def _work_read_blob(hermetic: HermeticGit, oid: str, described: str) -> bytes:
    """``git cat-file blob <oid>``, as a CLASS B invocation; unreadable is a refusal, never a fallback."""
    found = hermetic.run_bytes("cat-file", "blob", oid)
    if not found.ok:
        raise _transform(f"Git cannot read the attribute source {described}")
    return found.stdout


def _committed_sources(hermetic: HermeticGit, basis: str) -> list[tuple[str, str, bytes]]:
    """Every ``.gitattributes`` blob of ``basis``, at the root and at EVERY depth, found by enumeration.

    Enumerated from the tree, never guessed at from a fixed list of locations
    and never read from the working tree (§7.8.3). Each entry is
    ``(origin, directory, bytes)``.
    """
    found: list[tuple[str, str, bytes]] = []
    for entry in _work_tree_entries(hermetic, basis):
        directory, _, name = entry.path.rpartition("/")
        if fold(name) != GITATTRIBUTES:
            continue
        if entry.type != "blob" or entry.mode != REGULAR_FILE_MODE:
            raise _transform(
                f"{basis} holds {entry.path!r} as {entry.type} {entry.mode}; an attribute source is the regular "
                f"blob {GITATTRIBUTES}, mode {REGULAR_FILE_MODE}"
            )
        data = _work_read_blob(hermetic, entry.oid, f"{entry.path!r} of {basis}")
        found.append((f"{basis}:{entry.path}", directory, data))
    return found


def _info_attributes(store: ProjectStore, hermetic: HermeticGit) -> list[tuple[str, str, bytes]]:
    """``.git/info/attributes`` when it is there, as a root-relative source; absent contributes no rule.

    It is external Git metadata, never part of the committed tree and never a
    Work result path. The pin does not reach it, which is exactly why the
    per-commit preflight re-asks: a non-tree source arriving mid-run is the drift
    that check catches (§7.3). Present but unreadable is a refusal, not a shrug.
    """
    located = hermetic.run("rev-parse", "--git-path", INFO_ATTRIBUTES, check=False)
    text = located.stdout.strip()
    if not located.ok or not text:
        raise _transform(f"Git cannot name this repository's {INFO_ATTRIBUTES}")
    path = Path(text)
    if not path.is_absolute():
        path = Path(store.root) / path
    try:
        if not os.path.lexists(path):
            return []
        info = os.lstat(path)
        reparse = getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        if not stat.S_ISREG(info.st_mode) or reparse:
            raise _transform(f"{INFO_ATTRIBUTES} is not a plain file, so what Git reads there is not classified")
        data = path.read_bytes()
    except OSError as exc:
        raise _transform(f"{INFO_ATTRIBUTES} cannot be read ({exc})") from exc
    return [(INFO_ATTRIBUTES, "", data)]


def require_work_attribute_source(store: ProjectStore, hermetic: HermeticGit, basis: str) -> None:
    """The universal predicate of ``F3`` §7.8 over the exact persistence basis; unsafe or unknown is a refusal.

    ``basis`` is an exact full object id - ``PRE_S_C0_BASE`` at entry, and
    ``declared_base.base_commit`` for the commits after it, which §7.1.11 proves
    carry the same attribute-source state. Nothing here is hardcoded to ``HEAD``
    or to either of those: the caller names the basis.

    Two surfaces, and the difference is not a softening of the first (§7.8.4):

    ```text
    ORDINARY          no rule may ASSIGN any material attribute to a pattern
                      that can match a path outside the Review namespace
    .workline/review/ the canonical form-L rule is PERMITTED and REQUIRED, and
                      only for the ONE pattern positively confined to it
    ```

    The Review exception is narrow on purpose. A wider pattern that happens to
    also cover Review paths - ``**/*``, ``.workline/**``, ``*.yaml`` - is judged
    by the ordinary rule, and a canonical-LOOKING line in a nested source is not
    canonical at all, because from there it denotes a different namespace.

    What this predicate does NOT do, and does not pretend to: decide what a wide
    safe pattern such as ``**/* -eol`` leaves the Review namespace printing. It
    proves what is knowable over the source - that no ordinary material rule is
    present and that the canonical rule is - and
    :func:`require_pinned_path_evaluation` proves the state of the EXACT paths a
    commit writes, under this same source, immediately before that commit
    (§7.3). The two are not substitutes for one another.

    Nothing is written, no Review state is touched, and a success is not
    remembered: a later evaluation asks again.
    """
    _require_exact_basis(basis)
    sources = _committed_sources(hermetic, basis) + _info_attributes(store, hermetic)
    rules: list[Rule] = []
    for origin, directory, data in sources:
        rules.extend(parse_source(data, origin, directory))

    canonical: list[Rule] = []
    for rule in rules:
        if rule.is_canonical_review:
            if tuple(sorted(rule.meaning)) != CANONICAL_REVIEW_MEANING:
                raise _transform(
                    f"{rule.origin} holds the Review-namespace pattern {rule.pattern!r} with "
                    + " ".join(_spell(name, state) for name, state in rule.meaning)
                    + "; the reserved namespace takes the canonical form and no other"
                )
            canonical.append(rule)
            continue
        if rule.claims_review_namespace:
            # Refused whether or not it assigns anything material: `.workline/review/** -eol` assigns
            # nothing, and would still take the namespace out of form L, which §7.9's checkout claim
            # rests on. Only the canonical rule speaks for this namespace.
            raise _transform(
                f"{rule.origin} holds the additional Review-namespace rule {rule.pattern!r}; the reserved "
                f"namespace is spoken for by the canonical {CANONICAL_REVIEW_PATTERN} rule and by nothing else"
            )
        if not rule.material:
            continue
        raise _transform(
            f"{rule.origin} assigns the material attribute{'s' if len(rule.material) > 1 else ''} "
            f"{', '.join(rule.material)} to {rule.pattern!r}, which can match a path outside the Review "
            "namespace, so a commit made under this source need not store the bytes it was given"
        )

    if not canonical:
        raise _transform(
            f"no source of {basis} holds the canonical Review rule "
            f"`{CANONICAL_REVIEW_PATTERN} !text eol=lf -filter -ident -working-tree-encoding`, which is what "
            "makes canonical Review records readable back in a fresh clone"
        )
    if len(canonical) > 1:
        raise _transform(
            f"{len(canonical)} sources hold a {CANONICAL_REVIEW_PATTERN} rule ("
            + ", ".join(rule.origin for rule in canonical)
            + "); which one governs is not something this parser decides"
        )


# --------------------------------------------------------------------------- the pinned path evaluation (IP-9)


def _require_no_hazard_driver(hermetic: HermeticGit) -> None:
    """No filter driver named ``unset`` or ``unspecified`` is configured, under the hermetic resolution.

    ``check-attr`` printing ``unset`` does not prove an attribute is unset: a
    literal ``filter=unset`` prints exactly the same word and selects a driver of
    that name. The configuration is read through the class B envelope, so what is
    asked about is the resolution the commit itself would get.
    """
    for driver in HAZARD_FILTER_DRIVERS:
        found = hermetic.run("config", "--get-regexp", rf"^filter\.{driver}\.", check=False)
        if found.returncode not in (0, 1):
            raise _transform(f"Git cannot say whether a filter driver named {driver} is configured "
                             f"({found.stderr.strip()})")
        if found.returncode == 0 and found.stdout.strip():
            raise _transform(
                f"a filter driver named {driver} is configured, so a literal filter={driver} would select it and "
                "the printed word proves nothing"
            )


def _require_canonical_relative(relative: str) -> None:
    """The declared path is a plain repository-relative spelling, or the surface it lies on is unknown."""
    if not isinstance(relative, str) or not relative:
        raise _transform(f"{relative!r} is not a path this evaluation can place on a surface")
    if relative.startswith("/") or "\\" in relative or ":" in relative.split("/")[0]:
        raise _transform(f"{relative!r} is absolute, drive-qualified or holds a backslash, so which surface it "
                         "lies on is not decided here")
    if any(part in ("", ".", "..") for part in relative.split("/")):
        raise _transform(f"{relative!r} holds an empty, `.` or `..` component, so which surface it lies on is "
                         "not decided here")


def require_pinned_path_evaluation(
    store: ProjectStore, hermetic: HermeticGit, basis: str, relatives: "list[str] | tuple[str, ...]"
) -> None:
    """Evaluate an exact path set against the SAME pinned source the commit will use (``F3`` §7.3, IP-9).

    The live planning evaluation asks with no ``--source``, which is the working
    tree (M-22), and that is the defect this closes: evaluation and storage must
    not be able to disagree. Here the invocation carries ``attr.tree=<basis>``
    AND ``--source=<basis>`` - the same exact identity in both places, so the
    source the answer came from is mechanically the source the commit runs with.

    The complete material set is asked for, not the old planning subset of
    ``filter``/``ident``/``working-tree-encoding``: ``text`` and ``eol`` change
    stored bytes on their own (M-23, M-24, M-25).

    ```text
    ORDINARY paths            every material attribute `unspecified` or `unset`
    .workline/review/** paths exactly form L, and nothing weaker
    ```

    A pass is per path set and never carries: a pass proven for paths A says
    nothing about paths B (§7.3).
    """
    for relative in relatives:
        _require_canonical_relative(relative)
    _require_no_hazard_driver(hermetic)
    if not relatives:
        return
    printed = gitcmd.check_attributes(
        store.root,
        list(relatives),
        MATERIAL_ATTRIBUTES,
        before=hermetic.attribute_configuration_arguments(basis),
        options=(f"--source={basis}",),
        env=hermetic.environment(),
    )
    if printed is None:
        raise _transform(f"git check-attr --source={basis} did not answer under the pin")
    problems: list[str] = []
    for relative in sorted(relatives):
        values = printed.get(relative, {})
        shown = ", ".join(f"{name}: {values.get(name)}" for name in MATERIAL_ATTRIBUTES)
        if relative.startswith(REVIEW_NAMESPACE_PREFIX):
            if values != FORM_L:
                problems.append(f"the reserved Review path {relative} prints {shown}, not the canonical form")
            continue
        unsafe = [name for name in MATERIAL_ATTRIBUTES if values.get(name) not in ORDINARY_STATES]
        if unsafe:
            problems.append(f"{relative} prints {shown}, and {', '.join(unsafe)} would transform its bytes")
    if problems:
        raise _transform("; ".join(problems))


# --------------------------------------------------------------------------- the capability probe (IP-11)


def _without_pin(arguments: tuple[str, ...]) -> tuple[str, ...]:
    """The same attribute-resolving arguments with ONLY the ``attr.tree`` pin removed.

    What the probe's control needs: a run that differs from the pinned one in the
    pin and in nothing else, so a difference in the staged object is attributable
    to the pin rather than to some other setting.
    """
    kept: list[str] = []
    index = 0
    while index < len(arguments):
        if arguments[index] == "-c" and index + 1 < len(arguments) and arguments[index + 1].startswith("attr.tree="):
            index += 2
            continue
        kept.append(arguments[index])
        index += 1
    return tuple(kept)


def _staged_object(repo: Path, hermetic: HermeticGit, arguments: tuple[str, ...]) -> str:
    """Stage the probe path in the scratch repository and return the object id the index holds."""
    added = gitcmd.run_git_bytes(repo, *arguments, "add", "--", PROBE_PATH, env=hermetic.environment())
    if not added.ok:
        raise _unsupported(f"the probe could not stage its path ({added.stderr.decode('utf-8', 'replace').strip()})")
    listed = gitcmd.run_git_bytes(repo, *arguments, "ls-files", "-s", "-z", "--", PROBE_PATH,
                                 env=hermetic.environment())
    if not listed.ok:
        raise _unsupported("the probe could not read back what it staged")
    items = [item for item in listed.stdout.split(b"\0") if item]
    if len(items) != 1:
        raise _unsupported(f"the probe staged {len(items)} entries for one path")
    head, _, _ = items[0].partition(b"\t")
    fields = head.split(b" ")
    if len(fields) != 3:
        raise _unsupported("the probe could not read the staged object id")
    oid = fields[1].decode("ascii", "replace")
    if not gitcmd.full_commit_id(oid):
        raise _unsupported(f"the probe read {oid!r} where a full object id belongs")
    return oid


def _remove_scratch(path: Path) -> bool:
    """Remove the probe's directory completely; whether nothing of it is left.

    A repository the probe wrote objects into holds READ-ONLY files - that is how
    Git stores a loose object - and a plain recursive delete leaves them behind
    on Windows. Every entry is made writable first, and the answer is read from
    the filesystem afterwards rather than from the delete's own silence: a probe
    that cannot clean up after itself is a probe whose cleanup is not trusted
    (§7.7's containment), and the caller refuses on it.
    """
    for parent, directories, files in os.walk(path):
        for name in (*directories, *files):
            try:
                os.chmod(os.path.join(parent, name), stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)
    return not os.path.lexists(path)


@dataclass(frozen=True)
class ProbeMeasurement:
    """What one capability probe measured. Evidence, not an authorization anyone keeps."""

    basis: str
    pinned: str
    raw: str
    control: str | None


def probe_attribute_pin(store: ProjectStore, hermetic: HermeticGit) -> ProbeMeasurement:
    """Positively prove the running Git honours ``attr.tree``, here and now (``F3`` §7.7.2 B).

    In a throwaway repository under ``.workline/runtime/**`` - the same
    containment the live committed evaluation already uses (M-21):

    ```text
    1. a committed source carrying NO attributes
    2. probe bytes whose identity changes if a check-in transform runs
    3. a WORKING-TREE .gitattributes assigning that transform to the probe path
    4. stage it with the EXACT pin this unit exposes
    5. require the staged object id == git hash-object --no-filters of the bytes
    ```

    No filter program is configured or invoked: the transform is the built-in
    ``text`` normalization of CRLF, so the probe has no external side effect at
    all. ``git add`` appears HERE and only here - it is the mechanism under test,
    it runs in a scratch repository, and it is never the Work persistence
    primitive, which §7.1.2 prohibits it from being.

    A mismatch, or a question that cannot be answered, is
    ``review_git_unsupported``. Not knowing is not a yes.
    """
    found_format = hermetic.run("rev-parse", "--show-object-format", check=False)
    object_format = found_format.stdout.strip() if found_format.ok else ""
    if not object_format:
        raise _unsupported("Git cannot name this repository's object format, so the probe cannot match it")
    root = store.root / review_paths.RUNTIME_ATTR_PROBE_DIR
    scratch = root / secrets.token_hex(8)
    try:
        try:
            scratch.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise _unsupported(f"the probe directory {scratch} already exists") from exc
        repo = scratch / "probe"
        created = gitcmd.run_git(
            None, "init", "--quiet", "--template=", f"--object-format={object_format}", str(repo),
            check=False, env=hermetic.environment(),
        )
        if not created.ok:
            raise _unsupported(f"the probe repository could not be created ({created.stderr.strip()})")
        (repo / PROBE_PATH).write_bytes(PROBE_BYTES)
        (repo / GITATTRIBUTES).write_bytes(PROBE_RULE)

        tree = gitcmd.run_git_bytes(repo, "hash-object", "-t", "tree", "-w", "--stdin", input=b"",
                                    env=hermetic.environment())
        if not tree.ok:
            raise _unsupported("the probe could not write a source tree carrying no attributes")
        empty_tree = tree.stdout.decode("ascii", "replace").strip()
        committed = gitcmd.run_git_bytes(repo, "commit-tree", "-m", "attribute pin probe", empty_tree,
                                         input=b"", env=hermetic.commit_environment(PROBE_DATE))
        if not committed.ok:
            raise _unsupported("the probe could not commit a source tree carrying no attributes")
        basis = committed.stdout.decode("ascii", "replace").strip()
        if not gitcmd.full_commit_id(basis):
            raise _unsupported("the probe's own source commit has no full object id")

        pinned_arguments = hermetic.attribute_configuration_arguments(basis)
        # The control runs FIRST, so the pinned measurement is the one the index ends on and
        # cannot be read out of a stale entry. If the control does not differ, the probe does
        # not weaken: pinned equality remains the pass condition either way.
        control: str | None = None
        try:
            control = _staged_object(repo, hermetic, _without_pin(pinned_arguments))
        except StopError:
            control = None
        index = repo / ".git" / "index"
        try:
            if index.exists():
                index.unlink()
        except OSError as exc:
            raise _unsupported(f"the probe could not clear its own scratch index ({exc})") from exc

        pinned = _staged_object(repo, hermetic, pinned_arguments)
        raw = gitcmd.run_git_bytes(repo, "hash-object", "--no-filters", "-t", "blob", "--stdin",
                                   input=PROBE_BYTES, env=hermetic.environment())
        if not raw.ok:
            raise _unsupported("the probe could not compute the raw identity of its own bytes")
        expected = raw.stdout.decode("ascii", "replace").strip()
        if not gitcmd.full_commit_id(expected):
            raise _unsupported("the probe's raw identity is not a full object id")
        if pinned != expected:
            raise _unsupported(
                f"a path staged under attr.tree={basis} came out {pinned}, not the {expected} that "
                "`git hash-object --no-filters` gives, so this Git does not honour the pin"
            )
        measured = ProbeMeasurement(basis=basis, pinned=pinned, raw=expected, control=control)
    finally:
        removed = _remove_scratch(scratch)
    if not removed:
        raise _unsupported(f"the probe directory {scratch} could not be removed, so the probe did not contain itself")
    return measured


def require_attribute_pin_capability(store: ProjectStore, hermetic: HermeticGit) -> ProbeMeasurement:
    """The declared floor, and then the measurement that is the actual authority (``F3`` §7.7.2, IP-11).

    The version is checked first so a Git below the floor is refused WITHOUT
    running a probe that could authorize it, and an unknown version meets no
    minimum. Above the floor the probe decides: a floor that is too low never
    authorizes an unpinned commit by itself, because the probe tests exactly the
    equality the floor is supposed to protect.

    Nothing here is remembered. The contract requires the running Git be proven
    before the first pinned commit of EVERY review-v1 Work operation, so this
    module keeps no process-lifetime "already proven" flag; the unit that owns an
    operation is where a per-operation proof would live.
    """
    version = gitcmd.running_git_version()
    if not gitcmd.version_meets(version, gitcmd.P3_WORK_ATTR_PIN_GIT_MIN):
        shown = gitcmd.version_text(version) if version is not None else "unknown"
        raise _unsupported(
            f"the running Git is {shown} and the attribute-source pin is declared from "
            f"{gitcmd.version_text(gitcmd.P3_WORK_ATTR_PIN_GIT_MIN)}"
        )
    return probe_attribute_pin(store, hermetic)
