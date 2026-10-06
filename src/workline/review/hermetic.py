"""The two Git environment classes a review-v1 Work operation runs in (``F3`` §7.1.9).

Git takes its instructions from three places at once — the command line, the
configuration it resolves, and the environment it inherits — and only the first
of those is ours by default. An inherited ``GIT_AUTHOR_NAME`` writes someone
else's name onto a commit; an inherited ``GIT_INDEX_FILE`` redirects every index
command; an inherited ``GIT_OBJECT_DIRECTORY`` makes the repository's own commit
invisible (M-61). None of that is exotic: it is one exported variable away.

So every Git invocation of this operation runs in an environment this module
builds, in the one order the contract freezes:

```text
STRIP  ->  CAPTURE  ->  NEUTRALIZE  ->  HERMETIC EXECUTION
```

**Class A — the identity capture.** The strip, and nothing else. Ordinary Git
configuration resolution stays intact, because this class exists to read it:
exactly ``config --get user.name`` and ``config --get user.email``, and nothing
else, ever. The Project root is a command argument, never an ambient variable.

**Class B — every other invocation.** The same strip, then the allowlist below
and nothing beyond it, with configuration neutralized and the captured identity
injected explicitly.

The order is the whole mechanism. Capture-then-strip leaves the capture
poisonable — ``git var GIT_AUTHOR_IDENT`` returns the hostile inherited identity
(M-63), which is why that command is not an authorized capture mechanism at all.
Strip-then-neutralize-then-capture makes the capture *impossible*, because a
Project whose identity lives only in global config reads back empty once
``GIT_CONFIG_GLOBAL`` points at an empty file (M-64). Only one order is both
safe and possible, and :func:`enter` is the only way to reach the class B that
commits: a :class:`HermeticGit` cannot be constructed without an identity that
was captured before the neutralization it is handed to.

**Read-only class B.** Reading committed objects needs the class B envelope and
nothing more: no identity, because nothing is committed, and no Project-owned
scratch. :func:`read_only` gives a :class:`ReadOnlyGit` whose envelope is built
by the same functions, whose empty configuration file and hooks directory live
outside the Project, and which runs only committed-object reads. A reader of a
Project - its validation, above all - therefore writes nothing into it.

This module builds environments. It dispatches nothing: no persistence identity
names it yet, and the review-v1 Work path stays unavailable until the unit that
owns that dispatch lands.

**Where the scratch lives.** A class B environment that commits keeps its two
Workline-owned empty objects - the ``core.hooksPath`` directory and the
``GIT_CONFIG_GLOBAL`` file - at the paths a :class:`ScratchPaths` names inside
the repository it commits in. A Project's are :data:`PROJECT_SCRATCH`, under
``.workline/runtime/review/``, exactly as always (:func:`enter`). Workline-root
policy maintenance (P7, ``WORKLINE_COMPLETION_SPRINT`` §31.8 / §31.30) enters
the same frozen order with its own root-runtime scratch (:func:`enter_root`),
which can never name ``.workline/``: no root operation creates it.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Iterator

from .. import gitcmd
from ..errors import StopError
from ..store import WORKLINE_DIR, ProjectStore
from . import paths as review_paths

#: The prefix of every variable the strip removes. No inherited name survives it,
#: in either class: the strip is what protects against a hostile environment, and
#: no invocation of this operation is exempt from it (§7.1.9, M-61).
GIT_VARIABLE_PREFIX = "GIT_"

#: The class B allowlist, in full: the six variables every class B invocation carries.
#: A variable that is not here is not set, and a variable that is inherited is not kept
#: (§7.1.9). Class A injects NONE of them. Two further sets are conditional and named
#: below: the identity, on the one command that writes a commit, and ``GIT_INDEX_FILE``,
#: only where an isolated index is named.
CLASS_B_ALLOWLIST = (
    "GIT_ATTR_NOSYSTEM",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_CONFIG_GLOBAL",
    "GIT_NO_LAZY_FETCH",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_LITERAL_PATHSPECS",
)

#: The allowlisted variables whose value is the same in every Project. ``GIT_CONFIG_GLOBAL``
#: is the sixth: its value is that Project's Workline-owned empty file.
CLASS_B_FIXED_VALUES = {
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_LITERAL_PATHSPECS": "1",
}

#: The identity variables class B injects from the class A capture, and nothing else
#: contributes to author or committer. They are supplied together with the dates,
#: because a commit's identity inputs are frozen with the rest of its plan (§7.1.9).
CLASS_B_IDENTITY_VARIABLES = (
    "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
    "GIT_AUTHOR_DATE",
    "GIT_COMMITTER_NAME",
    "GIT_COMMITTER_EMAIL",
    "GIT_COMMITTER_DATE",
)

#: The configuration every class B invocation carries, beyond ``core.hooksPath``
#: whose value is per Project. ``core.autocrlf``/``core.eol`` are CONFIGURATION and
#: not attributes: measured, ``core.autocrlf=true`` normalizes CRLF check-in content
#: even with an attribute pin in place (M-23), and Git for Windows sets it globally
#: by default, so this is the ordinary condition on that platform.
CLASS_B_CONFIGURATION = (
    ("core.fsmonitor", "false"),
    ("commit.gpgSign", "false"),
    ("gc.auto", "0"),
    ("maintenance.auto", "false"),
    ("core.autocrlf", "false"),
    ("core.eol", "lf"),
)

#: What the entry read of the promisor configuration asks for (M-54).
_PROMISOR_PATTERN = r"^remote\..*\.promisor$"


@dataclass(frozen=True)
class Identity:
    """The configured Git identity, captured under class A before anything is neutralized.

    Both fields are non-empty: an empty value is never accepted, and there is no
    fallback that could produce one (§7.1.9 phase A).
    """

    name: str
    email: str


def stripped_environment() -> dict[str, str]:
    """This process's environment with every inherited ``GIT_*`` variable removed.

    The whole of class A's environment, and the base of class B's. Nothing is
    kept by name and nothing is excused: measured (M-61), inherited
    ``GIT_AUTHOR_NAME``/``GIT_AUTHOR_EMAIL`` put ``author Attacker <evil@x>`` on
    a commit in a Project configured to someone else, an inherited
    ``GIT_INDEX_FILE`` silently redirects every index command, and an inherited
    ``GIT_OBJECT_DIRECTORY`` made ``cat-file -e HEAD`` exit 1 — the repository's
    own commit invisible.
    """
    return {
        name: value
        for name, value in os.environ.items()
        if not name.upper().startswith(GIT_VARIABLE_PREFIX)
    }


def class_a_environment() -> dict[str, str]:
    """The environment of the identity capture: the strip, and nothing injected.

    Class A does NOT neutralize configuration. It is the one purpose that
    requires the configuration to be readable, and measured (M-64), the same
    capture run with the class B neutralization variables set returns exit 1 and
    empty output for both fields.
    """
    return stripped_environment()


def capture_identity(root: Path) -> Identity:
    """The configured identity of the Project at ``root``, read under class A.

    Exactly these two commands, and nothing else is ever run in class A::

        git -C <root> config --get user.name
        git -C <root> config --get user.email

    ``--get`` reads the MERGED configuration with ordinary precedence, so system,
    global and repository-local settings decide exactly as they always did, and
    ``-C`` survives the strip because it is an argument rather than a variable.

    Either field unavailable is STOP AT ENTRY - the same condition ordinary Git
    reports - raised before anything is written. There is no fallback: no
    ``git var ...IDENT``, no OS or hostname synthesis, and an empty value is
    never accepted. Measured (M-63), with nothing configured anywhere
    ``config --get`` exits 1 with empty output and invents nothing, so removing
    ``git var`` loses no capability here.
    """
    environment = class_a_environment()
    captured: dict[str, str] = {}
    for field in ("user.name", "user.email"):
        found = gitcmd.run_git(root, "config", "--get", field, check=False, env=environment)
        value = found.stdout.strip() if found.ok else ""
        if not value:
            raise StopError(
                f"this Project has no configured {field}, and a review-v1 Work commit is made with the "
                "configured identity or with none at all; nothing is written: STOP",
                code="review_identity_unavailable",
            )
        captured[field] = value
    return Identity(captured["user.name"], captured["user.email"])


@dataclass(frozen=True)
class ScratchPaths:
    """Where a committing class B environment keeps its two Workline-owned empty objects, inside its repository.

    ``no_hooks`` is the directory named as ``core.hooksPath`` and ``no_config``
    the file named as ``GIT_CONFIG_GLOBAL``, each a repository-relative POSIX
    path: no absolute path, no empty, ``.`` or ``..`` component, no backslash.
    The same strings name them in a refusal. Nothing else about the scratch
    varies: both are created when absent and proven empty and plain
    immediately before every use, wherever they live.
    """

    no_hooks: str
    no_config: str

    def __post_init__(self) -> None:
        for named, value in (("no_hooks", self.no_hooks), ("no_config", self.no_config)):
            parts = value.split("/") if isinstance(value, str) else []
            if not parts or value.startswith("/") or ":" in value or "\\" in value \
                    or any(part in ("", ".", "..") for part in parts):
                raise ValueError(f"a class B scratch {named} is a repository-relative POSIX path, not {value!r}")

    def parts(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """The path components of the hooks directory and of the configuration file."""
        return tuple(self.no_hooks.split("/")), tuple(self.no_config.split("/"))


#: A Project's class B scratch: under ``.workline/runtime/review/``, exactly where it always was.
PROJECT_SCRATCH = ScratchPaths(review_paths.RUNTIME_NO_HOOKS_DIR, review_paths.RUNTIME_NO_CONFIG_FILE)


def _scratch_hooks_directory(root: Path, scratch: ScratchPaths) -> str:
    return _empty_hooks_directory(Path(root) / scratch.no_hooks, scratch.no_hooks, _COMMIT_HOOK_CONSEQUENCE)


def _scratch_config_file(root: Path, scratch: ScratchPaths) -> str:
    return _empty_config_file(Path(root) / scratch.no_config, scratch.no_config, _COMMIT_OUTCOME)


def no_hooks_directory(store: ProjectStore) -> str:
    """The absolute path of the Workline-owned empty directory named as ``core.hooksPath``.

    Created when absent, and proven to be an empty plain directory immediately
    before every use: anything else there is ``review_hooks_path_invalid``,
    because a hook found there would run. This is not only defence in depth —
    measured (M-48), ``update-ref`` ran a ``reference-transaction`` hook three
    times for one call with the default hooks directory and not at all with this
    one, and ``update-index`` ran ``post-index-change`` the same way.
    """
    return _scratch_hooks_directory(store.root, PROJECT_SCRATCH)


def no_config_file(store: ProjectStore) -> str:
    """The absolute path of the Workline-owned empty file named as ``GIT_CONFIG_GLOBAL``.

    Created empty when absent, and proven to be an empty plain file immediately
    before every use: a file with content there would be read as this
    invocation's global configuration, which is the one thing the variable
    exists to prevent.
    """
    return _scratch_config_file(store.root, PROJECT_SCRATCH)


#: How a refusal of a class B scratch object says what it prevented, for a write-capable and a read-only context.
_COMMIT_HOOK_CONSEQUENCE = "the commit could run a hook from it; nothing is committed"
_COMMIT_OUTCOME = "nothing is committed"
_READ_HOOK_CONSEQUENCE = "a read could run a hook from it; nothing is read"
_READ_OUTCOME = "nothing is read"


def _empty_hooks_directory(path: Path, named: str, consequence: str) -> str:
    """``path`` as an empty plain directory: created when absent, and proven immediately before every use.

    The one proof of a class B hooks directory wherever it lives - a Project's
    own (:func:`no_hooks_directory`) or a read-only context's scratch outside
    the Project (:func:`read_only`). ``named`` is how a refusal names it.
    """
    try:
        if not os.path.lexists(path):
            path.mkdir(parents=True)
        info = os.lstat(path)
        reparse = getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        if not stat.S_ISDIR(info.st_mode) or reparse or any(path.iterdir()):
            raise StopError(
                f"{named} is not an empty plain directory, so {consequence}: STOP",
                code="review_hooks_path_invalid",
            )
    except OSError as exc:
        raise StopError(
            f"{named} cannot be prepared as the empty hooks directory ({exc}): STOP",
            code="review_hooks_path_invalid",
        ) from exc
    return os.path.abspath(path)


def _empty_config_file(path: Path, named: str, outcome: str) -> str:
    """``path`` as an empty plain file: created empty when absent, and proven immediately before use.

    The one proof of a class B ``GIT_CONFIG_GLOBAL`` file wherever it lives, as
    :func:`_empty_hooks_directory` is of the hooks directory.
    """
    try:
        if not os.path.lexists(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"")
        info = os.lstat(path)
        reparse = getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        if not stat.S_ISREG(info.st_mode) or reparse or info.st_size != 0:
            raise StopError(
                f"{named} is not an empty plain file, so it would be read as this invocation's global "
                f"configuration; {outcome}: STOP",
                code="review_no_config_file_invalid",
            )
    except OSError as exc:
        raise StopError(
            f"{named} cannot be prepared as the empty configuration file ({exc}): STOP",
            code="review_no_config_file_invalid",
        ) from exc
    return os.path.abspath(path)


def _class_b_base(no_config: str) -> dict[str, str]:
    """The strip, then the six allowlisted variables, and nothing else."""
    environment = stripped_environment()
    environment.update(CLASS_B_FIXED_VALUES)
    environment["GIT_CONFIG_GLOBAL"] = no_config
    return environment


def _configuration_arguments(hooks: str) -> tuple[str, ...]:
    """The ``-c`` arguments of every class B invocation: ``core.hooksPath`` = ``hooks``, then the frozen controls."""
    settings = [("core.hooksPath", hooks), *CLASS_B_CONFIGURATION]
    arguments: list[str] = []
    for key, value in settings:
        arguments += ["-c", f"{key}={value}"]
    return tuple(arguments)


def _run(
    root: Path, configuration: tuple[str, ...], args: tuple[str, ...], environment: dict[str, str], *, check: bool
) -> gitcmd.GitResult:
    """One class B command, decoded: the configuration arguments, then ``args``, in ``environment``."""
    return gitcmd.run_git(root, *configuration, *args, check=check, env=environment)


def _run_bytes(
    root: Path,
    configuration: tuple[str, ...],
    args: tuple[str, ...],
    environment: dict[str, str],
    *,
    input: bytes | None = None,
) -> gitcmd.GitBytes:
    """One class B command, kept as bytes: the configuration arguments, then ``args``, in ``environment``."""
    return gitcmd.run_git_bytes(root, *configuration, *args, input=input, env=environment)


@dataclass(frozen=True)
class HermeticGit:
    """A Project's class B environment, and the identity it injects.

    Reachable only through :func:`enter`, which performs the frozen order, so
    there is no way to hold one of these without an identity that was captured
    before the neutralization this hands to Git.

    ``promisor_remotes`` is what the entry read of the promisor configuration
    found (M-54). It is carried rather than acted on: the condition is made
    visible, and the unit that owns a mutation records it there.
    """

    root: Path
    identity: Identity
    promisor_remotes: tuple[str, ...]
    _no_config: str
    _scratch: ScratchPaths

    def environment(self, *, index_file: str | None = None) -> dict[str, str]:
        """The class B environment: the strip, then the allowlist, and nothing else.

        ``GIT_INDEX_FILE`` is set only when an isolated index is named, so no
        command touches an index by accident. The identity variables are absent:
        they belong to :meth:`commit_environment`, on the one command that
        writes a commit object.
        """
        environment = _class_b_base(self._no_config)
        if index_file is not None:
            environment["GIT_INDEX_FILE"] = index_file
        return environment

    def commit_environment(self, date: str, *, index_file: str | None = None) -> dict[str, str]:
        """:meth:`environment` plus the captured identity, for the one command that commits.

        Author and committer are the same captured pair and the same ``date`` —
        one timestamp, so the commit's identity does not depend on when within
        the operation ``commit-tree`` happens to run. Nothing else contributes
        to author or committer.

        The date is required rather than optional because the identity and its
        dates are one set of commit-identity inputs: there is no authorized way
        to inject the identity without fixing the timestamp it is recorded with.
        """
        if not date:
            raise StopError(
                "a review-v1 Work commit is made with the exact timestamp it is recorded with, and none was "
                "named; nothing is committed: STOP",
                code="review_commit_date_unavailable",
            )
        environment = self.environment(index_file=index_file)
        environment.update(
            {
                "GIT_AUTHOR_NAME": self.identity.name,
                "GIT_AUTHOR_EMAIL": self.identity.email,
                "GIT_AUTHOR_DATE": date,
                "GIT_COMMITTER_NAME": self.identity.name,
                "GIT_COMMITTER_EMAIL": self.identity.email,
                "GIT_COMMITTER_DATE": date,
            }
        )
        return environment

    def configuration_arguments(self) -> tuple[str, ...]:
        """The ``-c`` arguments every class B invocation carries.

        The hooks directory is re-proven on every call rather than remembered,
        because it is proven empty *immediately before use* and a hook can be
        dropped there at any later moment.
        """
        return _configuration_arguments(_scratch_hooks_directory(self.root, self._scratch))

    def attribute_configuration_arguments(self, source: str) -> tuple[str, ...]:
        """:meth:`configuration_arguments` plus the attribute-source pin (``F3`` §7.1.9 class (b)).

        Every invocation that RESOLVES ATTRIBUTES carries two settings beyond the
        class B ones, and carries them in addition to - never instead of - the
        complete envelope this composes from:

        ```text
        attr.tree            = <this commit's persistence basis>
        core.attributesFile  = <the Workline-owned empty file>
        ```

        ``source`` is the persistence basis as an EXACT full object id, and is
        validated before Git is asked. ``HEAD``, a branch name, an abbreviation
        and every other revision expression are refused: a pin whose identity
        Git resolves at use time is not a pin, because what it names can change
        between the evaluation and the commit the evaluation is supposed to
        govern. Both object formats are accepted - 40 hex for SHA-1 and 64 for
        SHA-256 - because a basis is whatever identity its repository stores.

        The attributes file is the same Workline-owned empty file as
        ``GIT_CONFIG_GLOBAL``, and it is RE-PROVEN here rather than remembered,
        exactly as the hooks directory is: what matters is that it is an empty
        plain file immediately before use, and content appearing there would
        become an attribute source of this very invocation.
        """
        if not gitcmd.full_commit_id(source):
            raise StopError(
                f"the attribute source must be pinned to an exact full object id, and {source!r} is not one; "
                "an attribute question asked under an unpinned or resolvable source cannot be answered for the "
                "commit it is meant to govern: STOP",
                code="review_git_transform",
            )
        empty = _scratch_config_file(self.root, self._scratch)
        return (*self.configuration_arguments(), "-c", f"attr.tree={source}", "-c", f"core.attributesFile={empty}")

    def run(
        self,
        *args: str,
        check: bool = True,
        index_file: str | None = None,
        date: str | None = None,
    ) -> gitcmd.GitResult:
        """Run one class B Git command: the configuration arguments, then ``args``.

        ``date`` names the commit timestamp and makes this the commit invocation,
        which is the only one that receives the identity.
        """
        environment = (
            self.environment(index_file=index_file)
            if date is None
            else self.commit_environment(date, index_file=index_file)
        )
        return _run(self.root, self.configuration_arguments(), args, environment, check=check)

    def run_bytes(self, *args: str, input: bytes | None = None) -> gitcmd.GitBytes:
        """Run one class B Git command and keep its output as BYTES, undecoded and untranslated.

        The same envelope as :meth:`run` - the same environment and the same
        configuration arguments, from the same two methods - differing only in
        that nothing decodes the result.

        That difference is load-bearing for whoever reads a stored object.
        Measured: a commit object whose header block holds a line that is a lone
        CR can exist in the store, and text mode's universal-newline translation
        turns that CR into a newline, so the header block appears to end early
        and a `parent` header below it disappears. Two parents read as one, which
        is the "the walk ended, so this is a root" reading §7.1.8 forbids - and
        it fails OPEN. A reader of literal headers must see literal bytes.

        This carries no identity, no dates and no ``GIT_INDEX_FILE``: it is for
        reading, and a read writes no commit and touches no index. ``input`` is
        fed to standard input exactly as given - what ``hash-object --stdin``
        needs to name the identity of bytes without writing them anywhere.
        """
        return _run_bytes(self.root, self.configuration_arguments(), args, self.environment(), input=input)

    def execute(
        self,
        *args: str,
        input: bytes | None = None,
        index_file: str | None = None,
        date: str | None = None,
    ) -> gitcmd.GitBytes:
        """Run one class B Git command that may WRITE - an object, an isolated index, a commit - keeping bytes.

        The same envelope as :meth:`run` and :meth:`run_bytes`, from the same two
        methods, and nothing added to it but what the one command names:
        ``GIT_INDEX_FILE`` only when ``index_file`` is given (so no command
        touches an index by accident), and the captured identity with its date
        only when ``date`` is given (the one command that writes a commit
        object). ``input`` is fed to standard input exactly as given.
        """
        environment = (
            self.environment(index_file=index_file)
            if date is None
            else self.commit_environment(date, index_file=index_file)
        )
        return _run_bytes(self.root, self.configuration_arguments(), args, environment, input=input)


def _promisor_remotes(hermetic: "HermeticGit") -> tuple[str, ...]:
    """The Project's promisor-configured remotes, read at entry so the condition is visible (M-54).

    A partial clone would otherwise demand-fetch from a promisor remote in the
    middle of a proof. ``GIT_NO_LAZY_FETCH`` makes that a local-unavailable
    failure rather than a fetch; this read is what makes the arrangement
    reportable instead of silent. Exit 1 is the ordinary "no match" answer.

    It is an ordinary class B invocation and is made through :meth:`HermeticGit.run`
    like every other one, so it carries the whole envelope and not only the
    environment half of it.
    """
    found = hermetic.run("config", "--get-regexp", _PROMISOR_PATTERN, check=False)
    if not found.ok:
        return ()
    names: list[str] = []
    for line in found.stdout.splitlines():
        key = line.split(" ", 1)[0].strip()
        match = re.fullmatch(r"remote\.(.+)\.promisor", key)
        if match is not None:
            names.append(match.group(1))
    return tuple(sorted(set(names)))


def _require_no_grafts(root: Path) -> None:
    """A legacy ``.git/info/grafts`` file that is PRESENT AND NON-EMPTY is STOP (§7.1.9, §21.14 B).

    The predicate is the contract's, exactly: "Legacy ``.git/info/grafts``, if
    present and non-empty, STOPS at entry." An empty file grafts nothing and is
    not the refused condition — Git creates and leaves one in ordinary use, and
    refusing it would turn a lawful repository away.

    Correctness does not depend on this check at all: the raw ancestry reader
    reads the stored commit object, which a graft file does not alter (M-57),
    and one can appear at any later moment — which is precisely why it cannot be
    the mechanism. It is retained because it is cheap and a Project using grafts
    is one a person should know about.

    Emptiness is a property of an ordinary file. Anything else at that path —
    a directory, a symlink, a reparse point — is refused rather than measured:
    following it to decide would be the one thing a no-follow check must not do,
    so what cannot be proven empty is not treated as empty.
    """
    grafts = Path(root) / ".git" / "info" / "grafts"
    try:
        if not os.path.lexists(grafts):
            return
        info = os.lstat(grafts)
        reparse = getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        if not stat.S_ISREG(info.st_mode) or reparse:
            raise StopError(
                "this Project's .git/info/grafts is not an ordinary file, so whether it grafts anything "
                "cannot be read without following it; nothing is committed: STOP",
                code="review_repository_grafted",
            )
        if info.st_size > 0:
            raise StopError(
                "this Project has a non-empty legacy .git/info/grafts file, which rewrites what every "
                "revision walker reports about ancestry; nothing is committed: STOP",
                code="review_repository_grafted",
            )
    except OSError as exc:
        raise StopError(
            f"this Project's .git/info/grafts cannot be read ({exc}): STOP",
            code="review_repository_grafted",
        ) from exc


def _require_not_shallow(hermetic: "HermeticGit") -> None:
    """A shallow repository is STOP — defence in depth only (§7.1.9).

    Measured (M-59), in a shallow clone the walker reported HEAD as a root with
    no parents while the object held two ``parent`` headers. As with grafts, the
    raw reader is unaffected; the check exists so the condition is reported.

    It is an ordinary class B invocation and is made through :meth:`HermeticGit.run`
    like every other one, so it carries the whole envelope and not only the
    environment half of it.
    """
    found = hermetic.run("rev-parse", "--is-shallow-repository", check=False)
    if found.ok and found.stdout.strip() == "true":
        raise StopError(
            "this Project is a shallow repository, where a commit's stored parents are not all present; "
            "nothing is committed: STOP",
            code="review_repository_shallow",
        )


def enter(store: ProjectStore) -> HermeticGit:
    """Perform the frozen order and return the Project's class B environment.

    ```text
    1. strip every inherited GIT_* for the class A capture invocation
    2. capture the configured identity under ordinary Git configuration resolution
    3. STOP AT ENTRY if either identity field is unavailable
    4. activate the configuration neutralization
    5. construct the class B hermetic environment
    6. explicitly inject the captured identity
    7. execute every commit and proof Git operation
    ```

    Steps 1-3 are :func:`capture_identity`; steps 4-6 are the returned object.
    The entry reads of §7.1.9 - the promisor configuration, the grafts file and
    the shallow flag - are made here rather than left to each caller to
    remember. The two that invoke Git are made THROUGH the constructed object,
    so they are class B invocations in full: one authority builds the envelope,
    and an entry read cannot carry a different one from a later proof command.
    """
    return _enter(store.root, PROJECT_SCRATCH)


def enter_root(root: Path, scratch: ScratchPaths) -> HermeticGit:
    """The same frozen order for the repository at ``root``, with ``scratch`` as its class B scratch (P7 §31.30).

    For Workline-root policy maintenance, which is not a Project and has no
    ``ProjectStore``: every step of :func:`enter` - the class A identity
    capture (STOP AT ENTRY ``review_identity_unavailable`` when either field is
    unconfigured), the grafts, shallow and promisor entry reads, and the
    neutralized class B envelope - with the two empty objects at ``scratch``
    (``.workline-root-runtime/no-hooks`` and ``.workline-root-runtime/no-config``
    for the root, §31.8). A scratch under ``.workline/`` is refused before
    anything is read or created: nothing entered here may create the Project
    namespace in the repository it commits in. The caller has already proven
    the directory the scratch lives in.
    """
    for parts in scratch.parts():
        if parts[0] == WORKLINE_DIR:
            raise ValueError(f"a root class B scratch never lives under {WORKLINE_DIR}/: {'/'.join(parts)!r}")
    return _enter(Path(root), scratch)


def _enter(root: Path, scratch: ScratchPaths) -> HermeticGit:
    identity = capture_identity(root)
    _require_no_grafts(root)
    built = HermeticGit(
        root=root,
        identity=identity,
        promisor_remotes=(),
        _no_config=_scratch_config_file(root, scratch),
        _scratch=scratch,
    )
    _require_not_shallow(built)
    return replace(built, promisor_remotes=_promisor_remotes(built))


# --------------------------------------------------------------------------- read-only class B

#: Every Git command a read-only class B context may run: reads of committed objects, nothing else.
READ_ONLY_COMMANDS = ("cat-file", "ls-tree", "rev-parse")


@dataclass(frozen=True)
class ReadOnlyGit:
    """Class B for reading committed objects, holding nothing inside the repository it reads.

    Its envelope is built by the same functions as :class:`HermeticGit`'s: the
    strip, the allowlist with its fixed values, an empty ``GIT_CONFIG_GLOBAL``,
    the frozen configuration controls and a proven-empty ``core.hooksPath``.
    The two empty objects live in scratch the context owns OUTSIDE the
    Project, and each is re-proven immediately before use. It carries no
    identity and captures none, because a read writes no commit; and it runs
    nothing but :data:`READ_ONLY_COMMANDS`, so it has no commit, no index and
    no network to reach.

    Reachable only through :func:`read_only`, which owns the scratch.
    """

    root: Path
    _no_config: str
    _no_hooks: str

    def environment(self) -> dict[str, str]:
        """The class B environment of a read: the strip, then the allowlist, and nothing else."""
        return _class_b_base(_empty_config_file(Path(self._no_config), self._no_config, _READ_OUTCOME))

    def configuration_arguments(self) -> tuple[str, ...]:
        """The class B ``-c`` arguments, the scratch hooks directory re-proven empty immediately before use."""
        hooks = _empty_hooks_directory(Path(self._no_hooks), self._no_hooks, _READ_HOOK_CONSEQUENCE)
        return _configuration_arguments(hooks)

    def run(self, *args: str, check: bool = True) -> gitcmd.GitResult:
        """Run one read under the class B envelope, decoded."""
        _require_read(args)
        return _run(self.root, self.configuration_arguments(), args, self.environment(), check=check)

    def run_bytes(self, *args: str, input: bytes | None = None) -> gitcmd.GitBytes:
        """Run one read under the class B envelope, keeping its output as bytes (see :meth:`HermeticGit.run_bytes`)."""
        _require_read(args)
        return _run_bytes(self.root, self.configuration_arguments(), args, self.environment(), input=input)


def _require_read(args: tuple[str, ...]) -> None:
    if not args or args[0] not in READ_ONLY_COMMANDS:
        raise ValueError(f"a read-only class B context runs only {', '.join(READ_ONLY_COMMANDS)}, not {args[:1]!r}")


@contextmanager
def read_only(root: Path) -> Iterator[ReadOnlyGit]:
    """A read-only class B context over the repository at ``root``, whose scratch lives outside it.

    Nothing is created, changed or removed inside ``root``. The empty
    configuration file and the empty hooks directory are made in a fresh
    directory of the operating system's temporary area - refused if that
    directory lies inside ``root`` - and that directory is removed when the
    context exits. A scratch that cannot be removed is left where it is:
    nothing is ever done inside ``root`` to recover.

    No identity is captured, so a Project with no configured ``user.name`` or
    ``user.email`` is read like any other: that requirement belongs to the
    write-capable :func:`enter`, whose class B commits.
    """
    project = Path(root).resolve()
    try:
        scratch = Path(tempfile.mkdtemp(prefix="workline-class-b-read-")).resolve()
    except OSError as exc:
        raise StopError(
            f"no scratch for a read-only class B context can be made ({exc}); nothing is read: STOP",
            code="review_no_config_file_invalid",
        ) from exc
    try:
        if scratch == project or project in scratch.parents:
            raise StopError(
                f"the temporary area {scratch} lies inside {project}, so a read-only class B context would write "
                "into the Project it reads; nothing is read: STOP",
                code="review_no_config_file_invalid",
            )
        config = scratch / "no-config"
        hooks = scratch / "no-hooks"
        built = ReadOnlyGit(
            root=Path(root),
            _no_config=_empty_config_file(config, str(config), _READ_OUTCOME),
            _no_hooks=_empty_hooks_directory(hooks, str(hooks), _READ_HOOK_CONSEQUENCE),
        )
        yield built
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
