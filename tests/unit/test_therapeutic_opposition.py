"""Unit tests for Phase 5.16: Therapeutic Opposition Integration.

Validates the 18 specific opposition requirements defined in Section 22:
TEST 1: Explicit FAILED_TO_IMPROVE claim + disease relevant + adequate quality -> opposition eligible
TEST 2: TERMINATED_FOR_FUTILITY -> opposition eligible
TEST 3: TERMINATED_FOR_SAFETY -> opposition eligible
TEST 4: WORSENED_OUTCOME -> opposition eligible
TEST 5: CONTRAINDICATED -> opposition eligible
TEST 6: Missing approval only -> NOT opposition
TEST 7: Missing mechanism only -> NOT opposition
TEST 8: Trial status COMPLETED without explicit negative outcome -> NOT opposition
TEST 9: Administrative termination -> NOT opposition
TEST 10: Same NCT represented through multiple records -> one independent evidence group
TEST 11: Irrelevant disease -> excluded
TEST 12: Weak negative evidence -> does not independently qualify for OPPOSE
TEST 13: Strong SUPPORT + strong OPPOSITION -> UNCERTAIN (Rule 1b)
TEST 14: Strong empirical opposition -> NOT_RECOMMENDED (Rule 2b)
TEST 15: Approved indication + strong empirical opposition -> NOT_RECOMMENDED (Rule 2b veto overrides regulatory status)
TEST 16: Existing Lisinopril -> Hypertension positive behavior -> SUPPORT / PROMISING
TEST 17: Existing weak/indirect case -> UNCERTAIN
TEST 18: Existing AdvancedConflictResolver behavior remains unchanged
"""
from __future__ import annotations

import uuid
import pytest
from unittest.mock import MagicMock

from backend.core.domain.claim import Claim
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.contradiction import Contradiction
from backend.core.domain.disease import Disease
from backend.core.domain.drug import Drug
from backend.core.domain.reasoning_result import (
    OppositionAssessment,
    RiskAssessment,
    SupportAssessment,
    MechanisticAssessment,
)
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.evidence_type import EvidenceType
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.recommendation import RecommendationStatus
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.identifier import CanonicalIdentifier, ResolvedIdentifierSet
from backend.core.value_objects.provenance import ProvenanceReference
from backend.reasoning.agents.clinical_safety_agent import SafetyProfile
from backend.reasoning.agents.prior_knowledge_agent import PriorKnowledgeContext
from backend.reasoning.conflict.conflict_resolver import AdvancedConflictResolver
from backend.reasoning.context.scientific_context_builder import DimensionalAssessment, ScientificContext
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    trial_to_negative_claim,
)
from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator


def _make_drug(name: str) -> Drug:
    return Drug(
        name=name,
        identifiers=ResolvedIdentifierSet(
            entity_name=name,
            entity_type="drug",
            identifiers=[CanonicalIdentifier(namespace="chembl", value="CHEMBL1")],
        ),
    )


def _make_disease(name: str) -> Disease:
    return Disease(
        name=name,
        identifiers=ResolvedIdentifierSet(
            entity_name=name,
            entity_type="disease",
            identifiers=[CanonicalIdentifier(namespace="mesh", value="D001")],
        ),
    )


def _make_opposition_claim(
    predicate: PredicateType,
    drug: str = "TestDrug",
    disease: str = "TestDisease",
    record_id: str = "NCT12345678",
    source_name: str = "ClinicalTrials.gov",
    erw_val: float = 0.90,
    confidence: float = 0.95,
) -> Claim:
    return Claim(
        subject=drug,
        predicate=predicate,
        object=disease,
        confidence=confidence,
        erw=ERW(value=erw_val, base_weight=erw_val),
        provenance=ProvenanceReference(
            source_name=source_name,
            source_version="2024",
            record_id=record_id,
        ),
        raw_text=f"{drug} {predicate.value} for {disease}",
        is_validated=True,
    )


