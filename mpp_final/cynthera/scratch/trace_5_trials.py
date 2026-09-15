"""Script for Section 12: Trace exact evidence lineage for 5 target trials.
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
    analyze_trial_drug_role,
    trial_to_negative_claim,
    matches_disease_condition,
    TherapeuticOppositionAssessor,
)
from backend.engineering.retrieval.disease_relation import classify_disease_relation, matches_for_trial_attribution

TARGET_TRIALS = [
    ("NCT02667587", "Nivolumab", "Glioblastoma"),
    ("NCT02617589", "Nivolumab", "Glioblastoma"),
    ("NCT00120289", "Niacin", "Cardiovascular disease"),
    ("NCT02362321", "Dexamethasone", "Traumatic brain injury"),
    ("NCT02284906", "Pioglitazone", "Alzheimer's disease"),
]

async def trace_5_trials():
    print("=" * 80)
    print("SECTION 12: NEGATIVE SIGNAL PRESERVATION AUDIT (5 TARGET TRIALS)")
    print("=" * 80)
    pipeline = RetrievalPipeline()
    assessor = TherapeuticOppositionAssessor()
    
    for nct_id, drug_name, disease_name in TARGET_TRIALS:
        print(f"\nTracing [{nct_id}] {drug_name} -> {disease_name}...")
        async with ClinicalTrialsConnector() as conn:
            data = await conn.fetch(drug_name, disease_name, max_results=50)
        studies = data.get("studies", [])
        study = next((s for s in studies if s.get("protocolSection", {}).get("identificationModule", {}).get("nctId") == nct_id), None)
        if not study:
            print(f"  [FAIL] {nct_id} NOT found in fetched studies (len={len(studies)})")
            continue
        
        # Step 1: Raw JSON presence
        has_results = study.get("hasResults", False)
        status = study.get("protocolSection", {}).get("statusModule", {}).get("overallStatus")
        why_stopped = study.get("protocolSection", {}).get("statusModule", {}).get("whyStopped")
        print(f"  1. RAW JSON: overallStatus={status}, whyStopped={why_stopped}, hasResults={has_results}")
        
        # Step 2: Parsed trial
        drug = Drug(name=drug_name, identifiers={"chembl": "CHEMBL"})
        disease = Disease(name=disease_name, identifiers={"mesh": "MESH"})
        parsed_trials = pipeline._parse_trials_data({"studies": [study]}, drug, disease)
        if not parsed_trials:
            print(f"  [FAIL] Study failed to parse into ClinicalTrial object!")
            continue
        t = parsed_trials[0]
        print(f"  2. PARSED TRIAL: status={t.status}, neg_eff={t.is_negative_efficacy}, neg_reason={t.negative_efficacy_reason[:75] if t.negative_efficacy_reason else None}")
        
        # Step 3: Disease relation
        dis_match = matches_disease_condition(t, disease_name)
        conds = t.condition_names
        print(f"  3. DISEASE MATCH: matched={dis_match}, conditions={conds}")
        
        # Step 4: Attribution
        attr = evaluate_trial_attribution(t, drug_name)
        print(f"  4. ATTRIBUTION: decision={attr.final_attribution_decision}, role={attr.drug_role.value}, is_diff={attr.is_differentiating_intervention}")
        print(f"     Reason: {attr.attribution_reason[:90]}...")
        
        # Step 5: Negative claim
        claim = trial_to_negative_claim(t, drug_name, disease_name)
        print(f"  5. NEGATIVE CLAIM: generated={claim is not None}")
        if claim:
            print(f"     Subject={claim.subject}, Predicate={claim.predicate}, Confidence={claim.confidence}, ERW={claim.erw.value if hasattr(claim.erw, 'value') else claim.erw}")
            assessment = assessor.assess([claim], drug_name, disease_name)
            print(f"  6. OPPOSITION SCORE: score={assessment.score:.3f}, level={assessment.level}")
        else:
            print(f"  6. OPPOSITION SCORE: 0.000 (No claim generated)")

if __name__ == "__main__":
    asyncio.run(trace_5_trials())
