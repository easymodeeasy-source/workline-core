"""Child process driven by the execution lock and Project context tests (not a test module itself).

It runs one Workline operation against a Project in a separate process and
reports how that ended as one JSON line, so a test can hold the Project
execution lock in one process while another process tries to use the Project,
or continue an operation from a process of its own. The child works from the
directory the test starts it in: that is the invocation context Workline
resolves for it.
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

from workline import roadmap as rm  # noqa: E402
from workline import start as st  # noqa: E402
from workline.errors import StopError  # noqa: E402
from workline.oplock import project_operation  # noqa: E402
from workline.phase_create import PhaseSpec  # noqa: E402
from workline.store import ProjectStore  # noqa: E402

WAIT_SECONDS = 120


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
    ready = signals / f"ready-{spec['name']}"
    release = signals / f"release-{spec['name']}"
    if spec.get("wait_for"):
        _wait_for(Path(spec["wait_for"]))

    def block() -> None:
        ready.write_text("ready", encoding="utf-8")
        _wait_for(release)

    def complete_now(ctx: st.ExecutionContext):
        name = f"result_{ctx.work.display}.txt"
        (store.root / name).write_text(f"{ctx.work.name}\n", encoding="utf-8")
        return st.Completed((name,))

    def complete_after_release(ctx: st.ExecutionContext):
        block()
        return complete_now(ctx)

    def crash(ctx: st.ExecutionContext):
        ready.write_text("ready", encoding="utf-8")
        os._exit(3)

    scenario = spec["scenario"]
    mutation_id = None
    try:
        if scenario == "hold_lock":
            with project_operation(store, "test-holder"):
                block()
            outcome = "released"
        elif scenario == "start_blocking":
            outcome = st.start(store, spec["work_id"], spec.get("mode", "single-work"), complete_after_release).status
        elif scenario == "start_complete":
            result = st.start(store, spec["work_id"], spec.get("mode", "single-work"), complete_now)
            outcome, mutation_id = result.status, result.mutation_id
        elif scenario == "start_crash":
            st.start(store, spec["work_id"], "single-work", crash)
            outcome = "did not crash"
        elif scenario == "roadmap_blocking":
            real_finalize = rm._finalize

            def finalize_after_release(*args, **kwargs):
                block()
                return real_finalize(*args, **kwargs)

            rm._finalize = finalize_after_release
            plan = rm.RoadmapPlan("Second", "second background", "second desired state", {"x": PhaseSpec("X", "x done")})
            rm.create_roadmap(store, plan)
            outcome = "created"
        else:
            raise SystemExit(f"unknown scenario: {scenario}")
    except StopError as exc:
        print(json.dumps({"outcome": "stop", "code": exc.code, "message": exc.message}), flush=True)
        return
    print(json.dumps({"outcome": outcome, "code": None, "mutation_id": mutation_id}), flush=True)


if __name__ == "__main__":
    main()
