import json
import sqlite3
import sys
sys.path.insert(0, ".")

from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    trial_to_negative_claim,
    is_trial_comparator,
)
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.enums.trial_outcome import TrialOutcomeStatus

with open("scratch/corpus_negative_trials.json", "r", encoding="utf-8") as f:
    trials_raw = json.load(f)

results = []
for item in trials_raw:
    trial = ClinicalTrial(
        nct_id=item["nct_id"],
        title=item["title"],
        phase=item["phase"] or "N/A",
        status=TrialOutcomeStatus(item["status"]),
        intervention_names=item["intervention_names"],
        comparator_names=item["comparator_names"],
        why_stopped=item["why_stopped"],
        provenance={"source_name": "ClinicalTrials.gov", "record_id": item["nct_id"], "source_version": "2024"}
    )
    is_comp = is_trial_comparator(trial, item["drug"])
    claim = trial_to_negative_claim(trial, item["drug"], item["disease"])
    
    results.append({
        "case_id": item["case_id"],
        "drug": item["drug"],
        "disease": item["disease"],
        "nct_id": item["nct_id"],
        "phase": item["phase"],
        "status": item["status"],
        "is_comp": is_comp,
        "claim_produced": claim is not None,
        "predicate": claim.predicate.value if claim else None,
        "raw_text": claim.raw_text if claim else None,
    })

print(f"{'Case':<10} | {'Drug':<18} | {'NCT':<12} | {'Phase':<10} | {'Comp?':<6} | {'Claim?':<6} | {'Predicate'}")
print("-" * 85)
for r in results:
    print(f"{r['case_id']:<10} | {r['drug']:<18} | {r['nct_id']:<12} | {r['phase']:<10} | {str(r['is_comp']):<6} | {str(r['claim_produced']):<6} | {r['predicate']}")
