"""Unit tests for CYNTHERA P0b-2: Semantic Opposition Qualification Layer.

Validates semantic qualification and conflict resolution semantics:
1. TC-001 (Lisinopril -> Hypertension): NCT00582114 hemodialysis/LVH subpopulation
   is disqualified from direct empirical opposition.
2. TC-003 (Budesonide -> Asthma): NCT00471809 steroid reduction/step-down
   is classified as BACKGROUND_THERAPY_FAILURE and disqualified.
3. TC-062 (Ranibizumab -> AMD): NCT02611778 biosimilar equivalence failure
   is classified as BIOSIMILAR_EQUIVALENCE_FAILURE and disqualified.
4. Genuine Direct Negatives:
   - Azithromycin -> COVID-19 (NCT04332107 futility) -> DIRECT_THERAPEUTIC_FAILURE -> Rule 2b fires.
   - Niacin -> Cardiovascular disease (NCT00120289 AIM-HIGH) -> DIRECT_THERAPEUTIC_FAILURE -> Rule 2b fires.
   - Dexamethasone -> TBI (NCT02362321 CRASH/harm) -> DIRECT_THERAPEUTIC_FAILURE -> Rule 2b fires.
5. Replicated Negatives:
   - Nivolumab -> GBM (n=2, Opp=0.6885) -> preserved.
   - Hydroxychloroquine -> COVID-19 (n=4, Opp=0.7493) -> preserved.
6. Conflict Resolution Semantics:
   - Case A: Approved + disqualified opposition -> PROMISING (Rule -1).
   - Case B: Approved + isolated single direct negative (n=1) -> UNCERTAIN (Rule 1b).
   - Case C: Approved + replicated direct negative (n>=2) -> NOT_RECOMMENDED (Rule 2b).
   - Case D: Approved + regulatory boxed warning / high RS -> NOT_RECOMMENDED (Rule 0 / Rule 3).
   - Case E: Unapproved + valid direct negative -> NOT_RECOMMENDED (Rule 2b).
7. Test Invariants (Section 14).
"""
from __future__ import annotations

import uuid
import pytest

from backend.core.domain.claim import Claim
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.disease import Disease
from backend.core.domain.drug import Drug
from backend.core.domain.reasoning_result import (
    OppositionAssessment,
    RiskAssessment,
    SupportAssessment,
    MechanisticAssessment,
)
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.recommendation import RecommendationStatus
from backend.core.enums.trial_attribution import TrialDrugRole, AttributionTextEvidence
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.identifier import CanonicalIdentifier, ResolvedIdentifierSet
from backend.core.value_objects.provenance import ProvenanceReference
from backend.reasoning.agents.clinical_safety_agent import SafetyProfile
from backend.reasoning.agents.prior_knowledge_agent import PriorKnowledgeContext
from backend.reasoning.context.scientific_context_builder import DimensionalAssessment, ScientificContext
from backend.reasoning.opposition.opposition_qualification import (
    OppositionQualificationResult,
    qualify_opposition_claim,
)
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    trial_to_negative_claim,
    evaluate_trial_attribution,
)
from backend.reasoning.orchestrator.decision_rules import (
    OppositionConflictDecision,
    OppositionConflictType,
    apply_decision_rules,
    classify_opposition_conflict,
)


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


def _make_package(drug_name: str, disease_name: str) -> RetrievalPackage:
    return RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=_make_drug(drug_name),
        disease=_make_disease(disease_name),
        targets=[],
        proteins=[],
        pathways=[],
        evidence_records=[],
        clinical_trials=[],
        retrieval_confidence="HIGH",
    )


