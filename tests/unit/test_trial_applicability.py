from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.trial_applicability import (
    TrialApplicabilityStatus,
    assess_trial_applicability,
)


def make_trial(title: str, conditions: list[str]) -> ClinicalTrial:
    return ClinicalTrial(
        nct_id="NCT12345678",
        title=title,
        phase="Phase III",
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        provenance=ProvenanceReference(
            source_name="ClinicalTrials.gov",
            source_version="test",
            record_id="NCT12345678",
            url="https://clinicaltrials.gov/study/NCT12345678",
        ),
        condition_names=conditions,
    )


def test_exact_disease_is_direct():
    result = assess_trial_applicability(
        make_trial("Study in heart failure", ["Heart failure"]),
        "Heart failure",
    )
    assert result.status == TrialApplicabilityStatus.DIRECT
    assert result.direct_therapeutic_evidence is True


def test_biomarker_query_rejects_unselected_trial():
    result = assess_trial_applicability(
        make_trial("Study in non-small-cell lung cancer", ["Non-small-cell lung cancer"]),
        "EGFR-positive lung cancer",
    )
    assert result.status == TrialApplicabilityStatus.SUBTYPE_MISMATCH
    assert result.direct_therapeutic_evidence is False


def test_explicit_population_mismatch_is_not_direct():
    result = assess_trial_applicability(
        make_trial("Adult pulmonary arterial hypertension study", ["Pulmonary arterial hypertension"]),
        "Pediatric pulmonary arterial hypertension",
    )
    assert result.status == TrialApplicabilityStatus.POPULATION_MISMATCH
    assert result.direct_therapeutic_evidence is False


def test_explicit_dose_mismatch_is_not_direct():
    result = assess_trial_applicability(
        make_trial("Low-dose pulmonary arterial hypertension study", ["Pulmonary arterial hypertension"]),
        "High-dose pulmonary arterial hypertension",
    )
    assert result.status == TrialApplicabilityStatus.DOSE_MISMATCH
    assert result.direct_therapeutic_evidence is False


def test_sibling_disease_is_not_direct():
    result = assess_trial_applicability(
        make_trial("Hemorrhagic stroke study", ["Hemorrhagic stroke"]),
        "Ischemic stroke",
    )
    assert result.status == TrialApplicabilityStatus.SUBTYPE_MISMATCH
    assert result.direct_therapeutic_evidence is False
