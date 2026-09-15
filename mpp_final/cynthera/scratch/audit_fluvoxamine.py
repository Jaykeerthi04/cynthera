import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

cache_path = Path("data/ct_raw_cache/Fluvoxamine_COVID_19.json")
raw_data = json.load(open(cache_path, "r", encoding="utf-8"))
studies = raw_data.get("studies", [])
print(f"Total Fluvoxamine COVID-19 studies: {len(studies)}")

from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    trial_to_negative_claim,
    evaluate_trial_attribution,
)

pipeline = RetrievalPipeline()
drug_obj = Drug(name="Fluvoxamine", identifiers={"chembl": "CHEMBL_TEST"})
disease_obj = Disease(name="COVID-19", identifiers={"mesh": "MESH_TEST"})
parsed = pipeline._parse_trials_data({"studies": studies}, drug_obj, disease_obj)

print(f"Parsed trials: {len(parsed)}")

for idx, t in enumerate(parsed):
    has_res = bool(t.has_results or t.outcome_measures)
    why_stopped = getattr(t, "why_stopped", None)
    outcomes = getattr(t, "outcome_measures", [])
    print(f"\n[{idx}] Trial {t.nct_id}: Status={t.status} | is_neg={t.is_negative_efficacy} | has_res={has_res}")
    print(f"    Title: {t.title}")
    print(f"    why_stopped: {why_stopped}")
    print(f"    Outcome count: {len(outcomes)}")
    for om_idx, om in enumerate(outcomes):
        print(f"      - OM[{om_idx}]: type={om.get('type')}, title={om.get('title')}")
        print(f"        direction={om.get('direction')}, reason={om.get('reason_code')}, p_val={om.get('p_value')}, stat_type={om.get('stat_type')}")
        if 'analysis' in om:
            print(f"        analysis: {om['analysis']}")
    
    # Attribution
    attr = evaluate_trial_attribution(t, "Fluvoxamine")
    claim = trial_to_negative_claim(t, "Fluvoxamine", "COVID-19")
    print(f"    Attribution: decision={attr.final_attribution_decision}, role={attr.drug_role}, reason={attr.attribution_reason}")
    print(f"    Claim: {claim}")
