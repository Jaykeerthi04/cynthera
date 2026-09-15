"""Unit tests for clinical trial statistical direction semantics.

Comprehensive test suite verifying that clinical trial outcome measures, p-values,
confidence intervals, non-inferiority margins, equivalence bounds, and safety endpoints
are interpreted with scientific correctness.

Prevents false opposition regressions (e.g. TC-043 Rosiglitazone, TC-072 Empagliflozin)
while strictly preserving genuine negative evidence (e.g. TC-030 CRASH, TC-026 AIM-HIGH).
"""
from __future__ import annotations

import pytest

from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.enums.statistical_direction import (
    OutcomeDirection,
    StatisticalReasonCode,
    OutcomeEvaluationResult,
)
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    trial_to_negative_claim,
    TherapeuticOppositionAssessor,
)


def _build_trial(
    nct_id: str = "NCT01234567",
    title: str = "Test Trial",
    status: TrialOutcomeStatus = TrialOutcomeStatus.UNKNOWN,
    is_negative_efficacy: bool = False,
    negative_efficacy_reason: str | None = None,
    condition_names: list[str] | None = None,
    intervention_names: list[str] | None = None,
    comparator_names: list[str] | None = None,
    why_stopped: str | None = None,
    outcome_measures: list[dict] | None = None,
) -> ClinicalTrial:
    prov = ProvenanceReference(
        source_name="ClinicalTrials.gov",
        source_version="2024",
        record_id=nct_id,
        url=f"https://clinicaltrials.gov/study/{nct_id}",
    )
    return ClinicalTrial(
        nct_id=nct_id,
        title=title,
        phase="Phase III",
        status=status,
        provenance=prov,
        condition_names=condition_names or ["DiseaseY"],
        intervention_names=intervention_names or ["DrugX"],
        comparator_names=comparator_names or ["Placebo"],
        why_stopped=why_stopped,
        is_negative_efficacy=is_negative_efficacy,
        negative_efficacy_reason=negative_efficacy_reason,
        outcome_measures=outcome_measures or [],
        has_results=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: p >= 0.05 primary endpoint is NEUTRAL, NOT automatic failure
# ─────────────────────────────────────────────────────────────────────────────
def test_01_primary_endpoint_p_ge_005_is_neutral_not_failure():
    """p >= 0.05 on primary endpoint does NOT establish therapeutic failure; must be NEUTRAL."""
    om = {
        "type": "PRIMARY",
        "title": "Time to Recovery",
        "description": "Days to symptom resolution",
        "analyses": [
            {
                "pValue": "0.120",
                "statisticalMethod": "Log Rank",
                "paramType": "Hazard Ratio",
                "paramValue": "0.91",
                "ciLowerLimit": "0.80",
                "ciUpperLimit": "1.03",
            }
        ],
    }
    res = RetrievalPipeline._evaluate_outcome_measure_direction(om)
    assert res.direction == OutcomeDirection.NEUTRAL
    assert res.reason_code == StatisticalReasonCode.NON_SIGNIFICANT_PRIMARY_ENDPOINT
    assert "did not achieve statistical significance" in res.reason

    # Completed trial with neutral primary endpoint remains UNKNOWN, NOT COMPLETED_FAILURE
    trial = _build_trial(
        status=TrialOutcomeStatus.UNKNOWN,
        is_negative_efficacy=False,
        negative_efficacy_reason=res.reason,
    )
    claim = trial_to_negative_claim(trial, "DrugX", "DiseaseY")
    assert claim is None, "Neutral primary endpoint must NOT produce a negative claim"


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: p >= 0.05 secondary endpoint is NEUTRAL, NOT therapeutic failure
# ─────────────────────────────────────────────────────────────────────────────
def test_02_secondary_endpoint_p_ge_005_not_therapeutic_failure():
    """p >= 0.05 on secondary endpoint must NOT brand the entire trial as therapeutic failure."""
    om = {
        "type": "SECONDARY",
        "title": "Quality of Life Score at Week 12",
        "description": "SF-36 physical component score",
        "analyses": [
            {
                "pValue": "0.350",
                "statisticalMethod": "ANCOVA",
                "paramType": "Mean Difference",
                "paramValue": "1.2",
            }
        ],
    }
    res = RetrievalPipeline._evaluate_outcome_measure_direction(om)
    assert res.direction == OutcomeDirection.NEUTRAL
    assert res.reason_code == StatisticalReasonCode.NON_SIGNIFICANT_SECONDARY_ENDPOINT

    raw_study = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT01234567", "briefTitle": "Secondary non-sig study"},
                    "statusModule": {"overallStatus": "COMPLETED"},
                    "designModule": {"phases": ["PHASE3"]},
                    "conditionsModule": {"conditions": ["DiseaseY"]},
                    "armsInterventionsModule": {
                        "armGroups": [
                            {"type": "EXPERIMENTAL", "interventionNames": ["Drug: DrugX"]},
                            {"type": "PLACEBO_COMPARATOR", "interventionNames": ["Drug: Placebo"]},
                        ]
                    },
                },
                "resultsSection": {
                    "outcomeMeasuresModule": {
                        "outcomeMeasures": [om]
                    }
                },
            }
        ]
    }
    pipeline = RetrievalPipeline(db_path=":memory:")
    drug = Drug(name="DrugX", identifiers={"chembl": "CHEMBL123"})
    disease = Disease(name="DiseaseY", identifiers={"mesh": "D000001"})
    trials = pipeline._parse_trials_data(raw_study, drug, disease)

    assert len(trials) == 1
    assert trials[0].status == TrialOutcomeStatus.UNKNOWN
    assert trials[0].is_negative_efficacy is False
    assert trial_to_negative_claim(trials[0], "DrugX", "DiseaseY") is None


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Significant beneficial primary endpoint is POSITIVE
# ─────────────────────────────────────────────────────────────────────────────
def test_03_significant_beneficial_primary_endpoint_is_positive():
    """Statistically significant beneficial primary endpoint evaluates to POSITIVE."""
    om = {
        "type": "PRIMARY",
        "title": "Overall Survival",
        "description": "Months from randomization to death",
        "analyses": [
            {
                "pValue": "0.002",
                "statisticalMethod": "Log Rank",
                "paramType": "Hazard Ratio",
                "paramValue": "0.72",
                "ciLowerLimit": "0.58",
                "ciUpperLimit": "0.89",
            }
        ],
    }
    res = RetrievalPipeline._evaluate_outcome_measure_direction(om)
    assert res.direction == OutcomeDirection.POSITIVE
    assert res.reason_code == StatisticalReasonCode.STATISTICALLY_SIGNIFICANT_BENEFIT

    trial = _build_trial(
        status=TrialOutcomeStatus.COMPLETED_SUCCESS,
        is_negative_efficacy=False,
    )
    assert trial_to_negative_claim(trial, "DrugX", "DiseaseY") is None


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Significant harmful primary endpoint is NEGATIVE
# ─────────────────────────────────────────────────────────────────────────────
def test_04_significant_harmful_primary_endpoint_is_negative():
    """Statistically significant harmful primary outcome (increased mortality/progression) is NEGATIVE."""
    om = {
        "type": "PRIMARY",
        "title": "All-Cause Mortality",
        "description": "Death from any cause during treatment",
        "analyses": [
            {
                "pValue": "0.001",
                "statisticalMethod": "Log Rank",
                "paramType": "Hazard Ratio",
                "paramValue": "1.48",
                "ciLowerLimit": "1.18",
                "ciUpperLimit": "1.86",
            }
        ],
    }
    res = RetrievalPipeline._evaluate_outcome_measure_direction(om)
    assert res.direction == OutcomeDirection.NEGATIVE
    assert res.reason_code == StatisticalReasonCode.STATISTICALLY_SIGNIFICANT_HARM

    trial = _build_trial(
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        is_negative_efficacy=True,
        negative_efficacy_reason=res.reason,
    )
    claim = trial_to_negative_claim(trial, "DrugX", "DiseaseY")
    assert claim is not None
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Explicit futility is NEGATIVE
# ─────────────────────────────────────────────────────────────────────────────
def test_05_explicit_futility_is_negative():
    """Explicit futility boundary crossing evaluates to NEGATIVE and produces FAILED_TO_IMPROVE."""
    om = {
        "type": "PRIMARY",
        "title": "Primary Efficacy Composite",
        "description": "Pre-specified futility boundary crossed at interim analysis; DSMB recommended stop.",
        "analyses": [],
    }
    res = RetrievalPipeline._evaluate_outcome_measure_direction(om)
    assert res.direction == OutcomeDirection.NEGATIVE
    assert res.reason_code == StatisticalReasonCode.EXPLICIT_FUTILITY

    trial = _build_trial(
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        is_negative_efficacy=True,
        negative_efficacy_reason=res.reason,
    )
    claim = trial_to_negative_claim(trial, "DrugX", "DiseaseY")
    assert claim is not None
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Explicit lack of efficacy is NEGATIVE
# ─────────────────────────────────────────────────────────────────────────────
def test_06_explicit_lack_of_efficacy_is_negative():
    """Explicit textual lack of efficacy / failed primary endpoint is NEGATIVE."""
    om = {
        "type": "PRIMARY",
        "title": "Primary endpoint resolution",
        "description": "Trial failed to meet primary endpoint: investigator reported clear lack of efficacy.",
        "analyses": [],
    }
    res = RetrievalPipeline._evaluate_outcome_measure_direction(om)
    assert res.direction == OutcomeDirection.NEGATIVE
    assert res.reason_code == StatisticalReasonCode.EXPLICIT_LACK_OF_EFFICACY

    trial = _build_trial(
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        is_negative_efficacy=True,
        negative_efficacy_reason=res.reason,
    )
    claim = trial_to_negative_claim(trial, "DrugX", "DiseaseY")
    assert claim is not None
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: Single-arm without comparator is UNKNOWN / INCONCLUSIVE
# ─────────────────────────────────────────────────────────────────────────────
def test_07_single_arm_without_comparator_is_unknown():
    """Single-arm or paired within-subject analysis without comparator must NOT become NEGATIVE."""
    om = {
        "type": "PRIMARY",
        "title": "Single arm response rate",
        "description": "Within-subject change from baseline",
        "analyses": [
            {
                "pValue": "0.280",
                "statisticalMethod": "Paired t-test",
            }
        ],
    }
    res = RetrievalPipeline._evaluate_outcome_measure_direction(om)
    assert res.direction == OutcomeDirection.UNKNOWN
    assert res.reason_code == StatisticalReasonCode.SINGLE_ARM_NO_COMPARATOR

    trial = _build_trial(
        status=TrialOutcomeStatus.UNKNOWN,
        is_negative_efficacy=False,
    )
    assert trial_to_negative_claim(trial, "DrugX", "DiseaseY") is None


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: Non-inferiority success
# ─────────────────────────────────────────────────────────────────────────────
def test_08_non_inferiority_success():
    """Non-inferiority study meeting margin evaluates to POSITIVE (NON_INFERIOR)."""
    om = {
        "type": "PRIMARY",
        "title": "Composite Cardiovascular Event Rate",
        "description": "Non-inferiority comparison against standard of care",
        "analyses": [
            {
                "nonInferiorityType": "NON_INFERIORITY",
                "nonInferiorityComment": "Non-inferiority margin of 1.25 for hazard ratio",
                "statisticalMethod": "Cox proportional hazards non-inferiority test",
                "paramType": "Hazard Ratio",
                "paramValue": "0.98",
                "ciLowerLimit": "0.82",
                "ciUpperLimit": "1.17",  # upper bound 1.17 <= margin 1.25 -> success!
            }
        ],
    }
    res = RetrievalPipeline._evaluate_outcome_measure_direction(om)
    assert res.direction == OutcomeDirection.POSITIVE
    assert res.reason_code == StatisticalReasonCode.NON_INFERIOR
    assert "met non-inferiority criterion" in res.reason


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: Non-inferiority failure
# ─────────────────────────────────────────────────────────────────────────────
def test_09_non_inferiority_failure():
    """Non-inferiority study failing margin evaluates to NEGATIVE (NON_INFERIORITY_FAILURE)."""
    om = {
        "type": "PRIMARY",
        "title": "Treatment Success Rate",
        "description": "Non-inferiority trial vs active comparator",
        "analyses": [
            {
                "nonInferiorityType": "NON_INFERIORITY",
                "nonInferiorityComment": "Non-inferiority margin is 1.15",
                "statisticalMethod": "Cox regression non-inferiority test",
                "paramType": "Hazard Ratio",
                "paramValue": "1.05",
                "ciLowerLimit": "0.89",
                "ciUpperLimit": "1.32",  # upper bound 1.32 > margin 1.15 -> failure!
            }
        ],
    }
    res = RetrievalPipeline._evaluate_outcome_measure_direction(om)
    assert res.direction == OutcomeDirection.NEGATIVE
    assert res.reason_code == StatisticalReasonCode.NON_INFERIORITY_FAILURE
    assert "failed non-inferiority criterion" in res.reason