def _make_sci_context(status: str = "APPROVED", confidence: float = 1.0) -> ScientificContext:
    return ScientificContext(
        DimensionalAssessment("regulatory", status, confidence, []),
        DimensionalAssessment("repurposing", "NOVEL", 0.0, []),
        DimensionalAssessment("mechanistic", "NONE", 0.0, []),
        DimensionalAssessment("clinical", "NONE", 0.0, []),
        DimensionalAssessment("maturity", "NONE", 0.0, []),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. TC-001: Lisinopril -> Hypertension (NCT00582114 Subpopulation Audit)
# ─────────────────────────────────────────────────────────────────────────────

def test_tc001_lisinopril_hemodialysis_subpopulation_disqualified():
    """TC-001: NCT00582114 in hemodialysis patients evaluating LVH regression is disqualified from direct opposition."""
    trial = ClinicalTrial(
        nct_id="NCT00582114",
        title="Hypertension in Hemodialysis Patients (Aim 3)",
        phase="Phase IV",
        status=TrialOutcomeStatus.TERMINATED_SAFETY,
        why_stopped="Stopped by data safety monitoring board",
        condition_names=["Hemodialysis", "Hypertension", "Left Ventricular Hypertrophy"],
        intervention_names=["Lisinopril"],
        comparator_names=["Atenolol"],
        outcome_measures=[
            {
                "title": "The Primary End Point is the Regression of Left Ventricular Hypertrophy (LVH)",
                "type": "PRIMARY",
                "direction": "UNKNOWN",
                "reason_code": "INSUFFICIENT_STATISTICAL_CONTEXT",
            },
            {
                "title": "Serious Adverse Events and Cardiovascular Events",
                "type": "OTHER_PRE_SPECIFIED",
                "direction": "SAFETY_HARM",
                "reason_code": "SAFETY_ENDPOINT",
            },
        ],
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="2024", record_id="NCT00582114"),
    )

    claim = trial_to_negative_claim(trial, "Lisinopril", "Hypertension")
    assert claim is not None

    qual = qualify_opposition_claim(claim, "Lisinopril", "Hypertension", trial)
    assert qual.qualified is False
    assert qual.reason_code in ("INDIRECT_SUBPOPULATION_RESULT", "SAFETY_SIGNAL")
    assert qual.directness == "SUBPOPULATION"
    assert qual.replication_eligible is False

    # Assessor should reject this claim and return score 0.0
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "Lisinopril", "Hypertension")
    assert assessment.score == 0.0
    assert assessment.level == "NONE"
    assert assessment.qualified_negative_claim_count == 0
    assert assessment.excluded_negative_claim_count == 1

    # Decision rules: Approval anchor survives
    decision = apply_decision_rules(
        is_approved=True,
        matched_chembl_term="hypertension",
        support_score=0.991,
        mechanistic_score=0.49,
        risk_score=0.0,
        opp_assessment=assessment,
    )
    assert decision.status == RecommendationStatus.PROMISING
    assert any("Rule -1 (APPROVED INDICATION RESOLUTION)" in r for r in decision.reasons)


# ─────────────────────────────────────────────────────────────────────────────
# 2. TC-003: Budesonide -> Asthma (NCT00471809 Step-Down Audit)
# ─────────────────────────────────────────────────────────────────────────────

def test_tc003_budesonide_step_down_strategy_disqualified():
    """TC-003: NCT00471809 (MARS trial for reduction of inhaled corticosteroids) is disqualified as background therapy failure."""
    trial = ClinicalTrial(
        nct_id="NCT00471809",
        title="Childhood Asthma Research and Education (CARE) Network Trial - Montelukast or Azithromycin for Reduction of Inhaled Corticosteroids in Childhood Asthma (MARS)",
        phase="Phase IV",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        why_stopped="The CARE Network DSMB recommended to the NHLBI that the MARS trial be terminated, based on a futility analysis with 55 randomized children.",
        condition_names=["Asthma"],
        intervention_names=[],
        comparator_names=[],
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="2024", record_id="NCT00471809"),
    )

    claim = trial_to_negative_claim(trial, "Budesonide", "Asthma")
    assert claim is not None

    qual = qualify_opposition_claim(claim, "Budesonide", "Asthma", trial)
    assert qual.qualified is False
    assert qual.reason_code == "BACKGROUND_THERAPY_FAILURE"
    assert qual.directness == "INDIRECT"
    assert qual.replication_eligible is False

    # Assessor returns score 0.0
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "Budesonide", "Asthma")
    assert assessment.score == 0.0
    assert assessment.level == "NONE"

    # Decision rules: Approval anchor survives
    decision = apply_decision_rules(
        is_approved=True,
        matched_chembl_term="asthma",
        support_score=0.988,
        mechanistic_score=0.50,
        risk_score=0.0,
        opp_assessment=assessment,
    )
    assert decision.status == RecommendationStatus.PROMISING


