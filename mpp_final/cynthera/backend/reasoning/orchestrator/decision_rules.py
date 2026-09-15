"""Authoritative Decision Rules Engine for CYNTHERA.

Single Source of Truth for recommendation classification (Rule Set v3.2).
Provides pure, deterministic rule evaluation shared between production orchestrators
and evaluation/benchmark runners.

Rule Set v3.2 — Evidence-First Architecture with Empirical Opposition (Phase 5.16 / 5.17):
- Rule -2 (DATA AVAILABILITY FAILURE): Critical DBs failed → INSUFFICIENT_DATA
- Rule -1 (APPROVED INDICATION): ChEMBL signals approved for this disease
    → PROMISING, bypass ClinicalTrials safety lock (Rule 4)
    → Overridden to UNCERTAIN if strong empirical opposition coexists
    → Safety veto still applies (Rules 0 and 3)
- Rule 0 (SAFETY_VETO): Boxed warning + HIGH risk → NOT_RECOMMENDED
- Rule 1b (UNRESOLVED CONFLICT): Directional contradiction detected → UNCERTAIN
- Rule 2b (DIRECTIONAL OPPOSITION VETO): Target-level directional opposition → NOT_RECOMMENDED
- Rule 1b (EPISTEMIC CONFLICT): SS >= 0.60 AND Opposition >= 0.60 → UNCERTAIN
- Rule 2b (EMPIRICAL OPPOSITION VETO): Opposition in ("MODERATE", "HIGH") AND score >= 0.45 → NOT_RECOMMENDED
- Rule 2 (CLINICAL FAILURE VETO): failed_trial_count >= 2 and risk >= 0.50 → NOT_RECOMMENDED
- Rule 3 (SAFETY_VETO): RS >= 0.70 → NOT_RECOMMENDED (or UNCERTAIN if approved)
- Rule 1 (HIGH-QUALITY THERAPEUTIC EVIDENCE): Documented trial success & RS <= 0.39 → PROMISING
- Rule 1 (PROMISING with gates): SS >= 0.40, MS >= 0.40, RS <= 0.39
    → Gate 1b: Mechanistic quality (WEAK_SPECULATIVE without approval → UNCERTAIN)
    → Gate 1c: Therapeutic anchor gate (requires trial success or approved anchor → UNCERTAIN)
- Rule 4 (SAFETY_LOCK): ClinicalTrials failed AND not approved → cap at UNCERTAIN
- Rule 5 (UNCERTAIN): default
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from backend.core.enums.recommendation import RecommendationStatus


class OppositionConflictType(str, Enum):
    """Categorical classification of interaction between indication and empirical opposition."""

    NO_CONFLICT = "NO_CONFLICT"
    INVALID_OPPOSITION = "INVALID_OPPOSITION"
    ISOLATED_DIRECT_CONFLICT = "ISOLATED_DIRECT_CONFLICT"
    REPLICATED_DIRECT_CONFLICT = "REPLICATED_DIRECT_CONFLICT"
    REGULATORY_SAFETY_CONFLICT = "REGULATORY_SAFETY_CONFLICT"


class OppositionConflictDecision(BaseModel):
    """Structured resolution of interaction between indication status and empirical opposition."""

    model_config = {"frozen": True}

    conflict_type: OppositionConflictType = Field(..., description="Categorical conflict classification.")
    should_veto: bool = Field(..., description="True if opposition warrants an empirical veto.")
    should_route_uncertain: bool = Field(..., description="True if evidence conflict routes recommendation to UNCERTAIN.")
    reason_code: str = Field(..., description="Machine-readable conflict resolution reason code.")
    explanation: str = Field(..., description="Human-auditable explanation of conflict resolution.")


def classify_opposition_conflict(
    is_approved: bool,
    opposition_score: float,
    independent_group_count: int,
    qualified_opposition: bool,
    has_direct_harm: bool = False,
    regulatory_safety_veto: bool = False,
    **kwargs: Any,
) -> OppositionConflictDecision:
    """Authoritatively classify the interaction between an indication and empirical opposition.

    Encodes explicit conflict policy (CYNTHERA P0b-2.1):
    - Regulatory contraindication overrides regardless of empirical status.
    - Zero or disqualified opposition produces NO_CONFLICT or INVALID_OPPOSITION.
    - For approved indications:
      * Isolated single study (n=1) -> ISOLATED_DIRECT_CONFLICT (routes to UNCERTAIN under Rule 1b).
      * Replicated studies (n>=2) -> REPLICATED_DIRECT_CONFLICT (participates in Rule 2b veto).
    - For unapproved indications:
      * Qualified direct opposition (n>=1) -> REPLICATED_DIRECT_CONFLICT / ISOLATED_DIRECT_CONFLICT (Rule 2b veto eligible).
    """
    if regulatory_safety_veto:
        return OppositionConflictDecision(
            conflict_type=OppositionConflictType.REGULATORY_SAFETY_CONFLICT,
            should_veto=True,
            should_route_uncertain=False,
            reason_code="REGULATORY_SAFETY_OVERRIDE",
            explanation="Authoritative regulatory contraindication or boxed warning overrides indication.",
        )

    if opposition_score <= 0.0 or not qualified_opposition:
        if opposition_score > 0.0 and not qualified_opposition:
            return OppositionConflictDecision(
                conflict_type=OppositionConflictType.INVALID_OPPOSITION,
                should_veto=False,
                should_route_uncertain=False,
                reason_code="INVALID_OPPOSITION_FILTERED",
                explanation="Negative trial evidence is semantically invalid or indirect relative to hypothesis.",
            )
        return OppositionConflictDecision(
            conflict_type=OppositionConflictType.NO_CONFLICT,
            should_veto=False,
            should_route_uncertain=False,
            reason_code="NO_OPPOSITION",
            explanation="No qualified empirical opposition detected.",
        )

    # Qualified direct empirical opposition exists (score > 0)
    if not is_approved:
        conflict_type = (
            OppositionConflictType.REPLICATED_DIRECT_CONFLICT
            if independent_group_count >= 2
            else OppositionConflictType.ISOLATED_DIRECT_CONFLICT
        )
        return OppositionConflictDecision(
            conflict_type=conflict_type,
            should_veto=True,
            should_route_uncertain=False,
            reason_code="UNAPPROVED_EMPIRICAL_VETO",
            explanation=(
                f"Unapproved candidate has documented empirical opposition (score={opposition_score:.3f}, "
                f"groups={independent_group_count}, direct_harm={has_direct_harm})."
            ),
        )

    # Approved indication handling:
    if independent_group_count >= 2:
        return OppositionConflictDecision(
            conflict_type=OppositionConflictType.REPLICATED_DIRECT_CONFLICT,
            should_veto=True,
            should_route_uncertain=False,
            reason_code="APPROVED_REPLICATED_OPPOSITION_VETO",
            explanation=(
                f"Replicated independent empirical opposition ({independent_group_count} study groups) "
                f"overrides approved therapeutic anchor due to replicated clinical trial failure or futility."
            ),
        )

    # Isolated single negative trial against approved indication
    return OppositionConflictDecision(
        conflict_type=OppositionConflictType.ISOLATED_DIRECT_CONFLICT,
        should_veto=False,
        should_route_uncertain=True,
        reason_code="APPROVED_ISOLATED_OPPOSITION_CONFLICT",
        explanation=(
            f"Approved therapeutic anchor coexists with an isolated, single-study negative trial "
            f"(Opposition Score = {opposition_score:.3f}, {independent_group_count} group). "
            f"Vetoing an approved indication requires replicated independent empirical opposition (n_groups >= 2); "
            f"evidence conflict routes recommendation to UNCERTAIN."
        ),
    )


class DecisionResult:
    """Canonical result object returned by apply_decision_rules.

    Behaves as a 2-tuple (status, reasons) for complete backward compatibility
    with existing unpacking syntax:
        status, reasons = apply_decision_rules(...)

    Also provides rich attribute access:
        result.status -> RecommendationStatus
        result.reasons -> list[str]
        result.deciding_rule -> str (reasons[0] or primary deciding rule)
        result.trace -> dict[str, Any]
        result.conflict -> OppositionConflictDecision | None
    """

    def __init__(
        self,
        status: RecommendationStatus,
        reasons: list[str],
        trace: dict[str, Any] | None = None,
        conflict: OppositionConflictDecision | None = None,
    ) -> None:
        self.status = status
        self.reasons = reasons
        self.trace = trace or {}
        self.conflict = conflict

    @property
    def deciding_rule(self) -> str:
        for r in reversed(self.reasons):
            if r.startswith("Rule ") and not r.startswith("Rule -1 (APPROVED INDICATION ANCHOR)"):
                return r
        return self.reasons[0] if self.reasons else ""

    def __iter__(self):
        return iter((self.status, self.reasons))

    def __getitem__(self, index: int):
        return (self.status, self.reasons)[index]

    def __len__(self) -> int:
        return 2

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, tuple):
            return (self.status, self.reasons) == other
        if isinstance(other, DecisionResult):
            return self.status == other.status and self.reasons == other.reasons
        return False

    def __repr__(self) -> str:
        return f"DecisionResult(status={self.status}, reasons_count={len(self.reasons)})"


def build_evidence_checks(
    support: Any = None,
    mechanistic: Any = None,
    risk: Any = None,
    contradictions: list[Any] | None = None,
    package: Any = None,
    opposition: Any = None,
    *,
    support_score: float | None = None,
    support_level: str | None = None,
    evidence_count: int | None = None,
    mechanistic_score: float | None = None,
    mechanistic_level: str | None = None,
    pathway_count: int | None = None,
    risk_score: float | None = None,
    risk_level: str | None = None,
    opposition_score: float | None = None,
    opposition_level: str | None = None,
    independent_group_count: int | None = None,
    sources_failed: list[str] | None = None,
    **kwargs: Any,
) -> list[str]:
    """Build evidence checklist for transparent recommendation display."""
    ss_score = float(
        support_score
        if support_score is not None
        else (getattr(support, "score", 0.0) if support else 0.0)
    )
    ss_level = str(
        support_level
        if support_level is not None
        else (getattr(support, "level", "LOW") if support else "LOW")
    )
    ss_count = int(
        evidence_count
        if evidence_count is not None
        else (getattr(support, "evidence_count", 0) if support else 0)
    )

    ms_score = float(
        mechanistic_score
        if mechanistic_score is not None
        else (getattr(mechanistic, "score", 0.0) if mechanistic else 0.0)
    )
    ms_level = str(
        mechanistic_level
        if mechanistic_level is not None
        else (getattr(mechanistic, "level", "LOW") if mechanistic else "LOW")
    )
    ms_paths = int(
        pathway_count
        if pathway_count is not None
        else (getattr(mechanistic, "pathway_count", 0) if mechanistic else 0)
    )

    rs_score = float(
        risk_score
        if risk_score is not None
        else (getattr(risk, "score", 0.0) if risk else 0.0)
    )
    rs_level = str(
        risk_level
        if risk_level is not None
        else (getattr(risk, "level", "LOW") if risk else "LOW")
    )

    opp_score = float(
        opposition_score
        if opposition_score is not None
        else (getattr(opposition, "score", 0.0) if opposition else 0.0)
    )
    opp_level = str(
        opposition_level
        if opposition_level is not None
        else (getattr(opposition, "level", "NONE") if opposition else "NONE")
    )
    opp_groups = int(
        independent_group_count
        if independent_group_count is not None
        else (getattr(opposition, "independent_group_count", 0) if opposition else 0)
    )

    pkg_sources = list(
        sources_failed
        if sources_failed is not None
        else (getattr(package, "sources_failed", []) if package else [])
    )
    contra_list = contradictions or []

    checks: list[str] = []
    checks.append("Evidence signals:")
    checks.append(
        f"  {'[PASS]' if ss_score >= 0.5 else '[FAIL]'} Literature support: "
        f"SS = {ss_score:.3f} ({ss_level}) from {ss_count} records"
    )
    checks.append(
        f"  {'[PASS]' if ms_score >= 0.4 else '[FAIL]'} Mechanistic plausibility: "
        f"MS = {ms_score:.3f} ({ms_level}), "
        f"{ms_paths} pathway(s)"
    )
    checks.append(
        f"  {'[FAIL]' if rs_score >= 0.4 else '[PASS]'} Safety/Risk acceptable: "
        f"RS = {rs_score:.3f} ({rs_level})"
    )
    if (opposition or opposition_score is not None) and opp_score > 0:
        checks.append(
            f"  {'[FAIL]' if opp_score >= 0.45 else '[PASS]'} Empirical opposition: "
            f"Score = {opp_score:.3f} ({opp_level}) from {opp_groups} group(s)"
        )
    checks.append(
        f"  {'[FAIL]' if contra_list else '[PASS]'} Evidence consistency: "
        f"{'No contradictions' if not contra_list else f'{len(contra_list)} contradiction(s) detected'}"
    )
    checks.append(
        f"  {'[PASS]' if 'clinicaltrials' not in pkg_sources else '[FAIL]'} "
        f"Human clinical data: "
        f"{'Available' if 'clinicaltrials' not in pkg_sources else 'Unavailable (ClinicalTrials.gov)'}"
    )
    return checks


def apply_decision_rules(
    support: Any = None,
    mechanistic: Any = None,
    risk: Any = None,
    contradictions: list[Any] | None = None,
    package: Any = None,
    safety_profile: Any = None,
    prior_ctx: Any = None,
    scientific_context: Any = None,
    opposition: Any = None,
    contradiction_summary: Any = None,
    *,
    is_approved: bool | None = None,
    matched_chembl_term: str | None = None,
    support_score: float | None = None,
    mechanistic_score: float | None = None,
    risk_score: float | None = None,
    safety_veto: bool | None = None,
    strong_conflict: bool | None = None,
    contradiction_level: str | None = None,
    has_high_quality_therapeutic: bool | None = None,
    opp_assessment: Any = None,
    failed_trial_count: int | None = None,
    opposition_score: float | None = None,
    opposition_level: str | None = None,
    independent_group_count: int | None = None,
    disease_name: str | None = None,
    sources_failed: list[str] | None = None,
    has_boxed_warning: bool | None = None,
    overall_safety_grade: str | None = None,
    regulatory_confidence: float | None = None,
    **kwargs: Any,
) -> DecisionResult:
    """Apply deterministic recommendation rules over (SS, MS, RS, and Opposition).

    Authoritative single source of truth for CYNTHERA.
    """
    reasons: list[str] = []

    # 1. Normalize opposition
    opp = opposition if opposition is not None else opp_assessment
    opp_score = float(
        opposition_score
        if opposition_score is not None
        else (getattr(opp, "score", 0.0) if opp else 0.0)
    )
    opp_level = str(
        opposition_level
        if opposition_level is not None
        else (getattr(opp, "level", "NONE") if opp else "NONE")
    )
    opp_groups = int(
        independent_group_count
        if independent_group_count is not None
        else (getattr(opp, "independent_group_count", 0) if opp else 0)
    )
    opp_claims = int(getattr(opp, "qualified_negative_claim_count", 0) if opp else 0)
    opp_evaluated = bool(opp is not None or opposition_score is not None)

    # 2. Build evidence checks
    checks = build_evidence_checks(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=contradictions,
        package=package,
        opposition=opp,
        support_score=support_score,
        mechanistic_score=mechanistic_score,
        risk_score=risk_score,
        opposition_score=opp_score,
        opposition_level=opp_level,
        independent_group_count=opp_groups,
        sources_failed=sources_failed,
        **kwargs,
    )

    # 3. Extract approval state
    if is_approved is not None:
        is_approved_val = bool(is_approved)
    else:
        is_approved_val = bool(
            getattr(getattr(scientific_context, "regulatory", None), "status", None)
            == "APPROVED"
        )

    dis_name = (
        disease_name
        or getattr(getattr(package, "disease", None), "name", "")
        or kwargs.get("disease", "")
        or ""
    )
    matched_term = (
        matched_chembl_term
        or getattr(prior_ctx, "matched_indication_term", "")
        or ""
    )
    reg_confidence = float(
        regulatory_confidence
        if regulatory_confidence is not None
        else getattr(getattr(scientific_context, "regulatory", None), "confidence", 1.0)
    )

    # 4. Extract package failure state
    pkg_failed_sources = list(
        sources_failed
        if sources_failed is not None
        else (getattr(package, "sources_failed", []) if package else [])
    )

    # 5. Extract support variables
    ss_score = float(
        support_score
        if support_score is not None
        else (getattr(support, "score", 0.0) if support else 0.0)
    )
    ss_evidence_count = int(
        getattr(support, "evidence_count", 0)
        if support
        else kwargs.get("evidence_count", 0)
    )
    if has_high_quality_therapeutic is not None:
        ss_high_qual = bool(has_high_quality_therapeutic)
    else:
        ss_high_qual = bool(
            getattr(support, "has_high_quality_therapeutic", False) if support else False
        )

    # 6. Extract mechanistic variables
    ms_score = float(
        mechanistic_score
        if mechanistic_score is not None
        else (getattr(mechanistic, "score", 0.0) if mechanistic else 0.0)
    )
    ms_evidence_status = str(
        getattr(mechanistic, "evidence_status", "SUCCESS")
        if mechanistic
        else kwargs.get("mechanistic_evidence_status", "SUCCESS")
    )
    ms_score_components = (
        getattr(mechanistic, "score_components", {})
        or kwargs.get("score_components", {})
        or {}
    )
    ms_support_level = ms_score_components.get("support_level")

    # 7. Extract risk variables
    rs_score = float(
        risk_score
        if risk_score is not None
        else (getattr(risk, "score", 0.0) if risk else 0.0)
    )
    rs_failed_trials = int(
        failed_trial_count
        if failed_trial_count is not None
        else (getattr(risk, "failed_trial_count", 0) if risk else 0)
    )
    rs_contradictions = int(getattr(risk, "contradiction_count", 0) if risk else 0)

    # 8. Extract safety variables
    safety_boxed = bool(
        has_boxed_warning
        if has_boxed_warning is not None
        else (
            getattr(safety_profile, "has_boxed_warning", False)
            if safety_profile
            else (safety_veto or False)
        )
    )
    safety_grade = str(
        overall_safety_grade
        if overall_safety_grade is not None
        else (
            getattr(safety_profile, "overall_safety_grade", "A")
            if safety_profile
            else ("D" if safety_veto else "A")
        )
    )
    effective_safety_veto = (
        safety_boxed
        or (
            safety_veto
            if safety_veto is not None
            else (getattr(risk, "safety_veto", False) if risk else False)
        )
    )

    # 9. Extract contradiction / conflict variables
    contra_list = contradictions or []
    is_strong_conflict = bool(
        strong_conflict
        if strong_conflict is not None
        else (
            getattr(contradiction_summary, "strong_conflict", False)
            if contradiction_summary
            else False
        )
    )
    contra_resolution = str(
        contradiction_level
        if contradiction_level is not None
        else (
            getattr(contradiction_summary, "resolution", "")
            if contradiction_summary
            else ""
        )
    )
    contra_explanation = str(
        getattr(contradiction_summary, "explanation", "")
        if contradiction_summary
        else ""
    )

    # Observability and trace state
    approval_anchor_detected = is_approved_val
    rule_minus_one_entered = is_approved_val
    downstream_opposition_rules_reached = is_approved_val
    conflict_resolution_reached = bool(
        contradiction_summary is not None
        or contra_list
        or strong_conflict is not None
        or contradiction_level is not None
    )

    # Determine direct harm flag from opposition assessment
    has_direct_harm = bool(getattr(opp, "has_direct_harm", False))

    # Authoritative opposition conflict classification (CYNTHERA P0b-2.1)
    opp_qualified = bool(
        opp_claims > 0
        or (opp is None and opp_score > 0.0)
        or bool(getattr(opp, "qualified_claims", []))
    )
    conflict = classify_opposition_conflict(
        is_approved=is_approved_val,
        opposition_score=opp_score,
        independent_group_count=opp_groups,
        qualified_opposition=opp_qualified,
        has_direct_harm=has_direct_harm,
        regulatory_safety_veto=bool(is_approved_val and safety_boxed and rs_score >= 0.6),
    )

    def _finalize(status: RecommendationStatus, res_reasons: list[str]) -> DecisionResult:
        deciding = ""
        for r in reversed(res_reasons):
            if r.startswith("Rule ") and not r.startswith("Rule -1 (APPROVED INDICATION ANCHOR)"):
                deciding = r
                break
        if not deciding:
            deciding = res_reasons[0] if res_reasons else ""
        trace = {
            "approved_anchor": is_approved_val,
            "approval_anchor_detected": approval_anchor_detected,
            "rule_minus_one_entered": rule_minus_one_entered,
            "opposition_evaluated": opp_evaluated,
            "opposition_score": opp_score,
            "opposition_level": opp_level,
            "independent_groups": opp_groups,
            "qualified_negative_claim_count": opp_claims,
            "has_direct_harm": has_direct_harm,
            "conflict_type": conflict.conflict_type.value,
            "conflict_reason": conflict.reason_code,
            "downstream_opposition_rules_reached": downstream_opposition_rules_reached,
            "conflict_resolution_reached": conflict_resolution_reached,
            "rule_fired": deciding,
            "final_recommendation": status.value if hasattr(status, "value") else str(status),
        }
        return DecisionResult(status=status, reasons=res_reasons, trace=trace, conflict=conflict)

    # ─────────────────────────────────────────────
    # RULE CASCADE
    # ─────────────────────────────────────────────

    # Rule -2: Check Source Availability / Pipeline Failure Gate
    if ms_evidence_status == "SOURCE_UNAVAILABLE" or (
        "chembl" in pkg_failed_sources and "uniprot" in pkg_failed_sources
    ):
        reasons.append(
            f"Rule -2 (DATA AVAILABILITY FAILURE): Critical target/mechanism databases "
            f"failed during retrieval: [{', '.join(pkg_failed_sources)}]. "
            "Unable to evaluate hypothesis due to source unavailability."
        )
        reasons.extend(checks)
        return _finalize(RecommendationStatus.INSUFFICIENT_DATA, reasons)

    # Rule -1 (APPROVED INDICATION ANCHOR): Approval is recorded as a supporting therapeutic anchor.
    if is_approved_val:
        dis_info = f" matching '{dis_name}'" if dis_name else ""
        term_info = f" Matched ChEMBL term: '{matched_term}'." if matched_term else ""
        reasons.append(
            f"Rule -1 (APPROVED INDICATION ANCHOR): ChEMBL indication data indicates this drug "
            f"is approved (max_phase_for_ind = 4) for an indication{dis_info} "
            f"(regulatory confidence {reg_confidence:.0%}).{term_info} "
            "Approval recorded as positive therapeutic anchor. "
            "Downstream safety, opposition, and conflict rules are evaluated."
        )

    # Rule 0: Safety & Contraindication Veto — boxed warning or high-concern safety profile
    if is_approved_val:
        if conflict.conflict_type == OppositionConflictType.REGULATORY_SAFETY_CONFLICT or (safety_boxed and rs_score >= 0.6):
            reasons.append(
                f"Rule 0 override: Despite approved status, boxed warning AND "
                f"Risk Score = {rs_score:.3f} (HIGH). "
                "Safety concerns override even for approved indications."
            )
            reasons.extend(checks)
            return _finalize(RecommendationStatus.NOT_RECOMMENDED, reasons)
    else:
        if safety_boxed or safety_grade == "D" or effective_safety_veto or rs_score >= 0.6:
            reasons.append(
                f"Rule 0 (SAFETY VETO): ⚠ Boxed warning / contraindication detected. Risk Score = "
                f"{rs_score:.3f}. Safety grade: {safety_grade}. "
                "NOT RECOMMENDED due to unacceptable safety profile / disease contraindication."
            )
            reasons.extend(checks)
            return _finalize(RecommendationStatus.NOT_RECOMMENDED, reasons)

    # Directional contradiction check: unresolved conflict (Rule 1b)
    if is_strong_conflict or contra_resolution == "UNRESOLVED_CONFLICT":
        reasons.append(
            f"Rule 1b (UNRESOLVED CONFLICT): Directional contradiction detected across targets/evidence groups. "
            f"Conflict summary: {contra_explanation or 'Conflicting directional evidence'}."
        )
        reasons.extend(checks)
        return _finalize(RecommendationStatus.UNCERTAIN, reasons)

    # Contradiction summary directional opposition veto (Rule 2b)
    if contra_resolution == "OPPOSES":
        reasons.append(
            "Rule 2b (DIRECTIONAL OPPOSITION VETO): Directional evidence indicates target opposition. "
            "NOT RECOMMENDED due to directional therapeutic conflict."
        )
        reasons.extend(checks)
        return _finalize(RecommendationStatus.NOT_RECOMMENDED, reasons)

    # Rule 1b: Strong Support + Strong Opposition (Epistemic Conflict)
    if opp_score >= 0.60 and ss_score >= 0.60:
        reasons.append(
            f"Rule 1b (EPISTEMIC CONFLICT): Strong supporting evidence (SS = {ss_score:.3f} ≥ 0.60) "
            f"coexists with strong empirical opposing evidence (Opposition Score = {opp_score:.3f} ≥ 0.60). "
            "Evidence is fundamentally contradictory across independent clinical/literature sources."
        )
        reasons.extend(checks)
        return _finalize(RecommendationStatus.UNCERTAIN, reasons)

    # Rule 1b: Isolated empirical opposition against approved indication
    if conflict.conflict_type == OppositionConflictType.ISOLATED_DIRECT_CONFLICT and conflict.should_route_uncertain:
        reasons.append(
            f"Rule 1b (APPROVED INDICATION vs ISOLATED EMPIRICAL OPPOSITION CONFLICT): "
            f"Approved therapeutic anchor coexists with an isolated, single-study negative trial "
            f"(Opposition Score = {opp_score:.3f}, {opp_groups} independent group). "
            "Vetoing an approved indication requires replicated independent empirical opposition (n_groups >= 2); "
            "evidence conflict routes recommendation to UNCERTAIN."
        )
        reasons.extend(checks)
        return _finalize(RecommendationStatus.UNCERTAIN, reasons)

    # Rule 2b: Empirical Opposition Veto — explicit disease-specific negative therapeutic evidence
    if conflict.should_veto and opp_level in ("MODERATE", "HIGH") and opp_score >= 0.45:
        if conflict.conflict_type == OppositionConflictType.REPLICATED_DIRECT_CONFLICT:
            reasons.append(
                f"Rule 2b (EMPIRICAL OPPOSITION VETO): Replicated empirical opposition "
                f"score = {opp_score:.3f} ({opp_level}) across {opp_groups} independent study group(s) "
                "overrides approved therapeutic anchor due to replicated clinical trial failure or futility."
            )
        else:
            reasons.append(
                f"Rule 2b (EMPIRICAL OPPOSITION VETO): Documented empirical opposition score = "
                f"{opp_score:.3f} ({opp_level}) across {opp_groups} "
                f"independent study group(s). NOT RECOMMENDED due to explicit disease-specific clinical failure, "
                "futility, or negative therapeutic outcome."
            )
        reasons.extend(checks)
        return _finalize(RecommendationStatus.NOT_RECOMMENDED, reasons)

    # Rule 2: Clinical Trial Failure Assessment — multiple clinically significant trial failures or high risk burden
    if rs_score >= 0.60 or (rs_failed_trials >= 2 and rs_score >= 0.50):
        reasons.append(
            f"Rule 2 (CLINICAL FAILURE VETO): Risk Score = {rs_score:.3f} "
            f"with {rs_failed_trials} clinically significant trial failure(s). "
            "NOT RECOMMENDED due to documented clinical endpoint failures or safety signals."
        )
        reasons.extend(checks)
        return _finalize(RecommendationStatus.NOT_RECOMMENDED, reasons)

    # Rule 3: Safety veto — high risk score (evidence-based, fires before data-lock)
    if rs_score >= 0.7:
        if is_approved_val:
            reasons.append(
                f"Rule 3 override: Despite approved status, Risk Score is HIGH ({rs_score:.3f}). "
                "Significant safety signals detected."
            )
            reasons.extend(checks)
            return _finalize(RecommendationStatus.UNCERTAIN, reasons)
        else:
            reasons.append(
                f"Rule 3 (SAFETY VETO): Risk Score is HIGH ({rs_score:.3f}). "
                f"Triggered by {rs_failed_trials} failed trial(s) and "
                f"{rs_contradictions} contradiction(s). "
                f"Safety grade: {safety_grade}."
            )
            reasons.extend(checks)
            return _finalize(RecommendationStatus.NOT_RECOMMENDED, reasons)

    # Rule -1 Resolution: Approved Indication Confirmed
    if is_approved_val:
        reasons.append(
            "Rule -1 (APPROVED INDICATION RESOLUTION): Approved therapeutic anchor confirmed. "
            "All safety, empirical opposition, and conflict evaluations passed. "
            "Confirmed PROMISING under approved indication pathway."
        )
        reasons.extend(checks)
        return _finalize(RecommendationStatus.PROMISING, reasons)

    # Rule 1: High-quality therapeutic evidence (clinical trial success) can establish PROMISING
    if ss_high_qual and rs_score <= 0.39:
        reasons.append(
            f"Rule 1 (HIGH-QUALITY THERAPEUTIC EVIDENCE): Documented clinical trial success or high-quality therapeutic evidence "
            f"(SS = {ss_score:.3f}, RS = {rs_score:.3f}). High-quality evidence establishes therapeutic viability."
        )
        reasons.extend(checks)
        return _finalize(RecommendationStatus.PROMISING, reasons)

    # Rule 1: Promising criteria (evidence-based, fires before data-lock)
    if ss_score >= 0.4 and ms_score >= 0.4 and rs_score <= 0.39:
        if ms_support_level == "WEAK_SPECULATIVE" and not is_approved_val:
            reasons.append(
                "Rule 1b (MECHANISTIC QUALITY GATE): Mechanistic candidate is WEAK_SPECULATIVE without regulatory approval. "
                "Cannot recommend solely on speculative mechanism."
            )
            reasons.extend(checks)
            return _finalize(RecommendationStatus.UNCERTAIN, reasons)

        # Rule 1c: Therapeutic Evidence Anchor Gate (Phase 5.17 correctness fix)
        if not ss_high_qual:
            reasons.append(
                f"Rule 1c (LITERATURE SIGNAL WITHOUT THERAPEUTIC ANCHOR): "
                f"Support score reflects literature co-mentions "
                f"(SS = {ss_score:.3f}, from {ss_evidence_count} record(s)) and "
                f"mechanistic plausibility (MS = {ms_score:.3f}), but no "
                "pair-specific clinical trial success or approved therapeutic indication was found. "
                "Promoting to UNCERTAIN pending human clinical validation of this drug-disease pair."
            )
            reasons.extend(checks)
            return _finalize(RecommendationStatus.UNCERTAIN, reasons)

        reasons.append(
            f"Rule 1 (PROMISING): SS = {ss_score:.3f} (≥ 0.40), "
            f"MS = {ms_score:.3f} (≥ 0.40), "
            f"RS = {rs_score:.3f} (≤ 0.39). "
            f"High-quality therapeutic evidence confirmed (has_high_quality_therapeutic = True). "
            f"Safety grade: {safety_grade}."
        )
        reasons.extend(checks)
        return _finalize(RecommendationStatus.PROMISING, reasons)

    # Rule 4: Safety lock — clinical trials data unavailable (fallback, after evidence)
    if "clinicaltrials" in pkg_failed_sources:
        reasons.append(
            "Rule 4 (SAFETY LOCK): ClinicalTrials.gov data unavailable. "
            "Without human clinical evidence, the maximum confidence level is UNCERTAIN. "
            "This is a conservative safety constraint for repurposing hypotheses, "
            "not a scientific negative."
        )
        reasons.extend(checks)
        return _finalize(RecommendationStatus.UNCERTAIN, reasons)

    # Rule 5: Default uncertain
    reasons.append(
        f"Rule 5 (UNCERTAIN): Mixed or sparse evidence. "
        f"SS={ss_score:.3f}, MS={ms_score:.3f}, RS={rs_score:.3f}. "
        f"Safety grade: {safety_grade}."
    )
    reasons.extend(checks)
    return _finalize(RecommendationStatus.UNCERTAIN, reasons)
