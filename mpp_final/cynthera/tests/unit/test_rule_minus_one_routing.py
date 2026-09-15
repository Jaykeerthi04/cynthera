"""Deterministic unit tests and regression verification for Phase 1B Rule -1 routing."""

import pytest
from backend.core.domain.claim import Claim
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.approval_signal import ApprovalSignal
from backend.core.value_objects.identifier import CanonicalIdentifier, ResolvedIdentifierSet
from backend.core.enums import PredicateType, EvidenceType
from backend.core.domain.hypothesis import Hypothesis
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.reasoning.agents.clinical_safety_agent import SafetyProfile
from backend.core.domain.reasoning_result import (
    SupportAssessment, MechanisticAssessment, RiskAssessment, OppositionAssessment,
    RecommendationStatus
)
from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
from backend.reasoning.context.scientific_context_builder import ScientificContextBuilder
from backend.reasoning.agents.prior_knowledge_agent import PriorKnowledgeContext
from backend.core.domain.contradiction_summary import ContradictionSummary


def make_package(
    drug_name: str,
    disease_name: str,
    is_approved: bool = True,
    sources_failed: list[str] | None = None,
) -> RetrievalPackage:
    hyp = Hypothesis(drug_name=drug_name, disease_name=disease_name)
    drug = Drug(
        name=drug_name,
        identifiers=ResolvedIdentifierSet(
            entity_name=drug_name,
            entity_type="drug",
            identifiers=[CanonicalIdentifier(namespace="chembl", value=f"CHEMBL_{drug_name.upper()}")],
        ),
    )
    disease = Disease(
        name=disease_name,
        identifiers=ResolvedIdentifierSet(
            entity_name=disease_name,
            entity_type="disease",
            identifiers=[CanonicalIdentifier(namespace="mesh", value=f"MESH_{disease_name.upper()}")],
        ),
    )
    approval_signal = None
    if is_approved:
        approval_signal = ApprovalSignal(
            is_approved=True,
            max_phase=4,
            matched_indication_term=disease_name,
            match_confidence=1.0,
        )
    return RetrievalPackage(
        hypothesis_id=hyp.id,
        drug=drug,
        disease=disease,
        approval_signal=approval_signal,
        sources_failed=sources_failed or [],
    )


def test_approved_positive_no_opposition_reaches_rule_minus_one_resolution():
    """Approved drug with no opposition passes through downstream rules to Rule -1 resolution."""
    orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    
    pkg = make_package("Lisinopril", "hypertension")
    support = SupportAssessment(score=0.7, level="HIGH", evidence_count=10, has_high_quality_therapeutic=True)
    mechanistic = MechanisticAssessment(score=0.8, level="HIGH", pathway_count=3)
    risk = RiskAssessment(score=0.2, level="LOW", failed_trial_count=0, contradiction_count=0)
    safety = SafetyProfile(overall_safety_grade="A", has_boxed_warning=False)
    
    prior_ctx = PriorKnowledgeContext(
        is_approved_indication=True,
        evaluation_pathway="APPROVED_INDICATION",
        matched_indication_term="hypertension",
    )
    sci_ctx = ScientificContextBuilder.build(prior_ctx, support, mechanistic, [], pkg)
    opp = OppositionAssessment.empty()
    
    rec, reasons = orch._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=pkg,
        safety_profile=safety,
        prior_ctx=prior_ctx,
        scientific_context=sci_ctx,
        opposition=opp,
    )
    
    assert rec == RecommendationStatus.PROMISING
    assert any("Rule -1 (APPROVED INDICATION RESOLUTION)" in r for r in reasons)
    
    trace = orch._last_rule_minus_one_trace
    assert trace["approval_anchor_detected"] is True
    assert trace["rule_minus_one_entered"] is True
    assert trace["opposition_evaluated"] is True
    assert trace["opposition_score"] == 0.0
    assert trace["opposition_level"] == "NONE"
    assert trace["downstream_opposition_rules_reached"] is True
    assert trace["final_recommendation"] == "PROMISING"