# ─────────────────────────────────────────────────────────────────────────────
# 3. TC-062: Ranibizumab -> AMD (NCT02611778 Biosimilar Equivalence Audit)
# ─────────────────────────────────────────────────────────────────────────────

def test_tc062_ranibizumab_biosimilar_equivalence_failure_disqualified():
    """TC-062: NCT02611778 biosimilar FYB201 equivalence failure is disqualified from opposing Ranibizumab (Lucentis)."""
    trial = ClinicalTrial(
        nct_id="NCT02611778",
        title="Efficacy and Safety of the Biosimilar Ranibizumab FYB201 in Comparison to Lucentis in Patients With Neovascular Age-related Macular Degeneration",
        phase="Phase III",
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        condition_names=["Age-related Macular Degeneration (AMD)"],
        intervention_names=["ranibizumab"],
        comparator_names=["ranibizumab"],
        outcome_measures=[
            {
                "title": "Change From Baseline in Best Corrected Visual Acuity (BCVA) [Letters] After 8 Weeks",
                "type": "PRIMARY",
                "direction": "NEGATIVE",
                "reason_code": "EQUIVALENCE_FAILURE",
            }
        ],
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="2024", record_id="NCT02611778"),
    )

    claim = trial_to_negative_claim(trial, "Ranibizumab", "Age-related macular degeneration")
    assert claim is not None

    qual = qualify_opposition_claim(claim, "Ranibizumab", "Age-related macular degeneration", trial)
    assert qual.qualified is False
    assert qual.reason_code == "BIOSIMILAR_EQUIVALENCE_FAILURE"
    assert qual.comparator_semantics == "REFERENCE_PRODUCT_COMPARATOR"
    assert qual.replication_eligible is False

    # Assessor returns score 0.0
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "Ranibizumab", "Age-related macular degeneration")
    assert assessment.score == 0.0
    assert assessment.level == "NONE"

    # Decision rules: Approval anchor survives
    decision = apply_decision_rules(
        is_approved=True,
        matched_chembl_term="age-related macular degeneration",
        support_score=0.988,
        mechanistic_score=0.50,
        risk_score=0.0,
        opp_assessment=assessment,
    )
    assert decision.status == RecommendationStatus.PROMISING


# ─────────────────────────────────────────────────────────────────────────────
# 4. Genuine Direct Negatives Must Remain Qualified
# ─────────────────────────────────────────────────────────────────────────────

def test_genuine_negative_azithromycin_covid_qualified():
    """Azithromycin -> COVID-19 (NCT04332107 futility) qualifies as direct opposition and triggers Rule 2b."""
    trial = ClinicalTrial(
        nct_id="NCT04332107",
        title="Azithromycin for COVID-19 Treatment in Outpatients Nationwide",
        phase="Phase III",
        design_allocation="RANDOMIZED",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        why_stopped="Futility",
        condition_names=["COVID-19"],
        intervention_names=["Azithromycin"],
        comparator_names=["Placebo"],
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="2024", record_id="NCT04332107"),
    )
    claim = trial_to_negative_claim(trial, "Azithromycin", "COVID-19")
    assert claim is not None

    qual = qualify_opposition_claim(claim, "Azithromycin", "COVID-19", trial)
    assert qual.qualified is True
    assert qual.reason_code == "DIRECT_THERAPEUTIC_FAILURE"
    assert qual.directness == "DIRECT"
    assert qual.replication_eligible is True

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "Azithromycin", "COVID-19")
    assert assessment.score == 0.5670
    assert assessment.level == "HIGH"

    # Not approved -> Rule 2b veto fires
    decision = apply_decision_rules(
        is_approved=False,
        support_score=0.988,
        mechanistic_score=0.0,
        risk_score=0.45,
        opp_assessment=assessment,
    )
    assert decision.status == RecommendationStatus.NOT_RECOMMENDED
    assert any("Rule 2b (EMPIRICAL OPPOSITION VETO)" in r for r in decision.reasons)


