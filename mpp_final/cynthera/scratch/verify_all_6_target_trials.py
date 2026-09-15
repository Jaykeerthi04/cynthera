import asyncio
import httpx
import json
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
    TherapeuticOppositionAssessor,
)

TARGETS = [
    ("NCT00120289", "Niacin", "Cardiovascular disease"),
    ("NCT02362321", "Dexamethasone", "Traumatic brain injury"),
    ("NCT02667587", "Simvastatin", "Sepsis"),
    ("NCT02617589", "Nivolumab", "Glioblastoma"),
    ("NCT02284906", "Pioglitazone", "Alzheimer's disease"),
    ("NCT02020616", "Metformin", "Type 2 diabetes"),
]

async def main():
    pipeline = RetrievalPipeline()
    assessor = TherapeuticOppositionAssessor()
    results = []
    
    headers = {"Accept": "application/json"}
    async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
        for nct, drug, disease in TARGETS:
            r = await client.get(f"https://clinicaltrials.gov/api/v2/studies/{nct}")
            if r.status_code != 200:
                print(f"Failed to fetch {nct}: {r.status_code}")
                continue
            study = r.json()
            drug_obj = Drug(name=drug, identifiers={"chembl": "CHEMBL_TEST"})
            disease_obj = Disease(name=disease, identifiers={"mesh": "MESH_TEST"})
            trials = pipeline._parse_trials_data({"studies": [study]}, drug_obj, disease_obj)
            if not trials:
                print(f"Failed to parse {nct}")
                continue
            t = trials[0]
            cond_match = matches_disease_condition(t, disease)
            attr = evaluate_trial_attribution(t, drug)
            claim = trial_to_negative_claim(t, drug, disease)
            claims = [claim] if claim else []
            opp = assessor.assess(claims=claims, drug_name=drug, disease_name=disease)
            
            results.append({
                "nct_id": nct,
                "drug": drug,
                "disease": disease,
                "retrieved": True,
                "parsed": True,
                "status": str(t.status),
                "condition_matched": cond_match,
                "drug_role": attr.drug_role.value,
                "drug_attributed": attr.final_attribution_decision,
                "attribution_reason": attr.attribution_reason,
                "negative_claim_generated": claim is not None,
                "opposition_generated": opp.score > 0.0,
                "opposition_score": opp.score,
            })
            print(f"[{nct}] {drug} -> {disease}: parsed=True, cond={cond_match}, role={attr.drug_role.value}, attr={attr.final_attribution_decision}, claim={claim is not None}, opp={opp.score:.3f}")

    with open("scratch/verified_6_targets.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
