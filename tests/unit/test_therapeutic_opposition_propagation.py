"""Regression tests for Priority 2: Therapeutic Opposition Propagation.

Validates the 9 specific requirements defined in Step 10:
1. Neutral p >= 0.05 -> zero therapeutic opposition (no claim, Opp = 0.0)
2. Explicit futility -> non-zero therapeutic opposition
3. Significant harmful primary efficacy endpoint -> non-zero therapeutic opposition
4. Primary direct therapeutic failure -> non-zero therapeutic opposition
5. Secondary neutral endpoint -> zero therapeutic opposition
6. Genuine negative trial can cross the empirical-opposition decision boundary when evidence quality/strength warrants it (Opp >= 0.45, Rule 2b)
7. Neutral trial cannot cross that boundary (Opp = 0.0)
8. Multiple independent genuine failures aggregate appropriately (n=2 > n=1)
9. Duplicate copies of the same failure do not artificially inflate opposition (same NCT = 1 group)
"""
import pytest
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.claim import Claim
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.reasoning_result import OppositionAssessment
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.enums.recommendation import RecommendationStatus
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    trial_to_negative_claim,
)
from backend.reasoning.orchestrator.decision_rules import apply_decision_rules


def _build_trial(
    nct_id: str,
    status: TrialOutcomeStatus,
    title: str = "Test Trial",
    design_allocation: str = "RANDOMIZED",
    study_type: str = "INTERVENTIONAL",
    condition_names: list[str] | None = None,
    intervention_names: list[str] | None = None,
    comparator_names: list[str] | None = None,
    why_stopped: str | None = None,
    outcome_measures: list[dict] | None = None,
    is_negative_efficacy: bool = False,
    negative_efficacy_reason: str | None = None,
) -> ClinicalTrial:
    return ClinicalTrial(
        nct_id=nct_id,
        title=title,
        phase="Phase III",
        status=status,
        provenance=ProvenanceReference(
            source_name="ClinicalTrials.gov",
            source_version="2024",
            record_id=nct_id,
        ),
        design_allocation=design_allocation,
        study_type=study_type,
        condition_names=condition_names or ["Cardiovascular disease"],
        intervention_names=intervention_names or ["TestDrug"],
        comparator_names=comparator_names or ["Placebo"],
        why_stopped=why_stopped,
        outcome_measures=outcome_measures or [],
        is_negative_efficacy=is_negative_efficacy,
        negative_efficacy_reason=negative_efficacy_reason,
    )


# 1. Neutral p >= 0.05 -> zero therapeutic opposition
def test_1_neutral_p_value_produces_zero_opposition():
    """Requirement 1: A neutral trial (p >= 0.05) produces NO claim and Opp = 0.0."""
    trial = _build_trial(
        nct_id="NCT01111111",
        status=TrialOutcomeStatus.UNKNOWN,
        title="Neutral Trial of TestDrug",
        outcome_measures=[
            {
                "type": "PRIMARY",
                "title": "Primary Endpoint",
                "direction": "NEUTRAL",
                "reason_code": "NON_SIGNIFICANT_PRIMARY_ENDPOINT",
            }
        ],
    )
    claim = trial_to_negative_claim(trial, "TestDrug", "Cardiovascular disease")
    assert claim is None, "Neutral primary endpoint must not produce an opposition claim"

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([], "TestDrug", "Cardiovascular disease")
    assert assessment.score == 0.0
    assert assessment.level == "NONE"
    assert assessment.independent_group_count == 0


# 2. Explicit futility -> non-zero therapeutic opposition
def test_2_explicit_futility_produces_nonzero_opposition():
    """Requirement 2: Explicit futility produces a genuine opposition claim and non-zero score."""
    trial = _build_trial(
        nct_id="NCT02222222",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        title="Futility Trial",
        why_stopped="Study stopped early for futility by DSMB",
        outcome_measures=[
            {
                "type": "PRIMARY",
                "title": "Primary Outcome",
                "direction": "NEGATIVE",
                "reason_code": "EXPLICIT_FUTILITY",
            }
        ],
    )
    claim = trial_to_negative_claim(trial, "TestDrug", "Cardiovascular disease")
    assert claim is not None, "Explicit futility trial must generate a negative claim"
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE
    assert claim.confidence == 0.95

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "TestDrug", "Cardiovascular disease")
    assert assessment.score > 0.0
    assert assessment.score >= 0.45
    assert assessment.level == "HIGH"