def _make_package(drug_name: str = "TestDrug", disease_name: str = "TestDisease", trials: list[ClinicalTrial] | None = None) -> RetrievalPackage:
    return RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=_make_drug(drug_name),
        disease=_make_disease(disease_name),
        targets=[],
        proteins=[],
        pathways=[],
        evidence_records=[],
        clinical_trials=trials or [],
        retrieval_confidence="HIGH",
    )


def _make_sci_context(status: str = "INVESTIGATIONAL", confidence: float = 0.0) -> ScientificContext:
    return ScientificContext(
        DimensionalAssessment("regulatory", status, confidence, []),
        DimensionalAssessment("repurposing", "NOVEL", 0.0, []),
        DimensionalAssessment("mechanistic", "NONE", 0.0, []),
        DimensionalAssessment("clinical", "NONE", 0.0, []),
        DimensionalAssessment("maturity", "NONE", 0.0, []),
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 - 5: Five real opposition predicates
# ─────────────────────────────────────────────────────────────────────────────

def test_1_explicit_failed_to_improve_is_opposition_eligible():
    """TEST 1: Explicit FAILED_TO_IMPROVE claim + disease relevant + adequate quality -> opposition eligible."""
    claim = _make_opposition_claim(PredicateType.FAILED_TO_IMPROVE)
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "TestDrug", "TestDisease")
    assert assessment.qualified_negative_claim_count == 1
    assert assessment.excluded_negative_claim_count == 0
    assert assessment.independent_group_count == 1
    assert assessment.strongest_group_weight > 0.0
    assert assessment.level != "NONE"
    assert assessment.score > 0.0


def test_2_terminated_for_futility_is_opposition_eligible():
    """TEST 2: TERMINATED_FOR_FUTILITY -> opposition eligible."""
    claim = _make_opposition_claim(PredicateType.TERMINATED_FOR_FUTILITY)
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "TestDrug", "TestDisease")
    assert assessment.qualified_negative_claim_count == 1
    assert assessment.excluded_negative_claim_count == 0
    assert assessment.independent_group_count == 1
    assert assessment.level != "NONE"
    assert assessment.score > 0.0


def test_3_terminated_for_safety_is_opposition_eligible():
    """TEST 3: TERMINATED_FOR_SAFETY -> opposition eligible."""
    claim = _make_opposition_claim(PredicateType.TERMINATED_FOR_SAFETY)
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "TestDrug", "TestDisease")
    assert assessment.qualified_negative_claim_count == 1
    assert assessment.excluded_negative_claim_count == 0
    assert assessment.independent_group_count == 1
    assert assessment.level != "NONE"
    assert assessment.score > 0.0


def test_4_worsened_outcome_is_opposition_eligible():
    """TEST 4: WORSENED_OUTCOME -> opposition eligible."""
    claim = _make_opposition_claim(PredicateType.WORSENED_OUTCOME)
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "TestDrug", "TestDisease")
    assert assessment.qualified_negative_claim_count == 1
    assert assessment.excluded_negative_claim_count == 0
    assert assessment.independent_group_count == 1
    assert assessment.level != "NONE"
    assert assessment.score > 0.0


def test_5_contraindicated_is_opposition_eligible():
    """TEST 5: CONTRAINDICATED -> opposition eligible."""
    claim = _make_opposition_claim(PredicateType.CONTRAINDICATED)
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "TestDrug", "TestDisease")
    assert assessment.qualified_negative_claim_count == 1
    assert assessment.excluded_negative_claim_count == 0
    assert assessment.independent_group_count == 1
    assert assessment.level != "NONE"
    assert assessment.score > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6 - 9: Absence of evidence is NOT opposition
# ─────────────────────────────────────────────────────────────────────────────

