"""Achievement evidence (``WORKLINE_COMPLETION_SPRINT`` §14.18 - §14.26 / §32.33 - §32.48): the pure core.

Phase completion stays generated state and ``roadmap_achieved`` stays the one
Roadmap lifecycle event. What this module adds is the evidence side, as pure
functions and strict value types:

```text
basis        one canonical Phase basis projection over structural truth, and its
             digest - the achievement record and its ID are never part of it (§32.33)
matching     current evidence = exactly one record that validates AND binds every
             field of the recomputed current basis; none -> missing / stale; more ->
             conflict; a record claiming the current basis but not binding it -> invalid (§32.34)
obligation   whether a projected post-operation state must close a Phase evidence
             obligation, and the one owner entry point that builds it (§32.35)
progression  generated complete vs progression-ready, and the startable-Phase
             narrowing both Roadmap and status use (§32.40 - §32.41)
evidence     strict phase_completion / roadmap_achievement bodies (§32.38, §32.47)
decision     RoadmapAchievementDecision, its judgement vocabulary and the
             legacy-string rule (§32.43)
H-2          the mechanical achieved preconditions over supplied facts (§32.44)
Roadmap      the Roadmap achievement basis (§32.45) and event / evidence / basis
             agreement (§32.46 step 11)
```

Inert: no lock, no mutation, no reservation, no filesystem or Git access, and
no Review history read. The I/O seams - the achievement history namespace and
its ID kind, the owner-side writer that reserves and records evidence, the
history reader ``phase_progression_ready(store, phase_id)`` relies on, and every
owner hook - belong to their owners and are recorded as deferred integration;
every function here takes the facts those seams will supply.

The persisted record's header (schema / version / history contract) is the
history owner's; the bodies here are what it carries.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

from .errors import ValidationError
from .ids import is_valid_id
from .review import records, serialize
from .review.integration import AUTHORIZING_PHASE_OUTCOMES, HUMAN_CONFIRMATION_REQUIRED, PhaseOutcome
from .store import PHASE_DESIRED_HEADING, ROADMAP_DESIRED_HEADING

if TYPE_CHECKING:  # pragma: no cover
    from .state import ProjectView
    from .store import Entity, Event

# --------------------------------------------------------------------------- identities

#: Digest material schemas. Each is part of its canonical bytes, so a change of meaning is a digest change.
SCHEMA_PHASE_BASIS = "workline-phase-achievement-basis"
SCHEMA_ROADMAP_BASIS = "workline-roadmap-achievement-basis"
SCHEMA_STRUCTURAL_VALIDATION = "workline-structural-validation"
SCHEMA_DECISION = "workline-roadmap-achievement-decision"
MATERIAL_VERSION = 1

#: The two achievement evidence kinds one versioned schema dispatches by (§14.18, §32.32).
KIND_PHASE_COMPLETION = "phase_completion"
KIND_ROADMAP_ACHIEVEMENT = "roadmap_achievement"
EVIDENCE_KINDS = (KIND_PHASE_COMPLETION, KIND_ROADMAP_ACHIEVEMENT)

VALIDATION_PASS = "pass"
VALIDATION_FAIL = "fail"

# --------------------------------------------------------------------------- matching / progression vocabulary

EVIDENCE_READY = "ready"
EVIDENCE_MISSING = "missing"
EVIDENCE_STALE = "stale"
EVIDENCE_CONFLICT = "conflict"
#: A record claims the current basis digest but does not validate or does not bind the recomputed basis (reconcile).
EVIDENCE_INVALID = "invalid"
#: The Project structure does not validate: no evidence can be current (a distinct status, never "stale").
EVIDENCE_STRUCTURE_INVALID = "structure_invalid"
EVIDENCE_STATUSES = (
    EVIDENCE_READY, EVIDENCE_MISSING, EVIDENCE_STALE, EVIDENCE_CONFLICT, EVIDENCE_INVALID, EVIDENCE_STRUCTURE_INVALID,
)

# --------------------------------------------------------------------------- Roadmap judgement (§32.43)

JUDGEMENT_ACHIEVED = "achieved"
JUDGEMENT_HUMAN_CONFIRMATION_REQUIRED = "human_confirmation_required"
JUDGEMENT_NOT_ACHIEVED = "not_achieved"
JUDGEMENT_DESIRED_STATE_CHANGE_REQUIRED = "desired_state_change_required"
JUDGEMENTS = (
    JUDGEMENT_ACHIEVED, JUDGEMENT_HUMAN_CONFIRMATION_REQUIRED, JUDGEMENT_NOT_ACHIEVED,
    JUDGEMENT_DESIRED_STATE_CHANGE_REQUIRED,
)
#: The legacy string judgements ``roadmap.evaluate_achievement`` accepts, mapped to the structured vocabulary.
#: They map one to one onto the ``AchievementResult`` statuses, which are the structured judgements themselves.
LEGACY_JUDGEMENTS: Mapping[str, str] = {
    "achieved": JUDGEMENT_ACHIEVED,
    "human_confirmation": JUDGEMENT_HUMAN_CONFIRMATION_REQUIRED,
    "not_achieved": JUDGEMENT_NOT_ACHIEVED,
    "desired_state_change": JUDGEMENT_DESIRED_STATE_CHANGE_REQUIRED,
}

#: The Roadmap lifecycle event an achieved decision records; its schema is unchanged by RB5 (§14.24).
ROADMAP_ACHIEVED_EVENT = "roadmap_achieved"
#: The existing Project operation an achieved write runs inside (§32.46 step 1).
ROADMAP_ACHIEVEMENT_OPERATION = "roadmap-achievement"

#: A structured, public-safe identity label (evaluator identity / version, evidence reference, role).
_LABEL_LIMIT = records.P4_MAX_LABEL
_LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/+-]*")


def _invalid(message: str) -> ValidationError:
    return ValidationError(message, code="review_record_invalid")


def _mode_reviewed() -> str:
    from .phase_integration import MODE_REVIEWED

    return MODE_REVIEWED


def _mode_legacy() -> str:
    from .phase_integration import MODE_LEGACY

    return MODE_LEGACY


# --------------------------------------------------------------------------- small strict checks

def _label_problem(value: object, described: str) -> str | None:
    problem = records.public_safe_problem(value, limit=_LABEL_LIMIT)
    if problem is not None:
        return f"{described} is not a public-safe label: {problem}"
    if _LABEL_RE.fullmatch(str(value)) is None:
        return f"{described} {value!r} is not a structured identity (no prose, no whitespace)"
    return None


def _text_problem(value: object, described: str) -> str | None:
    problem = records.public_safe_problem(value)
    return None if problem is None else f"{described} is not H-3 public-safe text: {problem}"


def _digest_problem(value: object, described: str) -> str | None:
    if not isinstance(value, str) or records.DIGEST_RE.fullmatch(value) is None:
        return f"{described} {value!r} is not a lowercase hex SHA-256"
    return None


def _id_problem(value: object, kind: str, described: str) -> str | None:
    if not isinstance(value, str) or not is_valid_id(value, kind):
        return f"{described} {value!r} is not a {kind} ID"
    return None


def _sorted_unique_problem(items: Sequence[Any], described: str) -> str | None:
    try:
        ordered = list(items) == sorted(set(items))
    except TypeError:
        ordered = False
    return None if ordered else f"{described} is not sorted and unique"


def _hashable_set(values: Iterable[Any]) -> set[Any]:
    """The hashable members of ``values``. An unhashable one is left out, never raised: its own field check reports it
    (RB5FA-1 - a strict reader turns a malformed record into ``review_record_invalid``, never a raw ``TypeError``)."""
    found: set[Any] = set()
    for value in values:
        try:
            found.add(value)
        except TypeError:
            continue
    return found


def _member(value: object, members: set[Any]) -> bool:
    """``value in members``; an unhashable ``value`` is not a member (reported by its own check, never raised)."""
    try:
        return value in members
    except TypeError:
        return False


def _exact_fields(record: object, expected: tuple[str, ...], described: str) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise _invalid(f"{described} is not a mapping")
    if set(record) != set(expected):
        missing = sorted(set(expected) - set(record))
        extra = sorted(set(record) - set(expected))
        raise _invalid(f"{described} does not hold exactly its fields (missing {missing}, unexpected {extra})")
    return record


def _require_list(record: dict[str, Any], key: str, described: str) -> list[Any]:
    value = record[key]
    if not isinstance(value, list):
        raise _invalid(f"{described} {key} is not a list")
    return value


# --------------------------------------------------------------------------- structural validation material

def structural_validation_material(problems: Iterable[Any]) -> dict[str, Any]:
    """The canonical record of one structural validation result: pass / fail and the exact problems, sorted."""
    found = sorted({(str(problem.code), str(problem.message)) for problem in problems})
    return {
        serialize.SCHEMA_KEY: SCHEMA_STRUCTURAL_VALIDATION, serialize.VERSION_KEY: MATERIAL_VERSION,
        "result": VALIDATION_FAIL if found else VALIDATION_PASS,
        "problems": [{"code": code, "message": message} for code, message in found],
    }


#: The digest of a passing structural validation. Evidence is only ever created over a passing structure, so a
#: record binding any other structural digest is not evidence (RB5C-M1).
PASS_VALIDATION_DIGEST = serialize.digest(structural_validation_material(()))


def structural_validation(view: "ProjectView") -> tuple[bool, str]:
    """Whether the canonical structure ``view`` holds validates, and the digest of that result.

    The structural validation is Project-wide (the owners' own pre / postcheck
    scope). A caller that builds several bases over one view computes it once
    and passes it in (``validation=``), so one view costs one validation.
    """
    from .validate import validate_structure

    material = structural_validation_material(validate_structure(view))
    return material["result"] == VALIDATION_PASS, serialize.digest(material)


def _desired_state_digest(text: str | None) -> str | None:
    return None if text is None else serialize.digest_of_text(text)


# --------------------------------------------------------------------------- the Phase basis (§32.33)

@dataclass(frozen=True)
class PhaseBasis:
    """One canonical Phase basis projection and its digest. Never contains achievement evidence or its ID."""

    phase_id: str
    roadmap_id: str | None
    completion_mode: str
    generated_complete: bool
    structural_validation_passed: bool
    covering_integration_ids: tuple[str, ...]
    material: Mapping[str, Any]
    digest: str

    @property
    def reviewed(self) -> bool:
        return self.completion_mode == _mode_reviewed()

    @property
    def effective_work_ids(self) -> tuple[str, ...]:
        return tuple(work["work_id"] for work in self.material["works"])

    @property
    def phase_desired_state_digest(self) -> str | None:
        return self.material["phase_desired_state_digest"]

    @property
    def structural_validation_digest(self) -> str:
        return self.material["structural_validation_digest"]

    def work_fact(self, work_id: str) -> Mapping[str, Any] | None:
        for work in self.material["works"]:
            if work["work_id"] == work_id:
                return work
        return None

    def downstream_confirmations(self, integration_id: str) -> list[dict[str, Any]]:
        """The downstream confirmations of one covering integration, with their terminal event identity."""
        states = {work["work_id"]: work for work in self.material["works"]}
        for coverage in self.material["coverage"]:
            if coverage["integration_id"] == integration_id:
                return [
                    {"work_id": work_id, "completed_event_id": states[work_id]["terminal_event_id"]}
                    for work_id in coverage["downstream_confirmation_ids"]
                ]
        raise _invalid(f"{integration_id} is not a covering integration of Phase {self.phase_id}'s current basis")


def phase_basis(view: "ProjectView", phase_id: str, *, validation: tuple[bool, str] | None = None) -> PhaseBasis:
    """§32.33: the current Phase basis over entity / event / relation truth, and its digest.

    Binds the Phase / Roadmap IDs, the Phase desired-state digest, the exact
    effective current-plan Works with their states and terminal event
    identities, the marker / completion mode, the current covering
    integrations with their exact direct coverage edges and downstream
    confirmations, and the structural validation digest. It excludes the
    achievement record and its ID, so evidence can bind it without binding
    itself; computed on a projected post-operation view it equals the value the
    same function computes on the committed state that operation leaves.
    ``validation`` is :func:`structural_validation` of the same view, when the
    caller already holds it.
    """
    from . import phase_integration as pi

    phase = view.phases.get(phase_id)
    if phase is None:
        raise _invalid(f"Phase {phase_id} does not exist")
    mode = pi.completion_mode(view, phase_id)
    covering = pi.covering_integration_ids(view, phase_id)
    passed, validation_digest = structural_validation(view) if validation is None else validation
    complete = pi.phase_generated_complete(view, phase_id)
    material = serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_PHASE_BASIS, serialize.VERSION_KEY: MATERIAL_VERSION,
        "phase_id": phase_id,
        "roadmap_id": phase.roadmap_id,
        "phase_desired_state_digest": _desired_state_digest(phase.section(PHASE_DESIRED_HEADING)),
        "phase_lifecycle": view.phase_lifecycle(phase_id),
        "completion_mode": mode,
        "generated_complete": complete,
        "works": pi.effective_work_facts(view, phase_id),
        "covering_integration_ids": list(covering),
        "coverage": [pi.coverage_facts(view, phase_id, integration_id) for integration_id in covering],
        "structural_validation_digest": validation_digest,
    })
    return PhaseBasis(phase_id, phase.roadmap_id, mode, complete, passed, covering, material,
                      serialize.digest(material))


# --------------------------------------------------------------------------- phase_completion evidence (§32.38)

@dataclass(frozen=True)
class IntegrationRunRef:
    """The Phase Integration Review references a phase_completion record binds (§32.38, ruling CPQ-05A).

    Supplied by the owner from the terminal stage it records - the integration,
    its Run, its frozen Candidate, the Receipt it consumes, the Consumption and
    the P5 consumed Run summary it writes - never looked up by newest file.
    ``integration_id`` ties the references to the covering integration. Four
    distinct digests, each of its own record (CPQ-05A):

    ```text
    candidate_hash      the exact Phase Integration Candidate hash
    run_digest          the canonical TERMINAL Review Gate digest of the Integration Run
    receipt_digest      the exact Receipt digest
    consumption_digest  the exact Consumption digest
    ```

    The current P5 Run-summary reference is kept separately -
    ``review_run_id`` + ``run_summary_digest`` - and is never the Run digest.
    """

    integration_id: str
    review_run_id: str
    candidate_hash: str
    run_digest: str
    receipt_id: str
    receipt_digest: str
    consumption_id: str
    consumption_digest: str
    run_summary_digest: str

    def to_record(self) -> dict[str, Any]:
        return {
            "integration_id": self.integration_id,
            "review_run_id": self.review_run_id, "candidate_hash": self.candidate_hash,
            "run_digest": self.run_digest,
            "receipt_id": self.receipt_id, "receipt_digest": self.receipt_digest,
            "consumption_id": self.consumption_id, "consumption_digest": self.consumption_digest,
            "run_summary_digest": self.run_summary_digest,
        }

    def problems(self) -> list[str]:
        found = [
            _id_problem(self.integration_id, "work", "integration_review integration_id"),
            _id_problem(self.review_run_id, "review_run", "integration review_run_id"),
            _digest_problem(self.candidate_hash, "integration candidate_hash"),
            _digest_problem(self.run_digest, "integration run_digest (terminal Gate digest)"),
            _id_problem(self.receipt_id, "review_receipt", "integration receipt_id"),
            _digest_problem(self.receipt_digest, "integration receipt_digest"),
            _id_problem(self.consumption_id, "review_consumption", "integration consumption_id"),
            _digest_problem(self.consumption_digest, "integration consumption_digest"),
            _digest_problem(self.run_summary_digest, "integration run_summary_digest"),
        ]
        # Distinctness is judged over the string digests only: a non-string one is already reported by its own field
        # check above and must never make this check raise (RB5FA-1).
        digests = [digest for digest in (self.candidate_hash, self.run_digest, self.receipt_digest,
                                         self.consumption_digest, self.run_summary_digest) if isinstance(digest, str)]
        if len(set(digests)) != len(digests):
            found.append("the Candidate / Run / Receipt / Consumption / P5 Run-summary digests are of five distinct "
                         "records; two of them are equal, so one is bound to the wrong record (the Run digest is the "
                         "terminal Gate digest, never the Run-summary digest)")
        return [problem for problem in found if problem is not None]


PHASE_EVIDENCE_FIELDS = (
    "kind", "achievement_evidence_id", "phase_id", "roadmap_id", "phase_desired_state_digest", "basis_digest",
    "completion_mode", "effective_work_ids", "covering_integration_id", "integration_review", "phase_outcome",
    "phase_outcome_digest", "downstream_confirmations", "structural_validation_digest", "work_review_refs",
    "no_blocking_obligation_digests", "evaluators", "rationale", "causing_operation",
)
_INTEGRATION_REF_FIELDS = (
    "integration_id", "review_run_id", "candidate_hash", "run_digest", "receipt_id", "receipt_digest",
    "consumption_id", "consumption_digest", "run_summary_digest",
)
_CONFIRMATION_FIELDS = ("work_id", "completed_event_id")
_WORK_REVIEW_FIELDS = ("work_id", "review_run_id", "run_summary_digest")
_EVALUATOR_FIELDS = ("role", "identity", "version")
_PHASE_CAUSE_FIELDS = ("mutation_id", "operation", "event_ids")


@dataclass(frozen=True)
class PhaseCompletionEvidence:
    """The strict body of one immutable ``phase_completion`` achievement record (§14.19, §32.38).

    Evidence and audit only - never lifecycle truth. ``achievement_evidence_id``
    is checked here as a public-safe identity only: its ID kind (prefix ``rha``,
    allocation A-1) is added to the ID owner after RB6 lands, and the history
    reader checks it then. ``phase_outcome_digest`` is the digest of the exact
    Phase outcome record the Integration Review judged, so the history validator
    can compare it with the Candidate's adjudication.
    """

    achievement_evidence_id: str
    phase_id: str
    roadmap_id: str
    phase_desired_state_digest: str
    basis_digest: str
    completion_mode: str
    effective_work_ids: tuple[str, ...]
    covering_integration_id: str
    integration_review: IntegrationRunRef
    phase_outcome: str
    phase_outcome_digest: str
    downstream_confirmations: tuple[tuple[str, str], ...]
    structural_validation_digest: str
    work_review_refs: tuple[tuple[str, str, str | None], ...]
    no_blocking_obligation_digests: tuple[str, ...]
    evaluators: tuple[tuple[str, str, str], ...]
    rationale: str
    causing_mutation_id: str
    causing_operation: str
    causing_event_ids: tuple[str, ...]
    kind: str = KIND_PHASE_COMPLETION

    def to_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "achievement_evidence_id": self.achievement_evidence_id,
            "phase_id": self.phase_id,
            "roadmap_id": self.roadmap_id,
            "phase_desired_state_digest": self.phase_desired_state_digest,
            "basis_digest": self.basis_digest,
            "completion_mode": self.completion_mode,
            "effective_work_ids": list(self.effective_work_ids),
            "covering_integration_id": self.covering_integration_id,
            "integration_review": self.integration_review.to_record(),
            "phase_outcome": self.phase_outcome,
            "phase_outcome_digest": self.phase_outcome_digest,
            "downstream_confirmations": [
                {"work_id": work_id, "completed_event_id": event_id} for work_id, event_id in self.downstream_confirmations
            ],
            "structural_validation_digest": self.structural_validation_digest,
            "work_review_refs": [
                {"work_id": work_id, "review_run_id": run_id, "run_summary_digest": digest}
                for work_id, run_id, digest in self.work_review_refs
            ],
            "no_blocking_obligation_digests": list(self.no_blocking_obligation_digests),
            "evaluators": [
                {"role": role, "identity": identity, "version": version} for role, identity, version in self.evaluators
            ],
            "rationale": self.rationale,
            "causing_operation": {
                "mutation_id": self.causing_mutation_id, "operation": self.causing_operation,
                "event_ids": list(self.causing_event_ids),
            },
        }

    def problems(self) -> list[str]:
        """Why this body is not a strict phase_completion record; empty when it is (no Project read)."""
        if type(self.integration_review) is not IntegrationRunRef:
            return [f"integration_review is {type(self.integration_review).__name__}, not an IntegrationRunRef"]
        found: list[str | None] = [
            None if self.kind == KIND_PHASE_COMPLETION else f"kind {self.kind!r} is not {KIND_PHASE_COMPLETION}",
            _label_problem(self.achievement_evidence_id, "achievement_evidence_id"),
            _id_problem(self.phase_id, "phase", "phase_id"),
            _id_problem(self.roadmap_id, "roadmap", "roadmap_id"),
            _digest_problem(self.phase_desired_state_digest, "phase_desired_state_digest"),
            _digest_problem(self.basis_digest, "basis_digest"),
            None if self.completion_mode == _mode_reviewed() else
            f"completion_mode {self.completion_mode!r}: phase_completion evidence is reviewed evidence only "
            "(a legacy basis never fabricates Review refs)",
            _id_problem(self.covering_integration_id, "work", "covering_integration_id"),
            None if self.phase_outcome in AUTHORIZING_PHASE_OUTCOMES else
            f"phase_outcome {self.phase_outcome!r} never completes a reviewed integration",
            _digest_problem(self.phase_outcome_digest, "phase_outcome_digest"),
            None if self.structural_validation_digest == PASS_VALIDATION_DIGEST else
            "structural_validation_digest is not the digest of a passing structural validation",
            _text_problem(self.rationale, "rationale"),
            _id_problem(self.causing_mutation_id, "mutation", "causing mutation_id"),
            _label_problem(self.causing_operation, "causing operation"),
            None if self.integration_review.integration_id == self.covering_integration_id else
            "integration_review is about another integration than the covering one",
        ]
        found += self.integration_review.problems()
        found += [_id_problem(work_id, "work", "effective_work_ids entry") for work_id in self.effective_work_ids]
        found.append(_sorted_unique_problem(self.effective_work_ids, "effective_work_ids"))
        if self.covering_integration_id not in self.effective_work_ids:
            found.append(f"covering integration {self.covering_integration_id} is not an effective Work of the basis")
        for work_id, event_id in self.downstream_confirmations:
            found += [_id_problem(work_id, "work", "downstream confirmation"),
                      _id_problem(event_id, "event", "downstream confirmation completed_event_id"),
                      None if work_id in self.effective_work_ids else
                      f"downstream confirmation {work_id} is not an effective Work of the basis"]
        found.append(_sorted_unique_problem([work_id for work_id, _ in self.downstream_confirmations],
                                            "downstream_confirmations"))
        if self.phase_outcome == HUMAN_CONFIRMATION_REQUIRED and not self.downstream_confirmations:
            found.append("human_confirmation_required completes only with a completed downstream confirmation")
        for work_id, run_id, digest in self.work_review_refs:
            found += [_id_problem(work_id, "work", "work_review_refs work_id"),
                      _id_problem(run_id, "review_run", "work_review_refs review_run_id"),
                      None if digest is None else _digest_problem(digest, "work_review_refs run_summary_digest")]
        found.append(_sorted_unique_problem([(w, r) for w, r, _ in self.work_review_refs], "work_review_refs"))
        found += [_digest_problem(digest, "no_blocking_obligation_digests entry")
                  for digest in self.no_blocking_obligation_digests]
        found.append(_sorted_unique_problem(self.no_blocking_obligation_digests, "no_blocking_obligation_digests"))
        if not self.evaluators:
            found.append("evaluators is empty: evaluator / reviewer identities and versions are required")
        for role, identity, version in self.evaluators:
            found += [_label_problem(role, "evaluator role"), _label_problem(identity, "evaluator identity"),
                      _label_problem(version, "evaluator version")]
        found.append(_sorted_unique_problem(list(self.evaluators), "evaluators"))
        found += [_id_problem(event_id, "event", "causing event_ids entry") for event_id in self.causing_event_ids]
        found.append(_sorted_unique_problem(self.causing_event_ids, "causing event_ids"))
        return [problem for problem in found if problem is not None]

    @classmethod
    def from_record(cls, record: object) -> "PhaseCompletionEvidence":
        """Strict read of a body: exactly its fields, every field of its type, and :meth:`problems` empty."""
        described = "phase_completion evidence"
        body = _exact_fields(record, PHASE_EVIDENCE_FIELDS, described)
        try:
            review = _exact_fields(body["integration_review"], _INTEGRATION_REF_FIELDS, f"{described} integration_review")
            cause = _exact_fields(body["causing_operation"], _PHASE_CAUSE_FIELDS, f"{described} causing_operation")
            confirmations = [_exact_fields(item, _CONFIRMATION_FIELDS, f"{described} downstream confirmation")
                             for item in _require_list(body, "downstream_confirmations", described)]
            work_refs = [_exact_fields(item, _WORK_REVIEW_FIELDS, f"{described} work_review_ref")
                         for item in _require_list(body, "work_review_refs", described)]
            evaluators = [_exact_fields(item, _EVALUATOR_FIELDS, f"{described} evaluator")
                          for item in _require_list(body, "evaluators", described)]
            evidence = cls(
                achievement_evidence_id=body["achievement_evidence_id"],
                phase_id=body["phase_id"],
                roadmap_id=body["roadmap_id"],
                phase_desired_state_digest=body["phase_desired_state_digest"],
                basis_digest=body["basis_digest"],
                completion_mode=body["completion_mode"],
                effective_work_ids=tuple(_require_list(body, "effective_work_ids", described)),
                covering_integration_id=body["covering_integration_id"],
                integration_review=IntegrationRunRef(**{key: review[key] for key in _INTEGRATION_REF_FIELDS}),
                phase_outcome=body["phase_outcome"],
                phase_outcome_digest=body["phase_outcome_digest"],
                downstream_confirmations=tuple((item["work_id"], item["completed_event_id"]) for item in confirmations),
                structural_validation_digest=body["structural_validation_digest"],
                work_review_refs=tuple((item["work_id"], item["review_run_id"], item["run_summary_digest"])
                                       for item in work_refs),
                no_blocking_obligation_digests=tuple(_require_list(body, "no_blocking_obligation_digests", described)),
                evaluators=tuple((item["role"], item["identity"], item["version"]) for item in evaluators),
                rationale=body["rationale"],
                causing_mutation_id=cause["mutation_id"],
                causing_operation=cause["operation"],
                causing_event_ids=tuple(_require_list(cause, "event_ids", f"{described} causing_operation")),
                kind=body["kind"],
            )
        except (TypeError, KeyError) as exc:
            raise _invalid(f"{described} does not read: {exc}") from exc
        problems = evidence.problems()
        if problems:
            raise _invalid(f"{described} is invalid: " + "; ".join(problems))
        return evidence

    @property
    def digest(self) -> str:
        """The digest of this body's canonical bytes (the persisted record digest is the history owner's)."""
        return serialize.digest(self.to_record())


def phase_evidence_basis_problems(evidence: object, basis: PhaseBasis) -> list[str]:
    """Why ``evidence`` is not valid current evidence for the recomputed ``basis``; empty when it is (RB5C-M1).

    The record must validate in itself and bind every field the basis derives:
    Phase / Roadmap IDs, basis digest, reviewed mode, desired-state digest,
    exact effective Work set, a passing structural validation, a covering
    integration that is a reviewed integration of this basis, and exactly that
    integration's completed downstream confirmations. The record's own
    ``basis_digest`` is never trusted alone.
    """
    if type(evidence) is not PhaseCompletionEvidence:
        return [f"current-basis evidence is a validated PhaseCompletionEvidence, not {type(evidence).__name__}"]
    problems = list(evidence.problems())
    if (evidence.phase_id, evidence.roadmap_id) != (basis.phase_id, basis.roadmap_id):
        problems.append("the record names another Phase / Roadmap than the basis")
    if evidence.basis_digest != basis.digest:
        problems.append(f"basis digest {evidence.basis_digest} != recomputed basis {basis.digest}")
    if not basis.reviewed or evidence.completion_mode != basis.completion_mode:
        problems.append("the basis is not a reviewed basis the record's completion mode can bind")
    if not basis.generated_complete:
        problems.append("the basis is not generated-complete")
    if not basis.structural_validation_passed or evidence.structural_validation_digest != basis.structural_validation_digest:
        problems.append("the record does not bind the basis's passing structural validation")
    if evidence.phase_desired_state_digest != basis.phase_desired_state_digest:
        problems.append("the record binds another Phase desired state than the basis")
    if tuple(evidence.effective_work_ids) != basis.effective_work_ids:
        problems.append("the record binds another effective Work set than the basis")
    covering = basis.work_fact(evidence.covering_integration_id)
    if evidence.covering_integration_id not in basis.covering_integration_ids or covering is None \
            or covering["work_kind"] != "phase_integration_check" or covering["phase_review_contract"] != _mode_reviewed():
        problems.append(f"{evidence.covering_integration_id} is not a covering reviewed integration of the basis")
    else:
        expected = tuple((item["work_id"], item["completed_event_id"])
                         for item in basis.downstream_confirmations(evidence.covering_integration_id))
        if tuple(evidence.downstream_confirmations) != expected:
            problems.append("the record binds other downstream confirmations than the basis")
    return problems


def build_phase_completion_evidence(
    achievement_evidence_id: str,
    basis: PhaseBasis,
    *,
    covering_integration_id: str,
    integration_review: IntegrationRunRef,
    phase_outcome: PhaseOutcome,
    work_review_refs: Iterable[tuple[str, str, str | None]] = (),
    no_blocking_obligation_digests: Iterable[str] = (),
    evaluators: Iterable[tuple[str, str, str]],
    rationale: str,
    causing_mutation_id: str,
    causing_operation: str,
    causing_event_ids: Iterable[str] = (),
) -> PhaseCompletionEvidence:
    """§32.35 (pure half): the phase_completion body for a projected reviewed, generated-complete basis.

    The basis supplies every structural binding - IDs, desired-state digest,
    basis digest, effective Works, downstream confirmations of the covering
    integration with their completion events, structural validation - so the
    caller cannot bind a basis other than the one it projected. The judged
    :class:`~workline.review.integration.PhaseOutcome` must be about exactly the
    basis's Phase desired state (RB5C-M2); its digest is persisted. The caller
    supplies the Review references of its own terminal stage and the identity
    of its own mutation; reserving the ID and recording the effect are the
    owner's (no second mutation is ever opened). ``work_review_refs`` may be
    empty: no RB5 path requires Review history that does not exist (no
    backfill). Owners use :func:`phase_completion_evidence_for`, which checks
    the obligation first.
    """
    if not basis.reviewed:
        raise _invalid(f"Phase {basis.phase_id} is legacy: no phase_completion evidence is created for it")
    if not basis.generated_complete:
        raise _invalid(f"Phase {basis.phase_id}'s projected basis is not generated-complete")
    if not basis.structural_validation_passed:
        raise _invalid(f"Phase {basis.phase_id}'s projected structure does not validate")
    if covering_integration_id not in basis.covering_integration_ids:
        raise _invalid(f"{covering_integration_id} does not cover Phase {basis.phase_id}'s current basis")
    if type(phase_outcome) is not PhaseOutcome:
        raise _invalid(f"the judged Phase outcome is a PhaseOutcome, not {type(phase_outcome).__name__}")
    if phase_outcome.phase_desired_state_digest != basis.phase_desired_state_digest:
        raise _invalid(f"the Integration Review judged another Phase desired state than Phase {basis.phase_id}'s "
                       "current one; no evidence certifies an objective no Review judged")
    if phase_outcome.outcome not in AUTHORIZING_PHASE_OUTCOMES:
        raise _invalid(f"phase outcome {phase_outcome.outcome!r} never completes a reviewed integration")
    evidence = PhaseCompletionEvidence(
        achievement_evidence_id=achievement_evidence_id,
        phase_id=basis.phase_id,
        roadmap_id=str(basis.roadmap_id),
        phase_desired_state_digest=str(basis.phase_desired_state_digest),
        basis_digest=basis.digest,
        completion_mode=basis.completion_mode,
        effective_work_ids=basis.effective_work_ids,
        covering_integration_id=covering_integration_id,
        integration_review=integration_review,
        phase_outcome=phase_outcome.outcome,
        phase_outcome_digest=phase_outcome.digest,
        downstream_confirmations=tuple(
            (item["work_id"], item["completed_event_id"]) for item in basis.downstream_confirmations(covering_integration_id)
        ),
        structural_validation_digest=basis.structural_validation_digest,
        work_review_refs=tuple(sorted(work_review_refs, key=lambda item: (item[0], item[1]))),
        no_blocking_obligation_digests=tuple(sorted(set(no_blocking_obligation_digests))),
        evaluators=tuple(sorted(set(evaluators))),
        rationale=rationale,
        causing_mutation_id=causing_mutation_id,
        causing_operation=causing_operation,
        causing_event_ids=tuple(sorted(set(causing_event_ids))),
    )
    problems = phase_evidence_basis_problems(evidence, basis)
    if problems:
        raise _invalid("phase_completion evidence would be invalid: " + "; ".join(problems))
    return evidence


# --------------------------------------------------------------------------- current-basis matching (§32.34)

@dataclass(frozen=True)
class EvidenceMatch:
    """The current phase_completion evidence of one Phase + basis."""

    phase_id: str
    basis_digest: str
    status: str
    matching_ids: tuple[str, ...] = ()
    historical_ids: tuple[str, ...] = ()
    invalid_ids: tuple[str, ...] = ()
    #: The one current record when ready (its body digest is what a Roadmap basis binds).
    current: PhaseCompletionEvidence | None = None

    @property
    def evidence_id(self) -> str | None:
        """The current evidence ID - only when exactly one valid record matches."""
        return self.matching_ids[0] if self.status == EVIDENCE_READY else None


def match_current_phase_evidence(basis: PhaseBasis, evidence: Iterable[PhaseCompletionEvidence]) -> EvidenceMatch:
    """§32.34 over the recomputed current ``basis``.

    Exactly one record that validates and binds every field of the basis
    (:func:`phase_evidence_basis_problems`) -> ready; none -> missing (stale when
    older-basis evidence exists); more than one -> conflict. A record that claims
    the current basis digest but does not bind the basis -> invalid (reconcile),
    never ready. A structure that does not validate -> structure_invalid, never
    stale. Selection is by Phase + basis only - never filename, mtime or newest;
    older-basis evidence is historical and never overwritten.
    """
    if type(basis) is not PhaseBasis:
        raise _invalid(f"current-basis matching takes the recomputed PhaseBasis, not {type(basis).__name__}")
    for_phase = []
    for item in evidence:
        if type(item) is not PhaseCompletionEvidence:
            raise _invalid(f"current-basis matching reads validated PhaseCompletionEvidence only, not {type(item).__name__}")
        if item.phase_id == basis.phase_id:
            for_phase.append(item)
    claiming = [item for item in for_phase if item.basis_digest == basis.digest]
    historical = tuple(sorted(item.achievement_evidence_id for item in for_phase if item.basis_digest != basis.digest))
    if not basis.structural_validation_passed:
        return EvidenceMatch(basis.phase_id, basis.digest, EVIDENCE_STRUCTURE_INVALID, (), historical,
                             tuple(sorted(item.achievement_evidence_id for item in claiming)))
    valid = sorted((item for item in claiming if not phase_evidence_basis_problems(item, basis)),
                   key=lambda item: item.achievement_evidence_id)
    invalid = tuple(sorted(item.achievement_evidence_id for item in claiming
                           if phase_evidence_basis_problems(item, basis)))
    matching = tuple(item.achievement_evidence_id for item in valid)
    if invalid:
        return EvidenceMatch(basis.phase_id, basis.digest, EVIDENCE_INVALID, matching, historical, invalid)
    if len(valid) == 1:
        return EvidenceMatch(basis.phase_id, basis.digest, EVIDENCE_READY, matching, historical, (), valid[0])
    if valid:
        return EvidenceMatch(basis.phase_id, basis.digest, EVIDENCE_CONFLICT, matching, historical)
    return EvidenceMatch(basis.phase_id, basis.digest, EVIDENCE_STALE if historical else EVIDENCE_MISSING, (),
                         historical)


# --------------------------------------------------------------------------- obligation / progression (§32.35, §32.40)

@dataclass(frozen=True)
class PhaseEvidenceObligation:
    """Whether a projected post-operation state obliges its owner to create phase_completion evidence."""

    phase_id: str
    required: bool
    reason: str
    basis: PhaseBasis
    match: EvidenceMatch | None = None


def phase_evidence_obligation(
    projected_view: "ProjectView", phase_id: str, evidence: Iterable[PhaseCompletionEvidence]
) -> PhaseEvidenceObligation:
    """§32.35 decision: required exactly when the projection is reviewed, generated-complete and has no current evidence.

    A conflicting or invalid current-basis match, or a projected structure that
    does not validate, is a reconcile failure / STOP - never a reason to write
    another record.
    """
    basis = phase_basis(projected_view, phase_id)
    if not basis.reviewed:
        return PhaseEvidenceObligation(phase_id, False, "legacy Phase: no achievement evidence obligation", basis)
    if not basis.generated_complete:
        return PhaseEvidenceObligation(phase_id, False, "projected Phase is not generated-complete", basis)
    match = match_current_phase_evidence(basis, evidence)
    if match.status == EVIDENCE_STRUCTURE_INVALID:
        raise ValidationError(f"Phase {phase_id}'s projected structure does not validate: no evidence is created over "
                              "it", code="structure_invalid")
    if match.status in (EVIDENCE_CONFLICT, EVIDENCE_INVALID):
        raise _invalid(
            f"Phase {phase_id} holds phase_completion records for one current basis that do not resolve to exactly "
            f"one valid record (valid: {', '.join(match.matching_ids) or 'none'}; invalid: "
            f"{', '.join(match.invalid_ids) or 'none'}): reconcile required, nothing more is written"
        )
    if match.status == EVIDENCE_READY:
        return PhaseEvidenceObligation(phase_id, False, f"current-basis evidence {match.evidence_id} exists", basis, match)
    return PhaseEvidenceObligation(phase_id, True, "reviewed Phase becomes generated-complete on this basis", basis, match)


def phase_completion_evidence_for(
    projected_view: "ProjectView",
    phase_id: str,
    existing_evidence: Iterable[PhaseCompletionEvidence],
    *,
    achievement_evidence_id: str,
    covering_integration_id: str,
    integration_review: IntegrationRunRef,
    phase_outcome: PhaseOutcome,
    source_ref_problems: Sequence[str],
    evaluators: Iterable[tuple[str, str, str]],
    rationale: str,
    causing_mutation_id: str,
    causing_operation: str,
    causing_event_ids: Iterable[str] = (),
    work_review_refs: Iterable[tuple[str, str, str | None]] = (),
    no_blocking_obligation_digests: Iterable[str] = (),
) -> PhaseCompletionEvidence | None:
    """The one owner-callable creation path (§32.35, RB5C-L6): obligation first, then build.

    ``None`` when the projected state creates no obligation (legacy, not
    complete, or current-basis evidence exists). Otherwise the source refs must
    have validated against canonical Review / P5 records - the history owner's
    check, whose problems the caller passes as ``source_ref_problems`` (required,
    and it must be empty) - and the body is built over the projected basis. A
    builder-only path cannot create a duplicate record through this entry.
    """
    obligation = phase_evidence_obligation(projected_view, phase_id, existing_evidence)
    if not obligation.required:
        return None
    if isinstance(source_ref_problems, (str, bytes)) or not isinstance(source_ref_problems, Sequence):
        raise _invalid("source_ref_problems is the history owner's validation result: a sequence of problems")
    if source_ref_problems:
        raise _invalid("the integration Review / P5 source refs do not validate: " + "; ".join(source_ref_problems))
    return build_phase_completion_evidence(
        achievement_evidence_id, obligation.basis, covering_integration_id=covering_integration_id,
        integration_review=integration_review, phase_outcome=phase_outcome, work_review_refs=work_review_refs,
        no_blocking_obligation_digests=no_blocking_obligation_digests, evaluators=evaluators, rationale=rationale,
        causing_mutation_id=causing_mutation_id, causing_operation=causing_operation, causing_event_ids=causing_event_ids,
    )


@dataclass(frozen=True)
class ProgressionReadiness:
    """Progression-ready is not Phase lifecycle state (§32.40)."""

    phase_id: str
    ready: bool
    completion_mode: str
    generated_complete: bool
    reason: str
    match: EvidenceMatch | None = None


_UNREADY_DETAIL = {
    EVIDENCE_MISSING: "no phase_completion evidence exists for the current basis",
    EVIDENCE_STALE: "phase_completion evidence exists only for an older basis",
    EVIDENCE_CONFLICT: "more than one phase_completion record claims the current basis",
    EVIDENCE_INVALID: "a phase_completion record claims the current basis but does not bind it (reconcile)",
}


def phase_progression_decision(
    view: "ProjectView", phase_id: str, evidence: Iterable[PhaseCompletionEvidence], *,
    validation: tuple[bool, str] | None = None,
) -> ProgressionReadiness:
    """The decision ``phase_progression_ready(store, phase_id)`` makes once its history reader supplies ``evidence``.

    Legacy Phase complete -> ready under legacy rules; reviewed Phase complete
    -> ready only with exactly one valid current-basis record; incomplete ->
    not ready. A failing Project-wide structural validation is reported as
    such, never as stale evidence. Generated state itself never reads this.
    """
    basis = phase_basis(view, phase_id, validation=validation)
    if not basis.generated_complete:
        return ProgressionReadiness(phase_id, False, basis.completion_mode, False, "Phase is not generated-complete")
    if not basis.reviewed:
        return ProgressionReadiness(phase_id, True, basis.completion_mode, True, "legacy Phase complete")
    match = match_current_phase_evidence(basis, evidence)
    if match.status == EVIDENCE_READY:
        return ProgressionReadiness(phase_id, True, basis.completion_mode, True,
                                    f"current-basis evidence {match.evidence_id}", match)
    if match.status == EVIDENCE_STRUCTURE_INVALID:
        return ProgressionReadiness(phase_id, False, basis.completion_mode, True,
                                    "the Project structure does not validate: no achievement evidence can be current",
                                    match)
    return ProgressionReadiness(
        phase_id, False, basis.completion_mode, True,
        f"generated-complete, but the achievement evidence obligation is not closed: {_UNREADY_DETAIL[match.status]} "
        f"(basis {basis.digest})", match,
    )


@dataclass(frozen=True)
class ProgressionNarrowing:
    """A startable-Phase candidate set narrowed by progression-readiness of its completed predecessors."""

    ready: tuple["Entity", ...]
    #: ``(candidate phase_id, predecessor phase_id, reason)`` for every candidate held back, in input order.
    blocked: tuple[tuple[str, str, str], ...]


def progression_ready_candidates(
    view: "ProjectView", candidates: Iterable["Entity"], evidence: Iterable[PhaseCompletionEvidence]
) -> ProgressionNarrowing:
    """RB8-FC-08 / §32.41: narrow startable-Phase candidates by progression-readiness - the one function Roadmap's
    startable wrapper and status's next-Phase projection both call.

    ``ProjectView.startable_phases`` stays pure and lifecycle-only; a candidate
    whose ``requires_completion`` predecessor Phase is complete but not
    progression-ready (:func:`phase_progression_decision`) is held back, with
    the evidence obligation as the reason - never reported as a lifecycle
    dependency. Structural validation runs once for the whole narrowing; no
    order, filename or newest rule is involved, and input order is kept.
    """
    evidence = list(evidence)
    validation = structural_validation(view)
    decisions: dict[str, ProgressionReadiness] = {}
    ready: list[Any] = []
    blocked: list[tuple[str, str, str]] = []
    for candidate in candidates:
        held = []
        for relation in sorted(view.relations_to(candidate.id, "requires_completion"), key=lambda r: r.from_id):
            if relation.from_id not in view.phases:
                continue
            if relation.from_id not in decisions:
                decisions[relation.from_id] = phase_progression_decision(view, relation.from_id, evidence,
                                                                         validation=validation)
            decision = decisions[relation.from_id]
            if not decision.ready:
                held.append((candidate.id, relation.from_id, decision.reason))
        if held:
            blocked.extend(held)
        else:
            ready.append(candidate)
    return ProgressionNarrowing(tuple(ready), tuple(blocked))


def postcommit_basis_problems(evidence: PhaseCompletionEvidence, committed: PhaseBasis) -> list[str]:
    """§32.39: the record against the basis recomputed from HEAD's committed state; empty when they agree.

    The same full binding check current-basis matching uses
    (:func:`phase_evidence_basis_problems`). A mismatch is a STOP / reconcile for
    the owner - replacement evidence is never fabricated.
    """
    return phase_evidence_basis_problems(evidence, committed)


# --------------------------------------------------------------------------- RoadmapAchievementDecision (§32.43)

@dataclass(frozen=True)
class RoadmapAchievementDecision:
    """The structured v2 Roadmap achievement decision. The caller / agent may supply ``achieved`` under H-2."""

    judgement: str
    evaluator_identity: str
    evaluator_version: str
    public_safe_rationale: str
    evidence_refs: tuple[str, ...] = ()
    human_decision_ref: str | None = None

    def problems(self) -> list[str]:
        found = [
            None if self.judgement in JUDGEMENTS else f"judgement {self.judgement!r} is not one of {', '.join(JUDGEMENTS)}",
            _label_problem(self.evaluator_identity, "evaluator_identity"),
            _label_problem(self.evaluator_version, "evaluator_version"),
            _text_problem(self.public_safe_rationale, "public_safe_rationale"),
            None if isinstance(self.evidence_refs, tuple) else "evidence_refs is not a tuple",
            None if self.human_decision_ref is None else
            _id_problem(self.human_decision_ref, "review_decision", "human_decision_ref"),
        ]
        if isinstance(self.evidence_refs, tuple):
            found += [_label_problem(ref, "evidence_refs entry") for ref in self.evidence_refs]
            found.append(_sorted_unique_problem(self.evidence_refs, "evidence_refs"))
        return [problem for problem in found if problem is not None]

    def to_record(self) -> dict[str, Any]:
        return {
            serialize.SCHEMA_KEY: SCHEMA_DECISION, serialize.VERSION_KEY: MATERIAL_VERSION,
            "judgement": self.judgement,
            "evaluator_identity": self.evaluator_identity,
            "evaluator_version": self.evaluator_version,
            "public_safe_rationale": self.public_safe_rationale,
            "evidence_refs": list(self.evidence_refs),
            "human_decision_ref": self.human_decision_ref,
        }

    @property
    def digest(self) -> str:
        problems = self.problems()
        if problems:
            raise _invalid("RoadmapAchievementDecision is invalid: " + "; ".join(problems))
        return serialize.digest(self.to_record())

    @property
    def records_event(self) -> bool:
        """Only ``achieved`` writes; every other judgement is a read-only result (§14.26, §32.48)."""
        return self.judgement == JUDGEMENT_ACHIEVED


def structured_judgement(legacy: str) -> str:
    """The structured judgement of a legacy string judgement, or a refusal."""
    if legacy not in LEGACY_JUDGEMENTS:
        raise ValidationError(f"unknown judgement: {legacy}")
    return LEGACY_JUDGEMENTS[legacy]


# --------------------------------------------------------------------------- the Roadmap basis (§32.45)

@dataclass(frozen=True)
class RoadmapBasis:
    """The canonical Roadmap achievement basis, frozen before the write and rechecked under the lock.

    ``roadmap_lifecycle`` is carried for the "Roadmap active" precondition but
    is NOT part of the digest material: the ``roadmap_achieved`` event the
    decision records changes it, and binding it would make the read-back of
    the committed state disagree with the evidence by construction (RB5C-H1).
    """

    roadmap_id: str
    roadmap_lifecycle: str
    active_phase_ids: tuple[str, ...]
    all_active_phases_complete: bool
    reviewed_phase_ids: tuple[str, ...]
    #: Reviewed Phases whose current evidence is not ready, with the match status.
    unready_phases: tuple[tuple[str, str], ...]
    structural_validation_passed: bool
    material: Mapping[str, Any]
    digest: str

    @property
    def phase_evidence_refs(self) -> tuple[tuple[str, str, str], ...]:
        """``(phase_id, achievement_evidence_id, evidence body digest)`` of every ready reviewed Phase."""
        return tuple(
            (entry["phase_id"], entry["achievement_evidence_id"], entry["evidence_digest"])
            for entry in self.material["phases"] if entry["achievement_evidence_id"] is not None
        )

    @property
    def legacy_phase_facts(self) -> tuple[tuple[str, str, bool], ...]:
        """``(phase_id, basis_digest, generated_complete)`` of every legacy Phase, explicitly marked legacy."""
        return tuple(
            (entry["phase_id"], entry["basis_digest"], entry["generated_complete"])
            for entry in self.material["phases"] if entry["completion_mode"] == _mode_legacy()
        )

    @property
    def review_refs(self) -> tuple[str, ...]:
        return tuple(self.material["review_refs"])

    @property
    def human_decision_ref(self) -> str | None:
        return self.material["human_decision_ref"]

    @property
    def requires_structured_decision(self) -> bool:
        """§32.43: a Roadmap containing P5-capable (reviewed) Phases records ``achieved`` only by the structured form."""
        return bool(self.reviewed_phase_ids)


def roadmap_basis(
    view: "ProjectView",
    roadmap_id: str,
    evidence: Iterable[PhaseCompletionEvidence],
    *,
    review_refs: Iterable[str] = (),
    human_decision_ref: str | None = None,
) -> RoadmapBasis:
    """§32.45 over the current view and the validated phase_completion evidence.

    Every active Phase is bound by its current Phase basis digest; a reviewed
    Phase additionally by its one current evidence ID and that record's body
    digest (computed from the matched record itself, never supplied), a legacy
    Phase explicitly as legacy (no Review history is invented for it). The
    Project-wide structural validation is computed once.

    ``review_refs`` and ``human_decision_ref`` are bound as the owner gives
    them. Whether they name valid, current canonical Review / RB4 Human
    Decision Evidence records is the owner's check (§32.44 "all referenced P5
    evidence valid/current"), whose result :func:`achieved_precondition_problems`
    requires as ``reference_problems`` (RB5FB-1); nothing here reads a record.
    """
    from . import phase_integration as pi

    roadmap = view.roadmaps.get(roadmap_id)
    if roadmap is None:
        raise _invalid(f"Roadmap {roadmap_id} does not exist")
    evidence = list(evidence)
    validation = structural_validation(view)
    entries: list[dict[str, Any]] = []
    reviewed: list[str] = []
    unready: list[tuple[str, str]] = []
    complete = True
    for phase in sorted(view.active_phases(roadmap_id), key=lambda p: p.id):
        basis = phase_basis(view, phase.id, validation=validation)
        complete = complete and basis.generated_complete
        entry: dict[str, Any] = {
            "phase_id": phase.id, "completion_mode": basis.completion_mode,
            "generated_complete": basis.generated_complete, "basis_digest": basis.digest,
            "evidence_status": None, "achievement_evidence_id": None, "evidence_digest": None,
        }
        if basis.completion_mode == pi.MODE_REVIEWED:
            reviewed.append(phase.id)
            match = match_current_phase_evidence(basis, evidence)
            entry["evidence_status"] = match.status
            if match.status == EVIDENCE_READY and match.current is not None:
                entry["achievement_evidence_id"] = match.current.achievement_evidence_id
                entry["evidence_digest"] = match.current.digest
            else:
                unready.append((phase.id, match.status))
        entries.append(entry)
    active = tuple(entry["phase_id"] for entry in entries)
    refs = sorted(set(review_refs))
    material = serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_ROADMAP_BASIS, serialize.VERSION_KEY: MATERIAL_VERSION,
        "roadmap_id": roadmap_id,
        "roadmap_desired_state_digest": _desired_state_digest(roadmap.section(ROADMAP_DESIRED_HEADING)),
        "active_phase_ids": list(active),
        "all_active_phases_complete": bool(active) and complete,
        "phases": entries,
        "structural_validation_digest": validation[1],
        "review_refs": refs,
        "human_decision_ref": human_decision_ref,
    })
    return RoadmapBasis(
        roadmap_id, view.roadmap_lifecycle(roadmap_id), active, bool(active) and complete, tuple(reviewed),
        tuple(unready), validation[0], material, serialize.digest(material),
    )


def decision_input_problems(basis: RoadmapBasis, decision: object) -> list[str]:
    """§32.43: which decision form ``basis`` accepts; empty when ``decision`` is acceptable (RB5C-L7).

    A legacy string judgement stays accepted for a legacy-only Roadmap; a
    Roadmap containing reviewed (P5-capable) Phases records ``achieved`` only
    through a valid structured :class:`RoadmapAchievementDecision`.
    """
    if isinstance(decision, str):
        if decision not in LEGACY_JUDGEMENTS:
            return [f"unknown judgement: {decision}"]
        if LEGACY_JUDGEMENTS[decision] == JUDGEMENT_ACHIEVED and basis.requires_structured_decision:
            return ["a Roadmap containing reviewed Phases records achieved only through the structured "
                    "RoadmapAchievementDecision, not a legacy string judgement"]
        return []
    if type(decision) is RoadmapAchievementDecision:
        return [f"decision: {problem}" for problem in decision.problems()]
    return [f"a Roadmap achievement decision is a legacy string or a RoadmapAchievementDecision, not "
            f"{type(decision).__name__}"]


# --------------------------------------------------------------------------- H-2 mechanical preconditions (§32.44)

def achieved_precondition_problems(
    frozen: RoadmapBasis,
    current: RoadmapBasis,
    decision: RoadmapAchievementDecision,
    *,
    blocking_obligations: Iterable[str],
    unresolved_human_decisions: Iterable[str],
    reference_problems: Sequence[str],
) -> list[str]:
    """Why an ``achieved`` write may not happen now; empty when every H-2 mechanical precondition holds.

    ``frozen`` is the basis the semantic evaluation was made on, ``current`` the
    same basis recomputed under the Project execution lock. Both blocking and
    HUMAN inputs are required (no default reads as "none", RB5C-L2). The
    semantic judgement of the desired state stays the caller's; this never
    invents meaning and never adds a Human step merely because the evaluator is
    AI. Checked before the write only: after the stage is applied the owner
    proves :func:`readback_problems` instead.

    ``reference_problems`` is the owner's validation result over
    ``current.review_refs`` and ``current.human_decision_ref`` against the
    canonical Review / RB4 Human Decision Evidence records (§32.44 "all
    referenced P5 evidence valid/current", §32.45; RB5FB-1). It is required, a
    sequence of problems, and must be empty - the same "no default reads as
    none" rule as ``blocking_obligations`` and as
    :func:`phase_completion_evidence_for`'s ``source_ref_problems``. This
    function itself checks only that the decision and the basis agree on
    those references, never that the records exist or are current.
    """
    from .state import ACTIVE

    if type(decision) is not RoadmapAchievementDecision:
        return [f"the achieved path takes a structured RoadmapAchievementDecision, not {type(decision).__name__}"]
    problems = [f"decision: {problem}" for problem in decision.problems()]
    if decision.judgement != JUDGEMENT_ACHIEVED:
        problems.append(f"judgement {decision.judgement!r} records no achievement event")
    if current.roadmap_lifecycle != ACTIVE:
        problems.append(f"Roadmap {current.roadmap_id} is {current.roadmap_lifecycle}, not active")
    if not current.all_active_phases_complete:
        problems.append("not every active Phase is generated-complete")
    for phase_id, status in current.unready_phases:
        problems.append(f"reviewed Phase {phase_id} is not progression-ready (evidence {status})")
    if not current.structural_validation_passed:
        problems.append("structural validation does not pass")
    if frozen.roadmap_id != current.roadmap_id:
        problems.append("the frozen basis is another Roadmap's")
    elif frozen.digest != current.digest:
        problems.append("the canonical basis changed after the decision was frozen: re-evaluate")
    citable = _hashable_set(evidence_id for _, evidence_id, _ in current.phase_evidence_refs) \
        | _hashable_set(current.review_refs)
    if isinstance(decision.evidence_refs, tuple):  # anything else is already a decision problem (decision.problems)
        for _, evidence_id, _ in current.phase_evidence_refs:
            if evidence_id not in decision.evidence_refs:
                problems.append(f"the decision does not cite current Phase evidence {evidence_id}")
        for ref in decision.evidence_refs:
            if not _member(ref, citable):
                problems.append(f"the decision cites {ref}, which the current basis does not hold as valid evidence")
    if decision.human_decision_ref != current.human_decision_ref:
        problems.append("the decision's Human Decision Evidence reference is not the basis's")
    if isinstance(reference_problems, (str, bytes)) or not isinstance(reference_problems, Sequence):
        problems.append("reference_problems is not established (the owner's validation of the basis's review_refs / "
                        "human_decision_ref against the canonical Review / Human Decision Evidence records is "
                        "required)")
    else:
        problems += [f"referenced Review / Human Decision Evidence does not validate: {item}"
                     for item in reference_problems]
    for name, items in (("blocking_obligations", blocking_obligations),
                        ("unresolved_human_decisions", unresolved_human_decisions)):
        if items is None or isinstance(items, (str, bytes)):
            problems.append(f"{name} is not established (a collection of open items is required)")
    for obligation in sorted(set(blocking_obligations or ())):
        problems.append(f"blocking Review / achievement obligation remains: {obligation}")
    for human in sorted(set(unresolved_human_decisions or ())):
        problems.append(f"unresolved HUMAN decision remains: {human}")
    return problems


# --------------------------------------------------------------------------- roadmap_achievement evidence (§32.47)

ROADMAP_EVIDENCE_FIELDS = (
    "kind", "achievement_evidence_id", "roadmap_id", "roadmap_desired_state_digest", "roadmap_basis_digest",
    "active_phase_ids", "phase_evidence_refs", "legacy_phase_facts", "review_refs", "structural_validation_digest",
    "judgement", "decision_digest", "decision_evidence_refs", "evaluator_identity", "evaluator_version",
    "human_decision_ref", "rationale", "reserved_event_id", "causing_operation",
)
_PHASE_REF_FIELDS = ("phase_id", "achievement_evidence_id", "evidence_digest")
_LEGACY_FACT_FIELDS = ("phase_id", "basis_digest", "completion_mode", "generated_complete")
_ROADMAP_CAUSE_FIELDS = ("mutation_id", "operation")


@dataclass(frozen=True)
class RoadmapAchievementEvidence:
    """The strict body of one immutable ``roadmap_achievement`` record (§14.24, §32.47).

    Evidence and event are one logical decision: the record references the
    reserved ``roadmap_achieved`` event ID, and the event schema is unchanged.
    The structured decision is persisted field by field (its evidence refs
    included), so ``decision_digest`` is recomputed, never trusted (RB5C-L3).
    """

    achievement_evidence_id: str
    roadmap_id: str
    roadmap_desired_state_digest: str
    roadmap_basis_digest: str
    active_phase_ids: tuple[str, ...]
    phase_evidence_refs: tuple[tuple[str, str, str], ...]
    legacy_phase_facts: tuple[tuple[str, str], ...]
    review_refs: tuple[str, ...]
    structural_validation_digest: str
    decision_digest: str
    decision_evidence_refs: tuple[str, ...]
    evaluator_identity: str
    evaluator_version: str
    human_decision_ref: str | None
    rationale: str
    reserved_event_id: str
    causing_mutation_id: str
    causing_operation: str = ROADMAP_ACHIEVEMENT_OPERATION
    judgement: str = JUDGEMENT_ACHIEVED
    kind: str = KIND_ROADMAP_ACHIEVEMENT

    def to_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "achievement_evidence_id": self.achievement_evidence_id,
            "roadmap_id": self.roadmap_id,
            "roadmap_desired_state_digest": self.roadmap_desired_state_digest,
            "roadmap_basis_digest": self.roadmap_basis_digest,
            "active_phase_ids": list(self.active_phase_ids),
            "phase_evidence_refs": [
                {"phase_id": phase_id, "achievement_evidence_id": evidence_id, "evidence_digest": digest}
                for phase_id, evidence_id, digest in self.phase_evidence_refs
            ],
            "legacy_phase_facts": [
                {"phase_id": phase_id, "basis_digest": digest, "completion_mode": _mode_legacy(),
                 "generated_complete": True}
                for phase_id, digest in self.legacy_phase_facts
            ],
            "review_refs": list(self.review_refs),
            "structural_validation_digest": self.structural_validation_digest,
            "judgement": self.judgement,
            "decision_digest": self.decision_digest,
            "decision_evidence_refs": list(self.decision_evidence_refs),
            "evaluator_identity": self.evaluator_identity,
            "evaluator_version": self.evaluator_version,
            "human_decision_ref": self.human_decision_ref,
            "rationale": self.rationale,
            "reserved_event_id": self.reserved_event_id,
            "causing_operation": {"mutation_id": self.causing_mutation_id, "operation": self.causing_operation},
        }

    def decision(self) -> RoadmapAchievementDecision:
        """The structured decision this record persists."""
        return RoadmapAchievementDecision(self.judgement, self.evaluator_identity, self.evaluator_version,
                                          self.rationale, tuple(self.decision_evidence_refs), self.human_decision_ref)

    def problems(self) -> list[str]:
        found: list[str | None] = [
            None if self.kind == KIND_ROADMAP_ACHIEVEMENT else f"kind {self.kind!r} is not {KIND_ROADMAP_ACHIEVEMENT}",
            None if self.judgement == JUDGEMENT_ACHIEVED else
            f"judgement {self.judgement!r}: only an achieved decision has achievement evidence",
            _label_problem(self.achievement_evidence_id, "achievement_evidence_id"),
            _id_problem(self.roadmap_id, "roadmap", "roadmap_id"),
            _digest_problem(self.roadmap_desired_state_digest, "roadmap_desired_state_digest"),
            _digest_problem(self.roadmap_basis_digest, "roadmap_basis_digest"),
            None if self.structural_validation_digest == PASS_VALIDATION_DIGEST else
            "structural_validation_digest is not the digest of a passing structural validation",
            _digest_problem(self.decision_digest, "decision_digest"),
            _label_problem(self.evaluator_identity, "evaluator_identity"),
            _label_problem(self.evaluator_version, "evaluator_version"),
            None if self.human_decision_ref is None else
            _id_problem(self.human_decision_ref, "review_decision", "human_decision_ref"),
            _text_problem(self.rationale, "rationale"),
            _id_problem(self.reserved_event_id, "event", "reserved_event_id"),
            _id_problem(self.causing_mutation_id, "mutation", "causing mutation_id"),
            None if self.causing_operation == ROADMAP_ACHIEVEMENT_OPERATION else
            f"causing operation {self.causing_operation!r} is not {ROADMAP_ACHIEVEMENT_OPERATION}",
        ]
        found += [_id_problem(phase_id, "phase", "active_phase_ids entry") for phase_id in self.active_phase_ids]
        found.append(_sorted_unique_problem(self.active_phase_ids, "active_phase_ids"))
        if not self.active_phase_ids:
            found.append("an achieved Roadmap has at least one active Phase")
        reviewed = [phase_id for phase_id, _, _ in self.phase_evidence_refs]
        legacy = [phase_id for phase_id, _ in self.legacy_phase_facts]
        for phase_id, evidence_id, digest in self.phase_evidence_refs:
            found += [_label_problem(evidence_id, f"evidence ref of {phase_id}"),
                      _digest_problem(digest, f"evidence digest of {phase_id}")]
        for phase_id, digest in self.legacy_phase_facts:
            found.append(_digest_problem(digest, f"legacy basis digest of {phase_id}"))
        found.append(_sorted_unique_problem(reviewed, "phase_evidence_refs"))
        found.append(_sorted_unique_problem(legacy, "legacy_phase_facts"))
        try:
            bound_once = sorted(reviewed + legacy) == list(self.active_phase_ids)
        except TypeError:  # unorderable Phase IDs: each is reported by its own check (RB5FA-1)
            bound_once = False
        if not bound_once:
            found.append("every active Phase is bound exactly once, by reviewed evidence or as an explicit legacy fact")
        found += [_label_problem(ref, "review_refs entry") for ref in self.review_refs]
        found.append(_sorted_unique_problem(self.review_refs, "review_refs"))
        decision = self.decision()
        decision_problems = decision.problems()
        found += [f"persisted decision: {problem}" for problem in decision_problems]
        if not decision_problems and decision.digest != self.decision_digest:
            found.append("decision_digest is not the digest of the persisted structured decision")
        citable = _hashable_set(evidence_id for _, evidence_id, _ in self.phase_evidence_refs) \
            | _hashable_set(self.review_refs)
        for _, evidence_id, _ in self.phase_evidence_refs:
            if evidence_id not in self.decision_evidence_refs:
                found.append(f"the persisted decision does not cite Phase evidence {evidence_id}")
        for ref in self.decision_evidence_refs:
            if not _member(ref, citable):
                found.append(f"the persisted decision cites {ref}, which the record does not bind")
        return [problem for problem in found if problem is not None]

    @classmethod
    def from_record(cls, record: object) -> "RoadmapAchievementEvidence":
        described = "roadmap_achievement evidence"
        body = _exact_fields(record, ROADMAP_EVIDENCE_FIELDS, described)
        try:
            cause = _exact_fields(body["causing_operation"], _ROADMAP_CAUSE_FIELDS, f"{described} causing_operation")
            phase_refs = [_exact_fields(item, _PHASE_REF_FIELDS, f"{described} phase evidence ref")
                          for item in _require_list(body, "phase_evidence_refs", described)]
            legacy = [_exact_fields(item, _LEGACY_FACT_FIELDS, f"{described} legacy phase fact")
                      for item in _require_list(body, "legacy_phase_facts", described)]
            for item in legacy:
                if item["completion_mode"] != _mode_legacy() or item["generated_complete"] is not True:
                    raise _invalid(f"{described} legacy phase fact {item['phase_id']!r} is not an explicit "
                                   "legacy completion fact")
            evidence = cls(
                achievement_evidence_id=body["achievement_evidence_id"],
                roadmap_id=body["roadmap_id"],
                roadmap_desired_state_digest=body["roadmap_desired_state_digest"],
                roadmap_basis_digest=body["roadmap_basis_digest"],
                active_phase_ids=tuple(_require_list(body, "active_phase_ids", described)),
                phase_evidence_refs=tuple((i["phase_id"], i["achievement_evidence_id"], i["evidence_digest"])
                                          for i in phase_refs),
                legacy_phase_facts=tuple((i["phase_id"], i["basis_digest"]) for i in legacy),
                review_refs=tuple(_require_list(body, "review_refs", described)),
                structural_validation_digest=body["structural_validation_digest"],
                decision_digest=body["decision_digest"],
                decision_evidence_refs=tuple(_require_list(body, "decision_evidence_refs", described)),
                evaluator_identity=body["evaluator_identity"],
                evaluator_version=body["evaluator_version"],
                human_decision_ref=body["human_decision_ref"],
                rationale=body["rationale"],
                reserved_event_id=body["reserved_event_id"],
                causing_mutation_id=cause["mutation_id"],
                causing_operation=cause["operation"],
                judgement=body["judgement"],
                kind=body["kind"],
            )
        except (TypeError, KeyError) as exc:
            raise _invalid(f"{described} does not read: {exc}") from exc
        problems = evidence.problems()
        if problems:
            raise _invalid(f"{described} is invalid: " + "; ".join(problems))
        return evidence

    @property
    def digest(self) -> str:
        return serialize.digest(self.to_record())


def build_roadmap_achievement_evidence(
    achievement_evidence_id: str,
    basis: RoadmapBasis,
    decision: RoadmapAchievementDecision,
    *,
    reserved_event_id: str,
    causing_mutation_id: str,
) -> RoadmapAchievementEvidence:
    """§32.46 step 7 (pure half): the roadmap_achievement body referencing the reserved event ID.

    Refuses a basis that is not ready for achievement on its own (RB5C-L1): an
    inactive Roadmap, an incomplete active Phase, an unready reviewed Phase or a
    failing structure - so even a builder-only path cannot certify a legacy
    Phase that is not complete.
    """
    from .state import ACTIVE

    if type(decision) is not RoadmapAchievementDecision or not decision.records_event:
        raise _invalid("only a structured achieved RoadmapAchievementDecision creates achievement evidence")
    refused = [
        None if basis.roadmap_lifecycle == ACTIVE else f"Roadmap {basis.roadmap_id} is {basis.roadmap_lifecycle}",
        None if basis.all_active_phases_complete else "not every active Phase is generated-complete",
        None if basis.structural_validation_passed else "structural validation does not pass",
        None if not basis.unready_phases else
        "reviewed Phase(s) not progression-ready: " + ", ".join(f"{p} ({s})" for p, s in basis.unready_phases),
    ]
    refused = [reason for reason in refused if reason is not None]
    if refused:
        raise _invalid("the Roadmap basis is not ready for achievement: " + "; ".join(refused))
    evidence = RoadmapAchievementEvidence(
        achievement_evidence_id=achievement_evidence_id,
        roadmap_id=basis.roadmap_id,
        roadmap_desired_state_digest=str(basis.material["roadmap_desired_state_digest"]),
        roadmap_basis_digest=basis.digest,
        active_phase_ids=basis.active_phase_ids,
        phase_evidence_refs=basis.phase_evidence_refs,
        legacy_phase_facts=tuple((phase_id, digest) for phase_id, digest, _ in basis.legacy_phase_facts),
        review_refs=basis.review_refs,
        structural_validation_digest=str(basis.material["structural_validation_digest"]),
        decision_digest=decision.digest,
        decision_evidence_refs=tuple(decision.evidence_refs),
        evaluator_identity=decision.evaluator_identity,
        evaluator_version=decision.evaluator_version,
        human_decision_ref=decision.human_decision_ref,
        rationale=decision.public_safe_rationale,
        reserved_event_id=reserved_event_id,
        causing_mutation_id=causing_mutation_id,
    )
    problems = evidence.problems()
    if problems:
        raise _invalid("roadmap_achievement evidence would be invalid: " + "; ".join(problems))
    return evidence


def event_evidence_problems(evidence: RoadmapAchievementEvidence, event: "Event") -> list[str]:
    """§32.46 step 11: the recorded ``roadmap_achieved`` event and the record are one decision; empty when they agree.

    The event keeps its existing schema: it carries no metadata, and the
    evidence references it - never the other way round.
    """
    problems = []
    if event.id != evidence.reserved_event_id:
        problems.append(f"event {event.id} is not the reserved event {evidence.reserved_event_id}")
    if event.type != ROADMAP_ACHIEVED_EVENT:
        problems.append(f"event {event.id} is {event.type}, not {ROADMAP_ACHIEVED_EVENT}")
    if event.entity != evidence.roadmap_id:
        problems.append(f"event {event.id} is about {event.entity}, not Roadmap {evidence.roadmap_id}")
    if dict(event.metadata):
        problems.append(f"event {event.id} carries metadata: the roadmap_achieved event schema is unchanged")
    return problems


def readback_problems(evidence: RoadmapAchievementEvidence, committed: RoadmapBasis, event: "Event") -> list[str]:
    """§32.46 step 11 in full: event / evidence / basis agreement against the committed state.

    ``committed`` is :func:`roadmap_basis` recomputed from the committed state,
    which holds the ``roadmap_achieved`` event; the basis digest does not bind
    the lifecycle that event changes, so a legitimate achievement reads back
    equal (RB5C-H1).
    """
    problems = list(evidence.problems()) + event_evidence_problems(evidence, event)
    if evidence.roadmap_basis_digest != committed.digest:
        problems.append(f"roadmap basis {evidence.roadmap_basis_digest} != committed basis {committed.digest}")
    return problems


__all__ = [
    "KIND_PHASE_COMPLETION", "KIND_ROADMAP_ACHIEVEMENT", "EVIDENCE_KINDS", "EVIDENCE_STATUSES", "EVIDENCE_READY",
    "EVIDENCE_MISSING", "EVIDENCE_STALE", "EVIDENCE_CONFLICT", "EVIDENCE_INVALID", "EVIDENCE_STRUCTURE_INVALID",
    "JUDGEMENTS", "LEGACY_JUDGEMENTS", "PASS_VALIDATION_DIGEST", "PhaseBasis", "phase_basis", "structural_validation",
    "structural_validation_material", "IntegrationRunRef", "PhaseCompletionEvidence", "phase_evidence_basis_problems",
    "build_phase_completion_evidence", "EvidenceMatch", "match_current_phase_evidence", "PhaseEvidenceObligation",
    "phase_evidence_obligation", "phase_completion_evidence_for", "ProgressionReadiness", "phase_progression_decision",
    "ProgressionNarrowing", "progression_ready_candidates", "postcommit_basis_problems", "RoadmapAchievementDecision",
    "structured_judgement", "RoadmapBasis", "roadmap_basis", "decision_input_problems", "achieved_precondition_problems",
    "RoadmapAchievementEvidence", "build_roadmap_achievement_evidence", "event_evidence_problems", "readback_problems",
]