# ─────────────────────────────────────────────────────────────────────────────
# Test 10: Equivalence interpretation (success and failure)
# ─────────────────────────────────────────────────────────────────────────────
def test_10_equivalence_interpretation():
    """Equivalence studies evaluated against bounds: within bounds = POSITIVE; outside = NEGATIVE."""
    # 10a: Successful equivalence
    om_success = {
        "type": "PRIMARY",
        "title": "Therapeutic Equivalence Score",
        "description": "Equivalence study with bounds [0.80, 1.25]",
        "analyses": [
            {
                "nonInferiorityType": "EQUIVALENCE",
                "nonInferiorityComment": "Equivalence bounds of 0.80 to 1.25",
                "paramType": "Ratio",
                "ciLowerLimit": "0.92",
                "ciUpperLimit": "1.08",
            }
        ],
    }
    res_succ = RetrievalPipeline._evaluate_outcome_measure_direction(om_success)
    assert res_succ.direction == OutcomeDirection.POSITIVE
    assert res_succ.reason_code == StatisticalReasonCode.EQUIVALENT

    # 10b: Failed equivalence
    om_fail = {
        "type": "PRIMARY",
        "title": "Therapeutic Equivalence Score",
        "description": "Equivalence study with bounds [0.80, 1.25]",
        "analyses": [
            {
                "nonInferiorityType": "EQUIVALENCE",
                "nonInferiorityComment": "Equivalence bounds of 0.80 to 1.25",
                "paramType": "Ratio",
                "ciLowerLimit": "0.74",  # outside 0.80!
                "ciUpperLimit": "1.18",
            }
        ],
    }
    res_fail = RetrievalPipeline._evaluate_outcome_measure_direction(om_fail)
    assert res_fail.direction == OutcomeDirection.NEGATIVE
    assert res_fail.reason_code == StatisticalReasonCode.EQUIVALENCE_FAILURE


