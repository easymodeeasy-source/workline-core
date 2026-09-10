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
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import gitcmd, gitops
from .errors import StopError
from .mutation import Effect, MutationController, WriteScope, abandon_on_stop
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

    state = bootstrap_state(store)
    if state == CONFLICT:
        raise bootstrap_conflict_error()
    if state == MATCHING and bootstrap_tracked(store):
        return BackfillResult("already_present", root, None, gitcmd.head_commit(root))

    ensure_bootstrap_committable(store)

    owned = [BOOTSTRAP_REL_PATH]
    controller = MutationController(store)
    invocation = {"operation": OWNER, "project_root": str(root)}
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

    head_before = gitcmd.head_commit(root)
    push = gitcmd.has_remote(root, gitops.DEFAULT_REMOTE)
    gitops.finalize(mutation, "commit", BACKFILL_COMMIT_MESSAGE, owned, push=push)

    _postcheck(store, owned, preexisting, head_before)
    mutation.complete()
    return BackfillResult(
        "created", root, mutation.id, gitcmd.head_commit(root), pushed=push, resumed=mutation.resumed
    )


def _postcheck(store: ProjectStore, owned: list[str], preexisting: list[str], head_before: str | None) -> None:
    root = store.root
    if bootstrap_state(store) != MATCHING:
        raise StopError("postcheck: bootstrap content is not the expected bootstrap", code="postcheck_failed")
    if not bootstrap_tracked(store):
        raise StopError("postcheck: bootstrap is not tracked", code="postcheck_failed")
    if gitcmd.changed_against_head(root, owned):
        raise StopError("postcheck: bootstrap differs from HEAD", code="postcheck_failed")

    head = gitcmd.head_commit(root)
    if head is None or head == head_before:
        raise StopError("postcheck: backfill commit missing", code="postcheck_failed")
    touched = gitcmd.run_git(root, "show", "--name-only", "--format=", "-z", head).stdout
    changed = {p.replace("\\", "/") for p in touched.split("\0") if p.strip()}
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
