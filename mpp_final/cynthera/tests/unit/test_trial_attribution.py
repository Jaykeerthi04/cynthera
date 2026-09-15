"""Unit tests for Clinical Trial Attribution Logic (Phase 1A).

Deterministic test suite validating the 8 core attribution cases (A through H)
plus Metformin and Niacin regression verification as required by Phase 1A specification.

Test A: Drug appears only in experimental arm -> eligible for attribution.
Test B: Drug appears only in comparator arm -> not attributed as experimental failure.
Test C: Drug appears identically in both arms as background therapy -> rejected.
Test D: Drug appears in all arms but differs by dose/intensity -> eligible for attribution.
Test E: Combination therapy where Drug X is intentionally in treatment arm -> potentially attributable.
Test F: Generic "Lack of Efficacy" termination with no drug attribution -> requires structural attribution.
Test G: Explicit "lack of efficacy of Drug X" -> strong attribution-text evidence.
Test H: Duplicate source record -> merged into single evidence group.
"""
from __future__ import annotations

import pytest

from backend.core.domain.claim import Claim
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.trial_attribution import TrialDrugRole, AttributionTextEvidence
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    analyze_trial_drug_role,
    analyze_failure_attribution_text,
    evaluate_trial_attribution,
    trial_to_negative_claim,
)