def test_6_missing_approval_only_is_not_opposition():
    """TEST 6: Missing approval only -> NOT opposition."""
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([], "TestDrug", "TestDisease")
    assert assessment.score == 0.0
    assert assessment.level == "NONE"
    assert assessment.qualified_negative_claim_count == 0
    assert assessment.independent_group_count == 0


def test_7_missing_mechanism_only_is_not_opposition():
    """TEST 7: Missing mechanism only -> NOT opposition."""
    assessor = TherapeuticOppositionAssessor()
    # Support claim (INHIBITS predicate, not negative opposition predicate)
    claim = Claim(
        subject="TestDrug",
        predicate=PredicateType.INHIBITS,
        object="TestDisease",
        confidence=0.9,
        erw=ERW(value=0.9, base_weight=0.9),
        provenance=ProvenanceReference(source_name="PubMed", source_version="2024", record_id="PMID123"),
        is_validated=True,
    )
    assessment = assessor.assess([claim], "TestDrug", "TestDisease")
    assert assessment.score == 0.0
    assert assessment.level == "NONE"
    assert assessment.qualified_negative_claim_count == 0


def test_8_trial_completed_without_negative_outcome_is_not_opposition():
    """TEST 8: Trial status COMPLETED without explicit negative outcome -> NOT opposition claim."""
    trial = ClinicalTrial(
        nct_id="NCT00012345",
        title="Completed Success Trial",
        phase="Phase III",
        status=TrialOutcomeStatus.COMPLETED_SUCCESS,
        enrollment=500,
        provenance=ProvenanceReference(
            source_name="ClinicalTrials.gov",
            source_version="2024",
            record_id="NCT00012345",
        ),
    )
    claim = trial_to_negative_claim(trial, "TestDrug", "TestDisease")
    assert claim is None


def test_9_administrative_termination_is_not_opposition():
    """TEST 9: Administrative termination -> NOT opposition claim."""
    trial = ClinicalTrial(
        nct_id="NCT00099999",
        title="Terminated for funding",
        phase="Phase II",
        status=TrialOutcomeStatus.TERMINATED_ADMINISTRATIVE,
        enrollment=50,
        provenance=ProvenanceReference(
            source_name="ClinicalTrials.gov",
            source_version="2024",
            record_id="NCT00099999",
        ),
    )
    claim = trial_to_negative_claim(trial, "TestDrug", "TestDisease")
    assert claim is None


# ─────────────────────────────────────────────────────────────────────────────
# TEST 10 - 12: Independence, relevance gating, and weak evidence
# ─────────────────────────────────────────────────────────────────────────────

def test_10_same_nct_multiple_records_is_one_independent_group():
    """TEST 10: Same NCT represented through multiple records -> one independent evidence group."""
    c1 = _make_opposition_claim(PredicateType.FAILED_TO_IMPROVE, record_id="NCT00112233", source_name="ClinicalTrials.gov")
    c2 = _make_opposition_claim(PredicateType.FAILED_TO_IMPROVE, record_id="NCT00112233", source_name="PubMed")
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([c1, c2], "TestDrug", "TestDisease")
    assert assessment.independent_group_count == 1
    assert assessment.qualified_negative_claim_count == 2


def test_11_irrelevant_disease_is_excluded():
    """TEST 11: Irrelevant disease -> excluded."""
    claim = _make_opposition_claim(PredicateType.FAILED_TO_IMPROVE, disease="Unrelated Condition")
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "TestDrug", "TargetDisease")
    assert assessment.qualified_negative_claim_count == 0
    assert assessment.excluded_negative_claim_count == 1
    assert assessment.score == 0.0
    assert assessment.level == "NONE"


def test_12_weak_negative_evidence_does_not_qualify_for_oppose():
    """TEST 12: Weak negative evidence (low ERW / confidence) -> does not independently qualify for OPPOSE."""
    claim = Claim(
        subject="TestDrug",
        predicate=PredicateType.FAILED_TO_IMPROVE,
        object="TestDisease",
        confidence=0.30,
        erw=ERW(value=0.20, base_weight=0.20),
        provenance=ProvenanceReference(source_name="Unknown", source_version="2020", record_id="REF1"),
        raw_text="Weak negative signal",
        is_validated=True,
    )
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "TestDrug", "TestDisease")
    assert assessment.score < 0.45
    assert assessment.level in ("LOW", "NONE")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 13 - 15: Orchestrator Recommendation Rules
