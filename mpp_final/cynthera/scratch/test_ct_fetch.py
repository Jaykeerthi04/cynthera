import asyncio
import os
import sys
import time
sys.path.insert(0, os.path.abspath("."))
from backend.engineering.retrieval.connectors.clinicaltrials import ClinicalTrialsConnector
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    trial_to_negative_claim,
    evaluate_trial_attribution,
    TherapeuticOppositionAssessor,
)

async def main():
    t0 = time.time()
    drug_name = "Lisinopril"
    disease_name = "Hypertension"
    async with ClinicalTrialsConnector() as conn:
        res = await conn.fetch(drug_name, disease_name, max_results=50)
    fetch_dt = time.time() - t0
    
    pipeline = RetrievalPipeline()
    drug_obj = Drug(name=drug_name, identifiers={"chembl": "CHEMBL_TEST"})
    disease_obj = Disease(name=disease_name, identifiers={"mesh": "MESH_TEST"})
    
    t1 = time.time()
    parsed_trials = pipeline._parse_trials_data(res, drug_obj, disease_obj)
    parse_dt = time.time() - t1
    
    claims = []
    for t in parsed_trials:
        c = trial_to_negative_claim(t, drug_name, disease_name)
        if c:
            claims.append(c)
            
    assessor = TherapeuticOppositionAssessor()
    opp = assessor.assess(claims=claims, drug_name=drug_name, disease_name=disease_name)
    opp_dt = time.time() - t1
    
    print(f"Fetch: {fetch_dt:.2f}s, Parse: {parse_dt:.3f}s, Total Opp eval: {opp_dt:.3f}s")
    print(f"Parsed trials: {len(parsed_trials)}, Neg claims: {len(claims)}, Opp score: {opp.score}, Opp level: {opp.level}")

if __name__ == "__main__":
    asyncio.run(main())
