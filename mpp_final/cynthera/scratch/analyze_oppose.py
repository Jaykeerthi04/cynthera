import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('evaluation_outputs/100_case_final/results.jsonl', 'r', encoding='utf-8') as f:
    results = [json.loads(line) for line in f]

oppose_preds = [r for r in results if r['prediction'] == 'OPPOSE']
print(f"Total OPPOSE predictions: {len(oppose_preds)}")
for r in oppose_preds:
    print(f"[{r['case_id']}] {r['drug']} -> {r['disease']}")
    print(f"  Standard Gold: {r['standard_gold']} | Epistemic Gold: {r['epistemic_gold']}")
    print(f"  Decision Rule: {r['decision_rule']}")
    print(f"  Opposition Score: {r['opposition_score']} | Level: {r['opposition_level']}")
    print(f"  Qualified Neg Claims: {r['qualified_negative_claim_count']} | Groups: {r['independent_negative_group_count']}")
    print(f"  Safety Veto: {r['safety_veto']}")
    print(f"  Contradiction: {r['contradiction_level']}")
    print(f"  Final Rationale: {r['final_rationale']}")
    print()