def test_genuine_negative_niacin_cvd_qualified():
    """Niacin -> Cardiovascular disease (NCT00120289 AIM-HIGH) qualifies as direct opposition."""
    trial = ClinicalTrial(
        nct_id="NCT00120289",
        title="Niacin Plus Statin to Prevent Vascular Events",
        phase="Phase III",
        design_allocation="RANDOMIZED",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        why_stopped="AIM-HIGH was stopped on the recommendation of the DSMB because of lack of efficacy of niacin in preventing primary outcome events.",
        condition_names=["Cardiovascular disease", "Atherosclerosis"],
        intervention_names=["Extended-Release Niacin + Simvastatin"],
        comparator_names=["Simvastatin + Placebo"],
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="2024", record_id="NCT00120289"),
    )
    claim = trial_to_negative_claim(trial, "Niacin", "Cardiovascular disease")
    assert claim is not None

    qual = qualify_opposition_claim(claim, "Niacin", "Cardiovascular disease", trial)
    assert qual.qualified is True
    assert qual.reason_code == "DIRECT_THERAPEUTIC_FAILURE"

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "Niacin", "Cardiovascular disease")
    assert assessment.score == 0.5670
    assert assessment.level == "HIGH"


def test_genuine_negative_dexamethasone_tbi_qualified():
    """Dexamethasone -> Traumatic brain injury (NCT02362321 CRASH/CSDH) qualifies as direct opposition."""
    trial = ClinicalTrial(
        nct_id="NCT02362321",
        title="Role of Dexamethasone in the Conservative Treatment of Chronic Subdural Hematoma",
        phase="Phase III",
        design_allocation="RANDOMIZED",
        status=TrialOutcomeStatus.TERMINATED_SAFETY,
        why_stopped="Due to serious adverse events",
        condition_names=["Chronic Subdural Hematoma", "Traumatic Brain Injury"],
        intervention_names=["Dexamethasone"],
        comparator_names=["Placebo"],
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="2024", record_id="NCT02362321"),
    )
    claim = trial_to_negative_claim(trial, "Dexamethasone", "Traumatic brain injury")
    assert claim is not None

    qual = qualify_opposition_claim(claim, "Dexamethasone", "Traumatic brain injury", trial)
    assert qual.qualified is True
    assert qual.reason_code == "DIRECT_THERAPEUTIC_HARM"
    assert qual.is_direct_harm is True

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "Dexamethasone", "Traumatic brain injury")
    assert assessment.score == 0.5670
    assert assessment.level == "HIGH"
    assert assessment.has_direct_harm is True


# ─────────────────────────────────────────────────────────────────────────────
# 5. Conflict Resolution Semantics (Cases A, B, C, D, E)
# ─────────────────────────────────────────────────────────────────────────────

def test_case_b_approved_with_isolated_direct_opposition_yields_uncertain():
    """Case B: Approved indication + isolated single negative trial (n=1) routes to UNCERTAIN (Rule 1b conflict)."""
    opp = OppositionAssessment(
        score=0.5670,
        level="HIGH",
        independent_group_count=1,
        qualified_negative_claim_count=1,
        rationale="Single isolated negative study",
    )
    decision = apply_decision_rules(
        is_approved=True,
        matched_chembl_term="test indication",
        support_score=0.50,
        mechanistic_score=0.50,
        risk_score=0.20,
        opp_assessment=opp,
    )
    assert decision.status == RecommendationStatus.UNCERTAIN
    assert any("Rule 1b (APPROVED INDICATION vs ISOLATED EMPIRICAL OPPOSITION CONFLICT)" in r for r in decision.reasons)


def test_case_c_approved_with_replicated_direct_opposition_yields_not_recommended():
    """Case C: Approved indication + replicated direct negative trials (n>=2) overrides approval (Rule 2b veto)."""
    opp = OppositionAssessment(
        score=0.6885,
        level="HIGH",
        independent_group_count=2,
        qualified_negative_claim_count=2,
        rationale="Replicated negative trials across independent centers",
    )
    decision = apply_decision_rules(
        is_approved=True,
        matched_chembl_term="test indication",
        support_score=0.50,
        mechanistic_score=0.50,
        risk_score=0.20,
        opp_assessment=opp,
    )
    assert decision.status == RecommendationStatus.NOT_RECOMMENDED
    assert any("Rule 2b (EMPIRICAL OPPOSITION VETO)" in r for r in decision.reasons)


