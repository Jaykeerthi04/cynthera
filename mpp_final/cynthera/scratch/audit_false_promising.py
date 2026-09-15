import json

ledger = json.load(open('backend/evaluation/post_clinicaltrials_50_fast_ledger.json', encoding='utf-8'))
cases = ledger['cases']

print("=" * 100)
print("AUDIT OF FALSE-PROMISING CASES (Predicted SUPPORT when Gold != SUPPORT)")
print("=" * 100)

base_fp = [c for c in cases if c['baseline_prediction'] == 'SUPPORT' and c['standard_gold'] != 'SUPPORT']
post_fp = [c for c in cases if c['prediction'] == 'SUPPORT' and c['standard_gold'] != 'SUPPORT']

print(f"Baseline False-Promising count: {len(base_fp)}")
for c in base_fp:
    print(f"  [Base FP] {c['case_id']} {c['drug']} -> {c['disease']} | Gold: {c['standard_gold']} | SS={c['support_score']} RS={c['risk_score']}")

print(f"\nPost-Fix False-Promising count: {len(post_fp)}")
for c in post_fp:
    print(f"  [Post FP] {c['case_id']} {c['drug']} -> {c['disease']} | Gold: {c['standard_gold']} | BasePred: {c['baseline_prediction']} | SS={c['support_score']} RS={c['risk_score']} Opp={c['opposition_score']} | Rule: {c['decision_rule']}")
