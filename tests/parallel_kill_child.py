"""Child process for the r6/r7 review tests (not a test module): one parallel START of a Solver-integrating Work
that dies (os._exit, no cleanup of any kind) at a chosen point of ``_move_checkout``.

``die`` (spec key):
  after_ref             right after the checkout's target branch was moved (default)
  before_index_replace  right before the index file of the checkout is replaced
  after_index_replace   right after it was replaced, before the journal records it
  before_lock_release   right before the checkout's index.lock is removed
  after_lock_release    right after it was removed, before the journal is closed
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


def _in_solver(path) -> bool:
    return "/solver/" in str(path).replace("\\", "/") + "/"


def main() -> None:
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    store = ProjectStore(Path(spec["root"]))
    die = spec.get("die", "after_ref")

    run_git = gitcmd.run_git

    def dying_git(repo, *args, **kwargs):
        out = run_git(repo, *args, **kwargs)
        if die == "after_ref" and repo is not None and str(repo).replace("\\", "/").endswith("/solver") \
                and args[:2] == ("update-ref", "refs/heads/main"):
            os._exit(23)
        return out

    gitcmd.run_git = dying_git

    replace = os.replace

    def dying_replace(src, dst, *rest):
        target = str(dst).replace("\\", "/")
        hit = target.endswith("/.git/index") and _in_solver(target)
        if hit and die == "before_index_replace":
            os._exit(23)
        out = replace(src, dst, *rest)
        if hit and die == "after_index_replace":
            os._exit(23)
        return out

    os.replace = dying_replace

    unlink = Path.unlink

    def dying_unlink(self, *args, **kwargs):
        hit = self.name == "index.lock" and _in_solver(self)
        if hit and die == "before_lock_release":
            os._exit(23)
        out = unlink(self, *args, **kwargs)
        if hit and die == "after_lock_release":
            os._exit(23)
        return out

    Path.unlink = dying_unlink

    def change(ctx):
        (Path(spec["signals"]) / "executor-ran").write_text("1", encoding="utf-8")
        (ctx.workspace / "engine.cpp").write_text("int v = 2;\n", encoding="utf-8")
        return st.Completed(("engine.cpp",), "feat(solver): v = 2")

    workspace = par.WorkspaceSpec(repo=store.root / "solver", root=Path(spec["ws_root"]), regenerable=("bin", "bin/*"),
                                  branch_prefix="feature/", integrate=par.IntegrateSpec("solver", push_remote="origin"))
    st.start(store, spec["work_id"], "single-work", change, parallel=True, workspace=workspace)
    os._exit(0)


if __name__ == "__main__":
    main()