def test_case_d_approved_with_boxed_warning_and_high_risk_yields_safety_veto():
    """Case D: Regulatory boxed warning + high RS overrides approved indication via Rule 0 regardless of opposition."""
    opp = OppositionAssessment.empty()
    decision = apply_decision_rules(
        is_approved=True,
        has_boxed_warning=True,
        risk_score=0.65,
        opp_assessment=opp,
    )
    assert decision.status == RecommendationStatus.NOT_RECOMMENDED
    assert any("Rule 0 override" in r for r in decision.reasons)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Test Invariants (Section 14)
# ─────────────────────────────────────────────────────────────────────────────

def test_invariant_same_nct_cannot_count_as_multiple_groups():
    """Invariant 1: Multiple claims from same NCT must cluster into exactly one group."""
    prov = ProvenanceReference(source_name="ClinicalTrials.gov", source_version="2024", record_id="NCT00999999")
    c1 = Claim(subject="DrugX", predicate=PredicateType.FAILED_TO_IMPROVE, object="DiseaseY", confidence=0.9, erw=ERW(value=0.9, base_weight=0.9), evidence_type="RCT", provenance=prov, is_validated=True)
    c2 = Claim(subject="DrugX", predicate=PredicateType.FAILED_TO_IMPROVE, object="DiseaseY", confidence=0.85, erw=ERW(value=0.55, base_weight=0.55), evidence_type="RCT", provenance=prov, is_validated=True)

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([c1, c2], "DrugX", "DiseaseY")
    assert assessment.independent_group_count == 1
    assert assessment.qualified_negative_claim_count == 2
    assert assessment.score == 0.5670  # 0.81 * (1.0 - 0.30/1)


def test_invariant_non_significant_does_not_generate_negative_claim():
    """Invariant 4: Non-significant trials (e.g. Fluvoxamine NCT05890586) must not generate negative opposition claims."""
    trial = ClinicalTrial(
        nct_id="NCT05890586",
        title="ACTIV-6: COVID-19 Study of Repurposed Medications",
        phase="Phase III",
        status=TrialOutcomeStatus.COMPLETED_SUCCESS,  # or non-negative
        condition_names=["COVID-19"],
        intervention_names=["Fluvoxamine"],
        comparator_names=["Placebo"],
        outcome_measures=[
            {
                "title": "Time to Sustained Recovery",
                "type": "PRIMARY",
                "direction": "NON_SIGNIFICANT",
                "reason_code": "NON_SIGNIFICANT_PRIMARY_ENDPOINT",
            }
        ],
        provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="2024", record_id="NCT05890586"),
    )
    claim = trial_to_negative_claim(trial, "Fluvoxamine", "COVID-19")
    assert claim is None


# ─────────────────────────────────────────────────────────────────────────────
# 7. Isolated Conflict Classifier Tests (Section 19)
# ─────────────────────────────────────────────────────────────────────────────

def test_classify_opposition_conflict_no_conflict():
    """No opposition evidence yields NO_CONFLICT."""
    res = classify_opposition_conflict(
        is_approved=True,
        opposition_score=0.0,
        independent_group_count=0,
        qualified_opposition=False,
    )
    assert res.conflict_type == OppositionConflictType.NO_CONFLICT
    assert res.should_veto is False
    assert res.should_route_uncertain is False
    assert res.reason_code == "NO_OPPOSITION"


def test_classify_opposition_conflict_invalid_opposition():
    """Disqualified / invalid opposition yields INVALID_OPPOSITION."""
    res = classify_opposition_conflict(
        is_approved=True,
        opposition_score=0.5670,
        independent_group_count=1,
        qualified_opposition=False,
    )
    assert res.conflict_type == OppositionConflictType.INVALID_OPPOSITION
    assert res.should_veto is False
    assert res.should_route_uncertain is False
    assert res.reason_code == "INVALID_OPPOSITION_FILTERED"


