import sys, json
sys.path.insert(0, ".")
from pathlib import Path
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.opposition.therapeutic_opposition_assessor import trial_to_negative_claim
from backend.reasoning.opposition.opposition_qualification import qualify_opposition_claim

raw_data = json.loads(Path("data/ct_raw_cache/Dexamethasone_Traumatic_brain_injury.json").read_text(encoding="utf-8"))
pipeline = RetrievalPipeline()
drug = "Dexamethasone"
disease = "Traumatic brain injury"
parsed = pipeline._parse_trials_data(
    raw_data,
    Drug(name=drug, identifiers={"chembl": "CHEMBL_TEST"}),
    Disease(name=disease, identifiers={"mesh": "MESH_TEST"}),
)

for t in parsed:
    if t.nct_id == "NCT02362321":
        print("Trial NCT02362321:")
        print("  is_negative_efficacy:", t.is_negative_efficacy)
        print("  status:", t.status)
        print("  why_stopped:", t.why_stopped)
        c = trial_to_negative_claim(t, drug, disease)
        print("  Claim generated:", c is not None)
        if c:
            q = qualify_opposition_claim(c, drug, disease, trial=t)
            print("  Qualification:")
            print("    qualified:", q.qualified)
            print("    reason_code:", q.reason_code)
            print("    directness:", q.directness)
            print("    endpoint_relevance:", q.endpoint_relevance)
            print("    explanation:", q.explanation)
