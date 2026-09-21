"""Review Core: the subordinate authorization gate, and nothing that progresses anything.

```text
Review  =  subordinate authorization / quality gate
Review  != a second lifecycle / progression controller
```

Everything here is read, validated, rendered or compared. Nothing here holds
the Project lock, opens a mutation, decides that an operation should proceed, or
writes a file. Review gate state is written by the top-level operation that uses
the gate - Roadmap's mutation owner, START's mutation owner - through the one
Mutation Controller the Project already has (``R3`` §1).

Lifecycle truth stays exactly where it was:

```text
state.py  <-  canonical entities / relations / lifecycle events
```

``ProjectView`` and ``state.py`` do not import this package, and no Review
record takes part in deriving Work, Phase or Roadmap state.

**P1 scope.** Review Core, canonical authority, the durable clone-safe gate
foundation, immutable recovery-safe persistence, the Receipt and Consumption
foundation, the three projections, the adapter foundation, the Review-validity
and Evidence completeness foundation, and structural validation.

**Not activated by P1.** Work completion is not gated by Review. START's
terminal semantics are untouched, no activation record is created, and the
``review-v1`` operation contract is defined but not switched on. P2 (Roadmap and
Phase-entry integration) and P3 (Work terminal gating, Class A, the split
publication path) are deliberately absent.
"""

from __future__ import annotations

from . import adapter, closure, gate, paths, projections, records, serialize, validate
from .paths import REVIEW_DIR, RUNTIME_REVIEW_DIR
from .projections import (
    AUTHORIZED_TRANSITION,
    OPERATION_METADATA,
    REVIEWED_ARTIFACT,
    Projection,
    ProjectionSet,
    normative,
)
from .records import (
    CandidateSnapshot,
    Consumption,
    GateGeneration,
    Receipt,
    Supersession,
    TaskInput,
    WorkTerminalActivation,
)
from .store import GateChain, ReviewStore
from .validate import ReviewProblem, validate_review

__all__ = [
    "AUTHORIZED_TRANSITION",
    "CandidateSnapshot",
    "Consumption",
    "GateChain",
    "GateGeneration",
    "OPERATION_METADATA",
    "Projection",
    "ProjectionSet",
    "REVIEWED_ARTIFACT",
    "REVIEW_DIR",
    "RUNTIME_REVIEW_DIR",
    "Receipt",
    "ReviewProblem",
    "ReviewStore",
    "Supersession",
    "TaskInput",
    "WorkTerminalActivation",
    "adapter",
    "closure",
    "gate",
    "normative",
    "paths",
    "projections",
    "records",
    "serialize",
    "validate",
    "validate_review",
]
