import sys
sys.path.insert(0, ".")
import asyncio
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.enums.trial_attribution import TrialDrugRole
from backend.core.value_objects.provenance import ProvenanceReference
from backend.reasoning.opposition.therapeutic_opposition_assessor import evaluate_trial_attribution

# Trial 1: Autoinjector preference study
t1 = ClinicalTrial(
    nct_id="NCT01875991",
    title="Preference Between Two Autoinjectors in Patients With Rheumatoid Arthritis and Plaque Psoriasis Treated With Etanercept",
    phase="Phase IV",
    status=TrialOutcomeStatus.COMPLETED_FAILURE,
    intervention_names=["Etanercept via Autoinjector A", "Etanercept via Autoinjector B"],
    comparator_names=[],
    is_negative_efficacy=True,
    negative_efficacy_reason="Outcome 'Change From Baseline in Needle Apprehension at Week 4' failed to achieve statistical significance (p=0.501 >= 0.05, Van Elteren test)",
    provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="2024", record_id="NCT01875991"),
)

# Trial 2: Observational radiographic study
t2 = ClinicalTrial(
    nct_id="NCT01623752",
    title="Prospective Evaluation of the Radiographic Efficacy of Enbrel",
    phase="Phase IV",
    status=TrialOutcomeStatus.COMPLETED_FAILURE,
    intervention_names=["Etanercept", "Etanercept"],
    comparator_names=[],
    is_negative_efficacy=True,
    negative_efficacy_reason="Outcome 'Change From Pre-treatment in Normalized Radiographic Progression of mTSS or Adapted mTSS at End of Phase 1 (Week 78): EAS' failed to achieve statistical significance (p=0.278 >= 0.05, Paired t-test)",
    provenance=ProvenanceReference(source_name="ClinicalTrials.gov", source_version="2024", record_id="NCT01623752"),
)

import re

def is_device_or_usability_endpoint(title: str, desc: str = "") -> bool:
    text = f"{title} {desc}".lower()
    cues = (
        "needle apprehension", "autoinjector", "preference", "device",
        "ease of use", "usability", "satisfaction", "questionnaire",
        "willingness to", "compliance", "adherence"
    )
    return any(c in text for c in cues)

print("t1 endpoint is usability:", is_device_or_usability_endpoint(t1.negative_efficacy_reason))

