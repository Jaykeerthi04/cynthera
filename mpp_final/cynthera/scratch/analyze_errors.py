import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('evaluation_outputs/100_case_final/results.jsonl', 'r', encoding='utf-8') as f:
    results = [json.loads(line) for line in f]

with open('evaluation_outputs/100_case_final/metrics.json', 'r', encoding='utf-8') as f:
    metrics = json.load(f)

# Let's inspect errors and group them by root cause
errors_std = [r for r in results if not r['is_correct_standard']]
errors_epi = [r for r in results if not r['is_correct_epistemic']]

print(f"Total Standard Errors: {len(errors_std)}")
print(f"Total Epistemic Errors: {len(errors_epi)}")

# Group errors by (Pred, Gold)
error_patterns = {}
for r in errors_std:
    key = f"{r['prediction']} vs Gold {r['standard_gold']}"
    error_patterns[key] = error_patterns.get(key, 0) + 1

print("\nStandard Error Patterns:")
for k, v in error_patterns.items():
    print(f"  {k}: {v}")

error_patterns_epi = {}
for r in errors_epi:
    key = f"{r['epistemic_prediction']} vs EpistemicGold {r['epistemic_gold']}"
    error_patterns_epi[key] = error_patterns_epi.get(key, 0) + 1

print("\nEpistemic Error Patterns:")
for k, v in error_patterns_epi.items():
    print(f"  {k}: {v}")
