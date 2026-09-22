"""Git safety helpers shared by operation owners.

* pre-existing dirty state is captured at operation entry and never staged;
* an operation whose commit could never be separated from that state is
  refused before its first effect, not at its Git stage;
* only paths the current operation owns are committed;
* commit / push are recorded as mutation effects so a failure resumes from the
  Git stage without re-running domain writes;
* a push is only ever recorded for a destination the operation owner verified
  at its entry (:mod:`workline.destination`), never for whatever ``origin``
  happens to be.
"""

from __future__ import annotations

from pathlib import Path

from . import gitcmd
from .destination import DEFAULT_REMOTE, PushDestination, ensure_push_destination
from .errors import StopError
from .mutation import PLANNING_COMMIT_MODE, Effect, Mutation, abandon_on_stop
from .store import RUNTIME_DIR, ProjectStore

__all__ = [
    "DEFAULT_REMOTE",
    "OVERLAP_MESSAGE",
    "PushDestination",
    "canonical_dirty_paths",
    "capture_preexisting_dirty",
    "ensure_git_ready",
    "ensure_push_destination",
    "ensure_separable",
    "ensure_separable_before_effects",
    "finalize",
    "finalize_effects",
    "is_runtime_path",
    "narrow_preexisting_dirty",
    "preexisting_dirty_snapshot",
    "record_preexisting_dirty",
    "require_no_planning_transform",
    "review_commit_effect",
    "review_publication_effect",
]


def is_runtime_path(path: str) -> bool:
    return path == RUNTIME_DIR or path.startswith(RUNTIME_DIR + "/")


def capture_preexisting_dirty(repo: Path) -> list[str]:
    """Dirty paths that are not Workline runtime metadata."""
    return sorted(p for p in gitcmd.dirty_paths(repo) if not is_runtime_path(p))


def preexisting_dirty_snapshot(repo: Path, *, exclude: tuple[str, ...] = ()) -> list[str]:
    """The pre-existing dirty paths an operation records as its snapshot.

    ``exclude`` drops paths the operation has already proven it owns — an
    untracked file byte-identical to an artifact this operation would write is
    not an unrelated user change, so it may be committed instead of blocking
    the operation.
    """
    return [p for p in capture_preexisting_dirty(repo) if p not in exclude]


def record_preexisting_dirty(mutation: Mutation, repo: Path, *, exclude: tuple[str, ...] = ()) -> list[str]:
    """Capture pre-existing dirty paths once per mutation (stable across resume).

    The snapshot (:func:`preexisting_dirty_snapshot`, ``exclude`` applied) is
    taken when the note is first recorded, so every later reader (including the
    Git stage) sees the same list on resume.
    """
    noted = mutation.note("preexisting_dirty")
    if noted is None:
        noted = preexisting_dirty_snapshot(repo, exclude=exclude)
        mutation.set_note("preexisting_dirty", noted)
    return list(noted)


OVERLAP_MESSAGE = "pre-existing changes overlap operation-owned paths and cannot be separated safely: "


def ensure_separable(preexisting: list[str], owned: list[str]) -> None:
    overlap = sorted(set(preexisting) & set(owned))
    if overlap:
        raise StopError(OVERLAP_MESSAGE + ", ".join(overlap), code="dirty_overlap")


def narrow_preexisting_dirty(mutation: Mutation, repo: Path) -> list[str]:
    """Drop from the recorded snapshot the paths that are not changed any more, and keep every other.

    The snapshot is taken once and never taken again
    (:func:`record_preexisting_dirty`), so that an operation can never come to
    treat what its own executor produced as a change that was there before it.
    That also means a path it names is named for the rest of the mutation, and
    the operation's commit is refused for that path however the person answers:
    after they commit their change, after they discard it, with the whole
    working tree clean. A path the snapshot names that is no longer changed has
    nothing left to be separated from, so it is dropped here and the same
    operation goes on the next time it is run.

    Only dropped, never added, and only where nothing of this run has been
    written yet: the set may shrink as the person resolves their changes, and
    can never grow to cover what the operation itself produced.

    A path is never dropped because this mutation wrote it. The snapshot names
    paths and not what they held, so a path carrying both the person's change
    and the operation's own writes cannot be told apart, and dropping it would
    commit their change as part of the operation's own.
    """
    noted = record_preexisting_dirty(mutation, repo)
    if not noted:
        return noted
    current = set(capture_preexisting_dirty(repo))
    still = [path for path in noted if path in current]
    if len(still) != len(noted):
        mutation.set_note("preexisting_dirty", still)
    return still


def ensure_separable_before_effects(mutation: Mutation, paths: list[str]) -> None:
    """Refuse a mutation that has recorded no effect when a pre-existing change overlaps ``paths``.

    ``paths`` are what the operation commits whatever else it goes on to do:
    the files its first stage writes and those of every later stage it has
    already decided. Its Git stage (:func:`finalize`) refuses a commit that
    overlaps the changes that were there before the operation, and that
    snapshot is recorded once per mutation, so an operation that went on
    anyway applied its events, ran its executor, committed and pushed part of
    what it produced, and then stopped at a stage no retry could pass. The
    same refusal is made here instead, on the very snapshot the Git stage
    reads, before the first effect is recorded: the mutation is abandoned,
    and nothing is written, run, committed or pushed.

    The overlap is never separated. The operation decides on the Project as
    the working tree holds it, the person's change included, so committing
    only its own part of a file could publish a history its own preconditions
    would refuse; the person commits or discards their change, and the
    operation is run again.

    A mutation that has recorded an effect is not refused here: its snapshot
    names the paths that were dirty, not what they held, so nothing can be
    told apart or taken over, and its Git stage stays as it was.
    """
    if mutation.effects:
        return
    with abandon_on_stop(mutation):
        ensure_separable(record_preexisting_dirty(mutation, mutation.store.root), paths)