def test_approved_with_high_opposition_vetoed_by_rule_2b():
    """Approved drug with genuine high opposition is NOT short-circuited by Rule -1; Rule 2b vetoes."""
    orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    
    pkg = make_package("Niacin", "cardiovascular disease")
    support = SupportAssessment(score=0.7, level="HIGH", evidence_count=10, has_high_quality_therapeutic=True)
    mechanistic = MechanisticAssessment(score=0.8, level="HIGH", pathway_count=3)
    risk = RiskAssessment(score=0.3, level="LOW", failed_trial_count=1, contradiction_count=0)
    safety = SafetyProfile(overall_safety_grade="B", has_boxed_warning=False)
    
    prior_ctx = PriorKnowledgeContext(
        is_approved_indication=True,
        evaluation_pathway="APPROVED_INDICATION",
        matched_indication_term="cardiovascular disease",
    )
    sci_ctx = ScientificContextBuilder.build(prior_ctx, support, mechanistic, [], pkg)
    opp = OppositionAssessment(
        score=0.5120,
        level="HIGH",
        independent_group_count=2,
        qualified_negative_claim_count=2,
        rationale="Documented clinical failure in AIM-HIGH and literature.",
    )
    
    rec, reasons = orch._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=pkg,
        safety_profile=safety,
        prior_ctx=prior_ctx,
        scientific_context=sci_ctx,
        opposition=opp,
    )
    
    assert rec == RecommendationStatus.NOT_RECOMMENDED
    assert any("Rule 2b (EMPIRICAL OPPOSITION VETO)" in r for r in reasons)
    
    trace = orch._last_rule_minus_one_trace
    assert trace["approval_anchor_detected"] is True
    assert trace["rule_minus_one_entered"] is True
    assert trace["opposition_evaluated"] is True
    assert trace["opposition_score"] == 0.5120
    assert trace["opposition_level"] == "HIGH"
    assert trace["qualified_negative_claim_count"] == 2
    assert trace["downstream_opposition_rules_reached"] is True
    assert trace["final_recommendation"] == "NOT_RECOMMENDED"


def test_approved_with_boxed_warning_and_high_risk_vetoed():
    """Approved drug with boxed warning AND high risk is vetoed by Rule 0."""
    orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    
    pkg = make_package("ToxicDrug", "serious disease")
    support = SupportAssessment(score=0.7, level="HIGH", evidence_count=10, has_high_quality_therapeutic=True)
    mechanistic = MechanisticAssessment(score=0.8, level="HIGH", pathway_count=3)
    risk = RiskAssessment(score=0.65, level="HIGH", failed_trial_count=0, contradiction_count=0)
    safety = SafetyProfile(overall_safety_grade="C", has_boxed_warning=True)
    
    prior_ctx = PriorKnowledgeContext(
        is_approved_indication=True,
        evaluation_pathway="APPROVED_INDICATION",
        matched_indication_term="serious disease",
    )
    sci_ctx = ScientificContextBuilder.build(prior_ctx, support, mechanistic, [], pkg)
    opp = OppositionAssessment.empty()
    
    rec, reasons = orch._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=pkg,
        safety_profile=safety,
        prior_ctx=prior_ctx,
        scientific_context=sci_ctx,
        opposition=opp,
    )
    
    assert rec == RecommendationStatus.NOT_RECOMMENDED
    assert any("Rule 0 override" in r for r in reasons)
    assert orch._last_rule_minus_one_trace["final_recommendation"] == "NOT_RECOMMENDED"


def test_approved_with_boxed_warning_but_low_risk_survives():
    """Approved drug with boxed warning (common for biologics) but low risk survives Rule 0 to PROMISING."""
    orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    
    pkg = make_package("Adalimumab", "Crohn's disease")
    support = SupportAssessment(score=0.85, level="HIGH", evidence_count=20, has_high_quality_therapeutic=True)
    mechanistic = MechanisticAssessment(score=0.9, level="HIGH", pathway_count=4)
    risk = RiskAssessment(score=0.25, level="LOW", failed_trial_count=0, contradiction_count=0)
    safety = SafetyProfile(overall_safety_grade="B", has_boxed_warning=True)
    
    prior_ctx = PriorKnowledgeContext(
        is_approved_indication=True,
        evaluation_pathway="APPROVED_INDICATION",
        matched_indication_term="Crohn's disease",
    )
    sci_ctx = ScientificContextBuilder.build(prior_ctx, support, mechanistic, [], pkg)
    opp = OppositionAssessment.empty()
    
    rec, reasons = orch._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=pkg,
        safety_profile=safety,
        prior_ctx=prior_ctx,
        scientific_context=sci_ctx,
        opposition=opp,
    )
    
    assert rec == RecommendationStatus.PROMISING
    assert any("Rule -1 (APPROVED INDICATION RESOLUTION)" in r for r in reasons)
    assert orch._last_rule_minus_one_trace["final_recommendation"] == "PROMISING"
