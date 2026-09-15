"""Script to audit Section 7: Metformin regression on NCT02020616 and 5 other background therapy trials.
"""
import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

from backend.engineering.retrieval.connectors.clinicaltrials import ClinicalTrialsConnector
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.enums.trial_attribution import TrialDrugRole
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    evaluate_trial_attribution,
    analyze_trial_drug_role,
    trial_to_negative_claim,
)

async def audit_metformin():
    print("=" * 80)
    print("SECTION 7: METFORMIN REGRESSION AUDIT")
    print("=" * 80)
    
    # Check NCT02020616
    nct_id = "NCT02020616"
    pipeline = RetrievalPipeline()
    async with ClinicalTrialsConnector() as conn:
        data = await conn.fetch("Metformin", "Type 2 diabetes", max_results=50)
    
    studies = data.get("studies", [])
    s_target = next((s for s in studies if s.get("protocolSection", {}).get("identificationModule", {}).get("nctId") == nct_id), None)
    
    drug = Drug(name="Metformin", identifiers={"chembl": "CHEMBL1431"})
    disease = Disease(name="Type 2 diabetes", identifiers={"mesh": "D003924"})
    
    if s_target:
        parsed_list = pipeline._parse_trials_data({"studies": [s_target]}, drug, disease)
        if parsed_list:
            t = parsed_list[0]
            role, intr_m, comp_m, is_diff, reason = analyze_trial_drug_role(t, "Metformin")
            attr = evaluate_trial_attribution(t, "Metformin")
            claim = trial_to_negative_claim(t, "Metformin", "Type 2 diabetes")
            print(f"NCT02020616 Title: {t.title}")
            print(f"Interventions: {t.intervention_names} | Comparators: {t.comparator_names}")
            print(f"Role: {role.value} | is_diff: {is_diff} | Decision: {attr.final_attribution_decision}")
            print(f"Reason: {attr.attribution_reason}")
            print(f"Claim generated: {claim is not None}")
    else:
        print(f"NCT02020616 not in first 50 results of Metformin query. Checking mock / dedicated fetch...")

    # Identify 5 other combination / background trials in Metformin T2D
    parsed_all = pipeline._parse_trials_data(data, drug, disease)
    bg_trials = []
    for t in parsed_all:
        role, intr_m, comp_m, is_diff, reason = analyze_trial_drug_role(t, "Metformin")
        if role == TrialDrugRole.CONCOMITANT_THERAPY or (role == TrialDrugRole.EVALUATED_COMBINATION_COMPONENT and not is_diff):
            attr = evaluate_trial_attribution(t, "Metformin")
            bg_trials.append((t, role, is_diff, attr))

    print(f"\nTotal parsed Metformin trials: {len(parsed_all)}")
    print(f"Total background-therapy / non-differentiating Metformin trials found: {len(bg_trials)}")
    for i, (t, role, is_diff, attr) in enumerate(bg_trials[:6], 1):
        print(f"\n[{i}] {t.nct_id}: {t.title[:75]}...")
        print(f"    Intr: {t.intervention_names} vs Comp: {t.comparator_names}")
        print(f"    Role: {role.value} | is_diff: {is_diff} | Attributed: {attr.final_attribution_decision}")
        print(f"    Reason: {attr.attribution_reason[:100]}...")

if __name__ == "__main__":
    asyncio.run(audit_metformin())