def test_classify_opposition_conflict_isolated_direct_approved():
    """Approved indication + isolated negative trial (n=1) yields ISOLATED_DIRECT_CONFLICT (routes UNCERTAIN)."""
    res = classify_opposition_conflict(
        is_approved=True,
        opposition_score=0.5670,
        independent_group_count=1,
        qualified_opposition=True,
    )
    assert res.conflict_type == OppositionConflictType.ISOLATED_DIRECT_CONFLICT
    assert res.should_veto is False
    assert res.should_route_uncertain is True
    assert res.reason_code == "APPROVED_ISOLATED_OPPOSITION_CONFLICT"


def test_classify_opposition_conflict_replicated_direct_approved():
    """Approved indication + replicated negative trials (n=2) yields REPLICATED_DIRECT_CONFLICT (vetoes)."""
    res = classify_opposition_conflict(
        is_approved=True,
        opposition_score=0.6885,
        independent_group_count=2,
        qualified_opposition=True,
    )
    assert res.conflict_type == OppositionConflictType.REPLICATED_DIRECT_CONFLICT
    assert res.should_veto is True
    assert res.should_route_uncertain is False
    assert res.reason_code == "APPROVED_REPLICATED_OPPOSITION_VETO"


def test_classify_opposition_conflict_unapproved_candidate():
    """Unapproved indication + qualified negative trial yields veto."""
    res = classify_opposition_conflict(
        is_approved=False,
        opposition_score=0.5670,
        independent_group_count=1,
        qualified_opposition=True,
    )
    assert res.conflict_type == OppositionConflictType.ISOLATED_DIRECT_CONFLICT
    assert res.should_veto is True
    assert res.should_route_uncertain is False
    assert res.reason_code == "UNAPPROVED_EMPIRICAL_VETO"


def test_classify_opposition_conflict_regulatory_safety_override():
    """Regulatory boxed warning / safety override yields REGULATORY_SAFETY_CONFLICT."""
    res = classify_opposition_conflict(
        is_approved=True,
        opposition_score=0.5670,
        independent_group_count=1,
        qualified_opposition=True,
        regulatory_safety_veto=True,
    )
    assert res.conflict_type == OppositionConflictType.REGULATORY_SAFETY_CONFLICT
    assert res.should_veto is True
    assert res.should_route_uncertain is False
    assert res.reason_code == "REGULATORY_SAFETY_OVERRIDE"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Isolated Semantic Qualification of All Nine Categories (Section 20)
# ─────────────────────────────────────────────────────────────────────────────