# ─────────────────────────────────────────────────────────────────────────────

def test_13_strong_support_and_strong_opposition_yields_uncertain():
    """TEST 13: Strong SUPPORT + strong OPPOSITION -> UNCERTAIN (Rule 1b epistemic conflict)."""
    support = SupportAssessment(score=0.75, level="HIGH")
    mechanistic = MechanisticAssessment(score=0.60, level="MEDIUM")
    risk = RiskAssessment(score=0.20, level="LOW")
    opposition = OppositionAssessment(
        score=0.65,
        level="HIGH",
        independent_group_count=2,
        qualified_negative_claim_count=2,
    )
    package = _make_package()
    safety = SafetyProfile(overall_safety_grade="A")
    prior = PriorKnowledgeContext()
    sci_ctx = _make_sci_context()

    orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    status, reasons = orch._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=package,
        safety_profile=safety,
        prior_ctx=prior,
        scientific_context=sci_ctx,
        opposition=opposition,
    )

    assert status == RecommendationStatus.UNCERTAIN
    assert any("EPISTEMIC CONFLICT" in r for r in reasons)


def test_14_strong_empirical_opposition_yields_not_recommended():
    """TEST 14: Strong empirical opposition -> NOT_RECOMMENDED (Rule 2b empirical opposition veto)."""
    support = SupportAssessment(score=0.20, level="LOW")
    mechanistic = MechanisticAssessment(score=0.30, level="LOW")
    risk = RiskAssessment(score=0.20, level="LOW")
    opposition = OppositionAssessment(
        score=0.55,
        level="MODERATE",
        independent_group_count=1,
        qualified_negative_claim_count=1,
    )
    package = _make_package()
    safety = SafetyProfile(overall_safety_grade="A")
    prior = PriorKnowledgeContext()
    sci_ctx = _make_sci_context()

    orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    status, reasons = orch._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=package,
        safety_profile=safety,
        prior_ctx=prior,
        scientific_context=sci_ctx,
        opposition=opposition,
    )

    assert status == RecommendationStatus.NOT_RECOMMENDED
    assert any("EMPIRICAL OPPOSITION VETO" in r for r in reasons)


def test_15_approved_indication_plus_strong_empirical_opposition_yields_not_recommended():
    """TEST 15: Approved indication + replicated strong empirical opposition -> NOT_RECOMMENDED (Rule 2b veto overrides regulatory status)."""
    support = SupportAssessment(score=0.85, level="HIGH", has_high_quality_therapeutic=True)
    mechanistic = MechanisticAssessment(score=0.50, level="MEDIUM")
    risk = RiskAssessment(score=0.20, level="LOW")
    opposition = OppositionAssessment(
        score=0.50,
        level="MODERATE",
        independent_group_count=2,
        qualified_negative_claim_count=2,
    )
    package = _make_package()
    safety = SafetyProfile(overall_safety_grade="A")
    prior = PriorKnowledgeContext(matched_indication_term="TestDisease")
    sci_ctx = _make_sci_context(status="APPROVED", confidence=1.0)

    orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    status, reasons = orch._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=package,
        safety_profile=safety,
        prior_ctx=prior,
        scientific_context=sci_ctx,
        opposition=opposition,
    )

    assert status == RecommendationStatus.NOT_RECOMMENDED
    assert any("EMPIRICAL OPPOSITION VETO" in r for r in reasons)


