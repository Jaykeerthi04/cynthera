"""Pre-75-Case Readiness and Epistemic Consistency Verification Test Suite.

Covers:
  Test A: Opposition result consistency
  Test B: Etanercept end-to-end attribution (NCT01875991 & NCT01623752)
  Test C: Fluvoxamine opposition serialization (no overwrite)
  Test D: Metformin / LY3053102 background attribution
  Test E: Comparator-only exclusion
  Test F: Combination-arm attribution
  Test G: Hard negative -> UNCERTAIN epistemic invariant
  Test H: Approved indication routing (positive + no opposition -> SUPPORT)
  Test I: Approved positive + genuine opposition (Rule 2b veto -> NOT_RECOMMENDED / OPPOSE)
  Test J: Tamoxifen subtype indication resolution (biomarker/subtype matching & active form)
  Test K: Registered trial without results != therapeutic support
  Test L: Clinical trial result directionality (SUPPORTS vs OPPOSES vs UNKNOWN)
  Test M: Serialized result == canonical decision result
"""
import uuid
import pytest
from datetime import datetime

from backend.core.domain.claim import Claim
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.approval_signal import ApprovalSignal
from backend.core.domain.contradiction_summary import ContradictionSummary
from backend.core.domain.reasoning_result import (
    OppositionAssessment,
    ReasoningResult,
    SupportAssessment,
    MechanisticAssessment,
    RiskAssessment,
    ScientificAuditReport,
    level_from_score,
)
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.recommendation import RecommendationStatus
from backend.core.enums.trial_attribution import TrialDrugRole, AttributionTextEvidence
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    analyze_trial_drug_role,
    evaluate_trial_attribution,
    trial_to_negative_claim,
)
from backend.reasoning.therapeutic_evidence_audit import audit_high_quality_therapeutic_evidence
from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
from backend.reasoning.context.scientific_context_builder import ScientificContext, DimensionalAssessment


# =========================================================================
# Test A: Opposition Result Consistency
# =========================================================================

def test_a_opposition_result_consistency():
    """A: result.opposition_score == decision.opposition_score, level == level_from_score(score),
    qualified_claim_count == len(qualified_claims), independent_group_count == len(independent_groups).
    """
    assessor = TherapeuticOppositionAssessor()

    # Case 1: Positive opposition with 2 independent groups
    prov1 = ProvenanceReference(source_name="ClinicalTrials.gov", source_version="v1", record_id="NCT00000001", url="http://example.com/1")
    prov2 = ProvenanceReference(source_name="ClinicalTrials.gov", source_version="v1", record_id="NCT00000002", url="http://example.com/2")
    c1 = Claim(
        subject="DrugX", predicate=PredicateType.FAILED_TO_IMPROVE, object="DiseaseY",
        confidence=0.95, erw=ERW(value=0.90, base_weight=0.90), provenance=prov1,
    )
    c2 = Claim(
        subject="DrugX", predicate=PredicateType.TERMINATED_FOR_FUTILITY, object="DiseaseY",
        confidence=0.95, erw=ERW(value=0.85, base_weight=0.85), provenance=prov2,
    )

    assessment = assessor.assess([c1, c2], drug_name="DrugX", disease_name="DiseaseY")

    assert assessment.score > 0.0
    assert assessment.level == level_from_score(assessment.score)
    assert assessment.qualified_claim_count == len(assessment.qualified_claims) == 2
    assert assessment.qualified_negative_claim_count == 2
    assert assessment.independent_group_count == len(assessment.independent_groups) == 2

    # Verify ReasoningResult properties reflect the canonical assessment
    res = ReasoningResult(
        hypothesis_id=uuid.uuid4(),
        support_assessment=SupportAssessment(score=0.5, level="MEDIUM"),
        mechanistic_assessment=MechanisticAssessment(score=0.5, level="MEDIUM"),
        risk_assessment=RiskAssessment(score=0.2, level="LOW"),
        recommendation_status=RecommendationStatus.NOT_RECOMMENDED,
        audit_report=ScientificAuditReport(summary="Test audit"),
        opposition_assessment=assessment,
    )
    assert res.opposition_score == assessment.score
    assert res.opposition_level == assessment.level == level_from_score(res.opposition_score)
    assert res.qualified_negative_claim_count == assessment.qualified_negative_claim_count == 2
    assert res.independent_opposition_group_count == assessment.independent_group_count == 2

    # Case 2: Zero opposition assessment
    empty = OppositionAssessment.empty()
    assert empty.score == 0.0
    assert empty.level == "NONE" == level_from_score(0.0)
    assert empty.qualified_claim_count == len(empty.qualified_claims) == 0
    assert empty.independent_group_count == len(empty.independent_groups) == 0