def test_semantic_qualification_all_nine_categories():
    """Explicit tests for all 9 semantic qualification categories in isolation."""
    prov = ProvenanceReference(source_name="ClinicalTrials.gov", source_version="2024", record_id="NCT00000001")
    
    # 1. INDIRECT_SUBPOPULATION_RESULT
    t1 = ClinicalTrial(
        nct_id="NCT00582114",
        title="Lisinopril in Hemodialysis Patients with Left Ventricular Hypertrophy",
        phase="Phase III",
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        condition_names=["End-Stage Renal Disease", "Hemodialysis", "Hypertension"],
        intervention_names=["Lisinopril"],
        comparator_names=["Atenolol"],
        provenance=prov,
    )
    c1 = trial_to_negative_claim(t1, "Lisinopril", "Hypertension")
    assert c1 is not None
    q1 = qualify_opposition_claim(c1, "Lisinopril", "Hypertension", t1)
    assert q1.qualified is False
    assert q1.reason_code == "INDIRECT_SUBPOPULATION_RESULT"

    # 2. BACKGROUND_THERAPY_FAILURE
    t2 = ClinicalTrial(
        nct_id="NCT00471809",
        title="Childhood Asthma Research and Education (CARE) Network Trial - Montelukast or Azithromycin for Reduction of Inhaled Corticosteroids in Childhood Asthma (MARS)",
        phase="Phase IV",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        why_stopped="The CARE Network DSMB recommended to the NHLBI that the MARS trial be terminated, based on a futility analysis with 55 randomized children.",
        condition_names=["Asthma"],
        intervention_names=[],
        comparator_names=[],
        provenance=prov,
    )
    c2 = trial_to_negative_claim(t2, "Budesonide", "Asthma")
    assert c2 is not None
    q2 = qualify_opposition_claim(c2, "Budesonide", "Asthma", t2)
    assert q2.qualified is False
    assert q2.reason_code == "BACKGROUND_THERAPY_FAILURE"

    # 3. BIOSIMILAR_EQUIVALENCE_FAILURE
    t3 = ClinicalTrial(
        nct_id="NCT02611778",
        title="Efficacy and Safety of the Biosimilar Ranibizumab FYB201 in Comparison to Lucentis in Patients With Neovascular Age-related Macular Degeneration",
        phase="Phase III",
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        condition_names=["Age-related macular degeneration"],
        intervention_names=["ranibizumab"],
        comparator_names=["ranibizumab"],
        outcome_measures=[
            {
                "title": "Change From Baseline in Best Corrected Visual Acuity (BCVA) [Letters] After 8 Weeks",
                "type": "PRIMARY",
                "direction": "NEGATIVE",
                "reason_code": "EQUIVALENCE_FAILURE",
            }
        ],
        provenance=prov,
    )
    c3 = trial_to_negative_claim(t3, "Ranibizumab", "Age-related macular degeneration")
    assert c3 is not None
    q3 = qualify_opposition_claim(c3, "Ranibizumab", "Age-related macular degeneration", t3)
    assert q3.qualified is False
    assert q3.reason_code == "BIOSIMILAR_EQUIVALENCE_FAILURE"

    # 4. ACTIVE_COMPARATOR_DIRECTION_ERROR
    c4 = Claim(
        subject="DrugA",
        predicate=PredicateType.FAILED_TO_IMPROVE,
        object="DiseaseX",
        confidence=0.8,
        erw=ERW(value=0.8, base_weight=0.8),
        evidence_type="RCT",
        provenance=prov,
        is_validated=True,
        attribution_trace={"drug_role": "COMPARATOR_ONLY", "is_differentiating_intervention": False, "final_attribution_decision": False},
    )
    q4 = qualify_opposition_claim(c4, "DrugA", "DiseaseX")
    assert q4.qualified is False
    assert q4.reason_code == "ACTIVE_COMPARATOR_DIRECTION_ERROR"

    # 5. DIRECT_THERAPEUTIC_FAILURE
    t5 = ClinicalTrial(
        nct_id="NCT00120289",
        title="AIM-HIGH: Niacin in Patients with Atherosclerotic Cardiovascular Disease",
        phase="Phase III",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        why_stopped="Futility and lack of efficacy on primary cardiovascular endpoint",
        condition_names=["Cardiovascular Disease", "Atherosclerosis"],
        intervention_names=["Niacin"],
        comparator_names=["Placebo"],
        provenance=prov,
    )
    c5 = trial_to_negative_claim(t5, "Niacin", "Cardiovascular disease")
    q5 = qualify_opposition_claim(c5, "Niacin", "Cardiovascular disease", t5)
    assert q5.qualified is True
    assert q5.reason_code == "DIRECT_THERAPEUTIC_FAILURE"
    assert q5.is_direct_harm is False

    # 6. DIRECT_THERAPEUTIC_HARM
    t6 = ClinicalTrial(
        nct_id="NCT02362321",
        title="Role of Dexamethasone in Chronic Subdural Hematoma",
        phase="Phase III",
        status=TrialOutcomeStatus.TERMINATED_SAFETY,
        why_stopped="Due to serious adverse events",
        condition_names=["Chronic Subdural Hematoma", "Traumatic Brain Injury"],
        intervention_names=["Dexamethasone"],
        comparator_names=["Placebo"],
        provenance=prov,
    )
    c6 = trial_to_negative_claim(t6, "Dexamethasone", "Traumatic brain injury")
    q6 = qualify_opposition_claim(c6, "Dexamethasone", "Traumatic brain injury", t6)
    assert q6.qualified is True
    assert q6.reason_code == "DIRECT_THERAPEUTIC_HARM"
    assert q6.is_direct_harm is True

    # 7. SAFETY_SIGNAL (administrative DSMB stop without direct harm)
    t7 = ClinicalTrial(
        nct_id="NCT09999998",
        title="Study of Investigational Drug in General Population",
        phase="Phase II",
        status=TrialOutcomeStatus.TERMINATED_SAFETY,
        why_stopped="DSMB recommended stopping accrual too slow and administrative review",
        condition_names=["Hypertension"],
        intervention_names=["DrugZ"],
        comparator_names=["Placebo"],
        provenance=prov,
    )
    c7 = trial_to_negative_claim(t7, "DrugZ", "Hypertension")
    q7 = qualify_opposition_claim(c7, "DrugZ", "Hypertension", t7)
    assert q7.qualified is False
    assert q7.reason_code == "SAFETY_SIGNAL"

    # 8. AMBIGUOUS_INTERVENTION
    c8 = Claim(
        subject="DrugAmb",
        predicate=PredicateType.FAILED_TO_IMPROVE,
        object="DiseaseY",
        confidence=0.7,
        erw=ERW(value=0.5, base_weight=0.5),
        evidence_type="RCT",
        provenance=prov,
        is_validated=True,
        attribution_trace={"drug_role": "UNCERTAIN", "is_differentiating_intervention": True, "final_attribution_decision": False},
    )
    q8 = qualify_opposition_claim(c8, "DrugAmb", "DiseaseY")
    assert q8.qualified is False
    assert q8.reason_code == "AMBIGUOUS_INTERVENTION"

    # 9. UNRELATED_DISEASE (sibling excluded)
    c9 = Claim(
        subject="Aspirin",
        predicate=PredicateType.FAILED_TO_IMPROVE,
        object="Hemorrhagic stroke",
        confidence=0.9,
        erw=ERW(value=0.9, base_weight=0.9),
        evidence_type="RCT",
        provenance=prov,
        is_validated=True,
    )
    q9 = qualify_opposition_claim(c9, "Aspirin", "Ischemic stroke")
    assert q9.qualified is False
    assert q9.reason_code == "UNRELATED_DISEASE"


