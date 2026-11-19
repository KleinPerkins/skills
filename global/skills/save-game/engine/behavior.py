"""Agent-behavior rules: marginal scope, decision reversal/scope change,
blocker classification, hygiene evaluation, next-action determination, and
natural stopping (plan: normative glossary; "Reversals and scope/plan
change"; "Autonomy, blockers, hygiene, and stopping"; M2/M4 gates).

This is the Phase 3a behavior-rule layer that `engine.flush`, `engine.index`,
and `engine.reconcile` explicitly defer to in their own docstrings ("Phase
3a's behavior-rule domain"). It is a self-contained, stdlib-only,
side-effect-free collection of functions and dataclasses: it never touches
disk, a lock, or a live Git root, and it never imports flush/index/reconcile
back. Wiring these decisions into the four contracts and the CLI is the
integration phase's job, not this module's.

It reuses Phase 1's `schemas`/`schemas_validate` so every schema-shaped
fragment this module produces (a `hygiene` object, a `marginal_scope_budget`,
one `decisions[]` entry, a `next_actions` list, one `blockers[]` entry) stays
conformant with `save-game-current/v1` -- see `validate_current_fragment`
below -- and reuses `ids.now_iso`/`ids.new_id` for the same ID/timestamp
conventions the rest of the engine already uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import ids, schemas
from . import schemas_validate as sv

_CURRENT_SCHEMA_NAME = "current.v1"


def _resolve_sub_schema(path: tuple) -> dict:
    node = schemas.load_schema(_CURRENT_SCHEMA_NAME)
    for step in path:
        node = node[step]
    return node


def validate_current_fragment(instance, *path: str) -> None:
    """Validates `instance` against the sub-schema found by walking `path`
    (literal JSON-Schema keys, e.g. `("properties", "hygiene")` or
    `("properties", "decisions", "items")`) inside `save-game-current/v1`.
    Raises `schemas_validate.SchemaValidationError` on any violation. This
    reuses Phase 1's schema files and validator instead of re-deriving a
    parallel fragment schema for pieces smaller than a whole document."""
    sv.validate(instance, _resolve_sub_schema(path))


def validate_hygiene_dict(doc: dict) -> None:
    validate_current_fragment(doc, "properties", "hygiene")


def validate_marginal_scope_budget_dict(doc: dict) -> None:
    validate_current_fragment(doc, "properties", "marginal_scope_budget")


def validate_decision_dict(doc: dict) -> None:
    validate_current_fragment(doc, "properties", "decisions", "items")


def validate_next_actions_list(doc: list) -> None:
    validate_current_fragment(doc, "properties", "next_actions")


def validate_blocker_dict(doc: dict) -> None:
    validate_current_fragment(doc, "properties", "blockers", "items")


# ---------------------------------------------------------------------------
# 1. Marginal-scope exception (plan: normative glossary "Marginal-scope
#    exception"; v2 hardening: estimate_source tagging + consumed-minutes
#    budget tracking so repeated small items cannot stack past the limit).
# ---------------------------------------------------------------------------

MARGINAL_MINUTES_CAP = 15
MARGINAL_PERCENT_CAP = 0.10

ESTIMATE_SOURCES = frozenset({"operator_set", "agent_estimated", "unknown"})
_KNOWN_ESTIMATE_SOURCES = frozenset({"operator_set", "agent_estimated"})

# The eleven scope dimensions the plan names verbatim ("no public API, data
# contract, security, governance, dependency, user-visible behavior,
# ownership, budget, deadline, communication, or acceptance criterion").
SCOPE_CHANGE_DIMENSIONS = frozenset(
    {
        "public_api", "data_contract", "security", "governance", "dependency",
        "user_visible_behavior", "ownership", "budget", "deadline",
        "communication", "acceptance_criterion",
    }
)


@dataclass(frozen=True)
class MarginalScopeBudget:
    """Mirrors `save-game-current/v1`'s `marginal_scope_budget` field exactly:
    required `consumed_minutes` + `estimate_source`, optional
    `remaining_minutes_estimate` -- see `validate_marginal_scope_budget_dict`.
    `estimate_source` here tags the WORKSTREAM's remaining-effort estimate
    (the schema field it sits beside), not any one candidate item's own
    estimate -- see `MarginalScopeCandidate.estimate_source` for that."""

    consumed_minutes: int = 0
    estimate_source: str = "unknown"
    remaining_minutes_estimate: Optional[int] = None

    def to_schema_dict(self) -> dict:
        doc: dict = {"consumed_minutes": self.consumed_minutes, "estimate_source": self.estimate_source}
        if self.remaining_minutes_estimate is not None:
            doc["remaining_minutes_estimate"] = self.remaining_minutes_estimate
        return doc


@dataclass(frozen=True)
class MarginalScopeCandidate:
    """One piece of discovered work being evaluated for silent absorption
    (plan: "discovered work may be absorbed only if every condition is
    true..."). `estimate_source` tags THIS item's own minute estimate; the
    plan ties `operator_set`/`agent_estimated` tagging to the workstream's
    remaining-effort estimate specifically, but the item's own estimate needs
    the same "is it actually known" gate -- "unknown means fail" applies to
    both, so this module requires both to be known rather than picking one."""

    summary: str
    estimated_minutes: Optional[int]
    estimate_source: str  # operator_set | agent_estimated | unknown
    local_and_reversible_in_one_patch: bool
    uses_already_authorized_surface: bool
    verification_command: Optional[str] = None  # name of an EXISTING command that proves it; falsy = no proof
    touches: frozenset = field(default_factory=frozenset)  # subset of SCOPE_CHANGE_DIMENSIONS this item actually affects


@dataclass(frozen=True)
class MarginalScopeDecision:
    decision: str  # "accept" | "defer_and_surface"
    reasons: list
    updated_budget: MarginalScopeBudget

    @property
    def accepted(self) -> bool:
        return self.decision == "accept"

    def plain_language(self) -> str:
        if self.accepted:
            return f"Absorbed as in-scope without asking: {self.reasons[0]}."
        return "Not silently absorbed -- surfacing for your decision: " + "; ".join(self.reasons) + "."


def evaluate_marginal_scope(candidate: MarginalScopeCandidate, budget: MarginalScopeBudget) -> MarginalScopeDecision:
    """Evaluates ALL of the plan's marginality conditions and returns
    accept/defer-and-surface with reasons. Unknown means fail: any condition
    that cannot be confirmed true is treated as failing, never guessed as a
    pass. `budget` is the workstream's CURRENT marginal-scope budget before
    this candidate; on accept, `updated_budget.consumed_minutes` already
    includes this candidate, so a caller that persists it and passes it into
    the next call gets correct cumulative stacking -- several small items
    checked one after another, not each evaluated as if it were the first."""
    reasons: list = []

    touched = sorted(candidate.touches & SCOPE_CHANGE_DIMENSIONS)
    if touched:
        reasons.append(f"changes {', '.join(t.replace('_', ' ') for t in touched)}, which always needs your authority")

    if not candidate.local_and_reversible_in_one_patch:
        reasons.append("is not local and reversible in one patch")

    if not candidate.uses_already_authorized_surface:
        reasons.append("touches a root or file surface that was not already authorized")

    if not candidate.verification_command:
        reasons.append("has no existing verification command to prove it")

    item_minutes_known = candidate.estimated_minutes is not None and candidate.estimate_source in _KNOWN_ESTIMATE_SOURCES
    if not item_minutes_known:
        reasons.append("this item's own time estimate is not known")

    remaining_known = budget.remaining_minutes_estimate is not None and budget.estimate_source in _KNOWN_ESTIMATE_SOURCES
    if not remaining_known:
        reasons.append("the remaining authorized effort estimate is not known")

    if item_minutes_known and remaining_known:
        projected = budget.consumed_minutes + candidate.estimated_minutes
        if projected > MARGINAL_MINUTES_CAP:
            reasons.append(f"would push cumulative small absorbed work to {projected} minutes, above the {MARGINAL_MINUTES_CAP}-minute cap")
        cap_pct_minutes = MARGINAL_PERCENT_CAP * budget.remaining_minutes_estimate
        if projected > cap_pct_minutes:
            reasons.append(
                f"would push cumulative small absorbed work to {projected} minutes, above "
                f"{int(MARGINAL_PERCENT_CAP * 100)}% of the ~{budget.remaining_minutes_estimate}-minute "
                f"remaining estimate (~{cap_pct_minutes:.1f} minutes)"
            )

    if reasons:
        return MarginalScopeDecision("defer_and_surface", reasons, budget)

    projected = budget.consumed_minutes + candidate.estimated_minutes
    updated = MarginalScopeBudget(
        consumed_minutes=projected,
        estimate_source=budget.estimate_source,
        remaining_minutes_estimate=budget.remaining_minutes_estimate,
    )
    validate_marginal_scope_budget_dict(updated.to_schema_dict())
    return MarginalScopeDecision(
        "accept",
        [f"'{candidate.summary}' is small, easy to undo, already within what's authorized, and backed by an existing check ({projected} minutes so far)"],
        updated,
    )


# ---------------------------------------------------------------------------
# 2. Decision reversal and plan/scope-change semantics (plan: "Reversals and
#    scope/plan change").
# ---------------------------------------------------------------------------

DECISION_STATUSES = frozenset({"proposed", "accepted", "superseded", "rejected"})
_INACTIVE_DECISION_STATUSES = frozenset({"superseded", "rejected"})


@dataclass(frozen=True)
class AuthorityPointer:
    """`{kind, locator, item_or_section, revision, digest, observed_at}` per
    the plan's normative glossary. An empty `locator` means no durable
    source/revision can be named for the statement -- the plan calls this
    case `operator_attested_unverifiable`. The authority-pointer schema has
    no dedicated boolean field for that marker (it is frozen from Phase 1),
    so it is encoded in the one free-text field available: `to_schema_dict`
    writes the literal marker into `locator` with `kind: other`. This is a
    deliberate, noted resolution of a schema/plan gap, not a guess at a field
    that doesn't exist."""

    kind: str = "other"
    locator: str = ""
    observed_at: str = ""
    item_or_section: Optional[str] = None
    revision: Optional[str] = None
    digest: Optional[str] = None

    @property
    def is_unverifiable(self) -> bool:
        return not (self.locator and self.locator.strip())

    def to_schema_dict(self) -> dict:
        if self.is_unverifiable:
            locator, kind = "operator_attested_unverifiable", "other"
        else:
            locator, kind = self.locator.strip()[:500], self.kind
        doc = {"kind": kind, "locator": locator, "observed_at": self.observed_at or ids.now_iso()}
        if self.item_or_section:
            doc["item_or_section"] = self.item_or_section[:200]
        if self.revision:
            doc["revision"] = self.revision[:200]
        if self.digest:
            doc["digest"] = self.digest
        return doc


@dataclass(frozen=True)
class Decision:
    decision_id: str
    statement: str
    status: str
    authority: AuthorityPointer
    revision: str
    supersedes: Optional[str] = None

    def to_schema_dict(self) -> dict:
        doc = {
            "decision_id": self.decision_id,
            "statement": self.statement[:200],
            "status": self.status,
            "authority": self.authority.to_schema_dict(),
            "revision": self.revision[:200],
        }
        if self.supersedes:
            doc["supersedes"] = self.supersedes
        return doc


@dataclass(frozen=True)
class DecisionReversalRequest:
    target_decision_id: str
    new_statement: str
    new_revision: str
    new_authority: AuthorityPointer
    session_or_turn_id: Optional[str] = None


@dataclass(frozen=True)
class ReversalResult:
    accepted: bool
    reasons: list
    decisions: list  # the full updated active_decisions list (unchanged if not accepted)
    new_decision: Optional[Decision] = None

    def plain_language(self) -> str:
        if self.accepted:
            return f"Recorded the change: '{self.new_decision.statement}' now replaces the earlier decision."
        return "Could not record that change: " + "; ".join(self.reasons) + "."


def apply_decision_reversal(active_decisions: list, request: DecisionReversalRequest) -> ReversalResult:
    """`active_decisions` is a list of `Decision`. Rejects a reversal that
    does not reference a real, currently-active prior decision. On success,
    replaces the target with a new decision carrying a one-hop `supersedes`
    pointer -- active state keeps only the current version of a decision
    (plan: Decision glossary), so the superseded entry is dropped from the
    returned list rather than kept alongside it with `status="superseded"`;
    prior debate remains recoverable only through Git/history/recovery
    evidence, never duplicated here (plan: "Reversals and scope/plan
    change")."""
    target = next((d for d in active_decisions if d.decision_id == request.target_decision_id), None)
    if target is None:
        return ReversalResult(False, ["no prior decision with that ID exists to reverse"], active_decisions)
    if target.status in _INACTIVE_DECISION_STATUSES:
        return ReversalResult(
            False,
            [f"decision {request.target_decision_id!r} is already {target.status}, not the active statement to reverse"],
            active_decisions,
        )

    authority = request.new_authority
    if authority.is_unverifiable:
        marker = "operator_attested_unverifiable"
        if request.session_or_turn_id:
            marker += f" (session {request.session_or_turn_id})"
        authority = AuthorityPointer(kind="other", locator=marker, observed_at=authority.observed_at or ids.now_iso())

    new_decision = Decision(
        decision_id=ids.new_id("dec"),
        statement=request.new_statement,
        status="accepted",
        authority=authority,
        revision=request.new_revision,
        supersedes=target.decision_id,
    )
    validate_decision_dict(new_decision.to_schema_dict())
    updated = [d for d in active_decisions if d.decision_id != target.decision_id] + [new_decision]
    return ReversalResult(True, ["reversal recorded with a one-hop supersedes pointer"], updated, new_decision)


def classify_plan_revision(current_revision: str, successors: list, *, authority_unchanged: bool = True) -> str:
    """Plan: "Plan revision with a valid successor and unchanged authority is
    ADVANCED; two competing successors are CONFLICT." Reuses Reconcile's own
    MATCH/ADVANCED/CONFLICT/UNKNOWN vocabulary for this claim
    (`plan_revision`) rather than inventing a parallel one -- see
    `engine.reconcile`. A changed authority pointer is deliberately UNKNOWN,
    not CONFLICT: the plan's ADVANCED case requires unchanged authority, and
    Reconcile's own UNKNOWN handling ("gather one bounded evidence pass...")
    is the closer fit for "the plan now points somewhere new" than an
    immediate, definitive CONFLICT."""
    successors = [s for s in successors if s and s != current_revision]
    if not successors:
        return "MATCH"
    if not authority_unchanged:
        return "UNKNOWN"
    if len(set(successors)) > 1:
        return "CONFLICT"
    return "ADVANCED"


@dataclass(frozen=True)
class ScopeChangeRequest:
    kind: str  # "expansion" | "removal"
    summary: str
    marginal_candidate: Optional[MarginalScopeCandidate] = None  # only meaningful for "expansion"


@dataclass(frozen=True)
class ScopeChangeResult:
    accepted: bool
    reasons: list
    requires_operator_authority: bool
    updated_budget: Optional[MarginalScopeBudget] = None
    moves_to_deferred: bool = False

    def plain_language(self) -> str:
        if self.moves_to_deferred:
            return f"Moved out of active scope into deferred, not discarded: {self.reasons[0]}."
        if self.accepted:
            return f"Absorbed without asking: {self.reasons[0]}."
        return "This needs your go-ahead before it's in scope: " + "; ".join(self.reasons) + "."


def apply_scope_change(request: ScopeChangeRequest, budget: MarginalScopeBudget) -> ScopeChangeResult:
    """Plan: "Scope expansion, root addition, acceptance-criterion change,
    external side effect, or new commitment always requires operator
    authority unless every marginal-scope condition passes" and "Removing
    work from scope moves its pointer to deferred; it is not silently
    discarded or kept active." Delegates expansion's marginality check to
    `evaluate_marginal_scope` rather than re-implementing the same rules."""
    if request.kind == "removal":
        return ScopeChangeResult(
            True, ["set aside for later, not dropped"], requires_operator_authority=False, moves_to_deferred=True
        )

    if request.marginal_candidate is None:
        return ScopeChangeResult(False, ["scope expansion with no marginal-scope evaluation available"], requires_operator_authority=True)

    decision = evaluate_marginal_scope(request.marginal_candidate, budget)
    if decision.accepted:
        return ScopeChangeResult(True, decision.reasons, requires_operator_authority=False, updated_budget=decision.updated_budget)
    return ScopeChangeResult(False, decision.reasons, requires_operator_authority=True)


# ---------------------------------------------------------------------------
# 3. Blocker classification and transient-failure handling (plan: normative
#    glossary "Blocker"; "Autonomy, blockers, hygiene, and stopping").
# ---------------------------------------------------------------------------

BLOCKER_KINDS = ("operator_decision", "access_denial", "canonical_conflict", "unsafe_choice", "external_event")

_BLOCKER_KIND_PLAIN = {
    "operator_decision": "this needs you to make a call before the agent continues",
    "access_denial": "access or permission was denied, and someone else needs to grant it",
    "canonical_conflict": "two authoritative sources disagree and need a decision on which one wins",
    "unsafe_choice": "the only remaining step would be unsafe or hard to undo without your say-so",
    "external_event": "this is waiting on something outside the agent's control",
}

_SIGNAL_TO_KIND = (
    ("operator_decision_required", "operator_decision"),
    ("definitive_access_denial", "access_denial"),
    ("canonical_source_conflict", "canonical_conflict"),
    ("unsafe_or_irreversible_choice", "unsafe_choice"),
    ("external_event_required", "external_event"),
)


@dataclass(frozen=True)
class DifficultySignal:
    """A difficulty the agent hit, described plainly plus flags for the five
    named blocker kinds. Deliberately has NO flags for "failing test",
    "implementation difficulty", "discoverable unknown", or "recoverable
    tool error": the plan lists those as the explicit non-blocker default,
    so `classify_blocker` treats anything that matches none of the five named
    kinds as ordinary difficulty -- it never needs its own enumerated
    reason to do so."""

    description: str
    operator_decision_required: bool = False
    definitive_access_denial: bool = False
    canonical_source_conflict: bool = False
    unsafe_or_irreversible_choice: bool = False
    external_event_required: bool = False


@dataclass(frozen=True)
class BlockerClassification:
    classification: str  # "ordinary_difficulty" | "true_blocker"
    kind: Optional[str]
    description: str
    continue_autonomously: bool

    def plain_language(self) -> str:
        if self.classification == "ordinary_difficulty":
            return f"Not a blocker, continuing: {self.description}."
        return f"Stopping to surface a real blocker: {_BLOCKER_KIND_PLAIN.get(self.kind, self.description)}."

    def to_schema_dict(self) -> Optional[dict]:
        if self.classification != "true_blocker":
            return None
        doc = {"description": (self.description or self.kind or "blocked")[:150], "kind": self.kind}
        validate_blocker_dict(doc)
        return doc


def classify_blocker(signal: DifficultySignal) -> BlockerClassification:
    """Ordinary debugging, failing tests, discoverable unknowns, and
    recoverable tool errors are NOT blockers (plan glossary, verbatim) --
    only the five named kinds ever produce `true_blocker`. Everything else is
    ordinary executable difficulty and autonomous execution continues."""
    for attr, kind in _SIGNAL_TO_KIND:
        if getattr(signal, attr):
            return BlockerClassification("true_blocker", kind, signal.description, continue_autonomously=False)
    return BlockerClassification(
        "ordinary_difficulty",
        None,
        f"{signal.description} is ordinary executable work (e.g. a failing test, implementation difficulty, "
        "a discoverable unknown, or a recoverable tool error), not a blocker",
        continue_autonomously=True,
    )


def blocker_classification_from_persisted(blocker_doc: dict) -> BlockerClassification:
    """Reconstructs the `BlockerClassification` a persisted `current.v1`
    `blockers[]` entry (`{"description", "kind"}`) came from. Reconstruction
    is exact, not a guess: `to_schema_dict` only ever persists a
    `true_blocker` (it returns `None` for `ordinary_difficulty`), so every
    persisted entry is unambiguously `true_blocker` with
    `continue_autonomously=False` -- this is the read-side mirror of that
    write-side contract, used by callers (e.g. the CLI's `status` surface)
    that need to re-run `determine_stopping` against already-saved state
    instead of duplicating `_SIGNAL_TO_KIND`'s kind table themselves."""
    kind = blocker_doc.get("kind")
    if kind not in dict(_SIGNAL_TO_KIND).values():
        raise ValueError(f"not a recognized blocker kind: {kind!r}")
    return BlockerClassification("true_blocker", kind, blocker_doc.get("description", ""), continue_autonomously=False)


def transient_failure_next_step(retry_count_same_operation: int, attempted_materially_different_alternative: bool) -> str:
    """Plan: "A transient technical failure gets one same-operation retry
    when safe, then one materially different safe alternative. Repeating the
    unchanged attempt is not progress." Returns exactly one of three
    next-step tokens. Exhausting both never automatically reclassifies the
    difficulty as a blocker by itself -- that only happens if the attempt
    independently surfaces one of the five named blocker kinds (re-run
    `classify_blocker` with the new evidence); otherwise it is a candidate
    for "no authorized dependency-satisfied action remains" via
    `determine_stopping`, a distinct natural-stopping reason from a
    blocker."""
    if retry_count_same_operation < 1:
        return "retry_same_operation"
    if not attempted_materially_different_alternative:
        return "try_materially_different_alternative"
    return "escalate_or_reclassify"


# ---------------------------------------------------------------------------
# 4. Hygiene evaluation (plan: normative glossary "Hygiene"; "Autonomy,
#    blockers, hygiene, and stopping"; v2 hardening: "unknown spawned-process
#    state" is agent-self-reported from its own tool-call history, never
#    save-game-tracked).
# ---------------------------------------------------------------------------

HYGIENE_CONDITIONS = (
    "transactions_finalized", "temp_files_clear", "spawned_process_state_known",
    "repo_status_observed", "required_checks_run", "no_unclassified_delta",
)

_HYGIENE_CONDITION_PLAIN = {
    "transactions_finalized": "a save is still in progress",
    "temp_files_clear": "temporary files were left behind",
    "spawned_process_state_known": "it isn't confirmed whether background processes it started have stopped",
    "repo_status_observed": "repository status was not checked",
    "required_checks_run": "required checks have not run",
    "no_unclassified_delta": "there are changes that haven't been sorted out yet",
}


@dataclass(frozen=True)
class HygieneCondition:
    condition: str
    passed: bool
    evidence: str


@dataclass(frozen=True)
class HygieneReport:
    conditions: tuple  # tuple[HygieneCondition, ...], in HYGIENE_CONDITIONS order

    @property
    def all_clear(self) -> bool:
        return all(c.passed for c in self.conditions)

    def failing(self) -> list:
        return [c for c in self.conditions if not c.passed]

    def plain_language(self) -> str:
        if self.all_clear:
            return (
                "Hygiene is clear: no pending saves, no leftover files or processes, repository status was "
                "checked (not changed), and required checks ran."
            )
        gaps = "; ".join(
            f"{_HYGIENE_CONDITION_PLAIN.get(c.condition, c.condition)} ({c.evidence})"
            if c.evidence
            else _HYGIENE_CONDITION_PLAIN.get(c.condition, c.condition)
            for c in self.failing()
        )
        return f"Not calling this clean yet: {gaps}."

    def to_schema_dict(self) -> dict:
        by_name = {c.condition: c.passed for c in self.conditions}
        doc = {
            "transactions_finalized": by_name["transactions_finalized"],
            "temp_artifacts_clear": by_name["temp_files_clear"] and by_name["spawned_process_state_known"],
            "repo_status_observed": by_name["repo_status_observed"],
            "required_checks_run": by_name["required_checks_run"],
            # Inverted polarity vs. the other four flags, matching the existing
            # convention documented in engine.index.hygiene_summary: True here
            # means an unclassified delta EXISTS (the bad state).
            "unclassified_delta": not by_name["no_unclassified_delta"],
        }
        validate_hygiene_dict(doc)
        return doc


def hygiene_report_from_persisted(hygiene_doc: dict) -> HygieneReport:
    """Reconstructs a `HygieneReport` from a persisted `current.v1` `hygiene`
    object. This is a lossy PROJECTION, not a re-derivation: `to_schema_dict`
    permanently ANDs `temp_files_clear` with `spawned_process_state_known`
    into one persisted `temp_artifacts_clear` bit, so a caller reading
    persisted state back (e.g. the CLI's `status` surface) cannot recover
    which of the two sub-conditions failed if `temp_artifacts_clear` is
    false -- both are reported as mirroring the single persisted bit,
    documented here rather than silently guessed. `unclassified_delta`'s
    inverted polarity round-trips exactly (no information loss there)."""
    evidence = "(from persisted current-state; see docstring on collapsed temp/process bit)"
    conditions = (
        HygieneCondition("transactions_finalized", hygiene_doc["transactions_finalized"], ""),
        HygieneCondition("temp_files_clear", hygiene_doc["temp_artifacts_clear"], evidence),
        HygieneCondition("spawned_process_state_known", hygiene_doc["temp_artifacts_clear"], evidence),
        HygieneCondition("repo_status_observed", hygiene_doc["repo_status_observed"], ""),
        HygieneCondition("required_checks_run", hygiene_doc["required_checks_run"], ""),
        HygieneCondition("no_unclassified_delta", not hygiene_doc["unclassified_delta"], ""),
    )
    return HygieneReport(conditions)


def evaluate_hygiene(
    *,
    transactions_finalized: bool,
    temp_files_clear: bool,
    spawned_process_state_known: bool,
    spawned_process_evidence: str,
    repo_status_observed: bool,
    required_checks_run: bool,
    no_unclassified_delta: bool,
    transactions_evidence: str = "",
    temp_files_evidence: str = "",
    repo_status_evidence: str = "",
    required_checks_evidence: str = "",
    unclassified_delta_evidence: str = "",
) -> HygieneReport:
    """Every hygiene condition the plan defines, evaluated with per-condition
    evidence. `spawned_process_state_known` and `spawned_process_evidence`
    are the v2-hardened "unknown spawned-process state" condition: this
    module has no access to real tool-call history, so the caller must
    self-report it (e.g. "no background processes were started this
    session", or "PID 1234 confirmed exited") rather than this module
    inventing or tracking it."""
    conditions = (
        HygieneCondition("transactions_finalized", transactions_finalized, transactions_evidence),
        HygieneCondition("temp_files_clear", temp_files_clear, temp_files_evidence),
        HygieneCondition("spawned_process_state_known", spawned_process_state_known, spawned_process_evidence),
        HygieneCondition("repo_status_observed", repo_status_observed, repo_status_evidence),
        HygieneCondition("required_checks_run", required_checks_run, required_checks_evidence),
        HygieneCondition("no_unclassified_delta", no_unclassified_delta, unclassified_delta_evidence),
    )
    report = HygieneReport(conditions)
    report.to_schema_dict()  # validated as a side effect; raises on any shape drift
    return report


# ---------------------------------------------------------------------------
# 5. Next-action determination (plan: normative glossary "Next action").
# ---------------------------------------------------------------------------

MAX_NEXT_ACTIONS = 3


@dataclass(frozen=True)
class CandidateAction:
    description: str
    owner: str = ""
    preconditions: str = ""
    expected_evidence: str = ""
    completion_test: str = ""
    authorized: bool = True
    dependency_satisfied: bool = True
    is_hygiene: bool = False

    def to_schema_dict(self) -> dict:
        doc = {"description": self.description[:150]}
        if self.owner:
            doc["owner"] = self.owner[:50]
        if self.preconditions:
            doc["preconditions"] = self.preconditions[:150]
        if self.expected_evidence:
            doc["expected_evidence"] = self.expected_evidence[:150]
        if self.completion_test:
            doc["completion_test"] = self.completion_test[:150]
        return doc


def determine_next_actions(candidates: list, *, hygiene_required: bool) -> list:
    """Bounded to `MAX_NEXT_ACTIONS` (schema: `next_actions` maxItems 3).
    "Hygiene precedes feature work when hygiene is required for trustworthy
    continuation" (plan) -- hygiene-tagged candidates are moved first,
    never dropped in favor of feature work while `hygiene_required` is true.
    The caller supplies candidates in priority order within each bucket;
    this function only filters (authorized + dependency-satisfied), reorders
    hygiene-first, and bounds -- it does not invent a size/urgency ranking
    the plan doesn't define."""
    eligible = [c for c in candidates if c.authorized and c.dependency_satisfied]
    if hygiene_required:
        ordered = [c for c in eligible if c.is_hygiene] + [c for c in eligible if not c.is_hygiene]
    else:
        ordered = eligible
    bounded = [c.to_schema_dict() for c in ordered[:MAX_NEXT_ACTIONS]]
    validate_next_actions_list(bounded)
    return bounded


# ---------------------------------------------------------------------------
# 6. Natural-stopping determination (plan: normative glossary "Natural
#    stopping point").
# ---------------------------------------------------------------------------

STOPPING_OUTCOMES = (
    "acceptance_and_hygiene_complete", "genuine_blocker", "operator_stop", "no_authorized_action_remains", "continue",
)


@dataclass(frozen=True)
class StoppingDecision:
    outcome: str
    reason: str

    def plain_language(self) -> str:
        return self.reason


def determine_stopping(
    *,
    operator_requested_stop: bool,
    blockers: list,  # list[BlockerClassification]
    acceptance_complete: bool,
    hygiene: HygieneReport,
    next_actions: list,
) -> StoppingDecision:
    """Exactly one of the plan's four stopping reasons, or "continue" (plan:
    normative glossary "Natural stopping point": "acceptance plus hygiene is
    complete; an actual blocker exists; the operator explicitly stops; or no
    authorized dependency-satisfied action remains. Otherwise autonomous
    execution continues."). The plan does not state a precedence when more
    than one condition holds at once; this implementation checks the
    operator's own explicit word first (the most direct authority), then a
    genuine blocker (which by definition means no safe action remains
    regardless of any other state), then acceptance+hygiene, then action
    availability -- a deliberate, noted ordering choice, not a plan
    requirement."""
    if operator_requested_stop:
        return StoppingDecision("operator_stop", "Stopping because you asked to stop.")

    true_blockers = [b for b in blockers if b.classification == "true_blocker"]
    if true_blockers:
        return StoppingDecision("genuine_blocker", true_blockers[0].plain_language())

    if acceptance_complete and hygiene.all_clear:
        return StoppingDecision("acceptance_and_hygiene_complete", "Stopping because the work is accepted and the kitchen is clean.")

    if not next_actions:
        return StoppingDecision("no_authorized_action_remains", "Stopping here: there's nothing left that's both allowed and ready to go right now.")

    return StoppingDecision("continue", "Continuing: there's still a next step that's allowed and ready to go.")