# 3. Significant harmful primary efficacy endpoint -> non-zero therapeutic opposition
def test_3_significant_harmful_endpoint_produces_nonzero_opposition():
    """Requirement 3: Significant harmful primary endpoint produces strong opposition."""
    trial = _build_trial(
        nct_id="NCT03333333",
        status=TrialOutcomeStatus.TERMINATED_SAFETY,
        title="Harmful Outcome Trial",
        why_stopped="Terminated due to serious adverse events and increased mortality",
        outcome_measures=[
            {
                "type": "PRIMARY",
                "title": "All-Cause Mortality",
                "direction": "SAFETY_HARM",
                "reason_code": "STATISTICALLY_SIGNIFICANT_HARM",
            }
        ],
    )
    claim = trial_to_negative_claim(trial, "TestDrug", "Cardiovascular disease")
    assert claim is not None, "Harmful primary endpoint must generate an opposition claim"
    assert claim.confidence == 0.95

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "TestDrug", "Cardiovascular disease")
    assert assessment.score >= 0.45
    assert assessment.level == "HIGH"


# 4. Primary direct therapeutic failure -> non-zero therapeutic opposition
def test_4_primary_direct_failure_produces_nonzero_opposition():
    """Requirement 4: Completed trial failing primary endpoint produces non-zero opposition."""
    trial = _build_trial(
        nct_id="NCT04444444",
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        title="Completed Failure Study",
        is_negative_efficacy=True,
        negative_efficacy_reason="Primary efficacy endpoint failed",
        outcome_measures=[
            {
                "type": "PRIMARY",
                "title": "Primary Efficacy Endpoint",
                "direction": "NEGATIVE",
                "reason_code": "STATISTICALLY_SIGNIFICANT_HARM",
            }
        ],
    )
    claim = trial_to_negative_claim(trial, "TestDrug", "Cardiovascular disease")
    assert claim is not None, "Primary endpoint failure must produce an opposition claim"
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "TestDrug", "Cardiovascular disease")
    assert assessment.score >= 0.45
    assert assessment.level == "HIGH"


# 5. Secondary neutral endpoint -> zero therapeutic opposition
def test_5_secondary_neutral_endpoint_produces_zero_opposition():
    """Requirement 5: Non-significant secondary endpoint produces ZERO opposition."""
    trial = _build_trial(
        nct_id="NCT05555555",
        status=TrialOutcomeStatus.UNKNOWN,
        title="Study with Neutral Secondary Endpoint",
        outcome_measures=[
            {
                "type": "SECONDARY",
                "title": "Secondary Quality of Life Endpoint",
                "direction": "NEUTRAL",
                "reason_code": "NON_SIGNIFICANT_SECONDARY_ENDPOINT",
            }
        ],
    )
    claim = trial_to_negative_claim(trial, "TestDrug", "Cardiovascular disease")
    assert claim is None, "Secondary neutral endpoint must not generate opposition claim"


# 6. Genuine negative trial can cross empirical-opposition decision boundary
def test_6_genuine_negative_trial_crosses_decision_boundary():
    """Requirement 6: A single definitive Phase III RCT failure can cross Opp >= 0.45 and trigger Rule 2b."""
    trial = _build_trial(
        nct_id="NCT00120289",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        title="AIM-HIGH Trial: Niacin Plus Statin to Prevent Vascular Events",
        why_stopped="AIM-HIGH was stopped on the recommendation of the DSMB because of lack of efficacy of niacin in preventing primary outcome events.",
        condition_names=["Cardiovascular disease"],
        intervention_names=["Niacin"],
        comparator_names=["Placebo"],
    )
    claim = trial_to_negative_claim(trial, "Niacin", "Cardiovascular disease")
    assert claim is not None

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "Niacin", "Cardiovascular disease")

    # Score must be >= 0.45 (HIGH level)
    assert assessment.score >= 0.45, f"Expected Opp >= 0.45, got {assessment.score}"
    assert assessment.level == "HIGH"
    assert assessment.independent_group_count == 1

    # Feed into authoritative decision rules
    decision = apply_decision_rules(
        support_score=0.70,
        mechanistic_score=0.50,
        risk_score=0.20,
        opp_assessment=assessment,
        failed_trial_count=1,
    )
    assert decision.status == RecommendationStatus.NOT_RECOMMENDED
    assert "Rule 2b" in decision.deciding_rule, f"Expected Rule 2b to fire, got: {decision.deciding_rule}"