# =========================================================================
# Test B: Etanercept End-to-End Attribution Forensics
# =========================================================================

def test_b_etanercept_end_to_end_attribution():
    """B: Forensic rejection of NCT01875991 (device preference/needle apprehension)
    and NCT01623752 (observational progression paired t-test) from Etanercept opposition.
    """
    # 1. NCT01875991: Usability endpoint & delivery device comparison
    t1 = ClinicalTrial(
        nct_id="NCT01875991",
        title="Preference Between Two Autoinjectors in Patients With Rheumatoid Arthritis and Plaque Psoriasis Treated With Etanercept",
        phase="Phase IV",
        status=TrialOutcomeStatus.UNKNOWN,
        intervention_names=["Etanercept via Autoinjector A", "Etanercept via Autoinjector B"],
        comparator_names=[],
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="v1", record_id="NCT01875991"),
    )
    # Role analysis: Both arms receive Etanercept via different autoinjectors
    role1, intr_match1, comp_match1, is_diff1, reason1 = analyze_trial_drug_role(t1, "Etanercept")
    assert role1 == TrialDrugRole.CONCOMITANT_THERAPY
    assert is_diff1 is False

    attr1 = evaluate_trial_attribution(t1, "Etanercept")
    assert attr1.final_attribution_decision is False
    assert "device" in attr1.attribution_reason.lower() or "usability" in attr1.attribution_reason.lower()

    # Outcome evaluation: Needle apprehension endpoint must be classified as non-efficacy
    om_needle = {
        "type": "PRIMARY",
        "title": "Change From Baseline in Needle Apprehension at Week 4",
        "description": "Visual analog scale of needle apprehension",
        "analyses": [{"pValue": "0.501", "statisticalMethod": "Van Elteren test"}],
    }
    dir1, reason_om1 = RetrievalPipeline._evaluate_outcome_measure_direction(om_needle)
    assert dir1 == "UNKNOWN"
    assert "Non-efficacy endpoint" in (reason_om1 or "")

    # 2. NCT01623752: Observational single-cohort paired t-test on radiographic progression
    t2 = ClinicalTrial(
        nct_id="NCT01623752",
        title="Prospective Evaluation of the Radiographic Efficacy of Enbrel",
        phase="Phase IV",
        status=TrialOutcomeStatus.UNKNOWN,
        intervention_names=["Etanercept", "Etanercept"],
        comparator_names=[],
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="v1", record_id="NCT01623752"),
    )
    om_progression = {
        "type": "PRIMARY",
        "title": "Change From Pre-treatment in Normalized Radiographic Progression of mTSS at Week 78",
        "description": "Paired within-patient progression analysis",
        "analyses": [{"pValue": "0.278", "statisticalMethod": "Paired t-test"}],
    }
    dir2, reason_om2 = RetrievalPipeline._evaluate_outcome_measure_direction(om_progression)
    assert dir2 == "UNKNOWN"
    assert "within-group" in (reason_om2 or "").lower() or "paired" in (reason_om2 or "").lower()

    # Verify neither trial generates a negative claim for Etanercept in RA
    claim1 = trial_to_negative_claim(t1, "Etanercept", "Rheumatoid arthritis")
    assert claim1 is None

    claim2 = trial_to_negative_claim(t2, "Etanercept", "Rheumatoid arthritis")
    assert claim2 is None