def _build_trial(
    nct_id: str = "NCT00000001",
    title: str = "Clinical Trial Evaluation",
    status: TrialOutcomeStatus = TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
    phase: str = "Phase III",
    intervention_names: list[str] | None = None,
    comparator_names: list[str] | None = None,
    why_stopped: str | None = None,
    condition_names: list[str] | None = None,
) -> ClinicalTrial:
    """Helper to build a valid ClinicalTrial entity."""
    return ClinicalTrial(
        nct_id=nct_id,
        title=title,
        phase=phase,
        status=status,
        intervention_names=intervention_names or [],
        comparator_names=comparator_names or [],
        why_stopped=why_stopped,
        condition_names=condition_names or [],
        provenance=ProvenanceReference(
            source_name="ClinicalTrials.gov",
            source_version="2024",
            record_id=nct_id,
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test A: Drug appears only in experimental arm
# ─────────────────────────────────────────────────────────────────────────────

def test_a_drug_appears_only_in_experimental_arm():
    """Test A: Drug appears only in experimental arm -> eligible for attribution."""
    trial = _build_trial(
        nct_id="NCT01000001",
        title="Study of DrugX vs Placebo",
        intervention_names=["DrugX"],
        comparator_names=["Placebo"],
        condition_names=["DiseaseY"],
        why_stopped="Futility",
    )
    attr = evaluate_trial_attribution(trial, "DrugX")
    assert attr.drug_role == TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION
    assert attr.is_differentiating_intervention is True
    assert attr.intervention_match is True
    assert attr.comparator_match is False
    assert attr.final_attribution_decision is True

    claim = trial_to_negative_claim(trial, "DrugX", "DiseaseY")
    assert claim is not None
    assert claim.subject == "DrugX"
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE
    assert claim.attribution_trace is not None
    assert claim.attribution_trace["drug_role"] == TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION.value


# ─────────────────────────────────────────────────────────────────────────────
# Test B: Drug appears only in comparator arm
# ─────────────────────────────────────────────────────────────────────────────

def test_b_drug_appears_only_in_comparator_arm():
    """Test B: Drug appears only in comparator arm -> not attributed as experimental failure."""
    trial = _build_trial(
        nct_id="NCT01000002",
        title="InvestigationalAgent versus Aspirin in Secondary Prevention",
        intervention_names=["InvestigationalAgent"],
        comparator_names=["Aspirin"],
        why_stopped="Lack of Efficacy",
    )
    attr = evaluate_trial_attribution(trial, "Aspirin")
    assert attr.drug_role == TrialDrugRole.COMPARATOR_ONLY
    assert attr.is_differentiating_intervention is False
    assert attr.intervention_match is False
    assert attr.comparator_match is True
    assert attr.final_attribution_decision is False

    claim = trial_to_negative_claim(trial, "Aspirin", "Cardiovascular disease")
    assert claim is None


# ─────────────────────────────────────────────────────────────────────────────
# Test C: Drug appears identically in both arms as background therapy
# ─────────────────────────────────────────────────────────────────────────────

def test_c_drug_appears_identically_in_both_arms_as_background_therapy():
    """Test C: Drug appears identically in both arms as background therapy -> not attributed."""
    trial = _build_trial(
        nct_id="NCT02020616",
        title="A Study of the Safety and Effectiveness of LY3053102 in Participants With Type 2 Diabetes",
        phase="Phase I",
        intervention_names=["LY3053102", "Metformin"],
        comparator_names=["Placebo", "Metformin"],
        why_stopped="Lack of Efficacy",
    )
    attr = evaluate_trial_attribution(trial, "Metformin")
    assert attr.drug_role == TrialDrugRole.BACKGROUND_CONSTANT_THERAPY
    assert attr.is_differentiating_intervention is False
    assert attr.intervention_match is True
    assert attr.comparator_match is True
    assert attr.final_attribution_decision is False
    assert "constant background therapy" in attr.attribution_reason

    claim = trial_to_negative_claim(trial, "Metformin", "Type 2 diabetes mellitus")
    assert claim is None


# ─────────────────────────────────────────────────────────────────────────────
# Test D: Drug appears in all arms but differs by dose/intensity
# ─────────────────────────────────────────────────────────────────────────────

def test_d_drug_differs_by_dose_intensity_in_experimental_contrast():
    """Test D: Drug appears in all arms but differs by dose/intensity -> eligible for attribution."""
    trial = _build_trial(
        nct_id="NCT01000004",
        title="Dose-ranging Study of DrugX in Severe Disease",
        intervention_names=["DrugX 1000mg"],
        comparator_names=["DrugX 500mg"],
        why_stopped="Futility at higher dose",
    )
    attr = evaluate_trial_attribution(trial, "DrugX")
    assert attr.drug_role == TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION
    assert attr.is_differentiating_intervention is True
    assert attr.intervention_match is True
    assert attr.comparator_match is True
    assert attr.final_attribution_decision is True
    assert "dose-response contrast" in attr.attribution_reason

    claim = trial_to_negative_claim(trial, "DrugX", "Severe Disease")
    assert claim is not None
    assert claim.attribution_trace["is_differentiating_intervention"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Test E: Combination therapy where Drug X is intentionally part of treatment arm
# ─────────────────────────────────────────────────────────────────────────────

def test_e_combination_therapy_where_drug_is_treatment_contrast():
    """Test E: Combination therapy where Drug X is part of experimental contrast -> potentially attributable."""
    trial = _build_trial(
        nct_id="NCT00120289",
        title="Niacin Plus Statin to Prevent Vascular Events",
        phase="Phase III",
        intervention_names=["Extended release niacin", "Simvastatin"],
        comparator_names=["Simvastatin"],
        condition_names=["Cardiovascular disease"],
        why_stopped="AIM-HIGH was stopped on the recommendation of the DSMB because of lack of efficacy of niacin in preventing primary outcome events.",
    )
    attr = evaluate_trial_attribution(trial, "Niacin")
    assert attr.drug_role == TrialDrugRole.EVALUATED_COMBINATION_COMPONENT
    assert attr.is_differentiating_intervention is True
    assert attr.intervention_match is True
    assert attr.comparator_match is False
    assert attr.final_attribution_decision is True

    claim = trial_to_negative_claim(trial, "Niacin", "Cardiovascular disease")
    assert claim is not None
    assert claim.subject == "Niacin"
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE


# ─────────────────────────────────────────────────────────────────────────────
# Test F: Generic "Lack of Efficacy" with no drug attribution
# ─────────────────────────────────────────────────────────────────────────────

def test_f_generic_lack_of_efficacy_requires_structural_attribution():
    """Test F: Generic failure text requires structural attribution; generic text on background fails."""
    # Sub-case 1: Generic failure on background therapy -> rejected
    trial_bg = _build_trial(
        nct_id="NCT01000006",
        title="NovelAgent on Background Metformin in Diabetes",
        intervention_names=["NovelAgent", "Metformin"],
        comparator_names=["Placebo", "Metformin"],
        why_stopped="Lack of Efficacy",
    )
    attr_bg = evaluate_trial_attribution(trial_bg, "Metformin")
    assert attr_bg.text_attribution_result == AttributionTextEvidence.GENERIC_FAILURE_REASON
    assert attr_bg.drug_role == TrialDrugRole.BACKGROUND_CONSTANT_THERAPY
    assert attr_bg.final_attribution_decision is False

    # Sub-case 2: Generic failure on primary evaluated drug -> valid
    trial_primary = _build_trial(
        nct_id="NCT01000007",
        title="Study of NovelAgent in Diabetes",
        intervention_names=["NovelAgent"],
        comparator_names=["Placebo"],
        why_stopped="Lack of Efficacy",
    )
    attr_pri = evaluate_trial_attribution(trial_primary, "NovelAgent")
    assert attr_pri.text_attribution_result == AttributionTextEvidence.GENERIC_FAILURE_REASON
    assert attr_pri.drug_role == TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION
    assert attr_pri.final_attribution_decision is True


# ─────────────────────────────────────────────────────────────────────────────
# Test G: Explicit "lack of efficacy of Drug X"
# ─────────────────────────────────────────────────────────────────────────────

def test_g_explicit_drug_attribution_text():
    """Test G: Explicit drug mention in termination rationale -> EXPLICIT_DRUG_ATTRIBUTION."""
    text_ev, reason = analyze_failure_attribution_text(
        why_stopped="Stopped early due to lack of efficacy of niacin in the target population.",
        title="AIM-HIGH Study",
        drug_name="Niacin",
    )
    assert text_ev == AttributionTextEvidence.EXPLICIT_DRUG_ATTRIBUTION
    assert "Niacin" in reason

    # Contrast with generic text
    text_ev_gen, _ = analyze_failure_attribution_text(
        why_stopped="Lack of Efficacy",
        title="LY Study",
        drug_name="Metformin",
    )
    assert text_ev_gen == AttributionTextEvidence.GENERIC_FAILURE_REASON


# ─────────────────────────────────────────────────────────────────────────────
# Test H: Duplicate source record
# ─────────────────────────────────────────────────────────────────────────────

def test_h_duplicate_source_record_merged():
    """Test H: Multiple negative claims with same record_id do not create duplicate independent groups."""
    prov = ProvenanceReference(
        source_name="ClinicalTrials.gov",
        source_version="2024",
        record_id="NCT00120289",
    )
    claim1 = Claim(
        subject="Niacin",
        predicate=PredicateType.FAILED_TO_IMPROVE,
        object="Cardiovascular disease",
        confidence=0.95,
        erw=ERW(value=0.90, base_weight=0.90),
        provenance=prov,
        raw_text="AIM-HIGH stopped for lack of efficacy of niacin.",
        is_validated=True,
        evidence_type="RCT",
    )
    claim2 = Claim(
        subject="Niacin",
        predicate=PredicateType.FAILED_TO_IMPROVE,
        object="Cardiovascular disease",
        confidence=0.90,
        erw=ERW(value=0.90, base_weight=0.90),
        provenance=prov,
        raw_text="Secondary publication of AIM-HIGH futility.",
        is_validated=True,
        evidence_type="RCT",
    )

    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim1, claim2], "Niacin", "Cardiovascular disease")
    assert assessment.qualified_negative_claim_count == 2
    assert assessment.independent_group_count == 1  # Grouped by record:NCT00120289
    assert assessment.score == pytest.approx(0.5670, abs=0.001)


# ─────────────────────────────────────────────────────────────────────────────
# Metformin & Niacin Specific Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_metformin_ly3053102_trial_excluded():
    """Verify Metformin NCT02020616 is rejected and produces no negative claim."""
    trial = _build_trial(
        nct_id="NCT02020616",
        title="A Study of the Safety and Effectiveness of LY3053102 in Participants With Type 2 Diabetes",
        phase="Phase I",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        intervention_names=["LY3053102", "Metformin", "LY3053102", "Exenatide ER", "Metformin"],
        comparator_names=["Placebo", "Metformin", "Exenatide ER", "Metformin"],
        why_stopped="Lack of Efficacy",
    )
    attr = evaluate_trial_attribution(trial, "Metformin")
    assert attr.drug_role == TrialDrugRole.BACKGROUND_CONSTANT_THERAPY
    assert attr.is_differentiating_intervention is False
    assert attr.final_attribution_decision is False

    claim = trial_to_negative_claim(trial, "Metformin", "Type 2 diabetes mellitus")
    assert claim is None


def test_niacin_aim_high_trial_attributed():
    """Verify Niacin NCT00120289 (AIM-HIGH) is attributed and produces a valid negative claim."""
    trial = _build_trial(
        nct_id="NCT00120289",
        title="Niacin Plus Statin to Prevent Vascular Events",
        phase="Phase III",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        intervention_names=["Extended release niacin", "Simvastatin"],
        comparator_names=["Simvastatin"],
        condition_names=["Cardiovascular disease"],
        why_stopped="AIM-HIGH was stopped on the recommendation of the DSMB because of lack of efficacy of niacin in preventing primary outcome events.",
    )
    attr = evaluate_trial_attribution(trial, "Niacin")
    assert attr.is_differentiating_intervention is True
    assert attr.text_attribution_result == AttributionTextEvidence.EXPLICIT_DRUG_ATTRIBUTION
    assert attr.final_attribution_decision is True

    claim = trial_to_negative_claim(trial, "Niacin", "Cardiovascular disease")
    assert claim is not None
    assert claim.subject == "Niacin"
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE
    assert claim.attribution_trace["is_differentiating_intervention"] is True
