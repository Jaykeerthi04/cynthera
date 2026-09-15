"""Unit tests for ClinicalTrials.gov Issue 5 Negative-Outcome Recovery (Phase 2).

Deterministic test suite validating the 11 core requirements (A through K)
from Prompt Section 26:

A. Completed trial with positive outcome -> NOT negative
B. Completed trial with unknown outcome -> NOT negative
C. Negative primary efficacy outcome -> FAILED_TO_IMPROVE
D. Negative secondary efficacy outcome (when primary missing/silent) -> FAILED_TO_IMPROVE
E. Safety-only adverse outcome -> classified as safety, NOT therapeutic efficacy opposition
F. Missing resultsSection -> handled safely without exception
G. Malformed / null results -> handled safely without exception
H. Duplicate NCT -> clustered into 1 independent evidence group
I. Pair-mismatched trial -> excluded by pair specificity gate
J. Explicit negative efficacy statement in outcome text -> converted to negative claim
K. Negative outcome of an unrelated intervention in a combination study -> rejected by attribution
"""
from __future__ import annotations

import pytest

from backend.core.domain.claim import Claim
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.trial_attribution import TrialDrugRole
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    matches_disease_condition,
    trial_to_negative_claim,
)


def _build_trial(
    nct_id: str = "NCT00000001",
    title: str = "Clinical Trial Evaluation of DrugX in DiseaseY",
    status: TrialOutcomeStatus = TrialOutcomeStatus.UNKNOWN,
    phase: str = "Phase III",
    intervention_names: list[str] | None = None,
    comparator_names: list[str] | None = None,
    why_stopped: str | None = None,
    has_results: bool = True,
    outcome_measures: list[dict] | None = None,
    is_negative_efficacy: bool = False,
    negative_efficacy_reason: str | None = None,
    condition_names: list[str] | None = None,
) -> ClinicalTrial:
    """Helper to build a valid ClinicalTrial entity for Phase 2 tests."""
    return ClinicalTrial(
        nct_id=nct_id,
        title=title,
        phase=phase,
        status=status,
        intervention_names=intervention_names if intervention_names is not None else ["DrugX"],
        comparator_names=comparator_names if comparator_names is not None else ["Placebo"],
        why_stopped=why_stopped,
        provenance=ProvenanceReference(
            source_name="ClinicalTrials.gov",
            source_version="2024",
            record_id=nct_id,
        ),
        has_results=has_results,
        outcome_measures=outcome_measures or [],
        is_negative_efficacy=is_negative_efficacy,
        negative_efficacy_reason=negative_efficacy_reason,
        condition_names=condition_names if condition_names is not None else ["DiseaseY"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test A: Completed trial with positive outcome
# ─────────────────────────────────────────────────────────────────────────────
def test_a_completed_trial_with_positive_outcome():
    """A: Superiority p < 0.05 or positive statement must NOT become negative opposition."""
    om = {
        "type": "PRIMARY",
        "title": "Overall Survival at 1 Year",
        "description": "Proportion of surviving patients",
        "analyses": [
            {
                "pValue": "0.012",
                "statisticalMethod": "Log Rank",
                "nonInferiorityType": "SUPERIORITY",
            }
        ],
    }
    direction, reason = RetrievalPipeline._evaluate_outcome_measure_direction(om)
    assert direction == "POSITIVE"
    assert "p=0.012" in reason

    trial = _build_trial(
        status=TrialOutcomeStatus.COMPLETED_SUCCESS,
        is_negative_efficacy=False,
    )
    claim = trial_to_negative_claim(trial, "DrugX", "DiseaseY")
    assert claim is None, "Positive completed trial must NOT produce a negative claim"


# ─────────────────────────────────────────────────────────────────────────────
# Test B: Completed trial with unknown outcome
# ─────────────────────────────────────────────────────────────────────────────
def test_b_completed_trial_with_unknown_outcome():
    """B: Completed trial with no resultsSection or inconclusive analysis must remain non-negative."""
    om = {
        "type": "PRIMARY",
        "title": "Exploratory Biomarker Response",
        "description": "Descriptive statistics without hypothesis testing",
        "analyses": [],
    }
    direction, reason = RetrievalPipeline._evaluate_outcome_measure_direction(om)
    assert direction == "UNKNOWN"

    trial = _build_trial(
        status=TrialOutcomeStatus.UNKNOWN,
        is_negative_efficacy=False,
    )
    claim = trial_to_negative_claim(trial, "DrugX", "DiseaseY")
    assert claim is None, "Trial with unknown outcome must NOT produce a negative claim"


# ─────────────────────────────────────────────────────────────────────────────
# Test C: Primary efficacy outcome with p >= 0.05 is NEUTRAL, NOT failure
# ─────────────────────────────────────────────────────────────────────────────
def test_c_neutral_primary_efficacy_outcome_not_failure():
    """C: Primary efficacy endpoint failing superiority (p >= 0.05) is NEUTRAL and must NOT produce FAILED_TO_IMPROVE."""
    om = {
        "type": "PRIMARY",
        "title": "Time to Clinical Recovery",
        "description": "Days to symptom resolution",
        "analyses": [
            {
                "pValue": "0.880",
                "statisticalMethod": "Log Rank",
                "paramType": "Hazard Ratio",
                "paramValue": "0.99",
                "ciLowerLimit": "0.87",
                "ciUpperLimit": "1.13",
            }
        ],
    }
    direction, reason = RetrievalPipeline._evaluate_outcome_measure_direction(om)
    assert direction == "NEUTRAL"
    assert "did not achieve statistical significance" in reason

    trial = _build_trial(
        status=TrialOutcomeStatus.UNKNOWN,
        is_negative_efficacy=False,
        negative_efficacy_reason=reason,
    )
    claim = trial_to_negative_claim(trial, "DrugX", "DiseaseY")
    assert claim is None, "Neutral primary outcome trial must NOT produce a negative claim"


def test_c2_genuine_negative_primary_efficacy_harm():
    """C2: Primary efficacy endpoint with statistically significant harm produces FAILED_TO_IMPROVE."""
    om = {
        "type": "PRIMARY",
        "title": "All-Cause Mortality",
        "description": "Death from any cause at 1 year",
        "analyses": [
            {
                "pValue": "0.001",
                "statisticalMethod": "Log Rank",
                "paramType": "Hazard Ratio",
                "paramValue": "1.45",
                "ciLowerLimit": "1.15",
                "ciUpperLimit": "1.82",
            }
        ],
    }
    direction, reason = RetrievalPipeline._evaluate_outcome_measure_direction(om)
    assert direction == "NEGATIVE"
    assert "significantly increased risk" in reason

    trial = _build_trial(
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        is_negative_efficacy=True,
        negative_efficacy_reason=reason,
    )
    claim = trial_to_negative_claim(trial, "DrugX", "DiseaseY")
    assert claim is not None
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE


def test_c3_genuine_negative_primary_futility():
    """C3: Primary endpoint with explicit futility produces FAILED_TO_IMPROVE."""
    om = {
        "type": "PRIMARY",
        "title": "Event-Free Survival",
        "description": "Futility boundary crossed at pre-specified interim analysis",
        "analyses": [],
    }
    direction, reason = RetrievalPipeline._evaluate_outcome_measure_direction(om)
    assert direction == "NEGATIVE"
    assert "futility" in reason.lower()

    trial = _build_trial(
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        is_negative_efficacy=True,
        negative_efficacy_reason=reason,
    )
    claim = trial_to_negative_claim(trial, "DrugX", "DiseaseY")
    assert claim is not None
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE


# ─────────────────────────────────────────────────────────────────────────────
# Test D: Non-significant secondary efficacy outcome is NEUTRAL, NOT failure
# ─────────────────────────────────────────────────────────────────────────────
def test_d_neutral_secondary_efficacy_outcome_not_failure():
    """D: When primary endpoint is silent/missing, non-significant secondary endpoint (p >= 0.05) is NEUTRAL and does NOT brand trial as failure."""
    raw_study_data = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT01234567", "briefTitle": "Secondary non-significant trial"},
                    "statusModule": {"overallStatus": "COMPLETED"},
                    "designModule": {"phases": ["PHASE3"], "designInfo": {"allocation": "RANDOMIZED"}},
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
                        "outcomeMeasures": [
                            {
                                "type": "PRIMARY",
                                "title": "Enrollment completeness",
                                "description": "Number of participants enrolled",
                                "analyses": [],  # silent primary
                            },
                            {
                                "type": "SECONDARY",
                                "title": "Progression Free Survival",
                                "analyses": [
                                    {"pValue": "0.42", "statisticalMethod": "Log Rank"}
                                ],
                            },
                        ]
                    }
                },
            }
        ]
    }
    pipeline = RetrievalPipeline(db_path=":memory:")
    drug = Drug(name="DrugX", identifiers={"chembl": "CHEMBL123"})
    disease = Disease(name="DiseaseY", identifiers={"mesh": "D000001"})
    parsed_trials = pipeline._parse_trials_data(raw_study_data, drug, disease)

    assert len(parsed_trials) == 1
    t = parsed_trials[0]
    assert t.status == TrialOutcomeStatus.UNKNOWN
    assert t.is_negative_efficacy is False

    claim = trial_to_negative_claim(t, "DrugX", "DiseaseY")
    assert claim is None, "Non-significant secondary endpoint must NOT produce a negative claim"


