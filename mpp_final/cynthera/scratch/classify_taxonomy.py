import json
from collections import Counter
from pathlib import Path

ledger_path = Path("backend/evaluation/post_clinicaltrials_50_fast_ledger.json")
with open(ledger_path, "r", encoding="utf-8") as f:
    ledger = json.load(f)

cases = ledger["cases"]

print("=" * 80)
print("ALL 25 STANDARD POST-FIX ERRORS & CLASSIFICATION")
print("=" * 80)

# Taxonomy:
# A. ClinicalTrials retrieval
# B. ClinicalTrials parsing
# C. ClinicalTrials attribution
# D. Disease relation
# E. Statistical direction parsing
# F. Therapeutic direction
# G. Mechanistic reasoning
# H. Safety/contraindication
# I. Evidence weighting / score saturation
# J. Deduplication / independence
# K. Literature retrieval
# L. Benchmark/evaluator artifact
# M. Other

# Let's inspect each error:
errs = [c for c in cases if c["prediction"] != c["standard_gold"]]
print(f"Total standard errors: {len(errs)}")

for c in errs:
    cid = c["case_id"]
    drug = c["drug"]
    dis = c["disease"]
    gold = c["standard_gold"]
    pred = c["prediction"]
    ss = c["support_score"]
    opp = c["opposition_score"]
    rule = c["decision_rule"]
    rc_rep = c.get("root_cause_classification")
    print(f"{cid} | {drug} -> {dis} | Gold: {gold} | Pred: {pred} | RepRC: {rc_rep} | SS: {ss:.3f} | Opp: {opp:.3f}")
    print(f"  Rule: {rule}")
