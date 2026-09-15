import json
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")

from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    trial_to_negative_claim,
    evaluate_trial_attribution,
)

pipeline = RetrievalPipeline()
cache_dir = Path("data/ct_raw_cache")
results_100_path = Path("evaluation_outputs/100_case_final/results.jsonl")

baseline_100 = {}
with open(results_100_path, "r", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        baseline_100[d["case_id"]] = d

cases_p0b = [
    ("TC-001", "Lisinopril", "Hypertension"),
    ("TC-003", "Budesonide", "Asthma"),
    ("TC-062", "Ranibizumab", "Age-related macular degeneration"),
]

print("=" * 80)
print("P0b: APPROVAL VS OPPOSITION CONFLICT DETAILED AUDIT")
print("=" * 80)

for cid, drug, dis in cases_p0b:
    base = baseline_100[cid]
    safe_name = f"{re.sub(r'[^a-zA-Z0-9_]', '_', drug)}_{re.sub(r'[^a-zA-Z0-9_]', '_', dis)}.json"
    cache_path = cache_dir / safe_name
    raw_studies = json.load(open(cache_path, "r", encoding="utf-8")).get("studies", [])

    parsed = pipeline._parse_trials_data(
        {"studies": raw_studies},
        Drug(name=drug, identifiers={"chembl": "TEST"}),
        Disease(name=dis, identifiers={"mesh": "TEST"}),
    )

    claims = []
    for t in parsed:
        c = trial_to_negative_claim(t, drug, dis)
        if c is not None:
            attr = evaluate_trial_attribution(t, drug)
            claims.append((t, c, attr))

    print(f"\n==================== {cid}: {drug} -> {dis} ====================")
    print(f"Approval anchor in baseline rule: {base.get('decision_rule')}")
    print(f"Negative claims count: {len(claims)}")
    for t, c, attr in claims:
        print(f"Trial NCT ID: {t.nct_id}")
        print(f"  Title: {t.title}")
        print(f"  Status: {t.status}")
        print(f"  whyStopped: {getattr(t, 'why_stopped', None)}")
        print(f"  Conditions: {getattr(t, 'condition_names', [])}")
        print(f"  Design: allocation={getattr(t, 'design_allocation', None)}, study_type={getattr(t, 'study_type', None)}")
        print(f"  Outcome Measures count: {len(getattr(t, 'outcome_measures', []))}")
        for om in getattr(t, 'outcome_measures', [])[:3]:
            print(f"    - OM: type={om.get('type')}, title={om.get('title')}, dir={om.get('direction')}, reason={om.get('reason_code')}")
        print(f"  Attribution role: {attr.drug_role}")
        print(f"  Attribution reason: {attr.attribution_reason}")
        print(f"  Claim predicate: {c.predicate}")
        print(f"  Confidence: {c.confidence}, ERW: {c.erw.value}")
