"""Child process for the parallel START tests (not a test module itself).

It runs one parallel START of one Work from the Project folder it is started
in, with an executor whose behaviour the spec names, and reports the result as
one JSON line. The executor leaves a signal file the moment it is entered, so
a test can prove which Work's executor ran, in which process and when.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from workline import parallel as par  # noqa: E402
from workline import start as st  # noqa: E402
from workline.errors import StopError  # noqa: E402
from workline.store import ProjectStore  # noqa: E402

WAIT_SECONDS = 180


def _wait_for(path: Path) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while not path.exists():
        if time.monotonic() > deadline:
            raise SystemExit(f"timed out waiting for {path}")
        time.sleep(0.02)


def main() -> None:
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    store = ProjectStore(Path(spec["root"]))
    signals = Path(spec["signal_dir"])
    name = spec["name"]

    def executor(ctx: st.ExecutionContext):
        entered = {"work_id": ctx.work.id, "run_id": ctx.run_id, "pid": os.getpid(), "workspace": str(ctx.workspace),
                   "attempt": ctx.attempt, "at": time.time()}
        (signals / f"entered-{name}-{ctx.attempt}.json").write_text(json.dumps(entered), encoding="utf-8")
        for rel, text in spec.get("writes", {}).items():
            target = ctx.workspace / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        if spec.get("block"):
            _wait_for(signals / f"release-{name}")
        if spec.get("crash"):
            os._exit(17)  # the executor's process dies: no cleanup of any kind runs
        return st.Completed(tuple(spec.get("writes", {})), spec.get("message"))

    if spec.get("crash_after_copy"):
        copy = par._copy_results

        def copy_then_die(*args):
            copy(*args)
            os._exit(19)  # dies inside the finish: results copied into the Project, nothing committed

        par._copy_results = copy_then_die
    if spec.get("crash_after_claim"):
        set_state = par._set

        def die_before_creating(store_, record, state, **fields):
            if state == par.CREATING:
                os._exit(23)  # the claim committed the Work's start; the run record still says claiming
            return set_state(store_, record, state, **fields)

        par._set = die_before_creating
    if spec.get("crash_after_return"):
        def die_after_return(*args):
            os._exit(29)  # the executor returned and its result is recorded; nothing of it is committed yet

        par._commit_returned = die_after_return
    workspace = par.WorkspaceSpec(root=Path(spec["workspace_root"]), regenerable=tuple(spec.get("regenerable", ())))
    try:
        if "lock_wait" in spec:
            result = par.run(store, spec["work_id"], executor, workspace, lock_wait=float(spec["lock_wait"]))
        else:
            result = st.start(store, spec["work_id"], "single-work", executor, parallel=True, workspace=workspace)
        out = {"status": result.status, "work_id": result.work_id, "detail": result.detail, "code": result.code}
    except StopError as exc:
        out = {"status": "stop", "code": exc.code, "detail": str(exc)}
    out["finished_at"] = time.time()
    print(json.dumps(out))


if __name__ == "__main__":
    main()