def test_15b_approved_indication_plus_isolated_opposition_yields_uncertain():
    """TEST 15b: Approved indication + isolated single-study opposition -> UNCERTAIN (Rule 1b epistemic conflict)."""
    support = SupportAssessment(score=0.85, level="HIGH", has_high_quality_therapeutic=True)
    mechanistic = MechanisticAssessment(score=0.50, level="MEDIUM")
    risk = RiskAssessment(score=0.20, level="LOW")
    opposition = OppositionAssessment(
        score=0.50,
        level="MODERATE",
        independent_group_count=1,
        qualified_negative_claim_count=1,
    )
    package = _make_package()
    safety = SafetyProfile(overall_safety_grade="A")
    prior = PriorKnowledgeContext(matched_indication_term="TestDisease")
    sci_ctx = _make_sci_context(status="APPROVED", confidence=1.0)

    orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    status, reasons = orch._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=package,
        safety_profile=safety,
        prior_ctx=prior,
        scientific_context=sci_ctx,
        opposition=opposition,
    )

    assert status == RecommendationStatus.UNCERTAIN
    assert any("ISOLATED EMPIRICAL OPPOSITION CONFLICT" in r for r in reasons)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 16 - 18: Regression Audits
# ─────────────────────────────────────────────────────────────────────────────

def test_16_lisinopril_hypertension_positive_behavior_preserved():
    """TEST 16: Existing Lisinopril -> Hypertension positive behavior -> PROMISING."""
    support = SupportAssessment(score=0.95, level="HIGH", has_high_quality_therapeutic=True)
    mechanistic = MechanisticAssessment(score=0.80, level="HIGH")
    risk = RiskAssessment(score=0.10, level="LOW")
    opposition = OppositionAssessment.empty()
    package = _make_package("Lisinopril", "Hypertension")
    safety = SafetyProfile(overall_safety_grade="A")
    prior = PriorKnowledgeContext(matched_indication_term="Hypertension")
    sci_ctx = _make_sci_context(status="APPROVED", confidence=1.0)

    orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    status, reasons = orch._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=package,
        safety_profile=safety,
        prior_ctx=prior,
        scientific_context=sci_ctx,
        opposition=opposition,
    )

    assert status == RecommendationStatus.PROMISING
    assert any("APPROVED INDICATION" in r for r in reasons)


def test_17_weak_indirect_case_remains_uncertain():
    """TEST 17: Existing weak/indirect case -> UNCERTAIN."""
    support = SupportAssessment(score=0.25, level="LOW")
    mechanistic = MechanisticAssessment(score=0.20, level="LOW")
    risk = RiskAssessment(score=0.15, level="LOW")
    opposition = OppositionAssessment.empty()
    package = _make_package("WeakDrug", "RareDisease")
    safety = SafetyProfile(overall_safety_grade="A")
    prior = PriorKnowledgeContext()
    sci_ctx = _make_sci_context(status="INVESTIGATIONAL", confidence=0.0)

    orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    status, reasons = orch._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=package,
        safety_profile=safety,
        prior_ctx=prior,
        scientific_context=sci_ctx,
        opposition=opposition,
    )

    assert status == RecommendationStatus.UNCERTAIN
    assert any("Rule 5 (UNCERTAIN)" in r for r in reasons)


def test_18_advanced_conflict_resolver_behavior_remains_unchanged():
    """TEST 18: Existing AdvancedConflictResolver behavior remains unchanged (ACTIVATES vs INHIBITS)."""
    c_act = Claim(
        subject="DrugA",
        predicate=PredicateType.ACTIVATES,
        object="TargetT",
        confidence=0.9,
        erw=ERW(value=0.9, base_weight=0.9),
        provenance=ProvenanceReference(source_name="PubMed", source_version="2024", record_id="PMID1"),
        is_validated=True,
    )
    c_inh = Claim(
        subject="DrugA",
        predicate=PredicateType.INHIBITS,
        object="TargetT",
        confidence=0.9,
        erw=ERW(value=0.9, base_weight=0.9),
        provenance=ProvenanceReference(source_name="PubMed", source_version="2024", record_id="PMID2"),
        is_validated=True,
    )
    resolver = AdvancedConflictResolver()
    report = resolver.resolve([c_act, c_inh])
    assert len(report.contradictions) == 1
    assert report.contradictions[0].shared_subject == "DrugA"
    assert "Directional conflict" in report.contradictions[0].explanation


