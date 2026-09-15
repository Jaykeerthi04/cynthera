import json
import re
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    trial_to_negative_claim,
    evaluate_trial_attribution,
)

pipeline = RetrievalPipeline()
pairs = [
    ("Lisinopril", "Hypertension"),
    ("Budesonide", "Asthma"),
    ("Ranibizumab", "Age-related macular degeneration"),
]

for drug, disease in pairs:
    safe_name = f"{re.sub(r'[^a-zA-Z0-9_]', '_', drug)}_{re.sub(r'[^a-zA-Z0-9_]', '_', disease)}.json"
    raw_data = json.load(open(f"data/ct_raw_cache/{safe_name}"))
    trials = pipeline._parse_trials_data(
        raw_data,
        Drug(name=drug, identifiers={"chembl": "TEST"}),
        Disease(name=disease, identifiers={"mesh": "TEST"})
    )
    print(f"=== {drug} -> {disease} ===")
    for t in trials:
        claim = trial_to_negative_claim(t, drug, disease)
        if claim:
            attr = evaluate_trial_attribution(t, drug)
            print("NCT:", t.nct_id, "status:", t.status, "is_neg:", t.is_negative_efficacy,
                  "whyStopped:", getattr(t, "why_stopped", None),
                  "attr_decision:", attr.final_attribution_decision,
                  "role:", attr.drug_role,
                  "reason:", attr.attribution_reason)
            print("claim:", claim.claim_text, "confidence:", claim.confidence)
