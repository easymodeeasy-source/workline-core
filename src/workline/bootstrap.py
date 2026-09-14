"""Project-side bootstrap Skill (Workline infrastructure, not a domain Skill).

A Workline Project is opened directly in Claude Code for day-to-day work, so
it needs one discoverable entry point of its own. That entry point is a single
very thin Skill at ``.claude/skills/workline/SKILL.md``:

* it holds no Workline operation semantics and is not a copy of any canonical
  Skill;
* it never embeds the Workline root — that comes from ``.workline/project.yaml``;
* it knows exactly one stable ID, ``skills/project-router``, and no Skill
  inventory, so a Skill added to the Workline root reaches every Project
  without any Project being touched.

This module owns the bootstrap's canonical text, the conflict decision for an
existing file, and the backfill path for Projects created before the bootstrap
existed. Backfill is ordinary maintenance, so — unlike Project開始, whose
initial commit deliberately needs no push — it commits *and* pushes when a
remote exists, otherwise a clone would not receive it.

An interrupted backfill is finished by running it again, and that run looks for
its own unfinished record before it looks at the bootstrap: the bootstrap is a
fixed text, so a matching, tracked file says nothing about who put it there
(:func:`_unfinished_backfill`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from . import gitcmd, gitops
from .errors import ReconcileRequired, StopError
from .mutation import CLOSED_RECORD_FIELDS, Effect, Mutation, MutationController, WriteScope, abandon_on_stop
from .oplock import project_operation
from .registry import PROJECT_ROUTER_SKILL_ID, validate_registry
from .store import BOOTSTRAP_REL_PATH, WORKLINE_DIR, ProjectStore
from .validate import validate_project_yaml

OWNER = "bootstrap-backfill"
BACKFILL_COMMIT_MESSAGE = "chore(workline): add project bootstrap skill"

ABSENT = "absent"
MATCHING = "matching"
CONFLICT = "conflict"

BOOTSTRAP_SKILL_NAME = "workline"

_BOOTSTRAP_TEXT = """---
name: workline
description: Workline の入口。established Workline Project（root に .workline/project.yaml がある）で Workline の作業をするときに使う。計画・現在地の確認・登録済み作業の実行など、Workline が扱う操作すべてが対象。このSkillはWorkline処理を一切持たず、.workline/project.yaml が指すWorkline rootのregistryから canonical router を解決して委譲するだけの薄いbootstrapである。どのSkillを使うかはregistryから動的に決まる。
---

# Workline bootstrap

このSkillはWorkline操作の実処理を持たない。current Projectからcanonical Workline authorityへ到達するためだけに存在する。

このファイルが守る制約:

- Workline rootのabsolute pathをここへ書かない。必ず `.workline/project.yaml` から解決する。
- `skills/project-router` 以外のWorkline Skill IDをここは知らない。Skill一覧・Skill対応表をここへ保存しない。
- Workline operation semanticsをここへ複製しない。

## 手順

1. current Project rootに `.workline/project.yaml` が存在することを確認する。
   無ければこのrootはestablished Workline Projectではない。STOPして報告する。
   ここでProjectを初期化しない。初期化はWorkline root側から行うpre-project操作である。

2. `.workline/project.yaml` からconfigured Workline rootを取得する。

3. そのWorkline rootの `registry.md` を読む。

4. registryを正式なWorkline routing規則でvalidateする。通らなければSTOPする。

5. stable ID `skills/project-router` を一意解決する。
   0件・複数件・broken targetはSTOP。filename / mtime / Git上の新しさ / 意味類似で代替しない。

6. routing先のcanonical `SKILL.md` を読む。

7. 以降はそのcanonical routerの指示に従う。current requestに対応するSkillの選択はrouterが行う。

## canonical implementation first

Workline rootにこの処理のcanonical implementationが存在する場合は、必ずそれを使用する。