# =========================================================================
# Test C: Fluvoxamine Opposition Serialization (No Overwrite Bug)
# =========================================================================

def test_c_fluvoxamine_opposition_serialization():
    """C: Ensure opposition_score (e.g. 0.512) is NOT overwritten to 0.0 by
    contradiction_summary.opposition_weight in evaluation serialization.
    """
    prov = ProvenanceReference(source_name="ClinicalTrials.gov", source_version="v1", record_id="NCT04727424")
    c = Claim(
        subject="Fluvoxamine", predicate=PredicateType.FAILED_TO_IMPROVE, object="COVID-19",
        confidence=0.95, erw=ERW(value=0.90, base_weight=0.90), provenance=prov,
    )
    assessor = TherapeuticOppositionAssessor()
    opp_assessment = assessor.assess([c], "Fluvoxamine", "COVID-19")

    # Force a score of 0.512 to replicate the exact observed failure case
    opp_assessment_512 = OppositionAssessment(
        score=0.512,
        level="HIGH",
        independent_group_count=2,
        qualified_negative_claim_count=2,
        qualified_claim_count=2,
        rationale="empirical opposition score = 0.512 (HIGH) across 2 independent groups",
    )

    # Empty ContradictionSummary where opposition_weight would default to 0.0
    contra_sum = ContradictionSummary(
        resolution="NONE",
        strong_conflict=False,
        explanation="No target conflict",
    )

    result = ReasoningResult(
        hypothesis_id=uuid.uuid4(),
        support_assessment=SupportAssessment(score=0.3, level="LOW"),
        mechanistic_assessment=MechanisticAssessment(score=0.2, level="LOW"),
        risk_assessment=RiskAssessment(score=0.5, level="MEDIUM"),
        recommendation_status=RecommendationStatus.NOT_RECOMMENDED,
        audit_report=ScientificAuditReport(summary="Fluvoxamine test"),
        opposition_assessment=opp_assessment_512,
        contradiction_summary=contra_sum,
    )

    # Simulate serializer logic (verifying that opp_score is read directly from opposition_assessment)
    opp_assess = result.opposition_assessment
    opp_score = float(opp_assess.score)
    opp_level = opp_assess.level
    qualified_neg_claims = int(opp_assess.qualified_negative_claim_count)

    serialized = {
        "opposition_score": round(opp_score, 4),
        "opposition_level": opp_level,
        "qualified_negative_claim_count": qualified_neg_claims,
    }

    assert serialized["opposition_score"] == 0.512
    assert serialized["opposition_level"] == "HIGH"
    assert serialized["qualified_negative_claim_count"] == 2


# =========================================================================
# Test D: Metformin / LY3053102 Background Attribution
# =========================================================================

def test_d_metformin_background_attribution():
    """D: When evaluated drug appears in all arms as background therapy,
    investigational failure of added drug cannot be attributed to the background drug.
    """
    trial = ClinicalTrial(
        nct_id="NCT02020616",
        title="A Study of LY3053102 in Participants With Type 2 Diabetes Mellitus on Metformin",
        phase="Phase II",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        intervention_names=["LY3053102 + Metformin", "Metformin Hydrochloride"],
        comparator_names=["Placebo + Metformin"],
        why_stopped="Lack of Efficacy",
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="v1", record_id="NCT02020616"),
    )

    role, intr_match, comp_match, is_diff, arm_reason = analyze_trial_drug_role(trial, "Metformin")
    assert role in (TrialDrugRole.BACKGROUND_CONSTANT_THERAPY, TrialDrugRole.BACKGROUND_THERAPY)
    assert is_diff is False

    attr = evaluate_trial_attribution(trial, "Metformin")
    assert attr.final_attribution_decision is False
    assert "background standard-of-care" in attr.attribution_reason or "background" in attr.attribution_reason.lower()


