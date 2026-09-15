import json
import csv
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('evaluation_outputs/100_case_final/results.jsonl', 'r', encoding='utf-8') as f:
    results = [json.loads(line) for line in f]

print(f"Total results: {len(results)}")

# Let's inspect errors across both tracks
std_errors = [r for r in results if not r['is_correct_standard']]
epi_errors = [r for r in results if not r['is_correct_epistemic']]

print(f"Standard errors: {len(std_errors)}")
print(f"Epistemic errors: {len(epi_errors)}")

# Let's inspect category metrics
cat_stats = {}
for r in results:
    cat = r['category']
    if cat not in cat_stats:
        cat_stats[cat] = {'total': 0, 'std_correct': 0, 'epi_correct': 0, 'supp_gold': 0, 'supp_tp': 0, 'opp_gold': 0, 'opp_tp': 0, 'unc_gold': 0, 'unc_tp': 0, 'fp_supp': 0, 'fp_opp': 0}
    c = cat_stats[cat]
    c['total'] += 1
    if r['is_correct_standard']:
        c['std_correct'] += 1
    if r['is_correct_epistemic']:
        c['epi_correct'] += 1
    if r['standard_gold'] == 'SUPPORT':
        c['supp_gold'] += 1
        if r['prediction'] == 'SUPPORT':
            c['supp_tp'] += 1
    elif r['standard_gold'] == 'OPPOSE':
        c['opp_gold'] += 1
        if r['prediction'] == 'OPPOSE':
            c['opp_tp'] += 1
    elif r['standard_gold'] == 'UNCERTAIN':
        c['unc_gold'] += 1
        if r['prediction'] == 'UNCERTAIN':
            c['unc_tp'] += 1
    
    if r['prediction'] == 'SUPPORT' and r['standard_gold'] != 'SUPPORT':
        c['fp_supp'] += 1
    if r['prediction'] == 'OPPOSE' and r['standard_gold'] != 'OPPOSE':
        c['fp_opp'] += 1

print("\n=== CATEGORY BREAKDOWN ===")
for cat, s in cat_stats.items():
    print(f"{cat}: Total={s['total']} | StdAcc={s['std_correct']/s['total']:.1%} | EpiAcc={s['epi_correct']/s['total']:.1%} | SuppRec={s['supp_tp']}/{s['supp_gold']} | OppRec={s['opp_tp']}/{s['opp_gold']} | UncRec={s['unc_tp']}/{s['unc_gold']} | FP_Supp={s['fp_supp']} | FP_Opp={s['fp_opp']}")
