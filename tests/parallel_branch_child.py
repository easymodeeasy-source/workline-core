"""Child process for the r12 review tests (not a test module): one parallel START of a standalone Work on a
Project-named (or automatic) branch that dies (os._exit, no cleanup of any kind) at a chosen point of the creation of
its workspace.

``die`` (spec key):
  before_branch       right before the Work branch is made (the first branch-making git call, not run)
  after_branch        right after the call that made the Work branch returned
  after_worktree_add  right after ``git worktree add`` returned
  after_branch_delete right after the release's ``git branch -D`` returned (before the owned ref is removed)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from workline import gitcmd  # noqa: E402
from workline import parallel as par  # noqa: E402
from workline import start as st  # noqa: E402
from workline.store import ProjectStore  # noqa: E402


def _makes_branch(args) -> bool:
    return (args[:1] == ("update-ref",) and "--stdin" in args) or (args[:2] == ("worktree", "add") and "-b" in args)


def main() -> None:
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    store = ProjectStore(Path(spec["root"]))
    die = spec["die"]

    run_git, run_git_bytes = gitcmd.run_git, gitcmd.run_git_bytes

    def dying(call):
        def wrapped(repo, *args, **kwargs):
            if die == "before_branch" and _makes_branch(args):
                os._exit(23)
            out = call(repo, *args, **kwargs)
            if die == "after_branch" and _makes_branch(args):
                os._exit(23)
            if die == "after_worktree_add" and args[:2] == ("worktree", "add"):
                os._exit(23)
            if die == "after_branch_delete" and args[:2] == ("branch", "-D"):
                os._exit(23)
            return out
        return wrapped

    gitcmd.run_git, gitcmd.run_git_bytes = dying(run_git), dying(run_git_bytes)

    def change(ctx):
        (ctx.workspace / "a.txt").write_text("A\n", encoding="utf-8")
        return st.Completed(("a.txt",))

    st.start(store, spec["work_id"], "single-work", change, parallel=True,
             workspace=par.WorkspaceSpec(root=Path(spec["ws_root"]), branch_prefix="feature/", branch=spec["branch"]))
    os._exit(0)  # it was meant to die


if __name__ == "__main__":
    main()