# ─────────────────────────────────────────────────────────────────────────────
# 9. TC-062 Evaluator Parity Test (Section 9 & 17)
# ─────────────────────────────────────────────────────────────────────────────

def test_tc062_authoritative_evaluator_parity():
    """Explicit test that TC-062 (Ranibizumab -> AMD) returns SUPPORT via Rule -1 without evaluator divergence."""
    # Disqualified biosimilar trial NCT02611778
    prov = ProvenanceReference(source_name="ClinicalTrials.gov", source_version="2024", record_id="NCT02611778")
    t = ClinicalTrial(
        nct_id="NCT02611778",
        title="Efficacy and Safety of the Biosimilar Ranibizumab FYB201 in Comparison to Lucentis in Patients With Neovascular Age-related Macular Degeneration",
        phase="Phase III",
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        condition_names=["Age-related Macular Degeneration (AMD)"],
        intervention_names=["ranibizumab"],
        comparator_names=["ranibizumab"],
        outcome_measures=[
            {
                "title": "Change From Baseline in Best Corrected Visual Acuity (BCVA) [Letters] After 8 Weeks",
                "type": "PRIMARY",
                "direction": "NEGATIVE",
                "reason_code": "EQUIVALENCE_FAILURE",
            }
        ],
        provenance=prov,
    )
    claim = trial_to_negative_claim(t, "Ranibizumab", "Age-related macular degeneration")
    assert claim is not None
    qual = qualify_opposition_claim(claim, "Ranibizumab", "Age-related macular degeneration", t)
    assert qual.qualified is False
    assert qual.reason_code == "BIOSIMILAR_EQUIVALENCE_FAILURE"

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "Ranibizumab", "Age-related macular degeneration")
    assert assessment.score == 0.0
    assert assessment.level == "NONE"

    decision = apply_decision_rules(
        is_approved=True,
        matched_chembl_term="wet macular degeneration",
        support_score=0.994,
        evidence_count=68,
        mechanistic_score=0.490,
        risk_score=0.0,
        opp_assessment=assessment,
    )
    assert decision.status == RecommendationStatus.PROMISING
    assert "Rule -1 (APPROVED INDICATION RESOLUTION)" in decision.deciding_rule
    assert decision.trace["conflict_type"] == OppositionConflictType.NO_CONFLICT.value
    assert decision.trace["approved_anchor"] is True
    assert decision.trace["opposition_score"] == 0.0