# 7. Neutral trial cannot cross that boundary
def test_7_neutral_trial_cannot_cross_boundary():
    """Requirement 7: Neutral trials produce zero opposition and cannot trigger Rule 2b veto."""
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([], "Rosiglitazone", "Type 2 diabetes")

    assert assessment.score == 0.0
    assert assessment.level == "NONE"

    decision = apply_decision_rules(
        support_score=0.70,
        mechanistic_score=0.50,
        risk_score=0.20,
        opp_assessment=assessment,
        failed_trial_count=0,
    )
    # Neutral trial must not oppose
    assert decision.status != RecommendationStatus.NOT_RECOMMENDED
    assert "Rule 2b" not in decision.deciding_rule


# 8. Multiple independent genuine failures aggregate appropriately
def test_8_multiple_independent_failures_aggregate():
    """Requirement 8: Two independent RCT failures achieve higher opposition score than one."""
    trial_1 = _build_trial(
        nct_id="NCT00000001",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        title="Trial 1",
    )
    trial_2 = _build_trial(
        nct_id="NCT00000002",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        title="Trial 2",
    )
    claim_1 = trial_to_negative_claim(trial_1, "TestDrug", "Cardiovascular disease")
    claim_2 = trial_to_negative_claim(trial_2, "TestDrug", "Cardiovascular disease")

    assessor = TherapeuticOppositionAssessor()
    assessment_1 = assessor.assess([claim_1], "TestDrug", "Cardiovascular disease")
    assessment_2 = assessor.assess([claim_1, claim_2], "TestDrug", "Cardiovascular disease")

    assert assessment_2.independent_group_count == 2
    assert assessment_1.independent_group_count == 1
    assert assessment_2.score > assessment_1.score, "Two independent groups must score higher than one"
    # factor(2) = 0.85, factor(1) = 0.70 -> 0.81 * 0.85 = 0.6885 vs 0.81 * 0.70 = 0.5670
    assert assessment_2.score == pytest.approx(0.6885, abs=0.01)
    assert assessment_1.score == pytest.approx(0.5670, abs=0.01)


# 9. Duplicate copies of the same failure do not artificially inflate opposition
def test_9_duplicate_records_do_not_inflate_opposition():
    """Requirement 9: Multiple claims from the same trial are grouped and do NOT inflate score."""
    prov = ProvenanceReference(
        source_name="ClinicalTrials.gov",
        source_version="2024",
        record_id="NCT00120289",
    )
    claim_a = Claim(
        subject="TestDrug",
        predicate=PredicateType.FAILED_TO_IMPROVE,
        object="Cardiovascular disease",
        confidence=0.95,
        erw=ERW(value=0.90, base_weight=0.90),
        provenance=prov,
        raw_text="Primary publication record",
        is_validated=True,
        evidence_type="RCT",
    )
    claim_b = Claim(
        subject="TestDrug",
        predicate=PredicateType.FAILED_TO_IMPROVE,
        object="Cardiovascular disease",
        confidence=0.90,
        erw=ERW(value=0.90, base_weight=0.90),
        provenance=prov,
        raw_text="Secondary publication record of same trial",
        is_validated=True,
        evidence_type="RCT",
    )

    assessor = TherapeuticOppositionAssessor()
    single_assessment = assessor.assess([claim_a], "TestDrug", "Cardiovascular disease")
    duplicate_assessment = assessor.assess([claim_a, claim_b], "TestDrug", "Cardiovascular disease")

    assert duplicate_assessment.qualified_negative_claim_count == 2
    assert duplicate_assessment.independent_group_count == 1
    assert duplicate_assessment.score == single_assessment.score, "Duplicate records from same study must not inflate opposition score"
