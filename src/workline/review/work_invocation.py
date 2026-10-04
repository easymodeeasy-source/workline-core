"""The durable markers of a review-v1 Work START, and the one predicate that reads them (``F1`` §4, ``F3`` §11.1).

A review-v1 Work START writes exactly two keys into its mutation's durable
invocation, together, at the intent's first durable write (F1-D2)::

    review_contract      = "review-v1-work-v1"
    publication_contract = "review-v1-split-v1"

and a legacy START writes neither. Every question "is this mutation a
review-v1 Work mutation?" is answered here, from the durable invocation ALONE
- never from stage shape, from files, from the presence of a Review record or
from branch state (F1-D2, R5 §12.3.2):

```text
LEGACY    no marker key at all, positively shown
WORK      operation "start" AND both markers with exactly the frozen values -
          the review contract v1, or the distinct P4 one (G-6 Option M,
          told apart by :func:`contract_of`) - AND no other marker key
INVALID   every other presence, value or combination - one marker without
          the other, an unknown value, an extra marker key, a marker on
          another operation. It fails closed wherever it is read, and it is
          never read as either of the other two.
```

The markers are compatibility metadata, never slot identity: ``operation``,
``work_id`` and ``mode`` stay the slot (F1 §4.2).
"""

from __future__ import annotations

from typing import Any

from .records import P4_WORK_CONTRACT
from .work_context import REVIEW_CONTRACT

#: F1-D2: the publication marker. F1-frozen and never renamed; the Work publication
#: VALIDATOR is a separate identity (``F3`` §4.4).
PUBLICATION_CONTRACT = "review-v1-split-v1"

#: The one operation the Work markers belong to.
OPERATION = "start"

#: The review contracts a Work START's ``review_contract`` marker may name: v1 (F1-D2), or the distinct P4
#: contract (G-6 Option M). Both share the publication marker, whose validator does not tell Review contract
#: generations apart; which one a record runs under is read with :func:`contract_of`, never inferred.
CONTRACTS = (REVIEW_CONTRACT, P4_WORK_CONTRACT)

#: Every key that is a review-v1 marker on any operation's durable invocation. A START
#: invocation carrying one of these beyond the frozen pair is contradictory metadata.
MARKER_KEYS = ("review_contract", "publication_contract", "recovery_of_review_run_id")

LEGACY = "legacy"
WORK = "work"
INVALID = "invalid"


def markers(contract: str = REVIEW_CONTRACT) -> dict[str, str]:
    """The two keys a review Work START of ``contract`` writes into its durable invocation, and nothing else."""
    if contract not in CONTRACTS:
        raise ValueError(f"not a Work review contract: {contract!r}")
    return {"review_contract": contract, "publication_contract": PUBLICATION_CONTRACT}


def classify(invocation: object) -> str:
    """``LEGACY``, ``WORK`` or ``INVALID`` for a START mutation's durable invocation.

    Read from the invocation alone. Anything that is not a mapping is
    ``INVALID``: a record whose invocation cannot be read says nothing about
    which contract it runs under, and silence is never legacy proof.
    """
    if not isinstance(invocation, dict):
        return INVALID
    present = {key for key in MARKER_KEYS if key in invocation}
    if not present:
        return LEGACY
    if (
        present == {"review_contract", "publication_contract"}
        and invocation.get("review_contract") in CONTRACTS
        and invocation.get("publication_contract") == PUBLICATION_CONTRACT
        and invocation.get("operation") == OPERATION
    ):
        return WORK
    return INVALID


def is_work(invocation: Any) -> bool:
    """Whether the durable invocation positively names a review Work contract (v1 or P4)."""
    return classify(invocation) == WORK


def contract_of(invocation: Any) -> str | None:
    """The exact review contract a review Work START's markers name (v1 or P4); None for legacy or invalid."""
    if classify(invocation) != WORK:
        return None
    return str(invocation["review_contract"])