def test_d2_positive_secondary_efficacy_outcome():
    """D2: When primary endpoint is silent, statistically significant positive secondary endpoint establishes positive efficacy."""
    raw_study_data = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT01234568", "briefTitle": "Secondary success trial"},
                    "statusModule": {"overallStatus": "COMPLETED"},
                    "designModule": {"phases": ["PHASE3"], "designInfo": {"allocation": "RANDOMIZED"}},
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
                        "outcomeMeasures": [
                            {
                                "type": "PRIMARY",
                                "title": "Enrollment completeness",
                                "description": "Number of participants enrolled",
                                "analyses": [],  # silent primary
                            },
                            {
                                "type": "SECONDARY",
                                "title": "Overall Survival",
                                "analyses": [
                                    {"pValue": "0.012", "statisticalMethod": "Log Rank"}
                                ],
                            },
                        ]
                    }
                },
            }
        ]
    }
    pipeline = RetrievalPipeline(db_path=":memory:")
    drug = Drug(name="DrugX", identifiers={"chembl": "CHEMBL123"})
    disease = Disease(name="DiseaseY", identifiers={"mesh": "D000001"})
    parsed_trials = pipeline._parse_trials_data(raw_study_data, drug, disease)

    assert len(parsed_trials) == 1
    t = parsed_trials[0]
    assert t.status == TrialOutcomeStatus.COMPLETED_SUCCESS
    assert t.is_negative_efficacy is False
    assert trial_to_negative_claim(t, "DrugX", "DiseaseY") is None