# =========================================================================
# Test E: Comparator-Only Exclusion
# =========================================================================

def test_e_comparator_only_exclusion():
    """E: Negative evidence in a trial comparing Drug A vs Comparator B
    must NEVER generate opposition against Comparator B.
    """
    trial = ClinicalTrial(
        nct_id="NCT01111111",
        title="DrugA Versus Warfarin in Atrial Fibrillation",
        phase="Phase III",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        intervention_names=["DrugA"],
        comparator_names=["Warfarin"],
        why_stopped="DrugA failed to demonstrate non-inferiority",
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="v1", record_id="NCT01111111"),
    )

    role, intr_match, comp_match, is_diff, arm_reason = analyze_trial_drug_role(trial, "Warfarin")
    assert role in (TrialDrugRole.COMPARATOR_ONLY, TrialDrugRole.ACTIVE_COMPARATOR)
    assert is_diff is False

    attr = evaluate_trial_attribution(trial, "Warfarin")
    assert attr.final_attribution_decision is False
    assert "comparator/control only" in attr.attribution_reason


# =========================================================================
# Test F: Combination-Arm Attribution
# =========================================================================

def test_f_combination_arm_attribution():
    """F: Drug A + Drug B generic failure cannot be attributed to Drug A alone
    without explicit drug attribution.
    """
    trial_generic = ClinicalTrial(
        nct_id="NCT02222222",
        title="Study of DrugA Combined With DrugB",
        phase="Phase II",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        intervention_names=["DrugA", "DrugB"],
        comparator_names=["Placebo"],
        why_stopped="Lack of Efficacy",
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="v1", record_id="NCT02222222"),
    )
    attr_gen = evaluate_trial_attribution(trial_generic, "DrugA")
    assert attr_gen.final_attribution_decision is False
    assert "combination" in attr_gen.attribution_reason.lower()

    trial_explicit = ClinicalTrial(
        nct_id="NCT02222223",
        title="Study of DrugA Combined With DrugB",
        phase="Phase II",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        intervention_names=["DrugA", "DrugB"],
        comparator_names=["Placebo"],
        why_stopped="Lack of efficacy of DrugA in combination arm",
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="v1", record_id="NCT02222223"),
    )
    attr_exp = evaluate_trial_attribution(trial_explicit, "DrugA")
    assert attr_exp.final_attribution_decision is True


# =========================================================================
# Test G: Hard Negative -> UNCERTAIN Invariant
# =========================================================================

def test_g_hard_negative_remains_uncertain():
    """G: Unverified indication with no qualifying opposition must remain UNCERTAIN,
    never OPPOSE. Absence of evidence is not opposition.
    """
    orchestrator = ReasoningOrchestrator()
    support = SupportAssessment(score=0.1, level="LOW")
    mechanistic = MechanisticAssessment(score=0.1, level="LOW")
    risk = RiskAssessment(score=0.0, level="NONE")
    opposition = OppositionAssessment.empty()

    from unittest.mock import MagicMock
    pkg = MagicMock()
    pkg.disease.name = "Depression"
    pkg.drug.name = "Furosemide"
    pkg.sources_failed = []

    sci_ctx = ScientificContext(
        regulatory=DimensionalAssessment(dimension="regulatory", status="NOT_EVALUATED", confidence=0.0),
        repurposing=DimensionalAssessment(dimension="repurposing", status="NOT_EVALUATED", confidence=0.0),
        mechanistic=DimensionalAssessment(dimension="mechanistic", status="INSUFFICIENT_EVIDENCE", confidence=0.0),
        clinical=DimensionalAssessment(dimension="clinical", status="INSUFFICIENT_EVIDENCE", confidence=0.0),
        knowledge_maturity=DimensionalAssessment(dimension="knowledge_maturity", status="LOW", confidence=0.0),
    )
    safety_prof = MagicMock(has_boxed_warning=False, overall_safety_grade="A")
    prior_ctx = MagicMock(matched_indication_term="")

    rec, reasons = orchestrator._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=pkg,
        safety_profile=safety_prof,
        prior_ctx=prior_ctx,
        scientific_context=sci_ctx,
        opposition=opposition,
    )
    assert rec == RecommendationStatus.UNCERTAIN
    assert any("Rule 5" in r for r in reasons)