# ─────────────────────────────────────────────────────────────────────────────
# TESTS 19 - 21: Phase 5.17 Defect 1 — RCT evidence type on trial claims
# ─────────────────────────────────────────────────────────────────────────────

def _make_trial(
    nct_id: str,
    status: TrialOutcomeStatus,
    title: str = "Test Trial",
    design_allocation: str | None = "RANDOMIZED",
    study_type: str | None = "INTERVENTIONAL",
    intervention_names: list[str] | None = None,
    comparator_names: list[str] | None = None,
    why_stopped: str | None = None,
    condition_names: list[str] | None = None,
) -> ClinicalTrial:
    return ClinicalTrial(
        nct_id=nct_id,
        title=title,
        phase="Phase III",
        status=status,
        drug_chembl_id="CHEMBL1",
        disease_identifier="MESH:D001",
        enrollment=500,
        provenance=ProvenanceReference(
            source_name="ClinicalTrials.gov",
            source_version="2024",
            record_id=nct_id,
        ),
        design_allocation=design_allocation,
        study_type=study_type,
        intervention_names=intervention_names or [],
        comparator_names=comparator_names or [],
        condition_names=condition_names or [],
        why_stopped=why_stopped,
    )


def test_19_trial_claim_has_rct_evidence_type():
    """TEST 19 (Phase 5.17): trial_to_negative_claim sets evidence_type='RCT' when metadata supports it."""
    trial = _make_trial(
        nct_id="NCT04332107",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        title="Azithromycin for COVID-19 Treatment in Outpatients Nationwide",
        design_allocation="RANDOMIZED",
    )
    claim = trial_to_negative_claim(trial, "Azithromycin", "COVID-19")
    assert claim is not None, "trial_to_negative_claim must produce a Claim for efficacy-terminated trial"
    assert claim.evidence_type == "RCT", (
        f"Expected evidence_type='RCT' on trial-derived claim, got {claim.evidence_type!r}. "
        "This is required so compute_claim_weight() applies the 0.90 type multiplier, not 0.50."
    )


def test_20_rct_evidence_type_produces_correct_weight():
    """TEST 20 (Phase 5.17): compute_claim_weight uses 0.90 RCT multiplier for trial claims."""
    from backend.reasoning.conflict.evidence_weighting import compute_claim_weight, EVIDENCE_TYPE_WEIGHTS

    trial = _make_trial(
        nct_id="NCT04332107",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        design_allocation="RANDOMIZED",
        condition_names=["TestDisease"],
    )
    claim = trial_to_negative_claim(trial, "TestDrug", "TestDisease")
    assert claim is not None

    weight = compute_claim_weight(claim)
    expected = round(0.90 * EVIDENCE_TYPE_WEIGHTS["RCT"] * 1.0, 4)  # = 0.81 (no recency boost)
    assert weight == pytest.approx(expected, abs=0.05), (
        f"Expected compute_claim_weight(trial_claim) ≈ {expected:.4f} (RCT-weighted), "
        f"got {weight:.4f}. Check that evidence_type='RCT' is set and EVIDENCE_TYPE_WEIGHTS['RCT']={EVIDENCE_TYPE_WEIGHTS['RCT']}."
    )
    # Critically: verify it is NOT the old broken value
    broken_weight = round(0.90 * EVIDENCE_TYPE_WEIGHTS["UNKNOWN"] * 1.0, 4)  # = 0.45
    assert weight != pytest.approx(broken_weight, abs=0.001), (
        f"compute_claim_weight returned {weight:.4f} which matches the broken UNKNOWN weight {broken_weight:.4f}. "
        "The evidence_type='RCT' is not being read correctly."
    )


