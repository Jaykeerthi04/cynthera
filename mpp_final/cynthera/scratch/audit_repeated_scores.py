import json
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")

with open("backend/evaluation/before_vs_now_50_end_to_end_ledger.json", "r", encoding="utf-8") as f:
    ledger = json.load(f)

cases = ledger["cases"]
repeated_targets = [0.5670, 0.6885, 0.7493]

from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    trial_to_negative_claim,
    evaluate_trial_attribution,
    determine_trial_evidence_type,
    TherapeuticOppositionAssessor,
)
from backend.reasoning.conflict.evidence_weighting import (
    compute_claim_weight,
    evidence_group_key,
    cluster_into_evidence_groups,
    group_weight,
)

pipeline = RetrievalPipeline()
assessor = TherapeuticOppositionAssessor()

cases_by_score = {}
for c in cases:
    opp = c["now"]["opposition_score"]
    cases_by_score.setdefault(opp, []).append(c)

print("=" * 80)
print("P0.2: REPEATED OPPOSITION SCORES IN CURRENT LEDGER")
print("=" * 80)

for target in repeated_targets:
    matching = cases_by_score.get(target, [])
    print(f"\n==================== SCORE = {target:.4f} ({len(matching)} cases) ====================")
    for c in matching:
        cid = c["case_id"]
        drug = c["drug"]
        dis = c["disease"]
        gold = c["standard_gold"]
        pred = c["now"]["prediction"]
        rule = c["now"]["decision_rule"]

        # Run pipeline trace on this case
        safe_name = f"{re.sub(r'[^a-zA-Z0-9_]', '_', drug)}_{re.sub(r'[^a-zA-Z0-9_]', '_', disease if (disease := dis) else '')}.json"
        cache_path = Path("data/ct_raw_cache") / safe_name
        raw_studies = []
        if cache_path.exists():
            raw_studies = json.load(open(cache_path, "r", encoding="utf-8")).get("studies", [])
        
        parsed = pipeline._parse_trials_data(
            {"studies": raw_studies},
            Drug(name=drug, identifiers={"chembl": "TEST"}),
            Disease(name=dis, identifiers={"mesh": "TEST"}),
        )

        claims = []
        for t in parsed:
            cl = trial_to_negative_claim(t, drug, dis)
            if cl is not None:
                attr = evaluate_trial_attribution(t, drug)
                claims.append((t, cl, attr))

        groups = cluster_into_evidence_groups([cl for _, cl, _ in claims])
        nct_ids = [t.nct_id for t, _, _ in claims]
        g_keys = list(groups.keys())
        g_weights = [group_weight(g_claims) for g_claims in groups.values()]

        print(f"\nCase {cid}: {drug} -> {dis} | Gold: {gold} | Pred: {pred}")
        print(f"  Total Studies Retrieved: {len(raw_studies)} | Parsed: {len(parsed)}")
        print(f"  Negative Claims: {len(claims)}")
        print(f"  NCT IDs: {nct_ids}")
        print(f"  Independent Groups ({len(groups)}): {g_keys}")
        print(f"  Group Weights: {g_weights}")
        for t, cl, attr in claims:
            cw = compute_claim_weight(cl)
            print(f"    - [{t.nct_id}] Predicate={cl.predicate} | Conf={cl.confidence} | ERW={cl.erw.value} | EvType={cl.evidence_type} | Weight={cw} | AttrRole={attr.drug_role}")
            print(f"      whyStopped: {getattr(t, 'why_stopped', None)}")

