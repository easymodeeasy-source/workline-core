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
safe and possible, and :func:`enter` is the only way to reach class B: a
:class:`HermeticGit` cannot be constructed without an identity that was captured
before the neutralization it is handed to.

This module builds environments. It dispatches nothing: no persistence identity
names it yet, and the review-v1 Work path stays unavailable until the unit that
owns that dispatch lands.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
import re
import stat

from .. import gitcmd
from ..errors import StopError
from ..store import ProjectStore
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


def no_hooks_directory(store: ProjectStore) -> str:
    """The absolute path of the Workline-owned empty directory named as ``core.hooksPath``.

    Created when absent, and proven to be an empty plain directory immediately
    before every use: anything else there is ``review_hooks_path_invalid``,
    because a hook found there would run. This is not only defence in depth —
    measured (M-48), ``update-ref`` ran a ``reference-transaction`` hook three
    times for one call with the default hooks directory and not at all with this
    one, and ``update-index`` ran ``post-index-change`` the same way.
    """
    path = store.root / review_paths.RUNTIME_NO_HOOKS_DIR
    try:
        if not os.path.lexists(path):
            path.mkdir(parents=True)
        info = os.lstat(path)
        reparse = getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        if not stat.S_ISDIR(info.st_mode) or reparse or any(path.iterdir()):
            raise StopError(
                f"{review_paths.RUNTIME_NO_HOOKS_DIR} is not an empty plain directory, so the commit could run "
                "a hook from it; nothing is committed: STOP",
                code="review_hooks_path_invalid",
            )
    except OSError as exc:
        raise StopError(
            f"{review_paths.RUNTIME_NO_HOOKS_DIR} cannot be prepared as the empty hooks directory ({exc}): STOP",
            code="review_hooks_path_invalid",
        ) from exc
    return os.path.abspath(path)


def no_config_file(store: ProjectStore) -> str:
    """The absolute path of the Workline-owned empty file named as ``GIT_CONFIG_GLOBAL``.

    Created empty when absent, and proven to be an empty plain file immediately
    before every use: a file with content there would be read as this
    invocation's global configuration, which is the one thing the variable
    exists to prevent.
    """
    path = store.root / review_paths.RUNTIME_NO_CONFIG_FILE
    try:
        if not os.path.lexists(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"")
        info = os.lstat(path)
        reparse = getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        if not stat.S_ISREG(info.st_mode) or reparse or info.st_size != 0:
            raise StopError(
                f"{review_paths.RUNTIME_NO_CONFIG_FILE} is not an empty plain file, so it would be read as this "
                "invocation's global configuration; nothing is committed: STOP",
                code="review_no_config_file_invalid",
            )
    except OSError as exc:
        raise StopError(
            f"{review_paths.RUNTIME_NO_CONFIG_FILE} cannot be prepared as the empty configuration file "
            f"({exc}): STOP",
            code="review_no_config_file_invalid",
        ) from exc
    return os.path.abspath(path)


def _class_b_base(no_config: str) -> dict[str, str]:
    """The strip, then the six allowlisted variables, and nothing else."""
    environment = stripped_environment()
    environment.update(CLASS_B_FIXED_VALUES)
    environment["GIT_CONFIG_GLOBAL"] = no_config
    return environment


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
    _store: ProjectStore

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
        settings = [("core.hooksPath", no_hooks_directory(self._store)), *CLASS_B_CONFIGURATION]
        arguments: list[str] = []
        for key, value in settings:
            arguments += ["-c", f"{key}={value}"]
        return tuple(arguments)

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
        empty = no_config_file(self._store)
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
        return gitcmd.run_git(self.root, *self.configuration_arguments(), *args, check=check, env=environment)

    def run_bytes(self, *args: str) -> gitcmd.GitBytes:
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
        reading, and a read writes no commit and touches no index.
        """
        return gitcmd.run_git_bytes(self.root, *self.configuration_arguments(), *args, env=self.environment())


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


def _require_no_grafts(store: ProjectStore) -> None:
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
    grafts = store.root / ".git" / "info" / "grafts"
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
    identity = capture_identity(store.root)
    _require_no_grafts(store)
    built = HermeticGit(
        root=store.root,
        identity=identity,
        promisor_remotes=(),
        _no_config=no_config_file(store),
        _store=store,
    )
    _require_not_shallow(built)
    return replace(built, promisor_remotes=_promisor_remotes(built))