def test_21_two_rct_failures_produce_moderate_opposition():
    """TEST 21 (Phase 5.17): Two independent RCT-weighted failed trials produce MODERATE+ opposition."""
    trial_1 = _make_trial(
        nct_id="NCT04332107",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        title="Azithromycin for COVID-19 Treatment in Outpatients Nationwide",
        design_allocation="RANDOMIZED",
    )
    trial_2 = _make_trial(
        nct_id="NCT04341870",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        title="CORIMUNO-19 Trial: Sarilumab, Azithromycin",
        design_allocation="RANDOMIZED",
        condition_names=["COVID-19"],
    )

    claim_1 = trial_to_negative_claim(trial_1, "Azithromycin", "COVID-19")
    claim_2 = trial_to_negative_claim(trial_2, "Azithromycin", "COVID-19")
    assert claim_1 is not None and claim_2 is not None

    assert claim_1.evidence_type == "RCT"
    assert claim_2.evidence_type == "RCT"

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim_1, claim_2], "Azithromycin", "COVID-19")

    assert assessment.independent_group_count == 2
    assert assessment.score >= 0.45
    assert assessment.level in ("MODERATE", "HIGH")


def test_22_attribution_gate_excludes_comparator_drug():
    """TEST 22: Negative result against intervention A must NOT become opposition against comparator B."""
    trial = _make_trial(
        nct_id="NCT09999999",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        title="DrugA Versus DrugB in Treatment of ConditionX",
        comparator_names=["DrugB"],
        intervention_names=["DrugA"],
        why_stopped="Terminated early due to lack of efficacy of DrugA compared to DrugB",
    )

    # When querying DrugB (the comparator), attribution gate must return None
    claim_b = trial_to_negative_claim(trial, "DrugB", "ConditionX")
    assert claim_b is None, "Comparator drug must NOT receive a negative opposition claim"


def test_23_attribution_gate_retains_investigational_drug():
    """TEST 23: Negative result against intervention A MUST become opposition against intervention A."""
    trial = _make_trial(
        nct_id="NCT09999999",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        title="DrugA Versus DrugB in Treatment of ConditionX",
        comparator_names=["DrugB"],
        intervention_names=["DrugA"],
        why_stopped="Terminated early due to lack of efficacy of DrugA compared to DrugB",
    )

    # When querying DrugA (the experimental intervention), opposition claim must be generated
    claim_a = trial_to_negative_claim(trial, "DrugA", "ConditionX")
    assert claim_a is not None, "Investigational drug must receive negative opposition claim"
    assert claim_a.subject == "DrugA"
    assert claim_a.predicate == PredicateType.FAILED_TO_IMPROVE


