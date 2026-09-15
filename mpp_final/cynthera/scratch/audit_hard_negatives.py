import json
from collections import Counter

ledger = json.load(open('backend/evaluation/post_clinicaltrials_50_fast_ledger.json', encoding='utf-8'))
cases = ledger['cases']

print("=" * 100)
print("AUDIT OF ALL HARD-NEGATIVE CASES (Gold == OPPOSE)")
print("=" * 100)

hard_negs = [c for c in cases if c['standard_gold'] == 'OPPOSE']
print(f"Total hard-negative cases: {len(hard_negs)}\n")

transitions = Counter()
rows = []

for c in hard_negs:
    cid = c['case_id']
    drug = c['drug']
    disease = c['disease']
    b_pred = c['baseline_prediction']
    p_pred = c['prediction']
    
    trans_type = "UNCHANGED"
    if b_pred == "UNCERTAIN" and p_pred == "OPPOSE":
        trans_type = "UNCERTAIN -> CORRECT"
    elif b_pred == "UNCERTAIN" and p_pred == "SUPPORT":
        trans_type = "UNCERTAIN -> INCORRECT (FALSE PROMISING)"
    elif b_pred == "UNCERTAIN" and p_pred == "UNCERTAIN":
        trans_type = "UNCHANGED UNCERTAIN"
    elif b_pred == "OPPOSE" and p_pred == "OPPOSE":
        trans_type = "UNCHANGED CORRECT (OPPOSE)"
    elif b_pred == "SUPPORT" and p_pred == "SUPPORT":
        trans_type = "UNCHANGED INCORRECT (SUPPORT)"
    elif b_pred == "SUPPORT" and p_pred == "OPPOSE":
        trans_type = "INCORRECT (SUPPORT) -> CORRECT (OPPOSE)"
    elif b_pred == "OPPOSE" and p_pred == "SUPPORT":
        trans_type = "CORRECT (OPPOSE) -> INCORRECT (SUPPORT)"
    elif b_pred == "OPPOSE" and p_pred == "UNCERTAIN":
        trans_type = "CORRECT (OPPOSE) -> INCORRECT (UNCERTAIN)"
        
    transitions[trans_type] += 1
    rows.append((cid, drug, disease, b_pred, p_pred, trans_type, c['opposition_score'], c['decision_rule']))

print(f"{'CID':<8} {'Drug':<18} {'Disease':<28} {'Base':<10} {'Post':<10} {'Transition Type':<35} {'OppScore':<8}")
print("-" * 125)
for cid, drug, disease, b_pred, p_pred, trans_type, opp, rule in rows:
    print(f"{cid:<8} {drug[:17]:<18} {disease[:27]:<28} {b_pred:<10} {p_pred:<10} {trans_type:<35} {opp:<8.3f}")

print("\n--- TRANSITION SUMMARY FOR HARD NEGATIVES ---")
for t, count in transitions.most_common():
    print(f"  {t}: {count} ({count/len(hard_negs):.1%})")

# Calculate hard-negative specific metrics
base_correct = sum(1 for c in hard_negs if c['baseline_prediction'] == 'OPPOSE')
post_correct = sum(1 for c in hard_negs if c['prediction'] == 'OPPOSE')

base_unc = sum(1 for c in hard_negs if c['baseline_prediction'] == 'UNCERTAIN')
post_unc = sum(1 for c in hard_negs if c['prediction'] == 'UNCERTAIN')

base_fp = sum(1 for c in hard_negs if c['baseline_prediction'] == 'SUPPORT')
post_fp = sum(1 for c in hard_negs if c['prediction'] == 'SUPPORT')

print("\n--- HARD NEGATIVE METRICS ---")
print(f"Hard-Negative Accuracy (Recall on OPPOSE): Base = {base_correct}/{len(hard_negs)} ({base_correct/len(hard_negs):.4f}), Post = {post_correct}/{len(hard_negs)} ({post_correct/len(hard_negs):.4f})")
print(f"Hard-Negative Uncertainty Rate: Base = {base_unc}/{len(hard_negs)} ({base_unc/len(hard_negs):.4f}), Post = {post_unc}/{len(hard_negs)} ({post_unc/len(hard_negs):.4f})")
print(f"Hard-Negative False-Promising Rate: Base = {base_fp}/{len(hard_negs)} ({base_fp/len(hard_negs):.4f}), Post = {post_fp}/{len(hard_negs)} ({post_fp/len(hard_negs):.4f})")
