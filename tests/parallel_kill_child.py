"""Child process for the r6 review tests (not a test module): one parallel START of a Solver-integrating Work that
dies (os._exit, no cleanup of any kind) right after the gitlink checkout's ref was moved by ``_move_checkout``."""

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


def main() -> None:
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    store = ProjectStore(Path(spec["root"]))
    original = gitcmd.run_git

    def dying(repo, *args, **kwargs):
        out = original(repo, *args, **kwargs)
        if repo is not None and str(repo).replace("\\", "/").endswith("/solver") and args[:2] == ("update-ref", "refs/heads/main"):
            os._exit(23)  # the ref moved; the working tree and index state is whatever it is now
        return out

    gitcmd.run_git = dying

    def change(ctx):
        (Path(spec["signals"]) / "executor-ran").write_text("1", encoding="utf-8")
        (ctx.workspace / "engine.cpp").write_text("int v = 2;\n", encoding="utf-8")
        return st.Completed(("engine.cpp",), "feat(solver): v = 2")

    workspace = par.WorkspaceSpec(repo=store.root / "solver", root=Path(spec["ws_root"]), regenerable=("bin", "bin/*"),
                                  branch_prefix="feature/", integrate=par.IntegrateSpec("solver", push_remote="origin"))
    st.start(store, spec["work_id"], "single-work", change, parallel=True, workspace=workspace)


if __name__ == "__main__":
    main()