このSKILL本文を根拠に、registry parsing / routing / validation / filesystem構造を独自に再実装しない。
実装の存在確認より先に手作業でファイルを作り始めない。

canonical implementationが使用不能な場合は、manual fallbackへ進まずSTOPして報告する。
"""


def render_bootstrap() -> str:
    """The canonical bootstrap text. Byte-compared for conflict detection."""
    return _BOOTSTRAP_TEXT


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n")


def bootstrap_path(store: ProjectStore) -> Path:
    return store.root / BOOTSTRAP_REL_PATH


def bootstrap_state(store: ProjectStore) -> str:
    """``absent`` | ``matching`` | ``conflict`` for the Project's bootstrap.

    ``conflict`` means a file already occupies the bootstrap path with content
    that is not the expected bootstrap: ownership is unknown, so it is never
    overwritten.
    """
    path = bootstrap_path(store)
    if not path.exists():
        return ABSENT
    if not path.is_file():
        return CONFLICT
    try:
        current = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return CONFLICT
    return MATCHING if _normalize(current) == _normalize(render_bootstrap()) else CONFLICT


def bootstrap_tracked(store: ProjectStore) -> bool:
    result = gitcmd.run_git(store.root, "ls-files", "--", BOOTSTRAP_REL_PATH, check=False)
    return result.ok and bool(result.stdout.strip())


def ensure_bootstrap_committable(store: ProjectStore) -> None:
    """STOP when the Project's Git config would silently drop the bootstrap.

    ``git add`` refuses an ignored path, so an ignored bootstrap could never be
    committed and would never reach a clone. That is reported as a STOP rather
    than discovered as a raw Git failure mid-commit.
    """
    ignored = gitcmd.is_ignored(store.root, BOOTSTRAP_REL_PATH)
    if ignored is None:
        raise StopError(
            f"cannot determine whether {BOOTSTRAP_REL_PATH} is ignored by the Project repository; STOP",
            code="bootstrap_path_unclear",
        )
    if ignored:
        raise StopError(
            f"{BOOTSTRAP_REL_PATH} is ignored by the Project's .gitignore, so the bootstrap could not be "
            "committed or reach a clone; STOP",
            code="bootstrap_path_ignored",
        )


def bootstrap_conflict_error() -> StopError:
    return StopError(
        f"{BOOTSTRAP_REL_PATH} already exists with different content; ownership unknown, not overwriting",
        code="bootstrap_conflict",
    )


def is_established_project(store: ProjectStore) -> bool:
    """A Project whose canonical state is present, valid and tracked."""
    if not store.project_yaml.is_file():
        return False
    if validate_project_yaml(store):
        return False
    try:
        store.read_roadmap_relations()
        store.read_related()
        store.read_events()
    except StopError:
        return False
    tracked = gitcmd.run_git(store.root, "ls-files", "--", f"{WORKLINE_DIR}/project.yaml", check=False)
    return tracked.ok and bool(tracked.stdout.strip())


@dataclass(frozen=True)
class BackfillResult:
    status: str  # "created" | "already_present"
    project_root: Path
    mutation_id: str | None
    head: str | None
    pushed: bool = False
    resumed: bool = False


def backfill_bootstrap(project_root: Path) -> BackfillResult:
    """Add the bootstrap Skill to an already-established Workline Project.

    Only the bootstrap file is written. ``.workline`` is not re-initialized,
    ``project.yaml`` is not rewritten, and no Roadmap / Phase / Work /
    relation / event is touched. Idempotent: an already-matching bootstrap is
    reported as ``already_present``. A differing file at the bootstrap path
    STOPs. Other Skills under ``.claude/skills`` are never read or modified.

    A backfill left unfinished is resumed as the same mutation before any of
    that is decided, or refused when the record cannot show the bootstrap it
    left is its own (:func:`_unfinished_backfill`).
    """
    root = Path(project_root)
    if not root.is_dir():
        raise StopError(f"Project root is not a directory: {root}", code="project_root_missing")
    root = root.resolve()

    store = ProjectStore(root)
    if gitcmd.toplevel(root) != root:
        raise StopError(
            f"Project root is not the Git top-level; backfill needs an established Project repository: {root}",
            code="not_a_project",
        )
    with project_operation(store, OWNER):
        return _backfill_locked(store, root)


def _backfill_locked(store: ProjectStore, root: Path) -> BackfillResult:
    if not is_established_project(store):
        raise StopError(
            "not a valid established Workline Project (project.yaml missing, invalid or untracked); "
            "backfill does not initialize a Project",
            code="not_a_project",
        )

    workline = store.workline_root()
    validation = validate_registry(workline)
    if not validation.ok:
        detail = "; ".join(f"{p.code}: {p.message}" for p in validation.problems)
        raise StopError(f"registry validation failed: {detail}", code="registry_invalid")

    invocation = {"operation": OWNER, "project_root": str(root)}
    # Before anything current state could decide: a bootstrap this backfill left behind looks exactly like
    # one that was already there.
    unfinished = _unfinished_backfill(store, invocation)
    state = bootstrap_state(store)
    if unfinished is None:
        if state == CONFLICT:
            raise bootstrap_conflict_error()
        if state == MATCHING and bootstrap_tracked(store):
            return BackfillResult("already_present", root, None, gitcmd.head_commit(root))
    elif not unfinished["effects"] and _committed_as_expected(store):
        return _close_undecided(store, root, invocation)
    else:
        _refuse_unowned_bootstrap(store, unfinished)
        if state == CONFLICT:
            raise bootstrap_conflict_error()

    ensure_bootstrap_committable(store)

    owned = [BOOTSTRAP_REL_PATH]
    destination = gitops.ensure_push_destination(store)
    controller = MutationController(store)
    mutation = controller.open(OWNER, invocation, WriteScope(files=tuple(owned)))

    with abandon_on_stop(mutation):
        gitops.ensure_git_ready(root)
        preexisting = gitops.record_preexisting_dirty(
            mutation, root, exclude=(BOOTSTRAP_REL_PATH,) if state == MATCHING else ()
        )
        gitops.ensure_separable(preexisting, owned)

    if state == ABSENT and not mutation.has_stage("bootstrap"):
        mutation.add_effects("bootstrap", [Effect.write_file(BOOTSTRAP_REL_PATH, render_bootstrap())])
    mutation.apply()
    gitops.finalize(mutation, "commit", BACKFILL_COMMIT_MESSAGE, owned, destination=destination)

    _postcheck(store, owned, preexisting, mutation)
    mutation.complete()
    return BackfillResult(
        "created", root, mutation.id, gitcmd.head_commit(root),
        pushed=destination is not None, resumed=mutation.resumed,
    )


# --------------------------------------------------------------------------- an unfinished backfill

#: The top-level fields of a recovery record the Mutation Controller began and has not closed.
_PENDING_FIELDS = CLOSED_RECORD_FIELDS - {"completed_at"}
_EFFECT_FIELDS = frozenset({"seq", "stage", "kind", "payload", "applied"})
#: Where a decided effect records the branch it was decided on (:mod:`workline.mutation`, BL-036).
_DECIDED_ON = "decided_on"
_COMMIT_ID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
_BRANCH_REF = re.compile(r"refs/heads/\S+")
#: Every order of stages a backfill records: the bootstrap it decided to write (only when there was none),
#: then the commit and, with a remote, the push.
_RECORDED_SHAPES = (
    (),
    (("bootstrap", "write_file"),),
    (("bootstrap", "write_file"), ("commit", "git_commit")),
    (("bootstrap", "write_file"), ("commit", "git_commit"), ("commit", "git_push")),
    (("commit", "git_commit"),),
    (("commit", "git_commit"), ("commit", "git_push")),
)


def _unfinished_backfill(store: ProjectStore, invocation: dict) -> dict | None:
    """This Project's unfinished backfill record, if there is one; STOP when it cannot be shown to be this backfill.

    The bootstrap is one fixed text, so its being present, matching and tracked
    says nothing about who put it there: an interrupted backfill leaves exactly
    the bootstrap anyone else would. Whether this backfill still has something
    of its own to finish is therefore asked of the recovery records first, and
    only then of the bootstrap - otherwise a bootstrap the backfill staged but
    never committed, or committed but never pushed, is reported as already
    present and the record stays pending for good.

    The records are looked for by owner, not by the exact invocation: a runtime
    area belongs to one Project, so every backfill record in it was left by a
    backfill of this Project, and one the exact invocation would not find - the
    Project was moved, or the record was written for another root - is refused
    rather than passed over. Refused as well, with nothing written: more than
    one record, and a record in another shape than a backfill writes
    (:func:`_unprovable_record`), including one that decided another bootstrap
    than this implementation writes.
    """
    pending = [record for record in MutationController(store).list_pending() if record["owner"] == OWNER]
    if not pending:
        return None
    ids = ", ".join(sorted(record["mutation_id"] for record in pending))
    if len(pending) > 1:
        raise ReconcileRequired(
            f"{len(pending)} unfinished bootstrap backfills ({ids}): which of them decided the bootstrap cannot be "
            "shown, so none is continued and they are left untouched: reconcile required"
        )
    record = pending[0]
    if record["invocation"] != invocation:
        raise ReconcileRequired(
            f"the unfinished bootstrap backfill {ids} was recorded for another invocation "
            f"({record['invocation']!r}) than this one ({invocation!r}), as a Project that was moved leaves it; "
            "it is not continued as this one and is left untouched: reconcile required"
        )
    problem = _unprovable_record(record)
    if problem is not None:
        raise ReconcileRequired(
            f"the unfinished bootstrap backfill {ids} {problem}, so it cannot be shown to be what this backfill "
            "recorded; it is not continued and is left untouched: reconcile required"
        )
    return record


def _unprovable_record(record: dict) -> str | None:
    """Why ``record`` is not in the shape a backfill records; None when it is.

    Checked against what a backfill writes and nothing looser: its fields, its
    write scope, no reserved ID, only the note of pre-existing changes, and
    effects in one of the orders it records them (:data:`_RECORDED_SHAPES`),
    applied in order. The bootstrap it decided to write must be the text this
    implementation writes - a record left by an implementation with another
    bootstrap is not finished with this one's. A commit it recorded and has
    not made must name its branch: a record written before commits carried
    their branch does not show where the commit goes.
    """
    if set(record) != _PENDING_FIELDS:
        return "holds other fields than a backfill record"
    if record["write_scope"] != {"entities": [], "files": [BOOTSTRAP_REL_PATH]}:
        return "declares another write scope than the bootstrap"
    if record["reserved_ids"] != {}:
        return "reserved IDs, which a backfill never does"
    notes = record["notes"]
    if not isinstance(notes, dict) or not set(notes) <= {"preexisting_dirty"}:
        return "holds notes a backfill does not write"
    effects = record["effects"]
    if not isinstance(effects, list) or not all(isinstance(effect, dict) for effect in effects):
        return "holds effects a backfill does not record"
    for index, effect in enumerate(effects):
        allowed = _EFFECT_FIELDS | ({_DECIDED_ON} if effect.get("kind") == "write_file" else frozenset())
        if not _EFFECT_FIELDS <= set(effect) <= allowed or effect["seq"] != index + 1:
            return "holds effects a backfill does not record"
    if tuple((effect["stage"], effect["kind"]) for effect in effects) not in _RECORDED_SHAPES:
        return "recorded other stages than a backfill does"
    applied = [effect["applied"] is True for effect in effects]
    if any(later and not earlier for earlier, later in zip(applied, applied[1:])):
        return "holds an effect applied after one that is not"
    for effect in effects:
        payload = effect["payload"]
        if not isinstance(payload, dict):
            return "holds effects a backfill does not record"
        if effect["kind"] == "write_file":
            if set(payload) != {"path", "content"} or payload["path"] != BOOTSTRAP_REL_PATH:
                return "decided to write something other than the bootstrap"
            if not isinstance(payload["content"], str) or _normalize(payload["content"]) != _normalize(render_bootstrap()):
                return "decided a bootstrap other than the one this Workline implementation writes"
        elif effect["kind"] == "git_commit":
            base, branch = payload.get("base_head"), payload.get("branch")
            if (
                not set(payload) <= {"message", "paths", "base_head", "branch"}
                or payload.get("message") != BACKFILL_COMMIT_MESSAGE
                or payload.get("paths") != [BOOTSTRAP_REL_PATH]
                or not isinstance(base, str) or not _COMMIT_ID.fullmatch(base)
                or "branch" in payload and not (isinstance(branch, str) and _BRANCH_REF.fullmatch(branch))
            ):
                return "recorded another commit than the bootstrap commit a backfill makes"
            if "branch" not in payload and effect["applied"] is not True:
                return ("recorded a commit it has not made without the branch it goes on, as a record written before "
                        "commits carried their branch does")
        elif effect["kind"] == "git_push":
            if set(payload) != {"remote", "branch", "locator"} or not all(
                isinstance(value, str) and value for value in payload.values()
            ):
                return "recorded another push than a backfill does"
    return None


def _committed_as_expected(store: ProjectStore) -> bool:
    """Whether HEAD holds the expected bootstrap with nothing of it changed in the index or the worktree."""
    root = store.root
    return (
        bootstrap_state(store) == MATCHING
        and gitcmd.head_paths(root, BOOTSTRAP_REL_PATH) == [BOOTSTRAP_REL_PATH]
        and not gitcmd.changed_against_head(root, [BOOTSTRAP_REL_PATH])
    )


def _close_undecided(store: ProjectStore, root: Path, invocation: dict) -> BackfillResult:
    """Close an unfinished backfill that decided nothing, now that the bootstrap is committed without it.

    The record holds no effect - the backfill stopped before it decided to
    write, commit or push anything - so none of the committed bootstrap is its
    doing and nothing of it is left to finish. It is closed the way an intent
    that never recorded an effect is (:meth:`Mutation.abandon`), and the result
    is the one a Project without the record gets: nothing is committed or
    pushed, and a commit someone else made stays theirs.
    """
    mutation = MutationController(store).open(OWNER, invocation, WriteScope(files=(BOOTSTRAP_REL_PATH,)))
    mutation.abandon()
    return BackfillResult("already_present", root, None, gitcmd.head_commit(root))


def _refuse_unowned_bootstrap(store: ProjectStore, record: dict) -> None:
    """STOP, before anything is replayed, when the bootstrap Git holds cannot be shown to be this backfill's commit.

    A backfill decides the bootstrap only while HEAD has none, and commits it
    only through the commit it recorded. What HEAD holds is shown to be that
    commit only when the record holds the commit as made - it is saved right
    after the commit succeeded - and the one commit since the recorded base
    that changed the bootstrap is it: its message and nothing but the
    bootstrap. Anything else is not taken for it:

    * HEAD holds the bootstrap while the record has not decided or not made its
      commit. It may be this backfill's own commit, made just before an
      interruption kept it from being recorded as made, or an identical one
      someone else committed; the text cannot tell them apart, and resuming
      would push the latter as this backfill's own (the Mutation Controller
      classifies a commit whose paths hold nothing left to commit as made,
      which for a fixed text shows no ownership);
    * the bootstrap was changed by another commit, or by more than one, since
      the base of the commit the record holds as made.
    """
    effects = record["effects"]
    if not effects:
        return
    root = store.root
    commit = next((effect for effect in effects if effect["kind"] == "git_commit"), None)
    ids = record["mutation_id"]
    if commit is None or commit["applied"] is not True:
        if gitcmd.head_paths(root, BOOTSTRAP_REL_PATH) != []:
            raise ReconcileRequired(
                f"the unfinished bootstrap backfill {ids} has not recorded its commit as made, yet HEAD already holds "
                "the bootstrap: that may be its own commit made just before an interruption or an identical one "
                "committed by someone else, and a fixed text cannot tell them apart, so nothing is replayed, committed "
                "or pushed as its own: reconcile required"
            )
        return
    payload = commit["payload"]
    changed_by = gitcmd.commits_touching(root, payload["base_head"], "HEAD", [BOOTSTRAP_REL_PATH])
    if changed_by is None or len(changed_by) != 1 or not _is_backfill_commit(root, changed_by[0], payload):
        raise ReconcileRequired(
            f"the unfinished bootstrap backfill {ids} recorded its commit as made, but since its base the bootstrap "
            "was not changed by that one commit alone, so what HEAD holds is not shown to be it; nothing is replayed "
            "or pushed: reconcile required"
        )


def _is_backfill_commit(root: Path, commit: str, payload: dict) -> bool:
    """Whether ``commit`` carries the recorded message and changes nothing but the recorded paths."""
    message = gitcmd.run_git(root, "log", "-1", "--format=%B", commit, check=False)
    return message.ok and message.stdout.strip() == payload["message"].strip() and _changed_by(root, commit) == set(payload["paths"])


def _changed_by(root: Path, commit: str) -> set[str] | None:
    shown = gitcmd.run_git(root, "show", "--name-only", "--format=", "-z", commit, check=False)
    if not shown.ok:
        return None
    return {p.replace("\\", "/") for p in shown.stdout.split("\0") if p.strip()}


def _postcheck(store: ProjectStore, owned: list[str], preexisting: list[str], mutation: Mutation) -> None:
    root = store.root
    if bootstrap_state(store) != MATCHING:
        raise StopError("postcheck: bootstrap content is not the expected bootstrap", code="postcheck_failed")
    if not bootstrap_tracked(store):
        raise StopError("postcheck: bootstrap is not tracked", code="postcheck_failed")
    if gitcmd.changed_against_head(root, owned):
        raise StopError("postcheck: bootstrap differs from HEAD", code="postcheck_failed")

    # The backfill commit is found in the history since the base its commit was recorded on - not as HEAD having
    # moved during this run: a resumed backfill whose commit was already made, or made by the replay before this
    # point, has nothing left to move HEAD.
    commits = [effect for effect in mutation.effects if effect["kind"] == "git_commit"]
    base = commits[0]["payload"].get("base_head") if len(commits) == 1 else None
    made = gitcmd.commits_touching(root, base, "HEAD", owned) if isinstance(base, str) else None
    if not made:
        raise StopError("postcheck: backfill commit missing", code="postcheck_failed")
    if len(made) != 1:
        raise StopError(
            "postcheck: the bootstrap was changed by more than the backfill commit since that commit was recorded",
            code="postcheck_failed",
        )
    changed = _changed_by(root, made[0]) or set()
    if changed != set(owned):
        raise StopError(
            "postcheck: backfill commit touched more than the bootstrap: " + ", ".join(sorted(changed - set(owned))),
            code="postcheck_failed",
        )

    problems = validate_project_yaml(store)
    if problems:
        raise StopError("postcheck: " + "; ".join(p.message for p in problems), code="postcheck_failed")
    still_dirty = set(gitops.capture_preexisting_dirty(root))
    lost = sorted(set(preexisting) - still_dirty)
    if lost:
        raise StopError("postcheck: unrelated changes were consumed: " + ", ".join(lost), code="postcheck_failed")
