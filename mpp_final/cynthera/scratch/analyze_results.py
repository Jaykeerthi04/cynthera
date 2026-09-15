import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('evaluation_outputs/100_case_final/results.jsonl', 'r', encoding='utf-8') as f:
    results = [json.loads(line) for line in f]

print(f'Total cases loaded: {len(results)}')

# 1. Verified Negative True Positives
print('\n=== VERIFIED NEGATIVE TRUE POSITIVES (5) ===')
for r in results:
    if r['prediction'] == 'OPPOSE' and r['standard_gold'] == 'OPPOSE':
        print(f"[{r['case_id']}] {r['drug']} -> {r['disease']}")
        print(f"  Standard Gold: {r['standard_gold']} | Epistemic Gold: {r['epistemic_gold']}")
        print(f"  Decision Rule: {r['decision_rule']}")
        print(f"  Opposition Score: {r['opposition_score']} | Level: {r['opposition_level']}")
        print(f"  Neg claims: {r['qualified_negative_claim_count']} | Groups: {r['independent_negative_group_count']}")
        print(f"  Final rationale: {r['final_rationale']}")
        print()

# 2. Missed OPPOSE cases (Standard Gold == OPPOSE, Pred != OPPOSE)
print('\n=== MISSED OPPOSE CASES (FN of OPPOSE in Standard track) ===')
fn_oppose_std = [r for r in results if r['standard_gold'] == 'OPPOSE' and r['prediction'] != 'OPPOSE']
print(f"Total FN of OPPOSE (Standard): {len(fn_oppose_std)}")
for r in fn_oppose_std:
    print(f"[{r['case_id']}] {r['drug']} -> {r['disease']}: Pred={r['prediction']} | EpistemicGold={r['epistemic_gold']} | Rule={r['decision_rule'][:40]} | Supp={r['support_score']:.3f} | Opp={r['opposition_score']:.3f} | Trials={r['clinical_trial_count']} | WithRes={r['trials_with_results']}")

# 3. Missed OPPOSE cases in Epistemic track (Epistemic Gold == OPPOSE, Pred != OPPOSE)
print('\n=== MISSED OPPOSE CASES (FN of OPPOSE in Epistemic track) ===')
fn_oppose_epi = [r for r in results if r['epistemic_gold'] == 'OPPOSE' and r['epistemic_prediction'] != 'OPPOSE']
print(f"Total FN of OPPOSE (Epistemic): {len(fn_oppose_epi)}")
for r in fn_oppose_epi:
    print(f"[{r['case_id']}] {r['drug']} -> {r['disease']}: Pred={r['epistemic_prediction']} | Rule={r['decision_rule'][:40]} | Supp={r['support_score']:.3f} | Opp={r['opposition_score']:.3f}")

# 4. Missed SUPPORT cases (Standard Gold == SUPPORT, Pred != SUPPORT)
print('\n=== MISSED SUPPORT CASES (FN of SUPPORT) ===')
fn_support = [r for r in results if r['standard_gold'] == 'SUPPORT' and r['prediction'] != 'SUPPORT']
print(f"Total FN of SUPPORT: {len(fn_support)}")
for r in fn_support:
    print(f"[{r['case_id']}] {r['drug']} -> {r['disease']}: Pred={r['prediction']} | Rule={r['decision_rule'][:40]} | Supp={r['support_score']:.3f} | Opp={r['opposition_score']:.3f}")

# 5. Correct UNCERTAIN cases (Epistemic Gold == UNCERTAIN, Epistemic Pred == UNCERTAIN)
print('\n=== CORRECT UNCERTAIN (Epistemic) ===')
tp_unc = [r for r in results if r['epistemic_gold'] == 'UNCERTAIN' and r['epistemic_prediction'] == 'UNCERTAIN']
print(f"Total Correct UNCERTAIN (Epistemic): {len(tp_unc)}")
for r in tp_unc:
    print(f"[{r['case_id']}] {r['drug']} -> {r['disease']}: Stress={r['special_stress_condition']} | Rule={r['decision_rule'][:40]} | Supp={r['support_score']:.3f} | Opp={r['opposition_score']:.3f}")
