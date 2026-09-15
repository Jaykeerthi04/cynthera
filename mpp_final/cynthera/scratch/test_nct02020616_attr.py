import asyncio
import httpx
import os
import sys

sys.path.insert(0, os.path.abspath("."))
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    evaluate_trial_attribution,
    trial_to_negative_claim,
    matches_disease_condition,
)

async def test_nct02020616():
    headers = {"Accept": "application/json"}
    async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
        r = await client.get("https://clinicaltrials.gov/api/v2/studies/NCT02020616")
        study = r.json()
    
    pipeline = RetrievalPipeline()
    drug_obj = Drug(name="Metformin", identifiers={"chembl": "CHEMBL_TEST"})
    disease_obj = Disease(name="Type 2 diabetes", identifiers={"mesh": "MESH_TEST"})
    
    trials = pipeline._parse_trials_data({"studies": [study]}, drug_obj, disease_obj)
    t = trials[0]
    
    cond_match = matches_disease_condition(t, "Type 2 diabetes")
    attr = evaluate_trial_attribution(t, "Metformin")
    claim = trial_to_negative_claim(t, "Metformin", "Type 2 diabetes")
    
    print("NCT:", t.nct_id)
    print("Status:", t.status)
    print("Condition Matched:", cond_match)
    print("Attribution Decision:", "ATTRIBUTED" if attr.final_attribution_decision else "REJECTED")
    print("Drug Role:", attr.drug_role.value)
    print("Attribution Reason:", attr.attribution_reason)
    print("Negative Claim Generated:", claim is not None)

if __name__ == "__main__":
    asyncio.run(test_nct02020616())