def ensure_git_ready(repo: Path) -> str:
    """Return the current branch; STOP on detached HEAD."""
    branch = gitcmd.current_branch(repo)
    if branch is None:
        raise StopError("repository is in detached HEAD state", code="detached_head")
    return branch


def finalize_effects(
    store: ProjectStore, message: str, paths: list[str], *, destination: PushDestination | None
) -> list[Effect]:
    """Build the commit effect, plus a push effect when ``destination`` is set.

    ``destination`` is the verified :class:`PushDestination` the owner obtained
    at its entry; ``None`` means this finalization does not push (a remote-less
    Project, or Project開始, whose initial commit deliberately needs no push).
    """
    repo = store.root
    effects = [
        Effect.git_commit(message, sorted(set(paths)), gitcmd.head_commit(repo), gitcmd.current_branch_ref(repo))
    ]
    if destination is not None:
        effects.append(Effect.git_push(destination.remote, ensure_git_ready(repo), destination.locator))
    return effects


def finalize(
    mutation: Mutation, stage: str, message: str, paths: list[str], *, destination: PushDestination | None
) -> None:
    """Record and apply the Git stage of ``mutation`` (idempotent on resume).

    A stage that holds a push is recorded only while the publication barrier
    is clear for HEAD, the parent of the commit it will make (``rules/git``
    Push destination): otherwise it is not recorded, and the mutation stays
    pending with its domain effects applied until the barrier clears.
    """
    store = mutation.store
    if not mutation.has_stage(stage):
        preexisting = record_preexisting_dirty(mutation, store.root)
        ensure_separable(preexisting, paths)
        if destination is not None:
            from .review import publication

            publication.require_barrier_clear(store.root, gitcmd.head_commit(store.root))
        mutation.add_effects(stage, finalize_effects(store, message, paths, destination=destination))
    mutation.apply()


# --------------------------------------------------------------------------- review-v1 planning commits

def review_commit_effect(
    store: ProjectStore,
    message: str,
    paths: list[str],
    *,
    base_head: str | None = None,
    branch: str | None = None,
    base_exact: bool = False,
) -> Effect:
    """A review-v1 planning commit: the live ``git_commit`` effect, made by the planning commit primitive.

    Generation commits and the metadata commit keep the live base rules: their
    base and branch are HEAD's when they are recorded. The registration commit
    is ``base_exact``: made only on its recorded parent ``base_head``, on the
    bound ``branch``.
    """
    repo = store.root
    effect = Effect.git_commit(
        message,
        sorted(set(paths)),
        base_head if base_head is not None else gitcmd.head_commit(repo),
        branch if branch is not None else gitcmd.current_branch_ref(repo),
    )
    effect.payload["mode"] = PLANNING_COMMIT_MODE
    if base_exact:
        effect.payload["base_exact"] = True
    return effect


def review_publication_effect(destination: PushDestination, branch: str, commit: str) -> Effect:
    """The planning push: the live three keys and the exact commit it publishes."""
    effect = Effect.git_push(destination.remote, branch, destination.locator)
    effect.payload["commit"] = commit
    return effect


def require_no_planning_transform(repo: Path, paths: list[str]) -> None:
    """Git persistence preflight, transform attributes: no filter, ident or re-encoding applies to ``paths``.

    ``git check-attr filter ident working-tree-encoding`` must print
    ``unspecified`` or ``unset`` for each, and the effective configuration must
    define no filter driver named ``unset`` or ``unspecified``: a printed word
    proves no state, and a literal ``filter=unset`` selects a driver so named.
    Anything else is ``review_git_transform``.
    """
    printed = gitcmd.check_attributes(repo, paths, ("filter", "ident", "working-tree-encoding"))
    if printed is None:
        raise StopError(
            "git check-attr cannot say whether a filter, ident or re-encoding applies to the planning paths: STOP",
            code="review_git_transform",
        )
    transformed = sorted(
        f"{path} {name}: {value}"
        for path, values in printed.items()
        for name, value in values.items()
        if value not in ("unspecified", "unset")
    )
    if transformed:
        raise StopError(
            "a Git transformation applies to review-v1 planning paths (" + "; ".join(transformed) + "); the committed "
            "blob could differ from the written bytes: STOP",
            code="review_git_transform",
        )
    drivers = gitcmd.config_names_matching(repo, r"^filter\.(unset|unspecified)\.")
    if drivers is None or drivers:
        raise StopError(
            "a filter driver named unset or unspecified is configured ("
            + (", ".join(sorted(drivers)) if drivers else "Git cannot say")
            + "), which a literal attribute value would select: STOP",
            code="review_git_transform",
        )


def canonical_dirty_paths(store: ProjectStore) -> list[str]:
    """Dirty paths under ``.workline/`` excluding the runtime area."""
    return sorted(
        p for p in gitcmd.dirty_paths(store.root, [".workline"]) if not is_runtime_path(p)
    )
