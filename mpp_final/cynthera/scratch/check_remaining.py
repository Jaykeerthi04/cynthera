import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))
from backend.engineering.retrieval.connectors.clinicaltrials import ClinicalTrialsConnector
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    trial_to_negative_claim,
    TherapeuticOppositionAssessor,
)

CASES = [
    ("Ivermectin", "COVID-19"),
    ("Fluvoxamine", "COVID-19"),
    ("Simvastatin", "Alzheimer's disease"),
    ("Valproic acid", "Glioblastoma"),
    ("Gefitinib", "Non-small cell lung cancer"),
    ("Crizotinib", "Non-small cell lung cancer"),
]

async def check():
    pipeline = RetrievalPipeline()
    assessor = TherapeuticOppositionAssessor()
    for drug_name, disease_name in CASES:
        try:
            async with ClinicalTrialsConnector() as conn:
                data = await conn.fetch(drug_name, disease_name, max_results=50)
            drug = Drug(name=drug_name, identifiers={"chembl": "CHEMBL"})
            disease = Disease(name=disease_name, identifiers={"mesh": "MESH"})
            trials = pipeline._parse_trials_data(data, drug, disease)
            claims = []
            for t in trials:
                c = trial_to_negative_claim(t, drug_name, disease_name)
                if c:
                    claims.append(c)
            assessment = assessor.assess(claims, drug_name, disease_name)
            ret_count = len(data.get("studies", []))
            print(f"{drug_name} -> {disease_name}: retrieved={ret_count}, parsed={len(trials)}, neg_claims={len(claims)}, opp_score={assessment.score:.3f}, level={assessment.level}")
        except Exception as e:
            print(f"Error {drug_name}: {e}")

if __name__ == "__main__":
    asyncio.run(check())