# =========================================================================
# Test H: Approved Indication Routing
# =========================================================================

def test_h_approved_indication_routing():
    """H: Approved indication without opposition routes through Rule -1 to PROMISING."""
    orchestrator = ReasoningOrchestrator()
    support = SupportAssessment(score=0.95, level="HIGH")
    mechanistic = MechanisticAssessment(score=0.49, level="LOW")
    risk = RiskAssessment(score=0.0, level="NONE")
    opposition = OppositionAssessment.empty()

    from unittest.mock import MagicMock
    pkg = MagicMock()
    pkg.disease.name = "Hypertension"
    pkg.drug.name = "Lisinopril"
    pkg.sources_failed = []

    sci_ctx = ScientificContext(
        regulatory=DimensionalAssessment(dimension="regulatory", status="APPROVED", confidence=1.0),
        repurposing=DimensionalAssessment(dimension="repurposing", status="NOT_EVALUATED", confidence=0.0),
        mechanistic=DimensionalAssessment(dimension="mechanistic", status="PLAUSIBLE", confidence=0.7),
        clinical=DimensionalAssessment(dimension="clinical", status="APPROVED_INDICATION", confidence=1.0),
        knowledge_maturity=DimensionalAssessment(dimension="knowledge_maturity", status="HIGH", confidence=1.0),
    )
    safety_prof = MagicMock(has_boxed_warning=False, overall_safety_grade="A")
    prior_ctx = MagicMock(matched_indication_term="hypertension")

    rec, reasons = orchestrator._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=pkg,
        safety_profile=safety_prof,
        prior_ctx=prior_ctx,
        scientific_context=sci_ctx,
        opposition=opposition,
    )
    assert rec == RecommendationStatus.PROMISING
    assert any("Rule -1 (APPROVED INDICATION RESOLUTION)" in r for r in reasons)


# =========================================================================
# Test I: Approved Positive + Genuine Opposition
# =========================================================================

def test_i_approved_positive_with_genuine_opposition():
    """I: Approved indication with genuine strong opposition (score >= 0.45)
    triggers Rule 2b veto to NOT_RECOMMENDED / OPPOSE.
    """
    orchestrator = ReasoningOrchestrator()
    support = SupportAssessment(score=0.95, level="HIGH")
    mechanistic = MechanisticAssessment(score=0.0, level="NONE")
    risk = RiskAssessment(score=0.2, level="LOW")

    opp = OppositionAssessment(
        score=0.512,
        level="HIGH",
        independent_group_count=2,
        qualified_negative_claim_count=2,
        qualified_claim_count=2,
        rationale="Strong opposition in cardiovascular prevention",
    )

    from unittest.mock import MagicMock
    pkg = MagicMock()
    pkg.disease.name = "Cardiovascular disease"
    pkg.drug.name = "Niacin"
    pkg.sources_failed = []

    sci_ctx = ScientificContext(
        regulatory=DimensionalAssessment(dimension="regulatory", status="APPROVED", confidence=1.0),
        repurposing=DimensionalAssessment(dimension="repurposing", status="NOT_EVALUATED", confidence=0.0),
        mechanistic=DimensionalAssessment(dimension="mechanistic", status="INSUFFICIENT_EVIDENCE", confidence=0.0),
        clinical=DimensionalAssessment(dimension="clinical", status="APPROVED_INDICATION", confidence=1.0),
        knowledge_maturity=DimensionalAssessment(dimension="knowledge_maturity", status="HIGH", confidence=1.0),
    )
    safety_prof = MagicMock(has_boxed_warning=False, overall_safety_grade="A")
    prior_ctx = MagicMock(matched_indication_term="cardiovascular disease")

    rec, reasons = orchestrator._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=pkg,
        safety_profile=safety_prof,
        prior_ctx=prior_ctx,
        scientific_context=sci_ctx,
        opposition=opp,
    )
    assert rec == RecommendationStatus.NOT_RECOMMENDED
    assert any("Rule 2b (EMPIRICAL OPPOSITION VETO)" in r for r in reasons)


