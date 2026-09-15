import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath("."))

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.enums.trial_attribution import TrialDrugRole
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.engineering.retrieval.connectors.clinicaltrials import ClinicalTrialsConnector
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.engineering.retrieval.disease_relation import (
    classify_disease_relation,
    matches_for_approval_anchor,
    evaluate_approval_anchor_match,
    evaluate_trial_attribution_match,
)
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    trial_to_negative_claim,
    evaluate_trial_attribution,
)

async def test_5():
    with open('scratch/resolved_50_cases.json', encoding='utf-8') as f:
        cases = json.load(f)[:5]
    
    pipeline = RetrievalPipeline()
    assessor = TherapeuticOppositionAssessor()
    
    for c in cases:
        drug = c['drug']
        disease = c['disease']
        t0 = time.time()
        async with ClinicalTrialsConnector() as conn:
            data = await conn.fetch(drug, disease, max_results=50)
        studies = data.get("studies", [])
        drug_obj = Drug(name=drug, identifiers={"chembl": "CHEMBL_TEST"})
        disease_obj = Disease(name=disease, identifiers={"mesh": "MESH_TEST"})
        trials = pipeline._parse_trials_data(data, drug_obj, disease_obj)
        
        claims = []
        for t in trials:
            cl = trial_to_negative_claim(t, drug, disease)
            if cl:
                claims.append(cl)
        opp = assessor.assess(claims, drug, disease)
        print(f"[{c['case_id']}] {drug} -> {disease}: retrieved={len(studies)}, parsed={len(trials)}, claims={len(claims)}, opp={opp.score:.3f} ({opp.level}) in {time.time()-t0:.2f}s")

if __name__ == "__main__":
    asyncio.run(test_5())
