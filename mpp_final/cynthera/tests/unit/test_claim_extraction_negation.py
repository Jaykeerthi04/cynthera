"""Unit tests for Phase 5.17: Claim extraction fallback negation guard and Rule 1 therapeutic gate.

TEST-NEG-01: Abstract with "did not prevent" -> FAILED_TO_IMPROVE, NOT PREVENTS
TEST-NEG-02: Abstract with unambiguous "prevent" (no negation) -> PREVENTS
TEST-NEG-03: Abstract with "fluvoxamine did not improve" -> FAILED_TO_IMPROVE
TEST-NEG-04: Abstract with "did not significantly reduce" -> FAILED_TO_IMPROVE
TEST-NEG-05: Abstract with "failed to prevent hospitalization" -> FAILED_TO_IMPROVE
TEST-NEG-06: Abstract with "no evidence of efficacy" + drug present -> FAILED_TO_IMPROVE
TEST-NEG-07: Negation guard does NOT apply when negation is far away (> 45 chars)
TEST-NEG-08: Rule 1 secondary branch with no therapeutic anchor -> UNCERTAIN
TEST-NEG-09: Rule 1 secondary branch with therapeutic anchor -> PROMISING
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from backend.reasoning.extraction.claim_extraction_agent import ClaimExtractionAgent


# ─────────────────────────────────────────────────────────────────────────────
# Helper: direct access to rule_based_fallback
# ─────────────────────────────────────────────────────────────────────────────

def _fallback(text: str, drug: str = "TestDrug", disease: str = "TestDisease") -> list[dict]:
    """Invoke _rule_based_fallback directly on a ClaimExtractionAgent instance."""
    agent = ClaimExtractionAgent.__new__(ClaimExtractionAgent)
    # Minimal init without DB or API keys
    agent._model = "gemini-2.0-flash"
    agent._api_key = None
    agent._last_extraction_method = "rule_based_fallback"
    agent._has_logged_unconfigured_warning = True
    agent._raw_cache = None
    import asyncio
    agent._sem = asyncio.Semaphore(3)
    return agent._rule_based_fallback(text, drug, disease)


# ─────────────────────────────────────────────────────────────────────────────
# TEST-NEG-01 through TEST-NEG-07: Negation Guard
# ─────────────────────────────────────────────────────────────────────────────

def test_neg_01_did_not_prevent_produces_failed_to_improve():
    """TEST-NEG-01: 'did not prevent hospitalization' must map to FAILED_TO_IMPROVE, not PREVENTS.

    This is the ACTIV-6 / COVID-OUT inversion bug. The abstract contains the word 'prevent'
    but in a negated context. Before the fix, this produced PREVENTS (positive claim).
    """
    text = (
        "Fluvoxamine 50 mg twice daily did not prevent hospitalization or death "
        "in outpatient COVID-19 patients. No evidence of efficacy was found. "
        "The trial was completed per protocol (ACTIV-6, NCT04885530)."
    )
    claims = _fallback(text, drug="Fluvoxamine", disease="COVID-19")
    # Should get at least one negative claim
    predicates = [c["predicate"] for c in claims]
    assert "PREVENTS" not in predicates, (
        f"'PREVENTS' should not appear when 'prevent' is preceded by 'did not'. "
        f"Got predicates: {predicates}"
    )
    # Must have a negative predicate
    negative_predicates = {
        "FAILED_TO_IMPROVE", "NO_SIGNIFICANT_BENEFIT", "TERMINATED_FOR_FUTILITY",
        "TERMINATED_FOR_SAFETY", "WORSENED_OUTCOME", "CONTRAINDICATED",
    }
    assert any(p in negative_predicates for p in predicates), (
        f"Expected a negative predicate for a negated prevention claim. Got: {predicates}"
    )


def test_neg_02_unambiguous_prevents_still_fires():
    """TEST-NEG-02: Abstract with unambiguous positive 'prevent' (no negation) -> PREVENTS."""
    text = (
        "Aspirin prevents platelet aggregation and reduces the risk of myocardial infarction "
        "in patients with established cardiovascular disease."
    )
    claims = _fallback(text, drug="Aspirin", disease="myocardial infarction")
    predicates = [c["predicate"] for c in claims]
    assert "PREVENTS" in predicates, (
        f"Expected PREVENTS for unambiguous positive prevention claim. Got: {predicates}"
    )


def test_neg_03_fluvoxamine_did_not_improve_covid19():
    """TEST-NEG-03: 'fluvoxamine did not improve' -> FAILED_TO_IMPROVE."""
    text = (
        "In this randomized placebo-controlled trial, fluvoxamine did not improve "
        "time to sustained recovery compared with placebo (HR 0.96; 95% CrI, 0.86-1.06). "
        "Posterior probability of superiority was 0.21."
    )
    claims = _fallback(text, drug="fluvoxamine", disease="COVID-19")
    predicates = [c["predicate"] for c in claims]
    assert "FAILED_TO_IMPROVE" in predicates, (
        f"Expected FAILED_TO_IMPROVE for 'did not improve' pattern. Got: {predicates}"
    )
    assert "PREVENTS" not in predicates, (
        f"PREVENTS should not appear. Got: {predicates}"
    )


def test_neg_04_did_not_significantly_reduce():
    """TEST-NEG-04: 'did not significantly reduce' -> FAILED_TO_IMPROVE."""
    text = (
        "Metformin did not significantly reduce the risk of COVID-19 hospitalization "
        "or death compared to placebo in this outpatient trial."
    )
    claims = _fallback(text, drug="Metformin", disease="COVID-19")
    predicates = [c["predicate"] for c in claims]
    assert "FAILED_TO_IMPROVE" in predicates, (
        f"Expected FAILED_TO_IMPROVE for 'did not significantly reduce'. Got: {predicates}"
    )


def test_neg_05_failed_to_prevent_hospitalization():
    """TEST-NEG-05: 'failed to prevent hospitalization' -> FAILED_TO_IMPROVE, not PREVENTS."""
    text = (
        "Ivermectin failed to prevent hospitalization or death in outpatients with COVID-19 "
        "in this quadruple-masked randomized trial."
    )
    claims = _fallback(text, drug="Ivermectin", disease="COVID-19")
    predicates = [c["predicate"] for c in claims]
    assert "PREVENTS" not in predicates, (
        f"PREVENTS should not appear when 'prevent' follows 'failed to'. Got: {predicates}"
    )
    assert "FAILED_TO_IMPROVE" in predicates, (
        f"Expected FAILED_TO_IMPROVE for 'failed to prevent'. Got: {predicates}"
    )


def test_neg_06_no_evidence_of_efficacy_with_drug():
    """TEST-NEG-06: 'no evidence of efficacy' when drug is present -> FAILED_TO_IMPROVE."""
    text = (
        "Hydroxychloroquine showed no evidence of efficacy for COVID-19 treatment "
        "in this multicenter randomized controlled trial."
    )
    claims = _fallback(text, drug="Hydroxychloroquine", disease="COVID-19")
    predicates = [c["predicate"] for c in claims]
    assert "FAILED_TO_IMPROVE" in predicates, (
        f"Expected FAILED_TO_IMPROVE for 'no evidence of efficacy'. Got: {predicates}"
    )


def test_neg_07_negation_far_away_does_not_suppress():
    """TEST-NEG-07: Negation prefix > 45 chars before 'prevent' does NOT suppress PREVENTS.

    The negation guard inspects the 45-character window before each keyword occurrence.
    A negation clause that is 60+ characters BEFORE 'prevent' should not suppress it.
    The test text has neutral introductory text (no negation near 'prevent').
    """
    # The word "prevent" appears with a long neutral introduction that has no negation
    # within 45 chars before it. The negation guard should NOT suppress this.
    neutral_intro = "X" * 60  # 60 neutral chars before "prevent"
    text = f"Aspirin {neutral_intro} can prevent platelet aggregation in cardiovascular disease."
    claims = _fallback(text, drug="Aspirin", disease="platelet aggregation")
    predicates = [c["predicate"] for c in claims]
    # PREVENTS should NOT be suppressed because there is no negation near "prevent"
    assert len(claims) > 0, (
        f"Expected at least one claim to be extracted when 'prevent' has no nearby negation. "
        f"Got 0 claims."
    )
    assert "PREVENTS" in predicates, (
        f"Expected PREVENTS since 'prevent' has no negation within 45 chars. "
        f"Got predicates: {predicates}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST-NEG-08 and TEST-NEG-09: Rule 1c Therapeutic Anchor Gate
# ─────────────────────────────────────────────────────────────────────────────

def test_neg_08_rule1c_no_therapeutic_anchor_returns_uncertain():
    """TEST-NEG-08: Rule 1 secondary branch without therapeutic anchor -> UNCERTAIN.

    Simulates a case where SS ≥ 0.40, MS ≥ 0.40, RS ≤ 0.39, but
    has_high_quality_therapeutic=False (no approved indication, no successful trial).
    Expects UNCERTAIN, not PROMISING.
    """
    from backend.core.domain.reasoning_result import (
        SupportAssessment, MechanisticAssessment, RiskAssessment, OppositionAssessment,
    )
    from backend.core.enums.recommendation import RecommendationStatus
    from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
    from backend.reasoning.agents.clinical_safety_agent import SafetyProfile
    from backend.reasoning.agents.prior_knowledge_agent import PriorKnowledgeContext
    from backend.reasoning.context.scientific_context_builder import DimensionalAssessment, ScientificContext
    import uuid

    from backend.core.domain.disease import Disease
    from backend.core.domain.drug import Drug
    from backend.core.domain.retrieval_package import RetrievalPackage
    from backend.core.value_objects.identifier import CanonicalIdentifier, ResolvedIdentifierSet

    drug = Drug(
        name="Colchicine",
        identifiers=ResolvedIdentifierSet(
            entity_name="Colchicine",
            entity_type="drug",
            identifiers=[CanonicalIdentifier(namespace="chembl", value="CHEMBL1")],
        ),
    )
    disease = Disease(
        name="Colorectal Cancer",
        identifiers=ResolvedIdentifierSet(
            entity_name="Colorectal Cancer",
            entity_type="disease",
            identifiers=[CanonicalIdentifier(namespace="mesh", value="D015179")],
        ),
    )
    package = RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        targets=[],
        proteins=[],
        pathways=[],
        evidence_records=[],
        clinical_trials=[],
        retrieval_confidence="HIGH",
    )

    # High SS from generic literature, moderate MS, low RS — but NO therapeutic anchor
    support = SupportAssessment(
        score=0.995,
        level="HIGH",
        evidence_count=78,
        weighted_sum=12.3,
        rationale="Generic PubMed co-mentions only",
        has_high_quality_therapeutic=False,  # THE KEY: no therapeutic anchor
    )
    mechanistic = MechanisticAssessment(
        score=0.421,
        level="MEDIUM",
        pathway_count=2,
        mechanistic_chain=["Colchicine", "inhibits", "tubulin"],
        rationale="Moderate mechanistic evidence",
    )
    risk = RiskAssessment(
        score=0.213,
        level="LOW",
        failed_trial_count=0,
        contradiction_count=0,
        rationale="Low risk",
    )
    opposition = OppositionAssessment.empty()
    safety = SafetyProfile(
        overall_safety_grade="B",
        has_boxed_warning=False,
        adverse_events=[],
    )
    prior_ctx = PriorKnowledgeContext(
        has_established_precedent=False,
        evidence_boost=0.0,
        narrative="No prior knowledge.",
        matched_indication_term="",
    )
    sci_context = ScientificContext(
        DimensionalAssessment("regulatory", "INVESTIGATIONAL", 0.0, []),
        DimensionalAssessment("repurposing", "NOVEL", 0.0, []),
        DimensionalAssessment("mechanistic", "NONE", 0.0, []),
        DimensionalAssessment("clinical", "NONE", 0.0, []),
        DimensionalAssessment("maturity", "NONE", 0.0, []),
    )

    orchestrator = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    status, reasons = orchestrator._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=package,
        safety_profile=safety,
        prior_ctx=prior_ctx,
        scientific_context=sci_context,
        opposition=opposition,
    )

    assert status == RecommendationStatus.UNCERTAIN, (
        f"Expected UNCERTAIN for generic literature with no therapeutic anchor, got {status!r}. "
        f"Reasons: {reasons}"
    )
    # Verify Rule 1c rationale is present
    combined = " ".join(reasons)
    assert "Rule 1c" in combined or "THERAPEUTIC ANCHOR" in combined, (
        f"Expected Rule 1c rationale in reasons. Got: {reasons[:3]}"
    )


def test_neg_09_rule1_with_therapeutic_anchor_returns_promising():
    """TEST-NEG-09: Rule 1 with has_high_quality_therapeutic=True -> PROMISING.

    Verifies that the Rule 1c gate only blocks cases without therapeutic evidence
    and does NOT block cases that have approved indication or successful trial evidence.
    """
    from backend.core.domain.reasoning_result import (
        SupportAssessment, MechanisticAssessment, RiskAssessment, OppositionAssessment,
    )
    from backend.core.enums.recommendation import RecommendationStatus
    from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
    from backend.reasoning.agents.clinical_safety_agent import SafetyProfile
    from backend.reasoning.agents.prior_knowledge_agent import PriorKnowledgeContext
    from backend.reasoning.context.scientific_context_builder import DimensionalAssessment, ScientificContext
    import uuid

    from backend.core.domain.disease import Disease
    from backend.core.domain.drug import Drug
    from backend.core.domain.retrieval_package import RetrievalPackage
    from backend.core.value_objects.identifier import CanonicalIdentifier, ResolvedIdentifierSet

    drug = Drug(
        name="Metformin",
        identifiers=ResolvedIdentifierSet(
            entity_name="Metformin",
            entity_type="drug",
            identifiers=[CanonicalIdentifier(namespace="chembl", value="CHEMBL1431")],
        ),
    )
    disease = Disease(
        name="Type 2 Diabetes",
        identifiers=ResolvedIdentifierSet(
            entity_name="Type 2 Diabetes",
            entity_type="disease",
            identifiers=[CanonicalIdentifier(namespace="mesh", value="D003924")],
        ),
    )
    package = RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        targets=[],
        proteins=[],
        pathways=[],
        evidence_records=[],
        clinical_trials=[],
        retrieval_confidence="HIGH",
    )

    # High SS from literature + genuine therapeutic anchor
    support = SupportAssessment(
        score=0.990,
        level="HIGH",
        evidence_count=100,
        weighted_sum=15.0,
        rationale="Approved indication evidence present",
        has_high_quality_therapeutic=True,  # THE KEY: therapeutic anchor present
    )
    mechanistic = MechanisticAssessment(
        score=0.65,
        level="HIGH",
        pathway_count=5,
        mechanistic_chain=["Metformin", "activates", "AMPK"],
        rationale="Strong mechanistic evidence",
    )
    risk = RiskAssessment(
        score=0.10,
        level="LOW",
        failed_trial_count=0,
        contradiction_count=0,
        rationale="Low risk",
    )
    opposition = OppositionAssessment.empty()
    safety = SafetyProfile(
        overall_safety_grade="A",
        has_boxed_warning=False,
        adverse_events=[],
    )
    prior_ctx = PriorKnowledgeContext(
        has_established_precedent=True,
        evidence_boost=0.1,
        narrative="Metformin is approved for T2D.",
        matched_indication_term="type 2 diabetes",
    )
    sci_context = ScientificContext(
        DimensionalAssessment("regulatory", "INVESTIGATIONAL", 0.0, []),
        DimensionalAssessment("repurposing", "NOVEL", 0.0, []),
        DimensionalAssessment("mechanistic", "NONE", 0.0, []),
        DimensionalAssessment("clinical", "NONE", 0.0, []),
        DimensionalAssessment("maturity", "NONE", 0.0, []),
    )

    orchestrator = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    status, reasons = orchestrator._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=package,
        safety_profile=safety,
        prior_ctx=prior_ctx,
        scientific_context=sci_context,
        opposition=opposition,
    )

    # With therapeutic anchor, Rule 1 should fire PROMISING (not UNCERTAIN via Rule 1c)
    assert status == RecommendationStatus.PROMISING, (
        f"Expected PROMISING when has_high_quality_therapeutic=True, got {status!r}. "
        f"Reasons: {reasons}"
    )


def test_neg_10_explicit_validation_sentences():
    """TEST-NEG-10: Test fallback extractor with specific required negation sentences.

    Required test sentences:
    1. 'The drug did not improve recovery.'
    2. 'The treatment did not significantly reduce hospitalization.'
    3. 'The study failed to demonstrate efficacy.'
    4. 'No evidence of benefit was observed.'
    5. 'The treatment did not prevent hospitalization.'

    Invariant: None of these may be converted into PREVENTS.
    """
    negated_sentences = [
        "The drug did not improve recovery.",
        "The treatment did not significantly reduce hospitalization.",
        "The study failed to demonstrate efficacy.",
        "No evidence of benefit was observed.",
        "The treatment did not prevent hospitalization.",
    ]
    for sent in negated_sentences:
        claims = _fallback(sent, drug="The drug", disease="recovery")
        predicates = [c["predicate"] for c in claims]
        assert "PREVENTS" not in predicates, (
            f"Negated sentence '{sent}' was converted into PREVENTS! Predicates: {predicates}"
        )


def test_neg_11_genuine_positive_statements_remain_positive():
    """TEST-NEG-11: Genuine positive statements must produce positive predicates (IMPROVES, PREVENTS)."""
    # 1. Unambiguous positive prevent statement
    pos_prevent = "The treatment significantly prevents hospitalization in high-risk patients."
    claims_prev = _fallback(pos_prevent, drug="The treatment", disease="hospitalization")
    predicates_prev = [c["predicate"] for c in claims_prev]
    assert "PREVENTS" in predicates_prev, f"Expected PREVENTS from positive statement, got: {predicates_prev}"

    # 2. Unambiguous positive improve statement
    pos_improve = "The drug significantly improves patient recovery and clinical outcomes."
    claims_imp = _fallback(pos_improve, drug="The drug", disease="recovery")
    predicates_imp = [c["predicate"] for c in claims_imp]
    assert "IMPROVES" in predicates_imp, f"Expected IMPROVES from positive statement, got: {predicates_imp}"


def test_neg_12_adversarial_prevent_negation():
    """TEST-NEG-12: Adversarial sentences where 'prevent' appears inside a negated statement."""
    adversarial_sentences = [
        "The drug failed to prevent disease progression in randomized trials.",
        "Treatment was ineffective and did not prevent relapse.",
        "There was no evidence that the drug could prevent acute complications.",
        "The trial terminated without preventing secondary endpoints.",
    ]
    for sent in adversarial_sentences:
        claims = _fallback(sent, drug="The drug", disease="disease progression")
        predicates = [c["predicate"] for c in claims]
        assert "PREVENTS" not in predicates, (
            f"Adversarial sentence '{sent}' incorrectly produced PREVENTS! Predicates: {predicates}"
        )