# ─────────────────────────────────────────────────────────────────────────────
# Test E: Safety-only adverse outcome
# ─────────────────────────────────────────────────────────────────────────────
def test_e_safety_only_adverse_outcome():
    """E: Adverse event imbalances / safety endpoints must NOT become FAILED_TO_IMPROVE efficacy opposition."""
    assert RetrievalPipeline._is_safety_endpoint("Incidence of Treatment-Emergent Adverse Events", "Safety profile") is True
    assert RetrievalPipeline._is_safety_endpoint("Time to Clinical Recovery", "Efficacy endpoint") is False

    om_safety = {
        "type": "PRIMARY",
        "title": "Serious Adverse Events (SAEs)",
        "description": "Number of patients with SAEs",
        "analyses": [{"pValue": "0.02", "paramType": "Relative Risk", "paramValue": "1.5"}],
    }
    raw_study_data = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT09999999", "briefTitle": "Safety trial"},
                    "statusModule": {"overallStatus": "COMPLETED"},
                    "designModule": {"phases": ["PHASE1"]},
                    "conditionsModule": {"conditions": ["DiseaseY"]},
                    "armsInterventionsModule": {
                        "armGroups": [
                            {"type": "EXPERIMENTAL", "interventionNames": ["Drug: DrugX"]},
                        ]
                    },
                },
                "resultsSection": {
                    "outcomeMeasuresModule": {
                        "outcomeMeasures": [om_safety]
                    }
                },
            }
        ]
    }
    pipeline = RetrievalPipeline(db_path=":memory:")
    drug = Drug(name="DrugX", identifiers={"chembl": "CHEMBL123"})
    disease = Disease(name="DiseaseY", identifiers={"mesh": "D000001"})
    parsed_trials = pipeline._parse_trials_data(raw_study_data, drug, disease)
    assert len(parsed_trials) == 1
    t = parsed_trials[0]
    # Safety outcome must not set is_negative_efficacy
    assert t.is_negative_efficacy is False
    assert t.status == TrialOutcomeStatus.UNKNOWN
    claim = trial_to_negative_claim(t, "DrugX", "DiseaseY")
    assert claim is None, "Safety-only outcome must NOT produce FAILED_TO_IMPROVE"


# ─────────────────────────────────────────────────────────────────────────────
# Test F: Missing resultsSection
# ─────────────────────────────────────────────────────────────────────────────
def test_f_missing_results_section():
    """F: Studies without resultsSection must be handled safely without error and not produce negative claims."""
    raw_study_data = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT01111111", "briefTitle": "Trial without results"},
                    "statusModule": {"overallStatus": "COMPLETED"},
                    "conditionsModule": {"conditions": ["DiseaseY"]},
                }
            }
        ]
    }
    pipeline = RetrievalPipeline(db_path=":memory:")
    drug = Drug(name="DrugX", identifiers={"chembl": "CHEMBL123"})
    disease = Disease(name="DiseaseY", identifiers={"mesh": "D000001"})
    trials = pipeline._parse_trials_data(raw_study_data, drug, disease)
    assert len(trials) == 1
    assert trials[0].has_results is False
    assert trials[0].is_negative_efficacy is False
    assert trial_to_negative_claim(trials[0], "DrugX", "DiseaseY") is None


