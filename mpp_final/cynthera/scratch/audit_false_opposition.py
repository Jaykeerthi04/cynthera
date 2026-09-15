import json

ledger = json.load(open('backend/evaluation/post_clinicaltrials_50_fast_ledger.json', encoding='utf-8'))
cases = ledger['cases']

print("=" * 100)
print("AUDIT OF FALSE-OPPOSITION CASES (Predicted OPPOSE when Gold == SUPPORT)")
print("=" * 100)

base_fo = [c for c in cases if c['baseline_prediction'] == 'OPPOSE' and c['standard_gold'] == 'SUPPORT']
post_fo = [c for c in cases if c['prediction'] == 'OPPOSE' and c['standard_gold'] == 'SUPPORT']

print(f"Baseline False-Opposition count: {len(base_fo)}")
for c in base_fo:
    print(f"  [Base FO] {c['case_id']} {c['drug']} -> {c['disease']} | BaseRule: {c.get('baseline_rule', 'N/A')} | SS={c['support_score']} RS={c['risk_score']} Opp={c['baseline_opposition_score']}")

print(f"\nPost-Fix False-Opposition count: {len(post_fo)}")
for c in post_fo:
    print(f"  [Post FO] {c['case_id']} {c['drug']} -> {c['disease']} | BasePred: {c['baseline_prediction']} | SS={c['support_score']} RS={c['risk_score']} Opp={c['opposition_score']} | Rule: {c['decision_rule']}")