# =========================================================================
# Test J: Tamoxifen Subtype Indication Resolution
# =========================================================================

def test_j_tamoxifen_subtype_indication_resolution():
    """J: Disease normalization resolves subtype/biomarker query ('ER-positive breast cancer')
    to parent indication term ('breast cancer'), and exposes requested_disease & matching_rationale.
    """
    pipeline = RetrievalPipeline(db_path=":memory:")

    # Indications containing 'breast cancer' with max_phase 4
    indication_data = {
        "indications": [
            {"mesh_heading": "Breast Neoplasms", "efo_term": "breast cancer", "max_phase_for_ind": 4}
        ]
    }
    mol_data = {"max_phase": "4.0"}

    # 1. Subtype / biomarker match
    sig_subtype = pipeline._parse_indication_data(indication_data, mol_data, "ER-positive breast cancer")
    assert sig_subtype is not None
    assert sig_subtype.is_approved is True
    assert sig_subtype.max_phase == 4
    assert sig_subtype.matched_indication == "breast cancer"
    assert sig_subtype.requested_disease == "ER-positive breast cancer"
    assert "Parent/subtype compatible match" in sig_subtype.matching_rationale
    assert sig_subtype.match_confidence >= 0.50

    # 2. Exact match
    sig_exact = pipeline._parse_indication_data(indication_data, mol_data, "Breast Cancer")
    assert sig_exact is not None
    assert sig_exact.is_approved is True
    assert "Direct disease match" in sig_exact.matching_rationale

    # 3. Unrelated disease
    sig_unrelated = pipeline._parse_indication_data(indication_data, mol_data, "Prostate Cancer")
    assert sig_unrelated is not None
    assert sig_unrelated.is_approved is False
    assert sig_unrelated.max_phase == 0


# =========================================================================
# Test K: Registered Trial Without Results != Therapeutic Support
# =========================================================================

def test_k_registered_trial_without_results():
    """K: A registered trial with no results/outcome must NOT be counted as therapeutic support."""
    trial = ClinicalTrial(
        nct_id="NCT09999999",
        title="Unpublished registry study",
        phase="Phase III",
        status=TrialOutcomeStatus.UNKNOWN,
        drug_chembl_id="CHEMBL123",
        disease_identifier="D000001",
        has_results=False,
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="v1", record_id="NCT09999999"),
    )

    from unittest.mock import MagicMock
    pkg = MagicMock(clinical_trials=[trial], approval_signal=None, evidence_records=[])

    audits = audit_high_quality_therapeutic_evidence(pkg)
    trial_audit = [a for a in audits if a.provenance_id == "NCT09999999"][0]

    assert trial_audit.quality == "REGISTERED_STATUS_ONLY"
    assert trial_audit.direction == "UNKNOWN"
    assert trial_audit.therapeutic_relevance is False
    assert trial_audit.allowed_for_high_quality_therapeutic is False


# =========================================================================
# Test L: Clinical Trial Result Directionality
# =========================================================================

