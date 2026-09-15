import json
from pathlib import Path

ledger_path = Path("backend/evaluation/post_clinicaltrials_50_fast_ledger.json")
with open(ledger_path, "r", encoding="utf-8") as f:
    ledger = json.load(f)

cases = ledger["cases"]

print("=" * 100)
print("PREDICTION TRANSITIONS (Baseline != Post-Fix)")
print("=" * 100)

transitions = []
for c in cases:
    b_pred = c["baseline_prediction"]
    p_pred = c["prediction"]
    if b_pred != p_pred:
        transitions.append(c)
        print(f"Case ID: {c['case_id']}")
        print(f"  Drug / Disease: {c['drug']} -> {c['disease']}")
        print(f"  Gold: Standard={c['standard_gold']}, Epistemic={c['epistemic_gold']}")
        print(f"  Transition: {b_pred} -> {p_pred}")
        print(f"  Scores: SS={c['support_score']}, MS={c['mechanistic_score']}, RS={c['risk_score']}")
        print(f"  Opposition: Base={c['baseline_opposition_score']} -> Post={c['opposition_score']} ({c['opposition_level']})")
        print(f"  Rule: {c['decision_rule']}")
        print(f"  Reported Change Cause: {c['change_attribution']}")
        print(f"  Reported Root Cause: {c['root_cause_classification']}")
        print(f"  CT Parsed: {c['clinical_trials_parsed']}, Attributed Neg: {c['attributed_negative_trials']}, Claims: {c['negative_claim_count']}")
        print("-" * 80)

print(f"\nTotal transitions: {len(transitions)}")