# ─────────────────────────────────────────────────────────────────────────────
# Test 11: Safety endpoint is SAFETY_HARM, not generic efficacy failure
# ─────────────────────────────────────────────────────────────────────────────
def test_11_safety_endpoint_is_safety_harm_not_efficacy_failure():
    """Safety/adverse event imbalance must evaluate to SAFETY_HARM and not generate FAILED_TO_IMPROVE."""
    om_safety = {
        "type": "PRIMARY",
        "title": "Incidence of Treatment-Emergent Serious Adverse Events",
        "description": "Toxicity and safety monitoring",
        "analyses": [
            {
                "pValue": "0.010",
                "paramType": "Relative Risk",
                "paramValue": "2.10",
            }
        ],
    }
    res = RetrievalPipeline._evaluate_outcome_measure_direction(om_safety)
    assert res.direction == OutcomeDirection.SAFETY_HARM
    assert res.reason_code == StatisticalReasonCode.SAFETY_ENDPOINT

    raw_study = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT09991111", "briefTitle": "Safety trial"},
                    "statusModule": {"overallStatus": "COMPLETED"},
                    "designModule": {"phases": ["PHASE1"]},
                    "conditionsModule": {"conditions": ["DiseaseY"]},
                    "armsInterventionsModule": {
                        "armGroups": [{"type": "EXPERIMENTAL", "interventionNames": ["Drug: DrugX"]}],
                    },
                },
                "resultsSection": {
                    "outcomeMeasuresModule": {"outcomeMeasures": [om_safety]},
                },
            }
        ]
    }
    pipeline = RetrievalPipeline(db_path=":memory:")
    drug = Drug(name="DrugX", identifiers={"chembl": "CHEMBL123"})
    disease = Disease(name="DiseaseY", identifiers={"mesh": "D000001"})
    trials = pipeline._parse_trials_data(raw_study, drug, disease)

    assert len(trials) == 1
    assert trials[0].is_negative_efficacy is False
    assert trials[0].status == TrialOutcomeStatus.UNKNOWN
    assert trial_to_negative_claim(trials[0], "DrugX", "DiseaseY") is None