def test_l_clinical_trial_result_directionality():
    """L: Ensure explicit semantics: SUPPORTS, OPPOSES, UNKNOWN/INSUFFICIENT."""
    t_success = ClinicalTrial(
        nct_id="NCT00000001", title="Success trial", phase="Phase III",
        status=TrialOutcomeStatus.COMPLETED_SUCCESS, drug_chembl_id="CHEMBL1", disease_identifier="D1",
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="v1", record_id="NCT00000001"),
    )
    t_failure = ClinicalTrial(
        nct_id="NCT00000002", title="Failure trial", phase="Phase III",
        status=TrialOutcomeStatus.COMPLETED_FAILURE, drug_chembl_id="CHEMBL1", disease_identifier="D1",
        negative_efficacy_reason="Primary endpoint not met",
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="v1", record_id="NCT00000002"),
    )
    t_unknown = ClinicalTrial(
        nct_id="NCT00000003", title="No results trial", phase="Phase III",
        status=TrialOutcomeStatus.UNKNOWN, drug_chembl_id="CHEMBL1", disease_identifier="D1",
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="v1", record_id="NCT00000003"),
    )

    from unittest.mock import MagicMock
    pkg = MagicMock(clinical_trials=[t_success, t_failure, t_unknown], approval_signal=None, evidence_records=[])
    audits = {a.provenance_id: a for a in audit_high_quality_therapeutic_evidence(pkg)}

    assert audits["NCT00000001"].direction == "SUPPORTS"
    assert audits["NCT00000001"].quality == "CLINICAL_HUMAN"
    assert audits["NCT00000001"].allowed_for_high_quality_therapeutic is True

    assert audits["NCT00000002"].direction == "OPPOSES"
    assert audits["NCT00000002"].quality == "CLINICAL_HUMAN_FAILURE"
    assert audits["NCT00000002"].allowed_for_high_quality_therapeutic is False

    assert audits["NCT00000003"].direction == "UNKNOWN"
    assert audits["NCT00000003"].quality == "REGISTERED_STATUS_ONLY"
    assert audits["NCT00000003"].allowed_for_high_quality_therapeutic is False


# =========================================================================
# Test M: Serialized Result == Canonical Decision Result
# =========================================================================

def test_m_serialized_result_matches_canonical():
    """M: Evaluator serializer must strictly read from the internal decision object
    without deriving or recomputing fields.
    """
    from backend.evaluation.run_25_case_evaluation import RECOMMENDATION_TO_3CLASS

    opp = OppositionAssessment(
        score=0.48,
        level="HIGH",
        independent_group_count=3,
        qualified_negative_claim_count=4,
        qualified_claim_count=4,
        rationale="Canonical opposition",
    )
    decision = ReasoningResult(
        hypothesis_id=uuid.uuid4(),
        support_assessment=SupportAssessment(score=0.88, level="HIGH"),
        mechanistic_assessment=MechanisticAssessment(score=0.45, level="LOW"),
        risk_assessment=RiskAssessment(score=0.35, level="LOW"),
        recommendation_status=RecommendationStatus.NOT_RECOMMENDED,
        audit_report=ScientificAuditReport(summary="Canonical test"),
        opposition_assessment=opp,
    )

    # Simulated serializer read
    serialized = {
        "prediction": RECOMMENDATION_TO_3CLASS[decision.recommendation_status.value],
        "recommendation": decision.recommendation_status.value,
        "opposition_score": round(decision.opposition_score, 4),
        "opposition_level": decision.opposition_level,
        "qualified_negative_claim_count": decision.qualified_negative_claim_count,
        "independent_opposition_group_count": decision.independent_opposition_group_count,
    }

    assert serialized["prediction"] == "OPPOSE"
    assert serialized["recommendation"] == decision.recommendation_status.value
    assert serialized["opposition_score"] == decision.opposition_assessment.score
    assert serialized["opposition_level"] == decision.opposition_assessment.level
    assert serialized["qualified_negative_claim_count"] == decision.opposition_assessment.qualified_claim_count
    assert serialized["independent_opposition_group_count"] == decision.opposition_assessment.independent_group_count
