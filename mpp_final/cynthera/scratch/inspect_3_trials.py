import sys
sys.path.insert(0, ".")
import json
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.reasoning.opposition.therapeutic_opposition_assessor import trial_to_negative_claim
from backend.infrastructure.cache.raw_response_cache import RawResponseCache

cache = RawResponseCache()
pipe = RetrievalPipeline(db_path=':memory:')

for nct in ['NCT00367055', 'NCT04509674', 'NCT03448406']:
    raw = cache.get('clinicaltrials', nct)
    if not raw:
        print(f'NCT {nct} not in cache')
        continue
    if 'studies' not in raw:
        raw = {'studies': [raw]}
    drug = Drug(name='TestDrug', identifiers={'chembl': 'CHEMBL1'})
    disease = Disease(name='TestDisease', identifiers={'mesh': 'D1'})
    trials = pipe._parse_trials_data(raw, drug, disease)
    for t in trials:
        print(f"{t.nct_id}: status={t.status}, is_negative_efficacy={t.is_negative_efficacy}")
        for om in t.outcome_measures:
            print(f"   OM {om.get('type')}: {om.get('title')[:55]} -> dir={om.get('direction')} (reason_code={om.get('reason_code')})")