# ─────────────────────────────────────────────────────────────────────────────
# Test 12: Neutral EMPACT-MI-like result must NOT create opposition for Empagliflozin -> HF
# ─────────────────────────────────────────────────────────────────────────────
def test_12_neutral_empact_mi_result_no_opposition_for_empagliflozin_hf():
    """Neutral post-MI study (e.g. EMPACT-MI) must NOT create therapeutic opposition for Empagliflozin in HF."""
    om_empact = {
        "type": "PRIMARY",
        "title": "Composite of Time to First Heart Failure Hospitalization or All-Cause Mortality",
        "description": "Post-myocardial infarction heart failure event prevention",
        "analyses": [
            {
                "pValue": "0.210",
                "statisticalMethod": "Log Rank",
                "paramType": "Hazard Ratio",
                "paramValue": "0.90",
                "ciLowerLimit": "0.76",
                "ciUpperLimit": "1.07",
            }
        ],
    }
    res = RetrievalPipeline._evaluate_outcome_measure_direction(om_empact)
    assert res.direction == OutcomeDirection.NEUTRAL
    assert res.reason_code == StatisticalReasonCode.NON_SIGNIFICANT_PRIMARY_ENDPOINT

    raw_study = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT04509245", "briefTitle": "EMPACT-MI Study"},
                    "statusModule": {"overallStatus": "COMPLETED"},
                    "designModule": {"phases": ["PHASE3"]},
                    "conditionsModule": {"conditions": ["Heart Failure", "Myocardial Infarction"]},
                    "armsInterventionsModule": {
                        "armGroups": [
                            {"type": "EXPERIMENTAL", "interventionNames": ["Drug: Empagliflozin"]},
                            {"type": "PLACEBO_COMPARATOR", "interventionNames": ["Drug: Placebo"]},
                        ]
                    },
                },
                "resultsSection": {
                    "outcomeMeasuresModule": {"outcomeMeasures": [om_empact]},
                },
            }
        ]
    }
    pipeline = RetrievalPipeline(db_path=":memory:")
    drug = Drug(name="Empagliflozin", identifiers={"chembl": "CHEMBL2028674"})
    disease = Disease(name="Heart failure", identifiers={"mesh": "D006333"})
    trials = pipeline._parse_trials_data(raw_study, drug, disease)

    assert len(trials) == 1
    t = trials[0]
    assert t.status == TrialOutcomeStatus.UNKNOWN
    assert t.is_negative_efficacy is False

    claim = trial_to_negative_claim(t, "Empagliflozin", "Heart failure")
    assert claim is None, "EMPACT-MI neutral outcome must NOT produce a negative claim"

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([], "Empagliflozin", "Heart failure")
    assert assessment.score == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Test 13: Rosiglitazone neutral secondary endpoint must NOT create opposition for T2D
