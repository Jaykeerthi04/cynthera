import json
import sqlite3
import sys
sys.path.insert(0, ".")

from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    trial_to_negative_claim,
)
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.reasoning.conflict.evidence_weighting import compute_claim_weight
from backend.evaluation.run_25_case_evaluation import EVALUATION_CASES
from backend.evaluation.holdout_30_case_dataset import HOLDOUT_CASES

con = sqlite3.connect("data/cynthera.db")
cur = con.cursor()

def get_latest_package(drug: str, disease: str):
    cur.execute("""
        SELECT rp.data_json
        FROM hypotheses h
        JOIN retrieval_packages rp ON h.id = rp.hypothesis_id
        WHERE LOWER(h.drug_name) = LOWER(?) AND LOWER(h.disease_name) = LOWER(?)
        ORDER BY rp.sealed_at DESC
        LIMIT 1;
    """, (drug, disease))
    row = cur.fetchone()
    if row:
        return json.loads(row[0])
    return None

all_cases = [(c["drug"], c["disease"]) for c in EVALUATION_CASES] + [(c.drug, c.disease) for c in HOLDOUT_CASES]

phase_groups = {}
total_neg_claims = 0

for drug, disease in all_cases:
    pkg = get_latest_package(drug, disease)
    if not pkg:
        continue
    for t_data in pkg.get("clinical_trials", []):
        try:
            trial = ClinicalTrial(**t_data)
        except Exception:
            # Recreate with pydantic
            trial = ClinicalTrial(
                nct_id=t_data["nct_id"],
                title=t_data["title"],
                phase=t_data.get("phase") or "N/A",
                status=TrialOutcomeStatus(t_data["status"]),
                study_type=t_data.get("study_type"),
                design_allocation=t_data.get("design_allocation"),
                intervention_names=t_data.get("intervention_names", []),
                comparator_names=t_data.get("comparator_names", []),
                why_stopped=t_data.get("why_stopped"),
                provenance=t_data.get("provenance") or {"source_name": "ClinicalTrials.gov", "record_id": t_data["nct_id"], "source_version": "2024"}
            )
        claim = trial_to_negative_claim(trial, drug, disease)
        if claim is not None:
            total_neg_claims += 1
            weight = compute_claim_weight(claim)
            phase_raw = trial.phase or "Unknown"
            if "Phase I/II" in phase_raw or phase_raw == "Phase I":
                phase_bin = "Phase I"
            elif "Phase II/III" in phase_raw or phase_raw == "Phase II":
                phase_bin = "Phase II"
            elif phase_raw == "Phase III":
                phase_bin = "Phase III"
            elif phase_raw == "Phase IV":
                phase_bin = "Phase IV"
            else:
                phase_bin = "Unknown"
            
            if phase_bin not in phase_groups:
                phase_groups[phase_bin] = []
            phase_groups[phase_bin].append({
                "drug": drug,
                "disease": disease,
                "nct_id": trial.nct_id,
                "raw_phase": phase_raw,
                "weight": weight,
                "evidence_type": claim.evidence_type,
                "title": trial.title
            })

print(f"Total negative claims found: {total_neg_claims}")
print("=== NEGATIVE CLAIMS BY PHASE (REAL CACHED TRIAL OBJECTS) ===")
for p in ["Phase I", "Phase II", "Phase III", "Phase IV", "Unknown"]:
    claims = phase_groups.get(p, [])
    count = len(claims)
    weights = [c["weight"] for c in claims]
    mean_w = sum(weights) / count if count > 0 else 0.0
    max_w = max(weights) if count > 0 else 0.0
    print(f"| {p:<10} | {count:^15} | {mean_w:^19.4f} | {max_w:^18.4f} |")
    for c in claims:
        print(f"    - {c['nct_id']} ({c['raw_phase']}) {c['drug']} -> {c['disease']}: weight={c['weight']} (ev_type={c['evidence_type']})")

con.close()
