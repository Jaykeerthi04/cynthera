"""Script for Section 13: False-Opposition Audit across 7 unverified / control cases.
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
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    evaluate_trial_attribution,
    trial_to_negative_claim,
    TherapeuticOppositionAssessor,
)

CASES_SECTION_13 = [
    ("Furosemide", "Depression"),
    ("Warfarin", "Leishmaniasis"),
    ("Sildenafil", "Alzheimer's disease"),
    ("Sildenafil", "Heart failure"),
    ("Celecoxib", "Cancer"),
    ("Ivermectin", "Cancer"),
    ("Metformin", "Alzheimer's disease"),
]

async def audit_false_opposition():
    print("=" * 80)
    print("SECTION 13: FALSE-OPPOSITION AUDIT")
    print("=" * 80)
    pipeline = RetrievalPipeline()
    assessor = TherapeuticOppositionAssessor()

    for drug_name, disease_name in CASES_SECTION_13:
        try:
            async with ClinicalTrialsConnector() as conn:
                data = await conn.fetch(drug_name, disease_name, max_results=50)
            studies = data.get("studies", [])
            drug = Drug(name=drug_name, identifiers={"chembl": "CHEMBL"})
            disease = Disease(name=disease_name, identifiers={"mesh": "MESH"})
            parsed = pipeline._parse_trials_data(data, drug, disease)
            
            matched_conds = 0
            attributed_count = 0
            claims = []
            
            for t in parsed:
                attr = evaluate_trial_attribution(t, drug_name)
                if attr.final_attribution_decision:
                    attributed_count += 1
                c = trial_to_negative_claim(t, drug_name, disease_name)
                if c:
                    claims.append(c)
            
            assessment = assessor.assess(claims, drug_name, disease_name)
            print(f"{drug_name:<12} -> {disease_name:<22}: Retrieved={len(studies):>2} | Parsed={len(parsed):>2} | Attributed={attributed_count:>2} | NegClaims={len(claims):>2} | OppScore={assessment.score:.3f} | Level={assessment.level}")
            if claims:
                print(f"   --> Generated claims:")
                for cl in claims[:3]:
                    print(f"       [{cl.provenance.record_id if cl.provenance else 'N/A'}] {cl.subject} {cl.predicate} {cl.object} (text: {str(cl.raw_text)[:60]}...)")
        except Exception as e:
            print(f"Error {drug_name} -> {disease_name}: {e}")

if __name__ == "__main__":
    asyncio.run(audit_false_opposition())