# ─────────────────────────────────────────────────────────────────────────────
def test_13_rosiglitazone_neutral_secondary_endpoint_no_opposition_for_t2d():
    """Rosiglitazone trial with neutral secondary exploratory endpoint must NOT create opposition for T2D."""
    om_primary_neutral = {
        "type": "PRIMARY",
        "title": "Change in Fasting Plasma Glucose at Week 24",
        "analyses": [
            {
                "pValue": "0.080",
                "statisticalMethod": "ANCOVA",
                "paramType": "Mean Difference",
                "paramValue": "-12.5",
            }
        ],
    }
    om_secondary_neutral = {
        "type": "SECONDARY",
        "title": "Exploratory Cardiovascular Composite Events",
        "analyses": [
            {
                "pValue": "0.400",
                "statisticalMethod": "Log Rank",
                "paramType": "Hazard Ratio",
                "paramValue": "1.08",
                "ciLowerLimit": "0.85",
                "ciUpperLimit": "1.37",
            }
        ],
    }
    raw_study = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT00265148", "briefTitle": "Rosiglitazone T2D Evaluation"},
                    "statusModule": {"overallStatus": "COMPLETED"},
                    "designModule": {"phases": ["PHASE3"]},
                    "conditionsModule": {"conditions": ["Type 2 Diabetes Mellitus"]},
                    "armsInterventionsModule": {
                        "armGroups": [
                            {"type": "EXPERIMENTAL", "interventionNames": ["Drug: Rosiglitazone"]},
                            {"type": "ACTIVE_COMPARATOR", "interventionNames": ["Drug: Metformin"]},
                        ]
                    },
                },
                "resultsSection": {
                    "outcomeMeasuresModule": {"outcomeMeasures": [om_primary_neutral, om_secondary_neutral]},
                },
            }
        ]
    }
    pipeline = RetrievalPipeline(db_path=":memory:")
    drug = Drug(name="Rosiglitazone", identifiers={"chembl": "CHEMBL582"})
    disease = Disease(name="Type 2 diabetes mellitus", identifiers={"mesh": "D003924"})
    trials = pipeline._parse_trials_data(raw_study, drug, disease)

    assert len(trials) == 1
    t = trials[0]
    assert t.status == TrialOutcomeStatus.UNKNOWN
    assert t.is_negative_efficacy is False

    claim = trial_to_negative_claim(t, "Rosiglitazone", "Type 2 diabetes mellitus")
    assert claim is None, "Rosiglitazone neutral trial must NOT produce a negative claim"


