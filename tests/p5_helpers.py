"""RB4 / P5 test helpers: the test-only P4-only-cycle seam and Human Decision Evidence inputs.

``p4_only_cycle`` is a TEST-ONLY fixture seam (Orchestrator decision on the RB4-OWNER STOP, 2026-10-04): it
patches the one default a NEW first Run binds (``p4.DEFAULT_POLICY_ID``) back to the P4 policy for the duration
of a test, so the Runs that test creates are P4-only exactly as pre-P5 code wrote them (b8621d5e). No runtime
selector, flag or environment switch exists for this; production code always binds the P5-capable default to a
new first Run (GAP-A option 3) and keeps a cycle's stored family afterwards.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator
from unittest import mock

from workline import gitcmd
from workline.review import history, p4, serialize
from workline.review.store import ReviewStore


@contextmanager
def p4_only_cycle() -> Iterator[None]:
    """Every first Run created inside binds the P4 policy, as a Run created before P5 activation did."""
    with mock.patch.object(p4, "DEFAULT_POLICY_ID", p4.POLICY_ID):
        yield


@contextmanager
def p5_only_cycle() -> Iterator[None]:
    """Every first Run created inside binds the P5 policy, as a Run created before P6 activation did.

    TEST-ONLY, mirroring :func:`p4_only_cycle` (Orchestrator ruling R6-1): production code always binds the
    P6-capable default to a new first Run; this seam lets the P5 tests keep testing P5 Runs exactly as pre-P6
    code wrote them. No runtime selector, flag or environment switch exists for it.
    """
    with mock.patch.object(p4, "DEFAULT_POLICY_ID", p4.P5_POLICY_ID):
        yield


def first_envelope(review: ReviewStore, run_id: str) -> dict[str, Any]:
    chain = review.gate_chain(run_id)
    return review.read_task_input(str(chain.generations[0].accepted_tasks[0]["task_id"])).request_envelope


def committed_paths(repo: Any, commit: str = "HEAD") -> list[str]:
    """The paths ``commit`` changes against its parent."""
    full = gitcmd.run_git(repo, "rev-parse", "--verify", commit, check=False).stdout.strip()
    return sorted(gitcmd.commit_changes(repo, full) or [])


def at_head(repo: Any, path: str) -> bool:
    """Whether HEAD's tree holds ``path``."""
    return bool(gitcmd.tree_entries(repo, gitcmd.head_commit(repo) or "", [path]))


def decision_evidence(
    review: ReviewStore,
    affected_run_id: str,
    decision: p4.HumanDecision,
    current_requirement: dict[str, Any],
    *,
    question: str = "which scope does the plan cover",
    answer: str = "the Human confirmed the scope as written",
    effect: bool | None = None,
) -> p4.DecisionEvidence:
    """A well-formed P5 evidence input for the HUMAN_WAIT Run ``affected_run_id`` and the Human ``decision``.

    Every reference is read from the canonical records exactly as a caller would: the HUMAN entries and coverage
    gaps of the Run's adjudication, its Candidate, the canonical requirement authority identity, the adjudication
    digest as the source, and - for ``requirement_changed`` (or ``effect=True``) - the current requirement digest.
    """
    chain = review.gate_chain(affected_run_id)
    adjudication = review.read_adjudication(affected_run_id)
    entries = tuple({"task_id": e["task_id"], "result_digest": e["result_digest"], "claim_index": e["claim_index"]}
                    for e in adjudication.entries if e["outcome"] == p4.OUTCOME_HUMAN)
    gaps = tuple({"task_id": g["task_id"], "surface": g["surface"]} for g in adjudication.coverage_gaps
                 if g["resolution"] in history.HUMAN_GAP_RESOLUTIONS)
    changed = decision.disposition == p4.DECISION_CHANGED
    with_effect = changed if effect is None else effect
    return p4.DecisionEvidence(
        affected_review_run_id=affected_run_id,
        affected_candidate_hash=chain.generations[0].candidate_hash,
        decision_id=decision.decision_id,
        decision_disposition=decision.disposition,
        affected_entries=entries,
        question_summary=question,
        decision_summary=answer if not changed else "the Human changed the requirement",
        authority_identity=p4.requirement_authority_identity(current_requirement),
        action_class=history.DECISION_ACTIONS[decision.disposition],
        source_digests=(serialize.digest(adjudication.to_record()),),
        affected_coverage_gaps=gaps,
        effect_digests=(serialize.digest(current_requirement),) if with_effect else (),
    )
