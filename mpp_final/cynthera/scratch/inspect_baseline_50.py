import json

with open('scratch/resolved_50_cases.json', encoding='utf-8') as f:
    cases = json.load(f)

cids = [c['case_id'] for c in cases]
results_by_cid = {}
with open('evaluation_outputs/100_case_final/results.jsonl', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        results_by_cid[d['case_id']] = d

print(f"{'Idx':<3} {'CID':<6} {'Drug':<20} {'Disease':<30} {'StdGold':<8} {'Pred':<8} {'SS':<6} {'RS':<6} {'Opp':<6} {'Rule':<35}")
print("-" * 140)

for idx, c in enumerate(cases, 1):
    cid = c['case_id']
    b = results_by_cid.get(cid, {})
    pred = b.get('prediction', 'N/A')
    std = c.get('standard_gold', 'N/A')
    ss = b.get('support_score', 0.0)
    rs = b.get('risk_score', 0.0)
    opp = b.get('opposition_score', 0.0)
    rule = b.get('decision_rule', 'N/A')
    rule_short = rule.split(':')[0] if ':' in rule else rule[:35]
    print(f"{idx:<3} {cid:<6} {c['drug'][:19]:<20} {c['disease'][:29]:<30} {std:<8} {pred:<8} {ss:<6.3f} {rs:<6.3f} {opp:<6.3f} {rule_short[:35]:<35}")