# ─────────────────────────────────────────────────────────────────────────────
# Test G: Malformed / null results
# ─────────────────────────────────────────────────────────────────────────────
def test_g_malformed_null_results():
    """G: Malformed results (None values, unparseable strings, missing fields) must not raise exceptions."""
    malformed_om = {
        "type": "PRIMARY",
        "title": None,
        "description": None,
        "analyses": [
            {"pValue": "not_a_number", "paramValue": None, "ciLowerLimit": "bad", "ciUpperLimit": None},
            {"pValue": None},
        ],
    }
    direction, reason = RetrievalPipeline._evaluate_outcome_measure_direction(malformed_om)
    assert direction == "UNKNOWN"
    assert reason is None


# ─────────────────────────────────────────────────────────────────────────────
# Test H: Duplicate NCT
# ─────────────────────────────────────────────────────────────────────────────
def test_h_duplicate_nct_clustering():
    """H: Multiple claims referencing the same NCT must be clustered into 1 independent evidence group."""
    trial = _build_trial(
        nct_id="NCT04492475",
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        is_negative_efficacy=True,
    )
    claim1 = trial_to_negative_claim(trial, "DrugX", "DiseaseY")
    claim2 = trial_to_negative_claim(trial, "DrugX", "DiseaseY")

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim1, claim2], "DrugX", "DiseaseY")

    assert assessment.qualified_negative_claim_count == 2
    assert assessment.independent_group_count == 1, "Duplicate NCT must collapse into 1 independent study"
    assert assessment.score > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Test I: Pair-mismatched trial
# ─────────────────────────────────────────────────────────────────────────────
def test_i_pair_mismatched_trial_excluded():
    """I: Trial evaluating DrugX in DiseaseZ must NOT produce negative opposition for DiseaseY."""
    trial_mismatch = _build_trial(
        nct_id="NCT07777777",
        title="DrugX in Rheumatoid Arthritis",
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        is_negative_efficacy=True,
        condition_names=["Rheumatoid Arthritis", "Joint Inflammation"],
    )
    # Evaluated against Alzheimer's disease
    assert matches_disease_condition(trial_mismatch, "Alzheimer's disease") is False
    claim = trial_to_negative_claim(trial_mismatch, "DrugX", "Alzheimer's disease")
    assert claim is None, "Pair-mismatched trial must be excluded by pair specificity gate"


# ─────────────────────────────────────────────────────────────────────────────
# Test J: Explicit negative efficacy statement vs neutral statement
# ─────────────────────────────────────────────────────────────────────────────
def test_j_explicit_negative_efficacy_statement():
    """J: Explicit textual statements of lack of efficacy qualify as negative; neutral phrasing is NEUTRAL."""
    om_text = {
        "type": "PRIMARY",
        "title": "Primary endpoint analysis",
        "description": "Investigator concluded lack of efficacy: the study drug failed to meet the primary endpoint.",
        "analyses": [],
    }
    direction, reason = RetrievalPipeline._evaluate_outcome_measure_direction(om_text)
    assert direction == "NEGATIVE"
    assert "lack of efficacy" in reason.lower()

    # Neutral phrasing must evaluate to NEUTRAL
    om_neutral = {
        "type": "PRIMARY",
        "title": "Primary endpoint analysis",
        "description": "There was no statistically significant difference between study drug and placebo.",
        "analyses": [],
    }
    dir_n, reason_n = RetrievalPipeline._evaluate_outcome_measure_direction(om_neutral)
    assert dir_n == "NEUTRAL"
    assert "neutral" in reason_n.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Test K: Negative outcome of unrelated intervention in combination study
# ─────────────────────────────────────────────────────────────────────────────
def test_k_negative_outcome_unrelated_intervention():
    """K: In combination trial where DrugX is background therapy and DrugY fails, DrugX is rejected by attribution."""
    trial_combo = _build_trial(
        nct_id="NCT02020616",
        title="Study of NovelAgent added to Metformin vs Metformin alone",
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        is_negative_efficacy=True,
        intervention_names=["NovelAgent", "Metformin"],
        comparator_names=["Placebo", "Metformin"],
        why_stopped="Lack of efficacy of NovelAgent",
        condition_names=["Type 2 Diabetes Mellitus"],
    )
    # Evaluated for Metformin
    claim = trial_to_negative_claim(trial_combo, "Metformin", "Type 2 Diabetes Mellitus")
    assert claim is None, "Background therapy must NOT be attributed trial failure"