def test_24_evidence_type_study_design_granularity():
    """TEST 24: Evidence-type classification granularity and compute_claim_weight().

    Checks:
    - RCT (RANDOMIZED) -> weight = 0.90 * 0.90 = 0.81
    - non-RCT / interventional (NON_RANDOMIZED) -> weight = 0.90 * 0.75 = 0.675
    - observational (OBSERVATIONAL) -> weight = 0.90 * 0.65 = 0.585
    - unknown study design (None) -> UNKNOWN, weight = 0.90 * 0.50 = 0.45
    """
    from backend.reasoning.conflict.evidence_weighting import compute_claim_weight

    # 1. RCT
    trial_rct = _make_trial(
        nct_id="NCT00000001",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        title="Randomized Study of DrugX",
        design_allocation="RANDOMIZED",
        condition_names=["DiseaseY"],
    )
    claim_rct = trial_to_negative_claim(trial_rct, "DrugX", "DiseaseY")
    assert claim_rct is not None
    assert claim_rct.evidence_type == "RCT"
    assert compute_claim_weight(claim_rct) == pytest.approx(0.81, abs=0.01)

    # 2. Non-RCT / interventional
    trial_interv = _make_trial(
        nct_id="NCT00000002",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        title="Open-Label Phase II Study of DrugX",
        design_allocation="NON_RANDOMIZED",
        study_type="INTERVENTIONAL",
        condition_names=["DiseaseY"],
    )
    claim_interv = trial_to_negative_claim(trial_interv, "DrugX", "DiseaseY")
    assert claim_interv is not None
    assert claim_interv.evidence_type == "INTERVENTIONAL"
    assert compute_claim_weight(claim_interv) == pytest.approx(0.675, abs=0.01)

    # 3. Observational
    trial_obs = _make_trial(
        nct_id="NCT00000003",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        title="Observational Registry Study",
        design_allocation=None,
        study_type="OBSERVATIONAL",
        condition_names=["DiseaseY"],
    )
    claim_obs = trial_to_negative_claim(trial_obs, "DrugX", "DiseaseY")
    assert claim_obs is not None
    assert claim_obs.evidence_type == "OBSERVATIONAL"
    assert compute_claim_weight(claim_obs) == pytest.approx(0.585, abs=0.01)

    # 4. Unknown study design (must remain UNKNOWN)
    trial_unk = _make_trial(
        nct_id="NCT00000004",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        title="Study of DrugX in DiseaseY",
        design_allocation=None,
        study_type=None,
    )
    claim_unk = trial_to_negative_claim(trial_unk, "DrugX", "DiseaseY")
    assert claim_unk is not None
    assert claim_unk.evidence_type == "UNKNOWN"
    assert compute_claim_weight(claim_unk) == pytest.approx(0.45, abs=0.01)


def test_25_cyn_013_nct02313909_attribution_regression():
    """TEST 25 (CYN-013 Regression): NCT02313909 NAVIGATE ESUS trial attribution audit.

    Trial: Rivaroxaban Versus Aspirin in Secondary Prevention of Stroke and Prevention
           of Systemic Embolism in Patients With Recent Embolic Stroke of Undetermined Source (ESUS)
    Status: TERMINATED_LACK_OF_EFFICACY

    Aspirin was the active comparator / standard of care control.
    The failure of rivaroxaban over aspirin must NOT generate an opposition claim for Aspirin.
    """
    trial_cyn013 = ClinicalTrial(
        nct_id="NCT02313909",
        title="Rivaroxaban Versus Aspirin in Secondary Prevention of Stroke and Prevention of Systemic Embolism in Patients With Recent Embolic Stroke of Undetermined Source (ESUS)",
        phase="Phase III",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        drug_chembl_id="CHEMBL25",
        provenance=ProvenanceReference(
            source_name="ClinicalTrials.gov",
            source_version="2024",
            record_id="NCT02313909",
        ),
        comparator_names=["Aspirin"],
        intervention_names=["Rivaroxaban"],
        why_stopped="Study stopped early due to lack of efficacy of rivaroxaban compared to aspirin and increased bleeding",
    )

    # Evaluating Aspirin -> must return None (attribution gate blocks it)
    claim_aspirin = trial_to_negative_claim(trial_cyn013, "Aspirin", "Secondary prevention of cardiovascular disease")
    assert claim_aspirin is None, (
        "Attribution Gate failed: NCT02313909 negative outcome applied to Rivaroxaban, "
        "not Aspirin. Aspirin was the comparator and must NOT receive a negative opposition claim."
    )

    # Evaluating Rivaroxaban -> must generate opposition claim
    claim_rivaroxaban = trial_to_negative_claim(trial_cyn013, "Rivaroxaban", "Secondary prevention of cardiovascular disease")
    assert claim_rivaroxaban is not None, "Rivaroxaban was the investigational drug and should receive opposition claim"
    assert claim_rivaroxaban.subject == "Rivaroxaban"
    assert claim_rivaroxaban.predicate == PredicateType.FAILED_TO_IMPROVE