# ─────────────────────────────────────────────────────────────────────────────
# Test 14: CRASH Dexamethasone genuine negative evidence remains negative
# ─────────────────────────────────────────────────────────────────────────────
def test_14_crash_dexamethasone_genuine_negative_remains_negative():
    """CRASH trial in TBI demonstrated statistically significant excess mortality; must remain NEGATIVE."""
    om_crash_mortality = {
        "type": "PRIMARY",
        "title": "All-Cause Mortality at 14 Days",
        "description": "Death from any cause within 2 weeks of head injury",
        "analyses": [
            {
                "pValue": "0.0001",
                "statisticalMethod": "Log Rank",
                "paramType": "Risk Ratio",
                "paramValue": "1.18",
                "ciLowerLimit": "1.09",
                "ciUpperLimit": "1.27",
            }
        ],
    }
    res = RetrievalPipeline._evaluate_outcome_measure_direction(om_crash_mortality)
    assert res.direction == OutcomeDirection.NEGATIVE
    assert res.reason_code == StatisticalReasonCode.STATISTICALLY_SIGNIFICANT_HARM

    trial = _build_trial(
        nct_id="NCT00000222",
        title="CRASH trial: Corticosteroid Randomisation After Significant Head Injury",
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        is_negative_efficacy=True,
        negative_efficacy_reason=res.reason,
        condition_names=["Traumatic Brain Injury"],
        intervention_names=["Dexamethasone"],
        comparator_names=["Placebo"],
    )
    claim = trial_to_negative_claim(trial, "Dexamethasone", "Traumatic brain injury")
    assert claim is not None, "CRASH trial must produce an empirical opposition claim"
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "Dexamethasone", "Traumatic brain injury")
    assert assessment.score > 0.0, "CRASH evidence must generate therapeutic opposition"
    assert assessment.independent_group_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# Test 15: AIM-HIGH Niacin genuine negative evidence remains negative
# ─────────────────────────────────────────────────────────────────────────────
def test_15_aim_high_niacin_genuine_negative_remains_negative():
    """AIM-HIGH trial terminated early for lack of efficacy/futility; must remain NEGATIVE."""
    trial = _build_trial(
        nct_id="NCT00120289",
        title="AIM-HIGH: Niacin in Patients with Low HDL and Cardiovascular Disease",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        is_negative_efficacy=True,
        negative_efficacy_reason="Trial terminated early: Lack of efficacy; no safety concern",
        why_stopped="Lack of efficacy; no safety concern",
        condition_names=["Cardiovascular Disease", "Atherosclerosis"],
        intervention_names=["Niacin", "Simvastatin"],
        comparator_names=["Placebo", "Simvastatin"],
    )
    claim = trial_to_negative_claim(trial, "Niacin", "Cardiovascular disease")
    assert claim is not None, "AIM-HIGH must produce an empirical opposition claim"
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "Niacin", "Cardiovascular disease")
    assert assessment.score > 0.0, "AIM-HIGH evidence must generate therapeutic opposition"
    assert assessment.independent_group_count == 1
